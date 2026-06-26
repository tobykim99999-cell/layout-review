from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse
from uuid import uuid4

from layout_review_agent.agents import LayoutReviewCoordinator
from layout_review_agent.llm import OpenAICompatibleLLMClient, load_llm_config
from layout_review_agent.rules import list_profiles, validate_profile_data
from layout_review_agent.spec_normalizer import (
    SpecNormalizationError,
    extract_spec_text,
    normalize_spec_to_profile,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_BASE_DIR = "web_runs"
DEFAULT_RULES_DIR = "rule_profiles"
MAX_UPLOAD_BYTES = 80 * 1024 * 1024


def safe_filename(value: str) -> str:
    name = Path(value or "upload.docx").name
    name = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", name, flags=re.UNICODE)
    if not name.lower().endswith(".docx"):
        name += ".docx"
    return name


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


def llm_status() -> dict[str, Any]:
    config = load_llm_config()
    return config.masked()


def parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    message = BytesParser(policy=default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    if not message.is_multipart():
        return fields, files
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename:
            files[name] = (filename, payload)
        else:
            fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    return fields, files


def parse_urlencoded(body: bytes) -> dict[str, str]:
    parsed = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def render_page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; color: #1f2937; background: #f6f8fb; }}
    main {{ max-width: 980px; margin: 36px auto; background: #fff; border: 1px solid #d8dee9; border-radius: 8px; padding: 28px; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; }}
    p {{ line-height: 1.7; }}
    .muted {{ color: #64748b; }}
    .row {{ margin: 16px 0; }}
    label {{ display: block; font-weight: 700; margin-bottom: 8px; }}
    input[type=file], input[type=text], select {{ width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; }}
    .checks label {{ display: inline-flex; gap: 8px; align-items: center; margin-right: 22px; font-weight: 400; }}
    button {{ padding: 10px 18px; border: 0; border-radius: 6px; background: #1d4ed8; color: #fff; cursor: pointer; }}
    button:hover {{ background: #1e40af; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 20px 0; }}
    .card {{ border: 1px solid #d8dee9; border-radius: 6px; padding: 14px; }}
    .value {{ font-size: 28px; font-weight: 700; }}
    .links a {{ display: inline-block; margin: 0 10px 10px 0; }}
    .error {{ background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; padding: 12px; border-radius: 6px; }}
    code {{ background: #f1f5f9; padding: 2px 5px; border-radius: 4px; }}
    .busy-overlay {{ position: fixed; inset: 0; display: none; place-items: center; background: rgba(246, 248, 251, 0.86); z-index: 20; }}
    .busy-overlay.active {{ display: grid; }}
    .busy-panel {{ width: min(520px, calc(100vw - 32px)); border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; padding: 22px; box-shadow: 0 18px 60px rgba(15, 23, 42, 0.16); }}
    .agent-row {{ display: grid; grid-template-columns: 52px 1fr; gap: 14px; align-items: center; }}
    .agent-avatar {{ width: 46px; height: 46px; border-radius: 50%; background: #1d4ed8; position: relative; box-shadow: inset 0 -7px 0 rgba(15, 23, 42, 0.18); animation: agentPulse 1.4s ease-in-out infinite; }}
    .agent-avatar::before, .agent-avatar::after {{ content: ""; position: absolute; top: 17px; width: 7px; height: 7px; border-radius: 50%; background: #fff; }}
    .agent-avatar::before {{ left: 13px; }}
    .agent-avatar::after {{ right: 13px; }}
    .busy-title {{ margin: 0; font-size: 20px; font-weight: 700; }}
    .busy-subtitle {{ margin: 6px 0 0; color: #64748b; }}
    .agent-steps {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin-top: 18px; }}
    .agent-step {{ min-height: 46px; border: 1px solid #d8dee9; border-radius: 6px; padding: 8px; font-size: 13px; color: #334155; background: #f8fafc; animation: stepGlow 1.8s ease-in-out infinite; }}
    .agent-step:nth-child(2) {{ animation-delay: .18s; }}
    .agent-step:nth-child(3) {{ animation-delay: .36s; }}
    .agent-step:nth-child(4) {{ animation-delay: .54s; }}
    .agent-step:nth-child(5) {{ animation-delay: .72s; }}
    .busy-dots::after {{ content: ""; animation: dots 1.2s steps(4, end) infinite; }}
    @keyframes agentPulse {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-4px); }} }}
    @keyframes stepGlow {{ 0%, 100% {{ border-color: #d8dee9; background: #f8fafc; }} 50% {{ border-color: #93c5fd; background: #eff6ff; }} }}
    @keyframes dots {{ 0% {{ content: ""; }} 25% {{ content: "."; }} 50% {{ content: ".."; }} 75%, 100% {{ content: "..."; }} }}
  </style>
</head>
<body>
  <main>{body}</main>
  <div id="busyOverlay" class="busy-overlay" aria-live="polite" aria-hidden="true">
    <div class="busy-panel">
      <div class="agent-row">
        <div class="agent-avatar" aria-hidden="true"></div>
        <div>
          <p class="busy-title">智能体正在执行任务<span class="busy-dots"></span></p>
          <p class="busy-subtitle">请不要关闭页面，完成后会自动显示结果。</p>
        </div>
      </div>
      <div class="agent-steps">
        <div class="agent-step">文档解析</div>
        <div class="agent-step">规则审核</div>
        <div class="agent-step">保守修复</div>
        <div class="agent-step">LLM 解释</div>
        <div class="agent-step">生成报告</div>
      </div>
    </div>
  </div>
  <script>
    document.querySelectorAll("form.js-work-form").forEach(function(form) {{
      form.addEventListener("submit", function() {{
        var overlay = document.getElementById("busyOverlay");
        if (overlay) {{
          overlay.classList.add("active");
          overlay.setAttribute("aria-hidden", "false");
        }}
        form.querySelectorAll("button").forEach(function(button) {{
          button.disabled = true;
        }});
      }});
    }});
  </script>
</body>
</html>
""".encode("utf-8")


def render_upload_page(
    profiles: list[dict[str, Any]] | None = None,
    selected_profile: str = "default_undergraduate",
    notice: str = "",
) -> bytes:
    profiles = profiles or list_profiles(DEFAULT_RULES_DIR)
    options = []
    warnings = []
    hidden_drafts = 0
    for profile in profiles:
        if profile.get("is_draft") and int(profile.get("rule_count", 0)) == 0:
            hidden_drafts += 1
            continue
        label = f'{profile["display_name"]} / {profile["version"]}'
        if profile.get("is_demo"):
            label += "（演示规则，非学校标准）"
        if profile.get("is_template"):
            label += "（模板，请先复制改名）"
        if not profile.get("valid"):
            label += "（规则无效）"
            warnings.append(f'{profile["profile_id"]}: {"; ".join(profile.get("errors", []))}')
        disabled = " disabled" if profile.get("is_template") or not profile.get("valid") else ""
        selected = " selected" if profile["profile_id"] == selected_profile else ""
        options.append(
            f'<option value="{html.escape(profile["profile_id"])}"{selected}{disabled}>{html.escape(label)}</option>'
        )
    warnings_html = ""
    if warnings:
        warnings_html = "<div class=\"error\">规则库存在问题：<br>" + "<br>".join(html.escape(item) for item in warnings) + "</div>"
    status = llm_status()
    llm_status_text = "已配置，会在勾选后调用" if status["enabled"] else "未配置，勾选后只生成上下文，不会调用大模型"
    llm_detail = ""
    if status["enabled"]:
        llm_detail = f' provider={html.escape(str(status["provider"]))} model={html.escape(str(status["model"]))} url={html.escape(str(status["chat_completions_url"]))}'
    notice_html = f'<div class="card">{html.escape(notice)}</div>' if notice else ""
    draft_notice = ""
    if hidden_drafts:
        draft_notice = f'<p class="muted">已隐藏 {hidden_drafts} 个旧草稿规则库；重新上传对应规范文件会自动生成可选规则库。</p>'
    body = f"""
<h1>毕业论文排版审核智能体</h1>
<p class="muted">上传自研排版系统处理后的 DOCX，系统会调用多智能体流水线完成审核、保守修复、报告生成和迭代画像。</p>
<p class="muted">正式使用前必须先创建目标学校规则库；默认规则只用于演示，不代表任何学校官方标准。</p>
{warnings_html}
{notice_html}
{draft_notice}
<form class="js-work-form" method="post" action="/audit" enctype="multipart/form-data">
  <div class="row">
    <label for="document">论文 DOCX</label>
    <input id="document" name="document" type="file" accept=".docx" required>
  </div>
  <div class="row">
    <label for="profile">学校规则库</label>
    <select id="profile" name="profile">
      {''.join(options)}
    </select>
    <p class="muted">目标学校规则库放在 <code>rule_profiles</code> 目录。可上传结构化 JSON，也可上传学校官方 DOCX/TXT/MD 规范自动生成。</p>
  </div>
  <div class="row checks">
    <label><input type="checkbox" name="fix_safe" checked> 自动安全修复（仅低风险项）</label>
    <label><input type="checkbox" name="llm_advice" checked> 生成共享 LLM 解释上下文</label>
  </div>
  <p class="muted">LLM 状态：{html.escape(llm_status_text)}{llm_detail}</p>
  <button type="submit">开始审核</button>
</form>
<p class="muted">不需要命令行。运行本地网页服务后，在这里上传文档即可。</p>
<p><a href="/profiles/new">上传学校论文格式规范或规则库</a> · <a href="/llm/status">查看 LLM 配置状态</a></p>
"""
    return render_page("排版审核智能体", body)


def render_llm_status_page() -> bytes:
    status = llm_status()
    rows = "".join(
        f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in status.items()
    )
    body = f"""
<h1>LLM 配置状态</h1>
<p class="muted">配置来源：项目根目录 <code>llm_config.json</code>，也可用环境变量覆盖。API Key 只显示脱敏状态。</p>
<table>{rows}</table>
<p>{'已配置，勾选 llm_advice 后会尝试调用接口。' if status["enabled"] else '未配置完整：必须同时有 base_url、api_key、model。'}</p>
<p><a href="/">返回论文上传页</a></p>
"""
    return render_page("LLM 配置状态", body)


def render_profile_upload_page(message: str = "") -> bytes:
    message_html = f'<div class="card">{message}</div>' if message else ""
    status = llm_status()
    llm_text = "已配置：上传 DOCX/TXT/MD 规范后会自动生成可选规则库。" if status["enabled"] else "未配置：上传官方规范只能保存来源草稿，不能自动规范化。"
    body = f"""
<h1>上传学校论文格式规范</h1>
<p class="muted">如果上传的是结构化规则库 JSON，系统会校验后加入规则下拉框。如果上传的是学校官方 DOCX/TXT/MD 规范，系统会调用已配置的大模型自动规范化为可选规则库；PDF 需安装文本抽取依赖或改传 DOCX。</p>
<p class="muted">LLM 状态：{html.escape(llm_text)}</p>
{message_html}
<form class="js-work-form" method="post" action="/profiles/upload" enctype="multipart/form-data">
  <div class="row">
    <label for="spec">规范文件或规则库 JSON</label>
    <input id="spec" name="spec" type="file" accept=".json,.docx,.pdf,.txt,.md" required>
  </div>
  <div class="row">
    <label for="profile_id">规则库 ID</label>
    <input id="profile_id" name="profile_id" type="text" placeholder="例如 xx_university_undergraduate_2026">
  </div>
  <div class="row">
    <label for="display_name">显示名称</label>
    <input id="display_name" name="display_name" type="text" placeholder="例如 XX大学本科毕业论文格式规范 2026">
  </div>
  <div class="row">
    <label for="school">学校</label>
    <input id="school" name="school" type="text" placeholder="例如 XX大学">
  </div>
  <div class="row">
    <label for="degree_level">学历层次</label>
    <input id="degree_level" name="degree_level" type="text" placeholder="本科/硕士/博士">
  </div>
  <div class="row">
    <label for="version">版本</label>
    <input id="version" name="version" type="text" value="2026.1">
  </div>
  <button type="submit">上传并生成可选规则库</button>
</form>
<p><a href="/">返回论文上传页</a></p>
"""
    return render_page("上传学校规范", body)


def render_profile_upload_result(title: str, details: list[str]) -> bytes:
    items = "".join(f"<li>{html.escape(item)}</li>" for item in details)
    body = f"""
<h1>{html.escape(title)}</h1>
<ul>{items}</ul>
<p><a href="/">返回论文上传页</a></p>
<p><a href="/profiles/new">继续上传规范</a></p>
"""
    return render_page(title, body)


def generated_profile_id(details: list[str]) -> str:
    for item in details:
        if item.startswith("规则 ID："):
            return item.split("：", 1)[1].strip()
    return ""


def render_result_page(result: dict[str, Any], run_id: str) -> bytes:
    summary = result["summary"]
    reports = result["reports"]
    safe_fix = result.get("safe_fix") or {}
    shared_llm = result.get("shared_llm") or {}
    applied_count = len(safe_fix.get("applied", []))
    skipped_count = len(safe_fix.get("skipped", []))
    llm_status_value = shared_llm.get("status", "not_run")
    links = [
        ("审核报告 HTML", file_url(run_id, "reports/audit_report.html")),
        ("问题清单 Excel", file_url(run_id, "reports/issues.xlsx")),
        ("原文批注 DOCX", file_url(run_id, "reports/annotated.docx")),
        ("修复后 DOCX", file_url(run_id, "reports/fixed.docx")),
        ("结构化结果 JSON", file_url(run_id, "reports/result.json")),
        ("迭代画像 JSON", file_url(run_id, "reports/iteration_insights.json")),
    ]
    if result.get("post_fix_summary"):
        links.append(("修复后二次审核 JSON", file_url(run_id, "reports/post_fix_result.json")))
    link_html = "".join(f'<a href="{href}" target="_blank">{html.escape(label)}</a>' for label, href in links)
    body = f"""
<h1>审核完成</h1>
<p class="muted">文件：{html.escape(result["document"]["file_name"])}</p>
<div class="cards">
  <div class="card"><div class="muted">合规得分</div><div class="value">{summary["score"]}</div></div>
  <div class="card"><div class="muted">问题总数</div><div class="value">{summary["total_issues"]}</div></div>
  <div class="card"><div class="muted">可自动修复</div><div class="value">{summary["auto_fixable_issues"]}</div></div>
  <div class="card"><div class="muted">需人工复核</div><div class="value">{summary["manual_required_issues"]}</div></div>
</div>
<div class="links">{link_html}</div>
<p class="muted">自动修复实际应用：{applied_count}；跳过：{skipped_count}。共享 LLM 状态：{html.escape(str(llm_status_value))}。</p>
<p><a href="/">继续上传下一篇</a></p>
<p class="muted">本次运行目录：<code>{html.escape(str(Path(reports["json"]).parent))}</code></p>
"""
    return render_page("审核完成", body)


def render_error_page(message: str) -> bytes:
    return render_page("审核失败", f'<h1>审核失败</h1><div class="error">{html.escape(message)}</div><p><a href="/">返回上传页</a></p>')


def file_url(run_id: str, relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/")
    return f"/files/{quote(run_id)}/{quote(normalized)}"


class LayoutReviewWebHandler(BaseHTTPRequestHandler):
    server_version = "LayoutReviewWeb/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            rules_dir: Path = self.server.rules_dir  # type: ignore[attr-defined]
            self.send_html(render_upload_page(list_profiles(rules_dir)))
            return
        if parsed.path == "/profiles/new":
            self.send_html(render_profile_upload_page())
            return
        if parsed.path == "/llm/status":
            self.send_html(render_llm_status_page())
            return
        if parsed.path.startswith("/files/"):
            self.serve_file(parsed.path)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/profiles/upload":
            try:
                title, details = self.handle_profile_upload()
                if title in {"规则库已自动规范化并启用", "规则库导入成功"}:
                    rules_dir: Path = self.server.rules_dir  # type: ignore[attr-defined]
                    profile_id = generated_profile_id(details)
                    self.send_html(
                        render_upload_page(
                            list_profiles(rules_dir),
                            selected_profile=profile_id or "default_undergraduate",
                            notice=f"{title}，已自动选中：{profile_id}" if profile_id else title,
                        )
                    )
                    return
                self.send_html(render_profile_upload_result(title, details))
            except Exception as exc:
                self.send_html(render_error_page(str(exc)), status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/profiles/normalize":
            try:
                title, details = self.handle_profile_normalize()
                if title == "规则库已自动规范化并启用":
                    rules_dir: Path = self.server.rules_dir  # type: ignore[attr-defined]
                    profile_id = generated_profile_id(details)
                    self.send_html(
                        render_upload_page(
                            list_profiles(rules_dir),
                            selected_profile=profile_id or "default_undergraduate",
                            notice=f"{title}，已自动选中：{profile_id}" if profile_id else title,
                        )
                    )
                    return
                self.send_html(render_profile_upload_result(title, details))
            except Exception as exc:
                self.send_html(render_error_page(str(exc)), status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path != "/audit":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        try:
            result, run_id = self.handle_audit()
            self.send_html(render_result_page(result, run_id))
        except Exception as exc:
            self.send_html(render_error_page(str(exc)), status=HTTPStatus.BAD_REQUEST)

    def handle_audit(self) -> tuple[dict[str, Any], str]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ValueError("没有收到上传内容。")
        if content_length > MAX_UPLOAD_BYTES:
            raise ValueError("文件过大，当前限制为 80MB。")

        content_type = self.headers.get("Content-Type", "")
        body = self.rfile.read(content_length)
        fields, files = parse_multipart(content_type, body)
        if "document" not in files:
            raise ValueError("请上传 .docx 文件。")

        original_name, payload = files["document"]
        if not original_name.lower().endswith(".docx"):
            raise ValueError("当前只支持 .docx 文件。")
        if not payload:
            raise ValueError("上传文件为空。")

        run_id = uuid4().hex
        base_dir: Path = self.server.base_dir  # type: ignore[attr-defined]
        run_dir = base_dir / run_id
        upload_dir = run_dir / "uploads"
        output_dir = run_dir / "reports"
        upload_dir.mkdir(parents=True, exist_ok=True)

        input_path = upload_dir / safe_filename(original_name)
        input_path.write_bytes(payload)

        profile = fields.get("profile", "default_undergraduate").strip() or "default_undergraduate"
        fix_safe = "fix_safe" in fields
        llm_advice = "llm_advice" in fields
        coordinator = LayoutReviewCoordinator(
            profile=profile,
            rules_dir=self.server.rules_dir,  # type: ignore[attr-defined]
            llm_client=build_llm_client(),
            memory_path=base_dir / "review_memory.jsonl",
        )
        result = coordinator.audit(input_path, output_dir, fix_safe=fix_safe, llm_advice=llm_advice)
        return result, run_id

    def handle_profile_upload(self) -> tuple[str, list[str]]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ValueError("没有收到上传内容。")
        if content_length > MAX_UPLOAD_BYTES:
            raise ValueError("文件过大，当前限制为 80MB。")

        content_type = self.headers.get("Content-Type", "")
        body = self.rfile.read(content_length)
        fields, files = parse_multipart(content_type, body)
        if "spec" not in files:
            raise ValueError("请上传学校规范文件或结构化规则库 JSON。")

        original_name, payload = files["spec"]
        if not payload:
            raise ValueError("上传文件为空。")

        filename = safe_storage_filename(original_name, "school_spec")
        suffix = Path(filename).suffix.lower()
        if suffix not in {".json", ".docx", ".pdf", ".txt", ".md"}:
            raise ValueError("仅支持 .json、.docx、.pdf、.txt、.md。")

        rules_dir: Path = self.server.rules_dir  # type: ignore[attr-defined]
        rules_dir.mkdir(parents=True, exist_ok=True)
        source_dir = rules_dir / "_sources"
        source_dir.mkdir(parents=True, exist_ok=True)

        if suffix == ".json":
            return self.install_rule_profile_json(rules_dir, filename, payload)
        return self.save_official_spec_source(rules_dir, source_dir, filename, payload, fields)

    def handle_profile_normalize(self) -> tuple[str, list[str]]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ValueError("没有收到规则库信息。")
        body = self.rfile.read(content_length)
        fields = parse_urlencoded(body)
        profile_id = safe_profile_id(fields.get("profile_id", ""))
        if not profile_id:
            raise ValueError("缺少规则库 ID。")

        rules_dir: Path = self.server.rules_dir  # type: ignore[attr-defined]
        profile_path = rules_dir / f"{profile_id}.json"
        if not profile_path.exists():
            raise ValueError(f"规则库草稿不存在：{profile_id}")
        try:
            raw = json.loads(profile_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"规则库草稿 JSON 格式错误：{exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError("规则库草稿顶层必须是对象。")
        source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
        uploaded_file = str(source.get("uploaded_file", ""))
        if not uploaded_file:
            raise ValueError("这个草稿没有记录原始规范文件，无法自动规范化。")
        source_path = Path(uploaded_file)
        if not source_path.is_absolute():
            source_path = rules_dir / source_path
        source_path = source_path.resolve()
        source_root = (rules_dir / "_sources").resolve()
        if not str(source_path).startswith(str(source_root)) or not source_path.exists():
            raise ValueError("原始规范文件不存在或不在 rule_profiles/_sources 目录。")

        filename = safe_storage_filename(str(source.get("document_name") or source_path.name), "school_spec")
        display_name = str(raw.get("display_name") or profile_id)
        if display_name.endswith("待录入规则库"):
            display_name = f"{Path(filename).stem} 论文格式规范"
        version = str(raw.get("version") or "2026.1")
        payload = source_path.read_bytes()
        return self.write_active_profile_from_spec(
            rules_dir=rules_dir,
            profile_id=profile_id,
            display_name=display_name,
            version=version,
            source_path=source_path,
            filename=filename,
            payload=payload,
            source={
                **source,
                "uploaded_file": str(source_path),
                "normalization": "llm_or_local_generated_from_existing_draft",
                "note": "规则由已保存的学校官方规范自动规范化生成，审核仍以此 JSON 的确定性规则为准。",
            },
        )

    def install_rule_profile_json(self, rules_dir: Path, filename: str, payload: bytes) -> tuple[str, list[str]]:
        try:
            raw = json.loads(payload.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ValueError("JSON 规则库必须使用 UTF-8 编码。") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 规则库格式错误：{exc}") from exc

        if not isinstance(raw, dict):
            raise ValueError("JSON 规则库顶层必须是对象。")
        errors = validate_profile_data(raw)
        if errors:
            raise ValueError("规则库校验失败：" + "；".join(errors))

        profile_id = safe_profile_id(str(raw["profile_id"]))
        raw["profile_id"] = profile_id
        target = rules_dir / f"{profile_id}.json"
        target.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return (
            "规则库导入成功",
            [
                f"规则库：{raw.get('display_name', profile_id)}",
                f"规则 ID：{profile_id}",
                f"保存位置：{target}",
                "刷新论文上传页后，可在学校规则库下拉框中选择它。",
            ],
        )

    def save_official_spec_source(
        self,
        rules_dir: Path,
        source_dir: Path,
        filename: str,
        payload: bytes,
        fields: dict[str, str],
    ) -> tuple[str, list[str]]:
        profile_id = safe_profile_id(fields.get("profile_id", "") or Path(filename).stem)
        display_name = fields.get("display_name", "").strip() or f"{profile_id} 论文格式规范"
        version = fields.get("version", "").strip() or "2026.1"
        source_path = source_dir / f"{profile_id}_{filename}"
        source_path.write_bytes(payload)
        source = {
            "type": "uploaded_school_spec",
            "school": fields.get("school", "").strip(),
            "degree_level": fields.get("degree_level", "").strip(),
            "document_name": filename,
            "uploaded_file": str(source_path),
        }
        try:
            return self.write_active_profile_from_spec(
                rules_dir=rules_dir,
                profile_id=profile_id,
                display_name=display_name,
                version=version,
                source_path=source_path,
                filename=filename,
                payload=payload,
                source={
                    **source,
                    "normalization": "llm_or_local_generated_from_uploaded_spec",
                    "note": "规则由上传的学校官方规范自动规范化生成，审核仍以此 JSON 的确定性规则为准。",
                },
            )
        except SpecNormalizationError as exc:
            return self.write_disabled_draft(
                rules_dir,
                profile_id,
                display_name,
                version,
                source,
                source_path,
                filename,
                f"自动规范化失败：{exc}",
            )

    def write_active_profile_from_spec(
        self,
        *,
        rules_dir: Path,
        profile_id: str,
        display_name: str,
        version: str,
        source_path: Path,
        filename: str,
        payload: bytes,
        source: dict[str, Any],
    ) -> tuple[str, list[str]]:
        llm_client = build_llm_client()
        spec_text = extract_spec_text(filename, payload)
        result = normalize_spec_to_profile(
            spec_text=spec_text,
            profile_id=profile_id,
            display_name=display_name,
            version=version,
            source=source,
            llm_client=llm_client,
        )

        generated_dir = rules_dir / "_generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        profile_path = rules_dir / f"{profile_id}.json"
        prompt_path = generated_dir / f"{profile_id}_prompt.txt"
        response_path = generated_dir / f"{profile_id}_response.txt"
        profile_path.write_text(json.dumps(result.profile, ensure_ascii=False, indent=2), encoding="utf-8")
        prompt_path.write_text(result.prompt, encoding="utf-8")
        response_path.write_text(result.response, encoding="utf-8")
        details = [
            f"规范来源文件：{source_path}",
            f"可选规则库：{profile_path}",
            f"规则 ID：{profile_id}",
            f"抽取规范文本：{result.source_text_chars} 字，送入模型：{result.used_text_chars} 字。",
            f"生成规则数：{len(result.profile.get('rules', []))}",
            f"必备模块数：{len(result.profile.get('required_sections', []))}",
            f"提示词留档：{prompt_path}",
            f"模型返回留档：{response_path}",
            "返回论文上传页后，可在学校规则库下拉框中选择它。",
        ]
        details.extend(result.notes)
        return ("规则库已自动规范化并启用", details)

    def write_disabled_draft(
        self,
        rules_dir: Path,
        profile_id: str,
        display_name: str,
        version: str,
        source: dict[str, Any],
        source_path: Path,
        filename: str,
        reason: str,
    ) -> tuple[str, list[str]]:
        draft = {
            "profile_id": profile_id,
            "display_name": display_name,
            "version": version,
            "is_demo": False,
            "is_template": True,
            "is_draft": True,
            "source": {
                **source,
                "note": reason,
            },
            "description": "待规范化为学校官方格式规则。上传规范文件本身不会自动成为可靠审核规则。",
            "rules": [],
            "required_sections": [],
        }
        draft_path = rules_dir / f"{profile_id}.json"
        draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        return (
            "学校规范已保存，规则库草稿已生成",
            [
                f"规范来源文件：{source_path}",
                f"草稿规则库：{draft_path}",
                reason,
                "该草稿暂不会出现在可用审核规则中，因为它还没有具体 rules。",
                "配置 LLM 后重新上传同一份规范，系统会自动规范化并启用。",
            ],
        )

    def serve_file(self, request_path: str) -> None:
        parts = request_path.removeprefix("/files/").split("/", 1)
        if len(parts) != 2:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        run_id = unquote(parts[0])
        relative = unquote(parts[1])
        base_dir: Path = self.server.base_dir  # type: ignore[attr-defined]
        target = (base_dir / run_id / relative).resolve()
        base = (base_dir / run_id).resolve()
        if not str(target).startswith(str(base)) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()
        with target.open("rb") as file:
            self.wfile.write(file.read())

    def send_html(self, content: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web] {self.address_string()} - {format % args}")


def build_server(host: str, port: int, base_dir: str | Path, rules_dir: str | Path = DEFAULT_RULES_DIR) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), LayoutReviewWebHandler)
    server.base_dir = Path(base_dir).resolve()  # type: ignore[attr-defined]
    server.base_dir.mkdir(parents=True, exist_ok=True)  # type: ignore[attr-defined]
    server.rules_dir = Path(rules_dir).resolve()  # type: ignore[attr-defined]
    server.rules_dir.mkdir(parents=True, exist_ok=True)  # type: ignore[attr-defined]
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local web UI for DOCX layout review.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--base-dir", default=DEFAULT_BASE_DIR, help="Directory used for uploaded files and reports.")
    parser.add_argument("--rules-dir", default=DEFAULT_RULES_DIR, help="Directory for school rule profiles.")
    args = parser.parse_args(argv)

    server = build_server(args.host, args.port, args.base_dir, args.rules_dir)
    host, port = server.server_address
    print(f"排版审核智能体网页已启动: http://{host}:{port}")
    status = llm_status()
    print(f"LLM 状态: {'已配置' if status['enabled'] else '未配置'}")
    if status["enabled"]:
        print(f"LLM 模型: {status['model']} URL: {status['chat_completions_url']}")
    print("按 Ctrl+C 停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
