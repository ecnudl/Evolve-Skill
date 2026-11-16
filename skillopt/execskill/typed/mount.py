"""The per-item mount of typed-v2 (design §5.5): type assignment -> system card composition -> the solver model's
program selection -> a route-B ``Package`` of the enabled programs -> ``solver.solve`` with an unstarted sandbox
worker -> judge / score (the SpreadsheetBench score context) -> one cell record.

WHY this module exists: route B's cell runner (``cells.run_cell``) needs a protocol unit, an endpoint recorder and the
chain's acceptance machinery; typed-v2 reuses only the shell, the judge/scorers and the sandbox (design §5.4), so the
few lines that glue them for one item live here, outside any route-B unit. Nothing here reads a test panel: items and
their public views are handed in by the caller (practice units, or ``reads.read_panel`` inside a sealed read unit).

Two route-B facts shape ``solve``: (1) the frozen ``backends._response`` turns EVERY exception of the call function
into the unknown reason ``model_call_exception:<Type>``, so a typed ledger stop or a provider balance stop raised
inside a call would be recorded as an unknown cell; ``solve`` keeps the exceptions its call wrapper saw and re-raises
the stops once the shell has closed its worker. (2) the judge's ``deciding_receipt`` indexes the receipts the shell
itself collected, so ``solve`` passes exactly those (never a shared recorder's list that may hold the selection call).
"""
from __future__ import annotations

import json
import re
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path

from skillopt.continual_eval import backends
from skillopt.continual_eval.core import require
from skillopt.execskill import judge, solver, v222_cards, zebralogic
from skillopt.execskill.errors import STOP_KINDS
from skillopt.execskill.package import Package, Procedure, empty
from skillopt.execskill.v225_cards import CARD_JOIN
from skillopt.validator_pilot.api import digest

from . import BASE_CARD_DEFAULT, BASE_CARDS, EVIDENCE, MACHINERY, MOUNT_ARMS, ORDER, ROUTE_B_EVIDENCE
from .library import canonical_sha256, parse_selection, selection_format_retry, selection_request, sha256_text
from .tasktypes import public_text, structural_signature
from .units import MODEL_SIDE_ERRORS, RECEIPT_KEYS, Stop

ARMS = MOUNT_ARMS  # ('F', 'B', 'C0', 'C', 'cand_card', 'cand_program')
ROUTED_ARMS = ('F', 'cand_card', 'cand_program')
# typed-v3 (T9): the key of a package candidate of arm cand_program ({'procedures': [records], 'home_type'}), all its
# records forced together; the one-program shape {'procedure': record, 'home_type'} and its identity are unchanged
PACKAGE_KEY = 'procedures'
BASE_ARM = 'B'  # the learning base (addendum D17): the base card alone, never routed, nothing offered
SELECTION_STATUSES = ('ok', 'parse_failure', 'not_needed', 'none_selected')
SELECTION_ATTEMPTS = 2  # the request and one format retry (design §2)
OUTPUT_EXCERPT_CHARS = 2000
RAW_EXCERPT_CHARS = 300
TRUNCATION_MARK = '…[truncated]'
STEP_LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}')  # package.STEP
MAX_SCORE_POSITIONS = 8
STOPS = tuple(STOP_KINDS) + (Stop,)
# A cell decided by one of these shell reasons is a configuration failure, never a model outcome (arch_probes.p1_cell).
CONFIGURATION_REASONS = ('invalid_prompt_layout', 'invalid_code_extraction_version', 'invalid_public_contract',
                         'invalid_alfworld_trace_version', 'invalid_alfworld_step_budget',
                         'public_input_or_runtime_error:', 'alfworld_environment_error:ValueError',
                         'alfworld_environment_error:FileNotFoundError', 'alfworld_environment_error:ImportError',
                         'alfworld_environment_error:ModuleNotFoundError')


# ---- cards ---------------------------------------------------------------------------------------------------------
def format_block(bench):
    """The fixed answer-format block: arm C0's whole system card and, under the base 'format', the tail of every
    learned one (under 'historical' the tail is the whole card C, which holds every line of this block)."""
    return zebralogic.CARD_TEXT if bench == zebralogic.BENCH else v222_cards.format_text(bench)


def historical_card(bench):
    """Arm C: the whole frozen main-v7 card (ZebraLogic never had one, so its C equals C0)."""
    return format_block(bench) if bench == zebralogic.BENCH else v222_cards.historical_text(bench)


