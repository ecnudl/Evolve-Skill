"""Main-v5 preparation from frozen metadata and practice supplies only.

The main-v4 S0 carries reviewed protected-ID hashes. Reusing those hashes avoids
opening split/layout/test files during the new preparation. No test panel or
historical read result is consulted. All active maps remove LiveMath.
"""
from copy import deepcopy
import hashlib
from types import SimpleNamespace

from skillopt.continual_eval.core import read_json, require, safe_path
from skillopt.validator_pilot.api import digest
from . import (confirm, manifest, profiles as p, step, v211_allocation,
               v211_protection, zebra_smoke, zebralogic as z)

RETAINED = ('searchqa', 'officeqa', 'spreadsheetbench', 'alfworld')
LEARNED = RETAINED[:-1]


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _practice_paths(source):
    """Refuse an inherited practice pin that aliases a closed data source."""
    pinned = source['data']['pinned']['paths']
    closed = {safe_path(pinned['split'])}
    for group in ('test', 'layouts', 'upstream'):
        closed.update(safe_path(path) for path in pinned[group].values())
    for bench in RETAINED:
        path = safe_path(source['data']['pools'][bench]['path'])
        require(path not in closed and not any(path.is_relative_to(root) for root in closed),
                'A retained practice pool must not alias a sealed source')
    tail = safe_path(source['data']['searchqa_tail']['path'])
    require(tail not in closed and not any(tail.is_relative_to(root) for root in closed),
            'The SearchQA tail must not alias a sealed source')


def _allocations(source):
    """Recompute the three unchanged allocations without opening partition metadata."""
    protected = v211_protection.validate(source['protected_ids'])
    _practice_paths(source)
    data = source['data']
    carrier = SimpleNamespace(setting=SimpleNamespace(extra={
        'searchqa_tail': manifest._searchqa_tail(data)}))
    tail, kept = step._tail(carrier)
    found = {}
    for bench in LEARNED:
        previous = source['allocations'][bench]
        require(previous['source_pins']['pool'] == data['pools'][bench]
                and previous['source_pins']['protected_ids'] == protected[bench],
                'Inherited allocation pool and protected-ID pins must agree')
        pool = manifest._items(data['pools'][bench], bench)
        _, allocated = v211_allocation.allocate(bench, pool,
            tail=tail if bench == 'searchqa' else (),
            kept=kept if bench == 'searchqa' else None,
            protected_hashes=protected[bench]['id_hashes'],
            source_pins=deepcopy(previous['source_pins']),
            provenance=deepcopy(previous['provenance']))
        require(allocated == previous, 'Inherited allocation changed: ' + bench)
        found[bench] = allocated
    # Step 5 is imported, but its retained supply/protected provenance is checked.
    v211_protection.check_items('alfworld', manifest._items(data['pools']['alfworld'], 'alfworld'),
                               protected['alfworld']['id_hashes'])
    return found


