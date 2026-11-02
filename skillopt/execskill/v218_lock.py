"""main-v6 environment-only memory locking and non-authoritative wait receipts."""
from __future__ import annotations

import errno
import fcntl
import functools
import json
import os
import sys
import threading
import time
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

from skillopt.continual_eval.core import require, safe_path

from . import profiles as p

_STATES = {}
_STATES_LOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _state(path):
    # The PID makes an inherited state after fork unusable in its new process.
    key = os.getpid(), str(path)
    with _STATES_LOCK:
        return _STATES.setdefault(key, {'condition': threading.Condition(), 'mode': None,
            'fd': None, 'threads': {}, 'acquiring': False, 'holder': None})


def _best_effort(function):
    try:
        return function()
    except (OSError, ValueError, TypeError):
        return None


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n')


def _append(path, line):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        os.write(fd, (line + '\n').encode())
    finally:
        os.close(fd)


def _holders(path):
    found = []
    for file in sorted(path.parent.glob(path.name + '.holder-*.json')):
        value = _best_effort(lambda file=file: json.loads(file.read_text()))
        if isinstance(value, dict) and {'unit', 'pid', 'mode', 'since'} <= set(value):
            found.append({key: value[key] for key in ('unit', 'pid', 'mode', 'since')})
    return found


def _waiting(setting, chain, unit, mode, requested, holders):
    holder = '; '.join('%s %s %s since %s' % (h['unit'], h['pid'], h['mode'], h['since'])
                       for h in holders) or 'unknown unknown unknown since unknown'
    line = 'waiting for memory-heavy lock %s since %s for %s; holder %s' % (
        mode, requested, unit, holder)
    _best_effort(lambda: _append(safe_path(setting.root) / chain / 'chain.log', line))
    _best_effort(lambda: print(line, file=sys.stderr, flush=True))


@contextmanager
def environment(setting, *benches, unit=None, chain=None):
    """Lock only an actual environment operation, nesting without another flock.

    A mixed operation names all its benches before entering. Shared-to-exclusive
    nesting is refused before any flock, because silently blocking there can
    deadlock. Unrelated threads coordinate locally rather than flocking a file
    already held by this process; shared ALFWorld workers can run together.
    """
    if not p.uses_environment_lock(p.configuration_of(setting)):
        yield
        return
    from .chain import HEAVY_LOCK, heavy_mode
    actual = heavy_mode(benches)
    if actual is None:
        yield
        return
    extra = setting.extra
    # A mixed cell batch declares all its environment benches before dispatch.
    # A non-environment operation above remains free, even in a Sheet step.
    mode = heavy_mode((*benches, *extra.get('memory_lock_benches', ())))
    unit = unit or extra.get('memory_lock_unit')
    chain = chain or extra.get('memory_lock_chain') or (unit or '').split('/')[0]
    require(chain in p.CHAINS and isinstance(unit, str) and unit,
            'A main-v6 environment lock names its chain and unit')
    path = safe_path(extra.get('slot_root', p.SLOT_ROOT)) / HEAVY_LOCK
    path.parent.mkdir(parents=True, exist_ok=True)
    state, thread = _state(path), threading.get_ident()
    condition = state['condition']
    label = 'exclusive' if mode == fcntl.LOCK_EX else 'shared'
    requested, clock = _now(), time.monotonic()
    waited, holders, entered = False, [], False
    holder_file = path.with_name(path.name + '.holder-%s.json' % os.getpid())

    def wait_once():
        nonlocal waited, holders
        if not waited:
            waited, holders = True, _best_effort(lambda: _holders(path)) or []
            _waiting(setting, chain, unit, label, requested, holders)

    with condition:
        if thread in state['threads']:
            require(state['mode'] == fcntl.LOCK_EX or mode == fcntl.LOCK_SH,
                    'A mixed environment operation must request its strongest lock before entering')
            state['threads'][thread] += 1
            entered = True
        else:
            def compatible():
                return (mode == state['mode'] == fcntl.LOCK_SH or
                        state['mode'] == fcntl.LOCK_EX and (state['holder'] or {}).get('unit') == unit)
            while state['acquiring'] or (state['threads'] and not compatible()):
                require(not (state['mode'] == fcntl.LOCK_SH and mode == fcntl.LOCK_EX
                             and (state['holder'] or {}).get('unit') == unit),
                        'A mixed environment operation must request its strongest lock before entering')
                wait_once()
                condition.wait()
            if state['threads']:
                state['threads'][thread] = 1
                entered = True
            else:
                state['acquiring'] = True
    if not entered:
        fd = None
        try:
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, mode | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                wait_once()
                fcntl.flock(fd, mode)
            holder = {'unit': unit, 'pid': os.getpid(), 'mode': label, 'since': _now()}
            _best_effort(lambda: _write(holder_file, holder))
            with condition:
                state.update(fd=fd, mode=mode, acquiring=False, holder=holder)
                state['threads'][thread] = 1
                condition.notify_all()
        except BaseException:
            if fd is not None:
                os.close(fd)
            with condition:
                state['acquiring'] = False
                condition.notify_all()
            raise
    if waited:
        receipt = {'unit': unit, 'mode': label, 'requested': requested, 'acquired': _now(),
                   'waited_seconds': max(0, time.monotonic() - clock), 'holder_at_request': holders}
        _best_effort(lambda: _append(safe_path(setting.root) / chain / 'lock-waits.jsonl',
                                     json.dumps(receipt, sort_keys=True)))
    try:
        yield
    finally:
        with condition:
            state['threads'][thread] -= 1
            if not state['threads'][thread]:
                del state['threads'][thread]
            if not state['threads']:
                # Holder metadata is informational; failure to remove it cannot
                # prevent the real kernel lock from being released.
                _best_effort(lambda: holder_file.unlink(missing_ok=True))
                fd = state['fd']
                state.update(fd=None, mode=None, holder=None)
                os.close(fd)
                condition.notify_all()


def workers(factory, setting):
    """Wrap only workers with a workbook mount, including routing and replays."""
    @contextmanager
    def opened(package, *, inputs_dir=None, **options):
        hold = environment(setting, 'spreadsheetbench') if inputs_dir is not None else nullcontext()
        with hold:
            with factory(package, inputs_dir=inputs_dir, **options) as worker:
                yield worker
    return opened


def call(function, setting, *benches, unit=None, chain=None):
    """Protect one native operation/reset, leaving surrounding role calls free."""
    @functools.wraps(function)
    def protected(*args, **kwargs):
        with environment(setting, *benches, unit=unit, chain=chain):
            return function(*args, **kwargs)
    return protected


def engine(value, setting):
    if value is None:
        return None
    return replace(value, recalc=call(value.recalc, setting, 'spreadsheetbench'),
                   qualify=call(value.qualify, setting, 'spreadsheetbench'))


def preparation(root, name):
    """Pre-chain native measurements log under the preparation output's G directory."""
    setting = SimpleNamespace(root=safe_path(root), extra={'configuration': p.MAIN_V6,
        'memory_lock_chain': 'G', 'memory_lock_unit': 'G/preparation/' + name})
    return environment(setting, 'spreadsheetbench')
