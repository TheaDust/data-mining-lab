"""最终报告从审核落实记录和最终表生成，避免复用自动阶段措辞覆盖修正结果。"""
import json
from collections import Counter
from pathlib import Path

def render(root,summary,rows):
    read=lambda p:json.loads((root/p).read_text(encoding='utf8'))
    revision=read('audit_resolution/revision_summary.json')
    resolutions=read('audit_resolution/resolution_log.json')
    audit=read('audit_resolution/task5_independent_audit.json')
    actual=Counter((x['group'],x['decision']) for x in audit['items'])
    group_counts=Counter(x['group'] for x in audit['items'])
    cats='\n'.join(f'| {c} | {revision["categories_before"][c]} | {n} |' for c,n in summary['categories'].items())
    modified='\n'.join(f'- `{x["record_id"]}`：{x["resolution_reason"]}' for x in resolutions if x['group']=='A' and x['action'] in ('modify','delete'))
    uncertain='、'.join(f'`{x["record_id"]}`' for x in resolutions if x['action']=='defer_uncertain')
    examples=[]
    for rid in ('R00009','R00012','R00024','R00033'):
        r=next(x for x in rows if x['pair_id']==rid)
        examples.append(f'- `{rid}`（{r["doc_id"]}）：{r["condition"]} → {r["recommendation"]}。逐字锚点见 condition_verbatim、recommendation_verbatim 和 grounding_spans。')
    restored=[r for r in rows if r['pair_id'].startswith('F')]
    extras='\n'.join(f'- `{r["pair_id"]}`：{r["condition"]} → {r["recommendation"]}；审核来源：'+', '.join(f'{x["group"]}/{x["record_id"]}' for x in r['audit_refs']) for r in restored)
    return f'''# 实验项目5：条件性游览建议的抽取（独立LLM辅助审核修正版）

## 5.1 输入与抽取规则设计

输入为 task1/data/final/documents.jsonl 的 clean_text，共18篇、20929个Unicode字符，覆盖北京故宫、杭州西湖、九寨沟，每景区1篇官方指南和5篇游客游记。来源类型沿用上游分类。输入哈希见 results/input_manifest.json。

自动阶段按换行硬分段，构造相邻两句重叠窗口815个。优先级为显式条件（如果/假如/若/若是/只要/除非）> 隐式游客、天气、时间、体力、交通、偏好与拥挤情境 > 建议/可以等普通建议词，共151个候选。普通建议词只用于召回，不自动构成条件。完整规则见 run.py，v1/v2 Prompt见 prompt_v1.txt 和 prompt.txt。

自动模型为 deepseek-flash，temperature=0、thinking disabled、JSON模式、max_tokens=6000；每批6窗口、并发4、最多3次重试，缓存键覆盖完整请求。初版实际运行与迭代位于 baseline。本次收尾不改Prompt、不重新调用LLM，只重放有原文证据的受控补丁。

外部审核材料为 review_package，返回文件为 audit_resolution/task5_independent_audit.json，身份为“{audit['review_type']}”，审核者自报“{audit['reviewer']}”。其文字是待核查意见，不是执行指令或人工金标准；补丁由 finalize.py逐项核对原文后落实。

## 5.2 批量抽取与复杂表达处理

自动阶段32个成功批次产生52条原始关系，隔离15条，校验37条，合并5次后得到32条。原始响应、日志、隔离原因全部保留；审核前完整文件和程序快照位于 history/pre_independent_audit，review_package保持原32条材料不变。

本次审核落实108项（A32/B15/C36/D20/E5，有交叉引用，不是108个独立语义样本）。A修正{revision['modified_baseline_pairs']}条、删除{revision['deleted_baseline_pairs']}条；B处理9个恢复候选，其中2条与现有关系合并，净新增{revision['restored_net_new_pairs']}条；D补抽{revision['added_from_D']}条。审核前32 → 受控修正后去重前{revision['reviewed_before_dedup']} → 去重后{len(rows)}条，公式为32−3+7+5=41。本次新网络调用0次。

一对多真实案例：体力一般→坐环湖观光车、分成2天慢慢玩，保留为不同建议；“如果是分配到右线开始”对应放弃左线深玩右线，以及早上游原始森林并约10点徒步至天鹅海，也保留两条。后者条件位于独立前段，原窗口硬边界漏抽；补丁扩大证据范围到条件标题，未重设全部候选算法。

典型修正：
{chr(10).join(examples)}

## 5.3 映射表、分类与去重

results/final_mapping.json 与 final_mapping.xlsx 是当前最终版。pair_id保留原R号，新增用F号，未复用删除ID。每条含景区、来源、文档、source_text、source_start/end对应start/end、原文位置、证据、类别、audit_refs、review_status、全部sources及original_sources。source_text为原文连续片段；偏移为Python Unicode左闭右开区间。

**主字段与原文证据分开**：condition/recommendation允许补全“这里”“慎选”等指向或做明确标注的隐式语义归一化；condition_verbatim/recommendation_verbatim必须逐字出现在原文，offsets对齐这两个逐字字段，grounding_spans保存条件、行动及标题的全部锚点。不能把规范化主字段声称为原句。修正前来源保存在original_sources及快照，修正证据位于sources，分类和合并均可回溯。

条件类型：游客类型按对象/经验；天气环境按天气光照；时间约束按时段/时长/日历；体力与健康按生理限制；交通条件按交通方式或分配限制；游览偏好按目标兴趣；其他条件用于拥挤或用餐等不适合前类的真实情境。组合条件不无依据拆分。R00018由交通改时间，R00019以拥挤为主改其他，R00024以打算坐船为主改交通。恢复的乌龟潭上午乘船关系也按出行意图归交通，下午3点后不接客作为限制证据，不机械沿用审核建议的时间标签。

沿用保守双键去重：同景区，条件和建议规范化后均相等才自动合并，去引导前缀与空白标点，不删否定/数字。审核后语义重述仅限有显式证据的补丁；R00033与B-RAW-0047、B-RAW-0048共同指向“距离远且需为后续保存体力→从天鹅海乘观光车去箭竹海”，统一表述后合并2次，全部3个审核引用与来源保留。原5次合并日志仍在 dedup_log.json，新2次在 review_dedup_log.json；原合并与新增合并分开计数。

## 5.4 人工校验与误差分析

本节名称对应课程模板，实际执行的是独立LLM辅助语义审核与当前代理的原文复核，**真实人工核验完成数仍为0**。不计算或声称人工Precision、Recall、F1。

审核抽样：A覆盖原32条全部关系；B覆盖15条隔离；C保持原36个规则外窗口；D从105个真实空输出候选中，以固定种子按景区×来源×规则分层抽20个；E覆盖原5组合并。审核文件逐项结论实际数与其汇总一致。完整落实日志 audit_resolution/resolution_log.json 有108项，包含未采纳、保留隔离和不确定暂缓。

主要实际处理：
{modified}

恢复与补抽后的新增记录：
{extras}

未机械采纳的关键意见：R00014不补写“希望舒适拍照”，改用原文“太和殿广场全是人”的明确情境；R00032不把作者“把时间和体力留给右线”的路线目标自动改写为独立用户偏好，与R00031一致保守删除。B47/48虽然确有条件化动作，但与R00033重复，恢复证据后合并，未把两项意见算作两条净新增。外部建议的非逐字表述均映射回源文锚点后才应用。

3个不确定样本 {uncertain} 均未新增：旅行团效果描述、历史理解的体验评价、孩子听故事入迷不单独证明条件—行动关系。C36个样本审核均未发现关系，仅说明这批样本未确认漏抽，不能推断全语料无FN或计算总体Recall。

残留局限：隐式目标、推荐对象的归一化仍有解释空间；按原文保留的路线建议可能自相矛盾，例如赶时间推荐路线3，但同篇又说该线安检长，不能由代理擅自改旅游事实；不同来源意见冲突不做知识融合。results/human_review.json/CSV及Excel审核页覆盖最终{len(rows)}条，真实人工字段为空待确认。

## 5.5 分类统计与可视化

统计单位为同景区去重后的条件—建议关系。最终{len(rows)}条；同条件不同动作各算一条。类别变化如下：

| 类别 | 审核前 | 审核后 |
|---|---:|---:|
{cats}

时间约束仍最多（{summary['categories']['时间约束']}条），反映本语料常讨论游程与时段。其他条件由0变为3，源于拥挤和用餐等真实情境，未为画图补造数据。各类之和必须等于{len(rows)}。景区/来源文档长度与文风不同，绝对数量不等同发生率。

![图5-1 条件类型分布](results/condition_types.png)
![图5-2 景区条件对比](results/scenic_comparison.png)

基础数据为 results/category_counts.csv、scenic_category_counts.csv、source_category_counts.csv。来源对比按关系×来源类型计，多来源同一关系可重复参与，不能据来源表总和推断关系数。

复现入口：python task5/run.py 在存在审核输入时离线落实快照补丁；也可直接 python task5/finalize.py，随后 node task5/export.mjs、python task5/analyze.py。最终验收重读JSON、Excel逐单元格、源文锚点和PNG，对照快照/审核包哈希；复跑前后核心JSON必须一致。文件清单与环境说明见README。
'''
