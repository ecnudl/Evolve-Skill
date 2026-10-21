"""Controls for validation by GENERATED test tasks (engineering fixtures, no method-effect claim): SearchQA tasks are
written from a stage's training tasks only, filtered deterministically and by an independent review, and can then
replace the canonical validation partition as the selection set of the validation-gated learner."""
import hashlib
import json
from copy import deepcopy

import pytest

from scripts import generate_searchqa_tasks as gen
from scripts import run_fivebench_g_stage as tool
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from tests.test_continual_learning_active_evidence import API
from tests.test_continual_learning_domains import setup

CONTEXT = ("Mount Kenya is the highest mountain in Kenya. Nairobi is the capital of Kenya and was founded in 1899. "
           "The Tana River is the longest river in Kenya.")


def _study(tmp_path, monkeypatch, *, tasks=12):
    _, base, args = setup("searchqa")
    task = base["tasks"][0]
    dev = {**base, "tasks": [{**deepcopy(task), "task_id": str(i), "family_id": str(i),
                              "public": {"question": f"Source clue number {i} about the highest mountain?",
                                         "context": CONTEXT + f" Note {i}."}} for i in range(tasks)]}
    dev_path = tmp_path / "study" / "dev_panel.json"
    write_json(dev_path, dev)
    plan = seal({"config": {"panels": {"searchqa": str(dev_path)}}})
    write_json(tmp_path / "study/ref/plan.json", plan)
    model = args["model"]
    model["transport"]["stream_wall_seconds"] = 3600
    model["max_tokens"] = tool.BUDGET_V11["solver_max_tokens"]
    protocol = {"record_hash": "p" * 64, "root": str(tmp_path / "study"),
                "references": {"searchqa": {"root": str(tmp_path / "study/ref"), "plan_hash": plan["record_hash"]}},
                "files": {str(dev_path): hashlib.sha256(dev_path.read_bytes()).hexdigest()},
                "model": model, "roles": {"searchqa": {"runtime": {}}},
                "learning_model_service": {"fixture": True}, "config": {"native_lock": str(tmp_path / "lock")}}
    split = seal({"version": tool.SPLIT_VERSION, "f_study_usage": {"searchqa": {"protocol_hash": "p" * 64}},
                  "splits": {"searchqa": {"train": [{"task_id": t["task_id"], "family_id": t["family_id"]}
                                                    for t in dev["tasks"]], "val": []}}})
    write_json(tmp_path / "split.json", split)
    monkeypatch.setattr(tool, "_study", lambda study: (tmp_path / "study", protocol))
    monkeypatch.setattr(tool, "_outside", lambda out, root, protocol, extra=(): None)
    monkeypatch.setattr(tool, "TRAIN", {**tool.TRAIN, "searchqa": {"families": 6}})
    return dev, split


class Writer(API):
    """Fixture writer / reviewer: two questions per source (one good, one whose answer is not in the snippets), the
    reviewer rejects every question about the river."""

    def _verifier(self, payload):
        if "source_question" in payload and "proposed_answer" not in payload:
            number = payload["snippets"].rsplit("Note ", 1)[1].rstrip(".")
            return {"tasks": [
                {"question": f"Clue {number}: this city is the capital of Kenya", "answer": "Nairobi",
                 "quote": "Nairobi is the capital of Kenya"},
                {"question": f"Clue {number}: the longest river in Kenya is this one", "answer": "Tana River",
                 "quote": "The Tana River is the longest river in Kenya"},
                {"question": "ignored third question beyond the per-task limit", "answer": "Kenya", "quote": "Kenya"}]}
        if "proposed_answer" in payload:
            assert payload["source_question"].startswith("Source clue number")
            number = int(payload["question"].split(":")[0].split()[1])
            good = "river" not in payload["question"] or number % 2 == 0  # even sources keep BOTH siblings
            return {"supported": True, "unique": good, "form": True, "distinct": True, "reason": "fixture"}
        return super()._verifier(payload)


