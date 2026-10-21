"""Generalization feedback study (fivebench-generalization-feedback-study-v1): one shared rollout over real learn tasks
and generated diagnostic items; a text layer (judge), a code layer (host derivation check on generated rows), both, two
scalar proposals; every distinct candidate scored twice on a transfer pool."""
import json
from copy import deepcopy

import pytest

from scripts import run_generalization_feedback_study as runner
from skillopt.continual_learning.recovery import POLICY_V10
from skillopt.feedback_study import generalization_feedback as gf
from skillopt.validator_pilot.api import digest
from tests.test_feedback_study_rubric_form import FormAPI

TABLE = ("### bulletin_1956.txt page 3\n| Fiscal year | Receipts | Expenditures |\n| 1955 | 60,390 | 64,570 |\n"
         "| 1956 | 68,165 | 66,540 |\n| 1957 | 71,029 | 69,433 |\n")
DERIVATION = {"figures": [{"name": "a", "value": "60,390", "quote": "| 1955 | 60,390 | 64,570 |"},
                          {"name": "b", "value": "68,165", "quote": "| 1956 | 68,165 | 66,540 |"}],
              "expression": "(b - a) / a * 100", "decimals": 2, "answer": "12.87", "category": "percent",
              "question": "q", "source_task_hash": "s"}


def _task(task_id, family, partition, question, answer):
    return {"task_id": task_id, "family_id": family, "project_id": "", "partition": partition,
            "public": {"question": question, "context": TABLE}, "private": {"answer": answer}}


def _material():
    real = [_task("L%d" % i, "lf%d" % i, "development", "What were receipts in fiscal year 1955 for item %d, rounded to the "
                  "nearest hundredths place?" % i, "60390.00") for i in range(8)]
    diag = [_task("gD%d" % i, "officeqa:gen-d:L%d" % i, "development", "By what percent did receipts grow from 1955 to "
                  "1956 (variant %d), rounded to the nearest hundredths place?" % i, "12.87") for i in range(6)]
    transfer = [_task("gT%d" % i, "officeqa:gen-t:H%d" % (i // 2), "skill_confirmation", "What were expenditures in 1957 "
                      "(variant %d), rounded to the nearest hundredths place?" % i, "69433.00") for i in range(6)]
    panel = {"version": "continual-panel-v1", "benchmark": "officeqa", "dataset_revision": "fixture-generalization-v1",
             "provenance": "fixture", "tasks": real + diag + transfer}
    derivations = {t["task_id"]: deepcopy(DERIVATION) for t in diag}
    return panel, derivations


def _spec(panel, derivations, blocks=2, series=None):
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
             "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 3600,
                           "initial_health_policy": "completed_response_v1"}}
    train = sorted({t["family_id"] for t in panel["tasks"] if t["partition"] == "development"})
    selection = sorted({t["family_id"] for t in panel["tasks"] if t["partition"] != "development"})
    template = {"panel_hash": digest(panel), "train_families": train, "selection_families": selection, "model": model,
                "runtime": {}, "parent_skill": "Read the table.\n", "seed": 0, "recovery_policy": deepcopy(POLICY_V10)}
    transfer = sorted(t["task_id"] for t in panel["tasks"] if t["partition"] != "development")
    pools = {"learn_tasks": ["L%d" % i for i in range(8)], "held_out_tasks": ["H0", "H1", "H2"],
             "diagnostic_items": sorted(derivations), "transfer_items": transfer,
             "categories": {**{i: "percent" for i in derivations}, **{i: ("precision" if i < "gT3" else "scale") for i in transfer}}}
    return gf.build_spec(template, pools, digest(derivations), {"fixture": True}, blocks,
                         {"fixture": True, **({"series": series} if series else {})})


