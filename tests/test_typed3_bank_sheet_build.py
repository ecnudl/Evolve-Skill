"""typed-v3 item bank, sheet reference programs (bank/sheet_build.py) with a fake writer, a local stand-in for the
sandbox (the fake program text is trusted test code) and the benchmark's cached-value comparison as the scorer."""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import openpyxl
import pytest

from skillopt.continual_eval import spreadsheet_compat
from skillopt.execskill import code_delivery
from skillopt.execskill.typed import units
from skillopt.execskill.typed.bank import env as bank_env, prompts, sheet_build

GOOD = ('import openpyxl\nwb = openpyxl.load_workbook("input.xlsx")\nws = wb["Data"]\n'
        'for r in range(2, ws.max_row + 1):\n    ws.cell(r, 3).value = ws.cell(r, 1).value * ws.cell(r, 2).value\n'
        'wb.save("output.xlsx")\n')
OFF_BY_ONE = GOOD.replace('ws.cell(r, 3).value =', 'ws.cell(r + 1, 3).value =')
COPIED = GOOD.replace('ws.cell(r, 1).value * ws.cell(r, 2).value', '[1250, 4125][r - 2]')
CRASH = 'import openpyxl\nraise SystemExit(3)\n# input.xlsx output.xlsx\n'


@pytest.fixture
def root():
    base = Path('/tmp/typed3-neutral')
    base.mkdir(exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='sheetb-', dir=base))
    yield made
    shutil.rmtree(made, ignore_errors=True)


def workbook(path, rows):
    book = openpyxl.Workbook()
    book.active.title = 'Data'
    for row in rows:
        book.active.append(row)
    book.save(path)
    return str(path)


def make_item(root, name):
    folder = root / 'files' / name
    folder.mkdir(parents=True)
    rows = [['Units', 'Price', 'Total'], [50, 25, None], [75, 55, None]]
    want = [['Units', 'Price', 'Total'], [50, 25, 1250], [75, 55, 4125]]
    return {'benchmark': 'spreadsheetbench', 'task_id': name, 'family_id': 'exact-' + name, 'part': 'train',
            'public': {'instruction': 'Fill column C with Units times Price for every data row.',
                       'input_files': [workbook(folder / 'in.xlsx', rows)], 'answer_position': 'C2:C3'},
            'private': {'answer_position': 'C2:C3', 'test_files': [workbook(folder / 'want.xlsx', want)]}}


def run(program, input_path):
    with tempfile.TemporaryDirectory(prefix='run-', dir='/tmp/typed3-neutral') as folder:
        shutil.copy(input_path, Path(folder) / 'input.xlsx')
        done = subprocess.run([sys.executable, '-I', '-c', program], cwd=folder, capture_output=True, timeout=60)
        out = Path(folder) / 'output.xlsx'
        if done.returncode != 0 or not out.exists():
            return {'status': 'missing_output', 'reason': 'native_exception:SystemExit' if done.returncode else 'missing_output'}
        return {'status': 'available', 'output_base64': base64.b64encode(out.read_bytes()).decode()}


def score(item, program, cases, tag):
    with tempfile.TemporaryDirectory(prefix='score-', dir='/tmp/typed3-neutral') as folder:
        out = Path(folder) / 'output.xlsx'
        out.write_bytes(base64.b64decode(cases[0]['output_base64']))
        result = spreadsheet_compat.evaluate(str(out), item['private']['test_files'][0], None, item['public']['answer_position'])
    return {'status': {'passed': 'pass', 'failed': 'fail'}.get(result['status'], 'unknown'), 'reason': result['reason']}


class Fake:
    max_tokens = 2048

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def call(self, system, user):
        self.calls.append((system, json.loads(user)))
        return {'ok': True, 'response': self.answer(system, json.loads(user)), 'finish_reason': 'stop', 'error_type': None,
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}


TOOLS = {'run': run, 'score': score, 'extract': code_delivery.extract_python}


