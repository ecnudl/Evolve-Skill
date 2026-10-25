"""Read-only, zero-call route-B v2.3 audit (owner request 2026-10-25, deliverable 3; Amendment 1).

Reproduce stored v2.1/v2.2 acceptance decisions, then partition all arms under T1 using stored request hashes and
enabled procedure versions. Report actual and hypothetical dispatch by arm, zero-dispatch identical_all items and
the substituted decision; count T2's identical training items; compare every permitted SpreadsheetBench reply with the two
E5 variants. No procedure, program, sandbox, model client or scorer is executed. Missing records and faults refuse
reuse; reported savings are consequently a conservative lower bound. Counterfactual scores substitute observations,
not new evidence of model quality, and retained timestamps cannot predict a shorter run's timing.

Only sealed rounds, decisions, cells, trajectories, packages, procedures and training unit records are read. Paths
containing final|test|holdout|held_out|verifier_calibration|reserve are excluded before opening (including selftest),
as are repository data/, symlinks, private caches and hidden directories. A remote /data/<run> is an allowed run
root; repository data/ is not. Output must be outside the input root. Use ``python -m scripts.execskill_v23_replay
RUN_ROOT --output REPORT.json``; the sibling REPORT.txt contains the short summary. Existing outputs are refused.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from skillopt.coevo5.calls import _request_hash
from skillopt.continual_eval.code_delivery import extract_python as extract_v1
from skillopt.continual_eval.core import require
from skillopt.execskill import acceptance, reuse
from skillopt.execskill.cells import cell_id
from skillopt.execskill.code_delivery import extract_python as extract_v2
from skillopt.execskill.protocol import RECORD_HASH, SLICES, verified
from skillopt.validator_pilot.api import digest

VERSION = "execskill-v23-offline-replay-v2"
FORBIDDEN = re.compile(r"final|test|holdout|held_out|verifier_calibration|reserve", re.I)
REPOSITORY_DATA = Path(__file__).resolve().parents[1] / "data"
PRIVATE = {"artifacts", "host_only", "calls", "cache", "caches", "api_cache", "private", "runtime", "data",
           "scorer_artifacts", "__pycache__"}
OLD_EVIDENCE = {"main_v2_1_real_run", "main_v2_2_real_run", "engineering_fixture", "smoke"}
ATTEMPT = re.compile(r"attempt-[1-9][0-9]*")
TRAIN = re.compile(r"train-r[1-9][0-9]*")
SHA = re.compile(r"[0-9a-f]{64}")
CELL_ID = re.compile(r"[0-9a-f]{32}")


class Inputs:
    """A bounded artifact reader. All opens use ``read``; discovery never follows a link or excluded directory."""

    def __init__(self, root):
        given = Path(root).absolute()
        require(not FORBIDDEN.search(str(given)), "Refused input path: forbidden split name")
        require(not any(p.is_symlink() for p in (given, *given.parents)), "Refused symlink input root")
        self.root = given.resolve()
        require(not self.root.is_relative_to(REPOSITORY_DATA), "Repository data/ is never an input")
        require(self.root.is_dir(), "The run root is an existing directory")
        self.excluded = []
        self.training_attempts = set()
        self.paths = self._discover()
        self.allowed = frozenset(self.paths)
        self._cache = {}

    def checked(self, path):
        path = Path(path).absolute()
        require(path.is_relative_to(self.root), "An input must stay inside the run root")
        require(not FORBIDDEN.search(str(path)), "Refused input path: forbidden split name")
        require(not any(p.is_symlink() for p in (path, *path.parents)), "Refused symlink input")
        require(path.resolve().is_relative_to(self.root), "An input resolves outside the run root")
        require(not path.resolve().is_relative_to(REPOSITORY_DATA), "Repository data/ is never an input")
        return path

    def _discover(self):
        found = []
        for folder, directories, files in os.walk(self.root, followlinks=False):
            base = Path(folder)
            if ATTEMPT.fullmatch(base.name) and TRAIN.fullmatch(base.parent.name):
                self.training_attempts.add(base)
            kept = []
            for name in sorted(directories):
                child = base / name
                if FORBIDDEN.search(name) or name.startswith(".") or name in PRIVATE or child.is_symlink():
                    self.excluded.append(str(child.relative_to(self.root)))
                else:
                    kept.append(name)
            directories[:] = kept
            for name in sorted(files):
                child = base / name
                if FORBIDDEN.search(name) or name.startswith(".") or child.is_symlink():
                    self.excluded.append(str(child.relative_to(self.root)))
                    continue
                if (name == "sealed.json" and base.name == "accept"
                        or name == "decision.json" and base.name == "decision" and base.parent.parent.name == "accept"
                        or name == "unit.json" and TRAIN.fullmatch(base.name)
                        or child.suffix == ".json" and (base.name in {"cells", "trajectories"}
                        and CELL_ID.fullmatch(child.stem) or base.name in {"packages", "procedures"}
                        and SHA.fullmatch(child.stem))):
                    found.append(self.checked(child))
        return sorted(found)

    def read(self, path, kind):
        path = self.checked(path)
        require(path in self.allowed, "Only allowlisted run artifacts may be read")
        if path not in self._cache:
            with path.open(encoding="utf-8") as handle:
                self._cache[path] = json.load(handle)
        return verified(self._cache[path], kind)

    def relative(self, path):
        return str(Path(path).relative_to(self.root))


def _procedures(inputs):
    """Index sealed definitions by content hash; never construct or execute a Procedure."""
    packages, procedures = {}, {}
    for path in inputs.paths:
        if path.parent.name not in {"packages", "procedures"}:
            continue
        kind = "package" if path.parent.name == "packages" else "procedure"
        value = inputs.read(path, kind)
        require(path.stem == value[RECORD_HASH], "A definition filename is its record hash")
        target = packages if kind == "package" else procedures
        target[path.stem] = value
    return packages, procedures


def _unavailable(bench, reason):
    return {"bench": bench, "request_sha256": None, "post_call": [], "faults": [{"kind": reason}]}


def stored_signature(trajectory, packages, procedures, *, cell=None, sealed=None):
    """A conservative T1 signature of stored observations. All recorded faults refuse reuse, including later
    faults: a historic record does not prove a separate zero-call pass was clean. QA bindings are included because
    they can change a second call; SpreadsheetBench includes enabled sheet_feedback versions and placebo content."""
    bench = trajectory["bench"]
    if bench == "alfworld":
        return _unavailable(bench, "alfworld_excluded")
    first = [c for c in trajectory.get("calls", []) if c.get("purpose") == "first"]
    if len(first) != 1:
        return _unavailable(bench, "missing_or_ambiguous_first_request")
    request = first[0]
    require(request.get("request_sha256") == _request_hash(request["system"], request["user"]),
            "A stored first request hash must match its texts")
    route, shell = trajectory.get("route"), trajectory.get("shell") or {}
    if not isinstance(route, dict) or not isinstance(route.get("enabled"), list):
        return _unavailable(bench, "missing_enabled_list")
    faults = list(route.get("faults") or []) + list(shell.get("faults") or []) + list((cell or {}).get("faults") or [])
    enabled, post = route["enabled"], []
    if enabled:
        package = packages.get(trajectory.get("package_sha256"))
        if package is None:
            return _unavailable(bench, "missing_package_definition")
        versions = dict(zip(package["order"], package["procedures"]))
        for pid in enabled:
            procedure = procedures.get(versions.get(pid))
            if procedure is None or procedure["id"] != pid:
                return _unavailable(bench, "missing_procedure_definition")
            hooks = [h for h in procedure["hooks"] if h in (("sheet_feedback", "bindings")
                                                            if bench == "spreadsheetbench" else ("bindings",))]
            if not hooks:
                continue
            entry = {"procedure": procedure[RECORD_HASH], "hooks": hooks,
                     "requests_second_call": procedure["requests_second_call"]}
            arm = trajectory["arm"]
            if arm in ("P_y", "P_i"):
                if sealed is None:
                    return _unavailable(bench, "missing_placebo_post_call_content")
                content = sealed["placebo_y" if arm == "P_y" else "placebo_i"] or {}
                source = (cell or {}).get("cell", {}).get("source_item", trajectory["task_id"])
                sham = (content.get(source) or {}).get("procedures", {}).get(pid)
                if sham is not None:
                    entry["sham_sha256"] = digest({h: sham.get(h) for h in hooks})
            post.append(entry)
    return {"bench": bench, "request_sha256": request["request_sha256"], "post_call": post, "faults": faults,
            "enabled": list(enabled)}


def _same(signatures, bench):
    """One signature only if every registered run proves the same clean request and post-call behavior."""
    if not signatures:
        return _unavailable(bench, "missing_trajectory")
    if any(s["faults"] for s in signatures):
        return _unavailable(bench, "stored_fault_or_incomplete_evidence")
    first = signatures[0]
    if any(s != first for s in signatures[1:]):
        return _unavailable(bench, "requests_or_hooks_differ_across_runs")
    return first


def _acceptance_cells(inputs, unit_root, sealed, decision):
    """Read the decision's exact block provenance; never follow an unguarded path in a stored record."""
    require(decision["sealed"]["record"] == sealed[RECORD_HASH], "The stored decision names this sealed round")
    cells, paths = [], []
    for block, jobs in acceptance.schedule(sealed).items():
        attempt = (decision.get("provenance", {}).get(str(block)) or {}).get("attempt")
        require(type(attempt) is str and ATTEMPT.fullmatch(attempt), "A block names its single stored attempt")
        for job in jobs:
            name = cell_id(sealed["unit"], job["arm"], job["item"], job["run"])
            path = unit_root / attempt / "cells" / (name + ".json")
            cells.append(inputs.read(path, "cell"))
            paths.append(path)
    return cells, paths


