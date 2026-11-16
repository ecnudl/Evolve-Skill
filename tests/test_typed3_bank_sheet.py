"""typed-v3 item bank, SpreadsheetBench fixed code (bank/sheet.py): the writer's workbook view, the expected answer
cells, the copied-answer screen of reference programs, the scaling of a twin's workbook and the labels of a wrong
output. Small workbooks are written with openpyxl; no sandbox, no model."""
import datetime
import shutil
import tempfile
from fractions import Fraction
from pathlib import Path

import openpyxl
import pytest

from skillopt.execskill.typed.bank import sheet


@pytest.fixture
def folder():
    base = Path('/tmp/typed3-neutral')
    base.mkdir(exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='sheet-', dir=base))
    yield made
    shutil.rmtree(made, ignore_errors=True)


def book(path, rows, sheet_name='Data', extra=None):
    made = openpyxl.Workbook()
    made.active.title = sheet_name
    for row in rows:
        made.active.append(row)
    for name, more in (extra or {}).items():
        other = made.create_sheet(name)
        for row in more:
            other.append(row)
    made.save(path)
    return str(path)


ROWS = [['Region', 'Year', 'Units', 'Price', 'Total'],
        ['North', 2021, 120, 2.5, None], ['South', 2021, 80, 3.75, None], ['East', 2022, 45, 10.0, None],
        ['West', 2022, 7, 1.25, None]]
EXPECTED = [row[:4] + [None if total is None else total] for row, total in zip(ROWS, ['Total', 300.0, 300.0, 450.0, 8.75])]


def test_view_and_answer_cells(folder):
    path = book(folder / 'in.xlsx', ROWS + [['r%d' % i, 2023, i, 1.0, None] for i in range(30)])
    view = sheet.workbook_view(path, "'Data'!E2:E5")
    data = view['sheets'][0]
    assert (data['sheet'], data['rows'], data['columns']) == ('Data', 35, 5)
    assert len(data['first_rows']) == sheet.VIEW_ROWS and data['first_rows'][1] == ['North', 2021, 120, 2.5, None]
    assert data['last_rows']['from_row'] == 33 and len(data['last_rows']['rows']) == 3
    assert view['answer_cells'] == 4 and view['answer_cells_in_input'][0] == {'sheet': 'Data', 'cell': 'E2', 'value': None}
    expected = book(folder / 'want.xlsx', EXPECTED)
    assert sheet.answer_cells(expected, 'E2:E5') == [('Data', 'E2', 300), ('Data', 'E3', 300), ('Data', 'E4', 450), ('Data', 'E5', 8.75)]
    assert sheet.targets('E2:E3', ['Data']) == [('Data', ['E2', 'E3'])]


def test_an_answer_sheet_the_input_lacks(folder):
    path = book(folder / 'in.xlsx', ROWS)
    view = sheet.workbook_view(path, "'Summary'!A1:B2")
    assert view['answer_cells_in_input'] == [] and view['answer_sheet_missing_in_input'] is True
    assert sheet.scale_workbook(path, str(folder / 'twin.xlsx'), 2, "'Summary'!A1:B2", '') == 7


def test_screen_refuses_copied_answers_only(folder):
    path = book(folder / 'in.xlsx', ROWS)
    values = sheet.workbook_values(path)
    honest = ('import openpyxl\nwb = openpyxl.load_workbook("input.xlsx")\nws = wb["Data"]\n'
              'for r in range(2, ws.max_row + 1):\n    ws.cell(r, 5).value = ws.cell(r, 3).value * ws.cell(r, 4).value\n'
              'wb.save("output.xlsx")\n')
    assert sheet.screen_program(honest, 'Fill Total = Units * Price', [300.0, 300.0, 450.0, 8.75], values) > 0
    copied = honest.replace('ws.cell(r, 3).value * ws.cell(r, 4).value', '[300, 300, 450, 8.75][r - 2]')
    with pytest.raises(sheet.Drop) as caught:
        sheet.screen_program(copied, 'Fill Total = Units * Price', [300.0, 300.0, 450.0, 8.75], values)
    assert caught.value.reason == 'copied_answers' and '450' in caught.value.detail
    # a category word the instruction names, and a value that is a cell of the input, are not copied answers
    labels = honest.replace('ws.cell(r, 3).value * ws.cell(r, 4).value', '"High" if ws.cell(r, 3).value > 100 else "North"')
    assert sheet.screen_program(labels, 'Write High when Units exceed 100', ['High', 'North'], values) > 0
    with pytest.raises(sheet.Drop) as caught:
        sheet.screen_program('print(1', '', [], values)
    assert caught.value.reason == 'syntax'
    with pytest.raises(sheet.Drop) as caught:
        sheet.screen_program('x = 1\n', '', [1], values)
    assert caught.value.reason == 'contract'
    single = honest.replace('ws.cell(r, 3).value * ws.cell(r, 4).value', '1234.5')
    with pytest.raises(sheet.Drop):
        sheet.screen_program(single, 'Compute the grand total', [1234.5], values)


