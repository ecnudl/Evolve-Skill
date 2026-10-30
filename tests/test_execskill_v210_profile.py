"""Instruction-start identities and the full pre-edit historical configuration capture."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.coevo5.outcomes import Verdict
from skillopt.execskill import (audit, budgets, engineer, instruction_start, judge, manifest,
                               profiles as p, protocol, routes, smoke, step)
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_zpc_regression import FEATURES

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = json.loads((ROOT / 'tests/fixtures/execskill/v210_parents_before.json').read_text())


@pytest.mark.parametrize('name', sorted(SNAPSHOT['configurations']))
def test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name):
    before = SNAPSHOT['configurations'][name]
    found = manifest._plain({'features': {key: getattr(p, key).get(name, {'unregistered': True}) for key in FEATURES},
        'registered': manifest.registered(name), 'prompts': manifest.prompt_sha(name),
        'roles': manifest.role_settings(name), 'budgets': {c: budgets.chain_caps(c, name) for c in p.CHAINS},
        'call_budgets': [p.ENGINEER_CALL_BUDGETS[name], p.TRAIN_ENGINEER_CALL_BUDGETS[name]],
        'units': list(step.training_units(name)), 'runtime': before['runtime'],
        'k1_judge': {label: judge.judge('alfworld', {'game_file': 'authored'}, {}, case['prediction'],
            runtime=before['runtime'], score=case['score'], verdict=Verdict(**case['verdict']))
            for label, case in SNAPSHOT['k1_episodes'].items()},
        'audit_views': {key: audit.public_view('alfworld', view)
                        for key, view in SNAPSHOT['audit_public_inputs'].items()},
        'audit_keys': {key: audit.situation_key({'item': SNAPSHOT['audit_item'], 'step': int(key),
                        'view': audit.public_view('alfworld', view)})
                       for key, view in SNAPSHOT['audit_public_inputs'].items()}})
    encoded = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    assert encoded(found) == encoded(before)


def test_historical_fixtures_are_not_rewritten_in_a_standalone_snapshot():
    captured = json.loads((ROOT / 'tests/fixtures/execskill/v210_protected_fixture_sha256.json').read_text())['sha256']
    for name, sha in captured.items():
        assert name.startswith('tests/fixtures/')
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name


@pytest.mark.parametrize('name,namespaces,evidence,arms', [
    (p.BASELINE_V210, {'G': 'G-base210', 'D': 'D-base210'}, 'baseline_v210_real_run', ('C', 'B')),
    (p.MAIN_V3, {'G': 'G-v3', 'D': 'D-v3'}, 'main_v3_real_run', ('F', 'C', 'B'))])
def test_two_new_identities_are_only_v23_feature_family(name, namespaces, evidence, arms, tmp_path):
    assert {name for name in p.CONFIGURATIONS if not p.is_v211(name) and not p.is_v212(name) and not p.is_v213(name)} - set(SNAPSHOT['configurations']) == {p.BASELINE_V210, p.MAIN_V3}
    assert p.is_v23(name) and p.is_v210(name)
    assert not any(fn(name) for fn in (p.is_v24, p.is_v25, p.is_v26, p.is_v27, p.is_v28,
        p.is_v29, p.is_v291, p.is_v292, p.is_v293, p.is_v294, p.is_v295, p.is_v296, p.is_v297))
    assert p.CONFIGURATIONS[name]['order'] == p.BENCHES
    assert p.launchable_chains(name) == ('G', 'D')
    assert p.RUN_ROOTS[name] == '/data/execskill-20261029-' + name
    assert p.CHAIN_NAMESPACES[name] == namespaces
    assert p.REAL_RUN_EVIDENCE[name] == evidence
    assert p.verified(p.record('authored', evidence, {}))['evidence'] == evidence
    assert p.read_arms_of(name) == protocol.read_arms_of(name) == arms
    assert not p.STAGE_READ[name] and not p.TEST_WITHHOLDING[name] and not p.PLACEBO_ARMS[name]
    assert p.ACCEPT_FRESHNESS[name] == 'fivebench_slices_after_main_v2_2_v2_3_not_launched'
    assert p.ACCEPT_RULES[name] == p.ACCEPT_RULES[p.MAIN_V2_3]
    assert p.IDENTICAL_REQUEST_REUSE[name]
    assert routes.current(tmp_path, configuration=name, chain='D') == 'B'
    for old in SNAPSHOT['configurations']:
        assert p.TEST_WITHHOLDING[old] and p.PLACEBO_ARMS[old]


def test_instruction_fixture_is_exact_and_mutation_is_refused(tmp_path, monkeypatch):
    pinned = instruction_start.pins()
    assert [pinned[b]['chars'] for b in p.BENCHES] == [1846, 2926, 2068, 2907, 2301]
    for entry in pinned.values():
        assert hashlib.sha256(entry['text'].encode()).hexdigest() == entry['sha256']
    forged = json.loads(instruction_start.FIXTURE.read_text())
    forged['instructions']['officeqa']['text'] += 'changed'
    forged['instructions']['officeqa']['sha256'] = hashlib.sha256(forged['instructions']['officeqa']['text'].encode()).hexdigest()
    forged['instructions']['officeqa']['chars'] += 7
    path = tmp_path / 'instructions.json'
    path.write_text(json.dumps(forged))
    monkeypatch.setattr(instruction_start, 'FIXTURE', path)
    with pytest.raises(ValueError, match='fixture hash'):
        instruction_start.pins()


@pytest.mark.parametrize('name', [p.BASELINE_V210, p.MAIN_V3])
def test_cards_are_verbatim_idempotent_and_leave_original_bytes_recoverable(name):
    cards = {b: instruction_start.pins()[b]['text'] for b in p.BENCHES}
    active = instruction_start.active_cards(cards, name)
    assert instruction_start.active_cards(active, name) == active
    assert instruction_start.original_cards(active, name) == cards
    for bench in p.BENCHES:
        assert active[bench] == cards[bench] == instruction_start.pins()[bench]['text']
    assert instruction_start.active_cards(cards, p.MAIN_V2_3) == cards


@pytest.mark.parametrize('train', [False, True])
def test_actual_engineer_request_sees_active_card_and_the_one_new_sentence(train):
    from tests.test_execskill_v24_engineer import context
    from tests.test_execskill_v24_feedback_isolation import WireRoles
    ctx, _ = context(configuration=p.MAIN_V2_3, bench='officeqa', mode='train' if train else 'single')
    ctx = replace(ctx, configuration=p.MAIN_V3, card=instruction_start.pins()['officeqa']['text'])
    ctx.roles = WireRoles(['authored reply'])
    assert ctx.card == instruction_start.pins()['officeqa']['text']
    reply, call = engineer._ask(ctx, {'card': ctx.card}, 'propose')
    assert reply == 'authored reply' and call
    system = ctx.roles.wire[0]['system']
    parent = engineer.ENGINEER_SYSTEM_V23 if train else engineer.ENGINEER_SYSTEM_SINGLE_V23
    assert system == parent + '\n' + instruction_start.ENGINEER_SENTENCE
    pinned = manifest.prompt_sha(p.MAIN_V3)
    assert hashlib.sha256(system.encode()).hexdigest() == (pinned['v2']['engineer'] if train else pinned['engineer'])


@pytest.mark.parametrize('name', [p.BASELINE_V210, p.MAIN_V3])
def test_reduced_caps_have_exact_arm_arithmetic_and_only_learning_step_scopes(name):
    sizes = {b: n for b, (n, _) in p.TEST_READ_CELLS[p.MAIN_V2_3].items()}
    assert sum(sizes.values()) == 1110
    assert p.TEST_READ_CELLS[name] == {b: (2*n, n if name == p.MAIN_V3 else 0) for b, n in sizes.items()}
    per_cell = {b: {'card': p.CELL_ANCHORS[b][1], 'procedure_assumed': True} for b in p.BENCHES}
    terms = p.read_estimate_terms(per_cell, 1, name)
    assert terms == {b: Fraction(p.CELL_ANCHORS[b][1]) * n * (Fraction(18, 5) if name == p.MAIN_V3 else 2)
                     for b, n in sizes.items()}
    expected_read = protocol._round_up(3*(sum(terms.values())+5*16*p.READ_RESERVATION), p.MILLION)
    assert p.CONFIGURATIONS[name]['test_read_cap'] == expected_read
    assert expected_read == (238000000 if name == p.MAIN_V3 else 188000000)
    for chain in p.CHAINS:
        caps = budgets.chain_caps(chain, name)
        assert all(type(value) is int and value > 0 for value in caps.values())
        assert not any(':alfworld:' in scope for scope in caps)
        assert set(smoke._scope_cells(chain, name)) == {key for key in caps if key != 'overall'
            and not key.endswith(':glm') and ':role:' not in key}
        if name == p.BASELINE_V210:
            assert set(caps) == {'overall', chain+':solver', chain+':test'}
    if name == p.BASELINE_V210:
        assert step.training_units(name) == ()
        assert smoke.glm_projection({}, name) == {}
    else:
        assert step.training_units(name) == step.training_units(p.MAIN_V2_3)
        for bench, removed in [('searchqa',1000), ('officeqa',400), ('livemath',400), ('spreadsheetbench',240)]:
            before = p.CONFIG_SCHEDULE_CELLS[p.MAIN_V2_3][bench]
            after = p.CONFIG_SCHEDULE_CELLS[name][bench]
            assert after['accept'][bench] == (before['accept'][bench][0], before['accept'][bench][1]-removed)
            assert after['examiner'][bench][1] == before['examiner'][bench][1]-p.G_ACC[bench]
            for kind in ('run', 'selftest'):
                assert after[kind] == before[kind]
                assert p.CONFIG_STEP_CAPS[name][bench][kind] == p.CONFIG_STEP_CAPS[p.MAIN_V2_3][bench][kind]


@pytest.mark.parametrize('train', [False, True])
def test_sealed_engineer_record_binds_the_prompt_that_was_actually_sent(train):
    from tests.execskill_fakes import engineer_reply
    from tests.test_execskill_v24_engineer import context
    from tests.test_execskill_v24_feedback_isolation import WireRoles
    ctx, _ = context(configuration=p.MAIN_V2_3, bench='officeqa', mode='train' if train else 'single')
    ctx = replace(ctx, configuration=p.MAIN_V3, card=instruction_start.pins()['officeqa']['text'])
    ctx.roles = WireRoles([engineer_reply({'findings': []}, []), engineer_reply({'changes': []}, [])]
                         if train else [engineer_reply({'changes': []}, [])])
    _, record = engineer.run_train(ctx) if train else engineer.run(ctx)
    pinned = manifest.prompt_sha(p.MAIN_V3)
    assert record['prompt_sha256'] == (pinned['v2']['engineer'] if train else pinned['engineer'])
    matching = [row for row in ctx.roles.wire if row['system'] == instruction_start.engineer_system(p.MAIN_V3, train=train)]
    assert matching and hashlib.sha256(matching[0]['system'].encode()).hexdigest() == record['prompt_sha256']


@pytest.mark.parametrize('name', [p.BASELINE_V210, p.MAIN_V3])
def test_real_registered_historical_cards_are_instructions_and_pass_without_change(name):
    from scripts.run_execskill import CARD_IDENTITY
    instructions = instruction_start.pins()
    cards = {bench: entry['text'] for bench, entry in instructions.items()}
    for bench, (chars, prefix) in CARD_IDENTITY.items():
        assert len(cards[bench]) == chars
        assert hashlib.sha256(cards[bench].encode()).hexdigest().startswith(prefix)
    assert instruction_start.active_cards(cards, name) == cards
    assert instruction_start.active_cards(cards, p.MAIN_V2_3) == cards


@pytest.mark.parametrize('name', [p.BASELINE_V210, p.MAIN_V3])
@pytest.mark.parametrize('alteration', ['public_card', 'append', 'newline', 'blank'])
def test_v210_cards_refuse_public_card_concatenation_or_instruction_drift(name, alteration):
    instruction = instruction_start.pins()['officeqa']['text']
    card = {'public_card': 'Authored public task card.', 'append': instruction + '\n\n' + instruction,
            'newline': instruction + '\n', 'blank': ''}[alteration]
    with pytest.raises(ValueError, match='Historical solver card must equal the frozen instruction'):
        instruction_start.active_cards({'officeqa': card}, name)
    assert instruction_start.active_cards({'officeqa': card}, p.MAIN_V2_3) == {'officeqa': card}
