"""coevo5 smoke (registration §14 step 5; v2 delta §11; v3 delta §2, §11) end to end, offline: v3's chain I-ds from the
instructions -- first the format check, then its SearchQA and OfficeQA stages on the head of the registered training
draws with the scripted roles of the stage tests, every GLM-5.3 call charged to the pre-launch ledger beside the
imported v1 texts and every deepseek call to deepseek's own scopes of that ledger; the paths the first stage did not
reach (v3: the self-test's revision call too) run once on its first proposal; a failed format check ends the smoke; a
paused smoke waits for the owner; the summary reads what ran with zero calls and is what the launch manifest's
generator accepts."""
import functools
import json

import pytest

from scripts import run_coevo5
from skillopt.coevo5 import analyst, manifest, prelaunch, research, smoke, step, texts
from skillopt.coevo5 import data as data_module
from skillopt.coevo5.budget import DEEPSEEK, OVERALL, Budget, chain_scope, deepseek_scope, step_scope
from skillopt.coevo5.protocol import DATA_SEED
from skillopt.coevo5.skill import Skill
from skillopt.coevo5.units import Setting, unit_path
from skillopt.continual_eval.core import read_json, write_json
from tests.coevo5_fakes import USAGE, Script
from tests.test_coevo5_prelaunch import _existing, _page, _writer
from tests.test_coevo5_step import OFFICE_RULE, SEARCH_RULE, _forward, _pool, _roles, _runs
from tests.test_coevo5_step import _solver as _step_solver

DRAW = {"searchqa": 16, "officeqa": 16}


def _found(roles, sources, **kw):
    return {"purpose": kw["purpose"], "question": kw["question"], "status": "found", "conclusion": "Exact strings.",
            "quotes": [{"page": "p", "text": "exact"}], "calls": 3, "log": [{"round": 1}]}


def _solver(system, payload):
    """Three SearchQA items in four fail without the rule (the stage's support does not hang on the seeded halves)."""
    question = payload.get("question", "")
    if question.startswith("SQ"):
        n = int(question[2:])
        return "<answer>%s</answer>" % ("ans%d" % n if SEARCH_RULE in system or n % 4 == 0 else "wrong")
    return _step_solver(system, payload)


def _smoke_roles(state):
    """The stage tests' roles, the analyst's rule by its section (SearchQA -- ``state["search_rule"]`` when given --
    then OfficeQA); with ``state["local"]`` the analyst proposes a local rule that asks ``state["questions"]`` (none
    by default)."""
    base = _roles(state)

    def answer(system, payload):
        if system == analyst.ANALYST_SYSTEM:
            if state.get("fail"):
                raise RuntimeError("the analyst's route is down")
            state["rule"] = state.get("search_rule", SEARCH_RULE) if payload["section"] == "SearchQA" else OFFICE_RULE
            reply = base(system, payload)
            if state.get("local"):
                reply = {"rules": [{**reply["rules"][0], "placement": "local", "questions": state.get("questions", [])}],
                         "transfer": {"none": "a fix of this kind only"}}
            return reply
        return base(system, payload)
    return answer


