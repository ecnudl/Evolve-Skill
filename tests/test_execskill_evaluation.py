"""T-EVAL-1..5 (implementation plan §8.1, §2.10; registration §8.1; Codex F16, F17): the consent key set, one
multi-arm read unit with structural-zero sharing and twins, the hash-only persistence with the transient store deleted,
the canary scan before sealing, and the unseal order. Offline and deterministic: a stateless fake solver behind the
frozen Endpoint, FakeSandbox procedures and a synthetic test panel (fixture items, never a test pool). An unseal needs
the run root's two canary records (registrar decision C3-1 (b)): ``register_canaries`` makes them from synthetic texts;
tests/test_execskill_canaries.py tests them and the run-root scan. The read record's selection skips test texts found
verbatim on the training side (registrar decision PR-C31-3 (1a)): ``pool_pins`` pins synthetic training pools outside
the run root."""
from __future__ import annotations

import hashlib
import itertools
import json
from contextlib import contextmanager

import pytest

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import evaluation
from skillopt.execskill.cells import Arm, Context, Pause
from skillopt.execskill.package import empty, with_
from skillopt.execskill.protocol import BENCHES, CANARIES, CONSENT_FIELDS, NOTES_KEY, TEST_ARMS, record, verified
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import FakeSandbox, procedure
from tests.fixtures.execskill.items import officeqa_items

EVIDENCE = "engineering_fixture"
BENCH, CHAIN, RUN = "officeqa", "D", "fixture-run"
CARD = "Read the public table before answering."
RAW = "RAW-REPLY-TEXT"
ITEMS = officeqa_items(12)
USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def page(view):
    return int(view["context"].split("page ", 1)[1].split("\n", 1)[0])


N = procedure("p-officeqa-1-1", ("applies", "before_call"), header="Row helper notes.", evidence=EVIDENCE)
M = procedure("p-officeqa-1-2", ("applies", "before_call"), header="Column helper notes.", evidence=EVIDENCE)
HOOKS = {N.id: {"applies": lambda view: page(view) % 3 != 0,
                "before_call": lambda view, state: {"facts": ["Use the row of the named year."]}},
         M.id: {"applies": lambda view: page(view) % 2 == 0,
                "before_call": lambda view, state: {"facts": ["Columns are fiscal years."]}}}
CARD_PACKAGE = empty(step="pilot/s2-officeqa/t1", evidence=EVIDENCE)
FINAL = with_(CARD_PACKAGE, step="pilot/s2-officeqa/t2", add=[N, M])
ZERO = {item["task_id"] for item in ITEMS if not HOOKS[N.id]["applies"](item["public"])
        and not HOOKS[M.id]["applies"](item["public"])}


def consent_value(**changes):
    value = {"test_evaluation": True, "sheet_test_qualification": False, "multi_arm_arms": list(TEST_ARMS),
             "by": "owner", "date": "2026-10-22", "note": "Read the pilot's five test sets once."}
    value.update(changes)
    return value


# registrar decision C3-1 (b): synthetic stand-ins for the five test sets' canary texts (never a test pool)
S0_TEXTS = {"searchqa": ["Fixture SearchQA question %d about a river delta?" % n for n in range(6)],
            "alfworld": ["valid_unseen/fixture-task-%d/trial_1/game.tw-pddl" % n for n in range(6)]}
READ_TEXTS = {
    "officeqa": ["What were the fixture customs receipts in fiscal year %d?" % (1930 + n) for n in range(8)],
    "livemath": ["Fixture theorem %d: which option gives \u03c0 \u2264 x for every upper bound x?" % n
                 for n in range(7)],
    "spreadsheetbench": ['In fixture sheet %d, fill column "C" with the running total & round it.' % n
                         for n in range(6)] + ["too short"]}


# the training side the read record's selection checks (registrar decision PR-C31-3 (1a)): synthetic pool items of
# the pilot's two benches whose public fields hold none of READ_TEXTS
TRAINING_TEXTS = {
    "officeqa": ["What were the fixture training receipts in fiscal year %d?" % (1900 + n) for n in range(4)],
    "spreadsheetbench": ['In fixture training sheet %d, fill column "D" with the mean of row 2.' % n for n in range(4)]}


