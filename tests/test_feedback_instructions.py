from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _install_import_stubs() -> None:
    if "pydantic" not in sys.modules:
        pydantic = types.ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **data):
                for key, value in data.items():
                    setattr(self, key, value)

            def model_dump(self):
                return dict(self.__dict__)

        def Field(default=None, default_factory=None, **_kwargs):
            if default_factory is not None:
                return default_factory()
            return default

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

    if "docx" not in sys.modules:
        docx = types.ModuleType("docx")
        docx.Document = object
        sys.modules["docx"] = docx

        oxml = types.ModuleType("docx.oxml")
        ns = types.ModuleType("docx.oxml.ns")
        ns.qn = lambda value: value
        oxml.ns = ns
        sys.modules["docx.oxml"] = oxml
        sys.modules["docx.oxml.ns"] = ns

        table_mod = types.ModuleType("docx.table")
        table_mod.Table = object
        sys.modules["docx.table"] = table_mod

        text_mod = types.ModuleType("docx.text")
        paragraph_mod = types.ModuleType("docx.text.paragraph")
        paragraph_mod.Paragraph = object
        text_mod.paragraph = paragraph_mod
        sys.modules["docx.text"] = text_mod
        sys.modules["docx.text.paragraph"] = paragraph_mod

    if "pptx" not in sys.modules:
        pptx = types.ModuleType("pptx")
        pptx.Presentation = object
        sys.modules["pptx"] = pptx

        dml = types.ModuleType("pptx.dml")
        dml_color = types.ModuleType("pptx.dml.color")
        dml_color.RGBColor = lambda *args: args
        dml.color = dml_color
        sys.modules["pptx.dml"] = dml
        sys.modules["pptx.dml.color"] = dml_color

        enum = types.ModuleType("pptx.enum")
        shapes = types.ModuleType("pptx.enum.shapes")
        shapes.MSO_CONNECTOR = object()
        shapes.MSO_SHAPE = object()
        text = types.ModuleType("pptx.enum.text")
        text.MSO_ANCHOR = object()
        text.PP_ALIGN = object()
        enum.shapes = shapes
        enum.text = text
        sys.modules["pptx.enum"] = enum
        sys.modules["pptx.enum.shapes"] = shapes
        sys.modules["pptx.enum.text"] = text

        util = types.ModuleType("pptx.util")
        util.Emu = int
        util.Pt = int
        sys.modules["pptx.util"] = util

    if "httpx" not in sys.modules:
        httpx = types.ModuleType("httpx")

        class _Response:
            status_code = 200

            def __init__(self, text="{}"):
                self.text = text

            def json(self):
                return {}

        def post(*_args, **_kwargs):
            return _Response()

        httpx.post = post
        sys.modules["httpx"] = httpx

    if "fastapi" not in sys.modules:
        fastapi = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code=500, detail=""):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def get(self, *_args, **_kwargs):
                def decorator(func):
                    return func

                return decorator

            def post(self, *_args, **_kwargs):
                def decorator(func):
                    return func

                return decorator

        def File(default=None, **_kwargs):
            return default

        def Form(default=None, **_kwargs):
            return default

        class UploadFile:
            def __init__(self, filename=None):
                self.filename = filename

            async def read(self):
                return b""

        fastapi.FastAPI = FastAPI
        fastapi.File = File
        fastapi.Form = Form
        fastapi.HTTPException = HTTPException
        fastapi.UploadFile = UploadFile
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class _BaseResponse:
            def __init__(self, content=None):
                self.content = content
                self.status_code = 200

        class HTMLResponse(_BaseResponse):
            pass

        class JSONResponse(_BaseResponse):
            pass

        class RedirectResponse(_BaseResponse):
            pass

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        responses.RedirectResponse = RedirectResponse
        sys.modules["fastapi.responses"] = responses


_install_import_stubs()

from app.config import Settings
from app.docx_parser import Block
from app.models import Deck, Slide
from app.pipeline import convert


