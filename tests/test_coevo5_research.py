"""coevo5 research (registration §7; §4 step 5b; the material of §8): the frozen sources (the Wikipedia API at fixed
parameters, the pinned archive, the disambiguation and Jeopardy filters), the bounded request loop (rounds, queries,
pages, model calls -- invalid replies included), verbatim quotes, table and definition material, and the single
rewrite of a rule. No network: Wikipedia is an ``httpx.MockTransport``; the model is a scripted client behind the real
call wrapper."""
import hashlib
import json

import httpx
import pytest

from skillopt.coevo5 import research
from skillopt.coevo5.outcomes import BudgetStop
from skillopt.coevo5.protocol import RESEARCH_MAX_CALLS, RESEARCH_MAX_PAGES
from skillopt.coevo5.research import Archive, FetchError, Sources, Wikipedia, material, request, rewrite
from skillopt.validator_pilot.api import digest
from tests.coevo5_fakes import roles

HTML = ('<div class="mw-parser-output"><p>The <b>towns</b> grew quickly.<sup class="reference"><a href="#c1">[1]</a>'
        '</sup></p><style>.mw-x{color:red}</style><script>var x = "1";</script>'
        '<table class="wikitable"><caption>Population by year</caption>\n'
        '<tr><th>Town</th><th>2000</th><th>2010</th></tr>\n'
        '<tr><td>Alpha</td><td>1,200</td><td>1,500<sup class="reference">[2]</sup></td></tr>\n'
        '<tr><td>Beta</td><td>800</td><td>950</td></tr></table>'
        '<table><tr><td>Only one column</td></tr><tr><td>12</td></tr></table>'
        '<p>A <i>prime number</i> is a natural number greater than 1 that is not a product of two smaller\n'
        'natural numbers.</p></div>')
TEXT = ["The towns grew quickly.", "Population by year", "Town | 2000 | 2010", "Alpha | 1,200 | 1,500",
        "Beta | 800 | 950", "Only one column", "12",
        "A prime number is a natural number greater than 1 that is not a product of two smaller natural numbers."]
PRIME = "A prime number is a natural number greater than 1"
CONTINUE, NONE = {"status": "continue"}, {"status": "none"}


def _q(*queries, source="wikipedia"):
    return {"queries": list(queries), "source": source}


def _p(*keys):
    return {"pages": list(keys)}


def _found(quote, page="P1", conclusion="Primes are greater than 1."):
    return {"status": "found", "conclusion": conclusion, "quotes": [{"page": page, "text": quote}]}


def _page(title, html=HTML, *, revid=7, redirects=(), disambiguation=False):
    return {"title": title, "pageid": 1, "revid": revid, "redirects": [dict(r) for r in redirects], "text": html,
            "properties": {"disambiguation": ""} if disambiguation else {"wikibase_item": "Q1"}}


def _wikipedia(searches, pages, *, seen=None, status=None, raw=None):
    """``searches``: {query: [titles]}; ``pages``: {requested title: parse value}; ``status``: {title: HTTP status};
    ``raw``: {title: response body text}."""

    def handler(req):
        params = dict(req.url.params)
        if seen is not None:
            seen.append((params, req.headers.get("user-agent")))
        if params["action"] == "query":
            hits = [{"ns": 0, "title": t, "pageid": i} for i, t in enumerate(searches.get(params["srsearch"], []))]
            return httpx.Response(200, json={"batchcomplete": True, "query": {"search": hits}})
        title = params["page"]
        if status and title in status:
            return httpx.Response(status[title], text="busy")
        if raw and title in raw:
            return httpx.Response(200, text=raw[title])
        if title not in pages:
            return httpx.Response(200, json={"error": {"code": "missingtitle"}})
        return httpx.Response(200, json={"parse": pages[title]})

    return Wikipedia(transport=httpx.MockTransport(handler))


