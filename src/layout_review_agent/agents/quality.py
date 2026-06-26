from __future__ import annotations

from typing import Any

from layout_review_agent.agents.base import Agent
from layout_review_agent.models import AgentRunContext, AuditSummary


class QualityGateAgent(Agent[dict[str, Any]]):
    def __init__(self) -> None:
        super().__init__(
            agent_id="quality_gate",
            description="Compare pre-fix and post-fix audits and flag residual risk.",
        )

    def run(
        self,
        context: AgentRunContext,
        before_summary: AuditSummary,
        after_summary: AuditSummary | None,
    ) -> dict[str, Any]:
        trace = context.start_trace(self.agent_id, "quality_gate")
        if after_summary is None:
            result = {
                "status": "not_run",
                "message": "Safe fix was not requested; post-fix audit skipped.",
                "issue_delta": None,
                "score_delta": None,
            }
        else:
            issue_delta = after_summary.total_issues - before_summary.total_issues
            score_delta = after_summary.score - before_summary.score
            status = "passed" if issue_delta <= 0 else "review_required"
            result = {
                "status": status,
                "message": "Post-fix audit completed.",
                "issue_delta": issue_delta,
                "score_delta": score_delta,
                "remaining_issues": after_summary.total_issues,
                "remaining_manual_required": after_summary.manual_required_issues,
                "remaining_auto_fixable": after_summary.auto_fixable_issues,
            }
        context.shared.record_artifact("quality_gate", result)
        context.shared.observe(
            self.agent_id,
            "Quality gate evaluated post-fix state.",
            status=result["status"],
        )
        trace.finish(
            result["status"],
            result["message"],
            **{k: v for k, v in result.items() if k not in {"status", "message"}},
        )
        return result
