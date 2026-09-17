"""Preregistered, fixed section lesions on the SAME source-retention holdout.

Import-safe: no model/QA imports before the caller's existing-session preload.
This is section attribution, not clean mechanism isolation or new source draws.
"""
from __future__ import annotations

import hashlib
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

BEST_SHA256 = "6aad066e67088cb4d814f8452908f092ca5a9f45ab44fcb7f65deb752fc5d17c"
LESIONS = ("without_evidence_section", "without_answer_form_sections")
ARMS = ("base", "full", *LESIONS)
EVIDENCE_HEADER = "## Extractive / Trivia Evidence Selection"
ANSWER_HEADER = "## Concise clue-answering rules"
SLOW_START, SLOW_END = "<!-- SLOW_UPDATE_START -->", "<!-- SLOW_UPDATE_END -->"
PHASES = ("prepare", "test", "report")


def _deps(repo):
    from scripts.source_retention_session_mvp import preload_session_environment
    preload_session_environment(Path(repo))
    from skillopt.scope_evolution_v2 import source_data, source_retention
    return source_data, source_retention


def _section_span(full: str, header: str) -> tuple[int, int]:
    matches = list(re.finditer(r"(?m)^" + re.escape(header) + r"$", full))
    if len(matches) != 1 or full.count(header) != 1:
        raise ValueError(f"Expected exactly one complete section header: {header}")
    start = matches[0].start()
    following = re.search(r"(?m)^#{1,2} ", full[matches[0].end():])
    if following is None:
        raise ValueError("Expected the following heading for a bounded section deletion")
    return start, matches[0].end() + following.start()


def _remove_spans(full: str, spans) -> str:
    spans = sorted(spans)
    if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
        raise ValueError("Overlapping deletion spans")
    pieces, previous = [], 0
    for start, end in spans:
        if not 0 <= start < end <= len(full):
            raise ValueError("Invalid deletion span")
        pieces.append(full[previous:start])
        previous = end
    return "".join(pieces) + full[previous:]


def section_lesions(full: str) -> dict[str, str]:
    """Delete exact original spans only; no rewriting, normalization or additions."""
    if hashlib.sha256(full.encode("utf-8")).hexdigest() != BEST_SHA256:
        raise ValueError("Full Skill differs from the exact historical SHA256")
    for header in (EVIDENCE_HEADER, ANSWER_HEADER, "## Jeopardy-Style Wordplay", "## Final Answer Formatting"):
        if full.count(header) != 1:
            raise ValueError("Expected unique historical headings")
    evidence = _section_span(full, EVIDENCE_HEADER)
    answer = _section_span(full, ANSWER_HEADER)
    if full.count(SLOW_START) != 1 or full.count(SLOW_END) != 1:
        raise ValueError("Expected one complete slow-update block")
    slow = (full.index(SLOW_START), full.index(SLOW_END) + len(SLOW_END))
    if slow[0] >= slow[1] - len(SLOW_END):
        raise ValueError("Invalid slow-update marker order")
    outputs = {LESIONS[0]: _remove_spans(full, [evidence]),
               LESIONS[1]: _remove_spans(full, [answer, slow])}
    for text in outputs.values():
        if "## Final Answer Formatting" not in text or "## Jeopardy-Style Wordplay" not in text:
            raise ValueError("Lesion removed a required preserved section")
    return outputs


def _code_hashes(repo):
    data, _ = _deps(repo)
    names = ["skillopt/scope_evolution_v2/source_attribution.py", "scripts/source_attribution_mvp.py",
             "skillopt/scope_evolution_v2/source_retention.py", "skillopt/scope_evolution_v2/source_data.py",
             "skillopt/scope_evolution_v2/retention_routing.py",
             "scripts/source_retention_session_mvp.py", "scripts/paced_scope_mvp.py",
             "skillopt/cross_domain/runtime.py", "skillopt/cross_domain/gate.py",
             "skillopt/envs/searchqa/rollout.py", "skillopt/envs/searchqa/evaluator.py",
             "skillopt/envs/searchqa/prompts/rollout_system.md", "skillopt/model/openai_compatible_backend.py"]
    return {name: data.file_hash(Path(repo) / name) for name in names}