def _archive(root, docs):
    root.mkdir(parents=True)
    index = {}
    for name, (title, body) in docs.items():
        (root / name).write_text(body, encoding="utf-8")
        index[name] = {"sha256": hashlib.sha256(body.encode()).hexdigest(), "title": title}
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return Archive(root)


def _many(n):
    """Searches "t1".."tn" find the pages "Page 1".."Page n" (each a copy of HTML)."""
    return ({"t%d" % i: ["Page %d" % i] for i in range(1, n + 1)},
            {"Page %d" % i: _page("Page %d" % i, revid=i) for i in range(1, n + 1)})


# ------------------------------------------------------------------------------------------------- page text
def test_page_text_drops_markup_and_keeps_tables_as_rows():
    body, tables = research.page_text(HTML)
    assert body.split("\n") == TEXT
    assert tables[0] == {"caption": "Population by year",
                         "rows": [["Town", "2000", "2010"], ["Alpha", "1,200", "1,500"], ["Beta", "800", "950"]]}
    assert research.eligible(tables[0]) and not research.eligible(tables[1])  # one column
    nested = research.page_text("<table><tr><td>a<table><tr><td>1</td><td>2</td></tr></table></td><td>3</td></tr>"
                                "</table>")
    assert nested[1] == [{"caption": "", "rows": [["1", "2"]]}, {"caption": "", "rows": [["a", "3"]]}]
    assert research.render_table(tables[0]) == "\n".join(TEXT[1:5])


@pytest.mark.parametrize("cell, number", [("1,200", True), ("$3.5", True), ("12%", True), ("−4", True),
                                          ("12 (2010)", False), ("abc", False), ("", False)])
def test_numeric_cells(cell, number):
    assert research.numeric(cell) is number


@pytest.mark.parametrize("rows", [
    [["a", "1"]],  # one row
    [["a", "b"], ["c", "d"]],  # no number
    [[str(i) for i in range(16)], ["x"] * 16],  # 16 columns
    [["a", str(i)] for i in range(61)],  # 61 rows
])
def test_an_ineligible_table(rows):
    assert not research.eligible({"caption": "", "rows": rows})


def test_a_long_page_is_shown_as_its_lead_and_the_lines_richest_in_the_request_words():
    lines = ["Lead line %d about nothing." % i for i in range(10)] + ["filler " * 30] * 200
    lines[150] = "The decimal rounding rule is half even."
    shown = research._excerpt("\n".join(lines), ["decimal", "rounding"], limit=1200)
    assert shown.startswith("Lead line 0 about nothing.") and "The decimal rounding rule is half even." in shown
    assert "[...]" in shown and len(shown) <= 1300
    assert research._excerpt("x" * 50, ["decimal"], limit=100) == "x" * 50


# ---------------------------------------------------------------------------------------------------- sources
def test_the_wikipedia_client_sends_the_frozen_parameters_and_reads_the_final_page():
    seen = []
    wiki = _wikipedia({"prime": ["Prime number"]},
                      {"PI": _page("Pi", redirects=[{"from": "PI", "to": "Pi"}])}, seen=seen)
    assert wiki.client.trust_env is False
    assert wiki.search("prime") == ["Prime number"]
    assert seen[-1] == ({"action": "query", "list": "search", "srsearch": "prime", "srlimit": "5", "srnamespace": "0",
                         "srprop": "", "format": "json", "formatversion": "2"}, research.USER_AGENT)
    page = wiki.page("PI")
    assert seen[-1][0] == {"action": "parse", "page": "PI", "prop": "text|revid|properties", "redirects": "1",
                           "disableeditsection": "1", "disabletoc": "1", "format": "json", "formatversion": "2"}
    assert {k: page[k] for k in ("title", "revid", "redirects", "disambiguation")} == {
        "title": "Pi", "revid": 7, "redirects": [{"from": "PI", "to": "Pi"}], "disambiguation": False}


