"""Registrar decision C3-1 (b) (registration §8.1, Codex F16; tickets fixer-4, C3-1): the test read's second canary
record -- made once per run root, under the owner's test-read consent only, from OfficeQA's, LiveMath's and
SpreadsheetBench's test sets and kept as lengths and sha256 prefixes -- merged after the S0 exclusion unit's record by
``load_canaries``; a read unit makes it before its attempt (``run_unit_spec``); the whole run root is searched for every
canary before a chain's first unseal, and a hit pauses for the owner before any score is read. Registrar decision
PR-C31-3 (addendum 14:1x): the read record skips test texts found verbatim in the same field of the training-side pool
items; the owner's ``release <scan record_sha256>`` lets a later scan with exactly those hits pass; the scan's process
pool gives the one-process result. Offline: synthetic test panels, synthetic training pools and fixture texts (never a
test pool), no model call; nothing is printed."""
from __future__ import annotations

import html
import io
import json
import os
import zipfile

from concurrent.futures import ProcessPoolExecutor

import pytest

from scripts import run_execskill as cli
from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json, safe_path, write_json
from skillopt.execskill import budgets, chain, evaluation, package
from skillopt.execskill.cells import Pause
from skillopt.execskill.protocol import CANARIES, RECORD_HASH, record, verified
from skillopt.validator_pilot.api import digest
from tests.test_execskill_evaluation import (CHAIN, EVIDENCE, READ_TEXTS, RUN, S0_TEXTS, TRAINING_TEXTS, ReadPanel,
                                             Solver, consent_value, pool_pins, read, register_canaries, s0_canaries)

READ_BENCHES = ("livemath", "officeqa", "spreadsheetbench")
EXCLUSION_CONSENT = {"exclusion_runs": ["alfworld_test_identity_check", "searchqa_test_exclusion"], "by": "owner",
                     "date": "2026-10-21", "note": "The two S0 exclusion runs only."}


def chosen(bench, made):
    """The fixture texts of ``bench`` that the registered selection made canaries."""
    return [text for text in READ_TEXTS[bench]
            if len(text) >= evaluation.MIN_CANARY_CHARS and evaluation.canary(text) in made["canaries"]]


def fields(value):
    return {k: v for k, v in value.items() if k not in ("version", "evidence", RECORD_HASH)}


def ended(root):
    """Chain D's read is complete and the owner's continuation file exists: an unseal may begin."""
    write_json(root / CHAIN / "chain-complete.json", record("chain-complete", EVIDENCE, {"chain": CHAIN}))
    write_json(root / "shared" / "owner-continuation.json",
               {"by": "owner", "date": "2026-10-22", "decision": "continue", "note": "go on"})


def unseal(root, unit_root):
    return evaluation.unseal(root, root / CHAIN, CHAIN, [unit_root], run=RUN, evidence=EVIDENCE,
                             clock=lambda: "2026-10-22T12:00:00Z")


def without(paths, texts):
    """None of ``texts`` occurs in any of ``paths``."""
    for path in paths:
        stored = path.read_text(encoding="utf-8")
        assert not any(text in stored for text in texts), path


