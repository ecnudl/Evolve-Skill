"""Trajectories and the enable log of route-B cells (protocol ``fivebench-execskill-v1``; registration §2.3, §4.3,
§5.1, §7.1 after Codex F10; implementation plan §1 trajectories row, §2.2, §2.3; T-TRAJ-1).

A trajectory is what one training-side cell showed the solver and got back, written once as a sealed
``fivebench-execskill-v1-trajectory`` record to ``<attempt>/trajectories/<cell>.json``: per logical call its purpose,
system and user texts, request hash and a receipt summary; the replies; the deciding receipt, the worst delivery and
the logical calls with their transport sends; the shell's notes, computations, pre-check report, procedure calls,
faults and fallback; on ALFWorld every step with the observation it saw, the reply, the action and the observation
after it (the frozen transition trace); the judge and the v2 token; dispatch and finish times. Test-read cells keep
hashes only (plan §2.10) and have no trajectory.

The enable log (§2.2) is ``<attempt>/enable_log.jsonl``: one sealed ``fivebench-execskill-v1-enable`` line per routed
cell, appended after the cell record.

What the method roles read (§4.3, §7.1):
- ``whitelisted``: the trajectory cut to an explicit key whitelist; a trajectory that carries hidden environment data
  (an expert plan, a game file, an ``extra`` key -- in any field or in any request it records) is refused.
- ``masked_view``: the detector's view (``purpose`` "detector") and the examiner's ("examiner": plus the right/wrong
  bit, never the reference). QA: the task's public view, the notes shown and the replies with every answer carrier
  masked (answer tags, unclosed ones included; JSON "answer" values; SearchQA's last non-empty line when it has
  neither, the frozen scorer's fallback) AND every other occurrence of a carried answer anywhere in the reply
  (case-insensitive, whitespace-normalised; a number also by value), on LiveMath also the chosen option's letter
  references and its option text -- with the right/wrong bit, a restated answer would be the reference (isolation
  review 7). SpreadsheetBench: the task, the first notes and the first program only --
  the pre-check report and the repair exchange are the program's run status on the public input. ALFWorld: the
  landmark view.
- ``landmark_view`` (Codex F10): only episodes still running after step 10 (more than 10 steps) and not censored by
  infrastructure, shown as exactly their first 10 (observation, action) pairs -- no observation after step 10, no
  terminal observation, no won/done flag, no step count. Every other episode is ``Excluded`` with its reason:
  ``ended_by_step_10:<won|done|infrastructure>``, or ``censored:infrastructure`` for an infrastructure-censored
  episode that ran past step 10.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from skillopt.coevo5.calls import USAGE_FIELDS
from skillopt.coevo5.cells import exclusive
from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import outcomes_ext, zebralogic
from .profiles import is_v29
from .profiles import SUPPORTED_BENCHES as BENCHES, LANDMARK_STEPS, NOTES_KEY, QA, RECORD_HASH, record, verified

TRAJECTORIES = "trajectories"
ENABLE_LOG = "enable_log.jsonl"
PURPOSES = ("detector", "examiner")
MASK = "[masked]"
UNKNOWN_TOKENS = ("unknown", "unknown_artifact", outcomes_ext.UNKNOWN_FAULT)
HIDDEN = frozenset({"expert_plan", "gamefile", "game_file", "extra"})
TOP = ("cell", "unit", "arm", "arm_kind", "bench", "task_id", "run", "package_sha256", "route", "calls", "replies",
       "deciding_receipt", "worst_delivery", "shell", "alfworld_steps", "token")
CALL_KEYS = ("purpose", "system", "user", "request_sha256", "receipt")
SHELL_KEYS = ("notes", "compute", "precheck", "procedure_calls", "faults", "fallback")
STEP_KEYS = ("i", "observation", "notes", "discouraged", "reply", "action", "how", "post_observation")
ANSWER_TAG = re.compile(r"(<answer>)(.*?)(</answer>)", re.S | re.I)
OPEN_TAG = re.compile(r"(<answer>)((?:(?!</answer>).)*)$", re.S | re.I)
JSON_ANSWER = re.compile(r'("answer"\s*:\s*)("(?:[^"\\]|\\.)*"|-?\d[\d.eE+-]*)')
NUMBER_TOKEN = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?!\w)")
OPTION_LINE = re.compile(r"^\s*\(?([A-E])[.)]\s*(.+?)\s*$", re.M)
LETTER = re.compile(r"\(?([A-E])\)?")


@dataclass(frozen=True)
class Excluded:
    """An episode the landmark task does not use (Codex F10) and why (module docstring)."""
    reason: str


# ----------------------------------------------------------------------------------------------- the record
def receipt_summary(receipt):
    """What a trajectory keeps of a receipt besides its reply: the delivery state (``outcomes_ext.delivery``), the
    finish reason and the usage counts."""
    if not isinstance(receipt, dict):
        return {"delivery": outcomes_ext.delivery(receipt)}
    usage = receipt.get("usage") if isinstance(receipt.get("usage"), dict) else {}
    finish, visible = receipt.get("finish_reason"), receipt.get("visible_completion_tokens")
    return {"delivery": outcomes_ext.delivery(receipt), "finish_reason": finish if isinstance(finish, str) else None,
            "usage": {name: usage.get(name) if type(usage.get(name)) is int else None for name in USAGE_FIELDS},
            "visible_completion_tokens": visible if type(visible) is int else None}


def _reply(receipt):
    reply = receipt.get("response") if isinstance(receipt, dict) else None
    return reply if isinstance(reply, str) else None


def _steps(calls, prediction, shell):
    """The shell's ALFWorld steps with the observation each step saw (its request), the reply and the observation
    after it (the frozen trace's ``post_observation``); the i-th step is the i-th ``step`` call."""
    asked = [call for call in calls if call["purpose"] == "step"]
    trace = prediction.get("trace") if isinstance(prediction.get("trace"), list) else []
    out = []
    for entry in shell.get("alfworld_steps") or []:
        i = entry["i"]
        require(type(i) is int and 0 <= i < len(asked), "Each ALFWorld step has its call")
        after = trace[i] if i < len(trace) and isinstance(trace[i], dict) else {}
        out.append({"i": i, "view_sha256": entry["view_sha256"],
                    "observation": json.loads(asked[i]["user"]).get("observation"), "notes": entry["notes"],
                    "discouraged": entry["discouraged"], "reply": _reply(asked[i]["receipt"]),
                    "action": entry["action"], "how": entry["how"],
                    "post_observation": after.get("post_observation"), "state_sha256": entry["state_sha256"]})
    return out


def build(cell, *, evidence, arm_kind, package_sha256, calls, prediction, judge, deciding, worst, logical_calls,
          dispatch_ts, finish_ts, configuration=None, solver_route=None, keyword_hits=None):
    """The trajectory record of one completed cell (plan §2.3). ``calls``: the logical calls of the solve whose
    prediction is final, each {purpose, system, user, request_sha256, receipt}; ``prediction``: that prediction;
    ``judge``: the cell's judge record; ``deciding``, ``worst``, ``logical_calls``: the cell record's."""
    shell = prediction.get("shell") if isinstance(prediction.get("shell"), dict) else {}
    fields = {
        "cell": cell["id"], "unit": cell["unit"], "arm": cell["arm"], "arm_kind": arm_kind,
        "bench": cell["benchmark"], "task_id": cell["task_id"], "run": cell["run"], "package_sha256": package_sha256,
        "route": shell.get("route"),
        "calls": [{"purpose": call["purpose"], "system": call["system"], "user": call["user"],
                   "request_sha256": call["request_sha256"], "receipt": receipt_summary(call["receipt"])}
                  for call in calls],
        "replies": [_reply(call["receipt"]) for call in calls], "deciding_receipt": deciding, "worst_delivery": worst,
        "logical_calls": logical_calls,
        "shell": {"notes": shell.get("notes", []), "compute": shell.get("compute"), "precheck": shell.get("precheck"),
                  "procedure_calls": shell.get("procedure_events", []), "faults": shell.get("faults", []),
                  "fallback": shell.get("fallback")},
        "alfworld_steps": _steps(calls, prediction, shell) if cell["benchmark"] == "alfworld" else None,
        "judge": judge, "token": judge["v2"]["token"], "dispatch_ts": dispatch_ts, "finish_ts": finish_ts}
    if configuration == 'main-v4':
        fields['shell']['effects'] = list(shell.get('effects', ()))
    if is_v29(configuration):
        models = list(dict.fromkeys(call["receipt"].get("returned_model") for call in calls
                                   if isinstance(call.get("receipt"), dict) and call["receipt"].get("returned_model")))
        fields.update(configuration=configuration, solver_route=solver_route, returned_models=models,
                      returned_model=models[-1] if models else None,
                      keyword_hits=keyword_hits or {"count": 0, "sentences": []})
        fields["shell"]["keyword_hits"] = fields["keyword_hits"]
        for original, kept in zip(calls, fields["calls"]):
            receipt = original.get("receipt") or {}
            kept["receipt"].update(returned_model=receipt.get("returned_model"),
                                   route=receipt.get("route", (solver_route or {}).get("route")))
    return record("trajectory", evidence, fields)


def write(attempt, cell_id, value):
    """Write a cell's trajectory once: ``<attempt>/trajectories/<cell>.json``."""
    value = verified(value, "trajectory")
    require(value["cell"] == cell_id, "The trajectory of this cell")
    write_json(safe_path(attempt) / TRAJECTORIES / (cell_id + ".json"), value)
    return value


def load_run(unit_root):
    """The trajectories of a completed unit (its ``unit.json`` names the attempt), each verified, in (arm, task id,
    run) order."""
    unit_root = safe_path(unit_root)
    unit = verified(read_json(unit_root / "unit.json"), "unit")
    require(unit["status"] == "complete", "A completed unit")
    directory = unit_root / unit["attempt"] / TRAJECTORIES
    found = [verified(read_json(path), "trajectory") for path in sorted(directory.glob("*.json"))] \
        if directory.is_dir() else []
    return sorted(found, key=lambda t: (t["arm"], t["task_id"], t["run"]))


# ----------------------------------------------------------------------------------------------- the enable log
def append_enable(attempt, cell_record, route):
    """Append one cell's enable-log line (§2.2; plan §2.2) after its record. ``route``: the sealed route of the
    cell's final prediction (``router.RouteLog.to_json``)."""
    route = verified(route, "route")
    cell, per = cell_record["cell"], route["per_procedure"]
    line = record("enable", cell_record["evidence"], {
        "unit": cell["unit"], "arm": cell["arm"], "bench": cell["benchmark"], "item": cell["task_id"],
        "run": cell["run"], "enabled": list(route["enabled"]),
        "withheld": [pid for pid, entry in per.items() if entry["withheld"]],
        "applies": {pid: entry["applies"] for pid, entry in per.items()}, "faults": list(route["faults"]),
        "route_sha256": route[RECORD_HASH]})
    path = safe_path(attempt) / ENABLE_LOG
    with exclusive(path.with_name(ENABLE_LOG + ".lock"), wait=True):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    return line


def enable_log(attempt):
    """The enable-log lines of an attempt, each verified, in append order."""
    path = safe_path(attempt) / ENABLE_LOG
    if not path.exists():
        return []
    return [verified(json.loads(line), "enable") for line in path.read_text(encoding="utf-8").splitlines() if line]


# ------------------------------------------------------------------------------------------------------ views
def _refuse_hidden(value):
    if isinstance(value, dict):
        for name, item in value.items():
            if name in HIDDEN or str(name).startswith("extra."):
                raise ValueError("hidden_environment_data: %s" % name)
            _refuse_hidden(item)
    elif isinstance(value, list):
        for item in value:
            _refuse_hidden(item)


def whitelisted(trajectory):
    """The trajectory cut to the whitelist (``TOP``, ``CALL_KEYS``, ``SHELL_KEYS``, ``STEP_KEYS``); ValueError when it
    or a request it records carries hidden environment data."""
    trajectory = verified(trajectory, "trajectory")
    _refuse_hidden(trajectory)
    for call in trajectory["calls"]:
        _refuse_hidden(zebralogic.parse_user(call["user"]) if trajectory["bench"] == zebralogic.BENCH
                       else json.loads(call["user"]))
    out = {name: trajectory[name] for name in TOP}
    out["calls"] = [{name: call[name] for name in CALL_KEYS} for call in trajectory["calls"]]
    out["shell"] = {name: trajectory["shell"][name] for name in SHELL_KEYS}
    if trajectory["alfworld_steps"] is not None:
        out["alfworld_steps"] = [{name: step[name] for name in STEP_KEYS} for step in trajectory["alfworld_steps"]]
    return out


def _carried(bench, reply):
    """The answers a reply's carriers hold: answer tags (closed and unclosed), JSON "answer" values and, on SearchQA
    without either, the last non-empty line."""
    if bench == zebralogic.BENCH:
        return zebralogic.carried_values(reply)
    found = [m.group(2) for m in ANSWER_TAG.finditer(reply)] + [m.group(2) for m in OPEN_TAG.finditer(reply)]
    for m in JSON_ANSWER.finditer(reply):
        try:
            found.append(str(json.loads(m.group(2))))
        except ValueError:
            found.append(m.group(2))
    if bench == "searchqa" and not found:
        lines = [line for line in reply.split("\n") if line.strip()]
        found += lines[-1:]
    return [a.strip() for a in found if a.strip()]


def _number(text):
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _restated(text, answer):
    """``text`` with every further occurrence of ``answer`` masked: word-bounded, case-insensitive, any whitespace;
    a number also by its value (thousands separators, trailing zeros)."""
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(word) for word in answer.split()) + r"(?!\w)"
    text = re.sub(pattern, MASK, text, flags=re.I)
    value = _number(answer)
    if value is not None:
        text = NUMBER_TOKEN.sub(lambda m: MASK if _number(m.group(0)) == value else m.group(0), text)
    return text


