"""SpreadsheetBench part of the item bank: reference programs for the training items (BANK-PILOT B10).

    ref     per parent and style (``prompts.SHEET_STYLES``: two independent ways of writing it) a reference program
            from the program writer, who sees the instruction, a view of the input workbook and the EXPECTED answer
            cells (training side). Fixed code screens it (one program, valid Python, the input/output contract, no
            expected value copied in as a constant), runs it in the benchmark's own sandbox and scores its output
            against the parent's expected workbook with the benchmark's own scorer. ANCHORED = the scorer passes.
            Up to SHEET_ATTEMPTS requests; a repair request carries the earlier reply and the failed check.
    twins   fixed code and the sandbox, no model: for a parent with TWO anchored programs (one alone is not enough),
            copies of its workbook with every numeric data cell multiplied by one factor
            (``sheet.scale_workbook``); the expected workbook of a twin is the output of the first program on the
            changed copy. Kept only when the answer cells differ from the parent's and are not all empty, the
            second anchored program gives the same answer cells, and the twin passes the reference qualification
            (its expected workbook scored against itself twice by the benchmark's scorer, as the 91 real items
            were).
    newtask a NEW instruction on a parent's workbook from the task writer (the workbook view, the parent's
            instruction as the example about this workbook, the kind of task wanted, optionally the research brief),
            with its answer position and its reference program. A SECOND program is written by another request that
            sees only the new instruction, the workbook view and the answer position. Kept when both programs run,
            the answer cells are filled and differ from the input's, the two outputs agree on the answer cells, and
            the item passes the reference qualification twice. No expected workbook exists before the programs
            run, so agreement of two independently written programs stands in for the anchor.
    report  how many parents have one and two anchored programs, the reasons of the others, attempts used, twins,
            new tasks.

An anchored program is the parent's code rubric (it computes the expected cells) and the precondition of a data
twin or of a new instruction on the same workbook: both need an expected workbook computed by code.

The sandbox, the scorer and the machine-wide memory lock come in as ``tools`` (``run(program, input_path) ->
case``, ``score(item, program, cases, tag) -> {status, reason}``, ``extract(reply) -> {status, code, reason}``):
the real ones are built by ``scripts/run_bank.py`` from the bound machinery snapshot, so a program is run and
judged exactly as a solver's program is. Each run and each scoring holds the memory lock exclusively: this stage
must not run while a chain is reading or learning sheet or ALFWorld units on the same machine.
"""
from __future__ import annotations

import base64
import json
import re
import tempfile
from pathlib import Path

from .. import units
from . import prompts, report, sheet
from .env import read_object, text_sha256
from .oqa_build import safe_id

BENCH = 'spreadsheetbench'
SCORING_EXCEPTION = 'native_scoring_exception'   # mount._sheet_score: an exception inside the scoring, nothing stored
SHEET_ATTEMPTS = 3
TWINS_PER_PARENT = 2
EXPECTED_SHOWN = sheet.EXPECTED_SHOWN


def _expected_shown(expected):
    return [{'sheet': name, 'cell': cell, 'value': sheet.shown(value)} for name, cell, value in expected[:EXPECTED_SHOWN]]


def _label(case, expected_path, answer_position):
    """The rubric's label of a wrong output, from the produced workbook bytes (a scratch file, removed again)."""
    if not isinstance(case.get('output_base64'), str):
        return 'missing_output'
    with tempfile.TemporaryDirectory(prefix='bank-sheet-') as folder:
        path = Path(folder) / 'output.xlsx'
        path.write_bytes(base64.b64decode(case['output_base64']))
        try:
            return sheet.label_output(str(path), expected_path, answer_position)
        except Exception:
            return 'all_wrong'