def workbook(text):
    """A generated SpreadsheetBench input workbook whose shared strings hold ``text`` (XML-escaped)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/sharedStrings.xml", "<sst><si><t>%s</t></si></sst>" % html.escape(text, quote=True))
    return buffer.getvalue()


# --------------------------------------------------------------------------------------- the second record
def test_the_read_canaries_are_refused_without_the_owners_test_read_consent(tmp_path):
    panel, pools = ReadPanel(), pool_pins(tmp_path / "pools")
    for n, value in enumerate((None, consent_value(test_evaluation=False), consent_value(extra=1))):
        root = tmp_path / str(n)
        s0_canaries(root)
        write_json(root / "shared" / "exclusion-consent.json", EXCLUSION_CONSENT)  # covers the S0 runs only
        if value is not None:
            write_json(root / "shared" / "consent.json", value)
        with pytest.raises(ValueError, match="consent"):
            evaluation.make_read_canaries(root, None, pools=pools, run=RUN, evidence=EVIDENCE, panel=panel)
        assert not (root / evaluation.READ_CANARIES).exists()
        with pytest.raises(ValueError, match="not made"):
            evaluation.load_canaries(root, read=True)
    assert panel.seen == []  # no test set was opened


def test_the_read_canaries_are_made_once_from_three_test_sets_and_merged_after_s0s(tmp_path, capsys):
    root, pools = tmp_path / "run-root", pool_pins(tmp_path / "pools")
    write_json(root / "shared" / "consent.json", consent_value())
    with pytest.raises(ValueError, match="No registered test canaries"):  # make-manifest writes S0's record first
        evaluation.make_read_canaries(root, None, pools=pools, run=RUN, evidence=EVIDENCE, panel=ReadPanel())
    first = s0_canaries(root)
    assert evaluation.load_canaries(root) == first["canaries"]  # before the read: S0's alone
    panel = ReadPanel()
    made = evaluation.make_read_canaries(root, "pinned", pools=pools, run=RUN, evidence=EVIDENCE, panel=panel)
    assert panel.seen == [(bench, evaluation.READ_CANARY_UNIT) for bench in READ_BENCHES]
    assert made == verified(read_json(root / evaluation.READ_CANARIES), "test-read-canaries")
    assert made["counts"] == {bench: evaluation.CANARIES_PER_BENCH for bench in READ_BENCHES}
    # PR-C31-3 (1a): no fixture test text is on the training side, so nothing is skipped and the selection is S0's
    assert made["skipped"] == {bench: 0 for bench in READ_BENCHES}
    assert made["training_pools"] == {"livemath": None, "officeqa": pools["officeqa"]["sha256"],
                                      "spreadsheetbench": pools["spreadsheetbench"]["sha256"]}
    assert made["canaries"] == evaluation.select_canaries(READ_TEXTS)[0]
    assert (made["extends"], made["run"], made["consent_sha256"]) == (first[RECORD_HASH], RUN, digest(consent_value()))
    assert made["sources"] == {"livemath": "the public question", "officeqa": "the public question",
                               "spreadsheetbench": "the public instruction"}
    assert set(made["panels"]) == set(READ_BENCHES) and made["unit"] == evaluation.READ_CANARY_UNIT
    assert all(set(found) == {"chars", "sha256_16"} for found in made["canaries"])
    assert all(len(chosen(bench, made)) == evaluation.CANARIES_PER_BENCH for bench in READ_BENCHES)
    # the selection is the S0 exclusion unit's: the CLI's make_canaries picks the same texts
    assert evaluation.select_canaries(S0_TEXTS)[0] == cli.make_canaries(S0_TEXTS, unit="u", consent_record={})[
        "canaries"]
    # lengths and sha256 prefixes only: no text in the record
    without([root / evaluation.READ_CANARIES], [text for texts in READ_TEXTS.values() for text in texts])
    # made once: the other units and chain read it, and no test set is opened again
    again = ReadPanel({bench: ["Another fixture text that is long enough, number %d" % n for n in range(6)]
                       for bench in READ_BENCHES})
    assert evaluation.make_read_canaries(root, "pinned", pools=pools, run=RUN, evidence=EVIDENCE, panel=again) == made
    assert again.seen == []
    merged = evaluation.load_canaries(root, read=True)
    assert merged == first["canaries"] + made["canaries"] == evaluation.load_canaries(root) and len(merged) == 25
    with pytest.raises(ValueError, match="another run"):
        evaluation.make_read_canaries(root, "pinned", pools=pools, run="another-run", evidence=EVIDENCE, panel=again)
    assert capsys.readouterr() == ("", "")


def test_a_read_record_that_extends_another_root_or_bench_set_or_holds_text_is_refused(tmp_path):
    root = tmp_path / "run-root"
    write_json(root / "shared" / "consent.json", consent_value())
    made = register_canaries(root)
    first = verified(read_json(root / CANARIES), "test-canaries")
    cases = {
        "another-root": (record("test-canaries", "smoke", {**fields(first), "consent_sha256": "1" * 64}), made),
        "a-bench-of-s0": (first, record("test-read-canaries", EVIDENCE, {
            **fields(made), "counts": {"searchqa": 5, "livemath": 5, "officeqa": 5}})),
        "miscounted": (first, record("test-read-canaries", EVIDENCE, {
            **fields(made), "counts": {"livemath": 4, "officeqa": 5, "spreadsheetbench": 5}})),
        "with-text": (first, record("test-read-canaries", EVIDENCE, {
            **fields(made), "canaries": [{**made["canaries"][0], "text": READ_TEXTS["officeqa"][0]},
                                         *made["canaries"][1:]]})),
        # PR-C31-3 (1a): a read record that does not name the training pools it checked and the texts it skipped
        "without-the-skip": (first, record("test-read-canaries", EVIDENCE, {
            k: v for k, v in fields(made).items() if k not in ("skipped", "training_pools")})),
        "a-skip-of-text": (first, record("test-read-canaries", EVIDENCE, {
            **fields(made), "skipped": {**made["skipped"], "officeqa": [READ_TEXTS["officeqa"][0]]}})),
    }
    for name, (s0, second) in cases.items():
        write_json(tmp_path / name / CANARIES, s0)
        write_json(tmp_path / name / evaluation.READ_CANARIES, second)
        with pytest.raises(ValueError, match="extend|counted|lengths|training side"):
            evaluation.load_canaries(tmp_path / name)


def test_the_read_selection_skips_test_texts_found_verbatim_in_the_same_field_of_the_training_pools(tmp_path):
    root = tmp_path / "run-root"
    write_json(root / "shared" / "consent.json", consent_value())
    s0_canaries(root)
    unfiltered = {"canaries": evaluation.select_canaries(READ_TEXTS)[0]}
    oq, sb, lm = (chosen(bench, unfiltered) for bench in ("officeqa", "spreadsheetbench", "livemath"))
    # oq[0] quoted inside a training question, sb[0] a training instruction verbatim; oq[1] only in a training
    # context (another field) and lm[0] in OfficeQA's training questions (another bench): those two stay eligible
    quoted = "Training question quoting a test one: %s (in millions)" % oq[0]
    pools = pool_pins(tmp_path / "pools", {"officeqa": TRAINING_TEXTS["officeqa"] + [quoted, lm[0]],
                                           "spreadsheetbench": TRAINING_TEXTS["spreadsheetbench"] + [sb[0]]},
                      others={"officeqa": [{"question": "A training question of its own, long enough?",
                                            "context": "Page 3 reads: " + oq[1]}]})
    made = evaluation.make_read_canaries(root, None, pools=pools, run=RUN, evidence=EVIDENCE, panel=ReadPanel())
    assert made["skipped"] == {"livemath": 0, "officeqa": 1, "spreadsheetbench": 1}
    assert evaluation.canary(oq[0]) not in made["canaries"] and evaluation.canary(sb[0]) not in made["canaries"]
    # otherwise unchanged: the registered seeded order without the skipped texts (still five per bench)
    kept = {bench: [t for t in texts if t not in (oq[0], sb[0])] for bench, texts in READ_TEXTS.items()}
    assert made["canaries"] == evaluation.select_canaries(kept)[0]
    assert made["counts"] == {bench: evaluation.CANARIES_PER_BENCH for bench in READ_BENCHES}
    assert all(found in made["canaries"] for found in unfiltered["canaries"]
               if found not in (evaluation.canary(oq[0]), evaluation.canary(sb[0])))
    assert evaluation.canary(oq[1]) in made["canaries"] and evaluation.canary(lm[0]) in made["canaries"]
    assert evaluation.training_duplicates(READ_TEXTS, {"officeqa": [quoted]}) == {
        "livemath": frozenset(), "officeqa": frozenset({oq[0]}), "spreadsheetbench": frozenset()}
    without([root / evaluation.READ_CANARIES], [oq[0], sb[0], quoted])  # counts only, never a text
    # a bench whose every test text is on the training side has no canary: refused, nothing written
    other = tmp_path / "other"
    write_json(other / "shared" / "consent.json", consent_value())
    s0_canaries(other)
    every = pool_pins(tmp_path / "every", {**TRAINING_TEXTS, "officeqa": READ_TEXTS["officeqa"]})
    with pytest.raises(ValueError, match="absent from the training side"):
        evaluation.make_read_canaries(other, None, pools=every, run=RUN, evidence=EVIDENCE, panel=ReadPanel())
    assert not (other / evaluation.READ_CANARIES).exists()


def test_training_pools_that_differ_from_their_pins_are_refused_before_any_test_set_is_opened(tmp_path):
    root = tmp_path / "run-root"
    write_json(root / "shared" / "consent.json", consent_value())
    s0_canaries(root)
    pools, panel = pool_pins(tmp_path / "pools"), ReadPanel()
    changed = safe_path(pools["officeqa"]["path"])
    changed.write_text(changed.read_text(encoding="utf-8").replace("1900", "1901"), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from its pin"):
        evaluation.make_read_canaries(root, None, pools=pools, run=RUN, evidence=EVIDENCE, panel=panel)
    for pins in (None, {}, {"officeqa": pools["officeqa"]}, {**pools, "officeqa": {"path": str(changed)}}):
        with pytest.raises(ValueError, match="data.pools"):  # no pins, or not those of the pilot's pools
            evaluation.make_read_canaries(root, None, pools=pins, run=RUN, evidence=EVIDENCE, panel=panel)
    assert panel.seen == [] and not (root / evaluation.READ_CANARIES).exists()


def test_a_read_unit_makes_the_read_canaries_before_its_attempt_and_reads_with_all_of_them(tmp_path, monkeypatch):
    from tests.test_execskill_manifest import NO_CALLS, FakeDockerCLI, pilot

    m = pilot(tmp_path, monkeypatch)
    root = safe_path(m["root"])
    write_json(root / "shared" / "consent.json", consent_value())
    s0_canaries(root)
    Budget(budgets.ledger_root(root, "D")).declare(budgets.chain_caps("D"))  # as chain.run declares it
    final = package.empty(step="D/s2-officeqa/t1", evidence=m["evidence"])
    package.save(root / "D", final)
    # PR-C31-3 (1a): the manifest's data.pools are the training side; their texts are also offered as test texts
    pins = m["data"]["pools"]
    trained = {bench: [item["public"][evaluation.READ_CANARY_SOURCES[bench]]
                       for item in json.loads(safe_path(pins[bench]["path"]).read_text(encoding="utf-8"))]
               for bench in ("officeqa", "spreadsheetbench")}
    offered = {**READ_TEXTS, **{bench: READ_TEXTS[bench] + trained[bench] for bench in trained}}
    duplicates = [text for texts in trained.values() for text in texts if len(text) >= evaluation.MIN_CANARY_CHARS]
    assert any(evaluation.canary(text) in evaluation.select_canaries(offered)[0] for text in duplicates)
    seen, panel = [], ReadPanel(offered)

    def evaluate(unit_root, **given):  # the read unit itself is T-EVAL's; here only what it is handed, and when
        seen.append((unit_root, (root / evaluation.READ_CANARIES).exists(), given["canaries"]))

    monkeypatch.setattr(evaluation, "evaluate", evaluate)
    specs = {}
    for bench in ("officeqa", "livemath"):
        specs[bench] = tmp_path / ("read-%s.json" % bench)
        write_json(specs[bench], {"chain": "D", "bench": bench, "package_sha256": final.sha256,
                                  "unit_root": str(root / "D" / "test" / bench)})
    write_json(root / "D" / "test" / "livemath" / "unit.json", {"status": "complete"})  # a finished unit: no access
    assert evaluation.run_unit_spec(m, spec=specs["livemath"], docker=FakeDockerCLI(), transport=NO_CALLS,
                                    panel=panel) == chain.EXIT_COMPLETE
    assert panel.seen == [] and not (root / evaluation.READ_CANARIES).exists() and seen == []
    assert evaluation.run_unit_spec(m, spec=specs["officeqa"], docker=FakeDockerCLI(), transport=NO_CALLS,
                                    panel=panel) == chain.EXIT_COMPLETE
    assert panel.seen == [(bench, evaluation.READ_CANARY_UNIT) for bench in READ_BENCHES]
    merged = evaluation.load_canaries(root, read=True)
    assert seen == [(root / "D" / "test" / "officeqa", True, merged)] and len(merged) == 25
    made = verified(read_json(root / evaluation.READ_CANARIES), "test-read-canaries")
    assert made["training_pools"] == {"livemath": None, "officeqa": pins["officeqa"]["sha256"],
                                      "spreadsheetbench": pins["spreadsheetbench"]["sha256"]}
    assert made["skipped"] == {"livemath": 0, **{bench: len({t for t in trained[bench] if t in duplicates})
                                                 for bench in trained}}
    assert not any(evaluation.canary(text) in made["canaries"] for text in duplicates)


# ------------------------------------------------------------------------------------------ the run-root scan
def test_the_root_scan_reads_decoded_json_nested_documents_workbook_members_and_raw_text(tmp_path):
    quoted = 'A fixture question with "quotes" and a backslash \\ inside?'
    accented = "Fixture theorem: which option gives π ≤ x for every x?"
    marked = "Fill the fixture column with A & B, then <round> it."
    canaries = [evaluation.canary(text) for text in (quoted, accented, marked)]
    tree = tmp_path / "root"
    write_json(tree / "a" / "escaped.json", {"field": quoted})  # escaped quotes and backslash
    write_json(tree / "a" / "nested.json", {"user": json.dumps({"q": accented}), "n": 1})  # a stored request
    write_json(tree / "a" / "deep" / "store.json", {"t": [marked]})
    (tree / "b").mkdir()
    (tree / "b" / "events.jsonl").write_text("not json: %s\n%s\n" % (marked, json.dumps({"x": quoted})),
                                             encoding="utf-8")
    (tree / "b" / "child.log").write_bytes(("warning: " + accented + "\n").encode("utf-8") + b"\xff\xfe")
    (tree / "c").mkdir()
    (tree / "c" / "input.xlsx").write_bytes(workbook(marked))
    write_json(tree / "c" / "near.json", {"field": quoted.replace("?", "!")})  # one character off
    (tree / "c" / "blob.bin").write_bytes(bytes(range(256)) * 4)
    files, hits = evaluation.root_scan(tree, canaries)
    assert files == 8 and hits == [
        {"where": "a", "path": "a/escaped.json", "canary": 0}, {"where": "a", "path": "a/nested.json", "canary": 1},
        {"where": "a/deep", "path": "a/deep/store.json", "canary": 2},
        {"where": "b", "path": "b/child.log", "canary": 1}, {"where": "b", "path": "b/events.jsonl", "canary": 0},
        {"where": "b", "path": "b/events.jsonl", "canary": 2}, {"where": "c", "path": "c/input.xlsx", "canary": 2}]
    assert all(set(hit) == {"where", "path", "canary"} for hit in hits)
    assert evaluation.root_scan(tree, []) == (8, [])
    os.symlink(tree / "c" / "near.json", tree / "c" / "link.json")  # a link would go unread: refused
    with pytest.raises(ValueError, match="link"):
        evaluation.root_scan(tree, canaries)


def test_the_root_scan_gives_the_one_process_result_with_any_number_of_processes(tmp_path, monkeypatch):
    texts = [READ_TEXTS["officeqa"][0], READ_TEXTS["livemath"][1], READ_TEXTS["spreadsheetbench"][2],
             S0_TEXTS["searchqa"][3]]
    canaries = [evaluation.canary(text) for text in texts]
    tree, page = tmp_path / "root", "A long training context page of the fixture. " * 12  # cached: >= 256 chars
    for n in range(40):
        body = {"context": page, "n": n, **({"user": json.dumps({"question": texts[n % 4]})} if n % 7 == 0 else {})}
        write_json(tree / "GD"[n % 2] / ("s%d-officeqa" % (n % 3)) / "run" / "attempt-1" / ("c%02d.json" % n), body)
    (tree / "shared" / "research").mkdir(parents=True)
    (tree / "shared" / "research" / "page.txt").write_text("quoting %s\n%s" % (texts[1], page), encoding="utf-8")
    (tree / "G" / "input.xlsx").write_bytes(workbook(texts[2]))
    one = evaluation.root_scan(tree, canaries)
    assert one[0] == 42 and len({hit["path"] for hit in one[1]}) == 8
    made = []

    class Recording(ProcessPoolExecutor):
        def __init__(self, **options):
            made.append((options["max_workers"], options["mp_context"].get_start_method()))
            super().__init__(**options)

    monkeypatch.setattr(evaluation, "ProcessPoolExecutor", Recording)
    assert evaluation.root_scan(tree, canaries, workers=3) == one and made == []  # a small root: this process
    monkeypatch.setattr(evaluation, "ROOT_SCAN_POOL_BYTES", 0)
    for workers in (2, 3, 5):  # registrar decision PR-C31-3 (3): the same files, hits and order
        assert evaluation.root_scan(tree, canaries, workers=workers) == one
    assert made == [(2, "spawn"), (3, "spawn"), (5, "spawn")]
    assert evaluation.root_scan(tree, [], workers=3) == (42, []) and len(made) == 3
    for count in (1, 2, 5, 40):  # contiguous runs that cover every file once
        shares = evaluation._shares([5, 1, 1, 9, 2, 2, 2, 30, 1], count)
        assert [index for start, end in shares for index in range(start, end)] == list(range(9))


def test_the_scan_leaves_cpus_to_a_running_chain():
    assert [evaluation.scan_workers(cpus) for cpus in (1, 2, 3, 4, 6, 7, 8, 64)] == [1, 1, 1, 2, 4, 5, 5, 5]
    assert 1 <= evaluation.scan_workers() <= evaluation.ROOT_SCAN_WORKERS


def plant_in_a_unit_file(root, text):
    """A stored request in a step unit's trajectory: a JSON document inside a JSON string."""
    path = root / CHAIN / "s2-officeqa" / "run" / "attempt-1" / "trajectories" / "D-s2-officeqa-run-c7.json"
    write_json(path, {"calls": [{"purpose": "solve", "user": json.dumps({"question": text, "context": "p. 3"})}]})
    return path