def test_reference_programs_anchor_after_repairs(root):
    two = '```python\nprint(1)\n```\ntext\n```python\nprint(2)\n```'
    replies = {'T1': iter([two, '```python\n' + COPIED + '```', '```python\n' + GOOD + '```']),
               'T2': iter(['```python\n' + OFF_BY_ONE + '```', '```python\n' + CRASH + '```', '```python\n' + OFF_BY_ONE + '```'])}

    def writer(system, payload):
        assert payload['expected_answer_cells'][0] == {'sheet': 'Data', 'cell': 'C2', 'value': 1250}
        assert payload['workbook']['sheets'][0]['first_rows'][1] == [50, 25, None] and prompts.SHEET_STYLES['a'] in system
        name = 'T1' if len(writer.seen.setdefault('T1', [])) < 3 and writer.turn == 'T1' else 'T2'
        writer.seen.setdefault(name, []).append(payload.get('check_failure'))
        return next(replies[name])
    writer.seen, writer.turn = {}, 'T1'
    role = Fake(writer)
    env = bank_env.BankEnv(root, units.Ledger(root / 'ledger.json', 5_000_000), {'role': role}, width=1)
    first = sheet_build.reference_program(env, TOOLS, make_item(root, 'T1'), 'a')
    assert first['status'] == 'anchored' and [a.get('check') for a in first['attempts']] == ['no_program', 'copied_answers', 'anchored']
    assert writer.seen['T1'][0] is None and 'exactly one' in writer.seen['T1'][1] and '1250' in writer.seen['T1'][2]
    stored = env.read('spreadsheetbench', 'ref', 'T1-a.program.json')
    assert stored['program'] == GOOD and stored['program_sha256'] == first['program_sha256']
    writer.turn = 'T2'
    second = sheet_build.reference_program(env, TOOLS, make_item(root, 'T2'), 'a')
    assert second['status'] == 'dropped' and [a.get('check') for a in second['attempts']] == ['mismatch', 'run', 'mismatch']
    assert 'shifted_rows' in second['attempts'][0]['detail'] and 'SystemExit' in second['attempts'][1]['detail']
    assert 'shifted_rows' in writer.seen['T2'][1] and not (root / 'spreadsheetbench' / 'ref' / 'T2-a.program.json').exists()
    calls = len(role.calls)
    assert sheet_build.reference_program(env, TOOLS, make_item(root / 'again', 'T1'), 'a') == first and len(role.calls) == calls
    summary = sheet_build.build_report(env, [{'task_id': 'T1'}, {'task_id': 'T2'}], {'T1': 'shown', 'T2': 'judge'})
    assert summary['by_style'] == {'a': {'anchored': 1, 'dropped': 1}} and summary['parents_with_a_program'] == 1
    assert summary['failed_checks'] == {'mismatch': 2, 'copied_answers': 1, 'no_program': 1, 'run': 1}
    assert summary['parents_with_a_program_by_side'] == {'shown': 1} and summary['attempts_of_anchored'] == {3: 1}


def test_stage_runs_both_styles_and_keeps_machine_failures_open(root):
    def writer(system, payload):
        return '```python\n' + GOOD + '```'
    env = bank_env.BankEnv(root, units.Ledger(root / 'ledger.json', 5_000_000), {'role': Fake(writer)}, width=2)
    broken = dict(TOOLS, run=lambda program, path: {'status': 'unknown', 'reason': 'native_execution_unavailable'})
    item = make_item(root, 'T3')
    assert sheet_build.stage_ref(env, broken, [item], ['a', 'b']) == {'a: sandbox': 1, 'b: sandbox': 1}
    assert not list((root / 'spreadsheetbench' / 'ref').glob('T3-*.json'))                 # no verdict was written
    assert sheet_build.stage_ref(env, TOOLS, [item], ['a', 'b']) == {'a: anchored': 1, 'b: anchored': 1}
    assert sheet_build.build_report(env, [item], {'T3': 'shown'})['parents_with_two_programs'] == 1


