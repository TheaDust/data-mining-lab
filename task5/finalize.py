"""冻结自动结果，落实独立LLM审核。仅使用本地证据，修正表是可重放的版本化补丁。"""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results'
AUD=ROOT/'audit_resolution'
SNAP=ROOT/'history/pre_independent_audit'
CATS=['游客类型','天气环境','时间约束','体力与健康','交通条件','游览偏好','其他条件']

def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def hashes(folder): return {p.relative_to(folder).as_posix():digest(p) for p in sorted(folder.rglob('*')) if p.is_file()}
def norm(s):
    # 与原后处理相同，仅做可解释的字符串规范化；语义重述由有证据的补丁显式指定。
    return re.sub(r'[\s，。；、：！!？?"“”]','',re.sub(r'^(如果|假如|若是|若|建议|最好|可以|推荐|尽量)+','',s.strip()))

def snapshot():
    if not (SNAP/'snapshot_manifest.json').exists():
        assert not SNAP.exists(), '未完成快照需检查，不能覆盖历史'
        SNAP.mkdir(parents=True)
        shutil.copytree(OUT,SNAP/'results')
        for name in ('REPORT.md','README.md','analyze.py','run.py','export.mjs','prompt.txt','prompt_v1.txt'):
            shutil.copy2(ROOT/name,SNAP/name)
        dump(SNAP/'snapshot_manifest.json',hashes(SNAP))
    else:
        expected=load(SNAP/'snapshot_manifest.json')
        assert expected=={k:v for k,v in hashes(SNAP).items() if k!='snapshot_manifest.json'}

