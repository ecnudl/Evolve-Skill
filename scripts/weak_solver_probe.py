#!/usr/bin/env python3
"""Solver-strength probe (2026-10-15, evaluation only): solve the SAME items with several Skills and one chosen model,
k independent runs each, and score them with the frozen native scorers -- to see whether the differences between
Skills (empty, zero-shot instruction, learned) widen when the solver is weaker.

The prompt is exactly the learning stages' (``continual_eval.backends.solve``); only the model call differs: the frozen
client (``validator_pilot/api.py``) admits glm-5.3 alone, so this script sends the same chat request to one of two
approved endpoints with an explicitly allowed model name, through the approved PJLAB gateway, reading the backend's
credential file without ever printing it. Two backends:
  * ``bigmodel`` -- the credential repository's ``.env`` (BIGMODEL_CHAT_URL, BIGMODEL_API_KEY), reused from the frozen
    learning path; the GLM models route here.
  * ``free_router`` -- the OpenDataLab router env (OPENDATALAB_ROUTER_URL, OPENDATALAB_ROUTER_KEY); the gateway requires
    an ``X-Session-Id`` header (one fresh UUID per call), authorized by the provider for this probe's batch use. The
    Qwen3.5-9B and deepseek-v4-flash entries route here. The provider may return a canonical model id different from
    the request id (e.g. ``deepseek-v4-flash`` -> ``deepseek-flash``); every allow-list entry declares the full set of
    acceptable response model ids.
One explicit route (2026-10-19, coevo5 registration v3 §9), chosen only by a caller that names it (``Client(...,
route=..., route_env=...)``; the probe's own command line never does):
  * ``pjlab_token`` -- the PJLAB token endpoint (fixed URL; PJLAB_TOKEN_API_KEY from its credential file), with its own
    allow-list: deepseek-v4-flash, which must echo ``deepseek-v4-flash``. No X-Session-Id header. Every request names
    the thinking mode, disabled: the endpoint mixes a thinking and a non-thinking serving from call to call, and only
    "disabled" is honoured by both (2026-10-19 probes, 48 calls each: enabled 42 thinking and 6 not, disabled 48 not).
    A reply that still carries reasoning text came from the other serving: ``thinking_mismatch``, like another model's.
A reply counts only when it is a completed ("stop"), well formed reply whose returned model id is in that set;
everything else stays unknown (never pass, never fail). No Skill is learned, no gate is run, no test or calibration
item is read. Every record is written once; a used output directory is never reused; the first cell runs alone and a
configuration failure stops the probe before anything else is submitted.

Usage:
  weak_solver_probe.py run --model glm-4.7-flash --benchmark officeqa --repo <credential repo>
      --items <panel.json>[:<partition>] | --items <pilot items.json> [--items ...]
      --skill <name>=none|f:<file> [--skill ...] --runs 2 --workers 6 --output <new dir> [--lock <lock file>]
  weak_solver_probe.py run --model Qwen/Qwen3.5-9B --benchmark officeqa --router-env <router.env>
      --items ... --skill ... --output <new dir>  # free-router models require --router-env instead of --repo
  weak_solver_probe.py report --output <dir> [<dir> ...]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import math
import os
import random
import re
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skillopt.continual_eval import backends  # noqa: E402

VERSION = "solver-strength-probe-v3"
BIGMODEL_HOST = "open.bigmodel.cn"
BIGMODEL_PATH = "/api/paas/v4/chat/completions"
FREE_ROUTER_HOST = "free-router.opendatalab.com"
FREE_ROUTER_CHAT_PATH = "/v1/chat/completions"
SESSION_ID_HEADER = "X-Session-Id"
PJLAB_TOKEN_HOST = "token.pjlab.org.cn"
PJLAB_TOKEN_PATH = "/v1/chat/completions"
PJLAB_TOKEN_URL = "https://" + PJLAB_TOKEN_HOST + PJLAB_TOKEN_PATH
GATEWAY = "http://httpproxy-headless.kubebrain.svc.pjlab.local:3128"
# model -> (backend, thinking field, reasoning_effort, default max_tokens, response_model_ids): the explicit allow-list.
# ``response_model_ids`` is the set of model ids the provider may echo back for this request id; the probe refuses any
# response outside that set. Free-router entries route through FREE_ROUTER_HOST and receive an X-Session-Id header on
# every call (one fresh UUID per call); the provider authorized this gateway header for batch use.
MODELS = {
    "glm-5.3":              ("bigmodel",    "enabled", "low",  65536, frozenset({"glm-5.3"})),
    "glm-5.3-flash":        ("bigmodel",    "enabled", None,   32768, frozenset({"glm-5.3-flash"})),
    "glm-4.7-flash":        ("bigmodel",    "enabled", None,   32768, frozenset({"glm-4.7-flash"})),
    "glm-4.5-flash":        ("bigmodel",    "enabled", None,   32768, frozenset({"glm-4.5-flash"})),
    "glm-4-flash-250414":   ("bigmodel",    None,      None,   4095,  frozenset({"glm-4-flash-250414"})),
    "Qwen/Qwen3.5-9B":      ("free_router", None,      None,   32768, frozenset({"Qwen/Qwen3.5-9B"})),
    # deepseek-v4-flash's response id is the canonical "deepseek-flash"; both are accepted.
    "deepseek-v4-flash":    ("free_router", None,      None,   32768, frozenset({"deepseek-v4-flash", "deepseek-flash"})),
}
# route -> {model: (response_model_ids, thinking)}: an explicit route's own allow-list and the thinking mode its requests
# name (a MODELS entry supplies the other request settings)
ROUTES = {"pjlab_token": {"deepseek-v4-flash": (frozenset({"deepseek-v4-flash"}), "disabled")}}
BENCHMARKS = ("officeqa", "searchqa")
FORBIDDEN = {"final", "test", "holdout", "held_out", "heldout", "verifier_calibration", "calibration", "reserve"}
RETRY_STATUSES = {429, 500, 502, 503, 504}
BACKOFF = (10, 30, 60)
RATE_BACKOFF = (30, 90, 180)  # HTTP 429 (provider rate limits on the free flash tiers) waits longer
NAME = re.compile(r"[A-Za-z0-9_-]{1,40}")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def write_once(path, value):
    """Atomic, exclusive publication: a unique temporary file in the target directory, hard-linked to the target
    (which must not exist), then removed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1))
        os.link(tmp, path)  # FileExistsError when the target exists: nothing is overwritten
    finally:
        os.unlink(tmp)


