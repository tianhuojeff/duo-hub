#!/usr/bin/env python3
"""Duo Hub — Codex 主管与可插拔 Agent 协作中心。"""

import hashlib
import hmac
import http.server
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from datetime import datetime
from http.cookies import SimpleCookie
from pathlib import Path

from duohub.agents import (
    AgentDescriptor,
    AgentRegistry,
    AgentRequest,
    AntigravityCliAdapter,
    GeminiCliAdapter,
)

# ============================================================
# 配置 — 从 config.json 读取，支持环境变量覆盖
# ============================================================
HOST = "127.0.0.1"
PORT = int(os.environ.get("DUO_PORT", "5199"))
AI_TIMEOUT = int(os.environ.get("DUO_AI_TIMEOUT", "300"))
FAST_AI_TIMEOUT = int(os.environ.get("DUO_FAST_AI_TIMEOUT", "90"))
APP_VERSION = "0.6.1"
GATEWAY_CACHE_TTL = int(os.environ.get("DUO_GATEWAY_CACHE_TTL", "30"))
GATEWAY_CHECK_TIMEOUT = float(os.environ.get("DUO_GATEWAY_CHECK_TIMEOUT", "1"))
REQUEST_BODY_TIMEOUT = float(os.environ.get("DUO_REQUEST_BODY_TIMEOUT", "5"))
AGENT_CONTEXT_MESSAGES = int(os.environ.get("DUO_AGENT_CONTEXT_MESSAGES", "4"))
AGENT_CONTEXT_CHARS = int(os.environ.get("DUO_AGENT_CONTEXT_CHARS", "1000"))
LOCAL_NO_PROXY = ("127.0.0.1", "localhost", "::1")


def _merge_csv_env(existing, additions):
    parts = []
    seen = set()
    for item in (existing or "").replace(";", ",").split(","):
        value = item.strip()
        if value and value.lower() not in seen:
            parts.append(value)
            seen.add(value.lower())
    for value in additions:
        if value.lower() not in seen:
            parts.append(value)
            seen.add(value.lower())
    return ",".join(parts)


def _ensure_local_no_proxy(env):
    merged = _merge_csv_env(env.get("NO_PROXY") or env.get("no_proxy") or "", LOCAL_NO_PROXY)
    env["NO_PROXY"] = merged
    env["no_proxy"] = merged


_ensure_local_no_proxy(os.environ)

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

    # Claude 工作区（停用兼容配置，未来可重新注册 Adapter）
    claude_ws = os.environ.get("DUO_CLAUDE_WORKSPACE", config.get("claude_workspace", ""))
    CLAUDE_WORKSPACE = Path(claude_ws) if claude_ws else Path.cwd()

    # Codex 工作区
    codex_ws = os.environ.get("DUO_CODEX_WORKSPACE", config.get("codex_workspace", ""))
    CODEX_WORKSPACE = Path(codex_ws) if codex_ws else Path.cwd()

    # 当前 Gemini 席位工作区。默认跟随 Codex 工作区，不继承旧 Claude 路径。
    gemini_ws = os.environ.get("DUO_GEMINI_WORKSPACE", config.get("gemini_workspace", ""))
    GEMINI_WORKSPACE = Path(gemini_ws) if gemini_ws else CODEX_WORKSPACE

    # Web 目录
    WEB_DIR = Path(__file__).parent / "web"

    # 网关端口
    CCMR_PORT = int(os.environ.get("DUO_CCMR_PORT", config.get("ccmr_port", "18080")))
    OPENCLAW_PORT = int(os.environ.get("DUO_OPENCLAW_PORT", config.get("openclaw_port", "18789")))

    return (
        PROTOCOL_DIR,
        CLAUDE_WORKSPACE,
        CODEX_WORKSPACE,
        GEMINI_WORKSPACE,
        WEB_DIR,
        CCMR_PORT,
        OPENCLAW_PORT,
        config,
    )

(
    PROTOCOL_DIR,
    CLAUDE_WORKSPACE,
    CODEX_WORKSPACE,
    GEMINI_WORKSPACE,
    WEB_DIR,
    CCMR_PORT,
    OPENCLAW_PORT,
    CONFIG,
) = _load_config()

INBOX_FILE = PROTOCOL_DIR / "inbox" / "current_task.txt"
OUTBOX_CLAUDE = PROTOCOL_DIR / "outbox" / "claude.md"
OUTBOX_LOBSTER = PROTOCOL_DIR / "outbox" / "lobster.md"
OUTBOX_CODEX = PROTOCOL_DIR / "outbox" / "codex.md"
OUTBOX_GEMINI = PROTOCOL_DIR / "outbox" / "gemini.md"
SESSION_FILE = PROTOCOL_DIR / "session.json"
CHAT_FILE = PROTOCOL_DIR / "chat.json"
EVENTS_FILE = PROTOCOL_DIR / "events.jsonl"
API_TOKEN_FILE = PROTOCOL_DIR / "api_token"
LOOP_STATE_FILE = PROTOCOL_DIR / "loop_state.json"
LOOP_REPORT_FILE = PROTOCOL_DIR / "loop_report.md"

DEFAULT_AGENT_SETTINGS = (
    {
        "id": "gemini",
        "enabled": True,
        "invoke_by_default": True,
        "provider": "antigravity-cli",
        "model": "gemini-4-hydrogen-medium",
    },
)
AGENT_SETTINGS = tuple(CONFIG.get("agents") or DEFAULT_AGENT_SETTINGS)
AI_ORDER = tuple(
    str(item.get("id", "")).strip()
    for item in AGENT_SETTINGS
    if item.get("enabled", True) and item.get("invoke_by_default", True) and item.get("id")
)
SUPERVISOR_TARGETS = tuple(
    str(item.get("id", "")).strip()
    for item in AGENT_SETTINGS
    if item.get("enabled", True) and item.get("id")
)
TERMINAL_STATUSES = ("done", "timeout", "error")
AI_LABELS = {
    "user": "用户",
    "gemini": "Gemini",
    "claude": "Claude Code",
    "lobster": "龙虾 (OpenClaw)",
    "codex": "Codex",
    "system": "系统",
}
OUTBOX_FILES = {
    "gemini": OUTBOX_GEMINI,
    "claude": OUTBOX_CLAUDE,
    "lobster": OUTBOX_LOBSTER,
    "codex": OUTBOX_CODEX,
}

