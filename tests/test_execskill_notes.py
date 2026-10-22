"""T-NOTES-1..3: typed notes, fixed headers, the lexicon screen and the caps (registration §2.2, §2.3; plan §1
notes.py, §8.1)."""
from __future__ import annotations

import pytest

from skillopt.execskill import notes, protocol
from skillopt.execskill.notes import Screened, assemble, check_bindings, header_hits, lexicon_hits, render, screen
from skillopt.validator_pilot.api import digest

H = protocol.NOTE_HEADERS
FIELDS = {
    "warnings": ["The second table continues on the next page."],
    "facts": ["Fiscal year 1990 receipts: 1,031.3", "Fiscal year 1989 receipts: 990.7"],
    "table": [["Year", "Receipts"], ["1989", "990.7"], ["1990", "1,031.3"]],
    "candidates": ["1,031.3 - 990.7"],
    "bindings": [{"name": "r1990", "value": "1,031.3", "quote": "1990 receipts were 1,031.3"}],
}


# ---------------------------------------------------------------------------------- T-NOTES-1 rendering and caps
def test_render_uses_the_fixed_headers_in_field_order():
    kept, dropped = screen(FIELDS, bench="officeqa")
    assert dropped == [] and list(kept) == ["facts", "table", "candidates", "warnings", "bindings"]
    text = render(kept, bench="officeqa", header="A helper program read the tables of this page.")
    assert text == "\n".join([
        "A helper program read the tables of this page.",
        H["facts"], "- Fiscal year 1990 receipts: 1,031.3", "- Fiscal year 1989 receipts: 990.7",
        H["table"], "| Year | Receipts |", "| 1989 | 990.7 |", "| 1990 | 1,031.3 |",
        H["candidates"], "- 1,031.3 - 990.7",
        H["warnings"], "- The second table continues on the next page.",
        H["bindings"], '- r1990 = 1,031.3 (quoted: "1990 receipts were 1,031.3")',
    ])


def test_render_empty_and_refusals():
    assert render({}, bench="officeqa", header="A helper program read the page.") == ""
    assert render({"facts": []}, bench="officeqa", header="") == ""
    assert render({"facts": ["x"]}, bench="officeqa", header="") == H["facts"] + "\n- x"
    with pytest.raises(ValueError):
        render({"facts": ["Answer with a number."]}, bench="officeqa", header="")
    with pytest.raises(ValueError):
        render({"facts": ["x"]}, bench="officeqa", header="Return the answer only.")
    with pytest.raises(ValueError):
        render({"facts": ["x"]}, bench="officeqa", header="h" * 201)


def test_assemble_caps_skip_whole_notes_in_package_order():
    assert protocol.MAX_NOTE_CHARS["officeqa"] == 4000 and protocol.MAX_NOTE_CHARS["alfworld"] == 1500
    a, b, c = "a" * 1000, "b" * 600, "c" * 400
    text, skipped = assemble([("p1", a, 1500), ("p2", "", 100), ("p3", b, 500), ("p4", c, 400), ("p5", a, 1000)],
                             bench="alfworld")
    assert text == a + "\n\n" + c
    assert skipped == [{"procedure": "p3", "reason": "over_declared_cap", "chars": 600},
                       {"procedure": "p5", "reason": "over_total_cap", "chars": 1000}]
    text, skipped = assemble([("p1", a, 4000), ("p5", a, 4000), ("p6", a, 4000), ("p7", a, 4000)], bench="searchqa")
    assert text == "\n\n".join([a, a, a]) and [s["procedure"] for s in skipped] == ["p7"]


# --------------------------------------------------------------------------- T-NOTES-2 drops are procedure faults
@pytest.mark.parametrize("bench", protocol.BENCHES)
def test_every_registered_term_drops_the_field(bench):
    for term in protocol.LEXICON[bench]:
        text = "here: %s now" % term.upper()
        hits = lexicon_hits(text, bench=bench)  # "<answer" also shows the word "answer"
        kept, dropped = screen({"facts": ["ok", text]}, bench=bench)
        assert term in hits and kept == {}, term
        assert dropped == [{"field": "facts", "reason": "lexicon", "detail": hits[0]}], term


