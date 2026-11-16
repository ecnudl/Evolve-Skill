"""typed-v3 decisions on the gate list J, the screen before the gate, the preset (docs/handoff/typed-v3/CHAIN-DECISIONS.md
T7, T2, T9; build brief P3b) -- fakes only (no network, no Docker, no /data, nothing paid).

The chains run through the REAL ``chain.run``, ``mount``, ``writers``, P2a's SearchQA selector and P3a's arithmetic
(``gatestats``); the clients are P2b's scripted ones (``tests.test_typed3_item_stage.Script``). The solve is the smoke's
fake solve with an outcome rule that reads the item, the mount and the cell's repeat (``solve_with``: a gate cell's
repeat r = 1..R comes from its tag, a single-run cell has none), so a test can make the repeats of one item differ.

SearchQA fixture (P2b's, ``tests.test_typed3_item_stage``): learn = items 0..11, the real gate slice R = 12..19; with
B wrong on the year / person / place questions below 32 and right on every other item (``b_like``) the item stage
selects, as P2b worked out by hand, judging attack A = 20 24 21 25 22 26, guard G = 23 27 31 and three calibration
items K (``round_1_calibration``), shown attack 28 29 30 and guard 35 39; the check holds (B 0 of 6 attack, 3 of 3
calibration). So J = R + A + G + K (20 items), E = R + A (14 items) and the screen items A + G (9 items). On J, B is
right in every run on 15, 19, the guard and the calibration items, and wrong in every run elsewhere, unless a test's
rule says otherwise. Every expected value below is worked out by hand from these counts (R = 3, a = 3, c = 2):

    se = (100 / (R n)) sqrt(2 Q / (R - 1)) = (100 / (3 n)) sqrt(Q),   tau = max(3, 2 se),   gain = 100 D / (3 n).
"""
import json
import math
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from scripts import run_typed
from skillopt.execskill import typed as typed_
from skillopt.execskill.typed import archives, chain, gates, library as library_, prepare, readout, readplan, smoke
from skillopt.execskill.typed import units, writers
from tests import test_typed3_item_stage as stage
from tests.test_typed3_item_stage import QUOTAS, ROUND_1, index, markers, round_1_calibration, sq_id, strict
from tests.test_typed_chain import recovery
from tests.test_typed_schedule import inputs  # noqa: F401 -- prepare's fixture (pools, machinery record, typed tree)

NEUTRAL = Path('/tmp/typed3-p3b-neutral').resolve()  # resolved: route B's safe_path refuses a symlink in any parent
NOW = '2026-11-15T00:00:00'
R = 3
REAL = list(range(12, 20))
A, G = ROUND_1['judging_attack'], ROUND_1['judging_guard']


class Kill(BaseException):
    """A process death in the middle of a step: no ``Exception``, so ``chain.run`` records no pause and nothing after
    it runs (the test then resumes with the owner's recovery, as after a real kill)."""


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='gate3-', dir=NEUTRAL))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


# ---- the fake solve and the outcome rules ---------------------------------------------------------------------------
def solve_with(rule, fires=None):
    """``smoke.fake_solve``'s record shape from one scripted send; the outcome is ``rule(bench, item, mounted, repeat)``
    (``repeat``: r of a gate cell ``<arm>#<r>`` read from its tag, None for a single-run cell) and the procedures that
    fire are the enabled ones ``fires(bench, item, procedure)`` admits (all of them by default)."""
    def run(bench, item, mounted, *, call, runtime, worker_factory=None, native=None, nominal_tokens=None, unit, tag,
            scorer_root, mode=None, step=None, episodes=None):
        found = call(mounted.get('system_card') or '', smoke.fake_request(bench, item, mounted))
        repeat = smoke.repeat_of_tag(bench, item['task_id'], mounted.get('arm'), tag)
        enabled = list(mounted.get('enabled') or [])
        token = rule(bench, item, mounted, repeat) if found.get('ok') else 'unknown_' + str(found.get('error_type'))
        reply = found.get('response')
        return {'bench': bench, 'item_id': item['task_id'], 'arm': mounted.get('arm'),
                'mount': {k: v for k, v in mounted.items() if k not in ('enabled', 'card_text', 'system_card')},
                'public_hash': library_.canonical_sha256(item['public']),
                'prediction_status': 'available' if found.get('ok') else 'unknown', 'output_excerpt': (reply or '')[:2000],
                'reply': reply, 'correct': None if token.startswith('unknown') else token == 'pass', 'token': token,
                'official': {'status': token, 'reason': 'scripted'}, 'format': {}, 'flags': [],
                'fired': [p['id'] for p in enabled if fires is None or fires(bench, item, p)], 'faults': [],
                'tokens': call.tokens(), 'sends': call.sends,
                'request_sha256': [s['request_sha256'] for s in call.sends], 'configuration_error': False,
                'infrastructure_unknown': call.infrastructure_unknown(), 'failure': None}
    return run


def b_like(bench, item, mounted, repeat):
    """P2b's ``strict`` without the card's help: every arm is right where B is (a card changes nothing)."""
    return strict(bench, item, {**mounted, 'card_text': None})


def variance(bench, item, mounted, repeat):
    """B right on attack item 20 in run 1 only (S = 1) and on guard items 23, 27 in runs 1 and 2 (S = 2; right in a
    single run); a card fixes attack item 24 in every run and changes nothing else."""
    if bench != 'searchqa':
        return b_like(bench, item, mounted, repeat)
    i = index(item['task_id'])
    if i == 24 and mounted.get('card_text'):
        return 'pass'
    if i == 20:
        return 'pass' if repeat == 1 else 'fail'
    if i in (23, 27):
        return 'fail' if repeat == 3 else 'pass'
    return b_like(bench, item, mounted, repeat)


def harm(bench, item, mounted, repeat):
    """A card fixes attack item 20 and breaks the three guard items (where B is right in every run)."""
    if bench != 'searchqa':
        return b_like(bench, item, mounted, repeat)
    i = index(item['task_id'])
    if mounted.get('card_text') and i == 20:
        return 'pass'
    if mounted.get('card_text') and i in G:
        return 'fail'
    return b_like(bench, item, mounted, repeat)


def calibration_only(bench, item, mounted, repeat):
    """B right on the calibration items in a single run (the item check) and wrong in every gate run; a card right on
    them in every run: the card's whole gain sits on K."""
    if bench == 'searchqa' and index(item['task_id']) in round_1_calibration():
        return 'pass' if mounted.get('card_text') or repeat is None else 'fail'
    return b_like(bench, item, mounted, repeat)


def screen_short(bench, item, mounted, repeat):
    """B (and every arm without a card) right on attack item 20 in gate run 1: b = 9 + 1 on A + G."""
    if bench == 'searchqa' and index(item['task_id']) == 20 and not mounted.get('card_text') and repeat == 1:
        return 'pass'
    return b_like(bench, item, mounted, repeat)


def build(root, script, *, rule=b_like, fires=None, gate_rule='evolution', gate_screen=False, **kw):
    """P2b's fake services of the SearchQA fixture (``tests.test_typed3_item_stage.build``: item stage 'planned' with
    its quota table, one card round unless ``limits`` says otherwise) with this module's solve and the sealed gate rule
    and screen (None leaves the field out of the manifest)."""
    services = stage.build(root, script, **kw)
    services.solve_fn = solve_with(rule, fires)
    for key, value in (('gate_rule', gate_rule), ('gate_screen', gate_screen)):
        if value is not None:
            services.manifest[key] = value
    return services


def run(root, script=None, **kw):
    script = script if script is not None else stage.Script()
    services = build(root, script, **kw)
    return chain.run(root, 'G', services=services, sleep=lambda s: None), services


def read(root, *parts):
    return json.loads(Path(root, 'G', *parts).read_text())


def cells_of(root, unit):
    return [json.loads(p.read_text()) for p in sorted(Path(root, 'G', *unit.split('/'), 'cells').glob('*.json'))]


def J():
    return [sq_id(i) for i in REAL + A + G + round_1_calibration()]


def E():
    return [sq_id(i) for i in REAL + A]


def screened():
    return [sq_id(i) for i in A + G]


def hand(D, Q, n):
    """(gain, se, tau) in points by the module's formulas (R = 3: 2 Q / (R - 1) = Q)."""
    se = 100 / (R * n) * math.sqrt(Q)
    return 100 * D / (R * n), se, max(3.0, 2 * se)


def close(found, expected):
    return abs(found - expected) < 1e-9


# ==== A: the options, prepare, the preset, the CLI, the chain state ====================================================
def test_the_options_their_defaults_and_their_readers():
    assert (typed_.GATE_RULES, typed_.GATE_RULE_DEFAULT) == (('whole', 'evolution'), 'whole')
    assert (typed_.GATE_SCREENS, typed_.GATE_SCREEN_DEFAULT) == ((False, True), False)
    assert (typed_.RESUME_REPLAYS, typed_.RESUME_REPLAY_DEFAULT) == (('off', 'on'), 'off')
    # a typed-v2 style manifest (no field) decides by typed-v2's rules, screens nothing and resumes as typed-v2
    assert (prepare.gate_rule_of({}), prepare.gate_screen_of({}), prepare.resume_replay_of({})) == ('whole', False, 'off')
    planned = {'item_stage': 'planned', 'item_quotas': prepare.default_item_quotas()}
    assert prepare.gate_rule_of({**planned, 'gate_rule': 'evolution'}) == 'evolution'
    assert prepare.gate_screen_of({**planned, 'gate_screen': True}) is True
    assert prepare.resume_replay_of({'resume_replay': 'on'}) == 'on'
    for reader, bad in ((prepare.gate_rule_of, {**planned, 'gate_rule': 'E'}),
                        (prepare.gate_rule_of, {**planned, 'gate_rule': None}),
                        (prepare.gate_rule_of, {'gate_rule': 'evolution'}),        # needs the item stage 'planned'
                        (prepare.gate_screen_of, {**planned, 'gate_screen': 1}),
                        (prepare.gate_screen_of, {**planned, 'gate_screen': 'true'}),
                        (prepare.gate_screen_of, {'gate_screen': True}),           # needs the item stage 'planned'
                        (prepare.resume_replay_of, {'resume_replay': True}),
                        (prepare.resume_replay_of, {'resume_replay': 'yes'}),
                        (prepare.gate_rule_of, None), (prepare.gate_screen_of, None), (prepare.resume_replay_of, None)):
        with pytest.raises(ValueError):
            reader(bad)
    # P3a's arithmetic, re-exported where the chain reads its gates
    from skillopt.execskill.typed import gatestats
    for name in ('EVOLUTION_CARD_REASONS', 'SCREEN_REASONS', 'ITEM_CLASSES', 'EVOLUTION_CLASSES', 'evolution_statistics',
                 'card_decision_evolution', 'screen_decision', 'screen_counts', 'class_gains'):
        assert getattr(gates, name) is getattr(gatestats, name), name
    assert chain.SCREEN_CLASSES == ('attack', 'guard') and set(chain.SCREEN_CLASSES) <= set(gates.ITEM_CLASSES)
    assert set(chain.TYPED_V3_GATE_PAUSES).isdisjoint(chain.GATE_PAUSES)


def test_prepare_seals_the_gate_options_and_a_default_manifest_stays_typed_v2s(inputs):
    parent = inputs['parent']
    common = dict(machinery_manifest=inputs['machinery'], roles_repo='/root/roles', pools_root=inputs['pools'],
                  smoke=True, typed_tree=inputs['tree'], root_parent=str(parent))
    default = prepare.prepare(parent / 'execskill-20261112-typed-v3-smoke', **common)
    # written only when not at their defaults (as the resume replay, B6 d): a default manifest is the one before them
    assert not {'gate_rule', 'gate_screen', 'resume_replay'} & set(default)
    assert (prepare.gate_rule_of(default), prepare.gate_screen_of(default), prepare.resume_replay_of(default)) == (
        'whole', False, 'off')
    made = prepare.prepare(parent / 'execskill-20261113-typed-v3-smoke', item_stage='planned', gate_rule='evolution',
                           gate_screen=True, resume_replay='on', **common)
    assert (made['gate_rule'], made['gate_screen'], made['resume_replay']) == ('evolution', True, 'on')
    assert prepare.load_manifest(made['root']) == made
    assert set(made) - set(default) == {'gate_rule', 'gate_screen', 'resume_replay'} and set(default) <= set(made)
    one = prepare.prepare(parent / 'execskill-20261114-typed-v3-smoke', item_stage='planned', gate_screen=True,
                          **common)   # each field on its own: the screen without the rule on E
    assert 'gate_rule' not in one and one['gate_screen'] is True and 'resume_replay' not in one
    fields = {key: value for key, value in made.items() if key != 'record_sha256'}
    for key, value in (('gate_rule', 'whole'), ('gate_screen', False), ('resume_replay', 'off')):  # the hash covers them
        assert prepare.seal({**fields, key: value})['record_sha256'] != made['record_sha256']
    # refused before anything is written: an unknown value, 'evolution' or the screen without 'planned'
    for n, bad in enumerate(({'gate_rule': 'E', 'item_stage': 'planned'}, {'gate_rule': 'evolution'},
                             {'gate_screen': True}, {'gate_screen': 1, 'item_stage': 'planned'},
                             {'resume_replay': 'yes'}, {'resume_replay': True})):
        new = parent / ('execskill-2026112%d-typed-v3-smoke' % n)
        with pytest.raises(ValueError):
            prepare.prepare(new, **common, **bad)
        assert not new.exists()
    # load_manifest refuses a changed value (re-sealed, so only the field differs); without the fields: the defaults
    root = Path(made['root'])
    for key, value in (('gate_rule', 'E'), ('gate_screen', 'yes'), ('resume_replay', 'never'), ('item_stage', 'none')):
        changed = {**fields, key: value, **({'item_quotas': None} if key == 'item_stage' else {})}
        units.write_json(root / 'manifest.json', prepare.seal(changed))
        with pytest.raises(ValueError):
            prepare.load_manifest(root)
    units.write_json(root / 'manifest.json', prepare.seal({key: value for key, value in fields.items()
                                                           if key not in ('gate_rule', 'gate_screen', 'resume_replay')}))
    loaded = prepare.load_manifest(root)
    assert (prepare.gate_rule_of(loaded), prepare.gate_screen_of(loaded), prepare.resume_replay_of(loaded)) == (
        'whole', False, 'off')


