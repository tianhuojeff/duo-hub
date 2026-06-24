#!/usr/bin/env python3
"""
Duo Hub — 三AI协作中心
一键启动，让 Claude Code、龙虾(OpenClaw) 和 Codex 同时看到你的需求并协商分工
"""

import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
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
APP_VERSION = "0.4.3"
GATEWAY_CACHE_TTL = int(os.environ.get("DUO_GATEWAY_CACHE_TTL", "30"))
GATEWAY_CHECK_TIMEOUT = float(os.environ.get("DUO_GATEWAY_CHECK_TIMEOUT", "1"))

def _load_config():
    """加载配置，优先环境变量，其次 config.local.json/config.json，最后自动检测"""
    config = {}
    for filename in ("config.json", "config.local.json"):
        config_file = Path(__file__).parent / filename
        if not config_file.exists():
            continue
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config.update(json.load(f))
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

    # Codex 工作区
    codex_ws = os.environ.get("DUO_CODEX_WORKSPACE", config.get("codex_workspace", ""))
    CODEX_WORKSPACE = Path(codex_ws) if codex_ws else Path.cwd()

    # Web 目录
    WEB_DIR = Path(__file__).parent / "web"

    # 网关端口
    CCMR_PORT = int(os.environ.get("DUO_CCMR_PORT", config.get("ccmr_port", "8080")))
    OPENCLAW_PORT = int(os.environ.get("DUO_OPENCLAW_PORT", config.get("openclaw_port", "18789")))

    return PROTOCOL_DIR, CLAUDE_WORKSPACE, CODEX_WORKSPACE, WEB_DIR, CCMR_PORT, OPENCLAW_PORT

PROTOCOL_DIR, CLAUDE_WORKSPACE, CODEX_WORKSPACE, WEB_DIR, CCMR_PORT, OPENCLAW_PORT = _load_config()

INBOX_FILE = PROTOCOL_DIR / "inbox" / "current_task.txt"
OUTBOX_CLAUDE = PROTOCOL_DIR / "outbox" / "claude.md"
OUTBOX_LOBSTER = PROTOCOL_DIR / "outbox" / "lobster.md"
OUTBOX_CODEX = PROTOCOL_DIR / "outbox" / "codex.md"
SESSION_FILE = PROTOCOL_DIR / "session.json"
CHAT_FILE = PROTOCOL_DIR / "chat.json"

AI_ORDER = ("claude", "lobster", "codex")
TERMINAL_STATUSES = ("done", "timeout", "error")
AI_LABELS = {
    "user": "天火大人",
    "claude": "Claude Code",
    "lobster": "龙虾 (OpenClaw)",
    "codex": "Codex",
    "system": "系统",
}
OUTBOX_FILES = {
    "claude": OUTBOX_CLAUDE,
    "lobster": OUTBOX_LOBSTER,
    "codex": OUTBOX_CODEX,
}


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

# 自动检测 Codex。Windows 后台进程优先使用 codex.cmd，避免误执行无扩展名 npm shim。
_codex_candidates = [
    str(Path.home() / "AppData" / "Roaming" / "npm" / "codex.cmd"),
    str(Path.home() / "AppData" / "Roaming" / "npm" / "codex.exe"),
    str(Path.home() / "AppData" / "Roaming" / "npm" / "codex.ps1"),
]
CODEX_CMD = _find_tool("codex.cmd", "DUO_CODEX_CMD", _codex_candidates)


