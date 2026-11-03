# Task1 正式交付数据

项目 2 的固定输入是本目录的 `documents.csv`，或内容相同的 `documents.jsonl`。

- 数据版本：2026-11-03，18 条；故宫、西湖、九寨沟各 1 篇官方路线和 5 篇游客游记。
- 下游处理读取 `clean_text`，以 `doc_id` 关联；字符索引对应该文本，不要随意重新清洗。
- 作者缺失 2 条、完整发布时间缺失 15 条。未知值在 JSONL 中为 null、CSV 中为空；不从月日或相对日期猜测年份。
- 源批次：`supplement_20261103_172434_826954`。游客页面在用户本人登录的 Chrome CDP 会话中获取，官方页面复用归档。

## 文件

- `documents.csv` / `documents.jsonl`：统一 Document 数据，符合根目录 SCHEMA.md。
- `QUALITY_REPORT.md` / `quality_report.json`：从交付 CSV 重新读取生成的检查及逐条样例。
- `cleaning_audit.json`：清洗操作明细。
- `content_preservation_check.json`：18 条正文清洗前后非空白字符序列均一致。
- `provenance.json`：笔记规范 URL、原件文件名及 SHA-256，用于本地原件核对。

## 与本地归档的差异

本目录移除了小红书 URL 中临时分享参数；doc_id、raw_text、clean_text 保持不变。原始分享链接、浏览器 HTML、会话日志及历史失败记录保留在本地 `task1/crawler/results/`，不进入 Git。`raw_html_path` 是相对于本目录的本地归档路径，新克隆仓库不含这些原件。不能仅凭 Git 副本重做 HTML 解析，但可以直接进行后续实验和检查结构化文本。

原始 HTML 可能含页面状态及账户相关信息，未经检查不直接发布。Git 中的文本仍是来源网站内容，公开传播前需考虑来源许可。

## 质量与限制

无空正文、重复 URL 或完全重复文档；未检测到明显乱码、大量连续重复行。乱码检查为启发式；重复检查为精确匹配。游客 emoji、话题、提及账号及看图提示保留；西湖官方页仍有延伸阅读尾段。正文可能因内联标签存在分行，没有语义重写；未识别图片内文字，没有开展实验 2–6。

本地重新导出（需保留源批次）：

```powershell
python -m task1.crawler.export_final task1/crawler/results/supplement_20261103_172434_826954
```

离线验证：

```powershell
python -m unittest task1.crawler.test.test_existing_chrome task1.crawler.test.test_formal_parser task1.crawler.test.test_cleaner task1.crawler.test.test_document_pipeline
```
