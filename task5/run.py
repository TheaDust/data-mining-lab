"""条件建议抽取：标准库完成联网与缓存，分析阶段另用 pandas/matplotlib。"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib import request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'task2'))
from run import key  # 复用上游凭据读取，任何输出均不包含凭据。

SOURCE = ROOT.parent / 'task1/data/final/documents.jsonl'
OUT = ROOT / 'results'
CATS = ['游客类型','天气环境','时间约束','体力与健康','交通条件','游览偏好','其他条件']
EXPLICIT = r'如果|假如|若是|若|只要|除非|倘若'
IMPLICIT = r'老人|老年|亲子|孩子|儿童|小孩|下雨|雨天|晴天|炎热|高温|冬季|夏季|旺季|淡季|周末|节假日|体力|高反|高原反应|自驾|乘车|时间有限|时间充裕|赶时间|喜欢|想要|想看|想拍|感兴趣|适合|时候|的话|时，|人多|人最多|拥挤|排队'
ADVICE = r'建议|可以|最好|推荐|尽量|避免|不妨|务必|需要|应当|注意|不要|记得|提前'

def save(name, obj):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf8')

def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def build():
    docs = [json.loads(l) for l in SOURCE.read_text(encoding='utf8').splitlines() if l.strip()]
    pieces = []
    for d in docs:
        text = d['clean_text']
        # 以段落为硬边界，相邻两句窗口保留跨句条件；窗口重叠由后续同源去重处理。
        for para in re.finditer(r'[^\n]+', text):
            sentences = list(re.finditer(r'[^。！？!?]+[。！？!?]?', para[0]))
            for i, s in enumerate(sentences):
                end = sentences[min(i+1,len(sentences)-1)].end()
                start = para.start()+s.start()
                fragment = text[start:para.start()+end]
                reason = 'explicit' if re.search(EXPLICIT,fragment) else 'implicit' if re.search(IMPLICIT,fragment) else 'advice_only' if re.search(ADVICE,fragment) else 'unselected'
                pieces.append(dict(id=f"{d['doc_id']}:{start}",doc_id=d['doc_id'],scenic_area=d['scenic_spot'],source_type=d['source_type'],url=d['url'],start=start,end=para.start()+end,source_text=fragment,rule=reason))
    save('input_manifest.json',dict(path=str(SOURCE),sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),documents=[{k:v for k,v in d.items() if k not in ('raw_text','clean_text')} for d in docs]))
    save('all_windows.json',pieces)
    candidates=[p for p in pieces if p['rule']!='unselected']
    save('candidates.json',candidates)
    return docs,pieces,candidates

def call(batch):
    config=load(ROOT.parent/'task2/config.json')
    config['max_tokens']=6000
    prompt=(ROOT/'prompt.txt').read_text(encoding='utf8')
    payload=json.dumps({**config,'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps([{'id':p['id'],'text':p['source_text']} for p in batch],ensure_ascii=False)}]},ensure_ascii=False).encode()
    h=hashlib.sha256(payload).hexdigest()
    p=OUT/'cache'/f'{h}.json'
    if p.exists():
        raw=load(p)
        return raw,'cache',h
    for attempt in range(3):
        try:
            req=request.Request('https://api.deepseek.com/chat/completions',data=payload,headers={'Content-Type':'application/json','Authorization':'Bearer '+key()})
            with request.urlopen(req,timeout=150) as r:
                response=json.load(r)
            choice=response['choices'][0]
            if choice['finish_reason']!='stop':
                raise ValueError('truncated response')
            pairs=json.loads(choice['message']['content'])['pairs']
            if not isinstance(pairs,list):
                raise ValueError('pairs must be list')
            raw={'pairs':pairs,'model':response.get('model'),'usage':response.get('usage'),'config':config,'prompt_version':'v2','attempts':attempt+1}
            save(f'cache/{h}.json',raw)
            return raw,'network',h
        except Exception as e:
            # 不保存 HTTP 正文和请求头，防止服务错误回显敏感认证信息。
            if attempt==2:
                return {'pairs':[],'error':type(e).__name__},'failed',h
            time.sleep(2**attempt)

def normalize(s):
    # 仅移除无语义前缀及标点；不删除否定、数字、程度副词，避免改变适用条件。
    s=re.sub(r'^(如果|假如|若是|若|建议|最好|可以|推荐|尽量)+','',s.strip())
    return re.sub(r'[\s，。；、：！!？?"“”]','',s)

def finish(docs,pieces,candidates,results,audit):
    index={p['id']:p for p in pieces}
    raw=[]; rejected=[]; checked=[]
    for response,status,h in results:
        for item in response['pairs']:
            raw.append(dict(item,cache_id=h))
            p=index.get(item.get('id'))
            fields=['condition','recommendation','evidence_span']
            error='unknown_id' if not p else next((f'invalid_{f}' for f in fields if not isinstance(item.get(f),str) or not item[f].strip() or item[f] not in p['source_text']),None)
            if not error and any(item[f] not in item['evidence_span'] for f in fields[:2]): error='evidence_not_covering'
            if not error and item.get('condition_type') not in CATS: error='invalid_category'
            # 实际误差中出现模型无视 Prompt 的残片、评价和顺序描述，保守隔离而不臆补对象。
            if not error:
                c,r=item['condition'],item['recommendation']
                if r.strip('！!。，') in ('慎选','适合','选这里','直接抄作业'):
                    error='unresolved_recommendation_target'
                elif re.search(r'拍照才好看|特别有氛围感|开启.*之旅',r):
                    error='evaluation_not_action'
                elif c in ('进门','吃饭','天鹅海结束','漫步群山之余') or re.search(r'下车后$|→',c):
                    error='sequence_not_condition'
                elif c in r or r in c:
                    error='overlapping_condition_action'
                elif c=='容易晕' and '不容易晕' in item['evidence_span']:
                    error='negation_boundary'
                elif '记得上午去' in r and '下午3点后' in c:
                    error='time_boundary_needs_context'
                elif c.startswith('财') or c=='7 座古寺一次串':
                    error='list_not_condition'
            if error:
                rejected.append(dict(item,reason=error)); continue
            offsets={f:p['start']+p['source_text'].index(item[f]) for f in fields}
            checked.append({**p,**item,'pair_id':f'R{len(checked)+1:05d}','offsets':offsets,'extraction_method':'regex+LLM','prompt_version':'v2','review_status':'待人工确认','audit_candidate':p['rule']=='unselected'})
    save('raw_pairs.json',raw); save('validated_pairs.json',checked); save('rejected_pairs.json',rejected)
    # 保守近重复：建议去前缀后相等才合并。其余相似表达仅列为待核验，不自动做语义合并。
    groups={}; merges=[]
    for row in checked:
        k=(row['scenic_area'],normalize(row['condition']),normalize(row['recommendation']))
        provenance={f:row[f] for f in ('pair_id','doc_id','id','source_type','url','source_text','evidence_span','offsets')}
        if k in groups:
            groups[k]['sources'].append(provenance)
            merges.append({'kept':groups[k]['pair_id'],'merged':row['pair_id'],'reason':'condition_and_recommendation_normalized_equal'})
        else:
            groups[k]={**row,'sources':[provenance],'normalized_condition':k[1],'normalized_recommendation':k[2]}
    final=list(groups.values())
    save('final_mapping.json',final); save('dedup_log.json',merges)
    from difflib import SequenceMatcher
    near=[]
    for i,a in enumerate(final):
        for b in final[i+1:]:
            if a['scenic_area']==b['scenic_area'] and a['normalized_condition']==b['normalized_condition']:
                x,y=a['normalized_recommendation'],b['normalized_recommendation']
                if x in y or y in x or SequenceMatcher(None,x,y).ratio()>=.75:
                    near.append(dict(left=a['pair_id'],right=b['pair_id'],action='保留两条，待人工判定范围与否定差异'))
    save('near_duplicate_review.json',near)
    counts=Counter(r['condition_type'] for r in final)
    summary=dict(documents=len(docs),windows=len(pieces),candidates=len(candidates),negative_audit_windows=len(audit),raw_pairs=len(raw),validated_pairs=len(checked),rejected_pairs=len(rejected),final_pairs=len(final),merged=len(merges),categories={c:counts[c] for c in CATS},calls=Counter(s for _,s,_ in results),failed_batches=[h for r,s,h in results if s=='failed'],audit_discoveries=sum(r['audit_candidate'] for r in checked),document_distribution={f'{a}/{b}':n for (a,b),n in Counter((d['scenic_spot'],d['source_type']) for d in docs).items()})
    save('summary.json',summary)
    save('run_log.json',[dict(cache_id=h,status=s,**{k:v for k,v in r.items() if k!='pairs'}) for r,s,h in results])
    # 分层抽样覆盖不同景区、来源、类别，同时保留无预测窗口用于 FN 检查。
    sample=[]; strata=Counter()
    for r in final:
        k=(r['scenic_area'],r['source_type'],r['condition_type'])
        if strata[k]<2:
            sample.append(dict(sample_type='prediction',pair_id=r['pair_id'],doc_id=r['doc_id'],source_text=r['source_text'],condition=r['condition'],recommendation=r['recommendation'],condition_type=r['condition_type'])); strata[k]+=1
    predicted={r['id'] for r in checked}
    for p in audit+[p for p in candidates if p['id'] not in predicted][:20]:
        sample.append(dict(sample_type='negative_window',pair_id='',doc_id=p['doc_id'],source_text=p['source_text'],condition='',recommendation='',condition_type=''))
    for r in sample: r.update(human_condition='',human_recommendation='',error_type='',human_label='',reviewer='',review_status='待人工确认')
    save('human_review.json',sample)
    save('automatic_checks.json',dict(evidence_checked=len(raw),rejected=len(rejected),human_completed=0,precision=None,recall=None,f1=None,notes='证据子串一致不等于语义正确；无人工金标准不计算P/R/F1。'))
    print(json.dumps(summary,ensure_ascii=False))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--smoke',action='store_true'); args=ap.parse_args()
    # 审核后的默认复跑必须重放冻结补丁，不能用旧自动过滤结果覆盖最终成果。
    if not args.smoke and (ROOT/'audit_resolution/task5_independent_audit.json').exists():
        from finalize import main as finalize_main
        finalize_main()
        return
    docs,pieces,candidates=build()
    if args.smoke:
        r=call(candidates[:4]); save('smoke.json',r); print('smoke',r[1],len(r[0]['pairs'])); return
    # 未命中窗口按每文档均匀取至多两条，审核筛选外漏召回，不能据此声称全局召回率。
    audit=[]
    for d in docs:
        neg=[p for p in pieces if p['doc_id']==d['doc_id'] and p['rule']=='unselected']
        audit+=neg[::max(1,len(neg)//2)][:2]
    save('negative_audit.json',audit)
    batches=[candidates[i:i+6] for i in range(0,len(candidates),6)]+[audit[i:i+6] for i in range(0,len(audit),6)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(call,batches))
    finish(docs,pieces,candidates,results,audit)

if __name__=='__main__': main()
