"""Batch 3: the run's report (registration §12; v2: delta §9; v3: delta §1, §7, §9) -- read only from the sealed
records of the chains that ended; the main table's counts with reused records, v3's registered readings (the deepseek
family: I-ds primary, E-ds secondary, the NoSkill-ds reference at stage 0 only; no baseline test), every stage's update
and the examiner's description -- the self-test's plan, the gate's funnel, each code's check-half support, an untestable
ALFWorld stage -- and the deepseek solver's tokens beside GLM-5.3's; zero calls. The fixture runs have v3's shape:
every chain its own stage 0, no baseline."""
from __future__ import annotations

import functools
import json

import pytest

from scripts import run_coevo5
from skillopt.coevo5 import evaluation, readout, report
from skillopt.coevo5.protocol import ORDER, VERSION
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import write_json

RUN = "run-1"
RESAMPLES = 200
ITEMS = {b: ["%s-%d" % (b, i) for i in range(6)] for b in ORDER}
SOURCES = {"officeqa-0": ["a.json"], "officeqa-1": ["a.json"], "officeqa-2": ["b.json", "c.json"],
           "officeqa-3": ["c.json"], "officeqa-4": ["d.json"], "officeqa-5": []}
SPECIAL = {("E-ds", 1, "searchqa", "searchqa-5"): ("fail", "noncompletion", "pass"),  # backend passed a blank reply
           ("I-ds", 3, "livemath", "livemath-5"): ("unknown", "infrastructure", None)}
ACCEPTED = {1: [("r1", "similar"), ("r2", "local")], 2: [("r3", "local")], 5: [("r4", "local")]}


def _passes(chain, stage, bench):
    learned = stage >= ORDER.index(bench) + 1
    return {"E-ds": 2 + 2 * learned, "NoSkill-ds": 1, "I-ds": 3 + learned}[chain]


def _tokens(chain, stage, bench):
    n = _passes(chain, stage, bench)
    out = {}
    for i, task_id in enumerate(ITEMS[bench]):
        token = "pass" if i < n else "fail"
        out[task_id] = SPECIAL.get((chain, stage, bench, task_id), (token, "answer", token))
    return out


def _unit(root, run, chain, stage, bench):
    unit_root = root / chain / ("s%d" % stage) / "evaluation" / bench
    unit = "%s/s%d/evaluation/%s" % (chain, stage, bench)
    for task_id, (token, kind, official) in _tokens(chain, stage, bench).items():
        write_json(unit_root / "attempt-1" / "cells" / ("c-%s.json" % task_id),
                   seal({"cell": {"task_id": task_id}, "final": {"token": token, "kind": kind},
                         "official": None if official is None else {"status": official}}))
    record = seal({"version": VERSION + "-evaluation", "run": run, "unit": unit, "chain": chain, "stage": stage,
                   "benchmark": bench, "config": {}, "skill_sha256": "%s-%d" % (chain, stage), "status": "complete",
                   "attempt": "attempt-1", "counts": {}, "cells": ["c-" + t for t in ITEMS[bench]]})
    write_json(unit_root / "unit.json", record)
    return unit_root, record


def _reused(root, run, chain, stage, bench, source_root, source):
    unit_root = root / chain / ("s%d" % stage) / "evaluation" / bench
    write_json(unit_root / "unit.json", seal({
        "version": VERSION + "-evaluation", "run": run, "unit": "%s/s%d/evaluation/%s" % (chain, stage, bench),
        "chain": chain, "stage": stage, "benchmark": bench, "config": {}, "skill_sha256": source["skill_sha256"],
        "status": "reused", "from": source["record_hash"], "from_root": str(source_root), "attempt": "attempt-1",
        "counts": {}}))


def _step_unit(root, run, chain, stage, kind, result, files=None):
    unit_root = root / chain / ("s%d" % stage) / kind
    for name, value in (files or {}).items():
        write_json(unit_root / "attempt-1" / name, value)
    write_json(unit_root / "unit.json", seal({"version": VERSION + "-unit", "run": run,
                                              "identity": {"unit": "%s/s%d/%s" % (chain, stage, kind)},
                                              "status": "complete", "attempt": "attempt-1", "result": result}))


