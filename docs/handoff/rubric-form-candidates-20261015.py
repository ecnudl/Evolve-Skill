"""Zero-call: what each arm's analyst made of its feedback in the rubric-form study (fivebench-rubric-form-study-v1).
Reads the sealed records of the usable blocks -- the proposal result (candidate text, applied edits), the parent text
and the verifier rows that fed the analyst (failing judged/host checks on host-fail rows of AUTHORIZED blocks) -- and
prints per arm: candidate size, applied edits, feedback rows and their check categories, the added sections' categories,
and a crude propagation measure (share of the feedback's content words that re-appear in the arm's added text, against
the scalar arm's added text as the no-feedback control). Never reads test data; selection-set tasks are generated items.
Usage: candidates.py <study dir>:<block> [...]   e.g. .../officeqa-rubric-form-a/study:0 .../officeqa-rubric-form-c/study:0"""
import collections
import difflib
import json
import os
import re
import sys

ARMS = ("scalar", "labelled", "default_text", "global_text", "cluster_text", "format_text", "format_code", "compliance_code")
TEXT = ("default_text", "global_text", "cluster_text", "format_text", "format_code", "compliance_code")
CATEGORIES = [  # first match wins; keyword lists are deliberately short and literal
    ("rounding", r"round|decimal|hundredth|tenth|significant|digits?"),
    ("unit/scale", r"\bunit|billion|million|thousand|percent|per cent|%|scale|dollar"),
    ("list/brackets", r"bracket|\blist\b|comma-separated|comma separated|\[\s*\w"),
    ("date", r"\bdate|month|\byear\b|day\b"),
    ("answer tag", r"answer tag|<answer>|nothing else|single value|only the|no commentary|no units|extra text"),
    ("scope/asked item", r"address|asked|scope|the question asks|requested|item"),
    ("computation", r"comput|calculat|\bsum\b|\bmean\b|average|growth|difference|ratio|derivation|arithmetic|formula"),
    ("source/page", r"\bpage|cite|citation|source|table|cell|quote|verbatim"),
]
STOP = set("""the a an and or of to in on for with by from as at is are be was were that this these those it its into than then
there their they them which who what when where while will would should could can must may might not no nor do does did done
have has had having if else only also any all each every both either neither such same other another more most less least
very much many some few about above below between within without before after during under over again further once here
how why so too just like per via vs versus e g i etc answer answers question questions response responses value values
number numbers given provided required requires require using use used""".split())


def read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def words(text):
    return {w for w in re.findall(r"[a-z][a-z\-]{3,}", text.lower()) if w not in STOP}


def category(text):
    low = text.lower()
    for name, pattern in CATEGORIES:
        if re.search(pattern, low):
            return name
    return "other"


def added_lines(parent, candidate):
    out = []
    for line in difflib.unified_diff(parent.splitlines(), candidate.splitlines(), lineterm="", n=0):
        if line.startswith("+") and not line.startswith("+++"):
            out.append(line[1:])
    return out


def feedback_rows(root, block, arm):
    """Host-fail rows whose report carried at least one failing check -- what the analyst saw -- in an authorized block."""
    folder = os.path.join(root, "verifier", "%d-%s" % (block, arm))
    if not os.path.isdir(folder):
        return None, []
    summary = read(os.path.join(folder, "summary.json")) if os.path.exists(os.path.join(folder, "summary.json")) else {}
    authorized = summary.get("authorized")
    if authorized is None:
        reports = os.path.join(folder, "reports")
        flags = [read(os.path.join(reports, f)).get("authorized") for f in os.listdir(reports)] if os.path.isdir(reports) else []
        authorized = bool(flags) and all(flags)
    rows = []
    folder_rows = os.path.join(folder, "rows")
    for name in sorted(os.listdir(folder_rows)):
        row = read(os.path.join(folder_rows, name))
        failing = [p for p in row.get("probes", []) if p.get("verdict") == "fail" or p.get("outcome") == "fail"]
        if row.get("host_status") == "fail" and failing:
            rows.append(failing)
    return authorized, rows


