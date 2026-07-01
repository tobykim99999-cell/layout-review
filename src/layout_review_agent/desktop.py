from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import threading
import webbrowser
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox
from tkinter import scrolledtext, ttk
from typing import Any
from uuid import uuid4

from layout_review_agent.agents import LayoutReviewCoordinator
from layout_review_agent.llm import OpenAICompatibleLLMClient, load_llm_config
from layout_review_agent.rules import list_profiles, validate_profile_data
from layout_review_agent.spec_normalizer import (
    SpecNormalizationError,
    extract_spec_text,
    normalize_spec_to_profile,
)

DEFAULT_BASE_DIR = "desktop_runs"
DEFAULT_RULES_DIR = "rule_profiles"


def safe_storage_filename(value: str, default: str = "upload") -> str:
    name = Path(value or default).name
    name = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", name, flags=re.UNICODE).strip("._")
    return name or default


def safe_profile_id(value: str) -> str:
    profile_id = re.sub(r"[^a-zA-Z0-9_\-]+", "_", value.strip()).strip("_").lower()
    return profile_id or f"school_profile_{uuid4().hex[:8]}"


def build_llm_client() -> OpenAICompatibleLLMClient | None:
    config = load_llm_config()
    if not config.enabled:
        return None
    return OpenAICompatibleLLMClient(config=config)


