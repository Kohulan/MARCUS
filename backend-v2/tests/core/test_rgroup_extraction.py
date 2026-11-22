"""The R-group model's request (byte for byte the bake-off client's) and the checks of its rows."""

import hashlib
import json

import pytest

from marcus.core import rgroup_extraction as rg

URI = "data:image/png;base64,iVBORw0KGgo="

# sha256 of json.dumps(predict_rg.body_for(rec, "nuextract3-rgroup-v1", images)) from
# MARCUS-training markush-eval/bakeoff/code (the client the model was tested with), the image
# URI fixed to URI. Computed with that code on 2026-11-22; request_body must give the same bytes.
BAKEOFF = [
    (
        ["R1", "R2"],
        "CAPTION (page 3): Compounds 3a-3c. 3a: R1 = OMe, R2 = H\n(page 3) Text β-D-Glc",
        "60b7b508dfbb5b4d1382c9a78b2b5b55049e983e5dc982bb8b1b0bcb2c05cd44",
    ),
    (["R", "X", "Ar"], "", "b25a749474b3a5a44ea276bf90b7045375c2ad693c18ef8584ab4051c443b8de"),
    (
        ["R1"],
        "TABLE (page 2):\nCompound | R1\n1 | Cl\n2 | Br",
        "4e53ebd5bc067cac0b5e63c7cb759b1214d944a321276b0795572124a4982500",
    ),
]


@pytest.mark.parametrize(("labels", "context", "digest"), BAKEOFF)
def test_request_bytes_are_the_bakeoff_clients(labels, context, digest):
    body = rg.request_body("nuextract3-rgroup-v1", labels, context, URI)
    assert hashlib.sha256(json.dumps(body).encode()).hexdigest() == digest


def test_request_shape_as_trained():
    body = rg.request_body("m", ["R1", "R2"], "ctx", URI)
    assert list(body) == [
        "model", "temperature", "max_tokens", "messages", "response_format",
        "chat_template_kwargs",
    ]  # fmt: skip
    assert body["temperature"] == 0 and body["max_tokens"] == 2048
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    system, user = body["messages"]
    assert system == {"role": "system", "content": rg.SYSTEM_VISION}
    image, text = user["content"]  # the image first, then the text
    assert image == {"type": "image_url", "image_url": {"url": URI}}
    assert text == {
        "type": "text",
        "text": "The structure has these R-groups: R1, R2.\n\nPaper text near the structure:\nctx",
    }
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "rgroups", "schema": rg.schema_for(["R1", "R2"])},
    }
    assert "stream" not in body and "grammar" not in body


def test_system_prompt_is_the_trained_one():
    assert rg.SYSTEM_VISION.startswith("You read chemistry papers. A structure drawing")
    assert "(for example 3a, OMe, H, β-D-Glc, OAc)" in rg.SYSTEM_VISION
    assert rg.SYSTEM_VISION.endswith("return an empty list.")
    assert hashlib.sha256(rg.SYSTEM_VISION.encode()).hexdigest() == (
        hashlib.sha256(
            (
                "You read chemistry papers. A structure drawing in this paper has R-group "
                "placeholders. From the page image and the text, captions and tables below, "
                "list every compound that this scaffold stands for, with the substituent the "
                "paper gives for each R-group. Copy compound labels and substituents exactly as "
                "written in the paper (for example 3a, OMe, H, β-D-Glc, OAc). Use only what the "
                "paper states; never guess. If the paper does not define the R-groups, return an "
                "empty list."
            ).encode()
        ).hexdigest()
    )


def test_schema_names_every_label_and_bounds_every_string():
    schema = rg.schema_for(["R1", "X"])
    item = schema["properties"]["rows"]["items"]
    assert item["properties"]["compound"] == {"type": "string", "maxLength": 40}
    groups = item["properties"]["groups"]
    assert groups["required"] == ["R1", "X"] and groups["additionalProperties"] is False
    assert groups["properties"]["X"] == {"type": "string", "maxLength": 80}
    assert schema["required"] == ["rows"] and schema["additionalProperties"] is False


