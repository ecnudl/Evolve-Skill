"""OfficeQA part of the item bank: the stages that turn the 74 training items into number twins (BANK-PILOT.md).

    trace   one derivation per parent from the annotator role (the item's question, document and REFERENCE answer;
            training side), checked by fixed code and anchored on the reference (``oqa.anchor``); one repair request
            that names the failed check; the writer's coded mistakes are kept when they check and differ.
    twins   fixed code, no model: up to TWINS_PER_PARENT number twins per anchored parent, each with its code rubric.
    check   the checker = the benchmark's own solver request with the hand card, sent to the solver client: CHECK_RUNS
            runs per parent, one per twin and a second one when the first fails. A twin is DROPPED only when the
            checker solves the parent every time and the twin never (the changed numbers broke something the
            derivation does not see); a twin of a parent the checker cannot solve stays, marked unconfirmed -- a
            filter on "the checker solved it" would remove exactly the hard items.
    newq    new questions on a parent's document from the question writer, in two arms per parent: ``plain`` (the
            document and example questions only) and ``brief`` (the research brief of ``research`` added). The
            answer is computed by fixed code (``oqa.check_new_question``); a parent that shares a page with an item
            outside the pool gets none (BANK-PILOT B12). A new question has no reference to anchor on, so the
            checker must VERIFY it: two runs, a third when they disagree, kept with two passes.
    diagnose  (B24) per REAL parent of the SHOWN side that the checker failed at least once: the diagnostician reads
            the document, the question, the reference answer with its derivation and the checker's replies, and
            names the cause, a general weakness and what a new question must require to expose it; one more request
            merges the diagnoses into at most ``prompts.MAX_WEAKNESSES`` weaknesses. Nothing of the judging side is
            read. The third arm of ``newq``, ``target``, gives these weaknesses to the question writer.
    audit   (B23) the auditor checks the MEANING of a derivation (is each quoted figure the one the question needs,
            is the computation the one asked for) without seeing a computed answer; AUDIT_RUNS independent requests,
            ACCEPTED when every one accepts. Calibration on what is known: the anchored derivation of a real parent
            is right, its coded mistakes are wrong. When the calibration meets ``AUDIT_RULE`` the audit may vouch
            for a new question that the checker does not solve (a hard question whose answer can still be trusted).
    report  counts, drop reasons, checker pass rates of parents against twins (difficulty parity), the arms of new
            questions side by side, the rubric's labels of the checker's wrong replies, the diagnosis, the audit's
            calibration and its verdicts against the checker's, and the tokens charged.

Records are write-once under ``<root>/officeqa/``: ``trace/<parent>.json``, ``items/<item>.json`` (the practice item
in pool shape: benchmark, task_id, family_id, part, public, private), ``records/<item>.json`` (provenance, side and
rubric; never shown to a solver), ``check/<id>.json``. A stage that stops (token cap, interruption) is run again
with the same command; finished parents and calls are not repeated.
"""
from __future__ import annotations

import random
import re

from .. import units
from . import (ARMS, AUDIT_RULE, AUDIT_RUNS, CHECK_RUNS, DIAGNOSIS_REPLY_CHARS, NEW_QUESTIONS_PER_ARM, SEED, SIDES,
               TRACE_ATTEMPTS, TWINS_PER_PARENT, oqa, prompts, report)
from .env import read_object, text_sha256
from . import rejudge

BENCH = 'officeqa'
PARENT_ANSWER = 'parent_answer'   # a twin's wrong reply that is the parent's answer
NO_REPLY = 'no_reply'             # a run whose reply the model cut or withheld: final and wrong
TWIN_PARENT_DROPS = 2             # dropped twins of one parent from which ALL its twins are set aside
REPAIRABLE = set(oqa.REASONS) - {'not_numeric', 'not_found'}
ANSWER_TAG = re.compile(r'<answer>(.*?)</answer>', re.S | re.I)


def safe_id(task_id):
    """A parent id as a file and tag name (ids are 'UID0065'-like; anything else is made plain)."""
    return re.sub(r'[^A-Za-z0-9_.-]', '_', task_id)


# ---- trace ---------------------------------------------------------------------------------------------------------
def _mistakes(found, normal, context):
    """The writer's coded mistakes that check as derivations, carry a registered label, give as many answers as the
    right derivation and a different value."""
    kept, right = [], oqa.exact_values(normal)
    for entry in found if isinstance(found, list) else []:
        if not isinstance(entry, dict) or entry.get('label') not in prompts.MISTAKE_LABELS:
            continue
        try:
            trace = oqa.check_trace(entry, context)
            values = oqa.exact_values(trace)
        except oqa.Drop:
            continue
        if len(values) == len(right) and values != right:
            kept.append({'label': entry['label'], 'text': str(entry.get('text') or '')[:300], 'trace': trace})
    return kept[:3]


def trace_parent(env, item):
    """The write-once trace record of one parent: status anchored / not_numeric / not_found / dropped / no_reply."""
    parent, public, reference = item['task_id'], item['public'], item['private']['answer']

    def compute():
        attempts, previous, failure = [], None, None
        for attempt in range(1, TRACE_ATTEMPTS + 1):
            system, user = prompts.trace_request(public['question'], reference, public['context'], previous, failure)
            sent = env.call(BENCH + '/trace', '%s-a%d' % (safe_id(parent), attempt), system, user)
            row = {'attempt': attempt, 'request_sha256': sent['request_sha256'], 'failure': sent['failure']}
            attempts.append(row)
            if sent['reply'] is None:
                if (sent['failure'] or '').startswith('infrastructure:'):
                    raise RuntimeError('infrastructure: ' + str(sent['failure']))  # not a verdict: run the stage again
                return {'parent': parent, 'status': 'no_reply', 'reason': sent['failure'], 'attempts': attempts}
            found = read_object(sent['reply'])
            try:
                if found is None:
                    raise oqa.Drop('shape')
                normal, computed = oqa.anchor(found, public['context'], reference, oqa.officeqa_judge)
            except oqa.Drop as refused:
                row['check'], row['detail'] = refused.reason, refused.detail[:200]
                if refused.reason in ('not_numeric', 'not_found'):
                    return {'parent': parent, 'status': refused.reason, 'reason': refused.reason, 'attempts': attempts}
                previous, failure = sent['reply'], prompts.failure_text(refused.reason, refused.detail[:200])
                continue
            row['check'] = 'anchored'
            mistakes = _mistakes(found.get('mistakes'), normal, public['context'])
            return {'parent': parent, 'status': 'anchored', 'reason': None, 'attempts': attempts, 'trace': normal,
                    'computed': computed, 'mistakes': mistakes, 'rubric': oqa.rubric(normal, mistakes=mistakes)}
        return {'parent': parent, 'status': 'dropped', 'reason': attempts[-1].get('check'), 'attempts': attempts}

    return env.once((BENCH, 'trace', safe_id(parent) + '.json'), compute)


def stage_trace(env, items):
    def work(item):
        try:
            return trace_parent(env, item)['status']
        except units.Stop:
            raise
        except RuntimeError as failed:  # an infrastructure failure: nothing written, the next run sends it again
            return str(failed)
    return report.tally(env.fan(items, work, label='trace'))


# ---- twins ---------------------------------------------------------------------------------------------------------
def twin_id(parent, number):
    return '%s~n%d' % (parent, number)


