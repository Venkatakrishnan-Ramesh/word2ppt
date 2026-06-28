"""Render a Deck into an editable .pptx file using python-pptx.

Bulleted slides use the standard title+content layout. Flow diagrams are drawn
as native, editable rounded-rectangle shapes connected by arrow connectors, so
the user can move/restyle them in PowerPoint afterwards.
"""

from __future__ import annotations

import io
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

from .models import Deck, Diagram, Slide, Table

# Brand-ish palette kept in one place rather than scattered as magic values.
_ACCENT = RGBColor(0x2D, 0x5B, 0xFF)
_ACCENT_DARK = RGBColor(0x1B, 0x2A, 0x4A)
_NODE_FILL = RGBColor(0xEC, 0xF1, 0xFF)
_NODE_LINE = RGBColor(0x2D, 0x5B, 0xFF)
_TEXT_DARK = RGBColor(0x1A, 0x1A, 0x1A)
_WHITE = RGBColor(0xFF, 0xFF, 0xFF)


def _slide_size(prs: Presentation) -> tuple[int, int]:
    return prs.slide_width, prs.slide_height


def _add_title_slide(prs: Presentation, deck: Deck) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    width, height = _slide_size(prs)

    band = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, int(height * 0.34), width, int(height * 0.32)
    )
    band.fill.solid()
    band.fill.fore_color.rgb = _ACCENT_DARK
    band.line.fill.background()

    box = slide.shapes.add_textbox(
        int(width * 0.08), int(height * 0.36), int(width * 0.84), int(height * 0.28)
    )
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.text = deck.title
    p.alignment = PP_ALIGN.LEFT
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = _WHITE
    if deck.subtitle:
        sub = tf.add_paragraph()
        sub.text = deck.subtitle
        sub.font.size = Pt(18)
        sub.font.color.rgb = RGBColor(0xC8, 0xD4, 0xF0)


def _add_bullets(slide, slide_data: Slide, prs: Presentation) -> None:
    width, _ = _slide_size(prs)
    box = slide.shapes.add_textbox(
        int(width * 0.08), Emu(int(prs.slide_height * 0.26)),
        int(width * 0.84), int(prs.slide_height * 0.6),
    )
    tf = box.text_frame
    tf.word_wrap = True
    for i, bullet in enumerate(slide_data.bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = f"•  {bullet}"
        p.font.size = Pt(20)
        p.font.color.rgb = _TEXT_DARK
        p.space_after = Pt(10)


def _add_diagram(slide, diagram: Diagram, prs: Presentation) -> None:
    width, height = _slide_size(prs)
    steps = diagram.steps
    if not steps:
        return

    top_margin = int(height * 0.28)
    area_w = int(width * 0.84)
    left_margin = int(width * 0.08)

    if diagram.direction == "right":
        gap = int(area_w * 0.04)
        node_w = (area_w - gap * (len(steps) - 1)) // len(steps)
        node_h = int(height * 0.16)
        top = top_margin + int(height * 0.12)
        boxes = []
        for i, label in enumerate(steps):
            left = left_margin + i * (node_w + gap)
            boxes.append(_node(slide, label, left, top, node_w, node_h))
        for a, b in zip(boxes, boxes[1:]):
            _connect(slide, a, b)
    else:  # "down"
        node_w = int(area_w * 0.5)
        left = left_margin + (area_w - node_w) // 2
        available = int(height * 0.62)
        gap = int(available * 0.05)
        node_h = (available - gap * (len(steps) - 1)) // len(steps)
        node_h = min(node_h, int(height * 0.13))
        boxes = []
        for i, label in enumerate(steps):
            top = top_margin + i * (node_h + gap)
            boxes.append(_node(slide, label, left, top, node_w, node_h))
        for a, b in zip(boxes, boxes[1:]):
            _connect(slide, a, b)


def _node(slide, label: str, left: int, top: int, w: int, h: int):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = _NODE_FILL
    shape.line.color.rgb = _NODE_LINE
    shape.line.width = Pt(1.5)
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.text = label
    p.alignment = PP_ALIGN.CENTER
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = _ACCENT_DARK
    return shape


def _connect(slide, a, b) -> None:
    connector = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        a.left + a.width // 2, a.top + a.height,
        b.left + b.width // 2, b.top,
    )
    # Vertical vs horizontal endpoints depending on relative position.
    if abs(b.top - a.top) < a.height:  # side by side -> horizontal arrow
        connector.begin_x, connector.begin_y = a.left + a.width, a.top + a.height // 2
        connector.end_x, connector.end_y = b.left, b.top + b.height // 2
    line = connector.line
    line.color.rgb = _ACCENT
    line.width = Pt(2.25)
    _add_arrow_head(connector)


