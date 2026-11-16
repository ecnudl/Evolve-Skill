"""Readout of a typed-v2 run (design §5.9): what the chain did (closed mode) and, once the owner opens the sealed
test reads, the 5x5 tables, paired contrasts, same-request noise and continual-learning metrics (open mode).

Data boundary (design §3). Closed mode reads only open files under ``<root>/<chain>/``: ``state.json``,
``ledger.json``, ``confirm.json``, ``s<k>/noise.json``, ``s<k>/decisions.json``, ``s<k>/library.json``,
``s<k>/typemap.json``, the learning units' ``cells/`` and ``done.json`` under ``s<k>/`` and the open mirrors
``read-status/<event>-<bench>.json`` (counts only). It never opens a sealed read unit (a directory whose name carries
``test-read``): every file goes through ``units.read_json`` with ``allow_sealed=False``, and the mirrors are copied
without any key that names a pass, a failure or an accuracy. Open mode (``open_sealed=True``, the owner's opening)
adds the cells of the read units (``test-read-<event>-<bench>``; ``practice-read-...`` in a smoke) and keeps from every
sealed cell only outcome tokens, counters, hashes and the mount record, never a reply, an excerpt or a prediction.

Scoring conventions (route B ``readout._accuracy``): a cell's ``correct`` is True/False/None; None is an unknown judge
token and is never scored as wrong. Accuracies are reported on side L (unknown = wrong), side H (unknown = right)
and over the known cells only, with the unknown counts beside them. Paired contrasts use ``gates.paired_statistics``
on the complete cases (both cells known, ``excluded_unknown`` counted), in points.

Continual-learning metrics per bench b (k_b = the step that evolved b = its position in ORDER; S0 := C0 in the
typed-v1 functions of a ``full`` root; an economy root takes S0 := the start of learning, see below), on the
items common to every event of that panel, for each side L and H:
  final                 = acc(S5)
  gain_over_C0          = acc(S5) - acc(C0);  gain_over_C = acc(S5) - acc(C)
  forgetting            = max_{1 <= k < 5} acc(S_k) - acc(S5)          (signed, no floor: design §5.9)
  forgetting_after_home = max_{k_b <= k < 5} acc(S_k) - acc(S5)        (the vendored cl_metrics FGT, signed)
  backward_transfer     = acc(S5) - acc(S_{k_b})        for k_b < 5; None at the last step (no later step exists)
  forward_transfer      = acc(S_{k_b-1}) - acc(C0)      for k_b >= 2; None at k_b = 1 (S0 is C0)
  plasticity            = acc(S_{k_b}) - acc(S_{k_b-1})
Macro values are equal-weight means over the benches where the per-bench value is defined, as in
``tests/fixtures/execskill/v225_cl_metrics_reference.py`` (ACC, dACC, BWT over t < K, FGT, FWT over t >= 2, PG).
``latest`` repeats the block with the last available S<k> in place of S5 for an unfinished chain, labelled as such.

typed-v3 (CHAIN-DECISIONS T2): a chain whose state records ``read_anchors`` ['C'] did not read C0 (the format block
alone). Its open document has rows C, S1..S5 only, the contrasts S<k> - C and S<k> - S<k-1>, a 5x5 with both of them
(``diff_points_vs_C``, ``diff_points_vs_previous``; S0 := C) in place of S<k> - C0, and the metrics above with
S0 := C: the C0 level, gain_over_C0 and the same-request noise (C vs C0) are dropped (``C0_DEPENDENT``); a read unit
of C0 in such a chain is refused. Every other chain's document is exactly as before.

typed-v3 steps (CHAIN-DECISIONS T3 to T9; brief P3b C): a step whose ``decisions.json`` carries the item block, the
gate rule or the program learning gets ``typed_v3`` in its entry (``typed_v3_step``, counts from that file alone): the
item stage (counts by side and class, J's counts, the plans, both checks), the step's rules (the card rule used: on E =
R + A, or on J = R where no item was made; the screen items), every candidate's evolution block, screen record, gains
by item class and B's parity, the repair history of the programs, and the archive package's own gate decision apart
from the step's later candidates, with the statement that the archive's test readings were known when its rule was set
(T9). The markdown adds the same per step. A typed-v2 style step's entry is unchanged.

Nothing here selects or recommends a configuration: every acceptance was decided by the practice-side gates
(design §2), the test numbers are generalization evidence only, and the markdown says so.

Economy read plan (spec/read-plan.md 1.F, R63 to R74, R89, R90; addendum D10 d, RP3 to RP7). A chain whose state
says ``read_plan.mode == 'economy'`` reads every class of equal requests once, by its representative; every other
member is an ALIAS. The readout then resolves every (event, bench) from the state, checked against the bound plan
and the verified alias records (``_resolve``), loads FRESH units only under their own event, and marks every alias
cell with its representative (``=X``, the representative's reading shown again, and its unknown / infrastructure /
configuration counts). A contrast inside one class is ``-`` (JSON null), never a measured 0.0; a contrast that is
not same-phase (R89) is a reference value only; continual-learning terms inside one class are structural zeros, the
maxima follow RP4, and every macro has two pre-registered columns. Every typed-v1 function above is unchanged and
still renders a ``full`` root exactly as before; the economy functions live in their own section below.

Economy continual-learning terms (fix-c): S0 := the start of learning, ``BASE_EVENTS[base_card]`` (C under base
'historical', addendum D17; C0 under 'format'), so forward_transfer = acc(S_{k_b-1}) - acc(S0) and the plasticity of
k_b = 1 = acc(S1) - acc(S0) never carry the hand card's own gain over C0 (gain_over_C0 and gain_over_C keep both
rows). A term between two same-phase fresh units whose requests are identical on every item is a noise sample, not
an effect (R67): by construction 0 like a structural term, never in a maximum, counted apart in the macros. A
maximum with an earlier event that has no reading (pending, invalid, void_alias) is ``incomplete``, never a value.
"""
from __future__ import annotations

import os
import re
import time
from collections import Counter
from pathlib import Path

from skillopt.continual_eval.core import require

from . import CHAINS, ORDER, READ_ARMS, VERSION
from . import gates, units
from . import readplan as rp
from .library import Library
from .tasktypes import TypeMap, source_id

READOUT_VERSION = VERSION + '-readout-v1'
READ_PREFIXES = ('test-read-', 'practice-read-')
STEP_EVENTS = tuple(event for event in READ_ARMS if event.startswith('S'))
SIDES = ('L', 'H')
# Keys an open mirror must never carry into a closed readout (counts only, never pass/fail): substrings, plus the
# exact names below (so an unknown kind such as 'failure:ValueError' keeps its count).
CLOSED_BLOCKED = ('pass', 'correct', 'accuracy')
CLOSED_BLOCKED_EXACT = ('fail', 'failed', 'fails', 'wrong', 'acc')
# Keys whose values are text of a request or a reply; a projected cell or a copied record drops them.
TEXT_KEYS = ('response', 'reply', 'system', 'user', 'text', 'prompt', 'output', 'excerpt', 'prediction', 'body',
             'sends', 'card_text', 'system_card')
MOUNT_KEYS = ('type', 'unknown_reason', 'card_skill', 'programs_enabled')
NOISE_KEYS = ('rule', 'n', 'excluded_unknown', 'flip_rate', 'mean_points', 'se_points', 'tau_points')  # read-side noise
# the learning step's calibration (DESIGN 3.4: R runs of the learning base B per gate item, ``gates.calibration``)
GATE_NOISE_KEYS = ('rule', 'repeats', 'n', 'mixed_items', 'se_points', 'tau_points', 'unknown_final', 'reruns')
LEDGER_KEYS = ('cap', 'charged', 'reported', 'sends', 'missing_usage', 'stopped', 'stop_reason', 'infra_streak')
METRIC_KEYS = ('final', 'C0', 'C', 'gain_over_C0', 'gain_over_C', 'forgetting', 'forgetting_after_home',
               'backward_transfer', 'forward_transfer', 'plasticity')
# typed-v3 T2 (read_anchors C, a 'full' root): C0 is not read. Dropped: the C0 level, gain_over_C0 and the same-request
# noise (C vs C0); S0 := C, the start of learning under the base 'historical' that C alone requires, so
# forward_transfer = acc(S_{k_b-1}) - acc(C) and the plasticity of k_b = 1 = acc(S1) - acc(C).
C0_DEPENDENT = ('C0', 'gain_over_C0', 'same_request_noise')
C_METRIC_KEYS = tuple(key for key in METRIC_KEYS if key not in C0_DEPENDENT)
# Addendum D17 "Reporting" (fix-b, review F2): the sealed base card of the run (the chain state keeps the manifest's
# ``base_card``), what the learned arms compose on, and the row that is the start of learning.
BASE_EVENTS = {'historical': 'C', 'format': 'C0'}
BASE_CARD_LINES = {
    'historical': ('every learned arm S1..S5 composes on the historical card C: a learned card is added to C, and a '
                   'bench whose type learned nothing reads exactly C. The C row is the start of learning, not learned '
                   'gain (C\'s own gain over C0 belongs to the hand-written card): typed-v2 starts from C, while the '
                   'v2.24 SkillOpt / GEPA baselines started from an empty skill (and were read on 2026-11-07/08: '
                   'cross-run, cross-date).'),
    'format': 'every learned arm S1..S5 composes on the format lines of C, which are C0; C is a reference row only.',
}
DISCLAIMER = (
    'Every acceptance in this run was decided by the practice-side gates (design §2: same-request noise threshold, '
    'card/program/no-harm decisions on practice slices). Nothing in this readout picks or recommends a configuration, '
    'and no test number fed back into learning. Test-panel numbers are generalization evidence only. Unknown '
    'outcomes are never scored as wrong: side L counts them as wrong and side H as right only to bound the accuracy, '
    'paired contrasts exclude them, and their counts are listed.')


# ---- files -------------------------------------------------------------------------------------------------------
def _read(path, *, allow_sealed=False):
    """A JSON file through the sealed-path guard, or None when absent (a readout tolerates an unfinished chain)."""
    path = Path(path)
    if not path.exists():
        return None
    return units.read_json(path, allow_sealed=allow_sealed)


def _counter(values):
    """{str(key): count} sorted by key; keys are stringified so sorted JSON output never compares None with str."""
    return {str(key): count for key, count in sorted(Counter(values).items(), key=lambda row: str(row[0]))}


def _scrub(value, blocked=TEXT_KEYS, exact=()):
    """A deep copy without any key that names text (a reply, a request) or, for mirrors, a pass/fail count."""
    if isinstance(value, dict):
        return {key: _scrub(inner, blocked, exact) for key, inner in value.items()
                if not any(word in str(key).lower() for word in blocked) and str(key).lower() not in exact}
    if isinstance(value, list):
        return [_scrub(inner, blocked, exact) for inner in value]
    return value


def chains_of(root):
    return [chain for chain in CHAINS if (Path(root) / chain).is_dir()]


def _anchors_of(state):
    """typed-v3 T2: the chain's read anchors from its state (``read_anchors``, written only for C alone); typed-v2's
    C0 and C for every other state. A value that is not registered is refused (the readout never guesses a plan)."""
    found = state.get('read_anchors') if isinstance(state, dict) else None
    return rp.READ_ANCHORS_DEFAULT if found is None else rp.anchor_tuple(found)


def _step_dirs(chain_dir):
    found = {}
    for path in sorted(chain_dir.glob('s[0-9]*')):
        if path.is_dir() and re.fullmatch(r's(\d+)', path.name):
            found[int(path.name[1:])] = path
    return found


def parse_read_name(name):
    """('C0', 'searchqa') from 'test-read-C0-searchqa' or 'practice-read-S3-alfworld'; None for any other name."""
    for prefix in READ_PREFIXES:
        if name.startswith(prefix):
            rest = name[len(prefix):]
            for event in sorted(READ_ARMS, key=len, reverse=True):
                if rest.startswith(event + '-') and rest[len(event) + 1:] in ORDER:
                    return event, rest[len(event) + 1:]
    return None


def _mirror_name(stem):
    for event in sorted(READ_ARMS, key=len, reverse=True):
        if stem.startswith(event + '-') and stem[len(event) + 1:] in ORDER:
            return event, stem[len(event) + 1:]
    return None


# ---- closed-mode pieces ----------------------------------------------------------------------------------------
def _ledger_totals(state):
    if state is None:
        return None
    return {**{key: state.get(key) for key in LEDGER_KEYS}, 'pending': len(state.get('pending') or {}),
            'recovered': len(state.get('recovered') or [])}


def _is_read_unit_name(name):
    return any(prefix in str(name) for prefix in READ_PREFIXES)


def _costs(state):
    """Tokens per unit and per chain from the ledger (reported = provider usage; charged keeps bounds when missing)."""
    if state is None:
        return None
    by_unit = {str(unit): dict(row) for unit, row in (state.get('by_unit') or {}).items()}
    reads = {unit: row for unit, row in by_unit.items() if _is_read_unit_name(unit)}
    learning = {unit: row for unit, row in by_unit.items() if unit not in reads}
    total = lambda rows, key: sum(int(row.get(key) or 0) for row in rows.values())
    return {'chain_charged': state.get('charged'), 'chain_reported': state.get('reported'), 'by_unit': by_unit,
            'read_units': {'count': len(reads), 'charged': total(reads, 'charged'), 'reported': total(reads, 'reported')},
            'learning_units': {'count': len(learning), 'charged': total(learning, 'charged'),
                               'reported': total(learning, 'reported')}}


def _noise(step_dir):
    """The step's gate calibration (``s<k>/noise/noise.json``): the keys of ``GATE_NOISE_KEYS``."""
    for candidate in (step_dir / 'noise.json', step_dir / 'noise' / 'noise.json', step_dir / 'noise' / 'threshold.json'):
        found = _read(candidate)
        if isinstance(found, dict) and 'tau_points' in found:
            return {key: found.get(key) for key in GATE_NOISE_KEYS}
    return None


def _flatten_decisions(value, label=''):
    """Every nested dict with a 'kind' and an 'accepted'/'merge' key is one gate decision; the rest is walked."""
    if isinstance(value, dict):
        if 'kind' in value and ('accepted' in value or 'merge' in value):
            yield label, value
            return
        for key, inner in value.items():
            yield from _flatten_decisions(inner, label + '/' + str(key) if label else str(key))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            yield from _flatten_decisions(inner, '%s[%d]' % (label, index))


def _decision_row(label, decision):
    """One gate decision (DESIGN 3.4: item means of R runs per arm) with its denominators (n items, R, fired items,
    model-side unknown runs) and the tau and SE it was held to (its own baseline's repeats); a program row shows the
    deciding gain on its fired items beside the whole-slice gain, and where the baseline runs come from."""
    kind = decision.get('kind')
    program = kind == 'program'
    pick = lambda key: decision.get(key + '_fired') if program else decision.get(key)
    baseline = decision.get('baseline') if isinstance(decision.get('baseline'), dict) else {}
    row = {'label': label, 'kind': kind, 'accepted': decision.get('accepted', decision.get('merge')),
           'reason': decision.get('reason'), 'tau_points': decision.get('tau_points'), 'n': decision.get('n'),
           'repeats': decision.get('repeats'), 'se_points': decision.get('se_points'),
           'excluded_unknown': decision.get('excluded_unknown'), 'unknown_final': decision.get('unknown_final'),
           'mean_points': decision.get('gain_points_fired') if program else decision.get('gain_points'),
           'better': pick('better'), 'worse': pick('worse'), 'tied': pick('tied'),
           'baseline': (baseline.get('shared_from') or {}).get('unit') or baseline.get('unit'),
           'baseline_selected': decision.get('baseline_selected')}
    if program:
        row.update(fired_n=decision.get('fired_items'), whole_slice_mean_points=decision.get('gain_points'),
                   se_points_fired=decision.get('se_points_fired'), se_points_scaled=decision.get('se_points_scaled'))
    if 'shared_with' in decision:  # addendum D16 (c): a shared type's member checks, the "related gain"
        shared_with = [member for member in decision.get('shared_with') or [] if isinstance(member, dict)]
        # RP15: each member is a source member or a routed member, with its gate items routed into the home type
        scope = {member.get('bench'): {'member': member.get('member'), 'routed_gate_items': member.get('routed_gate_items')}
                 for member in shared_with}
        row.update(shared_with=[member.get('bench') for member in shared_with], membership=scope,
                   member_harm=decision.get('member_harm'),
                   related=[_related_row(member, scope.get(member.get('bench')))
                            for member in decision.get('members') or []])
    return row


def _related_row(member, scope=None):
    """One member check of a shared type (addendum D16 c): the candidate's gain on that member bench's gate slice
    (the "related gain"), its counts, the tau it was held to (its own baseline's repeats) and no_regress, the only
    part of it that decides, and (RP15, ``scope``) whether the bench is a source or a routed member and how many of
    its gate items route into the home type. Informational beyond no_regress."""
    baseline = member.get('baseline') if isinstance(member.get('baseline'), dict) else {}
    scope = scope or {}
    return {'bench': member.get('bench'), 'source': member.get('source'), 'member': scope.get('member'),
            'routed_gate_items': scope.get('routed_gate_items'), 'n': member.get('n'),
            'repeats': member.get('repeats'), 'gain_points': member.get('gain_points'),
            'se_points': member.get('se_points'), 'tau_points': member.get('tau_points'),
            'better': member.get('better'), 'worse': member.get('worse'), 'tied': member.get('tied'),
            'unknown_final': member.get('unknown_final'), 'no_regress': member.get('no_regress'),
            'baseline': (baseline.get('shared_from') or {}).get('unit') or baseline.get('unit'),
            'baseline_selected': member.get('baseline_selected')}


def _decisions(step_dir):
    found = _read(step_dir / 'decisions.json')
    return [_decision_row(label, decision) for label, decision in _flatten_decisions(found)] if found is not None else []


def _library_listing(path):
    """Names, kinds, descriptions and home types of every skill in the frozen library of a step (hash verified)."""
    if not path.exists():
        return None
    rows = []
    for skill in Library.load(path).skills:
        origin = skill.get('origin') or {}
        rows.append({'skill_id': skill['skill_id'], 'name': skill['name'], 'kind': skill['kind'],
                     'home_type': skill['home_type'], 'description': skill.get('description'),
                     'origin_step': origin.get('step'), 'origin_bench': origin.get('bench'),
                     'retired_at_step': skill.get('retired_at_step'), 'sha256': skill.get('sha256')})
    return rows


def _typemap_summary(path):
    """Types with their sources, card and programs; sources with their size and threshold (never the centroid)."""
    if not path.exists():
        return None
    found = TypeMap.load(path)
    sources = {sid: {key: source.get(key) for key in ('signature', 'members', 'threshold', 'mean_distance', 'added_step')}
               for sid, source in found.data['sources'].items()}
    return {'step': found.data.get('step'), 'embedding': found.data.get('embedding'), 'types': found.summary(),
            'sources': sources}