def _read_env(path):
    """Read KEY=VALUE lines from a credential file; values stay in memory only."""
    values = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _validated_url(url, host, path, message):
    """``url`` must be https with the given host, no credentials in url, no query/fragment, standard port, exact path."""
    try:
        parsed = urlsplit(url)
        ok = (parsed.scheme == "https" and parsed.hostname == host and not parsed.username and not parsed.password
              and not parsed.query and not parsed.fragment and parsed.port in (None, 443)
              and parsed.path.rstrip("/") == path.rstrip("/"))
    except ValueError:
        ok = False
    if not ok:
        raise SystemExit(message) from None
    return url


def bigmodel_credentials(repo):
    """The credential repository's BigModel endpoint and key (never printed, written or put in an exception)."""
    values = _read_env(Path(repo) / ".env")
    url, key = values.get("BIGMODEL_CHAT_URL", ""), values.get("BIGMODEL_API_KEY", "")
    _validated_url(url, BIGMODEL_HOST, BIGMODEL_PATH, "BIGMODEL_CHAT_URL is not the approved BigModel chat endpoint")
    if not key:
        raise SystemExit("BIGMODEL_API_KEY missing")
    return url, key


def router_credentials(env_path):
    """The OpenDataLab free-router endpoint and key (never printed, written or put in an exception). Returns the full
    chat-completions URL ready for POST. The provider gates on an X-Session-Id header which the probe injects on every
    call; this script never fabricates agent transcripts."""
    values = _read_env(env_path)
    base = values.get("OPENDATALAB_ROUTER_URL", "").rstrip("/")
    key = values.get("OPENDATALAB_ROUTER_KEY", "")
    url = base + FREE_ROUTER_CHAT_PATH
    _validated_url(url, FREE_ROUTER_HOST, FREE_ROUTER_CHAT_PATH,
                   "OPENDATALAB_ROUTER_URL is not the approved free-router endpoint")
    if not key:
        raise SystemExit("OPENDATALAB_ROUTER_KEY missing")
    return url, key


