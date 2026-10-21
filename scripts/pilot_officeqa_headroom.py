#!/usr/bin/env python3
"""Headroom pilot for OfficeQA in a ONE-CALL form with the frozen solver -- NOT a method result, NOT a benchmark port.

Question (design memo docs/handoff/benchmark-replacement-pilot-20261013.md, section 6): before OfficeQA replaces a
benchmark in the learning toolchain, does the frozen solver leave room for a Skill there, and does a zero-shot
instruction already take that room?

    zeroshot --study F --repo R --output DIR
    prepare  --study F --repo R --upstream U --id-split S --revision SHA
             --skill name=none --skill name=f:/abs/file ... --output DIR   (zero calls)
    run      --output DIR
    report   --output DIR [--contrast a-b ...]

The task form is NOT the one the SkillOpt paper measured. There the solver searches the Treasury Bulletin text
files with tools over up to 24 turns; this toolchain's solver makes one call. Here the solver receives the question
and the parsed page(s) the question's own source hints point to (the original environment's "oracle parsed pages"
renderer, at most 24,000 characters per page and 80,000 in all) and returns a short answer: reading and
calculation, no retrieval. Numbers are therefore not comparable with the paper's.

Data discipline. Only the items of the paper's TRAIN and VALIDATION parts (data/officeqa_id_split) are read out of
the question file; its 172 test items are never materialised. The paper's checkpoint Skill was learned and selected
on exactly these items, so its arm is an optimistic reference, not a clean measurement. Scoring is the original
environment's normalised exact match on the text inside the LAST answer tag (lower case, commas removed, most
punctuation removed, unit words removed; no numeric tolerance); a delivered reply without an answer tag is a wrong
answer and is counted as ``invalid_format``.

Everything about calls, margins, intents, per-attempt costs and "nothing is resumed" is the reviewed machinery of
scripts/pilot_livemath_headroom.py, imported from there.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import generate_zero_shot_skill as zero  # noqa: E402
from scripts import pilot_livemath_headroom as base  # noqa: E402
from scripts import run_fivebench_g_stage as tool  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json  # noqa: E402

VERSION = "officeqa-headroom-pilot-v1"
KIND = "officeqa-headroom-pilot-solver"
PARTS = ("train", "val")  # of the paper's split; its test part is never read out
CONTRACT = "\nReturn the concise final answer inside <answer>...</answer>."
EVIDENCE_NOTE = "Treat it as the document evidence for this question."
TASK_CARD = (
    "Task kind: questions about U.S. Treasury Bulletin documents (the OfficeQA benchmark, in a one-call form). "
    "Answering needs finding the right values in the supplied document pages (running text and tables) and often a "
    "calculation with them.\n"
    "Input the solver receives: a JSON object with two fields -- \"question\" and \"context\" (the parsed text of "
    "the bulletin page or pages the question refers to; tables are rendered as text; a long page may be cut).\n"
    "Fixed instructions the solver always receives: \"Solve the supplied task using only the supplied public "
    "information.\" and \"Return the concise final answer inside <answer>...</answer>.\"\n"
    "Scoring (public metric): the text inside the last <answer>...</answer> is compared with the reference answer "
    "by exact match after normalization (lower case; commas removed; punctuation removed except digits, '.', '-' "
    "and '%'; the words million, billion, dollar(s) and nominal removed; whitespace collapsed). There is no "
    "numeric tolerance. A reply without such a tag counts as wrong. Anything outside the tag is ignored.")
IMPLEMENTATION = (*base.IMPLEMENTATION, "scripts/pilot_livemath_headroom.py", "skillopt/envs/officeqa/evaluator.py",
                  "skillopt/envs/officeqa/tool_runtime.py")


def system_prompt(skill):
    """The system message of the toolchain's ``solve`` (the SearchQA output-contract line)."""
    system = "Solve the supplied task using only the supplied public information."
    if skill.strip():
        system += "\n\nFrozen skill guidance (use only where applicable):\n" + skill
    return system + CONTRACT


def answer(text):
    """The text inside the LAST answer tag (stripped), or None when there is no tag or it is empty."""
    found = re.findall(r"<answer>(.*?)</answer>", text, re.DOTALL | re.IGNORECASE)
    return (found[-1].strip() or None) if found else None


