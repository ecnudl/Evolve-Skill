"""typed-v2 program-writer prompt, static-screen rule table and fix evidence (DESIGN 3.2, decision D3).

typed-v1 sent the stale route-B engineer text, which never stated the static screen: 4 of its 12 program candidates
died there (F6). This module owns the ten system texts of the typed program writer (the five benches times the
purposes ``propose`` and ``fix``), the table ``RULES`` of every rule of the frozen screen with a legal rewrite, and
the evidence rows a fix call receives. The screen itself is NOT changed: it stays ``policy.check(source,
version=POLICY_VERSION)`` with no bench (so the OfficeQA and ALFWorld literal bans apply on every bench), exactly as
``writers.build_procedure`` calls it. The two static-screen relaxations the owner approved are deferred (DESIGN
section 1); the text names both forms as illegal and gives their legal rewrite.

Every list and limit of a text is rendered from the bound modules (``policy``, ``profiles``, ``package``, ``notes``,
this package's limits, ``replies.REPLY_FORMAT``), never typed, so a text cannot disagree with the screen that runs.
Rules stated in words are held to the code by the legal and the illegal example program of each row, which
``verify()`` runs through the real screen. ``PINS`` holds the sha256 of the ten texts; a change of any text comes with
a new ``PROMPT_VERSION`` and new ``PINS``. Import order ``replies`` <- ``engineer_prompt`` <- ``writers``: this module
imports no module of ``typed`` that imports it, never calls a model and touches no file.

    row      = Rule(key, rule, sentence, rewrite, legal, illegal, parent, label)
    evidence = {'check', 'detail': [{'rule', 'line', 'detail', 'source_line', 'rule_text', 'rewrite'}], 'more'}
    record   = {'rows': [{'rule', 'key', 'line', 'detail', 'source_line'}], 'more'}      # evidence_record
"""
from __future__ import annotations

import hashlib
import re
from collections import namedtuple

from skillopt.execskill import notes, package, policy, profiles

from . import MACHINERY, MAX_PROGRAM_CANDIDATES, MAX_PROGRAM_PROPOSALS, ORDER
from . import replies

# typed-engineer-prompt-1 (batch 1, never sent by a run) stated '"from M import name" are allowed' without the ban on
# banned members that the screen applies to a from-import; -2 states it in the [import] row (fix-b, coord-1).
PROMPT_VERSION = 'typed-engineer-prompt-2'
PURPOSES = ('propose', 'fix')
POLICY_VERSION = profiles.POLICY_VERSIONS[MACHINERY]   # the typed screen: the same expression as writers.POLICY_VERSION
CHECKS = ('policy', 'hooks', 'structure', 'source')    # the checks of writers.build_procedure (``failed['check']``)
EVIDENCE_ROWS = 8
SOURCE_LINE_CHARS = 240
# The hooks that can write a note, per bench (the route-B registrar's no-effect list, X/engineer.py:2359-2361,
# without its ALFWorld addition alf_after_step: a state-only program writes no note). A program that defines none of
# them fails ``build_procedure`` with check 'hooks', rule 'no_hook_function' (addendum O7).
NOTE_HOOKS_BY_BENCH = {'searchqa': ('before_call', 'bindings'), 'officeqa': ('before_call', 'bindings'),
                       'zebralogic': ('before_call',), 'spreadsheetbench': ('before_call', 'sheet_feedback'),
                       'alfworld': ('alf_before_step',)}
CONSTANT_DETAIL = 'a constant must be a literal or a registered pure expression'   # X/policy.py:389-390
TYPE_NAME_ATTRIBUTES = ('__name__', '__class__', '__qualname__')

# Every frozen name this module reads, in the shape of machinery.REQUIRED ({module: (names,)}).
MACHINERY_SYMBOLS = {
    'skillopt.execskill.notes': ('FIELD_TYPES',),
    'skillopt.execskill.package': ('MAX_STATE_BYTES',),
    'skillopt.execskill.policy': ('FORBIDDEN_ATTRIBUTES', 'FORBIDDEN_MODULES', 'FORBIDDEN_NAMES', 'FROM_ONLY',
                                  'IMPORTABLE', 'MAX_CONSTANT_CHARS', 'ORDINARY_ATTRIBUTES', 'RECEPTACLES', 'RULES',
                                  'check', 'source_limit'),
    'skillopt.execskill.profiles': ('MAX_DESCRIPTION_CHARS', 'MAX_HEADER_CHARS', 'MAX_NOTE_CHARS', 'POLICY_VERSIONS',
                                    'SANDBOX_TIMEOUTS'),
}

# The first seven fields are the row of spec/engineer.md 1.1 item 4; ``label`` is the name printed in brackets (a
# sentence row) or after "Rewrite," (a rewrite row, ``parent`` set, ``sentence`` None).
Rule = namedtuple('Rule', ('key', 'rule', 'sentence', 'rewrite', 'legal', 'illegal', 'parent', 'label'))