# --- parsing ----------------------------------------------------------------------------------


def _answer(*rows) -> str:
    return json.dumps({"rows": [{"compound": c, "groups": g} for c, g in rows]})


def test_rows_are_parsed_in_label_order_and_cleaned():
    raw = _answer(("3a", {"R2": "H", "R1": " OMe\u200b "}), ("3b", {"R1": "H", "R2": "OMe"}))
    rows = rg.parse_rows(raw, ["R1", "R2"])
    assert rows == [
        {"compound": "3a", "groups": {"R1": "OMe", "R2": "H"}},
        {"compound": "3b", "groups": {"R1": "H", "R2": "OMe"}},
    ]
    assert list(rows[0]["groups"]) == ["R1", "R2"]


def test_empty_and_repeated_rows_are_dropped():
    raw = _answer(("", {"R1": ""}), ("1", {"R1": "Cl"}), ("1", {"R1": "Cl"}), ("2", {"R1": ""}))
    assert rg.parse_rows(raw, ["R1"]) == [
        {"compound": "1", "groups": {"R1": "Cl"}},
        {"compound": "2", "groups": {"R1": ""}},
    ]


def test_no_rows_is_an_answer():
    assert rg.parse_rows('{"rows": []}', ["R1"]) == []


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        '{"rows": {}}',
        '{"rows": [], "extra": 1}',
        _answer(("1", {"R2": "H"})),  # another label
        _answer(("1", {"R1": "H", "R2": "H"})),  # a label too many
        _answer(("1", {"R1": 5})),
        _answer(("x" * 41, {"R1": "H"})),
        _answer(("1", {"R1": "H" * 81})),
        '{"rows": [{"compound": "1"}]}',
        "[" * 100_000,
    ],
)
def test_answers_outside_the_schema_are_refused(raw):
    with pytest.raises(rg.BadRows):
        rg.parse_rows(raw, ["R1"])


def test_rows_are_capped():
    raw = _answer(*((str(i), {"R1": "H"}) for i in range(rg.MAX_ROWS + 10)))
    assert len(rg.parse_rows(raw, ["R1"])) == rg.MAX_ROWS


def test_a_cut_answer_keeps_its_complete_rows():
    full = _answer(("3a", {"R1": "OMe"}), ("3b", {"R1": "H"}), ("3c", {"R1": "Cl"}))
    cut = full[: full.index('"3c"') + 6]
    with pytest.raises(rg.BadRows):
        rg.parse_rows(cut, ["R1"])
    assert rg.salvage_rows(cut, ["R1"]) == [
        {"compound": "3a", "groups": {"R1": "OMe"}},
        {"compound": "3b", "groups": {"R1": "H"}},
    ]
    assert rg.salvage_rows('{"rows": [{"comp', ["R1"]) == []
    assert rg.salvage_rows("garbage [", ["R1"]) == []
    # a row outside the schema ends the salvage
    bad = '{"rows":[{"compound":"1","groups":{"R1":"H"}},{"compound":"2","groups":{"R9":"H"}},'
    assert rg.salvage_rows(bad, ["R1"]) == [{"compound": "1", "groups": {"R1": "H"}}]


# --- stored shapes ------------------------------------------------------------------------------


def test_labels_error():
    assert rg.labels_error(["R1", "R2"]) is None
    for bad in (None, [], ["R1", "R1"], [""], [5], ["x" * 41], ["R\x00"], ["R"] * 31):
        assert rg.labels_error(bad) is not None, bad


def test_rows_error():
    labels = ["R1", "R2"]
    good = [{"compound": "1", "groups": {"R1": "H", "R2": "Me"}}]
    assert rg.rows_error(good, labels) is None
    assert rg.rows_error([], labels) is None
    for bad in (
        None,
        {"compound": "1"},
        [{"compound": "1", "groups": {"R2": "Me", "R1": "H"}}],  # not in label order
        [{"compound": "1", "groups": {"R1": "H"}}],
        [{"compound": 1, "groups": {"R1": "H", "R2": "Me"}}],
        [{"compound": "1", "groups": {"R1": "H\x00", "R2": "Me"}}],
        [{"compound": "1", "groups": {"R1": "H", "R2": "Me"}, "x": 1}],
        [good[0]] * (rg.MAX_ROWS + 1),
    ):
        assert rg.rows_error(bad, labels) is not None, bad


