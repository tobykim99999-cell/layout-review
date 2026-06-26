from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from docx import Document

from layout_review_agent.agents.base import Agent
from layout_review_agent.docx_format import apply_paragraph_field, apply_section_field
from layout_review_agent.models import AgentRunContext, Issue


class SafeFixerAgent(Agent[dict[str, Any]]):
    DEFAULT_SAFE_PARAGRAPH_FIELDS = {
        "line_spacing",
        "first_line_indent_cm",
        "space_before_pt",
        "space_after_pt",
    }

    def __init__(self, confidence_threshold: float = 0.94) -> None:
        super().__init__(
            agent_id="safe_fixer",
            description="Apply only high-confidence deterministic DOCX formatting fixes.",
        )
        self.confidence_threshold = confidence_threshold

    def run(self, context: AgentRunContext, issues: list[Issue], fixed_path: Path) -> dict[str, Any]:
        trace = context.start_trace(self.agent_id, "safe_fix")
        fixed_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(context.input_path, fixed_path)
        document = Document(str(fixed_path))
        body_bounds = self._find_body_bounds(document)

        applied: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for issue in issues:
            if issue.status != "auto_fixable" or issue.confidence < self.confidence_threshold:
                skipped.append({"issue_id": issue.issue_id, "reason": "not_auto_fixable_or_low_confidence"})
                continue
            strategy = issue.fix_strategy
            target = strategy.get("target")
            element_id = strategy.get("element_id", "")
            field = strategy.get("field")
            value = strategy.get("value")
            ok = False
            if target == "paragraph" and field:
                if not strategy.get("allow_paragraph_fix", False):
                    record = {
                        "issue_id": issue.issue_id,
                        "rule_id": issue.rule_id,
                        "element_id": element_id,
                        "field": field,
                        "value": value,
                        "reason": "paragraph_auto_fix_requires_explicit_safe_paragraph_auto_fix",
                    }
                    skipped.append(record)
                    continue
                safe_fields = set(strategy.get("safe_fix_fields") or self.DEFAULT_SAFE_PARAGRAPH_FIELDS)
                if field not in safe_fields:
                    skipped.append(
                        {
                            "issue_id": issue.issue_id,
                            "rule_id": issue.rule_id,
                            "element_id": element_id,
                            "field": field,
                            "value": value,
                            "reason": "paragraph_field_not_in_safe_fix_fields",
                        }
                    )
                    continue
                if element_id.startswith("table-"):
                    skipped.append(
                        {
                            "issue_id": issue.issue_id,
                            "rule_id": issue.rule_id,
                            "element_id": element_id,
                            "field": field,
                            "value": value,
                            "reason": "table_paragraph_auto_fix_skipped",
                        }
                    )
                    continue
                paragraph = self._resolve_paragraph(document, element_id)
                if paragraph is not None:
                    if self._paragraph_is_safe_for_auto_fix(paragraph, issue.rule_id, element_id, body_bounds):
                        ok = apply_paragraph_field(paragraph, field, value)
                    else:
                        skipped.append(
                            {
                                "issue_id": issue.issue_id,
                                "rule_id": issue.rule_id,
                                "element_id": element_id,
                                "field": field,
                                "value": value,
                                "reason": "paragraph_shape_not_safe_for_auto_fix",
                            }
                        )
                        continue
            elif target == "section" and field:
                section = self._resolve_section(document, element_id)
                if section is not None:
                    ok = apply_section_field(section, field, value)

            record = {
                "issue_id": issue.issue_id,
                "rule_id": issue.rule_id,
                "element_id": element_id,
                "field": field,
                "value": value,
            }
            if ok:
                applied.append(record)
            else:
                record["reason"] = "target_not_found_or_field_not_supported"
                skipped.append(record)

        document.save(str(fixed_path))
        context.shared.record_artifact("fixed_docx", str(fixed_path))
        context.shared.record_metric("safe_fixes_applied", len(applied))
        context.shared.record_metric("safe_fixes_skipped", len(skipped))
        context.shared.decide(
            self.agent_id,
            "apply_safe_fixes",
            "Only auto_fixable issues above the confidence threshold were modified.",
            confidence_threshold=self.confidence_threshold,
            applied=len(applied),
            skipped=len(skipped),
        )
        trace.finish(
            "ok",
            f"Applied {len(applied)} safe fixes.",
            applied=len(applied),
            skipped=len(skipped),
            fixed_path=str(fixed_path),
        )
        return {
            "fixed_path": fixed_path,
            "applied": applied,
            "skipped": skipped,
            "body_bounds": body_bounds,
        }

    def _resolve_paragraph(self, document: Any, element_id: str) -> Any | None:
        if element_id.startswith("p-"):
            index = int(element_id.split("-", 1)[1])
            if 0 <= index < len(document.paragraphs):
                return document.paragraphs[index]
            return None
        if element_id.startswith("table-"):
            parts = element_id.split("-")
            if len(parts) != 5:
                return None
            table_index = int(parts[1])
            row_index = int(parts[2][1:])
            cell_index = int(parts[3][1:])
            paragraph_index = int(parts[4][1:])
            try:
                return document.tables[table_index].rows[row_index].cells[cell_index].paragraphs[paragraph_index]
            except IndexError:
                return None
        return None

    def _paragraph_is_safe_for_auto_fix(
        self,
        paragraph: Any,
        rule_id: str,
        element_id: str,
        body_bounds: dict[str, int | None],
    ) -> bool:
        text = paragraph.text.strip()
        if len(text) < 8:
            return False
        style_name = paragraph.style.name if paragraph.style is not None else ""
        if rule_id == "body-paragraph":
            index = self._paragraph_index(element_id)
            if not self._is_inside_body_bounds(index, body_bounds):
                return False
            if self._looks_like_non_body_paragraph(text, style_name):
                return False
            if "Heading" in style_name or "标题" in style_name:
                return False
            if str(paragraph.alignment) in {"CENTER (1)", "RIGHT (2)"}:
                return False
        for run in paragraph.runs:
            if not run.text.strip() or run.font.size is None:
                continue
            if run.font.size.pt and run.font.size.pt > 18:
                return False
        return True

    def _find_body_bounds(self, document: Any) -> dict[str, int | None]:
        paragraphs = list(document.paragraphs)
        start = self._find_body_start(paragraphs)
        end = self._find_body_end(paragraphs, start)
        return {"start": start, "end": end}

    def _find_body_start(self, paragraphs: list[Any]) -> int | None:
        toc_index = self._find_first_matching_index(paragraphs, r"^目\s*录$|^contents$", 0)
        search_from = toc_index + 1 if toc_index is not None else 0
        for index in range(search_from, len(paragraphs)):
            text = paragraphs[index].text.strip()
            if self._looks_like_toc_entry(text):
                continue
            if self._looks_like_body_start_heading(text):
                return index
        return None

    def _find_body_end(self, paragraphs: list[Any], start: int | None) -> int | None:
        if start is None:
            return None
        for index in range(start + 1, len(paragraphs)):
            text = paragraphs[index].text.strip()
            if re.search(r"^(参考文献|致谢|附录|声明|作者简介|攻读学位期间)", text, flags=re.IGNORECASE):
                return index
        return None

    def _find_first_matching_index(self, paragraphs: list[Any], pattern: str, start: int) -> int | None:
        for index in range(start, len(paragraphs)):
            if re.search(pattern, paragraphs[index].text.strip(), flags=re.IGNORECASE):
                return index
        return None

    def _paragraph_index(self, element_id: str) -> int | None:
        if not element_id.startswith("p-"):
            return None
        try:
            return int(element_id.split("-", 1)[1])
        except ValueError:
            return None

    def _is_inside_body_bounds(self, index: int | None, body_bounds: dict[str, int | None]) -> bool:
        if index is None:
            return False
        start = body_bounds.get("start")
        if start is None or index <= start:
            return False
        end = body_bounds.get("end")
        return end is None or index < end

    def _looks_like_body_start_heading(self, text: str) -> bool:
        normalized = " ".join(text.split())
        if not normalized:
            return False
        if self._looks_like_toc_entry(normalized):
            return False
        return bool(
            re.search(r"^第[一二三四五六七八九十0-9]+章\s*\S+", normalized)
            or re.search(r"^[一二三四五六七八九十]+[、.．]\s*\S+", normalized)
            or re.search(r"^1(?:[.．、]|\s+)\s*\S+", normalized)
            or re.search(r"^(绪论|引言|前言)$", normalized)
        )

    def _looks_like_non_body_paragraph(self, text: str, style_name: str) -> bool:
        normalized = " ".join(text.split())
        lower_style = style_name.lower()
        if "toc" in lower_style or "目录" in style_name:
            return True
        if self._looks_like_toc_entry(normalized):
            return True
        if re.search(
            r"^(摘\s*要|abstract|关键词|key\s*words?|keywords|目\s*录|contents|参考文献|致谢|附录)",
            normalized,
            flags=re.IGNORECASE,
        ):
            return True
        if re.search(r"^(图|表)\s*\d+|^formula\s*\d+", normalized, flags=re.IGNORECASE):
            return True
        if re.search(r"^\s*\[?\d+\]?\s+[A-Za-z].+", normalized):
            return True
        if not re.search(r"[\u4e00-\u9fff]", normalized) and re.search(r"[A-Za-z]", normalized):
            return True
        return False

    def _looks_like_toc_entry(self, text: str) -> bool:
        normalized = text.strip()
        if not normalized:
            return False
        return bool(
            re.search(r"(\.{3,}|…{2,}|·{3,}|_{3,})", normalized)
            or re.search(r"\s+\d+\s*$", normalized)
            and re.search(r"^(第[一二三四五六七八九十0-9]+章|[0-9]+(?:\.[0-9]+)*|[一二三四五六七八九十]+[、.．])", normalized)
        )

    def _resolve_section(self, document: Any, element_id: str) -> Any | None:
        if not element_id.startswith("section-"):
            return None
        index = int(element_id.split("-", 1)[1])
        if 0 <= index < len(document.sections):
            return document.sections[index]
        return None
