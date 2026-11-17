"""Logical Agent Registry used by the backend and dynamic UI."""

from __future__ import annotations

from typing import Any, Iterable

from .base import AgentAdapter


class AgentRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, AgentAdapter] = {}

    def register(self, adapter: AgentAdapter) -> None:
        agent_id = adapter.descriptor.id
        if not agent_id:
            raise ValueError("agent id must not be empty")
        if agent_id in self._adapters:
            raise ValueError(f"agent already registered: {agent_id}")
        self._adapters[agent_id] = adapter

    def get(self, agent_id: str) -> AgentAdapter:
        try:
            return self._adapters[agent_id]
        except KeyError as exc:
            raise KeyError(f"unknown agent: {agent_id}") from exc

    def enabled(self) -> Iterable[AgentAdapter]:
        return (
            adapter
            for adapter in self._adapters.values()
            if adapter.descriptor.enabled
        )

    def default_invoke_ids(self) -> tuple[str, ...]:
        return tuple(
            adapter.descriptor.id
            for adapter in self.enabled()
            if adapter.descriptor.invoke_by_default
        )

    def public_agents(self, session: dict[str, Any]) -> list[dict[str, Any]]:
        agents = []
        for adapter in self.enabled():
            item = adapter.descriptor.to_public()
            agent_id = adapter.descriptor.id
            item.update({
                "status": session.get(f"{agent_id}_status", "idle"),
                "model": session.get(f"{agent_id}_model", adapter.descriptor.default_model),
                "last_run": session.get(f"_{agent_id}_last_run", {}),
            })
            agents.append(item)
        return agents

    def health(self) -> dict[str, dict[str, Any]]:
        return {
            adapter.descriptor.id: adapter.health_check()
            for adapter in self.enabled()
        }

    def cancel_all(self, run_id: str = "") -> None:
        for adapter in self.enabled():
            adapter.cancel(run_id)