RESEARCHED = [
    {"id": "r1", "original": "old text", "rewrite": "rewritten", "status": "kept", "text": "new text", "questions": [
        {"question": "q1", "status": "found", "log": [{"round": 1, "conclusion": {"status": "found"},
                                                      "void": "quote_not_verbatim"},
                                                     {"round": 2, "conclusion": {"status": "found"}}]},
        {"question": "q2", "status": "not_dispatched"}]},
    {"id": "r2", "original": "t2", "rewrite": None, "status": "kept", "text": "t2", "questions": [
        {"question": "q3", "status": "none", "log": [{"round": 1, "conclusion": None},
                                                     {"round": 2, "conclusion": {"status": "none"}}]}]},
    {"id": "r9", "original": "t9", "rewrite": None, "status": "dropped_pre_dispatch", "questions": []}]
PREPARED = {"status": "prepared",
            "revision": {"status": "accepted", "accepted": True, "balanced_accuracy": {"old": "3/5", "new": "4/5"},
                         "correct": {"old": 6, "new": 8}, "invalid": {"old": 1, "new": 0}},
            "halves": {"proposal": ["searchqa/b"], "check": ["searchqa/a", "searchqa/c", "searchqa/d", "searchqa/e",
                                                              "searchqa/f"]},
            "rules": [{"id": "r1", "status": "supported", "forward": {}}, {"id": "r2", "status": "supported", "forward": {}},
                      {"id": "r9", "status": "dropped_pre_dispatch"}, {"id": "r10", "status": "supported", "forward": {}}]}
# v3 §7: the self-test's plan -- r2 revised and passed, r10 dropped by its revision; r1's forward panel built after it
SELFTESTED = {**PREPARED, "status": "selftested", "supported": ["r1", "r2"],
              "rules": [{"id": "r1", "status": "supported", "forward": {
                  "officeqa": {"status": "ok", "counts": {"generated": 10, "valid": 8}, "items": []}}},
                  {"id": "r2", "status": "supported", "forward": {}, "before_selftest": "t2 before"},
                  {"id": "r9", "status": "dropped_pre_dispatch"}, {"id": "r10", "status": "selftest_dropped"}],
              "selftest": {"r1": {"round1": {"passed": True}},
                           "r2": {"round1": {"passed": False}, "revision": "revised", "round2": {"passed": True}},
                           "r10": {"round1": {"passed": False}, "revision": "dropped"},
                           "_revision": {"status": "valid", "dropped": [], "omitted_tasks": 0}}}
UNTESTABLE = {"status": "prepared", "halves": {"proposal": [], "check": []},
              "rules": [{"id": "r1", "status": "insufficient_support"}, {"id": "r2", "status": "insufficient_support"}]}
TRAINED = {"cells": {"searchqa/a": ["c0", "c2"], "searchqa/b": ["c1"], "searchqa/c": ["c3"], "searchqa/d": ["c4"],
                     "searchqa/e": ["c5"], "searchqa/f": ["c6"]}, "tokens": {}}
DIAGNOSED = {"c0": {"code": "D1"}, "c2": {"code": "D1"}, "c1": {"code": "D1"}, "c3": {"code": "D1"},  # c1: proposal
             "c4": {"code": "D1"}, "c5": {"code": "D2"}, "c6": {"code": "D1"}}
SCREENED = {"r1:similar": {"status": "pass"}, "r1:local": {"status": "fail"}, "r2:local": {"status": "pass"}}
CONFIRMED = {"r1:similar": {"status": "pass"}, "r2:local": {"status": "pass"}}


