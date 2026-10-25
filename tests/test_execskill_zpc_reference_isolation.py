"""Private-only Zebra sentinels through the real writer pipeline, with authored offline role/sandbox fakes."""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer, examiner, profiles, rounds, step, trajectories, zebralogic
from skillopt.execskill.package import FIXTURE, empty
from skillopt.execskill.registry import Registry
from tests.execskill_fakes import engineer_reply
from tests.execskill_zpc_fakes import tmp_path
from tests import test_execskill_zpc_pipeline as fixture
from tests.test_execskill_zpc_pipeline import offline

BENCH = "zebralogic"
GENERIC = '''def applies(view):
    return "columns" in view
def before_call(view, state):
    return {"facts": ["Check all public clues before completing the grid."]}
'''
DETECTOR = '''def detect(view):
    return bool(view["replies"])
'''


def private_pool(pool):
    """Every answer is opaque and absent from every public item, including other strata/slices."""
    cut = zebralogic.slices(pool)
    membership = {item["task_id"]: name for name, items in cut.items() for item in items}
    sentinels = {name: [] for name in (*cut, "excluded", "sealed")}
    for index, item in enumerate(pool):
        name = membership.get(item["task_id"], "excluded")
        houses, width = map(int, item["task"].split("*"))
        item["public"]["question"] = ("There are %d houses, numbered 1 to %d from left to right, as seen from across the street. "
            "Synthetic public task %s. Use the ordering constraints to fill each registered attribute."
            % (houses, houses, item["task_id"]))
        grid = {}
        for house in range(1, houses + 1):
            values = ["%sPRIVATE%03dH%dC%d" % (name.upper(), index, house, column) for column in range(width)]
            sentinels[name] += values
            grid["House %d" % house] = dict(zip(item["public"]["columns"], values))
        item["private"]["answer"] = grid
    sentinels["sealed"] = ["SEALEDPRIVATEANSWERSENTINEL"]
    public = json.dumps([item["public"] for item in pool])
    assert all(value not in public for values in sentinels.values() for value in values)
    return zebralogic.slices(pool), sentinels


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child)


