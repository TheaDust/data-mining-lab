"""Batch runner for experiment 4: pronoun detection and coreference resolution.

Usage (from the repository root):

    python -X utf8 task4/run.py
    python -X utf8 -m unittest discover -s task4/tests -v

The runner reads only task1 documents, task2 V2 entities and task3 route POIs.
It rewrites ``task4/results/`` and does not modify upstream files.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from .extract import antecedent_match, resolve_document, split_sentences
except ImportError:  # direct execution: python task4/run.py
    from extract import antecedent_match, resolve_document, split_sentences

TASK_DIR = Path(__file__).resolve().parent
ROOT = TASK_DIR.parent
DOCS_PATH = ROOT / "task1" / "data" / "final" / "documents.jsonl"
ENTITIES_PATH = ROOT / "task2" / "results" / "v2" / "entities.json"
ROUTES_PATH = ROOT / "task3" / "results" / "official_routes.json"
VISITOR_ROUTES_PATH = ROOT / "task3" / "results" / "visitor_routes.json"
ANNOTATIONS_PATH = TASK_DIR / "annotations.json"
RESULTS_DIR = TASK_DIR / "results"

SELECTED_DOCS = [
    "gugong_user_generated_ac13633e735a71ff",
    "xihu_user_generated_6322b1ddadb1b801",
    "xihu_user_generated_ddcb0707c1791565",
    "jiuzhaigou_user_generated_653f517e7ecb42a0",
    "jiuzhaigou_user_generated_aa7e68d694fcc6a7",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_extra_poi_names() -> set[str]:
    names: set[str] = set()
    for path in (ROUTES_PATH, VISITOR_ROUTES_PATH):
        if not path.exists():
            continue
        for route in json.loads(path.read_text(encoding="utf-8")):
            for step in route.get("steps", []):
                for poi in step.get("pois", []):
                    name = poi.get("name") or poi.get("text")
                    if name:
                        names.add(name)
    return names


def validate_inputs(
    docs: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    doc_by_id = {doc["doc_id"]: doc for doc in docs}
    duplicate_docs = [key for key, count in Counter(doc["doc_id"] for doc in docs).items() if count > 1]
    if duplicate_docs:
        raise ValueError(f"duplicate doc_id: {duplicate_docs}")

    entity_errors: list[str] = []
    for entity in entities:
        doc = doc_by_id.get(entity.get("doc_id"))
        if doc is None:
            entity_errors.append(f"unknown doc_id {entity.get('doc_id')}")
            continue
        text = doc["clean_text"]
        start, end = entity.get("start"), entity.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            entity_errors.append(f"non-integer span {entity}")
            continue
        if not (0 <= start < end <= len(text)):
            entity_errors.append(f"span out of range {entity.get('doc_id')} {start}-{end}")
            continue
        if text[start:end] != entity.get("text"):
            entity_errors.append(f"slice mismatch {entity.get('doc_id')} {start}-{end}")
    if entity_errors:
        raise ValueError("entity validation failed:\n" + "\n".join(entity_errors[:20]))

    annotation_errors: list[str] = []
    for ann in annotations:
        doc = doc_by_id.get(ann.get("doc_id"))
        if doc is None:
            annotation_errors.append(f"unknown doc_id {ann.get('doc_id')}")
            continue
        text = doc["clean_text"]
        p_start, p_end = ann["pronoun_start"], ann["pronoun_end"]
        if text[p_start:p_end] != ann["pronoun"]:
            annotation_errors.append(f"pronoun slice mismatch {ann['annotation_id']}")
        if ann["status"] == "clear":
            a_start, a_end = ann["antecedent_start"], ann["antecedent_end"]
            if not isinstance(a_start, int) or not isinstance(a_end, int):
                annotation_errors.append(f"missing antecedent {ann['annotation_id']}")
            elif text[a_start:a_end] != ann["antecedent"]:
                annotation_errors.append(f"antecedent slice mismatch {ann['annotation_id']}")
        elif ann["status"] == "no_antecedent":
            if ann["antecedent"] is not None:
                annotation_errors.append(f"no_antecedent with antecedent {ann['annotation_id']}")
        else:
            annotation_errors.append(f"unknown annotation status {ann['annotation_id']}")
        sentences = split_sentences(text)
        if not any(s.start <= p_start < s.end and text[s.start:s.end] == ann["sentence"] for s in sentences):
            annotation_errors.append(f"sentence mismatch {ann['annotation_id']}")
    if annotation_errors:
        raise ValueError("annotation validation failed:\n" + "\n".join(annotation_errors[:20]))

    return {
        "documents": len(docs),
        "entities": len(entities),
        "annotations": len(annotations),
        "selected_documents": len({ann["doc_id"] for ann in annotations}),
        "entity_errors": 0,
        "annotation_errors": 0,
    }


def compact_candidates(mention: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    return [
        {
            "text": candidate["text"],
            "start": candidate["start"],
            "end": candidate["end"],
            "type": candidate["type"],
            "source": candidate["source"],
            "score": candidate["score"],
        }
        for candidate in mention.get("candidates", [])[:limit]
    ]


def evaluate(
    mentions_by_doc: dict[str, list[dict[str, Any]]],
    annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    index = {
        (mention["doc_id"], mention["start"], mention["end"]): mention
        for mentions in mentions_by_doc.values()
        for mention in mentions
    }
    cases: list[dict[str, Any]] = []
    for ann in annotations:
        mention = index.get((ann["doc_id"], ann["pronoun_start"], ann["pronoun_end"]))
        if mention is None:
            cases.append({
                "annotation_id": ann["annotation_id"],
                "doc_id": ann["doc_id"],
                "pronoun": ann["pronoun"],
                "pronoun_start": ann["pronoun_start"],
                "gold_status": ann["status"],
                "gold_antecedent": ann["antecedent"],
                "predicted_status": "detection_miss",
                "predicted_antecedent": None,
                "correct": False,
                "error": "detection_miss",
            })
            continue

        if ann["status"] == "clear":
            correct = (
                mention["resolution_status"] == "resolved"
                and antecedent_match(mention["antecedent"], ann["antecedent"])
            )
            if correct:
                error = None
            elif mention["resolution_status"] == "resolved":
                error = "wrong_antecedent"
            elif mention["resolution_status"] == "ambiguous":
                error = "ambiguous"
            else:
                error = "missed_antecedent"
        else:
            correct = mention["resolution_status"] in {
                "no_antecedent", "ambiguous", "non_entity", "out_of_scope"
            }
            error = None if correct else "false_resolution"

        cases.append({
            "annotation_id": ann["annotation_id"],
            "doc_id": ann["doc_id"],
            "pronoun": ann["pronoun"],
            "pronoun_start": ann["pronoun_start"],
            "gold_status": ann["status"],
            "gold_antecedent": ann["antecedent"],
            "gold_type": ann["pronoun_type"],
            "predicted_status": mention["resolution_status"],
            "predicted_antecedent": mention["antecedent"],
            "predicted_type": mention["pronoun_type"],
            "correct": correct,
            "error": error,
        })

    clear_cases = [case for case in cases if case["gold_status"] == "clear"]
    abstain_cases = [case for case in cases if case["gold_status"] == "no_antecedent"]
    resolved_cases = [case for case in clear_cases if case["predicted_status"] == "resolved"]
    correct_resolved = [case for case in resolved_cases if case["correct"]]
    correct_abstain = [case for case in abstain_cases if case["correct"]]

    def ratio(numerator: int | float, denominator: int | float) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    by_type: dict[str, dict[str, Any]] = {}
    for gold_type in sorted({case["gold_type"] for case in cases}):
        subset = [case for case in cases if case["gold_type"] == gold_type]
        subset_clear = [case for case in subset if case["gold_status"] == "clear"]
        subset_resolved = [case for case in subset_clear if case["predicted_status"] == "resolved"]
        subset_correct = [case for case in subset if case["correct"]]
        by_type[gold_type] = {
            "annotated": len(subset),
            "clear": len(subset_clear),
            "no_antecedent": len(subset) - len(subset_clear),
            "resolved": len(subset_resolved),
            "correct": len(subset_correct),
            "accuracy_overall": ratio(len(subset_correct), len(subset)),
            "accuracy_resolved": ratio(len([c for c in subset_resolved if c["correct"]]), len(subset_resolved)),
            "coverage": ratio(len(subset_resolved), len(subset_clear)),
        }

    return {
        "annotated_total": len(cases),
        "clear_total": len(clear_cases),
        "no_antecedent_total": len(abstain_cases),
        "detection_misses": len([case for case in cases if case["predicted_status"] == "detection_miss"]),
        "resolved_total": len(resolved_cases),
        "correct_resolved": len(correct_resolved),
        "correct_abstention": len(correct_abstain),
        "coverage": ratio(len(resolved_cases), len(clear_cases)),
        "accuracy_resolved": ratio(len(correct_resolved), len(resolved_cases)),
        "accuracy_overall": ratio(sum(case["correct"] for case in cases), len(cases)),
        "false_resolutions": len([case for case in abstain_cases if not case["correct"]]),
        "by_type": by_type,
        "cases": cases,
        "errors": [case for case in cases if not case["correct"]],
    }


def build_resolved_texts(
    docs: list[dict[str, Any]],
    mentions_by_doc: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for doc in docs:
        text = doc["clean_text"]
        mentions = mentions_by_doc[doc["doc_id"]]
        resolved = [m for m in mentions if m["resolution_status"] == "resolved"]
        resolved.sort(key=lambda m: m["start"], reverse=True)

        resolved_text = text
        for mention in resolved:
            resolved_text = (
                resolved_text[:mention["start"]]
                + mention["antecedent"]
                + resolved_text[mention["replace_end"]:]
            )

        marked_text = text
        for mention in resolved:
            marker = f"{mention['surface']}〔→{mention['antecedent']}〕"
            marked_text = marked_text[:mention["start"]] + marker + marked_text[mention["end"]:]

        sentences: list[dict[str, Any]] = []
        by_sentence: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for mention in resolved:
            by_sentence[(mention["sentence_start"], mention["sentence_end"])].append(mention)
        for (start, end), items in sorted(by_sentence.items()):
            original = text[start:end]
            plain = original
            marked = original
            for mention in sorted(items, key=lambda m: m["start"], reverse=True):
                rel_start = mention["start"] - start
                rel_end = mention["replace_end"] - start
                plain = plain[:rel_start] + mention["antecedent"] + plain[rel_end:]
                marker = f"{mention['surface']}〔→{mention['antecedent']}〕"
                marked = marked[:rel_start] + marker + marked[mention["end"] - start:]
            sentences.append({
                "sentence_start": start,
                "sentence_end": end,
                "original": original,
                "resolved": plain,
                "marked": marked,
                "mentions": [m["mention_id"] for m in items],
            })

        output[doc["doc_id"]] = {
            "doc_id": doc["doc_id"],
            "scenic_spot": doc["scenic_spot"],
            "source_type": doc["source_type"],
            "resolved_count": len(resolved),
            "resolved_text": resolved_text,
            "marked_text": marked_text,
            "resolved_sentences": sentences,
        }
    return output


def build_triples(mentions_by_doc: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    triples: list[dict[str, Any]] = []
    for mentions in mentions_by_doc.values():
        for mention in mentions:
            if mention["resolution_status"] != "resolved":
                continue
            triples.append({
                "subject": mention["antecedent"],
                "predicate": "referred_by_pronoun",
                "object": mention["surface"],
                "doc_id": mention["doc_id"],
                "mention_id": mention["mention_id"],
                "sentence": mention["sentence"],
                "confidence": mention["confidence"],
            })
    return triples


def build_summary(
    docs: list[dict[str, Any]],
    mentions_by_doc: dict[str, list[dict[str, Any]]],
    evaluation: dict[str, Any],
    input_checks: dict[str, Any],
    annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    all_mentions = [m for mentions in mentions_by_doc.values() for m in mentions]
    return {
        "input": {
            "documents": len(docs),
            "documents_sha256": sha256(DOCS_PATH),
            "entities_sha256": sha256(ENTITIES_PATH),
            "annotations_sha256": sha256(ANNOTATIONS_PATH),
            "selected_documents": sorted({ann["doc_id"] for ann in annotations}),
            "annotated_documents": sorted({ann["doc_id"] for ann in annotations}),
        },
        "detection": {
            "mentions": len(all_mentions),
            "by_type": dict(Counter(m["pronoun_type"] for m in all_mentions)),
            "by_kind": dict(Counter(m["kind"] for m in all_mentions)),
            "by_status": dict(Counter(m["resolution_status"] for m in all_mentions)),
            "pronoun_surfaces": dict(Counter(m["surface"] for m in all_mentions)),
            "documents_with_mentions": len([d for d, ms in mentions_by_doc.items() if ms]),
        },
        "resolution": {
            "resolved": sum(1 for m in all_mentions if m["resolution_status"] == "resolved"),
            "no_antecedent": sum(1 for m in all_mentions if m["resolution_status"] == "no_antecedent"),
            "ambiguous": sum(1 for m in all_mentions if m["resolution_status"] == "ambiguous"),
            "non_entity": sum(1 for m in all_mentions if m["resolution_status"] == "non_entity"),
            "out_of_scope": sum(1 for m in all_mentions if m["resolution_status"] == "out_of_scope"),
            "antecedent_types": dict(Counter(m["antecedent_type"] for m in all_mentions if m["antecedent_type"])),
        },
        "evaluation": {k: v for k, v in evaluation.items() if k not in {"cases", "errors"}},
        "checks": input_checks,
    }


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_quality(
    summary: dict[str, Any],
    evaluation: dict[str, Any],
    mentions_by_doc: dict[str, list[dict[str, Any]]],
) -> None:
    lines: list[str] = []
    lines.append("# 任务 4 质量检查记录")
    lines.append("")
    lines.append("本文件由 `python -X utf8 task4/run.py` 自动重建，记录程序校验、人工标注评估和已知边界。")
    lines.append("")
    lines.append("## 输入与位置校验")
    lines.append("")
    lines.append(f"- 文档数：{summary['input']['documents']}；人工标注：{summary['evaluation']['annotated_total']} 条；覆盖 {len(SELECTED_DOCS)} 篇游客游记。")
    lines.append(f"- 文档 SHA-256：`{summary['input']['documents_sha256']}`。")
    lines.append(f"- 实体 SHA-256：`{summary['input']['entities_sha256']}`。")
    lines.append(f"- 标注 SHA-256：`{summary['input']['annotations_sha256']}`。")
    lines.append("- 所有实体、代词和先行词切片均与 `clean_text` 对应位置一致；标注中的句子切分也通过复核。")
    lines.append("")
    lines.append("## 检测与消解统计")
    lines.append("")
    detection = summary["detection"]
    resolution = summary["resolution"]
    lines.append(f"- 全语料检测到 {detection['mentions']} 个代词/指示表达，覆盖 {detection['documents_with_mentions']} 篇文档。")
    lines.append(f"- 按类型：{detection['by_type']}。")
    lines.append(f"- 按状态：{detection['by_status']}。")
    lines.append(f"- 已消解 {resolution['resolved']} 条，弃权 {resolution['no_antecedent']} 条，歧义 {resolution['ambiguous']} 条。")
    lines.append(f"- 先行词类型：{resolution['antecedent_types']}。")
    lines.append("")
    lines.append("## 人工标注评估")
    lines.append("")
    lines.append(f"- 标注总数：{evaluation['annotated_total']}；明确先行词 {evaluation['clear_total']} 条；无明确先行词 {evaluation['no_antecedent_total']} 条。")
    lines.append(f"- 覆盖率：{evaluation['coverage']:.2%}（{evaluation['resolved_total']}/{evaluation['clear_total']}）。")
    lines.append(f"- 已消解准确率：{evaluation['accuracy_resolved']:.2%}（{evaluation['correct_resolved']}/{evaluation['resolved_total']}）。")
    lines.append(f"- 总体准确率（含弃权）：{evaluation['accuracy_overall']:.2%}。")
    lines.append(f"- 错误案例：{len(evaluation['errors'])} 条。")
    lines.append("")
    lines.append("| 类型 | 标注数 | 明确先行词 | 已消解 | 总体准确率 |")
    lines.append("|---|---:|---:|---:|---:|")
    for name, row in evaluation["by_type"].items():
        lines.append(f"| {name} | {row['annotated']} | {row['clear']} | {row['resolved']} | {row['accuracy_overall']:.2%} |")
    lines.append("")
    lines.append("## 已知边界")
    lines.append("")
    lines.append("- 规则只覆盖本批 18 篇文本中的代词和指示表达，未训练统计模型，也未使用神经网络共指模型。")
    lines.append("- 人工标注是 5 篇游记中的定向样本，不是全语料 gold；28 条上的准确率不能外推为整体性能。")
    lines.append("- 第一、第二人称和泛称主要标为 `out_of_scope`，不作为实体共指评估；它们仍保留在 `mentions.json` 中，便于检查检测召回。")
    lines.append("- “这里特别提醒”这类指向下文的篇章指代被标为无明确先行词，系统应弃权；如果强行回指前文路线段，属于过度消解。")
    lines.append("- 长路线段的先行词以原文箭头链整体表示，替换后句子可能不自然；`marked_text` 保留原词并标注预测，便于人工核对。")
    lines.append("")
    lines.append("## 代表性输出")
    lines.append("")
    examples = []
    for doc_id in SELECTED_DOCS:
        for mention in mentions_by_doc.get(doc_id, []):
            if mention["resolution_status"] == "resolved":
                examples.append(mention)
                break
    for mentions in mentions_by_doc.values():
        for mention in mentions:
            if len(examples) >= 8:
                break
            if mention["resolution_status"] == "resolved" and mention not in examples:
                examples.append(mention)
    for mention in examples[:8]:
        lines.append(f"- `{mention['doc_id']}`：`{mention['surface']}` → `{mention['antecedent']}`（{mention['antecedent_type']}，置信度 {mention['confidence']:.3f}）")
    lines.append("")
    (RESULTS_DIR / "QUALITY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    docs = load_jsonl(DOCS_PATH)
    entities = json.loads(ENTITIES_PATH.read_text(encoding="utf-8"))
    annotation_payload = json.loads(ANNOTATIONS_PATH.read_text(encoding="utf-8"))
    annotations = annotation_payload["annotations"]
    extra_poi_names = load_extra_poi_names()

    input_checks = validate_inputs(docs, entities, annotations)

    entities_by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in entities:
        entities_by_doc[entity["doc_id"]].append(entity)

    mentions_by_doc: dict[str, list[dict[str, Any]]] = {}
    all_candidates: dict[str, int] = {}
    for doc in docs:
        mentions, candidates = resolve_document(
            doc,
            entities_by_doc.get(doc["doc_id"], []),
            extra_poi_names,
        )
        mentions_by_doc[doc["doc_id"]] = mentions
        all_candidates[doc["doc_id"]] = len(candidates)

    evaluation = evaluate(mentions_by_doc, annotations)
    summary = build_summary(docs, mentions_by_doc, evaluation, input_checks, annotations)
    summary["candidates_by_doc"] = all_candidates

    all_mentions = [
        {
            "mention_id": mention["mention_id"],
            "doc_id": mention["doc_id"],
            "scenic_spot": mention["scenic_spot"],
            "source_type": mention["source_type"],
            "source_name": mention["source_name"],
            "url": mention["url"],
            "pronoun": mention["surface"],
            "pronoun_start": mention["start"],
            "pronoun_end": mention["end"],
            "replace_end": mention["replace_end"],
            "replace_text": mention["replace_text"],
            "pronoun_type": mention["pronoun_type"],
            "kind": mention["kind"],
            "head": mention["head"],
            "head_type": mention["head_type"],
            "sentence": mention["sentence"],
            "sentence_start": mention["sentence_start"],
            "sentence_end": mention["sentence_end"],
            "resolution_status": mention["resolution_status"],
            "antecedent": mention["antecedent"],
            "antecedent_start": mention["antecedent_start"],
            "antecedent_end": mention["antecedent_end"],
            "antecedent_type": mention["antecedent_type"],
            "confidence": mention["confidence"],
            "candidates": compact_candidates(mention),
        }
        for mentions in mentions_by_doc.values()
        for mention in mentions
    ]

    coreferences = []
    for mention in all_mentions:
        if mention["resolution_status"] != "resolved":
            continue
        coreferences.append({
            "coref_id": f"coref_{len(coreferences) + 1:04d}",
            "doc_id": mention["doc_id"],
            "scenic_spot": mention["scenic_spot"],
            "source_type": mention["source_type"],
            "source_name": mention["source_name"],
            "url": mention["url"],
            "pronoun": mention["pronoun"],
            "pronoun_start": mention["pronoun_start"],
            "pronoun_end": mention["pronoun_end"],
            "pronoun_type": mention["pronoun_type"],
            "antecedent": mention["antecedent"],
            "antecedent_start": mention["antecedent_start"],
            "antecedent_end": mention["antecedent_end"],
            "antecedent_type": mention["antecedent_type"],
            "method": "rule_nearest_entity_with_heading_and_route_constraints",
            "confidence": mention["confidence"],
            "mention_id": mention["mention_id"],
            "sentence": mention["sentence"],
            "sentence_start": mention["sentence_start"],
            "sentence_end": mention["sentence_end"],
        })

    resolved_texts = build_resolved_texts(docs, mentions_by_doc)
    triples = build_triples(mentions_by_doc)

    write_json(RESULTS_DIR / "mentions.json", all_mentions)
    write_json(RESULTS_DIR / "coreferences.json", coreferences)
    (RESULTS_DIR / "coreferences.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in coreferences) + "\n",
        encoding="utf-8",
    )
    write_json(RESULTS_DIR / "evaluation.json", evaluation)
    write_json(RESULTS_DIR / "resolved_texts.json", resolved_texts)
    write_json(RESULTS_DIR / "triples.json", triples)
    write_json(RESULTS_DIR / "summary.json", summary)
    write_quality(summary, evaluation, mentions_by_doc)

    print(json.dumps({
        "documents": len(docs),
        "mentions": len(all_mentions),
        "coreferences": len(coreferences),
        "annotated": evaluation["annotated_total"],
        "accuracy_overall": evaluation["accuracy_overall"],
        "accuracy_resolved": evaluation["accuracy_resolved"],
        "coverage": evaluation["coverage"],
        "errors": len(evaluation["errors"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