def pjlab_credentials(env_path):
    """The PJLAB token endpoint (fixed) and its key from the credential file (never printed, written or put in an
    exception)."""
    key = _read_env(env_path).get("PJLAB_TOKEN_API_KEY", "")
    if not key:
        raise SystemExit("PJLAB_TOKEN_API_KEY missing")
    return _validated_url(PJLAB_TOKEN_URL, PJLAB_TOKEN_HOST, PJLAB_TOKEN_PATH, "Not the PJLAB token endpoint"), key


def _labels(row):
    labels = [row.get("partition"), row.get("split"), row.get("part")]
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    labels += [meta.get(k) for k in ("part", "partition", "split", "role")]
    return [str(x).lower() for x in labels if x is not None]


def load_items(spec):
    """``<panel>[:<partition>]`` (tasks with task_id/partition; the suffix only SELECTS a partition) or a pilot item
    file (items with id/meta; no suffix: its own labels are kept). Any test/calibration/reserve label anywhere in a
    row's metadata refuses the whole file."""
    path, partition = spec, ""
    if ":" in spec and not Path(spec).exists():
        path, partition = spec.rsplit(":", 1)
    data = json.loads(Path(path).read_text())
    source = data["tasks"] if isinstance(data, dict) and "tasks" in data else data["items"] if isinstance(data, dict) else data
    rows = []
    for row in source:
        if set(_labels(row)) & FORBIDDEN:
            raise SystemExit("Test/calibration/reserve items are never read by this probe")
        if "task_id" in row:
            if partition and row.get("partition") != partition:
                continue
            rows.append({"id": row["task_id"], "public": row["public"], "private": row["private"],
                         "label": row.get("partition")})
        else:
            if partition:
                raise SystemExit("A pilot item file keeps its own labels; no partition suffix")
            rows.append({"id": row["id"], "public": row["public"], "private": row["private"],
                         "label": "/".join(_labels(row)) or "unlabeled"})
    if not rows:
        raise SystemExit("No item selected from " + path)
    return rows


def load_skill(spec):
    name, _, source = spec.partition("=")
    if not NAME.fullmatch(name or "") or not source:
        raise SystemExit("--skill <name>=none|f:<file> with a name of letters, digits, _ or - (at most 40)")
    if source == "none":
        return name, ""
    if not source.startswith("f:"):
        raise SystemExit("--skill <name>=none|f:<file>")
    return name, Path(source[2:]).read_text()


