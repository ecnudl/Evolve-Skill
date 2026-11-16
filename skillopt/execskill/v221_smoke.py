"""main-v7's extra SX mechanisms on authored fixtures, without model or data access."""
from __future__ import annotations

from datetime import datetime

from skillopt.coevo5.evaluation import attempts
from skillopt.continual_eval.core import read_json, require, safe_path
from . import profiles as p, units, v221_recovery
from .cells import Pause


def recovery_demo(root):
    """Exercise the production unit runner with a simulated clock, never a real wait."""
    root = safe_path(root)
    identity = {'unit': 'G/s1-searchqa/authored-retry', 'chain': 'G', 'k': 1}
    unit = root / identity['unit']
    clock = {'now': 1000.0}
    def sleep(seconds):
        clock['now'] += seconds
    def work(attempt):
        if attempt.name == 'attempt-1':
            raise Pause('container_cleanup_unconfirmed', 'Authored cleanup stop.', identity['unit'])
        return {'completed_at': clock['now'], 'model_calls': 0}
    result = v221_recovery.run_unit(unit, execute=units._run_unit, run='authored-v221-SX',
        identity=identity, work=work, evidence='engineering_fixture', configuration=p.MAIN_V7,
        clock=lambda: clock['now'], sleep=sleep)
    auto = read_json(unit / 'attempt-1' / v221_recovery.FILE)
    elapsed = result['result']['completed_at'] - datetime.fromisoformat(auto['at']).timestamp()
    return {'passed': result['status'] == 'complete' and result['attempt'] == 'attempt-2'
            and elapsed == v221_recovery.WAIT_SECONDS and len(result['automatic_retries']) == 1,
        'attempts': [a.name for a in attempts(unit)], 'elapsed_seconds': elapsed,
        'wait_clock': 'authored_simulated_clock', 'recovery': auto,
        'unit_record_sha256': result[p.RECORD_HASH], 'model_calls': 0, 'sealed_reads': 0}


def structural_smoke(root):
    """Retain main-v6's SX checks and add every main-v7 mechanism required by the brief."""
    from . import v214_stages, v221_learning
    root = safe_path(root)
    inherited = v214_stages.sx(root / 'inherited', configuration=p.MAIN_V6)
    learning = v221_learning.structural_smoke(root / 'learning')
    retry = recovery_demo(root / 'retry')
    value = {'configuration': p.MAIN_V7, 'passed': all(row['passed'] for row in (inherited, learning, retry)),
             'inherited': inherited, 'learning': learning, 'automatic_retry': retry,
             'model_calls': 0, 'sealed_reads': 0}
    check_result(value)
    return value


def check_result(value):
    """Readiness checks the required mechanism evidence, not merely an SX `passed` bit."""
    require(isinstance(value, dict) and value.get('configuration') == p.MAIN_V7 and value.get('passed') is True
            and value.get('model_calls') == 0 and value.get('sealed_reads') == 0,
            'main-v7 SX is a passed zero-model, zero-panel mechanism exercise')
    inherited, learning, retry = (value.get(key, {}) for key in ('inherited', 'learning', 'automatic_retry'))
    require(inherited.get('passed') is True and inherited.get('configuration') == p.MAIN_V6
            and all(inherited.get(key, {}).get('passed') is True for key in ('stage_rows', 'split', 'read_reuse')),
            'main-v7 SX retains the main-v6 stage, split and request-reuse exercises')
    require(learning.get('passed') is True and learning.get('model_calls') == 0 and learning.get('sealed_reads') == 0,
            'main-v7 SX learning mechanisms run without a model or protected panel')
    from . import v221_rule
    decisions = learning.get('decisions', {})
    require(set(decisions) == {'training', 'confirmation', 'acceptance'}
            and decisions['training'] == decisions['confirmation'] == decisions['acceptance']
            and decisions['training'].get('decision') == 'accept'
            and v221_rule.rule_ok(decisions['training']),
            'main-v7 SX exercises the identical gain-and-no-harm record at all three stages')
    require(all(learning.get(key, {}).get('passed') is True
                for key in ('early_acceptance', 'split_merge', 'audit_non_drop')),
            'main-v7 SX exercises immediate adoption, ordered split merge and audit retention')
    require(retry.get('passed') is True and retry.get('attempts') == ['attempt-1', 'attempt-2']
            and retry.get('elapsed_seconds') == v221_recovery.WAIT_SECONDS
            and retry.get('wait_clock') == 'authored_simulated_clock'
            and retry.get('model_calls') == 0 and retry.get('sealed_reads') == 0
            and retry.get('recovery', {}).get('by') == 'system'
            and retry.get('recovery', {}).get('kind') == 'container_cleanup_unconfirmed',
            'main-v7 SX exercises one recorded infrastructure retry after a simulated 60-second wait')
    return value
