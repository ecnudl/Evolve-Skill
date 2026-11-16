"""main-v8's pinned instruction decomposition and ordinary routed note procedures.

The five historical cards include inactive LiveMath. Zebra's registered neutral
card is entirely format, so it has no invented content segment. These functions
never read a task pool or call a solver. Measured decomposition is an S0 duty.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

from skillopt.continual_eval.core import require

VERSION = 'instruction-segments-v2-22'
START = 'format_shell_and_routed_P0_v222'
CONFIGURATION = 'main-v8'
FIXTURE = Path(__file__).resolve().parents[2] / 'tests/fixtures/execskill/v222_cards'
FILE_SHA256 = {
    'searchqa.json': 'a2bd6d9d94a6fffc7da0d426af6ed41e5e6c58d76ab2e0d479e27abff5d27ba0',
    'officeqa.json': '6a5d314da6176684b3fa789962d6d156936053dff7d8c4651db80b0787261add',
    'livemath.json': '3355a95ece63605aca277b5ad582d28c9ffb86f9f64df0495dbbef2e6ac94fcf',
    'spreadsheetbench.json': '3df8a7f041c1083fa7e7b965b5ab073ee585e03fd8eff096e1024f2ceca71f69',
    'alfworld.json': 'b5469b60b44cd050aacd40f04bde1ce4ac4f0ee048fbe4d373d6e17f42feec90',
    'manifest.json': 'a0bece4a2e64f8bb5a61d31b16d56e4e27679458c8d92087e5cce06d484ff2bb',
}
BENCHES = ('searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench', 'alfworld')
ARMS = ('B', 'C0', 'C', 'F')
MAX_SEGMENT_CHARS = 1500
MIN_PRACTICE_ITEMS = 18
WHOLE_CARD_FALLBACK = 'whole_card_fallback'
FALLBACK_RUNTIME_KEY = 'v222_whole_card_fallback'
QUANTITY_CUES = ('how many', 'how much', 'quantity', 'amount', 'total', 'sum', 'ratio', 'percent',
                 'percentage', 'million', 'billion', 'dollar', 'rate', 'increase', 'decrease', 'difference')
_CONTEXT = ("isinstance(view.get('question'), str) and bool(view.get('question', '').strip()) and "
            "isinstance(view.get('context'), str) and bool(view.get('context', '').strip()) and "
            "'choices' not in view and 'workbook_preview' not in view and 'admissible_commands' not in view")
QUANTITY_PATTERN = r"\b(?:" + "|".join(re.escape(cue) for cue in QUANTITY_CUES) + r")\b"
_QUANTITY = "bool(re.search(" + repr(QUANTITY_PATTERN) + ", view.get('question', '').lower()))"
# All operands are public task structure. No id, benchmark name, path or answer is visible.
PREDICATES = {
    'evidence_context': '(' + _CONTEXT + ') and not (' + _QUANTITY + ')',
    'quantity_context': '(' + _CONTEXT + ') and (' + _QUANTITY + ')',
    'public_evidence': _CONTEXT,
    'multiple_choice': "isinstance(view.get('question'), str) and isinstance(view.get('choices'), (list, dict)) and bool(view.get('choices'))",
    'workbook_preview': "isinstance(view.get('instruction'), str) and isinstance(view.get('workbook_preview'), (dict, list, str)) and bool(view.get('workbook_preview'))",
    'admissible_commands': "isinstance(view.get('initial_observation'), str) and isinstance(view.get('admissible_commands', view.get('admissible_commands_at_reset')), list)",
}
ENGINEER_SENTENCE = (
    '\nMain-v8 instructions are routed note segments in the package. You may propose a content segment '
    '(fixed text plus a predicate over public task structure) or a computational procedure. Format blocks '
    'are fixed and cannot be edited. Never route by benchmark name, task id, private path, answer or score. '
    'Use before_call to deliver segment text (and alf_before_step for action episodes); emitting the note '
    'is required to count its effect. Segment notes are at most 1500 characters and share unchanged total '
    'note caps. Confirmation and acceptance also enforce the registered cross-benchmark no-harm gate; '
    'harmful cross-firing is narrowed and rechecked or rejected. Coverage must report segments as well as procedures. '
    'Keep the existing JSON change schema: kind=new or revision (with revises for a revision), description, '
    'hooks, max_note_chars<=1500, requests_second_call=false, state_bytes=0, and replay_tests when required. '
    'In the accompanying Python module declare V222_SEGMENT=\'instruction-segments-v2-22\', '
    'SEGMENT_HOME as the home benchmark, SEGMENT_TEXT as the complete fixed text, and SEGMENT_FIELDS as '
    '{\'facts\': [contiguous pieces of SEGMENT_TEXT, each <=200 characters]}. Define applies(view) using only '
    'public structural fields; before_call(view,state) must only return SEGMENT_FIELDS. For action tasks, '
    'also declare alf_before_step and return {\'fields\': SEGMENT_FIELDS, \'discourage\': []}. No new edit kind is needed.\n'
)


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _enabled(configuration):
    from .profiles import is_v222
    require(is_v222(configuration), 'Instruction segments are registered only for main-v8')


def pins():
    """Verify raw files, original-card identity, and an exhaustive lossless line partition."""
    from . import instruction_start
    original = instruction_start.pins()
    loaded = {}
    for name, expected in FILE_SHA256.items():
        raw = (FIXTURE / name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, 'Frozen card decomposition hash differs: ' + name)
        loaded[name] = json.loads(raw)
    manifest = loaded.pop('manifest.json')
    require(manifest['files'] == {k: v for k, v in FILE_SHA256.items() if k != 'manifest.json'},
            'All five historical decomposition files are pinned')
    values = {}
    for name, value in loaded.items():
        bench = value['bench']
        require(name == bench + '.json' and value['historical'] == original[bench]
                and value['source_fixture_sha256'] == instruction_start.FIXTURE_SHA256,
                'A decomposition retains its frozen historical source')
        lines = value['historical']['text'].splitlines(True)
        require(2 <= len(value['segments']) <= 5, 'Each historical card has two to five content segments')
        covered = []
        for part in [value['format'], *value['segments']]:
            text = ''.join(lines[i] for i in part['line_indices'])
            require(text == part['text'] and _sha(text) == part['sha256'] and len(text) == part['chars'],
                    'Every format and content text has its exact source and hash')
            covered.extend(part['line_indices'])
        require(sorted(covered) == list(range(len(lines))), 'Format and segments partition every historical line once')
        for part in value['segments']:
            require(part['max_note_chars'] == MAX_SEGMENT_CHARS and part['predicate']['kind'] in PREDICATES,
                    'A segment has its registered structural predicate and note cap')
        values[bench] = value
    return values


def manifest_pins():
    values = pins()
    from .zebralogic import CARD_TEXT, CARD_SHA256
    return {'version': VERSION, 'start': START, 'files': dict(FILE_SHA256), 'arms': list(ARMS), 'decomposition_arm': 'C_hist',
            'format_sha256': {b: CARD_SHA256 if b == 'zebralogic' else values[b]['format']['sha256'] for b in BENCHES},
            'segments': {b: [] if b == 'zebralogic' else [dict(row) for row in values[b]['segments']] for b in BENCHES},
            'zebralogic': {'format': CARD_TEXT, 'segments': [], 'reason': 'registered neutral card contains format only'},
            'inactive_historical_bench': 'livemath', 'max_segment_chars': MAX_SEGMENT_CHARS,
            'predicate_sources': dict(PREDICATES), 'quantity_cues': list(QUANTITY_CUES),
            'home_predicate_limitation': 'Shared QA structure is split by quantity/scale cues; false-negative home coverage is measured by the decomposition check.',
            'fallback': 'whole historical shell card, no own P0 segments or hygiene, exact main-v7 card request',
            'seed_source_policy_exception': 'Only exact pinned seed source may retain frozen public ALFWorld numbered-command examples.',
            'engineer_instruction': ENGINEER_SENTENCE, 'engineer_instruction_sha256': _sha(ENGINEER_SENTENCE)}


def historical_text(bench):
    require(bench in BENCHES, 'A registered main-v8 benchmark')
    if bench == 'zebralogic':
        from .zebralogic import CARD_TEXT
        return CARD_TEXT
    return pins()[bench]['historical']['text']


def format_text(bench):
    require(bench in BENCHES, 'A registered main-v8 benchmark')
    if bench == 'zebralogic':
        return historical_text(bench)
    return pins()[bench]['format']['text']


def shell_card(bench, *, fallback=()):
    """One pinned shell card; fallback never creates a note or combines cards."""
    require(set(fallback) <= set(BENCHES), 'Fallback names active benchmarks')
    return historical_text(bench) if bench in fallback else format_text(bench)


def fallback_benches(setting, chain):
    from .profiles import configuration_of, is_v225
    _enabled(configuration_of(setting))
    if is_v225(configuration_of(setting)):
        require(not setting.extra.get('v222_fallbacks'), 'Main-v9 has no whole-card fallbacks')
        return ()
    found = setting.extra.get('v222_fallbacks', {}).get(chain, ())
    require(isinstance(found, (list, tuple)) and len(found) == len(set(found))
            and set(found) <= set(BENCHES), 'A chain binds distinct whole-card fallback benches')
    return tuple(found)


def setting_cards(setting, chain):
    fallback = fallback_benches(setting, chain)
    return {bench: shell_card(bench, fallback=fallback) for bench in setting.cards}


def historical_runtime(runtime):
    """Zebra's historical C omits its neutral card; other shells need no change."""
    return {**runtime, FALLBACK_RUNTIME_KEY: True}


