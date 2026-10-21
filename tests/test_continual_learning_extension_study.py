"""The extension study: LiveMath data layout, the derived study protocol, its split, and the tools on top."""
import hashlib
import json
from copy import deepcopy

import pytest

from scripts import make_extension_study as ext
from scripts import run_active_evidence_panel_eval as panel_eval
from scripts import run_fivebench_g_stage as tool
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends, datasets
from skillopt.continual_eval.core import read_json, write_json
from tests.test_continual_learning_domains import setup
from tests.test_continual_learning_livemath_pilot import _upstream


def _base(tmp_path):
    """A study-F-shaped protocol without references (nothing to check in an evaluation source). The model record
    is a natural one: the builders' panels are imported data (provenance "natural"); nothing here makes a call."""
    _, _, args = setup("searchqa", natural=True)
    model = args["model"]
    model["transport"]["stream_wall_seconds"] = 3600
    model["max_tokens"] = tool.BUDGET_V11["solver_max_tokens"]
    root = tmp_path / "F"
    protocol = seal({"version": tool._sequence().BUDGET_SEQUENCE, "root": str(root), "references": {}, "model": model,
                     "learning_model_service": {"fixture": True}, "learning_client_options": {"x": 1}, "order": [],
                     "roles": {}, "files": {},
                     "config": {"native_lock": str(tmp_path / "lock"),
                                "learning_recovery_policy": {"skill_budget_bytes": 32000}, "workers": 8}})
    write_json(root / "protocol.json", protocol)
    return root, protocol


def _built(tmp_path, monkeypatch):
    up, ids = _upstream(tmp_path, per=7)  # months 202602 (the paper's split), 202603, 202604; seven items each
    monkeypatch.setattr(ext, "PILOT_PER_MONTH", 2)
    monkeypatch.setitem(ext.LAYOUTS, "livemath", lambda u, s, seed: ext.layout_livemath(u, s, seed, val=4))
    monkeypatch.setattr(tool, "_outside", lambda out, root, protocol, extra=(): None)
    layout = ext.data("livemath", str(up), str(ids), str(tmp_path / "lm"), revision="r" * 40)
    base, _ = _base(tmp_path)
    protocol = ext.study(str(base), [str(tmp_path / "lm")], str(tmp_path / "X"))
    split = ext.split(str(tmp_path / "X"), str(tmp_path / "split.json"))
    return layout, protocol, split