def reference_program(env, tools, item, style):
    """The write-once record of one parent and style: status anchored / dropped / no_reply, the attempts, and for an
    anchored program its source (also written beside the record as ``<parent>-<style>.py``)."""
    parent, public = item['task_id'], item['public']
    input_path, expected_path, position = public['input_files'][0], item['private']['test_files'][0], public['answer_position']

    def compute():
        view = sheet.workbook_view(input_path, position)
        expected = sheet.answer_cells(expected_path, position)
        known = sheet.workbook_values(input_path)
        attempts, previous, failure = [], None, None
        for attempt in range(1, SHEET_ATTEMPTS + 1):
            system, user = prompts.sheet_ref_request(public['instruction'], position, view, _expected_shown(expected),
                                                     style, previous, failure)
            tag = '%s-%s-a%d' % (safe_id(parent), style, attempt)
            sent = env.call(BENCH + '/ref', tag, system, user)
            row = {'attempt': attempt, 'request_sha256': sent['request_sha256'], 'failure': sent['failure']}
            attempts.append(row)
            if sent['reply'] is None:
                if (sent['failure'] or '').startswith('infrastructure:'):
                    raise RuntimeError('infrastructure: ' + str(sent['failure']))
                return {'parent': parent, 'style': style, 'status': 'no_reply', 'reason': sent['failure'], 'attempts': attempts}
            previous = sent['reply']
            extracted = tools['extract'](sent['reply'])
            if extracted.get('status') != 'available':
                row['check'] = 'no_program'
                failure = prompts.SHEET_FAILURES['no_program'] % extracted.get('reason')
                continue
            program = extracted['code']
            try:
                sheet.screen_program(program, public['instruction'], [value for _, _, value in expected], known)
            except sheet.Drop as refused:
                row['check'], row['detail'] = refused.reason, refused.detail[:200]
                failure = prompts.SHEET_FAILURES[refused.reason] % refused.detail[:200]
                continue
            case = tools['run'](program, input_path)
            if case.get('status') != 'available':
                row['check'], row['detail'] = 'run', str(case.get('reason') or case.get('status'))[:120]
                if 'unavailable' in row['detail'] or 'cleanup' in row['detail']:
                    raise RuntimeError('sandbox: ' + row['detail'])               # the machine, not the program
                failure = prompts.SHEET_FAILURES['run'] % row['detail']
                continue
            score = tools['score'](item, program, [case], tag)
            if score.get('status') == 'pass':
                row['check'] = 'anchored'
                units.write_json(env.path(BENCH, 'ref', '%s-%s.program.json' % (safe_id(parent), style)),
                                 {'parent': parent, 'style': style, 'program': program,
                                  'program_sha256': text_sha256(program)})
                return {'parent': parent, 'style': style, 'status': 'anchored', 'reason': None, 'attempts': attempts,
                        'program_sha256': text_sha256(program), 'answer_cells': len(expected)}
            if score.get('status') != 'fail':
                # The scorer keeps an unknown verdict and answers the same request with it again, so "run the stage
                # again" would never end: an unknown is a failed check with its reason. Only an exception inside the
                # scoring (no stored verdict) is left open.
                reason = str(score.get('reason'))[:120]
                if reason.startswith(SCORING_EXCEPTION):
                    raise RuntimeError('scorer: ' + reason)
                row['check'], row['detail'] = 'unscorable', reason
                failure = prompts.SHEET_FAILURES['unscorable'] % reason
                continue
            label = _label(case, expected_path, position)
            row['check'], row['detail'] = 'mismatch', '%s; %s' % (str(score.get('reason'))[:80], label)
            failure = prompts.SHEET_FAILURES['mismatch'] % row['detail']
        return {'parent': parent, 'style': style, 'status': 'dropped', 'reason': attempts[-1].get('check'),
                'attempts': attempts}

    return env.once((BENCH, 'ref', '%s-%s.json' % (safe_id(parent), style)), compute)


def _open(failed):
    """The word a stage reports for a task that ended without a verdict: 'infrastructure', 'sandbox', 'scorer' for
    the machine-side failures raised as RuntimeError, 'error: <type>' for anything else (a workbook the fixed code
    cannot read, no scoring position left): the stage goes on with the other tasks either way."""
    if isinstance(failed, RuntimeError) and str(failed).split(':')[0] in ('infrastructure', 'sandbox', 'scorer'):
        return str(failed).split(':')[0]
    return 'error: ' + type(failed).__name__


def stage_ref(env, tools, items, styles):
    tasks = [(item, style) for item in items for style in styles]

    def work(task):
        item, style = task
        try:
            return '%s: %s' % (style, reference_program(env, tools, item, style)['status'])
        except units.Stop:
            raise
        except Exception as failed:
            return '%s: %s' % (style, _open(failed))
    return report.tally(env.fan(tasks, work, label='reference programs'))