# ---- fixed wording ---------------------------------------------------------------------------------------------
INTRO = {
    'propose': ('You write small Python helper programs for a solver model that works on %s tasks. A program runs in '
                'a sandbox beside the solver. Its hook functions read the public task input and may hand the solver '
                'short notes. It never sees a reference answer or a score. A program is kept only on results: first '
                'it must run without a fault on a few practice tasks; then, on held-out practice tasks, the solver '
                'must do clearly better with it than without it on the tasks where the program applied, and no worse '
                'over all tasks.'),
    'fix': ('A helper program you wrote for a solver model on %s tasks was rejected by a check before it could be '
            'tested. Correct it. Keep what the program does; change only what the check requires. You get this one '
            'correction.'),
}
RECEIVE = {
    'propose': ('WHAT YOU RECEIVE (user message, JSON). task_card and format_block: what the solver is already told; '
                'both are fixed, do not restate them. skill_index: names and descriptions of the skills that already '
                'exist for these tasks; do not duplicate one. trajectories: practice tasks with the solver\'s '
                'outcome; look for mistakes a program could have prevented by computing or checking something from '
                'the task input. hook_views: one real sample of the exact inputs your hooks receive (long strings and '
                'lists are cut for display only).'),
    'fix': ('WHAT YOU RECEIVE (user message, JSON). change: the entry of the rejected program. failed_source: its '
            'full text. failed.check: which check failed ("policy" = the static screen below; "hooks" = no usable '
            'hook function is defined; "structure" = the entry and the hooks do not fit together; "source" = no '
            'program text was found). Each row of failed.detail gives: rule (the name used in the screen rules '
            'below), line and source_line (where; line 0 = the file as a whole), detail (what the checker saw), '
            'rule_text (the rule in words) and rewrite (the standard legal form). failed.more counts violations not '
            'shown.'),
}
PROPOSE_ORDER = ('Propose at most %d programs, the most useful first. They are checked in your order: the first %d '
                 'that pass the static screen are tested, and a later one is used only when an earlier one fails. ')
FIX_RETURN = ('Apply the rewrite on every listed line. Then read the whole program once more against every rule of '
              'the static screen: a rejected program often breaks the same rule in other places. Return the complete '
              'corrected program, not a patch, with the same entry fields (%s).')
HOOKS_HEAD = ('HOOKS. The sandbox calls only top-level functions with exactly these names and parameters. Naming a '
              'hook in "hooks" does not create it. ')
NO_HOOK_SENTENCE = 'A program that defines none of %s can never write a note and is rejected.'
APPLIES_LINE = ('applies(view) -> bool. Optional; without it the program applies to every task. Return False where '
                'the program has nothing reliable to say: it is judged on the tasks where applies returned True.')
NOTES_TEXT = ('NOTES. A notes dict may hold any of: "facts" and "warnings": lists of strings, each at most %d '
              'characters; "candidates": list of strings, each at most %d characters; "table": list of rows, at most '
              '%d rows by %d columns, every cell a string of at most %d characters; "bindings": list of %s, each a '
              'string of at most %d characters. An unknown field, a wrong type or a value over its cap is a fault and '
              'the whole note is dropped; so is a rendered note longer than max_note_chars. Smallest valid returns: '
              '%s. When the program cannot verify what it would say on a task, return no note: a wrong note costs '
              'more than no note.')
CONTENT = ('CONTENT. Notes state what the program computed from this task\'s own public input. Never: a false or '
           'overclaiming note; advice on the form of the answer beyond what the task itself states; an instruction '
           'that overrides the task or its scoring; a guess from what is typical for the benchmark; facts from '
           'outside the task or hard-coded answers; routing by benchmark name, task id, file path, answer or score. '
           'The program must do what its description says.')
SCREEN_HEAD = ('STATIC SCREEN. Before anything runs, a checker reads the program text. It is strict and literal: one '
               'violation rejects the program, and you get one correction. The rules, each with the name the checker '
               'reports:')
SMALLEST = {'searchqa': 'before_call -> {}; bindings -> {"bindings": []}',
            'officeqa': 'before_call -> {}; bindings -> {"bindings": []}',
            'zebralogic': 'before_call -> {}',
            'spreadsheetbench': 'before_call -> {}; sheet_feedback -> {"fields": {}, "request_repair": False}',
            'alfworld': 'alf_before_step -> {"fields": {}, "discourage": []}'}
# Addendum D17: the label of the base card block of the proposal payload (``writers.program_payload`` adds
# {'meaning': BASE_CARD_MEANING, 'text': <the base card>} under the base 'historical' where it adds to the format
# block). It lives in the user message, so the ten pinned system texts and ``PINS`` are unchanged.
BASE_CARD_MEANING = ('The instruction the solver already receives on every task of this kind: this whole text is in '
                     'its system prompt, unchanged, and it contains every line of format_block. Your program\'s notes '
                     'add to it: do not repeat it and do not contradict it.')
# Addendum D16 (a): a shared type's proposal payload (its home type also holds sources of earlier benches) gets the
# key ``members`` (``writers.program_members``): this sentence, naming the member sources (``%s``) and stating the
# acceptance rule on them (b), and one block per member source labelled with it (its format block and, where the base
# adds to it, its base card under MEMBER_BASE_MEANING, D17; and its trajectories). User message only: the ten pinned
# system texts and ``PINS`` are unchanged, and a type of one bench gets no such key.
MEMBERS_MEANING = ('Your programs also run on every task of the other sources of this task type: %s. members.sources '
                   'shows for each of them what the solver already receives there (its format_block and, where given, '
                   'its base card) and practice tasks with the solver\'s outcome there (trajectories). A program is '
                   'kept only if, besides the rule of the system message on the tasks like those in trajectories, the '
                   'solver does no worse with it than without it over all held-out practice tasks of each of these '
                   'sources, beyond the measured noise.')
MEMBER_BASE_MEANING = ('The instruction the solver already receives on every task of this source: this whole text is '
                       'in its system prompt, unchanged, and it contains every line of this source\'s format_block. Your '
                       'program\'s notes add to it: do not repeat it and do not contradict it.')