def preparation(main_v4_s0_file, *, zebra_pool=z.POOL_PATH,
                zebra_split_manifest=z.SPLIT_MANIFEST_PATH, configuration=p.MAIN_V5):
    """Return a mixed preparation; only the source S0 and practice files are read.

    Source identities and active mappings are copied by value. The original
    main-v4 S0 is never rewritten, and its LiveMath inputs are never opened.
    ``zebra_split_manifest`` is the public hash inventory, not the sealed panel.
    """
    path = safe_path(main_v4_s0_file)
    raw = path.read_bytes()
    import json
    source = p.verified(json.loads(raw), 'v211-s0')
    require(source.get('configuration') == p.MAIN_V4 and source.get('passed') is True
            and source.get('sealed_reads') == 0 and source.get('pytest', {}).get('passed') is True,
            'main-v5 requires a passing frozen main-v4 S0 with no sealed reads')
    require(set(source['cards']) == set(p.BENCHES)
            and all(set(source[key]) == set(p.BENCHES) for key in ('contracts', 'runtime'))
            and set(source['data']['pools']) == set(p.BENCHES),
            'The source S0 must carry all original five-benchmark preparation maps')
    allocated = _allocations(source)
    pool = z.load_pool(zebra_pool)
    split = zebra_smoke._split_pins(zebra_split_manifest)
    cuts = z.slices(pool)
    confirmed = confirmation_identity(configuration, pool)
    data = deepcopy(source['data'])
    data['pools'] = {bench: deepcopy(data['pools'][bench]) for bench in RETAINED}
    data['pools'][z.BENCH] = {'path': str(safe_path(zebra_pool)), 'sha256': z.POOL_SHA256}
    removed = set()
    for group, entries in data['pinned']['paths'].items():
        if isinstance(entries, dict) and 'livemath' in entries:
            removed.add(str(safe_path(entries.pop('livemath'))))
    data['pinned']['sha256'] = {key: value for key, value in data['pinned']['sha256'].items()
                               if key not in removed}
    data['pinned']['zebralogic'] = deepcopy(z.identity()['sealed'])
    # These historical estimates are not valid for the new roster/stage read.
    data.pop('test_read_estimate', None)
    data.pop('test_read_terms', None)
    if isinstance(data.get('research'), dict):
        data['research'].pop('livemath', None)
    data.update(zebra_pc=z.identity(), split_manifest=split, confirm=confirmed,
                zebra_slice_ids={key: [item['task_id'] for item in rows] for key, rows in cuts.items()})
    return {
        'registration': {'configuration': configuration,
            'source_main_v4_s0': {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                                 'record_sha256': source[p.RECORD_HASH]},
            'inherited': deepcopy(source['registration']),
            'zebra_pool': deepcopy(data['pools'][z.BENCH]), 'zebra_split_manifest': deepcopy(split),
            'sealed_reads': 0, 'protected_id_basis': 'frozen_main_v4_s0_by_value'},
        'data': data,
        'exclusion_records': deepcopy(source['exclusion_records']),
        'cards': {**{b: source['cards'][b] for b in RETAINED}, z.BENCH: z.CARD_TEXT},
        'contracts': {**{b: deepcopy(source['contracts'][b]) for b in RETAINED},
                      z.BENCH: {'text': z.CONTRACT, 'sha': hashlib.sha256(z.CONTRACT.encode()).hexdigest()}},
        'runtime': {**{b: deepcopy(source['runtime'][b]) for b in RETAINED},
                    z.BENCH: dict(zebra_smoke.RUNTIME)},
        'sheet_qualification': deepcopy(source['sheet_qualification']),
        'fixtures': deepcopy(source['fixtures']),
        'allocations': allocated,
        'protected_ids': {b: deepcopy(source['protected_ids'][b]) for b in RETAINED},
        'confirm': confirmed,
        'zebra_slices': {key: {'items': len(rows), 'ids_sha256': digest([item['task_id'] for item in rows])}
                         for key, rows in cuts.items()},
    }


def verify(value):
    """Reopen only the declared S0/practice inputs and compare the complete bridge."""
    registration = value['registration']
    source = registration['source_main_v4_s0']
    require(_sha(source['path']) == source['sha256'], 'Frozen main-v4 S0 bytes changed')
    found = preparation(source['path'], zebra_pool=registration['zebra_pool']['path'],
                        zebra_split_manifest=registration['zebra_split_manifest']['path'],
                        **({'configuration': registration['configuration']}
                           if p.is_implant_v5(registration['configuration']) or p.is_v218(registration['configuration']) else {}))
    require(found == value, 'The mixed preparation differs from its source identities')
    return found


def confirmation_identity(configuration, pool):
    selected = p.ZEBRA_PC_V15 if p.is_v218(configuration) else p.ZEBRA_PC_V13
    found = confirm.identity(selected, pool)
    if p.is_v218(configuration):
        found = {**found, 'freshness': p.confirm_freshness(configuration, z.BENCH)}
    return found
