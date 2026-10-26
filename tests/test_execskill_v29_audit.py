"""Offline engineering fixtures for v2.9 audited note policy, extraction and agreement."""
import copy
import json
import re
from types import SimpleNamespace

import pytest

from skillopt.execskill import audit


def procedure(pid='p-zebralogic-1-1', source=None):
    return SimpleNamespace(id=pid, description='Extract the task facts.', source=source or
        'def before_call(view, state):\n    return {"facts": ["The public clue is visible."]}\n')


def situation(item='run-1', step=None, text='The public clue is visible.', pid='p-zebralogic-1-1', source='run'):
    return {'item': item, 'cell': item + '-cell', 'step': step,
            'view': {'question': 'The public clue is visible.', 'columns': ['Name']},
            'notes': [{'procedure': pid, 'text': text}], 'source': source}


class Judge:
    def __init__(self, *, template=None, truth='true', policy='ok', program=None, invalid=0, contradiction=False):
        self.calls, self.seen = [], []
        self.template, self.truth, self.policy = template, truth, policy
        self.program, self.invalid, self.contradiction = program, invalid, contradiction

    def plain(self, role, system, user, *, label, max_tokens):
        self.seen.append((system, user, max_tokens))
        self.calls.append({'label': label, 'sends': [{'charged': 13, 'receipt': {'usage': {'prompt_tokens': 10, 'completion_tokens': 3}}}]})
        if self.invalid:
            self.invalid -= 1
            return 'unusable'
        if system == audit.A_SYSTEM:
            rows = [{'t': t, 'verdict': self.template or 'ok', 'reason': 'Authored evidence.', 'false_when': 'When a clue is absent.'}
                    for t in re.findall(r'^(T\d+):', user, flags=re.M)]
            return json.dumps({'templates': rows, 'other': []})
        situations = []
        for part in re.split(r'^Situation ', user, flags=re.M)[1:]:
            sid = part.split()[0]
            ids = re.findall(r'^(N\d+) \[', part, flags=re.M)
            situations.append({'s': sid, 'notes': [{'n': n, 'truth': self.truth, 'policy': self.policy,
                'evidence': 'The public clue is visible.' if self.truth == 'false' else '',
                'reason': 'Authored note check.'} for n in ids]})
        verdict = self.program(len(self.calls)) if callable(self.program) else self.program or 'ok'
        result = {'situations': situations, 'program': {'verdict': verdict, 'reason': 'Authored program check.'}}
        if audit.CONTRADICTIONS in system:
            pairs = ['%s/%s' % (s['s'], n['n']) for s in situations for n in s['notes']]
            result['contradictions'] = [{'notes': pairs[:2], 'reason': 'Two incompatible facts.'}] if self.contradiction and len(pairs) > 1 else []
        return json.dumps(result)


def run(g=None, d=None, *, rows=None, procedures=None, final=False, cache=None):
    return audit.run_audit(procedures or [procedure()], rows or [situation()], {'G': g or Judge(), 'D': d or Judge()},
        bench='zebralogic', configuration='zebra-pc-v7', step='D/s1-zebralogic/engineer-r1', round=1,
        change_id='1', final=final, cache=cache)


@pytest.mark.parametrize('left,right,confirmed,advisory', [('P1','P2',1,0), ('P2',None,0,1), (None,None,0,0)])
def test_template_agreement_is_same_template_any_policy(left, right, confirmed, advisory):
    result = run(Judge(template=left), Judge(template=right))
    assert len(result['confirmed']) == confirmed
    assert len(result['advisory']) == advisory


@pytest.mark.parametrize('truth,policy,confirmed', [('false','ok',True), ('unverifiable','ok',False), ('true','P2',True)])
def test_truth_and_policy_note_agreement(truth, policy, confirmed):
    result = run(Judge(truth=truth, policy=policy), Judge(truth=truth, policy=policy))
    assert bool(result['confirmed']) is confirmed


def test_note_agreement_allows_different_fault_kind_same_note():
    result = run(Judge(truth='false'), Judge(policy='P3'))
    assert len(result['confirmed']) == 1 and result['confirmed'][0]['kind'] == 'note'


def test_other_requires_same_function_and_policy():
    def other(code):
        return audit.findings({'templates': [], 'other': [{'where': 'before_call', 'verdict': code, 'reason': 'R'}]},
                              part='A', procedure='p')
    confirmed, advisory = audit.agreement({'G': other('P1'), 'D': other('P2')}, {'G': True, 'D': True})
    assert not confirmed and len(advisory) == 2
    confirmed, _ = audit.agreement({'G': other('P1'), 'D': other('P1')}, {'G': True, 'D': True})
    assert len(confirmed) == 1


