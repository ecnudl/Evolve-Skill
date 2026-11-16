"""Run one fake typed chain, or one default prepare, in a given source tree and dump what it wrote: the helper of
``tests/test_typed3_item_stage_guarantees.py``, which compares the integrated tree with a ``git archive`` export of the
base commit (Codex review of P2b, finding 5). It imports only modules both trees have and is run as a script, once per
tree, so the two runs never share a module:

    python3 tests/typed3_base_runner.py TREE chain ROOT OUT SCENARIO VARIANT
    python3 tests/typed3_base_runner.py TREE prepare PARENT OUT

``chain``: the scenario ``SCENARIO`` of ``tests/test_typed2_shared.py`` (``SINGLE``: 'smoke' or 'default'; five benches,
the REAL mount, writers and reads) through that file's ``real_run``; ``VARIANT`` 'absent' runs the synthetic manifest
as it is (no typed-v3 option field), 'explicit' adds the option fields a default prepare of TREE seals (decision B6 (c):
``program_learning`` 'single' and ``archive`` {}; where TREE has the item stage, ``item_stage`` 'none' and
``item_quotas`` None). OUT receives every file under ROOT (JSON parsed, any other file by its sha256), every request of
the script (purpose, unit, system, user) and the end state. ``prepare``: a default smoke prepare under PARENT with the
fixture inputs of ``tests/test_typed_reads.py``; OUT receives the sealed manifest. Both modes report the tree's version
and evidence labels. The wall clock is frozen (``time.strftime`` without a time tuple formats one fixed instant), so
records that hash a time stamp are comparable across runs.
"""
import hashlib
import json
import os
import sys
import time

FIXED_TIME = time.struct_time((2026, 11, 15, 0, 0, 0, 6, 319, 0))


def freeze_clock():
    strftime = time.strftime

    def frozen(fmt, t=None):
        return strftime(fmt, FIXED_TIME if t is None else t)
    time.strftime = frozen


def with_explicit_defaults(manifest, typed):
    """The option fields a default prepare of this tree seals (B6 (c)), added to a synthetic manifest."""
    fields = {'program_learning': typed.PROGRAM_LEARNING_DEFAULT, 'archive': {}}
    if hasattr(typed, 'ITEM_STAGES'):
        fields.update(item_stage=typed.ITEM_STAGE_DEFAULT, item_quotas=None)
    return {**manifest, **fields}


def run_chain(root, scenario, variant):
    from skillopt.execskill import typed
    from skillopt.execskill.typed import smoke
    from tests import test_typed2_shared as shared
    if variant == 'explicit':
        synthetic = smoke.synthetic_manifest
        smoke.synthetic_manifest = lambda **kw: with_explicit_defaults(synthetic(**kw), typed)
    else:
        assert variant == 'absent', variant
    limits, outcomes = shared.SINGLE[scenario]
    state, script, _ = shared.real_run(root, limits=limits, outcomes=outcomes)
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            data = path.read_bytes()
            try:
                files[path.relative_to(root).as_posix()] = {'json': json.loads(data.decode('utf-8'))}
            except ValueError:
                files[path.relative_to(root).as_posix()] = {'sha256': hashlib.sha256(data).hexdigest()}
    return {'complete': state['complete'], 'paused': state['paused'], 'state': state, 'files': files,
            'requests': [list(request) for request in script.requests]}


def run_prepare(parent):
    from skillopt.execskill import zebralogic
    from skillopt.execskill.typed import prepare
    from tests.test_typed_reads import write_machinery, write_pools, write_tree, zebra_rows
    zebralogic.load_pool = lambda *a, **k: zebra_rows()
    parent.mkdir(parents=True, exist_ok=True)
    machinery = parent / 'machinery.json'
    write_machinery(machinery)
    made = prepare.prepare(parent / 'execskill-20261112-typed-v3-smoke', machinery_manifest=machinery,
                           roles_repo='/root/roles', pools_root=write_pools(parent), smoke=True,
                           typed_tree=write_tree(parent), root_parent=str(parent))
    return {'manifest': made}


def main(argv):
    tree, mode, root, out = argv[:4]
    sys.path[0] = tree  # the tree's packages first, never this file's directory
    os.chdir(tree)
    freeze_clock()
    from pathlib import Path
    import skillopt
    import tests
    for module in (skillopt, tests):  # the packages of TREE, whatever else is on the path
        assert Path(module.__file__).resolve().is_relative_to(Path(tree).resolve()), module.__file__
    from skillopt.execskill import typed
    found = {'labels': {'version': typed.VERSION, 'evidence': dict(typed.EVIDENCE)}}
    if mode == 'chain':
        found.update(run_chain(Path(root), *argv[4:6]))
    else:
        assert mode == 'prepare', mode
        found.update(run_prepare(Path(root)))
    Path(out).write_text(json.dumps(found, sort_keys=True))


if __name__ == '__main__':
    main(sys.argv[1:])
