# 数据挖掘探索性实验：统一数据 Schema 规范 v1.0

> 项目：景区游览指南的程序性知识挖掘  
> 适用范围：实验 1–6  
> 目的：统一各阶段的数据组织方式，保证数据可追溯、可复现、可扩展，并避免后续实验反复修改字段。

---

## 1. 设计目标

本项目采用“**一个文档主表 + 多个派生结构**”的方式组织数据。

核心原则：

1. **实验 1 负责建立统一的文档级数据基础。**
2. 后续实体、路线、共指、条件建议等结果均通过 `doc_id` 与原始文档关联。
3. 区分：
   - 网页原始事实；
   - 清洗后的文本；
   - 后续算法推导出的知识。
4. 不把所有内容塞进一个超大 JSON。
5. 所有后续结果都应能够追溯到原始网页和对应文本。
6. Schema 优先保持简单稳定，确有需求时再增加字段。

总体关系：

```text
documents
    │
    │ doc_id
    ├── entities
    ├── routes
    ├── coreferences
    ├── condition_advices
    └── knowledge_graph
```

---

# 2. Document Schema：文档主表

实验 1 的核心输出统一采用该 Schema。

推荐格式：`CSV / JSONL / Excel` 均可。

## 2.1 核心字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `doc_id` | string | 是 | 文档唯一 ID，后续所有实验通过该字段关联 |
| `scenic_spot` | string | 是 | 景区名称，如“北京故宫”“杭州西湖” |
| `source_type` | enum | 是 | 来源类型：官方或用户生成内容 |
| `source_name` | string | 是 | 来源网站或平台名称 |
| `url` | string | 是 | 原始网页 URL |
| `text_type` | enum | 是 | 文本类型，如官方路线、游客游记 |
| `title` | string | 是 | 页面/文章标题 |
| `author` | string/null | 否 | 作者，无法获取时为 `null` |
| `publish_time` | string/null | 否 | 发布时间，无法获取时为 `null` |
| `crawl_time` | string | 是 | 实际抓取时间，建议 ISO 8601 格式 |
| `crawler_type` | enum | 是 | 使用静态或动态 crawler |
| `raw_text` | string | 是 | 从网页提取的原始正文文本 |
| `clean_text` | string | 是 | 清洗后的正文，供后续实验使用 |

## 2.2 推荐扩展字段

以下字段可按实际情况添加，但不是第一版必须项。

| 字段 | 类型 | 说明 |
|---|---|---|
| `raw_html_path` | string/null | 原始 HTML 本地保存路径 |
| `language` | string | 默认可填写 `zh-CN` |
| `metadata` | object | 额外来源信息，不建议滥用 |
| `crawl_status` | string | 抓取成功/失败状态 |
| `notes` | string/null | 特殊问题或人工备注 |

---

# 3. 固定枚举值

为避免同一个概念出现多种写法，以下字段应尽量使用统一枚举。

## 3.1 source_type

```text
official
user_generated
```

含义：

- `official`：官方景区、政府、官方旅游平台等。
- `user_generated`：游客游记、攻略、社区内容等。

## 3.2 text_type

第一阶段固定：

```text
official_route
travel_note
```

如后续确有需要，可扩展：

```text
official_guide
travel_tip
news
other
```

但新增前应先确认是否真的需要。

## 3.3 crawler_type

```text
static
dynamic
```

含义：

- `static`：`requests + BeautifulSoup`
- `dynamic`：`Playwright + Chrome`

---

# 4. doc_id 命名规范

`doc_id` 必须：

- 全局唯一；
- 稳定；
- 不依赖数组下标；
- 尽量能快速看出文档来源。

推荐格式：

```text
{scenic_spot}_{source_type}_{序号}
```

示例：

```text
gugong_official_001
gugong_user_001
xihu_official_001
huangshan_user_003
```

建议景区名称采用固定英文/拼音短名，例如：

```text
gugong
xihu
huangshan
zhangjiajie
jiuzhaigou
```

一旦确定，不要在项目中途随意更换。

---

# 5. Document 示例

```json
{
  "doc_id": "gugong_official_001",
  "scenic_spot": "北京故宫",
  "source_type": "official",
  "source_name": "故宫博物院官网",
  "url": "https://example.com/route",
  "text_type": "official_route",
  "title": "故宫一日游路线",
  "author": null,
  "publish_time": null,
  "crawl_time": "2026-11-02T20:00:00+08:00",
  "crawler_type": "static",
  "raw_text": "……",
  "clean_text": "……"
}
```

---

# 6. 文本版本与位置索引规则

后续实验 2 和实验 4 会记录实体、代词等的字符位置，因此必须明确位置索引对应哪一版文本。

统一规定：

> **所有 NLP 位置索引默认对应 `clean_text`。**

统一采用：

```text
start：从 0 开始
end：左闭右开，即 [start, end)
```

