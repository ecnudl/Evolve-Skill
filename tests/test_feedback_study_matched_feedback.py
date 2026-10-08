"""L3 matched one-step feedback study controls (engineering fixtures; no method-effect claim): every block shares one
fresh train rollout across the three arms, the arms differ only in verifier reports and rubric guidance, each arm
makes its own independent native proposal draw, candidates are frozen before any validation, every changed
candidate and the parent get one full validation pass, no-update proposals fall back to the parent, and the
registered block-level analysis is computed exactly."""
import json
import threading

import pytest

from skillopt.continual_learning.skillopt import VERIFIER_PREAMBLE
from skillopt.feedback_study import matched_feedback as mf
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_domains import PRIVATE_CANARY
from tests.test_continual_learning_generalization_v8 import LABEL
from tests.test_continual_learning_verifier_v10 import _closed
from tests.test_feedback_study_fixed_rubric import PASS_IDS, RubricAPI, _panel, _rubrics
from tests.test_feedback_study_fixed_rubric import _spec as _l1_spec


def _spec(panel):
    template = dict(_l1_spec(panel)["template"])
    rubrics = _rubrics()
    return mf.build_spec(template, {"default": rubrics["default"], "h2": rubrics["h2"]}, {"fixture": True})


def evaluate(task, skill):
    """Train rows: fixed host outcomes; validation rows: even ids need the generic rule, odd ids the h2-specific one."""
    index = int(task["task_id"])
    if task["partition"] == "development":
        ok = task["task_id"] in PASS_IDS
    elif index % 2 == 0:
        ok = "requested constant" in skill
    else:
        ok = "answer-checkable" in skill
    return ({"status": "available", "output": f"one #{index}" if ok else f"zero #{index}", "reason": "fixture"},
            {"status": "pass" if ok else "fail", "score": float(ok), "reason": "fixture", "metrics": {}})


class FeedbackAPI(RubricAPI):
    """Judge as in L1 (default abstains on wrong answers -> unauthorized; h2 detects them -> authorized). Analysts that
    see the h2 rubric guidance (and merges/rankings of their edits) add an h2-specific rule; ``empty`` makes every
    analyst propose nothing (no update)."""

    def __init__(self, rules=None, *, empty=False):
        super().__init__(rules)
        self.empty, self.reflections = empty, []

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if kind.endswith("reflection"):
            extra = " Check answer-checkable constraints." if ("ARM:h2" in system or "answer-checkable" in user) else ""
            edits = [] if self.empty else [{"op": "append", "content": "Use the requested constant result." + extra}]
            row = {**row, "response": json.dumps({"batch_size": 2, "patch": {"reasoning": "Fixture only", "edits": edits}})}
            with self.lock:
                self.reflections.append((key, system, user))
        return row


def _intents(root, role):
    return {p.stem: json.loads(p.read_text()) for p in (root / "call_intents").glob("*.json")
            if json.loads(p.read_text())["role"] == role}


