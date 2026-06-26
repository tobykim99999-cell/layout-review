from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from layout_review_agent.agents import LayoutReviewCoordinator
from layout_review_agent.llm import LLMConfig, OpenAICompatibleLLMClient
from layout_review_agent.rules import list_profiles
from layout_review_agent.sample import create_bad_sample


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="layout-review",
        description="Multi-agent DOCX thesis layout review and safe-fix tool.",
    )
    parser.add_argument("--profile", default="default_undergraduate", help="Rule profile name or JSON file path.")
    parser.add_argument("--rules-dir", default=None, help="Optional custom rule profile directory.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="Audit one DOCX document.")
    audit.add_argument("input", help="Input .docx file.")
    audit.add_argument("--rules-dir", dest="command_rules_dir", default=None, help="Optional custom rule profile directory.")
    audit.add_argument("--out", default="reports", help="Output directory.")
    audit.add_argument("--fix-safe", action="store_true", help="Apply high-confidence deterministic fixes.")
    audit.add_argument("--llm-advice", action="store_true", help="Run optional advisory-only LLM extension point.")
    audit.add_argument("--llm-provider", default="", help="LLM provider name, e.g. openai-compatible.")
    audit.add_argument("--llm-base-url", default="", help="OpenAI-compatible chat completions base URL.")
    audit.add_argument("--llm-endpoint", default="", help="Deprecated alias for --llm-base-url.")
    audit.add_argument("--llm-api-key", default="", help="LLM API key. Defaults to LAYOUT_REVIEW_LLM_API_KEY.")
    audit.add_argument("--llm-model", default=None, help="LLM model name for advisory mode.")
    audit.add_argument("--llm-temperature", type=float, default=0.2, help="LLM temperature.")
    audit.add_argument("--llm-max-tokens", type=int, default=1000, help="LLM max tokens.")
    audit.add_argument("--memory-file", default=None, help="Optional JSONL file for long-term iteration memory.")

    batch = subparsers.add_parser("batch", help="Audit all DOCX files in one directory.")
    batch.add_argument("input_dir", help="Directory containing .docx files.")
    batch.add_argument("--rules-dir", dest="command_rules_dir", default=None, help="Optional custom rule profile directory.")
    batch.add_argument("--out", default="batch_reports", help="Output directory.")
    batch.add_argument("--fix-safe", action="store_true", help="Apply high-confidence deterministic fixes.")
    batch.add_argument("--llm-advice", action="store_true", help="Run optional advisory-only LLM extension point.")
    batch.add_argument("--llm-provider", default="", help="LLM provider name, e.g. openai-compatible.")
    batch.add_argument("--llm-base-url", default="", help="OpenAI-compatible chat completions base URL.")
    batch.add_argument("--llm-endpoint", default="", help="Deprecated alias for --llm-base-url.")
    batch.add_argument("--llm-api-key", default="", help="LLM API key. Defaults to LAYOUT_REVIEW_LLM_API_KEY.")
    batch.add_argument("--llm-model", default=None, help="LLM model name for advisory mode.")
    batch.add_argument("--llm-temperature", type=float, default=0.2, help="LLM temperature.")
    batch.add_argument("--llm-max-tokens", type=int, default=1000, help="LLM max tokens.")
    batch.add_argument("--memory-file", default=None, help="Optional JSONL file for long-term iteration memory.")

    sample = subparsers.add_parser("sample", help="Create a sample invalid thesis DOCX.")
    sample.add_argument("out", help="Output directory for sample document.")

    profiles = subparsers.add_parser("profiles", help="List available rule profiles.")
    profiles.add_argument("--rules-dir", dest="command_rules_dir", default=None, help="Optional custom rule profile directory.")
    profiles.add_argument("--json", action="store_true", help="Output rule profiles as JSON.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "sample":
        path = create_bad_sample(args.out)
        print(f"Sample written: {path}")
        return 0

    effective_rules_dir = getattr(args, "command_rules_dir", None) or args.rules_dir

    if args.command == "profiles":
        profiles = list_profiles(effective_rules_dir)
        if args.json:
            print(json.dumps(profiles, ensure_ascii=False, indent=2))
        else:
            for profile in profiles:
                flags = []
                if profile.get("is_demo"):
                    flags.append("demo")
                if profile.get("is_template"):
                    flags.append("template")
                if not profile.get("valid"):
                    flags.append("invalid")
                suffix = f" [{' '.join(flags)}]" if flags else ""
                print(f"{profile['profile_id']} - {profile['display_name']} / {profile['version']}{suffix}")
                if profile.get("errors"):
                    for error in profile["errors"]:
                        print(f"  - {error}")
        return 0

    llm_client = None
    base_url = (
        getattr(args, "llm_base_url", "")
        or getattr(args, "llm_endpoint", "")
        or os.environ.get("LAYOUT_REVIEW_LLM_BASE_URL", "")
    )
    if base_url:
        api_key = getattr(args, "llm_api_key", "") or os.environ.get("LAYOUT_REVIEW_LLM_API_KEY", "")
        if not api_key:
            parser.error("Set --llm-api-key or LAYOUT_REVIEW_LLM_API_KEY when using --llm-base-url.")
        config = LLMConfig(
            provider=getattr(args, "llm_provider", "") or os.environ.get("LAYOUT_REVIEW_LLM_PROVIDER", "openai-compatible"),
            base_url=base_url,
            api_key=api_key,
            model=args.llm_model or os.environ.get("LAYOUT_REVIEW_LLM_MODEL", "gpt-4.1-mini"),
            temperature=args.llm_temperature,
            max_tokens=args.llm_max_tokens,
        )
        llm_client = OpenAICompatibleLLMClient(config=config)

    coordinator = LayoutReviewCoordinator(
        profile=args.profile,
        rules_dir=effective_rules_dir,
        llm_client=llm_client,
        memory_path=getattr(args, "memory_file", None),
    )

    if args.command == "audit":
        result = coordinator.audit(args.input, args.out, fix_safe=args.fix_safe, llm_advice=args.llm_advice)
        print(json.dumps({"summary": result["summary"], "reports": result["reports"]}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "batch":
        result = coordinator.batch(Path(args.input_dir), Path(args.out), fix_safe=args.fix_safe, llm_advice=args.llm_advice)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
