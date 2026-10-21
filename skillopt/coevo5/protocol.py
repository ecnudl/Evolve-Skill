"""Registered constants: version 1 (docs/handoff/coevo5-registration-v6-20261017.md, run 10/18-10/19 from the frozen
snapshot /data/coevo5-20261017-source-e) as changed by version 2 (docs/handoff/coevo5-registration-v2-delta-20261019.md,
every v2 change is marked "v2"; frozen in /data/coevo5-20261019-v2-source) and by version 3
(docs/handoff/coevo5-registration-v3-delta-20261019.md, written before any v3 run; marked "v3"). Changing any value after
launch is a new protocol version."""
from __future__ import annotations

from fractions import Fraction

VERSION = "fivebench-coevolution-v3"

# §1: the fixed order of the sequential chain.
ORDER = ("searchqa", "officeqa", "livemath", "spreadsheetbench", "alfworld")
QA_FORMATS = ("searchqa", "officeqa", "livemath")

# §1.1: the similarity map (confirmed by the owner, 10/17). Forward panels exist in two question-answering styles only
# (§8): SearchQA is never a forward target, and no SpreadsheetBench panel can be generated.
SIMILAR_PAIRS = (("searchqa", "officeqa"), ("officeqa", "livemath"), ("officeqa", "spreadsheetbench"))
SIMILAR = {b: tuple(o for o in ORDER if (b, o) in SIMILAR_PAIRS or (o, b) in SIMILAR_PAIRS) for b in ORDER}
FORWARD_STYLES = ("officeqa", "livemath")


def similar_targets(bench):
    """(backward, forward): the similar targets a rule learned at ``bench``'s stage can be checked on -- similar benches
    already learned (their regression panels) and similar benches not yet learned that have a generated style."""
    k = ORDER.index(bench)
    return (tuple(b for b in SIMILAR[bench] if ORDER.index(b) < k),
            tuple(b for b in SIMILAR[bench] if ORDER.index(b) > k and b in FORWARD_STYLES))
SOLVERS = ("glm-5.3", "deepseek-v4-flash")
ROLE_MODEL = "glm-5.3"  # every method role (roles.py): identical in every chain
ROLE_MAX_TOKENS = 16384  # §13.5: reasoning low, temperature 0
ROLE_READ_TIMEOUT_SECONDS = 900
ANALYST_ATTEMPTS = 2  # §4: no valid proposal JSON twice -> no rules this step (a method-failure event)

# §3: the Skill layout. The applicability lines are fixed text, never learned.
TITLES = {"searchqa": "SearchQA", "officeqa": "OfficeQA", "livemath": "LiveMath",
          "spreadsheetbench": "SpreadsheetBench", "alfworld": "ALFWorld"}
APPLIES_WHEN = {
    "searchqa": "Applies when: the task gives a clue-style question with retrieved web search snippets and asks for a "
                "short answer.",
    "officeqa": "Applies when: the task gives document text or data tables, such as U.S. Treasury Bulletin pages, and "
                "asks a question answered from them.",
    "livemath": "Applies when: the task is a mathematics question with lettered answer options.",
    "spreadsheetbench": "Applies when: the task asks for a Python program that modifies a spreadsheet workbook.",
    "alfworld": "Applies when: the task is a text household environment where you choose one admissible action per "
                "step.",
}
MAX_SKILL_BYTES = 20000  # bounds the cost of ALFWorld, which resends the Skill on every action
MAX_RULE_CHARS = 600
MAX_RULES = 5
MAX_SIMILAR_RULES = 2  # proposed for similar placement, at a stage with checkable similar targets
MAX_RESEARCH_QUESTIONS = 2  # per rule (step 5b)
REWRITE_CALLS = 1  # per researched rule (step 5b): never retried; an invalid rewrite keeps the original text

# §2: the seed of every draw (training execution, regression panels): hash orders of task ids (data.ranked).
DATA_SEED = 20261017

