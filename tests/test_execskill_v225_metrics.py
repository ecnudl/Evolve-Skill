"""Field-for-field CL equality against the independent, SHA-pinned reference."""
import hashlib
from copy import deepcopy
import json

from skillopt.execskill import v225_metrics as m
from tests.test_execskill_v225_read import synthetic_aggregate
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401


def normalized(value):
    return json.loads(json.dumps(value))


def test_anchor_c_equals_vendored_reference_field_for_field(fast_statistics):
    agg=synthetic_aggregate()
    result=m.compute(agg,'G')
    ref=m.reference()
    c=ref.chains_from_readout(agg,'main-v9','authored')['G']
    for an in ('P','S'):
        assert normalized(result['anchor_C'][an])==normalized(ref.cl_metrics(c,an,result['similar']))


def test_c0_and_b_are_actual_reanchored_reference_matrices(fast_statistics):
    agg=synthetic_aggregate()
    result=m.compute(agg,'G')
    ref=m.reference()
    for anchor in ('C0','B'):
        changed=deepcopy(agg)
        for pb in changed['chains']['G']['per_bench'].values():
            pb['acc']['C']=pb['acc'][anchor]
            old=deepcopy(pb['pairs'])
            for arm in ('S1','S2','S3','S4','S5','F'):
                pb['pairs'][arm+'-C']=old[arm+'-'+anchor]
        c=ref.chains_from_readout(changed,'main-v9','authored')['G']
        for an in ('P','S'):
            assert normalized(result['anchor_'+anchor][an])==normalized(ref.cl_metrics(c,an,result['similar']))


def test_changed_only_and_same_text_never_label_unchanged_rows_transfer(fast_statistics):
    result=m.compute(synthetic_aggregate(),'G')
    for an in ('P','S'):
        assert result['changed_only'][an]['steps']==[2,4]
        assert result['changed_only'][an]['off_inf']==8
        assert result['changed_only'][an]['TS_n']+result['changed_only'][an]['TD_n']==8
    assert [row['step'] for row in result['same_text']]==[1,3,5]
    assert all(row['reading']=='same_text_noise_not_transfer_or_forgetting' for row in result['same_text'])
    assert 'C_end-C is descriptive' in result['drift_reading']
    assert set(result['drift_control'])=={'searchqa','officeqa','zebralogic','spreadsheetbench','alfworld'}


def test_reference_sha_and_secondary_copy_are_pinned():
    assert hashlib.sha256(m.REFERENCE_PATH.read_bytes()).hexdigest()==m.REFERENCE_SHA256
    other=m.REFERENCE_PATH.parent/'v225_metrics/cl_metrics.py'
    assert other.read_bytes()==m.REFERENCE_PATH.read_bytes()
