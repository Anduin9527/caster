"""LlamaIndex framework adapter; the only production model/tool loop."""

from typing import Any, Callable

from llama_index.core.agent import FunctionAgent

from .prompting import AgentPublicResponse, structured_public_response
from .redaction import redact_text
from .settings import ConnectionSettings


class RunLimits:
    def __init__(
        self,
        max_tool_rounds: int = 8,
        timeout: float = 90.0,
        max_history: int = 12,
        max_deltas: int = 2000,
    ):
        self.max_tool_rounds = max_tool_rounds
        self.timeout = timeout
        self.max_history = max_history
        self.max_deltas = max_deltas


class RunOutcome:
    def __init__(
        self, run_id: str, status: str, text: str = "", error: str = "", tool_calls: int = 0
    ):
        self.run_id = run_id
        self.status = status
        self.text = text
        self.error = error
        self.tool_calls = tool_calls


class _HashableFunctionAgent(FunctionAgent):
    """FunctionAgent with a usable hash.

    ``FunctionAgent`` is a pydantic model, so pydantic sets ``__hash__ = None``.
    The workflow runtime caches serializers in a ``WeakKeyDictionary`` and fails
    with ``TypeError: unhashable type`` before any request is made. Identity
    hashing is enough for that cache and changes no agent behaviour.
    """

    def __hash__(self):
        return id(self)


class LlamaIndexBackend:
    """The production agent loop: LlamaIndex FunctionAgent + OpenAILike.

    ``llm_factory`` exists so the real adapter (agent construction, tool loop,
    response handling) can be exercised without a model endpoint; production
    callers leave it unset and get OpenAILike.
    """

    def __init__(self, settings: ConnectionSettings, llm_factory=None):
        self.settings = settings
        self.llm_factory = llm_factory

    def _llm(self):
        if self.llm_factory is not None:
            return self.llm_factory()
        from llama_index.llms.openai_like import OpenAILike

        return OpenAILike(
            model=self.settings.model,
            api_key=self.settings.api_key,
            api_base=self.settings.base_url,
            is_chat_model=True,
            temperature=0.2,
            timeout=self.settings.timeout,
            max_retries=1,
            is_function_calling_model=True,
        )

    async def run(
        self,
        tools: list,
        system_prompt,
        history: list[dict[str, str]],
        user_message: str,
        limits: RunLimits,
        emit: Callable[[str, dict[str, Any]], None],
    ) -> RunOutcome:
        from llama_index.core.base.llms.types import ChatMessage
        from llama_index.core.prompts import BasePromptTemplate

        llm = self._llm()
        rendered_prompt = (
            system_prompt.format(llm=llm)
            if isinstance(system_prompt, BasePromptTemplate)
            else str(system_prompt)
        )
        agent = _HashableFunctionAgent(
            name="CASTER",
            tools=tools,
            llm=llm,
            system_prompt=rendered_prompt,
            streaming=False,
            structured_output_fn=structured_public_response,
            allow_parallel_tool_calls=False,
            early_stopping_method="generate",
            verbose=False,
            timeout=limits.timeout,
        )
        # The agent keeps its own chat memory; pass the prior turns as history and
        # the current turn as the start event's user_msg.
        messages = [
            ChatMessage(role=m["role"], content=m["content"])
            for m in history[-limits.max_history :]
            if m.get("content")
        ]
        result = await agent.run(
            user_msg=user_message, chat_history=messages, max_iterations=limits.max_tool_rounds
        )
        structured = getattr(result, "structured_response", None)
        if isinstance(structured, AgentPublicResponse):
            text = structured.final_markdown
        elif isinstance(structured, dict) and "final_markdown" in structured:
            text = str(structured["final_markdown"] or "")
        else:
            # Old/custom workflow adapters may not expose structured_response;
            # normalize their final message through the same framework hook.
            response = getattr(result, "response", result)
            text = structured_public_response(
                [ChatMessage(role="assistant", content=str(response or ""))]
            )["final_markdown"]
        # Redact before chunking: a long key may span several public deltas.
        text = redact_text(text, self.settings.api_key if self.settings is not None else "")
        for index, chunk in enumerate(_chunks(text, 80)[: limits.max_deltas]):
            emit("message.delta", {"index": index, "text": chunk})
        return RunOutcome("", "completed", text=text, tool_calls=0)


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]
