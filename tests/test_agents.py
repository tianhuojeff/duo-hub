import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from duohub.agents import (
    AgentDescriptor,
    AgentRegistry,
    AgentRequest,
    AntigravityCliAdapter,
    GeminiCliAdapter,
)


def descriptor(provider: str, model: str = "model-a") -> AgentDescriptor:
    return AgentDescriptor(
        id="gemini",
        display_name="Gemini",
        provider=provider,
        default_model=model,
        gateway_key="gemini",
    )


class FakeRunner:
    def __init__(self, completed: subprocess.CompletedProcess[str]):
        self.completed = completed
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return self.completed


class AgentRegistryTests(unittest.TestCase):
    def test_registry_exposes_enabled_default_agent(self):
        runner = FakeRunner(subprocess.CompletedProcess([], 0, "1.0\n", ""))
        adapter = AntigravityCliAdapter(
            descriptor=descriptor("antigravity-cli"),
            command="agy.exe",
            workspace=Path.cwd(),
            runner=runner,
        )
        registry = AgentRegistry()
        registry.register(adapter)
        self.assertEqual(registry.default_invoke_ids(), ("gemini",))
        public = registry.public_agents({"gemini_status": "idle", "gemini_model": "model-a"})
        self.assertEqual(public[0]["provider"], "antigravity-cli")

    def test_registry_rejects_duplicate_ids(self):
        runner = FakeRunner(subprocess.CompletedProcess([], 0, "1.0\n", ""))
        first = AntigravityCliAdapter(
            descriptor=descriptor("antigravity-cli"),
            command="agy.exe",
            workspace=Path.cwd(),
            runner=runner,
        )
        second = GeminiCliAdapter(
            descriptor=descriptor("gemini-cli"),
            command="gemini.cmd",
            workspace=Path.cwd(),
            runner=runner,
        )
        registry = AgentRegistry()
        registry.register(first)
        with self.assertRaises(ValueError):
            registry.register(second)


class CliAdapterTests(unittest.TestCase):
    def request(self) -> AgentRequest:
        return AgentRequest(prompt="ping", model="model-a", mode="task", timeout_seconds=30)

    def test_antigravity_success_parses_auditable_fields(self):
        payload = (
            '{"conversation_id":"c-1","status":"SUCCESS","response":"pong",'
            '"duration_seconds":1.2,"num_turns":1,"usage":{"total_tokens":12}}'
        )
        runner = FakeRunner(subprocess.CompletedProcess([], 0, payload, ""))
        adapter = AntigravityCliAdapter(
            descriptor=descriptor("antigravity-cli"),
            command="agy.exe",
            workspace=Path.cwd(),
            runner=runner,
        )
        result = adapter.invoke(self.request())
        self.assertEqual(result.status, "done")
        self.assertEqual(result.output, "pong")
        self.assertEqual(result.session_id, "c-1")
        self.assertEqual(result.usage["total_tokens"], 12)
        self.assertEqual(result.exit_code, 0)

    def test_gemini_auth_error_is_not_reported_as_success(self):
        payload = '{"session_id":"s-1","error":{"message":"auth required","code":41}}'
        runner = FakeRunner(subprocess.CompletedProcess([], 41, payload, ""))
        adapter = GeminiCliAdapter(
            descriptor=descriptor("gemini-cli"),
            command="gemini.cmd",
            workspace=Path.cwd(),
            runner=runner,
        )
        result = adapter.invoke(self.request())
        self.assertEqual(result.status, "error")
        self.assertEqual(result.exit_code, 41)
        self.assertEqual(result.error, "auth required")

    def test_cancel_terminates_provider_process_tree(self):
        adapter = AntigravityCliAdapter(
            descriptor=descriptor("antigravity-cli"),
            command=sys.executable,
            workspace=Path.cwd(),
        )
        completed = []

        def run_sleeper():
            completed.append(adapter._run(["-c", "import time; time.sleep(30)"], 30, "run-cancel"))

        thread = threading.Thread(target=run_sleeper)
        thread.start()
        deadline = time.time() + 5
        while adapter._process is None and time.time() < deadline:
            time.sleep(0.02)
        self.assertIsNotNone(adapter._process)
        adapter.cancel("run-cancel")
        thread.join(timeout=8)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(completed), 1)
        self.assertNotEqual(completed[0].returncode, 0)


if __name__ == "__main__":
    unittest.main()
