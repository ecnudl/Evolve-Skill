"""Bounded instruction-writer requests over explicitly supplied practice rows."""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy

from skillopt.coevo5 import texts
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import profiles as p, v225_cards as cards, v222_cards

VIEW_CHARS = 3000
REPLY_HEAD = 300
REPLY_TAIL = 1200
REFERENCE_CHARS = 300
TRUNCATION_MARK = '…[truncated]'
RESULT_FIELDS = ('stage', 'touched', 'fixed', 'broken', 'net', 'gain_floor', 'harm_cap', 'whole_batch',
                 'decision', 'failing_clause')
FORBIDDEN = ('more than 3,000 characters or 12 bullets', 'answer, action or calc tags or code fences',
             'task identifiers or file paths', 'reference answers or values', 'copied example text')
SMOKE_EVIDENCE = ('smoke', 'engineering_fixture')
CALLS_PER_ROUND = 2
CALLS_PER_BENCH = 6
CALLS_PER_CHAIN = 24


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _text(value):
    return value if isinstance(value, str) else _json(value)


def truncate(value, limit, *, head=None, tail=None):
    value = _text(value)
    if len(value) <= limit:
        return value
    if head is None:
        head = (limit - len(TRUNCATION_MARK)) // 2
        tail = limit - len(TRUNCATION_MARK) - head
    return value[:head] + TRUNCATION_MARK + value[-tail:]


def _unit(row, *, chain, bench, k, c, smoke=False):
    """Fail before selecting examples if any offered row has protected provenance."""
    unit = row.get('unit', '')
    if smoke:
        require(row.get('evidence') in SMOKE_EVIDENCE, 'Smoke writer rows require smoke or fixture evidence')
        require(bench == 'searchqa' and c == 1 and unit == chain + '/v225-smoke/price/searchqa/C0'
                and row.get('bench') == bench and row.get('arm') == 'C0',
                'Smoke writer sees only reserved SearchQA C0 practice observations')
        p.verified(row, 'trajectory')
        return 'smoke_C0'
    match = re.fullmatch(re.escape(f'{chain}/s{k}-{bench}/') + r'(run|card-train-c([1-3]))', unit)
    require(match is not None and row.get('bench') == bench, 'Writer examples are own-step practice run/card-train cells only')
    if match.group(1) == 'run':
        require(row.get('arm') in ('S', 'parent') or row.get('arm_kind') == 'parent', 'Writer run examples are parent cells')
    else:
        require(c > 1 and int(match.group(2)) == c - 1 and row.get('arm') == "S'",
                'Writer revisions see only the immediately preceding card training candidate')
    if 'record_sha256' in row:
        p.verified({key: value for key, value in row.items() if key not in ('card_fixed', 'card_broken')}, 'trajectory')
    else:
        require(row.get('evidence') == 'engineering_fixture', 'Unsealed writer rows must be authored engineering fixtures')
    return match.group(1)


def _public_and_reply(row):
    if 'view' in row and row.get('evidence') == 'engineering_fixture':
        return _text(row['view']), str(row.get('reply') or '')
    calls = row.get('calls') or []
    first = next((call for call in calls if call.get('purpose') == 'first'), None)
    require(first is not None and isinstance(first.get('user'), str), 'Writer examples require a public request view')
    replies = row.get('replies') or []
    deciding = row.get('deciding_receipt')
    reply = (replies[deciding] if type(deciding) is int and 0 <= deciding < len(replies)
             else next((text for text in reversed(replies) if isinstance(text, str)), ''))
    return first['user'], reply or ''


def select_examples(rows, *, chain, bench, k, c, references, allowed_ids, smoke=False, incumbent_evidence=None):
    require(bench in cards.BENCHES[:-1] and 1 <= c <= cards.CARD_ROUNDS, 'A registered learned-card round')
    require(not smoke or incumbent_evidence in SMOKE_EVIDENCE,
            'Smoke writer incumbent requires smoke or fixture evidence')
    allowed = set(allowed_ids)
    require(set(references) <= allowed, 'Writer references belong only to the run allocation')
    chosen = {}
    for row in rows:
        _unit(row, chain=chain, bench=bench, k=k, c=c, smoke=smoke)
        key = row.get('task_id')
        require(key in allowed, 'Writer examples are registered run-slice items')
        run = row.get('run', 0)
        require(type(run) is int and run >= 0, 'Writer example has a registered run number')
        if key not in chosen or run < chosen[key].get('run', 0):
            chosen[key] = row
    def order(row):
        priority = (0 if row.get('card_broken') else 1) if row['token'] == 'fail' else (0 if row.get('card_fixed') else 1)
        return priority if c > 1 else 0, cards.sha256(_json([p.SEED, 'v225-card-examples', chain, bench, k, c, row['task_id']]))
    output = []
    for token, limit in (('fail', p.ENGINEER_SHOWN['failures']), ('pass', p.ENGINEER_SHOWN['successes'])):
        candidates = sorted((row for row in chosen.values() if row.get('token') == token), key=order)
        for row in candidates[:limit]:
            view, reply = _public_and_reply(row)
            entry = {'view': truncate(view, VIEW_CHARS),
                     'reply': truncate(reply, REPLY_HEAD + REPLY_TAIL, head=REPLY_HEAD, tail=REPLY_TAIL),
                     'outcome': token}
            if token == 'fail' and row['task_id'] in references:
                entry['reference'] = _text(references[row['task_id']])[:REFERENCE_CHARS]
            output.append(entry)
    return output


