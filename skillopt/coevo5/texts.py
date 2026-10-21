"""Pre-launch texts (registration §0, §1, §6): the five public task cards, the task-card instructions of chain I, and
the six initial rubrics.

The SearchQA, OfficeQA and LiveMath cards are the ones their existing instructions were written from
(``scripts/generate_zero_shot_skill.py``, verbatim); the SpreadsheetBench and ALFWorld cards are new and state, like
those, only the solver's fixed instructions (verbatim from the frozen backends), the input it receives and the public
metric -- never an example task, a model answer or a score. The two missing instructions are written once each by the
same prompt as the existing three and never selected among alternatives; the six initial rubrics are written once
each from the cards by one fixed prompt (the general rubric from all five cards) and checked by the program -- a reply
that is not a valid rubric twice stops the preparation (the owner decides). Everything is frozen into the manifest
before any run, with each generation's record.
"""
from __future__ import annotations

from skillopt.continual_eval.core import require

from .examiner import GENERAL, MAX_ITEMS, validate_rubric
from .protocol import ANALYST_ATTEMPTS, ORDER, TITLES
from .roles import Invalid, fields

# verbatim from scripts/generate_zero_shot_skill.py (a test checks the equality)
INSTRUCTION_SYSTEM = (
    "You write the guidance text (a \"Skill\") that will be appended to the system prompt of another language model "
    "which solves tasks of one kind. You are given ONLY the public description of the task kind. You have seen no "
    "example task, no model answer and no score, and you must not pretend otherwise: do not invent facts about the "
    "data.\n\nWrite the guidance a careful practitioner would write BEFORE any experience with the task: what the "
    "solver should pay attention to, how it should use the supplied material, and how it should form its final "
    "answer so that it satisfies the stated output contract and scoring. Keep it general for this task kind.\n\n"
    "Output only the guidance text in plain Markdown, at most 12 bullet points, with no preamble and no closing "
    "remark.")
