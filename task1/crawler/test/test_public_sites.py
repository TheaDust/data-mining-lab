"""测试指定的两个公开网站，并按运行时间保存 HTML 和结果摘要。"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter

from bs4 import BeautifulSoup

if __package__:
    from ..dynamic_crawler import fetch_html as fetch_dynamic
    from ..static_crawler import fetch_html as fetch_static
else:
    # 保留直接运行脚本的用法，与模块运行使用相同的采集实现。
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from dynamic_crawler import fetch_html as fetch_dynamic
    from static_crawler import fetch_html as fetch_static


SITES = {
    "palace_museum": "https://www.dpm.org.cn/Visit.html",
    "zhangjiajie": "https://www.discoverzhangjiajie.org/zh/guidebook/routes/index.html",
}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # 每次独立归档，避免覆盖上次实验；带时区的时间便于追溯网络测试结果。
    now = datetime.now().astimezone()
    output = Path(__file__).resolve().parents[1] / "results" / now.strftime("%Y%m%d_%H%M%S_%f")
    output.mkdir(parents=True, exist_ok=False)
    summary = {"started_at": now.isoformat(), "results": []}
    for site, url in SITES.items():
        for mode, fetch in (("static", fetch_static), ("dynamic", fetch_dynamic)):
            record = {"site": site, "url": url, "crawler": mode}
            started = perf_counter()
            try:
                html = fetch(url)
                if not html.strip():
                    raise ValueError("返回的 HTML 为空")
                site_dir = output / site
                site_dir.mkdir(exist_ok=True)
                html_path = site_dir / f"{mode}.html"
                html_path.write_text(html, encoding="utf-8")
                # 通用页面信息在调用方解析，不让采集器依赖具体站点的 HTML。
                soup = BeautifulSoup(html, "html.parser")
                title = soup.title.get_text(strip=True) if soup.title else ""
                text = soup.get_text(" ", strip=True)
                record.update(
                    success=True,
                    title=title,
                    html_chars=len(html),
                    text_preview=text[:500],
                    html_file=html_path.relative_to(output).as_posix(),
                )
                print(f"{site}/{mode}: OK, title={title}, chars={len(html)}", flush=True)
            except Exception as exc:
                # 失败也留存诊断，并继续其他组合，避免单站故障中断整个实验。
                record.update(success=False, error_type=type(exc).__name__, error=str(exc))
                logging.exception("%s/%s 采集失败", site, mode)
            record["elapsed_seconds"] = round(perf_counter() - started, 3)
            summary["results"].append(record)
            (output / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    print(f"结果目录：{output.resolve()}", flush=True)
    return int(any(not row["success"] for row in summary["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