def make_twins(env, item, side):
    """The twin items of one anchored parent (fixed code). Returns [(item id or None, drop reason or None)]."""
    parent = item['task_id']
    record = env.read(BENCH, 'trace', safe_id(parent) + '.json')
    if record['status'] != 'anchored':
        return []
    trace, mistakes, out, seen = record['trace'], record['mistakes'], [], set()
    for number in range(1, TWINS_PER_PARENT + 1):
        made = twin_id(parent, number)
        if env.exists(BENCH, 'records', safe_id(made) + '.json'):
            out.append((made, None))
            continue
        rng = random.Random('%d:%s:%d' % (SEED, parent, number))
        try:
            context, gold, changes = oqa.make_twin(item['public']['context'], item['public']['question'], trace,
                                                   record['computed'], rng, oqa.officeqa_judge)
            key = tuple(sorted(changes.items()))
            if key in seen or not oqa.officeqa_judge(gold, gold):
                raise oqa.Drop('answer_unchanged', 'a repeated draw')
        except oqa.Drop as refused:
            out.append((None, refused.reason))
            continue
        seen.add(key)
        twin = {'benchmark': BENCH, 'task_id': made, 'family_id': item.get('family_id', BENCH + ':' + parent),
                'part': 'bank', 'public': {'question': item['public']['question'], 'context': context},
                'private': {'answer': gold, 'source_sha256': item['private'].get('source_sha256')}}
        units.write_json(env.path(BENCH, 'items', safe_id(made) + '.json'), twin)
        units.write_json(env.path(BENCH, 'records', safe_id(made) + '.json'), {
            'item': made, 'kind': 'number_twin', 'parent': parent, 'side': side, 'seed': '%d:%s:%d' % (SEED, parent, number),
            'changes': [{'old': old, 'new': new, 'occurrences': oqa.count_tokens(old, item['public']['context'])}
                        for old, new in sorted(changes.items())],
            'trace_sha256': text_sha256(prompts.dumps(trace)), 'context_sha256': text_sha256(context),
            'rubric': oqa.rubric(trace, changes, mistakes)})
        out.append((made, None))
    return out


def stage_twins(env, items, sides):
    made, drops = [], []
    for item in items:
        for item_id, reason in make_twins(env, item, sides[item['task_id']]):
            (made if item_id else drops).append(item_id or reason)
    return {'made': len(made), 'dropped': report.tally(drops)}


# ---- new questions -------------------------------------------------------------------------------------------------
def question_id(parent, arm, number):
    return '%s~q%s%d' % (parent, ARMS[arm], number)


def write_questions(env, item, side, examples, arm, brief, weaknesses=None):
    """The write-once record of one parent and arm: how many entries the writer gave, the items kept, the drops.
    Arm 'target' sends the diagnosed ``weaknesses`` and records which one each kept question targets."""
    parent, context = item['task_id'], item['public']['context']
    known = {row['id'] for row in weaknesses or []}

    def compute():
        system, user = prompts.newq_request(context, item['public']['question'], examples, NEW_QUESTIONS_PER_ARM,
                                            brief if arm == 'brief' else None, weaknesses if arm == 'target' else None)
        sent = env.call(BENCH + '/newq', '%s-%s' % (safe_id(parent), arm), system, user)
        if sent['reply'] is None:
            if (sent['failure'] or '').startswith('infrastructure:'):
                raise RuntimeError('infrastructure: ' + str(sent['failure']))
            return {'parent': parent, 'arm': arm, 'entries': 0, 'kept': [], 'drops': ['no_reply']}
        found = read_object(sent['reply']) or {}
        entries = found.get('items') if isinstance(found.get('items'), list) else []
        parent_trace = None
        if env.exists(BENCH, 'trace', safe_id(parent) + '.json'):
            parent_trace = env.read(BENCH, 'trace', safe_id(parent) + '.json').get('trace')
        kept, drops, siblings = [], [], []
        for entry in entries[:NEW_QUESTIONS_PER_ARM]:
            try:
                question, normal, gold = oqa.check_new_question(
                    entry, context, parent_question=item['public']['question'], parent_trace=parent_trace,
                    siblings=siblings)
            except oqa.Drop as refused:
                drops.append(refused.reason)
                continue
            made = question_id(parent, arm, len(kept) + 1)
            mistakes = _mistakes(entry.get('mistakes'), normal, context)
            units.write_json(env.path(BENCH, 'items', safe_id(made) + '.json'), {
                'benchmark': BENCH, 'task_id': made, 'family_id': item.get('family_id', BENCH + ':' + parent),
                'part': 'bank', 'public': {'question': question, 'context': context},
                'private': {'answer': gold, 'source_sha256': item['private'].get('source_sha256')}})
            units.write_json(env.path(BENCH, 'records', safe_id(made) + '.json'), {
                'item': made, 'kind': 'new_question', 'arm': arm, 'parent': parent, 'side': side, 'trace': normal,
                'request_sha256': sent['request_sha256'], 'mistakes': [m['label'] for m in mistakes],
                'mistake_traces': [{'label': m['label'], 'trace': m['trace']} for m in mistakes],
                'targets': (entry['targets'] if arm == 'target' and isinstance(entry.get('targets'), str)
                            and entry['targets'] in known else None),
                'rubric': oqa.rubric(normal, mistakes=mistakes)})
            kept.append(made)
            siblings.append((question, normal))
        return {'parent': parent, 'arm': arm, 'entries': len(entries), 'kept': kept, 'drops': drops}

    return env.once((BENCH, 'newq', '%s-%s.json' % (safe_id(parent), arm)), compute)


def stage_newq(env, items, sides, shared_pages, arms, brief, weaknesses=None):
    """New questions for every parent that shares no page with an item outside the pool. Example questions: two
    real questions of other parents on the SAME side (a seeded draw), so that nothing crosses the two sides. The
    ``weaknesses`` of arm 'target' come from failed real items of the shown side only and go to both sides."""
    eligible = [item for item in items if item['task_id'] not in set(shared_pages)]
    tasks = []
    for item in eligible:
        others = sorted(other['public']['question'] for other in items
                        if sides[other['task_id']] == sides[item['task_id']] and other['task_id'] != item['task_id'])
        examples = random.Random('%d:examples:%s' % (SEED, item['task_id'])).sample(others, min(2, len(others)))
        tasks += [(item, examples, arm) for arm in arms]

    def work(task):
        item, examples, arm = task
        try:
            record = write_questions(env, item, sides[item['task_id']], examples, arm, brief, weaknesses)
            return '%s: kept %d' % (arm, len(record['kept']))
        except units.Stop:
            raise
        except RuntimeError as failed:
            return str(failed)
    return {'parents': len(eligible), 'results': report.tally(env.fan(tasks, work, label='new questions'))}


# ---- check ---------------------------------------------------------------------------------------------------------
def solve_once(env, tools, public, gold, tag, sheet=None, unit=BENCH + '/check'):
    """One checker run: the benchmark's solver request (``tools['card']`` as the system card: the hand card for the
    checker) to the solver client, scored by the benchmark's answer-tag scorer. {'verdict': pass / fail / unknown,
    'answer', 'label'}; ``label`` is the rubric's name for a wrong reply (None without a rubric or for a pass).
    ``unit``: where the calls are stored (a contrast configuration has its own)."""
    call = env.solver_call(unit, tag)
    prediction = tools['solve'](BENCH, public, tools['card'], call, runtime=tools['runtime'])
    if prediction.get('status') != 'available' or not isinstance(prediction.get('output'), str):
        if call.recorder.sends and not call.recorder.infrastructure_unknown():
            # the model answered and the answer is unusable (cut at the token bound, filtered, empty): a chain scores
            # such a cell 0 and never runs it again; so does the checker (review 2026-11-13: a redraw until a
            # reply arrives would lift the pass rates)
            return {'verdict': 'fail', 'answer': '', 'label': NO_REPLY, 'reason': str(prediction.get('reason'))[:120]}
        return {'verdict': 'unknown', 'reason': str(prediction.get('reason'))[:120]}
    output = prediction['output']
    found = ANSWER_TAG.findall(output)
    answer = found[-1].strip() if found else ''
    verdict = tools['score'](BENCH, output, gold)['status']
    label = oqa.classify(answer, sheet) if verdict == 'fail' and sheet is not None else None
    return {'verdict': verdict, 'answer': answer[:200], 'label': label}


