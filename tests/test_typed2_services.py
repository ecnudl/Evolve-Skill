"""typed-v2 Services pass (step 1b; DESIGN 3.5, the Services fields of 3.6, 4.1; addendum D15): the start checks of
every real start, the code identity the manifest seals, the ledger cap from the sealed manifest, the container scope
that keeps typed-v1, typed-v2 and smoke containers apart, and the learning widths of learning units beside the read
widths of read units. Fakes only: no network, no Docker, no /data, no model call."""
import contextlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import manifest as route_b_manifest, slots, typed, zebralogic
from skillopt.execskill.sandbox import client as sandbox
from skillopt.execskill.typed import chain, machinery, prepare, smoke, units
from tests.test_typed_chain import build
from tests.test_typed_reads import sealed_code, services_for, write_machinery, write_pools, write_tree, zebra_rows

# pytest's tmp_path carries the word "test" (refused by the sealed-path guard); /tmp is a symlink on macOS, which
# route B's safe_path refuses in any parent: the neutral root through its resolved spelling
NEUTRAL = Path('/tmp/typed2-neutral').resolve()
RUN_NAME, SMOKE_NAME, V1_NAME = 'execskill-20261112-typed-v3', 'execskill-20261112-typed-v3-smoke', 'execskill-20261110-typed-v1'


@pytest.fixture
def tmp_path():
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='services-', dir=NEUTRAL))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def code(**changes):
    """A bound machinery record as a real ``prepare`` on dl seals it (fixture values, this code's list pins)."""
    return sealed_code(**{'snapshot': '/data/execskill-code-20261109-main-v10', **changes})['machinery_code']


TYPED_CODE = {'files': 20, 'sha256_list_sha256': 'c' * 64}


def sealed_manifest(**changes):
    return {'machinery_code': code(), 'provenance': {'typed_code': dict(TYPED_CODE)}, 'caps': dict(typed.CAPS), **changes}


def listing(path):
    path = Path(path)
    if not path.exists():
        return None
    return sorted((str(p.relative_to(path)), p.stat().st_size) for p in path.rglob('*'))


# ---- start_checks -------------------------------------------------------------------------------------------------
def test_start_checks_pass_on_the_sealed_records_and_return_the_machinery_record(tmp_path):
    root = tmp_path / RUN_NAME
    calls = []
    found = chain.start_checks(root, sealed_manifest(), check=lambda: calls.append('check') or code(),
                               provenance=lambda: calls.append('typed') or dict(TYPED_CODE))
    assert found == code() and calls == ['check', 'typed'] and not root.exists()


def test_start_checks_refuse_every_difference_and_name_keys_only(tmp_path):
    root = tmp_path / RUN_NAME
    cases = {
        'list_sha256': dict(check=lambda: code(list_sha256='0' * 64)),
        'snapshot': dict(check=lambda: code(snapshot='/data/execskill-code-20261201-other')),
        'typed_from': dict(check=lambda: code(typed_from='/data/execskill-dev-typed2')),
        'symbols': dict(check=lambda: code(symbols=144)),
        'bound': dict(check=lambda: code(bound=False)),
        'extra key': dict(check=lambda: {**code(), 'extra': 1}),
    }
    for name, case in cases.items():
        with pytest.raises(ValueError, match='machinery of this start differs') as refused:
            chain.start_checks(root, sealed_manifest(), check=case['check'], provenance=lambda: dict(TYPED_CODE))
        assert '/data/' not in str(refused.value) and 'c' * 64 not in str(refused.value), name
    # the typed package or the launcher changed since prepare (a test or ops helper is not part of it)
    with pytest.raises(ValueError, match='typed code .*differs'):
        chain.start_checks(root, sealed_manifest(), check=code,
                           provenance=lambda: {**TYPED_CODE, 'sha256_list_sha256': 'd' * 64})
    # a manifest prepared unbound is refused by every real start, before the check runs
    untouched = []
    with pytest.raises(ValueError, match='without the machinery snapshot'):
        chain.start_checks(root, sealed_manifest(machinery_code=code(bound=False)),
                           check=lambda: untouched.append(1) or code(bound=False), provenance=lambda: dict(TYPED_CODE))
    assert untouched == []
    # a manifest that seals no record or no typed code
    with pytest.raises(ValueError, match='no machinery_code'):
        chain.start_checks(root, {k: v for k, v in sealed_manifest().items() if k != 'machinery_code'}, check=code,
                           provenance=lambda: dict(TYPED_CODE))
    with pytest.raises(ValueError, match='no provenance.typed_code'):
        chain.start_checks(root, sealed_manifest(provenance={}), check=code, provenance=lambda: dict(TYPED_CODE))
    # a refusal of the machinery check itself propagates unchanged
    def refused():
        raise ValueError('Machinery check 2 refused: stand-in')
    with pytest.raises(ValueError, match='Machinery check 2 refused'):
        chain.start_checks(root, sealed_manifest(), check=refused, provenance=lambda: dict(TYPED_CODE))
    assert not root.exists()


