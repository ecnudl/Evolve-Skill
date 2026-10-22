"""Fakes of the route-B shell and router tests (implementation plan §7; T-SOLVER-1..9, T-ROUTE-1..5): offline and
deterministic -- no model, no docker, no ALFWorld process.

- ``Script``: a call function ``call(system, user) -> receipt`` replying from a list or a function, logging every
  request (the frozen and the route-B solver are driven by two equal scripts and their logs compared byte for byte).
- ``FakeAlfEnv`` / ``alf_sessions``: the frozen ``_AlfSession`` interface (reset, step, close) over one fixture game of
  ``tests/fixtures/execskill/items.py``, installed as ``backends._new_alfworld`` so the frozen loop and the shell open
  the same environment. A step's admissible commands are the game's base commands plus the next plan step; the plan
  step advances the game; the last one wins. ``infos`` carry the expert plan and the game file as the real
  environment's do, so a test can check that none of it reaches a request, a hook or a trace.
- ``FakeNative``: stands for the container runs (``backends._native``) and the pre-check run (``precheck.precheck``),
  answering deterministically and recording the slots the running thread holds.
- ``FakeSandbox``: the ``sandbox.client.Worker`` interface in process. ``hooks`` {procedure id: {function: callable}}
  stand for the procedures' sources (the real worker executes a source only in its container; these tests check the
  shell, and one test drives the real worker through ``tests/execskill_fakes_docker.FakeDocker``); a predicate without
  a callable returns True, any other hook without one returns None (no output). ``raises`` {(id, function): exception}
  and ``faults`` {(id, function): fault kind} force the worker's failures.
- ``procedure``: a valid fixture procedure whose generated source declares the hooks with their registered parameters.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from skillopt.continual_eval import backends
from skillopt.execskill import precheck as prechecks
from skillopt.execskill.package import NOTE_HOOKS, Procedure
from skillopt.validator_pilot.api import digest

USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
PARAMETERS = {"applies": "view", "before_call": "view, state", "bindings": "view",
              "sheet_feedback": "view, run_report, state", "alf_before_step": "view, state",
              "alf_after_step": "event, state"}


def receipt(text, *, finish_reason="stop", visible=None, ok=True):
    """A receipt with the frozen client's keys; ``visible``: the visible completion tokens (chain D's §4.1 rule)."""
    found = {"ok": ok, "response": text, "finish_reason": finish_reason, "status": 200, "usage": dict(USAGE)}
    if visible is not None:
        found["visible_completion_tokens"] = visible
    return found


class Script:
    """``replies``: a list (one per call, in order) or a function of (system, user); a reply is text (a delivered
    receipt), a receipt, or an exception to raise. ``during(system, user)``: runs inside every call (a slot holder).
    ``receipts``: the receipts returned, one per call that returned (the Recorder's logical receipts)."""

    def __init__(self, replies, *, during=None):
        self.replies, self.during, self.requests, self.receipts = replies, during, [], []

    def __call__(self, system, user):
        self.requests.append((system, user))
        if self.during is not None:
            self.during(system, user)
        reply = self.replies(system, user) if callable(self.replies) else self.replies[len(self.requests) - 1]
        if isinstance(reply, BaseException):
            raise reply
        self.receipts.append(reply if isinstance(reply, dict) else receipt(reply))
        return self.receipts[-1]


class FakeAlfEnv:
    def __init__(self, game, *, close_error=None):
        self.game, self.close_error = game, close_error
        self.position, self.actions, self.closed = 0, [], False

    def _infos(self, won):
        admissible, plan = list(self.game["admissible_commands"]), self.game["plan"]
        if self.position < len(plan) and plan[self.position] not in admissible:
            admissible.append(plan[self.position])
        return [{"admissible_commands": admissible, "won": won, "extra.expert_plan": list(self.game["expert_plan"]),
                 "extra.gamefile": self.game["gamefile"]}]

    def reset(self):
        self.position = 0
        return [self.game["initial_observation"]], None, self._infos(False)

    def step(self, actions):
        action, plan = actions[0], self.game["plan"]
        self.actions.append(action)
        moved = self.position < len(plan) and action == plan[self.position]
        self.position += 1 if moved else 0
        won = self.position == len(plan)
        observation = (self.game["terminal_observation"] if won
                       else "You arrive at step %d." % self.position if moved else "Nothing happens.")
        return [observation], None, [1.0 if won else 0.0], [won], self._infos(won)

    def close(self):
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def alf_sessions(monkeypatch, *, close_error=None):
    """Install FakeAlfEnv as ``backends._new_alfworld``; returns the list of sessions opened."""
    sessions = []

    def new(public, runtime):
        game = json.loads(Path(public["game_file"]).read_text(encoding="utf-8"))
        sessions.append(FakeAlfEnv(game, close_error=close_error))
        return sessions[-1]

    monkeypatch.setattr(backends, "_new_alfworld", new)
    return sessions


class FakeNative:
    """``report``: the pre-check report's fields ({status, exc_type, message, answer_cells}); ``holdings``: the
    route-B pools' ``Holdings`` (each run records the pools its thread holds)."""

    def __init__(self, *, report=None, holdings=None):
        self.report = dict(report or {"status": "ok", "answer_cells": {"Sheet!B1": "15"}})
        self.holdings = holdings
        self.cases, self.prechecks, self.held = [], [], []

    def _hold(self, what):
        self.held.append((what, self.holdings.held() if self.holdings is not None else ()))

    def native(self, request, runtime):
        self._hold("case")
        self.cases.append(request)
        return {"status": "available", "reason": "fake_native_case", "code_sha256": digest(request["code"]),
                "cleanup_confirmed": True}

    def precheck(self, program, workbook, answer_position, runtime, *, evidence, tag=None, docker=None):
        """The shell's call (``precheck.precheck``): ``tag`` is the cell worker's unit tag (C5-2), recorded; ``docker``
        is not used by the fake."""
        self._hold("precheck")
        self.prechecks.append({"program": program, "workbook": str(workbook), "answer_position": answer_position,
                               "tag": tag})
        fields = {key: value for key, value in self.report.items() if key != "status"}
        return prechecks.report(self.report["status"], evidence=evidence, **fields)

    def install(self, monkeypatch):
        monkeypatch.setattr(backends, "_native", self.native)
        monkeypatch.setattr(prechecks, "precheck", self.precheck)
        return self


class FakeSandbox:
    def __init__(self, hooks=None, *, raises=None, faults=None):
        self.hooks, self.raises, self.faults = dict(hooks or {}), dict(raises or {}), dict(faults or {})
        self.package = self.kind = self.inputs = None
        self.calls, self.pings, self.closed = [], 0, False

    def start(self, package, *, kind, inputs_dir=None):
        assert self.package is None and not self.closed, "A worker is started once"
        self.package, self.kind = package, kind
        self.inputs = sorted(os.listdir(inputs_dir)) if inputs_dir is not None else None
        return self

    def call(self, proc_id, fn, args, *, timeout_s):
        assert self.package is not None and not self.closed and proc_id in self.package.order and timeout_s > 0
        args = json.loads(json.dumps(list(args)))
        self.calls.append((proc_id, fn, args))
        if (proc_id, fn) in self.raises:
            raise self.raises[(proc_id, fn)]
        if (proc_id, fn) in self.faults:
            return {"ok": False, "fault": self.faults[(proc_id, fn)], "exc_type": None, "message": "forced",
                    "line": None}
        hook = self.hooks.get(proc_id, {}).get(fn)
        try:
            value = hook(*args) if hook is not None else (True if fn == "applies" else None)
        except Exception as error:  # the worker's ``exception`` fault
            return {"ok": False, "fault": "exception", "exc_type": type(error).__name__, "message": str(error),
                    "line": 1}
        value = json.loads(json.dumps(value))
        return {"ok": True, "value": value, "value_sha256": digest(value), "cpu_ms": 1, "rss_kib": 1024}

    def ping(self):
        assert self.package is not None and not self.closed
        self.pings += 1
        return {"ok": True}

    def close(self):
        self.closed = True

    def called(self, fn):
        return [(pid, args) for pid, name, args in self.calls if name == fn]


def source(hooks):
    text = '"""A fixture procedure."""\n'
    for hook in hooks:
        text += "\n\ndef %s(%s):\n    return %s\n" % (hook, PARAMETERS[hook], "True" if hook == "applies" else "None")
    return text


def procedure(pid, hooks, **fields):
    """A valid procedure: ``p-`` ids are smoke records, ``fx-`` ids engineering fixtures."""
    learned = pid.startswith("p-")
    fields.setdefault("origin", pid.split("-")[1] if learned else "officeqa")
    fields.setdefault("evidence", "smoke" if learned else "engineering_fixture")
    fields.setdefault("description", "A fixture procedure %s." % pid)
    fields.setdefault("source", source(hooks))
    fields.setdefault("max_note_chars", 600 if set(hooks) & set(NOTE_HOOKS) else 0)
    fields.setdefault("state_bytes", 256 if "alf_after_step" in hooks else 0)
    return Procedure(id=pid, hooks=tuple(hooks), **fields)