def main():
    snapshot()
    audit=load(AUD/'task5_independent_audit.json')
    package_before=hashes(ROOT/'review_package')
    frozen_before=hashes(SNAP)
    base=load(SNAP/'results/final_mapping.json')
    checked={r['pair_id']:r for r in load(SNAP/'results/validated_pairs.json')}
    index={r['pair_id']:r for r in base}
    A={r['pair_id']:r for r in load(ROOT/'review_package/A_final_pairs.json')}
    B={r['review_record_id']:r for r in load(ROOT/'review_package/B_quarantined.json')}
    D={r['candidate_id']:r for r in load(ROOT/'review_package/D_llm_rejected.json')}
    docs={r['doc_id']:r for r in load(ROOT/'review_package/F_source_documents.json')}
    reviews={(r['group'],r['record_id']):r for r in audit['items']}
    assert len(reviews)==len(audit['items'])==108
    expected={'A':set(A),'B':set(B),'C':{r['window_id'] for r in load(ROOT/'review_package/C_rule_missed.json')},
              'D':set(D),'E':{r['merge_group_id'] for r in load(ROOT/'review_package/E_dedup_merges.json')}}
    assert all({rid for g,rid in reviews if g==group}==ids for group,ids in expected.items())
    source_path=ROOT.parent/'task1/data/final/documents.jsonl'
    actual_docs={r['doc_id']:r['clean_text'] for r in (json.loads(l) for l in source_path.read_text(encoding='utf8').splitlines() if l.strip())}
    assert actual_docs=={k:v['clean_text'] for k,v in docs.items()}, '当前原文与审核包不一致，不能错误应用旧审核'

    # 每个补丁均指向审核记录。canonical可以补全指代；verbatim永远是逐字原文，二者不混淆。
    specs=[
      dict(group='A',rid='R00009',condition='初次来',recommendation='不建议为了省几步路中轴线和东西宫来回穿梭',cat='游客类型'),
      dict(group='A',rid='R00012',condition='带娃',recommendation='在神武门收尾，跟孩子科普溥仪离开皇宫以后的故事',cat='游客类型',rv='在这里收尾，顺便跟孩子科普一下溥仪离开皇宫以后经理的伪满洲国等其他故事',quotes=['神武门'],note='补全这里指向神武门；经理为原文错字，保留在逐字证据中。'),
      dict(group='A',rid='R00014',condition='太和殿广场全是人',recommendation='下午1点左右进场',cat='其他条件',note='采纳关系方向问题，但使用明确的拥挤情境，不凭空补出希望舒适拍照的偏好。'),
      dict(group='A',rid='R00017',condition='带小朋友',recommendation='去花港观鱼喂锦鲤',cat='游客类型',rv='花港观鱼可以喂锦鲤',note='原句带小朋友喜欢表明对象适配；行动为有上下文依据的隐式推荐，逐字证据仍保留原句。'),
      dict(group='A',rid='R00018',condition='周末节假日',recommendation='自驾记得查政策',cat='时间约束',note='审核称时间类别可保留，但实际原类别为交通；据条件含义纠正为时间约束。'),
      dict(group='A',rid='R00019',condition='周末人挤人的话',recommendation='🉑选凤起路出站',cat='其他条件',note='完整保留周末限定，主要触发为拥挤。'),
      dict(group='A',rid='R00024',condition='打算坐船',recommendation='出门前留意天气预报',cat='交通条件',note='风雨是提醒原因，打算坐船才是适用条件。'),
      dict(group='A',rid='R00029',condition='想安安静静欣赏风景的人',recommendation='游览茅家埠（上香古道）',cat='游览偏好',rv='一个冷门的宝藏景点，就在西湖的西侧是曾经的上香古道',quotes=['5️⃣茅家埠'],note='段落标题与适合表述共同支撑隐式推荐，不把景点介绍本身当动作。'),
      dict(group='A',rid='R00033',condition='现场看路线距离非常远，后面还有五花海、珍珠滩等真正的精华，没必要提前把体力耗光',recommendation='乘观光车从天鹅海前往箭竹海',cat='体力与健康',rv='直接选择坐观光车',quotes=['天鹅海→箭竹海不建议徒步'],note='补齐原关系的行程对象，为与B恢复记录的保守同义合并提供直接原文依据。'),
      dict(group='B',rid='B-RAW-0013',condition='吃饭',recommendation='选择冰窖餐厅',cat='其他条件',rv='可以选这里',quotes=['冰窖餐厅'],note='同句这里有明确先行词，原残片过滤过严。'),
      dict(group='B',rid='B-RAW-0014',condition='想拍蓝天配黄瓦红墙的照片',recommendation='提前看好未来一周的天气预报，哪天晴天选哪天',cat='游览偏好',cv='蓝天配黄瓦红墙拍照才好看',note='摄影目的由紧邻的晴天选择与拍照理由隐含支持；条件为显式标注的语义归一化，不声称逐字出现想拍。'),
      dict(group='B',rid='B-RAW-0016',condition='带娃/赶时间',recommendation='选择半天精华线（2.5～3小时）',cat='游客类型',rv='半天精华线',note='标题适合带娃/赶时间支持路线选择；斜线表示备选对象，不拆为组合AND条件。'),
      dict(group='B',rid='B-RAW-0021',condition='带老人小孩',recommendation='慎选路线1（东华门→午门）',cat='游客类型',rv='慎选',quotes=['路线 1（省心避人流｜红线）：东华门→午门'],note='跨段标题恢复慎选的明确对象。'),
      dict(group='B',rid='B-RAW-0022',condition='赶时间',recommendation='慎选路线4（中山公园→午门）',cat='时间约束',rv='慎选',quotes=['路线 4（小众舒适｜蓝线）：中山公园→午门'],note='由原位置所在路线4段落标题定位对象。'),
      dict(group='B',rid='B-RAW-0023',condition='体力好的年轻人',recommendation='选择路线5（西华门→午门）',cat='体力与健康',rv='适合体力好的年轻人',quotes=['路线 5（人少清净｜紫线）：西华门→午门'],note='适合构成隐式路线选择，分类按体力约束。'),
      dict(group='B',rid='B-RAW-0027',condition='计划乘船游乌龟潭路线',recommendation='上午前往乘船',cat='交通条件',cv='推荐乌龟潭路线',rv='记得上午去',quotes=['下午3点后船工基本不接这个路线了'],note='乌龟潭路线意图是语义归一化条件；下午3点后不接是时间限制证据，不作为已发生条件。主类别取出行方式意图，未机械沿用审核建议的时间分类。'),
      dict(group='B',rid='B-RAW-0047',condition='现场看路线距离非常远，后面还有五花海、珍珠滩等真正的精华，没必要提前把体力耗光',recommendation='乘观光车从天鹅海前往箭竹海',cat='体力与健康',rv='天鹅海结束直接坐车去箭竹海',quotes=['天鹅海→箭竹海不建议徒步'],note='恢复跨句的距离与体力限制后，与现有R00033合并而非增加重复。'),
      dict(group='B',rid='B-RAW-0048',condition='现场看路线距离非常远，后面还有五花海、珍珠滩等真正的精华，没必要提前把体力耗光',recommendation='乘观光车从天鹅海前往箭竹海',cat='体力与健康',rv='天鹅海结束直接坐车去箭竹海',quotes=['天鹅海→箭竹海不建议徒步'],note='与B-RAW-0047和R00033同一关系，合并保留全部审核及来源引用。'),
      dict(group='D',rid='jiuzhaigou_user_generated_0ed001d738cb93a5:640',condition='如果是分配到右线开始',recommendation='放弃左线，深度玩右线',cat='交通条件',note='使用前一独立段落的条件标题，修复原窗口硬段边界漏抽。'),
      dict(group='D',rid='jiuzhaigou_user_generated_0ed001d738cb93a5:640',condition='如果是分配到右线开始',recommendation='早上就在原始森林慢悠悠的逛，然后10:00大概阳光出来了就开始从原始森林徒步到天鹅海',cat='交通条件',note='同一条件对应第二项时间路线安排，保留原时间与大概限定。'),
      dict(group='D',rid='gugong_official_df6c311301c59157:3346',condition='摄影爱好者',recommendation='去西北角楼拍摄',cat='游览偏好',rv='建议去西北角楼',note='摄影爱好者是兴趣偏好而非生理人群；同行摄影标题与推荐动作支持。'),
      dict(group='D',rid='gugong_user_generated_c57f5e2b6ca3c3a0:284',condition='第一次来',recommendation='留足1天游览，不选1-2小时快速路线',cat='游客类型',rv='一定留1天',quotes=['不推荐1-2小时的快速路线'],note='前句初访条件与后续快速路线否定一起补全，保持与R00009不同动作。'),
      dict(group='D',rid='jiuzhaigou_official_88ef5cc31789dc71:1287',condition='第一天的游览时间很宽松',recommendation='走进景区外的藏家乐',cat='时间约束',rv='推荐您走进景区外的藏家乐',note='因此连接时间充裕与额外活动，不补充原文未给出的条件。'),
    ]
    deleted={'R00027':'路线背景不是付费参观的适用前提，采纳删除。',
             'R00031':'景色评价与作者行程步骤不作为游客情境条件，采纳删除。',
             'R00032':'不采纳补写希望的建议：作者速通经验与目的不足以支撑独立偏好条件，与R00031采用一致的保守边界，删除。'}
    corrected={s['rid']:s for s in specs if s['group']=='A'}
    actions=[]
    rows=[]
    for r in base:
        if r['pair_id'] in deleted: continue
        r=copy.deepcopy(r)
        r['sources']=[copy.deepcopy(checked[p['pair_id']]) for p in r['sources']]
        r['original_sources']=copy.deepcopy(r['sources'])
        r['condition_verbatim']=r['condition']; r['recommendation_verbatim']=r['recommendation']
        r['review_status']='独立LLM辅助审核及证据复核；待真实人工确认'
        r['audit_refs']=[{'group':'A','record_id':r['pair_id']}]
        r['resolution_note']='核对原文后保留原预测。'
        if r['pair_id'] not in corrected: rows.append(r)

    def make(s,num):
        source=(A if s['group']=='A' else B if s['group']=='B' else D)[s['rid']]
        text=docs[source['doc_id']]['clean_text']
        c=s['condition']; r=s['recommendation']; cv=s.get('cv',c); rv=s.get('rv',r)
        def find(q):
            matches=list(re.finditer(re.escape(q),text))
            assert matches, (s['group'],s['rid'],q)
            # 同词多次出现时优先当前审核窗口附近，避免慎选/适合对应到另一条路线。
            return min((m.start() for m in matches),key=lambda i:abs(i-source['source_start']))
        ci,ri=find(cv),find(rv)
        spans=[{'role':'condition','text':cv,'start':ci,'end':ci+len(cv)},
               {'role':'recommendation','text':rv,'start':ri,'end':ri+len(rv)}]
        for q in s.get('quotes',[]):
            i=find(q); spans.append({'role':'context','text':q,'start':i,'end':i+len(q)})
        start=min(x['start'] for x in spans); end=max(x['end'] for x in spans)
        # 覆盖全部直接证据与路线标题；原始窗口另存，支持跨段修复而不覆写原抽取证据。
        lo=text.rfind('\n',0,start)+1
        hi=text.find('\n',end); hi=len(text) if hi<0 else hi
        evidence=text[start:end]; fragment=text[lo:hi]
        pid=s['rid'] if s['group']=='A' else f'F{num:05d}'
        evidence_source=dict(pair_id=pid,doc_id=source['doc_id'],id=source['window_id'],
          source_type=source['source_type'],url=source.get('source_url'),source_text=fragment,
          condition_verbatim=cv,recommendation_verbatim=rv,evidence_span=evidence,
          offsets={'condition':ci,'recommendation':ri,'evidence_span':start},grounding_spans=spans)
        original=index[s['rid']] if s['group']=='A' else source
        result=dict(pair_id=pid,doc_id=source['doc_id'],scenic_area=source['scenic_area'],source_type=source['source_type'],
          url=source.get('source_url'),id=source['window_id'],start=lo,end=hi,source_text=fragment,
          condition_type=s['cat'],condition=c,recommendation=r,condition_verbatim=cv,recommendation_verbatim=rv,
          evidence_span=evidence,offsets=evidence_source['offsets'],sources=[evidence_source],grounding_spans=spans,
          original_sources=original.get('sources',[{'window_id':source['window_id'],'source_text':source['source_text']}]),
          extraction_method='原自动抽取/漏抽样本 + 独立LLM辅助审核 + 原文证据复核',prompt_version='v2+audit_patch_v1',
          review_status='独立LLM辅助审核及证据复核；待真实人工确认',
          audit_refs=[{'group':s['group'],'record_id':s['rid']}],resolution_note=s.get('note','按原文修正边界。'),
          canonicalization_note='condition/recommendation为可读语义表述；*_verbatim与grounding_spans为逐字原文，保留否定与限制。')
        return result
    for i,s in enumerate(specs,1): rows.append(make(s,i))
    # 首先保留原32条表的ID与顺序，新增关系用F前缀，避免覆盖历史R号。
    ordering={r['pair_id']:i for i,r in enumerate(base)}
    rows.sort(key=lambda r:(0,ordering[r['pair_id']]) if r['pair_id'] in ordering else (1,r['pair_id']))
    dump(OUT/'reviewed_pairs_before_dedup.json',rows)
    groups={}; merge_ops=[]
    for r in rows:
        k=(r['scenic_area'],norm(r['condition']),norm(r['recommendation']))
        r.update(normalized_condition=k[1],normalized_recommendation=k[2])
        if k in groups:
            keep=groups[k]
            keep['sources']+=r['sources']; keep['audit_refs']+=r['audit_refs']; keep['original_sources']+=r['original_sources']
            merge_ops.append({'kept':keep['pair_id'],'merged':r['pair_id'],'reason':'审核后同景区条件与建议双键相等；合并保留全部证据','audit_refs':r['audit_refs']})
        else: groups[k]=r
    final=list(groups.values())
    final_by_ref=defaultdict_list(final)
    # 每个审核项均有落实记录，包括不新增、不恢复与不同意的结论，不以计数摘要替代逐项处理。
    for item in audit['items']:
        g,rid=item['group'],item['record_id']; linked=final_by_ref.get((g,rid),[])
        if g=='A':
            action='delete' if rid in deleted else 'modify' if rid in corrected else 'retain'
            reason=deleted.get(rid,corrected.get(rid,{}).get('note','核对原文，保留有效关系。'))
        elif g=='B':
            action='restore_and_merge' if rid in ('B-RAW-0047','B-RAW-0048') else 'restore' if linked else 'keep_quarantined'
            reason=next((s.get('note','有原文依据，恢复并补全。') for s in specs if s['group']==g and s['rid']==rid),item['reason'])
        elif g=='D':
            action='add' if linked else 'defer_uncertain' if item['decision']=='不确定' else 'no_addition'
            reason='核对上下文后补抽，未调用原模型。' if linked else '仅有方案效果评价、未明确独立条件；不凭常识新增。' if item['decision']=='不确定' else item['reason']
        elif g=='E': action='retain_historical_merge'; reason='原合并成员条件建议一致；与关系本身是否正确分开判定，全部历史来源保留。'
        else: action='no_addition'; reason=item['reason']
        actions.append({'group':g,'record_id':rid,'independent_decision':item['decision'],'error_types':item['error_types'],
          'action':action,'resolution_reason':reason,'final_pair_ids':linked,'independent_proposed_pairs':item['proposed_pairs'],
          'human_gold':False,'original_audit_ref':'audit_resolution/task5_independent_audit.json'})
    dump(AUD/'resolution_log.json',actions)
    dump(AUD/'applied_patch_specs.json',specs)
    dump(OUT/'final_mapping.json',final)
    dump(OUT/'review_dedup_log.json',merge_ops)
    from difflib import SequenceMatcher
    near=[]
    for i,a in enumerate(final):
        for b in final[i+1:]:
            if a['scenic_area']==b['scenic_area'] and a['normalized_condition']==b['normalized_condition']:
                x,y=a['normalized_recommendation'],b['normalized_recommendation']
                if x in y or y in x or SequenceMatcher(None,x,y).ratio()>=.75:
                    near.append({'left':a['pair_id'],'right':b['pair_id'],'decision':'保留不同动作，待真实人工核验'})
    dump(OUT/'review_near_duplicates.json',near)
    summary=load(SNAP/'results/summary.json')
    old_count=summary['final_pairs']
    category=Counter(r['condition_type'] for r in final)
    stats={'before_pairs':old_count,'after_pairs':len(final),'modified_baseline_pairs':len(corrected),'deleted_baseline_pairs':len(deleted),
           'restored_candidates':sum(s['group']=='B' for s in specs),'restored_net_new_pairs':sum(r['pair_id'].startswith('F') and any(x['group']=='B' for x in r['audit_refs']) for r in final),
           'added_from_D':sum(r['pair_id'].startswith('F') and any(x['group']=='D' for x in r['audit_refs']) for r in final),
           'reviewed_before_dedup':len(rows),'review_merge_operations':len(merge_ops),'audit_items_resolved':len(actions),
           'uncertain_not_added':sum(x['action']=='defer_uncertain' for x in actions),'audit_type':audit['review_type'],
           'new_network_calls':0,'categories_before':summary['categories'],'categories_after':{c:category[c] for c in CATS}}
    assert old_count-stats['deleted_baseline_pairs']+stats['restored_net_new_pairs']+stats['added_from_D']==len(final)
    summary.update(final_pairs=len(final),categories=stats['categories_after'],stage='independent_audit_finalized',
                   automatic_final_pairs=old_count,reviewed_pairs_before_dedup=len(rows),review_merge_operations=len(merge_ops),audit_resolution=stats)
    dump(OUT/'summary.json',summary)
    dump(AUD/'revision_summary.json',stats)
    review=[dict(sample_type='final_prediction',pair_id=r['pair_id'],doc_id=r['doc_id'],condition=r['condition'],recommendation=r['recommendation'],
         condition_type=r['condition_type'],source_text=r['source_text'],review_status=r['review_status'],
         human_label='',human_condition='',human_recommendation='',reviewer='',error_type='') for r in final]
    dump(OUT/'human_review.json',review)
    # 自动质量门检查逐字锚点，而不是强迫语义规范化后的主字段也必须原文连续出现。
    for r in final:
        assert r['condition_type'] in CATS
        for p in r['sources']:
            text=docs[p['doc_id']]['clean_text']
            for f in ('condition','recommendation'):
                literal=p.get(f+'_verbatim',p.get(f,r[f])); start=p['offsets'][f]
                assert text[start:start+len(literal)]==literal,(r['pair_id'],f)
            assert p['source_text'] in text and p['evidence_span'] in text
            assert p.get('condition_verbatim',p.get('condition',r['condition'])) in p['evidence_span']
            assert p.get('recommendation_verbatim',p.get('recommendation',r['recommendation'])) in p['evidence_span']
            for span in p.get('grounding_spans',[]): assert text[span['start']:span['end']]==span['text']
    assert len({r['pair_id'] for r in final})==len(final)
    assert len({(r['scenic_area'],r['normalized_condition'],r['normalized_recommendation']) for r in final})==len(final)
    assert hashes(SNAP)==frozen_before and hashes(ROOT/'review_package')==package_before
    # 未经改写的历史文件仍置于results，保存并验证它们与快照逐字一致。
    historical=['raw_pairs.json','validated_pairs.json','rejected_pairs.json','dedup_log.json','run_log.json','candidates.json','negative_audit.json']
    assert all(digest(OUT/n)==digest(SNAP/'results'/n) for n in historical)
    dump(AUD/'provenance_checks.json',{'source_evidence_aligned':True,'all_108_items_resolved':True,'no_exact_duplicate':True,
         'snapshot_unchanged':True,'review_package_unchanged':True,'historical_outputs_unchanged':True,
         'snapshot_manifest':hashes(SNAP),'review_package_manifest':package_before,'human_gold':False})
    print(json.dumps(stats,ensure_ascii=True))

def defaultdict_list(rows):
    result={}
    for r in rows:
        for ref in r['audit_refs']: result.setdefault((ref['group'],ref['record_id']),[]).append(r['pair_id'])
    return result

if __name__=='__main__': main()
