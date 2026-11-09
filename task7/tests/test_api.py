import json

from fastapi.testclient import TestClient

from task7 import api


def test_health_never_exposes_secret():
    response = TestClient(api.app).get("/api/health")
    assert response.status_code == 200
    assert "api_key" not in response.text.lower()
    assert "sk-" not in response.text
    assert len(response.json()["scenic_spots"]) == 3


def test_request_validation():
    client = TestClient(api.app)
    for payload in [{"message": ""}, {"message": "x", "session_id": "../bad"}, {"message": "x", "api_key": "secret"}]:
        assert client.post("/api/plan", json=payload).status_code == 422


def test_ndjson_progress_and_session_context(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(api, "session_file", tmp_path / "sessions.json")

    class FakePlanner:
        def __init__(self, *args):
            pass

        def run(self, message, previous, history, emit):
            seen.append((previous, history))
            emit({"type": "progress", "stage": "understand", "label": "测试进度"})
            return {"status": "clarification", "message": "测试追问", "constraints": {"scenic_spot": "北京故宫"}}

    monkeypatch.setattr(api, "Planner", FakePlanner)
    client = TestClient(api.app)
    first = client.post("/api/plan", json={"message": "故宫"})
    events = [json.loads(x) for x in first.text.splitlines()]
    assert first.headers["content-type"].startswith("application/x-ndjson")
    assert [e["type"] for e in events] == ["session", "progress", "result"]
    sid = events[-1]["data"]["session_id"]
    assert (tmp_path / "sessions.json").exists()
    client.post("/api/plan", json={"message": "一天", "session_id": sid})
    assert seen[-1] == ({"scenic_spot": "北京故宫"}, ["故宫"])
    api.sessions.pop(sid, None)


def test_busy_request_rejected():
    sid = "a" * 32
    api.busy.add(sid)
    try:
        assert TestClient(api.app).post("/api/plan", json={"message": "一天", "session_id": sid}).status_code == 409
    finally:
        api.busy.discard(sid)


def test_export_is_attachment_and_validates_id(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "RUNS", tmp_path)
    rid = "b" * 32
    result = {"status": "ready", "steps": [{"order": 1}], "message": "测试导出"}
    (tmp_path / f"{rid}.json").write_text(json.dumps({"result": result}))
    client = TestClient(api.app)
    r = client.get(f"/api/export/{rid}")
    assert r.json() == result
    assert r.headers["content-disposition"].startswith("attachment;")
    assert client.get("/api/export/invalid").status_code == 422
    assert client.get("/api/export/" + "c" * 32).status_code == 404
