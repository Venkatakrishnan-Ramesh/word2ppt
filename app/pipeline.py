"""Glue: file -> blocks -> deck -> (pptx, html). Kept separate from the web layer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import MAX_SLIDES, Settings, clamp_max_slides
from .docx_parser import Block, parse_docx
from .html_builder import render_html
from .models import Deck, Diagram, Slide
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
from .themes import resolve_theme

SUPPORTED_EXTS = {".docx", ".txt", ".md", ".markdown", ".text"}

_SLIDE_COUNT_RE = re.compile(r"\b(\d{1,3})\s*slides?\b", re.IGNORECASE)

# Phrases that force every flow diagram into a given layout direction.
_HORIZONTAL_HINTS = ("horizontal", "left to right", "left-to-right", "side by side")
_VERTICAL_HINTS = ("vertical", "top to bottom", "top-to-bottom", "top down", "top-down")


def _forced_diagram_direction(instructions: str) -> str | None:
    """Return 'right'/'down' if the user asked for a flowchart direction, else None."""
    text = (instructions or "").lower()
    if any(h in text for h in _HORIZONTAL_HINTS):
        return "right"
    if any(h in text for h in _VERTICAL_HINTS):
        return "down"
    return None


def _default_diagram_direction(diagrams: bool, instructions: str) -> str | None:
    """Pick the diagram direction to apply when the user did not specify one."""
    forced = _forced_diagram_direction(instructions)
    if forced:
        return forced
    return "right" if diagrams else None


def _apply_diagram_direction(deck: Deck, direction: str) -> Deck:
    """Force every flow diagram in the deck to a single layout direction."""
    slides = []
    for slide in deck.slides:
        if not slide.diagram:
            slides.append(slide)
            continue
        diagram = _copy_model(slide.diagram, direction=direction)
        slides.append(_copy_model(slide, diagram=diagram))
    return Deck(title=deck.title, subtitle=deck.subtitle, slides=slides)


def _copy_model(obj, **updates):
    """Return a new model instance with updates applied, regardless of Pydantic version."""
    if hasattr(obj, "model_copy"):
        return obj.model_copy(update=updates)
    data = obj.model_dump() if hasattr(obj, "model_dump") else dict(obj.__dict__)
    data.update(updates)
    return obj.__class__(**data)


@dataclass(frozen=True)
class ConversionResult:
    deck: Deck
    strategy: str  # "groq" | "heuristic"
    pptx_bytes: bytes
    html: str
    reviewed: bool = False
    review_notes: tuple[str, ...] = ()
    theme: str = "corporate-blue"
    theme_label: str = "Corporate Blue"


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


def _expand_to_target_slides(deck, target_slides: int):
    """Best-effort expansion when the user asked for a larger slide count.

    This keeps slides grouped. We only split when the slide has enough content to
    remain readable after the split, rather than fanning a bullet list out into
    one-bullet slides.
    """
    if target_slides <= 0 or len(deck.slides) >= target_slides:
        return deck

    expanded = list(deck.slides)
    while len(expanded) < target_slides:
        split_idx = _find_splittable_slide(expanded)
        if split_idx is None:
            break
        slide = expanded.pop(split_idx)
        expanded[split_idx:split_idx] = _split_slide_balanced(slide)

    return type(deck)(title=deck.title, subtitle=deck.subtitle, slides=expanded)


def _find_splittable_slide(slides) -> int | None:
    """Return the index of the slide with the most content that can be split well."""
    best_idx: int | None = None
    best_size = 0
    for idx, slide in enumerate(slides):
        size = _splittable_size(slide)
        if size > best_size:
            best_idx = idx
            best_size = size
    return best_idx


def _splittable_size(slide) -> int:
    if slide.table and len(slide.table.rows) >= 6:
        return len(slide.table.rows)
    if slide.diagram and len(slide.diagram.steps) >= 6:
        return len(slide.diagram.steps)
    if len(slide.bullets) >= 6:
        return len(slide.bullets)
    return 0


def _split_slide_balanced(slide):
    """Split a slide into two grouped slides, keeping chunks readable."""
    if slide.table and len(slide.table.rows) >= 6:
        return _split_rows_balanced(slide)
    if slide.diagram and len(slide.diagram.steps) >= 6:
        return _split_steps_balanced(slide)
    if len(slide.bullets) >= 6:
        return _split_bullets_balanced(slide)
    return [slide]


def _balanced_split_index(total: int, min_chunk: int = 3) -> int | None:
    """Return a split index that keeps both chunks at least ``min_chunk`` long."""
    if total < min_chunk * 2:
        return None
    split_at = total // 2
    if split_at < min_chunk:
        split_at = min_chunk
    if total - split_at < min_chunk:
        split_at = total - min_chunk
    return split_at if min_chunk <= split_at <= total - min_chunk else None


def _split_bullets_balanced(slide):
    bullets = list(slide.bullets)
    split_at = _balanced_split_index(len(bullets))
    if split_at is None:
        return [slide]
    left = bullets[:split_at]
    right = bullets[split_at:]
    if not left or not right:
        return [slide]
    return [
        type(slide)(title=f"{slide.title} (1/2)", bullets=left, notes=slide.notes),
        type(slide)(title=f"{slide.title} (2/2)", bullets=right),
    ]


def _split_steps_balanced(slide):
    steps = list(slide.diagram.steps)
    split_at = _balanced_split_index(len(steps))
    if split_at is None:
        return [slide]
    left = steps[:split_at]
    right = steps[split_at:]
    if not left or not right:
        return [slide]
    diagram_type = type(slide.diagram)
    return [
        type(slide)(
            title=f"{slide.title} (1/2)",
            diagram=diagram_type(type=slide.diagram.type, direction=slide.diagram.direction, steps=left),
            notes=slide.notes,
        ),
        type(slide)(
            title=f"{slide.title} (2/2)",
            diagram=diagram_type(type=slide.diagram.type, direction=slide.diagram.direction, steps=right),
        ),
    ]


def _split_rows_balanced(slide):
    rows = list(slide.table.rows)
    split_at = _balanced_split_index(len(rows))
    if split_at is None:
        return [slide]
    left = rows[:split_at]
    right = rows[split_at:]
    if not left or not right:
        return [slide]
    table_type = type(slide.table)
    return [
        type(slide)(
            title=f"{slide.title} (1/2)",
            bullets=slide.bullets,
            table=table_type(headers=slide.table.headers, rows=left),
            notes=slide.notes,
        ),
        type(slide)(
            title=f"{slide.title} (2/2)",
            table=table_type(headers=slide.table.headers, rows=right),
        ),
    ]


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

    # Theme is chosen by naming it in the instructions; resolve before we append
    # our own slide-count guidance to the instruction text.
    theme = resolve_theme(instructions)

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

    diagram_direction = _default_diagram_direction(diagrams, instructions)
    if diagram_direction:
        deck = _apply_diagram_direction(deck, diagram_direction)

    if explicit_target:
        deck = _expand_to_target_slides(deck, explicit_target)

    return ConversionResult(
        deck=deck,
        strategy=strategy,
        pptx_bytes=render_pptx(deck, theme),
        html=render_html(deck, theme),
        reviewed=review,
        review_notes=review_notes,
        theme=theme.name,
        theme_label=theme.label,
    )