def _unit_summary(unit_dir, *, allow_sealed=False):
    """Counts of one unit: cells, expected, stop reason, tokens, unknown and failure kinds, per arm (no text)."""
    done = _read(unit_dir / 'done.json', allow_sealed=allow_sealed)
    cells_dir = unit_dir / 'cells'
    cells = ([_read(path, allow_sealed=allow_sealed) for path in sorted(cells_dir.glob('*.json'))]
             if cells_dir.is_dir() else [])
    unsubmitted = len(list((unit_dir / 'unsubmitted').glob('*.json'))) if (unit_dir / 'unsubmitted').is_dir() else 0
    by_arm = {}
    for cell in cells:  # a gate repeat '<arm>#<r>' folds into its arm, with the counts per repeat beside (DESIGN 3.4)
        label = str(cell.get('arm'))
        arm = by_arm.setdefault(gates.arm_of_label(label), {'cells': 0, 'correct': 0, 'wrong': 0, 'unknown': 0})
        outcome = 'correct' if cell.get('correct') is True else 'wrong' if cell.get('correct') is False else 'unknown'
        arm['cells'] += 1
        arm[outcome] += 1
        repeat = gates.repeat_of_label(label)
        if repeat is not None:
            counts = arm.setdefault('repeats', {}).setdefault(str(repeat), {'cells': 0, 'correct': 0, 'wrong': 0,
                                                                           'unknown': 0})
            counts['cells'] += 1
            counts[outcome] += 1
    failure = _read(unit_dir / 'failure.json', allow_sealed=allow_sealed)
    plan = _read(unit_dir / 'plan.json', allow_sealed=allow_sealed)
    return {'unit': unit_dir.name, 'done': done is not None, 'cells': len(cells),
            'expected_cells': (done or {}).get('expected_cells'), 'missing_cells': (done or {}).get('missing_cells'),
            'stop_reason': (done or {}).get('stop_reason'), 'started': (done or {}).get('started'),
            'finished': (done or {}).get('finished'), 'unsubmitted': unsubmitted,
            'tokens': sum(int(cell.get('tokens') or 0) for cell in cells),
            'unknown': sum(cell.get('correct') is None for cell in cells),
            'unknown_by_token': _counter(cell.get('token') for cell in cells if cell.get('correct') is None),
            'infrastructure_unknown': sum(bool(cell.get('infrastructure_unknown')) for cell in cells),
            'configuration_error': sum(bool(cell.get('configuration_error')) for cell in cells),
            'failures': _counter(cell.get('failure') for cell in cells if cell.get('failure')),
            'by_arm': by_arm, 'failure': _scrub(failure) if isinstance(failure, dict) else failure,
            'gate_plan': ({key: plan.get(key) for key in ('arm', 'repeats', 'shared_from', 'identity_sha256')}
                          if isinstance(plan, dict) else None)}


def _step_bench(step_dir, k, order):
    """The bench a step evolved: what its ``decisions.json`` records (the chain's own order), else ``order[k-1]``."""
    found = _read(step_dir / 'decisions.json')
    bench = found.get('bench') if isinstance(found, dict) else None
    if isinstance(bench, str) and bench:
        return bench
    return order[k - 1] if 0 < k <= len(order) else None


def _step(step_dir, k, order=ORDER):
    """One learning step: its bench, noise tau, gate decisions, frozen library/typemap and learning units; a typed-v3
    step (its ``decisions.json`` carries the item stage, the gate rule or the program learning) adds ``typed_v3``
    (``typed_v3_step``). A typed-v2 style step's entry is exactly as before."""
    unit_dirs = [path for path in sorted(step_dir.iterdir()) if path.is_dir() and not _is_read_unit_name(path.name)]
    out = {'step': k, 'bench': _step_bench(step_dir, k, order), 'noise': _noise(step_dir),
           'decisions': _decisions(step_dir), 'library': _library_listing(step_dir / 'library.json'),
           'typemap': _typemap_summary(step_dir / 'typemap.json'),
           'units': {path.name: _unit_summary(path) for path in unit_dirs}}
    extra = typed_v3_step(_read(step_dir / 'decisions.json'))
    if extra is not None:
        out['typed_v3'] = extra
    return out


# ---- typed-v3 additions of a step (CHAIN-DECISIONS T3 to T9; brief P3b C) -------------------------------------------
TYPED_V3_KEYS = ('items', 'gate_rule', 'program_learning')   # what a typed-v3 step's decisions.json may add
EVOLUTION_KEYS = ('n', 'difference_sum', 'variance_sum', 'gain_points', 'se_points', 'tau_points', 'better', 'worse',
                  'tied', 'reaches')
SCREEN_KEYS = ('unit', 'items', 'classes', 'repeats', 'b', 'c', 'fired', 'baseline_pass_points', 'candidate_pass_points',
               'passed', 'reason')
CHECK_KEYS = ('unit', 'round', 'holds', 'reason', 'attack', 'calibration', 'difference_points', 'by_weakness', 'cells',
              'reused')
ARCHIVE_KNOWN = ('the archive packages were chosen when their test readings (earlier runs) were already known: the '
                 'rule that admits them was set after those readings (CHAIN-DECISIONS T9). A package\'s own gate '
                 'decision is shown apart from the step\'s later candidates; the test reads after the step (S<k>) hold '
                 'the package and every candidate the step accepted after it together, and no read separates them.')
SCREEN_NOTE = ('the screen is a coarse filter (build decision B4): a candidate without effect passes about half the time, '
               'a real gain can be screened out; a refusal at the screen is not evidence of no effect.')


def _evolution_summary(block):
    """The deciding numbers of an evolution card on E (its ids stay in the decision record)."""
    return {key: block.get(key) for key in EVOLUTION_KEYS} if isinstance(block, dict) else None


def _screen_summary(record):
    return {key: record.get(key) for key in SCREEN_KEYS} if isinstance(record, dict) else None


def _repair_summary(row):
    """A program row's repair history (T8): the free repair rounds and the one paid feedback round, counts only."""
    repair, learn = row.get('repair'), row.get('learn')
    if not isinstance(repair, dict) and not isinstance(learn, dict):
        return None
    out = {}
    if isinstance(repair, dict):
        out.update(rounds=repair.get('rounds'), limit=repair.get('limit'), kept_round=repair.get('kept_round'),
                   stop=repair.get('stop'), probes=[{key: probe.get(key) for key in (
                       'unit', 'items', 'routed', 'fired', 'noted', 'fault_count', 'unsent', 'failed')}
                       for probe in repair.get('probes') or [] if isinstance(probe, dict)])
    if isinstance(learn, dict):
        feedback = learn.get('feedback') if isinstance(learn.get('feedback'), dict) else None
        out['paid_round'] = {'unit': learn.get('unit'), 'against': learn.get('against'), 'items': learn.get('items'),
                             'fixed': learn.get('fixed'), 'broken': learn.get('broken'),
                             'faults': len(learn.get('faults') or []),
                             'feedback': None if feedback is None else {key: feedback.get(key) for key in (
                                 'unit', 'status', 'kept', 'stop')}}
    return out


def _candidate(kind, row):
    """One candidate of a typed-v3 step: its verdict, the gains by item class (informational), the evolution block of
    a card decided on E, its screen record and a program's repair history."""
    kind = 'archive' if kind == 'program' and row.get('origin') == 'archive' else kind
    return {'kind': kind, 'unit': row.get('unit'), 'round': row.get('round'), 'candidate': row.get('candidate'),
            'accepted': row.get('accepted'), 'reason': row.get('reason'), 'n': row.get('n'),
            'gain_points': row.get('gain_points'), 'tau_points': row.get('tau_points'),
            'gain_points_fired': row.get('gain_points_fired'), 'fired_items': row.get('fired_items'),
            'baseline': ((row.get('baseline') or {}).get('shared_from') or {}).get('unit')
            or (row.get('baseline') or {}).get('unit'),
            'by_class': row.get('by_class'), 'evolution': _evolution_summary(row.get('evolution')),
            'screen': _screen_summary(row.get('screen_run')), 'repair': _repair_summary(row) if kind != 'card' else None}


def typed_v3_step(decisions):
    """What a typed-v3 step adds to the readout (brief P3b C; CHAIN-DECISIONS T3 to T9), from its ``decisions.json``
    alone; None for a typed-v2 style step (none of ``TYPED_V3_KEYS``). ``items``: the item block (the reason when no
    item was made, counts by side and class, J's counts, the plans' kept weaknesses, both checks, the replacement);
    ``gate_rule``: the step's rules (rule, screen, the card rule used, the sizes of J and E, the screen items);
    ``candidates``: every card round and program row in decision order (``_candidate``); ``archive``: the archive
    package's OWN gate decision apart from the step's later candidates (T9), with how many later program candidates
    there were and the arm they were judged against, and ``archive_known`` (``ARCHIVE_KNOWN``)."""
    if not isinstance(decisions, dict) or not any(key in decisions for key in TYPED_V3_KEYS):
        return None
    out = {}
    items = decisions.get('items')
    if isinstance(items, dict):
        out['items'] = {'reason': items.get('reason'), 'counts': items.get('counts'), 'gate': items.get('gate'),
                        'quota': items.get('quota'), 'final_round': items.get('final_round'),
                        'plans': [{key: plan.get(key) for key in ('unit', 'round', 'status', 'unreadable', 'kept',
                                                                  'rule', 'guards')}
                                  for plan in items.get('plans') or [] if isinstance(plan, dict)],
                        'checks': [{key: check.get(key) for key in CHECK_KEYS}
                                   for check in items.get('checks') or [] if isinstance(check, dict)],
                        'replacement': items.get('replacement')}
    if isinstance(decisions.get('gate_rule'), dict):
        out['gate_rule'] = dict(decisions['gate_rule'])
    out['candidates'] = ([_candidate('card', row) for row in decisions.get('cards') or [] if isinstance(row, dict)]
                         + [_candidate('program', row) for row in decisions.get('programs') or []
                            if isinstance(row, dict)])
    programs = [row for row in decisions.get('programs') or [] if isinstance(row, dict)]
    archive = next((row for row in programs if row.get('origin') == 'archive'), None)
    if archive is not None:
        later = [row for row in programs if row is not archive]
        learning = decisions.get('program_learning') if isinstance(decisions.get('program_learning'), dict) else {}
        out['archive'] = {**_candidate('program', archive), 'package': archive.get('package'),
                          'procedure_ids': archive.get('procedure_ids'),
                          'later_candidates': len(later),
                          'later_candidates_judged_against': learning.get('engineer_gate_current'),
                          'archive_known': ARCHIVE_KNOWN}
    return out


def _home_steps(steps, order):
    """{bench: the step that evolved it}: the registered order, overridden by what the chain's steps record."""
    home = {bench: k for k, bench in enumerate(order, 1)}
    for k, step in steps.items():
        if k >= 1 and step.get('bench'):
            home[step['bench']] = k
    return home


def _mirrors(chain_dir):
    """The open read-status mirrors, counts only: a key naming a pass/fail/accuracy is never copied."""
    out = {}
    status_dir = chain_dir / 'read-status'
    if not status_dir.is_dir():
        return out
    for path in sorted(status_dir.glob('*.json')):
        found = _read(path)
        out[path.stem] = (_scrub(_scrub(found), CLOSED_BLOCKED, CLOSED_BLOCKED_EXACT) if isinstance(found, dict)
                          else found)
    return out


def _mirror_fractions_present(mirror):
    """A mirror carries routing fractions when some key names them with a non-empty value."""
    if not isinstance(mirror, dict):
        return False
    for key, value in mirror.items():
        if any(word in str(key).lower() for word in ('typed', 'mount', 'routing', 'fraction', 'selection')):
            if value not in (None, {}, []):
                return True
    return False


def _closed_mount_check(mirrors):
    rows = {}
    for stem, mirror in mirrors.items():
        parsed = _mirror_name(stem)
        if parsed is None:
            continue
        rows[stem] = {'event': parsed[0], 'bench': parsed[1], 'present': _mirror_fractions_present(mirror),
                      'source': 'read-status mirror (counts only)'}
    return {'reads': rows, 'all_present': bool(rows) and all(row['present'] for row in rows.values()),
            'rule': 'every read records what it mounted (the main-v9 F2 identity defect: a card never mounted went '
                    'unnoticed because no read recorded its mount)'}


# ---- open-mode pieces ------------------------------------------------------------------------------------------
def _flags_only(value):
    """Format counters/booleans of a cell; any string value (possible text) is dropped."""
    if not isinstance(value, dict):
        return {}
    return {str(key): inner for key, inner in value.items() if isinstance(inner, (bool, int, float))}


def _project(cell):
    """The sealed cell's non-text fields: outcome, counters, hashes and the mount; never a reply or a prediction."""
    mount = cell.get('mount') if isinstance(cell.get('mount'), dict) else {}
    selection = mount.get('selection') if isinstance(mount.get('selection'), dict) else {}
    official = cell.get('official')
    token = cell.get('token')
    return {'item_id': str(cell['item_id']), 'arm': cell.get('arm'), 'correct': cell.get('correct'),
            'token': token if isinstance(token, str) else None,
            'official': official.get('status') if isinstance(official, dict) else official if isinstance(official, str) else None,
            'format': _flags_only(cell.get('format')), 'flags': sorted(str(flag) for flag in cell.get('flags') or []),
            'fired': [str(x) for x in cell.get('fired') or []], 'faults': len(cell.get('faults') or []),
            'tokens': int(cell.get('tokens') or 0),
            'request_sha256': [str(x) for x in cell.get('request_sha256') or []],
            'configuration_error': bool(cell.get('configuration_error')),
            'infrastructure_unknown': bool(cell.get('infrastructure_unknown')),
            'failure': cell.get('failure') if isinstance(cell.get('failure'), str) else None,
            'mount': {'present': all(key in mount for key in MOUNT_KEYS), 'type': mount.get('type'),
                      'unknown_reason': mount.get('unknown_reason'), 'card_skill': mount.get('card_skill'),
                      'programs_offered': len(mount.get('programs_offered') or []),
                      'programs_enabled': [str(x) for x in mount.get('programs_enabled') or []],
                      'selection_status': selection.get('status')}}


def read_units_of(chain_dir):
    """{(event, bench): unit dir} of the read units under the chain (and its anchors/ folder when used)."""
    found = {}
    for parent in (chain_dir, chain_dir / 'anchors'):
        if not parent.is_dir():
            continue
        for path in sorted(parent.iterdir()):
            parsed = parse_read_name(path.name) if path.is_dir() else None
            if parsed is not None:
                require(parsed not in found, 'Two read units for one event and bench: ' + path.name)
                found[parsed] = path
    return found


def _load_read_unit(unit_dir):
    """{item_id: projected cell} of one read unit, read with allow_sealed (the owner's opening)."""
    cells = {}
    cells_dir = unit_dir / 'cells'
    for path in sorted(cells_dir.glob('*.json')) if cells_dir.is_dir() else []:
        projected = _project(units.read_json(path, allow_sealed=True))
        require(projected['item_id'] not in cells, 'Two cells of one item in ' + unit_dir.name)
        cells[projected['item_id']] = projected
    done = _read(unit_dir / 'done.json', allow_sealed=True)
    return cells, {'unit': unit_dir.name, 'done': done is not None, 'stop_reason': (done or {}).get('stop_reason'),
                   'expected_cells': (done or {}).get('expected_cells'), 'cells': len(cells)}


def _routing(rows):
    """Mount fractions of one read: typed share, unknown reasons, cards/programs mounted, selection outcomes."""
    n = len(rows)
    share = lambda count: count / n if n else None
    typed = sum(row['mount']['type'] is not None for row in rows)
    cards = sum(row['mount']['card_skill'] is not None for row in rows)
    enabled = sum(bool(row['mount']['programs_enabled']) for row in rows)
    return {'cells': n, 'mount_records_present': sum(row['mount']['present'] for row in rows),
            'typed': typed, 'typed_fraction': share(typed),
            'unknown_by_reason': _counter(row['mount']['unknown_reason'] for row in rows if row['mount']['type'] is None),
            'card_mounted': cards, 'card_mounted_fraction': share(cards),
            'programs_offered_cells': sum(row['mount']['programs_offered'] > 0 for row in rows),
            'programs_enabled_cells': enabled, 'enabled_fraction': share(enabled),
            'fired_cells': sum(bool(row['fired']) for row in rows),
            'selection_status': _counter(row['mount']['selection_status'] for row in rows
                                         if row['mount']['selection_status'] is not None),
            'types': _counter(row['mount']['type'] for row in rows if row['mount']['type'] is not None),
            'cards': _counter(row['mount']['card_skill'] for row in rows if row['mount']['card_skill'] is not None),
            'programs': _counter(program for row in rows for program in row['mount']['programs_enabled'])}


def _accuracy(rows):
    """L (unknown = wrong), H (unknown = right) and known-only accuracy of projected cells, with the counts."""
    n = len(rows)
    correct = sum(row['correct'] is True for row in rows)
    unknown = sum(row['correct'] is None for row in rows)
    known = n - unknown
    return {'n': n, 'correct_known': correct, 'unknown': unknown,
            'accuracy': {'L': correct / n if n else None, 'H': (correct + unknown) / n if n else None,
                         'known': correct / known if known else None}}


def _event_summary(cells, items):
    rows = [cells[item] for item in items]
    return {**_accuracy(rows), 'cells': len(cells),
            'unknown_by_token': _counter(row['token'] for row in rows if row['correct'] is None),
            'infrastructure_unknown': sum(row['infrastructure_unknown'] for row in rows),
            'configuration_error': sum(row['configuration_error'] for row in rows),
            'failures': _counter(row['failure'] for row in rows if row['failure']),
            'faults': sum(row['faults'] for row in rows),
            'format': _counter(key for row in rows for key, value in row['format'].items() if value is True),
            'flags': _counter(flag for row in rows for flag in row['flags']),
            'tokens': sum(row['tokens'] for row in rows), 'routing': _routing(rows)}


def _paired(first, second, items):
    """first - second on the complete cases (gates.split_pairs: unknown excluded and counted), in points."""
    pairs = [(item, second[item]['correct'], first[item]['correct']) for item in items]
    diffs, kept, excluded = gates.split_pairs(pairs)
    stats = gates.paired_statistics(diffs)
    points = lambda value: None if value is None else value * 100
    interval = lambda value: None if value is None else [x * 100 for x in value]
    return {'n_common': len(items), 'n': len(kept), 'excluded_unknown': excluded,
            'mean_points': points(stats['mean']), 'se_points': points(stats['se']),
            't_interval95_points': interval(stats['t_interval95']),
            'bootstrap_interval95_points': interval(stats['bootstrap_interval95']),
            'better': stats['better'], 'worse': stats['worse'], 'tied': stats['tied'],
            'first_correct': sum(candidate for _, _, candidate in kept),
            'second_correct': sum(current for _, current, _ in kept)}


def _pairs(by_event, items):
    """S<k>-C0, S<k>-C and S<k>-S<k-1> (k >= 2; S1-C0 is step 1's incremental contrast) for the events present."""
    out = {}
    for k in range(1, len(STEP_EVENTS) + 1):
        event = 'S%d' % k
        if event not in by_event:
            continue
        for anchor in ('C0', 'C'):
            if anchor in by_event:
                out['%s-%s' % (event, anchor)] = _paired(by_event[event], by_event[anchor], items)
        previous = 'S%d' % (k - 1)
        if k >= 2 and previous in by_event:
            out['%s-%s' % (event, previous)] = _paired(by_event[event], by_event[previous], items)
    return out


def _same_request_noise(c0, c):
    """C vs C0 on the items whose request sha lists are identical (ZebraLogic by construction: C has no card)."""
    if c0 is None or c is None:
        return None
    items = sorted(set(c0) & set(c))
    missing = [item for item in items if not c0[item]['request_sha256'] or not c[item]['request_sha256']]
    identical = [item for item in items if item not in missing and c0[item]['request_sha256'] == c[item]['request_sha256']]
    noise = gates.noise_threshold([(item, c0[item]['correct'], c[item]['correct']) for item in identical]) if identical else None
    return {'items_common': len(items), 'identical_requests': len(identical),
            'differing_requests': len(items) - len(identical) - len(missing), 'missing_request_sha': len(missing),
            'noise': {key: noise.get(key) for key in NOISE_KEYS} if noise else None}


def _panel(by_event):
    """One bench: per-event accuracies on the common items, the paired contrasts and the same-request noise."""
    events = [event for event in READ_ARMS if event in by_event]
    common = sorted(set.intersection(*(set(by_event[event]) for event in events))) if events else []
    return {'events': events, 'items_common': len(common),
            'items_by_event': {event: len(by_event[event]) for event in events},
            'per_event': {event: _event_summary(by_event[event], common) for event in events},
            'pairs': _pairs(by_event, common), 'same_request_noise': _same_request_noise(by_event.get('C0'), by_event.get('C'))}


