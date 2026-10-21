"""Controls for the learning-v11 (active_evidence) branch of the G stage tool: a prepared stage reads no validation
data, its manifest validates, and the tool verifies a finished stage's evidence inventory (fixture only)."""
import hashlib
import json
from copy import deepcopy

import pytest

from scripts import run_fivebench_g_stage as tool
from skillopt.active_evidence import METHOD, PROTOCOL
from skillopt.active_evidence import protocol as ae
from skillopt.active_evidence.stage import run_stage
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from tests.test_continual_learning_active_evidence import API, evaluate
from tests.test_continual_learning_domains import setup

REAL_PARENT_SKILL = tool.parent_skill  # the fixture study replaces it; the study-branch parent test restores it


def _fixture_study(tmp_path, monkeypatch, *, n_families=40):
    """A minimal F-study stand-in: a development panel of 40 single-task families, a split whose train part is the
    whole panel, and the protocol fields prepare_active_evidence reads. No val file exists anywhere."""
    _, base, args = setup("bigcodebench")
    task = base["tasks"][0]
    dev_panel = {**base, "tasks": [{**deepcopy(task), "task_id": str(i), "family_id": str(i)} for i in range(n_families)]}
    dev_path = tmp_path / "study" / "dev_panel.json"
    write_json(dev_path, dev_panel)
    ref_root = tmp_path / "study" / "ref"
    plan = seal({"config": {"panels": {"bigcodebench": str(dev_path)}}})
    write_json(ref_root / "plan.json", plan)
    model = args["model"]
    model["transport"]["stream_wall_seconds"] = 3600
    model["max_tokens"] = tool.BUDGET_V11["solver_max_tokens"]  # F's model record matches the solver budget
    protocol = {"record_hash": "p" * 64, "root": str(tmp_path / "study"),
                "references": {"bigcodebench": {"root": str(ref_root), "plan_hash": plan["record_hash"]}},
                "files": {str(dev_path): hashlib.sha256(dev_path.read_bytes()).hexdigest()},
                "model": model, "roles": {"bigcodebench": {"runtime": {}}},
                "learning_model_service": {"fixture": True}, "config": {"native_lock": str(tmp_path / "lock")}}
    split = seal({"version": tool.SPLIT_VERSION,
                  "f_study_usage": {"bigcodebench": {"protocol_hash": protocol["record_hash"]}},
                  "splits": {"bigcodebench": {"train": [{"task_id": t["task_id"], "family_id": t["family_id"]}
                                                        for t in dev_panel["tasks"]], "val": []}}})
    split_path = tmp_path / "split.json"
    write_json(split_path, split)
    monkeypatch.setattr(tool, "_study", lambda study: (tmp_path / "study", protocol))
    monkeypatch.setattr(tool, "parent_skill", lambda root, protocol, name, split_hash=None: ("", {"parent": name}))
    monkeypatch.setattr(tool, "_outside", lambda out, root, protocol, extra=(): None)
    monkeypatch.setattr(tool, "TRAIN", {**tool.TRAIN, "bigcodebench": {"families": 8}})
    return split_path, dev_panel


def test_prepare_active_evidence_reads_no_validation_data_and_validates(tmp_path, monkeypatch):
    split_path, dev_panel = _fixture_study(tmp_path, monkeypatch)
    out = tmp_path / "stage"
    record = tool.prepare(str(tmp_path / "study"), str(split_path), str(out), str(tmp_path), benchmark="bigcodebench",
                          parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE, learning_version="v11",
                          arms={"feedback": "diagnosis_research", "post_update": "challenge_replay"})
    assert record["method"] == METHOD and record["learning_version"] == PROTOCOL and record["val_source_sha256"] is None
    assert record["selection_tasks"] == 0 and record["train_tasks"] == 8 and record["challenge_tasks"] == 32
    assert record["arms"] == {"feedback": "diagnosis_research", "post_update": "challenge_replay"}
    # decision rule v2 limits are fixed at preparation: the fresh panel is capped by the 32 eligible pool tasks and
    # needs 90% coverage (29); the requested defaults stay on record; alpha is unchanged
    assert record["eligible_fresh_tasks"] == 32 and record["limits_requested"]["fresh_tasks"] == 96
    assert (record["limits"]["fresh_tasks"], record["limits"]["min_paired_known"], record["limits"]["decision_alpha_permille"]) == (32, 29, 50)
    value = read_json(out / "manifest.json", sealed=True)
    assert value["active_evidence"]["limits"] == record["limits"]
    panel = read_json(out / "panel.json")
    assert ae.validate_manifest(value, panel) == value and value["selection_families"] == []
    assert len(value["active_evidence"]["step_families"]) == 8 and len(value["active_evidence"]["challenge_families"]) == 32
    assert {t["partition"] for t in panel["tasks"]} == {"development"} and len(panel["tasks"]) == 40
    assert tool._manifest_method(record) == "rubric_research" and tool._method(record) == METHOD
    with pytest.raises(ValueError, match="active-evidence method is learning v11"):
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "x"), str(tmp_path), benchmark="bigcodebench",
                     parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE, learning_version="v10")
    with pytest.raises(ValueError, match="Arms and reference Skills belong"):
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "y"), str(tmp_path), benchmark="bigcodebench",
                     parent="none", val_source=None, seed=3, method="skillopt", learning_version="v8",
                     arms={"feedback": "scalar", "post_update": "none"})