def test_data_twins_need_a_changed_answer_agreement_and_qualification(root):
    from skillopt.execskill.typed import prepare
    writer = lambda system, payload: '```python\n' + (GOOD if prompts.SHEET_STYLES['a'] in system else GOOD.replace('ws.cell(r, 1).value * ws.cell(r, 2).value', 'ws.cell(r, 2).value * ws.cell(r, 1).value')) + '```'
    env = bank_env.BankEnv(root, units.Ledger(root / 'ledger.json', 5_000_000), {'role': Fake(writer)}, width=1)
    item = make_item(root, 'T5')
    assert sheet_build.stage_ref(env, TOOLS, [item], ['a', 'b']) == {'a: anchored': 1, 'b: anchored': 1}
    assert sorted(sheet_build.anchored_programs(env, 'T5')) == ['a', 'b']
    result = sheet_build.stage_twins(env, TOOLS, [item], {'T5': 'judge'})
    assert result == {'made': 2, 'dropped': {}, 'parents_without_a_verdict': 0, 'without_a_verdict': {}}
    twin = env.read('spreadsheetbench', 'items', 'T5_d1.json')
    record = env.read('spreadsheetbench', 'records', 'T5_d1.json')
    prepare.validate_items([twin], 'spreadsheetbench')
    made = openpyxl.load_workbook(twin['private']['test_files'][0])['Data']
    assert [made.cell(r, 3).value for r in (2, 3)] == [65 * 33, 98 * 72]                # 50, 25, 75, 55 times 1.3, half up
    assert record['programs_agree'] is True and record['side'] == 'judge' and record['cells_changed'] == 4
    assert set(twin['private']['asset_sha256']) == {twin['public']['input_files'][0], twin['private']['test_files'][0]}
    assert sheet_build.stage_twins(env, TOOLS, [item], {'T5': 'judge'})['made'] == 2   # nothing made twice
    assert sheet_build.build_report(env, [item], {'T5': 'judge'})['data_twins'] == {
        'made': 2, 'parents': 1, 'by_side': {'judge': 2}, 'checked_by_a_second_program': 2}


def test_data_twin_refusals(root):
    constant = GOOD.replace('ws.cell(r, 1).value * ws.cell(r, 2).value', 'ws.cell(r, 1).value * 0 + ws.cell(1, 1).value')
    writer = lambda system, payload: '```python\n' + GOOD + '```'
    env = bank_env.BankEnv(root, units.Ledger(root / 'ledger.json', 5_000_000), {'role': Fake(writer)}, width=1)
    item = make_item(root, 'T6')
    sheet_build.stage_ref(env, TOOLS, [item], ['a'])
    units.write_json(root / 'spreadsheetbench' / 'ref' / 'T6-b.program.json', {'parent': 'T6', 'style': 'b', 'program': OFF_BY_ONE})
    assert sheet_build.stage_twins(env, TOOLS, [item], {'T6': 'shown'})['dropped'] == {'programs_disagree': 2}
    never = dict(TOOLS, score=lambda item, program, cases, tag: {'status': 'fail', 'reason': 'x'})
    other = make_item(root, 'T7')
    sheet_build.stage_ref(env, TOOLS, [other], ['a'])
    # one program that fits the parent's numbers proves nothing about changed numbers (review 2026-11-13)
    assert sheet_build.stage_twins(env, TOOLS, [other], {'T7': 'shown'})['dropped'] == {'one_program_only': 2}
    sheet_build.stage_ref(env, TOOLS, [other], ['b'])
    assert sheet_build.stage_twins(env, never, [other], {'T7': 'shown'})['dropped'] == {'not_qualified': 2}
    runs = []

    def second_run_down(program, path):                                      # the machine fails on the second program
        runs.append(path)
        return run(program, path) if len(runs) % 2 else {'status': 'unknown', 'reason': 'native_execution_unavailable'}
    assert sheet_build.stage_twins(env, dict(TOOLS, run=second_run_down), [other], {'T7': 'shown'}) == {
        'made': 0, 'dropped': {}, 'parents_without_a_verdict': 1, 'without_a_verdict': {'sandbox': 1}}
    # an unknown verdict is kept by the scorer and would be repeated: it disqualifies; only a scoring exception stays open
    unknown = dict(TOOLS, score=lambda item, program, cases, tag: {'status': 'unknown', 'reason': 'reference_native_cache_drift_or_unavailable'})
    assert sheet_build.stage_twins(env, unknown, [other], {'T7': 'shown'})['dropped'] == {'not_qualified': 2}
    broken = dict(TOOLS, score=lambda item, program, cases, tag: {'status': 'unknown', 'reason': 'native_scoring_exception:OSError'})
    assert sheet_build.stage_twins(env, broken, [other], {'T7': 'shown'}) == {
        'made': 0, 'dropped': {}, 'parents_without_a_verdict': 1, 'without_a_verdict': {'scorer': 1}}
    assert sheet_build.stage_twins(env, TOOLS, [make_item(root, 'T8')], {'T8': 'shown'})['made'] == 0   # no anchored program
    del constant