def _five_by_five(panels, home_steps, n_steps):
    """Rows: steps 1..n = the bench evolved at that step (``home_steps``); columns: the five panels; S<k>-C0 (points)
    and S<k> accuracy."""
    evolved = {k: bench for bench, k in home_steps.items()}
    rows = {}
    for k in range(1, n_steps + 1):
        event = 'S%d' % k
        cell = lambda bench, key: panels[bench]['per_event'][event]['accuracy'][key] if bench in panels and event in panels[bench]['per_event'] else None
        rows[event] = {'step': k, 'evolved_bench': evolved.get(k),
                       'diff_points_vs_C0': {bench: (panels[bench]['pairs'].get(event + '-C0') or {}).get('mean_points')
                                             if bench in panels else None for bench in ORDER},
                       'accuracy_L': {bench: cell(bench, 'L') for bench in ORDER},
                       'accuracy_H': {bench: cell(bench, 'H') for bench in ORDER}}
    return rows


def _formulas(acc, k_home, final):
    """The module's CL formulas on one side's accuracies {event: value}; None where an input event is missing."""
    if final is None or acc.get(final) is None:
        return {**{key: None for key in METRIC_KEYS}, 'final_event': None}
    K = int(final[1:])
    step = lambda k: 'C0' if k == 0 else 'S%d' % k
    diff = lambda x, y: None if x is None or y is None else x - y
    final_acc = acc[final]
    earlier = [acc[step(k)] for k in range(1, K) if acc.get(step(k)) is not None]
    after_home = [acc[step(k)] for k in range(k_home, K) if acc.get(step(k)) is not None]
    return {'final_event': final, 'final': final_acc, 'C0': acc.get('C0'), 'C': acc.get('C'),
            'gain_over_C0': diff(final_acc, acc.get('C0')), 'gain_over_C': diff(final_acc, acc.get('C')),
            'forgetting': max(earlier) - final_acc if earlier else None,  # signed: a bench ending above every
            'forgetting_after_home': max(after_home) - final_acc if after_home else None,  # earlier step is negative
            'backward_transfer': diff(final_acc, acc.get(step(k_home))) if k_home < K else None,
            'forward_transfer': diff(acc.get(step(k_home - 1)), acc.get('C0')) if k_home >= 2 else None,
            'plasticity': diff(acc.get(step(k_home)), acc.get(step(k_home - 1)))}


def _bench_metrics(panel, k_home, final_event):
    """One bench's metrics with ``final_event`` (S<n> of the chain's last step) and its ``latest`` block."""
    events = panel['events']
    steps = [event for event in STEP_EVENTS if event in events]
    acc = {side: {event: panel['per_event'][event]['accuracy'][side] for event in events} for side in SIDES}
    final = final_event if final_event in events else None
    latest = steps[-1] if steps else None
    return {'home_step': k_home, 'events': events, 'n': panel['items_common'], 'final_event': final,
            'latest_event': latest, **{side: _formulas(acc[side], k_home, final) for side in SIDES},
            'latest': {side: _formulas(acc[side], k_home, latest) for side in SIDES}}


def _macro(per_bench, side, block=None):
    """Equal-weight means over the benches where a value is defined (the reference's ACC/dACC/BWT/FGT/FWT/PG)."""
    out = {}
    for key in METRIC_KEYS:
        values = [(m['latest'][side] if block == 'latest' else m[side])[key] for m in per_bench.values()]
        values = [value for value in values if value is not None]
        out[key] = {'mean': sum(values) / len(values) if values else None, 'n_benches': len(values)}
    return out


def _cl_metrics(panels, home_steps, n_steps):
    """CL metrics per bench (home step = the step that evolved it) and their macro means; the final event is
    S<n_steps>, the last step of the chain's order."""
    final_event = 'S%d' % n_steps
    per_bench = {bench: _bench_metrics(panels[bench], home_steps[bench], final_event)
                 for bench in ORDER if bench in panels and bench in home_steps}
    return {'definitions': {
                'acc': 'accuracy of an event on the items common to every event of the panel; L: unknown = wrong, '
                       'H: unknown = right; S0 := C0', 'final': 'acc(S%d)' % n_steps,
                'gain_over_C0': 'acc(S%d) - acc(C0)' % n_steps, 'gain_over_C': 'acc(S%d) - acc(C)' % n_steps,
                'forgetting': 'max_{1<=k<%d} acc(S_k) - acc(S%d) (signed, no floor)' % (n_steps, n_steps),
                'forgetting_after_home': 'max_{k_b<=k<%d} acc(S_k) - acc(S%d) (vendored cl_metrics FGT, signed)' % (n_steps, n_steps),
                'backward_transfer': 'acc(S%d) - acc(S_{k_b}) for k_b < %d (k_b = the step that evolved the bench)' % (n_steps, n_steps),
                'forward_transfer': 'acc(S_{k_b-1}) - acc(C0) for k_b >= 2', 'plasticity': 'acc(S_{k_b}) - acc(S_{k_b-1})',
                'macro': 'equal-weight mean over the benches where the value is defined',
                'latest': 'the same formulas with the last available S<k> in place of S%d (unfinished chain)' % n_steps},
            'final_event': final_event, 'home_steps': dict(home_steps), 'per_bench': per_bench,
            'macro': {side: _macro(per_bench, side) for side in SIDES},
            'macro_latest': {side: _macro(per_bench, side, 'latest') for side in SIDES}}


def _open_mount_check(reads, steps):
    """Every read's cells carry a mount record and name only skills frozen in that step's library."""
    rows = {}
    for (event, bench), summary in reads.items():
        routing = summary['routing']
        library = steps.get(int(event[1:]), {}).get('library') if event.startswith('S') else None
        known = {row['skill_id'] for row in library} if library else None
        seen = set(routing['cards']) | set(routing['programs'])
        rows['%s-%s' % (event, bench)] = {
            'event': event, 'bench': bench, 'cells': routing['cells'],
            'mount_records_present': routing['mount_records_present'],
            'present': routing['cells'] > 0 and routing['mount_records_present'] == routing['cells'],
            'typed_fraction': routing['typed_fraction'], 'card_mounted_fraction': routing['card_mounted_fraction'],
            'skills_seen': sorted(seen), 'library_skills': sorted(known) if known is not None else None,
            'unknown_skill_ids': sorted(seen - known) if known is not None else [], 'source': 'sealed cells'}
    return {'reads': rows,
            'all_present': bool(rows) and all(row['present'] and not row['unknown_skill_ids'] for row in rows.values()),
            'rule': 'every read records what it mounted, and every mounted skill exists in that step\'s frozen library '
                    '(the main-v9 F2 identity defect: a card never mounted went unnoticed)'}


def _open(chain_dir, steps, order):
    """The sealed reads opened: per-bench panels, the 5x5, CL metrics, costs per read and the mount check."""
    by_bench, reads, read_units = {}, {}, {}
    for (event, bench), unit_dir in read_units_of(chain_dir).items():
        cells, meta = _load_read_unit(unit_dir)
        by_bench.setdefault(bench, {})[event] = cells
        read_units['%s-%s' % (event, bench)] = meta
    panels = {bench: _panel(by_bench[bench]) for bench in ORDER if bench in by_bench}
    for bench, panel in panels.items():
        for event in panel['events']:
            reads[(event, bench)] = panel['per_event'][event]
    home = _home_steps(steps, order)
    return {'read_units': read_units, 'panels': panels, 'five_by_five': _five_by_five(panels, home, len(order)),
            'cl_metrics': _cl_metrics(panels, home, len(order)), 'mount_check': _open_mount_check(reads, steps),
            'read_tokens': {'%s-%s' % key: value['tokens'] for key, value in reads.items()}}


# ---- typed-v3 T2: a 'full' chain without the C0 read (read_anchors C) -------------------------------------------
# The typed-v1 consumers above stay byte-equal (tests/test_typed_readout.py pins their source). A chain whose state
# records read_anchors ['C'] is opened by ``_open_c``, which reuses them for the panels, the pairs (S<k> - C and
# S<k> - S<k-1> only, since no C0 unit exists), the accuracies and the mount check, and replaces only what names C0:
# the 5x5 contrast and the S0 of the continual-learning metrics.
def _five_by_five_c(panels, home_steps, n_steps):
    """typed-v3 T2 (no C0 read): the rows of ``_five_by_five`` with the contrasts S<k> - C and S<k> - S<k-1> in points
    (S0 := C: at k = 1 the second repeats S1 - C) in place of S<k> - C0, and the S<k> accuracies."""
    evolved = {k: bench for bench, k in home_steps.items()}
    rows = {}
    for k in range(1, n_steps + 1):
        event, previous = 'S%d' % k, 'S%d' % (k - 1) if k >= 2 else 'C'

        def diff(bench, name):
            return (panels[bench]['pairs'].get(name) or {}).get('mean_points') if bench in panels else None

        def cell(bench, key):
            found = panels.get(bench, {}).get('per_event', {}).get(event)
            return found['accuracy'][key] if found is not None else None
        rows[event] = {'step': k, 'evolved_bench': evolved.get(k),
                       'diff_points_vs_C': {bench: diff(bench, event + '-C') for bench in ORDER},
                       'diff_points_vs_previous': {bench: diff(bench, '%s-%s' % (event, previous)) for bench in ORDER},
                       'accuracy_L': {bench: cell(bench, 'L') for bench in ORDER},
                       'accuracy_H': {bench: cell(bench, 'H') for bench in ORDER}}
    return rows


def _formulas_c(acc, k_home, final):
    """``_formulas`` with S0 := C (the start of learning under the base 'historical' that C alone requires) and the
    keys of ``C_METRIC_KEYS``: forward_transfer = acc(S_{k_b-1}) - acc(C) for k_b >= 2, the plasticity of k_b = 1 =
    acc(S1) - acc(C); the C0 level and gain_over_C0 are not computed."""
    if final is None or acc.get(final) is None:
        return {**{key: None for key in C_METRIC_KEYS}, 'final_event': None}
    K = int(final[1:])
    step = lambda k: 'C' if k == 0 else 'S%d' % k
    diff = lambda x, y: None if x is None or y is None else x - y
    final_acc = acc[final]
    earlier = [acc[step(k)] for k in range(1, K) if acc.get(step(k)) is not None]
    after_home = [acc[step(k)] for k in range(k_home, K) if acc.get(step(k)) is not None]
    return {'final_event': final, 'final': final_acc, 'C': acc.get('C'), 'gain_over_C': diff(final_acc, acc.get('C')),
            'forgetting': max(earlier) - final_acc if earlier else None,  # signed, as ``_formulas``
            'forgetting_after_home': max(after_home) - final_acc if after_home else None,
            'backward_transfer': diff(final_acc, acc.get(step(k_home))) if k_home < K else None,
            'forward_transfer': diff(acc.get(step(k_home - 1)), acc.get('C')) if k_home >= 2 else None,
            'plasticity': diff(acc.get(step(k_home)), acc.get(step(k_home - 1)))}


def _bench_metrics_c(panel, k_home, final_event):
    """``_bench_metrics`` on ``_formulas_c``."""
    events = panel['events']
    steps = [event for event in STEP_EVENTS if event in events]
    acc = {side: {event: panel['per_event'][event]['accuracy'][side] for event in events} for side in SIDES}
    final = final_event if final_event in events else None
    latest = steps[-1] if steps else None
    return {'home_step': k_home, 'events': events, 'n': panel['items_common'], 'final_event': final,
            'latest_event': latest, **{side: _formulas_c(acc[side], k_home, final) for side in SIDES},
            'latest': {side: _formulas_c(acc[side], k_home, latest) for side in SIDES}}


def _macro_c(per_bench, side, block=None):
    """``_macro`` over the keys of ``C_METRIC_KEYS``."""
    out = {}
    for key in C_METRIC_KEYS:
        values = [(m['latest'][side] if block == 'latest' else m[side])[key] for m in per_bench.values()]
        values = [value for value in values if value is not None]
        out[key] = {'mean': sum(values) / len(values) if values else None, 'n_benches': len(values)}
    return out


def _cl_metrics_c(panels, home_steps, n_steps):
    """``_cl_metrics`` without C0: per bench ``_bench_metrics_c`` (S0 := C), the macro means over ``C_METRIC_KEYS``,
    and the dropped quantities named under ``not_read``."""
    final_event = 'S%d' % n_steps
    per_bench = {bench: _bench_metrics_c(panels[bench], home_steps[bench], final_event)
                 for bench in ORDER if bench in panels and bench in home_steps}
    return {'definitions': {
                'acc': 'accuracy of an event on the items common to every event of the panel; L: unknown = wrong, '
                       'H: unknown = right; S0 := C (C0 is not read)', 'final': 'acc(S%d)' % n_steps,
                'gain_over_C': 'acc(S%d) - acc(C)' % n_steps,
                'forgetting': 'max_{1<=k<%d} acc(S_k) - acc(S%d) (signed, no floor)' % (n_steps, n_steps),
                'forgetting_after_home': 'max_{k_b<=k<%d} acc(S_k) - acc(S%d) (vendored cl_metrics FGT, signed)' % (n_steps, n_steps),
                'backward_transfer': 'acc(S%d) - acc(S_{k_b}) for k_b < %d (k_b = the step that evolved the bench)' % (n_steps, n_steps),
                'forward_transfer': 'acc(S_{k_b-1}) - acc(C) for k_b >= 2', 'plasticity': 'acc(S_{k_b}) - acc(S_{k_b-1})',
                'macro': 'equal-weight mean over the benches where the value is defined',
                'latest': 'the same formulas with the last available S<k> in place of S%d (unfinished chain)' % n_steps,
                'not_read': 'read_anchors C: the anchor C0 is not read, so the C0 level, gain_over_C0 and the '
                            'same-request noise (C vs C0) are not computed'},
            'final_event': final_event, 'home_steps': dict(home_steps), 'per_bench': per_bench,
            'macro': {side: _macro_c(per_bench, side) for side in SIDES},
            'macro_latest': {side: _macro_c(per_bench, side, 'latest') for side in SIDES},
            'not_read': list(C0_DEPENDENT)}


def _open_c(chain_dir, steps, order):
    """``_open`` of a chain without the C0 read: the same panels (rows C, S1..S5; no C0 unit, so the pairs are S<k> - C
    and S<k> - S<k-1> only and the same-request noise is None), ``_five_by_five_c``, ``_cl_metrics_c``, the mount check
    and the read tokens. A read unit of an event the chain does not plan (a C0 unit) is refused, never tabulated or
    silently left out."""
    by_bench, reads, read_units = {}, {}, {}
    found = read_units_of(chain_dir)
    planned = rp.read_events(('C',))
    unplanned = sorted('%s-%s' % key for key in found if key[0] not in planned)
    require(not unplanned, 'Read units of events a chain with read_anchors C does not plan: ' + ', '.join(unplanned))
    for (event, bench), unit_dir in found.items():
        cells, meta = _load_read_unit(unit_dir)
        by_bench.setdefault(bench, {})[event] = cells
        read_units['%s-%s' % (event, bench)] = meta
    panels = {bench: _panel(by_bench[bench]) for bench in ORDER if bench in by_bench}
    for bench, panel in panels.items():
        for event in panel['events']:
            reads[(event, bench)] = panel['per_event'][event]
    home = _home_steps(steps, order)
    return {'read_units': read_units, 'panels': panels, 'five_by_five': _five_by_five_c(panels, home, len(order)),
            'cl_metrics': _cl_metrics_c(panels, home, len(order)), 'mount_check': _open_mount_check(reads, steps),
            'read_tokens': {'%s-%s' % key: value['tokens'] for key, value in reads.items()}}


# ---- economy read plan: resolver, marks, contrasts, phases (spec/read-plan.md 1.F; addendum D10 d, RP3-RP7) ----
ECONOMY = 'economy'
PAIR_SOURCES = ('fresh', 'alias', 'void_alias', 'pending', 'invalid')
CELL_KINDS = ('measured', 'alias', 'same_class', 'structural', 'noise_sample', 'split', 'incomplete', 'none')
STALE_ALIAS = 'stale_alias_record'
FRESH_KINDS = ('fresh', 'read-status')   # 3.6: fresh is implied when absent; a read stores its mirror ('read-status')
SPLIT_SECONDS = 24 * 3600            # RP5: a pause of at most 24 h whose owner record says same_phase: true
LOCAL_TIME = '%Y-%m-%dT%H:%M:%S'     # chain._now, units: local wall-clock time without a zone
DIFF_KEYS = ('gain_over_C0', 'gain_over_C', 'forgetting', 'forgetting_after_home', 'backward_transfer',
             'forward_transfer', 'plasticity')
LEVEL_KEYS = ('final', 'C0', 'C')
ECONOMY_LEGEND = ('=X v u/i/c: same requests as event X (D10 d: not read again); v is X\'s own reading shown again, '
                  'u/i/c = X\'s unknown / infrastructure / configuration counts; - : same requests, not measured '
                  '(JSON null; a structural 0 in a continual-learning term); noise sample: two fresh readings of '
                  'identical requests, a measure of noise and not an effect (R67); split: not same-phase (R89), point '
                  'value in the reference block only; pending / invalid / void_alias: no value')
ECONOMY_DEFINITIONS = {
    'cell': ('every exported grid number is {value, source, of, independent, kind}: source fresh | alias | '
             'void_alias | pending | invalid (of a difference: fresh when neither side was dereferenced); an alias '
             'cell has value null and of = its representative (dereference on purpose; a 5x5 difference row carries '
             'the contrast cell it stands for as shown); kind measured | alias | same_class | structural | '
             'noise_sample | split | incomplete | none'),
    'same_class': ('two events of one class send the same requests: their contrast is null and printed -, never a '
                   'measured 0.0 or 0/0 counts (D10 d, R67)'),
    'contrast': ('a contrast between two classes uses the two representatives\' fresh units (R68) and is labelled '
                 'requests identical | different (d of n items) | unverified from the first inputs per item (system '
                 'hash, first selection request, offered programs, public hash, first request hash when no program '
                 'is offered; R67); identical everywhere = a noise sample, not an effect'),
    'structural': ('a continual-learning term between two events of one class is a structural 0 (kind structural), '
                   'never a sample (R70)'),
    'noise_sample': ('a continual-learning term between two same-phase fresh units whose requests are identical on '
                     'every item (a fallback class, a re-read of a voided alias, a void plan) is a noise sample, not '
                     'an effect (R67): kind noise_sample, value null, its reading as reference; by construction 0 like '
                     'a structural term, so it never enters a maximum and a macro counts it apart'),
    'forgetting': ('RP4: when an earlier event shares the final event\'s class (or, a noise sample, its requests), '
                   'the measured maximum over the other classes if above 0, else - with the count of by-construction '
                   'terms (JSON value 0, kind structural); without such events the signed measured maximum; split '
                   'terms and noise samples are listed beside and never enter the maximum; an earlier event without '
                   'a reading (pending, invalid, void_alias) leaves the maximum undefined (kind incomplete, the '
                   'missing events and the maximum of the others listed)'),
    'macro': ('two pre-registered columns: (a) the mean over the benches where the term is defined, structural zeros '
              'and noise samples entered as 0 (k structural, m noise samples); (b) the mean over the measured '
              'benches only (n); an incomplete term counts as pending. A macro with a split '
              'term prints mixed: k same-phase, m split, no mean. A comparison with a five-bench baseline uses (a); '
              'neither is comparable with a full run\'s maximum over noisy readings'),
    'same_phase': ('R89: equal sets of returned model ids over all sends of both units, and no splitting recovery '
                   'between the earlier unit\'s first start and the later unit\'s last finish (a recovery does not '
                   'split iff its pause, or for a crash the time since the latest earlier unit or plan file, lasted '
                   'at most 24 h AND its owner record says same_phase: true)'),
    'replicates': ('in-run replicates: the number of distinct pairs of fresh units whose measured contrast has '
                   'identical requests on every item (R69; 0 unless a fallback read two identical classes); the '
                   'practice-side gate noise of each step is shown beside the read tables instead (RP7)'),
    'generalization': ('S<k> minus the previous state on every bench (S0 = the base row: C under base historical, C0 '
                       'under format), from the representatives; home = the bench evolved at step k, same-type = a '
                       'bench with a source in the home bench\'s type in s<k>/typemap.json, routed n/N = any other '
                       'bench n of whose N panel items the fresh unit standing for S<k> (its own or its '
                       'representative\'s: same requests) routed into the home type (a bench not learned yet with the '
                       'home bench\'s signature, or an earlier bench routed into the type, RP15), other-type = every '
                       'other bench. Informational: it decides nothing')}


