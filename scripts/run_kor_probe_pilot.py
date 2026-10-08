"""KOR probe-stage pilot: can label-free applicability evidence guide a Skill rewrite?

Every arm shares F's completed SkillOpt S1 Skill as parent. A0 is the parent
itself; A1 is one mechanism-level rewrite whose prompt carries label-free
interference evidence from the evidence half of the sealed probes; A2 is the
same rewrite instruction without evidence. Run "a" puts No-Skill and A0 through
F's frozen budget-derived KOR solver over every probe; run "b" puts A1/A2
through the identical solver configuration over the held-out half only (odd
probe index per rule), so no arm is compared on a probe its evidence showed.
Probes are synthetic (public rule texts, new inputs) and scored only by the
label-free verifier: no official scorer, evaluation panel or gold label enters.
Every paid request has a durable intent; an open intent stops the pilot for
operator review and is never resampled. One history per arm: a direction-finding
pilot, not a significance, final or deployment claim.

Residual risk shared with F and every earlier run: the frozen client
(skillopt/validator_pilot/api.py, hash-pinned here and in the evaluation source)
may retry internally after a partial stream, so a discarded wrong-model attempt
can cost one extra call without appearing in the final receipt; this orchestrator
stops on every identity problem a receipt does show, but cannot see inside the
client's retries. Hardening the client is a separate, versioned change.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
from collections import Counter
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

VERSION = "kor-probe-rewrite-pilot-v8"
EXAMPLES = 8
SPAN_CHARS = 300
# Host code that shapes prompts, extraction, client requests and label-free scoring.
HOST_SOURCES = ("scripts/run_kor_probe_pilot.py", "skillopt/applicability/kor.py", "skillopt/applicability/kor_probes.py",
                "skillopt/continual_eval/backends.py", "skillopt/validator_pilot/api.py")
SYSTEM = ("You maintain a Skill: reusable guidance that is added to a solver's instructions for many different "
          "kinds of tasks (code, spreadsheets, questions, rule-based calculations and puzzles, interactive "
          "environments). Rewrite the Skill so that every rule states the underlying mechanism, the public task "
          "features that make it apply, the action to take, and the situations where it must not be applied. "
          "Preserve what helps the tasks the Skill was written for. Return only the rewritten Skill between "
          "<skill> and </skill>, at most {budget} UTF-8 bytes.")
CLOSING = "Rewrite the Skill now."


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _host_sources():
    root = Path(__file__).resolve().parents[1]
    return {name: _sha(root / name) for name in HOST_SOURCES}


def _sequence():
    """The frozen queue module next to this script; importable under F's derived source too."""
    spec = importlib.util.spec_from_file_location(
        "frozen_sequence", Path(__file__).resolve().with_name("continue_fivebench_baselines.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wrong_model(receipt, model):
    """Model identity is wrong or unverifiable: any model-identity error, another returned model, or a
    filtered response that does not prove the expected model over a complete stream (the frozen
    client's filter classification can mask an identity error)."""
    error, returned = str(receipt.get("error_type") or ""), receipt.get("returned_model")
    filtered = "filter" in error or receipt.get("finish_reason") in {"sensitive", "content_filter"}
    return ("model" in error or returned not in (None, model)
            or (filtered and (returned != model or receipt.get("stream_complete") is not True)))


def _open_calls(base):
    """Paid requests without a valid closure: each intent needs a sealed terminal for the
    same request under the same digest name, and no terminal may lack its intent."""
    base, problems = safe_path(base), []
    for intent in base.glob("**/call_intents/*.json"):
        try:
            request = {k: v for k, v in read_json(intent, sealed=True).items() if k != "record_hash"}
            record = read_json(intent.parent.parent / "calls" / intent.name, sealed=True)
            closed = record["request"] == request and digest(request) == intent.stem
        except (OSError, ValueError, KeyError, TypeError):
            closed = False
        if not closed:
            problems.append(str(intent))
    for calls in base.glob("**/calls"):
        if calls.parent.name != "api":  # the client's own cache lives in api/calls; every other terminal is audited
            problems += [str(t) for t in calls.glob("*.json") if not (calls.parent / "call_intents" / t.name).exists()]
    return sorted(problems)


class _SolverAbort(BaseException):
    """Stops every later solver submission after a failed call; never swallowed as an Exception."""


def _gated(base):
    """The frozen per-position call class, with one shared abort gate for the whole worker."""
    failed = []

    class GatedCalls(base):
        def __call__(self, system, user):
            if failed:
                raise _SolverAbort("an earlier solver call failed: " + failed[0])
            try:
                receipt = super().__call__(system, user)
            except Exception as exc:  # the intent stays open for operator review
                failed.append(type(exc).__name__)
                raise _SolverAbort("solver call failed: " + type(exc).__name__) from exc
            if _wrong_model(receipt, self.api.model):
                failed.append(str(receipt.get("error_type") or "unexpected_response_model"))  # sealed receipt kept
                raise _SolverAbort("the service answered with another model")
            return receipt
    return GatedCalls


# ----------------------------------------------------------------------- worker
def _worker_tools():
    from skillopt.continual_eval import core, runner

    return SimpleNamespace(source_root=Path(core.__file__).resolve().parents[2], freeze_plan=core.freeze_plan,
                           load_plan=core.load_plan, checkpoint_path=core.checkpoint_path,
                           register_checkpoint=core.register_checkpoint, load_checkpoint=core.load_checkpoint,
                           generate=runner.generate, runner=runner, sequence=_sequence())


def worker(request_path, output):
    """Runs inside F's verified budget-derived KOR evaluation source: solve only, never score."""
    tools = _worker_tools()
    request = read_json(request_path, sealed=True)
    require(tools.source_root == safe_path(request["evaluation_source"]), "Worker imported the wrong source")
    service = tools.sequence.verify_service(safe_path(request["reference_root"]))
    require(service == request["service"], "Frozen No-Skill model service changed")
    run = safe_path(request["run"])
    if not (run / "plan.json").exists():
        require(not run.exists(), "A partially created probe run needs operator review")
        tools.freeze_plan(request["config"], run)
    # On every entry, before any paid call: the current client is the frozen service.
    tools.sequence.check_client_service(request["repo"], request["config"]["model"], run / "api", service)
    plan = tools.load_plan(run)
    require(plan["config"] == request["config"], "Probe run configuration changed")
    require(not _open_calls(run / "predictions"), "Unclosed solver calls need operator review")
    for method, skill in request["policies"].items():
        if skill and not tools.checkpoint_path(run, method, "h0", 1).exists():
            tools.register_checkpoint(run, method, "h0", 1, skill, provenance=request["provenance"])
    for method, skill in request["policies"].items():  # every checkpoint before the first paid call
        checkpoint = tools.load_checkpoint(run, method, "h0", 1 if skill else 0, plan)
        require(checkpoint["skill_text"] == skill, "Probe checkpoint holds another policy")
    # Within this worker process only: the first failed solver call blocks every later submission.
    tools.runner.PositionCalls = _gated(tools.runner.PositionCalls)
    for method, skill in request["policies"].items():
        tools.generate(run, method=method, history="h0", stage=1 if skill else 0, benchmark="korbench",
                       repo=request["repo"], workers=request["workers"])
        require(not _open_calls(run / "predictions"), "Unclosed solver calls need operator review")
    tools.sequence.verify_service(run, service)
    tools.sequence.require_eval_handoff(run)
    write_json(output, seal({"run": str(run), "plan_hash": plan["record_hash"], "policies": request["policies"]}))


# ----------------------------------------------------------------- preparation
def _half(probe):
    return "evidence" if int(probe["task_id"].rsplit(":", 1)[1]) % 2 == 0 else "held_out"


def _panel(probes, path):
    """The probes as a frozen-solver panel; the reference sits in `answer` but is never scored."""
    panel = {"version": "continual-panel-v1", "benchmark": "korbench", "provenance": "natural",
             "dataset_revision": "kor-probes:" + probes["record_hash"],
             "tasks": [{"task_id": p["task_id"], "family_id": p["family_id"], "project_id": "",
                        "partition": "development", "public": p["public"],
                        "private": {"answer": p["private"]["reference"], "category": p["private"]["category"],
                                    "rule_id": p["private"]["rule_id"], "upstream_index": p["task_id"]}}
                       for p in probes["probes"]]}
    write_json(path, panel)
    return panel


def _parent(f_root, f_protocol):
    """F's completed SkillOpt S1 (bound by the accepted feedback pilot) and its learning budget."""
    from scripts.run_feedback_ablation_pilot import _arm_a, _budget

    manifest, stage, _, _ = _arm_a(f_root, f_protocol)
    require(stage["action"] == "selected_update" and stage["skill"], "The parent must be an accepted S1 update")
    return {"skill": stage["skill"], "stage_hash": stage["record_hash"], "budget": _budget(manifest),
            "max_tokens": manifest["budget"]["reflection_max_tokens"]}


def _check_probes(probes, f_protocol, reference):
    from skillopt.applicability import kor, kor_probes

    require(probes["version"] == kor_probes.VERSION and probes["verifier"] == kor.VERSION
            and probes["protocol_hash"] == f_protocol["record_hash"]
            and probes["panel_plan_hash"] == reference["plan_hash"], "Probes do not belong to this frozen study")
    ids = [p["task_id"] for p in probes["probes"]]
    require(len(ids) == len(set(ids)), "Duplicate probe ids")
    for probe in probes["probes"]:
        rule, question = probe["public"]["rule"], probe["public"]["question"]
        require(kor.verify(rule, question, probe["private"]["reference"])["status"] == "pass"
                and kor.verify(rule, question, probe["private"]["mutated"])["status"] == "fail",
                "A probe no longer qualifies under the current verifier")


def prepare(f_study, probes_path, output):
    from scripts import continue_fivebench_baselines as sequence
    from scripts.run_feedback_ablation_pilot import _evaluation_source

    f_root, root = safe_path(f_study), safe_path(output)
    require(not root.exists(), "A new pilot directory is required")
    f_protocol = read_json(f_root / "protocol.json", sealed=True)
    require(f_protocol["version"] == sequence.BUDGET_SEQUENCE and "skillopt" in f_protocol["methods"],
            "The parent must come from F's v4 study")
    parent = _parent(f_root, f_protocol)
    reference = f_protocol["references"]["korbench"]
    evaluation_changes = _evaluation_source(reference, parent["budget"])
    plan = read_json(safe_path(reference["root"]) / "plan.json", sealed=True)
    require(plan["record_hash"] == reference["plan_hash"], "No-Skill plan is not the frozen reference plan")
    probes = read_json(probes_path, sealed=True)
    _check_probes(probes, f_protocol, reference)
    held_out = {**probes, "probes": [p for p in probes["probes"] if _half(p) == "held_out"]}
    root.mkdir(parents=True, mode=0o700)
    write_json(root / "probes.json", probes)
    _panel(probes, root / "panels/all.json")
    _panel(held_out, root / "panels/held_out.json")
    configs = {}
    for name, panel, methods in (("a", "all", ["no_skill", "a0"]), ("b", "held_out", ["no_skill", "a1", "a2"])):
        config = deepcopy(plan["config"])
        config["panels"] = {k: None for k in config["panels"]}
        config["panels"]["korbench"] = str(safe_path(root / f"panels/{panel}.json"))
        config["methods"] = methods
        configs[name] = config
    protocol = seal({
        "version": VERSION, "f_protocol_hash": f_protocol["record_hash"], "f_study": str(f_root),
        "parent": {"stage_hash": parent["stage_hash"], "skill_sha256": hashlib.sha256(parent["skill"].encode()).hexdigest(),
                   "skill_bytes": len(parent["skill"].encode())},
        "parent_skill": parent["skill"], "budget": parent["budget"],
        "probes_sha256": _sha(root / "probes.json"), "probes_record_hash": probes["record_hash"],
        "panels_sha256": {name: _sha(root / f"panels/{name}.json") for name in ("all", "held_out")},
        "split": "evidence = even probe index per rule; arms compared on odd (held-out) indices",
        "reference": {k: reference[k] for k in ("root", "source", "evaluation_source", "python", "plan_hash",
                                                "model_service")},
        "evaluation_source_changes": evaluation_changes, "host_sources": _host_sources(), "configs": configs,
        "workers": f_protocol["config"]["workers"],
        "rewrite": {"model": f_protocol["model"], "client_options": f_protocol["learning_client_options"],
                    "service": f_protocol["learning_model_service"], "max_tokens": parent["max_tokens"],
                    "system_sha256": hashlib.sha256(SYSTEM.format(budget=parent["budget"]).encode()).hexdigest()},
        "examples": EXAMPLES, "histories_per_arm": 1, "scored_by": "label_free_verifier_only",
        "claim": "direction_finding_pilot_on_synthetic_probes", "deployment_authorized": False})
    write_json(root / "protocol.json", protocol)
    return protocol


def _load(output):
    from scripts.run_feedback_ablation_pilot import _evaluation_source

    root = safe_path(output)
    protocol = read_json(root / "protocol.json", sealed=True)
    require(protocol["version"] == VERSION and _sha(root / "probes.json") == protocol["probes_sha256"]
            and all(_sha(root / f"panels/{n}.json") == h for n, h in protocol["panels_sha256"].items()),
            "Pilot protocol, probes or panels changed")
    require(_host_sources() == protocol["host_sources"], "Host prompt, client or scoring sources changed")
    require(hashlib.sha256(SYSTEM.format(budget=protocol["budget"]).encode()).hexdigest()
            == protocol["rewrite"]["system_sha256"], "Rewrite prompt changed")
    require(hashlib.sha256(protocol["parent_skill"].encode()).hexdigest() == protocol["parent"]["skill_sha256"],
            "Parent Skill changed")
    require(_evaluation_source(protocol["reference"], protocol["budget"]) == protocol["evaluation_source_changes"],
            "Derived evaluation source changed")
    probes = read_json(root / "probes.json", sealed=True)
    panels = {name: read_json(root / f"panels/{name}.json")["tasks"] for name in ("all", "held_out")}
    return root, protocol, probes, panels


# --------------------------------------------------------------------- running
def _invoke(protocol, request_path, output, log):
    reference = protocol["reference"]
    source = reference["evaluation_source"]
    env = dict(os.environ, PYTHONPATH=str(safe_path(source)))
    command = [reference["python"], str(Path(__file__).absolute()), "worker",
               "--request", str(request_path), "--output", str(output)]
    with safe_path(log).open("ab") as handle:
        code = subprocess.run(command, cwd=source, env=env, stdout=handle, stderr=handle).returncode
    require(code == 0 and Path(output).is_file(), "Probe solver worker failed; inspect its private log, do not retry")
    return read_json(output, sealed=True)


def _request(root, protocol, name, policies, repo):
    reference = protocol["reference"]
    return seal({"run": str(safe_path(root / f"runs/{name}")), "config": protocol["configs"][name],
                 "policies": policies, "provenance": "kor_probe_pilot:" + protocol["record_hash"],
                 "repo": str(safe_path(repo)), "workers": protocol["workers"],
                 "evaluation_source": reference["evaluation_source"], "reference_root": reference["root"],
                 "service": reference["model_service"]})


def _phase(root, protocol, name, policies, repo):
    path, request = root / f"requests/{name}.json", _request(root, protocol, name, policies, repo)
    if path.exists():
        require(read_json(path, sealed=True) == request, "Existing probe request is stale")
    else:
        write_json(path, request)
    phase = _invoke(protocol, path, root / f"phase-{name}.json", root / f"phase-{name}.log")
    require(phase["run"] == request["run"] and phase["policies"] == policies
            and phase["plan_hash"] == read_json(safe_path(phase["run"]) / "plan.json", sealed=True)["record_hash"],
            "Probe phase record does not bind")
    return phase


def _predictions(run, config, policies, panel_tasks):
    """Recorded attempts bound plan -> checkpoint (declared policy) -> prediction -> frozen probe."""
    run = safe_path(run)
    plan = read_json(run / "plan.json", sealed=True)
    require(plan["config"] == config, "Probe run configuration differs from the frozen protocol")
    tasks = [t for t in plan["tasks"] if t["benchmark"] == "korbench"]
    hashes = {t["task_id"]: t["task_hash"] for t in tasks}
    require(len(hashes) == len(tasks) == len(plan["tasks"]) and hashes == {t["task_id"]: digest(t) for t in panel_tasks},
            "Probe run tasks differ from the frozen probe panel")
    require(not _open_calls(run / "predictions"), "Unclosed solver calls need operator review")
    by_key = {}
    for path in (run / "predictions").glob("*/prediction.json"):
        record = read_json(path, sealed=True)
        request = record["request"]
        key = (request["checkpoint_hash"], request["task_hash"], request["repeat"])
        require(key not in by_key, "Duplicate probe attempt")
        by_key[key] = record
    out = {}
    for method, skill in policies.items():
        stage = 1 if skill else 0
        checkpoint = read_json(run / f"checkpoints/{method}/h0/s{stage}.json", sealed=True)
        require(checkpoint["plan_hash"] == plan["record_hash"] and checkpoint["skill_text"] == skill
                and checkpoint["skill_hash"] == hashlib.sha256(skill.encode()).hexdigest(),
                "Probe checkpoint does not hold the declared policy")
        for task_id, task_hash in hashes.items():
            for repeat in range(plan["repeats"]):
                record = by_key.get((checkpoint["record_hash"], task_hash, repeat))
                require(record is not None and record["request"]["plan_hash"] == plan["record_hash"]
                        and record["request"]["benchmark"] == "korbench", "Missing or foreign probe attempt")
                out[(method, task_id, repeat)] = record["prediction"]
    return out, plan["repeats"]


def _verdict(probe, prediction):
    from skillopt.applicability import kor

    if prediction.get("status") != "available" or type(prediction.get("output")) is not str:
        return {"status": "unknown", "reason": "prediction_unavailable"}
    return kor.verify(probe["public"]["rule"], probe["public"]["question"], prediction["output"])


def _pair(skill, base):
    if skill not in {"pass", "fail"} or base not in {"pass", "fail"}:
        return "unknown"
    return "tie" if skill == base else "win" if skill == "pass" else "loss"


def _evidence(probes, predictions, repeats):
    """Label-free interference of A0 against No-Skill on the evidence half only."""
    from skillopt.applicability import kor

    counts, losses = {}, []
    for probe in sorted(probes, key=lambda p: (p["handler"], p["task_id"])):
        if _half(probe) != "evidence":
            continue
        for repeat in range(repeats):
            base = _verdict(probe, predictions[("no_skill", probe["task_id"], repeat)])
            with_skill = _verdict(probe, predictions[("a0", probe["task_id"], repeat)])
            pair = _pair(with_skill["status"], base["status"])
            counts.setdefault(probe["private"]["category"], Counter())[pair] += 1
            if pair == "loss":
                output = predictions[("a0", probe["task_id"], repeat)]["output"]
                span = (kor._puzzle_span if probe["handler"].startswith("puzzle") else kor._operation_span)(output)
                losses.append({"handler": probe["handler"], "category": probe["private"]["category"],
                               "question": probe["public"]["question"],
                               "answer": (span or "(no [[...]] answer)")[:SPAN_CHARS], "check": with_skill["reason"]})
    chosen, firsts = [], {}
    for loss in losses:  # one example per rule first, the categories taking turns ...
        firsts.setdefault(loss["category"], {}).setdefault(loss["handler"], loss)
    queues = [list(rules.values()) for _, rules in sorted(firsts.items())]
    while len(chosen) < EXAMPLES and any(queues):
        for queue in queues:
            if queue and len(chosen) < EXAMPLES:
                chosen.append(queue.pop(0))
    for loss in losses:  # ... then the rest in order, without repeating an identical example
        if len(chosen) < EXAMPLES and loss not in chosen:
            chosen.append(loss)
    return {"counts": {k: dict(sorted(v.items())) for k, v in sorted(counts.items())}, "examples": chosen,
            "losses": len(losses)}


def _user_prompt(skill, evidence):
    lines = ["Current Skill:", "<skill>", skill, "</skill>", ""]
    if evidence is not None:
        lines.append("Evidence from fresh rule-application tasks, checked against each task's public rules "
                     "(no answer keys). With the Skill versus without it:")
        for category, c in evidence["counts"].items():
            lines.append(f"- {category}: improved {c.get('win', 0)}, worsened {c.get('loss', 0)}, "
                         f"unchanged {c.get('tie', 0)}, undecided {c.get('unknown', 0)}")
        if evidence["examples"]:
            lines.append("Examples where the answer given with the Skill broke the task's public rules while the "
                         "answer without it satisfied them:")
            for index, example in enumerate(evidence["examples"], 1):
                lines += [f"[{index}] Task: {example['question']}", f"    Answer with the Skill: {example['answer']}",
                          f"    Public check failed: {example['check']}"]
        lines.append("")
    lines.append(CLOSING)
    return "\n".join(lines)


class _AuditedCall:
    """One frozen rewrite request with a durable intent before any paid call; every
    receipt, fresh or cached, must answer exactly this request on the frozen service."""

    KIND = "kor-probe-rewrite"

    def __init__(self, protocol, base, arm):
        rewrite = protocol["rewrite"]
        self.api, self.base = None, safe_path(base)
        self.identity = {"protocol": protocol["record_hash"], "arm": arm}
        self.max_tokens, self.model = rewrite["max_tokens"], rewrite["model"]["name"]
        self.service = {k: v for k, v in rewrite["service"].items() if k != "record_hash"}

    def request(self, system, user):
        value = {"identity": self.identity, "system": system, "user": user, "max_tokens": self.max_tokens}
        return value, digest(value)

    def _bound(self, record, system, user):
        request, key = self.request(system, user)
        expected = {"model": self.model, "system": system, "user": user, "kind": self.KIND, "key": key,
                    "max_tokens": self.max_tokens, "repeat": 0, "service": self.service}
        receipt = record["receipt"]
        require(record["request"] == request and receipt.get("request") == expected
                and receipt.get("request_hash") == digest(expected), "Rewrite receipt does not match its request")
        return receipt

    def receipt(self, record, system, user):
        """A request-bound receipt, refused (never classified) when another model answered."""
        receipt = self._bound(record, system, user)
        require(not _wrong_model(receipt, self.model), "The rewrite service answered with another model; operator review")
        return receipt

    def __call__(self, system, user):
        request, key = self.request(system, user)
        terminal, intent = self.base / f"calls/{key}.json", self.base / f"call_intents/{key}.json"
        if terminal.exists():
            return self.receipt(read_json(terminal, sealed=True), system, user)
        require(not intent.exists(), "Interrupted rewrite request; do not resample")
        require(self.api.model == self.model and self.api.service == self.service,
                "Rewrite client is not the frozen learning service")
        write_json(intent, seal(request))
        receipt = self.api.call(system, user, self.KIND, key, max_tokens=self.max_tokens, repeat=0)
        record = {"request": request, "receipt": receipt}
        self._bound(record, system, user)
        write_json(terminal, seal(record))  # the receipt is kept even when it is refused below
        return self.receipt(record, system, user)


def _client(repo, rewrite, cache):
    from skillopt.validator_pilot.api import CachedAPI

    model = rewrite["model"]
    return CachedAPI(Path(repo), Path(cache), provider=model["provider"], model=model["name"], workers=1,
                     reasoning_effort=model["reasoning_effort"], **model["transport"], **rewrite["client_options"],
                     **({"proxy": model["proxy"]} if "proxy" in model else {}))


def _extract(response, parent, budget):
    if response is None:
        return None, "no_response"
    found = re.search(r"<skill>(.*)</skill>", response, re.S)
    skill = found.group(1).strip() if found else ""
    if not skill:
        return None, "no_skill_block"
    if len(skill.encode()) > budget:
        return None, "over_budget"
    if skill == parent:
        return None, "unchanged"
    return skill, "rewritten"


def _classify(receipt, system, user):
    """The frozen solver client's response classification, applied to an already closed receipt."""
    from skillopt.continual_eval.backends import _response

    return _response(lambda s, u: receipt, system, user)


def _replay_rewrite(root, protocol, arm, system, user, record):
    """A recorded rewrite must reproduce from its single closed receipt and this exact request."""
    base = root / f"rewrites/{arm}"
    require(not _open_calls(base), "Interrupted rewrite request; do not resample")
    call = _AuditedCall(protocol, base, arm)
    expected, key = call.request(system, user)
    terminals = sorted((base / "calls").glob("*.json"))
    require(len(terminals) == 1 and terminals[0].stem == key, "Rewrite records belong to another request")
    response, costs, reason = _classify(call.receipt(read_json(terminals[0], sealed=True), system, user), system, user)
    skill, status = _extract(response, protocol["parent_skill"], protocol["budget"])
    require(record["identity"] == expected["identity"] and record["with_evidence"] == (arm == "a1")
            and record["user_sha256"] == hashlib.sha256(user.encode()).hexdigest()
            and record["system_sha256"] == protocol["rewrite"]["system_sha256"]
            and (record["response_reason"], record["costs"], record["skill"], record["reason"])
            == (reason, costs, skill, status)
            and record["status"] == ("completed" if skill else "pending"),
            "Recorded rewrite does not reproduce from its receipt")
    return record


def _rewrite(root, protocol, arm, evidence, repo):
    """One audited rewrite; a closed failure leaves the arm pending; an open call stops the pilot."""
    require((evidence is not None) == (arm == "a1"), "Only arm a1 receives evidence")
    base, path = root / f"rewrites/{arm}", root / f"rewrites/{arm}.json"
    system = SYSTEM.format(budget=protocol["budget"])
    user = _user_prompt(protocol["parent_skill"], evidence)
    if path.exists():
        return _replay_rewrite(root, protocol, arm, system, user, read_json(path, sealed=True))
    require(not _open_calls(base), "Interrupted rewrite request; do not resample")
    rewrite = protocol["rewrite"]
    call = _AuditedCall(protocol, base, arm)
    identity = call.identity
    _, key = call.request(system, user)
    require(all(p.stem == key for p in (base / "calls").glob("*.json")), "Rewrite records belong to another request")
    api = _client(repo, rewrite, base / "api")
    try:
        require(seal(api.service) == rewrite["service"], "Current client differs from the frozen learning service")
        call.api = api
        receipt = call(system, user)  # any exception here stops the pilot with its intent recorded
    finally:
        api.close()
    response, costs, reason = _classify(receipt, system, user)
    skill, status = _extract(response, protocol["parent_skill"], protocol["budget"])
    record = seal({"identity": identity, "with_evidence": arm == "a1",
                   "system_sha256": hashlib.sha256(system.encode()).hexdigest(),
                   "user_sha256": hashlib.sha256(user.encode()).hexdigest(), "response_reason": reason,
                   "costs": costs, "status": "completed" if skill else "pending", "reason": status, "skill": skill})
    write_json(path, record)
    return record


def _f_finished(protocol):
    """User decision (10/4): the paid probe stage starts only after F finished both methods."""
    from scripts import continue_fivebench_baselines as sequence

    for method in ("skillopt", "gepa"):
        path = safe_path(protocol["f_study"]) / method / "final.json"
        require(path.is_file(), f"F has not finished {method}; the paid probe stage waits")
        final = read_json(path, sealed=True)
        require(final["protocol_hash"] == protocol["f_protocol_hash"] and final["method"] == method
                and final["attempted_stages"] == len(sequence.BENCHMARKS), f"F's {method} final record does not bind")


def run(output, repo):
    root, protocol, probes, panels = _load(output)
    with output_lock(root):  # one orchestrator: paid requests are never issued twice concurrently
        _f_finished(protocol)
        require(not _open_calls(root / "rewrites"), "Interrupted rewrite request; do not resample")
        policies_a = {"no_skill": "", "a0": protocol["parent_skill"]}
        phase_a = _phase(root, protocol, "a", policies_a, repo)
        predictions, repeats = _predictions(phase_a["run"], protocol["configs"]["a"], policies_a, panels["all"])
        evidence = _evidence(probes["probes"], predictions, repeats)
        write_json(root / "evidence.json", seal({"protocol_hash": protocol["record_hash"], **evidence}))
        rewrites = {arm: _rewrite(root, protocol, arm, evidence if arm == "a1" else None, repo) for arm in ("a1", "a2")}
        policies_b = {arm: r["skill"] for arm, r in rewrites.items() if r["status"] == "completed"}
        phase_b = _phase(root, protocol, "b", policies_b, repo) if policies_b else None
        result = seal({"protocol_hash": protocol["record_hash"], "phase_a": phase_a["record_hash"],
                       "phase_b": phase_b["record_hash"] if phase_b else None,
                       "rewrites": {arm: r["record_hash"] for arm, r in rewrites.items()},
                       "pending_arms": sorted(arm for arm, r in rewrites.items() if r["status"] != "completed")})
        write_json(root / "result.json", result)
    return result


# ---------------------------------------------------------------------- report
def _validated(root, protocol, probes, panels):
    """Read-only replay of the whole chain: phases, predictions, evidence and rewrites."""
    result = read_json(root / "result.json", sealed=True)
    require(result["protocol_hash"] == protocol["record_hash"], "Result belongs to another pilot")
    require(not _open_calls(root), "Unclosed paid requests need operator review")
    policies_a = {"no_skill": "", "a0": protocol["parent_skill"]}

    def phase(name, policies):
        request = read_json(root / f"requests/{name}.json", sealed=True)
        record = read_json(root / f"phase-{name}.json", sealed=True)
        require(record["record_hash"] == result[f"phase_{name}"]
                and {k: v for k, v in request.items() if k not in {"repo", "record_hash"}}
                == {k: v for k, v in _request(root, protocol, name, policies, request["repo"]).items()
                    if k not in {"repo", "record_hash"}}
                and record["run"] == request["run"] and record["policies"] == policies
                and record["plan_hash"] == read_json(safe_path(record["run"]) / "plan.json", sealed=True)["record_hash"],
                "Probe phase records do not bind to the protocol")
        return record

    predictions, repeats = _predictions(phase("a", policies_a)["run"], protocol["configs"]["a"], policies_a,
                                        panels["all"])
    evidence = _evidence(probes["probes"], predictions, repeats)
    require(read_json(root / "evidence.json", sealed=True) == seal({"protocol_hash": protocol["record_hash"], **evidence}),
            "Recorded evidence differs from the recorded run")
    system = SYSTEM.format(budget=protocol["budget"])
    rewrites = {arm: _replay_rewrite(root, protocol, arm, system,
                                     _user_prompt(protocol["parent_skill"], evidence if arm == "a1" else None),
                                     read_json(root / f"rewrites/{arm}.json", sealed=True)) for arm in ("a1", "a2")}
    require({arm: r["record_hash"] for arm, r in rewrites.items()} == result["rewrites"], "Rewrite records changed")
    policies_b = {arm: r["skill"] for arm, r in rewrites.items() if r["status"] == "completed"}
    require((result["phase_b"] is None) == (not policies_b), "Held-out phase does not match the rewrites")
    if policies_b:
        extra, _ = _predictions(phase("b", policies_b)["run"], protocol["configs"]["b"], policies_b, panels["held_out"])
        predictions.update(extra)
    return predictions, repeats, rewrites, evidence, sorted(policies_b)


def report(output):
    root, protocol, probes, panels = _load(output)
    predictions, repeats, rewrites, evidence, arms_b = _validated(root, protocol, probes, panels)
    held = [p for p in probes["probes"] if _half(p) == "held_out"]
    by_id = {p["task_id"]: p for p in probes["probes"]}
    verdicts = {key: _verdict(by_id[key[1]], value)["status"] for key, value in predictions.items()}
    arms = ["no_skill", "a0", *arms_b]
    comparisons = {}
    for i, left in enumerate(arms):
        for right in arms[:i]:
            table = {}
            for probe in held:
                for repeat in range(repeats):
                    pair = _pair(verdicts[(left, probe["task_id"], repeat)], verdicts[(right, probe["task_id"], repeat)])
                    for label in (probe["private"]["category"], "all"):
                        table.setdefault(label, Counter())[pair] += 1
            comparisons[f"{left}_vs_{right}"] = {k: dict(sorted(v.items())) for k, v in sorted(table.items())}
    return seal({"version": VERSION + "-report", "protocol_hash": protocol["record_hash"],
                 "held_out_positions": len(held) * repeats, "evidence": {k: evidence[k] for k in ("counts", "losses")},
                 "rewrites": {arm: {"status": r["status"], "reason": r["reason"], "with_evidence": r["with_evidence"],
                                    "skill_bytes": len(r["skill"].encode()) if r["skill"] else None,
                                    "skill_sha256": hashlib.sha256(r["skill"].encode()).hexdigest() if r["skill"] else None,
                                    "costs": r["costs"]} for arm, r in rewrites.items()},
                 "comparisons_on_held_out": comparisons, "scored_by": "label_free_verifier_only",
                 "histories_per_arm": 1, "claim": protocol["claim"], "significance_claimed": False,
                 "deployment_authorized": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "worker", "report"))
    parser.add_argument("--output", help="Pilot directory (new for prepare)")
    parser.add_argument("--f-study")
    parser.add_argument("--probes")
    parser.add_argument("--repo")
    parser.add_argument("--request")
    parser.add_argument("--export", help="New report directory outside the pilot")
    args = parser.parse_args()
    if args.command == "worker":
        worker(args.request, args.output)
    elif args.command == "prepare":
        require(args.f_study and args.probes and args.output, "--f-study, --probes and --output required")
        print(json.dumps({"protocol_hash": prepare(args.f_study, args.probes, args.output)["record_hash"]}))
    elif args.command == "run":
        require(args.repo and args.output, "--repo and --output required")
        print(json.dumps(run(args.output, args.repo)))
    else:
        require(args.export and args.output, "--export and --output required")
        export, pilot = safe_path(args.export), safe_path(args.output)
        inside = any(p.exists() and p.samefile(pilot) for p in (export, *export.parents))
        require(not export.exists() and not inside, "Use a new export outside the pilot")
        value = report(args.output)
        export.mkdir(parents=True, mode=0o700)
        write_json(export / "report.json", value)
        print(json.dumps({"record_hash": value["record_hash"]}))


if __name__ == "__main__":
    main()