def test_an_unknown_score_is_a_failed_check_and_a_scoring_exception_stays_open(root):
    seen, tags = [], []

    def writer(system, payload):
        seen.append(payload.get('check_failure'))
        return '```python\n' + GOOD + '```'

    def once_unknown(item, program, cases, tag):
        tags.append(tag)
        return {'status': 'unknown', 'reason': 'prediction:volatile_function'} if len(tags) == 1 else score(item, program, cases, tag)
    env = bank_env.BankEnv(root, units.Ledger(root / 'ledger.json', 5_000_000), {'role': Fake(writer)}, width=1)
    made = sheet_build.reference_program(env, dict(TOOLS, score=once_unknown), make_item(root, 'T9'), 'a')
    assert made['status'] == 'anchored' and [a.get('check') for a in made['attempts']] == ['unscorable', 'anchored']
    assert seen[0] is None and 'could not be checked (prediction:volatile_function)' in seen[1]
    broken = dict(TOOLS, score=lambda item, program, cases, tag: {'status': 'unknown', 'reason': 'native_scoring_exception:OSError'})
    other = make_item(root, 'T10')
    assert sheet_build.stage_ref(env, broken, [other], ['a']) == {'a: scorer': 1}
    crash = dict(TOOLS, run=lambda program, path: 1 / 0)                     # anything else: the stage goes on, no verdict
    assert sheet_build.stage_ref(env, crash, [other], ['a']) == {'a: error: ZeroDivisionError': 1}
    assert sheet_build.stage_ref(env, TOOLS, [other], ['a']) == {'a: anchored': 1}


SUM = ('import openpyxl\nwb = openpyxl.load_workbook("input.xlsx")\nws = wb["Data"]\n'
       'for r in range(2, ws.max_row + 1):\n    ws.cell(r, 4).value = ws.cell(r, 1).value + ws.cell(r, 2).value\n'
       'wb.save("output.xlsx")\n')
SUM_OTHER = SUM.replace('ws.cell(r, 1).value + ws.cell(r, 2).value', 'sum(ws.cell(r, c).value for c in (1, 2))')
TASK = {'instruction': 'On the Data sheet I need a new column D that adds Units and Price for every data row, written as '
                       'plain numbers into D2:D3.', 'answer_position': "'Data'!D2:D3"}


def task_reply(task=TASK, program=SUM):
    return '```json\n%s\n```\n```python\n%s```' % (json.dumps(task), program)