def pool_pins(directory, texts=None, *, others=None):
    """The manifest's ``data.pools`` pins of synthetic training pools (``{bench: {"path", "sha256"}}``): one pool item
    per text in the bench's canary field (``evaluation.READ_CANARY_SOURCES``); ``others``: {bench: [{public field:
    text}]} items with other public fields."""
    pins = {}
    for bench, values in sorted((texts or TRAINING_TEXTS).items()):
        field = evaluation.READ_CANARY_SOURCES[bench]
        publics = [{field: text} for text in values] + list((others or {}).get(bench, []))
        items = [{"task_id": "%s-train-%d" % (bench, n), "public": public, "private": {}}
                 for n, public in enumerate(publics)]
        path = directory / ("%s.json" % bench)
        write_json(path, items)
        pins[bench] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return pins


class ReadPanel:
    """The three test sets the read's canaries come from (``evaluation.READ_CANARY_SOURCES``), synthetic; every
    access is recorded."""

    def __init__(self, texts=None):
        self.texts, self.seen = texts or READ_TEXTS, []

    def __call__(self, pinned, bench, *, access):
        self.seen.append((bench, access.unit))
        field = evaluation.READ_CANARY_SOURCES[bench]
        tasks = [{"task_id": "%s-%d" % (bench, n), "public": {field: text}, "private": {}}
                 for n, text in enumerate(self.texts[bench])]
        return tasks, {"panel_hash": digest(tasks)}


def s0_canaries(root):
    """The S0 exclusion unit's sealed canary record as ``make-manifest`` writes it into the run root."""
    found, counts = evaluation.select_canaries(S0_TEXTS)
    value = record("test-canaries", "smoke", {
        "canaries": found, "counts": counts, "per_bench": evaluation.CANARIES_PER_BENCH,
        "seed_tag": evaluation.CANARY_TAG, "sources": {"alfworld": "the game file path inside the release",
                                                       "searchqa": "the public question"},
        "unit": "smoke/s0/test-exclusion", "consent_sha256": "0" * 64})
    write_json(root / CANARIES, value)
    return value


def register_canaries(root, panel=None, pools=None):
    """The run root's two canary records: S0's and the test read's, made under the consent ``read`` wrote, against the
    training pools ``pools`` pins (default: ``pool_pins`` beside the run root)."""
    s0_canaries(root)
    return evaluation.make_read_canaries(root, None, pools=pools or pool_pins(root.parent / "pools"), run=RUN,
                                         evidence=EVIDENCE, panel=panel or ReadPanel())


class Solver:
    """Right when the request carries procedure notes, else "0"; every reply carries a raw marker text."""

    def __init__(self):
        self.answers = {(item["public"]["question"], item["public"]["context"]): item["private"]["answer"]
                        for item in ITEMS}
        self.calls = 0

    def call(self, system, user):
        self.calls += 1
        view = json.loads(user)
        answer = self.answers[(view["question"], view["context"])] if NOTES_KEY in view else "0"
        return {"ok": True, "response": "%s <answer>%s</answer>" % (RAW, answer), "finish_reason": "stop",
                "error_type": None, "usage": dict(USAGE), "attempts": [{"status": 200}]}


def panel(pinned, bench, *, access):
    assert bench == BENCH and access.unit == "%s/test/%s" % (CHAIN, BENCH)
    tasks = [{"task_id": i["task_id"], "public": i["public"], "private": i["private"]} for i in ITEMS]
    return tasks, {"panel_hash": digest(tasks), "excluded_without_pages": 0, "source_files": None}


@contextmanager
def route_workers(package, item):
    worker = FakeSandbox(HOOKS).start(package, kind="cell")
    try:
        yield worker
    finally:
        worker.close()


def arms():
    def placebo(cell, task):
        return Arm("placebo_y", FINAL, placebo={"procedures": {
            N.id: {"before_call": {"facts": ["A donor's row note."]}},
            M.id: {"before_call": {"facts": ["A donor's column note."]}}}, "seed": "seed:" + cell["id"]})

    return {"F": Arm("candidate", FINAL), "C": Arm("card", CARD_PACKAGE), "P_F": placebo,
            "T_F": Arm("text", FINAL, text={N.id: "Points at the row of the year.", M.id: "Names the columns."})}