def check_parent(env, tools, item):
    parent = item['task_id']

    def compute():
        sheet = None
        if env.exists(BENCH, 'trace', safe_id(parent) + '.json'):
            sheet = env.read(BENCH, 'trace', safe_id(parent) + '.json').get('rubric')
        runs = [solve_once(env, tools, item['public'], item['private']['answer'], '%s-r%d' % (safe_id(parent), run),
                           sheet) for run in range(1, CHECK_RUNS + 1)]
        if any(run['verdict'] == 'unknown' for run in runs):
            raise RuntimeError('unknown checker run')  # undelivered or cut reply: no verdict, run the stage again
        return {'id': parent, 'kind': 'parent', 'runs': runs, 'passes': sum(run['verdict'] == 'pass' for run in runs)}

    return env.once((BENCH, 'check', safe_id(parent) + '.json'), compute)


def check_twin(env, tools, twin, record, parent_passes, parent_gold=None):
    """Status confirmed (the checker reached the made answer), unconfirmed (it did not, and it does not solve the
    parent every time either: no evidence), dropped (it solves the parent every time and the twin never). A wrong
    reply that the judge takes for the PARENT's answer is labelled ``parent_answer``: the solver did not compute
    from the changed numbers (the document still prints the old result, or a linked figure the twin left alone)."""
    made = twin['task_id']

    def compute():
        runs = [solve_once(env, tools, twin['public'], twin['private']['answer'], safe_id(made) + '-r1', record['rubric'])]
        solvable = parent_passes == CHECK_RUNS
        if runs[0]['verdict'] == 'fail' and solvable:
            runs.append(solve_once(env, tools, twin['public'], twin['private']['answer'], safe_id(made) + '-r2',
                                   record['rubric']))
        if any(run['verdict'] == 'unknown' for run in runs):
            raise RuntimeError('unknown checker run')
        for run in runs:
            if (run['verdict'] == 'fail' and parent_gold is not None and run['answer']
                    and tools['score'](BENCH, '<answer>%s</answer>' % run['answer'], parent_gold)['status'] == 'pass'):
                run['label'] = PARENT_ANSWER
        passes = sum(run['verdict'] == 'pass' for run in runs)
        status = 'confirmed' if passes else ('dropped' if solvable else 'unconfirmed')
        return {'id': made, 'kind': 'number_twin', 'parent': record['parent'], 'runs': runs, 'passes': passes,
                'parent_passes': parent_passes, 'status': status}

    return env.once((BENCH, 'check', safe_id(made) + '.json'), compute)


def twin_statuses(rows):
    """{twin id: final status} of checked twins. A parent with TWIN_PARENT_DROPS or more dropped twins loses ALL its
    twins (``dropped_with_parent``): the checker solves that parent every time and its twins hardly ever, so the
    derivation's path through the document is not the path a solver takes once numbers change (a printed total, a
    ratio or a repeated figure the twin left unchanged). Pilot 2026-11-13: 23 of 198 twins were dropped, 20 of them
    on 6 parents."""
    dropped = {}
    for row in rows:
        if row['status'] == 'dropped':
            dropped[row['parent']] = dropped.get(row['parent'], 0) + 1
    return {row['id']: 'dropped_with_parent' if row['status'] != 'dropped' and dropped.get(row['parent'], 0) >= TWIN_PARENT_DROPS
            else row['status'] for row in rows}


def made_items(env, kind):
    """[(item, record)] of every made item of one kind written so far, in id order."""
    folder = env.path(BENCH, 'records')
    out = []
    for path in sorted(folder.glob('*.json')) if folder.is_dir() else []:
        record = units.read_json(path)
        if record['kind'] == kind:
            out.append((units.read_json(env.path(BENCH, 'items', path.name)), record))
    return out


def twins_of(env):
    return made_items(env, 'number_twin')


def check_question(env, tools, made, record):
    """Status verified (two passes of at most three runs) or unverified. A new question rests on nothing but its
    writer's derivation, so the checker has to reach its answer."""
    name = made['task_id']

    def compute():
        runs = [solve_once(env, tools, made['public'], made['private']['answer'], '%s-r%d' % (safe_id(name), run),
                           record['rubric']) for run in range(1, CHECK_RUNS + 1)]
        if sum(run['verdict'] == 'pass' for run in runs) == 1:
            runs.append(solve_once(env, tools, made['public'], made['private']['answer'],
                                   '%s-r%d' % (safe_id(name), CHECK_RUNS + 1), record['rubric']))
        if any(run['verdict'] == 'unknown' for run in runs):
            raise RuntimeError('unknown checker run')
        passes = sum(run['verdict'] == 'pass' for run in runs)
        return {'id': name, 'kind': 'new_question', 'arm': record['arm'], 'parent': record['parent'], 'runs': runs,
                'passes': passes, 'status': 'verified' if passes >= 2 else 'unverified'}

    return env.once((BENCH, 'check', safe_id(name) + '.json'), compute)


def stage_check(env, tools, items):
    def parent_work(item):
        try:
            return check_parent(env, tools, item)['passes']
        except units.Stop:
            raise
        except RuntimeError:
            return None
    passes = dict(zip([item['task_id'] for item in items], env.fan(items, parent_work, label='check parents')))

    golds = {item['task_id']: item['private']['answer'] for item in items}

    def twin_work(pair):
        twin, record = pair
        if passes.get(record['parent']) is None:
            return 'parent_unchecked'
        try:
            return check_twin(env, tools, twin, record, passes[record['parent']], golds.get(record['parent']))['status']
        except units.Stop:
            raise
        except RuntimeError:
            return 'unknown'
    statuses = env.fan(twins_of(env), twin_work, label='check twins')

    def question_work(pair):
        made, record = pair
        try:
            return check_question(env, tools, made, record)['status']
        except units.Stop:
            raise
        except RuntimeError:
            return 'unknown'
    questions = env.fan(made_items(env, 'new_question'), question_work, label='check new questions')
    return {'parents': report.tally('passes_%s' % value for value in passes.values()), 'twins': report.tally(statuses),
            'new_questions': report.tally(questions)}


# ---- diagnosis (B24) -----------------------------------------------------------------------------------------------
def _reply_text(env, tag):
    """The solver reply a checker run was scored on: the last delivered receipt of its stored calls ('' if none)."""
    path = env.path(BENCH + '/check', 'calls', tag + '.json')
    sends = units.read_json(path) if path.exists() else []
    for send in reversed(sends):
        receipt = send.get('receipt') or {}
        if receipt.get('ok') is True and isinstance(receipt.get('response'), str):
            return receipt['response']
    return ''


def diagnose_parent(env, item, check_row):
    """The write-once diagnosis of one REAL parent of the shown side that the checker failed at least once: status
    diagnosed (a weakness and a test were named) / void / no_reply."""
    parent, public = item['task_id'], item['public']
    name = safe_id(parent)

    def compute():
        wrong, right = [], None
        for index, run in enumerate(check_row['runs'], 1):
            text = _reply_text(env, '%s-r%d' % (name, index))
            if run['verdict'] == 'pass':
                right = right or text[:DIAGNOSIS_REPLY_CHARS]
            else:
                wrong.append({'reply': text[:DIAGNOSIS_REPLY_CHARS], 'answer_read_by_the_judge': run['answer']})
        trace = None
        if env.exists(BENCH, 'trace', name + '.json'):
            trace = env.read(BENCH, 'trace', name + '.json').get('trace')
        sent = env.call(BENCH + '/diagnosis', name, *prompts.diagnosis_request(
            public['context'], public['question'], item['private']['answer'], trace, wrong, right))
        base = {'parent': parent, 'passes': check_row['passes'], 'with_derivation': trace is not None,
                'labels': [run.get('label') for run in check_row['runs'] if run['verdict'] != 'pass']}
        if sent['reply'] is None:
            if (sent['failure'] or '').startswith('infrastructure:'):
                raise RuntimeError('infrastructure: ' + str(sent['failure']))
            return {**base, 'status': 'no_reply', 'reason': sent['failure']}
        found = read_object(sent['reply']) or {}
        text = lambda key: found[key].strip()[:600] if isinstance(found.get(key), str) else ''
        kind = found.get('kind') if found.get('kind') in prompts.WEAKNESS_KINDS else 'other'
        return {**base, 'status': 'diagnosed' if text('weakness') and text('test') else 'void', 'kind': kind,
                'cause': text('cause'), 'weakness': text('weakness'), 'test': text('test')}

    return env.once((BENCH, 'diagnosis', name + '.json'), compute)


