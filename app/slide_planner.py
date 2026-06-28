"""Turn parsed document blocks into a Deck.

Two strategies:
  * groq_plan  — ask a Groq LLM to restructure prose into clean slides (JSON mode)
  * heuristic_plan — group by headings; works with no API key at all

`plan_deck` picks the best available strategy and always falls back to the
heuristic if the AI path fails, so a conversion never hard-errors on the model.
"""

from __future__ import annotations

import json
import re
import textwrap
import time

from .config import (
    MAX_BULLET_CHARS,
    MAX_BULLETS_PER_SLIDE,
    MAX_SLIDES,
    MAX_TABLE_ROWS_PER_SLIDE,
    Settings,
)
from .docx_parser import Block, blocks_to_plain_text, document_title
from .models import Deck, Diagram, Slide, Table

# Headings hinting that the content under them is a sequential process.
_PROCESS_KEYWORDS = (
    "process",
    "workflow",
    "steps",
    "procedure",
    "pipeline",
    "lifecycle",
    "flow",
    "stages",
    "phases",
    "how it works",
)
_MAX_DIAGRAM_STEPS = 8
# Routes/corridors can be longer than a generic process before we split them.
_MAX_ROUTE_STEPS = 14
# Split a sequence written inline as "A - B - C" / "A → B → C".
_ROUTE_SPLIT_RE = re.compile(r"\s*(?:->|→|–|—|»|>|–|—|\s-\s)\s*")


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _route_steps(text: str) -> list[str]:
    """Return ordered nodes if `text` reads like an inline route/sequence, else []."""
    cleaned = text.replace("**", "").strip().rstrip(".")
    # Drop a leading "... connect:" style lead-in before the actual sequence.
    if ":" in cleaned and len(cleaned.split(":", 1)[0]) < 40:
        cleaned = cleaned.split(":", 1)[1].strip()
    parts = [p.strip(" .•-") for p in _ROUTE_SPLIT_RE.split(cleaned)]
    parts = [p for p in parts if p]
    if not (4 <= len(parts) <= 25):
        return []
    # Each node should be short and place/step-like, not a full sentence.
    for part in parts:
        if len(part) > 45 or "." in part or len(part.split()) > 7:
            return []
    return parts[:_MAX_ROUTE_STEPS]


def strip_diagrams(deck: Deck) -> Deck:
    """Remove flow diagrams, preserving their content as bullets.

    Used when diagrams are turned off (e.g. formal government decks): a diagram-only
    slide becomes a bulleted slide so no information is lost.
    """
    slides: list[Slide] = []
    for slide in deck.slides:
        if not slide.diagram:
            slides.append(slide)
            continue
        if slide.bullets or slide.table:
            # Other content carries the slide; just drop the diagram.
            slides.append(
                Slide(
                    title=slide.title,
                    bullets=slide.bullets,
                    table=slide.table,
                    notes=slide.notes,
                )
            )
        else:
            slides.append(
                Slide(
                    title=slide.title,
                    bullets=[_truncate(s, MAX_BULLET_CHARS) for s in slide.diagram.steps],
                    notes=slide.notes,
                )
            )
    return Deck(title=deck.title, subtitle=deck.subtitle, slides=slides)


def extract_route_slides(blocks: list[Block]) -> list[Slide]:
    """Find inline route/corridor lines in the source and render them as flow diagrams.

    Deterministic and engine-independent: this guarantees a sequence written as
    "A - B - C - ... - Z" becomes a real flow diagram, regardless of what the LLM
    chose to do.
    """
    slides: list[Slide] = []
    seen: set[tuple[str, ...]] = set()
    for block in blocks:
        if block.kind not in ("text", "bullet", "title", "heading"):
            continue
        steps = _route_steps(block.text)
        if not steps:
            continue
        key = tuple(steps)
        if key in seen:
            continue
        seen.add(key)
        title = "Corridor Route" if steps[0][:1].isalpha() else "Route"
        slides.append(
            Slide(
                title=title,
                diagram=Diagram(
                    type="flow",
                    direction="down",
                    steps=[_truncate(s, 40) for s in steps],
                ),
            )
        )
    return slides


def _clean_diagram(raw: object) -> Diagram | None:
    if not isinstance(raw, dict):
        return None
    steps = [
        _truncate(str(s).strip(), 60)
        for s in (raw.get("steps") or [])
        if str(s).strip()
    ][:_MAX_DIAGRAM_STEPS]
    if len(steps) < 2:
        return None
    direction = "right" if str(raw.get("direction", "")).lower() == "right" else "down"
    return Diagram(type="flow", direction=direction, steps=steps)


