"""typed-v2 step 5m: the mount identity of design 3.4 ("Shared arms") and the split of ``mount._routed_mount`` into
``_route`` (the routing part, no call) and the selection part (fakes only: scripted selectors, no network, no Docker,
no /data, no files).

Golden values. ``GOLDEN`` holds per case the sha256 of the JSON bytes (insertion order, ``ensure_ascii=False``) of
what ``mount.mount`` returned and the selection requests it sent, or of the refusal it raised and the requests sent
before it. They were computed on 2026-11-12 BEFORE the split, twice, with equal results: with the committed
``T/mount.py`` of commit 8375ecb (the untouched starting point of the typed-v2 build; ``git show`` output loaded as a
module of the typed package from a scratch directory) and with the working-tree file before the edit (the same code;
step 1a had changed two docstring lines only). The fixture embeddings are exact axis vectors, so every centroid,
distance and threshold is exact or one correctly rounded square root: the digests do not depend on the interpreter's
float summation (Python 3.12 changed ``sum`` over floats; the real suite also runs on 3.11).
"""
import hashlib
import inspect
import json

import pytest

from skillopt.execskill.package import Procedure
from skillopt.execskill.typed import ORDER, library as lib, mount, tasktypes as typing_
from tests.execskill_fakes_env import Script, receipt
from tests.fixtures.execskill.items import searchqa_items

IDENTITY_KEYS = ('system_card_sha256', 'programs_offered', 'forced')
SOURCE = ('"""A fixture program."""\n\n\ndef applies(view):\n    return True\n\n\n'
          'def before_call(view, state):\n    return None\n')
OTHER_SOURCE = SOURCE.replace('A fixture program.', 'Another fixture program.')
CARD_TEXT = '- read every snippet before answering'
NEW_CARD = '- a new card'
QA_TEXTS = ['Which fixture town keeps the bell number %d?' % i for i in range(40)]
TREASURY_TEXTS = ['Which treasury table keeps the receipt number %d?' % i for i in range(40)]
ZEBRA_QUESTION = ('There are 2 houses, numbered 1 to 2 from left to right, as seen from across the street. Each house '
                  'is occupied by a different person. Eric drinks milk. The milk drinker lives in house 1. Arnold '
                  'drinks tea.')
ZEBRA_ITEM = {'benchmark': 'zebralogic', 'task_id': 'fx-zebra-1',
              'public': {'question': ZEBRA_QUESTION, 'columns': ['Name', 'Drink']},
              'private': {'answer': {'House 1': {'Name': 'Eric', 'Drink': 'milk'},
                                     'House 2': {'Name': 'Arnold', 'Drink': 'tea'}}}}
ZEBRA_TEXTS = ['There are %d houses in the fixture street.' % i for i in range(2, 42)]
USE_A = ['{"use": ["snippet-scanner-a"], "why": "use it"}']
NONE_SELECTED = ['{"use": [], "why": "none applies"}']
# refused by mount in its selection part (after the routing): mount_identity makes no selection, so it does not refuse
SELECTION_PART = ('refused-programs-without-selector', 'refused-forced-id-already-mounted')


# ---- fixtures ------------------------------------------------------------------------------------------------
class AxisEmbedder:
    """Exact unit vectors, one axis per text family, counting its calls (every routing number is exact)."""

    def __init__(self):
        self.calls = 0

    def __call__(self, texts):
        self.calls += 1
        return [[1.0 if i == (3 if 'treasury' in text else 4) else 0.0 for i in range(8)] for text in texts]


def program_record(pid, source=SOURCE):
    return Procedure(id=pid, origin='searchqa', description='A fixture program.', hooks=('applies', 'before_call'),
                     source=source, evidence='engineering_fixture', max_note_chars=600).to_json()


def card_skill(tid, text=CARD_TEXT, name='evidence-answer-card'):
    return lib.make_skill(skill_id='card-%s-s1' % tid, name=name, kind='card', home_type=tid, body={'text': text},
                          origin={'chain': 'G', 'step': 1, 'bench': 'searchqa'}, description='For evidence QA.')


