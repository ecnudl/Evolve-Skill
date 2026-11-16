"""Ledger, recorded calls and the concurrent unit runner of typed-v2 (fakes only)."""
import json
import shutil
import tempfile
import threading
from pathlib import Path

import pytest

from skillopt.execskill.typed import units


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    root = Path('/tmp/typed2-neutral')
    root.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='unit-', dir=root))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def receipt(ok=True, text='ok', prompt=100, completion=20, error=None):
    return {'ok': ok, 'response': text if ok else None, 'finish_reason': 'stop' if ok else None,
            'usage': {'prompt_tokens': prompt, 'completion_tokens': completion, 'total_tokens': prompt + completion},
            'error_type': error}


def test_ledger_charges_before_send_and_settles(tmp_path):
    ledger = units.Ledger(tmp_path / 'ledger.json', 10_000)
    key, bound = ledger.before_send('sys', 'user', 1000, cell='c1', unit='u1')
    # route B's reservation: four attempt bounds (the frozen clients retry up to three times inside one call)
    assert bound == len('sysuser') + 512 + 1000 and ledger.state['charged'] == 4 * bound and ledger.state['pending']
    ledger.settle(key, receipt(prompt=50, completion=10), max_tokens=1000, prompt_bound=bound - 1000)
    assert ledger.state['charged'] == 60 and ledger.state['reported'] == 60 and not ledger.state['pending']
    assert ledger.state['by_unit']['u1'] == {'calls': 1, 'reported': 60, 'charged': 60}
    key, bound = ledger.before_send('sys', 'user', 1000, cell='c2', unit='u1')
    ledger.settle(key, {'ok': False, 'usage': {}}, max_tokens=1000, prompt_bound=bound - 1000)
    assert ledger.state['charged'] == 60 + bound and ledger.state['missing_usage'] == 1
    with pytest.raises(units.Stop):
        units.Ledger(tmp_path / 'ledger.json', 10_000)  # exists, resume off
    with pytest.raises(ValueError):
        units.Ledger(tmp_path / 'ledger.json', 20_000, resume=True)  # cap changed


def test_ledger_cap_breach_and_resume_keep_pending_bounds(tmp_path):
    ledger = units.Ledger(tmp_path / 'ledger.json', 7_000)
    key, bound = ledger.before_send('s', 'u', 1000, cell='c1', unit='u')
    with pytest.raises(units.Stop):
        ledger.before_send('s', 'u', 1000, cell='c2', unit='u')  # cap: two reservations of 4 x 1514 exceed 7,000
    assert ledger.state['stop_reason'] == 'token_cap' and ledger.stopped()
    # an interrupted pending call survives a restart with its whole reservation and marks its cell for rerun; the
    # unit's cost names that reservation too (Codex review 11/10, finding 6)
    resumed = units.Ledger(tmp_path / 'ledger.json', 7_000, resume=True)
    assert resumed.rerun_cells == {('u', 'c1')} and resumed.state['pending'] == {} and resumed.state['charged'] == 4 * bound
    assert resumed.state['recovered'][0]['cell'] == 'c1' and resumed.stopped()
    assert resumed.state['by_unit']['u'] == {'calls': 1, 'reported': 0, 'charged': 4 * bound, 'recovered': 4 * bound}
    fresh = units.Ledger(tmp_path / 'l2.json', 100_000)
    key, bound = fresh.before_send('s', 'u', 100, cell='c', unit='u')
    with pytest.raises(units.Stop):
        fresh.settle(key, receipt(completion=101), max_tokens=100, prompt_bound=bound - 100)
    assert fresh.state['stop_reason'] == 'reservation_breach'


def test_infrastructure_streak_persists_and_stops(tmp_path):
    ledger = units.Ledger(tmp_path / 'l.json', 10 ** 9)
    for _ in range(7):
        ledger.observe_infrastructure(True)
    assert not ledger.stopped() and ledger.state['infra_streak'] == 7
    again = units.Ledger(tmp_path / 'l.json', 10 ** 9, resume=True)
    again.observe_infrastructure(True)
    assert again.stopped() and again.state['stop_reason'] == 'eight_consecutive_infrastructure_unknowns'
    other = units.Ledger(tmp_path / 'm.json', 10 ** 9)
    for _ in range(7):
        other.observe_infrastructure(True)
    other.observe_infrastructure(False)
    assert other.state['infra_streak'] == 0