def _clean_slide(raw: dict) -> Slide | None:
    title = _truncate(str(raw.get("title", "")).strip(), 120)
    if not title:
        return None
    bullets_in = raw.get("bullets") or []
    bullets = [
        _truncate(str(b).strip(), MAX_BULLET_CHARS)
        for b in bullets_in
        if str(b).strip()
    ][:MAX_BULLETS_PER_SLIDE]
    diagram = _clean_diagram(raw.get("diagram"))
    table = _clean_table(raw.get("table"))
    notes = _truncate(str(raw.get("notes", "")).strip(), 400)
    return Slide(title=title, bullets=bullets, diagram=diagram, table=table, notes=notes)


def _clean_table(raw: object) -> Table | None:
    if not isinstance(raw, dict):
        return None
    headers = [str(h).strip() for h in (raw.get("headers") or []) if str(h).strip()]
    rows: list[list[str]] = []
    for row in raw.get("rows") or []:
        if isinstance(row, (list, tuple)):
            cells = [_truncate(str(c).strip(), 90) for c in row]
            if any(cells):
                rows.append(cells)
    if not rows:
        return None
    return Table(headers=headers, rows=rows)


# --------------------------------------------------------------------------- #
# Heuristic strategy (no API key required)
# --------------------------------------------------------------------------- #


def _maybe_diagram(heading: str, bullets: list[str]) -> Diagram | None:
    """Promote a process-like heading + multi-step list into a flow diagram."""
    if len(bullets) < 2 or len(bullets) > _MAX_DIAGRAM_STEPS:
        return None
    looks_process = any(kw in heading.lower() for kw in _PROCESS_KEYWORDS)
    if not looks_process:
        return None
    steps = [_truncate(b, 60) for b in bullets]
    return Diagram(type="flow", direction="down", steps=steps)


def heuristic_plan(
    blocks: list[Block], fallback_title: str, max_slides: int = MAX_SLIDES
) -> Deck:
    """Group content under headings. Each heading becomes a slide.

    A heading whose name implies a process (workflow, steps, pipeline, ...) and
    whose body is a short list is rendered as a flow diagram instead of bullets.
    """
    title = document_title(blocks, fallback_title)
    slides: list[Slide] = []
    current: Slide | None = None

    def flush(slide: Slide | None) -> None:
        # Title-only slides are dropped: the deck already opens with a title slide.
        if not slide or not (slide.bullets or slide.diagram):
            return
        diagram = _maybe_diagram(slide.title, slide.bullets)
        if diagram:
            slides.append(Slide(title=slide.title, diagram=diagram, notes=slide.notes))
        else:
            slides.append(slide)

    for block in blocks:
        if block.kind in ("title", "heading"):
            flush(current)
            current = Slide(title=_truncate(block.text, 120), bullets=[], notes="")
        elif block.kind == "table":
            flush(current)
            section_title = current.title if current else title
            headers = list(block.rows[0]) if block.rows else []
            body = [list(r) for r in block.rows[1:]]
            slides.append(
                Slide(title=section_title, table=Table(headers=headers, rows=body))
            )
            current = Slide(title=section_title, bullets=[], notes="")
        else:
            if current is None:
                current = Slide(title=title, bullets=[], notes="")
            if len(current.bullets) >= MAX_BULLETS_PER_SLIDE:
                flush(current)
                current = Slide(title=current.title, bullets=[], notes="")
            current.bullets.append(_truncate(block.text, MAX_BULLET_CHARS))

    flush(current)

    if not slides:
        slides = [Slide(title=title, bullets=["(No content found in document)"])]

    return Deck(title=title, subtitle=fallback_title, slides=slides[:max_slides])


# --------------------------------------------------------------------------- #
# Groq strategy
# --------------------------------------------------------------------------- #

