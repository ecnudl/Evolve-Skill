"""Generate SearchQA test tasks from a stage's TRAINING tasks, to serve as the selection set of the validation-gated
Rubric+Research learner (learning v10) in place of the canonical validation partition
(docs/handoff/generated-validation-design-20261013.md).

Label-free and train-only: the writer sees one training task's PUBLIC fields (its question and retrieved snippets)
and writes up to ``--per-task`` new clue-style questions about OTHER facts in those snippets, each with an answer
that appears verbatim in them and a supporting quote. No reference answer, no validation / test / reserve item and
no solver outcome enters a prompt. A candidate survives when

1. deterministic filters hold (the answer and the quote are verbatim in the snippets, the quote contains the answer,
   the question does not contain it, lengths are bounded, it differs from the source question and from every other
   generated or development question), and
2. an independent reviewer call judges the answer supported, unique and in its shortest natural form.

No filter uses a solver's answer, so the pool is not conditioned on being solved. The generated task keeps the
source task's snippets as its context and the proposed answer as its only reference; it is scored by the frozen
exact-match scorer like any SearchQA task.

Usage:
  python scripts/generate_searchqa_tasks.py prepare --study <F study> --split <split manifest> \\
      --repo <credential repo> --seed <stage seed> --output <new dir>
  python scripts/generate_searchqa_tasks.py run --output <prepared dir>   # writes items.json, records.json
  python scripts/generate_searchqa_tasks.py check --output <dir>          # exit 0 only for a completed generation
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_fivebench_g_stage as tool  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

VERSION = "generated-searchqa-tasks-v1"
BENCHMARK = "searchqa"
ARMS = {"feedback": "scalar", "post_update": "none"}
BATCH = 4  # units submitted together (a connection failure then costs at most four calls' attempts)
PER_TASK = 2
WRITER = (
    "You write evaluation questions for an open-domain question-answering task. You are given ONE source item: a "
    "clue-style question and the retrieved web search snippets that came with it. Write up to {count} NEW "
    "clue-style questions in the same style (a short statement or clue about an unnamed thing, as in a quiz show), "
    "each about a DIFFERENT fact than the source question and than each other, such that:\n"
    "- the answer is a short entity or value (one to five words) that appears verbatim in the snippets;\n"
    "- the snippets alone are enough to answer it, and only one answer fits;\n"
    "- the question does not contain its answer;\n"
    "- the question does not ask what the source question asks.\n"
    "For each question give the exact answer string as it appears in the snippets and a short verbatim quote (at "
    "most 300 characters) from the snippets that contains the answer and supports it. If the snippets do not "
    "support such a question, return fewer questions or none.\n"
    "Return one JSON object and nothing else: {{\"tasks\": [{{\"question\": \"...\", \"answer\": \"...\", "
    "\"quote\": \"...\"}}]}}")
REVIEWER = (
    "You check a quiz question against retrieved web search snippets. You are given the snippets, the source "
    "question they were retrieved for, a new question, a proposed answer and a supporting quote. Decide four "
    "things:\n"
    "- supported: do the snippets state that the proposed answer is the answer to the question?\n"
    "- unique: is there no other equally good answer to the question in the snippets?\n"
    "- form: is the proposed answer the shortest natural name or value of the thing asked for, with no extra words?\n"
    "- distinct: does the question ask for something else than the source question does (not a paraphrase of it "
    "and not the same answer)?\n"
    "Return one JSON object and nothing else: {\"supported\": true|false, \"unique\": true|false, \"form\": "
    "true|false, \"distinct\": true|false, \"reason\": \"at most 200 characters\"}")
VERDICTS = ("supported", "unique", "form", "distinct")
FILTERS = ("question 20-300 chars; answer 1-60 chars and at most 6 words, not yes/no; quote at most 400 chars; "
           "normalized answer inside the normalized snippets; quote inside the snippets and containing the answer "
           "(case ignored, whitespace collapsed); the normalized answer does not occur as a word sequence in the "
           "normalized question; normalized question differs from the source question, from every development "
           "question and from every earlier accepted question (exact identity after normalization, not semantic "
           "deduplication -- paraphrases of the source question are left to the reviewer)")


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tool_sha256():
    """The identity of the generator a prepared directory is bound to."""
    return _sha(Path(__file__))


def _squash(text):
    return re.sub(r"\s+", " ", text).strip()


def context_text(context):
    """The snippets as one text (the native schema allows a string or a list of strings)."""
    return context if type(context) is str else "\n".join(context)


def admissible(candidate, source, seen_questions):
    """None when the candidate passes the deterministic filters, otherwise the first reason it fails."""
    from skillopt.envs.searchqa.evaluator import normalize_answer

    if type(candidate) is not dict or any(type(candidate.get(k)) is not str for k in ("question", "answer", "quote")):
        return "malformed"
    question, answer, quote = (_squash(candidate[k]) for k in ("question", "answer", "quote"))
    context = _squash(context_text(source["context"]))
    if not 20 <= len(question) <= 300:
        return "question_length"
    if not 1 <= len(answer) <= 60 or len(answer.split()) > 6 or normalize_answer(answer) in ("", "yes", "no"):
        return "answer_form"
    if len(quote) > 400 or quote.lower() not in context.lower() or answer.lower() not in quote.lower():
        return "quote_not_verbatim_or_without_answer"
    if normalize_answer(answer) not in normalize_answer(context):
        return "answer_not_in_snippets"
    if (" " + normalize_answer(answer) + " ") in (" " + normalize_answer(question) + " "):
        return "answer_in_question"
    key = normalize_answer(question)
    if key == normalize_answer(source["question"]) or key in seen_questions:
        return "duplicate_question"
    return None


def question_key(text):
    """The identity under which two questions count as the same one."""
    from skillopt.envs.searchqa.evaluator import normalize_answer

    return normalize_answer(text)


def admit(candidate, source, seen_questions):
    """(None, the fields of the candidate's record) for a survivor of the deterministic filters, else (reason, None)."""
    reason = admissible(candidate, source, seen_questions)
    if reason is not None:
        return reason, None
    return None, {k: _squash(candidate[k]) for k in ("question", "answer", "quote")}


def write_payload(public):
    return {"source_question": public["question"], "snippets": public["context"]}


def review_payload(public, item):
    return {"snippets": public["context"], "source_question": public["question"], "question": item["question"],
            "proposed_answer": item["answer"], "quote": item["quote"]}


def task_item(public, item):
    return {"id": item["id"], "question": item["question"], "context": public["context"], "answers": [item["answer"]]}


def prepare(study, split_path, output, repo, *, seed, per_task=PER_TASK):
    from skillopt.active_evidence import protocol as ae
    from skillopt.continual_learning.recovery import RETRY_POLICIES
    from skillopt.envs.searchqa.evaluator import normalize_answer

    version, policy, budget = tool._protocol("v11")
    require(type(per_task) is int and 1 <= per_task <= 4, "One to four questions per training task")
    root, protocol = tool._study(study)
    out = safe_path(output)
    tool._outside(out, root, protocol, [split_path])
    require(not out.exists(), "Use a new directory")
    split = read_json(split_path, sealed=True)
    require(split["version"] == tool.SPLIT_VERSION
            and split["f_study_usage"][BENCHMARK]["protocol_hash"] == protocol["record_hash"],
            "The split was not verified against this study")
    ref = protocol["references"][BENCHMARK]
    plan = read_json(safe_path(ref["root"]) / "plan.json", sealed=True)
    require(plan["record_hash"] == ref["plan_hash"], "Reference plan changed")
    dev_path = plan["config"]["panels"][BENCHMARK]
    require(protocol["files"].get(str(safe_path(dev_path))) == _sha(dev_path),
            "F's development panel is not the frozen input the study recorded")
    dev_panel = read_json(dev_path)
    # exactly the training rows a learning stage of this seed draws (the stage tool's own outcome-blind draw)
    train, families = tool.train_tasks(dev_panel, split, BENCHMARK, seed)
    require(all(type(t["public"]["context"]) is str or (type(t["public"]["context"]) is list
                and all(type(x) is str for x in t["public"]["context"])) for t in train),
            "A training task's snippets are a string or a list of strings")
    panel = {**deepcopy(dev_panel), "tasks": deepcopy(train)}
    value = ae.manifest(panel, step_families=sorted(families), challenge_families=[],
                        model=deepcopy(protocol["model"]), budget=budget,
                        runtime=protocol["roles"][BENCHMARK]["runtime"], parent_skill="", seed=seed, arms=ARMS,
                        limits=ae.effective_limits(ARMS, 0))
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "panel.json", panel)
    write_json(out / "manifest.json", value)
    record = seal({"version": VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
                   "split_hash": split["record_hash"], "benchmark": BENCHMARK, "repo": str(safe_path(repo)),
                   "seed": seed, "per_task": per_task, "source_tasks": len(train),
                   "source_task_hashes": sorted(digest(t) for t in train), "source_families": sorted(families),
                   "writer_system": WRITER.format(count=per_task), "reviewer_system": REVIEWER, "filters": FILTERS,
                   "development_questions_hash": digest(sorted(normalize_answer(t["public"]["question"])
                                                               for t in dev_panel["tasks"])),
                   "information": "public fields (question, snippets) of this seed's training tasks only; no "
                                  "reference answer, no validation / test / reserve item, no solver outcome",
                   "client_options": {"delivery_retry_policy": RETRY_POLICIES[version]},
                   "learning_model_service": protocol["learning_model_service"],
                   "native_lock": protocol["config"]["native_lock"], "dev_panel": str(safe_path(dev_path)),
                   "manifest_hash": value["record_hash"], "panel_sha256": _sha(out / "panel.json"),
                   "tool_sha256": tool_sha256()})
    write_json(out / "generation.json", record)
    return record


