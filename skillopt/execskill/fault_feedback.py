"""Bounded v2.9.1 diagnostics from actual C6 calls, without executing any hooks.

The callers opt in by configuration. Historical replay/engineer records never
invoke these helpers. Counts are distinct task ids across both C6 passes and
C6b routing; a predicate fault counts as faulted only for an item that applied
in at least one of those observations.
"""
from __future__ import annotations

import copy
import json
from collections import Counter, defaultdict

VIEW_CHARS = 4000
STATE_CHARS = 1000
MESSAGE_CHARS = 300
SIGNATURES = 5
SOURCE_CHARS = 200
LINT_BYTES = 4000
EVIDENCE_BYTES = 16000
TRUNCATION_MARKER = "... [truncated]"


def _json(value):
    # Match engineer._ask's serializer, including separator whitespace.
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def serialized_bytes(value):
    return len(_json(value).encode("utf-8"))


def lint_extension(value):
    """The exact C6 diagnostic extension sent with next-round lint."""
    return {key: value[key] for key in ("signatures", "dropped_notes", "truncated") if key in value}


def _source_text(text):
    return text if len(text) <= SOURCE_CHARS else text[:SOURCE_CHARS - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER


def _truncated_argument(value):
    return isinstance(value, dict) and value.get("truncated") is True and "json_prefix" in value


def _argument_bytes(value, limit):
    """Shorten an argument's JSON prefix to a byte allowance, including its wrapper."""
    if serialized_bytes(value) <= limit:
        return copy.deepcopy(value)
    encoded = value["json_prefix"] if _truncated_argument(value) else _json(value)
    low, high = 0, len(encoded)
    while low < high:
        middle = (low + high + 1) // 2
        if serialized_bytes({"truncated": True, "json_prefix": encoded[:middle]}) <= limit:
            low = middle
        else:
            high = middle - 1
    return {"truncated": True, "json_prefix": encoded[:low]}


def bound_diagnostics(value, *, example):
    """Preserve counts; fit diagnostic displays using the actual request serializer.

    Keep the most frequent signature when possible. Remove lower-ranked signatures,
    then context lines, then argument prefixes. Oversized residual identifiers can
    be omitted as a last resort, rather than returned as invented shortened IDs.
    """
    result = copy.deepcopy(value)
    projection = (lambda: result) if example else (lambda: lint_extension(result))
    limit = EVIDENCE_BYTES if example else LINT_BYTES
    arguments = (result.get("example_call") or {}).get("arguments", {})
    for name, argument in list(arguments.items()):
        cap = STATE_CHARS if name == "state" else VIEW_CHARS
        bounded = bounded_json(argument, cap)
        if bounded != argument or _truncated_argument(argument):
            result["truncated"] = True
        arguments[name] = bounded
    if serialized_bytes(projection()) <= limit:
        return result
    result["truncated"] = True
    while serialized_bytes(projection()) > limit and len(result["signatures"]) > 1:
        result["signatures"].pop()
    for signature in reversed(result["signatures"]):
        context = signature.get("source_context", [])
        while serialized_bytes(projection()) > limit and context:
            context.pop()
        if not context:
            signature.pop("source_context", None)
    # Sort by current encoded size, with a stable name tie-break. Null state and
    # other small exact arguments remain intact while large arguments shrink.
    minimum = serialized_bytes({"truncated": True, "json_prefix": ""})
    for name in sorted(arguments, key=lambda key: (-serialized_bytes(arguments[key]), key)):
        excess = serialized_bytes(projection()) - limit
        if excess <= 0:
            break
        size = serialized_bytes(arguments[name])
        if size > minimum:
            arguments[name] = _argument_bytes(arguments[name], max(minimum, size - excess))
    # Runtime hook names and counters are small; task IDs and exception type names
    # can still be long. Omit remaining oversized displays without altering totals.
    while serialized_bytes(projection()) > limit and result["signatures"]:
        result["signatures"].pop()
    reasons = result["dropped_notes"]["top_reasons"]
    while serialized_bytes(projection()) > limit and reasons:
        reasons.pop()
    if serialized_bytes(projection()) > limit and result.get("example_call") is not None:
        result["example_call"] = None
    if serialized_bytes(projection()) > limit and example:
        result["per_hook"] = {}
    assert serialized_bytes(projection()) <= limit
    return result


def bounded_json(value, limit):
    """Keep the exact JSON value when it fits, otherwise label its bounded prefix.

    The limit includes the truncation wrapper and JSON escaping, so the actual
    serialized evidence field never exceeds the advertised character allowance.
    """
    encoded = _json(value)
    if len(encoded) <= limit:
        return json.loads(encoded)
    low, high = 0, min(limit, len(encoded))
    while low < high:
        middle = (low + high + 1) // 2
        result = {"truncated": True, "json_prefix": encoded[:middle]}
        if len(_json(result)) <= limit:
            low = middle
        else:
            high = middle - 1
    return {"truncated": True, "json_prefix": encoded[:low]}


def capture_arguments(hook, args):
    """Snapshot actual hook arguments before execution, preserving None state."""
    names = (("event", "state") if hook == "alf_after_step" else
             ("view", "report", "state") if hook == "sheet_feedback" else
             ("view",) if hook in ("applies", "bindings") else ("view", "state"))
    return {name: bounded_json(value, STATE_CHARS if name == "state" else VIEW_CHARS)
            for name, value in zip(names, args)}


def field_measurements(name, value):
    """Lengths of a rejected note field, including row/column caps when relevant."""
    from .notes import FIELD_TYPES
    strings = []
    def collect(node):
        if isinstance(node, str):
            strings.append(len(node))
        elif isinstance(node, list):
            for entry in node:
                collect(entry)
        elif isinstance(node, dict):
            for entry in node.values():
                collect(entry)
    collect(value)
    measured = {"max_chars": max(strings, default=0)}
    if isinstance(value, list):
        measured["entries"] = len(value)
        if any(isinstance(row, list) for row in value):
            measured["max_columns"] = max((len(row) for row in value if isinstance(row, list)), default=0)
    return {"field": name, "measured_length": measured["max_chars"],
            "field_measurements": measured,
            "field_limits": {key: val for key, val in FIELD_TYPES.get(name, {}).items() if key.startswith("max_")}}


class CapturePredicate:
    """Transparent proxy around the existing C6b predicate call; never calls twice."""
    def __init__(self, worker):
        self.worker, self.calls = worker, []

    def call(self, procedure, hook, args, **kwargs):
        arguments = capture_arguments(hook, args)
        result = self.worker.call(procedure, hook, args, **kwargs)
        self.calls.append({"arguments": arguments, "result": result})
        return result


def predicate_capture(procedure, item, view, routed, captured):
    """A C6b per-item record, with original exception line and exact arguments."""
    result = captured.calls[-1]["result"] if captured.calls else {}
    arguments = captured.calls[-1]["arguments"] if captured.calls else capture_arguments("applies", [view])
    faults = []
    for original in routed.faults:
        kind = "predicate:not_bool" if original["kind"] == "not_bool" else "crash:" + str(original["kind"])
        faults.append({**original, "kind": kind, "step": None,
                       "message": str(original.get("message") or "")[:MESSAGE_CHARS],
                       "line": result.get("line"), "arguments": copy.deepcopy(arguments)})
    return {"task_id": item, "applies": routed.per_procedure.get(procedure.id, {}).get("applies"),
            "faults": faults}


def _detail(report, name):
    return next((row.get("detail") or {} for row in report.get("checks", ()) if row["check"] == name), {})


def output_shape_fields(hook, kind, message, *, v292=False):
    """Child-only explanation, generated from the shell's return-shape rule."""
    if not v292 or kind != "output_shape":
        return {}
    from .donors import expected_shape
    return {"expected": expected_shape(hook), "returned": message}


def shape_fields_ok(row, *, v292=False):
    if not isinstance(row, dict) or (v292 and row.get("kind") == "output_shape"
            and not all(type(row.get(key)) is str for key in ("hook", "message"))):
        return False
    expected = output_shape_fields(row.get("hook"), row.get("kind"), row.get("message"), v292=v292)
    return ({key: row[key] for key in ("expected", "returned") if key in row} == expected
            and (not expected or all(type(row.get(key)) is str for key in expected)))


def summarize(procedure, report, *, limit=SIGNATURES, example=True, configuration=None):
    """Count complete attempts; signatures are stable and count distinct items."""
    from . import profiles as p
    v292 = configuration is not None and p.is_v292(configuration)
    child = p.is_v211(configuration)
    eligible = {row['task_id'] for row in _detail(report, 'C6b').get('captures', ())
                if row.get('example_eligible')} if child else None
    fired, observed = set(), []
    for item in _detail(report, "C6").get("items", ()):
        task = item.get("task_id", item.get("item", item.get("cell")))
        for phase in ("first", "second"):
            outcome = item.get(phase) or {}
            if outcome.get("applies") is True or outcome.get("applies") == "default_true":
                fired.add(task)
            observed.extend((task, fault) for fault in outcome.get("faults", ())
                            if fault.get("procedure", procedure.id) == procedure.id)
    for item in _detail(report, "C6b").get("captures", ()):
        task = item["task_id"]
        if item.get("applies") is True or item.get("applies") == "default_true":
            fired.add(task)
        observed.extend((task, fault) for fault in item.get("faults", ())
                        if fault.get("procedure", procedure.id) == procedure.id)
    dropped = Counter()
    grouped, by_hook, faulted = defaultdict(list), defaultdict(set), set()
    for task, fault in observed:
        if fault.get("informational"):
            # audit_keyword records retained sentences, not actual note drops.
            if str(fault.get("kind", "")).startswith("note_") and fault.get("kind") != "note_audit_keyword":
                dropped[fault.get("reason") or fault["kind"][5:]] += 1
            continue
        if task not in fired:
            continue
        faulted.add(task)
        by_hook[fault.get("hook")].add(task)
        key = (fault.get("hook"), fault.get("kind"), fault.get("exc_type"),
               str(fault.get("message", fault.get("detail", "")) or "")[:MESSAGE_CHARS], fault.get("line"))
        grouped[key].append((task, fault))
    ordered = sorted(grouped, key=lambda key: (-len({task for task, _ in grouped[key]}), _json(key)))
    signatures, shown_lines = [], set()
    truncated = len(ordered) > limit or len(dropped) > 3
    source = procedure.source.splitlines()
    for key in ordered[:limit]:
        entries = grouped[key]
        tasks = sorted({task for task, _ in entries})
        steps = [fault.get("step") for _, fault in entries]
        first_step = min((step for step in steps if type(step) is int), default=None)
        hook, kind, exc_type, message, line = key
        row = {"hook": hook, "kind": kind, "exc_type": exc_type, "message": message, "line": line,
               "items": len(tasks), "first_step": first_step, "example_task_ids": [task for task in tasks if eligible is None or task in eligible][:2]}
        row.update(output_shape_fields(hook, kind, message, v292=v292))
        if type(line) is int and 1 <= line <= len(source):
            row["source_line"] = _source_text(source[line - 1])
            truncated |= row["source_line"] != source[line - 1]
            context = []
            for number in range(max(1, line - 2), min(len(source), line + 2) + 1):
                if number in shown_lines:
                    truncated = True
                    continue
                text = _source_text(source[number - 1])
                truncated |= text != source[number - 1]
                context.append({"line": number, "text": text})
            row["source_context"] = context
            shown_lines.update(entry["line"] for entry in context)
            shown_lines.add(line)
        caps = [fault for _, fault in entries if "measured_length" in fault]
        if caps:
            measured = max(caps, key=lambda fault: fault["measured_length"])
            for name in ("measured_length", "max_note_chars", "bench_cap", "state_bytes",
                         "field", "field_measurements", "field_limits"):
                if name in measured:
                    row[name] = copy.deepcopy(measured[name])
        signatures.append(row)
    threshold = max(1, (len(fired) + 9) // 10)
    result = {"fired": len(fired), "faulted": len(faulted), "threshold": threshold,
              "triggered": len(faulted) >= threshold,
              "per_hook": {hook: len(tasks) for hook, tasks in sorted(by_hook.items())},
              "signatures": signatures,
              "dropped_notes": {"count": sum(dropped.values()),
                                "top_reasons": [{"reason": reason, "count": count}
                                                for reason, count in sorted(dropped.items(), key=lambda pair: (-pair[1], pair[0]))[:3]]}}
    if truncated:
        result["truncated"] = True
    if example:
        result["example_call"] = None
        if ordered:
            entries = sorted(grouped[ordered[0]], key=lambda item: (item[0],
                -1 if item[1].get("step") is None else item[1]["step"]))
            if eligible is not None:
                entries = [entry for key in ordered for entry in sorted(grouped[key], key=lambda row: row[0])
                           if entry[0] in eligible]
            if not entries:
                return bound_diagnostics(result, example=example)
            task, fault = entries[0]
            result["example_call"] = {"task_id": task, "hook": fault.get("hook"), "step": fault.get("step"),
                                      "arguments": copy.deepcopy(fault.get("arguments", {}))}
    return bound_diagnostics(result, example=example)


def lint_details_ok(row, *, v292=False):
    """Validate the bounded diagnostic extension allowed in next-round lint."""
    if not isinstance(row, dict) or "truncated" in row and row["truncated"] is not True:
        return False
    try:
        if serialized_bytes(lint_extension(row)) > LINT_BYTES:
            return False
    except (TypeError, ValueError, UnicodeError):
        return False
    if any(type(row.get(key)) is not int or row[key] < 0 for key in ("fired_items", "faulted_items")):
        return False
    if row["faulted_items"] > row["fired_items"]:
        return False
    signatures = row.get("signatures")
    if not isinstance(signatures, list) or len(signatures) > 3:
        return False
    required = {"hook", "kind", "exc_type", "message", "line", "items", "first_step", "example_task_ids"}
    optional = {"source_line", "source_context", "measured_length", "max_note_chars", "bench_cap", "state_bytes",
                "field", "field_measurements", "field_limits"}
    if v292:
        optional |= {"expected", "returned"}
    for signature in signatures:
        if not isinstance(signature, dict) or not required <= set(signature) or set(signature) - required - optional:
            return False
        if not shape_fields_ok(signature, v292=v292):
            return False
        if (not all(type(signature[key]) is str for key in ("hook", "kind", "message"))
                or len(signature["message"]) > MESSAGE_CHARS
                or signature["exc_type"] is not None and type(signature["exc_type"]) is not str
                or type(signature["items"]) is not int or signature["items"] < 1
                or not isinstance(signature["example_task_ids"], list) or len(signature["example_task_ids"]) > 2
                or not all(type(item) is str for item in signature["example_task_ids"])):
            return False
        if any(signature[key] is not None and type(signature[key]) is not int for key in ("line", "first_step")):
            return False
        if any(type(signature[key]) is not int or signature[key] < 0 for key in
               ("measured_length", "max_note_chars", "bench_cap", "state_bytes") if key in signature):
            return False
        if "source_line" in signature and (type(signature["source_line"]) is not str
                                            or len(signature["source_line"]) > SOURCE_CHARS):
            return False
        if "field" in signature and type(signature["field"]) is not str:
            return False
        if "source_context" in signature:
            context = signature["source_context"]
            if (not isinstance(context, list) or len(context) > 5 or any(
                    not isinstance(entry, dict) or set(entry) != {"line", "text"}
                    or type(entry["line"]) is not int or type(entry["text"]) is not str
                    or len(entry["text"]) > SOURCE_CHARS for entry in context)):
                return False
        for key in ("field_limits", "field_measurements"):
            if key in signature and (not isinstance(signature[key], dict) or not all(
                    type(name) is str and type(number) is int and number >= 0
                    for name, number in signature[key].items())):
                return False
            allowed = ({"max_chars", "max_rows", "max_columns"} if key == "field_limits" else
                       {"max_chars", "entries", "max_columns"})
            if key in signature and not set(signature[key]) <= allowed:
                return False
    dropped = row.get("dropped_notes")
    return (isinstance(dropped, dict) and set(dropped) == {"count", "top_reasons"}
            and type(dropped["count"]) is int and dropped["count"] >= 0
            and isinstance(dropped["top_reasons"], list) and len(dropped["top_reasons"]) <= 3
            and all(isinstance(entry, dict) and set(entry) == {"reason", "count"}
                    and type(entry["reason"]) is str and type(entry["count"]) is int and entry["count"] > 0
                    for entry in dropped["top_reasons"]))