def read(tmp_path, solver, canaries):
    root = tmp_path / "run-root"
    shared = root / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    if not (shared / "consent.json").exists():
        write_json(shared / "consent.json", consent_value())
    endpoint = Endpoint(solver, model="deepseek-v4.1-flash-1017", max_tokens=100,
                        slots=Slots(tmp_path / "slots", "deepseek", 2), sleep=lambda _: None)
    unit_root = root / CHAIN / "test" / BENCH
    ticks = itertools.count()
    context = Context(attempt=unit_root / "attempt-1", endpoint=endpoint, runtime=RUNTIME,
                      cards={b: CARD for b in BENCHES}, native=Slots(tmp_path / "slots", "spreadsheet-native", 1),
                      episodes=Slots(tmp_path / "slots", "alfworld-episode", 1),
                      worker=lambda bench: FakeSandbox(HOOKS), evidence=EVIDENCE, clock=lambda: float(next(ticks)))
    found = evaluation.evaluate(unit_root, run=RUN, shared=shared, pinned=None, chain=CHAIN, bench=BENCH, arms=arms(),
                                context=context, workers=2, route_workers=route_workers, canaries=canaries,
                                panel=panel)
    return root, unit_root, found


# ---------------------------------------------------------------------------------------------------- T-EVAL-1
def test_eval1_the_consent_key_set_is_exact(tmp_path):
    shared = tmp_path / "shared"
    with pytest.raises(ValueError, match="consent"):
        evaluation.consent(shared)
    assert CONSENT_FIELDS == {"test_evaluation", "sheet_test_qualification", "multi_arm_arms", "by", "date", "note"}
    for n, bad in enumerate([consent_value(extra=1),
                             {k: v for k, v in consent_value().items() if k != "multi_arm_arms"},
                             consent_value(multi_arm_arms=["F", "C"]), consent_value(test_evaluation="yes"),
                             consent_value(by="agent"), consent_value(note=" ")]):
        write_json(tmp_path / str(n) / "consent.json", bad)
        with pytest.raises(ValueError, match="consent"):
            evaluation.consent(tmp_path / str(n))
    write_json(shared / "consent.json", consent_value())
    assert evaluation.consent(shared)["multi_arm_arms"] == list(TEST_ARMS)


# ------------------------------------------------------------------------------------------ T-EVAL-2, -4, -5
def test_eval2_a_multi_arm_unit_shares_structural_zeros_and_seals_hashes_only(tmp_path):
    solver = Solver()
    texts = [item["public"]["question"] for item in ITEMS] + [item["public"]["context"][:60] for item in ITEMS]
    canaries = [evaluation.canary(text) for text in texts]
    root, unit_root, found = read(tmp_path, solver, canaries)
    assert verified(found, "evaluation")["status"] == "complete" and found["structural_zero"] == len(ZERO) == 2
    attempt = unit_root / found["attempt"]
    cells = {c["cell"]["id"]: c for c in (verified(read_json(p), "evaluation-cell")
                                          for p in (attempt / "cells").glob("*.json"))}
    by_key = {(c["cell"]["arm"], c["cell"]["task_id"]): c for c in cells.values()}
    # every item has its C cell; F, P_F and T_F ran where F enables a procedure and share C on the structural zeros
    twins = [c for c in cells.values() if c["cell"]["arm"].startswith("withhold:")]
    ran = [c for c in cells.values() if c["shared_with"] is None]
    assert len(ran) == solver.calls == 12 + 3 * 10 + len(twins) and found["twins"] == len(twins) == 7
    for item in (i["task_id"] for i in ITEMS):
        source = by_key[("C", item)]
        for arm in ("F", "P_F", "T_F"):
            cell = by_key[(arm, item)]
            if item in ZERO:
                assert cell["shared_with"] == source["cell"]["id"] and cell["calls"] == [] and cell["enabled"] == []
            else:
                assert cell["shared_with"] is None and cell["enabled"] and len(cell["calls"]) == 1
    per_item = {}
    for twin in twins:
        per_item.setdefault(twin["cell"]["task_id"], []).append(twin["cell"]["arm"])
        assert twin["withheld"] == [twin["cell"]["arm"].split(":", 1)[1]] and twin["cell"]["task_id"] not in ZERO
    assert max(len(v) for v in per_item.values()) <= 2
    assert {by_key[(a, i)]["arm_kind"] for a, i in by_key if a in ("F", "C", "P_F", "T_F")} == {
        "candidate", "card", "placebo_y", "text"}
    # Codex F16: no raw text outside the transient store, which is gone; its deletion manifest is recorded
    assert not (attempt / "transient").exists()
    for path in root.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            assert RAW not in text and "Fixture bulletin page" not in text and "Receipts by fiscal year" not in text
    deletion = verified(read_json(attempt / "transient-deleted.json"), "transient-deletion")
    assert deletion["files"] > 0 and found["transient_deleted_sha256"] == deletion["manifest_sha256"]
    sample = by_key[("F", sorted(set(i["task_id"] for i in ITEMS) - ZERO)[0])]
    assert set(sample["calls"][0]) == {"purpose", "request_sha256", "reply_sha256", "completion_tokens"}
    assert sample["calls"][0]["completion_tokens"] == USAGE["completion_tokens"]
    assert sample["judge"]["v2"] == "pass" and sample["final"]["token"] == "pass"
    # the canary scan ran over every artifact before sealing
    scan = verified(read_json(attempt / "canary_scan.json"), "canary-scan")
    assert scan["hits"] == 0 and scan["artifacts_scanned"] > len(cells) and scan["canaries"] == len(canaries)
    assert found["canary_scan_sha256"] == scan["record_sha256"]


