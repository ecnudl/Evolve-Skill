"""T-RES-1..3: the examiner's research (registration §7.2, §21 owner rule (b); plan research row) over FakeResearch
and the scripted GLM-5.3 researcher -- offline, deterministic, no paid call."""
from __future__ import annotations

import json

import pytest

from tests.execskill_fakes import glm_roles
from tests.execskill_fakes_research import (CONTINUE, DEFINITION, NONE, FakeWikipedia, archive_fixture, definition, found,
                                      pick, query, sources, table, values)
from tests.fixtures.execskill.items import officeqa_items, spreadsheetbench_items
from skillopt.coevo5 import leakage
from skillopt.continual_eval.core import write_json
from skillopt.execskill import research
from skillopt.execskill.protocol import MAX_RESEARCH_REQUESTS, RESEARCH_MAX_CALLS, verified
from skillopt.validator_pilot.api import digest

EVIDENCE = "engineering_fixture"


def _researcher(tmp_path, replies, *, bench="officeqa", limit=MAX_RESEARCH_REQUESTS, wikipedia=None):
    roles, fake = glm_roles(tmp_path, replies)
    opened, wiki = sources(tmp_path, wikipedia=wikipedia)
    corpus = (leakage.Corpus(bench, officeqa_items(40)) if bench == "officeqa"  # 40: one item is < 5 %
              else leakage.Corpus(bench, spreadsheetbench_items(tmp_path / "sheets")) if bench == "spreadsheetbench"
              else leakage.Corpus(bench, []))
    return research.Researcher(roles, opened, corpus, bench=bench, label="unit/research", limit=limit), fake, wiki


# --------------------------------------------------------------------------------------------------- T-RES-1
def test_res1_wikipedia_requests_carry_exactly_the_frozen_parameters(tmp_path):
    researcher, fake, wiki = _researcher(tmp_path, [query("government revenue table"), pick("R1"), table()])
    got = researcher.family_material(concept="government revenue")
    assert got["status"] == "found" and got["calls"] == 3 and len(fake.seen) == 3
    assert got["table"]["rows"][1] == ["2019", "1,718", "71", "1,789"] and got["source"]["revid"] == 1001
    hosts = {(host, path) for host, path, _, _ in wiki.requests}
    assert hosts == {("en.wikipedia.org", "/w/api.php")}
    searched, parsed = wiki.requests[0][2], wiki.requests[1][2]
    assert searched == {k: str(v) for k, v in research.search_params("government revenue table").items()}
    assert parsed == {k: str(v) for k, v in research.page_params("Government revenue").items()}
    assert all("fivebench-execskill-v1" in agent for _, _, _, agent in wiki.requests)
    client = researcher.sources.wikipedia.client
    assert client.trust_env is False and client.follow_redirects is False


def test_res1_explicit_proxy_only_and_no_other_host(tmp_path):
    with pytest.raises(ValueError):
        research.Wikipedia(proxy="http://user:secret@proxy.example:3128")
    with pytest.raises(ValueError):
        research.Wikipedia(proxy="socks5://proxy.example:1080")
    research.Wikipedia(proxy="http://httpproxy-headless.kubebrain.svc.pjlab.local:3128").close()
    wiki = FakeWikipedia(redirect_to="https://elsewhere.example/w/api.php")
    opened, _ = sources(tmp_path, wikipedia=wiki)
    searched = opened.search("wikipedia", "revenue")
    assert searched["error"] == "http_302" and searched["results"] == []
    assert {host for host, _, _, _ in wiki.requests} == {"en.wikipedia.org"}  # the redirect was not followed