def base_text(bench, base_card=BASE_CARD_DEFAULT):
    """The base of every learned mount of ``bench`` (addendum D17): the format block under 'format', the whole
    historical card C under 'historical' (for ZebraLogic both are its format block)."""
    require(base_card in BASE_CARDS, 'A registered base card %s: %r' % (BASE_CARDS, base_card))
    return historical_card(bench) if base_card == 'historical' else format_block(bench)


def system_card(bench, card_text, *, base_card=BASE_CARD_DEFAULT):
    """The probe-1 'sys' layout: learned card, a blank line, the base (``base_text``: the format block, or the
    historical card C under D17); the base alone without a card. D2's length rules apply to the learned text only."""
    require(type(card_text) is str, 'A card text is text')
    base = base_text(bench, base_card)
    return card_text + CARD_JOIN + base if card_text.strip() else base


def excerpt(text, n=OUTPUT_EXCERPT_CHARS):
    """At most ``n`` characters of a text (a non-text value is rendered as JSON), marked when cut."""
    if text is None:
        return None
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, sort_keys=True)
    if len(text) <= n:
        return text
    return text[:max(0, n - len(TRUNCATION_MARK))] + TRUNCATION_MARK


# ---- packages -----------------------------------------------------------------------------------------------------
def procedure_from_record(record):
    """A route-B ``Procedure`` rebuilt from its sealed record exactly as ``package.load`` does (hash verified)."""
    if isinstance(record, Procedure):
        return record
    require(isinstance(record, dict), 'A procedure record is a sealed mapping')
    return Procedure.from_json(record)  # PackageInvalid unless the record verifies and hashes to itself


def package_for(enabled_records, *, step, evidence):
    """The mount package (design §5.4): the enabled programs by direct construction, or the empty package."""
    require(type(step) is str and STEP_LABEL.fullmatch(step) is not None, 'A package step label: ' + repr(step))
    procedures = tuple(procedure_from_record(record) for record in enabled_records)
    if not procedures:
        return empty(step=step, evidence=evidence)
    return Package(procedures, step, evidence)


def step_label(text):
    """A package step label from free text (unit names carry '/', which the label admits)."""
    cleaned = re.sub(r'[^A-Za-z0-9._:/-]', '-', str(text))[:200]
    require(STEP_LABEL.fullmatch(cleaned) is not None, 'Cannot derive a package step label from ' + repr(text))
    return cleaned


# ---- shell record readers -----------------------------------------------------------------------------------------
def _shell(prediction):
    shell = prediction.get('shell') if isinstance(prediction, dict) else None
    return shell if isinstance(shell, dict) else {}


def fired_ids(prediction):
    """Procedure ids whose ``applies`` fired (True, or the v2.9 default) in the shell's route record."""
    route = _shell(prediction).get('route')
    if not isinstance(route, dict):
        return []
    return [pid for pid, entry in (route.get('per_procedure') or {}).items()
            if entry.get('applies') is True or entry.get('applies') == 'default_true']


def enabled_ids(prediction):
    """Procedure ids the route enabled (fired and not withheld)."""
    route = _shell(prediction).get('route')
    return list(route.get('enabled') or []) if isinstance(route, dict) else []


def faults(prediction):
    """The shell's procedure faults: [{procedure, hook, kind, exc_type, message}]."""
    return [dict(fault) for fault in (_shell(prediction).get('faults') or [])]


# ---- views ---------------------------------------------------------------------------------------------------------
def bench_runtime(bench, runtime):
    """One bench's frozen runtime from the per-bench table (a table without any bench key is taken as the bench's
    own runtime, so callers holding either shape pass it unchanged); None means no runtime."""
    if runtime is None:
        return {}
    require(isinstance(runtime, dict), 'A runtime is a mapping')
    if bench in runtime:
        require(isinstance(runtime[bench], dict), 'A bench runtime is a mapping')
        return runtime[bench]
    require(not set(runtime) & set(ORDER), 'The runtime table has no entry for ' + bench)
    return runtime


def view_of(bench, item, runtime):
    """The routing view of an item (the keys the hooks and ``structural_signature`` see), from its public part."""
    return solver.routing_view(bench, deepcopy(item['public']), runtime=bench_runtime(bench, runtime))