class LayoutReviewDesktopApp:
    def __init__(self, root: Tk, base_dir: str | Path = DEFAULT_BASE_DIR, rules_dir: str | Path = DEFAULT_RULES_DIR) -> None:
        self.root = root
        self.base_dir = Path(base_dir).resolve()
        self.rules_dir = Path(rules_dir).resolve()
        self.document_path: Path | None = None
        self.result: dict[str, Any] | None = None
        self.profile_options: dict[str, str] = {}
        self.busy = False
        self.busy_tick = 0

        self.profile_label = StringVar()
        self.document_label = StringVar(value="尚未选择论文 DOCX")
        self.status_text = StringVar(value="待命")
        self.fix_safe = BooleanVar(value=True)
        self.llm_advice = BooleanVar(value=True)
        self.score_value = StringVar(value="-")
        self.issue_value = StringVar(value="-")
        self.auto_value = StringVar(value="-")
        self.manual_value = StringVar(value="-")

        self.root.title("毕业论文排版审核智能体助手")
        self.root.geometry("1080x720")
        self.root.minsize(980, 640)
        self._build_ui()
        self.reload_profiles()
        self._log("桌面智能体助手已启动。")
        self._log(f"规则库目录：{self.rules_dir}")
        self._log(f"运行输出目录：{self.base_dir}")

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Section.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Value.TLabel", font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"))

        shell = ttk.Frame(self.root, padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=0)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        ttk.Label(header, text="毕业论文排版审核智能体助手", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="本地运行，保留规则审核、学校规范导入、安全修复、原文批注和报告输出能力。",
        ).pack(anchor="w", pady=(4, 0))

        agent_panel = ttk.LabelFrame(shell, text="智能体执行状态", padding=14)
        agent_panel.grid(row=1, column=0, sticky="ns", padx=(0, 14))
        agent_panel.columnconfigure(0, weight=1)

        self.agent_canvas = ttk.Label(agent_panel, text="AI", anchor="center", width=8)
        self.agent_canvas.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(agent_panel, textvariable=self.status_text, style="Section.TLabel", wraplength=190).grid(
            row=1, column=0, sticky="ew", pady=(0, 12)
        )
        self.progress = ttk.Progressbar(agent_panel, mode="indeterminate", length=190)
        self.progress.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        self.step_labels: list[ttk.Label] = []
        for index, text in enumerate(["文档解析", "规则审核", "保守修复", "LLM 解释", "生成报告"]):
            label = ttk.Label(agent_panel, text=f"○ {text}", width=22)
            label.grid(row=3 + index, column=0, sticky="w", pady=4)
            self.step_labels.append(label)

        controls = ttk.Frame(shell)
        controls.grid(row=1, column=1, sticky="nsew")
        controls.columnconfigure(0, weight=1)
        controls.rowconfigure(6, weight=1)

        doc_box = ttk.LabelFrame(controls, text="1. 选择论文", padding=12)
        doc_box.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        doc_box.columnconfigure(0, weight=1)
        ttk.Label(doc_box, textvariable=self.document_label).grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ttk.Button(doc_box, text="选择 DOCX", command=self.choose_document).grid(row=0, column=1)

        profile_box = ttk.LabelFrame(controls, text="2. 学校规则库", padding=12)
        profile_box.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        profile_box.columnconfigure(0, weight=1)
        self.profile_combo = ttk.Combobox(profile_box, textvariable=self.profile_label, state="readonly")
        self.profile_combo.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ttk.Button(profile_box, text="刷新", command=self.reload_profiles).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(profile_box, text="导入学校规范", command=self.import_school_spec).grid(row=0, column=2)

        option_box = ttk.LabelFrame(controls, text="3. 审核选项", padding=12)
        option_box.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ttk.Checkbutton(option_box, text="自动安全修复明显问题", variable=self.fix_safe).pack(side="left", padx=(0, 22))
        ttk.Checkbutton(option_box, text="生成共享 LLM 解释", variable=self.llm_advice).pack(side="left", padx=(0, 22))
        ttk.Button(option_box, text="查看 LLM 状态", command=self.show_llm_status).pack(side="right")

        action_box = ttk.Frame(controls)
        action_box.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(action_box, text="开始审核", style="Primary.TButton", command=self.start_audit).pack(side="left")
        ttk.Button(action_box, text="打开原文批注", command=lambda: self.open_report("annotated_docx")).pack(
            side="left", padx=(10, 0)
        )
        ttk.Button(action_box, text="打开修复稿", command=lambda: self.open_document_result("fixed_path")).pack(
            side="left", padx=(10, 0)
        )
        ttk.Button(action_box, text="打开 HTML 报告", command=lambda: self.open_report("html")).pack(side="left", padx=(10, 0))
        ttk.Button(action_box, text="打开结果目录", command=self.open_output_dir).pack(side="left", padx=(10, 0))
        ttk.Button(action_box, text="导出结果", command=self.export_results).pack(side="left", padx=(10, 0))

        summary = ttk.Frame(controls)
        summary.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        for index in range(4):
            summary.columnconfigure(index, weight=1)
        self._summary_card(summary, 0, "合规得分", self.score_value)
        self._summary_card(summary, 1, "问题总数", self.issue_value)
        self._summary_card(summary, 2, "可自动修复", self.auto_value)
        self._summary_card(summary, 3, "需人工复核", self.manual_value)

        ttk.Label(controls, text="执行日志", style="Section.TLabel").grid(row=5, column=0, sticky="w")
        self.log_area = scrolledtext.ScrolledText(controls, height=12, wrap="word")
        self.log_area.grid(row=6, column=0, sticky="nsew", pady=(6, 0))
        self.log_area.configure(state="disabled")

    def _summary_card(self, parent: ttk.Frame, column: int, title: str, value: StringVar) -> None:
        frame = ttk.LabelFrame(parent, text=title, padding=10)
        frame.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
        ttk.Label(frame, textvariable=value, style="Value.TLabel").pack(anchor="center")

    def choose_document(self) -> None:
        path = filedialog.askopenfilename(
            title="选择处理后的论文 DOCX",
            filetypes=[("Word DOCX", "*.docx")],
        )
        if not path:
            return
        self.document_path = Path(path)
        self.document_label.set(str(self.document_path))
        self._log(f"已选择论文：{self.document_path}")

    def reload_profiles(self) -> None:
        profiles = [profile for profile in list_profiles(self.rules_dir) if profile.get("valid") and not profile.get("is_template")]
        self.profile_options = {}
        labels = []
        for profile in profiles:
            label = f"{profile['display_name']} / {profile['version']} ({profile['profile_id']})"
            labels.append(label)
            self.profile_options[label] = profile["profile_id"]
        self.profile_combo["values"] = labels
        if labels and self.profile_label.get() not in labels:
            self.profile_label.set(labels[0])
        if not labels:
            self.profile_label.set("")
        self._log(f"已加载 {len(labels)} 个可用规则库。")

    def import_school_spec(self) -> None:
        path = filedialog.askopenfilename(
            title="选择学校论文格式规范或规则库",
            filetypes=[
                ("支持的规范文件", "*.json *.docx *.txt *.md *.pdf"),
                ("JSON 规则库", "*.json"),
                ("Word DOCX", "*.docx"),
                ("文本文件", "*.txt *.md"),
                ("PDF 文件", "*.pdf"),
            ],
        )
        if not path:
            return
        threading.Thread(target=self._import_school_spec_worker, args=(Path(path),), daemon=True).start()

    def _import_school_spec_worker(self, path: Path) -> None:
        self._set_busy(True, "正在导入学校规范")
        try:
            self.rules_dir.mkdir(parents=True, exist_ok=True)
            payload = path.read_bytes()
            filename = safe_storage_filename(path.name, "school_spec")
            if path.suffix.lower() == ".json":
                title, profile_id = self._install_rule_profile_json(filename, payload)
            else:
                title, profile_id = self._write_active_profile_from_spec(path, filename, payload)
            self.root.after(0, lambda: self._import_done(title, profile_id))
        except Exception as exc:
            self.root.after(0, lambda: self._fail(str(exc)))

    def _install_rule_profile_json(self, filename: str, payload: bytes) -> tuple[str, str]:
        raw = json.loads(payload.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("JSON 规则库顶层必须是对象。")
        errors = validate_profile_data(raw)
        if errors:
            raise ValueError("规则库校验失败：" + "；".join(errors))
        profile_id = safe_profile_id(str(raw["profile_id"]))
        raw["profile_id"] = profile_id
        target = self.rules_dir / f"{profile_id}.json"
        target.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return (f"结构化规则库已导入：{filename}", profile_id)

    def _write_active_profile_from_spec(self, path: Path, filename: str, payload: bytes) -> tuple[str, str]:
        profile_id = safe_profile_id(path.stem)
        display_name = f"{path.stem} 论文格式规范"
        version = "2026.1"
        source_dir = self.rules_dir / "_sources"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / f"{profile_id}_{filename}"
        shutil.copy2(path, source_path)
        source = {
            "type": "uploaded_school_spec",
            "document_name": filename,
            "uploaded_file": str(source_path),
            "normalization": "desktop_llm_or_local_generated_from_uploaded_spec",
            "note": "规则由桌面助手从学校官方规范自动规范化生成，审核仍以此 JSON 的确定性规则为准。",
        }
        spec_text = extract_spec_text(filename, payload)
        result = normalize_spec_to_profile(
            spec_text=spec_text,
            profile_id=profile_id,
            display_name=display_name,
            version=version,
            source=source,
            llm_client=build_llm_client(),
        )

        generated_dir = self.rules_dir / "_generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        profile_path = self.rules_dir / f"{profile_id}.json"
        profile_path.write_text(json.dumps(result.profile, ensure_ascii=False, indent=2), encoding="utf-8")
        (generated_dir / f"{profile_id}_prompt.txt").write_text(result.prompt, encoding="utf-8")
        (generated_dir / f"{profile_id}_response.txt").write_text(result.response, encoding="utf-8")
        return (f"学校规范已生成可选规则库：{profile_path.name}", profile_id)

    def _import_done(self, title: str, profile_id: str) -> None:
        self._set_busy(False, "规则库导入完成")
        self.reload_profiles()
        for label, value in self.profile_options.items():
            if value == profile_id:
                self.profile_label.set(label)
                break
        self._log(title)
        messagebox.showinfo("导入完成", title)

    def show_llm_status(self) -> None:
        status = load_llm_config().masked()
        lines = [f"{key}: {value}" for key, value in status.items()]
        messagebox.showinfo("LLM 配置状态", "\n".join(lines))

    def start_audit(self) -> None:
        if self.busy:
            return
        if self.document_path is None:
            messagebox.showwarning("缺少论文", "请先选择需要审核的 DOCX 论文。")
            return
        profile_id = self.selected_profile_id()
        if not profile_id:
            messagebox.showwarning("缺少规则库", "请先选择学校规则库。")
            return
        threading.Thread(target=self._audit_worker, args=(self.document_path, profile_id), daemon=True).start()

    def _audit_worker(self, document_path: Path, profile_id: str) -> None:
        self._set_busy(True, "智能体正在审核论文")
        try:
            run_dir = self.base_dir / uuid4().hex
            output_dir = run_dir / "reports"
            coordinator = LayoutReviewCoordinator(
                profile=profile_id,
                rules_dir=self.rules_dir,
                llm_client=build_llm_client(),
                memory_path=self.base_dir / "review_memory.jsonl",
            )
            self._thread_log("开始解析 DOCX。")
            result = coordinator.audit(
                document_path,
                output_dir,
                fix_safe=self.fix_safe.get(),
                llm_advice=self.llm_advice.get(),
            )
            self.root.after(0, lambda: self._audit_done(result))
        except Exception as exc:
            self.root.after(0, lambda: self._fail(str(exc)))

    def _audit_done(self, result: dict[str, Any]) -> None:
        self.result = result
        summary = result["summary"]
        self.score_value.set(str(summary["score"]))
        self.issue_value.set(str(summary["total_issues"]))
        self.auto_value.set(str(summary["auto_fixable_issues"]))
        self.manual_value.set(str(summary["manual_required_issues"]))
        self._set_busy(False, "审核完成")
        reports = result.get("reports", {})
        self._log("审核完成。")
        self._log(f"HTML 报告：{reports.get('html')}")
        self._log(f"原文批注：{reports.get('annotated_docx')}")
        if result.get("document", {}).get("fixed_path"):
            self._log(f"修复稿：{result['document']['fixed_path']}")
        messagebox.showinfo("审核完成", "审核完成，可以打开原文批注、修复稿或报告目录。")

    def selected_profile_id(self) -> str:
        label = self.profile_label.get()
        return self.profile_options.get(label, "")

    def open_report(self, key: str) -> None:
        if not self.result:
            messagebox.showwarning("暂无结果", "请先完成一次审核。")
            return
        path = self.result.get("reports", {}).get(key)
        self._open_path(path)

    def open_document_result(self, key: str) -> None:
        if not self.result:
            messagebox.showwarning("暂无结果", "请先完成一次审核。")
            return
        path = self.result.get("document", {}).get(key)
        self._open_path(path)

    def open_output_dir(self) -> None:
        if not self.result:
            messagebox.showwarning("暂无结果", "请先完成一次审核。")
            return
        reports_dir = self._current_reports_dir()
        if reports_dir is None:
            messagebox.showwarning("暂无目录", "结果目录不存在。")
            return
        self._open_path(str(reports_dir))

    def export_results(self) -> None:
        reports_dir = self._current_reports_dir()
        if reports_dir is None:
            messagebox.showwarning("暂无结果", "请先完成一次审核。")
            return
        target = filedialog.askdirectory(title="选择导出结果的文件夹")
        if not target:
            return
        destination = self._unique_export_dir(Path(target), reports_dir.parent.name)
        try:
            shutil.copytree(reports_dir, destination)
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        messagebox.showinfo("导出完成", f"结果已导出到：\n{destination}")
        self._open_path(str(destination))

    def _current_reports_dir(self) -> Path | None:
        if not self.result:
            return None
        json_path = self.result.get("reports", {}).get("json")
        if not json_path:
            return None
        reports_dir = Path(str(json_path)).parent
        return reports_dir if reports_dir.exists() else None

    def _unique_export_dir(self, target_dir: Path, run_id: str) -> Path:
        base_name = f"layout_review_{run_id}"
        destination = target_dir / base_name
        if not destination.exists():
            return destination
        for index in range(2, 1000):
            candidate = target_dir / f"{base_name}_{index}"
            if not candidate.exists():
                return candidate
        return target_dir / f"{base_name}_{uuid4().hex[:8]}"

    def _open_path(self, value: Any) -> None:
        if not value:
            messagebox.showwarning("文件不存在", "当前结果没有这个文件。")
            return
        path = Path(str(value))
        if not path.exists():
            messagebox.showwarning("文件不存在", str(path))
            return
        try:
            self._launch_path(path)
        except OSError as exc:
            parent = path if path.is_dir() else path.parent
            try:
                self._launch_path(parent)
            except OSError:
                pass
            messagebox.showwarning("无法直接打开", f"系统无法直接打开：\n{path}\n\n已尝试打开所在目录。\n\n错误：{exc}")

    def _launch_path(self, path: Path) -> None:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
            return
        opened = webbrowser.open(path.resolve().as_uri())
        if not opened:
            raise OSError(f"无法打开 {path}")

    def _set_busy(self, busy: bool, status: str) -> None:
        self.busy = busy
        self.root.after(0, lambda: self._apply_busy_state(busy, status))

    def _apply_busy_state(self, busy: bool, status: str) -> None:
        self.status_text.set(status)
        if busy:
            self.progress.start(12)
            self.busy_tick = 0
            self._animate_steps()
        else:
            self.progress.stop()
            for label in self.step_labels:
                text = label.cget("text").replace("●", "✓").replace("○", "✓")
                label.configure(text=text)

    def _animate_steps(self) -> None:
        if not self.busy:
            return
        active = self.busy_tick % len(self.step_labels)
        for index, label in enumerate(self.step_labels):
            base = label.cget("text")[2:]
            label.configure(text=f"{'●' if index == active else '○'} {base}")
        self.busy_tick += 1
        self.root.after(550, self._animate_steps)

    def _fail(self, message: str) -> None:
        self._set_busy(False, "执行失败")
        self._log(f"失败：{message}")
        messagebox.showerror("执行失败", message)

    def _thread_log(self, message: str) -> None:
        self.root.after(0, lambda: self._log(message))

    def _log(self, message: str) -> None:
        self.log_area.configure(state="normal")
        self.log_area.insert("end", message + "\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local desktop assistant for layout review.")
    parser.add_argument("--base-dir", default=DEFAULT_BASE_DIR)
    parser.add_argument("--rules-dir", default=DEFAULT_RULES_DIR)
    args = parser.parse_args(argv)

    root = Tk()
    LayoutReviewDesktopApp(root, base_dir=args.base_dir, rules_dir=args.rules_dir)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
