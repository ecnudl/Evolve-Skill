"""Pre-v2.8 identities and v2.7b behavior, captured before v2.8 implementation.

Existing historical/v1/v2/v3/v4/ALF-v1 byte fixtures remain authoritative.
This extends them to every configuration's identity plus v5/ALF-v2 actual
proposal/fix requests and records. All content is authored engineering data.
"""
from copy import deepcopy
from dataclasses import replace

import pytest

from tests.test_execskill_zpc_regression import FEATURES, byte_sha
from tests.test_execskill_zpc_pipeline import offline

OLD_CONFIGURATIONS = ('default', 'recommended', 'main', 'main-v2', 'main-v2-1', 'main-v2-2', 'main-v2-3',
                      'zebra-pc-v1', 'zebra-pc-v2', 'zebra-pc-v3', 'zebra-pc-v4', 'alfworld-v1',
                      'zebra-pc-v5', 'alfworld-v2')


def snapshot():
    from skillopt.execskill import budgets, engineer, manifest, policy, profiles as p
    from tests.execskill_fakes import engineer_reply
    from tests.test_execskill_v23_engineer import context
    from tests.test_execskill_v27_fix_replies import authored, encoded, run_fix
    result = {}
    for name in OLD_CONFIGURATIONS:
        registration = manifest._plain({
            'features': {key: getattr(p, key).get(name, {'unregistered': True}) for key in FEATURES},
            'family': p.FEATURE_FAMILIES[name], 'namespaces': p.CHAIN_NAMESPACES.get(name),
            'registered': manifest.registered(name), 'prompts': manifest.prompt_sha(name),
            'roles': manifest.role_settings(name),
            'budgets': {chain: budgets.chain_caps(chain, name) for chain in p.CHAINS},
            'policy': policy.POLICIES[p.POLICY_VERSIONS[name]],
        })
        result[name] = {'registration': registration}
        if name not in ('zebra-pc-v5', 'alfworld-v2'):
            continue
        records = {}
        for mode in ('train', 'single'):
            for shape in ('corrected', 'missing_kind', 'extra_key', 'malformed_claim'):
                ctx, _, incorrect, correct = authored(name, mode=mode)
                fixed = deepcopy(correct.entry)
                if shape == 'missing_kind':
                    fixed.pop('kind')
                if shape == 'extra_key':
                    fixed['claims_fix_note'] = 'Authored unknown metadata.'
                if shape == 'malformed_claim':
                    incorrect.entry['replay_tests'][0]['property']['value'] = ['Mara'] * 10
                package, record = run_fix(ctx, incorrect, encoded(correct, entry=fixed))
                records[mode + '_' + shape] = {
                    'package': package.to_json() if package is not None else None,
                    'record': record, 'requests': ctx.roles.seen, 'wire': ctx.roles.wire}
        result[name]['records_and_requests'] = records
    return result


# Captured in this working copy before any v2.8 edits; never regenerated to fit changes.
BASELINE_SHA256 = {'default': 'a8b4499ec66209b2aff7351c695f8521ef55090a872027cb7910d800431d1a1f',
 'recommended': 'ee6e1dd197480e854d46be765aa1d42bc441de9713c6eddd9472f18e7a79bfd4',
 'main': '8d5c863ad7b53a58a3ed97f0c07a1b43363e033c70247b51dba0ff43fdb0bd9e',
 'main-v2': 'a61742b9d0f96d4103594b2355c0c92ae6612ecd607da959d3481eca33ef7f4d',
 'main-v2-1': 'd0a77b92bf7ec8a5689965c00a7995a54b7c683d9959a6706debcb996a0842f0',
 'main-v2-2': '1c0a64e14a357577ee25610d823ba7486e5d2960fd5262e70cfc24a480358d96',
 'main-v2-3': '611d66a98b58911bd65ec2e254073aa675b5a2cf1bf2f24f8202934eccb5b85b',
 'zebra-pc-v1': '0117a0460d7fff5f481afb936823c06bbef7db02379f8b8f439f539f29bd83c3',
 'zebra-pc-v2': 'f9d4629d6cf8e95874012135e89f82b4cad89b1fd913d714bd71f724276997f7',
 'zebra-pc-v3': 'f00b99f588e94e34ea4d188e175a4eb88ab8e3c3936d258ba538a519dd13ca99',
 'zebra-pc-v4': '27d2b1d7d13bfcd40306fb7f2abe5e1665cc3e9de3eec8fd875790ce33e0b98f',
 'alfworld-v1': '85bcf7731cd42cb93a7c765366198f9e0d05b817294525b3f2953f7c8ad9f9bd',
 'zebra-pc-v5': 'ce7d1c3cf09b43472b10fb36367de79a08466a32a908d3d1e2394bca529cd8d0',
 'alfworld-v2': '5ce8e7006da22f9b3c1cea000f68cb0b6d476e25cf59bef91f04782d61af8781'}


@pytest.fixture(scope='module')
def frozen_values():
    return {name: byte_sha(value) for name, value in snapshot().items()}


@pytest.mark.parametrize('configuration', OLD_CONFIGURATIONS)
def test_every_pre_v28_configuration_keeps_its_identity_and_v27_records(configuration, frozen_values):
    assert frozen_values[configuration] == BASELINE_SHA256[configuration]