# ---- mount ---------------------------------------------------------------------------------------------------------
def mount(bench, item, *, arm, typemap, library, vector, selector=None, candidate=None, view=None, runtime=None,
          base_card=BASE_CARD_DEFAULT):
    """The mount record of one item (design §1.3 plus arm, card_text, system_card, enabled): C0 mounts the format
    block alone; C the historical card; B (the learning base, addendum D17) the base alone; F assigns the type and
    mounts its active card and the programs the solver model selects; cand_card replaces the card by
    ``candidate['text']``; cand_program adds ``candidate['procedure']`` without offering it (typed-v3, T9: or every
    record of ``candidate['procedures']``, an archive package, in package order). ``view``: the routing
    view when the caller already has it (it embedded its text), else ``view_of(bench, item, runtime)``. An item of a
    routed arm that is unknown (unseen structure or too far from every source) gets neither a card nor a candidate:
    the candidate is recorded as not applied.

    ``base_card`` (the manifest's sealed ``base_card``, addendum D17): every mount of B, F, cand_card and
    cand_program composes on ``base_text(bench, base_card)`` -- a learned text T gives ``T + CARD_JOIN + base``, no
    text (an unknown item, a type without a card, B) the base alone, so under 'historical' such an item sends
    exactly arm C's system text (RP12 / Q23). C0 and C are the read anchors and never depend on it."""
    require(arm in ARMS, 'Unknown mount arm: ' + repr(arm))
    require(base_card in BASE_CARDS, 'A registered base card %s: %r' % (BASE_CARDS, base_card))
    require(isinstance(item, dict) and isinstance(item.get('public'), dict), 'An item carries its public part')
    if view is None:
        view = view_of(bench, item, runtime)
    routed = arm in ROUTED_ARMS
    record = {'arm': arm, 'routed': routed, 'signature': _signature(view, strict=routed), 'type': None,
              'source': None, 'distance': None, 'threshold': None, 'unknown_reason': None, 'card_skill': None,
              'programs_offered': [], 'selection': None, 'programs_enabled': [], 'enabled': [], 'candidate': None}
    if arm == 'C0':
        card_text, system = '', format_block(bench)
    elif arm == 'C':
        card_text = system = historical_card(bench)  # the whole frozen card, never composed with the block again
    elif arm == BASE_ARM:
        card_text, system = '', system_card(bench, '', base_card=base_card)
    else:
        card_text, system = _routed_mount(bench, view, record, typemap=typemap, library=library, vector=vector,
                                          selector=selector, candidate=candidate, arm=arm, base_card=base_card)
    record.update({'card_text': card_text, 'system_card': system, 'system_card_sha256': sha256_text(system)})
    return record


def mount_identity(bench, item, *, arm, typemap, library, vector, candidate=None, view=None, runtime=None,
                   base_card=BASE_CARD_DEFAULT):
    """The mount identity of one item under an arm (design 3.4, "Shared arms"), with no call of any kind (it takes no
    selector, the vector is the caller's): ``{'system_card_sha256', 'programs_offered': [[skill_id, skill sha256],
    ...], 'forced': record sha256 or None}``. It is ``mount`` up to, not including, the selection call: the hash of
    the composed system card, the programs the item's type offers to the selection call (library order, each with its
    skill hash), and the program candidate forced into the package when it applies (its sealed ``record_sha256``,
    which ``mount`` records as ``candidate['sha256']``). The selection reply never enters, so two arms with equal
    identities send their requests from the same distribution. Arguments as ``mount`` without ``selector`` (the same
    ``base_card``: the learned arms compose on the manifest's base); the refusals of ``mount`` before its selection
    call are kept, in the same order."""
    require(arm in ARMS, 'Unknown mount arm: ' + repr(arm))
    require(base_card in BASE_CARDS, 'A registered base card %s: %r' % (BASE_CARDS, base_card))
    require(isinstance(item, dict) and isinstance(item.get('public'), dict), 'An item carries its public part')
    if view is None:
        view = view_of(bench, item, runtime)
    signature = _signature(view, strict=arm in ROUTED_ARMS)
    offered, forced = [], None
    if arm == 'C0':
        system = format_block(bench)
    elif arm == 'C':
        system = historical_card(bench)
    elif arm == BASE_ARM:
        system = system_card(bench, '', base_card=base_card)
    else:
        route = _route({'signature': signature}, typemap=typemap, library=library, vector=vector,
                       candidate=candidate, arm=arm)
        if route is None:  # an item of no type: the base alone (RP12 / Q23), nothing offered, no candidate applied
            system = system_card(bench, '', base_card=base_card)
        else:
            system = system_card(bench, route['card_text'], base_card=base_card)
            offered = [[skill['skill_id'], skill['sha256']] for skill in route['programs']]
            if route['arm'] == 'cand_program' and PACKAGE_KEY in route['candidate']:
                # typed-v3 (T9): a package candidate forces every record; its identity is the list of their hashes
                forced = [record.get('record_sha256') for record in _forced_records(route['candidate'])]
                require(all(type(sha) is str and sha for sha in forced),
                        'A package candidate holds sealed records with their hashes')
            elif route['arm'] == 'cand_program':
                forced = _forced_record(route['candidate']).get('record_sha256')
                # None means "no program forced": an applied candidate must carry its sealed hash
                require(type(forced) is str and forced, 'A program candidate is a sealed record with its hash')
    return {'system_card_sha256': sha256_text(system), 'programs_offered': offered, 'forced': forced}