def _acceptance(inputs, path, definitions):
    sealed = inputs.read(path, "acceptance-sealed")
    require(sealed["evidence"] in OLD_EVIDENCE and "reuse" not in sealed,
            "Replay requires an original main-v2-1/main-v2-2 round (or a synthetic fixture)")
    out = {"round": inputs.relative(path.parent), "sealed_sha256": sealed[RECORD_HASH],
           "evidence": sealed["evidence"], "bench": sealed["bench"], "attempts": []}
    decisions = [p for p in inputs.paths if p.name == "decision.json" and p.parent.parent.parent == path.parent]
    for decision_path in decisions:
        decision = inputs.read(decision_path, "decision")
        cells, cell_paths = _acceptance_cells(inputs, path.parent, sealed, decision)
        reproduced = acceptance.decide(cells, sealed)
        grouped = defaultdict(list)
        for cell, cell_path in zip(cells, cell_paths):
            trajectory_path = cell_path.parent.parent / "trajectories" / cell_path.name
            signature = (_unavailable(sealed["bench"], "missing_trajectory") if trajectory_path not in inputs.allowed
                         else stored_signature(inputs.read(trajectory_path, "trajectory"), *definitions,
                                               cell=cell, sealed=sealed))
            grouped[(cell["set"], cell["task_id"], cell["arm"])].append(signature)
        signatures = {}
        for (cell_set, item, arm), group in grouped.items():
            signatures.setdefault(cell_set, {}).setdefault(item, {})[arm] = _same(group, sealed["bench"])
        plan = reuse.from_signatures(sealed, signatures)
        hypothetical = acceptance.with_reuse(sealed, plan)
        jobs = {acceptance._job_key(j) for block in acceptance.schedule(hypothetical).values() for j in block}
        retained = [c for c in cells if acceptance._cell_key(c) in jobs]
        what_if = acceptance.decide(retained, hypothetical)
        skipped = Counter(c["arm"] for c in cells if acceptance._cell_key(c) not in jobs)
        actual, dispatched = Counter(c["arm"] for c in cells), Counter(c["arm"] for c in retained)
        identical = plan["identical_all"]
        identical_counts = {cell_set: len(items) for cell_set, items in sorted(identical.items())}
        out["attempts"].append({"decision_file": inputs.relative(decision_path),
                                "stored_decision_sha256": decision[RECORD_HASH],
                                "reproduced": reproduced == decision,
                                "reproduced_sha256": reproduced[RECORD_HASH], "stored_cells": len(cells),
                                "dispatch": {"actual": len(cells), "under_t1": len(retained),
                                             "by_arm": {arm: {"actual": actual[arm], "under_t1": dispatched[arm],
                                                               "avoided": actual[arm] - dispatched[arm]}
                                                        for arm in sorted(actual)}},
                                "identical_all": {"items": sum(identical_counts.values()),
                                                  "by_set": identical_counts,
                                                  "real_astar_items": len(set(identical.get("real", []))
                                                                          & set(sealed["plan"]["astar"]))},
                                "t1_cells_not_dispatched": len(cells) - len(retained),
                                "t1_by_arm": dict(sorted(skipped.items())), "reuse_plan": plan,
                                "what_if_decision": what_if})
    if not decisions:
        out["status"] = "sealed_without_stored_decision"
    return out