PRESET_FIELDS = {'base_card': 'historical', 'schedule': 'interleaved', 'read_plan': 'full', 'read_anchors': ['C'],
                 'arms': ['C', 'S1', 'S2', 'S3', 'S4', 'S5'], 'memory_lock': 'unit_shared', 'program_learning': 'repair',
                 'item_stage': 'planned', 'gate_rule': 'evolution', 'gate_screen': True, 'resume_replay': 'on'}


def test_the_preset_seals_exactly_the_fields_of_the_brief_for_the_run_and_the_smoke(inputs):
    """``prepare.typed_v3_preset``: base card historical, schedule interleaved, read plan full, read anchors C (arms C,
    S1..S5), memory lock unit_shared, program learning repair, the chain's archive packages of the tree's index, item
    stage planned with T5's quota table (the smoke: its tiny table), gate rule evolution, the screen, resume replay on.
    The preset manifest differs from a default one (same root kind, same draw) in exactly these fields."""
    assert prepare.TYPED_V3_PRESET == {**{k: v for k, v in PRESET_FIELDS.items() if k not in ('read_anchors', 'arms')},
                                       'read_anchors': ('C',), 'archive': 'index'}
    assert prepare.typed_v3_preset() == {**prepare.TYPED_V3_PRESET, 'item_quotas': None}
    assert prepare.typed_v3_preset(smoke=True)['item_quotas'] == prepare.smoke_item_quotas()
    row = {'judging': {'attack': 1, 'guard': 2, 'calibration': 2}, 'shown': {'attack': 1, 'guard': 4}}
    zero = {'judging': {'attack': 0, 'guard': 0, 'calibration': 0}, 'shown': {'attack': 0, 'guard': 0}}
    assert prepare.smoke_item_quotas() == {'searchqa': row, 'officeqa': zero, 'zebralogic': row,
                                           'spreadsheetbench': zero, 'alfworld': row}
    # the smoke's row is a fixed point of the 20 % rule (the smoke's two learn items never keep a weakness)
    from skillopt.execskill.typed import items as items_
    for kept in (0, 3):
        found = items_.counts('zebralogic', kept, prepare.smoke_item_quotas())
        assert (found['judging'], found['shown']) == (row['judging'], row['shown'])
    parent = inputs['parent']
    small = {bench: {'learn': 2, 'gate': 3} for bench in typed_.ORDER}  # the fixture's pools hold 16 items
    for smoke_root, suffix in ((False, ''), (True, '-smoke')):
        common = dict(machinery_manifest=inputs['machinery'], roles_repo='/root/roles', pools_root=inputs['pools'],
                      smoke=smoke_root, typed_tree=inputs['tree'], root_parent=str(parent),
                      **({} if smoke_root else {'slices': small}))
        default = prepare.prepare(parent / ('execskill-20261112-typed-v3' + suffix), **common)
        made = prepare.prepare(parent / ('execskill-20261115-typed-v3' + suffix), **common,
                               **prepare.typed_v3_preset(smoke=smoke_root))
        assert prepare.load_manifest(made['root']) == made
        quotas = prepare.smoke_item_quotas() if smoke_root else prepare.default_item_quotas()
        expected = {**PRESET_FIELDS, 'archive': archives.sealed('index'), 'item_quotas': quotas}
        assert {key: made[key] for key in expected} == expected
        assert made['archive'] and set(made['archive']) == {'G', 'D'}
        volatile = {'root', 'prepared_at', 'record_sha256'}
        differ = {key for key in set(made) | set(default) if key not in volatile and made.get(key) != default.get(key)}
        # the schedule and read plan of the preset are the code defaults (typed-v1's order, every read fresh): sealed
        # by both manifests alike; every other preset field differs from a default manifest, and nothing else does
        assert (default['schedule'], default['read_plan']) == (typed_.SCHEDULE_DEFAULT, 'full') == ('interleaved', 'full')
        assert differ == set(expected) - {'schedule', 'read_plan'}, sorted(differ ^ set(expected))
        assert default['item_stage'] == 'none' and not {'read_anchors', 'gate_rule', 'gate_screen',
                                                        'resume_replay'} & set(default)


def test_the_cli_prepares_the_preset_alone(tmp_path, monkeypatch, capsys):
    import os
    saved = dict(os.environ)
    try:
        parse = run_typed.parser().parse_args
        assert parse(['prepare', '--root', '/r', '--typed-v3']).typed_v3 is True
        assert parse(['prepare', '--root', '/r']).typed_v3 is False
        for bad in (['run', '--root', '/r', '--chain', 'G', '--typed-v3'],
                    ['smoke', '--root', '/r', '--chain', 'G', '--fake', '--typed-v3']):
            with pytest.raises(SystemExit):
                parse(bad)
        calls = []
        monkeypatch.setattr(run_typed, '_prepare', lambda root, **kw: calls.append(kw) or {
            'configuration': 'typed-v3', 'gate_rule': 'evolution', 'gate_screen': True, 'resume_replay': 'on'})
        root, machinery = tmp_path / 'run', tmp_path / 'machinery.json'
        root.mkdir()
        machinery.write_text(json.dumps({'runtime': {}}))
        base = ['prepare', '--root', str(root), '--machinery-manifest', str(machinery)]
        for extra, smoke_flag in (([], False), (['--smoke'], True)):
            assert run_typed.main(base + ['--typed-v3'] + extra) == 0
            assert calls[-1] == {'machinery_manifest': str(machinery), 'roles_repo': typed_.ROLES_REPO,
                                 'pools_root': typed_.POOLS_ROOT, 'smoke': smoke_flag, 'typed_v3': True}
            printed = json.loads(capsys.readouterr().out)['manifest']
            assert (printed['gate_rule'], printed['gate_screen'], printed['resume_replay']) == ('evolution', True, 'on')
        # every single-option flag beside the preset is refused before anything is prepared
        for flag in (['--schedule', 'learn_first'], ['--base-card', 'historical'], ['--read-anchors', 'C'],
                     ['--item-stage', 'planned'], ['--archive', 'index'], ['--program-learning', 'repair'],
                     ['--memory-lock', 'unit_shared'], ['--read-plan', 'full'], ['--read-plan-probe', 'C0:zebralogic'],
                     ['--resume-replay', 'off'], ['--resume-replay', 'on']):
            before = len(calls)
            with pytest.raises(SystemExit):
                run_typed.main(base + ['--typed-v3'] + flag)
            assert len(calls) == before, flag
        assert {key.replace('_', '-') for key in run_typed.PRESET_EXCLUSIVE} == {
            'base-card', 'schedule', 'memory-lock', 'read-plan', 'read-plan-probe', 'program-learning', 'archive',
            'item-stage', 'read-anchors', 'resume-replay'}
        # the adapter: the preset's arguments (the smoke's with smoke), nothing beside them
        seen = []
        monkeypatch.undo()
        monkeypatch.setattr(prepare, 'prepare', lambda root, **kw: seen.append(kw) or {})
        common = dict(machinery_manifest='/m.json', roles_repo='/creds', pools_root='/pools')
        run_typed._prepare('/r', smoke=False, typed_v3=True, **common)
        run_typed._prepare('/r', smoke=True, typed_v3=True, **common)
        assert seen == [{**common, 'smoke': False, **prepare.typed_v3_preset()},
                        {**common, 'smoke': True, **prepare.typed_v3_preset(smoke=True)}]
        for single in ({'schedule': 'learn_first'}, {'resume_replay': 'off'}):
            with pytest.raises(ValueError, match='no single option'):
                run_typed._prepare('/r', smoke=False, typed_v3=True, **single, **common)
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_a_state_started_under_one_gate_rule_or_screen_refuses_the_other(tmp_path):
    plain = chain._open_state(tmp_path / 'a', 'G', 'smoke', False)
    assert 'gate_rule' not in plain and 'gate_screen' not in plain   # typed-v2's state shape
    made = chain._open_state(tmp_path / 'b', 'G', 'smoke', False, gate_rule='evolution', gate_screen=True)
    assert (made['gate_rule'], made['gate_screen']) == ('evolution', True)
    (tmp_path / 'b').mkdir()
    units.write_json(tmp_path / 'b' / 'state.json', made)
    assert chain._open_state(tmp_path / 'b', 'G', 'smoke', True, gate_rule='evolution', gate_screen=True) == made
    for kw in ({}, {'gate_rule': 'evolution'}, {'gate_screen': True}, {'gate_rule': 'whole', 'gate_screen': True}):
        with pytest.raises(ValueError, match='another'):
            chain._open_state(tmp_path / 'b', 'G', 'smoke', True, **kw)
    (tmp_path / 'a').mkdir()
    units.write_json(tmp_path / 'a' / 'state.json', plain)
    for kw in ({'gate_rule': 'evolution'}, {'gate_screen': True}):
        with pytest.raises(ValueError, match='another'):
            chain._open_state(tmp_path / 'a', 'G', 'smoke', True, **kw)
    # chain.run refuses a bad value before the chain directory, the state or the ledger is written
    for n, change in enumerate(({'gate_rule': 'E'}, {'gate_screen': 'yes'}, {'item_stage': 'none', 'item_quotas': None})):
        root = tmp_path / ('bad-%d' % n)
        services = build(root, stage.Script(), gate_screen=True)
        services.manifest.update(change)
        with pytest.raises(ValueError):
            chain.run(root, 'G', services=services, sleep=lambda s: None)
        assert not root.exists()


OPTION_DEFAULTS = {'program_learning': 'single', 'archive': None, 'item_stage': 'none', 'item_quotas': None,
                   'read_anchors': ('C0', 'C'), 'resume_replay': 'off', 'gate_rule': 'whole', 'gate_screen': False}


def test_a_state_records_every_typed_v3_option_and_refuses_a_resume_under_another_value_of_any(tmp_path):
    """The merged ``_open_state``: a state started with every typed-v3 option away from its default records each one
    (the archive and the quota table by their hashes); reopened with the same values it is the same state; reopened
    with any ONE of them at its default it is refused (a new root is needed), and so is a typed-v2 style state
    reopened with any one of them set. A typed-v2 style state records none of them."""
    full = {'program_learning': 'repair', 'archive': {'G': {'zebralogic': {'package': 'p'}}}, 'item_stage': 'planned',
            'item_quotas': prepare.smoke_item_quotas(), 'read_anchors': ('C',), 'resume_replay': 'on',
            'gate_rule': 'evolution', 'gate_screen': True}
    assert set(full) == set(OPTION_DEFAULTS)
    made = chain._open_state(tmp_path / 'a', 'G', 'smoke', False, **full)
    assert {key: made.get(key) for key in ('program_learning', 'archive_sha256', 'item_stage', 'item_quotas_sha256',
                                           'read_anchors', 'resume_replay', 'gate_rule', 'gate_screen')} == {
        'program_learning': 'repair', 'archive_sha256': library_.canonical_sha256(full['archive']),
        'item_stage': 'planned', 'item_quotas_sha256': library_.canonical_sha256(full['item_quotas']),
        'read_anchors': ['C'], 'resume_replay': 'on', 'gate_rule': 'evolution', 'gate_screen': True}
    plain = chain._open_state(tmp_path / 'b', 'G', 'smoke', False)
    assert not {'program_learning', 'archive_sha256', 'item_stage', 'item_quotas_sha256', 'read_anchors',
                'resume_replay', 'gate_rule', 'gate_screen'} & set(plain)
    for name, state in (('a', made), ('b', plain)):
        (tmp_path / name).mkdir()
        units.write_json(tmp_path / name / 'state.json', state)
    assert chain._open_state(tmp_path / 'a', 'G', 'smoke', True, **full) == made
    assert chain._open_state(tmp_path / 'b', 'G', 'smoke', True) == plain
    for key, default in OPTION_DEFAULTS.items():
        with pytest.raises(ValueError, match='another'):
            chain._open_state(tmp_path / 'a', 'G', 'smoke', True, **{**full, key: default})
        with pytest.raises(ValueError, match='another'):
            chain._open_state(tmp_path / 'b', 'G', 'smoke', True, **{key: full[key]})


# ==== B: the card rule on E = R + A, the program rule on J (T7) ========================================================
def card_r1(root):
    return read(root, 's1', 'card-r1', 'decision.json')


