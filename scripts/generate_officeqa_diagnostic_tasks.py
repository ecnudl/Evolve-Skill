"""Generate CATEGORY-TARGETED OfficeQA tasks from ONE SIDE of an L/H split of a stage's TRAINING tasks (generator v2,
2026-10-15; design docs/handoff/generalization-architecture-20261015.md section 2.3).

Everything that makes a v1 generated task sound is kept (``generate_officeqa_tasks``: the writer never states an
answer, the answer is COMPUTED exactly from figures quoted from whole table cells of the pages, the same deterministic
filters and reviewer verdicts, the same lifecycle). What changes:
- every question targets one registered CATEGORY of a known failure mode of the solver on OfficeQA (rounding, unit or
  scale, percent conventions, choosing among several printed versions of a series, figures on different pages, a
  simple statistic), and the category travels with the item;
- a generation covers ONE side of the study's L/H split of the training draw: this module, the LEARN side (diagnostic
  items; the writer sees the source question as in v1 -- those are training questions the learner sees anyway), and
  ``generate_officeqa_transfer_tasks``, the HELD-OUT side, PAGE-ONLY (no held-out question reaches any prompt);
- ``derivations()`` reads the accepted items' derivations (host-only: they are the items' reference answers).

Usage:
  python scripts/generate_officeqa_diagnostic_tasks.py prepare --study <extension study> --split <its split> \\
      --repo <credential repo> --seed <stage seed> --lh-split <L/H split.json> --output <new dir>
  python scripts/generate_officeqa_diagnostic_tasks.py run --output <prepared dir>
  python scripts/generate_officeqa_diagnostic_tasks.py check --output <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import generate_officeqa_tasks as v1  # noqa: E402
from scripts import generate_searchqa_tasks as base  # noqa: E402
from scripts import run_fivebench_g_stage as tool  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.continual_eval.core import read_json, require, safe_path, write_json  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

VERSION = "generated-officeqa-diagnostic-tasks-v2"
SIDE = "learn"
SOURCE_QUESTION_SHOWN = True
BENCHMARK = v1.BENCHMARK
PER_TASK = v1.PER_TASK
CATEGORIES = {
    "precision": "the answer must be rounded to a stated number of decimal places (or to a whole number) after a "
                 "computation whose exact value has more digits",
    "scale": "the pages print the figures in one unit (thousands, millions, billions of dollars) and the question "
             "asks for the answer in another unit, so the expression contains the conversion",
    "percent": "the question asks for a percent change, a share in percent, or a difference in percentage points, "
               "so the expression decides between a ratio, a ratio times 100 and a plain difference",
    "vintage": "the same series or line item is printed more than once on the pages (different columns, periods, "
               "preliminary and revised values, or two tables) and the question names exactly which one it asks for",
    "multipage": "the figures come from two different pages of the supplied context",
    "statistic": "the answer is a simple statistic over three or more printed figures (a sum, an average, an average "
                 "difference or a share of a total)",
}
_CATEGORY_TEXT = ("Every question must target ONE of these categories, named in its \"category\" field; spread your "
                  "questions over different categories that the pages support, and skip a category the pages do not "
                  "support:\n" + "".join("- \"%s\": %s;\n" % (name, text) for name, text in CATEGORIES.items()))


def _with_categories(writer):
    out = writer.replace("Return one JSON object and nothing else:", _CATEGORY_TEXT + "Return one JSON object and nothing else:")
    out = out.replace("\"expression\": \"...\", \"decimals\": 0}}]}}",
                      "\"expression\": \"...\", \"decimals\": 0, \"category\": \"...\"}}]}}")
    require(out.count("\"category\"") == 2 and _CATEGORY_TEXT in out, "The category request did not enter the writer system")
    return out


WRITER = _with_categories(v1.WRITER)
REVIEWER, VERDICTS = v1.REVIEWER, v1.VERDICTS
FILTERS = (v1.FILTERS + "; plus: a category from the registered list (" + ", ".join(CATEGORIES) + "); the "
           "expression is plain arithmetic text only (figure names, numbers, + - * / ( ) . , and abs/min/max: no comment)")
question_key = v1.question_key
_V1_IDENTITY = v1.tool_sha256
_ARITHMETIC = re.compile(r"[a-z0-9_+\-*/()., ]+")  # figure names, numbers, operators, parentheses, abs/min/max


def tool_sha256():
    """The generator's identity: this file, the v1 generator whose filters it reuses, and the shared lifecycle."""
    return hashlib.sha256((base._sha(Path(__file__)) + _V1_IDENTITY()).encode()).hexdigest()