# ---- data twins ----------------------------------------------------------------------------------------------------
def anchored_programs(env, parent):
    """{style: program source} of a parent's anchored reference programs."""
    folder, found = env.path(BENCH, 'ref'), {}
    for path in sorted(folder.glob(safe_id(parent) + '-*.program.json')) if folder.is_dir() else []:
        row = units.read_json(path)
        found[row['style']] = row['program']
    return found


def _written(case, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(case['output_base64']))
    return str(path)


def _file_sha256(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualify(tools, task, expected_path, made):
    """(qualified, detail): the reference qualification of a made item -- its expected workbook submitted as the
    answer and scored twice by the benchmark's scorer, both passes needed (as for the 91 real items). An unknown
    verdict disqualifies with its reason (the scorer would repeat it); an exception inside the scoring raises
    RuntimeError and leaves the item without a verdict."""
    reference = {'status': 'available', 'output_base64': base64.b64encode(Path(expected_path).read_bytes()).decode()}
    scores = [tools['score'](task, None, [reference], '%s-q%d' % (safe_id(made), scoring)) for scoring in (1, 2)]
    reasons = [str(score.get('reason'))[:100] for score in scores if score.get('status') != 'pass']
    if any(reason.startswith(SCORING_EXCEPTION) for reason in reasons):
        raise RuntimeError('scorer: ' + '; '.join(reasons)[:160])
    return not reasons, '; '.join(reasons)[:200]


def make_data_twins(env, tools, item, side):
    """[(twin id or None, drop reason or None)] for one parent. A machine-side failure (sandbox unavailable, an
    unknown score) raises RuntimeError and writes nothing for that twin."""
    parent, public = item['task_id'], item['public']
    programs = anchored_programs(env, parent)
    if not programs:
        return []
    if len(programs) < 2:
        # one program that reproduces the parent's workbook may do so by a wrong rule that happens to fit its
        # numbers (review 2026-11-13: A*B/12 for A+B at 20 and 30); a twin's answer needs two that agree
        return [(None, 'one_program_only')] * TWINS_PER_PARENT
    styles = sorted(programs)
    position, parent_expected = public['answer_position'], item['private']['test_files'][0]
    out = []
    for number, factor in enumerate(sheet.SCALE_FACTORS[:TWINS_PER_PARENT], 1):
        made = '%s~d%d' % (parent, number)
        if env.exists(BENCH, 'records', safe_id(made) + '.json'):
            out.append((made, None))
            continue
        folder = env.path(BENCH, 'files', safe_id(made))
        folder.mkdir(parents=True, exist_ok=True)
        input_path, expected_path = str(folder / 'input.xlsx'), str(folder / 'expected.xlsx')
        try:
            changed = sheet.scale_workbook(public['input_files'][0], input_path, factor, position, public['instruction'])
        except sheet.Drop as refused:
            out.append((None, refused.reason))
            continue
        case, _ = _run(tools, programs[styles[0]], input_path)      # a machine-side failure raises: no verdict
        if case is None:
            out.append((None, 'program_fails_on_twin'))
            continue
        _written(case, expected_path)
        verdict = sheet.compare_cells(expected_path, parent_expected, position)
        if verdict != 'different':
            out.append((None, 'answer_unchanged' if verdict == 'same' else 'answer_without_values'))
            continue
        if sheet.blank_answer(expected_path, position):
            out.append((None, 'answer_blank'))
            continue
        other, _ = _run(tools, programs[styles[1]], input_path)     # the same rule for the second program
        if other is None:
            out.append((None, 'second_program_fails_on_twin'))
            continue
        agreed = sheet.compare_cells(_written(other, folder / 'second.xlsx'), expected_path, position)
        if agreed != 'same':
            out.append((None, 'programs_disagree'))
            continue
        twin = {'benchmark': BENCH, 'task_id': made, 'family_id': item.get('family_id'), 'part': 'bank',
                'public': {'instruction': public['instruction'], 'input_files': [input_path], 'answer_position': position},
                'private': {'answer_position': position, 'test_files': [expected_path],
                            'asset_sha256': {input_path: _file_sha256(input_path), expected_path: _file_sha256(expected_path)},
                            'source_sha256': item['private'].get('source_sha256')}}
        if not qualify(tools, twin, expected_path, made)[0]:
            out.append((None, 'not_qualified'))
            continue
        units.write_json(env.path(BENCH, 'items', safe_id(made) + '.json'), twin)
        units.write_json(env.path(BENCH, 'records', safe_id(made) + '.json'), {
            'item': made, 'kind': 'data_twin', 'parent': parent, 'side': side, 'factor': str(factor),
            'cells_changed': changed, 'program_style': styles[0], 'second_program': styles[1],
            'programs_agree': True,
            'program_sha256': text_sha256(programs[styles[0]])})
        out.append((made, None))
    return out


def stage_twins(env, tools, items, sides):
    made, drops, open_ = [], [], []
    for item in items:
        try:
            for item_id, reason in make_data_twins(env, tools, item, sides[item['task_id']]):
                (made if item_id else drops).append(item_id or reason)
        except units.Stop:
            raise
        except Exception as failed:
            open_.append(_open(failed))
    return {'made': len(made), 'dropped': report.tally(drops), 'parents_without_a_verdict': len(open_),
            'without_a_verdict': report.tally(open_)}


# ---- new tasks -----------------------------------------------------------------------------------------------------
MAX_ANSWER_CELLS = 500
INSTRUCTION_CHARS = (80, 1500)
PYTHON_BLOCK = re.compile(r'```(?:python|py)[ \t]*\n.*?```', re.S)


def _task_reply(reply, extract):
    """(instruction, answer position, program) of a task writer's reply, or ``sheet.Drop``. Tolerant reading, strict
    use: the program is what the benchmark's own extraction finds in the reply (one python block); the instruction
    and the answer position come from the JSON object in the rest of the reply, fenced or not."""
    if not PYTHON_BLOCK.search(reply or ''):   # the benchmark's extraction takes an unfenced reply whole as code
        raise sheet.Drop('reply_shape', 'no python block')
    extracted = extract(reply)
    if extracted.get('status') != 'available':
        raise sheet.Drop('reply_shape', 'program: %s' % extracted.get('reason'))
    value = read_object(PYTHON_BLOCK.sub('', reply or ''))
    instruction, position = (value.get('instruction'), value.get('answer_position')) if isinstance(value, dict) else (None, None)
    if not (isinstance(instruction, str) and INSTRUCTION_CHARS[0] <= len(instruction.strip()) <= INSTRUCTION_CHARS[1]
            and isinstance(position, str) and position.strip()):
        raise sheet.Drop('reply_shape', 'instruction or position')
    return instruction.strip(), position.strip(), extracted['code']


def _run(tools, program, input_path):
    case = tools['run'](program, input_path)
    if case.get('status') != 'available':
        reason = str(case.get('reason') or case.get('status'))
        if 'unavailable' in reason or 'cleanup' in reason:
            raise RuntimeError('sandbox: ' + reason[:100])
        return None, reason[:100]
    return case, None


def new_task(env, tools, item, side, arm, number, kind, examples, brief):
    """The write-once record of one new task on a parent's workbook: status made / dropped (+ reason). ``arm``:
    'plain' (no brief; ids ``<parent>~tp<n>``) or 'brief' (the research brief in the request; ``<parent>~tb<n>``)."""
    from . import oqa
    assert (arm == 'brief') == bool(brief), 'The brief arm, and only it, carries the brief'
    parent, public = item['task_id'], item['public']
    made = '%s~t%s%d' % (parent, arm[0], number)
    name = '%s-t%s%d' % (safe_id(parent), arm[0], number)

    def compute():
        input_path = public['input_files'][0]
        base = {'item': made, 'parent': parent, 'side': side, 'arm': arm, 'kind_wanted': kind}
        import openpyxl
        book = openpyxl.load_workbook(input_path, read_only=True)
        sheetnames = list(book.sheetnames)
        book.close()
        view = sheet.workbook_view(input_path, public['answer_position'])
        # the writer chooses its own answer cells: the parent's answer cells are not part of what it is shown
        view = {key: value for key, value in view.items() if not key.startswith('answer_')}
        sent = env.call(BENCH + '/newtask', name + '-write',
                        *prompts.sheet_task_request(view, public['instruction'], examples, kind, brief))
        if sent['reply'] is None:
            if (sent['failure'] or '').startswith('infrastructure:'):
                raise RuntimeError('infrastructure: ' + str(sent['failure']))
            return {**base, 'status': 'dropped', 'reason': 'no_reply'}
        try:
            instruction, position, program = _task_reply(sent['reply'], tools['extract'])
            cells = sum(len(group) for _, group in sheet.targets(position, sheetnames))
            if not 1 <= cells <= MAX_ANSWER_CELLS:
                raise sheet.Drop('answer_position', cells)
            if oqa.jaccard(instruction, public['instruction']) >= oqa.REPEAT_JACCARD:
                raise sheet.Drop('repeats_parent')
            sheet.program_constants(program)
            if 'input.xlsx' not in program or 'output.xlsx' not in program:
                raise sheet.Drop('contract')
        except sheet.Drop as refused:
            return {**base, 'status': 'dropped', 'reason': refused.reason, 'detail': refused.detail[:120]}
        except Exception as refused:  # the scorer's grammar refused the position
            return {**base, 'status': 'dropped', 'reason': 'answer_position', 'detail': type(refused).__name__}
        folder = env.path(BENCH, 'files', safe_id(made))
        folder.mkdir(parents=True, exist_ok=True)
        expected_path = str(folder / 'expected.xlsx')
        case, failure = _run(tools, program, input_path)
        if case is None:
            return {**base, 'status': 'dropped', 'reason': 'program_fails', 'detail': failure}
        _written(case, expected_path)
        filled = sheet.compare_cells(expected_path, input_path, position)
        if filled != 'different':
            return {**base, 'status': 'dropped', 'reason': 'nothing_computed' if filled == 'same' else 'answer_without_values'}
        if sheet.blank_answer(expected_path, position):
            # two programs that both CLEAR the answer cells differ from the input, agree with each other and qualify
            return {**base, 'status': 'dropped', 'reason': 'answer_blank'}
        second = env.call(BENCH + '/newtask', name + '-solve',
                          *prompts.sheet_solve_request(instruction, position, sheet.workbook_view(input_path, position)))
        if second['reply'] is None:
            if (second['failure'] or '').startswith('infrastructure:'):
                raise RuntimeError('infrastructure: ' + str(second['failure']))
            return {**base, 'status': 'dropped', 'reason': 'no_second_program'}
        extracted = tools['extract'](second['reply'])
        if extracted.get('status') != 'available':
            return {**base, 'status': 'dropped', 'reason': 'no_second_program'}
        other, failure = _run(tools, extracted['code'], input_path)
        if other is None:
            return {**base, 'status': 'dropped', 'reason': 'second_program_fails', 'detail': failure}
        if sheet.compare_cells(_written(other, folder / 'second.xlsx'), expected_path, position) != 'same':
            try:
                label = sheet.label_output(str(folder / 'second.xlsx'), expected_path, position)
            except Exception:
                label = 'unlabelled'
            return {**base, 'status': 'dropped', 'reason': 'programs_disagree', 'detail': label}
        task = {'benchmark': BENCH, 'task_id': made, 'family_id': item.get('family_id'), 'part': 'bank',   # B11: the parent's
                'public': {'instruction': instruction, 'input_files': [input_path], 'answer_position': position},
                'private': {'answer_position': position, 'test_files': [expected_path],
                            'asset_sha256': {input_path: _file_sha256(input_path), expected_path: _file_sha256(expected_path)},
                            'source_sha256': item['private'].get('source_sha256')}}
        qualified, detail = qualify(tools, task, expected_path, made)
        if not qualified:
            return {**base, 'status': 'dropped', 'reason': 'not_qualified', 'detail': detail}
        units.write_json(env.path(BENCH, 'items', safe_id(made) + '.json'), task)
        units.write_json(env.path(BENCH, 'records', safe_id(made) + '.json'), {
            'item': made, 'kind': 'new_task', 'parent': parent, 'side': side, 'arm': arm, 'kind_wanted': kind,
            'answer_cells': cells, 'program': program,
            'program_sha256': text_sha256(program), 'second_program_sha256': text_sha256(extracted['code'])})
        return {**base, 'status': 'made', 'reason': None, 'answer_cells': cells}

    return env.once((BENCH, 'newtask', safe_id(made) + '.json'), compute)


def stage_newtask(env, tools, items, sides, arms, per_parent, brief):
    """New tasks for the given parents: per arm ``per_parent`` tasks each, of the registered kinds in turn. Example
    requests: two real instructions of other parents on the SAME side (a seeded draw), so a task kept for judging
    never shows a writer an instruction of the shown side's judging counterpart and the reverse."""
    import random
    from . import SEED
    tasks = []
    for item in items:
        others = sorted(other['public']['instruction'][:600] for other in items
                        if sides[other['task_id']] == sides[item['task_id']] and other['task_id'] != item['task_id'])
        examples = random.Random('%d:examples:%s' % (SEED, item['task_id'])).sample(others, min(2, len(others)))
        tasks += [(item, arm, number, prompts.SHEET_TASK_KINDS[(number - 1) % len(prompts.SHEET_TASK_KINDS)], examples)
                  for arm in arms for number in range(1, per_parent + 1)]

    def work(task):
        item, arm, number, kind, examples = task
        try:
            row = new_task(env, tools, item, sides[item['task_id']], arm, number, kind, examples,
                           brief if arm == 'brief' else None)
            return '%s: %s' % (arm, 'made' if row['status'] == 'made' else 'dropped, ' + str(row['reason']))
        except units.Stop:
            raise
        except Exception as failed:
            return '%s: %s' % (arm, _open(failed))
    return report.tally(env.fan(tasks, work, label='new tasks'))


def _twin_report(env, sides):
    folder = env.path(BENCH, 'records')
    rows = [units.read_json(path) for path in sorted(folder.glob('*.json'))] if folder.is_dir() else []
    rows = [row for row in rows if row['kind'] == 'data_twin']
    return {'made': len(rows), 'parents': len({row['parent'] for row in rows}),
            'by_side': report.tally(row['side'] for row in rows),
            'checked_by_a_second_program': sum(row['programs_agree'] is True for row in rows)}


def _task_report(env):
    folder = env.path(BENCH, 'newtask')
    rows = [units.read_json(path) for path in sorted(folder.glob('*.json'))] if folder.is_dir() else []
    out = {}
    for arm in sorted({row['arm'] for row in rows}):
        mine = [row for row in rows if row['arm'] == arm]
        made = [row for row in mine if row['status'] == 'made']
        out[arm] = {'asked': len(mine), 'made': len(made), 'parents_with_a_new_task': len({row['parent'] for row in made}),
                    'made_by_side': report.tally(row['side'] for row in made),
                    'drop_reasons': report.tally(row['reason'] for row in mine if row['status'] != 'made'),
                    'made_by_kind': report.tally(row['kind_wanted'][:40] for row in made)}
    return out


def build_report(env, items, sides):
    folder = env.path(BENCH, 'ref')
    rows = [units.read_json(path) for path in sorted(folder.glob('*.json'))
            if not path.name.endswith('.program.json')] if folder.is_dir() else []
    anchored = {}
    for row in rows:
        if row['status'] == 'anchored':
            anchored.setdefault(row['parent'], []).append(row['style'])
    styles = sorted({row['style'] for row in rows})
    return {
        'bench': BENCH, 'parents': len(items), 'records': len(rows),
        'by_style': {style: report.tally(row['status'] for row in rows if row['style'] == style) for style in styles},
        'drop_reasons': report.tally(row['reason'] for row in rows if row['status'] != 'anchored'),
        'attempts_of_anchored': report.tally(len(row['attempts']) for row in rows if row['status'] == 'anchored'),
        'parents_with_a_program': len(anchored),
        'parents_with_two_programs': sum(len(found) >= 2 for found in anchored.values()),
        'parents_with_a_program_by_side': report.tally(sides[parent] for parent in anchored),
        'failed_checks': report.tally(attempt.get('check') for row in rows for attempt in row['attempts']
                                      if attempt.get('check') not in (None, 'anchored')),
        'data_twins': _twin_report(env, sides),
        'new_tasks': _task_report(env),
        'ledger': {key: env.ledger.state.get(key) for key in ('cap', 'charged', 'reported', 'sends', 'stopped',
                                                              'stop_reason')},
    }
