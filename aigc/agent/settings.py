"""Model connection settings for the Agent: private storage, explicit priority.

Priority, highest first: explicit process environment (``AIGC_AGENT_*``)
> the editable runtime file under the data dir > ``config.env`` > built-in
defaults. The runtime file is written atomically with 0600 permissions and is
ignored by Git, so the frontend never sees a full key.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx

from .redaction import redact_text

PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "siliconflow",
        "label": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": [
            "deepseek-ai/DeepSeek-V3.2",
            "Qwen/Qwen3-30B-A3B-Instruct",
            "Qwen/Qwen3-Next-80B-A3B-Instruct",
        ],
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    {
        "id": "openai",
        "label": "OpenAI 兼容服务",
        "base_url": "https://api.openai.com/v1",
        "models": [],
    },
    {"id": "custom", "label": "自定义地址", "base_url": "", "models": []},
]

SECRET_FILENAME = "model-connection.json"
TEST_MODEL_PROMPT = "Reply with the single word: ok"
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "connection_probe",
            "description": "Report readiness.",
            "parameters": {
                "type": "object",
                "properties": {"ready": {"type": "boolean"}},
                "required": ["ready"],
            },
        },
    }
]


class SettingsError(ValueError):
    pass


def provider_presets() -> list[dict[str, Any]]:
    return [
        {"id": p["id"], "label": p["label"], "base_url": p["base_url"], "models": p["models"]}
        for p in PROVIDERS
    ]


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return key[:3] + "•" * 6 + key[-2:]


def settings_path(data_dir) -> Path:
    path = Path(data_dir) / "agent"
    path.mkdir(parents=True, exist_ok=True)
    return path / SECRET_FILENAME


def _write_private(path: Path, body: dict[str, Any]) -> None:
    """Atomic write with owner-only permissions; never leaves a readable window."""
    payload = json.dumps(body, ensure_ascii=False, indent=2)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".connection-", suffix=".tmp")
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        with open(temporary, "w"):
            pass
        path.parent.joinpath(temporary).unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)


def _read_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text())
    except (ValueError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


class ConnectionSettings:
    """Effective connection values plus provenance, resolved once per run."""

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        provider: str = "custom",
        source: str = "default",
        remember: bool = True,
        timeout: float = 90.0,
        max_tool_rounds: int = 8,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self.source = source
        self.remember = remember
        self.timeout = timeout
        self.max_tool_rounds = max_tool_rounds

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def missing(self) -> list:
        return [
            name
            for name, value in (
                ("Base URL", self.base_url),
                ("API Key", self.api_key),
                ("模型", self.model),
            )
            if not value
        ]

    def public(self) -> dict[str, Any]:
        """Everything the frontend may see. Never the full key."""
        return {
            "configured": self.configured,
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "source": self.source,
            "remember": self.remember,
            "has_api_key": bool(self.api_key),
            "api_key_masked": mask_key(self.api_key),
            "max_tool_rounds": self.max_tool_rounds,
            "timeout_seconds": self.timeout,
        }

    def redacted(self) -> dict[str, Any]:
        value = self.public()
        value["api_key"] = ""
        return value


def load_settings(config: dict[str, Any] | None = None) -> ConnectionSettings:
    """Static startup config only; the editable file is applied by resolve()."""
    from ..config import load as load_config

    config = load_config() if config is None else config
    return ConnectionSettings(
        base_url=config.get("AIGC_AGENT_BASE_URL", "").rstrip("/"),
        api_key=config.get("AIGC_AGENT_API_KEY", ""),
        model=config.get("AIGC_AGENT_MODEL", ""),
        provider=config.get("AIGC_AGENT_PROVIDER", "custom"),
        source="env"
        if any(config.get("AIGC_AGENT_" + k) for k in ("BASE_URL", "API_KEY", "MODEL"))
        else "default",
        timeout=float(config.get("AIGC_AGENT_TIMEOUT", 90) or 90),
        max_tool_rounds=int(config.get("AIGC_AGENT_MAX_TOOL_ROUNDS", 8) or 8),
    )


def _startup_source(key: str) -> str:
    """'process' when the value comes from the environment, else 'file'."""
    return os.environ.get(key) or ""


def resolve(config: dict[str, Any] | None = None) -> ConnectionSettings:
    """Resolve per field, highest priority first:

    explicit process environment > the editable runtime file > ``config.env`` >
    built-in default. Merging ``config.env`` and the environment first would let a
    static ``config.env`` value silently win over a setting the user just saved in
    the UI, so each source is consulted separately.
    """
    from ..config import load as load_config

    config = load_config() if config is None else config
    data_dir = config.get("AIGC_DATA_DIR")
    if data_dir is None:
        data_dir = load_config()["AIGC_DATA_DIR"]
    stored = _read_file(settings_path(data_dir))
    stored_url = (stored.get("base_url") or "").rstrip("/")

    def pick(key: str, file_value: str) -> tuple[str, str]:
        env = _startup_source("AIGC_AGENT_" + key)
        if env:
            return env, "process"
        if file_value:
            return file_value, "runtime"
        return config.get("AIGC_AGENT_" + key, ""), "file"

    base_url, base_source = pick("BASE_URL", stored_url)
    model, model_source = pick("MODEL", stored.get("model") or "")
    provider, _ = pick("PROVIDER", stored.get("provider") or "")
    key, key_source = pick("API_KEY", stored.get("api_key") or "")
    # A key saved for one endpoint is never inherited by a different one. The
    # guard applies only to the *stored* key: a key configured in the process
    # environment belongs to the endpoint configured alongside it, so dropping it
    # would break a legitimate deployment override.
    if key_source == "runtime" and stored_url and base_url and base_url != stored_url:
        key, key_source = "", "file"
    source = (
        "process"
        if "process" in (base_source, model_source, key_source)
        else "runtime"
        if "runtime" in (base_source, model_source, key_source)
        else "file"
    )
    return ConnectionSettings(
        base_url=base_url,
        api_key=key,
        model=model,
        provider=provider or "custom",
        source=source,
        remember=bool(stored.get("remember", True)),
        timeout=float(config.get("AIGC_AGENT_TIMEOUT", 90) or 90),
        max_tool_rounds=int(config.get("AIGC_AGENT_MAX_TOOL_ROUNDS", 8) or 8),
    )


def save(
    config: dict[str, Any] | None,
    base_url: str,
    api_key: str,
    model: str,
    provider: str = "custom",
    remember: bool = True,
    keep_existing_key: bool = False,
) -> ConnectionSettings:
    """Persist an editable connection. Empty key + keep_existing_key keeps the old one."""
    base_url = (base_url or "").strip().rstrip("/")
    model = (model or "").strip()
    if not base_url:
        raise SettingsError("Base URL 不能为空")
    if not model:
        raise SettingsError("模型名称不能为空")
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise SettingsError("Base URL 必须以 http:// 或 https:// 开头")
    data_dir = (config or {}).get("AIGC_DATA_DIR")
    if data_dir is None:
        from ..config import load as load_config

        data_dir = load_config()["AIGC_DATA_DIR"]
    path = settings_path(data_dir)
    existing = _read_file(path)
    key = api_key
    if not key and keep_existing_key and existing.get("base_url", "").rstrip("/") == base_url:
        key = existing.get("api_key", "")
    body = {
        "base_url": base_url,
        "model": model,
        "provider": provider,
        "remember": bool(remember),
        "api_key": key,
        "schema_version": 1,
    }
    _write_private(path, body)
    return _public_from(body, "runtime")


def _public_from(body: dict[str, Any], source: str) -> ConnectionSettings:
    return ConnectionSettings(
        body.get("base_url", ""),
        body.get("api_key", ""),
        body.get("model", ""),
        body.get("provider", "custom"),
        source,
    )


def clear(config: dict[str, Any] | None = None) -> ConnectionSettings:
    """Forget the stored key and endpoint; static env config alone remains."""
    data_dir = (config or {}).get("AIGC_DATA_DIR")
    if data_dir is None:
        from ..config import load as load_config

        data_dir = load_config()["AIGC_DATA_DIR"]
    settings_path(data_dir).unlink(missing_ok=True)
    return load_settings(config)


async def list_models(settings: ConnectionSettings) -> dict[str, Any]:
    """Read the provider model list; failure is reported, never faked."""
    if not settings.base_url:
        return {"available": False, "models": [], "error": "尚未填写 Base URL"}
    if not settings.api_key:
        return {"available": False, "models": [], "error": "尚未填写 API Key"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                settings.base_url + "/models",
                headers={"Authorization": "Bearer " + settings.api_key},
            )
        if response.status_code in (401, 403):
            return {"available": False, "models": [], "error": "API Key 无效或已过期"}
        response.raise_for_status()
        data = response.json()
        models = sorted(
            str(item["id"])
            for item in data.get("data", [])
            if isinstance(item, dict) and item.get("id")
        )
        if not models:
            return {"available": False, "models": [], "error": "服务端未返回模型列表，可手动填写"}
        return {"available": True, "models": models, "error": ""}
    except Exception as error:  # surfaced verbatim; no silent fallback list
        return {
            "available": False,
            "models": [],
            "error": "读取模型列表失败：" + type(error).__name__,
        }


async def test_connection(settings: ConnectionSettings) -> dict[str, Any]:
    """One short, explicit model request that also probes tool calling.

    Never claims success: unsupported tools, missing models and bad credentials
    each get their own readable reason.
    """
    if not settings.configured:
        return {
            "ok": False,
            "reason": "incomplete",
            "detail": "缺少：" + "、".join(settings.missing()),
        }
    payload = {
        "model": settings.model,
        "messages": [{"role": "user", "content": TEST_MODEL_PROMPT}],
        "max_tokens": 16,
        "temperature": 0,
        "tools": TOOLS,
        "tool_choice": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=min(settings.timeout, 60)) as client:
            response = await client.post(
                settings.base_url + "/chat/completions",
                headers={"Authorization": "Bearer " + settings.api_key},
                json=payload,
            )
    except Exception as error:
        return {
            "ok": False,
            "reason": "unreachable",
            "detail": "无法连接 " + settings.base_url + "：" + type(error).__name__,
        }
    if response.status_code in (401, 403):
        return {"ok": False, "reason": "unauthorized", "detail": "API Key 被拒绝"}
    if response.status_code == 404:
        return {"ok": False, "reason": "model_missing", "detail": "模型不存在或地址不正确"}
    if response.status_code == 400 and _looks_like_tool_rejection(response.text):
        return {"ok": False, "reason": "no_tool_support", "detail": "该模型不支持工具调用"}
    if response.status_code >= 400:
        return {
            "ok": False,
            "reason": "http_" + str(response.status_code),
            "detail": redact_text(response.text, settings.api_key)[:400],
        }
    try:
        message = response.json()["choices"][0]["message"]
    except (ValueError, KeyError, IndexError):
        return {"ok": False, "reason": "bad_response", "detail": "返回内容无法解析"}
    content = (message.get("content") or "").strip()
    tool_calls = message.get("tool_calls") or []
    if not content and not tool_calls:
        return {"ok": False, "reason": "empty_response", "detail": "模型返回了空内容"}
    return {
        "ok": True,
        "reason": "ok",
        "detail": "连接成功",
        "supports_tools": bool(tool_calls) or _declares_tools(response.text),
        "model": settings.model,
        "base_url": settings.base_url,
        "answered": redact_text(content, settings.api_key)[:120],
    }


def _looks_like_tool_rejection(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in ("tool", "function_call", "tools"))


def _declares_tools(text: str) -> bool:
    return "tool_calls" in (text or "")