def program_skill(tid, letter, *, source=SOURCE):
    return lib.make_skill(skill_id='prog-%s-s1-%s' % (tid, letter), name='snippet-scanner-' + letter, kind='program',
                          home_type=tid, body={'procedure': program_record('fx-typed-' + letter, source)},
                          origin={'chain': 'G', 'step': 1, 'bench': 'searchqa'},
                          description='Scans the snippets for named values.')


def world(embed, *, card=True, programs=1, program_source=SOURCE, merged=False):
    """A type map with one QA source and type t01 (plus, when ``merged``, a second source merged into it: the shape of
    the no-harm scratch map) and a library with the type's card and programs; returns (map, library, type, vectors)."""
    tm = typing_.TypeMap()
    sid = tm.add_source({'path': '/x/searchqa.json', 'sha256': 'a' * 64}, 'question/context', embed(QA_TEXTS), step=1)
    tid = tm.new_type(sid, step=1)
    vectors = {'qa': tm.data['sources'][sid]['centroid']}
    if merged:
        other = tm.add_source({'path': '/x/officeqa.json', 'sha256': 'b' * 64}, 'question/context',
                              embed(TREASURY_TEXTS), step=2)
        tm.merge_source(other, tid, step=2, evidence={'fixture': 'merged'})
        vectors['treasury'] = tm.data['sources'][other]['centroid']
    library = lib.Library()
    if card:
        library.add(card_skill(tid))
        tm.set_card(tid, 'card-%s-s1' % tid, step=1)
    for letter in 'abc'[:programs]:
        skill = program_skill(tid, letter, source=program_source)
        library.add(skill)
        tm.add_program(tid, skill['skill_id'], step=1)
    return tm, library, tid, vectors


def zebra_world(embed):
    tm = typing_.TypeMap()
    sid = tm.add_source({'path': '/x/zebralogic.json', 'sha256': 'c' * 64}, 'puzzle_template', embed(ZEBRA_TEXTS),
                        step=1)
    tid = tm.new_type(sid, step=1)
    library = lib.Library()
    library.add(card_skill(tid, '- fill the grid house by house', 'grid-card'))
    tm.set_card(tid, 'card-%s-s1' % tid, step=1)
    return tm, library, tid, {'qa': tm.data['sources'][sid]['centroid']}


def plain_case(bench):
    """An item of each bench with what ``mount`` needs to derive (QA, ZebraLogic) or receive (the others) its view."""
    if bench == 'searchqa':
        return searchqa_items(1)[0], {}
    if bench == 'zebralogic':
        return ZEBRA_ITEM, {'runtime': {'zebralogic': {}}}
    views = {'officeqa': {'question': 'What is the 2020 excise total?', 'context': 'Year | Excise\n2020 | 305'},
             'spreadsheetbench': {'instruction': 'Put the sum of A1:A3 in B1.', 'workbook_preview': 'A1=1 A2=2 A3=3'},
             'alfworld': {'task': 'put a clean mug in the coffee machine', 'admissible_commands': ['go to sink 1']}}
    item = {'benchmark': bench, 'task_id': 'fx-%s-1' % bench, 'public': dict(views[bench]), 'private': {}}
    return item, {'view': views[bench]}


