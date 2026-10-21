"""The run's report (registration §12; v2: delta §9): the main tables, the registered readings, every stage's update
and the examiner's description, read from the sealed records of the chains that are complete or terminated -- until then a
chain's test scores stay sealed (§0, ``evaluation.unseal``). A chain that ended early reports its completed evaluations
(marked "链未完成"); every reading that needs one of its missing units is "not assessable" and nothing replaces it
(§13.4). Zero model calls; it writes nothing into the run.

Main table (§12.2): per chain, stages 0-5 by bench, "correct / total (incomplete, unknown)" on the completion basis
(§10) -- incomplete: the solver did not complete (§5.4 row 5, a failure); unknown: no result, by category -- and the
official basis (known records only) beside it. The macro average is the "known" variant of §12.6, with the "low" and
"high" variants (every unknown record failed / passed) as its range. Beside the readings (§2.1, §2.2, §10, §13.4): each
test panel's denominator with its exclusions; every attempt that was redone or did not complete, with the owner's
decision; the ledger's spending by scope, every raised cap (a protocol deviation), halt, breach and refusal; and per
stage the labelled items available and used, the generated items, the solver cells, the GLM-5.3 calls and tokens.
v2 (delta §9) also describes, per learning stage, the gate's funnel (the rules entered, past the screen, past the
confirmation, accepted) and the distinct check-half items each diagnosis code failed on (a rule needs 4).
v3 (delta §1, §7, §9): the deepseek family's readings (I-ds primary, E-ds secondary, NoSkill-ds the reference); the
funnel reads the self-test's plan and counts its outcomes; an ALFWorld stage whose every proposal lacked support is
"untestable" (too few check-half trigger items), never "nothing to learn"; the deepseek solver's tokens per scope and
per step, beside GLM-5.3's.
"""
from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from skillopt.continual_eval.core import read_json, require, safe_path

from . import budget as budgets
from . import chain as chains
from . import evaluation, qualify, readout, step
from .budget import OVERALL, chain_scope, deepseek_scope, step_scope
from .protocol import BOOTSTRAP_RESAMPLES, MIN_TRIGGER, ORDER, POOLS, SHARED_STAGE0, TEST_SIZES, VERSION
from .units import CHAINS

INCOMPLETE = "noncompletion"
UNKNOWN_TOKENS = ("unknown", "unknown_artifact")
PLACEMENTS = ("local", "similar")
NAMES = {"searchqa": "SearchQA", "officeqa": "OfficeQA", "livemath": "LiveMath", "spreadsheetbench": "SpreadsheetBench",
         "alfworld": "ALFWorld"}
STATES = {"complete": "完成", "terminated": "链未完成（已终止）", None: "未结束（成绩仍封存）"}
ACTIONS = {"selected_update": "更新", "completed_no_update": "学完、未改", "pending_carry_parent": "自己的规则停下、沿用上一步"}
VERDICTS = {"not_worse": "不差于", "worse": "差于", "uncertain": "不确定", "not_tested": "未检验（前一个不成立）"}
CELL_KINDS = {"self": "自身", "forward": "前向相似", "backward": "后向相似", "rest": "其余"}
LEARNING_UNITS = ("train", "prepare", "selftest", "screen", "confirm", "composite", "merge")
REWRITES = {"rewritten": "改了", "kept": "原样", "rewrite_failed": "失败"}


@dataclass(frozen=True)
class Run:
    """What the report reads of a run: its id (the launch manifest's hash) and its directory."""

    run: str
    root: Path

    @property
    def shared(self):
        return self.root / "shared"


def of_manifest(path):
    """(the sealed launch manifest, its ``Run``): read only -- no ledger, slot or client is set up."""
    value = read_json(path, sealed=True)
    require(value.get("version") == VERSION + "-manifest", "Not a coevo5 manifest")
    return value, Run(value["record_hash"], safe_path(value["root"]))


def _unit_name(key):
    return "%s/s%d/evaluation/%s" % key


def ended(setting, name):
    """"complete", "terminated" or None for a chain of this run."""
    return chains._terminal(chains.chain_root(setting, name), {"run": setting.run, "chain": name})


def load(setting):
    """(units, states): {(chain, stage, bench): {"source", "cells"}} of every ended chain's completed evaluation
    units, and {chain: "complete" | "terminated" | None}."""
    units, states = {}, {}
    for name in readout.CHAIN_NAMES:
        states[name] = ended(setting, name)
        if states[name] is None:
            continue
        roots = {(name, s, b): chains.unit_root(setting, name, s, b) for s in readout.STAGES for b in ORDER}
        done = {key: root for key, root in roots.items() if (root / "unit.json").exists()}
        found = evaluation.unseal(chains.chain_root(setting, name), name, list(done.values()), run=setting.run,
                                  detail=True)
        units.update({key: found[_unit_name(key)] for key in done})
    return units, states


