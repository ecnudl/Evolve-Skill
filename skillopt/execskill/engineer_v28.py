"""Configuration-scoped outcome-judged engineer orchestration and schema repair."""
from __future__ import annotations

from types import SimpleNamespace

from skillopt.validator_pilot.api import digest

from . import engineer_reader as reader, policy, profiles as p, replay
from .package import MAX_STATE_BYTES

FIX_SYSTEM = "Correct the named change using the fatal check's evidence. Keep its kind and incumbent target."
FORMAT_RETRY_SYSTEM = "Only fix the format. Preserve the program's intended behavior. Return the requested change using the supplied schema."
INFORMATION_COUNTS = frozenset({"items", "faults", "mismatches", "fires_on", "predicate_faults", "fired", "empty",
    "exceptions", "nonempty", "claimed", "failed", "dropped_tests", "quality_problems", "tracker_agree",
    "tracker_steps", "screened"})


def advisory_feedback(change, report):
    """Counts-only quality evidence plus malformed-test explanations for the next engineer round."""
    from . import engineer as e
    lint = report.setdefault("lint", {"id": change.procedure.id, "tests": [], "problems": []})
    for dropped in report.get("dropped_tests", []):
        reason = dropped["reason"]
        detail = reason if reason in e.LINT_DETAILS else "id" if reason == "duplicate_ids" else "keys"
        lint["problems"].append({"reason": "invalid_test", "test": dropped["test"], "detail": detail,
                                 "evaluated": False, "validation_explanation": dropped["validation_explanation"]})
    lint["problems"] = lint["problems"][:e.MAX_LINT]
    information = []
    for check in report["checks"]:
        name, detail = check["check"], check.get("detail") or {}
        counts = {}
        if name == "C5b":
            counts = {"claimed": detail.get("claimed", 0), "failed": len(detail.get("failed", [])),
                      "dropped_tests": len(report.get("dropped_tests", []))}
        elif name == "C6":
            counts = {"items": detail.get("trajectories", 0), "faults": detail.get("fault_count", 0),
                      "mismatches": detail.get("mismatched_total", len(detail.get("mismatched", [])))}
        elif name in ("C6b", "C6c"):
            counts = {key: value for key, value in detail.items() if key in INFORMATION_COUNTS and type(value) is int}
        elif name == "C7":
            counts = {"quality_problems": detail.get("informational_problem_count",
                                                     len(detail.get("informational_problems", [])))}
            agreement = detail.get("tracker_agreement")
            if agreement is not None:
                counts.update(tracker_agree=agreement[0], tracker_steps=agreement[1])
        elif name == "C9":
            counts = {"screened": len(detail)}
        else:
            continue
        information.append({"check": name, "passed": bool(check["passed"]), "counts": counts})
    lint["information"] = information