def _run(root, run=RUN, *, ended=None, last=None, registry=True):
    """Every chain's evaluation units (its own stage 0 -- the reference's only one; E-ds' stage-2 SearchQA unit
    reused for an unchanged Skill), its merges, I-ds' stage-1 train, prepare, selftest, screen and confirm units and
    its stage-5 (ALFWorld) prepare unit whose proposals all lacked support.
    ``ended``: {chain: "complete" | "terminated"} (default: all complete); ``last``: {chain: its last evaluated
    stage}."""
    ended = {name: "complete" for name in readout.CHAIN_NAMES} if ended is None else ended
    for name in readout.CHAIN_NAMES:
        previous = None
        for stage in range((last or {}).get(name, 0 if name == readout.REFERENCE else 5) + 1):
            for bench in ORDER:
                if (name, stage, bench) == ("E-ds", 2, "searchqa"):
                    _reused(root, run, name, 2, bench, *previous)
                else:
                    unit = _unit(root, run, name, stage, bench)
                    previous = unit if bench == "searchqa" else previous
            if stage == 0:
                continue
            _step_unit(root, run, name, stage, "merge",
                       {"accepted": [{"id": i, "placement": p} for i, p in ACCEPTED.get(stage, [])]})
        if name in ended:
            write_json(root / name / ("chain-%s.json" % ended[name]), seal({"identity": {"run": run, "chain": name}}))
    _step_unit(root, run, "I-ds", 1, "train", TRAINED)
    _step_unit(root, run, "I-ds", 1, "prepare", PREPARED,
               {"revision.json": {"panel": ["k%d" % i for i in range(10)]}, "research.json": RESEARCHED,
                "diagnoses.json": DIAGNOSED})
    _step_unit(root, run, "I-ds", 1, "selftest", SELFTESTED)
    _step_unit(root, run, "I-ds", 1, "screen", {"verdicts": SCREENED})
    _step_unit(root, run, "I-ds", 1, "confirm", {"verdicts": CONFIRMED})
    if (last or {}).get("I-ds", 5) == 5:
        _step_unit(root, run, "I-ds", 5, "prepare", UNTESTABLE)
    if registry:
        write_json(root / "shared" / "test" / "officeqa.json", seal({
            "version": VERSION + "-test-panel", "entry": {"run": run, "benchmark": "officeqa", "panel_hash": "h",
                                                         "tasks": ITEMS["officeqa"], "excluded_without_pages": [],
                                                         "source_files": SOURCES}}))


def _build(root, run=RUN):
    return report.build(report.Run(run, root), resamples=RESAMPLES)