def _signature(view, *, strict):
    """The structural signature; an unregistered shape is an error only when the arm routes on it."""
    try:
        return structural_signature(view)
    except ValueError:
        if strict:
            raise
        return None


def _route(record, *, typemap, library, vector, candidate, arm):
    """The routing part of a routed arm's mount, up to and not including the selection call; it makes no call of any
    kind (``mount`` and ``mount_identity`` share it). Writes the routing fields of ``record`` (``type``, ``source``,
    ``distance``, ``threshold``, ``unknown_reason``, ``card_skill``, ``candidate``, ``programs_offered``) and returns
    None for an item of no type, else ``{'type', 'card_text', 'programs', 'arm', 'candidate'}`` with the arm and the
    candidate in effect (an item routed to another type than the candidate's home mounts as F)."""
    require(typemap is not None and library is not None, 'A routed arm mounts from the frozen type map and library')
    _check_candidate(arm, candidate)
    signature = record['signature']
    require(vector is not None or not any(typemap.type_of_source(sid) is not None
                                          for sid in typemap.sources_with_signature(signature)),
            'A routed item of a typed structure needs its embedding vector')
    assigned = typemap.assign(signature, vector)
    record.update({key: assigned[key] for key in ('type', 'source', 'distance', 'threshold', 'unknown_reason')})
    tid = assigned['type']
    if tid is None:
        if candidate is not None:
            record['candidate'] = {'kind': 'card' if arm == 'cand_card' else 'program', 'applied': False,
                                   'reason': assigned['unknown_reason']}
        return None
    card = library.active_card(tid)
    programs = library.programs(tid)
    _consistent(typemap, tid, card, programs)
    record['card_skill'] = card['skill_id'] if card is not None else None
    card_text = card['body']['text'] if card is not None else ''
    if candidate is not None and tid != candidate['home_type']:
        # the candidate would be installed into its home type only: an item routed to another type keeps that type's
        # mount (arm F), so the gate measures exactly what acceptance would deploy on the slice
        record['candidate'] = {'kind': 'card' if arm == 'cand_card' else 'program', 'applied': False,
                               'reason': 'other_type', 'home_type': candidate['home_type']}
        arm, candidate = 'F', None
    if arm == 'cand_card':
        card_text = candidate['text']
        record['candidate'] = {'kind': 'card', 'applied': True, 'sha256': sha256_text(card_text),
                               'home_type': candidate['home_type']}
    record['programs_offered'] = [skill['skill_id'] for skill in programs]
    return {'type': tid, 'card_text': card_text, 'programs': programs, 'arm': arm, 'candidate': candidate}