def cases(embed):
    """The golden table (fresh worlds per call): C0 and C on every bench; every routed arm on every routing shape
    (typed, type without skills, merged source, unseen signature, distance above p95, ZebraLogic); every selection
    outcome; every candidate outcome; every refusal of ``mount``, including the order of two faults."""
    table = []

    def add(name, bench, item, replies=None, **kw):
        table.append({'name': name, 'bench': bench, 'item': item, 'kw': kw, 'replies': replies})

    def routed(name, state, arm='F', replies=None, *, vector='qa', candidate=None, bench='searchqa', item=None, **extra):
        tm, library, _, vectors = state
        add(name, bench, item or qa, replies, arm=arm, typemap=tm, library=library,
            vector=vectors[vector] if isinstance(vector, str) else vector, candidate=candidate, **extra)

    for bench in ORDER:
        item, extra = plain_case(bench)
        for arm in ('C0', 'C', 'B'):  # B: the learning base of step 5b (addendum D17), under the default base 'format'
            add('%s-%s' % (arm, bench), bench, item, arm=arm, typemap=None, library=None, vector=None, **extra)
    qa = searchqa_items(1)[0]
    far = embed(['treasury table z'])[0]
    bare, empty, two = world(embed, programs=0), world(embed, card=False, programs=0), world(embed, programs=2)
    solo, one = world(embed, card=False, programs=1), world(embed, programs=1)
    merged, zebra = world(embed, programs=1, merged=True), zebra_world(embed)
    unseen = (typing_.TypeMap(), lib.Library(), None, {'qa': None})
    tid = bare[2]
    card = {'text': NEW_CARD, 'home_type': tid}
    program = {'procedure': program_record('fx-cand-prog'), 'home_type': tid}
    zebra_kw = {'bench': 'zebralogic', 'item': ZEBRA_ITEM, 'runtime': {'zebralogic': {}}}

    routed('F-card-no-programs', bare, replies=[])
    routed('F-type-without-skills', empty, replies=[])
    routed('F-programs-format-retry', two,
           replies=['not json at all', '{"use": ["snippet-scanner-b"], "why": "named values"}'])
    routed('F-programs-both-selected', two, replies=['{"use": ["snippet-scanner-b", "snippet-scanner-a"], "why": "both"}'])
    routed('F-programs-parse-failure', two, replies=['{"use": ["other-skill"], "why": "x"}', receipt('', ok=False)])
    routed('F-programs-none-selected', two, replies=NONE_SELECTED)
    routed('F-no-card-one-program', solo, replies=USE_A)
    routed('F-merged-source', merged, replies=USE_A, vector='treasury')
    routed('F-unseen-signature', unseen, vector=None)
    routed('F-distance-above-p95', one, replies=[], vector=far)
    routed('F-zebralogic', zebra, replies=[], **zebra_kw)
    routed('cand_card-applied', bare, 'cand_card', [], candidate=card)
    routed('cand_card-applied-with-programs', two, 'cand_card', USE_A, candidate=card)
    routed('cand_card-incumbent-text', bare, 'cand_card', [], candidate={'text': CARD_TEXT, 'home_type': tid})
    routed('cand_card-other-type', one, 'cand_card', NONE_SELECTED, candidate={'text': NEW_CARD, 'home_type': 't99'})
    routed('cand_card-distance-above-p95', bare, 'cand_card', [], vector=far, candidate=card)
    routed('cand_card-unseen-signature', unseen, 'cand_card', vector=None, candidate=card)
    routed('cand_card-zebralogic', zebra, 'cand_card', [], candidate=card, **zebra_kw)
    routed('cand_program-applied', bare, 'cand_program', [], candidate=program)
    routed('cand_program-applied-after-selection', two, 'cand_program', USE_A, candidate=program)
    routed('cand_program-procedure-object', bare, 'cand_program', [],
           candidate={'procedure': Procedure.from_json(program['procedure']), 'home_type': tid})
    routed('cand_program-no-card', solo, 'cand_program', NONE_SELECTED, candidate=program)
    routed('cand_program-other-type', one, 'cand_program', USE_A, candidate={**program, 'home_type': 't99'})
    routed('cand_program-distance-above-p95', one, 'cand_program', [], vector=far, candidate=program)
    routed('cand_program-unseen-signature', unseen, 'cand_program', vector=None, candidate=program)

    no_map = (None, None, tid, bare[3])
    card_disagrees, programs_disagree = world(embed, programs=0), world(embed, programs=1)
    card_disagrees[0].set_card(tid, 'card-of-another-step', step=2)
    programs_disagree[0].add_program(tid, 'prog-t01-s2-z', step=2)
    # typed-v2 step 5b: B became a mount arm (addendum D17); the unknown arm is now a read event, which never mounts
    add('refused-unknown-arm', 'searchqa', qa, arm='S1', typemap=None, library=None, vector=None)
    add('refused-item-without-public', 'searchqa', {'task_id': 'fx-x'}, arm='C0', typemap=None, library=None,
        vector=None)
    routed('refused-unregistered-shape', bare, view={'unknown_field': 'x'})
    routed('refused-missing-vector', bare, vector=None)
    routed('refused-no-type-map', no_map)
    routed('refused-F-with-candidate', bare, candidate=card)
    routed('refused-candidate-without-home-type', bare, 'cand_card', candidate={'text': NEW_CARD})
    routed('refused-blank-card-candidate', bare, 'cand_card', candidate={'text': ' ', 'home_type': tid})
    routed('refused-program-candidate-not-a-record', bare, 'cand_program',
           candidate={'procedure': SOURCE, 'home_type': tid})
    routed('refused-map-library-card-disagree', card_disagrees)
    routed('refused-map-library-programs-disagree', programs_disagree, replies=USE_A)
    routed('refused-order-map-before-candidate', no_map, candidate=card)
    routed('refused-order-candidate-before-vector', bare, 'cand_card', vector=None,
           candidate={'text': ' ', 'home_type': tid})
    routed('refused-programs-without-selector', one)
    routed('refused-forced-id-already-mounted', one, 'cand_program', USE_A,
           candidate={'procedure': program_record('fx-typed-a'), 'home_type': tid})
    return table


