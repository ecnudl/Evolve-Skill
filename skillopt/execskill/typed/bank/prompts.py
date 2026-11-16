"""Fixed prompts of the item bank's method roles (typed-v3 bank): the derivation annotator and the question writer.
A role sees TRAINING-SIDE items only. Every request is one system and one user string (the frozen client sends
exactly these two messages); a repair is a NEW request that carries the earlier reply and the fixed check's reason.
Texts are constants: a change is a new bank version. The checker has no prompt here: it is the benchmark's own
solver request (``continual_eval.backends.solve``) with the hand card."""
from __future__ import annotations

import json

DERIVATION_FORMAT = (
    '"values": EVERY number read from the document that the answer is computed from, at most 40. For each one:\n'
    '  "name": a short identifier, for example v1.\n'
    '  "literal": the number exactly as it is printed in the document: digits, thousands commas and a decimal part '
    'as printed. No currency sign, percent sign, unit, minus sign or brackets.\n'
    '  "quote": 10 to 160 characters copied verbatim from ONE line of the document that contain the literal, with '
    'enough of the surrounding words or cells to show which number it is.\n'
    '  "kind": "data" for a reported quantity; "selector" for a year, a date part, a page, row, table or series '
    'number, a maturity such as the 2 in "2-year": any number that only identifies what to read.\n'
    '"steps" (optional, at most 20): named intermediate results, each {"name": a short identifier, "expression": '
    '...}. A step may use the values and the steps before it. Use a step for a quantity that is needed more than '
    'once, such as a mean or a growth rate.\n'
    '"answers": one entry for each number of the answer, in order. Each entry:\n'
    '  "expression": arithmetic over the names of the values and steps: + - * / and **, brackets, the functions '
    'abs(x), sqrt(x), ln(x), log10(x), exp(x), pow(x, y), round(x, n), and over two or more arguments: min, max, '
    'sum, mean, median, stdev_pop, stdev_samp, var_pop, var_samp, geomean, and corr(x1, ..., xn, y1, ..., yn) for '
    'the correlation of the first half of its arguments with the second half. Nothing else: no other function, no '
    'comparison, no condition, no assignment inside an expression. Plain numbers are only for constants that are '
    'NOT printed in the document (100, 12, a unit conversion such as 1000000); a number read from the document is '
    'always a value.\n'
    '  "decimals": the number of digits after the decimal point that the question asks for, 0 to 6; null when the '
    'exact value is wanted.\n'
    'A number printed with a minus sign or in brackets as a negative: give the literal without the sign and negate '
    'it in the expression. A unit word after a number ("million", "billion", "thousand") is not part of the '
    'literal: multiply in the expression when the question asks for another unit.')

# The coded mistakes a writer may name for an item's rubric (``oqa.rubric``); the generic ones -- rounding, sign,
# percent form, unit scale, operands exchanged, a value read but not computed with, format -- need no writer.
MISTAKE_LABELS = ('wrong_period', 'wrong_series', 'wrong_table_or_page', 'other_vintage', 'wrong_operation',
                  'missing_step')
MISTAKE_FORMAT = (
    '"mistakes" (optional, at most 3): derivations of WRONG answers that a careless reader of this document would '
    'plausibly reach. Each one: "label" (one of ' + ', '.join('"%s"' % label for label in MISTAKE_LABELS) + '), '
    '"text" (one sentence saying what was misread or miscomputed) and its own "values" and "answers" in the same '
    'format, with the same number of answers. Use other numbers of the document (the neighbouring period: '
    'wrong_period; the neighbouring line or a total instead of a part: wrong_series; a similar figure of another '
    'table or page: wrong_table_or_page; the preliminary instead of the revised figure or the reverse: '
    'other_vintage) or another computation on the same numbers (wrong_operation; an intermediate result given as '
    'the answer: missing_step). They only serve to name the mistake behind a wrong reply.')

