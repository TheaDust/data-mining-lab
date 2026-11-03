"""读取最终 CSV 检查质量；只报告，不自动修正数据。"""
import csv
import hashlib
import json
import re
from collections import Counter
from itertools import groupby
from pathlib import Path


def check_csv(path: Path, attempts: list, *, report_dir: Path | None = None) -> dict:
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        rows = list(reader)
    def duplicates(values):
        return {k: n for k, n in Counter(values).items() if n > 1}
    details = []
    for row in rows:
        raw, clean = row['raw_text'], row['clean_text']
        lines = clean.splitlines()
        run = max((len(list(group)) for _, group in groupby(lines)), default=0)
        # 乱码检测仅标记高可信的替代字符和常见误解码片段，不擅自猜测原文。
        signals = {m: clean.count(m) for m in ('\ufffd', '锟斤拷', '烫烫烫', 'Ã', 'Â') if m in clean}
        raw_signals = {m: raw.count(m) for m in ('\ufffd', '锟斤拷', '烫烫烫', 'Ã', 'Â') if m in raw}
        details.append(dict(doc_id=row['doc_id'], scenic_spot=row['scenic_spot'],
                            raw_chars=len(raw), clean_chars=len(clean), removed_chars=len(raw)-len(clean),
                            change_ratio=round((len(raw)-len(clean))/max(len(raw), 1), 4),
                            garbled_signals=signals, raw_garbled_signals=raw_signals, max_consecutive_identical_lines=run,
                            excessive_repeated_lines=run >= 5,
                            raw_sample=raw[:600], clean_sample=clean[:600],
                            warnings=(['字符变化较大，请结合原件复核'] if len(clean)<len(raw)*0.5 else [])
                            + (['疑似乱码，请人工复核'] if signals else [])))
    report = dict(total_records=len(rows), attempted_urls=len(attempts),
                  successful_urls=sum(a['status']=='success' for a in attempts),
                  failed_urls=sum(a['status']=='failed' for a in attempts),
                  sample_coverage={spot:{'available':sum(r['scenic_spot']==spot for r in rows),'requested':2,'shortfall':max(0,2-sum(r['scenic_spot']==spot for r in rows))} for spot in sorted({a.get('scenic_spot','未知') for a in attempts})},
                  per_spot_text_type={spot:dict(Counter(r['text_type'] for r in rows if r['scenic_spot']==spot)) for spot in sorted({a.get('scenic_spot','未知') for a in attempts})},
                  failures=[a for a in attempts if a['status']=='failed'],
                  per_scenic_spot={a: sum(r['scenic_spot']==a for r in rows) for a in
                                   ['北京故宫','杭州西湖','黄山','张家界','九寨沟']},
                  missing_fields={f: sum(not r[f].strip() for r in rows) for f in fields},
                  empty_raw_text=sum(not r['raw_text'].strip() for r in rows),
                  empty_clean_text=sum(not r['clean_text'].strip() for r in rows),
                  duplicate_urls=duplicates(r['url'] for r in rows),
                  duplicate_doc_ids=duplicates(r['doc_id'] for r in rows),
                  duplicate_documents=duplicates(hashlib.sha256(r['clean_text'].encode()).hexdigest() for r in rows),
                  duplicate_definition='clean_text 完全相同；不做语义或近似去重',
                  garbled_detection_limit='启发式检查，不能保证发现所有乱码；只报警，不自动纠正', records=details)
    root = report_dir if report_dir is not None else path.parent.parent
    (root/'quality_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    sections = ['# Task1 CSV 质量检查', f"总记录数：{len(rows)}；尝试 URL：{len(attempts)}；失败：{len(report['failures'])}。",
                '## 统计', '```json\n'+json.dumps({k:v for k,v in report.items() if k!='records'}, ensure_ascii=False,indent=2)+'\n```']
    for d in details:
        sections += [f"## {d['scenic_spot']} / {d['doc_id']}",
                     f"字符数：{d['raw_chars']} → {d['clean_chars']}；最大连续重复行：{d['max_consecutive_identical_lines']}；乱码信号：{d['garbled_signals']}；警告：{d['warnings']}",
                     '清洗前（前 600 字符）：\n```text\n'+d['raw_sample']+'\n```',
                     '清洗后（前 600 字符）：\n```text\n'+d['clean_sample']+'\n```']
    (root/'QUALITY_REPORT.md').write_text('\n\n'.join(sections), encoding='utf-8')
    return report
