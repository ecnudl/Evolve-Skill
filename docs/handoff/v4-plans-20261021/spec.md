# Protocol v4 change specification (fivebench-coevolution-v4), written 2026-10-20 by the main session

Repository: /Users/dulin/Documents/Paper/SkillOpt (branch research/active-evidence-skill-evolution). Package:
`skillopt/coevo5/` (~10k lines). Tests: `tests/test_coevo5_*.py` + `tests/coevo5_fakes.py`; baseline 2026-10-20:
`python3 -m pytest tests/test_coevo5_*.py -q -x -p no:cacheprovider` -> 704 passed, 1 skipped in 39 s. The v3 code is
frozen remotely (snapshot /data/coevo5-20261019-v3-source-f, identical to the local tree today), so editing the local
tree never touches a completed run. Registration documents (READ, never edit): docs/handoff/coevo5-registration-20261016.md
(the base protocol, § numbers cited in docstrings), coevo5-registration-v2-delta-20261019.md,
coevo5-registration-v3-delta-20261019.md. The main session writes the v4 delta document and the living docs itself;
you do not touch docs/.

Owner's instruction (2026-10-20, verbatim intent): "fix the bugs found and make the prompt improvements directly; have
Codex review the code". Everything below is in scope; items marked DECIDED carry a policy decision the owner can
reverse later (keep each one a small, named switch or a clearly marked constant so it can be flipped).

## 0. Ground rules for every change
- Bump `VERSION` in `skillopt/coevo5/protocol.py` to "fivebench-coevolution-v4". Every sealed record carries it, so
  v4 output must go to new directories; the manifest/prelaunch/smoke code paths must keep working with the new string
  (find every place that pins or compares the version string, incl. tests and `coevo5_fakes.py`).
- Preserve the registered semantics of everything NOT listed here. If a change here forces a change elsewhere, name it.
- Keep the code's style: dense module/function docstrings that cite the registration ("v3 §9", "§13.4"); for v4
  changes cite "v4 §<item id below>" (e.g. "v4 B1"). No new third-party dependencies.
- Tests: every item gets at least one new or changed unit test using the existing fakes; the whole suite must pass.
- Never read test pools; never print credentials; no network calls in tests.
- Role calls cost GLM tokens: where an item multiplies calls (votes, per-code analyst calls, applicability judge),
  compute the new per-step GLM volume and raise the registered GLM step/chain caps in `protocol.py`/`prelaunch.py`
  proportionally (document the arithmetic in the docstring).

## 1. Bugs (B1-B17)

B1 (analyst.py, step.py `_admissible`/prepare) codes/evidence double declaration. v3: the analyst declares `codes`
   and `evidence`; any inconsistency voids the rule, no re-ask (7 of 49 v3 proposals died so). v4: the reply row has
   NO `codes` field (ignore it if present); `codes` := sorted set of the diagnosis codes of the cited evidence items
   (per-item codes, see B8). A row citing an item that is not a proposal-half failure is re-asked once with the
   validator message (B5); if still invalid, only that ROW is voided (recorded with reason `evidence_invalid`), never
   the whole reply.

B2 (analyst.py `_transfer`, prompt; step.py) transfer/placement double authority. v4: delete the `transfer` slot and
   all its handling. `placement` in {"local", "similar"} (default "local" when absent; any other value => row re-ask
   then void with reason `placement_invalid`). More `similar` rows than the registered allowance per step => the
   extras are demoted to local and recorded (`demoted_similar`), the reply is never voided. The analyst prompt states
   what a `similar` rule must pass (a forward panel of generated similar-target items; C4' no-worse on similar
   targets) and that at most N similar rules per step are allowed (N = the existing constant).

B3 (leakage.py, step.py prepare) mechanical leakage drops record nothing. v4: every mechanical decision is recorded in
   the prepare record: `{"rule": id, "hit": <kind>, "snippet": <the matched text, <= 80 chars>, "item": <task id or
   null>, "decision": "adjudicate"|"dropped"}`; `dropped_pre_dispatch` entries carry this.

