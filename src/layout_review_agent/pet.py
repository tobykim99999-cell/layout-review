from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import threading
import webbrowser
from pathlib import Path
from tkinter import BooleanVar, Canvas, PhotoImage, StringVar, Tk, Toplevel, filedialog, messagebox
from tkinter import ttk
from typing import Any
from uuid import uuid4

from layout_review_agent.agents import LayoutReviewCoordinator
from layout_review_agent.desktop import (
    DEFAULT_RULES_DIR,
    build_llm_client,
    safe_profile_id,
    safe_storage_filename,
)
from layout_review_agent.llm import load_llm_config
from layout_review_agent.rules import list_profiles, validate_profile_data
from layout_review_agent.spec_normalizer import extract_spec_text, normalize_spec_to_profile

DEFAULT_BASE_DIR = "pet_runs"
TRANSPARENT_COLOR = "#f7fbff"
PET_CANVAS_WIDTH = 330
PET_CANVAS_HEIGHT = 260
PANEL_WIDTH = 370
PANEL_MIN_HEIGHT = 490
PANEL_SCREEN_MARGIN = 56
DEFAULT_PET_IMAGE = Path(__file__).resolve().parent / "assets" / "robot_3d.png"


class RobotPetCanvas(Canvas):
    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(
            master,
            width=PET_CANVAS_WIDTH,
            height=PET_CANVAS_HEIGHT,
            bg=TRANSPARENT_COLOR,
            highlightthickness=0,
            **kwargs,
        )
        self.tick = 0
        self.mood = "idle"
        self._source_image: PhotoImage | None = None
        self.pet_image: PhotoImage | None = None
        self._load_pet_image(DEFAULT_PET_IMAGE)
        self.after(80, self.animate)

    def set_mood(self, mood: str) -> None:
        self.mood = mood

    def animate(self) -> None:
        self.tick += 1
        self.draw_pet()
        self.after(80 if self.mood != "busy" else 55, self.animate)

    def _load_pet_image(self, image_path: Path) -> None:
        if not image_path.exists():
            return
        self._source_image = PhotoImage(file=str(image_path))
        width = self._source_image.width()
        height = self._source_image.height()
        scale = max(1, math.ceil(width / 310), math.ceil(height / 300))
        self.pet_image = self._source_image.subsample(scale, scale) if scale > 1 else self._source_image

    def draw_pet(self) -> None:
        self.delete("all")
        t = self.tick
        bob = math.sin(t / 8) * 6
        pulse = 1 + math.sin(t / 7) * 0.08
        cx = PET_CANVAS_WIDTH / 2
        cy = 126 + bob

        self._draw_shadow(cx, 226, pulse)
        self._draw_status_orbit(cx, cy, t)
        if self.pet_image is None:
            self._draw_missing_asset(cx, cy)
        else:
            self.create_image(cx, cy, image=self.pet_image)
        self._draw_status_badge(cx, cy, t)

    def _draw_shadow(self, cx: float, y: float, pulse: float) -> None:
        self.create_oval(cx - 120, y + 5, cx + 120, y + 27, fill="#eaf5ff", outline="")
        self.create_oval(cx - 88, y - 11, cx + 88, y + 14, fill="#d8eaff", outline="")
        self.create_oval(cx - 68, y - 15, cx + 68, y + 7, fill="#f2faff", outline="")
        glow = 24 * pulse
        self.create_oval(cx - glow, y - 8, cx + glow, y + 11, fill="#bdf7ff", outline="")

    def _draw_status_orbit(self, cx: float, cy: float, t: int) -> None:
        if self.mood != "busy":
            return
        self.create_arc(cx - 128, cy - 72, cx + 128, cy + 72, start=10, extent=55, style="arc", outline="#7ddcff", width=2)
        self.create_arc(cx - 128, cy - 72, cx + 128, cy + 72, start=190, extent=60, style="arc", outline="#b7f4ff", width=2)
        for index in range(5):
            angle = t / 8 + index * math.tau / 5
            x = cx + math.cos(angle) * 122
            y = cy + math.sin(angle) * 63
            size = 3 + index % 3
            self.create_oval(x - size, y - size, x + size, y + size, fill="#7df4ff", outline="")

    def _draw_missing_asset(self, cx: float, cy: float) -> None:
        self._rounded_rect(cx - 64, cy - 50, cx + 64, cy + 50, 24, fill="#e8f5ff", outline="#86c8ff", width=2)
        self._rounded_rect(cx - 42, cy - 22, cx + 42, cy + 18, 18, fill="#11243d", outline="#30c7ff", width=2)
        self.create_text(cx, cy - 1, text="AI", fill="#8ff8ff", font=("Arial", 17, "bold"))

    def _draw_status_badge(self, cx: float, cy: float, t: int) -> None:
        badge_x = cx + 72
        badge_y = cy - 78
        if self.mood == "busy":
            self._rounded_rect(badge_x, badge_y, badge_x + 47, badge_y + 39, 16, fill="#e7f3ff", outline="#61b6ff", width=2)
            for index in range(3):
                x = badge_x + 17 + index * 8
                y = badge_y + 20 + math.sin(t / 4 + index) * 2
                self.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#1d7fff", outline="")
        elif self.mood == "done":
            self._rounded_rect(badge_x, badge_y, badge_x + 47, badge_y + 39, 16, fill="#e8fff3", outline="#35c875", width=2)
            self.create_line(
                badge_x + 13,
                badge_y + 21,
                badge_x + 22,
                badge_y + 30,
                badge_x + 36,
                badge_y + 12,
                fill="#12a95b",
                width=4,
                capstyle="round",
                joinstyle="round",
            )
        elif self.mood == "error":
            self._rounded_rect(badge_x + 3, badge_y, badge_x + 44, badge_y + 39, 16, fill="#fff0f0", outline="#ff5b66", width=2)
            self.create_line(badge_x + 24, badge_y + 10, badge_x + 24, badge_y + 24, fill="#e11d48", width=4, capstyle="round")
            self.create_oval(badge_x + 21, badge_y + 29, badge_x + 27, badge_y + 35, fill="#e11d48", outline="")
        else:
            self.create_oval(cx + 95, cy + 82, cx + 113, cy + 100, fill="#c7fbff", outline="")
            self.create_oval(cx + 99, cy + 86, cx + 109, cy + 96, fill="#19c7df", outline="")
            self.create_oval(cx + 101, cy + 88, cx + 105, cy + 92, fill="#ffffff", outline="")

    def _rounded_rect(self, x0: float, y0: float, x1: float, y1: float, radius: float, **kwargs: Any) -> None:
        points = [
            x0 + radius,
            y0,
            x1 - radius,
            y0,
            x1,
            y0,
            x1,
            y0 + radius,
            x1,
            y1 - radius,
            x1,
            y1,
            x1 - radius,
            y1,
            x0 + radius,
            y1,
            x0,
            y1,
            x0,
            y1 - radius,
            x0,
            y0 + radius,
            x0,
            y0,
        ]
        self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)


