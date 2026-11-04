"""Offline task 5: python -X utf8 task5/run.py."""
from collections import Counter
import csv
import hashlib
from html import escape
import json
from pathlib import Path

if __package__:
    from .extract import TYPE_LABELS, anchor, contexts, extract, group_mappings, make_pair, nearby_context
else:
    from extract import TYPE_LABELS, anchor, contexts, extract, group_mappings, make_pair, nearby_context


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'task1/data/final/documents.jsonl'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def check_anchor(value, text):
    a, b = value['start'], value['end']
    if not (0 <= a < b <= len(text) and text[a:b] == value['text']):
        raise ValueError(f'Invalid source anchor: {value}')


def validate(pairs, documents):
    by_id = {d['doc_id']: d for d in documents}
    seen, checks = set(), 0
    for pair in pairs:
        if pair['advice_id'] in seen:
            raise ValueError('Duplicate advice ID')
        seen.add(pair['advice_id'])
        doc = by_id[pair['doc_id']]
        if pair['scenic_spot'] != doc['scenic_spot'] or pair['url'] != doc['url']:
            raise ValueError('Source metadata mismatch')
        text = doc['clean_text']
        check_anchor({'text': pair['source_sentence'], 'start': pair['start'], 'end': pair['end']}, text)
        checks += 1
        for name in ('condition', 'advice'):
            span = pair[name + '_span']
            check_anchor(span, text)
            if pair[name] != span['text'] or not (pair['start'] <= span['start'] < span['end'] <= pair['end']):
                raise ValueError('Pair span outside source window')
            checks += 1
        if pair['context']:
            check_anchor(pair['context'], text)
            checks += 1
        if pair['condition_type'] not in pair['condition_types'] or any(t not in TYPE_LABELS for t in pair['condition_types']):
            raise ValueError('Invalid condition type')
    return checks


def apply_reviews(pairs, documents, reviews):
    """Apply explicit local review decisions; no automatic human-confirmed labels."""
    rows = {p['advice_id']: p.copy() for p in pairs}
    by_id = {d['doc_id']: d for d in documents}
    log = []
    for review in reviews:
        action = review['action']
        previous = review.get('advice_id')
        if action in ('reject', 'replace', 'confirm') and previous not in rows:
            raise ValueError(f'Review targets an unknown advice ID: {previous}')
        if action == 'confirm':
            rows[previous]['review_status'] = 'reviewed'
            updated = previous
        elif action == 'reject':
            del rows[previous]
            updated = None
        elif action in ('add', 'replace'):
            doc = by_id[review['doc_id']]
            original = rows[previous] if action == 'replace' else None
            ca, cb, aa, ab = (review[k] for k in ('condition_start', 'condition_end', 'advice_start', 'advice_end'))
            if not (0 <= ca < cb <= len(doc['clean_text']) and 0 <= aa < ab <= len(doc['clean_text'])):
                raise ValueError('Review offsets are outside clean_text')
            context = nearby_context(contexts(doc['clean_text']), ca)
            if original and original['doc_id'] == doc['doc_id'] and (ca, cb) == (original['condition_span']['start'], original['condition_span']['end']):
                context = original['context']
            if 'context_start' in review or 'context_end' in review:
                context = anchor(doc['clean_text'], review['context_start'], review['context_end'])
                check_anchor(context, doc['clean_text'])
                context['usable'] = True
            relation = review.get('relation', original['relation'] if original else 'recommendation')
            new = make_pair(doc, (ca, cb), (aa, ab), (min(ca, aa), max(cb, ab)), 'review', context=context, relation=relation)
            if not new:
                raise ValueError('Review contains an empty condition or advice')
            if 'condition_type' in review:
                new['condition_type'] = review['condition_type']
                new['condition_types'] = [review['condition_type']]
            new['review_status'] = 'reviewed'
            if action == 'replace':
                del rows[previous]
            updated = new['advice_id']
            if updated in rows:
                raise ValueError('Review would duplicate an existing pair')
            rows[updated] = new
        else:
            raise ValueError(f'Unknown review action: {action}')
        log.append({'action': action, 'previous_id': previous, 'result_id': updated, 'note': review.get('note', '')})
    return sorted(rows.values(), key=lambda p: (p['doc_id'], p['condition_span']['start'])), log


