"""Parse the three archived official guides; all offsets refer to clean_text."""
import re


# Only merge site-specific names supported by the archived guide's context.
ALIASES = {
    '北京故宫': {},
    '杭州西湖': {},
    '九寨沟': {'天鹅湖': '天鹅海', '诺日朗中心': '诺日朗中心站'},
}
SURROUNDING = {'九寨沟县城', '九寨沟神仙池景区', '漳扎镇'}
BOUNDARIES = {'沟口', '出沟', '游客中心', '进景区'}
COLLECTIVES = {'北京故宫': {'三大殿'}, '杭州西湖': set(), '九寨沟': {'树正区域'}}
STATIONS = {'诺日朗中心站', '诺日朗中转', '镜海停车场'}
CLOCK = re.compile(r'(?<!\d)([0-2]?\d)[：:]([0-5]\d)(?!\d)')
RANGE = re.compile(r'(?<!\d)([0-2]?\d)[：:]([0-5]\d)\s*[-—–~～]\s*([0-2]?\d)[：:]([0-5]\d)(?!\d)')
SPLIT = re.compile(r'➡\ufe0f?|→|—+|-')


def evidence(text, start, end):
    return {'text': text[start:end], 'start': start, 'end': end}


def lines(text):
    offset = 0
    for line in text.splitlines(keepends=True):
        value = line.rstrip('\r\n')
        if value.strip():
            yield value, offset
        offset += len(line)


def split_top(text, pattern):
    """Split separators outside parentheses, retaining exact local positions."""
    depth, start, i = 0, 0, 0
    while i < len(text):
        char = text[i]
        if char in '（(':
            depth += 1
        elif char in '）)':
            depth -= 1
        match = pattern.match(text, i) if depth == 0 else None
        if match:
            yield text[start:i], start
            i = start = match.end()
        else:
            i += 1
    yield text[start:], start


def trim(value, offset):
    left = len(value) - len(value.lstrip())
    return value.strip(), offset + left


def poi(doc, text, start, entities):
    name = ALIASES[doc['scenic_spot']].get(text, text)
    end = start + len(text)
    return {
        **evidence(doc['clean_text'], start, end), 'name': name,
        'normalized': name != text,
        'kind': 'boundary' if text in BOUNDARIES else 'station' if name in STATIONS else 'collective' if text in COLLECTIVES[doc['scenic_spot']] else 'unresolved' if name == '诺日朗' else 'poi',
        'scope': 'surrounding' if name in SURROUNDING else 'scenic_area',
        'entity_ref': next(({'start': start, 'end': end, 'type': 'POI'} for e in entities
                            if e['type'] == 'POI' and e['start'] == start and e['end'] == end), None),
    }


def literal_pois(doc, fragment, offset, entities):
    """Official chain nodes are structural evidence even if NER missed them."""
    result = []
    for value, local in split_top(fragment, re.compile(r'、|及')):
        value, start = trim(value, offset + local)
        # Parentheses qualify the preceding node; they do not imply another visit.
        name = re.split(r'[（(]', value)[0].strip()
        if name == '沟口乘车':
            name = '沟口'
        if name.startswith('外东路'):
            start += len('外东路')
            name = name[len('外东路'):]
        if name:
            result.append(poi(doc, name, start, entities))
    return result


def new_route(doc, name, number, kind='official_recommendation'):
    return {
        'route_id': f"{doc['doc_id']}_route_{number:02d}",
        **{key: doc[key] for key in ('doc_id', 'scenic_spot', 'source_type', 'url')},
        'route_name': name, 'route_kind': kind, 'duration_text': None,
        'duration_evidence': None, 'components': [], 'steps': [], 'issues': [],
    }


def period_at(minutes):
    return '上午' if minutes < 11 * 60 + 30 else '中午' if minutes < 13 * 60 + 30 else '下午' if minutes < 18 * 60 else '晚上'


