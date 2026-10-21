#!/usr/bin/env python3
"""Zero-call feature profile of training (or generated) OfficeQA-style items (2026-10-16).

Tags every selected item with ``skillopt.skill_features.tagger`` and aggregates the tags into a profile. Items carrying
a validation, test, held-out, reserve or calibration label are refused (labels compared lower-cased, trimmed, with every
run of spaces, tabs, "-" or "_" read as one "_"): the profile steers generation and edit gating, so only training-side
or generated items may enter it.
``skill_confirmation`` is the protocol's validation partition, refused unless ``--generated`` declares a generated
selection set whose every selected id starts with "gen-". Every item record keeps the digest of its public fields, so
that a probe can be checked to have measured exactly these items.

Usage:
  build_training_profile.py build --panel <panel.json> [--partition development] [--tasks <split.json>:<key>]
      [--generated] --output <new profile.json>
  build_training_profile.py compare --target <profile.json> --candidate <profile.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skillopt.skill_features import profile as fp  # noqa: E402
from skillopt.skill_features import tagger  # noqa: E402

VERSION = "training-profile-builder-v1"
FORBIDDEN = {"final", "test", "holdout", "held_out", "heldout", "reserve", "calibration", "verifier_calibration",
             "val", "validation", "dev_val", "selection"}
VALIDATION_PARTITION = "skill_confirmation"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def public_digest(public):
    return hashlib.sha256(json.dumps(public, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _norm_label(value):
    return re.sub(r"[\s_-]+", "_", str(value).strip().lower())


def _labels(row):
    labels = [row.get(k) for k in ("partition", "split", "part", "role")]
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    labels += [meta.get(k) for k in ("part", "partition", "split", "role")]
    return {_norm_label(x) for x in labels if x is not None}


def load(panel_path, partition=None, tasks_spec=None, generated=False):
    """[(id, question, answer, context, public digest)] of the selected rows. A panel row has task_id/partition, a
    pilot row id/meta; any forbidden label anywhere in a SELECTED row refuses the build; the validation partition is
    admitted only as a declared generated set."""
    data = json.loads(Path(panel_path).read_text(encoding="utf-8"))
    rows = data["tasks"] if isinstance(data, dict) and "tasks" in data else data["items"] if isinstance(data, dict) else data
    wanted = None
    if tasks_spec:
        path, _, key = tasks_spec.rpartition(":")
        if not path or not key:
            raise SystemExit("--tasks <split.json>:<key>")
        wanted = set(json.loads(Path(path).read_text(encoding="utf-8"))[key])
    selected = []
    for row in rows:
        ident = row.get("task_id", row.get("id"))
        if partition and _norm_label(row.get("partition")) != _norm_label(partition):
            continue
        if wanted is not None and ident not in wanted:
            continue
        labels = _labels(row)
        if labels & FORBIDDEN:
            raise SystemExit("A validation/test/held-out/reserve item was selected: refused (%s)" % ident)
        if generated and not str(ident).startswith("gen-"):
            raise SystemExit("A declared generated set selects only gen- ids (%s)" % ident)
        if VALIDATION_PARTITION in labels and not generated:
            raise SystemExit("The validation partition is admitted only as a declared generated set (%s)" % ident)
        selected.append((ident, row["public"]["question"], row.get("private", {}).get("answer"),
                         row["public"].get("context"), public_digest(row["public"])))
    if wanted is not None and {s[0] for s in selected} != wanted:
        raise SystemExit("The task list names ids the panel does not select")
    if not selected:
        raise SystemExit("No item selected")
    if len({s[0] for s in selected}) != len(selected):
        raise SystemExit("Duplicate item ids")
    return selected


def build(panel_path, output, partition=None, tasks_spec=None, generated=False):
    out = Path(output)
    if out.exists():
        raise SystemExit("Use a new output file (a profile is written once)")
    selected = load(panel_path, partition, tasks_spec, generated)
    records = {ident: {**tagger.tag_item(q, a, c), "public_digest": d} for ident, q, a, c, d in selected}
    value = {"version": VERSION, "tagger_version": tagger.VERSION, "profile_version": fp.VERSION,
             "source": {"panel": str(Path(panel_path).resolve()), "panel_sha256": _sha(panel_path),
                        "partition": partition, "tasks": tasks_spec, "generated": generated, "items": len(records)},
             "items": records, "profile": fp.profile(records.values())}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as handle:  # exclusive: never overwrites
        json.dump(value, handle, ensure_ascii=False, indent=1, sort_keys=True)
    return value


def summary_lines(value):
    p = value["profile"]
    lines = ["items %d (tagger %s)" % (p["items"], value.get("tagger_version"))]
    for axis in fp.AXES:
        lines.append("%-12s %s" % (axis, ", ".join("%s %.2f" % kv for kv in list(p[axis].items())[:10])))
    lines.append("%-12s %s" % ("tags", ", ".join("%s %.2f" % kv for kv in list(p["tag_frequency"].items())[:24])))
    for key in ("pages", "issues", "context_chars"):
        lines.append("%-12s %s" % (key, p[key]))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--panel", required=True)
    b.add_argument("--partition")
    b.add_argument("--tasks")
    b.add_argument("--generated", action="store_true")
    b.add_argument("--output", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--target", required=True)
    c.add_argument("--candidate", required=True)
    args = parser.parse_args(argv)
    if args.command == "build":
        value = build(args.panel, args.output, args.partition, args.tasks, args.generated)
        print("\n".join(summary_lines(value)))
    else:
        target = json.loads(Path(args.target).read_text(encoding="utf-8"))["profile"]
        candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))["profile"]
        print(json.dumps(fp.compare(target, candidate), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
