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
from .slide_planner import _paginate_tables, plan_deck
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
) -> ConversionResult:
    blocks = parse_source(source)
    if not blocks:
        raise ValueError("No readable content found in the uploaded file.")

    fallback_title = source.stem.replace("_", " ").replace("-", " ").strip().title()
    deck, strategy = plan_deck(blocks, fallback_title, settings)

    review_notes: tuple[str, ...] = ()
    if review:
        deck, notes = review_deck(deck, blocks, settings)
        deck = _paginate_tables(deck)  # reviewer may have reshaped tables
        review_notes = tuple(notes)

    return ConversionResult(
        deck=deck,
        strategy=strategy,
        pptx_bytes=render_pptx(deck),
        html=render_html(deck),
        reviewed=review,
        review_notes=review_notes,
    )
