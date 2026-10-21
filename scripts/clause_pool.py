#!/usr/bin/env python3
"""Clause pool (architecture X, 2026-10-16; design docs/handoff/two-architectures-design-20261016.md section 6):
decompose candidates into edits, register the noise model, screen and confirm edits on their trigger subsets of the
training items, compose the final Skill. Zero model calls: every measurement is a ``scripts/weak_solver_probe.py``
directory, and every one is checked before use -- a completed summary of its own config, the measured Skill text
(its probe hash), the registered gate items (each item's public fields and its scoring inputs -- the public fields and
the private fields the benchmark's scorer reads, SCORED_PRIVATE, e.g. OfficeQA's reference answer; the whole private
record for another benchmark -- re-read from the probe's own item sources), the registered solver
configuration, the registered number of runs for every gate item (RUNS_HALF per noise half, RUNS_MEASURED per screen or
confirmation probe, at least MIN_PARENT_RUNS parent runs per item in all), and its place in time and identity (the noise
is registered from two distinct probes; a screen or confirmation probe starts after the registration and is none of the
probes used before). Every output is sealed (its content hash is recomputed whenever it is read) and written once
(atomically: a temporary file linked into place, never over an existing one). Skill files are read with universal
newlines, as the probe reads them.

Usage:
  clause_pool.py decompose --parent <parent.md> --candidate <name>=<file.md> [...] --output <new dir>
  clause_pool.py noise --parent <parent.md> --half <probe dir>:<skill> --half <probe dir>:<skill>
      --items <gate profile.json> --output <new.json>
  clause_pool.py screen --edits <dir>/edits.json --noise <noise.json> --parent-runs <probe dir>:<skill> [...]
      --measured <probe dir> --output <new.json>
  clause_pool.py confirm --screen <screen.json> --parent-runs <probe dir>:<skill> [...] --measured <probe dir>
      --output <new.json>
  clause_pool.py compose --edits <dir>/edits.json --decisions <confirm.json> [--edits ... --decisions ...]
      [--sources a,b] [--whole] --output <new.md>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import weak_solver_probe as probe  # noqa: E402
from scripts.build_training_profile import public_digest  # noqa: E402
from skillopt.clause_pool import edits as ed  # noqa: E402
from skillopt.clause_pool import gate as gt  # noqa: E402
from skillopt.coevolution_v5.core import seal, verify  # noqa: E402

VERSION = "clause-pool-tool-v1"
CODE = ("skillopt/clause_pool/edits.py", "skillopt/clause_pool/gate.py", "skillopt/skill_features/tagger.py",
        "scripts/clause_pool.py", "scripts/build_training_profile.py")
SOLVER_KEYS = ("version", "backend", "model", "benchmark", "max_tokens", "thinking", "reasoning_effort", "temperature",
               "proxy", "response_model_ids", "session_id_header", "prompt")
STAMP = "%Y-%m-%dT%H:%M:%S%z"
# Registered run counts (design section 6): two runs per gate item in each noise half and in each screen or confirmation
# probe; the parent's runs on the gate items total at least four per item.
RUNS_HALF, RUNS_MEASURED, MIN_PARENT_RUNS = 2, 2, 4
# The private fields each benchmark's scorer reads (skillopt/continual_eval/backends.score): an item file and a panel
# partition holding the same questions and answers score identically even when their provenance keys differ.
SCORED_PRIVATE = {"officeqa": ("answer",), "searchqa": ("answers",)}


def scoring_digest(benchmark, row):
    fields = SCORED_PRIVATE.get(benchmark)
    private = row["private"] if fields is None else {k: row["private"].get(k) for k in fields}
    return probe.digest({"benchmark": benchmark, "public": row["public"], "private": private})


def _sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_identity():
    return {name: _sha_file(PROJECT_ROOT / name) for name in CODE}


def _absent(*paths):
    for path in paths:
        if Path(path).exists():
            raise SystemExit("Output already exists (outputs are written once): %s" % path)


def _write_once(path, value):
    """Write a complete file at a new path: a temporary file in the same directory, linked into place (the link fails
    if the path exists), so that a failure leaves either nothing or the whole file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    try:
        with open(temporary, "x", encoding="utf-8") as handle:
            handle.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=1,
                                                                         sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sealed(path):
    try:
        return verify(json.loads(Path(path).read_text(encoding="utf-8")))
    except ValueError:
        raise SystemExit("A sealed file does not match its content hash: %s" % path) from None