def host(task, skill):
    """Real learn rows: even ids pass; odd ids drop the decimals. Diagnostic rows: ids 0-2 answer as a fraction
    (x100 slip), 3-5 pass. Transfer rows: a candidate with the decimals rule passes all; otherwise ids 0-3 fail."""
    tid = task["task_id"]
    if tid.startswith("L"):
        ok = int(tid[1:]) % 2 == 0
        output = "<answer>60390.00</answer>" if ok else "<answer>60390</answer>"
    elif tid.startswith("gD"):
        ok = int(tid[2:]) >= 3
        output = "<answer>12.87</answer>" if ok else "<answer>0.1287</answer>"
    else:
        ok = "decimal places" in skill or int(tid[2:]) >= 4
        output = "<answer>69433.00</answer>" if ok else "<answer>69433</answer>"
    return ({"status": "available", "output": output, "reason": "fixture"},
            {"status": "pass" if ok else "fail", "score": float(ok), "reason": "fixture", "metrics": {}})


class GenAPI(FormAPI):
    """Judges as FormAPI (no decimal point -> fail). Analysts: the edit names the feedback kind they saw."""

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super(FormAPI, self).call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if kind.endswith("reflection"):
            code = "host-executed derivation check" in user
            judge = "Verifier (reusable rubric" in user
            seen = "both" if code and judge else "code" if code else "judge" if judge else "none"
            with self.lock:
                self.reflections.append((key, seen, system, user))
            content = ("Read the table carefully." if seen == "none"
                       else "Give the number of decimal places the question asks (%s feedback)." % seen)
            row = {**row, "response": json.dumps({"batch_size": 2, "patch": {"reasoning": "Fixture only",
                                                                            "edits": [{"op": "append", "content": content}]}})}
        return row


def test_layers_feed_exactly_their_arms_and_candidates_are_scored_twice_on_the_transfer_pool(tmp_path):
    panel, derivations = _material()
    spec = _spec(panel, derivations)
    api = GenAPI()
    result = gf.run_study(spec, panel, derivations, tmp_path / "study", fixture_api=api, fixture_evaluate=host)
    assert result["status"] == "completed", result.get("reason")
    # judge calls: every train row (8 real + 6 generated) x 2 blocks; the code layer makes none
    assert len(api.prompts["verifier"]) == 14 * 2
    for b in range(2):
        c = json.loads((tmp_path / ("study/blocks/%d/candidates.json" % b)).read_text())
        assert c["train"]["generated_rows"] == 6 and c["train"]["host_fail_generated_rows"] == 3
        assert c["verifier"]["global_text"]["authorized"] and c["verifier"]["code_diag"]["authorized"]
        assert c["verifier"]["code_diag"]["error_modes"] == {"power_of_ten": 3}
        d = c["dispositions"]
        assert d["scalar"]["traces_with_feedback"] == 0 and d["scalar_repeat"]["traces_with_feedback"] == 0
        assert d["code_diag"]["traces_with_feedback"] == 3 and d["code_diag"]["generated_traces_with_feedback"] == 3
        # v10 reports every host-failed row the judge checked (passed checks say what was NOT the problem): 4 real + 3
        assert d["global_text"]["traces_with_feedback"] == 7 and d["global_text"]["generated_traces_with_feedback"] == 3
        assert d["global_code"]["traces_with_feedback"] == 7 and d["global_code"]["generated_traces_with_feedback"] == 3
    # what each arm's analysts saw
    seen, users = {}, {}
    for key, kind, system, user in api.reflections:
        logical = json.loads((tmp_path / "study/call_intents" / (key + ".json")).read_text())["logical_id"]
        _, step, stage, _ = logical.split(":")
        arm = step.split("-", 1)[1]
        seen.setdefault(arm, set()).add(kind)
        users.setdefault(arm, []).append((stage, system, user))
    assert seen["scalar"] == seen["scalar_repeat"] == {"none"}
    assert "code" in seen["code_diag"] and "judge" not in seen["code_diag"] and "both" not in seen["code_diag"]
    assert "judge" in seen["global_text"] and "code" not in seen["global_text"]
    assert "both" in seen["global_code"] or {"code", "judge"} <= seen["global_code"]
    analysts = lambda arm: sorted((s, u) for st, s, u in users[arm] if st == "analyst")
    assert analysts("scalar") == analysts("scalar_repeat")  # identical inputs: the in-block noise reference
    assert any("expected 12.87; your answer 0.1287. Diagnosis (power_of_ten)" in u for _, u in analysts("code_diag"))
    # a generated item's derivation reaches the code arms only
    assert all("expected 12.87;" not in u for arm in ("scalar", "scalar_repeat", "global_text") for _, u in analysts(arm))
    assert any("expected 12.87;" in u for _, u in analysts("global_code"))
    # the code layer's registered analyst note rides on the failure analysts of the code arms only
    note = gf.CODE_NOTE["preamble"]
    assert all(note in s for s, u in analysts("code_diag") if "host-executed derivation check" in u)
    assert all(note not in s for arm in ("scalar", "scalar_repeat", "global_text") for s, _ in analysts(arm))
    # the transfer pool: parent and each distinct candidate twice; identical candidates share one evaluation
    outcome = json.loads((tmp_path / "study/blocks/0/outcome.json").read_text())
    assert all(len(e["passes"]) == 2 and e["positions"] == 12 for e in outcome["evaluations"].values())
    assert outcome["arms"]["scalar_repeat"]["evaluation_slot"] in ("scalar", "scalar_repeat")
    assert outcome["selection_task_ids"] == ["gT%d" % i for i in range(6)]
    arms = result["arms"]
    assert arms["scalar"]["pass"] == 2 * 2 * 2 and all(arms[a]["pass"] == 2 * 12 for a in ("global_text", "code_diag", "global_code"))
    by = {(c["treatment"], c["control"]): c for c in result["contrasts"]}
    assert by[("code_diag", "scalar")]["primary"] and by[("code_diag", "scalar")]["differences"] == [8, 8]
    assert by[("code_diag", "scalar")]["supported"] is False  # two blocks cannot reach alpha
    assert by[("scalar_repeat", "scalar")]["differences"] == [0, 0] and not by[("scalar_repeat", "scalar")]["primary"]
    assert result["by_category"]["parent"]["precision"]["positions"] == 2 * 2 * 3
    assert result["verifier"]["code_error_modes"] == {"power_of_ten": 6}
    # replay: no new call; the sealed inventory verifies; the runner's pooled report reads it
    calls = len(api.prompts["verifier"]) + len(api.reflections)
    assert gf.run_study(spec, panel, derivations, tmp_path / "study", fixture_api=api, fixture_evaluate=host) == result
    assert len(api.prompts["verifier"]) + len(api.reflections) == calls
    assert gf.verify_result(tmp_path / "study") == result
    text = runner.report([str(tmp_path)])
    assert "PRIMARY" in text and "noise reference: scalar_repeat - scalar" in text