def test_scaling_keeps_relations_and_protected_cells(folder):
    rows = ROWS + [['Sum', None, '=SUM(C2:C5)', None, None], ['Limit', None, 100, None, None]]
    path = book(folder / 'in.xlsx', rows, extra={'Keys': [[120, 'north key'], [80, 'south key']]})
    changed = sheet.scale_workbook(path, str(folder / 'twin.xlsx'), Fraction(13, 10), 'E2:E5',
                                   'Mark rows whose Units exceed 100')
    made = openpyxl.load_workbook(folder / 'twin.xlsx')
    data, keys = made['Data'], made['Keys']
    assert [data.cell(r, 3).value for r in range(2, 6)] == [156, 104, 59, 7]        # integers stay integers; 7 is below 10
    assert [data.cell(r, 4).value for r in range(2, 6)] == [3.3, 4.88, 13, 1.63]               # half up, each cell's decimals kept
    assert [data.cell(r, 2).value for r in range(2, 6)] == [2021, 2021, 2022, 2022]  # years stay
    assert data['C6'].value == '=SUM(C2:C5)' and data['C7'].value == 100             # a formula; a number of the instruction
    assert [keys.cell(r, 1).value for r in (1, 2)] == [156, 104]                     # equal keys stay equal across sheets
    assert changed == 9
    with pytest.raises(sheet.Drop) as caught:
        sheet.scale_workbook(book(folder / 'text.xlsx', [['a', 'b'], ['x', 5]]), str(folder / 'no.xlsx'), 2, 'B2', '')
    assert caught.value.reason == 'nothing_to_change'


def test_labels_of_wrong_outputs(folder):
    expected = book(folder / 'want.xlsx', EXPECTED)
    label = lambda rows, name='Data': sheet.label_output(book(folder / 'out.xlsx', rows, sheet_name=name), expected, 'E2:E5')
    filled = lambda totals: [row[:4] + [total] for row, total in zip(ROWS, ['Total'] + totals)]
    assert sheet.label_output(None, expected, 'E2:E5') == 'missing_output'
    assert label(filled([300, 300, 450, 8.75]), name='Other') == 'missing_sheet'
    assert label(ROWS) == 'nothing_written'
    assert label([ROWS[0]] + [ROWS[1]] + filled([300, 300, 450, 8.75])[1:]) == 'shifted_rows'
    shifted = [row[:4] + [None, total] for row, total in zip(ROWS, ['Total', 300, 300, 450, 8.75])]
    assert label(shifted) == 'shifted_columns'
    assert label(filled([300.4, 300.2, 451, 8.8])) == 'number_close'
    assert label(filled(['three hundred', 'x', 'y', 'z'])) == 'type_mismatch'
    assert label(filled([300, 300, 450, 99])) == 'partly_right'
    assert label(filled([1, 2, 3, 4])) == 'all_wrong'
    words = book(folder / 'words.xlsx', [['k', 'v'], ['a', 'Open Item'], ['b', 'Closed']])
    assert sheet.label_output(book(folder / 'o2.xlsx', [['k', 'v'], ['a', 'open  item'], ['b', 'Closed']]), words, 'B2:B3') == 'text_form'
    dates = book(folder / 'dates.xlsx', [['d'], [datetime.datetime(2024, 3, 1)]])
    assert sheet.label_output(book(folder / 'o3.xlsx', [['d'], ['2024-03-01']]), dates, 'A2') == 'type_mismatch'


def test_one_copied_answer_refuses_a_program_with_several_answer_cells():
    # review 2026-11-13: computing the first answer and writing the second down used to pass
    program = ('import openpyxl\nwb = openpyxl.load_workbook("input.xlsx")\nws = wb.active\n'
               'ws["C2"] = ws["A2"].value * ws["B2"].value\nws["C3"] = 4125\nwb.save("output.xlsx")\n')
    with pytest.raises(sheet.Drop) as refused:
        sheet.screen_program(program, 'Fill column C with Units times Price.', [1250, 4125], {'50', '25', '75', '55'})
    assert refused.value.reason == 'copied_answers' and '4125' in refused.value.detail
    # a value the input holds or the instruction names is not a copied answer
    assert sheet.screen_program(program, 'Fill column C; the last row must read 4125.', [1250, 4125], {'50'}) > 0
    assert sheet.screen_program(program, 'Fill column C with Units times Price.', [1250, 4125], {'4125'}) > 0