def test_call_recorder_records_and_classifies(tmp_path):
    ledger = units.Ledger(tmp_path / 'l.json', 10 ** 7)
    calls = []

    def client(system, user):
        calls.append((system, user))
        return receipt(text='reply')
    rec = units.CallRecorder(client, ledger, max_tokens=500, tag='t', unit='u', out_path=tmp_path / 'calls' / 't.json',
                             transform=lambda s, u: (s, u + '\n# suffix'))
    out = rec('sys', 'user')
    assert out['response'] == 'reply' and calls == [('sys', 'user\n# suffix')]
    saved = json.loads((tmp_path / 'calls' / 't.json').read_text())
    assert saved[0]['receipt']['response'] == 'reply' and 'logical_call' in saved[0] and rec.tokens() == 120
    assert not rec.infrastructure_unknown()
    bad = units.CallRecorder(lambda s, u: {'ok': False, 'usage': {}, 'error_type': 'http_502'}, ledger, max_tokens=500,
                             tag='b', unit='u', out_path=None)
    bad('s', 'u')
    assert bad.infrastructure_unknown()
    modelside = units.CallRecorder(lambda s, u: {'ok': False, 'usage': {}, 'error_type': 'finish_length'}, ledger,
                                   max_tokens=500, tag='m', unit='u', out_path=None)
    modelside('s', 'u')
    assert not modelside.infrastructure_unknown()
    with pytest.raises(RuntimeError):
        units.CallRecorder(lambda s, u: (_ for _ in ()).throw(RuntimeError('boom')), ledger, max_tokens=5, tag='e', unit='u', out_path=None)('s', 'u')
    assert not ledger.state['pending']  # settled at the bound after the exception


@pytest.mark.parametrize('interrupt', [KeyboardInterrupt, SystemExit])
def test_an_interrupted_call_stays_pending_and_is_recovered_on_resume(tmp_path, interrupt):
    """fix-b (review rb-resume 1): SIGINT (KeyboardInterrupt) or SystemExit inside a call ends the process like a kill:
    the call may have reached the provider, so it is never settled; its reservation stays pending, and the resumed
    ledger records it as recovered and marks its (unit, cell) for a re-run, exactly as after a kill (the decision
    records count such re-runs from the recovered rows). An ordinary exception still settles at the bound."""
    ledger = units.Ledger(tmp_path / 'l.json', 10 ** 7)

    def client(system, user):
        raise interrupt()
    rec = units.CallRecorder(client, ledger, max_tokens=500, tag='c1', unit='s1/card-r1',
                             out_path=tmp_path / 'calls' / 'c1.json')
    with pytest.raises(interrupt):
        rec('sys', 'user')
    (key, entry), = ledger.state['pending'].items()
    assert entry['cell'] == 'c1' and entry['unit'] == 's1/card-r1' and ledger.state['charged'] == entry['bound']
    saved = json.loads((tmp_path / 'calls' / 'c1.json').read_text())
    assert saved[0]['receipt'] is None and saved[0]['exception'] == interrupt.__name__
    ledger.stop('interrupted')  # what run_unit does on its way out
    resumed = units.Ledger(tmp_path / 'l.json', 10 ** 7, resume=True)
    assert resumed.rerun_cells == {('s1/card-r1', 'c1')} and resumed.state['pending'] == {}
    assert [(row['unit'], row['cell']) for row in resumed.state['recovered']] == [('s1/card-r1', 'c1')]
    assert resumed.state['charged'] == entry['bound'] and resumed.state['by_unit']['s1/card-r1']['calls'] == 1


def make_jobs(benches, n, arms=('sys', 'suffix')):
    return [(b, {'task_id': '%s-%d' % (b, i), 'public': {}}, arms) for b in benches for i in range(n)]


