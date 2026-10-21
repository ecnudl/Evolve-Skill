"""Paired evaluation of FROZEN Skill texts on an external task panel through the learning-v11 call path.

Evaluation only: nothing is learned, selected or deployed here. Every named Skill text solves every task of the
panel once, under its own rollout key, with the frozen solver model, ledger, adapter and scorer of the
``active_evidence`` package (the same call path as every v11 development evaluation). The arms are interleaved:
the tasks are shuffled once (seeded) and cut into chunks, and inside chunk ``c`` the arms run in the given order
rotated by ``c``, so a service drift during the run does not line up with one arm.

The panel is an EXTERNAL sample (e.g. ``scripts/make_searchqa_fresh_sample.py``): ``prepare`` refuses a panel that
shares a task id or a family with any partition of the canonical split, and a Skill whose learning stage trained
on a family of the panel. The tasks carry the package's ``development`` label because this is development-stage
evaluation data (never a final evaluation): once a block has been read here it is used development evidence.

A Skill is given as ``name=none`` (the empty Skill), ``name=f:<absolute text file>`` (a fixed operator-supplied
text) or ``name=g:<completed G stage directory>`` (the Skill that stage's ``learned.json`` records: for a v11
``scalar / none`` stage the one-step update adopted without selection, for a validation-gated chain stage the
Skill it deployed).

Usage:
  python scripts/run_active_evidence_panel_eval.py prepare --study <F study> --split <split manifest> \\
      --repo <credential repo> --benchmark searchqa --items <items.json> --revision <dataset revision> \\
      --skill empty=none --skill generic=f:/abs/generic.md --skill l1=g:<stage dir> ... --output <new dir>
  python scripts/run_active_evidence_panel_eval.py run --output <prepared dir>
  python scripts/run_active_evidence_panel_eval.py status --output <dir>   # exit 0 completed, 3 pending, 2 invalid
  python scripts/run_active_evidence_panel_eval.py report --output <dir> [<dir> ...] \\
      [--contrast a-b ...] [--group name=arm1,arm2,... ...]

``report`` is zero-call. ``--contrast a-b`` reads arm (or group) ``a`` minus arm (or group) ``b`` on the jointly
known tasks of all given runs; a group is the per-task MEAN pass rate of its arms (learning histories).
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import random
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

VERSION = "active-evidence-panel-eval-v1"
ARMS = {"feedback": "scalar", "post_update": "none"}  # the manifest's formal arm: no update is ever proposed here
NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")
FIRST_ROLLOUT = 3000  # arm k solves under rollout key 3000 + k (step keys are 0..99, challenge keys 1000..)
MAX_ARMS = 64


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _import_panel(benchmark, items, revision):
    from skillopt.continual_eval import datasets

    require(benchmark in ("searchqa", *tool.EXTENSION_BENCHMARKS),
            "Only SearchQA and the extension benchmarks' item files are importable here")
    return getattr(datasets, "import_" + benchmark)(items, partition="development", revision=revision)


def verified_stage(protocol, previous, split_hash):
    """(stage record, learned record) of a completed G stage whose Skill may be read: the checks the stage tool
    makes before it chains from a stage (``parent_skill`` ``g:``) -- same study and split, sealed manifest / panel /
    result bound to the stage record, the learned Skill equal to the sealed result's, and every retained learning
    artifact present with its recorded hash and nothing unrecorded beside it -- except the tool-compatibility gate:
    that gate decides which stages THIS tool version may operate on, while a sealed Skill text can be read from a
    stage prepared by any earlier tool version (the hash is recorded in the provenance)."""
    stage, learned = tool._completed_stage(protocol, previous, split_hash)
    value = read_json(previous / "manifest.json", sealed=True)
    result = read_json(previous / "learning/result.json", sealed=True)
    tool._verify_learning_evidence(previous, value, result)
    require(stage["version"] == tool.VERSION and value["record_hash"] == stage["manifest_hash"]
            and tool._sha(previous / "panel.json") == stage["panel_sha256"]
            and learned["learning_result_hash"] == result["record_hash"]
            and learned["status"] == result["status"] == "completed"
            and learned["skill"] == (result["candidate_skill"] if learned["action"] == "selected_update"
                                     else value["parent_skill"])
            and (learned["action"] == "selected_update") == (result["candidate_skill"] != value["parent_skill"]),
            "The stage is not a completed, consistently recorded stage with its learning evidence intact")
    return stage, learned


def skill_spec(protocol, spec, split_hash, panel_families):
    """(name, text, provenance) of one ``name=none | name=f:<abs file> | name=g:<completed stage dir>``."""
    from skillopt.continual_learning.contracts import check_skill
    from skillopt.continual_learning.recovery import POLICY_V10

    name, separator, where = spec.partition("=")
    require(separator == "=" and NAME.fullmatch(name) is not None and (where == "none" or where[:2] in {"f:", "g:"}),
            "A Skill is given as name=none, name=f:<absolute text file> or name=g:<completed G stage directory>")
    if where == "none":
        text, source = "", {"action": "empty_skill"}
    elif where.startswith("f:"):
        require(Path(where[2:]).is_absolute(), "A fixed Skill text is given by an absolute path")
        path = safe_path(where[2:])
        require(path.is_file(), "A fixed Skill text is an existing file")
        text = path.read_text(encoding="utf-8")
        require(text.strip() != "", "A fixed Skill text is not empty (the empty Skill is name=none)")
        source = {"action": "fixed_text", "file": str(path)}
    else:
        previous = safe_path(where[2:])
        stage, learned = verified_stage(protocol, previous, split_hash)
        require(not set(stage.get("train_families", [])) & panel_families,
                "The Skill's learning stage trained on a family of this panel")
        text = learned["skill"]
        source = {"action": "stage:" + learned["action"], "stage": previous.name, "stage_hash": stage["record_hash"],
                  "learned_hash": learned["record_hash"], "stage_tool_sha256": stage.get("tool_sha256"),
                  "benchmark": stage["benchmark"], "method": stage["method"],
                  "learning_version": stage["learning_version"], "arms": stage.get("arms"),
                  "parent": Path(stage["parent"][2:]).name if str(stage.get("parent"))[:2] == "f:" else stage.get("parent"),
                  "parent_skill_sha256": stage.get("parent_skill_sha256"), "seed": stage.get("seed"),
                  "train_tasks": stage.get("train_tasks"), "selection_tasks": stage.get("selection_tasks")}
    check_skill(text, POLICY_V10["skill_budget_bytes"])
    return name, text, {**source, "skill_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "skill_bytes": len(text.encode())}


def schedule(task_hashes, arms, *, seed, chunk):
    """[(arm index, [task hash, ...]), ...]: seeded task order cut into chunks; arm order rotated per chunk."""
    order = sorted(task_hashes)
    random.Random(seed).shuffle(order)
    plan = []
    for number, start in enumerate(range(0, len(order), chunk)):
        tasks = order[start:start + chunk]
        for offset in range(arms):
            plan.append(((number + offset) % arms, tasks))
    return plan


def prepare(study, split_path, output, repo, *, benchmark, items, revision, skills, seed, chunk):
    from skillopt.active_evidence import PROTOCOL
    from skillopt.active_evidence import protocol as ae

    version, policy, budget = tool._protocol("v11")
    require(benchmark in tool.API_ONLY, "This tool runs API-only domains")
    root, protocol = tool._study(study)
    out = safe_path(output)
    tool._outside(out, root, protocol, [split_path])
    require(not out.exists(), "Use a new directory")
    split = read_json(split_path, sealed=True)
    tool.check_split(split, protocol, benchmark)
    tool.check_evaluation_block(protocol, benchmark, items)
    panel = _import_panel(benchmark, items, revision)
    families = {t["family_id"] for t in panel["tasks"]}
    require(len(families) == len(panel["tasks"]) >= 1, "One task per family is expected of an external panel")
    canonical = [e for part in split["splits"][benchmark].values() for e in part]
    require(not {str(t["task_id"]) for t in panel["tasks"]} & {str(e["task_id"]) for e in canonical}
            and not families & {e["family_id"] for e in canonical},
            "The panel shares a task or a family with the canonical split: it is not an external sample")
    require(1 <= len(skills) <= MAX_ARMS and type(chunk) is int and chunk >= 1, "Between 1 and 64 Skills; chunk >= 1")
    parsed = [skill_spec(protocol, spec, split["record_hash"], families) for spec in skills]
    require(len({name for name, _, _ in parsed}) == len(parsed), "Skill names are unique")
    positions = len(panel["tasks"]) * len(parsed)
    budget = {**budget, "max_metric_calls": positions + 64, "max_api_calls": 2 * positions + 64,
              "max_reported_tokens": max(budget["max_reported_tokens"], 20_000 * positions)}
    value = ae.manifest(panel, step_families=sorted(families), challenge_families=[],
                        model=deepcopy(protocol["model"]), budget=budget,
                        runtime=protocol["roles"][benchmark]["runtime"], parent_skill="", seed=seed, arms=ARMS,
                        limits=ae.effective_limits(ARMS, 0))
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "panel.json", panel)
    write_json(out / "manifest.json", value)
    texts = seal({"skills": [{"name": name, "skill": text} for name, text, _ in parsed]})
    write_json(out / "skills.json", texts)
    record = seal({"version": VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
                   "split": str(safe_path(split_path)), "split_hash": split["record_hash"], "benchmark": benchmark,
                   "repo": str(safe_path(repo)), "items": str(safe_path(items)), "items_sha256": _sha(items),
                   "dataset_revision": revision, "tasks": len(panel["tasks"]),
                   "skills": [{"name": name, "rollout": FIRST_ROLLOUT + k, **source}
                              for k, (name, _, source) in enumerate(parsed)],
                   "skills_hash": texts["record_hash"], "seed": seed, "chunk": chunk,
                   "schedule": "seeded task order cut into chunks; arm order rotated by the chunk number",
                   "method": tool.ACTIVE_EVIDENCE, "learning_version": PROTOCOL, "base_learning_version": version,
                   "recovery_policy": policy, "budget": budget,
                   "client_options": {"delivery_retry_policy": _retry_policy(version)},
                   "learning_model_service": protocol["learning_model_service"],
                   "native_lock": protocol["config"]["native_lock"],
                   "manifest_hash": value["record_hash"], "panel_sha256": _sha(out / "panel.json"),
                   "tool_sha256": _sha(Path(__file__)), "stage_tool_sha256": _sha(Path(tool.__file__)),
                   "learning_sources": value["source_identity"],
                   "package_sources": value["active_evidence"]["package_sources"],
                   "data_scope": "external_sample_disjoint_from_the_canonical_split__development_stage_evaluation_"
                                 "only__nothing_learned_selected_or_deployed",
                   "deployment_authorized": False})
    write_json(out / "eval.json", record)
    return record


def _retry_policy(version):
    from skillopt.continual_learning.recovery import RETRY_POLICIES

    return RETRY_POLICIES[version]


def _load(output):
    from skillopt.active_evidence import protocol as ae

    out = safe_path(output)
    record = read_json(out / "eval.json", sealed=True)
    require(record["version"] == VERSION and record["tool_sha256"] == _sha(Path(__file__)), "Tool changed")
    _, protocol = tool._study(record["study"])
    require(protocol["record_hash"] == record["protocol_hash"], "Study changed")
    value = read_json(out / "manifest.json", sealed=True)
    panel = read_json(out / "panel.json")
    texts = read_json(out / "skills.json", sealed=True)
    require(value["record_hash"] == record["manifest_hash"] and _sha(out / "panel.json") == record["panel_sha256"]
            and texts["record_hash"] == record["skills_hash"], "Evaluation inputs changed")
    ae.validate_manifest(value, panel)
    skills = [(entry["name"], entry["skill"]) for entry in texts["skills"]]
    require([name for name, _ in skills] == [s["name"] for s in record["skills"]]
            and all(hashlib.sha256(text.encode()).hexdigest() == s["skill_sha256"]
                    for (_, text), s in zip(skills, record["skills"])), "Skill texts changed")
    return out, record, value, panel, skills


class NetworkUnavailable(Exception):
    """The connectivity gate ran out of patience before a batch (no call of that batch was submitted)."""


def read_header_block(receive, *, limit=4096):
    """The header block of a reply (up to and including its blank line), read one byte at a time through
    ``receive(max_bytes)`` so that nothing after it is consumed; None when the peer closed the connection or
    ``limit`` bytes arrived before the block was complete (a truncated or oversized reply is never accepted)."""
    reply = b""
    while not (reply.endswith(b"\r\n\r\n") or reply.endswith(b"\n\n")):
        if len(reply) >= limit:
            return None
        piece = receive(1)
        if not piece:
            return None
        reply += piece
    return reply


def status_line(block):
    """The first line of a header block (None stays None)."""
    return None if block is None else block.split(b"\n", 1)[0].rstrip(b"\r")


def connect_established(line):
    """True only for a complete ``HTTP/1.x 200 ...`` status line (the three-character status token ``200``)."""
    if line is None:
        return False
    tokens = line.decode("latin1", "replace").split()
    return len(tokens) >= 2 and tokens[0] in ("HTTP/1.0", "HTTP/1.1") and tokens[1] == "200"


def tunnel_probe(proxy, host, *, timeout=10, context=None):
    """One connectivity probe, no model call, no HTTP request to the provider and no credential: can a TLS
    session with the provider host be established -- through the credential-free gateway of the frozen model
    record (an HTTP CONNECT tunnel) when there is one? The gateway must answer the CONNECT with a complete status
    line whose status is exactly 200, and then the TLS handshake with the provider must complete. (On 2026-10-12
    the calls failed in exactly this phase: the gateway kept answering 200 while handshakes through the tunnel
    timed out for a minute or two, so a CONNECT-level probe stayed green.)"""
    import socket
    import ssl

    try:
        context = context or ssl.create_default_context()
        if proxy is None:
            with socket.create_connection((host, 443), timeout=timeout) as connection:
                with context.wrap_socket(connection, server_hostname=host):
                    return True
        require("@" not in proxy, "Only a credential-free gateway is probed")
        name, _, port = proxy.split("//")[-1].rstrip("/").partition(":")
        with socket.create_connection((name, int(port or 3128)), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(("CONNECT %s:443 HTTP/1.1\r\nHost: %s:443\r\n\r\n" % (host, host)).encode())
            if not connect_established(status_line(read_header_block(connection.recv))):
                return False
            with context.wrap_socket(connection, server_hostname=host):
                return True
    except (OSError, ssl.SSLError):
        return False


def bounded(function, seconds):
    """``function()`` in a daemon thread; False when it has not returned True within ``seconds`` (name resolution
    is outside a socket's own timeout, so the whole probe is bounded here)."""
    import threading

    box = []
    worker = threading.Thread(target=lambda: box.append(function()), daemon=True)
    worker.start()
    worker.join(seconds)
    return bool(box and box[0] is True)


def network_gate(probe, *, quiet=3, interval=10.0, patience=3600.0, sleep=None, clock=None):
    """A callable that returns once the network is reachable: at once when a probe succeeds, otherwise after
    ``quiet`` consecutive successful probes. The deadline runs from the moment the gate is entered and covers the
    probes themselves; when it has passed, the gate raises ``NetworkUnavailable`` -- also when connectivity came
    back only after the deadline (the batch is then not released). It only delays the submission of a batch; it
    never changes a call, a retry or the accounting."""
    import time

    sleep, clock = sleep or time.sleep, clock or time.monotonic
    state = {"waits": 0, "waited_seconds": 0.0, "failed_probes": 0}

    def gate():
        start = clock()
        if probe() and clock() - start <= patience:
            return
        state["waits"] += 1
        streak = 0
        try:
            while streak < quiet:
                if clock() - start > patience:
                    raise NetworkUnavailable("no connectivity for %d seconds" % patience)
                sleep(interval)
                if probe():
                    streak += 1
                else:
                    streak, state["failed_probes"] = 0, state["failed_probes"] + 1
            if clock() - start > patience:  # recovered too late: the batch is not released
                raise NetworkUnavailable("no connectivity for %d seconds" % patience)
        finally:
            state["waited_seconds"] += clock() - start

    gate.state = state
    return gate


def evaluate(value, panel, skills, root, *, seed, chunk, api, fixture_evaluate=None, gate=None):
    """Solve every (task, Skill) position in the interleaved order. Returns nothing: the sealed evaluation records
    on disk are the result (``collect``), so whatever stops this loop, what was solved stays reportable. ``gate``
    (optional) is called before every batch and may only delay it (the connectivity gate)."""
    from skillopt.active_evidence.protocol import step_items
    from skillopt.continual_learning.gepa import Adapter
    from skillopt.continual_learning.ledger import Ledger

    write_json(root / "model_service.json", seal(api.service))
    ledger = Ledger(root, value, api)
    adapter = Adapter(value, root, ledger, fixture_evaluate=fixture_evaluate)
    items = {digest(item["task"]): item for item in step_items(value, panel)}
    first = True
    for arm, tasks in schedule(list(items), len(skills), seed=seed, chunk=chunk):
        batch = [items[h] for h in tasks]
        parts = [batch[:1], batch[1:]] if first else [batch]  # the first real reply is the health barrier
        first = False
        for part in parts:
            if part:
                if gate is not None:
                    gate()
                adapter.evaluate_rows(part, {"skill": skills[arm][1]}, rollout=FIRST_ROLLOUT + arm)


def collect(value, panel, skills, root, *, reason, network_gate_state=None):
    """The sealed result, read back from the durable records (sealed evaluations, receipts, intents): positions,
    accounting and the inventory of the retained evidence. ``completed`` needs every position, closed evaluations
    and calls, complete usage accounting and no stop reason."""
    from skillopt.active_evidence.protocol import step_items
    from skillopt.active_evidence.stage import stage_artifacts
    from skillopt.continual_learning.ledger import Ledger
    from skillopt.continual_learning.skillopt import _evaluations_closed

    items = {digest(item["task"]): item for item in step_items(value, panel)}
    names = [name for name, _ in skills]
    arm = {FIRST_ROLLOUT + k: (name, digest({"skill": text})) for k, (name, text) in enumerate(skills)}
    status, evidence = {h: {} for h in items}, {h: {} for h in items}
    for path in sorted((root / "evaluations").glob("*.json")) if (root / "evaluations").exists() else []:
        row = read_json(path, sealed=True)
        request = row["request"]
        name, candidate = arm.get(request.get("rollout"), (None, None))
        require(request["manifest_hash"] == value["record_hash"] and name is not None
                and request["candidate_hash"] == candidate and request["task_hash"] in items
                and name not in status[request["task_hash"]], "Foreign or repeated evaluation record")
        status[request["task_hash"]][name] = (row["score"]["status"] if row["score"]["status"] in ("pass", "fail")
                                              else "unknown")
        evidence[request["task_hash"]][name] = row["record_hash"]
    summary = {name: {s: sum(status[h].get(name) == s for h in items) for s in ("pass", "fail", "unknown")}
               for name in names}
    for name in names:
        summary[name]["not_run"] = sum(name not in status[h] for h in items)
    costs = artifacts = None
    closed = blocked = False
    if (root / "model_service.json").exists():
        ledger = Ledger(root, value, None)  # read-only
        costs = ledger.snapshot()
        closed = _evaluations_closed(root) and costs.get("unclosed_calls") == 0
        blocked = bool(ledger.usage_blocks_completion(costs))
        artifacts = stage_artifacts(root, ledger)
    every = all(len(status[h]) == len(names) for h in items)
    if reason is None and not every:
        reason = "positions_missing"
    if reason is None and not closed:
        reason = "open_evaluation_or_call"
    if reason is None and blocked:
        reason = "usage_or_receipt_accounting_incomplete"
    return seal({"version": VERSION, "manifest_hash": value["record_hash"],
                 "status": "completed" if reason is None else "pending", "reason": reason,
                 "arms": names, "summary": summary,
                 "positions": [{"task_hash": h, "family_id": items[h]["task"]["family_id"], "status": status[h],
                                "evidence": evidence[h]} for h in sorted(items)],
                 "costs": costs, "artifacts": artifacts, "evaluations_closed": closed,
                 "usage_blocks_completion": blocked, "resume_supported": False,
                 "network_gate": network_gate_state,
                 "note": "development-stage evaluation of frozen Skill texts; nothing learned, selected or deployed"})


def fixture_guard(provider, fixture_api, fixture_evaluate):
    """True for a fixture run. A natural run can inject NEITHER hook (an injected scorer alone would fabricate
    scores without a solver call); a fixture run needs both."""
    fixture = provider == "fixture"
    require(fixture or (fixture_api is None and fixture_evaluate is None), "Natural run cannot inject fixtures")
    require(not fixture or (fixture_api is not None and fixture_evaluate is not None), "Invalid fixture callbacks")
    return fixture


def run(output, *, fixture_api=None, fixture_evaluate=None, fixture_gate=None):
    """Run one prepared evaluation. Every check of an earlier attempt and the publication of the result happen
    while BOTH locks are held; any stop -- an interrupted earlier attempt, a pending ledger, an ordinary exception
    -- ends in a durable pending result built from what is on disk. Nothing is ever resumed."""
    from skillopt.continual_learning.ledger import BudgetExhausted, LearningPending
    from skillopt.continual_learning.recovery import client_options
    from skillopt.validator_pilot.api import CachedAPI

    out, record, value, panel, skills = _load(output)
    fixture = fixture_guard(value["model"]["provider"], fixture_api, fixture_evaluate)
    require(fixture or fixture_gate is None, "Natural run cannot inject fixtures")
    root = out / "learning"
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)  # one paid workload of this study family at a time
        with output_lock(root):
            if (out / "result.json").exists():
                return read_json(out / "result.json", sealed=True)
            if (root / "started.json").exists():
                return finish(out, record, collect(value, panel, skills, root,
                                                   reason="interrupted_evaluation_no_automatic_resume"))
            reason, gate = None, fixture_gate
            try:
                sequence = None if fixture else tool._sequence()
                if not fixture:
                    sequence.check_client_service(record["repo"], value["model"], out / "client-check",
                                                  record["learning_model_service"],
                                                  client_options=record["client_options"])
                write_json(root / "started.json", seal({"eval_hash": record["record_hash"]}))
                if fixture:
                    api = fixture_api
                else:
                    model = value["model"]
                    api = CachedAPI(Path(record["repo"]), root / "api", provider=model["provider"],
                                    model=model["name"], workers=1, reasoning_effort=model["reasoning_effort"],
                                    **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                                    **({"proxy": model["proxy"]} if "proxy" in model else {}), **client_options(value))
                if not fixture:
                    # delay a batch while the provider cannot be reached (connect phase); calls are never altered
                    proxy, host = value["model"].get("proxy"), api.service["host"]
                    gate = network_gate(lambda: bounded(lambda: tunnel_probe(proxy, host), 20.0))
                try:
                    evaluate(value, panel, skills, root, seed=record["seed"], chunk=record["chunk"], api=api,
                             fixture_evaluate=fixture_evaluate, gate=gate)
                finally:
                    api.close()
                if not fixture:
                    sequence.verify_service(root, record["learning_model_service"])
            except (LearningPending, BudgetExhausted) as exc:
                reason = "%s:%s" % (type(exc).__name__, str(exc)[:200])
            except Exception as exc:  # anything else: durable pending record, the type only (no message text)
                reason = "error:" + type(exc).__name__
            return finish(out, record, collect(value, panel, skills, root, reason=reason,
                                               network_gate_state=getattr(gate, "state", None)))


