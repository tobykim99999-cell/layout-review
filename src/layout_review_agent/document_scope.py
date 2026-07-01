from __future__ import annotations

import re
from typing import Any

from layout_review_agent.models import DocumentElement


def find_body_bounds_from_elements(elements: list[DocumentElement]) -> dict[str, int | None]:
    paragraphs: list[tuple[int, str]] = []
    for element in elements:
        if element.element_type != "paragraph" or element.location.get("scope") != "body":
            continue
        index = paragraph_index_from_element_id(element.element_id)
        if index is None:
            index = _safe_int(element.location.get("paragraph_index"))
        if index is None:
            continue
        paragraphs.append((index, element.text))
    return _find_body_bounds(sorted(paragraphs, key=lambda item: item[0]))


def find_body_bounds_from_paragraphs(paragraphs: list[Any]) -> dict[str, int | None]:
    return _find_body_bounds([(index, getattr(paragraph, "text", "")) for index, paragraph in enumerate(paragraphs)])


def find_reference_bounds_from_elements(elements: list[DocumentElement]) -> dict[str, int | None]:
    paragraphs: list[tuple[int, str]] = []
    for element in elements:
        if element.element_type != "paragraph" or element.location.get("scope") != "body":
            continue
        index = paragraph_index_from_element_id(element.element_id)
        if index is None:
            index = _safe_int(element.location.get("paragraph_index"))
        if index is None:
            continue
        paragraphs.append((index, element.text))
    return _find_reference_bounds(sorted(paragraphs, key=lambda item: item[0]))


def rule_targets_body_paragraph(rule: dict[str, Any]) -> bool:
    selector = rule.get("selector", {})
    if selector.get("element_type") and selector.get("element_type") != "paragraph":
        return False

    rule_id = str(rule.get("id", "")).lower().replace("_", "-")
    if rule_id in {"body", "body-text", "body-paragraph"} or "body-paragraph" in rule_id:
        return True

    text = " ".join(str(rule.get(key, "")) for key in ("category", "description"))
    lower_text = text.lower()
    if re.search(r"\bbody[-_\s]?(paragraph|text)\b", lower_text):
        return True
    if "正文" not in text:
        return False
    if any(marker in text for marker in ("标题", "题名", "目录", "摘要", "关键词", "参考文献", "致谢", "附录")):
        return False
    return any(marker in text for marker in ("段落", "文字", "文本", "格式", "字体", "字号", "行距", "缩进"))


def reference_rule_mode(rule: dict[str, Any]) -> str | None:
    selector = rule.get("selector", {})
    if selector.get("element_type") and selector.get("element_type") != "paragraph":
        return None

    rule_id = str(rule.get("id", "")).lower().replace("_", "-")
    text = " ".join(str(rule.get(key, "")) for key in ("category", "description"))
    lower_text = text.lower()
    is_reference_rule = (
        "reference" in rule_id
        or "references" in rule_id
        or "bibliography" in rule_id
        or "参考文献" in text
        or "文献列表" in text
    )
    if not is_reference_rule:
        return None
    if _expected_looks_like_heading(rule.get("expected", {})):
        return "heading"
    return "entry"


def rule_targets_caption(rule: dict[str, Any]) -> bool:
    selector = rule.get("selector", {})
    if selector.get("element_type") and selector.get("element_type") != "paragraph":
        return False
    rule_id = str(rule.get("id", "")).lower().replace("_", "-")
    text = " ".join(str(rule.get(key, "")) for key in ("category", "description"))
    return "caption" in rule_id or any(marker in text for marker in ("图题", "表题", "题注"))


def is_body_paragraph_element(element: DocumentElement, body_bounds: dict[str, int | None]) -> bool:
    if element.element_type != "paragraph" or element.location.get("scope") != "body":
        return False
    index = paragraph_index_from_element_id(element.element_id)
    if index is None:
        index = _safe_int(element.location.get("paragraph_index"))
    if not is_inside_body_bounds(index, body_bounds):
        return False

    text = element.text.strip()
    if looks_like_non_body_paragraph(text, element.style_name or ""):
        return False
    if _style_is_heading(element.style_name or ""):
        return False
    return True


def is_reference_paragraph_element(element: DocumentElement, reference_bounds: dict[str, int | None]) -> bool:
    if element.element_type != "paragraph" or element.location.get("scope") != "body":
        return False
    index = paragraph_index_from_element_id(element.element_id)
    if index is None:
        index = _safe_int(element.location.get("paragraph_index"))
    if not is_inside_body_bounds(index, reference_bounds):
        return False
    return looks_like_reference_entry(element.text)


def is_reference_heading_element(element: DocumentElement) -> bool:
    if element.element_type != "paragraph" or element.location.get("scope") != "body":
        return False
    return looks_like_reference_heading(element.text)


def is_caption_paragraph_element(element: DocumentElement, body_bounds: dict[str, int | None]) -> bool:
    if element.element_type != "paragraph" or element.location.get("scope") != "body":
        return False
    index = paragraph_index_from_element_id(element.element_id)
    if index is None:
        index = _safe_int(element.location.get("paragraph_index"))
    if body_bounds.get("start") is not None and not is_inside_body_bounds(index, body_bounds):
        return False
    return looks_like_caption_text(element.text)


def paragraph_index_from_element_id(element_id: str) -> int | None:
    if not element_id.startswith("p-"):
        return None
    try:
        return int(element_id.split("-", 1)[1])
    except ValueError:
        return None