# §2: (items, runs per item) of a stage's training execution; the gate's focal panel is the same items with GATE_RUNS.
# SpreadsheetBench's 120 is nominal: its panels hold every reference-qualified pool item (§2.1), fixed in the manifest.
TRAIN_ROLLOUT = {"searchqa": (200, 2), "officeqa": (74, 2), "livemath": (100, 2), "spreadsheetbench": (120, 1),
                 "alfworld": (57, 2)}
GATE_RUNS = {"searchqa": 2, "officeqa": 2, "livemath": 2, "spreadsheetbench": 1, "alfworld": 1}
POOLS = {"searchqa": (400, 200), "officeqa": (50, 24), "livemath": (155, 128), "spreadsheetbench": (80, 40),
         "alfworld": (39, 18)}  # (historical train, historical val)
TEST_SIZES = {"searchqa": 400, "officeqa": 172, "livemath": 125, "spreadsheetbench": 279, "alfworld": 134}
REGRESSION_ITEMS = 60  # x 1 run, for every bench before the last (SpreadsheetBench: all qualified items if fewer)
REGRESSION_RUNS = 1
SHEET_MIN_QUALIFIED = 30  # fewer qualified SpreadsheetBench training items: no rule tests, no regression panel (§2.1)

# v2 §5.1: every arm of C1 (the rule, the parent, the four controls) runs this often on trigger items, in every round;
# the focal panel's other items keep GATE_RUNS.
TRIGGER_RUNS = {"searchqa": 4, "officeqa": 4, "livemath": 4, "spreadsheetbench": 2, "alfworld": 2}
# v2 §5.2: the parent runs a regression item twice, a rule arm (and the composite arm) once.
PARENT_REGRESSION_RUNS = 2
# §5.5: tolerances in items, from the registered rule ``calibrate`` in docs/handoff/coevo5_power_sim.py (focal panel
# minus 8 trigger items). v2 §5.2: the regression panel's (60 items, parent x2, rule x1) from ``calibrate_split`` in
# docs/handoff/coevo5_power_sim_v2.py. SpreadsheetBench's values are recomputed for its qualified sizes.
TOLERANCE_FOCAL = {"searchqa": 7, "officeqa": 6, "livemath": 9, "spreadsheetbench": 9, "alfworld": 5}
TOLERANCE_REGRESSION = {"searchqa": 5, "officeqa": 6, "livemath": 8, "spreadsheetbench": 6}
MAX_EXTRA_VIOLATIONS = 2
MIN_TRIGGER = 4
MIN_GAIN = 1
MIN_SIMILAR_DELTA = 0  # C4': no worse than the parent on every similar target
MAX_UNKNOWN_SHARE = Fraction(1, 10)  # per arm; parent/control infrastructure share pauses the chain (§5.4, §13.4)

# §5.4: remedies that never replace a delivered answer.
MAX_RESENDS = 2  # identical request after a call that delivered nothing, each after the cooldown
RESEND_COOLDOWN_SECONDS = 300
MAX_REEXECUTIONS = 2  # the same SpreadsheetBench program
MAX_RESCORES = 2  # the same SpreadsheetBench workbooks, in a fresh scoring directory
MAX_EPISODE_RESTARTS = 2  # an ALFWorld environment that failed before any model call
READ_TIMEOUT_SECONDS = 2400  # a 65,536-token reply took 10-19 minutes historically
MAX_WORKBOOK_BYTES = 8 * 1024 * 1024  # the frozen backend's limit on a generated workbook
MAX_WORKBOOK_EXPANDED_BYTES = 128 * 1024 * 1024  # and on its unpacked size

# §8: forward panels of a similar candidate, one per forward target, generated from researched public material.
FORWARD_PER_CALL = 3  # items requested per generation call
FORWARD_ATTEMPTS = 5  # rounds per (rule, forward target): a material request, a generation call, a check per item
FORWARD_PANEL = (8, 12)  # the first 12 valid distinct items are kept; fewer than 8: own placement only
FORWARD_RUNS = 2