def merge_weaknesses(env, parents):
    """The write-once list of weaknesses a question writer is shown, merged by one request from the diagnoses of
    ``parents`` (ids, in order). The request carries the kind, weakness and test sentences only, never an item."""
    def compute():
        rows = [env.read(BENCH, 'diagnosis', safe_id(parent) + '.json') for parent in parents
                if env.exists(BENCH, 'diagnosis', safe_id(parent) + '.json')]
        rows = [row for row in rows if row['status'] == 'diagnosed']
        cases = [{'case': number, 'kind': row['kind'], 'weakness': row['weakness'], 'test': row['test']}
                 for number, row in enumerate(rows, 1)]
        if not cases:
            return {'status': 'void', 'reason': 'no_diagnosis', 'shown': [], 'cases': 0}
        sent = env.call(BENCH + '/diagnosis', 'merge', *prompts.merge_request(cases))
        if sent['reply'] is None:
            if (sent['failure'] or '').startswith('infrastructure:'):
                raise RuntimeError('infrastructure: ' + str(sent['failure']))
            return {'status': 'void', 'reason': 'no_reply', 'shown': [], 'cases': len(cases)}
        found = read_object(sent['reply']) or {}
        shown, covered = [], []
        for entry in found.get('weaknesses') if isinstance(found.get('weaknesses'), list) else []:
            if not (isinstance(entry, dict) and isinstance(entry.get('weakness'), str) and entry['weakness'].strip()
                    and isinstance(entry.get('test'), str) and entry['test'].strip()):
                continue
            members = sorted({n for n in entry.get('cases') or [] if type(n) is int and 1 <= n <= len(cases)})
            shown.append({'id': 'w%d' % (len(shown) + 1),
                          'kind': entry.get('kind') if entry.get('kind') in prompts.WEAKNESS_KINDS else 'other',
                          'weakness': entry['weakness'].strip()[:400], 'test': entry['test'].strip()[:400]})
            covered.append(members)
            if len(shown) == prompts.MAX_WEAKNESSES:
                break
        return {'status': 'merged' if shown else 'void', 'reason': None if shown else 'shape', 'shown': shown,
                'cases': len(cases), 'cases_of': {row['id']: len(members) for row, members in zip(shown, covered)},
                'parents': [row['parent'] for row in rows]}

    return env.once((BENCH, 'diagnosis', 'weaknesses.json'), compute)


def stage_diagnose(env, items, sides):
    """Diagnose every real parent of the SHOWN side that the checker failed at least once, then merge."""
    rows = {}
    for item in items:
        name = safe_id(item['task_id'])
        if sides[item['task_id']] == SIDES[0] and env.exists(BENCH, 'check', name + '.json'):
            row = env.read(BENCH, 'check', name + '.json')
            if row['passes'] < len(row['runs']):
                rows[item['task_id']] = (item, row)

    def work(pair):
        try:
            return diagnose_parent(env, *pair)['status']
        except units.Stop:
            raise
        except RuntimeError as failed:
            return str(failed).split(':')[0]
    statuses = report.tally(env.fan(list(rows.values()), work, label='diagnose'))
    if 'infrastructure' in statuses:
        return {'failed_parents_of_the_shown_side': len(rows), 'diagnoses': statuses, 'merge': 'not run: some parents are open'}
    try:
        merged = merge_weaknesses(env, list(rows))
    except units.Stop:
        raise
    except RuntimeError as failed:
        return {'failed_parents_of_the_shown_side': len(rows), 'diagnoses': statuses, 'merge': str(failed).split(':')[0]}
    return {'failed_parents_of_the_shown_side': len(rows), 'diagnoses': statuses, 'merge': merged['status'],
            'weaknesses': [{'id': row['id'], 'kind': row['kind'], 'cases': merged['cases_of'][row['id']]}
                           for row in merged['shown']]}


def diagnosis_report(env):
    folder = env.path(BENCH, 'diagnosis')
    rows = [units.read_json(path) for path in sorted(folder.glob('*.json'))
            if path.name != 'weaknesses.json'] if folder.is_dir() else []
    merged = env.read(BENCH, 'diagnosis', 'weaknesses.json') if env.exists(BENCH, 'diagnosis', 'weaknesses.json') else None
    return {'parents_diagnosed': len(rows), 'status': report.tally(row['status'] for row in rows),
            'kinds': report.tally(row.get('kind') for row in rows if row['status'] == 'diagnosed'),
            'with_derivation': sum(row['with_derivation'] for row in rows),
            'merge': None if merged is None else {'status': merged['status'], 'cases': merged['cases'],
                                                  'weaknesses': merged['shown'], 'cases_of': merged.get('cases_of')}}


# ---- audit (B23) ---------------------------------------------------------------------------------------------------
def audit(env, name, base, context, question, trace):
    """The write-once audit record of one derivation: AUDIT_RUNS independent requests; status accepted (every run
    accepts) / refused (none) / split. A reply that is no verdict counts as a run that did not accept."""
    def compute():
        runs = []
        for run in range(1, AUDIT_RUNS + 1):
            sent = env.call(BENCH + '/audit', '%s-r%d' % (name, run), *prompts.audit_request(context, question, trace))
            if sent['reply'] is None:
                if (sent['failure'] or '').startswith('infrastructure:'):
                    raise RuntimeError('infrastructure: ' + str(sent['failure']))
                runs.append({'verdict': 'void', 'wrong': [], 'failure': sent['failure']})
                continue
            verdict, wrong = oqa.audit_verdict(read_object(sent['reply']))
            runs.append({'verdict': verdict, 'wrong': wrong})
        accepts = sum(run['verdict'] == 'accept' for run in runs)
        return {**base, 'runs': runs, 'accepts': accepts,
                'status': 'accepted' if accepts == len(runs) else ('refused' if accepts == 0 else 'split')}

    return env.once((BENCH, 'audit', name + '.json'), compute)


def calibration_tasks(env, items):
    """What is KNOWN about derivations: the anchored derivation of a real parent is right; a coded mistake of that
    parent whose answer the judge refuses for the reference is wrong."""
    tasks = []
    for item in items:
        parent, name = item['task_id'], safe_id(item['task_id'])
        if not env.exists(BENCH, 'trace', name + '.json'):
            continue
        record = env.read(BENCH, 'trace', name + '.json')
        if record['status'] != 'anchored':
            continue
        public = item['public']
        tasks.append(('cal-%s-ok' % name, {'id': parent, 'kind': 'calibration', 'truth': 'right', 'label': None},
                      public['context'], public['question'], record['trace']))
        for number, mistake in enumerate(record['mistakes'], 1):
            try:
                wrong = oqa.gold_text(oqa.compute_answers(mistake['trace']), record['trace'].get('suffix', ''))
            except oqa.Drop:
                continue
            if oqa.officeqa_judge(wrong, item['private']['answer']) is not False:
                continue
            tasks.append(('cal-%s-m%d' % (name, number),
                          {'id': parent, 'kind': 'calibration', 'truth': 'wrong', 'label': mistake['label']},
                          public['context'], public['question'], mistake['trace']))
    return tasks