def _usage(value):
    if (isinstance(value, dict) and all(type(value.get(k)) is int and value[k] >= 0
                                        for k in ("prompt_tokens", "completion_tokens", "total_tokens"))):
        return {k: value[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    return None


class Client:
    def __init__(self, repo, model, *, proxy, max_tokens, router_env=None, read_timeout=900, transport=None, route=None,
                 route_env=None):
        import httpx

        if model not in MODELS:
            raise SystemExit("Model not in this probe's allow-list: " + model)
        if proxy not in (None, GATEWAY):
            raise SystemExit("Only the approved PJLAB gateway (or none) may be used")
        backend, thinking, effort, _, response_ids = MODELS[model]
        if route is not None:  # an explicit route: its own allow-list and credential file only
            if model not in ROUTES.get(route, {}):
                raise SystemExit("Model not in this route's allow-list: " + model)
            if not route_env:
                raise SystemExit("The route needs its credential file")
            backend, (response_ids, thinking) = route, ROUTES[route][model]
            self.url, self._key = pjlab_credentials(route_env)
        elif backend == "bigmodel":
            if not repo:
                raise SystemExit("--repo is required for a BigModel model")
            self.url, self._key = bigmodel_credentials(repo)
        else:
            if not router_env:
                raise SystemExit("--router-env is required for a free-router model")
            self.url, self._key = router_credentials(router_env)
        self.backend, self.model, self.max_tokens = backend, model, max_tokens
        self.thinking, self.effort, self.response_model_ids = thinking, effort, response_ids
        options = {"transport": transport} if transport is not None else ({"proxy": proxy} if proxy else {})
        self.http = httpx.Client(timeout=httpx.Timeout(connect=20, read=read_timeout, write=30, pool=30),
                                 trust_env=False, follow_redirects=False, **options)
        self._transport_errors = (httpx.TransportError,)

    def body(self, system, user):
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": self.max_tokens, "temperature": 0}
        if self.thinking:
            body["thinking"] = {"type": self.thinking}
        if self.effort:
            body["reasoning_effort"] = self.effort
        return body

    def _receipt(self, status, data, attempts, started):
        """The receipt ``backends.solve`` reads. ``ok`` only for a completed reply ('stop') of the requested model with
        an error-free envelope and nonblank text; blank text of such a reply keeps the frozen 'delivered without text'
        meaning; anything else is unknown. A request that disables thinking is answered by the requested serving only
        when the reply carries no reasoning text; otherwise the reply is the other serving's (``thinking_mismatch``,
        read before the finish reason)."""
        base = {"status": status, "attempts": attempts, "seconds": round(time.time() - started, 1)}
        if not isinstance(data, dict) or "error" in data:
            return {**base, "ok": False, "response": None, "finish_reason": None, "usage": {}, "error_type": "error_payload"}
        choices = data.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        message = choice.get("message") if choice is not None and isinstance(choice.get("message"), dict) else None
        if message is None:
            return {**base, "ok": False, "response": None, "finish_reason": None, "usage": {}, "error_type": "malformed_choices"}
        finish = choice.get("finish_reason")
        if finish is not None and type(finish) is not str:  # normalized before any other return reads it
            return {**base, "ok": False, "response": None, "finish_reason": None, "usage": {}, "error_type": "malformed_finish"}
        returned_model = data.get("model")  # the allow-list contains only strings; non-str echoes are mismatches
        if not isinstance(returned_model, str) or returned_model not in self.response_model_ids:
            return {**base, "ok": False, "response": None, "finish_reason": finish, "usage": {},
                    "error_type": "model_mismatch", "returned_model": str(returned_model)[:60]}
        usage = _usage(data.get("usage"))
        content = message.get("content")
        reasoning = message.get("reasoning_content")
        receipt = {**base, "response": content if isinstance(content, str) else None, "finish_reason": finish,
                   "usage": usage or {}, "usage_valid": usage is not None, "returned_model": data.get("model"),
                   "reasoning_chars": len(reasoning) if isinstance(reasoning, str) else 0}
        if self.thinking == "disabled" and receipt["reasoning_chars"]:
            return {**receipt, "ok": False, "error_type": "thinking_mismatch"}
        if finish != "stop":
            return {**receipt, "ok": False, "error_type": "finish_" + str(finish)[:30]}
        if not isinstance(content, str):
            return {**receipt, "ok": False, "error_type": "content_missing"}
        if not content.strip():
            return {**receipt, "ok": False, "error_type": "empty_content"}
        return {**receipt, "ok": True}

    def call(self, system, user):
        """One chat completion with bounded retries on transport errors and transient statuses only. Free-router calls
        carry a fresh ``X-Session-Id`` UUID per call (the gateway requires this; the provider authorized the batch use).
        The UUID is never persisted or printed."""
        body = self.body(system, user)
        attempts, started = [], time.time()
        for attempt in range(len(BACKOFF) + 1):
            t0 = time.time()
            headers = {"Authorization": "Bearer " + self._key}
            if self.backend == "free_router":
                headers[SESSION_ID_HEADER] = str(uuid.uuid4())
            try:
                r = self.http.post(self.url, json=body, headers=headers)
            except self._transport_errors as exc:  # transport: the type only; anything else is a bug and propagates
                attempts.append({"error": type(exc).__name__, "seconds": round(time.time() - t0, 1)})
                if attempt < len(BACKOFF):
                    time.sleep(BACKOFF[attempt])
                    continue
                return {"ok": False, "response": None, "finish_reason": None, "usage": {}, "attempts": attempts,
                        "error_type": "transport", "seconds": round(time.time() - started, 1)}
            status = r.status_code
            attempts.append({"status": status, "seconds": round(time.time() - t0, 1)})
            if status in RETRY_STATUSES and attempt < len(BACKOFF):
                time.sleep((RATE_BACKOFF if status == 429 else BACKOFF)[attempt])
                continue
            try:
                data = r.json()
            except ValueError:
                data = None
            if status != 200:
                code = None
                if isinstance(data, dict) and isinstance(data.get("error"), dict):
                    code = str(data["error"].get("code"))[:20]
                return {"ok": False, "response": None, "finish_reason": None, "usage": {}, "status": status,
                        "attempts": attempts, "error_type": "http_%d" % status, "error_code": code,
                        "seconds": round(time.time() - started, 1)}
            if data is None:
                return {"ok": False, "response": None, "finish_reason": None, "usage": {}, "status": status,
                        "attempts": attempts, "error_type": "invalid_json", "seconds": round(time.time() - started, 1)}
            return self._receipt(status, data, attempts, started)
        raise AssertionError("unreachable")


def _validated(record):
    """A first cell opens the batch only on positive evidence: a completed ('stop') reply of the requested model (a
    scored answer, or the frozen 'delivered without text')."""
    return record["finish_reason"] == "stop" and record["error_type"] in (None, "empty_content") \
        and record["prediction_status"] == "available"


def run(args, client_factory=None):
    out = Path(args.output)
    if out.exists():
        raise SystemExit("Use a new output directory (a probe directory is written once)")
    if args.benchmark not in BENCHMARKS:
        raise SystemExit("Benchmark not supported by this probe")
    if args.model not in MODELS:
        raise SystemExit("Model not in this probe's allow-list: " + args.model)
    items = [row for spec in args.items for row in load_items(spec)]
    ids = [r["id"] for r in items]
    if len(set(ids)) != len(ids):
        raise SystemExit("Duplicate item ids across --items")
    skills = dict(load_skill(s) for s in args.skill)
    if len(skills) != len(args.skill) or len({n.casefold() for n in skills}) != len(skills):
        raise SystemExit("Duplicate skill names (case-insensitively)")
    backend, thinking, effort, default_max, response_ids = MODELS[args.model]
    if backend == "bigmodel" and not args.repo:
        raise SystemExit("--repo is required for a BigModel model")
    if backend == "free_router" and not args.router_env:
        raise SystemExit("--router-env is required for a free-router model")
    max_tokens = args.max_tokens or default_max
    # Only pass router_env when the backend needs it, so a legacy BigModel-only client_factory keeps working.
    extra = {"router_env": args.router_env} if backend == "free_router" else {}
    client = (client_factory or Client)(args.repo, args.model, proxy=args.proxy, max_tokens=max_tokens, **extra)
    config = {"version": VERSION, "backend": backend, "model": args.model, "benchmark": args.benchmark,
              "runs": args.runs, "thinking": thinking, "reasoning_effort": effort, "max_tokens": max_tokens,
              "temperature": 0, "proxy": args.proxy, "items": args.items, "item_ids_hash": digest(sorted(ids)),
              "items_hash": digest(sorted(digest(r) for r in items)), "n_items": len(items),
              "item_labels": {lab: sum(r["label"] == lab for r in items) for lab in sorted({str(r["label"]) for r in items})},
              "skills": {name: {"hash": digest(text), "bytes": len(text.encode())} for name, text in skills.items()},
              "seed": args.seed, "prompt": "continual_eval.backends.solve (the learning stages' solver prompt)",
              "response_model_ids": sorted(response_ids),
              "session_id_header": SESSION_ID_HEADER if backend == "free_router" else None,
              "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    out.mkdir(parents=True)
    write_once(out / "config.json", config)
    rng = random.Random(args.seed)
    cells = []
    for repeat in range(args.runs):  # every run interleaves items and Skills (no Skill runs in a block of its own)
        order = items[:]
        rng.shuffle(order)
        for item in order:
            names = sorted(skills)
            rng.shuffle(names)
            cells.extend((repeat, item, name) for name in names)
    done = {"n": 0}
    progress = threading.Lock()

    def one(cell):
        repeat, item, name = cell
        receipts = []

        def call(system, user):
            receipt = client.call(system, user)
            receipts.append(receipt)
            return receipt

        prediction = backends.solve(args.benchmark, item["public"], skills[name], call, runtime={})
        score = backends.score(args.benchmark, item["public"], item["private"], prediction, runtime={})
        last = receipts[-1] if receipts else {}
        record = {"skill": name, "item": item["id"], "label": item["label"], "run": repeat, "status": score["status"],
                  "score": score.get("score"), "reason": score.get("reason"), "prediction_status": prediction["status"],
                  "prediction_reason": prediction.get("reason"), "output": prediction.get("output"),
                  "finish_reason": last.get("finish_reason"), "usage": last.get("usage") or {},
                  "usage_valid": last.get("usage_valid", False), "returned_model": last.get("returned_model"),
                  "reasoning_chars": last.get("reasoning_chars"), "attempts": last.get("attempts"),
                  "error_type": last.get("error_type"), "error_code": last.get("error_code"), "seconds": last.get("seconds")}
        write_once(out / "records" / name / ("%s.%d.json" % (digest(item["id"])[:24], repeat)), record)
        with progress:
            done["n"] += 1
            if done["n"] % 100 == 0 or done["n"] == len(cells):
                print("%s %d/%d cells" % (time.strftime("%H:%M:%S"), done["n"], len(cells)), flush=True)
        return record

    def execute():
        first = one(cells[0])  # the first real reply alone: anything but a validated model response stops here
        if not _validated(first):
            write_once(out / "summary.json", {"status": "aborted_at_first_cell", "error_type": first["error_type"],
                                              "error_code": first["error_code"], "config_hash": digest(config)})
            raise SystemExit("First cell is not a validated model response (%s): nothing else submitted"
                             % (first["error_type"] or first["prediction_reason"]))
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            return [first] + list(pool.map(one, cells[1:]))

    if args.lock:
        with open(args.lock, "a") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            records = execute()
    else:
        records = execute()
    summary = summarize(records, sorted(skills), args.runs)
    write_once(out / "summary.json", {**summary, "status": "completed", "config_hash": digest(config),
                                      "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    print(json.dumps({k: summary[k] for k in ("per_skill", "unknown_cells")}, indent=1))


def sign_test(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def summarize(records, skills, runs):
    by = {}
    for r in records:
        by.setdefault(r["skill"], {}).setdefault(r["item"], {})[r["run"]] = r["status"]
    per_skill = {}
    for name in skills:
        cells = [s for item in by.get(name, {}).values() for s in item.values()]
        per_run = [sum(1 for item in by.get(name, {}).values() if item.get(k) == "pass") for k in range(runs)]
        known = cells.count("pass") + cells.count("fail")
        per_skill[name] = {"cells": len(cells), "pass": cells.count("pass"), "fail": cells.count("fail"),
                           "unknown": cells.count("unknown"), "known": known,
                           "pass_rate_known": cells.count("pass") / known if known else None, "pass_per_run": per_run}
    pairs = {}
    for a in skills:
        for b in skills:
            if a >= b:
                continue
            wins = losses = ties = excluded = 0
            item_up = item_down = item_tied = item_excluded = item_partial = 0
            for item, statuses in by.get(a, {}).items():
                net, known = 0, 0
                for k, sa in statuses.items():
                    sb = by.get(b, {}).get(item, {}).get(k)
                    if sa not in ("pass", "fail") or sb not in ("pass", "fail"):
                        excluded += 1
                        continue
                    known += 1
                    wins += sa == "pass" and sb == "fail"
                    losses += sa == "fail" and sb == "pass"
                    ties += sa == sb
                    net += (sa == "pass") - (sb == "pass")
                if known == 0:
                    item_excluded += 1
                    continue
                item_partial += known < runs
                item_up += net > 0
                item_down += net < 0
                item_tied += net == 0
            pairs["%s - %s" % (a, b)] = {
                "cells": {"wins": wins, "losses": losses, "ties": ties, "excluded_unknown": excluded,
                          "sign_test_p_pooled_cells": sign_test(wins, losses),
                          "note": "cells of one item are repeated runs, not independent"},
                "items": {"better": item_up, "worse": item_down, "tied": item_tied, "excluded_all_unknown": item_excluded,
                          "partially_known": item_partial, "sign_test_p": sign_test(item_up, item_down),
                          "note": "per item the net over its jointly known runs (an item with some unknown runs counts "
                                  "on the known ones): the item-level inference"}}
    stability = {}
    for name in skills:
        classes = {"always_pass": 0, "flaky": 0, "always_fail": 0, "with_unknown": 0}
        for statuses in by.get(name, {}).values():
            values = [statuses.get(k) for k in range(runs)]
            if any(v not in ("pass", "fail") for v in values):
                classes["with_unknown"] += 1
            elif all(v == "pass" for v in values):
                classes["always_pass"] += 1
            elif all(v == "fail" for v in values):
                classes["always_fail"] += 1
            else:
                classes["flaky"] += 1
        stability[name] = classes
    reasons = {}
    for r in records:
        if r["status"] == "unknown":
            key = str(r.get("error_type") or r.get("prediction_reason") or r.get("reason"))
            reasons[key] = reasons.get(key, 0) + 1
    tokens = sum(int(r["usage"].get("total_tokens", 0)) for r in records if r.get("usage_valid"))
    return {"per_skill": per_skill, "pairs": pairs, "stability": stability,
            "unknown_cells": sum(1 for r in records if r["status"] == "unknown"), "unknown_reasons": reasons,
            "total_tokens_reported": tokens, "cells_without_valid_usage": sum(1 for r in records if not r.get("usage_valid")),
            "cells": len(records)}


def _rate(v):
    return "N/A" if v is None or v.get("known", 0) == 0 else "%.3f" % (v["pass"] / v["known"])


def report(args):
    rows = []
    for directory in args.output:
        d = Path(directory)
        config = json.loads((d / "config.json").read_text())
        summary = json.loads((d / "summary.json").read_text()) if (d / "summary.json").exists() else None
        if summary is None or summary.get("status") != "completed":
            print("%s: %s" % (d.name, "no summary (unfinished)" if summary is None else summary.get("status")))
            continue
        if summary.get("config_hash") != digest(config):
            print("%s: summary does not belong to this config: skipped" % d.name)
            continue
        rows.append((config, summary))
        print("== %s | model %s | %s | items %d %s | runs %d | unknown %d %s | tokens %s (cells without usage %d)" % (
            d.name, config["model"], config["benchmark"], config["n_items"], config.get("item_labels", ""),
            config["runs"], summary["unknown_cells"], summary["unknown_reasons"] or "", summary["total_tokens_reported"],
            summary["cells_without_valid_usage"]))
        for name, v in summary["per_skill"].items():
            print("  %-14s pass %4d / known %-4d (%s) unknown %d | per run %s | stability %s" % (
                name, v["pass"], v["known"], _rate(v), v["unknown"], v["pass_per_run"], summary["stability"][name]))
        for pair, v in summary["pairs"].items():
            i, c = v["items"], v["cells"]
            print("  %-30s items better %3d worse %3d tied %3d all-unknown %d partly-known %d p=%.4g | cells wins %d "
                  "losses %d ties %d excluded %d" % (pair, i["better"], i["worse"], i["tied"], i["excluded_all_unknown"],
                                                    i["partially_known"], i["sign_test_p"], c["wins"], c["losses"],
                                                    c["ties"], c["excluded_unknown"]))
    groups = {}
    for config, summary in rows:
        groups.setdefault((config["benchmark"], config["items_hash"]), []).append((config, summary))
    for (benchmark, items_hash), group in groups.items():
        if len(group) < 2:
            continue
        names = sorted({n for c, _ in group for n in c["skills"]})
        print("\n%s, items %s: pass rate over known cells by model (a Skill with different text under one name is marked *)"
              % (benchmark, items_hash[:12]))
        print("  %-14s " % "skill" + " ".join("%-16s" % c["model"][:16] for c, _ in group))
        for name in names:
            hashes = {c["skills"][name]["hash"] for c, _ in group if name in c["skills"]}
            print("  %-14s " % (name + ("*" if len(hashes) > 1 else "")) +
                  " ".join("%-16s" % _rate(s["per_skill"].get(name)) for _, s in group))


def main(argv=None, client_factory=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--model", required=True)
    r.add_argument("--benchmark", required=True)
    r.add_argument("--repo", default=None, help="credential repository with .env (required for BigModel models)")
    r.add_argument("--router-env", default=None,
                   help="free-router env file with OPENDATALAB_ROUTER_URL/KEY (required for free-router models)")
    r.add_argument("--items", action="append", required=True)
    r.add_argument("--skill", action="append", required=True)
    r.add_argument("--runs", type=int, default=2)
    r.add_argument("--workers", type=int, default=6)
    r.add_argument("--max-tokens", type=int, default=None, help="default: the model's entry in MODELS")
    r.add_argument("--seed", type=int, default=20261015)
    r.add_argument("--proxy", default=GATEWAY)
    r.add_argument("--lock")
    r.add_argument("--output", required=True)
    p = sub.add_parser("report")
    p.add_argument("--output", nargs="+", required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        if not 1 <= args.runs <= 5 or not 1 <= args.workers <= 12 or not (args.max_tokens is None or 256 <= args.max_tokens <= 65536):
            raise SystemExit("runs 1-5, workers 1-12, max tokens 256-65536")
        run(args, client_factory)
    else:
        report(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