# §5.2: directive "irrelevant text" controls -- situations that occur in none of the five benchmarks, written to the
# length of a typical rule. Each round places its four texts at every placement it tests (the bench's own section;
# the similar sections: the bench's own and those of every checkable similar target of the stage).
PLACEBOS_SCREEN = (
    "When a task asks you to compose a haiku, keep the 5-7-5 syllable pattern across its three lines. Avoid end "
    "rhymes and do not give the poem a title unless one is explicitly requested.",
    "If you are asked to give a color in hexadecimal notation, write the six hex digits in uppercase and prefix them "
    "with a single # sign, for example #1A2B3C; never use the three-digit shorthand.",
    "When a recipe is requested, list every ingredient with its quantity before describing any cooking step, and "
    "group the steps under short headings for preparation, cooking and serving.",
    "When translating a Latin inscription, keep personal and place names in their original Latin form and put any "
    "modern equivalent in parentheses after the first mention only.",
)
PLACEBOS_CONFIRM = (
    "If a task asks for a limerick, use an AABBA rhyme scheme, keep the third and fourth lines shorter than the "
    "others, and end on the punch line rather than an explanation.",
    "When asked to state a temperature in kelvin, write the number followed by a space and a capital K, never with a "
    "degree sign, for example 300 K rather than 300 degrees K.",
    "If you are asked to record a chess move, use standard algebraic notation such as Nf3 or exd5, mark checks with "
    "+ and checkmate with #, and omit move commentary.",
    "When asked to describe a knitting pattern, state the needle size and yarn weight before the stitch sequence, "
    "and give each row on its own line with its stitch count.",
)

# §5.5 C3: the fixed per-bench format each answer must keep; the rubric's evolving items never change it.
REQUIRED_FORMAT = {"searchqa": ("answer_tag_present",), "officeqa": ("answer_tag_present",),
                   "livemath": ("answer_single_letter",), "spreadsheetbench": ("code_present",), "alfworld": ()}

# §6: the examiner (not revised on ALFWorld, whose trajectories state the outcome).
EXAMINER_BENCHES = ORDER[:4]
RUBRIC_PANEL_PER_CLASS = 20
RUBRIC_MIN_MINORITY = 8
RUBRIC_MIN_BA_GAIN = Fraction(1, 20)
RUBRIC_MIN_NET = 2
RUBRIC_MAX_DISAGREEMENTS = 20
RUBRIC_MAX_EDITS = 3
# v2 §6: a rubric item's text and basis may have up to 450 characters (the reviser's prompt still asks for 300); a
# revision's edits are validated one by one.
RUBRIC_ITEM_CHARS = 450