class LayoutReviewPetApp:
    def __init__(self, root: Tk, base_dir: str | Path = DEFAULT_BASE_DIR, rules_dir: str | Path = DEFAULT_RULES_DIR) -> None:
        self.root = root
        self.base_dir = Path(base_dir).resolve()
        self.rules_dir = Path(rules_dir).resolve()
        self.document_path: Path | None = None
        self.result: dict[str, Any] | None = None
        self.profile_options: dict[str, str] = {}
        self.busy = False
        self.drag_x = 0
        self.drag_y = 0
        self.press_root_x = 0
        self.press_root_y = 0
        self.did_drag = False

        self.profile_label = StringVar()
        self.status_text = StringVar(value="点击机器人展开功能。")
        self.document_label = StringVar(value="未选择论文")
        self.fix_safe = BooleanVar(value=True)
        self.llm_advice = BooleanVar(value=True)
        self.summary_text = StringVar(value="待审核")
        self.profile_combo: ttk.Combobox | None = None
        self.panel: Toplevel | None = None

        self._build_ui()
        self.reload_profiles()

    def _build_ui(self) -> None:
        self.root.title("排版审核智能机器人")
        self.root.geometry("330x260+80+110")
        self.root.resizable(False, False)
        self.root.overrideredirect(True)
        self.root.configure(bg=TRANSPARENT_COLOR)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.98)
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT_COLOR)
        except Exception:
            pass

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Pet.TButton", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Tiny.TLabel", font=("Microsoft YaHei UI", 9))

        self.pet = RobotPetCanvas(self.root)
        self.pet.pack(fill="both", expand=True)
        self.pet.bind("<ButtonPress-1>", self._start_drag)
        self.pet.bind("<B1-Motion>", self._drag)
        self.pet.bind("<ButtonRelease-1>", self._release_pet)
        self.pet.bind("<Button-3>", lambda _event: self.root.destroy())

        self.panel = Toplevel(self.root)
        self.panel.withdraw()
        self.panel.overrideredirect(True)
        self.panel.resizable(False, False)
        self.panel.configure(bg="#dbeafe")
        self.panel.attributes("-topmost", True)
        self.panel.attributes("-alpha", 0.98)

        shell = ttk.Frame(self.panel, padding=12)
        shell.pack(fill="both", expand=True, padx=2, pady=2)

        top = ttk.Frame(shell)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="排版审核机器人", font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
        ttk.Button(top, text="隐藏", width=6, command=self.hide_panel).pack(side="right")

        bubble = ttk.LabelFrame(shell, text="状态", padding=8)
        bubble.pack(fill="x", pady=(0, 8))
        ttk.Label(bubble, textvariable=self.status_text, wraplength=340).pack(anchor="w")
        ttk.Label(bubble, textvariable=self.summary_text, foreground="#2563eb").pack(anchor="w", pady=(4, 0))
        quick_results = ttk.Frame(bubble)
        quick_results.pack(fill="x", pady=(8, 0))
        ttk.Button(quick_results, text="批注", command=lambda: self.open_report("annotated_docx")).pack(side="left", fill="x", expand=True)
        ttk.Button(quick_results, text="修复稿", command=lambda: self.open_document_result("fixed_path")).pack(
            side="left", fill="x", expand=True, padx=(6, 0)
        )
        ttk.Button(quick_results, text="报告", command=lambda: self.open_report("html")).pack(side="left", fill="x", expand=True, padx=(6, 0))
        ttk.Button(quick_results, text="目录", command=self.open_output_dir).pack(side="left", fill="x", expand=True, padx=(6, 0))

        doc_box = ttk.LabelFrame(shell, text="论文", padding=8)
        doc_box.pack(fill="x", pady=(0, 8))
        ttk.Label(doc_box, textvariable=self.document_label, style="Tiny.TLabel", wraplength=250).pack(side="left", fill="x", expand=True)
        ttk.Button(doc_box, text="选择", width=7, command=self.choose_document).pack(side="right")

        profile_box = ttk.LabelFrame(shell, text="学校规则库", padding=8)
        profile_box.pack(fill="x", pady=(0, 8))
        self.profile_combo = ttk.Combobox(profile_box, textvariable=self.profile_label, state="readonly", width=30)
        self.profile_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(profile_box, text="刷新", width=7, command=self.reload_profiles).pack(side="right", padx=(6, 0))
        ttk.Button(profile_box, text="导入", width=7, command=self.import_school_spec).pack(side="right", padx=(6, 0))

        option_box = ttk.LabelFrame(shell, text="选项", padding=8)
        option_box.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(option_box, text="安全修复", variable=self.fix_safe).pack(side="left")
        ttk.Checkbutton(option_box, text="LLM 解释", variable=self.llm_advice).pack(side="left", padx=(12, 0))
        ttk.Button(option_box, text="LLM 状态", command=self.show_llm_status).pack(side="right")

        ttk.Button(shell, text="开始审核", style="Pet.TButton", command=self.start_audit).pack(fill="x", pady=(0, 8))

        result_box = ttk.LabelFrame(shell, text="结果", padding=8)
        result_box.pack(fill="x", pady=(0, 8))
        ttk.Button(result_box, text="原文批注", command=lambda: self.open_report("annotated_docx")).grid(
            row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        ttk.Button(result_box, text="修复稿", command=lambda: self.open_document_result("fixed_path")).grid(
            row=0, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Button(result_box, text="HTML 报告", command=lambda: self.open_report("html")).grid(
            row=1, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(result_box, text="结果目录", command=self.open_output_dir).grid(row=1, column=1, sticky="ew")
        ttk.Button(result_box, text="导出结果", command=self.export_results).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        result_box.columnconfigure(0, weight=1)
        result_box.columnconfigure(1, weight=1)

        footer = ttk.Frame(shell)
        footer.pack(fill="x")
        ttk.Button(footer, text="关闭机器人", command=self.root.destroy).pack(side="right")

    def _start_drag(self, event: Any) -> None:
        self.drag_x = event.x
        self.drag_y = event.y
        self.press_root_x = event.x_root
        self.press_root_y = event.y_root
        self.did_drag = False

    def _drag(self, event: Any) -> None:
        if abs(event.x_root - self.press_root_x) > 3 or abs(event.y_root - self.press_root_y) > 3:
            self.did_drag = True
        x = self.root.winfo_x() + event.x - self.drag_x
        y = self.root.winfo_y() + event.y - self.drag_y
        self.root.geometry(f"+{x}+{y}")
        if self.is_panel_visible():
            self._position_panel()

    def _release_pet(self, _event: Any) -> None:
        if not self.did_drag:
            self.toggle_panel()

    def toggle_panel(self) -> None:
        if self.is_panel_visible():
            self.hide_panel()
        else:
            self.show_panel()

    def show_panel(self) -> None:
        if self.panel is None:
            return
        self._position_panel()
        self.panel.deiconify()
        self.panel.lift()
        self.root.lift()

    def hide_panel(self) -> None:
        if self.panel is not None:
            self.panel.withdraw()

    def is_panel_visible(self) -> bool:
        return self.panel is not None and self.panel.state() != "withdrawn"

    def _position_panel(self) -> None:
        if self.panel is None:
            return
        self.panel.update_idletasks()
        width = max(PANEL_WIDTH, self.panel.winfo_reqwidth() + 4)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        max_height = max(PANEL_MIN_HEIGHT, screen_height - PANEL_SCREEN_MARGIN)
        height = min(max(PANEL_MIN_HEIGHT, self.panel.winfo_reqheight() + 4), max_height)
        x = self.root.winfo_x() + 295
        y = self.root.winfo_y() + 14
        if x + width > screen_width:
            x = max(8, self.root.winfo_x() - width + 35)
        if y + height > screen_height:
            y = max(8, screen_height - height - 48)
        self.panel.geometry(f"{width}x{height}+{x}+{y}")

    def choose_document(self) -> None:
        path = filedialog.askopenfilename(title="选择论文 DOCX", filetypes=[("Word DOCX", "*.docx")])
        if not path:
            return
        self.document_path = Path(path)
        self.document_label.set(self.document_path.name)
        self.status_text.set("论文已准备好，选择规则库后就可以审核。")
        self.pet.set_mood("idle")
        self.show_panel()

    def reload_profiles(self) -> None:
        profiles = [profile for profile in list_profiles(self.rules_dir) if profile.get("valid") and not profile.get("is_template")]
        self.profile_options = {}
        labels = []
        for profile in profiles:
            label = f"{profile['display_name']} ({profile['profile_id']})"
            labels.append(label)
            self.profile_options[label] = profile["profile_id"]
        self.profile_combo["values"] = labels
        if labels and self.profile_label.get() not in labels:
            self.profile_label.set(labels[0])
        if not labels:
            self.profile_label.set("")

    def import_school_spec(self) -> None:
        if self.busy:
            messagebox.showwarning("正在执行", "当前任务还没结束，请稍后再导入规则。")
            return
        path = filedialog.askopenfilename(
            title="选择学校规范或规则库",
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
        self._busy("正在导入学校规范，我会把它变成可选规则库。")
        try:
            self.rules_dir.mkdir(parents=True, exist_ok=True)
            payload = path.read_bytes()
            filename = safe_storage_filename(path.name, "school_spec")
            if path.suffix.lower() == ".json":
                profile_id = self._install_rule_profile_json(payload)
                title = "结构化规则库已导入。"
            else:
                profile_id = self._write_active_profile_from_spec(path, filename, payload)
                title = "学校规范已生成规则库。"
            self.root.after(0, lambda: self._import_done(title, profile_id))
        except Exception as exc:
            self.root.after(0, lambda: self._fail(str(exc)))

    def _install_rule_profile_json(self, payload: bytes) -> str:
        raw = json.loads(payload.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("JSON 规则库顶层必须是对象。")
        errors = validate_profile_data(raw)
        if errors:
            raise ValueError("规则库校验失败：" + "；".join(errors))
        profile_id = safe_profile_id(str(raw["profile_id"]))
        raw["profile_id"] = profile_id
        (self.rules_dir / f"{profile_id}.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return profile_id

    def _write_active_profile_from_spec(self, path: Path, filename: str, payload: bytes) -> str:
        profile_id = safe_profile_id(path.stem)
        source_dir = self.rules_dir / "_sources"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / f"{profile_id}_{filename}"
        shutil.copy2(path, source_path)
        source = {
            "type": "uploaded_school_spec",
            "document_name": filename,
            "uploaded_file": str(source_path),
            "normalization": "pet_llm_or_local_generated_from_uploaded_spec",
            "note": "规则由桌面宠物助手从学校官方规范自动规范化生成，审核仍以此 JSON 的确定性规则为准。",
        }
        result = normalize_spec_to_profile(
            spec_text=extract_spec_text(filename, payload),
            profile_id=profile_id,
            display_name=f"{path.stem} 论文格式规范",
            version="2026.1",
            source=source,
            llm_client=build_llm_client(),
        )
        generated_dir = self.rules_dir / "_generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        (self.rules_dir / f"{profile_id}.json").write_text(json.dumps(result.profile, ensure_ascii=False, indent=2), encoding="utf-8")
        (generated_dir / f"{profile_id}_prompt.txt").write_text(result.prompt, encoding="utf-8")
        (generated_dir / f"{profile_id}_response.txt").write_text(result.response, encoding="utf-8")
        return profile_id

    def _import_done(self, title: str, profile_id: str) -> None:
        self.busy = False
        self.pet.set_mood("done")
        self.reload_profiles()
        for label, value in self.profile_options.items():
            if value == profile_id:
                self.profile_label.set(label)
                break
        self.status_text.set(title)
        self.show_panel()
        messagebox.showinfo("导入完成", title)

    def show_llm_status(self) -> None:
        status = load_llm_config().masked()
        messagebox.showinfo("LLM 配置状态", "\n".join(f"{key}: {value}" for key, value in status.items()))

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
        threading.Thread(
            target=self._audit_worker,
            args=(self.document_path, profile_id, self.fix_safe.get(), self.llm_advice.get()),
            daemon=True,
        ).start()

    def _audit_worker(self, document_path: Path, profile_id: str, fix_safe: bool, llm_advice: bool) -> None:
        self._busy("正在调用智能体流水线：解析、审核、修复、生成批注。")
        try:
            output_dir = self.base_dir / uuid4().hex / "reports"
            coordinator = LayoutReviewCoordinator(
                profile=profile_id,
                rules_dir=self.rules_dir,
                llm_client=build_llm_client(),
                memory_path=self.base_dir / "review_memory.jsonl",
            )
            result = coordinator.audit(
                document_path,
                output_dir,
                fix_safe=fix_safe,
                llm_advice=llm_advice,
            )
            self.root.after(0, lambda: self._audit_done(result))
        except Exception as exc:
            self.root.after(0, lambda: self._fail(str(exc)))

    def _audit_done(self, result: dict[str, Any]) -> None:
        self.busy = False
        self.result = result
        summary = result["summary"]
        self.summary_text.set(
            f"得分 {summary['score']} | 问题 {summary['total_issues']} | 自动修复 {summary['auto_fixable_issues']} | 复核 {summary['manual_required_issues']}"
        )
        self.status_text.set("审核完成，可以打开批注或修复稿。")
        self.pet.set_mood("done")
        self.show_panel()
        messagebox.showinfo("审核完成", "报告已经生成。建议先打开“批注”查看原文提示。")

    def selected_profile_id(self) -> str:
        return self.profile_options.get(self.profile_label.get(), "")

    def open_report(self, key: str) -> None:
        if not self.result:
            messagebox.showwarning("暂无结果", "请先完成一次审核。")
            return
        self._open_path(self.result.get("reports", {}).get(key))

    def open_document_result(self, key: str) -> None:
        if not self.result:
            messagebox.showwarning("暂无结果", "请先完成一次审核。")
            return
        self._open_path(self.result.get("document", {}).get(key))

    def open_output_dir(self) -> None:
        if not self.result:
            messagebox.showwarning("暂无结果", "请先完成一次审核。")
            return
        reports_dir = self._current_reports_dir()
        self._open_path(str(reports_dir) if reports_dir else "")

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
            os.startfile(str(path))  # type: ignore[attr-defined]
            return
        opened = webbrowser.open(path.resolve().as_uri())
        if not opened:
            raise OSError(f"无法打开 {path}")

    def _busy(self, text: str) -> None:
        self.busy = True

        def apply_state() -> None:
            self.status_text.set(text)
            self.summary_text.set("执行中")
            self.pet.set_mood("busy")
            self.show_panel()

        self.root.after(0, apply_state)

    def _fail(self, message: str) -> None:
        self.busy = False
        self.status_text.set(f"失败：{message}")
        self.pet.set_mood("error")
        self.show_panel()
        messagebox.showerror("执行失败", message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the animated desktop pet assistant for layout review.")
    parser.add_argument("--base-dir", default=DEFAULT_BASE_DIR)
    parser.add_argument("--rules-dir", default=DEFAULT_RULES_DIR)
    args = parser.parse_args(argv)

    root = Tk()
    LayoutReviewPetApp(root, base_dir=args.base_dir, rules_dir=args.rules_dir)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