def test_the_report_reads_every_ended_chain(tmp_path):
    _run(tmp_path)
    built = _build(tmp_path)
    assert built["chains"] == {name: "complete" for name in readout.CHAIN_NAMES}
    e = built["tables"]["E-ds"]
    assert sorted(e) == ["0", "1", "2", "3", "4", "5"]
    assert e["1"]["searchqa"] == {"correct": 4, "total": 6, "incomplete": 1, "unknown": 0, "unknown_kinds": {},
                                  "official_pass": 5, "official_known": 6, "reused": None}
    assert e["2"]["searchqa"] == {**e["1"]["searchqa"], "reused": "E-ds/s1/evaluation/searchqa"}
    assert e["0"]["alfworld"]["reused"] is None  # every chain evaluates its own stage 0
    assert sorted(built["tables"]["NoSkill-ds"]) == ["0"] and built["tables"]["NoSkill-ds"]["0"]["officeqa"][
        "correct"] == 1
    assert built["tables"]["I-ds"]["3"]["livemath"] == {"correct": 4, "total": 6, "incomplete": 0, "unknown": 1,
                                                        "unknown_kinds": {"infrastructure": 1}, "official_pass": 4,
                                                        "official_known": 5, "reused": None}
    assert built["updates"]["I-ds"]["1"] == {"local": 1, "similar": 1}
    assert built["updates"]["I-ds"]["3"] == {"local": 0, "similar": 0} and "NoSkill-ds" not in built["updates"]
    readings = built["readings"]
    primary = readings["primary"]  # v3: I-ds beyond its instructions
    assert (primary["chain"], primary["kind"]) == ("I-ds", "exceeds_instructions")
    assert primary["reading"]["known"]["estimate"] == pytest.approx(100 / 6)
    assert primary["reading"]["known"]["resamples"] == RESAMPLES
    assert primary["status"] == {"method_moved": True, "stages_with_accepted_rules": 3, "verdict": True}
    secondary = readings["secondary"]
    assert secondary["gain"]["reading"]["known"]["estimate"] == pytest.approx(100 * 2 / 6)  # E-ds' learning gain
    assert secondary["scaffold"]["known"]["estimate"] == pytest.approx(100 / 6)
    assert secondary["scaffold_reaches_instructions"]["verdict"] == "not_worse"
    assert readings["chains"]["NoSkill-ds"]["macro"]["0"]["known"]["estimate"] == pytest.approx(100 / 6)
    assert readings["transfer"]["Q1"] is True and readings["transfer"]["Q2"] is False
    assert readings["transfer"]["similar_placement_used"] is True
    assert readings["chains"]["E-ds"]["macro"]["0"]["known"]["estimate"] == pytest.approx(100 * 2 / 6)
    stage = built["examiner"]["I-ds"]["1"]  # the fates after the self-test
    assert stage["revision"]["panel"] == 10 and stage["untestable"] is False
    assert stage["rules"] == {"supported": 2, "dropped_pre_dispatch": 1, "selftest_dropped": 1}
    assert stage["selftest"] == {"tested": 3, "round1_passed": 1, "reply": "valid",
                                 "revisions": {"dropped": 1, "revised": 1}, "round2_passed": 1}
    assert stage["gate"] == {"entered": 2, "screen": 2, "confirm": 2, "accepted": 2}
    assert stage["support"] == {"codes": {"D1": 4, "D2": 1}, "reaching": 1}  # item a twice, b in the proposal half
    assert stage["forward"] == [{"rule": "r1", "target": "officeqa", "status": "ok", "generated": 10, "valid": 8}]
    assert stage["research"] == {"rules": 3, "requests": 2, "found": 1, "claimed": 2, "verbatim": 1,
                                 "rewrites": [{"rule": "r1", "status": "rewritten", "before": "old text",
                                               "after": "new text"}]}
    assert built["examiner"]["I-ds"]["5"]["untestable"] is True  # every ALFWorld proposal lacked support
    assert set(built["examiner"]) == {"I-ds"}  # E-ds' prepare units are absent here; the reference learns nothing
    assert "NoSkill-ds" not in built["accounting"]
    text = report.markdown(built)
    assert "### E-ds（完成）" in text and "| 1 | 4 / 6（1，0） | 2 / 6（0，0） |" in text
    assert "| 1 / 1 |" in text and "### NoSkill-ds（完成）" in text and "| P1" not in text and "主张 1" not in text
    assert "第 3 版登记 §1：deepseek 一族，I-ds 为主" in text
    assert "- 方法有没有动（至少 2 步收下过规则）：成立（3 步）" in text
    assert "超过指令 M_I-ds[5] − M_I-ds[0]（第 0 步是五份任务说明指令；L > 0 记“超过”，否则“未建立”）：%s，超过" % (
        report._interval(primary["reading"])) in text
    assert "学习增益 M_E-ds[5] − M_E-ds[0]（第 0 步是空架子；固定架子之上的增量变化，L > 0 才算成立）：%s，成立" % (
        report._interval(secondary["gain"]["reading"])) in text
    assert "M_E-ds[0] − M_NoSkill-ds[0]：%s" % report._interval(secondary["scaffold"]) in text
    assert "自测：3 条，第 1 轮过 1 条；修改回复 valid（dropped 1，revised 1）；第 2 轮过 1 条" in text
    assert "可检验的触发题不足，无法检验" in text
    assert "相似 T_sim（L > 0） | +0.0（L +0.0；[+0.0, +0.0]）" in text
    assert "门的漏斗：进门 2，过初筛 2，过复核 2，收下 2" in text
    assert "检验半里各代码失败的不同题数（够 4 道的代码 1 个）：D1 4、D2 1" in text
    assert "挑选用：面板 10 题，平衡准确率 60.0% → 80.0%，判对 6 → 8，不合法 1 → 0" in text
    assert '改写前："old text"' in text and '改写后："new text"' in text
    assert "改写尝试 1 次（改了 1，原样 0，失败 0）" in text and "未知记录的类别：第 3 步 LiveMath：infrastructure 1" in text