def _source_contract(repo, source, execution_mode):
    data, retention = _deps(repo)
    protocol = data.read_json(source / "source_protocol.json")
    manifest = data.read_json(source / "source_manifest.json")
    frozen = data.read_json(source / "frozen_source_protocol.json")
    if (data.digest(manifest) != protocol["manifest_hash"]
            or frozen["manifest_hash"] != data.digest(manifest)
            or frozen["protocol_hash"] != data.digest(protocol)
            or protocol["code_hashes"] != retention._code_hashes()
            or frozen["code_hashes"] != protocol["code_hashes"]
            or frozen["arms"] != protocol["arms"]
            or frozen["execution_mode"] != execution_mode):
        raise ValueError("Source protocol, manifest, code, arms or execution mode changed")
    for name, expected in frozen["calibration_artifact_hashes"].items():
        if data.file_hash(source / name) != expected:
            raise ValueError("Frozen source calibration artifact changed")
    for arm in ("base", "full"):
        info = protocol["arms"][arm]
        if data.file_hash(source / info["snapshot"]) != info["sha256"]:
            raise ValueError("Source Skill snapshot changed")
    if protocol["arms"]["full"]["sha256"] != BEST_SHA256:
        raise ValueError("Source does not contain the exact historical full Skill")
    return protocol, manifest, frozen


def _holdout_opened(source: Path, routing: Path) -> bool:
    paths = [source / "datasets/holdout.json", source / "holdout_summary.json",
             source / "searchqa_rollouts/holdout", routing / "datasets/source_holdout.json",
             routing / "datasets/controls_holdout.json", routing / "routes/holdout.json",
             routing / "routes/holdout_seal.json", routing / "controls/holdout/target_started.json"]
    if any(p.exists() for p in paths):
        return True
    # Fail closed on an unexpected per-call cache; read request metadata only.
    from skillopt.scope_evolution_v2.retention_routing import _cached_request_split
    return any(_cached_request_split(p) == "holdout" for p in (source / "calls").glob("*.json"))


def _validate(repo, root, protocol):
    data, _ = _deps(repo)
    source = Path(protocol["settings"]["source_dir"])
    _source_contract(repo, source, protocol["execution_mode"])
    if protocol["code_hashes"] != _code_hashes(repo):
        raise ValueError("Frozen attribution implementation changed")
    for name, sha in protocol["source_artifacts"].items():
        if data.file_hash(source / name) != sha:
            raise ValueError("Frozen source dependency changed")
    for info in protocol["arms"].values():
        if data.file_hash(root / info["snapshot"]) != info["sha256"]:
            raise ValueError("Frozen attribution Skill changed")
    seal = data.read_json(root / "attribution_seal.json")
    if seal["protocol_sha256"] != data.file_hash(root / "attribution_protocol.json"):
        raise ValueError("Attribution protocol seal changed")


def prepare(repo, root, source_dir, routing_dir, *, workers=6, seed=20260908,
            execution_mode="real_target_api"):
    repo, root, source, routing = map(lambda p: Path(p).resolve(), (repo, root, source_dir, routing_dir))
    if execution_mode not in {"real_target_api", "injected_test_double"} or workers != 6:
        raise ValueError("Use the fixed six-worker execution contract and an explicit valid mode")
    if any(root == p or p in root.parents or root in p.parents for p in (source, routing)):
        raise ValueError("Attribution must use its own separate non-nested directory")
    data, _ = _deps(repo)
    settings = {"source_dir": str(source), "routing_dir": str(routing), "workers": workers, "seed": seed,
                "logical_min_interval_seconds": 2.0}
    path = root / "attribution_protocol.json"
    if path.exists():
        protocol = data.read_json(path)
        if protocol["settings"] != settings or protocol["execution_mode"] != execution_mode:
            raise ValueError("Attribution settings changed; preserve this run")
        _validate(repo, root, protocol)
        return protocol
    if _holdout_opened(source, routing):
        raise ValueError("Cannot preregister lesions after source/routing holdout has opened")
    src, manifest, _ = _source_contract(repo, source, execution_mode)
    contents = {arm: (source / src["arms"][arm]["snapshot"]).read_text(encoding="utf-8")
                for arm in ("base", "full")}
    contents.update(section_lesions(contents["full"]))
    snapshots = {}
    for arm, text in contents.items():
        name = f"skills/{arm}.md"
        data.write_immutable_text(root / name, text)
        snapshots[arm] = {"snapshot": name, "sha256": data.file_hash(root / name), "characters": len(text),
                          "target_draw": "borrow_same_C_holdout" if arm in ("base", "full") else "new_fixed_section_lesion"}
    protocol = {"protocol_version": "fixed-section-attribution-v1", "settings": settings,
                "execution_mode": execution_mode, "prepared_utc": datetime.now(timezone.utc).isoformat(),
                "source_artifacts": {name: data.file_hash(source / name) for name in
                                     ("source_protocol.json", "source_manifest.json", "frozen_source_protocol.json")},
                "source_manifest_digest": data.digest(manifest), "arms": snapshots,
                "holdout_n": len(manifest["splits"]["holdout"]), "new_arms": list(LESIONS),
                "max_new_logical_target_calls": 2 * len(manifest["splits"]["holdout"]),
                "code_hashes": _code_hashes(repo),
                "comparisons": [[arm, "base"] for arm in ("full", *LESIONS)] + [[arm, "full"] for arm in LESIONS],
                "bootstrap": {"n_resamples": 5000, "seed": seed, "unit": "original task", "confidence": .95},
                "analysis_population": "common API-success IDs across base/full/both lesions; same denominator for all comparisons",
                "lesion_definition": {LESIONS[0]: "delete exact Evidence Selection section up to next heading",
                                      LESIONS[1]: "delete exact Concise section and inclusive complete SLOW_UPDATE marker block; retain all other bytes"},
                "notes": ["Preregistered after C calibration inspection but before source/D holdout opened; no E calibration or holdout-based edits.",
                          "Section-level attribution, not clean mechanism causality: content overlaps and prompt lengths are not matched.",
                          "The answer-form lesion also removes SLOW_UPDATE instance memories (Fragonard/Showboat/Bagpipes etc.); effects cannot be uniquely attributed to pure formatting.",
                          "Base/full reuse the identical C observations, not independent additional replications.",
                          "C's original three-arm common-success denominator may differ from this four-arm denominator; compare IDs before comparing headline rates.",
                          "All null/negative results remain; no candidate selection or threshold optimization.",
                          "Single generation per task, one sampling seed; no multiple-comparison or service-drift correction.",
                          "Original SearchQA prompts, context truncation and evaluator; only two fixed Skill texts differ.",
                          "API failures remain unscored; complete-case filtering may be biased.",
                          "Two-second pacing limits logical starts within one process, not internal wire retries or other processes.",
                          "Run source/D routing and target stages serially; no safety certification or scope-evolution claim."],
                **{key: src[key] for key in ("model", "required_provider_host", "effective_max_tokens_cap", "requested_max_completion_tokens")}}
    if _holdout_opened(source, routing):
        raise ValueError("Holdout opened during preparation; do not backfill the protocol")
    data.write_immutable_json(path, protocol)
    data.write_immutable_json(root / "attribution_seal.json", {"protocol_sha256": data.file_hash(path),
                              "holdout_opened_at_registration": False})
    return protocol


