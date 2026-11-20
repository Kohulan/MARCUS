"""The annotate handler, the llama-server client (against a local stub server) and the fake
annotator."""

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from marcus.core import annotation as ann
from marcus.core.pipeline import BadResult
from marcus.core.storage import paper_dir
from marcus.workers import annotate as annotate_pkg  # noqa: F401  (registers the handler)
from marcus.workers.annotate.fake import FakeAnnotator, fake_values
from marcus.workers.annotate.handler import annotate, get_annotator
from marcus.workers.annotate.llama import AnnotatorUnavailable, LlamaAnnotator
from marcus.workers.runtime import HANDLERS, BadInput, StepTimeout
from tests.workers.helpers import view

TITLE = "Taxanes from the Bark of Taxus brevifolia"
ABSTRACT = (
    "Two new taxane diterpenoids were isolated from the bark of Taxus brevifolia collected in "
    "Oregon. Their structures were established by NMR spectroscopy and HRMS."
)
INTRO = "Taxus brevifolia is a source of paclitaxel. In this study we report new taxanes."
LATER = "The bark of Taxus brevifolia was extracted with methanol (see NMR data)."


def _doc() -> dict:
    items = [
        ("title", TITLE),
        ("section_header", "Abstract"),
        ("text", ABSTRACT),
        ("section_header", "Introduction"),
        ("text", INTRO),
        ("section_header", "Experimental Section"),
        ("text", LATER),
    ]
    texts = [
        {"self_ref": f"#/texts/{i}", "label": label, "text": text, "prov": [{"page_no": 1}]}
        for i, (label, text) in enumerate(items)
    ]
    return {"body": {"children": [{"$ref": f"#/texts/{i}"} for i in range(len(texts))]},
            "texts": texts}  # fmt: skip


def _paper_with_text(doc=None) -> uuid.UUID:
    pid = uuid.uuid4()
    d = paper_dir(pid)
    d.mkdir(parents=True)
    (d / "text.json").write_text(json.dumps(doc if doc is not None else _doc()))
    return pid


def _answer(**fields) -> str:
    return json.dumps({f: fields.get(f, "nan") for f in ann.FIELDS}, separators=(",", ":"))


class Stub:
    """A llama-server stand-in on 127.0.0.1: records requests, answers as told."""

    def __init__(self):
        self.requests: list[dict] = []
        self.status = 200
        self.reply: object = {"choices": [{"message": {"content": _answer()}}]}
        self.delay = 0.0
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                stub.requests.append({"path": self.path, "body": json.loads(body)})
                if stub.delay:
                    threading.Event().wait(stub.delay)
                data = stub.reply if isinstance(stub.reply, bytes) else json.dumps(stub.reply)
                data = data.encode() if isinstance(data, str) else data
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
    monkeypatch.setenv("MARCUS_ANNOTATOR_URL", s.url)
    clear_settings_cache()
    yield s
    s.close()


def test_the_handler_is_registered():
    from marcus.core.enums import StepKind

    assert HANDLERS[StepKind.ANNOTATE] is annotate


def test_request_is_the_trained_one(stub):
    stub.reply = {
        "choices": [{"message": {"content": _answer(organism_or_species="Taxus brevifolia")}}]
    }
    pid = _paper_with_text()
    out = annotate(view(paper_id=pid), None)
    (req,) = stub.requests
    assert req["path"] == "/v1/chat/completions"
    body = req["body"]
    assert body["messages"] == [
        {"role": "system", "content": ann.SYSTEM_PROMPT},
        {"role": "user", "content": f"{TITLE}\tABSTRACT: {ABSTRACT}\tINTRODUCTION: {INTRO}"},
    ]
    assert body["temperature"] == 0 and body["max_tokens"] == 4096
    assert body["grammar"] == ann.grammar()
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["stream"] is False
    assert out["model"] == "qwen3.5-9b-marcus-v1"
    assert out["model_version"] == "Q8_0 llama.cpp b12554"
    assert out["output"]["organism_or_species"] == ["Taxus brevifolia"]
    # located everywhere in the whole text (title, abstract, introduction, later sections)
    blocks = ann.docling_blocks(_doc())
    hits = out["positions"]["organism_or_species"]["Taxus brevifolia"]
    assert [b for b, _, _ in hits] == [0, 2, 4, 6]
    assert all(blocks[b][s:e] == "Taxus brevifolia" for b, s, e in hits)
    assert isinstance(out["ms"], int) and out["ms"] >= 0


def test_values_are_deduplicated_after_decoding(stub):
    loop = ", ".join(["taxane diterpenoids"] * 20)
    stub.reply = {"choices": [{"message": {"content": _answer(compound_class=loop)}}]}
    out = annotate(view(paper_id=_paper_with_text()), None)
    assert out["output"]["compound_class"] == ["taxane diterpenoids"]


