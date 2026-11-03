"""从已归档原件生成 Document Schema 1.0；失败记录不混入文档主表。"""
import argparse
import hashlib
import json
import csv
import logging
from pathlib import Path
from .parsers.template_parser import TemplateParser
from .parsers.pdf_parser import PdfParser
from .cleaner import clean_text, clean_with_audit
from .quality_check import check_csv

PARSERS = {'gugong': 'dpm_visit', 'huangshan': 'huangshan_strategy',
           'zhangjiajie': 'hunan_article', 'jiuzhaigou': 'jiuzhai_service', 'xihu': 'pdf_text'}


def validate_document(doc: dict) -> None:
    required = ('doc_id scenic_spot source_type source_name url text_type title crawl_time crawler_type raw_text clean_text').split()
    for key in required:
        if not isinstance(doc.get(key), str) or not doc[key].strip():
            raise ValueError(f'字段缺失或类型错误: {key}')
    for key in ('author', 'publish_time'):
        if doc.get(key) is not None and not isinstance(doc[key], str):
            raise ValueError(f'字段类型错误: {key}')
    for key, allowed in [('source_type', {'official', 'user_generated'}),
                         ('text_type', {'official_route', 'travel_note'}),
                         ('crawler_type', {'static', 'dynamic'})]:
        if doc[key] not in allowed:
            raise ValueError(f'枚举错误: {key}')


def process(root: Path) -> list:
    rows = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    documents, report, audits = [], [], []
    for row in rows:
        name = row.get('parser') or PARSERS[row['slug']]
        result = dict(url=row['url'], scenic_spot=row['scenic_spot'], parser=name, crawler_type=row.get('crawler_type', 'static'))
        stage = 'crawler' if 'error' in row else 'parser'
        try:
            if 'error' in row:
                raise ValueError(row['error'])
            path = Path(row['raw_file'])
            from .parsers.formal_parser import FormalParser, FORMAL_NAMES
            parser = FormalParser(name) if name in FORMAL_NAMES else TemplateParser(name) if name != 'pdf_text' else PdfParser()
            parsed = parser.parse(path.read_bytes() if name == 'pdf_text' else path.read_text(encoding='utf-8'))
            # URL 哈希保证跨运行稳定且不依赖输入列表次序。
            from urllib.parse import urlsplit, urlunsplit
            parts=urlsplit(row['url'])
            identity=urlunsplit((parts.scheme,parts.netloc,parts.path,'','')) if name=='xiaohongshu_note' else row['url']
            source_type=row.get('source_type','official')
            doc = dict(doc_id=f"{row['slug']}_{source_type}_{hashlib.sha256(identity.encode()).hexdigest()[:16]}",
                       scenic_spot=row['scenic_spot'], source_type=source_type, source_name=row['source_name'],
                       url=row['url'], text_type=row.get('text_type','official_route'), crawl_time=row['crawl_time'],
                       crawler_type=row['crawler_type'], **parsed)
            stage='cleaner'
            doc['clean_text'], audit = clean_with_audit(doc['raw_text'])
            audits.append(dict(doc_id=doc['doc_id'], **audit))
            doc['raw_html_path'] = path.relative_to(root).as_posix() if path.suffix == '.html' else None
            doc['notes'] = row.get('notes', '官方页采用 official_route，可能包含综合导览；未进行语义抽取。' if source_type=='official' else '游客正文按 DOM 顺序保留；未进行语义抽取。')
            validate_document(doc)
            documents.append(doc)
            result.update(status='success', title=doc['title'], author=doc['author'], publish_time=doc['publish_time'],
                          raw_chars=len(doc['raw_text']), clean_chars=len(doc['clean_text']))
        except Exception as exc:
            result.update(status='failed', failure_stage=stage, error=str(exc), needs_replacement=True)
            if row.get('raw_file') and name=='xiaohongshu_note':
                from bs4 import BeautifulSoup
                visible=BeautifulSoup(Path(row['raw_file']).read_text(encoding='utf-8'),'html.parser').get_text(' ',strip=True)
                result['page_message']=visible[:400]
            logging.error('处理失败 %s %s %s',row['url'],stage,str(exc))
        report.append(result)
    (root / 'processed').mkdir(exist_ok=True)
    (root / 'processed/documents.jsonl').write_text(''.join(json.dumps(d, ensure_ascii=False)+'\n' for d in documents), encoding='utf-8')
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (root / 'failures.json').write_text(json.dumps([r for r in report if r['status']=='failed'], ensure_ascii=False, indent=2), encoding='utf-8')
    fields = ('doc_id scenic_spot source_type source_name url text_type title author publish_time crawl_time crawler_type raw_text clean_text raw_html_path notes').split()
    csv_path = root / 'processed/documents.csv'
    # utf-8-sig 便于 Windows Excel 直接读取中文；csv 模块正确转义正文换行与引号。
    with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(documents)
    (root/'cleaning_audit.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf-8')
    check_csv(csv_path, report)
    return report


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('result_dir', type=Path)
    print(json.dumps(process(cli.parse_args().result_dir.resolve()), ensure_ascii=False, indent=2))