def plant_in_the_research_store(root, text):
    path = root / "shared" / "research" / CHAIN / "sources" / ("a" * 64 + ".json")
    write_json(path, {"title": "Public finance", "text": "An archived page quoting: %s (end)" % text})
    return path


def plant_in_a_generated_set(root, text):
    """A generated SpreadsheetBench input workbook of a generate unit."""
    path = root / CHAIN / "s1-spreadsheetbench" / "generate" / "attempt-1" / "g_self" / "g-1" / "input.xlsx"
    path.parent.mkdir(parents=True)
    path.write_bytes(workbook(text))
    return path


PLANTS = {"unit_file": (plant_in_a_unit_file, "livemath", "D/s2-officeqa"),
          "research_store": (plant_in_the_research_store, "officeqa", "shared/research"),
          "generated_set": (plant_in_a_generated_set, "spreadsheetbench", "D/s1-spreadsheetbench")}


@pytest.mark.parametrize("place", sorted(PLANTS))
def test_a_canary_planted_in_the_run_root_pauses_the_unseal_until_the_owner_decides(tmp_path, capsys, place):
    plant, bench, where = PLANTS[place]
    root, unit_root, _ = read(tmp_path, Solver(), [])
    made = register_canaries(root)
    ended(root)
    text = chosen(bench, made)[0]
    planted = plant(root, text)
    index = evaluation.load_canaries(root, read=True).index(evaluation.canary(text))
    with pytest.raises(Pause) as stop:
        unseal(root, unit_root)
    assert (stop.value.kind, stop.value.cell) == ("canary_hit", "D/root-scan")
    attempt = root / CHAIN / "root-scan" / "attempt-1"
    scan = verified(read_json(attempt / "scan.json"), "root-canary-scan")
    hit = {"where": where, "path": str(planted.relative_to(root)), "canary": index}
    assert (scan["hits"], scan["files_hit"], scan["shown"], scan["canaries"]) == (1, 1, [hit], 25)
    assert scan["by_bench"] == {bench: 1} and scan["by_where"] == {where: 1}
    status = verified(read_json(attempt / "status.json"), "unit-status")
    assert (status["status"], status["kind"], status["scan_sha256"]) == ("paused", "canary_hit", scan[RECORD_HASH])
    assert not (root / CHAIN / "unsealed.json").exists()  # no score was read, no marker written
    without([attempt / "scan.json", attempt / "status.json"], [text])
    # paused for the owner: nothing is scanned or unsealed before the owner's decision is recorded
    with pytest.raises(Pause) as stop:
        unseal(root, unit_root)
    assert (stop.value.kind, stop.value.reason) == ("awaiting_owner_decision", "attempt-1")
    # the decision lets a new scan run; the planted text is still there, so it pauses again
    write_json(attempt / "recovery.json", {"by": "owner", "date": "2026-10-22", "decision": "scan again"})
    with pytest.raises(Pause, match="canary_hit"):
        unseal(root, unit_root)
    assert verified(read_json(root / CHAIN / "root-scan" / "attempt-2" / "scan.json"), "root-canary-scan")["hits"] == 1
    planted.unlink()
    write_json(root / CHAIN / "root-scan" / "attempt-2" / "recovery.json",
               {"by": "owner", "date": "2026-10-22", "decision": "the planted file is gone"})
    opened = unseal(root, unit_root)
    assert opened["units"]["officeqa"]
    assert verified(read_json(root / CHAIN / "unsealed.json"), "unseal")["canary_scan"]["attempt"] == "attempt-3"
    out, err = capsys.readouterr()
    assert text not in out + err


