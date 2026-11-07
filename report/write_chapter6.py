"""Fill chapter 6 of the group report from the task 6 outputs.

Run from the repository root:

    python -X utf8 report/write_chapter6.py

The script only replaces the bodies of 6.1-6.6.  Chapters 1-5 and the
experiment 7 template are left untouched.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import docx
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.shared import Cm, Pt
from docx.table import Table
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "report"
DOCX_PATH = next(REPORT_DIR.glob("*.docx"))
STATS_PATH = ROOT / "task6" / "results" / "stats.json"
QUALITY_PATH = ROOT / "task6" / "results" / "quality.json"
FIG_DIR = ROOT / "task6" / "figures"

HEADINGS = [
    "6.1 输入关联与融合策略",
    "6.2 对齐样例与噪声诊断",
    "6.3 图谱模式（Schema）设计",
    "6.4 构建实现与结构化输出",
    "6.5 图谱可视化",
    "6.6 质量验证与结果分析",
]


def find_heading(doc: docx.Document, text: str) -> Paragraph:
    for paragraph in doc.paragraphs:
        if paragraph.text.strip() == text:
            return paragraph
    raise ValueError(f"heading not found: {text}")


def remove_section_content(doc: docx.Document, heading: Paragraph) -> None:
    element = heading._p.getnext()
    while element is not None:
        next_element = element.getnext()
        if element.tag.endswith("}p"):
            paragraph = Paragraph(element, heading._parent)
            text = paragraph.text.strip()
            style = paragraph.style.name if paragraph.style is not None else ""
            if style == "GuideH2":
                break
            if style == "Normal" and not text:
                break
            element.getparent().remove(element)
        elif element.tag.endswith("}tbl"):
            element.getparent().remove(element)
        else:
            break
        element = next_element


def add_paragraph_after(cursor, text: str, doc: docx.Document, bold: bool = False, size: float | None = None):
    paragraph = OxmlElement("w:p")
    cursor.addnext(paragraph)
    obj = Paragraph(paragraph, doc.paragraphs[0]._parent)
    obj.style = doc.styles["GuideBody"]
    run = obj.add_run(text)
    run.bold = bold
    if size:
        run.font.size = Pt(size)
    if bold:
        obj.paragraph_format.space_before = Pt(4)
        obj.paragraph_format.space_after = Pt(2)
        obj.paragraph_format.keep_with_next = True
    return paragraph


def add_table_after(
    cursor,
    doc: docx.Document,
    headers: list[str],
    rows: list[list[str]],
    widths: list[float],
    reference_table: Table,
    font_size: float = 9.5,
):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    old_tbl_pr = table._tbl.tblPr
    new_tbl_pr = copy.deepcopy(reference_table._tbl.tblPr)
    table._tbl.replace(old_tbl_pr, new_tbl_pr)
    table.autofit = False
    for col_index, width in enumerate(widths):
        table.columns[col_index].width = Cm(width)
    cursor.addnext(table._tbl)

    for row_index, row_values in enumerate([headers] + rows):
        row = table.rows[row_index]
        tr_pr = row._tr.get_or_add_trPr()
        tr_pr.append(OxmlElement("w:cantSplit"))
        if row_index == 0:
            tr_pr.append(OxmlElement("w:tblHeader"))
        for col_index, value in enumerate(row_values):
            cell = table.cell(row_index, col_index)
            cell.width = Cm(widths[col_index])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            paragraph.style = doc.styles["GuideBody"]
            paragraph.paragraph_format.space_before = Pt(1)
            paragraph.paragraph_format.space_after = Pt(1)
            paragraph.paragraph_format.keep_with_next = row_index == 0
            run = paragraph.add_run(str(value))
            run.font.size = Pt(font_size)
            run.bold = row_index == 0
            if col_index > 0 and len(headers) <= 5:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return table._tbl


def add_picture_after(cursor, doc: docx.Document, path: Path, width_cm: float = 15.8):
    paragraph = OxmlElement("w:p")
    cursor.addnext(paragraph)
    obj = Paragraph(paragraph, doc.paragraphs[0]._parent)
    obj.style = doc.styles["GuideBody"]
    obj.alignment = WD_ALIGN_PARAGRAPH.CENTER
    obj.paragraph_format.space_before = Pt(4)
    obj.paragraph_format.space_after = Pt(2)
    obj.add_run().add_picture(str(path), width=Cm(width_cm))
    return paragraph


def add_caption_after(cursor, doc: docx.Document, text: str, keep_with_next: bool = True):
    paragraph = OxmlElement("w:p")
    cursor.addnext(paragraph)
    obj = Paragraph(paragraph, doc.paragraphs[0]._parent)
    obj.style = doc.styles["GuideBody"]
    obj.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = obj.add_run(text)
    run.font.size = Pt(9.5)
    obj.paragraph_format.space_after = Pt(6)
    obj.paragraph_format.keep_with_next = keep_with_next
    return paragraph


def fill_section(doc: docx.Document, heading_text: str, blocks: list[tuple], reference_table: Table) -> None:
    heading = find_heading(doc, heading_text)
    remove_section_content(doc, heading)
    cursor = heading._p
    for block in blocks:
        kind = block[0]
        if kind == "p":
            cursor = add_paragraph_after(cursor, block[1], doc, bold=block[2] if len(block) > 2 else False)
        elif kind == "table":
            cursor = add_table_after(cursor, doc, block[1], block[2], block[3], reference_table, font_size=block[4] if len(block) > 4 else 9.5)
        elif kind == "cap":
            cursor = add_caption_after(cursor, doc, block[1], keep_with_next=True)
        elif kind == "figcap":
            cursor = add_caption_after(cursor, doc, block[1], keep_with_next=False)
        elif kind == "pic":
            cursor = add_picture_after(cursor, doc, block[1], width_cm=block[2] if len(block) > 2 else 15.8)
        else:
            raise ValueError(kind)


def main() -> None:
    stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    quality = json.loads(QUALITY_PATH.read_text(encoding="utf-8"))
    analysis = quality["analysis"]
    doc = docx.Document(DOCX_PATH)
    reference_table = doc.tables[23]
    counts = stats["node_types"]
    edges = stats["edge_types"]
    spots = stats["per_scenic_spot"]

    # ---------------------------------------------------------------- 6.1
    input_rows = [
        ["task1 文档", "18 篇（官方 3 + 游记 15）", "文档节点、来源追溯"],
        ["task2 实体", "1,415 个（POI 1,112 / TIME 182 / TRANSPORT 121）", "POI 节点、提及频次、跨来源合并"],
        ["task3 官方路线", "17 条 / 185 步", "路线、步骤、POI 顺序"],
        ["task3 游客路线", "6 条 / 65 步", "与官方路线对照"],
        ["task5 条件建议", "41 条 / 7 类", "条件节点、条件—POI 关联"],
    ]
    blocks_61 = [
        ("p", "本章把前五个实验的输出整合成一张可查询、可追溯的景区游览知识图谱。图谱需要同时回答三类问题：景区里有什么、怎么走、在什么条件下怎么选。task5 在任务书中是可选输入；本次 task5 已交付 41 条条件关系，因此一并入图。输入文件与关联键如表 6-1 所示。"),
        ("cap", "表 6-1 图谱输入与用途"),
        ("table", ["输入", "规模", "本章用途"], input_rows, [3.2, 7.6, 5.2]),
        ("p", "关联主键是 task3 为每个路线 POI 保留的 entity_ref：它记录该 POI 在原文中的 (doc_id, start, end, type)。本章用这四元组与 task2 实体精确连接，而不是按名称模糊匹配。298 个路线 POI 提及中，291 个带 entity_ref，291 个全部命中 task2，命中率 100%；3 个没有 entity_ref 的提及按名称归并，4 个边界动作不建 POI 节点。"),
        ("p", "POI 去重按 (景区, 规范化名称) 聚合，规范化只做两件事：去掉空白字符；应用 task3 已记录的保守别名（九寨沟：天鹅湖→天鹅海、诺日朗中心→诺日朗中心站）。没有做“去掉行政前缀”“合并父子景点”等激进归一，避免把“故宫”和“北京故宫”、“西湖”和“西湖十景”错误合并。聚合后得到 215 个 POI 节点，其中 148 个被路线引用、67 个只来自 task2 提及；70 个 POI 同时被官方文档和游客文档提及。"),
        ("p", "节点保留 mention_count、document_count、doc_ids、source_types、aliases、in_route、route_count 等属性；文档到 POI 的 MENTIONS 边按“文档—POI”聚合（436 条），边上保留 count 与 source_type。这样既能追溯来源，也不会让同一文档的重复提及把图撑大。"),
        ("p", "过滤规则有三条：只出现 1 次且未被任何路线引用的 125 个 POI 候选不进入主图，写入 excluded_pois.csv；出沟、进景区等 4 个边界“POI”不建节点；task3 本身没有 POI 的 3 个步骤保留在路线中但不建 VISITS 边。另有两条九寨沟路线首尾是边界动作，因此只有 21 条路线有 STARTS_AT/ENDS_AT，这是有意保留的数据缺口。"),
    ]
    fill_section(doc, HEADINGS[0], blocks_61, reference_table)

    # ---------------------------------------------------------------- 6.2
    align_rows = [
        ["太和殿", "故宫官方路线 / 游客攻略", "task2 实体 + task3 entity_ref", "12 次提及、2 条路线，来源含 official 与 user_generated"],
        ["天鹅湖 → 天鹅海", "九寨沟官方路线", "task3 别名归一", "原文写“天鹅湖”，task3 已归一为“天鹅海”，节点保留别名"],
        ["故宫 ≠ 北京故宫", "跨文档", "不做父子/主题合并", "“故宫”作为泛称保留，不与景区根节点合并"],
        ["出沟 / 进景区", "九寨沟路线", "边界动作过滤", "不建 POI 节点；步骤保留，无 VISITS 边"],
        ["只在游记出现 1 次的餐馆", "task2 候选", "低频过滤", "无路线支持且提及 <2，写入 excluded_pois.csv"],
    ]
    blocks_62 = [
        ("p", "对齐不仅要看“能否连上”，还要看“是否应该连上”。表 6-2 给出本章的代表性正例与反例。正例之所以可靠，是因为 task3 的 entity_ref 直接指向 task2 在原文中的字符区间；反例则说明为什么不能只用名称相等做合并。"),
        ("cap", "表 6-2 实体对齐与噪声处理样例"),
        ("table", ["对象", "来源", "处理", "结果"], align_rows, [3.0, 4.2, 4.4, 4.4]),
        ("p", "噪声诊断的重点不是“删掉看起来不对的东西”，而是把规则和影响说清楚。低频不等于错误：一个只在游记中出现一次的餐馆可能是真实地点，但它没有路线支持，作为景点图谱的主节点会稀释核心结构，因此本章把它留在 excluded_pois.csv 而不是删除。边界动作则是语义错误：出沟、进景区是动作，不是景点，必须从 POI 层过滤，但步骤仍要保留，否则路线顺序会断。"),
        ("p", "对齐后的主要风险是别名漏配和同名异指。本章的别名表只接受 task3 已经验证过的两条，其他一律按原字符串处理；因此“天鹅湖”能被正确合并，但“九寨沟景区门口”和“沟口”仍被视为两个节点。后者是保守策略的代价，会在 6.6 的数据缺口中说明。"),
    ]
    fill_section(doc, HEADINGS[1], blocks_62, reference_table)

    # ---------------------------------------------------------------- 6.3
    node_rows = [
        ["ScenicSpot", str(counts.get("ScenicSpot", 0)), "景区根节点", "route_count、document_count、condition_count"],
        ["POI", str(counts.get("POI", 0)), "规范化景点", "mention_count、route_count、aliases、source_types"],
        ["Route", str(counts.get("Route", 0)), "官方/游客路线", "route_id、route_kind、source_type、step_count"],
        ["Step", str(counts.get("Step", 0)), "路线中的一步", "order、day、time_period、activity_raw、pois"],
        ["Activity", str(counts.get("Activity", 0)), "归一化活动", "category"],
        ["TimePeriod", str(counts.get("TimePeriod", 0)), "时段", "period（上午/中午/下午）"],
        ["Condition", str(counts.get("Condition", 0)), "条件性建议", "pair_id、condition、recommendation、review_status"],
        ["ConditionType", str(counts.get("ConditionType", 0)), "条件类型（按景区实例化）", "label"],
        ["Document", str(counts.get("Document", 0)), "原文档", "title、source_type、text_type、url"],
    ]
    edge_rows = [
        ["HAS_ROUTE", str(edges.get("HAS_ROUTE", 0)), "景区 → 路线", "路线归属"],
        ["HAS_STEP", str(edges.get("HAS_STEP", 0)), "路线 → 步骤", "属性 order"],
        ["NEXT", str(edges.get("NEXT", 0)), "步骤 → 下一步", "路线内顺序链"],
        ["VISITS", str(edges.get("VISITS", 0)), "步骤 → POI", "order_in_step、aligned_to_task2"],
        ["STARTS_AT", str(edges.get("STARTS_AT", 0)), "路线 → POI", "首步 POI"],
        ["ENDS_AT", str(edges.get("ENDS_AT", 0)), "路线 → POI", "末步 POI"],
        ["HAS_ACTIVITY", str(edges.get("HAS_ACTIVITY", 0)), "步骤 → 活动", "一个步骤可多标签"],
        ["AT_TIME", str(edges.get("AT_TIME", 0)), "步骤 → 时段", "仅显式时段"],
        ["HAS_CONDITION", str(edges.get("HAS_CONDITION", 0)), "景区 → 条件", "条件归属"],
        ["HAS_TYPE", str(edges.get("HAS_TYPE", 0)), "条件 → 条件类型", "条件分类"],
        ["RELATES_TO", str(edges.get("RELATES_TO", 0)), "条件 → POI", "matched_text、match_field"],
        ["DESCRIBES", str(edges.get("DESCRIBES", 0)), "文档 → 路线", "路线来源"],
        ["FROM_DOC", str(edges.get("FROM_DOC", 0)), "条件 → 文档", "条件来源"],
        ["MENTIONS", str(edges.get("MENTIONS", 0)), "文档 → POI", "count"],
    ]
    blocks_63 = [
        ("p", "图谱采用带属性的有向多重图（NetworkX MultiDiGraph），节点和边都带 scenic_spot，保证三个景区可以独立取子图。节点类型如表 6-3，边类型如表 6-4。"),
        ("cap", f"表 6-3 节点类型（{stats['node_count']} 个）"),
        ("table", ["节点类型", "数量", "说明", "主要属性"], node_rows, [2.7, 1.4, 5.2, 6.7], 9.0),
        ("cap", f"表 6-4 边类型（{stats['edge_count']} 条）"),
        ("table", ["边类型", "数量", "方向", "说明"], edge_rows, [3.0, 1.4, 5.0, 6.6], 9.0),
        ("p", "Activity 和 ConditionType 按景区实例化（例如“北京故宫/游览参观”与“九寨沟/游览参观”是两个节点），这样每个景区子图都是自包含的；代价是同类节点重复，但换来了清晰的连通分量和更简单的查询。"),
        ("p", "节点 ID 采用可读前缀：spot:北京故宫、poi:北京故宫:午门、route:<route_id>、step:<route_id>:<step_id>、condition:R00008、doc:<doc_id>。一条典型路径在图中表示为：景区 -[HAS_ROUTE]-> 路线 -[HAS_STEP {order:1}]-> 步骤 -[VISITS]-> 午门，步骤再通过 HAS_ACTIVITY 指向“游览参观”。NEXT 保证同一路线内步骤有序，STARTS_AT/ENDS_AT 提供路线首尾的快速入口。"),
    ]
    fill_section(doc, HEADINGS[2], blocks_63, reference_table)

    # ---------------------------------------------------------------- 6.4
    spot_rows = []
    for spot, row in spots.items():
        spot_rows.append([spot, str(row["routes"]), str(row["steps"]), str(row["pois"]), str(row["conditions"]), str(row["edges"])])
    file_rows = [
        ["nodes.csv / edges.csv", "节点表、边表（properties 为 JSON）"],
        ["graph.json", "节点-边 JSON，含 metadata 与输入 SHA-256"],
        ["graph.graphml", "可导入 Gephi / Neo4j"],
        ["stats.json / quality.json", "规模、类型分布、18 项检查"],
        ["QUALITY.md / excluded_pois.csv", "人读质量报告、125 个被过滤候选"],
        ["figures/*.png / *.html", "静态图与自包含交互图"],
    ]
    blocks_64 = [
        ("p", "构图代码在 task6/build.py，查询接口在 task6/graph.py，一键流水线在 task6/run.py。实现上刻意没有引入 Neo4j：当前规模只有 583 个节点、1,751 条边，NetworkX 足够完成构图、查询和导出；graph.graphml 可以在需要时直接导入 Gephi 或 Neo4j，因此提交物不依赖数据库服务，组员和老师可以直接复现。"),
        ("p", "构图流程是：读取 5 个输入文件并计算 SHA-256 → 聚合 task2 POI、按 task3 别名归一 → 过滤低频候选与边界动作 → 建景区、文档、POI 节点 → 按 route_id 排序建路线和步骤，连接 HAS_STEP/NEXT/VISITS → 归一活动、连接时段 → 建条件、条件类型、RELATES_TO → 导出 CSV/JSON/GraphML → 运行质量检查 → 生成可视化。节点和边输出前按 ID 排序，保证同一输入得到同一份文件。"),
        ("cap", "表 6-5 各景区图谱规模"),
        ("table", ["景区", "路线", "步骤", "POI", "条件", "边"], spot_rows, [3.4, 2.2, 2.2, 2.6, 2.4, 2.6]),
        ("cap", "表 6-6 主要结构化输出"),
        ("table", ["文件", "内容"], file_rows, [6.0, 10.0]),
        ("p", "运行方式：python -m task6.run 执行构图、18 项检查和可视化；python -m task6.run --skip-viz 只构图与检查；python -m unittest discover -s task6/tests -v 运行 13 项单元测试。查询接口提供 routes、route_sequence、route_pois、routes_through_poi、conditions、find_poi、subgraph 等方法，task7 直接调用这些方法，而不是把图谱内容写进 Prompt。"),
        ("p", f"构建结果：{stats['node_count']} 个节点、{stats['edge_count']} 条边；其中 POI {counts.get('POI', 0)} 个、Step {counts.get('Step', 0)} 个、Condition {counts.get('Condition', 0)} 条、Document {counts.get('Document', 0)} 篇。三个景区子图各自连通，弱连通分量为 3，孤立节点为 0。"),
    ]
    fill_section(doc, HEADINGS[3], blocks_64, reference_table)

    # ---------------------------------------------------------------- 6.5
    blocks_65 = [
        ("p", "可视化分两层：静态图用于报告与答辩，交互图用于探索和查询演示。静态图由 matplotlib 生成，节点颜色区分景区、路线、POI、条件与条件类型；交互图由 PyVis 生成，是自包含 HTML，不依赖外部 CDN。"),
        ("p", "图 6-1 给出总体规模：节点类型以 POI（215）和 Step（250）为主，边类型以 MENTIONS（436）、VISITS（294）、HAS_ACTIVITY（272）、HAS_STEP（250）为主；三个景区中，西湖的路线（12）和 POI（111）最多，故宫的条件（18）最多。"),
        ("pic", FIG_DIR / "graph_overview.png", 15.5),
        ("figcap", "图 6-1 task6 知识图谱总体规模"),
        ("p", "图 6-2 是故宫的路线—POI 投影。左侧 6 个方块是路线（官方 4、游客 2），右侧 26 个圆点是路线 POI；边上的数字是访问顺序，红色加粗的是路线一（午门 → 太和殿 → 中和殿 → 保和殿 → 乾清宫 → 交泰殿 → 坤宁宫 → 御花园 → 神武门）。黄色大圆点是出现在 ≥3 条路线中的高频 POI：午门、乾清宫、御花园、神武门。该图能直接看出中轴线是多条路线的共同骨架，珍宝馆、钟表馆只出现在部分路线，属于可选支线。"),
        ("pic", FIG_DIR / "gugong_route_network.png", 13.0),
        ("figcap", "图 6-2 北京故宫路线—POI 网络（红色为路线一）"),
        ("p", "图 6-3 是故宫条件子图：左侧 7 个条件类型，中间 18 条条件，右侧被建议涉及的 9 个 POI。时间约束和游客类型是故宫最主要的条件类型，条件建议集中指向午门、神武门、珍宝馆等关键节点。九寨沟的对应静态图保存在 figures/jiuzhaigou_route_network.png（5 条路线、33 个路线 POI）；九寨沟的高频 POI 更多，说明官方一日/二日/三日路线与游客实际路线在核心景点上高度重合，差异主要在顺序和交通方式。"),
        ("pic", FIG_DIR / "gugong_conditions.png", 14.0),
        ("figcap", "图 6-3 北京故宫条件性建议子图"),
        ("p", "交互图（figures/gugong_graph.html、xihu_graph.html、jiuzhaigou_graph.html）采用固定分层布局（景区 → 路线 → POI → 条件 → 条件类型），缩放、拖拽即可查看；悬停节点会显示类型、名称、提及次数、路线数、条件文本等属性。为避免密集景区标签重叠，交互图只标注高频 POI，其余节点悬停可见。"),
    ]
    fill_section(doc, HEADINGS[4], blocks_65, reference_table)

    # ---------------------------------------------------------------- 6.6
    check_rows = [
        ["节点/边 ID 唯一", "583 节点、1,751 边，无重复"],
        ["边端点存在", "悬空边 0"],
        ["路线/步骤数量", "23 条 / 250 步，与 task3 一致"],
        ["步骤序号连续、NEXT 完整", "每条路线 1..N；NEXT 缺失 0"],
        ["步骤—POI 访问边", "294 条（298 提及，4 个边界动作被过滤）"],
        ["task2/task3 对齐", "291/291 个 entity_ref 精确命中"],
        ["POI 过滤策略", "无“单次提及且无路线”的节点"],
        ["弱连通分量 / 孤立节点", "3 个 / 0 个"],
        ["各景区子图连通", "北京故宫、杭州西湖、九寨沟均为 True"],
        ["条件类型/数量", "41 条、7 类"],
        ["文档可追溯", "18/18 篇至少连接一条路线或条件"],
    ]
    core_rows = [
        ["北京故宫", "御花园", "5", "16"],
        ["北京故宫", "午门", "3", "22"],
        ["北京故宫", "神武门", "3", "18"],
        ["杭州西湖", "柳浪闻莺", "3", "12"],
        ["杭州西湖", "三潭印月", "3", "10"],
        ["杭州西湖", "花港观鱼", "3", "10"],
        ["九寨沟", "原始森林", "5", "22"],
        ["九寨沟", "箭竹海", "5", "18"],
        ["九寨沟", "五彩池", "5", "17"],
        ["九寨沟", "五花海", "5", "16"],
    ]
    temporal = analysis["temporal"]
    cond = analysis["conditions"]
    blocks_66 = [
        ("p", f"质量检查在 task6/validate.py 中实现，共 18 项，全部通过（results/quality.json）。表 6-7 列出关键检查项。"),
        ("cap", "表 6-7 关键质量检查"),
        ("table", ["检查项", "结果"], check_rows, [6.0, 10.0]),
        ("p", "按“出现在多少条路线中”排序，各景区核心 POI 如表 6-8。它们共同的特点是路线覆盖广、文档提及多，既是路线规划的必经点，也是游记叙事的重点，适合作为 task7 路线推荐时的锚点。"),
        ("cap", "表 6-8 核心 POI（部分）"),
        ("table", ["景区", "POI", "路线数", "提及数"], core_rows, [4.0, 6.0, 3.0, 3.0]),
        ("p", "典型路径方面，故宫路线一可以还原为：午门 → 太和殿 → 中和殿 → 保和殿 → 乾清宫 → 交泰殿 → 坤宁宫 → 御花园 → 神武门。九寨沟最长路线（三日多彩游，30 步）覆盖从县城、神仙池、漳扎镇到沟内三条沟的主要景点，并在第二天、第三天重复经过诺日朗中心站、犀牛海、树正瀑布等换乘/核心节点；这说明“重复访问”是真实路线的一部分，图谱用 NEXT 链和重复的 VISITS 边保留，而不是去重成一条简单路径。"),
        ("p", f"数据缺口必须明确：250 个步骤中只有 {temporal['with_time_period']} 个有显式时段、{temporal['with_day']} 个有日期/天数、{temporal['with_clock']} 个有时刻，219 个步骤没有时段；只有 {temporal['with_visit_duration']} 个步骤有游玩时长、{temporal['with_travel_duration']} 个有交通时长。task7 不能把“没有时段”默认为上午或下午，只能作为未知处理。"),
        ("p", f"条件融合方面，{cond['total']} 条条件中 {cond['linked_to_poi']} 条链接到具体 POI，{cond['unlinked_to_poi']} 条只到景区/文档级；共生成 {stats['condition_poi_links']} 条 RELATES_TO 边。字符串匹配可能漏掉“这里”“那边”等指代，也可能把泛称误链；边上的 matched_text 和 match_field 用于复核。task5 的 review_status 仍是“待真实人工确认”，图谱不把它当金标准。"),
        ("p", f"此外，{temporal['without_poi']} 个步骤没有 POI（4 个边界动作 + 3 个 task3 本身无 POI 的步骤），2 条九寨沟路线首尾是边界动作、没有起终点边；task2 的 TIME/TRANSPORT 实体没有单独建节点，只用于统计与活动归一。这些缺口会在第 7 章 Agent 的设计中显式处理：Agent 只能查询图上已有的关系，缺失信息应回答“未知”或给出保守建议，而不是让语言模型补全。"),
        ("p", "总体来看，本章把 task1–task5 的输出融合为 583 个节点、1,751 条边的可查询图谱：291 个 task3 实体引用全部对齐 task2，三个景区子图各自连通，18 项自动检查全部通过，并给出了静态图与可交互的分层图。图谱的边界同样明确：时间与时长覆盖不足、条件链接依赖字符串匹配、task5 尚未完成真实人工确认；这些边界将直接约束第 7 章 Agent 的回答范围。"),
    ]
    fill_section(doc, HEADINGS[5], blocks_66, reference_table)

    doc.save(DOCX_PATH)
    print(f"chapter 6 written: {DOCX_PATH}")
    print(f"nodes={stats['node_count']} edges={stats['edge_count']} checks={len(quality['checks'])}")


if __name__ == "__main__":
    main()