DEFAULT_LOBSTER_MODEL = "deepseek/deepseek-v4-flash"
LOBSTER_MODEL_ALIASES = {
    "": DEFAULT_LOBSTER_MODEL,
    "dmxapi/gpt-4.1-mini": DEFAULT_LOBSTER_MODEL,
    "dmxapi/gpt-4.1-mini-2025-04-14": DEFAULT_LOBSTER_MODEL,
    "gpt-4.1-mini": DEFAULT_LOBSTER_MODEL,
    "gpt-5.5": DEFAULT_LOBSTER_MODEL,
}
LOBSTER_FAST_CCMR_MODELS = {
    "ikuncode/claude-sonnet-4-6": "ikun-gpt-gpt-5-5",
    "ikuncode/claude-opus-4-8": "ikun-gpt-gpt-5-5",
    "ikuncode/claude-opus-4-7": "ikun-gpt-gpt-5-5",
    "ikuncode/claude-opus-4-6": "ikun-gpt-gpt-5-5",
    "ikuncode/claude-haiku-4-5-20251001": "ikun-gpt-gpt-5-5",
}
DEFAULT_CLAUDE_MODEL = "ikun-claude-claude-sonnet-4-6"
CLAUDE_REVIEW_FALLBACK_MODELS = (
    "ikun-gpt-gpt-5-5",
    "ikun-gpt-gpt-5-4",
)
CLAUDE_MODEL_ALIASES = {
    "": DEFAULT_CLAUDE_MODEL,
    "deepseek-v4-pro": "ikun-gpt-gpt-5-5",
    "deepseek-v4-flash": "ikun-gpt-gpt-5-5",
    "kimi-k2.6": "ikun-gpt-gpt-5-5",
    "minimax-m3": "ikun-gpt-gpt-5-5",
    "qwen3.5-plus": "ikun-gpt-gpt-5-5",
    "glm-5.1": "ikun-gpt-gpt-5-5",
    "step-3.7-flash": "ikun-gpt-gpt-5-5",
    "claude": DEFAULT_CLAUDE_MODEL,
    "sonnet": DEFAULT_CLAUDE_MODEL,
    "sonnet-4-6": DEFAULT_CLAUDE_MODEL,
    "claude-sonnet-4-6": DEFAULT_CLAUDE_MODEL,
    "ikuncode-claude-sonnet-4-6": DEFAULT_CLAUDE_MODEL,
    "ikun-claude-claude-sonnet-4-6": DEFAULT_CLAUDE_MODEL,
    "ikun-claude-claude-opus-4-8": DEFAULT_CLAUDE_MODEL,
    "ikun-claude-claude-opus-4-7": DEFAULT_CLAUDE_MODEL,
    "ikun-claude-claude-opus-4-6": DEFAULT_CLAUDE_MODEL,
    "ikun-claude-claude-opus-4-5": DEFAULT_CLAUDE_MODEL,
    "ikun-claude-claude-haiku-4-5": DEFAULT_CLAUDE_MODEL,
    "ikuncode-claude-opus-4-8": DEFAULT_CLAUDE_MODEL,
    "ikuncode-claude-opus-4-7": DEFAULT_CLAUDE_MODEL,
    "ikuncode-claude-opus-4-6": DEFAULT_CLAUDE_MODEL,
    "ikuncode-claude-opus-4-5-20251101": DEFAULT_CLAUDE_MODEL,
    "ikuncode-claude-haiku-4-5-20251001": DEFAULT_CLAUDE_MODEL,
    "ikuncode-claude-sonnet-4-5-20250929": DEFAULT_CLAUDE_MODEL,
    "ikuncode-gpt-5.5": "ikun-gpt-gpt-5-5",
    "gpt-5.5": "ikun-gpt-gpt-5-5",
    "ikuncode-gpt-5.4": "ikun-gpt-gpt-5-4",
    "gpt-5.4": "ikun-gpt-gpt-5-4",
}


def _find_tool(name, env_var, known_paths):
    """查找可执行文件：环境变量 > PATH 搜索 > 已知路径"""
    env_val = os.environ.get(env_var, "")
    if env_val and Path(env_val).exists():
        return env_val
    path_match = shutil.which(name)
    if path_match:
        return path_match
    for p in known_paths:
        if Path(p).exists():
            return p
    return name


# 自动检测 ccmr
_ccmr_candidates = [
    str(Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "claude-code-model-router" / "dist" / "cli.js"),
]
for _base in (
    Path.home() / "AppData" / "Local" / "pnpm" / "global",
    Path.home() / "AppData" / "Local" / "pnpm" / "global" / "5",
):
    _ccmr_candidates.append(str(_base / "node_modules" / "claude-code-model-router" / "dist" / "cli.js"))

NODE_CMD = "node"
CCMR_JS = _find_tool("ccmr_js", "DUO_CCMR_JS", _ccmr_candidates)

# 自动检测 Claude CLI。Windows 后台进程优先使用 claude.cmd，避免 npm shim 解析问题。
_claude_candidates = [
    str(Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd"),
    str(Path.home() / "AppData" / "Roaming" / "npm" / "claude.exe"),
    str(Path.home() / "AppData" / "Roaming" / "npm" / "claude.ps1"),
]
CLAUDE_CMD = _find_tool("claude.cmd", "DUO_CLAUDE_CMD", _claude_candidates)

# 自动检测 openclaw
_oc_candidates = [
    str(Path.home() / "AppData" / "Local" / "pnpm" / "openclaw.cmd"),
]
for _base in (
    Path.home() / "AppData" / "Local" / "pnpm" / "global",
    Path.home() / "AppData" / "Local" / "pnpm" / "global" / "5",
):
    _oc_candidates.append(str(_base / "node_modules" / "openclaw" / "openclaw.mjs"))
OPENCLAW_CMD = _find_tool("openclaw", "DUO_OPENCLAW_CMD", _oc_candidates)

# 自动检测 Codex。Windows 后台进程优先使用 codex.cmd，避免误执行无扩展名 npm shim。
_codex_candidates = [
    str(Path.home() / "AppData" / "Roaming" / "npm" / "codex.cmd"),
    str(Path.home() / "AppData" / "Roaming" / "npm" / "codex.exe"),
    str(Path.home() / "AppData" / "Roaming" / "npm" / "codex.ps1"),
]
CODEX_CMD = _find_tool("codex.cmd", "DUO_CODEX_CMD", _codex_candidates)

# Gemini 席位可以选择 Google Gemini CLI 或 Antigravity CLI provider。
_gemini_candidates = [
    str(Path.home() / "AppData" / "Roaming" / "npm" / "gemini.cmd"),
    str(Path.home() / "AppData" / "Roaming" / "npm" / "gemini.exe"),
    str(Path.home() / "AppData" / "Roaming" / "npm" / "gemini.ps1"),
]
GEMINI_CMD = _find_tool("gemini.cmd", "DUO_GEMINI_CMD", _gemini_candidates)

_antigravity_candidates = [
    str(Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.exe"),
]
ANTIGRAVITY_CMD = _find_tool("agy.exe", "DUO_ANTIGRAVITY_CMD", _antigravity_candidates)


def _cmd_parts(cmd):
    path = Path(cmd)
    if path.suffix.lower() == ".ps1":
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    if path.suffix.lower() in (".cmd", ".bat"):
        return ["cmd.exe", "/c", str(path)]
    return [str(path)]


def _claude_cmd_parts():
    return _cmd_parts(CLAUDE_CMD)


def _codex_cmd_parts():
    path = Path(CODEX_CMD)
    if path.suffix.lower() == ".ps1":
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    return [str(path)]


def _openclaw_cmd_parts():
    path = Path(OPENCLAW_CMD)
    if path.suffix.lower() == ".ps1":
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    if path.suffix.lower() in (".cmd", ".bat"):
        return ["cmd.exe", "/c", str(path)]
    if path.suffix.lower() == ".mjs":
        return [NODE_CMD, str(path)]
    return [str(path)]

# 构建子进程环境
_ENV = os.environ.copy()
_ensure_local_no_proxy(_ENV)
_npm_bin = str(Path.home() / "AppData" / "Roaming" / "npm")
_pnpm_bin = str(Path.home() / "AppData" / "Local" / "pnpm")
_agy_bin = str(Path.home() / "AppData" / "Local" / "agy" / "bin")
_ENV["PATH"] = os.pathsep.join([_npm_bin, _pnpm_bin, _agy_bin, _ENV.get("PATH", "")])

# OpenClaw NODE_PATH（自动检测）
_oc_node_paths = []
for _base in (
    Path.home() / "AppData" / "Local" / "pnpm" / "global",
    Path.home() / "AppData" / "Local" / "pnpm" / "global" / "5",
):
    _m = _base / "node_modules" / "openclaw" / "node_modules"
    if _m.exists():
        _oc_node_paths.append(str(_m))
        _oc_node_paths.append(str(_m.parent))
if _oc_node_paths:
    _oc_path = os.pathsep.join(_oc_node_paths)
    _ENV["NODE_PATH"] = _oc_path + os.pathsep + _ENV.get("NODE_PATH", "")


def _build_agent_registry():
    """Build enabled logical seats from config without hard-coding orchestration loops."""
    registry = AgentRegistry()
    for settings in AGENT_SETTINGS:
        if not settings.get("enabled", True):
            continue
        agent_id = str(settings.get("id", "")).strip()
        if agent_id != "gemini":
            # Future adapters can be registered here without changing orchestration code.
            continue
        provider = str(settings.get("provider", "antigravity-cli")).strip().lower()
        if provider == "gemini-cli":
            adapter_cls = GeminiCliAdapter
            command = GEMINI_CMD
        elif provider == "antigravity-cli":
            adapter_cls = AntigravityCliAdapter
            command = ANTIGRAVITY_CMD
        else:
            raise ValueError(f"unsupported Gemini provider: {provider}")
        default_model = str(settings.get("model") or adapter_cls.MODELS[0].id)
        descriptor = AgentDescriptor(
            id="gemini",
            display_name="Gemini",
            provider=provider,
            default_model=default_model,
            models=adapter_cls.MODELS,
            capabilities=("analysis", "research", "code", "structured-output"),
            enabled=True,
            invoke_by_default=bool(settings.get("invoke_by_default", True)),
            gateway_key="gemini",
            icon="Gm",
            color="#8b5cf6",
        )
        registry.register(adapter_cls(
            descriptor=descriptor,
            command=command,
            workspace=GEMINI_WORKSPACE,
            env=_ENV,
        ))
    return registry


def _claude_gateway_env(model_id):
    env = _ENV.copy()
    gateway_url = f"http://127.0.0.1:{CCMR_PORT}"
    env.setdefault("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude-gateway"))
    env["ANTHROPIC_BASE_URL"] = gateway_url
    env["ANTHROPIC_AUTH_TOKEN"] = env.get("CCMR_AUTH_TOKEN", "ccmr-local-gateway")
    env["ANTHROPIC_MODEL"] = model_id
    env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model_id
    env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model_id
    env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = model_id
    env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] = "1"
    env.setdefault("NODE_NO_WARNINGS", "1")
    env.setdefault("LANG", "zh_CN.UTF-8")
    env.setdefault("LC_ALL", "zh_CN.UTF-8")
    return env


