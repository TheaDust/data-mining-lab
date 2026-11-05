"""Offline task 3 entry point: python task3/run.py."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

if __package__:
    from .extract import ALIASES, comparisons, official_routes, visitor_routes
    from .figures import write_hierarchy_diagram
else:
    from extract import ALIASES, comparisons, official_routes, visitor_routes
    from figures import write_hierarchy_diagram


ROOT = Path(__file__).resolve().parent
DOCUMENTS = ROOT.parent / 'task1/data/final/documents.jsonl'
ENTITIES = ROOT.parent / 'task2/results/v2/entities.json'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def check_evidence(value, text):
    """Check every recursively nested raw-text anchor, including POI references."""
    count = 0
    if isinstance(value, dict):
        if {'text', 'start', 'end'} <= value.keys():
            start, end = value['start'], value['end']
            if not (0 <= start < end <= len(text) and text[start:end] == value['text']):
                raise ValueError(f'Invalid source slice: {value}')
            count += 1
        for child in value.values():
            count += check_evidence(child, text)
    elif isinstance(value, list):
        count += sum(check_evidence(child, text) for child in value)
    return count


def validate(routes, documents):
    by_id = {d['doc_id']: d['clean_text'] for d in documents}
    source_docs = {d['doc_id']: d for d in documents}
    ids = [r['route_id'] for r in routes]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate route IDs')
    anchors = 0
    for route in routes:
        experience = route.get('experience_evidence')
        if experience and experience['text'] not in source_docs[route['doc_id']][experience['field']]:
            raise ValueError('Self-report evidence differs from its source field')
        steps = route['steps']
        if not steps or [s['step_id'] for s in steps] != list(range(1, len(steps) + 1)):
            raise ValueError(f"Empty or unordered steps: {route['route_id']}")
        hierarchy_ids = [i for d in route['hierarchy'] for p in d['periods'] for i in p['step_ids']]
        if hierarchy_ids != list(range(1, len(steps) + 1)):
            raise ValueError(f"Hierarchy lost/reordered steps: {route['route_id']}")
        for day in route['hierarchy']:
            for period in day['periods']:
                for i in period['step_ids']:
                    step = steps[i - 1]
                    if step['day'] != day['day'] or step['time_period'] != period['time_period']:
                        raise ValueError('Hierarchy label mismatch')
        for step in steps:
            if step['time_period'] is not None and not (step['time_evidence'] or step['time_heading']):
                raise ValueError('Time period without source evidence')
            a, b = step['evidence']['start'], step['evidence']['end']
            if any(not (a <= p['start'] < p['end'] <= b) for p in step['pois']):
                raise ValueError('POI outside its step')
        anchors += check_evidence(route, by_id[route['doc_id']])
    return anchors


def summary(routes):
    return {spot: {
        'routes': sum(r['scenic_spot'] == spot for r in routes),
        'steps': sum(len(r['steps']) for r in routes if r['scenic_spot'] == spot),
        'timed_steps': sum(s['time_text'] is not None for r in routes if r['scenic_spot'] == spot for s in r['steps']),
        'time_unspecified_steps': sum(s['time_period'] is None for r in routes if r['scenic_spot'] == spot for s in r['steps']),
    } for spot in dict.fromkeys(r['scenic_spot'] for r in routes)}


def write_hierarchy(path, routes):
    content = ['# 路线层级清单', '', '步骤和时间均可在路线 JSON 中回查原文证据；未注明的时间保留未知。', '']
    for route in routes:
        content += [f"## {route['scenic_spot']} · {route['route_name']}", '', f"路线 ID：`{route['route_id']}`", '']
        for day in route['hierarchy']:
            label = f"第 {day['day']} 天" if day['day'] is not None else '日期未注明'
            content.append(f'- {label}')
            for period in day['periods']:
                content.append(f"  - {period['time_period'] or '时段未注明'}")
                for i in period['step_ids']:
                    step = route['steps'][i - 1]
                    name = step['poi'] or '未注明具名地点'
                    timing = f"；{step['time_text']}" if step['time_text'] else ''
                    order = '；节点内部顺序未知' if step['poi_order'] == 'unspecified' else ''
                    content.append(f"    - 步骤 {i}：{name}；{step['activity']}{timing}{order}")
        content.append('')
    path.write_text('\n'.join(content), encoding='utf-8')


def write_quality(path, officials, visitors, comparisons_, anchors):
    content = [
        '# 任务 3 数据检查与定向复核', '',
        f'程序检查 {len(officials)} 条官方路线、{len(visitors)} 条游客路线；{anchors} 个原文锚点切片一致。',
        '检查项包括：路线 ID 唯一、步骤连续、层级不丢失或重排步骤、层级标签一致、POI 位于步骤原文范围内、时间层级有原文依据。', '',
        '以下是对原文与规则输出的代码辅助复核，不是独立人工 gold 或整体准确率。学生人工确认尚未记录。', '',
        '| 景区 | 官方路线 | 步骤 | 有时刻的步骤 | 时段未知的步骤 |',
        '|---|---:|---:|---:|---:|',
    ]
    for spot, item in summary(officials).items():
        content.append(f"| {spot} | {item['routes']} | {item['steps']} | {item['timed_steps']} | {item['time_unspecified_steps']} |")
    content += ['', '## 原文问题及解析边界', '']
    for route in officials + visitors:
        for issue in route['issues']:
            content.append(f"- `{route['route_id']}`：{issue['code']}；{issue.get('message', '')}")
    content += [
        '', '## 可复核样例', '',
        '- 故宫四条总览各保存一次；正文重复的【游玩路线】不再另建重复路线。路线二、三的“中轴线+”保留为未展开组合，不自动补全九个景点。',
        '- 西湖十条“途径”分别归属各自标题；“全程约3小时”存为整条路线时长，不变成“上午”。“远眺”保留为观看方式。',
        '- “药王庙、阮公祠”“舞鹤赋刻石及林逋墓”等同一链节点中的并列地点标为内部顺序未知；括号说明不另生成访问步骤。',
        '- 九寨沟一日游保存 15 个原文移动/活动段；15:40–17:00 的多站共用一个时间窗，不均分成各站时长。',
        '- 九寨沟末两段原文分别为 17:00–17:20 和 17:00–17：35，标记重叠，原值不改。',
        '- 二日、三日方案按 Day 标记组织；三日方案第一天含县城→神仙池→漳扎镇，外围节点保留 surrounding 范围；神仙池景点清单不当作访问顺序。',
        '- 六篇游客样本包含两篇推荐攻略和四篇作者自述；自述证据保存在 experience_evidence，标题中的“亲测”也明确标注来源字段，不等于独立验证的轨迹。',
        '- 新增西湖家庭路线中“对面就是太子湾公园”只是方位说明，未生成访问节点；故宫“三大殿”和九寨沟“树正区域”按集合节点保留，不推断内部访问顺序。',
        '- 西湖“雷峰夕照/雷峰塔”“南屏晚钟/净慈寺”保持不同名称；景观主题与具体建筑不直接合并。',
        '- 只在明确路线片段中匹配 POI，V2 未识别的官方路线节点由结构规则补取；不把全文实体顺序用作路线。',
        '', '## 对比结果', '',
        '| 景区 | 游客样本 | 性质 | 官方景点覆盖率 | 景点集合 Jaccard | 顺序相似度 |',
        '|---|---|---|---:|---:|---:|',
    ]
    for c in comparisons_:
        m = c['normalized']
        kind = '作者自述' if c['visitor_route_kind'] == 'visitor_actual' else '推荐攻略'
        content.append(f"| {c['scenic_spot']} | {c['visitor_route_name']} | {kind} | {m['official_coverage']:.1%} | {m['poi_jaccard']:.3f} | {m['order_similarity']:.3f} |")
    content += ['', '指标受样本、推荐主题和名称口径影响；不是抽取准确率，也不代表路线质量。公式与样本边界见 README.md。', '']
    path.write_text('\n'.join(content), encoding='utf-8')


def main():
    documents = [json.loads(line) for line in DOCUMENTS.read_text(encoding='utf-8').splitlines() if line.strip()]
    entities = load(ENTITIES)
    source_sha = hashlib.sha256(DOCUMENTS.read_bytes()).hexdigest()
    frozen = load(ROOT.parent / 'task2/results/input_manifest.json')
    if source_sha != frozen['sha256']:
        raise ValueError('Task 1 source differs from the input used by task 2')
    by_id = {d['doc_id']: d['clean_text'] for d in documents}
    for entity in entities:
        check_evidence(entity, by_id[entity['doc_id']])
    selections = load(ROOT / 'samples.json')
    officials = official_routes(documents, entities)
    visitors = visitor_routes(documents, entities, officials, selections)
    anchors = validate(officials + visitors, documents)
    compared = comparisons(officials, visitors)
    out = ROOT / 'results'
    out.mkdir(exist_ok=True)
    dump(out / 'official_routes.json', officials)
    dump(out / 'visitor_routes.json', visitors)
    dump(out / 'hierarchy.json', [{k: r[k] for k in ('route_id', 'doc_id', 'scenic_spot', 'route_name', 'hierarchy')} for r in officials + visitors])
    write_hierarchy(out / 'hierarchy.md', officials + visitors)
    write_hierarchy_diagram(out / 'hierarchy-overview.drawio', officials)
    dump(out / 'comparison.json', compared)
    fields = ('route_id', 'doc_id', 'scenic_spot', 'route_name', 'route_kind', 'step_id', 'day', 'time_text', 'time_period', 'poi', 'activity', 'activity_inferred', 'poi_order', 'visit_duration_text', 'travel_duration_text', 'source_text', 'start', 'end')
    with (out / 'steps.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for route in officials + visitors:
            for step in route['steps']:
                row = {k: route[k] if k in route else step[k] for k in fields if k not in ('source_text', 'start', 'end')}
                writer.writerow({**row, 'source_text': step['evidence']['text'], 'start': step['evidence']['start'], 'end': step['evidence']['end']})
    stats = {
        'inputs': {str(p.relative_to(ROOT.parent).as_posix()): hashlib.sha256(p.read_bytes()).hexdigest() for p in (DOCUMENTS, ENTITIES, ROOT / 'samples.json')},
        'official': summary(officials), 'visitor': summary(visitors),
        'slice_checks': anchors, 'slice_failures': 0,
        'issues': dict(Counter(i['code'] for r in officials + visitors for i in r['issues'])),
        'aliases': ALIASES,
        'visitor_kinds': dict(Counter(r['route_kind'] for r in visitors)),
        'temporal_coverage': {
            'total_steps': sum(len(r['steps']) for r in officials + visitors),
            'known_period_steps': sum(s['time_period'] is not None for r in officials + visitors for s in r['steps']),
            'unknown_period_steps': sum(s['time_period'] is None for r in officials + visitors for s in r['steps']),
            'dated_steps': sum(s['day'] is not None for r in officials + visitors for s in r['steps']),
        },
    }
    dump(out / 'summary.json', stats)
    write_quality(out / 'QUALITY.md', officials, visitors, compared, anchors)
    print(f'Official routes: {len(officials)}; visitor routes: {len(visitors)}; source anchors checked: {anchors}')
    for spot, item in stats['official'].items():
        print(f"{spot}: {item['routes']} routes, {item['steps']} steps")


if __name__ == '__main__':
    main()