def test_p6_any_batch_per_judge_confirms_even_if_different_batches():
    rows = [situation('run-%d' % i) for i in range(12)]
    result = run(Judge(program=lambda n: 'P6' if n == 2 else 'ok'),
                 Judge(program=lambda n: 'P6' if n == 4 else 'ok'), rows=rows)
    assert [f['kind'] for f in result['confirmed']] == ['program']


@pytest.mark.parametrize('invalid,available,calls', [(1,True,3), (2,False,3)])
def test_one_format_retry_then_unavailable_and_incomplete(invalid, available, calls):
    g = Judge(template='P2', invalid=invalid)
    result = run(g, Judge(template='P2'))
    assert result['available']['G'] is available
    assert result['audit_incomplete'] is not available
    assert len(g.calls) == calls
    assert bool(result['confirmed']) is available
    assert len(result['requests'][0]['requests']['G']['retries']) == 1
    assert result['tokens']['G'] == {'input': calls*10, 'output': calls*3, 'charged': calls*13}


def test_exact_request_cache_reuses_raw_parsed_and_costs():
    cache, g, d = {}, Judge(), Judge()
    first = run(g, d, cache=cache)
    second = run(g, d, cache=cache)
    assert len(g.calls) == len(d.calls) == 2
    assert all(pair['requests']['G']['reused'] for pair in second['requests'])
    assert second['tokens']['G']['charged'] == 0
    for pair in first['requests']:
        for row in pair['requests'].values():
            assert row['max_tokens'] == 8192
            assert audit.text_sha256(row['prompt_text']) == row['prompt_sha256']


def test_templates_ast_strings_fstrings_percent_format_order_dedup_and_marking():
    source = '''def before_call(view,state):
    a = "A plain literal sentence."
    b = f"Computed value {view['question']} is visible."
    c = "Percent %s facts" % a
    d = "Format {} facts".format(a)
    e = "A plain literal sentence."
    f = "Please answer with the requested JSON."
'''
    result = audit.templates(source, 'zebralogic')
    assert [row['text'] for row in result['templates']] == ['A plain literal sentence.',
        'Computed value {...} is visible.', 'question', 'Percent %s facts', 'Format {} facts', 'Please answer with the requested JSON.']
    assert result['templates'][-1]['always_check_P2'] and result['truncated'] == 0


def test_template_cap_preserves_late_always_check_before_filling_ordinary():
    source = '\n'.join('S%d = "Ordinary literal sentence %d"' % (i,i) for i in range(70))
    source += '\nSPECIAL = "Answer in JSON only."\n'
    result = audit.templates(source, 'zebralogic')
    assert len(result['templates']) == 60 and result['truncated'] == 11
    assert result['templates'][-1]['always_check_P2']


def test_sampling_determinism_limits_extra_and_excludes_prior_situations():
    rows = [situation('run-%03d' % i, text='Answer with JSON.' if i%2 else 'A public fact.') for i in range(100)]
    kwargs = dict(bench='zebralogic', configuration='zebra-pc-v7', step='D/s1', round=1, change_id='1', source_sha256='a'*64)
    a = audit.sample_situations(rows, **kwargs)
    b = audit.sample_situations(list(reversed(rows)), **kwargs)
    assert a == b and len(a['situations']) == 16 and a['extra'] == 4
    keys = [audit.situation_key(s) for s in a['situations']]
    c = audit.sample_situations(rows, exclude=keys, **kwargs)
    assert not set(keys) & {audit.situation_key(s) for s in c['situations']}


def test_alf_sampling_eight_episodes_step_zero_and_two_later():
    rows = [situation('game-%02d' % i, step=j) for i in range(20) for j in range(10)]
    result = audit.sample_situations(rows, bench='alfworld', configuration='alfworld-v4', step='D/s1', round=1,
                                    change_id='1', source_sha256='b'*64)
    by_item = {}
    for row in result['situations']:
        by_item.setdefault(row['item'], []).append(row['step'])
    assert len(by_item) == 8 and all(len(v)==3 and 0 in v for v in by_item.values())


def test_final_prefers_confirm_and_confirmed_contradiction_drops_later_procedure():
    first, second = procedure(), procedure('p-zebralogic-1-2')
    rows = [situation('train-%d'%i, source='train') for i in range(30)]
    for i in range(12):
        row = situation('confirm-%d'%i, source='confirm')
        row['notes'].append({'procedure': second.id, 'text': 'The public clue is absent.'})
        rows.append(row)
    result = run(Judge(contradiction=True), Judge(contradiction=True), rows=rows, procedures=[first,second], final=True)
    assert all(s['source']=='confirm' for s in result['sampling']['situations'])
    assert audit.removed_procedures(result, [first.id,second.id]) == [second.id]


