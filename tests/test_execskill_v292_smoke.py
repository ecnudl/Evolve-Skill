"""v2.9.2 S3c retains the crash while fixing only the child ALF return shape."""
import hashlib
from dataclasses import replace

import pytest

from skillopt.execskill import alf_smoke, donors, engineer, profiles as p, v29_smoke, zebra_smoke
from tests.test_execskill_v291_smoke import prepare
from tests.test_execskill_v27_zebra_smoke_review import made as zebra_made
from tests.test_execskill_alf_v1_smoke_review import made as alf_made
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


def source_of(reply):
    entries, sources = engineer.parse(reply)
    return engineer.changes_of(entries, sources, 'authored')[0].source


def test_child_alf_fault_fixture_crashes_at_none_but_returns_a_valid_shape_after_state_repair():
    reply = v29_smoke.authored_fault_reply('alfworld', configuration='alfworld-v6')
    source = source_of(reply)
    assert 'return {"fields": {"facts": [state.get("previous_observation", "")]}}' in source
    scope = {}
    exec(compile(source, '<authored-local-fixture>', 'exec'), scope)
    with pytest.raises(AttributeError):
        scope['alf_before_step']({}, None)
    value = scope['alf_before_step']({}, {'previous_observation': 'Observed cabinet.'})
    assert donors.shaped(value, 'discourage') == ({'facts': ['Observed cabinet.']}, [])


@pytest.mark.parametrize('bench,parent,child', [('zebralogic', 'zebra-pc-v8', 'zebra-pc-v9'),
                                             ('alfworld', 'alfworld-v5', 'alfworld-v6')])
def test_parent_fault_fixture_is_identical_and_zebra_child_content_is_unchanged(bench, parent, child):
    before = v29_smoke.authored_fault_reply(bench)
    frozen = {'zebralogic': '9082e1bfc2f3ebf4b371c594a6edf57893e6bd3e6f3ff5dced8beae8f025fdfd',
              'alfworld': 'e4d3513451c78f453d5ec9b31bcfc4ba0af62d07f024ea7db48d5b0c5c9f45d5'}
    assert hashlib.sha256(before.encode()).hexdigest() == frozen[bench]
    assert v29_smoke.authored_fault_reply(bench, configuration=parent) == before
    new = v29_smoke.authored_fault_reply(bench, configuration=child)
    assert (new == before) is (bench == 'zebralogic')


@pytest.mark.parametrize('configuration,make,module', [
    ('zebra-pc-v9', zebra_made, zebra_smoke), ('alfworld-v6', alf_made, alf_smoke)])
def test_child_s3c_has_independent_identity_one_repair_call_and_cached_result(
        tmp_path, monkeypatch, configuration, make, module):
    setting, services, solver, roles = prepare(tmp_path, monkeypatch, configuration, make, 'fixed')
    authored_workers = services.workers
    def workers(package, **options):
        assert options.pop('cleanup_grace_seconds') == 120
        assert isinstance(options.pop('cleanup_events'), list)
        assert options.pop('ready_timeout_seconds') == 90
        assert isinstance(options.pop('start_events'), list)
        return authored_workers(package, **options)
    services = replace(services, workers=workers)
    identities = []
    original = module._cached_substage
    def capture(st, identity):
        identities.append(identity)
        return original(st, identity)
    monkeypatch.setattr(module, '_cached_substage', capture)
    result = v29_smoke._s3c(setting, services)
    assert result['passed'] and result['faulted_after'] == 0
    assert result['role_measurements']['engineer']['calls'] == 1
    assert identities[-1]['recipe'] == 'v292-fault-repair-v1'
    assert identities[-1]['configuration'] == configuration
    before = len(solver.requests), len(roles.seen)
    assert v29_smoke._s3c(setting, services) == result
    assert (len(solver.requests), len(roles.seen)) == before


@pytest.mark.parametrize('configuration,make,module', [
    ('zebra-pc-v8', zebra_made, zebra_smoke), ('alfworld-v5', alf_made, alf_smoke)])
def test_parent_s3c_keeps_the_prior_recipe_and_proposal_identity(
        tmp_path, monkeypatch, configuration, make, module):
    from skillopt.validator_pilot.api import digest
    setting, services, _, _ = prepare(tmp_path, monkeypatch, configuration, make, 'fixed')
    sentinel = {'authored': 'already cached'}
    seen = []
    def cached(st, identity):
        seen.append(identity)
        return sentinel
    monkeypatch.setattr(module, '_cached_substage', cached)
    assert v29_smoke._s3c(setting, services) is sentinel
    assert seen[0]['recipe'] == 'v291-fault-repair-v1'
    assert seen[0]['proposal_sha256'] == digest(v29_smoke.authored_fault_reply(p.active_benches(configuration)[0]))
