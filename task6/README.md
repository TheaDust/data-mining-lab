# task6：多源程序性知识的融合与图谱可视化

把 task1 的 18 篇景区文档、task2 的 1,415 个实体、task3 的 23 条路线 / 250 个步骤，以及 task5 的 41 条条件建议，融合成一张可查询的异构图谱。

- 图规模：**583 个节点、1,751 条边**
- 三个景区各自连通：北京故宫、杭州西湖、九寨沟
- 全部自动检查通过（18/18）
- 图查询接口：`task6/graph.py`，task7 直接调用，避免把图谱内容塞进 Prompt

## 1. 输入

| 输入 | 路径 | 用途 |
|---|---|---|
| task1 文档 | `task1/data/final/documents.jsonl` | 文档节点、来源追溯 |
| task2 实体 | `task2/results/v2/entities.json` | POI 节点与提及频次；TIME/TRANSPORT 用于统计校验 |
| task3 官方路线 | `task3/results/official_routes.json` | 17 条官方路线、路线步骤 |
| task3 游客路线 | `task3/results/visitor_routes.json` | 6 条游客路线 |
| task5 条件建议 | `task5/results/final_mapping.json` | 41 条条件-建议对（可选输入，本次已融合） |

输入文件的 SHA-256 写入 `results/stats.json` 和 `results/graph.json` 的 `metadata.inputs`，用于复现。

## 2. 图谱 Schema

### 2.1 节点类型（9 类）

| 节点类型 | 数量 | 说明 | 关键属性 |
|---|---:|---|---|
| `ScenicSpot` | 3 | 景区根节点 | `route_count`、`document_count`、`condition_count` |
| `POI` | 215 | 规范化后的景点 | `mention_count`、`route_count`、`aliases`、`source_types`、`in_route` |
| `Route` | 23 | 官方/游客路线 | `route_id`、`route_kind`、`source_type`、`step_count` |
| `Step` | 250 | 路线中的一步 | `order`、`day`、`time_period`、`activity_raw`、`pois` |
| `Activity` | 12 | 归一化活动 | `category`（游览参观/乘车换乘/徒步步行等） |
| `TimePeriod` | 3 | 时段 | `period`（上午/中午/下午） |
| `Condition` | 41 | 条件性建议 | `condition`、`recommendation`、`condition_type`、`review_status` |
| `ConditionType` | 18 | 条件类型（按景区实例化） | `label` |
| `Document` | 18 | 原文档 | `title`、`source_type`、`text_type`、`url` |

### 2.2 边类型（14 类）

| 边类型 | 数量 | 方向 | 说明 |
|---|---:|---|---|
| `HAS_ROUTE` | 23 | 景区 → 路线 | 路线归属 |
| `HAS_STEP` | 250 | 路线 → 步骤 | 属性 `order` |
| `NEXT` | 227 | 步骤 → 下一步 | 路线内顺序链 |
| `VISITS` | 294 | 步骤 → POI | 属性 `order_in_step`、`aligned_to_task2` |
| `STARTS_AT` | 21 | 路线 → POI | 首步 POI；2 条边界路线不虚构 |
| `ENDS_AT` | 21 | 路线 → POI | 末步 POI |
| `HAS_ACTIVITY` | 272 | 步骤 → 活动 | 一个步骤可多标签 |
| `AT_TIME` | 31 | 步骤 → 时段 | 仅显式时段 |
| `HAS_CONDITION` | 41 | 景区 → 条件 | 条件归属 |
| `HAS_TYPE` | 41 | 条件 → 条件类型 | 条件分类 |
| `RELATES_TO` | 30 | 条件 → POI | 推荐文本中的最长子串匹配 |
| `DESCRIBES` | 23 | 文档 → 路线 | 路线来源 |
| `FROM_DOC` | 41 | 条件 → 文档 | 条件来源 |
| `MENTIONS` | 436 | 文档 → POI | 属性 `count`，同一文档内聚合 |

`Document` 和 `MENTIONS` 保留完整来源链；可视化时默认隐藏，避免文档节点成为视觉枢纽。

## 3. 融合规则

