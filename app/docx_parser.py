"""Extract a structured outline from a .docx file.

We turn the document into a heading-aware block list. This is the raw material
that either the heuristic planner or the Groq planner turns into slides.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph


@dataclass(frozen=True)
class Block:
    """One logical piece of the document."""

    kind: str  # "title" | "heading" | "text" | "bullet" | "table"
    level: int  # heading depth (1-9); 0 for non-headings
    text: str
    # For kind == "table": first inner tuple is the header row, the rest are body rows.
    rows: tuple[tuple[str, ...], ...] = ()


def _classify(style_name: str) -> tuple[str, int]:
    """Map a Word paragraph style to a block kind + heading level."""
    name = (style_name or "").lower()
    if name == "title":
        return "title", 0
    if name.startswith("heading"):
        digits = "".join(ch for ch in name if ch.isdigit())
        level = int(digits) if digits else 1
        return "heading", level
    if "list" in name or "bullet" in name:
        return "bullet", 0
    return "text", 0


def _table_block(table: DocxTable) -> Block | None:
    rows: list[tuple[str, ...]] = []
    for row in table.rows:
        cells = tuple(" ".join(cell.text.split()) for cell in row.cells)
        if any(cells):
            rows.append(cells)
    if len(rows) < 2:
        return None
    return Block(kind="table", level=0, text="", rows=tuple(rows))


def parse_docx(path: Path) -> list[Block]:
    """Read a .docx into ordered blocks, preserving paragraph/table interleaving."""
    document = Document(str(path))
    blocks: list[Block] = []
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            kind, level = _classify(paragraph.style.name if paragraph.style else "")
            blocks.append(Block(kind=kind, level=level, text=text))
        elif child.tag == qn("w:tbl"):
            table_block = _table_block(DocxTable(child, document))
            if table_block:
                blocks.append(table_block)
    return blocks


def document_title(blocks: list[Block], fallback: str) -> str:
    """Best-effort presentation title: explicit Title, else first heading, else filename."""
    for block in blocks:
        if block.kind == "title":
            return block.text
    for block in blocks:
        if block.kind == "heading":
            return block.text
    return fallback


def blocks_to_plain_text(blocks: list[Block], limit: int = 16000) -> str:
    """Render blocks as lightweight markdown for the LLM prompt (length-capped)."""
    lines: list[str] = []
    for block in blocks:
        if block.kind in ("title", "heading"):
            prefix = "#" * max(1, block.level or 1)
            lines.append(f"{prefix} {block.text}")
        elif block.kind == "bullet":
            lines.append(f"- {block.text}")
        elif block.kind == "table":
            for row in block.rows:
                lines.append("| " + " | ".join(row) + " |")
        else:
            lines.append(block.text)
    text = "\n".join(lines)
    return text[:limit]
