"""Evaluate a frozen five-domain study's policies on the canonical test split (paid; user request 10/5).

The canonical split (fivebench-split-v2) proves, bound to this study's protocol,
reference plans and learning panels, that the study evaluated exactly the train
part and learned only inside it, so its Skills can be tested on ``test``. Every
distinct policy of the study -- No-Skill and each accepted update of each
method; a stage without an update keeps its parent's policy -- is evaluated once
(one repeat) on each domain's test panel. A cell uses the study's own frozen
evaluation configuration for that domain with exactly three changes: the panel
(the domain's test panel), the partition (``final``) and the repeat count (1);
the method list names only the evaluated method. It runs the study's frozen
evaluation implementation in the budget-derived evaluation source that already
evaluated its new policies (same model service, budgets, scorer runtime and
re-qualified Sheet scorer), so No-Skill and every Skill share one code path; an
empty Skill adds no guidance, so No-Skill sees exactly its usual prompt.

Identity: test panels are built only from the very source files the split was
built from (by hash), must reproduce its test ids and families, and their file
hashes are bound into every request. The evaluation code and interpreter must
equal what the study's own evaluations of that domain recorded in their frozen
plans (source and runtime identity), the whole derived source tree must still
equal the frozen reference source except the Skill-budget literal, and this
tool and the study's orchestrator are bound by hash. Nothing is written into
the study. ``run`` waits on the study's native lock, re-verifies everything
after the wait and again before every cell, never resumes a begun cell,
replays recorded cells without new calls, and checks the evaluated checkpoint.
Only one cell generates at a time with the study's 10 workers (the key's limit
is about 10 concurrent calls); a finished cell is scored by a second worker
process while the next cell generates, but a generation that itself runs
containers or native episodes (SpreadsheetBench, ALFWorld) first waits for
scoring to finish, so there is one native workload at a time as in the study's
serial procedure. The controller is single-threaded: each round it first
collects exited workers, and after a failed cell it starts nothing further and
lets a running worker finish. Stopping a run is an operator action handled as
in the study's orchestrator, no more: see ``_Workers``. The test split is held
out from the study's learning and selection; it is not an exposure-filtered
independent final.
Run with PYTHONPATH and cwd at the study's frozen orchestrator source.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import checkpoint_path, read_json, require, safe_path, write_json

VERSION = "fivebench-test-eval-v8"
SPLIT_VERSION = "fivebench-split-v2"
OVERRIDE_KEYS = {"qualification_path", "qualification_sha256", "qualification_hash"}
# The key allows about 10 concurrent model calls, so model generation stays one cell at a time with
# the study's 10 workers; a cell's native scoring then overlaps the next cell's generation. Generation
# of these two benchmarks is itself native (Sheet runs the generated programs in containers, ALFWorld
# runs episodes), so it waits until scoring is idle: one native workload at a time, as in the study.
# The order puts each native scoring (Sheet, BCB, KOR) beside an API-only generation.
NATIVE_GENERATION = frozenset({"spreadsheetbench", "alfworld"})
GENERATION_ORDER = ("searchqa", "alfworld", "spreadsheetbench", "bigcodebench", "korbench")
POLL_SECONDS = 0.2  # the controller's polling step
# Test tasks that cannot be scored as released; excluded from evaluation, never repaired.
EXCLUDED = {"spreadsheetbench": {"42930": "upstream gold workbook is misnamed 1_43930_golden.xlsx, so the "
                                          "release cannot pair it with 1_42930_init.xlsx"}}


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


# ------------------------------------------------------------------ controller side (study source)
def _sequence():
    from scripts import continue_fivebench_baselines as sequence
    return sequence


def _study(study):
    sequence = _sequence()
    root = safe_path(study)
    protocol = read_json(root / "protocol.json", sealed=True)
    require(protocol["root"] == str(root) and protocol["version"] == sequence.BUDGET_SEQUENCE,
            "Only a budget-derived (v4) study is supported")
    sequence.check_frozen_files(protocol)  # read-only, unlike sequence.check()
    budget, checked = sequence._skill_limit(protocol), set()
    for ref in protocol["references"].values():  # the whole derived tree, not only its two edited files
        pair = (ref["source"], ref["evaluation_source"])
        if pair not in checked:
            sequence._check_budget_source(*pair, budget)
            checked.add(pair)
    return root, protocol


def _stages(root, protocol):
    """Every method's sealed stage records, bound as the orchestrator binds its chain."""
    stages = {}
    for method in protocol["methods"]:
        previous, parent_hash, rows = "", None, []
        for number, benchmark in enumerate(protocol["order"], 1):
            stage = read_json(root / method / f"s{number}-{benchmark}" / "stage.json", sealed=True)
            require(stage["protocol_hash"] == protocol["record_hash"] and stage["method"] == method
                    and stage["stage"] == number and stage["benchmark"] == benchmark
                    and stage["parent_skill"] == previous and stage["parent_stage_hash"] == parent_hash
                    and (stage["action"] == "selected_update") == (stage["skill"] != previous),
                    "Stage chain binding mismatch")
            rows.append(stage)
            previous, parent_hash = stage["skill"], stage["record_hash"]
        stages[method] = rows
    return stages


