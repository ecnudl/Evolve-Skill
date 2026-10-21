"""The final evaluation reader of the two-architecture experiment: the registered E design (24 pilot val items, 3 runs
per arm), per-label item contrasts with a sign test and a bootstrap interval, and the registered reading (E primary,
T support, any other label descriptive only)."""
import json
import time

import pytest

from scripts import report_two_architectures as rt
from scripts import weak_solver_probe as probe

SOLVER = {"version": probe.VERSION, "backend": "free_router", "model": "deepseek-v4-flash", "benchmark": "officeqa",
          "max_tokens": 32768, "thinking": None, "reasoning_effort": None, "temperature": 0, "proxy": probe.GATEWAY,
          "response_model_ids": ["deepseek-flash", "deepseek-v4-flash"], "session_id_header": "X-Session-Id",
          "prompt": "continual_eval.backends.solve (the learning stages' solver prompt)"}


def _items(path, n_val=24, n_t=4, extra=()):
    items = [{"id": "E%02d" % i, "meta": {"part": "val"}, "public": {"question": "q%d" % i, "context": "c"},
              "private": {"answer": str(i)}} for i in range(n_val)]
    items += [{"id": "T%d" % i, "meta": {"part": "skill_confirmation"}, "public": {"question": "t%d" % i, "context": "c"},
               "private": {"answer": str(i)}} for i in range(n_t)]
    path.write_text(json.dumps({"items": items + list(extra)}))
    return path


def _probe(path, items, outcomes, *, runs=3, solver=None, drop=None):
    """outcomes[skill](item id, run) -> status."""
    rows = probe.load_items(str(items))
    config = {**(solver or SOLVER), "runs": runs, "items": [str(items)], "n_items": len(rows),
              "item_ids_hash": probe.digest(sorted(r["id"] for r in rows)),
              "items_hash": probe.digest(sorted(probe.digest(r) for r in rows)),
              "skills": {s: {"hash": probe.digest(s), "bytes": 1} for s in outcomes}, "started": time.strftime("%Y")}
    path.mkdir(parents=True)
    (path / "config.json").write_text(json.dumps(config))
    for skill, status in outcomes.items():
        for r in rows:
            for run in range(runs):
                if drop == (skill, r["id"], run):
                    continue
                target = path / "records" / skill / ("%s.%d.json" % (probe.digest(r["id"])[:24], run))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps({"skill": skill, "item": r["id"], "label": r["label"], "run": run,
                                              "status": status(r["id"], run)}))
    (path / "summary.json").write_text(json.dumps({"status": "completed", "config_hash": probe.digest(config)}))
    return path


def test_contrasts_per_label_and_the_registered_reading(tmp_path):
    pilot = _items(tmp_path / "pilot.json")
    first = {"E%02d" % i for i in range(6)}
    base = lambda item, run: "pass" if item in ("E00", "E01", "T0") else "fail"
    better = lambda item, run: "pass" if item in first | {"T0"} else "fail"
    both = lambda item, run: "pass" if item in first | {"T0", "T1", "T2", "T3"} else "fail"
    noisy = lambda item, run: "unknown" if item == "E05" else base(item, run)
    d = _probe(tmp_path / "p", pilot, {"bzero": base, "pool_all": better, "noisy": noisy, "both": both})
    value = rt.report(["bzero=%s:bzero" % d, "pool_all=%s:pool_all" % d, "noisy=%s:noisy" % d, "both=%s:both" % d],
                      ["pool_all-bzero", "noisy-bzero", "both-bzero"], pilot)
    e = value["contrasts"]["pool_all-bzero"]["by_label"]["val"]
    assert (e["items"], e["sum"], e["better"], e["worse"], e["tied"]) == (24, 4.0, 4, 0, 20)
    assert e["sign_test_p"] == pytest.approx(0.125) and e["interval"][0] > 0 and e["reading"] == "positive"
    assert value["contrasts"]["pool_all-bzero"]["by_label"]["skill_confirmation"]["sum"] == 0
    # E positive, T flat: registered as not an effect
    assert value["contrasts"]["pool_all-bzero"]["reading"] == "positive on E, not supported by T: not read as an effect"
    assert value["contrasts"]["both-bzero"]["reading"] == "effect: positive on E, supported by T"
    assert value["contrasts"]["noisy-bzero"]["by_label"]["val"]["excluded_unknown"] == 1
    assert value["contrasts"]["noisy-bzero"]["reading"] == "not established on E (interval contains 0)"
    assert value["roles"] == {"skill_confirmation": "T (support)", "val": "E (primary)"} and value["runs"] == 3
    assert value["pass_rate"]["bzero"]["val"] == {"items": 24, "known_runs": 72, "pass_rate": round(2 / 24, 6)}
    assert any("pool_all-bzero: positive on E" in line for line in rt.lines(value))


