# 任务 4 质量检查记录

本文件由 `python -X utf8 task4/run.py` 自动重建，记录程序校验、人工标注评估和已知边界。

## 输入与位置校验

- 文档数：18；人工标注：28 条；覆盖 5 篇游客游记。
- 文档 SHA-256：`a00d04703a53c515a39a39a74582f1e6d00f7098474460eec7ecb93a722c3a65`。
- 实体 SHA-256：`ba18804ef40693ea6cd676a8facab9e97f598c9e74a2c0d842b3a732578fe87e`。
- 标注 SHA-256：`19635032720e6227d944962c4ff9cc2658aafdf2acb95d1c02596e6f13fc1458`。
- 所有实体、代词和先行词切片均与 `clean_text` 对应位置一致；标注中的句子切分也通过复核。

## 检测与消解统计

- 全语料检测到 162 个代词/指示表达，覆盖 16 篇文档。
- 按类型：{'person_third': 14, 'place': 32, 'demonstrative': 19, 'person_reflexive': 3, 'person_generic': 8, 'object': 4, 'discourse': 12, 'determiner': 32, 'person_second': 9, 'person_first': 29}。
- 按状态：{'no_antecedent': 24, 'resolved': 55, 'out_of_scope': 49, 'ambiguous': 11, 'non_entity': 23}。
- 已消解 55 条，弃权 24 条，歧义 11 条。
- 先行词类型：{'POI': 56, 'PERSON': 1, 'ROUTE_SEGMENT': 7, 'ROUTE': 1, 'TRANSPORT': 1}。

## 人工标注评估

- 标注总数：28；明确先行词 26 条；无明确先行词 2 条。
- 覆盖率：100.00%（26/26）。
- 已消解准确率：100.00%（26/26）。
- 总体准确率（含弃权）：100.00%。
- 错误案例：0 条。

| 类型 | 标注数 | 明确先行词 | 已消解 | 总体准确率 |
|---|---:|---:|---:|---:|
| demonstrative | 4 | 4 | 4 | 100.00% |
| determiner | 12 | 11 | 11 | 100.00% |
| person_third | 1 | 1 | 1 | 100.00% |
| place | 11 | 10 | 10 | 100.00% |

## 已知边界

- 规则只覆盖本批 18 篇文本中的代词和指示表达，未训练统计模型，也未使用神经网络共指模型。
- 人工标注是 5 篇游记中的定向样本，不是全语料 gold；28 条上的准确率不能外推为整体性能。
- 第一、第二人称和泛称主要标为 `out_of_scope`，不作为实体共指评估；它们仍保留在 `mentions.json` 中，便于检查检测召回。
- “这里特别提醒”这类指向下文的篇章指代被标为无明确先行词，系统应弃权；如果强行回指前文路线段，属于过度消解。
- 长路线段的先行词以原文箭头链整体表示，替换后句子可能不自然；`marked_text` 保留原词并标注预测，便于人工核对。

## 代表性输出

- `gugong_user_generated_ac13633e735a71ff`：`这里` → `午门`（POI，置信度 0.960）
- `xihu_user_generated_6322b1ddadb1b801`：`这` → `自行车`（TRANSPORT，置信度 0.460）
- `xihu_user_generated_ddcb0707c1791565`：`这` → `断桥残雪→白堤→平湖秋月→曲院风荷→花港观鱼（对面就是太子湾公园）→然后坐船看三潭印月`（ROUTE_SEGMENT，置信度 0.838）
- `jiuzhaigou_user_generated_653f517e7ecb42a0`：`这` → `原始森林 → 芳草海 → 天鹅海 → 🚌箭竹海`（ROUTE_SEGMENT，置信度 0.830）
- `jiuzhaigou_user_generated_aa7e68d694fcc6a7`：`这里` → `诺日朗中心`（POI，置信度 0.748）
- `gugong_official_df6c311301c59157`：`那里` → `故宫`（POI，置信度 0.674）
- `gugong_official_df6c311301c59157`：`这` → `故宫`（POI，置信度 0.760）
- `gugong_official_df6c311301c59157`：`这里` → `故宫`（POI，置信度 0.754）

