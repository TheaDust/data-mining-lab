"""只读现有实验产物，准备独立语义审核材料；不导入抽取入口，不联网。"""
import ast
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'review_package'
RESULTS = ROOT / 'results'
SOURCE = ROOT.parent / 'task1/data/final/documents.jsonl'
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def frozen_hashes():
    # 包括全部历史缓存与结果，而非只保护最终表；导出目录和依赖不属于实验基线。
    files = list(RESULTS.rglob('*')) + list((ROOT / 'baseline').rglob('*'))
    files += [SOURCE] + list(ROOT.glob('*.py')) + list(ROOT.glob('*.txt')) + list(ROOT.glob('*.md'))
    return {p.relative_to(ROOT.parent).as_posix(): sha(p.read_bytes()) for p in sorted(set(files)) if p.is_file()}


def signature(row):
    return tuple(row.get(f) for f in ('id', 'condition', 'recommendation', 'evidence_span', 'condition_type'))


RULES = {
    'unknown_id': ('窗口 ID 不在当前 all_windows 中', "p=index.get(item.get('id')); not p"),
    'invalid_recommendation': ('建议缺失、空、类型不正确或不是原始窗口的连续子串', "not isinstance(item.get('recommendation'),str) or not item['recommendation'].strip() or item['recommendation'] not in p['source_text']"),
    'unresolved_recommendation_target': ('建议去除末尾指定标点后恰为预设残片之一', "r.strip('！!。，') in ('慎选','适合','选这里','直接抄作业')"),
    'evaluation_not_action': ('建议匹配预设评价或修辞表达', "re.search(r'拍照才好看|特别有氛围感|开启.*之旅',r)"),
    'sequence_not_condition': ('条件匹配预设顺序片段或箭头路线', "c in ('进门','吃饭','天鹅海结束','漫步群山之余') or re.search(r'下车后$|→',c)"),
    'overlapping_condition_action': ('条件与建议相互包含', 'c in r or r in c'),
    'negation_boundary': ('预测容易晕，但证据含不容易晕', "c=='容易晕' and '不容易晕' in item['evidence_span']"),
    'time_boundary_needs_context': ('建议上午去而条件含下午3点后，程序隔离待查', "'记得上午去' in r and '下午3点后' in c"),
    'list_not_condition': ('条件匹配此前特定列表表达的过滤规则', "c.startswith('财') or c=='7 座古寺一次串'"),
}


