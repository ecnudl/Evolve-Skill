"""Frozen main-v4 four-benchmark prompts; no single-benchmark parent dispatch.

The construction is V211-DESIGN §6, checked against its eight literal hashes.
All public strings and canonical structures are pinned independently. Runtime
request hashes bind concrete evidence and rendered inert-repair causes.
"""
from __future__ import annotations

import hashlib
import json

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest
from . import audit, engineer, engineer_reader, engineer_v29, engineer_v291, engineer_v293, engineer_v294, engineer_v295, instruction_start

BENCHES = ('searchqa', 'officeqa', 'livemath', 'spreadsheetbench')

COMMON = "You maintain sandboxed helper procedures for {bench}, configuration main-v4 (v2.11).\nPropose at most 3 changes. Procedures must compute from public inputs; never memorize item answers.\nFatal checks: sandbox safety and resource/load limits; reference-answer leakage; registered static bans, shortcuts and meta counterfactuals; answer-channel markers; source over 24000 UTF-8 bytes; unusable delivery after one format-only retry. J7 remains binding.\nReplay tests and claims_fix are advisory. Malformed tests are dropped and reported. Replay mismatch, faults, firing and note coverage, tracker agreement and registrar quality findings are information. Faults suppress the affected notes. Wholly inert changes are not trained. Workers use PYTHONHASHSEED=0 and fresh module namespaces.\nTraining adoption requires more fixed than broken items, rational net gain of at least max(1, ceil(0.02 * evaluated items)), the registered format guard, and confirmation. Acceptance uses the sealed practical rule: pooled S'-(S+C)/2 when the parent has no procedure on this bench, otherwise S'-S; at least 5 whole-batch points, or for SearchQA at least 2 points with the registered p <= 0.05 test. J2 is removed; J3 is informational; J4/J5/J6/J7 remain binding.\nReturn one fenced JSON object with a changes list and one fenced Python block per coded change in manifest order. Changes are new, revision with revises, deletion with id, or narrowing with id and benches. Coded metadata includes description, hooks, header, max_note_chars, requests_second_call, state_bytes, excluded_benches and replay_tests. Description/header limits are 600/200 characters. Use the supplied schema. Unknown keys are recorded and ignored; recoverable omissions use the fixed change, incumbent, then schema defaults. A format-only retry preserves intended behaviour and consumes the same unit call budget.\nUse only hooks supported on the current bench. Before-call and feedback notes must be truthful about the input visible at that hook; task-stated requirements may be repeated."

MODE = {'single': 'This is one proposal round; each failing change gets at most one ordinary behaviour fix. Training, when used, has at most 6 rounds and patience 4.', 'train': 'Training has at most 6 rounds and patience 4 candidate rounds without adoption; each failing change gets at most 3 ordinary behaviour fixes.'}

HOOKS = {'searchqa': 'applies(view) -> bool is optional (default true). view={question,context}. before_call(view,state) -> fields or None, state=None. bindings(view) -> {bindings:[{name,quote,value}]} or None supplies numeric text quoted verbatim from the public input for the shell calculator. No solver reply, reference answer or private metadata is visible.', 'officeqa': 'applies(view) -> bool is optional (default true). view={question,context}. before_call(view,state) -> fields or None, state=None. bindings(view) -> {bindings:[{name,quote,value}]} or None supplies numeric text quoted verbatim from the public input for the shell calculator. No solver reply, reference answer or private metadata is visible.', 'livemath': 'applies(view) -> bool is optional (default true). view={question,choices}. before_call(view,state) -> fields or None, state=None. bindings(view) -> {bindings:[{name,quote,value}]} or None supplies numeric text quoted verbatim from the public input for the shell calculator. Choices keep their public order and labels. Never use option position or a benchmark-specific answer prior.', 'spreadsheetbench': 'applies(view) -> bool is optional (default true). view={instruction,workbook_preview,input_path,required_output_path,required_answer_position}. before_call(view,state) -> fields or None, state=None. sheet_feedback(view,run_report,state) -> {fields:fields,request_repair:bool}, state=None. run_report={status,exc_type,message,answer_cells} comes from one execution on the public input workbook; it contains no reference workbook or private grading result. Declare requests_second_call=true to request at most one solver repair. The helper receives no solver program. bindings is unavailable. A permitted repair request is an effect even when fields are empty.'}

