# 实验项目 2：游览步骤的实体识别

读取实验 1 的 `task1/data/final/documents.jsonl`，不改动上游数据。Python 3.10+，仅标准库；浏览器直接打开 SVG 图。使用环境变量 `DEEPSEEK_API_KEY`，也可从根目录的 `.env` 读取同名字段。

从仓库根目录执行：

```powershell
python task2/run.py v1
python task2/run.py v2
python task2/analyze.py
```

每次运行先校验输入 SHA-256 及分块映射。相同版本、分块、文本、Prompt 和模型配置命中缓存，无 API 调用；成功响应按请求哈希存档。实时 API 即便 temperature=0 也可能有细微变化，历史结果以保存的响应为准。如需新实验，请先把整个 results 归档到其他位置；避免同时运行同一版本。可用 `--pilot` 探测一个分块，默认并发 4。网络错误、服务限流、输出截断及无效 JSON 最多试三次；认证等永久错误记录并退出非零，分析拒绝不完整结果。调用参数见 config.json。

| 文件 | 内容 |
|---|---|
| ENTITY_SPEC.md / prompts/ | 实体规范与 V1、V2 Prompt |
| results/input_manifest.json | 固定输入摘要、文档与分块映射 |
| results/v1/、results/v2/ | entities.json、issues.json、run.json、raw/ |
| results/analysis/summary.json | 景区分布、检查与用量汇总 |
| results/analysis/frequencies.csv、*.svg | 两轮三类词频和柱状图，另含景区对比图 |
| results/analysis/*_only.json | 严格按文档、位置和标签计算的差异 |
| results/analysis/human_review.md | 六组原文与预测、AI 辅助核验、学生人工确认结论 |
| QUALITY.md / REPORT.md | 实际复核证据与报告模板第 2 章 |

异常统计是对齐阶段事件数：unmatched 为响应候选未找到或序号无效；overlap 为被剔除的重叠位置；duplicate 为重复预测的位置事件（count 字段是该位置多出的条数）；schema 与 type_conflict 分别为格式/标签错误和同位置类型冲突。运行日志只保存状态、异常类别和用量，不记录认证头或密钥。

仅复核既有结果时，可单独执行 `python task2/analyze.py`，无需 API 密钥。此命令重建统计和图表，仅在抽查文件缺失时生成样本初稿。实验 3、6 可读取 `results/v2/entities.json`，以 `doc_id` 对接实验 1 的 `clean_text`，并使用 `start`、`end` 恢复提及位置。V1 与两版差异保留用于核对漏项。
