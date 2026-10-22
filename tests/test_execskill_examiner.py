"""T-EXAM-1..6: the examiner role (registration §4.3, §5.2, §5.3, §7.1, §7.2, §21 owner rule (b); plan examiner row).
Offline and deterministic: the examiner and the researcher are FakeGLM behind the real ``Roles``, the research sources
are FakeResearch, every detector runs in the real sandbox worker through FakeDocker, and the probe cells are
synthetic sealed cell records. Everything is an engineering fixture."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from skillopt.coevo5 import leakage
from skillopt.execskill import detectors, examiner, research, step
from skillopt.execskill.detectors import Detector
from skillopt.execskill.generators import livemath, sheet
from skillopt.execskill.generators.families import generated_item
from skillopt.execskill.package import FIXTURE
from skillopt.execskill.protocol import BAND_PROBE_ITEMS, BAND_ROUNDS, MAX_ITEMS_PER_FINDING, record, verified
from tests.execskill_fakes import INVALID_JSON, POLICY_VIOLATING_SOURCE, engineer_reply, glm_roles
from tests.execskill_fakes_research import pick, query, sources, table
from tests.fixtures.execskill.items import alfworld_games, officeqa_items
from tests.test_execskill_detectors import trajectory
from tests.test_execskill_replay import fake, workers  # noqa: F401  (the FakeDocker worker factory)

UNIT = "G/s2-searchqa/diagnose"
HEDGE = 'def detect(view):\n    return any("maybe" in (reply or "").lower() for reply in view["replies"])\n'
NO_DETECT = "def fires(view):\n    return True\n"


def qa_set():
    """Twelve SearchQA cells, one per item: failures hedge ("maybe") or give no answer tag; successes answer plainly;
    every answer is restated before its tag."""
    out = []
    for n in range(12):
        answer = "Oslo%d" % n
        if n % 3 == 0:
            token, reply = "fail", "It is %s, maybe.\n<answer>%s</answer>" % (answer, answer)
        elif n % 3 == 1:
            token, reply = "pass", "It is %s.\n<answer>%s</answer>" % (answer, answer)
        else:
            token, reply = ("fail", "I cannot tell.") if n == 2 else ("pass", "So %s.\n<answer>%s</answer>" % (
                answer, answer))
        view = {"question": "Which city hosts fixture event E%02d?" % n, "context": ["Public note N%02d." % n]}
        out.append(trajectory("c-%02d" % n, "searchqa", "item-%02d" % n, token, [view], [reply]))
    return out


def keys_of(value):
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys_of(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys_of(v)}
    return set()


def cell(item, token, *, run=1, arm="S", bench="officeqa", shortcut=None, final=None, stopped=False):
    """A sealed probe cell record (the fields the gates read): ``token`` its scorer-v2 token, ``final`` the
    completion-aware one when it differs (a JSON-rescued pass); ``stopped``: stopped before its verdict (no final, no
    judge). ``shortcut``: the shell mode the cell asked for and ran in, kept in ``cell`` and at the top level as
    ``cells.run_cell`` keeps it (ticket C1-2)."""
    found = {"id": "%s:%s:%d" % (arm, item, run), "unit": "G/s2-%s/probe" % bench, "arm": arm, "benchmark": bench,
             "task_id": item, "run": run}
    mode = {"shortcut": shortcut} if shortcut is not None else {}
    verdict = {"final": None, "judge": None} if stopped else {"final": {"token": final or token},
                                                              "judge": {"v2": {"token": token}}}
    return record("cell", FIXTURE, {"cell": {**found, **mode}, **mode, **verdict})


def detector_answer(*replies):
    """Scripted examiner detector replies, in order; each request's payload is kept."""
    queue, seen = list(replies), []

    def answer(system, payload):
        assert system == examiner.DETECTOR_SYSTEM
        seen.append(payload)
        return queue.pop(0)
    return answer, seen


# ------------------------------------------------------------------------------------------------- T-EXAM-1
def test_exam1_the_detector_payload_shows_the_masked_write_half_only(tmp_path, workers):
    halves = detectors.split(qa_set(), bench="searchqa", unit=UNIT)
    library = [Detector(id="d-searchqa-1-1", bench="searchqa", source=HEDGE, description="Hedged replies fail.")]
    payload = examiner.detector_payload(halves, bench="searchqa", library=library, workers=workers)
    text = json.dumps(payload)
    assert len(payload["trajectories"]) == len(halves["write"]) == 6 and payload["half"] == "write"
    for hold in halves["hold"]:  # nothing of a hold-half cell reaches the examiner (§4.3, §5.2)
        assert json.loads(hold["calls"][0]["user"])["question"] not in text and hold["cell"] not in text
    assert "Oslo" not in text and "[masked]" in text  # answers and their restatements masked
    assert not keys_of(payload) & examiner.FORBIDDEN_KEYS
    assert "passed" not in keys_of(payload["trajectories"][0]["view"])
    shown = payload["trajectories"]
    assert [t["residual"] for t in shown] == sorted((t["residual"] for t in shown), reverse=True)  # residual first
    for entry in shown:
        hedged = any("maybe" in reply for reply in entry["view"]["replies"])
        assert entry["covered_by"] == (["d-searchqa-1-1"] if hedged else [])  # run in the sandbox (FakeDocker)
        assert entry["residual"] == (not hedged and not entry["categories"])
    assert payload["library"] == [{"id": "d-searchqa-1-1", "description": "Hedged replies fail."}]
    assert payload["counts"]["cells"] == 6 and set(payload["counts"]) == {"cells", "failed", "categories", "excluded"}
    leaked = dict(halves, write=halves["write"] + halves["hold"][:1])
    with pytest.raises(ValueError, match="hold-half"):
        examiner.detector_payload(leaked, bench="searchqa")
    with pytest.raises(ValueError, match="worker factory"):
        examiner.detector_payload(halves, bench="searchqa", library=library)