def calibration_names(env, items):
    return [task[0] for task in calibration_tasks(env, items)]


def question_tasks(env, only_unverified=False):
    """The audit tasks of the new questions; ``only_unverified``: those the checker did not verify (the ones an
    audit can add something to: a verified question keeps its status whatever the audit says)."""
    tasks = []
    for made, record in made_items(env, 'new_question'):
        name = safe_id(made['task_id'])
        if only_unverified:
            if not env.exists(BENCH, 'check', name + '.json') or env.read(BENCH, 'check', name + '.json')['status'] == 'verified':
                continue
        tasks.append((name, {'id': made['task_id'], 'kind': 'new_question', 'arm': record['arm'],
                             'parent': record['parent'], 'truth': None, 'label': None},
                      made['public']['context'], made['public']['question'], record['trace']))
    return tasks


AUDIT_SCOPES = ('calibration', 'unverified', 'questions', 'all')


def stage_audit(env, items, scope):
    """``scope``: 'calibration' (the known derivations), 'unverified' (the new questions the checker did not
    verify), 'questions' (every new question) or 'all' (calibration and every question). Questions are audited only
    when the finished calibration meets the registered rule: an audit that cannot vouch for anything is not paid
    for."""
    assert scope in AUDIT_SCOPES, 'Scope among ' + str(AUDIT_SCOPES)

    def work(task):
        try:
            row = audit(env, *task)
            return '%s: %s' % (row['kind'] if row['truth'] is None else 'known ' + row['truth'], row['status'])
        except units.Stop:
            raise
        except RuntimeError as failed:
            return str(failed).split(':')[0]
    results = {}
    if scope in ('calibration', 'all'):
        results = report.tally(env.fan(calibration_tasks(env, items), work, label='audit calibration'))
    if scope == 'calibration' or 'infrastructure' in results:
        return {'scope': scope, 'results': results}
    summary = audit_report(env, {}, calibration_names(env, items))
    if not (summary and summary['meets_the_rule']):
        return {'scope': scope, 'results': results, 'questions': 'not audited: the calibration %s' % (
            'has not run' if not (summary and summary['calibration']['right']['derivations'])
            else 'is not complete' if summary['calibration']['missing'] else 'does not meet the rule')}
    asked = report.tally(env.fan(question_tasks(env, only_unverified=scope == 'unverified'), work, label='audit questions'))
    return {'scope': scope, 'results': {**results, **asked}}


def audit_report(env, checks, expected):
    """The calibration of the audit (how often it accepts what is known to be right and to be wrong), whether it
    meets the registered rule, and its verdicts on the new questions against the checker's. ``expected``: the names
    of the calibration records the bank's known derivations call for (``calibration_names``): the rule can hold only
    when EVERY one of them exists (review 2026-11-13: a calibration cut short by a limit or by failures must not
    authorise anything) and there are at least the registered numbers of right and wrong derivations."""
    folder = env.path(BENCH, 'audit')
    rows = [units.read_json(path) for path in sorted(folder.glob('*.json'))] if folder.is_dir() else []
    if not rows:
        return None
    names = {path.stem for path in folder.glob('cal-*.json')}
    missing = sorted(set(expected) - names)
    known = [row for row in rows if row['kind'] == 'calibration']
    share = lambda part, whole: round(len(part) / len(whole), 4) if whole else None
    calibration = {}
    for truth in ('right', 'wrong'):
        mine = [row for row in known if row['truth'] == truth]
        runs = [run for row in mine for run in row['runs']]
        calibration[truth] = {
            'derivations': len(mine), 'status': report.tally(row['status'] for row in mine),
            'accepted_share': share([row for row in mine if row['status'] == 'accepted'], mine),
            'single_run_accept_share': share([run for run in runs if run['verdict'] == 'accept'], runs),
            'void_runs': sum(run['verdict'] == 'void' for run in runs)}
    calibration['wrong']['accepted_by_label'] = {
        label: '%d of %d' % (sum(r['status'] == 'accepted' for r in known if r['label'] == label),
                             sum(1 for r in known if r['label'] == label))
        for label in sorted({row['label'] for row in known if row['truth'] == 'wrong'})}
    right, wrong = calibration['right']['accepted_share'], calibration['wrong']['accepted_share']
    calibration['expected'], calibration['missing'] = len(expected), len(missing)
    usable = (not missing and right is not None and wrong is not None
              and calibration['right']['derivations'] >= AUDIT_RULE['right_min']
              and calibration['wrong']['derivations'] >= AUDIT_RULE['wrong_min']
              and right >= AUDIT_RULE['right_accepted_min'] and wrong <= AUDIT_RULE['wrong_accepted_max'])
    questions = {}
    for row in rows:
        if row['kind'] != 'new_question':
            continue
        check = checks.get(row['id'], {}).get('status', 'unchecked')
        cell = questions.setdefault(row['arm'], {})
        key = 'checker %s, audit %s' % (check, row['status'])
        cell[key] = cell.get(key, 0) + 1
    return {'runs_per_derivation': AUDIT_RUNS, 'rule': AUDIT_RULE, 'calibration': calibration,
            'meets_the_rule': usable if known else None, 'new_questions': questions}


def question_statuses(checks, audits, usable):
    """{question id: final status}: ``verified`` (the checker solved it twice), ``audited`` (it did not, the audit
    accepted the derivation in every run AND the audit met its calibration rule: a hard question with a trusted
    answer), else ``unverified``."""
    out = {}
    for name, row in checks.items():
        if row.get('kind') != 'new_question':
            continue
        if row['status'] == 'verified':
            out[name] = 'verified'
        else:
            out[name] = 'audited' if usable and audits.get(name, {}).get('status') == 'accepted' else 'unverified'
    return out


# ---- contrast: a second solver configuration on real and made items (the instrument check, design section 6.3) ------
CONFIG_NAME = re.compile(r'[a-z][a-z0-9]{0,11}')
CONTRAST_PARENT_RUNS = 2          # as the checker's runs on a real parent
CONTRAST_KIND = 'contrast'        # configuration records ``contrast-<config>.json``, parity ``contrast-parity.json``
BOOTSTRAP_DRAWS = 2000


def _checks(env):
    folder, out = env.path(BENCH, 'check'), {}
    for path in sorted(folder.glob('*.json')) if folder.is_dir() else []:
        row = units.read_json(path)
        out[row['id']] = row
    return out


def _audits(env):
    folder = env.path(BENCH, 'audit')
    return {row['id']: row for row in (units.read_json(path) for path in sorted(folder.glob('*.json')))
            if row['kind'] == 'new_question'} if folder.is_dir() else {}


def judged_items(env, items):
    """[(id, kind, parent, arm, public, gold)] of what a configuration is judged on: every real parent, the made twins
    the checker CONFIRMED (and whose parent keeps its twins), and the new questions with the final status verified
    or audited. An item whose answer nothing vouches for is not a measuring item."""
    checks = _checks(env)
    summary = audit_report(env, checks, calibration_names(env, items))
    final = question_statuses(checks, _audits(env), bool(summary and summary['meets_the_rule']))
    twin_final = twin_statuses([row for row in checks.values() if row['kind'] == 'number_twin'])
    out = [(item['task_id'], 'parent', item['task_id'], None, item['public'], item['private']['answer']) for item in items]
    for twin, record in twins_of(env):
        if twin_final.get(twin['task_id']) == 'confirmed':
            out.append((twin['task_id'], 'number_twin', record['parent'], None, twin['public'], twin['private']['answer']))
    for made, record in made_items(env, 'new_question'):
        if final.get(made['task_id']) in ('verified', 'audited'):
            out.append((made['task_id'], 'new_question', record['parent'], record['arm'], made['public'],
                        made['private']['answer']))
    return out


