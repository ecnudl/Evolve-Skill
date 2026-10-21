"""Learning v11 ``active_evidence``: evidence-driven Skill evolution without a canonical validation split (10/9); the
post-update decision uses a fresh panel sampled from a fixed reserved development challenge pool.

Per step: train execution -> code triage of every row -> causal hypotheses for a few representative cases ->
on-demand Research (whitelisted documentation only) -> hypothesis-bound diagnostic checks (BigCodeBench: executed in
the pinned container; text domains: judged obligations) -> itemized, graded evidence reports for the analysts ->
the repository's native Skill updater -> the frozen Current and the frozen Candidate re-solve a few NEW real tasks
from a challenge pool plus a replay sample of step rows -> keep / revert / park under rules frozen before the
comparison. Dynamic tasks and replay are learning-process data, never a final evaluation.

The package lives outside ``skillopt/continual_learning`` on purpose (the precedent is ``feedback_study``):
``contracts.sources()`` hashes every module there, so a new file inside it would change the frozen learning source
identity and the current checkout could no longer validate any sealed v8-v10 stage (which this mode imports train
rollouts from). The mode reuses the v10 mechanisms as a library -- ledger, solver adapter, probe parser/review/
execution helpers, native updater pipeline -- and binds its own code by hash in its sealed protocol.
"""
from __future__ import annotations

PROTOCOL = "active-evidence-learning-v11"
METHOD = "active_evidence"
# Exactly the package modules a run can execute (the learning sources are bound by the base record); a later
# module enters the identity only when it is listed here.
MODULES = ("__init__.py", "protocol.py", "profiles.py", "triage.py", "diagnoser.py", "checks.py", "reports.py",
           "research.py", "diagnosis.py", "updater.py", "challenge.py", "decision.py", "stage.py",
           "label_feedback.py", "matched.py", "screen.py")