def mount_payload(module, case):
    """What ``module.mount`` returned for the case and the selection requests it sent, or its refusal."""
    selector = Script(case['replies']) if case['replies'] is not None else None
    try:
        record = module.mount(case['bench'], case['item'], selector=selector, **case['kw'])
    except ValueError as error:
        return {'error': type(error).__name__, 'message': str(error), 'requests': _requests(selector)}
    return {'record': record, 'requests': _requests(selector)}


def _requests(selector):
    return [list(pair) for pair in selector.requests] if selector is not None else None


def digest(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode('utf-8')).hexdigest()


def golden_digests(module, embed):
    return {case['name']: digest(mount_payload(module, case)) for case in cases(embed)}


def identity_of(case):
    return mount.mount_identity(case['bench'], case['item'], **case['kw'])


def expected_identity(record, library):
    """The identity read off a mount record: the composed system card's hash, the offered programs (library order)
    with their skill hashes, the record hash of a program candidate that was applied."""
    candidate = record['candidate'] or {}
    applied = candidate.get('kind') == 'program' and candidate.get('applied') is True
    return {'system_card_sha256': record['system_card_sha256'],
            'programs_offered': [[sid, library.get(sid)['sha256']] for sid in record['programs_offered']],
            'forced': candidate['sha256'] if applied else None}


