"""typed-v3 B7 (docs/handoff/typed-v3/CHAIN-DECISIONS.md, 2026-11-15): a provider's content-filter refusal of a solver
request -- GLM-5.3 answers HTTP 400 with error code 1301, 0 tokens, and the same again for the same request -- is a
model-side outcome, as ``finish_sensitive`` is (addendum O1: final, scored 0, never re-run, no pause). It is read from
a send record's ``receipt_rest``, which the resume replay 'on' (the typed-v3 preset) keeps; a record without it
(typed-v2's, 'off') and every other failure keep typed-v2's rule (an infrastructure unknown: the arm is undecidable,
the chain pauses ``gate_cells_unknown``). Role calls are unchanged. Also B7: one optional lowercase letter after the
date names a further run root of the same day. Fakes only (no network, no Docker, no /data, nothing paid).

B7b (Codex's review of f1950b9): under the resume replay 'on' a saved refusal answers its occurrence in a solver cell
wherever it stands in the calls file, also in a cell re-run after another failure (``units.ReplayRule``'s
``final_refusals``, set by ``ReplayingRecorder`` only; the role-call replay and the default rule are unchanged); and a
refused item's text reaches no role sample that shows text without reading an outcome -- the analyst's learn rows
(``items.plan.learn_rows``), the engineer's hook view (``chain._Run.hook_item``), the describer's examples
(``chain._Run.examples_of``) and a repair request's coverage block (``writers.coverage_report``'s ``exclude``) -- while
every count keeps it. The refused set is read from the step's records (``chain._Run.refused_ids``), so a resumed step
rebuilds the same role requests even where it does not re-enter a unit. Harnesses: the chain fakes of
``tests/test_typed_chain.py``, P1's (``tests/test_typed3_program_learning.py``), P2b's
(``tests/test_typed3_item_stage.py``), P3r's run-mode reads (``tests/test_typed3_reads.py``) and the kill helpers of
``tests/test_typed3_resume_replay.py``."""
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from skillopt.execskill.typed import chain, prepare, reads, smoke, units, writers
from skillopt.execskill.typed.items import plan
from tests import test_typed3_item_stage as stage
from tests import test_typed3_program_learning as learning
from tests import test_typed3_reads as reading
from tests import test_typed3_resume_replay as replay
from tests import test_typed_chain as chain_v2
from tests.test_typed3_reads import qualified  # noqa: F401 -- the faked sheet qualification of run-mode reads

NEUTRAL = Path('/tmp/typed3-filter-neutral').resolve()  # resolved: route B's safe_path refuses a symlink in any parent
REST = {'error_code': '1301', 'seconds': 0.9, 'status': 400}
FILTERED = {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'http_400', **REST}
DELIVERED = {'ok': True, 'response': 'reply', 'finish_reason': 'stop', 'error_type': None,
             'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}
ITEM = 'searchqa-g1'  # the gate item whose every solver request the fake provider refuses


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='filter-', dir=NEUTRAL))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def record(receipt, rest=None):
    """A send record as ``units.CallRecorder`` writes it (``receipt_rest`` only when given)."""
    found = {'request_sha256': 'r', 'receipt': {key: receipt.get(key) for key in units.RECEIPT_KEYS}}
    if rest is not None:
        found['receipt_rest'] = rest
    return found


def test_the_refusal_rule_and_what_stays_an_infrastructure_unknown():
    assert units.PROVIDER_FILTER_REFUSALS == frozenset({('http_400', '1301')})
    refused = record(FILTERED, REST)
    assert units.provider_filter_refusal(refused) and not units.infrastructure_unknown_of([refused])
    assert units.provider_filter_refusal(record(FILTERED, {**REST, 'error_code': 1301}))  # an integer code too
    # typed-v2's records keep no receipt_rest: the same failure stays an infrastructure unknown
    assert not units.provider_filter_refusal(record(FILTERED)) and units.infrastructure_unknown_of([record(FILTERED)])
    for rest in ({**REST, 'error_code': '1302'}, {'seconds': 0.9, 'status': 400}, {**REST, 'error_code': None}, {}):
        assert not units.provider_filter_refusal(record(FILTERED, rest))
        assert units.infrastructure_unknown_of([record(FILTERED, rest)])
    for other in ('http_500', 'http_429', 'transport', None):
        assert units.infrastructure_unknown_of([record({**FILTERED, 'error_type': other}, REST)])
    # a delivered receipt is no refusal, whatever its rest says
    assert not units.provider_filter_refusal(record(DELIVERED, REST))
    assert not units.infrastructure_unknown_of([record(DELIVERED, REST)])
    # a refusal never hides another failure of the same cell
    assert units.infrastructure_unknown_of([refused, {'request_sha256': 'x', 'receipt': None, 'exception': 'ConnectTimeout'}])
    assert units.infrastructure_unknown_of([refused, record({**FILTERED, 'error_type': 'transport'}, {})])
    assert not units.infrastructure_unknown_of([refused, record(DELIVERED, {})])