def system(configuration, *, train):
    cap = policy.source_limit(p.POLICY_VERSIONS[configuration])
    bench = "ALFWorld" if p.is_alfworld(configuration) else "ZebraLogic"
    hooks = ("applies(view) -> bool on {initial_observation, admissible_commands_at_reset, task_text}; "
             "alf_before_step(view,state) -> {fields,discourage}, view={initial_observation,observation,"
             "admissible_commands,recent_history}; alf_after_step(event,state) -> JSON state, "
             "event={step,action,observation,admissible_commands}. State is passed explicitly; module globals reset."
             if p.is_alfworld(configuration) else
             "applies(view) -> bool; before_call(view,state) -> fields or None. "
             "view={question,columns}; state=None. Read the puzzle's own clues and compute useful constraints.")
    learning = ("Up to %d training rounds, patience %d; each failing change gets up to %d behavior fix calls. "
                "Training adoption keeps the net-gain requirement and format guard. "
                % (p.TRAIN_ROUNDS, p.TRAIN_PATIENCE, p.TRAIN_FIXES) if train else
                "This is one proposal round; each failing change gets one behavior fix call. ")
    return ("You maintain sandboxed helper procedures for %s, configuration %s (v2.8). "
            "Propose at most %d changes to improve solver outcomes. %s\n%s\n"
            "Fatal: sandbox safety (syntax, banned names/imports, pure module constants, resource/load limits); "
            "reference-answer leakage (one adjudication); shortcuts/static bans, meta counterfactuals and J7; "
            "answer-channel markers in notes; source over %d UTF-8 bytes; a reply still unusable after one "
            "format-only retry. Never embed reference answers or task-specific memorized solutions. "
            "Replay tests and claims_fix are advice: malformed tests are dropped and failing tests reported. "
            "Replay mismatch, crashes/timeouts, firing/note coverage, tracker agreement and registrar quality "
            "checks are information. A fault contributes no note on that item; wholly inert procedures skip "
            "training. Workers use PYTHONHASHSEED=%d and fresh module namespaces. "
            "Acceptance uses unchanged %s J1 >= %s points, J4/J5/J6/J7; J3 is information.\n"
            "Fields: facts/warnings lists of text, table rows, candidates, verbatim bindings. "
            "Give task facts, never reply-form instructions. Sentences/list elements saying answer with, respond "
            "with, output only, format your, round to, give the answer as, only the or just the are removed and "
            "recorded; factual uses of units, return, round, output and answer are allowed.\n"
            "Reply with a JSON object {changes:[...]} in a fenced block and fenced Python for each coded change. "
            "Changes: new; revision with revises=id; deletion with id; narrowing with id and benches. "
            "Coded metadata: description, hooks, header, max_note_chars, requests_second_call, state_bytes, "
            "excluded_benches, replay_tests. Description/header are truncated to %d/%d characters. "
            "Unknown keys are recorded and ignored; missing fields inherit the fixed change, then its incumbent, "
            "then schema defaults; hooks/kind are derived when possible; unambiguous misplaced keys are moved. "
            "Optional replay tests use id, trajectory, hook, property, claims_fix, nonvacuity; step belongs inside "
            "property. The full schema and generated example accompany a format-only retry; that call consumes "
            "the unit call budget, not a behavior fix.\n"
            % (bench, configuration, p.MAX_CHANGES, learning, hooks, cap, p.V28_HASHSEED, p.PRACTICAL_RULE["name"],
               p.PRACTICAL_RULE["gain_points"], p.MAX_DESCRIPTION_CHARS, p.MAX_HEADER_CHARS))