# typed-v3 (CHAIN-DECISIONS T8): the program-repair system text, a purpose of its own BESIDE the ten pinned texts of
# typed-v2 ('propose' and 'fix': ``PURPOSES``, ``PINS``, ``system`` and the return value of ``verify`` are unchanged,
# and ``system`` still refuses any other purpose). Its five texts (one per bench, ``repair_system``) are rendered from
# the same bound modules and the same rule table as the ten (the HOOKS, NOTES, CONTENT and STATIC SCREEN paragraphs are
# the propose text's, word for word), plus the sandbox's wall limit per hook call (``profiles.SANDBOX_TIMEOUTS``, the
# "wall timeout of 5 s" of the worker's timeout fault) and the rule that an exhaustive search must prune. They are
# pinned in ``REPAIR_PINS`` and checked by ``verify()`` together with the ten; machinery check 6 pins both tables
# (``machinery.pinned_texts``). The reply format is the fix reply's (``replies.REPLY_FORMAT['fix']``: one entry, one
# program), read by the same tolerant reader with its one format retry.
REPAIR = 'repair'
REPAIR_SHOWN_ITEMS = 5  # tasks per failure class, and broken tasks, a repair request shows (its text states it)
REPAIR_INTRO = ('A helper program you wrote for a solver model on %s tasks passed the static screen. It was then run in '
                'the sandbox on practice tasks without any model call: on each task its hooks ran and the request the '
                'solver would receive was built. Revise it so that it writes a correct, useful note on more of these '
                'tasks. Keep what works; change what the coverage report shows does not work.')
REPAIR_RECEIVE = ('WHAT YOU RECEIVE (user message, JSON). change: the entry of the program. source: its full text. '
                  'coverage: what the run on practice tasks showed: items (the tasks run), routed (the tasks of the '
                  'program\'s task type, the only ones where it is mounted; the other tasks count in no class), fired '
                  '(the tasks where it applied: applies returned True or is not defined), noted (the tasks where its '
                  'note reached the request), faults (counts by kind: timeout means a hook call ran past the wall limit '
                  'under RUN LIMITS; another kind names the exception or the rule a returned value broke), scope (what '
                  'of each task was run) and classes: for each failure class among the routed tasks '
                  '(fired_without_note: it applied and wrote no note; not_fired: applies returned False; fault:<kind>: '
                  'a hook failed with that fault) its count and up to %d of its tasks with their public text. learn '
                  '(only after one paid run of the program on the '
                  'practice tasks): fixed and broken (the tasks the solver got right only with the program, and the '
                  'tasks it got right only without it) and up to %d broken tasks with their public text.')
REPAIR_RETURN = ('Return the complete revised program, not a patch, with the same entry fields (%s). A note must stay '
                 'correct: never trade correctness for coverage, and on a task where the program cannot verify what it '
                 'would say it returns no note.')
RUN_LIMITS = ('RUN LIMITS. Each hook call runs in the sandbox with a wall limit of %d s (applies: %d s); a call that '
              'runs longer is stopped, counted as a timeout fault, and the program is switched off for that task. An '
              'exhaustive search (over assignments, orderings or combinations) must prune: check every partial choice '
              'against the constraints and cut a branch as soon as it breaks one; when the search cannot finish well '
              'inside the limit, return no note.')

# The rows of the three checks of build_procedure that are not the policy screen (one evidence row each, line 0).
# ``%s`` is the bench's note-hook list; the 'hooks' rule_text is word for word the HOOKS sentence of the text.
CHECK_WORDS = {
    'hooks': {'rule': 'no_hook_function', 'rule_text': NO_HOOK_SENTENCE,
              'rewrite': ('define at least one of %s as a top-level function with exactly the parameters given under '
                          'HOOKS; where it has nothing reliable to say it returns the smallest valid value given '
                          'under NOTES.')},
    'structure': {'rule': 'structure',
                  'rule_text': 'The entry and the hooks must fit together; detail names the requirement that failed.',
                  'rewrite': ('change the entry or the program so that this requirement holds; keep the entry '
                              'fields in their stated forms.')},
    'source': {'rule': 'source', 'rule_text': 'A program text must be found in the reply.',
               'rewrite': 'give the complete program in one fenced python block after the JSON block.'},
}


# ---- the rule table --------------------------------------------------------------------------------------------
def _program(top=(), body=()):
    """A complete example module: ``top`` lines, then a ``before_call`` holding ``body`` and returning {}."""
    return (''.join(line + '\n' for line in top) + 'def before_call(view, state):\n'
            + ''.join('    ' + line + '\n' for line in body) + '    return {}\n')


def _listed(names):
    return ', '.join(names)


def _quoted(texts):
    """'"a", "b" and "c"': the example lines of a sentence."""
    quoted = ['"%s"' % text for text in texts]
    return ', '.join(quoted[:-1]) + ' and ' + quoted[-1] if len(quoted) > 1 else ''.join(quoted)


# fix-b (coord-1): the frozen screen also rejects, with rule 'import', a from-import of a member that the name or
# attribute rules ban or that is a blocked module name, time and random included (``policy._imports`` with
# ``_forbidden_member``). The [import] row names these three lines as rejected and its rewrite names the legal form
# IMPORT_MEMBER_LEGAL; ``verify()`` runs each through the real screen.
IMPORT_MEMBER_EXAMPLES = ('from datetime import time', 'from pandas import read_csv', 'from numpy import random')
IMPORT_MEMBER_LEGAL = _program(top=['import datetime'], body=['t = datetime.time(12, 0)'])