def main():
    OUT.mkdir(exist_ok=True)
    before = frozen_hashes()
    docs = [json.loads(line) for line in SOURCE.read_text(encoding='utf8').splitlines() if line.strip()]
    doc_index = {d['doc_id']: d for d in docs}
    windows = read(RESULTS / 'all_windows.json')
    window_index = {w['id']: w for w in windows}
    candidates = read(RESULTS / 'candidates.json')
    audit = read(RESULTS / 'negative_audit.json')
    raw = read(RESULTS / 'raw_pairs.json')
    final = read(RESULTS / 'final_mapping.json')
    checked = read(RESULTS / 'validated_pairs.json')
    checked_index = {r['pair_id']: r for r in checked}
    rejected = read(RESULTS / 'rejected_pairs.json')
    merges = read(RESULTS / 'dedup_log.json')

    # 用原始的配置、Prompt、批次顺序重建哈希，只查本地响应。哈希对不上即停止，不能猜测空响应。
    config = read(ROOT.parent / 'task2/config.json')
    config['max_tokens'] = 6000
    prompt = (ROOT / 'prompt.txt').read_text(encoding='utf8')
    batches = [candidates[i:i+6] for i in range(0,len(candidates),6)] + [audit[i:i+6] for i in range(0,len(audit),6)]
    calls = {}
    batch_hashes = []
    reconstructed_raw = []
    for batch in batches:
        payload = json.dumps({**config, 'messages': [
            {'role':'system','content':prompt},
            {'role':'user','content':json.dumps([{'id':w['id'],'text':w['source_text']} for w in batch],ensure_ascii=False)}
        ]}, ensure_ascii=False).encode()
        h = sha(payload)
        cache = read(RESULTS / 'cache' / f'{h}.json')
        batch_hashes.append(h)
        reconstructed_raw += [dict(r, cache_id=h) for r in cache['pairs']]
        for w in batch:
            calls[w['id']] = dict(cache_id=h, model=cache.get('model'), prompt_version=cache.get('prompt_version'),
                                  call_success='error' not in cache,
                                  returned_pairs=[r for r in cache['pairs'] if r.get('id')==w['id']],
                                  batch_result_count=len(cache['pairs']))
    assert reconstructed_raw == raw
    assert batch_hashes == [x['cache_id'] for x in read(RESULTS / 'run_log.json')]

    raw_index = defaultdict(list)
    for i,r in enumerate(raw,1):
        raw_index[signature(r)].append((i,r))

    def raw_refs(r):
        return [{'raw_record_id':f'RAW-{i:04d}', 'raw_array_index_0based':i-1, 'cache_id':x['cache_id']}
                for i,x in raw_index[signature(r)]]

    def context(w):
        d = doc_index[w['doc_id']]
        text = d['clean_text']; start,end = w['start'],w['end']
        assert text[start:end] == w['source_text']
        paragraphs = list(re.finditer(r'[^\n]+',text))
        touched = [i for i,p in enumerate(paragraphs) if p.start()<end and p.end()>start]
        assert touched
        # 逐字保留所在整段及前后各一段，标题、路线指代有更大依赖时可直接看F全文。
        left = paragraphs[max(0,min(touched)-1)].start()
        right = paragraphs[min(len(paragraphs)-1,max(touched)+1)].end()
        return dict(window_id=w['id'], doc_id=w['doc_id'], scenic_area=w['scenic_area'],
                    source_type=w['source_type'], source_type_label={'official':'官方指南','user_generated':'游客游记'}.get(w['source_type'],w['source_type']),
                    source_title=d.get('title'), source_url=d.get('url'), source_text=w['source_text'],
                    source_start=start, source_end=end, context_before=text[left:start], context_after=text[end:right],
                    context_full=text[left:right], context_start=left, context_end=right,
                    full_document_ref=w['doc_id'], missing_fields=[],review_status='待审核')

    def enriched(r):
        w=window_index[r['id']]
        return {**r,**context(w),'raw_record_refs':raw_refs(r),'review_status':'待审核'}

    A=[]
    for r in final:
        item=enriched(r)
        item['sources']=[enriched(checked_index[p['pair_id']]) for p in r['sources']]
        item['merged_source_ids']=[p['pair_id'] for p in r['sources']]
        item['merge_removed_source_ids']=[p['pair_id'] for p in r['sources'] if p['pair_id']!=r['pair_id']]
        A.append(item)
    B=[]
    for r in rejected:
        refs=raw_refs(r); assert len(refs)==1
        original=raw[refs[0]['raw_array_index_0based']]
        description,code=RULES[r['reason']]
        item={**enriched(r),'review_record_id':'B-'+refs[0]['raw_record_id'],
              'original_relation_id':None,'original_id_note':'原始输出没有独立关系ID；RAW编号按冻结的raw_pairs数组位置补建，原始id为窗口ID',
              'raw_record_id':refs[0]['raw_record_id'],'raw_model_output':original,
              'quarantine_reason':r['reason'],'validation_rule_description':description,'validation_rule_code':code,
              'prediction_substring_checks':{f:isinstance(r.get(f),str) and r[f] in window_index[r['id']]['source_text'] for f in ('condition','recommendation','evidence_span')}}
        item['missing_fields']=['original_relation_id (原始文件未分配独立关系ID)']
        B.append(item)

    # 读取常量只为解释当时规则，不执行 run.py，也不重新选择36个窗口。
    constants={n.targets[0].id:ast.literal_eval(n.value) for n in ast.parse((ROOT/'run.py').read_text(encoding='utf8')).body
               if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('EXPLICIT','IMPLICIT','ADVICE')}
    def triggers(w):
        return {name:[{'text':m[0],'start_in_window':m.start(),'end_in_window':m.end()} for m in re.finditer(pattern,w['source_text'])] for name,pattern in constants.items()}
    C=[]
    for w in audit:
        assert w['rule']=='unselected'
        assert not any(triggers(w).values())
        C.append({**context(w),'rule':w['rule'],'rule_miss_reason':'EXPLICIT、IMPLICIT、ADVICE均未命中（已对照现有冻结规则核对）',
                  'llm_review_performed':True,'llm_original_extractor_check':calls[w['id']],
                  'llm_result_note':'原抽取模型同源检查，不是独立语义审核结论'})

    eligible=[w for w in candidates if calls[w['id']]['call_success'] and not calls[w['id']]['returned_pairs']]
    strata=defaultdict(list)
    seed='task5-independent-review-20261107-v1'
    for w in eligible:
        strata[(w['scenic_area'],w['source_type'],w['rule'])].append(w)
    for group in strata.values():
        group.sort(key=lambda w:sha((seed+'|'+w['id']).encode()))
    selected=[]
    # 固定种子哈希排序后按景区×来源×最高优先级规则轮转，覆盖小样本官方层。
    while len(selected)<min(20,len(eligible)):
        for k in sorted(strata):
            if strata[k] and len(selected)<20:
                selected.append(strata[k].pop(0))
    D=[{**context(w),'candidate_id':w['id'],'rule':w['rule'],'trigger_matches':triggers(w),
        'llm_result':calls[w['id']], 'current_rejection_reason':None,
        'rejection_note':'本窗口模型pairs为空；旧结果没有逐窗口拒绝解释，不推测原因',
        'missing_fields':['current_rejection_reason (历史响应未提供)']} for w in selected]

    grouped=defaultdict(list)
    for m in merges: grouped[m['kept']].append(m)
    E=[]
    for kept,ops in grouped.items():
        r=next(x for x in final if x['pair_id']==kept)
        ids=[kept]+[x['merged'] for x in ops]
        assert set(ids)=={x['pair_id'] for x in r['sources']}
        E.append({'merge_group_id':'MG-'+kept, 'retained_pair_id':kept,'member_record_ids':ids,
                  'removed_record_ids':[x['merged'] for x in ops], 'members':[enriched(checked_index[i]) for i in ids],
                  'retained_condition':r['condition'],'retained_recommendation':r['recommendation'],
                  'normalized_condition':r['normalized_condition'],'normalized_recommendation':r['normalized_recommendation'],
                  'rule':'同景区且条件、建议分别规范化后均相等；删除指定前缀及空白标点，不做全面语义合并',
                  'normalization_code':"re.sub(r'^(如果|假如|若是|若|建议|最好|可以|推荐|尽量)+','',s.strip()); re.sub(r'[\\s，。；、：！!？?\"“”]','',s)",
                  'operations':ops,'review_status':'待审核'})
    F=[{'doc_id':d['doc_id'],'scenic_area':d['scenic_spot'],'source_type':d['source_type'],'title':d.get('title'),
        'url':d.get('url'),'clean_text':d['clean_text'],'source_file':'task1/data/final/documents.jsonl'} for d in docs]
    near=read(RESULTS/'near_duplicate_review.json')
    G=[{**r,'left_record':next(x for x in A if x['pair_id']==r['left']),
        'right_record':next(x for x in A if x['pair_id']==r['right']),'review_status':'待审核'} for r in near]
    groups={'A_final_pairs.json':A,'B_quarantined.json':B,'C_rule_missed.json':C,'D_llm_rejected.json':D,
            'E_dedup_merges.json':E,'F_source_documents.json':F,'G_near_duplicates.json':G}
    for name,rows in groups.items(): dump(name,rows)

    # Excel单元格保留合法JSON序列化的嵌套值，另设明细页让审核者无需解析JSON也可阅读合并来源。
    wb=Workbook(); wb.remove(wb.active)
    sheet_rows={'A_FinalPairs':A,'B_Quarantined':B,'C_RuleMissed':C,'D_LLMRejected':D,'E_DedupMerges':E,
                'A_SourceDetails':[{'final_pair_id':r['pair_id'],**p} for r in A for p in r['sources']],
                'E_MergeMembers':[{'merge_group_id':r['merge_group_id'],**p} for r in E for p in r['members']],
                'F_SourceDocuments':F,'G_NearDuplicates':G}
    feedback=['review_decision','error_types','corrected_condition','corrected_recommendation','corrected_condition_type','review_notes','reviewer']
    priority=['pair_id','review_record_id','window_id','candidate_id','merge_group_id','doc_id','scenic_area','source_type_label',
              'condition_type','condition','recommendation','source_text','context_before','context_after','evidence_span']
    expected={}; longest=0
    for name,rows in sheet_rows.items():
        ws=wb.create_sheet(name)
        keys=list(dict.fromkeys(k for r in rows for k in r))
        columns=[k for k in priority if k in keys]+[k for k in keys if k not in priority]+feedback
        if not rows: columns=['review_status']+feedback
        ws.append(columns)
        for row in rows:
            values=[]
            for k in columns:
                v=row.get(k)
                if isinstance(v,(dict,list)): v=json.dumps(v,ensure_ascii=False)
                if isinstance(v,str):
                    longest=max(longest,len(v))
                    assert len(v)<=32767, f'Excel字符串长度超过上限: {name}/{k}'
                values.append(v)
            ws.append(values)
            # 全部文本显式存为字符串，避免 = 前缀原文被Excel解释为公式。
            for cell in ws[ws.max_row]:
                if isinstance(cell.value,str): cell.data_type='s'
        ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]:
            cell.font=Font(bold=True,color='FFFFFF'); cell.fill=PatternFill('solid',fgColor='24476A')
            cell.alignment=Alignment(wrap_text=True,vertical='top')
        ws.row_dimensions[1].height=34
        for j,k in enumerate(columns,1):
            width=68 if any(t in k for t in ('text','context','evidence','members','sources','output','rule_code')) else 42 if k in ('condition','recommendation','doc_id','window_id','candidate_id') else 25
            ws.column_dimensions[get_column_letter(j)].width=width
        for row in ws.iter_rows(min_row=2):
            for cell in row: cell.alignment=Alignment(wrap_text=True,vertical='top')
            ws.row_dimensions[row[0].row].height=150
        expected[name]=(columns,rows)
    wb.save(OUT/'review_all.xlsx')
    reread=load_workbook(OUT/'review_all.xlsx',data_only=False)
    for name,(columns,rows) in expected.items():
        persisted=list(reread[name].values)
        assert list(persisted[0])==columns
        assert len(persisted)==len(rows)+1
        for actual,row in zip(persisted[1:],rows):
            for k,v in zip(columns,actual):
                wanted=row.get(k)
                if isinstance(wanted,(list,dict)): assert json.loads(v)==wanted
                # XLSX把空字符串持久化为空单元格；按JSON字段类型恢复空上下文，而非误报原文丢失。
                else: assert v==wanted or (v is None and wanted==''), (name,k)

    assert (len(A),len(B),len(C),len(D),len(merges))==(32,15,36,20,5)
    assert len(E)==5
    assert len({x['pair_id'] for x in A})==len(A)
    assert len({x['raw_record_id'] for x in B})==len(B)
    assert [x['window_id'] for x in C]==[x['id'] for x in audit]
    assert not {x['window_id'] for x in C}&{x['window_id'] for x in D}
    assert {x['candidate_id'] for x in D}<={x['id'] for x in eligible}
    assert len({p['pair_id'] for r in A for p in r['sources']})==len(checked)==37
    assert len(raw)==len(checked)+len(B)==52
    after=frozen_hashes(); assert before==after
    dump('integrity_checks.json',{'status':'passed','counts':{k:len(v) for k,v in groups.items()},
         'dedup_operations':len(merges),'D_eligible_population':len(eligible),'D_sampling_seed':seed,
         'D_sampling_method':'景区×来源×优先级规则分层，固定种子SHA256排序，逐层轮转取20条',
         'D_strata':{' / '.join(k):sum((r['scenic_area'],r['source_type'],r['rule'])==k for r in D) for k in sorted(strata)},
         'checks':{'all_A_final_ids_preserved':True,'all_B_raw_records_recovered':True,'C_exact_historical_order':True,
                   'D_actual_successful_empty_model_outputs':True,'C_D_disjoint':True,'E_all_operations_and_sources':True,
                   'context_exact_source_slices':True,'batch_hashes_match_historical_log':True,'cached_pairs_equal_raw_file':True,
                   'excel_json_all_cells_equal':True,'excel_text_untruncated':True,'review_judgments_empty':True,'baseline_hashes_unchanged':True},
         'max_excel_cell_chars':longest,'missing_source_or_context_records':0,
         'missing_historical_fields':['B原始关系无独立ID，以RAW数组索引补建','D历史响应无逐窗口拒绝解释，保留null'],
         'source_hashes_before':before,'source_hashes_after':after})
    dump('package_manifest.json',{'files':{p.name:sha(p.read_bytes()) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='package_manifest.json'}})
    print(json.dumps({'A':len(A),'B':len(B),'C':len(C),'D':len(D),'E_groups':len(E),'E_operations':len(merges),'G':len(G),'D_eligible':len(eligible),'max_cell_chars':longest,'integrity':'passed'}))


if __name__=='__main__': main()