def test_deterministic_filters():
    source = {"question": "Source clue about the highest mountain?", "context": CONTEXT}
    good = {"question": "This city is the capital of Kenya", "answer": "Nairobi", "quote": "Nairobi is the capital of Kenya"}
    assert gen.admissible(good, source, set()) is None
    for change, reason in (({"answer": "Mombasa", "quote": "Nairobi is the capital of Kenya"}, "quote_not_verbatim_or_without_answer"),
                           ({"quote": "Nairobi is surely the capital"}, "quote_not_verbatim_or_without_answer"),
                           ({"question": "Nairobi is the capital of which country, this one?", "answer": "Nairobi"}, "answer_in_question"),
                           ({"question": "short"}, "question_length"),
                           ({"answer": "yes", "quote": "yes"}, "answer_form"),
                           ({"answer": "one two three four five six seven", "quote": "x"}, "answer_form"),
                           ({"question": "Source clue about the highest mountain"}, "duplicate_question"),
                           ({"answer": 3}, "malformed")):
        assert gen.admissible({**good, **change}, source, set()) == reason
    from skillopt.envs.searchqa.evaluator import normalize_answer
    assert gen.admissible(good, source, {normalize_answer(good["question"])}) == "duplicate_question"


def test_tasks_are_generated_from_training_tasks_only_and_published_once(tmp_path, monkeypatch):
    dev, _ = _study(tmp_path, monkeypatch)
    record = gen.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "g"), str(tmp_path), seed=3)
    assert record["source_tasks"] == 6 and record["per_task"] == 2 and "no reference answer" in record["information"]
    api = Writer()
    with pytest.raises(ValueError, match="Invalid fixture callbacks"):
        gen.run(str(tmp_path / "g"))
    result = gen.run(str(tmp_path / "g"), fixture_api=api)
    assert result["status"] == "completed" and result["source_tasks"] == 6
    kept = result["candidates_accepted"]
    assert (result["candidates_written"], result["candidates_after_filters"]) == (12, 12) and 6 < kept < 12
    path, _, checked = gen.check(str(tmp_path / "g"))
    items = json.loads(path.read_text(encoding="utf-8"))
    assert checked == result and len(items) == kept and all(set(i) == {"id", "question", "context", "answers"} for i in items)
    assert all(i["answers"] in (["Nairobi"], ["Tana River"]) and i["id"].startswith("gen-") for i in items)
    # siblings written from the same training task share ONE family (one sign per source in the gate's test)
    families = gen.family_map(str(tmp_path / "g"))
    assert set(families) == {i["id"] for i in items} and len(set(families.values())) == 6
    assert all(f.startswith("generated-") for f in families.values())
    # every generated task keeps the snippets of one of THIS seed's training tasks; nothing else of the panel is used
    train_contexts = {t["public"]["context"] for t in read_json(tmp_path / "g/panel.json")["tasks"]}
    assert {i["context"] for i in items} == train_contexts and len(train_contexts) == 6
    # prompts carry public fields only: no private answer of the development panel
    private = json.dumps(dev["tasks"][0]["private"]["answers"])
    assert len(api.prompts["verifier"]) == 6 + 12 and not api.prompts["solver"] and not api.prompts["reflection"]
    assert all(private not in p for p in api.prompts["verifier"])
    records = read_json(tmp_path / "g/records.json", sealed=True)["sources"]
    assert sum(c.get("accepted") is True for r in records for c in r["candidates"]) == kept
    assert all(len(r["candidates"]) == 2 for r in records)  # the third proposal is beyond the per-task limit
    # generated once: a later invocation returns the published result without another call
    assert gen.run(str(tmp_path / "g"), fixture_api=api) == result and len(api.prompts["verifier"]) == 18
    # a run that cannot start its first call is a durable pending result with no items file
    gen.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "g2"), str(tmp_path), seed=3)

    class Broken(API):
        def call(self, *args, **kwargs):
            raise RuntimeError("provider text")

    failed = gen.run(str(tmp_path / "g2"), fixture_api=Broken())
    assert failed["status"] == "pending" and failed["reason"] == "error:RuntimeError"
    assert not (tmp_path / "g2/items.json").exists()
    with pytest.raises(ValueError, match="No completed generation"):
        gen.check(str(tmp_path / "g2"))