def admit(candidate, source, seen_questions):
    """The category check, then v1's deterministic filters on the candidate without its category (v1's duplicate check
    against the source question runs on the host and shows nothing to any model)."""
    if type(candidate) is not dict:
        return "malformed", None
    category = candidate.get("category")
    if type(category) is not str or category not in CATEGORIES:
        return "category_missing_or_unknown", None
    reason, fields = v1.admit({k: v for k, v in candidate.items() if k != "category"}, source, seen_questions)
    if reason is not None:
        return reason, None
    if not _ARITHMETIC.fullmatch(fields["expression"]):  # v1's parser ignores comments: v2 admits plain arithmetic only
        return "expression_not_plain_arithmetic", None
    return None, {**fields, "category": category}


write_payload, review_payload = v1.write_payload, v1.review_payload


def task_item(public, item):
    return {**v1.task_item(public, item), "category": item["category"]}


def prepare_side(kind, study, split_path, output, repo, *, seed, per_task, lh_split):
    """v1's preparation (this seed's training draw, the same generation manifest and lifecycle record) restricted to
    ``kind.SIDE`` of the L/H split, under ``kind``'s writer/reviewer systems and identity. No shared module global is
    modified."""
    from skillopt.active_evidence import protocol as ae
    from skillopt.continual_learning.recovery import RETRY_POLICIES

    version, policy, budget = tool._protocol("v11")
    require(type(per_task) is int and 1 <= per_task <= 4, "One to four questions per training task")
    require(kind.SIDE in ("learn", "held_out"), "Unknown side")
    root, protocol = tool._study(study)
    out = safe_path(output)
    tool._outside(out, root, protocol, [split_path, lh_split])
    require(not out.exists(), "Use a new directory")
    split = read_json(split_path, sealed=True)
    tool.check_split(split, protocol, BENCHMARK)
    cut = read_json(lh_split, sealed=True)
    dev_path = tool.dev_panel_path(protocol, BENCHMARK)
    dev_panel = read_json(dev_path)
    train, _ = tool.train_tasks(dev_panel, split, BENCHMARK, seed)
    drawn = {t["task_id"] for t in train}
    side = set(cut["learn_tasks"] if kind.SIDE == "learn" else cut["held_out_tasks"])
    require(side and side <= drawn and not set(cut["learn_tasks"]) & set(cut["held_out_tasks"])
            and set(cut["learn_tasks"]) | set(cut["held_out_tasks"]) == drawn,
            "The L/H split does not partition this seed's training draw")
    train = [t for t in train if t["task_id"] in side]
    families = sorted({t["family_id"] for t in train})
    require(all(type(t["public"]["context"]) is str for t in train), "A training task's pages are one text")
    panel = {**deepcopy(dev_panel), "tasks": deepcopy(train)}
    value = ae.manifest(panel, step_families=families, challenge_families=[], model=deepcopy(protocol["model"]),
                        budget=budget, runtime=protocol["roles"][BENCHMARK]["runtime"], parent_skill="", seed=seed,
                        arms=base.ARMS, limits=ae.effective_limits(base.ARMS, 0))
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "panel.json", panel)
    write_json(out / "manifest.json", value)
    record = seal({"version": kind.VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
                   "split_hash": split["record_hash"], "benchmark": BENCHMARK, "repo": str(safe_path(repo)),
                   "seed": seed, "per_task": per_task, "source_tasks": len(train),
                   "source_task_hashes": sorted(digest(t) for t in train), "source_families": families,
                   "lh_split_hash": cut["record_hash"], "side": kind.SIDE,
                   "source_question_shown": kind.SOURCE_QUESTION_SHOWN,
                   "writer_system": kind.WRITER.format(count=per_task, figures=v1.MAX_FIGURES, decimals=v1.MAX_DECIMALS),
                   "reviewer_system": kind.REVIEWER, "filters": kind.FILTERS,
                   "development_questions_hash": digest(sorted(v1.question_key(t["public"]["question"])
                                                               for t in dev_panel["tasks"])),
                   "information": "public fields of this side's training tasks only (%s); no reference answer, no "
                                  "validation / test item, no solver outcome; the reference of a generated task is "
                                  "computed from figures quoted from those pages"
                                  % ("question and parsed pages" if kind.SOURCE_QUESTION_SHOWN else "parsed pages only"),
                   "client_options": {"delivery_retry_policy": RETRY_POLICIES[version]},
                   "learning_model_service": protocol["learning_model_service"],
                   "native_lock": protocol["config"]["native_lock"], "dev_panel": str(safe_path(dev_path)),
                   "manifest_hash": value["record_hash"], "panel_sha256": base._sha(out / "panel.json"),
                   "tool_sha256": kind.tool_sha256()})
    write_json(out / "generation.json", record)
    return record


