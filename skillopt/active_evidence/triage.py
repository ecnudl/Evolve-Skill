"""Code triage of one step's rows and the choice of representative cases -- no model call.

Categories (from the sealed evaluation, never from the output text alone): ``environment`` (unknown score: cleanup,
missing module, container error), ``delivery`` (an empty or undelivered generated output), ``host_fail``,
``host_pass``. The batch summary is compact (counts, per-family pass/fail); the representatives are chosen by a
frozen quota -- failures and successes in equal shares, within-family pairs (one pass and one fail of the same
family) first, then by evidence hash -- so the diagnoser sees successes, pairs and failures, not just the first
failures. Hidden-test tracebacks are written host-only and never enter a prompt."""
from __future__ import annotations

from skillopt.coevolution_v5.core import seal

from . import PROTOCOL

CATEGORIES = ("environment", "delivery", "host_fail", "host_pass")
SELECTION_RULE = "equal_shares_fail_pass_within_family_pairs_first_then_evidence_hash_v1"


def triage_row(pair, saved):
    """One known step row: the saved evaluation decides (prediction status, output, score)."""
    prediction, score = saved["prediction"], saved["score"]
    output = pair["row"]["output"]["output"]
    if prediction.get("status") != "available" or not str(output).strip():
        return {"category": "delivery", "reason": str(prediction.get("reason"))[:120]}
    return {"category": "host_fail" if score["status"] == "fail" else "host_pass",
            "reason": str(score.get("reason"))[:120]}


def summarize(pairs, triaged, unknown):
    families = {}
    for pair, verdict in zip(pairs, triaged):
        family = families.setdefault(pair["item"]["task"]["family_id"], {"pass": 0, "fail": 0, "delivery": 0})
        families[pair["item"]["task"]["family_id"]][
            "pass" if verdict["category"] == "host_pass" else "fail" if verdict["category"] == "host_fail" else "delivery"] += 1
    counts = {category: sum(v["category"] == category for v in triaged) for category in CATEGORIES}
    counts["environment"] += unknown
    return {"rows": len(pairs) + unknown, "known": len(pairs), "unknown_excluded": unknown, "counts": counts,
            "families": dict(sorted(families.items())),
            "mixed_families": sorted(f for f, c in families.items() if c["pass"] and c["fail"]),
            "note": "host pass/fail is host information (the development checker), not a discovery"}


def select_cases(pairs, triaged, limits):
    """Representatives under the frozen quota. Returns (cases, omitted)."""
    rows = [(pair, verdict) for pair, verdict in zip(pairs, triaged)]
    by_family = {}
    for pair, verdict in rows:
        by_family.setdefault(pair["item"]["task"]["family_id"], []).append((pair, verdict))
    pairs_first = set()
    for family, members in sorted(by_family.items()):
        statuses = {v["category"] for _, v in members}
        if {"host_fail", "host_pass"} <= statuses:
            fail = min((p for p, v in members if v["category"] == "host_fail"), key=lambda p: p["token"])
            ok = min((p for p, v in members if v["category"] == "host_pass"), key=lambda p: p["token"])
            pairs_first.update({fail["token"], ok["token"]})
    ordered = sorted(rows, key=lambda r: (r[0]["token"] not in pairs_first, r[0]["token"]))
    fails = [r for r in ordered if r[1]["category"] in {"host_fail", "delivery"}]
    passes = [r for r in ordered if r[1]["category"] == "host_pass"]
    quota = limits["view_rows"]
    half = quota // 2
    chosen = fails[:max(half, quota - len(passes))] + passes[:max(quota - half, quota - len(fails))]
    chosen = sorted(chosen, key=lambda r: r[0]["token"])[:quota]
    cases = []
    for pair, verdict in chosen:
        token = pair["token"]
        cases.append({"case_id": "case-" + token[:12], "token": token, "host_status": pair["host_status"],
                      "category": verdict["category"], "family_id": pair["item"]["task"]["family_id"],
                      "why": "pair" if token in pairs_first else "failure" if verdict["category"] != "host_pass"
                      else "success"})
    return cases, len(rows) - len(chosen)


def triage_record(value, step, pairs, saved_rows, unknown, limits):
    """The sealed triage of one step (prompt-safe: no tracebacks, no private data) plus the host-only detail."""
    triaged = [triage_row(pair, saved_rows[pair["token"]]) for pair in pairs]
    summary = summarize(pairs, triaged, unknown)
    cases, omitted = select_cases(pairs, triaged, limits)
    record = seal({"protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": step,
                   "summary": summary, "cases": cases, "cases_omitted": omitted, "selection_rule": SELECTION_RULE,
                   "by_token": {p["token"]: v for p, v in zip(pairs, triaged)}})
    host_only = seal({"protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": step,
                      "rows": {p["token"]: {"score_reason": saved_rows[p["token"]]["score"].get("reason"),
                                            "native_result": (saved_rows[p["token"]]["score"].get("metrics") or {}).get("native_result"),
                                            "detail_keys": sorted(((saved_rows[p["token"]]["score"].get("metrics") or {}).get("details") or {}).keys())
                                            if type((saved_rows[p["token"]]["score"].get("metrics") or {}).get("details")) is dict else []}
                               for p in pairs},
                      "information_origin": "host_development_audit_never_prompted"})
    return record, host_only