CONFIRM = 'Adoption also requires fixed > broken on the reserved confirm slice for this round, used for one decision only. Confirm and acceptance are training-side data, never validation sets. You receive confirm counts only, never its items, answers, outputs or repair examples.'

CAPS = 'Note caps: facts/warnings items <= 200 characters; candidates <= 120 characters; table <= 20 rows by 12 columns, each cell <= 40 characters; binding name/quote/value <= 200 characters each. Each field over its cap is dropped whole and counts as a fault. Rendered notes must fit max_note_chars and 4000 characters per request.'

HOOK_NAMES = {bench: ('applies', 'before_call', 'sheet_feedback') if bench == 'spreadsheetbench'
              else ('applies', 'before_call', 'bindings') for bench in BENCHES}
INERT = {bench: ('The shell calls only top-level functions named exactly ' + ', '.join(HOOK_NAMES[bench])
    + '. Declaring a hook does not create it. A change with no effect hook, '
      'never firing, or no request effect gets at most one inert repair; '
      'retain it only if fatal checks pass and an effect appears. '
      'Crashes and excluded benches are not inert-repair cases.') for bench in BENCHES}
TRUNCATION_RULE = ('Audit views may be truncated. Omitted content is not evidence that a claim is false. '
    'Use unverifiable unless visible public evidence supports or contradicts the claim. '
    'A SpreadsheetBench pre-check report describes public execution, not correctness against a reference.')
TASK_CARDS = {
    'searchqa': 'The solver answers a question using its supplied public context.',
    'officeqa': 'The solver answers a bulletin question using its supplied public context.',
    'livemath': 'The solver answers a mathematics question with the supplied public choices.',
    'spreadsheetbench': 'The solver returns a Python program that operates on the public workbook and writes the requested output workbook and answer cells.',
}
PURPOSES = ('propose', 'fix', 'format_retry', 'audit_fix', 'fault_repair', 'inert_repair')
REPAIRS = {'fix': engineer_v29.FIX_SYSTEM, 'format_retry': engineer_v293.FORMAT_RETRY_SYSTEM,
    'audit_fix': engineer_v29.AUDIT_FIX_SYSTEM, 'fault_repair': engineer_v291.FAULT_REPAIR_INSTRUCTION,
    'inert_repair': engineer_v294.INERT_REPAIR_INSTRUCTION}
SYSTEMS = {bench: {mode: '\n'.join(part.strip('\n') for part in (
    COMMON.format(bench=bench), instruction_start.ENGINEER_SENTENCE, MODE[mode], HOOKS[bench],
    engineer.ENGINEER_FACTS_V23, engineer_v29.SHORT_POLICY, engineer_v29.AUDIT_RULE,
    CONFIRM, engineer_v291.FAULT_RULE, CAPS, INERT[bench], engineer_v295.ABSTAIN_RULE)) + '\n'
    for mode in MODE} for bench in BENCHES}
EXPECTED = {
    'searchqa': ('547b6cbff515517556debde17e8e3ce4e367340189c168be509eed9e31c089dd', 'f197407b4f553586c5f7d63cafda41d2c9055ff641cfdf6cfa772c1f0c8e857d'),
    'officeqa': ('a0f3ff888215f903d7637123dc00a21022f87dc0f8b76f049ae2420434743b6d', '2e6421d7e1c1aa45537c53d7ad1130b5788037dd02754a738b4baa060b948518'),
    'livemath': ('97c463e5eb9cb5dc1adb5a02b9591ebcaedef3b57c475ffd446fa66e123b75f1', '061a9c116ab6bb8edf92ade20882af63d6c8051540e977ea6e3802fc0e48aab4'),
    'spreadsheetbench': ('a2694d46fc981df4814cfdf0c46ddb8f44d7d7eaac0ff6ac4cbb2246f85ca592', '832c41a3e59e74948a29ad7f9aa25a5b56ec50e11612fd568dc57f8957c9d7d1'),
}


