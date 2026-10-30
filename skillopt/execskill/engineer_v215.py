"""The v2.15 engineer-only diagnostics addition; all inherited prompt text is frozen."""
from copy import copy
from types import SimpleNamespace

from skillopt.continual_eval.core import require

from . import audit, engineer_v295, profiles as p

DIAGNOSTICS_SECTION = (
    '\nEngineer-only diagnostics (zebra-pc-v14):\n'
    'A note-writing hook may return an optional top-level `diagnostics` list of at most 5 strings. '
    'Each string is truncated to 240 characters and truncation is recorded; malformed diagnostics '
    'are ignored as informational shape faults. Only the engineer sees this channel: the shell '
    'removes it before rendering, it does not count toward note caps, and it never reaches the solver '
    'or delivered-note audits. Compute diagnostics only from the public input view. Say why the '
    'program returned no note or quote the input text it could not interpret. '
    'Feedback may store diagnostics once in a shared `texts` list; an item\'s `text_indices` '
    'and an aggregate\'s `text_index` refer to entries in that list.\n'
    'Before presenting a complete answer or decisive conclusion, check that every condition stated '
    'in the item was understood and that the conclusion is the only one consistent with all of them. '
    'If either check cannot be verified, return no note and report the reason in `diagnostics`.\n'
)
PURPOSES = ('propose', 'fix', 'format_retry', 'audit_fix', 'fault_repair', 'inert_repair')


def system(configuration, *, train):
    require(p.is_v215(configuration), 'The v2.15 engineer prompt belongs to zebra-pc-v14')
    return engineer_v295.system(p.ZEBRA_PC_V13, train=train) + DIAGNOSTICS_SECTION


def dispatch(ctx, user):
    """Preserve the exact inherited mode and repair suffix, then add the new section."""
    require(p.is_v215(ctx.configuration), 'The v2.15 engineer prompt belongs to zebra-pc-v14')
    from . import engineer
    parent = copy(ctx)
    parent.configuration = p.ZEBRA_PC_V13
    inherited_user = user
    evidence = user.get('evidence')
    if isinstance(evidence, dict) and 'engineer_diagnostics' in evidence:
        inherited_user = {**user, 'evidence': {key: value for key, value in evidence.items()
                                             if key != 'engineer_diagnostics'}}
    return engineer._legacy_system(parent, inherited_user) + DIAGNOSTICS_SECTION


def prompt_pins():
    values = {'diagnostics': DIAGNOSTICS_SECTION}
    for mode in ('single', 'train'):
        ctx = SimpleNamespace(configuration=p.ZEBRA_PC_V14, bench=p.ZEBRA, mode=mode)
        for purpose in PURPOSES:
            values[mode + '/' + purpose] = dispatch(ctx, {'request': purpose, 'evidence': {}})
    return {key: {'text': value, 'sha256': audit.text_sha256(value)} for key, value in values.items()}
