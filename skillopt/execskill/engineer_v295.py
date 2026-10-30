"""Opt-in v2.9.5 search budget and abstention prompts; parent pins stay frozen."""
from . import audit, engineer_v29, engineer_v291, engineer_v293, engineer_v294, profiles as p

ABSTAIN_RULE = (
    'When a program cannot verify its result on an item, it should return no note for that item: '
    'unverified warnings or partial results tend to turn correct answers wrong, and training counts '
    'every answer they break.'
)


def system(configuration, *, train):
    if p.is_v213(configuration):
        return system(p.ZEBRA_PC_V13, train=train)
    if p.is_v296(configuration):
        return system(p.ALFWORLD_V9, train=train)
    parent = {'zebra-pc-v12': 'zebra-pc-v11', 'zebra-pc-v13': 'zebra-pc-v11', 'alfworld-v9': 'alfworld-v8'}[configuration]
    text = engineer_v294.system(parent, train=train).replace('(v2.9.4)', '(v2.9.5)')
    # The parent's frozen wording remains exact except for L1's changed limits.
    if (p.train_rounds(configuration), p.train_patience(configuration)) != (
            p.train_rounds(parent), p.train_patience(parent)):
        template = ('Up to %d training rounds, patience %d;' if train else
                    'Training, when used, has patience %d over at most %d rounds.')
        before = ((p.train_rounds(parent), p.train_patience(parent)) if train else
                  (p.train_patience(parent), p.train_rounds(parent)))
        after = ((p.train_rounds(configuration), p.train_patience(configuration)) if train else
                 (p.train_patience(configuration), p.train_rounds(configuration)))
        assert text.count(template % before) == 1
        text = text.replace(template % before, template % after)
    return text + ABSTAIN_RULE + '\n'


def prompt_pins():
    configurations = ('zebra-pc-v12', 'alfworld-v9')
    values = {configuration + '/' + mode: system(configuration, train=mode == 'train')
              for configuration in configurations for mode in ('single', 'train')}
    for configuration in configurations:
        values[configuration + '/note_caps'] = engineer_v291.note_caps_rule(configuration)
        values[configuration + '/hook_rule'] = engineer_v294.hook_rule(configuration)
        values[configuration + '/inert_repair'] = engineer_v294.inert_repair_instruction(configuration, ['<cause>'])
    values.update(fix=engineer_v29.FIX_SYSTEM, format_retry=engineer_v293.FORMAT_RETRY_SYSTEM,
                  audit_fix=engineer_v29.AUDIT_FIX_SYSTEM,
                  fault_repair=engineer_v291.FAULT_REPAIR_INSTRUCTION,
                  inert_repair=engineer_v294.INERT_REPAIR_INSTRUCTION, abstain=ABSTAIN_RULE)
    return {key: {'text': value, 'sha256': audit.text_sha256(value)} for key, value in values.items()}
