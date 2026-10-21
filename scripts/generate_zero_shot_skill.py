"""Generate ONE zero-shot initial Skill for a benchmark from its PUBLIC task card only (no task, no model answer,
no score) -- the pre-frozen "reasonable initial instruction" of the learn-from-B study
(docs/handoff/active-evidence-learn-from-b-design-20261012.md).

One reflection-role call of the frozen analyst model through the learning-v11 ledger; the reply is the Skill text.
It is generated ONCE and never selected among alternatives: ``prepare`` seals the prompt before the call, ``run``
refuses a directory that has already been started, and the text is frozen by its hash before any Skill solves a
task under it. The ledger needs a manifest, so the run is authorized over the study's frozen development panel;
no task of that panel is read into the prompt (the prompt is the fixed text below).

Usage:
  python scripts/generate_zero_shot_skill.py prepare --study <F study> --split <split manifest> \\
      --repo <credential repo> --benchmark searchqa --output <new dir>
  python scripts/generate_zero_shot_skill.py run --output <prepared dir>     # writes <dir>/skill.md
  python scripts/generate_zero_shot_skill.py check --output <dir>            # exit 0 only for a completed generation
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_fivebench_g_stage as tool  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json  # noqa: E402

VERSION = "zero-shot-initial-skill-v1"
ARMS = {"feedback": "scalar", "post_update": "none"}
SYSTEM = (
    "You write the guidance text (a \"Skill\") that will be appended to the system prompt of another language model "
    "which solves tasks of one kind. You are given ONLY the public description of the task kind. You have seen no "
    "example task, no model answer and no score, and you must not pretend otherwise: do not invent facts about the "
    "data.\n\nWrite the guidance a careful practitioner would write BEFORE any experience with the task: what the "
    "solver should pay attention to, how it should use the supplied material, and how it should form its final "
    "answer so that it satisfies the stated output contract and scoring. Keep it general for this task kind.\n\n"
    "Output only the guidance text in plain Markdown, at most 12 bullet points, with no preamble and no closing "
    "remark.")
LIVEMATH_CARD = (
    "Task kind: multiple-choice questions about research-level mathematics (the LiveMathematicianBench "
    "benchmark): each question is built from a theorem of a recent arXiv paper.\n"
    "Input the solver receives: a JSON object with two fields -- \"question\" (the statement to complete "
    "or decide) and \"choices\" (five options labelled A to E, separated by blank lines; exactly one is "
    "correct).\n"
    "Fixed instructions the solver always receives: \"Solve the supplied task using only the supplied "
    "public information.\" and \"Choose exactly one of the listed options and return only its letter "
    "inside <answer>...</answer>.\"\n"
    "Scoring (public metric): the letter inside the last <answer>...</answer> is compared with the "
    "letter of the correct option; a reply without such a tag, or with anything but one letter in it, "
    "counts as wrong. Anything outside the tag is ignored.")
OFFICEQA_CARD = (
    "Task kind: questions about U.S. Treasury Bulletin documents (the OfficeQA benchmark, in a one-call "
    "form). Answering needs finding the right values in the supplied document pages (running text and "
    "tables) and often a calculation with them.\n"
    "Input the solver receives: a JSON object with two fields -- \"question\" and \"context\" (the parsed "
    "text of the bulletin page or pages the question refers to; tables are rendered as text; a long page "
    "may be cut).\n"
    "Fixed instructions the solver always receives: \"Solve the supplied task using only the supplied "
    "public information.\" and \"Return the concise final answer inside <answer>...</answer>.\"\n"
    "Scoring (public metric): the text inside the last <answer>...</answer> is compared with the "
    "reference answer by exact match after normalization (lower case; commas removed; punctuation "
    "removed except digits, '.', '-' and '%'; the words million, billion, dollar(s) and nominal removed; "
    "whitespace collapsed). There is no numeric tolerance. A reply without such a tag counts as wrong. "
    "Anything outside the tag is ignored.")
# Public task cards: the solver's fixed instructions (verbatim from skillopt/continual_eval/backends.py), the input
# fields, and the benchmark's public metric as implemented by the scorer. No example, no outcome.
TASK_CARDS = {
    "searchqa": (
        "Task kind: open-domain question answering over retrieved search snippets (the SearchQA benchmark).\n"
        "Input the solver receives: a JSON object with two fields -- \"question\" (a short clue-style question) and "
        "\"context\" (several retrieved web search snippets, possibly noisy or irrelevant).\n"
        "Fixed instructions the solver always receives: \"Solve the supplied task using only the supplied public "
        "information.\" and \"Return the concise final answer inside <answer>...</answer>.\"\n"
        "Scoring (public metric): the text inside the last <answer>...</answer> is compared with the reference "
        "answer(s) by exact match after SQuAD-style normalization (lower case, punctuation removed, the articles "
        "a/an/the removed, whitespace collapsed). Anything else in the reply is ignored."),
    # the two extension benchmarks: the cards of their headroom pilots, verbatim
    "livemath": LIVEMATH_CARD,
    "officeqa": OFFICEQA_CARD,
}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prompt(benchmark):
    require(benchmark in TASK_CARDS, "No public task card for this benchmark yet")
    return SYSTEM, "Public task card:\n\n" + TASK_CARDS[benchmark]


def prepare(study, split_path, output, repo, *, benchmark, seed=20261012):
    from skillopt.active_evidence import protocol as ae
    from skillopt.continual_learning.recovery import RETRY_POLICIES

    version, policy, budget = tool._protocol("v11")
    root, protocol = tool._study(study)
    out = safe_path(output)
    tool._outside(out, root, protocol, [split_path])
    require(not out.exists(), "Use a new directory")
    split = read_json(split_path, sealed=True)
    tool.check_split(split, protocol, benchmark)
    dev_path = tool.dev_panel_path(protocol, benchmark)
    panel = read_json(dev_path)
    panel = {**panel, "tasks": [t for t in panel["tasks"] if t["partition"] == "development"]}
    system, user = prompt(benchmark)
    value = ae.manifest(panel, step_families=sorted({t["family_id"] for t in panel["tasks"]}), challenge_families=[],
                        model=deepcopy(protocol["model"]), budget=budget,
                        runtime=protocol["roles"][benchmark]["runtime"], parent_skill="", seed=seed, arms=ARMS,
                        limits=ae.effective_limits(ARMS, 0))
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "panel.json", panel)
    write_json(out / "manifest.json", value)
    record = seal({"version": VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
                   "benchmark": benchmark, "repo": str(safe_path(repo)), "system": system, "user": user,
                   "prompt_sha256": hashlib.sha256((system + "\n\n" + user).encode()).hexdigest(),
                   "information": "public task card only: solver instructions, input fields, public metric; no task, "
                                  "no model answer, no score",
                   "selection": "generated once; never selected among alternatives",
                   "client_options": {"delivery_retry_policy": RETRY_POLICIES[version]},
                   "learning_model_service": protocol["learning_model_service"],
                   "native_lock": protocol["config"]["native_lock"],
                   "manifest_hash": value["record_hash"], "panel_sha256": _sha(out / "panel.json"),
                   "tool_sha256": _sha(Path(__file__))})
    write_json(out / "generation.json", record)
    return record


def skill_text(reply):
    """The reply as a Skill text: a single wrapping Markdown code fence is removed, nothing else is edited."""
    text = reply.strip()
    if text.startswith("```") and text.endswith("```") and text.count("```") == 2:
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip() if "\n" in text else ""
    return text + "\n"


def write(value, record, root, api):
    """The one generation call -> (Skill text or None, sealed result). Any failure is a durable pending result."""
    from skillopt.continual_learning.contracts import check_skill
    from skillopt.continual_learning.ledger import BudgetExhausted, LearningPending, Ledger
    from skillopt.continual_learning.recovery import POLICY_V10

    write_json(root / "model_service.json", seal(api.service))
    ledger = Ledger(root, value, api)
    text = reason = receipt = None
    try:
        receipt = ledger.call("reflection", "zero-shot-initial-skill:0", record["system"], record["user"],
                              value["budget"]["reflection_max_tokens"])
        if receipt.get("ok") is not True or type(receipt.get("response")) is not str:
            reason = "generation_call_not_delivered"
        else:
            text = skill_text(receipt["response"])
            if text.strip() == "":
                text, reason = None, "generated_skill_empty"
            else:
                try:
                    check_skill(text, POLICY_V10["skill_budget_bytes"])
                except ValueError:
                    text, reason = None, "generated_skill_invalid"
    except (LearningPending, BudgetExhausted) as exc:
        reason = "%s:%s" % (type(exc).__name__, str(exc)[:200])
    except Exception as exc:  # the type only: a provider message is never copied into the record
        reason = "error:" + type(exc).__name__
    costs = ledger.snapshot()
    if reason is None and (costs.get("unclosed_calls") != 0 or ledger.usage_blocks_completion(costs)):
        text, reason = None, "usage_or_receipt_accounting_incomplete"
    return text, seal({"version": VERSION, "generation_hash": record["record_hash"],
                       "status": "completed" if reason is None else "pending", "reason": reason,
                       "request_hash": None if receipt is None else receipt.get("request_hash"),
                       "finish_reason": None if receipt is None else receipt.get("finish_reason"),
                       "skill_sha256": None if text is None else hashlib.sha256(text.encode()).hexdigest(),
                       "skill_bytes": None if text is None else len(text.encode()), "costs": costs,
                       "regeneration": "never in place: a pending generation is reviewed and, if repeated, repeated in "
                                       "a new directory and disclosed"})


def run(output, *, fixture_api=None):
    """Generate once. The checks of an earlier attempt and the publication of the text and the result happen while
    both locks are held."""
    from skillopt.active_evidence import protocol as ae
    from skillopt.continual_learning.recovery import client_options
    from skillopt.validator_pilot.api import CachedAPI

    out = safe_path(output)
    record = read_json(out / "generation.json", sealed=True)
    require(record["version"] == VERSION and record["tool_sha256"] == _sha(Path(__file__)), "Tool changed")
    value = read_json(out / "manifest.json", sealed=True)
    panel = read_json(out / "panel.json")
    require(value["record_hash"] == record["manifest_hash"] and _sha(out / "panel.json") == record["panel_sha256"],
            "Generation inputs changed")
    ae.validate_manifest(value, panel)
    fixture = value["model"]["provider"] == "fixture"
    require(fixture or fixture_api is None, "Natural run cannot inject fixtures")
    require(not fixture or fixture_api is not None, "Invalid fixture callbacks")
    root = out / "learning"
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        with output_lock(root):
            if (out / "result.json").exists():
                return read_json(out / "result.json", sealed=True)
            if (root / "started.json").exists():
                result = seal({"version": VERSION, "generation_hash": record["record_hash"], "status": "pending",
                               "reason": "interrupted_generation_no_automatic_resume", "skill_sha256": None,
                               "skill_bytes": None})
                write_json(out / "result.json", result)
                return result
            text = None
            try:
                sequence = None if fixture else tool._sequence()
                if not fixture:
                    sequence.check_client_service(record["repo"], value["model"], out / "client-check",
                                                  record["learning_model_service"],
                                                  client_options=record["client_options"])
                write_json(root / "started.json", seal({"generation_hash": record["record_hash"]}))
                if fixture:
                    api = fixture_api
                else:
                    model = value["model"]
                    api = CachedAPI(Path(record["repo"]), root / "api", provider=model["provider"],
                                    model=model["name"], workers=1, reasoning_effort=model["reasoning_effort"],
                                    **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                                    **({"proxy": model["proxy"]} if "proxy" in model else {}), **client_options(value))
                try:
                    text, result = write(value, record, root, api)
                finally:
                    api.close()
                if not fixture:
                    sequence.verify_service(root, record["learning_model_service"])
            except Exception as exc:
                text = None
                result = seal({"version": VERSION, "generation_hash": record["record_hash"], "status": "pending",
                               "reason": "error:" + type(exc).__name__, "skill_sha256": None, "skill_bytes": None})
            if text is not None:
                (out / "skill.md").write_text(text, encoding="utf-8")
            write_json(out / "result.json", result)
            return result


def check(output):
    """The published Skill of a COMPLETED generation: (path, sha256). An interrupted publication can leave a Skill
    file without a completed record -- such a file is never to be consumed."""
    out = safe_path(output)
    record = read_json(out / "generation.json", sealed=True)
    result = read_json(out / "result.json", sealed=True)
    path = out / "skill.md"
    require(result.get("generation_hash") == record["record_hash"] and result.get("status") == "completed"
            and path.is_file() and _sha(path) == result["skill_sha256"],
            "No completed generation with a matching Skill file")
    return path, result["skill_sha256"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    for name in ("study", "split", "repo", "output"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--benchmark", required=True, choices=sorted(TASK_CARDS))
    sub.add_parser("run").add_argument("--output", required=True)
    sub.add_parser("check").add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "check":
        path, sha = check(args.output)
        print(json.dumps({"skill": str(path), "skill_sha256": sha}))
        return 0
    if args.command == "prepare":
        record = prepare(args.study, args.split, args.output, args.repo, benchmark=args.benchmark)
        value = {k: record[k] for k in ("version", "benchmark", "prompt_sha256", "record_hash")}
    else:
        result = run(args.output)
        value = {k: result.get(k) for k in ("version", "status", "reason", "skill_sha256", "skill_bytes", "record_hash")}
    print(json.dumps(value))
    return 0 if args.command == "prepare" or value["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
