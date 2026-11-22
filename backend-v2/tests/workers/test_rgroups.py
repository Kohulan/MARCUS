"""The rgroups handler's inputs (page text, page image), the llama-server client (against a local
stub server) and the fake reader."""

import base64
import io
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image

from marcus.core import annotation as ann
from marcus.core import page_text
from marcus.core import rgroup_extraction as rg
from marcus.core.enums import ErrorClass, StepKind
from marcus.core.pipeline import BadResult
from marcus.core.storage import page_image_path, paper_dir
from marcus.workers.llamachat import ModelUnavailable
from marcus.workers.rgroups import inputs
from marcus.workers.rgroups.fake import FakeRgroupReader, fake_rows
from marcus.workers.rgroups.handler import extract_rgroups, get_reader, read_scaffold
from marcus.workers.rgroups.llama import LlamaRgroupReader
from marcus.workers.runtime import HANDLERS, BadInput, StepTimeout, _classify


def _text(label, text, page, layer=None):
    item = {"label": label, "text": text, "prov": [{"page_no": page}]}
    if layer:
        item["content_layer"] = layer
    return item


def _table(page, cells):
    return {
        "prov": [{"page_no": page}],
        "data": {
            "table_cells": [
                {"start_row_offset_idx": r, "start_col_offset_idx": c, "text": t}
                for r, c, t in cells
            ]
        },
    }


DOC = {
    "texts": [
        _text("text", "Far away on page one.", 1),
        _text("text", "Compounds 3a-3c were isolated.", 3),
        _text("caption", "Figure 2. Structures 3a: R1 = OMe, R2 = H; 3b: R1 = H, R2 = OMe", 3),
        _text("page_header", "Journal header", 3, layer="furniture"),
        _text("footnote", "  a  measured   in CDCl3 ", 4),
        _text("text", "", 2),
        _text("text", "Page five is too far.", 5),
    ],
    "tables": [
        _table(2, [(0, 0, "Compound"), (0, 1, "R1"), (1, 0, "3c"), (1, 1, " Cl ")]),
        _table(5, [(0, 0, "far")]),
    ],
}


# --- page text: markush_eval.page_context -------------------------------------------------------


def test_page_context_reads_pages_around_the_scaffold_captions_and_tables_first():
    assert inputs.page_context(DOC, 3) == (
        "CAPTION (page 3): Figure 2. Structures 3a: R1 = OMe, R2 = H; 3b: R1 = H, R2 = OMe\n"
        "CAPTION (page 4): a measured in CDCl3\n"
        "TABLE (page 2):\nCompound | R1\n3c | Cl\n"
        "(page 3) Compounds 3a-3c were isolated."
    )


def test_page_context_stops_before_the_part_that_would_pass_the_cap(monkeypatch):
    monkeypatch.setattr(page_text, "MAX_CHARS", 90)
    assert inputs.page_context(DOC, 3) == (
        "CAPTION (page 3): Figure 2. Structures 3a: R1 = OMe, R2 = H; 3b: R1 = H, R2 = OMe"
    )


def test_page_context_of_a_page_without_text_is_empty():
    assert inputs.page_context({"texts": [], "tables": []}, 9) == ""
    assert inputs.page_context({}, 1) == ""


# --- page image: 150 dpi size, at most 1.3 MP -------------------------------------------------


def test_model_size_is_the_150_dpi_render_capped_at_1_3_megapixels():
    # A4 at 300 dpi (PyMuPDF): 2481 x 3508; at 150 dpi 1241 x 1754 (2.18 MP), then the cap
    assert inputs.model_size(2481, 3508) == (959, 1355)
    w, h = inputs.model_size(2481, 3508)
    assert w * h <= inputs.MAX_PIXELS
    # a small page is only halved
    assert inputs.model_size(1000, 1200) == (500, 600)
    # odd sizes round up like the 150 dpi render
    assert inputs.model_size(1001, 1201) == (501, 601)
    # a long thin page keeps at least 28 px a side once scaled down
    assert inputs.model_size(40, 400_000)[0] == inputs.MIN_SIDE  # when capped, as load_image
    assert inputs.model_size(40, 40_000) == (20, 20_000)  # under the cap: only halved


def _png(path, size, mode="RGB"):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, "white" if mode == "RGB" else 255).save(path)


def _decode(uri: str) -> Image.Image:
    head, data = uri.split(",", 1)
    assert head == "data:image/png;base64"
    return Image.open(io.BytesIO(base64.b64decode(data)))


def test_page_image_is_a_png_data_uri_at_the_model_size(tmp_path):
    path = tmp_path / "0000.png"
    _png(path, (2481, 3508), mode="L")  # a grey page comes out RGB
    im = _decode(inputs.page_image_uri(path))
    assert im.format == "PNG" and im.mode == "RGB" and im.size == (959, 1355)


# --- the llama-server client ------------------------------------------------------------------


def _answer(*rows) -> str:
    return json.dumps({"rows": [{"compound": c, "groups": g} for c, g in rows]})


