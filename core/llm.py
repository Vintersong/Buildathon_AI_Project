"""Unified multi-provider LLM dispatch.

Every LLM call in the app goes through :func:`complete`. It routes to whichever
provider is selected in ``config.json`` (``provider`` field) using a per-provider
API key stored in ``.secrets.json`` (gitignored). Supported providers:

    - ``gemini``   — Google Gemini (``google-generativeai``)
    - ``openai``   — OpenAI / GPT (``openai``)
    - ``anthropic``— Anthropic / Claude (``anthropic``)
    - ``local``    — any OpenAI-compatible local server (LM Studio, Ollama, …)

Callers always retain a heuristic / template fallback, so the app stays usable
when no key is configured. Use :func:`llm_available` to check first.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .config import (
    LM_STUDIO_MODEL,
    get_active_model,
    get_active_provider,
    get_provider_api_key,
)

# Sensible default model per provider. Overridden by the ``model`` field in
# config.json when set (see :func:`active_model`).
DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-6",
    "local": LM_STUDIO_MODEL,
}


def active_model() -> str:
    """Resolve the model name for the active provider (config override or default)."""
    provider = get_active_provider()
    return get_active_model(DEFAULT_MODELS.get(provider, DEFAULT_MODELS["gemini"]))


def llm_available() -> bool:
    """True when the active provider can be reached (key present, or local up)."""
    provider = get_active_provider()
    if provider == "local":
        from .extract import _lm_studio_available
        return _lm_studio_available()
    return bool(get_provider_api_key(provider))


def complete(
    messages: List[Dict[str, str]],
    *,
    json_mode: bool = False,
    schema: Optional[str] = None,
    temperature: float = 0.1,
    model: Optional[str] = None,
) -> str:
    """Run a chat completion against the active provider and return the text.

    ``messages`` is an OpenAI-style list of ``{"role": ..., "content": ...}``
    dicts (roles: ``system`` / ``user`` / ``assistant``). When ``json_mode`` is
    True the provider is asked for JSON and any code fences are stripped from the
    result. ``schema`` selects the local-server response schema ("rerank" for the
    match reranker, otherwise the extraction schema).
    """
    provider = get_active_provider()
    model = model or active_model()

    if provider == "local":
        text = _complete_local(messages, json_mode, schema)
    elif provider == "openai":
        text = _complete_openai(messages, json_mode, temperature, model)
    elif provider == "anthropic":
        text = _complete_anthropic(messages, json_mode, temperature, model)
    else:
        text = _complete_gemini(messages, json_mode, temperature, model)

    return _strip_code_fences(text) if json_mode else text


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _complete_gemini(messages, json_mode, temperature, model) -> str:
    import google.generativeai as genai

    key = get_provider_api_key("gemini")
    if not key:
        raise ValueError("No Gemini API key configured")
    genai.configure(api_key=key)

    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system") or None
    convo = [m for m in messages if m["role"] != "system"]

    gen_config: Dict[str, Any] = {"temperature": temperature}
    if json_mode:
        gen_config["response_mime_type"] = "application/json"

    gmodel = genai.GenerativeModel(
        model_name=model,
        system_instruction=system,
        generation_config=gen_config,
    )

    if len(convo) <= 1:
        resp = gmodel.generate_content(convo[-1]["content"] if convo else "")
    else:
        history = [
            {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
            for m in convo[:-1]
        ]
        chat = gmodel.start_chat(history=history)
        resp = chat.send_message(convo[-1]["content"])
    return resp.text


def _complete_openai(messages, json_mode, temperature, model) -> str:
    from openai import OpenAI

    key = get_provider_api_key("openai")
    if not key:
        raise ValueError("No OpenAI API key configured")
    client = OpenAI(api_key=key)

    kwargs: Dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def _complete_anthropic(messages, json_mode, temperature, model) -> str:
    import anthropic

    key = get_provider_api_key("anthropic")
    if not key:
        raise ValueError("No Anthropic API key configured")
    client = anthropic.Anthropic(api_key=key)

    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    if json_mode:
        system = (system + "\n\n" if system else "") + (
            "Respond with ONLY valid JSON. No markdown, no code fences, no commentary."
        )
    convo = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")]
    if not convo:
        convo = [{"role": "user", "content": ""}]

    resp = client.messages.create(
        model=model,
        system=system or anthropic.NOT_GIVEN,
        max_tokens=2048,
        temperature=temperature,
        messages=convo,
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _complete_local(messages, json_mode, schema) -> str:
    # OpenAI-compatible local server (LM Studio / Ollama) via existing helpers.
    from .extract import _lm_studio_chat, _lm_studio_rerank

    if json_mode and schema == "rerank":
        return _lm_studio_rerank(messages)
    return _lm_studio_chat(messages, json_mode=json_mode)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _strip_code_fences(text: str) -> str:
    """Remove a leading/trailing ```json ... ``` fence some models add."""
    if not text:
        return text
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_RE.sub("", stripped)
    return stripped.strip()
