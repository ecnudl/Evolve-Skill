"""Bounded development failure-message feedback (``feedback = hidden_failure``): a study arm, never the method.

For every FAILED development step row the analysts' [verification] turn quotes the final exception messages of that
row's failing hidden tests (traceback frames, absolute paths and source lines removed, at most ``MAX_TESTS_PER_ROW``
tests in sorted test-name order, ``PER_TEST_CHARS`` per test, the row report bounded like any evidence report).
Hidden test code, expected answers and canonical solutions are still never shown; the rows are the stage's bound
step rows (development partition only), so challenge-pool and final data never enter. The extraction policy is
frozen here and audited (denominators for every detailed row whether or not it is released, message classes,
source and payload hashes) before any updater call; a release that reaches fewer than half of the failed rows is a
failed delivery and stops the step."""
from __future__ import annotations

import re

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, write_json
from skillopt.validator_pilot.api import digest

from . import PROTOCOL
from .reports import _bounded, seal_report
from .triage import triage_record
from .updater import TRUNCATION

ARM = "hidden_failure"
RELEASE_PROFILE = "development-failure-messages-v1"
INFORMATION_RELEASE = ("final exception messages (with test names) of the failing hidden tests of FAILED development "
                       "step rows, to the analysts of the message branch only")
HEADER = "HIDDEN TEST FAILURES (label feedback; development task only)"
MAX_TESTS_PER_ROW = 4
PER_TEST_CHARS = 400
MIN_RELEASED_FRACTION = 0.5
MESSAGE_CLASSES = ("value_diff", "not_raised", "bare_assertion", "typed_error", "other_assertion")
# The analysts' step summary for the message branch: a fixed statement of the release (no model text).
LABEL_SUMMARY = (
    "Bounded development failure-message feedback. Each FAILED development row's [verification] turn quotes the final "
    "exception messages of its failing hidden tests (traceback frames and file paths removed; at most "
    + str(MAX_TESTS_PER_ROW) + " tests per row in test-name order). Hidden test code, expected answers and canonical "
    "solutions are not shown. Infer general procedures from what the tests complained about (which documented "
    "behaviours the implementations missed); do not copy a task's expected value, test name, file name or literal into "
    "the skill as such -- write the reusable rule."
)
_EXCEPTION_LINE = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Warning|Interrupt|Exit)\b")
_FRAME = re.compile(r'^\s*File "[^"]*", line \d+.*$', re.M)
# absolute paths of every flavour: POSIX (any non-blank, non-quote characters after a leading slash that does not
# follow a word character or a dot -- so '1/2', 'a/b' and '100 / 2' stay), home-relative, Windows drive letters and
# UNC shares; only blanks and quotes terminate a path, punctuation inside it is part of it
_PATH = re.compile(r"(?<![\w.])/[^\s\"']+|(?<![\w.])~/[^\s\"']+|\b[A-Za-z]:\\[^\s\"']+|(?<!\\)\\\\[^\s\"']+")
_FORBIDDEN = (("traceback_header", re.compile(r"Traceback \(most recent call last\)")),
              ("frame", re.compile(r'File "')), ("frame_location", re.compile(r"\bline \d+, in \b")),
              ("path", _PATH), ("indented_source_line", re.compile(r"^\s{2,}\S", re.M)))


def forbidden_content(text):
    """Names the first forbidden pattern in a released text (traceback header, frame, path, indented source line)."""
    for name, pattern in _FORBIDDEN:
        if pattern.search(text):
            return name
    return None


def failure_message(traceback_text, *, per_test_chars=PER_TEST_CHARS):
    """The final exception line(s) of one hidden-test traceback: the LAST line matching the exception-class pattern
    starts the message (a chained exception yields the final one; pandas/numpy messages span several lines), frame
    headers and paths are dropped and the text is bounded. None when the traceback has no exception line
    (ambiguous: not released) or when forbidden content survives."""
    lines = [line.rstrip() for line in str(traceback_text).splitlines()]
    start = None
    for index, line in enumerate(lines):
        if _EXCEPTION_LINE.match(line):
            start = index
    if start is None:
        return None
    text = "\n".join(line for line in lines[start:] if line.strip())
    text = _PATH.sub("<path>", _FRAME.sub("", text))
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return None if forbidden_content(text) else _bounded(text, per_test_chars)


