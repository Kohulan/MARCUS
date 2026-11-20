"""marcus.core.annotation: fields, the decoding grammar, the output parser, the text blocks the
Paper view shows (a port of frontend-v2 doclingBlocks) and the value locator."""

import json
import re

import pytest

from marcus.core import annotation as ann


def test_fields_and_limits_are_the_trained_ones():
    assert ann.FIELDS == (
        "compound_group", "compound_class", "organism_part", "organism_or_species",
        "geo_location", "Kingdom", "trivial_name", "location", "iupac_name", "abbreviation",
        "iupac_like_name",
    )  # fmt: skip
    assert ann.MAX_LENGTH == {
        "compound_group": 435, "compound_class": 576, "organism_part": 183,
        "organism_or_species": 676, "geo_location": 348, "Kingdom": 60, "trivial_name": 397,
        "location": 234, "iupac_name": 7179, "abbreviation": 586, "iupac_like_name": 990,
    }  # fmt: skip
    assert set(ann.LABELS) == set(ann.FIELDS)
    assert ann.SYSTEM_PROMPT == "Extract the compound information from the Paragraph."


def test_grammar_has_the_keys_in_order_bounded_strings_and_no_free_whitespace():
    g = ann.grammar()
    root = next(line for line in g.splitlines() if line.startswith("root ::="))
    keys = [f'\\"{f}\\":' for f in ann.FIELDS]
    positions = [root.find(k) for k in keys]
    assert all(p >= 0 for p in positions) and positions == sorted(positions)
    for i, field in enumerate(ann.FIELDS):
        assert f"s{i} ::= " in g and f"char{{0,{ann.MAX_LENGTH[field]}}}" in g
    # no free whitespace: no literal of the object or string rules holds a space, tab or newline,
    # and no rule but `char` (the string contents) exists
    rules = [line for line in g.splitlines() if line]
    assert {r.split(" ::= ")[0] for r in rules} == {"root", "char", *(f"s{i}" for i in range(11))}
    for rule in rules:
        if rule.startswith("char ::= "):
            continue
        for literal in re.findall(r'"((?:[^"\\]|\\.)*)"', rule):
            assert not re.search(r"\s|\\[nt]", literal), (rule, literal)


def _raw(**values) -> str:
    obj = {f: values.get(f, "nan") for f in ann.FIELDS}
    return json.dumps(obj, separators=(",", ":"))


def test_parse_splits_plain_and_quoted_fields_and_dedupes():
    raw = _raw(
        compound_group="'clerodane diterpenoids', 'Clerodane Diterpenoids'",
        organism_or_species="Xylocarpus granatum, X. granatum, Xylocarpus granatum",
        location="'mono-, bi-, and tricyclic oxepanes'",
        trivial_name="Amphiol, Amphiol (1), amphiol (1), Amphiol",
        Kingdom="Plant",
    )
    out = ann.parse_output(raw)
    assert list(out) == list(ann.FIELDS)
    assert out["compound_group"] == ["clerodane diterpenoids", "Clerodane Diterpenoids"]
    assert out["organism_or_species"] == ["Xylocarpus granatum", "X. granatum"]
    assert out["location"] == ["mono-, bi-, and tricyclic oxepanes"]
    assert out["trivial_name"] == ["Amphiol", "Amphiol (1)", "amphiol (1)"]  # case is a form
    assert out["Kingdom"] == ["Plant"]
    assert out["iupac_name"] == []


def test_parse_keeps_inner_primes_and_trailing_periods():
    raw = _raw(
        trivial_name="3'-O-methylquercetin, luteolin 3'", organism_or_species="Streptomyces sp."
    )
    out = ann.parse_output(raw)
    assert out["trivial_name"] == ["3'-O-methylquercetin", "luteolin 3'"]
    assert out["organism_or_species"] == ["Streptomyces sp."]


