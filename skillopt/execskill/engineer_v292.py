"""Opt-in v2.9.2 reader tolerance; parent prompt pins remain frozen."""
from . import audit, engineer_v29, engineer_v291


FORMAT_RETRY_SYSTEM = (
    'Return only the change at `change_index` (identified by `change_id` when given) '
    'in the usual format: one JSON manifest with exactly that one change plus its Python block. '
    'Use the supplied schema and fix the parse problem; do not change the intended behaviour. '
    + engineer_v29.SHORT_POLICY
)


def system(configuration, *, train):
    parent = {'zebra-pc-v9': 'zebra-pc-v8', 'alfworld-v6': 'alfworld-v5'}[configuration]
    return engineer_v291.system(parent, train=train).replace('(v2.9.1)', '(v2.9.2)')


def prompt_pins():
    values = {configuration + '/' + mode: system(configuration, train=mode == 'train')
              for configuration in ('zebra-pc-v9', 'alfworld-v6') for mode in ('single', 'train')}
    values.update({configuration + '/note_caps': engineer_v291.note_caps_rule(configuration)
                   for configuration in ('zebra-pc-v9', 'alfworld-v6')})
    values.update(fix=engineer_v29.FIX_SYSTEM, format_retry=FORMAT_RETRY_SYSTEM,
                  audit_fix=engineer_v29.AUDIT_FIX_SYSTEM,
                  fault_repair=engineer_v291.FAULT_REPAIR_INSTRUCTION)
    return {key: {'text': value, 'sha256': audit.text_sha256(value)} for key, value in values.items()}
