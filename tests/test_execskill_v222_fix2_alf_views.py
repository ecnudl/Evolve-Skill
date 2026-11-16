"""Exporter-shaped main-v8 practice overlays; every game is authored in scratch."""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.continual_eval import backends
from skillopt.continual_eval.core import write_json
from skillopt.execskill import alfworld_format, manifest, profiles as p, solver, supply
from skillopt.execskill import v222_alf_views as overlay, v222_cards as cards, v222_gate as gate
from skillopt.execskill import v222_runtime as runtime, v222_smoke as smoke
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v222_fix1_supply import source


@pytest.fixture
def exported(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    game_root = root / 'games'
    environment = {'alfworld_data': str(game_root), 'max_steps': 50, 'seed': 42}
    games = []
    for room in range(108):
        for number in range(5):
            key = 'room-%03d-game-%d' % (room, number)
            path = game_root / key / 'game.tw-pddl'
            path.parent.mkdir(parents=True)
            path.write_text('Authored game ' + key, encoding='utf-8')
            games.append({'task_id': key, 'room': str(room), 'task_type': 'pick_and_place_simple',
                'gamefile': str(path.relative_to(game_root)),
                'game_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    fresh = supply.supply_record('alfworld-xs', 'alfworld', games,
        sources={'data_root': str(game_root), 'pool_games_sha256': 'a' * 64}, evidence='engineering_fixture')
    cut = supply.slices('alfworld', supply.order('alfworld', games), supply.registered_sizes('alfworld'))
    reset = lambda row: ('Authored room.\nYour task is to: inspect ' + row['task_id'], ['look'])
    views = supply.views_record(fresh, supply.prereset(games, cut, reset=reset), cut, runtime=environment)
    fresh_path, views_path = root / 'supply.json', root / 'views.json'
    write_json(fresh_path, fresh)
    write_json(views_path, views)
    rows, counts = supply.alfworld_pool(fresh, views, runtime=environment)
    exported = supply.write_pool_export(root / 'pool', {'alfworld': (rows, counts)}, source={'alfworld': {
        'supply': str(fresh_path), 'supply_sha256': fresh[p.RECORD_HASH],
        'views': str(views_path), 'views_sha256': views[p.RECORD_HASH]}})
    imported = source()
    imported['data']['pools']['alfworld'] = supply.pool_pins(exported)['alfworld']
    del imported['allocations']['alfworld']
    imported['runtime'] = {'alfworld': environment}
    read_items = manifest._items
    monkeypatch.setattr(manifest, '_items', lambda entry, bench: deepcopy(entry)
        if isinstance(entry, list) else read_items(entry, bench))
    pools = {bench: manifest._items(entry, bench) for bench, entry in imported['data']['pools'].items()}
    setting = SimpleNamespace(shared=tmp_path / 'shared', pools=pools,
        runtime={'alfworld': alfworld_format.bind(environment, p.MAIN_V8)},
        extra={'configuration': p.MAIN_V8, 'v211_allocation': imported['allocations']})
    available, excluded = runtime._training_allocations(setting)
    harms = gate.harm_slices(available, excluded=excluded)
    decomposition = cards.decomposition_slices({bench: [row['task_id'] for row in selected]
                                                for bench, selected in available.items()})
    union = set(decomposition['alfworld']['items']) | {row['task_id'] for row in harms['alfworld']}
    missing = {row['task_id'] for row in available['alfworld']
               if row['task_id'] in union and 'routing_view' not in row['public']}
    calls = []

    class Environment:
        def __init__(self, key):
            self.key = key

        def reset(self):
            calls.append(('reset', self.key))
            return ['Authored overlay room.\nYour task is to: inspect ' + self.key], None, [
                {'admissible_commands': ['look']}]

        def close(self):
            calls.append(('close', self.key))

    def opened(public, actual_runtime):
        assert actual_runtime == environment
        return Environment(Path(public['game_file']).parent.name)

    monkeypatch.setattr(backends, '_new_alfworld', opened)
    return SimpleNamespace(root=root, imported=imported, setting=setting, available=available,
        excluded=excluded, harms=harms, decomposition=decomposition, union=union,
        missing=missing, calls=calls, environment=environment)


def prepared(exported):
    registered = smoke.prepare_practice(exported.imported)
    exported.setting.extra['v222_practice'] = deepcopy(registered)
    return registered


def reseal(value):
    return p.record(overlay.KIND, value['evidence'], {key: entry for key, entry in value.items()
        if key not in ('version', 'evidence', p.RECORD_HASH)})


def test_real_exporter_draws_get_complete_union_views_without_changing_frozen_pools_or_d1(exported):
    original_rows = deepcopy(exported.setting.pools)
    original_files = {path: path.read_bytes() for path in exported.root.rglob('*') if path.is_file()}
    assert len(exported.available['alfworld']) == 390
    assert len(exported.excluded['alfworld']) == 150
    assert len(exported.harms['alfworld']) == len(exported.decomposition['alfworld']['items']) == 20
    assert any('routing_view' not in row['public'] for row in exported.harms['alfworld'])
    assert exported.missing & set(exported.decomposition['alfworld']['items'])
    unviewed = next(row for row in exported.harms['alfworld'] if 'routing_view' not in row['public'])
    with pytest.raises(ValueError, match='registered routing view'):
        solver.routing_view('alfworld', unviewed['public'], runtime=exported.setting.runtime['alfworld'])
    registered = prepared(exported)
    value = registered[overlay.KEY]
    assert set(value['views']) == exported.union and value['model_calls'] == 0
    assert value['binding']['runtime_sha256'] == digest(exported.environment)
    assert exported.calls == [action for key in sorted(exported.missing)
                              for action in [('reset', key), ('close', key)]]
    assert registered[smoke.SUPPLY_FLAG]['benches']['alfworld'] == {
        'available': 390, 'decomposition_items': 20, 'harm_items': 20, 'acceptance_excluded': 150}
    selected, harms, bound = smoke.practice(exported.setting)
    assert bound == registered
    for row in selected['alfworld'] + harms['alfworld']:
        assert row['task_id'] not in exported.excluded['alfworld']
        assert row['views_runtime_sha256'] == digest(exported.environment)
        assert solver.routing_view('alfworld', row['public'], runtime=exported.setting.runtime['alfworld'])
    runtime_harms, pinned = runtime.preflight(exported.setting)
    assert runtime_harms == harms and pinned == registered['harm']
    assert exported.setting.pools == original_rows
    assert all(path.read_bytes() == content for path, content in original_files.items())


def test_overlay_reload_and_runtime_attach_never_reset_and_bind_source_game_and_view_hashes(exported, monkeypatch):
    registered = prepared(exported)
    value = registered[overlay.KEY]
    monkeypatch.setattr(backends, '_new_alfworld', lambda *_: pytest.fail('Reload must not reset'))
    reloaded = smoke.prepare_practice(exported.imported, alf_views=value)
    assert reloaded == registered
    selected, _, _ = smoke.practice(exported.setting)
    assert {row['task_id'] for row in selected['alfworld']} == set(exported.decomposition['alfworld']['items'])
    by_id = {row['task_id']: row for row in exported.available['alfworld']}
    for key, pin in value['binding']['games'].items():
        assert pin['game_sha256'] == by_id[key]['private']['game_sha256']
        assert pin['source_item_sha256'] == digest(by_id[key])
        assert value['views'][key]['view_sha256'] == digest(value['views'][key]['view'])


@pytest.mark.parametrize('change', ['missing_record', 'missing_view', 'view_hash', 'runtime', 'draw',
                                   'source_row', 'harm_registration'])
def test_runtime_refuses_mismatched_overlay_before_routing(exported, monkeypatch, change):
    registered = prepared(exported)
    stored = exported.setting.extra['v222_practice']
    value = stored[overlay.KEY]
    if change == 'missing_record':
        del stored[overlay.KEY]
    elif change == 'missing_view':
        del value['views'][next(iter(value['views']))]
        stored[overlay.KEY] = reseal(value)
    elif change == 'view_hash':
        value['views'][next(iter(value['views']))]['view']['task_text'] += ' changed'
        stored[overlay.KEY] = reseal(value)
    elif change == 'runtime':
        exported.setting.runtime['alfworld']['seed'] += 1
    elif change == 'draw':
        value['binding']['draws']['harm'].reverse()
        value['binding_sha256'] = digest(value['binding'])
        stored[overlay.KEY] = reseal(value)
    elif change == 'harm_registration':
        pinned = stored['harm']['benches']['alfworld']['public_sha256']
        pinned[next(iter(pinned))] = 'f' * 64
    else:
        key = registered[overlay.KEY]['binding']['ids'][0]
        next(row for row in exported.setting.pools['alfworld'] if row['task_id'] == key)['family_id'] += '-changed'
    monkeypatch.setattr(backends, '_new_alfworld', lambda *_: pytest.fail('Runtime must not reset'))
    monkeypatch.setattr(solver, 'routing_view', lambda *_args, **_kwargs: pytest.fail('No routing before pins validate'))
    with pytest.raises(ValueError):
        runtime.preflight(exported.setting)
    assert not (exported.setting.shared / 'v222-harm-slices.json').exists()


@pytest.mark.parametrize('selected_kind', ['missing_view', 'existing_view'])
def test_all_selected_game_bytes_are_verified_before_the_first_reset(exported, selected_kind):
    candidates = exported.missing if selected_kind == 'missing_view' else exported.union - exported.missing
    assert candidates
    key = sorted(candidates)[-1]
    row = next(row for row in exported.available['alfworld'] if row['task_id'] == key)
    Path(row['public']['game_file']).write_text('Changed authored game', encoding='utf-8')
    with pytest.raises(ValueError, match='game differs from its pinned SHA256'):
        smoke.prepare_practice(exported.imported)
    assert not exported.calls


def test_overlay_rejects_an_older_configuration_before_any_reset(exported):
    with pytest.raises(ValueError, match='main-v8 only'):
        overlay.prepare(exported.available['alfworld'], exported.harms['alfworld'],
            exported.decomposition['alfworld'], runtime=exported.environment, configuration=p.MAIN_V7)
    assert not exported.calls