@pytest.mark.parametrize('keep', [True, False])
def test_a_recorder_classifies_the_refusal_from_what_it_keeps(tmp_path, keep):
    """A ``CallRecorder`` keeps ``receipt_rest`` when ``keep_rest`` (the resume replay 'on' sets it): then the refusal
    is model-side; without it the record holds no code and the refusal stays an infrastructure unknown (typed-v2)."""
    ledger = units.Ledger(tmp_path / 'ledger.json', 10 ** 7)
    rec = units.CallRecorder(lambda s, u: dict(FILTERED), ledger, max_tokens=500, tag='t', unit='u',
                             out_path=tmp_path / 'calls' / 't.json')
    rec.keep_rest = keep
    assert rec('sys', 'user')['error_code'] == '1301'  # the shell sees the whole receipt either way
    saved = json.loads((tmp_path / 'calls' / 't.json').read_text())
    assert ('receipt_rest' in saved[0]) is keep
    assert rec.infrastructure_unknown() is (not keep) and rec.tokens() == 0
    assert not ledger.state['pending']  # settled once, as any failed receipt


def test_a_replaying_recorder_classifies_a_replayed_refusal_as_its_recorder_does(tmp_path):
    """Under 'on' a cell run again after a kill answers a saved refusal from its calls file (``ReplayingRecorder``,
    the failure the earlier flow went past): its path holds the saved record with its rest, so the replayed refusal is
    model-side too, and nothing is sent for it."""
    ledger = units.Ledger(tmp_path / 'ledger.json', 10 ** 7)
    sent = []

    def client(system, user):
        sent.append(user)
        return dict(FILTERED) if user == 'first' else dict(DELIVERED)
    first = units.replaying(units.CallRecorder(client, ledger, max_tokens=500, tag='t', unit='u',
                                               out_path=tmp_path / 'calls' / 't.json'))
    first('sys', 'first')
    first('sys', 'second')
    earlier = json.loads((tmp_path / 'calls' / 't.json').read_text())
    assert [s['receipt']['ok'] for s in earlier] == [False, True] and earlier[0]['receipt_rest']['error_code'] == '1301'
    again = units.ReplayingRecorder(units.CallRecorder(client, ledger, max_tokens=500, tag='t', unit='u',
                                                       out_path=tmp_path / 'calls' / 't2.json'), earlier)
    assert again('sys', 'first')['error_code'] == '1301' and again('sys', 'second')['ok']
    assert sent == ['first', 'second'] and again.replayed and not again.infrastructure_unknown()


def filtering_solver(system, user):
    """The fake provider: every solver request of ``ITEM`` is refused by its content filter, every other is answered."""
    if 'item %s?' % ITEM in user:
        return dict(FILTERED)
    return 'The answer is 42.'


def cells_of(root, unit, item_id):
    return [json.loads(p.read_text()) for p in Path(root, 'G', *unit.split('/'), 'cells').glob('*.json')
            if json.loads(p.read_text())['item_id'] == item_id]


