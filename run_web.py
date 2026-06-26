from __future__ import annotations

import sys
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from layout_review_agent.web import build_server  # noqa: E402
except ModuleNotFoundError as exc:
    missing = exc.name or ""
    if missing == "docx":
        print("启动失败：当前 Python 解释器缺少依赖 python-docx。")
        print("在 PyCharm 里安装依赖：Settings -> Project -> Python Interpreter -> + -> 搜索 python-docx 并安装。")
        print("还需要确认 openpyxl、lxml 也已安装。")
        print("或者把 PyCharm 解释器切换到已验证可用的 Python 3.12。")
        raise SystemExit(1) from exc
    raise


def main() -> int:
    host = "127.0.0.1"
    port = 8000
    base_dir = ROOT / "web_runs"
    try:
        server = build_server(host, port, base_dir, ROOT / "rule_profiles")
    except OSError:
        port = 8001
        server = build_server(host, port, base_dir, ROOT / "rule_profiles")

    actual_host, actual_port = server.server_address
    url = f"http://{actual_host}:{actual_port}"
    print(f"排版审核智能体网页已启动: {url}")
    print("如果浏览器没有自动打开，请复制上面的地址手动打开。")
    print("保持这个运行窗口不要关闭；点击红色停止按钮才会关闭服务。")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
