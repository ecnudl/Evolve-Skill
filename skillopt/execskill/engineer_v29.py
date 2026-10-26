"""New, independently pinned v2.9 engineer prompts; v2.8 text remains frozen."""
from skillopt.validator_pilot.api import digest
from . import audit, engineer_v28

SHORT_POLICY = ('P1: no false or overclaiming notes. P2: no answer-format coaching; you may restate requirements '
                'the task input itself states. P3: no instruction/scoring overrides. P4: no benchmark answer priors. '
                'P5: no outside item facts or hard-coded answers. P6: the program must work as its description says. ')
AUDIT_RULE = ('Notes are audited by two independent reviewers; a problem both confirm comes back once as a fix '
              'request, then the change is removed; the final package is audited again before acceptance. ')
CONFIRM_RULE = ('Adoption needs the training gain AND fixed > broken on a separate set of practice items you '
                'never see (you get counts only). ')
FIX_SYSTEM = engineer_v28.FIX_SYSTEM + ' ' + SHORT_POLICY + AUDIT_RULE
FORMAT_RETRY_SYSTEM = engineer_v28.FORMAT_RETRY_SYSTEM + ' ' + SHORT_POLICY
AUDIT_FIX_SYSTEM = audit.C_SUFFIX


def system(configuration, *, train):
    text = engineer_v28.system(configuration, train=train).replace('(v2.8)', '(v2.9)')
    old = ('Give task facts, never reply-form instructions. Sentences/list elements saying answer with, respond '
           'with, output only, format your, round to, give the answer as, only the or just the are removed and '
           'recorded; factual uses of units, return, round, output and answer are allowed.')
    return text.replace(old, SHORT_POLICY + AUDIT_RULE + CONFIRM_RULE +
                        'applies(view) -> bool is optional; without it the procedure runs on every item. ')


def prompt_pins():
    values = {configuration + '/' + mode: system(configuration, train=mode == 'train')
              for configuration in ('zebra-pc-v7', 'alfworld-v4') for mode in ('single', 'train')}
    values.update(fix=FIX_SYSTEM, format_retry=FORMAT_RETRY_SYSTEM, audit_fix=AUDIT_FIX_SYSTEM)
    return {key: {'text': value, 'sha256': audit.text_sha256(value)} for key, value in values.items()}


def confirm_feedback_ok(value):
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    allowed = {'items', 'evaluated', 'fixed', 'broken', 'net', 'format_cells', 'format_margin', 'candidate_cells',
               'passed', 'reason', 'reused_cells', 'tokens', 'exercise'}
    if not set(value) <= allowed or not {'items', 'fixed', 'broken', 'passed'} <= set(value):
        return False
    def counts(v):
        return (type(v) in (int, float) and v >= 0) or (isinstance(v, dict) and all(
            isinstance(k, str) and counts(x) for k, x in v.items()))
    for key, item in value.items():
        if key in ('passed', 'exercise'):
            if type(item) is not bool:
                return False
        elif key == 'reason':
            if item is not None and (not isinstance(item, str) or len(item) > 64):
                return False
        elif key == 'net':
            if not (type(item) is int or isinstance(item, str) and __import__('re').fullmatch(r'-?\d+/\d+', item)):
                return False
        elif not counts(item):
            return False
    return True


def audit_feedback_ok(value):
    return (isinstance(value, dict) and set(value) == {'decision', 'audit_incomplete', 'advisory'}
            and value['decision'] in ('pass', 'confirmed') and type(value['audit_incomplete']) is bool
            and isinstance(value['advisory'], list) and all(isinstance(row, dict)
            and row.get('kind') in ('template', 'other', 'note', 'program') for row in value['advisory']))