B4 (leakage.py + the adjudicator) illustrative hits are dropped before adjudication. v4 (DECIDED): ALL hit kinds
   (answer_text, answer_word, number, quoted phrase, option_text) go to the adjudicator with the hit context; the
   adjudicator labels each hit one of {"leak", "illustrative", "task_structure"} with a written reason first (B6/P4
   format, 3 votes); "leak" => the rule is dropped (recorded, B3); otherwise kept. The ONLY remaining mechanical drop
   is a verbatim reference answer of >= 12 characters that is not a dictionary word (keep whatever stricter rule exists
   today for that case; document it). The analyst prompt states the rules (P2/B5): no digits except years, no quoted
   passages or option text, examples must be invented, not copied from a task.

B5 (calls.py/roles.py role-call wrapper, analyst.py, examiner.py, forward.py validators) re-ask without feedback. v4:
   a reply that fails validation is re-asked ONCE with the validator's message appended ("Your previous reply failed
   validation: <message>. Reply with the corrected JSON only."), then the row (or the reply if the whole structure is
   unparsable) is voided with the reason. Extra keys are tolerated everywhere. Archival-only string fields
   (rationales, notes) over their limit are truncated for the archive, never a reason to void. `Rule()` constraints
   that the model is not told (leading/trailing whitespace, a '#'-leading line, length) : strip whitespace server-side;
   the remaining constraints appear in the prompt and in the re-ask message.

B6 (the leakage adjudicator; find it: leakage.py / research.py) the adjudicator lacks the solver's input spec. v4: its
   input includes the benchmark's public task card (what the solver sees) and the rule's `when`/`do` (P1); its output
   is reason-then-label JSON (`{"reason": ..., "label": ...}`), 3 votes (P4), tie => "leak".

B7 (scoring.py and the SearchQA/OfficeQA format checks in skillopt/continual_eval/backends.py or wherever `preflight`
   / C3 "format violation" is computed) format check vs scorer disagree. v4: the format-violation predicate used by
   C3 and the task-card wording must agree with the scorer: a reply counts as a format violation iff the scorer's own
   extraction fails (so a tagless last-line answer the scorer accepts is NOT a violation), and an EMPTY
   `<answer></answer>` IS a violation (today it passes the format check but OfficeQA scores it invalid). Keep the task
   card's instruction to use the tags. Add tests for both cases per benchmark.