def test_matched_blocks_share_rollouts_freeze_candidates_and_analyze_by_block(tmp_path):
    panel = _panel()
    spec = _spec(panel)
    root = tmp_path / "study"
    api = FeedbackAPI()
    seen, lock = {"train": 0}, threading.Lock()

    def tracked(task, skill):
        with lock:
            if task["partition"] == "development":
                seen["train"] += 1
            else:  # validation of block b only after ALL of its candidates and dispositions were frozen
                block = (seen["train"] - 1) // 12
                assert (root / "blocks" / str(block) / "candidates.json").is_file(), block
        return evaluate(task, skill)

    result = mf.run_study(spec, panel, root, fixture_api=api, fixture_evaluate=tracked)
    assert result["status"] == "completed" and result["completed_blocks"] == mf.BLOCKS and seen["train"] == 12 * mf.BLOCKS
    # arms: scalar and the unauthorized default arm propose the generic rule, the authorized h2 arm the h2 rule
    arms = result["arms"]
    assert arms["h2"]["authorized_blocks"] == mf.BLOCKS and arms["default"]["authorized_blocks"] == 0
    assert arms["scalar"]["pass"] == arms["default"]["pass"] == 2 * mf.BLOCKS and arms["h2"]["pass"] == 4 * mf.BLOCKS
    primary = result["primary"]
    assert primary["differences"] == [2] * mf.BLOCKS and primary["p_value"] == pytest.approx(2 / 2 ** mf.BLOCKS)
    assert primary["informative_blocks"] == mf.BLOCKS and primary["method"] == "exact_block_sign_flip_convolution"
    assert "informative_families" not in primary
    # the private-label sentinel through every analyst, merge and ranking request
    assert api.reflections and all(LABEL not in s + u and PRIVATE_CANARY not in s + u for _, s, u in api.reflections)
    assert primary["supported"] is True and result["registered_wording"].startswith("evolved_verifier_feedback")
    default_vs_scalar, h2_vs_default = result["secondary"]
    assert default_vs_scalar["differences"] == [0] * mf.BLOCKS and default_vs_scalar["p_value"] == 1
    assert h2_vs_default["mean_difference"] == 2
    # every arm drew its OWN proposal: distinct logical ids even where inputs are identical (scalar vs unauthorized)
    reflection = _intents(root, "reflection")
    for block in range(mf.BLOCKS):
        prefixes = {arm: [i for i in reflection.values() if i["logical_id"].startswith(f"skillopt:{block}-{arm}:")]
                    for arm in mf.ARMS}
        assert all(prefixes.values()) and len(prefixes["scalar"]) == len(prefixes["default"])
        first = {arm: sorted(prefixes[arm], key=lambda i: i["logical_id"])[0] for arm in mf.ARMS}
        assert first["scalar"]["system"] == first["default"]["system"] and first["scalar"]["user"] == first["default"]["user"]
        assert first["h2"]["system"] != first["scalar"]["system"] and "ARM:h2" in first["h2"]["system"]
        assert VERIFIER_PREAMBLE[:40] not in first["scalar"]["system"] and VERIFIER_PREAMBLE[:40] in first["h2"]["system"]
        candidates = json.loads((root / "blocks" / str(block) / "candidates.json").read_text())
        assert candidates["dispositions"]["h2"]["traces_with_verifier_report"] == 6
        assert candidates["dispositions"]["scalar"]["traces_with_verifier_report"] == 0
        assert candidates["dispositions"]["default"]["rubric_guidance"] is False
        # the h2 arm's failed rows carry exactly their sealed reports; the scalar arm's never
        h2_turns = [json.loads(p.read_text())[2]["content"]
                    for p in (root / "native" / str(block) / "h2" / "predictions").rglob("conversation.json")]
        scalar_turns = [json.loads(p.read_text())[2]["content"]
                        for p in (root / "native" / str(block) / "scalar" / "predictions").rglob("conversation.json")]
        assert sum("Verifier (reusable rubric" in t for t in h2_turns) == 6
        assert not any("Verifier" in t for t in scalar_turns)
        # one full validation pass per changed candidate and for the parent, on registered rollouts
        outcome = json.loads((root / "blocks" / str(block) / "outcome.json").read_text())
        plan = mf.block_plan(spec, block)
        assert set(outcome["evaluations"]) == set(mf.SLOTS)
        assert all(outcome["evaluations"][s]["rollout"] == plan["validation_rollouts"][s] for s in mf.SLOTS)
        assert all(e["positions"] == 4 for e in outcome["evaluations"].values())
    # the shared rollout: each block judged and proposed from the same 12 train rows (one rollout id per block)
    intents = [json.loads(p.read_text()) for p in (root / "evaluation_intents").glob("*.json")]
    assert sorted({i["rollout"] for i in intents if i["role"] == "train"}) == list(range(mf.BLOCKS))
    assert sum(i["role"] == "train" for i in intents) == 12 * mf.BLOCKS
    # replay from the sealed evidence, no new call
    calls = len(api.reflections)
    assert mf.run_study(spec, panel, root, fixture_api=api, fixture_evaluate=tracked) == result
    assert len(api.reflections) == calls


