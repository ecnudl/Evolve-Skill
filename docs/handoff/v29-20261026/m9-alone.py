#!/usr/bin/env python3
"""Inspect operator process listings without exposing arguments or credentials.

The Linux pre-suite template owns a shared cooperative machine lock as well.
This scan catches pre-existing drivers that do not participate in that lock;
the operator's explicit ALONE confirmation remains mandatory.
"""
import ast
import json
import os
from pathlib import PurePath
import re
import shlex
import subprocess

EXEC_COMMANDS = {'run', 'evaluate', 'evaluate-unit', 'step-unit', 'first-call',
                 'v214-smoke-run', 'v211-smoke-run', 'v210-smoke-run', 'smoke-run'}
EXPERIMENT_DRIVERS = {'run_coevo5.py', 'run_continual_learning.py', 'weak_solver_probe.py',
                      'run_weak_solver_probe.py', 'evaluate_fivebench_test.py',
                      'run_test_eval_f_linux.sh', 'run_remeasure_f_linux.sh', 'run_long_baselines_linux.sh'}
EXPERIMENT_PREFIXES = ('run_fivebench_', 'run_skillopt_generalization_', 'run_generalization_feedback_')


def _python_cli_import(code):
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return False
    return any(isinstance(node, (ast.Import, ast.ImportFrom)) and
               any(alias.name.split('.')[-1] == 'run_execskill' for alias in node.names)
               for node in ast.walk(tree))


def active_driver(comm, command):
    try:
        args = shlex.split(command)
    except ValueError:
        # ps does not preserve shell quoting; whitespace still preserves entrypoint names.
        args = command.split()
    names = [PurePath(arg).name for arg in args]
    executable = PurePath(comm).name
    python = any(re.fullmatch(r'(?:python|pypy)(?:\d+(?:\.\d+)*)?', name)
                 for name in [executable, *names[:1]])
    shell = any(name in ('bash', 'sh', 'zsh', 'dash') for name in [executable, *names[:1]])
    entrypoints = [executable, *names[:1]]
    if python and '-c' not in args and '-m' not in args:
        options_with_values = {'-W', '-X'}
        skip = False
        for token in args[1:]:
            if skip:
                skip = False
                continue
            if token in options_with_values:
                skip = True
                continue
            if token.startswith('-'):
                continue
            entrypoints.append(PurePath(token).name)
            break
    if any(re.fullmatch(r'(?:pytest|py\.test)(?:-\d+(?:\.\d+)*)?', name) for name in entrypoints):
        return 'pytest'
    if python and any(args[i:i+2] == ['-m', 'pytest'] for i in range(len(args)-1)):
        return 'pytest'
    if not (python or shell or any(name in EXPERIMENT_DRIVERS or name.startswith(EXPERIMENT_PREFIXES)
                                  or name == 'run_execskill.py' for name in names[:1])):
        return None
    execskill = 'run_execskill.py' in names or 'scripts.run_execskill' in args
    if '-c' in args:
        index = args.index('-c')
        execskill |= index+1 < len(args) and (_python_cli_import(args[index+1])
            or re.search(r'\b(?:from scripts import run_execskill|import scripts\.run_execskill)\b', command) is not None)
    if execskill and any(arg in EXEC_COMMANDS or arg.endswith('-smoke-run') for arg in args):
        return 'execskill experiment/read'
    for name in names:
        if name in EXPERIMENT_DRIVERS or name.startswith(EXPERIMENT_PREFIXES):
            return name
        if re.fullmatch(r'm\d+-(?:run|smoke|launch|go)\.sh', name):
            return name
        if re.fullmatch(r'run-v\d+-pre\.sh', name):
            return name
    return None


def active_processes(text, *, own_pid):
    """Return non-ancestor active drivers from `ps -eo pid=,ppid=,comm=,args=`."""
    rows = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        pid, parent, comm, args = line.split(None, 3)
        rows[int(pid)] = (int(parent), comm, args)
    ancestors, pid = set(), own_pid
    while pid and pid not in ancestors:
        ancestors.add(pid)
        pid = rows[pid][0] if pid in rows else 0
    found = []
    for pid, (_, comm, args) in rows.items():
        if pid in ancestors:
            continue
        driver = active_driver(comm, args)
        if driver:
            found.append({'pid': pid, 'driver': driver})
    return found


def main():
    text = subprocess.check_output(['ps', '-eo', 'pid=,ppid=,comm=,args='], text=True)
    active = active_processes(text, own_pid=os.getpid())
    if active:
        raise SystemExit('Active suite/read/experiment: keep this full suite alone: ' + json.dumps(active))
    print('{"passed":true,"exit_code":0,"active_drivers":0}')


if __name__ == '__main__':
    main()