def panels(setting, units):
    """{bench: readout.Panel} of the test items every unit of the bench holds; OfficeQA items are grouped by their
    source files, as the test registry names them (§12.6)."""
    out = {}
    for bench in ORDER:
        held = {frozenset(unit["cells"]) for key, unit in units.items() if key[2] == bench}
        if not held:
            continue
        require(len(held) == 1, "The units of %s hold different test items" % bench)
        items, groups = sorted(held.pop()), None
        if bench == "officeqa":
            entry = read_json(safe_path(setting.shared) / "test" / "officeqa.json", sealed=True)["entry"]
            require(entry["run"] == setting.run and set(items) <= set(entry["source_files"]),
                    "The test registry of another run")
            groups = {item: entry["source_files"][item] for item in items}
        out[bench] = readout.panel(items, groups)
    return out


def table(units, name):
    """§12.2 of one chain: {stage: {bench: counts}} of its completed units; ``reused``: the unit whose records a
    reused or shared unit stands for."""
    out = {}
    for key, unit in units.items():
        if key[0] != name:
            continue
        cells = list(unit["cells"].values())
        out.setdefault(key[1], {})[key[2]] = {
            "correct": sum(c["token"] == "pass" for c in cells), "total": len(cells),
            "incomplete": sum(c["kind"] == INCOMPLETE for c in cells),
            "unknown": sum(c["token"] in UNKNOWN_TOKENS for c in cells),
            "unknown_kinds": dict(Counter(c["kind"] for c in cells if c["token"] in UNKNOWN_TOKENS)),
            "official_pass": sum(c["official"] == "pass" for c in cells),
            "official_known": sum(c["official"] in ("pass", "fail") for c in cells),
            "reused": None if unit["source"] == _unit_name(key) else unit["source"]}
    return {stage: out[stage] for stage in sorted(out)}


def _record(setting, path):
    record = read_json(path, sealed=True)
    require(record["run"] == setting.run, "A unit of another run")
    return record


def updates(setting, states):
    """{chain: {stage: ...}} of every ended chain: the rules the method accepted, by placement (its merge unit); a
    baseline's action (its learning unit)."""
    out = {}
    for name, state in states.items():
        if state is None:
            continue
        baseline = CHAINS[name]["caps"] == "baseline"
        for stage in range(1, len(ORDER) + 1):
            path = chains.chain_root(setting, name) / ("s%d" % stage) / ("learning" if baseline else "merge") / "unit.json"
            if not path.exists():
                continue
            result = _record(setting, path)["result"]
            out.setdefault(name, {})[stage] = (
                {"changed": result["action"] == "selected_update", "action": result["action"],
                 "reason": result["reason"]} if baseline
                else {p: sum(a["placement"] == p for a in result["accepted"]) for p in PLACEMENTS})
    return out


def _revision(summary, attempt):
    """The rubric revision of one stage (§6): its result and, once a candidate was judged, the selection panel's size
    beside the balanced accuracy, the correct and the invalid verdicts before and after ("挑选用")."""
    if summary is None:
        return None
    path = attempt / "revision.json"
    panel = read_json(path).get("panel") if path.exists() else None
    return {**summary, "panel": None if panel is None else len(panel)}


def _research(path):
    """A prepare unit's research checks: the verify requests dispatched and found, each claimed finding's verbatim
    quote check, and every rewrite attempted (rewritten, kept unchanged, or failed) with the rule before and after."""
    if not path.exists():
        return None
    researched = read_json(path)
    requests = [q for r in researched for q in r["questions"] if "log" in q]
    claimed = [e for q in requests for e in q["log"] if (e.get("conclusion") or {}).get("status") == "found"]
    return {"rules": len(researched), "requests": len(requests), "found": sum(q["status"] == "found" for q in requests),
            "claimed": len(claimed), "verbatim": sum("void" not in e for e in claimed),
            "rewrites": [{"rule": r["id"], "status": r["rewrite"], "before": r["original"],
                          "after": r.get("text", r["original"])} for r in researched if r.get("rewrite")]}


def _gate(setting, root, rules):
    """v2 §9: the stage's rules that entered the gate, passed its screen and its confirmation (some arm), and were
    accepted; None for a round that never ran."""
    out = {"entered": sum(r["status"] == "supported" for r in rules)}
    for name in ("screen", "confirm"):
        path = root / name / "unit.json"
        out[name] = len({arm.split(":")[0] for arm, verdict in _record(setting, path)["result"]["verdicts"].items()
                         if verdict["status"] == "pass"}) if path.exists() else None
    path = root / "merge" / "unit.json"
    out["accepted"] = len(_record(setting, path)["result"]["accepted"]) if path.exists() else None
    return out


def _support(setting, root, record):
    """v2 §9: {code: the distinct check-half items its diagnosed failures fell on} of the stage, and how many codes
    reach the 4 trigger items a rule needs (§5.7); None without the diagnoses."""
    path, trained = root / "prepare" / record["attempt"] / "diagnoses.json", root / "train" / "unit.json"
    if not path.exists() or not trained.exists():
        return None
    check = set(record["result"]["halves"]["check"])
    item_of = {cid: item for item, ids in _record(setting, trained)["result"]["cells"].items() for cid in ids}
    codes = {}
    for key, value in read_json(path).items():
        if item_of.get(key) in check:
            codes.setdefault(value["code"], set()).add(item_of[key])
    counts = {code: len(items) for code, items in sorted(codes.items())}
    return {"codes": counts, "reaching": sum(n >= MIN_TRIGGER for n in counts.values())}


