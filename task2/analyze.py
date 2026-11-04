"""Rebuild charts and comparison from the two saved runs, without an API key."""
from collections import Counter
import csv
from html import escape
from run import OUT, TYPES, dump, inputs, load


def chart(path, title, rows, colors):
    height = 90 + len(rows)*34
    peak = max((n for _, n in rows), default=1) or 1
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="880" height="{height}" viewBox="0 0 880 {height}">',
           '<rect width="100%" height="100%" fill="#f4f8fc"/>',
           '<g font-family="Microsoft YaHei, Noto Sans CJK SC, sans-serif" fill="#182c43">',
           f'<text x="24" y="33" font-size="22" font-weight="bold">{escape(title)}</text>',
           '<text x="24" y="57" font-size="14">单位：独立出现位置（次）</text>']
    for i,(label,n) in enumerate(rows):
        y = 72 + i*34
        width = 460*n/peak
        svg += [f'<text x="260" y="{y+17}" font-size="15" text-anchor="end">{escape(label)}</text>',
                f'<rect x="278" y="{y}" width="{width}" height="24" rx="3" fill="{colors[i % len(colors)]}"/>',
                f'<text x="{289+width}" y="{y+17}" font-size="15">{n}</text>']
    path.write_text('\n'.join(svg+['</g></svg>']), encoding='utf8')


def main():
    docs, chunks = inputs()
    folder = OUT/'analysis'
    folder.mkdir(exist_ok=True)
    rows = {v:load(OUT/v/'entities.json') for v in ('v1','v2')}
    runs = {v:load(OUT/v/'run.json') for v in rows}
    assert all(x['input_sha256'] == load(OUT/'input_manifest.json')['sha256'] for x in runs.values())
    assert runs['v1']['configuration'] == runs['v2']['configuration']
    assert all(not x['failed_chunks'] and not x['slice_failures'] for x in runs.values())
    freq = {v:{t:Counter(e['text'] for e in es if e['type']==t) for t in TYPES}
            for v,es in rows.items()}
    spots = sorted({d['scenic_spot'] for d in docs})
    stats = {}
    with (folder/'frequencies.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(('version','type','text','count'))
        for v,es in rows.items():
            summary = runs[v]
            stats[v] = {'total':len(es),'by_type':{t:sum(freq[v][t].values()) for t in TYPES},
                        'by_scenic_spot':{s:{t:sum(e['scenic_spot']==s and e['type']==t for e in es)
                                            for t in TYPES} for s in spots},
                        'issues':summary['issue_counts'],'successful_chunks':len(chunks),
                        'slice_checks':summary['slice_checks'],'slice_failures':len(summary['slice_failures']),
                        'usage':{k:sum(c['usage'].get(k,0) for c in summary['chunks']) for k in
                                 ('prompt_tokens','completion_tokens','prompt_cache_hit_tokens')}}
            for t, counts in freq[v].items():
                ranked = sorted(counts.items(), key=lambda x:(-x[1],x[0]))
                w.writerows((v,t,label,n) for label,n in ranked)
                chart(folder/f'{v}_{t}.svg', f'{v.upper()} {t} 高频实体（前 12）', ranked[:12], ['#246f96'])
    chart(folder/'v2_scenic_spots.svg', 'V2 三景区实体分布',
          [(f'{s} · {t}',stats['v2']['by_scenic_spot'][s][t]) for s in spots for t in TYPES],
          ['#246f96','#1c8073','#94632b'])
    ident = lambda e: (e['doc_id'],e['start'],e['end'],e['type'])
    sets = {v:{ident(e) for e in es} for v,es in rows.items()}
    stats['span_comparison'] = {'unchanged':len(sets['v1'] & sets['v2']),
                                'v1_only':len(sets['v1'] - sets['v2']), 'v2_only':len(sets['v2'] - sets['v1'])}
    dump(folder/'summary.json',stats)
    for v, other in [('v1','v2'),('v2','v1')]:
        dump(folder/f'{v}_only.json',[e for e in rows[v] if ident(e) not in sets[other]])

    # A regenerated sample must not overwrite review notes or student decisions.
    review_path = folder/'human_review.md'
    if review_path.exists():
        return
    # Sample each scenic spot × source type. Explicitly provide all predictions
    # in the window so the reviewer can mark omissions against the original.
    lines = ['# 人工抽查待核验', '', '每个景区各选一篇官方路线、一篇游客游记；按固定输入顺序选组内首篇，取首个分块的前 220 字并扩至下一换行（最多再扩 50 字）。位置为全文字符偏移。请标出误报、漏报、边界、类别和歧义。以下人工判断栏未填。']
    for spot in spots:
        for kind in ('official_route','travel_note'):
            d = next(d for d in docs if d['scenic_spot']==spot and d['text_type']==kind)
            s = d['clean_text']
            nl = s.find('\n',220,270)
            end = nl if nl >= 0 else min(len(s),220)
            lines += ['',f'## {spot} · {kind}', '', f'文档：`{d["doc_id"]}`　范围：[0, {end})　[来源]({d["url"]})',
                      '', '~~~~text',s[:end],'~~~~','']
            for v, es in rows.items():
                pred = [f'{e["type"]}「{e["text"]}」[{e["start"]},{e["end"]})'
                        for e in es if e['doc_id']==d['doc_id'] and e['end']<=end]
                lines += [f'- {v.upper()}：'+'；'.join(pred)]
            lines += ['- 人工判断与依据：待确认；漏项请写原文及位置。']
    review_path.write_text('\n'.join(lines)+'\n',encoding='utf8')


if __name__ == '__main__':
    main()

