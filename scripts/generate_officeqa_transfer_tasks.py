"""Generate category-targeted OfficeQA tasks from the HELD-OUT side of an L/H split of a stage's training tasks,
PAGE-ONLY (generator v2, transfer side; 2026-10-15). Identical to ``generate_officeqa_diagnostic_tasks`` except that
no held-out question reaches any prompt: the writer sees only the parsed pages of one held-out task, the reviewer sees
the pages and the new question, and the reviewer's "distinct from the source question" verdict -- which needs the
source question -- is dropped (v1's exact-duplicate check against the source question still runs, on the host).
These items are the study's transfer pool: they score frozen candidates and never reach a learner.

Usage:
  python scripts/generate_officeqa_transfer_tasks.py prepare --study <extension study> --split <its split> \\
      --repo <credential repo> --seed <stage seed> --lh-split <L/H split.json> --output <new dir>
  python scripts/generate_officeqa_transfer_tasks.py run --output <prepared dir>
  python scripts/generate_officeqa_transfer_tasks.py check --output <dir>
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import generate_officeqa_diagnostic_tasks as v2  # noqa: E402
from scripts import generate_officeqa_tasks as v1  # noqa: E402
from scripts import generate_searchqa_tasks as base  # noqa: E402
from skillopt.continual_eval.core import require  # noqa: E402

VERSION = "generated-officeqa-transfer-tasks-v2"
SIDE = "held_out"
SOURCE_QUESTION_SHOWN = False
BENCHMARK, PER_TASK, CATEGORIES = v2.BENCHMARK, v2.PER_TASK, v2.CATEGORIES


def _replace(text, old, new):
    require(text.count(old) == 1, "The page-only rewrite of a frozen prompt did not apply: " + old[:60])
    return text.replace(old, new)


WRITER = _replace(v2.WRITER,
                  "You are given ONE source item: a question and the parsed page(s) it was asked about. Write up to "
                  "{count} NEW questions over the SAME pages in the style of the source question (a precise, "
                  "self-contained request for one number that names the table or series, the period and the unit as "
                  "needed), each about DIFFERENT figures than the source question and than each other.",
                  "You are given the parsed page(s) of ONE source document. Write up to {count} NEW questions over "
                  "these pages, each a precise, self-contained request for one number that names the table or series, "
                  "the period and the unit as needed, each about DIFFERENT figures than the others.")
REVIEWER = _replace(_replace(_replace(_replace(
    v1.REVIEWER,
    "You are given the pages, the source question they came with, a new question,", "You are given the pages, a new question,"),
    "Decide six things:", "Decide five things:"),
    "- distinct: does the question ask for something else than the source question does (not a paraphrase of it "
    "and not the same figure)?\n", ""),
    "\"distinct\": true|false, ", "")
VERDICTS = tuple(v for v in v1.VERDICTS if v != "distinct")
FILTERS = v2.FILTERS + "; page-only: no source question in any prompt"
question_key, admit, task_item = v2.question_key, v2.admit, v2.task_item


def tool_sha256():
    return hashlib.sha256((base._sha(Path(__file__)) + v2.tool_sha256()).encode()).hexdigest()


def write_payload(public):
    return {"pages": public["context"]}


def review_payload(public, item):
    return {"pages": public["context"], "question": item["question"], "figures": item["figures"],
            "expression": item["expression"], "decimals": item["decimals"], "computed_answer": item["answer"]}


def prepare(study, split_path, output, repo, *, seed, per_task=PER_TASK, lh_split):
    return v2.prepare_side(sys.modules[__name__], study, split_path, output, repo, seed=seed, per_task=per_task,
                           lh_split=lh_split)


def run(output, *, fixture_api=None, fixture_gate=None):
    return base.run(output, fixture_api=fixture_api, fixture_gate=fixture_gate, kind=sys.modules[__name__])


def check(output):
    return base.check(output, sys.modules[__name__])


def family_map(output):
    return base.family_map(output, sys.modules[__name__])


def derivations(output):
    return v2.derivations_of(sys.modules[__name__], output)


if __name__ == "__main__":
    raise SystemExit(v2.main_for(sys.modules[__name__]))