def test_the_protocol_is_frozen_and_the_derivations_are_bound(tmp_path):
    panel, derivations = _material()
    spec = _spec(panel, derivations, blocks=3)
    from skillopt.coevolution_v5.core import seal
    body = {k: v for k, v in spec.items() if k != "record_hash"}
    with pytest.raises(ValueError):
        gf.validate_spec(seal({**body, "arms": ["scalar", "global_text"]}))
    with pytest.raises(ValueError):
        gf.validate_spec(seal({**body, "pools": {**spec["pools"], "transfer_items": spec["pools"]["diagnostic_items"]}}))
    plan = gf.block_plan(spec, 1)
    assert all(len(v) == 2 for v in plan["validation_rollouts"].values())
    assert len({r for v in plan["validation_rollouts"].values() for r in v} | {r for v in gf.block_plan(spec, 0)["validation_rollouts"].values() for r in v}) == 24
    other = dict(derivations)
    other["gD0"] = {**other["gD0"], "answer": "99.99"}
    with pytest.raises(ValueError):
        gf.run_study(spec, panel, other, tmp_path / "study", fixture_api=GenAPI(), fixture_evaluate=host)
    a, b = _spec(panel, derivations, 1, "a"), _spec(panel, derivations, 1, "b")
    assert a["record_hash"] != b["record_hash"] and gf.block_plan(a, 0) != gf.block_plan(b, 0)