def test_officeqa_items_that_share_a_source_file_are_resampled_together(tmp_path):
    _run(tmp_path)
    units, _ = report.load(report.Run(RUN, tmp_path))
    panels = report.panels(report.Run(RUN, tmp_path), units)
    assert panels["officeqa"].groups == (0, 0, 1, 1, 2, 3) and panels["searchqa"].groups == (0, 1, 2, 3, 4, 5)
    with pytest.raises(ValueError, match="registry"):  # every item named by this run's registry
        report.panels(report.Run("another-run", tmp_path), units)


def test_scores_stay_sealed_until_a_chain_ends(tmp_path):
    _run(tmp_path, ended={})
    built = _build(tmp_path)
    assert built["chains"] == {name: None for name in readout.CHAIN_NAMES}
    assert built["tables"] == {} and built["updates"] == {} and built["examiner"] == {} and built["readings"] is None
    text = report.markdown(built)
    assert "E-ds 未结束（成绩仍封存）" in text and "所有读数都无法评估" in text and "4 / 6" not in text


def test_a_chain_that_ended_early_leaves_its_missing_readings_not_assessable(tmp_path):
    _run(tmp_path, ended={"I-ds": "terminated", "NoSkill-ds": "complete"}, last={"I-ds": 2})
    built = _build(tmp_path)
    assert built["chains"]["I-ds"] == "terminated" and built["chains"]["E-ds"] is None
    assert sorted(built["tables"]["I-ds"]) == ["0", "1", "2"] and "E-ds" not in built["tables"]
    primary = built["readings"]["primary"]
    assert primary["reading"]["available"] is False and "I-ds/s5/searchqa" in primary["reading"]["missing"]
    assert primary["status"]["verdict"] is None
    assert built["readings"]["secondary"]["scaffold_reaches_instructions"]["verdict"] is None  # E-ds never ended
    assert built["readings"]["updates"]["I-ds"]["moved"] is True  # two stages with rules before it stopped
    text = report.markdown(built)
    assert "### I-ds（链未完成（已终止））" in text and "E-ds 未结束（成绩仍封存）" in text
    assert "- 超过指令 M_I-ds[5] − M_I-ds[0]（第 0 步是五份任务说明指令；L > 0 记“超过”，否则“未建立”）：无法评估，无法评估" in text


def test_a_bench_without_records_leaves_every_reading_not_assessable(tmp_path):
    _run(tmp_path)
    for chain in readout.CHAIN_NAMES:  # no unit of any ended chain holds an ALFWorld record
        for path in sorted(tmp_path.glob("%s/s*/evaluation/alfworld/unit.json" % chain)):
            path.unlink()
    built = _build(tmp_path)
    assert built["readings"] is None and built["tables"]["E-ds"]["5"].keys() == set(ORDER) - {"alfworld"}
    assert "| — |" in report.markdown(built)


def test_records_of_another_run_or_other_items_are_refused(tmp_path):
    _run(tmp_path, registry=False)
    with pytest.raises(ValueError, match="another run"):  # the chain markers name this run
        report.build(report.Run("another-run", tmp_path), resamples=RESAMPLES)
    with pytest.raises(FileNotFoundError):  # OfficeQA's resampling groups come from the run's test registry
        _build(tmp_path)
    other = tmp_path / "other"
    _run(other)
    path = other / "E-ds" / "s3" / "evaluation" / "alfworld" / "unit.json"
    record = json.loads(path.read_text())
    path.unlink()
    record = {k: v for k, v in record.items() if k != "record_hash"}
    write_json(path, seal({**record, "cells": record["cells"][:5]}))
    with pytest.raises(ValueError, match="different test items"):
        _build(other)