def setting_runtime(setting, chain):
    fallback = fallback_benches(setting, chain)
    found = {bench: {key: value for key, value in runtime.items() if key != FALLBACK_RUNTIME_KEY}
             for bench, runtime in setting.runtime.items()}
    return {bench: historical_runtime(runtime) if bench == 'zebralogic' and bench in fallback else runtime
            for bench, runtime in found.items()}


def chunks(text):
    """Lossless source-text chunks; only existing typed fact fields are used."""
    require(isinstance(text, str) and bool(text.strip()), 'A segment contains nonempty text')
    return [text[i:i + 200] for i in range(0, len(text), 200)]


def _source(bench, text, predicate):
    require(bench in BENCHES + ('livemath',) and isinstance(predicate, dict)
            and set(predicate) == {'kind'} and predicate['kind'] in PREDICATES,
            'Segment predicates use registered public task structure only')
    fields = {'facts': chunks(text)}
    return ("import re\n\nV222_SEGMENT = " + repr(VERSION) + "\nSEGMENT_HOME = " + repr(bench)
            + "\nSEGMENT_TEXT = " + repr(text) + "\nSEGMENT_FIELDS = " + repr(fields)
            + "\n\ndef applies(view):\n    return " + PREDICATES[predicate['kind']]
            + "\n\ndef before_call(view, state):\n    return SEGMENT_FIELDS\n"
            + "\ndef alf_before_step(view, state):\n    return {'fields': SEGMENT_FIELDS, 'discourage': []}\n")