def build_ok(bench, item, arm, tag):
    return {'bench': bench, 'item_id': item['task_id'], 'arm': arm, 'correct': True, 'failure': None,
            'configuration_error': False, 'infrastructure_unknown': False, 'tokens': 10,
            'sends': [{'receipt': {'ok': True, 'response': 'x'}}]}


def test_run_unit_runs_all_cells_concurrently_and_resumes(tmp_path):
    ledger = units.Ledger(tmp_path / 'l.json', 10 ** 9)
    seen = []
    lock = threading.Lock()

    def build(bench, item, arm, tag):
        with lock:
            seen.append((bench, item['task_id'], arm))
        return build_ok(bench, item, arm, tag)
    jobs = make_jobs(['searchqa', 'alfworld'], 4)
    cells, reason = units.run_unit(tmp_path / 'u1', jobs, unit='u1', widths={'searchqa': 3, 'alfworld': 2}, build_cell=build, ledger=ledger)
    assert reason is None and len(cells) == 16 and len(seen) == 16
    done = json.loads((tmp_path / 'u1' / 'done.json').read_text())
    assert done['cells'] == 16 and done['missing_cells'] == 0
    # both arms of an item run back to back in a deterministic order
    order = [arm for b, i, arm in seen if i == 'searchqa-2']
    assert order == units.arm_order('searchqa-2', ('sys', 'suffix'))
    # a done unit is returned from disk without rebuilding
    seen.clear()
    cells2, _ = units.run_unit(tmp_path / 'u1', jobs, unit='u1', widths={}, build_cell=build, ledger=ledger)
    assert len(cells2) == 16 and not seen
    # partial unit without done.json: resume reuses completed cells, reruns the ledger's pending cells
    partial = tmp_path / 'u2'
    (partial / 'cells').mkdir(parents=True)
    tag = units.cell_tag('searchqa', 'searchqa-0', 'sys')
    (partial / 'cells' / (tag + '.json')).write_text(json.dumps(build_ok('searchqa', {'task_id': 'searchqa-0'}, 'sys', tag)))
    with pytest.raises(units.Stop):
        units.run_unit(partial, make_jobs(['searchqa'], 1), unit='partial', widths={}, build_cell=build, ledger=ledger)
    ledger.rerun_cells.add(('partial', units.cell_tag('searchqa', 'searchqa-0', 'suffix')))
    seen.clear()
    cells3, _ = units.run_unit(partial, make_jobs(['searchqa'], 1), unit='partial', widths={}, build_cell=build, ledger=ledger, resume=True)
    assert len(cells3) == 2 and seen == [('searchqa', 'searchqa-0', 'suffix')]


def test_run_unit_stops_on_first_cell_configuration_and_on_cap(tmp_path):
    ledger = units.Ledger(tmp_path / 'l.json', 10 ** 9)

    def broken(bench, item, arm, tag):
        raise KeyError('missing runtime')
    cells, reason = units.run_unit(tmp_path / 'u', make_jobs(['searchqa'], 3), unit='u', widths={'searchqa': 3}, build_cell=broken, ledger=ledger)
    assert cells == [] and reason.startswith('first_cell_configuration') and ledger.stopped()
    assert (tmp_path / 'u' / 'failure.json').exists() and len(list((tmp_path / 'u' / 'unsubmitted').glob('*.json'))) == 1
    capped = units.Ledger(tmp_path / 'c.json', 4_000)  # each send reserves 4 x 812 and settles 250: four cells fit

    def spend(bench, item, arm, tag):
        key, bound = capped.before_send('s' * 200, 'u', 100, cell=tag, unit='u')
        capped.settle(key, receipt(prompt=200, completion=50), max_tokens=100, prompt_bound=bound - 100)
        return build_ok(bench, item, arm, tag)
    cells, reason = units.run_unit(tmp_path / 'v', make_jobs(['searchqa'], 5), unit='v', widths={'searchqa': 1}, build_cell=spend, ledger=capped)
    assert reason == 'token_cap' and 0 < len(cells) < 10
    done = json.loads((tmp_path / 'v' / 'done.json').read_text())
    assert done['stop_reason'] == 'token_cap' and done['missing_cells'] == 10 - len(cells)


