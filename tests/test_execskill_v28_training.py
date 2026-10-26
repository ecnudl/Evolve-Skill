"""v2.8 outcome-owned training and acceptance; synthetic offline evidence only."""
from types import SimpleNamespace
from contextlib import contextmanager
from dataclasses import replace

import pytest

from skillopt.execskill import acceptance, profiles as p, step
from tests.test_execskill_acceptance import N, fast_statistics, make_cells, seal  # noqa: F401


NEW = ("zebra-pc-v6", "alfworld-v3")
OLD = ("zebra-pc-v5", "alfworld-v2")


def paired_cells(count=10, *, faults=True, bad_format=False):
    cells = {}
    for n in range(count):
        for arm in ("S", "S'"):
            cell = {"cell": {"id": f"{arm}/{n}", "arm": arm, "task_id": str(n)},
                    "judge": {"v2": {"token": "pass" if arm == "S'" else "fail"},
                              "format": {"violation": bad_format and arm == "S'"}},
                    "faults": [{"procedure": "p", "kind": "crash:RuntimeError"}]
                              if faults and arm == "S'" else []}
            cells[(arm, str(n))] = [cell]
    return cells


@pytest.mark.parametrize("configuration", NEW + OLD)
def test_fault_guards_are_measured_but_only_v28_ignores_them(configuration):
    cells = paired_cells()
    verdict = step.train_verdict(cells, [str(n) for n in range(10)], [], {"p"},
        predicate_faults=10, routed=10, sign=False, configuration=configuration)
    assert verdict["own_fault_cells"] == verdict["predicate_faults"] == 10
    assert not verdict["guards"]["own_faults"] and not verdict["guards"]["predicate_faults"]
    assert verdict["adopted"] is (configuration in NEW)
    assert verdict["need"] == 1 and verdict["net"] == "10/1"
    if configuration in NEW:
        assert verdict["informational_guards"] == ["own_faults", "predicate_faults"]
        assert verdict["reason"] is None
    else:
        assert "informational_guards" not in verdict and verdict["reason"] == "guard:own_faults"


@pytest.mark.parametrize("configuration", NEW)
def test_v28_keeps_format_and_gain_guards(configuration):
    verdict = step.train_verdict(paired_cells(bad_format=True), [str(n) for n in range(10)], [], {"p"},
        predicate_faults=10, routed=10, sign=False, configuration=configuration)
    assert not verdict["adopted"] and verdict["reason"] == "guard:format"
    cells = paired_cells()
    for rows in cells.values():
        rows[0]["judge"]["v2"]["token"] = "pass"
    verdict = step.train_verdict(cells, [str(n) for n in range(10)], [], {"p"},
        predicate_faults=10, routed=10, sign=False, configuration=configuration)
    assert not verdict["adopted"] and verdict["reason"] == "gain:fixed_over_broken"


@pytest.mark.parametrize("configuration", NEW + OLD)
def test_final_selftest_faults_are_also_information_only_in_v28(configuration):
    cells = [row for rows in paired_cells().values() for row in rows]
    verdict = step.selftest_verdict(cells, {"zebralogic": [str(n) for n in range(10)]}, {"p"},
                                   configuration=configuration)
    assert verdict["fault_cells"] == 10 and verdict["fault_blocks"]
    assert verdict["blocked"] is (configuration in OLD)
    formatted = [row for rows in paired_cells(bad_format=True).values() for row in rows]
    verdict = step.selftest_verdict(formatted, {"zebralogic": [str(n) for n in range(10)]}, {"p"},
                                   configuration=configuration)
    assert verdict["blocked"]


@pytest.mark.parametrize("configuration", NEW + OLD)
def test_j3_measured_but_not_deciding_only_in_v28(tmp_path, configuration):
    sealed = seal(tmp_path, rule=p.PRACTICAL_RULE, configuration=configuration)
    cells = make_cells(sealed, faults=lambda job: [{"procedure": N.id, "hook": "before_call", "kind": "timeout"}]
                       if job["arm"] == "S'" else [])
    result = acceptance.decide(cells, sealed)
    assert result["guards"]["J1"]["ok"] and not result["guards"]["J3"]["ok"]
    assert result["guards"]["J3"]["fault_items"] > 1
    assert result["decision"] == ("accept" if configuration in NEW else "reject")
    assert ("configuration" in sealed) is (configuration in NEW)
    assert result["guards"]["J3"].get("informational", False) is (configuration in NEW)
    assert acceptance.reproduce(cells, sealed, result)