def read_plan_mode(state):
    """'economy' when the chain state says so; 'full' for every other state (typed-v1, the code default)."""
    info = state.get('read_plan') if isinstance(state, dict) else None
    return ECONOMY if isinstance(info, dict) and info.get('mode') == ECONOMY else 'full'


def _plan_info(state):
    info = state.get('read_plan') if isinstance(state, dict) else None
    return info if isinstance(info, dict) else {}


def _short(value):
    return value[:12] if isinstance(value, str) else None


def _bound_plan(chain_dir, info):
    """(plan, error code): (None, None) before the binding; a plan whose bytes, self-hash or structure fail, or whose
    hashes are not the bound ones, gives its fixed code (R74: then no read table is rendered)."""
    if not info.get('plan_sha256'):
        return None, None
    path = chain_dir / rp.PLAN_FILE
    if not path.is_file():
        return None, 'plan_missing'
    try:
        return rp.load_plan(path, file_sha256=info.get('file_sha256'), plan_sha256=info['plan_sha256']), None
    except rp.ReadPlanError as error:
        return None, error.code
    except (OSError,) + rp.UNREADABLE:
        return None, 'plan_unreadable'


def _raw_mirror(chain_dir, event, bench):
    found = _read(chain_dir / 'read-status' / ('%s-%s.json' % (event, bench))) if event in READ_ARMS else None
    return found if isinstance(found, dict) else None


def _aliases(chain_dir, plan=None):
    """R65: the alias records under ``<chain>/read-alias/`` (closed names only, R80: a ``.part`` file or an archived
    record is never read), each verified as R44 a does when the bound plan is given (bytes, self-hash, plan hash,
    equality with the record rebuilt from the plan, the representative's aggregate hash and counts from its open
    mirror). {'<event>-<bench>': {event, bench, of, unit, counts, check, record_sha256, valid, error}}; hashes and
    counts only."""
    folder = chain_dir / rp.ALIAS_DIR
    out = {}
    for name in rp.record_names(folder):
        parsed = _mirror_name(name[:-len('.json')]) if rp.record_kind(name) == 'alias' else None
        if parsed is None:
            continue
        event, bench = parsed
        row = {'event': event, 'bench': bench, 'of': None, 'unit': None, 'counts': None, 'check': None,
               'record_sha256': None, 'valid': False, 'error': None}
        try:
            raw = rp.record_from_bytes(rp.read_bytes(folder / name), code='read_alias_invalid')
            representative = raw.get('representative') if isinstance(raw.get('representative'), dict) else {}
            row.update(of=representative.get('event') if representative.get('event') in READ_ARMS else None,
                       unit=representative.get('unit') if isinstance(representative.get('unit'), str) else None,
                       counts=raw.get('representative_counts') if isinstance(raw.get('representative_counts'), dict)
                       else None, check=raw.get('check') if isinstance(raw.get('check'), dict) else None,
                       record_sha256=raw.get('record_sha256') if rp.is_hash(raw.get('record_sha256')) else None)
            mirror = _raw_mirror(chain_dir, row['of'], bench)
            if plan is None:
                row['error'] = 'plan_missing'
            elif mirror is None:
                row['error'] = 'representative_missing'
            else:
                rp.load_alias(folder / name, plan, representative_aggregate_sha256=mirror.get('aggregate_sha256'),
                              representative_counts={key: mirror.get(key) for key in rp.COUNT_KEYS})
                row['valid'] = True
        except rp.ReadPlanError as error:
            row['error'] = error.code
        except (OSError,) + rp.UNREADABLE:
            row['error'] = 'read_alias_invalid'
        out['%s-%s' % (event, bench)] = row
    return out


def _pair(source, of=None, cls=None, **extra):
    """One resolved (event, bench): ``independent`` is true only for a fresh unit (R63)."""
    return {'source': source, 'of': of, 'class': cls, 'independent': source == 'fresh', **extra}


def _class_id(plan, event, bench):
    try:
        return rp.class_of(plan, event, bench)['id']
    except (ValueError, KeyError, TypeError):
        return None


def _fresh_complete(entry, done, event, bench):
    """R46's fresh rule on the open side: the ``read-`` marker and a complete mirror without a stop."""
    return (entry.get('status', 'complete') == 'complete' and entry.get('stop_reason') is None
            and not entry.get('missing_cells') and 'read-%s-%s' % (event, bench) in done)


def _alias_problem(key, entry, record, plan, pairs, void):
    """None when an alias state entry stands: its record verifies and names the state's representative, which is a
    complete fresh unit; else the fixed reason that makes the pair ``invalid``."""
    if void:
        return 'plan_void'
    if plan is None:
        return 'plan_missing'
    if record is None:
        return 'record_missing'
    if not record['valid']:
        return record['error'] or 'read_alias_invalid'
    if entry.get('alias_sha256') != record['record_sha256'] or entry.get('alias_of') != record['of']:
        return 'state_mismatch'
    representative = pairs.get((record['of'], key[1])) or {}
    if representative.get('source') != 'fresh' or not representative.get('complete'):
        return 'representative_not_fresh'
    return None


def _resolve_chain(chain_dir, state):
    """R63 on one chain directory: every (event, bench) from the STATE (the only authority on how a pair was
    settled, R39), checked against the bound plan and the verified alias records: ``{'source': fresh | alias |
    void_alias | pending | invalid, 'of': <event read>, 'class': <plan class id>, 'independent': bool}``. With
    ``read_plan = full`` (or a typed-v1 state) every pair is ``fresh`` (R6). An alias record without a matching alias
    state entry is a ``stale_alias_record``, never shown. A void plan makes every pair its own class."""
    state = state if isinstance(state, dict) else {}
    mode = read_plan_mode(state)
    keys = [(event, bench) for event in READ_ARMS for bench in ORDER]
    out = {'mode': mode, 'plan': None, 'error': None, 'plan_error': None, 'void': False, 'void_reason': None,
           'aliases': {}, 'stale_alias_records': []}
    if mode != ECONOMY:
        out['pairs'] = {key: _pair('fresh', key[0]) for key in keys}
        return out
    info = _plan_info(state)
    void = info.get('void') is True
    plan, error = _bound_plan(chain_dir, info)
    aliases = _aliases(chain_dir, plan)
    out.update(plan=plan, plan_error=error, error=None if void else error, void=void,
               void_reason=info.get('void_reason'), aliases=aliases)
    if error is not None and not void:   # R74: an economy root whose plan fails renders no read table
        out['pairs'] = {key: _pair('invalid', reason=error) for key in keys}
        out['stale_alias_records'] = sorted(aliases)
        return out
    reads = state.get('reads') if isinstance(state.get('reads'), dict) else {}
    done = set(state.get('done_units') or [])
    entries = {key: (reads.get(key[0]) if isinstance(reads.get(key[0]), dict) else {}).get(key[1]) for key in keys}
    classes = {key: _class_id(plan, *key) if plan is not None and not void else None for key in keys}
    pairs = {}
    for key, entry in entries.items():
        kind = entry.get('kind', 'fresh') if isinstance(entry, dict) and entry else None
        if kind is None:
            pairs[key] = _pair('pending', cls=classes[key])
        elif kind in FRESH_KINDS:   # a fresh entry is the unit's counts-only mirror (its own kind 'read-status')
            pairs[key] = _pair('fresh', key[0], classes[key], complete=_fresh_complete(entry, done, *key))
        elif kind == 'void_alias':
            pairs[key] = _pair('void_alias', cls=classes[key])
        elif kind != 'alias':
            pairs[key] = _pair('invalid', cls=classes[key], reason='state_entry')
    for key, entry in entries.items():   # aliases after every representative is resolved
        if key in pairs:
            continue
        record = aliases.get('%s-%s' % key)
        reason = _alias_problem(key, entry, record, plan, pairs, void)
        pairs[key] = (_pair('alias', record['of'], classes[key], counts=dict(record['counts']),
                            check=dict(record['check'])) if reason is None
                      else _pair('invalid', cls=classes[key], reason=reason))
    out['pairs'] = pairs
    out['stale_alias_records'] = sorted(stem for stem, row in aliases.items()
                                        if not (isinstance(entries.get((row['event'], row['bench'])), dict)
                                                and entries[(row['event'], row['bench'])].get('kind') == 'alias'))
    return out


def _resolve(root, chain):
    """R63: the resolver of one chain of a run root (see ``_resolve_chain``)."""
    chain_dir = Path(root) / chain
    return _resolve_chain(chain_dir, _read(chain_dir / 'state.json'))


def _resolver_export(resolved):
    """The resolver as JSON: pairs keyed '<event>-<bench>', the plan by its short hash only."""
    plan = resolved['plan']
    return {'mode': resolved['mode'], 'plan_sha256': _short((plan or {}).get('plan_sha256')),
            'error': resolved['error'], 'plan_error': resolved['plan_error'], 'void': resolved['void'],
            'void_reason': resolved['void_reason'], 'stale_alias_records': list(resolved['stale_alias_records']),
            'pairs': {'%s-%s' % key: dict(value) for key, value in resolved['pairs'].items()}}


def read_counts(resolved, state):
    """R71, R73: {settled, of: 35, fresh_done, fresh_planned, alias, fallbacks, void_aliases, pending, invalid}.
    Voided aliases are the planned alias pairs now read fresh or awaiting their fresh read (R42, R44 e)."""
    pairs = resolved['pairs']
    plan, info = resolved['plan'], _plan_info(state)
    sources = Counter(pair['source'] for pair in pairs.values())
    planned_alias = {tuple(key) for key in rp.alias_pairs(plan)} if plan is not None else set()
    if plan is not None:
        voided = sum(1 for key in planned_alias if resolved['void'] or pairs[key]['source'] in ('fresh', 'void_alias'))
        fresh_planned = plan['counts']['fresh'] + voided
    else:
        voided, fresh_planned = sources['void_alias'], rp.PAIRS if resolved['void'] else None
    fresh_done = sum(1 for pair in pairs.values() if pair['source'] == 'fresh' and pair.get('complete'))
    return {'settled': fresh_done + sources['alias'], 'of': rp.PAIRS, 'fresh_done': fresh_done,
            'fresh_planned': fresh_planned, 'alias': sources['alias'],
            'fallbacks': (plan['counts']['fallback'] if plan is not None else 0) + len(info.get('fallbacks') or {}),
            'void_aliases': voided, 'pending': sources['pending'], 'invalid': sources['invalid']}


def _uic(counts):
    if not isinstance(counts, dict):
        return '?/?/?'
    return '/'.join(_num(counts.get(key)) for key in rp.COUNT_KEYS)


def _classes(resolved, state, mirrors):
    """R73: per bench the plan's classes: members, representative, the plan status and fallback reason, how each
    member is settled now, the post-read check counts and the representative's u/i/c counts (alias record, else
    its open mirror); a post-read mismatch of the bench (R42) beside."""
    plan = resolved['plan']
    if plan is None:
        return None
    fallbacks = _plan_info(state).get('fallbacks') or {}
    out = {}
    for bench in plan['order']:
        rows = []
        for cls in plan['benches'][bench]['classes']:
            representative = cls['representative']
            records = [resolved['aliases'].get('%s-%s' % (m, bench)) for m in cls['members'] if m != representative]
            records = [row for row in records if row]
            mirror = mirrors.get('%s-%s' % (representative, bench)) or {}
            counts = next((row['counts'] for row in records if row.get('counts')), None) or (
                {key: mirror.get(key) for key in rp.COUNT_KEYS} if mirror else None)
            planned = plan['benches'][bench]['events'][representative]
            rows.append({'id': cls['id'], 'members': list(cls['members']), 'representative': representative,
                         'status': planned['status'], 'reason': planned['reason'],
                         'settled': {m: resolved['pairs'][(m, bench)]['source'] for m in cls['members']},
                         'check': next((row['check'] for row in records if row.get('check')), None),
                         'counts': counts})
        fallback = fallbacks.get(bench) if isinstance(fallbacks.get(bench), dict) else None
        out[bench] = {'classes': rows, 'post_read_mismatch': dict(fallback) if fallback else None}
    return out


def _planned_mount(resolved):
    """R65, R72: the plan's panel-level counts of every alias pair, marked planned (no cell of its own exists)."""
    plan = resolved['plan']
    rows = {}
    for (event, bench), pair in resolved['pairs'].items():
        if pair['source'] == 'alias' and plan is not None:
            planned = plan['benches'][bench]['events'][event]
            rows['%s-%s' % (event, bench)] = {
                'event': event, 'bench': bench, 'of': pair['of'], 'items': plan['benches'][bench]['items'],
                **{key: planned[key] for key in ('typed', 'unknown', 'with_card', 'with_programs', 'captured')},
                'source': 'planned'}
    return rows


def _economy_closed(chain_dir, resolved, state, mirrors):
    """The closed-mode blocks of an economy chain: the read plan, the resolver, the alias records (their own block,
    R65), stale records, the classes (R73), the economy counts (R71) and the planned mount rows of the aliases."""
    plan, info = resolved['plan'], _plan_info(state)
    replay = info.get('replay') if isinstance(info.get('replay'), dict) else {}
    return {'read_plan': {'mode': ECONOMY, 'plan_sha256': _short((plan or {}).get('plan_sha256')),
                          'bound': bool(info.get('plan_sha256')), 'smoke': (plan or {}).get('smoke'),
                          'error': resolved['error'], 'plan_error': resolved['plan_error'], 'void': resolved['void'],
                          'void_reason': resolved['void_reason'], 'replay': replay.get('verdict'),
                          'counts': dict(plan['counts']) if plan is not None else None,
                          'failures': list(info.get('failures') or []),
                          'recoveries': len(info.get('recoveries') or [])},
            'resolver': _resolver_export(resolved),
            'aliases': {stem: dict(row) for stem, row in resolved['aliases'].items()
                        if stem not in resolved['stale_alias_records']},
            'stale_alias_records': [{'pair': stem, 'reason': STALE_ALIAS} for stem in resolved['stale_alias_records']],
            'classes': _classes(resolved, state, mirrors), 'economy': read_counts(resolved, state),
            'planned_mount': _planned_mount(resolved)}


# -- open side: fresh units only, unit times, first inputs, same phase -----------------------------------------
def _epoch(text):
    try:
        return time.mktime(time.strptime(str(text), LOCAL_TIME))
    except (ValueError, TypeError, OverflowError):
        return None


def _clock(epoch):
    return None if epoch is None else time.strftime(LOCAL_TIME, time.localtime(epoch))


def _returned_models(cell):
    """R90: the returned model id of every solver and selection send (ids only, never a reply)."""
    found = []
    for key in ('sends', 'selection_sends'):
        for send in cell.get(key) or []:
            receipt = send.get('receipt') if isinstance(send, dict) else None
            model = receipt.get('returned_model') if isinstance(receipt, dict) else None
            if isinstance(model, str) and model:
                found.append(model[:64])
    return found


def _project_economy(cell):
    """``_project`` plus R90's ids and hashes: the returned model ids and the first inputs of R67 (system hash, the
    first selection request ``attempts[0]``, the offered program ids, ``public_hash``, ``request_sha256[0]`` when no
    program is offered); never a text."""
    row = _project(cell)
    mount = cell.get('mount') if isinstance(cell.get('mount'), dict) else {}
    selection = mount.get('selection') if isinstance(mount.get('selection'), dict) else {}
    attempts = selection.get('attempts') if isinstance(selection.get('attempts'), list) else []
    offered = [str(x) for x in mount.get('programs_offered') or [] if isinstance(x, str)]
    system = mount.get('system_card_sha256') or cell.get('system_card_sha256')
    public = cell.get('public_hash')
    requests = row['request_sha256']
    row['returned_models'] = _returned_models(cell)
    row['inputs'] = {'system_sha256': system if rp.is_hash(system) else None,
                     'selection_sha256': attempts[0] if attempts and rp.is_hash(attempts[0]) else None,
                     'programs_offered': offered, 'public_hash': public if rp.is_hash(public) else None,
                     'first_request': requests[0] if requests and not offered else None}
    return row


def _load_fresh_unit(unit_dir):
    """{item_id: projected cell} of one fresh unit and its meta: R90's time range (the earliest of every attempt's
    ``started`` and the oldest cell file time, to the latest ``finished`` or cell file time; a killed attempt without
    ``done.json`` still has its cell file times) and the returned model ids with their counts."""
    cells, times = {}, []
    cells_dir = unit_dir / 'cells'
    for path in sorted(cells_dir.glob('*.json')) if cells_dir.is_dir() else []:
        projected = _project_economy(units.read_json(path, allow_sealed=True))
        require(projected['item_id'] not in cells, 'Two cells of one item in ' + unit_dir.name)
        cells[projected['item_id']] = projected
        times.append(path.stat().st_mtime)
    done = _read(unit_dir / 'done.json', allow_sealed=True)
    attempts = [row for row in [done] + [_read(p, allow_sealed=True) for p in sorted(unit_dir.glob('done-stopped-*.json'))]
                if isinstance(row, dict)]
    starts = [t for t in (_epoch(row.get('started')) for row in attempts) if t is not None] + (
        [min(times)] if times else [])
    ends = [t for t in (_epoch(row.get('finished')) for row in attempts) if t is not None] + (
        [max(times)] if times else [])
    models = Counter(model for row in cells.values() for model in row['returned_models'])
    start, finish = (min(starts) if starts else None), (max(ends) if ends else None)
    return cells, {'unit': unit_dir.name, 'done': done is not None, 'stop_reason': (done or {}).get('stop_reason'),
                   'expected_cells': (done or {}).get('expected_cells'), 'cells': len(cells),
                   'attempts': len(attempts), 'start': start, 'finish': finish,
                   'range': [_clock(start), _clock(finish)], 'models': dict(sorted(models.items()))}