def test_sealed_path_guard():
    with pytest.raises(ValueError):
        units.checked_path('/data/run/G/test-read-searchqa/cells/x.json')
    assert units.checked_path('/data/run/G/test-read-searchqa/x.json', allow_sealed=True).name == 'x.json'
    assert units.checked_path('/data/run/G/s1/noise/cells/x.json').name == 'x.json'


def test_run_unit_stops_on_a_route_b_stop_kind_from_any_cell(tmp_path):
    """A route-B stop (sandbox, balance, package, ...) raised by a non-first cell stops the unit with its kind
    (stop.json names the cell) instead of becoming an unsubmitted row; a later cell is never submitted."""
    from skillopt.execskill.errors import BalanceExhausted, SandboxUnavailable
    ledger = units.Ledger(tmp_path / 'l.json', 10 ** 9)
    seen = []

    def build(bench, item, arm, tag):
        seen.append(item['task_id'])
        if item['task_id'] == 'searchqa-2':
            raise SandboxUnavailable('docker down')
        return build_ok(bench, item, arm, tag)
    cells, reason = units.run_unit(tmp_path / 'u', make_jobs(['searchqa'], 4, arms=('sys',)), unit='u', widths={'searchqa': 1},
                                   build_cell=build, ledger=ledger)
    assert reason == 'sandbox' and ledger.state['stop_reason'] == 'sandbox' and len(cells) == 2
    stop = json.loads((tmp_path / 'u' / 'stop.json').read_text())
    assert stop['reason'] == 'sandbox' and stop['failure'] == 'SandboxUnavailable' and stop['cell'] == units.cell_tag('searchqa', 'searchqa-2', 'sys')
    assert not (tmp_path / 'u' / 'unsubmitted').exists() and 'searchqa-3' not in seen
    assert json.loads((tmp_path / 'u' / 'done.json').read_text())['missing_cells'] == 2
    other = units.Ledger(tmp_path / 'm.json', 10 ** 9)
    broke = lambda bench, item, arm, tag: (_ for _ in ()).throw(BalanceExhausted('balance'))
    _, reason = units.run_unit(tmp_path / 'v', make_jobs(['searchqa'], 1, arms=('sys',)), unit='v', widths={}, build_cell=broke, ledger=other)
    assert reason == 'balance_exhausted' and other.stopped()


def test_mark_infrastructure_reruns_and_archive_done(tmp_path):
    ledger = units.Ledger(tmp_path / 'l.json', 10 ** 9)
    unit = tmp_path / 'u'
    jobs = make_jobs(['searchqa'], 3, arms=('sys',))
    failing = {'on': True}

    def build(bench, item, arm, tag):
        row = build_ok(bench, item, arm, tag)
        if failing['on'] and item['task_id'] != 'searchqa-0':
            row.update(correct=None, infrastructure_unknown=True, sends=[{'receipt': {'ok': False, 'error_type': 'transport'}}])
        return row
    cells, reason = units.run_unit(unit, jobs, unit='unit', widths={'searchqa': 1}, build_cell=build, ledger=ledger)
    assert reason is None and sum(c['correct'] is None for c in cells) == 2
    assert units.mark_infrastructure_reruns(unit, ledger, unit='unit') == []  # a done unit is never touched
    assert units.archive_done(unit) and (unit / 'done-stopped-1.json').exists() and not (unit / 'done.json').exists()
    marked = units.mark_infrastructure_reruns(unit, ledger, unit='unit')
    assert sorted(marked) == sorted(units.cell_tag('searchqa', 'searchqa-%d' % i, 'sys') for i in (1, 2))
    assert ledger.rerun_cells == {('unit', tag) for tag in marked} and len(list((unit / 'rerun').glob('*.json'))) == 2
    # typed-v2 step 5w: the archived record is moved out of cells/ (one file per earlier attempt, counted as a re-run)
    assert not any((unit / 'cells' / (tag + '.json')).exists() for tag in marked)
    assert units.reruns_of(unit, marked) == 2
    failing['on'] = False
    cells, reason = units.run_unit(unit, jobs, unit='unit', widths={'searchqa': 1}, build_cell=build, ledger=ledger, resume=True)
    assert reason is None and all(c['correct'] is True for c in cells) and len(cells) == 3
    assert not units.archive_done(tmp_path / 'nowhere')