def test_generated_tasks_replace_the_validation_partition_of_the_frozen_rubric_research_learner(tmp_path, monkeypatch):
    """``--generated-val``: the stage tool binds a completed generation made from exactly this stage's training
    tasks as the selection set; the frozen learning-v10 learner then runs unchanged on it (no canonical validation
    file exists anywhere in this fixture)."""
    from skillopt.continual_learning.skillopt import run_stage
    from tests.test_continual_learning_active_evidence import evaluate
    from tests.test_continual_learning_verifier_v10 import executor

    _study(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "parent_skill", lambda root, protocol, name, split_hash=None: ("", {"parent": name}))
    gen.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "g"), str(tmp_path), seed=3)
    generation = gen.run(str(tmp_path / "g"), fixture_api=Writer())
    common = dict(benchmark="searchqa", parent="none", method="rubric_research", learning_version="v10")
    record = tool.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "stage"), str(tmp_path),
                          val_source=None, seed=3, generated_val=str(tmp_path / "g"), **common)
    assert record["selection_source"].startswith("generated_from_this_stage_training_tasks")
    assert record["selection_tasks"] == generation["candidates_accepted"] > 6 and record["train_tasks"] == 6
    assert record["selection_families"] == 6 == record["generated_val"]["families"]  # siblings grouped by source
    assert record["generated_val"]["items_sha256"] == generation["items_sha256"] == record["val_source_sha256"]
    assert "selection_is_generated" in record["data_scope"]
    value, panel = read_json(tmp_path / "stage/manifest.json", sealed=True), read_json(tmp_path / "stage/panel.json")
    selection = [t for t in panel["tasks"] if t["partition"] == "skill_confirmation"]
    assert len(selection) > 6 and all(t["task_id"].startswith("gen-") for t in selection)
    assert sorted({t["family_id"] for t in selection}) == value["selection_families"] and len(value["selection_families"]) == 6
    assert tool._load(str(tmp_path / "stage"))[1] == record
    # refusals: another seed's generation, both sources at once, the v11 method, a generation that is not complete
    with pytest.raises(ValueError, match="not made from this stage's training tasks"):
        tool.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "r1"), str(tmp_path),
                     val_source=None, seed=4, generated_val=str(tmp_path / "g"), **common)
    with pytest.raises(ValueError, match="not both"):
        tool.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "r2"), str(tmp_path),
                     val_source=str(tmp_path / "split.json"), seed=3, generated_val=str(tmp_path / "g"), **common)
    with pytest.raises(ValueError, match="no generated validation"):
        tool.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "r3"), str(tmp_path),
                     benchmark="searchqa", parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE,
                     learning_version="v11", generated_val=str(tmp_path / "g"))
    gen.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "g3"), str(tmp_path), seed=3)
    with pytest.raises((ValueError, FileNotFoundError)):
        tool.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "r4"), str(tmp_path),
                     val_source=None, seed=3, generated_val=str(tmp_path / "g3"), **common)
    # the frozen learner runs on the generated selection set and its gate decides on those tasks
    result = run_stage(value, panel, tmp_path / "stage/learning", fixture_api=API(),
                       fixture_evaluate=evaluate("candidate_wins"), fixture_probe_executor=executor())
    assert result["status"] == "completed", result.get("reason")
    assert result["candidate_skill"] != "" and result["steps"][0]["gate_action"] == "accept_confirmed"