def _plan(setting, chain_root, stage):
    """v3 §7: the rules of the stage as its gate read them (the self-test's plan when it ran), or None."""
    path = step.plan_path(chain_root, stage)
    return _record(setting, path)["result"] if path.exists() else None


def untestable(bench, rules):
    """v3 §1: an ALFWorld stage whose every proposal lacked support (fewer than 4 check-half trigger items) cannot
    test its proposals -- read "untestable", never "nothing to learn" or "at the ceiling"."""
    return bench == "alfworld" and bool(rules) and all(r["status"] == "insufficient_support" for r in rules)


def examiner(setting, states):
    """§12.7, description only, of every ended method chain: per stage the rubric revision, the fate of each proposed
    rule, the forward panels and the research checks; v2: the gate's funnel and the support of each code; v3: the
    fates after the self-test, its counts, and whether an ALFWorld stage was untestable."""
    out = {}
    for name, state in states.items():
        if state is None or CHAINS[name]["caps"] == "baseline":
            continue
        for stage in range(1, len(ORDER) + 1):
            path = chains.chain_root(setting, name) / ("s%d" % stage) / "prepare" / "unit.json"
            if not path.exists():
                continue
            record = _record(setting, path)
            result, attempt = record["result"], path.parent / record["attempt"]
            plan = _plan(setting, chains.chain_root(setting, name), stage)
            rules = plan.get("rules", [])
            out.setdefault(name, {})[stage] = {
                "status": result.get("status"), "revision": _revision(result.get("revision"), attempt),
                "rules": dict(Counter(r["status"] for r in rules)), "selftest": step.selftest_counts(plan),
                "untestable": untestable(ORDER[stage - 1], result.get("rules", [])),
                "gate": _gate(setting, path.parent.parent, rules),
                "support": _support(setting, path.parent.parent, record),
                "forward": [{"rule": r["id"], "target": target, "status": panel["status"],
                             "generated": panel["counts"]["generated"], "valid": panel["counts"]["valid"]}
                            for r in rules for target, panel in sorted(r.get("forward", {}).items())],
                "research": _research(attempt / "research.json")}
    return out


def test_panels(setting):
    """§2.1, §10: each bench's test panel as the run's registry names it -- its size beside the registered one, the
    OfficeQA items excluded without pages, and SpreadsheetBench's test-side qualification (qualified, and the
    exclusions by reason). Counts only."""
    base = safe_path(setting.shared) / "test"
    out = {}
    for bench in ORDER:
        path = base / ("%s.json" % bench)
        if not path.exists():
            continue
        entry = read_json(path, sealed=True)["entry"]
        require(entry["run"] == setting.run, "The test registry of another run")
        out[bench] = {"registered": TEST_SIZES[bench], "tasks": len(entry["tasks"]),
                      "excluded_without_pages": len(entry["excluded_without_pages"])}
        pointer = base / (evaluation.SHEET_QUALIFICATION + ".json")
        if bench == "spreadsheetbench" and pointer.exists():
            link = read_json(pointer, sealed=True)
            record = qualify.load(base / evaluation.SHEET_QUALIFICATION / link["attempt"] / "qualification.json")
            require(record["record_hash"] == link["qualification_hash"], "The test qualification changed")
            out[bench]["qualification"] = qualify.summary(record)
    return out


def spending(setting):
    """The run's GLM-5.3 ledger, read only (its event log replayed in memory; a torn last line, a change never
    acknowledged, is left out): per scope its cap as declared and in force, the tokens settled and still open and the
    calls reserved; every raised cap (a protocol deviation, with its amount and reason), halt, resume, breach and
    refusal (§13.4)."""
    path = safe_path(setting.shared) / "ledger" / "events.jsonl"
    if not path.exists():
        return None
    raw = path.read_bytes()
    state, calls = deepcopy(budgets.INITIAL), Counter()
    out = {"raises": [], "halts": [], "resumes": [], "breaches": [], "refusals": [], "orphans": 0}
    for line in raw[:raw.rfind(b"\n") + 1].splitlines():
        event = json.loads(line)
        kind = event["event"]
        if kind == "reserve":
            calls.update(event["scopes"])
        elif kind == "raise":
            out["raises"].append({k: event[k] for k in ("scope", "from", "cap", "deviation")})
        elif kind == "halt":
            out["halts"].append({"reason": event["reason"], "label": event["label"]})
        elif kind == "resume":
            out["resumes"].append(event["decision"])
        elif kind == "settle" and event.get("breach"):
            out["breaches"].append({k: event[k] for k in ("label", "breach", "overrun")})
        elif kind == "refuse":
            out["refusals"].append({"label": event["label"], "exceeded": event.get("exceeded"),
                                    "halted": bool(event.get("halted"))})
        elif kind == "orphan":
            out["orphans"] += 1
        budgets._apply(state, event)
    out["scopes"] = {scope: {"declared": state["declared"].get(scope), "cap": cap,
                             "settled": state["settled"].get(scope, 0),
                             "open": sum(r["amount"] for r in state["open"].values() if scope in r["scopes"]),
                             "calls": calls[scope]} for scope, cap in sorted(state["caps"].items())}
    out["halted"] = state["halted"]
    return out