def finish(out, record, result):
    """Bind the evaluation's result to its sealed preparation record and write it."""
    result = seal({**{k: v for k, v in result.items() if k != "record_hash"}, "eval_hash": record["record_hash"],
                   "operated_by_tool_sha256": _sha(Path(__file__))})
    write_json(out / "result.json", result)
    return result


def status(output):
    """(exit code, summary) of a run directory: 0 a completed result, 3 a durable PENDING result (sealed and bound
    to this directory's preparation record -- the only state after which a block may be repeated in a new
    directory), 2 anything else (no result, or a result that is not this evaluation's)."""
    out = safe_path(output)
    try:
        record, result = read_json(out / "eval.json", sealed=True), read_json(out / "result.json", sealed=True)
        value = read_json(out / "manifest.json", sealed=True)
        require(record["version"] == VERSION and result.get("eval_hash") == record["record_hash"]
                and value["record_hash"] == record["manifest_hash"] == result.get("manifest_hash")
                and result.get("status") in ("completed", "pending"), "Result is not this evaluation's")
    except (OSError, ValueError, KeyError, TypeError):
        return 2, {"status": "missing_or_invalid_result"}
    return (0 if result["status"] == "completed" else 3), {"status": result["status"], "reason": result.get("reason")}


# ----------------------------------------------------------------------------- report (zero-call)
MIN_COVERAGE = 0.9  # a contrast is read only when at least this share of the positions is jointly known
MIN_HISTORIES = 3   # fewer histories: no history-level or crossed interval
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086}