def _training(inputs, trajectory_values, definitions):
    groups = defaultdict(list)
    for attempt in inputs.training_attempts:
        groups[attempt]
    for path in inputs.paths:
        if path.name == "unit.json":
            unit = inputs.read(path, "unit")
            require(type(unit.get("attempt")) is str and ATTEMPT.fullmatch(unit["attempt"]),
                    "A training unit names its completed attempt")
            groups[path.parent / unit["attempt"]]  # completed zero-dispatch rounds still have an output row
    for path, trajectory in trajectory_values:
        if TRAIN.fullmatch(path.parent.parent.parent.name):
            groups[path.parent.parent].append((path, trajectory))
    out = []
    for attempt, found in sorted(groups.items()):
        pairs = defaultdict(lambda: defaultdict(dict))
        for path, trajectory in found:
            if trajectory["arm"] not in ("S", "S'"):
                continue
            cell_path = attempt / "cells" / path.name
            cell = inputs.read(cell_path, "cell") if cell_path in inputs.allowed else None
            pairs[trajectory["task_id"]][trajectory["arm"]][trajectory["run"]] = (
                stored_signature(trajectory, *definitions, cell=cell), trajectory)
        identical, unknown, cells_saved = [], [], 0
        for item, arms in sorted(pairs.items()):
            if set(arms) != {"S", "S'"} or set(arms["S"]) != set(arms["S'"]):
                unknown.append(item)
                continue
            bench = next(iter(arms["S"].values()))[1]["bench"]
            runs = SLICES[bench]["run"][1] if item.startswith(bench + "/") else 1
            if set(arms["S"]) != set(range(runs)):
                unknown.append(item)
                continue
            left = _same([pair[0] for pair in arms["S"].values()], bench)
            right = _same([pair[0] for pair in arms["S'"].values()], bench)
            if left["faults"] or right["faults"]:
                unknown.append(item)
                continue
            differs = any(arms["S"][run][1]["route"]["enabled"] != arms["S'"][run][1]["route"]["enabled"]
                          for run in arms["S"])
            if differs and reuse.interchangeable(left, right, bench=bench):
                identical.append(item)
                cells_saved += len(arms["S"]) + len(arms["S'"])
        unit_path = attempt.parent / "unit.json"
        unit = inputs.read(unit_path, "unit") if unit_path in inputs.allowed else None
        result = unit["result"] if unit and unit.get("attempt") == attempt.name else {}
        expected = result.get("differs")
        out.append({"round": inputs.relative(attempt.parent), "attempt": attempt.name,
                    "authoritative_completed_attempt": bool(result), "recorded_differs": expected,
                    "observed_items": len(pairs), "unobserved_items": max(0, expected - len(pairs))
                    if isinstance(expected, int) else None,
                    "t2_items_skipped": len(identical), "identical": identical,
                    "t2_cells_not_dispatched": cells_saved, "unproven_items": unknown})
    return out