def _completed(unit_root):
    """The attempt a unit's record names (the test qualification: its pointer), or None."""
    if (unit_root / "unit.json").exists():
        return read_json(unit_root / "unit.json", sealed=True).get("attempt")
    pointer = unit_root.parent / (unit_root.name + ".json")
    if unit_root.name == evaluation.SHEET_QUALIFICATION and pointer.exists():
        return read_json(pointer, sealed=True)["attempt"]
    return None


def redone(setting, states):
    """§13.4: every unit of an ended chain -- and the shared stage 0 and the test-side qualification -- that took more
    than one attempt or did not complete: each attempt's status and the owner's recorded decision. A discarded
    attempt's costs are in the ledger; it enters no reading."""
    roots = [chains.chain_root(setting, name) for name, state in states.items() if state is not None]
    if any(states.get(member) for member in SHARED_STAGE0.get(chains.SHARED, ())):
        roots.append(chains.chain_root(setting, chains.SHARED))
    units = sorted({path.parent for root in roots for pattern in ("s*/*/attempt-*", "s*/evaluation/*/attempt-*")
                    for path in root.glob(pattern) if path.is_dir()})
    units += [safe_path(setting.shared) / "test" / evaluation.SHEET_QUALIFICATION]
    out = []
    for unit_root in units:
        found, done = evaluation.attempts(unit_root) if unit_root.exists() else [], _completed(unit_root)
        if not found or (len(found) == 1 and done == found[0].name):
            continue
        rows = []
        for attempt in found:
            status, recovery = attempt / "status.json", attempt / "recovery.json"
            paused = read_json(status, sealed=True) if status.exists() else None
            rows.append({"attempt": attempt.name,
                         "status": "complete" if attempt.name == done else
                         "%s:%s" % (paused["kind"], paused["reason"]) if paused else "interrupted_or_running",
                         "decision": read_json(recovery) if recovery.exists() else None})
        out.append({"unit": unit_root.relative_to(safe_path(setting.root)).as_posix(), "attempts": rows})
    return out


def available(manifest):
    """§2.2's labelled items available at each stage, from the launch manifest: the bench's training pool
    (SpreadsheetBench: its qualified items) and the regression panels of the benches before it."""
    sizes = {b: sum(POOLS[b]) for b in ORDER}
    sizes["spreadsheetbench"] = manifest["provenance"]["sheet_qualification"]["qualified"]
    return {bench: {"pool": sizes[bench],
                    "regression": sum(len(manifest["regression"][b]["items"]) for b in ORDER[:k])}
            for k, bench in enumerate(ORDER)}


def _items(unit_root):
    """(the items of every cell of every attempt of a unit, the cell count) -- discarded attempts used them too."""
    items, count = set(), 0
    for attempt in evaluation.attempts(unit_root) if unit_root.exists() else []:
        for path in sorted((attempt / "cells").glob("*.json")):
            items.add(read_json(path, sealed=True)["cell"]["task_id"])
            count += 1
    return items, count


def accounting(setting, states, spent, supply=None):
    """§2.2 per ended chain and stage: the labelled items available (``supply``, from the manifest) and used
    (distinct; a baseline: its learning panel), the generated items' labels (forward panels), the learning units'
    solver cells, and the GLM-5.3 calls and tokens charged to the stage's learning and evaluation (every attempt)."""
    out = {}
    for name, state in states.items():
        if state is None or not chains.learns(name):  # v2 §1: the reference evaluates stage 0 only
            continue
        baseline = CHAINS[name]["caps"] == "baseline"
        for stage, bench in enumerate(ORDER, 1):
            root = chains.chain_root(setting, name) / ("s%d" % stage)
            row = {"available": (supply or {}).get(bench)}
            if baseline:
                path = root / "learning" / "unit.json"
                result = _record(setting, path)["result"] if path.exists() else None
                row.update(used=None if result is None else result["train_tasks"] + result["selection_tasks"],
                           generated=0, cells=None)
            else:
                items, cells = set(), 0
                for unit in LEARNING_UNITS:
                    found, count = _items(root / unit)
                    items, cells = items | found, cells + count
                rules = (_plan(setting, chains.chain_root(setting, name), stage) or {}).get("rules", [])
                row.update(used=len({i for i in items if not i.startswith("fwd:")}), cells=cells,
                           generated=sum(len(p["items"]) for r in rules for p in (r.get("forward") or {}).values()))
            for kind in ("learning", "evaluation"):
                for label, scope_name in ((kind, step_scope(name, stage, kind)),
                                          ("deepseek_" + kind, deepseek_scope(name, stage, kind))):
                    scope = ((spent or {}).get("scopes") or {}).get(scope_name)
                    row[label] = None if scope is None else {"calls": scope["calls"],
                                                             "tokens": scope["settled"] + scope["open"]}
            out.setdefault(name, {})[stage] = row
    return out