def _rules():
    """The 22 rows (17 sentence rows, 5 rewrite rows), in the order of the STATIC SCREEN paragraph, rendered from
    the bound modules at call time."""
    limit = policy.source_limit(POLICY_VERSION)
    constant = policy.MAX_CONSTANT_CHARS
    from_only = '; '.join('"from %s import %s"' % (module, _listed(members))
                          for module, members in policy.FROM_ONLY.items())
    modules = [name for name in policy.FORBIDDEN_MODULES if name not in policy.ORDINARY_ATTRIBUTES]
    rows = [
        ('size', 'size', 'size',
         'The file is at most {:,} bytes of UTF-8.'.format(limit),
         'shorten the program; drop tables and branches it does not need.',
         _program(), _program(top=['# ' + 'x' * limit]), None),
        ('syntax', 'syntax', 'syntax', 'The file is valid Python 3.',
         'correct the line the checker names and re-read the lines around it.',
         _program(body=['return {"facts": []}']), _program(body=['return {"facts": [}']), None),
        ('top_level', 'module_level', 'module_level, statements',
         ('At the top level write only: an optional docstring as the first statement, import lines, def functions, '
          'and constants written NAME = value with one plain name on the left. No if / for / while / try / with, no '
          'class, no "A, B = 1, 2", no "A: int = 1", no "A += 1", no call or other expression on a line of its own.'),
         'move the statement into a function; write one constant per line.',
         _program(top=['LIMIT = 3']), _program(top=['LIMIT = 3', 'if LIMIT > 2: LIMIT = 2']), None),
        ('constant_value', 'module_level', 'module_level, constant values',
         ('The value of a top-level constant must be one of: (a) a literal: a number, string, bytes, True, False, '
          'None, or a tuple, list, set or dict written out with literals inside (nesting is fine); (b) the name of an '
          'earlier constant, alone: B = A; (c) literals of one type joined with +: "ab" + "cd", [1, 2] + [3]; (d) '
          'exactly ONE of these calls on literals: set(...), frozenset(...), tuple(...), list(...), dict(...), '
          'sorted(...) of one literal; "a b c".split() or "a,b".split(","); ", ".join(["a", "b"]); '
          're.compile("pattern") or re.compile("pattern", re.I | re.M) after a plain "import re". The forms cannot be '
          'nested or mixed. Nothing else is allowed in a constant: no f-string, comprehension, lambda, *, %, .format, '
          'no other call, no expression that uses another constant.'),
         None,
         _program(top=['WORDS = {"alpha", "beta"}']),
         _program(top=['WORDS = {w.lower() for w in ("Alpha", "Beta")}']), None),
        ('constant_word_set', 'module_level', 'word set', None,
         ('WORDS = frozenset("alpha beta".split()) is rejected (two calls). Write WORDS = frozenset({"alpha", '
          '"beta"}), or keep a list: WORDS = "alpha beta".split().'),
         _program(top=['WORDS = frozenset({"alpha", "beta"})']),
         _program(top=['WORDS = frozenset("alpha beta".split())']), 'constant_value'),
        ('constant_regex', 'module_level', 'regex', None,
         (r'PAT = re.compile(r"(\d+)\s*" + UNIT) is rejected. Write the pattern as one string literal (adjacent '
          r'literals without + count as one: re.compile(r"(\d+)\s*" r"(kg|lb)")), or compile it inside the function '
          r'that uses it.'),
         _program(top=['import re', r'PAT = re.compile(r"(\d+)\s*" r"(kg)")']),
         _program(top=['import re', 'UNIT = "kg"', r'PAT = re.compile(r"(\d+)\s*" + UNIT)']), 'constant_value'),
        ('constant_other', 'module_level', 'any other value', None,
         'compute it inside a function and call that function where the value is needed.',
         _program(body=['SEP = ", ".join(sorted(["b", "a"]))']),
         _program(top=['SEP = ", ".join(sorted(["b", "a"]))']), 'constant_value'),
        ('constant_size', 'constant_size', 'constant_size',
         'The written value of one constant is at most {:,} characters.'.format(constant),
         'several shorter constants, combined inside a function.',
         _program(top=['BIG = "%s"' % ('x' * (constant - 100))]),
         _program(top=['BIG = "%s"' % ('x' * (constant + 100))]), None),
        ('statement', 'statement', 'statement', 'No class, global, nonlocal, async or await anywhere.',
         'return dicts or tuples; keep memory in the state argument.',
         _program(top=['def box(): return {}']), _program(top=['class Box: pass']), None),
        ('decorator', 'decorator', 'decorator', 'No decorators.', 'a plain function.',
         _program(top=['def helper(x): return x']),
         _program(top=['import functools', '@functools.lru_cache(maxsize=None)', 'def helper(x): return x']), None),
        ('import', 'import', 'import',
         ('Only these modules may be imported: %s. "import M", "import M as name" and "from M import name" are '
          'allowed for them, and also %s. In "from M import name" the name must not be one that the [name] or '
          '[attribute] rules below ban, nor a blocked module name (%s included): %s are rejected. No "import *", no '
          'other submodule and no other module: no typing, dataclasses, os, sys, io, time, random, pathlib.'
          % (_listed(policy.IMPORTABLE), from_only, ' and '.join(policy.ORDINARY_ATTRIBUTES),
             _quoted(IMPORT_MEMBER_EXAMPLES))),
         ('leave type hints out or use the built-in names (list, dict); for a banned member import the module and '
          'write the member after a dot where the [attribute] rule allows it (import datetime, then datetime.time).'),
         _program(top=['from datetime import datetime']), _program(top=['from typing import List']), None),
        ('name', 'name', 'name',
         ('These names cannot be used at all (as a call, variable, parameter, function name or import alias): %s. '
          'No name may start with two underscores.' % _listed(policy.FORBIDDEN_NAMES)),
         ('view.get("key") instead of getattr / hasattr; call a variable ident or kind, not id or hash; return notes '
          'instead of print.'),
         _program(body=['found = "question" in view']), _program(body=['found = hasattr(view, "question")']), None),
        ('attribute', 'attribute', 'attribute',
         ('After a dot these are never allowed: (1) a name starting with an underscore, which covers every dunder '
          '(__name__, __class__, __dict__); (2) a name starting with read_ or to_ (to_dict, to_numeric, to_datetime, '
          'read_csv); (3) these names: %s; (4) a name equal to a blocked module name: %s.'
          % (_listed(policy.FORBIDDEN_ATTRIBUTES), _listed(modules))),
         None,
         _program(body=['value = view.get("cache")']), _program(body=['value = view._cache']), None),
        ('attribute_type_name', 'attribute', 'exception or type name', None,
         ('type(e).__name__ is rejected. Catch the class you expect and write its name as text: except ValueError: '
          'kind = "ValueError". For an unknown exception use repr(e).split("(", 1)[0].'),
         _program(body=['try:', '    value = float(view.get("question"))', 'except ValueError:',
                        '    kind = "ValueError"']),
         _program(body=['try:', '    value = float(view.get("question"))', 'except Exception as e:',
                        '    kind = type(e).__name__']), 'attribute'),
        ('attribute_data', 'attribute', 'data access', None,
         ('view.get("code") or row["code"] instead of view.code; list(series) and dict(zip(keys, values)) instead of '
          'to_list / to_dict; float(text) instead of to_numeric.'),
         _program(body=['rows = dict(view)']), _program(body=['rows = view.to_dict()']), 'attribute'),
        ('numpy_random', 'numpy_random', 'numpy_random',
         'numpy randomness only as numpy.random.default_rng(seed) with one fixed integer seed.',
         'rng = numpy.random.default_rng(7).',
         _program(top=['import numpy as np'], body=['rng = np.random.default_rng(7)']),
         _program(top=['import numpy as np'], body=['rng = np.random.default_rng()']), None),
        ('clock', 'clock', 'clock',
         ('No current time: besides .now / .today / .utcnow, no "now" or "today" text given to Timestamp, Period or '
          'datetime64.'),
         'take dates from the task text.',
         _program(top=['import pandas as pd'], body=['t = pd.Timestamp("2020-01-01")']),
         _program(top=['import pandas as pd'], body=['t = pd.Timestamp("now")']), None),
        ('sympify', 'sympify', 'sympify', 'No sympy parsing of text: no S("..."), sympify, parse_expr or lambdify.',
         'build expressions from sympy.Symbol and numbers.',
         _program(top=['import sympy'], body=['e = sympy.Symbol("x") + 1']),
         _program(top=['import sympy'], body=['e = sympy.S("x+1")']), None),
        ('dunder_string', 'dunder_string', 'dunder_string',
         'No string literal may contain a word wrapped in double underscores, such as "__main__".',
         'drop the text or write it without the underscores.',
         _program(body=['k = "main"']), _program(body=['k = "__main__"']), None),
        ('meta_option', 'meta_option', 'meta_option',
         ('The file, comments included, must not contain "stronger result", "stronger statement" or any four '
          'consecutive words of "one of the remaining options is correct but a stronger result can be proven".'),
         'delete the sentence; describe what the program computes instead.',
         _program(top=['# among the options given']), _program(top=['# of the remaining options']), None),
        ('bulletin_literal', 'bulletin_literal', 'bulletin_literal',
         ('On every bench, no string literal (docstrings included) may contain: a page reference with a number '
          '("page 12", "pp. 3"); a month name or abbreviation followed by a year 1800-2099 ("March 1985"; the word '
          '"may" counts); "treasury bulletin" followed by a digit.'),
         r'read such values from the task input at run time; in a pattern write \d+.',
         _program(body=['s = "see the page named in the question"']), _program(body=['s = "see page 12"']), None),
        ('receptacle_literal', 'receptacle_literal', 'receptacle_literal',
         ('On every bench, no string literal may contain one of these words followed by a number ("cabinet 1", '
          '"drawer 3"): %s.' % _listed(policy.RECEPTACLES)),
         'take object names from the observation or the admissible commands at run time.',
         _program(body=['s = "open the drawer"']), _program(body=['s = "open drawer 3"']), None),
    ]
    return tuple(Rule(key, rule, sentence, rewrite, legal, illegal, parent, label)
                 for key, rule, label, sentence, rewrite, legal, illegal, parent in rows)