# v2 §3: the frozen failure types the diagnosis chooses first (the stage's rubric text items only when none fits, then
# "other"): decidable from the task, the final answer and the reference, since the answers show little or no reasoning.
# Final lists from the audit of the v1 run's training failures (taxonomy audit, delta appendix A); LiveMath's D1 and D2
# are assigned by table (``TABLE_CODES``) from the reference and the chosen letter, never by the model.
TAXONOMY = {
    "searchqa": (
        ("D1", "Extra words: names the right thing but adds words the reference lacks: a fuller name, first or middle "
               "name, initials, a title, a category or type word, a place name, or an article."),
        ("D2", "Other form: names the right thing in another single form: part of the expected name or phrase missing, "
               "singular vs plural or other inflection, a synonym, nickname, older or newer name, or different "
               "spelling or accents."),
        ("D3", "Not one answer: the answer field is not one short answer: it lists alternatives, adds a parenthetical "
               "alias or explanation, or is a sentence, even when the correct answer appears inside it."),
        ("D4", "Wrong candidate: gives a different entity of the right kind: another candidate that fits only part of "
               "the clue (often one named in the snippets) or a guess, not the one that all parts of the clue "
               "describe."),
        ("D5", "Wrong kind: gives the wrong kind of answer or answers a different element of the clue than the one "
               "asked (e.g. a place for a person, a group for its members), often when the clue only names a topic."),
    ),
    "officeqa": (
        ("D1", "Wrong data: used a value from the wrong row, column, table or page, or from the wrong period (date, "
               "month, quarter, fiscal vs calendar year), although the needed value is in the document."),
        ("D2", "Wrong method: computed a different quantity than asked: wrong formula or statistic (e.g. sample vs "
               "population, compound vs continuous rate, percent change vs percent difference, level vs change, "
               "percentile rule) or an intermediate value."),
        ("D3", "Calculation slip: right data and method, but the arithmetic is off: an addition or division slip, "
               "imprecise logarithms, roots or powers, or rounding of intermediate values; often only the last digits "
               "differ."),
        ("D4", "Answer form: the value is right, or right before the final rounding, but its written form fails: "
               "percent sign, sign, decimal places or rounding, unit or scale (thousands vs millions), extra text, or "
               "list order and brackets."),
        ("D5", "Not in the document: the values needed are not in the provided pages (e.g. a chart without its "
               "numbers, or an outside fact such as a price index or a publication date), so the answer was a guess or "
               "the solver said data are missing."),
    ),
    "livemath": (
        ("D1", "Missed stronger result: the correct choice is the option saying that a stronger result than the listed "
               "ones can be proven, but the answer picked one of the listed statements."),
        ("D2", "Wrongly chose stronger result: the answer picked the option saying that a stronger result than the "
               "listed ones can be proven, but one of the listed statements is the correct strongest one."),
        ("D3", "Weaker option: the picked statement asserts less than the correct one: extra hypotheses, a weaker or "
               "partial conclusion, one direction of an equivalence, or a claim that the result holds only in a "
               "narrower case."),
        ("D4", "Stronger option: the picked statement claims more than the correct one: drops a hypothesis or an "
               "'almost every' qualifier, widens the range or set of cases, tightens a bound, or fixes an explicit "
               "constant."),
        ("D5", "Different claim: the picked statement is neither weaker nor stronger than the correct one: a changed "
               "constant, exponent, index, sign or condition that makes it incomparable, or a different statement "
               "altogether."),
    ),
    "spreadsheetbench": (
        ("D1", "Program error: no usable workbook: the reply gave a formula, comment or prose instead of a runnable "
               "Python program, or the program crashed (unexpected cell types, unavailable library feature) or wrote "
               "no output.xlsx."),
        ("D2", "Wrong target: results written to the wrong sheet or cells: shifted by a row or column, extra headers or "
               "labels inside the answer range, or part of the answer range left empty."),
        ("D3", "Hardcoded or copied: wrote fixed values, guessed constants, or one row's formula unchanged (e.g. a "
               "fixed row reference) where each row needs its own value or formula derived from the data."),
        ("D4", "Wrong logic: the program or formula computes a different rule than the instruction asks: a misread "
               "condition, wrong input cells or range, wrong aggregation, or an invented rule for cases the "
               "instruction covers."),
        ("D5", "Formula semantics: a spreadsheet function or formula behaves differently than assumed after "
               "recalculation: array formulas without array entry, wildcards, exact vs approximate lookup, error "
               "handling, text vs number or date types."),
        ("D6", "Key alignment: rows are matched wrongly when combining data: wrong key column or header row, keys not "
               "normalized (case, spaces, number vs text), or missing or duplicated keys."),
    ),
    "alfworld": (
        ("D1", "Wrong object: used a different object or receptacle than the goal names (e.g. a similar item of "
               "another type), or put the object in the wrong place."),
        ("D2", "Missing step: skipped a required change of the object before placing it (clean, heat, cool, slice, or "
               "turning on a lamp to look at it), or tried it with the wrong appliance."),
        ("D3", "Search loop: kept revisiting the same few places or re-handling the same object instead of checking "
               "receptacles not yet opened, so the needed object (or the second one) was found late or never."),
        ("D4", "Invalid actions: repeated commands the environment rejects ('Nothing happens'): wrong command wording, "
               "taking a second object while holding one, or going to receptacles that do not exist."),
    ),
}
# LiveMath's meta-option (in 129 of the 283 training items): its two codes follow from the letters alone
TABLE_CODES = {"livemath": ("D1", "D2")}
STRONGER_OPTION = "One of the remaining options is correct, but a stronger result can be proven."
DIAGNOSE_CONTEXT_CHARS = {"officeqa": 30000}  # v2 §3: the OfficeQA diagnosis sees the long Treasury pages (v1: 6000)