def policies(stages):
    """No-Skill plus every accepted update; each stage row points at the policy it deploys."""
    found = {"no_skill": {"method": "no_skill", "stage": 0, "chain": [], "stage_hash": None,
                          "skill_sha256": _text_sha("")}}
    rows = {}
    for method, records in stages.items():
        current, chain = "no_skill", []
        for stage in records:
            chain = chain + [stage["skill"]]
            if stage["action"] == "selected_update":
                current = f"{method}-s{stage['stage']}"
                found[current] = {"method": method, "stage": stage["stage"], "chain": chain,
                                  "stage_hash": stage["record_hash"], "skill_sha256": _text_sha(stage["skill"])}
            require(found[current]["skill_sha256"] == _text_sha(stage["skill"]),
                    "A stage row does not deploy its policy")
            rows[f"{method}-s{stage['stage']}"] = current
    return found, rows


def policy_order(found, rows, protocol):
    """No-Skill, then each method's final policy (the headline comparison), then the earlier stages."""
    last = len(protocol["order"])
    first = ["no_skill", *(rows[f"{method}-s{last}"] for method in protocol["methods"])]
    order = list(dict.fromkeys([*first, *found]))
    require(sorted(order) == sorted(found), "Every policy must be scheduled exactly once")
    return order


def _study_identity(stages, benchmark):
    """Code and interpreter identity recorded by the study's own evaluations of this benchmark."""
    seen = []
    for records in stages.values():
        for stage in records:
            cell = stage["cells"][benchmark]
            if cell.get("kind") == "new_frozen_policy_evaluation" and cell.get("reused") is False:
                plan = read_json(safe_path(cell["result"]["root"]) / "plan.json", sealed=True)
                require(plan["record_hash"] == cell["result"]["plan_hash"], "A study evaluation plan changed")
                seen.append({"source_identity": plan["source_identity"], "host_runtime": plan["host_runtime"]})
    require(seen and all(s == seen[0] for s in seen),
            "The study's evaluations of one benchmark disagree on their code or runtime identity")
    return seen[0]


def _outside(out, root, protocol, extra=()):
    frozen = {root, *map(safe_path, extra)} | {safe_path(ref[k]) for ref in protocol["references"].values()
                                               for k in ("root", "source", "evaluation_source") if k in ref}
    require(all(not out.is_relative_to(p) and not p.is_relative_to(out) for p in frozen),
            "Use a new directory outside the study, its references and the panel sources")


def _check_split(split, protocol):
    """The split must have been verified against exactly this study; containment is rechecked here."""
    require(split["version"] == SPLIT_VERSION and set(split["splits"]) == set(protocol["order"]), "Unsupported split")
    for benchmark in protocol["order"]:
        usage, ref, parts = split["f_study_usage"][benchmark], protocol["references"][benchmark], split["splits"][benchmark]
        plan = read_json(safe_path(ref["root"]) / "plan.json", sealed=True)
        learning_path = protocol["roles"][benchmark]["path"]
        require(usage["protocol_hash"] == protocol["record_hash"]
                and usage["reference_plan_hash"] == ref["plan_hash"] == plan["record_hash"]
                and usage["learning_panel_sha256"] == _sha(learning_path),
                "The split was not verified against this study")
        train = {e["task_id"] for e in parts["train"]}
        held = [e for part in ("val", "test", "reserve") for e in parts[part]]
        evaluated = {str(t["task_id"]) for t in plan["tasks"] if t["benchmark"] == benchmark}
        learning = {str(t["task_id"]) for t in read_json(learning_path)["tasks"]}
        require(evaluated == train and learning <= train and not train & {e["task_id"] for e in held}
                and not {e["family_id"] for e in parts["train"]} & {e["family_id"] for e in held},
                "The study used tasks or families outside train")