def _screen_line(row):
    if row.parent is not None:
        return 'Rewrite, %s: %s' % (row.label, row.rewrite)
    if row.rewrite is None:
        return '[%s] %s' % (row.label, row.sentence)
    return '[%s] %s Rewrite: %s' % (row.label, row.sentence, row.rewrite)


# ---- the texts -------------------------------------------------------------------------------------------------
def _entry_items(bench):
    note_cap = max(profiles.MAX_NOTE_CHARS.values())
    items = ['"kind": "new" (the only kind accepted)',
             '"description": what the program does and when it helps, at most %d characters'
             % profiles.MAX_DESCRIPTION_CHARS,
             '"hooks": the hook functions your code defines',
             '"header": a short title shown above its notes, at most %d characters, or ""' % profiles.MAX_HEADER_CHARS,
             '"max_note_chars": the longest note it may produce, 1 to %d (left out or 0 means %d)'
             % (note_cap, note_cap)]
    fields = ['"kind": "new"', '"description"', '"hooks"', '"header"', '"max_note_chars"']
    if bench == 'spreadsheetbench':
        items.append('"requests_second_call": true only if sheet_feedback may ask for a repair')
        fields.append('"requests_second_call"')
    if bench == 'alfworld':
        items.append('"state_bytes": the largest state alf_after_step returns, 1 to %d bytes of JSON (left out or 0 '
                     'means %d)' % (package.MAX_STATE_BYTES, package.MAX_STATE_BYTES))
        fields.append('"state_bytes"')
    return items, fields


def _binding_keys():
    return '{%s}' % ', '.join('"%s"' % key for key in notes.FIELD_TYPES['bindings']['keys'])


