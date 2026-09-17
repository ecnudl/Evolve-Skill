"""Host-only independent oracles and real frozen OS-sandbox task checks."""

import ast
import itertools
import json
import posixpath
import random
import re
from collections import defaultdict
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction

import pytest

from skillopt.coevolution_v3 import executor
from skillopt.coevolution_v5.core import feedback_packet, initial_rubric
from skillopt.coevolution_v7 import tasks as t
from skillopt.validator_pilot.api import digest

CALIBRATION = t.calibration_tasks()
DEVELOPMENT = t.development_tasks()
FINAL = t.final_coding_tasks()
NATIVE = t.final_native_tasks()
CODING = CALIBRATION + DEVELOPMENT + FINAL


def oracle(family, data):
    """Independently calculated host truth, never imported reference execution."""
    if family == 'maximum-bipartite-assignment':
        sentinel = data['right_size']
        possibilities = []
        for assignment in itertools.product(*[sorted({x for x in options if x < sentinel}) + [sentinel]
                                                for options in data['choices']]):
            present = [x for x in assignment if x != sentinel]
            if len(present) == len(set(present)):
                possibilities.append(assignment)
        best = min(possibilities, key=lambda assignment: (assignment.count(sentinel), assignment))
        return {'matched': len(best) - best.count(sentinel), 'assignment': [None if x == sentinel else x for x in best]}
    if family == 'integer-largest-remainder-allocation':
        total = sum(data['weights'])
        if not total:
            return {'allocation': [0] * len(data['weights']), 'unallocated': data['seats']}
        quotas = [Fraction(data['seats'] * w, total) for w in data['weights']]
        floor = [int(q) for q in quotas]
        for i in sorted(range(len(quotas)), key=lambda i: (-(quotas[i] - floor[i]), i))[:data['seats'] - sum(floor)]:
            floor[i] += 1
        return {'allocation': floor, 'unallocated': 0}
    if family == 'endian-twos-complement-bitfield':
        if data['offset'] + data['width'] > 16:
            return {'error': 'range'}
        word = int.from_bytes(bytes(data['bytes']), byteorder=data['order'])
        modulus = 2 ** data['width']
        value = word // (2 ** data['offset']) % modulus
        return {'value': value - modulus if data['signed'] and value >= modulus // 2 else value}
    if family == 'canonical-longest-common-subsequence':
        candidates = [{''.join(text[i] for i in indices) for n in range(len(text) + 1)
                       for indices in itertools.combinations(range(len(text)), n)} for text in [data['left'], data['right']]]
        return min(candidates[0] & candidates[1], key=lambda value: (-len(value), value))
    if family == 'weighted-orthogonal-grid-routing':
        grid = data['grid']
        if not grid or not grid[0] or any(len(row) != len(grid[0]) for row in grid):
            return None
        nodes = [(r, c) for r, row in enumerate(grid) for c, value in enumerate(row) if value > 0]
        a, b = tuple(data['start']), tuple(data['goal'])
        if a not in nodes or b not in nodes:
            return None
        distances = {(x, y): (0 if x == y else grid[y[0]][y[1]] if abs(x[0] - y[0]) + abs(x[1] - y[1]) == 1
                               else float('inf')) for x in nodes for y in nodes}
        for via in nodes:
            for x in nodes:
                for y in nodes:
                    distances[x, y] = min(distances[x, y], distances[x, via] + distances[via, y])
        return None if distances[a, b] == float('inf') else distances[a, b]
    if family == 'quoted-comment-shielding-lexer':
        text = data['text']
        result, index = [], 0
        while index < len(text):
            if text[index].isspace():
                index += 1
                continue
            if text.startswith('--', index):
                index = text.index('\n', index) + 1 if '\n' in text[index:] else len(text)
                continue
            if text[index] == "'":
                start, index, pieces = index, index + 1, []
                while True:
                    end = text.find("'", index)
                    if end < 0:
                        return {'tokens': result, 'error': start}
                    pieces.append(text[index:end])
                    if end + 1 < len(text) and text[end + 1] == "'":
                        pieces.append("'")
                        index = end + 2
                    else:
                        index = end + 1
                        break
                result.append(['string', ''.join(pieces)])
                continue
            matched = next(((kind, match.group()) for kind, pattern in (
                ('id', r'[A-Za-z_][A-Za-z_0-9]*'), ('integer', r'[0-9]+'), ('operator', r'==|='))
                if (match := re.match(pattern, text[index:]))), None)
            if matched is None:
                return {'tokens': result, 'error': index}
            result.append(list(matched))
            index += len(matched[1])
        return {'tokens': result, 'error': None}
    if family == 'original-coordinate-multi-edit':
        text, edits = data['text'], data['edits']
        bad = [i for i, e in enumerate(edits) if e['start'] > e['end'] or e['end'] > len(text)]
        if bad:
            return {'error': 'range', 'index': bad[0]}
        for a, b in itertools.combinations(edits, 2):
            occupied_a, occupied_b = set(range(a['start'], a['end'])), set(range(b['start'], b['end']))
            if occupied_a & occupied_b or (not occupied_a and a['start'] in occupied_b - {b['start']}) or (
                    not occupied_b and b['start'] in occupied_a - {a['start']}):
                return {'error': 'overlap'}
        characters = list(text)
        for index in sorted(range(len(edits)), key=lambda i: (edits[i]['start'], edits[i]['end'], i), reverse=True):
            e = edits[index]
            characters[e['start']:e['end']] = list(e['value'])
        return {'text': ''.join(characters)}
    if family == 'hierarchical-wildcard-policy-resolution':
        matching = []
        for index, rule in enumerate(data['rules']):
            positions = [i for i, part in enumerate(rule['pattern']) if part == '**']
            found = False
            for lengths in itertools.product(range(len(data['path']) + 1), repeat=len(positions)):
                widths = dict(zip(positions, lengths))
                expanded = [segment for i, part in enumerate(rule['pattern'])
                            for segment in (['*'] * widths[i] if part == '**' else [part])]
                if len(expanded) == len(data['path']) and all(x == '*' or x == y for x, y in zip(expanded, data['path'])):
                    found = True
                    break
            if found:
                matching.append((sum(part not in ['*', '**'] for part in rule['pattern']), rule['priority'], index))
        if not matching:
            return {'allowed': False, 'matched': []}
        priority = max(row[:2] for row in matching)
        winners = [row[2] for row in matching if row[:2] == priority]
        return {'allowed': all(data['rules'][i]['effect'] == 'allow' for i in winners), 'matched': winners}
    if family == 'exact-rational-expression-extension':
        expression = ' '.join('(' + str(token) + ')' if type(token) is int else token for token in data['tokens'])
        allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.UAdd, ast.USub)
        try:
            node = ast.parse(expression, mode='eval')
            if any(not isinstance(value, allowed) for value in ast.walk(node)):
                raise ValueError()
            def evaluate(value):
                if isinstance(value, ast.Constant):
                    return Fraction(value.value)
                if isinstance(value, ast.UnaryOp):
                    result = evaluate(value.operand)
                    return -result if isinstance(value.op, ast.USub) else result
                left, right = evaluate(value.left), evaluate(value.right)
                if isinstance(value.op, ast.Add):
                    return left + right
                if isinstance(value.op, ast.Sub):
                    return left - right
                if isinstance(value.op, ast.Mult):
                    return left * right
                return left / right
            result = evaluate(node.body)
            return {'numerator': result.numerator, 'denominator': result.denominator}
        except (SyntaxError, ValueError):
            return {'error': 'syntax'}
        except ZeroDivisionError:
            return {'error': 'division_by_zero'}
    if family == 'event-sourced-snapshot-pagination':
        events = data['events']
        selected = {}
        for key in {e['id'] for e in events}:
            winner = sorted(enumerate(events), key=lambda pair: (pair[1]['version'], pair[0]), reverse=True)
            row = next(row for _, row in winner if row['id'] == key)
            if not row['deleted']:
                selected[key] = {'id': key, 'value': row['value']}
        order = sorted(selected, key=lambda key: next(i for i, e in enumerate(events) if e['id'] == key))
        end = data['offset'] + data['limit']
        return {'items': [selected[key] for key in order[data['offset']:end]], 'total': len(order),
                'next': end if end < len(order) else None}
    if family == 'virtual-path-root-confinement':
        changes = [(-1 if part == '..' else 1) for part in data['path'].split('/') if part not in ['', '.']]
        lowest = min([0] + [sum(changes[:end]) for end in range(1, len(changes) + 1)])
        return {'path': posixpath.normpath('/' + data['path'].lstrip('/')), 'root_escape_attempts': -lowest}
    if family == 'bounded-denomination-combinations':
        stock = defaultdict(int)
        for coin in data['coins']:
            stock[coin['value']] += coin['count']
        return sum(sum(value * count for value, count in zip(stock, counts)) == data['target']
                   for counts in itertools.product(*[range(number + 1) for number in stock.values()]))
    raise AssertionError(f'Missing oracle for {family}')