def _test_families(split, benchmark):
    """task_id -> family_id of the evaluated test tasks (the split's test part minus documented exclusions)."""
    test = {e["task_id"]: e["family_id"] for e in split["splits"][benchmark]["test"]}
    excluded = EXCLUDED.get(benchmark, {})
    require(set(excluded) <= set(test), "An exclusion is not a test task")
    return {task: family for task, family in test.items() if task not in excluded}


def _families(panel):
    return {str(t["task_id"]): str(t["family_id"]) for t in panel["tasks"]}


def build_test_panels(split, *, bcb_final, sheet_final, kor_final, searchqa_test, alfworld_test, alfworld_root):
    """Test panels from the very files the split was built from; returns {benchmark: panel}."""
    from skillopt.continual_eval import datasets

    for path in (bcb_final, sheet_final, kor_final, searchqa_test, alfworld_test):
        require(split["sources"].get(str(safe_path(path))) == _sha(path),
                "A test source is not the file the split was built from")
    panels = {"bigcodebench": read_json(bcb_final), "spreadsheetbench": read_json(sheet_final),
              "korbench": read_json(kor_final)}
    for benchmark in panels:
        dropped = EXCLUDED.get(benchmark, {})
        panels[benchmark] = {**panels[benchmark],
                             "tasks": [t for t in panels[benchmark]["tasks"] if str(t["task_id"]) not in dropped]}
    wanted = _test_families(split, "searchqa")
    rows = [r for r in read_json(searchqa_test) if str(r["id"]) in wanted]
    panels["searchqa"] = datasets.import_searchqa(
        rows, partition="final", revision=f"skillopt-searchqa-native-test:{SPLIT_VERSION}:{split['record_hash'][:12]}")
    panels["alfworld"] = datasets.import_alfworld(
        read_json(alfworld_test), data_root=alfworld_root, partition="final",
        revision=f"alfworld-json_2.1.1-valid_unseen:{SPLIT_VERSION}")
    require(all(t["private"]["game_metadata"]["source_split"] == "valid_unseen" for t in panels["alfworld"]["tasks"]),
            "ALFWorld test games must come from valid_unseen")
    for benchmark, panel in panels.items():
        datasets.validate_panel(panel)
        require(_families(panel) == _test_families(split, benchmark)
                and all(t["partition"] == "final" for t in panel["tasks"]),
                f"{benchmark}: test panel tasks or families differ from the split")
        require(datasets.readiness(panel)["status"] == "ready", f"{benchmark}: test panel assets not ready")
    return panels


def _config(protocol, benchmark, panel_path, method):
    ref = protocol["references"][benchmark]
    plan = read_json(safe_path(ref["root"]) / "plan.json", sealed=True)
    require(plan["record_hash"] == ref["plan_hash"], "Reference plan changed")
    config = deepcopy(plan["config"])
    config["panels"] = {b: (str(panel_path) if b == benchmark else None) for b in config["panels"]}
    config["partition"], config["repeats"] = "final", 1
    config["methods"] = ["no_skill"] if method == "no_skill" else ["no_skill", method]
    override = protocol.get("evaluation_runtime_overrides", {}).get(benchmark)
    if override is not None:  # the re-qualified scorer of the derived evaluation source (as in the study)
        require(set(override) == {"recalculation"} and set(override["recalculation"]) == OVERRIDE_KEYS,
                "Only the derived source's re-qualified scorer may be rebound")
        runtime = config["runtime"][benchmark]
        runtime["recalculation"] = {**runtime["recalculation"], **override["recalculation"]}
    return config