def test_exam1_generation_payloads_never_carry_references_or_per_item_counts():
    with pytest.raises(ValueError, match="reference or verdict"):
        examiner.generator_payload("spreadsheetbench", [], sources={"S1": {"instruction": "x", "private": {"a": 1}}})
    with pytest.raises(ValueError, match="aggregated counts"):
        examiner.policy_payload("officeqa", outcomes={"officeqa/item-1": 1})
    with pytest.raises(ValueError, match="aggregated counts"):
        examiner.policy_payload("officeqa", outcomes={"dropped": {"gen:g-officeqa-1-1:3": 1}})
    with pytest.raises(ValueError, match="SearchQA"):
        examiner.policy_payload("searchqa")
    built = examiner.Generated("fx-gen-oq", "officeqa", ({"items": [], "made": 2, "dropped": {"format": 2},
                                                          "status": "none_kept", "family": "officeqa.ratio",
                                                          "material": "m"},))
    counts = examiner.outcome_counts([examiner.gates(built, {}, evidence=FIXTURE)])
    assert counts == {"sets": 1, "admitted": 0, "failed": {"band": 1, "labels": 1, "no_items": 1, "shortcut": 1},
                      "items": {"made": 2, "kept": 0}, "dropped": {"format": 2}, "band": {"not_run": 1},
                      "families": {"officeqa.ratio": {"none_kept": 1}}, "research": {}, "generators": {}}
    shown = examiner.policy_payload("officeqa", outcomes=counts)
    assert [f["name"] for f in shown["families"]] == sorted(examiner.generators.FAMILIES["officeqa"])
    assert not keys_of(shown) & examiner.FORBIDDEN_KEYS


# ------------------------------------------------------------------------------------------------- T-EXAM-2
def test_exam2_detector_manifest_parsed_and_each_source_policy_checked(tmp_path, workers):
    halves = detectors.split(qa_set(), bench="searchqa", unit=UNIT)
    payload = examiner.detector_payload(halves, bench="searchqa")
    reply = engineer_reply({"detectors": [{"description": "Hedged replies fail."}, {"description": "Bad code."},
                                          {"description": "No entry point."}]},
                           [HEDGE, POLICY_VIOLATING_SOURCE, NO_DETECT])
    answer, seen = detector_answer(reply)
    roles, _ = glm_roles(tmp_path / "glm", answer)
    candidates, sealed = examiner.detector_write(roles, payload, k=2, label=UNIT, evidence=FIXTURE)
    sealed = verified(sealed, "examiner-detectors")
    assert [d.id for d in candidates] == ["fx-searchqa-2-1"] and seen == [payload]
    assert [(r["n"], r["kept"]) for r in sealed["written"]] == [(1, True), (2, False), (3, False)]
    assert sealed["written"][1]["reason"].startswith("detector_policy")
    assert "detect(view)" in sealed["written"][2]["reason"]
    assert sealed["candidates_sha256"] == detectors.candidates_sha256(candidates) and sealed["calls"] == 1
    views = {t["cell"]: detectors.masked_view(t, bench="searchqa", purpose="detector") for t in halves["write"]}
    fired = detectors.evaluate(candidates, views, workers)["fx-searchqa-2-1"]  # the candidate runs in the sandbox
    assert fired["faults"] == {} and fired["fired"] == sorted(c for c, v in views.items() if "maybe" in v["replies"][0])
    library = [Detector(id="d-searchqa-2-1", bench="searchqa", source=HEDGE, description="Hedged replies fail.")]
    real = examiner.detector_payload(halves, bench="searchqa", library=library, workers=workers)
    roles, _ = glm_roles(tmp_path / "glm-real", detector_answer(reply)[0])
    candidates, _ = examiner.detector_write(roles, real, k=2, label=UNIT, evidence="pilot_real_run")
    assert [d.id for d in candidates] == ["d-searchqa-2-2"]  # the next free registrar id