def _unit(ledger, logical, system, user):
    """One verifier-role JSON call -> (object or None, status). A call that was not delivered costs this unit only
    (the ledger's own accounting decides when the run as a whole must stop)."""
    from skillopt.active_evidence.diagnosis import call_json
    from skillopt.continual_learning.ledger import LearningPending

    try:
        return call_json(ledger, logical, system, user, [])
    except LearningPending as exc:
        if str(exc) != "verifier_call_undelivered":
            raise
        return None, "undelivered"


def generate(value, record, panel, dev_questions, root, api, *, gate=None, kind=None):
    """Write, filter and review; returns (items, records). Raises whatever stops the run as a whole. ``kind`` is the
    benchmark's generator module (its filters, payloads and item form); the default is this one."""
    from concurrent.futures import ThreadPoolExecutor

    from skillopt.continual_learning.ledger import Ledger

    kind = kind or sys.modules[__name__]
    write_json(root / "model_service.json", seal(api.service))
    ledger = Ledger(root, value, api)
    sources = sorted(panel["tasks"], key=digest)
    records, candidates, seen = [], [], set(dev_questions)

    def batches(units, call):
        results = []
        for start in range(0, len(units), BATCH):
            chunk = units[start:start + BATCH]
            if gate is not None:
                gate()
            if start == 0:  # the first real reply is the health barrier
                results.append(call(chunk[0]))
                chunk = chunk[1:]
            with ThreadPoolExecutor(max_workers=BATCH) as pool:
                results += list(pool.map(call, chunk))
        return results

    def write(task):
        public = task["public"]
        return _unit(ledger, "taskgen:write:" + digest(task), record["writer_system"],
                     json.dumps(kind.write_payload(public), ensure_ascii=False, sort_keys=True))

    for task, (reply, status) in zip(sources, batches(sources, write)):
        proposed = reply.get("tasks") if type(reply) is dict else None
        entry = {"source_task_hash": digest(task), "write_status": status, "candidates": []}
        for candidate in (proposed if type(proposed) is list else [])[:record["per_task"]]:
            reason, fields = kind.admit(candidate, task["public"], seen)
            item = {"filter": reason}
            if reason is None:
                question = fields["question"]
                seen.add(kind.question_key(question))
                item.update({"id": "gen-" + hashlib.sha256((digest(task) + "\n" + question).encode()).hexdigest()[:16],
                             **fields})
                candidates.append((task, item))
            entry["candidates"].append(item)
        records.append(entry)

    def review(pair):
        task, item = pair
        return _unit(ledger, "taskgen:review:" + item["id"], record["reviewer_system"],
                     json.dumps(kind.review_payload(task["public"], item), ensure_ascii=False, sort_keys=True))

    items = []
    for (task, item), (reply, status) in zip(candidates, batches(candidates, review)):
        verdict = {k: reply.get(k) for k in kind.VERDICTS} if type(reply) is dict else {}
        item["review_status"], item["review"] = status, verdict
        item["accepted"] = all(verdict.get(k) is True for k in kind.VERDICTS)
        if item["accepted"]:
            items.append(kind.task_item(task["public"], item))
    return items, records, ledger