def test_a_clean_run_root_passes_with_every_file_read_and_the_marker_names_the_scan(tmp_path, capsys):
    root, unit_root, _ = read(tmp_path, Solver(), [])
    register_canaries(root)
    ended(root)
    before = [path for path in root.rglob("*") if path.is_file()]
    opened = unseal(root, unit_root)
    scan = verified(read_json(root / CHAIN / "root-scan" / "attempt-1" / "scan.json"), "root-canary-scan")
    assert scan["files_scanned"] == len(before) + 1  # every file of the root, and the scan's own lock
    assert (scan["hits"], scan["files_hit"], scan["shown"], scan["by_where"], scan["by_bench"]) == (0, 0, [], {}, {})
    assert scan["canaries_sha256"] == digest(evaluation.load_canaries(root, read=True)) and scan["chain"] == CHAIN
    assert scan["hits_sha256"] == digest([])
    marker = verified(read_json(root / CHAIN / "unsealed.json"), "unseal")
    assert marker["canary_scan"] == {"attempt": "attempt-1", "record_sha256": scan[RECORD_HASH], "release": None}
    assert unseal(root, unit_root) == opened  # a later unseal reads the marker's clean scan: no new scan
    assert [path.name for path in evaluation.attempts(root / CHAIN / "root-scan")] == ["attempt-1"]
    assert not (root / CHAIN / "root-scan" / "attempt-1" / "status.json").exists()
    assert capsys.readouterr() == ("", "")