def test_the_denominators_attempts_deviations_and_costs_are_reported(tmp_path):
    """§2.1, §2.2, §10, §13.4: the test panels with their exclusions; a redone unit with the owner's decision; the
    ledger's spending, a raised cap and a halt; and per stage the labelled items, generated items and calls."""
    from skillopt.coevo5 import chain
    from skillopt.coevo5.budget import Budget, deepseek_scope, step_scope

    _run(tmp_path)
    test = tmp_path / "shared" / "test"
    write_json(test / "spreadsheetbench.json", seal({"version": VERSION + "-test-panel", "entry": {
        "run": RUN, "benchmark": "spreadsheetbench", "panel_hash": "h", "tasks": ["s%d" % i for i in range(279)],
        "excluded_without_pages": [], "source_files": {}}}))
    record = seal({"version": VERSION + "-sheet-qualification", "side": "test", "tasks": 279, "model_calls": 0,
                   "qualified": ["s%d" % i for i in range(200)],
                   "excluded": {**{"s%d" % i: "reference_mismatch" for i in range(200, 270)},
                                **{"s%d" % i: "scorer_error" for i in range(270, 279)}}})
    write_json(test / "spreadsheetbench-qualification" / "attempt-1" / "qualification.json", record)
    write_json(test / "spreadsheetbench-qualification.json", seal({"attempt": "attempt-1",
                                                                   "qualification_hash": record["record_hash"]}))
    unit = tmp_path / "I-ds" / "s2" / "screen"  # paused once, redone on the owner's decision
    write_json(unit / "attempt-1" / "status.json", seal({"status": "paused", "kind": "infrastructure_incomplete",
                                                         "reason": "parent_unknown_share", "cell": None}))
    write_json(unit / "attempt-1" / "recovery.json", {"by": "owner", "date": "2026-10-20", "decision": "redo it"})
    _step_unit(tmp_path, RUN, "I-ds", 2, "screen", {"verdicts": {}}, {})
    record = json.loads((unit / "unit.json").read_text())
    (unit / "unit.json").unlink()
    write_json(unit / "unit.json", seal({**{k: v for k, v in record.items() if k != "record_hash"},
                                         "attempt": "attempt-2"}))
    (unit / "attempt-2").mkdir()
    for n, item in enumerate(("searchqa/a", "searchqa/b", "searchqa/a", "fwd:r1:officeqa:1")):
        write_json(tmp_path / "I-ds" / "s1" / "train" / "attempt-1" / "cells" / ("c%d.json" % n),
                   seal({"cell": {"task_id": item}, "final": {"token": "pass", "kind": "answer"}}))
    budget = Budget(tmp_path / "shared" / "ledger", poll=0)
    budget.declare(chain.caps("I-ds"))
    scopes = ("overall", "chain:I-ds", step_scope("I-ds", 1, "learning"))
    budget.settle(budget.reserve(scopes, 1000, label="I-ds/s1/prepare", generation=0), 700, detail={})
    for kind, spent in (("learning", 4000), ("evaluation", 3000)):  # v3 §9: the deepseek solver's own scopes
        budget.settle(budget.reserve(chain.deepseek_scopes("I-ds", 1, kind), 5000, label="I-ds/s1/" + kind,
                                     generation=0), spent, detail={})
    budget.raise_cap(step_scope("I-ds", 1, "learning"), 12_000_000, deviation="the owner raised it: 10/20")
    budget.halt("ledger_failure:OSError", label="I-ds/s1/prepare")
    budget.resume(decision="reconciled")
    (tmp_path / "shared" / "ledger" / "events.jsonl").open("ab").write(b'{"event": "reserve", "torn')
    built = report.build(report.Run(RUN, tmp_path), resamples=RESAMPLES,
                         supply={b: {"pool": 10 * (k + 1), "regression": k} for k, b in enumerate(ORDER)})
    assert built["test_panels"]["spreadsheetbench"] == {
        "registered": 279, "tasks": 279, "excluded_without_pages": 0,
        "qualification": {"side": "test", "items": 279, "qualified": 200,
                          "excluded": {"reference_mismatch": 70, "scorer_error": 9}}}
    assert built["redone"] == [{"unit": "I-ds/s2/screen", "attempts": [
        {"attempt": "attempt-1", "status": "infrastructure_incomplete:parent_unknown_share",
         "decision": {"by": "owner", "date": "2026-10-20", "decision": "redo it"}},
        {"attempt": "attempt-2", "status": "complete", "decision": None}]}]
    spent = built["spending"]
    assert spent["scopes"][step_scope("I-ds", 1, "learning")] == {"declared": 10_000_000, "cap": 12_000_000,
                                                                  "settled": 700, "open": 0, "calls": 1}
    assert spent["scopes"][deepseek_scope()]["settled"] == 7000 and spent["scopes"]["overall"]["settled"] == 700
    assert spent["raises"] == [{"scope": step_scope("I-ds", 1, "learning"), "from": 10_000_000, "cap": 12_000_000,
                                "deviation": "the owner raised it: 10/20"}]
    assert spent["halts"] == [{"reason": "ledger_failure:OSError", "label": "I-ds/s1/prepare"}]
    assert spent["resumes"] == ["reconciled"] and spent["halted"] is None
    row = built["accounting"]["I-ds"]["1"]  # the self-test's plan holds r1's forward panel (10 items listed: none)
    assert row == {"available": {"pool": 10, "regression": 0}, "used": 2, "generated": 0, "cells": 4,
                   "learning": {"calls": 1, "tokens": 700}, "evaluation": None,
                   "deepseek_learning": {"calls": 1, "tokens": 4000}, "deepseek_evaluation": {"calls": 1, "tokens": 3000}}
    text = report.markdown(built)
    assert "SpreadsheetBench：登记 279 题，评测面板 279 题；测试侧资格检查 279 题中合格 200 题（分母），不合格原因：" \
        "reference_mismatch 70、scorer_error 9" in text
    assert "协议偏离（提高上限）：step:I-ds:1:learning 从 10,000,000 提到 12,000,000，理由：the owner raised it: 10/20" \
        in text
    assert "- I-ds/s2/screen：attempt-1 infrastructure_incomplete:parent_unknown_share，负责人决定（2026-10-20）：" \
        "redo it；attempt-2 complete" in text
    assert "| 1 SearchQA | 10 + 0 | 2 | 0 | 4 | 1 / 700 | — | 1 / 4,000 | 1 / 3,000 |" in text
    assert "- deepseek-v4-flash（做题模型）总花费：7,000 tokens，上限 430,000,000" in text
    assert "  - I-ds：7,000 tokens，上限 200,000,000" in text


