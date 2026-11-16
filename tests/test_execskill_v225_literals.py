"""Every remaining parent literal in the 22 registered modules is classified."""
from collections import Counter
import json
from pathlib import Path
import re

from skillopt.execskill import profiles as p, v222_gate as gate

ROOT = Path(__file__).resolve().parents[1]
AUDIT = json.loads((ROOT/'tests/fixtures/execskill/v225_literals.json').read_text())


def current_sites():
    found=[]
    for name in AUDIT['scope_files']:
        for line in (ROOT/name).read_text().splitlines():
            if 'MAIN_V8' in line or "'main-v8'" in line or '"main-v8"' in line:
                found.append((name,line.strip()))
    return Counter(found)


def registered_sources():
    """The frozen audit plus only the reviewed v2.26 additive admissions."""
    expected = []
    for entry in AUDIT['sites']:
        source = entry['source']
        if entry['handling'] == 'widened explicit membership':
            assert entry['classification'] == 'inherited_behavior'
            source = re.sub(r'\b((?:p\.|protocol\.)?MAIN_V9)\b',
                lambda match: match[0] + ', ' + match[0].replace('MAIN_V9', 'MAIN_V10'), source)
            source = source.replace("'main-v9'", "'main-v9', 'main-v10'").replace(
                '"main-v9"', '"main-v9", "main-v10"')
        elif entry['file'] == 'skillopt/execskill/v222_smoke.py' and source == (
                'configuration = p.MAIN_V9 if p.is_v225(p.configuration_of(setting)) else p.MAIN_V8'):
            assert entry['handling'] == 'is_v225 dispatch to v225_smoke'
            source = 'configuration = p.configuration_of(setting) if p.is_v225(p.configuration_of(setting)) else p.MAIN_V8'
        expected.append((entry['file'], source))
    return Counter(expected)


def test_every_parent_literal_is_classified_and_no_new_site_is_silently_inherited():
    assert len(AUDIT['scope_files'])==22 and len(set(AUDIT['scope_files']))==22
    assert AUDIT['brief_reported_parent_sites']==94
    assert current_sites()==registered_sources()
    assert len(AUDIT['sites'])==AUDIT['current_source_lines']
    for entry in AUDIT['sites']:
        assert entry['classification'] in {'inherited_behavior','overridden_behavior','identity','frozen_artifact'}
        assert entry['function'] and entry['handling'] and entry['rationale']
        if entry['handling']=='widened explicit membership':
            assert 'MAIN_V9' in entry['source'] or 'main-v9' in entry['source']


def test_runtime_identity_literals_were_replaced_and_parent_draws_remain_equal():
    runtime=(ROOT/'skillopt/execskill/v222_runtime.py').read_text()
    split=(ROOT/'skillopt/execskill/v221_split.py').read_text()
    assert "recorded['configuration'] == p.MAIN_V8" not in runtime
    assert "'configuration': profiles.MAIN_V8" not in split
    pools={bench:[{'task_id':bench+'-%03d'%i,'benchmark':bench,'partition':'practice',
        'public':{'question':'Authored question.'},'private':{'answer':'authored'}} for i in range(100)]
        for bench in p.MAIN_V5_ORDER}
    parent=gate.harm_slices(pools,configuration=p.MAIN_V8)
    child=gate.harm_slices(pools,configuration=p.MAIN_V9)
    assert parent==child
    old,new=gate.registration(parent,configuration=p.MAIN_V8),gate.registration(child,configuration=p.MAIN_V9)
    assert old['configuration']==p.MAIN_V8 and new['configuration']==p.MAIN_V9
    assert {k:v for k,v in old.items() if k not in ('configuration','sha256')}=={
        k:v for k,v in new.items() if k not in ('configuration','sha256')}