def text_sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


for _bench, _hashes in EXPECTED.items():
    for _mode, _sha in zip(MODE, _hashes):
        require(text_sha(SYSTEMS[_bench][_mode]) == _sha, 'Frozen v2.11 engineer prompt drift')


def inert_repair_instruction(bench, causes):
    require(bench in BENCHES, 'A learned main-v4 benchmark')
    return engineer_v294.INERT_REPAIR_INSTRUCTION.format(
        causes=', '.join(sorted(set(causes))), hooks=', '.join(HOOK_NAMES[bench]))


def system(bench, *, train, purpose='propose', causes=()):
    require(bench in BENCHES and purpose in PURPOSES, 'A registered main-v4 benchmark and prompt purpose')
    suffix = inert_repair_instruction(bench, causes) if purpose == 'inert_repair' else REPAIRS.get(purpose, '')
    return SYSTEMS[bench]['train' if train else 'single'] + suffix


def audit_system(part, *, final=False):
    require(part in ('A', 'B'), 'A registered audit part')
    return audit.A_SYSTEM if part == 'A' else (audit.B_SYSTEM + ('\n' + audit.CONTRADICTIONS if final else '')
                                               + '\n' + TRUNCATION_RULE)


def _text(value):
    return {'text': value, 'sha256': text_sha(value)}