def native(adapter, files, public_only=False):
    return executor.evaluate(adapter.task, {'files': {name: files[name] for name in adapter.task.editable_paths}},
                             public_only=public_only)


def test_new_panel_shape_and_structural_disjointness():
    assert (len(DEVELOPMENT), len(CALIBRATION), len(FINAL), len(NATIVE)) == (3, 6, 6, 12)
    assert len({a.task.id for a in CODING}) == 15
    assert len({a.task.cluster_id for a in CODING}) == 12
    assert len({a.task.cluster_id for a in FINAL}) == 3
    assert len({(a.domain, a.task['cluster_id']) for a in NATIVE}) == 4
    for group in (DEVELOPMENT, CALIBRATION, FINAL):
        assert not {a.task.cluster_id for a in group} & {a.task.cluster_id for other in (
            DEVELOPMENT, CALIBRATION, FINAL) if other is not group for a in other}
    assert len({digest(v) for a in CALIBRATION for v in a.task.metadata['controls'].values()}) == 24
    assert all('v6-' not in a.task.id and a.task.metadata['historical_task_assets_used'] is False for a in CODING)


@pytest.mark.parametrize('adapter', CODING, ids=lambda a: a.task.id)
def test_coding_literal_gold_is_legal_and_independently_correct(adapter):
    for case in adapter.task.public_cases + adapter.task.private_cases:
        assert adapter._input_valid(case['input']), case
        assert oracle(adapter.task.family, case['input']) == case['expected'], case


