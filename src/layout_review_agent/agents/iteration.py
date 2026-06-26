from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from layout_review_agent.agents.base import Agent
from layout_review_agent.models import AgentRunContext, AuditSummary, Issue, utc_now


class IterationMemoryAgent(Agent[dict[str, Any]]):
    def __init__(self) -> None:
        super().__init__(
            agent_id="iteration_memory",
            description="Record recurring issues and produce iteration insights for rule and formatter improvement.",
        )

    def run(
        self,
        context: AgentRunContext,
        issues: list[Issue],
        summary: AuditSummary,
        safe_fix: dict[str, Any] | None = None,
        post_fix_summary: AuditSummary | None = None,
    ) -> dict[str, Any]:
        trace = context.start_trace(self.agent_id, "iteration_memory")
        context.output_dir.mkdir(parents=True, exist_ok=True)

        top_rules = Counter(issue.rule_id for issue in issues).most_common(10)
        top_categories = Counter(issue.category for issue in issues).most_common(10)
        top_fields = Counter(issue.field or "unknown" for issue in issues).most_common(10)
        issue_delta = None
        score_delta = None
        if post_fix_summary is not None:
            issue_delta = post_fix_summary.total_issues - summary.total_issues
            score_delta = post_fix_summary.score - summary.score

        insights = {
            "generated_at": utc_now(),
            "run_id": context.run_id,
            "document": str(context.input_path),
            "profile_id": context.profile_id,
            "score": summary.score,
            "total_issues": summary.total_issues,
            "manual_required_issues": summary.manual_required_issues,
            "auto_fixable_issues": summary.auto_fixable_issues,
            "safe_fixes_applied": len((safe_fix or {}).get("applied", [])),
            "safe_fixes_skipped": len((safe_fix or {}).get("skipped", [])),
            "post_fix_issue_delta": issue_delta,
            "post_fix_score_delta": score_delta,
            "top_rules": top_rules,
            "top_categories": top_categories,
            "top_fields": top_fields,
            "manual_required_examples": [
                issue.to_dict() for issue in issues if issue.status == "manual_required"
            ][:10],
            "next_iteration_actions": self._build_actions(summary, top_rules, top_categories, post_fix_summary),
        }

        insights_path = context.output_dir / "iteration_insights.json"
        insights_path.write_text(json.dumps(insights, ensure_ascii=False, indent=2), encoding="utf-8")
        context.shared.record_artifact("iteration_insights", str(insights_path))
        context.shared.record_metric("iteration_top_rules", top_rules)
        context.shared.observe(
            self.agent_id,
            "Iteration insights generated.",
            top_rules=top_rules[:3],
            top_categories=top_categories[:3],
        )

        if context.memory_path is not None:
            context.memory_path.parent.mkdir(parents=True, exist_ok=True)
            with context.memory_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(insights, ensure_ascii=False) + "\n")
            context.shared.record_artifact("long_term_memory", str(context.memory_path))

        trace.finish(
            "ok",
            "Iteration insights written.",
            top_rule_count=len(top_rules),
            memory_path=str(context.memory_path) if context.memory_path else "",
        )
        return insights

    def summarize_batch(self, output_dir: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
        top_rules: Counter[str] = Counter()
        top_categories: Counter[str] = Counter()
        total_issues = 0
        total_manual_required = 0
        for result in results:
            total_issues += result["summary"]["total_issues"]
            total_manual_required += result["summary"]["manual_required_issues"]
            for issue in result.get("issues", []):
                top_rules[issue["rule_id"]] += 1
                top_categories[issue["category"]] += 1

        insights = {
            "generated_at": utc_now(),
            "document_count": len(results),
            "total_issues": total_issues,
            "manual_required_issues": total_manual_required,
            "top_rules": top_rules.most_common(20),
            "top_categories": top_categories.most_common(20),
            "next_iteration_actions": self._build_batch_actions(top_rules, top_categories, total_manual_required),
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "batch_iteration_insights.json"
        path.write_text(json.dumps(insights, ensure_ascii=False, indent=2), encoding="utf-8")
        insights["path"] = str(path)
        return insights

    def _build_actions(
        self,
        summary: AuditSummary,
        top_rules: list[tuple[str, int]],
        top_categories: list[tuple[str, int]],
        post_fix_summary: AuditSummary | None,
    ) -> list[str]:
        actions: list[str] = []
        if top_rules:
            actions.append(f"优先复盘高频规则 {top_rules[0][0]}，确认是排版系统漏改还是规则配置过严。")
        if top_categories:
            actions.append(f"优先优化类别“{top_categories[0][0]}”的排版系统输出和样本文档覆盖。")
        if summary.manual_required_issues:
            actions.append("人工复核问题仍存在，后续可接入渲染校验或共享 LLM 解释辅助降低判断成本。")
        if post_fix_summary is not None and post_fix_summary.total_issues >= summary.total_issues:
            actions.append("安全修复后问题未下降，应检查修复字段映射或 DOCX 样式继承读取逻辑。")
        if not actions:
            actions.append("当前样本问题较少，可继续扩大真实稿件样本库以验证规则覆盖率。")
        return actions

    def _build_batch_actions(
        self,
        top_rules: Counter[str],
        top_categories: Counter[str],
        total_manual_required: int,
    ) -> list[str]:
        actions: list[str] = []
        if top_rules:
            rule_id, count = top_rules.most_common(1)[0]
            actions.append(f"批量最高频规则为 {rule_id}（{count} 次），建议优先反向优化自研排版系统。")
        if top_categories:
            category, count = top_categories.most_common(1)[0]
            actions.append(f"批量最高频问题类别为“{category}”（{count} 次），建议补充专项回归样本。")
        if total_manual_required:
            actions.append(f"批量仍有 {total_manual_required} 个需人工复核问题，建议纳入下一轮智能迭代重点。")
        if not actions:
            actions.append("批量样本未发现明显问题，可继续扩大样本集。")
        return actions