def prepare(study, split_path, output, repo, *, seed, per_task=PER_TASK, lh_split):
    return prepare_side(sys.modules[__name__], study, split_path, output, repo, seed=seed, per_task=per_task,
                        lh_split=lh_split)


def run(output, *, fixture_api=None, fixture_gate=None):
    return base.run(output, fixture_api=fixture_api, fixture_gate=fixture_gate, kind=sys.modules[__name__])


def check(output):
    return base.check(output, sys.modules[__name__])


def family_map(output):
    return base.family_map(output, sys.modules[__name__])


def derivations_of(kind, output):
    """Zero calls: {generated item id -> its derivation} of a completed generation of ``kind`` -- the figures (printed
    value and quote), the expression, the rounding, the computed answer, the category and the source task -- read from
    the sealed records. Host-only: these are the items' reference answers and must never reach a solver."""
    out = safe_path(output)
    path, record, _ = base.check(output, kind)
    records = read_json(out / "records.json", sealed=True)
    items = {i["id"]: i for i in json.loads(path.read_text(encoding="utf-8"))}
    found = {}
    for entry in records["sources"]:
        for candidate in entry["candidates"]:
            if candidate.get("accepted") and candidate["id"] in items:
                found[candidate["id"]] = {"source_task_hash": entry["source_task_hash"],
                                          **{k: deepcopy(candidate[k]) for k in ("question", "figures", "expression",
                                                                                 "decimals", "answer", "category")}}
    require(set(found) == set(items), "Every accepted item has exactly one derivation")
    return found


def derivations(output):
    return derivations_of(sys.modules[__name__], output)


def main_for(kind, argv=None):
    parser = argparse.ArgumentParser(description=kind.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    for name in ("--study", "--split", "--repo", "--output", "--lh-split"):
        p.add_argument(name, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--per-task", type=int, default=kind.PER_TASK)
    for name in ("run", "check"):
        sub.add_parser(name).add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        record = kind.prepare(args.study, args.split, args.output, args.repo, seed=args.seed, per_task=args.per_task,
                              lh_split=args.lh_split)
        print(json.dumps({k: record[k] for k in ("version", "side", "seed", "source_tasks", "record_hash")}))
        return 0
    if args.command == "run":
        result = kind.run(args.output)
        print(json.dumps({k: result.get(k) for k in ("version", "status", "reason", "items")}))
        return 0 if result["status"] == "completed" else 1
    _, _, result = kind.check(args.output)
    print(json.dumps({k: result.get(k) for k in ("version", "status", "items")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_for(sys.modules[__name__]))