# v2 §4: the analyst's evidence (shown proposal-half failures whose code the rule targets), its contrast examples
# (proposal-half answers that passed) and the fields that state what the parent already covers and what the rule adds.
EVIDENCE = (2, 8)
CONTRAST_EXAMPLES = 4
MAX_COVERED_CHARS = 200
MAX_ADDS_CHARS = 300
MAX_TRANSFER_REASON_CHARS = 300
MAX_RATIONALE_CHARS = 500
MAX_QUESTION_CHARS = 300
# v3 §6: the analyst's shown failures (40 elsewhere) and its wider OfficeQA pages (the diagnosis' 30,000 above; the
# contrast examples keep the common 6,000); SpreadsheetBench views show the solver's workbook preview (clipped) and up to
# 12 answer-range cells with their expected, written and recalculated values.
ANALYST_EXAMPLES = {"officeqa": 16, "spreadsheetbench": 20}
ANALYST_CONTEXT_CHARS = {"officeqa": 20000}
SHEET_PREVIEW_CHARS = 4000
SHEET_CELLS = 12
SHEET_VALUE_CHARS = 100
# v3 §6: the most UTF-8 bytes of the message (the payload as ``roles.ask`` sends it) of the analyst, the self-test
# revision and the rubric reviser (v1's largest valid analyst message: 209,041 bytes, 85,789 prompt tokens); shown
# examples beyond it are left out from the end of their seeded order, and the payload says how many.
ROLE_INPUT_BYTES = 220000

# v3 §7: the proposal-half self-test of every supported rule on its own evidence items (the parent on their union), one
# batch revision of the rules that fail it, and a second round for the revised texts (against the parent's first round).
SELFTEST_RUNS = {"searchqa": 2, "officeqa": 2, "livemath": 2, "spreadsheetbench": 1, "alfworld": 1}
SELFTEST_SHOWN = 3  # evidence items shown per failing rule in the revision call (seeded order)
SELFTEST_ATTEMPTS = 2  # the revision call; a second only when the first reply is invalid

# §7: research.
RESEARCH_MAX_ROUNDS = 3
RESEARCH_MAX_QUERIES = 3  # per round
RESEARCH_MAX_PAGES = 3  # per question
RESEARCH_MAX_CALLS = 8  # model calls per research request, malformed replies included; then "no qualified finding"

# §9: leakage checks.
LEAK_NGRAM = 8
LEAK_TEMPLATE_SHARE = Fraction(1, 20)
LEAK_MIN_SINGLE_WORD = 5
LEAK_MIN_SIGNIFICANT_DIGITS = 3
LEAK_MIN_OPTION_CHARS = 4
# v2 §7: a single-word answer collision goes to the adjudicator with at most this many colliding training items, each
# question clipped to this many characters.
LEAK_WORD_EVIDENCE_ITEMS = 3
LEAK_WORD_EVIDENCE_CHARS = 600
# v2 §8: an archive page is a search result when it holds at least this share of the query's distinct words.
ARCHIVE_MIN_WORD_SHARE = Fraction(1, 2)

# §12: readings.
NI_MARGIN = 3  # percentage points, macro average of the five benches; a practical margin
BOOTSTRAP_RESAMPLES = 10000
BOOTSTRAP_SEED = 20261017

