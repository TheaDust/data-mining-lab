"""Fill only member C's chapter, reflection slots and contribution row.
Use the bundled document runtime. Preserve all other DOCX package parts.
"""
from pathlib import Path
from io import BytesIO
import re, copy, json, zipfile
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.text.paragraph import Paragraph

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'report/第8组_卢满江_《数据挖掘》探索性实验报告-提交版.docx'
SINGLE=ROOT/'report/房立志_实验7与系统集成.docx'
md=(ROOT/'task7/REPORT.md').read_text()
original=DEST.read_bytes()
backup=Path('/tmp/shanxing-report-original.docx')
if not backup.exists(): backup.write_bytes(original)
doc=Document(BytesIO(original))

def find(text):
    return next(p for p in doc.paragraphs if p.text.strip()==text)

def style_run(run,size=10.5,bold=False):
    run.font.name='宋体'; run.font.size=Pt(size);run.bold=bold;run.font.color.rgb=RGBColor(0,0,0)
    run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'宋体')

def para_before(anchor,text,style='GuideBody',bold=False):
    p=anchor.insert_paragraph_before(style=style)
    style_run(p.add_run(text.replace('`','').replace('**','')),12 if style=='GuideH2' else 10.5,bold or style=='GuideH2')
    p.paragraph_format.widow_control=True
    return p

def table_before(anchor,rows):
    t=doc.add_table(rows=1,cols=len(rows[0])); t.autofit=False
    widths={2:[3.2,11.4],3:[3.4,3.0,8.2]}.get(len(rows[0]),[14.6/len(rows[0])]*len(rows[0]))
    for c,w in zip(t.columns,widths): c.width=Cm(w)
    pr=t._tbl.tblPr
    borders=OxmlElement('w:tblBorders')
    for name in ['top','left','bottom','right','insideH','insideV']:
        b=OxmlElement('w:'+name);b.set(qn('w:val'),'single');b.set(qn('w:sz'),'4');b.set(qn('w:color'),'D9D9D9');borders.append(b)
    pr.append(borders)
    for i,row in enumerate(rows):
        cells=t.rows[0].cells if i==0 else t.add_row().cells
        for j,(cell,text) in enumerate(zip(cells,row)):
            cell.width=Cm(widths[j]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p=cell.paragraphs[0];p.style=doc.styles['GuideBody'];p.paragraph_format.space_after=Pt(4);p.paragraph_format.space_before=Pt(4)
            style_run(p.add_run(text.replace('`','')),9.5,i==0)
            tcpr=cell._tc.get_or_add_tcPr();marg=OxmlElement('w:tcMar')
            for edge in ['top','bottom','left','right']:
                e=OxmlElement('w:'+edge);e.set(qn('w:w'),'90');e.set(qn('w:type'),'dxa');marg.append(e)
            tcpr.append(marg)
            if i==0:
                sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'EDEDED');tcpr.append(sh)
        trpr=t.rows[i]._tr.get_or_add_trPr();trpr.append(OxmlElement('w:cantSplit'))
        if i==0:trpr.append(OxmlElement('w:tblHeader'))
    anchor._p.addprevious(t._tbl)


def blocks(anchor,content):
    lines=content.strip().splitlines();i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                row=[c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch('[: -]+',c) for c in row): rows.append(row)
                i+=1
            table_before(anchor,rows);continue
        if line.startswith('!['):
            path=re.search(r'\]\((.+)\)',line).group(1)
            p=anchor.insert_paragraph_before();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after=Pt(8)
            p.add_run().add_picture(str(ROOT/'task7'/path),width=Cm(14.2))
            i+=1;continue
        if line.startswith('### '):
            p=para_before(anchor,line[4:],bold=True);p.paragraph_format.keep_with_next=True
        else:
            p=para_before(anchor,line)
            if re.match(r'图7-\d',line):p.paragraph_format.keep_with_next=True;p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        i+=1