def build(setting, *, resamples=BOOTSTRAP_RESAMPLES, supply=None):
    """The report of the run, as its JSON (stage keys are strings); ``supply``: ``available`` of its manifest."""
    units, states = load(setting)
    found = panels(setting, units)
    changes = updates(setting, states)
    spent = spending(setting)
    report = {"version": VERSION + "-report", "run": setting.run, "chains": states,
              "tables": {name: table(units, name) for name, state in states.items() if state is not None},
              "updates": changes, "examiner": examiner(setting, states), "readings": None,
              "test_panels": test_panels(setting), "spending": spent, "redone": redone(setting, states),
              "accounting": accounting(setting, states, spent, supply)}
    if set(found) == set(ORDER):  # a bench without any record leaves every macro reading without it (§12.6)
        records = {key: readout.Unit(unit["source"], {i: c["token"] for i, c in unit["cells"].items()})
                   for key, unit in units.items()}
        report["readings"] = readout.registered(readout.Readings(records, found, resamples=resamples), changes)
    return json.loads(json.dumps(report, ensure_ascii=False, allow_nan=False))


# ---------------------------------------------------------------------------------------------------- markdown
def _counts(counts):
    return "%d / %d（%d，%d）" % (counts["correct"], counts["total"], counts["incomplete"], counts["unknown"])


def _available(result):
    return result is not None and result["available"]


def _range(result):
    """A level: the known estimate, with the low and high variants as its range."""
    if not _available(result):
        return "无法评估"
    return "%.1f（%.1f–%.1f）" % tuple(result[v]["estimate"] for v in readout.VARIANTS)


def _interval(result, variant=readout.KNOWN):
    """A difference: the estimate and its two-sided 95% interval."""
    if not _available(result):
        return "无法评估"
    value = result[variant]
    return "%+.1f [%+.1f, %+.1f]" % (value["estimate"], *value["interval95"])


def _bound(result, variant):
    """A §12.8 reading: the estimate, its one-sided 95% lower bound L and its two-sided 95% interval."""
    if not _available(result):
        return "无法评估"
    value = result[variant]
    return "%+.1f（L %+.1f；[%+.1f, %+.1f]）" % (value["estimate"], value["lower90"], *value["interval95"])


def _verdict(value):
    if value is None:
        return "无法评估"
    if value is True or value is False:
        return "成立" if value else "未建立"
    return VERDICTS[value]


def _update(baseline, value):
    if value is None:
        return "—"
    if baseline:
        return ACTIONS[value["action"]] + ("：" + value["reason"] if value["action"] == "pending_carry_parent" else "")
    return "%d / %d" % (value["similar"], value["local"])


def _main(report):
    readings = report["readings"]
    lines = ["## 1 主表（§12.2）", ""]
    for name, rows in report["tables"].items():
        baseline = CHAINS[name]["caps"] == "baseline"
        macro = readings["chains"][name]["macro"] if readings else {}
        changes = report["updates"].get(name, {})
        lines += ["### %s（%s）" % (name, STATES[report["chains"][name]]), "",
                  "| 步 | %s | 宏平均 | %s |" % (" | ".join(NAMES[b] for b in ORDER),
                                                 "学习结果" if baseline else "收下的规则（相似 / 本 bench）"),
                  "|---|" + "---|" * (len(ORDER) + 2)]
        for stage, row in rows.items():
            lines.append("| %s | %s | %s | %s |" % (
                stage, " | ".join(_counts(row[b]) if b in row else "—" for b in ORDER), _range(macro.get(stage)),
                _update(baseline, changes.get(stage)) if stage != "0" else ""))
        lines += ["", "官方口径（只算已知记录：通过 / 已知）："]
        lines += ["- 第 %s 步：" % stage + "；".join("%s %d / %d" % (NAMES[b], row[b]["official_pass"],
                                                               row[b]["official_known"]) for b in ORDER if b in row)
                  for stage, row in rows.items()]
        kinds = ["第 %s 步 %s：%s" % (stage, NAMES[b], "、".join("%s %d" % item for item in sorted(
            row[b]["unknown_kinds"].items()))) for stage, row in rows.items() for b in ORDER
            if b in row and row[b].get("unknown_kinds")]
        if kinds:
            lines += ["", "未知记录的类别：" + "；".join(kinds)]
        lines.append("")
    return lines


def _test_panels(report):
    lines = ["## 0 测试面板与分母（§2.1、§10）", ""]
    if not report["test_panels"]:
        return lines + ["还没有任何测试面板的登记。", ""]
    for bench, row in report["test_panels"].items():
        text = "- %s：登记 %d 题，评测面板 %d 题" % (NAMES[bench], row["registered"], row["tasks"])
        if row["excluded_without_pages"]:
            text += "；缺出处页而排除 %d 题" % row["excluded_without_pages"]
        found = row.get("qualification")
        if found is not None:
            text += "；测试侧资格检查 %d 题中合格 %d 题（分母）" % (found["items"], found["qualified"])
            if found["excluded"]:
                text += "，不合格原因：" + "、".join("%s %d" % item for item in sorted(found["excluded"].items()))
        lines.append(text)
    return lines + [""]


GAIN_LABELS = {
    "learning_gain": "学习增益 M_{0}[5] − M_{0}[0]（第 0 步是空架子；固定架子之上的增量变化，L > 0 才算成立）",
    "exceeds_instructions": "超过指令 M_{0}[5] − M_{0}[0]（第 0 步是五份任务说明指令；L > 0 记“超过”，否则“未建立”）"}