def test_tool_verifies_a_finished_v11_stage_inventory(tmp_path, monkeypatch):
    split_path, dev_panel = _fixture_study(tmp_path, monkeypatch)
    out = tmp_path / "stage"
    tool.prepare(str(tmp_path / "study"), str(split_path), str(out), str(tmp_path), benchmark="bigcodebench", parent="none",
                 val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE, learning_version="v11",
                 arms={"feedback": "scalar", "post_update": "challenge_replay"})
    value = read_json(out / "manifest.json", sealed=True)
    panel = read_json(out / "panel.json")
    pass_ids = {t["task_id"] for t in panel["tasks"][:5]}

    def fixture_evaluate(task, skill):
        ok = task["task_id"] in pass_ids if task["family_id"] in value["active_evidence"]["step_families"] \
            else "requested constant" in skill
        return ({"status": "available", "output": "one" if ok else "zero", "reason": "fixture"},
                {"status": "pass" if ok else "fail", "score": float(ok), "reason": "fixture", "metrics": {}})

    result = run_stage(value, panel, out / "learning", fixture_api=API(), fixture_evaluate=fixture_evaluate)
    assert result["status"] == "completed" and result["decisions"] == ["keep"]
    tool._verify_learning_evidence(out, value, result)  # every sealed record is inventoried
    tool._active_evidence_handoff(out / "learning")
    (out / "learning/chain/extra.json").write_text("{}")
    with pytest.raises(ValueError, match="does not record"):
        tool._verify_learning_evidence(out, value, result)
    (out / "learning/chain/extra.json").unlink()
    (out / "learning/diagnosis/0/executions").mkdir(parents=True)
    write_json(out / "learning/diagnosis/0/executions/x-standard.intent.json", seal({"open": True}))
    with pytest.raises(ValueError, match="Open diagnostic execution"):
        tool._active_evidence_handoff(out / "learning")