def main(argv):
    per_arm = collections.defaultdict(lambda: {"blocks": 0, "bytes": [], "edits": [], "ops": collections.Counter(), "feedback_rows": [],
                                               "feedback_cats": collections.Counter(), "added_cats": collections.Counter(),
                                               "sections": [], "propagation_own": [], "propagation_scalar": [], "failed": 0})
    for spec in argv:
        root, block = spec.rsplit(":", 1)
        block = int(block)
        label = os.path.basename(os.path.dirname(root.rstrip("/")))
        candidates = read(os.path.join(root, "blocks", str(block), "candidates.json"))
        dispositions = candidates["dispositions"]
        texts, parents = {}, {}
        for arm in ARMS:
            folder = os.path.join(root, "native", str(block), arm)
            entry = per_arm[arm]
            if not os.path.isdir(folder) or not os.path.exists(os.path.join(folder, "result.json")) \
                    or dispositions.get(arm, {}).get("status") != "candidate_ready":
                entry["failed"] += 1  # proposal failed (analyst JSON rejected): the arm stayed on the parent
                continue
            result = read(os.path.join(folder, "result.json"))
            identity = read(os.path.join(folder, "identity.json"))
            parents[arm] = identity["parent_skill"]
            texts[arm] = result.get("candidate_skill") or ""
            entry["blocks"] += 1
            entry["bytes"].append(len(texts[arm].encode("utf-8")))
            applied = [e for e in (result.get("application") or []) if str(e.get("status", "")).startswith("applied")]
            entry["edits"].append(len(applied))
            entry["ops"].update(e.get("op", "?") for e in applied)
            added = added_lines(parents[arm], texts[arm])
            for line in added:
                if line.startswith("#"):
                    entry["sections"].append(line.strip("# ").strip()[:70])
                    entry["added_cats"][category(line)] += 1
        scalar_added = " ".join(added_lines(parents.get("scalar", ""), texts.get("scalar", ""))) if "scalar" in texts else ""
        for arm in TEXT:
            authorized, rows = feedback_rows(root, block, arm)
            entry = per_arm[arm]
            if authorized is None:
                continue
            entry["feedback_rows"].append(len(rows) if authorized else 0)
            if not authorized or arm not in texts or dispositions.get(arm, {}).get("status") != "candidate_ready":
                continue
            feedback = " ".join(" ".join(str(p.get(k, "")) for k in ("obligation", "evidence", "check", "detail")) for failing in rows for p in failing)
            for failing in rows:
                for p in failing:
                    entry["feedback_cats"][category(str(p.get("obligation", "")) + " " + str(p.get("check", "")))] += 1
            vocabulary = words(feedback)
            if vocabulary:
                own = " ".join(added_lines(parents[arm], texts[arm]))
                entry["propagation_own"].append(len(vocabulary & words(own)) / len(vocabulary))
                entry["propagation_scalar"].append(len(vocabulary & words(scalar_added)) / len(vocabulary))
        print("block %s:%d  candidates: %s" % (label, block, {a: len(texts.get(a, "").encode("utf-8")) for a in ARMS if a in texts}))

    def mean(values):
        return None if not values else round(sum(values) / len(values), 2)

    print()
    for arm in ARMS:
        e = per_arm[arm]
        print("%-16s blocks %d (failed %d) | candidate bytes mean %s | applied edits mean %s %s | feedback rows per authorized block %s" % (
            arm, e["blocks"], e["failed"], mean(e["bytes"]), mean(e["edits"]), dict(e["ops"]), e["feedback_rows"] or "-"))
        if e["feedback_cats"]:
            print("    feedback check categories (failing checks the analyst saw): %s" % dict(e["feedback_cats"].most_common()))
        if e["propagation_own"]:
            print("    feedback words re-appearing in added text: own %s vs scalar control %s (per block own %s)" % (
                mean(e["propagation_own"]), mean(e["propagation_scalar"]), [round(x, 2) for x in e["propagation_own"]]))
        print("    added section categories: %s" % dict(e["added_cats"].most_common()))
        print("    added sections (sample): %s" % e["sections"][:8])


if __name__ == "__main__":
    main(sys.argv[1:])
