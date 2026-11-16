"""What re-judging a card of a FINISHED typed run needs on both of its paths (bank items: ``oqa_build`` contrasts,
BANK-PILOT B26; spare real items: ``spare``, B28): the record of a configuration, written before any call, and the
parity of its requests with the run's own.

A configuration is a name bound to one system card, one solver, one run count and one ordered list of items; a
re-judging configuration is bound, in addition, to where it comes from (``origin``): the learning step of the run,
the unit and arm of that step whose cells sent this system card, its role (the base the run's gate compared
against, or a candidate of one card round) and the identity of the request construction (runtime and code). Its
record ``<bench>/<kind>-<config>.json`` is written (or compared) BEFORE the first call of a stage, and every item
record already in its folder is compared with it first: a stage that is run again under the same name with another
card stops before it writes or pays for anything. A report decides only on configurations whose registered items
all have their records.

Parity: a re-judging replicates a gate of the run, so for the run's own gate items the first request built here
under a configuration must be the request the run sent for the same item FROM THE CONFIGURATION'S OWN SOURCE: the
base from the cells of the unit the run's gate used as its baseline (a base or incumbent arm, never a candidate's),
a candidate from the cells of the card round whose writer wrote exactly this text. The run's learning-step cells are
read for that (practice side only: ``<chain>/s<k>/<unit>/cells``; a step directory holds no read unit); nothing is
sent. A stage runs only with a passing parity record of the same step, the same request identity and the same
cards.
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import units
from ..library import canonical_sha256

PROBE_ERROR = 'request_probe'    # the receipt of a request that is built and hashed, never sent
STEP_DIR = re.compile(r's[1-9][0-9]*')
UNIT_NAME = re.compile(r'[a-z][a-z0-9-]{0,39}')
CARD_ROUND = re.compile(r'card-r[1-9][0-9]*')
BASE_ARMS = ('B', 'F')           # the learning base and the incumbent: what a card gate compares a candidate against
CANDIDATE_ARM = 'cand_card'
ROLES = ('base', 'candidate')


# ---- configuration records -------------------------------------------------------------------------------------------
def _config_path(env, bench, kind, config):
    return env.path(bench, '%s-%s.json' % (kind, config))


def register(env, bench, kind, config, identity, ids, *, runs_of=None, exact=False):
    """Bind ``config`` to ``identity`` ({'card_sha256', 'solver', 'runs', ...}) and to the ordered item ids of this
    stage, BEFORE any call. An existing record must carry the same identity. Its items: with ``exact`` the same
    list (a judged population that changed since is refused: its records would mix two populations); without, they
    must be the head of the new list or the new list the head of them (a later run on more items of one ranking
    continues; the longer list is kept). Every item record already in the configuration's folder must carry the
    identity too, belong to the registered items and hold the expected number of runs (``identity['runs']``, or
    ``runs_of(id)`` when the count depends on the item); records written before this module existed have no
    configuration record and are checked the same way. Returns the record."""
    ids = list(ids)
    assert ids and len(set(ids)) == len(ids), 'A configuration is registered on distinct items'
    path = _config_path(env, bench, kind, config)
    stored = units.read_json(path) if path.exists() else None
    if stored is not None:
        assert {key: stored.get(key) for key in identity} == identity and set(stored) == set(identity) | {
            'bench', 'config', 'items'}, 'The configuration %s is registered with another card, solver or run count' % config
        old = stored['items']
        if exact:
            assert old == ids, 'The judged items changed since the configuration %s was registered' % config
        else:
            assert old[:len(ids)] == ids or ids[:len(old)] == old, \
                'The configuration %s is registered on other items' % config
    known = set(ids) | set(stored['items'] if stored else ())
    folder = env.path(bench, '%s-%s' % (kind, config))
    for row_path in sorted(folder.glob('*.json')) if folder.is_dir() else []:
        row = units.read_json(row_path)
        assert row.get('card_sha256') == identity['card_sha256'], \
            'The configuration %s holds records of another card' % config
        assert row.get('solver', 'G') == identity['solver'], \
            'The configuration %s holds records of another solver' % config
        assert row.get('id') in known, 'The configuration %s holds a record outside its items' % config
        want = identity['runs'] if identity.get('runs') is not None else runs_of(row['id']) if runs_of else None
        assert want is None or len(row['runs']) == want, \
            'The configuration %s holds records with another number of runs' % config
    if stored is not None and len(ids) <= len(stored['items']):
        return stored
    record = {'bench': bench, 'config': config, **identity, 'items': ids}
    units.write_json(path, record)
    return record


def registered(env, bench, kind, config):
    """The configuration's record, None when it has none."""
    path = _config_path(env, bench, kind, config)
    return units.read_json(path) if path.exists() else None