def test_prepare_binds_reference_skills_from_sealed_stages_of_the_same_study(tmp_path, monkeypatch):
    """``--reference name=g:<dir>``: the Skill a finished G stage of the same study/split recorded, refused when that
    stage trained on families of this stage's holdout pool; the manifest carries the text and its provenance."""
    split_path, dev_panel = _fixture_study(tmp_path, monkeypatch)
    split_hash = read_json(split_path, sealed=True)["record_hash"]
    study = {"arms": {"feedback": "diagnosis_research", "post_update": "matched_scalar_branch"}}
    probe = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "probe"), str(tmp_path),
                         benchmark="bigcodebench", parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE,
                         learning_version="v11", **study)
    assert probe["reference_skills"] == []
    step_families = probe["train_families"]
    pool = sorted({t["family_id"] for t in dev_panel["tasks"]} - set(step_families))

    def finished(name, *, families, skill="Baseline guidance.", status="completed", action="selected_update", **changes):
        root = tmp_path / name
        stage = seal({"version": tool.VERSION, "protocol_hash": "p" * 64, "study": str(tmp_path / "study"),
                      "split_hash": split_hash, "benchmark": "bigcodebench", "method": "skillopt",
                      "learning_version": "continual-learning-v9", "train_families": families, "selection_tasks": 4,
                      **changes})
        write_json(root / "stage.json", stage)
        write_json(root / "learned.json", seal({"stage_hash": stage["record_hash"], "status": status, "action": action,
                                                "skill": skill, "skill_sha256": hashlib.sha256(skill.encode()).hexdigest()}))
        return f"{name}=g:{root}"

    good = finished("gated", families=step_families)
    record = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "stage"), str(tmp_path),
                          benchmark="bigcodebench", parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE,
                          learning_version="v11", references=(good,), **study)
    value = read_json(tmp_path / "stage/manifest.json", sealed=True)
    reference = value["active_evidence"]["reference_skills"][0]
    assert reference["name"] == "gated" and reference["skill"] == "Baseline guidance."
    assert reference["source"]["method"] == "skillopt" and reference["source"]["train_families_disjoint_from_holdout_pool"] is True
    assert record["reference_skills"] == [{"name": "gated", **reference["source"]}] and "skill" not in record["reference_skills"][0]
    assert ae.validate_manifest(value, read_json(tmp_path / "stage/panel.json")) == value

    def refused(spec, message, output):
        with pytest.raises(ValueError, match=message):
            tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / output), str(tmp_path),
                         benchmark="bigcodebench", parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE,
                         learning_version="v11", references=(spec,), **study)

    refused(finished("leaky", families=step_families[:2] + pool[:1]), "holdout pool", "r1")
    refused(finished("pending", families=step_families, status="pending"), "completed, consistently recorded", "r2")
    refused(finished("otherstudy", families=step_families, protocol_hash="q" * 64), "completed, consistently recorded", "r3")
    refused("gated=" + str(tmp_path / "gated"), "name=g:", "r4")
    # a fixed operator-supplied text (a hand-written control): sealed by hash, no stage records to cross-check
    fixed = tmp_path / "generic.md"
    fixed.write_text("- Think step by step.\n- Answer in the form the task asks for.\n", encoding="utf-8")
    record = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "fixed"), str(tmp_path),
                          benchmark="bigcodebench", parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE,
                          learning_version="v11", references=(good, f"generic=f:{fixed}"), **study)
    value = read_json(tmp_path / "fixed/manifest.json", sealed=True)
    by = {r["name"]: r for r in value["active_evidence"]["reference_skills"]}
    assert by["generic"]["skill"] == fixed.read_text(encoding="utf-8") and by["gated"]["skill"] == "Baseline guidance."
    assert by["generic"]["source"]["action"] == "fixed_text"
    assert by["generic"]["source"]["skill_sha256"] == hashlib.sha256(fixed.read_bytes()).hexdigest()
    assert by["generic"]["source"]["skill_bytes"] == len(fixed.read_bytes())
    assert [r["name"] for r in record["reference_skills"]] == ["gated", "generic"]
    assert all("skill" not in r for r in record["reference_skills"])
    assert ae.validate_manifest(value, read_json(tmp_path / "fixed/panel.json")) == value
    empty = tmp_path / "empty.md"
    empty.write_text(" \n", encoding="utf-8")
    refused(f"generic=f:{empty}", "not empty", "r6")
    refused(f"generic=f:{tmp_path / 'missing.md'}", "existing file", "r7")
    oversize = tmp_path / "big.md"
    oversize.write_text("x" * 40000, encoding="utf-8")
    with pytest.raises(ValueError):
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "r8"), str(tmp_path), benchmark="bigcodebench",
                     parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE, learning_version="v11",
                     references=(f"generic=f:{oversize}",), **study)
    # references are refused outside the matched-branch study
    with pytest.raises(ValueError, match="belong to the matched-branch study"):
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "r5"), str(tmp_path), benchmark="bigcodebench",
                     parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE, learning_version="v11",
                     arms={"feedback": "diagnosis_research", "post_update": "challenge_replay"}, references=(good,))