def draw(upstream, id_split):
    """(items, dropped ids, hashes of the page files used). An item is {"id", "meta", "public": {question,
    context}, "private": {answer}}; an item whose source hints resolve to no parsed page is dropped and listed."""
    from skillopt.envs.officeqa.tool_runtime import (_iter_oracle_refs, _locate_parsed_json,
                                                     build_oracle_parsed_pages_context)

    root = safe_path(upstream)
    with (root / "officeqa_full.csv").open(newline="", encoding="utf-8") as handle:
        rows = {row["uid"]: row for row in csv.DictReader(handle)}
    docs = [str(root / "treasury_bulletins_parsed" / "transformed")]
    items, dropped, pages = [], [], {}
    for part in PARTS:
        for entry in json.loads((safe_path(id_split) / part / "items.json").read_text(encoding="utf-8")):
            uid = str(entry["uid"])
            row = rows[uid]
            require(row["question"].strip() and row["answer"].strip(), "Unexpected question record")
            context = build_oracle_parsed_pages_context(row["source_files"], row["source_docs"], docs,
                                                        evidence_note=EVIDENCE_NOTE)
            if not context.strip():
                dropped.append(uid)
                continue
            for source_file, _, _ in _iter_oracle_refs(row["source_files"], row["source_docs"]):
                path = _locate_parsed_json(source_file, docs)
                if path is not None:
                    pages[path.name] = base._sha(path)
            items.append({"id": uid, "meta": {"part": part, "difficulty": row["difficulty"]},
                          "public": {"question": row["question"].strip(), "context": context},
                          "private": {"answer": row["answer"].strip()}})
    require(len({i["id"] for i in items}) == len(items) and items, "No usable item")
    return items, dropped, pages


def prepare(study, repo, upstream, id_split, output, skills, *, revision):
    root, protocol, service = base._model(study)
    out = safe_path(output)
    require(not out.exists(), "Use a new directory")
    require(len(revision) == 40, "Give the 40-character source revision")
    items, dropped, pages = draw(upstream, id_split)
    require(len(dropped) * 10 <= len(items) + len(dropped), "More than a tenth of the items have no parsed page")
    named = [base.skill_spec(s) for s in skills]
    require(len(named) >= 2 and len({n for n, _, _ in named}) == len(named), "Give at least two distinct arms")
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "items.json", seal({"items": items}))
    write_json(out / "skills.json", seal({"skills": [{"name": n, "skill": s} for n, s, _ in named]}))
    record = seal({"version": VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
                   "repo": str(safe_path(repo)), "benchmark": "officeqa", "variant": "one_call_oracle_parsed_pages",
                   "source": {"revision": revision,
                              "files": {"officeqa_full.csv": base._sha(safe_path(upstream) / "officeqa_full.csv")},
                              "parsed_pages_sha256": hashlib.sha256(
                                  json.dumps(sorted(pages.items())).encode()).hexdigest(),
                              "parsed_page_files": len(pages),
                              "id_split_manifest_sha256": base._sha(safe_path(id_split) / "split_manifest.json")},
                   "implementation_sha256": {name: base._sha(PROJECT_ROOT / name) for name in IMPLEMENTATION},
                   "parts": list(PARTS), "items": len(items), "dropped_without_parsed_page": dropped,
                   "context_chars": {"min": min(len(i["public"]["context"]) for i in items),
                                     "max": max(len(i["public"]["context"]) for i in items)},
                   "items_hash": read_json(out / "items.json", sealed=True)["record_hash"],
                   "skills_hash": read_json(out / "skills.json", sealed=True)["record_hash"],
                   "arms": [{"name": n, "skill_bytes": len(s.encode()),
                             "skill_sha256": hashlib.sha256(s.encode()).hexdigest(), **p} for n, s, p in named],
                   "system_contract": CONTRACT, **service,
                   "data_scope": "the paper's train and validation items only; its test items are never read out",
                   "tool_sha256": base._sha(Path(__file__))})
    write_json(out / "pilot.json", record)
    return record


