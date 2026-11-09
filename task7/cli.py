import argparse
import json

from task7.agent import Planner


def main():
    parser = argparse.ArgumentParser(description="基于本组知识图谱的景区游览规划")
    parser.add_argument("message", help="例如：带老人去九寨沟玩一天，希望轻松一些")
    args = parser.parse_args()
    result = Planner().run(args.message)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["status"] == "error" else 0)


if __name__ == "__main__":
    main()