def test_prepare_seals_the_screened_update_mode_and_the_selection_study(tmp_path, monkeypatch):
    """``--arm-update screened``: the update mode is sealed in the manifest and the stage record; the selection study
    requires it; the baseline methods refuse it."""
    split_path, _ = _fixture_study(tmp_path, monkeypatch)
    common = dict(benchmark="bigcodebench", parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE,
                  learning_version="v11")
    record = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "screened"), str(tmp_path),
                          arms={"feedback": "diagnosis_research", "post_update": "matched_selection_branch"},
                          update_mode="screened", **common)
    value = read_json(tmp_path / "screened/manifest.json", sealed=True)
    assert record["update_mode"] == value["active_evidence"]["update_mode"] == "screened"
    assert record["arms"]["post_update"] == "matched_selection_branch" and record["limits"]["replay_rows"] == 0
    assert (record["limits"]["fresh_tasks"], record["limits"]["min_paired_known"], record["limits"]["screen_alpha_permille"]) == (32, 29, 100)
    assert ae.validate_manifest(value, read_json(tmp_path / "screened/panel.json")) == value
    native = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "native"), str(tmp_path),
                          arms={"feedback": "diagnosis_research", "post_update": "challenge_replay"}, **common)
    assert native["update_mode"] == "native"
    with pytest.raises(ValueError, match="needs update_mode screened"):
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "bad"), str(tmp_path),
                     arms={"feedback": "diagnosis_research", "post_update": "matched_selection_branch"}, **common)
    with pytest.raises(ValueError, match="belong to the active-evidence method"):
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "bad2"), str(tmp_path), benchmark="bigcodebench",
                     parent="none", val_source=None, seed=3, method="skillopt", learning_version="v8", update_mode="screened")


def test_prepare_can_enlarge_the_step_subset_and_the_larger_draw_contains_the_default_one(tmp_path, monkeypatch):
    """``--train-families``: development tasks a validation split would have used go to learning; the seeded ranking
    is unchanged (nested subsets), the reserved pool and the effective limits shrink, and nothing can shrink the frozen
    default."""
    split_path, _ = _fixture_study(tmp_path, monkeypatch)
    common = dict(benchmark="bigcodebench", parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE,
                  learning_version="v11", arms={"feedback": "scalar", "post_update": "challenge_replay"})
    small = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "small"), str(tmp_path), **common)
    large = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "large"), str(tmp_path),
                         train_families=16, **common)
    assert small["train_tasks"] == 8 and large["train_tasks"] == 16 and large["challenge_tasks"] == 24
    assert set(small["train_families"]) < set(large["train_families"])
    assert large["train_spec"]["families"] == 16 and large["train_spec_default"]["families"] == 8
    assert (large["limits"]["fresh_tasks"], large["limits"]["min_paired_known"], large["eligible_fresh_tasks"]) == (24, 22, 24)
    value = read_json(tmp_path / "large/manifest.json", sealed=True)
    assert ae.validate_manifest(value, read_json(tmp_path / "large/panel.json")) == value
    with pytest.raises(ValueError, match="only enlarge"):
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "bad"), str(tmp_path), train_families=4, **common)
    # a reference Skill learned on the default subset stays admissible for the larger stage's (smaller) pool
    with pytest.raises(ValueError, match="belong to the active-evidence method"):
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "bad2"), str(tmp_path), benchmark="bigcodebench",
                     parent="none", val_source=None, seed=3, method="skillopt", learning_version="v8", train_families=16)