@pytest.fixture
def smoked(tmp_path, monkeypatch):
    """A smoke specification in the pre-launch directory ``pre`` beside the v1 texts imported there (written in
    ``pre-v1``, charged to its ledger), with its scripted client."""
    name = smoke.CHAIN
    monkeypatch.setattr(research, "request", _found)
    monkeypatch.setattr(step.forward, "build_panel", lambda roles, **kw: _forward(kw["rule_id"], kw["target"]))
    rollout = {**data_module.TRAIN_ROLLOUT, "searchqa": (20, 2), "officeqa": (16, 2)}
    monkeypatch.setattr(data_module, "TRAIN_ROLLOUT", rollout)
    monkeypatch.setattr(step, "TRAIN_ROLLOUT", rollout)
    pools = {"searchqa": _pool("searchqa", 30), "officeqa": _pool("officeqa", 16)}
    monkeypatch.setattr(data_module, "pin", lambda config: {"fixture": True})
    monkeypatch.setattr(data_module, "pool", lambda pinned, bench: [dict(t) for t in pools[bench]])
    monkeypatch.setattr(smoke.backends, "readiness", lambda bench, runtime: {"status": "ready"})
    monkeypatch.setattr(smoke, "FORMAT_BENCHES", smoke.BENCHES)  # SpreadsheetBench and LiveMath: not in the fixture
    monkeypatch.setattr(smoke, "FORMAT_ITEMS", 4)
    state = {"rule": SEARCH_RULE, "solver": _solver}
    script = Script(_smoke_roles(state))
    monkeypatch.setattr(smoke.manifest, "_clients", lambda config: lambda model, max_tokens, timeout: script)
    monkeypatch.setattr(smoke, "Setting", functools.partial(Setting, cooldown=0))
    pre, written = tmp_path / "pre", prelaunch.TEXTS_VERSION
    monkeypatch.setattr(prelaunch, "TEXTS_VERSION", "fivebench-coevolution-v1-texts")  # as v1 wrote them
    prelaunch.prepare_texts(tmp_path / "pre-v1" / "texts", {b: _existing(tmp_path, b) for b in prelaunch.EXISTING},
                            _writer())
    monkeypatch.setattr(prelaunch, "TEXTS_VERSION", written)
    prelaunch.import_texts(pre / "texts", tmp_path / "pre-v1" / "texts" / "texts.json")
    prelaunch.build_archive(tmp_path / "archive", fetch=_page)
    record = smoke.make(pre / "smoke", texts_record=pre / "texts" / "texts.json", archive=tmp_path / "archive",
                        repo=tmp_path / "repo", deepseek_env=tmp_path / "pjlab-token.env", proxy=None,
                        research_proxy=None, workers=4, draw=DRAW)
    return {"pre": pre, "spec": pre / "smoke" / prelaunch.SMOKE_RECORD, "record": record, "state": state,
            "script": script, "pools": pools, "chain": name}


def _glm(script):
    """The scripted client's calls that are not the solver's: the GLM-5.3 method roles."""
    return [s for s in script.seen if not s[0].startswith("Solve the supplied task")]


