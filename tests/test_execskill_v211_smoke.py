"""Executable child smoke and fail-closed receipt tests; all providers are authored fakes."""
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import fixtures, manifest, profiles as p, v211_smoke as smoke, v211_stages as stages
from skillopt.execskill import v211_smoke_controls as controls, v211_limits, v211_fixtures
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v211_rehearsal import build, offline  # noqa: F401
from tests.test_execskill_v211_manifest import setup


def test_zero_call_adapter_controls_keep_repair_fallback_separate_from_cost(tmp_path):
    root=tmp_path/'fixtures'
    v211_fixtures.make(root)
    result=controls.controls(root)
    assert result['passed'] and result['external_calls']==result['model_calls']==0
    assert result['evidence']=='engineering_fixture' and not result['benchmark_effect_evidence']
    assert result['repair_fallback']['shell']['fallback']=='second_call_fallback'
    assert result['requested_repair']['shell']['deciding_receipt']==1


def test_s3_all_four_real_engineer_paths_and_measured_roles(tmp_path,monkeypatch):
    setting,services,_=build(tmp_path,monkeypatch)
    monkeypatch.setattr(stages,'fixture_pools',lambda st:st.pools)
    local=smoke._stage_setting(setting,'S3')
    result=stages.s3(local,services)
    assert result['passed'], {b: (r['drills']['passed'], r['real_engineer']['engineer']['proposals']) for b,r in result['benches'].items()}
    for bench,row in result['benches'].items():
        assert set(row['role_measurements'])==set(v211_limits.role_calls(bench))
        assert all(v['calls']>0 and v['per_call']>0 for v in row['role_measurements'].values())
        assert row['drills']['fault_repair']['calls'] and row['drills']['inert_repair']['calls']
        assert row['drills']['format_retry'] and row['drills']['audit_fix']['call']
        assert row['confirm']['confirm']['exercise'] and not row['benchmark_effect_evidence']
        for control in row['authored_controls'].values():
            assert control['passed'] and control['evidence']=='engineering_fixture'
            assert control['model_calls']==0 and control['excluded_from_cost_projection']
        final=row['authored_controls']['audit2']
        assert final['sources']==['confirm','train'] and final['stale_source_situations']=={'note_source':0,'package_source':0}
        assert final['candidate_identity_unchanged'] and final['after_package_sha256']==final['expected_fixture_package_sha256']


def test_s2_refuses_short_authored_pool_before_dispatch(tmp_path,monkeypatch):
    setting,services,_=build(tmp_path,monkeypatch)
    monkeypatch.setattr(stages,'fixture_pools',lambda st:{'searchqa':st.pools['searchqa'][:3]})
    with pytest.raises(ValueError,match='Exact S2'):
        stages.s2(setting)


def test_schedule_pins_caps_probes_and_scarce_fixture_choice():
    value=smoke.schedule()
    assert value['caps']==manifest._plain(v211_limits.smoke_identity())
    assert value['D_S1'] is False and value['scarce_supply']=='authored_fixtures_only'
    assert value['role_cost_probes']==stages.role_probe_pins()
    assert sum(sum(v) for v in value['caps']['stages']['S2']['solver_cells'].values())==172


def test_projection_requires_all_actual_roles_and_next_reservation():
    cells={b:{'measurements':{'actual':100,'per_class':{b:{'card':{'cells':1,'tokens':50},
        'procedure':{'cells':1,'tokens':50}}},'request_bytes':{b:1000}},'settled_tokens':100} for b in p.BENCHES}
    roles={b:{'role_measurements':{r:{'calls':1,'per_call':100,'request_bytes':1000}
        for r in v211_limits.role_calls(b)},'confirm_measurements':{}} for b in p.BENCHES[:-1]}
    m={'clients':{'solver':{c:{'B':{b:65536 for b in p.BENCHES}} for c in p.CHAINS}}}
    result=stages.projection(m,{'benches':cells},{'benches':roles})
    assert result['passed'] and result['all_scopes_projected']
    for c in p.CHAINS:
        assert result['overall'][c]['projected']==result['solver_scopes'][c+':solver']['projected']+result['method_scopes'][c+':glm']['needed']
    del roles['officeqa']['role_measurements']['leakage']
    with pytest.raises(ValueError,match='Measured roles'):
        stages.projection(m,{'benches':cells},{'benches':roles})