CARDS = {
    "searchqa": (
        "Task kind: open-domain question answering over retrieved search snippets (the SearchQA benchmark).\n"
        "Input the solver receives: a JSON object with two fields -- \"question\" (a short clue-style question) and "
        "\"context\" (several retrieved web search snippets, possibly noisy or irrelevant).\n"
        "Fixed instructions the solver always receives: \"Solve the supplied task using only the supplied public "
        "information.\" and \"Return the concise final answer inside <answer>...</answer>.\"\n"
        "Scoring (public metric): the text inside the last <answer>...</answer> is compared with the reference "
        "answer(s) by exact match after SQuAD-style normalization (lower case, punctuation removed, the articles "
        "a/an/the removed, whitespace collapsed). Anything else in the reply is ignored."),
    "officeqa": (
        "Task kind: questions about U.S. Treasury Bulletin documents (the OfficeQA benchmark, in a one-call "
        "form). Answering needs finding the right values in the supplied document pages (running text and "
        "tables) and often a calculation with them.\n"
        "Input the solver receives: a JSON object with two fields -- \"question\" and \"context\" (the parsed "
        "text of the bulletin page or pages the question refers to; tables are rendered as text; a long page "
        "may be cut).\n"
        "Fixed instructions the solver always receives: \"Solve the supplied task using only the supplied "
        "public information.\" and \"Return the concise final answer inside <answer>...</answer>.\"\n"
        "Scoring (public metric): the text inside the last <answer>...</answer> is compared with the "
        "reference answer by exact match after normalization (lower case; commas removed; punctuation "
        "removed except digits, '.', '-' and '%'; the words million, billion, dollar(s) and nominal removed; "
        "whitespace collapsed). There is no numeric tolerance. A reply without such a tag counts as wrong. "
        "Anything outside the tag is ignored."),
    "livemath": (
        "Task kind: multiple-choice questions about research-level mathematics (the LiveMathematicianBench "
        "benchmark): each question is built from a theorem of a recent arXiv paper.\n"
        "Input the solver receives: a JSON object with two fields -- \"question\" (the statement to complete "
        "or decide) and \"choices\" (five options labelled A to E, separated by blank lines; exactly one is "
        "correct).\n"
        "Fixed instructions the solver always receives: \"Solve the supplied task using only the supplied "
        "public information.\" and \"Choose exactly one of the listed options and return only its letter "
        "inside <answer>...</answer>.\"\n"
        "Scoring (public metric): the letter inside the last <answer>...</answer> is compared with the "
        "letter of the correct option; a reply without such a tag, or with anything but one letter in it, "
        "counts as wrong. Anything outside the tag is ignored."),
    "spreadsheetbench": (
        "Task kind: spreadsheet manipulation (the SpreadsheetBench benchmark): a natural-language instruction asks "
        "for a change to an Excel workbook, and the solver writes a Python program that makes it.\n"
        "Input the solver receives: a JSON object with five fields -- \"instruction\", \"workbook_preview\" (for up "
        "to 20 sheets: the sheet name, its row and column counts, and the first 5 rows of up to 20 columns, with "
        "formulas shown as formulas), \"input_path\" (\"input.xlsx\"), \"required_output_path\" (\"output.xlsx\") "
        "and \"required_answer_position\" (the cells or range the instruction's result must occupy).\n"
        "Fixed instructions the solver always receives: \"Solve the supplied task using only the supplied public "
        "information.\" and \"Return one complete Python program in a ```python code block.\"\n"
        "Scoring (public metric): the program is taken from the reply's one ```python code block (without one, "
        "from a single unlabelled block or a reply that is entirely code; two Python blocks count as wrong) and runs "
        "once per test case in a sandbox (no network, a time limit of 300 seconds), reading that case's input.xlsx "
        "and writing output.xlsx; the workbook is recalculated, and the values in the answer position are compared "
        "with the reference workbook's. A task counts as solved only when every test case matches; a program that "
        "raises an error or writes no valid output.xlsx does not solve it."),
    "alfworld": (
        "Task kind: household tasks in a text environment (the ALFWorld benchmark): the solver acts step by step, "
        "one action per step, to reach a goal stated at the start (for example, to put a cleaned object in a "
        "receptacle).\n"
        "Input the solver receives at every step: a JSON object with four fields -- \"initial_observation\" (the "
        "room description and the task, as given when the episode starts), \"observation\" (the environment's "
        "latest text), \"admissible_commands\" (the actions the environment accepts now) and \"recent_history\" (the "
        "last five observation-action pairs).\n"
        "Fixed instructions the solver always receives: \"Act in the text environment. Return a single action "
        "inside <action>...</action>.\"\n"
        "Scoring (public metric): the episode succeeds when the environment reports the goal reached within 50 "
        "steps; an episode that runs out of steps counts as failed. The text inside the first <action>...</action> "
        "is executed (a reply without the tag is executed whole); an empty action or one longer than 1000 characters "
        "counts as failed."),
}
RUBRIC_SYSTEM = (
    "You write the initial rubric an examiner uses to judge a solver's answers to one kind of task WITHOUT seeing the "
    "correct answer. You are given ONLY the public description of the task kind (or, for the general rubric, of "
    "several kinds): no example task, no model answer, no score; do not invent facts about the data. A rubric item is "
    "a general criterion an examiner can verify from the task and the answer alone. Some items can be verified by a "
    "host check from this fixed library (name: parameters): answer_tag_present: {}; answer_single_letter: {}; "
    "answer_pure_number: {\"allow_percent\": true or false}; answer_no_percent: {}; answer_no_letters: {}; "
    "answer_max_words: {\"n\": 1-50}; code_present: {}. Use a check only when the item is exactly that check; "
    "otherwise use null. Write at most 12 items. Reply with one JSON object only: {\"items\": [{\"id\": \"%s1\", "
    "\"text\": \"at most 300 characters\", \"check\": null or {\"name\": ..., \"params\": {...}}, \"basis\": \"why, "
    "from the description, at most 300 characters\"}, ...]} with ids %s1, %s2, ... in order. "
    # the owner's decision of 10/17 (registration §25): a format reminder after two SpreadsheetBench replies left out
    # the basis; what an item says is unchanged
    "The object has the single key \"items\", and every item has exactly the four keys id, text, check and basis: "
    "none may be left out, none added.")


