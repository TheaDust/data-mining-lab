"""真实结果统计、报告生成与交付验收。"""
from pathlib import Path
import sys,json,csv,zipfile,os
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.audit_deps'))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.tmp/matplotlib'))
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

OUT=ROOT/'results'
def load(n): return json.loads((OUT/n).read_text(encoding='utf8'))
def main():
    s=load('summary.json'); rows=load('final_mapping.json'); df=pd.DataFrame(rows)
    stats=pd.Series(s['categories'],name='关系数量').rename_axis('条件类型')
    stats.to_csv(OUT/'category_counts.csv',encoding='utf-8-sig')
    cross=pd.crosstab(df.scenic_area,df.condition_type).reindex(columns=s['categories'],fill_value=0)
    cross.to_csv(OUT/'scenic_category_counts.csv',encoding='utf-8-sig')
    # 合并关系可能同时来自官方与游记；按“关系×来源类型”计数，不声称可与关系总数相加。
    source=pd.DataFrame([{'source_type':t,'condition_type':r['condition_type']} for r in rows for t in sorted({p['source_type'] for p in r['sources']})])
    pd.crosstab(source.source_type,source.condition_type).to_csv(OUT/'source_category_counts.csv',encoding='utf-8-sig')
    pd.DataFrame(load('human_review.json')).to_csv(OUT/'human_review.csv',index=False,encoding='utf-8-sig')
    font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
    plt.rcParams['font.family']=font.get_name(); plt.rcParams['axes.unicode_minus']=False
    fig,ax=plt.subplots(figsize=(11,5)); bars=ax.bar(stats.index,stats.values,color='#3976A8')
    ax.bar_label(bars); ax.set_ylabel('去重后条件—建议关系数'); ax.set_title('图5-1 条件类型分布（含零样本类别）'); ax.set_ylim(0,max(stats.values)+3)
    fig.tight_layout(); fig.savefig(OUT/'condition_types.png',dpi=160); plt.close(fig)
    ax=cross.T.plot.bar(figsize=(12,6)); ax.set_ylabel('关系数量'); ax.set_title('图5-2 各景区条件类型对比'); ax.tick_params(axis='x',rotation=0)
    plt.tight_layout(); plt.savefig(OUT/'scenic_comparison.png',dpi=160); plt.close()
    base=json.loads((ROOT/'baseline/summary.json').read_text(encoding='utf8'))
    examples='\n'.join(f"- `{r['pair_id']}`（{r['doc_id']}）：{r['condition']} → {r['recommendation']}。" for r in rows[:6])
    rejected=load('rejected_pairs.json')
    errors='\n'.join(f"- {r.get('condition','')} → {r.get('recommendation','')}：`{r['reason']}`（自动隔离，非人工判定）。" for r in rejected[:12])
    content=f'''# 实验项目5：条件性游览建议的抽取

## 5.1 输入与抽取规则设计
输入为 task1/data/final/documents.jsonl 的 clean_text，共{s['documents']}篇、3个景区，各1篇官方及5篇游客文本。source_type 沿用上游分类，不重新验证网站身份。输入SHA256见 results/input_manifest.json。
按换行硬分段、相邻两句重叠窗口，共{s['windows']}个窗口。字符偏移采用 Python Unicode 下标，左闭右开。优先级：显式条件 > 隐式情境 > 普通建议。候选{s['candidates']}个；建议/可以仅用于召回，不能单独证明有条件。规则全文见 run.py 的 EXPLICIT/IMPLICIT/ADVICE。
模型 deepseek-flash，温度0，thinking disabled，JSON模式，max_tokens 6000；每批6片段、并发4、最多重试3次。完整核心Prompt见 prompt.txt（v2），初版见 prompt_v1.txt。采用条件、建议、证据逐字子串约束，保留组合条件、一对多及段内跨句关系。温度0仍不保证远端模型完全确定，缓存才提供本次结果的精确重放。

## 5.2 批量抽取与复杂表达处理
本轮产生{s['raw_pairs']}条原始模型关系，程序校验后{s['validated_pairs']}条。批次日志见 results/run_log.json；失败{s['calls'].get('failed',0)}批。缓存命中数反映最近重放，首次联网信息可在缓存 usage 与 attempts 查看。
一个条件有不同建议时保留多行，例如“体力一般”对应坐观光车与分2天慢慢玩。多分句建议可能保留一个连续动作组，未无依据拆成不完整宾语。跨句仅在同段相邻两句支持，超过该范围可能漏抽。
真实样例：
{examples}

## 5.3 映射表、分类与去重
一行对应一个独立关系；pair_id 为本次校验结果序号（跨版本不稳定），doc_id 与字符位置用于稳定溯源。字段包含condition_type、condition、recommendation、scenic_area、source_type、source_text、evidence_span、offsets、url、prompt_version、review_status与sources。sources保留所有合并前原始关系、文档、原文和位置。
分类为游客类型、天气环境、时间约束、体力与健康、交通条件、游览偏好、其他条件。由模型按适用情境标记，仍需独立核验。
按同景区、条件和建议同时规范化相等合并，规范化仅删除标点与无语义引导前缀，不删否定、数字。{s['validated_pairs']} → {s['final_pairs']}条，合并{s['merged']}条，实际案例见 results/dedup_log.json。条件相同且建议有包含/高字符相似度者仅列为 near_duplicate_review.json 待判定，不自动吞并语义不同或范围不同的建议。不是全面语义去重。

## 5.4 人工校验与误差分析
初版结果保存在 baseline，初版候选{base['candidates']}、原始关系{base['raw_pairs']}、去重{base['final_pairs']}。实查发现修辞效果误作行动、对象残缺、时间边界反向和纯先后关系。v2加入反例约束，候选增加人多/拥挤/排队召回。第二轮仍有模型不遵守要求的结果，因此增加小范围可解释隔离规则，保留 rejected_pairs.json，不修改模型原始输出。优化数量变化不代表精度提升的量化证据。
自动隔离{s['rejected_pairs']}条，典型案例：
{errors}
对规则未命中窗口每文档均匀取至多2个，本轮共{s['negative_audit_windows']}个，经同模型辅助检查发现{s['audit_discoveries']}条通过校验关系。初轮规则外曾发现“中轴线人最多→拍照可去两侧宫殿”，据此扩展规则。抽查量很小且同模型存在共同盲点，零发现不等于无漏抽。
results/human_review.csv、Excel人工审核页包含分层预测样本及无预测片段，供填写 FP/FN/Boundary/Association/Classification、修正条件与建议、审核人。全部待人工确认，没有真实人工标注，不报告人工Precision/Recall/F1。自动检查只能证明证据字符串可对齐，无法证明语义或分类正确。个别泛化条件、路线编号指向不明、来源措辞错误仍可能保留，须结合原文确认。

## 5.5 分类统计与可视化
统计单位是同景区条件与建议规范化去重后的关系，共{s['final_pairs']}条。类别数量为：{json.dumps(s['categories'],ensure_ascii=False)}。时间约束关系最多，说明本语料更常讨论时段与游程安排，不能推广为旅游总体规律。其他条件零样本仍显示，不补造关系。
![图5-1 条件类型分布](results/condition_types.png)
![图5-2 景区对比](results/scenic_comparison.png)
基础数据见 category_counts.csv、scenic_category_counts.csv。来源对比以关系×来源类型计数，多来源关系可重复参与，故不可将其总和当作去重关系数。不同景区文档长度和写作风格不同，绝对计数不等于发生率。
'''
    if s.get('stage')=='independent_audit_finalized':
        from final_report import render
        content=render(ROOT,s,rows)
    (ROOT/'REPORT.md').write_text(content,encoding='utf8')
    # 验收从持久化文件重新读取，避免仅验证内存中尚未落盘的数据。
    assert sum(s['categories'].values())==len(rows)==s['final_pairs']
    docs={json.loads(l)['doc_id']:json.loads(l)['clean_text'] for l in (ROOT.parent/'task1/data/final/documents.jsonl').read_text(encoding='utf8').splitlines()}
    for r in rows:
        for p in r['sources']:
            for f in ('condition','recommendation'):
                literal=p.get(f+'_verbatim',p.get(f,r[f]))
                start=p['offsets'][f]; assert docs[p['doc_id']][start:start+len(literal)]==literal
            assert p['evidence_span'] in docs[p['doc_id']]
    import openpyxl
    book=openpyxl.load_workbook(OUT/'final_mapping.xlsx',read_only=True)
    # 部分导出器省略 worksheet dimension，read_only.max_row 为 None；实际读取行验证。
    actual=list(book['条件建议映射'].values)
    assert len(actual)==len(rows)+1
    assert [r[0] for r in actual[1:]]==[r['pair_id'] for r in rows]
    # 不只检查行数：逐单元格核对主表文本及嵌套来源，防止旧Excel或导出错列通过验收。
    for values,r in zip(actual[1:],rows):
        for name,value in zip(actual[0],values):
            target=r.get(name)
            if isinstance(target,(list,dict)): assert json.loads(value)==target,(r['pair_id'],name)
            else: assert value==target or value is None and target=='',(r['pair_id'],name)
    for p in OUT.glob('*.json'): json.loads(p.read_text(encoding='utf8'))
    from PIL import Image
    for n in ('condition_types.png','scenic_comparison.png'): Image.open(OUT/n).verify()
    (OUT/'acceptance.json').write_text(json.dumps(dict(json_valid=True,excel_rows=len(rows),excel_cells_equal=True,stats_equal=True,evidence_offsets_valid=True,png_valid=True,human_review='pending',review_type='independent_llm_assisted',human_gold=False),indent=2),encoding='utf8')
    print('验收通过',len(rows))

if __name__=='__main__': main()