class _NoCalls:
    def call(self, *args, **kwargs):
        raise ValueError("Borrowed C rollout is missing; attribution may not regenerate Base/full")


class _GuardedAPI:
    """First-call health barrier and three-consecutive-failure circuit breaker."""
    def __init__(self, api):
        self.api, self.condition = api, threading.Condition()
        self.started = self.ready = self.stopped = False
        self.failures = 0

    def call(self, *args, **kwargs):
        with self.condition:
            first = not self.started
            if first:
                self.started = True
            else:
                while not self.ready and not self.stopped:
                    self.condition.wait()
            if self.stopped:
                raise RuntimeError("Attribution API batch stopped; preserve failed caches")
        try:
            result = self.api.call(*args, **kwargs)
            if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                raise ValueError("Attribution client must return an explicit boolean API status")
        except BaseException:
            with self.condition:
                self.stopped = True
                self.condition.notify_all()
            raise
        with self.condition:
            self.failures = 0 if result["ok"] else self.failures + 1
            self.stopped = self.stopped or (first and not result["ok"]) or self.failures >= 3
            self.ready = True
            self.condition.notify_all()
            if self.stopped:
                raise RuntimeError("Attribution API fail-fast; keep failed caches and use an explicitly new branch")
        return result


def summarize(outcomes, *, seed=20260908, bootstrap_n=5000):
    if set(outcomes) != set(ARMS):
        raise ValueError("Exactly Base/full/two fixed lesion arms are required")
    from skillopt.scope_evolution_v2.source_retention import summarize as source_summary
    base = source_summary(outcomes, seed=seed, bootstrap_n=bootstrap_n)
    # Aliases only for summary lookup; never mutate/relabel saved arm or Skill hashes.
    by_full = source_summary({"base": outcomes["full"], "source_base": outcomes["base"],
                              **{arm: outcomes[arm] for arm in LESIONS}}, seed=seed, bootstrap_n=bootstrap_n)
    if base["common_ids"] != by_full["common_ids"]:
        raise ValueError("Reference comparisons must use the same four-arm common population")
    return {**base, "vs_full": {arm: by_full["vs_base"][arm] for arm in LESIONS},
            "reference_aliases_are_summary_only": True}