# §13: GLM-5.3 token caps, enforced by reservation before every dispatch.
CLIENT_ATTEMPTS = 4  # the solver client's own attempts per call (1 + 3 retries)
RESERVATION_OVERHEAD = 512  # tokens per request on top of its UTF-8 bytes
M = 1_000_000
# §10 (v1): E-glm, SkillOpt-glm and GEPA-glm shared one stage-0 evaluation of the empty Skill. v2 §1-§2: E starts
# from the scaffold and NoSkill-glm evaluates the empty Skill on its own; nothing is shared.
SHARED_STAGE0 = {}
# "N": the NoSkill-glm reference (v2 §1); a baseline (run by no v2 chain) would evaluate its empty stage 0 alone, as N
STAGE0_EVALUATION_CAP = {"E": 20 * M, "I": 35 * M, "N": 20 * M, "baseline": 20 * M}
LEARNING_CAP = {
    "E": {"searchqa": 60 * M, "officeqa": 55 * M, "livemath": 65 * M, "spreadsheetbench": 45 * M, "alfworld": 135 * M},
    "I": {"searchqa": 90 * M, "officeqa": 70 * M, "livemath": 85 * M, "spreadsheetbench": 65 * M, "alfworld": 225 * M},
    "ds": {"searchqa": 10 * M, "officeqa": 6 * M, "livemath": 6 * M, "spreadsheetbench": 4 * M, "alfworld": 3 * M},
}  # "ds": the GLM-5.3 method roles of a deepseek chain; baselines: BASELINE_LEARNING_CAP per stage
# A baseline's evaluation step: the high-cost scenario of §13.1 with its own Skill limit (32,000 bytes, about 8,000
# tokens: 45.5M, rounded up to 50M) -- the 20M first registered was E-glm's (a Skill of at most 20,000 bytes).
EVALUATION_CAP = {"E": 20 * M, "I": 35 * M, "baseline": 50 * M}
# The frozen learner's own hard rules (continual_learning/ledger.py, recovery.py, validator_pilot/api.py): it admits no
# call once 60M tokens are reported, holds at most 8 calls open, each of at most 3 attempts, admits at most 64 attempts
# without usage, refuses prompts over 240,000 bytes and never asks for more than 131,072 output tokens.
BASELINE_REPORTED_TOKENS = 60 * M
BASELINE_INFLIGHT, BASELINE_CLIENT_ATTEMPTS, BASELINE_UNKNOWN_COST_ATTEMPTS = 8, 3, 64
BASELINE_PROMPT_BYTES, BASELINE_RECOVERY_TOKENS = 240000, 131072
BASELINE_LEARNING_CAP = 93 * M  # the worst case above (92.7M), reserved whole before every baseline learning stage
# §11: the frozen learners' own budget per stage (learning v9 as study G ran it: scripts/run_fivebench_g_stage.BUDGET_V9),
# their Skill interface (recovery.POLICY_V9) and the seed of stage k (seed + k, as study F).
BASELINE_BUDGET = {"max_metric_calls": 8000, "max_reflection_calls": 128, "max_api_calls": 12000,
                   "max_reported_tokens": BASELINE_REPORTED_TOKENS, "max_iterations": 3, "minibatch_size": 8,
                   "solver_max_tokens": 65536, "reflection_max_tokens": 8192}
BASELINE_SKILL_BYTES = 32000
# §11: the baselines' learning model and frozen service are study F's (its sealed protocol on the development machine,
# /root/continual-fivebench-20261003-f-study/protocol.json, fivebench-sequential-attempts-v4).
BASELINE_PROTOCOL = "1a6c3abbc43e6296fd9f0f46f070eb7940c4c85133c8f57bf75d6a7e650b6e91"
CHAIN_CAP = {"E-glm": 480 * M, "I-glm": 745 * M, "SkillOpt-glm": 735 * M, "GEPA-glm": 735 * M, "E-ds": 29 * M,
             "I-ds": 29 * M, "NoSkill-glm": 20 * M, "NoSkill-ds": 1 * M}  # v2 runs no baseline chain (§1); their