def add_step(route, doc, value, offset, pois, day=None, period=None, time_heading=None):
    match = RANGE.search(value)
    clock = CLOCK.search(value)
    timing = match or clock
    clock_range = None
    if match:
        h1, m1, h2, m2 = map(int, match.groups())
        clock_range = [60 * h1 + m1, 60 * h2 + m2]
    point = 60 * int(clock[1]) + int(clock[2]) if clock else None
    if period is None and point is not None:
        period = period_at(point)
    time_ev = evidence(doc['clean_text'], offset + timing.start(), offset + timing.end()) if timing else None
    actions = [m.group() for m in re.finditer(r'安检检票|换乘观光车|乘坐观光车|观光车|摆渡车|坐船|登岸|步行|乘车|用餐|休息|拍照|驱车|办理入住|游览|到达景区|进景区|出沟|出景区|上车|下车|换车', value)]
    # Preserve travel vs visit durations; never divide one shared window among POIs.
    visit = re.search(r'游览时间(?P<duration>约?\d+(?:个多)?分钟)|(?P<duration2>约?\d+个多小时)游览时间', value)
    travel = re.search(r'约?\d+(?:个半)?分钟车程|约?\d+个半小时|约?\d+(?:个)?小时车程|一个小时车程|步行\d+分钟', value)
    visit_text = (visit['duration'] or visit['duration2']) if visit else None
    visit_span = visit.span('duration' if visit['duration'] else 'duration2') if visit else None
    poi_order = 'explicit' if re.search(r'→|➡|从.+到', value) else 'unspecified' if len(pois) > 1 else 'single'
    step = {
        'step_id': len(route['steps']) + 1, 'day': day,
        'time_text': timing.group() if timing else None, 'time_period': period,
        'time_evidence': time_ev, 'time_heading': time_heading,
        'clock_range_minutes': clock_range,
        'clock_point_minutes': None if match else point,
        'poi': ('、' if poi_order == 'unspecified' else ' → ').join(p['name'] for p in pois), 'pois': pois,
        'poi_order': poi_order,
        'activity': '、'.join(dict.fromkeys(actions)) or '参观',
        'activity_inferred': not bool(actions),
        'visit_duration_text': visit_text,
        'visit_duration_evidence': evidence(doc['clean_text'], offset + visit_span[0], offset + visit_span[1]) if visit_span else None,
        'travel_duration_text': travel.group() if travel else None,
        'travel_duration_evidence': evidence(doc['clean_text'], offset + travel.start(), offset + travel.end()) if travel else None,
        'evidence': evidence(doc['clean_text'], offset, offset + len(value)),
        'visit_mode': 'distant_view' if '远眺' in value else 'unspecified',
    }
    route['steps'].append(step)
    return step


def add_chain(route, doc, body, offset, entities, day=None, period=None, heading=None):
    for fragment, local in split_top(body, SPLIT):
        fragment, start = trim(fragment, offset + local)
        if fragment:
            add_step(route, doc, fragment, start, literal_pois(doc, fragment, start, entities), day, period, heading)


def parse_gugong(doc, entities):
    routes = []
    for value, offset in lines(doc['clean_text']):
        match = re.match(r'(路线[一二三四].*?[：:])(?P<body>.+)$', value)
        if not match:
            continue
        route = new_route(doc, match[1].rstrip('：:'), len(routes) + 1)
        body, start = match['body'], offset + match.start('body')
        prefix = re.match(r'中轴线\+(?:东线)?', body)
        if prefix:
            route['components'].append(evidence(doc['clean_text'], start, start + prefix.end()))
            route['issues'].append({'code': 'unexpanded_component', 'message': '中轴线为组合路线的前置区域；原文未明确其完整访问序列，不自动复制路线一。'})
            body, start = body[prefix.end():], start + prefix.end()
        add_chain(route, doc, body, start, entities)
        routes.append(route)
    return routes