def test_exam2_policy_and_generator_replies_parsed(tmp_path):
    policy_reply = {"families": ["spreadsheetbench.formula_edit"], "rationale": "Sums and rounding.",
                    "requests": [{"kind": "family_material", "family": "spreadsheetbench.formula_edit",
                                  "concept": "ROUND", "topic": None}]}
    roles, _ = glm_roles(tmp_path, [policy_reply])
    payload = examiner.policy_payload("spreadsheetbench")
    policy, sealed = examiner.policy_revise(roles, payload, label="G/s1-spreadsheetbench/generate", evidence=FIXTURE)
    assert policy["requests"] == [{"kind": "family_material", "family": "spreadsheetbench.formula_edit",
                                   "concept": "ROUND", "topic": None}] and policy["bench"] == "spreadsheetbench"
    assert verified(sealed, "examiner-policy")["fallback"] is None and sealed["calls"] == 1
    material = research.material({"purpose": "verify", "status": "found", "conclusion": "Openable receptacles hide "
                                  "objects.", "quotes": [{"page": "P1", "text": "a drawer is opened"}]})
    shown = examiner.generator_payload("alfworld", [material])
    assert shown["families"] == [] and shown["materials"] == [{"id": material["id"], "kind": "selection",
                                                               "conclusion": material["conclusion"]}]
    spec = {"task_kinds": ["place"], "min_receptacles": 3, "min_openable": 1, "target": "openable",
            "finding": material["id"]}
    roles, _ = glm_roles(tmp_path / "alf", [{"specs": [{"selection": spec}, {"selection": dict(spec, finding="x")}]}])
    specs, sealed = examiner.generator_write(roles, shown, label="G/s3-alfworld/generate", evidence=FIXTURE)
    assert specs == [{"n": 1, "selection": spec}] and sealed["dropped"] == [{"n": 2, "reason": "no_material"}]
    games = alfworld_games()
    pool = {g["task_id"]: {"initial_observation": g["initial_observation"], "task_text": "put a mug in fridge",
                           "admissible_commands_at_reset": g["admissible_commands"]} for g in games}
    chosen = verified(examiner.selection(spec, pool, [material], n=4, seed_tag="t", evidence=FIXTURE),
                      "selection-validity")
    assert len(chosen["selected"]) == len(chosen["null"]) == 4 and chosen["claim"] == "selection_validity"
    assert chosen["shift"]["feature"] == "openable"


def test_r4_the_policy_payload_states_the_valid_request_kinds_and_choosable_parameters(tmp_path):
    """Registrar addendum 2026-10-22 15:5x R4: the policy payload states per bench the request kinds ``_policy``
    accepts and per family the parameter names a parameter_choice may name (none on SpreadsheetBench); the validation
    and the registered void-on-invalid fallback are unchanged."""
    sheet = examiner.policy_payload("spreadsheetbench")
    assert sheet["request_kinds"] == ["family_material"]
    assert [(f["name"], f["parameter_choice_names"]) for f in sheet["families"]] == [
        ("spreadsheetbench.formula_edit", [])]
    office = examiner.policy_payload("officeqa")
    assert office["request_kinds"] == ["family_material", "parameter_choice"]
    assert all(f["parameter_choice_names"] == ["decimals"] for f in office["families"])
    lm = {f["name"]: f["parameter_choice_names"] for f in examiner.policy_payload("livemath")["families"]}
    assert lm["livemath.binomial"] == ["k", "n"] and lm["livemath.integral"] == ["coefficients", "lower", "upper"]
    alf = examiner.policy_payload("alfworld")
    assert alf["request_kinds"] == ["selection_hint"] and alf["families"] == []
    assert not keys_of(sheet) & examiner.FORBIDDEN_KEYS and not keys_of(office) & examiner.FORBIDDEN_KEYS
    choice = {"families": ["spreadsheetbench.formula_edit"], "rationale": "", "requests": [
        {"kind": "family_material", "family": "spreadsheetbench.formula_edit", "concept": "ROUND", "topic": None},
        {"kind": "parameter_choice", "family": "spreadsheetbench.formula_edit", "question": "How many edits?",
         "names": ["edits"], "topic": None}]}
    roles, _ = glm_roles(tmp_path, [choice])
    policy, sealed = examiner.policy_revise(roles, sheet, label="u", evidence=FIXTURE)
    assert policy["requests"] == [] and sealed["fallback"] == "empty"  # one invalid request still voids the reply