def test_no_update_proposals_fall_back_to_the_block_parent_pass(tmp_path):
    panel = _panel()
    spec = _spec(panel)
    result = mf.run_study(spec, panel, tmp_path / "s", fixture_api=FeedbackAPI(empty=True), fixture_evaluate=evaluate)
    assert result["status"] == "completed"
    assert all(result["arms"][arm]["dispositions"] == {"no_update": mf.BLOCKS} for arm in mf.ARMS)
    assert result["primary"]["differences"] == [0] * mf.BLOCKS and result["primary"]["supported"] is False
    for block in range(mf.BLOCKS):
        outcome = json.loads((tmp_path / "s" / "blocks" / str(block) / "outcome.json").read_text())
        assert set(outcome["evaluations"]) == {"parent"}
        assert all(outcome["arms"][arm]["evaluated"] == "parent_fallback" for arm in mf.ARMS)


def test_a_failure_leaves_a_pending_study_that_is_never_resumed(tmp_path):
    panel = _panel()
    spec = _spec(panel)
    calls = {"h2": 0}

    def third_block_h2(payload):
        if payload.get("rubric", {}).get("mechanism", "").startswith("ARM:h2"):
            calls["h2"] += 1
            return calls["h2"] == 2 * 12 + 5  # a cell of block 2
        return False

    def broken(row, cap):
        return {**row, "ok": False, "finish_reason": None, "status": 502, "stream_complete": False,
                "error_type": "http_error", "response": None}

    root = tmp_path / "s"
    result = mf.run_study(spec, panel, root, fixture_api=FeedbackAPI({third_block_h2: broken}), fixture_evaluate=evaluate)
    assert result["status"] == "pending" and result["reason"] == "verifier_call_failed" and result["completed_blocks"] == 2
    assert "primary" not in result
    assert mf.verify_result(root) == result  # a pending result is sealed evidence too
    (root / "result.json").unlink()
    assert mf.run_study(spec, panel, root, fixture_api=FeedbackAPI(), fixture_evaluate=evaluate)["reason"] == \
        "interrupted_study_no_automatic_resume"


def test_verify_result_rejects_changed_missing_or_extra_evidence(tmp_path):
    import shutil

    panel = _panel()
    spec = _spec(panel)
    mf.run_study(spec, panel, tmp_path / "ok", fixture_api=FeedbackAPI(), fixture_evaluate=evaluate)
    assert mf.verify_result(tmp_path / "ok")["status"] == "completed"
    for damage in ("change", "delete", "extra"):
        copy = tmp_path / damage
        shutil.copytree(tmp_path / "ok", copy)
        if damage == "change":
            target = copy / "native" / "3" / "h2" / "result.json"
            target.write_text(target.read_text() + "\n")
        elif damage == "delete":
            (copy / "blocks" / "5" / "candidates.json").unlink()
        else:
            (copy / "blocks" / "5" / "note.json").write_text("{}")
        with pytest.raises(ValueError):
            mf.verify_result(copy)


def test_the_protocol_is_frozen_and_the_plan_is_registered(tmp_path):
    panel = _panel()
    spec = _spec(panel)
    with pytest.raises(ValueError):
        mf.validate_spec({**spec, "blocks": 4})
    rubrics = _rubrics()
    with pytest.raises(ValueError):  # the treatment rubric must differ from the control
        mf.build_spec(dict(spec["template"]), {"default": rubrics["default"], "h2": rubrics["default"]}, {})
    plans = [mf.block_plan(spec, b) for b in range(mf.BLOCKS)]
    assert plans == [mf.block_plan(spec, b) for b in range(mf.BLOCKS)]  # deterministic from the registered seed
    assert all(sorted(p["proposal_order"]) == sorted(mf.ARMS) and sorted(p["evaluation_order"]) == sorted(mf.SLOTS)
               for p in plans)
    rollouts = [r for p in plans for r in p["validation_rollouts"].values()]
    assert len(set(rollouts)) == len(rollouts) and min(rollouts) >= 1
    assert len({tuple(p["proposal_order"]) for p in plans}) > 1  # actually randomized across blocks
    assert set(mf.study_sources(mf.MODULES)) == {f"feedback_study/{m}" for m in mf.MODULES}
    assert digest(panel) == spec["template"]["panel_hash"]