例如：

```python
clean_text[start:end]
```

必须能够直接得到对应实体文本。

示例：

```json
{
  "text": "太和殿",
  "start": 126,
  "end": 129
}
```

则：

```python
clean_text[126:129] == "太和殿"
```

注意：

- 清洗完成后再做实体识别；
- 后续不要随意重新修改 `clean_text`；
- 如果清洗规则发生重大变化，应重新生成下游结果。

---

# 7. Entity Schema：实体识别结果

实验 2 使用。

每一个实体出现位置单独记录。

## 核心字段

```json
{
  "entity_id": "ent_000001",
  "doc_id": "gugong_official_001",
  "text": "太和殿",
  "entity_type": "POI",
  "start": 126,
  "end": 129
}
```

推荐字段：

| 字段 | 说明 |
|---|---|
| `entity_id` | 实体出现记录唯一 ID |
| `doc_id` | 来源文档 |
| `text` | 原始实体文本 |
| `entity_type` | 实体类型 |
| `start` | `clean_text` 起始位置 |
| `end` | `clean_text` 结束位置 |

实体类型第一版：

```text
POI
TRANSPORT
TIME
```

注意：

> 同一实体在同一文章中出现多次，应分别保留位置记录，而不是只保留一个实体名称。

---

# 8. Route Schema：路线结构

实验 3 使用。

路线不要直接塞入 Document 主表，而应独立保存。

示例：

```json
{
  "route_id": "route_gugong_001",
  "doc_id": "gugong_official_001",
  "scenic_spot": "北京故宫",
  "route_name": "故宫一日游",
  "steps": [
    {
      "step_id": 1,
      "time_text": "上午9点",
      "time_period": "上午",
      "poi": "午门",
      "activity": "入园"
    },
    {
      "step_id": 2,
      "time_text": null,
      "time_period": "上午",
      "poi": "太和殿",
      "activity": "参观"
    }
  ]
}
```

## 8.1 Route 核心字段

| 字段 | 说明 |
|---|---|
| `route_id` | 路线唯一 ID |
| `doc_id` | 来源文档 |
| `scenic_spot` | 景区 |
| `route_name` | 路线名称 |
| `steps` | 有序步骤列表 |

## 8.2 Step 核心字段

| 字段 | 说明 |
|---|---|
| `step_id` | 路线内部步骤编号 |
| `time_text` | 原文时间表达 |
| `time_period` | 归一化后的时间段 |
| `poi` | 景点 |
| `activity` | 活动 |

重要原则：

> `time_text` 表示原文事实，`time_period` 表示后续归一化结果。

例如：

```text
原文："下午两点左右"
time_text = "下午两点左右"
time_period = "下午"
```

如果原文没有时间，不要凭空补一个“上午/下午”当作原文事实。

---

# 9. Coreference Schema：共指消解

实验 4 使用。

示例：

```json
{
  "coref_id": "coref_0001",
  "doc_id": "xihu_user_001",
  "pronoun": "那里",
  "pronoun_start": 342,
  "pronoun_end": 344,
  "antecedent": "断桥",
  "antecedent_start": 315,
  "antecedent_end": 317,
  "method": "llm",
  "confidence": 0.91
}
```

核心字段：

| 字段 | 说明 |
|---|---|
| `coref_id` | 共指记录 ID |
| `doc_id` | 来源文档 |
| `pronoun` | 指代表达 |
| `pronoun_start/end` | 指代表达位置 |
| `antecedent` | 预测先行词 |
| `antecedent_start/end` | 先行词位置 |
| `method` | 使用的方法 |
| `confidence` | 可选置信度 |

无明确先行词时：

```json
{
  "antecedent": null
}
```

不要强行预测。

---

# 10. Condition Advice Schema：条件建议

实验 5 使用。

示例：

```json
{
  "advice_id": "adv_0001",
  "doc_id": "huangshan_user_003",
  "scenic_spot": "黄山",
  "condition_type": "weather",
  "condition": "如果下雨",
  "advice": "建议携带雨衣，不建议撑伞",
  "source_sentence": "如果下雨，山上风大，建议穿雨衣，不建议撑伞。",
  "start": 230,
  "end": 255
}
```

核心字段：

| 字段 | 说明 |
|---|---|
| `advice_id` | 建议记录 ID |
| `doc_id` | 来源文档 |
| `scenic_spot` | 景区 |
| `condition_type` | 条件类别 |
| `condition` | 条件部分 |
| `advice` | 建议部分 |
| `source_sentence` | 原始句子 |
| `start/end` | 在 `clean_text` 中的位置 |

条件类型可逐步归纳，例如：

```text
weather
visitor_type
time
physical_condition
transport
crowd
season
other
```

暂时不要为了“看起来完整”人工制造不存在的类别。

---

# 11. Knowledge Graph 输入原则