@pytest.mark.parametrize("text, hit", [
    ("Answer only with the number.", True),
    ("Respond   only the total", True),
    ("Put it in <ANSWER> tags", True),
    ("```python", True),
    ("Round to two decimal places", True),
    ("The answers listed below", True),  # registrar decision 2026-10-22 (A3-1 (a)): inflections match
    ("A barely visible note", False),  # whole words: "bare" + "ly" is no registered suffix
    ("Returns of 1990", True),
    ("The round-trip time", True),
    ("Receipts of the United States", False),  # "units" takes no suffix without its "s"
    ("The formation of the table", False),
    ("Values around 1990, surrounding text", False),
])
def test_matching_rule_is_the_registered_one(text, hit):
    assert bool(lexicon_hits(text, bench="officeqa")) is hit
    assert protocol.LEXICON_MATCH.startswith("case-insensitive; a term starting and ending with a letter")
    assert protocol.LEXICON_SUFFIXES == ("s", "es", "ed", "d", "ing")
    assert protocol.LEXICON_VERBATIM == {"bindings": "quote", "table": "cell"}


# ticket A3-1, item 1: every inflection the old rule let through, now caught (registrar decision 2026-10-22, (a))
@pytest.mark.parametrize("word, term", [
    ("answers", "answer"), ("answered", "answer"), ("responds", "respond"), ("outputs", "output"),
    ("returned", "return"), ("returns", "return"), ("rounded", "round"), ("rounding", "round"),
    ("formatted", "format"), ("formats", "format"), ("decimal place", "decimal places"),
    ("outputting", "output"), ("single letters", "single letter"), ("unit", "units"), ("bared", "bare"),
])
def test_a3_1_inflections_are_caught(word, term):
    for bench in ("officeqa", "livemath", "searchqa", "alfworld"):
        assert lexicon_hits("Note: %s here." % word.upper(), bench=bench) == [term], (word, bench)
        kept, dropped = screen({"facts": ["Rounded to two places, in millions", "ok"]}, bench=bench)
        assert kept == {} and dropped == [{"field": "facts", "reason": "lexicon", "detail": "round"}]
    assert (lexicon_hits(word, bench="spreadsheetbench") == []) is (term == "format")


# ticket A3-1, item 2: verbatim item text in a quote or a table cell is the item's, not the procedure's (decision (b))
PUBLIC = ("Table 4. Total return on investment, in units of 1,000 dollars. Shares trade in round lots of 100; the "
          "return for 1990 was 7.5.")
VERBATIM = ("Total return on investment", "in units of 1,000", "round lots")


@pytest.mark.parametrize("quoted", VERBATIM)
def test_a3_1_a_verbatim_quote_or_table_cell_is_not_screened(quoted):
    table = {"table": [["Item", "Value"], [quoted, "7.5"]]}
    kept, dropped = screen(table, bench="officeqa", public_text=PUBLIC)
    assert dropped == [] and kept == table and kept.public_text == PUBLIC
    assert render(kept, bench="officeqa", header="").splitlines()[2] == "| %s | 7.5 |" % quoted
    binding = {"bindings": [{"name": "r", "value": "7.5", "quote": "the return for 1990 was 7.5"}]}
    kept, dropped = screen(binding, bench="officeqa", public_text=PUBLIC)
    assert dropped == [] and check_bindings(kept["bindings"], PUBLIC) == (binding["bindings"], [])
    for field in ("facts", "candidates", "warnings"):  # the same words as the procedure's own text are still caught
        kept, dropped = screen({field: [quoted]}, bench="officeqa", public_text=PUBLIC)
        assert kept == {} and dropped[0]["reason"] == "lexicon", (field, quoted)
    for fields in (table, binding):  # without the item's text (a sham, a caller without the item) every text counts
        assert screen(fields, bench="officeqa")[1][0]["reason"] == "lexicon"
    kept, _ = screen(table, bench="officeqa", public_text=PUBLIC)
    with pytest.raises(ValueError):  # a plain copy lost the item's text: render screens every text again
        render(dict(kept), bench="officeqa", header="")


def test_a3_1_only_verbatim_quotes_and_cells_are_exempt():
    not_verbatim = {"table": [["Return", "the total only"]]}  # "the total only" is not in the item's text
    assert screen(not_verbatim, bench="officeqa", public_text=PUBLIC)[1] == [
        {"field": "table", "reason": "lexicon", "detail": "return"}]
    rephrased = {"bindings": [{"name": "r", "value": "7.5", "quote": "Return for 1990: 7.5"}]}
    assert screen(rephrased, bench="officeqa", public_text=PUBLIC)[1][0]["reason"] == "lexicon"
    named = {"bindings": [{"name": "returns", "value": "7.5", "quote": "the return for 1990 was 7.5"}]}
    assert screen(named, bench="officeqa", public_text=PUBLIC)[1][0]["detail"] == "return"  # a name is screened
    with pytest.raises(ValueError):
        screen({"facts": ["x"]}, bench="officeqa", public_text=["not text"])
    assert isinstance(screen({"facts": ["x"]}, bench="officeqa")[0], Screened)