def test_eval4_5_a_store_that_keeps_raw_replies_is_caught_by_the_canary_scan_before_sealing(tmp_path, monkeypatch):
    original = evaluation.sealed_cell

    def leaking(full):  # mutation (19): the sealed record keeps the raw reply
        value = original(full)
        value["raw"] = [s["receipt"]["response"] for s in full["sends"] if isinstance(s.get("receipt"), dict)]
        return value

    monkeypatch.setattr(evaluation, "sealed_cell", leaking)
    marker = "%s <answer>" % RAW  # a registered canary of the reply text
    with pytest.raises(Pause) as stop:
        read(tmp_path, Solver(), [evaluation.canary(marker + "0</answer>")])
    assert stop.value.kind == "canary_hit"
    unit_root = tmp_path / "run-root" / CHAIN / "test" / BENCH
    assert not (unit_root / "unit.json").exists()
    status = verified(read_json(unit_root / "attempt-1" / "status.json"), "unit-status")
    assert status["kind"] == "canary_hit" and status["hits"]
    assert not (unit_root / "attempt-1" / "canary_scan.json").exists()


def test_eval5_the_scan_reads_every_file_and_decoded_json_strings(tmp_path):
    text = 'A "quoted" test question about receipts?'
    found = evaluation.canary(text)
    assert set(found) == {"chars", "sha256_16"} and text not in json.dumps(found)
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "clean.txt").write_text("nothing here", encoding="utf-8")
    assert evaluation.canary_scan(tmp_path, [found]) == (1, [])
    write_json(tmp_path / "a" / "escaped.json", {"field": text})  # escaped quotes: only the decoded strings match
    files, hits = evaluation.canary_scan(tmp_path, [found])
    assert files == 2 and hits == [{"path": "a/escaped.json", "canary": 0}]
    with pytest.raises(ValueError):
        evaluation.canary("too short")


def test_eval_f_equal_c_is_never_read(tmp_path):
    with pytest.raises(ValueError, match="F = C"):
        evaluation.evaluate(tmp_path / "u", run=RUN, shared=tmp_path / "shared", pinned=None, chain=CHAIN,
                            bench=BENCH, arms={**arms(), "F": Arm("candidate", CARD_PACKAGE)}, context=None,
                            workers=1, route_workers=route_workers, canaries=[], panel=panel)


# ---------------------------------------------------------------------------------------------------- T-EVAL-3
def addendum(root, at):
    """The owner's formal-chain addendum document, sealed by ``seal_addendum`` at ``at``."""
    (root / "shared" / "formal-addendum.md").write_text("Formal chain: benches, slice sizes, caps.\n", encoding="utf-8")
    return evaluation.seal_addendum(root, evidence=EVIDENCE, clock=lambda: at)


