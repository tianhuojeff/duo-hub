"""Gemini logical-seat providers for Google Gemini CLI and Antigravity CLI."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .base import AgentAdapter, AgentDescriptor, AgentRequest, AgentRunResult, ModelOption


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _command_parts(command: str) -> list[str]:
    path = Path(command)
    suffix = path.suffix.lower()
    if suffix == ".ps1":
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    if suffix in (".cmd", ".bat"):
        return ["cmd.exe", "/d", "/s", "/c", str(path)]
    return [str(path)]


def _parse_json(stdout: str) -> Mapping[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start:end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


class _CliAdapter(AgentAdapter):
    def __init__(
        self,
        *,
        descriptor: AgentDescriptor,
        command: str,
        workspace: Path,
        env: Mapping[str, str] | None = None,
        runner: Runner = subprocess.run,
    ) -> None:
        self.descriptor = descriptor
        self.command = command
        self.workspace = workspace
        self.env = dict(env or os.environ)
        self.runner = runner

    def _run(self, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        return self.runner(
            _command_parts(self.command) + args,
            cwd=str(self.workspace),
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=flags,
        )

    def health_check(self) -> dict[str, Any]:
        try:
            result = self._run(["--version"], 8)
            return {
                "available": result.returncode == 0,
                "provider": self.descriptor.provider,
                "version": (result.stdout or result.stderr or "").strip(),
                "exit_code": result.returncode,
            }
        except Exception as exc:
            return {
                "available": False,
                "provider": self.descriptor.provider,
                "version": "",
                "error": str(exc),
            }

    def _result(
        self,
        *,
        request: AgentRequest,
        result: subprocess.CompletedProcess[str],
        payload: Mapping[str, Any],
        started_at: str,
        started_clock: float,
        success: bool,
        output: str,
        error: str,
        usage: Mapping[str, Any],
        session_id: str,
    ) -> AgentRunResult:
        return AgentRunResult(
            actor=self.descriptor.id,
            recorded_by=request.recorded_by,
            provider=self.descriptor.provider,
            model=request.model or self.descriptor.default_model,
            status="done" if success else "error",
            output=output,
            exit_code=result.returncode,
            started_at=started_at,
            ended_at=_now(),
            duration_ms=round((time.perf_counter() - started_clock) * 1000),
            session_id=session_id,
            usage=usage,
            error=error,
            raw=payload,
        )


class AntigravityCliAdapter(_CliAdapter):
    """Run the Gemini seat through the authenticated local Antigravity CLI."""

    MODELS = (
        ModelOption("gemini-4-hydrogen-medium", "Gemini 4 Hydrogen Medium"),
        ModelOption("gemini-4-argon-medium", "Gemini 4 Argon Medium"),
        ModelOption("gemini-3.8-flash-medium", "Gemini 3.8 Flash Medium"),
    )

    def invoke(self, request: AgentRequest) -> AgentRunResult:
        started_at = _now()
        started_clock = time.perf_counter()
        timeout = max(1, request.timeout_seconds)
        args = [
            "--print", request.prompt,
            "--output-format", "json",
            "--mode", "plan",
            "--model", request.model or self.descriptor.default_model,
            "--print-timeout", f"{timeout}s",
        ]
        try:
            result = self._run(args, timeout + 10)
        except subprocess.TimeoutExpired:
            return AgentRunResult(
                actor=self.descriptor.id,
                recorded_by=request.recorded_by,
                provider=self.descriptor.provider,
                model=request.model or self.descriptor.default_model,
                status="timeout",
                output="",
                exit_code=None,
                started_at=started_at,
                ended_at=_now(),
                duration_ms=round((time.perf_counter() - started_clock) * 1000),
                error=f"Antigravity CLI timed out after {timeout} seconds",
            )
        payload = _parse_json(result.stdout)
        status = str(payload.get("status", "")).upper()
        output = str(payload.get("response", "") or "").strip()
        error = str(payload.get("error", "") or "").strip()
        if result.returncode != 0 and not error:
            error = (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
        success = result.returncode == 0 and status == "SUCCESS" and bool(output)
        if not success and not error:
            error = "Antigravity CLI returned no successful response"
        return self._result(
            request=request,
            result=result,
            payload=payload,
            started_at=started_at,
            started_clock=started_clock,
            success=success,
            output=output,
            error=error,
            usage=payload.get("usage", {}) if isinstance(payload.get("usage"), dict) else {},
            session_id=str(payload.get("conversation_id", "") or ""),
        )


class GeminiCliAdapter(_CliAdapter):
    """Run the Gemini seat through Google's Gemini CLI headless JSON mode."""

    MODELS = (
        ModelOption("auto", "Gemini CLI Auto"),
        ModelOption("gemini-3.5-flash", "Gemini 3.5 Flash"),
        ModelOption("gemini-2.5-pro", "Gemini 2.5 Pro"),
    )

    def invoke(self, request: AgentRequest) -> AgentRunResult:
        started_at = _now()
        started_clock = time.perf_counter()
        timeout = max(1, request.timeout_seconds)
        args = [
            "-p", request.prompt,
            "--output-format", "json",
            "--approval-mode", "plan",
            "--skip-trust",
            "--model", request.model or self.descriptor.default_model,
        ]
        try:
            result = self._run(args, timeout)
        except subprocess.TimeoutExpired:
            return AgentRunResult(
                actor=self.descriptor.id,
                recorded_by=request.recorded_by,
                provider=self.descriptor.provider,
                model=request.model or self.descriptor.default_model,
                status="timeout",
                output="",
                exit_code=None,
                started_at=started_at,
                ended_at=_now(),
                duration_ms=round((time.perf_counter() - started_clock) * 1000),
                error=f"Gemini CLI timed out after {timeout} seconds",
            )
        payload = _parse_json(result.stdout)
        output = str(payload.get("response", "") or "").strip()
        payload_error = payload.get("error", {})
        if isinstance(payload_error, dict):
            error = str(payload_error.get("message", "") or "").strip()
        else:
            error = str(payload_error or "").strip()
        if result.returncode != 0 and not error:
            error = (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
        success = result.returncode == 0 and bool(output) and not error
        if not success and not error:
            error = "Gemini CLI returned no response"
        return self._result(
            request=request,
            result=result,
            payload=payload,
            started_at=started_at,
            started_clock=started_clock,
            success=success,
            output=output,
            error=error,
            usage=payload.get("stats", {}) if isinstance(payload.get("stats"), dict) else {},
            session_id=str(payload.get("session_id", "") or ""),
        )