def test_parse_drops_empty_markers_control_characters_and_a_repetition_loop():
    loop = ", ".join(["sesquiterpene"] * 30)
    raw = _raw(compound_class=loop, geo_location="nan", abbreviation="NMR,  , HPLC\u0000, \u202eX")
    out = ann.parse_output(raw)
    assert out["compound_class"] == ["sesquiterpene"]
    assert out["geo_location"] == []
    assert out["abbreviation"] == ["NMR", "HPLC", "X"]


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        json.dumps({f: "nan" for f in ann.FIELDS[:-1]}),  # a key missing
        json.dumps({**{f: "nan" for f in ann.FIELDS}, "extra": "x"}),
        json.dumps({**{f: "nan" for f in ann.FIELDS}, "Kingdom": 3}),
        json.dumps({**{f: "nan" for f in ann.FIELDS}, "Kingdom": "x" * 61}),
    ],
)
def test_parse_refuses_output_outside_the_schema(raw):
    with pytest.raises(ann.BadOutput):
        ann.parse_output(raw)


# --- docling blocks (frontend-v2/src/workspace/doclingText.ts) ---------------------------------


def _t(i, label, value, **kw):
    return {"self_ref": f"#/texts/{i}", "label": label, "text": value, **kw}


def test_blocks_follow_body_order_through_groups_and_skip_tables_and_pictures():
    doc = {
        "body": {
            "children": [
                {"$ref": "#/texts/3"},
                {"$ref": "#/groups/0"},
                {"$ref": "#/tables/0"},
                {"$ref": "#/texts/0"},
                {"$ref": "#/pictures/0"},
            ]
        },
        "texts": [
            _t(0, "text", "Last paragraph."),
            _t(1, "list_item", "First item."),
            _t(2, "list_item", "Second item."),
            _t(3, "section_header", "Results"),
        ],
        "groups": [{"children": [{"$ref": "#/texts/1"}, {"$ref": "#/texts/2"}]}],
    }
    assert ann.docling_blocks(doc) == [
        "Results", "First item.", "Second item.", "Last paragraph.",
    ]  # fmt: skip


def test_blocks_without_a_body_use_array_order_and_skip_blank_text():
    doc = {"texts": [_t(0, "section_header", "Intro"), _t(1, "text", "  "), _t(2, "text", "B.")]}
    assert ann.docling_blocks(doc) == ["Intro", "B."]


def test_blocks_skip_dangling_refs_and_a_group_that_contains_itself_but_repeat_shared_items():
    doc = {
        "body": {
            "children": [
                {"$ref": "#/texts/9"},
                {"$ref": "#/groups/0"},
                {"$ref": "nonsense"},
                {"$ref": "#/texts/0"},
            ]
        },
        "texts": [_t(0, "text", "Kept.")],
        "groups": [{"children": [{"$ref": "#/groups/0"}, {"$ref": "#/texts/0"}]}],
    }
    assert ann.docling_blocks(doc) == ["Kept.", "Kept."]


def test_blocks_walk_a_text_items_own_children():
    doc = {
        "body": {"children": [{"$ref": "#/texts/0"}]},
        "texts": [
            _t(0, "list_item", "Outer.", children=[{"$ref": "#/texts/1"}]),
            _t(1, "list_item", "Inner.", children=[{"$ref": "#/texts/1"}]),
        ],
    }
    assert ann.docling_blocks(doc) == ["Outer.", "Inner."]


@pytest.mark.parametrize("doc", [None, [], {"texts": "x"}, {"texts": [None, 3, {"text": 5}]}])
def test_blocks_of_malformed_documents_are_empty(doc):
    assert ann.docling_blocks(doc) == []


# --- locating values ---------------------------------------------------------------------------


def test_locate_finds_every_occurrence_with_utf16_offsets():
    blocks = [
        "Sinularia flexibilis was collected.",
        "From \U0001d6fc-S. flexibilis and Sinularia flexibilis.",
    ]
    loc = ann.Locator(blocks)
    hits = loc.find("Sinularia flexibilis")
    assert hits == [[0, 0, 20], [1, 26, 46]]  # the alpha is one code point, two UTF-16 units
    js_like = blocks[1].encode("utf-16-le")
    assert js_like[26 * 2 : 46 * 2].decode("utf-16-le") == "Sinularia flexibilis"


def test_locate_ignores_whitespace_soft_hyphens_dashes_and_accents_but_keeps_word_edges():
    blocks = ["Iso-\u00adlated from Taxus  brevi\u00adfolia leaves, a taxane\u2013diterpene."]
    loc = ann.Locator(blocks)
    (hit,) = loc.find("Taxus brevifolia")
    assert blocks[0][hit[1] : hit[2]] == "Taxus  brevi\u00adfolia"
    (dash,) = loc.find("taxane-diterpene")
    assert blocks[0][dash[1] : dash[2]] == "taxane\u2013diterpene"
    assert loc.find("leave") == []  # inside a word
    assert loc.find("Caf\u00e9") == []
    assert ann.Locator(["cafe\u0301 extract"]).find("Caf\u00e9") == [[0, 0, 5]]