@pytest.mark.parametrize('adapter', CODING, ids=lambda a: a.task.id)
def test_reference_and_equivalent_pass_frozen_os_sandbox(adapter):
    for name in ('reference', 'equivalent'):
        result = native(adapter, adapter.task.metadata['controls'][name])
        assert result['hard'] is True and result['execution_ok'] is True, (name, result)


@pytest.mark.parametrize('adapter', CODING, ids=lambda a: a.task.id)
def test_native_controls_expose_semantic_and_preservation_defects(adapter):
    for name in ('semantic_mutant', 'preservation_mutant'):
        result = native(adapter, adapter.task.metadata['controls'][name])
        assert result['hard'] is False and result['execution_ok'] is True, (name, result)
        failures = [row for row in result['case_results'] if row['passed'] is False]
        if name == 'preservation_mutant':
            assert failures and all(row['id'].endswith(':input_unchanged') for row in failures)
        else:
            assert any(row['id'].endswith(':behavior') for row in failures)


@pytest.mark.parametrize('adapter', CALIBRATION, ids=lambda a: a.task.id)
def test_public_calibration_controls_all_pass_but_legal_probes_expose_mutants(adapter):
    for name in ('reference', 'equivalent', 'semantic_mutant', 'preservation_mutant'):
        assert native(adapter, adapter.task.metadata['controls'][name], public_only=True)['hard'] is True
    for name in ('semantic_mutant', 'preservation_mutant'):
        assessed = adapter.evaluate(adapter.task.metadata['controls'][name], initial_rubric(), phase='promotion',
                                    public_only=True, extra_inputs=[case['input'] for case in adapter.task.private_cases])
        assert assessed[0]['status'] == 'pass'
        assert assessed[1]['status'] == 'fail' and assessed[1]['verified'] is True


@pytest.mark.parametrize('adapter', CODING, ids=lambda a: a.task.id)
def test_public_interface_exposes_contract_not_private_oracle(adapter):
    public = adapter.public_task()
    task = adapter.task
    assert json.dumps(task.metadata['public_contract'], sort_keys=True, ensure_ascii=False) in public['prompt']
    assert not {'metadata', 'private_cases', 'reference_files', 'controls'} & public.keys()
    assert all(case['label'] not in json.dumps(public) for case in task.private_cases)
    assert task.files['api.py'] == t.ENTRY and 'copy' not in t.ENTRY