def test_the_smoke_runs_two_stages_on_the_draws_head_charged_to_the_pre_launch_ledger(smoked):
    found = smoke.run(smoked["spec"])
    name = smoked["chain"]
    root = smoked["pre"] / "smoke" / name
    assert found["chain"] == name == "I-ds"
    assert found["status"] == "complete" and found["run"] == smoked["record"]["record_hash"]
    assert read_json(smoked["pre"] / "smoke" / prelaunch.SMOKE_SUMMARY) == found
    assert {"s%d/%s" % (k, u) for k in (1, 2) for u in ("train", "prepare", "selftest", "screen", "confirm", "merge")
            } | {"s0/format-check", "s1/smoke-paths"} == set(found["units"])
    # v3 §2: the format check -- three Skills on the first items of each bench's draw, once each
    checked = found["format_check"]
    assert checked["passed"] is True and checked["failing"] == []
    assert checked["shares"] == {s: {b: "1" for b in smoke.BENCHES} for s in ("E", "I", "empty")}
    assert sum(found["units"]["s0/format-check"]["attempts"][0]["cells"].values()) == 3 * 2 * 4
    systems = {system for system, _ in smoked["script"].seen[:24]}
    guided = [t for t in systems if "Frozen skill guidance" in t]
    assert len(systems) == 3 and len(guided) == 2  # E's scaffold, I's instructions; the empty Skill has none
    assert all(t.index("<answer>") < t.index("Frozen skill guidance") for t in guided)  # v3 §2: the contract first
    assert all(u["complete"] and len(u["attempts"]) == 1 for u in found["units"].values())
    # the smaller draws are the heads of the registered seeded orders, with the registered runs per item
    for stage, bench in enumerate(smoke.BENCHES, 1):
        trained = read_json(unit_path(root, stage, "train") / "unit.json", sealed=True)["result"]
        head = data_module.training_items(smoked["pools"][bench], bench, DATA_SEED, size=DRAW[bench])
        assert sorted(trained["tokens"]) == [step.key(bench, t["task_id"]) for t in head]
        assert all(len(tokens) == 2 for tokens in trained["tokens"].values())
    # v3: the chain starts from the instructions; the first stage's merge is the second stage's parent
    first = Skill.from_json(read_json(unit_path(root, 1, "merge") / "unit.json", sealed=True)["result"]["skill"])
    assert not first.scaffold and dict(first.seeds) and first.rules[0].sections == ("searchqa", "officeqa")
    one, two = found["stages"]["1"], found["stages"]["2"]  # each reached its research and its forward panels
    assert one["proposals"] == 1 and one["research"]["requests"] == 1 and one["research"]["found"] == 1
    assert one["forward"] == {"s1-r1:officeqa": {"status": "ok", "items": 12}}
    assert one["selftest"] == {"tested": 1, "round1_passed": 1, "reply": None, "revisions": {}, "round2_passed": 0}
    assert one["excluded"] == {"screen": 0, "confirm": 0}
    # the rule passed its self-test: the revision call runs once on its own (its reply never tested)
    assert found["paths"] == {"rule": "s1-r1", "revision": {"status": "valid", "rule": "s1-r1",
                                                             "reply": {"s1-r1": None}, "dropped": []}}
    assert one["accepted"] == [{"id": "s1-r1", "placement": "similar"}]
    assert one["analyst"]["transfer"] == {"rule": 1, "status": "named"}
    assert two["forward"] == {"s2-r1:livemath": {"status": "ok", "items": 12}}
    assert two["accepted"] == [{"id": "s2-r1", "placement": "similar"}] and two["rounds"] == ["screen", "confirm"]
    # the second stage checks SearchQA's regression panel (as a launch draws it): the parent twice, a rule once
    panel = data_module.regression_items(smoked["pools"]["searchqa"], "searchqa", DATA_SEED)
    runs = _runs(unit_path(root, 2, "screen"))
    assert {runs[("parent", step.key("searchqa", t["task_id"]))] for t in panel} == {2}
    assert {runs[("s2-r1:similar", step.key("searchqa", t["task_id"]))] for t in panel} == {1}
    # every call is charged to the pre-launch ledger: the GLM-5.3 roles to the chain's scopes, the deepseek solver to
    # deepseek's own (v3 §9); the imported texts cost nothing here
    glm = len(_glm(smoked["script"]))
    solved = len(smoked["script"].seen) - glm
    spent = Budget(smoked["pre"] / "ledger").snapshot()
    assert spent[chain_scope(name)]["settled"] == glm * USAGE["total_tokens"] and solved > glm > 0
    assert spent[DEEPSEEK]["settled"] == spent[deepseek_scope(name)]["settled"] == solved * USAGE["total_tokens"]
    for stage, bench in enumerate(smoke.BENCHES, 1):
        solver = found["units"]["s%d/train" % stage]["attempts"][0]["solver_charged"]
        assert solver == 2 * DRAW[bench] * USAGE["total_tokens"]
    assert spent[OVERALL]["settled"] == glm * USAGE["total_tokens"] and spent[OVERALL]["open"] == 0
    assert spent[OVERALL]["cap"] == prelaunch.PRELAUNCH_CAP and found["ledger"] == spent
    assert found["code_changed_since_smoke"] == [] and found["environment_changed"] is False
    # what the launch manifest's generator reads of it
    assert prelaunch._smoke(smoked["pre"] / "smoke", smoked["pre"] / "ledger", manifest.pin_code()) == {
        "path": str(smoked["pre"] / "smoke"), "record_hash": found["run"], "chain": name, "status": "complete",
        "changed_since": []}
    assert prelaunch.prior_usage(smoked["pre"] / "ledger")["total"] == spent[OVERALL]["settled"]
    calls = len(smoked["script"].seen)  # a completed smoke runs nothing again
    assert smoke.run(smoked["spec"])["status"] == "complete" and len(smoked["script"].seen) == calls