def plot(path, title, types, series):
    """Grouped bars, one exclusive primary category per mapping or occurrence."""
    colors = ['#246f96', '#218474', '#ba7735']
    bar_height = 20
    row_height = 28 + bar_height * len(series)
    height = 112 + row_height * len(types)
    peak = max((counts.get(t, 0) for _, counts in series for t in types), default=1) or 1
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}">',
           f'<title>{escape(title)}</title>', '<rect width="100%" height="100%" fill="#f4f8fc"/>',
           '<g font-family="Microsoft YaHei, Noto Sans CJK SC, sans-serif" fill="#182c43">',
           f'<text x="24" y="35" font-size="22" font-weight="bold">{escape(title)}</text>',
           '<text x="24" y="58" font-size="14">主类别互斥计数；单位：条</text>']
    for j, (label, _) in enumerate(series):
        x = 24 + j * 240
        svg += [f'<rect x="{x}" y="73" width="14" height="14" fill="{colors[j % len(colors)]}"/>',
                f'<text x="{x + 22}" y="85" font-size="14">{escape(label)}</text>']
    for i, kind in enumerate(types):
        y = 112 + i * row_height
        svg.append(f'<text x="205" y="{y + 15}" text-anchor="end" font-size="15">{escape(TYPE_LABELS[kind])}</text>')
        for j, (_, counts) in enumerate(series):
            count = counts.get(kind, 0)
            width = 610 * count / peak
            top = y + j * bar_height
            svg += [f'<rect x="225" y="{top}" width="{width:.2f}" height="16" rx="2" fill="{colors[j % len(colors)]}"/>',
                    f'<text x="{235 + width:.2f}" y="{top + 13}" font-size="13">{count}</text>']
    path.write_text('\n'.join(svg + ['</g></svg>']) + '\n', encoding='utf-8')


