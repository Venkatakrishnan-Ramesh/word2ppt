"""LLM provider layer with automatic fallback.

Order of attempts for a JSON-mode completion:
  1. Groq primary model (e.g. llama-3.3-70b-versatile)
  2. Groq fallback model (e.g. llama-3.1-8b-instant — separate free-tier quota)
  3. Google Gemini (free tier) if GEMINI_API_KEY is set

Each provider is tried in turn; a rate/size/quota error moves on to the next.
Raises only when every configured provider fails, letting the caller fall back
to the offline heuristic.
"""

from __future__ import annotations

import json
import time

import httpx

from .config import Settings

# Error fragments meaning "this model is out of quota / request too big" — when we
# see these we move to the next model/provider rather than retrying the same one.
_QUOTA_ERROR_HINTS = (
    "rate_limit",
    "429",
    "413",
    "too large",
    "tokens per",
    "quota",
    "resource_exhausted",
)


def _is_quota_error(exc: Exception) -> bool:
    return any(h in str(exc).lower() for h in _QUOTA_ERROR_HINTS)


def _groq_call(model: str, system: str, user: str, settings: Settings, mt: int) -> dict:
    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    completion = client.chat.completions.create(
        model=model,
        temperature=0.2,
        max_tokens=mt,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return json.loads(completion.choices[0].message.content)


def _gemini_call(system: str, user: str, settings: Settings, mt: int) -> dict:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
            "maxOutputTokens": mt,
        },
    }
    resp = httpx.post(
        url,
        params={"key": settings.gemini_api_key},
        json=body,
        timeout=60.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def complete_json(
    system: str,
    user: str,
    settings: Settings,
    retries: int = 3,
    max_tokens: int | None = None,
) -> dict:
    """Run a JSON-mode completion across providers with fallback. Raises on total failure."""
    mt = max_tokens or settings.groq_max_tokens
    last_error: Exception | None = None
    tried: list[str] = []

    if settings.groq_api_key:
        groq_models = [settings.groq_model]
        if settings.groq_fallback_model and settings.groq_fallback_model not in groq_models:
            groq_models.append(settings.groq_fallback_model)
        for model in groq_models:
            tried.append(f"groq:{model}")
            for attempt in range(retries):
                try:
                    return _groq_call(model, system, user, settings, mt)
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    if _is_quota_error(exc):
                        break  # this model is capped — try the next one
                    if attempt < retries - 1:
                        time.sleep(0.7 * (attempt + 1))

    if settings.gemini_api_key:
        tried.append(f"gemini:{settings.gemini_model}")
        for attempt in range(retries):
            try:
                return _gemini_call(system, user, settings, mt)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if _is_quota_error(exc):
                    break
                if attempt < retries - 1:
                    time.sleep(0.7 * (attempt + 1))

    raise RuntimeError(f"All LLM providers failed (tried {tried}): {last_error}")