def pins():
    """Raw UTF-8 strings and canonical JSON structures, isolated from old maps."""
    from . import profiles as p, describer, examiner, research
    from skillopt.coevo5 import leakage
    from skillopt.continual_eval import backends
    systems = {bench: {mode: {purpose: _text(system(bench, train=mode == 'train', purpose=purpose,
        causes=('<cause>',))) for purpose in PURPOSES} for mode in MODE} for bench in BENCHES}
    materials = {**REPAIRS, 'common': COMMON, 'confirm': CONFIRM, 'caps': CAPS,
        'instruction_sentence': instruction_start.ENGINEER_SENTENCE, 'facts': engineer.ENGINEER_FACTS_V23,
        'short_policy': engineer_v29.SHORT_POLICY, 'audit_rule': engineer_v29.AUDIT_RULE,
        'fault_rule': engineer_v291.FAULT_RULE, 'abstain': engineer_v295.ABSTAIN_RULE,
        'audit_policy': audit.POLICY, 'audit_schema_A': audit.A_SCHEMA, 'audit_schema_B': audit.B_SCHEMA,
        'audit_schema_final': audit.B_FINAL_SCHEMA, 'audit_format_retry': audit.FORMAT_RETRY,
        'audit_fix_prefix': audit.C_PREFIX, 'audit_fix_advisory': audit.C_ADVISORY,
        'audit_fix_suffix': audit.C_SUFFIX, 'audit_contradictions': audit.CONTRADICTIONS,
        'truncation_rule': TRUNCATION_RULE, 'format_retry_example': engineer_reader.schema_document()['example']}
    materials.update({kind + '/' + bench: value for kind, values in (
        ('hook', HOOKS), ('inert', INERT), ('task_card', TASK_CARDS)) for bench, value in values.items()})
    materials.update({'mode/' + mode: text for mode, text in MODE.items()})
    inherited = {'analyst': engineer.ANALYST_SYSTEM, 'describer': describer.DESCRIBER_SYSTEM,
        'leakage': leakage.ADJUDICATE_SYSTEM, 'research/query': research.QUERY_SYSTEM,
        'research/pick': research.PICK_SYSTEM,
        **{'research/conclude/' + key: value for key, value in research.CONCLUDE_SYSTEM.items()},
        'examiner/policy/single': examiner.POLICY_SYSTEM, 'examiner/policy/train': examiner.POLICY_SYSTEM_V2,
        'examiner/detectors': examiner.DETECTOR_SYSTEM, 'examiner/generators/single': examiner.GENERATOR_SYSTEM,
        'examiner/generators/train': examiner.GENERATOR_SYSTEM_V2}
    structures = {'hooks': HOOKS, 'hook_names': HOOK_NAMES, 'task_cards': TASK_CARDS,
        'sampling_truncation': {bench: p.audit_spec(p.MAIN_V4, bench) for bench in BENCHES},
        'truncation_policy': {'text': 'equal_head_tail', 'marker': '…[truncated]',
            'fit': 'repeatedly_halve_public_text_limits', 'retain': ['identifiers', 'choice_labels', 'phase_boundaries', 'note_ids'],
            'overflow': 'incomplete_coverage', 'omission_verdict': 'unverifiable'},
        'workbook_preview': {'max_sheets': 20, 'max_rows': 5, 'max_columns': 20,
            'source': 'recorded runtime preview; no new workbook read',
            'supported_versions': [None, backends.SHEET_PREVIEW_VERSION],
            'effective_version': 'inherited pinned SpreadsheetBench runtime sheet',
            'runtime_version_and_source_pinned_by_manifest': True},
        'format_retry_schema': engineer_reader.schema_document()}
    structures = json.loads(json.dumps(structures, ensure_ascii=False, sort_keys=True))
    result = {'systems': systems, 'materials': {key: _text(value) for key, value in materials.items()},
        'audit': {bench: {'A': _text(audit_system('A')), 'B': _text(audit_system('B')),
                         'final': _text(audit_system('B', final=True))} for bench in BENCHES},
        'maps': {key: {'value': value, 'sha256': digest(value)} for key, value in structures.items()},
        'inherited': {key: {**_text(value), 'canonical_text_sha256': digest(value)}
                      for key, value in inherited.items()},
        'alfworld_audit': audit.prompt_pins(p.ALFWORLD_V11)}
    result['map_sha256'] = {key: digest(value) for key, value in result.items()}
    return result


def dispatch(ctx, user):
    """Resolve the current benchmark before every historical prompt selector."""
    purpose = user.get('request', 'propose')
    purpose = purpose if purpose in PURPOSES else 'propose'
    causes = user.get('causes', user.get('evidence', {})) if purpose == 'inert_repair' else ()
    selected = system(ctx.bench, train=ctx.mode == 'train', purpose=purpose, causes=causes)
    frozen = pins()
    expected = ctx.sheet.get('v211_prompt_pins', frozen)
    require(expected == frozen, 'The main-v4 dispatch pins must match the sealed manifest')
    mode = 'train' if ctx.mode == 'train' else 'single'
    template = expected['systems'][ctx.bench][mode][purpose]
    require(template == _text(system(ctx.bench, train=ctx.mode == 'train', purpose=purpose,
                                     causes=('<cause>',))), 'The main-v4 benchmark/mode/purpose prompt pin')
    if purpose != 'inert_repair':
        require(text_sha(selected) == template['sha256'], 'The dispatched main-v4 prompt hash')
    return selected


def request_pin(ctx, user, system_text, purpose):
    """Pin the exact rendered user request separately from its static template."""
    request = json.dumps(user, ensure_ascii=False, sort_keys=True)
    row = {'bench': ctx.bench, 'mode': ctx.mode, 'purpose': purpose,
           'system_sha256': text_sha(system_text), 'user_sha256': text_sha(request),
           'request_sha256': digest({'system': system_text, 'user': request})}
    ctx.sheet.setdefault('v211_requests', []).append(row)
    return request
