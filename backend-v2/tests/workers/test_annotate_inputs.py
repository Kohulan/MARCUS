"""The model input builder (a port of the training builder; checked once against all 833
training-corpus documents: identical input text for every one)."""

from marcus.workers.annotate.inputs import MAX_CHARS, model_input, scrub_emails


def _doc(items: list[tuple[str, str]]) -> dict:
    texts = [
        {"self_ref": f"#/texts/{i}", "label": label, "text": text, "prov": [{"page_no": 1}]}
        for i, (label, text) in enumerate(items)
    ]
    return {"body": {"children": [{"$ref": f"#/texts/{i}"} for i in range(len(texts))]},
            "texts": texts}  # fmt: skip


ABSTRACT = (
    "Two new clerodane diterpenoids were isolated from the leaves of Casearia sylvestris. "
    "Their structures were elucidated by NMR and HRMS data and showed cytotoxic activity."
)
INTRO = (
    "Casearia species are known as a rich source of clerodane diterpenoids. In this study "
    "we report the isolation of two compounds."
)


def test_title_abstract_and_introduction_in_the_trained_format():
    doc = _doc(
        [
            ("title", "Clerodane Diterpenoids from Casearia sylvestris"),
            ("section_header", "Abstract"),
            ("text", ABSTRACT),
            ("section_header", "1. Introduction"),
            ("text", INTRO),
            ("section_header", "2. Results and Discussion"),
            ("text", "Compound 1 was obtained as a white powder."),
        ]
    )
    assert model_input(doc) == (
        "Clerodane Diterpenoids from Casearia sylvestris"
        f"\tABSTRACT: {ABSTRACT}\tINTRODUCTION: {INTRO}"
    )


def test_input_is_capped_at_paragraph_or_sentence_boundaries():
    long_intro = [("text", f"Sentence {i} about Casearia. " * 40) for i in range(10)]
    doc = _doc(
        [("title", "A Long Paper about Casearia Species"), ("section_header", "Abstract"),
         ("text", ABSTRACT), ("section_header", "Introduction"), *long_intro]
    )  # fmt: skip
    text = model_input(doc)
    assert len(text) <= MAX_CHARS
    assert text.endswith(".")


def test_emails_are_removed_with_their_label():
    assert scrub_emails("Contact. E-mail: a.b@uni-jena.de; c@x.org. Next") == "Contact. . Next"
    assert scrub_emails("no address here") == "no address here"


def test_a_document_without_text_gives_an_empty_input():
    assert model_input({"body": {"children": []}, "texts": []}) == ""