def test_start_checks_refuse_a_root_of_another_typed_version_before_any_check(tmp_path):
    calls = []
    for root in (tmp_path / V1_NAME, tmp_path / V1_NAME / 'nested' / RUN_NAME):
        with pytest.raises(ValueError, match='another typed version'):
            chain.start_checks(root, sealed_manifest(), check=lambda: calls.append(1) or code(),
                               provenance=lambda: calls.append(2) or dict(TYPED_CODE))
    state = tmp_path / RUN_NAME
    units.write_json(state / 'G' / 'state.json', {'version': 'typed-v1', 'chain': 'G'})
    with pytest.raises(ValueError, match='belongs to another version'):
        chain.start_checks(state, sealed_manifest(), check=lambda: calls.append(1) or code(),
                           provenance=lambda: calls.append(2) or dict(TYPED_CODE))
    assert calls == []


# ---- run: the real start is checked before the ledger opens ------------------------------------------------------
def real_like(root, monkeypatch, *, typed_code=None):
    """Fake services that carry a sealed machinery record (what ``real_services`` hands ``run``), with the machinery
    check and the typed code of this process stubbed; returns (services, calls of the stubs)."""
    services, _, _ = build(root, order=('searchqa',))
    services.manifest = {**services.manifest, 'machinery_code': code(),
                         'provenance': {'typed_code': dict(TYPED_CODE)}}
    services.machinery_code, services.container_scope = code(), chain.container_scope_of(root)
    calls = []
    monkeypatch.setattr(machinery, 'check', lambda *, real, snapshot=None: calls.append(('check', real)) or code())
    monkeypatch.setattr(prepare, 'typed_code', lambda tree=None: calls.append(('typed', tree)) or dict(typed_code or TYPED_CODE))
    return services, calls