def _request(protocol, plan, benchmark, name, out):
    policy, ref = plan["policies"][name], protocol["references"][benchmark]
    orchestrator = str(Path(_sequence().__file__).absolute())
    require(orchestrator in protocol["source_files"], "The orchestrator is not the study's frozen one")
    return seal({"version": VERSION, "benchmark": benchmark, "policy": name, "method": policy["method"],
                 "stage": policy["stage"], "chain": policy["chain"],
                 "provenance": "fivebench_test_eval:" + (policy["stage_hash"] or "no_skill"),
                 "config": _config(protocol, benchmark, out / f"panels/{benchmark}.json", policy["method"]),
                 "run": str(out / f"runs/{benchmark}/{name}"), "repo": plan["repo"],
                 "workers": protocol["config"]["workers"], "service": plan["services"][benchmark],
                 "panel_sha256": plan["panels"][benchmark],
                 "expected_source_identity": plan["identities"][benchmark]["source_identity"],
                 "expected_host_runtime": plan["identities"][benchmark]["host_runtime"],
                 "evaluation_source": ref["evaluation_source"], "python": ref["python"],
                 "orchestrator": orchestrator, "orchestrator_sha256": protocol["source_files"][orchestrator],
                 "tool_sha256": plan["tool_sha256"]})


def prepare(study, split_path, output, repo, **panel_sources):
    root, protocol = _study(study)
    out = safe_path(output)
    _outside(out, root, protocol, [split_path, *panel_sources.values()])
    require(not out.exists(), "Use a new directory")
    split = read_json(split_path, sealed=True)
    _check_split(split, protocol)
    stages = _stages(root, protocol)
    found, rows = policies(stages)
    panels = build_test_panels(split, **panel_sources)
    services = {b: _sequence().verify_service(protocol["references"][b]["root"]) for b in protocol["order"]}
    identities = {b: _study_identity(stages, b) for b in protocol["order"]}
    out.mkdir(parents=True, mode=0o700)
    for benchmark, panel in panels.items():
        write_json(out / f"panels/{benchmark}.json", panel)
    plan = {"version": VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
            "split": str(safe_path(split_path)), "split_hash": split["record_hash"], "repo": str(safe_path(repo)),
            "panels": {b: _sha(out / f"panels/{b}.json") for b in panels}, "policies": found, "stage_rows": rows,
            "services": services, "identities": identities, "tool_sha256": _sha(Path(__file__)), "repeats": 1,
            "excluded": EXCLUDED,
            "cells": [[b, name] for name in policy_order(found, rows, protocol) for b in GENERATION_ORDER]}
    require(sorted(b for b, _ in plan["cells"]) == sorted(list(protocol["order"]) * len(found)),
            "Every benchmark must be scheduled for every policy")
    requests = {}
    for benchmark, name in plan["cells"]:
        path = out / f"requests/{benchmark}/{name}.json"
        write_json(path, _request(protocol, plan, benchmark, name, out))
        requests[f"{benchmark}/{name}"] = _sha(path)
    write_json(out / "test_eval.json", seal({**plan, "request_sha256": requests}))
    return read_json(out / "test_eval.json", sealed=True)


def _load(output):
    """Re-verify the tool, study, split, policies, identities, panels and every request."""
    out = safe_path(output)
    plan = read_json(out / "test_eval.json", sealed=True)
    require(plan["version"] == VERSION and plan["tool_sha256"] == _sha(Path(__file__)),
            "Unsupported test evaluation or changed tool")
    root, protocol = _study(plan["study"])
    _outside(out, root, protocol)
    split = read_json(plan["split"], sealed=True)
    require(split["record_hash"] == plan["split_hash"], "The split changed")
    _check_split(split, protocol)
    stages = _stages(root, protocol)
    found, rows = policies(stages)
    require(plan["protocol_hash"] == protocol["record_hash"] and found == plan["policies"]
            and rows == plan["stage_rows"]
            and {b: _study_identity(stages, b) for b in protocol["order"]} == plan["identities"],
            "The study, its policies or its evaluation identity changed")
    for benchmark, sha in plan["panels"].items():
        path = out / f"panels/{benchmark}.json"
        require(_sha(path) == sha and _families(read_json(path)) == _test_families(split, benchmark),
                "A test panel changed")
    for benchmark, name in plan["cells"]:
        path = out / f"requests/{benchmark}/{name}.json"
        require(read_json(path, sealed=True) == _request(protocol, plan, benchmark, name, out)
                and _sha(path) == plan["request_sha256"][f"{benchmark}/{name}"], "Test evaluation request changed")
    return out, plan, protocol


