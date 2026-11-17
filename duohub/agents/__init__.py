"""Agent adapters and registry for Duo Hub."""

from .base import AgentDescriptor, AgentRequest, AgentRunResult, ModelOption
from .gemini import AntigravityCliAdapter, GeminiCliAdapter
from .registry import AgentRegistry

__all__ = [
    "AgentDescriptor",
    "AgentRequest",
    "AgentRunResult",
    "AgentRegistry",
    "AntigravityCliAdapter",
    "GeminiCliAdapter",
    "ModelOption",
]