def _extract(trajectory_values, inputs):
    variants = {"refuse": {"by_arm": {}, "needs_rescoring": []}, "last": {"by_arm": {}, "needs_rescoring": []}}
    for path, trajectory in trajectory_values:
        if trajectory["bench"] != "spreadsheetbench":
            continue
        replies, calls = trajectory.get("replies"), trajectory.get("calls")
        require(isinstance(replies, list) and isinstance(calls, list) and len(replies) == len(calls)
                and all(isinstance(call, dict) for call in calls),
                "Stored SpreadsheetBench trajectory requires one call per reply: " + inputs.relative(path))
        for index, reply in enumerate(replies):
            if type(reply) is not str:
                continue
            old = extract_v1(reply)
            for multiple, result in variants.items():
                new = extract_v2(reply, multiple=multiple)
                counts = result["by_arm"].setdefault(trajectory["arm"], Counter())
                counts["replies"] += 1
                counts["v1_available"] += old["status"] == "available"
                counts["v2_available"] += new["status"] == "available"
                changed = (old["status"], old.get("code_sha256")) != (new["status"], new.get("code_sha256"))
                counts["changed_extraction_outcomes"] += changed
                counts["changed_reason_or_kind"] += (old.get("reason"), old.get("candidate_kind"), old.get("kinds", [])) != (
                    new.get("reason"), new.get("candidate_kind"), new.get("kinds", []))
                counts["v1_reason:" + old["reason"]] += 1
                counts["v2_reason:" + new["reason"]] += 1
                for kind in new.get("kinds", []):
                    counts["v2_kind:" + kind] += 1
                if changed:
                    call = calls[index]
                    result["needs_rescoring"].append({"trajectory": inputs.relative(path), "cell": trajectory["cell"],
                        "arm": trajectory["arm"], "item": trajectory["task_id"], "run": trajectory["run"],
                        "reply_index": index, "purpose": call.get("purpose"),
                        "delivery": (call.get("receipt") or {}).get("delivery"),
                        "v1": {k: old.get(k) for k in ("status", "reason", "candidate_kind", "code_sha256")},
                        "v2": {k: new.get(k) for k in ("status", "reason", "candidate_kind", "code_sha256", "kinds")}})
    for result in variants.values():
        result["by_arm"] = {a: dict(sorted(c.items())) for a, c in sorted(result["by_arm"].items())}
        result["changed_cells"] = len({r["trajectory"] for r in result["needs_rescoring"]})
    return variants


