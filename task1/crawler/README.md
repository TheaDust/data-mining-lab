# 网页采集模块

## 正式交付与 Git 跟踪

项目 2 使用 `task1/data/final/documents.csv`（或同目录 JSONL）的 `clean_text`，以 `doc_id` 关联后续结果。该目录保存固定 18 条正式数据、质量报告和清洗审计，详见其中 README。

代码、测试、Schema 和正式数据随 Git 跟踪；`results/` 中原始页面、含分享参数的输入、会话日志和历史批次仅本地保留。正式数据中的小红书链接使用不含分享参数的笔记 URL，正文和 doc_id 不变。重新采集时可通过 `python -m task1.crawler.test.run_formal --inputs 本地输入清单.local.json` 提供合法来源的完整输入；不带参数的 URL 不保证始终公开可访问。新电脑缺少本地原件时，仍可从正式 CSV/JSONL开展后续实验，但无法直接重做原件解析。

## 使用用户 Chrome 会话或人工 HTML 补游客数据

程序不会启动/修改用户的 Chrome 调试配置，不读取/复制 cookie。请由用户主动启动可通过本机 CDP 访问的 Chrome，并在**该实例**中确认正常登录及笔记可见。日常 Chrome 已登录不代表另一个调试实例也已登录。本工具只使用已有 context，在自己的新标签页访问正文，结束仅关闭自己的标签页并断开驱动。

```powershell
python -m task1.crawler.test.supplement_notes --mode cdp --endpoint http://127.0.0.1:9222
```

若没有调试会话或访问仍受限，在正常 Chrome 逐条打开笔记并手动保存网页，按笔记 ID 命名为 `笔记ID.html`（不是网页源码空壳，需包含已渲染正文）。每次运行的 `import_map.json` 对应完整原始 URL、景区及文件名。然后执行：

```powershell
python -m task1.crawler.test.supplement_notes --mode local --html-dir "D:\你的HTML目录"
```

原三个官方文件只复制归档，不再次访问。每轮结果在 `results/supplement_时间/`，包含 session.json、notes_results.json、raw/、manifest.json、processed/documents.csv、QUALITY_REPORT.md、cleaning_audit.json、error.log。导入时间不冒充网页保存时间，人工来源写在 notes；原 URL 保留在 url。原 parser 和 cleaner 不变。无有效正文的文件不会写入成功 CSV。

## 18 个正式 URL

运行 `python -m task1.crawler.test.run_formal`，仅访问固定清单内的 18 个页面。先用静态采集，正文缺失时再普通 Chrome 访问一次；安全限制或登录页记录失败，不绕过。归档到 `results/formal_时间/`；`inputs.json` 是输入，`manifest.json` 对应原件和实际采集方式，`failures.json` 列出失败阶段和页面提示，`error.log` 保留诊断。失败页不混入成功 CSV。

复核：`python -m unittest task1.crawler.test.test_formal_parser task1.crawler.test.test_cleaner task1.crawler.test.test_document_pipeline`。离线再处理使用 `python -m task1.crawler.document_pipeline 结果目录`，不会重新抓取网页。

## Task1：采集、清洗、CSV 与质量检查

```powershell
conda activate crawlert1
python -m task1.crawler.test.inspect_sources
python -m unittest task1.crawler.test.test_cleaner task1.crawler.test.test_document_pipeline
```

每次运行单独归档到 `results/task1_时间/`。`raw/` 为原始页面；`manifest.json` 为采集清单及失败原因；`processed/documents.csv` 是统一 UTF-8 BOM CSV（空 author/publish_time 表示未知）；JSONL 同步保留便于后续程序读取。`cleaning_audit.json` 记录每条文档的修改计数及具体删除/替换内容；`quality_report.json` 和 `QUALITY_REPORT.md` 从实际 CSV 重新读取并检查，包含缺失率计数、重复、字符变化、启发式乱码检查与清洗前后样例。

Parser 按模板定位标题、元信息和正文；cleaner 只规范实体、异常空白、控制字符、残留标签、独立按钮文字、URL 及相邻长行重复。保留正文顺序和数值，不做语义过滤。乱码只报告，不自动猜测修复。CSV 只含 Document 字段，不含后续实验结构。质量报告不修改 CSV。

