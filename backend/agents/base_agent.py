"""Base class shared by all agents in the multi-agent system."""
from __future__ import annotations

from abc import ABC
from typing import Any

from core.logging_config import get_logger
from models.schemas import AgentResult
from services.llm_service import LLMService, get_llm


class BaseAgent(ABC):
    """Common plumbing: logging, LLM access, uniform result envelope."""

    name: str = "base"

    def __init__(self, llm: LLMService | None = None) -> None:
        self.llm = llm or get_llm()
        self.logger = get_logger(f"agent.{self.name}")

    def ok(self, detail: str = "", **data: Any) -> AgentResult:
        return AgentResult(agent=self.name, ok=True, detail=detail, data=data)

    def fail(self, detail: str, **data: Any) -> AgentResult:
        self.logger.warning("%s failed: %s", self.name, detail)
        return AgentResult(agent=self.name, ok=False, detail=detail, data=data)