class _Phases:
    """R89 on one chain: the recoveries of the state with their outage (pause start, or for a crash the latest
    earlier unit or plan file time) and the owner's ``same_phase`` flag from ``recovery-consumed-<n>.json``."""

    def __init__(self, chain_dir, state):
        self.chain_dir, self._times = Path(chain_dir), None
        found = state.get('recoveries') if isinstance(state, dict) else None
        self.recoveries = [self._recovery(row) for row in found or [] if isinstance(row, dict)]

    def _file_times(self):
        """Modification times of the chain's unit files (cells, done, done-stopped) and plan files (3.2 to 3.4)."""
        if self._times is None:
            found = []
            for folder, _dirs, names in os.walk(self.chain_dir):
                here = Path(folder)
                for name in names:
                    unit_file = (name == 'done.json' or (name.startswith('done-stopped-') and name.endswith('.json'))
                                 or (here.name == 'cells' and name.endswith('.json')))
                    plan_file = ((here == self.chain_dir and name == rp.PLAN_FILE)
                                 or (here.name in (rp.SEALED_DIR, rp.SMOKE_SEALED_DIR, rp.ALIAS_DIR)
                                     and rp.record_kind(name) is not None))
                    if unit_file or plan_file:
                        try:
                            found.append((here / name).stat().st_mtime)
                        except OSError:
                            continue
            self._times = sorted(found)
        return self._times

    def _recovery(self, row):
        n = row.get('n')
        at = _epoch(row.get('at'))
        owner = _read(self.chain_dir / ('recovery-consumed-%d.json' % n)) if type(n) is int else None
        same = isinstance(owner, dict) and owner.get('same_phase') is True
        paused = row.get('paused') if isinstance(row.get('paused'), dict) else None
        if paused is not None:
            start, basis = _epoch(paused.get('at')), 'pause'
        else:   # a crash or a kill records no pause (I-4): bound by the latest earlier unit or plan file
            earlier = [t for t in self._file_times() if at is not None and t < at]
            start, basis = (max(earlier) if earlier else None), 'file_time'
        outage = at - start if at is not None and start is not None else None
        splits = not (same and outage is not None and 0 <= outage <= SPLIT_SECONDS)
        return {'n': n, 'at': _clock(at), 'epoch': at, 'basis': basis,
                'outage_seconds': None if outage is None else round(outage, 1), 'same_phase': same, 'splits': splits}

    def check(self, first, second):
        """R89 for two fresh units' metas: {'same_phase', 'reason', 'recoveries': the numbers that split}."""
        if set(first['models']) != set(second['models']):
            return {'same_phase': False, 'reason': 'model ids differ', 'recoveries': []}
        if None in (first['start'], second['start'], first['finish'], second['finish']):
            return {'same_phase': False, 'reason': 'no time range', 'recoveries': []}
        low, high = min(first['start'], second['start']), max(first['finish'], second['finish'])
        split = [row['n'] for row in self.recoveries
                 if row['splits'] and (row['epoch'] is None or low <= row['epoch'] <= high)]
        return {'same_phase': not split, 'reason': 'recovery' if split else None, 'recoveries': split}

    def export(self):
        return [{key: row[key] for key in ('n', 'at', 'basis', 'outage_seconds', 'same_phase', 'splits')}
                for row in self.recoveries]


def _inputs_complete(inputs):
    return bool(inputs['system_sha256'] and inputs['public_hash']
                and (inputs['first_request'] if not inputs['programs_offered'] else inputs['selection_sha256']))


def _requests_label(first, second):
    """R67 on first inputs per item, never on full send lists: identical | different (d of n items) | unverified."""
    items = sorted(set(first) | set(second))
    differ = unverified = 0
    for item in items:
        a, b = first.get(item), second.get(item)
        if a is None or b is None or not _inputs_complete(a['inputs']) or not _inputs_complete(b['inputs']):
            unverified += 1
        elif a['inputs'] != b['inputs']:
            differ += 1
    label = 'different' if differ else 'unverified' if unverified else 'identical'
    return {'label': label, 'differ': differ, 'unverified': unverified, 'items': len(items),
            'text': 'different (%d of %d items)' % (differ, len(items)) if differ else label}


def _rep(pairs, event, bench):
    pair = pairs[(event, bench)]
    return pair['of'] if pair['source'] in ('fresh', 'alias') else None


def _cell(value, source, of, independent, kind, **extra):
    """R66: the exported grid number."""
    return {'value': value, 'source': source, 'of': of, 'independent': independent, 'kind': kind, **extra}


def _contrast_pairs():
    """The contrasts of typed-v1's ``_pairs``: S<k>-C0, S<k>-C and S<k>-S<k-1> (k >= 2)."""
    out = []
    for k in range(1, len(STEP_EVENTS) + 1):
        out += [('S%d' % k, 'C0'), ('S%d' % k, 'C')] + ([('S%d' % k, 'S%d' % (k - 1))] if k >= 2 else [])
    return out


def _contrast(first, second, bench, ctx):
    """R67, R68: first - second of one bench. One class: ``same_class``, delta null. Two classes: from the two
    representatives' fresh units with the requests label; not same-phase (R89): a reference point value only."""
    pairs, cells, metas = ctx['pairs'], ctx['cells'].get(bench, {}), ctx['metas']
    ra, rb = _rep(pairs, first, bench), _rep(pairs, second, bench)
    out = {'first': first, 'second': second, 'of': [ra, rb], 'independent': False, 'same_class': False,
           'delta': None, 'requests': None, 'same_phase': None, 'reference': None, 'noise_sample': False}
    if ra is None or rb is None:
        return {**out, 'status': pairs[(first if ra is None else second, bench)]['source']}
    if ra == rb:
        return {**out, 'status': 'same_class', 'same_class': True}
    if ra not in cells or rb not in cells:
        return {**out, 'status': 'pending'}
    items = sorted(set(cells[ra]) & set(cells[rb]))
    label = _requests_label(cells[ra], cells[rb])
    phase = ctx['phases'].check(metas[(ra, bench)], metas[(rb, bench)])
    out.update(requests=label, same_phase=phase['same_phase'])
    if not phase['same_phase']:
        return {**out, 'status': 'split', 'reference': {
            'point_points': _paired(cells[ra], cells[rb], items)['mean_points'], 'reason': phase['reason'],
            'recoveries': phase['recoveries'], 'ranges': {ra: metas[(ra, bench)]['range'],
                                                          rb: metas[(rb, bench)]['range']},
            'models': {ra: metas[(ra, bench)]['models'], rb: metas[(rb, bench)]['models']}}}
    return {**out, 'status': 'measured', 'delta': _paired(cells[ra], cells[rb], items),
            'independent': (first, second) == (ra, rb), 'noise_sample': label['label'] == 'identical'}


def _contrast_cell(contrast):
    """A contrast as a grid number (R66): measured value, or null with kind same_class / split / none."""
    if contrast is None:
        return _cell(None, 'pending', None, False, 'none')
    status = contrast['status']
    source = 'fresh' if contrast['of'] == [contrast['first'], contrast['second']] else 'alias'
    if status == 'measured':
        return _cell(contrast['delta']['mean_points'], source, contrast['of'], contrast['independent'], 'measured',
                     requests=contrast['requests']['text'])
    if status == 'same_class':
        return _cell(None, source, contrast['of'], False, 'same_class')
    if status == 'split':
        return _cell(None, source, contrast['of'], False, 'split', reference=contrast['reference']['point_points'],
                     recoveries=contrast['reference']['recoveries'], reason=contrast['reference']['reason'])
    return _cell(None, status if status in PAIR_SOURCES else 'pending', None, False, 'none')


def _mark(pair):
    """A reading cell of the event grid without its value: fresh, or an alias with its representative's counts."""
    kind = 'measured' if pair['source'] == 'fresh' else 'alias' if pair['source'] == 'alias' else 'none'
    return {'source': pair['source'], 'of': pair['of'], 'independent': pair['independent'], 'kind': kind,
            'counts': pair.get('counts'), 'class': pair.get('class'), 'reason': pair.get('reason')}


def _same_request_noise_fresh(c0, c):
    """R69: C vs C0 on fresh units only, on the items whose first inputs are identical (E1)."""
    if c0 is None or c is None:
        return None
    items = sorted(set(c0) & set(c))
    unverified = [i for i in items if not _inputs_complete(c0[i]['inputs']) or not _inputs_complete(c[i]['inputs'])]
    identical = [i for i in items if i not in unverified and c0[i]['inputs'] == c[i]['inputs']]
    noise = gates.noise_threshold([(i, c0[i]['correct'], c[i]['correct']) for i in identical]) if identical else None
    return {'items_common': len(items), 'identical_requests': len(identical),
            'differing_requests': len(items) - len(identical) - len(unverified), 'missing_request_sha': len(unverified),
            'noise': {key: noise.get(key) for key in NOISE_KEYS} if noise else None, 'compared_on': 'first inputs'}


def _panel_economy(bench, ctx):
    """One bench under economy: fresh units under their own event only (R64), the marks of all seven events, the
    contrasts of R67 and the bench's in-run replicate count (R69)."""
    cells = ctx['cells'].get(bench, {})
    events = [event for event in READ_ARMS if event in cells]
    common = sorted(set.intersection(*(set(cells[event]) for event in events))) if events else []
    contrasts = {'%s-%s' % names: _contrast(*names, bench, ctx) for names in _contrast_pairs()}
    replicates = {frozenset(c['of']) for c in contrasts.values() if c['status'] == 'measured' and c['noise_sample']}
    fresh = lambda event: cells.get(event) if ctx['pairs'][(event, bench)]['source'] == 'fresh' else None
    return {'events': events, 'items_common': len(common),
            'items_by_event': {event: len(cells[event]) for event in events},
            'marks': {event: _mark(ctx['pairs'][(event, bench)]) for event in READ_ARMS},
            'per_event': {event: _event_summary(cells[event], common) for event in events},
            'contrasts': contrasts, 'in_run_replicates': len(replicates),
            'same_request_noise': _same_request_noise_fresh(fresh('C0'), fresh('C')),
            'units': {event: ctx['metas'][(event, bench)] for event in events}}


def _acc_cell(panels, pairs, event, bench, side):
    pair = pairs[(event, bench)]
    panel = panels.get(bench) or {}
    if pair['source'] == 'fresh' and event in panel.get('per_event', {}):
        return _cell(panel['per_event'][event]['accuracy'][side], 'fresh', event, True, 'measured')
    if pair['source'] == 'alias':
        return _cell(None, 'alias', pair['of'], False, 'alias', counts=pair.get('counts'))
    return _cell(None, pair['source'] if pair['source'] != 'fresh' else 'pending', None, False, 'none')


def _diff_cell(panels, pairs, first, second, bench):
    """A 5x5 difference cell. Two events of one class give ``-`` (same requests, not measured) whatever the row's
    source; otherwise an alias row shows its representative (=X) and no number of its own (R66), carrying the contrast
    cell it stands for (``shown``: the representatives' value, kind and requests label), so it prints what X's own
    row prints: a value, ``split`` or a noise sample (fix-c, rc-readout-2 and -4)."""
    cell = _contrast_cell(((panels.get(bench) or {}).get('contrasts') or {}).get('%s-%s' % (first, second)))
    pair = pairs[(first, bench)]
    if pair['source'] == 'alias' and cell['kind'] != 'same_class':
        return _cell(None, 'alias', pair['of'], False, 'alias', counts=pair.get('counts'), shown=cell)
    return cell


def _five_by_five_economy(panels, pairs, home_steps, n_steps):
    evolved = {k: bench for bench, k in home_steps.items()}
    rows = {}
    for k in range(1, n_steps + 1):
        event = 'S%d' % k
        rows[event] = {'step': k, 'evolved_bench': evolved.get(k),
                       'diff_points_vs_C0': {b: _diff_cell(panels, pairs, event, 'C0', b) for b in ORDER},
                       'diff_points_vs_C': {b: _diff_cell(panels, pairs, event, 'C', b) for b in ORDER},
                       'accuracy_L': {b: _acc_cell(panels, pairs, event, b, 'L') for b in ORDER},
                       'accuracy_H': {b: _acc_cell(panels, pairs, event, b, 'H') for b in ORDER}}
    return rows


def _term(ctx, bench, first, second, side):
    """A continual-learning term acc(first) - acc(second) through the resolver (R70): structural 0 inside one class,
    a split pair a reference value only, two same-phase fresh units whose requests are identical on every item (R67)
    a noise sample, not an effect (kind ``noise_sample``: no value of its own, its reading as ``reference``; by
    construction 0, as a structural term; fix-c, rc-readout-2), else the representatives' measured difference."""
    pairs, panel = ctx['pairs'], ctx['panels'].get(bench) or {}
    ra, rb = _rep(pairs, first, bench), _rep(pairs, second, bench)
    if ra is None or rb is None:
        return _cell(None, 'pending', [ra, rb], False, 'none')
    source = 'fresh' if (ra, rb) == (first, second) else 'alias'
    if ra == rb:
        return _cell(0.0, source, [ra, rb], False, 'structural')
    per_event = panel.get('per_event') or {}
    if ra not in per_event or rb not in per_event:
        return _cell(None, 'pending', [ra, rb], False, 'none')
    x, y = per_event[ra]['accuracy'][side], per_event[rb]['accuracy'][side]
    value = None if x is None or y is None else x - y
    phase = ctx['phases'].check(ctx['metas'][(ra, bench)], ctx['metas'][(rb, bench)])
    if not phase['same_phase']:
        return _cell(None, source, [ra, rb], False, 'split', reference=value, recoveries=phase['recoveries'],
                     reason=phase['reason'])
    cells = ctx['cells'].get(bench) or {}
    if value is not None and _requests_label(cells.get(ra) or {}, cells.get(rb) or {})['label'] == 'identical':
        return _cell(None, source, [ra, rb], False, 'noise_sample', reference=value, requests='identical')
    return _cell(value, source, [ra, rb], (ra, rb) == (first, second), 'measured')


def _rp4(ctx, bench, events, final, side):
    """RP4 with the split rule of R70 for forgetting / forgetting_after_home over ``events`` (the earlier events).
    An earlier event with the final event's requests is a by-construction term that never enters the maximum: its
    class (``structural_terms``) or a fresh unit whose requests are identical on every item (``noise_terms``, a noise
    sample with its reading beside; fix-c, rc-readout-2). An earlier event without a reading (pending, invalid,
    void_alias) leaves the maximum undefined: kind ``incomplete``, the maximum of the others as ``partial``, the
    missing events listed (fix-c, rc-readout-5)."""
    if not events:
        return None
    rf = _rep(ctx['pairs'], final, bench)
    if rf is None or rf not in ((ctx['panels'].get(bench) or {}).get('per_event') or {}):
        return _cell(None, 'pending', None, False, 'none')
    structural = [e for e in events if _rep(ctx['pairs'], e, bench) == rf]
    measured, split, noise, missing = [], [], [], []
    for event in events:
        if event in structural:
            continue
        term = _term(ctx, bench, event, final, side)
        if term['kind'] == 'measured' and term['value'] is not None:
            measured.append((event, term))
        elif term['kind'] == 'noise_sample':
            noise.append({'event': event, 'of': term['of'], 'reference': term['reference'], 'source': term['source']})
        elif term['kind'] == 'split':
            split.append({'event': event, 'of': term['of'], 'reference': term['reference'],
                          'recoveries': term['recoveries'], 'reason': term['reason']})
        else:
            missing.append({'event': event, 'source': ctx['pairs'][(event, bench)]['source']})
    extra = {'structural_terms': len(structural), 'noise_terms': noise, 'split_terms': split, 'missing_terms': missing}
    best = max(measured, key=lambda row: row[1]['value']) if measured else None
    source = 'alias' if structural or any(t['source'] == 'alias' for _, t in measured) or any(
        row['source'] == 'alias' for row in noise) else 'fresh'
    if missing:
        return _cell(None, source, None, False, 'incomplete', partial=best[1]['value'] if best is not None else None,
                     **extra)
    if best is None and split:
        return _cell(None, source, None, False, 'split', note='split only', **extra)
    if structural or noise:
        if best is not None and best[1]['value'] > 0:
            return _cell(best[1]['value'], source, best[1]['of'], False, 'measured', **extra)
        return _cell(0.0, source, [rf, rf], False, 'structural',
                     other_max=best[1]['value'] if best is not None else None, **extra)
    if best is None:
        return _cell(None, 'pending', None, False, 'none', **extra)
    return _cell(best[1]['value'], source, best[1]['of'], False, 'measured', **extra)


def _bench_metrics_economy(ctx, bench, k_home, n_steps, base_event='C0'):
    """The per-bench terms. S0 := ``base_event``, the start of learning: C under base 'historical' (addendum D17),
    C0 under 'format' (fix-c, rc-readout-1), so forward transfer and the plasticity of the first step never carry the
    hand card's own gain over C0; gain_over_C0 and gain_over_C keep both rows."""
    final = 'S%d' % n_steps
    step = lambda k: base_event if k == 0 else 'S%d' % k
    panel = ctx['panels'][bench]
    out = {'home_step': k_home, 'n': panel['items_common'], 'final_event': final, 'S0': base_event}
    for side in SIDES:
        out[side] = {
            'final': _acc_cell(ctx['panels'], ctx['pairs'], final, bench, side),
            'C0': _acc_cell(ctx['panels'], ctx['pairs'], 'C0', bench, side),
            'C': _acc_cell(ctx['panels'], ctx['pairs'], 'C', bench, side),
            'gain_over_C0': _term(ctx, bench, final, 'C0', side),
            'gain_over_C': _term(ctx, bench, final, 'C', side),
            'forgetting': _rp4(ctx, bench, [step(k) for k in range(1, n_steps)], final, side),
            'forgetting_after_home': _rp4(ctx, bench, [step(k) for k in range(k_home, n_steps)], final, side),
            'backward_transfer': _term(ctx, bench, final, step(k_home), side) if k_home < n_steps else None,
            'forward_transfer': _term(ctx, bench, step(k_home - 1), step(0), side) if k_home >= 2 else None,
            'plasticity': _term(ctx, bench, step(k_home), step(k_home - 1), side)}
    return out


def _macro_terms(terms):
    """R70's two columns over the per-bench terms (None = undefined for that bench). A noise sample (identical
    requests, fix-c, rc-readout-2) is a by-construction 0 like a structural term: entered as 0 in (a), never in (b),
    and counted apart; an incomplete maximum (a missing earlier reading, rc-readout-5) is counted as pending."""
    defined = [t for t in terms if t is not None and t['kind'] in ('measured', 'structural', 'noise_sample', 'split')]
    measured = [t for t in defined if t['kind'] == 'measured']
    structural = [t for t in defined if t['kind'] == 'structural']
    noise = [t for t in defined if t['kind'] == 'noise_sample']
    split = [t for t in defined if t['kind'] == 'split']
    base = {'source': 'macro', 'of': None, 'independent': False, 'benches': len(defined),
            'pending': sum(1 for t in terms if t is not None and t['kind'] in ('none', 'incomplete'))}
    if noise:
        base['noise_samples'] = len(noise)
    if split:
        text = 'mixed: %d same-phase, %d split, no mean' % (len(measured), len(split))
        return {'a': {**base, 'value': None, 'kind': 'mixed', 'text': text, 'structural': len(structural)},
                'b': {**base, 'value': None, 'kind': 'mixed', 'text': text, 'n': len(measured)}}
    a = [t['value'] for t in measured] + [0.0] * (len(structural) + len(noise))
    return {'a': {**base, 'value': sum(a) / len(a) if a else None, 'kind': 'macro_a', 'structural': len(structural)},
            'b': {**base, 'value': sum(t['value'] for t in measured) / len(measured) if measured else None,
                  'kind': 'macro_b', 'n': len(measured)}}


def _macro_level(ctx, side, event):
    """The mean reading of an event over the benches, each read through its representative on purpose."""
    values, aliased = [], 0
    for bench, panel in ctx['panels'].items():
        rep = _rep(ctx['pairs'], event, bench)
        value = (panel['per_event'].get(rep) or {}).get('accuracy', {}).get(side) if rep else None
        if value is not None:
            values.append(value)
            aliased += rep != event
    mean = sum(values) / len(values) if values else None
    row = {'value': mean, 'source': 'macro', 'of': None, 'independent': False, 'kind': 'mean', 'n': len(values),
           'aliased': aliased}
    return {'a': dict(row), 'b': dict(row)}


