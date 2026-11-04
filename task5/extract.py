"""Local rules for conditional recommendations, with exact clean_text anchors."""
import hashlib
import re
import unicodedata


TYPE_PATTERNS = {
    'weather': r'下雨|雨天|阴雨|晴天|风雨|光线偏暗|太阳|暴晒',
    'visitor_type': r'老人|小孩|小朋友|婴儿车|带娃|带孩子|父母|亲子|年轻人|新手|第一次|初次|初入高原|感兴趣|甄嬛传|想安安静静',
    'physical_condition': r'体力|力气|不想走|省腿|长距离|远的路段|大距离',
    'time': r'时间|赶时间|下午|早上|中午|出发前|特展时',
    'transport': r'坐船|乘船|拼船|没约上',
    'crowd': r'人多|清净|排队|节假日|旺季|避人流',
    'season': r'\d+[‑–—-]\d+月|丰水期|冬季|夏季|春季',
    'budget': r'省钱|不花额外门票',
    'route': r'分配到|右线开始|左线开始|→|➡|群山',
}
TYPE_LABELS = {
    'weather': '天气与光线', 'visitor_type': '游客类型与偏好',
    'physical_condition': '体力与步行偏好', 'time': '时间安排',
    'transport': '交通与预约', 'crowd': '人流条件', 'season': '季节',
    'budget': '预算', 'route': '路线与地形', 'other': '其他明确条件',
}
# Longer forms come first; the match itself, not a rewritten label, is the condition.
IMPLICIT = re.compile('|'.join([
    r'带娃\s*/\s*带父母', r'带老人小孩', r'初入高原的朋友',
    r'体力(?:一般|较差|不好|有限|充足)', r'不想走(?:太多)?路',
    r'赶时间想省腿', r'赶时间', r'想省钱不花额外门票', r'怕人多想清净',
    r'时间(?:有限|充裕|充足)', r'一天时间相对紧凑',
    r'旅游旺季参观时', r'不赶时间', r'下午的话', r'光线偏暗',
    r'每年\d+[‑–—-]\d+月郁金香展', r'打算坐船', r'没约上', r'有特展时',
    r'初次来', r'第一次来', r'新手', r'晴天',
    r'远的路段', r'长距离', r'大距离移动', r'带娃', r'漫步群山之余',
]))
EXPLICIT = re.compile(r'如果|假如|倘若|要是|若(?!干|隐|有若无)')
INTRO = re.compile(r'不建议|不推荐|比较推荐|建议|推荐|可以|可(?=到|选|自带|顺带|以)|慎选|选路线|选珍宝馆|直接|留意|带伞|一定(?:留|坐|做好)|千万别|千万注意|该坐|(?:入园)?需要提前预约')
DIRECT = re.compile(r'^(?:则|那么|就)?(?:穿|带|携带|选|坐|留|走|慢慢走|放弃|深度玩|分成|提前|注意|做好|别|不要|不宜)')
TRIGGER = re.compile(r'如果|假如|倘若|若|建议|推荐|可以|适合|慎选|→选|晴天带伞|时间充裕|体力|打算坐船|距离.*坐车')
UNITS = re.compile(r'(?:[^。！？!?；;\n～~]|(?<=\d)[～~](?=\d))+[。！？!?；;～~]?')


def anchor(text, start, end):
    return {'text': text[start:end], 'start': start, 'end': end}


def trim_span(text, start, end):
    while start < end and (text[start].isspace() or text[start] in '，,：:；;（(→➡️'):
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] in '。！？!?；;，,（(～~✅❌📌⏳⌛💡👟🌿📝'):
        end -= 1
    for opening, closing in [('（', '）'), ('(', ')')]:
        while end > start and text[end - 1] == closing and text[start:end].count(closing) > text[start:end].count(opening):
            end -= 1
    return start, end


def classify(condition):
    types = [label for label, pattern in TYPE_PATTERNS.items() if re.search(pattern, condition)]
    # Scheduling after dispatch is a route condition, not a general time choice.
    if 'route' in types:
        types.remove('route')
        types.insert(0, 'route')
    return types or ['other']


def stable_id(*parts):
    value = '|'.join(map(str, parts)).encode('utf-8')
    return hashlib.sha256(value).hexdigest()[:16]


