# word2ppt

Turn a **Word document or plain-text/markdown file** into a real presentation —
exported as both an **editable PowerPoint (`.pptx`)** and a **self-contained HTML deck**.
Sequential content (workflows, steps, pipelines) is automatically rendered as
**flow diagrams** — native editable shapes in PowerPoint, Mermaid SVG in HTML.

## How it works

```
upload (.docx/.txt/.md)
        │
        ▼
  parse → outline blocks            (python-docx / markdown-aware text parser)
        │
        ▼
  plan slides                       Groq LLM (free key)  ──or──  heading heuristic
        │                           detects processes → flow diagrams
        ▼
  build  ┌─ .pptx  (python-pptx, native shapes + arrows)
         └─ .html  (reveal.js + Mermaid)
```

If `GROQ_API_KEY` is set, slides are AI-restructured and summarized. Without a key,
a heading-based heuristic still produces a clean deck — so it always works.

## Quick start

```bash
cd word2ppt
cp .env.example .env        # optional: paste a free Groq key into .env
./run.sh                    # creates a venv, installs deps, serves on :8000
```

Open <http://127.0.0.1:8000>, drop a file, download the `.pptx` / `.html`.

### Get a free Groq key (optional, for AI mode)

1. Sign up at <https://console.groq.com>
2. Create a key at <https://console.groq.com/keys>
3. Put it in `.env` as `GROQ_API_KEY=...`

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/` | Upload UI |
| `GET`  | `/api/health` | Engine status (AI vs heuristic) |
| `POST` | `/api/convert` | Multipart `file` → JSON with download links |
| `GET`  | `/api/download/{name}` | Fetch a generated `.pptx` / `.html` |

## Supported input

`.docx`, `.txt`, `.md`, `.markdown`, `.text`

For text/markdown, use `#`/`##` headings (or `===`/`---` underlines) to mark slide
breaks. Headings named like *Process*, *Workflow*, *Steps*, *Pipeline* with a short
list under them become flow diagrams automatically.

## Project layout

```
app/
  config.py         settings + paths
  models.py         Deck / Slide / Diagram
  docx_parser.py    .docx → blocks
  text_parser.py    .txt/.md → blocks
  slide_planner.py  blocks → Deck (Groq + heuristic, diagram detection)
  pptx_builder.py   Deck → .pptx
  html_builder.py   Deck → reveal.js HTML
  pipeline.py       orchestration
  main.py           FastAPI app
static/index.html   upload UI
```