def _add_arrow_head(connector) -> None:
    """Add a triangle arrowhead to a connector's end (python-pptx has no helper)."""
    ln = connector.line._get_or_add_ln()
    from pptx.oxml.ns import qn

    tail = ln.find(qn("a:tailEnd"))
    if tail is None:
        tail = ln.makeelement(qn("a:tailEnd"), {})
        ln.append(tail)
    tail.set("type", "triangle")
    tail.set("w", "med")
    tail.set("len", "med")


def _add_table(slide, table: Table, prs: Presentation) -> None:
    width, height = _slide_size(prs)
    headers = table.headers or [""] * (len(table.rows[0]) if table.rows else 0)
    n_cols = max(len(headers), max((len(r) for r in table.rows), default=0))
    n_rows = len(table.rows) + 1  # + header row
    if n_cols == 0 or n_rows <= 1:
        return

    left = int(width * 0.06)
    top = int(height * 0.24)
    table_w = int(width * 0.88)
    table_h = int(height * 0.66)
    shape = slide.shapes.add_table(n_rows, n_cols, left, top, table_w, table_h)
    tbl = shape.table

    # Font shrinks as the table gets denser so more content stays on one slide.
    longest = max(
        (len(c) for row in table.rows for c in row),
        default=10,
    )
    font_pt = 12 if longest <= 40 else 10 if longest <= 90 else 8

    for col_idx in range(n_cols):
        header_text = headers[col_idx] if col_idx < len(headers) else ""
        cell = tbl.cell(0, col_idx)
        _style_cell(cell, header_text, font_pt, header=True)

    for r_idx, row in enumerate(table.rows, start=1):
        for col_idx in range(n_cols):
            text = row[col_idx] if col_idx < len(row) else ""
            _style_cell(tbl.cell(r_idx, col_idx), text, font_pt, header=False)


def _style_cell(cell, text: str, font_pt: int, header: bool) -> None:
    cell.margin_left = Emu(45720)
    cell.margin_right = Emu(45720)
    cell.margin_top = Emu(18288)
    cell.margin_bottom = Emu(18288)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    cell.fill.solid()
    cell.fill.fore_color.rgb = _ACCENT_DARK if header else _WHITE
    tf = cell.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_pt)
    p.font.bold = header
    p.font.color.rgb = _WHITE if header else _TEXT_DARK


def _add_content_slide(prs: Presentation, slide_data: Slide) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    width, _ = _slide_size(prs)

    accent = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, int(width * 0.025), prs.slide_height
    )
    accent.fill.solid()
    accent.fill.fore_color.rgb = _ACCENT
    accent.line.fill.background()

    title_box = slide.shapes.add_textbox(
        int(width * 0.08), int(prs.slide_height * 0.08),
        int(width * 0.84), int(prs.slide_height * 0.14),
    )
    tp = title_box.text_frame.paragraphs[0]
    tp.text = slide_data.title
    tp.font.size = Pt(30)
    tp.font.bold = True
    tp.font.color.rgb = _ACCENT_DARK

    if slide_data.bullets:
        _add_bullets(slide, slide_data, prs)
    if slide_data.diagram:
        _add_diagram(slide, slide_data.diagram, prs)
    if slide_data.table:
        _add_table(slide, slide_data.table, prs)

    if slide_data.notes:
        slide.notes_slide.notes_text_frame.text = slide_data.notes


def _build_presentation(deck: Deck) -> Presentation:
    prs = Presentation()
    prs.slide_width = Emu(12192000)  # 16:9
    prs.slide_height = Emu(6858000)
    _add_title_slide(prs, deck)
    for slide_data in deck.slides:
        _add_content_slide(prs, slide_data)
    return prs


def render_pptx(deck: Deck) -> bytes:
    """Build the deck entirely in memory (stateless / serverless-friendly)."""
    buffer = io.BytesIO()
    _build_presentation(deck).save(buffer)
    return buffer.getvalue()


def build_pptx(deck: Deck, out_path: Path) -> Path:
    """Convenience for local use / CLI: render and write to disk."""
    out_path.write_bytes(render_pptx(deck))
    return out_path
