from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from layout_review_agent.agents.auditor import RuleAuditorAgent
from layout_review_agent.agents.fixer import SafeFixerAgent
from layout_review_agent.agents.iteration import IterationMemoryAgent
from layout_review_agent.agents.parser import DocumentParserAgent
from layout_review_agent.agents.quality import QualityGateAgent
from layout_review_agent.agents.reporter import ReportWriterAgent
from layout_review_agent.llm import LLMClient
from layout_review_agent.models import AgentRunContext, AuditSummary, Issue, utc_now
from layout_review_agent.rules import load_profile


class LayoutReviewCoordinator:
    def __init__(
        self,
        profile: str = "default_undergraduate",
        rules_dir: str | Path | None = None,
        llm_client: LLMClient | None = None,
        memory_path: str | Path | None = None,
    ) -> None:
        self.profile = load_profile(profile, rules_dir)
        self.parser = DocumentParserAgent()
        self.auditor = RuleAuditorAgent()
        self.fixer = SafeFixerAgent()
        self.quality_gate = QualityGateAgent()
        self.iteration_memory = IterationMemoryAgent()
        self.reporter = ReportWriterAgent()
        self.llm_client = llm_client
        self.memory_path = Path(memory_path).resolve() if memory_path else None

    def audit(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        fix_safe: bool = False,
        llm_advice: bool = False,
    ) -> dict[str, Any]:
        input_path = Path(input_path).resolve()
        output_dir = Path(output_dir).resolve()
        if input_path.suffix.lower() != ".docx":
            raise ValueError("Only .docx input is supported in this version.")
        context = AgentRunContext(
            input_path=input_path,
            output_dir=output_dir,
            profile_id=self.profile.profile_id,
            llm=self.llm_client,
            memory_path=self.memory_path,
        )

        parsed = self.parser.run(context)
        audit_result = self.auditor.run(context, parsed, self.profile)
        issues: list[Issue] = audit_result["issues"]
        before_summary: AuditSummary = audit_result["summary"]

        fixer_result = None
        post_fix = None
        after_summary = None
        if fix_safe:
            fixed_path = output_dir / "fixed.docx"
            fixer_result = self.fixer.run(context, issues, fixed_path)
            post_parsed = self.parser.run(context, fixed_path)
            post_fix = self.auditor.run(context, post_parsed, self.profile)
            after_summary = post_fix["summary"]
            post_path = output_dir / "post_fix_result.json"
            post_path.write_text(
                json.dumps(self._to_serializable(post_fix), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        quality = self.quality_gate.run(context, before_summary, after_summary)
        shared_llm = self._run_shared_llm_advice(context, issues, before_summary) if llm_advice else None
        iteration = self.iteration_memory.run(context, issues, before_summary, fixer_result, after_summary)
        result = {
            "run_id": context.run_id,
            "generated_at": utc_now(),
            "document": {
                "input_path": str(input_path),
                "file_name": input_path.name,
                "fixed_path": str(fixer_result["fixed_path"]) if fixer_result else None,
            },
            "profile": audit_result["profile"],
            "summary": before_summary,
            "issues": issues,
            "safe_fix": fixer_result,
            "post_fix_summary": after_summary,
            "quality_gate": quality,
            "shared_llm": shared_llm,
            "iteration": iteration,
            "shared_context": context.shared.to_dict(),
            "agent_traces": context.traces_as_dicts(),
        }
        report_paths = self.reporter.run(context, result)
        result["reports"] = {key: str(value) for key, value in report_paths.items()}
        result["shared_context"] = context.shared.to_dict()
        result["agent_traces"] = context.traces_as_dicts()
        return self._to_serializable(result)

    def batch(
        self,
        input_dir: str | Path,
        output_dir: str | Path,
        fix_safe: bool = False,
        llm_advice: bool = False,
    ) -> dict[str, Any]:
        input_dir = Path(input_dir).resolve()
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for docx_path in sorted(input_dir.glob("*.docx")):
            doc_output_dir = output_dir / docx_path.stem
            results.append(self.audit(docx_path, doc_output_dir, fix_safe=fix_safe, llm_advice=llm_advice))

        summary = {
            "generated_at": utc_now(),
            "profile_id": self.profile.profile_id,
            "input_dir": str(input_dir),
            "document_count": len(results),
            "documents": [
                {
                    "file_name": result["document"]["file_name"],
                    "score": result["summary"]["score"],
                    "total_issues": result["summary"]["total_issues"],
                    "manual_required_issues": result["summary"]["manual_required_issues"],
                    "report": result["reports"]["html"],
                }
                for result in results
            ],
        }
        summary["iteration"] = self.iteration_memory.summarize_batch(output_dir, results)
        summary_path = output_dir / "batch_summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary

    def _to_serializable(self, value: Any) -> Any:
        if isinstance(value, Issue):
            return value.to_dict()
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {key: self._to_serializable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._to_serializable(item) for item in value]
        return value

    def _run_shared_llm_advice(
        self,
        context: AgentRunContext,
        issues: list[Issue],
        summary: AuditSummary,
    ) -> dict[str, Any]:
        trace = context.start_trace("shared_llm", "advisory_context")
        prompt = self._build_shared_llm_prompt(context, issues, summary)
        if context.llm is None:
            result = {
                "status": "not_configured",
                "mode": "shared_llm_service",
                "affects_score": False,
                "affects_fixes": False,
                "config": None,
                "prompt": prompt,
                "advice": "LLM service is not configured. The prompt is provided for later model integration.",
            }
            context.shared.record_artifact("shared_llm_prompt", prompt)
            context.shared.observe("shared_llm", "Shared LLM service was requested but is not configured.")
            trace.finish("not_configured", "Shared LLM service is not configured.")
            return result

        try:
            advice = context.llm.complete(prompt)
            status = "ok" if str(advice).strip() else "empty_response"
            if status == "empty_response":
                advice = "LLM 接口已调用，但返回内容为空。"
            result = {
                "status": status,
                "mode": "shared_llm_service",
                "affects_score": False,
                "affects_fixes": False,
                "config": self._llm_config_snapshot(context.llm),
                "prompt": prompt,
                "advice": advice,
            }
            context.shared.record_artifact("shared_llm_prompt", prompt)
            context.shared.record_artifact("shared_llm_advice", advice)
            context.shared.observe("shared_llm", "Shared LLM service completed.", status=status)
            trace.finish(status, "Shared LLM service completed.")
            return result
        except Exception as exc:  # pragma: no cover - defensive integration boundary
            result = {
                "status": "failed",
                "mode": "shared_llm_service",
                "affects_score": False,
                "affects_fixes": False,
                "config": self._llm_config_snapshot(context.llm),
                "prompt": prompt,
                "advice": f"Shared LLM call failed: {exc}",
            }
            context.shared.record_artifact("shared_llm_prompt", prompt)
            context.shared.observe("shared_llm", "Shared LLM service failed.", error=str(exc))
            trace.finish("failed", "Shared LLM service failed.")
            return result

    def _build_shared_llm_prompt(
        self,
        context: AgentRunContext,
        issues: list[Issue],
        summary: AuditSummary,
    ) -> str:
        lines = [
            "你是排版审核多智能体系统的共享大模型能力层。",
            "请只提供解释、人工复核优先级和可读建议，不要推翻硬规则结论，不要要求自动修改内容。",
            f"文档：{context.input_path.name}",
            f"规则档案：{context.profile_id}",
            f"合规得分：{summary.score}",
            f"问题总数：{summary.total_issues}",
            f"严重问题数：{summary.severe_issues}",
            f"需人工复核数：{summary.manual_required_issues}",
            "代表性问题：",
        ]
        for issue in issues[:15]:
            lines.append(
                f"- [{issue.severity}/{issue.status}] {issue.category} {issue.rule_id} "
                f"位置={issue.location.get('element_id')} 字段={issue.field} "
                f"实际={issue.actual} 期望={issue.expected} 建议={issue.suggestion}"
            )
        return "\n".join(lines)

    def _llm_config_snapshot(self, llm_client: LLMClient | None) -> dict[str, Any] | None:
        config = getattr(llm_client, "config", None)
        if config is None:
            return None
        return {
            "provider": getattr(config, "provider", ""),
            "base_url": getattr(config, "base_url", ""),
            "api_key": "***" if getattr(config, "api_key", "") else "",
            "model": getattr(config, "model", ""),
            "temperature": getattr(config, "temperature", None),
            "max_tokens": getattr(config, "max_tokens", None),
        }