@pytest.mark.parametrize("fields, reason", [
    ({"facts": "not a list"}, "type"),
    ({"facts": [1, 2]}, "type"),
    ({"facts": ["x" * 201]}, "cap"),
    ({"candidates": ["x" * 121]}, "cap"),
    ({"table": [["c"] * 13]}, "cap"),
    ({"table": [["c"]] * 21}, "cap"),
    ({"table": [["x" * 41]]}, "cap"),
    ({"table": ["row"]}, "type"),
    ({"bindings": [{"name": "a", "value": "1"}]}, "type"),
    ({"notes": ["free text"]}, "unknown_field"),
])
def test_malformed_fields_are_dropped(fields, reason):
    kept, dropped = screen(fields, bench="searchqa")
    assert kept == {} and [d["reason"] for d in dropped] == [reason]


def test_one_drop_per_field_and_non_mapping_output():
    kept, dropped = screen({"facts": ["ok"], "warnings": ["output this"], "extra": [], "table": "x"},
                           bench="officeqa")
    assert kept == {"facts": ["ok"]}
    assert [(d["field"], d["reason"]) for d in dropped] == [("table", "type"), ("warnings", "lexicon"),
                                                            ("extra", "unknown_field")]
    assert screen(["facts"], bench="officeqa") == ({}, [{"field": None, "reason": "type", "detail": "list"}])


def test_livemath_meta_option_in_a_note_is_dropped():
    kept, dropped = screen({"candidates": ["(E) a stronger result can be proven"]}, bench="livemath")
    assert kept == {} and dropped[0]["reason"] == "meta_option"
    assert screen({"candidates": ["(E) a stronger result can be proven"]}, bench="officeqa")[0]


def test_bindings_are_checked_verbatim():
    public = "In 1990 receipts were 1,031.3 million; in 1989 they were 990.7 million."
    bindings = [
        {"name": "r1990", "value": "1,031.3", "quote": "1990 receipts were 1,031.3"},
        {"name": "r1989", "value": "990.7", "quote": "they were 990.70"},  # quote not in the text
        {"name": "r1988", "value": "975.0", "quote": "1990 receipts were 1,031.3"},  # value not in the quote
        {"name": "r1990", "value": "990.7", "quote": "were 990.7"},  # repeated name
        {"name": "max", "value": "990.7", "quote": "were 990.7"},  # a function name
        {"name": "growth", "value": "1990 receipts", "quote": "1990 receipts"},  # not a number
    ]
    kept, dropped = check_bindings(bindings, public)
    assert kept == [bindings[0]]
    assert [d["reason"] for d in dropped] == ["not_verbatim", "not_verbatim", "duplicate_name", "name", "value"]


# ----------------------------------------------------------------------- T-NOTES-3 SpreadsheetBench and "format"
def test_spreadsheetbench_exempts_format_only():
    note = {"warnings": ["Keep the date format of column B."]}
    assert screen(note, bench="spreadsheetbench") == (note, [])
    assert screen(note, bench="officeqa")[1][0]["reason"] == "lexicon"
    assert "format" not in protocol.LEXICON["spreadsheetbench"] and "format" in protocol.LEXICON["alfworld"]
    assert screen({"warnings": ["Write the output file."]}, bench="spreadsheetbench")[1][0]["detail"] == "output"


def test_header_hits_follow_the_scope():
    header = "A helper program checked the cell format."
    assert header_hits(header, benches=["spreadsheetbench"]) == []
    assert header_hits(header, benches=["spreadsheetbench", "officeqa"]) == [("officeqa", "format")]
    assert ("livemath", "stronger result") in header_hits("Prefer the stronger result.", benches=["livemath"])


# the lexicon's one hash, frozen before S2 (plan §11): the value after the registrar decision of 2026-10-22 (A3-1)
LEXICON_SHA256 = "a007ee266909803d13b10bde9030bd20ada6d676060b4b71633d5a799793ff4b"


def test_lexicon_record_is_hashed():
    record = notes.lexicon_record()
    assert record["version"] == "fivebench-execskill-v1-lexicon"
    assert record["headers"] == H and record["caps"] == protocol.MAX_NOTE_CHARS
    assert record["suffixes"] == list(protocol.LEXICON_SUFFIXES) and record["verbatim"] == protocol.LEXICON_VERBATIM
    assert notes.lexicon_sha256() == digest(record) == LEXICON_SHA256