def contexts(text):
    """Only actual section/route headers can supply a missing recommendation target."""
    result = []
    offset = 0
    for line in text.splitlines(keepends=True):
        value = line.rstrip('\r\n')
        target = re.search(r'^[^\w\u4e00-\u9fff]*路线\s*[1-5][（(]|^[一二三四五六七八九十]+、(?:.*线|.*参观|午门雁翅楼)|^\d\ufe0f?\u20e3\s*[^\n]+[（(]p\d|^.+｜(?:帝王|真正生活|溥仪)', value)
        reset = re.search(r'温馨提示|贴心总结|【实用信息】|【听劝必看】|^[一二三四五六七八九十]+、实用|^.+【.+】$', value)
        if target or reset:
            start, end = trim_span(text, offset, offset + len(value))
            result.append({**anchor(text, start, end), 'usable': bool(target)})
        offset += len(line)
    return result


def nearby_context(headers, position):
    header = next((h for h in reversed(headers) if h['start'] <= position), None)
    return header if header and header['usable'] and position - header['end'] < 1000 else None


def make_pair(doc, condition_span, advice_span, window, rule, context=None, relation='recommendation'):
    text = doc['clean_text']
    ca, cb = trim_span(text, *condition_span)
    aa, ab = trim_span(text, *advice_span)
    if ca == cb or aa == ab:
        return None
    types = classify(text[ca:cb])
    wa, wb = min(window[0], ca, aa), max(window[1], cb, ab)
    # Keep the full physical line so a ticket/POI named before "!" is not lost.
    wa = text.rfind('\n', 0, wa) + 1
    newline = text.find('\n', wb)
    wb = newline if newline >= 0 else len(text)
    return {
        'advice_id': 'adv_' + stable_id(doc['doc_id'], ca, cb, aa, ab),
        **{k: doc[k] for k in ('doc_id', 'scenic_spot', 'source_type', 'source_name', 'url')},
        'condition_type': types[0], 'condition_types': types,
        'condition': text[ca:cb], 'advice': text[aa:ab],
        'condition_span': anchor(text, ca, cb), 'advice_span': anchor(text, aa, ab),
        'source_sentence': text[wa:wb], 'start': wa, 'end': wb,
        'context': context, 'rule': rule, 'relation': relation,
        'requires_context': context is None and bool(re.search(r'这里|那里|直接抄|这条路线|慎选', text[aa:ab])),
        'review_status': 'automatic',
    }


def advice_start(text, start, end):
    start, end = trim_span(text, start, end)
    # Keep time qualifiers before the verb. Remove a leading factual clause only
    # when the directive begins after a comma, e.g. "山上风大，建议穿雨衣".
    intro = INTRO.search(text, start, end)
    if intro:
        before = text[start:intro.start()]
        comma = max(before.rfind('，'), before.rfind(','))
        if comma >= 0:
            start += comma + 1
        for marker in ('那么', '则'):
            if text.startswith(marker, start):
                start += len(marker)
        return trim_span(text, start, end)
    if DIRECT.match(text[start:end]):
        return start, end
    return None


def advice_end(text, start, end):
    # Causes explain the advice; retain coordinated recommendations before them.
    cause = re.search(r'，?因为|，?所以|，(?=阴雨天的时候)', text[start:end])
    if cause:
        end = start + cause.start()
    return trim_span(text, start, end)[1]


def explicit_pairs(doc, units, i, headers):
    text = doc['clean_text']
    unit = units[i]
    value = unit.group()
    triggers = list(EXPLICIT.finditer(value))
    results = []
    for j, trigger in enumerate(triggers):
        start = unit.start() + trigger.end()
        end = unit.start() + triggers[j + 1].start() if j + 1 < len(triggers) else unit.end()
        fragment = text[start:end]
        if re.match(r'让我重新|不能了解|能参与', fragment):
            continue
        comma = re.search(r'[，,：:]', fragment)
        intro = INTRO.search(fragment)
        connector = re.search(r'那么|则|就(?=穿|带|携带|选|坐|留|走|注意)', fragment)
        split = min([m.start() for m in (comma, intro, connector) if m] or [len(fragment)])
        ca, cb = trim_span(text, start, start + split)
        aa, ab = trim_span(text, start + split, end)
        # A condition-only line may govern exactly the next unit, never a new heading.
        if aa == ab and i + 1 < len(units):
            following = units[i + 1]
            if text[unit.end():following.start()].count('\n') <= 1 and not re.search(r'【|^\d[.、]|^[一二三四五六七八九十]+、|^#{1,6} ', following.group()):
                aa, ab = following.span()
        target = advice_start(text, aa, ab)
        if target and ca < cb:
            aa, ab = target
            ab = advice_end(text, aa, ab)
            pair = make_pair(doc, (ca, cb), (aa, ab), (unit.start(), max(unit.end(), ab)), 'explicit_condition', nearby_context(headers, unit.start()))
            if pair:
                results.append(pair)
    return results


