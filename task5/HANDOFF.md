# 实验项目5成果交接：条件性游览建议

## 1. 下游默认版本

**实验6、7默认读取 `task5/results/final_mapping.json`，当前为独立LLM辅助审核修正后的41条关系。** 不需要重新运行抽取模型，也不需要API Key。Excel用于浏览与人工确认，程序接入以JSON为准。

版本标识：`results/summary.json` 的 `stage` 为 `independent_audit_finalized`。当前不存在单独的v3目录；沿用的R号和新增F号共同组成最终版本，不能只读其中一种前缀。

原自动阶段32条、最早v1结果、待审核包中的32条都不是当前下游输入。审核后的规范化主字段可能包含有证据的指代补全，不能将它们一律当作原文切片。

本交接文档中的路径均相对仓库根目录，便于其他机器接入。

## 2. 实际规模与质量状态

输入来自实验1的18篇清洗文档，北京故宫、杭州西湖、九寨沟各1篇官方指南及5篇游客游记。自动阶段151个候选窗口，另抽查36个规则外窗口，产生52条原始关系、37条程序校验关系，原去重后32条。

独立审核返回108项意见（A32/B15/C36/D20/E5，有交叉引用）。核对原文后修正9条、删除3条，隔离恢复净新增7条、漏抽补入5条；另2条恢复记录合入既有关系。最终32−3+7+5=41条。本轮收尾没有新增模型调用。

| 条件类型 | 最终关系数 |
|---|---:|
| 游客类型 | 7 |
| 天气环境 | 3 |
| 时间约束 | 13 |
| 体力与健康 | 6 |
| 交通条件 | 5 |
| 游览偏好 | 4 |
| 其他条件 | 3 |
| 合计 | 41 |

按文档所属景区：北京故宫18、杭州西湖12、九寨沟11。按主记录来源：official 8、user_generated 33。后者是主记录口径；若统计合并来源，应遍历sources并明确计数单位，不能把来源出现次数当作独立关系数。

**审核是独立LLM辅助语义审核及代理原文复核，真实人工确认仍未完成。** 当前review_status保留待真实人工确认状态。没有人工金标准，不提供经过人工确认的Precision、Recall、F1或逐条置信概率。

## 3. 核心文件索引

| 路径 | 下游用途 | 优先级 |
|---|---|---|
| `task5/results/final_mapping.json` | 当前41条条件关系，含原文锚点和合并来源 | 必需 |
| `task5/results/summary.json` | 版本阶段、类别计数及修改摘要 | 建议同时读取 |
| `task1/data/final/documents.jsonl` | 按doc_id恢复clean_text全文、标题等元信息 | 核验证据、解析路线指代时必需 |
| `task5/results/final_mapping.xlsx` | 最终映射表及待真实人工确认页 | 人工查看按需 |
| `task5/results/input_manifest.json` | 原输入版本及来源信息 | 输入版本检查按需 |
| `task5/audit_resolution/task5_independent_audit.json` | 独立LLM审核原件 | 审计按需 |
| `task5/audit_resolution/resolution_log.json` | 108项意见如何落实、哪些未采纳及最终ID | 解释修正时使用 |
| `task5/audit_resolution/revision_summary.json` | 审核前后数量、分类变化 | 报告或审计按需 |
| `task5/results/review_dedup_log.json` | 本次额外2次合并；原5次在dedup_log.json | 合并审计按需 |
| `task5/results/final_acceptance.json` | JSON、Excel、统计、证据及离线复跑验收记录 | 接入前参考 |
| `task5/results/human_review.json`、`human_review.csv` | 最终41条的真实人工确认模板 | 后续人工评估按需 |
| `task5/REPORT.md` | 方法、结果、修正案例与局限 | 实验报告参考 |
| `task5/history/pre_independent_audit/` | 审核前32条及完整快照 | 最终版离线重放需要；不是图谱输入 |
| `task5/review_package/` | 外部审核实际使用的冻结材料 | 离线修正程序需要；其中A仍为旧32条 |
| `task5/baseline/` | 更早的v1实验与迭代对照 | 对照分析使用，不混入最终表 |

`raw_pairs.json`、`validated_pairs.json`、`rejected_pairs.json`、历史缓存和旧映射表是过程证据，不能与最终41条拼接后直接建图，否则会重新引入已删除或重复的关系。

## 4. JSON字段契约

顶层为数组，一行表示一个独立条件—建议关系。重要字段如下。

