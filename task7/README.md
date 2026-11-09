# 山行 景区游览规划应用

成员C负责的实验7与系统集成：React网页 + FastAPI + DeepSeek工具调用 + 实验6知识图谱。支持北京故宫、杭州西湖、九寨沟。图谱数据来自本组上游结果，不重新采集或重跑实验1–6。

## 快速运行

需要Python 3.11+、Node.js 20.19+与npm。在仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r task7/requirements.lock.txt
cp .env.example .env  # 仅首次创建；已有配置时不要覆盖
```

在本机`.env`设置`DEEPSEEK_API_KEY`。`DEEPSEEK_MODEL`默认`deepseek-flash`，`DEEPSEEK_BASE_URL`默认`https://api.deepseek.com`。密钥只在服务端读取，前端没有模型密钥配置项；`.env`被Git忽略。不要把真实凭据写进代码、报告或截图。

```bash
cd task7/web
npm ci
npm run build
cd ../..
bash task7/start.sh
```

浏览器打开 http://127.0.0.1:8000 。退出服务按Ctrl+C；本地服务无需登录。端口冲突时使用`SHANXING_PORT=8001 bash task7/start.sh`。只绑定本机回环地址，本实现未提供公网认证与多用户隔离，不直接绑定0.0.0.0对外发布。

开发时分别运行后端与前端：

```bash
.venv/bin/python -m uvicorn task7.api:app --reload --host 127.0.0.1 --port 8000
# 另一个终端，仓库根目录：
npm --prefix task7/web run dev
```

开发前端访问 http://127.0.0.1:5173 ，`/api`代理到8000。API说明在`/api/docs`。生产静态构建由FastAPI同源提供。

## 使用

1. 首页输入需求或点击一个示例；也可选景区并展开旅行偏好。
2. 信息不足会追问，未覆盖景区或无匹配景点会明确说明。
3. 查看有序行程，点击“查看依据”阅读原文和来源。
4. 在同一对话中说“保留太和殿，不去珍宝馆”，系统继承旧需求并重新检索校验。
5. “查看本次查询记录”展示真实工具参数与结果；“导出结果”下载完整JSON。

浏览器保存最近12段手记（仅当前浏览器）；服务端在`task7/results/runs/sessions.json`保存最多100段会话约束。运行日志也在该目录，均被Git忽略。删除浏览器存储会清除本机界面历史；删除该目录会清除服务端历史与日志。请保留需要交付的演示日志。

## 命令行

```bash
.venv/bin/python -m task7.cli '带老人去九寨沟玩一天，希望轻松一些'
```

## 结构

| 文件 | 用途 |
|---|---|
| `agent.py` | 需求解析、最多8轮工具循环、条件适用性复核、方案校验 |
| `tools.py` | 实验6只读图谱工具、本次请求来源与路线白名单 |
| `models.py` | 约束、工具参数与最终方案的Pydantic Schema |
| `llm.py` | DeepSeek API适配、超时与服务错误处理 |
| `api.py` | 会话、并发限制、NDJSON阶段事件、静态网页 |
| `web/src/` | React交互界面与响应式样式 |
| `tests/` | 明确使用测试替身的离线检查，不冒充真实模型测试 |
| `results/evaluation.json` | 9个真实模型验收场景的输入与结果 |
| `results/demo.json` | 一条真实完整的工具调用与生成结果 |
| `results/failure_before_advice_audit.json` | 初次真实测试的条件误用，保留作失败分析 |
| `figures/` | 浏览器验收截图 |
| `REPORT.md` | 实验7报告正文及反思素材 |

## 输入依赖与约定

读取`task6/graph.py`及`task6/results/graph.json`（583节点、1751边），并按`doc_id`读取`task1/data/final/documents.jsonl`与`task5/results/final_mapping.json`补齐证据。图谱哈希写入每次结果。

路线先检索再读取详情，最终步骤从真实记录构建，保留原路线相对顺序。支持删减步骤；不拼接不同路线。无明确时间保留未知，不伪造经纬度、步行距离、票价或开放时间。条件建议先检索，再由独立的模型请求复核其完整条件；不足以确认适用的建议丢弃。