def test_an_answer_outside_the_schema_is_a_final_engine_error(stub):
    stub.reply = {"choices": [{"message": {"content": '{"Kingdom":"Plant"}'}}]}
    with pytest.raises(BadResult):
        annotate(view(paper_id=_paper_with_text()), None)


@pytest.mark.parametrize(
    "reply", [{"choices": []}, {"nope": 1}, b"not json", {"choices": [{"message": {"content": 5}}]}]
)
def test_a_reply_without_a_message_is_a_final_engine_error(stub, reply):
    stub.reply = reply
    with pytest.raises(BadResult):
        annotate(view(paper_id=_paper_with_text()), None)


def test_a_4xx_is_final_and_a_5xx_is_retryable(stub):
    pid = _paper_with_text()
    stub.status = 400
    with pytest.raises(BadResult):
        annotate(view(paper_id=pid), None)
    stub.status = 503
    with pytest.raises(AnnotatorUnavailable):
        annotate(view(paper_id=pid), None)


def test_no_server_is_retryable_and_a_slow_one_a_timeout(stub, monkeypatch, clear_settings_cache):
    pid = _paper_with_text()
    stub.delay = 1.0
    monkeypatch.setenv("MARCUS_ANNOTATOR_TIMEOUT_S", "0.2")
    clear_settings_cache()
    with pytest.raises(StepTimeout):
        annotate(view(paper_id=pid), None)
    monkeypatch.setenv("MARCUS_ANNOTATOR_URL", "http://127.0.0.1:9")  # discard port: refused
    clear_settings_cache()
    with pytest.raises(AnnotatorUnavailable):
        annotate(view(paper_id=pid), None)


def test_runtime_classes_of_the_client_errors():
    from marcus.core.enums import ErrorClass
    from marcus.workers.runtime import _classify

    assert _classify(AnnotatorUnavailable("x")) == (ErrorClass.ENGINE_ERROR, True)
    assert _classify(StepTimeout("x")) == (ErrorClass.TIMEOUT, True)
    assert _classify(BadResult("x")) == (ErrorClass.ENGINE_ERROR, False)
    assert _classify(BadInput("x")) == (ErrorClass.BAD_INPUT, False)


@pytest.mark.parametrize(
    "setup",
    [
        lambda pid: None,  # no text file
        lambda pid: (paper_dir(pid) / "text.json").write_text("{broken"),
        lambda pid: (paper_dir(pid) / "text.json").write_text("[1, 2]"),
        lambda pid: (paper_dir(pid) / "text.json").write_text(
            json.dumps({"body": {"children": []}, "texts": []})
        ),
    ],
    ids=["missing", "not-json", "not-a-document", "no-text"],
)
def test_input_problems_are_final_bad_input(stub, setup):
    pid = uuid.uuid4()
    paper_dir(pid).mkdir(parents=True)
    setup(pid)
    with pytest.raises(BadInput):
        annotate(view(paper_id=pid), None)
    assert stub.requests == []  # the model is never asked


def test_llama_client_ignores_proxy_settings(stub, monkeypatch):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    client = LlamaAnnotator(stub.url, 5, "m", "v")
    assert client.complete("text") == _answer()


# --- the fake annotator ------------------------------------------------------------------------


def test_fake_annotator_is_refused_unless_fake_engines_are_enabled(
    monkeypatch, clear_settings_cache
):
    monkeypatch.setenv("MARCUS_ANNOTATOR", "fake")
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "0")
    clear_settings_cache()
    with pytest.raises(RuntimeError):
        get_annotator()
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    clear_settings_cache()
    assert isinstance(get_annotator(), FakeAnnotator)


def test_fake_annotator_is_deterministic_and_answers_in_the_models_format():
    text = f"{TITLE}\tABSTRACT: {ABSTRACT}\tINTRODUCTION: {INTRO} Compound 1 and Compound 2."
    raw = FakeAnnotator(delay_s=0).complete(text)
    assert raw == FakeAnnotator(delay_s=0).complete(text)
    assert list(json.loads(raw)) == list(ann.FIELDS)
    values = ann.parse_output(raw)
    assert values == fake_values(text)
    assert values["organism_or_species"] == ["Taxus brevifolia"]
    assert values["organism_part"] == ["bark"]
    assert values["Kingdom"] == ["Plant"]
    assert values["trivial_name"] == ["Compound 1", "Compound 2"]
    assert values["abbreviation"] == ["NMR", "HRMS"]
    assert values["compound_class"] == ["diterpenoids"]
    assert values["iupac_name"] == []


def test_fake_handler_run_end_to_end(monkeypatch, clear_settings_cache):
    monkeypatch.setenv("MARCUS_ANNOTATOR", "fake")
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    clear_settings_cache()
    out = annotate(view(paper_id=_paper_with_text()), None)
    assert (out["model"], out["model_version"]) == ("fake-annotator", "fake-1")
    assert out["positions"]["abbreviation"]["NMR"]  # found in the abstract and later
    assert len(out["positions"]["abbreviation"]["NMR"]) == 2