def pinned_seed_source(source):
    """An exact immutable seed source, never an exemption for a changed/learned source."""
    return any(source == _source(bench, row['text'], row['predicate'])
               for bench, value in pins().items() for row in value['segments'])


def segment_metadata(procedure):
    from .policy import POLICY_VERSION_V222
    if getattr(procedure, 'policy_version', None) != POLICY_VERSION_V222:
        return None
    try:
        constants = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(procedure.source).body
                     if isinstance(node, ast.Assign) and len(node.targets) == 1
                     and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('V222_SEGMENT', 'SEGMENT_HOME', 'SEGMENT_TEXT')}
    except (SyntaxError, ValueError, TypeError):
        return None
    if constants.get('V222_SEGMENT') != VERSION or constants.get('SEGMENT_HOME') != procedure.origin:
        return None
    text = constants.get('SEGMENT_TEXT')
    if not isinstance(text, str) or not text.strip():
        return None
    return {'kind': 'instruction_segment', 'home': procedure.origin, 'text_sha256': _sha(text),
            'text_chars': len(text), 'seeded': pinned_seed_source(procedure.source)}


def is_segment(procedure):
    return segment_metadata(procedure) is not None


def make_segment(bench, text, predicate, *, evidence, ordinal=1, step=0, configuration=CONFIGURATION):
    """Build an ordinary note procedure; policy identity is the persistent main-v8 gate."""
    _enabled(configuration)
    from .package import Procedure
    from .policy import POLICY_VERSION_V222
    from . import notes
    require(not any(marker in text.lower() for marker in notes.CHANNEL_MARKERS_V29),
            'Segment content passes the unchanged note safety screen')
    fields, dropped = notes.screen({'facts': chunks(text)}, bench=bench, outcome_judged=True, audited=True)
    require(not notes.fault_drops(dropped, outcome_judged=True), 'Segment content passes the unchanged note safety screen')
    rendered = notes.render(fields, bench=bench, header='')
    require(len(rendered) <= MAX_SEGMENT_CHARS, 'segment_exceeds_unchanged_note_cap')
    return Procedure(id=f'p-{bench}-{step}-{ordinal}', origin=bench, description='Routed instruction content segment',
        hooks=('applies', 'before_call', 'alf_before_step'), source=_source(bench, text, predicate),
        evidence=evidence, max_note_chars=MAX_SEGMENT_CHARS, policy_version=POLICY_VERSION_V222)


