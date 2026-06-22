#!/usr/bin/env python3
"""
Duo Hub — 双AI协作中心
一键启动，让 Claude Code 和 龙虾(OpenClaw) 同时看到你的需求并协商分工
"""

import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path

# ============================================================
# 配置 — 从 config.json 读取，支持环境变量覆盖
# ============================================================
HOST = "127.0.0.1"
PORT = int(os.environ.get("DUO_PORT", "5199"))
AI_TIMEOUT = int(os.environ.get("DUO_AI_TIMEOUT", "300"))

def _load_config():
    """加载配置，优先环境变量，其次 config.json，最后自动检测"""
    config = {}
    config_file = Path(__file__).parent / "config.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass

    # 协议目录
    protocol_dir = os.environ.get("DUO_PROTOCOL_DIR", config.get("protocol_dir", ""))
    if protocol_dir:
        PROTOCOL_DIR = Path(protocol_dir)
    else:
        PROTOCOL_DIR = Path.home() / ".duo_hub" / "protocol"

    # Claude 工作区
    claude_ws = os.environ.get("DUO_CLAUDE_WORKSPACE", config.get("claude_workspace", ""))
    CLAUDE_WORKSPACE = Path(claude_ws) if claude_ws else Path.cwd()

    # Web 目录
    WEB_DIR = Path(__file__).parent / "web"

    # 网关端口
    CCMR_PORT = int(os.environ.get("DUO_CCMR_PORT", config.get("ccmr_port", "8080")))
    OPENCLAW_PORT = int(os.environ.get("DUO_OPENCLAW_PORT", config.get("openclaw_port", "18789")))

    return PROTOCOL_DIR, CLAUDE_WORKSPACE, WEB_DIR, CCMR_PORT, OPENCLAW_PORT

PROTOCOL_DIR, CLAUDE_WORKSPACE, WEB_DIR, CCMR_PORT, OPENCLAW_PORT = _load_config()

INBOX_FILE = PROTOCOL_DIR / "inbox" / "current_task.txt"
OUTBOX_CLAUDE = PROTOCOL_DIR / "outbox" / "claude.md"
OUTBOX_LOBSTER = PROTOCOL_DIR / "outbox" / "lobster.md"
SESSION_FILE = PROTOCOL_DIR / "session.json"
CHAT_FILE = PROTOCOL_DIR / "chat.json"


def _find_tool(name, env_var, known_paths):
    """查找可执行文件：环境变量 > PATH 搜索 > 已知路径"""
    env_val = os.environ.get(env_var, "")
    if env_val and Path(env_val).exists():
        return env_val
    for p in known_paths:
        if Path(p).exists():
            return p
    # 最后尝试 PATH 中的命令
    return name


# 自动检测 ccmr
_ccmr_candidates = [
    str(Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "claude-code-model-router" / "dist" / "cli.js"),
]
# 也尝试找 claude-code-model-router 的安装位置
import glob as _glob
for _base in [str(Path.home() / "AppData" / "Roaming" / "npm" / "node_modules"),
              str(Path.home() / "AppData" / "Local" / "pnpm" / "global")]:
    _matches = _glob.glob(f"{_base}/**/claude-code-model-router/dist/cli.js", recursive=True)
    _ccmr_candidates.extend(_matches)

NODE_CMD = "node"
CCMR_JS = _find_tool("ccmr_js", "DUO_CCMR_JS", _ccmr_candidates)

# 自动检测 openclaw
_oc_candidates = [
    str(Path.home() / "AppData" / "Local" / "pnpm" / "openclaw.cmd"),
]
for _base in [str(Path.home() / "AppData" / "Local" / "pnpm" / "global")]:
    _matches = _glob.glob(f"{_base}/**/openclaw/openclaw.mjs", recursive=True)
    _oc_candidates.extend(_matches)
OPENCLAW_CMD = _find_tool("openclaw", "DUO_OPENCLAW_CMD", _oc_candidates)

# 构建子进程环境
_ENV = os.environ.copy()
_npm_bin = str(Path.home() / "AppData" / "Roaming" / "npm")
_pnpm_bin = str(Path.home() / "AppData" / "Local" / "pnpm")
_ENV["PATH"] = os.pathsep.join([_npm_bin, _pnpm_bin, _ENV.get("PATH", "")])

# OpenClaw NODE_PATH（自动检测）
_oc_node_paths = []
for _base in [str(Path.home() / "AppData" / "Local" / "pnpm" / "global")]:
    _matches = _glob.glob(f"{_base}/**/openclaw/node_modules", recursive=True)
    for _m in _matches:
        _oc_node_paths.append(_m)
        _oc_node_paths.append(str(Path(_m).parent))