def test_private_references_are_consumed_run_only_in_real_pipeline(tmp_path, monkeypatch):
    calls, contexts, panel_reads = [], [], []
    def forbidden_panel(*args, **kwargs):
        panel_reads.append((args, kwargs))
        pytest.fail("The evolution pipeline must never request a sealed panel")
    monkeypatch.setattr(zebralogic, "test_panel", forbidden_panel)
    source_worker = fixture.SourceWorker

    class RecordingWorker(source_worker):
        def start(self, package, *, kind, inputs_dir=None):
            # Detector bundles expose source entries but no Package.order; this fake supplies its call whitelist.
            if not hasattr(package, "order"):
                package = SimpleNamespace(procedures=package.procedures,
                                          order=tuple(entry.id for entry in package.procedures))
            return super().start(package, kind=kind, inputs_dir=inputs_dir)

        def call(self, proc_id, fn, args, *, timeout_s):
            calls.append((self.kind, fn, deepcopy(args)))
            return super().call(proc_id, fn, args, timeout_s=timeout_s)

    monkeypatch.setattr(fixture, "SourceWorker", RecordingWorker)
    setting, services, fake_solver, glm = fixture.build(tmp_path, monkeypatch)
    cut, sentinels = private_pool(setting.pools[BENCH])
    by_question = {item["public"]["question"]: item for item in setting.pools[BENCH]}
    run_ids = {item["task_id"] for item in cut["run"]}
    run_keys = {rounds.key(BENCH, ident) for ident in run_ids}
    embedded = sentinels["run"][0]
    copied = GENERIC.replace('"Check all public clues before completing the grid."',
                             repr("House 1 Attribute0 " + embedded))

    def answer(system, user):
        view = zebralogic.parse_user(user)
        item = by_question[view["question"]]
        if item["task_id"] in run_ids:
            # Scripted responses exercise reference disclosure and masking, not a solver efficacy claim.
            grid = deepcopy(item["private"]["answer"])
            if not view.get(profiles.NOTES_KEY):
                grid["House 1"][view["columns"][0]] = "incorrect synthetic guess"
        else:
            grid = {"House %d" % house: {column: "incorrect synthetic guess" for column in view["columns"]}
                    for house in range(1, zebralogic.public_house_count(view) + 1)}
        return json.dumps({"reasoning": "A scripted fixture response.", "solution": grid})

    def role(system, payload):
        if system == examiner.DETECTOR_SYSTEM:
            return engineer_reply({"detectors": [{"description": "Checks the presence of a masked reply."}]},
                                  [DETECTOR])
        if system == engineer.ANALYST_SYSTEM:
            return engineer_reply({"findings": []}, [])
        if system == engineer.ENGINEER_SYSTEM_ZPC:
            if payload["request"] == "fix" or payload["round"] == 1:
                return engineer_reply({"changes": [{"kind": "new", "description": "Checks all public clues.",
                    "hooks": ["applies", "before_call"], "max_note_chars": 4000,
                    "excluded_benches": list(profiles.BENCHES)}]},
                    [GENERIC if payload["request"] == "fix" else copied])
            return engineer_reply({"changes": []}, [])
        return {"verdict": "yes", "reason": "This literal copies a private run-grid assignment."}

    fake_solver.rules = [(None, answer)]
    glm.replies = role
    original = engineer.run_train

    def capture(ctx):
        contexts.append(ctx)
        return original(ctx)

    monkeypatch.setattr(engineer, "run_train", capture)
    parent = empty(step="D/s0", evidence=FIXTURE)
    found = step.run_step(setting, "D", BENCH, 1, parent, services=services)
    root = setting.root / "D" / "s1-zebralogic"
    assert found.record["decision"] == "reject"  # train improves; the untouched acceptance answers stay hidden
    assert fixture.result(root, "train-r1")["adopted"] is True
    attempts = fixture.result(root, "engineer-r1")["engineer"]["changes"][0]["attempts"]
    assert attempts[0]["failed"] == "C4" and attempts[1]["passed"]
    collision = next(check for check in attempts[0]["checks"] if check["check"] == "C4" and not check["passed"])
    assert collision["detail"]["hits"] and collision["detail"]["kept"] is False
    assert any("answer_text" in hit["reasons"] for hit in collision["detail"]["hits"])

    consumed = services.registry.entries("D-zpc1", BENCH)
    assert all(consumed[ident]["state"] == "decided" and consumed[ident]["purpose"] == "run" for ident in run_ids)
    assert contexts and all(set(ctx.references) <= run_keys for ctx in contexts)
    assert all(ctx.corpora[BENCH].size == 60 for ctx in contexts)
    assert any(ctx.references for ctx in contexts)
    assert panel_reads == []
    key, view = contexts[0].routing_items[0]
    with pytest.raises(ValueError, match="exact public view"):
        replace(contexts[0], routing_items=[(key, {**view, "reference": embedded})])

    role_channels = json.dumps(glm.seen)
    persisted = "\n".join(path.read_text() for path in tmp_path.rglob("*") if path.is_file())
    feedback = fixture.result(root, "train-r1")["feedback"]
    shown = [entry for entry in _walk(feedback) if "reference" in entry]
    assert shown and all(entry["task_id"] in run_keys for entry in shown)
    assert any(value in json.dumps(feedback) for value in sentinels["run"])
    analyst = [payload for system, payload in glm.seen if system == engineer.ANALYST_SYSTEM]
    proposed = [payload for system, payload in glm.seen if system == engineer.ENGINEER_SYSTEM_ZPC]
    assert analyst and proposed
    assert any(value in json.dumps(analyst) for value in sentinels["run"])
    assert any(entry.get("reference") for payload in proposed for entry in _walk(payload))
    for name in ("smoke", "accept", "spare", "excluded", "sealed"):
        assert sentinels[name], name
        for value in sentinels[name]:
            assert value not in role_channels and value not in persisted
            assert value not in json.dumps(calls) and value not in json.dumps(feedback)

    # Actual examiner requests and actual detector sandbox calls mask grids before exposure.
    examiner_calls = [payload for system, payload in glm.seen if system == examiner.DETECTOR_SYSTEM]
    detector_calls = [args[0] for _, fn, args in calls if fn == "detect"]
    assert examiner_calls and detector_calls
    for view in detector_calls:
        assert set(view) == {"bench", "task", "notes", "replies"}
        assert "passed" not in view
    assert not any(value in json.dumps(examiner_calls + detector_calls) for value in sentinels["run"])

    public_views = [args[0] for _, fn, args in calls if fn in ("applies", "before_call")]
    assert public_views
    assert all(set(view) == {"question", "columns"} and view == by_question[view["question"]]["public"]
               for view in public_views)
    assert not any(value in json.dumps(public_views) for values in sentinels.values() for value in values)
    # Solver requests contain only public text and authored notes; references stay in the method roles.
    assert not any(value in json.dumps(fake_solver.requests) for values in sentinels.values() for value in values)

    # Notes can themselves hold a complete grid. Both masking paths hide them, independent of reply masking.
    stored = contexts[0].trajectories[0]
    changed = {key: deepcopy(value) for key, value in stored.items() if key not in (profiles.RECORD_HASH, "version", "evidence")}
    view = zebralogic.parse_user(changed["calls"][0]["user"])
    note = json.dumps({"solution": cut["run"][0]["private"]["answer"]})
    changed["calls"][0]["user"] = zebralogic.render_user(view, notes=note)
    changed = profiles.record("trajectory", FIXTURE, changed)
    for purpose in ("examiner", "detector"):
        masked = trajectories.masked_view(changed, bench=BENCH, purpose=purpose)
        assert masked["notes"] == trajectories.MASK
        assert not any(value in json.dumps(masked) for value in sentinels["run"])