# caps stay defined, with their own stage 0 since nothing is shared (v1: 715M each, its stage 0 charged to E-glm).
# v3 §1: NoSkill-ds (deepseek's empty-Skill stage 0) makes no GLM-5.3 call; its cap is a guard only.
# v3 §9: deepseek-v4-flash's tokens (the solver of the deepseek chains, through the PJLAB token endpoint) are
# reserved and settled like GLM-5.3's, in scopes of their own that the GLM-5.3 ceiling does not count: per chain and in
# all. A chain that reaches its allowance pauses (§13.4).
DEEPSEEK_CEILING = 430 * M
DEEPSEEK_CHAIN_CAP = {"I-ds": 200 * M, "E-ds": 200 * M, "NoSkill-ds": 30 * M}
# v2 §10: the owner's coevo5 total of 1.44 billion less v1's spend (about 0.174 billion with its pre-launch texts and
# smoke) and v1's pending E-ds and I-ds role caps (0.058 billion), rounded down: 1.2 billion. v3 §10: less v2's
# pre-launch ledger at its cap (``prelaunch.PRELAUNCH_CAP``, 0.03 billion; its smoke was still running when v3 froze).
OVERALL_CEILING = 1170 * M

# §13.5 and §5.4: the solvers' calls (scripts/weak_solver_probe.py Client: 1 + 3 attempts on transport errors and HTTP
# 429/5xx), and the concurrency every coevo5 process shares (file-lock slots). Native work has its own bounded slots
# (the development machine: 7 CPUs, 15 GB).
SOLVER_MAX_TOKENS = {"glm-5.3": 65536, "deepseek-v4-flash": 32768}
# v3 §9: the deepseek solver's route (scripts/weak_solver_probe.py ROUTES: thinking disabled on every request), bound
# with its credential file's path in the clients of a smoke and a launch manifest
DEEPSEEK_ROUTE = "pjlab_token"
SLOTS = {"glm-5.3": 10, "deepseek-v4-flash": 12, "spreadsheet-native": 3, "alfworld-episode": 6}

# The frozen backends' runtime of every benchmark (the development machine). SpreadsheetBench: the frozen v7 scorer with
# the 23-control engine qualification (§2.1), explicit Python fences (row 6) and the public formula preview, executing
# no further case after an unconfirmed cleanup (row 3). ALFWorld: the history's settings plus the public transition
# log (it does not change the solver's prompt).
# v3 §2: the answer-format contract before the Skill; ALFWorld's already is. After the format check (the owner,
# 2026-10-19 14:3x): v2, whose SpreadsheetBench contract also states the deliverable (a program writing output.xlsx, not
# a formula alone) and the fence on its own line -- for every Skill, the empty one included; the other three
# benchmarks' prompts are v1's, an empty Skill's unchanged there.
PROMPT_LAYOUT = "contract-first-v2"
RUNTIME = {
    "searchqa": {"prompt_layout": PROMPT_LAYOUT}, "officeqa": {"prompt_layout": PROMPT_LAYOUT},
    "livemath": {"prompt_layout": PROMPT_LAYOUT},
    "spreadsheetbench": {
        "prompt_layout": PROMPT_LAYOUT, "image": "sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd", "timeout_seconds": 300,
        "memory_mb": 4096, "cpus": 1, "code_extraction_version": "explicit-python-fences-v1",
        "spreadsheet_preview_version": "public-formula-preview-v1", "_stop_on_cleanup_failure": True,
        "spreadsheet_scorer": "qualified_lo_recalc_v7_v1",
        "recalculation": {"image": "sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790",
                          "timeout_seconds": 120,
                          "qualification_path": "/root/continual-fivebench-20261003-f-q23/qualification.json",
                          "qualification_sha256": "f5bc90dfc435cf0ddf9cfa8179237568edb605673dd7f8e08a2658815da6f54c",
                          "qualification_hash": "cc4ab804d497c09ac4416ea814d3200000a1e7d4a91bc02238191f71c729b9bf"}},
    "alfworld": {"alfworld_data": "/root/continual-alf-prep-20260928/data", "alfworld_split": "train", "max_steps": 50,
                 "timeout_seconds": 60, "seed": 42, "alfworld_trace_version": "alfworld-public-transitions-v1"},
}
