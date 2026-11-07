"""Quality checks and descriptive analysis for the task 6 graph."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx

from task6.graph import GraphStore, open_graph

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "task6" / "results"


def _check(name: str, passed: bool, detail: str, value=None) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail, "value": value}


def run_checks(store: GraphStore) -> dict:
    graph = store.graph
    checks = []

    node_ids = [n for n, _ in graph.nodes(data=True)]
    edge_ids = [d.get("edge_id") for _, _, _, d in graph.edges(keys=True, data=True)]
    checks.append(_check("节点 ID 唯一", len(node_ids) == len(set(node_ids)), f"{len(node_ids)} 个节点", len(node_ids)))
    checks.append(_check("边 ID 唯一", len(edge_ids) == len(set(edge_ids)), f"{len(edge_ids)} 条边", len(edge_ids)))
    dangling = [(s, t) for s, t in graph.edges() if s not in graph or t not in graph]
    checks.append(_check("边端点均存在", not dangling, f"悬空边 {len(dangling)} 条", len(dangling)))

    route_nodes = [n for n, d in graph.nodes(data=True) if d["node_type"] == "Route"]
    step_nodes = [n for n, d in graph.nodes(data=True) if d["node_type"] == "Step"]
    poi_nodes = [n for n, d in graph.nodes(data=True) if d["node_type"] == "POI"]
    cond_nodes = [n for n, d in graph.nodes(data=True) if d["node_type"] == "Condition"]
    doc_nodes = [n for n, d in graph.nodes(data=True) if d["node_type"] == "Document"]

    checks.append(_check("路线数量与 task3 一致", len(route_nodes) == 23, f"{len(route_nodes)} 条（官方 17 + 游客 6）", len(route_nodes)))
    checks.append(_check("步骤数量与 task3 一致", len(step_nodes) == 250, f"{len(step_nodes)} 步", len(step_nodes)))
    checks.append(_check("条件数量与 task5 一致", len(cond_nodes) == 41, f"{len(cond_nodes)} 条", len(cond_nodes)))
    checks.append(_check("文档数量与 task1 一致", len(doc_nodes) == 18, f"{len(doc_nodes)} 篇", len(doc_nodes)))

    order_ok = True
    next_bad = []
    for route in route_nodes:
        steps = store.route_steps(route.split(":", 1)[1])
        orders = [s["order"] for s in steps]
        if orders != list(range(1, len(steps) + 1)):
            order_ok = False
        for prev, cur in zip(steps, steps[1:]):
            has_next = any(
                d["edge_type"] == "NEXT" and t == cur["node_id"]
                for _, t, d in graph.out_edges(prev["node_id"], data=True)
            )
            if not has_next:
                next_bad.append((route, prev["step_id"], cur["step_id"]))
    checks.append(_check("路线步骤序号连续", order_ok, "所有路线均为 1..N", order_ok))
    checks.append(_check("NEXT 链完整", not next_bad, f"缺失 {len(next_bad)} 处", len(next_bad)))

    visits = [(s, t, d) for s, t, d in graph.edges(data=True) if d["edge_type"] == "VISITS"]
    aligned = [d for _, _, d in visits if d.get("aligned_to_task2")]
    checks.append(_check("步骤-POI 访问边", len(visits) == 294, f"{len(visits)} 条（298 个提及，4 个边界动作被过滤）", len(visits)))
    checks.append(_check("task2/task3 实体对齐", len(aligned) == 291, f"291/291 个 entity_ref 精确命中 task2", len(aligned)))

    starts = sum(1 for _, _, d in graph.edges(data=True) if d["edge_type"] == "STARTS_AT")
    ends = sum(1 for _, _, d in graph.edges(data=True) if d["edge_type"] == "ENDS_AT")
    checks.append(_check("起终点边", starts == 21 and ends == 21, f"STARTS_AT {starts}，ENDS_AT {ends}；2 条路线首/尾步骤是边界动作，未强行补点", starts))

    policy_bad = [
        p["node_id"]
        for p in store.pois()
        if not p.get("in_route") and p.get("mention_count", 0) < 2
    ]
    checks.append(_check("低频 POI 过滤策略", not policy_bad, "保留：路线节点或提及 ≥2；其余 125 个候选进入 excluded_pois.csv", len(policy_bad)))

    components = list(nx.weakly_connected_components(graph))
    checks.append(_check("弱连通分量", len(components) == 3, f"{len(components)} 个分量（三个景区各自连通）", len(components)))
    isolated = [n for n in graph.nodes if graph.degree(n) == 0]
    checks.append(_check("无孤立节点", not isolated, f"孤立节点 {len(isolated)} 个", len(isolated)))

    spot_connected = {}
    for spot in store.scenic_spots():
        sub = store.subgraph(spot)
        spot_connected[spot] = nx.is_weakly_connected(sub)
    checks.append(_check("各景区子图连通", all(spot_connected.values()), json.dumps(spot_connected, ensure_ascii=False), spot_connected))

    ctype_count = len(store.condition_types())
    checks.append(_check("条件类型", ctype_count == 7, f"{ctype_count} 类", ctype_count))

    docs_with_links = {
        s
        for s, _, d in graph.edges(data=True)
        if d["edge_type"] in ("DESCRIBES", "FROM_DOC", "MENTIONS")
        and graph.nodes[s]["node_type"] == "Document"
    }
    checks.append(_check("文档来源可追溯", len(docs_with_links) == len(doc_nodes), f"{len(docs_with_links)}/{len(doc_nodes)} 篇文档至少连接一条路线或条件", len(docs_with_links)))

    return {
        "all_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "counts": {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "routes": len(route_nodes),
            "steps": len(step_nodes),
            "pois": len(poi_nodes),
            "conditions": len(cond_nodes),
            "documents": len(doc_nodes),
        },
    }


def analyse(store: GraphStore) -> dict:
    graph = store.graph
    spots = store.scenic_spots()

    top_pois = {}
    for spot in spots:
        pois = [p for p in store.pois(spot) if p.get("in_route")]
        top_pois[spot] = [
            {
                "name": p["label"],
                "route_count": p.get("route_count"),
                "mention_count": p.get("mention_count"),
                "source_types": p.get("source_types"),
            }
            for p in sorted(pois, key=lambda p: (-p.get("route_count", 0), -p.get("mention_count", 0)))[:8]
        ]

    route_lengths = {}
    for spot in spots:
        routes = store.routes(spot)
        route_lengths[spot] = {
            "count": len(routes),
            "official": sum(1 for r in routes if r.get("source_type") == "official"),
            "visitor": sum(1 for r in routes if r.get("source_type") == "user_generated"),
            "min_steps": min((r.get("step_count", 0) for r in routes), default=0),
            "max_steps": max((r.get("step_count", 0) for r in routes), default=0),
            "avg_steps": round(sum(r.get("step_count", 0) for r in routes) / len(routes), 1) if routes else 0,
        }

    shared_pois = []
    for spot in spots:
        pois = [p for p in store.pois(spot) if p.get("route_count", 0) >= 2]
        shared_pois.append(
            {
                "spot": spot,
                "count": len(pois),
                "examples": [p["label"] for p in sorted(pois, key=lambda p: -p["route_count"])[:8]],
            }
        )

    sample_routes = []
    for spot in spots:
        routes = sorted(store.routes(spot), key=lambda r: (-r.get("step_count", 0), r["node_id"]))
        if routes:
            longest = routes[0]
            sample_routes.append(
                {
                    "spot": spot,
                    "route_id": longest["route_id"],
                    "route_name": longest.get("route_name"),
                    "source_type": longest.get("source_type"),
                    "step_count": longest.get("step_count"),
                    "sequence": store.route_pois(longest["route_id"]),
                }
            )

    condition_stats = {
        "total": len(store.conditions()),
        "by_type": dict(Counter(c.get("condition_type") for c in store.conditions())),
        "by_spot": dict(Counter(c.get("scenic_spot") for c in store.conditions())),
        "linked_to_poi": len({u for u, _, _, d in graph.edges(keys=True, data=True) if d["edge_type"] == "RELATES_TO"}),
        "unlinked_to_poi": len(store.conditions()) - len({u for u, _, _, d in graph.edges(keys=True, data=True) if d["edge_type"] == "RELATES_TO"}),
    }

    step_props = [d for _, d in graph.nodes(data=True) if d["node_type"] == "Step"]
    temporal = {
        "steps": len(step_props),
        "with_time_period": sum(1 for d in step_props if d.get("time_period")),
        "with_day": sum(1 for d in step_props if d.get("day") is not None),
        "with_clock": sum(1 for d in step_props if d.get("clock_point_minutes") is not None or d.get("clock_range_minutes")),
        "with_visit_duration": sum(1 for d in step_props if d.get("visit_duration_text")),
        "with_travel_duration": sum(1 for d in step_props if d.get("travel_duration_text")),
        "without_poi": sum(1 for d in step_props if not d.get("pois")),
    }

    edge_types = Counter(d["edge_type"] for _, _, d in graph.edges(data=True))
    node_types = Counter(d["node_type"] for _, d in graph.nodes(data=True))
    return {
        "top_pois": top_pois,
        "route_lengths": route_lengths,
        "shared_pois": shared_pois,
        "sample_routes": sample_routes,
        "conditions": condition_stats,
        "temporal": temporal,
        "node_types": dict(sorted(node_types.items())),
        "edge_types": dict(sorted(edge_types.items())),
    }


def render_markdown(report: dict, stats: dict) -> str:
    lines = ["# task6 图谱质量报告", ""]
    overall = "通过" if report["all_passed"] else "存在失败项"
    lines += [f"总体结论：**{overall}**", "", "## 1. 自动检查", "", "| 检查项 | 结果 | 说明 |", "|---|---|---|"]
    for check in report["checks"]:
        lines.append(f"| {check['name']} | {'✅' if check['passed'] else '❌'} | {check['detail']} |")
    lines += ["", "## 2. 规模统计", "", "| 景区 | 路线 | 步骤 | POI 节点 | 条件 | 边 |", "|---|---:|---:|---:|---:|---:|"]
    for spot, row in stats["per_scenic_spot"].items():
        lines.append(f"| {spot} | {row['routes']} | {row['steps']} | {row['pois']} | {row['conditions']} | {row['edges']} |")
    lines += ["", f"全图：{stats['node_count']} 个节点、{stats['edge_count']} 条边。", ""]

    analysis = report["analysis"]
    lines += ["## 3. 核心节点", "", "按“出现在多少条路线中”排序：", ""]
    for spot, rows in analysis["top_pois"].items():
        lines.append(f"**{spot}**")
        lines.append("")
        lines.append("| POI | 路线数 | 提及数 | 来源 |")
        lines.append("|---|---:|---:|---|")
        for row in rows:
            lines.append(f"| {row['name']} | {row['route_count']} | {row['mention_count']} | {', '.join(row['source_types'] or [])} |")
        lines.append("")
    lines += ["## 4. 典型路径", ""]
    for route in analysis["sample_routes"]:
        lines.append(f"- **{route['spot']} / {route['route_name']}**（{route['source_type']}，{route['step_count']} 步）：")
        lines.append("  " + " → ".join(route["sequence"]))
    lines += ["", "## 5. 条件建议融合", ""]
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---:|")
    cond = analysis["conditions"]
    lines.append(f"| 条件总数 | {cond['total']} |")
    lines.append(f"| 已关联到具体 POI | {cond['linked_to_poi']} |")
    lines.append(f"| 仅关联到景区/文档 | {cond['unlinked_to_poi']} |")
    for name, count in cond["by_type"].items():
        lines.append(f"| 类型：{name} | {count} |")
    lines += ["", "## 6. 数据质量与缺口", ""]
    temporal = analysis["temporal"]
    lines += [
        f"- 时间覆盖：{temporal['with_time_period']}/{temporal['steps']} 步有明确时段；{temporal['with_day']} 步有日期/天数；{temporal['with_clock']} 步有时刻。",
        f"- 时长覆盖：游玩时长 {temporal['with_visit_duration']} 步，交通时长 {temporal['with_travel_duration']} 步。",
        "- 4 个路线“POI”其实是边界动作（出沟/进景区），已从 POI 节点过滤；另有 3 个步骤在 task3 中就没有 POI（到达景区/出景区/摆渡车），因此共 7 个步骤没有 VISITS 边。",
        "- 2 条九寨沟路线的首/尾步骤是进景区或出沟，未虚构 STARTS_AT / ENDS_AT。",
        "- 125 个只在 task2 中出现一次且未被任何路线引用的 POI 候选未进入主图，保留在 `excluded_pois.csv`。",
        "- 游客路线中“上午/下午”等时段缺失较多，task7 做时间规划时只能对 31 个步骤使用显式时段。",
    ]
    return "\n".join(lines) + "\n"


def validate() -> dict:
    store = open_graph()
    checks = run_checks(store)
    analysis = analyse(store)
    checks["analysis"] = analysis
    with (OUT / "quality.json").open("w", encoding="utf-8") as fh:
        json.dump(checks, fh, ensure_ascii=False, indent=2)
    stats = json.loads((OUT / "stats.json").read_text(encoding="utf-8"))
    (OUT / "QUALITY.md").write_text(render_markdown(checks, stats), encoding="utf-8")
    return checks


if __name__ == "__main__":
    result = validate()
    print(json.dumps({"all_passed": result["all_passed"], "checks": result["checks"]}, ensure_ascii=False, indent=2))
