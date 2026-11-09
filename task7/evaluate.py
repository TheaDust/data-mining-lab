"""Opt-in live acceptance scenarios. Requests are billable; no mocks here."""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from task7.agent import Planner
from task7.tools import Knowledge

CASES = [
    ("elder", "带老人去九寨沟玩一天，希望轻松一些", "ready"),
    ("family", "带孩子去故宫玩半天，必须去太和殿，不去珍宝馆", "ready"),
    ("couple", "情侣去西湖玩一天，喜欢拍照", "ready"),
    ("missing_spot", "我和孩子想玩一天", "clarification"),
    ("missing_duration", "想去西湖游玩", "clarification"),
    ("unsupported", "去黄山玩一天", "no_match"),
    ("conflict", "故宫玩一天，太和殿必须去，也必须避开太和殿", "clarification"),
    ("unknown_poi", "故宫玩一天，必须去火星博物馆", "no_match"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="明确启用真实模型请求，会产生API费用")
    args = parser.parse_args()
    if not args.live:
        parser.error("真实模型验收需显式指定 --live；离线测试使用 pytest task7/tests")
    k = Knowledge()

    def execute(case):
        name, message, expected = case
        result = Planner(k).run(message)
        checks = {"status": result["status"] == expected}
        if result["status"] == "ready":
            tools = [t["name"] for t in result["trace"] if t["type"] == "tool"]
            checks["real_tools"] = "search_routes" in tools and "get_route_details" in tools
            steps = result["steps"]
            checks["nonempty_steps"] = bool(steps)
            checks["source_quotes"] = all(s["source"]["quote"] in k.documents[s["source"]["doc_id"]]["clean_text"] for s in steps)
            if name == "family":
                pois = {p for s in steps for p in s["pois"]}
                checks["required_poi"] = "太和殿" in pois
                checks["excluded_poi"] = "珍宝馆" not in pois
            if name == "elder":
                checks["no_inferred_high_altitude_experience"] = all(a["pair_id"] != "R00006" for a in result["advice"])
        row = {"case": name, "input": message, "expected": expected, "actual": result["status"],
               "passed": all(checks.values()), "checks": checks, "request_id": result["request_id"],
               "steps": len(result.get("steps", [])), "message": result["message"]}
        print(json.dumps({"case": name, "actual": result["status"], "passed": row["passed"]}, ensure_ascii=False), flush=True)
        return row, result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, CASES))
    # Continue one real conversation, preserving parsed context and user messages.
    previous = results[2][1]
    followup = Planner(k).run("改成两天，想安安静静欣赏风景", previous["constraints"], [CASES[2][1]])
    checks = {"status": followup["status"] == "ready", "spot_retained": followup["constraints"]["scenic_spot"] == "杭州西湖",
              "duration_updated": followup["constraints"]["days"] == 2}
    results.append(({"case": "followup", "input": "改成两天，想安安静静欣赏风景", "expected": "ready",
        "actual": followup["status"], "passed": all(checks.values()), "checks": checks,
        "request_id": followup["request_id"], "steps": len(followup.get("steps", [])), "message": followup["message"]}, followup))
    folder = Path(__file__).parent / "results"
    summary = {"mode": "live_deepseek", "created_at": datetime.now(timezone.utc).isoformat(), "model": results[0][1]["model"],
        "graph_sha256": k.fingerprint, "passed": sum(r["passed"] for r, _ in results), "total": len(results),
        "cases": [r for r, _ in results]}
    (folder / "evaluation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "demo.json").write_text(json.dumps({"input": CASES[1][1], "result": results[1][1]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Live checks: {summary['passed']}/{summary['total']}")
    raise SystemExit(0 if summary["passed"] == summary["total"] else 1)


if __name__ == "__main__":
    main()