def implicit_pairs(doc, unit, headers):
    text = doc['clean_text']
    value = unit.group()
    results = []
    matches = list(IMPLICIT.finditer(value))
    for i, match in enumerate(matches):
        ca, cb = unit.start() + match.start(), unit.start() + match.end()
        if value[max(0, match.start() - 2):match.start()] == '哪天':
            continue
        end = unit.start() + matches[i + 1].start() if i + 1 < len(matches) else unit.end()
        aa, ab = trim_span(text, cb, end)
        tail = text[aa:ab]
        # The condition must immediately govern a directive, not a later unrelated clause.
        if not (INTRO.match(tail) or DIRECT.match(tail)):
            if not tail.startswith('出门前'):
                continue
        if tail.startswith(('的时候特别有氛围', '人', '之后')):
            continue
        if not (INTRO.search(tail) or DIRECT.match(tail)):
            continue
        ab = advice_end(text, aa, ab)
        pair = make_pair(doc, (ca, cb), (aa, ab), unit.span(), 'implicit_condition', nearby_context(headers, unit.start()))
        if pair:
            results.append(pair)
    return results


def segment_pairs(doc, unit, headers):
    match = re.search(r'[\u4e00-\u9fff]+(?:→[\u4e00-\u9fff]+)+', unit.group())
    if not match:
        return []
    start, end = unit.start() + match.start(), unit.start() + match.end()
    # In the compact form the final place is immediately followed by the directive.
    marker = re.search(r'不建议|可以|建议', doc['clean_text'][start:unit.end()])
    if marker and start + marker.start() < end:
        end = start + marker.start()
    target = advice_start(doc['clean_text'], end, unit.end())
    if not target:
        return []
    aa, ab = target
    pair = make_pair(doc, (start, end), (aa, advice_end(doc['clean_text'], aa, ab)), unit.span(), 'route_segment', nearby_context(headers, unit.start()))
    return [pair] if pair else []


def suitability_pairs(doc, unit, headers):
    """Invert 'option suitable for X': X is the condition, option is the advice."""
    text, value = doc['clean_text'], unit.group()
    match = re.search(r'(?:很|最)?适合(?:人群】?[：:]|人群[：:])?\s*(.+)', value)
    if not match:
        return []
    ca, cb = unit.start() + match.start(1), unit.start() + match.end(1)
    # Parentheses and punctuation delimit the stated visitor/time constraint.
    end = re.search(r'[）)，,。！？!]', text[ca:cb])
    if end:
        cb = ca + end.start()
    if text[ca:cb] == '亲子慢逛':
        cb = ca + len('亲子')
    if not re.search(r'老人|小孩|带娃|赶时间|体力|年轻人|亲子|感兴趣|甄嬛传|想安安静静', text[ca:cb]):
        return []
    context = nearby_context(headers, unit.start())
    # A route title containing the suitability phrase is its own target.
    title_prefix = re.search(r'^([一二三四五六七八九十]+、[^（(]+)[（(]', value)
    if title_prefix:
        aa, ab = unit.start() + title_prefix.start(1), unit.start() + title_prefix.end(1)
    elif context:
        aa, ab = context['start'], context['end']
        qualifier = re.search(r'[（(｜]', text[aa:ab])
        if qualifier:
            ab = aa + qualifier.start()
    else:
        return []
    pair = make_pair(doc, (ca, cb), (aa, ab), (min(aa, unit.start()), unit.end()), 'suitable_for', context, 'suitable_option')
    return [pair] if pair else []


