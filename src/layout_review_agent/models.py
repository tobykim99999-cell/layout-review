from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4


class SharedLLMService(Protocol):
    def complete(self, prompt: str) -> str:
        """Return a text completion for optional shared LLM assistance."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentTrace:
    agent_id: str
    action: str
    status: str
    message: str = ""
    started_at: str = dataclass_field(default_factory=utc_now)
    finished_at: str | None = None
    metrics: dict[str, Any] = dataclass_field(default_factory=dict)

    def finish(self, status: str = "ok", message: str = "", **metrics: Any) -> None:
        self.status = status
        self.message = message or self.message
        self.finished_at = utc_now()
        self.metrics.update(metrics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "action": self.action,
            "status": self.status,
            "message": self.message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "metrics": self.metrics,
        }


@dataclass
class SharedReviewState:
    artifacts: dict[str, Any] = dataclass_field(default_factory=dict)
    metrics: dict[str, Any] = dataclass_field(default_factory=dict)
    observations: list[dict[str, Any]] = dataclass_field(default_factory=list)
    decisions: list[dict[str, Any]] = dataclass_field(default_factory=list)

    def record_artifact(self, name: str, value: Any) -> None:
        self.artifacts[name] = value

    def record_metric(self, name: str, value: Any) -> None:
        self.metrics[name] = value

    def observe(self, agent_id: str, message: str, **data: Any) -> None:
        self.observations.append(
            {
                "agent_id": agent_id,
                "message": message,
                "data": data,
                "created_at": utc_now(),
            }
        )

    def decide(self, agent_id: str, decision: str, reason: str, **data: Any) -> None:
        self.decisions.append(
            {
                "agent_id": agent_id,
                "decision": decision,
                "reason": reason,
                "data": data,
                "created_at": utc_now(),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "observations": self.observations,
            "decisions": self.decisions,
        }


@dataclass
class AgentRunContext:
    input_path: Path
    output_dir: Path
    profile_id: str
    llm: SharedLLMService | None = None
    memory_path: Path | None = None
    run_id: str = dataclass_field(default_factory=lambda: uuid4().hex)
    traces: list[AgentTrace] = dataclass_field(default_factory=list)
    metadata: dict[str, Any] = dataclass_field(default_factory=dict)
    shared: SharedReviewState = dataclass_field(default_factory=SharedReviewState)

    def start_trace(self, agent_id: str, action: str) -> AgentTrace:
        trace = AgentTrace(agent_id=agent_id, action=action, status="running")
        self.traces.append(trace)
        return trace

    def traces_as_dicts(self) -> list[dict[str, Any]]:
        return [trace.to_dict() for trace in self.traces]


@dataclass
class DocumentElement:
    element_id: str
    element_type: str
    text: str
    location: dict[str, Any]
    style_name: str | None = None
    format: dict[str, Any] = dataclass_field(default_factory=dict)

    def preview(self, limit: int = 80) -> str:
        value = " ".join(self.text.split())
        return value[:limit]


@dataclass
class ParsedDocument:
    path: Path
    elements: list[DocumentElement]
    sections: list[DocumentElement]
    metadata: dict[str, Any]

    def all_elements(self) -> list[DocumentElement]:
        return [*self.sections, *self.elements]


@dataclass
class Issue:
    issue_id: str
    rule_id: str
    agent_id: str
    severity: str
    category: str
    status: str
    confidence: float
    message: str
    location: dict[str, Any]
    actual: Any
    expected: Any
    suggestion: str
    field: str | None = None
    fix_strategy: dict[str, Any] = dataclass_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "rule_id": self.rule_id,
            "agent_id": self.agent_id,
            "severity": self.severity,
            "category": self.category,
            "status": self.status,
            "confidence": self.confidence,
            "message": self.message,
            "location": self.location,
            "actual": self.actual,
            "expected": self.expected,
            "suggestion": self.suggestion,
            "field": self.field,
            "fix_strategy": self.fix_strategy,
        }


@dataclass
class AuditSummary:
    total_issues: int
    score: int
    by_severity: dict[str, int]
    by_status: dict[str, int]
    by_category: dict[str, int]
    severe_issues: int
    auto_fixable_issues: int
    manual_required_issues: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_issues": self.total_issues,
            "score": self.score,
            "by_severity": self.by_severity,
            "by_status": self.by_status,
            "by_category": self.by_category,
            "severe_issues": self.severe_issues,
            "auto_fixable_issues": self.auto_fixable_issues,
            "manual_required_issues": self.manual_required_issues,
        }