def classify(message):
    head = message.split("\n", 1)[0]
    if "[left]" in message or "[right]" in message or "!=" in message:
        return "value_diff"
    if "not raised" in message:
        return "not_raised"
    if re.match(r"^AssertionError:?\s*$", head) or "False is not true" in head or "True is not false" in head:
        return "bare_assertion"
    if not head.startswith("AssertionError"):
        return "typed_error"
    return "other_assertion"


def row_release(details, limit, *, max_tests=MAX_TESTS_PER_ROW, per_test_chars=PER_TEST_CHARS):
    """The accounting of one failed row's hidden-test detail and, when releasable, its released text. None only
    when the scorer left no per-test detail at all; otherwise every test is counted whether or not it is released
    (``text`` is None for a withheld row, with the reason)."""
    if type(details) is not dict or not details:
        return None
    names = sorted(details)
    considered = names[:max_tests]
    extracted = {name: failure_message(details[name], per_test_chars=per_test_chars) for name in considered}
    messages = {name: text for name, text in extracted.items() if text is not None}

    def classes(items):
        items = list(items)
        return {c: sum(classify(m) == c for m in items) for c in MESSAGE_CLASSES}
    accounting = {"tests_total": len(names), "tests_omitted_by_cap": len(names) - len(considered),
                  "tests_withheld": len(considered) - len(messages), "tests_extracted": len(messages),
                  "tests_truncated": sum(m.endswith(TRUNCATION) for m in messages.values()),
                  "classes_extracted": classes(messages.values())}
    withheld = {"text": None, "tests_shown": 0, "tests_cut_by_row_cap": 0, "last_entry_partial": False,
                "row_truncated": False, "classes": classes([]), **accounting}
    if not messages:
        return {**withheld, "withheld_reason": "no_releasable_message"}
    lines = [f"{HEADER}: {len(names)} failing hidden test(s)"
             + (f", first {max_tests} shown" if len(names) > max_tests else "")
             + (f", {len(considered) - len(messages)} withheld" if len(messages) < len(considered) else "") + "."]
    lines.extend(f"- {name}: {text}" for name, text in messages.items())
    joined = "\n".join(lines)
    truncated = len(joined) > limit
    body = joined[:limit] if truncated else joined  # the row cap cuts the joined text; messages keep their own marker
    text = body + TRUNCATION if truncated else body
    hit = forbidden_content(text)  # a test NAME can carry a path or frame text: the whole row is then withheld
    if hit is not None:
        return {**withheld, "withheld_reason": "forbidden_content_in_row:" + hit}
    # what the analysts actually receive after the row cap: entries whose line start survived (the last may be cut)
    shown = [name for name in messages if f"\n- {name}: " in body]
    partial = truncated and bool(shown) and not body.endswith(messages[shown[-1]])
    return {"text": text, "withheld_reason": None, "tests_shown": len(shown),
            "tests_cut_by_row_cap": len(messages) - len(shown), "last_entry_partial": partial,
            "row_truncated": truncated, "classes": classes(messages[name] for name in shown), **accounting}


def _write_or_replay(path, record, what):
    if path.exists():
        require(read_json(path, sealed=True) == record, what + " replay changed")
    else:
        write_json(path, record)