class FeedbackInstructionTests(unittest.TestCase):
    def test_pipeline_passes_instructions_to_planner_and_reviewer(self) -> None:
        settings = Settings(
            groq_api_key=None,
            groq_model="test-model",
            groq_fallback_model=None,
            gemini_api_key=None,
            gemini_model="test-gemini",
            max_upload_bytes=1024,
            groq_max_tokens=128,
            groq_source_chars=256,
            feedback_webhook_url=None,
        )
        blocks = [Block(kind="heading", level=1, text="Intro")]
        deck = Deck(title="Deck", subtitle="Source", slides=[Slide(title="Intro")])

        with (
            patch("app.pipeline.parse_source", return_value=blocks),
            patch("app.pipeline.plan_deck", return_value=(deck, "heuristic")) as plan_mock,
            patch("app.pipeline.review_deck", return_value=(deck, ("note",))) as review_mock,
            patch("app.pipeline.strip_diagrams", return_value=deck),
            patch("app.pipeline.render_pptx", return_value=b"pptx"),
            patch("app.pipeline.render_html", return_value="<html />"),
        ):
            convert(
                Path("example.txt"),
                settings,
                review=True,
                diagrams=False,
                instructions="make it concise",
            )

        self.assertEqual(plan_mock.call_args.kwargs["instructions"], "make it concise")
        self.assertEqual(review_mock.call_args.kwargs["instructions"], "make it concise")

    def test_pipeline_uses_source_name_not_temp_stem_for_title_hint(self) -> None:
        settings = Settings(
            groq_api_key=None,
            groq_model="test-model",
            groq_fallback_model=None,
            gemini_api_key=None,
            gemini_model="test-gemini",
            max_upload_bytes=1024,
            groq_max_tokens=128,
            groq_source_chars=256,
            feedback_webhook_url=None,
        )
        blocks = [Block(kind="text", level=0, text="Body")]
        deck = Deck(title="Deck", subtitle="Source", slides=[Slide(title="Intro")])

        with (
            patch("app.pipeline.parse_source", return_value=blocks),
            patch("app.pipeline.plan_deck", return_value=(deck, "heuristic")) as plan_mock,
            patch("app.pipeline.strip_diagrams", return_value=deck),
            patch("app.pipeline.render_pptx", return_value=b"pptx"),
            patch("app.pipeline.render_html", return_value="<html />"),
        ):
            convert(
                Path("/tmp/tmpabc123.md"),
                settings,
                source_name="Quarterly Report",
            )

        self.assertEqual(plan_mock.call_args.args[1], "Quarterly Report")

    def test_pipeline_preserves_target_slide_count(self) -> None:
        settings = Settings(
            groq_api_key=None,
            groq_model="test-model",
            groq_fallback_model=None,
            gemini_api_key=None,
            gemini_model="test-gemini",
            max_upload_bytes=1024,
            groq_max_tokens=128,
            groq_source_chars=256,
            feedback_webhook_url=None,
        )
        blocks = [Block(kind="text", level=0, text="Body")]
        deck = Deck(title="Deck", subtitle="Source", slides=[Slide(title="Intro")])

        with (
            patch("app.pipeline.parse_source", return_value=blocks),
            patch("app.pipeline.plan_deck", return_value=(deck, "heuristic")) as plan_mock,
            patch("app.pipeline.strip_diagrams", return_value=deck),
            patch("app.pipeline.render_pptx", return_value=b"pptx"),
            patch("app.pipeline.render_html", return_value="<html />"),
        ):
            convert(
                Path("/tmp/tmpabc123.md"),
                settings,
                target_slides=20,
            )

        self.assertEqual(plan_mock.call_args.args[3], 20)
        self.assertIn("Preserve at least 20 slides", plan_mock.call_args.kwargs["instructions"])

    def test_pipeline_can_disable_tables(self) -> None:
        settings = Settings(
            groq_api_key=None,
            groq_model="test-model",
            groq_fallback_model=None,
            gemini_api_key=None,
            gemini_model="test-gemini",
            max_upload_bytes=1024,
            groq_max_tokens=128,
            groq_source_chars=256,
            feedback_webhook_url=None,
        )
        blocks = [Block(kind="table", level=0, text="", rows=(("A", "B"), ("1", "2")))]
        deck = Deck(title="Deck", subtitle="Source", slides=[Slide(title="Table")])

        with (
            patch("app.pipeline.parse_source", return_value=blocks),
            patch("app.pipeline.plan_deck", return_value=(deck, "heuristic")),
            patch("app.pipeline.strip_diagrams", return_value=deck),
            patch("app.pipeline.strip_tables", return_value=deck) as strip_tables_mock,
            patch("app.pipeline.render_pptx", return_value=b"pptx"),
            patch("app.pipeline.render_html", return_value="<html />"),
        ):
            convert(
                Path("/tmp/tmpabc123.md"),
                settings,
                tables=False,
            )

        strip_tables_mock.assert_called_once()

    def test_main_bytes_path_forwards_instructions(self) -> None:
        from app.main import _convert_bytes

        fake_result = type(
            "FakeResult",
            (),
            {
                "deck": type(
                    "FakeDeck",
                    (),
                    {
                        "title": "Deck Title",
                        "slides": [type("FakeSlide", (), {"diagram": None, "table": None})()],
                    },
                )(),
                "strategy": "heuristic",
                "html": "<html />",
                "pptx_bytes": b"pptx",
                "reviewed": False,
                "review_notes": (),
            },
        )()
        with patch("app.main.convert", return_value=fake_result) as convert_mock:
            response = _convert_bytes(
                b"hello",
                ".txt",
                review=False,
                diagrams=False,
                tables=False,
                max_slides=0,
                instructions="focus on benefits",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(convert_mock.call_args.kwargs["instructions"], "focus on benefits")
        self.assertFalse(convert_mock.call_args.kwargs["tables"])


if __name__ == "__main__":
    unittest.main()