def run(output, *, fixture_api=None, fixture_gate=None, kind=None):
    """Generate once; lifecycle checks and publication happen while both locks are held; any stop is a durable
    pending result without an items file. ``kind``: see ``generate``."""
    from skillopt.active_evidence import protocol as ae
    from skillopt.continual_learning.ledger import BudgetExhausted, LearningPending, Ledger
    from skillopt.continual_learning.recovery import client_options
    from skillopt.validator_pilot.api import CachedAPI

    from scripts.run_active_evidence_panel_eval import bounded, network_gate, tunnel_probe

    kind = kind or sys.modules[__name__]
    out = safe_path(output)
    record = read_json(out / "generation.json", sealed=True)
    require(record["version"] == kind.VERSION and record["tool_sha256"] == kind.tool_sha256(), "Tool changed")
    value = read_json(out / "manifest.json", sealed=True)
    panel = read_json(out / "panel.json")
    require(value["record_hash"] == record["manifest_hash"] and _sha(out / "panel.json") == record["panel_sha256"]
            and sorted(digest(t) for t in panel["tasks"]) == record["source_task_hashes"], "Generation inputs changed")
    ae.validate_manifest(value, panel)
    dev_questions = sorted(kind.question_key(t["public"]["question"]) for t in read_json(record["dev_panel"])["tasks"])
    require(digest(dev_questions) == record["development_questions_hash"], "Development panel changed")
    fixture = value["model"]["provider"] == "fixture"
    require(fixture or (fixture_api is None and fixture_gate is None), "Natural run cannot inject fixtures")
    require(not fixture or fixture_api is not None, "Invalid fixture callbacks")
    root = out / "learning"
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        with output_lock(root):
            if (out / "result.json").exists():
                return read_json(out / "result.json", sealed=True)
            base = {"version": kind.VERSION, "generation_hash": record["record_hash"]}
            if (root / "started.json").exists():
                result = seal({**base, "status": "pending", "reason": "interrupted_generation_no_automatic_resume"})
                write_json(out / "result.json", result)
                return result
            items = records = ledger = None
            reason, gate = None, fixture_gate
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
                    proxy, host = model.get("proxy"), api.service["host"]
                    gate = network_gate(lambda: bounded(lambda: tunnel_probe(proxy, host), 20.0))
                try:
                    items, records, ledger = generate(value, record, panel, dev_questions, root, api, gate=gate,
                                                      kind=kind)
                finally:
                    api.close()
                if not fixture:
                    sequence.verify_service(root, record["learning_model_service"])
            except (LearningPending, BudgetExhausted) as exc:
                reason = "%s:%s" % (type(exc).__name__, str(exc)[:200])
            except Exception as exc:  # the type only: a provider message is never copied into the record
                reason = "error:" + type(exc).__name__
            costs = None
            if (root / "model_service.json").exists():
                reader = Ledger(root, value, None)
                costs = reader.snapshot()
                if reason is None and (costs.get("unclosed_calls") != 0 or reader.usage_blocks_completion(costs)):
                    reason = "usage_or_receipt_accounting_incomplete"
            if reason is None:
                write_json(out / "records.json", seal({"sources": records}))
                (out / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
                written = sum(len(r["candidates"]) for r in records)
                admitted = sum(c["filter"] is None for r in records for c in r["candidates"])
                result = seal({**base, "status": "completed", "reason": None, "items": len(items),
                               "items_sha256": _sha(out / "items.json"),
                               "records_hash": read_json(out / "records.json", sealed=True)["record_hash"],
                               "source_tasks": len(records),
                               "sources_without_reply": sum(type(r["write_status"]) is not str
                                                            or not r["write_status"].startswith("ok") for r in records),
                               "candidates_written": written, "candidates_after_filters": admitted,
                               "candidates_accepted": len(items), "costs": costs,
                               "network_gate": getattr(gate, "state", None)})
            else:
                result = seal({**base, "status": "pending", "reason": reason, "costs": costs,
                               "network_gate": getattr(gate, "state", None)})
            write_json(out / "result.json", result)
            return result


def family_map(output, kind=None):
    """{generated task id: family id} of a completed generation: one family per SOURCE training task (the questions
    written from the same snippets are siblings), in a namespace of its own."""
    _, _, result = check(output, kind)
    records = read_json(safe_path(output) / "records.json", sealed=True)
    require(records["record_hash"] == result["records_hash"], "Generation records changed")
    return {c["id"]: "generated-" + source["source_task_hash"][:24]
            for source in records["sources"] for c in source["candidates"] if c.get("accepted") is True}


def check(output, kind=None):
    """(items path, sealed generation record, sealed result) of a COMPLETED generation whose published files match."""
    kind = kind or sys.modules[__name__]
    out = safe_path(output)
    record = read_json(out / "generation.json", sealed=True)
    result = read_json(out / "result.json", sealed=True)
    path = out / "items.json"
    require(record["version"] == kind.VERSION and result.get("generation_hash") == record["record_hash"]
            and result.get("status") == "completed" and path.is_file() and _sha(path) == result["items_sha256"]
            and read_json(out / "records.json", sealed=True)["record_hash"] == result["records_hash"],
            "No completed generation with matching published files")
    return path, record, result


def main(argv=None, kind=None):
    kind = kind or sys.modules[__name__]
    parser = argparse.ArgumentParser(description=kind.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    for name in ("study", "split", "repo", "output"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--per-task", type=int, default=kind.PER_TASK)
    for name in ("run", "check"):
        sub.add_parser(name).add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        record = kind.prepare(args.study, args.split, args.output, args.repo, seed=args.seed, per_task=args.per_task)
        value = {k: record[k] for k in ("version", "seed", "source_tasks", "per_task", "record_hash")}
    elif args.command == "check":
        path, _, result = check(args.output, kind)
        value = {"items": str(path), "count": result["items"], "items_sha256": result["items_sha256"]}
    else:
        result = run(args.output, kind=kind)
        value = {k: result.get(k) for k in ("version", "status", "reason", "source_tasks", "candidates_written",
                                            "candidates_after_filters", "candidates_accepted", "record_hash")}
    print(json.dumps(value))
    return 0 if args.command != "run" or value["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
