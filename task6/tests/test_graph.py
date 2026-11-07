from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import networkx as nx

from task6.build import build_graph
from task6.graph import open_graph


class GraphBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        build_graph()
        cls.store = open_graph()
        cls.graph = cls.store.graph
        cls.stats = json.loads((ROOT / "task6" / "results" / "stats.json").read_text(encoding="utf-8"))

    def test_expected_scale(self) -> None:
        self.assertEqual(self.graph.number_of_nodes(), 583)
        self.assertEqual(self.graph.number_of_edges(), 1751)
        self.assertEqual(len(self.store.routes()), 23)
        self.assertEqual(len(self.store.nodes_of_type("Step")), 250)
        self.assertEqual(len(self.store.conditions()), 41)
        self.assertEqual(len(self.store.nodes_of_type("Document")), 18)
        self.assertEqual(len(self.store.pois()), 215)

    def test_no_dangling_edges_and_unique_ids(self) -> None:
        self.assertTrue(all(s in self.graph and t in self.graph for s, t in self.graph.edges()))
        node_ids = [n for n in self.graph.nodes]
        edge_ids = [d["edge_id"] for _, _, _, d in self.graph.edges(keys=True, data=True)]
        self.assertEqual(len(node_ids), len(set(node_ids)))
        self.assertEqual(len(edge_ids), len(set(edge_ids)))

    def test_routes_match_task3_and_sequence_is_contiguous(self) -> None:
        for route in self.store.routes():
            steps = self.store.route_steps(route["route_id"])
            self.assertEqual(route["step_count"], len(steps))
            self.assertEqual([s["order"] for s in steps], list(range(1, len(steps) + 1)))
            for previous, current in zip(steps, steps[1:]):
                self.assertTrue(
                    any(
                        data["edge_type"] == "NEXT" and target == current["node_id"]
                        for _, target, data in self.graph.out_edges(previous["node_id"], data=True)
                    )
                )

    def test_route_start_end_matches_first_last_poi(self) -> None:
        starts = [e for e in self.graph.edges(data=True) if e[2]["edge_type"] == "STARTS_AT"]
        ends = [e for e in self.graph.edges(data=True) if e[2]["edge_type"] == "ENDS_AT"]
        self.assertEqual(len(starts), 21)
        self.assertEqual(len(ends), 21)
        for source, target, _ in starts:
            route_id = source.split(":", 1)[1]
            sequence = self.store.route_sequence(route_id)
            self.assertEqual(target.split(":", 2)[2], sequence[0]["pois"][0])
        for source, target, _ in ends:
            route_id = source.split(":", 1)[1]
            sequence = self.store.route_sequence(route_id)
            self.assertEqual(target.split(":", 2)[2], sequence[-1]["pois"][-1])

    def test_poi_alignment_and_visits(self) -> None:
        visits = [d for _, _, d in self.graph.edges(data=True) if d["edge_type"] == "VISITS"]
        self.assertEqual(len(visits), 294)
        self.assertEqual(sum(1 for d in visits if d.get("aligned_to_task2")), 291)
        self.assertEqual(self.stats["alignment"]["route_poi_entity_refs"], 291)
        self.assertEqual(self.stats["alignment"]["route_poi_entity_refs_aligned"], 291)

    def test_boundary_actions_are_filtered_from_poi_nodes(self) -> None:
        labels = {p["label"] for p in self.store.pois()}
        for boundary in ("出沟", "进景区"):
            self.assertNotIn(boundary, labels)
        steps_without_poi = [
            s
            for s in self.store.nodes_of_type("Step")
            if not s.get("pois")
        ]
        self.assertEqual(len(steps_without_poi), 7)
        self.assertEqual(self.stats["filters"]["non_poi_route_labels"], 4)

    def test_low_frequency_poi_policy(self) -> None:
        for poi in self.store.pois():
            self.assertTrue(poi.get("in_route") or poi.get("mention_count", 0) >= 2)
        self.assertEqual(self.stats["excluded_poi_count"], 125)
        with (ROOT / "task6" / "results" / "excluded_pois.csv").open(encoding="utf-8-sig") as fh:
            excluded = list(csv.DictReader(fh))
        self.assertEqual(len(excluded), 125)

    def test_three_connected_scenic_subgraphs(self) -> None:
        self.assertEqual(len(list(nx.weakly_connected_components(self.graph))), 3)
        for spot in self.store.scenic_spots():
            self.assertTrue(nx.is_weakly_connected(self.store.subgraph(spot)), spot)
        self.assertFalse(any(self.graph.degree(n) == 0 for n in self.graph))

    def test_conditions_fusion(self) -> None:
        self.assertEqual(len(self.store.condition_types()), 7)
        self.assertEqual(self.stats["condition_poi_links"], 30)
        linked = [c for c in self.store.conditions() if self.store.condition_pois(c["pair_id"])]
        self.assertEqual(len(linked), 20)
        self.assertGreaterEqual(len(self.store.conditions(condition_type="时间约束")), 10)
        self.assertTrue(any(c["pair_id"] == "R00008" for c in self.store.conditions(poi="珍宝馆", scenic_spot="北京故宫")))

    def test_route_sequence_and_poi_queries(self) -> None:
        route_id = "gugong_official_df6c311301c59157_route_01"
        self.assertEqual(
            self.store.route_pois(route_id),
            ["午门", "太和殿", "中和殿", "保和殿", "乾清宫", "交泰殿", "坤宁宫", "御花园", "神武门"],
        )
        route_names = {r["label"] for r in self.store.routes_through_poi("太和殿", "北京故宫")}
        self.assertEqual(route_names, {"路线一(图中黄箭头)", "游客攻略：半天精华线"})

    def test_alias_resolution(self) -> None:
        node_id = self.store.find_poi("天鹅湖", "九寨沟")
        self.assertEqual(self.store.node(node_id)["label"], "天鹅海")
        self.assertTrue(self.store.pois(scenic_spot="九寨沟", in_route_only=True))

    def test_csv_and_json_exports_round_trip(self) -> None:
        with (ROOT / "task6" / "results" / "nodes.csv").open(encoding="utf-8-sig") as fh:
            nodes = list(csv.DictReader(fh))
        with (ROOT / "task6" / "results" / "edges.csv").open(encoding="utf-8-sig") as fh:
            edges = list(csv.DictReader(fh))
        payload = json.loads((ROOT / "task6" / "results" / "graph.json").read_text(encoding="utf-8"))
        self.assertEqual(len(nodes), self.graph.number_of_nodes())
        self.assertEqual(len(edges), self.graph.number_of_edges())
        self.assertEqual(len(payload["nodes"]), self.graph.number_of_nodes())
        self.assertEqual(len(payload["edges"]), self.graph.number_of_edges())
        self.assertEqual(payload["metadata"]["inputs"], self.stats["inputs"])

    def test_documents_are_traceable(self) -> None:
        doc_nodes = {n for n, d in self.graph.nodes(data=True) if d["node_type"] == "Document"}
        linked = {
            source
            for source, _, data in self.graph.edges(data=True)
            if data["edge_type"] in ("DESCRIBES", "FROM_DOC", "MENTIONS") and source in doc_nodes
        }
        self.assertEqual(linked, doc_nodes)


if __name__ == "__main__":
    unittest.main()
