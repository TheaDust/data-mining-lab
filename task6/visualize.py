"""Visualise the task 6 knowledge graph.

Static figures (PNG)
    gugong_route_network.png      故宫 6 条路线 × 26 个路线 POI 的二部图
    jiuzhaigou_route_network.png  九寨沟 5 条路线 × 35 个路线 POI
    gugong_conditions.png         故宫 条件类型 → 条件 → POI 三层图
    graph_overview.png            节点/边类型与景区规模概览

Interactive figures (HTML, self-contained)
    gugong_graph.html
    xihu_graph.html
    jiuzhaigou_graph.html
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from task6.graph import GraphStore, open_graph

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "task6" / "figures"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

TYPE_COLORS = {
    "ScenicSpot": "#2f5597",
    "Route": "#4f81bd",
    "POI": "#70ad47",
    "Step": "#bfbfbf",
    "Activity": "#ffc000",
    "TimePeriod": "#00b0f0",
    "Condition": "#c00000",
    "ConditionType": "#a64d79",
    "Document": "#b4a7d6",
}
EDGE_COLORS = {
    "HAS_ROUTE": "#9dc3e6",
    "HAS_STEP": "#d9d9d9",
    "NEXT": "#bfbfbf",
    "VISITS": "#70ad47",
    "HAS_ACTIVITY": "#ffc000",
    "AT_TIME": "#00b0f0",
    "HAS_CONDITION": "#e6b8b7",
    "HAS_TYPE": "#c9a0c7",
    "RELATES_TO": "#ff6699",
    "STARTS_AT": "#2f5597",
    "ENDS_AT": "#c00000",
    "DESCRIBES": "#b4a7d6",
    "FROM_DOC": "#b4a7d6",
    "MENTIONS": "#e2f0d9",
}


def _route_node_id(route_id: str) -> str:
    return f"route:{route_id}"


def _poi_node_id(spot: str, label: str) -> str:
    return f"poi:{spot}:{label}"


def route_poi_projection(store: GraphStore, spot: str) -> tuple[nx.DiGraph, dict]:
    routes = store.routes(spot)
    routes = sorted(routes, key=lambda r: (r.get("source_type") != "official", r["route_id"]))
    graph = nx.DiGraph()
    orders: dict[tuple[str, str], list[int]] = defaultdict(list)
    poi_mentions = Counter()
    route_steps: dict[str, list[dict]] = {}
    for route in routes:
        rid = route["route_id"]
        rnode = _route_node_id(rid)
        graph.add_node(rnode, kind="route", label=route.get("route_name") or rid, source_type=route.get("source_type"))
        steps = store.route_sequence(rid)
        route_steps[rid] = steps
        for step in steps:
            for poi in step["pois"]:
                pnode = _poi_node_id(spot, poi)
                graph.add_node(pnode, kind="poi", label=poi)
                orders[(rnode, pnode)].append(step["order"])
                poi_mentions[pnode] += 1
                graph.add_edge(rnode, pnode)
    meta = {"orders": orders, "poi_mentions": poi_mentions, "route_steps": route_steps}
    return graph, meta


def plot_route_network(store: GraphStore, spot: str, filename: str) -> Path:
    graph, meta = route_poi_projection(store, spot)
    routes = [n for n, d in graph.nodes(data=True) if d["kind"] == "route"]
    pois = [n for n, d in graph.nodes(data=True) if d["kind"] == "poi"]

    # Vertical order: average normalised step position, then route frequency.
    def poi_key(node: str) -> tuple:
        positions = []
        for route in routes:
            steps = meta["route_steps"][route.split(":", 1)[1]]
            for i, step in enumerate(steps):
                if any(_poi_node_id(spot, p) == node for p in step["pois"]):
                    positions.append(i / max(len(steps) - 1, 1))
        avg = sum(positions) / len(positions) if positions else 0
        return (avg, -graph.degree(node), graph.nodes[node]["label"])

    pois = sorted(pois, key=poi_key)
    pos = {}
    for i, route in enumerate(routes):
        pos[route] = (0.0, 1 - (i / max(len(routes) - 1, 1)))
    for i, poi in enumerate(pois):
        pos[poi] = (1.0, 1 - (i / max(len(pois) - 1, 1)))

    height = max(9.5, 0.42 * len(pois) + 3)
    fig, ax = plt.subplots(figsize=(15, height))
    highlight = routes[0] if routes else None

    for route in routes:
        source_type = graph.nodes[route]["source_type"]
        color = "#c00000" if route == highlight else ("#4f81bd" if source_type == "official" else "#e07b39")
        width = 2.8 if route == highlight else 1.1
        targets = list(graph.successors(route))
        nx.draw_networkx_edges(
            graph,
            pos,
            edgelist=[(route, t) for t in targets],
            ax=ax,
            edge_color=color,
            width=width,
            alpha=0.85 if route == highlight else 0.55,
            arrows=True,
            arrowsize=9,
            connectionstyle="arc3,rad=0.0",
        )
        if route == highlight:
            step_count = len(meta["route_steps"][route.split(":", 1)[1]])
            for target in targets:
                orders = meta["orders"][(route, target)]
                label = ",".join(str(o) for o in orders)
                frac = 0.28 + 0.42 * (sum(orders) / len(orders)) / max(step_count, 1)
                x = pos[route][0] + (pos[target][0] - pos[route][0]) * frac
                y = pos[route][1] + (pos[target][1] - pos[route][1]) * frac
                ax.text(x, y, label, fontsize=7.2, color="#c00000", ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.14", fc="white", ec="none", alpha=0.85))

    top = max((graph.degree(p) for p in pois), default=1)
    for route in routes:
        ax.scatter(*pos[route], s=900, marker="s", color="#4f81bd" if graph.nodes[route]["source_type"] == "official" else "#e07b39",
                   edgecolors="white", linewidths=1.5, zorder=4)
    for poi in pois:
        degree = graph.degree(poi)
        highlight_poi = degree == top and degree >= 3
        ax.scatter(*pos[poi], s=110 + degree * 75, color="#ffc000" if highlight_poi else "#70ad47",
                   edgecolors="#c00000" if highlight_poi else "white", linewidths=1.4, zorder=4)

    for route in routes:
        label = graph.nodes[route]["label"]
        ax.text(-0.04, pos[route][1], label, ha="right", va="center", fontsize=9.5,
                color="#1f3864" if graph.nodes[route]["source_type"] == "official" else "#843c0c")
    for poi in pois:
        degree = graph.degree(poi)
        suffix = f" ×{degree}" if degree >= 3 else ""
        ax.text(1.04, pos[poi][1], graph.nodes[poi]["label"] + suffix, ha="left", va="center",
                fontsize=8.8, color="#1e4620" if degree < top else "#7f6000",
                fontweight="bold" if degree >= 3 else "normal")

    official = sum(1 for r in routes if graph.nodes[r]["source_type"] == "official")
    visitor = len(routes) - official
    ax.set_title(
        f"{spot}游览知识图谱：路线—POI 投影\n"
        f"{len(routes)} 条路线（官方 {official} / 游客 {visitor}）· {len(pois)} 个路线 POI",
        fontsize=15, pad=16,
    )
    ax.set_xlim(-0.45, 1.30)
    ax.set_ylim(-0.04, 1.04)
    ax.axis("off")
    legend = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#4f81bd", markersize=11, label="官方路线"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#e07b39", markersize=11, label="游客路线"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#70ad47", markersize=10, label="POI"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#ffc000", markeredgecolor="#c00000", markersize=12, label="高频 POI（≥3 条路线）"),
        Line2D([0], [0], color="#c00000", lw=2.8, label="高亮路线（数字=访问顺序）"),
    ]
    ax.legend(handles=legend, loc="upper left", bbox_to_anchor=(0.0, -0.012), ncol=3,
              frameon=False, fontsize=9, columnspacing=1.2, handletextpad=0.5)
    fig.subplots_adjust(left=0.31, right=0.80, top=0.90, bottom=0.055)
    out = FIG / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def plot_conditions(store: GraphStore, spot: str, filename: str) -> Path:
    conditions = store.conditions(spot)
    types = sorted({c.get("condition_type") for c in conditions})
    linked = defaultdict(list)
    for cond in conditions:
        for poi in store.condition_pois(cond["pair_id"]):
            linked[cond["pair_id"]].append(poi["label"])
    linked_pois = sorted({p for ps in linked.values() for p in ps})

    graph = nx.DiGraph()
    for ctype in types:
        graph.add_node(f"type:{ctype}", kind="type", label=ctype)
    for cond in conditions:
        graph.add_node(cond["node_id"], kind="condition", label=cond["pair_id"], ctype=cond.get("condition_type"))
        graph.add_edge(f"type:{cond.get('condition_type')}", cond["node_id"])
    for cond in conditions:
        for poi in linked.get(cond["pair_id"], []):
            node = f"poi:{poi}"
            graph.add_node(node, kind="poi", label=poi)
            graph.add_edge(cond["node_id"], node)

    pos = {}
    for i, ctype in enumerate(types):
        pos[f"type:{ctype}"] = (0.0, 1 - i / max(len(types) - 1, 1))
    for i, cond in enumerate(conditions):
        pos[cond["node_id"]] = (0.48, 1 - i / max(len(conditions) - 1, 1))
    for i, poi in enumerate(linked_pois):
        pos[f"poi:{poi}"] = (1.0, 1 - i / max(len(linked_pois) - 1, 1))

    fig, ax = plt.subplots(figsize=(14, max(8, 0.40 * len(conditions) + 2)))
    type_colors = dict(zip(types, ["#2f5597", "#c55a11", "#70ad47", "#7030a0", "#c00000", "#00b0f0", "#7f6000", "#a64d79"]))
    nx.draw_networkx_edges(graph, pos, ax=ax, edge_color=["#c9a0c7" if graph.nodes[u]["kind"] == "type" else "#ffb3c7" for u, v in graph.edges()],
                           width=[1.4 if graph.nodes[u]["kind"] == "type" else 1.6 for u, v in graph.edges()], alpha=0.65,
                           arrows=True, arrowsize=8)
    for kind, color, size, marker in (
        ("type", "#a64d79", 900, "h"),
        ("condition", "#c00000", 180, "D"),
        ("poi", "#70ad47", 260, "o"),
    ):
        nodes = [n for n, d in graph.nodes(data=True) if d["kind"] == kind]
        ax.scatter([pos[n][0] for n in nodes], [pos[n][1] for n in nodes], s=size, marker=marker,
                   color=color, edgecolors="white", linewidths=1.2, zorder=3)
    for n, d in graph.nodes(data=True):
        if d["kind"] == "type":
            ax.text(-0.05, pos[n][1], d["label"], ha="right", va="center", fontsize=11, color="#4b1f4b", fontweight="bold")
        elif d["kind"] == "condition":
            cond = next(c for c in conditions if c["node_id"] == n)
            text = (cond.get("condition") or "")[:14]
            ax.text(0.44, pos[n][1], f"{d['label']} {text}", ha="right", va="center", fontsize=8.2, color="#7f0000")
        else:
            ax.text(1.04, pos[n][1], d["label"], ha="left", va="center", fontsize=9, color="#1e4620")
    linked_count = sum(1 for c in conditions if linked.get(c["pair_id"]))
    ax.set_title(f"{spot}条件性建议子图\n{len(conditions)} 条条件 · {linked_count} 条已链接到具体 POI · {len(types)} 类条件",
                 fontsize=15, pad=14)
    ax.set_xlim(-0.38, 1.32)
    ax.set_ylim(-0.05, 1.05)
    ax.axis("off")
    ax.legend(handles=[
        Line2D([0], [0], marker="h", color="w", markerfacecolor="#a64d79", markersize=12, label="条件类型"),
        Line2D([0], [0], marker="D", color="w", markerfacecolor="#c00000", markersize=8, label="条件（pair_id + 条件文本）"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#70ad47", markersize=9, label="被建议涉及的 POI"),
    ], loc="upper left", bbox_to_anchor=(0.0, -0.012), ncol=3, frameon=False, fontsize=9,
       columnspacing=1.2, handletextpad=0.5)
    fig.subplots_adjust(left=0.30, right=0.82, top=0.90, bottom=0.055)
    out = FIG / filename
    fig.savefig(out, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def plot_overview(store: GraphStore, filename: str = "graph_overview.png") -> Path:
    stats = json.loads((ROOT / "task6" / "results" / "stats.json").read_text(encoding="utf-8"))
    node_types = stats["node_types"]
    edge_types = stats["edge_types"]
    spots = stats["per_scenic_spot"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    ax = axes[0][0]
    names = list(node_types)
    values = [node_types[n] for n in names]
    ax.barh(names, values, color=[TYPE_COLORS.get(n, "#999999") for n in names])
    for y, v in enumerate(values):
        ax.text(v + 3, y, str(v), va="center", fontsize=9)
    ax.set_title("节点类型分布", fontsize=13)
    ax.invert_yaxis()
    ax.set_xlim(0, max(values) * 1.18)

    ax = axes[0][1]
    names = list(edge_types)
    values = [edge_types[n] for n in names]
    ax.barh(names, values, color="#8faadc")
    for y, v in enumerate(values):
        ax.text(v + 3, y, str(v), va="center", fontsize=9)
    ax.set_title("边类型分布", fontsize=13)
    ax.invert_yaxis()
    ax.set_xlim(0, max(values) * 1.18)

    ax = axes[1][0]
    spots_names = list(spots)
    x = range(len(spots_names))
    width = 0.36
    ax.bar([i - width / 2 for i in x], [spots[s]["routes"] for s in spots_names], width, label="路线", color="#4f81bd")
    ax.bar([i + width / 2 for i in x], [spots[s]["conditions"] for s in spots_names], width, label="条件", color="#c00000")
    for i, s in enumerate(spots_names):
        ax.text(i - width / 2, spots[s]["routes"] + 0.3, str(spots[s]["routes"]), ha="center", fontsize=9)
        ax.text(i + width / 2, spots[s]["conditions"] + 0.3, str(spots[s]["conditions"]), ha="center", fontsize=9)
    ax.set_xticks(list(x), spots_names)
    ax.set_title("各景区路线与条件数量", fontsize=13)
    ax.legend(frameon=False)
    ax.set_ylim(0, max(max(spots[s]["routes"], spots[s]["conditions"]) for s in spots_names) * 1.25)

    ax = axes[1][1]
    ax.bar([i - width / 2 for i in x], [spots[s]["steps"] for s in spots_names], width, label="步骤", color="#70ad47")
    ax.bar([i + width / 2 for i in x], [spots[s]["pois"] for s in spots_names], width, label="POI", color="#ffc000")
    for i, s in enumerate(spots_names):
        ax.text(i - width / 2, spots[s]["steps"] + 1.5, str(spots[s]["steps"]), ha="center", fontsize=9)
        ax.text(i + width / 2, spots[s]["pois"] + 1.5, str(spots[s]["pois"]), ha="center", fontsize=9)
    ax.set_xticks(list(x), spots_names)
    ax.set_title("各景区步骤与 POI 节点数量", fontsize=13)
    ax.legend(frameon=False)
    ax.set_ylim(0, max(max(spots[s]["steps"], spots[s]["pois"]) for s in spots_names) * 1.25)

    fig.suptitle(f"task6 知识图谱概览：{stats['node_count']} 个节点 / {stats['edge_count']} 条边", fontsize=15)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = FIG / filename
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def _tooltip(node: dict) -> str:
    keys = [
        "node_type", "label", "scenic_spot", "route_name", "source_type", "route_kind", "step_count",
        "day", "time_text", "activity_raw", "condition", "recommendation", "condition_type",
        "mention_count", "route_count", "source_text", "title",
    ]
    rows = []
    for key in keys:
        value = node.get(key)
        if value in (None, "", [], {}):
            continue
        text = str(value)
        if len(text) > 120:
            text = text[:120] + "…"
        rows.append(f"<tr><td style='color:#666'>{key}</td><td>{text}</td></tr>")
    return f"<div style='max-width:420px'><b>{node['label']}</b><table>{''.join(rows)}</table></div>"


def export_interactive(store: GraphStore, spot: str, filename: str) -> Path:
    """Export a readable route-POI-condition projection with fixed layout."""
    from collections import defaultdict

    from pyvis.network import Network

    routes = store.routes(spot)
    routes = sorted(routes, key=lambda r: (r.get("source_type") != "official", r["route_id"]))
    conditions = store.conditions(spot)
    ctypes = sorted({c.get("condition_type") for c in conditions})

    edge_orders: dict[tuple[str, str], list[int]] = defaultdict(list)
    poi_order_values: dict[str, list[float]] = defaultdict(list)
    for route in routes:
        rid = route["route_id"]
        rnode = _route_node_id(rid)
        steps = store.route_sequence(rid)
        for step in steps:
            for poi in step["pois"]:
                pnode = _poi_node_id(spot, poi)
                edge_orders[(rnode, pnode)].append(step["order"])
                poi_order_values[pnode].append(step["order"] / max(len(steps) - 1, 1))

    condition_pois: dict[str, list[str]] = {}
    for cond in conditions:
        condition_pois[cond["pair_id"]] = [p["label"] for p in store.condition_pois(cond["pair_id"])]

    route_pois = {p for _, p in edge_orders}
    extra_pois = {_poi_node_id(spot, p) for ps in condition_pois.values() for p in ps}
    poi_nodes = sorted(route_pois | extra_pois)

    def poi_y(node: str) -> float:
        values = poi_order_values.get(node)
        if values:
            return sum(values) / len(values)
        return 1.08

    poi_nodes = sorted(poi_nodes, key=lambda n: (poi_y(n), -store.graph.nodes[n].get("route_count", 0), store.graph.nodes[n]["label"]))
    conditions = sorted(conditions, key=lambda c: (c.get("condition_type"), c["pair_id"]))

    net = Network(
        height="1400px",
        width="100%",
        directed=True,
        bgcolor="#ffffff",
        font_color="#222222",
        cdn_resources="in_line",
        heading="",
    )
    net.set_options(
        """
        {
          "physics": {"enabled": false},
          "interaction": {"hover": true, "tooltipDelay": 120, "navigationButtons": true, "zoomView": true, "dragView": true},
          "edges": {"smooth": {"type": "cubicBezier", "forceDirection": "horizontal", "roundness": 0.25}},
          "nodes": {"font": {"face": "Microsoft YaHei"}}
        }
        """
    )

    x_spot, x_route, x_poi, x_cond, x_type = 0, 260, 620, 980, 1240

    def y_pos(index: int, total: int) -> float:
        return 40 + index * (1320 / max(total - 1, 1))

    def add(kind: str, node_id: str, label: str, x: float, y: float, title: str, **attrs) -> None:
        size = {
            "ScenicSpot": 44, "Route": 26, "POI": 18, "Condition": 20, "ConditionType": 24,
        }[kind]
        if kind == "POI":
            size += min(store.graph.nodes[node_id].get("route_count", 0), 6) * 2
        shape = {
            "ScenicSpot": "star", "Route": "square", "POI": "dot",
            "Condition": "diamond", "ConditionType": "hexagon",
        }[kind]
        display_label = label
        label_size = 10 if kind == "POI" else 12
        if kind == "POI":
            attrs = store.graph.nodes[node_id]
            threshold = 3 if len(poi_nodes) > 45 else 2 if len(poi_nodes) > 20 else 0
            if attrs.get("route_count", 0) < threshold:
                display_label = " "
                label_size = 1
        net.add_node(
            node_id,
            label=display_label,
            title=title,
            x=int(x),
            y=int(y),
            physics=False,
            color=TYPE_COLORS[kind],
            shape=shape,
            size=size,
            borderWidth=2 if kind in ("ScenicSpot", "Route") else 1,
            font={
                "size": label_size,
                "face": "Microsoft YaHei",
                "strokeWidth": 3,
                "strokeColor": "#ffffff",
            },
        )

    spot_id = f"spot:{spot}"
    add("ScenicSpot", spot_id, spot, x_spot, 700, f"<b>{spot}</b><br>景区根节点")
    for i, route in enumerate(routes):
        route_node = _route_node_id(route["route_id"])
        add(
            "Route", route_node, route.get("route_name") or route["route_id"],
            x_route, y_pos(i, len(routes)), _tooltip(dict(store.graph.nodes[route_node])),
        )
    for i, node in enumerate(poi_nodes):
        attrs = dict(store.graph.nodes[node], node_id=node)
        add("POI", node, attrs["label"], x_poi, y_pos(i, len(poi_nodes)), _tooltip(attrs))
    for i, cond in enumerate(conditions):
        add("Condition", cond["node_id"], cond["pair_id"], x_cond, y_pos(i, len(conditions)), _tooltip(cond))
    for i, ctype in enumerate(ctypes):
        node_id = f"ctype:{spot}:{ctype}"
        add("ConditionType", node_id, ctype, x_type, y_pos(i, len(ctypes)),
            f"<b>{ctype}</b><br>{sum(1 for c in conditions if c.get('condition_type') == ctype)} 条条件")

    for route in routes:
        rnode = _route_node_id(route["route_id"])
        net.add_edge(spot_id, rnode, color=EDGE_COLORS["HAS_ROUTE"], width=1.6, title="HAS_ROUTE")
        for (source, target), orders in edge_orders.items():
            if source != rnode:
                continue
            net.add_edge(source, target, color=EDGE_COLORS["VISITS"], width=1.4,
                         title=f"VISITS · 访问顺序 {','.join(map(str, orders))}")
    for cond in conditions:
        net.add_edge(spot_id, cond["node_id"], color=EDGE_COLORS["HAS_CONDITION"], width=1.2, title="HAS_CONDITION")
        net.add_edge(cond["node_id"], f"ctype:{spot}:{cond.get('condition_type')}", color=EDGE_COLORS["HAS_TYPE"],
                     width=1.2, title="HAS_TYPE")
        for poi in condition_pois.get(cond["pair_id"], []):
            target = _poi_node_id(spot, poi)
            if target in net.node_ids:
                net.add_edge(cond["node_id"], target, color=EDGE_COLORS["RELATES_TO"], width=1.6,
                             dashes=True, title="RELATES_TO")

    out = FIG / filename
    net.write_html(str(out), notebook=False, open_browser=False)
    html = out.read_text(encoding="utf-8")
    title = f"{spot}知识图谱：路线—POI—条件投影"
    legend = (
        '<div style="padding:0 18px 10px;font:12px/1.9 Microsoft YaHei;color:#333">'
        f'<span style="color:{TYPE_COLORS["ScenicSpot"]}">★ 景区</span>　'
        f'<span style="color:{TYPE_COLORS["Route"]}">■ 路线</span>　'
        f'<span style="color:{TYPE_COLORS["POI"]}">● POI</span>　'
        f'<span style="color:{TYPE_COLORS["Condition"]}">◆ 条件</span>　'
        f'<span style="color:{TYPE_COLORS["ConditionType"]}">⬢ 条件类型</span>　'
        '<span style="color:#70ad47">—— 路线访问 POI</span>　'
        '<span style="color:#ff6699">- - 条件涉及 POI</span>　'
        '<span style="color:#666">拖拽/滚轮缩放，悬停查看属性</span>'
        '</div>'
    )
    header = (
        f'<div style="padding:14px 18px 4px;font:600 22px Microsoft YaHei;color:#1f3864">{title}</div>'
        f'<div style="padding:0 18px 6px;font:13px Microsoft YaHei;color:#666">'
        f'{len(routes)} 条路线 · {len(poi_nodes)} 个 POI · {len(conditions)} 条条件 · 固定分层布局'
        '</div>'
    )
    html = html.replace("<body>", f"<body>{header}{legend}", 1)
    out.write_text(html, encoding="utf-8")
    return out


def visualise(spots: list[str] | None = None) -> list[Path]:
    store = open_graph()
    FIG.mkdir(parents=True, exist_ok=True)
    spots = spots or store.scenic_spots()
    outputs: list[Path] = []
    for spot in spots:
        slug = {"北京故宫": "gugong", "杭州西湖": "xihu", "九寨沟": "jiuzhaigou"}[spot]
        if spot in ("北京故宫", "九寨沟"):
            outputs.append(plot_route_network(store, spot, f"{slug}_route_network.png"))
        if spot == "北京故宫":
            outputs.append(plot_conditions(store, spot, f"{slug}_conditions.png"))
        outputs.append(export_interactive(store, spot, f"{slug}_graph.html"))
    outputs.append(plot_overview(store))
    return outputs


if __name__ == "__main__":
    for path in visualise():
        print(path.relative_to(ROOT))