def test_run_checks_a_real_start_before_the_state_or_the_ledger_exists(tmp_path, monkeypatch):
    root = tmp_path / RUN_NAME
    services, calls = real_like(root, monkeypatch, typed_code={**TYPED_CODE, 'files': 21})
    with pytest.raises(ValueError, match='typed code'):
        chain.run(root, 'G', services=services)
    assert calls == [('check', True), ('typed', None)] and not root.exists()  # nothing written, no ledger, no call
    services, calls = real_like(root, monkeypatch)
    state = chain.run(root, 'G', services=services, sleep=lambda s: None)
    assert state['complete'] and calls == [('check', True), ('typed', None)]
    assert state['machinery_code'] == code() and state['container_scope'] == 'typed-v3:%s:' % RUN_NAME
    stored = json.loads((root / 'G' / 'state.json').read_text())
    assert stored['machinery_code'] == code() and stored['container_scope'] == 'typed-v3:%s:' % RUN_NAME
    # a resume checks again; a state started with another machinery record or scope is refused before the ledger
    stored['complete'] = False
    stored['machinery_code'] = code(symbols=1)
    units.write_json(root / 'G' / 'state.json', stored)
    ledger = (root / 'G' / 'ledger.json').read_bytes()
    services, calls = real_like(root, monkeypatch)
    with pytest.raises(ValueError, match='another machinery_code'):
        chain.run(root, 'G', services=services, resume=True)
    assert calls == [('check', True), ('typed', None)] and (root / 'G' / 'ledger.json').read_bytes() == ledger
    # services built for another root are refused (their containers would carry the other root's scope)
    services, calls = real_like(tmp_path / 'execskill-20261113-typed-v3', monkeypatch)
    with pytest.raises(ValueError, match='another root'):
        chain.run(tmp_path / 'execskill-20261114-typed-v3', 'G', services=services)
    assert not (tmp_path / 'execskill-20261114-typed-v3').exists()


def test_a_fake_start_runs_no_machinery_check_but_still_refuses_another_typed_version(tmp_path, monkeypatch):
    monkeypatch.setattr(machinery, 'check', lambda **kw: pytest.fail('a fake start never runs the machinery check'))
    services, _, _ = build(tmp_path / 'fake', order=('searchqa',))
    state = chain.run(tmp_path / 'fake', 'G', services=services, sleep=lambda s: None)
    assert state['complete'] and state['machinery_code'] is None and state['container_scope'] is None
    v1 = tmp_path / V1_NAME
    services, _, _ = build(v1, order=('searchqa',))
    with pytest.raises(ValueError, match='another typed version'):
        chain.run(v1, 'G', services=services)
    assert not v1.exists()


def test_open_state_records_and_compares_the_machinery_record_and_the_scope(tmp_path):
    fresh = chain._open_state(tmp_path / 'G', 'G', 'run', False, machinery_code=code(), container_scope='typed-v2:r:')
    assert fresh['machinery_code'] == code() and fresh['container_scope'] == 'typed-v2:r:'
    units.write_json(tmp_path / 'G' / 'state.json', fresh)
    assert chain._open_state(tmp_path / 'G', 'G', 'run', True, machinery_code=code(),
                             container_scope='typed-v2:r:')['machinery_code'] == code()
    for changes in ({'machinery_code': code(typed_from='/elsewhere')}, {'container_scope': 'typed-v2:other:'},
                    {'machinery_code': None}):
        kwargs = {'machinery_code': code(), 'container_scope': 'typed-v2:r:', **changes}
        with pytest.raises(ValueError, match='started with another'):
            chain._open_state(tmp_path / 'G', 'G', 'run', True, **kwargs)


# ---- the ledger cap comes from the sealed manifest -----------------------------------------------------------------
def test_the_ledger_cap_comes_from_the_sealed_manifest(tmp_path):
    services, _, _ = build(tmp_path / 'a', order=('searchqa',))
    services.manifest = {**services.manifest, 'caps': {'G': 12_345_678, 'D': 23_456_789}}
    chain.run(tmp_path / 'a', 'G', services=services, sleep=lambda s: None)
    assert json.loads((tmp_path / 'a' / 'G' / 'ledger.json').read_text())['cap'] == 12_345_678
    services, _, _ = build(tmp_path / 'b', order=('searchqa',))  # real_services sets Services.cap from the manifest
    services.cap = 9_876_543
    chain.run(tmp_path / 'b', 'G', services=services, sleep=lambda s: None)
    assert json.loads((tmp_path / 'b' / 'G' / 'ledger.json').read_text())['cap'] == 9_876_543
    # no cap in the services and none in the manifest: refused before anything is written (never the code constant)
    services, _, _ = build(tmp_path / 'c', order=('searchqa',))
    services.manifest = {k: v for k, v in services.manifest.items() if k != 'caps'}
    with pytest.raises(ValueError, match='ledger cap comes from the sealed manifest'):
        chain.run(tmp_path / 'c', 'G', services=services)
    assert not (tmp_path / 'c').exists()
    assert smoke.synthetic_manifest()['caps'] == typed.CAPS  # the fake manifest seals the caps a prepared one seals