# v3 (the owner, after the format check): the fixed contract the SpreadsheetBench card quotes (backends' v1 sentence)
SHEET_CONTRACT_QUOTE = '"Return one complete Python program in a ```python code block."'


def solver_cards(cards, runtime):
    """The public task cards as the run's roles read them (the analyst, the self-test's revision): each quotes the
    fixed instructions the solver receives under the run's prompt layout -- v3: SpreadsheetBench's contract-first-v2
    contract. The registered cards (``CARDS``: the archive, the texts record, the manifest) stay as they are."""
    from skillopt.continual_eval import backends

    out = dict(cards)
    if (runtime.get("spreadsheetbench") or {}).get("prompt_layout") == backends.CONTRACT_FIRST_LAYOUT_V2:
        card = out["spreadsheetbench"]
        require(card.count(SHEET_CONTRACT_QUOTE) == 1, "The SpreadsheetBench card quotes its contract once")
        out["spreadsheetbench"] = card.replace(SHEET_CONTRACT_QUOTE, '"%s"' % backends.SHEET_CONTRACT_V2.strip())
    return out


def instruction_prompt(benchmark):
    """(system, user) of a task-card instruction: the existing generator's prompt, its user message in plain text."""
    require(benchmark in CARDS, "No public task card")
    return INSTRUCTION_SYSTEM, "Public task card:\n\n" + CARDS[benchmark]


def instruction_text(reply):
    """The reply as the Skill text (one wrapping code fence removed, nothing else edited), or None when blank."""
    text = reply.strip()
    if text.startswith("```") and text.endswith("```") and text.count("```") == 2:
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip() if "\n" in text else ""
    return text + "\n" if text.strip() else None


def rubric_prompt(scope):
    """(system, payload) of an initial rubric: a bench from its card; the general rubric from all five."""
    letter = "G" if scope == GENERAL else "R"
    system = RUBRIC_SYSTEM % (letter, letter, letter)
    if scope == GENERAL:
        return system, {"rubric": "general: criteria that hold for every one of these task kinds",
                        "task_cards": {TITLES[b]: CARDS[b] for b in ORDER}}
    return system, {"rubric": TITLES[scope], "task_card": CARDS[scope]}


def _rubric(scope):
    def check(value):
        fields(value, ["items"])
        if type(value["items"]) is not list or not 1 <= len(value["items"]) <= MAX_ITEMS:
            raise Invalid("items")
        try:
            return validate_rubric({"bench": scope, "items": value["items"]}, scope)
        except ValueError as error:
            raise Invalid(str(error)[:60]) from None
    return check


def write_rubric(roles, scope, *, label):
    """The initial rubric of ``scope`` (a bench or ``general``), or None when two replies were not valid rubrics."""
    system, value = rubric_prompt(scope)
    for attempt in range(1, ANALYST_ATTEMPTS + 1):
        rubric = roles.ask("rubric_writer", system, value, label="%s/attempt%d" % (label, attempt),
                           check=_rubric(scope))
        if rubric is not None:
            return rubric
    return None


def write_instruction(roles, benchmark, *, label):
    """A task-card instruction written once (no selection); None when no complete, nonblank reply arrived."""
    system, user = instruction_prompt(benchmark)
    reply = roles.plain("instruction_writer", system, user, label=label)
    return None if reply is None else instruction_text(reply)