def replay(root):
    """Return a JSON-safe audit without changing the root or running any external code."""
    inputs = Inputs(root)
    definitions = _procedures(inputs)
    trajectories = [(p, inputs.read(p, "trajectory")) for p in inputs.paths if p.parent.name == "trajectories"]
    acceptance_rounds = [_acceptance(inputs, p, definitions) for p in inputs.paths if p.name == "sealed.json"]
    training = _training(inputs, trajectories, definitions)
    outcomes = _extract(trajectories, inputs)
    attempts = [a for r in acceptance_rounds for a in r["attempts"]]
    return {"version": VERSION, "run_root": str(inputs.root), "model_calls": 0, "program_executions": 0,
            "input_artifacts_read": len(inputs._cache), "excluded_paths": inputs.excluded,
            "acceptance": acceptance_rounds, "training": training, "extraction": outcomes,
            "totals": {"stored_decisions": len(attempts), "decisions_reproduced": sum(a["reproduced"] for a in attempts),
                       "actual_dispatched_cells": sum(a["dispatch"]["actual"] for a in attempts),
                       "t1_dispatched_cells": sum(a["dispatch"]["under_t1"] for a in attempts),
                       "identical_all_items": sum(a["identical_all"]["items"] for a in attempts),
                       "identical_all_real_astar_items": sum(a["identical_all"]["real_astar_items"] for a in attempts),
                       "t1_cells_not_dispatched": sum(a["t1_cells_not_dispatched"] for a in attempts),
                       "t2_items_skipped": sum(a["t2_items_skipped"] for a in training),
                       "t2_cells_not_dispatched": sum(a["t2_cells_not_dispatched"] for a in training)},
            "limitations": ["Historical replay and token-saving opportunity counts, not independent method-effect evidence.",
                "T1/T2 require complete identical request hashes and enabled post-call versions across stored runs; missing evidence or any recorded fault refuses reuse (conservative lower bound).",
                "T1 what-if retains historical dispatch/finish timestamps; J5 timing is descriptive of retained observations, not a prediction of a shorter run.",
                "T1 partitions all arms; identical_all counts items left with no dispatch after independent C/S_dup instruments. These items remain answered with exact zero differences and unchanged whole-batch denominators.",
                "Exact-zero substitutions remove independent-response noise from identical requests; paired-test p-values can be smaller than under historical dispatch and are counterfactual, not new model evidence.",
                "Savings count cells/items, not tokens or money; no counterfactual response or token cost is known.",
                "All stored acceptance decisions, including earlier attempts, are audited separately; totals across retries are observations, not unique-round budgets.",
                "Forbidden split paths, including selftest, are excluded; no test-split or protected-data files are opened.",
                "Extraction changes are program-delivery changes only. Listed cells require authorized execution/re-scoring before any accuracy claim; delivery failures may remain unscorable."]}


def summary(report):
    totals = report["totals"]
    return ("Decisions reproduced: {decisions_reproduced}/{stored_decisions}.\n"
            "T1 dispatch: {t1_dispatched_cells}/{actual_dispatched_cells} actual cells "
            "({t1_cells_not_dispatched} avoided; {identical_all_items} identical_all items).\n"
            "T2 items skipped: {t2_items_skipped} "
            "({t2_cells_not_dispatched} cells).\n".format(**totals)
            + "Extraction changed cells: refuse=%d; last=%d.\n" % tuple(
                report["extraction"][mode]["changed_cells"] for mode in ("refuse", "last"))
            + "Zero model calls; zero program executions. Savings are conservative historical what-ifs, not accuracy evidence.\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="New JSON report outside the run root; also writes .txt")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    text = output.with_suffix(".txt")
    require(output.suffix == ".json", "The report output has a .json suffix")
    require(not output.is_relative_to(args.run_root.resolve()) and not text.is_relative_to(args.run_root.resolve()),
            "The run root is read-only; choose report output outside it")
    require(not output.exists() and not text.exists(), "Replay outputs are new files")
    report = replay(args.run_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    with text.open("x", encoding="utf-8") as handle:
        handle.write(summary(report))
    print(summary(report), end="")
    return 0 if report["totals"]["stored_decisions"] == report["totals"]["decisions_reproduced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
