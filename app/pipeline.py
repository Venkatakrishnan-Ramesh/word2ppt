"""Glue: file -> blocks -> deck -> (pptx, html). Kept separate from the web layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .docx_parser import Block, parse_docx
from .html_builder import render_html
from .models import Deck
from .pptx_builder import render_pptx
from .reviewer import review_deck
from .config import MAX_SLIDES
from .slide_planner import (
    _paginate_tables,
    extract_route_slides,
    plan_deck,
    strip_diagrams,
)
from .text_parser import parse_text

SUPPORTED_EXTS = {".docx", ".txt", ".md", ".markdown", ".text"}


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


def convert(
    source: Path,
    settings: Settings,
    review: bool = False,
    diagrams: bool = False,
    max_slides: int = MAX_SLIDES,
    instructions: str = "",
    source_name: str = "",
) -> ConversionResult:
    blocks = parse_source(source)
    if not blocks:
        raise ValueError("No readable content found in the uploaded file.")

    origin = source_name.strip() or source.stem
    fallback_title = origin.replace("_", " ").replace("-", " ").strip().title()
    if not fallback_title or fallback_title.lower().startswith("tmp"):
        fallback_title = "Presentation"
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

    return ConversionResult(
        deck=deck,
        strategy=strategy,
        pptx_bytes=render_pptx(deck),
        html=render_html(deck),
        reviewed=review,
        review_notes=review_notes,
    )