def task_card(bench, runtime):
    return cards.ZEBRA_TASK_CARD if bench == 'zebralogic' else texts.solver_cards(texts.CARDS, runtime)[bench]


def count_result(result, *, configuration=None):
    require(isinstance(result, dict), 'A card revision has count-only feedback')
    stage = result.get('stage')
    require(stage in ('static', 'training', 'confirmation', 'acceptance'), 'A registered deciding card stage')
    clause = result.get('failing_clause', result.get('clause'))
    extra = ('candidate_error', 'cross_bench_harm') if p.is_v226(configuration) else ()
    require(clause is None or clause in ('gain_floor', 'harm_ratio', 'whole_batch', *cards.RETRY_REASONS, *extra),
            'A card revision names a registered failing clause')
    found = {key: result.get(key) for key in RESULT_FIELDS}
    found['failing_clause'] = clause
    for key in ('touched', 'fixed', 'broken', 'net', 'gain_floor', 'harm_cap', 'whole_batch'):
        require(found[key] is None or type(found[key]) in (int, float), 'Card feedback contains counts, never rows')
    require(found['decision'] in (None, 'accept', 'reject', 'card_rejected_static'), 'A registered card decision')
    return found


def build_request(*, bench, runtime, current_card, examples, c, previous_card=None, result=None, configuration=None):
    request = {'request': 'write' if c == 1 else 'revise', 'task_card': task_card(bench, runtime),
        'format_block': v222_cards.format_text(bench), 'current_card': current_card,
        'card_rules': {'max_chars': cards.MAX_CARD_CHARS, 'max_bullets': cards.MAX_CARD_BULLETS,
                       'forbidden': list(FORBIDDEN)},
        'examples': list(examples), 'evidence': 'practice_only'}
    if c > 1:
        require(isinstance(previous_card, str), 'A revision carries its previous card')
        request.update(previous_card=previous_card, result=count_result(result,
            **({'configuration': configuration} if p.is_v226(configuration) else {})))
    dropped = {'successes': 0, 'failures': 0}
    retry_chars = 2 + max(len(cards.CARD_RETRY.format(reason=reason)) for reason in cards.RETRY_REASONS.values())
    while len(_json(request)) + retry_chars > cards.CARD_WRITER_INPUT_CHARS and request['examples']:
        successes = [i for i, row in enumerate(request['examples']) if row['outcome'] == 'pass']
        index = successes[-1] if successes else len(request['examples']) - 1
        removed = request['examples'].pop(index)
        dropped['successes' if removed['outcome'] == 'pass' else 'failures'] += 1
    require(len(_json(request)) + retry_chars <= cards.CARD_WRITER_INPUT_CHARS, 'Fixed writer request fits its registered input ceiling')
    return request, dropped