def test_eval3_unseal_needs_the_chain_end_and_the_owner_continuation_and_labels_late_addenda(tmp_path):
    root, unit_root, found = read(tmp_path, Solver(), [])
    register_canaries(root)
    chain_root = root / CHAIN

    def unseal(clock="2026-10-22T12:00:00Z"):
        return evaluation.unseal(root, chain_root, CHAIN, [unit_root], run=RUN, evidence=EVIDENCE,
                                 clock=lambda: clock)

    with pytest.raises(ValueError, match="complete or terminated"):
        unseal()
    write_json(chain_root / "chain-complete.json", record("chain-complete", EVIDENCE, {"chain": CHAIN}))
    with pytest.raises(ValueError, match="continuation"):
        unseal()
    write_json(root / "shared" / "owner-continuation.json",
               {"by": "owner", "date": "2026-10-22", "decision": "continue", "note": "continue to the formal chain"})
    opened = unseal()  # continue, but no formal-chain addendum before the unseal
    assert opened["label"] == "interim_read_without_prior_addendum"
    assert opened["later_reads"] == "repeated_test_development"
    assert evaluation.read_label([chain_root]) == "repeated_test_development"
    addendum(root, "2026-10-22T13:00:00Z")
    assert unseal("2026-10-22T14:00:00Z")["later_reads"] == "repeated_test_development"  # the marker is written once
    # keyed by (arm, task_id, run): F shares C on the structural zeros
    table = opened["units"][BENCH]
    for item in ZERO:
        assert table[("F", item, 0)]["shared_with"] is not None and table[("F", item, 0)]["v2"] == table[
            ("C", item, 0)]["v2"]
    assert all(len(key) == 3 for key in table)


def test_eval3_an_addendum_hashed_before_the_unseal_makes_later_reads_confirmatory(tmp_path):
    root, unit_root, _ = read(tmp_path, Solver(), [])
    register_canaries(root)
    chain_root = root / CHAIN
    write_json(chain_root / "chain-terminated.json", record("chain-terminated", EVIDENCE, {"chain": CHAIN}))
    write_json(root / "shared" / "owner-continuation.json",
               {"by": "owner", "date": "2026-10-22", "decision": "continue", "note": "go on"})
    addendum(root, "2026-10-22T09:00:00Z")
    opened = evaluation.unseal(root, chain_root, CHAIN, [unit_root], run=RUN, evidence=EVIDENCE,
                               clock=lambda: "2026-10-22T10:00:00Z")
    assert (opened["label"], opened["later_reads"]) == ("interim_read_addendum_before_unseal", "confirmatory")
    assert evaluation.read_label([chain_root]) == "confirmatory"
    with pytest.raises(ValueError, match="another chain"):
        evaluation.unseal(root, chain_root, "G", [unit_root], run=RUN, evidence=EVIDENCE)


def test_continuation_check_reports_the_label_an_unseal_would_carry_and_reads_no_score(tmp_path):
    """Integration B5 (ticket A13-1, the CLI's continuation-check): nothing before the owner's file; the label of an
    unseal at the given time; after the unseal, the label it carried. No score is read, nothing is written."""
    root, unit_root, _ = read(tmp_path, Solver(), [])
    register_canaries(root)
    chain_root = root / CHAIN
    manifest = {"root": str(root)}

    def check(clock="2026-10-22T12:00:00Z"):
        return evaluation.continuation_check(manifest, chain=CHAIN, clock=lambda: clock)

    before = sorted(p for p in root.rglob("*") if p.is_file())
    assert check() == {"chain": CHAIN, "ended": [], "unsealed": False, "continuation": None, "addendum": None,
                       "label": None, "later_reads": None}
    write_json(chain_root / "chain-complete.json", record("chain-complete", EVIDENCE, {"chain": CHAIN}))
    write_json(root / "shared" / "owner-continuation.json",
               {"by": "owner", "date": "2026-10-22", "decision": "continue", "note": "go on"})
    found = check()
    assert (found["ended"], found["continuation"], found["label"], found["later_reads"]) == (
        ["chain-complete.json"], "continue", "interim_read_without_prior_addendum", "repeated_test_development")
    addendum(root, "2026-10-22T09:00:00Z")
    assert check()["label"] == "interim_read_addendum_before_unseal"
    assert check("2026-10-22T08:00:00Z")["later_reads"] == "repeated_test_development"  # addendum after "now"
    written = sorted(p for p in root.rglob("*") if p.is_file())
    assert [p for p in written if p not in before] == sorted(
        [chain_root / "chain-complete.json", root / "shared" / "owner-continuation.json",
         root / "shared" / "formal-addendum.json", root / "shared" / "formal-addendum.md"])
    opened = evaluation.unseal(root, chain_root, CHAIN, [unit_root], run=RUN, evidence=EVIDENCE,
                               clock=lambda: "2026-10-22T10:00:00Z")
    after = check("2026-10-23T00:00:00Z")
    assert after["unsealed"] is True and after["label"] == opened["label"] == "interim_read_addendum_before_unseal"
    assert after["later_reads"] == "confirmatory"
    with pytest.raises(ValueError, match="Unknown chain"):
        evaluation.continuation_check(manifest, chain="E")


