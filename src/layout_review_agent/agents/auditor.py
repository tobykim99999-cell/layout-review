from __future__ import annotations

import re
from collections import Counter
from typing import Any
from uuid import uuid4

from layout_review_agent.agents.base import Agent
from layout_review_agent.models import AgentRunContext, AuditSummary, DocumentElement, Issue, ParsedDocument
from layout_review_agent.rules import RuleProfile


class RuleAuditorAgent(Agent[dict[str, Any]]):
    def __init__(self) -> None:
        super().__init__(
            agent_id="rule_auditor",
            description="Compare parsed DOCX facts with deterministic layout rules.",
        )

    def run(self, context: AgentRunContext, parsed: ParsedDocument, profile: RuleProfile) -> dict[str, Any]:
        trace = context.start_trace(self.agent_id, "audit_rules")
        issues: list[Issue] = []
        for rule in profile.rules:
            for element in parsed.all_elements():
                if self._matches_selector(element, rule.get("selector", {})):
                    issues.extend(self._audit_element(element, rule))

        issues.extend(self._audit_required_sections(parsed, profile))
        summary = self._summarize(issues)
        context.shared.record_metric("audit_total_issues", summary.total_issues)
        context.shared.record_metric("audit_score", summary.score)
        context.shared.record_metric("audit_manual_required", summary.manual_required_issues)
        context.shared.observe(
            self.agent_id,
            "Deterministic rules completed.",
            total_issues=summary.total_issues,
            score=summary.score,
        )
        trace.finish("ok", f"Found {len(issues)} issues.", issues=len(issues), score=summary.score)
        return {
            "profile": {
                "profile_id": profile.profile_id,
                "display_name": profile.display_name,
                "version": profile.version,
            },
            "issues": issues,
            "summary": summary,
        }

    def _matches_selector(self, element: DocumentElement, selector: dict[str, Any]) -> bool:
        if selector.get("element_type") and selector["element_type"] != element.element_type:
            return False
        if selector.get("exclude_empty") and not element.text.strip():
            return False
        if selector.get("min_chars") and len(element.text.strip()) < int(selector["min_chars"]):
            return False
        if selector.get("style_names") and element.style_name not in selector["style_names"]:
            return False
        if selector.get("style_name_contains"):
            style_name = element.style_name or ""
            if selector["style_name_contains"] not in style_name:
                return False
        if selector.get("text_regex") and not re.search(selector["text_regex"], element.text.strip()):
            return False
        for pattern in selector.get("text_regex_not", []):
            if re.search(pattern, element.text.strip()):
                return False
        return True

    def _audit_element(self, element: DocumentElement, rule: dict[str, Any]) -> list[Issue]:
        issues: list[Issue] = []
        expected = rule.get("expected", {})
        tolerance = float(rule.get("tolerance", 0.01))
        for field, expected_value in expected.items():
            actual_value = element.format.get(field)
            if self._values_equal(actual_value, expected_value, tolerance):
                continue
            safe_fix_fields = set(rule.get("safe_fix_fields") or [])
            field_auto_fix_allowed = bool(rule.get("auto_fix", False))
            if safe_fix_fields and field not in safe_fix_fields:
                field_auto_fix_allowed = False
            status = rule.get("status", "manual_guided") if field_auto_fix_allowed else "manual_guided"
            if not field_auto_fix_allowed:
                status = "manual_guided"
            fix_strategy = {}
            if status == "auto_fixable":
                fix_strategy = {
                    "agent_id": "safe_fixer",
                    "target": element.element_type,
                    "element_id": element.element_id,
                    "field": field,
                    "value": expected_value,
                    "allow_paragraph_fix": bool(rule.get("safe_paragraph_auto_fix", False)),
                    "safe_fix_fields": list(safe_fix_fields),
                }
            issues.append(
                Issue(
                    issue_id=uuid4().hex,
                    rule_id=rule["id"],
                    agent_id=self.agent_id,
                    severity=rule.get("severity", "minor"),
                    category=rule.get("category", "通用格式"),
                    status=status,
                    confidence=float(rule.get("confidence", 0.9)),
                    message=f"{rule.get('description', rule['id'])}: {field} 不符合规范",
                    location=element.location,
                    actual=actual_value,
                    expected=expected_value,
                    suggestion=rule.get("suggestion", "请按规则库标准修正。"),
                    field=field,
                    fix_strategy=fix_strategy,
                )
            )
        return issues

    def _audit_required_sections(self, parsed: ParsedDocument, profile: RuleProfile) -> list[Issue]:
        issues: list[Issue] = []
        texts = [element.text.strip() for element in parsed.elements if element.text.strip()]
        for rule in profile.required_sections:
            pattern = rule["text_regex"]
            if any(re.search(pattern, text) for text in texts):
                continue
            issues.append(
                Issue(
                    issue_id=uuid4().hex,
                    rule_id=rule["id"],
                    agent_id=self.agent_id,
                    severity=rule.get("severity", "major"),
                    category=rule.get("category", "结构完整性"),
                    status="manual_required",
                    confidence=0.99,
                    message=f"缺少必备模块：{rule.get('label', rule['id'])}",
                    location={"element_id": "document", "scope": "document", "preview": ""},
                    actual="missing",
                    expected=rule.get("label", pattern),
                    suggestion=rule.get("suggestion", "请补充必备论文模块。"),
                    field="required_section",
                    fix_strategy={},
                )
            )
        return issues

    def _values_equal(self, actual: Any, expected: Any, tolerance: float) -> bool:
        if isinstance(expected, bool):
            return actual is not None and bool(actual) == expected
        if isinstance(expected, (int, float)):
            if actual is None:
                return False
            try:
                return abs(float(actual) - float(expected)) <= tolerance
            except (TypeError, ValueError):
                return False
        return actual == expected

    def _summarize(self, issues: list[Issue]) -> AuditSummary:
        severity_counts = Counter(issue.severity for issue in issues)
        status_counts = Counter(issue.status for issue in issues)
        category_counts = Counter(issue.category for issue in issues)
        penalty = (
            severity_counts.get("critical", 0) * 12
            + severity_counts.get("major", 0) * 6
            + severity_counts.get("minor", 0) * 2
        )
        score = max(0, 100 - penalty)
        return AuditSummary(
            total_issues=len(issues),
            score=score,
            by_severity=dict(severity_counts),
            by_status=dict(status_counts),
            by_category=dict(category_counts),
            severe_issues=severity_counts.get("critical", 0) + severity_counts.get("major", 0),
            auto_fixable_issues=status_counts.get("auto_fixable", 0),
            manual_required_issues=status_counts.get("manual_required", 0),
        )