def test_new_task_needs_two_agreeing_programs_and_qualification(root):
    from skillopt.execskill.typed import prepare
    seen = []

    def writer(system, payload):
        seen.append((system, payload))
        return task_reply() if system == prompts.SHEET_TASK_SYSTEM else '```python\n' + SUM_OTHER + '```'
    role = Fake(writer)
    env = bank_env.BankEnv(root, units.Ledger(root / 'ledger.json', 5_000_000), {'role': role}, width=1)
    items = [make_item(root, 'T20'), make_item(root, 'T21'), make_item(root, 'T22')]
    sides = {'T20': 'shown', 'T21': 'shown', 'T22': 'judge'}
    assert sheet_build.stage_newtask(env, TOOLS, items[:1] + items[1:], sides, ['plain', 'brief'], 1, 'BRIEF') == {
        'plain: made': 3, 'brief: made': 3}
    wrote = [payload for system, payload in seen if system == prompts.SHEET_TASK_SYSTEM]
    solved = [payload for system, payload in seen if system == prompts.SHEET_SOLVE_SYSTEM]
    assert len(wrote) == 6 and len(solved) == 6
    assert sorted(payload.get('brief', '-') for payload in wrote) == ['-'] * 3 + ['BRIEF'] * 3
    assert all(payload['about_this_workbook'].startswith('Fill column C') and payload['kind'] == prompts.SHEET_TASK_KINDS[0]
               and set(payload['workbook']) == {'sheets'} for payload in wrote)   # the parent's answer cells are not shown
    # the examples are instructions of OTHER parents of the same side; the judging parent T22 has none
    assert sorted(len(payload['examples']) for payload in wrote) == [0, 0, 1, 1, 1, 1]
    # the second program is written from the new instruction alone
    assert all(set(payload) == {'instruction', 'answer_position', 'workbook'} and payload['instruction'] == TASK['instruction']
               and payload['workbook']['answer_cells'] == 2 for payload in solved)
    task = env.read('spreadsheetbench', 'items', 'T20_tp1.json')
    record = env.read('spreadsheetbench', 'records', 'T20_tp1.json')
    prepare.validate_items([task], 'spreadsheetbench')
    assert task['task_id'] == 'T20~tp1' and task['public']['input_files'] == items[0]['public']['input_files']
    assert task['family_id'] == items[0]['family_id'] == 'exact-T20'         # a parent's items share its family (B11)
    made = openpyxl.load_workbook(task['private']['test_files'][0])['Data']
    assert [made.cell(r, 4).value for r in (2, 3)] == [75, 130]
    assert record['kind'] == 'new_task' and record['arm'] == 'plain' and record['side'] == 'shown' and record['program'] == SUM
    assert env.read('spreadsheetbench', 'records', 'T22_tb1.json')['side'] == 'judge'
    calls = len(role.calls)
    assert sheet_build.stage_newtask(env, TOOLS, items, sides, ['plain'], 1, None) == {'plain: made': 3} and len(role.calls) == calls
    summary = sheet_build.build_report(env, items, sides)['new_tasks']
    assert summary['plain'] == {'asked': 3, 'made': 3, 'parents_with_a_new_task': 3, 'made_by_side': {'shown': 2, 'judge': 1},
                                'drop_reasons': {}, 'made_by_kind': {prompts.SHEET_TASK_KINDS[0][:40]: 3}}
    assert summary['brief']['made'] == 3


