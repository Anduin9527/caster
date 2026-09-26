"""Offline lifecycle contracts for retries, cancellation and app isolation."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from aigc import api
from aigc.agent import engine
from aigc.agent.events import EventLog
from aigc.agent.sessions import Conversation
from aigc.store import Store


class Reply:
    def __init__(self, fail=False):
        self.fail = fail
        self.emit = None
        self.tools = {}
        self.history = []

    async def run(self, tools, system_prompt, history, user_message, limits, emit):
        self.emit = emit
        self.tools = {tool.metadata.name: tool for tool in tools}
        self.history = history
        if self.fail:
            raise RuntimeError("offline failure")
        emit("activity", {"who": "current-attempt"})
        return engine.RunOutcome("", "completed", text="完成")


class Blocking(Reply):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def run(self, *args):
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return await super().run(*args)


@pytest.fixture
def agent(tmp_path):
    return engine.AgentEngine(Store(tmp_path), {"AIGC_DATA_DIR": str(tmp_path)})


def test_failed_retry_gets_new_writable_tools_and_events(agent):
    conversation = agent.sessions.create(None)["id"]
    failed = Reply(fail=True)
    retried = Reply()

    async def scenario():
        first = await agent.run_message(
            conversation, "重试同一条消息", {}, backend=failed, idempotency_key="request"
        )
        assert first.status == "failed"
        second = await agent.run_message(
            conversation, "重试同一条消息", {}, backend=retried, idempotency_key="request"
        )
        assert second.run_id == first.run_id and second.status == "completed"

    asyncio.run(scenario())
    events = agent.events.since(conversation)
    assert any(event.payload.get("who") == "current-attempt" for event in events)
    assert any(event.type == "message.completed" for event in events)
    failed.emit("activity", {"who": "old-attempt"})
    assert agent.events.since(conversation) == events
    with pytest.raises(ValueError, match="本轮已结束"):
        failed.tools["prepare_generation_plan"].call(intent="跳起来")
    assert [message["role"] for message in agent.sessions.history(conversation)] == [
        "user",
        "assistant",
    ]


def test_retry_history_excludes_its_message_without_dropping_newer_turns(agent):
    conversation = agent.sessions.create(None)["id"]
    retried = Reply()

    async def scenario():
        await agent.run_message(
            conversation, "旧消息", {}, backend=Reply(True), idempotency_key="old"
        )
        await agent.run_message(
            conversation, "后来的消息", {}, backend=Reply(), idempotency_key="new"
        )
        await agent.run_message(conversation, "旧消息", {}, backend=retried, idempotency_key="old")

    asyncio.run(scenario())
    assert [message["content"] for message in retried.history] == ["后来的消息", "完成"]


def test_finished_callbacks_stay_closed_after_many_later_runs(agent):
    first = Reply()
    conversation = agent.sessions.create(None)["id"]

    async def scenario():
        await agent.run_message(conversation, "第一轮", {}, backend=first)
        for index in range(70):
            other = agent.sessions.create(None)["id"]
            await agent.run_message(other, str(index), {}, backend=Reply())

    asyncio.run(scenario())
    events = agent.events.since(conversation)
    first.emit("activity", {"who": "very-late"})
    assert agent.events.since(conversation) == events
    with pytest.raises(ValueError, match="本轮已结束"):
        first.tools["prepare_generation_plan"].call(intent="跳起来")
    with pytest.raises(ValueError, match="本轮已结束"):
        first.tools["get_service_capabilities"].call()


def test_request_cancellation_cancels_backend_and_releases_conversation(agent):
    conversation = agent.sessions.create(None)["id"]
    backend = Blocking()

    async def scenario():
        request = asyncio.create_task(agent.run_message(conversation, "你好", {}, backend=backend))
        await backend.started.wait()
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert backend.cancelled
        assert agent.sessions.get(conversation)["active_run_id"] is None
        assert agent.sessions.runs(conversation)[0]["status"] == "interrupted"
        assert (
            await agent.run_message(conversation, "下一轮", {}, backend=Reply())
        ).status == "completed"

    asyncio.run(scenario())


def test_tool_setup_failure_is_persisted_as_failure_and_is_retryable(agent, monkeypatch):
    conversation = agent.sessions.create(None)["id"]
    original = agent.build_tools

    def broken(*_args, **_kwargs):
        raise RuntimeError("tool setup failed")

    async def scenario():
        monkeypatch.setattr(agent, "build_tools", broken)
        failed = await agent.run_message(
            conversation, "你好", {}, backend=Reply(), idempotency_key="k"
        )
        assert failed.status == "failed" and "tool setup failed" in failed.error
        assert agent.sessions.get(conversation)["active_run_id"] is None
        monkeypatch.setattr(agent, "build_tools", original)
        assert (
            await agent.run_message(conversation, "你好", {}, backend=Reply(), idempotency_key="k")
        ).status == "completed"

    asyncio.run(scenario())


@pytest.mark.parametrize("secret", ["sk-test-secret-123456789", "provider-key-without-prefix"])
def test_model_errors_are_redacted_before_persistence_and_event_validation(agent, secret):
    agent.config["AIGC_AGENT_API_KEY"] = secret
    conversation = agent.sessions.create(None)["id"]

    class Leaks:
        async def run(self, *args):
            raise RuntimeError("provider rejected " + secret)

    outcome = asyncio.run(agent.run_message(conversation, "你好", {}, backend=Leaks()))
    assert outcome.status == "failed"
    run = agent.sessions.get_run(outcome.run_id)
    events = [event.model_dump() for event in agent.events.since(conversation)]
    assert secret not in outcome.error
    assert secret not in json.dumps([run, events], ensure_ascii=False)
    assert events[-1]["type"] == "run.failed"
    assert "已隐藏" in run["error"]


def test_model_response_and_stream_cannot_echo_the_connection_key(agent):
    secret = "opaque-provider-credential"
    agent.config["AIGC_AGENT_API_KEY"] = secret
    conversation = agent.sessions.create(None)["id"]

    class Echoes:
        async def run(self, tools, system_prompt, history, user_message, limits, emit):
            emit("message.delta", {"text": secret})
            return engine.RunOutcome("", "completed", text=secret)

    outcome = asyncio.run(agent.run_message(conversation, "你好", {}, backend=Echoes()))
    assert outcome.status == "completed" and secret not in outcome.text
    stored = [
        agent.sessions.history(conversation),
        [event.model_dump() for event in agent.events.since(conversation)],
    ]
    assert secret not in json.dumps(stored, ensure_ascii=False)


@pytest.mark.parametrize("status", [200, 500])
def test_connection_probe_redacts_provider_echoes(monkeypatch, status):
    import httpx

    from aigc.agent import settings

    secret = "test-private-provider-credential"
    original_client = httpx.AsyncClient

    def respond(_request):
        if status == 200:
            return httpx.Response(status, json={"choices": [{"message": {"content": secret}}]})
        return httpx.Response(status, text="provider error: " + secret)

    monkeypatch.setattr(
        settings.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    result = asyncio.run(
        settings.test_connection(
            settings.ConnectionSettings("https://example.invalid/v1", secret, "offline")
        )
    )
    assert secret not in json.dumps(result)
    assert result["ok"] is (status == 200)


def test_identical_run_ids_in_different_apps_cannot_cancel_each_other(tmp_path):
    left = engine.AgentEngine(Store(tmp_path / "left"))
    right = engine.AgentEngine(Store(tmp_path / "right"))
    conversation = left.sessions.create(None)
    right.store.put("agent_conversation", conversation, conversation["id"])
    first, second = Blocking(), Blocking()

    async def scenario():
        requests = [
            asyncio.create_task(
                agent.run_message(
                    conversation["id"],
                    "相同 ID",
                    {},
                    backend=backend,
                    idempotency_key="same",
                )
            )
            for agent, backend in ((left, first), (right, second))
        ]
        await first.started.wait()
        await second.started.wait()
        run_id = left.sessions.runs(conversation["id"])[0]["id"]
        left.stop(run_id)
        assert (await requests[0]).status == "stopped"
        assert first.cancelled
        assert not second.cancelled and not requests[1].done()
        second.release.set()
        assert (await requests[1]).status == "completed"

    asyncio.run(scenario())


def test_lifespan_shutdown_closes_owned_agent_runs(tmp_path):
    class OfflineComfy:
        async def close(self):
            pass

    store = Store(tmp_path)
    app = api.create_app(store=store, comfy=OfflineComfy())
    backend = Blocking()

    async def scenario():
        async with app.router.lifespan_context(app):
            agent = app.state.agent
            conversation = agent.sessions.create(None)["id"]
            request = asyncio.create_task(
                agent.run_message(conversation, "你好", {}, backend=backend)
            )
            await backend.started.wait()
        assert (await request).status == "interrupted"
        assert backend.cancelled
        assert agent.sessions.get(conversation)["active_run_id"] is None
        assert app.state.agent is None
        with pytest.raises(RuntimeError, match="关闭"):
            await agent.run_message(conversation, "新请求", {}, backend=Reply())

    asyncio.run(scenario())


def test_failed_retry_cannot_displace_another_active_run(agent):
    conversation = agent.sessions.create(None)["id"]
    failed = agent.sessions.start_run(conversation, "old-message")
    agent.sessions.finish_run(failed["id"], "failed")
    active = agent.sessions.start_run(conversation, "new-message")
    with pytest.raises(RuntimeError, match="已有一轮"):
        agent.sessions.start_run(conversation, "old-message")
    assert agent.sessions.get(conversation)["active_run_id"] == active["id"]
    assert agent.sessions.get_run(failed["id"])["status"] == "failed"


def test_concurrent_run_claims_have_one_winner(agent):
    conversation = agent.sessions.create(None)["id"]
    ready = Barrier(8)

    def start(index):
        ready.wait()
        try:
            return Conversation(agent.store).start_run(conversation, f"message-{index}")
        except RuntimeError:
            return None

    with ThreadPoolExecutor(max_workers=8) as workers:
        winners = [record for record in workers.map(start, range(8)) if record]
    assert len(winners) == 1
    assert agent.sessions.get(conversation)["run_count"] == 1
    assert agent.sessions.get(conversation)["active_run_id"] == winners[0]["id"]


def test_concurrent_message_replays_do_not_duplicate_or_lose_counts(agent):
    conversation = agent.sessions.create(None)["id"]
    ready = Barrier(8)

    def replay(_index):
        ready.wait()
        return Conversation(agent.store).add_message(
            conversation, "user", "同一请求", idempotency_key="key"
        )

    with ThreadPoolExecutor(max_workers=8) as workers:
        messages = list(workers.map(replay, range(8)))
    assert len({message["id"] for message in messages}) == 1
    assert agent.sessions.get(conversation)["message_count"] == 1


def test_rejected_message_is_not_left_in_history(agent):
    conversation = agent.sessions.create(None)["id"]
    agent.sessions.start_run(conversation, "active")
    with pytest.raises(RuntimeError, match="已有一轮"):
        agent.sessions.add_message(conversation, "user", "不能进入历史")
    assert agent.sessions.history(conversation) == []
    assert agent.sessions.get(conversation)["message_count"] == 0


def test_event_pages_resume_in_order_without_loading_other_conversations(agent, monkeypatch):
    log = EventLog(agent.store)
    for index in range(215):
        log.append("main", "run", "activity", {"n": index})
        log.append("other", "run", "activity", {"n": index})

    def no_full_scan(_kind):
        raise AssertionError("event polling must not load the entire record collection")

    monkeypatch.setattr(agent.store, "list", no_full_scan)
    first = log.since("main")
    second = log.since("main", first[-1].event_id)
    assert [event.payload["n"] for event in first + second] == list(range(215))
    assert len(first) == 200 and len(second) == 15
    assert log.since("main", second[-1].event_id) == []
    assert log.since("main", limit=0) == []
    with pytest.raises(LookupError):
        log.since("other", first[-1].event_id)
    with pytest.raises(LookupError):
        log.since("main", "missing-cursor")