实验 6 构建知识图谱时，主要读取：

```text
documents
entities
routes
condition_advices
```

必要时结合：

```text
coreferences
```

所有节点和关系应尽量保留：

```text
source_doc_id
source_type
source_name
```

这样可以回答：

> 这个节点或关系是从哪里来的？

图谱合并时不得仅因为名称相似就强制合并。

例如：

```text
"西湖"
"西湖景区"
```

可能应该归一化。

但：

```text
"故宫"
"故宫博物院"
"故宫角楼"
```

是否合并需要根据实际语义判断。

---

# 12. 原始事实与推导结果必须分离

这是本 Schema 最重要的原则之一。

## 原始/采集信息

```text
url
title
raw_text
publish_time
source_name
```

## 清洗结果

```text
clean_text
```

## 后续算法推导

```text
entities
routes
coreferences
condition_advices
knowledge_graph
```

例如：

原文：

```text
下午两点左右从慈宁宫前往御花园。
```

允许：

```text
time_text = "下午两点左右"
time_period = "下午"
```

但不能把推测出来的信息重新写回 `raw_text` 或伪装成网页原文。

---

# 13. 文件组织建议

推荐：

```text
data/
├── raw/
│   ├── html/
│   └── raw_documents.jsonl
│
├── processed/
│   └── documents.jsonl
│
├── entities/
│   └── entities.jsonl
│
├── routes/
│   └── routes.jsonl
│
├── coreferences/
│   └── coreferences.jsonl
│
├── condition_advices/
│   └── condition_advices.jsonl
│
└── graph/
    ├── nodes.csv
    └── edges.csv
```

代码：

```text
crawler/
parsers/
cleaning/
entity_extraction/
route_extraction/
coreference/
condition_extraction/
graph/
```

---

# 14. 数据格式建议

## 中间数据

优先推荐：

```text
JSONL
```

理由：

- 每行一条记录；
- 支持复杂字段；
- 比普通 JSON 更方便流式处理；
- 比 CSV 更适合嵌套路线结构；
- 后续 Python 读取方便。

## 人工检查/报告

可额外输出：

```text
CSV / Excel
```

因此推荐：

> JSONL 作为标准机器数据格式，Excel/CSV 作为检查和展示格式。

---

# 15. 清洗与 Schema 的边界

Crawler / Parser：

```text
网页
↓
提取正文与网页元信息
↓
Document 初始记录
```

Cleaning：

```text
raw_text
↓
清洗
↓
clean_text
```

后续 NLP：

```text
clean_text
↓
entities / routes / coreferences / condition_advices
```

Crawler 不负责：

- 实体识别；
- 路线推理；
- 共指消解；
- 条件分类。

Parser 也不要过度承担后续 NLP 工作。

---

# 16. Schema 版本管理

当前版本：

```text
Schema Version: 1.0
```

原则：

1. 小范围新增可选字段：`1.0 → 1.1`
2. 修改核心字段含义：升级主版本，如 `1.x → 2.0`
3. 不随意重命名已经使用的字段
4. 如必须修改，提供迁移脚本

建议在项目根目录保存：

```text
SCHEMA.md
```

并将本文件作为唯一正式规范。

---

# 17. 第一阶段必须冻结的字段

当前 crawler 和实验 1 正在进行，因此下面这些字段应从现在开始固定：

```text
doc_id
scenic_spot

source_type
source_name
url

text_type
title
author
publish_time

crawl_time
crawler_type

raw_text
clean_text
```

其中：

```text
author
publish_time
```

允许为 `null`。

其他字段后续按实验需求扩展。

---

# 18. 项目统一数据流

最终整个项目应形成：

```text
网页
│
├── Static Crawler
└── Dynamic Crawler
        ↓
      Parser
        ↓
     raw_text
        ↓
     Cleaning
        ↓
     clean_text
        ↓
   Document Schema
        │
        ├── Entity Extraction
        │       ↓
        │    entities
        │
        ├── Route Extraction
        │       ↓
        │     routes
        │
        ├── Coreference Resolution
        │       ↓
        │  coreferences
        │
        └── Condition Extraction
                ↓
         condition_advices
                │
                ↓
        Knowledge Graph
```

核心连接键始终是：

```text
doc_id
```

---

# 19. 最终约定

从本版本开始：

> **实验 1–6 的所有数据处理均以本 Schema 为基础。**

尤其遵守以下五点：

1. `doc_id` 作为文档级统一主键。
2. 后续位置索引统一对应 `clean_text`。
3. `start/end` 使用 Python 左闭右开 `[start, end)`。
4. 原始事实、清洗结果、算法推导结果严格分离。
5. 新增字段可以，擅自改变已有字段语义不可以。

这套 Schema 的目标不是一次设计得极其复杂，而是：

> **够用、稳定、可追溯，并能够自然支撑实验 2–6。**