def is_inside_body_bounds(index: int | None, body_bounds: dict[str, int | None]) -> bool:
    if index is None:
        return False
    start = body_bounds.get("start")
    if start is None or index <= start:
        return False
    end = body_bounds.get("end")
    return end is None or index < end


def looks_like_body_start_heading(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized or len(normalized) > 60:
        return False
    if looks_like_toc_entry(normalized):
        return False
    return bool(
        re.search(r"^第[一二三四五六七八九十百千万0-9]+章\s*\S+", normalized)
        or re.search(r"^[一二三四五六七八九十]+[、.．]\s*\S+", normalized)
        or re.search(r"^1(?:[.．、]|\s+)\s*\S+", normalized)
        or re.search(r"^(绪论|引言|前言)$", normalized, flags=re.IGNORECASE)
    )


def looks_like_body_end_heading(text: str) -> bool:
    normalized = _normalize_text(text)
    return bool(
        re.search(
            r"^(参考文献|致谢|附录|声明|作者简介|攻读学位期间|acknowledgements?|references?|bibliography|appendix)(?:\s|$|[:：])",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def looks_like_reference_heading(text: str) -> bool:
    return bool(re.search(r"^(参考文献|references?|bibliography)$", _normalize_text(text), flags=re.IGNORECASE))


def looks_like_reference_entry(text: str) -> bool:
    normalized = _normalize_text(text)
    return bool(
        re.search(r"^\[\d{1,3}\]\s*\S+", normalized)
        or re.search(r"^\d{1,3}[.)、]\s*\S+", normalized)
        or re.search(r"^\d{1,3}\s+[\u4e00-\u9fffA-Za-z]", normalized)
    )


def looks_like_caption_text(text: str) -> bool:
    normalized = _normalize_text(text)
    return bool(re.search(r"^(图|表)\s*\d+([-.]\d+)*\s+\S+", normalized))


def looks_like_non_body_paragraph(text: str, style_name: str = "") -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return True

    lower_style = style_name.lower()
    if "toc" in lower_style or "目录" in style_name:
        return True
    if looks_like_toc_entry(normalized):
        return True
    if _style_is_heading(style_name) and not looks_like_body_start_heading(normalized):
        return True
    if re.search(
        r"^(摘\s*要|abstract|关键词|key\s*words?|keywords|目\s*录|contents|参考文献|致谢|附录|"
        r"诚信承诺书|学生承诺|原创性声明|授权声明|任务书|开题报告|封面)",
        normalized,
        flags=re.IGNORECASE,
    ):
        return True
    if re.search(r"^(图|表)\s*\d+|^formula\s*\d+|^公式\s*\d+", normalized, flags=re.IGNORECASE):
        return True
    if re.search(r"^\s*\[?\d+\]?\s+[A-Za-z].+", normalized):
        return True
    if not re.search(r"[\u4e00-\u9fff]", normalized) and re.search(r"[A-Za-z]", normalized):
        return True
    return False


def looks_like_toc_entry(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return bool(
        re.search(r"(\.{3,}|…{2,}|·{3,}|_{3,})", normalized)
        or re.search(r"\s+\d+\s*$", normalized)
        and re.search(
            r"^(第[一二三四五六七八九十百千万0-9]+章|[0-9]+(?:\.[0-9]+)*|[一二三四五六七八九十]+[、.．])",
            normalized,
        )
    )


def _find_body_bounds(paragraphs: list[tuple[int, str]]) -> dict[str, int | None]:
    start = _find_body_start(paragraphs)
    end = _find_body_end(paragraphs, start)
    return {"start": start, "end": end}


def _find_reference_bounds(paragraphs: list[tuple[int, str]]) -> dict[str, int | None]:
    start = None
    for index, text in paragraphs:
        if looks_like_reference_heading(text):
            start = index
            break
    if start is None:
        return {"start": None, "end": None}
    end = None
    for index, text in paragraphs:
        if index <= start:
            continue
        if re.search(r"^(附录|致谢|声明|作者简介|攻读学位期间|appendix|acknowledgements?)", _normalize_text(text), flags=re.IGNORECASE):
            end = index
            break
    return {"start": start, "end": end}


def _find_body_start(paragraphs: list[tuple[int, str]]) -> int | None:
    toc_position = _find_first_matching_position(paragraphs, r"^目\s*录$|^contents$", 0)
    search_from = toc_position + 1 if toc_position is not None else 0
    for position in range(search_from, len(paragraphs)):
        index, text = paragraphs[position]
        if looks_like_toc_entry(text):
            continue
        if looks_like_body_start_heading(text):
            return index
    return None


def _find_body_end(paragraphs: list[tuple[int, str]], start: int | None) -> int | None:
    if start is None:
        return None
    for index, text in paragraphs:
        if index <= start:
            continue
        if looks_like_body_end_heading(text):
            return index
    return None


def _find_first_matching_position(paragraphs: list[tuple[int, str]], pattern: str, start: int) -> int | None:
    for position in range(start, len(paragraphs)):
        if re.search(pattern, paragraphs[position][1].strip(), flags=re.IGNORECASE):
            return position
    return None


def _style_is_heading(style_name: str) -> bool:
    return "heading" in style_name.lower() or "标题" in style_name


def _expected_looks_like_heading(expected: Any) -> bool:
    if not isinstance(expected, dict):
        return False
    font_size = expected.get("font_size_pt")
    try:
        large_font = font_size is not None and float(font_size) >= 14
    except (TypeError, ValueError):
        large_font = False
    return bool(expected.get("bold") is True or expected.get("alignment") == "center") and large_font


def _normalize_text(text: str) -> str:
    return " ".join(str(text).split())


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