def complete_rows(record, rows, *, runs_of=None):
    """The item records of a registered configuration in the order of its items, or None when one is missing. Every
    record is compared with the registered identity (a folder of mixed identities is refused)."""
    out = []
    for name in record['items']:
        row = rows.get(name)
        if row is None:
            return None
        assert row['card_sha256'] == record['card_sha256'] and row.get('solver', 'G') == record['solver'], \
            'The configuration %s holds a record of another card or solver' % record['config']
        want = record['runs'] if record.get('runs') is not None else runs_of(name) if runs_of else None
        assert want is None or len(row['runs']) == want, \
            'The configuration %s holds a record with another number of runs' % record['config']
        out.append(row)
    return out


def comparable(first, second):
    """None when two registered re-judging configurations may be compared as base and candidate, else the reason:
    one base and one candidate of the SAME learning step and request identity, the same solver, run count (at least
    two) and items."""
    if first is None or second is None:
        return 'a configuration without a record of what it was registered on'
    a, b = first.get('origin'), second.get('origin')
    if not a or not b:
        return 'a configuration that was not registered as a re-judging of a run'
    if a['role'] != 'base' or b['role'] != 'candidate':
        return 'the base is not the run\'s base, or the candidate is not a candidate of a card round'
    if a['step_dir'] != b['step_dir'] or a['request_identity'] != b['request_identity']:
        return 'the configurations come from different steps or request constructions'
    if first['items'] != second['items'] or first['solver'] != second['solver'] or first['runs'] != second['runs']:
        return 'the configurations differ in items, solver or run count'
    if type(first['runs']) is not int or first['runs'] < 2:
        return 'the gate rule needs at least two runs per item'
    return None


# ---- parity with the run (no call) -----------------------------------------------------------------------------------
def request_identity(runtime, code):
    """What decides how a request is built besides the item and the card: the runtime table and the code (the
    caller's code identity: file hashes of this tree and of the bound machinery). Compared, never interpreted."""
    return {'runtime_sha256': canonical_sha256(runtime), 'code_sha256': canonical_sha256(code)}


