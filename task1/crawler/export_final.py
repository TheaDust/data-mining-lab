"""将成功批次导出为可提交的固定交付：正文和 doc_id 不变，移除分享参数。"""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from .quality_check import check_csv


def export(source: Path, target: Path) -> None:
    source, target = source.resolve(), target.resolve()
    records = [json.loads(line) for line in (source/'processed/documents.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    if len(records) != 18:
        raise ValueError('正式交付应为已确认的 18 条记录')
    target.mkdir(parents=True, exist_ok=True)
    provenance = []
    for record in records:
        # 仅规范来源链接，不重跑 cleaner，避免改变后续实验依赖的字符位置。
        url = urlsplit(record['url'])
        if url.hostname == 'www.xiaohongshu.com':
            record['url'] = urlunsplit((url.scheme, url.netloc, url.path, '', ''))
        raw = source/record['raw_html_path']
        provenance.append(dict(doc_id=record['doc_id'], url=record['url'], raw_filename=raw.name,
                               raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest()))
        # 相对路径从交付目录出发；原件不进入 Git，但本机仍能定位。
        import os
        record['raw_html_path'] = Path(os.path.relpath(raw, target)).as_posix()
    (target/'documents.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    with (target/'documents.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    for name in ('cleaning_audit.json','content_preservation_check.json'):
        shutil.copy2(source/name,target/name)
    (target/'provenance.json').write_text(json.dumps(dict(source_batch=source.name,raw_files_tracked=False,records=provenance),ensure_ascii=False,indent=2),encoding='utf-8')
    attempts=[dict(url=r['url'],scenic_spot=r['scenic_spot'],status='success') for r in records]
    check_csv(target/'documents.csv',attempts,report_dir=target)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('source',type=Path)
    cli.add_argument('--target',type=Path,default=Path('task1/data/final'))
    args=cli.parse_args()
    export(args.source,args.target)