def test_public_view_whitelist_does_not_copy_labels_answers_or_hidden_history():
    view = {'question':'Public', 'columns':['Name'], 'gold':'SECRET_REFERENCE_SENTINEL',
            'task_text':'Public task', 'initial_observation':'Public reset', 'observation':'Public now',
            'recent_history':[{'observation':'Seen','action':'look','score':'HIDDEN_SCORE_SENTINEL'}]*9,
            'admissible_commands':['look']*80, 'reply':'HIDDEN_REPLY_SENTINEL'}
    zebra, alf = audit.public_view('zebralogic',view), audit.public_view('alfworld',view)
    assert set(zebra)=={'question','columns'} and len(alf['recent_history'])==5 and len(alf['admissible_commands'])==60
    assert 'SENTINEL' not in json.dumps([zebra,alf])


def test_unknown_template_is_ignored_and_never_confirms_hallucinated_unit():
    parsed = audit.parse_verdict(json.dumps({'templates':[{'t':'T999','verdict':'P2','reason':'x'}], 'other':[]}),
                                'A', extracted=audit.templates(procedure().source,'zebralogic'), procedures=[procedure()])
    assert parsed['templates'] == []
    assert parsed['_validation']['ignored'][0]['path'] == 'templates[0].t'
    assert parsed['_validation']['ignored'][0]['raw']['t'] == 'T999'
    assert {row['unit'] for row in parsed['_validation']['abstained']} == set(parsed['_validation']['required'])
    assert not audit.findings(parsed, part='A', procedure=procedure().id)


def test_final_delivered_notes_include_discouragement_and_verify_source_hash():
    from skillopt.execskill.protocol import NOTES_KEY
    proc = procedure()
    view = {'initial_observation':'Public reset','observation':'Public now',
            'recent_history':[],'admissible_commands':['look','open cabinet']}
    text='Known public fact.\nNot recommended: open cabinet'
    cell={'arm':"S'",'bench':'alfworld','unit':'D/s1-alfworld/confirm-r1','task_id':'game-one',
          'cell':'cell-one','calls':[{'purpose':'step','user':json.dumps({**view,NOTES_KEY:text})}],
          'shell':{'notes':[{'id':proc.id,'hook':'alf_before_step','step':0,'delivered_text':text,
                            'source_sha256':audit.text_sha256(proc.source)}]},
          'replies':['PRIVATE_REPLY'],'judge':{'gold':'PRIVATE_GOLD'},'token':'pass'}
    result=audit.situations_from_cells([cell],SimpleNamespace(procedures=[proc]))
    assert [n['text'] for n in result[0]['notes']]==['Known public fact.','Not recommended: open cabinet']
    assert 'PRIVATE' not in json.dumps(result)
    cell['shell']['notes'][0]['source_sha256']='0'*64
    assert audit.situations_from_cells([cell],SimpleNamespace(procedures=[proc]))==[]


def test_final_shows_context_procedure_descriptions_but_only_audits_changed_sources():
    changed, unchanged = procedure(), procedure('p-zebralogic-0-1')
    unchanged.description='Unchanged procedure description for cross-note contradictions.'
    row=situation()
    row['notes'].append({'procedure':unchanged.id,'text':'Another public statement.'})
    g,d=Judge(),Judge()
    result=audit.run_audit([changed],[row],{'G':g,'D':d},bench='zebralogic',configuration='zebra-pc-v7',
        step='D/s1-zebralogic/audit-final',final=True,context_procedures=[unchanged,changed])
    assert len([r for r in result['requests'] if r['part']=='A'])==1
    assert unchanged.description in next(r['requests']['G']['user'] for r in result['requests'] if r['part']=='B')


@pytest.mark.parametrize('template', ['All {...} clues were parsed.', 'All %d clues were parsed.', 'All {} clues were parsed.'])
def test_audit_fix_template_evidence_matches_actual_rendered_fragments(template):
    matching=situation('run-matching',text='All 7 clues were parsed.')
    unrelated=situation('run-unrelated',text='The public clue is visible.')
    result={'sampling':{'situations':[unrelated,matching]}}
    examples=audit.template_examples(template,result,'p-zebralogic-1-1')
    assert len(examples)==1 and examples[0]['item']=='run-matching'
    assert examples[0]['notes'][0]['text']=='All 7 clues were parsed.'