def _launch(request, operation, request_path, output, handle, admit=lambda: True):
    """Start one worker in the request's evaluation source with that reference's interpreter.

    ``admit`` is the admission point: it is asked last, after all preparation and immediately
    before the process is created; if it refuses, nothing is started and None is returned.
    """
    source = safe_path(request["evaluation_source"])
    command = [request["python"], str(Path(__file__).resolve()), "worker", "--operation", operation,
               "--request", str(request_path), "--output", str(output)]
    env = dict(os.environ, PYTHONPATH=str(source))
    if not admit():
        return None
    return subprocess.Popen(command, cwd=source, env=env, stdout=handle, stderr=handle)


class _Workers:
    """The controller's running worker processes; the controller itself is single-threaded.

    Stopping follows the study's own orchestrator (``subprocess.run``): workers are ordinary children
    in the controller's process group, so a signal sent to that group (closing the tmux session,
    Ctrl-C) reaches them directly, and when the controller itself fails or is interrupted with
    SIGINT it kills its running workers before re-raising. Nothing more is promised: a worker's own
    children (containers, native episode processes) are not tracked, and SIGTERM or SIGKILL sent to
    the controller alone leaves its workers running. A begun cell is never resumed automatically;
    when a run stops, every generated but not yet scored cell (up to four when scoring is slow)
    keeps its predictions and needs operator review.
    """

    def __init__(self):
        self.live = []

    def start(self, request_path, operation, output, log, other=None):
        """Start a worker, or return None when ``other`` (the other running worker) has exited.

        An exited worker may have failed, and a failed cell stops every further start, so the caller
        must collect it first. Whether it is still running is asked at the admission point.
        """
        request = read_json(request_path, sealed=True)
        handle = safe_path(log).open("ab")
        try:
            process = _launch(request, operation, request_path, output, handle,
                              lambda: other is None or other.poll() is None)
        except BaseException:
            handle.close()
            raise
        if process is None:
            handle.close()
            return None
        self.live.append((process, handle))
        return process

    def finish(self, process, output):
        """Collect an exited worker; a non-zero exit or a missing output is a failed cell."""
        code = process.wait()
        for entry in [e for e in self.live if e[0] is process]:
            entry[1].close()
            self.live.remove(entry)
        require(code == 0 and Path(output).is_file(), "Test evaluation worker failed; inspect its log, never retry")
        return read_json(output, sealed=True)

    def call(self, request_path, operation, output, log):
        """Run one worker to completion."""
        process = self.start(request_path, operation, output, log)
        while process.poll() is None:
            time.sleep(POLL_SECONDS)
        return self.finish(process, output)

    def stop_all(self):
        """Kill the running workers, as ``subprocess.run`` kills its child when it is interrupted."""
        for process, handle in self.live:
            process.kill()
            process.wait()
            handle.close()
        self.live.clear()


def _checked(out, plan, benchmark, name):
    policy = plan["policies"][name]
    evaluated = read_json(checkpoint_path(out / f"runs/{benchmark}/{name}", policy["method"], "h0",
                                          policy["stage"]), sealed=True)
    require(_text_sha(evaluated["skill_text"]) == policy["skill_sha256"],
            "Evaluated policy differs from the study policy")
    return read_json(out / f"results/{benchmark}/{name}.json", sealed=True)


def _start(output, workers, operation, benchmark, name, target, other=None):
    """Re-verify everything, then start one worker operation of one cell.

    Returns (process, its output), or None when the other running worker has exited by the
    admission point (after the re-verification and all launch preparation): it must be collected
    first, because a failed cell stops every further start.
    """
    out, _, _ = _load(output)
    suffix = "-verify" if operation == "verify" else ""
    result = out / target / benchmark / f"{name}.json"
    process = workers.start(out / f"requests/{benchmark}/{name}.json", operation, result,
                            out / f"logs/{benchmark}-{name}{suffix}.log", other)
    return None if process is None else (process, result)