# ------------------------------------------------------------------------------------------------- T-EXAM-3
def test_exam3_invalid_replies_fall_back_to_no_detector_no_spec_and_the_previous_policy(tmp_path):
    halves = detectors.split(qa_set(), bench="searchqa", unit=UNIT)
    payload = examiner.detector_payload(halves, bench="searchqa")
    answer, seen = detector_answer("I would look at hedges.", INVALID_JSON)
    roles, _ = glm_roles(tmp_path / "det", answer)
    candidates, sealed = examiner.detector_write(roles, payload, k=1, label=UNIT, evidence=FIXTURE)
    assert candidates == [] and sealed["calls"] == 2 and sealed["candidates_sha256"] is None
    assert [a["parsed"] for a in sealed["attempts"]] == [False, False] and seen[1]["unparseable"] == "manifest_blocks:0"

    material = research.material({"purpose": "table", "status": "found", "source": {"title": "T", "revid": 1},
                                  "table": {"page": "P1", "archive": "a" * 64, "index": 0, "caption": "c",
                                            "rows": [["Year", "A"], ["2019", "1,718"], ["2020", "1,609"]]}})
    shown = examiner.generator_payload("officeqa", [material])
    roles, _ = glm_roles(tmp_path / "gen", ["not json", {"specs": 5}])
    specs, sealed = examiner.generator_write(roles, shown, label="G/s2-officeqa/generate", evidence=FIXTURE)
    assert specs == [] and sealed["calls"] == 2 and [a["parsed"] for a in sealed["attempts"]] == [False, False]
    good = {"family": "officeqa.difference", "material": material["id"], "params": [{"cells": [[1, 1], [2, 1]],
                                                                                    "decimals": 0}]}
    replies = [{"specs": [dict(good, params=[{"cells": [[1, 1], [2, 1]], "decimals": 0, "answer": "-109"}]),
                          dict(good, family="officeqa.median"), dict(good, material="b" * 64),
                          dict(good, params=[good["params"][0]] * 11), dict(good, source="S1"), good]}]
    roles, _ = glm_roles(tmp_path / "drops", replies)
    specs, sealed = examiner.generator_write(roles, shown, label="G/s2-officeqa/generate", evidence=FIXTURE)
    assert specs == [{"n": 6, **good}]
    assert [d["reason"] for d in sealed["dropped"]] == ["answer_field", "unknown_family", "material_not_shown",
                                                        "params", "keys"]

    roles, _ = glm_roles(tmp_path / "policy", ["nope", {"families": [], "requests": [], "rationale": ""}])
    empty, sealed = examiner.policy_revise(roles, examiner.policy_payload("officeqa"), label="u", evidence=FIXTURE)
    assert empty["requests"] == [] and sealed["fallback"] == "empty"
    previous = {"bench": "officeqa", "families": ["officeqa.ratio"], "rationale": "",
                "requests": [{"kind": "family_material", "family": "officeqa.ratio", "concept": "budget",
                              "topic": None}]}
    bad = {"families": ["officeqa.ratio"], "rationale": "", "requests": [  # a family the policy does not use
        {"kind": "family_material", "family": "officeqa.sum", "concept": "budget", "topic": None}]}
    roles, _ = glm_roles(tmp_path / "previous", [bad])
    kept, sealed = examiner.policy_revise(roles, examiner.policy_payload("officeqa", previous=previous), label="u",
                                          evidence=FIXTURE)
    assert kept == previous and sealed["fallback"] == "previous"
    roles, _ = glm_roles(tmp_path / "lower", [{"families": ["spreadsheetbench.formula_edit"], "rationale": "",
                                                "requests": [{"kind": "family_material", "concept": "round",
                                                              "family": "spreadsheetbench.formula_edit"}]}])
    assert examiner.policy_revise(roles, examiner.policy_payload("spreadsheetbench"), label="u",
                                  evidence=FIXTURE)[1]["fallback"] == "empty"  # not a function name


# ------------------------------------------------------------------------------------------------- T-EXAM-4
PARAMS = [{"cells": [[1, 1], [3, 1]], "decimals": 2}, {"cells": [[1, 2], [3, 2]], "decimals": 1},
          {"cells": [[2, 1], [3, 1]], "decimals": 2, "perturb": [{"cell": [3, 1], "percent": 10}]},
          {"cells": [[1, 1], [2, 1]], "decimals": 2}]