def test_the_split_keeps_bulletin_files_on_one_side_and_the_informative_rule():
    files = {"t1": {"f1"}, "t2": {"f1", "f2"}, "t3": {"f3"}, "t4": {"f4"}, "t5": {"f2"}, "t6": {"f6"}}
    held = runner.held_out_tasks(files, 2, "seed")
    learn = set(files) - set(held)
    assert not {f for t in held for f in files[t]} & {f for t in learn for f in files[t]}
    assert len(held) >= 2 and runner.held_out_tasks(files, 2, "seed") == held
    assert {"t1", "t2", "t5"} <= set(held) or not {"t1", "t2", "t5"} & set(held)  # one component, never cut
    counts = {"a": [0, 3], "b": [2, 3], "c": [3, 3], "d": [1, 1], "e": [0, 2]}
    assert runner.informative(counts) == ["a", "b", "e"]  # failed at least once in >= 2 known runs


def test_the_combined_note_keeps_the_code_diagnosis_and_stays_within_the_frozen_bound():
    from skillopt.continual_learning.verifier import MAX_REPORT_CHARS

    code = "Verifier (host-executed derivation check ...): expected 12.87; your answer 0.1287. Diagnosis (power_of_ten): x." + "q" * 600
    text = "Verifier (reusable rubric ...): " + "t" * 1600
    note = gf.layered(code, text)
    assert note.startswith(code[:200]) and "Diagnosis (power_of_ten)" in note and "Verifier (reusable rubric" in note
    assert len(note) <= MAX_REPORT_CHARS
    assert gf.layered(None, None) is None and gf.layered(code, None).startswith(code) and gf.layered(None, text).startswith(text[:100])
    assert len(gf.layered("c" * 5000, "t" * 5000)) <= MAX_REPORT_CHARS


class LeakyAPI(GenAPI):
    """The code arms' analysts copy the generated item's expected answer into their edit."""

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if kind.endswith("reflection") and "host-executed derivation check" in user:
            row = {**row, "response": json.dumps({"batch_size": 2, "patch": {"reasoning": "Fixture only", "edits": [
                {"op": "append", "content": "Growth questions: the answer is 12.87 (decimal places as asked)."}]}})}
        return row


def test_a_candidate_carrying_a_derivation_never_reaches_a_solver(tmp_path):
    panel, derivations = _material()
    spec = _spec(panel, derivations, blocks=1)
    seen = []

    def spy(task, skill):
        seen.append(skill)
        return host(task, skill)

    result = gf.run_study(spec, panel, derivations, tmp_path / "study", fixture_api=LeakyAPI(), fixture_evaluate=spy)
    assert result["status"] == "completed"
    c = json.loads((tmp_path / "study/blocks/0/candidates.json").read_text())
    for arm in ("code_diag", "global_code"):
        assert c["dispositions"][arm]["status"] == "rejected_derivation_leak" and c["dispositions"][arm]["evaluated"] == "parent_fallback"
        assert c["dispositions"][arm]["leak"][0]["what"] == "answer"
    assert not any("12.87" in skill for skill in seen)  # no solver ever saw the leaked text
    assert gf.derivation_leak("Round 12.87 like this", {"x": DERIVATION}) and not gf.derivation_leak("Use 2 decimals", {"x": DERIVATION})


def test_only_a_primary_contrast_is_supported_over_six_blocks():
    panel, derivations = _material()
    spec = _spec(panel, derivations, blocks=6)
    candidates, outcomes = [], []
    passes = {"scalar": 5, "scalar_repeat": 5, "global_text": 6, "code_diag": 5, "global_code": 7}
    for block in range(6):
        arms = {}
        for arm, n in passes.items():
            statuses = ["pass"] * n + ["fail"] * (12 - n)
            arms[arm] = {"pass": n, "fail": 12 - n, "unknown": 0, "positions": 12, "evaluation_slot": arm,
                         "passes": [{"statuses": statuses[:6]}, {"statuses": statuses[6:]}]}
        parent = {"pass": 4, "fail": 8, "unknown": 0, "positions": 12, "passes": [{"statuses": ["fail"] * 6}, {"statuses": ["fail"] * 6}]}
        outcomes.append({"arms": arms, "evaluations": {"parent": parent}, "selection_task_ids": ["gT%d" % i for i in range(6)]})
        candidates.append({"dispositions": {a: {"status": "candidate_ready", "traces_with_feedback": 1} for a in passes},
                           "verifier": {"global_text": {"authorized": True}, "code_diag": {"authorized": True, "error_modes": {}}}})
    a = gf.analyze(spec, candidates, outcomes)
    by = {(c["treatment"], c["control"]): c for c in a["contrasts"]}
    assert by[("global_code", "global_text")]["supported"] is True and by[("global_code", "global_text")]["block_sign_flip"]["p_value"] == pytest.approx(2 / 64)
    assert by[("global_text", "scalar")]["block_sign_flip"]["p_value"] == pytest.approx(2 / 64) and by[("global_text", "scalar")]["supported"] is False
    assert by[("code_diag", "scalar")]["supported"] is False and by[("code_diag", "scalar")]["differences"] == [0] * 6