def _pipeline(output, out, plan, pending, workers, results):
    """Generate one cell at a time and score finished cells meanwhile; one native workload at a time.

    Each round first collects exited workers. After a failed cell nothing further starts; a worker
    that is already running finishes first.
    """
    todo, unscored = list(pending), []
    generating = scoring = failed = None  # a running slot is (cell, process, its output)
    while True:
        if generating is not None and generating[1].poll() is not None:
            (cell, process, result), generating = generating, None
            try:
                workers.finish(process, result)
                unscored.append(cell)
            except Exception as exc:  # noqa: BLE001
                failed = failed or exc
        if scoring is not None and scoring[1].poll() is not None:
            (cell, process, result), scoring = scoring, None
            try:
                workers.finish(process, result)
                results[cell] = _checked(out, plan, *cell)
            except Exception as exc:  # noqa: BLE001
                failed = failed or exc
        try:
            if failed is None and scoring is None and unscored:
                started = _start(output, workers, "score", *unscored[0], "results",
                                 generating and generating[1])
                if started is None:
                    continue  # the generating worker exited meanwhile: collect it first
                scoring = (unscored.pop(0), *started)
            # A native generation (Sheet, ALFWorld) waits until no scoring is running or queued.
            if (failed is None and generating is None and todo
                    and not (todo[0][0] in NATIVE_GENERATION and (scoring is not None or unscored))):
                started = _start(output, workers, "generate", *todo[0], "generated", scoring and scoring[1])
                if started is None:
                    continue  # the scoring worker exited meanwhile: collect it (it may have failed) first
                generating = (todo.pop(0), *started)
        except Exception as exc:  # noqa: BLE001 - e.g. a changed input found by the re-verification
            failed = failed or exc
        if generating is None and scoring is None and (failed is not None or not (todo or unscored)):
            break
        time.sleep(POLL_SECONDS)
    if failed is not None:
        raise failed


def run(output):
    from skillopt.continual_eval.core import output_lock
    from skillopt.continual_learning.launch import learning_environment

    out, plan, protocol = _load(output)
    results, workers = {}, _Workers()
    lock_path = safe_path(protocol["config"]["native_lock"])
    with output_lock(out), lock_path.open("a") as lock, ExitStack() as launch:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)  # waits for any study or re-measurement holding it
        try:
            out, plan, protocol = _load(output)  # everything re-verified after the wait
            launch.enter_context(learning_environment({"benchmark": "alfworld", "model": protocol["model"],
                                                       "runtime": protocol["roles"]["alfworld"]["runtime"]}))
            (out / "logs").mkdir(parents=True, exist_ok=True)
            pending = []
            for benchmark, name in map(tuple, plan["cells"]):  # checked before anything pays
                done = out / f"results/{benchmark}/{name}.json"
                if done.exists():
                    process, verified = _start(output, workers, "verify", benchmark, name, "verify")
                    while process.poll() is None:
                        time.sleep(POLL_SECONDS)
                    require(workers.finish(process, verified) == read_json(done, sealed=True),
                            "Recorded test cell changed")
                    results[(benchmark, name)] = _checked(out, plan, benchmark, name)
                else:
                    require(not (out / f"runs/{benchmark}/{name}").exists(),
                            "An interrupted test cell needs operator review; it is never resumed automatically")
                    pending.append((benchmark, name))
            _pipeline(output, out, plan, pending, workers, results)
        except BaseException:  # the controller failed or was interrupted: kill its running workers
            workers.stop_all()
            raise
    summary = _summary(plan, protocol, results)
    write_json(out / "summary.json", summary)
    return summary


def smoke(output):
    """Zero-call check of every cell: bind identities, freeze its plan, bind the service, register its chain."""
    out, plan, _ = _load(output)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    workers = _Workers()
    try:
        return {f"{b}/{name}": workers.call(out / f"requests/{b}/{name}.json", "dryrun",
                                            out / f"smoke/{b}/{name}.json", out / f"logs/smoke-{b}-{name}.log")
                for b, name in plan["cells"]}
    except BaseException:
        workers.stop_all()
        raise