TRACE_SYSTEM = (
    'You document how the reference answer to a question follows from a document. The document is the text of '
    'report pages (tables appear as rows of cells separated by "|"). You receive the document, the question and the '
    'reference answer, which is correct. Reply with one JSON object and nothing else.\n\n'
    'Write the derivation of the reference answer:\n\n' + DERIVATION_FORMAT + '\n\n'
    'The expressions, evaluated on the literals, must give the reference answer.\n\n' + MISTAKE_FORMAT + '\n\n'
    'If the reference answer is not a number or a list of numbers (a date, a name, a word), reply '
    '{"not_numeric": true}. If a number of the answer cannot be computed from numbers printed in the document, '
    'reply {"not_found": true}. Do not guess, and never choose numbers only because they happen to give the '
    'reference answer.')

REPAIR_NOTE = (
    '\n\nWhen the input holds "previous_reply" and "check_failure": a fixed program checked that earlier reply of '
    'yours and did not accept it, for the stated reason. Reply with the complete corrected JSON object%s.')
TRACE_REPAIR_END = (', or with {"not_found": true} when the reference answer cannot be derived from numbers '
                    'printed in the document')

REPAIR_TEXT = {
    'quote_not_in_document': 'the quote of value "%s" is not in the document verbatim (copy it from one line).',
    'literal_not_in_quote': 'the literal of value "%s" is not a whole number inside its quote.',
    'literal_unparsable': 'the literal "%s" is not a plain number as printed (digits, thousands commas, decimals).',
    'quote_shape': 'the quote of value "%s" must be 10 to 160 characters of one line.',
    'reference_not_reproduced': 'the expressions evaluate to %s, which is not the reference answer.',
    'unknown_name': 'an expression uses names that are not among the values: %s.',
    'expression': 'an expression could not be evaluated (%s).',
    'decimals': '"decimals" must be a whole number from 0 to 4 or null (got %s).',
    'constant_from_document': 'an expression contains the plain number %s, which is printed in the document: give '
                              'every number read from the document as a value with its quote.',
    'shape': 'the reply must be one JSON object with "values" (1 to 40), optional "steps" and "answers" (1 to 4)%s.',
    'value_name': 'the name "%s" is not usable: every value and step needs its own short identifier that is not a '
                  'function name.',
    'answer_shape': 'every step and answer needs an "expression"%s.',
    'not_terminating': 'with "decimals": null the exact value does not end (%s); give the decimals asked for.',
}

NEWQ_SYSTEM = (
    'You write new questions for a benchmark of numeric questions about pages of the U.S. Treasury Bulletin. You '
    'receive the document (the text of the pages; tables appear as rows of cells separated by "|"), example '
    'questions of the benchmark, one of which ("about_this_document") is about this same document, and the number '
    'of questions to write. Reply with one JSON object {"items": [...]} and nothing else.\n\n'
    'Each item is a question together with the derivation of its answer: "question" (the question text), "values" '
    'and "answers" (the derivation, in the format below). You never state the answer: a fixed program computes it '
    'from your derivation.\n\n'
    'Rules for the questions:\n'
    '- The answer is a number, or a short list of numbers, that follows by arithmetic from numbers printed in the '
    'document. No outside knowledge is needed or allowed.\n'
    '- Ask about quantities that the question "about_this_document" does NOT ask about, and let each of your '
    'questions rest on a different set of numbers.\n'
    '- Write the way the examples are written: the same register and length, the same way of naming the period, the '
    'series and the unit, the same way of asking for a rounding or an output format. Like the examples, do not '
    'always state a rounding, and ask for a bracketed list of two values in some questions.\n'
    '- Vary the computation over your questions: a value read off a table and converted to another unit, a '
    'difference, a sum or an average over several rows or periods, a ratio or a share, a percent change, a '
    'comparison of two series.\n'
    '- A question must have exactly one reading: name the table or series, the row and the period precisely, and '
    'state the unit of the answer.\n'
    '- Do not copy a number of the answer into the question.\n'
    '- When the input holds "brief": it describes the kinds of questions wanted and the mistakes solvers make on '
    'them; write questions of those kinds, and name the mistakes that apply.\n\n'
    'Derivation format:\n\n' + DERIVATION_FORMAT + '\n\n' + MISTAKE_FORMAT)