def _hook_lines(bench):
    if bench in ('searchqa', 'officeqa'):
        return ['before_call(view, state) -> a notes dict or None. view = {"question", "context"}; state is always '
                'None.',
                'bindings(view) -> {"bindings": [%s, ...]} or None: numbers quoted from the task text for the '
                'solver\'s calculator. name is a calculator name, value is numeric text, quote must contain value '
                'word for word.' % _binding_keys()]
    if bench == 'zebralogic':
        return ['before_call(view, state) -> a notes dict or None. view = {"question", "columns"}; state is always '
                'None. Read the puzzle\'s own clues and compute constraints the solver can use.']
    if bench == 'spreadsheetbench':
        return ['The view is {"instruction", "workbook_preview", "input_path", "required_output_path", '
                '"required_answer_position"}.',
                'before_call(view, state) -> a notes dict or None; state is always None.',
                'sheet_feedback(view, run_report, state) -> {"fields": notes dict, "request_repair": bool}. run_report '
                '= {"status", "exc_type", "message", "answer_cells"} comes from one run of the solver\'s code on the '
                'public input workbook; it holds no reference workbook and no grading result, and the program never '
                'sees the solver\'s code. request_repair asks for at most one repair attempt by the solver and counts '
                'only when the entry declares "requests_second_call": true.']
    return ['applies reads view = {"initial_observation", "admissible_commands_at_reset", "task_text"}.',
            'alf_before_step(view, state) -> {"fields": notes dict, "discourage": [admissible commands to advise '
            'against]}. view = {"initial_observation", "observation", "admissible_commands", "recent_history"}.',
            'alf_after_step(event, state) -> the new state (plain JSON data). event = {"step", "action", '
            '"observation", "admissible_commands"}. state is None until alf_after_step first returns a value. Module '
            'globals are reset between calls: keep memory in state only. On this bench the notes of one step are '
            'limited to %d characters in all; a longer note is skipped. The first fault switches the program off for '
            'the rest of the episode.' % profiles.MAX_NOTE_CHARS['alfworld']]


def _hooks_paragraph(bench):
    return '\n'.join([HOOKS_HEAD + NO_HOOK_SENTENCE % _listed(NOTE_HOOKS_BY_BENCH[bench]), APPLIES_LINE]
                     + _hook_lines(bench))


def _notes_paragraph(bench):
    field = notes.FIELD_TYPES
    return NOTES_TEXT % (field['facts']['max_chars'], field['candidates']['max_chars'], field['table']['max_rows'],
                         field['table']['max_columns'], field['table']['max_chars'], _binding_keys(),
                         field['bindings']['max_chars'], SMALLEST[bench])


def _screen_paragraph(rules):
    return '\n'.join([SCREEN_HEAD] + [_screen_line(row) for row in rules])


def _render(bench, purpose, rules):
    items, fields = _entry_items(bench)
    if purpose == 'propose':
        returned = ('WHAT YOU RETURN. ' + replies.REPLY_FORMAT['propose'] + '\n'
                    + PROPOSE_ORDER % (MAX_PROGRAM_PROPOSALS, MAX_PROGRAM_CANDIDATES)
                    + 'Each entry of "changes" has: ' + '; '.join(items) + '.')
    else:
        returned = 'WHAT YOU RETURN. ' + replies.REPLY_FORMAT['fix'] + '\n' + FIX_RETURN % ', '.join(fields)
    paragraphs = [INTRO[purpose] % bench, RECEIVE[purpose], returned, _hooks_paragraph(bench), _notes_paragraph(bench),
                  CONTENT, _screen_paragraph(rules)]
    return '\n\n'.join(paragraphs) + '\n'


def _render_all(rules):
    return {(bench, purpose): _render(bench, purpose, rules) for bench in ORDER for purpose in PURPOSES}


def run_limits():
    """The RUN LIMITS paragraph of the repair text: the bound sandbox wall limits (seconds) of a hook call and of the
    ``applies`` predicate (``profiles.SANDBOX_TIMEOUTS``), and the pruning rule."""
    return RUN_LIMITS % (profiles.SANDBOX_TIMEOUTS['hook'], profiles.SANDBOX_TIMEOUTS['predicate'])


def _render_repair(bench, rules):
    """The repair text of ``bench`` (typed-v3, T8): eight paragraphs -- intro, what is received, what is returned (the
    fix reply's format), then HOOKS and NOTES as in the propose text, RUN LIMITS, then CONTENT and the STATIC SCREEN as
    in the propose text."""
    _, fields = _entry_items(bench)
    returned = 'WHAT YOU RETURN. ' + replies.REPLY_FORMAT['fix'] + '\n' + REPAIR_RETURN % ', '.join(fields)
    paragraphs = [REPAIR_INTRO % bench, REPAIR_RECEIVE % (REPAIR_SHOWN_ITEMS, REPAIR_SHOWN_ITEMS), returned,
                  _hooks_paragraph(bench), _notes_paragraph(bench), run_limits(), CONTENT, _screen_paragraph(rules)]
    return '\n\n'.join(paragraphs) + '\n'


def _render_repairs(rules):
    return {(bench, REPAIR): _render_repair(bench, rules) for bench in ORDER}


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


RULES = _rules()
_ROWS = {row.key: row for row in RULES}
_DIRECT = tuple(row.key for row in RULES if row.key == row.rule and row.rule not in ('module_level', 'attribute'))
_KEY_BY_REWRITE = {row.rewrite: row.key for row in RULES if row.rewrite is not None}
_TEXTS = _render_all(RULES)
_REPAIR_TEXTS = _render_repairs(RULES)