def _cl_economy(ctx, home_steps, n_steps, base_event='C0'):
    per_bench = {bench: _bench_metrics_economy(ctx, bench, home_steps[bench], n_steps, base_event)
                 for bench in ORDER if bench in ctx['panels'] and bench in home_steps}
    final = 'S%d' % n_steps
    macro = {}
    for side in SIDES:
        macro[side] = {key: _macro_level(ctx, side, {'final': final}.get(key, key)) for key in LEVEL_KEYS}
        macro[side].update({key: _macro_terms([m[side][key] for m in per_bench.values()]) for key in DIFF_KEYS})
    return {'definitions': {**ECONOMY_DEFINITIONS, 'final': 'acc(%s)' % final, 'S0': base_event,
                            'formulas': ('as in the module docstring with S0 := %s (the start of learning: C under '
                                         'base historical, C0 under format), each term through the resolver'
                                         % base_event)},
            'final_event': final, 'home_steps': dict(home_steps), 'per_bench': per_bench, 'macro': macro}


def _bench_types(steps, k, pools):
    """{bench: type id in s<k>/typemap.json} through each bench's practice source id (None: no source yet)."""
    typemap = (steps.get(k) or {}).get('typemap') or {}
    owner = {sid: tid for tid, row in (typemap.get('types') or {}).items() for sid in row.get('sources') or []}
    out = {}
    for bench, pin in (pools or {}).items():
        if isinstance(pin, dict) and pin:
            pin = {key: pin[key] for key in ('path', 'sha256') if key in pin} or dict(pin)
            out[bench] = owner.get(source_id(pin))
    return out


def _routed_into(ctx, event, bench, home_type):
    """(n, N): how many of the N panel items of the fresh unit that stands for (event, bench) -- its own, or its
    representative's, which sends the same requests -- were routed into ``home_type`` (``mount.type`` of its cells);
    None when no fresh unit stands for the pair (pending, invalid, void_alias)."""
    rep = _rep(ctx['pairs'], event, bench)
    found = (ctx['cells'].get(bench) or {}).get(rep) if rep is not None else None
    if not found:
        return None
    return sum(1 for row in found.values() if row['mount']['type'] == home_type), len(found)


def _generalization(ctx, steps, home_steps, n_steps, base_event, pools):
    """The compact generalization view: per step k and bench, S<k> minus the previous state (S0 = the base row),
    with the bench's relation to the step's home bench: home; same-type (its source is in the home type); routed (its
    source is not, but its panel items were routed into the home type, so the step's skills reach them: a bench not
    learned yet with the home bench's signature, or an earlier bench routed into the type, RP15; fix-c,
    rc-readout-3), with the routed share n/N; else other-type. Informational: it decides nothing."""
    evolved = {k: bench for bench, k in home_steps.items()}
    rows = {}
    for k in range(1, n_steps + 1):
        event, previous = 'S%d' % k, ('S%d' % (k - 1) if k >= 2 else base_event)
        home, types = evolved.get(k), _bench_types(steps, k, pools)
        home_type = types.get(home)
        cells = {}
        for bench in ORDER:
            routed = None
            if bench == home:
                relation = 'home'
            elif home_type is None:
                relation = 'type unknown'
            elif types.get(bench) == home_type:
                relation = 'same-type'
            else:
                routed = _routed_into(ctx, event, bench, home_type)
                relation = 'routed' if routed is not None and routed[0] else 'other-type'
            cells[bench] = {**_contrast_cell(_contrast(event, previous, bench, ctx)), 'relation': relation,
                            **({'routed_items': routed[0], 'items': routed[1]} if routed is not None else {})}
        rows[event] = {'step': k, 'home_bench': home, 'home_type': home_type, 'previous': previous, 'cells': cells}
    return rows


def _gate_noise(steps):
    """RP7: the practice-side gate noise of each step (``s<k>/noise.json``), shown beside the read tables."""
    return {k: {'se_points': (step.get('noise') or {}).get('se_points'),
                'tau_points': (step.get('noise') or {}).get('tau_points')}
            for k, step in sorted(steps.items()) if k >= 1 and step.get('noise')}


def _open_economy(root, chain_dir, steps, order, resolved, state, base_card):
    """The sealed reads opened under economy: fresh units only (R64, R71), marks, contrasts with the same-phase
    rule, the 5x5 and CL objects (R66, R70), the reference block, the generalization view, the mount check over
    fresh units with the aliases' planned columns (R72). A plan that fails renders no read table (R74)."""
    if resolved['error'] is not None:
        return {'read_plan_error': resolved['error']}
    pairs, cells, metas, not_loaded = resolved['pairs'], {}, {}, []
    for (event, bench), unit_dir in read_units_of(chain_dir).items():
        if pairs[(event, bench)]['source'] != 'fresh':
            not_loaded.append('%s-%s' % (event, bench))   # R64: never loaded for an alias or unsettled pair
            continue
        found, meta = _load_fresh_unit(unit_dir)
        cells.setdefault(bench, {})[event] = found
        metas[(event, bench)] = meta
    ctx = {'pairs': pairs, 'cells': cells, 'metas': metas, 'phases': _Phases(chain_dir, state), 'panels': {}}
    ctx['panels'] = panels = {bench: _panel_economy(bench, ctx) for bench in ORDER if bench in cells}
    home = _home_steps(steps, order)
    n_steps = len(order)
    reads = {(event, bench): panel['per_event'][event] for bench, panel in panels.items() for event in panel['events']}
    reference = {}   # R67: one row per split pair of representatives, with every contrast name that maps to it
    for bench, panel in panels.items():
        for name, contrast in panel['contrasts'].items():
            if contrast['status'] == 'split':
                row = reference.setdefault((bench, tuple(contrast['of'])), {
                    'bench': bench, 'contrasts': [], 'of': contrast['of'], **contrast['reference']})
                row['contrasts'].append(name)
    reference = list(reference.values())
    manifest = _read(Path(root) / 'manifest.json')
    pools = manifest.get('pools') if isinstance(manifest, dict) and isinstance(manifest.get('pools'), dict) else {}
    mount = _open_mount_check(reads, steps)
    mount.update(planned=_planned_mount(resolved), scope='fresh units only (R72); alias rows are planned')
    base_event = BASE_EVENTS.get(base_card, 'C0')   # S0, the start of learning (addendum D17; fix-c, rc-readout-1)
    return {'read_units': {'%s-%s' % key: meta for key, meta in metas.items()}, 'not_loaded': sorted(not_loaded),
            'panels': panels, 'five_by_five': _five_by_five_economy(panels, pairs, home, n_steps),
            'cl_metrics': _cl_economy(ctx, home, n_steps, base_event), 'reference': reference,
            'generalization': _generalization(ctx, steps, home, n_steps, base_event, pools),
            'in_run_replicates': {**{bench: panel['in_run_replicates'] for bench, panel in panels.items()},
                                  'total': sum(panel['in_run_replicates'] for panel in panels.values())},
            'gate_noise': _gate_noise(steps), 'recoveries': ctx['phases'].export(), 'mount_check': mount,
            'read_tokens': {'%s-%s' % key: value['tokens'] for key, value in reads.items()}}


# ---- documents ---------------------------------------------------------------------------------------------------
def _own(root):
    """The version guard of every public entry (Codex review round 1, finding 4): ``prepare.own_root`` refuses a root,
    manifest or chain state of another typed version before anything is read or written, as the CLI already does."""
    from .prepare import own_root   # lazy: prepare imports the route-B machinery, a readout needs it only here
    own_root(root)
    return Path(root)


def chain_readout(root, chain, *, open_sealed=False, stamp=None, order=ORDER):
    """One chain's readout document (closed, or opened when ``open_sealed``). ``order``: the chain's bench order
    (``ORDER``; a shortened test chain names its own), which fixes the final event and the rows of the 5x5."""
    root = _own(root)
    chain_dir = root / chain
    require(chain_dir.is_dir(), 'No chain directory: ' + str(chain_dir))
    require(isinstance(order, (list, tuple)) and order and set(order) <= set(ORDER), 'A bench order within ORDER')
    ledger = _read(chain_dir / 'ledger.json')
    confirm = _read(chain_dir / 'confirm.json')
    state = _read(chain_dir / 'state.json')
    steps = {k: _step(path, k, order) for k, path in _step_dirs(chain_dir).items()}
    mirrors = _mirrors(chain_dir)
    doc = {'version': READOUT_VERSION, 'chain': chain, 'root': str(root), 'mode': 'open' if open_sealed else 'closed',
           'generated_utc': stamp or _stamp(), 'order': list(order),
           'state': _scrub(state) if isinstance(state, dict) else state,
           'ledger': _ledger_totals(ledger), 'costs': _costs(ledger),
           'confirm': _scrub(confirm) if isinstance(confirm, dict) else confirm, 'steps': steps,
           'read_status': mirrors, 'mount_check': _closed_mount_check(mirrors), 'disclaimer': DISCLAIMER,
           'base_card': state.get('base_card') if isinstance(state, dict) else None}
    anchors = _anchors_of(state)   # typed-v3 T2: named in the document only when C0 is not read
    if anchors != rp.READ_ANCHORS_DEFAULT:
        doc['read_anchors'] = list(anchors)
    resolved = _resolve_chain(chain_dir, state)
    if resolved['mode'] == ECONOMY:   # a full root (typed-v1 included) keeps exactly the document above
        doc.update(_economy_closed(chain_dir, resolved, state, mirrors))
        doc['mount_check'] = {**doc['mount_check'], 'planned': doc['planned_mount'],
                              'scope': 'fresh read-status mirrors only (R65); alias rows are planned'}
    if open_sealed:
        if resolved['mode'] == ECONOMY:
            doc.update(_open_economy(root, chain_dir, steps, order, resolved, state, doc['base_card']))
        else:
            doc.update(_open(chain_dir, steps, order) if anchors == rp.READ_ANCHORS_DEFAULT
                       else _open_c(chain_dir, steps, order))   # typed-v3 T2: no C0 read
    return doc


def _stamp(now=None):
    return time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(now))


def _write_text(path, text):
    path = units.checked_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


def build(root, *, open_sealed=False, out=None, now=None, order=ORDER):
    """Readout of every chain found under ``root``, written once to ``<root>/readout/<UTC stamp>/`` (or ``out``)
    as ``readout-<chain>.json`` and ``.md``; returns the documents and the paths."""
    root = _own(root)
    require(root.is_dir(), 'Run root must exist: ' + str(root))
    chains = chains_of(root)
    require(chains, 'No chain directory (G/D) under ' + str(root))
    clock = time.time() if now is None else now
    stamp = _stamp(clock)
    out_dir = Path(out) if out is not None else root / 'readout' / stamp
    while out is None and now is None and out_dir.exists():  # back-to-back readouts take the next free second
        clock += 1
        stamp = _stamp(clock)
        out_dir = root / 'readout' / stamp
    require(not out_dir.exists(), 'A readout goes to a new directory: ' + str(out_dir))
    docs = {chain: chain_readout(root, chain, open_sealed=open_sealed, stamp=stamp, order=order) for chain in chains}
    written = {}
    for chain, doc in docs.items():
        json_path, md_path = out_dir / ('readout-%s.json' % chain), out_dir / ('readout-%s.md' % chain)
        units.write_json(json_path, doc)
        _write_text(md_path, markdown(doc))
        written[chain] = {'json': str(json_path), 'markdown': str(md_path)}
    return {'version': READOUT_VERSION, 'root': str(root), 'mode': 'open' if open_sealed else 'closed',
            'generated_utc': stamp, 'out': str(out_dir), 'chains': docs, 'written': written}


def status(root, *, chains=None):
    """Counts only, no sealed access: per chain the state, the ledger totals and the open read mirrors, with the
    schedule, the phase ('learn' / 'read', None before the first unit and at completion) and the current unit
    (``read-<event>`` during a read event) at the top (DESIGN 3.6, schedule-lock S10; under 'learn_first' steps 1..5
    without any mirror are normal until reading begins); the run's sealed ``memory_lock`` from the open manifest
    (None without one)."""
    root = _own(root)
    out = {}
    for chain in chains or chains_of(root):
        chain_dir = root / chain
        state = _read(chain_dir / 'state.json')
        found = state if isinstance(state, dict) else {}
        out[chain] = {'state': _scrub(state) if isinstance(state, dict) else state,
                      'schedule': found.get('schedule'), 'phase': found.get('phase'),
                      'current_unit': found.get('current_unit'),
                      'ledger': _ledger_totals(_read(chain_dir / 'ledger.json')),
                      'steps_present': sorted(_step_dirs(chain_dir)), 'read_status': _mirrors(chain_dir)}
        mode = read_plan_mode(found)   # R73: the read plan's mode, short plan hash and read counts
        out[chain]['read_plan'] = {'mode': mode, 'plan_sha256': _short(_plan_info(found).get('plan_sha256'))}
        if _anchors_of(found) != rp.READ_ANCHORS_DEFAULT:   # typed-v3 T2: the planned events, C0 not among them
            out[chain]['read_plan']['read_events'] = list(rp.read_events(_anchors_of(found)))
        if mode == ECONOMY:
            resolved = _resolve_chain(chain_dir, found)
            out[chain]['read_plan'].update(error=resolved['error'], void=resolved['void'])
            out[chain]['reads'] = read_counts(resolved, found)
    manifest = _read(root / 'manifest.json')
    return {'root': str(root), 'mode': 'closed',
            'memory_lock': manifest.get('memory_lock') if isinstance(manifest, dict) else None, 'chains': out}


# ---- markdown ----------------------------------------------------------------------------------------------------
def _pct(value):
    return '—' if value is None else '%.1f' % (100 * value)


def _pts(value):
    return '—' if value is None else '%+.1f' % value


def _num(value):
    return '—' if value is None else str(value)


def _table(header, rows):
    lines = ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    lines += ['| ' + ' | '.join(str(cell) for cell in row) + ' |' for row in rows]
    return '\n'.join(lines)


def chain_status(state):
    """'complete' | 'paused' | 'running' | 'unknown' from a chain state (``chain.run`` records ``complete`` and
    ``paused``; an explicit ``status`` wins when a state carries one)."""
    if not isinstance(state, dict):
        return 'unknown'
    if state.get('status'):
        return str(state['status'])
    if state.get('complete') is True:
        return 'complete'
    return 'paused' if state.get('paused') else 'running'


def _md_state(doc):
    state = doc.get('state') or {}
    paused = state.get('paused') or {}
    ledger = doc.get('ledger') or {}
    lines = ['## Chain state', '',
             '- status: %s; step: %s; paused: %s' % (chain_status(state), state.get('step', state.get('current_step')),
                                                       paused.get('reason') if paused else 'no'),
             '- schedule: %s; phase: %s; current unit: %s' % (state.get('schedule') or 'not recorded',
                                                                state.get('phase') or '—',
                                                                state.get('current_unit') or '—'),
             '- done units: %s' % len(state.get('done') or state.get('done_units') or []),
             '- ledger: cap %s, charged %s, reported %s, sends %s, missing usage %s, stopped %s (%s), infra streak %s' % tuple(
                 _num(ledger.get(key)) for key in LEDGER_KEYS)]
    if state.get('schedule') == 'learn_first' and state.get('phase') != 'read' and chain_status(state) != 'complete':
        lines.append('- learn_first: all steps are learned and frozen before the first read event; no read mirror yet '
                     'is normal')
    if doc.get('read_plan'):   # economy only: a full root keeps the lines above unchanged (R73)
        plan, reads = doc['read_plan'], doc.get('economy') or {}
        lines.append('- read plan: economy; plan %s%s; reads settled %s of %s (fresh done %s of %s planned, aliases %s, '
                     'fallbacks %s, voided aliases %s, pending %s, invalid %s)' % (
                         plan.get('plan_sha256') or 'not bound', '; VOID (%s)' % plan.get('void_reason')
                         if plan.get('void') else '', *[_num(reads.get(key)) for key in (
                             'settled', 'of', 'fresh_done', 'fresh_planned', 'alias', 'fallbacks', 'void_aliases',
                             'pending', 'invalid')]))
    costs = doc.get('costs') or {}
    if costs:
        lines += ['', _table(['part', 'units', 'charged tokens', 'reported tokens'],
                             [[part, costs[part]['count'], costs[part]['charged'], costs[part]['reported']]
                              for part in ('learning_units', 'read_units')])]
    if doc.get('read_plan'):   # R71: the ledger holds fresh units only; no "tokens saved" figure
        reads = doc.get('economy') or {}
        lines += ['', '- economy: %s pairs aliased, %s fallbacks, %s voided aliases (read tokens: fresh units only)' % (
            _num(reads.get('alias')), _num(reads.get('fallbacks')), _num(reads.get('void_aliases')))]
    return lines


def _md_step(step):
    lines = ['### Step %d (%s)' % (step['step'], step.get('bench'))]
    noise = step.get('noise')
    lines.append('- noise tau: %s' % ('%s points (SE %.2f, %s runs per item, n %s, mixed items %s, model-side unknown '
                                       'runs %s, re-runs %s)' % (
        _num(noise['tau_points']), noise['se_points'] or 0.0, _num(noise['repeats']), _num(noise['n']),
        _num(noise['mixed_items']), _num(noise['unknown_final']), _num(noise['reruns'])) if noise else 'not recorded'))
    if step['decisions']:
        # a program row also shows its two informational SEs on the fired items (addendum, "Program gate on the
        # items where the program fired": reports compare the fired gain with both; fix-b, review rb-stats 2)
        lines += ['', _table(['decision', 'kind', 'accepted', 'reason', 'n', 'R', 'fired n', 'mean pts',
                              'better/worse/tied', 'whole-slice pts', 'SE pts', 'SE fired pts', 'SE scaled pts', 'tau',
                              'baseline'],
                             [[d['label'], d['kind'], d['accepted'],
                               d['reason'] if not d.get('member_harm') else '%s (%s)' % (d['reason'], d['member_harm']),
                               _num(d['n']), _num(d.get('repeats')),
                               _num(d.get('fired_n')), _pts(d['mean_points']),
                               '%s/%s/%s' % (_num(d['better']), _num(d['worse']), _num(d['tied'])),
                               _pts(d.get('whole_slice_mean_points')), _num(d.get('se_points')),
                               _num(d.get('se_points_fired')), _num(d.get('se_points_scaled')), _num(d['tau_points']),
                               '%s%s' % (_num(d.get('baseline')), ' (selected)' if d.get('baseline_selected') else '')]
                              for d in step['decisions']])]
        lines += _md_related(step['decisions'])
    else:
        lines.append('- gate decisions: none recorded')
    lines += _md_typed_v3(step.get('typed_v3'))
    library = step.get('library')
    if library:
        lines += ['', 'Library after the step:', '',
                  _table(['skill id', 'name', 'kind', 'home type', 'origin step', 'retired', 'description'],
                         [[s['skill_id'], s['name'], s['kind'], s['home_type'], _num(s['origin_step']),
                           _num(s['retired_at_step']), (s['description'] or '').replace('|', '/').replace('\n', ' ')]
                          for s in library])]
    else:
        lines.append('- library: %s' % ('empty' if library == [] else 'not frozen'))
    typemap = step.get('typemap')
    if typemap:
        lines += ['', 'Type map:', '', _table(['type', 'signature', 'sources', 'card', 'programs'],
                                                [[tid, t['signature'], ', '.join(t['sources']), _num(t['card']),
                                                  ', '.join(t['programs']) or '—'] for tid, t in typemap['types'].items()])]
    if step['units']:
        lines += ['', _table(['learning unit', 'cells', 'expected', 'stop', 'tokens', 'unknown', 'infra unknown', 'config errors'],
                             [[u['unit'], u['cells'], _num(u['expected_cells']), _num(u['stop_reason']), u['tokens'],
                               u['unknown'], u['infrastructure_unknown'], u['configuration_error']]
                              for u in step['units'].values()])]
    return lines


def _candidate_label(row):
    if row['kind'] == 'card':
        return 'card r%s' % _num(row['round'])
    return 'archive (program 0)' if row['kind'] == 'archive' else 'program %s' % _num(row['candidate'])


