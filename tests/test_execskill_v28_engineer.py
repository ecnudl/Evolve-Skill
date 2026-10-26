"""Real v2.8 engineer orchestration on authored in-process hooks and role replies."""
from contextlib import contextmanager
from dataclasses import replace

import pytest

from skillopt.execskill import engineer as e, profiles as p, step
from skillopt.execskill.package import Package, with_
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import GOOD, EMPTY, change, context, detail
from tests.test_execskill_v24_feedback_isolation import WireRoles, with_run_example
from tests.test_execskill_v24_routing_review import tracker_change
from tests.test_execskill_v26_references import CELL, fixture, reference
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


CONFIG = "zebra-pc-v6"
SYNTAX = "def applies(view):\n    return True\ndef before_call(view, state):\n    return {\n"


def encoded(proposed):
    return engineer_reply({"changes": [proposed.entry]}, [proposed.source])


def run(ctx, *replies):
    prefix = [engineer_reply({"findings": []}, [])] if ctx.mode == "train" else []
    ctx.roles = WireRoles(prefix + list(replies))
    return e.run_train(ctx) if ctx.mode == "train" else e.run(ctx)


def requests(ctx, name):
    return [payload for _, payload, _ in ctx.roles.seen if payload.get("request") == name]


def test_quality_information_and_dropped_tests_reach_next_round_payload():
    ctx, _ = fixture(configuration=CONFIG)
    invalid = reference(ctx, CELL)
    invalid["property"] = {"kind": "note_matches", "value": ["Mara"] * 10}
    package, record = run(ctx, encoded(change(ctx, tests=[invalid])))
    lint = record["lint"]
    assert lint[0]["problems"][0]["evaluated"] is False
    assert "fragments" in lint[0]["problems"][0]["validation_explanation"]
    assert {row["check"] for row in lint[0]["information"]} == {"C5b", "C6", "C6b", "C6c", "C7", "C9"}
    subsequent = replace(ctx, round=2, lint=lint)
    payload = e.payload(subsequent)
    assert payload["lint"] == lint


@pytest.mark.parametrize("source", [
    'def before_call(view, state):\n    return {}\n',
    'def applies(view):\n    return True\n',
    'def applies():\n    return True\ndef before_call(view, state):\n    return {}\n',
])
def test_missing_or_wrong_hook_signatures_are_item_faults_or_inert_not_c3(source):
    ctx, _ = fixture(configuration=CONFIG)
    proposed = change(ctx, source)
    report = e.check(proposed, ctx)
    assert report["passed"] and report["failed"] is None
    assert report.get("inert")


def test_wholly_excluded_procedure_is_inert_and_keeps_declared_scope():
    ctx, _ = fixture(configuration=CONFIG)
    proposed = change(ctx)
    proposed.entry["excluded_benches"] = list(p.SUPPORTED_BENCHES)
    report = e.check(proposed, ctx)
    assert report["passed"] and report["inert"]
    assert proposed.procedure.excluded_benches == tuple(p.SUPPORTED_BENCHES)


@pytest.mark.parametrize("mode", ["train", "single"])
@pytest.mark.parametrize("bad", ["fragments", "trajectory", "string", "wrong_step"])
def test_bad_replay_test_drops_only_the_test(mode, bad):
    ctx, _ = fixture(configuration=CONFIG, mode=mode)
    test = reference(ctx, CELL)
    if bad == "fragments":
        test["property"] = {"kind": "note_matches", "value": ["Mara"] * 10}
    elif bad == "trajectory":
        test["trajectory"] = "unresolvable-cell"
    elif bad == "string":
        test = "not an object"
    else:
        test["property"]["step"] = "invalid-step"
        test["hook"] = "alf_before_step"
    proposal = change(ctx, tests=[test])
    package, record = run(ctx, encoded(proposal))
    assert package is not None and package.procedures[0].source.strip() == proposal.source.strip()
    assert package.procedures[0].replay_tests == ()
    assert record["changes"][0]["attempts"][0]["dropped_tests"]
    assert any(row["rule"] == "malformed_test_dropped" for row in record["repairs"])
    assert not requests(ctx, "fix") and not requests(ctx, "format_retry")
    assert record["version"] == p.kind("engineer-v2-8")