def _codex_cmd_parts():
    path = Path(CODEX_CMD)
    if path.suffix.lower() == ".ps1":
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    return [str(path)]

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
        self._gateway_lock = threading.Lock()
        self._gateway_cache = None
        self._gateway_cache_at = 0
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
        self._normalize_session()
        self._save_session()

    def _new_session(self):
        return {
            "session_id": f"dh_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "phase": "idle",
            "round": 0,
            "claude_status": "idle",
            "lobster_status": "idle",
            "codex_status": "idle",
            "claude_model": "deepseek-v4-pro",
            "lobster_model": "deepseek/deepseek-v4-flash",  # DeepSeek 比 GPT 快且便宜
            "codex_model": "",
            "active_task_id": None,
            "created_at": datetime.now().isoformat(),
        }

    def _normalize_session(self):
        """兼容旧的双人 session，补齐三方状态字段。"""
        self.session.setdefault("phase", "idle")
        self.session.setdefault("round", 0)
        self.session.setdefault("active_task_id", None)
        self.session.setdefault("created_at", datetime.now().isoformat())
        self.session.setdefault("claude_model", "deepseek-v4-pro")
        self.session.setdefault("lobster_model", "deepseek/deepseek-v4-flash")
        self.session.setdefault("codex_model", "")
        for ai in AI_ORDER:
            self.session.setdefault(f"{ai}_status", "idle")

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
        now = time.time()
        if self._gateway_cache and now - self._gateway_cache_at < GATEWAY_CACHE_TTL:
            return self._gateway_cache

        if not self._gateway_lock.acquire(blocking=False):
            return self._gateway_cache or {"ccmr": False, "openclaw": False, "codex": False}

        try:
            now = time.time()
            if self._gateway_cache and now - self._gateway_cache_at < GATEWAY_CACHE_TTL:
                return self._gateway_cache

            self._gateway_cache = {
                "ccmr": self._port_open(CCMR_PORT),
                "openclaw": self._port_open(OPENCLAW_PORT),
                "codex": self._codex_available(),
            }
            self._gateway_cache_at = now
            return self._gateway_cache
        finally:
            self._gateway_lock.release()

    @staticmethod
    def _port_open(port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(GATEWAY_CHECK_TIMEOUT)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except Exception:
            return False

    @staticmethod
    def _codex_available():
        try:
            result = subprocess.run(
                _codex_cmd_parts() + ["--version"],
                capture_output=True,
                text=True,
                timeout=GATEWAY_CHECK_TIMEOUT,
                encoding="utf-8",
                errors="replace",
                env=_ENV,
            )
            return result.returncode == 0
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
            for m in recent:
                role_label = AI_LABELS.get(m["role"], m["role"])
                ctx += f"**{role_label}**: {m['content']}\n\n"

        header = (
            "# Duo Hub 协作任务\n\n"
            "你正在三AI协作中心工作，搭档是 Claude Code、OpenClaw「龙虾」和 Codex。"
            "天火大人通过 Duo Hub 同时与你们三个交互。\n\n"
            "工作规则：\n"
            "1. 分析任务需求，给出你的方案\n"
            "2. 标注你擅长的部分和需要对方配合的部分\n"
            "3. 如果是协商，请明确提出三方分工建议（格式：- XX负责：xxx）\n"
            "4. 回复使用中文，结构清晰\n\n"
            "---\n\n"
            "# 当前任务\n\n"
        )
        content = f"{header}{task_text}{ctx}"
        INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(INBOX_FILE, "w", encoding="utf-8") as f:
            f.write(content)

    def outbox_for(self, ai_name):
        if ai_name not in OUTBOX_FILES:
            raise ValueError(f"未知 AI: {ai_name}")
        return OUTBOX_FILES[ai_name]

    def read_outbox(self, ai_name):
        outbox = self.outbox_for(ai_name)
        if outbox.exists():
            try:
                with open(outbox, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                return None
        return None

    def get_outbox_mtime(self, ai_name):
        outbox = self.outbox_for(ai_name)
        if outbox.exists():
            try:
                return outbox.stat().st_mtime
            except Exception:
                return 0
        return 0

    def clear_outbox(self, ai_name):
        outbox = self.outbox_for(ai_name)
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
                    "你正在和 OpenClaw「龙虾」、Codex 协商三方分工。下面是上一轮回复。\n"
                    "请阅读后确认或提出一个明确的三方分工方案。\n"
                    "格式：\n- Claude负责：[具体任务]\n- 龙虾负责：[具体任务]\n- Codex负责：[具体任务]\n"
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
                    "你在三AI协作中心工作，搭档是 OpenClaw「龙虾」和 Codex。\n"
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

    def invoke_codex(self, task_text, model=None, mode="task"):
        """在后台线程中调用本机 Codex CLI。"""
        try:
            self.session["codex_status"] = "working"
            self.session["_codex_started"] = time.time()
            self._save_session()
            self.clear_outbox("codex")

            if mode == "negotiate":
                hub_prompt = (
                    "[Duo Hub 协商模式]\n"
                    "你是三方协作里的 Codex，同时也是临时协调员。请综合 Claude Code 和龙虾的意见，"
                    "提出责任清晰、不重叠、可执行的三方分工。\n"
                    "格式：\n- Claude负责：[具体任务]\n- 龙虾负责：[具体任务]\n- Codex负责：[具体任务]\n"
                    "如果对方已有合理反馈，优先吸收。回复使用中文。\n"
                )
            elif mode == "execute":
                hub_prompt = (
                    "[Duo Hub 执行模式]\n"
                    "分工已确认。只执行 Codex 负责的部分；需要改文件或运行命令就直接做。"
                    "不要泄露密钥、token、cookie 或 secrets 文件内容。完成后报告。回复使用中文。\n"
                )
            else:
                hub_prompt = (
                    "[Duo Hub 协作模式]\n"
                    "你在三AI协作中心工作，搭档是 Claude Code 和 OpenClaw「龙虾」。"
                    "分析任务需求，说明你适合承担的部分和需要对方配合的部分。回复使用中文。\n"
                )

            prompt = (
                f"{hub_prompt}\n\n"
                f"当前 Codex 工作区：{CODEX_WORKSPACE}\n\n"
                "---\n\n"
                f"{task_text}"
            )

            CODEX_WORKSPACE.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as tmp:
                last_message_path = Path(tmp.name)

            cmd = _codex_cmd_parts()
            cmd.extend(["--search", "-s", "danger-full-access", "-a", "never"])
            model_arg = model if model is not None else self.session.get("codex_model", "")
            if model_arg:
                cmd.extend(["-m", model_arg])
            cmd.extend([
                "exec",
                "-C",
                str(CODEX_WORKSPACE),
                "--skip-git-repo-check",
                "--color",
                "never",
                "--output-last-message",
                str(last_message_path),
                "-",
            ])

            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=AI_TIMEOUT,
                cwd=str(CODEX_WORKSPACE),
                encoding="utf-8",
                errors="replace",
                env=_ENV,
            )

            output = ""
            if last_message_path.exists():
                output = last_message_path.read_text(encoding="utf-8", errors="replace").strip()
            if not output:
                output = (result.stdout or "").strip()
            if not output and result.stderr:
                output = f"[Codex 输出为空]\nstderr: {result.stderr[:800]}"
            if result.returncode != 0:
                output = f"Codex 退出码 {result.returncode}\n\n{output}\n\nstderr:\n{(result.stderr or '')[:1200]}".strip()

            try:
                last_message_path.unlink(missing_ok=True)
            except Exception:
                pass

            with open(OUTBOX_CODEX, "w", encoding="utf-8") as f:
                f.write(output)

            self.session["codex_status"] = "done" if result.returncode == 0 else "error"
            self._save_session()

        except subprocess.TimeoutExpired:
            with open(OUTBOX_CODEX, "w", encoding="utf-8") as f:
                f.write(f"Codex 响应超时（超过 {AI_TIMEOUT} 秒）")
            self.session["codex_status"] = "timeout"
            self._save_session()
        except Exception as e:
            with open(OUTBOX_CODEX, "w", encoding="utf-8") as f:
                f.write(f"Codex 调用出错: {str(e)}")
            self.session["codex_status"] = "error"
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

    def is_done(self, ai):
        return self.session.get(f"{ai}_status") in TERMINAL_STATUSES

    def _all_done(self, agents=AI_ORDER):
        return all(self.is_done(ai) for ai in agents)

    def _collect_if_done(self, ai):
        if not self.is_done(ai):
            return
        if self.session.get(f"_{ai}_collected") == self.session["round"]:
            return
        text = self.read_outbox(ai)
        if text:
            self.add_message(ai, text)
            self.session[f"_{ai}_collected"] = self.session["round"]
            self._save_session()

    def _format_recent(self, n=20):
        recent = self.get_recent_messages(n)
        return "\n\n".join([f"[{AI_LABELS.get(m['role'], m['role'])}]: {m['content']}" for m in recent])

    @staticmethod
    def _parse_division_plan(text):
        """从 Codex 的 Markdown 分工提案中提取三方任务。"""
        if not text:
            return None
        plan = {ai: "" for ai in AI_ORDER}
        aliases = {
            "claude": ["Claude", "Claude Code", "克劳德"],
            "lobster": ["龙虾", "OpenClaw", "小八", "Lobster"],
            "codex": ["Codex"],
        }
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            stripped = line.strip().lstrip("-*0123456789.、 \t")
            for ai, names in aliases.items():
                if plan[ai]:
                    continue
                for name in names:
                    prefixes = [f"{name}负责", f"{name} 负责", f"{name}：", f"{name}:"]
                    if any(stripped.startswith(prefix) for prefix in prefixes):
                        content = stripped
                        for marker in ["负责：", "负责:", "：", ":"]:
                            if marker in content:
                                content = content.split(marker, 1)[1].strip()
                                break
                        extra = []
                        for follow in lines[idx + 1: idx + 8]:
                            f = follow.strip()
                            if not f:
                                if extra:
                                    break
                                continue
                            if any(token in f for token in ["Claude负责", "Claude 负责", "龙虾负责", "龙虾 负责", "Codex负责", "Codex 负责"]):
                                break
                            if f.startswith(("#", "---")):
                                break
                            extra.append(f)
                        plan[ai] = "\n".join([content] + extra).strip()
                        break
        return plan if any(plan.values()) else None

    def _store_division_from_latest_codex(self):
        for msg in reversed(self.chat.get("messages", [])):
            if msg.get("role") == "codex":
                plan = self._parse_division_plan(msg.get("content", ""))
                if plan:
                    self.session["_division_plan"] = plan
                    self.session["_division_text"] = msg.get("content", "")
                    self.session["_division_source_msg"] = msg.get("id")
                    self._save_session()
                return plan
        return None

    @staticmethod
    def _agent_agreement_state(text):
        if not text:
            return "silent"
        lowered = text.lower()
        negative = [
            "不同意", "不行", "不能", "做不到", "不可行", "需要调整", "必须调整",
            "建议调整", "有问题", "不合理", "不建议", "不适合", "无法", "缺少",
            "不可以", "不确认", "反对", "担心", "但是", "但需要", "不过需要",
            "需要先确认", "请确认", "选哪个", "是否", "?", "？",
        ]
        positive = ["同意分工", "同意", "确认", "没问题", "没有问题", "可以", "ok", "好的", "就这样"]
        for kw in [n.lower() for n in negative]:
            if kw == "有问题" and ("没有问题" in lowered or "没问题" in lowered):
                continue
            if kw in lowered:
                return "disagree"
        if any(kw in lowered for kw in positive):
            return "agree"
        return "unclear"

    def _start_agent(self, ai, task_text, mode="task"):
        model = self.session.get(f"{ai}_model", "")
        target = {
            "claude": self.invoke_claude,
            "lobster": self.invoke_lobster,
            "codex": self.invoke_codex,
        }[ai]
        threading.Thread(target=target, args=(task_text, model, mode), daemon=True).start()

    def process_task(self, task_text, needs_division=False):
        """提交任务：同时启动三个 AI。"""
        if self.session["phase"] in ("ai_working", "negotiating", "pending_confirmation", "awaiting_feedback", "executing"):
            return False, "已有任务正在处理中"

        self.session["round"] += 1
        self.session["phase"] = "ai_working"
        self.session["active_task_id"] = f"task_{self.session['round']:03d}"
        self.session["_needs_division"] = needs_division
        for ai in AI_ORDER:
            self.session[f"{ai}_status"] = "working"
            self.session[f"_{ai}_collected"] = 0
        self._save_session()

        self.write_inbox(task_text)
        self.add_message("user", task_text)

        for ai in AI_ORDER:
            self._start_agent(ai, task_text, "task")

        return True, self.session["active_task_id"]

    def check_and_collect_results(self):
        """检查三个 AI 是否完成，收集结果，自动推进阶段。"""
        phase = self.session["phase"]

        now = time.time()
        for ai in AI_ORDER:
            if self.session.get(f"{ai}_status") == "working":
                started = self.session.get(f"_{ai}_started", 0)
                if started and now - started > AI_TIMEOUT + 10:
                    self.session[f"{ai}_status"] = "timeout"
                    with open(self.outbox_for(ai), "w", encoding="utf-8") as f:
                        f.write(f"{AI_LABELS[ai]} 处理超时（超过 {AI_TIMEOUT} 秒无响应）")
                    self._save_session()

        if phase == "ai_working":
            for ai in AI_ORDER:
                self._collect_if_done(ai)

            if self._all_done():
                if self.session.get("_needs_division"):
                    self._auto_negotiate()
                else:
                    self.session["phase"] = "awaiting_user"
                    self._save_session()

        elif phase == "negotiating":
            stage = self.session.get("_negotiate_stage", "")

            if stage in ("codex_proposes", "codex_adjusts"):
                self._collect_if_done("codex")
                if self.is_done("codex") and self.session.get("_codex_collected") == self.session["round"]:
                    self._store_division_from_latest_codex()
                    self._negotiate_peers_respond()

            elif stage == "peers_confirm":
                for ai in ("claude", "lobster"):
                    self._collect_if_done(ai)

                if self._all_done(("claude", "lobster")):
                    peer_states = {
                        "claude": self._agent_agreement_state(self.read_outbox("claude") or ""),
                        "lobster": self._agent_agreement_state(self.read_outbox("lobster") or ""),
                    }
                    self.session["_peer_feedback"] = {
                        "claude": self.read_outbox("claude") or "",
                        "lobster": self.read_outbox("lobster") or "",
                        "states": peer_states,
                    }
                    peers_agreed = all(state == "agree" for state in peer_states.values())
                    neg_rounds = self.session.get("_neg_rounds", 0) + 1
                    self.session["_neg_rounds"] = neg_rounds

                    if peers_agreed:
                        self.session["phase"] = "pending_confirmation"
                        self.session["_division_status"] = "agreed"
                        msg = "✅ 三方已一致同意分工。请确认执行，或输入修改意见继续调整。"
                        self.add_message("system", msg)
                        self._save_session()
                    elif neg_rounds >= 3:
                        self.session["phase"] = "awaiting_feedback"
                        self.session["_division_status"] = "needs_user"
                        self.add_message(
                            "system",
                            "⚠️ 三方未达成一致，已暂停自动协商。请补充你的意见、继续协商、强制确认当前方案，或取消分工。"
                        )
                        self._save_session()
                    else:
                        self._negotiate_codex_adjust()

        elif phase == "executing":
            for ai in AI_ORDER:
                self._collect_if_done(ai)

            if self._all_done():
                self.session["phase"] = "done"
                self.add_message("system", "🎉 三方执行完毕！请在面板中查看各自成果。")
                self._save_session()

    def _auto_negotiate(self, user_feedback=""):
        """Codex 先汇总三方初步意见并提出三方分工。"""
        context_str = self._format_recent(20)
        feedback_block = f"\n\n## 天火大人的补充意见\n\n{user_feedback}\n" if user_feedback else ""

        self.session["round"] += 1
        self.session["phase"] = "negotiating"
        self.session["_negotiate_round"] = self.session["round"]
        self.session["_negotiate_stage"] = "codex_proposes"
        self.session["_neg_rounds"] = 0
        for ai in AI_ORDER:
            self.session[f"{ai}_status"] = "idle"
            self.session[f"_{ai}_collected"] = 0
        self.session["codex_status"] = "working"
        self._save_session()

        self.add_message("system", "🤝 Codex 正在汇总三方意见，准备提出三方分工…")

        prompt = (
            "## 协商分工 - Codex 汇总提案\n\n"
            "请阅读 Claude、龙虾和 Codex 的初步回复，以及天火大人的补充意见，提出一个明确的三方分工。\n"
            "必须包含：\n"
            "- Claude负责：[具体、可执行]\n"
            "- 龙虾负责：[具体、可执行]\n"
            "- Codex负责：[具体、可执行]\n"
            "规则：责任边界清晰，不重复安排同一件事；如果某方能力明显不适合，就把它安排到更适合的支持/审查/资料任务。\n"
            "回复使用中文。\n\n"
            f"{feedback_block}\n---\n{context_str}"
        )
        self.write_inbox(prompt)
        self._start_agent("codex", prompt, "negotiate")

    def _negotiate_peers_respond(self):
        """Claude 和龙虾并行确认 Codex 的三方分工提案。"""
        context_str = self._format_recent(20)
        self.session["_negotiate_stage"] = "peers_confirm"
        for ai in ("claude", "lobster"):
            self.session[f"{ai}_status"] = "working"
            self.session[f"_{ai}_collected"] = 0
        self._save_session()

        self.add_message("system", "🤝 Claude 和龙虾正在确认 Codex 的三方分工提案…")

        prompt = (
            "## 协商分工 - 确认或调整\n\n"
            "Codex 已经提出三方分工方案（见上文）。请只从你的能力边界和执行可行性出发确认或调整：\n"
            "- 同意就说「同意分工」，并列出你要执行的任务\n"
            "- 不同意就说明哪一项不可行，并给出替代分工\n"
            "回复使用中文。\n\n"
            f"---\n{context_str}"
        )
        self.write_inbox(prompt)
        self._start_agent("claude", prompt, "negotiate")
        self._start_agent("lobster", prompt, "negotiate")

    def _negotiate_codex_adjust(self):
        """Claude 或龙虾不同意时，Codex 再整合调整。"""
        context_str = self._format_recent(25)

        self.session["round"] += 1
        self.session["_negotiate_round"] = self.session["round"]
        self.session["_negotiate_stage"] = "codex_adjusts"
        for ai in AI_ORDER:
            self.session[f"{ai}_status"] = "idle"
            self.session[f"_{ai}_collected"] = 0
        self.session["codex_status"] = "working"
        self._save_session()

        self.add_message("system", "🤝 Claude 或龙虾提出调整意见，Codex 正在重新整合分工…")

        prompt = (
            "## 协商 - Codex 调整方案\n\n"
            "Claude 或龙虾对上轮三方分工提出了不同意见。请吸收合理反馈，重新给出三方分工。\n"
            "格式：\n- Claude负责：[调整后的任务]\n- 龙虾负责：[调整后的任务]\n- Codex负责：[调整后的任务]\n"
            "目标是可执行，不追求平均分配。回复使用中文。\n\n"
            f"---\n{context_str}"
        )
        self.write_inbox(prompt)
        self._start_agent("codex", prompt, "negotiate")

    def negotiate(self, user_feedback=""):
        """手动触发重新协商。"""
        if self.session["phase"] not in ("awaiting_user", "pending_confirmation", "awaiting_feedback", "done"):
            return False, "当前阶段不能发起协商"

        if user_feedback:
            self.add_message("user", f"【协商补充意见】{user_feedback}")
        self._auto_negotiate(user_feedback=user_feedback)
        return True, "ok"

    def cancel_division(self, user_note=""):
        """取消当前分工确认，回到可继续输入状态。"""
        if self.session["phase"] not in ("pending_confirmation", "awaiting_feedback"):
            return False, "当前阶段不能取消分工"
        if user_note:
            self.add_message("user", f"【取消分工说明】{user_note}")
        self.session["phase"] = "awaiting_user"
        self.session["_division_status"] = "cancelled"
        self.add_message("system", "↩ 已取消当前分工确认，可继续输入新需求或补充说明。")
        self._save_session()
        return True, "ok"

    def confirm_plan(self):
        """用户确认分工方案 → 三方分别执行。"""
        if self.session["phase"] not in ("pending_confirmation", "awaiting_feedback"):
            return False, "没有待确认的分工方案"

        self.session["round"] += 1
        self.session["phase"] = "executing"
        self.session["_exec_round"] = self.session["round"]
        for ai in AI_ORDER:
            self.session[f"{ai}_status"] = "working"
            self.session[f"_{ai}_collected"] = 0
        if self.session.get("_division_status") == "needs_user":
            self.add_message("system", "✅ 天火大人已强制确认当前分工！三方开始执行各自任务…")
        else:
            self.add_message("system", "✅ 天火大人已确认分工！三方开始执行各自任务…")
        self._save_session()

        all_context = self._format_recent(30)
        division_plan = self.session.get("_division_plan") or {}
        shared_task = (
            "## 执行阶段 - 三方共享上下文\n\n"
            "分工方案已经天火大人确认。每个 AI 只执行明确标注给自己的部分：\n"
            "- Claude 只执行「Claude负责」部分\n"
            "- 龙虾只执行「龙虾负责」部分\n"
            "- Codex 只执行「Codex负责」部分\n"
            "不要重复执行别人的任务。完成后报告你具体做了什么。\n\n"
            f"---\n{all_context}"
        )
        self.write_inbox(shared_task)

        for ai in AI_ORDER:
            assigned = division_plan.get(ai, "")
            agent_task = (
                f"## 执行阶段 - {AI_LABELS[ai]}\n\n"
                f"分工已确认。你是 {AI_LABELS[ai]}，只执行下面明确分配给你的部分。\n\n"
                f"## 你负责的任务\n\n{assigned or '未解析到结构化任务，请只根据最近分工中明确标注给你的部分执行。'}\n\n"
                "直接动手执行，完成后报告。不要泄露密钥或私人凭据。\n\n"
                f"---\n{all_context}"
            )
            self._start_agent(ai, agent_task, "execute")

        return True, "ok"

    def set_model(self, ai, model):
        """切换 AI 模型。"""
        if ai not in AI_ORDER:
            return False
        self.session[f"{ai}_model"] = model or ""
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

        # 提取结构化协商结果（如果有）
        division = self.session.get("_division_plan")
        if division and not any((division.get(ai) or "").strip() for ai in AI_ORDER):
            division = None

        agents = [
            {
                "id": ai,
                "label": AI_LABELS[ai],
                "status": self.session.get(f"{ai}_status", "idle"),
                "model": self.session.get(f"{ai}_model", ""),
            }
            for ai in AI_ORDER
        ]

        return {
            "version": APP_VERSION,
            "session_id": self.session["session_id"],
            "phase": self.session["phase"],
            "round": self.session["round"],
            "claude_status": self.session["claude_status"],
            "lobster_status": self.session["lobster_status"],
            "codex_status": self.session.get("codex_status", "idle"),
            "claude_model": self.session.get("claude_model", "deepseek-v4-pro"),
            "lobster_model": self.session.get("lobster_model", "deepseek/deepseek-v4-pro"),
            "codex_model": self.session.get("codex_model", ""),
            "active_task_id": self.session.get("active_task_id"),
            "gateways": self.check_gateways(),
            "agents": agents,
            "messages": recent,
            "total_messages": len(messages),
            "division": division,
            "division_status": self.session.get("_division_status", ""),
            "peer_feedback": self.session.get("_peer_feedback", {}),
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
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                data = {}
            ok, msg = hub.negotiate(user_feedback=(data.get("feedback", "") or "").strip())
            if ok:
                self._serve_json({"ok": True})
            else:
                self._serve_json({"error": msg}, 409)

        elif path == "/api/cancel-division":
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                data = {}
            ok, msg = hub.cancel_division(user_note=(data.get("note", "") or "").strip())
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
            if ai not in AI_ORDER or model is None:
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
    print("  ⚡ Duo Hub — 天火大人的三AI协作中心")
    print("=" * 56)
    print()
    print(f"  协议目录: {PROTOCOL_DIR}")
    print(f"  前端文件: {WEB_DIR}")
    print(f"  Claude 工作区: {CLAUDE_WORKSPACE}")
    print(f"  Codex 工作区: {CODEX_WORKSPACE}")
    print()

    # 检查网关
    print("[检测] 网关状态...")
    gws = hub.check_gateways()
    ccmr_icon = "[OK]" if gws["ccmr"] else "[XX]"
    oc_icon = "[OK]" if gws["openclaw"] else "[XX]"
    codex_icon = "[OK]" if gws["codex"] else "[XX]"
    print(f"  {ccmr_icon} ccmr 网关 (端口 {CCMR_PORT})")
    print(f"  {oc_icon} OpenClaw 网关 (端口 {OPENCLAW_PORT})")
    print(f"  {codex_icon} Codex CLI ({CODEX_CMD})")
    print()

    if not gws["ccmr"] or not gws["openclaw"] or not gws["codex"]:
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