# pinned before the split (see the module docstring); one digest per case of ``cases``
GOLDEN = {
    'C0-searchqa': '6f10f495bba0fb363f57a909e112a8e91b663dcfd85d54c870f96088b92ed6f7',
    'C-searchqa': 'd40c1bed1ae1df6d6bf009c02fedf5f5df8c3732c9d59c5dbcae50273b00f293',
    'C0-officeqa': '3f48f6439a7ef62b07502ca93c7f8cbd0b95385c177749fd07d84a05abad0e7e',
    'C-officeqa': '04687bf533cea9fbf1353952ae273b2d5f54ce3e1b7b57f0641d2ab64ffe125f',
    'C0-zebralogic': 'a97e4059a1fc0a7b8299115cdd8747d7a01b20a332ca2dde4242a26caee592a8',
    'C-zebralogic': '7fa8f69df0f1e7b893c232db17a8f2748ab3547c367908d6302c6400c40f6f7e',
    'C0-spreadsheetbench': '82c6f1aac048142efa72439457fd33ae0e97c9e1205051d183cc11e89d0a9e0e',
    'C-spreadsheetbench': '39beb5a3957c483e9eabc1f65048c2346f944d6c8f5d85d103dcccbc807eb4ec',
    'C0-alfworld': '1cddbbfa5811452cf39ad300513b1aece6325302a7821978a498107bff2dcb42',
    'C-alfworld': 'a31b8bcb70c4af7dd450403e785ae99ddba76f70e187b5888e14d1dab82cec1f',
    # typed-v2 step 5b (addendum D17): arm B under the default base 'format'; each value is the digest of the C0 case
    # of the same bench computed with the cdf85b6 mount, its record's arm set to 'B' (B mounts what C0 mounts)
    'B-searchqa': '4e71ef3b37d2d556975a6030c268ad48b291e1ca265f8d7316f734215244120f',
    'B-officeqa': 'd974f341c403ca4df0e144d75b4fbe73e6722a40df2e7a118cc9b900fa6e039a',
    'B-zebralogic': '10f3573be9b0c8d6397f2914e720460d8dca0f74dc87ab65a239e81a249dfbc7',
    'B-spreadsheetbench': 'c21bcc493ea3bb0a9e8953296a3d8d714658f85647ac75115d316656f6053e32',
    'B-alfworld': '7af5e7e25eb1d34cf8a6ee2f679064d99b019d8217557a0d40d11191c2df75de',
    'F-card-no-programs': 'b4742745c3e9578f2f37e3d7cc120d2c76bf34d8eaef2f45489197c1541b23aa',
    'F-type-without-skills': '778d47bc2ff519e0d894300838652bffd97a6dab7b85c69fad3262e396335a0f',
    'F-programs-format-retry': 'c301ea29582a3affaaad413acf59f6362b83eb2fbdf30f3ac62cace517881163',
    'F-programs-both-selected': 'e177ead73d002dd7fc200c8141f6e81822da5883eefcc86fd9e04b8fceae63c0',
    'F-programs-parse-failure': '89ff15d921e3567329c0a5f3b2eac10b75695f5b21b12622c5c1e7be3a4ce9dd',
    'F-programs-none-selected': '5fd67c67988966cca462cb7273759cf3d8841e01fc7deba7db534c3dcac24e9f',
    'F-no-card-one-program': '0c90d08eb974b1dd0e3bf76abb719b62c674bb45691b10e1e3357d06b9ce9f7b',
    'F-merged-source': '9baa6756899310ea5fcd4ead9e400f09c5a391754a25c1867da589e5a03c40dc',
    'F-unseen-signature': '70b1a9a547a046a30fbc86b700d3246a7dc254f3cd16a926c20d50907076f5ca',
    'F-distance-above-p95': '461c691c8649504ac0dcace898764c3bf4b89885722a3e6a331e32e7501c6ad8',
    'F-zebralogic': '82bcf5ed4b58d2c174851044991c5a822f902d41658aa8cf12ff28130ae8e712',
    'cand_card-applied': 'd3ac021820e2196eb119daeeb673619d51869ddc2921cc704ede3b1065dbfc0d',
    'cand_card-applied-with-programs': 'fdae834445020c77fa212a4666151dd30f99323a7c55d5277449ae9fe0900029',
    'cand_card-incumbent-text': 'fd2cf7096917e970ed368440d07e4b645396f6be55923a3bd1ddbe8cf55ccddd',
    'cand_card-other-type': 'fa63bce57586585dfd08262e4ca3bda32888015a7aa637a9284896a70e05fc4b',
    'cand_card-distance-above-p95': '6e63254bed7348b765caf2ea952acefaebe94d8284ca0dd9742e824f76e4b1c4',
    'cand_card-unseen-signature': '0ede545193c512571260111170d0b27332f0854b9d630d2e7172823816fc07f0',
    'cand_card-zebralogic': '74a2b667bb3c8f1caf22acad28a56a844204ee00ea04e9664809a36d570311dd',
    'cand_program-applied': 'e2ce775e7ce44018978ecb5b6e9dff4ae6df6c8438a645d4480e04f31787924d',
    'cand_program-applied-after-selection': '37e9cba7a738bd997a1f4e17569fdf4ad69de435475a0a574a1365fc93ba0c0b',
    'cand_program-procedure-object': 'e2ce775e7ce44018978ecb5b6e9dff4ae6df6c8438a645d4480e04f31787924d',
    'cand_program-no-card': 'ff4d611d47330427f63b2dcbbb41746b403645a4e86ac4af6a4b9d39ce3720f4',
    'cand_program-other-type': 'd42bfe1aa60ed044eda121d14b00f91b18ea0360b4713408b37345b61d1902a4',
    'cand_program-distance-above-p95': '596bbfe336b7409e16762e0ea3738f3b662f4b07a602d6a65425923e0ccdd3c9',
    'cand_program-unseen-signature': 'cef0ae35ceb7d3de230eb3093bb5c704e035769361e846ad9756e97f76e2ae20',
    # step 5b: the unknown arm is 'S1' (B became a mount arm); value computed with the cdf85b6 mount
    'refused-unknown-arm': '6ad83ae6a9def6b98c1d4d36f21cdb6db27e8c1fb2e2f8dc37c2feb35377cd3c',
    'refused-item-without-public': '7ed6402d3fc906caee88bb785fd76df9e16ae52234dddb11cebcf6fbfdd285c5',
    'refused-unregistered-shape': '5d65063297c4daae17542be9c9727312ea63a293eca09da75fc13399c82abb19',
    'refused-missing-vector': '183bf7fdf0a5c757094260781056459d6cfeb4ac342729ec51fd56ab58a6ef86',
    'refused-no-type-map': '7d7b0ea5c2386c7c46c623d47641bd17a0c3cfb931616d7f0e01f59b6d8f7108',
    'refused-F-with-candidate': '18c2248bdfe24ffb864f7b3045e8a9d6184d32bfa5e60d5aa970df41b67b39c3',
    'refused-candidate-without-home-type': '1b3949760fdd586db7e4e65608d53c2e6b4ed338efddd0002323b02cc726f5fe',
    'refused-blank-card-candidate': 'db8c7cfaff41a5cc158d46e126c3bd7422a123b7421e6e7f4f9a28d40ab4da8a',
    'refused-program-candidate-not-a-record': '1b0f4ea6fc28524d5c95319dc571628d077c198d5f872d11723e06dc7f31396a',
    'refused-map-library-card-disagree': 'e581495f2c9704b96ff594cb45564d71e5315bccc7f2e96839b41c0e9442068f',
    'refused-map-library-programs-disagree': 'e5ab98b5e7fa6f34c85f3145632d1c594d66e71f8cbe4f62027cbbc0f76fdee8',
    'refused-order-map-before-candidate': '7d7b0ea5c2386c7c46c623d47641bd17a0c3cfb931616d7f0e01f59b6d8f7108',
    'refused-order-candidate-before-vector': 'db8c7cfaff41a5cc158d46e126c3bd7422a123b7421e6e7f4f9a28d40ab4da8a',
    'refused-programs-without-selector': '233a25435e3ebfb1a4afc8c17bda3a6424105cdbd74a7604ea19337d70820384',
    'refused-forced-id-already-mounted': '380cc8d017610ce341cd4f7ad60ba6217b1f098fa886b5c1a8938766a2bf3be4',
}