def prepare(change, ctx):
    """Normalize package metadata and drop invalid tests before constructing Procedure."""
    from . import engineer as e
    log = change.repairs if change.repairs is not None else []
    change.repairs = log
    # Direct check() callers use exactly the same schema engine as model replies.
    change.entry = reader.normalize(change.entry, reader.schema(change.kind, train=ctx.mode == e.TRAIN,
        source=change.source or "", entry=change.entry), repairs=log)
    if change.kind not in e.CODED:
        return []
    entry = change.entry
    hooks = reader.defined_hooks(change.source)
    if entry["hooks"] != hooks:
        log.append({"rule": "derived", "path": "$.hooks", "before": entry["hooks"], "after": hooks})
        entry["hooks"] = hooks
    for name, cap in (("description", p.MAX_DESCRIPTION_CHARS), ("header", p.MAX_HEADER_CHARS)):
        if len(entry[name]) > cap:
            change.truncated[name] = len(entry[name])
            entry[name] = entry[name][:cap]
            log.append({"rule": "truncated", "path": "$." + name, "cap": cap})
    if not entry["description"]:
        entry["description"] = reader.schema()["description"].default
        log.append({"rule": "schema_default", "path": "$.description"})
    constraints = {
        "max_note_chars": (1 if any(h in p.NOTE_HOOKS for h in hooks) else 0,
                           max(p.MAX_NOTE_CHARS.values()) if any(h in p.NOTE_HOOKS for h in hooks) else 0),
        "state_bytes": (1 if "alf_after_step" in hooks else 0, MAX_STATE_BYTES),
    }
    for key, (lower, upper) in constraints.items():
        before = entry[key]
        entry[key] = max(lower, min(upper, before))
        if before != entry[key]:
            log.append({"rule": "bounded_metadata", "path": "$." + key, "before": before, "after": entry[key]})
    if entry["requests_second_call"] and not any(h in ("bindings", "sheet_feedback") for h in hooks):
        entry["requests_second_call"] = False
        log.append({"rule": "derived", "path": "$.requests_second_call"})
    benches = p.SUPPORTED_BENCHES if ctx.bench == "zebralogic" else p.BENCHES
    excluded = [b for b in benches if b in entry["excluded_benches"]]
    if excluded != entry["excluded_benches"]:
        log.append({"rule": "registered_values", "path": "$.excluded_benches"})
    entry["excluded_benches"] = excluded
    earlier_normalizations = len(change.normalized)
    e._normalize(change, benches=benches)
    log.extend({"rule": "schema_scope", **item} for item in change.normalized[earlier_normalizations:])
    e._resolve_change(change, ctx)
    log.extend({"rule": "trajectory_reference", **item} for item in change.trajectory_resolution or ())
    declared = SimpleNamespace(hooks=entry["hooks"])
    scope = e._scope_entries(ctx, set(entry["excluded_benches"]))
    kept, dropped, seen = [], [], set()
    for index, original in enumerate(entry["replay_tests"], 1):
        test = original
        if isinstance(test, dict):
            try:
                test = reader.normalize(test, reader.test_schema(test), path="$.replay_tests[%d]" % (index - 1), repairs=log)
            except reader.Unusable:
                pass
        reason = replay.validate_test(test, declared, scope)
        if reason is None and test["id"] in seen:
            reason = "duplicate_ids"
        if reason is None and len(kept) >= p.MAX_TESTS:
            reason = "test_count"
        if reason:
            feedback = replay.test_validation_feedback([test] if reason in ("duplicate_ids", "test_count") else test,
                reason, procedure=declared, entry=scope.get(test.get("trajectory")) if isinstance(test, dict)
                and isinstance(test.get("trajectory"), str) else None)
            dropped.append({"test": index, "reason": reason, **feedback})
            log.append({"rule": "malformed_test_dropped", "path": "$.replay_tests[%d]" % (index - 1), "reason": reason})
        else:
            seen.add(test["id"])
            kept.append(test)
    entry["replay_tests"] = kept
    return dropped


def _retry(ctx, reply, error, purpose, *, change=None, index=None):
    from . import engineer as e
    request = {"request": "format_retry", "instruction": FORMAT_RETRY_SYSTEM,
               "schema": reader.schema_document(), "parse_problem": error,
               "previous_reply": reply, "change_index": index}
    if change is not None:
        request["change"] = dict(change.entry, source=change.source)
    fixed, call = e._ask(ctx, request, "format-retry/" + purpose)
    event = {"purpose": purpose, "call": call, "parse_problem": error, "parsed": False}
    ctx.sheet.setdefault("format_retries", []).append(event)
    try:
        results = reader.read(fixed, ctx, fix_change=change)
        if index is not None and len(results) != 1:
            raise reader.Unusable("format retry must contain exactly the requested change")
        if any(result["error"] for result in results):
            raise reader.Unusable(next(result["error"] for result in results if result["error"]))
        event["parsed"] = True
        return results, call
    except reader.Unusable as problem:
        event["reason"] = str(problem)
        return None, call


