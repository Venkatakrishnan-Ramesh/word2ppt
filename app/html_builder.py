"""Render a Deck into a single self-contained reveal.js HTML file.

Flow diagrams become Mermaid ``flowchart`` blocks, which reveal.js renders as
real SVG diagrams in the browser. Everything loads from CDNs, so the output is
a single portable .html file.
"""

from __future__ import annotations

import html
from pathlib import Path

from .models import Deck, Diagram, Slide, Table

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/theme/white.css">
<style>
  :root {{ --accent: #2d5bff; --accent-dark: #1b2a4a; }}
  .reveal {{ font-family: "Inter", system-ui, sans-serif; }}
  .reveal h1, .reveal h2 {{ color: var(--accent-dark); text-transform: none; }}
  .reveal section.title-slide {{ text-align: left; }}
  .reveal section.title-slide h1 {{
    border-left: 8px solid var(--accent); padding-left: .5em; color: var(--accent-dark);
  }}
  .reveal .subtitle {{ color: #5a6781; font-size: .6em; }}
  .reveal ul {{ display: block; }}
  .reveal li {{ margin: .35em 0; }}
  .reveal .mermaid {{ display: flex; justify-content: center; }}
  .reveal table {{ font-size: .5em; border-collapse: collapse; width: 100%; }}
  .reveal table th, .reveal table td {{
    border: 1px solid #d3dcf0; padding: .25em .45em; text-align: left; vertical-align: top;
  }}
  .reveal table th {{ background: var(--accent-dark); color: #fff; }}
  .reveal table tr:nth-child(even) td {{ background: #f4f7ff; }}
  .reveal .slide-number {{ background: transparent; color: var(--accent); }}
</style>
</head>
<body>
<div class="reveal"><div class="slides">
{slides}
</div></div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
  mermaid.initialize({{ startOnLoad: true, theme: "default",
    themeVariables: {{ primaryColor: "#ecf1ff", primaryBorderColor: "#2d5bff",
      lineColor: "#2d5bff", primaryTextColor: "#1b2a4a" }} }});
  Reveal.initialize({{ hash: true, slideNumber: "c/t", transition: "slide" }});
</script>
</body>
</html>
"""


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _mermaid_for(diagram: Diagram) -> str:
    direction = "LR" if diagram.direction == "right" else "TD"
    lines = [f"flowchart {direction}"]
    node_ids = [f"n{i}" for i in range(len(diagram.steps))]
    for nid, label in zip(node_ids, diagram.steps):
        safe = diagram_label_escape(label)
        lines.append(f'  {nid}["{safe}"]')
    for a, b in zip(node_ids, node_ids[1:]):
        lines.append(f"  {a} --> {b}")
    body = "\n".join(lines)
    return f'<div class="mermaid">\n{body}\n</div>'


def diagram_label_escape(label: str) -> str:
    # Mermaid node labels in quotes: drop characters that break parsing.
    return label.replace('"', "'").replace("\n", " ").strip()


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
        parts.append(_mermaid_for(slide.diagram))
    if slide.table:
        parts.append(_render_table(slide.table))
    notes = f"<aside class=\"notes\">{_esc(slide.notes)}</aside>" if slide.notes else ""
    return f"<section>\n{''.join(parts)}\n{notes}\n</section>"


def _title_section(deck: Deck) -> str:
    sub = f'<p class="subtitle">{_esc(deck.subtitle)}</p>' if deck.subtitle else ""
    return (
        '<section class="title-slide">\n'
        f"<h1>{_esc(deck.title)}</h1>\n{sub}\n</section>"
    )


def render_html(deck: Deck) -> str:
    """Build the self-contained reveal.js document as a string (stateless)."""
    sections = [_title_section(deck)] + [_render_slide(s) for s in deck.slides]
    return _TEMPLATE.format(title=_esc(deck.title), slides="\n".join(sections))


def build_html(deck: Deck, out_path: Path) -> Path:
    """Convenience for local use / CLI: render and write to disk."""
    out_path.write_text(render_html(deck), encoding="utf-8")
    return out_path