def test_paths_the_stage_did_not_reach_run_once_on_its_first_proposal(smoked):
    smoked["state"]["local"] = True  # a local rule asking nothing: no research request, no forward panel
    found = smoke.run(smoked["spec"])
    assert found["status"] == "complete" and found["stages"]["1"]["research"]["requests"] == 0
    assert found["stages"]["1"]["forward"] == {}
    paths = found["paths"]
    assert paths["rule"] == "s1-r1" and paths["research"] == {"question": smoke.QUESTION, "status": "found", "calls": 3}
    assert paths["rewrite"] == {"status": "rewritten", "before": SEARCH_RULE, "after": SEARCH_RULE + " Keep it exact."}
    assert paths["forward"] == {"status": "ok", "items": 12, "counts": {}}
    unit = unit_path(smoked["pre"] / "smoke" / smoke.CHAIN, 1, smoke.PATHS)
    record = read_json(unit / "unit.json", sealed=True)
    assert record["identity"]["reached"] == {"research": False, "forward": False, "revision": False}
    assert paths["revision"]["status"] == "valid"
    assert {p.name for p in (unit / record["attempt"]).iterdir()} >= {"research.json", "forward.json", "roles.json"}
    assert found["units"]["s1/smoke-paths"]["attempts"][0]["roles"]["research_rewrite"]["calls"] == 1
    spent = Budget(smoked["pre"] / "ledger").snapshot()  # the paths are charged to the first stage's learning scopes
    rows = [a for unit, row in found["units"].items() if unit.startswith("s1/") for a in row["attempts"]]
    roles = sum(r["charged"] for a in rows for r in a["roles"].values())
    assert spent[step_scope(smoke.CHAIN, 1, "learning")]["settled"] == roles > 0
    assert spent[deepseek_scope(smoke.CHAIN, 1, "learning")]["settled"] == sum(a["solver_charged"] for a in rows) > 0


@pytest.mark.parametrize("rule, questions, research", [
    # the rule holds a SearchQA training answer ("ans12", v2 §7): no research request, no forward material
    ("Copy the exact answer, never ans12.", [], {"status": "not_dispatched", "rule_hit": "answer_word"}),
    # a question that holds one is not sent; the fallback question is
    (SEARCH_RULE, ["Is ans12 the answer?"], {"question": smoke.QUESTION, "status": "found", "calls": 3}),
])
def test_the_paths_send_nothing_the_production_screens_forbid(smoked, monkeypatch, rule, questions, research):
    sent = []
    monkeypatch.setattr(smoke.research, "request", lambda roles, sources, **kw: sent.append(kw) or _found(
        roles, sources, **kw))
    smoked["state"].update(local=True, search_rule=rule, questions=questions)
    found = smoke.run(smoked["spec"])
    assert found["status"] == "complete" and found["stages"]["1"]["research"]["requests"] == 0
    paths = found["paths"]
    assert {k: paths["research"][k] for k in research} == research
    if research["status"] == "not_dispatched":
        assert paths["forward"] == {"status": "not_dispatched", "rule_hit": "answer_word"} and "rewrite" not in paths
    first = [kw for kw in sent if "/s1/" in kw["label"]]  # SearchQA's (OfficeQA's training answers are numbers)
    assert all("ans12" not in kw["rule"] and "ans12" not in kw["question"] for kw in first)
    assert len(first) == (research["status"] != "not_dispatched")