def stage_contrasts(env, tools, items, cards, *, runs=None, side=None, sides=None, solver='G', origins=None):
    """The solver with OTHER system cards (``cards``: {configuration name: card text}) on the judged items. Without
    ``runs``: two runs per real parent, one per made item (the instrument check). With ``runs`` = R: R runs per
    item, as a gate arm has (re-judging a card). ``side`` (with ``sides``): only items whose parent is on that side.
    ``solver``: the label of the solver client's chain (a configuration keeps to one). The tasks are ordered item
    by item, the configurations of one item in a seeded order of their own (as a gate unit orders its arms): a base
    and its candidates meet an item in the same minutes, so a drift of the service over a stage is not read as a
    difference between them. Every configuration is registered before any call (``rejudge.register``: its card,
    solver, run count, side, origin (``origins``: a re-judging's source in the run, from ``rejudge.require_parity``)
    and the ordered item ids, which must be the judged items of now: a name that exists with another identity, or
    whose judged items changed, stops the stage before it writes or pays for anything). Records ``contrast-<config>/<id>.json``; nothing here changes a
    status."""
    assert cards and all(CONFIG_NAME.fullmatch(config) and config != 'c' for config in cards), \
        'Configuration names of lower-case letters and digits, not "c"'
    assert runs is None or (type(runs) is int and 1 <= runs <= 5), 'One to five runs per item'
    assert side is None or (side in SIDES and sides is not None), 'A side needs the table of sides'
    shas = {config: text_sha256(card) for config, card in cards.items()}
    names = sorted(cards)
    entries = [entry for entry in judged_items(env, items) if side is None or sides[entry[2]] == side]
    wanted = {entry[0]: runs or (CONTRAST_PARENT_RUNS if entry[1] == 'parent' else 1) for entry in entries}
    for config in names:        # before any call: one card, one solver, one run count, one item list per name
        rejudge.register(env, BENCH, CONTRAST_KIND, config,
                         {'card_sha256': shas[config], 'solver': solver, 'runs': runs, 'side': side,
                          'origin': origins[config] if origins else None},
                         [entry[0] for entry in entries], runs_of=wanted.get, exact=True)
    tasks = [(entry, config) for entry in entries
             for config in random.Random('%d:contrast-order:%s' % (SEED, entry[0])).sample(names, len(names))]

    def work(task):
        (name, kind, parent, arm, public, gold), config = task
        wanted = runs or (CONTRAST_PARENT_RUNS if kind == 'parent' else 1)
        unit, shaped = '%s/contrast-%s' % (BENCH, config), {**tools, 'card': cards[config]}

        def compute():
            made = [solve_once(env, shaped, public, gold, '%s-r%d' % (safe_id(name), run), unit=unit)
                    for run in range(1, wanted + 1)]
            if any(run['verdict'] == 'unknown' for run in made):
                raise RuntimeError('unknown solver run')
            return {'id': name, 'kind': kind, 'parent': parent, 'arm': arm, 'config': config,
                    'card_sha256': shas[config], 'solver': solver, 'runs': made,
                    'passes': sum(run['verdict'] == 'pass' for run in made)}
        try:
            row = env.once((BENCH, 'contrast-' + config, safe_id(name) + '.json'), compute)
            assert row['card_sha256'] == shas[config], 'The configuration %s was run with another card' % config
            assert row.get('solver', 'G') == solver, 'The configuration %s was run with another solver' % config
            assert len(row['runs']) == wanted, 'The configuration %s was run with another number of runs' % config
            return config, '%s: %d of %d' % (kind, row['passes'], len(row['runs']))
        except units.Stop:
            raise
        except RuntimeError:
            return config, 'unknown'
    done = env.fan(tasks, work, label='contrast ' + ','.join(names))
    return {'configurations': shas, 'solver': solver, 'runs': runs, 'side': side,
            'results': {config: report.tally(result for name, result in done if name == config) for config in names}}


def stage_contrast(env, tools, items, config, card, *, runs=None, side=None, sides=None, solver='G'):
    """One configuration (``config``: its name, ``card``: its text): ``stage_contrasts`` with a single card."""
    made = stage_contrasts(env, tools, items, {config: card}, runs=runs, side=side, sides=sides, solver=solver)
    return {'config': config, 'card_sha256': made['configurations'][config], 'solver': solver, 'runs': runs,
            'side': side, 'results': made['results'][config]}


def _all_runs(env, config):
    """{id: [run passed, ...]} of a contrast configuration."""
    folder = env.path(BENCH, 'contrast-' + config)
    rows = [units.read_json(path) for path in sorted(folder.glob('*.json'))] if folder.is_dir() else []
    return {row['id']: [run['verdict'] == 'pass' for run in row['runs']] for row in rows}


def gate_statistics(base_runs, cand_runs, ids):
    """The chain's own gate statistics and card decision (``typed.gatestats``: tau = max(3 points, 2 x the standard
    error from the baseline's repeats), accepted when the gain reaches tau and more items got better than worse) of
    a candidate configuration against a base on ``ids``, both run R >= 2 times per item; None when the run counts
    differ or R < 2. The rule treats items as independent: items made from one document are not, so the report
    gives a parent-resampled interval beside it."""
    from .. import TAU_MIN_POINTS, TAU_SE_MULTIPLIER, gatestats
    counts = {len(base_runs[name]) for name in ids} | {len(cand_runs[name]) for name in ids}
    if not ids or len(counts) != 1 or min(counts) < 2:
        return None
    arm = lambda runs: {'sums': {name: sum(runs[name]) for name in ids},
                        'squares': {name: sum(runs[name]) for name in ids}, 'unknown': 0}
    stats = gatestats.repeat_statistics(arm(base_runs), arm(cand_runs), items=list(ids), repeats=counts.pop(),
                                        minimum_points=TAU_MIN_POINTS, multiplier=TAU_SE_MULTIPLIER)
    decision = gatestats.card_decision(stats)
    return {key: decision[key] for key in ('n', 'repeats', 'gain_points', 'se_points', 'tau_points', 'better', 'worse',
                                           'tied', 'reaches', 'no_regress', 'accepted', 'reason')}


def _first_runs(env, config):
    """{id: (kind, parent, arm, first run passed)} of a configuration; 'c' is the checker itself."""
    if config == 'c':
        records = {row['id']: row for row in _checks(env).values()}
        arms = {made['task_id']: record['arm'] for made, record in made_items(env, 'new_question')}
        return {name: (row['kind'], row.get('parent', name), arms.get(name), row['runs'][0]['verdict'] == 'pass')
                for name, row in records.items()}
    folder = env.path(BENCH, 'contrast-' + config)
    rows = [units.read_json(path) for path in sorted(folder.glob('*.json'))] if folder.is_dir() else []
    return {row['id']: (row['kind'], row['parent'], row['arm'], row['runs'][0]['verdict'] == 'pass') for row in rows}


def _solver_of(env, config):
    """The solver chain a configuration ran with ('G' for the checker itself)."""
    folder = env.path(BENCH, 'contrast-' + config)
    rows = sorted(folder.glob('*.json')) if config != 'c' and folder.is_dir() else []
    return units.read_json(rows[0]).get('solver', 'G') if rows else 'G'


def _gain(pairs):
    """Candidate minus base in points over (base passed, candidate passed) pairs; None without pairs."""
    return 100.0 * sum(int(cand) - int(base) for base, cand in pairs) / len(pairs) if pairs else None