def test_locate_prefers_the_exact_case_and_falls_back_to_any_case():
    loc = ann.Locator(["Clerodane Diterpenoids. Two clerodane diterpenoids."])
    assert loc.find("Clerodane Diterpenoids") == [[0, 0, 22]]
    assert loc.find("CLERODANE DITERPENOIDS") == [[0, 0, 22], [0, 28, 50]]
    assert loc.find("") == [] and loc.find("   ") == []


def test_locate_caps_occurrences():
    loc = ann.Locator(["NMR " * (ann.MAX_OCCURRENCES + 50)])
    assert len(loc.find("NMR")) == ann.MAX_OCCURRENCES


def test_positions_cover_every_value_of_every_field():
    loc = ann.Locator(["Taxol from Taxus brevifolia bark."])
    values = {f: [] for f in ann.FIELDS}
    values["organism_or_species"] = ["Taxus brevifolia"]
    values["organism_part"] = ["bark", "roots"]
    pos = ann.positions(loc, values)
    assert pos["organism_or_species"] == {"Taxus brevifolia": [[0, 11, 27]]}
    assert pos["organism_part"] == {"bark": [[0, 28, 32]], "roots": []}
    assert pos["Kingdom"] == {}


def test_coconut_prefill_maps_organism_fields():
    shown = {f: [] for f in ann.FIELDS}
    shown["organism_or_species"] = ["Taxus brevifolia", "T. baccata"]
    shown["organism_part"] = ["bark", "leaves"]
    shown["geo_location"] = ["Oregon", "USA"]
    shown["location"] = ["forest"]
    shown["Kingdom"] = ["Plant"]
    assert ann.coconut_prefill(shown) == {
        "organisms": [
            {"name": "Taxus brevifolia", "parts": "bark, leaves", "location": "Oregon",
             "ecosystems": ""},
            {"name": "T. baccata", "parts": "bark, leaves", "location": "Oregon",
             "ecosystems": ""},
        ],
        "kingdom": ["Plant"],
    }  # fmt: skip
    assert ann.coconut_prefill({f: [] for f in ann.FIELDS}) == {"organisms": [], "kingdom": []}


def test_coconut_ecosystems_never_take_the_habitat_or_host_field():
    """The "Habitat or host" field holds a host plant as often as a habitat (an endophyte's host):
    the model cannot tell them apart, so nothing of it becomes a COCONUT ecosystem (F4)."""
    shown = {f: [] for f in ann.FIELDS}
    shown["organism_or_species"] = ["Fusarium sp."]
    shown["location"] = ["Camptotheca acuminata", "marine sediment"]
    (organism,) = ann.coconut_prefill(shown)["organisms"]
    assert organism["ecosystems"] == ""


def test_coconut_parts_keep_a_value_with_a_comma_whole():
    """The form's parts are comma-separated: a value that holds a comma (or a double quote) is
    written in double quotes, a quote inside doubled (frontend coconutApi `list`, F4)."""
    shown = {f: [] for f in ann.FIELDS}
    shown["organism_or_species"] = ["Taxus brevifolia"]
    shown["organism_part"] = ["roots, stems", "bark", 'the "inner" bark']
    (organism,) = ann.coconut_prefill(shown)["organisms"]
    assert organism["parts"] == '"roots, stems", bark, "the ""inner"" bark"'


def test_blocks_of_a_deeply_nested_document_need_no_recursion():
    depth = 5000
    groups = [{"children": [{"$ref": f"#/groups/{i + 1}"}]} for i in range(depth)]
    groups.append({"children": [{"$ref": "#/texts/0"}]})
    doc = {"body": {"children": [{"$ref": "#/groups/0"}]}, "groups": groups,
           "texts": [_t(0, "text", "Deep.")]}  # fmt: skip
    assert ann.docling_blocks(doc) == ["Deep."]