def _mean_se(values):
    n = len(values)
    mean = sum(values) / n
    return mean, (math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1) / n) if n > 1 else float("nan"))


def paired(positions, a, b, planned=None):
    """Arm (or group) ``a`` minus arm (or group) ``b`` on the tasks where EVERY arm involved is known (one common
    task set for the estimate and for every per-history value). A group is a list of arm names (learning histories)
    and contributes its per-task mean pass rate.

    * ``task_ci95``: tasks resampled, the realized Skill texts held fixed (conditional on these texts);
    * ``history_ci95`` (a group against one text, or two groups of equal size whose members are paired in the given
      order, e.g. by seed): histories resampled, the tasks held fixed;
    * ``crossed_ci95``: estimate +- t(H-1) * sqrt(se_task^2 + se_history^2) -- a deliberately conservative
      combination for tasks crossed with histories (the task-by-history interaction is counted in both terms).
      It is the only interval a claim about "the procedure on new tasks" may rest on; the other two are diagnostics.
    Two single texts have no history dimension: their Tango interval is conditional on those two texts.
    Every interval is conditional on the jointly known tasks (missing outcomes are assumed unrelated to the
    contrast); ``missing_outcome_bounds`` shows how far that assumption could matter. ``planned`` is the planned
    number of positions: coverage is judged against it, so a run that is absent counts as missing."""
    from skillopt.active_evidence.matched import paired_difference, sign_test_p

    first, second = ([a] if type(a) is str else list(a)), ([b] if type(b) is str else list(b))
    planned = len(positions) if planned is None else planned
    require(type(planned) is int and planned >= len(positions), "The planned denominator covers the given positions")
    rows = [p["status"] for p in positions
            if all(p["status"].get(arm) in ("pass", "fail") for arm in first + second)]
    n = len(rows)
    # Point bounds over ALL planned positions with every missing outcome set against / for the contrast (an
    # unknown or never-run solve of ``a`` counted as a failure and of ``b`` as a pass, and the reverse): what the
    # estimate could be if the missing outcomes were as unfavourable / favourable as possible.
    worst = lambda row, arms, missing: sum(  # noqa: E731
        (row.get(arm) == "pass") if row.get(arm) in ("pass", "fail") else missing for arm in arms) / len(arms)
    absent = planned - len(positions)
    low = (sum(worst(p["status"], first, 0) - worst(p["status"], second, 1) for p in positions) - absent) / planned
    high = (sum(worst(p["status"], first, 1) - worst(p["status"], second, 0) for p in positions) + absent) / planned
    out = {"planned_positions": planned, "positions": len(positions), "known": n,
           "histories": [len(first), len(second)], "missing_outcome_bounds": [low, high]}
    if n < 2 or n < MIN_COVERAGE * planned:
        return {**out, "estimate": None, "reason": "insufficient_jointly_known_positions"}
    rate = lambda row, arms: sum(row[arm] == "pass" for arm in arms) / len(arms)  # noqa: E731
    estimate, se_task = _mean_se([rate(r, first) - rate(r, second) for r in rows])
    out.update({"estimate": estimate, "task_se": se_task,
                "task_ci95": [estimate - 1.96 * se_task, estimate + 1.96 * se_task]})
    if len(first) == len(second) == 1:
        wins = sum(r[first[0]] == "pass" and r[second[0]] == "fail" for r in rows)
        losses = sum(r[first[0]] == "fail" and r[second[0]] == "pass" for r in rows)
        out.update({"wins": wins, "losses": losses, "ties": n - wins - losses,
                    "tango_ci95": paired_difference(wins, losses, n)["ci95"], "sign_p": sign_test_p(wins, losses)})
        return out
    if len(second) == 1:
        each = [sum((r[arm] == "pass") - (r[second[0]] == "pass") for r in rows) / n for arm in first]
    elif len(first) == len(second):
        each = [sum((r[x] == "pass") - (r[y] == "pass") for r in rows) / n for x, y in zip(first, second)]
    else:
        return out  # groups of different size have no pairing: task-level interval only
    out["per_history"] = each
    if len(each) >= MIN_HISTORIES:
        _, se_history = _mean_se(each)
        half = T975[len(each) - 1] * se_history
        crossed = T975[len(each) - 1] * math.sqrt(se_task ** 2 + se_history ** 2)
        out.update({"history_se": se_history, "history_ci95": [estimate - half, estimate + half],
                    "crossed_ci95": [estimate - crossed, estimate + crossed]})
    return out


