import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from task4.extract import (  # noqa: E402
    antecedent_match,
    build_candidates,
    classify_mention,
    detect_pronouns,
    normalize,
    replacement_suffix,
    resolve_document,
    split_sentences,
)
from task4.run import evaluate, load_extra_poi_names, load_jsonl  # noqa: E402

TASK_DIR = ROOT / "task4"


class SentenceAndDetectionTests(unittest.TestCase):
    def test_sentence_spans_are_half_open_and_cover_source(self):
        text = "第一句。第二句！\n第三句"
        sentences = split_sentences(text)
        self.assertEqual([text[s.start:s.end] for s in sentences], ["第一句。", "第二句！", "第三句"])
        self.assertEqual(sentences[0].start, 0)
        self.assertEqual(sentences[-1].end, len(text))

    def test_longest_pronoun_wins(self):
        text = "我们从这里出发，它们在那里等着。"
        mentions = detect_pronouns(text)
        surfaces = [(m["surface"], m["start"], m["end"]) for m in mentions]
        self.assertIn(("我们", 0, 2), surfaces)
        self.assertIn(("这里", 3, 5), surfaces)
        self.assertIn(("它们", 8, 10), surfaces)
        self.assertIn(("那里", 11, 13), surfaces)
        for mention in mentions:
            self.assertEqual(text[mention["start"]:mention["end"]], mention["surface"])

    def test_fixed_expressions_are_filtered(self):
        text = "其他游客其实从这里出发，从此不再回头，该坐观光车就坐。"
        surfaces = [m["surface"] for m in detect_pronouns(text)]
        self.assertNotIn("他", surfaces)
        self.assertNotIn("其", surfaces)
        self.assertNotIn("此", surfaces)
        self.assertNotIn("该", surfaces)
        self.assertIn("这里", surfaces)

    def test_same_surface_twice_has_distinct_offsets(self):
        text = "午门在这里。午门在那里。"
        mentions = detect_pronouns(text)
        places = [m for m in mentions if m["surface"] in {"这里", "那里"}]
        self.assertEqual(len(places), 2)
        self.assertNotEqual((places[0]["start"], places[0]["end"]), (places[1]["start"], places[1]["end"]))

    def test_hashtag_is_filtered(self):
        text = "正常句子。#避开人潮去这里\n"
        surfaces = [m["surface"] for m in detect_pronouns(text)]
        self.assertNotIn("这里", surfaces)


class ClassificationTests(unittest.TestCase):
    def classify(self, text, surface):
        start = text.index(surface)
        return classify_mention(text, surface, start, start + len(surface))

    def test_route_determiner(self):
        info = self.classify("这条路线很好走", "这")
        self.assertEqual(info["kind"], "determiner")
        self.assertEqual(info["head"], "路线")
        self.assertEqual(info["head_type"], "route")

    def test_poi_determiner(self):
        info = self.classify("这道门是午门", "这")
        self.assertEqual(info["head"], "门")
        self.assertEqual(info["head_type"], "poi")

    def test_demonstrative_not_determiner(self):
        info = self.classify("这个感觉一般", "这个")
        self.assertEqual(info["kind"], "demonstrative")

    def test_non_entity_plural(self):
        info = self.classify("这些照片很好看", "这些")
        self.assertEqual(info["head"], "照片")
        self.assertEqual(info["head_type"], "non_entity")
        self.assertEqual(info["status"], "non_entity")

    def test_replacement_suffix(self):
        self.assertEqual(replacement_suffix("这", "条路线很好", "路线"), "条路线")
        self.assertEqual(replacement_suffix("这个", "路线很好", "路线"), "路线")
        self.assertEqual(replacement_suffix("这", "座皇城很大", "皇城"), "座皇城")
        self.assertEqual(replacement_suffix("这", "是午门", None), "")


