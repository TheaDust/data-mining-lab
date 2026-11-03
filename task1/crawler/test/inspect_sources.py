"""仅下载五个适配样本，保存原件供离线解析调试。"""
import json
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from ..static_crawler import fetch_html
from ..dynamic_crawler import fetch_html as dynamic_html
from ..static_crawler import fetch_bytes
from requests.exceptions import SSLError
from ..document_pipeline import process

SITES = [
    ('gugong', '北京故宫', '故宫博物院官网', 'https://www.dpm.org.cn/Visit.html'),
    ('xihu', '杭州西湖', '杭州市文化广电旅游局', 'https://wgly.hangzhou.gov.cn/module/download/downfile.jsp?classid=0&filename=c3ccb4250d3143a09047ee20fbe1170c.pdf'),
    ('huangshan', '黄山', '黄山旅游官网', 'https://wap.huangshan.com.cn/detail/strategy/fjqlyzx'),
    ('zhangjiajie', '张家界', '湖南省文化和旅游厅', 'https://whhlyt.hunan.gov.cn/whhlyt/wldhlylx/202208/t20220816_27584140.html'),
    ('jiuzhaigou', '九寨沟', '九寨沟官网', 'https://www.jiuzhai.com/intelligent-service'),
]

def main():
    root = Path(__file__).resolve().parents[1] / 'results' / datetime.now().strftime('task1_%Y%m%d_%H%M%S_%f')
    (root / 'raw').mkdir(parents=True)
    records = []
    for slug, spot, source, url in SITES:
        row = dict(slug=slug, scenic_spot=spot, source_name=source, url=url)
        try:
            mode = 'dynamic' if slug == 'huangshan' else 'static'
            if slug == 'xihu':
                data = fetch_bytes(url, timeout=30)
                path = root / 'raw' / (slug + '.pdf')
                path.write_bytes(data)
                print(slug, data[:80], len(data), flush=True)
            else:
                try:
                    html = (dynamic_html if mode == 'dynamic' else fetch_html)(url)
                except SSLError as exc:
                    # requests 与 Chrome 的 TLS 实现不同；保留验证并改用 Chrome，不关闭证书校验。
                    row['previous_error'] = str(exc)
                    mode = 'dynamic'
                    html = dynamic_html(url)
                path = root / 'raw' / (slug + '.html')
                path.write_text(html, encoding='utf-8')
                soup = BeautifulSoup(html, 'html.parser')
                print(slug, soup.get_text(' ', strip=True)[:1200], flush=True)
            row.update(crawler_type=mode, crawl_time=datetime.now().astimezone().isoformat(), raw_file=str(path.resolve()))
        except Exception as exc:
            row.update(crawler_type=mode, crawl_time=datetime.now().astimezone().isoformat())
            row['error'] = str(exc)
            print(slug, str(exc), flush=True)
        records.append(row)
        (root / 'manifest.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    print(root.resolve())
    report = process(root.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(any(r['status'] == 'failed' for r in report))

if __name__ == '__main__':
    raise SystemExit(main())