@pytest.mark.parametrize("mode", ["train", "single"])
def test_failing_claim_is_reported_without_any_fix_call(mode):
    ctx, _ = fixture(configuration=CONFIG, mode=mode)
    test = reference(ctx, CELL)
    test["property"]["value"] = "Unmatched authored fragment."
    package, record = run(ctx, encoded(change(ctx, tests=[test])))
    assert package is not None
    report = record["changes"][0]["attempts"][0]
    c5b = next(row for row in report["checks"] if row["check"] == "C5b")
    assert not c5b["passed"] and c5b["informational"] and report["passed"]
    assert c5b["detail"]["failed"][0]["reason"] == "test_failed"
    assert package.procedures[0].replay_tests[0]["claims_fix"]
    assert report["lint"]["tests"][0]["holds"] is False
    assert not requests(ctx, "fix")


@pytest.mark.parametrize("malformed", [None, 17, True])
def test_malformed_test_container_cannot_discard_usable_source(malformed):
    ctx, _ = fixture(configuration=CONFIG)
    proposal = change(ctx)
    proposal.entry["replay_tests"] = malformed
    package, record = run(ctx, encoded(proposal))
    assert package is not None and package.procedures[0].replay_tests == ()
    assert not requests(ctx, "fix") and not requests(ctx, "format_retry")
    assert any("test" in row["rule"] for row in record["repairs"])


def test_real_reverse_replay_mismatch_is_recorded_without_discarding_first_output():
    ctx, workers = fixture(configuration=CONFIG)
    opened = []

    @contextmanager
    def drifting(package, **options):
        ordinal = len(opened)
        opened.append(options)
        with workers(package, **options) as worker:
            original = worker.call
            def call(pid, hook, args, **kwargs):
                result = original(pid, hook, args, **kwargs)
                if hook == "before_call" and result.get("ok"):
                    value = {"facts": ["Replay worker observation %d." % ordinal]}
                    return {**result, "value": value, "value_sha256": digest(value)}
                return result
            worker.call = call
            yield worker

    ctx.workers = drifting
    package, record = run(ctx, encoded(change(ctx)))
    assert package is not None
    report = record["changes"][0]["attempts"][0]
    c6 = next(row for row in report["checks"] if row["check"] == "C6")
    assert c6["detail"]["mismatched"] and c6["informational"] and report["passed"]
    assert opened[1]["hashseed"] == opened[2]["hashseed"] == 0
    assert not requests(ctx, "fix")


@pytest.mark.parametrize("source", [EMPTY, GOOD.replace('return "question" in view', 'return False'),
                                  GOOD.replace('rows = [line.split', 'raise ValueError("Authored fault")\n    rows = [line.split')])
def test_inert_program_is_recorded_and_never_becomes_a_training_candidate(source):
    ctx, _ = fixture(configuration=CONFIG)
    package, record = run(ctx, encoded(change(ctx, source)))
    assert package is None and record["candidate_sha256"] is None
    result = record["changes"][0]
    assert result["inert"] and result["survived"] and result["fix_calls"] == 0
    line = step._line(1, {"engineer": record, "candidate_sha256": None}, None)
    assert line["reason"] == "inert" and line["proposals"][0]["fate"] == "inert"


def test_inert_revision_preserves_incumbent():
    ctx, _ = fixture(configuration=CONFIG)
    incumbent = change(ctx)
    e._build(incumbent, ctx)
    parent = with_(ctx.parent, step="D/s0-parent", add=[incumbent.procedure])
    ctx = replace(ctx, parent=parent, base=parent)
    revision = change(ctx, EMPTY)
    revision.entry.update(kind="revision", revises=incumbent.procedure.id)
    package, record = run(ctx, encoded(revision))
    assert package is None and record["parent_sha256"] == parent.sha256
    assert record["changes"][0]["inert"] and record["changes"][0]["kind"] == "revision"
    assert ctx.parent.get(incumbent.procedure.id).source == GOOD


def test_answer_channel_marker_is_still_fatal():
    ctx, _ = fixture(configuration=CONFIG)
    source = 'def applies(view):\n    return True\ndef before_call(view, state):\n    return {"facts": ["<answer> clue"]}\n'
    proposal = change(ctx, source)
    report = e.check(proposal, ctx)
    assert report["failed"] == "C8" and not report["passed"]


def test_alf_tracker_quality_failure_is_information():
    ctx, _ = context(configuration="alfworld-v3", bench="alfworld")
    ctx = replace(ctx, current=list(ctx.trajectories))
    proposal = tracker_change(ctx, claims=False)
    proposal.source = proposal.source.replace('count += int(', 'count += 1 + int(')
    package, record = run(ctx, encoded(proposal))
    assert package is not None
    report = record["changes"][0]["attempts"][0]
    c7 = detail(report, "C7")
    assert c7["tracker_agreement"][0] == 0 and c7["tracker_agreement"][1] > 0
    assert any(row["reason"] == "reference_tracker" for row in c7.get("information", c7["problems"]))
    assert report["passed"] and not requests(ctx, "fix")


