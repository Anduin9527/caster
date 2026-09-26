"""SSE wire framing, cursor recovery and idle behavior without a real network."""

import asyncio
import json

import httpx

from aigc.agent.contracts import AgentEvent
from aigc.agent.events import EventLog
from aigc.agent.router import sse_frames
from aigc.agent.sessions import Conversation
from aigc.api import create_app
from aigc.store import Store


def test_stream_advances_cursor_and_stops_when_disconnected():
    cursors, frames = [], []

    def since(conversation, cursor):
        cursors.append((conversation, cursor))
        sequence = len(cursors)
        return [
            AgentEvent(
                event_id=f"c:{sequence}",
                conversation_id="c",
                type="activity",
                payload={"n": sequence},
            )
        ]

    async def disconnected():
        return len(frames) == 2

    async def scenario():
        async for frame in sse_frames(since, "c", "", disconnected, idle_sleep=0):
            frames.append(frame)

    asyncio.run(scenario())
    assert cursors == [("c", ""), ("c", "c:1")]
    for sequence, frame in enumerate(frames, 1):
        assert frame.startswith(f"id: c:{sequence}\ndata: ") and frame.endswith("\n\n")
        assert json.loads(frame.split("data: ")[1])["event_id"] == f"c:{sequence}"


def test_idle_heartbeat_does_not_create_a_business_event():
    frames = []

    async def disconnected():
        return bool(frames)

    async def scenario():
        async for frame in sse_frames(
            lambda *_args: [], "c", "", disconnected, idle_sleep=0, heartbeat=0
        ):
            frames.append(frame)

    asyncio.run(scenario())
    assert frames == [": keep-alive\n\n"]


def test_http_stream_resumes_from_last_event_id_header(tmp_path, monkeypatch):
    import aigc.agent.router as router

    store = Store(tmp_path)
    conversation = Conversation(store).create(None)["id"]
    log = EventLog(store)
    first = log.append(conversation, None, "activity", {"n": 1})
    last = log.append(conversation, None, "activity", {"n": 2})
    captured = []

    async def finite_stream(events_since, conversation_id, cursor, is_disconnected):
        captured.append(cursor)
        yield ": finished\n\n"

    monkeypatch.setattr(router, "sse_frames", finite_stream)
    app = create_app(store=store)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            url = f"/agent/conversations/{conversation}/events"
            response = await client.get(
                url, params={"after": first.event_id}, headers={"Last-Event-ID": last.event_id}
            )
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert (await client.get(url, headers={"Last-Event-ID": "missing"})).status_code == 404
            assert (await client.get("/agent/conversations/unknown/events")).status_code == 404

    asyncio.run(scenario())
    assert captured == [last.event_id]


def test_long_conversation_snapshot_uses_recent_events_and_a_current_cursor(tmp_path):
    store = Store(tmp_path)
    conversation = Conversation(store).create(None)["id"]
    log = EventLog(store)
    for number in range(250):
        log.append(conversation, None, "activity", {"n": number})
    other = log.append("other", None, "activity", {})
    app = create_app(store=store)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(f"/agent/conversations/{conversation}")
            assert response.status_code == 200
            events = response.json()["events"]
            assert [event["payload"]["n"] for event in events] == list(range(50, 250))
            assert log.since(conversation, events[-1]["event_id"]) == []
            assert other.event_id not in [event["event_id"] for event in events]

    asyncio.run(scenario())