def normalize(value):
    value = unicodedata.normalize('NFKC', value)
    value = re.sub(r'^[\s，,]*(?:如果|假如|倘若|若)?(?:您|大家)?(?:是)?', '', value)
    value = re.sub(r'^(?:比较推荐|建议|推荐|可以|可)(?!不)', '', value)
    return re.sub(r'[\s，,。！？!?；;：:✅❌📌]', '', value)


def suppress_duplicates(pairs):
    accepted, duplicates = [], []
    priority = {'explicit_condition': 0, 'suitable_for': 1, 'route_segment': 1, 'implicit_condition': 2}
    for pair in sorted(pairs, key=lambda p: (priority[p['rule']], -(len(p['condition']) + len(p['advice'])), p['start'])):
        duplicate = next((a for a in accepted if a['doc_id'] == pair['doc_id']
                          and a['relation'] == pair['relation']
                          and a['condition_span']['start'] <= pair['condition_span']['end']
                          and pair['condition_span']['start'] <= a['condition_span']['end']
                          and normalize(pair['condition']) == normalize(a['condition'])
                          and (normalize(pair['advice']) in normalize(a['advice']) or normalize(a['advice']) in normalize(pair['advice']))), None)
        if duplicate:
            duplicates.append({'removed': pair['advice_id'], 'kept': duplicate['advice_id'], 'reason': 'same_position_or_contained_rule_match'})
        else:
            accepted.append(pair)
    return sorted(accepted, key=lambda p: (p['doc_id'], p['condition_span']['start'], p['advice_span']['start'])), duplicates


def extract(documents):
    pairs, candidates = [], []
    for doc in documents:
        units = list(UNITS.finditer(doc['clean_text']))
        headers = contexts(doc['clean_text'])
        for i, unit in enumerate(units):
            proposed = explicit_pairs(doc, units, i, headers)
            proposed += implicit_pairs(doc, unit, headers)
            proposed += suitability_pairs(doc, unit, headers)
            proposed += segment_pairs(doc, unit, headers)
            pairs.extend(proposed)
            if TRIGGER.search(unit.group()) or proposed:
                candidates.append({
                    'doc_id': doc['doc_id'], 'scenic_spot': doc['scenic_spot'],
                    **anchor(doc['clean_text'], *unit.span()),
                    'proposed_ids': [p['advice_id'] for p in proposed],
                    'reason': 'rule_proposal' if proposed else 'no_supported_condition_advice_pair',
                })
    accepted, duplicates = suppress_duplicates(pairs)
    return accepted, candidates, duplicates


def group_mappings(pairs):
    """Conservative exact/prefix grouping; keep every source occurrence."""
    groups = []
    for pair in pairs:
        context = normalize(pair['context']['text']) if pair['context'] else ''
        condition, advice = normalize(pair['condition']), normalize(pair['advice'])
        # Prefix grouping must not swallow a newly added prohibition or route/time number.
        signature = repr((re.findall(r'\d+(?:\.\d+)?', advice), re.findall(r'不建议|不推荐|不要|不能|不宜|慎选|别', advice)))
        key = (pair['scenic_spot'], pair['condition_type'], condition, context, pair['relation'], signature)
        group = next((g for g in groups if g['_key'] == key and
                      (advice == g['_advice'] or
                       (min(len(advice), len(g['_advice'])) / max(len(advice), len(g['_advice'])) >= .85 and
                        (advice.startswith(g['_advice']) or g['_advice'].startswith(advice))))), None)
        if group:
            group['occurrences'].append(pair['advice_id'])
            group['dedup_method'] = 'normalized_exact' if advice == group['_advice'] else 'normalized_prefix'
        else:
            groups.append({
                'mapping_id': 'map_' + stable_id(*key, advice),
                **{k: pair[k] for k in ('scenic_spot', 'condition_type', 'condition_types', 'condition', 'advice', 'relation')},
                'context': pair['context']['text'] if pair['context'] else None,
                'occurrences': [pair['advice_id']], 'dedup_method': 'single',
                '_key': key, '_advice': advice,
            })
    return [{k: v for k, v in g.items() if not k.startswith('_')} for g in groups]