def read_call(ctx, reply, call, purpose, *, change=None):
    """At most one format retry for each unusable change (or unreadable envelope)."""
    from . import engineer as e
    try:
        results = reader.read(reply, ctx, fix_change=change)
    except reader.Unusable as problem:
        results, call = _retry(ctx, reply, str(problem), purpose, change=change,
                              index=change.n if change else None)
        if results is None:
            return [], [{"n": change.n if change else 1, "reason": "unparseable", "detail": str(problem)}]
    changes, failures = [], []
    for n, result in enumerate(results, 1):
        result_call = call
        if result["error"]:
            attempted_repairs = list(result["repairs"])
            repaired, result_call = _retry(ctx, reply, result["error"], purpose + "/%d" % n, change=change, index=n)
            if repaired is None:
                failures.append({"n": n, "reason": "unparseable", "detail": result["error"], "repairs": result["repairs"]})
                continue
            result = repaired[0]
            result["repairs"] = attempted_repairs + result["repairs"]
        entry = result["entry"]
        proposed = e.Change(change.n if change else n, entry["kind"], entry, result["source"], result_call,
                            repairs=(list(change.repairs or ()) if change else []) + result["repairs"])
        changes.append(proposed)
    return changes, failures


def fix(ctx, change, report, *, attempt=None, why=None):
    from . import engineer as e
    last = next((row for row in reversed(report["checks"]) if not row["passed"] and not row.get("informational")), None)
    user = {"request": "fix", "bench": ctx.bench, "change": dict(change.entry, source=change.source),
            "failed": last if ctx.echo else e._redacted(last), "attempt": attempt,
            "attempts": p.TRAIN_FIXES if ctx.mode == e.TRAIN else 1, "hook_views": e.hook_views(ctx)}
    purpose = "fix/%d/%d" % (change.n, attempt or 1)
    reply, call = e._ask(ctx, user, purpose)
    if call is None:
        return None, "no_calls_left"
    changes, failures = read_call(ctx, reply, call, purpose, change=change)
    return (changes[0], None) if changes and not failures else (None, "unparseable")


