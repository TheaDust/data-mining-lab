"""公开网页冒烟测试，可直接运行或作为模块运行。"""

import argparse
import logging
import sys
from pathlib import Path

from bs4 import BeautifulSoup

if __package__:
    from ..dynamic_crawler import fetch_html as fetch_dynamic
    from ..static_crawler import fetch_html as fetch_static
else:
    # 直接运行文件时 Python 只加入 test 目录，需要补充采集模块所在目录。
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from dynamic_crawler import fetch_html as fetch_dynamic
    from static_crawler import fetch_html as fetch_static


def print_summary(label: str, html: str) -> None:
    # 演示解析放在调用方，避免让 crawler 绑定任何页面结构。
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else "（无 title）"
    print(f"[{label}] title={title}; HTML 长度={len(html)}")
    print(html[:160].replace("\n", " "))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://example.com")
    parser.add_argument("--headed", action="store_true", help="显示 Chrome 窗口")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    failed = False
    # 单项失败后继续另一项，最终通过非零退出码明确报告失败。
    for label, fetch in (
        ("static", lambda: fetch_static(args.url)),
        ("dynamic", lambda: fetch_dynamic(args.url, headless=not args.headed)),
    ):
        try:
            html = fetch()
            if not html.strip():
                raise ValueError("返回的 HTML 为空")
            print_summary(label, html)
        except Exception:
            logging.exception("%s 冒烟测试失败", label)
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
