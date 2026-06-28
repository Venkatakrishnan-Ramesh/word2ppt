"""Glue: file -> blocks -> deck -> (pptx, html). Kept separate from the web layer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import MAX_SLIDES, Settings, clamp_max_slides
from .docx_parser import Block, parse_docx
from .html_builder import render_html
from .models import Deck
from .pptx_builder import render_pptx
from .reviewer import review_deck
from .slide_planner import (
    _paginate_tables,
    extract_route_slides,
    plan_deck,
    strip_diagrams,
    strip_tables,
)
from .text_parser import parse_text

SUPPORTED_EXTS = {".docx", ".txt", ".md", ".markdown", ".text"}

_SLIDE_COUNT_RE = re.compile(r"\b(\d{1,3})\s*slides?\b", re.IGNORECASE)


@dataclass(frozen=True)
class ConversionResult:
    deck: Deck
    strategy: str  # "groq" | "heuristic"
    pptx_bytes: bytes
    html: str
    reviewed: bool = False
    review_notes: tuple[str, ...] = ()


def parse_source(path: Path) -> list[Block]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return parse_docx(path)
    if suffix in SUPPORTED_EXTS:
        return parse_text(path)
    raise ValueError(f"Unsupported file type: {suffix or '(none)'}")


def _requested_slide_count(instructions: str) -> int:
    """Return an explicit slide count mentioned in user instructions, if any."""
    match = _SLIDE_COUNT_RE.search(instructions or "")
    if not match:
        return 0
    return clamp_max_slides(int(match.group(1)))


def _split_slide(slide) -> list:
    """Split one slide into smaller slides while preserving its content."""
    parts = []
    if slide.table and len(slide.table.rows) > 1:
        total = len(slide.table.rows)
        for idx, row in enumerate(slide.table.rows, 1):
            parts.append(
                type(slide)(
                    title=f"{slide.title} ({idx}/{total})",
                    bullets=slide.bullets if idx == 1 else [],
                    table=type(slide.table)(headers=slide.table.headers, rows=[row]),
                    notes=slide.notes if idx == 1 else "",
                )
            )
        return parts

    if slide.diagram and len(slide.diagram.steps) > 1:
        total = len(slide.diagram.steps)
        for idx, step in enumerate(slide.diagram.steps, 1):
            parts.append(
                type(slide)(
                    title=f"{slide.title} ({idx}/{total})",
                    bullets=[step],
                    notes=slide.notes if idx == 1 else "",
                )
            )
        return parts

    if len(slide.bullets) > 1:
        total = len(slide.bullets)
        for idx, bullet in enumerate(slide.bullets, 1):
            parts.append(
                type(slide)(
                    title=f"{slide.title} ({idx}/{total})",
                    bullets=[bullet],
                    notes=slide.notes if idx == 1 else "",
                )
            )
        return parts

    return [slide]


def _expand_to_target_slides(deck, target_slides: int):
    """Best-effort expansion when the user asked for a larger slide count."""
    if target_slides <= 0 or len(deck.slides) >= target_slides:
        return deck

    expanded = []
    for slide in deck.slides:
        if len(expanded) >= target_slides:
            break
        split = _split_slide(slide)
        for part in split:
            if len(expanded) >= target_slides:
                break
            expanded.append(part)

    if len(expanded) < target_slides:
        expanded.extend(deck.slides[len(expanded) : target_slides])

    return type(deck)(title=deck.title, subtitle=deck.subtitle, slides=expanded)


def convert(
    source: Path,
    settings: Settings,
    review: bool = False,
    diagrams: bool = False,
    tables: bool = True,
    max_slides: int = MAX_SLIDES,
    instructions: str = "",
    source_name: str = "",
    target_slides: int = 0,
) -> ConversionResult:
    blocks = parse_source(source)
    if not blocks:
        raise ValueError("No readable content found in the uploaded file.")

    origin = source_name.strip() or source.stem
    fallback_title = origin.replace("_", " ").replace("-", " ").strip().title()
    if not fallback_title or fallback_title.lower().startswith("tmp"):
        fallback_title = "Presentation"
    explicit_target = _requested_slide_count(instructions)
    if explicit_target:
        target_slides = explicit_target
    if target_slides > 0:
        max_slides = clamp_max_slides(target_slides)
        instructions = (
            f"{instructions.strip()}\n\n"
            f"Preserve at least {target_slides} slides. "
            "Do not merge slides in a way that reduces the deck below that count."
        ).strip()
    deck, strategy = plan_deck(
        blocks, fallback_title, settings, max_slides, instructions=instructions
    )

    review_notes: tuple[str, ...] = ()
    if review:
        deck, notes = review_deck(
            deck, blocks, settings, max_slides, instructions=instructions
        )
        deck = _paginate_tables(deck, max_slides)  # reviewer may have reshaped tables
        review_notes = tuple(notes)

    if diagrams:
        # Deterministically turn inline route/sequence lines into flow-diagram
        # slides, independent of what the LLM chose. Placed after the opening slide.
        route_slides = extract_route_slides(blocks)
        if route_slides:
            head, tail = deck.slides[:1], deck.slides[1:]
            merged = (head + route_slides + tail)[:max_slides]
            deck = Deck(title=deck.title, subtitle=deck.subtitle, slides=merged)
    else:
        # Diagrams not wanted (e.g. formal government decks): convert any diagram
        # the planner/reviewer produced back into plain bullet content.
        deck = strip_diagrams(deck)

    if not tables:
        deck = strip_tables(deck)

    if explicit_target:
        deck = _expand_to_target_slides(deck, explicit_target)

    return ConversionResult(
        deck=deck,
        strategy=strategy,
        pptx_bytes=render_pptx(deck),
        html=render_html(deck),
        reviewed=review,
        review_notes=review_notes,
    )