def test_tau_on_E_comes_from_the_baseline_repeats_on_E_and_decides_where_the_whole_list_rule_refuses(tmp_path,
                                                                                                     monkeypatch):
    """Unequal variance on E and on J (``variance``): B's sums on E are 3 on 15 and 19, 1 on attack item 20, 0 elsewhere
    -> Q_E = 3 * 1 - 1 = 2; on J the guard items 23 and 27 add S = 2 each -> Q_J = 2 + 2 + 2 = 6. The card fixes item
    24 (0 -> 3): D_E = D_J = 3, better 1, worse 0. On E (n 14): gain 100 * 3 / 42 = 7.14, se = (100 / 42) sqrt 2 = 3.37,
    tau_E = 6.73: reaches (in integers: 300 >= 126 and 9 * 196 * 2 = 3528 >= 2 * 4 * 2 * 196 = 3136); no_regress on J
    (D >= 0): accepted. The whole-list rule on the same runs: gain 100 * 3 / 60 = 5.0 < tau_J = 2 (100 / 60) sqrt 6 =
    8.16 (7200 < 19200): gain_below_tau. Had tau come from J's repeats with E's counts, E would fail too (7200 < 9408)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    whole, _ = run(tmp_path / 'whole', rule=variance, gate_rule='whole')
    evolution, _ = run(tmp_path / 'evolution', rule=variance, gate_rule='evolution')
    assert whole['complete'] and evolution['complete'], (whole['paused'], evolution['paused'])
    before, after = card_r1(tmp_path / 'whole'), card_r1(tmp_path / 'evolution')
    gain_j, se_j, tau_j = hand(3, 6, 20)
    for found in (before, after):   # the whole-list statistics of J are the same record in both
        assert (found['n'], found['difference_sum'], found['variance_sum'], found['better'], found['worse']) == (20, 3, 6, 1, 0)
        assert close(found['gain_points'], gain_j) and close(found['se_points'], se_j) and close(found['tau_points'], tau_j)
        assert found['reaches'] is False and found['no_regress'] is True
        assert [row[0] for row in found['per_item']] == J()
    assert (before['accepted'], before['reason'], 'evolution' in before) == (False, 'gain_below_tau', False)
    assert (after['accepted'], after['reason']) == (True, 'accepted')
    block = after['evolution']
    gain_e, se_e, tau_e = hand(3, 2, 14)
    assert block['item_ids'] == E() and (block['n'], block['difference_sum'], block['variance_sum']) == (14, 3, 2)
    assert close(block['gain_points'], gain_e) and close(block['se_points'], se_e) and close(block['tau_points'], tau_e)
    assert tau_e > 3.0 and gain_e > tau_e and tau_e < tau_j
    assert (block['better'], block['worse'], block['tied'], block['reaches']) == (1, 0, 13, True)
    assert chain.recompute_decision(after) == after and chain.recompute_decision(before) == before
    # where the runs are: the incumbent F shares B's noise runs; the card's own gate unit holds its R runs
    assert after['baseline'] == {'unit': 's1/outcomes', 'arm': 'F', 'shared_from': {'unit': 's1/noise', 'arm': 'B'}}
    blocks = [read(tmp_path / name, 's1', 'decisions.json').get('gate_rule') for name in ('whole', 'evolution')]
    assert blocks == [None, {'rule': 'evolution', 'screen': False, 'card_rule': 'evolution', 'gate_items': 20,
                             'evolution_items': 14, 'screened': False, 'screen_items': {'attack': 0, 'guard': 0}}]
    # the accepted card is installed (the frozen library holds it); a typed-v2 style state has no gate-rule key
    assert [s['kind'] for s in library_.Library.load(tmp_path / 'evolution' / 'G' / 's1' / 'library.json').skills] == [
        'card']
    assert 'gate_rule' not in whole and evolution['gate_rule'] == 'evolution' and 'gate_screen' not in evolution


def test_a_gain_on_E_with_a_regression_on_the_guard_items_beyond_tau_J_is_refused_with_harm(tmp_path, monkeypatch):
    """``harm``: the card fixes attack item 20 (+3) and breaks the three guard items (-9). B is deterministic (Q = 0,
    tau = 3 on E and on J). On E: D 3, gain 7.14 >= 3 (300 >= 126), better 1 > worse 0. On J: D = -6; no_regress fails
    (-600 < -180, D < 0, 36 * 2 = 72 > 2 * 4 * 0): harm. The whole-list rule refuses it earlier (D < 0: gain_below_tau)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    whole, _ = run(tmp_path / 'whole', rule=harm, gate_rule='whole')
    evolution, _ = run(tmp_path / 'evolution', rule=harm)
    assert whole['complete'] and evolution['complete']
    before, after = card_r1(tmp_path / 'whole'), card_r1(tmp_path / 'evolution')
    assert (before['accepted'], before['reason']) == (False, 'gain_below_tau')
    assert (after['accepted'], after['reason']) == (False, 'harm')
    assert (after['difference_sum'], after['variance_sum'], after['tau_points'], after['no_regress']) == (-6, 0, 3.0, False)
    block = after['evolution']
    assert (block['n'], block['difference_sum'], block['variance_sum'], block['tau_points'], block['reaches']) == (
        14, 3, 0, 3.0, True)
    assert close(block['gain_points'], 100 * 3 / 42) and (block['better'], block['worse']) == (1, 0)
    by_class = read(tmp_path / 'evolution', 's1', 'decisions.json')['cards'][0]['by_class']
    assert {name: by_class[name]['difference_sum'] for name in ('real', 'attack', 'guard', 'calibration')} == {
        'real': 0, 'attack': 3, 'guard': -9, 'calibration': 0}
    assert chain.recompute_decision(after) == after