# --- the labels asked for: only those the page text names ----------------------------------------
# OCSR sometimes adds a label the drawing does not have (DECIMER read stylissa-bromopyrroles
# page 6 as R1, R2, Z); the model then fills that column too.

STYLISSA = "(page 6) 7. R1 = R2 = Br; 8. R1 = H, R2 = Br (page 6) CONH2"


def test_a_label_the_text_never_names_is_left_out():
    assert rg.labels_to_ask(["R1", "R2", "Z"], STYLISSA) == ["R1", "R2"]


@pytest.mark.parametrize(
    ("label", "text"),
    [
        ("R1", "TABLE (page 3):\nCompound | R1 | R2"),
        ("R1", "R 1 = OMe"),  # Docling spaces a subscript
        ("R1", "R₁ = OMe"),
        ("R2", "R1 = R² = CH3"),
        ("R′", "R' = H"),
        ("R′", "R’ = H"),
        ("R″", 'R" = H'),
        ("R″", "R′′ = H"),
        ("R1′", "R 1 ′ = Glc"),
        ("R′1", "R′ 1 = Glc"),
        ("X", "3: X = Cl"),
        ("n", "n = 2"),
        ("Ar", "Ar = Ph"),
    ],
)
def test_a_label_counts_as_written_in_the_text(label, text):
    # R7 is named too: a one-letter label named alone decides nothing (rgroup_labels.WEAK)
    assert rg.labels_to_ask([label, "R7", "Z9"], f"{text}; R7 = H") == [label, "R7"]


@pytest.mark.parametrize(
    ("label", "text"),
    [
        ("R1", "R10 = H"),  # another label
        ("R", "R1 = H"),
        ("R1", "PAR1"),  # inside a word
        ("R1", "R1′ = H"),
        ("Z", "the (Z)-configured double bond"),  # a stereo descriptor
        ("R", "C-7 is (R)"),
    ],
)
def test_a_label_inside_another_token_does_not_count(label, text):
    assert rg.labels_to_ask([label, "R2"], f"{text}; R2 = H") == ["R2"]


def test_a_text_that_names_no_label_keeps_them_all():
    """No text (a page read from the image alone) or a raster figure: the text cannot tell."""
    assert rg.labels_to_ask(["R1", "Z"], "") == ["R1", "Z"]
    assert rg.labels_to_ask(["R9"], "(page 3) Compound 3 R1 = H") == ["R9"]


def test_the_labels_asked_keep_their_order():
    assert rg.labels_to_ask(["R1", "R2", "X"], "X = Cl, R2 = H, R1 = Me") == ["R1", "R2", "X"]


# --- `*`: an unlabelled attachment point -------------------------------------------------------
# The model was trained and tested on the labels printed in the paper (markush-train and
# markush-testset gold labels, 2,000+ of them): never `*`. So `*` is no label to ask for.


def test_an_unlabelled_point_is_not_asked_for():
    text = "Liang Xiong 1,2,3, * (page 3) 3a: R1 = OMe, R2 = H"  # an author's asterisk
    assert rg.labels_to_ask(["R1", "R2", "*"], text) == ["R1", "R2"]
    assert rg.labels_to_ask(["R", "*"], "") == ["R"]


def test_the_text_still_decides_among_the_labelled_ones():
    assert rg.labels_to_ask(["R1", "R2", "Z", "*"], STYLISSA) == ["R1", "R2"]


def test_a_structure_with_only_unlabelled_points_has_nothing_to_ask():
    """Owner decision 2026-11-22: such a structure is refused like one without R-groups."""
    assert rg.labels_to_ask(["*"], "R1 = H *") == []
