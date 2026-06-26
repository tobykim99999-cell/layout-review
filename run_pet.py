from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from layout_review_agent.pet import main  # noqa: E402
except ModuleNotFoundError as exc:
    missing = exc.name or ""
    if missing == "docx":
        print("启动失败：当前 Python 解释器缺少依赖 python-docx。")
        print("在 PyCharm 里安装依赖：Settings -> Project -> Python Interpreter -> + -> 搜索 python-docx 并安装。")
        print("还需要确认 openpyxl、lxml 也已安装。")
        raise SystemExit(1) from exc
    raise


if __name__ == "__main__":
    raise SystemExit(main())
