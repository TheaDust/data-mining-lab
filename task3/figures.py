"""Generate an editable overview from the actual official route hierarchy."""
from xml.etree import ElementTree as ET


def write_hierarchy_diagram(path, officials):
    one_day, multi_day = [r for r in officials if r['scenic_spot'] == '九寨沟'][:2]
    palace = next(r for r in officials if r['scenic_spot'] == '北京故宫')
    lake = next(r for r in officials if r['scenic_spot'] == '杭州西湖')
    graph = ET.Element('mxGraphModel', adaptiveColors='auto', page='1', pageWidth='1780', pageHeight='820')
    root = ET.SubElement(graph, 'root')
    ET.SubElement(root, 'mxCell', id='0')
    ET.SubElement(root, 'mxCell', id='1', parent='0')

    def node(identifier, label, x, y, parent='1', width=140, height=60, style=''):
        cell = ET.SubElement(root, 'mxCell', id=identifier, value=label, vertex='1', parent=parent,
                             style='rounded=1;whiteSpace=wrap;html=1;fontFamily=Microsoft YaHei;fontSize=16;fillColor=#f5f8fc;strokeColor=#7893aa;' + style)
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(width), height=str(height), attrib={'as': 'geometry'})

    def edge(identifier, source, target, parent):
        cell = ET.SubElement(root, 'mxCell', id=identifier, edge='1', source=source, target=target, parent=parent,
                             style='edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#6d8498;endArrow=block;')
        ET.SubElement(cell, 'mxGeometry', relative='1', attrib={'as': 'geometry'})

    node('title', '按原文证据选择路线层级粒度', 40, 15, width=1660, height=50,
         style='shape=text;fillColor=none;strokeColor=none;fontSize=28;fontStyle=1;')
    panels = [('timed', 'A　日内时段明确', '#e5eff8'), ('dated', 'B　日期明确、日内时段未注明', '#e5f3ee'), ('ordered', 'C　仅明确步骤顺序', '#fff1dd')]
    for i, (identifier, title, color) in enumerate(panels):
        node(identifier, title, 20 + i * 580, 90, width=560, height=660,
             style=f'swimlane;startSize=50;rounded=0;fillColor={color};fontSize=20;fontStyle=1;')

    node('timed-route', '九寨沟<br>一日精华游', 220, 80, 'timed')
    node('timed-day', '第 1 天', 220, 200, 'timed')
    edge('timed-root-day', 'timed-route', 'timed-day', 'timed')
    for i, period in enumerate(one_day['hierarchy'][0]['periods']):
        x = 40 + i * 180
        key = f'timed-period-{i}'
        node(key, period['time_period'], x, 320, 'timed')
        node(key + '-steps', f"{len(period['step_ids'])} 个有序步骤", x, 440, 'timed')
        edge(key + '-day', 'timed-day', key, 'timed')
        edge(key + '-sequence', key, key + '-steps', 'timed')
    node('timed-note', '上午 / 中午 / 下午来自原文标题。<br>同一时间窗内的多站共同保留在步骤中。', 30, 550, 'timed', 500, 70, 'shape=text;fillColor=none;strokeColor=none;')

    node('dated-route', '九寨沟<br>二日舒适游', 220, 80, 'dated')
    for i, day in enumerate(multi_day['hierarchy']):
        x = 130 + i * 180
        key = f'dated-day-{i}'
        count = sum(len(p['step_ids']) for p in day['periods'])
        node(key, f"第 {day['day']} 天", x, 200, 'dated')
        node(key + '-period', '时段未注明', x, 320, 'dated')
        node(key + '-steps', f'{count} 个有序步骤', x, 440, 'dated')
        edge(key + '-root', 'dated-route', key, 'dated')
        edge(key + '-unknown', key, key + '-period', 'dated')
        edge(key + '-sequence', key + '-period', key + '-steps', 'dated')
    node('dated-note', 'Day 1 / Day 2 支持相对日期分组。<br>时段缺失不妨碍保留日期与先后关系。', 30, 550, 'dated', 500, 70, 'shape=text;fillColor=none;strokeColor=none;')

    labels = [('route', '故宫 / 西湖路线'), ('day', '日期未注明'), ('period', '时段未注明'), ('steps', '有序步骤序列')]
    for i, (suffix, label) in enumerate(labels):
        node('ordered-' + suffix, label, 220, 80 + i * 120, 'ordered')
        if i:
            edge('ordered-edge-' + suffix, 'ordered-' + labels[i - 1][0], 'ordered-' + suffix, 'ordered')
    node('ordered-note', f"例：故宫路线一 {len(palace['steps'])} 步；西湖十景 {len(lake['steps'])} 步。<br>总时长与步骤顺序分别保存。", 30, 550, 'ordered', 500, 70, 'shape=text;fillColor=none;strokeColor=none;')
    node('legend', '“未注明”对应 JSON 的 null，表示缺失信息；日期与步骤层级已经构建，不代表已补全日内时间。', 40, 765, width=1660, height=45,
         style='shape=text;fillColor=none;strokeColor=none;fontSize=17;')
    # draw.io 只把 <mxfile><diagram> 包裹的文件识别为可打开的图，裸 mxGraphModel 会判为无效。
    body = ET.tostring(graph, encoding='unicode')
    path.write_text(
        '<mxfile host="app.diagrams.net">'
        f'<diagram id="overview" name="路线层级">{body}</diagram>'
        '</mxfile>\n',
        encoding='utf-8')