def _routed_mount(bench, view, record, *, typemap, library, vector, selector, candidate, arm, base_card):
    """``_route``, then the selection part: the solver model's selection call when the type offers programs, the
    enabled programs and the forced program candidate. The system card composes on the manifest's base
    (``system_card``): an item of no type gets the base alone (RP12 / Q23: under 'historical' arm C's text)."""
    route = _route(record, typemap=typemap, library=library, vector=vector, candidate=candidate, arm=arm)
    if route is None:
        return '', system_card(bench, '', base_card=base_card)
    tid, programs, arm, candidate = route['type'], route['programs'], route['arm'], route['candidate']
    if programs:
        require(selector is not None, 'A type with programs mounts through the solver model\'s selection call')
        record['selection'], chosen = _select(programs, library, view, selector, tid)
    else:
        record['selection'] = {'use': [], 'why': None, 'status': 'not_needed', 'request_sha256': None,
                               'attempts': [], 'tokens': 0, 'raw_excerpt': None, 'failure': None}
        chosen = []
    record['programs_enabled'] = [skill['skill_id'] for skill in chosen]
    record['enabled'] = [deepcopy(skill['body']['procedure']) for skill in chosen]
    if arm == 'cand_program' and PACKAGE_KEY in candidate:
        # typed-v3 (T9): every record of a package candidate joins the package, in package order
        forced = _forced_records(candidate)
        mounted = {r.get('id') for r in record['enabled']}
        ids = [r.get('id') for r in forced]
        require(len(set(ids)) == len(ids) and not set(ids) & mounted,
                'A package candidate holds records of distinct ids none of which is already mounted')
        record['enabled'].extend(forced)
        record['candidate'] = {'kind': 'program', 'applied': True, 'ids': ids,
                               'sha256': [r.get('record_sha256') for r in forced], 'home_type': candidate['home_type']}
    elif arm == 'cand_program':
        forced = _forced_record(candidate)
        require(isinstance(forced, dict) and forced.get('id') not in {r.get('id') for r in record['enabled']},
                'A candidate program is a record whose id is not already mounted')
        record['enabled'].append(forced)
        record['candidate'] = {'kind': 'program', 'applied': True, 'id': forced.get('id'),
                               'sha256': forced.get('record_sha256'), 'home_type': candidate['home_type']}
    return route['card_text'], system_card(bench, route['card_text'], base_card=base_card)


def _forced_record(candidate):
    """The program candidate's record as it joins the package (a ``Procedure`` becomes its sealed record)."""
    forced = candidate['procedure']
    return forced.to_json() if isinstance(forced, Procedure) else deepcopy(forced)


def _forced_records(candidate):
    """The records of a package candidate (typed-v3, T9: ``{'procedures': [...], 'home_type'}``), in package order."""
    return [record.to_json() if isinstance(record, Procedure) else deepcopy(record)
            for record in candidate[PACKAGE_KEY]]


def _check_candidate(arm, candidate):
    """A candidate names the type it would be installed into (``home_type``): it is applied only to items routed
    to that type (Codex review 11/10: a gate must not credit a candidate on items that keep another type's mount)."""
    if arm == 'F':
        require(candidate is None, 'Arm F mounts the library alone')
        return
    require(isinstance(candidate, dict) and isinstance(candidate.get('home_type'), str) and candidate['home_type'],
            'A candidate names its home type')
    if arm == 'cand_card':
        require(type(candidate.get('text')) is str and candidate['text'].strip(),
                'A card candidate is {"text": nonempty, "home_type": type}')
    elif PACKAGE_KEY in candidate:  # typed-v3 (T9): an archive package, every record enabled together
        records = candidate[PACKAGE_KEY]
        require('procedure' not in candidate and isinstance(records, list) and records
                and all(isinstance(record, (dict, Procedure)) for record in records),
                'A package candidate is {"procedures": [sealed records], "home_type": type}')
    else:
        require(isinstance(candidate.get('procedure'), (dict, Procedure)),
                'A program candidate is {"procedure": sealed record, "home_type": type}')


def _consistent(typemap, tid, card, programs):
    """The frozen type map and the library name the same skills (design §5.7 keeps both in step)."""
    typ = typemap.summary()[tid]
    require(typ['card'] == (card['skill_id'] if card is not None else None),
            'The type map and the library disagree on the active card of ' + tid)
    require(set(typ['programs']) == {skill['skill_id'] for skill in programs},
            'The type map and the library disagree on the programs of ' + tid)


def _select(programs, library, view, selector, tid):
    """One selection call with the type's program index (names + frozen descriptions), one format retry on a parse
    failure; returns the selection record and the chosen skills in library (acceptance) order."""
    index = library.index(home_type=tid, kinds=('program',))
    allowed = {row['name'] for row in index}
    request = selection_request(index, public_text(view))
    attempts, tokens, parsed, failure, raw = [], 0, None, None, None
    for attempt in range(SELECTION_ATTEMPTS):
        receipt = selector(request['system'], request['user'])
        attempts.append(request['request_sha256'])
        tokens += _usage_tokens(receipt)
        reply = receipt.get('response') if isinstance(receipt, dict) and receipt.get('ok') else None
        raw = reply if isinstance(reply, str) else (receipt.get('error_type') if isinstance(receipt, dict) else None)
        try:
            parsed = parse_selection(reply, allowed)
            failure = None
            break
        except ValueError as error:
            failure = str(error)
            request = selection_format_retry(request)
    status = 'parse_failure' if parsed is None else 'ok' if parsed['use'] else 'none_selected'
    use = list(parsed['use']) if parsed is not None else []
    chosen = [skill for skill in programs if skill['name'] in set(use)]
    return ({'use': use, 'why': parsed['why'] if parsed is not None else None, 'status': status,
             'request_sha256': attempts[-1], 'attempts': attempts, 'tokens': tokens,
             'raw_excerpt': excerpt(raw, RAW_EXCERPT_CHARS), 'failure': failure}, chosen)