def _class_points(row, name):
    found = ((row.get('by_class') or {}).get(name) or {}) if isinstance(row.get('by_class'), dict) else {}
    return _pts(found.get('gain_points'))


def _md_typed_v3(block):
    """The typed-v3 part of a step (brief P3b C): the item stage, the gate rule, every candidate's numbers on E, its
    screen, its gains by item class, the repair history of the programs, and the archive package apart (T9)."""
    if not block:
        return []
    lines = []
    items = block.get('items')
    if items:
        counts, gate = items.get('counts') or {}, items.get('gate') or {}
        judging, shown = counts.get('judging') or {}, counts.get('shown') or {}
        lines += ['', 'Item stage (CHAIN-DECISIONS T3 to T5): %s' % (
            'no item made (%s): J = R' % items['reason'] if items.get('reason') else 'items made after the diagnosis'),
            '- gate list J: real %s, attack %s, guard %s, calibration %s (total %s); shown attack %s, guard %s; replaced '
            '%s, unused %s' % (_num(gate.get('real')), _num(judging.get('attack')), _num(judging.get('guard')),
                               _num(judging.get('calibration')), _num(gate.get('total')), _num(shown.get('attack')),
                               _num(shown.get('guard')), _num(counts.get('replaced')), _num(counts.get('unused')))]
        for plan in items.get('plans') or []:
            lines.append('- plan round %s: %s, %s weaknesses kept, %s guards' % (
                _num(plan.get('round')), 'unreadable' if plan.get('unreadable') else plan.get('status'),
                _num(plan.get('kept')), _num(plan.get('guards'))))
        for check in items.get('checks') or []:
            attack, calibration = check.get('attack') or {}, check.get('calibration') or {}
            lines.append('- check round %s (B once): attack %s of %s right, calibration %s of %s right, difference %s '
                         'points: %s' % (_num(check.get('round')), _num(attack.get('pass')), _num(attack.get('n')),
                                         _num(calibration.get('pass')), _num(calibration.get('n')),
                                         _num((check.get('difference_points') or {}).get('points')),
                                         'holds' if check.get('holds') else 'does not hold (%s)' % check.get('reason')))
    rule = block.get('gate_rule')
    if rule:
        lines.append('- gate rule: %s; cards of this step decided %s; screen: %s' % (
            rule.get('rule'), 'on E = R + A (%s of the %s items of J; tau from the baseline\'s repeats on E)' % (
                _num(rule.get('evolution_items')), _num(rule.get('gate_items'))) if rule.get('card_rule') == 'evolution'
            else 'on the whole list J (%s items: no made item)' % _num(rule.get('gate_items')),
            'once on A + G before every gate (%s attack, %s guard items)' % (
                _num((rule.get('screen_items') or {}).get('attack')), _num((rule.get('screen_items') or {}).get('guard')))
            if rule.get('screened') else 'none on this step'))
    rows = block.get('candidates') or []
    if rows:
        lines += ['', _table(['candidate', 'accepted', 'reason', 'E n', 'E gain pts', 'E tau', 'E better/worse/tied',
                              'screen b / c (R x items)', 'screen fired', 'real pts', 'attack pts', 'guard pts',
                              'calibration pts', 'B parity pts'],
                             [[_candidate_label(row), row['accepted'], row['reason']]
                              + ([_num(row['evolution']['n']), _pts(row['evolution']['gain_points']),
                                  _num(row['evolution']['tau_points']), '%s/%s/%s' % tuple(
                                      _num(row['evolution'][key]) for key in ('better', 'worse', 'tied'))]
                                 if row.get('evolution') else ['—'] * 4)
                              + (['%s / %s (%s x %s)' % (_num(row['screen']['b']), _num(row['screen']['c']),
                                                         _num(row['screen']['repeats']), _num(row['screen']['items'])),
                                  _num(row['screen']['fired'])] if row.get('screen') else ['—', '—'])
                              + [_class_points(row, name) for name in ('real', 'attack', 'guard', 'calibration')]
                              + [_pts(((row.get('by_class') or {}).get('parity') or {}).get('parity_points'))
                                 if isinstance(row.get('by_class'), dict) else '—']
                              for row in rows]),
                  '', '- E: the real gate items and the judging-side attack items (where improvement is sought); the '
                      'gains by class and B\'s calibration-minus-real parity are reported and decide nothing']
        if any(row.get('screen') for row in rows):
            lines.append('- ' + SCREEN_NOTE)
    repaired = [row for row in rows if row.get('repair')]
    if repaired:
        lines += ['', _table(['program', 'repair rounds (limit)', 'kept round', 'stop', 'probes noted/routed',
                              'paid round fixed/broken', 'feedback repair'],
                             [[_candidate_label(row), '%s (%s)' % (_num(row['repair'].get('rounds')),
                                                                   _num(row['repair'].get('limit'))),
                               _num(row['repair'].get('kept_round')), _num(row['repair'].get('stop')),
                               ', '.join('%s/%s' % (_num(p.get('noted')), _num(p.get('routed')))
                                         for p in row['repair'].get('probes') or []) or '—',
                               '%s/%s' % (_num((row['repair'].get('paid_round') or {}).get('fixed')),
                                          _num((row['repair'].get('paid_round') or {}).get('broken')))
                               if row['repair'].get('paid_round') else '—',
                               _num(((row['repair'].get('paid_round') or {}).get('feedback') or {}).get('status'))]
                              for row in repaired])]
    archive = block.get('archive')
    if archive:
        lines += ['', '- archive package %s (candidate 0, its own gate decision): accepted %s (%s); gain on its %s '
                      'fired items %s pts, whole list %s pts, tau %s; baseline %s. Later program candidates of the '
                      'step: %s, judged against %s.' % (
                          archive.get('package'), archive.get('accepted'), archive.get('reason'),
                          _num(archive.get('fired_items')), _pts(archive.get('gain_points_fired')),
                          _pts(archive.get('gain_points')), _num(archive.get('tau_points')), _num(archive.get('baseline')),
                          _num(archive.get('later_candidates')), _num(archive.get('later_candidates_judged_against'))),
                  '- ' + ARCHIVE_KNOWN]
    return lines


def _member_label(bench, scope):
    """RP15: a member bench with its kind, 'searchqa (source)' or 'searchqa (routed: 2 gate items)'; the bench
    alone when the record predates the field."""
    scope = scope or {}
    if scope.get('member') == 'routed':
        count = scope.get('routed_gate_items')
        return '%s (routed: %s gate item%s)' % (bench, _num(count), '' if count == 1 else 's')
    return '%s (source)' % bench if scope.get('member') == 'source' else str(bench)


def _md_related(decisions):
    """Addendum D16 (c): for a step whose home type also has earlier member benches (by source or, RP15, by routed
    gate items), the home gain of every decision that reached the member checks beside each member bench's gain
    ("related gain"); informational, it decides nothing beyond no_regress. Both gains cover the whole gate slice
    (fix-c, rc-readout-6): a program's gain on its fired items, which decides it at home, has its own column. Nothing
    for a type of one bench."""
    rows = [[d['label'], d['accepted'],
             _pts(d.get('whole_slice_mean_points') if d['kind'] == 'program' else d['mean_points']),
             _pts(d['mean_points']) if d['kind'] == 'program' else '—',
             _member_label(r['bench'], r), _num(r['n']), _num(r['repeats']),
             _pts(r['gain_points']), _num(r['se_points']), _num(r['tau_points']),
             '%s/%s/%s' % (_num(r['better']), _num(r['worse']), _num(r['tied'])), r['no_regress'],
             '%s%s' % (_num(r['baseline']), ' (selected)' if r['baseline_selected'] else '')]
            for d in decisions for r in d.get('related') or []]
    shared = [d for d in decisions if 'shared_with' in d]
    if not shared:
        return []
    scope = {bench: (d.get('membership') or {}).get(bench) for d in shared for bench in d['shared_with']}
    lines = ['', 'Shared type: the home type\'s members are %s; a candidate that passed the home rule was checked on '
                 'each (no_regress, on the member\'s whole gate slice). Related gain is informational: it decides '
                 'nothing beyond no_regress.' % ', '.join(_member_label(bench, scope[bench]) for bench in sorted(scope))]
    if rows:
        lines += ['', _table(['decision', 'accepted', 'home gain pts', 'home fired gain pts', 'member bench', 'n', 'R',
                              'related gain pts', 'SE pts', 'tau', 'better/worse/tied', 'no_regress',
                              'member baseline'], rows),
                  '', '- home gain and related gain: whole gate slices; a program\'s gain on its fired items (its home '
                      'decision) is in "home fired gain pts"']
    else:
        lines.append('- no candidate of the step reached the member checks')
    return lines


def _md_reads_closed(doc):
    lines = ['## Test reads (closed: counts only, no sealed file opened)', '']
    mirrors = doc.get('read_status') or {}
    if not mirrors:
        return lines + ['No read-status mirror yet.']
    check = doc['mount_check']['reads']
    rows = []
    for stem, mirror in mirrors.items():
        counts = _scalar_leaves(mirror or {})
        rows.append([stem, check.get(stem, {}).get('present'), ', '.join('%s=%s' % kv for kv in sorted(counts.items()))])
    return lines + [_table(['read', 'mount fractions present', 'counts'], rows)]


def _scalar_leaves(value, prefix=''):
    """{'key' or 'key.sub': scalar} of a mirror, one level of nesting (tokens.total, mount.typed_fraction)."""
    out = {}
    for key, inner in value.items():
        if isinstance(inner, (bool, int, float, str)) and len(str(inner)) <= 64:
            out[prefix + str(key)] = inner
        elif isinstance(inner, dict) and not prefix:
            out.update(_scalar_leaves(inner, str(key) + '.'))
    return out


def _base_label(event, doc):
    """The event cell of a panel row: the base row of the learned arms (D17: C under 'historical', C0 under 'format')
    says so."""
    return event + ' (base of S1..S5)' if event == BASE_EVENTS.get(doc.get('base_card')) else event


def _md_panels(doc):
    lines = ['## Test panels (opened by the owner; generalization evidence only)']
    for bench, panel in doc['panels'].items():
        lines += ['', '### %s (common items %d)' % (bench, panel['items_common']), '',
                  _table(['event', 'n', 'acc L %', 'acc H %', 'acc known %', 'unknown', 'infra unknown', 'typed %',
                          'card mounted %', 'programs enabled %', 'tokens'],
                         [[_base_label(event, doc), s['n'], _pct(s['accuracy']['L']), _pct(s['accuracy']['H']), _pct(s['accuracy']['known']),
                           s['unknown'], s['infrastructure_unknown'], _pct(s['routing']['typed_fraction']),
                           _pct(s['routing']['card_mounted_fraction']), _pct(s['routing']['enabled_fraction']), s['tokens']]
                          for event, s in panel['per_event'].items()])]
        if panel['pairs']:
            lines += ['', _table(['contrast', 'n (known pairs)', 'unknown excl.', 'mean pts', 'SE pts', 't 95%', 'bootstrap 95%',
                                  'better/worse/tied'],
                                 [[name, p['n'], p['excluded_unknown'], _pts(p['mean_points']), _unsigned(p['se_points']),
                                   _interval(p['t_interval95_points']), _interval(p['bootstrap_interval95_points']),
                                   '%d/%d/%d' % (p['better'], p['worse'], p['tied'])] for name, p in panel['pairs'].items()])]
        noise = panel.get('same_request_noise')
        if doc.get('read_anchors'):   # typed-v3 T2: no C0 read, no C vs C0 pair
            lines += ['', '- same-request noise (C vs C0): not measured, C0 is not read (read_anchors C)']
        if noise:
            found = noise['noise'] or {}
            lines += ['', '- same-request noise (C vs C0, identical request sha lists on %d of %d items%s): %s' % (
                noise['identical_requests'], noise['items_common'],
                '; ZebraLogic reads C as C0 by construction' if bench == 'zebralogic' else '',
                'flip rate %s, mean %s pts, SE %s pts, tau %s' % (_num(found.get('flip_rate')), _pts(found.get('mean_points')),
                                                                    _pts(found.get('se_points')), _num(found.get('tau_points')))
                if found else 'no identical requests')]
    return lines


def _interval(value):
    return '—' if value is None else '[%+.1f, %+.1f]' % tuple(value)


def _unsigned(value):
    return '—' if value is None else '%.1f' % value


def _md_matrix(title, rows, key, render):
    lines = ['', title, '', _table(['step', 'evolved bench'] + list(ORDER),
                                   [[row['step'], row['evolved_bench']] + [render(row[key][bench]) for bench in ORDER]
                                    for row in rows.values()])]
    return lines


def _md_five_by_five(doc):
    rows = doc['five_by_five']
    lines = ['## 5x5 (rows = the bench evolved at step k, columns = the five panels)']
    if doc.get('read_anchors'):   # typed-v3 T2: no C0 read
        lines += _md_matrix('S<k> - C, mean paired difference in points (known pairs):', rows, 'diff_points_vs_C', _pts)
        lines += _md_matrix('S<k> - S<k-1> (S0 := C), mean paired difference in points (known pairs):', rows,
                            'diff_points_vs_previous', _pts)
        lines += _md_matrix('Accuracy of S<k> on L (unknown = wrong), %:', rows, 'accuracy_L', _pct)
        lines += _md_matrix('Accuracy of S<k> on H (unknown = right), %:', rows, 'accuracy_H', _pct)
        return lines
    lines += _md_matrix('S<k> - C0, mean paired difference in points (known pairs):', rows, 'diff_points_vs_C0', _pts)
    lines += _md_matrix('Accuracy of S<k> on L (unknown = wrong), %:', rows, 'accuracy_L', _pct)
    lines += _md_matrix('Accuracy of S<k> on H (unknown = right), %:', rows, 'accuracy_H', _pct)
    return lines


def _md_cl(doc):
    if doc.get('read_anchors'):   # typed-v3 T2: no C0 read
        return _md_cl_c(doc)
    metrics = doc['cl_metrics']
    lines = ['## Continual-learning metrics (formulas in the module docstring; S0 := C0)']
    for side in SIDES:
        rows = []
        for bench, m in metrics['per_bench'].items():
            values = m[side]
            rows.append([bench, m['home_step'], _num(m['final_event']), m['n']] +
                        [_pct(values['final']), _pct(values['C0']), _pct(values['C'])] +
                        [_pct_pts(values[key]) for key in ('gain_over_C0', 'gain_over_C', 'forgetting',
                                                          'forgetting_after_home', 'backward_transfer',
                                                          'forward_transfer', 'plasticity')])
        macro = metrics['macro'][side]
        rows.append(['macro', '', '', ''] + [_pct(macro[key]['mean']) for key in ('final', 'C0', 'C')] +
                    [_pct_pts(macro[key]['mean']) for key in ('gain_over_C0', 'gain_over_C', 'forgetting',
                                                              'forgetting_after_home', 'backward_transfer',
                                                              'forward_transfer', 'plasticity')])
        lines += ['', 'Side %s:' % side, '',
                  _table(['bench', 'home step', 'final', 'n', 'final %', 'C0 %', 'C %', 'gain vs C0', 'gain vs C',
                          'forgetting', 'forgetting after home', 'backward transfer', 'forward transfer', 'plasticity'], rows)]
    latest = [(bench, m['latest_event']) for bench, m in metrics['per_bench'].items() if m['final_event'] is None]
    if latest:
        lines += ['', 'Unfinished chain: the final event is missing on %s; `latest` in the JSON repeats the formulas with '
                      'the last available event (%s).' % (', '.join(b for b, _ in latest),
                                                           ', '.join('%s: %s' % row for row in latest))]
    return lines


def _md_cl_c(doc):
    """``_md_cl`` without C0 (typed-v3 T2): S0 := C; no C0 and gain-vs-C0 columns (``readout.C0_DEPENDENT``)."""
    metrics = doc['cl_metrics']
    keys = ('gain_over_C', 'forgetting', 'forgetting_after_home', 'backward_transfer', 'forward_transfer', 'plasticity')
    lines = ['## Continual-learning metrics (formulas in the module docstring with S0 := C; C0 is not read: no C0 '
             'level, no gain vs C0, no same-request noise)']
    for side in SIDES:
        rows = []
        for bench, m in metrics['per_bench'].items():
            values = m[side]
            rows.append([bench, m['home_step'], _num(m['final_event']), m['n'], _pct(values['final']),
                         _pct(values['C'])] + [_pct_pts(values[key]) for key in keys])
        macro = metrics['macro'][side]
        rows.append(['macro', '', '', '', _pct(macro['final']['mean']), _pct(macro['C']['mean'])] +
                    [_pct_pts(macro[key]['mean']) for key in keys])
        lines += ['', 'Side %s:' % side, '',
                  _table(['bench', 'home step', 'final', 'n', 'final %', 'C %', 'gain vs C', 'forgetting',
                          'forgetting after home', 'backward transfer', 'forward transfer', 'plasticity'], rows)]
    latest = [(bench, m['latest_event']) for bench, m in metrics['per_bench'].items() if m['final_event'] is None]
    if latest:
        lines += ['', 'Unfinished chain: the final event is missing on %s; `latest` in the JSON repeats the formulas with '
                      'the last available event (%s).' % (', '.join(b for b, _ in latest),
                                                           ', '.join('%s: %s' % row for row in latest))]
    return lines


def _pct_pts(value):
    return '—' if value is None else '%+.1f' % (100 * value)


def _md_mount_check(doc):
    check = doc['mount_check']
    lines = ['## Mount check (F2-style: every read records what it mounted)', '',
             '- rule: %s' % check['rule'], '- all present: %s' % check['all_present']]
    rows = check['reads']
    if rows and doc['mode'] == 'open':
        lines += ['', _table(['read', 'cells', 'mount records', 'present', 'typed %', 'card mounted %', 'skills seen',
                              'ids not in the step library'],
                             [[name, r['cells'], r['mount_records_present'], r['present'], _pct(r['typed_fraction']),
                               _pct(r['card_mounted_fraction']), ', '.join(r['skills_seen']) or '—',
                               ', '.join(r['unknown_skill_ids']) or '—'] for name, r in rows.items()])]
    return lines


# ---- markdown of an economy chain (R65 to R74; the typed-v1 renderers above stay for a full root) --------------
def _fmt(cell, render, deref=None):
    """One grid number of R66 as text: measured value, ``=X v u/i/c`` for an alias (v: the contrast cell it carries,
    ``shown``, else dereferenced on purpose), ``-`` inside one class, ``split`` for a reference-only value, ``-
    (noise sample, ref v)`` for a term between two readings of identical requests, else the pair's source."""
    if cell is None:
        return '—'
    kind = cell['kind']
    if kind == 'measured':   # identical requests on every item: a noise sample, not an effect (R67)
        return render(cell['value']) + (' noise sample' if cell.get('requests') == 'identical' else '')
    if kind == 'alias':
        shown = cell.get('shown')   # a 5x5 difference row: the representatives' own contrast (fix-c, rc-readout-4)
        value = _fmt(shown, render) if shown is not None else render(deref(cell['of'])) if deref is not None else '—'
        return '=%s %s u/i/c %s' % (cell['of'], value, _uic(cell.get('counts')))
    if kind in ('same_class', 'structural'):
        return '-'
    if kind == 'noise_sample':   # fix-c, rc-readout-2: by construction 0, the reading beside
        return '- (noise sample, ref %s)' % render(cell.get('reference'))
    if kind == 'split':
        return 'split'
    if kind == 'incomplete':
        return 'incomplete'
    return str(cell.get('source') or 'pending')


def _gate_noise_line(doc):
    parts = ['s%s tau %s / SE %s' % (k, _num(row['tau_points']), _num(row['se_points']))
             for k, row in (doc.get('gate_noise') or {}).items()]
    return ('- practice-side gate noise per step (points; the learning base B repeated on the gate slice; no '
            'test-side replicate exists, RP7): ' + ('; '.join(parts) or 'not recorded'))