@pytest.mark.parametrize("case, reason", [("status", "http_500"), ("missing", "api_error"), ("raw", "invalid_json"),
                                          ("malformed", "malformed_page")])
def test_a_source_answering_outside_its_interface_is_a_failed_fetch(case, reason):
    bad = dict(_page("X"))
    del bad["revid"]
    wiki = _wikipedia({}, {"X": bad} if case == "malformed" else {}, status={"X": 500} if case == "status" else None,
                      raw={"X": "<html>"} if case == "raw" else None)
    with pytest.raises(FetchError, match=reason):
        wiki.page("X")


@pytest.mark.parametrize("proxy", ["http://user:secret@proxy:3128", "socks5://proxy:1080", "proxy:3128"])
def test_a_proxy_is_explicit_and_carries_no_credentials(proxy):
    with pytest.raises(ValueError):
        Wikipedia(proxy=proxy)


def test_archive_documents_are_pinned_and_searched_by_whole_words(tmp_path):
    docs = {"decimal.txt": ("decimal module", "The decimal module rounds. Decimal context, decimal places."),
            "fractions.txt": ("fractions module", "Fractions are exact; a decimal string converts exactly."),
            "card.html": ("SearchQA task card", "<p>Return the answer inside <b>tags</b>.</p><script>x</script>")}
    archive = _archive(tmp_path / "archive", docs)
    assert archive.search("decimal") == ["decimal.txt", "fractions.txt"]  # 3 occurrences before 1
    # v2 §8: at least half of the distinct words, more of them first; whole words: "exact;" counts, "exactly" does not
    assert archive.search("decimal exact") == ["fractions.txt", "decimal.txt"]
    assert archive.search("decimal modules") == ["decimal.txt", "fractions.txt"]
    assert archive.search("decimal modules exactly") == ["fractions.txt"]  # two of three words
    assert archive.search("answer tags zebra") == ["card.html"] and archive.search("zebra") == []
    assert archive.search("...") == []
    assert archive.search("answer tags") == ["card.html"]
    assert archive.page("card.html") == "Return the answer inside tags."  # an HTML document is read as its text
    (tmp_path / "archive" / "decimal.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        Archive(tmp_path / "archive")


def test_archive_ties_are_ranked_by_name(tmp_path):
    archive = _archive(tmp_path / "archive", {"b.txt": ("b", "same words"), "a.txt": ("a", "same words")})
    assert archive.search("same words") == ["a.txt", "b.txt"]


# --------------------------------------------------------------------------------------------------- requests
def test_a_verify_request_ends_with_a_verbatim_quote_and_shows_the_researcher_no_bench_item(tmp_path):
    seen = []
    sources = Sources(_wikipedia({"prime number": ["Prime number"]}, {"Prime number": _page("Prime number")},
                                 seen=seen), None, tmp_path / "unit")
    model, script = roles(tmp_path, [_q("prime number"), _p("R1"),
                                     _found("A  prime number is a natural\nnumber greater than 1")])
    found = request(model, sources, purpose="verify", question="Is 1 a prime?", rule="Treat 1 as prime.",
                    label="s1-r1/q1")
    assert found["status"] == "found" and found["reason"] is None and found["calls"] == 3 and found["rounds"] == 1
    assert found["conclusion"] == "Primes are greater than 1."
    assert found["quotes"][0]["title"] == "Prime number" and found["quotes"][0]["revid"] == 7
    assert found["pages"] == [{"key": "P1", "source": "wikipedia", "title": "Prime number", "revid": 7,
                               "archive": found["quotes"][0]["archive"]}]
    assert [set(payload) for _, payload in script.seen] == [
        {"purpose", "request", "rule", "round", "sources", "queries_tried", "pages_read"},
        {"purpose", "request", "rule", "results", "pages_left", "pages_read"},
        {"purpose", "request", "rule", "pages"}]
    assert script.seen[0][1]["sources"] == ["wikipedia"]  # no archive configured
    assert script.seen[2][1]["pages"] == [{"key": "P1", "source": "wikipedia", "title": "Prime number",
                                           "text": "\n".join(TEXT)}]
    assert [system for system, _ in script.seen] == [research.QUERY_SYSTEM, research.PICK_SYSTEM,
                                                     research.CONCLUDE_SYSTEM["verify"]]
    assert model.count("s1-r1/q1/") == 3 and [c["label"] for c in model.calls] == [
        "s1-r1/q1/q1", "s1-r1/q1/p1", "s1-r1/q1/c1"]


def test_a_quote_that_is_not_verbatim_voids_the_finding_and_the_request_goes_on(tmp_path):
    searches, pages = _many(2)
    model, _ = roles(tmp_path, [_q("t1"), _p("R1"), _found("A prime number is any odd number"),
                                _q("t2"), _p("R1"), _found(PRIME, page="P2")])
    found = request(model, Sources(_wikipedia(searches, pages), None, tmp_path / "unit"), purpose="verify",
                    question="q", label="r")
    assert found["status"] == "found" and found["calls"] == 6 and found["quotes"][0]["title"] == "Page 2"
    assert found["log"][0]["void"] == "quote_not_verbatim" and "void" not in found["log"][1]


def test_model_calls_are_capped_at_eight_invalid_replies_included(tmp_path):
    searches, pages = _many(3)
    sources = Sources(_wikipedia(searches, pages), None, tmp_path / "unit")
    # every round valid: two full rounds (6 calls); a third cannot fit its three calls
    model, script = roles(tmp_path, [_q("t1"), _p("R1"), CONTINUE, _q("t2"), _p("R1"), CONTINUE])
    found = request(model, sources, purpose="verify", question="q", label="a")
    assert (found["status"], found["reason"], found["calls"], found["rounds"]) == ("none", "calls_exhausted", 6, 2)
    # an invalid pick consumes its call: 2 + 3 + 3 = the ceiling of 8
    model, _ = roles(tmp_path, [_q("t1"), "not json", _q("t2"), _p("R1"), CONTINUE, _q("t3"), _p("R1"), CONTINUE])
    found = request(model, Sources(_wikipedia(searches, pages), None, tmp_path / "unit"), purpose="verify",
                    question="q", label="b")
    assert (found["reason"], found["calls"], found["rounds"]) == ("rounds_exhausted", RESEARCH_MAX_CALLS, 3)
    assert found["log"][0]["pick"] is None and len(found["pages"]) == 2
    # invalid queries: each spends its round
    model, _ = roles(tmp_path, ["no", {"queries": []}, _q("a", "b", "c", "d")])
    found = request(model, sources, purpose="verify", question="q", label="c")
    assert (found["reason"], found["calls"], found["rounds"]) == ("rounds_exhausted", 3, 3)


def test_pages_are_capped_at_three_per_request(tmp_path):
    searches = {"t1": ["Page 1", "Page 2"], "t2": ["Page 3", "Page 4"]}
    pages = {t: _page(t) for t in ("Page 1", "Page 2", "Page 3", "Page 4")}
    model, script = roles(tmp_path, [_q("t1"), _p("R1", "R2"), CONTINUE, _q("t2"), _p("R1", "R2"), CONTINUE])
    found = request(model, Sources(_wikipedia(searches, pages), None, tmp_path / "unit"), purpose="verify",
                    question="q", label="r")
    assert [p["title"] for p in found["pages"]] == ["Page 1", "Page 2", "Page 3"] and RESEARCH_MAX_PAGES == 3
    assert script.seen[4][1]["pages_left"] == 1
    assert (found["reason"], found["calls"]) == ("pages_exhausted", 6)


def test_an_invalid_pick_reads_nothing_and_pages_already_picked_are_not_offered_again(tmp_path):
    searches = {"t1": ["Page 1"], "t2": ["Page 1", "Page 2"]}
    pages = {t: _page(t) for t in ("Page 1", "Page 2")}
    model, script = roles(tmp_path, [_q("t1"), _p("R9"), _q("t1"), _p("R1"), CONTINUE, _q("t2"), _p("R1"), NONE])
    found = request(model, Sources(_wikipedia(searches, pages), None, tmp_path / "unit"), purpose="verify",
                    question="q", label="r")
    assert found["log"][0]["pick"] is None and "fetched" in found["log"][0] and found["log"][0]["fetched"] == []
    assert found["log"][2]["results"] == [{"key": "R1", "source": "wikipedia", "title": "Page 2"}]
    assert (found["status"], found["reason"], found["calls"]) == ("none", "researcher_none", 8)


def test_disambiguation_and_jeopardy_pages_are_never_shown(tmp_path):
    searches = {"quiz": ["Jeopardy!", "Trivia", "Quiz (disambiguation)", "Game show"]}
    pages = {"Trivia": _page("Jeopardy! questions", redirects=[{"from": "Trivia", "to": "Jeopardy! questions"}]),
             "Quiz (disambiguation)": _page("Quiz (disambiguation)", disambiguation=True),
             "Game show": _page("Game show")}
    sources = Sources(_wikipedia(searches, pages), None, tmp_path / "unit")
    model, script = roles(tmp_path, [_q("quiz"), _p("R1", "R2", "R3"), _found(PRIME)])
    found = request(model, sources, purpose="verify", question="q", label="r")
    assert [r["title"] for r in found["log"][0]["results"]] == ["Trivia", "Quiz (disambiguation)", "Game show"]
    assert found["log"][0]["searches"][0]["dropped"] == ["Jeopardy!"]
    assert [n.get("skipped") for n in found["log"][0]["fetched"]] == ["excluded_title", "disambiguation", None]
    assert [p["title"] for p in script.seen[2][1]["pages"]] == ["Game show"]
    assert found["status"] == "found" and found["quotes"][0]["title"] == "Game show"
    archived = [json.loads(p.read_text()) for p in (tmp_path / "unit" / "sources").glob("*.json")]
    assert [r["title"] for r in next(a for a in archived if a["kind"] == "search")["results"]] == searches["quiz"]


def test_a_failed_fetch_is_recorded_and_the_request_goes_on(tmp_path):
    sources = Sources(_wikipedia({"t": ["Down", "Up"]}, {"Up": _page("Up")}, status={"Down": 500}), None,
                      tmp_path / "unit")
    model, _ = roles(tmp_path, [_q("t"), _p("R1", "R2"), _found(PRIME)])
    found = request(model, sources, purpose="verify", question="q", label="r")
    assert found["log"][0]["fetched"][0] == {"result": "R1", "title": "Down", "skipped": "http_500"}
    assert found["status"] == "found" and found["pages"][0]["title"] == "Up"


def test_a_verify_request_may_search_the_archive(tmp_path):
    archive = _archive(tmp_path / "archive", {"decimal.txt": ("decimal module", "Decimal rounds half even.")})
    sources = Sources(_wikipedia({}, {}), archive, tmp_path / "unit")
    model, script = roles(tmp_path, [_q("decimal", source="archive"), _p("R1"),
                                     _found("Decimal rounds half even.")])
    found = request(model, sources, purpose="verify", question="How does decimal round?", label="r")
    assert script.seen[0][1]["sources"] == ["wikipedia", "archive"]
    assert found["status"] == "found" and found["pages"][0] == {
        "key": "P1", "source": "archive", "title": "decimal module", "revid": None,
        "archive": found["quotes"][0]["archive"]}


# --------------------------------------------------------------------------------------------------- material
def test_table_material_is_an_eligible_table_of_a_wikipedia_page(tmp_path):
    seen, log = [], []
    archive = _archive(tmp_path / "archive", {"a.txt": ("doc", "towns towns")})
    sources = Sources(_wikipedia({"towns": ["Towns"], "towns 2": ["Towns 2"]},
                                 {"Towns": _page("Towns"), "Towns 2": _page("Towns 2", revid=9)}, seen=seen),
                      archive, tmp_path / "unit")
    model, script = roles(tmp_path, [_q("towns", source="archive"), _p("R1"),
                                     {"status": "found", "page": "P1", "table": 1},  # one column: void
                                     _q("towns 2"), _p("R1"), {"status": "found", "page": "P2", "table": 0}])
    found = material(model, sources, rule_text="Check units in tables.", style="officeqa", label="fwd", log=log)
    assert seen[0][0]["action"] == "query"  # a material request searches Wikipedia whatever the reply named
    assert [t["index"] for t in script.seen[2][1]["pages"][0]["tables"]] == [0]  # only eligible tables are shown
    assert log[0]["log"][0]["void"] == "ineligible_table" and log[0]["calls"] == 6
    assert found == {"style": "officeqa", "source": {"title": "Towns 2", "revid": 9},
                     "page": log[0]["table"]["archive"],
                     "table": {"caption": "Population by year", "rows": [["Town", "2000", "2010"],
                                                                         ["Alpha", "1,200", "1,500"],
                                                                         ["Beta", "800", "950"]]},
                     "text": "\n".join(TEXT[1:5])}
    assert script.seen[0][1]["request"] == research.MATERIAL_REQUEST["officeqa"]
    assert script.seen[0][1]["rule"] == "Check units in tables." and script.seen[0][1]["sources"] == ["wikipedia"]


def test_an_unknown_table_index_is_void(tmp_path):
    model, _ = roles(tmp_path, [_q("towns"), _p("R1"), {"status": "found", "page": "P1", "table": 5}, "x", "y"])
    log = []
    assert material(model, Sources(_wikipedia({"towns": ["Towns"]}, {"Towns": _page("Towns")}), None,
                                   tmp_path / "unit"), rule_text="r", style="officeqa", label="fwd", log=log) is None
    assert log[0]["log"][0]["void"] == "unknown_table" and (log[0]["reason"], log[0]["calls"]) == (
        "rounds_exhausted", 5)


def test_definition_material_is_a_verbatim_quote(tmp_path):
    sources = Sources(_wikipedia({"prime": ["Prime number"]}, {"Prime number": _page("Prime number")}), None,
                      tmp_path / "unit")
    model, script = roles(tmp_path, [_q("prime"), _p("R1"),
                                     {"status": "found", "page": "P1", "quote": "A prime number is an odd number"},
                                     _q("prime"), "invalid query"])
    log = []
    assert material(model, sources, rule_text="r", style="livemath", label="fwd", log=log) is None
    assert log[0]["log"][0]["void"] == "quote_not_verbatim"
    assert log[0]["log"][1]["results"] == []  # the page already read is not offered again: no pick, no conclusion
    model, script = roles(tmp_path, [_q("prime"), _p("R1"), {"status": "found", "page": "P1", "quote": PRIME}])
    found = material(model, sources, rule_text="r", style="livemath", label="fwd")
    assert found["quote"] == found["text"] == PRIME and found["source"] == {"title": "Prime number", "revid": 7}
    assert script.seen[2][0] == research.CONCLUDE_SYSTEM["definition"]


def test_a_researcher_answering_none_ends_the_request(tmp_path):
    model, script = roles(tmp_path, [_q("prime"), _p("R1"), NONE])
    log = []
    assert material(model, Sources(_wikipedia({"prime": ["P"]}, {"P": _page("P")}), None, tmp_path / "unit"),
                    rule_text="r", style="livemath", label="fwd", log=log) is None
    assert (log[0]["status"], log[0]["reason"], log[0]["calls"]) == ("none", "researcher_none", 3)


# ---------------------------------------------------------------------------------------------------- rewrite
FINDING = {"purpose": "verify", "status": "found", "question": "Is 1 prime?", "conclusion": "No.",
           "quotes": [{"page": "P1", "text": PRIME, "title": "Prime number", "revid": 7, "archive": "x"}]}


@pytest.mark.parametrize("reply, status", [
    ({"text": "Treat 1 as not prime."}, "rewritten"),
    ({"text": "Treat 1 as prime."}, "kept"),
    ("not json", "rewrite_failed"),
    ({"text": "two\n\nblocks"}, "rewrite_failed"),
    ({"text": "x" * 601}, "rewrite_failed"),
    ({"text": "# a heading"}, "rewrite_failed"),
    ({"text": " padded"}, "rewrite_failed"),
    ({"text": 5}, "rewrite_failed"),
    ({"text": "ok", "extra": 1}, "rewrite_failed"),
])
def test_one_rewrite_call_rewrites_keeps_or_fails_to_the_original(tmp_path, reply, status):
    model, script = roles(tmp_path, [reply])
    text, got = rewrite(model, "Treat 1 as prime.", [FINDING], label="s1-r1/rewrite")
    assert got == status and len(script.seen) == 1
    assert text == (reply["text"] if status == "rewritten" else "Treat 1 as prime.")
    assert script.seen[0] == (research.REWRITE_SYSTEM, {"rule": "Treat 1 as prime.", "findings": [
        {"question": "Is 1 prime?", "conclusion": "No.", "quotes": [PRIME]}]})


def test_a_rewrite_needs_qualified_findings(tmp_path):
    model, _ = roles(tmp_path, [])
    for findings in ([], [{**FINDING, "status": "none"}]):
        with pytest.raises(ValueError):
            rewrite(model, "r", findings, label="x")


# ------------------------------------------------------------------------------------------ archive and stops
def test_everything_fetched_is_archived_write_once_by_hash(tmp_path):
    seen = []
    sources = Sources(_wikipedia({"t": ["Page 1"]}, {"Page 1": _page("Page 1")}, seen=seen), None,
                      tmp_path / "unit")
    for label in ("a", "b"):
        model, _ = roles(tmp_path, [_q("t"), _p("R1"), _found(PRIME)])
        request(model, sources, purpose="verify", question="q", label=label)
    files = sorted((tmp_path / "unit" / "sources").glob("*.json"))
    values = [json.loads(path.read_text()) for path in files]
    assert all(digest(value) == path.stem for value, path in zip(values, files))
    assert sorted(v["kind"] for v in values) == ["page", "search"]  # identical search and page: one file each
    assert sum(1 for params, _ in seen if params["action"] == "parse") == 1  # the archived page is reused
    page = next(path for path, value in zip(files, values) if value["kind"] == "page")
    page.write_text(json.dumps({"kind": "page", "tampered": True}))
    with pytest.raises(ValueError, match="differs"):
        sources.keep(values[[v["kind"] for v in values].index("page")])


def test_a_stop_of_the_run_propagates_out_of_a_request(tmp_path):
    def stop(system, payload):
        raise BudgetStop("budget_stop:overall")

    model, _ = roles(tmp_path, stop)
    with pytest.raises(BudgetStop):
        request(model, Sources(_wikipedia({}, {}), None, tmp_path / "unit"), purpose="verify", question="q",
                label="r")
    assert model.calls[0]["sends"] and model.calls[0]["valid"] is False


@pytest.mark.parametrize("kwargs", [{"purpose": "explore"}, {"question": " "}, {"label": ""}, {"rule": ""}])
def test_a_malformed_request_is_refused(tmp_path, kwargs):
    model, _ = roles(tmp_path, [])
    with pytest.raises(ValueError):
        request(model, Sources(_wikipedia({}, {}), None, tmp_path / "unit"),
                **{"purpose": "verify", "question": "q", "label": "r", **kwargs})
