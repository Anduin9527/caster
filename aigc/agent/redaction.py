"""Redact model credentials before data enters public responses or event logs."""

import re
from typing import Any

_TOKEN = re.compile(r"\b(?:sk-[A-Za-z0-9_\-]{8,}|Bearer\s+\S{8,})\b", re.I)
_HIDDEN = "[已隐藏凭据形文本]"


def contains_credential(text: str) -> bool:
    return bool(_TOKEN.search(text))


def redact_text(text: str, *secrets: str) -> str:
    for secret in sorted({value for value in secrets if value}, key=len, reverse=True):
        text = text.replace(secret, _HIDDEN)
    return _TOKEN.sub(_HIDDEN, text)


def redact(value: Any, *secrets: str) -> Any:
    if isinstance(value, dict):
        return {key: redact(item, *secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, *secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, *secrets)
    return value