@pytest.mark.parametrize('adapter', CALIBRATION + FINAL, ids=lambda a: a.task.id)
def test_reserved_coding_splits_never_become_development_feedback(adapter):
    with pytest.raises(ValueError):
        adapter.evaluate(adapter.task.reference_files, initial_rubric(), phase='development')
    rows = adapter.evaluate(adapter.task.reference_files, initial_rubric(), phase=adapter.task.split)
    with pytest.raises(ValueError):
        feedback_packet(task_id=adapter.task.id, cluster_id=adapter.task.cluster_id, domain='coding', assessments=rows,
                        artifact=adapter.task.reference_files, contract=adapter.task.prompt)


def test_final_variants_have_different_public_data_but_shared_family():
    for first, second in zip(FINAL[::2], FINAL[1::2]):
        assert first.task.cluster_id == second.task.cluster_id
        assert first.task.public_cases != second.task.public_cases
        assert first.task.private_cases != second.task.private_cases
        assert first.task.reference_files == second.task.reference_files


def random_inputs(family, count=25):
    rng = random.Random(7249)
    results = []
    for _ in range(count):
        if family == 'maximum-bipartite-assignment':
            value = {'choices': [[rng.randrange(4) for _ in range(rng.randrange(4))] for _ in range(rng.randrange(5))],
                     'right_size': rng.randrange(1, 4)}
        elif family == 'integer-largest-remainder-allocation':
            value = {'weights': [rng.randrange(6) for _ in range(rng.randrange(6))], 'seats': rng.randrange(20)}
        elif family == 'endian-twos-complement-bitfield':
            value = {'bytes': [rng.randrange(256), rng.randrange(256)], 'order': rng.choice(['big', 'little']),
                     'offset': rng.randrange(16), 'width': rng.randrange(1, 17), 'signed': rng.choice([True, False])}
        elif family == 'canonical-longest-common-subsequence':
            value = {key: ''.join(rng.choice('abc') for _ in range(rng.randrange(8))) for key in ['left', 'right']}
        elif family == 'weighted-orthogonal-grid-routing':
            value = {'grid': [[rng.randrange(6) for _ in range(3)] for _ in range(2)],
                     'start': [rng.randrange(2), rng.randrange(3)], 'goal': [rng.randrange(2), rng.randrange(3)]}
        elif family == 'quoted-comment-shielding-lexer':
            value = {'text': ''.join(rng.choice(['a', 'B', '00', '==', '=', "'", '--', '\n', ' ', '@']) for _ in range(12))}
        elif family == 'original-coordinate-multi-edit':
            value = {'text': 'abcdef', 'edits': [{'start': rng.randrange(8), 'end': rng.randrange(8),
                                                'value': rng.choice(['LONG', '', 'X'])} for _ in range(rng.randrange(5))]}
        elif family == 'hierarchical-wildcard-policy-resolution':
            value = {'path': [rng.choice(['a', 'b']) for _ in range(rng.randrange(4))], 'rules': [
                {'pattern': [rng.choice(['a', 'b', '*', '**']) for _ in range(rng.randrange(4))],
                 'priority': rng.randrange(-2, 3), 'effect': rng.choice(['allow', 'deny'])} for _ in range(rng.randrange(5))]}
        elif family == 'exact-rational-expression-extension':
            tokens = ['-', '(', rng.randrange(-5, 6), rng.choice(['+', '-', '*', '/']), rng.randrange(-5, 6), ')',
                      rng.choice(['+', '-', '*', '/']), '-', rng.randrange(-5, 6)]
            if rng.randrange(5) == 0:
                tokens += [')']
            value = {'tokens': tokens}
        elif family == 'event-sourced-snapshot-pagination':
            value = {'events': [{'id': rng.choice('abc'), 'version': rng.randrange(4), 'deleted': rng.choice([True, False]),
                                 'value': rng.randrange(-5, 6)} for _ in range(rng.randrange(8))],
                     'offset': rng.randrange(5), 'limit': rng.randrange(1, 5)}
        elif family == 'virtual-path-root-confinement':
            value = {'path': '/'.join(rng.choice(['.', '..', 'a', 'b', '', '...']) for _ in range(9))}
        elif family == 'bounded-denomination-combinations':
            value = {'coins': [{'value': rng.randrange(1, 5), 'count': rng.randrange(4)} for _ in range(rng.randrange(5))],
                     'target': rng.randrange(12)}
        else:
            raise AssertionError(family)
        results.append(value)
    return results