def _option_masked(text, answer, choices):
    """LiveMath: the chosen option's letter references ("option C", "(C)", a line "C.") and its option text."""
    letter = LETTER.fullmatch(answer.strip())
    if letter is None:
        return text
    letter = letter.group(1)
    text = re.sub(r"(?i:\b(?:option|choice|answer)\b\s*(?:is\s*)?:?\s*)\(?%s\)?(?![A-Za-z])" % letter, MASK, text)
    text = re.sub(r"\(%s\)|^\s*%s[.)]" % (letter, letter), MASK, text, flags=re.M)
    for found, option in OPTION_LINE.findall(choices if isinstance(choices, str) else ""):
        if found == letter:
            text = _restated(text, option)
    return text


def mask_answers(bench, reply, *, choices=None):
    """``reply`` with the content of every answer carrier, and every restatement of a carried answer, replaced by
    ``MASK`` (module docstring); ``choices``: LiveMath's public options."""
    if bench == zebralogic.BENCH:
        return zebralogic.mask_reply(reply)
    require(bench in QA, "Answer carriers are masked on the QA benches")
    if reply is None:
        return None
    answers = _carried(bench, reply)
    masked, closed = ANSWER_TAG.subn(lambda m: m.group(1) + MASK + m.group(3), reply)
    masked, opened = OPEN_TAG.subn(lambda m: m.group(1) + MASK, masked)
    masked, numbered = JSON_ANSWER.subn(lambda m: m.group(1) + json.dumps(MASK), masked)
    if bench == "searchqa" and not closed + opened + numbered:
        lines = reply.split("\n")
        last = max((i for i, line in enumerate(lines) if line.strip()), default=None)
        if last is not None:
            lines[last] = MASK
        masked = "\n".join(lines)
    for answer in answers:
        masked = _restated(masked, answer)
        if bench == "livemath":
            masked = _option_masked(masked, answer, choices)
    return masked