def test_a_card_whose_gain_sits_only_on_the_calibration_items_is_refused(tmp_path, monkeypatch):
    """``calibration_only``: B right on K in the item check's single run (the check holds: 0 of 6 attack, 3 of 3
    calibration) and wrong in every gate run; the card right on K in every run where it is mounted. Calibration item
    75 lies beyond the SearchQA type's p95 routing threshold (P2b's fixture: no type, so no card is mounted there), so
    the card gains on two calibration items: D_K = 6, D_E = 0. The whole-list rule accepts it (D 6 over 20 items, Q 0:
    gain 10.0 >= 3, better 2 > 0); on E it is refused: gain_below_tau (D_E = 0)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    assert 75 in round_1_calibration()
    whole, _ = run(tmp_path / 'whole', rule=calibration_only, gate_rule='whole')
    evolution, _ = run(tmp_path / 'evolution', rule=calibration_only)
    assert whole['complete'] and evolution['complete']
    check = read(tmp_path / 'evolution', 's1', 'items-check', 'check.json')
    assert (check['holds'], check['attack']['pass'], check['calibration']['pass']) == (True, 0, 3)
    before, after = card_r1(tmp_path / 'whole'), card_r1(tmp_path / 'evolution')
    assert (before['accepted'], before['reason'], before['difference_sum'], before['gain_points'], before['better']) == (
        True, 'accepted', 6, 10.0, 2)
    rows = {row[0]: row for row in after['per_item']}
    assert [rows[sq_id(i)][1:] for i in round_1_calibration()] == [[0, 3] if i != 75 else [0, 0]
                                                                   for i in round_1_calibration()]
    assert (after['accepted'], after['reason'], after['evolution']['difference_sum']) == (False, 'gain_below_tau', 0)
    assert (after['evolution']['better'], after['evolution']['worse'], after['evolution']['tied']) == (0, 0, 14)


def test_programs_keep_the_whole_list_rule_and_by_class_reports_without_deciding(tmp_path, monkeypatch):
    """The program of slot 1 (P2b's SearchQA promotion path) under 'evolution': its record is ``program_decision``'s
    on J, exactly as under 'whole' (no evolution block), with by_class beside it in decisions.json."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    whole, _ = run(tmp_path / 'whole', rule=harm, gate_rule='whole')
    evolution, _ = run(tmp_path / 'evolution', rule=harm)
    a, b = (read(tmp_path / name, 's1', 'program-1', 'decision.json') for name in ('whole', 'evolution'))
    assert 'evolution' not in b and a['kind'] == b['kind'] == 'program'
    strip = lambda row: {k: v for k, v in row.items() if k not in ('mount_snapshot', 'baseline_selected')}  # noqa: E731
    assert strip(stage.strip(a)) == strip(stage.strip(b))
    assert chain.recompute_decision(b) == b
    row = read(tmp_path / 'evolution', 's1', 'decisions.json')['programs'][-1]
    assert row['by_class'] == gates.class_gains(b['per_item'], {i: c for i, c in zip(J(), ['real'] * 8 + ['attack'] * 6
                                                                                     + ['guard'] * 3 + ['calibration'] * 3)},
                                                R)


def test_a_step_without_made_items_decides_as_typed_v2_under_the_typed_v3_rules(tmp_path, monkeypatch):
    """OfficeQA (audit_bing_B36) and SpreadsheetBench (maker_not_built) with the default quota table: J = R, so the
    card rule is ``card_decision`` (no evolution block) and no candidate is screened (no screen unit, no screen record);
    apart from the decisions' gate_rule block every record equals the same chain's under 'whole' without the screen."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    order, quotas = ('officeqa', 'spreadsheetbench'), prepare.default_item_quotas()
    script_a, script_b = stage.Script(), stage.Script()
    plain, _ = run(tmp_path / 'a', script_a, rule=strict_rule, order=order, quotas=quotas, gate_rule='whole',
                   gate_screen=False)
    typed3, _ = run(tmp_path / 'b', script_b, rule=strict_rule, order=order, quotas=quotas, gate_screen=True)
    assert plain['complete'] and typed3['complete']
    found, expected = stage.records(tmp_path / 'b'), stage.records(tmp_path / 'a')
    for k in (1, 2):
        block = found['s%d/decisions.json' % k].pop('gate_rule')
        assert block == {'rule': 'evolution', 'screen': True, 'card_rule': 'whole', 'gate_items': 6 if k == 1 else 3,
                         'evolution_items': None, 'screened': False, 'screen_items': {'attack': 0, 'guard': 0}}
        assert 'gate_rule' not in expected['s%d/decisions.json' % k]
    assert found == expected
    assert not [rel for rel in found if '-screen/' in rel or 'screen.json' in rel]
    assert all('evolution' not in row and 'screen_run' not in row
               for k in (1, 2) for row in found['s%d/decisions.json' % k]['cards'])
    assert Counter(script_b.calls) == Counter(script_a.calls)


def strict_rule(bench, item, mounted, repeat):
    return strict(bench, item, mounted)


# ==== C: the screen before the gate (T7) ==============================================================================
def screen_of(root, stem):
    return read(root, *('%s-screen' % stem).split('/'), 'screen.json')


def test_the_screen_passes_at_R_c_equal_to_b_and_refuses_at_b_minus_one(tmp_path, monkeypatch):
    """A + G = 9 items. ``b_like``: B's runs there: 0 on each attack item, 3 on each guard item -> b = 9; the card's one
    run: wrong on A, right on G -> c = 3; R c = 9 = b: passed, the gate runs. ``screen_short``: B also right on item 20
    in gate run 1 -> b = 10, c = 3: R c = 9 = b - 1: refused (screen_below_baseline), zero gate cells, no gate unit.
    The program of slot 1 is screened against the same incumbent F (B's noise runs): fired on all 9 (b 9 / 10, c 3)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    assert gates.screen_decision(9, 3, repeats=3, items=9)['passed'] is True
    assert gates.screen_decision(10, 3, repeats=3, items=9)['reason'] == 'screen_below_baseline'
    equal, _ = run(tmp_path / 'equal', gate_screen=True)
    short, _ = run(tmp_path / 'short', rule=screen_short, gate_screen=True)
    assert equal['complete'] and short['complete'], (equal['paused'], short['paused'])
    sealed = read(tmp_path / 'equal', 's1', 'items.json')
    baseline = {'unit': 's1/outcomes', 'run_unit': 's1/noise', 'run_arm': 'B'}
    for name, b, passed, reason in (('equal', 9, True, 'passed'), ('short', 10, False, 'screen_below_baseline')):
        root = tmp_path / name
        # the candidate as mounted (its canonical hash binds the screen record to it): the card round's text, the
        # program of slot 1 as the engineer's proposals record holds it, both with their home type
        tid, = read(root, 's1', 'typemap.json')['types']
        proposal = next(row for row in read(root, 's1', 'programs', 'proposals.json') if row['slot'] == 1)
        mounted = {'s1/card-r1': {'text': read(root, 's1', 'card-r1', 'writer.json')['text'], 'home_type': tid},
                   's1/program-1': {'procedure': proposal['procedure'], 'home_type': tid}}
        for stem, arm, fired in (('s1/card-r1', 'cand_card', None), ('s1/program-1', 'cand_program', 9)):
            found = screen_of(root, stem)
            assert found == {'kind': 'screen', 'b': b, 'c': 3, 'repeats': 3, 'items': 9, 'fired': fired,
                             'baseline_pass_points': 100 * b / 27, 'candidate_pass_points': 100 * 3 / 9,
                             'passed': passed, 'reason': reason, 'unit': stem + '-screen', 'bench': 'searchqa', 'step': 1,
                             'arm': arm, 'item_ids': screened(), 'classes': {'attack': 6, 'guard': 3},
                             'procedures': None if fired is None else [proposal['procedure']['id']],
                             'baseline': baseline, 'candidate_sha256': library_.canonical_sha256(mounted[stem]),
                             'items_sha256': sealed['record_sha256']}, (name, stem)
            assert gates.recompute(found) == found
            assert sorted(cell['item_id'] for cell in cells_of(root, stem + '-screen')) == sorted(screened())
            assert {cell['arm'] for cell in cells_of(root, stem + '-screen')} == {arm}
    program = read(tmp_path / 'equal', 's1', 'program-1', 'decision.json')
    assert screen_of(tmp_path / 'equal', 's1/program-1')['procedures'] == [program['procedure_id']]
    # passed: the decision keeps the screen record beside its gate (60 fresh gate cells)
    card = card_r1(tmp_path / 'equal')
    assert card['screen_run'] == screen_of(tmp_path / 'equal', 's1/card-r1') and card['cells'] == 60
    assert len(cells_of(tmp_path / 'equal', 's1/card-r1')) == 60 and card['reason'] == 'gain_below_tau'
    # refused: zero gate cells, no gate plan or cell, no by_class, and the record rebuilds from itself
    for stem in ('s1/card-r1', 's1/program-1'):
        refused = read(tmp_path / 'short', *stem.split('/'), 'decision.json')
        assert (refused['accepted'], refused['reason'], refused['cells']) == (False, 'screen_below_baseline', 0)
        assert 'per_item' not in refused and refused['screen_run'] == screen_of(tmp_path / 'short', stem)
        assert chain.recompute_decision(refused) == refused
    assert not (tmp_path / 'short' / 'G' / 's1' / 'card-r1' / 'plan.json').exists()
    assert not (tmp_path / 'short' / 'G' / 's1' / 'card-r1' / 'cells').exists()
    assert not (tmp_path / 'short' / 'G' / 's1' / 'program-1-gate').exists()
    decisions = read(tmp_path / 'short', 's1', 'decisions.json')
    assert decisions['cards'][0]['by_class'] is None and decisions['programs'][-1]['by_class'] is None
    assert decisions['gate_rule']['screened'] is True and decisions['gate_rule']['screen_items'] == {'attack': 6,
                                                                                                      'guard': 3}
    assert not [arm for arm in decisions['gate']['arms'] if arm['unit'].endswith('-screen')]


def test_a_refused_screen_record_can_never_pass_for_a_gate_and_a_forged_verdict_is_seen():
    """``recompute_decision`` of a refusal without a gate: only a screen that did not pass can refuse; a stored verdict
    that its b and c do not give is not reproduced."""
    base = {'kind': 'card', 'accepted': False, 'reason': 'screen_below_baseline', 'cells': 0,
            'screen_run': {**gates.screen_decision(10, 3, repeats=3, items=9), 'unit': 's1/card-r1-screen'}}
    assert chain.recompute_decision(base) == base
    forged = {**base, 'screen_run': {**base['screen_run'], 'b': 9}}   # b = 9, c = 3 would pass
    with pytest.raises(ValueError):
        chain.recompute_decision(forged)
    lied = {**base, 'screen_run': {**base['screen_run'], 'passed': True, 'reason': 'passed'}}
    assert chain.recompute_decision(lied) != lied   # its b and c give a refusal: the stored verdict is not reproduced
    other = {**base, 'reason': 'screen_never_fired'}
    assert chain.recompute_decision(other) != other
    with pytest.raises(ValueError):
        chain.recompute_decision({**base, 'screen_run': {**base['screen_run'], 'kind': 'card'}})


def test_a_program_that_never_fires_on_the_screen_items_is_refused_at_the_screen(tmp_path, monkeypatch):
    """The program fires on the learn items only (its smoke on three learn items is clean): on A + G fired = 0 ->
    screen_never_fired (checked before the count: c 3 >= 9 / 3 would pass), zero gate cells, no gate unit."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    state, _ = run(tmp_path, gate_screen=True, fires=lambda bench, item, procedure: index(item['task_id']) < 12)
    assert state['complete'], state['paused']
    found = screen_of(tmp_path, 's1/program-1')
    assert (found['fired'], found['b'], found['c'], found['passed'], found['reason']) == (0, 9, 3, False,
                                                                                         'screen_never_fired')
    decision = read(tmp_path, 's1', 'program-1', 'decision.json')
    assert (decision['accepted'], decision['reason'], decision['cells']) == (False, 'screen_never_fired', 0)
    assert decision['smoke']['items'] == 3 and decision['smoke']['faults'] == [] and 'per_item' not in decision
    assert not (tmp_path / 'G' / 's1' / 'program-1-gate').exists() and 's1/program-1-smoke' in state['done_units']


def test_a_card_round_refused_at_the_screen_is_still_revised_in_round_two(tmp_path, monkeypatch):
    """Two card rounds, ``screen_short``: round 1 is refused at its screen; as after any refused round its card runs
    once on the learn and the shown items (s1/card-r1-learn) and round 2's writer gets those examples, the previous
    card and the round's summary -- the screen's counts only (stage 'screen'), no item id, no judging-side text."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    script = stage.Script()
    services = build(tmp_path, script, rule=screen_short, gate_screen=True, limits={'card_rounds': 2})
    calls, write = [], services.write_card
    services.write_card = lambda **kw: calls.append(kw) or write(**kw)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    done = [unit for unit in state['done_units'] if unit.startswith('s1/card')]
    assert done == ['s1/card-r1-screen', 's1/card-r1', 's1/card-r1-learn', 's1/card-r2-screen', 's1/card-r2']
    learn = [sq_id(i) for i in range(12)]
    shown = [sq_id(i) for i in ROUND_1['shown_attack'] + ROUND_1['shown_guard']]
    assert sorted(c['item_id'] for c in cells_of(tmp_path, 's1/card-r1-learn')) == sorted(learn + shown)
    first, second = calls
    assert (second['round'], second['previous']) == (2, read(tmp_path, 's1', 'card-r1', 'writer.json')['text'])
    assert second['result'] == card_r1(tmp_path) and [e['task_id'] for e in second['examples']][:12] != []
    summary = writers.revision_result(second['result'])
    assert summary == {'stage': 'screen', 'touched': 9, 'passes': 3, 'baseline_runs_right': 10,
                       'baseline_runs_per_item': 3, 'pass_points': 100 * 3 / 9, 'baseline_pass_points': 100 * 10 / 27,
                       'rule': writers.SCREEN_RULE, 'decision': 'reject', 'failing_clause': 'screen_below_baseline'}
    requests = [text for purpose, unit, text in script.role_requests(('card_writer',)) if unit == 's1/card-r2']
    assert requests and all('"stage": "screen"' in text for text in requests)
    for i in REAL + A + G + round_1_calibration():
        assert not [m for m in markers(i) for text in requests if m in text], i
        assert not [text for text in requests if sq_id(i) in text], i
    assert read(tmp_path, 's1', 'card-r2', 'decision.json')['reason'] == 'screen_below_baseline'


def test_the_screen_cells_are_never_gate_runs(tmp_path, monkeypatch):
    """Where every candidate passes its screen (``b_like``): the screen units hold one cell per screen item at the bare
    arm, the gate units R fresh cells per item of J at <arm>#<r> (sent apart: one send each), no gate arm of the step is
    a screen unit or shares one, and the decision counts the gate's own cells."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    script = stage.Script()
    state, services = run(tmp_path, script, gate_screen=True)
    assert state['complete'], state['paused']
    for stem, arm, gate_unit in (('s1/card-r1', 'cand_card', 's1/card-r1'),
                                 ('s1/program-1', 'cand_program', 's1/program-1-gate')):
        screen_cells = cells_of(tmp_path, stem + '-screen')
        assert sorted(c['item_id'] for c in screen_cells) == sorted(screened()) and {c['arm'] for c in screen_cells} == {arm}
        gate_cells = [c for c in cells_of(tmp_path, gate_unit) if c['arm'].startswith(arm + '#')]
        assert sorted((c['item_id'], c['arm']) for c in gate_cells) == sorted(
            (item, '%s#%d' % (arm, r)) for item in J() for r in (1, 2, 3))
        assert all(len(c['sends']) == 1 for c in gate_cells + screen_cells)
        assert not {c['tag'] for c in screen_cells} & {c['tag'] for c in gate_cells}
        sends = Counter(unit for purpose, unit in script.calls if purpose == 'solver')
        assert sends[stem + '-screen'] == 9 and sends[gate_unit] >= 60
    decisions = read(tmp_path, 's1', 'decisions.json')
    arms = decisions['gate']['arms']
    assert not [arm for arm in arms if '-screen' in arm['unit'] or '-screen' in str(arm.get('shared_from'))]
    for path in (tmp_path / 'G' / 's1').glob('*/plan.json'):
        plan = json.loads(path.read_text())
        assert '-screen' not in path.parent.name and '-screen' not in json.dumps(plan.get('shared_from')), path
    assert decisions['cards'][0]['cells'] == 60 and decisions['programs'][-1]['cells'] == 60


def test_the_revision_summary_of_a_card_decided_on_E(tmp_path, monkeypatch):
    """The round-2 summary of an evolution card: the counts and points on E (touched 14, fixed 1, broken 0, the gain
    and tau on E) and the harm clause on J (20 items, the whole-list gain and tau); counts and short labels only."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    run(tmp_path / 'v', rule=variance)
    run(tmp_path / 'h', rule=harm)
    accepted, refused = card_r1(tmp_path / 'v'), card_r1(tmp_path / 'h')
    gain_e, _, tau_e = hand(3, 2, 14)
    gain_j, _, tau_j = hand(3, 6, 20)
    found = writers.revision_result(accepted)
    assert set(found) == {'stage', 'touched', 'fixed', 'broken', 'net', 'tied', 'excluded_unknown', 'mean_gain_points',
                          'required_mean_gain_points', 'rule', 'whole_list_items', 'whole_list_mean_gain_points',
                          'allowed_loss_points', 'harm_rule', 'decision', 'failing_clause'}
    assert (found['touched'], found['fixed'], found['broken'], found['net'], found['tied']) == (14, 1, 0, 1, 13)
    assert close(found['mean_gain_points'], gain_e) and close(found['required_mean_gain_points'], tau_e)
    assert found['whole_list_items'] == 20 and close(found['whole_list_mean_gain_points'], gain_j)
    assert close(found['allowed_loss_points'], tau_j) and (found['decision'], found['failing_clause']) == ('accept', None)
    assert (found['rule'], found['harm_rule']) == (writers.EVOLUTION_RULE, writers.HARM_RULE)
    assert writers.revision_result(refused)['failing_clause'] == 'harm'
    assert 'searchqa-' not in json.dumps(found) and 'searchqa-' not in json.dumps(writers.revision_result(refused))
    assert all(len(text) <= 80 for text in (writers.EVOLUTION_RULE, writers.HARM_RULE, writers.SCREEN_RULE))


# ==== D: resume around the screen; stored records that their own records do not give again =============================
def kill_solve(services, unit, nth):
    """A process death at the ``nth`` solve of ``unit`` (1-based), before that cell's send."""
    solve, seen = services.solve_fn, []

    def killing(bench, item, mounted, **rest):
        if rest['unit'] == unit:
            seen.append(item['task_id'])
            if len(seen) == nth:
                raise Kill()
        return solve(bench, item, mounted, **rest)
    services.solve_fn = killing
    return seen


def kill_method(monkeypatch, name, test):
    """A process death at the first call of ``_Run.<name>`` that ``test(args)`` admits, before the method runs."""
    original, hit = getattr(chain._Run, name), []

    def killing(self, *args, **kw):
        if not hit and test(*args):
            hit.append(args[0])
            raise Kill()
        return original(self, *args, **kw)
    monkeypatch.setattr(chain._Run, name, killing)
    return hit


def kill_after_decision(monkeypatch, unit):
    """A process death right after the decision record of ``unit`` was written and checked (``verify_decision``),
    before anything of it is applied or the unit is marked done."""
    original, hit = chain._Run.verify_decision, []

    def killing(self, unit_, decision, compute, **kw):
        found = original(self, unit_, decision, compute, **kw)
        if unit_ == unit and not hit:
            hit.append(unit_)
            raise Kill()
        return found
    monkeypatch.setattr(chain._Run, 'verify_decision', killing)
    return hit


KILLS = {
    'inside_the_card_screen': ('b_like', lambda services, patch: kill_solve(services, 's1/card-r1-screen', 2)),
    'after_the_screen_cells': ('b_like', lambda services, patch: kill_method(
        patch, 'screen_record', lambda unit, *rest: unit == 's1/card-r1-screen')),
    'between_screen_and_gate_plan': ('b_like', lambda services, patch: kill_method(
        patch, 'gate_arm', lambda unit, *rest: unit == 's1/card-r1')),
    'at_the_first_gate_cell': ('b_like', lambda services, patch: kill_solve(services, 's1/card-r1', 1)),
    'inside_the_program_screen': ('b_like', lambda services, patch: kill_solve(services, 's1/program-1-screen', 2)),
    'after_a_screen_refusal': ('screen_short', lambda services, patch: kill_after_decision(patch, 's1/card-r1')),
    'after_a_program_refusal': ('screen_short', lambda services, patch: kill_after_decision(patch, 's1/program-1')),
    # a stored decision that reached its gate (Codex review of P3b): rebuilt from its records on resume, reproduced
    'after_an_accepted_card': ('variance', lambda services, patch: kill_after_decision(patch, 's1/card-r1')),
    'after_a_gated_program': ('b_like', lambda services, patch: kill_after_decision(patch, 's1/program-1')),
}
RULES = {'b_like': b_like, 'screen_short': screen_short, 'variance': variance}


@pytest.mark.parametrize('point', sorted(KILLS))
def test_a_kill_around_the_screen_resumes_to_the_records_of_an_uninterrupted_run(tmp_path, monkeypatch, point):
    """Killed inside the card round's screen unit, after its cells and before screen.json, between screen.json and
    the gate's plan, at the gate's first cell, inside the program's screen, after a card's and a program's screen
    refusal was recorded, and after an accepted card's and a gated program's decision was recorded (each stored
    decision is rebuilt from its records on resume and must be given again): the resumed run makes only the missing
    cells (no send repeated) and every record equals an uninterrupted run's; a later resume of the complete chain sends
    nothing."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    rule_name, arm = KILLS[point]
    reference, resumed = tmp_path / 'a', tmp_path / 'b'
    script_a = stage.Script()
    state, _ = run(reference, script_a, rule=RULES[rule_name], gate_screen=True)
    assert state['complete'], state['paused']
    script_b = stage.Script()
    services = build(resumed, script_b, rule=RULES[rule_name], gate_screen=True)
    with monkeypatch.context() as patched:
        hit = arm(services, patched)
        with pytest.raises(Kill):
            chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    assert hit
    if point in ('after_an_accepted_card', 'after_a_gated_program'):
        stored = json.loads((resumed / 'G' / hit[0] / 'decision.json').read_text())
        assert 'per_item' in stored and stored['screen_run']['passed'] is True
        assert point != 'after_an_accepted_card' or stored['accepted'] is True
    if point == 'after_the_screen_cells':
        assert 's1/card-r1-screen' in json.loads((resumed / 'G' / 'state.json').read_text())['done_units']
        assert not (resumed / 'G' / 's1' / 'card-r1-screen' / 'screen.json').exists()
    if point in ('between_screen_and_gate_plan', 'at_the_first_gate_cell'):
        assert (resumed / 'G' / 's1' / 'card-r1-screen' / 'screen.json').exists()
        assert (resumed / 'G' / 's1' / 'card-r1' / 'plan.json').exists() == (point == 'at_the_first_gate_cell')
    recovery(resumed)
    services = build(resumed, script_b, rule=RULES[rule_name], gate_screen=True)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    found, expected = stage.records(resumed), stage.records(reference)
    assert sorted(found) == sorted(expected)
    for rel in expected:
        assert found[rel] == expected[rel], rel
    assert Counter(script_b.calls) == Counter(script_a.calls)       # no call whose record exists was repeated
    assert len(script_b.requests) == len(script_a.requests)
    before = len(script_b.requests)
    assert chain.run(resumed, 'G', services=services, resume=True)['complete'] and len(script_b.requests) == before


def forged_on(record, ids):
    """``record`` with its evolution block rebuilt, coherently, on the ids ``ids`` (P3a's arithmetic): recompute
    accepts it; only the provenance of E is wrong."""
    stats = {key: value for key, value in record.items() if key != 'evolution'}
    return {**record, **gates.card_decision_evolution(stats, gates.evolution_statistics(stats, ids))}


FORGERIES = {
    'E_on_the_calibration_items': (lambda record: forged_on(record, [sq_id(i) for i in round_1_calibration()]),
                                   'evolution_items'),
    'E_without_the_attack_items': (lambda record: forged_on(record, [sq_id(i) for i in REAL]), 'evolution_items'),
    'no_evolution_block': (lambda record: {k: v for k, v in record.items() if k != 'evolution'}, 'evolution_items'),
    'a_changed_gain_on_E': (lambda record: {**record, 'evolution': {**record['evolution'], 'gain_points': 99.0}},
                            'gate_differs'),
    'a_changed_verdict': (lambda record: {**record, 'accepted': True, 'reason': 'accepted'}, 'stage'),
    'an_extra_field': (lambda record: {**record, 'note': 'added'}, 'not_reproduced'),
}


@pytest.mark.parametrize('forgery', sorted(FORGERIES))
def test_a_stored_card_decision_with_a_forged_E_is_refused_on_resume(tmp_path, monkeypatch, forgery):
    """Review of P3a, point 4: ``gates.recompute`` checks an evolution block against the record's own rows, not where E
    came from. ``calibration_only``: the honest decision refuses the card (D_E = 0); rebuilt on E = K (D 6 over the
    two routed calibration items: gain 66.7, better 2) the same runs would ACCEPT it, coherently. Killed after the
    decision record, forged, resumed: the chain pauses gate_decision_changed before anything of it is applied (the
    decision function run again on the records gives E = R + A of the sealed items.json in J's order, the gate rows
    of the cells, the verdict, and no other field)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    services = build(tmp_path, stage.Script(), rule=calibration_only)
    with monkeypatch.context() as patched:
        kill_after_decision(patched, 's1/card-r1')
        with pytest.raises(Kill):
            chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    path = tmp_path / 'G' / 's1' / 'card-r1' / 'decision.json'
    honest = json.loads(path.read_text())
    assert (honest['accepted'], honest['reason'], honest['evolution']['item_ids']) == (False, 'gain_below_tau', E())
    if forgery == 'E_on_the_calibration_items':
        assert forged_on(honest, [sq_id(i) for i in round_1_calibration()])['accepted'] is True
    change, code = FORGERIES[forgery]
    forged = change(honest)
    if code == 'evolution_items' and 'evolution' in forged:
        assert chain.recompute_decision(forged) == forged   # coherent: only its provenance betrays it
    units.write_json(path, forged)
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=build(tmp_path, stage.Script(), rule=calibration_only), resume=True,
                      sleep=lambda s: None)
    assert (state['paused']['reason'], state['paused']['unit'], state['paused']['detail']) == (
        'gate_decision_changed', 's1/card-r1', code)
    assert not (tmp_path / 'G' / 's1' / 'card-r1' / 'skill.json').exists()
    # nothing of it was applied and the step went no further: no skill, no programs unit, no frozen state
    assert not (tmp_path / 'G' / 's1' / 'programs').exists() and not (tmp_path / 'G' / 's1' / 'library.json').exists()
    assert state['current_unit'] == 's1/card-r1'


def test_a_changed_screen_record_or_a_decision_whose_screen_is_not_its_units_is_refused(tmp_path, monkeypatch):
    """screen.json of the card round changed between the screen and the gate (b one higher, its verdict coherently
    rebuilt): the resumed screen recomputes it from its cells and pauses gate_screen_changed. A stored program decision
    whose screen record is not the one its screen unit's cells give pauses gate_decision_changed (screen_differs)
    before anything of it is applied; with both changed alike the unit's cells refuse them (gate_screen_changed)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    root = tmp_path / 'card'
    services = build(root, stage.Script(), gate_screen=True)
    with monkeypatch.context() as patched:
        kill_method(patched, 'gate_arm', lambda unit, *rest: unit == 's1/card-r1')
        with pytest.raises(Kill):
            chain.run(root, 'G', services=services, sleep=lambda s: None)
    path = root / 'G' / 's1' / 'card-r1-screen' / 'screen.json'
    stored = json.loads(path.read_text())
    units.write_json(path, {**stored, **gates.screen_decision(stored['b'] + 1, stored['c'], repeats=3, items=9)})
    recovery(root)
    state = chain.run(root, 'G', services=build(root, stage.Script(), gate_screen=True), resume=True,
                      sleep=lambda s: None)
    assert (state['paused']['reason'], state['paused']['unit']) == ('gate_screen_changed', 's1/card-r1-screen')
    assert not (root / 'G' / 's1' / 'card-r1' / 'plan.json').exists()
    for name, both in (('program', False), ('program-both', True)):
        root = tmp_path / name
        services = build(root, stage.Script(), gate_screen=True)
        with monkeypatch.context() as patched:
            kill_after_decision(patched, 's1/program-1')
            with pytest.raises(Kill):
                chain.run(root, 'G', services=services, sleep=lambda s: None)
        decision_path = root / 'G' / 's1' / 'program-1' / 'decision.json'
        decision = json.loads(decision_path.read_text())
        changed = {**decision['screen_run'], **gates.screen_decision(8, 3, repeats=3, items=9, fired=9)}
        units.write_json(decision_path, {**decision, 'screen_run': changed})
        if both:
            units.write_json(root / 'G' / 's1' / 'program-1-screen' / 'screen.json', changed)
        recovery(root)
        state = chain.run(root, 'G', services=build(root, stage.Script(), gate_screen=True), resume=True,
                          sleep=lambda s: None)
        expected = (('gate_screen_changed', 's1/program-1-screen') if both
                    else ('gate_decision_changed', 's1/program-1'))
        assert (state['paused']['reason'], state['paused']['unit']) == expected, name
        assert both or state['paused']['detail'] == 'screen_differs'
        assert not (root / 'G' / 's1' / 'library.json').exists() and not (root / 'G' / 's1' / 'frozen.json').exists()


# ---- Codex review of P3b: a stored decision is applied only if the chain's own records give it again ---------------
def killed_after(root, unit, script=None, **kw):
    """The chain of ``build(root, ...)`` killed right after the decision record of ``unit`` was written, before
    anything of it was applied; returns that stored (honest) decision."""
    services = build(root, script if script is not None else stage.Script(), **kw)
    with pytest.MonkeyPatch.context() as patched:
        kill_after_decision(patched, unit)
        with pytest.raises(Kill):
            chain.run(root, 'G', services=services, sleep=lambda s: None)
    return json.loads((root / 'G' / unit / 'decision.json').read_text())


def resumed(root, script=None, **kw):
    """The owner's recovery, then a resume with fresh services of the same fixture; (state, script)."""
    recovery(root)
    script = script if script is not None else stage.Script()
    return chain.run(root, 'G', services=build(root, script, **kw), resume=True, sleep=lambda s: None), script


def assert_paused_unapplied(state, root, unit, detail):
    """Paused gate_decision_changed at ``unit`` with ``detail``, nothing of the stored decision applied: the step went
    no further (no frozen library of s1, no read, the state's current unit is the decision's)."""
    assert (state['paused']['reason'], state['paused']['unit'], state['paused']['detail']) == (
        'gate_decision_changed', unit, detail), state['paused']
    assert not (root / 'G' / 's1' / 'library.json').exists() and not (root / 'G' / 's1' / 'frozen.json').exists()
    assert state['current_unit'] == unit


def forged_rows(record, item, candidate_sum):
    """``record`` with the candidate's run count on ``item`` changed and every derived field rebuilt from the changed
    rows (``chain.recompute_decision``: statistics, verdict, evolution block): coherent in itself, so only the gate's
    cells can betray it."""
    rows = [[row[0], row[1], candidate_sum] if row[0] == item else list(row) for row in record['per_item']]
    forged = chain.recompute_decision({**record, 'per_item': rows})
    assert chain.recompute_decision(forged) == forged and forged != record
    return forged


@pytest.mark.parametrize('item,count,detail', [(24, 0, 'stage'), (31, 2, 'gate_differs')])
def test_a_self_consistent_forgery_of_the_gate_rows_is_refused_on_resume(tmp_path, monkeypatch, item, count, detail):
    """Codex review of P3b, BLOCKER 1. ``variance`` with the screen: the card round passes its screen and is accepted
    on E (attack item 24: B 0 of 3, the card 3 of 3). Killed after its decision record; the card's count on item 24
    set to 0 and every derived field rebuilt from the changed rows -- E, J and the screen record untouched, the record
    coherent (recompute gives it again) -- the forged record refuses the card (gain_below_tau); on the guard item 31
    (3 -> 2) the verdict stays and only the rows and statistics change. Resumed: the decision function on the gate's
    own cells (the incumbent F on B's noise runs, the card's gate unit, R = 3, the sealed J and E) gives the honest
    record, so the chain pauses gate_decision_changed (stage; gate_differs) before anything of it is applied."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    honest = killed_after(tmp_path, 's1/card-r1', rule=variance, gate_screen=True)
    assert (honest['accepted'], honest['screen_run']['passed']) == (True, True)
    assert [row[1:] for row in honest['per_item'] if row[0] in (sq_id(24), sq_id(31))] == [[0, 3], [3, 3]]
    forged = forged_rows(honest, sq_id(item), count)
    assert forged['evolution']['item_ids'] == E() and forged['screen_run'] == honest['screen_run']
    assert (forged['accepted'], forged['reason']) == ((False, 'gain_below_tau') if item == 24 else (True, 'accepted'))
    units.write_json(tmp_path / 'G' / 's1' / 'card-r1' / 'decision.json', forged)
    state, script = resumed(tmp_path, rule=variance, gate_screen=True)
    assert_paused_unapplied(state, tmp_path, 's1/card-r1', detail)
    assert not (tmp_path / 'G' / 's1' / 'programs').exists()
    assert not [call for call in script.calls if call[0] in ('solver', 'selection')]   # the gate's cells were reused


SECOND_ENTRY = {**smoke.HELPER_ENTRY, 'description': 'Lists a second caution for the solver before it answers.'}
SECOND_SOURCE = smoke.HELPER_SOURCE.replace('Read the whole task before answering.', 'Check every date in the context.')


def two_programs(system, user):
    """The engineer proposes two clean programs, slot 1 (the smoke's helper) and slot 2 (``SECOND_SOURCE``); a fix
    request gets the smoke's refused fix."""
    try:
        request = json.loads(user)
    except ValueError:
        request = {}
    request = request if isinstance(request, dict) else {}
    if request.get('request') == 'fix' or request.get('purpose') == 'fix':
        return smoke.FIX_REFUSED
    return smoke.program_reply([(smoke.HELPER_ENTRY, smoke.HELPER_SOURCE), (SECOND_ENTRY, SECOND_SOURCE)])


def second(procedure):
    return 'Check every date' in (procedure.get('source') or '')


def second_program_helps(bench, item, mounted, repeat):
    """The second program mounted: right on the attack items (where B is wrong in every run); else ``b_like``."""
    if bench == 'searchqa' and index(item['task_id']) in A and any(second(p) for p in mounted.get('enabled') or []):
        return 'pass'
    return b_like(bench, item, mounted, repeat)


def two_slots(both_refused):
    """The fixture of two program slots: slot 1 fires on the learn items only (screen_never_fired); slot 2 fires
    everywhere and is accepted (screen b 9, c 9; on the gate +18 runs on the attack items) -- or, with
    ``both_refused``, fires on the learn items only as well."""
    fires = (lambda bench, item, p: index(item['task_id']) < 12 or (second(p) and not both_refused))
    return {'rule': second_program_helps, 'fires': fires, 'gate_screen': True}


@pytest.mark.parametrize('both_refused', [False, True])
def test_a_decision_carrying_another_candidates_screen_is_refused_on_resume(tmp_path, monkeypatch, both_refused):
    """Codex review of P3b, BLOCKER 2. Slot 1 is refused at its screen (screen_never_fired); slot 2 passes its screen
    and its gate and is accepted. Killed after slot 2's decision record, which is replaced by a zero-cell refusal
    holding slot 1's unchanged, valid screen record: resumed, slot 2's decision function on its OWN screen unit
    (``s1/program-2-screen``, its arm, the incumbent F, its procedure id and hash) gives slot 2's own screen, so the
    chain pauses gate_decision_changed (screen_differs). With both slots refused at their screens the forged record
    differs from the honest one in its screen record alone -- the same verdict, reason and zero cells -- and is
    refused for it (the screen check is what sees it)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    kw = two_slots(both_refused)
    script = stage.Script({'replies': {'program_writer': two_programs}})
    honest = killed_after(tmp_path, 's1/program-2', script, **kw)
    first = read(tmp_path, 's1', 'program-1', 'decision.json')
    assert (first['accepted'], first['reason'], first['cells']) == (False, 'screen_never_fired', 0)
    assert first['screen_run']['unit'] == 's1/program-1-screen' and honest['screen_run']['unit'] == 's1/program-2-screen'
    if both_refused:
        assert (honest['accepted'], honest['reason'], honest['cells']) == (False, 'screen_never_fired', 0)
        forged = {**honest, 'screen_run': first['screen_run']}
    else:
        assert (honest['accepted'], honest['screen_run']['passed'], honest['cells']) == (True, True, 60)
        keep = ('kind', 'candidate', 'unit', 'proposal', 'status', 'procedure_id', 'request_sha256', 'screen',
                'mount_snapshot', 'smoke')
        forged = {**{key: honest[key] for key in keep}, 'accepted': False, 'reason': first['screen_run']['reason'],
                  'screen_run': first['screen_run'], 'cells': 0}
    assert chain.recompute_decision(forged) == forged   # coherent in itself
    units.write_json(tmp_path / 'G' / 's1' / 'program-2' / 'decision.json', forged)
    state, script = resumed(tmp_path, stage.Script({'replies': {'program_writer': two_programs}}), **kw)
    assert_paused_unapplied(state, tmp_path, 's1/program-2', 'screen_differs')
    assert not [call for call in script.calls if call[0] in ('solver', 'selection')]


def test_a_program_decision_whose_screen_and_gate_were_left_out_is_refused_on_resume(tmp_path, monkeypatch):
    """Codex review of P3b, BLOCKER 3 for a program: slot 2's accepted decision rewritten as a smoke fault (its
    ordinary fields kept, no screen record, no gate rows, no arms): its smoke cells are clean and its screen and gate
    units hold their records, so the stage is the one they give -- the chain pauses (screen_differs)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    kw = two_slots(False)
    honest = killed_after(tmp_path, 's1/program-2', stage.Script({'replies': {'program_writer': two_programs}}), **kw)
    assert honest['accepted'] is True and honest['smoke']['faults'] == []
    keep = ('kind', 'candidate', 'unit', 'proposal', 'status', 'procedure_id', 'request_sha256', 'screen',
            'mount_snapshot')
    forged = {**{key: honest[key] for key in keep}, 'accepted': False, 'reason': 'smoke_fault',
              'smoke': {**honest['smoke'], 'faults': [{'item_id': sq_id(0), 'faults': ['timeout'], 'failure': None,
                                                        'configuration_error': False}]}}
    units.write_json(tmp_path / 'G' / 's1' / 'program-2' / 'decision.json', forged)
    state, _ = resumed(tmp_path, stage.Script({'replies': {'program_writer': two_programs}}), **kw)
    assert_paused_unapplied(state, tmp_path, 's1/program-2', 'screen_differs')


@pytest.mark.parametrize('screened_step', [True, False])
def test_a_card_decision_whose_screen_and_gate_were_left_out_is_refused_on_resume(tmp_path, monkeypatch,
                                                                                  screened_step):
    """Codex review of P3b, BLOCKER 3: after the accepted (final, round 1 of 1) card round wrote its decision, the
    record keeps its ordinary metadata but loses per_item, evolution and screen_run and says accepted False,
    writer_screens_failed. The writer's record holds the card's text and the screen and gate units hold their
    records, so the stage is the one those give, never the one the missing fields suggest: the chain pauses
    (screen_differs with the screen; without it, under 'evolution' alone, evolution_items) and nothing of the forged
    refusal is applied (no programs unit)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    honest = killed_after(tmp_path, 's1/card-r1', rule=variance, gate_screen=screened_step)
    assert honest['accepted'] is True and ('screen_run' in honest) is screened_step
    meta = ('kind', 'round', 'unit', 'attempts', 'request_sha256', 'examples_unit')
    forged = {**{key: honest[key] for key in meta}, 'accepted': False, 'reason': 'writer_screens_failed'}
    units.write_json(tmp_path / 'G' / 's1' / 'card-r1' / 'decision.json', forged)
    state, _ = resumed(tmp_path, rule=variance, gate_screen=screened_step)
    assert_paused_unapplied(state, tmp_path, 's1/card-r1', 'screen_differs' if screened_step else 'evolution_items')
    assert not (tmp_path / 'G' / 's1' / 'programs').exists()


def test_a_stored_decision_whose_records_are_gone_pauses_and_runs_nothing(tmp_path, monkeypatch):
    """A stored program decision is rebuilt from records alone: with one cell of its gate unit gone (or its screen
    record), the resumed chain sends nothing, writes no screen record and runs no cell, and pauses
    gate_decision_changed (records_missing) before anything of the decision is applied."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    for name, gone in (('cell', 's1/program-1-gate/cells'), ('screen', 's1/program-1-screen/screen.json')):
        root = tmp_path / name
        honest = killed_after(root, 's1/program-1', gate_screen=True)
        assert 'per_item' in honest and honest['screen_run']['passed'] is True
        target = root / 'G' / gone
        (sorted(target.glob('*.json'))[0] if target.is_dir() else target).unlink()
        before = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
        state, script = resumed(root, gate_screen=True)
        assert_paused_unapplied(state, root, 's1/program-1', 'records_missing')
        assert not [call for call in script.calls if call[0] in ('solver', 'selection')], name
        after = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
        assert not [rel for rel in after - before if '/s1/program-1' in rel], name   # nothing re-made there


def test_a_stored_repair_decision_is_rebuilt_from_its_records_and_reproduced(tmp_path, monkeypatch):
    """Under the program learning 'repair' (probe, free repair rounds, the paid feedback round, then the screen and
    the gate): killed after slot 1's decision record and resumed, the decision function rebuilds the decision from
    its records alone (probes, repair records, the learn round's cells, the screen and gate units; nothing sent) and
    finds the same record; the chain completes with every record equal to an uninterrupted run's. The same stored
    decision with a coherently forged gate row pauses (gate_differs or stage)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    kw = {'gate_screen': True, 'program_learning': 'repair'}
    script_a = stage.Script()
    reference, _ = run(tmp_path / 'a', script_a, **kw)
    assert reference['complete'], reference['paused']
    script_b = stage.Script()
    honest = killed_after(tmp_path / 'b', 's1/program-1', script_b, **kw)
    assert 'repair' in honest and 'per_item' in honest and honest['screen_run']['passed'] is True
    state, _ = resumed(tmp_path / 'b', script_b, **kw)
    assert state['complete'], state['paused']
    found, expected = stage.records(tmp_path / 'b'), stage.records(tmp_path / 'a')
    assert sorted(found) == sorted(expected)
    for rel in expected:
        assert found[rel] == expected[rel], rel
    assert Counter(script_b.calls) == Counter(script_a.calls)   # the check sent nothing
    # forged: the same kill, one gate row of the candidate changed and the record rebuilt coherently
    honest = killed_after(tmp_path / 'c', 's1/program-1', **kw)
    item = honest['per_item'][0][0]
    forged = forged_rows(honest, item, (honest['per_item'][0][2] + 1) % 4)
    units.write_json(tmp_path / 'c' / 'G' / 's1' / 'program-1' / 'decision.json', forged)
    state, _ = resumed(tmp_path / 'c', **kw)
    assert state['paused']['reason'] == 'gate_decision_changed' and state['paused']['detail'] in ('gate_differs',
                                                                                                    'stage')
    assert state['paused']['unit'] == 's1/program-1'


def test_the_difference_of_two_decisions_is_named_by_its_first_differing_part():
    """``chain.decision_difference``: canonical JSON on both sides (a tuple and a list are the same row, key order
    plays no part) and a smoke's fault list in any order (``program_decision`` lists its faults in the order the smoke
    cells came back, a resumed unit's stored cells in file order); otherwise the first differing part in
    ``DECISION_DIFFERENCES`` order, whichever side is the stored one."""
    faults = [{'item_id': 'a', 'faults': ['x']}, {'item_id': 'b', 'faults': ['y']}]
    base = {'kind': 'program', 'accepted': True, 'reason': 'accepted', 'per_item': [['a', 0, 3]], 'screen_run': {'b': 1},
            'smoke': {'items': 2, 'faults': faults}, 'baseline': {'unit': 'u'}}
    same = {**base, 'per_item': [('a', 0, 3)], 'smoke': {'faults': faults[::-1], 'items': 2}}
    assert chain.decision_difference(base, same) is None
    cases = {'screen_differs': {**base, 'screen_run': {'b': 2}},
             'evolution_items': {**base, 'evolution': {'item_ids': ['a']}},
             'stage': {**base, 'accepted': False},
             'gate_differs': {**base, 'per_item': [['a', 0, 2]]},
             'not_reproduced': {**base, 'note': 1}}
    for code, other in cases.items():
        assert chain.decision_difference(base, other) == code == chain.decision_difference(other, base), code
    assert chain.decision_difference({**base, 'screen_run': {'b': 2}, 'accepted': False}, base) == 'screen_differs'
    assert chain.decision_difference({k: v for k, v in base.items() if k != 'screen_run'}, base) == 'screen_differs'
    assert chain.decision_difference(None, base) == 'not_reproduced'
    assert chain.DECISION_DIFFERENCES == ('screen_differs', 'evolution_items', 'stage', 'gate_differs',
                                          'not_reproduced')


# ==== E: the preset end to end -- both chains, five steps, a fresh read after every step, kills ======================
from skillopt.execskill.typed import itemstage, items as items_, reads  # noqa: E402
from skillopt.execskill.typed.items import store as store_  # noqa: E402
from tests.test_typed2_base import Capture, exact_embedder  # noqa: E402
from tests.test_typed3_reads import (C_EVENTS, LoggedCapture, expected_done, kill_now, sha256, snapshot,  # noqa: E402
                                     state_record, unit_of_request)

TREE = Path(run_typed.__file__).resolve().parents[1]
MADE = ('searchqa', 'zebralogic', 'alfworld')   # the benches with made items (OfficeQA B36, SpreadsheetBench B3: none)
ANALYST = json.dumps({'weaknesses': [], 'guards': [{'description': 'Tasks the solver gets right.', 'spec': {}}],
                      'note': 'fake'})


class FakeMaker:
    """A maker for the five synthetic benches (P2a's makers need real pools: a ZebraLogic language, ALFWorld task
    folders): the counts of ``inp.counts`` as new items in the bench's synthetic shape (``smoke.SYNTHETIC_ITEMS``),
    each written to the unit's store under its slot with its record (source 'made', a certificate), in listing order;
    deterministic, so a resumed unit makes the same items. With no kept weakness (the analyst names none) every
    count is the 20 % rule's, the smoke table's fixed point."""
    built = True

    def __init__(self, bench):
        self.bench = bench

    def capability_sheet(self, *, pool=None, learn_ids=None, gate_ids=None):
        return {'maker': 'fake-' + self.bench, 'what': 'Copies of the synthetic practice items.', 'fields': {}}

    def public_kind(self, item):
        return {}

    def make(self, inp):
        inp.check()
        records, slots = [], []
        for side, order in (('judging', ('attack', 'guard', 'calibration')), ('shown', ('attack', 'guard'))):
            for cls in order:
                for n in range(1, inp.counts[side][cls] + 1):
                    slot = store_.slot_name(side, cls, None, n)
                    item_id = '%s-made-s%d-r%d-%s' % (self.bench, inp.identity['step'], inp.identity.get('round', 1),
                                                      slot)
                    public, private = smoke.SYNTHETIC_ITEMS[self.bench](item_id)
                    item = {'benchmark': self.bench, 'task_id': item_id, 'public': public, 'private': private,
                            **({'task': '3*2'} if self.bench == 'zebralogic' else {})}
                    record = items_.item_record(item=item_id, cls=cls, weakness=None, side=side, family='f-' + item_id,
                                                source='made', certificate={'fake': True},
                                                item_sha256=items_.item_sha256(self.bench, item))
                    inp.store.write_item(slot, item)
                    inp.store.write_slot(slot, record=record, shortfall=None, attempts=[1])
                    inp.registry.add(record)
                    records.append(record)
                    slots.append({'slot': slot, 'item': item_id})
        return {'bench': self.bench, 'status': 'made', 'reason': None, 'records': records, 'slots': slots,
                'shortfalls': [], 'made_counts': items_.made_counts(records), 'record': {'version': items_.RECORD_VERSION}}


REAL_MAKER = itemstage._maker
FAKE_MAKERS = {bench: FakeMaker(bench) for bench in MADE}


def fake_maker(bench):
    return FAKE_MAKERS.get(bench) or REAL_MAKER(bench)


def install_fake_makers():
    """For a child process (the kill tests): the fake makers in place of P2a's, for the whole process."""
    itemstage._maker = fake_maker


@pytest.fixture
def fake_makers(monkeypatch):
    monkeypatch.setattr(itemstage, '_maker', fake_maker)


def preset_manifest():
    """The synthetic manifest (``smoke.synthetic_manifest``) with exactly the values of the typed-v3 smoke preset
    (``prepare.typed_v3_preset(smoke=True)``): what ``prepare --smoke --typed-v3`` seals."""
    preset = prepare.typed_v3_preset(smoke=True)
    made = smoke.synthetic_manifest(schedule=preset['schedule'], memory_lock=preset['memory_lock'],
                                    base_card=preset['base_card'], read_plan=preset['read_plan'])
    made.update(read_anchors=list(preset['read_anchors']), arms=list(readplan.read_events(preset['read_anchors'])),
                program_learning=preset['program_learning'], archive=archives.sealed(preset['archive']),
                item_stage=preset['item_stage'], item_quotas=preset['item_quotas'], gate_rule=preset['gate_rule'],
                gate_screen=preset['gate_screen'], resume_replay=preset['resume_replay'])
    return made


def preset_services(root, chain_name, script=None):
    """Fake services through the REAL mount, writers and reads on the smoke's practice panels with the smoke's slices
    and limits (one card round), exact family embeddings, the analyst's scripted plan (no weakness, one guard)."""
    script = script if script is not None else Capture({'replies': {'item_analyst': ANALYST}})
    services = smoke.fake_services(root, chain_name, preset_manifest(), scripted=script)
    services.embed = exact_embedder
    services.slices = smoke.smoke_slices(services.items, services.slices)
    services.limits = dict(smoke.SMOKE_LIMITS)
    return services


def decisions_of(chain_dir, k):
    return json.loads((Path(chain_dir) / ('s%d' % k) / 'decisions.json').read_text())


def gated_rows(decisions):
    return [row for row in decisions['cards'] + decisions['programs'] if 'per_item' in row]


def check_preset_chain(root, chain_name, state, services):
    """What a complete chain of the preset holds (both chains alike): the read events C, S1..S5 after each step and
    never C0; on a step with made items J = R (3) + A (1) + G (2) + K (2), every card decided on E = R + A of its
    sealed items.json, every candidate that reached a gate (card rounds, programs, the archive package) screened on A +
    G first in its own unit; on OfficeQA's and SpreadsheetBench's steps J = R, typed-v2's card rule, no screen."""
    chain_dir = root / chain_name
    assert state['complete'] and state['paused'] is None, state['paused']
    assert (state['read_anchors'], state['gate_rule'], state['gate_screen'], state['item_stage'],
            state['program_learning']) == (['C'], 'evolution', True, 'planned', 'repair')
    done = state['done_units']
    assert done == expected_done(done, C_EVENTS)
    assert not [unit for unit in done if 'C0' in unit] and not [p for p in chain_dir.rglob('*') if 'C0' in p.name]
    phases = [unit_of_request(unit) for _, unit, _, _ in services.script.requests]
    for k in range(1, 6):
        reading = [i for i, phase in enumerate(phases) if phase == ('read', 'S%d' % k)]
        learning = [i for i, phase in enumerate(phases) if phase == ('learn', k)]
        later = [i for i, phase in enumerate(phases) if phase[0] == 'learn' and phase[1] > k]
        assert reading and learning and max(learning) < min(reading) and (not later or max(reading) < min(later)), k
    for k, bench in enumerate(typed_.ORDER, 1):
        decisions = decisions_of(chain_dir, k)
        sealed = itemstage._read_sealed(chain_dir / ('s%d' % k) / 'items.json', chain_name, k, bench)
        rule = decisions['gate_rule']
        rows = gated_rows(decisions)
        assert rows, (k, bench)
        if bench in MADE:
            lists = sealed['lists']['judging']
            real = list(services.slices[bench]['gate'])
            attack, guard = ([e['record']['item'] for e in lists[cls]] for cls in ('attack', 'guard'))
            calibration = [e['record']['item'] for e in lists['calibration']]
            assert (len(real), len(attack), len(guard), len(calibration)) == (3, 1, 2, 2), (k, bench)
            assert rule == {'rule': 'evolution', 'screen': True, 'card_rule': 'evolution', 'gate_items': 8,
                            'evolution_items': 4, 'screened': True, 'screen_items': {'attack': 1, 'guard': 2}}
            for row in rows:
                assert [item for item, _, _ in row['per_item']] == real + attack + guard + calibration
                assert row['screen_run']['item_ids'] == attack + guard and row['screen_run']['passed'] is True
                unit = row['screen_run']['unit']
                assert json.loads((chain_dir / unit / 'screen.json').read_text()) == row['screen_run']
                assert len(list((chain_dir / unit / 'cells').glob('*.json'))) == 3
                assert (row['kind'] == 'card') == ('evolution' in row)
                if row['kind'] == 'card':
                    assert row['evolution']['item_ids'] == real + attack and row['screen_run']['fired'] is None
                else:
                    assert row['screen_run']['fired'] >= 1 and row['screen_run']['procedures']
                assert chain.recompute_decision(row) == row
            if bench in ('zebralogic', 'alfworld'):   # the chain's archive package of the index, candidate 0
                archive = decisions['programs'][0]
                assert archive['origin'] == 'archive' and archive['package'] == archives.sealed('index')[chain_name][
                    bench]['package']
                assert archive['screen_run']['procedures'] == archive['procedure_ids']
                assert archive['screen_run']['unit'] == 's%d/program-0-screen' % k
        else:
            assert sealed['reason'] in ('audit_bing_B36', 'maker_not_built') and decisions['items']['gate']['total'] == 3
            assert rule == {'rule': 'evolution', 'screen': True, 'card_rule': 'whole', 'gate_items': 3,
                            'evolution_items': None, 'screened': False, 'screen_items': {'attack': 0, 'guard': 0}}
            assert all('evolution' not in row and 'screen_run' not in row for row in rows)
            assert not list((chain_dir / ('s%d' % k)).glob('*-screen'))
            assert not list((chain_dir / ('s%d' % k)).glob('diagnose'))


@pytest.mark.parametrize('chain_name', ['G', 'D'])
def test_both_chains_of_the_preset_complete_five_steps_with_a_fresh_read_after_every_step(tmp_path, fake_makers,
                                                                                         chain_name):
    root = tmp_path / 'preset-smoke'
    services = preset_services(root, chain_name)
    state = chain.run(root, chain_name, services=services, sleep=lambda s: None)
    check_preset_chain(root, chain_name, state, services)
    # every read cell was solved in this run and mounts its own step's frozen state (P3r's reads, unchanged)
    assert sorted(state['read_mounts']) == sorted(C_EVENTS)
    assert run_typed.state_summary(state, root / chain_name)['read_plan']['reads']['settled'] == 30


# ---- kills of the preset chain: a SIGKILL of a child process at a chosen point (P3r's method) -----------------------
CHILD = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, %(tree)r)
from skillopt.execskill.typed import chain
from tests import test_typed3_gate_rule as t
t.install_fake_makers()
root, chain_name = Path(%(root)r), %(chain)r
services = t.preset_services(root, chain_name, script=t.LoggedCapture(%(log)r, {'replies': {'item_analyst': t.ANALYST}}))
t.arm_kill(services, root / chain_name, %(point)r)
state = chain.run(root, chain_name, services=services, sleep=lambda s: None)
print(json.dumps({'not_killed': True, 'paused': state['paused']}))
'''


def arm_kill(services, chain_dir, point):
    """The child's kill point. 'read:<event>-<bench>': inside that read unit's second panel cell, once another unit of
    the event has a record (P3r's 'cell' point). 'cell:<unit>:<n>': at the n-th solve of a learning unit, before its
    send (a screen unit; a gate unit's first cell: between its screen and its gate). 'screen-record:<unit>': right
    after that screen unit's screen.json was written, before anything else. 'decision:<unit>': right after that
    unit's decision record was written, before anything of it is applied (the resume rebuilds it from its records).
    'flushed:<unit>': right after the solve of one cell of that unit returned -- its receipt in its calls file, its
    record not written -- while no other cell of the unit has sent anything (B6 d's window)."""
    kind, _, where = point.partition(':')
    if kind == 'read':
        event, bench = where.split('-', 1)
        target, solve, count = reads.unit_name(event, bench, smoke=True), services.solve_fn, []
        others = [chain_dir / reads.unit_name(event, b, smoke=True) / 'cells' for b in typed_.ORDER if b != bench]

        def killing(bench_, item, mounted, *, unit, **kw):
            if unit == target:
                count.append(item['task_id'])
                if len(count) == 2:
                    import time
                    deadline = time.time() + 60
                    while time.time() < deadline and not any(d.is_dir() and any(d.glob('*.json')) for d in others):
                        time.sleep(0.01)
                    kill_now()
            return solve(bench_, item, mounted, unit=unit, **kw)
        services.solve_fn = killing
    elif kind == 'cell':
        unit_name, n = where.rsplit(':', 1)
        solve, count = services.solve_fn, []

        def killing(bench_, item, mounted, *, unit, **kw):
            if unit == unit_name:
                count.append(item['task_id'])
                if len(count) == int(n):
                    kill_now()
            return solve(bench_, item, mounted, unit=unit, **kw)
        services.solve_fn = killing
    elif kind == 'decision':
        verify = chain._Run.verify_decision

        def killing(self, unit, *args, **kw):
            found = verify(self, unit, *args, **kw)
            if unit == where:
                kill_now()
            return found
        chain._Run.verify_decision = killing
    elif kind == 'flushed':
        # the first cell of the unit to ask for a recorder is solved; every other cell of the unit waits before its
        # first recorder (so it sends nothing); right after that cell's solve returned -- its receipt flushed to its
        # calls file and settled, its cell record not yet written -- the process dies
        import threading
        import time
        make, solve, chosen, lock = services.solver_call, services.solve_fn, [], threading.Lock()

        def solver_call(bench_, unit, tag, **kw):
            if unit == where:
                with lock:
                    if not chosen:
                        chosen.append(tag)
                while tag != chosen[0]:
                    time.sleep(1)   # never returns: the kill ends the process
            return make(bench_, unit, tag, **kw)

        def killing(bench_, item, mounted, *, unit, **kw):
            row = solve(bench_, item, mounted, unit=unit, **kw)
            if unit == where:
                kill_now()
            return row
        services.solver_call, services.solve_fn = solver_call, killing
    else:
        assert kind == 'screen-record', point
        record = chain._Run.screen_record

        def killing(self, unit, *args, **kw):
            found = record(self, unit, *args, **kw)
            if unit == where:
                kill_now()
            return found
        chain._Run.screen_record = killing


@pytest.fixture(scope='module')
def clean_preset_runs():
    """One uninterrupted run of the preset per chain (the reference records and requests), shared by the kill cases."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='gate3-clean-', dir=NEUTRAL))
    out = {}
    try:
        with pytest.MonkeyPatch.context() as patched:   # the fake makers for these runs only (closed before the yield)
            patched.setattr(itemstage, '_maker', fake_maker)
            for chain_name in ('G', 'D'):
                root = base / ('clean-%s-smoke' % chain_name)
                services = preset_services(root, chain_name)
                state = chain.run(root, chain_name, services=services, sleep=lambda s: None)
                check_preset_chain(root, chain_name, state, services)
                out[chain_name] = {'root': root, 'state': state, 'snapshot': snapshot(root / chain_name),
                                   'requests': Counter((p, u, sha256(s + '\x00' + x))
                                                       for p, u, s, x in services.script.requests)}
        assert itemstage._maker is REAL_MAKER
        yield out
    finally:
        shutil.rmtree(base, ignore_errors=True)


def without_resent(found, after_kill, requests):
    """The snapshot ``found`` of a resumed preset chain with, in the calls files of every cell that had NO record at
    the kill, each send that the kill interrupted inside the client (no receipt, no exception) and that the resume sent
    again (a later send of the same request and occurrence follows it in the file) left out. The resume replay of B6
    (d) keeps such a send in its calls file -- it may have been billed -- and sends the call again; the uninterrupted
    run's file holds it once. A cell with a record at the kill keeps its file exactly; every send left out is a request
    the uninterrupted run sent (``requests``). Returns (snapshot, the sends left out)."""
    out, dropped = {}, []
    for rel, value in found.items():
        parts = rel.split('/')
        if len(parts) < 3 or parts[-2] != 'calls' or not isinstance(value, list):
            out[rel] = value
            continue
        unit, stem = '/'.join(parts[:-2]), parts[-1][:-len('.json')]
        tag, purpose = (stem[:-len('-selection')], 'selection') if stem.endswith('-selection') else (stem, 'solver')
        if (unit, tag) in after_kill:
            out[rel] = value
            continue
        kept = []
        for n, send in enumerate(value):
            later = [row for row in value[n + 1:] if isinstance(row, dict)
                     and (row.get('request_sha256'), row.get('occurrence')) == (send.get('request_sha256'),
                                                                               send.get('occurrence'))]
            if isinstance(send, dict) and send.get('receipt') is None and not send.get('exception') and later:
                assert (purpose, unit, send['request_sha256']) in requests, (rel, n)
                dropped.append((rel, n))
                continue
            kept.append(send)
        out[rel] = kept
    return out, dropped


PRESET_KILLS = [('G', 'read:S2-officeqa'), ('D', 'read:S3-zebralogic'), ('G', 'cell:s3/card-r1-screen:2'),
                ('D', 'cell:s5/program-0-screen:2'), ('G', 'screen-record:s3/program-0-screen'),
                ('D', 'cell:s1/card-r1:1'), ('G', 'cell:s5/program-1-gate:1'),
                # a stored repair-flow decision (probe, repairs, paid round, screen, gate) rebuilt from its records
                ('D', 'decision:s5/program-1')]


@pytest.mark.parametrize('chain_name,point', PRESET_KILLS)
def test_a_kill_of_the_preset_chain_resumes_to_the_records_of_an_uninterrupted_run(tmp_path, clean_preset_runs,
                                                                                   fake_makers, chain_name, point):
    """A SIGKILL of the chain process in the middle of a read event, inside a screen unit (a card round's, the archive
    package's), right after a screen record, and at the first cell of a gate after its screen (between the screen and
    the gate); then the owner's recovery and a resume in a new process: every file of the chain directory (clock values
    stripped), the done units in their order and the read entries equal those of an uninterrupted run; no cell with a
    record at the kill is built again, and a request is sent twice only for a cell that had no record."""
    root, log = tmp_path / 'killed-smoke', tmp_path / 'sends.jsonl'
    env = {key: value for key, value in __import__('os').environ.items() if key != 'PYTHONPATH'}
    env['TMPDIR'] = str(NEUTRAL)
    code = CHILD % {'tree': str(TREE), 'root': str(root), 'chain': chain_name, 'log': str(log), 'point': point}
    import signal
    import subprocess
    import sys
    killed = subprocess.run([sys.executable, '-c', code], cwd=str(TREE), env=env, capture_output=True, text=True,
                            timeout=600)
    assert killed.returncode == -signal.SIGKILL, (killed.stdout[-2000:], killed.stderr[-3000:])
    chain_dir = root / chain_name
    after_kill = {(str(p.parent.parent.relative_to(chain_dir)), p.stem) for p in chain_dir.rglob('cells/*.json')}
    state = json.loads((chain_dir / 'state.json').read_text())
    assert state['complete'] is False and state['paused'] is None  # a kill records nothing
    kind, _, where = point.partition(':')
    if kind == 'cell':
        unit = where.rsplit(':', 1)[0]
        assert unit.endswith('-screen') or (chain_dir / unit / 'plan.json').exists()
        if not unit.endswith('-screen'):   # between the screen and the gate: the screen is complete, no gate cell yet
            stem = unit[:-len('-gate')] if unit.endswith('-gate') else unit
            assert (chain_dir / (stem + '-screen') / 'screen.json').exists()
            assert not list((chain_dir / unit / 'cells').glob('*.json'))   # a unit's first cell runs alone
    elif kind == 'screen-record':
        assert (chain_dir / where / 'screen.json').exists()
        stem = where[:-len('-screen')]
        assert not (chain_dir / (stem + '-gate') / 'plan.json').exists()
    elif kind == 'decision':   # the record is there, nothing after it (the step's frozen library) is
        stored = json.loads((chain_dir / where / 'decision.json').read_text())
        assert 'per_item' in stored and 'repair' in stored and stored['screen_run']['passed'] is True
        assert not (chain_dir / where.split('/')[0] / 'library.json').exists()
    recovery(root, chain_name, 'resume after a kill')
    services = preset_services(root, chain_name)
    built, solver_call = [], services.solver_call
    services.solver_call = lambda bench, unit, tag, **kw: built.append((unit, tag)) or solver_call(bench, unit, tag, **kw)
    resumed = chain.run(root, chain_name, services=services, sleep=lambda s: None, resume=True)
    clean = clean_preset_runs[chain_name]
    assert resumed['complete'] and resumed['paused'] is None
    assert [r['paused'] for r in resumed['recoveries']] == [None]
    assert state_record(resumed) == state_record(clean['state'])
    # a call the kill interrupted inside the client (another cell's, in flight) stays in its calls file and is sent
    # again under the preset's resume replay (B6 d): that send aside, every file equals the uninterrupted run's
    found, dropped = without_resent(snapshot(chain_dir), after_kill, clean['requests'])
    assert sorted(found) == sorted(clean['snapshot'])
    for rel in clean['snapshot']:
        assert found[rel] == clean['snapshot'][rel], rel
    assert not set(built) & after_kill  # no cell with a record at the kill was built (no paid call repeated)
    sent = Counter(tuple(json.loads(line)) for line in log.read_text().splitlines())
    sent += Counter((p, u, sha256(s + '\x00' + x)) for p, u, s, x in services.script.requests)
    assert not clean['requests'] - sent  # nothing the uninterrupted run sent is missing
    extra = sent - clean['requests']     # sent twice: only requests of cells that had no record at the kill
    # after a decision record nothing is in flight, and the stored decision is rebuilt from records alone (records-only
    # mode never reaches a recorder, the replay or the ledger): nothing at all is sent twice
    assert kind != 'decision' or not (extra or dropped), (extra, dropped)
    for purpose, unit, request in extra.elements():
        assert purpose in ('solver', 'selection'), (purpose, unit)
        key = 'request_sha256' if purpose == 'solver' else 'selection_request_sha256'
        owners = [path.stem for path in (chain_dir / unit / 'cells').glob('*.json')
                  if request in (json.loads(path.read_text()).get(key) or [])]
        assert owners and not {(unit, tag) for tag in owners} & after_kill, (purpose, unit)


def test_under_the_preset_a_screen_cell_killed_after_its_reply_was_saved_resumes_with_no_new_send(tmp_path,
                                                                                                 clean_preset_runs,
                                                                                                 fake_makers):
    """B6 (d) under the full --typed-v3 preset (its resume replay 'on'): the screen runs through ``_Run.cells``, so the
    replay covers its cells as every learning unit's. A SIGKILL right after one cell of chain G's screen unit
    s3/card-r1-screen was solved -- its reply saved in the cell's calls file, its record not written -- while the
    unit's other cells had sent nothing; then the owner's recovery and a resume in a new process: that cell is
    answered from its calls file (no new send), the other cells run once, and every request of the uninterrupted run is
    sent exactly as often as there (zero new sends), with every record, the done units and the read entries equal."""
    chain_name, unit = 'G', 's3/card-r1-screen'
    root, log = tmp_path / 'killed-smoke', tmp_path / 'sends.jsonl'
    env = {key: value for key, value in __import__('os').environ.items() if key != 'PYTHONPATH'}
    env['TMPDIR'] = str(NEUTRAL)
    code = CHILD % {'tree': str(TREE), 'root': str(root), 'chain': chain_name, 'log': str(log),
                    'point': 'flushed:' + unit}
    import signal
    import subprocess
    import sys
    killed = subprocess.run([sys.executable, '-c', code], cwd=str(TREE), env=env, capture_output=True, text=True,
                            timeout=600)
    assert killed.returncode == -signal.SIGKILL, (killed.stdout[-2000:], killed.stderr[-3000:])
    chain_dir = root / chain_name
    assert preset_manifest()['resume_replay'] == 'on'
    calls = {path.stem: json.loads(path.read_text()) for path in (chain_dir / unit / 'calls').glob('*.json')}
    solved = [tag for tag in calls if not tag.endswith('-selection')]
    assert len(solved) == 1 and not list((chain_dir / unit / 'cells').glob('*.json'))   # one reply, no record yet
    assert [send['receipt']['ok'] for send in calls[solved[0]]] == [True]                # the reply was saved
    before = [row for row in (json.loads(line) for line in log.read_text().splitlines()) if row[1] == unit]
    assert [row[0] for row in before if row[0] == 'solver'] == ['solver']                # sent once before the kill
    recovery(root, chain_name, 'resume after a kill')
    services = preset_services(root, chain_name)
    resumed = chain.run(root, chain_name, services=services, sleep=lambda s: None, resume=True)
    clean = clean_preset_runs[chain_name]
    assert resumed['complete'] and resumed['paused'] is None
    assert state_record(resumed) == state_record(clean['state'])
    found = snapshot(chain_dir)
    assert sorted(found) == sorted(clean['snapshot'])
    for rel in clean['snapshot']:
        assert found[rel] == clean['snapshot'][rel], rel
    sent = Counter(tuple(json.loads(line)) for line in log.read_text().splitlines())
    sent += Counter((p, u, sha256(s + '\x00' + x)) for p, u, s, x in services.script.requests)
    assert sent == clean['requests']   # zero new sends: nothing missing, nothing sent twice
    items_screened = len(json.loads((chain_dir / unit / 'screen.json').read_text())['item_ids'])
    assert sum(1 for p, u, _, _ in services.script.requests if (p, u) == ('solver', unit)) == items_screened - 1


# ==== F: the readout additions (brief P3b C; T9) ======================================================================
def test_the_readout_reports_the_items_the_rules_the_screens_the_repairs_and_the_archive_apart(clean_preset_runs):
    """Per step, from its decisions.json alone: the item block, the step's rules, every candidate's evolution block,
    screen record, gains by class and parity, the programs' repair history, and the archive package's own gate decision
    apart from the step's later candidates with the T9 statement; the markdown renders each of them."""
    for chain_name in ('G', 'D'):
        root = clean_preset_runs[chain_name]['root']
        chain_dir = root / chain_name
        for open_sealed in (False, True):
            doc = readout.chain_readout(root, chain_name, open_sealed=open_sealed, stamp='x')
            assert doc['read_anchors'] == ['C']
            if open_sealed:   # rows C, S1..S5 only: no C0 row, no contrast with C0 (P3r's C-only readout)
                for bench in typed_.ORDER:
                    panel = doc['panels'][bench]
                    assert panel['events'] == list(C_EVENTS) and 'C0' not in panel['per_event']
                    assert not [name for name in panel['pairs'] if 'C0' in name]
            for k, bench in enumerate(typed_.ORDER, 1):
                block, decisions = doc['steps'][k]['typed_v3'], decisions_of(chain_dir, k)
                assert block == readout.typed_v3_step(decisions)
                items = decisions['items']
                assert block['items']['counts'] == items['counts'] and block['items']['gate'] == items['gate']
                assert block['items']['reason'] == items['reason'] and block['gate_rule'] == decisions['gate_rule']
                assert [c['round'] for c in block['items']['checks']] == [c['round'] for c in items['checks']]
                rows = decisions['cards'] + decisions['programs']
                assert len(block['candidates']) == len(rows)
                for found, row in zip(block['candidates'], rows):
                    assert (found['accepted'], found['reason'], found['by_class']) == (row['accepted'], row['reason'],
                                                                                       row['by_class'])
                    evolution = row.get('evolution')
                    assert found['evolution'] == (None if evolution is None else {
                        key: evolution[key] for key in readout.EVOLUTION_KEYS})
                    screen = row.get('screen_run')
                    assert found['screen'] == (None if screen is None else {key: screen[key]
                                                                            for key in readout.SCREEN_KEYS})
                    if row.get('repair'):
                        assert (found['repair']['rounds'], found['repair']['kept_round'], found['repair']['stop']) == (
                            row['repair']['rounds'], row['repair']['kept_round'], row['repair']['stop'])
                        assert found['repair']['paid_round']['fixed'] == row['learn']['fixed']
                    assert 'item_ids' not in json.dumps({'e': found['evolution'], 's': found['screen']})
                if bench in ('zebralogic', 'alfworld'):
                    archive = block['archive']
                    row = decisions['programs'][0]
                    assert (archive['kind'], archive['package'], archive['accepted'], archive['reason']) == (
                        'archive', row['package'], row['accepted'], row['reason'])
                    assert archive['later_candidates'] == len(decisions['programs']) - 1
                    assert archive['later_candidates_judged_against'] == decisions['program_learning'][
                        'engineer_gate_current']
                    assert archive['archive_known'] == readout.ARCHIVE_KNOWN
                else:
                    assert 'archive' not in block
            text = readout.markdown(doc)
            assert text.count('Item stage (CHAIN-DECISIONS T3 to T5)') == 5
            assert text.count('cards of this step decided on E = R + A (4 of the 8 items of J') == 3
            assert 'no item made (audit_bing_B36): J = R' in text and 'no item made (maker_not_built): J = R' in text
            assert text.count('once on A + G before every gate (1 attack, 2 guard items)') == 3
            assert text.count(readout.ARCHIVE_KNOWN) == 2 and readout.SCREEN_NOTE in text
            assert text.count('archive (program 0)') == 2 and 'archive package ' in text


def test_a_typed_v2_style_step_has_no_typed_v3_block(tmp_path, monkeypatch):
    """A chain without the typed-v3 options: its steps' readout entries carry no typed_v3 block and the markdown no
    typed-v3 line (the readout of every typed-v2 style root is as before)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    state, _ = run(tmp_path, stage='none', gate_rule=None, gate_screen=None)
    assert state['complete'], state['paused']
    doc = readout.chain_readout(tmp_path, 'G', stamp='x', order=('searchqa',))
    assert doc['steps'] and all('typed_v3' not in step for step in doc['steps'].values())
    assert readout.typed_v3_step(decisions_of(tmp_path / 'G', 1)) is None
    text = readout.markdown(doc)
    assert 'Item stage' not in text and 'gate rule' not in text and 'archive package' not in text


# ==== G: the consent of the preset's read arms; a later step's analyst and a screen refusal ===========================
def test_the_preset_reads_under_the_owners_consent_of_exactly_C_and_S1_to_S5(tmp_path, fake_makers):
    """The preset's anchors ('C',) plan the read events C, S1..S5 (prepare seals them as ``arms``): in run mode every
    read unit checks the owner's consent naming exactly them (``reads.consent``, unchanged) before its panel opens; a
    consent of typed-v2's seven arms is refused at the first read (C) before any panel opens."""
    from tests.test_typed3_reads import run_services, write_consent
    assert readplan.read_events(prepare.TYPED_V3_PRESET['read_anchors']) == C_EVENTS == tuple(PRESET_FIELDS['arms'])
    for name, arms, complete in (('six', C_EVENTS, True), ('seven', typed_.READ_ARMS, False)):
        root, seen = tmp_path / name, []
        write_consent(root, arms)
        script = Capture({'replies': {'item_analyst': ANALYST}})
        services = run_services(root, 'G', preset_manifest(), seen=seen, script=script, order=('searchqa',))
        state = chain.run(root, 'G', services=services, sleep=lambda s: None)
        if complete:
            assert state['complete'], state['paused']
            assert seen == [('searchqa', 'G/test-read-%s-searchqa' % event) for event in ('C', 'S1')]
        else:
            assert (state['paused']['reason'], state['paused']['unit']) == ('exception:ValueError', 'read-C')
            assert seen == [] and not (root / 'G' / 's1').exists()


def test_a_later_steps_analyst_sees_a_screen_refusal_as_a_short_label(tmp_path, monkeypatch):
    """SearchQA (step 1) under ``screen_short``: its card round and program are refused at their screens; ZebraLogic
    (step 2, P2b's puzzle pool and maker) gets them in the analyst's experience log as refused candidates with the
    reason label screen_below_baseline and no gain (they never reached a gate)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    script = stage.Script()
    state, _ = run(tmp_path, script, rule=screen_short, gate_screen=True, order=('searchqa', 'zebralogic'))
    assert state['complete'], state['paused']
    (request,) = [json.loads(user.split('\n\nFormat retry')[0]) for purpose, unit, _, user in script.requests
                  if purpose == 'item_analyst' and unit == 's2/items-plan']
    (step_1,) = request['experience']
    refused = [row for row in step_1['candidates'] if row['reason'] == 'screen_below_baseline']
    assert [(row['kind'], row['decision'], row['gain_points'], row['n']) for row in refused] == [
        ('card', 'refused', None, None), ('program', 'refused', None, None)]
    assert read(tmp_path, 's2', 'items.json')['reason'] is None


def test_a_shared_type_screens_and_decides_on_the_home_bench_and_checks_its_member_on_its_real_slice(tmp_path,
                                                                                                    monkeypatch):
    """OfficeQA (step 1, no made items) opens the type; SearchQA (step 2, made items) joins it (no harm: the type holds
    no skill), so OfficeQA is a member of step 2's home type. ``variance`` on SearchQA, no card effect on OfficeQA. The
    step-2 card round: its screen on SearchQA's A + G (b = 1 + 2 + 2 + 3 = 8 from B's runs on 20, 23, 27, 31; c = 4: the
    card's one run is right on 24, 23, 27, 31) passes; its rule on E = R + A as in the single-bench case (D_E 3, Q_E 2:
    accepted); then the member check on OfficeQA's real gate slice (no regression: D = 0) -- accepted, its record
    rebuilt by recompute with the member check and the evolution block."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    state, _ = run(tmp_path, rule=variance, gate_screen=True, order=('officeqa', 'searchqa'))
    assert state['complete'], state['paused']
    decisions = read(tmp_path, 's2', 'decisions.json')
    assert not decisions['typing']['new_type'] and [row['bench'] for row in decisions['shared_type']] == ['officeqa']
    card = read(tmp_path, 's2', 'card-r1', 'decision.json')
    assert (card['accepted'], card['reason'], card['member_harm']) == (True, 'accepted', None)
    assert (card['screen_run']['b'], card['screen_run']['c'], card['screen_run']['passed']) == (8, 4, True)
    assert card['evolution']['item_ids'] == E() and (card['evolution']['difference_sum'],
                                                      card['evolution']['variance_sum']) == (3, 2)
    (member,) = card['members']
    assert (member['bench'], member['no_regress'], member['difference_sum'], member['n']) == ('officeqa', True, 0, 6)
    assert chain.recompute_decision(card) == card
    plans = stage.gate_plans(tmp_path, 2)
    assert plans['card-r1-member-officeqa']['items'] == ['officeqa-%02d' % n for n in range(4, 10)]
    assert read(tmp_path, 's1', 'decisions.json')['gate_rule']['card_rule'] == 'whole'


def test_the_description_override_of_a_screened_program_reproduces_and_no_other_override_does(clean_preset_runs):
    """A gate-accepted program whose describer reply never parsed is refused with description_failed (typed-v2's one
    legal override, ``gate_verdict``): with its screen record beside it the record still rebuilds from itself; the same
    override on a record whose screen did not pass, or of a gate that refused, does not."""
    chain_dir = clean_preset_runs['G']['root'] / 'G'
    decision = json.loads((chain_dir / 's1' / 'program-1' / 'decision.json').read_text())
    assert decision['accepted'] is True and decision['screen_run']['passed'] is True
    override = {**decision, 'accepted': False, 'reason': 'description_failed', 'description': {'description': None},
                'gate_verdict': {'accepted': True, 'reason': 'accepted'}}
    assert chain.recompute_decision(override) == override
    failed_screen = {**override, 'screen_run': {**decision['screen_run'], 'passed': False,
                                                'reason': 'screen_below_baseline'}}
    assert chain.recompute_decision(failed_screen) != failed_screen
    refused_gate = {**override, 'gate_verdict': {'accepted': False, 'reason': 'gain_below_tau'}}
    assert chain.recompute_decision(refused_gate) != refused_gate