def test_ledger_charges_every_billed_attempt_of_one_call(tmp_path):
    """Route B's per-attempt settlement (Codex review 11/10, finding 2): a timed-out attempt that reached the
    provider is charged its whole bound, a refused one nothing, the delivered one its usage; an exception (no
    receipt) the whole reservation; a client outside the contract (five attempts) breaches."""
    ledger = units.Ledger(tmp_path / 'l.json', 10 ** 6)
    key, bound = ledger.before_send('s', 'u', 100, cell='a', unit='u')
    timed_out = {**receipt(prompt=100, completion=20), 'attempts': [{'error': 'ReadTimeout'}, {'status': 200}]}
    assert ledger.settle(key, timed_out) == bound + 120
    key, bound = ledger.before_send('s', 'u', 100, cell='b', unit='u')
    refused = {**receipt(prompt=100, completion=20), 'attempts': [{'error': 'ConnectError'}, {'status': 429}, {'status': 200}]}
    assert ledger.settle(key, refused) == 120
    key, bound = ledger.before_send('s', 'u', 100, cell='c', unit='u')
    assert ledger.settle(key, None) == 4 * bound
    key, bound = ledger.before_send('s', 'u', 100, cell='d', unit='u')
    with pytest.raises(units.Stop):
        ledger.settle(key, {**receipt(), 'attempts': [{'status': 200}] * 5})
    assert ledger.state['stop_reason'] == 'reservation_breach'
    rec = units.CallRecorder(lambda s, u: {**receipt(), 'attempts': [{'status': 200}]}, units.Ledger(tmp_path / 'm.json', 10 ** 6),
                             max_tokens=100, tag='t', unit='u', out_path=tmp_path / 'calls.json')
    rec('s', 'u')
    saved = json.loads((tmp_path / 'calls.json').read_text())
    assert saved[0]['receipt']['attempts'] == [{'status': 200}] and saved[0]['reserved'] == 4 * saved[0]['charge_bound']


def test_recovery_reruns_configuration_failed_cells_and_never_confirms_with_them(tmp_path):
    """A cell whose reply arrived but whose judge raised (configuration_error) is re-run after a recovery and can
    never release a bench's concurrency (Codex review 11/10, finding 4)."""
    ledger = units.Ledger(tmp_path / 'l.json', 10 ** 9)
    unit = tmp_path / 'u'
    tag = units.cell_tag('searchqa', 'searchqa-0', 'sys')
    failed = {**build_ok('searchqa', {'task_id': 'searchqa-0'}, 'sys', tag), 'correct': None, 'configuration_error': True,
              'failure': 'KeyError'}
    units.write_json(unit / 'cells' / (tag + '.json'), failed)
    assert not units._responded(failed)
    marked = units.mark_infrastructure_reruns(unit, ledger, unit='unit')
    assert marked == [tag] and ('unit', tag) in ledger.rerun_cells and (unit / 'rerun' / (tag + '-1.json')).exists()
    seen = []

    def build(bench, item, arm, tag):
        seen.append((item['task_id'], arm))
        return build_ok(bench, item, arm, tag)
    cells, reason = units.run_unit(unit, make_jobs(['searchqa'], 1), unit='unit', widths={'searchqa': 2}, build_cell=build, ledger=ledger,
                                   resume=True)
    assert reason is None and ('searchqa-0', 'sys') in seen and all(c.get('configuration_error') is False for c in cells)


# ---- fix-b (review rb-resume 3): rerun entries only under the ledger's lock -------------------------------------
class TrackedRLock:
    """``threading.RLock`` that knows its owner thread (the Ledger's lock replaced in a guarded test)."""

    def __init__(self):
        self._lock, self.owner, self.depth = threading.RLock(), None, 0

    def acquire(self, *args, **kwargs):
        got = self._lock.acquire(*args, **kwargs)
        if got:
            self.owner, self.depth = threading.get_ident(), self.depth + 1
        return got

    def release(self):
        self.depth -= 1
        if not self.depth:
            self.owner = None
        self._lock.release()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()

    def held(self):
        return self.owner == threading.get_ident()