def _usage_tokens(receipt):
    usage = receipt.get('usage') if isinstance(receipt, dict) else None
    total = usage.get('total_tokens') if isinstance(usage, dict) else None
    return total if type(total) is int and total >= 0 else 0


# ---- solve ---------------------------------------------------------------------------------------------------------
class _Recorded:
    """The call function handed to the shell: the receipts the shell saw (the judge's deciding index counts them),
    a minimal send log, and the exceptions the frozen ``_response`` swallowed."""

    def __init__(self, call):
        self.call, self.receipts, self.sends, self.errors = call, [], [], []

    def __call__(self, system, user):
        record = {'request_sha256': sha256_text(system + '\x00' + user), 'receipt': None}
        self.sends.append(record)
        try:
            receipt = self.call(system, user)
        except BaseException as error:
            record['exception'] = type(error).__name__
            self.errors.append(error)
            raise
        if not isinstance(receipt, dict):  # the recorder's rule (units.CallRecorder): never a non-dict receipt
            receipt = {'ok': False, 'usage': {}, 'error_type': 'invalid_receipt'}
        record['receipt'] = {key: receipt.get(key) for key in RECEIPT_KEYS}
        self.receipts.append(receipt)
        return receipt

    def reraise_stops(self):
        """A ledger stop or a route-B stop raised inside a call must stop the cell, not become an unknown reply."""
        for error in self.errors:
            if isinstance(error, STOPS):
                raise error

    def infrastructure_unknown(self):
        return bool(self.errors) or any(not r.get('ok') and (r.get('error_type') or 'unknown') not in MODEL_SIDE_ERRORS
                                        for r in self.receipts)


def solve(bench, item, mounted, *, call, runtime, worker_factory=None, native=None, nominal_tokens=None, unit, tag,
          scorer_root, mode, step=None, episodes=None):
    """One item through the route-B shell with its mount (design §1.4): the cell record of ``units.run_unit``.

    ``call(system, user) -> receipt``: the cell's recorded call (``units.CallRecorder``; ``.sends``/``.tokens()``
    are used when present); ``runtime``: the frozen per-bench table (or the bench's own runtime); ``worker_factory``:
    zero-arg, returns an UNSTARTED sandbox worker, called only when a program is enabled (``worker=None`` otherwise);
    ``native``: the spreadsheet-native pool (held by the shell around its containers and here around host scoring);
    ``nominal_tokens``: chain D's M for the margin truncation rule; ``unit``/``tag``/``scorer_root``: the scoring
    position and ``<scorer_root>/host_only/scorer_artifacts/<position>``; ``mode``: run | smoke | test, which picks the
    route-B evidence of the package and the typed evidence of the record; ``step``: the package step label (default
    ``typed/<unit>``); ``episodes``: the alfworld-episode pool, held around an ALFWorld episode when given."""
    require(mode in ROUTE_B_EVIDENCE, 'mode is run, smoke or test')
    require(isinstance(mounted, dict) and mounted.get('arm') in ARMS and type(mounted.get('system_card')) is str
            and isinstance(mounted.get('enabled'), list), 'A mount record from mount()')
    require(isinstance(item, dict) and isinstance(item.get('public'), dict) and isinstance(item.get('private'), dict),
            'An item carries its public and private parts')
    require(bench != 'spreadsheetbench' or (unit and tag and scorer_root),
            'SpreadsheetBench scoring needs its unit, cell tag and scorer root before the paid call')
    label = step_label(step if step is not None else 'typed/' + str(unit))
    package = package_for(mounted['enabled'], step=label, evidence=ROUTE_B_EVIDENCE[mode])
    require(not mounted['enabled'] or worker_factory is not None, 'Enabled programs run in a sandbox worker')
    worker = worker_factory() if mounted['enabled'] else None
    bench_rt = deepcopy(bench_runtime(bench, runtime))
    recorded = _Recorded(call)
    row = {'bench': bench, 'item_id': str(item['task_id']), 'arm': mounted['arm'], 'mount': _stored_mount(mounted),
           'public_hash': canonical_sha256(item['public']), 'evidence': EVIDENCE[mode], 'unit': unit, 'tag': tag,
           'step': label, 'package_sha256': package.sha256, 'nominal_tokens': nominal_tokens,
           'system_card_sha256': mounted.get('system_card_sha256') or sha256_text(mounted['system_card'])}
    failure, prediction = None, None
    try:
        with episodes.hold() if episodes is not None and bench == 'alfworld' else nullcontext():
            prediction = solver.solve(bench, deepcopy(item['public']), mounted['system_card'], package, recorded,
                                      runtime=bench_rt, worker=worker, native=native, nominal_tokens=nominal_tokens,
                                      configuration=MACHINERY)
    except STOPS:
        raise
    except Exception as error:
        failure = type(error).__name__
    recorded.reraise_stops()  # after the shell closed its worker
    if failure is None:
        score, score_meta = None, None
        try:
            if bench == 'spreadsheetbench' and prediction.get('status') == 'available':
                score, score_meta = _sheet_score(item, prediction, bench_rt, native=native, unit=unit, tag=tag,
                                                 scorer_root=scorer_root)
            scored = judge.judge(bench, item['public'], item['private'], prediction, recorded.receipts,
                                 runtime=bench_rt, score=score)
        except STOPS:
            raise
        except Exception as error:
            failure = type(error).__name__
    if failure is not None:
        row.update(_failed(prediction, failure))
    else:
        row.update(_judged(bench, prediction, scored, score, score_meta, recorded.receipts))
    row.update(_costs(call, recorded, row['correct']))
    return row