| 字段 | 含义与下游约定 |
|---|---|
| `pair_id` | 当前最终版本的关系ID，保留R号、新增F号；有缺号是正常情况，不重排 |
| `scenic_area` | 文档所属景区；实验2的对应字段名是scenic_spot，需要显式映射 |
| `doc_id` | 实验1文档主键；跨实验关联原文优先使用它 |
| `condition_type` | 条件语义主类别，属于上表7类之一；不是可直接执行的约束表达式 |
| `condition` | 面向使用的条件表述，可有已说明的隐式条件归一化 |
| `recommendation` | 面向使用的行动、选择或避免行为，保留否定和范围 |
| `condition_verbatim`、`recommendation_verbatim` | 当前主记录逐字原文锚点；可与主字段不同 |
| `source_text` | 原文连续片段；旧记录多为相邻两句窗口，修正记录可能扩大至跨段证据，长度不统一 |
| `start`、`end` | source_text在clean_text中的左闭右开范围，不能当作条件或建议的范围 |
| `evidence_span` | 直接证据连续片段；本身也属于原文 |
| `offsets` | condition、recommendation、evidence_span的全文起点；前两个对齐逐字锚点，不保证对齐规范化主字段 |
| `grounding_spans` | 可选的细粒度锚点列表，含role、text、start、end；修正记录提供，旧保留记录可能没有 |
| `sources` | 当前关系的全部活动证据来源，包括合并来源；溯源时优先遍历它 |
| `original_sources` | 修正前的原始来源/预测信息，供审计；不要把旧预测再当作新关系导入 |
| `source_type`、`url` | 主来源类型与地址，official/user_generated沿用上游标签，不代表已核定当前权威性 |
| `audit_refs` | 独立审核组别和原审核ID，可关联resolution_log.json |
| `extraction_method`、`prompt_version` | 自动或审核修正过程元信息；不同保留记录可能不同，不据此筛掉有效记录 |
| `review_status` | 当前为LLM辅助审核及证据复核、待真实人工确认；不是已人工通过 |
| `normalized_condition`、`normalized_recommendation` | 保守字符串去重键，不是完整的语义等价判定，也不是实体ID |
| `resolution_note`、`canonicalization_note` | 修正理由和主字段归一化说明；后者可选 |

**sources成员存在两种真实结构，消费者必须兼容：**

- 旧保留记录的source通常有condition/recommendation及offsets。
- 审核补丁生成的source通常有condition_verbatim/recommendation_verbatim及offsets。

因此来源锚点应按“verbatim优先、source自身原字段其次、主记录字段最后”读取，不能强制所有source都具有相同键集合。source内也不一定有start/end，可用offsets和逐字锚点长度定位。

原窗口`id`通常为`doc_id:窗口起点`，与pair_id不是同一种ID。修改或合并后，该窗口ID仅指原候选，不保证定义当前扩展证据的范围。稳定引用建议使用“版本阶段 + pair_id”，并保留doc_id与来源偏移。

## 5. 真实记录与只读接入示例

以下为最终表R00009的真实字段子集：

```json
{
  "pair_id": "R00009",
  "doc_id": "gugong_user_generated_c57f5e2b6ca3c3a0",
  "scenic_area": "北京故宫",
  "condition_type": "游客类型",
  "condition": "初次来",
  "recommendation": "不建议为了省几步路中轴线和东西宫来回穿梭",
  "condition_verbatim": "初次来",
  "recommendation_verbatim": "不建议为了省几步路中轴线和东西宫来回穿梭",
  "review_status": "独立LLM辅助审核及证据复核；待真实人工确认"
}
```

从仓库根目录执行以下代码，只读取结果和原文，不调用模型、不写文件：

```python
import json
from collections import Counter
from pathlib import Path

root = Path.cwd()  # 在仓库根目录运行
result = root / "task5/results"
pairs = json.loads((result / "final_mapping.json").read_text(encoding="utf-8"))
summary = json.loads((result / "summary.json").read_text(encoding="utf-8"))
assert summary["stage"] == "independent_audit_finalized"
assert len(pairs) == summary["final_pairs"] == 41
assert dict(Counter(p["condition_type"] for p in pairs)) == summary["categories"]
assert len({p["pair_id"] for p in pairs}) == len(pairs)

documents = {}
for line in (root / "task1/data/final/documents.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        doc = json.loads(line)
        documents[doc["doc_id"]] = doc

source_count = 0
for pair in pairs:
    for source in pair["sources"]:
        text = documents[source["doc_id"]]["clean_text"]
        for field in ("condition", "recommendation"):
            literal = source.get(field + "_verbatim", source.get(field, pair[field]))
            start = source["offsets"][field]
            assert text[start:start + len(literal)] == literal, (pair["pair_id"], field)
        assert source["evidence_span"] in text
        for span in source.get("grounding_spans", []):
            assert text[span["start"]:span["end"]] == span["text"]
        source_count += 1

selected = [p for p in pairs if p["scenic_area"] == "九寨沟"]
assert len(selected) == 11
print(f"关系{len(pairs)}条，证据来源{source_count}条，九寨沟{len(selected)}条")
```

