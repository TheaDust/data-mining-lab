"""One-command pipeline for task 6.

Usage
-----
python -m task6.run              # build + validate + visualise
python -m task6.run --skip-viz   # build + validate only
python -m task6.run --spot 北京故宫
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from task6.build import build_graph
from task6.validate import validate
from task6.visualize import visualise

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the task 6 knowledge graph")
    parser.add_argument("--skip-viz", action="store_true", help="skip PNG/HTML generation")
    parser.add_argument("--spot", action="append", help="limit visualisation to one scenic spot (repeatable)")
    args = parser.parse_args(argv)

    stats = build_graph()
    print(f"[build] nodes={stats['node_count']} edges={stats['edge_count']}")
    print(f"[build] node types: {json.dumps(stats['node_types'], ensure_ascii=False)}")
    print(f"[build] edge types: {json.dumps(stats['edge_types'], ensure_ascii=False)}")

    report = validate()
    status = "PASS" if report["all_passed"] else "FAIL"
    print(f"[validate] {status}: {sum(1 for c in report['checks'] if c['passed'])}/{len(report['checks'])} checks")
    if not report["all_passed"]:
        for check in report["checks"]:
            if not check["passed"]:
                print(f"  - {check['name']}: {check['detail']}")

    if not args.skip_viz:
        for path in visualise(args.spot):
            print(f"[viz] {path.relative_to(ROOT)}")

    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