def test_audit_fix_template_without_matching_output_explicitly_says_unavailable():
    proc=procedure(source='def before_call(view,state):\n    return {"facts":["All clues were parsed."]}\n')
    result=run(Judge(template='P2'),Judge(template='P2'),procedures=[proc],rows=[situation('run-unrelated')])
    text=audit.audit_fix_prompt(SimpleNamespace(procedure=proc),result)
    assert 'No matching run-slice output in the sampled situations' in text
    assert '"run_slice_examples": []' in text
    assert '"item": "run-unrelated"' not in text


def test_audit_request_labels_distinguish_real_resends_across_units_and_preserve_cache_origin():
    first=run(Judge(),Judge())
    pair=first['requests'][0]['requests']['G']
    assert pair['label'].endswith('/G') and 'engineer-r1' in pair['label']
    cache={}
    one=run(Judge(),Judge(),cache=cache)
    reused=run(Judge(),Judge(),cache=cache)
    assert reused['requests'][0]['requests']['G']['label']==one['requests'][0]['requests']['G']['label']
    second=audit.run_audit([procedure()],[situation()],{'G':Judge(),'D':Judge()},bench='zebralogic',
        configuration='zebra-pc-v7',step='D/s1-zebralogic/engineer-r2')
    assert second['requests'][0]['requests']['G']['label']!=pair['label']
    retry=run(Judge(invalid=1),Judge())['requests'][0]['requests']['G']
    assert retry['retries'][0]['label']==retry['label']+'/format-retry'


def test_audit1_keeps_two_later_steps_when_reset_has_no_note():
    rows = []
    for index in range(1, 7):
        row = situation('episode', step=index)
        rows.append(row)
    args = dict(bench='alfworld', configuration='alfworld-v4', step='s1', round=1,
                change_id='1', source_sha256='a'*64)
    first = audit.sample_situations(rows, **args)
    final = audit.sample_situations(rows, final=True, **args)
    assert len(first['situations']) == 2
    assert len(final['situations']) == 3


def test_final_two_rounds_keep_new_procedure_in_every_available_final_situation():
    """Round one's earlier cell IDs must not win deduplication over round two."""
    from skillopt.execskill.protocol import NOTES_KEY
    first, added = procedure(), procedure('p-zebralogic-1-2',
        'def before_call(view,state):\n    return {"facts":["The newly added procedure is visible."]}\n')
    final_sources = {p.id: audit.text_sha256(p.source) for p in (first, added)}
    cells = []
    for item in range(12):
        for round_n, procs in ((1, [first]), (2, [first, added])):
            texts = {p.id: 'Public fact from ' + p.id + '.' for p in procs}
            view = {'task_text': 'Public task', 'initial_observation': 'Public reset',
                    'observation': 'Public reset', 'recent_history': [], 'admissible_commands': ['look']}
            cells.append({'arm': "S'", 'bench': 'alfworld', 'unit': 'D/s1-alfworld/confirm-r%d' % round_n,
                'cell': 'round-%d-cell-%02d' % (round_n, item), 'task_id': 'game-%02d' % item,
                'package_sha256': 'final' if round_n == 2 else 'partial',
                'package_procedures': {p.id: final_sources[p.id] for p in procs},
                'calls': [{'purpose': 'step', 'user': json.dumps({**view, NOTES_KEY: '\n'.join(texts.values())})}],
                'shell': {'notes': [{'id': p.id, 'hook': 'alf_before_step', 'step': 0,
                    'delivered_text': texts[p.id], 'source_sha256': final_sources[p.id]} for p in procs]}})
    situations = audit.situations_from_cells(cells, SimpleNamespace(procedures=[first, added]))
    assert {s['package_sha256'] for s in situations} == {'partial', 'final'}
    result = audit.run_audit([first, added], situations, {'G': Judge(), 'D': Judge()},
        bench='alfworld', configuration='alfworld-v4', step='D/s1-alfworld/audit-final',
        final=True, final_package_sha256='final')
    sampled = result['sampling']['situations']
    assert len(sampled) == 8
    assert all(s['package_sha256'] == 'final' for s in sampled)
    assert all(added.id in {n['procedure'] for n in s['notes']} for s in sampled)


