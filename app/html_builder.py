"""Render a Deck into a single self-contained reveal.js HTML file.

Flow diagrams render as native HTML boxes and arrows so they stay large and
predictable in the browser. Everything loads from CDNs, so the output is a
single portable .html file.
"""

from __future__ import annotations

import html
from pathlib import Path

from .models import Deck, Diagram, Slide, Table
from .themes import DEFAULT_THEME, Theme

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/theme/{reveal_theme}.css">
<style>
  :root {{
    --accent: #{accent}; --accent-dark: #{accent_dark};
    --page-bg: #{page_bg}; --heading: #{heading_text}; --body: #{body_text};
    --subtitle: #{subtitle_text};
    --table-header-text: #{table_header_text}; --table-stripe: #{table_stripe};
    --table-border: #{table_border};
    --diagram-fill: #{diagram_fill}; --diagram-text: #{diagram_text};
  }}
  .reveal {{ font-family: "Inter", system-ui, sans-serif; color: var(--body); }}
  .reveal .slides section {{ color: var(--body); }}
  .reveal h1, .reveal h2 {{ color: var(--heading); text-transform: none; }}
  .reveal section.title-slide {{ text-align: left; }}
  .reveal section.title-slide h1 {{
    border-left: 8px solid var(--accent); padding-left: .5em; color: var(--heading);
  }}
  .reveal .subtitle {{ color: var(--subtitle); font-size: .6em; }}
  .reveal ul {{ display: block; }}
  .reveal li {{ margin: .35em 0; }}
  .reveal section.diagram-slide {{
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
  }}
  .reveal .diagram-flow {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    min-height: 74vh;
    width: 100%;
    margin-top: .75rem;
    overflow: hidden;
  }}
  .reveal .diagram-flow.right {{
    flex-direction: row;
    align-items: stretch;
    gap: .5rem;
    min-height: 58vh;
  }}
  .reveal .diagram-node {{
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    background: var(--diagram-fill);
    color: var(--diagram-text);
    border: 4px solid var(--accent);
    border-radius: 1rem;
    padding: 1rem 1.25rem;
    min-width: 0;
    max-width: none;
    min-height: 8.5rem;
    font-size: clamp(1rem, 1.8vw, 1.7rem);
    line-height: 1.2;
    font-weight: 700;
    box-shadow: 0 1.2rem 2.2rem rgba(27, 42, 74, .08);
  }}
  .reveal .diagram-flow.right .diagram-node {{
    flex: 1 1 0;
    min-height: 14rem;
    min-width: 0;
    max-width: none;
  }}
  .reveal .diagram-arrow {{
    color: var(--accent);
    font-size: clamp(2rem, 4vw, 3.2rem);
    font-weight: 800;
    line-height: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 2rem;
    flex: 0 0 auto;
    user-select: none;
  }}
  .reveal .diagram-flow.right .diagram-arrow {{
    align-self: center;
  }}
  .reveal table {{ font-size: .5em; border-collapse: collapse; width: 100%; }}
  .reveal table th, .reveal table td {{
    border: 1px solid var(--table-border); padding: .25em .45em;
    text-align: left; vertical-align: top;
  }}
  .reveal table th {{ background: var(--accent-dark); color: var(--table-header-text); }}
  .reveal table tr:nth-child(even) td {{ background: var(--table-stripe); }}
  .reveal .slide-number {{ background: transparent; color: var(--accent); }}
</style>
</head>
<body>
<div class="reveal"><div class="slides">
{slides}
</div></div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.js"></script>
<script>
  Reveal.initialize({{ hash: true, slideNumber: "c/t", transition: "slide" }});
</script>
</body>
</html>
"""


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def diagram_label_escape(label: str) -> str:
    return html.escape(label, quote=True).replace("\n", " ").strip()


def _render_diagram(diagram: Diagram) -> str:
    nodes = []
    for i, label in enumerate(diagram.steps):
        nodes.append(f'<div class="diagram-node">{diagram_label_escape(label)}</div>')
        if i < len(diagram.steps) - 1:
            nodes.append('<div class="diagram-arrow">→</div>' if diagram.direction == "right" else '<div class="diagram-arrow">↓</div>')
    return f'<div class="diagram-flow {diagram.direction}">{"".join(nodes)}</div>'


def _render_table(table: Table) -> str:
    head = ""
    if table.headers:
        head = "<thead><tr>" + "".join(
            f"<th>{_esc(h)}</th>" for h in table.headers
        ) + "</tr></thead>"
    body_rows = "".join(
        "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
        for row in table.rows
    )
    return f"<table>{head}<tbody>{body_rows}</tbody></table>"


def _render_slide(slide: Slide) -> str:
    parts = [f"<h2>{_esc(slide.title)}</h2>"]
    if slide.bullets:
        items = "".join(f"<li>{_esc(b)}</li>" for b in slide.bullets)
        parts.append(f"<ul>{items}</ul>")
    if slide.diagram:
        parts.append(_render_diagram(slide.diagram))
    if slide.table:
        parts.append(_render_table(slide.table))
    notes = f"<aside class=\"notes\">{_esc(slide.notes)}</aside>" if slide.notes else ""
    classes = "diagram-slide" if slide.diagram and not slide.bullets and not slide.table else ""
    class_attr = f' class="{classes}"' if classes else ""
    return f"<section{class_attr}>\n{''.join(parts)}\n{notes}\n</section>"


def _title_section(deck: Deck) -> str:
    sub = f'<p class="subtitle">{_esc(deck.subtitle)}</p>' if deck.subtitle else ""
    return (
        '<section class="title-slide">\n'
        f"<h1>{_esc(deck.title)}</h1>\n{sub}\n</section>"
    )


def render_html(deck: Deck, theme: Theme = DEFAULT_THEME) -> str:
    """Build the self-contained reveal.js document as a string (stateless)."""
    sections = [_title_section(deck)] + [_render_slide(s) for s in deck.slides]
    return _TEMPLATE.format(
        title=_esc(deck.title),
        slides="\n".join(sections),
        reveal_theme="black" if theme.dark else "white",
        accent=theme.accent,
        accent_dark=theme.accent_dark,
        page_bg=theme.page_bg,
        heading_text=theme.heading_text,
        body_text=theme.body_text,
        subtitle_text=theme.subtitle_text,
        table_header_text=theme.table_header_text,
        table_stripe=theme.table_stripe,
        table_border=theme.table_border,
        diagram_fill=theme.node_fill,
        diagram_text=theme.node_text,
    )


def build_html(deck: Deck, out_path: Path, theme: Theme = DEFAULT_THEME) -> Path:
    """Convenience for local use / CLI: render and write to disk."""
    out_path.write_text(render_html(deck, theme), encoding="utf-8")
    return out_path