# ------------------------------------------------------------------------- fixer regressions (reviews 2026-10-22)
def test_isolation_12_a_self_declared_or_changed_addendum_is_refused_and_sealed_once(tmp_path):
    root = tmp_path / "root"
    (root / "shared").mkdir(parents=True)
    write_json(root / "shared" / "formal-addendum.json", {"sha256": "a" * 64, "written_at": "2026-10-22T09:00:00Z"})
    with pytest.raises(ValueError):  # the old self-declared {sha256, written_at} is no sealed record
        evaluation._addendum(root)
    other = tmp_path / "other"
    (other / "shared").mkdir(parents=True)
    with pytest.raises(ValueError, match="document"):
        evaluation.seal_addendum(other, evidence=EVIDENCE, clock=lambda: "2026-10-22T09:00:00Z")
    sealed = addendum(other, "2026-10-22T09:00:00Z")
    assert evaluation._addendum(other) == {"sha256": sealed["sha256"], "written_at": "2026-10-22T09:00:00Z"}
    with pytest.raises(ValueError, match="once"):
        evaluation.seal_addendum(other, evidence=EVIDENCE, clock=lambda: "2026-10-22T10:00:00Z")
    (other / "shared" / "formal-addendum.md").write_text("A later, different addendum.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="differs from its seal"):
        evaluation._addendum(other)


def test_isolation_12_no_unseal_while_another_chain_of_the_root_is_running(tmp_path):
    root, unit_root, _ = read(tmp_path, Solver(), [])
    register_canaries(root)
    chain_root = root / CHAIN
    write_json(chain_root / "chain-complete.json", record("chain-complete", EVIDENCE, {"chain": CHAIN}))
    write_json(root / "shared" / "owner-continuation.json",
               {"by": "owner", "date": "2026-10-22", "decision": "continue", "note": "go on"})
    (root / "G").mkdir()  # chain G of the same root is still running
    with pytest.raises(ValueError, match="every chain"):
        evaluation.unseal(root, chain_root, CHAIN, [unit_root], run=RUN, evidence=EVIDENCE)
    write_json(root / "G" / "chain-terminated.json", record("chain-terminated", EVIDENCE, {"chain": "G"}))
    opened = evaluation.unseal(root, chain_root, CHAIN, [unit_root], run=RUN, evidence=EVIDENCE)
    cell = next(iter(opened["units"][BENCH].values()))
    # statistics review 5: the unsealed cell carries what the §8.3 table needs
    assert {"official", "final", "lenient", "carrier", "fault_kinds", "worst_delivery", "dispatch_ts", "finish_ts",
            "completion_tokens", "room"} <= set(cell)


def test_isolation_3_the_scorer_directory_passes_the_frozen_v7_guard_and_is_deleted(tmp_path):
    from skillopt.continual_eval import sheet_recalc_adapter

    store = evaluation.EvaluationStore(tmp_path / "attempt-1", evidence=EVIDENCE)
    request = {"benchmark": "spreadsheetbench", "task_id": "fixture-sheet-1", "run": 0}
    position = digest(request)
    prediction = {"files": {}}

    def context(directory):
        return {"_score_context": {"artifact_dir": str(directory), "position": position, "request": request,
                                   "prediction_hash": digest(prediction)}}

    qualified = {"record_hash": "q" * 64, "engine": {"image": "fixture"}}
    found, _ = sheet_recalc_adapter._context(context(store.scorer_dir(position)), {}, {}, prediction, qualified)
    assert found == store.scorer_dir(position) and store.transient in found.parents
    with pytest.raises(ValueError, match="host-only"):  # the guard is real: the old directory was refused
        sheet_recalc_adapter._context(context(store.transient / "scorer_artifacts" / position), {}, {}, prediction,
                                      qualified)
    found.mkdir(parents=True)
    (found / "receipt.json").write_text('{"output_base64": "UEsDBA=="}', encoding="utf-8")
    assert store.finish()["files"] == 1 and not store.transient.exists()


def test_isolation_2_an_alfworld_test_game_is_routed_on_a_view_made_in_memory(tmp_path, monkeypatch):
    from skillopt.coevo5.calls import Slots
    from skillopt.execskill.protocol import ALFWORLD_ROUTING_VIEW
    from tests.execskill_fakes_env import alf_sessions
    from tests.fixtures.execskill.items import alfworld_items

    sessions = alf_sessions(monkeypatch)
    games = alfworld_items(tmp_path / "data")
    tasks = [{"task_id": g["task_id"], "public": {"game_file": g["public"]["game_file"]}, "private": {}}
             for g in games]  # frozen-shaped: public {game_file} only (datasets.py:27-35)
    mug = procedure("p-alfworld-1-1", ("applies", "alf_before_step"), header="Fridge notes.", evidence=EVIDENCE)
    hooks = {mug.id: {"applies": lambda view: "mug" in view["task_text"]}}
    final = with_(empty(step="pilot/s1-alfworld/t1", evidence=EVIDENCE), step="pilot/s1-alfworld/t2", add=[mug])

    @contextmanager
    def workers(package, item):
        worker = FakeSandbox(hooks).start(package, kind="cell")
        try:
            yield worker
        finally:
            worker.close()

    before = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    reset = evaluation.alfworld_reset(RUNTIME["alfworld"], Slots(tmp_path / "slots", "alfworld-episode", 1))
    with pytest.raises(ValueError, match="reset"):
        evaluation.test_plan(tasks, final, bench="alfworld", unit="D/test/alfworld", runtime=RUNTIME["alfworld"],
                             workers=workers)
    plan = evaluation.test_plan(tasks, final, bench="alfworld", unit="D/test/alfworld", runtime=RUNTIME["alfworld"],
                                workers=workers, reset=reset)
    assert len(sessions) == len(tasks) and all(s.closed for s in sessions)
    assert all(set(t["public"]) == {"game_file"} for t in tasks)  # the caller's tasks are untouched
    for task in plan["tasks"]:
        view = task["public"]["routing_view"]
        assert task["public"]["routing_view_sha256"] == digest(view) and tuple(view) == ALFWORLD_ROUTING_VIEW
    fired = {t["task_id"] for t in plan["tasks"] if "mug" in t["public"]["routing_view"]["task_text"]}
    assert fired and set(plan["zero"]) == {t["task_id"] for t in tasks} - fired
    # the views live in memory only: nothing was written (the slot files aside)
    after = [p for p in tmp_path.rglob("*") if p.is_file() and "slots" not in p.parts]
    assert sorted(after) == [p for p in before if "slots" not in p.parts]
    with pytest.raises(ValueError, match="inside the read"):
        evaluation.test_plan(plan["tasks"], final, bench="alfworld", unit="D/test/alfworld",
                             runtime=RUNTIME["alfworld"], workers=workers, reset=reset)


def test_isolation_11_a_crashed_attempts_transient_store_is_deleted_with_a_record(tmp_path):
    unit_root = tmp_path / "run-root" / CHAIN / "test" / BENCH
    crashed = unit_root / "attempt-1"
    write_json(crashed / "transient" / "cells" / "x.json", {"prediction": "a raw test prediction"})
    write_json(crashed / "recovery.json", {"by": "owner", "date": "2026-10-22", "decision": "redo after a kill"})
    root, unit_root, found = read_attempt(tmp_path, Solver(), [], attempt="attempt-2")
    assert found["status"] == "complete" and not (crashed / "transient").exists()
    deletion = verified(read_json(crashed / "transient-deleted.json"), "transient-deletion")
    assert deletion["files"] == 1
    scan = verified(read_json(unit_root / "attempt-2" / "canary_scan.json"), "canary-scan")
    assert scan["cleaned_attempts"] == ["attempt-1"]


def test_isolation_11_a_pause_deletes_the_store_with_its_record_and_scans(tmp_path):
    def pausing(pinned, bench, *, access):
        raise Pause("fixture_pause", "panel unavailable", access.unit)

    with pytest.raises(Pause):
        read_attempt(tmp_path, Solver(), [], panel_function=pausing)
    attempt = tmp_path / "run-root" / CHAIN / "test" / BENCH / "attempt-1"
    assert verified(read_json(attempt / "transient-deleted.json"), "transient-deletion")["files"] == 0
    status = verified(read_json(attempt / "status.json"), "unit-status")
    assert status["kind"] == "fixture_pause" and status["scan"]["hits"] == []


def test_isolation_10_the_scan_covers_the_diagnostics_and_shared_test_and_runs_before_any_call(tmp_path):
    secret = "A test question text that must never leave the read."
    shared = tmp_path / "run-root" / "shared"
    (shared / "host_only" / "diagnostics").mkdir(parents=True)
    (shared / "host_only" / "diagnostics" / "child-step-1.log").write_text("warning: " + secret, encoding="utf-8")
    solver = Solver()
    with pytest.raises(Pause) as stop:
        read_attempt(tmp_path, solver, [evaluation.canary(secret)])
    assert stop.value.kind == "canary_hit" and solver.calls == 0
    status = verified(read_json(tmp_path / "run-root" / CHAIN / "test" / BENCH / "attempt-1" / "status.json"),
                      "unit-status")
    assert status["hits"] == [{"where": "diagnostics", "path": "child-step-1.log", "canary": 0}]
    files, hits = evaluation.unit_scan(tmp_path / "run-root" / CHAIN / "test" / BENCH, shared,
                                       [evaluation.canary(secret)])
    assert hits and all(secret not in json.dumps(hit) for hit in hits)


def read_attempt(tmp_path, solver, canaries, *, attempt="attempt-1", panel_function=None):
    """``read`` with another attempt directory or panel."""
    root = tmp_path / "run-root"
    shared = root / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    if not (shared / "consent.json").exists():
        write_json(shared / "consent.json", consent_value())
    endpoint = Endpoint(solver, model="deepseek-v4.1-flash-1017", max_tokens=100,
                        slots=Slots(tmp_path / "slots", "deepseek", 2), sleep=lambda _: None)
    unit_root = root / CHAIN / "test" / BENCH
    ticks = itertools.count()
    context = Context(attempt=unit_root / attempt, endpoint=endpoint, runtime=RUNTIME,
                      cards={b: CARD for b in BENCHES}, native=Slots(tmp_path / "slots", "spreadsheet-native", 1),
                      episodes=Slots(tmp_path / "slots", "alfworld-episode", 1),
                      worker=lambda bench: FakeSandbox(HOOKS), evidence=EVIDENCE, clock=lambda: float(next(ticks)))
    found = evaluation.evaluate(unit_root, run=RUN, shared=shared, pinned=None, chain=CHAIN, bench=BENCH, arms=arms(),
                                context=context, workers=2, route_workers=route_workers, canaries=canaries,
                                panel=panel_function or panel)
    return root, unit_root, found


# --------------------------------------------------------------------------- the read's twins (integration-B5)
def test_b5_both_chains_withhold_the_same_seeded_twins_on_the_same_items():
    """Registrar decision on integration-B5: the read's twins are drawn under ``test/<bench>`` with the chain dropped,
    so chains G and D withhold identical halves of the same items (acceptance twins stay seeded per chain and unit)."""
    tasks = [dict(item) for item in ITEMS]
    plans = {chain: evaluation.test_plan(tasks, FINAL, bench=BENCH, unit="%s/test/%s" % (chain, BENCH),
                                         runtime=RUNTIME[BENCH], workers=route_workers) for chain in ("G", "D")}
    assert plans["G"]["twins"] and plans["G"]["twins"] == plans["D"]["twins"]
    assert plans["G"]["sha256"] == plans["D"]["sha256"] and evaluation.twin_unit(BENCH) == "test/officeqa"
    for unit in ("D/s2-officeqa/accept", "test/officeqa", "X/test/officeqa", "D/test/livemath"):
        with pytest.raises(ValueError, match="read unit"):
            evaluation.test_plan(tasks, FINAL, bench=BENCH, unit=unit, runtime=RUNTIME[BENCH], workers=route_workers)
