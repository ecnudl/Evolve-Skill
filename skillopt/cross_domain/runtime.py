"""Resumable API execution using SkillOpt's existing compatible backend."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def configure_api(repo: Path, model: str, max_tokens: int = 8000) -> dict:
    # Only process-local proxy changes: do not touch Clash or machine routing.
    from dotenv import dotenv_values
    values = dotenv_values(repo / ".env")
    for key, value in values.items():
        if value is not None and ("OPENAI_COMPATIBLE" in key or key in {"OPTIMIZER_DEPLOYMENT", "TARGET_DEPLOYMENT"}):
            os.environ[key] = value
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "OPENAI_LOG"):
        os.environ.pop(key, None)
    url = values.get("OPENAI_COMPATIBLE_BASE_URL", "")
    key = values.get("OPENAI_COMPATIBLE_API_KEY", "")
    if not key or not url:
        raise ValueError("Missing local OPENAI_COMPATIBLE credentials; no secrets logged")
    from skillopt.model import set_backend
    from skillopt.model.openai_compatible_backend import configure_openai_compatible
    configure_openai_compatible(base_url=url, api_key=key, model=model,
                                optimizer_model=model, target_model=model,
                                optimizer_base_url=url, target_base_url=url,
                                optimizer_api_key=key, target_api_key=key,
                                temperature="", max_tokens=max_tokens, timeout_seconds=90)
    set_backend("openai_compatible")
    from urllib.parse import urlparse
    return {"provider_host": urlparse(url).hostname, "model": model,
            "backend": "openai_compatible", "max_tokens_cap": max_tokens,
            "temperature": "provider default", "reasoning_effort": "not forwarded by existing backend",
            "generation_seed": "not sent", "proxy": "process environment cleared"}


def safe_error(error: Exception) -> str:
    # Never persist SDK headers / URLs / raw exception bodies containing credentials.
    msg = str(error)
    status = re.search(r"(?:Error code: |status code[=: ]+)(\d{3})", msg, re.I)
    return type(error).__name__ + (f" HTTP {status.group(1)}" if status else " (details omitted)")


class CachedAPI:
    def __init__(self, root: Path, model: str, workers: int = 6):
        self.root, self.model, self.workers = root, model, workers
        from urllib.parse import urlparse

        from skillopt.model.openai_compatible_backend import TARGET_CONFIG
        parsed = urlparse(TARGET_CONFIG.base_url)
        self.service = {"host": parsed.hostname, "path": parsed.path,
                        "cap": TARGET_CONFIG.max_tokens, "temperature": TARGET_CONFIG.temperature}

    def call(self, system: str, user: str, *, kind: str, key: str,
             max_tokens: int = 2000, repeat: int = 0) -> dict:
        spec = {"system": system, "user": user, "model": self.model,
                "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat,
                "protocol": "scope-mvp-v1", "service": self.service}
        identifier = digest(spec)
        path = self.root / "calls" / (identifier + ".json")
        if path.exists():
            record = read_json(path)
            if record["request_hash"] != identifier:
                raise ValueError("Corrupt request cache")
            return record  # Terminal API failures are not silently retried on resume.
        from skillopt.model import chat_optimizer, chat_target
        fn = chat_target if kind == "target" else chat_optimizer
        start = time.monotonic()
        try:
            response, usage = fn(system=system, user=user, max_completion_tokens=max_tokens,
                                 retries=3, stage="cross_domain_" + kind, timeout=90)
            result = {"ok": True, "response": response, "usage": usage}
        except Exception as error:
            result = {"ok": False, "response": "", "usage": {}, "error": safe_error(error)}
        record = {"request_hash": identifier, "request": spec, **result,
                  "wall_seconds": time.monotonic() - start}
        write_json(path, record)
        return record

    def parallel(self, jobs: list, fn: Callable, label: str) -> list:
        result = [None] * len(jobs)
        start = time.monotonic()
        print(f"[{label}] {len(jobs)} jobs, workers={self.workers}", flush=True)
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(fn, job): i for i, job in enumerate(jobs)}
            for done, future in enumerate(as_completed(futures), 1):
                result[futures[future]] = future.result()
                if done % 20 == 0 or done == len(jobs):
                    print(f"[{label}] {done}/{len(jobs)} elapsed={time.monotonic()-start:.1f}s", flush=True)
        return result


TARGET_SYSTEM = (
    "Solve the supplied task. Follow its explicitly stated rules and return the requested JSON. "
    "You may reason privately. No external tools are available."
)


def rollout(api: CachedAPI, tasks: list, skill: str, label: str, repeat: int = 0) -> list[dict]:
    from skillopt.cross_domain.tasks import evaluate_answer
    system = TARGET_SYSTEM + ("\n\nReusable procedural guidance:\n" + skill if skill else "")

    def one(task):
        call = api.call(system, task.prompt, kind="target", key=task.id,
                        max_tokens=3000, repeat=repeat)
        evaluation = evaluate_answer(task, call["response"])
        return {"id": task.id, "domain": task.domain, "mechanism": task.mechanism,
                "group": task.group, "family": task.family, "split": task.split,
                "hard": int(evaluation["correct"]) if call["ok"] else None,
                "agent_ok": call["ok"], "evaluation": evaluation,
                "response": call["response"], "request_hash": call["request_hash"],
                "skill_hash": digest(skill), "repeat": repeat,
                "usage": call["usage"]}
    rows = api.parallel(tasks, one, label)
    write_json(api.root / "rollouts" / (label + ".json"), rows)
    good = [r for r in rows if r["agent_ok"]]
    print(f"[{label}] EM={sum(r['hard'] for r in good)}/{len(good)}, api_errors={len(rows)-len(good)}", flush=True)
    return rows
