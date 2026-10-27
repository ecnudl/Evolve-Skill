"""Opt-in v2.9.3 envelope retries; earlier engineer prompt pins stay frozen."""
from . import audit, engineer_v29, engineer_v291, engineer_v292, profiles as p


FORMAT_RETRY_SYSTEM = (
    'When `change_index` is null, the whole reply could not be read: return the whole proposal again '
    'as one JSON manifest containing every change (at most %d, with each change\'s replay tests inside '
    'that change), plus one Python block per change in manifest order. Otherwise, return only the change '
    'at `change_index` (identified by `change_id` when given) as one JSON manifest with exactly that one '
    'change plus its Python block. Use the supplied schema and fix the parse problem; '
    'do not change the intended behaviour. ' % p.MAX_CHANGES
    + engineer_v29.SHORT_POLICY
)


def system(configuration, *, train):
    parent = {'zebra-pc-v10': 'zebra-pc-v9', 'alfworld-v7': 'alfworld-v6'}[configuration]
    return engineer_v292.system(parent, train=train).replace('(v2.9.2)', '(v2.9.3)')


def prompt_pins():
    values = {configuration + '/' + mode: system(configuration, train=mode == 'train')
              for configuration in ('zebra-pc-v10', 'alfworld-v7') for mode in ('single', 'train')}
    values.update({configuration + '/note_caps': engineer_v291.note_caps_rule(configuration)
                   for configuration in ('zebra-pc-v10', 'alfworld-v7')})
    values.update(fix=engineer_v29.FIX_SYSTEM, format_retry=FORMAT_RETRY_SYSTEM,
                  audit_fix=engineer_v29.AUDIT_FIX_SYSTEM,
                  fault_repair=engineer_v291.FAULT_REPAIR_INSTRUCTION)
    return {key: {'text': value, 'sha256': audit.text_sha256(value)} for key, value in values.items()}