def probe():
    """(call, seen): a ``call(system, user)`` that records the request hash and answers with a failed receipt (the
    request is built and never sent), and the list it fills."""
    seen = []

    def call(system, user):
        seen.append(units.sha256_text(system + '\x00' + user))
        return {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': PROBE_ERROR}
    return call, seen


def step_dir_of(path):
    path = Path(path).absolute()
    assert STEP_DIR.fullmatch(path.name) and path.is_dir(), 'A learning step directory s<k>: ' + str(path)
    return path


def base_source(unit):
    """The source of a base configuration: the cells of ``unit`` sent under a base or incumbent arm."""
    assert UNIT_NAME.fullmatch(unit) and not CARD_ROUND.fullmatch(unit), 'A unit of the step that is no card round'
    return {'role': 'base', 'unit': unit, 'arms': list(BASE_ARMS)}


def candidate_source(step_dir, card_text):
    """The source of a candidate configuration: the card round of the step whose writer wrote EXACTLY this text
    (its candidate cells), or None when no round did."""
    step_dir = step_dir_of(step_dir)
    for folder in sorted(step_dir.iterdir()):
        writer = folder / 'writer.json'
        if CARD_ROUND.fullmatch(folder.name) and writer.is_file() and units.read_json(writer).get('text') == card_text:
            return {'role': 'candidate', 'unit': folder.name, 'arms': [CANDIDATE_ARM]}
    return None


def run_cell_index(step_dir, source):
    """{(item id, system card sha256): {request sha256, ...}} over the cells of ONE unit of one learning step of a
    typed run, sent under the source's arms, that enabled no program: what the run sent for an item under a system
    card from that source. ``step_dir``: ``<chain>/s<k>``."""
    cells = step_dir_of(step_dir) / source['unit'] / 'cells'
    index = {}
    for path in sorted(cells.glob('*.json')) if cells.is_dir() else []:
        row = units.read_json(path)
        mounted = row.get('mount') or {}
        if str(row.get('arm', '')).split('#', 1)[0] not in source['arms'] or mounted.get('enabled') \
                or not row.get('request_sha256') or not row.get('system_card_sha256'):
            continue
        index.setdefault((row['item_id'], row['system_card_sha256']), set()).update(row['request_sha256'])
    return index


def parity(index, gate_items, system_sha, first_request_of):
    """One configuration against its source in the run: for every gate item for which the source holds a cell with
    this system card, is the first request built here (``first_request_of(item)``, no call) the one request the run
    sent? Counts only. The run mounts a learned card on the items its type map routes into the card's type, so some
    gate items have no cell with the card: they are counted apart and compare nothing."""
    same = differ = absent = 0
    for item in gate_items:
        stored = index.get((item['task_id'], system_sha))
        if not stored:
            absent += 1
            continue
        if stored == {first_request_of(item)}:
            same += 1
        else:
            differ += 1
    return {'card_sha256': system_sha, 'gate_items': len(gate_items), 'same_request': same, 'different': differ,
            'no_run_cell_with_this_card': absent}


def check_parity(env, bench, kind, step_dir, identity, gate_items, configurations):
    """The parity record ``<bench>/<kind>-parity.json``. ``configurations``: {name: (system card sha256, source or
    None, first_request_of)}; a configuration without a source (a candidate text no card round wrote) fails.
    ``ok``: every configuration has a source, at least one gate item with the same request and none with a
    different one, and exactly one of them is the base."""
    step_dir = step_dir_of(step_dir)
    rows = {}
    for name, (system_sha, source, first_request_of) in sorted(configurations.items()):
        if source is None:
            rows[name] = {'card_sha256': system_sha, 'source': None, 'gate_items': len(gate_items), 'same_request': 0,
                          'different': 0, 'no_run_cell_with_this_card': len(gate_items),
                          'error': 'no card round of the step wrote this text'}
            continue
        rows[name] = {**parity(run_cell_index(step_dir, source), gate_items, system_sha, first_request_of),
                      'source': source}
    ok = (bool(rows) and all(row['source'] and row['same_request'] > 0 and row['different'] == 0 for row in rows.values())
          and sum(row['source']['role'] == 'base' for row in rows.values() if row['source']) == 1)
    record = {'bench': bench, 'step_dir': str(step_dir), 'request_identity': identity, 'ok': ok, 'configurations': rows}
    units.write_json(env.path(bench, '%s-parity.json' % kind), record)
    return record


def require_parity(env, bench, kind, shas, step_dir, identity):
    """Refuse to run configurations whose requests were not compared with the run's: the parity record must be ok,
    of this learning step and this request identity, and cover every configuration with the system card it is
    about to mount. Returns {name: origin} (what the stage registers the configuration with)."""
    path = env.path(bench, '%s-parity.json' % kind)
    assert path.exists(), 'Run the parity check first (%s has no %s-parity.json)' % (bench, kind)
    record = units.read_json(path)
    assert record.get('ok') is True, 'The parity check found a request that differs from the run\'s'
    assert record['step_dir'] == str(step_dir_of(step_dir)), 'The parity check is of another learning step'
    assert record['request_identity'] == identity, 'The parity check was made with another runtime or code'
    origins = {}
    for config, sha in shas.items():
        row = record['configurations'].get(config)
        assert row is not None and row['card_sha256'] == sha, \
            'The parity check did not cover the configuration %s with this card' % config
        origins[config] = {'step_dir': record['step_dir'], 'request_identity': identity, 'role': row['source']['role'],
                           'unit': row['source']['unit']}
    return origins
