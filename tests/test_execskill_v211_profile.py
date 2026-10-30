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
SNAPSHOT = json.loads((ROOT / 'tests/fixtures/execskill/v211_parents_before.json').read_text())


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


def test_all_32_historical_profile_tables_and_fixtures_are_unchanged():
    assert len(SNAPSHOT['configurations']) == 32
    for name, tables in SNAPSHOT['profile_tables'].items():
        assert manifest._plain({key: getattr(p, key)[name] for key in tables}) == tables
    # Keep the pre-edit capture intact; bytecode is not copied source evidence.
    from skillopt.execskill.v211_smoke import CAPTURED_GENERATED_CACHE
    assert len(CAPTURED_GENERATED_CACHE) == 2
    assert {path for path in SNAPSHOT['fixtures_sha256'] if '__pycache__' in path} == CAPTURED_GENERATED_CACHE
    assert len(set(SNAPSHOT['fixtures_sha256']) - CAPTURED_GENERATED_CACHE) == 28
    for path, sha in SNAPSHOT['fixtures_sha256'].items():
        if path in CAPTURED_GENERATED_CACHE:
            continue
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha, path


def test_main_v4_predicate_matrix_and_identity():
    name = p.MAIN_V4
    assert {n for n in p.CONFIGURATIONS if not p.is_v212(n) and not p.is_v213(n) and not p.is_v214(n)} - set(SNAPSHOT['configurations']) == {name}
    assert all(fn(name) for fn in (p.is_v23, p.is_v24, p.is_v25, p.is_v26, p.is_v27,
        p.is_v28, p.is_v29, p.is_v291, p.is_v292, p.is_v293, p.is_v294, p.is_v295, p.is_v210, p.is_v211))
    assert not any(fn(name) for fn in (p.is_v296, p.is_v297, p.is_zebra, p.is_alfworld, p.is_alfworld_v2))
    assert p.launchable_chains(name) == ('G', 'D')
    assert p.active_benches(name) == p.BENCHES
    assert p.RUN_ROOTS[name] == '/data/execskill-20261029-main-v4'
    assert p.CHAIN_NAMESPACES[name] == {'G': 'G-v4', 'D': 'D-v4'}
    assert p.REAL_RUN_EVIDENCE[name] == 'main_v4_real_run'
    assert p.read_arms_of(name) == ('F', 'C', 'B')
    assert p.ENGINEER_CALL_BUDGETS[name] == 31 and p.TRAIN_ENGINEER_CALL_BUDGETS[name] == 41
    for bench in p.BENCHES:
        assert p.uses_readable_alf_format(name, bench) == (bench == 'alfworld')
        assert p.uses_episode_audit(name, bench) == (bench == 'alfworld')
        if bench != 'alfworld':
            assert p.train_rounds(name, bench) == 6 and p.train_patience(name, bench) == 4