if _oc_node_paths:
    _oc_path = os.pathsep.join(_oc_node_paths)
    _ENV["NODE_PATH"] = _oc_path + os.pathsep + _ENV.get("NODE_PATH", "")

# ============================================================
# DuoHub — 协议和状态管理
# ============================================================
class DuoHub:
    def __init__(self):
        self.lock = threading.Lock()
        self._ensure_dirs()
        self._init_session()
        self._init_chat()

    def _ensure_dirs(self):
        PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
        (PROTOCOL_DIR / "inbox").mkdir(exist_ok=True)
        (PROTOCOL_DIR / "outbox").mkdir(exist_ok=True)

    def _init_session(self):
        if SESSION_FILE.exists():
            try:
                with open(SESSION_FILE, "r", encoding="utf-8") as f:
                    self.session = json.load(f)
            except Exception:
                self.session = self._new_session()
        else:
            self.session = self._new_session()
        self._save_session()

    def _new_session(self):
        return {
            "session_id": f"dh_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "phase": "idle",
            "round": 0,
            "claude_status": "idle",
            "lobster_status": "idle",
            "claude_model": "deepseek-v4-pro",
            "lobster_model": "deepseek/deepseek-v4-flash",  # DeepSeek 比 GPT 快且便宜
            "active_task_id": None,
            "created_at": datetime.now().isoformat(),
        }

    def _init_chat(self):
        if CHAT_FILE.exists():
            try:
                with open(CHAT_FILE, "r", encoding="utf-8") as f:
                    self.chat = json.load(f)
            except Exception:
                self.chat = {"messages": []}
        else:
            self.chat = {"messages": []}
        self._save_chat()

    def _save_session(self):
        with self.lock:
            tmp = SESSION_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.session, f, ensure_ascii=False, indent=2)
            tmp.replace(SESSION_FILE)

    def _save_chat(self):
        with self.lock:
            tmp = CHAT_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.chat, f, ensure_ascii=False, indent=2)
            tmp.replace(CHAT_FILE)

    # ---- 网关检测 ----
    def check_gateways(self):
        return {
            "ccmr": self._port_open(CCMR_PORT),
            "openclaw": self._port_open(OPENCLAW_PORT),
        }

    @staticmethod
    def _port_open(port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except Exception:
            return False

    # ---- 消息管理 ----
    def _next_msg_id(self):
        return f"msg_{len(self.chat['messages']) + 1:04d}"

    def add_message(self, role, content):
        msg = {
            "id": self._next_msg_id(),
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "round": self.session["round"],
        }
        self.chat["messages"].append(msg)
        self._save_chat()
        return msg

    def get_recent_messages(self, n=20):
        return self.chat["messages"][-n:]

    # ---- 协议 I/O ----
    def write_inbox(self, task_text):
        recent = self.get_recent_messages(10)
        ctx = ""
        if recent:
            ctx = "\n\n## 对话上下文\n\n"
            labels = {
                "user": "天火大人",
                "claude": "Claude Code",
                "lobster": "龙虾 (OpenClaw)",
                "system": "系统",
            }
            for m in recent:
                role_label = labels.get(m["role"], m["role"])
                ctx += f"**{role_label}**: {m['content']}\n\n"

        header = (
            "# Duo Hub 协作任务\n\n"
            "你正在双AI协作中心工作，搭档是另一方 AI。天火大人通过 Duo Hub 同时与你们两个交互。\n\n"
            "工作规则：\n"
            "1. 分析任务需求，给出你的方案\n"
            "2. 标注你擅长的部分和需要对方配合的部分\n"
            "3. 如果是协商，请明确提出分工建议（格式：- XX负责：xxx）\n"
            "4. 回复使用中文，结构清晰\n\n"
            "---\n\n"
            "# 当前任务\n\n"
        )
        content = f"{header}{task_text}{ctx}"
        INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(INBOX_FILE, "w", encoding="utf-8") as f:
            f.write(content)

    def read_outbox(self, ai_name):
        outbox = OUTBOX_CLAUDE if ai_name == "claude" else OUTBOX_LOBSTER
        if outbox.exists():
            try:
                with open(outbox, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                return None
        return None

    def get_outbox_mtime(self, ai_name):
        outbox = OUTBOX_CLAUDE if ai_name == "claude" else OUTBOX_LOBSTER
        if outbox.exists():
            try:
                return outbox.stat().st_mtime
            except Exception:
                return 0
        return 0

    def clear_outbox(self, ai_name):
        outbox = OUTBOX_CLAUDE if ai_name == "claude" else OUTBOX_LOBSTER
        outbox.parent.mkdir(parents=True, exist_ok=True)
        with open(outbox, "w", encoding="utf-8") as f:
            f.write("")

    # ---- AI 调用 ----
    def invoke_claude(self, task_text, model=None, mode="task"):
        """在后台线程中调用 Claude Code — 通过 stdin 传提示词避免命令行截断"""
        try:
            self.session["claude_status"] = "working"
            self.session["_claude_started"] = time.time()
            self._save_session()
            self.clear_outbox("claude")

            if mode == "negotiate":
                hub_prompt = (
                    "[Duo Hub 协商模式]\n"
                    "你正在和 OpenClaw「龙虾」协商分工。下面是你和对方的上一轮回复。\n"
                    "请阅读后提出一个明确的分工方案。\n"
                    "格式：\n- Claude负责：[具体任务]\n- 龙虾负责：[具体任务]\n"
                    "规则：责任明确不重叠。回复使用中文。\n"
                )
                short_prompt = f"协商上下文：\n\n{task_text}"
            elif mode == "execute":
                hub_prompt = (
                    "[Duo Hub 执行模式]\n"
                    "分工已确认。立即执行你负责的部分——直接写代码、创建文件、运行命令。\n"
                    "不要再问问题、不要再提议。完成后报告。回复使用中文。\n"
                )
                short_prompt = f"执行上下文：\n\n{task_text}"
            else:
                hub_prompt = (
                    "[Duo Hub 协作模式]\n"
                    "你在双AI协作中心工作，搭档是OpenClaw「龙虾」。\n"
                    "分析任务需求并给出方案。回复使用中文。\n"
                )
                recent = self.get_recent_messages(10)
                history = "\n\n".join([f"[{m['role']}]: {m['content']}" for m in recent])
                short_prompt = f"对话历史：\n{history}\n\n---\n最新任务：{task_text}"

            # 将完整提示词写入文件，通过 stdin 传给 ccmr（避开 Windows 命令行 8191 字符限制）
            full_prompt = f"{hub_prompt}\n\n---\n\n{short_prompt}"
            import uuid
            prompt_file = PROTOCOL_DIR / "inbox" / f"_claude_stdin_{uuid.uuid4().hex[:8]}.txt"
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(full_prompt)

            cmd = [
                NODE_CMD, CCMR_JS, "claude",
                "--print",
                "--dangerously-skip-permissions",
                "--permission-mode", "bypassPermissions",
                "--output-format", "text",
                "--model", model or self.session.get("claude_model", "deepseek-v4-pro"),
                "--add-dir", str(CLAUDE_WORKSPACE).replace("/", "\\"),
            ]

            with open(prompt_file, "r", encoding="utf-8") as f:
                result = subprocess.run(
                    cmd,
                    stdin=f,
                    capture_output=True,
                    text=True,
                    timeout=AI_TIMEOUT,
                    cwd=str(CLAUDE_WORKSPACE),
                    encoding="utf-8",
                    errors="replace",
                    env=_ENV,
                )

            # 清理临时文件
            try:
                prompt_file.unlink()
            except Exception:
                pass

            output = (result.stdout or "").strip()
            if not output and result.stderr:
                output = f"[Claude 输出为空]\nstderr: {result.stderr[:500]}"

            # 移除末尾的 [DuoHub:完成] 标记
            marker = "[DuoHub:完成]"
            if output.endswith(marker):
                output = output[: -len(marker)].strip()

            with open(OUTBOX_CLAUDE, "w", encoding="utf-8") as f:
                f.write(output)

            self.session["claude_status"] = "done"
            self._save_session()

        except subprocess.TimeoutExpired:
            with open(OUTBOX_CLAUDE, "w", encoding="utf-8") as f:
                f.write("Claude Code 响应超时（超过 300 秒）")
            self.session["claude_status"] = "timeout"
            self._save_session()
        except Exception as e:
            with open(OUTBOX_CLAUDE, "w", encoding="utf-8") as f:
                f.write(f"Claude Code 调用出错: {str(e)}")
            self.session["claude_status"] = "error"
            self._save_session()

    def invoke_lobster(self, task_text, model=None, mode="task"):
        """在后台线程中调用 OpenClaw (龙虾) — 网关模式(比local快10s+) + 读文件获取中文任务"""
        try:
            self.session["lobster_status"] = "working"
            self.session["_lobster_started"] = time.time()
            self._save_session()
            self.clear_outbox("lobster")

            inbox = str(INBOX_FILE).replace("\\", "/")
            if mode == "negotiate":
                short_prompt = f"Read {inbox} for negotiation context. Propose division. Reply in Chinese."
            elif mode == "execute":
                short_prompt = f"Read {inbox}. The division plan is approved. Execute your assigned tasks NOW. Do not ask questions - just do it. Write code, create files, run commands. Report what you did. Reply in Chinese."
            else:
                short_prompt = f"Read {inbox} and respond to the task. Reply in Chinese."

            model_arg = model or self.session.get("lobster_model", "deepseek/deepseek-v4-flash")
            oc_cmd = OPENCLAW_CMD
            cmd = f'"{oc_cmd}" agent --message "{short_prompt}" --session-key duo_hub --local --json --model {model_arg}'

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=AI_TIMEOUT,
                encoding="utf-8",
                errors="replace",
                shell=True,
                env=_ENV,
            )

            output = ""
            if result.stdout:
                raw = result.stdout.strip()
                json_str = DuoHub._extract_json(raw)
                if json_str:
                    try:
                        data = json.loads(json_str)
                        # 网关模式: result.payloads[0].text
                        # 本地模式: payloads[0].text
                        result_wrapper = data.get("result", data)
                        payloads = result_wrapper.get("payloads", [])
                        if payloads and isinstance(payloads, list) and len(payloads) > 0:
                            text = payloads[0].get("text", "")
                            if text and text.strip():
                                output = text.strip()
                        if not output:
                            output = result_wrapper.get("reply") or data.get("reply") or data.get("text") or data.get("content") or ""
                    except json.JSONDecodeError:
                        pass
                # JSON 提取失败 → 尝试整个 stdout 作为纯文本
                if not output:
                    # 跳过已知的横幅行
                    lines = raw.split("\n")
                    clean = []
                    for line in lines:
                        s = line.strip()
                        if not s or s.startswith("session.") or "state-migration" in s.lower() or "[plugin" in s.lower():
                            continue
                        if s.startswith("\x1b[") or "warning" in s.lower():
                            continue
                        clean.append(line)
                    output = "\n".join(clean).strip()
                if not output:
                    output = raw[:500] + "..." if len(raw) > 500 else raw

            # stderr 通常只是诊断信息，不作为回复内容
            if not output:
                output = f"[龙虾未返回有效回复]\nstdout({len(result.stdout)}): {result.stdout[:200]}\nstderr({len(result.stderr)}): {result.stderr[:200]}"

            with open(OUTBOX_LOBSTER, "w", encoding="utf-8") as f:
                f.write(output)

            self.session["lobster_status"] = "done"
            self._save_session()

        except subprocess.TimeoutExpired:
            with open(OUTBOX_LOBSTER, "w", encoding="utf-8") as f:
                f.write("龙虾 (OpenClaw) 响应超时（超过 300 秒）")
            self.session["lobster_status"] = "timeout"
            self._save_session()
        except Exception as e:
            with open(OUTBOX_LOBSTER, "w", encoding="utf-8") as f:
                f.write(f"龙虾 (OpenClaw) 调用出错: {str(e)}")
            self.session["lobster_status"] = "error"
            self._save_session()

    @staticmethod
    def _extract_json(text):
        """从混合文本中提取第一个完整 JSON 对象"""
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return None

    def process_task(self, task_text, needs_division=False):
        """提交任务：同时启动两个 AI"""
        if self.session["phase"] in ("ai_working", "negotiating"):
            return False, "已有任务正在处理中"

        self.session["round"] += 1
        self.session["phase"] = "ai_working"
        self.session["active_task_id"] = f"task_{self.session['round']:03d}"
        self.session["_needs_division"] = needs_division
        self._save_session()

        # 写 inbox
        self.write_inbox(task_text)

        # 添加用户消息
        self.add_message("user", task_text)

        # 后台线程同时启动两个 AI（传当前模型设置）
        cm = self.session.get("claude_model", "deepseek-v4-pro")
        lm = self.session.get("lobster_model", "deepseek/deepseek-v4-pro")
        t1 = threading.Thread(target=self.invoke_claude, args=(task_text, cm), daemon=True)
        t2 = threading.Thread(target=self.invoke_lobster, args=(task_text, lm), daemon=True)
        t1.start()
        t2.start()

        return True, self.session["active_task_id"]

    def check_and_collect_results(self):
        """检查两个 AI 是否完成，收集结果，自动推进阶段"""
        phase = self.session["phase"]

        # 超时检测：AI 卡在 working 状态超过 120 秒 → 强制标记为 timeout
        now = time.time()
        for ai in ("claude", "lobster"):
            if self.session.get(f"{ai}_status") == "working":
                started = self.session.get(f"_{ai}_started", 0)
                if started and now - started > AI_TIMEOUT + 10:
                    self.session[f"{ai}_status"] = "timeout"
                    outbox = OUTBOX_CLAUDE if ai == "claude" else OUTBOX_LOBSTER
                    with open(outbox, "w", encoding="utf-8") as f:
                        f.write(f"{ai} 处理超时（超过120秒无响应）")
                    self._save_session()

        if phase == "ai_working":
            claude_done = self.session["claude_status"] in ("done", "timeout", "error")
            lobster_done = self.session["lobster_status"] in ("done", "timeout", "error")

            if claude_done and self.session.get("_claude_collected") != self.session["round"]:
                text = self.read_outbox("claude")
                if text:
                    self.add_message("claude", text)
                    self.session["_claude_collected"] = self.session["round"]
                    self._save_session()

            if lobster_done and self.session.get("_lobster_collected") != self.session["round"]:
                text = self.read_outbox("lobster")
                if text:
                    self.add_message("lobster", text)
                    self.session["_lobster_collected"] = self.session["round"]
                    self._save_session()

            if claude_done and lobster_done:
                # 用户勾选了"需要分工"→ 自动进入协商
                if self.session.get("_needs_division"):
                    self._auto_negotiate()
                else:
                    self.session["phase"] = "awaiting_user"
                self._save_session()

        elif phase == "negotiating":
            stage = self.session.get("_negotiate_stage", "")
            claude_done = self.session["claude_status"] in ("done", "timeout", "error")
            lobster_done = self.session["lobster_status"] in ("done", "timeout", "error")

            if stage == "claude_proposes":
                # Claude 提议阶段：只等 Claude
                if claude_done and self.session.get("_claude_collected") != self.session["round"]:
                    text = self.read_outbox("claude")
                    if text:
                        self.add_message("claude", text)
                        self.session["_claude_collected"] = self.session["round"]
                        self._save_session()
                    # Claude 说完了 → 龙虾来回应
                    self._negotiate_lobster_respond()

            elif stage == "claude_adjusts":
                # Claude 调整轮：等 Claude 调整完 → 再给龙虾看
                if claude_done and self.session.get("_claude_collected") != self.session["round"]:
                    text = self.read_outbox("claude")
                    if text:
                        self.add_message("claude", text)
                        self.session["_claude_collected"] = self.session["round"]
                        self._save_session()
                    self._negotiate_lobster_respond()

            elif stage == "lobster_confirms":
                if lobster_done and self.session.get("_lobster_collected") != self.session["round"]:
                    text = self.read_outbox("lobster")
                    if text:
                        self.add_message("lobster", text)
                        self.session["_lobster_collected"] = self.session["round"]
                        self._save_session()

                    # 检查龙虾是否同意了
                    agree_keywords = ["同意", "确认", "没问题", "可以", "OK", "ok", "好的", "就这样"]
                    lobster_agreed = any(kw in text for kw in agree_keywords) if text else False
                    neg_rounds = self.session.get("_neg_rounds", 0) + 1
                    self.session["_neg_rounds"] = neg_rounds

                    if lobster_agreed or neg_rounds >= 3:
                        # 达成一致或达到最大轮次 → 等待确认
                        self.session["phase"] = "pending_confirmation"
                        msg = "✅ 协商完成！请确认分工。" if lobster_agreed else "⚠️ 已达最大协商轮次，请确认当前方案。"
                        self.add_message("system", msg)
                        self._save_session()
                    else:
                        # 龙虾有不同意见 → Claude 再调整
                        self._negotiate_claude_adjust()

        elif phase == "executing":
            claude_done = self.session["claude_status"] in ("done", "timeout", "error")
            lobster_done = self.session["lobster_status"] in ("done", "timeout", "error")

            if claude_done and self.session.get("_claude_collected") != self.session["round"]:
                text = self.read_outbox("claude")
                if text:
                    self.add_message("claude", text)
                    self.session["_claude_collected"] = self.session["round"]
                    self._save_session()

            if lobster_done and self.session.get("_lobster_collected") != self.session["round"]:
                text = self.read_outbox("lobster")
                if text:
                    self.add_message("lobster", text)
                    self.session["_lobster_collected"] = self.session["round"]
                    self._save_session()

            if claude_done and lobster_done:
                self.session["phase"] = "done"
                self.add_message("system", "🎉 双方执行完毕！请在面板中查看各自成果。")
                self._save_session()

    def _auto_negotiate(self):
        """顺序协商：Claude 先提议分工 → 龙虾看了再确认"""
        recent = self.get_recent_messages(10)
        ctx_parts = []
        for m in recent:
            role_map = {"user": "天火大人", "claude": "Claude", "lobster": "龙虾"}
            ctx_parts.append(f"[{role_map.get(m['role'], m['role'])}]: {m['content']}")
        context_str = "\n\n".join(ctx_parts)

        # 第一阶段：Claude 看龙虾回复后提议分工
        self.session["round"] += 1
        self.session["phase"] = "negotiating"
        self.session["claude_status"] = "working"
        self.session["lobster_status"] = "idle"
        self.session["_claude_collected"] = 0
        self.session["_negotiate_round"] = self.session["round"]
        self.session["_negotiate_stage"] = "claude_proposes"
        self._save_session()

        self.add_message("system", "🤝 Claude 正在阅读龙虾的方案，准备提议分工…")

        cm = self.session.get("claude_model", "deepseek-v4-pro")
        claude_prompt = (
            "## 协商分工 - 你来提议\n\n"
            "请阅读龙虾的方案，提出一个明确的分工。格式：\n"
            "- Claude负责：[你要做的具体任务]\n"
            "- 龙虾负责：[龙虾要做的具体任务]\n"
            "规则：责任明确不重叠。回复使用中文。\n\n"
            f"---\n{context_str}"
        )
        self.write_inbox(claude_prompt)
        t1 = threading.Thread(target=self.invoke_claude, args=(claude_prompt, cm, "negotiate"), daemon=True)
        t1.start()

    def _negotiate_lobster_respond(self):
        """第二阶段：龙虾看 Claude 提议后确认/调整"""
        recent = self.get_recent_messages(15)
        ctx_parts = []
        for m in recent:
            role_map = {"user": "天火大人", "claude": "Claude", "lobster": "龙虾", "system": "系统"}
            ctx_parts.append(f"[{role_map.get(m['role'], m['role'])}]: {m['content']}")
        context_str = "\n\n".join(ctx_parts)

        self.session["lobster_status"] = "working"
        self.session["_lobster_collected"] = 0
        self.session["_negotiate_stage"] = "lobster_confirms"
        self._save_session()

        self.add_message("system", "🤝 龙虾正在阅读 Claude 的分工提议…")

        lm = self.session.get("lobster_model", "deepseek/deepseek-v4-flash")
        lobster_prompt = (
            "## 协商分工 - 你来确认\n\n"
            "Claude 已经提出了分工方案（见上文）。请确认或调整：\n"
            "- 同意就说「同意分工」并列出你要执行的任务\n"
            "- 不同意的部分请说明怎么调整\n"
            "回复使用中文。\n\n"
            f"---\n{context_str}"
        )
        self.write_inbox(lobster_prompt)
        t2 = threading.Thread(target=self.invoke_lobster, args=(lobster_prompt, lm, "negotiate"), daemon=True)
        t2.start()

    def _negotiate_claude_adjust(self):
        """后续协商轮：Claude 看了龙虾的反馈后调整方案"""
        recent = self.get_recent_messages(15)
        ctx_parts = []
        for m in recent:
            role_map = {"user": "天火大人", "claude": "Claude", "lobster": "龙虾", "system": "系统"}
            ctx_parts.append(f"[{role_map.get(m['role'], m['role'])}]: {m['content']}")
        context_str = "\n\n".join(ctx_parts)

        self.session["round"] += 1
        self.session["claude_status"] = "working"
        self.session["lobster_status"] = "idle"
        self.session["_claude_collected"] = 0
        self.session["_claude_started"] = time.time()
        self.session["_negotiate_stage"] = "claude_adjusts"
        self._save_session()

        self.add_message("system", "🤝 龙虾有不同意见，Claude 正在调整方案…")

        cm = self.session.get("claude_model", "deepseek-v4-pro")
        claude_prompt = (
            "## 协商 - 调整方案\n\n"
            "龙虾看了你的方案后有反馈（见上文）。请根据龙虾的意见调整分工方案，"
            "努力达成一致。如果龙虾的反馈合理就接受。\n"
            "格式：\n- Claude负责：[调整后的任务]\n- 龙虾负责：[调整后的任务]\n"
            "回复使用中文。\n\n"
            f"---\n{context_str}"
        )
        self.write_inbox(claude_prompt)
        t = threading.Thread(target=self.invoke_claude, args=(claude_prompt, cm, "negotiate"), daemon=True)
        t.start()

    def negotiate(self):
        """手动触发重新协商"""
        if self.session["phase"] not in ("awaiting_user", "pending_confirmation", "done"):
            return False, "当前阶段不能发起协商"

        self._auto_negotiate()
        return True, "ok"

    def confirm_plan(self):
        """用户确认分工方案 → 提取各自任务，分别触发执行"""
        if self.session["phase"] != "pending_confirmation":
            return False, "没有待确认的分工方案"

        self.session["phase"] = "executing"
        self.session["_exec_round"] = self.session["round"]
        self.add_message("system", "✅ 天火大人已确认分工！双方开始执行各自任务…")
        self._save_session()

        # 提取协商轮双方的完整回复
        recent = self.get_recent_messages(20)
        all_context = "\n\n".join([f"[{m['role']}]: {m['content']}" for m in recent])

        # 给 Claude 的执行指令：包含完整上下文 + 强调执行 Claude 的部分
        claude_task = (
            "## 执行阶段 - Claude\n\n"
            "分工方案已经天火大人确认。**你负责的部分已经在下方对话中明确标注（Claude负责：xxx）**。\n"
            "不要问问题、不要提议——立即用 Write/Bash/Edit 等工具动手执行你的任务。\n"
            "完成后报告你具体做了什么。\n\n"
            f"---\n{all_context}"
        )

        # 写 inbox 给龙虾读
        lobster_task = (
            "## 执行阶段 - 龙虾\n\n"
            "分工已确认。**你负责的部分在对话中标注了（龙虾负责：xxx）**。"
            "立即执行，不要提问。完成后报告。\n\n"
            f"---\n{all_context}"
        )
        self.write_inbox(lobster_task)

        # 启动执行
        cm = self.session.get("claude_model", "deepseek-v4-pro")
        lm = self.session.get("lobster_model", "deepseek/deepseek-v4-flash")
        t1 = threading.Thread(target=self.invoke_claude, args=(claude_task, cm, "execute"), daemon=True)
        t2 = threading.Thread(target=self.invoke_lobster, args=(lobster_task, lm, "execute"), daemon=True)
        t1.start()
        t2.start()

        return True, "ok"

    def set_model(self, ai, model):
        """切换 AI 模型"""
        if ai == "claude":
            self.session["claude_model"] = model
        elif ai == "lobster":
            self.session["lobster_model"] = model
        else:
            return False
        self._save_session()
        return True

    def stop_session(self):
        """重置会话（保留历史为新会话存档）"""
        # 归档旧会话
        if self.chat.get("messages"):
            archive_dir = PROTOCOL_DIR / "archive"
            archive_dir.mkdir(exist_ok=True)
            archive_file = archive_dir / f"session_{self.session['session_id']}.json"
            try:
                with open(archive_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "session": self.session,
                        "chat": self.chat,
                    }, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # 创建新会话
        self.session = self._new_session()
        self.chat = {"messages": []}
        self._save_session()
        self._save_chat()

    def get_state(self):
        """获取完整状态（供 API 返回）"""
        self.check_and_collect_results()

        messages = self.chat.get("messages", [])
        recent = messages[-30:] if len(messages) > 30 else messages

        # 提取协商结果（如果有）
        division = None
        if self.session["phase"] in ("pending_confirmation", "confirmed"):
            for m in reversed(messages):
                if m.get("round") == self.session.get("_negotiate_round") and m["role"] in ("claude", "lobster"):
                    division = {
                        "claude": m["content"] if m["role"] == "claude" else "",
                        "lobster": m["content"] if m["role"] == "lobster" else "",
                    }
                    # 找配对的另一个
                    for m2 in reversed(messages):
                        if m2.get("round") == m["round"] and m2["role"] != m["role"] and m2["role"] in ("claude", "lobster"):
                            if m["role"] == "claude":
                                division["lobster"] = m2["content"]
                            else:
                                division["claude"] = m2["content"]
                            break
                    break

        return {
            "session_id": self.session["session_id"],
            "phase": self.session["phase"],
            "round": self.session["round"],
            "claude_status": self.session["claude_status"],
            "lobster_status": self.session["lobster_status"],
            "claude_model": self.session.get("claude_model", "deepseek-v4-pro"),
            "lobster_model": self.session.get("lobster_model", "deepseek/deepseek-v4-pro"),
            "active_task_id": self.session.get("active_task_id"),
            "gateways": self.check_gateways(),
            "messages": recent,
            "total_messages": len(messages),
            "division": division,
            "created_at": self.session["created_at"],
        }


# ============================================================
# HTTP 请求处理
# ============================================================
hub = DuoHub()


class DuoHubHandler(http.server.BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    def log_message(self, format, *args):
        # 简洁日志 (避免 emoji 编码问题)
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}", flush=True)
        except UnicodeEncodeError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] request", flush=True)

    # ---- 路由分发 ----
    def do_OPTIONS(self):
        """CORS 预检请求处理"""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._serve_static("index.html", "text/html; charset=utf-8")
        elif path == "/style.css":
            self._serve_static("style.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self._serve_static("app.js", "application/javascript; charset=utf-8")
        elif path == "/api/state":
            self._serve_json(hub.get_state())
        else:
            self._send_error(404, "Not Found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        body = self._read_body()

        if path == "/api/task":
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._serve_json({"error": "Invalid JSON"}, 400)
                return

            text = data.get("text", "").strip()
            needs_division = data.get("needs_division", False)
            if not text:
                self._serve_json({"error": "任务内容不能为空"}, 400)
                return

            ok, task_id = hub.process_task(text, needs_division=needs_division)
            if ok:
                self._serve_json({"ok": True, "task_id": task_id})
            else:
                self._serve_json({"error": task_id}, 409)

        elif path == "/api/negotiate":
            ok, msg = hub.negotiate()
            if ok:
                self._serve_json({"ok": True})
            else:
                self._serve_json({"error": msg}, 409)

        elif path == "/api/stop":
            hub.stop_session()
            self._serve_json({"ok": True})

        elif path == "/api/confirm":
            ok, msg = hub.confirm_plan()
            if ok:
                self._serve_json({"ok": True})
            else:
                self._serve_json({"error": msg}, 409)

        elif path == "/api/set-model":
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._serve_json({"error": "Invalid JSON"}, 400)
                return

            ai = data.get("ai", "")
            model = data.get("model", "")
            if ai not in ("claude", "lobster") or not model:
                self._serve_json({"error": "需要 ai 和 model 参数"}, 400)
                return

            if hub.set_model(ai, model):
                self._serve_json({"ok": True, "ai": ai, "model": model})
            else:
                self._serve_json({"error": "无效参数"}, 400)

        else:
            self._send_error(404, "Not Found")

    # ---- 工具方法 ----
    def _serve_static(self, filename, content_type):
        filepath = WEB_DIR / filename
        if not filepath.exists():
            self._send_error(404, f"File not found: {filename}")
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            data = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(data))
            self._send_cors_headers()
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self._send_error(500, str(e))

    def _serve_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self._send_cors_headers()
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            # 循环读取确保读满所有字节（修复中文 UTF-8 截断问题）
            raw = b""
            while len(raw) < length:
                chunk = self.rfile.read(length - len(raw))
                if not chunk:
                    break
                raw += chunk
            return raw.decode("utf-8", errors="replace")
        return ""

    def _send_error(self, code, message):
        self._serve_json({"error": message}, code)


# ============================================================
# 启动入口
# ============================================================
def main():
    # 修复 Windows GBK 终端的 emoji 编码问题
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("=" * 56)
    print("  ⚡ Duo Hub — 天火大人的双AI协作中心")
    print("=" * 56)
    print()
    print(f"  协议目录: {PROTOCOL_DIR}")
    print(f"  前端文件: {WEB_DIR}")
    print()

    # 检查网关
    print("[检测] 网关状态...")
    gws = hub.check_gateways()
    ccmr_icon = "[OK]" if gws["ccmr"] else "[XX]"
    oc_icon = "[OK]" if gws["openclaw"] else "[XX]"
    print(f"  {ccmr_icon} ccmr 网关 (端口 {CCMR_PORT})")
    print(f"  {oc_icon} OpenClaw 网关 (端口 {OPENCLAW_PORT})")
    print()

    if not gws["ccmr"] or not gws["openclaw"]:
        print("[!!] 部分网关未运行，请先启动相应网关")
        print("     或者使用 launch_duo_hub.cmd 一键启动全部服务")
        print()

    # 启动 HTTP 服务器
    server = http.server.ThreadingHTTPServer((HOST, PORT), DuoHubHandler)
    print(f"[启动] Duo Hub 服务器 -> http://{HOST}:{PORT}")
    print()
    print("  按 Ctrl+C 停止服务器")
    print("=" * 56)

    # 自动打开浏览器
    def open_browser():
        time.sleep(0.5)
        webbrowser.open(f"http://{HOST}:{PORT}")

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[停止] 服务器已关闭")
        server.shutdown()


if __name__ == "__main__":
    main()