输出状态：`ready`（通过结构与来源检查）、`clarification`（需要补充）、`no_match`（没有匹配或不覆盖）、`error`（服务失败或校验未通过）。`ready`不代表经过实地验证的可执行行程。

## 验证

```bash
.venv/bin/python -m pytest task7/tests -q
npm --prefix task7/web run build
.venv/bin/python -m task7.evaluate --live  # 真实DeepSeek请求，会产生API费用
```

2026年11月8日完成33项离线测试、9个真实场景的预设断言，以及桌面/390px窄屏浏览器检查。详见结果和报告。这是小规模功能验收，不能解读成总体准确率100%。

## 已知限制

- 250步骤仅31个有明确时段；无法验证精确时间预算、最短步行或无障碍通行。
- 删除步骤不等于证明删减后的交通衔接可行；界面保留这一提示。
- 建议由模型判断语义，可能漏用或误用；独立复核也不是人工金标准。
- 为保守起见，若一个步骤同时含想去与不想去景点，不会自动拆出新的子步骤。
- 历史游记和上游official类别不自动代表最新运营方公告。
- 请求日志含用户需求，保存在本机；不支持账户、多人协作或跨设备同步。
- 模型摘要与推荐理由是生成文本，程序校验保证引用及结构，不保证所有自然语言语义无误。

## 参考与原创实现

界面研究参考JourneyPilot、Travel Copilot；分阶段状态与追问流程参考LangChain旅游示例。这里只借鉴交互和架构思路，当前应用代码、插画SVG、图谱工具与校验逻辑自行实现；不依赖上述项目运行。

- https://github.com/Lagom-TA/JourneyPilot
- https://github.com/ajmudaliar/travel-copilot
- https://github.com/langchain-samples/demos-travel-planner-agent （已归档）
- https://api-docs.deepseek.com/guides/tool_calls/
- https://api-docs.deepseek.com/guides/json_mode/

### 实时图谱网络

采用 [react-force-graph 官方 directional-links-particles 示例](https://github.com/vasturiano/react-force-graph/blob/master/example/directional-links-particles/index.html)的 `react-force-graph-2d`，复用力导向布局、方向粒子及拖动/缩放交互；依赖采用 MIT 许可，保留 npm 包内许可文本。

`GET /api/graph` 导出任务6的583个真实节点、1751条真实关系。规划过程通过 NDJSON `progress`（stage=`graph`）发送真实查询投影：全图 → 目的地 → 已读取路线 → 最终步骤、建议及来源。无关节点渐隐后移出布局，保留节点位置并自动缩放。最终回查来源时可能补入新的证据节点，数量不保证严格递减。粒子仅表示关系方向，不代表模型内部思考或最短路计算。完成后可以收起网络，点击节点可查看名称；尊重系统减少动态效果设置。

故宫图谱验收请求：583 → 138 → 25 → 26 个节点，输出5个行程步骤。最后新增节点来自最终证据集合。验证记录见 `results/graph_qa.json`；当前离线测试33项通过。


## 成员C报告与演示交付

实验7报告正文见 `REPORT.md`，可单独阅读或合入总报告的7.1至7.7节；包含实现、接口、测试、图谱交互、失败分析、复现命令及个人贡献说明。Word版与小组总报告位于仓库的 `report/` 目录。

- `results/demo_jiuzhaigou.json`：最新真实九寨沟演示的输入、约束、工具调用、独立复核和最终输出。
- `videos/山行_九寨沟长辈游_演示.mp4`：1440×900、约54秒的实际运行演示。
- `results/preferences_layout_qa.json`：偏好面板在六种尺寸下无重叠的检查。

最新演示中结构化条件建议均被unknown过滤，但自然语言摘要仍残留被过滤建议，并叙述了未选择的返程步骤。该问题已在报告中如实记录，尚待实现“复核后重新生成摘要”及逐句证据校验；9/9功能断言不能覆盖这一语义漏洞。