# Replace only the chapter 7 bodies. The script is rerunnable.
sections=list(re.finditer(r'^## (7\.\d [^\n]+)\n',md,re.M))
summary=find('—实验总结：探索性实验总结反思')
chapter_end=summary._p.getprevious() # repeated report title before summary
for index,m in enumerate(sections):
    heading=find(m.group(1));next_heading=find(sections[index+1].group(1)) if index+1<len(sections) else None
    stop=next_heading._p if next_heading else chapter_end
    e=heading._p.getnext()
    while e is not stop:
        nxt=e.getnext();e.getparent().remove(e);e=nxt
    content=md[m.end():sections[index+1].start() if index+1<len(sections) else md.index('## 总结反思素材')]
    if index==0:
        content='本章负责人为房立志（成员C，学号202430550430），负责Agent设计、图谱查询工具、LLM接入、前后端应用集成、联调及多场景测试。原始数据和实验6图谱由前序实验提供。\n\n'+content
    if index==5:
        content+='\n参考实现：react-force-graph官方directional-links-particles示例，https://github.com/vasturiano/react-force-graph/blob/master/example/directional-links-particles/index.html。模型接口参考DeepSeek官方tool_calls和JSON Output文档。可视化依赖为MIT许可，图谱工具和校验逻辑为本项目实现。\n'
    if next_heading: anchor=next_heading
    else: anchor=Paragraph(chapter_end,heading._parent)
    blocks(anchor,content)

reflection={
'失败现象记录': '成员C负责部分发现三个具体失败现象。第一，最初九寨沟老人场景错误套用了“初入高原”条件，用户并未提供这一事实。第二，250个原步骤只有31个有明确时段，故宫半天示例无法证明满足精确时间预算。第三，最新演示的三条建议经独立复核均为unknown，但自然语言摘要仍残留相关建议，并叙述了未选择的返程步骤。前两项见failure_before_advice_audit.json及图谱统计，第三项见demo_jiuzhaigou.json。',
'失败原因深度分析':'第一项属于模型语义泛化错误，目的地常识被当成用户条件；只检查引用ID存在和引用文字为真，不能推出完整条件成立。第二项是系统性数据缺失，步骤顺序并不能推导移动或停留时长。第三项是生成与审核之间的工程边界缺口：审核修改了结构化advice，摘要却仍是审核前的文本。小样本功能测试只检查部分字段，不能排除这类语义错误。',
'3、改进/优化方案':'第一项已增加独立条件复核，对unknown保守拒绝；第二项当前保留未知时间和衔接提示，后续需要补充可追溯时长区间。第三项仍待实现“先审核、再按审核结果生成摘要”，为每条建议绑定pair_id、每项路线陈述绑定step_id，并增加被过滤建议不得复现在摘要中的测试。验证时固定图谱、用户输入与模型配置，对比是否启用独立复核及审核后摘要生成，分别统计误用率、误拒率和字段与摘要矛盾率，不用一张成功截图替代评估。',
'梳理现有技术方案的局限性':'从成员C的集成结果看，算法层面只从单条已有路线选取步骤，不能证明全局最短、低体力或跨路线衔接；数据层面缺少距离、完整时长与实时通行状态；工程层面缺少账号、多人隔离及生产部署机制；泛化层面只覆盖三个景区，未覆盖新目的地；评价层面只有9个真实功能场景和33项离线程序检查，没有独立人工金标准或实地可执行性验证。图谱粒子展示关系方向，不能作为模型推理正确性或行程优化的证明。',
'选定一个优先突破的技术点，并给出说明':'若继续研究一个学期，优先选择“带不确定性的时间与体力约束规划”。这是当前“带父母、节奏轻松”无法被程序严格验证的核心瓶颈。目标是把模糊偏好转为带数据来源、区间和未知状态的可计算约束，而非仅让模型把现有路线描述得更轻松。',
'突破该技术点的研究思路或实施方案':'第1至4周按景区和来源分层建立独立人工复核集，标注步行与乘车段、时长区间和信息缺失；第5至8周建立区间时间与体力预算模型，缺失连接保留未知；第9至12周固定数据划分与模型版本，对比纯LLM、当前检索校验、增加区间约束三种方案；第13至16周开展人工可执行性评审和误差分析。指标包括必去覆盖率、避开违反率、时间超限率、来源一致性、摘要矛盾率及人工可执行性评分。预期难点是不同人群速度差异与通行变动，应分别报告假设、未知比例和区间结果，避免以平均值掩盖不确定性。'
}
for label,text in reflection.items():
    heading=find(label)
    # Remove only blank paragraphs in the supplied response slot.
    nxt=heading._p.getnext()
    if nxt is not None and nxt.tag==qn('w:p') and ''.join(nxt.itertext()).strip():
        candidate=Paragraph(nxt,heading._parent)
        if candidate.style.name=='GuideBody' and candidate.text==text:
            e=nxt;nxt=nxt.getnext();e.getparent().remove(e)
    while nxt is not None and nxt.tag==qn('w:p') and not ''.join(nxt.itertext()).strip():
        e=nxt;nxt=nxt.getnext();e.getparent().remove(e)
    p=OxmlElement('w:p');heading._p.addnext(p);obj=Paragraph(p,heading._parent);obj.style=doc.styles['GuideBody'];style_run(obj.add_run(text))