1. **task3→task2 精确对齐**：用 `(doc_id, start, end, type)` 对齐路线步骤的 `entity_ref`。291 个引用全部命中 task2，0 个失败。
2. **别名归一**：只使用 task3 已记录的保守别名（九寨沟：天鹅湖→天鹅海、诺日朗中心→诺日朗中心站），不合并父子/主题名（故宫 ≠ 北京故宫）。
3. **POI 去重**：按 `(景区, 规范化名称)` 聚合 task2 提及与 task3 路线引用；得到 215 个主图 POI。
4. **低频过滤**：保留“被任一条路线引用”或“task2 提及 ≥2 次”的 POI；其余 125 个单次候选写入 `results/excluded_pois.csv`，不进入主图。
5. **边界动作过滤**：`出沟`、`进景区` 等 4 个路线“POI”实际是边界动作，不建 POI 节点；步骤本身仍保留。
6. **活动归一**：把 `参观/游览`、`步行/徒步`、`观光车/换乘`、`坐船`、`用餐/休息` 等归一为 12 个活动节点，原始文本留在 `Step.activity_raw`。
7. **条件融合**：41 条 task5 条件全部入图；在推荐语/条件文本中做最长子串匹配并去掉“故宫/九寨沟/西湖”等泛称，20 条条件链接到具体 POI（30 条 `RELATES_TO` 边）。

## 4. 输出

| 文件 | 说明 |
|---|---|
| `results/nodes.csv` | 节点表（`properties` 为 JSON 字符串） |
| `results/edges.csv` | 边表 |
| `results/graph.json` | 节点-边 JSON，含 metadata 与输入哈希 |
| `results/graph.graphml` | 可导入 Gephi/Neo4j 的 GraphML |
| `results/stats.json` | 规模、类型分布、对齐与过滤统计 |
| `results/quality.json` | 18 项自动检查与描述性分析 |
| `results/QUALITY.md` | 人读版质量报告 |
| `results/excluded_pois.csv` | 被过滤的 125 个低频 POI 候选 |
| `figures/*.png` | 静态图：故宫/九寨沟路线网络、故宫条件子图、总览 |
| `figures/*.html` | 自包含交互图（故宫/西湖/九寨沟） |

## 5. 运行

```bash
# 全流程：构图 → 质量检查 → 可视化
python -m task6.run

# 只构图与检查
python -m task6.run --skip-viz

# 只重画某个景区
python -m task6.run --spot 北京故宫

# 测试
python -m unittest discover -s task6/tests -v
```

## 6. 图查询接口（task7 使用）

```python
from task6.graph import open_graph

store = open_graph()

store.scenic_spots()                                  # ['九寨沟', '北京故宫', '杭州西湖']
store.routes("北京故宫", source_type="official")      # 官方路线
store.route_sequence("gugong_official_..._route_01")  # 有序步骤（POI/时间/活动）
store.route_pois("...")                               # 去重后的 POI 序列
store.routes_through_poi("太和殿", "北京故宫")         # 经过某 POI 的路线
store.conditions("北京故宫", condition_type="时间约束") # 条件建议
store.conditions(poi="珍宝馆", scenic_spot="北京故宫")
store.find_poi("天鹅湖", "九寨沟")                    # 别名解析 → 天鹅海
store.subgraph("北京故宫", node_types={"Route", "POI", "Condition"})
```

命令行：

```bash
python -m task6.graph stats
python -m task6.graph routes --spot 北京故宫
python -m task6.graph route gugong_official_df6c311301c59157_route_01
python -m task6.graph poi 太和殿 --spot 北京故宫
```

## 7. 已知限制

- 250 个步骤中只有 31 个有显式时段、125 个有日期/天数；时间规划不能只依赖图谱。
- 219 个步骤没有时段，task7 需要把“缺失”当作未知处理，不能默认为上午/下午。
- 条件到 POI 的连接是字符串匹配，存在漏链（21 条未链接）和少量误链风险，边属性保留了 `matched_text` 和 `match_field`。
- task5 的 `review_status` 仍为“待真实人工确认”，图谱原样保留该状态，不把它当作金标准。
- task2 的 TIME/TRANSPORT 实体没有单独建节点，只用于统计与校验；如需按交通方式查询，可在后续版本扩展。
