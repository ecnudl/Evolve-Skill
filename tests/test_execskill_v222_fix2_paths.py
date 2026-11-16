"""Protected-name and explicit source aliases fail before any supply byte read."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import manifest, profiles as p, v222_smoke as smoke
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

PROTECTED = ('test', 'holdout', 'held_out', 'final', 'sealed', 'reserve',
             'TestAccess', 'test_panel', 'block_c', 'block_d')


def refuse_bytes(monkeypatch):
    def forbidden(path):
        pytest.fail('Protected source reached read_bytes: ' + str(path))
    monkeypatch.setattr(Path, 'read_bytes', forbidden)


def reload_manifest(monkeypatch, root, pin, *, pinned=None):
    """Exercise setting_of's real supply-reload call, replacing unrelated setup."""
    monkeypatch.setattr(manifest.notes, 'lexicon_sha256', lambda: 'authored')
    monkeypatch.setattr(manifest, 'prompt_sha', lambda configuration: 'authored')
    monkeypatch.setattr(manifest, '_solver_chain', lambda *args: 'G')
    monkeypatch.setattr(manifest.routes, 'current', lambda *args, **kwargs: None)
    monkeypatch.setattr(manifest.slots, 'pools', lambda *args, **kwargs: {})
    monkeypatch.setattr(manifest, '_slot_sizes', lambda value: {})
    monkeypatch.setattr(manifest, 'Budget', lambda path: SimpleNamespace())
    monkeypatch.setattr(manifest, '_read_terms', lambda *args: True)
    monkeypatch.setattr(manifest, '_searchqa_tail', lambda data: {})
    monkeypatch.setattr(manifest, '_pools', lambda *args: {})
    monkeypatch.setattr(manifest, '_clients', lambda *args: None)
    monkeypatch.setattr(manifest, 'limits_of', lambda value: {})
    monkeypatch.setattr(manifest.units, 'Setting', lambda **kwargs: SimpleNamespace(**kwargs))
    data = {'instructions': {}, 'original_cards': {}, 'instruction_start': 'authored', 'blank_arm': {},
        'alfworld_v11_import': {}, 'allocations': {}, 'v211_prompt_pins': {}, 'freshness_amendment': {},
        'confirm': {}, 'test_read_estimate': {'G': 1}, 'test_read_terms': {'G': {}},
        'v222_practice': {'supply_pins': {'officeqa': pin}}, 'v222_practice_supply': {},
        'pinned': pinned or {}}
    value = {'configuration': p.MAIN_V8, 'evidence': manifest.SMOKE_EVIDENCE,
        'lexicon_sha': 'authored', 'prompt_sha': 'authored', p.RECORD_HASH: 'a' * 64,
        'root': str(root), 'slot_root': str(root / 'slots'), 'data': data,
        'clients': {'solver': {'G': {'model': p.CHAINS['G'], 'branch': None, 'longest': None}}},
        'cards': {}, 'runtime': {}, 'sandbox': {'image_id': 'authored'}}
    return manifest.setting_of(value, 'G', docker=object())


@pytest.mark.parametrize('token', PROTECTED)
@pytest.mark.parametrize('location', ['filename', 'directory'])
@pytest.mark.parametrize('reader', ['supply_manifest', 'pool', 'manifest_reload'])
def test_every_protected_substring_is_refused_before_either_read_or_reload(tmp_path, monkeypatch, token, location, reader):
    name = 'prefix-' + token.swapcase() + '-suffix'
    path = tmp_path / (name + '.json') if location == 'filename' else tmp_path / name / 'practice.json'
    pin = {'path': str(path), 'sha256': 'a' * 64}
    refuse_bytes(monkeypatch)
    with pytest.raises(ValueError, match='protected partition'):
        if reader == 'supply_manifest':
            smoke.prepare_practice({'data': {}}, supply_file=path)
        elif reader == 'pool':
            smoke.load_supply_pins({'officeqa': pin})
        else:
            reload_manifest(monkeypatch, tmp_path / 'run', pin)


@pytest.mark.parametrize('group', ['test', 'layouts', 'upstream', 'split', 'zebralogic'])
@pytest.mark.parametrize('reader', ['supply_manifest', 'pool', 'manifest_reload'])
def test_explicit_protected_alias_remains_closed_even_with_an_innocuous_name(tmp_path, monkeypatch, group, reader):
    closed = tmp_path / 'closed-source'
    path = closed / 'practice.json'
    pinned = ({'zebralogic': {'path': str(closed), 'sha256': 'b' * 64}} if group == 'zebralogic' else
              {'paths': {group: str(closed) if group == 'split' else {'officeqa': str(closed)}}})
    pin = {'path': str(path), 'sha256': 'a' * 64}
    refuse_bytes(monkeypatch)
    with pytest.raises(ValueError, match='alias a protected source'):
        if reader == 'supply_manifest':
            smoke.prepare_practice({'data': {'pinned': pinned}}, supply_file=path)
        elif reader == 'pool':
            smoke.load_supply_pins({'officeqa': pin}, forbidden_paths=smoke.protected_paths({'pinned': pinned}))
        else:
            reload_manifest(monkeypatch, tmp_path / 'run', pin, pinned=pinned)


def test_plain_practice_path_is_not_rejected_by_name(tmp_path):
    path = tmp_path / 'officeqa-practice.json'
    assert smoke._practice_path(path) == path