def parse_xihu(doc, entities):
    routes, title, block_start = [], None, 0
    for value, offset in lines(doc['clean_text']):
        if value.endswith('之旅') or value == '龙井八景':
            title, block_start = value, offset
        if value.startswith('途径：'):
            route = new_route(doc, title, len(routes) + 1)
            block = doc['clean_text'][block_start:offset]
            duration = re.search(r'(?:线路全程|全程)(约?\d+(?:\.\d+)?(?:[-—]\d+(?:\.\d+)?)?小时)', block)
            if duration:
                route['duration_text'] = duration[1]
                route['duration_evidence'] = evidence(doc['clean_text'], block_start + duration.start(1), block_start + duration.end(1))
            add_chain(route, doc, value[3:], offset + 3, entities)
            routes.append(route)
    return routes


def parse_jiuzhaigou(doc, entities):
    routes, route, day, period, heading = [], None, None, None, None
    for value, offset in lines(doc['clean_text']):
        if re.fullmatch(r'[一二三]日.+游', value):
            route = new_route(doc, value, len(routes) + 1)
            routes.append(route)
            day = 1 if value.startswith('一日') else None
            period, heading = None, None
        elif route is not None:
            day_match = re.fullmatch(r'【Day (\d)】', value)
            if day_match:
                day, period = int(day_match[1]), None
                heading = evidence(doc['clean_text'], offset, offset + len(value))
            elif value in ('【上午】', '【中午】', '【下午】'):
                period = value[1:-1]
                heading = evidence(doc['clean_text'], offset, offset + len(value))
            elif '→' in value:
                if RANGE.search(value):
                    body = re.split(r'[（(]', value, maxsplit=1)[0]
                    pois = []
                    for part, local in split_top(body, SPLIT):
                        part, start = trim(part, offset + local)
                        pois.extend(literal_pois(doc, part, start, entities))
                    add_step(route, doc, value, offset, pois, day, period, heading)
                else:
                    add_chain(route, doc, value, offset, entities, day, period, heading)
            elif route['route_name'].startswith('三日') and day == 1:
                journey = re.match(r'从(.+?)到(.+?)(\d+)公里', value)
                overnight = re.search(r'来到(.+?镇)', value)
                if journey:
                    pois = [poi(doc, journey[g], offset + journey.start(g), entities) for g in (1, 2)]
                    add_step(route, doc, value, offset, pois, day, period, heading)
                elif overnight:
                    town = overnight[1].rsplit('的', 1)[-1]
                    add_step(route, doc, value, offset, [poi(doc, town, offset + overnight.end(1) - len(town), entities)], day, period, heading)
                elif '景区景点：' in value:
                    route['issues'].append({'code': 'unordered_inventory', 'message': '神仙池景点介绍是无序清单，不生成景点间先后边。', 'evidence': evidence(doc['clean_text'], offset, offset + len(value))})
    return routes


def add_hierarchy(route):
    days = []
    for step in route['steps']:
        label = step['day']
        day = next((d for d in days if d['day'] == label), None)
        if day is None:
            day = {'day': label, 'periods': []}
            days.append(day)
        # Contiguous blocks preserve narrative order even if time labels regress.
        period = step['time_period']
        if not day['periods'] or day['periods'][-1]['time_period'] != period:
            day['periods'].append({'time_period': period, 'step_ids': []})
        day['periods'][-1]['step_ids'].append(step['step_id'])
    route['hierarchy'] = days


def time_issues(route):
    previous = None
    for step in route['steps']:
        window = step['clock_range_minutes']
        if window:
            if window[1] < window[0]:
                route['issues'].append({'code': 'reversed_time_range', 'step_id': step['step_id']})
            if previous and previous['day'] == step['day'] and window[0] < previous['clock_range_minutes'][1]:
                route['issues'].append({'code': 'overlapping_time_ranges', 'step_ids': [previous['step_id'], step['step_id']], 'message': '相邻原文时间区间重叠；保留原文，不自动改时刻。'})
            previous = step
        elif step['clock_point_minutes'] is not None:
            previous = None