def solve_one(api, record, out, arm, skill, item):
    """One position: sealed intent, the call(s), sealed outcome -- written by the worker itself."""
    from skillopt.envs.officeqa.evaluator import exact_match

    key = "%s:%s:%s" % (record["record_hash"][:16], arm, item["id"])
    intent = out / "intents" / arm / base._position(item["id"])
    intent.parent.mkdir(parents=True, exist_ok=True)
    write_json(intent, seal({"pilot_hash": record["record_hash"], "arm": arm, "item": item["id"], "key": key}))
    text, reason, receipts, raised = base.reply(api, record, key, system_prompt(skill),
                                                json.dumps(item["public"], ensure_ascii=False), kind=KIND)
    status, found = "unknown", None
    if text is not None:
        found = answer(text)
        status = "pass" if found is not None and exact_match(found, item["private"]["answer"]) == 1.0 else "fail"
    row = seal({"pilot_hash": record["record_hash"], "arm": arm, "item": item["id"], "status": status,
                "invalid_format": text is not None and found is None, "reason": reason,
                "request_hashes": [r.get("request_hash") for r in receipts],
                "finish_reasons": [r.get("finish_reason") for r in receipts], **base._usage(receipts, raised)})
    target = out / "calls" / arm / base._position(item["id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, row)
    return row


def run(output, *, fixture_api=None, probe=None):
    """Every arm solves every item once: the LiveMath pilot's rolling submission, margins and sealing."""
    out = safe_path(output)
    record = read_json(out / "pilot.json", sealed=True)
    require(record["version"] == VERSION and record["tool_sha256"] == base._sha(Path(__file__))
            and all(base._sha(PROJECT_ROOT / name) == value for name, value in record["implementation_sha256"].items()),
            "Tool changed")
    items = read_json(out / "items.json", sealed=True)
    skills = read_json(out / "skills.json", sealed=True)
    require(items["record_hash"] == record["items_hash"] and skills["record_hash"] == record["skills_hash"],
            "Pilot inputs changed")
    fixture = record["model"]["provider"] == "fixture"
    require(fixture == (fixture_api is not None), "Fixture client only for a fixture study")
    texts = {s["name"]: s["skill"] for s in skills["skills"]}
    arms = [a["name"] for a in record["arms"]]
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        with output_lock(out / "calls"):
            if (out / "result.json").exists():
                return read_json(out / "result.json", sealed=True)
            reason = None
            if (out / "started.json").exists():
                reason = "interrupted_run_no_automatic_resume"
            else:
                try:
                    if not fixture:
                        tool._sequence().check_client_service(
                            record["repo"], record["model"], out / "client-check",
                            record["learning_model_service"], client_options=record["client_options"])
                    write_json(out / "started.json", seal({"pilot_hash": record["record_hash"]}))
                    api = fixture_api if fixture else base._client(record, out, 1)
                    try:
                        if not fixture:
                            write_json(out / "model_service.json", seal(api.service))
                            if probe is None:  # as the panel evaluation tool: only delays a batch
                                from scripts.run_active_evidence_panel_eval import bounded, network_gate, tunnel_probe

                                proxy, host = record["model"].get("proxy"), api.service["host"]
                                probe = network_gate(lambda: bounded(lambda: tunnel_probe(proxy, host), 20.0))
                        rows = items["items"]
                        queue = []
                        for start in range(0, len(rows), base.CHUNK):
                            shift = (start // base.CHUNK) % len(arms)
                            queue += [(arm, item) for arm in arms[shift:] + arms[:shift]
                                      for item in rows[start:start + base.CHUNK]]
                        reason = base.execute(
                            queue, lambda job: solve_one(api, record, out, job[0], texts[job[0]], job[1]), probe)
                    finally:
                        if not fixture:
                            api.close()
                except Exception as exc:
                    reason = "error:" + type(exc).__name__
            statuses, counts, costs = base.collect(out, record)
            if reason is None and (any(c["not_run"] for c in counts.values()) or costs["open_intents"]):
                reason = "incomplete"
            result = seal({"version": VERSION, "pilot_hash": record["record_hash"],
                           "status": "completed" if reason is None else "pending", "reason": reason,
                           "items": len(statuses), "arms": counts, "costs": costs,
                           "costs_complete": not (costs["unresolved_calls"] or costs["attempts_without_usage"]
                                                  or costs["open_intents"])})
            write_json(out / "result.json", result)
            return result


def report(output, contrasts=()):
    """Zero calls: the LiveMath pilot's report (counts, pass rates with Wilson intervals, contrasts of a completed
    run with the coverage rule and missing-outcome bounds) -- without a chance level, which this task does not have --
    plus the pass counts by the benchmark's own difficulty label."""
    value = base.report(output, contrasts)
    value.pop("chance")
    out = safe_path(output)
    record = read_json(out / "pilot.json", sealed=True)
    statuses, _, _ = base.collect(out, record)
    levels = {i["id"]: i["meta"]["difficulty"] for i in read_json(out / "items.json", sealed=True)["items"]}
    value["by_difficulty"] = {
        level: {"items": sum(v == level for v in levels.values()),
                **{a["name"]: {"pass": sum(statuses[i].get(a["name"]) == "pass" for i in statuses if levels[i] == level),
                               "known": sum(statuses[i].get(a["name"]) in ("pass", "fail")
                                            for i in statuses if levels[i] == level)}
                   for a in record["arms"]}}
        for level in sorted(set(levels.values()))}
    return value


def zeroshot(study, repo, output, *, fixture_api=None):
    """One call without a recovery: the initial Skill a model writes from the public task card alone."""
    from skillopt.continual_learning.contracts import check_skill
    from skillopt.continual_learning.recovery import POLICY_V10

    root, protocol, service = base._model(study)
    out = safe_path(output)
    require(not out.exists(), "Use a new directory")
    out.mkdir(parents=True, mode=0o700)
    record = seal({"version": VERSION + ":zero-shot", "study": str(root), "protocol_hash": protocol["record_hash"],
                   "repo": str(safe_path(repo)), "system": zero.SYSTEM, "user": "Public task card:\n\n" + TASK_CARD,
                   "information": "public task card only: solver instructions, input fields, public metric; no task, "
                                  "no model answer, no score",
                   "selection": "generated once; never selected among alternatives", **service,
                   "tool_sha256": base._sha(Path(__file__))})
    write_json(out / "generation.json", record)
    fixture = record["model"]["provider"] == "fixture"
    require(fixture == (fixture_api is not None), "Fixture client only for a fixture study")
    text, reason, receipts, raised = None, None, [], 0
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        try:
            if not fixture:
                tool._sequence().check_client_service(
                    record["repo"], record["model"], out / "client-check", record["learning_model_service"],
                    client_options=record["client_options"])
            api = fixture_api if fixture else base._client(record, out, 1)
            try:
                text, reason, receipts, raised = base.reply(
                    api, record, record["record_hash"][:16] + ":zero-shot", record["system"], record["user"],
                    kind="officeqa-headroom-pilot-zero-shot", cap=record["reflection_max_tokens"], recover=False)
            finally:
                if not fixture:
                    api.close()
        except Exception as exc:  # what was received before the failure stays in ``receipts``
            text, reason = None, "error:" + type(exc).__name__
    if text is not None:
        text = zero.skill_text(text)
        try:
            check_skill(text, POLICY_V10["skill_budget_bytes"])
        except ValueError:
            text, reason = None, "generated_skill_invalid"
    if text is not None:
        (out / "skill.md").write_text(text, encoding="utf-8")
    result = seal({"version": record["version"], "generation_hash": record["record_hash"],
                   "status": "completed" if text is not None else "pending", "reason": reason,
                   "skill_sha256": None if text is None else hashlib.sha256(text.encode()).hexdigest(),
                   "skill_bytes": None if text is None else len(text.encode()), **base._usage(receipts, raised)})
    write_json(out / "result.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    z = sub.add_parser("zeroshot")
    p = sub.add_parser("prepare")
    for name in ("study", "repo", "output"):
        z.add_argument("--" + name, required=True)
        p.add_argument("--" + name, required=True)
    for name in ("upstream", "id-split", "revision"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--skill", action="append", default=[])
    sub.add_parser("run").add_argument("--output", required=True)
    r = sub.add_parser("report")
    r.add_argument("--output", required=True)
    r.add_argument("--contrast", action="append", default=[])
    args = parser.parse_args(argv)
    if args.command == "zeroshot":
        value = zeroshot(args.study, args.repo, args.output)
    elif args.command == "prepare":
        record = prepare(args.study, args.repo, args.upstream, args.id_split, args.output, args.skill,
                         revision=args.revision)
        value = {k: record[k] for k in ("version", "items", "dropped_without_parsed_page", "context_chars",
                                        "record_hash")}
        value["arms"] = [a["name"] for a in record["arms"]]
    elif args.command == "run":
        result = run(args.output)
        value = {k: result[k] for k in ("status", "reason", "items", "arms", "costs")}
    else:
        value = report(args.output, args.contrast)
    print(json.dumps(value, ensure_ascii=False))
    return 0 if args.command != "run" or value["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