def test_the_report_is_never_written_into_the_run(tmp_path, monkeypatch):
    root = tmp_path / "run"
    value = seal({"version": VERSION + "-manifest", "root": str(root), "code": {}})
    write_json(tmp_path / "manifest.json", value)
    _run(root, value["record_hash"])
    monkeypatch.setattr(report, "build", functools.partial(report.build, resamples=RESAMPLES))
    (tmp_path / "link").symlink_to(root)
    for out in (root / "reports", tmp_path / "link" / "reports"):
        with pytest.raises(ValueError, match="never written into the run"):
            run_coevo5.main(["report", "--manifest", str(tmp_path / "manifest.json"), "--out", str(out)])
    assert not (root / "reports").exists()


def test_the_command_writes_the_report_to_a_new_directory(tmp_path, monkeypatch):
    root = tmp_path / "run"
    value = seal({"version": VERSION + "-manifest", "root": str(root), "code": {}})
    write_json(tmp_path / "manifest.json", value)
    _run(root, value["record_hash"])
    monkeypatch.setattr(report, "build", functools.partial(report.build, resamples=RESAMPLES))
    out = tmp_path / "report"
    assert run_coevo5.main(["report", "--manifest", str(tmp_path / "manifest.json"), "--out", str(out)]) == 0
    built = json.loads((out / "report.json").read_text())
    assert built["run"] == value["record_hash"] and built["code"]["matches_manifest"] is False  # nothing pinned here
    assert built["readings"]["primary"]["status"]["verdict"] is True
    text = (out / "report.md").read_text()
    assert text.startswith("# coevo5 运行报告") and "代码：与启动清单不一致" in text
    with pytest.raises(ValueError, match="new directory"):
        run_coevo5.main(["report", "--manifest", str(tmp_path / "manifest.json"), "--out", str(out)])