def test_exam4_researched_generation_and_the_gates_on_officeqa(tmp_path, monkeypatch):
    policy_reply = {"families": ["officeqa.percent_change"], "rationale": "Public finance tables.",
                    "requests": [{"kind": "family_material", "family": "officeqa.percent_change",
                                  "concept": "government revenue table", "topic": None}]}
    research_replies = [query("government revenue table"), pick("R1"), table("P1", 0)]
    seen = []

    def answer(system, payload):
        seen.append((system, payload))
        if system == examiner.POLICY_SYSTEM:
            return policy_reply
        if system == examiner.GENERATOR_SYSTEM:
            return {"specs": [{"family": "officeqa.percent_change", "material": payload["materials"][0]["id"],
                               "params": PARAMS}]}
        return research_replies.pop(0)

    roles, _ = glm_roles(tmp_path / "glm", answer)
    label = "G/s2-officeqa/generate"
    policy, _ = examiner.policy_revise(roles, examiner.policy_payload("officeqa"), label=label, evidence=FIXTURE)
    opened, _ = sources(tmp_path)
    items = officeqa_items(40)
    researcher = research.Researcher(roles, opened, leakage.Corpus("officeqa", items), bench="officeqa",
                                     label=label + "/research")
    sent = examiner.research_requests(policy, researcher)
    assert [(r["kind"], f["status"]) for r, f in sent] == [("family_material", "found")]
    halves = research.split([f for _, f in sent if f["status"] == "found"], label, evidence=FIXTURE)
    assert len(halves["g_self"]) == 1 and halves["g_acc"] == []
    payload = examiner.generator_payload("officeqa", halves["g_self"])
    specs, _ = examiner.generator_write(roles, payload, label=label, evidence=FIXTURE)
    built = examiner.build(specs, halves["g_self"], bench="officeqa", generator="fx-gen-officeqa-2",
                           set_name="G_self", seed=7, evidence=FIXTURE)
    made = built.items
    assert len(made) == 4 and all(verified(i, "generated-item")["private"]["truth"]["kind"] == "family_reference"
                                  for i in made)
    public = [json.dumps(item["public"]) for item in items]
    for system, shown in seen:  # the researcher and the examiner never see a benchmark item
        assert not any(question in json.dumps(shown) for question in public[:5])
    ids = [i["id"] for i in made]
    band_cells = [[cell(i["id"], "pass" if n % 2 else "fail") for n, i in enumerate(examiner.probe_items(
        made, generator=built.generator, purpose="band"))]]
    shortcut_cells = [cell(ids[0], "pass", run=r, arm="C") for r in (1, 2)] + [
        cell(i, t, run=r, arm="C") for i in ids[1:] for r, t in ((1, "pass"), (2, "fail"))]
    # Codex finding #9 (§7.2: the parent's accuracy on 30 probe items): four items are insufficient material, never
    # admitted, whatever their probe cells say
    sparse = verified(examiner.gates(built, {"band": band_cells, "shortcut": shortcut_cells}, evidence=FIXTURE),
                      "generator-gates")
    assert not sparse["admitted"] and sparse["failed"] == ["band"] and sparse["kept"] == []
    assert sparse["band"] == {"in_band": False, "reason": "insufficient_material", "items": 4, "required": 30,
                              "probe_items": 0, "pass_rate": None, "direction": None}
    assert examiner.outcome_counts([sparse])["band"] == {"insufficient_material": 1}
    # the gate logic itself on this four-item engineering fixture: the probe scaled down to its four items
    monkeypatch.setattr(examiner, "BAND_PROBE_ITEMS", 4)
    gated = verified(examiner.gates(built, {"band": band_cells, "shortcut": shortcut_cells}, evidence=FIXTURE),
                     "generator-gates")
    assert gated["admitted"] and gated["failed"] == [] and gated["kept"] == ids[1:]  # 1 of 4 dropped: 25 % allowed
    assert gated["truth"]["made"] == 4 and gated["truth"]["kept"] == 4 and gated["band"]["pass_rate"] == 0.5
    assert gated["shortcut"]["dropped"] == [ids[0]] and gated["labels"]["truth_by_fixed_code"]
    frozen = verified(examiner.generator_record(gated, specs, evidence=FIXTURE), "generator")
    assert frozen["status"] == "admitted" and frozen["validity"] is None
    counts = examiner.outcome_counts([gated], research=sent, generator_records=[frozen])  # the next policy's input
    assert counts["items"] == {"made": 4, "kept": 4} and counts["band"] == {"in_band": 1}
    assert counts["research"] == {"family_material": {"found": 1}} and counts["generators"] == {"admitted": 1}
    assert not any(i in json.dumps(examiner.policy_payload("officeqa", previous=policy, outcomes=counts)) for i in ids)
    acc = examiner.build(specs, halves["g_self"], bench="officeqa", generator="fx-gen-officeqa-2", set_name="G_acc",
                         seed=7, evidence=FIXTURE, start=built.next_number)  # fixture: one finding, no g_acc half
    assert (built.next_number, acc.next_number) == (4, 8) and not {i["id"] for i in acc.items} & set(ids)  # C4-1
    paired = examiner.g_acc(acc.items, ["oq-a", "oq-b", "oq-c"], bench="officeqa", generator="fx-gen-officeqa-2")
    assert [p["source_item"] for p in paired] == ["oq-a", "oq-b", "oq-c"]  # one generated item per A* item
    assert len({p["id"] for p in paired}) == 3 and {p["id"] for p in paired} <= {i["id"] for i in acc.items}
    with pytest.raises(ValueError, match="frozen generator"):
        examiner.g_acc(made, ["oq-a"], bench="officeqa", generator="fx-gen-officeqa-2")  # G_self items
    capped = examiner.build([dict(specs[0], params=PARAMS * 3)] * 2, halves["g_self"], bench="officeqa",
                            generator="fx-gen-cap", set_name="G_self", seed=7, evidence=FIXTURE)
    assert len(capped.items) == 10 and sum(r["dropped"].get("finding_exhausted", 0) for r in capped.results) >= 12


# ------------------------------------------------------------------------------------------------- T-EXAM-5
def _rates(*passes, size=BAND_PROBE_ITEMS):
    return [[cell("it-%d" % n, "pass" if n < p else "fail") for n in range(size)] for p in passes]


def test_exam5_band_adjustments_are_bounded():
    ids = ["it-%d" % n for n in range(BAND_PROBE_ITEMS)]
    first = examiner.band(_rates(27), ids)
    assert (first["in_band"], first["direction"], first["adjustments"]) == (False, "too_easy", 0)
    hint = examiner.generator_payload("officeqa", [], band=first)["band"]
    assert hint == {"pass_rate": 0.9, "direction": "too_easy", "adjustment": 1}
    second = examiner.band(_rates(27, 3), ids)
    assert (second["direction"], second["adjustments"]) == ("too_hard", 1)
    third = examiner.band(_rates(27, 3, 15), ids)
    assert third["in_band"] and third["adjustments"] == BAND_ROUNDS - 1 and third["pass_rate"] == 0.5
    with pytest.raises(ValueError, match="at most two"):
        examiner.band(_rates(27, 3, 3, 15), ids)  # a fourth probe is refused
    with pytest.raises(ValueError, match="at most twice"):
        examiner.generator_payload("officeqa", [], band=examiner.band(_rates(27, 3, 3), ids))
    with pytest.raises(ValueError, match="at most twice"):
        examiner.generator_payload("officeqa", [], band=third)  # no adjustment after an in-band probe
    with pytest.raises(ValueError, match="final set"):
        examiner.band(_rates(15), ids[:3])
    unknown = examiner.band([[cell("it-0", "unknown")] + _rates(9)[0][1:]], ids)
    assert unknown["rounds"][0]["unknown"] == 1 and unknown["pass_rate"] == 8 / 30  # unknown is not passed
    stopped = examiner.band([[cell("it-0", "pass", stopped=True)] + _rates(9)[0][1:]], ids)
    assert stopped["rounds"][0]["unknown"] == 1 and stopped["pass_rate"] == 8 / 30  # stopped before its verdict
    built = examiner.Generated("fx-gen-band", "officeqa", ({"items": [], "made": 2, "dropped": {"format": 2},
                                                            "status": "none_kept", "family": "officeqa.ratio",
                                                            "material": "m"},))
    gated = examiner.gates(built, {"band": _rates(9)}, evidence=FIXTURE)
    assert not gated["admitted"] and gated["failed"] == ["truth", "band", "shortcut", "labels"]
    assert gated["truth"]["dropped"] == {"format": 2} and gated["band"]["reason"] == "not_run"