class GuardedSet(set):
    """The rerun set of a guarded ledger: every iteration and change from a thread that does not hold the ledger's
    lock is refused (AssertionError), so a test fails on any access a concurrent read unit could race with."""

    def __init__(self, values, lock):
        super().__init__(values)
        self.lock = lock

    def _check(self, what):
        assert self.lock.held(), 'rerun_cells.%s outside ledger.lock' % what
        return True


for _name in ('__iter__', 'add', 'discard', 'remove', 'pop', 'clear', 'update', 'difference_update',
              'intersection_update', 'symmetric_difference_update'):
    def _guarded(self, *args, _name=_name, **kwargs):
        self._check(_name)
        return getattr(set, _name)(self, *args, **kwargs)
    setattr(GuardedSet, _name, _guarded)


def guarded(ledger):
    ledger.lock = TrackedRLock()
    ledger.rerun_cells = GuardedSet(set.__iter__(ledger.rerun_cells), ledger.lock)
    return ledger


class GuardedLedger(units.Ledger):
    """``units.Ledger`` with the guard installed after its own construction (a resumed ledger fills the set first)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        guarded(self)


def test_rerun_entries_are_marked_read_and_consumed_only_under_the_ledger_lock(tmp_path):
    """fix-b (review rb-resume 3): the read units of one event run in parallel threads, and run_unit iterates
    ``rerun_cells``; a mark (``mark_infrastructure_reruns``) or a consumption by another unit outside the lock could
    raise 'Set changed size during iteration' and pause a resumed read event. Every access goes through the ledger's
    locked helpers: a guarded set refuses any access from a thread that does not hold the lock."""
    ledger = guarded(units.Ledger(tmp_path / 'l.json', 10 ** 9))
    unit = tmp_path / 'u'
    tag = units.cell_tag('searchqa', 'searchqa-0', 'sys')
    infra = {**build_ok('searchqa', {'task_id': 'searchqa-0'}, 'sys', tag), 'correct': None,
             'infrastructure_unknown': True}
    units.write_json(unit / 'cells' / (tag + '.json'), infra)
    assert units.mark_infrastructure_reruns(unit, ledger, unit='unit') == [tag]
    assert ledger.reruns_of_unit('unit') == {tag} and ledger.reruns_of_unit('other') == set()
    cells, reason = units.run_unit(unit, make_jobs(['searchqa'], 1, arms=('sys',)), unit='unit',
                                   widths={'searchqa': 2}, build_cell=build_ok, ledger=ledger, resume=True)
    assert reason is None and cells[0]['correct'] is True and ledger.reruns_of_unit('unit') == set()
    ledger.mark_rerun('unit', 'x')
    ledger.consume_reruns('unit', ['x', 'y'])
    with ledger.lock:
        assert set(ledger.rerun_cells) == set()
    with pytest.raises(AssertionError, match='outside ledger.lock'):
        ledger.rerun_cells.add(('unit', 'z'))  # the guard itself


def test_no_code_of_the_typed_package_touches_rerun_cells_outside_the_ledger():
    """fix-b (review rb-resume 3), structural: in ``skillopt/execskill/typed`` the attribute ``rerun_cells`` is read
    only inside ``units.Ledger`` (its locked helpers ``mark_rerun``, ``reruns_of_unit``, ``consume_reruns``)."""
    import ast
    package = Path(units.__file__).resolve().parent
    found = []
    for path in sorted(package.glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        inside = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and path.name == 'units.py' and node.name == 'Ledger':
                inside |= {id(inner) for inner in ast.walk(node)}
        found += ['%s:%d' % (path.name, node.lineno) for node in ast.walk(tree)
                  if isinstance(node, ast.Attribute) and node.attr == 'rerun_cells' and id(node) not in inside]
    assert found == []