def _summary(plan, protocol, results):
    cells = {}
    for benchmark in protocol["order"]:
        base = {(r["task_id"], r["repeat"]): r["status"] for r in results[(benchmark, "no_skill")]["rows"]}
        for name in plan["policies"]:
            result = results[(benchmark, name)]
            require(result["benchmark"] == benchmark and result["positions"] == len(base)
                    and len(result["rows"]) == len(base), "Incomplete or foreign test cell")
            rows = {(r["task_id"], r["repeat"]): r["status"] for r in result["rows"]}
            require(set(rows) == set(base), "Test cells must cover the same positions")
            paired = Counter("unknown" if "unknown" in (rows[k], base[k]) else "tie" if rows[k] == base[k]
                             else "win" if rows[k] == "pass" else "loss" for k in base)
            counts = Counter(rows.values())
            cells.setdefault(benchmark, {})[name] = {
                "counts": {s: counts[s] for s in ("pass", "fail", "unknown")}, "positions": len(rows),
                "confirmed_pass_rate": counts["pass"] / len(rows), "vs_no_skill": dict(paired),
                "costs": {k: result["costs"].get(k) for k in ("logical_calls", "http_attempts", "reported_tokens",
                                                               "usage_complete", "unclosed_calls")}}
    return seal({"version": VERSION, "protocol_hash": plan["protocol_hash"], "split_hash": plan["split_hash"],
                 "stage_rows": plan["stage_rows"], "cells": cells, "repeats": 1, "excluded": plan["excluded"],
                 "schedule": "one cell generating at a time (10 workers); native scoring overlaps the next "
                             "API-only generation; native generations wait for scoring to be idle",
                 "data_scope": "test_split_held_out_from_the_study_learning_and_selection_"
                               "not_an_exposure_filtered_independent_final",
                 "single_learning_history": True, "deployment_authorized": False})


