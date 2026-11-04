# 实验项目 2 成果交接

## 1. 项目定位与最终版本

实验 2 从实验 1 的清洗正文提取景点与游览地点、交通方式、时间节点。DeepSeek 根据 Prompt 提取原文字面和类型，Python 负责对齐、校验和导出提及记录。

**V2 是下游默认读取版本，V1 仅供实验对照。** V2 使用 `deepseek-flash` 和 `task2/prompts/v2.txt`。配置位于 `task2/config.json`，采用 JSON Object 输出、关闭思考、temperature=0、max_tokens=2400。

输入为 `task1/data/final/documents.jsonl`，最终实体为 `task2/results/v2/entities.json`。北京故宫、杭州西湖、九寨沟各有 1 篇官方路线和 5 篇游客游记，共 18 篇、21 块。V2 完成全部分块，共输出 **1,415 条实体提及**，其中 POI 1,112 条、TRANSPORT 121 条、TIME 182 条。

## 2. 核心文件位置索引

| 相对路径 | 文件类型 | 用途 | 下游是否需要 |
|---|---|---|---|
| `task2/results/v2/entities.json` | JSON | 最终实体提及、来源和全文位置 | 必需 |
| `task1/data/final/documents.jsonl` | JSONL | 清洗正文与文档元数据 | 关联原文时必需 |
| `task2/ENTITY_SPEC.md` | Markdown | 三类实体边界及抽查后补充的判定口径 | 解释标签和筛选噪声时参考 |
| `task2/results/input_manifest.json` | JSON | 固定输入的 SHA-256、文档与分块映射 | 验证输入版本时使用 |
| `task2/results/v2/` | 目录 | 最终实体及 V2 审计产物 | 实体必读，审计按需 |
| `task2/results/v2/run.json` | JSON | 配置、分块状态、异常统计和切片校验结果 | 审计按需 |
| `task2/results/v2/issues.json` | JSON | 被剔除或发生冲突的候选事件 | 诊断按需 |
| `task2/results/v2/raw/` | 目录 | 按分块和请求保存的原始模型响应 | 追溯候选按需 |
| `task2/results/v1/` | 目录 | V1 对照结果和运行记录 | 仅对照时使用 |
| `task2/results/analysis/` | 目录 | 汇总、词频、SVG 图表、两版差异及抽查记录 | 分析与可视化按需 |
| `task2/results/analysis/human_review.md` | Markdown | 六组样本的原文、预测和学生裁决 | 复核质量时使用 |
| `task2/QUALITY.md` | Markdown | 已知误报、漏报及边界问题 | 设计下游过滤时参考 |
| `task2/run.py` | Python | 批量调用、分块、对齐和导出 | 消费已有结果时无需运行 |
| `task2/analyze.py` | Python | 基于现有输出生成对比、统计和图表 | 消费已有结果时无需运行 |
| `task2/config.json` | JSON | 两轮共用的 API 参数 | 复现实验时参考 |
| `task2/prompts/v1.txt` | 文本 | V1 提取指令 | 仅对照时参考 |
| `task2/prompts/v2.txt` | 文本 | V2 提取和复查指令 | 追溯规则时参考 |

## 3. 最终实体数据结构

V2 文件顶层为 JSON 数组，每个对象表示一处实体提及。

| 字段 | 类型 | 含义 |
|---|---|---|
| `doc_id` | 字符串 | 实验 1 文档 ID，关联原文的主键 |
| `scenic_spot` | 字符串 | 文档所属景区，可用于筛选。该字段不表示实体本身一定属于该景区 |
| `source_type` | 字符串 | 来源类别，`official` 或 `user_generated` |
| `text_type` | 字符串 | 文本体裁，`official_route` 或 `travel_note` |
| `source_name` | 字符串 | 来源网站或平台名称 |
| `url` | 字符串 | 来源页面 URL |
| `chunk_id` | 字符串 | 分块标识，由文档 ID 与块起点构成 |
| `chunk_start`、`chunk_end` | 整数 | 分块在全文 `clean_text` 中的左闭右开区间 |
| `text` | 字符串 | 该处提及的原文切片 |
| `type` | 字符串 | `POI` 为景点、游览地点或具名站点，`TRANSPORT` 为交通方式或具体线路，`TIME` 为游览相关的日期、时刻、时段或时长 |
| `start`、`end` | 整数 | 实体在全文 `clean_text` 中的左闭右开区间 |

关联使用 `doc_id`，定位使用 `start`、`end`，筛选使用 `scenic_spot`、`type`。同一版中可用 `(doc_id, start, end, type)` 引用具体提及。

V2 文件首条真实记录如下。