_SYSTEM_PROMPT = textwrap.dedent(
    f"""
    You are preparing slides for an OFFICIAL GOVERNMENT / PUBLIC-SECTOR
    presentation. Use a formal, precise, administrative register. Rules:
    - Each slide has a formal, descriptive title (no marketing or casual language).
    - 2-{MAX_BULLETS_PER_SLIDE} bullets per slide; concise but complete formal
      phrases. Max {MAX_BULLET_CHARS} chars each.
    - PRESERVE official terminology, proper nouns, place names, scheme/section
      numbers, figures, units and abbreviations EXACTLY as in the source.
    - Summarize verbose prose without changing meaning or dropping key facts.
    - Never invent data, figures, or claims not present in the source.
    - Keep the original meaning and ordering of ideas.
    - Add brief, neutral speaker notes per slide when helpful.
    - Create a separate slide for each distinct topic or document section. For long,
      detailed documents, use MORE slides (split dense sections) and approach the
      user's slide limit rather than over-condensing. Never exceed the limit.
    DIAGRAMS:
    - When a slide describes a PROCESS, WORKFLOW, SEQUENCE, or ordered STEPS,
      represent it as a flow diagram instead of bullets.
    - A diagram is {{"type": "flow", "direction": "down" | "right", "steps": [str]}}
      with 2-{_MAX_DIAGRAM_STEPS} short node labels (max ~60 chars each) in order.
    - Use "direction": "right" for short pipelines, "down" for longer ones.
    - A slide may include bullets, a diagram, or a table. Prefer a diagram
      whenever the content is genuinely sequential.
    TABLES:
    - When the source has tabular data, keep it as a table:
      {{"headers": [str], "rows": [[str], ...]}}. Keep cells short; summarize long
      cell text into a few words. Do not exceed ~5 columns.
    Respond ONLY with JSON of the form:
    {{"title": str, "subtitle": str,
      "slides": [{{"title": str, "bullets": [str],
                   "diagram": {{"type": "flow", "direction": str, "steps": [str]}} | null,
                   "table": {{"headers": [str], "rows": [[str]]}} | null,
                   "notes": str}}]}}
    """
).strip()


def groq_json(system: str, user: str, settings: Settings, retries: int = 3) -> dict:
    """Call Groq in JSON mode with retries, so a transient failure or a single
    malformed response does not silently drop the whole deck to the heuristic."""
    from groq import Groq  # imported lazily so the heuristic path needs no dep

    client = Groq(api_key=settings.groq_api_key)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            completion = client.chat.completions.create(
                model=settings.groq_model,
                temperature=0.2,
                # Allow large JSON so big decks (many slides) aren't truncated.
                max_tokens=32000,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return json.loads(completion.choices[0].message.content)
        except Exception as exc:  # noqa: BLE001 — retry transient API/JSON errors
            last_error = exc
            if attempt < retries - 1:
                time.sleep(0.7 * (attempt + 1))
    raise RuntimeError(f"Groq call failed after {retries} attempts: {last_error}")


def groq_plan(
    blocks: list[Block],
    fallback_title: str,
    settings: Settings,
    max_slides: int = MAX_SLIDES,
) -> Deck:
    """Ask Groq to restructure the document. Raises only after retries are exhausted."""
    source = blocks_to_plain_text(blocks)
    payload = groq_json(
        _SYSTEM_PROMPT,
        f"Document title hint: {fallback_title}\n"
        f"Produce at most {max_slides} slides.\n\n{source}",
        settings,
    )

    slides = [s for raw in payload.get("slides", []) if (s := _clean_slide(raw))]
    if not slides:
        raise ValueError("Groq returned no usable slides")

    title = _truncate(str(payload.get("title") or fallback_title), 120)
    subtitle = _truncate(str(payload.get("subtitle") or fallback_title), 120)
    return Deck(title=title, subtitle=subtitle, slides=slides[:max_slides])


def _paginate_tables(deck: Deck, max_slides: int = MAX_SLIDES) -> Deck:
    """Split any slide whose table is taller than the per-slide limit into pages.

    Headers repeat on each page and the title gets a ``(i/n)`` suffix.
    """
    out: list[Slide] = []
    for slide in deck.slides:
        table = slide.table
        if not table or len(table.rows) <= MAX_TABLE_ROWS_PER_SLIDE:
            out.append(slide)
            continue
        chunks = [
            table.rows[i : i + MAX_TABLE_ROWS_PER_SLIDE]
            for i in range(0, len(table.rows), MAX_TABLE_ROWS_PER_SLIDE)
        ]
        total = len(chunks)
        for idx, chunk in enumerate(chunks, 1):
            out.append(
                Slide(
                    title=f"{slide.title} ({idx}/{total})",
                    bullets=slide.bullets if idx == 1 else [],
                    table=Table(headers=table.headers, rows=chunk),
                    notes=slide.notes if idx == 1 else "",
                )
            )
    return Deck(title=deck.title, subtitle=deck.subtitle, slides=out[:max_slides])


def plan_deck(
    blocks: list[Block],
    fallback_title: str,
    settings: Settings,
    max_slides: int = MAX_SLIDES,
) -> tuple[Deck, str]:
    """Build a Deck using the best available strategy.

    Returns the deck plus the strategy name actually used ("groq" | "heuristic").
    """
    if settings.ai_enabled:
        try:
            deck = groq_plan(blocks, fallback_title, settings, max_slides)
            return _paginate_tables(deck, max_slides), "groq"
        except Exception:  # noqa: BLE001 — any failure should degrade gracefully
            pass
    deck = heuristic_plan(blocks, fallback_title, max_slides)
    return _paginate_tables(deck, max_slides), "heuristic"