# ------------------------------------------------------------------ worker side (derived evaluation source)
def _orchestrator(path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("frozen_sequence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker(operation, request_path, output):
    from skillopt.continual_eval import core, runner
    from skillopt.continual_eval.core import freeze_plan, load_checkpoint, load_plan, register_checkpoint

    request = read_json(request_path, sealed=True)
    require(request["version"] == VERSION and operation in {"generate", "score", "verify", "dryrun"},
            "Unsupported worker request")
    new, config, method, stage = safe_path(request["run"]), request["config"], request["method"], request["stage"]
    benchmark = request["benchmark"]
    # Identity first, before anything is created or paid: this tool, the evaluation source it runs in,
    # the study's orchestrator, the code and interpreter of the study's own evaluations, and the panel.
    require(_sha(Path(__file__)) == request["tool_sha256"], "The evaluation tool changed")
    require(Path(core.__file__).resolve().parents[2] == safe_path(request["evaluation_source"]),
            "Worker imported the wrong evaluation source")
    require(_sha(request["orchestrator"]) == request["orchestrator_sha256"], "The study orchestrator changed")
    require(core.source_identity() == request["expected_source_identity"]
            and core.runtime_identity() == request["expected_host_runtime"],
            "Evaluation code or interpreter differs from the study's own evaluations")
    require(_sha(config["panels"][benchmark]) == request["panel_sha256"], "The test panel changed")
    sequence = _orchestrator(request["orchestrator"])

    def bound(plan):
        require(plan["config"] == config and plan["source_identity"] == request["expected_source_identity"]
                and plan["host_runtime"] == request["expected_host_runtime"]
                and plan["panels"][benchmark]["status"] == "present", "Frozen plan does not bind this request")
        return plan

    def chain(root):
        for number, skill in enumerate(request["chain"], 1):
            register_checkpoint(root, method, "h0", number, skill, provenance=request["provenance"])

    if operation == "dryrun":  # zero calls: a scratch plan beside the output, never the cell's run directory
        scratch = safe_path(output).parent / (safe_path(output).stem + "-plan")
        require(not scratch.exists() and not safe_path(output).exists(), "Smoke target already exists")
        frozen = bound(freeze_plan(config, scratch))
        sequence.check_client_service(request["repo"], config["model"], scratch / "api", request["service"])
        chain(scratch)
        loaded = bound(load_plan(scratch))
        require(load_checkpoint(scratch, method, "h0", stage, loaded)["skill_text"]
                == (request["chain"][-1] if request["chain"] else ""), "Smoke plan does not bind the policy")
        tasks = [t for t in loaded["tasks"] if t["benchmark"] == benchmark]
        value = seal({"plan_hash": frozen["record_hash"], "benchmark": benchmark, "policy": request["policy"],
                      "tasks": len(tasks), "positions": len(tasks) * loaded["repeats"], "model_calls": 0})
        write_json(output, value)
        return value
    if operation == "generate":  # model calls only; scoring is a separate operation
        require(not new.exists() and not safe_path(output).exists(), "Never silently retry a begun evaluation")
        bound(freeze_plan(config, new))
        sequence.check_client_service(request["repo"], config["model"], new / "api", request["service"])
        chain(new)
        runner.generate(new, method=method, history="h0", stage=stage, benchmark=benchmark,
                        repo=request["repo"], workers=request["workers"])
        sequence.require_eval_handoff(new)
        value = seal({"plan_hash": bound(load_plan(new))["record_hash"], "benchmark": benchmark,
                      "policy": request["policy"],
                      "predictions": len(list((new / "predictions").glob("*/prediction.json")))})
        write_json(output, value)
        return value
    if operation == "score":  # native scoring of closed predictions; no model calls
        require(new.exists() and not safe_path(output).exists(), "Scoring needs a generated, unscored cell")
        bound(load_plan(new))
        runner.score_checkpoint(new, method=method, history="h0", stage=stage, benchmark=benchmark)
    plan = bound(load_plan(new))
    for number, skill in enumerate(request["chain"], 1):
        checkpoint = load_checkpoint(new, method, "h0", number, plan)
        require(checkpoint["skill_text"] == skill and checkpoint["provenance"] == request["provenance"],
                "Policy checkpoint chain changed")
    sequence.verify_service(new, request["service"])
    sequence.require_eval_handoff(new)
    accounting = runner.report(new)
    rows = [read_json(p, sealed=True) for p in sorted((new / "host_only/scores").glob("*.json"))]
    expected = len([t for t in plan["tasks"] if t["benchmark"] == benchmark]) * plan["repeats"]
    require(len(rows) == expected and accounting["run_accounting"]["unclosed_calls"] == 0,
            "Incomplete test evaluation")
    result = seal({"root": str(new), "plan_hash": plan["record_hash"], "benchmark": benchmark,
                   "policy": request["policy"], "positions": expected,
                   "counts": dict(Counter(r["status"] for r in rows)), "costs": accounting["run_accounting"],
                   "rows": [{k: r[k] for k in ("task_id", "family_id", "repeat", "status", "record_hash")} for r in rows]})
    write_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "smoke", "run", "worker"))
    parser.add_argument("--output")
    parser.add_argument("--study")
    parser.add_argument("--split")
    parser.add_argument("--repo")
    parser.add_argument("--bcb-final")
    parser.add_argument("--sheet-final")
    parser.add_argument("--kor-final")
    parser.add_argument("--searchqa-test")
    parser.add_argument("--alfworld-test")
    parser.add_argument("--alfworld-root")
    parser.add_argument("--operation")
    parser.add_argument("--request")
    args = parser.parse_args()
    if args.command == "worker":
        worker(args.operation, args.request, args.output)
    elif args.command == "prepare":
        value = prepare(args.study, args.split, args.output, args.repo, bcb_final=args.bcb_final,
                        sheet_final=args.sheet_final, kor_final=args.kor_final, searchqa_test=args.searchqa_test,
                        alfworld_test=args.alfworld_test, alfworld_root=args.alfworld_root)
        print(json.dumps({"record_hash": value["record_hash"], "policies": sorted(value["policies"]),
                          "cells": len(value["cells"])}))
    elif args.command == "smoke":
        checked = smoke(args.output)
        print(json.dumps({"cells": len(checked), "positions": {k: v["positions"] for k, v in checked.items()}}))
    else:
        value = run(args.output)
        print(json.dumps({"record_hash": value["record_hash"]}))


if __name__ == "__main__":
    sys.exit(main())