def test_fixed_text_parent_goes_with_generated_validation(tmp_path, monkeypatch):
    """A fixed initial instruction as the parent of the frozen Rubric+Research learner, allowed only when the
    selection set is generated (v9 / v10): the stage records the text by hash, the gate compares candidates with
    that text, a stage without an accepted update carries it, and such a stage has no test cell."""
    from skillopt.continual_learning.skillopt import run_stage
    from tests.test_continual_learning_active_evidence import evaluate
    from tests.test_continual_learning_verifier_v10 import executor

    _study(tmp_path, monkeypatch)
    text = "Answer with the bare entity only.\n"
    (tmp_path / "b.md").write_text(text, encoding="utf-8")
    parent = "f:" + str(tmp_path / "b.md")
    gen.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "g"), str(tmp_path), seed=3)
    gen.run(str(tmp_path / "g"), fixture_api=Writer())
    common = dict(benchmark="searchqa", parent=parent, method="rubric_research", learning_version="v10")
    where = (str(tmp_path / "study"), str(tmp_path / "split.json"))
    record = tool.prepare(*where, str(tmp_path / "stage"), str(tmp_path), val_source=None, seed=3,
                          generated_val=str(tmp_path / "g"), **common)
    assert record["parent"] == parent and record["parent_action"] == "fixed_text" and record["parent_stage_hash"] is None
    assert record["parent_skill_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    value, panel = read_json(tmp_path / "stage/manifest.json", sealed=True), read_json(tmp_path / "stage/panel.json")
    assert value["parent_skill"] == text and value["parent_verifier_policy"] is None
    assert tool._load(str(tmp_path / "stage"))[1] == record
    # refusals: the canonical validation partition (chain stages keep chain parents), learning v8, a test cell
    with pytest.raises(ValueError, match="fixed-text parent"):
        tool.prepare(*where, str(tmp_path / "r1"), str(tmp_path), val_source=str(tmp_path / "split.json"), seed=3, **common)
    with pytest.raises(ValueError, match="fixed-text parent"):
        tool.prepare(*where, str(tmp_path / "r2"), str(tmp_path), val_source=None, seed=3, benchmark="searchqa",
                     parent=parent, method="skillopt", learning_version="v8", generated_val=str(tmp_path / "g"))
    with pytest.raises(ValueError, match="no test cell"):
        tool.test(str(tmp_path / "stage"), str(tmp_path / "unused"))

    def spy(mode, seen):
        base = evaluate(mode)

        def execute(task, skill):
            if task["task_id"].startswith("gen-"):
                seen.add(skill)
            return base(task, skill)
        return execute

    # the gate's parent on the generated tasks is the fixed text; a rejected candidate leaves that text in place
    seen = set()
    result = run_stage(value, panel, tmp_path / "stage/learning", fixture_api=API(),
                       fixture_evaluate=spy("parent_wins", seen), fixture_probe_executor=executor())
    assert result["status"] == "completed", result.get("reason")
    assert text in seen and len(seen) > 1 and all(s.startswith(text) or s == text for s in seen)
    assert result["candidate_skill"] == text and not any(step.get("accepted") for step in result["steps"])
    # an accepted candidate is an edit of the fixed text and was compared with it
    tool.prepare(*where, str(tmp_path / "stage2"), str(tmp_path), val_source=None, seed=3,
                 generated_val=str(tmp_path / "g"), **common)
    value2, panel2 = read_json(tmp_path / "stage2/manifest.json", sealed=True), read_json(tmp_path / "stage2/panel.json")
    seen = set()
    result = run_stage(value2, panel2, tmp_path / "stage2/learning", fixture_api=API(),
                       fixture_evaluate=spy("candidate_wins", seen), fixture_probe_executor=executor())
    assert result["status"] == "completed" and result["steps"][0]["gate_action"] == "accept_confirmed"
    assert text in seen and result["candidate_skill"] != text and result["candidate_skill"].startswith(text)
    # the file is bound for the life of the stage: a changed text is refused when the stage is loaded
    (tmp_path / "b.md").write_text(text + "More.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Parent changed"):
        tool._load(str(tmp_path / "stage"))