def _truncate_text(text, max_chars=AGENT_CONTEXT_CHARS):
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[已截断]"


def _extract_anthropic_text(data):
    for key in ("text", "reply", "output_text"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] or {}
        if isinstance(first, dict):
            message = first.get("message") or {}
            content = message.get("content") if isinstance(message, dict) else ""
            if isinstance(content, str) and content.strip():
                return content.strip()
    content = data.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts).strip()
    return ""


def _post_ccmr_message(prompt, model_id, max_tokens=1200, timeout=FAST_AI_TIMEOUT):
    payload = {
        "model": model_id,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{CCMR_PORT}/v1/messages",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_ENV.get('CCMR_AUTH_TOKEN', 'ccmr-local-gateway')}",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ccmr HTTP {e.code}: {body[:800]}") from e
    parsed = json.loads(raw)
    text = _extract_anthropic_text(parsed)
    if text:
        return text
    return raw.strip()


def _is_ccmr_channel_unavailable(error):
    text = str(error)
    return (
        "No available channel for model" in text
        or "无可用" in text
        or "no available channel" in text.lower()
    )


def _post_claude_review_message(prompt, model_id):
    try:
        return _post_ccmr_message(prompt, model_id)
    except Exception as e:
        if not _is_ccmr_channel_unavailable(e):
            raise
        last_error = e
        for fallback_model in CLAUDE_REVIEW_FALLBACK_MODELS:
            if fallback_model == model_id:
                continue
            try:
                fallback_output = _post_ccmr_message(prompt, fallback_model)
                return (
                    "[首选模型通道暂不可用，已临时切到 Duo Hub 配置的备用模型；"
                    "本回包保留实际底层模型来源，供调用方审计。]\n\n"
                    f"底层签字模型：{fallback_model}\n"
                    f"原 IKun Claude 通道错误：{str(e)[:500]}\n\n"
                    f"{fallback_output}"
                )
            except Exception as fallback_error:
                last_error = fallback_error
        raise last_error


def _lobster_fast_ccmr_model(model_id):
    return LOBSTER_FAST_CCMR_MODELS.get((model_id or "").strip())


def _is_heartbeat_task(task_text):
    text = (task_text or "").strip().lower()
    compact = "".join(text.split())
    heartbeat = {
        "来", "说话", "在吗", "ping", "pong", "hello", "hi",
        "检查连接", "连接检查", "检查各自连接", "现在检查各自连接",
        "测试连接", "连接测试", "谁能说话",
    }
    return compact in heartbeat

# ============================================================
# DuoHub — 协议和状态管理
# ============================================================
class DuoHub:
    def __init__(self):
        self.lock = threading.Lock()
        self._event_lock = threading.Lock()
        self._gateway_lock = threading.Lock()
        self._collect_lock = threading.Lock()
        self._gateway_cache = None
        self._agent_health_cache = {}
        self._gateway_cache_at = 0
        self.agent_registry = _build_agent_registry()
        self._ensure_dirs()
        self.api_token = self._init_api_token()
        self._init_session()
        self._init_chat()

    def _ensure_dirs(self):
        PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
        (PROTOCOL_DIR / "inbox").mkdir(exist_ok=True)
        (PROTOCOL_DIR / "outbox").mkdir(exist_ok=True)

    def _init_api_token(self):
        configured = os.environ.get("DUO_API_TOKEN", "").strip()
        if configured:
            return configured
        if API_TOKEN_FILE.exists():
            try:
                existing = API_TOKEN_FILE.read_text(encoding="utf-8").strip()
                if existing:
                    return existing
            except OSError:
                pass
        token = secrets.token_urlsafe(32)
        API_TOKEN_FILE.write_text(token, encoding="utf-8")
        try:
            API_TOKEN_FILE.chmod(0o600)
        except OSError:
            pass
        return token

    # ---- Loop state ----
    def _default_loop_state(self):
        return {
            "schema_version": 1,
            "status": "not_scanned",
            "updated_at": None,
            "source": "",
            "summary": "尚未扫描",
            "findings": [],
            "next_actions": ["点击 Loop 扫描，先做一次本地状态检查。"],
            "report_path": str(LOOP_REPORT_FILE),
        }

    def get_loop_state(self):
        if not LOOP_STATE_FILE.exists():
            return self._default_loop_state()
        try:
            with open(LOOP_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            default = self._default_loop_state()
            default.update(state if isinstance(state, dict) else {})
            return default
        except Exception as e:
            state = self._default_loop_state()
            state["status"] = "error"
            state["summary"] = f"Loop 状态读取失败: {e}"
            state["findings"] = [{
                "severity": "action",
                "area": "loop_state",
                "message": "loop_state.json 读取失败",
                "next": "检查协议目录权限或删除损坏的 loop_state.json 后重新扫描。",
            }]
            return state

    def _outbox_snapshot(self):
        snapshot = {}
        for ai in AI_ORDER:
            path = self.outbox_for(ai)
            item = {"path": str(path), "exists": path.exists(), "bytes": 0, "updated_at": None}
            if path.exists():
                try:
                    stat = path.stat()
                    item["bytes"] = stat.st_size
                    item["updated_at"] = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
                except Exception:
                    pass
            snapshot[ai] = item
        return snapshot

    def _repo_snapshot(self):
        repo = Path(__file__).parent
        result = {"path": str(repo), "available": False, "dirty": None, "changed": []}
        try:
            proc = subprocess.run(
                ["git", "status", "--short"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=5,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as e:
            result["error"] = str(e)
            return result
        result["available"] = proc.returncode == 0
        if proc.returncode != 0:
            result["error"] = (proc.stderr or proc.stdout or "").strip()[:500]
            return result
        changed = [line for line in (proc.stdout or "").splitlines() if line.strip()]
        result["dirty"] = bool(changed)
        result["changed"] = changed[:20]
        result["changed_count"] = len(changed)
        return result

    def _write_loop_report(self, state):
        lines = [
            "# Duo Hub Loop Scan",
            "",
            f"- updated_at: {state.get('updated_at')}",
            f"- status: {state.get('status')}",
            f"- phase: {state.get('phase')}",
            f"- active_task_id: {state.get('active_task_id') or ''}",
            "",
            "## Gateways",
        ]
        for name, online in (state.get("gateways") or {}).items():
            lines.append(f"- {name}: {'online' if online else 'offline'}")
        lines.extend(["", "## Agents"])
        for name, status in (state.get("agent_statuses") or {}).items():
            lines.append(f"- {name}: {status}")
        lines.extend(["", "## Findings"])
        findings = state.get("findings") or []
        if findings:
            for item in findings:
                lines.append(f"- [{item.get('severity')}] {item.get('area')}: {item.get('message')} Next: {item.get('next')}")
        else:
            lines.append("- no findings")
        lines.extend(["", "## Next Actions"])
        for action in state.get("next_actions") or []:
            lines.append(f"- {action}")
        lines.append("")
        with open(LOOP_REPORT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def run_loop_scan(self, source="manual"):
        """不调用模型的最小 Loop：发现状态、验证边界、写入下一步。"""
        self.check_and_collect_results()
        gateways = self.check_gateways()
        phase = self.session.get("phase", "idle")
        agent_statuses = {ai: self.session.get(f"{ai}_status", "idle") for ai in AI_ORDER}
        findings = []
        next_actions = []

        for name, online in gateways.items():
            if not online:
                findings.append({
                    "severity": "warn",
                    "area": "gateway",
                    "message": f"{name} 当前离线",
                    "next": "检查该 Agent provider 的安装、登录与命令路径，再重新扫描。",
                })

        if phase in ("ai_working", "negotiating", "executing"):
            next_actions.append("当前有 Agent 任务在运行，先等待完成或用“重置会话”停止后再推进下一轮。")
        elif phase == "pending_confirmation":
            findings.append({
                "severity": "action",
                "area": "division",
                "message": "分工已达成一致，正在等待用户确认",
                "next": "确认执行、输入修改意见，或取消当前分工。",
            })
        elif phase == "awaiting_feedback":
            findings.append({
                "severity": "action",
                "area": "division",
                "message": "参与 Agent 对分工存在分歧，已暂停自动协商",
                "next": "给出裁决意见，或限制协商轮次后重新触发协商。",
            })
        elif phase in ("idle", "awaiting_user", "done"):
            next_actions.append("系统空闲，可提交任务；默认不会调用模型，除非勾选启用 Agent 调用。")

        for ai, status in agent_statuses.items():
            if status == "working":
                started = self.session.get(f"_{ai}_started", 0)
                age = time.time() - started if started else 0
                if age > AI_TIMEOUT:
                    findings.append({
                        "severity": "action",
                        "area": ai,
                        "message": f"{AI_LABELS[ai]} 已运行超过超时时间",
                        "next": "刷新状态收集超时结果，必要时重置会话。",
                    })
            elif status in ("timeout", "error"):
                findings.append({
                    "severity": "warn",
                    "area": ai,
                    "message": f"{AI_LABELS[ai]} 状态为 {status}",
                    "next": "查看对应面板输出，必要时切换模型或检查网关。",
                })

        repo = self._repo_snapshot()
        if repo.get("dirty"):
            findings.append({
                "severity": "info",
                "area": "repo",
                "message": f"当前仓库有 {repo.get('changed_count', 0)} 个未提交变更",
                "next": "提交前先跑验证，并决定 models.yaml 是否纳入仓库。",
            })

        if not findings:
            status = "ready"
            summary = "Loop 扫描通过：网关和会话状态未发现阻塞项。"
        elif any(item["severity"] == "action" for item in findings):
            status = "blocked"
            summary = "Loop 扫描发现需要用户裁决或人工处理的阻塞项。"
        else:
            status = "watching"
            summary = "Loop 扫描发现可观察风险，但不阻塞继续工作。"

        if not next_actions:
            next_actions = [item["next"] for item in findings[:3]] or ["继续保持当前状态。"]

        state = {
            "schema_version": 1,
            "status": status,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "summary": summary,
            "session_id": self.session.get("session_id"),
            "phase": phase,
            "active_task_id": self.session.get("active_task_id"),
            "gateways": gateways,
            "agent_statuses": agent_statuses,
            "outboxes": self._outbox_snapshot(),
            "repo": repo,
            "findings": findings,
            "next_actions": next_actions,
            "report_path": str(LOOP_REPORT_FILE),
        }

        tmp = LOOP_STATE_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        tmp.replace(LOOP_STATE_FILE)
        self._write_loop_report(state)
        return state

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
        session = {
            "session_id": f"dh_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "phase": "idle",
            "round": 0,
            "event_seq": 0,
            "_active_run_id": "",
            "active_task_id": None,
            "created_at": datetime.now().isoformat(),
        }
        for adapter in self.agent_registry.enabled():
            agent_id = adapter.descriptor.id
            session[f"{agent_id}_status"] = "idle"
            session[f"{agent_id}_model"] = adapter.descriptor.default_model
        return session

    def _normalize_session(self):
        """Migrate legacy sessions to the currently enabled registry seats."""
        self.session.setdefault("phase", "idle")
        self.session.setdefault("round", 0)
        self.session.setdefault("event_seq", 0)
        self.session.setdefault("_active_run_id", "")
        self.session.setdefault("active_task_id", None)
        self.session.setdefault("created_at", datetime.now().isoformat())
        for adapter in self.agent_registry.enabled():
            agent_id = adapter.descriptor.id
            self.session.setdefault(f"{agent_id}_status", "idle")
            self.session.setdefault(f"{agent_id}_model", adapter.descriptor.default_model)

    @staticmethod
    def _normalize_lobster_model_id(model):
        model = (model or "").strip()
        return LOBSTER_MODEL_ALIASES.get(model, model or DEFAULT_LOBSTER_MODEL)

    @staticmethod
    def _normalize_claude_model_id(model):
        model = (model or "").strip()
        return CLAUDE_MODEL_ALIASES.get(model, model or DEFAULT_CLAUDE_MODEL)

    def _init_chat(self):
        if CHAT_FILE.exists():
            try:
                with open(CHAT_FILE, "r", encoding="utf-8") as f:
                    self.chat = json.load(f)
            except Exception:
                self.chat = {"messages": []}
        else:
            self.chat = {"messages": []}
        self._normalize_chat()
        self._save_chat()

    def _normalize_chat(self):
        """Keep chat storage tolerant to manual protocol edits."""
        if isinstance(self.chat, dict):
            messages = self.chat.get("messages")
            self.chat["messages"] = messages if isinstance(messages, list) else []
            return

        if isinstance(self.chat, list) and self.chat:
            first = self.chat[0]
            if isinstance(first, dict) and isinstance(first.get("messages"), list):
                messages = list(first["messages"])
                max_id = 0
                for msg in messages:
                    msg_id = str(msg.get("id", ""))
                    match = re.match(r"^msg_(\d+)$", msg_id)
                    if match:
                        max_id = max(max_id, int(match.group(1)))
                for item in self.chat[1:]:
                    if not isinstance(item, dict):
                        continue
                    max_id += 1
                    item.setdefault("id", f"msg_{max_id:04d}")
                    item.setdefault("round", self.session.get("round", 0))
                    messages.append(item)
                self.chat = {"messages": messages}
                return

        self.chat = {"messages": []}

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
            return self._gateway_cache or {agent_id: False for agent_id in SUPERVISOR_TARGETS}

        try:
            now = time.time()
            if self._gateway_cache and now - self._gateway_cache_at < GATEWAY_CACHE_TTL:
                return self._gateway_cache

            agent_health = self.agent_registry.health()
            self._agent_health_cache = agent_health
            self._gateway_cache = {
                agent_id: bool(health.get("available"))
                for agent_id, health in agent_health.items()
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

    def add_message(self, role, content, metadata=None):
        msg = {
            "id": self._next_msg_id(),
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "round": self.session["round"],
        }
        if metadata:
            msg["metadata"] = metadata
        self.chat["messages"].append(msg)
        self._save_chat()
        return msg

    def append_event(self, event_type, actor, content, metadata=None):
        """Append one visible, auditable event. Secrets and hidden reasoning are never added."""
        with self._event_lock:
            seq = int(self.session.get("event_seq", 0)) + 1
            self.session["event_seq"] = seq
            event = {
                "event_id": f"{self.session['session_id']}_{seq:06d}",
                "session_id": self.session["session_id"],
                "seq": seq,
                "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                "event_type": event_type,
                "actor": actor,
                "recorded_by": "duo-hub",
                "content": content,
                "content_hash": hashlib.sha256((content or "").encode("utf-8")).hexdigest(),
                "metadata": metadata or {},
            }
            EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(EVENTS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._save_session()
            return event

    def get_recent_messages(self, n=20):
        return self.chat["messages"][-n:]

    # ---- 协议 I/O ----
    def write_inbox(self, task_text):
        recent = self.get_recent_messages(AGENT_CONTEXT_MESSAGES)
        ctx = ""
        if recent:
            ctx = "\n\n## 对话上下文\n\n"
            for m in recent:
                role_label = AI_LABELS.get(m["role"], m["role"])
                ctx += f"**{role_label}**: {_truncate_text(m['content'])}\n\n"

        participants = "、".join(AI_LABELS[ai] for ai in AI_ORDER) or "当前已注册 Agent"
        division_example = "\n".join(f"- {AI_LABELS[ai]}负责：xxx" for ai in AI_ORDER)
        header = (
            "# Duo Hub 协作任务\n\n"
            f"你正在 Duo Hub 协作中心工作。当前启用的 Agent：{participants}。"
            "用户通过 Duo Hub 与当前 Agent 交互。\n\n"
            "工作规则：\n"
            "1. 分析任务需求，给出你的方案\n"
            "2. 标注你擅长的部分和需要对方配合的部分\n"
            f"3. 如果是协商，请按当前 Agent 明确提出分工建议：\n{division_example}\n"
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

    def _begin_run(self):
        run_id = f"run_{uuid.uuid4().hex}"
        self.session["_active_run_id"] = run_id
        return run_id

    def _run_is_current(self, run_id, session_id):
        return bool(
            run_id
            and session_id
            and self.session.get("_active_run_id") == run_id
            and self.session.get("session_id") == session_id
        )

    # ---- AI 调用 ----
    def invoke_gemini(self, task_text, model=None, mode="task", run_id="", session_id=""):
        """Invoke the logical Gemini seat through its configured provider adapter."""
        adapter = self.agent_registry.get("gemini")
        run_id = run_id or self.session.get("_active_run_id", "")
        session_id = session_id or self.session.get("session_id", "")
        if not self._run_is_current(run_id, session_id):
            return
        try:
            self.session["gemini_status"] = "working"
            self.session["_gemini_started"] = time.time()
            self._save_session()
            self.clear_outbox("gemini")

            mode_prompts = {
                "task": "[Duo Hub 分析模式]\n请只分析并回答任务，不执行写入、发布、删除或账号操作。",
                "negotiate": "[Duo Hub 协商模式]\n请审查 Codex 的分工方案，明确同意或指出需要调整之处。",
                "execute": "[Duo Hub 执行准备模式]\n请给出可执行方案和产物内容；当前阶段仍禁止直接修改文件。",
            }
            prompt = f"{mode_prompts.get(mode, mode_prompts['task'])}\n回复使用中文。\n\n{task_text}"
            requested_model = model or self.session.get("gemini_model") or adapter.descriptor.default_model
            self.append_event("agent_prompt", "codex", prompt, {
                "target": "gemini",
                "provider": adapter.descriptor.provider,
                "model": requested_model,
                "mode": mode,
            })
            result = adapter.invoke(AgentRequest(
                prompt=prompt,
                model=requested_model,
                mode=mode,
                timeout_seconds=AI_TIMEOUT,
                run_id=run_id,
            ))
            if not self._run_is_current(run_id, session_id):
                return
            metadata = result.metadata()
            metadata["run_id"] = run_id
            self.session["_gemini_last_run"] = metadata
            self.session["gemini_status"] = result.status
            output = result.output if result.status == "done" else (
                f"Gemini 调用失败（provider={result.provider}, exit={result.exit_code}）："
                f"{result.error or '未返回可见错误'}"
            )
            with open(OUTBOX_GEMINI, "w", encoding="utf-8") as f:
                f.write(output)
            self.append_event("agent_output", "gemini", output, metadata)
            self._save_session()
        except Exception as exc:
            if not self._run_is_current(run_id, session_id):
                return
            output = f"Gemini 调用出错: {exc}"
            with open(OUTBOX_GEMINI, "w", encoding="utf-8") as f:
                f.write(output)
            self.session["gemini_status"] = "error"
            self.session["_gemini_last_run"] = {
                "actor": "gemini",
                "recorded_by": "duo-hub",
                "provider": adapter.descriptor.provider,
                "model": model or adapter.descriptor.default_model,
                "status": "error",
                "run_id": run_id,
                "error": str(exc),
            }
            self.append_event("error", "gemini", output, self.session["_gemini_last_run"])
            self._save_session()

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
                recent = self.get_recent_messages(AGENT_CONTEXT_MESSAGES)
                history = "\n\n".join([f"[{m['role']}]: {_truncate_text(m['content'])}" for m in recent])
                short_prompt = f"对话历史：\n{history}\n\n---\n最新任务：{task_text}"

            # 将完整提示词写入文件，通过 stdin 传给 Claude CLI（避开 Windows 命令行 8191 字符限制）
            full_prompt = f"{hub_prompt}\n\n---\n\n{short_prompt}"
            model_arg = self._normalize_claude_model_id(model or self.session.get("claude_model"))

            if mode != "execute":
                output = _post_claude_review_message(full_prompt, model_arg)
                with open(OUTBOX_CLAUDE, "w", encoding="utf-8") as f:
                    f.write(output)
                self.session["claude_status"] = "done"
                self._save_session()
                return

            import uuid
            prompt_file = PROTOCOL_DIR / "inbox" / f"_claude_stdin_{uuid.uuid4().hex[:8]}.txt"
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(full_prompt)

            cmd = _claude_cmd_parts() + [
                "--print",
                "--dangerously-skip-permissions",
                "--permission-mode", "bypassPermissions",
                "--output-format", "text",
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
                    env=_claude_gateway_env(model_arg),
                )

            # 清理临时文件
            try:
                prompt_file.unlink()
            except Exception:
                pass

            output = (result.stdout or "").strip()
            empty_output = not output
            if empty_output:
                stderr = (result.stderr or "").strip()
                if stderr:
                    output = (
                        "[Claude Code CLI 未返回正文]\n"
                        "执行类任务没有得到可用结果；普通阅读/回复请走 ccmr 轻量路径。\n"
                        f"returncode: {result.returncode}\n"
                        f"stderr: {stderr[:800]}"
                    )
                else:
                    output = (
                        "[Claude Code CLI 未返回正文]\n"
                        "执行类任务没有得到可用结果；普通阅读/回复请走 ccmr 轻量路径。"
                    )

            # 移除末尾的 [DuoHub:完成] 标记
            marker = "[DuoHub:完成]"
            if output.endswith(marker):
                output = output[: -len(marker)].strip()

            with open(OUTBOX_CLAUDE, "w", encoding="utf-8") as f:
                f.write(output)

            self.session["claude_status"] = "error" if empty_output else "done"
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

            model_arg = self._normalize_lobster_model_id(model or self.session.get("lobster_model"))
            fast_model = _lobster_fast_ccmr_model(model_arg)
            if mode != "execute" and fast_model:
                full_prompt = (
                    "[Duo Hub 龙虾轻量回复模式]\n"
                    "你代表 OpenClaw「龙虾」参与三AI协作。当前只需要快速阅读和回复，"
                    "不要调用工具、不要执行外部动作、不要假装已经操作系统。回复使用中文，直接给结论。\n\n"
                    f"任务：{task_text}\n\n"
                    f"共享任务文件：{inbox}\n"
                )
                output = _post_ccmr_message(full_prompt, fast_model)
                with open(OUTBOX_LOBSTER, "w", encoding="utf-8") as f:
                    f.write(output)
                self.session["lobster_status"] = "done"
                self._save_session()
                return

            timeout_arg = str(min(AI_TIMEOUT, 120))
            cmd = _openclaw_cmd_parts() + [
                "agent",
                "--message", short_prompt,
                "--session-key", "main",
                "--json",
                "--model", model_arg,
                "--thinking", "minimal",
                "--timeout", timeout_arg,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=AI_TIMEOUT,
                encoding="utf-8",
                errors="replace",
                shell=False,
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
            self.add_message(ai, text, self.session.get(f"_{ai}_last_run", {}))
            self.session[f"_{ai}_collected"] = self.session["round"]
            self._save_session()

    def _format_recent(self, n=20):
        recent = self.get_recent_messages(n)
        return "\n\n".join([f"[{AI_LABELS.get(m['role'], m['role'])}]: {m['content']}" for m in recent])

    @staticmethod
    def _parse_division_plan(text):
        """Extract tasks for whichever logical agents are currently enabled."""
        if not text:
            return None
        plan = {ai: "" for ai in AI_ORDER}
        all_aliases = {
            "gemini": ["Gemini", "谷歌 Gemini"],
            "claude": ["Claude", "Claude Code", "克劳德"],
            "lobster": ["龙虾", "OpenClaw", "小八", "Lobster"],
            "codex": ["Codex"],
        }
        aliases = {ai: all_aliases.get(ai, [ai]) for ai in AI_ORDER}
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
                            markers = [
                                marker
                                for alias_names in aliases.values()
                                for name in alias_names
                                for marker in (f"{name}负责", f"{name} 负责")
                            ]
                            if any(token in f for token in markers):
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
            "gemini": self.invoke_gemini,
            "claude": self.invoke_claude,
            "lobster": self.invoke_lobster,
            "codex": self.invoke_codex,
        }[ai]
        if ai == "gemini":
            kwargs = {
                "run_id": self.session.get("_active_run_id", ""),
                "session_id": self.session.get("session_id", ""),
            }
            threading.Thread(target=target, args=(task_text, model, mode), kwargs=kwargs, daemon=True).start()
            return
        threading.Thread(target=target, args=(task_text, model, mode), daemon=True).start()

    def process_task(self, task_text, needs_division=False, allow_paid_agents=False):
        """Submit a task; model calls only run after explicit UI opt-in."""
        if self.session["phase"] in ("ai_working", "negotiating", "pending_confirmation", "awaiting_feedback", "executing", "supervising"):
            return False, "已有任务正在处理中"

        self.session["round"] += 1
        self.session["active_task_id"] = f"task_{self.session['round']:03d}"
        self.session["_needs_division"] = needs_division
        self.write_inbox(task_text)
        self.add_message("user", task_text)

        if allow_paid_agents and _is_heartbeat_task(task_text):
            gws = self.check_gateways()
            self.session["_active_run_id"] = ""
            self.session["phase"] = "awaiting_user"
            for ai in AI_ORDER:
                self.session[f"{ai}_status"] = "done"
                self.session[f"_{ai}_collected"] = self.session["round"]
            self._save_session()
            for ai in AI_ORDER:
                self.add_message(ai, f"{AI_LABELS[ai]} provider 状态：{'在线' if gws.get(ai) else '离线'}。")
            self.add_message("system", f"🩺 连接检查已完成；这次没有调用模型。Duo Hub {APP_VERSION}。")
            return True, self.session["active_task_id"]

        if not allow_paid_agents:
            self.session["_active_run_id"] = ""
            self.session["phase"] = "awaiting_user"
            for ai in AI_ORDER:
                self.session[f"{ai}_status"] = "idle"
                self.session[f"_{ai}_collected"] = self.session["round"]
            self._save_session()
            names = "、".join(AI_LABELS[ai] for ai in AI_ORDER)
            self.add_message("system", f"已记录这条内容，但未启动 {names}。要实际调用模型，请先勾选“启用 Agent 调用”。")
            return True, self.session["active_task_id"]

        self._begin_run()
        self.session["phase"] = "ai_working"
        for ai in AI_ORDER:
            self.session[f"{ai}_status"] = "working"
            self.session[f"_{ai}_collected"] = 0
        self._save_session()

        for ai in AI_ORDER:
            self._start_agent(ai, task_text, "task")

        return True, self.session["active_task_id"]

    def supervisor_note(self, role, content):
        """Codex 主管把当前裁决/说明同步到看板，不调用任何模型。"""
        role = (role or "codex").strip().lower()
        if role not in AI_LABELS:
            role = "codex"
        content = (content or "").strip()
        if not content:
            return False, "内容不能为空"

        if self.session.get("phase") not in ("ai_working", "negotiating", "pending_confirmation", "awaiting_feedback", "executing", "supervising"):
            self.session["phase"] = "awaiting_user"
        self.session["_supervisor_mode"] = True
        self._save_session()
        msg = self.add_message(role, content)
        return True, msg["id"]

    def supervisor_delegate(self, target, task_text, mode="task"):
        """Codex 主管按需只委派给一个指定参与方，并把请求/回包展示在 Duo Hub。"""
        target = (target or "").strip().lower()
        if target not in SUPERVISOR_TARGETS:
            return False, f"target 只能是：{', '.join(SUPERVISOR_TARGETS)}"

        if self.session["phase"] in ("ai_working", "negotiating", "pending_confirmation", "awaiting_feedback", "executing", "supervising"):
            return False, "已有任务正在处理中"

        task_text = (task_text or "").strip()
        if not task_text:
            return False, "委派内容不能为空"

        mode = (mode or "task").strip().lower()
        if mode not in ("task", "negotiate", "execute"):
            mode = "task"

        self.session["round"] += 1
        self.session["active_task_id"] = f"supervisor_{self.session['round']:03d}_{target}"
        self._begin_run()
        self.session["phase"] = "supervising"
        self.session["_supervisor_mode"] = True
        self.session["_supervisor_targets"] = [target]
        self.session[f"{target}_status"] = "working"
        self.session[f"_{target}_collected"] = 0
        self.session[f"_{target}_started"] = time.time()
        self._save_session()

        label = AI_LABELS[target]
        self.add_message("codex", f"【Codex 主管 -> {label}】\n{task_text}")
        prompt = (
            "## Codex 主管委派\n\n"
            f"你现在是 Codex 主管调度下的参与方：{label}。\n"
            "用户不直接与你协商；你只需要回答 Codex 主管委派给你的问题。\n"
            "要求：\n"
            "1. 只处理委派内容，不主动扩展到账号、发布、删除、交易等外部动作。\n"
            "2. 如果需要外部动作或敏感数据，明确说明需要 Codex 主管回到用户处确认。\n"
            "3. 回复给 Codex 主管，使用中文，直接给结论、依据、风险和下一步。\n\n"
            "## 委派内容\n\n"
            f"{task_text}"
        )
        self.write_inbox(prompt)
        self._start_agent(target, prompt, mode)
        return True, self.session["active_task_id"]

    def supervisor_assign(self, assignments, mode="execute"):
        """Codex supervisor assigns work to enabled registry agents."""
        if self.session["phase"] in ("ai_working", "negotiating", "pending_confirmation", "awaiting_feedback", "executing", "supervising"):
            return False, "已有任务正在处理中"

        if not isinstance(assignments, dict):
            return False, "assignments 必须是对象"

        cleaned = {}
        for ai in AI_ORDER:
            text = (assignments.get(ai) or "").strip()
            if text:
                cleaned[ai] = text

        if not cleaned:
            return False, f"至少要给 {', '.join(AI_ORDER)} 中的一方分配任务"

        mode = (mode or "execute").strip().lower()
        if mode not in ("task", "negotiate", "execute"):
            mode = "execute"

        self.session["round"] += 1
        self.session["active_task_id"] = f"division_{self.session['round']:03d}"
        self._begin_run()
        self.session["phase"] = "supervising"
        self.session["_supervisor_mode"] = True
        self.session["_supervisor_targets"] = list(cleaned.keys())
        self.session["_division_plan"] = {ai: cleaned.get(ai, "") for ai in AI_ORDER}
        self.session["_division_status"] = "supervisor_assigned"
        self.session["_peer_feedback"] = {}

        for ai in AI_ORDER:
            self.session[f"{ai}_status"] = "working" if ai in cleaned else "idle"
            self.session[f"_{ai}_collected"] = 0 if ai in cleaned else self.session["round"]
            if ai in cleaned:
                self.session[f"_{ai}_started"] = time.time()

        self._save_session()

        plan_lines = "\n".join(
            f"- {AI_LABELS[ai]}负责：{cleaned[ai]}"
            for ai in AI_ORDER
            if ai in cleaned
        )
        self.add_message("codex", f"【Codex 主管分工】\n{plan_lines}")
        self.add_message("system", f"🧭 Codex 主管已下发分工：{len(cleaned)} 个参与方并行执行。")

        shared_context = self._format_recent(20)
        for ai, assigned in cleaned.items():
            other_parts = "\n".join(
                f"- {AI_LABELS[other]}：{task}"
                for other, task in cleaned.items()
                if other != ai
            )
            prompt = (
                "## Duo Hub Agent 分工执行\n\n"
                f"你是 {AI_LABELS[ai]}。Codex 主管已经把同一个总任务拆给多个参与方。\n"
                "你只执行明确分配给你的部分，不要重复执行其他参与方的任务。\n"
                "如果你的任务需要外部账号动作、发布、删除、交易或敏感数据，必须停止并说明需要用户确认。\n\n"
                "## 你负责的任务\n\n"
                f"{assigned}\n\n"
                "## 其他参与方的任务（只作边界参考，不要代做）\n\n"
                f"{other_parts or '无'}\n\n"
                "## 回复要求\n\n"
                "用中文直接报告：已完成内容、关键证据/文件、风险、下一步建议。\n\n"
                f"---\n{shared_context}"
            )
            self.write_inbox(prompt)
            self._start_agent(ai, prompt, mode)

        return True, self.session["active_task_id"]

    def check_and_collect_results(self):
        if not self._collect_lock.acquire(blocking=False):
            return
        try:
            self._check_and_collect_results_locked()
        finally:
            self._collect_lock.release()

    def _check_and_collect_results_locked(self):
        """检查当前注册的 Agent 是否完成，收集结果，自动推进阶段。"""
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
                self.session["_active_run_id"] = ""
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
                peer_agents = tuple(ai for ai in AI_ORDER if ai != "codex")
                for ai in peer_agents:
                    self._collect_if_done(ai)

                if peer_agents and self._all_done(peer_agents):
                    peer_states = {
                        ai: self._agent_agreement_state(self.read_outbox(ai) or "")
                        for ai in peer_agents
                    }
                    self.session["_peer_feedback"] = {
                        **{ai: self.read_outbox(ai) or "" for ai in peer_agents},
                        "states": peer_states,
                    }
                    peers_agreed = all(state == "agree" for state in peer_states.values())
                    neg_rounds = self.session.get("_neg_rounds", 0) + 1
                    self.session["_neg_rounds"] = neg_rounds

                    if peers_agreed:
                        self.session["phase"] = "pending_confirmation"
                        self.session["_division_status"] = "agreed"
                        msg = "✅ 参与 Agent 已同意分工。请确认执行，或输入修改意见继续调整。"
                        self.add_message("system", msg)
                        self._save_session()
                    elif neg_rounds >= 3:
                        self.session["phase"] = "awaiting_feedback"
                        self.session["_division_status"] = "needs_user"
                        self.add_message(
                            "system",
                            "⚠️ 参与 Agent 未达成一致，已暂停自动协商。请补充意见、继续协商、确认当前方案，或取消分工。"
                        )
                        self._save_session()
                    else:
                        self._negotiate_codex_adjust()

        elif phase == "executing":
            for ai in AI_ORDER:
                self._collect_if_done(ai)

            if self._all_done():
                self.session["_active_run_id"] = ""
                self.session["phase"] = "done"
                self.add_message("system", "🎉 Agent 执行完毕！请在面板中查看成果。")
                self._save_session()

        elif phase == "supervising":
            targets = [ai for ai in self.session.get("_supervisor_targets", []) if ai in SUPERVISOR_TARGETS]
            for ai in targets:
                self._collect_if_done(ai)

            if targets and self._all_done(targets):
                names = "、".join(AI_LABELS[ai] for ai in targets)
                self.session["_active_run_id"] = ""
                self.session["phase"] = "awaiting_user"
                self.add_message("system", f"✅ Codex 主管委派已完成：{names} 已回包。")
                self._save_session()

    def _auto_negotiate(self, user_feedback=""):
        """Prepare a division for the currently enabled registry agents."""
        if len(AI_ORDER) == 1:
            agent_id = AI_ORDER[0]
            latest_user = next(
                (msg.get("content", "") for msg in reversed(self.chat.get("messages", [])) if msg.get("role") == "user"),
                "",
            )
            self.session["_division_plan"] = {agent_id: latest_user}
            self.session["_division_status"] = "single_agent_ready"
            self.session["_peer_feedback"] = {}
            self.session["phase"] = "pending_confirmation"
            self.add_message("system", f"📋 当前只启用 {AI_LABELS[agent_id]}，已生成单 Agent 分工，请确认执行。")
            self._save_session()
            return

        context_str = self._format_recent(20)
        feedback_block = f"\n\n## 用户的补充意见\n\n{user_feedback}\n" if user_feedback else ""

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

        self.add_message("system", "🤝 Codex 正在汇总参与 Agent 的意见，准备提出分工…")

        plan_format = "\n".join(f"- {AI_LABELS[ai]}负责：[具体、可执行]" for ai in AI_ORDER)
        prompt = (
            "## 协商分工 - Codex 汇总提案\n\n"
            "请阅读参与 Agent 的初步回复和用户补充意见，提出明确分工。\n"
            f"必须包含：\n{plan_format}\n"
            "规则：责任边界清晰，不重复安排同一件事；如果某方能力明显不适合，就把它安排到更适合的支持/审查/资料任务。\n"
            "回复使用中文。\n\n"
            f"{feedback_block}\n---\n{context_str}"
        )
        self.write_inbox(prompt)
        self._start_agent("codex", prompt, "negotiate")

    def _negotiate_peers_respond(self):
        """Enabled non-supervisor agents confirm the proposed division."""
        context_str = self._format_recent(20)
        self.session["_negotiate_stage"] = "peers_confirm"
        peer_agents = tuple(ai for ai in AI_ORDER if ai != "codex")
        for ai in peer_agents:
            self.session[f"{ai}_status"] = "working"
            self.session[f"_{ai}_collected"] = 0
        self._save_session()

        self.add_message("system", f"🤝 {'、'.join(AI_LABELS[ai] for ai in peer_agents)} 正在确认分工提案…")

        prompt = (
            "## 协商分工 - 确认或调整\n\n"
            "Codex 已经提出 Agent 分工方案（见上文）。请只从你的能力边界和执行可行性出发确认或调整：\n"
            "- 同意就说「同意分工」，并列出你要执行的任务\n"
            "- 不同意就说明哪一项不可行，并给出替代分工\n"
            "回复使用中文。\n\n"
            f"---\n{context_str}"
        )
        self.write_inbox(prompt)
        for ai in peer_agents:
            self._start_agent(ai, prompt, "negotiate")

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

        self.add_message("system", "🤝 参与 Agent 提出调整意见，Codex 正在重新整合分工…")

        plan_format = "\n".join(f"- {AI_LABELS[ai]}负责：[调整后的任务]" for ai in AI_ORDER)
        prompt = (
            "## 协商 - Codex 调整方案\n\n"
            "参与 Agent 对上轮分工提出了不同意见。请吸收合理反馈，重新给出分工。\n"
            f"格式：\n{plan_format}\n"
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
        """用户确认分工方案后，由当前注册 Agent 分别执行。"""
        if self.session["phase"] not in ("pending_confirmation", "awaiting_feedback"):
            return False, "没有待确认的分工方案"

        self.session["round"] += 1
        self._begin_run()
        self.session["phase"] = "executing"
        self.session["_exec_round"] = self.session["round"]
        for ai in AI_ORDER:
            self.session[f"{ai}_status"] = "working"
            self.session[f"_{ai}_collected"] = 0
        if self.session.get("_division_status") == "needs_user":
            self.add_message("system", "✅ 用户已强制确认当前分工！参与 Agent 开始执行各自任务…")
        else:
            self.add_message("system", "✅ 用户已确认分工！参与 Agent 开始执行各自任务…")
        self._save_session()

        all_context = self._format_recent(30)
        division_plan = self.session.get("_division_plan") or {}
        shared_task = (
            "## 执行阶段 - Agent 共享上下文\n\n"
            "分工方案已经用户确认。每个 Agent 只执行明确标注给自己的部分。\n"
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
        if ai == "claude":
            model = self._normalize_claude_model_id(model)
        elif ai == "lobster":
            model = self._normalize_lobster_model_id(model)
        self.session[f"{ai}_model"] = model or ""
        self._save_session()
        return True

    def stop_session(self):
        """重置会话（保留历史为新会话存档）"""
        cancelled_run_id = self.session.get("_active_run_id", "")
        if cancelled_run_id:
            self.agent_registry.cancel_all(cancelled_run_id)
            self.session["_active_run_id"] = ""

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
                        "cancelled_run_id": cancelled_run_id,
                    }, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # 创建新会话
        self.session = self._new_session()
        self.chat = {"messages": []}
        for ai in AI_ORDER:
            self.clear_outbox(ai)
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

        agents = self.agent_registry.public_agents(self.session)

        gateways = self.check_gateways()
        return {
            "version": APP_VERSION,
            "session_id": self.session["session_id"],
            "phase": self.session["phase"],
            "round": self.session["round"],
            "active_task_id": self.session.get("active_task_id"),
            "gateways": gateways,
            "agent_health": self._agent_health_cache,
            "agents": agents,
            "messages": recent,
            "total_messages": len(messages),
            "loop": self.get_loop_state(),
            "division": division,
            "division_status": self.session.get("_division_status", ""),
            "peer_feedback": self.session.get("_peer_feedback", {}),
            "event_seq": self.session.get("event_seq", 0),
            "created_at": self.session["created_at"],
        }


# ============================================================
# HTTP 请求处理
# ============================================================
hub = DuoHub()


class DuoHubHandler(http.server.BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    def log_message(self, format, *args):
        # Keep polling-heavy HTTP access logs from blocking responses on Windows redirects.
        if os.environ.get("DUO_HTTP_ACCESS_LOGS", "").lower() not in ("1", "true", "yes"):
            return
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}", flush=False)
        except UnicodeEncodeError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] request", flush=False)

    # ---- 路由分发 ----
    def do_OPTIONS(self):
        if not self._request_is_local() or not self._origin_is_allowed():
            self._send_error(403, "Cross-origin request denied")
            return
        self.send_response(204)
        origin = self.headers.get("Origin", "").strip()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Duo-Hub-Token")
        self._send_security_headers()
        self.end_headers()

    def do_GET(self):
        if not self._request_is_local() or not self._origin_is_allowed():
            self._send_error(403, "Local same-origin access only")
            return
        path = urllib.parse.urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._serve_static("index.html", "text/html; charset=utf-8")
        elif path == "/style.css":
            self._serve_static("style.css", "text/css; charset=utf-8")
        elif path == "/supervisor_status.css":
            self._serve_static("supervisor_status.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self._serve_static("app.js", "application/javascript; charset=utf-8")
        elif path == "/supervisor_status.js":
            self._serve_static("supervisor_status.js", "application/javascript; charset=utf-8")
        elif path == "/api/state":
            self._serve_json(hub.get_state())
        elif path == "/api/loop":
            self._serve_json(hub.get_loop_state())
        else:
            self._send_error(404, "Not Found")

    def do_POST(self):
        if not self._request_is_local() or not self._origin_is_allowed():
            self._send_error(403, "Local same-origin access only")
            return
        if not self._post_token_is_valid():
            self._send_error(401, "Missing or invalid Duo Hub API token")
            return
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
            allow_paid_agents = data.get("allow_paid_agents", False)
            if not text:
                self._serve_json({"error": "任务内容不能为空"}, 400)
                return

            ok, task_id = hub.process_task(text, needs_division=needs_division, allow_paid_agents=allow_paid_agents)
            if ok:
                self._serve_json({"ok": True, "task_id": task_id})
            else:
                self._serve_json({"error": task_id}, 409)

        elif path == "/api/supervisor/note":
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._serve_json({"error": "Invalid JSON"}, 400)
                return

            ok, msg_id = hub.supervisor_note(
                role=(data.get("role") or "codex"),
                content=(data.get("content") or ""),
            )
            if ok:
                self._serve_json({"ok": True, "message_id": msg_id})
            else:
                self._serve_json({"error": msg_id}, 400)

        elif path == "/api/supervisor/delegate":
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._serve_json({"error": "Invalid JSON"}, 400)
                return

            ok, task_id = hub.supervisor_delegate(
                target=(data.get("target") or ""),
                task_text=(data.get("text") or ""),
                mode=(data.get("mode") or "task"),
            )
            if ok:
                self._serve_json({"ok": True, "task_id": task_id})
            else:
                status = 409 if "处理中" in task_id else 400
                self._serve_json({"error": task_id}, status)

        elif path == "/api/supervisor/assign":
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._serve_json({"error": "Invalid JSON"}, 400)
                return

            ok, task_id = hub.supervisor_assign(
                assignments=(data.get("assignments") or {}),
                mode=(data.get("mode") or "execute"),
            )
            if ok:
                self._serve_json({"ok": True, "task_id": task_id})
            else:
                status = 409 if "处理中" in task_id else 400
                self._serve_json({"error": task_id}, status)

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

        elif path == "/api/loop-scan":
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                data = {}
            source = (data.get("source") or "manual").strip()[:40]
            self._serve_json({"ok": True, "loop": hub.run_loop_scan(source=source)})

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
            if filename == "index.html":
                self.send_header(
                    "Set-Cookie",
                    f"duo_hub_token={hub.api_token}; HttpOnly; SameSite=Strict; Path=/",
                )
            self._send_security_headers()
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.close_connection = True
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()
        except Exception as e:
            self._send_error(500, str(e))

    def _serve_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self._send_security_headers()
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def _send_security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )

    @staticmethod
    def _loopback_hostname(value):
        try:
            hostname = urllib.parse.urlsplit(f"//{value}").hostname
            return bool(hostname and (
                hostname.lower() == "localhost" or ipaddress.ip_address(hostname).is_loopback
            ))
        except ValueError:
            return False

    def _request_is_local(self):
        try:
            client_is_local = ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            client_is_local = False
        return client_is_local and self._loopback_hostname(self.headers.get("Host", ""))

    def _origin_is_allowed(self):
        origin = self.headers.get("Origin", "").strip()
        if not origin:
            return True
        try:
            parsed = urllib.parse.urlsplit(origin)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return (
                parsed.scheme == "http"
                and self._loopback_hostname(parsed.netloc)
                and port == PORT
            )
        except ValueError:
            return False

    def _post_token_is_valid(self):
        supplied = self.headers.get("X-Duo-Hub-Token", "").strip()
        if not supplied:
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                supplied = cookie.get("duo_hub_token").value if cookie.get("duo_hub_token") else ""
            except Exception:
                supplied = ""
        return bool(supplied) and hmac.compare_digest(supplied, hub.api_token)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            previous_timeout = self.connection.gettimeout()
            raw = b""
            deadline = time.time() + REQUEST_BODY_TIMEOUT
            reader = getattr(self.rfile, "read1", self.rfile.read)
            try:
                # 循环读取确保读满所有字节；超时后返回已收到内容，避免坏请求拖住线程。
                while len(raw) < length:
                    remaining_time = deadline - time.time()
                    if remaining_time <= 0:
                        break
                    self.connection.settimeout(max(0.1, remaining_time))
                    chunk = reader(min(4096, length - len(raw)))
                    if not chunk:
                        break
                    raw += chunk
            except socket.timeout:
                pass
            finally:
                self.connection.settimeout(previous_timeout)
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

    quiet = os.environ.get("DUO_QUIET", "").lower() in ("1", "true", "yes")
    quiet = quiet or os.environ.get("DUO_NO_BROWSER", "").lower() in ("1", "true", "yes")

    def say(*args, **kwargs):
        if not quiet:
            print(*args, **kwargs)

    say("=" * 56)
    say("  ⚡ Duo Hub — 可插拔 Agent 协作中心")
    say("=" * 56)
    say()
    say(f"  协议目录: {PROTOCOL_DIR}")
    say(f"  前端文件: {WEB_DIR}")
    say(f"  Gemini 工作区: {GEMINI_WORKSPACE}")
    say()

    # 检查网关
    say("[检测] 网关状态...")
    gws = hub.check_gateways()
    gemini_icon = "[OK]" if gws["gemini"] else "[XX]"
    provider = hub.agent_registry.get("gemini").descriptor.provider
    say(f"  {gemini_icon} Gemini 席位 ({provider})")
    say()

    if not gws["gemini"]:
        say("[!!] 当前 Gemini provider 不可用，请检查本机命令安装")
        say()

    # 启动 HTTP 服务器
    server = http.server.ThreadingHTTPServer((HOST, PORT), DuoHubHandler)
    say(f"[启动] Duo Hub 服务器 -> http://{HOST}:{PORT}")
    say()
    say("  按 Ctrl+C 停止服务器")
    say("=" * 56)

    # 自动打开浏览器；验证或后台运行可设置 DUO_NO_BROWSER=1 跳过。
    if os.environ.get("DUO_NO_BROWSER", "").lower() not in ("1", "true", "yes"):
        def open_browser():
            time.sleep(0.5)
            webbrowser.open(f"http://{HOST}:{PORT}")

        threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        say("\n[停止] 服务器已关闭")
        server.shutdown()


if __name__ == "__main__":
    main()