def content_text(bench):
    if bench == 'zebralogic':
        return ''
    value = pins()[bench]
    lines = value['historical']['text'].splitlines(True)
    indices = sorted(i for row in value['segments'] for i in row['line_indices'])
    return ''.join(lines[i] for i in indices)


def initial_package(*, evidence, step='root', fallback=(), configuration=CONFIGURATION):
    _enabled(configuration)
    from .profiles import is_v225
    if is_v225(configuration):
        from .package import empty
        require(not fallback, 'Main-v9 has no P0 or fallback')
        return empty(step=step, evidence=evidence)
    from .package import Package
    require(set(fallback) <= set(BENCHES), 'Fallback names active benchmarks')
    values, procedures = pins(), []
    for bench in BENCHES:
        if bench == 'zebralogic' or bench in fallback:
            continue
        rows = values[bench]['segments']
        for n, row in enumerate(rows, 1):
            procedures.append(make_segment(bench, row['text'], row['predicate'], evidence=evidence, ordinal=n,
                                          configuration=configuration))
    # Shared QA structures may match another seed predicate. Whole-card C must
    # still have exactly the legacy empty-package request on its fallback bench.
    narrowed = {proc.id: list(fallback) for proc in procedures} if fallback else {}
    return Package(tuple(procedures), step, evidence, narrowed=narrowed)


def own_segments(package, bench):
    return tuple(procedure for procedure in package.procedures if procedure.origin == bench and is_segment(procedure))


def arm_definition(bench, arm, *, package=None, evidence='engineering_fixture', fallback=(),
                   decomposition=False, root_step='root', initial=None, configuration=CONFIGURATION):
    _enabled(configuration)
    from .package import empty
    require(arm in ARMS or arm == 'C_hist' and decomposition, 'C_hist belongs only to the decomposition check')
    blank = empty(step='root', evidence=evidence)
    if arm == 'B':
        return {'kind': 'blank', 'card': '', 'package': blank}
    if arm == 'C_hist':
        return {'kind': 'historical_card_decomposition', 'card': historical_text(bench), 'package': blank}
    if arm == 'C0':
        return {'kind': 'format_only', 'card': shell_card(bench, fallback=fallback), 'package': blank}
    if arm == 'C':
        package = initial if initial is not None else initial_package(
            evidence=evidence, step=root_step, fallback=fallback, configuration=configuration)
    require(package is not None, 'F requires its learned package')
    return {'kind': 'card' if arm == 'C' else 'package', 'card': shell_card(bench, fallback=fallback), 'package': package}


