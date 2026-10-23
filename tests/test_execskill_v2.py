"""v2 "train then accept" (owner decision 2026-10-23 13:3x; SkillOpt-style analysts and step buffer, owner suggestion
2026-10-23 15:1x): the configuration, the engineer's train mode (analysts, cut description, optional replay tests,
up to three fix calls, the edit budget against S, ``rebase``), the adoption rule, the step buffer and the smoke's
example-stage helpers. Offline: the engineer, analysts and leakage adjudicator are FakeGLM behind the real ``Roles``;
every procedure runs in the real worker through FakeDocker; every procedure and trajectory is a synthetic fixture."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from skillopt.coevo5.leakage import Corpus
from skillopt.execskill import budgets, engineer, manifest, protocol, smoke, step
from skillopt.execskill.package import FIXTURE, edits, empty
from skillopt.execskill.protocol import verified
from tests.execskill_fakes import engineer_reply, glm_roles
from tests.test_execskill_engineer import CARD, WORDS, new
from tests.test_execskill_replay import (CRASH, NOTE, QA, fake, qa_items, qa_trajectories, source,  # noqa: F401
                                         workers)

V1_ENGINEER_PROMPT = "c3e800576462f9f4ff7eb1cb591f09be8c95cb74c37fd6446ec0f29009c2e7f0"  # the frozen v1 main manifest
FINDING = {"pattern": "The solver misses the entity the context names.", "items": ["q1", "not-shown"],
           "helper": "List the capitalised names of the context."}
SENTENCES = """
def applies(view):
    return "context" in view

def before_call(view, state):
    return {"facts": ["The context has %d sentences." % len(view["context"])]}
