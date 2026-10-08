"""V8 transfer requirement shared by native SkillOpt's analysts and GEPA's reflection prompt."""
from __future__ import annotations

# V8 transfer requirement, appended to both native analyst prompts (never replacing them).
# The Skill is deployed to unseen tasks and to other domains by one solver that answers in a
# single response without any code-execution tool, so edits must be transferable procedures.
TRANSFER_PREAMBLE_VERSION = "transfer-requirement-v1"
TRANSFER_PREAMBLE = """

## Transfer requirement (read before proposing edits)
The skill will be applied to UNSEEN tasks of the same kind and to tasks from OTHER domains, by a
solver that answers in ONE response and has NO code-execution tool (it cannot run Python, open
files or call the web). Therefore:
- Write every edit as a reusable procedure or check (what to verify, how to derive the result,
  how to format it) that the solver can carry out in its own reasoning text. Never advise
  "run the code" or "execute a script".
- Never copy a specific task's entities, question text, rule statement or expected answer into
  the skill; an example may illustrate a FORMAT only, with invented placeholder content.
- Prefer self-verification procedures (recompute by a second route, round-trip or inverse
  check, re-check every stated constraint) over memorized conclusions.
- Scope each edit to the task kind its evidence came from (e.g. "For rule-based cipher
  tasks ..."); do not state a domain-specific output format as a universal rule, and do not
  add text that could change behavior on unrelated task kinds.
"""
