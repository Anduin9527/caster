"""Application-owned Agent runs, cancellation, recovery and persistence."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .backend import LlamaIndexBackend, RunLimits, RunOutcome
from .events import EventLog
from .prompting import SYSTEM_PROMPT_TEMPLATE, build_system_prompt
from .redaction import redact, redact_text
from .sessions import Conversation
from .settings import ConnectionSettings
from .settings import resolve as resolve_settings

_CANCEL_GRACE = 5.0
SYSTEM_PROMPT = build_system_prompt()


@dataclass(eq=False)
class _RunAttempt:
    run_id: str
    owner: asyncio.Task
    task: asyncio.Task | None = None
    closed: bool = False
    secrets: tuple[str, ...] = field(default=(), repr=False)


def _public_run_error(error: str) -> str:
    """Translate framework mechanics into an actionable public failure."""
    detail = str(error or "")
    if "Max iterations" in detail or "max iterations" in detail:
        return "检索步骤过多，本轮未能形成最终回复。已保留工具记录，请调整条件后重试。"
    return detail


async def _settle(task: asyncio.Task) -> bool:
    """Wait for a cancelled backend to actually finish. True if it did."""
    _, pending = await asyncio.wait({task}, timeout=_CANCEL_GRACE)
    return not pending


class AgentEngine:
    def __init__(self, store, config: dict[str, Any] | None = None):
        self.store = store
        self.config = config or {}
        self.sessions = Conversation(store)
        self.events = EventLog(store)
        self._semantic = None
        self._active: dict[str, _RunAttempt] = {}
        self._tasks: set[asyncio.Task] = set()
        self._closing = False

    # -- recovery ----------------------------------------------------------- #
    def recover_interrupted(self) -> list[str]:
        """Mark runs left ``running`` by a previous process as interrupted.

        Call this once at service start-up, before accepting requests. Only
        unfinished persisted runs are touched, so recovery is idempotent.
        """
        stale = []
        for run in self.store.list("agent_run"):
            if run.get("status") not in ("running", "stopping"):
                continue
            run_id = run["id"]
            self.sessions.finish_run(
                run_id, "interrupted", error="服务重启导致本轮中断，可继续提问"
            )
            self.events.append(
                run["conversation_id"],
                run_id,
                "run.failed",
                {"reason": "interrupted", "detail": "服务重启导致本轮中断"},
            )
            stale.append(run_id)
        return stale

    # -- helpers ------------------------------------------------------------ #
    def _limits(self, settings: ConnectionSettings) -> RunLimits:
        return RunLimits(max_tool_rounds=settings.max_tool_rounds, timeout=settings.timeout)

    def build_tools(self, conversation_id: str, context, run_id: str | None = None, *, emit=None):
        from .planner import Planner
        from .retrieval import RetrievalService
        from .tools import AgentTools, build_tools

        character = (
            self.store.get("character", context.character_id) if context.character_id else None
        )
        ctx = AgentTools(
            self.store,
            RetrievalService(self.store, self.semantic_backend(), config=self.config),
            Planner(self.store),
            conversation_id,
            context,
            character,
            emit or self._emit_for(conversation_id, run_id),
        )
        return ctx, build_tools(ctx)

    def semantic_backend(self):
        """The vector index backend, or None when it is not deployed.

        Reused by this application's conversations. Returning None is the supported
        "semantic search unavailable" state, which retrieval reports to the user
        instead of silently returning fewer hits.
        """
        if self._semantic is None:
            from ..rag import build_backend

            self._semantic = build_backend(self.config)
        return self._semantic

    def _emit_for(self, conversation_id: str, run_id: str | None = None, attempt=None):
        def emit(type: str, payload: dict[str, Any]) -> None:
            if attempt is not None and attempt.closed:
                return
            self.events.append(
                conversation_id,
                run_id,
                type,
                redact(payload, *(attempt.secrets if attempt else ())),
            )

        return emit

    # -- the run ------------------------------------------------------------ #
    async def run_message(
        self,
        conversation_id: str,
        text: str,
        context,
        backend=None,
        idempotency_key: str | None = None,
    ) -> RunOutcome:
        from .contracts import WorkbenchContext

        if self._closing:
            raise RuntimeError("服务正在关闭，请稍后重试")
        context = WorkbenchContext.model_validate(context)
        self.sessions.get(conversation_id)
        message = self.sessions.add_message(
            conversation_id, "user", text, idempotency_key=idempotency_key, context=context
        )
        run_id = "run-" + message["id"]
        replay = self.store.get("agent_run", run_id)
        if replay and replay.get("status") not in ("failed",):
            return RunOutcome(run_id, replay["status"], error=replay.get("error", ""))
        run = self.sessions.start_run(conversation_id, message["id"], run_id=run_id)
        run_id = run["id"]
        # Each attempt owns an irreversible guard. A retry can reuse the run ID
        # without reopening tools or event callbacks from an earlier attempt.
        attempt = _RunAttempt(run_id, asyncio.current_task())
        self._active[run_id] = attempt
        metadata = {}
        try:
            settings = resolve_settings(self.config)
            attempt.secrets = (settings.api_key,)
            if backend is None:
                if not settings.configured:
                    error = "尚未配置模型连接：" + "、".join(settings.missing())
                    self.sessions.finish_run(run_id, "failed", error=error)
                    self.events.append(
                        conversation_id,
                        run_id,
                        "run.failed",
                        {"reason": "not_configured", "missing": settings.missing()},
                    )
                    return RunOutcome(run_id, "failed", error=error)
                backend = LlamaIndexBackend(settings)
            limits = self._limits(settings)
            emit = self._emit_for(conversation_id, run_id, attempt)
            ctx, tools = self.build_tools(conversation_id, context, run_id, emit=emit)
            ctx.closed = lambda: attempt.closed
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in self.sessions.history(conversation_id)
                if m.get("content") and m["id"] != message["id"]
            ]
            task = asyncio.create_task(
                backend.run(tools, SYSTEM_PROMPT_TEMPLATE, history, text, limits, emit),
                name="caster-agent-" + run_id,
            )
            attempt.task = task
            self._tasks.add(task)
            task.add_done_callback(self._task_done)
            try:
                outcome = await asyncio.wait_for(asyncio.shield(task), timeout=limits.timeout)
            except asyncio.TimeoutError:
                attempt.closed = True
                task.cancel()
                await _settle(task)
                outcome = RunOutcome(run_id, "failed", error="模型响应超时，草稿已保留")
            outcome.run_id = run_id
            outcome.text = redact_text(outcome.text, *attempt.secrets)
            outcome.error = redact_text(outcome.error, *attempt.secrets)
            metadata = {
                "tool_calls": len(ctx.calls),
                "model": settings.model,
                "base_url": settings.base_url,
            }
            current = self.sessions.get_run(run_id)
            if current["status"] in ("stopped", "interrupted"):
                return RunOutcome(run_id, current["status"], error=current.get("error", ""))
            if outcome.status == "completed":
                self.sessions.add_message(
                    conversation_id,
                    "assistant",
                    outcome.text,
                    kind="assistant",
                    extra={"run_id": run_id},
                )
                emit("message.completed", {"text": outcome.text})
                self.events.append(conversation_id, run_id, "run.completed", metadata)
                self.sessions.finish_run(run_id, "completed", **metadata)
            else:
                self._fail(conversation_id, outcome, metadata)
            return outcome
        except asyncio.CancelledError:
            attempt.closed = True
            current = self.sessions.get_run(run_id)
            decided = current["status"] in ("stopped", "interrupted")
            if not decided:
                self._interrupt(run_id, "请求已中断，可继续提问")
            if attempt.task is not None:
                if not attempt.task.done() and not attempt.task.cancelling():
                    attempt.task.cancel()
                await _settle(attempt.task)
            if decided:
                return RunOutcome(run_id, current["status"], error=current.get("error", ""))
            raise
        except Exception as error:  # a model failure must not look like success
            outcome = RunOutcome(
                run_id,
                "failed",
                error=type(error).__name__ + "：" + redact_text(str(error), *attempt.secrets)[:400],
            )
            self._fail(conversation_id, outcome, metadata)
            return outcome
        finally:
            attempt.closed = True
            if self._active.get(run_id) is attempt:
                del self._active[run_id]

    def _fail(self, conversation_id: str, outcome: RunOutcome, metadata: dict) -> None:
        outcome.error = _public_run_error(outcome.error)
        self.sessions.finish_run(outcome.run_id, "failed", error=outcome.error[:2000], **metadata)
        self.events.append(
            conversation_id,
            outcome.run_id,
            "run.failed",
            {"reason": "backend_error", "detail": outcome.error[:500]},
        )

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        # A task that outlives cancellation still has its exceptions consumed.
        if not task.cancelled():
            task.exception()

    def _interrupt(self, run_id: str, reason: str) -> None:
        run = self.sessions.finish_run(run_id, "interrupted", error=reason)
        self.events.append(
            run["conversation_id"],
            run_id,
            "run.failed",
            {"reason": "interrupted", "detail": reason},
        )

    @staticmethod
    def _cancel_attempt(attempt: _RunAttempt) -> None:
        attempt.closed = True
        if attempt.task is not None and not attempt.task.done():
            attempt.task.cancel()
        if attempt.owner is not asyncio.current_task() and not attempt.owner.done():
            attempt.owner.cancel()

    async def close(self) -> None:
        """End this application's runs and drain its model tasks on shutdown."""
        if self._closing:
            return
        self._closing = True
        for run_id, attempt in list(self._active.items()):
            current = self.sessions.get_run(run_id)
            if current["status"] in ("running", "stopping"):
                self._interrupt(run_id, "服务关闭导致本轮中断，可继续提问")
            self._cancel_attempt(attempt)
        for task in self._tasks:
            if not task.done() and not task.cancelling():
                task.cancel()
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=_CANCEL_GRACE)
        if self._semantic is not None:
            self._semantic.close()
            self._semantic = None

    def stop(self, run_id: str) -> dict[str, Any]:
        """Stop this run. Already queued jobs are not cancelled here."""
        run = self.sessions.get_run(run_id)
        if run["status"] not in ("running", "stopping"):
            return run
        record = self.sessions.finish_run(run_id, "stopped", error="已停止本轮回复")
        attempt = self._active.get(run_id)
        if attempt is not None:
            self._cancel_attempt(attempt)
        self.events.append(
            run["conversation_id"],
            run_id,
            "run.failed",
            {"reason": "stopped_by_user", "detail": "已停止本轮回复；已入队任务不受影响"},
        )
        return record