SOURCES = {"ds": "第 3 版登记 §1：deepseek 一族，I-ds 为主", "glm": "第 2 版登记 §9：GLM-5.3 一族，E-glm 为主"}


def _gain_verdict(kind, value):
    return "超过" if kind == "exceeds_instructions" and value is True else _verdict(value)


def _primary(readings):
    primary, status = readings["primary"], readings["primary"]["status"]
    name, moved = primary["chain"], status["stages_with_accepted_rules"]
    return ["## 2 主要读数（%s；第 1 版的 P1–P4 与两条“主张”在第 2 版取消）" % SOURCES[readings["family"]], "",
            "- 方法有没有动（至少 2 步收下过规则）：%s（%s）%s" % (
                _verdict(status["method_moved"]), "%s 未结束" % name if moved is None else "%d 步" % moved,
                "——方法几乎没有更新，读数照报、注明（§12.5）" if status["method_moved"] is False else ""),
            "- %s：%s，%s" % (GAIN_LABELS[primary["kind"]].format(name), _interval(primary["reading"]),
                             _gain_verdict(primary["kind"], status["verdict"])),
            "  - 未知记录全算错 / 全算对：%s / %s" % (_interval(primary["reading"], readout.LOW),
                                              _interval(primary["reading"], readout.HIGH)), ""]


def _transfer(readings):
    name = readings["primary"]["chain"]
    transfer, method = readings["transfer"], readings["chains"][name]
    cells = method["transfer"]
    lines = ["## 3 迁移读数（§12.8，Q 组，%s；估计值、单侧 95%% 下界 L、双侧 95%% 区间）" % name, "",
             "| 读数 | 只用已知 | 不利补全 | 有利补全 | 结论 |", "|---|---|---|---|---|"]
    for key, cell, label in (("Q1", "self", "Q1 自身 G_self（L > 0）"), ("Q2", "similar", "Q2 相似 T_sim（L > 0）"),
                             ("Q3", "rest", "Q3 其余 D_rest（L > −2）")):
        lines.append("| %s | %s | %s |" % (label, " | ".join(_bound(cells[cell], v) for v in readout.VARIANTS),
                                         _verdict(transfer[key])))
    lines += ["", "- 登记的合并迁移判据（Q1、Q2、Q3 都成立；只是类别平均上的判据）：%s"
              % _verdict(transfer["registered_transfer_criterion"]),
              "- 相似位置：%s" % {True: "用过", False: "相似位置未被使用",
                                None: "无法评估（%s 的合入记录不全）" % name}[transfer["similar_placement_used"]],
              "- 只描述：前向相似格的平均 T_fwd %s；后向相似格的平均 T_bwd %s" % (_interval(cells["forward"]),
                                                                      _interval(cells["backward"])), ""]
    kinds = {(s, b): k for k in CELL_KINDS for s, b in readout.transfer_cells()[k]}
    lines += ["每格的变化 ΔA[s][b]（只用已知记录，95% 区间；括号里是格的类别）：", "",
              "| 第 s 步学的 | %s |" % " | ".join(NAMES[b] for b in ORDER), "|---|" + "---|" * len(ORDER)]
    for s, learned in enumerate(ORDER, 1):
        lines.append("| %d %s | %s |" % (s, NAMES[learned], " | ".join(
            "%s（%s）" % (_interval(method["step_change"]["%d/%s" % (s, b)]), CELL_KINDS[kinds[(s, b)]])
            for b in ORDER)))
    lines += ["", "轮到时的提高 G_b 与轮到之前的变化 N_b（并列，只描述）：", "", "| bench | G_b | N_b |", "|---|---|---|"]
    lines += ["| %s | %s | %s |" % (NAMES[b], _interval(method["gain"][b]),
                                    _interval(method["ahead"][b]) if b in method["ahead"] else "—（第一个学）")
              for b in ORDER]
    return lines + [""]