# The third arm (BANK-PILOT B24): the writer also receives the weaknesses a diagnosis found. NEWQ_SYSTEM stays as it
# is (the stored requests of the first two arms are identified by their text); this note is added for 'target' only.
NEWQ_TARGET_NOTE = (
    '\n\nThe input holds "weaknesses": habits by which a solver was seen to answer questions of this benchmark '
    'wrongly, each with an "id", a description and what a question must require to expose it. EVERY question you '
    'write targets one of them: a solver with that habit is likely to get it wrong, a careful solver gets it '
    'right, and the question still has exactly one reading (never make a question hard by leaving something '
    'unsaid). Use only weaknesses this document gives room for; spread your questions over different weaknesses '
    'when it does. Give in each item "targets": the id of the weakness, and give in "mistakes" the wrong '
    'derivation that this habit leads to on your question.')

# ---- the audit of a derivation (BANK-PILOT B23) --------------------------------------------------------------------
AUDIT_SYSTEM = (
    'You audit the derivation of an answer to a question about a document. The document is the text of report '
    'pages (tables appear as rows of cells separated by "|"). You receive the document, the question and the '
    'derivation: the values read from the document (each with its literal and a quote that shows where it is '
    'printed), optional named steps, and the expressions that give the answer ("decimals": the digits after the '
    'decimal point, null for the exact value). The derivation may be right or wrong. A fixed program has already '
    'checked that every quote is in the document, and it does the arithmetic: you check the MEANING.\n\n'
    'For every value: find its quote in the document and decide whether it is the number the question needs: the '
    'right table and series (the right line; not a total in place of a part, not a neighbouring line), the right '
    'period, date or column, the right page, and the right vintage where the document prints a preliminary and a '
    'revised figure.\n'
    'For the computation: decide whether the expressions compute what the question asks for: the operation, the '
    'order of the operands (which is subtracted from which, which is the base of a change or a share), a ratio '
    'against a percent, the set of lines or periods that is summed or averaged, the unit of the answer, the number '
    'of answers and their order, and the rounding the question states.\n\n'
    'Reply with one JSON object and nothing else: {"values": [{"name": ..., "right": true or false, "why": one '
    'short sentence}], "computation": {"right": true or false, "why": one short sentence}, "verdict": "accept" or '
    '"refuse"}. Give "accept" only when every value and the computation are right. When you cannot tell, give '
    '"refuse".')

# ---- the diagnosis of wrong replies (BANK-PILOT B24) ---------------------------------------------------------------
WEAKNESS_KINDS = ('locating', 'period', 'computation', 'unit_scale', 'form', 'no_answer', 'other')
DIAGNOSIS_SYSTEM = (
    'You analyse why a solver answered a question about report pages wrongly. You receive the document (tables '
    'appear as rows of cells separated by "|"), the question, the reference answer, which is correct, where there '
    'is one the derivation of the reference answer (the values read from the document with their quotes, and the '
    'expressions), and the solver\'s replies that were judged wrong; a reply that was judged right may be added. '
    'The judge compares the answer text with the reference: a right number in another written form is wrong too. '
    'Reply with one JSON object and nothing else:\n'
    '"cause": two or three sentences on what the solver did wrong in THIS case, as far as its reply and the '
    'document show it: which number it took in place of which, which step it left out or added, or how it wrote '
    'the answer. Try to reproduce its wrong number from the document. If the cause cannot be seen, say so.\n'
    '"kind": one of "locating" (another line, series, table or page), "period" (another period, date, column or '
    'vintage), "computation" (another operation, operands exchanged, a step too few or too many, an intermediate '
    'rounding), "unit_scale" (unit, thousands against millions, ratio against percent), "form" (the right number '
    'written another way: decimals, sign, percent sign, list form, no answer tag), "no_answer" (it gave no '
    'answer or said the document does not tell), "other".\n'
    '"weakness": ONE sentence that names the habit behind the mistake in general words, with no number, name or '
    'wording of this case, so that it would apply to other documents of the same kind.\n'
    '"test": ONE sentence saying what a new question on another document must require so that a solver with this '
    'habit gets it wrong and a careful solver gets it right.')