@pytest.mark.parametrize("defect,failed", [(SYNTAX, "C2"), (GOOD + "#" + "x" * 24000, "C3")])
def test_syntax_and_source_cap_remain_fatal_and_use_behavior_fix(defect, failed):
    ctx, _ = fixture(configuration=CONFIG)
    package, record = run(ctx, encoded(change(ctx, defect)), encoded(change(ctx)))
    assert package is not None
    row = record["changes"][0]
    assert [attempt["failed"] for attempt in row["attempts"]] == [failed, None]
    assert row["fix_calls"] == 1 and len(requests(ctx, "fix")) == 1
    assert "24000" in ctx.roles.wire[1]["system"]


def test_format_retry_uses_unit_budget_without_consuming_train_fix_allowance():
    ctx, _ = fixture(configuration=CONFIG)
    broken, fixed = encoded(change(ctx, SYNTAX)), encoded(change(ctx))
    package, record = run(ctx, broken, "```json\n{", broken, broken, fixed)
    assert package is not None
    assert record["changes"][0]["fix_calls"] == p.TRAIN_FIXES == 3
    assert len(requests(ctx, "fix")) == 3 and len(requests(ctx, "format_retry")) == 1
    assert record["format_retries"][0]["parsed"] and record["calls"] == 5
    assert len(ctx.roles.calls) == 6  # the analyst uses its separate registered scope
    retry = requests(ctx, "format_retry")[0]
    assert retry["parse_problem"] and retry["schema"]["example"] and "Only fix the format" in retry["instruction"]


def test_truncated_proposal_gets_one_format_retry_then_unparseable_history():
    ctx, _ = fixture(configuration=CONFIG)
    package, record = run(ctx, "```json\n{", "```json\n{")
    assert package is None and len(requests(ctx, "format_retry")) == 1 and not requests(ctx, "fix")
    assert record["changes"][0]["reason"] == "unparseable" and not record["format_retries"][0]["parsed"]
    line = step._line(1, {"engineer": record, "candidate_sha256": None}, None)
    line["patience_counted"] = False
    assert line["proposals"][0]["fate"] == "unparseable"
    next_ctx = replace(ctx, round=2, history=[line], roles=WireRoles())
    e.run_train(next_ctx)


def test_next_round_accepts_informational_training_fields_and_inert_history():
    ctx, _ = fixture(configuration=CONFIG)
    package, record = run(ctx, encoded(change(ctx, EMPTY)))
    line = step._line(1, {"engineer": record, "candidate_sha256": None}, None)
    line["patience_counted"] = False
    next_ctx = with_run_example(replace(ctx, configuration=p.ZEBRA_PC_V5))
    next_ctx = replace(next_ctx, configuration=CONFIG,
        training={**next_ctx.training, "informational_guards": ["own_faults", "predicate_faults"]},
        history=[line], roles=WireRoles())
    e.run_train(next_ctx)
    payload = requests(next_ctx, "propose")[0]
    assert payload["training"]["informational_guards"] == ["own_faults", "predicate_faults"]
    assert payload["history"][0]["proposals"][0]["fate"] == "inert"


@pytest.mark.parametrize("entry", [{"kind": "deletion", "id": "fx-absent"},
                                    {"kind": "narrowing", "id": "fx-absent", "benches": []}])
def test_nonapplicable_metadata_edit_is_system_deferred(entry):
    ctx, _ = fixture(configuration=CONFIG)
    package, record = run(ctx, engineer_reply({"changes": [entry]}, []))
    assert package is None and record["changes"][0]["deferred"]
    assert record["changes"][0]["survived"] and not requests(ctx, "fix")
    line = step._line(1, {"engineer": record, "candidate_sha256": None}, None)
    line["patience_counted"] = False
    assert line["reason"] == line["proposals"][0]["fate"] == "system_deferred"
    replace(ctx, round=2, history=[line])


def test_full_package_defers_addition_without_rejecting_the_program():
    ctx, _ = fixture(configuration=CONFIG)
    built = change(ctx)
    e._build(built, ctx)
    parent = Package(tuple(replace(built.procedure, id="fx-existing-%d" % n) for n in range(p.MAX_PROCEDURES)),
                     "D/s0-parent", ctx.evidence)
    ctx = replace(ctx, parent=parent, base=parent)
    package, record = run(ctx, encoded(change(ctx)))
    assert package is None and record["changes"][0]["deferred"]
    assert record["changes"][0]["survived"] and not requests(ctx, "fix")