def test_the_cli_status_verifies_before_printing(tmp_path):
    from scripts import run_fivebench_matched_feedback_study as cli

    panel = _panel()
    spec = _spec(panel)
    mf.run_study(spec, panel, tmp_path / "out" / "study", fixture_api=FeedbackAPI(), fixture_evaluate=evaluate)
    assert cli.main(["status", "--output", str(tmp_path / "out")]) == 0
    (tmp_path / "out" / "study" / "blocks" / "0" / "plan.json").unlink()
    with pytest.raises(ValueError):
        cli.main(["status", "--output", str(tmp_path / "out")])


# ----------------------------------------------------------------------------- review round L3-1 regressions
class AnalystFaultAPI(FeedbackAPI):
    """The h2 arm's analyst/merge/rank replies are unusable: unparseable JSON (the one retry too) or length-truncated."""

    def __init__(self, mode):
        super().__init__()
        self.mode = mode

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if kind.endswith("reflection") and "ARM:h2" in system:
            if self.mode == "json":
                return {**row, "response": "this is not one JSON object"}
            return _closed(row, "length", "truncated_content", tokens=min(max_tokens, 100))
        return row


@pytest.mark.parametrize("mode", ["json", "length"])
def test_a_failed_native_proposal_leaves_the_study_pending_without_validation(tmp_path, mode):
    """Registered (Codex L3-1 b): any native pipeline failure -- analyst JSON rejected after its one retry, or a reply
    truncated at the reflection cap -- makes the study pending; the block is never validated nor resumed."""
    panel = _panel()
    spec = _spec(panel)
    root = tmp_path / "s"
    result = mf.run_study(spec, panel, root, fixture_api=AnalystFaultAPI(mode), fixture_evaluate=evaluate)
    assert result["status"] == "pending" and result["completed_blocks"] == 0 and "primary" not in result
    assert not (root / "blocks" / "0" / "candidates.json").exists() and not (root / "blocks" / "0" / "outcome.json").exists()
    intents = [json.loads(p.read_text()) for p in (root / "evaluation_intents").glob("*.json")]
    assert intents and all(i["role"] == "train" for i in intents)  # no validation call at all
    (root / "result.json").unlink()
    assert mf.run_study(spec, panel, root, fixture_api=FeedbackAPI(), fixture_evaluate=evaluate)["reason"] == \
        "interrupted_study_no_automatic_resume"


class OversizedAPI(FeedbackAPI):
    """The h2 arm's edits (and their merges/rankings) exceed the frozen 32,000-byte Skill interface."""

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if kind.endswith("reflection") and ("ARM:h2" in system or "answer-checkable" in user):
            content = "Check answer-checkable constraints. " + "x" * 33000
            row = {**row, "response": json.dumps({"batch_size": 2, "patch": {"reasoning": "Fixture only", "edits": [
                {"op": "append", "content": content}]}})}
        return row


def test_an_oversized_candidate_falls_back_to_the_parent_with_its_rejection_recorded(tmp_path):
    panel = _panel()
    spec = _spec(panel)
    root = tmp_path / "s"
    result = mf.run_study(spec, panel, root, fixture_api=OversizedAPI(), fixture_evaluate=evaluate)
    assert result["status"] == "completed"
    assert result["arms"]["h2"]["dispositions"] == {"rejected_inadmissible_over_budget": mf.BLOCKS}
    for block in range(mf.BLOCKS):
        candidates = json.loads((root / "blocks" / str(block) / "candidates.json").read_text())
        h2 = candidates["dispositions"]["h2"]
        assert h2["evaluated"] == "parent_fallback" and h2["candidate_hash"] is None and h2["rejected_candidate_hash"]
        outcome = json.loads((root / "blocks" / str(block) / "outcome.json").read_text())
        assert "h2" not in outcome["evaluations"] and outcome["arms"]["h2"]["pass"] == outcome["evaluations"]["parent"]["pass"]
        rejected = json.loads((root / "native" / str(block) / "h2" / "result.json").read_text())
        assert rejected["rejected_candidate_bytes"] > 32000 and rejected["candidate_skill"] == ""


