"""Round-one audit attribution regressions on authored read panels only."""
from hashlib import sha256
from types import SimpleNamespace

import pytest

from skillopt.execskill import cells, package, profiles as p
from tests.execskill_fakes_env import procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests import test_execskill_v218_read as reads


HEADER = 'Answer only with the result.'
HEADER_SHA256 = sha256(HEADER.encode('utf-8')).hexdigest()


def packages(*, source_has_silent):
    card = package.empty(step='D/s0', evidence=reads.EVIDENCE)
    active = reads.program('fx-v218-fix1-active')
    silent = procedure('fx-v218-fix1-silent', ('applies', 'before_call'), origin='officeqa',
                       header=HEADER, policy_version=p.POLICY_VERSIONS[p.MAIN_V5])
    members = {'F': (silent,), 'S1': (active, silent) if source_has_silent else (active,),
               'S2': (active,) if source_has_silent else (active, silent), 'S3': (silent,)}
    found = {label: package.Package(procs, 'D/' + label.lower(), reads.EVIDENCE, card.sha256)
             for label, procs in members.items()}
    arms = {'C': cells.Arm('card', card), 'F': cells.Arm('candidate', found['F']),
            'B': cells.Arm('blank', card)}
    stages = {'rows': ['C', 'S1', 'S2', 'S3', 'S3', 'F'],
              'packages': {label: found[label] for label in ('S1', 'S2', 'S3')}}
    hooks = {active.id: {'applies': lambda view: True,
                        'before_call': lambda view, state: {'facts': ['Column labels are visible.']}},
             silent.id: {'applies': lambda view: True, 'before_call': lambda view, state: {}}}
    return arms, stages, hooks


@pytest.mark.parametrize('configuration', [p.MAIN_V5, p.MAIN_V6])
@pytest.mark.parametrize('source_has_silent', [False, True])
def test_shared_read_keeps_own_keyword_hits_routes_and_source_scores(
        tmp_path, monkeypatch, configuration, source_has_silent):
    """F shares C; S2 shares S1 despite adding or removing an audited silent procedure."""
    monkeypatch.setattr(reads, 'packages', lambda: packages(source_has_silent=source_has_silent))
    arms, stages, _ = reads.packages()
    own = {**arms, **{label: cells.Arm('candidate', found)
                     for label, found in stages['packages'].items()}}
    _, result, records, solver = reads.authored_read(tmp_path, configuration=configuration)
    assert len(records) == 72
    by_id = {row['cell']['id']: row for row in records}
    for row in records:
        label = row['cell']['arm']
        enabled = {proc.id for proc in own[label].package.procedures}
        has_silent = 'fx-v218-fix1-silent' in enabled
        assert row['package_sha256'] == own[label].package.sha256
        assert set(row['enabled']) == enabled
        assert row['applies'] == {pid: True for pid in enabled}
        assert row['keyword_hits'] == {
            'count': 2 if has_silent else 0,
            'sentences': [{'sentence_sha256': HEADER_SHA256, 'count': 2}] if has_silent else []}
        if configuration == p.MAIN_V5:
            assert (row['shared_with'] is not None) == (label == 'S3')
            assert 'request_reuse' not in row
            continue
        if label not in ('F', 'S2', 'S3'):
            assert row['shared_with'] is None
            continue
        source = by_id[row['shared_with']]
        assert source['cell']['arm'] == ('S1' if label == 'S2' else 'C')
        assert row['request_reuse']['source_arm'] == source['cell']['arm']
        assert row['request_reuse']['identity'] == row['request_reuse']['source_identity']
        assert row['calls'] == [] and source['calls']
        for key in ('final', 'judge', 'returned_models', 'returned_model', 'solver_route'):
            assert row[key] == source[key]
        assert row['keyword_hits'] != source['keyword_hits']
    assert solver.calls == (60 if configuration == p.MAIN_V5 else 36)
    if configuration == p.MAIN_V6:
        assert result['request_reuse']['shared_cells_by_reason'] == {
            'identical_to_C': 24, 'identical_to_stage': 12}


@pytest.mark.parametrize('configuration, planned, count', [
    (p.MAIN_V5, None, 2), (p.MAIN_V6, None, 2),
    (p.MAIN_V6, {'planning_metadata': {'keyword_hits': {'count': 0, 'sentences': []}}}, 0)])
def test_own_audit_metadata_is_gated_to_main_v6_request_reuse(configuration, planned, count):
    source = {'keyword_hits': {'count': 2, 'sentences': [{'sentence_sha256': HEADER_SHA256, 'count': 2}]},
              'returned_models': ['authored-provider-model'], 'returned_model': 'authored-provider-model'}
    value = cells._shared_audited_fields(SimpleNamespace(configuration=configuration), source,
                                        {'per_procedure': {}}, planned)
    assert value['keyword_hits']['count'] == count and value['applies'] == {}
    assert value['returned_models'] == source['returned_models']
    assert value['returned_model'] == source['returned_model']
    value['keyword_hits']['count'] = 99
    assert source['keyword_hits']['count'] == 2
    if planned is not None:
        assert planned['planning_metadata']['keyword_hits']['count'] == 0
