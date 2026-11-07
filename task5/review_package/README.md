# 实验5独立语义核验材料包

本包只导出已冻结结果，没有重新抽取、修改Prompt或调用模型。所有审核结论列为空，状态为待审核。请先读 review_protocol.md。

## 上传建议

优先上传 **review_all.xlsx 和 review_protocol.md**。Excel包含全部A–E、合并来源展开明细、18篇全文，已逐单元格与JSON核对，无文本截断。较长单元格在表格显示时可能受行高限制，但其值完整，可在编辑栏查看，或上传对应JSON便于读取嵌套字段。

若ChatGPT对Excel长文本/嵌套JSON读取不完整，另外上传A–E五个JSON及F_source_documents.json。G_near_duplicates.json是补充线索，不替代全表重复核验。

## 文件用途与实际数量

| 材料 | 数量 | 来源与用途 |
|---|---:|---|
| A_final_pairs.json / A_FinalPairs | 32条 | results/final_mapping.json全部关系，含所有合并来源和上下文；核验FP、边界、关联、类别 |
| B_quarantined.json / B_Quarantined | 15条 | results/rejected_pairs.json全部隔离记录；从raw_pairs.json恢复原始输出、缓存引用、具体过滤规则 |
| C_rule_missed.json / C_RuleMissed | 36个 | results/negative_audit.json原有抽查窗口，保持原顺序；找候选阶段漏抽 |
| D_llm_rejected.json / D_LLMRejected | 20个 | candidates.json中有真实成功响应但该窗口pairs为空者，确定性分层抽样；找模型抽取阶段漏抽 |
| E_dedup_merges.json / E_DedupMerges | 5组、5次合并 | dedup_log.json全部操作；每组含保留与移除成员，共10个成员引用 |
| F_source_documents.json / F_SourceDocuments | 18篇 | task1/data/final/documents.jsonl的完整clean_text及文档元信息；供独立解决指代与跨段依赖 |
| A_SourceDetails（Excel） | 37条 | A的sources展开，完整覆盖validated_pairs.json，不是额外预测 |
| E_MergeMembers（Excel） | 10条 | E的members展开，便于直接查看每个成员的原文与上下文 |
| G_near_duplicates.json / G_NearDuplicates | 0条 | 原near_duplicate_review.json为空，不意味着A没有剩余重复，仍须全表比对 |
| integrity_checks.json | 1份 | 各组数量、D抽样总体和分层、内容一致性、原文件导出前后SHA256 |
| package_manifest.json | 1份 | 本包文件哈希，便于上传后核对版本 |

## A–E的关系与ID

- A覆盖37条校验记录去重后的32条；5条被移除记录仍在A.sources与E中。A_SourceDetails和E_MergeMembers是嵌套结构的重复展示。
- B是52条原始预测中被隔离的15条；与37条校验记录互斥。同一个窗口可能同时产生A关系和B隔离关系，因此文档或窗口ID可以重叠。
- C只含当时规则未命中的36个窗口，不重新挑选。D来自规则已命中的151候选，与C窗口互斥。D严格选择该窗口原模型返回零条记录者，不将“模型有输出但全部被自动过滤”的B窗口混为模型拒绝。
- E的保留记录也在A内，移除记录仍保留完整原文；不能把E计为新关系。
- pair_id沿用当前冻结版本的R编号，不保证跨实验版本不变。window_id/candidate_id为原doc_id加Unicode起点。source_start/end左闭右开，按Python Unicode字符下标，不是UTF-8字节，也不是UTF-16单元。
- B原输出没有独立关系ID，original_relation_id明确为null。补建RAW-0001等编号按冻结raw_pairs.json的1起始序号，另给0起始索引与cache_id；该编号不是伪造的原始模型ID。

## 原文、上下文与缺失字段

source_text逐字保留原窗口；context_before/after保留所在完整段及前后各一段范围中窗口外的文本，context_full为完整组合，带准确起止位置。段落可能含多句，因此通常超过相邻一句的上下文。文档开头或结尾的空上下文是自然边界，不是缺失。遇到更远的路线标题或指代，使用F全文。

JSON中空字符串表示自然边界的空上下文，null表示没有历史值。Excel会把空字符串保存为空单元格；核对时按字段类型等价处理，不将其视为文本丢失。Excel的sources、members等单元格使用标准JSON序列化，并另附A_SourceDetails、E_MergeMembers展开页。

预测condition、recommendation、evidence_span可能与原文不一致，特别是被隔离记录。包内保持原预测不修正，并标出子串检查结果，不把有问题的预测伪装成证据。

D历史响应只输出pairs，没有逐窗口解释；current_rejection_reason为null，注明缺失。C、D附原抽取器的缓存哈希、模型、版本与真实返回记录，是同源结果，不是新的独立审核。

source_type沿用上游official/user_generated，另给中文标签；未通过外部网站重新核定来源性质。原文错字、表情、换行和脱敏表达均保留。

## 抽样与复现

D按景区×来源类型×最高优先级规则分层，每层按固定种子 `task5-independent-review-20261107-v1` 与窗口ID的SHA256排序，各层轮转取20条。抽样总体与实际分层数量见integrity_checks.json。窗口命中的全部触发词也导出，避免最高优先级标签掩盖其他触发词。

生成命令（仓库根目录）：

```powershell
D:/app_install/miniconda/envs/crawlert1/python.exe task5/prepare_review.py
```

只需openpyxl及Python标准库，无网络。生成器从完整请求重建缓存哈希并核对run_log及raw_pairs，避免将找不到的响应误当空输出；不导入run.py，不读取.env。导出前后核对全部results、baseline、源文与实验入口/说明/Prompt的文件哈希，不改写实验基线。

## 独立性边界

由另一个ChatGPT对话返回的意见应称“独立LLM辅助语义审核”。真实人工确认需由学生或教师另行完成。不得据本包或同源空输出声称已获得人工金标准、完整Recall或人工确认的Precision/F1。