@pytest.mark.parametrize("fault", ["unconsumed", "registered", "dispatched", "wrong_unit", "wrong_root",
                                  "wrong_purpose", "changed_identity"])
def test_reference_boundary_refuses_unconsumed_or_misattributed_items(tmp_path, fault):
    item = fixture.fixture_pool()[0]
    item["private"]["answer"]["House 1"]["Attribute0"] = "PRIVATEBOUNDARYSENTINEL"
    registry = Registry(tmp_path / "registry", evidence=FIXTURE)
    st = SimpleNamespace(bench=BENCH, namespace="D-zpc1", services=SimpleNamespace(registry=registry),
                         setting=SimpleNamespace(root=tmp_path / "root"),
                         label=lambda unit: "D/s1-zebralogic/" + unit, purpose=lambda unit: unit)
    if fault != "unconsumed":
        unit = "D/s1-zebralogic/accept" if fault == "wrong_unit" else st.label("run")
        run_root = tmp_path / "another-root" if fault == "wrong_root" else st.setting.root
        registry.register(st.namespace, BENCH, [item], unit=unit, run_root=run_root,
                          purpose="accept" if fault == "wrong_purpose" else "run")
        if fault != "registered":
            registry.dispatch(st.namespace, BENCH, [item], unit=unit, run_root=run_root)
        if fault not in ("registered", "dispatched"):
            registry.decide(st.namespace, BENCH, [item], unit=unit, run_root=run_root)
    if fault == "changed_identity":
        item["private"]["answer"]["House 1"]["Attribute0"] = "CHANGEDPRIVATEIDENTITY"
    with pytest.raises(ValueError, match="consumed run items"):
        step._references(st, {"run": [item]}, [{"task_id": rounds.key(BENCH, item["task_id"]), "token": "fail"}])