def write_review(path, pairs, candidates, documents):
    if path.exists():
        return
    selected = []
    # Cover scene × source first, then primary types, without pretending random sampling.
    for field in (('scenic_spot', 'source_type'), ('condition_type',)):
        seen = set()
        for pair in pairs:
            key = tuple(pair[k] for k in field)
            if key not in seen:
                seen.add(key)
                if pair not in selected:
                    selected.append(pair)
    lines = ['# 条件建议人工复核清单', '', '此文件仅在缺失时生成，重跑保留手写内容。所有人工确认默认待填写。',
             '下列是按景区×来源及主类别定向选择的样例，不是随机样本，不用于推算整体准确率。', '',
             '核对条件、建议、否定、对象、跨行边界和分类；将确认、剔除、替换或补充结果写入 task5/reviews.json 后重跑。', '']
    for p in selected:
        lines += [f"## {p['scenic_spot']} · {p['condition_type']} · {p['advice_id']}", '',
                  f"文档：`{p['doc_id']}`　来源：[{p['source_name']}]({p['url']})", '',
                  '~~~~text', p['source_sentence'], '~~~~',
                  f"- 条件：{p['condition']} [{p['condition_span']['start']},{p['condition_span']['end']})",
                  f"- 建议：{p['advice']} [{p['advice_span']['start']},{p['advice_span']['end']})",
                  f"- 上下文：{p['context']['text'] if p['context'] else '未绑定标题，需结合原文判断'}",
                  '- 人工确认及修改：待填写。', '']
    lines += ['## 候选排除抽查', '', '以下候选未形成条件建议对；请同时检查是否漏抽。', '']
    for spot in dict.fromkeys(d['scenic_spot'] for d in documents):
        excluded = [c for c in candidates if c['scenic_spot'] == spot and not c['proposed_ids']][:2]
        for c in excluded:
            lines += [f"- `{c['doc_id']}` [{c['start']},{c['end']})：{c['text']}", '  - 人工判断：待填写。']
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_mapping(path, mappings, pairs):
    by_id = {p['advice_id']: p for p in pairs}
    lines = ['# 条件 → 建议映射表', '', '按主类别归类，合并组保留所有来源提及。完整位置和复核状态见 JSON。', '',
             '| ID | 景区 | 条件类型 | 条件 | 建议或适用方案 | 来源提及数 |', '|---|---|---|---|---|---|']
    for group in mappings:
        clean = lambda s: s.replace('|', '／').replace('\n', ' ')
        lines.append('| ' + ' | '.join([group['mapping_id'], group['scenic_spot'], TYPE_LABELS[group['condition_type']], clean(group['condition']), clean(group['advice']), str(len(group['occurrences']))]) + ' |')
    lines += ['', '## 来源索引', '']
    for group in mappings:
        refs = [by_id[k] for k in group['occurrences']]
        lines.append(f"- `{group['mapping_id']}`：" + '；'.join(f"`{p['doc_id']}` [{p['start']},{p['end']})" for p in refs))
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    documents = [json.loads(s) for s in SOURCE.read_text(encoding='utf-8').splitlines() if s.strip()]
    automatic, candidates, duplicates = extract(documents)
    pairs, review_log = apply_reviews(automatic, documents, load(ROOT / 'reviews.json'))
    checks = validate(pairs, documents)
    mappings = group_mappings(pairs)
    out = ROOT / 'results'
    out.mkdir(exist_ok=True)
    dump(out / 'condition_advices.json', pairs)
    dump(out / 'mappings.json', mappings)
    dump(out / 'candidate_audit.json', candidates)
    dump(out / 'duplicates.json', duplicates)
    dump(out / 'review_log.json', review_log)
    counts = Counter(g['condition_type'] for g in mappings)
    types = [t for t in TYPE_LABELS if counts[t]]
    spots = list(dict.fromkeys(d['scenic_spot'] for d in documents))
    by_spot = {s: Counter(g['condition_type'] for g in mappings if g['scenic_spot'] == s) for s in spots}
    stats = {
        'inputs': {p.relative_to(ROOT.parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE, ROOT / 'reviews.json')},
        'documents_processed': len(documents), 'documents_with_pairs': len({p['doc_id'] for p in pairs}),
        'candidate_units': len(candidates), 'automatic_pairs': len(automatic), 'final_pairs': len(pairs),
        'rule_duplicate_events': len(duplicates), 'unique_mappings': len(mappings),
        'merged_occurrences': len(pairs) - len(mappings), 'anchor_checks': checks, 'anchor_failures': 0,
        'by_primary_type': dict(counts), 'by_scenic_spot': {s: dict(c) for s, c in by_spot.items()},
        'source_types': dict(Counter(p['source_type'] for p in pairs)),
        'reviewed_pairs': sum(p['review_status'] == 'reviewed' for p in pairs),
        'context_required_pairs': sum(p['requires_context'] for p in pairs),
    }
    dump(out / 'summary.json', stats)
    plot(out / 'condition_types.svg', '条件类别分布（合并后的映射）', types, [('映射条数', counts)])
    plot(out / 'scenic_comparison.svg', '三个景区的条件建议对比（合并后的映射）', types, list(by_spot.items()))
    fields = ('advice_id', 'doc_id', 'scenic_spot', 'source_type', 'source_name', 'url', 'condition_type', 'condition', 'advice', 'source_sentence', 'start', 'end', 'rule', 'relation', 'review_status')
    with (out / 'condition_advices.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(pairs)
    write_mapping(out / 'mapping_table.md', mappings, pairs)
    write_review(out / 'human_review.md', pairs, candidates, documents)
    quality = ['# 任务 5 质量检查', '', f'处理 {len(documents)} 篇，保留 {len(pairs)} 处条件建议，合并为 {len(mappings)} 条映射；{checks} 个原文锚点校验通过。',
               f"已记录复核决定 {len(review_log)} 条，其中最终标记 reviewed 的提及 {stats['reviewed_pairs']} 条。", '',
               '自动规则的程序检查与代码辅助定向复核不能替代独立人工标注，未计算整体 Precision/Recall/F1。', '',
               '- “可以看到”“建议慢慢逛”等没有明确条件的表达保留在候选审计，不强配条件。',
               '- “因为阴雨天直接舍弃原始森林”是已发生的选择，没有直接当作面向游客的建议。',
               '- “不建议徒步”“慎选”等否定保留；“或者分成2天慢慢玩”等并列备选建议不拆掉。',
               '- 故宫路线 1 的带老人小孩慎选与路线 4 的赶时间慎选分别绑定标题；贴心总结和温馨提示会清除旧标题。',
               '- 九寨沟右线开局的条件与下一行建议关联，但不会越过新标题；更远的篇章条件仍可能漏抽。',
               '- 九寨沟两处天鹅海→箭竹海“不建议徒步”归为同一映射，两个原始位置保留。',
               '- “亲子适合某路线”保存为 suitable_option 关系，advice 字段是原文方案名，而不是自行编写的祈使句。',
               '- “新手可以直接抄”的具体对象依赖全文，requires_context 标记为 true；不把它当作已消解的具体路线指令。',
               '- 已知漏项包括“哪天晴天选哪天”这类关联表达，以及“有特展时超值得去”的隐式推荐。候选审计和人工清单支持补充。',
               '- 同句、位置重叠的重复规则按优先级消解；跨位置仅在同景区、同条件、同语境、同关系下合并规范化相同或长度比至少 0.85 的前缀建议。',
               '- 未做开放式语义近义归并，不合并不同路线的“慎选”，不把不同景区或相反建议混为一条。', '']
    (out / 'QUALITY.md').write_text('\n'.join(quality), encoding='utf-8')
    print(f'Documents: {len(documents)}; conditional occurrences: {len(pairs)}; unique mappings: {len(mappings)}; anchors checked: {checks}')


if __name__ == '__main__':
    main()