def test_r6b_the_band_and_shortcut_gates_count_scorer_v2_tokens():
    """Registrar addendum 2026-10-22 15:5x R6 (b): as the self-test and the acceptance do, the band and shortcut gates
    count ``judge.v2.token`` -- a JSON-carried right answer the completion-aware verdict calls a fail is a pass."""
    ids = ["it-%d" % n for n in range(BAND_PROBE_ITEMS)]
    rescued = [cell("it-%d" % n, "pass" if n < 15 else "fail", final="fail") for n in range(BAND_PROBE_ITEMS)]
    found = examiner.band([rescued], ids)
    assert found["pass_rate"] == 0.5 and found["in_band"]  # by the final tokens: 0 of 30, "too_hard"
    twice = [cell(i, "pass", run=r, arm="C", final="fail") for i in ids[:3] for r in (1, 2)]
    rest = [cell(i, t, run=r, arm="C") for i in ids[3:10] for r, t in ((1, "pass"), (2, "fail"))]
    cut = examiner.shortcut(twice + rest, ids, bench="officeqa")  # a ten-item shortcut probe: 3 of 10 > 25 %
    assert cut["dropped"] == ids[:3] and not cut["used"]  # by the final tokens nothing is right twice


# ------------------------------------------------------------------------------------------------- T-EXAM-6
def _items(answers, *, bench="livemath", checked_by=livemath.CHECKED_BY, kind="sympy_solve"):
    return [generated_item(evidence=FIXTURE, generator="fx-gen-lm", number=n, bench=bench, family="livemath.binomial",
                           source_item=None, material_id="m", public={"question": "Q%d" % n, "choices": "A. 1"},
                           private_fields={"answer": letter}, truth={"kind": kind, "checked_by": checked_by},
                           set_name="G_self", seed=1) for n, letter in enumerate(answers)]


