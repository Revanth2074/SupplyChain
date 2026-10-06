"""OpenAI-compatible LLM wrapper (aicredits.in gateway). Gracefully degrades
when no key is configured so the rest of the system still works."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAI

from .config import settings

log = logging.getLogger("llm")

_client: OpenAI | None = None


def available() -> bool:
    return bool(settings.LLM_API_KEY)


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY or "none",
                         timeout=90, max_retries=2)
    return _client


def chat(messages: list[dict], model: str | None = None, temperature: float = 0.2,
         max_tokens: int = 1200) -> str:
    if not available():
        raise RuntimeError("LLM not configured")
    r = client().chat.completions.create(
        model=model or settings.LLM_MODEL, messages=messages,
        temperature=temperature, max_tokens=max_tokens,
    )
    return r.choices[0].message.content or ""


_JSON_RE = re.compile(r"\{.*\}", re.S)


def chat_json(system: str, user: str, model: str | None = None, temperature: float = 0.1,
              max_tokens: int = 1200) -> dict[str, Any]:
    msgs = [{"role": "system", "content": system + "\nRespond ONLY with a valid JSON object."},
            {"role": "user", "content": user}]
    txt = chat(msgs, model=model, temperature=temperature, max_tokens=max_tokens)
    txt = txt.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        txt = txt[txt.find("{"):]
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        m = _JSON_RE.search(txt)
        if m:
            return json.loads(m.group(0))
        raise