def test_references_are_refused_on_selection_exposure_and_study_branches_are_loadable(tmp_path, monkeypatch):
    """Codex round 3: a ``g:`` reference that a v11 stage SELECTED on fresh panels overlapping this stage's holdout
    pool is refused (training-family disjointness alone is not holdout eligibility); an unselected branch candidate
    of a completed matched-scalar study is loadable as ``m:<dir>:comparator|treatment``; both stay admissible for an
    enlarged step subset only when no pool task was used to select them."""
    from skillopt.validator_pilot.api import digest

    split_path, dev_panel = _fixture_study(tmp_path, monkeypatch)
    split_hash = read_json(split_path, sealed=True)["record_hash"]
    study = dict(benchmark="bigcodebench", parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE,
                 learning_version="v11", arms={"feedback": "diagnosis_research", "post_update": "matched_scalar_branch"})
    probe = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "probe"), str(tmp_path), **study)
    step = probe["train_families"]
    pool_tasks = [t for t in read_json(tmp_path / "probe/panel.json")["tasks"] if t["family_id"] not in set(step)]

    def stage_dir(name, *, method="skillopt", arms=None, action="selected_update", skill="Kept guidance.", extra=None):
        root = tmp_path / name
        stage = seal({"version": tool.VERSION, "protocol_hash": "p" * 64, "study": str(tmp_path / "study"),
                      "split_hash": split_hash, "benchmark": "bigcodebench", "method": method,
                      "learning_version": "x", "train_families": step, "selection_tasks": 0,
                      "manifest_hash": digest(name), **({"arms": arms} if arms else {})})
        write_json(root / "stage.json", stage)
        write_json(root / "learned.json", seal({"stage_hash": stage["record_hash"], "status": "completed", "action": action,
                                                "skill": skill, "skill_sha256": hashlib.sha256(skill.encode()).hexdigest(),
                                                **(extra or {})}))
        return root

    def study_records(root, arms, texts):
        """A completed matched-scalar study's sealed branch proposals, chain and learning result, bound together."""
        matched = {}
        for branch, (folder, text) in texts.items():
            proposal = seal({"status": "candidate_ready", "candidate_skill": text})
            write_json(root / "learning" / folder / "0" / "result.json", proposal)
            matched[branch] = {"proposal_hash": proposal["record_hash"], "skill_hash": digest(text)}
        chain = seal({"matched": matched, "manifest_hash": digest(root.name), "step": 0, "arms": arms})
        write_json(root / "learning/chain/0.json", chain)
        result = seal({"status": "completed", "evidence_chain_hashes": [chain["record_hash"]]})
        write_json(root / "learning/result.json", result)
        return {"learning_result_hash": result["record_hash"], "evidence_chain_hashes": [chain["record_hash"]]}

    def prepare(output, *references, **extra):
        return tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / output), str(tmp_path),
                            references=references, **{**study, **extra})

    # a v11 method-mode stage that kept its Skill on a fresh panel containing a pool task of the new stage: refused
    kept = stage_dir("kept", method=tool.ACTIVE_EVIDENCE, arms={"feedback": "scalar", "post_update": "challenge_replay"})
    write_json(kept / "learning/challenge/0/draw.json", seal({"fresh": [{"task_hash": digest(pool_tasks[0])}]}))
    with pytest.raises(ValueError, match="selected on tasks of this stage's holdout pool"):
        prepare("r1", f"kept=g:{kept}")
    # the same stage is admissible when its fresh panel never touched the new stage's pool
    clean = stage_dir("clean", method=tool.ACTIVE_EVIDENCE, arms={"feedback": "scalar", "post_update": "challenge_replay"})
    write_json(clean / "learning/challenge/0/draw.json", seal({"fresh": [{"task_hash": "0" * 64}]}))
    record = prepare("r2", f"clean=g:{clean}")
    assert record["reference_skills"][0]["selection_exposure"].startswith("none on this stage's holdout pool")
    # an unselected study branch candidate
    study_arms = {"feedback": "diagnosis_research", "post_update": "matched_scalar_branch"}
    texts = {"comparator": ("native_matched", "Scalar branch guidance."), "treatment": ("native", "Diagnosis branch guidance.")}
    binding = study_records(tmp_path / "studied", study_arms, texts)
    study_stage = stage_dir("studied", method=tool.ACTIVE_EVIDENCE, action="completed_no_update", skill="", arms=study_arms,
                            extra=binding)
    # ... the study's own holdout draw overlaps the pool, which is fine: nothing was selected on it
    write_json(study_stage / "learning/challenge/0/draw.json", seal({"fresh": [{"task_hash": digest(pool_tasks[0])}]}))
    record = prepare("r3", f"s128=m:{study_stage}:comparator", f"m128=m:{study_stage}:treatment", train_families=16)
    value = read_json(tmp_path / "r3/manifest.json", sealed=True)
    by = {r["name"]: r for r in value["active_evidence"]["reference_skills"]}
    assert by["s128"]["skill"] == "Scalar branch guidance." and by["m128"]["skill"] == "Diagnosis branch guidance."
    assert by["s128"]["source"]["action"] == "study_branch:comparator" and "unselected" in by["s128"]["source"]["selection_exposure"]
    assert record["train_tasks"] == 16 and len(record["reference_skills"]) == 2
    # the reflection ceiling grows with the enlarged step subset (two updater branches on twice the rows)
    assert record["budget"]["max_reflection_calls"] == 2 * tool.BUDGET_V11["max_reflection_calls"] == value["budget"]["max_reflection_calls"]
    # Codex round 4: another study's sealed chain AND matching proposal transplanted into this stage directory are
    # refused -- the chain must be the completed stage's own step-0 chain
    other = tmp_path / "other"
    study_records(other, study_arms, {"comparator": ("native_matched", "Foreign text."), "treatment": ("native", "Foreign text 2.")})
    transplanted = stage_dir("transplanted", method=tool.ACTIVE_EVIDENCE, action="completed_no_update", skill="",
                             arms=study_arms, extra=study_records(tmp_path / "transplanted", study_arms, texts))
    for name in ("learning/chain/0.json", "learning/native_matched/0/result.json"):
        (transplanted / name).write_text((other / name).read_text())
    with pytest.raises(ValueError, match="own sealed step-0 chain"):
        prepare("r7", f"x=m:{transplanted}:comparator")
    # the same study stage as a g: reference is its carried (empty) parent -- allowed, it was never selected on the pool
    # by a decision; a tampered branch record, an unknown branch name and a non-study stage are refused
    with pytest.raises(ValueError, match="study branch is given as"):
        prepare("r4", f"x=m:{study_stage}:other")
    # the same unselected branch can be the PARENT of a refinement stage (a frozen base); the stage record binds it
    monkeypatch.setattr(tool, "parent_skill", REAL_PARENT_SKILL)
    refine = prepare("p1", parent=f"m:{study_stage}:comparator",
                     arms={"feedback": "diagnosis_research", "post_update": "matched_selection_branch"}, update_mode="screened")
    assert refine["parent"] == f"m:{study_stage}:comparator" and refine["parent_skill_sha256"] == by["s128"]["source"]["skill_sha256"]
    assert read_json(tmp_path / "p1/manifest.json", sealed=True)["parent_skill"] == "Scalar branch guidance."
    assert refine["parent_proposal_hash"] == by["s128"]["source"]["proposal_hash"]
    with pytest.raises(ValueError, match="v11 matched study stage"):
        prepare("r5", f"x=m:{clean}:comparator")
    write_json(tmp_path / "tampered.json", seal({"status": "candidate_ready", "candidate_skill": "Other text."}))
    (study_stage / "learning/native/0/result.json").write_text((tmp_path / "tampered.json").read_text())
    with pytest.raises(ValueError, match="recorded unselected branch candidate"):
        prepare("r6", f"x=m:{study_stage}:treatment")