# ---- real_services: cap, machinery record, container scope, heavy signature ----------------------------------------
class Captured:
    def __init__(self):
        self.workers, self.drains = [], []


def real_services(tmp_path, monkeypatch, chain_name='G', root_name=RUN_NAME, caps=None):
    """``chain.real_services`` with every machine-bound piece stubbed (pools, docker, worker, drain, readiness,
    items); the wiring itself is the real one."""
    captured = Captured()
    monkeypatch.delenv('ALFWORLD_DATA', raising=False)
    monkeypatch.setattr(chain, 'load_items', lambda manifest, **kw: {bench: [] for bench in typed.ORDER})
    monkeypatch.setattr(chain, 'sheet_readiness', lambda runtime: {'status': 'ready'})
    monkeypatch.setattr(route_b_manifest, '_slot_sizes', lambda setting: {})
    monkeypatch.setattr(route_b_manifest, 'limits_of', lambda manifest: {'cell': {}})
    live = SimpleNamespace(limited=lambda cap: ('live', cap))
    monkeypatch.setattr(slots, 'pools', lambda root, sizes: {slots.LIVE: live, slots.NATIVE: 'native',
                                                             slots.EPISODE: 'episodes', slots.CALL: 'per-call'})
    monkeypatch.setattr(sandbox, 'Docker', lambda: 'docker')
    monkeypatch.setattr(sandbox, 'Worker', lambda **options: captured.workers.append(options) or 'worker')
    monkeypatch.setattr(sandbox, 'drain_unit', lambda chain_letter, unit, **kw: captured.drains.append((chain_letter, unit)))
    manifest = {'runtime': {bench: {} for bench in typed.ORDER}, 'slot_root': str(tmp_path / 'slots'),
                'sandbox': {'image_id': 'sha256:' + 'd' * 64}, 'slices': {}, 'clients': {},
                'caps': caps or {'G': 1_234_567, 'D': 7_654_321}, 'machinery_code': code(),
                'tau_rule': prepare.tau_rule(),  # step 5w: the sealed gate rule real_services checks
                'memory_lock': 'per_cell_plain'}  # step 6s: the sealed lock mode heavy_for builds (DESIGN 3.6)
    settings = {'clients': {'solver': {'G': {}}, 'routes': {'D': {'B': {'M': {bench: 100 for bench in typed.ORDER}}}}}}
    role = SimpleNamespace(max_tokens=None, call=lambda system, user: {})
    clients = {'solver': lambda bench: (SimpleNamespace(call=lambda system, user: {}), 100),
               'role': lambda max_tokens: role}
    services = chain.real_services(tmp_path / root_name, chain_name, manifest, smoke=root_name.endswith('-smoke'),
                                   settings=settings, clients=clients)
    return services, captured, manifest


def test_real_services_take_the_cap_and_the_machinery_record_from_the_manifest(tmp_path, monkeypatch):
    services, captured, manifest = real_services(tmp_path, monkeypatch)
    assert services.cap == 1_234_567 != typed.CAPS['G'] and services.machinery_code == code()
    assert services.container_scope == 'typed-v3:%s:' % RUN_NAME and services.lock_setting is None
    assert services.limits == chain.DEFAULT_LIMITS
    with services.heavy('searchqa', unit='s1/noise'):  # the signature of every area: heavy(bench, unit=None)
        pass
    with services.heavy('searchqa'):
        pass
    d_services, _, _ = real_services(tmp_path, monkeypatch, 'D')
    assert d_services.cap == 7_654_321
    for broken in ({'caps': {'D': 7_654_321}}, {'machinery_code': None}):
        with pytest.raises(ValueError, match='seals'):
            chain.real_services(tmp_path / RUN_NAME, 'G', {**manifest, **broken}, smoke=False,
                                settings={'clients': {'solver': {'G': {}}}}, clients={})