# ---- the split leaves every mount record and request unchanged -------------------------------------------------
def test_mount_records_and_selection_requests_are_byte_identical_to_the_committed_version():
    assert golden_digests(mount, AxisEmbedder()) == GOLDEN


def test_golden_table_covers_every_arm_selection_status_candidate_outcome_and_bench():
    table = cases(AxisEmbedder())
    payloads = {case['name']: mount_payload(mount, case) for case in table}
    records = [payload['record'] for payload in payloads.values() if 'record' in payload]
    assert {record['arm'] for record in records} == set(mount.ARMS) and {case['bench'] for case in table} == set(ORDER)
    assert {record['selection']['status'] for record in records if record['selection']} == set(mount.SELECTION_STATUSES)
    assert {record['unknown_reason'] for record in records if record['routed']} == {
        None, 'unseen_signature', 'distance_above_p95'}
    outcomes = {(c['kind'], c['applied'], c.get('reason')) for c in (r['candidate'] for r in records) if c}
    assert outcomes == {(kind, applied, reason) for kind in ('card', 'program') for applied, reason in (
        (True, None), (False, 'other_type'), (False, 'unseen_signature'), (False, 'distance_above_p95'))}
    refused = sorted(name for name, payload in payloads.items() if 'error' in payload)
    assert refused == sorted(name for name in payloads if name.startswith('refused-'))
    assert all(payloads[name]['requests'] in (None, []) for name in refused if name not in SELECTION_PART)
    assert payloads['refused-forced-id-already-mounted']['requests'] and len(GOLDEN) == len(table)


