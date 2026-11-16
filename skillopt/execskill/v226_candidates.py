"""Main-v10 containment for one candidate's unexpected evaluation failure.

The unit runner still owns pauses. This layer executes inside its work callback,
records only exception types and code locations, and rethrows systemic failures
unchanged so the frozen unit pause/recovery rules remain authoritative.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field

from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import profiles as p
from .errors import ConfigurationError, stop_kind

FILE = 'v226-candidate-errors'
KIND = 'v226-candidate-errors'
_CURRENT = ContextVar('execskill_v226_candidate', default=None)
_PARENT_ROLES = frozenset(('parent', 'incumbent', 'S'))
_ROLES = _PARENT_ROLES | {'candidate', "S'", 'system'}
_INFRASTRUCTURE_MODULES = ('requests.', 'urllib.', 'urllib3.', 'httpx.', 'httpcore.', 'aiohttp.',
                           'socket', 'ssl', 'subprocess', 'concurrent.futures')
_HARD_MODULES = frozenset((
    'skillopt.execskill.policy', 'skillopt.execskill.manifest', 'skillopt.execskill.prelaunch',
    'skillopt.execskill.registry', 'skillopt.execskill.canaries', 'skillopt.execskill.canary',
    'skillopt.execskill.snapshot', 'skillopt.coevolution_v5.core',
    'skillopt.execskill.client', 'skillopt.execskill.v225_client', 'skillopt.execskill.budgets',
    'skillopt.coevo5.calls', 'skillopt.coevo5.roles', 'skillopt.coevo5.budget'))
_HARD_FUNCTIONS = frozenset(('require', 'verified', 'verify', 'seal', 'check_pins', 'leak_check',
                             'sheet_findings', 'canary_scan', 'scan_canaries', 'assert_learning_path',
                             '_ask', 'role_endpoint', 'solver_endpoint', 'send', '_send'))
_HARD_LOCATIONS = frozenset(('skillopt.execskill.engineer', function)
                          for function in ('analyse', 'payload', '_fit_train')) | {
                              ('skillopt.continual_eval.core', 'read_json')}


def _event(error):
    trace = error.__traceback__
    where = type(error).__module__ + ':unknown'
    while trace is not None:
        frame = trace.tb_frame
        where = frame.f_globals.get('__name__', 'unknown') + ':' + frame.f_code.co_name
        trace = trace.tb_next
    return {'kind': 'candidate_error', 'exception': type(error).__name__, 'where': where}


def signature(event):
    return event['exception'] + '@' + event['where']


def _hard(error, seen=None):
    """Explicit invariants and infrastructure never become experimental rejections."""
    from .cells import Pause
    from .chain import Terminated
    seen = set() if seen is None else seen
    if id(error) in seen:
        return False
    seen.add(id(error))
    if isinstance(error, (Pause, Terminated, OSError, MemoryError, TimeoutError)) or stop_kind(error):
        return True
    if type(error).__module__.startswith(_INFRASTRUCTURE_MODULES):
        return True
    if type(error).__module__ == 'skillopt.execskill.sandbox.client' and type(error).__name__ == '_Lost':
        return True
    trace = error.__traceback__
    while trace is not None:
        frame = trace.tb_frame
        module, function = frame.f_globals.get('__name__', ''), frame.f_code.co_name
        if (module in _HARD_MODULES or function in _HARD_FUNCTIONS
                or (module, function) in _HARD_LOCATIONS):
            return True
        if 'canary' in module or 'leakage' in module or 'canary' in function:
            return True
        trace = trace.tb_next
    cause = error.__cause__ or error.__context__
    return cause is not None and _hard(cause, seen)


def _empty():
    return {'configuration': p.MAIN_V10, 'order': [], 'candidates': {}, 'parent_errors': {},
            'candidate_errors': {}, 'events': []}


def read_record(path, kind=None):
    """Load a recovery input entirely outside candidate containment."""
    with arm('system'):
        try:
            value = read_json(path)
            require(isinstance(value, dict), 'A sealed record is a JSON object')
            return p.verified(value, kind) if kind is not None else value
        except (OSError, TypeError, KeyError, AttributeError) as error:
            raise ConfigurationError('Unreadable sealed record: ' + str(path)) from error


def _anchors(root):
    root = safe_path(root)
    paths = sorted(set(root.glob('*/unit.json')) | set(root.glob('*/attempt-*/status.json'))
                   | set(root.glob('*/attempt-*/completed.json')))
    for path in paths:
        value = read_record(path)
        if 'candidate_error_journal' in value:
            yield p.verified(value)['candidate_error_journal']


def _read(root):
    directory = safe_path(root) / FILE
    paths = sorted(directory.glob('*.json'))
    revisions = {}
    found = _empty()
    previous = None
    for number, path in enumerate(paths, 1):
        found = read_record(path, KIND)
        require(path.name == '%06d.json' % number and found.get('revision') == number
                and found.get('previous_sha256') == previous
                and found.get('configuration') == p.MAIN_V10,
                'Candidate error journal revisions and configuration are sealed')
        require(all(isinstance(found.get(key), dict) for key in ('candidates', 'parent_errors', 'candidate_errors'))
                and all(isinstance(found.get(key), list) for key in ('events', 'order')),
                'Candidate error journal state has its registered shape')
        previous = found[p.RECORD_HASH]
        revisions[number] = found
    for anchor in _anchors(root):
        require(isinstance(anchor, dict) and type(anchor.get('revision')) is int
                and {'record_sha256', 'candidate_errors'} <= set(anchor),
                'Candidate error journal anchor has its registered shape')
        revision = anchor['revision']
        require((revision == 0 and anchor['record_sha256'] is None) or
                revision in revisions and revisions[revision][p.RECORD_HASH] == anchor['record_sha256'],
                'Candidate error journal must reach every anchored revision')
        require(anchor['candidate_errors'] == (revisions[revision]['candidate_errors'] if revision else {}),
                'Candidate error journal anchor counts agree')
    state = {key: deepcopy(value) for key, value in found.items()
            if key not in ('version', 'evidence', p.RECORD_HASH, 'revision', 'previous_sha256')}
    completed = safe_path(root) / 'step.json'
    if completed.exists():
        value = read_record(completed, 'step')
        require(value.get('candidate_errors', {}) == state['candidate_errors'],
                'Completed step candidate error counts agree with the journal and unit anchors')
    for path in safe_path(root).glob('*/unit.json'):
        value = read_record(path, 'unit')
        result = value.get('result', {})
        require(isinstance(result, dict), 'A completed unit carries a result object')
        event = result.get('candidate_error')
        require(event is None or event in state['events'],
                'Completed unit candidate error counts agree with the journal')
    return state


def snapshot(root):
    state = _read(root)
    paths = sorted((safe_path(root) / FILE).glob('*.json'))
    head = read_record(paths[-1], KIND) if paths else None
    return {'revision': len(paths), 'record_sha256': head[p.RECORD_HASH] if head else None,
            'candidate_errors': state['candidate_errors']}


def _write(root, state, evidence):
    from skillopt.coevo5.cells import exclusive
    directory = safe_path(root) / FILE
    with exclusive(directory / '.lock', wait=True):
        paths = sorted(directory.glob('*.json'))
        previous = read_record(paths[-1], KIND)[p.RECORD_HASH] if paths else None
        revision = len(paths) + 1
        write_json(directory / ('%06d.json' % revision), p.record(KIND, evidence,
            {**state, 'revision': revision, 'previous_sha256': previous}))


def discard_if_empty(st, key, result):
    """A proposal-free engineer response is not an intervening candidate."""
    if (not p.is_v226(p.configuration_of(st.setting)) or not isinstance(result, (tuple, list))
            or len(result) != 2 or result[0] is not None or not isinstance(result[1], dict)
            or result[1].get('changes') != []):
        return result
    state = _read(st.root)
    if state['candidates'].get(key, {}).get('status') == 'evaluating':
        state['order'].remove(key)
        del state['candidates'][key]
        _write(st.root, state, st.evidence)
    return result


def counts(root):
    """Counts by exception/location signature for a single step directory."""
    return _read(root)['candidate_errors']


def events(root):
    """Safe event records only; no exception text, traceback or item identities."""
    return _read(root)['events']


@dataclass
class _Evaluation:
    root: object
    evidence: str
    key: str
    parent: object
    excluded: list = field(default_factory=list)

    def parent_error(self, error):
        self.excluded.append(error)
        state = _read(self.root)
        found = signature(_event(error))
        # A failed parent is never contained. Retain the signature if an owner
        # later resumes this step and another candidate exposes the same bug.
        state['parent_errors'][found] = True
        _write(self.root, state, self.evidence)


@contextmanager
def arm(role):
    """Mark parent or system operations inside the current candidate boundary."""
    require(role in _ROLES, 'A registered candidate evaluation role')
    current = _CURRENT.get()
    try:
        yield
    except Exception as error:
        if current is not None:
            if role in _PARENT_ROLES:
                current.parent_error(error)
            elif role == 'system':
                current.excluded.append(error)
        raise


@contextmanager
def package_arm(package):
    """Identify incumbent workers, including solo replays of inherited procedures."""
    current = _CURRENT.get()
    if current is None:
        yield
        return
    parent = current.parent
    same = parent is not None and package.sha256 == parent.sha256
    if not same and parent is not None and package.step == 'replay' and package.procedures:
        same = {proc.sha256 for proc in package.procedures} <= {proc.sha256 for proc in parent.procedures}
    with arm('parent' if same else 'candidate'):
        yield


def _previous_errors(st):
    errors = set()
    chain = getattr(st, 'chain_root', None)
    if chain is not None:
        for path in safe_path(chain).glob('s*-*/step.json'):
            number = int(path.parent.name.split('-', 1)[0][1:])
            if number < st.k:
                value = read_record(path, 'step')
                # Validate the completed step against its journal and unit receipts.
                errors.update(_read(path.parent)['candidate_errors'])
                errors.update(value.get('candidate_errors', {}))
    return errors


def guard(st, key, parent, work, rejected):
    """Wrap one phase of a candidate; all phases of that candidate share ``key``.