def _replicates_line(doc):
    found = doc.get('in_run_replicates') or {}
    return '- in-run replicates: %s (%s)' % (found.get('total', 0), ', '.join(
        '%s %s' % (bench, found[bench]) for bench in ORDER if bench in found) or 'no panel')


def _md_economy_closed(doc):
    """R65: alias pairs in their own block (never in the mirror table), stale records, classes and planned mounts."""
    lines = ['', '### Alias pairs (same requests as their representative; no unit, cell or mirror of their own)', '']
    rows = [[stem, 'same requests as %s' % _num(row['of']), _uic(row['counts']),
             '%s/%s of %s' % tuple(_num((row['check'] or {}).get(k)) for k in ('equal', 'unequal', 'items')),
             'verified' if row['valid'] else 'INVALID (%s)' % row['error']]
            for stem, row in (doc.get('aliases') or {}).items()]
    lines.append(_table(['pair', 'alias of', 'representative u/i/c', 'post-read check equal/unequal', 'record'], rows)
                 if rows else 'No alias record yet.')
    stale = doc.get('stale_alias_records') or []
    if stale:
        lines += ['', '- stale alias records (no alias state entry; reported, never shown): %s'
                  % ', '.join(row['pair'] for row in stale)]
    return lines + [''] + _md_classes(doc)


def _md_classes(doc):
    classes = doc.get('classes')
    lines = ['## Read classes (economy plan %s)' % (doc['read_plan'].get('plan_sha256') or 'not bound'), '']
    if doc['read_plan'].get('void'):
        lines.append('- the plan is VOID (%s): every pair is its own class and is read fresh' %
                     doc['read_plan'].get('void_reason'))
    if not classes:
        return lines + ['No bound plan.']
    rows = []
    for bench, entry in classes.items():
        for row in entry['classes']:
            settled = ', '.join('%s %s' % (m, s) for m, s in row['settled'].items())
            check = row['check'] or {}
            rows.append([bench, row['id'], '{%s}' % ', '.join(row['members']), row['representative'], row['status'],
                         _num(row['reason']), settled,
                         '%s/%s of %s' % tuple(_num(check.get(k)) for k in ('equal', 'unequal', 'items')),
                         _uic(row['counts'])])
    lines.append(_table(['bench', 'class', 'members', 'representative', 'plan status', 'fallback reason', 'settled',
                         'post-read check equal/unequal', 'representative u/i/c'], rows))
    for bench, entry in classes.items():
        if entry['post_read_mismatch']:
            lines.append('- %s: post-read mismatch (defect signal, R42): %s' % (bench, ', '.join(
                '%s %s' % kv for kv in sorted(entry['post_read_mismatch'].items()))))
    return lines


def _md_event_grid(doc, side):
    rows = []
    for event in READ_ARMS:
        row = [event]
        for bench in ORDER:
            panel = doc['panels'].get(bench)
            mark = panel['marks'][event] if panel else None
            if mark is None:
                row.append('—')
            elif mark['kind'] == 'measured' and event in panel['per_event']:
                row.append(_pct(panel['per_event'][event]['accuracy'][side]))
            elif mark['kind'] == 'alias':
                rep = panel['per_event'].get(mark['of'])
                row.append('=%s %s u/i/c %s' % (mark['of'], _pct(rep['accuracy'][side]) if rep else '—',
                                                _uic(mark['counts'])))
            else:
                row.append(mark['source'] if mark['kind'] != 'measured' else 'missing')
        rows.append(row)
    return [_table(['event'] + list(ORDER), rows), '', ECONOMY_LEGEND]


def _contrast_row(name, c, replicates):
    if c['status'] == 'measured':
        p = c['delta']
        requests = c['requests']['text'] + ('; noise sample, not an effect' if c['noise_sample'] else '')
        return [name, '%s-%s' % tuple(c['of']), requests, p['n'], p['excluded_unknown'], _pts(p['mean_points']),
                _unsigned(p['se_points']), _interval(p['t_interval95_points']),
                _interval(p['bootstrap_interval95_points']), '%d/%d/%d' % (p['better'], p['worse'], p['tied']),
                replicates]
    if c['status'] == 'same_class':
        return [name, '%s-%s' % tuple(c['of']), 'same requests, not measured'] + ['-'] * 7 + [replicates]
    if c['status'] == 'split':
        return [name, '%s-%s' % tuple(c['of']), 'not same-phase: reference block only'] + ['-'] * 7 + [replicates]
    return [name, '—', c['status']] + ['—'] * 7 + [replicates]


def _md_panels_economy(doc):
    lines = ['## Test panels (opened by the owner; generalization evidence only; fresh units only)']
    for bench, panel in doc['panels'].items():
        rows = []
        for event in READ_ARMS:
            mark = panel['marks'][event]
            if mark['kind'] == 'measured' and event in panel['per_event']:
                s = panel['per_event'][event]
                rows.append([_base_label(event, doc), s['n'], _pct(s['accuracy']['L']), _pct(s['accuracy']['H']),
                             _pct(s['accuracy']['known']), s['unknown'], s['infrastructure_unknown'],
                             _pct(s['routing']['typed_fraction']), _pct(s['routing']['card_mounted_fraction']),
                             _pct(s['routing']['enabled_fraction']), s['tokens']])
            elif mark['kind'] == 'alias':
                rep = panel['per_event'].get(mark['of'])
                acc = (rep or {}).get('accuracy') or {}
                rows.append([_base_label(event, doc), 'same requests as %s' % mark['of']] +
                            ['=%s %s' % (mark['of'], _pct(acc.get(k))) for k in ('L', 'H', 'known')] +
                            ['u/i/c %s' % _uic(mark['counts']), '—', '—', '—', '—', '—'])
            else:
                rows.append([_base_label(event, doc), mark['source'] if mark['kind'] == 'none' else 'missing'] +
                            ['—'] * 9)
        lines += ['', '### %s (common items of the fresh units %d)' % (bench, panel['items_common']), '',
                  _table(['event', 'n', 'acc L %', 'acc H %', 'acc known %', 'unknown', 'infra unknown', 'typed %',
                          'card mounted %', 'programs enabled %', 'tokens'], rows), '', ECONOMY_LEGEND, '',
                  _table(['contrast', 'of', 'requests', 'n (known pairs)', 'unknown excl.', 'mean pts', 'SE pts', 't 95%',
                          'bootstrap 95%', 'better/worse/tied', 'in-run replicates'],
                         [_contrast_row(name, c, panel['in_run_replicates']) for name, c in panel['contrasts'].items()]),
                  '', '- : same requests, not measured (D10 d)', _gate_noise_line(doc)]
        noise = panel.get('same_request_noise')
        if noise:
            found = noise['noise'] or {}
            lines.append('- same-request noise (fresh C vs C0, identical first inputs on %d of %d items): %s' % (
                noise['identical_requests'], noise['items_common'],
                'flip rate %s, mean %s pts, SE %s pts, tau %s' % (_num(found.get('flip_rate')), _pts(found.get('mean_points')),
                                                                  _pts(found.get('se_points')), _num(found.get('tau_points')))
                if found else 'no identical requests'))
        units_line = ', '.join('%s %s..%s models %s' % (event, meta['range'][0] or '?', meta['range'][1] or '?',
                                                        ', '.join('%s %s' % kv for kv in meta['models'].items()) or 'none')
                               for event, meta in panel['units'].items())
        lines.append('- fresh units (time range, returned model ids; R90): ' + (units_line or 'none'))
    return lines


def _md_reference(doc):
    rows = [[row['bench'], '%s-%s' % tuple(row['of']), ', '.join(row['contrasts']), _pts(row['point_points']),
             '; '.join('%s %s..%s' % (event, r[0] or '?', r[1] or '?') for event, r in row['ranges'].items()),
             row['reason'] if row['reason'] != 'recovery' else 'recoveries ' + ', '.join(map(str, row['recoveries']))]
            for row in doc.get('reference') or []]
    lines = ['## Reference block (not same-phase, R89: point difference only; no SE, interval or counts)', '']
    return lines + ([_table(['bench', 'representatives', 'contrasts', 'point pts', 'unit time ranges', 'split by'], rows)]
                    if rows else ['No split contrast.'])


def _md_matrix_economy(title, rows, key, render, replicates=None):
    body = []
    for event, row in rows.items():
        deref = lambda of, bench: (rows.get(of) or {}).get(key, {}).get(bench, {}).get('value')
        body.append([row['step'], row['evolved_bench']] + [
            _fmt(row[key][bench], render, (lambda of, b=bench: deref(of, b))) for bench in ORDER])
    if replicates is not None:
        body.append(['in-run replicates', ''] + [_num(replicates.get(bench, 0)) for bench in ORDER])
    return ['', title, '', _table(['step', 'evolved bench'] + list(ORDER), body)]


def _md_five_by_five_economy(doc):
    rows, replicates = doc['five_by_five'], doc.get('in_run_replicates') or {}
    lines = ['## 5x5 (rows = the bench evolved at step k, columns = the five panels; marks as in the legend)']
    lines += _md_matrix_economy('S<k> - C0, mean paired difference in points (known pairs):', rows,
                                'diff_points_vs_C0', _pts, replicates)
    lines += _md_matrix_economy('S<k> - C, mean paired difference in points (known pairs):', rows,
                                'diff_points_vs_C', _pts, replicates)
    lines += _md_matrix_economy('Accuracy of S<k> on L (unknown = wrong), %:', rows, 'accuracy_L', _pct)
    lines += _md_matrix_economy('Accuracy of S<k> on H (unknown = right), %:', rows, 'accuracy_H', _pct)
    return lines + ['', ECONOMY_LEGEND, _replicates_line(doc), _gate_noise_line(doc)]


def _fmt_term(cell):
    if cell is None:
        return '—'
    text = _fmt(cell, _pct_pts)
    noise = cell.get('noise_terms') or []
    if cell['kind'] == 'structural' and (cell.get('structural_terms') or noise):
        # RP4: the by-construction terms, the noise samples among them with their readings (fix-c, rc-readout-2)
        count = (cell.get('structural_terms') or 0) + len(noise)
        text = '- (%d by-construction term%s%s%s)' % (
            count, '' if count == 1 else 's', '' if not noise else ', of which %d noise sample%s: %s' % (
                len(noise), '' if len(noise) == 1 else 's',
                ', '.join('%s ref %s' % (row['event'], _pct_pts(row['reference'])) for row in noise)),
            '' if cell.get('other_max') is None else '; other classes max %s, not above 0' % _pct_pts(cell['other_max']))
    elif cell['kind'] == 'measured' and noise:
        text += ' [noise samples, not in the maximum: %s]' % ', '.join(
            '%s ref %s' % (row['event'], _pct_pts(row['reference'])) for row in noise)
    elif cell['kind'] == 'split' and cell.get('note'):
        text = cell['note']
    if cell.get('split_terms'):
        text += ' [split: %s]' % ', '.join('%s ref %s' % (row['event'], _pct_pts(row['reference']))
                                           for row in cell['split_terms'])
    if cell.get('missing_terms'):   # fix-c, rc-readout-5: never a maximum over an incomplete set
        text += ' [missing: %s%s]' % (', '.join('%s %s' % (row['event'], row['source']) for row in cell['missing_terms']),
                                      '' if cell.get('partial') is None
                                      else '; max of the others %s' % _pct_pts(cell['partial']))
    return text


def _fmt_macro(row):
    a, b = row['a'], row['b']
    if a['kind'] == 'mixed':
        return a['text'], b['text']
    if a['kind'] == 'mean':
        text = '%s (n %s, %s via representatives)' % (_pct(a['value']), a['n'], a['aliased'])
        return text, text
    noise = (', %s noise sample%s as 0' % (a['noise_samples'], '' if a['noise_samples'] == 1 else 's')
             if a.get('noise_samples') else '')
    return ('%s (%s of %s structural%s)' % (_pct_pts(a['value']), a['structural'], a['benches'], noise),
            '%s (n = %s of %s)' % (_pct_pts(b['value']), b['n'], b['benches']))


def _md_cl_economy(doc):
    metrics = doc['cl_metrics']
    keys = ('gain_over_C0', 'gain_over_C', 'forgetting', 'forgetting_after_home', 'backward_transfer',
            'forward_transfer', 'plasticity')
    lines = ['## Continual-learning metrics (economy: terms through the resolver; S0 := %s, the start of learning)'
             % metrics['definitions'].get('S0', 'C0')]
    for side in SIDES:
        rows = []
        for bench, m in metrics['per_bench'].items():
            values = m[side]
            deref = lambda of, b=bench: ((doc['panels'][b]['per_event'].get(of) or {}).get('accuracy') or {}).get(side)
            rows.append([bench, m['home_step'], m['final_event'], m['n']] +
                        [_fmt(values[key], _pct, deref) for key in LEVEL_KEYS] + [_fmt_term(values[key]) for key in keys])
        macro = metrics['macro'][side]
        for column in (0, 1):
            rows.append(['macro (%s)' % 'ab'[column], '', '', ''] +
                        [_fmt_macro(macro[key])[column] for key in LEVEL_KEYS + keys])
        lines += ['', 'Side %s:' % side, '',
                  _table(['bench', 'home step', 'final', 'n', 'final %', 'C0 %', 'C %', 'gain vs C0', 'gain vs C',
                          'forgetting', 'forgetting after home', 'backward transfer', 'forward transfer', 'plasticity'],
                         rows)]
    defs = metrics['definitions']
    return lines + ['', '- terms: ' + defs['formulas'], '- macro: ' + defs['macro'], '- forgetting: ' + defs['forgetting'],
                    '- structural: ' + defs['structural'], '- noise sample: ' + defs['noise_sample'],
                    _replicates_line(doc), _gate_noise_line(doc)]


def _relation_tag(cell):
    """The generalization view's relation as printed: home, same, routed n/N (fix-c, rc-readout-3), other, ?."""
    relation = cell['relation']
    if relation == 'routed':
        return 'routed %s/%s' % (cell['routed_items'], cell['items'])
    return {'home': 'home', 'same-type': 'same', 'other-type': 'other', 'type unknown': '?'}.get(relation, '?')


def _md_generalization(doc):
    rows = [[event, _num(row['home_bench']), row['previous']] +
            ['%s (%s)' % (_fmt(row['cells'][bench], _pts), _relation_tag(row['cells'][bench])) for bench in ORDER]
            for event, row in doc['generalization'].items()]
    return ['## Generalization view (S<k> minus the previous state; informational, it decides nothing)', '',
            '- ' + ECONOMY_DEFINITIONS['generalization'], '',
            _table(['step', 'home bench', 'previous'] + list(ORDER), rows), '',
            '- (home) the bench evolved at the step; (same) a bench with a source in its type; (routed n/N) n of the '
            'bench\'s N panel items were routed into the home type, so the step\'s skills reach them; (other) every '
            'other bench; - : same requests (the step changed nothing on that panel); split: see the reference block',
            _replicates_line(doc), _gate_noise_line(doc)]


def _md_economy_open(doc):
    if doc.get('read_plan_error'):   # R74: no read table, only the error
        return ['## Test reads: no table', '', '- the bound read plan failed its check (%s): no read table is rendered'
                % doc['read_plan_error']]
    lines = ['## Event grid (accuracy L, unknown = wrong, %)', ''] + _md_event_grid(doc, 'L')
    lines += ['', _replicates_line(doc), _gate_noise_line(doc), '']
    lines += _md_panels_economy(doc) + [''] + _md_reference(doc) + [''] + _md_five_by_five_economy(doc)
    lines += [''] + _md_cl_economy(doc) + [''] + _md_generalization(doc) + [''] + _md_classes(doc)
    stale = doc.get('stale_alias_records') or []
    if stale:
        lines += ['', '- stale alias records (reported, never shown): %s' % ', '.join(row['pair'] for row in stale)]
    if doc.get('not_loaded'):
        lines += ['- unit directories not loaded (pair not fresh: alias, pending or invalid): %s'
                  % ', '.join(doc['not_loaded'])]
    return lines


def _md_mount_check_economy(doc):
    check = doc['mount_check']
    lines = ['## Mount check (F2-style: every read records what it mounted)', '', '- rule: %s' % check['rule'],
             '- scope: %s' % check.get('scope'), '- all present: %s' % check['all_present']]
    rows = check['reads']
    if rows and doc['mode'] == 'open' and not doc.get('read_plan_error'):
        lines += ['', _table(['read', 'cells', 'mount records', 'present', 'typed %', 'card mounted %', 'skills seen',
                              'ids not in the step library'],
                             [[name, r['cells'], r['mount_records_present'], r['present'], _pct(r['typed_fraction']),
                               _pct(r['card_mounted_fraction']), ', '.join(r['skills_seen']) or '—',
                               ', '.join(r['unknown_skill_ids']) or '—'] for name, r in rows.items()])]
    planned = check.get('planned') or {}
    if planned:
        lines += ['', 'Alias pairs (planned, from the plan; no cell of their own):', '',
                  _table(['pair', 'of', 'items', 'typed', 'unknown', 'with card', 'with programs', 'source'],
                         [[name, r['of'], r['items'], r['typed'], r['unknown'], r['with_card'], r['with_programs'],
                           'planned'] for name, r in planned.items()])]
    return lines


def markdown(doc):
    """The chain's readout as markdown; the disclaimers come first and are repeated per section where it matters."""
    lines = ['# %s readout: chain %s (%s mode)' % (VERSION, doc['chain'], doc['mode']), '',
             'Generated %s UTC from `%s`.' % (doc['generated_utc'], doc['root']), '',
             '> ' + DISCLAIMER, '',
             '> %s' % ('Closed mode: no sealed test read was opened; read rows carry counts only.' if doc['mode'] == 'closed'
                       else 'Open mode: the owner opened the sealed test reads. Practice-side gates decided everything; '
                            'these numbers are generalization evidence and select nothing.'), '',
             '- base card: %s' % ('%s (sealed `base_card`): %s' % (doc['base_card'], BASE_CARD_LINES[doc['base_card']])
                                  if doc.get('base_card') in BASE_CARD_LINES else 'not recorded'), '']
    if doc.get('read_anchors'):   # typed-v3 T2 (a typed-v2 style document has no such line)
        lines[-1:-1] = ['- read anchors: %s (sealed `read_anchors`): the anchor C0 (the format block alone) is not '
                        'read; the rows are C, S1..S5 and the contrasts S<k> - C and S<k> - S<k-1>'
                        % ', '.join(doc['read_anchors'])]
    lines += _md_state(doc)
    lines += ['', '## Learning steps']
    for step in doc['steps'].values():
        lines += [''] + _md_step(step)
    if not doc['steps']:
        lines.append('No learning step recorded.')
    lines.append('')
    economy = bool(doc.get('read_plan'))
    if economy and doc['read_plan'].get('error'):   # R74: the error only, no read table in either mode
        lines += ['## Test reads: no table', '', '- the bound read plan failed its check (%s): no read table is '
                  'rendered' % doc['read_plan']['error'], '']
    elif economy and doc['mode'] == 'open':
        lines += _md_economy_open(doc) + ['']
    elif economy:
        lines += _md_reads_closed(doc) + _md_economy_closed(doc) + ['']
    elif doc['mode'] == 'open':
        lines += _md_panels(doc) + [''] + _md_five_by_five(doc) + [''] + _md_cl(doc) + ['']
    else:
        lines += _md_reads_closed(doc) + ['']
    lines += _md_mount_check_economy(doc) if economy else _md_mount_check(doc)
    lines += ['', '---', 'Practice-side gates decided every acceptance; no configuration was picked from these numbers.', '']
    return '\n'.join(lines)