# sha256 of the ten texts (DESIGN 4.3; machinery check 6). verify() recomputes them from the bound modules.
PINS = {
    ('searchqa', 'propose'): '2922c9d9a035b4f43867ec85a7e8dbc07b58caf737230104792ddddf16dc2246',
    ('searchqa', 'fix'): '7c65003537d122b2f7aa44d281958960116f00a54b79942c61c99cf3ef700c11',
    ('officeqa', 'propose'): '4b9817730e2d9fe8b314028652ac7f574672d7a7001fbd9606377da7d88d6947',
    ('officeqa', 'fix'): 'd6fb75ee3398bb30a3ab78d9fdec0a39e313eee996921a3067cf732512a34dbd',
    ('zebralogic', 'propose'): '1a8bf9a409861ce11e17ee2fd4b138c69981c5f1ab578ab756357bc3fab8243e',
    ('zebralogic', 'fix'): 'b7db80956e3410c386e8333b197c9106d473e7dab37416ac7e3e58856b94f31b',
    ('spreadsheetbench', 'propose'): '62ed78f84b98390e2de63b8add4da499dca77efdf5a0d47886102f86b6c38dde',
    ('spreadsheetbench', 'fix'): '3f0c0d4d9e1f3ed275c5f14927d4c80c092d690adca1b6dd536177006012f345',
    ('alfworld', 'propose'): '20108ba71865560182c09d8cf6ff9106f1eb51944041cf0f57d949e1bff34f4e',
    ('alfworld', 'fix'): '8a06fbbb1260f77571360ad32f88d23caaf76567b8bd1f01c6474ba43cb4a07b',
}
# typed-v3 (T8): sha256 of the five repair texts (``repair_system``); verify() recomputes them with the ten.
REPAIR_PINS = {
    ('searchqa', 'repair'): '96f5db12f1d67da800acb9820bc7143d4ee5445c6c8524651a0dcdf2d9dcc5d6',
    ('officeqa', 'repair'): '6b1701304d8e967374ebf330f744bba1672a951b3c20c1b3e8d255be17ff8ee0',
    ('zebralogic', 'repair'): 'd6756fffeffa68f72e286bf8168644d02974695a0d0bf0d2397e8c455c03fcdc',
    ('spreadsheetbench', 'repair'): 'd2322617e91bf6f51adfd75fe65e5c65fa4780b45eacb9886cb3d2ac448d14ab',
    ('alfworld', 'repair'): '6a3076c83f13319ef777567a587021c33d718a1c1e6ad36dc0f3a55bd8fc596f',
}


# ---- public functions ------------------------------------------------------------------------------------------
def system(bench, purpose):
    """The program writer's system text for ``bench`` (one of ``ORDER``) and ``purpose`` (``propose`` or ``fix``);
    ValueError for anything else."""
    if not isinstance(bench, str) or bench not in ORDER:
        raise ValueError('Unknown bench for the program writer: %r' % (bench,))
    if not isinstance(purpose, str) or purpose not in PURPOSES:
        raise ValueError('Unknown program-writer purpose: %r' % (purpose,))
    return _TEXTS[(bench, purpose)]


def repair_system(bench):
    """The program writer's repair text for ``bench`` (typed-v3, T8; one of ``ORDER``); ValueError for anything
    else. A purpose beside ``system``'s two (module constants above ``REPAIR_INTRO``)."""
    if not isinstance(bench, str) or bench not in ORDER:
        raise ValueError('Unknown bench for the program writer: %r' % (bench,))
    return _REPAIR_TEXTS[(bench, REPAIR)]


def rule_key_for(rule, detail, source_line):
    """The row of ``RULES`` whose words answer one screen violation (rule id, its detail, the violating source line):
    a constant that is not a registered pure expression gives ``constant_word_set`` when the line has ``.split(``
    and ``set(``, ``constant_regex`` when it has ``.compile(``, else ``constant_other``; any other ``module_level``
    gives ``top_level``; ``attribute`` gives ``attribute_type_name`` for a type-name dunder, else ``attribute_data``;
    every other id the row of the same name. Never a parent row; ValueError for an id without a row."""
    if rule == 'module_level':
        if detail != CONSTANT_DETAIL:
            return 'top_level'
        line = source_line if isinstance(source_line, str) else ''
        if '.split(' in line and 'set(' in line:
            return 'constant_word_set'
        return 'constant_regex' if '.compile(' in line else 'constant_other'
    if rule == 'attribute':
        return 'attribute_type_name' if detail in TYPE_NAME_ATTRIBUTES else 'attribute_data'
    if isinstance(rule, str) and rule in _DIRECT:
        return rule
    raise ValueError('No rule row for the screen rule %r' % (rule,))


def _lines(source):
    return re.split(r'\r\n|\r|\n', source)    # the line breaks the Python tokenizer counts (ast line numbers)


def _source_line(lines, line):
    """The stripped source line ``line`` (1-based), None for line 0 or a line the source does not have."""
    if type(line) is not int or not 0 < line <= len(lines):
        return None
    return lines[line - 1].strip()


