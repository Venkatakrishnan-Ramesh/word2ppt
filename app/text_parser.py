"""Parse a plain-text / markdown file into the same Block list the .docx parser emits.

Heading detection, in order of priority:
  * Markdown ATX headings: ``#``, ``##`` ...
  * Markdown Setext headings: a line underlined with ``===`` or ``---``
  * Short standalone UPPERCASE or Title-Case lines with no trailing punctuation
Bullets: lines starting with ``-``, ``*``, ``•`` or ``1.`` / ``1)``.
"""

from __future__ import annotations

import re
from pathlib import Path

from .docx_parser import Block

_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")
_ATX_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_SETEXT_RE = re.compile(r"^\s*(=+|-+)\s*$")
# A markdown table separator row, e.g. ``| ---: | :---: | --- |``
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")


def _is_table_row(line: str) -> bool:
    return line.strip().startswith("|") and line.count("|") >= 2


def _split_row(line: str) -> tuple[str, ...]:
    cells = line.strip().strip("|").split("|")
    return tuple(c.strip() for c in cells)


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 70:
        return False
    if stripped[-1] in ".:;,":
        return False
    words = stripped.split()
    if len(words) > 9:
        return False
    if stripped.isupper():
        return True
    # Title Case: most words capitalized.
    capped = sum(1 for w in words if w[:1].isupper())
    return capped >= max(1, len(words) - 1)


def parse_text(path: Path) -> list[Block]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    blocks: list[Block] = []
    first_heading_seen = False

    index = 0
    while index < len(lines):
        line = lines[index]
        text = line.strip()
        if not text:
            index += 1
            continue

        # Markdown table: a run of "| ... |" lines, with a separator as 2nd row.
        if _is_table_row(line):
            table_lines = []
            while index < len(lines) and _is_table_row(lines[index]):
                table_lines.append(lines[index])
                index += 1
            rows = [
                _split_row(tl)
                for tl in table_lines
                if not _TABLE_SEP_RE.match(tl)
            ]
            rows = [r for r in rows if any(r)]
            if len(rows) >= 2:
                blocks.append(Block(kind="table", level=0, text="", rows=tuple(rows)))
            continue

        atx = _ATX_RE.match(text)
        if atx:
            level = len(atx.group(1))
            kind = "title" if not first_heading_seen and level == 1 else "heading"
            first_heading_seen = True
            blocks.append(Block(kind=kind, level=level, text=atx.group(2).strip()))
            index += 1
            continue

        # Setext: current line is text, next line is === / ---
        nxt = lines[index + 1] if index + 1 < len(lines) else ""
        if nxt and _SETEXT_RE.match(nxt):
            level = 1 if nxt.strip().startswith("=") else 2
            kind = "title" if not first_heading_seen and level == 1 else "heading"
            first_heading_seen = True
            blocks.append(Block(kind=kind, level=level, text=text))
            index += 2
            continue

        bullet = _BULLET_RE.match(text)
        if bullet:
            blocks.append(Block(kind="bullet", level=0, text=bullet.group(1).strip()))
            index += 1
            continue

        if _looks_like_heading(text):
            first_heading_seen = True
            blocks.append(Block(kind="heading", level=1, text=text))
            index += 1
            continue

        blocks.append(Block(kind="text", level=0, text=text))
        index += 1

    return blocks