def _failed(prediction, failure):
    """A cell whose shell or judge raised (not a stop): unknown, a configuration failure, never scored as wrong."""
    return {'prediction_status': prediction.get('status') if isinstance(prediction, dict) else None,
            'reason': prediction.get('reason') if isinstance(prediction, dict) else None, 'output_excerpt': None,
            'reply': None, 'output': None, 'correct': None, 'token': None, 'final_token': None, 'official': None,
            'format': {}, 'flags': [], 'carrier': None, 'judge_version': None, 'score': None, 'score_position': None,
            'fired': fired_ids(prediction), 'route_enabled': enabled_ids(prediction), 'faults': faults(prediction),
            'costs': prediction.get('costs') if isinstance(prediction, dict) else None, 'deciding_receipt': None,
            'configuration_error': True, 'failure': failure}


def _judged(bench, prediction, scored, score, score_meta, receipts):
    token = scored['v2']['token']
    correct = None if token.startswith('unknown') else token == 'pass'
    reason = prediction.get('reason')
    reply = _reply(prediction, receipts)
    output = _output_summary(bench, prediction)
    return {'prediction_status': prediction.get('status'), 'reason': reason,
            'output_excerpt': excerpt(reply if reply is not None else output), 'reply': reply, 'output': output,
            'correct': correct, 'token': token, 'final_token': scored['final']['token'], 'official': scored['official'],
            'format': dict(scored['format']), 'flags': list(scored['flags']), 'carrier': scored['carrier'],
            'judge_version': scored['version'], 'score': score, 'score_position': score_meta,
            'fired': fired_ids(prediction), 'route_enabled': enabled_ids(prediction), 'faults': faults(prediction),
            'costs': prediction.get('costs'), 'deciding_receipt': _shell(prediction).get('deciding_receipt'),
            'configuration_error': correct is None and isinstance(reason, str)
            and reason.startswith(CONFIGURATION_REASONS), 'failure': None}


def _costs(call, recorded, correct):
    """Sends and tokens of the cell from the recorder when it keeps them (every send through it, the selection call
    included when the chain hands the same recorder to ``mount``), else from the shell's calls alone."""
    sends = list(call.sends) if isinstance(getattr(call, 'sends', None), list) else list(recorded.sends)
    tokens = call.tokens() if callable(getattr(call, 'tokens', None)) else sum(_usage_tokens(r) for r in recorded.receipts)
    infra = call.infrastructure_unknown() if callable(getattr(call, 'infrastructure_unknown', None)) \
        else recorded.infrastructure_unknown()
    return {'sends': sends, 'request_sha256': [s.get('request_sha256') for s in sends], 'tokens': tokens,
            'infrastructure_unknown': correct is None and bool(infra)}