def test_blocks_refs_are_matched_like_javascript():
    doc = {
        "body": {
            "children": [{"$ref": "#/texts/0\n"}, {"$ref": "#/texts/\u0661"}, {"$ref": "#/texts/0"}]
        },
        "texts": [_t(0, "text", "Once."), _t(1, "text", "Never.")],
    }
    assert ann.docling_blocks(doc) == ["Once."]


# --- quoted fields cut by the length limit or not exactly wrapped (review I1) -------------------


@pytest.mark.parametrize(
    ("text", "cut", "expected"),
    [
        # the repetition loop cut by maxLength: the last, unterminated value is a fragment
        ("'taxane A', 'taxane B', 'taxane B', 'tax", True, ["taxane A", "taxane B"]),
        ("'taxane A', 'taxane B', 'taxane B', 'tax", False, ["taxane A", "taxane B", "tax"]),
        ("'taxane A', 'taxane B',", False, ["taxane A", "taxane B"]),
        ("'a', 'b'.", False, ["a", "b"]),
        ("'taxane A', 'taxane B", False, ["taxane A", "taxane B"]),  # not cut: kept, unquoted
        ("'taxane A'", False, ["taxane A"]),
        ("'taxane A", False, ["taxane A"]),
        ("'mono-, bi-, and tricyclic oxepanes'", False, ["mono-, bi-, and tricyclic oxepanes"]),
        ("\u2018taxane A\u2019, \u2018taxane B\u2019", False, ["taxane A", "taxane B"]),
        # plain form: a trailing quote is a prime and stays
        ("luteolin 3', quercetin", False, ["luteolin 3'", "quercetin"]),
        ("3',4'-dihydroxyflavone, quercetin", False, ["3',4'-dihydroxyflavone", "quercetin"]),
    ],
)
def test_split_field_never_keeps_stray_quotes(text, cut, expected):
    assert ann.split_field(text, len(text) if cut else None) == expected
    assert not any(v[:1] in "'\u2018" for v in ann.split_field(text))


def test_a_plain_field_cut_by_the_length_limit_drops_its_last_fragment():
    loop = ", ".join(["sesquiterpene"] * 50)[: ann.MAX_LENGTH["compound_class"]]
    assert ann.split_field(loop, ann.MAX_LENGTH["compound_class"]) == ["sesquiterpene"]
    assert ann.split_field("alpha, bet", 10) == ["alpha"]  # cut at the limit
    assert ann.split_field("alpha, bet", 60) == ["alpha", "bet"]  # not cut


def test_parse_output_unquotes_a_cut_quoted_field():
    cut = ("'taxane A', " * 40)[: ann.MAX_LENGTH["compound_group"]]
    raw = json.dumps({f: "nan" for f in ann.FIELDS} | {"compound_group": cut})
    assert ann.parse_output(raw)["compound_group"] == ["taxane A"]


def test_locate_counts_a_lone_surrogate_as_one_code_unit():
    assert ann.Locator(["a\ud800 Taxus"]).find("Taxus") == [[0, 3, 8]]


def test_the_fast_normalisation_equals_the_per_character_rules():
    def slow(text, fold):
        chars, origin = [], []
        for i, ch in enumerate(text):
            for c in ann._piece(ch, fold):
                if c == " " and chars and chars[-1] == " ":
                    continue
                chars.append(c)
                origin.append(i)
        return "".join(chars), origin

    samples = [
        "Taxus  brevi­folia leaves", "a­ b", "x  y", "\x00\x7f́",
        "A–B  C", "ﬁne İx", "  lead", "trail  ", "café café", "",
    ]  # fmt: skip
    for text in samples:
        for fold in (False, True):
            form, origin = ann._normalise(text, fold)
            assert (form, list(origin)) == slow(text, fold), (text, fold)


def test_blocks_and_model_input_match_the_shared_parity_fixture():
    """tests/fixtures/docling_parity.json is read by this test and by frontend-v2
    src/workspace/doclingText.test.ts: the backend's walk and the Paper view's give the same
    blocks, and the model input stays as recorded (review A-M4)."""
    import pathlib

    from marcus.workers.annotate.inputs import model_input

    path = pathlib.Path(__file__).parents[1] / "fixtures" / "docling_parity.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    assert ann.docling_blocks(fixture["doc"]) == [b["text"] for b in fixture["blocks"]]
    assert model_input(fixture["doc"]) == fixture["input_text"]