MAX_WEAKNESSES = 8
MERGE_SYSTEM = (
    'You receive diagnoses of wrong answers of one solver on numeric questions about report pages: for each case '
    'its "kind", the "weakness" (a habit in general words) and the "test" (what a new question must require to '
    'expose it). Merge them into at most %d DISTINCT weaknesses, the most frequent first. Reply with one JSON '
    'object and nothing else: {"weaknesses": [{"kind": ..., "weakness": one sentence, "test": one sentence, '
    '"cases": [the numbers of the cases it covers]}]}. Keep the kinds as given. Use general words only: no number, '
    'name or wording that belongs to a single case. Leave out a diagnosis that names no cause.' % MAX_WEAKNESSES)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def derivation_view(trace):
    """A normal-form derivation as a role sees it: names, literals, quotes and expressions, nothing computed."""
    view = {'values': [{'name': v['name'], 'literal': v['literal'], 'quote': v['quote']} for v in trace['values']],
            'answers': [{'expression': a['expression'], 'decimals': a['decimals']} for a in trace['answers']]}
    if trace.get('steps'):
        view['steps'] = [{'name': s['name'], 'expression': s['expression']} for s in trace['steps']]
    return view


def audit_request(context, question, trace):
    """(system, user) of the auditor: the document, the question and the derivation; never a computed answer."""
    return AUDIT_SYSTEM, dumps({'document': context, 'question': question, 'derivation': derivation_view(trace)})


def diagnosis_request(context, question, reference, trace, wrong_replies, right_reply=None):
    """(system, user) of the diagnostician for one failed REAL item of the shown side."""
    payload = {'document': context, 'question': question, 'reference_answer': reference,
               'wrong_replies': list(wrong_replies)}
    if trace is not None:
        payload['derivation_of_the_reference_answer'] = derivation_view(trace)
    if right_reply:
        payload['a_reply_judged_right'] = right_reply
    return DIAGNOSIS_SYSTEM, dumps(payload)


def merge_request(cases):
    """(system, user) of the merge of diagnoses; ``cases``: [{case, kind, weakness, test}] and nothing of an item."""
    return MERGE_SYSTEM, dumps({'cases': list(cases)})


def trace_request(question, reference, context, previous=None, failure=None):
    """(system, user) of the derivation annotator; ``previous`` and ``failure`` make it the one repair request."""
    payload = {'document': context, 'question': question, 'reference_answer': reference}
    system = TRACE_SYSTEM
    if previous is not None:
        payload.update(previous_reply=previous, check_failure=failure)
        system += REPAIR_NOTE % TRACE_REPAIR_END
    return system, dumps(payload)


def failure_text(reason, detail):
    """The sentence a repair request shows for a fixed check's refusal."""
    template = REPAIR_TEXT.get(reason)
    if template is None:
        return 'the reply was not a derivation in the required format (%s).' % reason
    return template % (detail,)


def newq_request(context, parent_question, examples, count, brief=None, weaknesses=None):
    """(system, user) of the question writer. ``brief``: the research brief's question kinds and mistakes (arm
    'brief'); ``weaknesses``: the diagnosed weaknesses [{id, kind, weakness, test}] (arm 'target')."""
    payload = {'document': context, 'about_this_document': parent_question, 'examples': list(examples), 'count': count}
    if brief:
        payload['brief'] = brief
    if weaknesses:
        payload['weaknesses'] = list(weaknesses)
    return NEWQ_SYSTEM + (NEWQ_TARGET_NOTE if weaknesses else ''), dumps(payload)


