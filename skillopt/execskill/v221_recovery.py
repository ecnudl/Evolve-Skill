"""One persistent, explicitly classified infrastructure redo for main-v7 only.

No owner recovery is fabricated. The automatic record is a separate authorization,
and the elapsed-time check also applies when the runner resumes after interruption.
"""
from __future__ import annotations

from datetime import datetime, timezone
import errno
import json
from pathlib import Path
import time

from skillopt.coevo5.cells import exclusive
from skillopt.coevo5.evaluation import _next_attempt, attempts
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from .cells import Pause
from .errors import CleanupUnconfirmed, SandboxUnavailable
from . import profiles as p

WAIT_SECONDS = 60
FILE = 'auto-recovery.json'
FIELDS = {'by', 'kind', 'reason', 'attempt', 'at'}
REASONS = {
    'container_cleanup_unconfirmed': 'The unit container cleanup is unconfirmed.',
    'storage_exhausted': 'The filesystem reported ENOSPC or exhausted inodes.',
    'docker_start_failure': 'The Docker worker failed to start.',
    'client_pool_timeout_zero_sockets': 'The client pool timed out with an explicit zero-socket observation.',
}


def pause_kind(kind, reason):
    """Recognize explicit pure categories; generic infrastructure/transport is not enough."""
    if kind in REASONS:
        return kind
    if kind == 'cleanup' and (reason == 'CleanupUnconfirmed' or reason == 'unit_drain'
            or str(reason).startswith(('sandbox cleanup unconfirmed', 'sandbox containers remain',
                                       'unit_drain: ', 'the docker client of a removed sandbox'))):
        return 'container_cleanup_unconfirmed'
    if kind in ('enospc', 'inode_exhausted'):
        return 'storage_exhausted'
    if kind == 'sandbox' and str(reason).startswith('sandbox_start_failed:'):
        return 'docker_start_failure'
    return None


def _one(error):
    if isinstance(error, Pause):
        return pause_kind(error.kind, error.reason) if getattr(error, 'auto_retry_eligible', True) else None
    if isinstance(error, CleanupUnconfirmed):
        return 'container_cleanup_unconfirmed'
    if isinstance(error, OSError) and error.errno == errno.ENOSPC:
        return 'storage_exhausted'
    if isinstance(error, SandboxUnavailable) and str(error).startswith('sandbox_start_failed:'):
        return 'docker_start_failure'
    # A timeout alone does not establish the requested zero-socket condition.
    if (type(error).__name__ == 'PoolTimeout' and type(getattr(error, 'socket_count', None)) is int
            and error.socket_count == 0):
        return 'client_pool_timeout_zero_sockets'
    return None


def exception_pause(error):
    """Safe canonical fields, only if every active cause/context is pure infrastructure."""
    kind = _one(error)
    if kind is None:
        return None
    seen = {id(error)}
    cause = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        if _one(cause) is None:
            return None
        cause = cause.__cause__ or (None if cause.__suppress_context__ else cause.__context__)
    return {'kind': kind, 'reason': REASONS[kind]}


def _checked(attempt):
    path = attempt / FILE
    if not path.exists():
        return None
    value = read_json(path)
    require(isinstance(value, dict) and set(value) == FIELDS and value['by'] == 'system'
            and value['kind'] in REASONS and value['reason'] == REASONS[value['kind']]
            and value['attempt'] == attempt.name, 'Invalid main-v7 automatic recovery record')
    at = datetime.fromisoformat(value['at'])
    require(at.tzinfo is not None, 'Automatic recovery uses a timezone-aware timestamp')
    status = p.verified(read_json(attempt / 'status.json'), 'unit-status')
    require(status.get('status') == 'paused' and status.get('auto_retry_eligible', True)
            and pause_kind(status.get('kind'), status.get('reason')) == value['kind'],
            'Automatic recovery must name its own pure infrastructure pause')
    return value


def next_attempt(root):
    """Owner recovery remains valid; only an exact main-v7 automatic record adds permission."""
    found = _next_attempt(root)
    if found is not None:
        return found
    prior = attempts(root)
    if prior and _checked(prior[-1]) is not None:
        return safe_path(root) / ('attempt-%d' % (int(prior[-1].name.split('-')[1]) + 1))
    return None


def wait_pending(root, *, clock=None, sleep=None, run=None, identity=None):
    """A restarted process observes the remainder of the same fixed 60-second wait."""
    clock, sleep = clock or time.time, sleep or time.sleep
    prior = attempts(root)
    if not prior:
        return
    value = _checked(prior[-1])
    if value is not None:
        started = p.verified(read_json(prior[-1] / 'started.json'), 'unit-started')
        if run is not None or identity is not None:
            require(started.get('run') == run and started.get('identity') == identity,
                    'Automatic recovery resumes only the same unit and run')
        _log(safe_path(root), started['identity'], value,
             initiating_chain=started.get('initiating_chain'))
        at = datetime.fromisoformat(value['at']).timestamp()
        remaining = max(0.0, at + WAIT_SECONDS - clock())
        if remaining:
            sleep(remaining)