def official_routes(documents, all_entities):
    routes = []
    parsers = {'北京故宫': parse_gugong, '杭州西湖': parse_xihu, '九寨沟': parse_jiuzhaigou}
    for doc in documents:
        if doc['text_type'] == 'official_route':
            entities = [e for e in all_entities if e['doc_id'] == doc['doc_id']]
            routes.extend(parsers[doc['scenic_spot']](doc, entities))
    for route in routes:
        add_hierarchy(route)
        time_issues(route)
    return routes


def match_pois(doc, value, offset, entities, vocabulary):
    """Use NER at this location plus official names; longest spans win nesting."""
    candidates = {(e['start'], e['end']) for e in entities if e['type'] == 'POI'
                  and offset <= e['start'] < e['end'] <= offset + len(value)}
    for name in vocabulary:
        candidates.update((offset + m.start(), offset + m.end()) for m in re.finditer(re.escape(name), value))
    accepted = []
    noise = {'故宫', '故宫博物院', '紫禁城', '北京', '西湖', '杭州', '九寨沟', '景区', '左线', '右线', '中线', '西湖十景'}
    for a, b in sorted(candidates, key=lambda x: (x[0] - x[1], x[0])):
        word = doc['clean_text'][a:b]
        if word in noise or any(a < y and x < b for x, y in accepted):
            continue
        accepted.append((a, b))
    return [poi(doc, doc['clean_text'][a:b], a, entities) for a, b in sorted(accepted)]


def visitor_routes(documents, entities, officials, selections):
    by_id = {d['doc_id']: d for d in documents}
    routes = []
    for selection in selections:
        doc = by_id[selection['doc_id']]
        local_entities = [e for e in entities if e['doc_id'] == doc['doc_id']]
        route = new_route(doc, selection['route_name'], 1, selection['route_kind'])
        route['selection'] = selection
        experience = selection.get('experience')
        if experience:
            field, quote = experience['field'], experience['text']
            quote_start = doc[field].index(quote)
            route['experience_evidence'] = ({**evidence(doc[field], quote_start, quote_start + len(quote)), 'field': field}
                                            if field == 'clean_text' else {'field': field, 'text': quote})
        vocabulary = {p['text'] for r in officials if r['scenic_spot'] == doc['scenic_spot'] for s in r['steps'] for p in s['pois']}
        vocabulary.update(ALIASES[doc['scenic_spot']])
        vocabulary.update(COLLECTIVES[doc['scenic_spot']])
        vocabulary.update(BOUNDARIES)
        vocabulary.update(STATIONS if doc['scenic_spot'] == '九寨沟' else ())
        text = doc['clean_text']
        start = text.index(selection['start_marker'])
        end = text.index(selection['end_marker'], start) if selection.get('end_marker') else len(text)
        block = text[start:end]
        selected_lines = set(selection.get('include_lines', []))
        matched_lines = set()
        day = selection.get('day', 1)
        duration = re.search(r'(\d+(?:\.\d+)?[～~-]\d+(?:\.\d+)?小时)', block.split('\n', 1)[0])
        if duration:
            route['duration_text'] = duration[1]
            route['duration_evidence'] = evidence(text, start + duration.start(1), start + duration.end(1))
        for value, local in lines(block):
            offset = start + local
            mode = selection['mode']
            if selected_lines and value not in selected_lines:
                continue
            matched_lines.add(value)
            if mode == 'numbered' and not re.match(r'\d+\.', value):
                continue
            if mode == 'chain' and '→' not in value:
                continue
            if mode == 'clock' and not CLOCK.match(value):
                continue
            if mode == 'chain':
                for fragment, pos in split_top(value, SPLIT):
                    fragment, a = trim(fragment, offset + pos)
                    head = re.split(r'[（(]', fragment, maxsplit=1)[0]
                    pois = match_pois(doc, head, a, local_entities, vocabulary)
                    if not pois:
                        route['issues'].append({'code': 'unmatched_route_node', 'evidence': evidence(text, a, a + len(fragment))})
                    add_step(route, doc, fragment, a, pois, day)
            else:
                pois = match_pois(doc, value, offset, local_entities, vocabulary)
                # Keep timed entry/exit and movement actions even without a named POI.
                step = add_step(route, doc, value, offset, pois, day)
                if mode == 'clock' and len(pois) > 1:
                    step['poi_order'] = 'explicit'
                    step['poi'] = ' → '.join(p['name'] for p in pois)
        if selected_lines - matched_lines:
            raise ValueError(f"Selected route lines not found: {selection['doc_id']}")
        for step in route['steps']:
            if any(p['kind'] == 'unresolved' for p in step['pois']):
                route['issues'].append({'code': 'ambiguous_poi', 'step_id': step['step_id'], 'message': '“诺日朗”单独出现时未消歧，保留原始提及，但不参与景点对比。'})
            if any(p['kind'] == 'collective' for p in step['pois']):
                route['issues'].append({'code': 'unexpanded_collective', 'step_id': step['step_id'], 'message': '区域或集合节点保留原文，不展开为有序子景点；不参与具体景点覆盖指标。'})
        add_hierarchy(route)
        time_issues(route)
        routes.append(route)
    return routes


