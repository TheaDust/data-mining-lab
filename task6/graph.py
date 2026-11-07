"""Read-only query interface for the task 6 knowledge graph.

Task 7 must call this module instead of embedding graph facts in a prompt.
The store loads ``task6/results/graph.json`` once and exposes small, typed
query helpers over a NetworkX MultiDiGraph.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAPH = ROOT / "task6" / "results" / "graph.json"


class GraphStore:
    def __init__(self, path: str | Path = DEFAULT_GRAPH) -> None:
        self.path = Path(path)
        with self.path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        self.metadata: dict = payload.get("metadata", {})
        self.graph = nx.MultiDiGraph()
        for node in payload["nodes"]:
            attrs = dict(node.get("properties") or {})
            attrs.update(
                node_id=node["node_id"],
                node_type=node["node_type"],
                label=node["label"],
                scenic_spot=node["scenic_spot"],
            )
            self.graph.add_node(node["node_id"], **attrs)
        for edge in payload["edges"]:
            attrs = dict(edge.get("properties") or {})
            attrs.update(
                edge_id=edge["edge_id"],
                edge_type=edge["edge_type"],
                scenic_spot=edge["scenic_spot"],
            )
            self.graph.add_edge(edge["source"], edge["target"], key=edge["edge_id"], **attrs)
        self._index()

    # ------------------------------------------------------------------ index
    def _index(self) -> None:
        self._by_type: dict[str, list[str]] = {}
        self._by_label: dict[str, list[str]] = {}
        for node_id, attrs in self.graph.nodes(data=True):
            self._by_type.setdefault(attrs["node_type"], []).append(node_id)
            self._by_label.setdefault(attrs["label"], []).append(node_id)
        self._route_steps: dict[str, list[str]] = {}
        for route_id in self._by_type.get("Route", []):
            steps = [
                target
                for _, target, data in self.graph.out_edges(route_id, data=True)
                if data["edge_type"] == "HAS_STEP"
            ]
            self._route_steps[route_id] = sorted(
                steps,
                key=lambda step: self.graph.nodes[step].get("order", 10**6),
            )

    # ------------------------------------------------------------------ nodes
    def node(self, node_id: str) -> dict:
        if node_id not in self.graph:
            raise KeyError(node_id)
        return dict(self.graph.nodes[node_id], node_id=node_id)

    def nodes_of_type(self, node_type: str, scenic_spot: str | None = None) -> list[dict]:
        result = []
        for node_id in self._by_type.get(node_type, []):
            attrs = self.graph.nodes[node_id]
            if scenic_spot is None or attrs.get("scenic_spot") == scenic_spot:
                result.append(dict(attrs, node_id=node_id))
        return result

    def scenic_spots(self) -> list[str]:
        return sorted(
            attrs["label"]
            for _, attrs in self.graph.nodes(data=True)
            if attrs["node_type"] == "ScenicSpot"
        )

    def find_poi(self, name: str, scenic_spot: str | None = None) -> str:
        """Resolve a POI name or a recorded alias to a node id."""
        candidates = []
        for node_id, attrs in self.graph.nodes(data=True):
            if attrs["node_type"] != "POI":
                continue
            if scenic_spot and attrs.get("scenic_spot") != scenic_spot:
                continue
            if attrs["label"] == name or name in (attrs.get("aliases") or []):
                candidates.append(node_id)
        if not candidates:
            raise KeyError(f"POI not found: {name} ({scenic_spot or 'any spot'})")
        if len(candidates) > 1:
            exact = [c for c in candidates if self.graph.nodes[c]["label"] == name]
            if len(exact) == 1:
                return exact[0]
            raise KeyError(f"ambiguous POI: {name} -> {candidates}")
        return candidates[0]

    # ----------------------------------------------------------------- routes
    def routes(
        self,
        scenic_spot: str | None = None,
        source_type: str | None = None,
        route_kind: str | None = None,
    ) -> list[dict]:
        result = []
        for attrs in self.nodes_of_type("Route", scenic_spot):
            if source_type and attrs.get("source_type") != source_type:
                continue
            if route_kind and attrs.get("route_kind") != route_kind:
                continue
            result.append(attrs)
        return sorted(result, key=lambda r: r["node_id"])

    def route(self, route_id: str) -> dict:
        return self.node(f"route:{route_id}")

    def route_steps(self, route_id: str) -> list[dict]:
        node_id = f"route:{route_id}"
        if node_id not in self.graph:
            raise KeyError(f"route not found: {route_id}")
        return [self.node(step) for step in self._route_steps.get(node_id, [])]

    def route_sequence(self, route_id: str) -> list[dict]:
        """Ordered, task-7-friendly view of a route."""
        sequence = []
        for step in self.route_steps(route_id):
            sequence.append(
                {
                    "order": step.get("order"),
                    "step_id": step.get("step_id"),
                    "day": step.get("day"),
                    "time_text": step.get("time_text"),
                    "time_period": step.get("time_period"),
                    "pois": step.get("pois") or [],
                    "activity": step.get("activity_raw"),
                    "activity_categories": step.get("activity_categories") or [],
                    "visit_mode": step.get("visit_mode"),
                    "visit_duration_text": step.get("visit_duration_text"),
                    "travel_duration_text": step.get("travel_duration_text"),
                }
            )
        return sorted(sequence, key=lambda s: s["order"])

    def route_pois(self, route_id: str) -> list[str]:
        pois: list[str] = []
        for step in self.route_sequence(route_id):
            for poi in step["pois"]:
                if not pois or pois[-1] != poi:
                    pois.append(poi)
        return pois

    # -------------------------------------------------------------------- poi
    def pois(
        self,
        scenic_spot: str | None = None,
        in_route_only: bool = False,
        min_route_count: int = 0,
    ) -> list[dict]:
        result = []
        for attrs in self.nodes_of_type("POI", scenic_spot):
            if in_route_only and not attrs.get("in_route"):
                continue
            if attrs.get("route_count", 0) < min_route_count:
                continue
            result.append(attrs)
        return sorted(result, key=lambda p: (-p.get("route_count", 0), -p.get("mention_count", 0), p["label"]))

    def routes_through_poi(self, name: str, scenic_spot: str | None = None) -> list[dict]:
        poi_id = self.find_poi(name, scenic_spot)
        route_ids = []
        for source, _, data in self.graph.in_edges(poi_id, data=True):
            if data["edge_type"] != "VISITS":
                continue
            for route_node in self.graph.predecessors(source):
                if self.graph.nodes[route_node]["node_type"] == "Route":
                    route_ids.append(route_node)
        return [self.node(r) for r in sorted(set(route_ids))]

    def poi_documents(self, name: str, scenic_spot: str | None = None) -> list[dict]:
        poi_id = self.find_poi(name, scenic_spot)
        docs = []
        for source, _, data in self.graph.in_edges(poi_id, data=True):
            if data["edge_type"] == "MENTIONS":
                docs.append(self.node(source))
        return docs

    # -------------------------------------------------------------- conditions
    def conditions(
        self,
        scenic_spot: str | None = None,
        condition_type: str | None = None,
        poi: str | None = None,
    ) -> list[dict]:
        result = []
        poi_id = self.find_poi(poi, scenic_spot) if poi else None
        for attrs in self.nodes_of_type("Condition", scenic_spot):
            if condition_type and attrs.get("condition_type") != condition_type:
                continue
            if poi_id:
                linked = any(
                    data["edge_type"] == "RELATES_TO" and target == poi_id
                    for _, target, data in self.graph.out_edges(attrs["node_id"], data=True)
                )
                if not linked:
                    continue
            result.append(attrs)
        return sorted(result, key=lambda c: c["node_id"])

    def condition_types(self) -> list[str]:
        return sorted({c.get("condition_type") for c in self.nodes_of_type("Condition") if c.get("condition_type")})

    def condition_pois(self, pair_id: str) -> list[dict]:
        node_id = f"condition:{pair_id}"
        result = []
        for _, target, data in self.graph.out_edges(node_id, data=True):
            if data["edge_type"] == "RELATES_TO":
                result.append(self.node(target))
        return result

    # ---------------------------------------------------------------- generic
    def neighbors(self, node_id: str, edge_type: str | None = None, direction: str = "out") -> list[dict]:
        result = []
        if direction in ("out", "both"):
            for _, target, data in self.graph.out_edges(node_id, data=True):
                if edge_type is None or data["edge_type"] == edge_type:
                    result.append({"edge": dict(data), "node": self.node(target)})
        if direction in ("in", "both"):
            for source, _, data in self.graph.in_edges(node_id, data=True):
                if edge_type is None or data["edge_type"] == edge_type:
                    result.append({"edge": dict(data), "node": self.node(source)})
        return result

    def subgraph(
        self,
        scenic_spot: str,
        node_types: Iterable[str] | None = None,
    ) -> nx.MultiDiGraph:
        allowed = set(node_types) if node_types else None
        nodes = [
            n
            for n, attrs in self.graph.nodes(data=True)
            if attrs.get("scenic_spot") == scenic_spot and (allowed is None or attrs["node_type"] in allowed)
        ]
        return self.graph.subgraph(nodes).copy()

    def stats(self) -> dict:
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "node_types": {t: len(ids) for t, ids in sorted(self._by_type.items())},
            "scenic_spots": self.scenic_spots(),
        }


def open_graph(path: str | Path = DEFAULT_GRAPH) -> GraphStore:
    return GraphStore(path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Query the task 6 knowledge graph")
    parser.add_argument("command", choices=["stats", "spots", "routes", "route", "poi", "conditions", "types"])
    parser.add_argument("value", nargs="?")
    parser.add_argument("--spot")
    args = parser.parse_args()
    store = open_graph()
    if args.command == "stats":
        print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
    elif args.command == "spots":
        print(json.dumps(store.scenic_spots(), ensure_ascii=False))
    elif args.command == "routes":
        rows = [
            {k: r.get(k) for k in ("route_id", "route_name", "scenic_spot", "source_type", "route_kind", "step_count")}
            for r in store.routes(args.spot)
        ]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif args.command == "route":
        print(json.dumps(store.route_sequence(args.value), ensure_ascii=False, indent=2))
    elif args.command == "poi":
        print(json.dumps(store.routes_through_poi(args.value, args.spot), ensure_ascii=False, indent=2))
    elif args.command == "conditions":
        print(json.dumps(store.conditions(args.spot), ensure_ascii=False, indent=2))
    elif args.command == "types":
        print(json.dumps(store.condition_types(), ensure_ascii=False))