def aligned(a, b, seed_of):
    """Two groups paired by the RECORDED seed of their histories: (members of a, members of b, dropped members).
    A group whose members lack unique recorded seeds cannot be paired (None)."""
    seeds_a, seeds_b = [seed_of.get(m) for m in a], [seed_of.get(m) for m in b]
    if any(type(x) is not int for x in seeds_a + seeds_b) or len(set(seeds_a)) != len(a) or len(set(seeds_b)) != len(b):
        return None
    common = sorted(set(seeds_a) & set(seeds_b))
    return ([a[seeds_a.index(x)] for x in common], [b[seeds_b.index(x)] for x in common],
            sorted(m for m, x in zip(a + b, seeds_a + seeds_b) if x not in common))


def report(outputs, contrasts=(), groups=(), planned_tasks=None):
    from skillopt.active_evidence.stage import stage_artifacts
    from skillopt.continual_learning.ledger import Ledger

    runs = []
    for output in outputs:
        out = safe_path(output)
        record, result = read_json(out / "eval.json", sealed=True), read_json(out / "result.json", sealed=True)
        value = read_json(out / "manifest.json", sealed=True)
        require(result.get("eval_hash") == record["record_hash"] and value["record_hash"] == record["manifest_hash"]
                == result["manifest_hash"], "Result does not belong to this evaluation")
        if result.get("artifacts") is not None:
            # the retained evidence (receipts, intents, sealed evaluations) is the one the result was built from
            require(stage_artifacts(out / "learning", Ledger(out / "learning", value, None)) == result["artifacts"],
                    "Evaluation evidence changed")
        runs.append((out.name, record, result, value))
    names = runs[0][2]["arms"]
    same = lambda key: len({digest(key(run)) for run in runs}) == 1  # noqa: E731
    require(all(result["arms"] == names for _, _, result, _ in runs)
            and same(lambda run: [{k: v for k, v in s.items() if k != "file"} for s in run[1]["skills"]]),
            "The runs evaluate different arms or Skill texts")
    require(same(lambda run: [run[1]["benchmark"], run[1]["protocol_hash"], run[1]["learning_model_service"],
                              run[1]["recovery_policy"], run[1]["package_sources"], run[1]["learning_sources"],
                              run[3]["model"], run[3]["runtime"], run[3]["version"]]),
            "The runs differ in benchmark, model, service, runtime or sources")
    positions = [p for _, _, result, _ in runs for p in result["positions"]]
    require(len({p["task_hash"] for p in positions}) == len(positions)
            and len({p["family_id"] for p in positions}) == len(positions), "The runs share a task or a family")
    grouped = {}
    for spec in groups:
        name, separator, members = spec.partition("=")
        members = members.split(",")
        require(separator == "=" and name not in names and name not in grouped and len(members) >= 2
                and len(set(members)) == len(members) and all(m in names for m in members),
                "A group is name=arm1,arm2,... of distinct evaluated arms")
        grouped[name] = members
    out = {"runs": [{"run": name, "status": result["status"], "reason": result.get("reason"), "tasks": record["tasks"],
                     "costs": None if result["costs"] is None else {
                         k: result["costs"].get(k) for k in ("logical_calls", "solver_calls",
                                                             "reported_tokens_known_subtotal", "missing_usage_calls",
                                                             "unclosed_calls")}}
                    for name, record, result, _ in runs],
           "complete": all(result["status"] == "completed" for _, _, result, _ in runs),
           "skills": [{k: s.get(k) for k in ("name", "action", "stage", "skill_bytes", "parent", "seed")}
                      for s in runs[0][1]["skills"]],
           "arms": {name: {s: sum(p["status"].get(name) == s for p in positions) for s in ("pass", "fail", "unknown")}
                    for name in names},
           "groups": grouped, "contrasts": {}}
    for name in names:
        out["arms"][name]["not_run"] = sum(name not in p["status"] for p in positions)
    require(planned_tasks is None or (type(planned_tasks) is int and planned_tasks >= len(positions)),
            "The planned number of tasks covers the reported ones")
    out["planned_tasks"] = planned_tasks if planned_tasks is not None else len(positions)
    seed_of = {s["name"]: s.get("seed") for s in runs[0][1]["skills"]}
    for spec in contrasts:
        a, separator, b = spec.partition("-")
        require(separator == "-" and all(x in names or x in grouped for x in (a, b)), "A contrast is a-b")
        first, second, extra = grouped.get(a, a), grouped.get(b, b), {}
        if a in grouped and b in grouped:
            pairing = aligned(first, second, seed_of)
            if pairing is None or len(pairing[0]) < 2:
                # never paired by list position: without shared recorded seeds only the task-level reading remains
                extra = {"pairing": "fewer than two recorded seeds shared by both groups: histories are not paired",
                         "unpaired": True}
            else:
                first, second, dropped = pairing
                extra = {"paired_seeds": [seed_of[m] for m in first], "dropped_unpaired_histories": dropped}
        value = paired(positions, first, second, out["planned_tasks"])
        if extra.get("unpaired"):
            for key in ("per_history", "history_se", "history_ci95", "crossed_ci95"):
                value.pop(key, None)
        out["contrasts"][spec] = {**value, **{k: v for k, v in extra.items() if k != "unpaired"}}
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    for name in ("study", "split", "repo", "items", "revision", "output"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--benchmark", required=True, choices=tool.API_ONLY)
    p.add_argument("--skill", action="append", required=True)
    p.add_argument("--seed", type=int, default=20261012)
    p.add_argument("--chunk", type=int, default=50)
    for name in ("run", "status"):
        sub.add_parser(name).add_argument("--output", required=True)
    p = sub.add_parser("report")
    p.add_argument("--output", required=True, nargs="+")
    p.add_argument("--contrast", action="append", default=[])
    p.add_argument("--group", action="append", default=[])
    p.add_argument("--planned-tasks", type=int, help="the planned number of tasks over all runs of the design "
                                                     "(coverage is judged against it: an absent run is missing)")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        record = prepare(args.study, args.split, args.output, args.repo, benchmark=args.benchmark, items=args.items,
                         revision=args.revision, skills=args.skill, seed=args.seed, chunk=args.chunk)
        value = {k: record[k] for k in ("version", "benchmark", "tasks", "record_hash")}
        value["skills"] = [(s["name"], s["action"], s["skill_bytes"]) for s in record["skills"]]
    elif args.command == "status":
        code, value = status(args.output)
        print(json.dumps(value))
        return code
    elif args.command == "run":
        result = run(args.output)
        value = {k: result.get(k) for k in ("version", "status", "reason", "summary", "record_hash")}
    else:
        value = report(args.output, args.contrast, args.group, args.planned_tasks)
    print(json.dumps(value, ensure_ascii=False, indent=1 if args.command == "report" else None))
    return 0 if args.command != "run" or value["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