def sequence(route, normalized=True):
    result = []
    for step in route['steps']:
        if step['poi_order'] == 'unspecified' and len(step['pois']) > 1:
            raise ValueError('Order comparison requires explicit order inside each step')
        for point in step['pois']:
            if point['kind'] != 'poi' or point['scope'] != 'scenic_area':
                continue
            name = point['name'] if normalized else point['text']
            if not result or result[-1] != name:
                result.append(name)
    return result


def lcs_length(a, b):
    row = [0] * (len(b) + 1)
    for x in a:
        previous = 0
        for j, y in enumerate(b, 1):
            old = row[j]
            row[j] = previous + 1 if x == y else max(row[j], row[j - 1])
            previous = old
    return row[-1]


def metrics(a, b):
    left, right = set(a), set(b)
    overlap, union = left & right, left | right
    lcs = lcs_length(a, b)
    return {
        'official_sequence': a, 'visitor_sequence': b,
        'shared_pois': sorted(overlap), 'official_only': sorted(left - right), 'visitor_only': sorted(right - left),
        'official_coverage': len(overlap) / len(left) if left else None,
        'poi_jaccard': len(overlap) / len(union) if union else None,
        'lcs_length': lcs, 'order_similarity': 2 * lcs / (len(a) + len(b)) if a or b else None,
    }


def elapsed(route):
    clocks = [s['clock_range_minutes'] or ([s['clock_point_minutes']] * 2 if s['clock_point_minutes'] is not None else None) for s in route['steps']]
    clocks = [c for c in clocks if c]
    return clocks[-1][1] - clocks[0][0] if clocks else None


def comparisons(officials, visitors):
    result = []
    for visitor in visitors:
        official = next(r for r in officials if r['scenic_spot'] == visitor['scenic_spot'])
        result.append({
            'scenic_spot': visitor['scenic_spot'],
            'official_route_id': official['route_id'], 'visitor_route_id': visitor['route_id'],
            'visitor_route_kind': visitor['route_kind'],
            'visitor_route_name': visitor['route_name'],
            'selection_reason': visitor['selection']['comparison_reason'],
            'strict': metrics(sequence(official, False), sequence(visitor, False)),
            'normalized': metrics(sequence(official), sequence(visitor)),
            'time_comparison': {
                'official_duration_text': official['duration_text'], 'visitor_duration_text': visitor['duration_text'],
                'official_elapsed_minutes': elapsed(official), 'visitor_elapsed_minutes': elapsed(visitor),
                'official_explicit_visit_durations': sum(s['visit_duration_text'] is not None for s in official['steps']),
                'visitor_explicit_visit_durations': sum(s['visit_duration_text'] is not None for s in visitor['steps']),
                'note': '首末时刻差只表示所选片段的经过时间；不由到站时刻推算停留时长。官方原文时间冲突见路线 issues。',
            },
        })
    return result
