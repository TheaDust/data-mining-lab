"""Run from any directory: python task2/run.py v1 (or v2)."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib import request, error

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'task1/data/final/documents.jsonl'
OUT = ROOT / 'results'
TYPES = ('POI', 'TRANSPORT', 'TIME')
META = ('doc_id', 'scenic_spot', 'source_type', 'text_type', 'source_name', 'url')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    tmp.replace(path)


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def inputs():
    data = SOURCE.read_bytes()
    docs = [json.loads(line) for line in data.decode('utf8').split('\n') if line.strip()]
    assert len({d['doc_id'] for d in docs}) == len(docs)
    chunks = []
    for doc in docs:
        s = doc['clean_text']
        start = 0
        while start < len(s):
            end = min(start + 2400, len(s))
            # Prefer paragraph/sentence boundaries, retaining delimiters to preserve offsets.
            if end < len(s):
                cut = max(s.rfind(mark, start + 1600, end) for mark in ('\n', '。', '！', '？'))
                if cut >= 0:
                    end = cut + 1
            chunks.append(({**{k: doc[k] for k in META}, 'chunk_id': f"{doc['doc_id']}_{start}",
                            'chunk_start': start, 'chunk_end': end}, s[start:end]))
            start = end
    manifest = {'source': SOURCE.relative_to(ROOT.parent).as_posix(), 'sha256': digest(data),
                'documents': [{**{k: d[k] for k in META}, 'chars': len(d['clean_text'])} for d in docs],
                'chunks': [c for c, _ in chunks]}
    lock = OUT / 'input_manifest.json'
    if lock.exists():
        if load(lock) != manifest:
            raise SystemExit('Input or chunk mapping differs from the frozen manifest')
    else:
        dump(lock, manifest)
    return docs, chunks


def key():
    value = os.getenv('DEEPSEEK_API_KEY')
    if not value:
        f = ROOT.parent / '.env'
        m = re.search(r'^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=\s*(.+)$',
                      f.read_text(encoding='utf-8-sig') if f.exists() else '', re.M)
        value = m[1].strip().strip('"\'') if m else ''
    if not value:
        raise SystemExit('DEEPSEEK_API_KEY is missing')
    return value


def parse(raw):
    choice = raw['choices'][0]
    if choice['finish_reason'] != 'stop':
        raise ValueError('Incomplete response')
    rows = json.loads(choice['message']['content'])['entities']
    if not isinstance(rows, list):
        raise ValueError('entities must be an array')
    return rows


def call(meta, s, version, config, prompt):
    payload = json.dumps({**config, 'messages': [{'role': 'system', 'content': prompt},
                          {'role': 'user', 'content': s}]}, ensure_ascii=False).encode()
    folder = OUT / version / 'raw' / meta['chunk_id'] / digest(payload)
    if (folder / 'response.json').exists():
        return load(folder / 'response.json'), 'cache', []
    attempts = []
    for attempt in range(3):
        try:
            req = request.Request('https://api.deepseek.com/chat/completions', data=payload,
                                  headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key()})
            with request.urlopen(req, timeout=120) as response:
                raw = json.load(response)
            try:
                parse(raw)
            except (ValueError, KeyError, IndexError, TypeError):
                dump(folder / f'invalid_{time.time_ns()}.json', raw)
                raise
            dump(folder / 'response.json', raw)
            return raw, 'api', attempts
        except error.HTTPError as exc:
            attempts.append(f'HTTP {exc.code}')
            if exc.code not in (408, 429, 500, 502, 503, 504):
                break
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            attempts.append(type(exc).__name__)
        if attempt < 2:
            time.sleep(2 ** (attempt + 1))
    return None, 'failed', attempts


def align(meta, s, rows):
    candidates, issues = [], []
    for row in rows:
        if (not isinstance(row, dict) or row.get('type') not in TYPES
                or not isinstance(row.get('text'), str) or not row['text'].strip()):
            issues.append({'reason': 'schema', 'row': row})
            continue
        word, label = row['text'], row['type']
        # Lookahead counts even overlapping literal occurrences for ordinal addressing.
        starts = [m.start() for m in re.finditer(r'(?=' + re.escape(word) + ')', s)]
        if 'occurrence' in row:
            n = row['occurrence']
            starts = [starts[n - 1]] if type(n) is int and 1 <= n <= len(starts) else []
        if not starts:
            issues.append({'reason': 'unmatched', 'row': row})
        for start in starts:
            candidates.append((start, start + len(word), label, word))
    counts = Counter(candidates)
    # Longest span wins a nested conflict. Equal spans with different labels are
    # ambiguous and are excluded; never choose their type by alphabetical order.
    accepted = []
    for a, b, label, word in sorted(counts, key=lambda x: (x[0]-x[1], x)):
        if counts[a,b,label,word] > 1:
            issues.append({'reason': 'duplicate', 'text': word, 'start': a + meta['chunk_start'],
                           'count': counts[a,b,label,word]-1})
        if any(x == a and y == b and other != label for x,y,other,_ in counts):
            reason = 'type_conflict'
        elif any(a < y and x < b for x,y,_,_ in accepted):
            reason = 'overlap'
        else:
            accepted.append((a,b,label,word))
            continue
        issues.append({'reason': reason, 'text': word, 'type': label, 'start': a + meta['chunk_start']})
    base = meta['chunk_start']
    return [{**meta, 'text': word, 'type': label, 'start': a+base, 'end': b+base}
            for a,b,label,word in sorted(accepted)], [{**meta, **x} for x in issues]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('version', choices=('v1','v2'))
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--pilot', action='store_true', help='Probe one chunk before starting the batch')
    args = p.parse_args()
    docs, chunks = inputs()
    config = load(ROOT / 'config.json')
    prompt = (ROOT / 'prompts' / f'{args.version}.txt').read_text(encoding='utf8')
    def process(item):
        meta, s = item
        raw, status, attempts = call(meta, s, args.version, config, prompt)
        print(meta['chunk_id'], status, attempts, flush=True)
        return meta, s, raw, status, attempts
    if args.pilot:
        _, _, _, status, _ = process(chunks[0])
        return int(status == 'failed')
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(process, chunks))
    entities, issues, logs = [], [], []
    for meta, s, raw, status, attempts in results:
        logs.append({**meta, 'status':status, 'attempt_errors':attempts,
                     'usage': raw.get('usage', {}) if raw else {}, 'model': raw.get('model') if raw else None})
        if raw is not None:
            found, bad = align(meta, s, parse(raw))
            entities.extend(found)
            issues.extend(bad)
    by_id = {d['doc_id']:d['clean_text'] for d in docs}
    wrong = [e for e in entities if not (0 <= e['start'] < e['end'] <= len(by_id[e['doc_id']])
             and by_id[e['doc_id']][e['start']:e['end']] == e['text'])]
    folder = OUT / args.version
    dump(folder / 'entities.json', entities)
    dump(folder / 'issues.json', issues)
    dump(folder / 'run.json', {'configuration': config, 'prompt_sha256':digest(prompt.encode()),
         'input_sha256':load(OUT/'input_manifest.json')['sha256'], 'chunks':logs,
         'slice_checks':len(entities), 'slice_failures':wrong,
         'failed_chunks':sum(x['status']=='failed' for x in logs),
         'issue_counts': dict(Counter(x['reason'] for x in issues))})
    return int(bool(wrong) or any(x['status']=='failed' for x in logs))


if __name__ == '__main__':
    raise SystemExit(main())