def contrast_report(env, base, cand, sides, items=None):
    """Candidate configuration against base on FIRST runs, item by item: per group the pass rates, the gain in
    points, better / worse counts and a 95 % interval from resampling PARENTS (a parent and everything made from it
    move together: the made items of one document are not independent). ``instrument``: the gain on made items
    minus the gain on real items, with its interval -- near zero when made items measure what real items measure."""
    first, second = _first_runs(env, base), _first_runs(env, cand)
    solvers = {config: _solver_of(env, config) for config in (base, cand)}
    rows = [(name, first[name][0], first[name][1], first[name][2], first[name][3], second[name][3])
            for name in sorted(set(first) & set(second))]
    groups = {'real': lambda r: r[1] == 'parent',
              'real, judging side': lambda r: r[1] == 'parent' and sides.get(r[2]) == SIDES[1],
              'made': lambda r: r[1] != 'parent',
              'made, judging side': lambda r: r[1] != 'parent' and sides.get(r[2]) == SIDES[1],
              'number twins': lambda r: r[1] == 'number_twin'}
    for arm in ARMS:
        groups['new questions, ' + arm] = lambda r, arm=arm: r[1] == 'new_question' and r[3] == arm
    parents = sorted({row[2] for row in rows})
    by_parent = {parent: [row for row in rows if row[2] == parent] for parent in parents}
    rng = random.Random('%d:contrast:%s:%s' % (SEED, base, cand))
    draws = [[rng.choice(parents) for _ in parents] for _ in range(BOOTSTRAP_DRAWS)] if parents else []

    def interval(value_of):
        values = sorted(v for v in (value_of([row for parent in draw for row in by_parent[parent]]) for draw in draws)
                        if v is not None)
        if len(values) < 40:
            return None
        return [round(values[int(0.025 * (len(values) - 1))], 2), round(values[int(0.975 * (len(values) - 1))], 2)]

    out = {'base': base, 'candidate': cand, 'solver': solvers, 'same_solver': len(set(solvers.values())) == 1,
           'items': len(rows), 'parents': len(parents), 'groups': {}}
    for title, keep in groups.items():
        mine = [row for row in rows if keep(row)]
        if not mine:
            continue
        pairs = [(row[4], row[5]) for row in mine]
        out['groups'][title] = {
            'items': len(mine), 'parents': len({row[2] for row in mine}),
            'base_pass_pct': round(100.0 * sum(b for b, _ in pairs) / len(pairs), 2),
            'candidate_pass_pct': round(100.0 * sum(c for _, c in pairs) / len(pairs), 2),
            'gain_points': round(_gain(pairs), 2), 'better': sum(c and not b for b, c in pairs),
            'worse': sum(b and not c for b, c in pairs),
            'gain_interval_95': interval(lambda sample, keep=keep: _gain([(r[4], r[5]) for r in sample if keep(r)]))}

    def difference(sample):
        real = _gain([(r[4], r[5]) for r in sample if r[1] == 'parent'])
        made = _gain([(r[4], r[5]) for r in sample if r[1] != 'parent'])
        return None if real is None or made is None else made - real
    whole = difference(rows)
    out['instrument'] = {'made_gain_minus_real_gain_points': None if whole is None else round(whole, 2),
                         'interval_95': interval(difference),
                         'note': 'first runs only; intervals resample parents (%d draws, seeded)' % BOOTSTRAP_DRAWS}
    if base != 'c':                       # two contrast configurations with R runs per item: the chain's gate rule
        out['gate_rule'] = _gate_rule(env, base, cand, rows, groups, sides, interval, items)
    return out


def _gate_rule(env, base, cand, rows, groups, sides, interval, items):
    """The chain's gate rule of ``cand`` against ``base`` on the judging-side items, real, made and both. Decided
    only for the run's base and a candidate of a card round of the same learning step and request construction
    (``rejudge.comparable``), registered on the same items, solver and run count R >= 2, whose registered items are
    the judged items of NOW (``items``: the pool; an item that lost its status since must not stay in the judged
    population), each holding a record for every registered item (an item whose run failed for an infrastructure
    reason must not drop out of it): otherwise ``{'undecided': reason}``."""
    first = rejudge.registered(env, BENCH, CONTRAST_KIND, base)
    second = rejudge.registered(env, BENCH, CONTRAST_KIND, cand)
    refusal = rejudge.comparable(first, second)
    if refusal:
        return {'undecided': refusal}
    if items is None:
        return {'undecided': 'the judged items of now were not given'}
    current = [entry[0] for entry in judged_items(env, items) if first['side'] is None or sides[entry[2]] == first['side']]
    if current != first['items'] or first['side'] != second['side']:
        return {'undecided': 'the judged items changed since the configurations were registered'}
    rows_b = rejudge.complete_rows(first, _contrast_rows(env, base))
    rows_k = rejudge.complete_rows(second, _contrast_rows(env, cand))
    if rows_b is None or rows_k is None:
        return {'undecided': 'records are missing: %d and %d of %d items' % (
            len(set(first['items']) & set(_contrast_rows(env, base))),
            len(set(first['items']) & set(_contrast_rows(env, cand))), len(first['items']))}
    runs_b = {row['id']: [run['verdict'] == 'pass' for run in row['runs']] for row in rows_b}
    runs_k = {row['id']: [run['verdict'] == 'pass' for run in row['runs']] for row in rows_k}
    kinds = {row[0]: row for row in rows}
    gate = {'origin': {'step_dir': first['origin']['step_dir'], 'base_unit': first['origin']['unit'],
                       'candidate_unit': second['origin']['unit']}}
    for title, keep in (('real, judging side', groups['real, judging side']),
                        ('made, judging side', groups['made, judging side']),
                        ('real and made, judging side', lambda r: sides.get(r[2]) == SIDES[1])):
        ids = [name for name in first['items'] if name in kinds and keep(kinds[name])]
        stats = gate_statistics(runs_b, runs_k, ids)
        if stats is None:
            continue
        mean = lambda sample, ids=set(ids): (
            100.0 * sum(sum(runs_k[r[0]]) - sum(runs_b[r[0]]) for r in sample if r[0] in ids)
            / sum(len(runs_b[r[0]]) for r in sample if r[0] in ids)) if any(r[0] in ids for r in sample) else None
        gate[title] = {**stats, 'parents': len({kinds[name][2] for name in ids}),
                       'gain_interval_95_resampling_parents': interval(mean)}
    return gate


def _contrast_rows(env, config):
    folder = env.path(BENCH, 'contrast-' + config)
    return {row['id']: row for row in (units.read_json(path) for path in sorted(folder.glob('*.json')))} \
        if folder.is_dir() else {}


# ---- parity of contrast configurations with a run (no call; BANK-PILOT B26 step 1) --------------------------------------
def first_request(tools, public, card):
    """The first request the checker's solver would send for a question under a system card, with NO call."""
    call, seen = rejudge.probe()
    tools['solve'](BENCH, public, card, call, runtime=tools['runtime'])
    return seen[0] if seen else None


def stage_parity(env, tools, gate_items, cards, step_dir, identity, *, base, base_unit):
    """Every configuration of ``cards`` ({name: card TEXT as the run stored it}) against its source in the run's
    learning step ``step_dir`` on the run's gate items (the real parents of the judging side): the configuration
    ``base`` against the cells of ``base_unit`` (the unit the step's card gate used as its baseline: its base or
    incumbent arm), every other one against the card round whose writer wrote exactly its text. The system card of
    a configuration is its text mounted on the hand card (``tools['system_card']``).
    ``officeqa/contrast-parity.json`` (``rejudge.check_parity``). No call."""
    assert base in cards, 'The base configuration is one of the cards'
    configurations = {}
    for config, text in cards.items():
        card = tools['system_card'](text)
        source = rejudge.base_source(base_unit) if config == base else rejudge.candidate_source(step_dir, text)
        configurations[config] = (text_sha256(card), source,
                                  lambda item, card=card: first_request(tools, item['public'], card))
    return rejudge.check_parity(env, BENCH, CONTRAST_KIND, step_dir, identity, gate_items, configurations)