# Replace the supplied reflection prompts with concise section headings.
summary_index=next(i for i,p in enumerate(doc.paragraphs) if p.text.strip()=='—实验总结：探索性实验总结反思')
appendix_index=next(i for i,p in enumerate(doc.paragraphs) if p.text.strip()=='附录')
for paragraph in list(doc.paragraphs[summary_index+1:appendix_index]):
    text=paragraph.text.strip()
    if not text:
        paragraph._p.getparent().remove(paragraph._p)
        continue
    if text.startswith('回顾并记录实验过程中'):
        paragraph.text='一 失败现象原因与改进'
    elif text.startswith('你们的整体技术方案'):
        paragraph.text='二 现有局限与研究方案'
    if text in reflection or paragraph.text in {'一 失败现象原因与改进','二 现有局限与研究方案'}:
        paragraph.style=doc.styles['GuideH2']
        paragraph.paragraph_format.line_spacing=1.15
        paragraph.paragraph_format.space_before=Pt(8)
        paragraph.paragraph_format.space_after=Pt(4)
        paragraph.paragraph_format.keep_with_next=True
        pp=paragraph._p.get_or_add_pPr()
        for tag in ['numPr','ind','tabs']:
            existing=pp.find(qn('w:'+tag))
            if existing is not None:pp.remove(existing)
        for run in paragraph.runs:style_run(run,12,True)

# Fill only C's contribution; leave group percentages for members to agree.
row=doc.tables[2].rows[3]
row.cells[0].text='房立志';row.cells[1].text='组员C'
row.cells[2].text='实验7与整体系统集成：Agent及图谱工具、DeepSeek接入、Web界面与图谱动画、联调测试、演示及本章文档。'
for i,cell in enumerate(row.cells[:3]):
    cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for p in cell.paragraphs:
        p.paragraph_format.line_spacing=1.2
        p.paragraph_format.space_before=Pt(4)
        p.paragraph_format.space_after=Pt(4)
        p.paragraph_format.left_indent=Cm(0)
        p.paragraph_format.right_indent=Cm(0)
        p.paragraph_format.first_line_indent=Cm(0)
        for run in p.runs:style_run(run,12 if i<2 else 10.5)

# Save then preserve unchanged ZIP parts exactly.
buffer=BytesIO();doc.save(buffer)
with zipfile.ZipFile(BytesIO(original)) as old,zipfile.ZipFile(buffer) as new:
    output=BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as out:
        for info in old.infolist():
            key=info.filename
            payload=new.read(key) if key in {'word/document.xml','word/_rels/document.xml.rels','[Content_Types].xml'} else old.read(key)
            out.writestr(info,payload)
        for key in new.namelist():
            if key not in old.namelist():out.writestr(key,new.read(key))
    DEST.write_bytes(output.getvalue())
# Standalone member C excerpt, using the same real styles and section geometry.
single=Document(str(DEST));body=single.element.body
paras=single.paragraphs
start=next(p._p for p in paras if p.text.strip()=='—实验项目7 程序性知识应用：旅游规划Agent')
stop=next(p._p for p in paras if p.text.strip()=='附录')
keep=False
for e in list(body):
    if e is start:keep=True
    if e is stop:keep=False
    if not keep and e.tag!=qn('w:sectPr'):body.remove(e)
if 'Title' not in single.styles:
    single.styles.add_style('Title',WD_STYLE_TYPE.PARAGRAPH)
first=single.paragraphs[0];first.style=single.styles['Title'];first.text='房立志 实验7与系统集成';first.paragraph_format.page_break_before=False
for r in first.runs:style_run(r,16,True)
# Remove only the repeated template title immediately before the summary.
for p in list(single.paragraphs):
    if p.text.strip()=='《数据挖掘》探索性实验报告':p._p.getparent().remove(p._p)
single.save(SINGLE)
print(json.dumps({'full_report':str(DEST),'member_report':str(SINGLE),'paragraphs':len(doc.paragraphs)},ensure_ascii=False))