The first occurrence rejects only that candidate. A matching signature in the
any earlier candidate or step, or any incumbent evaluation, is systematic and
is raised unchanged. Repeated phases/resumes of a contained candidate reuse its
safe event without running candidate code or incrementing the count again.
    """
    if not p.is_v226(p.configuration_of(st.setting)):
        return work

    def wrapped(attempt):
        require(isinstance(key, str) and key, 'A candidate evaluation has a stable step-local key')
        state = _read(st.root)
        previous_errors = _previous_errors(st)
        if key not in state['candidates']:
            state['order'].append(key)
            state['candidates'][key] = {'status': 'evaluating'}
            _write(st.root, state, st.evidence)
        previous = state['candidates'][key]
        if previous['status'] == 'contained':
            return rejected(deepcopy(previous['event']))
        current = _Evaluation(st.root, st.evidence, key, parent)
        token = _CURRENT.set(current)
        try:
            result = work(attempt)
        except Exception as error:
            if any(error is marked for marked in current.excluded) or _hard(error):
                raise
            event = _event(error)
            found = signature(event)
            state = _read(st.root)
            position = state['order'].index(key)
            prior = [state['candidates'][other].get('event') for other in state['order'][:position]]
            systematic = (found in state['parent_errors'] or found in previous_errors
                          or any(event is not None and signature(event) == found for event in prior))
            old = state['candidates'][key]
            # An owner retry of a systematic candidate remains one candidate
            # event, even if several interrupted attempts encounter the bug.
            if 'event' not in old:
                state['events'].append(event)
                state['candidate_errors'][found] = state['candidate_errors'].get(found, 0) + 1
            else:
                require(old['event'] == event, 'A repeated failed candidate retains its error signature')
            state['candidates'][key] = {'status': 'systematic' if systematic else 'contained', 'event': event}
            _write(st.root, state, st.evidence)
            if systematic:
                raise
            return rejected(deepcopy(event))
        else:
            return discard_if_empty(st, key, result)
        finally:
            _CURRENT.reset(token)
    return wrapped
