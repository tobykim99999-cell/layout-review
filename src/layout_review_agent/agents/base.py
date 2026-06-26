from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from layout_review_agent.models import AgentRunContext

T = TypeVar("T")


class Agent(ABC, Generic[T]):
    agent_id: str
    description: str

    def __init__(self, agent_id: str, description: str) -> None:
        self.agent_id = agent_id
        self.description = description

    @abstractmethod
    def run(self, context: AgentRunContext, *args: object, **kwargs: object) -> T:
        """Run one deterministic agent step."""