def test_a_fixed_text_can_be_the_parent_and_the_empty_skill_a_named_reference(tmp_path, monkeypatch):
    """``--parent f:<file>`` (learning v11 only): a fixed operator-supplied text is the starting Skill of the step,
    bound by its hash and re-verified whenever the stage is loaded; under such a parent the EMPTY Skill may be a named
    evaluation-only reference (``name=none``), which an empty parent already is."""
    split_path, _ = _fixture_study(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "parent_skill", REAL_PARENT_SKILL)
    study = dict(benchmark="bigcodebench", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE, learning_version="v11",
                 arms={"feedback": "diagnosis_research", "post_update": "matched_scalar_branch"})
    fixed = tmp_path / "generic.md"
    fixed.write_text("- Think step by step.\n- Answer in the form the task asks for.\n", encoding="utf-8")

    def prepare(output, parent, *references, **extra):
        return tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / output), str(tmp_path),
                            parent=parent, references=references, **{**study, **extra})

    record = prepare("fromgeneric", f"f:{fixed}", "empty=none")
    value = read_json(tmp_path / "fromgeneric/manifest.json", sealed=True)
    assert value["parent_skill"] == fixed.read_text(encoding="utf-8")
    assert record["parent"] == f"f:{fixed}" and record["parent_action"] == "fixed_text" and record["parent_stage_hash"] is None
    assert record["parent_skill_sha256"] == hashlib.sha256(fixed.read_bytes()).hexdigest()
    reference = value["active_evidence"]["reference_skills"]
    assert [(r["name"], r["skill"], r["source"]["action"]) for r in reference] == [("empty", "", "empty_skill")]
    assert record["reference_skills"] == [{"name": "empty", **reference[0]["source"]}]
    assert ae.validate_manifest(value, read_json(tmp_path / "fromgeneric/panel.json")) == value
    assert tool._load(str(tmp_path / "fromgeneric"))[1] == record
    # a method-mode stage can start from the fixed text too (no references there)
    method = prepare("method", f"f:{fixed}", arms={"feedback": "scalar", "post_update": "challenge_replay"})
    assert method["parent_action"] == "fixed_text" and method["reference_skills"] == []
    # the empty Skill is not a named reference under an empty parent; an empty or missing parent file is refused
    with pytest.raises(ValueError, match="already this stage's parent reference"):
        prepare("r1", "none", "empty=none")
    blank = tmp_path / "blank.md"
    blank.write_text(" \n", encoding="utf-8")
    with pytest.raises(ValueError, match="not empty"):
        prepare("r2", f"f:{blank}")
    with pytest.raises(ValueError, match="existing file"):
        prepare("r3", f"f:{tmp_path / 'missing.md'}")
    with pytest.raises(ValueError, match="absolute path"):
        prepare("r5", "f:generic.md")
    # the older methods do not take a fixed-text parent
    with pytest.raises(ValueError, match="learning v11 option"):
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "r4"), str(tmp_path), benchmark="bigcodebench",
                     parent=f"f:{fixed}", val_source=None, seed=3, method="skillopt", learning_version="v8")
    # the text is bound for the life of the stage: an edited file no longer loads
    fixed.write_text("- Think step by step.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Parent changed"):
        tool._load(str(tmp_path / "fromgeneric"))