def test_unknown_validation_outcomes_keep_the_denominator_and_bound_the_contrast(tmp_path):
    panel = _panel()
    spec = _spec(panel)

    def with_unknown(task, skill):
        if task["task_id"] == "13":
            return ({"status": "available", "output": "?", "reason": "fixture"},
                    {"status": "unknown", "score": None, "reason": "fixture_unverifiable", "metrics": {}})
        return evaluate(task, skill)

    result = mf.run_study(spec, panel, tmp_path / "s", fixture_api=FeedbackAPI(), fixture_evaluate=with_unknown)
    assert result["status"] == "completed"
    for arm in mf.ARMS:
        assert result["arms"][arm]["positions"] == 4 * mf.BLOCKS and result["arms"][arm]["unknown"] == mf.BLOCKS
    primary = result["primary"]
    assert primary["differences"] == [1] * mf.BLOCKS and primary["unknown_sensitivity_mean_bounds"] == [0, 2]


class BothAuthorizedAPI(FeedbackAPI):
    """The default rubric detects too (with its own evidence text), so both verifier arms are authorized."""

    def _verifier(self, payload):
        value = super()._verifier(payload)
        if not payload["rubric"]["mechanism"].startswith("ARM:") and payload["anonymous_response"].startswith("zero"):
            value["checks"][0].update(verdict="fail", evidence="default rubric: " + payload["anonymous_response"][:40])
        return value


def test_a_report_from_another_arm_is_rejected(tmp_path):
    from copy import deepcopy

    from skillopt.continual_learning.feedback import project
    from skillopt.continual_learning.ledger import Ledger
    from skillopt.feedback_study.common import local_rubric

    panel = _panel()
    spec = _spec(panel)
    root = tmp_path / "s"
    result = mf.run_study(spec, panel, root, fixture_api=BothAuthorizedAPI(), fixture_evaluate=evaluate)
    assert result["status"] == "completed" and result["arms"]["default"]["authorized_blocks"] == mf.BLOCKS
    value = json.loads((root / "study.json").read_text())
    ledger = Ledger(root, value, None)
    reports = {arm: {p.stem: json.loads(p.read_text()) for p in (root / "verifier" / f"0-{arm}" / "reports").glob("*.json")}
               for arm in mf.VERIFIER_ARMS}
    tasks = {digest(t): t for t in panel["tasks"]}
    traces = []
    for path in (root / "evaluations").glob("*.json"):
        row = json.loads(path.read_text())
        if row["request"]["role"] == "train" and row["request"].get("rollout") == 0:
            task = tasks[row["request"]["task_hash"]]
            traces.append({**project(value, task["public"], row["prediction"], row["score"], private=task["private"],
                                     role="train"), "evidence_hash": row["record_hash"]})
    token = next(t["evidence_hash"] for t in traces if t["Feedback"]["status"] == "fail")
    rubric = local_rubric(spec["rubrics"]["h2"])

    def with_text(text):
        copy = deepcopy(traces)
        for trace in copy:
            if trace["evidence_hash"] == token:
                trace["Feedback"] = {**trace["Feedback"], "verifier": text}
        return copy

    h2_root = root / "verifier" / "0-h2"
    assert reports["h2"][token]["feedback"] != reports["default"][token]["feedback"]
    mf._bind_arm_traces(with_text(reports["h2"][token]["feedback"]), ledger, value["parent_skill"], 0, "0-h2",
                        h2_root, reports["h2"], rubric)  # the arm's own sealed report binds
    with pytest.raises(ValueError):  # the other arm's report text under this arm
        mf._bind_arm_traces(with_text(reports["default"][token]["feedback"]), ledger, value["parent_skill"], 0, "0-h2",
                            h2_root, reports["h2"], rubric)
    with pytest.raises(ValueError):  # the other arm's report records presented as this arm's
        mf._bind_arm_traces(with_text(reports["default"][token]["feedback"]), ledger, value["parent_skill"], 0, "0-h2",
                            h2_root, reports["default"], rubric)
    with pytest.raises(ValueError):  # another block's label
        mf._bind_arm_traces(with_text(reports["h2"][token]["feedback"]), ledger, value["parent_skill"], 0, "1-h2",
                            h2_root, reports["h2"], rubric)


