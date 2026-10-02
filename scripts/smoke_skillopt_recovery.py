"""Small real native-optimizer checks; NOT a benchmark-effect experiment.

Select two train and two selection families by hash, without consulting old
scores. Keep the old study untouched; freeze a v4 manifest in a new directory.
ALFWorld initialization and workbook compatibility have separate native smokes.
"""
from __future__ import annotations

import argparse
import fcntl
from copy import deepcopy

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.continual_learning.contracts import RECOVERY_VERSION, manifest
from skillopt.continual_learning.launch import learning_environment
from skillopt.continual_learning.recovery import POLICY
from skillopt.continual_learning.skillopt import run_stage
from skillopt.validator_pilot.api import digest


def small_panel(panel, roles):
    selected, groups = [], []
    for role in ('train', 'selection'):
        families = sorted(roles[role], key=lambda name: digest(['recovery-smoke-v1', name]))[:2]
        require(len(families) == 2, 'Smoke needs two distinct families per role')
        groups.append(families)
        for family in families:
            tasks = sorted((t for t in panel['tasks'] if t['family_id'] == family), key=digest)
            require(tasks, 'Missing smoke task family')
            selected.append(deepcopy(tasks[0]))
    require(not set(groups[0]) & set(groups[1]), 'Smoke roles overlap')
    return {**deepcopy(panel), 'tasks': selected}, groups


def run(study, output, repo, benchmarks):
    prior = read_json(safe_path(study) / 'protocol.json', sealed=True)
    root = safe_path(output)
    require(not root.exists(), 'A new smoke directory is required')
    results = []
    with output_lock(root), safe_path(prior['config']['native_lock']).open('a') as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        for benchmark in benchmarks:
            require(benchmark in {'bigcodebench', 'searchqa', 'korbench'}, 'Unsupported smoke domain')
            role = prior['roles'][benchmark]
            panel, groups = small_panel(read_json(role['path']), role)
            model = deepcopy(prior['model'])
            model['transport']['stream_wall_seconds'] = 3600
            budget = {**prior['config']['budget'], 'max_iterations': 1, 'minibatch_size': 2,
                      'max_metric_calls': 16, 'max_reflection_calls': 12,
                      'max_api_calls': 40, 'max_reported_tokens': 1500000}
            value = manifest(panel, train_families=groups[0], selection_families=groups[1],
                             model=model, budget=budget, runtime=role['runtime'], seed=20261002,
                             method='skillopt', version=RECOVERY_VERSION, recovery_policy=POLICY)
            target = root / benchmark
            write_json(target / 'manifest.json', value)
            write_json(target / 'panel.json', panel)
            with learning_environment(value):
                result = run_stage(value, panel, target / 'learning', repo=repo)
            summary = seal({'benchmark': benchmark, 'status': result['status'], 'reason': result['reason'],
                            'costs': result['costs'], 'learning_result_hash': result['record_hash'],
                            'train_tasks': 2, 'selection_tasks': 2,
                            'steps': len(result.get('steps', [])),
                            'candidate_nonempty': bool(result['candidate_skill']),
                            'evidence_kind': 'real_model_engineering_smoke_not_method_effect',
                            'accuracy_improvement_claimed': False, 'historical_records_modified': False})
            write_json(target / 'summary.json', summary)
            print({k: summary[k] for k in ('benchmark', 'status', 'reason', 'costs')}, flush=True)
            results.append(summary)
        final = seal({'version': 'skillopt-recovery-smoke-v1', 'results': results,
                      'completed_domains': sum(x['status'] == 'completed' for x in results),
                      'attempted_domains': len(results), 'method_effect_claimed': False})
        write_json(root / 'result.json', final)
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--benchmarks', nargs='+', choices=('bigcodebench', 'searchqa', 'korbench'),
                        default=['bigcodebench', 'searchqa', 'korbench'])
    args = parser.parse_args()
    require(len(args.benchmarks) == len(set(args.benchmarks)), 'Duplicate smoke domain')
    result = run(args.study, args.output, args.repo, args.benchmarks)
    return 0 if result['completed_domains'] == result['attempted_domains'] else 3


if __name__ == '__main__':
    raise SystemExit(main())
