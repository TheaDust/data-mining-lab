"""Build the multi-source procedural knowledge graph for task 6.

Inputs
------
task1/data/final/documents.jsonl          18 cleaned documents
task2/results/v2/entities.json            1,415 entity mentions
task3/results/{official,visitor}_routes.json  23 routes / 250 steps
task5/results/final_mapping.json          41 condition-advice pairs (optional)

Outputs
-------
task6/results/nodes.csv
task6/results/edges.csv
task6/results/graph.json
task6/results/graph.graphml
task6/results/stats.json
task6/results/excluded_pois.csv
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "task6" / "results"

INPUTS = {
    "documents": ROOT / "task1" / "data" / "final" / "documents.jsonl",
    "entities": ROOT / "task2" / "results" / "v2" / "entities.json",
    "official_routes": ROOT / "task3" / "results" / "official_routes.json",
    "visitor_routes": ROOT / "task3" / "results" / "visitor_routes.json",
    "conditions": ROOT / "task5" / "results" / "final_mapping.json",
}

SPOTS = ("北京故宫", "杭州西湖", "九寨沟")

# Conservative aliases documented by task 3.  Parent/child or theme names are
# never merged (e.g. 故宫 != 北京故宫, 西湖 != 西湖十景).
POI_ALIASES: dict[str, dict[str, str]] = {
    "北京故宫": {},
    "杭州西湖": {},
    "九寨沟": {
        "天鹅湖": "天鹅海",
        "诺日朗中心": "诺日朗中心站",
    },
}

# Route "POIs" that are actually boundary actions rather than scenic spots.
NON_POI_LABELS = {"出沟", "进景区", "出景区", "到达景区"}

# Names that are too generic to be used as a condition -> POI link.
GENERIC_POI_NAMES = {
    "故宫", "紫禁城", "九寨沟", "西湖", "杭州", "北京", "四川", "景区",
    "左线", "右线", "中线", "沟口",
}

# Keyword groups used to normalise the free-text activity of a route step.
ACTIVITY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("游览参观", ("参观", "游览")),
    ("徒步步行", ("徒步", "步行", "漫步", "爬上")),
    ("乘车换乘", ("观光车", "摆渡车", "乘车", "换乘", "换车", "上车", "下车", "驱车", "车")),
    ("乘船", ("坐船", "乘船", "手划船", "手摇船", "游船", "公交船", "登岸", "船")),
    ("用餐休息", ("用餐", "休息", "入住", "吃饭")),
    ("入园检票", ("安检", "检票")),
    ("进出景区", ("出沟", "出景区", "进景区", "到达景区")),
    ("拍照", ("拍照", "拍摄")),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def canon_poi(scenic_spot: str, name: str) -> str:
    name = re.sub(r"\s+", "", name or "")
    return POI_ALIASES.get(scenic_spot, {}).get(name, name)


def activity_categories(raw: str | None) -> list[str]:
    raw = raw or ""
    labels = [label for label, keys in ACTIVITY_RULES if any(k in raw for k in keys)]
    return labels or ["其他"]


class GraphBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.filters = Counter()
        self.alignment = Counter()
        self.poi_stats: dict[tuple[str, str], dict] = {}
        self.route_poi_stats: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"route_ids": set(), "step_ids": set(), "aliases": set()}
        )
        self.condition_poi_links: list[dict] = []
        self.excluded_pois: list[dict] = []

    # ------------------------------------------------------------------ nodes
    def add_node(self, node_id: str, node_type: str, label: str, scenic_spot: str, **props: Any) -> None:
        if node_id in self.nodes:
            raise ValueError(f"duplicate node id: {node_id}")
        self.nodes[node_id] = {
            "node_id": node_id,
            "node_type": node_type,
            "label": label,
            "scenic_spot": scenic_spot,
            "properties": props,
        }

    def add_edge(self, source: str, target: str, edge_type: str, scenic_spot: str, **props: Any) -> None:
        if source not in self.nodes or target not in self.nodes:
            raise ValueError(f"dangling edge {edge_type}: {source} -> {target}")
        self.edges.append(
            {
                "edge_id": f"e{len(self.edges) + 1:06d}",
                "source": source,
                "target": target,
                "edge_type": edge_type,
                "scenic_spot": scenic_spot,
                "properties": props,
            }
        )

    # ------------------------------------------------------------------ build
    def build(self) -> None:
        docs = load_jsonl(INPUTS["documents"])
        entities = load_json(INPUTS["entities"])
        routes = load_json(INPUTS["official_routes"]) + load_json(INPUTS["visitor_routes"])
        conditions = load_json(INPUTS["conditions"])

        docs.sort(key=lambda d: d["doc_id"])
        routes.sort(key=lambda r: r["route_id"])
        conditions.sort(key=lambda c: c["pair_id"])

        self._collect_pois(entities, routes)
        self._add_scenic_spots(routes, docs, conditions)
        self._add_documents(docs)
        self._add_pois()
        self._add_routes_and_steps(routes)
        self._add_conditions(conditions)

    def _collect_pois(self, entities: list[dict], routes: list[dict]) -> None:
        for ent in entities:
            if ent.get("type") != "POI":
                continue
            scenic = ent["scenic_spot"]
            name = canon_poi(scenic, ent["text"])
            if not name:
                continue
            stat = self.poi_stats.setdefault(
                (scenic, name),
                {
                    "mention_count": 0,
                    "doc_ids": set(),
                    "doc_counts": Counter(),
                    "source_types": set(),
                    "raw_forms": set(),
                    "types": Counter(),
                },
            )
            stat["mention_count"] += 1
            stat["doc_ids"].add(ent["doc_id"])
            stat["doc_counts"][ent["doc_id"]] += 1
            stat["source_types"].add(ent.get("source_type"))
            stat["raw_forms"].add(ent["text"])
            stat["types"][ent.get("type")] += 1

        for route in routes:
            scenic = route["scenic_spot"]
            for step in route["steps"]:
                for poi in step.get("pois", []):
                    self.filters["route_poi_mentions"] += 1
                    raw_name = poi.get("name") or poi.get("text") or ""
                    if raw_name in NON_POI_LABELS:
                        self.filters["non_poi_route_labels"] += 1
                        continue
                    name = canon_poi(scenic, raw_name)
                    stats = self.route_poi_stats[(scenic, name)]
                    stats["route_ids"].add(route["route_id"])
                    stats["step_ids"].add(f"{route['route_id']}:{step['step_id']}")
                    if raw_name != name:
                        stats["aliases"].add(raw_name)
                        self.alignment["normalized_route_pois"] += 1

    def _add_scenic_spots(self, routes: list[dict], docs: list[dict], conditions: list[dict]) -> None:
        for spot in SPOTS:
            route_count = sum(1 for r in routes if r["scenic_spot"] == spot)
            doc_count = sum(1 for d in docs if d["scenic_spot"] == spot)
            condition_count = sum(1 for c in conditions if c["scenic_area"] == spot)
            poi_count = sum(1 for (s, _) in self.route_poi_stats if s == spot)
            self.add_node(
                f"spot:{spot}",
                "ScenicSpot",
                spot,
                spot,
                route_count=route_count,
                document_count=doc_count,
                condition_count=condition_count,
                route_poi_count=poi_count,
            )

    def _add_documents(self, docs: list[dict]) -> None:
        for doc in docs:
            self.add_node(
                f"doc:{doc['doc_id']}",
                "Document",
                doc.get("title") or doc["doc_id"],
                doc["scenic_spot"],
                doc_id=doc["doc_id"],
                title=doc.get("title"),
                source_type=doc.get("source_type"),
                text_type=doc.get("text_type"),
                source_name=doc.get("source_name"),
                url=doc.get("url"),
                author=doc.get("author"),
                publish_time=doc.get("publish_time"),
                clean_chars=len(doc.get("clean_text") or ""),
            )

    def _add_pois(self) -> None:
        for (scenic, name), stat in sorted(self.poi_stats.items()):
            route_stat = self.route_poi_stats.get((scenic, name))
            in_route = route_stat is not None
            if not in_route and stat["mention_count"] < 2:
                self.excluded_pois.append(
                    {
                        "scenic_spot": scenic,
                        "name": name,
                        "mention_count": stat["mention_count"],
                        "doc_count": len(stat["doc_ids"]),
                        "reason": "single_mention_without_route_support",
                    }
                )
                self.filters["excluded_low_frequency_pois"] += 1
                continue
            aliases = sorted({a for a in stat["raw_forms"] if a != name})
            if route_stat:
                aliases = sorted(set(aliases) | route_stat["aliases"])
            node_id = f"poi:{scenic}:{name}"
            self.add_node(
                node_id,
                "POI",
                name,
                scenic,
                mention_count=stat["mention_count"],
                document_count=len(stat["doc_ids"]),
                doc_ids=sorted(stat["doc_ids"]),
                source_types=sorted(t for t in stat["source_types"] if t),
                aliases=aliases,
                in_route=in_route,
                route_count=len(route_stat["route_ids"]) if route_stat else 0,
                step_count=len(route_stat["step_ids"]) if route_stat else 0,
                linked_from="task2+task3" if route_stat else "task2",
            )
            for doc_id in sorted(stat["doc_ids"]):
                doc_node = f"doc:{doc_id}"
                if doc_node in self.nodes:
                    self.add_edge(
                        doc_node,
                        node_id,
                        "MENTIONS",
                        scenic,
                        count=stat["doc_counts"][doc_id],
                        source_type=self.nodes[doc_node]["properties"].get("source_type"),
                    )

        # task3 route POIs that never occur in task2 are still first-class nodes.
        for (scenic, name), route_stat in sorted(self.route_poi_stats.items()):
            if (scenic, name) not in self.poi_stats:
                raise ValueError(f"route POI missing task2 mention: {scenic}/{name}")

    def _add_routes_and_steps(self, routes: list[dict]) -> None:
        for route in routes:
            scenic = route["scenic_spot"]
            route_node = f"route:{route['route_id']}"
            self.add_node(
                route_node,
                "Route",
                route.get("route_name") or route["route_id"],
                scenic,
                route_id=route["route_id"],
                route_name=route.get("route_name"),
                route_kind=route.get("route_kind"),
                source_type=route.get("source_type"),
                doc_id=route["doc_id"],
                url=route.get("url"),
                duration_text=route.get("duration_text"),
                step_count=len(route["steps"]),
                components=route.get("components") or [],
                issues=route.get("issues") or [],
            )
            self.add_edge(f"spot:{scenic}", route_node, "HAS_ROUTE", scenic)
            self.add_edge(f"doc:{route['doc_id']}", route_node, "DESCRIBES", scenic)

            steps = sorted(route["steps"], key=lambda s: s["step_id"])
            previous_step = None
            first_poi = None
            last_poi = None
            for order, step in enumerate(steps, start=1):
                step_node = f"step:{route['route_id']}:{step['step_id']}"
                pois = []
                for poi in step.get("pois", []):
                    raw_name = poi.get("name") or poi.get("text") or ""
                    if raw_name in NON_POI_LABELS:
                        continue
                    pois.append(canon_poi(scenic, raw_name))
                categories = activity_categories(step.get("activity"))
                self.add_node(
                    step_node,
                    "Step",
                    f"第{step['step_id']}步 · {'/'.join(pois) if pois else (step.get('activity') or '步骤')}",
                    scenic,
                    step_id=step["step_id"],
                    order=order,
                    route_id=route["route_id"],
                    day=step.get("day"),
                    time_text=step.get("time_text"),
                    time_period=step.get("time_period"),
                    clock_point_minutes=step.get("clock_point_minutes"),
                    clock_range_minutes=step.get("clock_range_minutes"),
                    activity_raw=step.get("activity"),
                    activity_categories=categories,
                    visit_mode=step.get("visit_mode"),
                    poi_order=step.get("poi_order"),
                    pois=pois,
                    evidence_text=(step.get("evidence") or {}).get("text"),
                    visit_duration_text=step.get("visit_duration_text"),
                    travel_duration_text=step.get("travel_duration_text"),
                )
                self.add_edge(route_node, step_node, "HAS_STEP", scenic, order=order)
                if previous_step:
                    self.add_edge(previous_step, step_node, "NEXT", scenic, order=order)
                previous_step = step_node

                for poi_order, (poi, raw_poi) in enumerate(zip(pois, [p for p in step.get("pois", []) if (p.get("name") or p.get("text")) not in NON_POI_LABELS]), start=1):
                    poi_node = f"poi:{scenic}:{poi}"
                    if poi_node not in self.nodes:
                        raise ValueError(f"missing POI node {poi_node}")
                    ref = raw_poi.get("entity_ref")
                    aligned = bool(
                        ref
                        and (route["doc_id"], ref.get("start"), ref.get("end"), ref.get("type"))
                        in self._task2_refs()
                    )
                    if ref:
                        self.alignment["route_poi_entity_refs"] += 1
                        self.alignment["route_poi_entity_refs_aligned" if aligned else "route_poi_entity_refs_broken"] += 1
                    else:
                        self.alignment["route_poi_without_entity_ref"] += 1
                    self.add_edge(
                        step_node,
                        poi_node,
                        "VISITS",
                        scenic,
                        order_in_step=poi_order,
                        poi_order=step.get("poi_order"),
                        aligned_to_task2=aligned,
                        normalized=bool(raw_poi.get("normalized")),
                        raw_text=raw_poi.get("text"),
                    )
                    if poi_order == 1:
                        first_poi = first_poi or poi_node
                    last_poi = poi_node

                for category in categories:
                    activity_node = f"activity:{scenic}:{category}"
                    self._ensure_activity(activity_node, category, scenic)
                    self.add_edge(step_node, activity_node, "HAS_ACTIVITY", scenic, raw=step.get("activity"))

                period = step.get("time_period")
                if period:
                    time_node = f"time:{scenic}:{period}"
                    self._ensure_time(time_node, period, scenic)
                    self.add_edge(step_node, time_node, "AT_TIME", scenic, time_text=step.get("time_text"))

                if step is steps[0] and pois:
                    self.add_edge(route_node, f"poi:{scenic}:{pois[0]}", "STARTS_AT", scenic, step_id=step["step_id"])
                if step is steps[-1] and pois:
                    self.add_edge(route_node, f"poi:{scenic}:{pois[-1]}", "ENDS_AT", scenic, step_id=step["step_id"])

    def _task2_refs(self) -> set[tuple]:
        if not hasattr(self, "_refs_cache"):
            self._refs_cache = {
                (e["doc_id"], e["start"], e["end"], e["type"])
                for e in load_json(INPUTS["entities"])
                if e.get("type") == "POI"
            }
        return self._refs_cache

    def _ensure_activity(self, node_id: str, label: str, scenic: str) -> None:
        if node_id in self.nodes:
            return
        self.add_node(node_id, "Activity", label, scenic, category=label)

    def _ensure_time(self, node_id: str, label: str, scenic: str) -> None:
        if node_id in self.nodes:
            return
        self.add_node(node_id, "TimePeriod", label, scenic, period=label)

    def _add_conditions(self, conditions: list[dict]) -> None:
        for cond in conditions:
            scenic = cond["scenic_area"]
            pair_id = cond["pair_id"]
            node_id = f"condition:{pair_id}"
            self.add_node(
                node_id,
                "Condition",
                cond.get("normalized_condition") or cond.get("condition") or pair_id,
                scenic,
                pair_id=pair_id,
                condition=cond.get("condition"),
                normalized_condition=cond.get("normalized_condition"),
                recommendation=cond.get("recommendation"),
                normalized_recommendation=cond.get("normalized_recommendation"),
                condition_type=cond.get("condition_type"),
                rule=cond.get("rule"),
                source_text=cond.get("source_text"),
                evidence_span=cond.get("evidence_span"),
                doc_id=cond.get("doc_id"),
                url=cond.get("url"),
                extraction_method=cond.get("extraction_method"),
                review_status=cond.get("review_status"),
                audit_candidate=bool(cond.get("audit_candidate")),
                source_count=len(cond.get("sources") or []),
            )
            self.add_edge(f"spot:{scenic}", node_id, "HAS_CONDITION", scenic)
            type_node = f"ctype:{scenic}:{cond.get('condition_type')}"
            if type_node not in self.nodes:
                self.add_node(type_node, "ConditionType", cond.get("condition_type") or "未分类", scenic)
            self.add_edge(node_id, type_node, "HAS_TYPE", scenic)
            doc_node = f"doc:{cond.get('doc_id')}"
            if doc_node in self.nodes:
                self.add_edge(node_id, doc_node, "FROM_DOC", scenic)
            for target, matched, field in self._condition_poi_matches(cond):
                self.add_edge(
                    node_id,
                    target,
                    "RELATES_TO",
                    scenic,
                    matched_text=matched,
                    match_field=field,
                    method="longest_substring",
                )
                self.condition_poi_links.append({"pair_id": pair_id, "poi": matched, "field": field})

    def _condition_poi_matches(self, cond: dict) -> list[tuple[str, str, str]]:
        scenic = cond["scenic_area"]
        candidates = [
            name
            for (s, name) in self.poi_stats
            if s == scenic and len(name) >= 2 and name not in GENERIC_POI_NAMES
        ]
        found: list[tuple[str, str, str]] = []
        used_names: set[str] = set()
        for field, text in (("recommendation", cond.get("recommendation") or ""), ("condition", cond.get("condition") or "")):
            matches = sorted(
                ((name, text.find(name)) for name in candidates if name in text),
                key=lambda item: (-len(item[0]), item[1]),
            )
            occupied: list[tuple[int, int]] = []
            for name, pos in matches:
                if name in used_names:
                    continue
                span = (pos, pos + len(name))
                if any(not (span[1] <= a or span[0] >= b) for a, b in occupied):
                    continue
                node_id = f"poi:{scenic}:{name}"
                if node_id not in self.nodes:
                    continue
                found.append((node_id, name, field))
                used_names.add(name)
                occupied.append(span)
                if len(found) >= 3:
                    return found
        return found

    # ----------------------------------------------------------------- export
    def stats(self) -> dict:
        node_counts = Counter(n["node_type"] for n in self.nodes.values())
        edge_counts = Counter(e["edge_type"] for e in self.edges)
        per_spot = {}
        for spot in SPOTS:
            per_spot[spot] = {
                "nodes": sum(1 for n in self.nodes.values() if n["scenic_spot"] == spot),
                "edges": sum(1 for e in self.edges if e["scenic_spot"] == spot),
                "routes": sum(1 for n in self.nodes.values() if n["node_type"] == "Route" and n["scenic_spot"] == spot),
                "steps": sum(1 for n in self.nodes.values() if n["node_type"] == "Step" and n["scenic_spot"] == spot),
                "pois": sum(1 for n in self.nodes.values() if n["node_type"] == "POI" and n["scenic_spot"] == spot),
                "conditions": sum(1 for n in self.nodes.values() if n["node_type"] == "Condition" and n["scenic_spot"] == spot),
            }
        return {
            "inputs": {str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path) for path in INPUTS.values()},
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "node_types": dict(sorted(node_counts.items())),
            "edge_types": dict(sorted(edge_counts.items())),
            "per_scenic_spot": per_spot,
            "filters": dict(sorted(self.filters.items())),
            "alignment": dict(sorted(self.alignment.items())),
            "excluded_poi_count": len(self.excluded_pois),
            "condition_poi_links": len(self.condition_poi_links),
        }

    def export(self) -> dict:
        OUT.mkdir(parents=True, exist_ok=True)
        nodes = sorted(self.nodes.values(), key=lambda n: n["node_id"])
        edges = sorted(self.edges, key=lambda e: e["edge_id"])
        stats = self.stats()
        metadata = {
            "schema_version": "1.0",
            "source": "task1 documents + task2 entities + task3 routes + task5 conditions",
            "node_types": sorted({n["node_type"] for n in nodes}),
            "edge_types": sorted({e["edge_type"] for e in edges}),
            "counts": {"nodes": len(nodes), "edges": len(edges)},
            "inputs": stats["inputs"],
        }
        payload = {"metadata": metadata, "nodes": nodes, "edges": edges}
        with (OUT / "graph.json").open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        with (OUT / "nodes.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["node_id", "node_type", "label", "scenic_spot", "properties"])
            writer.writeheader()
            for node in nodes:
                writer.writerow({**node, "properties": json.dumps(node["properties"], ensure_ascii=False)})
        with (OUT / "edges.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["edge_id", "source", "target", "edge_type", "scenic_spot", "properties"])
            writer.writeheader()
            for edge in edges:
                writer.writerow({**edge, "properties": json.dumps(edge["properties"], ensure_ascii=False)})
        with (OUT / "stats.json").open("w", encoding="utf-8") as fh:
            json.dump(stats, fh, ensure_ascii=False, indent=2)
        with (OUT / "excluded_pois.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["scenic_spot", "name", "mention_count", "doc_count", "reason"])
            writer.writeheader()
            writer.writerows(sorted(self.excluded_pois, key=lambda x: (x["scenic_spot"], x["name"])))
        self._export_graphml(payload)
        return stats

    def _export_graphml(self, payload: dict) -> None:
        import networkx as nx

        graph = nx.MultiDiGraph()
        for node in payload["nodes"]:
            graph.add_node(
                node["node_id"],
                node_type=node["node_type"],
                label=node["label"],
                scenic_spot=node["scenic_spot"],
                properties=json.dumps(node["properties"], ensure_ascii=False),
            )
        for edge in payload["edges"]:
            graph.add_edge(
                edge["source"],
                edge["target"],
                key=edge["edge_id"],
                edge_type=edge["edge_type"],
                scenic_spot=edge["scenic_spot"],
                properties=json.dumps(edge["properties"], ensure_ascii=False),
            )
        nx.write_graphml(graph, OUT / "graph.graphml")


def build_graph() -> dict:
    builder = GraphBuilder()
    builder.build()
    return builder.export()


if __name__ == "__main__":
    stats = build_graph()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
