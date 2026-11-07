# 实验5：条件性游览建议抽取

输入：`../task1/data/final/documents.jsonl` 的 `clean_text`；不修改上游数据。正式任务书位于 `../files/数据挖掘_探索性实验任务书.md`。报告模板仅用于读取章结构，未覆盖。面向课程报告与人工审核，关系是预测结果，全部待独立人工确认。

## 运行

从仓库根目录，在 Python 3.12+ 环境执行：

```powershell
python -m pip install -r task5/requirements.txt
python task5/run.py --smoke
python task5/run.py
node task5/export.mjs
python task5/analyze.py
```

本次运行 Python 为 `D:/app_install/Python/python.exe`。由于默认临时目录安装失败，实际依赖安装到 task5/.deps（已忽略），analyze.py 自动加载该目录；其他环境正常安装 requirements.txt 即可。联网仅 run.py 需要，统计与导出不调用模型。

模型配置复用 task2/config.json，凭据从环境变量 DEEPSEEK_API_KEY 或仓库根 .env 读取，读取逻辑复用 task2/run.py 的 key()。地址为 https://api.deepseek.com/chat/completions。不要提交 .env。缓存键覆盖完整请求与Prompt；已有缓存直接重放。删除相应缓存才会重新请求，可能产生费用。失败批次列在 summary.json，失败时不可把输出视为完整实验。

Excel使用 Node 的 `@oai/artifact-tool`。export.mjs 默认引用本机 bundled runtime 的公开入口，可通过 ARTIFACT_TOOL_ENTRY 指定其他安装位置的 dist/artifact_tool.mjs。若宿主禁止junction，直接入口导入可运行。若原生渲染使Node非零退出，先检查 xlsx 是否已保存；Python验收会独立读取Excel确认行数，不将渲染成功等同于导出成功。中文绘图默认微软雅黑 C:/Windows/Fonts/msyh.ttc，其他系统请替换为已安装的中文字体。

## 产物与口径

- `results/raw_pairs.json`：未经校验的原始模型关系，关联 cache_id。
- `results/cache/`：真实响应、模型、参数、usage与重试次数，不含密钥。
- `results/validated_pairs.json`：程序证据/边界过滤后结果。
- `results/final_mapping.json`、`final_mapping.xlsx`：规范化去重关系。sources是合并前全部来源，不能只看主记录来源。
- `results/candidates.json`、`all_windows.json`、`negative_audit.json`：候选及规则外抽查范围。
- `results/rejected_pairs.json`、`near_duplicate_review.json`、`dedup_log.json`：隔离与去重痕迹。
- `results/human_review.csv`、`human_review.json`、Excel人工审核页：分层审核模板，无人工完成记录；填写时保留原预测及ID，修改单独写入human字段。
- `results/summary.json`、`run_log.json`、`automatic_checks.json`、`acceptance.json`：数量、调用与验收记录。
- `results/*counts.csv`、`condition_types.png`、`scenic_comparison.png`：统计数据及图5-1、5-2。
- `REPORT.md`：5.1–5.5可直接整理的真实实验素材。
- `baseline/`、`prompt_v1.txt`：保留初轮实际运行，方便对照。其 raw_pairs 引用 baseline/cache。

窗口重叠导致初始预测重复；去重以景区、规范化条件和建议共同判等。语义近重复保守保留待审。未命中窗口抽查不代表全语料召回评估；无独立人工金标准，不计算人工Precision、Recall、F1。报告案例以当次pair_id定位，跨版本请使用doc_id与offsets定位。

本次验收命令为 `python task5/analyze.py`，重新读取JSON、Excel、源文字符偏移、PNG并核对统计。批量主程序已通过缓存重放，无需重复联网。