def test_layout_keeps_the_test_part_as_ids_and_the_evaluation_blocks_outside_the_split(tmp_path, monkeypatch):
    layout, protocol, split = _built(tmp_path, monkeypatch)
    assert layout["counts"] == {"train": 12, "val": 4, "eval": 4, "test": 1}  # 21 items: 1 test, 4 pilot, 16 rest
    assert [e["task_id"] for e in layout["parts"]["test"]] == ["202602:1"]
    written = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "lm").rglob("*.json") if p.name != "layout.json")
    assert "object 202602-1?" not in written and "SECRET" not in written  # the test item is never rendered
    dev, val = read_json(tmp_path / "lm/dev_panel.json"), read_json(tmp_path / "lm/val_panel.json")
    assert dev["benchmark"] == "livemath" and {t["partition"] for t in dev["tasks"]} == {"development"}
    assert {t["partition"] for t in val["tasks"]} == {"skill_confirmation"} and len(val["tasks"]) == 4
    task = dev["tasks"][0]
    assert set(task["public"]) == {"question", "choices"} and task["private"]["answer"] in "ABCDE"
    assert task["family_id"] == "livemath:" + task["task_id"]
    assert "right option" in task["public"]["choices"].split("\n\n")["ABCDE".index(task["private"]["answer"])]
    blocks = layout["evaluation_blocks"]
    rows = json.loads((tmp_path / "lm/eval_blocks/block_e01/items.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in rows] == blocks["items"] and set(rows[0]) == {"id", "question", "choices", "answer"}
    assert all(i.split(":")[0] in {"202603", "202604"} for i in blocks["items"])  # the pilot's months only
    in_split = {e["task_id"] for part in ("train", "val", "test") for e in split["splits"]["livemath"][part]}
    assert not in_split & set(blocks["items"]) and len(in_split) == 17
    assert split["version"] == tool.EXTENSION_SPLIT and split["splits"]["livemath"]["reserve"] == []
    assert split["f_study_usage"]["livemath"]["protocol_hash"] == protocol["record_hash"]
    with pytest.raises(ValueError, match="new directory"):
        ext.data("livemath", str(tmp_path / "up"), str(tmp_path / "ids"), str(tmp_path / "lm"), revision="r" * 40)


def test_the_extension_study_carries_study_f_verbatim_and_is_reverified(tmp_path, monkeypatch):
    _, protocol, split = _built(tmp_path, monkeypatch)
    base = read_json(tmp_path / "F/protocol.json", sealed=True)
    assert protocol["version"] == tool.EXTENSION_STUDY and protocol["order"] == ["livemath"]
    assert protocol["model"] == base["model"] and protocol["learning_client_options"] == {"x": 1}
    assert protocol["config"] == {"native_lock": base["config"]["native_lock"],
                                  "learning_recovery_policy": {"skill_budget_bytes": 32000}}
    assert protocol["derived_from"]["protocol_hash"] == base["record_hash"] and protocol["references"] == {}
    root, loaded = tool._study(str(tmp_path / "X"))
    assert loaded == protocol and tool.dev_panel_path(loaded, "livemath") == str(tmp_path / "lm/dev_panel.json")
    tool.check_split(split, loaded, "livemath")
    with pytest.raises(ValueError, match="not verified"):  # the five-benchmark split version does not fit
        tool.check_split({**split, "version": tool.SPLIT_VERSION}, loaded, "livemath")
    # a changed development panel, or a study F that changed, is refused
    panel = tmp_path / "lm/dev_panel.json"
    original = panel.read_text(encoding="utf-8")
    panel.write_text(original + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen input"):
        tool.dev_panel_path(loaded, "livemath")
    panel.write_text(original, encoding="utf-8")
    (tmp_path / "F/protocol.json").write_text(json.dumps(seal({**{k: v for k, v in base.items() if k != "record_hash"},
                                                                "learning_model_service": {"fixture": False}})),
                                              encoding="utf-8")
    with pytest.raises(ValueError, match="no longer matches"):
        tool._study(str(tmp_path / "X"))


def test_stage_preparation_for_the_three_learners_and_a_panel_evaluation(tmp_path, monkeypatch):
    layout, protocol, split = _built(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "TRAIN", {**tool.TRAIN, "livemath": {"families": 6}})
    where = (str(tmp_path / "X"), str(tmp_path / "split.json"))
    common = dict(benchmark="livemath", parent="none", seed=3)
    v9 = tool.prepare(*where, str(tmp_path / "s9"), str(tmp_path), val_source=str(tmp_path / "lm/val_panel.json"),
                      method="skillopt", learning_version="v9", **common)
    v10 = tool.prepare(*where, str(tmp_path / "s10"), str(tmp_path), val_source=str(tmp_path / "lm/val_panel.json"),
                       method="rubric_research", learning_version="v10", **common)
    v11 = tool.prepare(*where, str(tmp_path / "s11"), str(tmp_path), val_source=None, method=tool.ACTIVE_EVIDENCE,
                       learning_version="v11", arms={"feedback": "scalar", "post_update": "none"}, **common)
    assert v9["train_tasks"] == v10["train_tasks"] == 6 and v9["selection_tasks"] == 4
    assert v11["benchmark"] == "livemath" and v9["selection_source"] == "canonical_validation_partition"
    for name in ("s9", "s10", "s11"):
        assert tool._load(str(tmp_path / name))[1]["benchmark"] == "livemath"
    # in an extension study the gated learners may start from a fixed initial instruction (no chains, no test cells)
    (tmp_path / "b.md").write_text("Compare every option with the hypotheses.\n", encoding="utf-8")
    fixed = tool.prepare(*where, str(tmp_path / "s10b"), str(tmp_path), val_source=str(tmp_path / "lm/val_panel.json"),
                         method="rubric_research", learning_version="v10", benchmark="livemath",
                         parent="f:" + str(tmp_path / "b.md"), seed=3)
    assert fixed["parent_action"] == "fixed_text" and fixed["selection_source"] == "canonical_validation_partition"
    assert read_json(tmp_path / "s10b/manifest.json", sealed=True)["parent_skill"].startswith("Compare every option")
    with pytest.raises(ValueError, match="fixed-text parent"):  # not for learning v8
        tool.prepare(*where, str(tmp_path / "s8b"), str(tmp_path), val_source=str(tmp_path / "lm/val_panel.json"),
                     method="skillopt", learning_version="v8", benchmark="livemath",
                     parent="f:" + str(tmp_path / "b.md"), seed=3)
    # learning v11 implements only pass/fail feedback without a post-update step here: the tool's default arms
    # (diagnosis) are refused at preparation, before any call
    with pytest.raises(ValueError, match="not implemented for the benchmark"):
        tool.prepare(*where, str(tmp_path / "s11d"), str(tmp_path), val_source=None, method=tool.ACTIVE_EVIDENCE,
                     learning_version="v11", **common)
    with pytest.raises(ValueError, match="no test cells"):
        tool.test(str(tmp_path / "s9"), str(tmp_path / "unused"))
    # labelled feedback and labels for the leak check come from the private answer letter
    from skillopt.continual_learning import feedback, skillopt
    task = read_json(tmp_path / "s9/panel.json")["tasks"][0]
    assert feedback.expected_text("livemath", task["private"]) == task["private"]["answer"]
    feedback.validate_public("livemath", task["public"])  # raises on any other field set
    with pytest.raises(ValueError):
        feedback.validate_public("livemath", {"question": "q", "context": "c"})
    rows = [{"score": 0, "output": {"evidence_hash": "h"}}]
    assert skillopt._train_labels("livemath", [{"task": task}], rows) == [("h", task["private"]["answer"])]
    # an evaluation block is an external panel for the panel tool; a split member is refused
    block = tmp_path / "lm/eval_blocks/block_e01/items.json"
    (tmp_path / "skill.md").write_text("Compare every option with the hypotheses.\n", encoding="utf-8")
    record = panel_eval.prepare(*where, str(tmp_path / "e1"), str(tmp_path), benchmark="livemath", items=str(block),
                                revision="r" * 40, skills=["empty=none", "other=f:" + str(tmp_path / "skill.md")], chunk=10, seed=3)
    assert record["benchmark"] == "livemath" and record["tasks"] == 4
    inside = tmp_path / "inside.json"
    inside.write_text(json.dumps([{"id": t["task_id"], **t["public"], "answer": t["private"]["answer"]}
                                  for t in read_json(tmp_path / "lm/val_panel.json")["tasks"]]), encoding="utf-8")
    with pytest.raises(ValueError, match="not an evaluation block"):  # only the layout's own blocks are evaluated
        panel_eval.prepare(*where, str(tmp_path / "e2"), str(tmp_path), benchmark="livemath", items=str(inside),
                           revision="r" * 40, skills=["empty=none", "other=f:" + str(tmp_path / "skill.md")], chunk=10, seed=3)


def test_panels_solve_and_score_through_the_toolchain_exactly_as_the_pilots_did():
    from scripts import pilot_livemath_headroom as lm
    from scripts import pilot_officeqa_headroom as oq

    seen = []

    def call(system, user):
        seen.append((system, user))
        return {"ok": True, "response": "so <answer> d) </answer>", "usage": {}, "finish_reason": "stop",
                "request": {"service": {}}}

    public = {"question": "Which?", "choices": "A. a\n\nB. b\n\nC. c\n\nD. d\n\nE. e"}
    prediction = backends.solve("livemath", {"choices": public["choices"], "question": public["question"]}, "S", call)
    assert seen[-1] == (lm.system_prompt("S"), json.dumps(public, ensure_ascii=False))  # byte-identical to the pilot
    assert backends.score("livemath", public, {"answer": "D"}, prediction)["status"] == "pass"
    assert backends.score("livemath", public, {"answer": "A"}, prediction)["status"] == "fail"
    for reply in ("D", "<answer>d is right</answer>", "<answer>A or D</answer>"):
        result = backends.score("livemath", public, {"answer": "D"}, {"status": "available", "output": reply})
        assert (result["status"], result["metrics"]["invalid_format"]) == ("fail", 1.0)  # wrong, never unknown
    doc = {"question": "How much?", "context": "### page\nvalue 1,234.5"}
    backends.solve("officeqa", doc, "", call)
    assert seen[-1] == (oq.system_prompt(""), json.dumps(doc, ensure_ascii=False))
    reply = {"status": "available", "output": "<answer>$1234.5 million</answer>"}
    assert backends.score("officeqa", doc, {"answer": "1,234.5"}, reply)["status"] == "pass"
    assert backends.score("officeqa", doc, {"answer": "1,234.50"}, reply)["status"] == "fail"  # no numeric tolerance
    assert backends.score("officeqa", doc, {"answer": "7"}, {"status": "available", "output": "7"})["metrics"] == {
        "em": 0.0, "invalid_format": 1.0}
    assert backends.readiness("livemath")["status"] == backends.readiness("officeqa")["status"] == "ready"
    # panels of the two benchmarks validate; a LiveMath answer must be one of the five letters
    rows = [{"id": "1", **public, "answer": "D"}]
    assert datasets.import_livemath(rows, revision="fixture-v1")["tasks"][0]["private"]["answer"] == "D"
    with pytest.raises(ValueError, match="five options"):
        datasets.import_livemath([{**rows[0], "answer": "F"}], revision="fixture-v1")
    assert datasets.import_officeqa([{"id": "u", **doc, "answer": "7"}], revision="fixture-v1")["benchmark"] == "officeqa"


EXTENSION_TASKS = {
    "livemath": ({"question": "Which statement holds?", "choices": "A. no\n\nB. yes\n\nC. no\n\nD. no\n\nE. no"},
                 {"answer": "B"}, "<answer>B</answer>", "<answer>A</answer>", "livemath_strict_letter_in_last_answer_tag"),
    "officeqa": ({"question": "What was the total?", "context": "### bulletin page 3\ntotal | 1,234.5"},
                 {"answer": "1,234.5"}, "<answer>1234.5</answer>", "<answer>99</answer>",
                 "officeqa_native_normalized_em_on_last_answer_tag"),
}


@pytest.mark.parametrize("benchmark", sorted(EXTENSION_TASKS))
def test_a_skillopt_stage_learns_on_an_extension_benchmark_with_the_real_solver_and_scorer(tmp_path, monkeypatch, benchmark):
    """Real solve / score / labelled-feedback / optimizer routing for the new benchmarks, offline provider; NOT a
    natural run. The fixture provider answers correctly iff the Skill carries the edit the fixture analyst writes."""
    from skillopt.continual_learning.contracts import manifest
    from skillopt.continual_learning.skillopt import run_stage
    from skillopt.validator_pilot.api import digest

    public, private, right, wrong, reason = EXTENSION_TASKS[benchmark]
    _, _, args = setup(natural=True)
    panel = {"version": "continual-panel-v1", "benchmark": benchmark, "dataset_revision": "fixture-extension-v1",
             "provenance": "natural",
             "tasks": [{"task_id": str(i), "family_id": str(i), "project_id": "", "partition": "development",
                        "public": deepcopy(public), "private": deepcopy(private)} for i in range(4)]}
    value = manifest(panel, **args)
    assert value["benchmark"] == benchmark

    class Provider:
        service, model, calls = {"fixture": "offline-extension"}, "glm-5.3", []

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                       "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
            self.calls.append(request)
            if kind.endswith("solver"):
                assert json.loads(user) == public and private["answer"] not in system  # public view only
                response = right if "requested constant" in system else wrong
            else:
                edits = [{"op": "append", "content": "Use the requested constant result."}]
                response = json.dumps({"batch_size": 2, "patch": {"reasoning": "Fixture only", "edits": edits}})
            return {"request": request, "request_hash": digest(request), "response": response, "ok": True,
                    "finish_reason": "stop", "usage": {"prompt_tokens": 20, "completion_tokens": 20},
                    "http_attempt_count": 1}

        def close(self):
            pass

    api = Provider()
    monkeypatch.setattr("skillopt.continual_learning.skillopt.CachedAPI", lambda *a, **k: api)
    result = run_stage(value, panel, tmp_path, repo=tmp_path)
    assert result["status"] == "completed", result
    assert result["initial_selection_score"] == 0 and result["selected_score"] == 1
    assert result["costs"]["solver_calls"] == 6 and result["costs"]["reflection_calls"] == 1
    rows = [read_json(path, sealed=True) for path in (tmp_path / "evaluations").glob("*.json")]
    assert len(rows) == 6 and {row["score"]["reason"] for row in rows} == {reason}


def test_a_study_or_split_that_no_longer_is_its_pinned_layout_is_refused(tmp_path, monkeypatch):
    layout, protocol, split = _built(tmp_path, monkeypatch)
    raw = lambda value: {k: v for k, v in value.items() if k != "record_hash"}  # noqa: E731
    study_file = tmp_path / "X/protocol.json"
    original = study_file.read_text(encoding="utf-8")
    # (1) a study pointing at another development panel (with that panel's hash) but claiming the same layout
    other = tmp_path / "other_panel.json"
    other.write_text((tmp_path / "lm/val_panel.json").read_text(encoding="utf-8"), encoding="utf-8")
    forged = raw(protocol)
    forged["roles"] = {"livemath": {"runtime": {}, "path": str(other)}}
    forged["files"] = {str(other): hashlib.sha256(other.read_bytes()).hexdigest()}
    study_file.write_text(json.dumps(seal(forged)), encoding="utf-8")
    with pytest.raises(ValueError, match="pinned data layout"):
        tool._study(str(tmp_path / "X"))
    # (2) a study whose layout reference does not exist, and one that derives from another extension study
    study_file.write_text(json.dumps(seal({**raw(protocol), "layouts": {"livemath": {"directory": str(tmp_path / "no"),
                                                                                    "layout_hash": "0" * 64}}})),
                          encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError)):
        tool._study(str(tmp_path / "X"))
    study_file.write_text(json.dumps(seal({**raw(protocol), "derived_from": {**protocol["derived_from"],
                                                                             "study": str(tmp_path / "X")}})),
                          encoding="utf-8")
    with pytest.raises(ValueError, match="derives from study F itself"):
        tool._study(str(tmp_path / "X"))
    study_file.write_text(original, encoding="utf-8")
    root, loaded = tool._study(str(tmp_path / "X"))
    # (3) a resealed split that drops the sealed test part, or renames a family, is not the layout
    for change in (lambda parts: {**parts, "test": []},
                   lambda parts: {**parts, "val": [{**parts["val"][0], "family_id": "x"}, *parts["val"][1:]]}):
        resealed = seal({**raw(split), "splits": {"livemath": change(split["splits"]["livemath"])}})
        with pytest.raises(ValueError, match="differs from the study's pinned data layout"):
            tool.check_split(resealed, loaded, "livemath")
    tool.check_split(split, loaded, "livemath")
    # (3b) an extra source in a resealed split cannot bring in another validation panel
    forged_val = tmp_path / "forged_val.json"
    panel = read_json(tmp_path / "lm/val_panel.json")
    panel["tasks"][0]["private"]["answer"] = "E" if panel["tasks"][0]["private"]["answer"] != "E" else "A"
    forged_val.write_text(json.dumps(panel), encoding="utf-8")
    extra = seal({**raw(split), "sources": {**split["sources"],
                                           str(forged_val): hashlib.sha256(forged_val.read_bytes()).hexdigest()}})
    with pytest.raises(ValueError, match="differs from the study's pinned data layout"):
        tool.check_split(extra, loaded, "livemath")
    with pytest.raises(ValueError, match="not the validation panel"):
        tool.check_val_source(loaded, "livemath", str(forged_val))
    tool.check_val_source(loaded, "livemath", str(tmp_path / "lm/val_panel.json"))
    # (4) a changed evaluation block is refused by the builder's consumer and by the panel tool
    block = tmp_path / "lm/eval_blocks/block_e01/items.json"
    rows = json.loads(block.read_text(encoding="utf-8"))
    block.write_text(json.dumps(rows[:-1]), encoding="utf-8")
    with pytest.raises(ValueError, match="blocks changed"):
        ext._layout(str(tmp_path / "lm"))
    with pytest.raises(ValueError, match="not an evaluation block"):
        tool.check_evaluation_block(loaded, "livemath", str(block))


def test_malformed_extension_items_and_blank_replies(tmp_path):
    good = "A. a\n\nB. b spans\ntwo lines\n\nC. c\n\nD. d\n\nE. e"
    assert datasets.livemath_options(good) == ["a", "b spans\ntwo lines", "c", "d", "e"]
    for bad in ("A. only option", "A. a\n\nB. b\n\nC. c\n\nD. d", "B. b\n\nA. a\n\nC. c\n\nD. d\n\nE. e",
                "A. a\n\nB. \n\nC. c\n\nD. d\n\nE. e"):
        assert datasets.livemath_options(bad) is None
        with pytest.raises(ValueError, match="five options"):
            datasets.import_livemath([{"id": "1", "question": "q", "choices": bad, "answer": "A"}], revision="fixture-v1")
    with pytest.raises(ValueError, match="one text"):
        datasets.import_officeqa([{"id": "u", "question": "q", "context": ["page"], "answer": "7"}], revision="fixture-v1")
    with pytest.raises(ValueError):
        datasets.import_officeqa([{"id": "u", "question": "q", "context": "page", "answer": "  "}], revision="fixture-v1")
    from skillopt.continual_learning import feedback
    with pytest.raises(ValueError):
        feedback.validate_public("officeqa", {"question": "q", "context": ["page"]})
    # a reply the provider COMPLETED without text is an answer in no valid form (wrong); an undelivered one is unknown
    public = {"question": "Which?", "choices": good}
    base = {"usage": {"prompt_tokens": 9, "completion_tokens": 0}, "request": {"service": {}}}
    completed = [{**base, "ok": True, "response": "  \n", "finish_reason": "stop"},
                 {**base, "ok": False, "response": "", "finish_reason": "stop", "error_type": "empty_content",
                  "status": 200, "stream_complete": True}]
    for receipt in completed:
        prediction = backends.solve("livemath", public, "", lambda system, user, r=receipt: r)
        assert (prediction["status"], prediction["output"]) == ("available", "")
        result = backends.score("livemath", public, {"answer": "A"}, prediction)
        assert (result["status"], result["metrics"]["invalid_format"]) == ("fail", 1.0)
    for receipt in ({**base, "ok": False, "response": "", "finish_reason": None, "error_type": "timeout"},
                    {**base, "ok": False, "response": "", "finish_reason": "stop", "error_type": "empty_content",
                     "stream_complete": False},
                    {**base, "ok": False, "response": "x", "finish_reason": "length", "error_type": "truncated_content"},
                    # a completed blank without reported usage is not an accounted answer; an oversized one is no answer
                    {**base, "ok": False, "response": "", "finish_reason": "stop", "error_type": "empty_content", "usage": {}},
                    {**base, "ok": True, "response": "\u3000" * 100000, "finish_reason": "stop"}):
        assert backends.solve("livemath", public, "", lambda system, user, r=receipt: r)["status"] == "unknown"
    # the five older benchmarks keep their behaviour: a blank completed SearchQA reply stays unknown
    old = backends.solve("searchqa", {"question": "q", "context": ["c"]}, "", lambda system, user: completed[0])
    assert old["status"] == "unknown"
    # only the LAST answer tag counts
    twice = {"status": "available", "output": "<answer>A</answer> no, <answer>B</answer>"}
    assert backends.score("livemath", public, {"answer": "B"}, twice)["status"] == "pass"
    assert backends.score("livemath", public, {"answer": "A"}, twice)["status"] == "fail"


def _fixture_stage(benchmark, *, train=8, selection=8):
    """A fixture-provenance panel of an extension benchmark with a learning v10 manifest (as the v10 tests build)."""
    from skillopt.continual_learning.contracts import VERIFIER_METHOD, VERIFIER_VERSION, manifest
    from skillopt.continual_learning.feedback import VERIFIER_PROFILE
    from skillopt.continual_learning.recovery import POLICY_V10

    public, private = EXTENSION_TASKS[benchmark][:2]
    _, base, args = setup("searchqa")
    tasks = [{"task_id": str(i), "family_id": str(i), "project_id": "",
              "partition": "development" if i < train else "skill_confirmation",
              "public": deepcopy(public), "private": deepcopy(private)} for i in range(train + selection)]
    panel = {**base, "benchmark": benchmark, "tasks": tasks}
    args.update(version=VERIFIER_VERSION, recovery_policy=deepcopy(POLICY_V10),
                train_families=[str(i) for i in range(train)],
                selection_families=[str(i) for i in range(train, train + selection)], feedback_profile=VERIFIER_PROFILE,
                method=VERIFIER_METHOD, parent_verifier_policy=None)
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    args["budget"].update(max_iterations=1, max_metric_calls=200, max_api_calls=600, max_reflection_calls=40,
                          max_verifier_calls=100, verifier_max_tokens=100)
    return manifest(panel, **args), panel


@pytest.mark.parametrize("benchmark", sorted(EXTENSION_TASKS))
def test_the_rubric_research_learner_runs_its_judge_path_on_an_extension_benchmark(tmp_path, benchmark):
    from skillopt.continual_learning import verifier as vf
    from skillopt.continual_learning.skillopt import run_stage
    from tests.test_continual_learning_verifier_v10 import API, host_evaluate

    value, panel = _fixture_stage(benchmark)
    api = API()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=host_evaluate(benchmark),
                       fixture_probe_executor=lambda *a: pytest.fail("no container for text domains"))
    assert result["status"] == "completed", result.get("reason")
    step = result["verifier_steps"][0]
    assert step["arm"] == "adaptive_no_research" and step["authorized"] and step["reports_with_feedback"] == 3
    assert set(result["verifier_policy"]) == {benchmark}  # the stage's own domain, starting from its default rubric
    assert vf.default_policy_record(benchmark)["policy"] == vf.DEFAULT_POLICIES[benchmark]
    judge = [p for p in api.prompts["verifier"] if "anonymous_response" in p]
    assert len(judge) == 8
    public = EXTENSION_TASKS[benchmark][0]
    if benchmark == "livemath":
        assert all("B. yes" in p for p in judge)  # the options are part of the task the judge may quote from
        assert vf.task_text(benchmark, public) == public["question"] + "\n\n" + public["choices"]
    else:
        assert vf.task_text(benchmark, public) == public["question"]  # obligations are quoted from the question only
        assert vf._public_view(benchmark, {**public, "context": "x" * 9000})["context"].endswith("[truncated]")


@pytest.mark.parametrize("benchmark", sorted(EXTENSION_TASKS))
def test_one_step_learning_v11_runs_on_an_extension_benchmark_and_refuses_the_diagnosis_arms(tmp_path, benchmark):
    from skillopt.active_evidence import protocol as ae
    from skillopt.active_evidence.stage import run_stage
    from tests.test_continual_learning_active_evidence import API, CHALLENGE, PLAIN, POOL, STEP, _args, evaluate

    public, private = EXTENSION_TASKS[benchmark][:2]
    _, base, _ = setup("searchqa")
    panel = {**base, "benchmark": benchmark,
             "tasks": [{"task_id": i, "family_id": i, "project_id": "", "partition": "development",
                        "public": deepcopy(public), "private": deepcopy(private)} for i in [*STEP, *POOL]]}
    value = ae.manifest(panel, **_args(arms=PLAIN))
    result = run_stage(value, panel, tmp_path / "learning", fixture_api=API(),
                       fixture_evaluate=evaluate("candidate_wins"), fixture_probe_executor=None)
    assert result["status"] == "completed" and result["decisions"] == ["accepted_without_challenge"]
    assert "requested constant" in result["candidate_skill"]
    with pytest.raises(ValueError, match="not implemented for the benchmark"):
        ae.manifest(panel, **_args(arms=CHALLENGE))


def test_the_officeqa_layout_is_the_papers_split_with_its_test_part_as_ids(tmp_path, monkeypatch):
    from tests.test_continual_learning_officeqa_pilot import ROWS
    from tests.test_continual_learning_officeqa_pilot import _upstream as officeqa_upstream

    rows = [r for r in ROWS if r[0] != "u4"] + [("u5", "train", "easy", "5"), ("u6", "train", "hard", "6"),
                                               ("u7", "val", "easy", "7")]
    monkeypatch.setattr("tests.test_continual_learning_officeqa_pilot.ROWS", rows)
    up, ids = officeqa_upstream(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "_outside", lambda out, root, protocol, extra=(): None)
    monkeypatch.setattr(tool, "TRAIN", {**tool.TRAIN, "officeqa": {"families": 3}})
    layout = ext.data("officeqa", str(up), str(ids), str(tmp_path / "oq"), revision="r" * 40)
    assert layout["counts"] == {"train": 4, "val": 2, "eval": 0, "test": 1}
    assert [e["task_id"] for e in layout["parts"]["test"]] == ["t1"] and layout["evaluation_blocks"] == {"items": [], "blocks": []}
    written = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "oq").rglob("*.json"))
    assert "SECRET TEST" not in written and "not document-disjoint" in layout["family_rule"]
    dev = read_json(tmp_path / "oq/dev_panel.json")
    assert dev["benchmark"] == "officeqa" and set(dev["tasks"][0]["public"]) == {"question", "context"}
    assert type(dev["tasks"][0]["public"]["context"]) is str
    base, _ = _base(tmp_path)
    protocol = ext.study(str(base), [str(tmp_path / "oq")], str(tmp_path / "XO"))
    split = ext.split(str(tmp_path / "XO"), str(tmp_path / "split-oq.json"))
    assert split["counts"]["officeqa"]["test"] == 1 and protocol["order"] == ["officeqa"]
    where = (str(tmp_path / "XO"), str(tmp_path / "split-oq.json"))
    v9 = tool.prepare(*where, str(tmp_path / "o9"), str(tmp_path), val_source=str(tmp_path / "oq/val_panel.json"),
                      method="skillopt", learning_version="v9", benchmark="officeqa", parent="none", seed=3)
    v11 = tool.prepare(*where, str(tmp_path / "o11"), str(tmp_path), val_source=None, method=tool.ACTIVE_EVIDENCE,
                       learning_version="v11", arms={"feedback": "scalar", "post_update": "none"},
                       benchmark="officeqa", parent="none", seed=3)
    assert v9["train_tasks"] == 3 and v9["selection_tasks"] == 2 and v11["benchmark"] == "officeqa"
    assert tool.TRAIN["officeqa"]["families"] == 3 and tool.API_ONLY[-1] == "officeqa"

