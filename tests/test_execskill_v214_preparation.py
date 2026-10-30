"""Mixed preparation with authored practice pools; real or sealed data stay closed."""
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import profiles as p, v214_preparation as v, zebralogic as z
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v211_manifest import setup as inherited_setup, reseal
from tests.test_execskill_zpc_adapter import materialize, pool_rows


def prepared(root, monkeypatch):
    source, options, old = inherited_setup(root / 'parent', monkeypatch)
    source_path = options['s0_file']
    pool = root / 'authored-zebra-pool.json'
    sha = materialize(pool, pool_rows())
    load = z.load_pool
    monkeypatch.setattr(z, 'POOL_SHA256', sha)
    monkeypatch.setattr(z, 'load_pool', lambda path, **kwargs: load(path, expected_sha256=sha))
    split = root / 'authored-split-inventory.json'
    write_json(split, {'output_sha256': {'zebralogic/pool.json': sha,
                                       'zebralogic/sealed-holdout.json': z.SEALED_SHA256}})
    return source, source_path, dict(zebra_pool=pool, zebra_split_manifest=split), options


def test_bridge_reads_practice_only_and_retains_exact_parent_allocations(tmp_path, monkeypatch):
    source, path, kwargs, _ = prepared(tmp_path, monkeypatch)
    before = path.read_bytes()
    closed = {Path(source['data']['pinned']['paths']['split']), Path(z.SEALED_PATH),
              Path(source['data']['pools']['livemath']['path'])}
    for group in ('test', 'layouts', 'upstream'):
        closed.update(Path(value) for value in source['data']['pinned']['paths'][group].values())
    reads = []
    read = Path.read_bytes
    read_text = Path.read_text
    def bytes_only(path, *args, **kwargs):
        assert path not in closed, 'Closed or removed input opened'
        reads.append(path)
        return read(path, *args, **kwargs)
    def text_only(path, *args, **kwargs):
        assert path not in closed, 'Closed or removed input opened'
        reads.append(path)
        return read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_bytes', bytes_only)
    monkeypatch.setattr(Path, 'read_text', text_only)
    made = v.preparation(path, **kwargs)
    assert v.verify(made) == made
    assert path.read_bytes() == before
    expected = {'searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench', 'alfworld'}
    assert set(made['data']['pools']) == set(made['cards']) == set(made['runtime']) == expected
    assert set(made['allocations']) == set(v.LEARNED)
    assert all(made['allocations'][b] == source['allocations'][b] for b in v.LEARNED)
    assert made['cards'][z.BENCH] == z.CARD_TEXT
    assert made['data']['zebra_pc'] == z.identity()
    assert made['data']['pinned']['zebralogic'] == z.identity()['sealed']
    assert made['confirm']['configuration'] == p.ZEBRA_PC_V13
    assert made['confirm']['items'] == 40
    assert made['zebra_slices']['run']['items'] == 60
    assert made['zebra_slices']['accept']['items'] == 100
    assert made['registration']['sealed_reads'] == 0
    for group in ('test', 'layouts', 'upstream', 'train', 'val'):
        assert 'livemath' not in made['data']['pinned']['paths'][group]
    assert not set(reads) & closed
    made['runtime']['officeqa']['authored_mutation'] = True
    assert 'authored_mutation' not in source['runtime']['officeqa']


@pytest.mark.parametrize('mutation', ['allocation', 'protected', 'source_configuration', 'failed'])
def test_bridge_refuses_resealed_parent_drift(tmp_path, monkeypatch, mutation):
    source, path, kwargs, _ = prepared(tmp_path, monkeypatch)
    source = deepcopy(source)
    if mutation == 'allocation':
        source['allocations']['officeqa']['slices']['run'][0] = 'different-practice-item'
    elif mutation == 'protected':
        source['protected_ids']['officeqa']['count'] += 1
    elif mutation == 'source_configuration':
        source['configuration'] = p.MAIN_V3
    else:
        source['passed'] = False
    path = tmp_path / 'resealed-parent.json'
    write_json(path, reseal(source))
    with pytest.raises(ValueError):
        v.preparation(path, **kwargs)


def test_verify_refuses_changed_source_or_mixed_identity(tmp_path, monkeypatch):
    _, path, kwargs, _ = prepared(tmp_path, monkeypatch)
    made = v.preparation(path, **kwargs)
    wrong = deepcopy(made)
    wrong['cards'][z.BENCH] += ' changed'
    with pytest.raises(ValueError, match='mixed preparation'):
        v.verify(wrong)
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='S0 bytes changed'):
        v.verify(made)