# ---- mount_identity ------------------------------------------------------------------------------------------
def test_mount_identity_equals_the_fields_of_mount_for_every_arm_and_fixture():
    for case in cases(AxisEmbedder()):
        payload = mount_payload(mount, case)
        if 'record' in payload:
            identity = identity_of(case)
            assert identity == expected_identity(payload['record'], case['kw']['library']), case['name']
            assert tuple(identity) == IDENTITY_KEYS and json.loads(json.dumps(identity)) == identity
        elif case['name'] in SELECTION_PART:
            # the selection part is never run: the identity is the one of any selection reply, here none selected
            record = mount.mount(case['bench'], case['item'], selector=Script(NONE_SELECTED), **case['kw'])
            assert identity_of(case) == expected_identity(record, case['kw']['library']), case['name']
        else:  # an arm that cannot mount has no identity either (same refusal, same order of the checks)
            with pytest.raises(ValueError) as refused:
                identity_of(case)
            assert str(refused.value) == payload['message'], case['name']


def test_mount_identity_makes_no_solver_router_or_embedding_call(monkeypatch):
    embed = AxisEmbedder()
    table = cases(embed)
    embed.calls = 0
    counts = {'router': 0, 'solver': 0, 'judge': 0, 'embedding': 0}

    def counted(kind, original):
        def wrapper(*args, **kwargs):
            counts[kind] += 1
            return original(*args, **kwargs)
        return wrapper
    for name in ('_select', 'selection_request', 'selection_format_retry', 'parse_selection'):
        monkeypatch.setattr(mount, name, counted('router', getattr(mount, name)))
    monkeypatch.setattr(mount, 'solve', counted('solver', mount.solve))
    monkeypatch.setattr(mount.solver, 'solve', counted('solver', mount.solver.solve))
    monkeypatch.setattr(mount.judge, 'judge', counted('judge', mount.judge.judge))
    monkeypatch.setattr(mount.backends, 'score', counted('judge', mount.backends.score))
    monkeypatch.setattr(typing_.TypeMap, 'assign_view', counted('embedding', typing_.TypeMap.assign_view))
    assert not {'selector', 'call', 'embed', 'embedder'} & set(inspect.signature(mount.mount_identity).parameters)
    done, refused = 0, 0
    for case in table:
        try:
            identity_of(case)
            done += 1
        except ValueError:
            refused += 1
    assert counts == {'router': 0, 'solver': 0, 'judge': 0, 'embedding': 0} and embed.calls == 0
    assert done == len([c for c in table if not c['name'].startswith('refused-')]) + len(SELECTION_PART)
    assert refused == len([c for c in table if c['name'].startswith('refused-')]) - len(SELECTION_PART)
    # the counters see the calls: mount() of the same item selects through them
    case = next(c for c in table if c['name'] == 'F-programs-both-selected')
    mount.mount(case['bench'], case['item'], selector=Script(case['replies']), **case['kw'])
    assert counts['router'] > 0


