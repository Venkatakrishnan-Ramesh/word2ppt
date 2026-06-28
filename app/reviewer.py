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
from .slide_planner import _clean_slide, _truncate

_REVIEW_SYSTEM = textwrap.dedent(
    """
    You are a meticulous presentation editor reviewing a draft slide deck that
    was auto-generated from a source document. Act as a critic, then an editor.

    Evaluate the draft against the ORIGINAL source for:
    - Clarity: titles are sharp; bullets are short phrases, not sentences.
    - Focus: one idea per slide; split or merge where needed.
    - Faithfulness: numbers, names and facts match the source; nothing invented.
    - Form: sequential/process content should be a flow diagram
      ({"type":"flow","direction":"down"|"right","steps":[str]}); tabular data
      should stay a table ({"headers":[str],"rows":[[str]]}).
    - Concision: tighten verbose cells and bullets.

    Return ONLY JSON:
    {
      "notes": [str],            // 3-8 short observations on what you changed/found
      "deck": {
        "title": str, "subtitle": str,
        "slides": [{"title": str, "bullets": [str],
                    "diagram": {...}|null, "table": {...}|null, "notes": str}]
      }
    }
    Keep at most %d slides. Preserve the source's ordering and meaning.
    """
    % MAX_SLIDES
).strip()


def _deck_to_json(deck: Deck) -> str:
    return json.dumps(deck.model_dump(), ensure_ascii=False)


def review_deck(
    deck: Deck, blocks: list[Block], settings: Settings
) -> tuple[Deck, list[str]]:
    """Run one agentic review/revision pass. Returns (revised_deck, notes)."""
    if not settings.ai_enabled:
        return deck, ["Agentic review skipped — no GROQ_API_KEY configured."]

    try:
        from groq import Groq

        client = Groq(api_key=settings.groq_api_key)
        completion = client.chat.completions.create(
            model=settings.groq_model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _REVIEW_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        "ORIGINAL SOURCE:\n"
                        f"{blocks_to_plain_text(blocks)}\n\n"
                        "DRAFT DECK (JSON):\n"
                        f"{_deck_to_json(deck)}"
                    ),
                },
            ],
        )
        payload = json.loads(completion.choices[0].message.content)
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
        slides=slides[:MAX_SLIDES],
    )
    return new_deck, (notes or ["Agentic review completed."])