class CandidateAndResolutionTests(unittest.TestCase):
    def make_doc(self, text, doc_id="doc_test"):
        return {
            "doc_id": doc_id,
            "scenic_spot": "测试景区",
            "source_type": "user_generated",
            "source_name": "测试",
            "url": "https://example.com",
            "clean_text": text,
        }

    def entities(self, text, pairs):
        return [
            {"doc_id": "doc_test", "text": name, "type": "POI", "start": text.index(name), "end": text.index(name) + len(name)}
            for name in pairs
        ]

    def test_heading_resolution(self):
        text = "午门｜人生开篇\n世人皆知午门斩首，实则这里是皇家盛典之门。"
        doc = self.make_doc(text)
        entities = self.entities(text, ["午门"])
        mentions, candidates = resolve_document(doc, entities)
        place = next(m for m in mentions if m["surface"] == "这里")
        self.assertEqual(place["resolution_status"], "resolved")
        self.assertEqual(place["antecedent"], "午门")

    def test_route_segment_resolution(self):
        text = "路线：\n原始森林 → 芳草海 → 天鹅海\n这一段非常好看。"
        doc = self.make_doc(text)
        entities = self.entities(text, ["原始森林", "芳草海", "天鹅海"])
        mentions, candidates = resolve_document(doc, entities)
        mention = next(m for m in mentions if m["surface"] == "这")
        self.assertEqual(mention["resolution_status"], "resolved")
        self.assertEqual(mention["antecedent"], "原始森林 → 芳草海 → 天鹅海")

    def test_cataphoric_place_abstains(self):
        text = "原始森林 → 芳草海 → 天鹅海\n这一段很好。\n⚠️这里特别提醒：天鹅海→箭竹海不建议徒步。"
        doc = self.make_doc(text)
        entities = self.entities(text, ["原始森林", "芳草海", "天鹅海", "箭竹海"])
        mentions, candidates = resolve_document(doc, entities)
        place = next(m for m in mentions if m["surface"] == "这里")
        self.assertIn(place["resolution_status"], {"no_antecedent", "ambiguous"})

    def test_palace_head_prefers_palace(self):
        text = "紫禁城是明清皇宫。后来，这座皇城成为博物院。"
        doc = self.make_doc(text)
        entities = self.entities(text, ["紫禁城"])
        mentions, candidates = resolve_document(doc, entities)
        mention = next(m for m in mentions if m["surface"] == "这")
        self.assertEqual(mention["resolution_status"], "resolved")
        self.assertEqual(mention["antecedent"], "紫禁城")

    def test_antecedent_match_normalizes_arrows_and_spaces(self):
        self.assertTrue(antecedent_match("原始森林 → 芳草海", "原始森林→芳草海"))
        self.assertTrue(antecedent_match("午门", "午门"))
        self.assertFalse(antecedent_match("午门", "神武门"))


class AnnotatedCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = load_jsonl(ROOT / "task1/data/final/documents.jsonl")
        cls.entities = json.loads((ROOT / "task2/results/v2/entities.json").read_text(encoding="utf-8"))
        cls.annotations = json.loads((TASK_DIR / "annotations.json").read_text(encoding="utf-8"))["annotations"]
        cls.extra_poi_names = load_extra_poi_names()

    def test_annotations_point_to_real_slices(self):
        docs = {d["doc_id"]: d for d in self.docs}
        for ann in self.annotations:
            text = docs[ann["doc_id"]]["clean_text"]
            self.assertEqual(text[ann["pronoun_start"]:ann["pronoun_end"]], ann["pronoun"])
            if ann["status"] == "clear":
                self.assertEqual(
                    text[ann["antecedent_start"]:ann["antecedent_end"]],
                    ann["antecedent"],
                )

    def test_selected_documents_achieve_expected_gold_accuracy(self):
        docs = {d["doc_id"]: d for d in self.docs}
        by_doc: dict[str, list[dict]] = {}
        for doc_id in sorted({ann["doc_id"] for ann in self.annotations}):
            by_doc[doc_id], _ = resolve_document(
                docs[doc_id],
                [e for e in self.entities if e["doc_id"] == doc_id],
                self.extra_poi_names,
            )
        report = evaluate(by_doc, self.annotations)
        self.assertEqual(report["annotated_total"], 28)
        self.assertEqual(report["detection_misses"], 0)
        self.assertEqual(report["correct_resolved"], 26)
        self.assertEqual(report["correct_abstention"], 2)
        self.assertEqual(report["accuracy_overall"], 1.0)


if __name__ == "__main__":
    unittest.main()
