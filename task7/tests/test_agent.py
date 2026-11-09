import json

import pytest

from task7.agent import Planner, check_plan, materialize
from task7.llm import ModelError
from task7.models import Constraints, Proposal
from task7.tools import Knowledge, ToolRun


@pytest.fixture(scope="module")
def knowledge():
    return Knowledge()


@pytest.fixture
def run(knowledge):
    r = ToolRun(knowledge, Constraints(scenic_spot="北京故宫", duration="一天", days=1))
    r.search_routes("北京故宫")
    r.get_route_details("gugong_official_df6c311301c59157_route_01")
    return r


def proposal(run, **changes):
    values = {"status": "ready", "message": "依据原路线整理", "route_id": next(iter(run.details)),
              "orders": [s["order"] for s in next(iter(run.details.values()))]}
    return Proposal.model_validate(values | changes)


def tool(name, args):
    return {"role": "assistant", "content": None, "tool_calls": [{"id": "call_" + name,
        "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


class ScriptedModel:
    """Explicit test double; never presented as a live LLM run."""
    model = "test-double"
    usage = []

    def __init__(self, responses):
        self.responses = iter(responses)

    def complete(self, *args, **kwargs):
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        return item


def json_reply(value):
    return {"role": "assistant", "content": json.dumps(value, ensure_ascii=False)}


def test_graph_and_all_step_evidence(knowledge):
    assert knowledge.store.stats()["nodes"] == 583
    assert knowledge.store.stats()["edges"] == 1751
    for r in knowledge.store.routes():
        for s in knowledge.store.route_steps(r["route_id"]):
            assert s.get("evidence_text", "") in knowledge.documents[r["doc_id"]]["clean_text"]


@pytest.mark.parametrize("name,args", [
    ("search_routes", {"scenic_spot": "九寨沟"}),
    ("get_route_details", {"route_id": "../../etc/passwd"}),
    ("get_source_evidence", {"doc_id": "gugong_official_df6c311301c59157"}),
    ("exec", {"cmd": "anything"}),
    ("search_routes", {"scenic_spot": "北京故宫", "arbitrary": True}),
    ("get_source_evidence", None),
])
def test_tool_scope_and_schema(knowledge, name, args):
    r = ToolRun(knowledge, Constraints(scenic_spot="北京故宫"))
    assert r.call(name, args)["status"] == "invalid_input"


def test_source_requires_retrieval(run):
    doc = run.routes[next(iter(run.details))]["doc_id"]
    assert run.call("get_source_evidence", {"doc_id": doc})["status"] == "ok"


def test_route_must_be_read(run):
    p = proposal(run, route_id="unretrieved")
    assert check_plan(p, run, "故宫一天")


@pytest.mark.parametrize("orders", [[], [2, 1], [1, 1], [999], [-1]])
def test_invalid_step_order(run, orders):
    assert check_plan(proposal(run, orders=orders), run, "故宫一天")


def test_required_and_excluded(run):
    run.c.must_visit = ["不存在的景点"]
    assert any("必去" in e for e in check_plan(proposal(run), run, "故宫一天"))
    run.c.must_visit = []
    run.c.avoid = ["太和殿"]
    assert any("避开" in e for e in check_plan(proposal(run), run, "故宫一天"))


def test_facts_come_from_store_and_unknown_time_stays_unknown(run):
    p = proposal(run)
    assert check_plan(p, run, "故宫一天") == []
    result = materialize(p, run)
    assert result["steps"][0]["time_text"] is None
    assert result["steps"][0]["time_period"] is None
    assert result["steps"][0]["source"]["quote"] == "午门"
    assert any("时间" in x for x in result["limitations"])


def test_original_day_cannot_exceed_budget(knowledge):
    r = ToolRun(knowledge, Constraints(scenic_spot="九寨沟", days=1))
    r.search_routes("九寨沟")
    candidate = next(x for x in r.routes if any((s.get("day") or 0) > 1 for s in knowledge.store.route_steps(x)))
    r.get_route_details(candidate)
    assert any("天数" in e for e in check_plan(proposal(r, route_id=candidate), r, "一天"))


def test_advice_must_be_retrieved_with_user_quote(run):
    p = proposal(run, advice=[{"pair_id": "invented", "user_evidence": "假定晴天", "reason": "测试"}])
    errors = check_plan(p, run, "故宫一天")
    assert any("本次search" in e for e in errors)
    assert any("用户消息" in e for e in errors)


@pytest.mark.parametrize("constraints,status", [
    ({}, "clarification"),
    ({"scenic_spot": "黄山", "duration": "一天"}, "no_match"),
    ({"scenic_spot": "北京故宫"}, "clarification"),
    ({"scenic_spot": "北京故宫", "duration": "一天", "must_visit": ["太和殿"], "avoid": ["太和殿"]}, "clarification"),
])
def test_early_clarification_and_scope(knowledge, constraints, status):
    result = Planner(knowledge, ScriptedModel([json_reply(constraints)])).run("测试需求", save=False)
    assert result["status"] == status
    assert not [t for t in result["trace"] if t["type"] == "tool"]


def test_model_failure_is_explicit(knowledge):
    result = Planner(knowledge, ScriptedModel([ModelError("模拟超时")])).run("故宫一天", save=False)
    assert result["status"] == "error"
    assert result["message"] == "模拟超时"


def test_real_tool_loop_with_independent_advice_audit(knowledge):
    rid = "gugong_official_df6c311301c59157_route_01"
    responses = [json_reply({"scenic_spot": "北京故宫", "duration": "一天"}),
        tool("search_routes", {"scenic_spot": "北京故宫"}),
        tool("get_route_details", {"route_id": rid}),
        tool("search_condition_advices", {"scenic_spot": "北京故宫"}),
        tool("submit_plan", {"status": "ready", "message": "有依据的方案", "route_id": rid, "orders": [1, 2],
            "advice": [{"pair_id": "R00010", "user_evidence": "故宫一天", "reason": "模型误选晴天建议"}]}),
        json_reply({"decisions": [{"pair_id": "R00010", "verdict": "unknown", "reason": "用户未提供天气"}]})]
    result = Planner(knowledge, ScriptedModel(responses)).run("故宫一天", save=False)
    assert result["status"] == "ready"
    assert result["advice"] == []
    assert len(result["steps"]) == 2
    assert any(t["type"] == "advice_audit" for t in result["trace"])


def test_second_invalid_plan_fails_closed(knowledge):
    responses = [json_reply({"scenic_spot": "北京故宫", "duration": "一天"}),
        tool("submit_plan", {"status": "ready", "message": "无依据", "route_id": "fake", "orders": [1]}),
        tool("submit_plan", {"status": "ready", "message": "仍无依据", "route_id": "fake", "orders": [1]})]
    result = Planner(knowledge, ScriptedModel(responses)).run("故宫一天", save=False)
    assert result["status"] == "error"
    assert not result.get("steps")


def test_non_ready_cannot_smuggle_plan(run):
    p = Proposal(status="no_match", message="无匹配", route_id="fake", orders=[1])
    assert check_plan(p, run, "测试")
