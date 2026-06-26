from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent
BUILTIN_RULES_DIR = PACKAGE_ROOT / "rules"


@dataclass(frozen=True)
class RuleProfile:
    profile_id: str
    display_name: str
    version: str
    source_path: Path
    raw: dict[str, Any]

    @property
    def rules(self) -> list[dict[str, Any]]:
        return list(self.raw.get("rules", []))

    @property
    def required_sections(self) -> list[dict[str, Any]]:
        return list(self.raw.get("required_sections", []))


def resolve_profile_path(profile: str, rules_dir: Path | None = None) -> Path:
    profile_path = Path(profile)
    if profile_path.suffix == ".json" and profile_path.exists():
        return profile_path

    candidates = []
    if rules_dir is not None:
        candidates.append(rules_dir / f"{profile}.json")
    candidates.append(BUILTIN_RULES_DIR / f"{profile}.json")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"Rule profile '{profile}' not found. Searched: {searched}")


def load_profile(profile: str = "default_undergraduate", rules_dir: str | Path | None = None) -> RuleProfile:
    rules_path = resolve_profile_path(profile, Path(rules_dir) if rules_dir else None)
    with rules_path.open("r", encoding="utf-8") as file:
        raw = json.load(file)
    errors = validate_profile_data(raw)
    if errors:
        joined = "; ".join(errors)
        raise ValueError(f"Invalid rule profile '{rules_path}': {joined}")
    return RuleProfile(
        profile_id=raw["profile_id"],
        display_name=raw.get("display_name", raw["profile_id"]),
        version=raw.get("version", "unknown"),
        source_path=rules_path,
        raw=raw,
    )


def validate_profile_data(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("profile_id", "display_name", "version"):
        if not raw.get(field):
            errors.append(f"missing required field: {field}")
    if not isinstance(raw.get("rules", []), list):
        errors.append("rules must be a list")
    if not isinstance(raw.get("required_sections", []), list):
        errors.append("required_sections must be a list")

    seen_rule_ids: set[str] = set()
    for index, rule in enumerate(raw.get("rules", [])):
        if not isinstance(rule, dict):
            errors.append(f"rules[{index}] must be an object")
            continue
        rule_id = rule.get("id")
        if not rule_id:
            errors.append(f"rules[{index}] missing id")
        elif rule_id in seen_rule_ids:
            errors.append(f"duplicate rule id: {rule_id}")
        else:
            seen_rule_ids.add(rule_id)
        if not isinstance(rule.get("selector"), dict):
            errors.append(f"rule {rule_id or index} selector must be an object")
        if not isinstance(rule.get("expected"), dict):
            errors.append(f"rule {rule_id or index} expected must be an object")
        if rule.get("status") not in {None, "auto_fixable", "manual_guided", "manual_required"}:
            errors.append(f"rule {rule_id or index} has invalid status")

    seen_section_ids: set[str] = set()
    for index, rule in enumerate(raw.get("required_sections", [])):
        if not isinstance(rule, dict):
            errors.append(f"required_sections[{index}] must be an object")
            continue
        section_id = rule.get("id")
        if not section_id:
            errors.append(f"required_sections[{index}] missing id")
        elif section_id in seen_section_ids:
            errors.append(f"duplicate required section id: {section_id}")
        else:
            seen_section_ids.add(section_id)
        if not rule.get("text_regex"):
            errors.append(f"required section {section_id or index} missing text_regex")
    return errors


def load_profile_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)
    errors = validate_profile_data(raw)
    return {
        "profile_id": raw.get("profile_id", path.stem),
        "display_name": raw.get("display_name", raw.get("profile_id", path.stem)),
        "version": raw.get("version", "unknown"),
        "source": str(path),
        "source_details": raw.get("source", {}),
        "valid": not errors,
        "errors": errors,
        "is_demo": bool(raw.get("is_demo", False)),
        "is_template": bool(raw.get("is_template", False)),
        "is_draft": bool(raw.get("is_draft", False)),
        "rule_count": len(raw.get("rules", [])) if isinstance(raw.get("rules", []), list) else 0,
        "required_section_count": len(raw.get("required_sections", []))
        if isinstance(raw.get("required_sections", []), list)
        else 0,
    }


def list_profiles(rules_dir: str | Path | None = None) -> list[dict[str, Any]]:
    paths: dict[str, Path] = {}
    for path in sorted(BUILTIN_RULES_DIR.glob("*.json")):
        paths[path.stem] = path
    if rules_dir is not None:
        custom_dir = Path(rules_dir)
        if custom_dir.exists():
            for path in sorted(custom_dir.glob("*.json")):
                paths[path.stem] = path

    profiles = [load_profile_file(path) for path in paths.values()]
    profiles.sort(key=lambda item: (item["is_template"], item["is_demo"], item["display_name"]))
    return profiles