"""


def configured(name):
    return SimpleNamespace(extra={"configuration": name})


def test_v2_configuration_namespaces_learning_caps_and_frozen_v1_prompts():
    assert protocol.namespace_of(configured("main-v2"), "G") == "G-v2"
    assert protocol.namespace_of(configured("main-v2"), "D") == "D-v2"
    assert protocol.namespace_of(configured("main"), "G") == "G" and protocol.namespace_of(configured("main"), "D") == "D"
    assert protocol.learning_of(configured("main-v2")) == "train" and protocol.learning_of(configured("main")) == "single"
    assert protocol.learning_of(configured(protocol.PILOT)) == "single"
    assert engineer.ENGINEER_PROMPT_SHA256 == V1_ENGINEER_PROMPT != engineer.ENGINEER_PROMPT_V2_SHA256
    v1 = {"describer", "engineer", "examiner"}  # Codex review 2026-10-23 #1: v1 manifests bind exactly these
    assert set(manifest.prompt_sha()) == set(manifest.prompt_sha("main")) == set(manifest.prompt_sha("default")) == v1
    prompts = manifest.prompt_sha("main-v2")
    assert prompts["engineer"] == V1_ENGINEER_PROMPT and set(prompts) == v1 | {"v2"}
    assert prompts["v2"] == {"engineer": engineer.ENGINEER_PROMPT_V2_SHA256, "analyst": engineer.ANALYST_PROMPT_SHA256,
                             "examiner": dict(protocol_examiner_v2())}
    assert budgets.smoke_caps()[budgets.SMOKE + ":solver"] == protocol.SMOKE_CAPS["solver"]
    assert budgets.smoke_caps(example=True)[budgets.SMOKE + ":solver"] == protocol.SMOKE_SX_CAPS["solver"]
    assert budgets.smoke_caps(example=True)[budgets.SMOKE + ":glm"] == protocol.SMOKE_SX_CAPS["glm"]
    assert smoke.max_role_calls("main") == smoke.MAX_ROLE_CALLS
    calls = smoke.max_role_calls("main-v2")
    assert calls["engineer"] == protocol.TRAIN_ROUNDS * (protocol.TRAIN_ENGINEER_CALLS + protocol.TRAIN_ANALYST_CALLS)
    assert calls["describer"] == smoke.MAX_ROLE_CALLS["describer"] and set(calls) == set(smoke.MAX_ROLE_CALLS)
    assert calls["examiner"] > smoke.MAX_ROLE_CALLS["examiner"] and calls["leakage"] > smoke.MAX_ROLE_CALLS["leakage"]
    assert smoke.engineer_request_floor("main") == smoke.ENGINEER_REQUEST_FLOOR
    assert smoke.engineer_request_floor("main-v2") == protocol.ROLE_INPUT_BYTES + max(
        len(engineer.ENGINEER_SYSTEM_V2.encode()), len(engineer.ANALYST_SYSTEM.encode()))


def protocol_examiner_v2():
    from skillopt.execskill import examiner
    return examiner.PROMPT_V2_SHA256


def test_the_v2_smoke_names_its_own_waiver_file():
    assert smoke.waiver_name({"required": ["S0", "S2", "S3", "SE6", "SX"]}) == protocol.SMOKE_WAIVER_V2
    assert smoke.waiver_name({"required": ["S0", "S2", "S3", "SE6"]}) == protocol.SMOKE_WAIVER
    assert protocol.SMOKE_WAIVER_V2 != protocol.SMOKE_WAIVER and "SX" in smoke.STAGES and "SX" in smoke.BUILT_STAGES
    assert smoke.PLAN["SX"]["searchqa"] == {"run": protocol.SX_SLICES["run"], "accept": protocol.SX_SLICES["accept"]}


def test_sx_takes_the_searchqa_smoke_items_after_s2():
    pool = [{"task_id": "sq-%03d" % n} for n in range(280)]
    items = smoke._sx_items(SimpleNamespace(pools={"searchqa": pool}))
    assert [i["task_id"] for i in items] == ["sq-%03d" % n for n in range(20, 280)]
    with pytest.raises(ValueError, match="hold SX"):
        smoke._sx_items(SimpleNamespace(pools={"searchqa": pool[:200]}))


# ------------------------------------------------------------------------------------- the engineer's train mode
def train_context(tmp_path, workers, answer, *, parent=None, base=None, round_=1, **fields):
    roles, glm = glm_roles(tmp_path / ("glm-%d" % round_), answer)
    base = base or empty(step="s0", evidence=FIXTURE)
    ctx = engineer.Context(
        bench="searchqa", k=1, step="s1", evidence=FIXTURE, parent=parent or base, trajectories=qa_trajectories(),
        corpora={"searchqa": Corpus("searchqa", qa_items())}, workers=workers, roles=roles,
        label="D/s1-searchqa/engineer-r%d" % round_, card=CARD,
        references={item: answers for item, (_, answers, token) in QA.items() if token == "fail"},
        mode=engineer.TRAIN, round=round_, base=base, current=qa_trajectories(), **fields)
    return ctx, glm


def scripted(proposal, fixes=()):
    """The analysts name one finding; the engineer proposes ``proposal`` and answers fix calls from ``fixes``; the
    leakage adjudicator keeps everything."""
    fixes = list(fixes)

    def answer(system, payload):
        if system == engineer.ANALYST_SYSTEM:
            return engineer_reply({"findings": [FINDING, {"items": ["q3"]}]}, [])
        if system == engineer.ENGINEER_SYSTEM_V2:
            return fixes.pop(0) if payload["request"] == "fix" else proposal
        return {"verdict": "no", "reason": "It names no reference answer."}

    return answer


def coded(description, text, **fields):
    entry = {"kind": "new", "description": description, "hooks": ["applies", "before_call"], "max_note_chars": 1000}
    return entry | fields, source(text)


def reply_of(*changes):
    return engineer_reply({"changes": [entry for entry, _ in changes]}, [code for _, code in changes])


def test_a_training_round_analyses_the_failures_then_proposes_with_cut_description_and_no_tests(tmp_path, workers):
    long = "Lists the numbers the question mentions. " * 20
    ctx, glm = train_context(tmp_path, workers, scripted(reply_of(coded(long, NOTE))))
    package, sealed = engineer.run_train(ctx)
    sealed = verified(sealed, "engineer")
    systems = [system for system, _ in glm.seen]
    assert systems[:2] == [engineer.ANALYST_SYSTEM, engineer.ENGINEER_SYSTEM_V2]
    analysed = glm.seen[0][1]
    assert analysed["request"] == "analyse" and analysed["card"] == CARD and analysed["package"] == []
    assert sorted(t["task_id"] for t in analysed["trajectories"]) == ["q1", "q3"]  # the failed items, one group
    assert all("reference" in t and t["kind"] == "failures" for t in analysed["trajectories"])
    assert all("system" not in call for t in analysed["trajectories"] for call in t["calls"])
    assert sealed["analysis"]["failed_items"] == 2 and sorted(sealed["analysis"]["items"]) == ["q1", "q3"]
    assert sealed["analysis"]["calls"][0]["findings"] == 1 and sealed["analysis"]["calls"][0]["reason"] is None
    assert sealed["analyst_prompt_sha256"] == engineer.ANALYST_PROMPT_SHA256
    proposed = glm.seen[1][1]
    assert proposed["analyses"] == [dict(FINDING, items=["q1"])]  # only shown items; a finding without pattern dropped
    assert proposed["round"] == 1 and proposed["rounds"] == protocol.TRAIN_ROUNDS and proposed["history"] == []
    assert proposed["edits"] == {"max": protocol.MAX_CHANGES, "used": 0, "edits": [], "step_procedures": []}
    change = sealed["changes"][0]
    assert change["survived"] and change["truncated"] == {"description": len(long)} and change["fix_calls"] == 0
    assert change["summary"] == long[:protocol.TRAIN_PROPOSAL_CHARS]
    assert [c["check"] for c in change["attempts"][0]["checks"]][-3:] == ["C7", "C8", "C9"]
    assert sealed["mode"] == engineer.TRAIN and sealed["prompt_sha256"] == engineer.ENGINEER_PROMPT_V2_SHA256
    assert sealed["round"] == 1 and sealed["base_sha256"] == ctx.base.sha256 and sealed["lint"] == []
    assert package.parent_sha256 == ctx.base.sha256 and [e.kind for e in edits(ctx.base, package)] == ["new"]
    assert len(package.procedures[0].description) == protocol.MAX_DESCRIPTION_CHARS
    assert sealed["calls"] == 1  # the analyst call is the engineer role's, under its own label prefix


def test_a_failing_change_gets_up_to_three_fix_calls_then_is_dropped(tmp_path, workers):
    crash = reply_of(coded("Divides by zero.", CRASH))
    ctx, glm = train_context(tmp_path, workers, scripted(crash, fixes=[crash, crash, crash]))
    package, sealed = engineer.run_train(ctx)
    change = verified(sealed, "engineer")["changes"][0]
    assert package is None and not change["survived"] and change["fix_calls"] == 3
    assert [a["failed"] for a in change["attempts"]] == ["C6"] * 4 and change["fix_replies"] == [None] * 3
    fixes = [payload for system, payload in glm.seen if system == engineer.ENGINEER_SYSTEM_V2
             and payload["request"] == "fix"]
    assert [f["attempt"] for f in fixes] == [1, 2, 3] and all(f["attempts"] == protocol.TRAIN_FIXES for f in fixes)
    assert all(f["failed"]["check"] == "C6" for f in fixes)
    labels = [c["label"] for c in ctx.roles.calls if c["label"].startswith("engineer/")]
    assert labels[-3:] == ["engineer/%s/fix/1/%d" % (ctx.label, n) for n in (1, 2, 3)]


def test_an_unusable_fix_reply_is_named_in_the_next_fix_call(tmp_path, workers):
    crash = reply_of(coded("Divides by zero.", CRASH))
    fixed = reply_of(coded("Counts the question's words.", WORDS))
    ctx, glm = train_context(tmp_path, workers, scripted(crash, fixes=["no blocks here", fixed]))
    package, sealed = engineer.run_train(ctx)
    change = verified(sealed, "engineer")["changes"][0]
    assert change["survived"] and change["fix_calls"] == 2 and change["fix_replies"][0].startswith("unparseable")
    second = [p for s, p in glm.seen if s == engineer.ENGINEER_SYSTEM_V2 and p["request"] == "fix"][1]
    assert second["previous_reply"].startswith("unparseable") and package is not None


def test_rounds_rebase_on_s_keep_ids_unique_and_stop_at_the_edit_budget(tmp_path, workers):
    base = empty(step="s0", evidence=FIXTURE)
    first, sealed_1 = engineer.run_train(train_context(tmp_path, workers, scripted(reply_of(
        coded("Lists the question's numbers.", NOTE), coded("Counts the question's words.", WORDS))), base=base)[0])
    assert first.order == ("fx-searchqa-1-1", "fx-searchqa-1-2")
    # round 2 revises the step's own first procedure and adds a third: re-expressed against S both are new
    revision = {"kind": "revision", "revises": "fx-searchqa-1-1", "description": "Lists the question's numbers twice.",
                "hooks": ["applies", "before_call"], "max_note_chars": 1000}
    ctx, glm = train_context(tmp_path, workers, scripted(reply_of((revision, source(NOTE)),
                                                                 coded("Counts the context's sentences.", SENTENCES))),
                             parent=first, base=base, round_=2, reserved=frozenset(first.order),
                             analysed=frozenset({"q1"}))
    second, sealed_2 = engineer.run_train(ctx)
    assert glm.seen[0][1]["trajectories"][0]["task_id"] == "q3"  # an item no earlier round analysed comes first
    assert second.parent_sha256 == base.sha256 and len(second.order) == 3
    assert "fx-searchqa-1-1" not in second.order and not set(second.order) & {"fx-searchqa-1-3"} - set(second.order)
    assert len(set(second.order)) == 3 and set(first.order) - {"fx-searchqa-1-1"} <= set(second.order)
    assert [e.kind for e in edits(base, second)] == ["new", "new", "new"]
    revised = [p for p in second.procedures if p.id not in first.order]
    assert all(p.lineage["revises"] is None for p in revised)  # it revised a procedure S never held
    assert glm.seen[1][1]["edits"]["used"] == 2 and glm.seen[1][1]["edits"]["step_procedures"] == list(first.order)
    # round 3: a fourth edit against S is beyond the budget -- C3, no fix call
    ctx, glm = train_context(tmp_path, workers, scripted(reply_of(coded("Counts the question's words again.", WORDS))),
                             parent=second, base=base, round_=3, reserved=frozenset(first.order + second.order))
    third, sealed_3 = engineer.run_train(ctx)
    change = verified(sealed_3, "engineer")["changes"][0]
    assert third is None and change["attempts"][-1]["failed"] == "C3" and change["attempts"][-1]["unfixable"]
    assert change["fix_calls"] == 0 and "edit_budget" in change["attempts"][-1]["checks"][-1]["detail"]


def test_the_train_mode_context_refuses_foreign_inputs(tmp_path, workers):
    with pytest.raises(ValueError, match="Training inputs only"):
        engineer.Context(bench="searchqa", k=1, step="s1", evidence=FIXTURE, parent=empty(step="s0", evidence=FIXTURE),
                         trajectories=qa_trajectories(), corpora={}, workers=workers, roles=None,
                         label="D/s1-searchqa/engineer", analysed=frozenset({"q1"}))
    with pytest.raises(ValueError, match="Analysed items"):
        train_context(tmp_path, workers, scripted(""), analysed=frozenset({"q9"}))
    with pytest.raises(ValueError, match="history"):
        train_context(tmp_path, workers, scripted(""), history=[{"round": 1, "proposals": [{"bad": [1]}]}])


def test_lenient_parsing_takes_a_source_field_as_the_code():
    entry = {"kind": "new", "description": "Lists numbers.", "hooks": ["applies", "before_call"], "max_note_chars": 9,
             "source": NOTE}
    reply = engineer_reply({"changes": [entry]}, [])
    with pytest.raises(engineer.Unparseable):
        engineer.parse(reply)
    changes, sources = engineer.parse(reply, lenient=True)
    assert sources == [NOTE] and "source" not in changes[0]


# ------------------------------------------------------------------------------------------ the adoption rule
def cell(token, *, faults=(), violation=False):
    return {"judge": {"v2": {"token": token}, "format": {"violation": violation}}, "faults": list(faults)}


def cells_of(rows):
    """{(arm, item): [cells]} from {item: (S' tokens, S tokens)}."""
    out, token = {}, {"p": "pass", "f": "fail"}
    for item, (new_tokens, old_tokens) in rows.items():
        out[("S'", item)] = [cell(token[t]) for t in new_tokens]
        out[("S", item)] = [cell(token[t]) for t in old_tokens]
    return out


def test_the_adoption_rule():
    fixed3 = cells_of({"a": ("pp", "ff"), "b": ("pp", "fp"), "c": ("pf", "ff"), "d": ("pp", "pp")})
    verdict = step.train_verdict(fixed3, ["a", "b", "c", "d"], [], {"p1"}, predicate_faults=0, routed=10)
    assert verdict["adopted"] and verdict["fixed"] == ["a", "b", "c"] and verdict["broken"] == []
    assert verdict["net"] == "2/1" and verdict["need"] == 1 and verdict["p_sign"] == 1 / 8
    one = step.train_verdict(cells_of({"a": ("pp", "ff")}), ["a"], [], {"p1"}, predicate_faults=0, routed=1)
    assert not one["adopted"] and one["reason"] == "gain:sign"  # one fixed item: p = 1/2
    mixed = cells_of({"a": ("pp", "ff"), "b": ("pp", "ff"), "c": ("ff", "pp")})
    assert step.train_verdict(mixed, ["a", "b", "c"], [], set(), predicate_faults=0, routed=3)["reason"] == "gain:sign"
    rows = {"i%03d" % n: ("pp", "pp") for n in range(98)} | {"h1": ("pf", "ff"), "h2": ("pf", "ff")}
    small = step.train_verdict(cells_of(rows), sorted(rows), [], set(), predicate_faults=0, routed=100)
    assert small["reason"] == "gain:net" and small["need"] == 2 and small["net"] == "1/1"  # two half-fixed of 100
    faulty = cells_of({"a": ("pp", "ff"), "b": ("pp", "ff"), "c": ("pp", "ff")})
    faulty[("S'", "a")][0]["faults"] = [{"procedure": "p1"}]
    assert step.train_verdict(faulty, ["a", "b", "c"], [], {"p1"}, predicate_faults=0,
                              routed=3)["reason"] == "guard:own_faults"
    inherited = step.train_verdict(faulty, ["a", "b", "c"], [], {"p2"}, predicate_faults=0, routed=3)
    assert inherited["adopted"]  # a fault of a procedure the round did not change is not the change's
    assert step.train_verdict(fixed3, ["a", "b", "c", "d"], [], {"p1"}, predicate_faults=1,
                              routed=10)["reason"] == "guard:predicate_faults"
    formats = cells_of({k: ("pp", "ff") for k in "abc"})
    for k in "abc":
        formats[("S'", k)] = [cell("pass", violation=True)] * 2
    assert step.train_verdict(formats, list("abc"), [], set(), predicate_faults=0,
                              routed=3)["reason"] == "guard:format"
    assert step.train_verdict({}, [], [], set(), predicate_faults=0, routed=5)["reason"] == "no_item_routes_differently"


def test_the_step_buffer_names_each_proposal_and_its_fate():
    def change(n, survived, failed=None, summary="text"):
        return {"n": n, "kind": "new", "id": "p%d" % n, "target": None, "survived": survived, "summary": summary,
                "attempts": [{"failed": failed}]}

    engineered = {"candidate_sha256": "c", "engineer": {
        "changes": [change(1, True), change(2, False, "C4", "Answer is 4.815"), change(3, False, "C3", "4.815"),
                    change(4, True), change(5, False, "C7"), {**change(6, False, "C1"), "kind": {"not": "a kind"}}],
        "dropped": [4]}}
    verdict = {"adopted": False, "items": 5, "generated": 0, "fixed": ["a"], "broken": ["b"], "net": "0/1",
               "p_sign": 0.75, "reason": "gain:fixed_over_broken"}
    line = step._line(2, engineered, {"verdict": verdict})
    assert line["proposals"] == [
        {"kind": "new", "id": "p1", "target": None, "description": "text", "fate": "not_adopted:gain:fixed_over_broken"},
        {"kind": "new", "id": "p2", "target": None, "description": "", "fate": "check_failed:C4"},
        # Codex review 2026-10-23 #3: a description no leakage check passed is never carried to a later round
        {"kind": "new", "id": "p3", "target": None, "description": "", "fate": "check_failed:C3"},
        {"kind": "new", "id": "p4", "target": None, "description": "text", "fate": "dropped_in_combination"},
        {"kind": "new", "id": "p5", "target": None, "description": "text", "fate": "check_failed:C7"},
        {"kind": None, "id": "p6", "target": None, "description": "", "fate": "check_failed:C1"}]
    assert engineer._history_line(line, 3) and line["reason"] == "gain:fixed_over_broken" and line["fixed"] == 1
    assert not engineer._history_line(line, 2)  # a line of this round or a later one is not history
    none = step._line(1, {"candidate_sha256": None, "engineer": {"changes": [], "dropped": []}}, None)
    assert none["reason"] == "no_candidate" and none["proposals"] == [] and engineer._history_line(none, 2)


def test_glm_projection_of_main_v2_prices_the_training_rounds_and_analysts():
    measured = {role: {"calls": 2, "tokens": 20_000, "per_call": 10_000.0, "request_bytes": 50_000}
                for role in budgets.ROLES}
    found = smoke.glm_projection(measured, "main-v2")
    calls = smoke.max_role_calls("main-v2")
    scope = found["G:xs:searchqa:1:role:engineer"]
    assert scope["cap"] == protocol.MAIN_V2_ROLE_CAPS["engineer"]
    assert scope["settled"] == 10_000 * (calls["engineer"] + calls["leakage"] + calls["describer"])
    assert scope["reservation"] == 4 * (smoke.engineer_request_floor("main-v2") + 512 + protocol.ROLE_MAX_TOKENS)
    assert found["D:xs:alfworld:5:role:examiner"]["cap"] == protocol.MAIN_V2_ROLE_CAPS["examiner"]
    assert found["G:glm"]["cap"] == protocol.MAIN_V2_GLM_CAP and all(entry["fits"] for entry in found.values())


# ------------------------------------------------------------------------- Codex review 2026-10-23 (codexdl) fixes
def test_codex_v2_2_a_smoke_without_sx_keeps_its_v1_plan_and_result(tmp_path):
    v1 = smoke.plan_of(smoke.SMOKE_STAGES)
    assert "SX" not in v1 and v1 == {k: v for k, v in smoke.PLAN.items() if k != "SX"}
    assert smoke.plan_of(smoke.G_SMOKE_STAGES + ("SX",))["SX"] == smoke.PLAN["SX"]
    assert smoke.V1_STAGES == ("S0", "S1", "S2", "SN1", "SE6", "S3", "S4")

    def summed(name, **fields):
        root = tmp_path / name
        root.mkdir()
        return smoke.summary({"root": str(root), protocol.RECORD_HASH: "0" * 64, **fields})

    assert list(summed("v1", stages=list(smoke.SMOKE_STAGES))["stages"]) == list(smoke.V1_STAGES)
    unlisted = summed("old")  # a spec without the list: every v1 stage is required, SX is not reported
    assert unlisted["required"] == list(smoke.V1_STAGES) and "SX" not in unlisted["stages"]
    example = summed("v2", stages=list(smoke.G_SMOKE_STAGES + ("SX",)))
    assert example["stages"]["SX"] == "missing" and example["required"][-1] == "SX"


def test_codex_v2_3_the_lint_names_tests_by_position_only():
    procedure = SimpleNamespace(id="fx-searchqa-1-1", hooks=("applies", "before_call"), replay_tests=(
        {"id": "ans-4.815", "trajectory": "c-q1"}, "not a test", {"id": "rt-2", "property": {"value": "4.815"}}))
    advice = {"tests": [], "problems": [
        {"reason": "invalid_test", "test": "ans-4.815", "detail": "keys"},
        {"reason": "invalid_test", "test": None, "detail": "keys"},
        {"reason": "invalid_test", "test": "rt-2", "detail": "keys"}, {"reason": "negative_test", "cell": "c-q1"}]}
    lint = engineer._lint(procedure, advice, {})
    assert lint == {"id": "fx-searchqa-1-1", "tests": [], "problems": [
        {"reason": "invalid_test", "test": 1, "detail": "keys"}, {"reason": "invalid_test", "test": 2, "detail": "keys"},
        {"reason": "invalid_test", "test": 3, "detail": "keys"}]}
    ran = {"tests": [{"id": "ans-4.815", "holds": False, "withheld": False, "mutated": None, "nonvacuous": True},
                     {"id": "rt-2", "holds": True, "withheld": True, "mutated": False, "nonvacuous": False}],
           "problems": [{"reason": "test_failed", "test": "ans-4.815"}, {"reason": "vacuous_test", "test": "rt-2"},
                        {"reason": "test_count", "detail": 9}, {"reason": "no_fix_claim"}]}
    lint = engineer._lint(procedure, ran, {})
    assert [t["test"] for t in lint["tests"]] == [1, 2] and "4.815" not in repr(lint)
    assert lint["problems"] == [{"reason": "test_failed", "test": 1}, {"reason": "vacuous_test", "test": 3},
                                {"reason": "test_count", "detail": 9}, {"reason": "no_fix_claim"}]
    assert engineer._lint_entry(lint)
    assert not engineer._lint_entry({**lint, "tests": [{**lint["tests"][0], "id": "ans-4.815"}]})
    assert not engineer._lint_entry({**lint, "problems": [{"reason": "invalid_test", "detail": "4.815"}]})


def test_codex_v2_3_c4_counts_the_table_references_earlier_rounds_disclosed(tmp_path, workers):
    """A SpreadsheetBench value an earlier round disclosed (``Context.disclosed``) stays disclosed: a later round whose
    own payload shows no reference still sends a literal holding it to adjudication; without it, nothing is flagged."""
    from tests.test_execskill_engineer import COLUMNS, COPIED_LITERAL, FAILED_ROWS, PASSED_ROWS, SHEET_REFERENCE
    from tests.test_execskill_engineer import _workbook
    from tests.test_execskill_replay import SHEET_VIEW, sheet_trajectories

    copied = engineer_reply({"changes": [{"kind": "new", "description": "Counts the instruction's words.",
                                          "hooks": ["applies", "before_call"], "max_note_chars": 1000}]},
                            [source(COPIED_LITERAL)])
    clean = engineer_reply({"changes": [{"kind": "new", "description": "Counts the instruction's columns.",
                                         "hooks": ["applies", "before_call"], "max_note_chars": 1000}]},
                           [source(COLUMNS)])
    items = [{"benchmark": "spreadsheetbench", "task_id": task, "public": {"instruction": SHEET_VIEW["instruction"]},
              "private": {}} for task in ("s1", "s2")]

    def context(name, replies, disclosed):
        roles, glm = glm_roles(tmp_path / name, replies)
        run = sheet_trajectories()
        base = empty(step="s0", evidence=FIXTURE)
        ctx = engineer.Context(
            bench="spreadsheetbench", k=1, step="s1", evidence=FIXTURE, parent=base, trajectories=run,
            corpora={"spreadsheetbench": Corpus("spreadsheetbench", items)}, workers=workers, roles=roles,
            label="D/s1-spreadsheetbench/engineer-r2", card=CARD, references={"s1": dict(SHEET_REFERENCE)},
            inputs_dirs={"c-sheet-fail": _workbook(tmp_path / name / "in-fail", FAILED_ROWS),
                         "c-sheet-pass": _workbook(tmp_path / name / "in-pass", PASSED_ROWS)},
            mode=engineer.TRAIN, round=2, base=base, current=[run[1]], disclosed=disclosed)
        return ctx, glm

    ctx, glm = context("kept", [copied, {"verdict": "yes", "reason": "It copies an answer value."}, clean],
                       frozenset({"s1"}))
    package, sealed = engineer.run_train(ctx)
    sealed = verified(sealed, "engineer")
    leak = sealed["changes"][0]["attempts"][0]["checks"][-1]
    assert leak["check"] == "C4" and not leak["passed"] and leak["detail"]["hits"][0]["where"] == "literal"
    assert sealed["changes"][0]["survived"] and sealed["disclosed"] == ["s1"] and package is not None
    assert "reference" not in repr(glm.seen[0][1]["trajectories"])  # this round's own payload shows none
    ctx, glm = context("forgotten", [copied], frozenset())
    _, sealed = engineer.run_train(ctx)
    assert verified(sealed, "engineer")["changes"][0]["attempts"][0]["passed"] and sealed["disclosed"] == []
    with pytest.raises(ValueError, match="Disclosed items"):
        train_context(tmp_path, workers, scripted(""), disclosed=frozenset({"q1"}))  # SearchQA: no table reference
    with pytest.raises(ValueError, match="Disclosed items"):
        train_context(tmp_path, workers, scripted(""), disclosed=frozenset({"q9"}))


def candidate_cell(trajectory, cell, unit="D/s1-searchqa/train-r1", arm="S'"):
    fields = {k: v for k, v in trajectory.items() if k not in ("version", "evidence", protocol.RECORD_HASH)}
    return protocol.record("trajectory", FIXTURE, {**fields, "cell": cell, "unit": unit, "arm": arm,
                                                   "arm_kind": "candidate" if arm == "S'" else "parent"})


def feedback(examples=(), **fields):
    return {"adopted": False, "reason": "gain:sign", "items": 2, "fixed": 1, "broken": 0, "net": "1/1", "need": 1,
            "p_sign": 0.5, "guards": {"own_faults": True, "predicate_faults": True, "format": True},
            "generated": {"items": 0, "fixed": 0, "broken": 0},
            "procedures": [{"id": "fx-searchqa-1-1", "change": "added", "enabled_items": 2, "fixed": 1, "broken": 0,
                            "examples": list(examples)}], **fields}


def example(task, cell, **fields):
    return {"task_id": task, "cell": cell, "outcome": "fixed", "question": "Q?", "notes": "N", "current_reply": "a",
            "candidate_reply": "b", "current_pass": "0/2", "candidate_pass": "2/2", **fields}


def test_codex_v2_4_the_context_takes_exactly_the_registered_feedback(tmp_path, workers):
    run = qa_trajectories()
    q1, q3 = (next(t for t in run if t["task_id"] == item) for item in ("q1", "q3"))
    evaluated = [candidate_cell(q1, "t-q1"), candidate_cell(q3, "t-q3"), candidate_cell(q1, "t-q1-s", arm="S")]
    answers = {item: answers for item, (_, answers, token) in QA.items() if token == "fail"}

    def accepted(training, **fields):
        train_context(tmp_path, workers, scripted(""), round_=2, evaluated=evaluated, training=training, **fields)

    accepted(feedback([example("q1", "t-q1", reference=answers["q1"])]))
    refused = [
        feedback(acceptance_examples=[example("q1", "t-q1")]),  # a foreign field beside an empty example list
        feedback([example("q1", "t-q3")]),  # the cell of another item
        feedback([example("q1", "t-q1-s")]),  # the incumbent's cell, not the candidate's
        feedback([example("q1", "c-q1")]),  # a run-unit cell, not the last training unit's
        feedback([example("q1", "t-q1", reference=["the answer"])]),  # not the item's own reference
        feedback([example("q1", "t-q1", question="Q" * 401)]),  # beyond its text cap
        feedback([dict(example("q1", "t-q1"), extra="x")]),
        {**feedback(), "procedures": [{**feedback()["procedures"][0], "source": "code"}]},
        {k: v for k, v in feedback().items() if k != "guards"}]
    for training in refused:
        with pytest.raises(ValueError, match="training feedback"):
            accepted(training)
    line = {"round": 1, "candidate": True, "adopted": False, "items": 2, "generated": 0, "fixed": 1, "broken": 0,
            "net": "1/1", "p_sign": 0.5, "reason": "gain:sign", "proposals": []}
    accepted(None, history=[line])
    for bad in ({**line, "note": "4.815"}, {**line, "round": 2}, {**line, "net": "4.815"},
                {**line, "proposals": [{"kind": "new", "id": "p", "target": None, "description": "d", "fate": "f",
                                        "extra": 1}]}):
        with pytest.raises(ValueError, match="history"):
            accepted(None, history=[bad])
    with pytest.raises(ValueError, match="Lint"):
        accepted(None, lint=[{"id": "fx-searchqa-1-1", "tests": [], "problems": [], "values": ["4.815"]}])


def test_codex_v2_5_an_oversized_proposal_message_leaves_out_examples_then_analyses():
    big = "x" * 60_000
    training = feedback([example("q1", "t-q%d" % n, reference={"Sheet1!A%d" % n: big}) for n in range(5)])
    user = {"request": "propose", "trajectories": [{"cell": "c%d" % n, "calls": big} for n in range(3)],
            "training": training, "analyses": [{"pattern": "y" * 250}] * 3}
    fitted = engineer._fit_train(dict(user))
    assert fitted["trajectories"] == [] and fitted["trajectories_omitted"] == 3
    assert fitted["examples_omitted"] == 2 and len(fitted["training"]["procedures"][0]["examples"]) == 3
    assert fitted["analyses_omitted"] == 0 and len(training["procedures"][0]["examples"]) == 5  # never mutated
    assert engineer.message_bytes(fitted) <= protocol.ROLE_INPUT_BYTES
    shown = engineer._shown_references(fitted)  # C4 counts exactly the examples the fitted message carries
    assert [cell for cell, _ in shown] == ["t-q0", "t-q1", "t-q2"]
    small = engineer._fit_train({"request": "propose", "trajectories": [{"cell": "c"}], "training": None,
                                 "analyses": []})
    assert small["trajectories_omitted"] == small["examples_omitted"] == small["analyses_omitted"] == 0
    with pytest.raises(ValueError, match="no example left"):
        engineer._fit_train({"request": "propose", "card": big * 4, "trajectories": [], "training": None,
                             "analyses": []})
