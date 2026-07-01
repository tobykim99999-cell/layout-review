from __future__ import annotations

import re
from typing import Any

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

ALIGNMENT_TO_NAME = {
    WD_ALIGN_PARAGRAPH.LEFT: "left",
    WD_ALIGN_PARAGRAPH.CENTER: "center",
    WD_ALIGN_PARAGRAPH.RIGHT: "right",
    WD_ALIGN_PARAGRAPH.JUSTIFY: "justify",
}

NAME_TO_ALIGNMENT = {value: key for key, value in ALIGNMENT_TO_NAME.items()}


def length_to_cm(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value.cm), 2)


def length_to_pt(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value.pt), 2)


def normalize_float(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def get_run_font_name(run: Any, prefer_east_asia: bool = False) -> str | None:
    r_pr = run._element.rPr
    east_asia = None
    if r_pr is not None and r_pr.rFonts is not None:
        east_asia = r_pr.rFonts.get(qn("w:eastAsia"))
    if prefer_east_asia and east_asia:
        return east_asia
    if run.font.name:
        return run.font.name
    if east_asia:
        return east_asia
    return None


def get_style_font_name(style: Any, prefer_east_asia: bool = False) -> str | None:
    if style is None:
        return None
    element = getattr(style, "element", None)
    east_asia = None
    if element is not None and element.rPr is not None and element.rPr.rFonts is not None:
        east_asia = element.rPr.rFonts.get(qn("w:eastAsia"))
    if prefer_east_asia and east_asia:
        return east_asia
    if getattr(style, "font", None) is not None and style.font.name:
        return style.font.name
    if east_asia:
        return east_asia
    return None


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def get_paragraph_font_name(paragraph: Any) -> str | None:
    prefer_east_asia = contains_cjk(paragraph.text)
    for run in paragraph.runs:
        if run.text.strip():
            name = get_run_font_name(run, prefer_east_asia=prefer_east_asia and contains_cjk(run.text))
            if name:
                return name
    return get_style_font_name(paragraph.style, prefer_east_asia=prefer_east_asia)


def get_style_font_size(style: Any) -> float | None:
    if style is None:
        return None
    if getattr(style, "font", None) is not None and style.font.size is not None:
        return length_to_pt(style.font.size)
    element = getattr(style, "element", None)
    if element is None:
        return None
    r_pr = element.rPr
    if r_pr is not None and r_pr.sz is not None and r_pr.sz.val is not None:
        return round(float(r_pr.sz.val) / 2, 2)
    return None


def get_paragraph_font_size(paragraph: Any) -> float | None:
    for run in paragraph.runs:
        if run.text.strip() and run.font.size is not None:
            return length_to_pt(run.font.size)
    return get_style_font_size(paragraph.style)


def get_paragraph_bool(paragraph: Any, attr: str) -> bool | None:
    for run in paragraph.runs:
        if run.text.strip():
            value = getattr(run.font, attr)
            if value is not None:
                return bool(value)
    if paragraph.style is not None:
        value = getattr(paragraph.style.font, attr)
        if value is not None:
            return bool(value)
    return None


def get_paragraph_format(paragraph: Any) -> dict[str, Any]:
    paragraph_format = paragraph.paragraph_format
    alignment = paragraph.alignment
    if alignment is None and paragraph.style is not None:
        alignment = paragraph.style.paragraph_format.alignment
    line_spacing = paragraph_format.line_spacing
    if line_spacing is None and paragraph.style is not None:
        line_spacing = paragraph.style.paragraph_format.line_spacing
    first_line_indent = paragraph_format.first_line_indent
    if first_line_indent is None and paragraph.style is not None:
        first_line_indent = paragraph.style.paragraph_format.first_line_indent
    space_before = paragraph_format.space_before
    if space_before is None and paragraph.style is not None:
        space_before = paragraph.style.paragraph_format.space_before
    space_after = paragraph_format.space_after
    if space_after is None and paragraph.style is not None:
        space_after = paragraph.style.paragraph_format.space_after

    return {
        "font_name": get_paragraph_font_name(paragraph),
        "font_size_pt": get_paragraph_font_size(paragraph),
        "bold": get_paragraph_bool(paragraph, "bold"),
        "italic": get_paragraph_bool(paragraph, "italic"),
        "alignment": ALIGNMENT_TO_NAME.get(alignment),
        "line_spacing": normalize_float(line_spacing),
        "first_line_indent_cm": length_to_cm(first_line_indent),
        "space_before_pt": length_to_pt(space_before),
        "space_after_pt": length_to_pt(space_after),
    }


def set_run_font_name(run: Any, font_name: str) -> None:
    run.font.name = font_name
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.get_or_add_rFonts()
    r_fonts.set(qn("w:eastAsia"), font_name)


def apply_font_to_paragraph(paragraph: Any, field: str, value: Any) -> None:
    runs = paragraph.runs
    if not runs:
        runs = [paragraph.add_run("")]
    for run in runs:
        if field == "font_name":
            set_run_font_name(run, str(value))
        elif field == "font_size_pt":
            run.font.size = Pt(float(value))
        elif field == "bold":
            run.font.bold = bool(value)
        elif field == "italic":
            run.font.italic = bool(value)


def apply_paragraph_field(paragraph: Any, field: str, value: Any) -> bool:
    if field in {"font_name", "font_size_pt", "bold", "italic"}:
        apply_font_to_paragraph(paragraph, field, value)
        return True
    if field == "alignment":
        paragraph.alignment = NAME_TO_ALIGNMENT.get(str(value))
        return paragraph.alignment is not None
    if field == "line_spacing":
        paragraph.paragraph_format.line_spacing = float(value)
        return True
    if field == "first_line_indent_cm":
        paragraph.paragraph_format.first_line_indent = Cm(float(value))
        return True
    if field == "space_before_pt":
        paragraph.paragraph_format.space_before = Pt(float(value))
        return True
    if field == "space_after_pt":
        paragraph.paragraph_format.space_after = Pt(float(value))
        return True
    return False


def apply_section_field(section: Any, field: str, value: Any) -> bool:
    if field == "page_width_cm":
        section.page_width = Cm(float(value))
        return True
    if field == "page_height_cm":
        section.page_height = Cm(float(value))
        return True
    if field == "top_margin_cm":
        section.top_margin = Cm(float(value))
        return True
    if field == "bottom_margin_cm":
        section.bottom_margin = Cm(float(value))
        return True
    if field == "left_margin_cm":
        section.left_margin = Cm(float(value))
        return True
    if field == "right_margin_cm":
        section.right_margin = Cm(float(value))
        return True
    return False
