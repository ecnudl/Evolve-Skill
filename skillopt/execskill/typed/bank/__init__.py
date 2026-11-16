"""typed-v3 item bank (练习题题库): NEW practice items made from TRAINING-SIDE items only.

Design: docs/handoff/typed-v3/PRACTICE-ITEMS-DESIGN.md (owner approved 2026-11-13 "同意，尽快开始") and
BANK-PILOT.md beside it. The bank is built once, outside any chain, in its own root; a chain later only reads its
qualified items. Two benches have no unused real practice items left (OfficeQA 74/74, SpreadsheetBench 91/91 used),
so their new items are MADE here:

- OfficeQA (``oqa``): number twins (the parent's question, the numbers its answer is computed from changed in the
  document, the answer recomputed by fixed code) and new questions on the same document (an item writer gives the
  question and its derivation; the answer is always computed by fixed code).
- SpreadsheetBench (``sheet``): data twins and new instructions (BANK-PILOT.md; built after the OfficeQA part).

Rules that hold everywhere (design §6, §8): a made answer comes from fixed code, never from a model's statement;
fixed code must first reproduce the parent's REFERENCE answer before it may compute a changed one; all items made
from one parent stay on one side (shown to writers / used for judging); nothing here reads a test-side file.
"""
from __future__ import annotations

VERSION = 'typed-bank-v2'   # v2 (2026-11-13, after the pilot roots bank-b and bank-d): the form sentence of percent
                            # questions, a parent's twins set aside together, new sheet tasks (BANK-PILOT B17-B19)
BENCHES = ('officeqa', 'spreadsheetbench')
SEED = 20261113

# OfficeQA quotas of the pilot (per parent; the run-level quotas of design §5 are checked on QUALIFIED items)
TWINS_PER_PARENT = 4
NEW_QUESTIONS_PER_ARM = 3   # per parent and arm; the pilot's two arms: 'plain' (no brief) and 'brief' (research brief)
ARMS = {'plain': 'p', 'brief': 'b', 'target': 't'}   # 'target' (B24): the writer receives the diagnosed weaknesses
AUDIT_RUNS = 2              # independent audit requests per derivation; ACCEPTED means every one accepts
# The audit may vouch for a question the checker does not solve only when, on the calibration set (the anchored
# derivations of real parents = right, their coded mistakes = wrong), it accepts at least this share of the right
# and at most this share of the wrong derivations. Registered before the first audit run (BANK-PILOT B23).
AUDIT_RULE = {'right_accepted_min': 0.80, 'wrong_accepted_max': 0.10,
              'right_min': 30, 'wrong_min': 30}   # and the calibration must be COMPLETE and at least this large
DIAGNOSIS_REPLY_CHARS = 2500   # of a solver reply shown to the diagnostician
TRACE_ATTEMPTS = 2          # one request and one repair request that names the fixed check that failed
CHECK_RUNS = 2              # independent solving runs of the checker per parent and per new question
ROLE_MAX_TOKENS = 32_768    # completion bound of the bank's role requests (thinking shares it; 8 of 74
                            # derivation requests ran out of 16,384 on 2026-11-13)
SIDES = ('shown', 'judge')  # shown to writers / kept for judging; a parent's made items all take the parent's side