def test_prepare_seals_an_analyst_prompt_profile(tmp_path, monkeypatch):
    split_path, _ = _fixture_study(tmp_path, monkeypatch)
    common = dict(benchmark="bigcodebench", parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE,
                  learning_version="v11", arms={"feedback": "scalar", "post_update": "none"})
    record = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "p"), str(tmp_path),
                          analyst_profile="generalize_v1", **common)
    assert record["analyst_profile"] == "generalize_v1"
    assert read_json(tmp_path / "p/manifest.json", sealed=True)["active_evidence"]["analyst_profile"] == "generalize_v1"
    plain = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "q"), str(tmp_path), **common)
    assert "analyst_profile" not in plain
    with pytest.raises(ValueError, match="belong to the active-evidence method"):
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "r"), str(tmp_path), benchmark="bigcodebench",
                     parent="none", val_source=None, seed=3, method="skillopt", learning_version="v8",
                     analyst_profile="generalize_v1")


def test_prepare_limit_overrides_cover_diagnosis_shape_only(tmp_path, monkeypatch):
    """``--limit key=integer``: the shape of diagnosis / update may be overridden (validated by the protocol's ranges
    and recorded); the decision's and the screen's operating points may not."""
    split_path, _ = _fixture_study(tmp_path, monkeypatch)
    common = dict(benchmark="bigcodebench", parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE,
                  learning_version="v11", arms={"feedback": "diagnosis_research", "post_update": "challenge_replay"})
    record = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "wide"), str(tmp_path),
                          limits=("view_rows=64", "max_hypotheses=6"), **common)
    value = read_json(tmp_path / "wide/manifest.json", sealed=True)
    assert record["limit_overrides"] == {"view_rows": 64, "max_hypotheses": 6}
    assert value["active_evidence"]["limits"]["view_rows"] == 64 and value["active_evidence"]["limits"]["max_hypotheses"] == 6
    assert record["limits_requested"]["view_rows"] == 16 and record["limits"]["fresh_tasks"] == 32
    for bad in ("fresh_tasks=200", "decision_alpha_permille=100", "screen_alpha_permille=300", "min_paired_known=1",
                "view_rows", "view_rows=many", "unknown=3"):
        with pytest.raises(ValueError, match="limit override"):
            tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / ("bad" + bad[:6])), str(tmp_path),
                         limits=(bad,), **common)
    with pytest.raises(ValueError):  # out of the protocol's range
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "range"), str(tmp_path),
                     limits=("view_rows=500",), **common)
    with pytest.raises(ValueError, match="limit override"):
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "twice"), str(tmp_path),
                     limits=("view_rows=32", "view_rows=64"), **common)
    plain = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "plain"), str(tmp_path), **common)
    assert plain["limit_overrides"] == {} and "train_panel_rows" not in plain["limits"]
    # the optional in-sample panel: sized at preparation, absent by default, refused outside the method's challenge
    shadow = tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "shadow"), str(tmp_path),
                          limits=("train_panel_rows=64",), **common)
    assert shadow["limits"]["train_panel_rows"] == 64 and shadow["limit_overrides"] == {"train_panel_rows": 64}
    assert {k: v for k, v in shadow["limits"].items() if k != "train_panel_rows"} == plain["limits"]
    with pytest.raises(ValueError, match="post-update challenge only"):
        tool.prepare(str(tmp_path / "study"), str(split_path), str(tmp_path / "study-panel"), str(tmp_path),
                     limits=("train_panel_rows=64",),
                     **{**common, "arms": {"feedback": "diagnosis_research", "post_update": "matched_scalar_branch"}})