B8 (examiner.py, step.py train/prepare, analyst payload) diagnosis per RUN, not per ITEM. v4: each failed run is still
   diagnosed, but the ITEM's code is the majority over its failed runs (tie => the code of the lowest run index); all
   downstream uses (analyst examples, evidence validation, codes in B1, trigger/precision in P1) are per item; the
   analyst sees one example per item (with its failed runs' outputs summarised, never the same item twice).

B9 (analyst.py, protocol ANALYST_EXAMPLES) example cap starves codes; the analyst is not told the testability
   constraint. v4 = P5 (per-code calls) + numbers: each per-code call shows ALL proposal-half failed items of that code
   up to the cap (cap applies per code now) and the counts: proposal-half failures with the code, check-half failures
   with the code, check-half items in total, and MIN_TRIGGER. A code with 0 check-half failures is not asked about
   (recorded as `untestable_code`).

B10 (step.py `shared_unanswered`, gate.py C4') forward items exempt from the shared-unanswered exclusion. v4: forward
   (generated) items are included in the exclusion mask exactly like pool items (an item no arm answered leaves every
   criterion of the round).

B11 (qualify.py; training-side qualification only) an item whose read view is unverifiable
   (`general_formula_read_view_unverified`) is unjudgeable in every arm and counts as rule=fail/parent=pass. v4: such
   items are excluded at the TRAINING-side qualification (recorded with the reason); the test-side qualification is
   untouched.

B12 (leakage.py) option-text hit threshold. v4: an option text counts as a hit only if it has >= 2 words or >= 10
   characters (short options like "none", "true", "0" never trigger).

B13 = P7 (skill.py render; texts/cards if they repeat the sentence) the solver's framing sentence "Frozen skill guidance
   (use only where applicable)" is jargon. v4 (shared-setup change; all chains redo step 0 in v4 anyway): "Skill
   guidance for this task. It has one section per task family, each headed by an 'Applies when' line: follow only the
   section(s) whose 'Applies when' matches the current task and ignore the others."

B14 (step.py merge) the merge record hashes `render()` text while every other record hashes `digest()` of the Skill's
   JSON. v4: one convention everywhere (the JSON digest); the merge record may ALSO carry the rendered text's sha256
   under a distinct key.

B15 (protocol.py, gate.py) `RESEARCH_MAX_ROUNDS = 3` never binds (the loop does at most 2): set the constant to the
   real maximum and fix the loop or the constant so they agree; the tolerance-calibration comment is stale (C2 panel
   now excludes evidence items): rewrite it; `gate.round_complete` is dead code (production uses `step.guard`):
   delete it and its tests, or make `step.guard` call it -- one pause definition only.

B16 (step.py regression panel construction) an emptied regression panel pauses as "configuration". v4: it pauses with
   the kind used for incomplete infrastructure (check `cells.STOP_KINDS`/Pause kinds and pick the registered one for
   "the data needed by this unit is not available"), with a reason naming the benchmark.

B17 (calls.py role endpoint) a role reply truncated at ROLE_MAX_TOKENS is voided without a resend. v4: resend once with
   "Your previous reply was cut off at the token limit; answer more concisely." appended; a second truncation voids.

## 2. Prompt and interface improvements (P1-P7)

P1 Conditional rule template and condition-derived triggers (analyst.py, skill.py Rule, step.py prepare/_round,
   gate.py, protocol.py). DECIDED design:
   - A proposal row has `when` (an observable condition on the task INPUT the solver sees, <= 200 chars), `do` (a
     bounded action, <= 300 chars), optional `otherwise` (<= 100 chars). The rule text is RENDERED by the code:
     "When <when>: <do>." + (" Otherwise: <otherwise>." if given); it must satisfy the existing Rule limits (<= 600
     chars). The row no longer carries free `text` (ignore it if present). The `when`/`do`/`otherwise` are stored in
     the rule record.
   - Trigger derivation: an APPLICABILITY JUDGE (GLM role, new) is asked for EVERY check-half item (passed and failed)
     whether the `when` condition holds for that item's public input (the task card + the item's public text, rendered
     exactly as the examiner sees it, truncated to the existing role input limit); reason-then-label JSON, 3 votes
     (P4), tie => not applicable. trigger := the items judged applicable. MIN_TRIGGER (4) applies to this set;
     fewer => `insufficient_support` with the counts recorded. The C2 "rest" panel := check-half items judged not
     applicable, minus evidence items (keep whatever other exclusions exist today).
   - Record per rule: `when_matched` (count), `when_precision` (applicable items that are check-half failures with
     one of the rule's codes / applicable items) and `when_recall` (those / all check-half failures with the codes);
     informational only in v4 (no gating on them).
   - Gate criteria C1-C4' are otherwise unchanged (same runs, same thresholds, same controls).
   - Cost: judge calls = (#rules) x (#check-half items) x 3 votes per step; the prompt is short (card + item + when);
     compute and raise the GLM caps (see §0).

P2 One worked example per role (analyst, examiner, adjudicator, applicability judge, forward checker): a valid JSON
   reply with clearly fictitious content that matches no benchmark (e.g. about an imaginary "colour-sorting" task).
   The example is part of the fixed prompt (so it is hashed with the roles' prompt identity as today).

P3 = B5.

P4 Reason-then-label with votes (calls.py/roles.py generic helper; examiner diagnosis, adjudicator, applicability
   judge, forward checker). `ROLE_VOTES = 3`, `ROLE_VOTE_TEMPERATURE = 0.7` (the voting roles only; the analyst stays
   at temperature 0, single call). The helper: `vote(call, parse, label_of, tie)` runs ROLE_VOTES independent samples,
   parses each, takes the majority label, returns the label, the per-vote reasons and the tally; no majority => `tie`
   (examiner: "other"; adjudicator: "leak"; applicability: not applicable; forward checker: invalid). All votes are
   archived in the unit's artifacts. Budget: 3x the calls of those roles.

P5 Analyst decomposition (analyst.py, step.py `_research`): ONE call per diagnosis code cluster (codes ordered by
   proposal-half frequency; clusters with 0 check-half failures skipped, B9), each asking for <= 2 rules for that code;
   then the existing dedup/merge; the per-step cap of 5 proposals stays (keep the 5 with the most evidence; record the
   rest as `over_cap`). The reply schema is otherwise the same as today minus `codes`/`transfer`/`text` (B1, B2, P1).

P6 Balanced evidence in the analyst payload: for the code cluster, (a) every failed item (B8 per item) with the solver's
   wrong output(s) and the reference answer IF the leakage policy of the role allows it today (keep today's policy on
   what the analyst may see), (b) up to 8 PASSED proposal-half items drawn at random (seeded) with their outputs, (c)
   for any item with one passed and one failed run, both outputs side by side (contrast), (d) the counts of B9. No
   example appears twice.

P7 = B13.

## 3. Policy decisions folded in (DECIDED; each a named switch)
C1 LiveMath meta-option (taxonomy code D1) vs leakage policy. v4: the adjudicator's label set is {leak, illustrative,
   task_structure}; a rule that describes the TASK STRUCTURE (e.g. "when the options include a 'none of the above'
   style option and your computed value matches no option, choose that option") is `task_structure` and allowed; a
   rule that encodes an ANSWER DISTRIBUTION ("the last option is usually right", "prefer option B") is `leak`. State
   this in the adjudicator prompt, the analyst prompt and the leakage module docstring. Switch:
   `LEAKAGE_ALLOW_TASK_STRUCTURE = True` in protocol.py.
C4 Seeds vs learned rules: seeds (the public task cards) are never adjudicated; learned rules are held to the policy
   above. No code change; the main session documents it.
Out of scope for v4 (explicitly NOT to implement): fresh-batch version-level acceptance, changes to C1-C4' thresholds,
   the generated-task redesign (P5-P8 of the earlier proposal), any test-side change.

## 4. Where things live (line numbers of the v3 tree, 2026-10-20; verify before editing)
step.py: train 197-212; halves 216-225; `_research` 266-290 (`dropped_pre_dispatch` at 275); `_admissible` 305-317;
prepare 320-401 (evidence discard 359, trigger 386-391); selftest 405-609; `_round` 642-717 (C2 panel ~689); screen
720-734; confirm 741-757; composite 765-813; merge 816-827; learn 830-861. gate.py (241 lines, all criteria).
stats.py (74). analyst.py: prompt 59-85, payload 125-153, evidence_problem 164-178, `_transfer` 180-195, propose/dedup
after. examiner.py: prompts 77-102, taxonomy helpers. protocol.py: constants 55-100, TAXONOMY 142-222, 227-257, 331.
forward.py (443), research.py (702; material/rewrite; the adjudicator may live here or in leakage.py), leakage.py
(291), skill.py (136), units.py (157), manifest.py, budget.py, calls.py (role endpoint 140-175, resend 261-279),
cells.py, evaluation.py, chain.py, qualify.py (144), scoring.py (93), texts.py (183), roles.py (142), readout.py,
report.py, smoke.py, prelaunch.py (caps).

## 5. Deliverable of a DESIGN agent (per group)
For each item in your group: status (planned | needs_decision | not_applicable with reason), files and functions,
the EXACT current code you will replace (verbatim, so an implementer can locate it), the complete replacement code,
the complete new/updated tests, the registration-delta sentence(s) describing the semantic change, and open questions.
Also list cross-group dependencies (what another group's item must provide, by name). The plan must be executable by an
implementer who has not read this spec.