偏移是Python Unicode码点，从0开始、左闭右开。不能直接用于raw_text、UTF-8字节序列或JavaScript UTF-16索引；JavaScript侧如需按码点切片，可先`Array.from(cleanText)`。原文中的空白、换行、表情和错字均不能先清洗后再套旧偏移。

## 6. 实验6：融合与图谱接入建议

1. 将41条作为条件建议断言导入，而非无条件旅游事实。建议为每条保留独立的断言节点/边ID，用pair_id关联来源、审核状态和证据，避免共享建议节点后把其他条件的证据串错。
2. 一个条件有多个行动必须保留，例如体力一般对应“坐环湖观光车”和“分成2天慢慢玩”，不能只取第一条建议。
3. 景点名称与实验2实体、实验3路线的对齐，优先在相同doc_id及证据上下文内进行。仅因关系来自故宫文档，不能把它关联到该文档的全部POI。未建立可靠链接时，保留文本条件和建议，标记实体链接未完成。
4. 路线1/3/4/5、左线/右线等标识具有文档作用域。不同文档的“路线3”不能直接共用节点；可先以(doc_id, 局部路线标签)建ID，再依据原文路线标题或实验3输出对齐。这里只提供证据，并未完成下游实体链接。
5. 同景区、相同规范化条件和建议才属于当前字符串重复口径。跨文档近义或跨景区别名合并需另建融合日志，不能丢sources与audit_refs；不要求融合后关系数仍为41。
6. official是上游来源类别，不自动等于当前景区运营方公告；若下游设置来源优先级，需结合source_name、URL、文档日期与实际内容，而非只看标签。

## 7. 实验7：规划Agent接入建议

- 先按景区检索，再根据用户的实际条件、目标和限制判断关系适用性，返回行动及证据。condition_type只适合辅助筛选，不能用“同一类别”替代语义匹配。
- 不将全部41条无条件套用。组合条件保持完整；“带娃/赶时间”等备选表达不能一律解析成AND或无依据拆分。否定建议不能在生成回答时变成正向推荐。
- 没有条件匹配时明确无匹配，不虚构规则；用户未给年龄、体力、天气或时间时，不擅自假定已满足。含“如果还有力气”“不赶时间”的关系应保留这种限定。
- 建议输出pair_id、doc_id、source_type、证据片段与审核状态，必要时通过source的URL回溯。主字段中的“选择路线5”等补全，应与标题锚点一起提供。
- 本数据不是现行开放、票价、预约、限行政策的权威实时来源，不能把历史游记安排承诺为当前可执行事实。这里未做新一轮联网核验。
- 来源内可能自相矛盾，例如R00016所在原文一面建议赶时间想省腿选路线3，另一面描述该线安检耗时。保留其来源性质与限制，不把它升级为无条件最优路线；冲突处理属于实验6/7的融合与规划工作。
- 未提供结构化布尔谓词、约束求解器、数值置信度或检索工具接口。后续可实现这些功能，但不要声称task5已提供。

## 8. 已知边界

独立审核与证据对齐不保证所有语义正确；隐式条件、目的推断、指代补全仍有解释空间。3条不确定意见未据此新增；C组36个规则外窗口未确认漏抽不代表全语料无FN。抽样不能用于估计总体Recall。

原文错字可能保留在逐字锚点中，如R00012证据中的“经理”、R00030中的“拍逛逛”。主字段归一化与原文引用应分开展示，不要偷偷修改源文导致偏移失效。无真实人工金标准，Agent或图谱页面不得标记“人工认证准确”。

## 9. 复现、验收与文件维护

**消费现有结果只需要Python标准库；不必安装模型、运行抽取或执行Excel导出。**

如需重建当前最终成果，仓库根目录命令为：

```powershell
python -m pip install -r task5/requirements.txt
python task5/run.py
node task5/export.mjs
python task5/analyze.py
python task5/verify_final.py
```

存在审核输入时，run.py默认离线转入finalize.py，从冻结快照重放修正；不重新请求LLM。`--smoke`是旧自动阶段的联网测试，不属于下游消费或最终复现的必要步骤。Excel导出需要本机artifact-tool公开入口，可用ARTIFACT_TOOL_ENTRY配置；中文绘图默认使用Windows微软雅黑路径。README中有实际环境与限制。

最终验收已检查JSON、Excel逐单元格、分类统计、景区统计、原文偏移、PNG、历史原件及默认入口离线重放幂等性，记录在final_acceptance.json。它证明文件一致性，不证明人工标注准确率。

历史与审核包中的SHA256是逐字节校验。不要自动格式化、改换行、删掉快照中的预览/缓存，或在当前最终结果上重新生成旧review_package；这些操作会破坏历史验收。Git检出后的换行转换也可能影响字节哈希，需与数据内容变更区分。

下游写入自己的实验目录，不覆盖task5的final_mapping.json、review_package或history。若后续人工确实修改关系，应新增版本及修改日志，并同步更新统计和报告，避免静默改写本次交接版本。