def test_typed_v1_and_typed_v2_get_different_container_tags_for_the_same_chain_and_unit(tmp_path, monkeypatch):
    unit = 's2/noise'
    typed_v1 = sandbox.unit_tag('G', unit)  # typed-v1 passed the bare chain-relative unit (C:1155, C:1164)
    services, captured, _ = real_services(tmp_path, monkeypatch)
    assert services.worker_factory('searchqa', unit, 'cell-tag')() == 'worker'
    services.drain(unit)
    scope = 'typed-v3:%s:' % RUN_NAME
    assert captured.workers[-1]['tag'] == sandbox.unit_tag('G', scope + unit) != typed_v1
    assert captured.drains == [('G', scope + unit)]  # the drain prefix and the worker tag agree
    assert sandbox.unit_tag('G', captured.drains[0][1]) == captured.workers[-1]['tag']
    # the run root and its smoke root, and the two chains, never share a prefix either
    smoke_services, smoke_captured, _ = real_services(tmp_path, monkeypatch, root_name=SMOKE_NAME)
    smoke_services.worker_factory('searchqa', unit, 'cell-tag')()
    d_services, d_captured, _ = real_services(tmp_path, monkeypatch, 'D')
    d_services.worker_factory('searchqa', unit, 'cell-tag')()
    tags = {typed_v1, captured.workers[-1]['tag'], smoke_captured.workers[-1]['tag'], d_captured.workers[-1]['tag']}
    assert len(tags) == 4 and smoke_captured.workers[-1]['tag'] == sandbox.unit_tag('G', 'typed-v3:%s:%s' % (SMOKE_NAME, unit))
    assert chain.container_scope_of('/data/' + RUN_NAME) == chain.container_scope_of(Path('/x') / RUN_NAME) == scope
    # a drained typed-v2 unit can never remove a typed-v1 container of the same chain letter and unit
    v1_container = sandbox.PREFIX + typed_v1 + '-' + 'a' * 32
    assert not v1_container.startswith(sandbox.PREFIX + sandbox.unit_tag('G', scope + unit) + '-')
    assert sandbox.NAME.fullmatch(v1_container)


# ---- learning widths and read widths ------------------------------------------------------------------------------
def width_spy(monkeypatch):
    """Every ``units.run_unit`` call as (unit path relative to the chain directory, widths)."""
    seen, real_run_unit = [], units.run_unit

    def spy(unit_dir, jobs, *, widths, **kw):
        seen.append((Path(unit_dir), dict(widths)))
        return real_run_unit(unit_dir, jobs, widths=widths, **kw)
    monkeypatch.setattr(units, 'run_unit', spy)
    return seen


def fake_smoke(root, monkeypatch):
    """The fake smoke on one bench through the REAL mount, writers and reads (held-out practice panels)."""
    seen = width_spy(monkeypatch)
    services = smoke.fake_services(root, 'G', smoke.synthetic_manifest(), scripted={})
    services.order = ('searchqa',)
    state = smoke.run(root, 'G', services=services, sleep=lambda s: None)
    calls = sorted(services.script.calls, key=repr)
    return state, seen, calls


def test_learning_units_use_the_learning_widths_and_read_units_the_read_widths(tmp_path, monkeypatch):
    root = tmp_path / SMOKE_NAME
    state, seen, _ = fake_smoke(root, monkeypatch)
    assert state['complete'], state
    learning = [(path, widths) for path, widths in seen if re.fullmatch(r's\d+', path.parent.name)]
    reading = [(path, widths) for path, widths in seen if path.name.startswith('practice-read-')]
    assert learning and reading and len(learning) + len(reading) == len(seen)
    assert all(widths == typed.LEARN_WIDTHS for _, widths in learning)
    assert all(widths == {'searchqa': typed.WIDTHS['searchqa']} for _, widths in reading)
    assert {path.name for path, _ in reading} == {'practice-read-%s-searchqa' % e for e in ('C0', 'C', 'S1')}
    assert typed.LEARN_WIDTHS['searchqa'] == 6 and typed.WIDTHS['searchqa'] == 3