批量扩展时应先配置新的站点模板并抽样复核；当前五站入口是小规模测试程序，不具备生产批量调度、断点续采及访问频率管理。

## Document Schema 适配测试

在项目根目录运行 `python -m task1.crawler.test.inspect_sources`，仅获取配置中的五个样本并自动解析。每次独立保存到 `results/schema_时间/`：`raw/` 保存原件，`manifest.json` 保存采集信息，`processed/documents.jsonl` 保存通过校验的 Document，`report.json` 保存逐项提取情况和错误。失败项不生成虚假文档；存在失败时测试退出码为 1。

离线重新解析：`python -m task1.crawler.document_pipeline task1/crawler/results/schema_20261102_204358`。
离线检查：`python -m unittest task1.crawler.test.test_document_pipeline`。

`TemplateParser` 通过模板配置复用于同站点同结构的页面，不按 URL 写独立类。`PdfParser` 是独立的二进制解析接口，文本型 PDF 需要可选轻量依赖 `pypdf`；当前西湖附件返回 404，故 PDF 解析尚未完成实站验证，环境中也未成功安装该依赖。扫描件、缺少可靠标题的 PDF 明确报错，不自动 OCR 或猜测标题。

本阶段沿用 SCHEMA.md 固定枚举 `official_route`，综合导览和咨询页面的类型局限写入 `notes`，不修改 Schema。作者只读取明确作者区域；不将网站名称或正文落款自动当作作者。湖南文章优先读取标题旁显示的发布时间，不把页面生成时间或正文落款日期当作发布时间。动态加载失败不会关闭证书验证或绕过限制。

## 指定公开网站测试及结果归档

测试脚本统一放在 `test/` 目录。运行 `python -m task1.crawler.test.test_public_sites`，依次使用静态和动态采集器测试故宫参观页及张家界线路页。结果保存在本目录的 `results/运行时间/` 下，各站点分别保存 `static.html`、`dynamic.html`；`summary.json` 记录 URL、标题、HTML 字符数、文本预览、耗时和失败原因。HTML 成功返回仅代表采集成功，仍需检查是否为目标内容或网站提示页。保存的 HTML 是页面快照，不包含图片等外部资源。

Python 3.11，使用 conda 环境 `crawlert1`。依赖为 `requests`、`beautifulsoup4`、`playwright`，动态采集需要本机 Google Chrome；无需执行 `playwright install`。

在项目根目录执行：

```powershell
conda activate crawlert1
python -m task1.crawler.test.test_crawler
python -m task1.crawler.test.test_crawler --headed
python -m task1.crawler.test.test_crawler --url https://example.com
```

也可直接运行 `python task1/crawler/test/test_crawler.py` 或 `python task1/crawler/test/test_public_sites.py`。两项测试打印 title 和 HTML 片段；任一失败则退出码为 1。公网测试依赖网络可达性。

```python
from task1.crawler.static_crawler import fetch_html
from task1.crawler.dynamic_crawler import fetch_html as fetch_dynamic

html = fetch_html("https://example.com", headers={"User-Agent": "CourseLab/1.0"}, timeout=15)
html = fetch_dynamic("https://example.com", headless=True, timeout=30000, wait_selector="h1")
```

静态 timeout 单位为秒，动态 timeout 单位为毫秒。动态默认等待 load；这不保证所有异步数据完成，实际页面可传入内容就绪元素的选择器。库只记录日志，由调用方配置日志输出。失败抛出原始 requests / Playwright 异常，不用空字符串掩盖失败。

后续扩展：在 `parsers/` 中新增继承 `BaseParser` 的站点解析器，实现 `parse(html) -> dict`，用 BeautifulSoup 提取景点名、地址、介绍等字段。西湖、故宫等官网优先选用静态采集；实际依赖 JavaScript 的页面使用动态采集。马蜂窝、小红书等需要按可公开访问的页面结构分别实现解析器，结合真实页面确定选择器与就绪条件。调用方组合采集、解析和保存流程，crawler 无需随站点修改。遵守网站访问规则，遇到登录、验证码或访问限制时停止，不绕过限制。