def _check_detail(detail):
    """The detail text of a 'hooks', 'structure' or 'source' failure: a text as given, or the details of its rows."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        return '; '.join(row['detail'] for row in detail
                         if isinstance(row, dict) and isinstance(row.get('detail'), str))
    return ''


def screen_evidence(failed, source, bench):
    """The ``failed`` part of a fix request (DESIGN 3.2): ``{'check', 'detail': [row, ...], 'more'}`` for one failure
    ``failed`` of ``writers.build_procedure`` on ``source``. Check 'policy' runs the frozen screen again, exactly as
    ``build_procedure`` does, keeps its order, shows the first ``EVIDENCE_ROWS`` violations and counts the rest in
    ``more``; a row is the violation's rule, line and detail, the stripped source line (cut at
    ``SOURCE_LINE_CHARS``; None for line 0), and the rule in words and its rewrite, word for word as in the system
    text. The checks 'hooks', 'structure' and 'source' give one row of ``CHECK_WORDS`` at line 0. ValueError for an
    unknown bench or check, or a policy failure that the screen does not reproduce."""
    if not isinstance(bench, str) or bench not in ORDER:
        raise ValueError('Unknown bench for the program writer: %r' % (bench,))
    check = failed.get('check') if isinstance(failed, dict) else None
    if not isinstance(check, str) or check not in CHECKS:
        raise ValueError('A screen failure names one of the checks %s' % (CHECKS,))
    if check != 'policy':
        words = CHECK_WORDS[check]
        hooks = _listed(NOTE_HOOKS_BY_BENCH[bench])
        fill = (lambda text: text % hooks) if check == 'hooks' else (lambda text: text)
        row = {'rule': words['rule'], 'line': 0, 'detail': _check_detail(failed.get('detail')), 'source_line': None,
               'rule_text': fill(words['rule_text']), 'rewrite': fill(words['rewrite'])}
        return {'check': check, 'detail': [row], 'more': 0}
    if not isinstance(source, str):
        raise ValueError('A policy failure has a program text')
    found = [violation.to_json() for violation in policy.check(source, version=POLICY_VERSION)]
    if not found:
        raise ValueError('The static screen finds no violation in this program text')
    lines, rows = _lines(source), []
    for violation in found[:EVIDENCE_ROWS]:
        line = _source_line(lines, violation['line'])
        row = _ROWS[rule_key_for(violation['rule'], violation['detail'], line)]
        words = _ROWS[row.parent] if row.parent is not None else row
        rows.append({'rule': violation['rule'], 'line': violation['line'], 'detail': violation['detail'],
                     'source_line': None if line is None else line[:SOURCE_LINE_CHARS],
                     'rule_text': words.sentence, 'rewrite': row.rewrite})
    return {'check': 'policy', 'detail': rows, 'more': len(found) - len(rows)}


def evidence_record(evidence):
    """The record form of ``screen_evidence`` for ``proposals.json`` (spec/engineer.md 3):
    ``{'rows': [{'rule', 'key', 'line', 'detail', 'source_line'}], 'more'}``; the words follow from ``key`` and
    ``PROMPT_VERSION`` (``key``: the row of ``RULES``, or the check for the rows of ``CHECK_WORDS``). ValueError for
    evidence that ``screen_evidence`` of this version did not give."""
    check = evidence['check']
    if check == 'policy' and not all(row['rewrite'] in _KEY_BY_REWRITE for row in evidence['detail']):
        raise ValueError('Screen evidence whose rewrite is not a row of %s' % PROMPT_VERSION)
    rows = [{'rule': row['rule'], 'key': _KEY_BY_REWRITE[row['rewrite']] if check == 'policy' else check,
             'line': row['line'], 'detail': row['detail'], 'source_line': row['source_line']}
            for row in evidence['detail']]
    return {'rows': rows, 'more': evidence['more']}


def _violations(text):
    return [violation.to_json() for violation in policy.check(text, version=POLICY_VERSION)]


def _maps_to(row, violations, lines, targets):
    return any(v['rule'] == row.rule and rule_key_for(v['rule'], v['detail'], _source_line(lines, v['line'])) in targets
               for v in violations)


def verify():
    """The zero-call self-check (spec/engineer.md 1.1 item 5): RuntimeError naming the first mismatch unless (i) the
    ten texts, rendered again from the bound modules, equal the texts of this process and their sha256 equal
    ``PINS``; (ii) under the frozen screen every legal example passes and every illegal one is rejected with its
    row's rule; (iii) the rows state every rule id of ``policy.RULES``; (iv) the violation of every illegal example
    maps back to its row (a parent row: to one of its rewrite rows). typed-v3 (T8): (i) holds for the five repair
    texts and ``REPAIR_PINS`` too. Returns ``{'version', 'pins'}`` for the manifest (pins keyed '<bench>.<purpose>';
    the ten, as before typed-v3)."""
    rules = _rules()
    if rules != RULES:
        raise RuntimeError('engineer_prompt: the rule table rendered now differs from the one of this process')
    texts = _render_all(rules)
    for key in sorted(set(texts) | set(PINS) | set(_TEXTS)):
        if key not in texts or texts[key] != _TEXTS.get(key):
            raise RuntimeError('engineer_prompt: the %s text rendered now differs from the one of this process'
                               % '.'.join(key))
        if _sha(texts[key]) != PINS.get(key):
            raise RuntimeError('engineer_prompt: the sha256 of the %s text differs from PINS' % '.'.join(key))
    repairs = _render_repairs(rules)
    for key in sorted(set(repairs) | set(REPAIR_PINS) | set(_REPAIR_TEXTS)):
        if key not in repairs or repairs[key] != _REPAIR_TEXTS.get(key):
            raise RuntimeError('engineer_prompt: the %s text rendered now differs from the one of this process'
                               % '.'.join(key))
        if _sha(repairs[key]) != REPAIR_PINS.get(key):
            raise RuntimeError('engineer_prompt: the sha256 of the %s text differs from REPAIR_PINS' % '.'.join(key))
    stated = {row.rule for row in rules}
    if stated != set(policy.RULES):
        raise RuntimeError('engineer_prompt: the rows state %s, the screen has %s'
                           % (sorted(stated), sorted(policy.RULES)))
    if len(_KEY_BY_REWRITE) != sum(row.rewrite is not None for row in rules):
        raise RuntimeError('engineer_prompt: two rows share one rewrite text')
    children = {}
    for row in rules:
        if row.parent is not None:
            children.setdefault(row.parent, set()).add(row.key)
    for row in rules:
        if _violations(row.legal):
            raise RuntimeError('engineer_prompt: the legal example of row %s is rejected by the screen' % row.key)
        violations = _violations(row.illegal)
        if not any(v['rule'] == row.rule for v in violations):
            raise RuntimeError('engineer_prompt: the illegal example of row %s is not rejected with rule %s'
                               % (row.key, row.rule))
        if not _maps_to(row, violations, _lines(row.illegal), children.get(row.key, {row.key})):
            raise RuntimeError('engineer_prompt: the illegal example of row %s does not map back to its row' % row.key)
    # the [import] row's own examples of a banned from-import member, and the legal form its rewrite names (coord-1)
    imported = _ROWS['import']
    if _violations(IMPORT_MEMBER_LEGAL):
        raise RuntimeError('engineer_prompt: the legal form of the import rewrite is rejected by the screen')
    for line in IMPORT_MEMBER_EXAMPLES:
        example = _program(top=[line])
        if not _maps_to(imported, _violations(example), _lines(example), {'import'}):
            raise RuntimeError('engineer_prompt: the screen does not reject %r with rule import' % line)
    return {'version': PROMPT_VERSION, 'pins': {'%s.%s' % key: PINS[key] for key in sorted(PINS)}}