@pytest.mark.parametrize('adapter', CALIBRATION + DEVELOPMENT + FINAL[::2], ids=lambda a: a.task.family)
def test_two_controls_against_random_independent_host_oracle_in_sandbox(adapter):
    values = random_inputs(adapter.task.family)
    assert all(adapter._input_valid(value) for value in values)
    cases = [{'label': f'independent-host-{i}', 'input': value, 'expected': oracle(adapter.task.family, value),
              'exception': None, 'public': False, 'dimension': 'requested_behavior'} for i, value in enumerate(values)]
    task = replace(adapter.task, public_cases=[], private_cases=cases)
    for name in ['reference', 'equivalent']:
        files = task.metadata['controls'][name]
        result = executor.evaluate(task, {'files': {'logic.py': files['logic.py']}}, public_only=False)
        assert result['hard'] is True and result['execution_ok'] is True, (name, result)


@pytest.mark.parametrize('adapter', NATIVE, ids=lambda a: a.task['id'])
def test_native_reference_uses_actual_formula_or_rule_execution(adapter):
    result = adapter.evaluate(adapter.task['reference_artifact'])
    assert result['status'] == 'pass' and result['score'] == 1.0
    assert result['case_results'] and all(row['passed'] is True for row in result['case_results'])
    assert all(row['error'] is None for row in result['case_results'])


@pytest.mark.parametrize('adapter', NATIVE, ids=lambda a: a.task['id'])
def test_native_public_contract_and_gold_isolation(adapter):
    task, public = adapter.task, adapter.public_task()
    assert json.dumps(task['contract'], sort_keys=True) in public['prompt']
    assert not {'hidden_cases', 'reference_artifact', 'metadata', 'cluster_id'} & public.keys()
    assert all(case['id'] not in json.dumps(public) for case in task['hidden_cases'])
    if task['contract']['change_scope'] == 'read_only':
        assert public['public_cases'] == []
        assert set(task['reference_artifact']) == {'answer'}


@pytest.mark.parametrize('adapter', NATIVE, ids=lambda a: a.task['id'])
def test_native_wrong_artifact_is_executably_rejected_not_unknown(adapter):
    task = adapter.task
    if task['contract']['change_scope'] == 'read_only':
        bad = {'answer': [] if adapter.domain == 'rule_reasoning' else task['reference_artifact']['answer'] + 1}
    elif adapter.domain == 'spreadsheet':
        bad = {'formulas': {cell: task['formulas'][cell] for cell in task['editable_cells']}}
    else:
        bad = {'rules': task['rules']}
    scored = adapter.evaluate(bad)
    assert scored['score'] == 0.0 and scored['status'] == 'fail', scored
    assert scored['case_results']


def test_native_structural_clusters_are_not_inflated_by_contract_strata():
    for domain in ['spreadsheet', 'rule_reasoning']:
        selected = [adapter for adapter in NATIVE if adapter.domain == domain]
        assert len(selected) == 6 and len({a.task['cluster_id'] for a in selected}) == 2
        for cluster in {a.task['cluster_id'] for a in selected}:
            variants = [a for a in selected if a.task['cluster_id'] == cluster]
            assert {a.task['contract']['change_scope'] for a in variants} == {'partial_update', 'full_replacement', 'read_only'}
            assert {a.task['metadata']['group'] for a in variants} == {'same_mechanism', 'near_miss', 'unrelated'}


