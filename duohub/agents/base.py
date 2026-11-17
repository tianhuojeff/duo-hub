"""Shared contracts for logical agents and their concrete providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str

    def to_public(self) -> dict[str, str]:
        return {"id": self.id, "label": self.label}


@dataclass(frozen=True)
class AgentDescriptor:
    id: str
    display_name: str
    provider: str
    default_model: str
    models: Sequence[ModelOption] = field(default_factory=tuple)
    capabilities: Sequence[str] = field(default_factory=tuple)
    enabled: bool = True
    invoke_by_default: bool = True
    gateway_key: str = ""
    icon: str = "AI"
    color: str = "#38bdf8"

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.display_name,
            "provider": self.provider,
            "default_model": self.default_model,
            "models": [model.to_public() for model in self.models],
            "capabilities": list(self.capabilities),
            "enabled": self.enabled,
            "invoke_by_default": self.invoke_by_default,
            "gateway": self.gateway_key or self.id,
            "icon": self.icon,
            "color": self.color,
        }


@dataclass(frozen=True)
class AgentRequest:
    prompt: str
    model: str
    mode: str
    timeout_seconds: int
    recorded_by: str = "duo-hub"


@dataclass
class AgentRunResult:
    actor: str
    recorded_by: str
    provider: str
    model: str
    status: str
    output: str
    exit_code: int | None
    started_at: str
    ended_at: str
    duration_ms: int
    session_id: str = ""
    usage: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict)

    def metadata(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "recorded_by": self.recorded_by,
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "session_id": self.session_id,
            "usage": dict(self.usage),
            "error": self.error,
        }


class AgentAdapter(ABC):
    descriptor: AgentDescriptor

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return installation/availability facts without submitting a model task."""

    @abstractmethod
    def invoke(self, request: AgentRequest) -> AgentRunResult:
        """Run one visible agent turn and return auditable metadata."""