def test_the_scan_record_is_the_same_whatever_the_number_of_processes(tmp_path, monkeypatch):
    found, made = {}, []

    class Recording(ProcessPoolExecutor):
        def __init__(self, **options):
            made.append(options["max_workers"])
            super().__init__(**options)

    monkeypatch.setattr(evaluation, "ProcessPoolExecutor", Recording)
    monkeypatch.setattr(evaluation, "ROOT_SCAN_POOL_BYTES", 0)
    for workers in (1, 3):
        monkeypatch.setattr(evaluation, "scan_workers", lambda workers=workers: workers)
        root, unit_root, _ = read(tmp_path / str(workers), Solver(), [])
        canaries = register_canaries(root)
        ended(root)
        plant_in_a_generated_set(root, chosen("spreadsheetbench", canaries)[0])
        plant_in_the_research_store(root, chosen("officeqa", canaries)[1])
        with pytest.raises(Pause, match="canary_hit"):
            unseal(root, unit_root)
        found[workers] = verified(read_json(root / CHAIN / "root-scan" / "attempt-1" / "scan.json"),
                                  "root-canary-scan")
    assert made == [3] and found[1]["hits"] == 2 and found[1]["files_scanned"] > 30
    assert found[1] == found[3]  # the sealed record, its hash included