def native_oracle(task, data):
    """Independent scalar/Boolean equations, not the native engine or formulas."""
    family, scope = task['metadata']['family'], task['contract']['change_scope']
    if task['domain'] == 'spreadsheet':
        x = {key: Fraction(str(value)) for key, value in data.items()}
        if family == 'production-capacity-workbook':
            gross = x['B3'] * x['B4']
            if scope == 'read_only':
                done = min(x['B2'], gross)
                return float(max(0, x['B2'] - done) + done * x['B6'] + x['B7'])
            usable = gross - min(gross, x['B5'])
            done = min(x['B2'], usable)
            result = {'C2': gross if scope == 'partial_update' else usable, 'C3': done,
                      'C4': max(0, x['B2'] - done),
                      'C5': (done if scope == 'partial_update' else usable) * x['B6'] + x['B7']}
        else:
            if scope == 'read_only':
                return float(x['B2'] + x['B3'] + 2 * x['B5'])
            if scope == 'partial_update':
                fusion = x['B3'] + x['B4'] * (x['B2'] - x['B3'])
                calibrated = fusion + x['B5']
                clipped = x['B7'] if calibrated > x['B7'] else calibrated
                clipped = x['B6'] if clipped < x['B6'] else clipped
                residual = calibrated - clipped
            else:
                fusion = x['B2'] - x['B3']
                calibrated = fusion * x['B8']
                clipped = sorted([x['B6'], x['B7'], calibrated])[1]
                residual = max(calibrated, clipped) - min(calibrated, clipped)
            result = {'C2': fusion, 'C3': calibrated, 'C4': clipped, 'C5': residual}
        return {key: float(value) for key, value in result.items()}
    facts = set(data)
    if family == 'document-release-workflow':
        reviewable = 'reviewable' in facts or {'draft', 'signed'} <= facts or (
            scope == 'full_replacement' and {'emergency', 'signed'} <= facts)
        approved = 'approved' in facts or (reviewable and 'peer' in facts and (
            scope != 'full_replacement' or 'legal' in facts)) or (scope != 'full_replacement' and 'emergency' in facts)
        released = 'released' in facts or (approved and 'clean' in facts and (scope != 'partial_update' or 'legal' in facts))
        values = {'reviewable': reviewable, 'approved': approved, 'released': released,
                  'archived': 'archived' in facts or released}
    else:
        sanitized = 'sanitized' in facts or {'raw', 'scrubbed'} <= facts
        eligible = 'eligible' in facts or ({'raw', 'request'} <= facts if scope == 'full_replacement'
                                          else sanitized and 'consent' in facts)
        purged = 'purged' in facts or (eligible and {'expired', 'hold_clear'} <= facts and (
            scope != 'partial_update' or 'request' in facts))
        values = {'sanitized': sanitized, 'eligible': eligible, 'purged': purged,
                  'retained': 'retained' in facts or 'legal_hold' in facts,
                  'audit_required': 'audit_required' in facts or purged}
    return sorted(key for key, present in values.items() if present)


@pytest.mark.parametrize('adapter', NATIVE, ids=lambda a: a.task['id'])
def test_native_gold_crosschecked_by_independent_host_equations(adapter):
    task = adapter.task
    for case in task['public_cases'] + task['hidden_cases']:
        data = {**task['inputs'], **case.get('overrides', {})} if adapter.domain == 'spreadsheet' else case['facts']
        expected = native_oracle(task, data)
        if adapter.domain == 'spreadsheet':
            assert case['expected'] == pytest.approx(expected)
        else:
            assert sorted(case['expected']) == expected


@pytest.mark.parametrize('adapter', [a for a in NATIVE if a.task['contract']['change_scope'] != 'read_only'],
                         ids=lambda a: a.task['id'])
def test_native_reference_random_recomputations_match_independent_host_oracle(adapter):
    rng = random.Random(547)
    task = deepcopy(adapter.task)
    cases = []
    for i in range(25):
        if adapter.domain == 'spreadsheet':
            if task['metadata']['family'] == 'production-capacity-workbook':
                data = {key: rng.randrange(12) for key in task['inputs']}
            else:
                data = {key: rng.randrange(-10, 11) for key in task['inputs']}
                data['B4'] = rng.randrange(5) / 4
            cases.append({'id': f'independent-native-{i}', 'overrides': data,
                          'expected': native_oracle(task, data)})
        else:
            facts = [name for name in task['vocabulary'] if rng.randrange(3) == 0]
            cases.append({'id': f'independent-native-{i}', 'facts': facts, 'expected': native_oracle(task, facts)})
    task['public_cases'], task['hidden_cases'] = [], cases
    result = t.NativeAdapter(task).evaluate(task['reference_artifact'])
    assert result['score'] == 1.0, result


def test_constructing_tasks_and_oracles_never_mutates_previous_panel():
    before = digest([a.task.to_dict() for a in CODING] + [a.task for a in NATIVE])
    sample = deepcopy(CALIBRATION[0].task.private_cases[0]['input'])
    original = deepcopy(sample)
    oracle(CALIBRATION[0].task.family, sample)
    assert sample == original
    fresh = t.calibration_tasks()
    fresh[0].task.metadata['controls']['reference']['logic.py'] = 'corrupt'
    assert digest([a.task.to_dict() for a in CODING] + [a.task for a in NATIVE]) == before