def _now():
    return time.strftime(STAMP)


class ProbeDir:
    """A completed probe directory, checked against its own config."""

    def __init__(self, spec_or_dir):
        self.dir = Path(spec_or_dir)
        self.config = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        summary_path = self.dir / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        self.hash = probe.digest(self.config)
        if summary.get("status") != "completed" or summary.get("config_hash") != self.hash:
            raise SystemExit("Probe %s: no completed summary of this config" % self.dir.name)
        self.started = datetime.strptime(self.config["started"], STAMP)

    def solver(self):
        return {k: self.config.get(k) for k in SOLVER_KEYS}

    def skill_hash(self, skill):
        return self.config["skills"].get(skill, {}).get("hash")

    def items(self):
        """{item id: (digest of its public fields, digest of its scoring inputs)}, re-read from the probe's own item
        sources (checked unchanged)."""
        rows = [row for spec in self.config["items"] for row in probe.load_items(spec)]
        if probe.digest(sorted(probe.digest(r) for r in rows)) != self.config["items_hash"]:
            raise SystemExit("Probe %s: its item sources changed" % self.dir.name)
        return {r["id"]: (public_digest(r["public"]), scoring_digest(self.config["benchmark"], r)) for r in rows}

    def runs(self, skill, items, required=None):
        """{item: [statuses]} for the given items; each needs exactly the probe's number of runs, which must be
        ``required`` when given."""
        expected, found = self.config["runs"], {}
        if required is not None and expected != required:
            raise SystemExit("Probe %s: %s runs per item, the registration needs %d" % (self.dir.name, expected, required))
        for path in sorted((self.dir / "records" / skill).glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            runs = found.setdefault(record["item"], {})
            if record.get("skill") != skill or record["run"] in runs:
                raise SystemExit("Probe %s: inconsistent records of %s" % (self.dir.name, skill))
            runs[record["run"]] = record["status"]
        out = {}
        for item in items:
            runs = found.get(item, {})
            if sorted(runs) != list(range(expected)):
                raise SystemExit("Probe %s: incomplete runs of %s on %s" % (self.dir.name, skill, item))
            out[item] = [runs[k] for k in range(expected)]
        return out


def _spec(spec):
    directory, _, skill = spec.rpartition(":")
    if not directory or not skill:
        raise SystemExit("A run source is <probe dir>:<skill>")
    return ProbeDir(directory), skill


def _check_probe(p, registered):
    if p.solver() != registered["solver"]:
        raise SystemExit("Probe %s: solver configuration differs from the registration" % p.dir.name)
    found = p.items()
    if any(found.get(i, (None,))[0] != d for i, d in registered["items"].items()):
        raise SystemExit("Probe %s: did not measure exactly the registered gate items" % p.dir.name)
    if any(found[i][1] != d for i, d in registered["scoring"].items()):
        raise SystemExit("Probe %s: scores the gate items against other references" % p.dir.name)


def _parent_runs(specs, registered):
    hashes, merged = [], {}
    for spec in specs:
        p, skill = _spec(spec)
        if p.hash in hashes:
            raise SystemExit("A parent probe is named twice")
        if p.skill_hash(skill) != registered["parent"]["probe_hash"]:
            raise SystemExit("Probe %s: %s is not the registered parent text" % (p.dir.name, skill))
        _check_probe(p, registered)
        hashes.append(p.hash)
        for item, statuses in p.runs(skill, registered["items"]).items():
            merged.setdefault(item, []).extend(statuses)
    if not hashes:
        raise SystemExit("At least one --parent-runs source")
    short = sorted(i for i in registered["items"] if len(merged[i]) < registered["runs"]["parent_min"])
    if short:
        raise SystemExit("The parent runs total fewer than %d on %d gate items" % (registered["runs"]["parent_min"],
                                                                                 len(short)))
    return merged, sorted(hashes)


def _fresh(p, registered, used):
    if p.hash in used:
        raise SystemExit("Probe %s was already used: a measurement needs fresh runs" % p.dir.name)
    if p.started <= datetime.strptime(registered["registered"], STAMP):
        raise SystemExit("Probe %s started before the noise model was registered" % p.dir.name)


def _item_tags(registered):
    profile = Path(registered["items_profile"])
    if _sha_file(profile) != registered["items_profile_sha256"]:
        raise SystemExit("The gate items file changed after the registration")
    items = json.loads(profile.read_text(encoding="utf-8"))["items"]
    return {item: items[item]["tags"] for item in registered["items"]}


def load_edits(path):
    """The sealed edits record, with every Skill file it names checked against its probe hash."""
    value = _sealed(path)
    skills = Path(path).parent / "skills"
    for entry in [*value["edits"], *value["wholes"], value["parent"]]:
        text = (skills / entry["skill_file"]).read_text(encoding="utf-8")
        if probe.digest(text) != entry["probe_hash"]:
            raise SystemExit("A Skill file changed after decomposition: %s" % entry["skill_file"])
    return value


# ----------------------------------------------------------------------------- commands
def decompose(parent_path, candidates, output):
    out = Path(output)
    _absent(out)
    parent = Path(parent_path).read_text(encoding="utf-8")
    edits, wholes, sources, texts = [], [], {}, {}
    for spec in candidates:
        name, _, path = spec.partition("=")
        if not ed.ID.fullmatch(name or "") or not path or name in sources or not ed.ID.fullmatch(name + "-whole"):
            raise SystemExit("--candidate <unique name>=<file> (a name of at most 34 letters, digits, _ or -)")
        text = Path(path).read_text(encoding="utf-8")
        try:
            found = ed.decompose(parent, text, name)
        except ValueError as exc:
            raise SystemExit("%s: %s" % (name, exc)) from None
        for e in found:
            texts[e["id"]] = ed.apply(parent, [e])
            e.update({"skill_file": e["id"] + ".md", "probe_hash": probe.digest(texts[e["id"]]),
                      "no_effect": ed.no_effect(parent, [e])})
        edits.extend(found)
        whole = {"id": name + "-whole", "source": name, "kind": "whole", "tags": [], "skill_file": name + "-whole.md",
                 "probe_hash": probe.digest(text), "candidate_path": str(Path(path).resolve())}
        texts[whole["id"]] = text
        wholes.append(whole)
        sources[name] = {"path": str(Path(path).resolve()), "probe_hash": probe.digest(text), "edits": len(found)}
    out.mkdir(parents=True)
    for ident, text in texts.items():
        _write_once(out / "skills" / (ident + ".md"), text)
    _write_once(out / "skills" / "parent.md", parent)
    value = seal({"version": VERSION, "edits_version": ed.VERSION, "code": code_identity(),
                  "parent": {"path": str(Path(parent_path).resolve()), "skill_file": "parent.md",
                             "probe_hash": probe.digest(parent)},
                  "candidates": sources, "edits": edits, "wholes": wholes, "created": _now()})
    _write_once(out / "edits.json", value)
    return value


def noise(parent_path, halves, profile_path, output):
    _absent(output)
    if len(halves) != 2:
        raise SystemExit("Exactly two --half sources: two independent measurements of the parent")
    parent = Path(parent_path).read_text(encoding="utf-8")
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    items = {item: record["public_digest"] for item, record in profile["items"].items()}
    (a, skill_a), (b, skill_b) = (_spec(h) for h in halves)
    if a.hash == b.hash:
        raise SystemExit("The two halves are the same probe")
    if a.solver() != b.solver():
        raise SystemExit("The two halves differ in solver configuration")
    found = a.items()
    if any(i not in found for i in items):
        raise SystemExit("Probe %s: did not measure exactly the registered gate items" % a.dir.name)
    registered = {"solver": a.solver(), "items": items, "scoring": {i: found[i][1] for i in items},
                  "parent": {"probe_hash": probe.digest(parent)},
                  "runs": {"half": RUNS_HALF, "measured": RUNS_MEASURED, "parent_min": MIN_PARENT_RUNS}}
    for p, skill in ((a, skill_a), (b, skill_b)):
        if p.skill_hash(skill) != registered["parent"]["probe_hash"]:
            raise SystemExit("Probe %s: %s is not the parent text" % (p.dir.name, skill))
        _check_probe(p, registered)
    value = seal({**gt.noise(a.runs(skill_a, items, RUNS_HALF), b.runs(skill_b, items, RUNS_HALF), items),
                  "tool": VERSION, "code": code_identity(), "solver": registered["solver"], "items": items,
                  "scoring": registered["scoring"], "runs": registered["runs"],
                  "items_profile": str(Path(profile_path).resolve()), "items_profile_sha256": _sha_file(profile_path),
                  "parent": {"path": str(Path(parent_path).resolve()), "probe_hash": registered["parent"]["probe_hash"]},
                  "halves": [{"path": str(p.dir.resolve()), "skill": s, "config_hash": p.hash}
                             for p, s in ((a, skill_a), (b, skill_b))],
                  "registered": _now()})
    _write_once(output, value)
    return value


def _measure_all(entries, measured, item_tags, parent, registered):
    results = []
    for e in entries:
        if e.get("no_effect") or measured.skill_hash(e["id"]) is None:
            continue
        if measured.skill_hash(e["id"]) != e["probe_hash"]:
            raise SystemExit("Probe %s measured another text under %s" % (measured.dir.name, e["id"]))
        runs = measured.runs(e["id"], registered["items"], registered["runs"]["measured"])
        m = gt.measure(e["tags"], item_tags, runs, parent)
        results.append((e, m))
    return results


def screen(edits_path, noise_path, parent_specs, measured_dir, output):
    _absent(output)
    edits_value, registered = load_edits(edits_path), _sealed(noise_path)
    if edits_value["parent"]["probe_hash"] != registered["parent"]["probe_hash"]:
        raise SystemExit("The edits and the noise registration have different parents")
    item_tags = _item_tags(registered)
    parent, parent_hashes = _parent_runs(parent_specs, registered)
    measured = ProbeDir(measured_dir)
    _fresh(measured, registered, {h["config_hash"] for h in registered["halves"]})
    _check_probe(measured, registered)
    results = []
    for e, m in _measure_all([*edits_value["edits"], *edits_value["wholes"]], measured, item_tags, parent,
                             registered):
        results.append({"id": e["id"], "source": e["source"], "kind": e.get("kind", "edit"), "tags": e["tags"], **m,
                        "screen": gt.screen(m, registered["v"])})
    if not results:
        raise SystemExit("No edit of the edits file was measured in this probe")
    value = seal({"tool": VERSION, "gate_version": gt.VERSION, "code": code_identity(),
                  "edits": str(Path(edits_path).resolve()), "edits_hash": edits_value["record_hash"],
                  "noise": str(Path(noise_path).resolve()), "noise_hash": registered["record_hash"],
                  "v": registered["v"], "parent_probes": parent_hashes,
                  "measured": {"path": str(measured.dir.resolve()), "config_hash": measured.hash},
                  "results": results, "passed": [r["id"] for r in results if r["screen"]["passed"]],
                  "created": _now()})
    _write_once(output, value)
    return value


def confirm(screen_path, parent_specs, measured_dir, output):
    _absent(output)
    screened = _sealed(screen_path)
    edits_value, registered = load_edits(screened["edits"]), _sealed(screened["noise"])
    if edits_value["record_hash"] != screened["edits_hash"] or registered["record_hash"] != screened["noise_hash"]:
        raise SystemExit("The edits or the noise registration changed after the screen")
    item_tags = _item_tags(registered)
    parent, parent_hashes = _parent_runs(parent_specs, registered)
    measured = ProbeDir(measured_dir)
    _fresh(measured, registered, {h["config_hash"] for h in registered["halves"]} | {screened["measured"]["config_hash"]})
    _check_probe(measured, registered)
    by_id = {e["id"]: e for e in [*edits_value["edits"], *edits_value["wholes"]]}
    passed = [by_id[i] for i in screened["passed"]]
    confirmed = {e["id"]: m for e, m in _measure_all(passed, measured, item_tags, parent, registered)}
    decisions = []
    for r in screened["results"]:
        entry = {**r, "confirm": None, "accepted": False}
        if r["screen"]["passed"]:
            m = confirmed.get(r["id"])
            if m is None:
                entry["confirm"] = {"passed": False, "pending": "not_measured_in_confirmation"}
            else:
                entry["confirm"] = {**m, **gt.confirm(m)}
                entry["accepted"] = entry["confirm"]["passed"]
        decisions.append(entry)
    value = seal({"tool": VERSION, "gate_version": gt.VERSION, "code": code_identity(),
                  "screen": str(Path(screen_path).resolve()), "screen_hash": screened["record_hash"],
                  "edits": screened["edits"], "edits_hash": screened["edits_hash"], "noise_hash": screened["noise_hash"],
                  "parent_probes": parent_hashes,
                  "measured": {"path": str(measured.dir.resolve()), "config_hash": measured.hash},
                  "decisions": decisions, "accepted": [d["id"] for d in decisions if d["accepted"]],
                  "created": _now()})
    _write_once(output, value)
    return value


def compose(edits_path, decisions_path, output, sources=None, whole=False, more=()):
    """``bzero + accepted edits`` (or, with ``whole``, the accepted whole candidate with the largest confirmation-round
    Δ_total; the parent when none). ``more``: further (edits, decisions) pairs of the same parent -- for example the
    old and the new candidates' gates -- composed together. Edits apply in confirmation-round strength order
    (Δ_trig/|S|); one that conflicts with a stronger one, or whose new text repeats a stronger one's (up to
    whitespace), is skipped and recorded."""
    receipt = str(output) + ".json"
    _absent(output, receipt)
    loaded, parent, accepted, every_id = [], None, {}, set()
    for e_path, d_path in [(edits_path, decisions_path), *more]:
        edits_value, decided = load_edits(e_path), _sealed(d_path)
        if decided["edits_hash"] != edits_value["record_hash"]:
            raise SystemExit("The decisions belong to another edits file")
        ids = {e["id"] for e in edits_value["edits"]} | {w["id"] for w in edits_value["wholes"]}
        if ids & every_id:  # an id names one text of one gate: decisions never cross edits files
            raise SystemExit("An edit or candidate id appears in two edits files: %s" % sorted(ids & every_id)[0])
        every_id |= ids
        skills = Path(e_path).parent / "skills"
        if parent is None:
            parent_hash = edits_value["parent"]["probe_hash"]
            parent = (skills / edits_value["parent"]["skill_file"]).read_text(encoding="utf-8")
        elif edits_value["parent"]["probe_hash"] != parent_hash:
            raise SystemExit("The edits files have different parents")
        for d in decided["decisions"]:
            if d["accepted"]:
                if d["id"] not in ids:
                    raise SystemExit("A decision names no edit of its edits file: %s" % d["id"])
                accepted[d["id"]] = d
        loaded.append((edits_value, decided, skills))
    wanted = set(sources.split(",")) if sources else None
    record = {"tool": VERSION, "edits_hash": [v["record_hash"] for v, _, _ in loaded],
              "decisions_hash": [d["record_hash"] for _, d, _ in loaded],
              "sources": sorted(wanted) if wanted else "all", "ordering": "confirmation round"}
    if whole:
        best = max((d for d in accepted.values() if d["kind"] == "whole" and (not wanted or d["source"] in wanted)),
                   key=lambda d: (gt.exact(d["confirm"], "delta_total"), d["id"]), default=None)
        entry = next(((w, skills) for v, _, skills in loaded for w in v["wholes"] if best and w["id"] == best["id"]),
                     None)
        text = parent if entry is None else (entry[1] / entry[0]["skill_file"]).read_text(encoding="utf-8")
        record["chosen"] = None if entry is None else entry[0]["id"]
    else:
        pool = [e for v, _, _ in loaded for e in v["edits"] if e["id"] in accepted
                and (not wanted or e["source"] in wanted)]
        strength = lambda e: gt.exact(accepted[e["id"]]["confirm"], "delta_trigger") / max(1, accepted[e["id"]]["n_trigger"])
        pool.sort(key=lambda e: (-strength(e), e["id"]))
        chosen, skipped, repeated = [], [], []
        for e in pool:
            if e["new"] is not None and any(c["new"] is not None and ed._norm(c["new"]) == ed._norm(e["new"])
                                            for c in chosen):
                repeated.append(e["id"])
                continue
            try:
                ed.apply(parent, chosen + [e])
            except ed.Conflict:
                skipped.append(e["id"])
                continue
            chosen.append(e)
        text = ed.apply(parent, chosen)
        record.update({"included": [e["id"] for e in chosen], "skipped_conflicts": skipped,
                       "skipped_repeats": repeated})
    record = seal({**record, "probe_hash": probe.digest(text), "created": _now()})
    _write_once(output, text)
    try:
        _write_once(receipt, record)  # the receipt marks a complete composition: written last
    except BaseException:
        Path(output).unlink()
        raise
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("decompose")
    d.add_argument("--parent", required=True)
    d.add_argument("--candidate", action="append", required=True)
    d.add_argument("--output", required=True)
    n = sub.add_parser("noise")
    for name in ("--parent", "--items", "--output"):
        n.add_argument(name, required=True)
    n.add_argument("--half", action="append", required=True)
    s = sub.add_parser("screen")
    for name in ("--edits", "--noise", "--measured", "--output"):
        s.add_argument(name, required=True)
    s.add_argument("--parent-runs", action="append", required=True)
    c = sub.add_parser("confirm")
    for name in ("--screen", "--measured", "--output"):
        c.add_argument(name, required=True)
    c.add_argument("--parent-runs", action="append", required=True)
    m = sub.add_parser("compose")
    m.add_argument("--edits", action="append", required=True)
    m.add_argument("--decisions", action="append", required=True)
    m.add_argument("--output", required=True)
    m.add_argument("--sources")
    m.add_argument("--whole", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "decompose":
        value = decompose(args.parent, args.candidate, args.output)
        for e in value["edits"]:
            print("%-18s %-7s at=%-3d %s tags=%s" % (e["id"], e["op"], e["at"], "no-effect" if e["no_effect"] else "",
                                                     ",".join(e["tags"]) or "(generic)"))
        print("%d edits (%d to measure), %d wholes" % (len(value["edits"]),
                                                       sum(not e["no_effect"] for e in value["edits"]), len(value["wholes"])))
    elif args.command == "noise":
        value = noise(args.parent, args.half, args.items, args.output)
        print(json.dumps({k: value[k] for k in ("v", "v_shown", "n_items", "items_known_in_both", "mean_difference",
                                                "registered")}))
    elif args.command == "screen":
        value = screen(args.edits, args.noise, args.parent_runs, args.measured, args.output)
        for r in value["results"]:
            print("%-18s n=%-3d cov=%.2f Δtrig=%+.2f Δrest=%+.2f thr=%s %s" % (
                r["id"], r["n_trigger"], r["coverage"], r["delta_trigger"], r["delta_rest"], r["screen"]["threshold"],
                "PASS" if r["screen"]["passed"] else (r["screen"]["pending"] or "-")))
    elif args.command == "confirm":
        value = confirm(args.screen, args.parent_runs, args.measured, args.output)
        print("accepted:", ", ".join(value["accepted"]) or "(none)")
    else:
        if len(args.edits) != len(args.decisions):
            raise SystemExit("One --decisions per --edits, in the same order")
        print(json.dumps(compose(args.edits[0], args.decisions[0], args.output, args.sources, args.whole,
                                 more=list(zip(args.edits[1:], args.decisions[1:])))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