@pytest.mark.parametrize("configuration", NEW)
def test_v28_j4_remains_fatal_even_with_informational_faults(tmp_path, configuration):
    sealed = seal(tmp_path, rule=p.PRACTICAL_RULE, configuration=configuration)
    cells = make_cells(sealed, violation=lambda job: job["arm"] == "S'")
    result = acceptance.decide(cells, sealed)
    assert result["decision"] == "reject" and "J4" in result["reason"]


@pytest.mark.parametrize("configuration", NEW)
def test_v28_infrastructure_instrument_still_pauses(tmp_path, configuration):
    sealed = seal(tmp_path, rule=p.PRACTICAL_RULE, configuration=configuration)
    cells = make_cells(sealed, flags=lambda job: ["reasoning_mismatch"])
    result = acceptance.decide(cells, sealed)
    assert result["decision"] == "undetermined" and not result["guards"]["J5"]["ok"]


@pytest.mark.parametrize("configuration", NEW + OLD)
def test_training_routes_reuse_one_worker_per_package_pass(monkeypatch, configuration):
    opened = []
    @contextmanager
    def workers(*args, **kwargs):
        opened.append(kwargs)
        yield SimpleNamespace(calls=0)

    def route(package, bench, view, worker):
        worker.calls += 1
        return SimpleNamespace(count=worker.calls, faults=())

    st = SimpleNamespace(bench="zebralogic", setting=SimpleNamespace(extra={"configuration": configuration}),
                         services=SimpleNamespace(workers=workers, item_workers=None))
    package = SimpleNamespace(for_bench=lambda bench: ["p"])
    monkeypatch.setattr(step.router, "route", route)
    result = step._routes(st, package, [("a", {}), ("b", {})], {"a": {}, "b": {}})
    assert {key: value.count for key, value in result.items()} == {"a": 1, "b": 2}
    assert len(opened) == 1
    if configuration in NEW:
        assert opened[0]["hashseed"] == 0


def test_v28_note_coverage_reconstructs_factual_lexicon_words():
    from skillopt.execskill import policy
    from tests.test_execskill_v25_training import procedure, package, trace, coverage
    proc = replace(procedure("p-units", fields={"facts": ["The value has units; return means the trip back."]}),
                   policy_version=policy.POLICY_VERSION_V28)
    pack = package(proc)
    trajectory = trace(pack)
    result = coverage(proc.id, pack, [trajectory])
    assert result["with_notes"] == 1 and result["fields"]["facts"] == 1 and result["faults"] == 0


@pytest.mark.parametrize("configuration", NEW)
def test_inert_changes_skip_train_evaluation_and_do_not_consume_patience(monkeypatch, configuration):
    incumbent = SimpleNamespace(sha256="incumbent")
    st = SimpleNamespace(parent=incumbent, setting=SimpleNamespace(extra={"configuration": configuration}))
    proposed = []

    def propose(st, cut, r, parent, **kwargs):
        proposed.append(r)
        change = {"id": "p-inert", "n": 1, "kind": "new", "target": None, "summary": "No usable note.",
                  "survived": True, "inert": True, "attempts": [{"failed": None}]}
        return {"candidate_sha256": None, "engineer": {"changes": [change], "dropped": [],
                "analysis": {"items": []}, "disclosed": [], "lint": []}}

    monkeypatch.setattr(step, "_engineer_train", propose)
    monkeypatch.setattr(step, "_train_eval", lambda *args, **kwargs: pytest.fail("Inert changes must cost no cells"))
    final, records, last = step._train(st, {"run": []}, None)
    assert final is incumbent and last is None and len(proposed) == p.TRAIN_ROUNDS
    assert all(row["reason"] == "inert" and row["inert"] == ["p-inert"]
               and row["proposals"][0]["fate"] == "inert" and not row["patience_counted"] for row in records)