def stage_rejudge(env, tools, items, cards, *, runs, side, sides, solver='G', step_dir, identity):
    """Re-judging (B26): ``stage_contrasts`` of card texts mounted on the hand card, allowed only with a passing
    parity record of this learning step and request identity that covers exactly these system cards; every
    configuration is registered with its origin in the run."""
    assert type(runs) is int and runs >= 2 and side == SIDES[1], 'A re-judging runs R >= 2 times on the judging side'
    system = {config: tools['system_card'](text) for config, text in cards.items()}
    origins = rejudge.require_parity(env, BENCH, CONTRAST_KIND, {config: text_sha256(card) for config, card in system.items()},
                                     step_dir, identity)
    return stage_contrasts(env, tools, items, system, runs=runs, side=side, sides=sides, solver=solver, origins=origins)


# ---- report --------------------------------------------------------------------------------------------------------
def new_question_report(env, items, checks, real, statuses=None):
    """The arms of new questions side by side: yield of the fixed checks, the checker's verdicts, the final status
    with the audit (``question_statuses``), what the questions compute, how many carry coded mistakes, and their
    distance from the real questions. An arm nothing was asked in is left out."""
    statuses = statuses or {}
    folder, out = env.path(BENCH, 'newq'), {}
    asked = [units.read_json(path) for path in sorted(folder.glob('*.json'))] if folder.is_dir() else []
    pairs = made_items(env, 'new_question')
    for arm in ARMS:
        rows = [row for row in asked if row['arm'] == arm]
        mine = [(made, record) for made, record in pairs if record['arm'] == arm]
        checked = [checks[made['task_id']] for made, _ in mine if made['task_id'] in checks]
        verified = {row['id'] for row in checked if row['status'] == 'verified'}
        features = [oqa.features(made['public']['question'], made['private']['answer'], record['trace'],
                                 made['public']['context']) for made, record in mine]
        first = [row['runs'][0]['verdict'] == 'pass' for row in checked]
        if not rows and not mine:
            continue
        final = [statuses.get(made['task_id'], 'unchecked') for made, _ in mine]
        out[arm] = {
            'final_status': report.tally(final),
            'final_status_by_side': {side: report.tally(status for status, (_, record) in zip(final, mine)
                                                        if record['side'] == side) for side in SIDES},
            'targets': report.tally(record.get('targets') for _, record in mine if record.get('targets')),
            'wrong_replies_matching_a_coded_mistake': sum(
                run.get('label') in prompts.MISTAKE_LABELS for row in checked for run in row['runs']),
            'parents_asked': len(rows), 'entries_written': sum(row['entries'] for row in rows),
            'kept_by_fixed_checks': len(mine), 'drop_reasons': report.tally(r for row in rows for r in row['drops']),
            'checked': len(checked), 'verified': len(verified),
            'verified_parents': len({row['parent'] for row in checked if row['status'] == 'verified'}),
            'first_run_pass_pct': 100.0 * sum(first) / len(first) if first else None,
            'with_coded_mistakes': sum(bool(record['mistakes']) for _, record in mine),
            'coded_mistakes': report.tally(label for _, record in mine for label in record['mistakes']),
            'operations': report.tally('+'.join(row['operations']) or 'read' for row in features),
            'wrong_reply_labels': report.tally(run['label'] for row in checked for run in row['runs'] if run.get('label')),
            'fidelity': report.compare(real, features, categorical=['answer_kind', 'rounding_stated', 'answer_parts'],
                                       numeric=['question_chars', 'values'])}
    return out



def build_report(env, items, sides, shared_pages):
    """The pilot's numbers for OfficeQA number twins, from the records alone (no model, no file outside the root)."""
    traces = {item['task_id']: env.read(BENCH, 'trace', safe_id(item['task_id']) + '.json')
              for item in items if env.exists(BENCH, 'trace', safe_id(item['task_id']) + '.json')}
    anchored = sorted(parent for parent, record in traces.items() if record['status'] == 'anchored')
    twins = twins_of(env)
    checks = {}
    folder = env.path(BENCH, 'check')
    for path in sorted(folder.glob('*.json')) if folder.is_dir() else []:
        row = units.read_json(path)
        checks[row['id']] = row
    parent_rows = [checks[item['task_id']] for item in items if item['task_id'] in checks]
    twin_rows = [checks[twin['task_id']] for twin, _ in twins if twin['task_id'] in checks]
    status_of = twin_statuses(twin_rows)
    qualified = [row for row in twin_rows if status_of[row['id']] == 'confirmed']
    diagnostic = [row for row in twin_rows if status_of[row['id']] == 'unconfirmed']
    rate = lambda rows: (100.0 * sum(r['runs'][0]['verdict'] == 'pass' for r in rows) / len(rows)) if rows else None
    by_parent = {}
    for row in twin_rows:
        by_parent.setdefault(row['parent_passes'], []).append(row)
    labels = [run['label'] for row in parent_rows + twin_rows for run in row['runs'] if run.get('label')]
    real = [oqa.features(i['public']['question'], i['private']['answer'], traces.get(i['task_id'], {}).get('trace'),
                         i['public']['context']) for i in items]
    made = [oqa.features(t['public']['question'], t['private']['answer'], traces[r['parent']]['trace'],
                         t['public']['context']) for t, r in twins]
    side_of = lambda rows: report.tally(sides[row['parent']] for row in rows)
    audited = audit_report(env, checks, calibration_names(env, items))
    statuses = question_statuses(checks, _audits(env), bool(audited and audited['meets_the_rule']))
    return {
        'bench': BENCH, 'parents': len(items),
        'trace': {'status': report.tally(record['status'] for record in traces.values()),
                  'drop_reasons': report.tally(record['reason'] for record in traces.values()
                                               if record['status'] in ('dropped', 'no_reply')),
                  'anchored': len(anchored),
                  'anchored_on_second_attempt': sum(len(traces[p]['attempts']) > 1 for p in anchored),
                  'anchored_by_side': report.tally(sides[p] for p in anchored),
                  'parents_with_coded_mistakes': sum(bool(traces[p]['mistakes']) for p in anchored),
                  'coded_mistakes': report.tally(m['label'] for p in anchored for m in traces[p]['mistakes'])},
        'twins': {'made': len(twins), 'parents_with_twins': len({r['parent'] for _, r in twins}),
                  'checked': len(twin_rows), 'status': report.tally(status_of[row['id']] for row in twin_rows),
                  'qualified': len(qualified), 'qualified_by_side': side_of(qualified),
                  'diagnostic_only': len(diagnostic), 'diagnostic_only_by_side': side_of(diagnostic),
                  'qualified_parents': len({row['parent'] for row in qualified})},
        'checker': {'parents_checked': len(parent_rows),
                    'parent_passes': report.tally('%d of %d' % (row['passes'], CHECK_RUNS) for row in parent_rows),
                    'first_run_pass_pct': {'parents': rate(parent_rows), 'twins': rate(twin_rows),
                                           'twins_of_parents_solved_every_time': rate(by_parent.get(CHECK_RUNS, [])),
                                           'twins_of_parents_never_solved': rate(by_parent.get(0, []))},
                    'wrong_reply_labels': report.tally(labels)},
        'fidelity': report.compare(real, made, categorical=['answer_kind', 'rounding_stated', 'answer_parts',
                                                            'negative', 'operations', 'pages'],
                                   numeric=['question_chars', 'context_chars', 'values']),
        'new_questions': new_question_report(env, items, checks, real, statuses),
        'diagnosis': diagnosis_report(env),
        'audit': audited,
        'shared_pages': {'parents_sharing_a_page_with_a_page_reference_outside_the_pool': len(shared_pages),
                         'note': 'page references only (ids and source pages of the id manifest); such parents get '
                                 'number twins, and no NEW question is written on them'},
        'ledger': {key: env.ledger.state[key] for key in ('cap', 'charged', 'reported', 'sends', 'stopped',
                                                          'stop_reason')},
        'sides': dict(zip(SIDES, ('parents of the learning slice: made items are shown to writers',
                                  'parents of the gate slice: made items are kept for judging'))),
    }