def records(root):
    """Public pause metadata only, for step and chain records; no cell/result data."""
    root = safe_path(root)
    return [{'unit': p.verified(read_json(path.parent / 'started.json'), 'unit-started')['identity']['unit'],
             'path': str(path.relative_to(root)), **_checked(path.parent)}
            for path in sorted(root.rglob(FILE))]


def _chain_root(root, identity, *, initiating_chain=None):
    parts = Path(identity['unit']).parts
    if parts and parts[0] in p.CHAINS and tuple(root.parts[-len(parts):]) == parts:
        return root.parents[len(parts) - 2] if len(parts) > 1 else root
    if (len(root.parts) >= 3 and root.parts[-3:-1] == ('shared', 'test')
            and initiating_chain in p.CHAINS):
        return root.parents[2] / initiating_chain
    return None


def _log(root, identity, value, *, initiating_chain=None):
    chain_root = _chain_root(root, identity, initiating_chain=initiating_chain)
    if chain_root is not None:
        path = chain_root / 'auto-recovery.jsonl'
        row = {'unit': identity['unit'], 'path': str(root / value['attempt'] / FILE), **value,
               **({'initiating_chain': initiating_chain} if initiating_chain is not None else {})}
        with exclusive(chain_root / '.auto-recovery.lock', wait=True):
            old = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
            encoded = json.dumps(row, sort_keys=True, ensure_ascii=False)
            if encoded not in old:
                with path.open('a', encoding='utf-8') as stream:
                    stream.write(encoded + '\n')


def authorize(root, *, run, identity, clock=None):
    """Authorize at most one automatic redo over the lifetime of this unit."""
    root = safe_path(root)
    with exclusive(root / '.lock'):
        prior = attempts(root)
        if not prior or any((a / FILE).exists() for a in prior):
            return False
        attempt = prior[-1]
        path = attempt / 'status.json'
        if not path.exists():
            return False
        status = p.verified(read_json(path), 'unit-status')
        kind = pause_kind(status.get('kind'), status.get('reason'))
        if status.get('status') != 'paused' or not status.get('auto_retry_eligible', True) or kind is None:
            return False
        started = p.verified(read_json(attempt / 'started.json'), 'unit-started')
        require(started.get('run') == run and started.get('identity') == identity,
                'Automatic recovery is bound to the same unit and run')
        value = {'by': 'system', 'kind': kind, 'reason': REASONS[kind], 'attempt': attempt.name,
                 'at': datetime.fromtimestamp((clock or time.time)(), timezone.utc).isoformat()}
        write_json(attempt / FILE, value)
        _log(root, identity, value, initiating_chain=started.get('initiating_chain'))
        return True


def run_unit(root, *, execute, clock=None, sleep=None, **kwargs):
    """The actual main-v7 runner; authored smoke injects only the clock and sleeper."""
    while True:
        wait_pending(root, clock=clock, sleep=sleep, run=kwargs['run'], identity=kwargs['identity'])
        try:
            return execute(root, **kwargs)
        except Pause:
            if not authorize(root, run=kwargs['run'], identity=kwargs['identity'], clock=clock):
                raise


def process_socket_count():
    """Observe only the current process, only after a pure PoolTimeout receipt.

    Addresses and socket details are discarded. Missing permission/dependency is
    unknown, which never authorizes the automatic retry.
    """
    try:
        import psutil
    except ImportError:
        return None
    try:
        return len(psutil.Process().net_connections(kind='all'))
    except (psutil.Error, OSError):
        return None


def pure_pool_timeout(receipt):
    attempts_ = receipt.get('attempts') if isinstance(receipt, dict) else None
    return (isinstance(receipt, dict) and receipt.get('ok') is False
            and receipt.get('error_type') == 'transport' and receipt.get('response') is None
            and receipt.get('finish_reason') is None and not receipt.get('usage')
            and isinstance(attempts_, list) and bool(attempts_)
            and all(isinstance(row, dict) and row.get('error') == 'PoolTimeout'
                    and row.get('status') is None for row in attempts_))


from skillopt.coevo5.calls import Endpoint as FrozenEndpoint


class Endpoint(FrozenEndpoint):
    """main-v7 only: settle the ordinary receipt before a proven zero-socket pause."""
    def send(self, system, user, recorder):
        receipt = super().send(system, user, recorder)
        if pure_pool_timeout(receipt):
            sockets = process_socket_count()
            recorder.sends[-1]['infrastructure_observation'] = {
                'kind': 'client_pool_timeout', 'socket_count': sockets,
                'zero_sockets_confirmed': type(sockets) is int and sockets == 0}
            if type(sockets) is int and sockets == 0:
                kind = 'client_pool_timeout_zero_sockets'
                raise Pause(kind, REASONS[kind], recorder.label)
        return receipt