def test_final_package_then_complete_changed_sources_then_partial_confirm():
    rows = []
    final_sources = {'new': 'new-source', 'revised': 'current-source'}
    for index in range(40):
        row = situation('partial-%02d' % index, source='confirm')
        row.update(package_sha256='partial', package_procedures={'new': 'new-source', 'revised': 'old-source'})
        rows.append(row)
    for index in range(6):
        row = situation('final-%02d' % index, source='train')
        row.update(package_sha256='final', package_procedures=final_sources)
        rows.append(row)
    for index in range(6):
        row = situation('complete-%02d' % index, source='train')
        row.update(package_sha256='superset', package_procedures={**final_sources, 'other': 'other-source'})
        rows.append(row)
    kwargs = dict(bench='zebralogic', configuration='zebra-pc-v7', step='s1', round=2,
        change_id='final', source_sha256='a'*64, final=True,
        final_package_sha256='final', final_procedures=final_sources)
    sampled = audit.sample_situations(rows, **kwargs)['situations']
    assert [s['package_sha256'] for s in sampled] == ['final'] * 6 + ['superset'] * 6
    excluded = [audit.situation_key(s) for s in sampled[:2]]
    later = audit.sample_situations(list(reversed(rows)), exclude=excluded, **kwargs)['situations']
    assert not set(excluded) & {audit.situation_key(s) for s in later}
    assert [s['package_sha256'] for s in later] == ['final'] * 4 + ['superset'] * 6 + ['partial'] * 2


def test_final_alf_later_steps_do_not_fall_back_while_final_package_steps_exist():
    rows = []
    for index in range(8):
        for package in ('partial', 'final'):
            row = situation('episode', step=index, source='confirm' if package == 'partial' else 'train')
            row.update(package_sha256=package, cell=package + str(index),
                       package_procedures={'new': 'current'} if package == 'final' else {})
            rows.append(row)
    result = audit.sample_situations(rows, bench='alfworld', configuration='alfworld-v4', step='s1', round=2,
        change_id='final', source_sha256='a'*64, final=True, final_package_sha256='final',
        final_procedures={'new': 'current'})
    assert len(result['situations']) == 3
    assert 0 in [s['step'] for s in result['situations']]
    assert all(s['package_sha256'] == 'final' for s in result['situations'])


def test_healthy_replay_keyword_hits_are_informational_in_judge_c6_counts():
    from skillopt.execskill import replay
    from tests.test_execskill_replay import qa_trajectories
    from tests.test_execskill_v29_runtime import procedure as runtime_procedure, worker
    proc = runtime_procedure()
    entry = replay.inputs_of(qa_trajectories()[0])
    outcome = replay.replay(worker(proc).start(replay.solo(proc), kind='cell'), proc, entry)
    assert outcome.notes and any(f.get('informational') for f in outcome.faults)
    counts = audit.c6_counts([entry], {entry['cell']: outcome})
    assert counts['faults'] == 0 and counts['keyword_hits']['count'] > 0
    assert counts['keyword_hits']['sentences']
    prompt = audit.situation_prompt([proc], 'zebralogic', [], {proc.id: counts})
    assert '"faults": 0' in prompt and '"keyword_hits":' in prompt
    outcome.faults.append({'kind': 'crash:RuntimeError'})
    assert audit.c6_counts([entry], {entry['cell']: outcome})['faults'] == 1


@pytest.mark.parametrize('invalid', ['NaN', 'Infinity', '-Infinity', '1e999', 'escaped-surrogate', 'literal-surrogate'])
def test_noncanonical_judge_reply_retries_then_unavailable_and_persists(tmp_path, invalid):
    from skillopt.validator_pilot.api import write_immutable_json
    class NoncanonicalJudge(Judge):
        def plain(self, *args, **kwargs):
            raw = super().plain(*args, **kwargs)
            if invalid.endswith('surrogate'):
                value = json.loads(raw)
                target = value['templates'][0] if 'templates' in value else value['program']
                target['reason'] = '\ud800'
                return json.dumps(value, ensure_ascii=(invalid == 'escaped-surrogate'))
            # Optional nested fields were previously accepted without validation.
            return raw.replace('"reason":', '"extra": ' + invalid + ', "reason":', 1)
    bad = NoncanonicalJudge()
    result = run(bad, Judge(template='P2'))
    assert result['audit_incomplete'] and not result['available']['G']
    assert not result['confirmed'] and len(bad.calls) == 4
    for pair in result['requests']:
        request = pair['requests']['G']
        assert request['parsed'] is None and not request['available']
        assert len(request['retries']) == 1 and len(request['raw_replies']) == 2
        assert request['unavailable_reason'] == 'non_canonical_json'
    path = tmp_path / 'unavailable-audit.json'
    write_immutable_json(path, result)
    assert json.loads(path.read_text())['audit_incomplete']