def paused_by_a_planted_canary(tmp_path):
    """Chain D has ended with an OfficeQA canary planted in the research store: the first unseal paused (attempt-1)."""
    root, unit_root, _ = read(tmp_path, Solver(), [])
    canaries = register_canaries(root)
    ended(root)
    text = chosen("officeqa", canaries)[0]
    plant_in_the_research_store(root, text)
    with pytest.raises(Pause, match="canary_hit"):
        unseal(root, unit_root)
    scan = verified(read_json(root / CHAIN / "root-scan" / "attempt-1" / "scan.json"), "root-canary-scan")
    return root, unit_root, canaries, text, scan


def decide(attempt, decision, by="owner"):
    """``run_execskill.py recover``'s recovery.json in ``attempt``."""
    value = {"by": by, "date": "2026-10-22", "decision": decision}
    write_json(attempt / "recovery.json", value)
    return value


def paused_again(root, unit_root, number, message):
    """The next unseal pauses in attempt-<number>: the owner's decision in the attempt before released nothing."""
    with pytest.raises(Pause, match="canary_hit"):
        unseal(root, unit_root)
    attempt = root / CHAIN / "root-scan" / ("attempt-%d" % number)
    status = verified(read_json(attempt / "status.json"), "unit-status")
    assert status["release"]["attempt"] == "attempt-%d" % (number - 1) and message in status["release"]["refused"]
    return verified(read_json(attempt / "scan.json"), "root-canary-scan")


