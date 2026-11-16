"""Rebuild the 46-parent fixture using only source obtained by git show e589b5b.

Run from the working-copy root. The temporary base checkout stays inside it;
neither the index nor a branch is changed.
"""
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

BASE = 'e589b5b'
ROOT = Path(__file__).resolve().parents[3]
TARGET = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else
          ROOT / 'tests/fixtures/execskill/v226_parents_before.json')

CAPTURE = r'''
import hashlib, json, sys
from pathlib import Path
from skillopt.coevo5.outcomes import Verdict
from skillopt.execskill import audit, budgets, judge, manifest, profiles as p, step
from tests.test_execskill_zpc_regression import FEATURES
before = json.loads(Path('tests/fixtures/execskill/v225_parents_before.json').read_text())
found = {key: value for key, value in before.items() if key not in ('configurations', 'profile_tables', 'version')}
found.update(version='v2.26-parents-before', source_commit='e589b5b', configurations={}, profile_tables={})
for name in sorted(p.CONFIGURATIONS):
    runtime = before['configurations'].get(name, {}).get('runtime', {'configuration': name})
    row = manifest._plain({
        'features': {key: getattr(p, key).get(name, {'unregistered': True}) for key in FEATURES},
        'registered': manifest.registered(name), 'prompts': manifest.prompt_sha(name),
        'roles': manifest.role_settings(name), 'budgets': {c: budgets.chain_caps(c, name) for c in p.CHAINS},
        'call_budgets': [p.ENGINEER_CALL_BUDGETS[name], p.TRAIN_ENGINEER_CALL_BUDGETS[name]],
        'units': list(step.training_units(name)), 'runtime': runtime,
        'k1_judge': {label: judge.judge('alfworld', {'game_file': 'authored'}, {}, case['prediction'],
            runtime=runtime, score=case['score'], verdict=Verdict(**case['verdict']))
            for label, case in before['k1_episodes'].items()},
        'audit_views': {key: audit.public_view('alfworld', view)
                        for key, view in before['audit_public_inputs'].items()},
        'audit_keys': {key: audit.situation_key({'item': before['audit_item'], 'step': int(key),
                        'view': audit.public_view('alfworld', view)})
                       for key, view in before['audit_public_inputs'].items()}})
    if name in before['configurations']:
        assert row == before['configurations'][name], name
    found['configurations'][name] = row
    found['profile_tables'][name] = manifest._plain({key: table[name] for key, table in vars(p).items()
        if key.isupper() and isinstance(table, dict) and name in table})
assert len(found['configurations']) == 46 and 'main-v9' in found['configurations']
payload = (json.dumps(found, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
Path(sys.argv[1]).write_bytes(payload)
print(str(len(found['configurations'])) + ' configurations; sha256=' + hashlib.sha256(payload).hexdigest())
'''

scratch = ROOT / '.review-scratch'
scratch.mkdir(exist_ok=True)
paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE,
                                 'skillopt', 'scripts', 'tests', 'docs'], cwd=ROOT, text=True).splitlines()
with TemporaryDirectory(prefix='v226-parents-', dir=scratch) as directory:
    base = Path(directory)
    for name in paths:
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(['git', 'show', BASE + ':' + name], cwd=ROOT))
    subprocess.run([sys.executable, '-c', CAPTURE, str(TARGET)], cwd=base, check=True,
                   env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