def _probe_dir(path, pool_path, partition, parent, *, runs=3, tamper=None):
    from scripts import weak_solver_probe as probe

    rows = probe.load_items("%s:%s" % (pool_path, partition))
    ids = [r["id"] for r in rows]
    config = {"version": probe.VERSION, "model": "glm-5.3", "benchmark": "officeqa", "runs": runs, "reasoning_effort": "low",
              "item_ids_hash": probe.digest(sorted(ids)), "items_hash": probe.digest(sorted(probe.digest(r) for r in rows)),
              "skills": {"parent": {"hash": probe.digest(parent), "bytes": len(parent)}}}
    path.mkdir(parents=True)
    (path / "config.json").write_text(json.dumps(config))
    records = []
    for i, item in enumerate(ids):
        for run in range(runs):
            status = "fail" if (i + run) % 3 == 0 else "pass"
            records.append({"skill": "parent", "item": item, "run": run, "status": status})
    if tamper == "duplicate":
        records[1] = dict(records[0])
    if tamper == "missing":
        records = records[:-1]
    for r in records:
        target = path / "records" / "parent" / ("%s.%d.json" % (probe.digest(r["item"])[:24], r["run"]))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(r))
    per = {"pass": sum(r["status"] == "pass" for r in records), "fail": sum(r["status"] == "fail" for r in records), "unknown": 0}
    (path / "summary.json").write_text(json.dumps({"status": "completed", "config_hash": probe.digest(config), "per_skill": {"parent": per}}))
    return path


def test_calibration_is_admitted_only_as_a_complete_inventory_of_the_exact_pool(tmp_path):
    panel, _ = _material()
    pool = tmp_path / "pool-D.json"
    pool.write_text(json.dumps({"tasks": [t for t in panel["tasks"] if t["task_id"].startswith("gD")]}))
    parent = "Read the table.\n"
    good = runner._calibration(_probe_dir(tmp_path / "ok", pool, "development", parent), pool, "development", parent)
    assert sum(k for _, k in good["counts"].values()) == 18 and len(good["inventory_hash"]) == 64
    assert runner.informative(good["counts"])  # the fixture fails some item in some run
    for tamper in ("duplicate", "missing"):
        with pytest.raises(ValueError):
            runner._calibration(_probe_dir(tmp_path / tamper, pool, "development", parent, tamper=tamper), pool, "development", parent)
    with pytest.raises(ValueError):  # another parent text
        runner._calibration(_probe_dir(tmp_path / "other", pool, "development", "Other.\n"), pool, "development", parent)
    with pytest.raises(ValueError):  # two runs instead of three
        runner._calibration(_probe_dir(tmp_path / "two", pool, "development", parent, runs=2), pool, "development", parent)
    changed = json.loads(pool.read_text())
    changed["tasks"][0]["public"]["question"] += " (changed)"
    pool.write_text(json.dumps(changed))
    with pytest.raises(ValueError):  # the pool's content changed after the calibration
        runner._calibration(tmp_path / "ok", pool, "development", parent)


