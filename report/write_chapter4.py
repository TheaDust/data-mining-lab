"""Fill chapter 4 of the group report from the experiment 4 outputs.

Run from the repository root:

    python -X utf8 report/write_chapter4.py

The script is idempotent: it replaces everything between the 4.1 heading and
the next chapter/first non-GuideBody page break with freshly generated blocks.
It leaves chapters 1-3 and the template sections 5-7 untouched.
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
SUMMARY_PATH = ROOT / "task4/results/summary.json"
EVALUATION_PATH = ROOT / "task4/results/evaluation.json"

HEADINGS = ["4.1 代词检测与待消解样本", "4.2 人工标注真实先行词", "4.3 消解方法与实现", "4.4 消解结果与输出", "4.5 人工核验与评价"]


def find_heading(doc: docx.Document, text: str) -> Paragraph:
    for paragraph in doc.paragraphs:
        if paragraph.text.strip() == text:
            return paragraph
    raise ValueError(f"heading not found: {text}")


def remove_section_content(doc: docx.Document, heading: Paragraph) -> None:
    """Remove placeholder paragraphs until the next heading or page break."""
    element = heading._p.getnext()
    while element is not None:
        next_element = element.getnext()
        if element.tag.endswith("}p"):
            paragraph = Paragraph(element, heading._parent)
            text = paragraph.text.strip()
            style = paragraph.style.name if paragraph.style is not None else ""
            if style == "GuideH2" or text.startswith("《数据挖掘》"):
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
        obj.paragraph_format.space_before = Pt(3)
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
    font_size: float = 10.5,
    keep_together: bool = True,
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
        cant_split = OxmlElement("w:cantSplit")
        tr_pr.append(cant_split)
        if row_index == 0:
            header = OxmlElement("w:tblHeader")
            tr_pr.append(header)
        for col_index, value in enumerate(row_values):
            cell = table.cell(row_index, col_index)
            cell.width = Cm(widths[col_index])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            paragraph.style = doc.styles["GuideBody"]
            paragraph.paragraph_format.space_before = Pt(1)
            paragraph.paragraph_format.space_after = Pt(1)
            if row_index == 0 or (keep_together and row_index < len(rows)):
                paragraph.paragraph_format.keep_with_next = True
            run = paragraph.add_run(str(value))
            run.font.size = Pt(font_size)
            run.bold = row_index == 0
            if col_index > 0 and len(headers) <= 5:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return table._tbl


def build_blocks() -> dict[str, list[tuple]]:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    evaluation = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    detection = summary["detection"]
    resolution = summary["resolution"]

    blocks: dict[str, list[tuple]] = {}

    blocks["4.1 代词检测与待消解样本"] = [
        ("p", "本章的目标是：检测游记中的代词和指示表达，人工标注可核验的先行词，用可解释的规则完成指代消解，并在小样本标注上评价覆盖率与准确率。"),
        ("p", "本实验以项目 1 的 clean_text 为唯一文本基准，使用项目 2 的 V2 实体和项目 3 的路线 POI 作为候选先行词来源。全语料 18 篇文档中 16 篇检测到代词或指示表达，共 162 个提及；其中选取 5 篇游客游记，从这 5 篇的 54 个提及中人工标注 28 条。5 篇样本覆盖三个景区，既有按标题分段的历史叙事，也有箭头路线和口语化攻略，具体分布如表 4-1 所示。"),
        ("caption", "表 4-1 共指消解样本与检测规模"),
        ("table", ["景区", "文档 ID 后缀", "文本特点", "检测提及", "人工标注"], [
            ["北京故宫", "ac13633e", "按“午门｜…”“乾清宫｜…”分节的历史叙事", "16", "13"],
            ["杭州西湖", "6322b1dd", "打卡点位编号与照片机位说明", "9", "4"],
            ["杭州西湖", "ddcb0707", "家庭省力路线，箭头链与坐船建议", "2", "2"],
            ["九寨沟", "653f517e", "一日三沟实测，箭头链和局部路线提醒", "14", "5"],
            ["九寨沟", "aa7e68d6", "按“📍景点”分节的徒步记录", "13", "4"],
            ["合计", "—", "—", "54", "28"],
        ], [2.0, 3.0, 6.1, 1.7, 1.7]),
        ("p", "检测使用正则表达式，按最长表面优先匹配，覆盖人称代词（我、我们、你、你们、他、她、它、他们、她们、它们、自己、大家）、地点代词（这里、这儿、那里、那儿、这边、那边、此处、此地）、指示表达（这、那、这个、那个、这些、那些、这种、那种、这样、那样）和书面指代（此、该、其）。分句使用句末标点、分号和换行。这里没有使用 Jieba 分词：代词是字符级模式，直接使用正则和原文偏移可以保证 clean_text[start:end] 与代词完全一致；分词不会改善这个边界，反而引入词典依赖。所有位置使用 Python Unicode 码点，从 0 开始，左闭右开。"),
        ("p", "检测阶段不是“见代词就收”。程序先排除“其他”“其实”“尤其”“从此”“此时”“该坐”等固定搭配，再把“这次”“这时”“这期间”“这么”等时间或篇章用法排除出实体消解；“这些照片”“这个历史疑案”“这句话”“这种布局”等标为 non_entity，避免强行绑定到最近景点。每个提及以（doc_id, start, end）唯一标识，同一句出现两个“这里”时仍能分别记录。"),
        ("caption", "表 4-2 全语料检测提及的类型与消解状态"),
        ("table", ["类型", "数量", "说明"], [
            ["地点代词 place", "32", "这里、那里、这边、那边等"],
            ["指示代词 demonstrative", "19", "这、那、这个等独立指代"],
            ["指示限定 determiner", "32", "这条路线、这道门、这个机位等"],
            ["第三人称 person_third", "14", "他、她、他们、她们"],
            ["第一人称 person_first", "29", "我、我们、咱们"],
            ["第二人称 person_second", "9", "你、你们"],
            ["泛称/反身", "11", "大家、自己"],
            ["对象 object", "4", "它、它们"],
            ["话语标记 discourse", "12", "这样、那样、这些（无中心词）等"],
        ], [4.2, 2.0, 8.4], False),
        ("p", f"状态方面，162 个提及中 {resolution['resolved']} 个已消解，{resolution['no_antecedent']} 个无明确先行词，{resolution['ambiguous']} 个歧义，{resolution['non_entity']} 个非实体短语，{resolution['out_of_scope']} 个第一/第二人称或泛称不计入实体共指评估。第一/第二人称仍保留在 mentions.json，用于检查检测召回，但不计入后面的准确率。"),
    ]

    blocks["4.2 人工标注真实先行词"] = [
        ("p", "人工标注覆盖 5 篇游记中的 28 个提及，其中 26 个有明确先行词，2 个无明确先行词。标注字段包括 doc_id、pronoun、pronoun_start/end、sentence、antecedent、antecedent_start/end、antecedent_type、status 和标注说明。明确先行词既可以是 POI（午门、柳浪闻莺、诺日朗中心），也可以是路线段（“原始森林 → 芳草海 → 天鹅海”）、路线名（“乌龟潭路线”）或人物名词（“娃”）。"),
        ("caption", "表 4-3 代表性人工标注案例"),
        ("table", ["代词", "语境（截断）", "标注先行词", "类型", "判断依据"], [
            ["这里", "“午门｜溥仪的人生开篇……实则这里是皇家盛典之门”", "午门", "POI", "当前小节标题就是午门"],
            ["这", "“成了这座皇城的主人”", "紫禁城", "POI", "“皇城”是对紫禁城的指称"],
            ["他", "“带娃驻足可以告诉他”", "娃", "人物", "最近明示人物为前文的“娃”"],
            ["这个", "“1️⃣ 柳浪闻莺（p1）这个机位在公园里面”", "柳浪闻莺", "POI", "编号标题下的“这个机位”回指该点位"],
            ["这", "“断桥残雪→……→三潭印月。为什么这条路线全家走都很轻松”", "整条箭头链", "路线段", "“这条路线”回指上一行完整路线"],
            ["这个", "“推荐乌龟潭路线……基本不接这个路线了”", "乌龟潭路线", "路线", "“这个路线”回指前文路线名"],
            ["这", "“天鹅海→箭竹海不建议徒步。我们这段没有走”", "天鹅海→箭竹海", "路线段", "“这段”回指上一句路线段"],
            ["这里", "“⚠️这里特别提醒：天鹅海→箭竹海不建议徒步”", "无", "—", "指下文提醒，是篇章指代，不强行回指"],
            ["这些", "“我拍的这些照片”", "无", "—", "指照片，没有可定位的景点/路线实体"],
        ], [1.4, 5.4, 3.0, 2.1, 2.7], False),
        ("p", "标注遵循四条规则。第一，先行词必须能在原文中定位，位置切片必须与文本一致。第二，标题和小节名可以作为先行词，但标题作用域在新标题处结束，不能把“温馨提示”绑定到前面的展览路线。第三，“这条路线/这一段”优先绑定箭头链或路线名，不绑定外层章节名“右线”。第四，指向下文的“这里特别提醒”、泛指照片或泛称人物的表达标为 no_antecedent，允许系统弃权；不为了凑满准确率而强行补一个先行词。"),
    ]

    blocks["4.3 消解方法与实现"] = [
        ("p", "本实验采用规则消解，不调用 LLM 或神经共指模型。候选先行词来自五类来源：（1）项目 2 的 POI 和 TRANSPORT 实体；（2）以“｜”“📍”、编号或短标题行识别的小节标题；（3）含“→”的路线链，用项目 2 和项目 3 的 POI 词表提取首末节点，得到连续路线段；（4）“POI + 路线”构成的复合路线名，例如“乌龟潭路线”；（5）人物名词词表（孩子、娃、小朋友、老人、家长、作者、同伴、家人）。"),
        ("caption", "表 4-4 指代短语分类与候选约束"),
        ("table", ["表面形式", "识别结果", "候选类型", "例子"], [
            ["这里、那里、这边、那边", "place", "POI / 路线 / 路线段", "“这里”指午门"],
            ["这、那、这个（独立使用）", "demonstrative", "POI / 路线 / 路线段 / 交通", "“这”指自行车"],
            ["这/那 + 量词 + 名词", "determiner", "由中心名词约束", "“这条路线”“这道门”“这个机位”"],
            ["它、它们", "object", "POI / 交通 / 路线段", "“它”指前文对象"],
            ["他、她、他们、她们", "person_third", "人物名词", "“他”指娃"],
            ["我、我们、你、大家、自己", "out_of_scope", "不计入实体共指", "作者自称、读者称呼"],
            ["这样、那样、这些（无名词）", "discourse", "弃权", "“这样刚好走完……”"],
        ], [3.0, 3.0, 4.2, 4.4], False),
        ("p", "中心名词决定候选类型。“路线、线路、线、段、行程、方案”只找路线或路线段；“门、宫、殿、园、海、塔、桥、寺、山、湖、景点、机位、院落、宫殿、城、皇城、围墙”只找 POI；“交通方式、车、船、观光车、自行车、大巴、地铁”只找交通实体；“照片、经验、故事、问题、句话、趣闻、布局、形式、两个”等标为非实体，直接弃权。“这座皇城/这座围墙/这紫禁城”只允许紫禁城、故宫、皇城类候选，避免被更近的宫院标题抢走。"),
        ("p", "候选用统一特征打分：类型兼容是前置条件；候选来源（标题、路线段、路线、实体、人物）、当前小节标题、句距、字符距离、中心名词匹配、路线中心词提示、词频和候选长度分别加权。标题候选只在其小节范围内获得奖励；如果“这里”距离当前标题超过 4 句，标题奖励取消，避免把章节名当成局部地点。“这一段/这条路线”遇到外层“右线”章节名时，取消该章节名奖励，让实际箭头链胜出。中心名词为“皇城/围墙/紫禁城/故宫”时，只保留宫城类候选，即使字符距离较远也接受最近的宫城。"),
        ("p", "无法判断时采用保守策略：候选分数低于 2.0、前两名差距小于 0.35，或“这里”指向两段以前的路线段时，输出 no_antecedent 或 ambiguous，不强行消解。“这里特别提醒：……”被标为无明确先行词，因为“这里”指下文提醒，不是前文实体回指；这是本实验刻意保留的弃权案例。"),
    ]

    blocks["4.4 消解结果与输出"] = [
        ("p", f"全语料共检测 162 个提及，{resolution['resolved']} 个已消解，{resolution['no_antecedent']} 个无明确先行词，{resolution['ambiguous']} 个歧义，{resolution['non_entity']} 个非实体短语，{resolution['out_of_scope']} 个第一/第二人称或泛称不计入实体评估。已消解结果的先行词类型以 POI 为主，另有路线段、路线名、交通方式和人物名词。5 篇标注样本中 54 个提及，28 个进入人工标注，26 个有明确先行词且全部正确消解，2 个无明确先行词且全部正确弃权。"),
        ("caption", "表 4-5 典型消解结果与消解后文本"),
        ("table", ["文档", "原句（截断）", "消解结果"], [
            ["故宫亲子叙事", "“实则这里是皇家盛典之门”", "“实则午门是皇家盛典之门”"],
            ["故宫亲子叙事", "“成了这座皇城的主人”", "“成了紫禁城的主人”"],
            ["故宫亲子叙事", "“带娃驻足可以告诉他”", "“带娃驻足可以告诉娃”"],
            ["西湖打卡攻略", "“这个机位在公园里面”", "“柳浪闻莺在公园里面”"],
            ["西湖家庭路线", "“为什么这条路线全家走都很轻松”", "“为什么断桥残雪→……→三潭印月全家走都很轻松”"],
            ["九寨沟实测", "“我们这段没有走”", "“我们天鹅海→箭竹海没有走”"],
            ["九寨沟徒步", "“对这个感觉一般”", "“对原始森林感觉一般”"],
            ["九寨沟徒步", "“这条的特点是芦苇搭配……”", "“芦苇海的特点是芦苇搭配……”"],
        ], [2.5, 5.8, 6.3]),
        ("p", "消解文本有两个版本。resolved_text 把完整指代短语替换为先行词，例如把“这条路线”整体替换，而不是只替换“这”后留下“条路线”；marked_text 保留原词并插入“〔→先行词〕”，更适合人工核对。逐句结果保存在 resolved_texts.json 的 resolved_sentences 中，每条记录都带原文、替换结果、标记结果和提及 ID。"),
        ("p", "知识三元组采用统一谓词 referred_by_pronoun，例如“午门 —referred_by_pronoun→ 这里”，并附 doc_id、mention_id、原句和置信度。coreferences.json 沿用 SCHEMA.md 第 9 节的 coref_id、doc_id、pronoun、pronoun_start/end、antecedent、antecedent_start/end、method、confidence，并补充 pronoun_type、antecedent_type、sentence、mention_id 等字段，便于下游按 doc_id 和原文位置回查。mentions.json 保留全部检测提及（包括弃权和第一/第二人称），coreferences.json 只保留已消解记录。"),
        ("caption", "表 4-7 实验 4 主要输出文件"),
        ("table", ["文件", "内容"], [
            ["mentions.json", "全部检测提及、候选、状态和分数"],
            ["coreferences.json / .jsonl", "已消解记录，沿用 SCHEMA.md 共指字段"],
            ["resolved_texts.json", "替换文本、标记文本和逐句消解结果"],
            ["triples.json", "先行词—referred_by_pronoun—代词三元组"],
            ["evaluation.json", "28 条人工标注的逐例判断与指标"],
            ["summary.json / QUALITY.md", "输入哈希、统计、校验和已知边界"],
        ], [5.5, 9.1]),
    ]

    blocks["4.5 人工核验与评价"] = [
        ("p", "评价只使用 28 条人工标注，不把规则输出当作 gold。覆盖率 = 已消解且标注为明确的条数 / 明确先行词总数；已消解准确率 = 正确消解条数 / 已消解条数；总体准确率 =（正确消解 + 正确弃权）/ 标注总数。无明确先行词样本：预测为 no_antecedent、ambiguous、non_entity 或 out_of_scope 均算正确弃权；预测出具体先行词算错误消解。"),
        ("caption", "表 4-6 人工标注评价结果"),
        ("table", ["类型", "标注数", "明确先行词", "已消解", "总体准确率"], [
            ["地点代词 place", "11", "10", "10", "100.00%"],
            ["指示限定 determiner", "12", "11", "11", "100.00%"],
            ["指示代词 demonstrative", "4", "4", "4", "100.00%"],
            ["第三人称 person_third", "1", "1", "1", "100.00%"],
            ["合计", "28", "26", "26", "100.00%"],
        ], [4.0, 2.5, 2.7, 2.5, 2.9]),
        ("p", "在 28 条标注上，检测缺失为 0，正确消解 26 条，正确弃权 2 条，覆盖率 100.00%，已消解准确率 100.00%，总体准确率 100.00%。这组数字说明当前规则与这批定向标注一致，不能外推为全语料准确率：标注只有 5 篇游记，规则又是在同一批文本上设计的，没有独立测试集。非标注文本中仍能看到错误或弃权，例如官方指南把故宫拟人化为“她”、把前三殿称为“他们”，以及“这些小院落”这类集合指代；程序对这些情况多数选择弃权或标为歧义，而不是强行绑定最近景点。"),
        ("p", "本实验的失败边界主要有四类。第一，篇章指代和集合指代缺少单数实体先行词，规则只能弃权，例如“这里特别提醒”“这些小院落”。第二，人物代词依赖人物名词词表，历史叙事中的“她/他”可能指人物、机构或拟人化的故宫，当前没有人物姓名识别，容易漏消解。第三，路线段作为先行词时，替换文本可能很长，虽然 marked_text 可读，但自然度不如短实体。第四，规则权重和中心名词表针对本批语料设计，跨景区、跨文体泛化尚未评估；如果文本出现新的指代形式，需要重新标注和调整规则。"),
        ("p", "总体来看，本实验完成了从 162 个提及的检测、28 条人工标注到规则消解与评价的闭环：55 个提及得到消解，28 条标注中 26 条明确先行词全部正确、2 条无明确先行词全部正确弃权。该结果只说明规则与这批定向标注一致，不能替代独立测试集；后续应补充跨文体标注和人物姓名识别。"),
        ("p", "复现命令为：python -X utf8 task4/run.py；测试命令为 python -X utf8 -m unittest discover -s task4/tests -v。运行会重建 task4/results/ 下的逐位置结果、消解文本、三元组、评价和检查摘要。17 项测试覆盖分句位置、最长匹配、固定搭配过滤、同句同形代词、hashtag 过滤、中心名词分类、替换短语边界、标题消解、路线段消解、篇章指代弃权、宫城别名、Unicode 位置和 28 条标注评估。完整字段、规则和已知边界见 task4/README.md。"),
    ]

    return blocks


def main() -> None:
    doc = docx.Document(DOCX_PATH)
    reference_table = doc.tables[4]  # chapter 1 table, custom thin borders
    blocks = build_blocks()

    for heading_text in HEADINGS:
        heading = find_heading(doc, heading_text)
        remove_section_content(doc, heading)
        cursor = heading._p
        for block in blocks[heading_text]:
            kind = block[0]
            if kind == "p":
                cursor = add_paragraph_after(cursor, block[1], doc)
            elif kind == "caption":
                cursor = add_paragraph_after(cursor, block[1], doc, bold=True)
            elif kind == "table":
                if len(block) == 5:
                    _, headers, rows, widths, keep_together = block
                else:
                    _, headers, rows, widths = block
                    keep_together = True
                cursor = add_table_after(
                    cursor, doc, headers, rows, widths, reference_table,
                    keep_together=keep_together,
                )
                # small spacer after the table
                cursor = add_paragraph_after(cursor, "", doc)
            else:
                raise ValueError(f"unknown block type: {kind}")

    # The template uses an empty Normal paragraph containing a page break
    # before every chapter title.  If chapter 4 ends exactly at the page
    # boundary, that break produces an extra blank page.  Replace it with
    # "page break before" on the chapter 5 title.
    paragraphs = doc.paragraphs
    for index, paragraph in enumerate(paragraphs):
        if paragraph.text.strip() == "—实验项目5 条件性游览建议的抽取":
            title = paragraphs[index - 1]
            previous = paragraphs[index - 2]
            if previous.text.strip() == "" and previous.style.name == "Normal":
                previous._p.getparent().remove(previous._p)
            title.paragraph_format.page_break_before = True
            break

    doc.save(DOCX_PATH)
    print(f"updated {DOCX_PATH.name}")


if __name__ == "__main__":
    main()