def test_the_owner_releases_exactly_the_paused_scan_and_the_marker_names_the_release(tmp_path, capsys):
    root, unit_root, _, text, first = paused_by_a_planted_canary(tmp_path)
    scans = root / CHAIN / "root-scan"
    # never automatic: a release that is not the owner's recorded decision is none; the scan awaits the owner
    decide(scans / "attempt-1", "release " + first[RECORD_HASH], by="operator")
    with pytest.raises(Pause) as stop:
        unseal(root, unit_root)
    assert (stop.value.kind, stop.value.reason) == ("awaiting_owner_decision", "attempt-1")
    (scans / "attempt-1" / "recovery.json").unlink()
    # a release that names another record (none; an earlier scan) or takes another form releases nothing: the next
    # scan pauses again in a new attempt, where the owner decides anew (a recovery file is written once)
    decide(scans / "attempt-1", "release " + "0" * 64)
    second = paused_again(root, unit_root, 2, "names another scan")
    decide(scans / "attempt-2", "release " + first[RECORD_HASH])
    third = paused_again(root, unit_root, 3, "names another scan")
    decide(scans / "attempt-3", "release the research hit")
    fourth = paused_again(root, unit_root, 4, "exactly")
    assert first["hits_sha256"] == second["hits_sha256"] == third["hits_sha256"] == fourth["hits_sha256"]
    assert not (root / CHAIN / "unsealed.json").exists()
    released = decide(scans / "attempt-4", "release " + fourth[RECORD_HASH])
    opened = unseal(root, unit_root)
    assert opened["units"]["officeqa"]
    fifth = verified(read_json(scans / "attempt-5" / "scan.json"), "root-canary-scan")
    assert (fifth["hits"], fifth["hits_sha256"], fifth["shown"]) == (1, fourth["hits_sha256"], fourth["shown"])
    assert not (scans / "attempt-5" / "status.json").exists()
    marker = verified(read_json(root / CHAIN / "unsealed.json"), "unseal")
    assert marker["canary_scan"] == {"attempt": "attempt-5", "record_sha256": fifth[RECORD_HASH], "release": {
        "attempt": "attempt-4", "scan_sha256": fourth[RECORD_HASH], "recovery_sha256": digest(released)}}
    assert unseal(root, unit_root) == opened  # the marker's released scan, verified again: no new scan
    assert len(evaluation.attempts(scans)) == 5
    # another chain's scan is its own: chain G's first unseal scans the root and pauses on the same hit
    write_json(root / "G" / "chain-complete.json", record("chain-complete", EVIDENCE, {"chain": "G"}))
    with pytest.raises(Pause) as stop:
        evaluation.unseal(root, root / "G", "G", [], run=RUN, evidence=EVIDENCE, clock=lambda: "2026-10-22T12:00:00Z")
    assert (stop.value.kind, stop.value.cell) == ("canary_hit", "G/root-scan")
    # the release is part of what the marker seals: a changed recovery file fails every later unseal
    (scans / "attempt-4" / "recovery.json").unlink()
    write_json(scans / "attempt-4" / "recovery.json", {**released, "date": "2026-10-23"})
    with pytest.raises(ValueError, match="owner-released"):
        unseal(root, unit_root)
    out, err = capsys.readouterr()
    assert text not in out + err


