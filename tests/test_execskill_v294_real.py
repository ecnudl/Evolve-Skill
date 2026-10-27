"""Historical round-5 replies with authored inputs and in-process fake services.

The supplied source contains only pure parsing/search functions. Replay executes
that inspected source, including the authored wrapper repair, without containers,
models or external I/O. Passing these checks is not a real-run effect estimate.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.execskill import engineer as e, engineer_reader, engineer_v28, profiles as p
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import context, detail
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v29_audit import Judge
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


FIXTURE = Path(__file__).parent / 'fixtures/execskill/zpc9_r5_replies.json'
FIXTURE_SHA256 = '3ad6732695a4a9190dbe490617517c9f0eec04c1299a5ecccd72704fafb80bd7'
REPLY = {row['label']: row['reply'] for row in json.loads(FIXTURE.read_text())}['propose']
IDS = ['zebra-csp-solver-v2', 'zebra-clue-indexer']
WRAPPER = '\ndef before_call(view, state):\n    return _run(view)\n'
PUBLIC = {
    'question': (
        'There are 2 houses, numbered 1 to 2 from left to right, as seen from across the street.\n'
        '- Name: `Alice`, `Bob`.\n'
        '- Color: `red`, `blue`.\n'
        '## Clues:\n'
        '1. Alice is in the first house.\n'
        '2. Bob is in the second house.\n'
        '3. red is in the first house.\n'
        '4. blue is in the second house.\n'
    ),
    'columns': ['Name', 'Color'],
}


def actual_context(configuration, mode):
    ctx, _ = context(configuration=configuration, mode=mode, views=[PUBLIC])
    if mode == 'train':
        ctx = replace(ctx, current=list(ctx.trajectories))
    ctx.audit_judges = {'G': Judge(), 'D': Judge()}
    return ctx


def actual_run(configuration, mode, *, repairs):
    ctx = actual_context(configuration, mode)
    rows = engineer_reader.read(REPLY, ctx)
    replies = [engineer_reply({'findings': []}, [])] if mode == 'train' else []
    replies.append(REPLY)
    if repairs:
        replies.extend(engineer_reply({'changes': [row['original']]}, [row['source'] + WRAPPER])
                       for row in rows)
    ctx.roles = WireRoles(replies)
    candidate, record = e.run_train(ctx) if mode == 'train' else e.run(ctx)
    assert not ctx.roles.replies
    return ctx, candidate, record, rows


@pytest.mark.parametrize('configuration', ['zebra-pc-v11', 'zebra-pc-v10', 'zebra-pc-v9'])
def test_real_reply_bytes_and_source_derived_hooks_are_preserved(configuration):
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    ctx = actual_context(configuration, 'single')
    rows = engineer_reader.read(REPLY, ctx)
    assert [row['original']['id'] for row in rows] == IDS
    assert all(row['original']['hooks'] == ['before_call'] for row in rows)
    assert all(engineer_reader.defined_hooks(row['source']) == ['applies'] for row in rows)
    assert all('def _run(view):' in row['source'] and not row['error'] for row in rows)
    changes, failures = engineer_v28.read_call(ctx, REPLY, 'a' * 64, 'propose')
    assert not failures and len(changes) == 2 and not ctx.roles.calls
    assert [change.source for change in changes] == [row['source'] for row in rows]


@pytest.mark.parametrize('mode', ['single', 'train'])
def test_real_round5_changes_each_get_one_wrapper_repair_then_reach_actual_audit(mode):
    ctx, candidate, record, sources = actual_run('zebra-pc-v11', mode, repairs=True)
    assert candidate is not None and len(candidate.procedures) == 2
    assert record['version'] == p.kind('engineer-v2-9-4')
    assert record['inert_repair_calls'] == 2 and record['fault_repair_calls'] == 0
    assert record['format_retries'] == [] and record['calls'] == 3
    calls = [wire for wire in ctx.roles.wire if '/inert-repair/' in wire['label']]
    assert len(calls) == 2
    for n, (row, original, procedure, wire) in enumerate(
            zip(record['changes'], sources, candidate.procedures, calls), 1):
        before, after = row['attempts']
        assert before['passed'] and before['inert'] and before['failed'] is None
        assert before['inert_causes'] == ['no_effect_hook']
        evidence = before['inert_evidence']['no_effect_hook']
        assert evidence['declared_hooks'] == ['before_call']
        assert 'applies' in evidence['defined_functions'] and '_run' in evidence['defined_functions']
        assert 'before_call' not in evidence['defined_functions']
        assert evidence['effect_hooks'] == ['before_call']
        assert detail(before, 'C6b')['fires_on'] == 1
        output = detail(before, 'C6c')
        assert output['status'] == 'not_applicable' and output['reason'] == 'no_note_writing_hook'
        assert after['passed'] and not after['inert'] and detail(after, 'C6c')['nonempty'] == 1
        assert all(check['passed'] for check in before['checks'] if not check.get('informational'))
        assert all(check['passed'] for check in after['checks'] if not check.get('informational'))
        assert row['survived'] and not row['inert'] and not row['deferred']
        assert row['kept_attempt'] == 1 and row['fix_calls'] == row['audit_fix_calls'] == 0
        repair = row['inert_repair']
        assert repair['causes'] == ['no_effect_hook'] and repair['stop_reason'] == 'fixed'
        assert repair['kept_index'] == 1 and len(repair['calls']) == 1
        event = repair['calls'][0]
        assert all(event[key] for key in ('call', 'parsed', 'checked', 'passed_fatal_checks', 'kept'))
        assert event['inert_after'] is False
        assert wire['label'].endswith('inert-repair/%d/1' % n)
        request = json.loads(wire['user'])
        assert request['request'] == 'inert_repair' and request['bench'] == 'zebralogic'
        assert request['change']['source'] == original['source']
        assert request['evidence'] == before['inert_evidence']
        assert 'no_effect_hook' in request['instruction'] and 'before_call' in request['instruction']
        assert wire['system'].endswith(request['instruction'])
        assert procedure.source.strip() == (original['source'] + WRAPPER).strip()
        assert 'before_call' in procedure.hooks
        assert len(row['audits']) == 1 and not row['audits'][0]['confirmed']
        assert row['audits'][0]['requests']
    assert all(judge.calls for judge in ctx.audit_judges.values())


@pytest.mark.parametrize('configuration', ['zebra-pc-v9', 'zebra-pc-v10'])
@pytest.mark.parametrize('mode', ['single', 'train'])
def test_real_round5_older_configs_stay_inert_without_new_fields_or_repair(configuration, mode):
    ctx, candidate, record, _ = actual_run(configuration, mode, repairs=False)
    assert candidate is None and len(record['changes']) == 2
    assert record['calls'] == 1 and record['fault_repair_calls'] == 0
    assert record['format_retries'] == [] and 'inert_repair_calls' not in record
    assert all('/inert-repair/' not in wire['label'] for wire in ctx.roles.wire)
    assert not any(judge.calls for judge in ctx.audit_judges.values())
    for row in record['changes']:
        assert row['survived'] and row['inert'] and not row['deferred']
        assert row['fix_calls'] == 0 and len(row['attempts']) == 1
        assert 'inert_causes' not in row and 'inert_repair' not in row
        checked = row['attempts'][0]
        assert checked['passed'] and checked['failed'] is None
        assert 'inert_causes' not in checked and 'inert_evidence' not in checked
        assert detail(checked, 'C6c')['reason'] == 'no_note_writing_hook'