def test_sx_real_training_sealed_acceptance_round_consumption_and_scopes(tmp_path,monkeypatch):
    setting,services,fakes=build(tmp_path,monkeypatch)
    rows=[]
    for i in range(280):
        item=deepcopy(setting.pools['searchqa'][0])
        item['task_id']='sx-authored-%03d'%i
        item['public']['question']='Fixture record %d: identify public value 17.'%i
        rows.append(item)
    setting.pools['searchqa']=rows
    monkeypatch.setattr(stages,'fixture_pools',lambda st:st.pools)
    result=stages.sx(setting,services)
    assert result['passed'],result
    assert result['train_cells']>0 and result['cells']>0
    assert result['rows']['acceptance'] and result['rows']['consumption']
    assert all(row['open']==0 and row['settled']<=row['cap'] for row in result['all_scopes'].values())
    assert 'smoke:role:audit_d' in result['all_scopes']
    before=(len(fakes['G'].requests),len(fakes['roles'].seen))
    assert stages.sx(setting,services)==result
    assert before==(len(fakes['G'].requests),len(fakes['roles'].seen))


def test_structural_smoke_passes_but_fixture_stage_cannot_authorize_readiness(tmp_path,monkeypatch):
    from dataclasses import replace
    checked,options,_=setup(tmp_path,monkeypatch)
    path=tmp_path/'manifest.json'
    m=smoke.make_manifest(path,**options)
    monkeypatch.setattr(manifest,'verify_code',lambda value:None)
    structural=smoke.structural_smoke(path,out=tmp_path/'structural')
    assert structural['passed'] and structural['model_calls']==0 and not structural['measured_readiness']
    case=tmp_path/'fake';case.mkdir()
    setting,services,_=build(case,monkeypatch)
    setting=replace(setting,run=m[p.RECORD_HASH],root=Path(m['root']))
    with pytest.raises(FileNotFoundError):
        smoke.run_stage(path,'S2',_setting=setting,_services=services)
    got=smoke.run_stage(path,'S0',_setting=setting,_services=services)
    assert got['result']['passed'] and not got['measured'] and got['evidence']=='engineering_fixture'
    assert smoke.run_stage(path,'S0',_setting=setting,_services=services)==got
    monkeypatch.setattr(manifest,'load',lambda *a,**k:m)
    # Complete-looking fixture receipts remain barred from readiness.
    for stage in smoke.STAGES[1:]:
        record={k:deepcopy(v) for k,v in got.items() if k not in ('version','evidence',p.RECORD_HASH)}
        record.update(stage=stage,result={'passed':True})
        write_json(smoke._stage_path(setting.root,stage),p.record('v211-smoke-stage','engineering_fixture',record))
    with pytest.raises(ValueError,match='passing measured'):
        smoke.summarize(path)
    assert not (setting.root/smoke.RESULT).exists()


def test_zero_call_controls_accept_actual_smoke_evidence_without_relabelling_candidate(tmp_path,monkeypatch):
    from dataclasses import replace
    from skillopt.execskill import step, v211_audit_control, v211_confirm_control
    setting,services,_=build(tmp_path,monkeypatch)
    setting=replace(setting,evidence='smoke')  # Providers stay local scripted fakes.
    monkeypatch.setattr(stages,'fixture_pools',lambda st:st.pools)
    local=smoke._stage_setting(setting,'S3')
    st,cut=stages.fixture_step(local,services,'searchqa','control-evidence-regression')
    step._run(st,cut)
    drill=stages._drills(st,cut)
    candidate=step._package(st,drill['candidate_sha256'])
    step._train_eval(st,cut,1,st.parent,candidate,None)
    confirmed=step._confirm_eval(st,cut,1,st.parent,candidate,exercise=True)
    before=(candidate.sha256,st.setting.budget.snapshot())
    confirmation=v211_confirm_control.confirmation_controls(st,cut,candidate,confirmed)
    audit=v211_audit_control.audit2_control(st,candidate)
    assert confirmation['passed'] and audit['passed']
    assert candidate.evidence=='smoke' and audit['authored_clone']['evidence']=='engineering_fixture'
    assert audit['before_package_sha256']==candidate.sha256 and audit['candidate_identity_unchanged']
    assert before==(candidate.sha256,st.setting.budget.snapshot())