def test_a_gate_item_the_provider_refuses_is_a_final_zero_in_every_arm_and_the_chain_goes_on(tmp_path):
    """Under 'on': every run of the refused item, in the noise arm and in the card round, is a final model-side
    unknown (scored 0, counted in unknown_final, never re-run, no rerun/ directory); the chain completes; the calls
    files keep the code. The same script under 'off' pauses ``gate_cells_unknown`` at s1/noise, as typed-v2 did."""
    services, modules, script = chain_v2.build(tmp_path / 'on', order=('searchqa',),
                                               scripted={'replies': {'solver': filtering_solver}})
    services.manifest['resume_replay'] = 'on'
    state = chain.run(tmp_path / 'on', 'G', services=services, sleep=lambda s: None)
    assert state['complete'] and state['paused'] is None, state['paused']
    root = tmp_path / 'on'
    noise = json.loads((root / 'G' / 's1' / 'noise' / 'noise.json').read_text())
    assert noise['unknown_final'] == 3 and noise['reruns'] == 0  # the item's three repeats B#1..3
    assert dict(noise['per_item'])[ITEM] == 0
    for unit in ('s1/noise', 's1/card-r1'):
        found = cells_of(root, unit, ITEM)
        assert len(found) == 3
        for cell in found:
            assert cell['correct'] is None and cell['infrastructure_unknown'] is False
            assert cell['sends'][0]['receipt']['error_type'] == 'http_400'
            assert cell['sends'][0]['receipt_rest']['error_code'] == '1301'
        assert not Path(root, 'G', *unit.split('/'), 'rerun').exists()
    card = json.loads((root / 'G' / 's1' / 'decisions.json').read_text())['cards'][0]
    assert card['unknown_final']['candidate'] == 3 and card['excluded_unknown'] == 0
    assert [row for row in card['per_item'] if row[0] == ITEM] == [[ITEM, 0, 0]]
    ledger = json.loads((root / 'G' / 'ledger.json').read_text())
    assert not ledger['stopped'] and ledger['infra_streak'] == 0

    services, modules, script = chain_v2.build(tmp_path / 'off', order=('searchqa',),
                                               scripted={'replies': {'solver': filtering_solver}})
    state = chain.run(tmp_path / 'off', 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'gate_cells_unknown' and state['paused']['unit'] == 's1/noise'


def test_a_further_root_of_the_same_day_takes_one_letter_after_the_date():
    for name in ('execskill-20261115b-typed-v3', 'execskill-20261115b-typed-v3-smoke', 'execskill-20261115-typed-v3'):
        assert prepare.ROOT_NAME.match(name)
    for name in ('execskill-20261115bb-typed-v3', 'execskill-20261115B-typed-v3', 'execskill-20261115-b-typed-v3',
                 'execskill-2026111b-typed-v3', 'execskill-20261115b-typed-v2', 'execskill-20261115b-typed-v3-smokes'):
        assert not prepare.ROOT_NAME.match(name)
    assert prepare.check_root('/data/execskill-20261115b-typed-v3').name == 'execskill-20261115b-typed-v3'
    assert prepare.check_root('/data/execskill-20261115b-typed-v3-smoke', smoke=True).name.endswith('-smoke')
    with pytest.raises(ValueError, match='smoke'):
        prepare.check_root('/data/execskill-20261115b-typed-v3-smoke')


# ==== B7b (1): a saved refusal is final under the resume replay ======================================================
TIMEOUT = {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'timeout'}
EXTRA = ('extra system', 'extra request')  # a request a cell's flow sends before its solve request
REFUSED = ('solver system', 'Who wrote the article mentioned in item %s?' % ITEM)


def numbered(user, receipt, rest=None, *, occurrence=1, system='solver system'):
    """A numbered send record as a replaying ``CallRecorder`` writes it (``receipt_rest`` only when given)."""
    return {**record(receipt, rest), 'request_sha256': units.sha256_text(system + '\x00' + user),
            'occurrence': occurrence}


def test_the_numbered_rule_without_final_refusals_is_unchanged_and_with_it_a_refusal_is_final():
    """``ReplayRule(numbered=True)`` keeps its rule unless ``final_refusals`` is set (only ``ReplayingRecorder`` sets it):
    a refusal at the end of the file is sent again, one the flow went past is replayed as a failure, a re-run
    (``failures`` False) replays no failure. With ``final_refusals`` a refusal answers its occurrence in all three
    cases; a delivered receipt of the occurrence still answers first; another code, a record without its rest
    (typed-v2's), a call that raised and a timeout stay what they were. The unnumbered rule takes no such option."""
    refusal, other = numbered(REFUSED[1], FILTERED, REST), numbered('another request', DELIVERED, {})
    sha = refusal['request_sha256']
    delivered, timeout = numbered(REFUSED[1], DELIVERED, {}), numbered(REFUSED[1], TIMEOUT, {})
    cases = [  # (calls file, failures, answer of occurrence 1 without final_refusals, with it)
        ([refusal], True, None, refusal),                      # where the earlier process stood (a kill)
        ([refusal], False, None, refusal),                     # a re-run after another failure
        ([refusal, other], True, refusal, refusal),            # a refusal the flow went past
        ([refusal, other], False, None, refusal),
        ([refusal, delivered], True, delivered, delivered),    # a delivered receipt answers first
        ([numbered(REFUSED[1], FILTERED, {**REST, 'error_code': '1302'})], True, None, None),
        ([numbered(REFUSED[1], FILTERED)], True, None, None),  # no rest kept: no refusal
        ([{**refusal, 'exception': 'Stop'}], True, None, None),
        ([timeout], True, None, None), ([timeout, other], False, None, None)]
    for sends, failures, plain, final in cases:
        assert units.ReplayRule(sends, failures=failures, numbered=True).answer(sha, 1) == plain, sends
        rule = units.ReplayRule(sends, failures=failures, numbered=True, final_refusals=True)
        assert rule.answer(sha, 1) == final and rule.answer(sha, 2) is None, sends
    with pytest.raises(ValueError, match='numbered'):
        units.ReplayRule([refusal], final_refusals=True)


@pytest.mark.parametrize('case', ['killed', 'rerun'])
def test_a_solver_cell_answers_its_saved_refusal_from_the_calls_file_on_resume_and_on_a_rerun(tmp_path, case):
    """The solver cells' replay (``units.replaying``). 'killed': the process died right after the cell's only send was
    refused -- the refusal is the calls file's last record, where the earlier process stood: the resumed cell is
    answered from the file -- nothing sent or charged, its path the saved record, a model-side outcome. 'rerun': the
    cell's flow sent EXTRA first, which timed out (the cell was an infrastructure unknown, its record archived for a
    re-run: ``failures`` False): the re-run sends EXTRA again and still answers the refusal from the file."""
    ledger, sent, failing = units.Ledger(tmp_path / 'ledger.json', 10 ** 7), [], {'extra': case == 'rerun'}

    def client(system, user):
        sent.append((system, user))
        if (system, user) == EXTRA:
            if failing['extra']:
                failing['extra'] = False
                return dict(TIMEOUT)
            return dict(DELIVERED)
        return dict(FILTERED)
    path = tmp_path / 's1' / 'noise' / 'calls' / 'cell.json'

    def recorder():
        return units.replaying(units.CallRecorder(client, ledger, max_tokens=500, tag='cell', unit='s1/noise',
                                                  out_path=path))
    first = recorder()
    if case == 'rerun':
        first(*EXTRA)
    first(*REFUSED)
    assert first.infrastructure_unknown() is (case == 'rerun')
    saved = json.loads(path.read_text())
    assert saved[-1]['receipt_rest']['error_code'] == '1301' and saved[-1]['occurrence'] == 1
    if case == 'rerun':  # the cell's record archived for a re-run, as mark_infrastructure_reruns leaves it
        units.write_json(tmp_path / 's1' / 'noise' / 'rerun' / 'cell-1.json', {'archived': True})
    before, sends = list(sent), ledger.state['sends']
    again = recorder()
    assert isinstance(again, units.ReplayingRecorder)
    if case == 'rerun':
        assert again(*EXTRA)['ok']  # a failure is sent again in a re-run ...
    found = again(*REFUSED)         # ... a refusal never is
    assert (found['ok'], found['error_type'], found['error_code']) == (False, 'http_400', '1301')
    assert sent == before + ([EXTRA] if case == 'rerun' else [])
    assert ledger.state['sends'] == sends + (case == 'rerun') and not ledger.state['pending']
    assert again.replayed == [units.sha256_text('\x00'.join(REFUSED))]
    assert again.path[-1] == saved[-1] and not again.infrastructure_unknown()
    assert again.tokens() == (120 if case == 'rerun' else 0)


def test_a_role_call_whose_refused_receipt_ends_its_calls_file_is_sent_again(tmp_path):
    """The role-call replay keeps today's rule (``chain._replay_receipts`` never sets ``final_refusals``): under 'on' a
    role request whose saved receipt is a refusal at the end of its calls file (where the earlier process stood) is
    sent again, as every failure there is. The recorder keeps the receipt's rest here (role recorders keep none today),
    so that the rule, not a missing code, is what sends it again."""
    ledger, sent = units.Ledger(tmp_path / 'ledger.json', 10 ** 7), []

    def client(system, user):
        sent.append(user)
        return dict(FILTERED)
    path = tmp_path / 's1' / 'card-r1' / 'calls' / 'writer-card_writer.json'

    def role():
        call = units.CallRecorder(client, ledger, max_tokens=500, tag='writer', unit='s1/card-r1', out_path=path)
        call.keep_rest = True
        return chain._replay_receipts(chain._keep_earlier_sends(call), numbered=True)
    role()('writer system', 'write a card')
    saved = json.loads(path.read_text())
    assert units.provider_filter_refusal(saved[-1]) and saved[-1]['occurrence'] == 1
    assert role()('writer system', 'write a card')['error_code'] == '1301'
    assert sent == ['write a card'] * 2 and ledger.state['sends'] == 2
    assert [send['occurrence'] for send in json.loads(path.read_text())] == [1, 1]


def services_of(root, solver=None):
    """The chain fakes of ``tests/test_typed_chain.py`` (SearchQA alone) under the resume replay 'on', every solver
    request of ``ITEM`` refused by the fake provider (``filtering_solver``) unless another ``solver`` is given."""
    services, modules, script = chain_v2.build(root, order=('searchqa',),
                                               scripted={'replies': {'solver': solver or filtering_solver}})
    services.manifest['resume_replay'] = 'on'
    return services, script


def test_a_refused_cell_killed_before_its_record_is_replayed_on_resume_and_stays_a_final_zero(tmp_path, monkeypatch):
    """Finding 1 of Codex's review of f1950b9 through the chain: the process dies right after the first noise cell of
    ``ITEM`` was solved -- its calls file holds the refusal alone, the cell record is not written. The resumed step
    answers the cell from its calls file: nothing is sent for it, the cell is the same final model-side unknown, and
    every record, every calls file, the scripted sends and the ledger are an uninterrupted run's."""
    monkeypatch.setattr(chain, '_now', lambda: replay.NOW)
    reference, resumed = tmp_path / 'a', tmp_path / 'b'
    services, script_a = services_of(reference)
    state = chain.run(reference, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    services, script_b = services_of(resumed)
    hit = replay.kill_after_solve(services, 's1/noise', item_id=ITEM)
    with pytest.raises(learning.Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    (item_id, tag), = hit
    cell = resumed / 'G' / 's1' / 'noise' / 'cells' / (tag + '.json')
    saved = replay.calls_file(resumed, 's1/noise', tag)
    assert not cell.exists() and len(saved) == 1 and saved[0]['receipt_rest']['error_code'] == '1301'
    chain_v2.recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    row = json.loads(cell.read_text())
    assert row['correct'] is None and row['infrastructure_unknown'] is False and row['sends'] == saved
    assert replay.calls_file(resumed, 's1/noise', tag) == saved
    replay.assert_same(replay.every_record(resumed), replay.every_record(reference))
    assert Counter(script_b.calls) == Counter(script_a.calls)
    assert replay.ledger_of(resumed) == replay.ledger_of(reference)


def test_a_refusal_saved_before_its_charge_was_settled_is_settled_once_and_never_sent_again(tmp_path, monkeypatch):
    """The process dies after a refused send of ``ITEM`` in s1/noise reached its calls file and before the ledger
    settled its reservation. The resumed ledger settles it from the saved receipt (``units.durable_receipts``: neither
    recovered nor marked for a re-run) and the resumed cell replays it, as that settlement presumes: nothing is sent
    again, and the ledger, every record and the scripted sends are an uninterrupted run's."""
    monkeypatch.setattr(chain, '_now', lambda: replay.NOW)
    reference, resumed = tmp_path / 'a', tmp_path / 'b'
    services, script_a = services_of(reference)
    state = chain.run(reference, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    original, hit = units.Ledger.settle, []

    def settle(self, key, receipt, **kwargs):
        entry = self.state['pending'].get(key) or {}
        if (entry.get('unit') == 's1/noise' and isinstance(receipt, dict) and receipt.get('error_code') == '1301'
                and not hit):
            hit.append((key, entry['cell']))
            raise learning.Kill()  # the refusal is in the calls file; the ledger still holds the reservation
        return original(self, key, receipt, **kwargs)
    monkeypatch.setattr(units.Ledger, 'settle', settle)
    services, script_b = services_of(resumed)
    with pytest.raises(learning.Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    (key, tag), = hit
    assert key in json.loads((resumed / 'G' / 'ledger.json').read_text())['pending']
    saved = replay.calls_file(resumed, 's1/noise', tag)
    assert [(send['logical_call'], send['receipt_rest']['error_code']) for send in saved] == [(key, '1301')]
    chain_v2.recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert replay.calls_file(resumed, 's1/noise', tag) == saved
    ledger_a, ledger_b = replay.ledger_of(reference), replay.ledger_of(resumed)
    assert ledger_b == ledger_a and ledger_b['recovered'] == []
    replay.assert_same(replay.every_record(resumed), replay.every_record(reference))
    assert Counter(script_b.calls) == Counter(script_a.calls)


def test_a_refusal_in_the_calls_file_of_a_cell_rerun_after_another_failure_is_not_sent_again(tmp_path):
    """The same with ``failures`` False: every noise cell of ``ITEM`` sends EXTRA before its solve request
    (``going_past``) and the provider's first EXTRA times out, so that cell is an infrastructure unknown whose calls
    file holds [EXTRA timed out, the refusal]; the chain pauses 'gate_cells_unknown'. The owner's recovery archives
    the cell and runs it again: EXTRA is sent again, the refusal is answered from the file (not sent a second time),
    and the healed cell is the final model-side unknown its two siblings are."""
    seen = Counter()

    def solver(system, user):
        if (system, user) == EXTRA:
            seen['extra'] += 1
            return dict(TIMEOUT) if seen['extra'] == 1 else 'extra answered'
        return filtering_solver(system, user)
    services, script = services_of(tmp_path, solver)
    services.solve_fn = replay.going_past(services.solve_fn, 's1/noise', ITEM)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'gate_cells_unknown' and state['paused']['unit'] == 's1/noise'
    noise = tmp_path / 'G' / 's1' / 'noise'
    [tag] = [p.stem for p in (noise / 'cells').glob('*.json') if json.loads(p.read_text())['infrastructure_unknown']]
    before = replay.calls_file(tmp_path, 's1/noise', tag)

    def shape(sends):
        return [(send['user'] == EXTRA[1], send['receipt']['ok'], (send.get('receipt_rest') or {}).get('error_code'))
                for send in sends]
    assert shape(before) == [(True, False, None), (False, False, '1301')]
    chain_v2.recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert [p.name for p in (noise / 'rerun').glob('*.json')] == [tag + '-1.json']
    after = replay.calls_file(tmp_path, 's1/noise', tag)
    assert after[:2] == before and shape(after[2:]) == [(True, True, None)]  # EXTRA alone was sent again
    healed = json.loads((noise / 'cells' / (tag + '.json')).read_text())
    assert healed['correct'] is None and healed['infrastructure_unknown'] is False
    assert healed['sends'] == [after[2], before[1]]  # this attempt's path: the new EXTRA, then the replayed refusal
    calibration = json.loads((noise / 'noise.json').read_text())
    assert (calibration['unknown_final'], calibration['reruns']) == (3, 1)


# ==== B7b (2): a refused item's text reaches no role sample that shows text without an outcome =====================
def test_a_cell_is_refused_when_its_solve_or_its_selection_request_was():
    assert units.cell_refused({'sends': [record(FILTERED, REST)], 'selection_sends': []})
    assert units.cell_refused({'sends': [record(DELIVERED, {})], 'selection_sends': [record(FILTERED, REST)]})
    assert not units.cell_refused({'sends': [record(DELIVERED, {}), record(FILTERED)], 'selection_sends': []})
    assert not units.cell_refused({'sends': [record({**FILTERED, 'error_type': 'http_500'}, REST)]})
    for row in ({}, None, [], {'sends': None, 'selection_sends': None}, {'sends': ['text']}):
        assert not units.cell_refused(row)


def coverage_world():
    bench, ids = 'searchqa', ['searchqa-l%d' % i for i in range(5)]
    items = [learning.item_of(bench, item_id) for item_id in ids]
    views = {item['task_id']: smoke.synthetic_view(bench, item) for item in items}
    probe = {'items': 5, 'routed': 5, 'fired': 3, 'noted': 1, 'faults': {'timeout': 1}, 'scope': 'first_request',
             'not_routed': [], 'per_item': [[ids[0], True, 12, []], [ids[1], False, 0, []], [ids[2], False, 0, []],
                                             [ids[3], True, 0, []], [ids[4], True, 0, ['timeout']]]}
    return ids, items, views, probe


def listed(report):
    return [[task['task_id'] for task in row['tasks']] for row in report['classes']]


def test_the_coverage_report_counts_a_refused_item_in_its_class_and_never_lists_its_text():
    ids, items, views, probe = coverage_world()
    plain = writers.coverage_report(probe, items, views)
    assert plain == writers.coverage_report(probe, items, views, exclude=())
    assert plain == writers.coverage_report(probe, items, views, exclude={ids[0], 'searchqa-g0'})  # listed nowhere
    assert listed(plain) == [[ids[3]], [ids[1], ids[2]], [ids[4]]]
    found = writers.coverage_report(probe, items, views, exclude={ids[1], ids[4]})
    assert [(row['class'], row['count']) for row in found['classes']] == [
        (row['class'], row['count']) for row in plain['classes']] == [
        ('fired_without_note', 1), ('not_fired', 2), ('fault:timeout', 1)]
    assert {k: v for k, v in found.items() if k != 'classes'} == {k: v for k, v in plain.items() if k != 'classes'}
    assert listed(found) == [[ids[3]], [ids[2]], []]
    assert 'item %s?' % ids[1] not in json.dumps(found) and 'item %s?' % ids[4] not in json.dumps(found)
    # the class's next item takes the place of a refused one (``shown`` at most)
    assert listed(writers.coverage_report(probe, items, views, shown=1, exclude={ids[1]})) == [[ids[3]], [ids[2]],
                                                                                              [ids[4]]]


def test_the_analyst_row_of_a_refused_learn_item_keeps_its_id_and_outcomes_and_shows_no_text():
    """``items.plan.learn_rows`` decides from the diagnose cells a row is built from: an item with a refused run (its
    solve or its selection request) keeps its id, its outcomes and its kind, with ``public_text`` None and no
    ``wrong_reply`` (even when another of its runs delivered a wrong reply); every other row is as before."""
    bench, ids = 'searchqa', ['searchqa-l0', 'searchqa-l1', 'searchqa-l2']
    items = [learning.item_of(bench, item_id) for item_id in ids]

    def cell(item_id, correct, reply='', *, refused=False, selection=False):
        send = record(FILTERED, REST) if refused else record({**DELIVERED, 'response': reply}, {})
        return {'bench': bench, 'item_id': item_id, 'correct': correct, 'reply': reply or None,
                'sends': [{**send, 'user': 'request of ' + item_id}],
                'selection_sends': [record(FILTERED, REST)] if selection else []}
    runs = {ids[0]: [cell(ids[0], None, refused=True), cell(ids[0], False, 'wrong 0'), cell(ids[0], False, 'wrong')],
            ids[1]: [cell(ids[1], False, 'wrong 1'), cell(ids[1], True, 'right'), cell(ids[1], True, 'right')],
            ids[2]: [cell(ids[2], False, 'wrong 2', selection=True), cell(ids[2], True, 'r'), cell(ids[2], True, 'r')]}
    rows = plan.learn_rows(bench, items, runs, 3, kind_of=lambda item: {'size': 'small'})
    assert rows[0] == {'id': ids[0], 'public_text': None, 'outcomes': [None, False, False], 'size': 'small'}
    assert rows[2] == {'id': ids[2], 'public_text': None, 'outcomes': [False, True, True], 'size': 'small'}
    assert rows[1] == {'id': ids[1], 'public_text': plan.public_text_of(bench, items[1]), 'outcomes': [False, True, True],
                       'wrong_reply': plan._excerpt('wrong 1'), 'size': 'small'}
    clean = {item_id: [cell(item_id, c['correct'], c['reply'] or '') for c in runs[item_id]] for item_id in ids}
    assert [row['public_text'] for row in plan.learn_rows(bench, items, clean, 3)] == [
        plan.public_text_of(bench, item) for item in items]
    assert [row.get('wrong_reply') for row in plan.learn_rows(bench, items, clean, 3)] == [
        plan._excerpt('wrong 0'), plan._excerpt('wrong 1'), plan._excerpt('wrong 2')]


def test_a_refused_practice_item_reaches_no_role_request_and_keeps_its_counts(tmp_path):
    """P1's harness ('repair', SearchQA: learn l0..l4, gate g0..g2) under 'on'; the provider refuses every solver
    request of the learn item l0 (a final model-side zero in every arm). No role request of the step holds its text:
    the engineer's hook view is l1's (the first learn item not refused), the repair request's coverage counts l0 in
    its class (not_fired: 3) and lists l3 and l4 only, and the accepted program's describer shows l1, l2 and l3. The
    learn denominators keep l0."""
    def solver(system, user):
        return dict(FILTERED) if 'item searchqa-l0?' in user else 'The answer is 42.'
    v0 = learning.program('v0', note=['l1', 'l2', 'g0', 'g1', 'g2'])
    script = learning.Engineer(v0, scripted={'replies': {'solver': solver}})
    services = learning.build(tmp_path, script, limits={'program_paid_feedback': 0})
    services.manifest['resume_replay'] = 'on'
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    refused = [row for row in learning.gate_cells(tmp_path, 's1/outcomes') if row['item_id'] == 'searchqa-l0']
    assert len(refused) == 1 and refused[0]['correct'] is None and refused[0]['infrastructure_unknown'] is False
    decisions = learning.read(tmp_path, 's1', 'decisions.json')
    assert decisions['outcomes']['learn']['items'] == 5 and decisions['outcomes']['learn']['unknown'] == 1
    role = [(purpose, unit, user) for purpose, unit, _, user in script.requests
            if purpose in ('card_writer', 'program_writer', 'describer')]
    assert {purpose for purpose, _, _ in role} == {'card_writer', 'program_writer', 'describer'}
    assert not [(purpose, unit) for purpose, unit, user in role if 'item searchqa-l0?' in user]
    hook = json.dumps(script.users('program_writer', 's1/programs')[0]['hook_views'])
    assert 'item searchqa-l1?' in hook and 'item searchqa-l0?' not in hook
    coverage = script.users('program_writer', 's1/program-1-repair-1')[0]['coverage']
    assert (coverage['items'], coverage['routed'], coverage['noted']) == (5, 5, 2)
    assert coverage['classes'] == [{'class': 'not_fired', 'count': 3, 'tasks': learning.tasks('searchqa', 'l3', 'l4')}]
    assert decisions['programs'][0]['accepted']
    describer = [json.loads(user) for purpose, unit, user in role if purpose == 'describer']
    assert [request['public_practice_examples'] for request in describer] == [
        [learning.view_text('searchqa', 'searchqa-l%d' % i) for i in (1, 2, 3)]]


class DiagnoseRefusal(stage.Script):
    """P2b's scripted clients whose provider refuses the solver requests of the learn item searchqa-00 in the unit
    s1/diagnose only (B's R runs there): only the item stage's records hold the refusal, and a resumed step, whose
    sealed items.json skips that unit, never re-enters them."""

    def reply(self, purpose, system, user, *, unit=None):
        found = super().reply(purpose, system, user, unit=unit)
        if purpose == 'solver' and unit == 's1/diagnose' and 'CTX00 ' in user:
            return dict(FILTERED)
        return found


def test_an_item_refused_in_the_item_stage_stays_out_of_the_analyst_rows_and_later_requests_also_on_resume(
        tmp_path, monkeypatch):
    """P2b's SearchQA scenario (item stage 'planned', program learning 'single') under 'on'; the learn item
    searchqa-00 is refused in s1/diagnose alone. The analyst's row for it holds its id and outcomes only; the card's
    describer shows the learn items 01, 02, 03 and the engineer's hook view is 01's. Then the process dies right
    after the card's describer call returned (its receipt saved, skill.json not written): the resumed step -- whose
    sealed items.json means diagnose is never re-entered -- reads the refusal from the step's records, rebuilds the
    same describer request and answers it from its calls file: no send, every record and the ledger as an
    uninterrupted run's."""
    monkeypatch.setattr(chain, '_now', lambda: replay.NOW)
    reference, resumed = tmp_path / 'a', tmp_path / 'b'

    def build(root, script):
        services = stage.build(root, script)
        services.manifest['resume_replay'] = 'on'
        return services
    script_a = DiagnoseRefusal()
    state = chain.run(reference, 'G', services=build(reference, script_a), sleep=lambda s: None)
    assert state['complete'], state['paused']
    diagnose = stage.cells_of(reference, 's1/diagnose')
    assert sorted(row['item_id'] for row in diagnose if units.cell_refused(row)) == ['searchqa-00'] * 3
    assert all(row['correct'] is None and not row['infrastructure_unknown'] for row in diagnose
               if row['item_id'] == 'searchqa-00')
    analyst = stage.request_of(next(user for purpose, _, _, user in script_a.requests if purpose == 'item_analyst'))
    rows = {row['id']: row for row in analyst['learn_items']}
    assert rows['searchqa-00'] == {'id': 'searchqa-00', 'public_text': None, 'outcomes': [None, None, None]}
    assert all(row['public_text'] for item_id, row in rows.items() if item_id != 'searchqa-00') and len(rows) == 12
    describer = [stage.request_of(user) for purpose, unit, _, user in script_a.requests
                 if purpose == 'describer' and unit == 's1/card-r1']
    assert len(describer) == 1
    examples = describer[0]['public_practice_examples']
    assert [text.split(' ')[0] for text in examples] == ['Q01', 'Q02', 'Q03']
    proposal = stage.request_of(next(user for purpose, unit, _, user in script_a.requests
                                     if purpose == 'program_writer' and unit == 's1/programs'))
    assert 'CTX01 ' in json.dumps(proposal['hook_views']) and 'CTX00 ' not in json.dumps(proposal['hook_views'])
    original, hit = chain._Run.record, []

    def record_(self, unit, name, compute):
        if (unit, name) == ('s1/card-r1', 'skill.json') and not hit:
            compute()        # the describer call is made and its receipt saved in its calls file ...
            hit.append(unit)
            raise learning.Kill()  # ... and the process dies before skill.json is written
        return original(self, unit, name, compute)
    monkeypatch.setattr(chain._Run, 'record', record_)
    script_b = DiagnoseRefusal()
    services = build(resumed, script_b)
    with pytest.raises(learning.Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    assert hit and not (resumed / 'G' / 's1' / 'card-r1' / 'skill.json').exists()
    chain_v2.recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert Counter(script_b.calls) == Counter(script_a.calls)
    replay.assert_same(replay.every_record(resumed), replay.every_record(reference))
    assert replay.ledger_of(resumed) == replay.ledger_of(reference)


# ==== B7b (3): a read cell through the real read path ==============================================================
PANEL_ITEM = 'searchqa-t0'


def panel_solver(system, user):
    """The fake provider of the run-mode reads: it refuses every solver request of the panel item ``PANEL_ITEM``."""
    return dict(FILTERED) if 'item %s?' % PANEL_ITEM in user else 'The answer is 42.'


def read_services(root, script, seen, *, mode='on'):
    """P3r's run mode (interleaved, full, base historical, the anchor C alone, the consent of C..S5; SearchQA only)
    through the REAL ``reads`` -- its recorders, the replay wrapping of ``reads._from_services``, its rows and mirror."""
    manifest = reading.c_manifest(**({'resume_replay': 'on'} if mode == 'on' else {}))
    return reading.run_services(root, 'G', manifest, seen=seen, script=script, order=('searchqa',))


@pytest.mark.parametrize('mode', ['off', 'on'])
def test_a_read_cell_the_provider_refuses_completes_the_read_as_a_model_side_unknown(tmp_path, monkeypatch,
                                                                                    qualified, mode):  # noqa: F811
    """Finding 3 of Codex's review of f1950b9: through the real read path the C and S1 reads of SearchQA complete
    with no pause; the refused panel item's cell is unknown (scored 0) and, under 'on', a model-side unknown with the
    code in its send's rest (the read's recorders keep it through ``units.replaying``), counted in the sealed mirror as
    unknown and never as an infrastructure unknown. Under 'off' (typed-v2) the record keeps no code: the same cell is
    an infrastructure unknown, as before."""
    monkeypatch.setattr(chain, '_now', lambda: replay.NOW)
    reading.write_consent(tmp_path)
    services = read_services(tmp_path, reading.Capture({'replies': {'solver': panel_solver}}), [], mode=mode)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'] and state['paused'] is None, state['paused']
    for event in ('C', 'S1'):
        cells = list(reading.cells_of(tmp_path / 'G' / ('test-read-%s-searchqa' % event)).values())
        [row] = [row for row in cells if row['item_id'] == PANEL_ITEM]
        assert len(cells) == 2 and row['correct'] is None and row['sends'][0]['receipt']['error_type'] == 'http_400'
        status = json.loads(reads.status_path(tmp_path, 'G', event, 'searchqa').read_text())
        assert status['status'] == 'complete' and status['unknown'] == 1
        if mode == 'on':
            assert row['infrastructure_unknown'] is False and row['sends'][0]['receipt_rest']['error_code'] == '1301'
            assert status['infrastructure_unknown'] == 0
        else:
            assert row['infrastructure_unknown'] is True and 'receipt_rest' not in row['sends'][0]
            assert status['infrastructure_unknown'] == 1


def test_a_refused_read_cell_killed_before_its_record_is_replayed_on_resume(tmp_path, monkeypatch,
                                                                            qualified):  # noqa: F811
    """The same read under 'on': the process dies right after the refused panel item's cell of the sealed unit
    test-read-S1-searchqa was solved (the refusal alone in its calls file; no cell, done record or mirror). The resumed
    read opens its panel again under the consent and answers the cell from its calls file: nothing is sent for it,
    the cell is the model-side unknown, and every file of the chain, the scripted sends and the ledger are an
    uninterrupted run's."""
    monkeypatch.setattr(chain, '_now', lambda: replay.NOW)
    unit = 'test-read-S1-searchqa'
    reference, resumed = tmp_path / 'a', tmp_path / 'b'
    for root in (reference, resumed):
        reading.write_consent(root)
    script_a = reading.Capture({'replies': {'solver': panel_solver}})
    state = chain.run(reference, 'G', services=read_services(reference, script_a, []), sleep=lambda s: None)
    assert state['complete'], state['paused']
    script_b = reading.Capture({'replies': {'solver': panel_solver}})
    services = read_services(resumed, script_b, [])
    hit = replay.kill_after_solve(services, unit, item_id=PANEL_ITEM)
    with pytest.raises(learning.Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    (item_id, tag), = hit
    where = resumed / 'G' / unit
    saved = json.loads((where / 'calls' / (tag + '.json')).read_text())
    assert not (where / 'cells' / (tag + '.json')).exists() and not (where / 'done.json').exists()
    assert len(saved) == 1 and saved[0]['receipt_rest']['error_code'] == '1301'
    reading.recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    row = json.loads((where / 'cells' / (tag + '.json')).read_text())
    assert row['correct'] is None and row['infrastructure_unknown'] is False and row['sends'] == saved
    assert reading.snapshot(resumed / 'G') == reading.snapshot(reference / 'G')
    assert Counter(script_b.calls) == Counter(script_a.calls)
    assert replay.ledger_of(resumed) == replay.ledger_of(reference)


def test_when_every_learn_item_is_refused_the_hook_view_comes_from_another_practice_item(tmp_path):
    """Codex's second look at B7b: the provider refuses every learn item (l0..l4). The engineer's hook view is then the
    first item of the practice source that is neither refused nor a real gate item of the step (here the first panel
    item, p0) -- never a refused text, never a gate item's."""
    def solver(system, user):
        return dict(FILTERED) if 'item searchqa-l' in user else 'The answer is 42.'
    v0 = learning.program('v0', note=['g0', 'g1', 'g2'])
    script = learning.Engineer(v0, scripted={'replies': {'solver': solver}})
    services = learning.build(tmp_path, script, limits={'program_paid_feedback': 0})
    services.manifest['resume_replay'] = 'on'
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    hook = json.dumps(script.users('program_writer', 's1/programs')[0]['hook_views'])
    assert 'item searchqa-l' not in hook and 'item searchqa-g' not in hook
    assert 'item searchqa-p0?' in hook
