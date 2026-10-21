"""Zero-call compliance audit for the verification-note binding study (and, as a dry run, the rubric-form study):
did the analysts of a bound arm actually answer the failed checks they were shown? Prompt assignment is recorded by the
study (`binding_applied`); obedience is not, so this reads the sealed raw proposals. Per block and arm:
  - the failed checks the arm's failure analysts saw (verifier rows: host-fail rows with a failing check, authorized
    blocks only), by category (regex over the obligation text);
  - the arm's failure minibatches (raw patches with source_type failure): whether the FIRST edit's content names a
    category of a failed check, whether any edit does, and whether `reasoning` refers to a check or note;
  - the share of failed-check categories answered by at least one edit.
Reported for each arm named on the command line, so a bound arm can be set against its base arm. Descriptive only;
category matching is a keyword heuristic. Never reads the private answer or test data.
Usage: compliance.py --arms global_text,global_text_bound <study dir>:<block> [...]"""
import collections
import json
import os
import re
import sys

# Narrow, check-shaped categories only (an OfficeQA judge check names a rounding, unit, list, date or tag obligation;
# broad notions such as "computation" or "scope" match almost any edit and are deliberately left out, as are evidence
# strings, which quote the output). A category counts as answered only by an edit whose content names the same thing.
CATEGORIES = [
    ("rounding", r"round(ed|ing)? to|decimal place|hundredth|tenth|thousandth|nearest whole|significant figure"),
    ("unit/scale", r"in (billions|millions|thousands)|billions? of|millions? of|unit (of|conversion|requested)|percent(age)? (sign|form)|as a percent"),
    ("list/brackets", r"bracket|comma-separated|comma separated|enclosed list|\blist of (values|items)"),
    ("date", r"date format|long date|month name|\bmonth, day|spelled[- ]out month|day of the month|format the date|as a date"),
    ("answer tag", r"answer tag|<answer>|nothing else in|only the (final|single) (value|number|answer)|no commentary|no units in|extra text"),
]


def read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def categories(text):
    low = text.lower()
    return {name for name, pattern in CATEGORIES if re.search(pattern, low)}


def failed_checks(root, block, arm):
    """(authorized, [obligation texts of failing checks on host-fail rows]) of the verifier run the arm's analysts saw."""
    folder = os.path.join(root, "verifier", "%d-%s" % (block, arm))
    if not os.path.isdir(folder):
        return None, []
    summary = read(os.path.join(folder, "summary.json"))
    found = []
    for name in sorted(os.listdir(os.path.join(folder, "rows"))):
        row = read(os.path.join(folder, "rows", name))
        if row.get("host_status") != "fail":
            continue
        for probe in row.get("probes", []):
            if probe.get("verdict") == "fail" or probe.get("outcome") == "fail":
                found.append(str(probe.get("obligation", "")) + " " + str(probe.get("check", "")))  # never the evidence
    return bool(summary.get("authorized")), found


def main(argv):
    arms, reference = None, None
    specs = []
    i = 0
    while i < len(argv):
        if argv[i] == "--arms":
            arms = argv[i + 1].split(",")
            i += 2
        elif argv[i] == "--reference":  # the checks an UNEXPOSED control arm is scored against (what the bound arm saw)
            reference = argv[i + 1]
            i += 2
        else:
            specs.append(argv[i])
            i += 1
    if not arms:
        raise SystemExit("--arms a,b[,c] [--reference <judged arm>] required")
    totals = {arm: collections.Counter() for arm in arms}
    for spec in specs:
        root, block = spec.rsplit(":", 1)
        block = int(block)
        label = os.path.basename(os.path.dirname(root.rstrip("/")))
        candidates = read(os.path.join(root, "blocks", str(block), "candidates.json"))
        for arm in arms:
            disposition = candidates["dispositions"].get(arm, {})
            base = disposition.get("base_arm") or arm
            if base not in candidates.get("verifier", {}) and reference:
                base = reference  # a control arm saw no checks: score its edits against the reference arm's checks
            authorized, checks = failed_checks(root, block, base)
            shown = collections.Counter()
            for text in checks:
                for c in categories(text) or {"other"}:
                    shown[c] += 1
            path = os.path.join(root, "native", str(block), arm, "result.json")
            if not os.path.exists(path) or disposition.get("status") != "candidate_ready":
                print("block %s:%d %-19s proposal not available (%s)" % (label, block, arm, disposition.get("status")))
                continue
            raw = [item for item in read(path).get("raw", []) if item.get("source_type") == "failure"]
            first_hits = any_hits = reasoning_hits = 0
            answered = set()
            for item in raw:
                patch = item.get("patch") or {}
                edits = patch.get("edits") or []
                contents = [str(e.get("content", "")) + " " + str(e.get("target", "")) for e in edits]
                shown_set = {c for c in shown if c != "other"}
                if contents and categories(contents[0]) & shown_set:
                    first_hits += 1
                hit = set()
                for text in contents:
                    hit |= categories(text) & shown_set
                if hit:
                    any_hits += 1
                answered |= hit
                if re.search(r"verifier|verification|\bnote\b|failed check|the check", str(patch.get("reasoning", "")).lower()):
                    reasoning_hits += 1
            applied = disposition.get("binding_applied")
            print("block %s:%d %-19s authorized %s binding_applied %s | failed checks shown %d by category %s | failure minibatches %d: first edit answers a shown category %d, any edit %d, reasoning mentions a check/note %d | categories answered %d/%d" % (
                label, block, arm, authorized, applied, len(checks), dict(shown.most_common()), len(raw), first_hits, any_hits, reasoning_hits,
                len(answered), len({c for c in shown if c != "other"})))
            t = totals[arm]
            t["minibatches"] += len(raw)
            t["first"] += first_hits
            t["any"] += any_hits
            t["reasoning"] += reasoning_hits
            t["categories_shown"] += len({c for c in shown if c != "other"})
            t["categories_answered"] += len(answered)
            t["blocks"] += 1
    print("\npooled (descriptive; keyword heuristic):")
    for arm in arms:
        t = totals[arm]
        if not t["blocks"]:
            continue
        print("  %-19s blocks %d | failure minibatches %d: first edit answers a shown category %d, any edit %d, reasoning mentions a check/note %d | shown categories answered %d/%d" % (
            arm, t["blocks"], t["minibatches"], t["first"], t["any"], t["reasoning"], t["categories_answered"], t["categories_shown"]))


if __name__ == "__main__":
    main(sys.argv[1:])