def run_label_feedback(ledger, value, root, step, pairs, unknown):
    """Seal one report per released failed step row (same path and shape the updater authenticates for diagnosis
    reports), the release audit and the step summary; returns the stage's diagnosis-shaped material. Zero model
    calls. Status ``failed_delivery`` (no reports) when fewer than half of the failed rows could be released."""
    extension = value["active_evidence"]
    arms, limits = extension["arms"], extension["limits"]
    require(arms["feedback"] == ARM, "Label feedback belongs to the hidden_failure arm only")
    folder = root / "diagnosis" / str(step)
    saved = {p["token"]: p["saved"] for p in pairs}
    triage, host_only = triage_record(value, step, pairs, saved, unknown, limits)
    _write_or_replay(folder / "triage.json", triage, "Triage")
    _write_or_replay(root / "host_only" / "triage" / (str(step) + ".json"), host_only, "Host-only triage")
    failed = [p for p in pairs if p["host_status"] == "fail"]
    releases, rows_audit = {}, {}
    for pair in failed:
        details = (pair["saved"]["score"].get("metrics") or {}).get("details")
        release = row_release(details, limits["report_chars"])
        row = {"details_available": release is not None,
               "source_details_hash": digest(details) if details is not None else None,
               "released": release is not None and release["text"] is not None}
        if release is not None:
            row.update({k: v for k, v in release.items() if k != "text"})
            row["released_payload_hash"] = digest(release["text"]) if release["text"] is not None else None
            if release["text"] is not None:
                releases[pair["token"]] = release
        rows_audit[pair["token"]] = row
    detailed = [r for r in rows_audit.values() if r["details_available"]]
    delivered = len(releases) >= MIN_RELEASED_FRACTION * len(failed) if failed else True

    def total(key, rows=detailed):
        return sum(r[key] for r in rows)
    audit = seal({"protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": step, "arm": ARM,
                  "release_profile": RELEASE_PROFILE, "information_release": INFORMATION_RELEASE,
                  "policy": {"max_tests_per_row": MAX_TESTS_PER_ROW, "per_test_chars": PER_TEST_CHARS,
                             "row_chars": limits["report_chars"], "ordering": "sorted test names, first N",
                             "message_start": "last line matching an exception-class pattern (chained exceptions -> final)",
                             "removed": "traceback frames, absolute paths (POSIX, home, Windows, UNC)",
                             "withheld": "no exception line; forbidden content in a message or in the assembled row",
                             "min_released_fraction": MIN_RELEASED_FRACTION},
                  # accounting over EVERY detailed failed row, independent of release eligibility
                  "denominators": {"step_rows": len(pairs), "host_fail_rows": len(failed),
                                   "rows_with_details": len(detailed), "rows_without_detail": len(failed) - len(detailed),
                                   "rows_released": len(releases), "rows_withheld": len(detailed) - len(releases),
                                   "tests_total": total("tests_total"), "tests_omitted_by_cap": total("tests_omitted_by_cap"),
                                   "tests_withheld": total("tests_withheld"), "tests_extracted": total("tests_extracted"),
                                   "tests_shown": total("tests_shown"), "tests_cut_by_row_cap": total("tests_cut_by_row_cap"),
                                   "tests_truncated": total("tests_truncated"), "rows_truncated": total("row_truncated"),
                                   "rows_with_partial_last_entry": total("last_entry_partial")},
                  # classes of every extracted message (all detailed rows) and of the entries actually emitted
                  "message_classes": {c: sum(r["classes_extracted"][c] for r in detailed) for c in MESSAGE_CLASSES},
                  "released_message_classes": {c: sum(r["classes"][c] for r in releases.values()) for c in MESSAGE_CLASSES},
                  "rows": rows_audit, "delivered": delivered})
    _write_or_replay(folder / "release_audit.json", audit, "Release audit")
    reports = {}
    if delivered:
        for pair in failed:
            release = releases.get(pair["token"])
            if release is None:
                continue
            report = seal_report(value, step, pair["token"], pair["host_status"], [], release["text"])
            _write_or_replay(folder / "reports" / (pair["token"] + ".json"), report, "Label report")
            reports[pair["token"]] = report
    status = "completed" if delivered else "failed_delivery"
    summary = seal({"protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": step, "arm": ARM,
                    "triage_hash": triage["record_hash"], "cases": [], "reserve_calls": 0, "status": status,
                    "release_profile": RELEASE_PROFILE, "information_release": INFORMATION_RELEASE,
                    "release_audit_hash": audit["record_hash"], "released_rows": sorted(reports),
                    "hypotheses": [], "checks": [], "observations": [], "grades": {},
                    "report_hashes": {t: r["record_hash"] for t, r in sorted(reports.items())},
                    "summary_text": LABEL_SUMMARY if delivered else None, "research": [],
                    "research_new_information": False, "research_consulted": False, "fact_needs": [],
                    "cases_skipped_for_reserve": []})
    _write_or_replay(folder / "summary.json", summary, "Label summary")
    return {"status": status, "reports": reports, "summary": summary["summary_text"],
            "summary_hash": summary["record_hash"], "rows_with_evidence": len(reports), "hypotheses": [], "checks": [],
            "observations": [], "research": [], "research_new_information": False, "research_consulted": False,
            "fact_needs": [], "triage_hash": summary["triage_hash"], "information_release": INFORMATION_RELEASE,
            "release_profile": RELEASE_PROFILE, "release_audit_hash": audit["record_hash"],
            "release_denominators": audit["denominators"], "message_classes": audit["message_classes"]}