def decomposition_decision(bench, historical, segmented, *, registered_count=None):
    """Paired practice aggregates: noninferior accuracy and every registered format counter."""
    from fractions import Fraction
    from .outcomes_ext import TOKENS
    require(bench in BENCHES, 'A registered decomposition benchmark')
    expected = historical['items'] if registered_count is None else registered_count
    require(type(expected) is int and MIN_PRACTICE_ITEMS <= expected <= (20 if bench == 'alfworld' else 100),
            'Decomposition uses at least 18 available practice items within its registered cap')
    require(historical['items'] == segmented['items'] == expected, 'Decomposition uses its registered practice slice')
    counter = {'searchqa': 'tag_present', 'officeqa': 'single_number', 'zebralogic': 'program_delivered',
               'spreadsheetbench': 'program_delivered', 'alfworld': 'action_violations'}[bench]
    for aggregate in (historical, segmented):
        require(all(type(aggregate.get(key)) is int and 0 <= aggregate[key] <= expected
                    for key in ('passed', 'observed_passed', 'unknown'))
                and aggregate.get('scoring_side') == 'H'
                and aggregate['passed'] == aggregate['observed_passed'] + aggregate['unknown'],
                'Both decomposition card arms use H with separate observed and unknown counts')
        unknown = aggregate.get('unknown_by_token')
        require(isinstance(unknown, dict) and set(unknown) <= {token for token in TOKENS if token.startswith('unknown')}
                and all(type(count) is int and count > 0 for count in unknown.values())
                and sum(unknown.values()) == aggregate['unknown'], 'Decomposition unknown counts match their tokens')
        require(all(isinstance(aggregate.get(key), dict) and set(aggregate[key]) == {counter}
                    and type(aggregate[key][counter]) is int and 0 <= aggregate[key][counter] <= expected
                    for key in ('format', 'format_applicable', 'format_not_applicable'))
                and aggregate['format_applicable'][counter] + aggregate['format_not_applicable'][counter] == expected
                and aggregate['format'][counter] <= aggregate['format_applicable'][counter],
                'Decomposition format counts partition applicable and not-applicable observations')
    before, after = historical['format'][counter], segmented['format'][counter]
    before_n, after_n = historical['format_applicable'][counter], segmented['format_applicable'][counter]
    before_rate = Fraction(before, before_n) if before_n else None
    after_rate = Fraction(after, after_n) if after_n else None
    compared = before_rate is not None and after_rate is not None
    good_format = ((after_rate <= before_rate if counter == 'action_violations' else after_rate >= before_rate)
                   if compared else None)
    gain = (segmented['passed'] - historical['passed']) / expected
    accepted = gain >= -0.01 and good_format is not False
    return {'bench': bench, 'items': expected, 'whole_slice_gain': gain, 'whole_slice_floor': -0.01,
            'format_counter': counter, 'historical_format': before, 'segmented_format': after,
            'historical_format_applicable': before_n, 'segmented_format_applicable': after_n,
            'historical_format_rate': float(before_rate) if before_rate is not None else None,
            'segmented_format_rate': float(after_rate) if after_rate is not None else None,
            'format_not_applicable': {'C_hist': historical['format_not_applicable'][counter],
                                      'C': segmented['format_not_applicable'][counter]},
            'format_compared': compared, 'format_not_worse': good_format,
            'unknown': {'C_hist': historical['unknown'], 'C': segmented['unknown']},
            'scoring_sides': {'C_hist': 'H', 'C': 'H'},
            'decision': 'accept_split' if accepted else WHOLE_CARD_FALLBACK,
            'hygiene_enabled': accepted and bench != 'alfworld',
            'shell_card_sha256': _sha(format_text(bench) if accepted else historical_text(bench)),
            'fallback_additional_model_cells': 0,
            'historical': historical, 'segmented': segmented}


def decomposition_identity(bench, pairs, *, registered_count=None):
    """A zero-call decomposition pass is permitted only by complete fault-free request identities."""
    from . import reuse
    require(bench in BENCHES and bench != 'alfworld', 'Episode decompositions require measured trajectories')
    count = len(pairs) if registered_count is None else registered_count
    require(type(count) is int and MIN_PRACTICE_ITEMS <= count <= 100 and len(pairs) == count,
            'A decomposition identity covers its entire registered available-count practice slice')
    require(all(set(pair) == {'C_hist', 'C'} for pair in pairs.values()), 'Both decomposition requests are identified')
    identical = all(reuse.interchangeable(pair['C_hist'], pair['C'], bench=bench) for pair in pairs.values())
    return {'bench': bench, 'items': len(pairs), 'identity_proven': identical,
            'model_calls': 0, 'decision': 'accept_identity' if identical else 'measurement_required',
            'whole_slice_gain': 0.0 if identical else None,
            'format_not_worse': True if identical else None}