def _persist(path, record):
    """Publish an immutable fsynced record before exposing the next action."""
    write_json(path, record)
    descriptor = os.open(safe_path(path).parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _durable_reply(roles, *, state_root, binding, system, sent, label, ordinal, evidence):
    """Reserve once before transport; replay only an acknowledged stored reply."""
    from skillopt.coevo5.cells import exclusive
    from .errors import BudgetStop
    root = safe_path(state_root)
    require(ordinal in (1, 2), 'At most two writer dispatches per round')
    identity = {key: binding[key] for key in ('chain', 'bench', 'step', 'round')}
    key = '%s-s%d-%s-c%d' % (identity['chain'], identity['step'], identity['bench'], identity['round'])
    slot = key + '-call-%d' % ordinal
    call_path, reply_path = root/'dispatches'/(slot+'.json'), root/'replies'/(slot+'.json')
    request_sha256 = digest({'system': system, 'user': sent, 'label': label, 'max_tokens': 32768})
    expected = p.record('v225-writer-dispatch', evidence, {**identity, 'ordinal': ordinal,
        'binding_sha256': digest(binding), 'request_sha256': request_sha256})
    with exclusive(root/'locks'/(slot+'.lock'), wait=True):
        with exclusive(root/'.lock', wait=True):
            _persist(root/'rounds'/(key+'.json'), p.record('v225-writer-round', evidence, binding))
            if call_path.exists():
                require(p.verified(read_json(call_path), 'v225-writer-dispatch') == expected,
                        'A writer dispatch resumes its exact registered request')
                if not reply_path.exists():
                    raise BudgetStop('Writer dispatch is reserved without a persisted reply; do not resend')
            else:
                records = [p.verified(read_json(path), 'v225-writer-dispatch')
                           for path in sorted((root/'dispatches').glob('*.json'))]
                require(all(row['chain'] == identity['chain'] for row in records),
                        'Writer dispatch accounting belongs to one chain')
                used = sum(all(row[field] == value for field,value in identity.items()) for row in records)
                bench_used = sum(row['bench'] == identity['bench'] for row in records)
                if used >= CALLS_PER_ROUND or bench_used >= CALLS_PER_BENCH or len(records) >= CALLS_PER_CHAIN:
                    raise BudgetStop('Writer dispatch cap exhausted: two per round, six per bench and twenty-four per chain')
                _persist(call_path, expected)
        if reply_path.exists():
            saved = p.verified(read_json(reply_path), 'v225-writer-reply')
            require(saved['dispatch_sha256'] == expected[p.RECORD_HASH], 'Writer reply binds its reserved dispatch')
            return saved['reply'], deepcopy(saved['calls'])
        before = len(roles.calls)
        reply = roles.plain('card_writer', system, sent, label=label, max_tokens=32768)
        calls = deepcopy(roles.calls[before:])
        require(len(calls) == 1, 'One reserved writer dispatch records one role call')
        _persist(reply_path, p.record('v225-writer-reply', evidence, {
            'dispatch_sha256': expected[p.RECORD_HASH], 'reply': reply, 'calls': calls}))
        return reply, calls


def write(roles, *, chain, bench, k, c, incumbent, rows, references, allowed_ids, corpus, practice_ids,
          runtime=None, previous_card=None, result=None, label=None, smoke=False, state_root=None, configuration=None):
    """At most two durable calls; completed replies survive unit retries."""
    require(chain in p.CHAINS and type(k) is int and 1 <= k <= 5, 'A registered writer chain and step')
    require(not smoke or incumbent.evidence in SMOKE_EVIDENCE,
            'Smoke writer incumbent requires smoke or fixture evidence')
    require(state_root is not None or incumbent.evidence == 'engineering_fixture',
            'A real writer uses durable per-chain dispatch accounting')
    examples = select_examples(rows, chain=chain, bench=bench, k=k, c=c, references=references,
                               allowed_ids=allowed_ids, smoke=smoke, incumbent_evidence=incumbent.evidence)
    own = incumbent.card_for(bench)
    request, dropped = build_request(bench=bench, runtime=runtime or {}, c=c,
        current_card=cards.metadata(own)['text'] if own is not None else '', examples=examples,
        previous_card=previous_card, result=result,
        **({'configuration': configuration} if p.is_v226(configuration) else {}))
    system = cards.CARD_WRITE_SYSTEM if c == 1 else cards.CARD_REVISE_SYSTEM
    message = _json(request)
    label = label or f'{chain}/s{k}-{bench}/card-write-c{c}'
    binding = {'chain':chain, 'bench':bench, 'step':k, 'round':c,
        'incumbent_sha256':incumbent.sha256, 'request':request, 'prompt_sha256':cards.sha256(system),
        'label':label, 'source_mode':'reserved_smoke_C0' if smoke else 'practice_run_or_card_training'}
    recorded = []
    violations, text, previous = [], None, None
    for attempt in (1, 2):
        sent = message if attempt == 1 else message + '\n\n' + cards.CARD_RETRY.format(reason=cards.RETRY_REASONS[previous])
        require(len(sent) <= cards.CARD_WRITER_INPUT_CHARS, 'Retry request fits the input ceiling')
        call_label = f'card_writer/{label}/{attempt}'
        if state_root is not None:
            reply, calls = _durable_reply(roles, state_root=state_root, binding=binding, system=system,
                sent=sent, label=call_label, ordinal=attempt, evidence=incumbent.evidence)
        else:
            before = len(roles.calls)
            reply = roles.plain('card_writer', system, sent, label=call_label, max_tokens=32768)
            calls = deepcopy(roles.calls[before:])
        recorded.extend(calls)
        text = texts.instruction_text(reply) if isinstance(reply, str) else None
        violation = cards.card_violation(text, bench=bench, corpus=corpus, shown=request['examples'],
            task_card=request['task_card'], format_block=request['format_block'], practice_ids=practice_ids)
        violations.append(violation)
        if violation is None:
            break
        previous = violation
    call_record = p.record('card-writer', incumbent.evidence, {'chain': chain, 'bench': bench, 'step': k, 'round': c,
        'request': request, 'prompt_sha256': cards.sha256(system), 'calls': recorded,
        'static': violations, 'dropped': dropped, 'card': text,
        'source_mode': 'reserved_smoke_C0' if smoke else 'practice_run_or_card_training',
        'decision': 'card_written' if violations[-1] is None else 'card_rejected_static'})
    return {'text': text if violations[-1] is None else None, 'static': violations[-1], 'static_attempts': violations,
        'decision': call_record['decision'], 'calls': len(recorded), 'call_record': call_record,
        'writer_sha256': call_record[p.RECORD_HASH], 'examples': request['examples'], 'dropped': dropped}