def test_equal_mounts_give_equal_identities_and_each_field_alone_changes_it():
    embed = AxisEmbedder()
    qa = searchqa_items(1)[0]

    def identity(state, arm='F', candidate=None, vector='qa'):
        tm, library, _, vectors = state
        return mount.mount_identity('searchqa', qa, arm=arm, typemap=tm, library=library,
                                    vector=vectors[vector] if isinstance(vector, str) else vector, candidate=candidate)

    def differing(a, b):
        return [key for key in IDENTITY_KEYS if a[key] != b[key]]
    base = world(embed, programs=1)
    tm, library, tid, _ = base
    f = identity(base)
    assert f == {'system_card_sha256': lib.sha256_text(mount.system_card('searchqa', CARD_TEXT)),
                 'programs_offered': [['prog-t01-s1-a', library.get('prog-t01-s1-a')['sha256']]], 'forced': None}
    # equal mounts, equal identities
    assert identity(world(embed, programs=1)) == f  # the same state rebuilt
    assert identity(world(embed, programs=1, merged=True), vector='treasury') == f  # routed through a merged source
    assert identity(base, 'cand_card', {'text': NEW_CARD, 'home_type': 't99'}) == f  # another type mounts as F
    assert identity(base, 'cand_program', {'procedure': program_record('fx-cand-prog'), 'home_type': 't99'}) == f
    assert identity(base, 'cand_card', {'text': CARD_TEXT, 'home_type': tid}) == f  # the incumbent text: same arm
    far = embed(['treasury table z'])[0]
    c0 = mount.mount_identity('searchqa', qa, arm='C0', typemap=None, library=None, vector=None)
    assert c0 == {'system_card_sha256': lib.sha256_text(mount.format_block('searchqa')), 'programs_offered': [],
                  'forced': None}
    assert identity(world(embed, card=False, programs=0)) == c0 == identity(base, vector=far)  # nothing mounted
    assert identity(base, 'cand_program', {'procedure': program_record('fx-cand-prog'), 'home_type': tid},
                    vector=far) == c0
    # the selection reply never enters: four mounts with four selection outcomes, one identity
    two = world(embed, programs=2)
    records = [mount.mount('searchqa', qa, arm='F', typemap=two[0], library=two[1], vector=two[3]['qa'],
                           selector=Script(replies)) for replies in (
        USE_A, NONE_SELECTED, ['{"use": ["snippet-scanner-b", "snippet-scanner-a"], "why": "both"}'],
        ['no json', 'still no json'])]
    assert len({json.dumps(record['selection'], sort_keys=True) for record in records}) == 4
    assert all(expected_identity(record, two[1]) == identity(two) for record in records)
    # each field alone changes the identity
    card = identity(base, 'cand_card', {'text': NEW_CARD, 'home_type': tid})
    assert differing(f, card) == ['system_card_sha256']
    assert card['system_card_sha256'] == lib.sha256_text(mount.system_card('searchqa', NEW_CARD))
    other_body = identity(world(embed, programs=1, program_source=OTHER_SOURCE))  # same skill id, another body
    assert differing(f, other_body) == ['programs_offered']
    assert other_body['programs_offered'][0][0] == f['programs_offered'][0][0]
    assert differing(f, identity(two)) == ['programs_offered']  # one more program offered
    program = identity(base, 'cand_program', {'procedure': program_record('fx-cand-prog'), 'home_type': tid})
    assert differing(f, program) == ['forced'] and program['forced'] == program_record('fx-cand-prog')['record_sha256']
    other_program = identity(base, 'cand_program', {'procedure': program_record('fx-cand-prog', OTHER_SOURCE),
                                                    'home_type': tid})
    assert differing(program, other_program) == ['forced']
    as_object = identity(base, 'cand_program', {'procedure': Procedure.from_json(program_record('fx-cand-prog')),
                                                'home_type': tid})
    assert as_object == program
    assert all(a != b for a, b in ((f, card), (f, other_body), (f, identity(two)), (f, program),
                                   (program, other_program)))


def test_mount_identity_refuses_a_program_candidate_without_its_record_hash():
    """``forced = None`` means "no program forced": an applied candidate without its sealed hash must not look like
    arm F (the package build would refuse such a record anyway, ``Procedure.from_json``)."""
    embed = AxisEmbedder()
    tm, library, tid, vectors = world(embed, programs=0)
    unsealed = {key: value for key, value in program_record('fx-cand-prog').items() if key != 'record_sha256'}
    kw = dict(arm='cand_program', typemap=tm, library=library, vector=vectors['qa'],
              candidate={'procedure': unsealed, 'home_type': tid})
    with pytest.raises(ValueError, match='sealed record'):
        mount.mount_identity('searchqa', searchqa_items(1)[0], **kw)
    # mount itself is unchanged by the split: it records the candidate as given (no hash), the solve refuses it later
    assert mount.mount('searchqa', searchqa_items(1)[0], **kw)['candidate']['sha256'] is None
