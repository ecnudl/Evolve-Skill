"""The SX rehearsal's fakes (v2's example stage, owner decision 2026-10-23 13:3x; ``smoke-run --stage SX --fake``):
the example step end to end with zero network, beside the S3 rehearsal's ``execskill_fakes_s3.py`` (unchanged).

- ``SXScript``: one scripted glm-5.3 gateway for the smoke solver and the method roles of a chain-G smoke, told apart
  by the pinned system prompt of each call: the analysts name one finding on the items they were shown, the engineer
  proposes one note procedure (sent again unchanged when asked to fix it), the leakage adjudicator keeps everything,
  the describer writes ``NOTE_TEXT``, the examiner writes no detector (SearchQA neither generates nor researches,
  §7.2; any policy, generator or research prompt gets an unusable reply); every other prompt -- the smoke solver's --
  gets ``fallback`` (``smoke._rehearsal_reply``).
- ``SXRehearsal``: the script with FakeWikipedia for the research sources.
Nothing here is real benchmark content.
"""
from __future__ import annotations

import json
import threading

from skillopt.coevo5 import leakage
from skillopt.execskill import describer, engineer, examiner, research
from tests.execskill_fakes import engineer_reply, fenced
from tests.execskill_fakes_research import FakeWikipedia
from tests.execskill_fakes_s3 import NOTE_TEXT

WORDS = """
def applies(view):
    return "question" in view

def before_call(view, state):
    return {"facts": ["The question has %d words." % len(str(view["question"]).split())]}
"""
CHANGE = {"kind": "new", "description": "Counts the words of the question and shows the count as a fact.",
          "hooks": ["applies", "before_call"], "max_note_chars": 600}
ROLE_OF = {engineer.ANALYST_SYSTEM: "analyst", engineer.ENGINEER_SYSTEM_V2: "engineer",
           leakage.ADJUDICATE_SYSTEM: "leakage", describer.DESCRIBER_SYSTEM: "describer",
           examiner.DETECTOR_SYSTEM: "detector", examiner.POLICY_SYSTEM_V2: "unusable",
           examiner.GENERATOR_SYSTEM_V2: "unusable", research.QUERY_SYSTEM: "unusable",
           research.PICK_SYSTEM: "unusable", **{system: "unusable" for system in research.CONCLUDE_SYSTEM.values()}}


class SXScript:
    """FakeProvider's ``answer(system, user)`` for SX (module docstring). ``seen`` lists (role, payload) of the role
    calls, in order."""

    def __init__(self, fallback):
        self.fallback, self.seen, self.lock = fallback, [], threading.Lock()

    def roles(self):
        return [name for name, _ in self.seen]

    def __call__(self, system, user):
        name = ROLE_OF.get(system)
        if name is None:
            return self.fallback(system, user)
        try:
            payload = json.loads(user)
        except ValueError:
            payload = user
        with self.lock:
            self.seen.append((name, payload))
        return getattr(self, "_" + name)(payload)

    @staticmethod
    def _analyst(payload):
        shown = [t["task_id"] for t in payload["trajectories"]]
        return engineer_reply({"findings": [{"pattern": "Long questions are answered with a bare number.",
                                             "items": shown[:2], "helper": "Count the question's words."}]}, [])

    @staticmethod
    def _engineer(payload):
        return engineer_reply({"changes": [dict(CHANGE)]}, [WORDS])

    @staticmethod
    def _leakage(payload):
        return json.dumps({"verdict": "no", "reason": "General advice on reading the task."})

    @staticmethod
    def _describer(payload):
        return NOTE_TEXT

    @staticmethod
    def _detector(payload):
        return fenced(json.dumps({"detectors": []}), "json")

    @staticmethod
    def _unusable(payload):
        return "No plan."


class SXRehearsal:
    """What ``smoke._sx`` runs on in fake mode: ``script`` (an ``SXScript`` over ``fallback``) and ``wikipedia``."""

    def __init__(self, fallback):
        self.script = SXScript(fallback)
        self.wikipedia = FakeWikipedia()