def _secondary(readings):
    secondary, moved = readings["secondary"], readings["updates"]
    names = readout.FAMILIES[readings["family"]]
    method, instructed, reference = names["method"], names["instructed"], names["reference"]
    q, other = secondary["transfer"], secondary["chain"]
    lines = ["## 4 次要读法（%s；不做多重校正）" % SOURCES[readings["family"]], "",
             "- %s：%s，%s" % (GAIN_LABELS[secondary["kind"]].format(other), _interval(secondary["gain"]["reading"]),
                              _gain_verdict(secondary["kind"], secondary["gain"]["verdict"])),
             "- 从只有架子到指令的水平 M_%s[5] − M_%s[0]：%s，%s" % (
                 method, instructed, _interval(secondary["scaffold_reaches_instructions"]["reading"]),
                 _verdict(secondary["scaffold_reaches_instructions"]["verdict"])),
             "- 架子的作用（只描述；含 Skill 非空时后端加的包装文字，是条件对比、不是唯一的因果分配）"
             "M_%s[0] − M_%s[0]：%s" % (method, reference, _interval(secondary["scaffold"])),
             "- %s 的迁移（只描述）：Q1 %s，Q2 %s，Q3 %s" % (other, *(_verdict(q[k]) for k in ("Q1", "Q2", "Q3")))]
    lines.append("- 各链收下规则的步数：" + "；".join(
        "%s %s" % (name, "无记录（未结束）" if value["stages_with_accepted_rules"] is None
                   else "%d 步" % value["stages_with_accepted_rules"]) for name, value in moved.items()))
    lines += ["", "各链的描述（只用已知记录，95% 区间；截断版把每项负数记 0 再平均）：", "",
              "| 链 | F̄ 平均遗忘 | F̄ 截断 | N̄ 轮到之前的迁移 | N̄ 截断 | G_self | T_sim | D_rest |",
              "|---|---|---|---|---|---|---|---|"]
    for name, value in readings["chains"].items():
        if name == readout.FAMILIES[readings["family"]]["reference"]:  # stage 0 only (§1)
            continue
        lines.append("| %s | %s |" % (name, " | ".join(_interval(r) for r in (
            value["mean_forgetting"], value["mean_forgetting_truncated"], value["mean_ahead"],
            value["mean_ahead_truncated"], value["transfer"]["self"], value["transfer"]["similar"],
            value["transfer"]["rest"]))))
    return lines + [""]


def _percent(fraction):
    return "%.1f%%" % (100 * float(Fraction(fraction)))


def _examiner(report):
    lines = ["## 5 考官与查证（§12.7，只描述）", ""]
    for name, stages in report["examiner"].items():
        lines += ["### %s" % name, ""]
        for stage, value in stages.items():
            revision = value["revision"]
            text = "无修订记录" if revision is None else "修订 %s" % revision["status"]
            if revision is not None and "balanced_accuracy" in revision:
                text += "；挑选用：面板 %s 题，平衡准确率 %s → %s，判对 %d → %d，不合法 %d → %d" % (
                    revision["panel"], _percent(revision["balanced_accuracy"]["old"]),
                    _percent(revision["balanced_accuracy"]["new"]), revision["correct"]["old"],
                    revision["correct"]["new"], revision["invalid"]["old"], revision["invalid"]["new"])
            lines.append("- 第 %s 步（%s，%s）：%s" % (stage, NAMES[ORDER[int(stage) - 1]], value["status"], text))
            lines.append("  - 规则的去向：" + ("，".join("%s %d" % item for item in sorted(value["rules"].items()))
                                          or "没有规则"))
            if value.get("untestable"):
                lines.append("  - 可检验的触发题不足，无法检验（每条提案在检验半里同类错题都不到 %d 道；不说成学不到或到顶）"
                             % MIN_TRIGGER)
            tested = value.get("selftest")
            if tested is not None:
                lines.append("  - 自测：%d 条，第 1 轮过 %d 条；修改回复 %s（%s）；第 2 轮过 %d 条" % (
                    tested["tested"], tested["round1_passed"], tested["reply"] or "未发",
                    "，".join("%s %d" % item for item in tested["revisions"].items()) or "无",
                    tested["round2_passed"]))
            gate = value["gate"]
            lines.append("  - 门的漏斗：进门 %d，过初筛 %s，过复核 %s，收下 %s" % (gate["entered"], *(
                "—" if gate[k] is None else gate[k] for k in ("screen", "confirm", "accepted"))))
            support = value["support"]
            if support is not None:
                lines.append("  - 检验半里各代码失败的不同题数（够 %d 道的代码 %d 个）：%s" % (
                    MIN_TRIGGER, support["reaching"],
                    "、".join("%s %d" % item for item in support["codes"].items()) or "没有失败"))
            lines.append("  - 前向题：" + ("；".join("%s → %s：%s，生成 %d、有效 %d" % (
                f["rule"], NAMES[f["target"]], f["status"], f["generated"], f["valid"]) for f in value["forward"])
                                        or "无"))
            research = value["research"]
            if research is None:
                lines.append("  - 查证：无记录")
                continue
            outcomes = Counter(rewrite["status"] for rewrite in research["rewrites"])
            lines.append("  - 查证：%d 条规则，派出 %d 次请求、找到 %d 次；声称找到的结论 %d 个，引用逐字核对通过 %d 个；"
                         "改写尝试 %d 次（%s）" % (
                             research["rules"], research["requests"], research["found"], research["claimed"],
                             research["verbatim"], len(research["rewrites"]),
                             "，".join("%s %d" % (REWRITES[k], outcomes[k]) for k in REWRITES)))
            for rewrite in research["rewrites"]:
                lines += ["    - %s（%s）改写前：%s" % (rewrite["rule"], REWRITES[rewrite["status"]],
                                                  json.dumps(rewrite["before"], ensure_ascii=False)),
                          "      改写后：%s" % json.dumps(rewrite["after"], ensure_ascii=False)]
        lines.append("")
    return lines


def _tokens(value):
    return "—" if value is None else "%d / %s" % (value["calls"], "{:,}".format(value["tokens"]))