```json
{
  "doc_id": "gugong_official_df6c311301c59157",
  "scenic_spot": "北京故宫",
  "source_type": "official",
  "text_type": "official_route",
  "source_name": "北京旅游网",
  "url": "https://www.visitbeijing.com.cn/article/47QrSKGCz9N",
  "chunk_id": "gugong_official_df6c311301c59157_0",
  "chunk_start": 0,
  "chunk_end": 2398,
  "text": "故宫",
  "type": "POI",
  "start": 0,
  "end": 2
}
```

## 4. 原文关联与字符位置规范

偏移以实验 1 的 `clean_text` 为基准，采用 Python Unicode 码点索引，从 0 开始，左闭右开 `[start,end)`。`raw_text`、UTF-8 字节位置及 JavaScript 的 UTF-16 索引不能直接代入。读取后保留正文原有空格、换行和字符。

按 `doc_id` 找到文档后，用 `clean_text[start:end]` 恢复提及。相同文本在不同位置出现时分别记录。`chunk_start` 和 `chunk_end` 指整块的全文范围，`start` 和 `end` 已换算为实体的全文位置。若在分块子串内切片，才需要从两端减去 `chunk_start`。

从项目根目录执行以下只读示例。

```python
import json
from pathlib import Path

source = Path("task1/data/final/documents.jsonl")
with source.open(encoding="utf-8") as stream:
    documents = {}
    for line in stream:
        if line.strip():
            doc = json.loads(line)
            documents[doc["doc_id"]] = doc

output = Path("task2/results/v2/entities.json")
entities = json.loads(output.read_text(encoding="utf-8"))

for entity in entities:
    clean_text = documents[entity["doc_id"]]["clean_text"]
    start, end = entity["start"], entity["end"]
    assert 0 <= start < end <= len(clean_text), entity
    assert clean_text[start:end] == entity["text"], entity

selected = [
    entity for entity in entities
    if entity["scenic_spot"] == "九寨沟" and entity["type"] == "POI"
]
print(f"已验证 {len(entities)} 条，筛选得到 {len(selected)} 条")
```

## 5. 输出数据质量与已知限制

- V2 包含 POI 1,112、TRANSPORT 121、TIME 182 条。位置一致性校验通过 1,415 条，失败 0 条。无法定位候选为 0，异常记录包含 24 个重复位置事件和 103 个重叠剔除事件。
- `align()` 按位置和标签去重，优先保留较长的重叠跨度，同一跨度若有跨标签冲突则剔除。上述数字是对齐事件数，异位重复提及仍保留。
- 字符位置正确只证明切片一致。抽查发现 V2 仍把背景城市名“杭州”、路线分组“右线”和景观集合“西湖十景”标为 POI，也把历史背景“南宋”标为 TIME，把票务商品“游船联票”标为 TRANSPORT。已确认漏项包括“树正沟”“步行”“紫禁城”“清晨”“傍晚”。人工裁决记录在抽查文档中，预测数组仍是模型输出。
- TIME 共用一个标签，包含日期、时刻、时段和持续时间，未提供子类型或标准时间值。实验 2 未执行完整的地点名称归一化或实体链接。同字符串可能指不同地点，别名或简称也可能指同一地点。父子景点关系需结合正文判断。

## 6. 下游实验使用建议

### 实验 3：游览路线的层级结构挖掘

**已有数据。** 按 `doc_id` 关联 `clean_text`，用 `text_type` 和 `source_type` 区分官方路线和游记。POI 与 TIME 的跨度可辅助识别列表、箭头、段落和时间窗口，TRANSPORT 可辅助判断换乘或移动段。

**下游需实现。** 先识别正文里的路线段、标题和步骤关系，再将位置邻近的实体绑定到对应步骤。字符顺序反映叙述顺序，文本可能回顾景点、列举备选路线或插入历史背景。区分“20分钟”这类停留时长、“下午16:00”这类时刻和“第二天”这类相对日期，再决定它们如何参与时间层级。

### 实验 6：多源程序性知识融合与图谱可视化

**已有数据。** 读取 V2，按 `scenic_spot`、`doc_id` 和 `type` 筛选候选提及。保留 `doc_id`、`start`、`end`、原文字面和来源 URL 作为节点或关系的证据。

**下游需实现。** 先按上下文过滤背景 POI、路线分组和非游览时间，再结合景区、名称、简称、别名和父子关系进行归一化、消歧及跨文档去重。将原始提及与归并后的图谱节点分别保存。路线边、时序边和父子边需要原文或后续抽取结果支持，保留证据以便回查。

## 7. 最简使用指引

- 最终实体：`task2/results/v2/entities.json`
- 原文数据：`task1/data/final/documents.jsonl`
- 实体规范：`task2/ENTITY_SPEC.md`
- 关联键：`doc_id`，定位取 `clean_text[start:end]`。
- 偏移：Python Unicode 码点，从 0 开始，左闭右开。
- 位置已校验，语义仍有误报和漏报，进入路线或图谱前需结合原文筛选。