def test_new_task_refusals(root):
    replies = {}

    def writer(system, payload):
        key = 'solve' if system == prompts.SHEET_SOLVE_SYSTEM else 'write'
        return replies[writer.turn][key]
    env = bank_env.BankEnv(root, units.Ledger(root / 'ledger.json', 5_000_000), {'role': Fake(writer)}, width=1)

    def outcome(name, write, solve='```python\n' + SUM_OTHER + '```', tools=TOOLS, item=None):
        writer.turn = name
        replies[name] = {'write': write, 'solve': solve}
        item = item or make_item(root, name)
        try:
            row = sheet_build.new_task(env, tools, item, 'shown', 'plain', 1, prompts.SHEET_TASK_KINDS[0], [], None)
        except RuntimeError as failed:
            return str(failed).split(':')[0]
        return row['reason']

    assert outcome('R1', '```python\n' + SUM + '```') == 'reply_shape'                   # no instruction
    assert outcome('R1b', json.dumps(TASK) + '\nno program follows') == 'reply_shape'
    assert outcome('R2', task_reply({**TASK, 'instruction': 'Add them.'})) == 'reply_shape'
    assert outcome('R3', task_reply({**TASK, 'answer_position': "'Nope'!A1:A2"})) == 'answer_position'
    assert outcome('R4', task_reply({**TASK, 'answer_position': "'Data'!D2:D900"})) == 'answer_position'
    long = make_item(root, 'R5')
    long['public']['instruction'] = TASK['instruction']
    assert outcome('R5', task_reply({**TASK, 'instruction': TASK['instruction'] + ' Thanks.'}), item=long) == 'repeats_parent'
    assert outcome('R6', task_reply(program='def broken(:\n')) == 'syntax'
    assert outcome('R7', task_reply(program='print(1)\n')) == 'contract'
    assert outcome('R8', task_reply(program=CRASH)) == 'program_fails'
    nothing = 'import openpyxl\nwb = openpyxl.load_workbook("input.xlsx")\nwb.save("output.xlsx")\n'
    assert outcome('R9', task_reply(program=nothing)) == 'nothing_computed'
    two = '```python\nprint(1)\n```\ntext\n```python\nprint(2)\n```'
    assert outcome('R10', task_reply(), solve=two) == 'no_second_program'
    assert outcome('R11', task_reply(), solve='```python\n' + CRASH + '```') == 'second_program_fails'
    shifted = SUM.replace('ws.cell(r, 4).value =', 'ws.cell(r + 1, 4).value =')
    assert outcome('R12', task_reply(), solve='```python\n' + shifted + '```') == 'programs_disagree'
    assert env.read('spreadsheetbench', 'newtask', 'R12_tp1.json')['detail'] == 'shifted_rows'
    never = dict(TOOLS, score=lambda item, program, cases, tag: {'status': 'unknown', 'reason': 'prediction:external_link'})
    assert outcome('R13', task_reply(), tools=never) == 'not_qualified'
    # two programs that both CLEAR filled answer cells differ from the input and agree: nothing was answered
    clear = SUM.replace('ws.cell(r, 4).value = ws.cell(r, 1).value + ws.cell(r, 2).value', 'ws.cell(r, 1).value = None')
    cleared = {**TASK, 'answer_position': "'Data'!A2:A3"}
    assert outcome('R15', task_reply(cleared, clear), solve='```python\n' + clear + '```') == 'answer_blank'
    assert 'external_link' in env.read('spreadsheetbench', 'newtask', 'R13_tp1.json')['detail']
    down = dict(TOOLS, run=lambda program, path: {'status': 'unknown', 'reason': 'native_execution_unavailable'})
    assert outcome('R14', task_reply(), tools=down) == 'sandbox'
    assert not (root / 'spreadsheetbench' / 'newtask' / 'R14_tp1.json').exists()        # no verdict: asked again later
    assert outcome('R14', task_reply(), item=make_item(root / 'again', 'R14')) is None   # made on the second run
    assert not (root / 'spreadsheetbench' / 'items' / 'R12_tp1.json').exists()


def test_a_task_reply_is_read_tolerantly(root):
    extract = code_delivery.extract_python
    plain = json.dumps(TASK) + '\n\nHere is the program:\n```python\n' + SUM + '```'
    fenced = 'Task:\n```\n' + json.dumps(TASK) + '\n```\n```python\n' + SUM + '```\nDone.'
    for reply in (task_reply(), plain, fenced):
        assert sheet_build._task_reply(reply, extract) == (TASK['instruction'], TASK['answer_position'], SUM)
    for bad in ('```python\n' + SUM + '```', json.dumps(TASK), '', None):
        with pytest.raises(sheet_build.sheet.Drop):
            sheet_build._task_reply(bad, extract)