def test_exam6_shortcut_rejection_variants_and_label_regularity(monkeypatch):
    ids = ["it-%d" % n for n in range(8)]
    right_twice = [cell(i, "pass", run=r, arm="C") for i in ids[:3] for r in (1, 2)]
    rest = [cell(i, t, run=r, arm="C") for i in ids[3:] for r, t in ((1, "pass"), (2, "fail"))]
    cut = examiner.shortcut(right_twice + rest, ids, bench="officeqa")
    assert not cut["used"] and cut["flagged_share"] == 3 / 8 and cut["dropped"] == ids[:3]  # > 25 %: the whole set
    assert examiner.shortcut(right_twice[:2] + rest, ids, bench="livemath")["used"]  # 1 of 6: kept
    with pytest.raises(ValueError, match="Two runs"):
        examiner.shortcut(rest[::2], ids, bench="officeqa")
    assert examiner.shortcut(None, ids, bench="spreadsheetbench")["reason"] == "not_run"

    balanced = _items("ABCDE" * 2)
    assert examiner.labels(balanced, bench="livemath") == {"truth_by_fixed_code": True, "ok": True,
                                                           "key_balance": {k: 0.2 for k in "ABCDE"}}
    assert not examiner.labels(_items("AABCDEABCD"), bench="livemath")["ok"]  # A at 30 %
    assert not examiner.labels(_items("ABCDE", checked_by="examiner"), bench="livemath")["ok"]  # not fixed code
    built = examiner.Generated("fx-gen-lm", "livemath", ({"items": _items("AAAAB"), "made": 5, "dropped": {},
                                                          "status": "made", "family": "livemath.binomial",
                                                          "material": "m"},))
    lm_ids = [i["id"] for i in built.items]
    monkeypatch.setattr(examiner, "BAND_PROBE_ITEMS", 5)  # the five-item fixture's band probe (Codex finding #9)
    gated = examiner.gates(built, {"band": [[cell(i, t) for i, t in zip(lm_ids, ["pass", "fail"] * 3)]],
                                   "shortcut": [cell(i, "fail", run=r) for i in lm_ids for r in (1, 2)]},
                           evidence=FIXTURE)
    assert gated["failed"] == ["labels"] and gated["kept"] == [] and gated["kept_sha256"] is None

    item = _items("A")[0]
    variant = verified(examiner.shortcut_variant(item), "generated-item")
    assert variant["public"] == {"question": "", "choices": "A. 1"} and variant["set"] == "shortcut"
    assert variant["variant_of"] == item["record_sha256"] and variant["id"] == item["id"]
    office = _items("1", bench="officeqa")[0]
    office = generated_item(evidence=FIXTURE, generator="fx-gen-oq", number=0, bench="officeqa",
                            family="officeqa.ratio", source_item=None, material_id="m",
                            public={"question": "What is the ratio?", "context": "Table: x"},
                            private_fields={"answer": "2"}, truth={"kind": "family_reference"}, set_name="G_self",
                            seed=1)
    office_variant = examiner.shortcut_variant(office)
    assert office_variant["public"] == {"question": "What is the ratio?", "context": ""}
    assert examiner.probe_mode(office_variant) is None and examiner.probe_mode(variant) is None  # plain blanks
    # SpreadsheetBench (ticket C1-2): the public fields stay, so the program runs on the real input; the cell's mode
    # tells the shell to show no workbook
    public = {"instruction": "Put the sum of A1:A5 into B1.", "input_files": ["/tmp/fx/input.xlsx"],
              "answer_position": "B1"}
    workbook = generated_item(evidence=FIXTURE, generator="fx-gen-sb", number=0, bench="spreadsheetbench",
                              family="spreadsheetbench.formula_edit", source_item="fx-spreadsheetbench-00",
                              material_id="m", public=public,
                              private_fields={"test_files": ["/tmp/fx/answer.xlsx"], "answer_position": "B1"},
                              truth={"kind": "recalc_formula", "checked_by": sheet.CHECKED_BY}, set_name="G_self",
                              seed=1)
    sb_variant = verified(examiner.shortcut_variant(workbook), "generated-item")
    assert sb_variant["public"] == public and sb_variant["private"] == workbook["private"]
    assert (sb_variant["set"], sb_variant["probe"], sb_variant["variant_of"]) == (
        "shortcut", "no_workbook", workbook["record_sha256"])
    assert examiner.probe_mode(sb_variant) == "no_workbook" == examiner.SHORTCUT_PROBES["spreadsheetbench"]
    with pytest.raises(ValueError, match="shortcut-probe variant"):
        examiner.probe_mode(workbook)  # the generated item itself is no probe variant
    # the gate judges SpreadsheetBench like the other benches, on cells that ran without the workbook only
    sb_ids = ["gen:fx-gen-sb:%d" % n for n in range(4)]
    sb_cells = [cell(i, "pass", run=r, arm="C", bench="spreadsheetbench", shortcut="no_workbook")
                for i in sb_ids[:1] for r in (1, 2)] + [
        cell(i, t, run=r, arm="C", bench="spreadsheetbench", shortcut="no_workbook")
        for i in sb_ids[1:] for r, t in ((1, "pass"), (2, "fail"))]
    judged = examiner.shortcut(sb_cells, sb_ids, bench="spreadsheetbench")
    assert (judged["probe"], judged["dropped"], judged["flagged_share"], judged["used"]) == (
        "no_workbook", sb_ids[:1], 0.25, True)
    with pytest.raises(ValueError, match="probe mode"):  # a probe cell that saw the workbook
        examiner.shortcut([cell(i, "fail", run=r, arm="C", bench="spreadsheetbench") for i in sb_ids for r in (1, 2)],
                          sb_ids, bench="spreadsheetbench")
    with pytest.raises(ValueError, match="probe mode"):  # QA probe cells run in the normal mode
        examiner.shortcut([cell(i, "fail", run=r, arm="C", shortcut="no_workbook") for i in ids for r in (1, 2)],
                          ids, bench="officeqa")
    probe = examiner.probe_items(_items("ABCDE" * 8), generator="fx-gen-lm", purpose="shortcut")
    again = examiner.probe_items(list(reversed(_items("ABCDE" * 8))), generator="fx-gen-lm", purpose="shortcut")
    assert len(probe) == 30 and [i["id"] for i in probe] == [i["id"] for i in again]


# ------------------------------------------------------------------------------- Codex findings #9 and #10
def _gated(size):
    """A LiveMath set of ``size`` items (balanced keys) through the gates: the band probe on its probe items, half
    right; the shortcut probe right on nothing."""
    items = _items(("ABCDE" * 7)[:size])
    built = examiner.Generated("fx-gen-lm", "livemath", ({"items": items, "made": size, "dropped": {},
                                                          "status": "made", "family": "livemath.binomial",
                                                          "material": "m"},))
    probe = examiner.probe_items(items, generator=built.generator, purpose="band")
    band_cells = [[cell(item["id"], "pass" if n % 2 else "fail") for n, item in enumerate(probe)]]
    shortcut_cells = [cell(item["id"], "fail", run=r, arm="C") for item in examiner.probe_items(
        items, generator=built.generator, purpose="shortcut") for r in (1, 2)]
    return built, band_cells, verified(examiner.gates(built, {"band": band_cells, "shortcut": shortcut_cells},
                                                      evidence=FIXTURE), "generator-gates")


def test_codex9_the_difficulty_gate_admits_only_on_30_qualified_probe_items():
    """Codex finding #9 (registration §7.2 "难度带（父包在 30 道探针题上 1 次的通过率在 20%–80% 之间"; no registrar
    relaxation): a set of 29 qualified items records insufficient material and is never admitted, even with a band
    probe of all 29 at 50 %; 30 items are admitted at the same rate. A deciding probe of fewer than 30 items is never
    in the band and has no adjustment direction."""
    assert BAND_PROBE_ITEMS == 30
    built, cells_29, short = _gated(29)
    assert len(built.items) == len(cells_29[0]) == 29 and not examiner.sufficient(built)
    assert not short["admitted"] and short["failed"] == ["band"] and short["kept"] == []
    assert short["band"] == {"in_band": False, "reason": "insufficient_material", "items": 29, "required": 30,
                             "probe_items": 0, "pass_rate": None, "direction": None}
    assert examiner.outcome_counts([short])["band"] == {"insufficient_material": 1}
    direct = examiner.band(cells_29, [item["id"] for item in built.items])
    assert (direct["in_band"], direct["direction"], direct["reason"], direct["pass_rate"]) == (
        False, None, "insufficient_material", 14 / 29)
    built, cells_30, full = _gated(30)
    assert examiner.sufficient(built) and len(cells_30[0]) == 30
    assert full["admitted"] and full["failed"] == [] and len(full["kept"]) == 30
    assert (full["band"]["probe_items"], full["band"]["pass_rate"], full["band"]["reason"]) == (30, 0.5, None)
    tilted = examiner.band([[cell(c["cell"]["task_id"], "pass") for c in cells_30[0]][:29]],
                           [item["id"] for item in built.items])
    assert not tilted["in_band"] and tilted["reason"] == "insufficient_material"  # 29 of the 30: no decision