def run_phase(repo, root, source_dir, routing_dir, phase, *, workers=6, seed=20260908,
              execution_mode="real_target_api", api=None):
    if phase not in PHASES:
        raise ValueError("Use prepare, test or report; this experiment has no calibration phase")
    repo, root, source = map(lambda p: Path(p).resolve(), (repo, root, source_dir))
    if phase == "test" and (api is not None) != (execution_mode == "injected_test_double"):
        raise ValueError("Test-double mode requires an injected client; real mode forbids injected clients")
    data, retention = _deps(repo)
    if phase == "prepare":
        return prepare(repo, root, source, routing_dir, workers=workers, seed=seed, execution_mode=execution_mode)
    path = root / "attribution_protocol.json"
    if not path.exists():
        raise ValueError("Prepare and seal attribution before any holdout is opened")
    protocol = prepare(repo, root, source, routing_dir, workers=workers, seed=seed, execution_mode=execution_mode)
    source_protocol, manifest, _ = _source_contract(repo, source, execution_mode)
    source_summary = data.read_json(source / "holdout_summary.json")
    if (source_summary.get("execution_mode") != execution_mode or source_summary.get("phase") != "test"
            or source_summary.get("split") != "holdout"
            or source_summary.get("protocol_hash") != data.digest(source_protocol)
            or set(source_summary.get("arms", {})) != set(source_protocol["arms"])):
        raise ValueError("Complete mode-matched original C holdout is required before E target execution")
    for arm in source_protocol["arms"]:
        if not (source / f"searchqa_rollouts/holdout/{arm}/results.jsonl").exists():
            raise ValueError("All original C holdout arms must finish before E")
    tasks = data.materialize_source_split(manifest, "holdout")
    if data.digest(tasks) != data.digest(data.read_json(source / "datasets/holdout.json")):
        raise ValueError("C holdout payload differs from its fixed manifest/cache")
    data.write_immutable_json(root / "datasets/holdout.json", tasks)
    borrowed = {}
    for arm in source_protocol["arms"]:
        content = (source / source_protocol["arms"][arm]["snapshot"]).read_text(encoding="utf-8")
        rows = retention._rollout(_NoCalls(), tasks, content, arm, "holdout", source, workers)
        if arm in ("base", "full"):
            borrowed[arm] = rows
    paths = ["holdout_summary.json", "datasets/holdout.json"] + [f"searchqa_rollouts/holdout/{arm}/results.jsonl" for arm in source_protocol["arms"]]
    provenance = {name: data.file_hash(source / name) for name in paths}
    data.write_immutable_json(root / "borrowed_source_holdout_artifacts.json", provenance)
    if phase == "report":
        client = _NoCalls()
        if not all((root / f"searchqa_rollouts/holdout/{arm}/results.jsonl").exists() for arm in LESIONS):
            raise ValueError("Both attribution arms must complete before report")
    else:
        data.write_immutable_json(root / "target_started.json", {"protocol_sha256": data.file_hash(path), "split": "holdout"})
        client = _GuardedAPI(api if api is not None else retention.SourceCachedAPI(repo, root, protocol))
    outcomes = dict(borrowed)
    for arm in LESIONS:
        skill = (root / protocol["arms"][arm]["snapshot"]).read_text(encoding="utf-8")
        outcomes[arm] = retention._rollout(client, tasks, skill, arm, "holdout", root, workers)
    summary = {"phase": "test", "split": "holdout", "execution_mode": execution_mode,
               "protocol_sha256": data.file_hash(path), "source_draws_shared_with_C": True,
               "section_level_not_clean_mechanism_causality": True,
               "borrowed_source_artifact_hashes": provenance,
               "skill_sha256": {arm: info["sha256"] for arm, info in protocol["arms"].items()},
               "new_logical_target_calls": sum(len(outcomes[arm]) for arm in LESIONS),
               **summarize(outcomes, seed=seed, bootstrap_n=5000)}
    data.write_immutable_json(root / "holdout_summary.json", summary)
    lines = ["# 固定 Section Lesion 来源归因", "", "同一 C holdout / Base / full draws；不是独立重复，也不是干净机制因果隔离。", "",
             "| Arm | 四臂共同成功 N | EM | F1 | API error |", "|---|---:|---:|---:|---:|"]
    def pct(v):
        return "N/A" if v is None else f"{v*100:.2f}%"
    for arm, row in summary["arms"].items():
        lines.append(f"| {arm} | {row['n_common_success']} | {pct(row['em'])} | {pct(row['f1'])} | {row['n_api_error']} |")
    lines += ["", "| Candidate | Reference | Wins | Losses | EM delta | Paired bootstrap 95% |", "|---|---|---:|---:|---:|---|"]
    for ref in ("base", "full"):
        for arm, result in summary[f"vs_{ref}"].items():
            lo, hi = result["paired_bootstrap95"]["em"]
            lines.append(f"| {arm} | {ref} | {result['paired']['wins']} | {result['paired']['losses']} | {pct(result['delta']['em'])} | {pct(lo)} to {pct(hi)} |")
    lines += ["", *[f"- {note}" for note in protocol["notes"]], ""]
    data.write_immutable_text(root / "holdout_report.md", "\n".join(lines))
    return summary