def _stored_mount(mounted):
    """The mount record kept with the cell: the enabled procedure records shrink to id + hash (the library and the
    candidate files hold the sources; the package hash is stored beside it)."""
    stored = {key: value for key, value in mounted.items() if key != 'enabled'}
    stored['enabled'] = [{'id': r.get('id') if isinstance(r, dict) else None,
                          'record_sha256': r.get('record_sha256') if isinstance(r, dict) else None}
                         for r in mounted['enabled']]
    return stored


def _reply(prediction, receipts):
    """The full reply the prediction was decided on (the deciding receipt's response), else a text output."""
    deciding = _shell(prediction).get('deciding_receipt')
    if type(deciding) is int and 0 <= deciding < len(receipts) and isinstance(receipts[deciding], dict):
        response = receipts[deciding].get('response')
        if isinstance(response, str):
            return response
    output = prediction.get('output')
    return output if isinstance(output, str) else None


def _output_summary(bench, prediction):
    """A compact, serialisable view of a structured output (workbook bytes are never copied into the cell)."""
    output = prediction.get('output')
    if not isinstance(output, dict):
        return None
    if bench == 'spreadsheetbench':
        return {'code': output.get('code'),
                'cases': [{'status': case.get('status'), 'reason': case.get('reason')} if isinstance(case, dict) else None
                          for case in (output.get('cases') or [])]}
    if bench == 'alfworld':
        trace = prediction.get('trace') or []
        last = trace[-1] if trace and isinstance(trace[-1], dict) else {}
        return {'won': output.get('won'), 'steps': output.get('steps'), 'trace_steps': len(trace),
                'last_action': last.get('action'),
                'last_observation': excerpt(last.get('post_observation') or last.get('observation'))}
    return {key: excerpt(value) for key, value in output.items()}


# ---- SpreadsheetBench scoring --------------------------------------------------------------------------------------
def score_context(unit, tag, scorer_root, prediction, *, scoring=0):
    """The host-only score context of ``sheet_numeric_adapter`` (cells._score): a position per scoring request and
    the artifact directory ``<scorer_root>/host_only/scorer_artifacts/<position>``."""
    request = {'benchmark': 'spreadsheetbench', 'unit': unit, 'cell': tag, 'scoring': scoring}
    position = digest(request)
    artifact_dir = Path(scorer_root) / 'host_only' / 'scorer_artifacts' / position
    return {'artifact_dir': str(artifact_dir), 'position': position, 'request': request,
            'prediction_hash': digest(prediction)}


def fresh_score_context(unit, tag, scorer_root, prediction):
    """A position that the write-once scorer accepts: unused, or holding this very prediction's result (reused);
    an interrupted attempt (started without result) or another prediction's result moves to the next index."""
    for scoring in range(MAX_SCORE_POSITIONS):
        context = score_context(unit, tag, scorer_root, prediction, scoring=scoring)
        root = Path(context['artifact_dir'])
        if not root.exists():
            return context
        result = root / 'result.json'
        if result.is_file():
            try:
                binding = json.loads(result.read_text(encoding='utf-8')).get('binding') or {}
            except (OSError, ValueError, AttributeError):
                continue
            if binding.get('prediction_hash') == context['prediction_hash']:
                return context
    raise ValueError('No fresh scoring position left for cell ' + str(tag))


def _sheet_score(item, prediction, bench_rt, *, native, unit, tag, scorer_root):
    """The delivered SpreadsheetBench program scored by the qualified recalculation under the native slot
    (cells._score); a scoring exception becomes an unknown score, never a wrong one."""
    context = fresh_score_context(unit, tag, scorer_root, prediction)
    score_runtime = deepcopy(bench_rt)
    score_runtime['_score_context'] = context
    try:
        with native.hold() if native is not None else nullcontext():
            score = backends.score('spreadsheetbench', item['public'], item['private'], prediction,
                                   runtime=score_runtime)
    except STOPS:
        raise
    except Exception as error:
        score = {'status': 'unknown', 'score': None, 'metrics': {},
                 'reason': 'native_scoring_exception:' + type(error).__name__}
    return score, {'position': context['position'], 'scoring': context['request']['scoring']}