def test_the_learning_widths_change_no_request_and_no_unit_order(tmp_path, monkeypatch):
    """ACCEPT of Step 1: with default fields every request and the order of units are those of the read widths; only
    the width of the learning units differs."""
    wide_state, _, wide_calls = fake_smoke(tmp_path / 'a' / SMOKE_NAME, monkeypatch)
    monkeypatch.setattr(chain, 'LEARN_WIDTHS', dict(typed.WIDTHS))
    narrow_state, _, narrow_calls = fake_smoke(tmp_path / 'b' / SMOKE_NAME, monkeypatch)
    assert wide_state['complete'] and narrow_state['complete']
    assert wide_state['done_units'] == narrow_state['done_units'] and wide_calls == narrow_calls

    def requests(root):
        out = {}
        for path in sorted((root / 'G').rglob('calls/*.json')):
            sends = json.loads(path.read_text())  # units.CallRecorder writes its list of sends
            assert isinstance(sends, list)
            out[str(path.relative_to(root))] = sorted(s.get('request_sha256') for s in sends)
        return out
    wide, narrow = requests(tmp_path / 'a' / SMOKE_NAME), requests(tmp_path / 'b' / SMOKE_NAME)
    assert wide == narrow and any('/s1/' in name for name in wide) and sum(map(len, wide.values())) > 20


# ---- Services fields, limits, fakes --------------------------------------------------------------------------------
def test_services_carry_every_new_field_and_the_five_limits(tmp_path):
    names = {f.name for f in chain.Services.__dataclass_fields__.values()}
    assert {'cap', 'machinery_code', 'container_scope', 'lock_setting', 'heavy', 'limits'} <= names
    assert chain.DEFAULT_LIMITS == {'card_rounds': typed.CARD_ROUNDS, 'max_program_proposals': 3,
                                    'max_program_candidates': 2, 'program_smoke_items': typed.PROGRAM_SMOKE_ITEMS,
                                    'gate_repeats': 3}
    assert set(smoke.SMOKE_LIMITS) == set(chain.DEFAULT_LIMITS)
    assert (smoke.SMOKE_LIMITS['card_rounds'], smoke.SMOKE_LIMITS['max_program_candidates'],
            smoke.SMOKE_LIMITS['program_smoke_items'], smoke.SMOKE_LIMITS['gate_repeats']) == (1, 1, 2, 3)
    fake = smoke.fake_services(tmp_path, 'G', smoke.synthetic_manifest())
    reads_fake = services_for(tmp_path, SimpleNamespace(client=None, selection_client=None, ledger=None, embed=None,
                                                        heavy_lock=lambda bench, unit=None: contextlib.nullcontext(),
                                                        mount=None, solve=None), mode='smoke')
    for services in (fake, reads_fake):
        assert isinstance(services, chain.Services) and services.limits == chain.DEFAULT_LIMITS
        assert (services.cap, services.machinery_code, services.container_scope, services.lock_setting) == (None,) * 4
        with services.heavy('spreadsheetbench', unit='s4/noise'):
            pass


# ---- prepare seals the code identity, load_manifest checks it ------------------------------------------------------
@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(zebralogic, 'load_pool', lambda *a, **k: zebra_rows())
    machinery_path = tmp_path / 'machinery.json'
    write_machinery(machinery_path)
    return {'pools': write_pools(tmp_path), 'machinery': machinery_path, 'tree': write_tree(tmp_path),
            'parent': tmp_path}


