"""Child prompt/record/repair integration with authored offline role replies."""
from dataclasses import replace

import pytest

from skillopt.execskill import audit, engineer as e, engineer_v291, engineer_v292, profiles as p
from tests.test_execskill_v291_engineer import run, GOOD, ALF_GOOD
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


CHILDREN = [('zebra-pc-v9', 'zebra-pc-v8', GOOD), ('alfworld-v6', 'alfworld-v5', ALF_GOOD)]


@pytest.mark.parametrize('configuration,parent,good', CHILDREN)
@pytest.mark.parametrize('mode', ['single', 'train'])
def test_child_prompt_record_and_shape_repair_reach_the_actual_engineer_path(configuration, parent, good, mode):
    hook = 'alf_before_step' if p.is_alfworld(configuration) else 'before_call'
    bad = 'def %s(view, state):\n    return 3\n' % hook
    ctx, package, record = run(bad, good, configuration=configuration, mode=mode)
    assert package is not None and package.procedures[0].source.strip() == good.strip()
    assert record['version'] == p.kind('engineer-v2-9-2')
    system = engineer_v292.system(configuration, train=mode == 'train')
    assert record['prompt_sha256'] == audit.text_sha256(system)
    assert system == engineer_v291.system(parent, train=mode == 'train').replace(
        '(v2.9.1)', '(v2.9.2)')
    assert record['fault_repair_calls'] == 1
    evidence = record['changes'][0]['fault_repair']['calls'][0]['request']['evidence']
    shape = next(row for row in evidence['signatures'] if row['kind'] == 'output_shape')
    assert shape['returned'] == 'int' and shape['expected'].startswith('None or {')
    assert ('discourage' in shape['expected']) == p.is_alfworld(configuration)
    for wire in ctx.roles.wire:
        if wire['label'].endswith('/propose'):
            assert wire['system'] == system
        elif '/fault-repair/' in wire['label']:
            assert wire['system'] == system + engineer_v291.FAULT_REPAIR_INSTRUCTION
    if mode == 'train':
        assert e.payload(replace(ctx, round=2, lint=record['lint']))['lint'] == record['lint']


@pytest.mark.parametrize('configuration,parent,good', CHILDREN)
@pytest.mark.parametrize('mode', ['single', 'train'])
def test_format_retry_uses_the_new_pinned_instruction_without_changing_parent_system(configuration, parent, good, mode):
    ctx, package, record = run(None, good, configuration=configuration, mode=mode)
    assert package is not None and len(record['format_retries']) == 1
    wire = next(row for row in ctx.roles.wire if '/format-retry/' in row['label'])
    assert wire['system'] == engineer_v292.system(configuration, train=mode == 'train') + engineer_v292.FORMAT_RETRY_SYSTEM
    assert record['format_retries'][0]['selected_by'] == 'single'
    assert all(audit.text_sha256(pin['text']) == pin['sha256'] for pin in engineer_v292.prompt_pins().values())
    assert 'change_id' not in engineer_v291.prompt_pins()['format_retry']['text']