def test_a_release_covers_exactly_the_released_hits_and_any_other_scan_pauses(tmp_path):
    root, unit_root, canaries, _, first = paused_by_a_planted_canary(tmp_path)
    scans = root / CHAIN / "root-scan"
    decide(scans / "attempt-1", "release " + first[RECORD_HASH])
    more = plant_in_a_unit_file(root, chosen("livemath", canaries)[0])  # a new hit after the owner's release
    with pytest.raises(Pause) as stop:
        unseal(root, unit_root)
    assert (stop.value.kind, stop.value.reason) == ("canary_hit", "2 hits")
    second = verified(read_json(scans / "attempt-2" / "scan.json"), "root-canary-scan")
    status = verified(read_json(scans / "attempt-2" / "status.json"), "unit-status")
    assert (status["kind"], status["scan_sha256"], status["release"]["attempt"]) == (
        "canary_hit", second[RECORD_HASH], "attempt-1") and "release in attempt-1" in status["reason"]
    with pytest.raises(Pause, match="awaiting_owner_decision"):
        unseal(root, unit_root)
    # fewer hits are other hits: the owner releases the two, one file goes, and the next scan pauses again --
    # although it finds attempt-1's hits, only the last paused scan's release is in force
    decide(scans / "attempt-2", "release " + second[RECORD_HASH])
    more.unlink()
    with pytest.raises(Pause) as stop:
        unseal(root, unit_root)
    third = verified(read_json(scans / "attempt-3" / "scan.json"), "root-canary-scan")
    assert stop.value.reason == "1 hits" and third["hits_sha256"] == first["hits_sha256"]
    assert not (root / CHAIN / "unsealed.json").exists()
    # a clean scan needs no release: the marker names none
    for path in (root / "shared" / "research").rglob("*.json"):
        path.unlink()
    decide(scans / "attempt-3", "release " + third[RECORD_HASH])
    unseal(root, unit_root)
    marker = verified(read_json(root / CHAIN / "unsealed.json"), "unseal")["canary_scan"]
    assert (marker["attempt"], marker["release"]) == ("attempt-4", None)


def test_release_check_accepts_only_the_owners_release_of_the_scan_paused_in_that_attempt(tmp_path):
    root, unit_root, _, _, first = paused_by_a_planted_canary(tmp_path)
    paused, sha = root / CHAIN / "root-scan" / "attempt-1", first[RECORD_HASH]
    assert evaluation.release_check(paused, "release " + sha) == sha
    for decision in ("scan again after removing the file", "Release " + sha, "released: " + sha):
        assert evaluation.release_check(paused, decision) is None  # free text: never a release
    for decision in ("release " + "f" * 64, "release " + sha.upper(), " release " + sha, "release " + sha + " now",
                     "release it"):  # the reserved word in another form, or naming another record: refused
        with pytest.raises(ValueError, match="release"):
            evaluation.release_check(paused, decision)
    with pytest.raises(ValueError, match="paused run-root canary scan only"):  # a unit's attempt takes no release
        evaluation.release_check(unit_root / "attempt-1", "release " + sha)
    assert evaluation.release_check(unit_root / "attempt-1", "redo after a kill") is None
    clean = root / CHAIN / "root-scan" / "attempt-7"  # an attempt without a paused scan has nothing to release
    clean.mkdir()
    with pytest.raises(ValueError, match="names the scan paused"):
        evaluation.release_check(clean, "release " + sha)


def test_no_unseal_reads_a_score_before_the_read_canaries_exist(tmp_path):
    root, unit_root, _ = read(tmp_path, Solver(), [])
    s0_canaries(root)  # the test read's record was never made
    ended(root)
    with pytest.raises(ValueError, match="not made"):
        unseal(root, unit_root)
    assert not (root / CHAIN / "unsealed.json").exists()
