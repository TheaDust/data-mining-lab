"""Local API and NDJSON progress stream. No credentials sent to browsers."""
import asyncio
import json
import os
import uuid
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Path as PathParameter
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from task7.graph_view import graph_payload
from task7.agent import Planner
from task7.llm import DeepSeek
from task7.models import PlanRequest
from task7.tools import Knowledge

app = FastAPI(title="山行 · 景区游览规划", docs_url="/api/docs", openapi_url="/api/openapi.json")
knowledge = Knowledge()
session_file = Path(__file__).parent / "results/runs/sessions.json"
try:
    sessions = OrderedDict(json.loads(session_file.read_text(encoding="utf-8")))
except (OSError, ValueError):
    sessions = OrderedDict()
busy = set()
gate = asyncio.Semaphore(2)
RUNS = Path(__file__).parent / "results/runs"


@app.get("/api/graph")
def graph():
    return graph_payload(knowledge)


@app.get("/api/health")
def health():
    model = DeepSeek()
    return {"status": "ok", "model_configured": bool(model.key), "model": model.model,
            "scenic_spots": knowledge.store.scenic_spots(), "stats": knowledge.store.stats()}


@app.get("/api/export/{request_id}")
def export_result(request_id: str = PathParameter(pattern=r"^[0-9a-f]{32}$")):
    try:
        record = json.loads((RUNS / f"{request_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(404, "该结果的本机日志不存在，可能已经清理。")
    return JSONResponse(record["result"], headers={"Content-Disposition": f'attachment; filename="shanxing-{request_id[:8]}.json"',
                                                  "Cache-Control": "no-store"})


@app.post("/api/plan")
async def plan(body: PlanRequest):
    sid = body.session_id or uuid.uuid4().hex
    if sid in busy:
        raise HTTPException(409, "上一条需求仍在处理，请稍后再试。")
    busy.add(sid)
    old = sessions.get(sid, {})
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def emit_progress(event):
        # Preserve ordering across the worker thread and async response. Scheduling
        # put_nowait without awaiting it can let the final result overtake progress.
        asyncio.run_coroutine_threadsafe(queue.put(event), loop).result(timeout=5)

    async def work():
        try:
            async with gate:
                planner = Planner(knowledge, DeepSeek())
                result = await asyncio.to_thread(planner.run, body.message, old.get("constraints"), old.get("messages", []), emit_progress)
                result["session_id"] = sid
                if result["status"] != "error":
                    sessions[sid] = {"constraints": result["constraints"],
                                     "messages": (old.get("messages", []) + [body.message])[-8:]}
                    sessions.move_to_end(sid)
                    while len(sessions) > 100:
                        sessions.popitem(last=False)
                    session_file.parent.mkdir(parents=True, exist_ok=True)
                    temporary = session_file.with_suffix(".tmp")
                    temporary.write_text(json.dumps(list(sessions.items()), ensure_ascii=False), encoding="utf-8")
                    temporary.replace(session_file)
                await queue.put({"type": "result", "data": result})
        except Exception:
            # Internal diagnostics belong in server logs, not streamed exception strings.
            import logging
            logging.exception("Planning request failed")
            await queue.put({"type": "result", "data": {"status": "error", "session_id": sid,
                "message": "规划服务发生异常，请稍后重试。"}})
        finally:
            busy.discard(sid)
            await queue.put(None)

    task = asyncio.create_task(work())

    async def events():
        try:
            yield json.dumps({"type": "session", "session_id": sid}) + "\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield '{"type":"heartbeat"}\n'
                    continue
                if event is None:
                    break
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            # httpx call in a thread is not interruptible. Keep request marked busy
            # until it really finishes; do not start a duplicate billable request.
            if not task.done():
                task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


dist = Path(__file__).parent / "web/dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="web")