# ---- research (BANK-PILOT B8) --------------------------------------------------------------------------------------
# A generic description of the task family: what a researcher is told. Never an item of a benchmark.
FAMILY = {
    'officeqa': 'Numeric questions about pages of an official statistical report, the monthly bulletin of the U.S. '
                'Treasury: tables and text on federal receipts and outlays, public debt, interest rates, ownership '
                'of government securities, currency and international finance. The solver reads the supplied pages '
                '(tables rendered as rows of cells) and answers with a number computed from figures printed there.',
    'spreadsheetbench': 'Spreadsheet manipulation requests of the kind users post in Excel help forums: the solver '
                        'receives an instruction and a workbook and must write a Python program (openpyxl, pandas) '
                        'that produces the requested cells in an output workbook.',
}
RESEARCH_QUESTIONS = {
    'officeqa': (
        {'id': 'kinds', 'sources': ('arxiv', 'wikipedia'),
         'text': 'What kinds of numeric questions are asked about tables in financial and statistical reports, and '
                 'which computations do they need (reading a value, differences, growth rates and percent changes, '
                 'shares and ratios, sums and averages over rows or periods, comparisons across tables or documents)?'},
        {'id': 'mistakes', 'sources': ('arxiv',),
         'text': 'Which mistakes do language models make when they answer numeric questions over tables and '
                 'financial documents: the wrong row, column or period, unit and scale errors, sign conventions, '
                 'rounding and output format, percent against percentage points, slips in multi-step arithmetic?'},
        {'id': 'conventions', 'sources': ('wikipedia',),
         'text': 'Which reporting conventions must a reader of U.S. Treasury statistics know: the federal fiscal '
                 'year against the calendar year, amounts stated in millions or billions of dollars, preliminary and '
                 'revised figures, negative amounts printed in brackets, the difference between public debt, '
                 'marketable securities, receipts and outlays?'},
        {'id': 'writing', 'sources': ('arxiv',),
         'text': 'What makes a written question for table question answering valid: one unambiguous reading, an '
                 'answer derivable from the given table alone, no answer leaked in the question; and which flaws do '
                 'automatically generated questions commonly have?'},
    ),
    'spreadsheetbench': (
        {'id': 'kinds', 'sources': ('arxiv', 'stackexchange'),
         'text': 'What kinds of spreadsheet manipulation tasks do users ask for (formulas over ranges, lookups and '
                 'conditional aggregation, text and date clean-up, reshaping and sorting rows, cross-sheet '
                 'operations), and what distinguishes cell-level from sheet-level tasks?'},
        {'id': 'mistakes', 'sources': ('arxiv', 'stackexchange'),
         'text': 'Which mistakes do programs written by language models make when they edit workbooks with openpyxl '
                 'or pandas: hard-coded row ranges, header rows and empty rows, merged cells, formulas against '
                 'cached values, number and date types, writing to the wrong sheet or cell range?'},
        {'id': 'conventions', 'sources': ('stackexchange', 'wikipedia'),
         'text': 'Which spreadsheet conventions matter for a correct program: how dates and times are stored as '
                 'serial numbers, how a formula cell differs from its displayed value, absolute and relative '
                 'references, how empty cells and text numbers behave in formulas?'},
        {'id': 'writing', 'sources': ('arxiv',),
         'text': 'What makes a benchmark task for program synthesis or spreadsheet automation valid: an unambiguous '
                 'instruction, a checkable expected output, robustness to changed data; and which flaws do '
                 'automatically generated tasks commonly have?'},
    ),
}
SOURCE_NOTES = {'wikipedia': 'English Wikipedia: background facts and conventions; query = words of an article title',
                'arxiv': 'arXiv: research papers (benchmarks, error analyses); query = three to six key terms, all '
                         'of which must occur',
                'stackexchange': 'Stack Overflow and Super User: practical questions and answers; query = key terms'}
RESEARCH_COMMON = (
    'You are the researcher of a study that writes practice tasks for a solver model. You do not see any task of '
    'the study. Your reading must stay general: knowledge about the task family, its difficulties and its domain. '
    'Reply with one JSON object and nothing else.\n\n')
RESEARCH_PLAN = RESEARCH_COMMON + (
    'You receive the task family, one research question, the sources you may search and the queries already tried. '
    'Give at most 4 new search queries that are likely to find pages answering the research question: '
    '{"queries": [{"source": "a source name", "query": "the search words"}]}. Use short queries of key terms, not '
    'sentences. Do not search for a particular benchmark or dataset by name.')
RESEARCH_PICK = RESEARCH_COMMON + (
    'You receive the task family, one research question and search hits (id, title, snippet). Pick at most 3 hits '
    'whose pages are most likely to answer the research question: {"read": ["an id", ...]}.')
