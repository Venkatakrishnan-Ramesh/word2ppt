"""Agentic content-review pass over a planned Deck using Groq.

A second LLM acts as a critic/editor: it reads the drafted slides plus the
original source, flags weaknesses (wordy bullets, weak titles, sequential
content that should be a diagram, inconsistent numbers), and returns a revised
deck together with short review notes.

Degrades gracefully: with no Groq key, or on any error, it returns the deck
unchanged plus an explanatory note, so the conversion never fails.
"""

from __future__ import annotations

import json
import time
import textwrap

from .config import MAX_SLIDES, Settings
from .docx_parser import Block, blocks_to_plain_text
from .models import Deck
from .slide_planner import _clean_slide, _truncate, groq_json

_REVIEW_SYSTEM = textwrap.dedent(
    """
    You are a meticulous editor reviewing a draft slide deck for an OFFICIAL
    GOVERNMENT / PUBLIC-SECTOR presentation. Act as a critic, then an editor.
    Maintain a formal, precise, administrative register throughout.

    Evaluate the draft against the ORIGINAL source for:
    - Tone: formal and official; remove any casual or marketing language.
    - Clarity: titles are formal and descriptive; bullets are clean formal phrases.
    - Faithfulness: numbers, place names, scheme/section numbers, units and facts
      must match the source EXACTLY; nothing invented or dropped.
    - Form: tabular data should stay a table
      ({"headers":[str],"rows":[[str]]}). Only use a flow diagram
      ({"type":"flow","direction":"down"|"right","steps":[str]}) when content is
      genuinely sequential.
    - Wording: you MAY rephrase a bullet or table cell for a more formal register,
      but only edit the text of an existing point in place.
    - Layout: if a diagram, table, or slide feels cramped or undersized, revise
      the deck to fix it when possible by enlarging the content area, splitting
      the slide, or rebalancing bullets. Do not leave a layout problem as a note
      if the deck can be corrected directly.

    PRESERVE ALL CONTENT — this is the most important rule:
    - Never delete, drop, or merge away a bullet, table row, or point. Every point
      in the draft must still appear in your output (rephrased at most).
    - Do NOT condense or summarise multiple points into one. Keep them separate.
    - You may SPLIT an overloaded slide into more slides, but never reduce the
      total number of points. Prefer more slides over fewer.
    - Keep at least as many bullets/rows on each topic as the draft has.

    Return ONLY JSON:
    {
      "notes": [str],            // 3-8 short observations on what you changed/found
      "deck": {
        "title": str, "subtitle": str,
        "slides": [{"title": str, "bullets": [str],
                    "diagram": {...}|null, "table": {...}|null, "notes": str}]
      }
    }
    Stay within the slide limit the user provides, but never drop points to fit:
    if content is too large, fill the slides densely rather than removing detail.
    Preserve ordering, meaning, and the full set of points from the draft.
    """
).strip()

_REVIEW_RETRY_DELAYS = (1.5, 3.0, 6.0)


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        hint in text
        for hint in (
            "rate_limit",
            "429",
            "tokens per minute",
            "quota",
            "resource_exhausted",
        )
    )


def _deck_to_json(deck: Deck) -> str:
    return json.dumps(_jsonable(deck), ensure_ascii=False)


def _jsonable(obj):
    if isinstance(obj, dict):
        return {key: _jsonable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(value) for value in obj]
    if hasattr(obj, "model_dump"):
        return _jsonable(obj.model_dump())
    return obj


def review_deck(
    deck: Deck,
    blocks: list[Block],
    settings: Settings,
    max_slides: int = MAX_SLIDES,
    instructions: str = "",
) -> tuple[Deck, list[str]]:
    """Run one agentic review/revision pass. Returns (revised_deck, notes)."""
    if not settings.ai_enabled:
        return deck, ["Agentic review skipped — no AI provider configured."]

    # The review sends the draft deck AND the source, so keep both compact: the
    # smaller Groq model has a ~6k tokens/minute window, and the draft already
    # carries most of the content.
    source_cap = min(settings.groq_source_chars, 2500)
    extra = (
        f"USER INSTRUCTIONS (apply these): {instructions.strip()}\n\n"
        if instructions.strip()
        else ""
    )
    user_prompt = (
        f"Slide limit: at most {max_slides} slides.\n"
        f"{extra}"
        "ORIGINAL SOURCE (excerpt):\n"
        f"{blocks_to_plain_text(blocks, source_cap)}\n\n"
        "DRAFT DECK (JSON):\n"
        f"{_deck_to_json(deck)}"
    )
    try:
        # Smaller output budget so the whole review request fits the free-tier window.
        payload = None
        last_error: Exception | None = None
        for attempt in range(1, len(_REVIEW_RETRY_DELAYS) + 2):
            try:
                payload = groq_json(_REVIEW_SYSTEM, user_prompt, settings, max_tokens=2500)
                break
            except Exception as exc:  # noqa: BLE001 — never let review break a conversion
                last_error = exc
                if not _is_quota_error(exc) or attempt > len(_REVIEW_RETRY_DELAYS):
                    raise
                time.sleep(_REVIEW_RETRY_DELAYS[attempt - 1])
        if payload is None:
            raise last_error or RuntimeError("Agentic review could not be completed.")
    except Exception as exc:  # noqa: BLE001 — never let review break a conversion
        if _is_quota_error(exc):
            return deck, [f"Agentic review still rate-limited after retries (error: {exc})."]
        return deck, [f"Agentic review skipped (error: {exc})."]

    notes = [
        _truncate(str(n).strip(), 200)
        for n in (payload.get("notes") or [])
        if str(n).strip()
    ][:8]

    revised = payload.get("deck") or {}
    slides = [s for raw in revised.get("slides", []) if (s := _clean_slide(raw))]
    if not slides:
        # Reviewer produced nothing usable — keep the draft, surface the notes.
        return deck, (notes or ["Agentic review returned no changes."])

    new_deck = Deck(
        title=_truncate(str(revised.get("title") or deck.title), 120),
        subtitle=_truncate(str(revised.get("subtitle") or deck.subtitle), 120),
        slides=slides[:max_slides],
    )
    return new_deck, (notes or ["Agentic review completed."])