def _researched(tmp_path):
    """(specs, the G_self half) of one researched OfficeQA table, as T-EXAM-4 makes them."""
    replies = [query("government revenue table"), pick("R1"), table("P1", 0)]

    def answer(system, payload):
        if system == examiner.POLICY_SYSTEM:
            return {"families": ["officeqa.percent_change"], "rationale": "Public finance tables.",
                    "requests": [{"kind": "family_material", "family": "officeqa.percent_change",
                                  "concept": "government revenue table", "topic": None}]}
        if system == examiner.GENERATOR_SYSTEM:
            return {"specs": [{"family": "officeqa.percent_change", "material": payload["materials"][0]["id"],
                               "params": PARAMS}]}
        return replies.pop(0)

    roles, _ = glm_roles(tmp_path / "glm", answer)
    label = "G/s2-officeqa/generate"
    policy, _ = examiner.policy_revise(roles, examiner.policy_payload("officeqa"), label=label, evidence=FIXTURE)
    researcher = research.Researcher(roles, sources(tmp_path)[0], leakage.Corpus("officeqa", officeqa_items(40)),
                                     bench="officeqa", label=label + "/research")
    sent = examiner.research_requests(policy, researcher)
    halves = research.split([f for _, f in sent if f["status"] == "found"], label, evidence=FIXTURE)
    specs, _ = examiner.generator_write(roles, examiner.generator_payload("officeqa", halves["g_self"]), label=label,
                                        evidence=FIXTURE)
    return specs, halves["g_self"]


def test_codex10_ten_items_per_finding_hold_across_the_attempts_builds(tmp_path):
    """Codex finding #10 (registration §7.2 "每条合格发现最多派生 10 道题", plan T-GEN-6; no per-build exception): the
    band adjustments rebuild from the same findings, so the counter continues across the attempt's builds --
    ``examiner.build`` from the previous build's ``derived``, and ``step._build`` from the counter the attempt's
    previous build of the set persisted (``finding-counts-<n>.json``) -- never 10 + 10 + 10 items of one finding."""
    specs, g_self = _researched(tmp_path)
    (finding,) = [material["id"] for material in g_self]
    many = [dict(specs[0], params=PARAMS * 3)]  # twelve parameter sets on the one finding
    first = examiner.build(many, g_self, bench="officeqa", generator="fx-gen-cap", set_name="G_self", seed=7,
                           evidence=FIXTURE)
    assert len(first.items) == MAX_ITEMS_PER_FINDING and first.derived == {finding: 10}
    again = examiner.build(many, g_self, bench="officeqa", generator="fx-gen-cap", set_name="G_self", seed=7,
                           evidence=FIXTURE, start=first.next_number, derived=first.derived)
    assert again.items == [] and again.derived == {finding: 10}
    assert again.results[0]["dropped"]["finding_exhausted"] == 12 and again.results[0]["status"] == "none_kept"
    part = examiner.build(many, g_self, bench="officeqa", generator="fx-gen-cap", set_name="G_self", seed=7,
                          evidence=FIXTURE, derived={finding: 7})
    assert len(part.items) == 3 and part.derived == {finding: 10}
    with pytest.raises(ValueError, match="finding-keyed counter"):
        examiner.build(many, g_self, bench="officeqa", generator="fx-gen-cap", set_name="G_self", seed=7,
                       evidence=FIXTURE, derived={finding: 11})
    # the step's builds of one attempt: the second and third (two band adjustments) derive nothing more
    st = SimpleNamespace(bench="officeqa", k=2, name="G/s2-officeqa", evidence=FIXTURE,
                         services=SimpleNamespace(checker=None, engine=None))
    attempt = tmp_path / "generate" / "attempt-1"
    attempt.mkdir(parents=True)
    built, numbers = None, 0
    for n in (1, 2, 3):
        built = step._build(st, many, g_self, "G_self", None, attempt, numbers)
        numbers = built.next_number
        persisted = verified(json.loads((attempt / ("finding-counts-%d.json" % n)).read_text()), "finding-counts")
        assert (persisted["set"], persisted["build"], persisted["derived"]) == ("G_self", n, {finding: 10})
        assert len(built.items) == (10 if n == 1 else 0)
    assert numbers == 3 * first.next_number  # every build numbers its items afresh: no id names two (ticket C4-1)
    # another attempt (a redo) and another set (G_acc, the other research half) start their own counters
    redo = tmp_path / "generate" / "attempt-2"
    redo.mkdir()
    assert len(step._build(st, many, g_self, "G_self", None, redo, 0).items) == 10
    assert len(step._build(st, many, g_self, "G_acc", None, attempt, numbers).items) == 10