RESEARCH_CONCLUDE = RESEARCH_COMMON + (
    'You receive the task family, one research question and excerpts of the pages read (id, title, text). State '
    'what the pages establish that answers the research question, at most 8 findings: {"findings": [{"kind": '
    '"question_kind" | "difficulty" | "mistake" | "convention" | "item_writing", "statement": "one sentence, in your '
    'words, that a writer of practice tasks can act on", "quote": "15 to 500 characters copied character for '
    'character from the page text that support the statement", "source": "the page id"}]}. A finding without an '
    'exact quote of a shown page is discarded. If the pages establish nothing useful, reply {"findings": []}.')
RESEARCH_BRIEF = RESEARCH_COMMON + (
    'You receive the task family, numbered findings of the research (kind, statement, quote) and the labels of the '
    'mistakes a scoring rubric can encode. Write the brief for the writer of practice tasks: {"question_kinds": '
    '[{"name": "a short name", "description": "what such a question asks and which computation it needs", "from": '
    '[finding numbers]}], "mistakes": [{"label": "one of the given labels", "description": "how solvers make this '
    'mistake on this task family, so that a writer can build it into a task", "from": [finding numbers]}], '
    '"conventions": [{"text": "one convention of the domain a task should exercise", "from": [finding numbers]}]}. '
    'At most 8 entries per list. Every entry must rest on the findings it names in "from"; an entry without them is '
    'discarded. Do not invent facts beyond the findings.')


def research_plan(family, question, allowed, earlier):
    return RESEARCH_PLAN, dumps({'task_family': family, 'research_question': question,
                                 'sources': {name: SOURCE_NOTES[name] for name in allowed},
                                 'queries_already_tried': list(earlier)})


def research_pick(family, question, hits):
    return RESEARCH_PICK, dumps({'task_family': family, 'research_question': question, 'hits': hits})


def research_conclude(family, question, shown):
    return RESEARCH_CONCLUDE, dumps({'task_family': family, 'research_question': question, 'pages': shown})


def research_brief(family, findings, labels):
    return RESEARCH_BRIEF, dumps({'task_family': family, 'findings': findings, 'mistake_labels': list(labels)})


# ---- SpreadsheetBench reference programs (BANK-PILOT B10) ---------------------------------------------------------
SHEET_STYLES = {
    'a': 'Work with openpyxl alone, cell by cell.',
    'b': 'Do the computation with pandas (read the needed sheet into a DataFrame) and write the result cells with '
         'openpyxl.',
}
SHEET_REF_SYSTEM = (
    'You write the reference solution of a spreadsheet task as a Python program. You receive the instruction of the '
    'task, a view of the input workbook (its sheets with their sizes, their first and last rows; formulas are shown '
    'as text), the answer position, the current content of the answer cells in the input and the EXPECTED values of '
    'the answer cells. Reply with one complete Python program in one ```python block and nothing else.\n\n'
    'The program reads the workbook "input.xlsx" in the current directory and writes "output.xlsx" there. In the '
    'output the answer cells must hold the expected values; every other cell and sheet stays as it is in the '
    'input.\n\n'
    'Rules:\n'
    '- Compute every answer from the data of the workbook, as the instruction asks. Never write an expected value '
    'into the program as a constant and never copy the expected values: the program is also run on a changed copy '
    'of the workbook (other numbers, more or fewer rows) and must then give the answers of that copy.\n'
    '- Find the extent of the data from the workbook itself (the last used row, the header names); do not fix row '
    'counts or totals.\n'
    '- Write VALUES into the answer cells (numbers, texts, dates), not formulas, unless the instruction explicitly '
    'asks for a formula to be entered. The checker compares the values of the answer cells: numbers at two '
    'decimals, texts exactly (case and blanks count), dates by day.\n'
    '- Open the workbook with openpyxl.load_workbook("input.xlsx") and save it with wb.save("output.xlsx"), so that '
    'the other cells keep their content. pandas and numpy may be used for the computation. No other file, no '
    'network.\n'
    '- %s')
