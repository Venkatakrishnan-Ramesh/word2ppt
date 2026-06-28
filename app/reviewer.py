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
    - Focus: one idea per slide; split or merge where needed.
    - Faithfulness: numbers, place names, scheme/section numbers, units and facts
      must match the source EXACTLY; nothing invented or dropped.
    - Form: tabular data should stay a table
      ({"headers":[str],"rows":[[str]]}). Only use a flow diagram
      ({"type":"flow","direction":"down"|"right","steps":[str]}) when content is
      genuinely sequential.
    - Concision: tighten verbose cells and bullets without losing official detail.

    Return ONLY JSON:
    {
      "notes": [str],            // 3-8 short observations on what you changed/found
      "deck": {
        "title": str, "subtitle": str,
        "slides": [{"title": str, "bullets": [str],
                    "diagram": {...}|null, "table": {...}|null, "notes": str}]
      }
    }
    Stay within the slide limit the user provides. Preserve ordering and meaning.
    """
).strip()


def _deck_to_json(deck: Deck) -> str:
    return json.dumps(deck.model_dump(), ensure_ascii=False)


def review_deck(
    deck: Deck,
    blocks: list[Block],
    settings: Settings,
    max_slides: int = MAX_SLIDES,
) -> tuple[Deck, list[str]]:
    """Run one agentic review/revision pass. Returns (revised_deck, notes)."""
    if not settings.ai_enabled:
        return deck, ["Agentic review skipped — no GROQ_API_KEY configured."]

    # The review sends the draft deck AND the source, so keep both compact: the
    # smaller Groq model has a ~6k tokens/minute window, and the draft already
    # carries most of the content.
    source_cap = min(settings.groq_source_chars, 2500)
    user_prompt = (
        f"Slide limit: at most {max_slides} slides.\n\n"
        "ORIGINAL SOURCE (excerpt):\n"
        f"{blocks_to_plain_text(blocks, source_cap)}\n\n"
        "DRAFT DECK (JSON):\n"
        f"{_deck_to_json(deck)}"
    )
    try:
        # Smaller output budget so the whole review request fits the free-tier window.
        payload = groq_json(_REVIEW_SYSTEM, user_prompt, settings, max_tokens=2500)
    except Exception as exc:  # noqa: BLE001 — never let review break a conversion
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