def decomposition_slices(pools, *, seed='execskill-v2-22-card-decomposition'):
    """Seeded ids only from the already-registered practice-side pools supplied by the caller."""
    require(set(pools) == set(BENCHES), 'Decomposition is registered on all five practice pools')
    output = {}
    for bench in BENCHES:
        items = list(pools[bench])
        require(len(items) == len(set(items)) and all(isinstance(key, str) and key for key in items)
                and len(items) >= MIN_PRACTICE_ITEMS,
                'v222_practice_supply_below_18: decomposition needs at least 18 distinct available practice items')
        count = min(20 if bench == 'alfworld' else 100, len(items))
        chosen = sorted(items, key=lambda key: _sha(json.dumps([seed, bench, key], ensure_ascii=False)))[:count]
        output[bench] = {'items': chosen, 'count': count, 'seed': seed, 'side': 'practice',
                         'arms': ['C_hist', 'C']}
    return output


def segment_violation(procedure):
    """Validate explicitly declared learned segments without changing computational procedures."""
    from .policy import POLICY_VERSION_V222
    if procedure.policy_version != POLICY_VERSION_V222:
        return None
    tree = ast.parse(procedure.source)
    declared = any(isinstance(node, ast.Name) and node.id == 'V222_SEGMENT' for node in ast.walk(tree))
    if not declared:
        return None
    metadata = segment_metadata(procedure)
    if metadata is None:
        return 'A declared instruction segment has valid identity, home and fixed text'
    if not 0 < procedure.max_note_chars <= MAX_SEGMENT_CHARS:
        return 'An instruction segment max_note_chars is at most 1500'
    try:
        constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                     if isinstance(node, ast.Assign) and len(node.targets) == 1
                     and isinstance(node.targets[0], ast.Name)
                     and node.targets[0].id in ('SEGMENT_TEXT', 'SEGMENT_FIELDS')}
    except (ValueError, TypeError):
        return 'Segment text and fields are fixed literals'
    fields, text = constants.get('SEGMENT_FIELDS'), constants.get('SEGMENT_TEXT')
    if not (isinstance(fields, dict) and set(fields) == {'facts'} and isinstance(fields['facts'], list)
            and all(isinstance(part, str) and len(part) <= 200 for part in fields['facts'])
            and ''.join(fields['facts']) == text):
        return 'Segment fixed fields preserve the complete text in capped chunks'
    from . import notes
    if any(marker in text.lower() for marker in notes.CHANNEL_MARKERS_V29):
        return 'Segment content passes the unchanged note safety screen'
    kept, dropped = notes.screen(fields, bench=procedure.origin, outcome_judged=True, audited=True)
    if notes.fault_drops(dropped, outcome_judged=True) or len(notes.render(kept, bench=procedure.origin, header=procedure.header)) > procedure.max_note_chars:
        return 'Complete segment delivery fits the declared unchanged note cap'
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    before, predicate = functions.get('before_call'), functions.get('applies')
    if not (before and predicate and len(before.body) == 1 and isinstance(before.body[0], ast.Return)
            and isinstance(before.body[0].value, ast.Name) and before.body[0].value.id == 'SEGMENT_FIELDS'
            and 'before_call' in procedure.hooks and 'applies' in procedure.hooks):
        return 'A segment delivers its fixed fields with before_call and declares a structural applies predicate'
    forbidden = {'bench', 'benchmark', 'id', 'task_id', 'game_file', 'path', 'answer', 'answers', 'label', 'score'}
    if any(isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.lower() in forbidden
           for node in ast.walk(predicate)):
        return 'Segment predicates use public structure rather than benchmark, identity, private data or outcomes'
    if 'alf_before_step' in procedure.hooks:
        alf = functions.get('alf_before_step')
        expected = ast.parse("def alf_before_step(view, state):\n    return {'fields': SEGMENT_FIELDS, 'discourage': []}\n").body[0]
        if alf is None or ast.dump(alf, include_attributes=False) != ast.dump(expected, include_attributes=False):
            return 'An action segment delivers the same fixed fields through alf_before_step'
    return None