def test_the_pooled_report_refuses_unfinished_and_duplicate_studies(tmp_path):
    panel, derivations = _material()
    spec = _spec(panel, derivations, blocks=1)
    gf.run_study(spec, panel, derivations, tmp_path / "a" / "study", fixture_api=GenAPI(), fixture_evaluate=host)
    (tmp_path / "b" / "study").mkdir(parents=True)
    (tmp_path / "b" / "study" / "protocol.json").write_text((tmp_path / "a" / "study" / "protocol.json").read_text())
    (tmp_path / "b" / "study" / "study.json").write_text((tmp_path / "a" / "study" / "study.json").read_text())
    with pytest.raises(ValueError):
        runner.report([str(tmp_path / "a"), str(tmp_path / "b")])  # b has no result
    with pytest.raises(ValueError):
        runner.report([str(tmp_path / "a"), str(tmp_path / "a")])  # the same sealed block twice
    assert "unknown bounds" in runner.report([str(tmp_path / "a")])


def test_the_leak_guard_covers_every_excerpt_a_note_can_show():
    long_quote = "| Net receipts of the fiscal year after refunds and transfers to trust funds, adjusted | 60,390 | 64,570 | 4,180 | 1,234 | 5,678 |"
    d = {**DERIVATION, "figures": [{**DERIVATION["figures"][0], "quote": long_quote}, DERIVATION["figures"][1]]}
    shown = " ".join(long_quote.split())[:110]
    assert gf.derivation_leak("Look at " + shown + " carefully", {"x": d})  # the displayed excerpt
    assert gf.derivation_leak("Look at " + shown[:40] + " carefully", {"x": d})  # a further cut excerpt
    assert not gf.derivation_leak("Read the receipts table carefully.", {"x": d})
    assert gf.significant_digits("0.005") == 1 and gf.significant_digits("0.0012") == 2 and gf.significant_digits("12.87") == 4
    assert not gf.derivation_leak("Allow a tolerance of 0.005.", {"x": {**DERIVATION, "answer": "0.005"}})


def test_neighbour_parsing_is_bounded():
    from skillopt.feedback_study import error_modes as em

    row = "| r | 31 |" + "|".join(" %d " % i for i in range(1000)) + "|"
    found = em._neighbours(row + "\n", {"name": "a", "value": "31", "quote": "| r | 31 |"})
    assert len(found) <= em.MAX_SUBSTITUTES
    huge = "| r | 31 | %s |\n| s | 3 | 0 |\n" % ("9" * 5000)
    deriv = {"figures": [{"name": "a", "value": "31", "quote": "| r | 31 |"}, {"name": "b", "value": "3", "quote": "| s | 3 | 0 |"}],
             "expression": "a / b", "decimals": 2, "answer": "10.33"}
    assert em.diagnose(deriv, huge, "<answer>5.00</answer>")["mode"] in ("unexplained", "neighbour_cell")


def test_only_validated_arithmetic_reaches_a_note():
    from scripts import generate_officeqa_diagnostic_tasks as gen2
    from skillopt.feedback_study import error_modes as em

    commented = "(b - a) / a * 100 # | 1957 | 71,029 | 69,433 | 1,596 |"
    assert gen2._ARITHMETIC.fullmatch("(b - a) / a * 100") and not gen2._ARITHMETIC.fullmatch(commented)
    # even a derivation that carried a comment renders the parsed expression only
    d = {**DERIVATION, "expression": commented}
    note = em.render(d, em.diagnose(d, TABLE, "<answer>0.1287</answer>"), 1800)
    assert "1957" not in note and "(b - a) / a * 100" in note
    assert gf.derivation_leak("Use (b - a) / a * 100 for growth", {"x": DERIVATION})


def test_canonical_keeps_the_exact_spelling_and_the_judge_never_sees_a_derivation(tmp_path):
    from skillopt.feedback_study import error_modes as em

    exact = "a + 999999999999999.99 - 999999999999999"
    assert em.canonical(exact) == exact and em.canonical(exact + " # | 1957 | 71,029 |") == exact
    assert em.canonical("# only a comment") == "(the derivation's expression)"
    panel, derivations = _material()
    api = GenAPI()
    gf.run_study(_spec(panel, derivations, blocks=1), panel, derivations, tmp_path / "study", fixture_api=api, fixture_evaluate=host)
    assert api.prompts["verifier"] and not any("(b - a) / a * 100" in p or "expected 12.87" in p for p in api.prompts["verifier"])
    assert not any("(b - a) / a * 100" in p for p in api.prompts["solver"])