def _costs(report):
    lines = ["## 6 花费、偏离与尝试（§13.4、§2.2）", ""]
    spent = report["spending"]
    if spent is None:
        lines += ["账本还没有记录。", ""]
    else:
        scopes = spent["scopes"]
        overall = scopes.get(OVERALL)
        if overall is not None:
            lines.append("- GLM-5.3 总花费（已结算 + 未结清）：{:,} tokens，上限 {:,}（登记 {:,}）".format(
                overall["settled"] + overall["open"], overall["cap"], overall["declared"]))
        lines += ["- %s：{:,} tokens".format(scopes[chain_scope(name)]["settled"] + scopes[chain_scope(name)]["open"])
                  % name for name in readout.CHAIN_NAMES if chain_scope(name) in scopes]
        found = scopes.get(deepseek_scope())
        if found is not None:  # v3 §9: the deepseek solver's own allowance, apart from GLM-5.3's
            lines.append("- deepseek-v4-flash（做题模型）总花费：{:,} tokens，上限 {:,}".format(
                found["settled"] + found["open"], found["cap"]))
            lines += ["  - %s：{:,} tokens，上限 {:,}".format(
                scopes[deepseek_scope(name)]["settled"] + scopes[deepseek_scope(name)]["open"],
                scopes[deepseek_scope(name)]["cap"]) % name
                for name in readout.CHAIN_NAMES if deepseek_scope(name) in scopes]
        lines += ["- 协议偏离（提高上限）：%s 从 {:,} 提到 {:,}，理由：%s".format(r["from"], r["cap"])
                  % (r["scope"], r["deviation"]) for r in spent["raises"]] or ["- 协议偏离（提高上限）：无"]
        lines += ["- 停发 %d 次、负责人恢复 %d 次、预留假设被打破 %d 次、预算拒绝 %d 次、进程结束未回执按整笔结算 %d 次"
                  % (len(spent["halts"]), len(spent["resumes"]), len(spent["breaches"]),
                     sum(1 for r in spent["refusals"] if not r["halted"]), spent["orphans"])]
        lines += ["  - 停发：%s（%s）" % (h["reason"], h["label"]) for h in spent["halts"]]
        lines += ["  - 恢复的决定：%s" % decision for decision in spent["resumes"]]
        lines += ["  - 假设被打破：%s（%s，超出 {:,}）".format(b["overrun"]) % (b["breach"], b["label"])
                  for b in spent["breaches"]]
    lines += ["", "每步的标注与调用（可用标注 = 本 bench 训练池 + 之前各 bench 的回归面板；基线：学习面板；"
              "调用 / tokens 是这一步记到账本上的全部尝试）：", ""]
    for name, stages in report["accounting"].items():
        lines += ["### %s" % name, "", "| 步 | 可用标注 | 用到的不重复标注 | 生成题 | 学习的做题格 | 学习：GLM 调用 / tokens |"
                  " 评测：GLM 调用 / tokens | 学习：deepseek 调用 / tokens | 评测：deepseek 调用 / tokens |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for stage, row in stages.items():
            supply = row["available"]
            lines.append("| %s %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                stage, NAMES[ORDER[int(stage) - 1]],
                "—" if supply is None else "%d + %d" % (supply["pool"], supply["regression"]),
                "—" if row["used"] is None else row["used"], row["generated"],
                "—" if row["cells"] is None else row["cells"], _tokens(row["learning"]), _tokens(row["evaluation"]),
                _tokens(row.get("deepseek_learning")), _tokens(row.get("deepseek_evaluation"))))
        lines.append("")
    lines += ["重做过或没做完的单元（被中断的尝试计入花费、不进任何读数）：" if report["redone"] else
              "重做过或没做完的单元：无", ""]
    for unit in report["redone"]:
        lines.append("- %s：" % unit["unit"] + "；".join(
            "%s %s%s" % (a["attempt"], a["status"], "，负责人决定（%s）：%s" % (a["decision"].get("date"),
                                                                       a["decision"].get("decision"))
                         if a["decision"] else "") for a in unit["attempts"]))
    return lines + [""]


def markdown(report):
    """A readable rendering of the report's JSON (the JSON is the record)."""
    lines = ["# coevo5 运行报告", "", "运行：`%s`。" % report["run"], ""]
    if "code" in report:
        lines += ["代码：%s" % ("与启动清单一致" if report["code"]["matches_manifest"]
                               else "与启动清单不一致（%s）" % report["code"]["detail"]), ""]
    lines += ["各链：" + "；".join("%s %s" % (name, STATES[state]) for name, state in report["chains"].items()) + "。",
              "", "读法：格子是“对的题数 / 总数（未完成数，未知数）”（完成口径：未完成算错，未知不算结果）。宏平均是"
              "五个 bench 的平均（百分点）：先写只用已知记录的值，括号里是把未知全算错、全算对时的值（§12.6）。差值写成"
              "“估计值 [95% 区间]”。", ""]
    lines += _test_panels(report) + _main(report)
    if report["readings"] is None:
        lines += ["## 2 读数", "", "还有 bench 没有任何已解封的评测记录：所有读数都无法评估（§12.6，不删 bench）。", ""]
    else:
        lines += _primary(report["readings"]) + _transfer(report["readings"]) + _secondary(report["readings"])
    return "\n".join(lines + _examiner(report) + _costs(report)).rstrip() + "\n"