def test_a_paused_smoke_waits_for_the_owner_and_is_never_accepted(smoked, capsys):
    smoked["state"]["fail"] = True
    assert run_coevo5.main(["smoke", "--spec", str(smoked["spec"])]) == 3
    found = read_json(smoked["pre"] / "smoke" / prelaunch.SMOKE_SUMMARY)
    assert (found["status"], found["kind"]) == ("paused", "exception")
    assert found["units"]["s1/prepare"]["attempts"][0]["status"] == "exception"
    calls = len(smoked["script"].seen)
    smoked["state"]["fail"] = False  # the route recovered: the unit still waits for the owner's decision
    again = smoke.run(smoked["spec"])
    assert (again["status"], again["kind"]) == ("paused", "awaiting_owner_decision")
    assert len(smoked["script"].seen) == calls and "s2/train" not in again["units"]
    with pytest.raises(ValueError, match="did not complete"):
        prelaunch._smoke(smoked["pre"] / "smoke", smoked["pre"] / "ledger", manifest.pin_code())


def test_the_smoke_is_made_beside_its_texts_on_the_registered_archive(smoked, tmp_path, capsys, monkeypatch):
    pre, texts_record = smoked["pre"], smoked["pre"] / "texts" / "texts.json"
    spec, value = smoke.setting(smoked["spec"])  # the roles read the run's contract (v3, v2 layout)
    assert value.cards == texts.solver_cards(texts.CARDS, spec["runtime"]) != texts.CARDS
    options = {"texts_record": texts_record, "archive": tmp_path / "archive", "repo": tmp_path / "repo",
               "deepseek_env": tmp_path / "pjlab-token.env", "proxy": None, "research_proxy": None, "workers": 4}
    refused = [(tmp_path / "elsewhere" / "smoke", {}),  # another pre-launch directory: another ledger
               (pre / "smoke", {}),  # an existing smoke
               (pre / "smoke-2", {"draw": {"searchqa": 0, "officeqa": 2}}),
               (pre / "smoke-3", {"draw": {"searchqa": 16}})]
    for out, change in refused:
        with pytest.raises(ValueError):
            smoke.make(out, **{**options, **change})
    index = (tmp_path / "archive" / "index.json").read_bytes()
    (tmp_path / "archive" / "notes.txt").write_text("the answer is 42", encoding="utf-8")
    (tmp_path / "archive" / "index.json").write_text(json.dumps({**json.loads(index), "notes.txt": {
        "sha256": data_module.sha(tmp_path / "archive" / "notes.txt"), "title": "Notes"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="other documents"):  # an indexed document beyond the registered roster
        smoke.make(pre / "smoke-4", **options)
    (tmp_path / "archive" / "index.json").write_bytes(index)
    arguments = ["smoke-make", "--out", str(pre / "smoke-5"), "--texts", str(texts_record), "--archive",
                 str(tmp_path / "archive"), "--repo", str(tmp_path / "repo"), "--deepseek-env",
                 str(tmp_path / "pjlab-token.env"), "--searchqa-items", "12"]
    with pytest.raises(SystemExit):  # v3: a deepseek learning chain only
        run_coevo5.main(arguments + ["--chain", "E-glm"])
    with pytest.raises(ValueError, match="deepseek learning chain"):
        smoke.make(pre / "smoke-6", **options, chain_name="NoSkill-ds")
    monkeypatch.setattr(smoke, "FORMAT_BENCHES", ("searchqa", "spreadsheetbench"))
    with pytest.raises(ValueError, match="qualifications"):  # the format check's SpreadsheetBench items
        smoke.make(pre / "smoke-7", **options)
    monkeypatch.setattr(smoke, "FORMAT_BENCHES", smoke.BENCHES)
    assert run_coevo5.main(arguments) == 0
    made = read_json(pre / "smoke-5" / prelaunch.SMOKE_RECORD, sealed=True)
    assert made["draw"] == {"searchqa": 12, "officeqa": smoke.DRAW["officeqa"]} and made["chain"] == "I-ds"
    assert made["clients"] == {"repo": str(tmp_path / "repo"), "proxy": run_coevo5.GATEWAY,
                               "deepseek_route": "pjlab_token", "deepseek_env": str(tmp_path / "pjlab-token.env")}
    assert made["sheet_qualification"] is None and made["runtime"] == smoke.RUNTIME
    assert made["research"]["sources_sha256"] == data_module.sha(tmp_path / "archive" / "sources.json")
    assert made["code"] == manifest.pin_code() and made["environment"] == manifest.environment()


def test_the_summary_names_what_changed_since_the_smoke(smoked):
    spec = read_json(smoked["spec"], sealed=True)
    changed = {**spec, "code": {**spec["code"], "skillopt/coevo5/step.py": "0" * 64},
               "environment": {**spec["environment"], "openpyxl": "0.0"}}
    found = smoke.summary(changed)
    assert found["code_changed_since_smoke"] == ["skillopt/coevo5/step.py"] and found["environment_changed"] is True
    assert found["units"] == {} and found["stages"] == {"1": None, "2": None} and found["paths"] is None
    assert found["format_check"] is None
    write_json(smoked["pre"] / "smoke" / prelaunch.SMOKE_SUMMARY, {"run": spec["record_hash"], "status": "complete"})
    pinned = {**manifest.pin_code(), "skillopt/coevo5/gate.py": "1" * 64}  # a file changed after the smoke
    assert prelaunch._smoke(smoked["pre"] / "smoke", smoked["pre"] / "ledger", pinned)["changed_since"] == [
        "skillopt/coevo5/gate.py"]


def test_v3_a_failed_format_check_ends_the_smoke_before_its_stages(smoked):
    scaffold = Skill(scaffold=True).render()

    def solver(system, payload):
        if system.endswith(scaffold):  # with E's scaffold the solver drops the answer tag
            return "The answer is ans1."
        return _solver(system, payload)
    smoked["state"]["solver"] = solver
    found = smoke.run(smoked["spec"])
    assert (found["status"], found["kind"]) == ("format_check_failed", smoke.FORMAT)
    assert {(f["skill"], f["criterion"]) for f in found["reason"]} == {("E", "floor"), ("E", "below_empty")}
    assert found["format_check"]["shares"]["E"] == {"searchqa": "0", "officeqa": "0"}
    assert set(found["units"]) == {"s0/format-check"} and found["stages"] == {"1": None, "2": None}
    with pytest.raises(ValueError, match="did not complete"):  # no launch manifest from it
        prelaunch._smoke(smoked["pre"] / "smoke", smoked["pre"] / "ledger", manifest.pin_code())
    calls = len(smoked["script"].seen)  # run again: the recorded check decides, nothing is re-sent
    assert smoke.run(smoked["spec"])["status"] == "format_check_failed" and len(smoked["script"].seen) == calls


def test_v3_the_floor_binds_the_method_s_starts_and_reports_the_empty_skill(smoked):
    """After two checks (the owner, 2026-10-19): an empty Skill below the floor is reported and stays the margin's
    reference, but no longer stops the smoke; E's and I's shares still must reach it (the test above)."""
    def solver(system, payload):
        if "Frozen skill guidance" not in system:  # the empty Skill: the solver drops the answer tag
            return "The answer is ans1."
        return _solver(system, payload)
    smoked["state"]["solver"] = solver
    found = smoke.run(smoked["spec"])
    checked = found["format_check"]
    assert checked["passed"] and checked["failing"] == [] and smoke.FORMAT_FLOORED == ("E", "I")
    assert checked["shares"]["empty"] == {"searchqa": "0", "officeqa": "0"}
    assert checked["shares"]["E"] == checked["shares"]["I"] == {"searchqa": "1", "officeqa": "1"}
    assert found["status"] == "complete"
