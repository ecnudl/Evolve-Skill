"""v2.14 additive registration; frozen parents and exact inherited method pins."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.execskill import (audit, budgets, instruction_start, manifest, profiles as p,
                               step, v210_import, v211_limits, zebralogic)
from tests import test_execskill_v212_profile as parent_tests

CAPTURE = Path(__file__).parent / 'fixtures/execskill/v214_parents_before.json'
SNAPSHOT = json.loads(CAPTURE.read_text())
CHILD = p.MAIN_V5


@pytest.mark.parametrize('name', sorted(SNAPSHOT['configurations']))
def test_all_35_preexisting_configuration_identities_are_byte_identical(name, monkeypatch):
    monkeypatch.setattr(parent_tests, 'SNAPSHOT', SNAPSHOT)
    parent_tests.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)


def test_preedit_capture_and_every_historical_profile_table_are_unchanged():
    assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == 'd22578c2e11da3890227863064d744e05876d0a7fd71f1a90baf97231d8e328b'
    assert len(SNAPSHOT['configurations']) == 35
    assert {n for n in p.CONFIGURATIONS if not p.is_v215(n) and not p.is_v217(n) and not p.is_implant_v5(n) and not p.is_v218(n)} - set(SNAPSHOT['configurations']) == {CHILD}
    for name, tables in SNAPSHOT['profile_tables'].items():
        found = manifest._plain({key: getattr(p, key)[name] for key in tables})
        assert json.dumps(found, sort_keys=True).encode() == json.dumps(tables, sort_keys=True).encode()


def test_order_chains_identity_and_import_reservation():
    assert p.CONFIGURATIONS[CHILD]['order'] == ('searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench', 'alfworld')
    assert p.active_benches(CHILD) == p.read_benches(CHILD) == p.CONFIGURATIONS[CHILD]['order']
    assert p.launchable_chains(CHILD) == ('G', 'D')
    assert p.RUN_ROOTS[CHILD] == '/data/execskill-20261031-main-v5'
    assert p.MAIN_V5_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert p.CHAIN_NAMESPACES[CHILD] == {'G': 'G-v5', 'D': 'D-v5'}
    assert p.REAL_RUN_EVIDENCE[CHILD] == 'main_v5_real_run'
    assert p.verified(p.record('authored', p.REAL_RUN_EVIDENCE[CHILD], {}))
    assert p.STAGE_READ[CHILD] and p.stage_arms_max(CHILD) == 4
    assert p.legacy.STAGE_READ[CHILD] is True
    assert p.legacy.stage_arms_max(CHILD) == 4
    assert p.legacy.read_arms_of(CHILD) == ('F', 'C', 'B', p.STAGES)
    assert p.legacy.estimate_arms(CHILD) == 5
    assert p.read_arms_of(CHILD) == ('F', 'C', 'B', p.STAGES)
    assert p.estimate_arms(CHILD) == 5
    assert not p.PLACEBO_ARMS[CHILD] and not p.TEST_WITHHOLDING[CHILD]
    assert not p.is_zebra(CHILD) and not p.is_v212(CHILD)
    assert p.train_rounds(CHILD, 'alfworld') == 0
    assert 'alfworld' not in p.CONFIG_STEP_CAPS[CHILD]
    assert v210_import.LEARNED_SOURCE_BYTES == 58596 and v210_import.LEARNED_PROCEDURES == 21


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench'])
def test_each_learning_step_selects_exact_parent_machinery(bench):
    parent = p.ZEBRA_PC_V13 if bench == p.ZEBRA else p.MAIN_V4
    assert p.machinery_configuration(CHILD, bench) == parent
    assert p.slice_spec(CHILD, bench) == p.slice_spec(parent, bench)
    assert p.audit_spec(CHILD, bench) == p.audit_spec(parent, bench)
    assert p.acceptance_rule(CHILD, bench) == p.ACCEPT_RULES[parent]
    assert p.accept_freshness(CHILD, bench) == p.ACCEPT_FRESHNESS[parent]
    assert p.confirm_freshness(CHILD, bench) == p.CONFIRM_FRESHNESS[parent]
    assert p.train_rounds(CHILD, bench) == 6 and p.train_patience(CHILD, bench) == 4
    assert p.ENGINEER_CALL_BUDGETS[CHILD] == p.ENGINEER_CALL_BUDGETS[parent] == 31
    assert p.TRAIN_ENGINEER_CALL_BUDGETS[CHILD] == p.TRAIN_ENGINEER_CALL_BUDGETS[parent] == 41
    assert p.ENGINEER_MAX_TOKENS[CHILD] == p.ENGINEER_MAX_TOKENS[parent] == 32768
    expected_caps = dict(p.CONFIG_STEP_CAPS[parent][bench])
    if bench == p.ZEBRA:
        expected_caps['selftest'] = 49400000
    assert p.CONFIG_STEP_CAPS[CHILD][bench] == expected_caps
    expected_schedule = __import__('copy').deepcopy(p.CONFIG_SCHEDULE_CELLS[parent][bench])
    if bench == 'spreadsheetbench':
        expected_schedule['selftest'].pop('livemath')
    elif bench == p.ZEBRA:
        expected_schedule['selftest']['officeqa'] = (0, 160)
    assert p.CONFIG_SCHEDULE_CELLS[CHILD][bench] == expected_schedule
    assert budgets.role_scope_caps(CHILD, bench) == budgets.role_scope_caps(parent, bench)
    for round in range(1, 7):
        assert p.confirm_spec(CHILD, bench, round) == p.confirm_spec(parent, bench, round)
    for mode in ('single', 'train'):
        for purpose in ('propose', 'fix', 'format_retry', 'audit_fix', 'fault_repair', 'inert_repair'):
            assert p.engineer_prompt(CHILD, bench, mode, purpose) == p.engineer_prompt(parent, bench, mode, purpose)
    for part in ('A', 'B'):
        assert audit.system_prompt(part, configuration=CHILD, bench=bench) == audit.system_prompt(part, configuration=parent, bench=bench)


def test_cards_preserve_instructions_and_neutral_zebra():
    cards = {b: zebralogic.CARD_TEXT if b == p.ZEBRA else instruction_start.pins()[b]['text'] for b in p.active_benches(CHILD)}
    assert instruction_start.active_cards(cards, CHILD) == cards
    assert all(instruction_start.original_card(b, text) == text for b, text in cards.items())
    with pytest.raises(Exception, match='Historical solver card'):
        instruction_start.active_cards({**cards, p.ZEBRA: 'changed'}, CHILD)


def test_glm_zebra_uses_existing_route_bound_and_timeout_pins():
    entry = p.main_v5_identity()['glm_zebra']
    assert entry == {'model': 'glm-5.3', 'max_tokens': 65536, 'read_timeout': 2400,
                     'branch': None, 'longest': None, 'nominal_M': None, 'ledger_bound': 65536}
    assert p.solver_tokens(p.CHAINS['D'], p.ZEBRA) == 16384
    assert p.read_timeout(p.CHAINS['D'], p.ZEBRA) == 600
    assert p.ledger_bound(p.CHAINS['D'], p.ZEBRA, branch='N', longest=60000) == 90000


def test_similarity_and_fired_share_preserve_every_parent():
    assert p.similar_pairs(CHILD) == (('searchqa', 'officeqa'), ('officeqa', 'spreadsheetbench'))
    for name in SNAPSHOT['configurations']:
        assert p.similar_pairs(name) == p.SIMILAR_PAIRS
    assert all(p.fired_share(b, CHILD) == p.FIRED_SHARES['home'] == 1 for b in p.read_benches(CHILD))


def test_worst_read_arithmetic_and_all_caps():
    items = {b: p.read_items(CHILD, b) for b in p.read_benches(CHILD)}
    assert items == {'searchqa': 400, 'officeqa': 172, p.ZEBRA: 200, 'spreadsheetbench': 279, 'alfworld': 134}
    assert sum(items.values()) == 1185
    assert p.TEST_READ_CELLS[CHILD] == {b: (2*n, 5*n) for b,n in items.items()}
    assert all(set(cells) <= set(items) for kinds in p.CONFIG_SCHEDULE_CELLS[CHILD].values()
               for cells in kinds.values())
    cell = {b: {'card': p.CELL_ANCHORS[b][1], 'procedure_assumed': True} for b in items}
    assert sum(p.read_estimate_terms(cell, 1, CHILD).values()) == 110056110
    assert p.estimate_test_read(cell, 3, CHILD) == 330168330
    cap = p.legacy._round_up(3*(110056110+5*16*520192),1000000)
    assert p.CONFIGURATIONS[CHILD]['test_read_cap'] == cap == 456000000
    assert sum(sum(c.values()) for c in p.CONFIG_STEP_CAPS[CHILD].values()) == 882100000
    assert p.CONFIGURATIONS[CHILD]['redo_reserve'] == 87000000
    assert p.CONFIGURATIONS[CHILD]['solver_cap'] == 1430000000
    assert p.CONFIG_GLM_CAP[CHILD] == (p.CONFIG_GLM_CAP[p.MAIN_V4]
        -sum(v211_limits.role_caps('livemath').values())+p.CONFIG_GLM_CAP[p.ZEBRA_PC_V13]) == 7070923008
    for chain in p.CHAINS:
        caps = budgets.chain_caps(chain, CHILD)
        assert caps[chain+':test'] == 456000000
        assert caps['overall'] == 8500923008
        assert not any('livemath' in k or ':alfworld:5' in k for k in caps)
        assert any(':zebralogic:3' in k for k in caps)