def test_another_label_is_descriptive_only(tmp_path):
    gate = [{"id": "G%d" % i, "meta": {"part": "train"}, "public": {"question": "g%d" % i, "context": "c"},
             "private": {"answer": str(i)}} for i in range(3)]
    pilot = _items(tmp_path / "pilot.json", extra=gate)
    d = _probe(tmp_path / "p", pilot, {"bzero": lambda i, r: "fail",
                                       "x": lambda i, r: "pass" if i.startswith("G") else "fail"})
    value = rt.report(["bzero=%s:bzero" % d, "x=%s:x" % d], ["x-bzero"], pilot)
    assert value["roles"]["train"] == "descriptive only (not an effect)"
    assert value["contrasts"]["x-bzero"]["by_label"]["train"]["reading"] == "positive"
    assert value["contrasts"]["x-bzero"]["reading"] == "not established on E (interval contains 0)"


def test_the_bootstrap_interval_covers_zero_for_mixed_differences():
    interval = rt.bootstrap([1, -1, 1, -1, 0, 0, 1, -1])
    assert interval[0] < 0 < interval[1] and rt.bootstrap([]) is None
    assert rt.bootstrap([1, 0, 1]) == rt.bootstrap([1, 0, 1])  # seeded
    assert rt.sign_test(9, 0) == pytest.approx(2 / 512) and rt.sign_test(0, 0) == 1.0


def test_the_registered_design_is_enforced(tmp_path):
    pilot = _items(tmp_path / "pilot.json")
    always = lambda item, run: "pass"
    a = _probe(tmp_path / "a", pilot, {"bzero": always})
    refused = {
        "other items": _probe(tmp_path / "b", _items(tmp_path / "other.json", n_t=5), {"x": always}),
        "another solver": _probe(tmp_path / "c", pilot, {"x": always}, solver={**SOLVER, "model": "glm-5.3"}),
        "a missing run": _probe(tmp_path / "d", pilot, {"x": always}, drop=("x", "E01", 2)),
        "two runs": _probe(tmp_path / "e", pilot, {"x": always}, runs=2),
    }
    for why, d in refused.items():
        with pytest.raises(SystemExit):
            rt.report(["bzero=%s:bzero" % a, "x=%s:x" % d], [], pilot)
    two = _probe(tmp_path / "f", pilot, {"bzero": always, "x": always}, runs=2)
    with pytest.raises(SystemExit):  # every arm with two runs: not the registered three
        rt.report(["bzero=%s:bzero" % two, "x=%s:x" % two], [], pilot)
    short = _items(tmp_path / "short.json", n_val=23)
    with pytest.raises(SystemExit):  # fewer val items than registered (also as the pilot)
        rt.report(["x=%s:x" % _probe(tmp_path / "g", short, {"x": always})], [], short)
    changed = json.loads(pilot.read_text())
    changed["items"][3]["private"]["answer"] = "changed"
    (tmp_path / "regraded.json").write_text(json.dumps(changed))
    with pytest.raises(SystemExit):  # E scored against other answers than the pilot's
        rt.report(["x=%s:x" % _probe(tmp_path / "h", tmp_path / "regraded.json", {"x": always})], [], pilot)
    with pytest.raises(SystemExit):  # a contrast over an arm that is not loaded
        rt.report(["bzero=%s:bzero" % a], ["pool_all-bzero"], pilot)
    assert rt.report(["bzero=%s:bzero" % a, "x=%s:x" % _probe(tmp_path / "i", pilot, {"x": always})], ["x-bzero"],
                     pilot)["contrasts"]["x-bzero"]["reading"] == "not established on E (interval contains 0)"