def test_prepare_seals_the_code_identity_and_load_manifest_checks_its_form(inputs):
    parent = inputs['parent']
    root = parent / SMOKE_NAME
    made = prepare.prepare(root, machinery_manifest=inputs['machinery'], roles_repo='/root/roles',
                           pools_root=inputs['pools'], smoke=True, typed_tree=inputs['tree'], root_parent=str(parent))
    assert made['machinery_code'] == machinery.check(real=False)  # this process: unbound on the Mac
    assert made['machinery_code']['bound'] is False and made['machinery_code']['list_sha256'] == machinery.LIST_SHA256
    assert made['provenance']['typed_code'] == prepare.typed_code(inputs['tree'])
    assert prepare.load_manifest(root) == made
    # an unbound manifest is refused by every real start
    with pytest.raises(ValueError, match='without the machinery snapshot'):
        chain.start_checks(root, made, check=lambda: made['machinery_code'], provenance=lambda: made['provenance']['typed_code'])
    fields = {key: value for key, value in made.items() if key != 'record_sha256'}
    broken = {
        'no machinery_code': {k: v for k, v in fields.items() if k != 'machinery_code'},
        'another list': {**fields, 'machinery_code': {**made['machinery_code'], 'list_sha256': '0' * 64}},
        'another data list': {**fields, 'machinery_code': {**made['machinery_code'], 'data_list_sha256': '0' * 64}},
        'a missing key': {**fields, 'machinery_code': {k: v for k, v in made['machinery_code'].items() if k != 'symbols'}},
        'no symbols': {**fields, 'machinery_code': {**made['machinery_code'], 'symbols': 0}},
        'no typed code': {**fields, 'provenance': {k: v for k, v in made['provenance'].items() if k != 'typed_code'}},
        'malformed typed code': {**fields, 'provenance': {**made['provenance'], 'typed_code': {'files': 3}}},
    }
    for name, value in broken.items():
        units.write_json(root / 'manifest.json', prepare.seal(value))
        with pytest.raises(ValueError, match='machinery|typed code'):
            prepare.load_manifest(root)


def test_typed_code_covers_the_typed_package_and_the_launcher_only(tmp_path):
    tree = tmp_path / 'tree'
    files = {'skillopt/execskill/typed/__init__.py': 'VERSION = 2\n', 'skillopt/execskill/typed/chain.py': 'x = 1\n',
             'skillopt/execskill/policy.py': 'frozen = 1\n', 'scripts/run_typed.py': 'main = 1\n',
             'scripts/ops_helper.py': 'helper = 1\n', 'tests/module.py': 'case = 1\n',
             'skillopt/execskill/typed/__pycache__/chain.cpython-313.pyc': 'cache'}
    for name, text in files.items():
        (tree / name).parent.mkdir(parents=True, exist_ok=True)
        (tree / name).write_text(text)
    first = prepare.typed_code(tree)
    assert first['files'] == 3 and len(first['sha256_list_sha256']) == 64
    for name in ('skillopt/execskill/policy.py', 'scripts/ops_helper.py', 'tests/module.py',
                 'skillopt/execskill/typed/__pycache__/chain.cpython-313.pyc'):
        (tree / name).write_text('changed\n')
        assert prepare.typed_code(tree) == first, name  # information only: never blocks a resume
    for name in ('skillopt/execskill/typed/chain.py', 'scripts/run_typed.py'):
        (tree / name).write_text('changed\n')
        assert prepare.typed_code(tree) != first, name
    (tree / 'skillopt/execskill/typed/new.py').write_text('n = 1\n')
    assert prepare.typed_code(tree)['files'] == 4
    current = prepare.typed_code()  # this tree: the typed package and the launcher
    assert current['files'] == len([p for p in (prepare.TYPED_TREE / 'skillopt/execskill/typed').rglob('*')
                                    if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']) + 1
