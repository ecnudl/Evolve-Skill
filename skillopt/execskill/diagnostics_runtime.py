"""Opt-in host transport for the engineer-only diagnostic channel."""
from __future__ import annotations

import hashlib

from skillopt.validator_pilot.api import digest

from . import diagnostics


def worker_call(worker, procedure, hook, args, *, timeout_s, configuration=None, bench='zebralogic'):
    """Real workers bound before output limits; authored workers may return plain values."""
    child = diagnostics.enabled(configuration) and hook == 'before_call'
    method = getattr(worker, 'call_diagnostics', None) if child else None
    if method is not None:
        return method(procedure, hook, args, timeout_s=timeout_s, bench=bench)
    return worker.call(procedure, hook, args, timeout_s=timeout_s)


def capture(result, *, configuration=None, bench='zebralogic', hook='before_call', procedure):
    """Clean result identity and a separately sealed record; never create solver faults."""
    if not diagnostics.enabled(configuration) or hook != 'before_call':
        return result, None
    source_sha = hashlib.sha256(procedure.source.encode()).hexdigest()
    if 'diagnostics' in result:
        report = diagnostics.safe_verified_record(result['diagnostics'], bench=bench)
        report = diagnostics._seal({**report, 'hook': hook, 'procedure': procedure.id,
                                    'source_sha256': source_sha})
        value = result.get('value')
    elif result.get('ok') is True:
        value, report = diagnostics.extract(result['value'], configuration=configuration, bench=bench,
            hook=hook, procedure=procedure.id, source_sha256=source_sha)
    else:
        return result, None
    clean = {key: value for key, value in result.items() if key != 'diagnostics'}
    if result.get('ok') is True:
        clean.update(value=value, value_sha256=digest(value))
    return clean, report