def test_a_prepared_study_refuses_a_changed_implementation(tmp_path, monkeypatch):
    """Codex L3-1 P2: preparation seals the implementation identity; a later code change is refused before any client
    or call (zero-call drift check)."""
    from skillopt.continual_eval.core import write_json

    panel = _panel()
    spec = _spec(panel)
    root = tmp_path / "s"
    write_json(root / "protocol.json", spec)
    write_json(root / "study.json", mf._manifest(spec, panel))
    monkeypatch.setattr(mf, "study_sources", lambda names: {"feedback_study/matched_feedback.py": "0" * 64})
    api = FeedbackAPI()
    with pytest.raises(ValueError, match="implementation identity"):
        mf.run_study(spec, panel, root, fixture_api=api, fixture_evaluate=evaluate)
    assert not (root / "started.json").exists() and not api.judged and not api.reflections


def test_a_prepared_study_refuses_changed_native_updater_code_or_prompts(tmp_path, monkeypatch):
    """Codex L3-2 P2: the native updater's code and prompts are part of the prepared identity, checked before any
    client, start marker or model call (a prompt edit after preparation is refused)."""
    from skillopt.continual_eval.core import write_json

    panel = _panel()
    spec = _spec(panel)
    prepared = mf._manifest(spec, panel)
    assert prepared["study"]["native_sources"] == mf.native_sources() and "prompts/analyst_error.md" in prepared["study"]["native_sources"]
    root = tmp_path / "s"
    write_json(root / "protocol.json", spec)
    write_json(root / "study.json", prepared)
    original = mf.native_sources()
    monkeypatch.setattr(mf, "native_sources", lambda: {**original, "prompts/analyst_error.md": "0" * 64})
    api = FeedbackAPI()
    with pytest.raises(ValueError, match="implementation identity"):
        mf.run_study(spec, panel, root, fixture_api=api, fixture_evaluate=evaluate)
    assert not (root / "started.json").exists() and not api.judged and not api.reflections


@pytest.mark.parametrize("drifted", ["skillopt/prompts/__init__.py", "skillopt/coevolution_v5/core.py",
                                     "skillopt/skill_validation/models.py",
                                     "scripts/run_fivebench_matched_feedback_study.py",
                                     "scripts/continue_fivebench_baselines.py"])
def test_the_prepared_identity_covers_the_whole_executed_code_closure(tmp_path, monkeypatch, drifted):
    """Codex L3-3/L3-4 P2: the prompt loader, seal/verify and receipt helpers, the CLI and the client/service
    orchestration (everything the paid run imports) are part of the prepared identity; drift in any of them is refused
    before any client, start marker or call."""
    from skillopt.continual_eval.core import write_json

    closure = mf.code_closure()
    assert {"skillopt/__init__.py", "scripts/__init__.py", "skillopt/feedback_study/matched_feedback.py",
            "skillopt/feedback_study/common.py", "skillopt/gradient/reflect.py", "skillopt/optimizer/clip.py",
            "skillopt/continual_learning/skillopt.py", "skillopt/continual_learning/verifier.py",
            "scripts/run_fivebench_fixed_rubric_study.py", "scripts/run_fivebench_g_stage.py", drifted} <= set(closure)
    assert closure == mf.code_closure()  # deterministic
    panel = _panel()
    spec = _spec(panel)
    prepared = mf._manifest(spec, panel)
    assert prepared["study"]["code_closure"] == closure
    root = tmp_path / "s"
    write_json(root / "protocol.json", spec)
    write_json(root / "study.json", prepared)
    monkeypatch.setattr(mf, "code_closure", lambda: {**closure, drifted: "0" * 64})
    api = FeedbackAPI()
    with pytest.raises(ValueError, match="implementation identity"):
        mf.run_study(spec, panel, root, fixture_api=api, fixture_evaluate=evaluate)
    assert not (root / "started.json").exists() and not api.judged and not api.reflections