class Stub:
    """A llama-server stand-in on 127.0.0.1: records requests, answers as told."""

    def __init__(self):
        self.requests: list[dict] = []
        self.status = 200
        self.finish = "stop"
        self.content: object = _answer()
        self.reply: object | None = None
        self.delay = 0.0
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                stub.requests.append({"path": self.path, "raw": raw, "body": json.loads(raw)})
                if stub.delay:
                    threading.Event().wait(stub.delay)
                reply = stub.reply
                if reply is None:
                    reply = {
                        "choices": [
                            {"message": {"content": stub.content}, "finish_reason": stub.finish}
                        ]
                    }
                data = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
                self.send_response(stub.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub(monkeypatch, clear_settings_cache):
    s = Stub()
    monkeypatch.setenv("MARCUS_RGROUP_URL", s.url)
    clear_settings_cache()
    yield s
    s.close()


def _paper(page=0, doc=DOC, image=True) -> uuid.UUID:
    pid = uuid.uuid4()
    paper_dir(pid).mkdir(parents=True)
    if doc is not None:
        (paper_dir(pid) / "text.json").write_text(json.dumps(doc))
    if image:
        _png(page_image_path(pid, page), (1000, 1200))
    return pid


def test_the_handler_is_registered():
    assert HANDLERS[StepKind.RGROUPS] is extract_rgroups


def test_request_is_the_trained_one(stub):
    stub.content = _answer(("3a", {"R1": "OMe", "R2": "H"}), ("3b", {"R1": "H", "R2": "OMe"}))
    pid = _paper(page=2)
    out = read_scaffold(get_reader(), pid, 2, ["R1", "R2"])
    (req,) = stub.requests
    assert req["path"] == "/v1/chat/completions"
    body = req["body"]
    image = body["messages"][1]["content"][0]["image_url"]["url"]
    assert _decode(image).size == (500, 600)  # the 150 dpi size of the 300 dpi page
    context = inputs.page_context(DOC, 3)  # API page 2 = Docling page 3
    expected = rg.request_body("nuextract3-rgroup-v1", ["R1", "R2"], context, image)
    assert req["raw"] == json.dumps(expected).encode()  # the bytes json.dumps writes
    assert out == {
        "model": "nuextract3-rgroup-v1",
        "model_version": "vision Q8_0 llama.cpp b12554",
        "labels": ["R1", "R2"],
        "rows": [
            {"compound": "3a", "groups": {"R1": "OMe", "R2": "H"}},
            {"compound": "3b", "groups": {"R1": "H", "R2": "OMe"}},
        ],
        "truncated": False,
        "ms": out["ms"],
    }
    assert isinstance(out["ms"], int) and out["ms"] >= 0


def test_a_label_the_page_text_never_names_is_not_asked_for(stub):
    """OCSR's extra label (DECIMER's Z beside R1, R2) is no column: the model is asked for the
    labels the page text names, and the result says which those were."""
    stub.content = _answer(("3a", {"R1": "OMe", "R2": "H"}))
    out = read_scaffold(get_reader(), _paper(page=2), 2, ["R1", "R2", "Z"])
    (req,) = stub.requests
    body = req["body"]
    assert body["messages"][1]["content"][1]["text"].startswith(
        "The structure has these R-groups: R1, R2.\n\n"
    )
    assert body["response_format"]["json_schema"]["schema"] == rg.schema_for(["R1", "R2"])
    assert out["labels"] == ["R1", "R2"]
    assert out["rows"] == [{"compound": "3a", "groups": {"R1": "OMe", "R2": "H"}}]


def test_an_unlabelled_point_is_not_asked_for(stub):
    """`*` (a dummy atom without a label) is no label the model was trained on: the request
    names the labelled ones only, as the trained requests did."""
    stub.content = _answer(("3a", {"R1": "OMe", "R2": "H"}))
    doc = {**DOC, "texts": [*DOC["texts"], _text("text", "Liang Xiong 1,2, *", 3)]}
    out = read_scaffold(get_reader(), _paper(page=2, doc=doc), 2, ["R1", "R2", "*"])
    (req,) = stub.requests
    text = req["body"]["messages"][1]["content"][1]["text"]
    assert text.startswith("The structure has these R-groups: R1, R2.\n\n")
    assert out["labels"] == ["R1", "R2"]


def test_a_structure_with_only_unlabelled_points_is_bad_input(stub):
    with pytest.raises(BadInput, match="no labelled R-groups"):
        read_scaffold(get_reader(), _paper(), 0, ["*"])
    assert stub.requests == []


def test_an_answer_outside_the_schema_is_a_final_engine_error(stub):
    stub.content = _answer(("1", {"R9": "H"}))
    with pytest.raises(BadResult):
        read_scaffold(get_reader(), _paper(), 0, ["R1"])


def test_an_answer_cut_by_the_token_limit_keeps_its_complete_rows(stub):
    full = _answer(("3a", {"R1": "OMe"}), ("3b", {"R1": "H"}))
    stub.content = full[: full.index('"3b"') + 3]
    stub.finish = "length"
    out = read_scaffold(get_reader(), _paper(), 0, ["R1"])
    assert out["truncated"] is True
    assert out["rows"] == [{"compound": "3a", "groups": {"R1": "OMe"}}]


@pytest.mark.parametrize(
    "reply", [{"choices": []}, {"nope": 1}, b"not json", {"choices": [{"message": {"content": 5}}]}]
)
def test_a_reply_without_a_message_is_a_final_engine_error(stub, reply):
    stub.reply = reply
    with pytest.raises(BadResult):
        read_scaffold(get_reader(), _paper(), 0, ["R1"])


def test_a_4xx_is_final_and_a_5xx_is_retryable(stub):
    pid = _paper()
    stub.status = 400
    with pytest.raises(BadResult):
        read_scaffold(get_reader(), pid, 0, ["R1"])
    stub.status = 503
    with pytest.raises(ModelUnavailable):
        read_scaffold(get_reader(), pid, 0, ["R1"])


def test_no_server_is_retryable_and_a_slow_one_a_timeout(stub, monkeypatch, clear_settings_cache):
    pid = _paper()
    stub.delay = 1.0
    monkeypatch.setenv("MARCUS_RGROUP_TIMEOUT_S", "0.2")
    clear_settings_cache()
    with pytest.raises(StepTimeout):
        read_scaffold(get_reader(), pid, 0, ["R1"])
    monkeypatch.setenv("MARCUS_RGROUP_URL", "http://127.0.0.1:9")  # discard port: refused
    clear_settings_cache()
    with pytest.raises(ModelUnavailable):
        read_scaffold(get_reader(), pid, 0, ["R1"])


def test_runtime_classes_of_the_client_errors():
    assert _classify(ModelUnavailable("x")) == (ErrorClass.ENGINE_ERROR, True)
    assert _classify(StepTimeout("x")) == (ErrorClass.TIMEOUT, True)
    assert _classify(BadResult("x")) == (ErrorClass.ENGINE_ERROR, False)
    assert _classify(BadInput("x")) == (ErrorClass.BAD_INPUT, False)


def test_client_ignores_proxy_settings(stub, monkeypatch):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    client = LlamaRgroupReader(stub.url, 5, "m", "v")
    assert client.read(["R1"], "ctx", "data:image/png;base64,") == (_answer(), False)


def test_a_missing_or_broken_page_image_is_bad_input(stub):
    with pytest.raises(BadInput, match="missing"):
        read_scaffold(get_reader(), _paper(image=False), 0, ["R1"])
    pid = _paper(image=False)
    path = page_image_path(pid, 0)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\x89PNG broken")
    with pytest.raises(BadInput, match="could not be read"):
        read_scaffold(get_reader(), pid, 0, ["R1"])
    assert stub.requests == []  # the model is never asked


@pytest.mark.parametrize("doc", [None, "{broken", "[1, 2]"], ids=["missing", "not-json", "list"])
def test_a_paper_without_usable_text_is_read_from_the_image(stub, doc):
    pid = _paper(doc=None)
    if doc is not None:
        (paper_dir(pid) / "text.json").write_text(doc)
    read_scaffold(get_reader(), pid, 0, ["R1"])
    (req,) = stub.requests
    text = req["body"]["messages"][1]["content"][1]["text"]
    assert text.endswith("Paper text near the structure:\n")


def test_a_text_over_the_cap_is_never_parsed(stub, monkeypatch):
    pid = _paper()
    monkeypatch.setattr(ann, "MAX_TEXT_BYTES", 1)
    read_scaffold(get_reader(), pid, 0, ["R1"])
    (req,) = stub.requests
    assert req["body"]["messages"][1]["content"][1]["text"].endswith("structure:\n")


# --- the fake reader -------------------------------------------------------------------------


def test_fake_reader_is_refused_unless_fake_engines_are_enabled(monkeypatch, clear_settings_cache):
    monkeypatch.setenv("MARCUS_RGROUP_READER", "fake")
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "0")
    clear_settings_cache()
    with pytest.raises(RuntimeError):
        get_reader()
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    clear_settings_cache()
    assert isinstance(get_reader(), FakeRgroupReader)


def test_fake_reader_reads_definitions_from_the_text_in_the_models_format():
    text = inputs.page_context(DOC, 3)
    raw, cut = FakeRgroupReader(delay_s=0).read(["R1", "R2"], text, "data:")
    assert cut is False
    assert rg.parse_rows(raw, ["R1", "R2"]) == [
        {"compound": "3a", "groups": {"R1": "OMe", "R2": "H"}},
        {"compound": "3b", "groups": {"R1": "H", "R2": "OMe"}},
    ]
    assert fake_rows(["X"], text) == []  # no definition of X: no rows
    assert raw == FakeRgroupReader(delay_s=0).read(["R1", "R2"], text, "")[0]


def test_fake_handler_run(monkeypatch, clear_settings_cache):
    monkeypatch.setenv("MARCUS_RGROUP_READER", "fake")
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    clear_settings_cache()
    out = read_scaffold(get_reader(), _paper(page=2), 2, ["R1"])
    assert (out["model"], out["model_version"]) == ("fake-rgroup", "fake-1")
    assert [r["compound"] for r in out["rows"]] == ["3a", "3b"]