def run(ctx):
    from . import engineer as e
    train = ctx.mode == e.TRAIN
    if p.is_v29(ctx.configuration):
        from . import engineer_v29
    findings, analysed_refs, analysis = e.analyse(ctx) if train else (None, [], None)
    user = e.payload(ctx, findings) if train else e.payload(ctx)
    ctx.sheet["shown"] = e._shown_references(user) + analysed_refs + (e._earlier_references(ctx) if train else []) + e._output_references(ctx, user)
    ctx.sheet.pop("disclosed", None)
    reply, call = e._ask(ctx, user, "propose")
    changes, failures = read_call(ctx, reply, call, "propose")
    proposals = [{"call": call, "parsed": not failures, "changes": len(changes),
                  **({"reason": "unparseable", "failures": failures} if failures else {})}]
    survivors, outcomes, taken, lint = [], [], set(), []
    for failure in failures:
        outcomes.append({**failure, "kind": None, "id": None, "target": None, "survived": False,
                         "attempts": [], "fix_calls": 0, "fix_replies": [], "summary": {"description": ""}})
    for change in changes:
        attempts, final, replies = [e.check(change, ctx, taken)], change, []
        while not attempts[-1]["passed"] and not attempts[-1].get("unfixable") and len(replies) < (p.TRAIN_FIXES if train else 1):
            fixed, why = fix(ctx, final, attempts[-1], attempt=len(replies) + 1)
            replies.append(why)
            if fixed is not None:
                final = fixed
                attempts.append(e.check(fixed, ctx, taken))
            if why in ("no_calls_left", "unparseable"):
                break
        survived = attempts[-1]["passed"]
        inert = bool(attempts[-1].get("inert"))
        deferred = bool(attempts[-1].get("deferred"))
        audit_fields = {}
        if p.is_v29(ctx.configuration) and survived and not inert and not deferred and final.kind in e.CODED:
            from . import audit
            audit_procedure_id = final.procedure.id
            audited = audit.audit1(ctx, final, attempts[-1])
            audit_fields = {"audits": [audited], "audit_fix_calls": 0}
            if audited["confirmed"]:
                request = {"request": "audit_fix", "bench": ctx.bench,
                           "change": dict(final.entry, source=final.source),
                           "instruction": audit.audit_fix_prompt(final, audited)}
                reply, audit_call = e._ask(ctx, request, "audit-fix/%d" % final.n)
                audit_fields["audit_fix_calls"] = int(audit_call is not None)
                repaired, failures = read_call(ctx, reply, audit_call, "audit-fix/%d" % final.n, change=final) if audit_call else ([], [])
                if not repaired or failures:
                    survived = False
                    audit_fields["reason"] = "audit_fix_failed_checks"
                else:
                    final = repaired[0]
                    attempts.append(e.check(final, ctx, taken))
                    survived = attempts[-1]["passed"]
                    inert, deferred = bool(attempts[-1].get("inert")), bool(attempts[-1].get("deferred"))
                    if not survived:
                        audit_fields["reason"] = "audit_fix_failed_checks"
                    elif not inert and not deferred:
                        audited = audit.audit1(ctx, final, attempts[-1])
                        audit_fields["audits"].append(audited)
                        if audited["confirmed"]:
                            survived = False
                            audit_fields["reason"] = "audit_confirmed"
            # This lint is run-slice-only; audit2 never calls the engineer or writes its lint.
            attempts[-1].setdefault("lint", {"id": audit_procedure_id, "tests": [], "problems": []})["audit"] = audit.feedback(audited)
        if survived and not inert and not deferred:
            survivors.append(final)
            taken.add(final.target)
        if attempts[-1].get("lint"):
            lint.append(attempts[-1]["lint"])
        outcomes.append({**final.to_json(), "attempts": attempts, "survived": survived, "inert": inert, "deferred": deferred,
                         "fix_calls": len(replies), "fix_replies": replies, "summary": e._summary(final),
                         **({"reason": "unparseable"} if replies and replies[-1] == "unparseable" else {}), **audit_fields})
    package, kept = e._combined_train(ctx, survivors) if train else e._combined(ctx.parent, survivors, ctx.step)
    fields = {"bench": ctx.bench, "k": ctx.k, "step": ctx.step, "label": ctx.label, "parent_sha256": ctx.parent.sha256,
              "prompt_sha256": (engineer_v29.audit.text_sha256(engineer_v29.system(ctx.configuration, train=train))
                                if p.is_v29(ctx.configuration) else digest(system(ctx.configuration, train=train))), "proposals": proposals, "changes": outcomes,
              "kept": [c.n for c in kept], "dropped": [c.n for c in survivors if c not in kept],
              "candidate_sha256": package.sha256 if package else None,
              "procedures": [proc.to_json() for proc in package.procedures] if package else [],
              "calls": ctx.roles.count("engineer/%s/" % ctx.label), "earlier_calls": ctx.spent,
              "repairs": [repair for outcome in outcomes for repair in outcome.get("repairs", [])],
              "format_retries": ctx.sheet.get("format_retries", []),
              **({"payload_trimming": user["payload_trimming"]} if "payload_trimming" in user else {})}
    if p.is_v29(ctx.configuration):
        audits = ctx.sheet.get("audits", [])
        fields.update(audits=audits, audit_incomplete=sum(a["audit_incomplete"] for a in audits),
                      audit_fix_calls=sum(row.get("audit_fix_calls", 0) for row in outcomes),
                      audit_tokens={judge: {key: sum(a["tokens"][judge][key] for a in audits)
                          for key in ("input", "output", "charged")} for judge in ("G", "D")})
    if train:
        fields.update(mode=e.TRAIN, round=ctx.round, base_sha256=ctx.base.sha256, budget=e.budget(ctx), lint=lint,
                      analysis=analysis, analyst_prompt_sha256=e.ANALYST_PROMPT_SHA256, disclosed=e._disclosed_items(ctx))
    return package, p.record(p.ENGINEER_RECORDS[ctx.configuration], ctx.evidence, fields)