def landmark_view(trajectory):
    """The ALFWorld landmark view (module docstring), or ``Excluded``."""
    trajectory = whitelisted(trajectory) if RECORD_HASH in trajectory else trajectory
    require(trajectory["bench"] == "alfworld", "The landmark view is ALFWorld's")
    steps = trajectory["alfworld_steps"] or []
    longer = len(steps) > LANDMARK_STEPS
    if trajectory["token"] in UNKNOWN_TOKENS:
        return Excluded("censored:infrastructure" if longer else "ended_by_step_10:infrastructure")
    if not longer:
        return Excluded("ended_by_step_10:" + ("won" if trajectory["token"] == "pass" else "done"))
    return {"bench": "alfworld",
            "steps": [{"observation": step["observation"], "action": step["action"]}
                      for step in steps[:LANDMARK_STEPS]]}


def masked_view(trajectory, *, bench, purpose):
    """What a detector (``purpose`` "detector") or the examiner ("examiner") reads of one trajectory (module
    docstring); ``Excluded`` for an ALFWorld episode outside the landmark task or a cell without a model call."""
    require(bench in BENCHES and purpose in PURPOSES, "A known bench and purpose")
    clean = whitelisted(trajectory)
    require(clean["bench"] == bench, "A trajectory of the bench")
    if bench == "alfworld":
        view = landmark_view(clean)
        if isinstance(view, Excluded):
            return view
    else:
        if not clean["calls"]:
            return Excluded("no_call")
        require(clean["calls"][0]["purpose"] == "first", "A QA or sheet trajectory starts with its first call")
        task = (zebralogic.parse_user(clean["calls"][0]["user"]) if bench == zebralogic.BENCH
                else json.loads(clean["calls"][0]["user"]))
        notes = task.pop(NOTES_KEY, None)
        replies = ([mask_answers(bench, reply, choices=task.get("choices")) for reply in clean["replies"]]
                   if bench in (*QA, zebralogic.BENCH) else clean["replies"][:1])
        if bench == zebralogic.BENCH and notes:
            notes = MASK  # an exact solver can carry the entire answer grid in its notes
        view = {"bench": bench, "task": task, "notes": notes, "replies": replies}
    if purpose == "examiner":
        view["passed"] = clean["token"] == "pass"
    return view
