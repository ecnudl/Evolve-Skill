"""Main-v4 exclusion identities from pinned ID metadata, never test item text."""
from copy import deepcopy
import hashlib

from skillopt.coevo5 import data
from skillopt.continual_eval.core import require, safe_path
from skillopt.validator_pilot.api import digest
from . import exclusion, profiles as p

TRAINING_PARTS = frozenset({'train', 'val', 'development', 'skill_confirmation'})
TEST_PARTS = frozenset({'test', 'final', 'sealed'})


def id_hash(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def _hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def derive(imported, *, access):
    """Use the inherited exclusion consent and a TestAccess for ID-only metadata.

    The registered historical pools include train + val. Extension evaluation
    blocks and every other partition stay closed, including unknown partitions.
    SearchQA's dropped entries are already hashes; ALF's game identity is a
    separate aggregate digest, not a task ID and not reversible to game paths.
    """
    require(isinstance(access, data.TestAccess), 'Protected IDs require TestAccess')
    records = imported['exclusion_records']
    search = p.verified(records[exclusion.SEARCHQA_RUN], exclusion.RECORD_KIND)
    alf = p.verified(records[exclusion.ALFWORLD_RUN], exclusion.RECORD_KIND)
    consent = {row['consent_sha256'] for row in records.values()}
    require(len(consent) == 1 and all(_hash(v) for v in consent), 'One inherited exclusion consent')
    require(search['run'] == exclusion.SEARCHQA_RUN
            and search['exclusion_sha256'] == digest(search['dropped'])
            and all(_hash(v) for v in search['dropped']), 'Pinned SearchQA dropped-ID hashes')
    require(alf['run'] == exclusion.ALFWORLD_RUN and alf['split'] == exclusion.TEST_SPLIT
            and alf['disjoint'] is True and alf['counts']['test_games'] > 0
            and alf['counts']['overlap_games'] == 0 and _hash(alf['exclusion_sha256']),
            'Passing ALFWorld test identity')
    pinned = imported['data']['pinned']
    split = data._split(pinned)
    result = {}
    for bench in p.BENCHES:
        split_path = str(safe_path(pinned['paths']['split']))
        sources = {'split': {'path': split_path, 'sha256': pinned['sha256'][split_path]}}
        groups = []
        if bench in split['splits']:
            groups.append(split['splits'][bench])
        evaluation_ids = []
        if bench in data.EXTENSIONS:
            layout = data._layout(pinned, bench)
            groups.append(layout['parts'])
            blocks = layout.get('evaluation_blocks', {})
            evaluation_ids = blocks.get('items', [])
            require(isinstance(evaluation_ids, list)
                    and all(isinstance(v, str) and v for v in evaluation_ids),
                    'Extension evaluation blocks contain IDs only')
            path = str(safe_path(pinned['paths']['layouts'][bench]))
            sources['layout'] = {'path': path, 'sha256': pinned['sha256'][path]}
        require(groups, 'Every benchmark has pinned partition metadata')
        protected, tests, partitions = set(), set(), {}
        for group in groups:
            require(isinstance(group, dict), 'Pinned partition mapping')
            for part, entries in group.items():
                require(isinstance(entries, list), 'Pinned partition ID list')
                ids = [str(row['task_id']) for row in entries]
                require(all(ids) and len(ids) == len(set(ids)), 'Distinct nonempty partition IDs')
                if part not in TRAINING_PARTS:
                    hashes = {id_hash(v) for v in ids}
                    protected.update(hashes)
                    partitions[part] = partitions.get(part, 0) + len(ids)
                    if part in TEST_PARTS:
                        tests.update(hashes)
        require(tests, 'Every benchmark needs nonempty pinned protected test IDs')
        protected.update(id_hash(v) for v in evaluation_ids)
        partitions['evaluation_blocks'] = len(evaluation_ids)
        if bench == 'searchqa':
            protected.update(search['dropped'])
            sources['searchqa_exclusion'] = {'record_sha256': search[p.RECORD_HASH],
                'exclusion_sha256': search['exclusion_sha256'], 'dropped_count': len(search['dropped'])}
        if bench == 'alfworld':
            sources['alfworld_test_identity'] = {'record_sha256': alf[p.RECORD_HASH],
                'exclusion_sha256': alf['exclusion_sha256'], 'split': alf['split'],
                'counts': deepcopy(alf['counts']), 'disjoint': True}
        hashes = sorted(protected)
        result[bench] = {'id_hashes': hashes, 'protected_ids_sha256': digest(hashes),
            'count': len(hashes), 'test_count': len(tests), 'partitions': partitions,
            'sources': sources, 'consent_sha256': next(iter(consent)), 'access_unit': access.unit,
            'item_text_reads': 0}
    return validate(result)


def validate(value):
    require(isinstance(value, dict) and set(value) == set(p.BENCHES), 'Five protected-ID identities')
    for bench, row in value.items():
        hashes = row.get('id_hashes')
        require(isinstance(hashes, list) and hashes and all(_hash(v) for v in hashes)
                and hashes == sorted(set(hashes)) and row.get('count') == len(hashes)
                and type(row.get('test_count')) is int and 0 < row['test_count'] <= len(hashes)
                and row.get('protected_ids_sha256') == digest(hashes)
                and row.get('item_text_reads') == 0 and _hash(row.get('consent_sha256'))
                and row.get('access_unit') == 'v211-s0-protected-ids',
                'Nonempty source-bound protected-ID identity')
        sources = row.get('sources', {})
        expected = {'split'} | ({'layout'} if bench in data.EXTENSIONS else set())
        if bench == 'searchqa':
            expected.add('searchqa_exclusion')
        if bench == 'alfworld':
            expected.add('alfworld_test_identity')
        require(set(sources) == expected and all(
            isinstance(sources[key].get('path'), str) and _hash(sources[key].get('sha256'))
            for key in ('split', 'layout') if key in expected), 'Pinned protected-ID metadata sources')
        for key in expected - {'split', 'layout'}:
            require(_hash(sources[key].get('record_sha256')) and _hash(sources[key].get('exclusion_sha256')),
                    'Pinned protected-ID exclusion record')
    return value


def check_items(bench, items, hashes):
    protected = set(hashes)
    require(protected and all(_hash(v) for v in protected), 'Nonempty protected-ID set is required')
    allowed = TRAINING_PARTS | ({'tail'} if bench == 'searchqa' else set())
    if bench == 'alfworld':
        allowed |= {'fresh'}
    for item in items:
        labels = [item[key] for key in ('partition', 'part') if key in item]
        require(labels and all(label in allowed for label in labels), 'Only training-side supplies may be allocated')
        require(id_hash(item['task_id']) not in protected, 'Allocation overlaps protected or already consumed IDs')