SHEET_REPAIR_END = ''
SHEET_FAILURES = {
    'no_program': 'the reply did not hold exactly one ```python block (%s).',
    'syntax': 'the program is not valid Python%s.',
    'contract': '%s.',
    'copied_answers': 'the program contains expected answer values as constants (%s); compute them from the data.',
    'run': 'the program did not produce output.xlsx in the sandbox (%s).',
    'mismatch': 'the answer cells of the output do not match the expected values (%s).',
    'unscorable': 'the output workbook could not be checked (%s): write plain values with openpyxl, no macros, no '
                  'links to other files, no volatile functions.',
}


def sheet_ref_request(instruction, answer_position, view, expected, style, previous=None, failure=None):
    """(system, user) of the reference-program writer; ``previous`` and ``failure`` make it a repair request."""
    payload = {'instruction': instruction, 'answer_position': answer_position, 'workbook': view,
               'expected_answer_cells': expected}
    system = SHEET_REF_SYSTEM % SHEET_STYLES[style]
    if previous is not None:
        payload.update(previous_reply=previous, check_failure=failure)
        system += REPAIR_NOTE % SHEET_REPAIR_END
    return system, dumps(payload)


# ---- SpreadsheetBench new tasks on a training workbook (BANK-PILOT B10) ---------------------------------------------
SHEET_CONTRACT = (
    'reads "input.xlsx" in the current directory, fills the answer cells with VALUES (numbers, texts, dates; not '
    'formulas) and writes "output.xlsx"; every other cell and sheet stays as it is. Compute from the data and find '
    'the extent of the data from the workbook itself. Open with openpyxl.load_workbook("input.xlsx") and save with '
    'wb.save("output.xlsx"); pandas and numpy may be used for the computation. No other file, no network.')
SHEET_TASK_KINDS = (
    'a value computed for every data row from other columns of that row',
    'a summary of the data: totals, counts or averages by a category or under a condition',
    'a lookup or matching between two columns or two sheets, or a cleaned-up version of a text or date column',
)
SHEET_TASK_SYSTEM = (
    'You write a new spreadsheet task for an existing workbook, of the kind users post in spreadsheet help forums, '
    'together with its reference solution. You receive a view of the workbook (its sheets with their sizes, first '
    'and last rows; formulas are shown as text), a request that was asked about this same workbook '
    '("about_this_workbook"), further example requests (for the register only) and the kind of task to write. '
    'Reply with exactly two blocks and nothing else: first a ```json block with {"instruction": ..., '
    '"answer_position": ...}, then a ```python block with the reference program.\n\n'
    'The task:\n'
    '- asks for something else than the request about this workbook does, and uses the data that are really in '
    'the workbook: name the sheet, the columns and the rows as a user would.\n'
    '- is written like the examples: a user describing what they need in plain words, with the cells or columns '
    'involved; one request of two to six sentences.\n'
    '- has ONE reading: say exactly which cells are to be filled and what each must hold, and how blanks, ties and '
    'text cells are to be treated where that matters.\n'
    '- "answer_position": the cells the solution fills, written like \'Sheet name\'!C2:C20: one rectangular range '
    'on an existing sheet, at most 500 cells, preferably cells that are empty in the workbook.\n'
    '- When the input holds "brief": it describes kinds of tasks and the mistakes solvers make on them; prefer a '
    'task on which such a mistake could be made.\n\n'
    'The reference program ' + SHEET_CONTRACT)
SHEET_SOLVE_SYSTEM = (
    'You solve a spreadsheet task with a Python program. You receive the instruction, a view of the workbook (its '
    'sheets with their sizes, first and last rows; formulas are shown as text) and the answer position. Reply with '
    'one complete Python program in one ```python block and nothing else. The program ' + SHEET_CONTRACT)


def sheet_task_request(view, parent_instruction, examples, kind, brief=None):
    payload = {'workbook': view, 'about_this_workbook': parent_instruction, 'examples': list(examples), 'kind': kind}
    if brief:
        payload['brief'] = brief
    return SHEET_TASK_SYSTEM, dumps(payload)


def sheet_solve_request(instruction, answer_position, view):
    return SHEET_SOLVE_SYSTEM, dumps({'instruction': instruction, 'answer_position': answer_position, 'workbook': view})