def test_res1_changed_archive_file_refused_on_open(tmp_path):
    root = archive_fixture(tmp_path / "archive")
    assert research.Archive(root).search("round decimal places") == ["calc-round.html"]
    (root / "calc-sum.html").write_text("<p>Adds numbers, edited after pinning.</p>", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        research.Archive(root)


def test_res1_disambiguation_and_jeopardy_dropped_also_after_redirect(tmp_path):
    opened, _ = sources(tmp_path)
    searched = opened.search("wikipedia", "government revenue table")
    assert searched["dropped"] == ["Jeopardy! answers"]
    assert [hit["title"] for hit in searched["results"]] == ["Government revenue", "Short list"]
    assert opened.fetch("wikipedia", "Budget")["dropped"] == "disambiguation"
    assert opened.fetch("wikipedia", "Quiz numbers")["dropped"] == "excluded_title"
    redirected = opened.fetch("wikipedia", "Revenue")
    assert "dropped" not in redirected and redirected["title"] == "Government revenue"


# --------------------------------------------------------------------------------------------------- T-RES-2
def test_res2_results_and_pages_archived_write_once_before_use(tmp_path):
    opened, _ = sources(tmp_path)
    searched = opened.search("wikipedia", "government revenue table")
    stored = tmp_path / "store" / "sources" / (searched["archive"] + ".json")
    kept = json.loads(stored.read_text(encoding="utf-8"))
    assert digest(kept) == searched["archive"] and [r["title"] for r in kept["results"]][1] == "Jeopardy! answers"
    page = opened.fetch("wikipedia", "Government revenue")
    assert (tmp_path / "store" / "sources" / (page["archive"] + ".json")).is_file()
    with pytest.raises(ValueError, match="Immutable"):
        write_json(stored, {**kept, "results": []})
    assert opened.fetch("wikipedia", "Government revenue") is page  # fetched again: the archived page


def test_res2_non_verbatim_quote_voids_the_finding_and_the_request_goes_on(tmp_path):
    replies = [query("derivative definition"), pick("R1"), definition("The derivative measures change."),
               query("economic growth rate"), pick("R1"), definition(DEFINITION)]
    researcher, fake, _ = _researcher(tmp_path, replies, bench="livemath")
    got = researcher.family_material(concept="derivative")
    assert got["log"][0]["void"] == "quote_not_verbatim"
    assert got["status"] == "found" and got["quote"] == DEFINITION and got["calls"] == 6 and got["rounds"] == 2
    assert got["source"] == {"title": "Derivative", "revid": 1003}


def test_res2_function_material_archive_only_and_must_name_the_function(tmp_path):
    replies = [query("round decimal places", source="wikipedia"), pick("R1"),
               found("ROUND rounds to decimal places.", ("P1", "Syntax: ROUND(Number [; Count])"))]
    researcher, _, wiki = _researcher(tmp_path, replies, bench="spreadsheetbench")
    got = researcher.family_material(concept="ROUND")
    assert got["status"] == "found" and got["subject"] == "ROUND" and wiki.requests == []
    assert got["quotes"][0]["title"] == "LibreOffice Calc: ROUND"
    material = research.material(got)
    assert material["kind"] == "function" and material["name"] == "ROUND"
    replies = [query("sum numbers range"), pick("R1"), found("Adds.", ("P1", "Adds all the numbers in a range of cells.")),
               query("sum numbers range"), query("sum numbers range")]
    researcher, _, _ = _researcher(tmp_path / "second", replies, bench="spreadsheetbench")
    missed = researcher.family_material(concept="SUM")
    assert missed["status"] == "none" and missed["log"][0]["void"] == "function_not_quoted"


def test_res2_parameter_values_must_be_written_in_their_quotes(tmp_path):
    quote = "The economy grew by 3.2 percent in 2021"
    researcher, _, _ = _researcher(tmp_path, [query("economic growth rate", source="wikipedia"), pick("R1"),
                                              values(("growth_percent", "3.2", "P1", quote))])
    got = researcher.parameter_choice(question="A typical annual growth rate.", names=["growth_percent"])
    assert got["status"] == "found" and got["values"][0]["value"] == "3.2"
    researcher, _, _ = _researcher(tmp_path / "second", [query("economic growth rate", source="wikipedia"),
                                                         pick("R1"), values(("growth_percent", "5.5", "P1", quote)),
                                                         query("economic growth rate"), query("economic growth rate")])
    wrong = researcher.parameter_choice(question="A typical annual growth rate.", names=["growth_percent"])
    assert wrong["status"] == "none" and wrong["log"][0]["void"] == "value_not_quoted"


# --------------------------------------------------------------------------------------------------- T-RES-3
def test_res3_a_round_starts_only_while_three_calls_and_a_page_fit(tmp_path):
    roles, fake = glm_roles(tmp_path, [query("government revenue table", source="wikipedia"), pick("R1"), CONTINUE,
                                       query("derivative definition", source="wikipedia"), pick("R1"), CONTINUE])
    opened, _ = sources(tmp_path)
    got = research.request(roles, opened, purpose="verify", question="What is government revenue?", label="r")
    assert (got["status"], got["reason"], got["calls"], got["rounds"]) == ("none", "calls_exhausted", 6, 2)
    assert len(fake.seen) == 6 and RESEARCH_MAX_CALLS - 6 < research.CALLS_PER_ROUND
    roles, _ = glm_roles(tmp_path / "pages", [query("government revenue table", "derivative definition",
                                                    source="wikipedia"), pick("R1", "R2", "R3"), CONTINUE])
    opened, _ = sources(tmp_path / "pages")
    got = research.request(roles, opened, purpose="verify", question="What is government revenue?", label="r")
    assert (got["reason"], got["calls"], len(got["pages"])) == ("pages_exhausted", 3, 3)


def test_res3_invalid_replies_consume_their_call_and_are_never_retried(tmp_path):
    too_many = query("a", "b", "c", "d", source="wikipedia")
    roles, fake = glm_roles(tmp_path, ["not json", too_many, '{"queries": []}'])
    opened, _ = sources(tmp_path)
    got = research.request(roles, opened, purpose="verify", question="What is revenue?", label="r")
    assert (got["status"], got["reason"], got["calls"], got["rounds"]) == ("none", "rounds_exhausted", 3, 3)
    assert len(fake.seen) == 3 and [c["valid"] for c in roles.calls] == [False, False, False]


def test_res3_at_most_24_requests_per_step_and_bench(tmp_path):
    with pytest.raises(ValueError):
        _researcher(tmp_path, [], limit=MAX_RESEARCH_REQUESTS + 1)
    researcher, fake, _ = _researcher(tmp_path / "one", [query("government revenue table"), pick("R1"), NONE],
                                      limit=1)
    assert researcher.family_material(concept="government revenue")["reason"] == "researcher_none"
    second = researcher.family_material(concept="customs receipts")
    assert (second["status"], second["reason"]) == ("not_dispatched", "requests_exhausted") and len(fake.seen) == 3
    summary = researcher.summary()
    assert summary["dispatched"] == 1 and summary["counts"] == {"family_material:none": 1,
                                                                "family_material:not_dispatched": 1}


def test_res3_requests_carrying_item_text_are_refused_before_dispatch(tmp_path):
    researcher, fake, wiki = _researcher(tmp_path, [])
    topic = "Fixture bulletin page 3 Table 4. Receipts by fiscal year"
    got = researcher.family_material(concept="receipts", topic=topic)
    assert (got["status"], got["reason"]) == ("not_dispatched", "leak:shared_8gram")
    assert fake.seen == [] and wiki.requests == []
    written = researcher.record(evidence=EVIDENCE, step="pilot/s2-officeqa/t1")
    assert verified(written, "research")["requests"][0]["reason"] == "leak:shared_8gram"


def _finding(index):
    table_value = {"page": "P1", "archive": "a" * 64, "index": index, "caption": "T",
                   "rows": [["Year", "Value"], ["2019", str(100 + index)]]}
    return {"purpose": "table", "status": "found", "table": table_value, "source": {"title": "T", "revid": index}}


def test_res3_findings_split_by_seed_disjoint_and_hashed(tmp_path):
    findings = [_finding(n) for n in range(7)] + [_finding(0)]  # the last repeats the first finding's material
    first = research.split(findings, "pilot/s2-officeqa/t1/examiner", evidence=EVIDENCE)
    again = research.split(list(reversed(findings)), "pilot/s2-officeqa/t1/examiner", evidence=EVIDENCE)
    assert first == again and verified(first, "research-split")
    ids_self = {m["id"] for m in first["g_self"]}
    ids_acc = {m["id"] for m in first["g_acc"]}
    assert not ids_self & ids_acc and len(ids_self | ids_acc) == 7 and abs(len(ids_self) - len(ids_acc)) <= 1
    assert first["g_self_sha256"] == digest(first["g_self"]) and first["g_acc_sha256"] == digest(first["g_acc"])
    other = research.split(findings, "pilot/s2-officeqa/t1/other", evidence=EVIDENCE)
    assert other["tag"] != first["tag"]
    with pytest.raises(ValueError):
        research.split([{"status": "none"}], "u", evidence=EVIDENCE)


# ------------------------------------------------------------------------- fixer regressions (reviews 2026-10-22)
def test_isolation_8_every_string_the_researcher_sees_is_screened_and_names_are_bounded(tmp_path):
    researcher, fake, _ = _researcher(tmp_path, [])
    item = next(str(i["private"]["answer"]) for i in officeqa_items(40)  # a bench item's text, on its own a hit
                if 0 < len(str(i["private"]["answer"])) <= 40
                and leakage.mechanical(str(i["private"]["answer"]), researcher.corpus))
    got = researcher.parameter_choice(question="A typical annual growth rate.", names=[item])
    assert got["status"] == "not_dispatched" and got["reason"].startswith("leak:") and fake.seen == []
    for names in ([], ["x" * 41], ["a", "b", "c", "d", "e", "f", "g"], [" "], [7]):
        with pytest.raises(ValueError, match="parameter"):
            researcher.parameter_choice(question="A typical annual growth rate.", names=names)
    leaked_rule = researcher.family_material(concept="government revenue", topic=item)
    assert leaked_rule["status"] == "not_dispatched" and fake.seen == []
