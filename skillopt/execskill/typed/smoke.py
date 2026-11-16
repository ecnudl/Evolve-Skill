"""The typed-v2 smoke (design §5.9): the whole chain on tiny practice slices under its own ``<root>-smoke`` root,
every unit type exercised, held-out practice items in place of the test panels (so no consent is needed), one
card round and at most one program candidate.

``fake_services`` wires scripted model replies, deterministic hash embeddings and a fake ``solve`` (judge tokens
from a table) so that ``smoke --fake`` runs locally without Docker, network or /data, while the REAL mount (type
assignment, system card composition, the selection call), the real writers (prompts, screens, retries) and the
real reads (sealed/open records) are reused where nothing machine-bound is needed. ``modules`` lets tests inject
fakes for those three modules before they exist in a tree. The scripted program writer answers in the typed-v2
reply format (``replies.REPLY_FORMAT``); on searchqa its one programs unit takes the whole promotion path of
DESIGN 3.2 / 3.3 (an unreadable reply, the one format retry, a proposal refused by the static screen with its
refused fix, a later proposal promoted to slot 1), and ALFWorld gets a program with its own note hook.

The smoke runs on its manifest's base card (addendum D17): ``prepare --smoke --base-card historical`` for the
typed-v2 smoke; a fake smoke without a prepared manifest takes ``base_card`` (the code default 'format' when None).
Likewise its schedule and memory lock (DESIGN 3.6; ``prepare --smoke --schedule learn_first --memory-lock
unit_shared`` for the typed-v2 smoke, addenda D9, D13): a fake smoke's synthetic manifest carries both fields (the code
defaults unless a test builds it with others); the fake services take no lock in either mode.

The read plan (addendum D9, D10; read-plan R7, 4.3): the typed-v2 smoke is prepared with the run's values and the
smoke-only probe (``CONFIGURED``: learn_first, unit_shared, base 'historical', read_plan 'economy', read_plan_probe
['C0', 'zebralogic']). A fake smoke without a prepared manifest runs on the synthetic manifest with the code defaults
('full' reads), or with ``CONFIGURED`` when asked (``configured``, CLI ``smoke --fake --configured``): then the real
pass runs on the practice panels, its automatic replay is the real ``plan-replay --fake`` child process (R76), and
``fake_kill_at`` (CLI ``--fake-kill-at``) names one of the three kill points of R92 at which the fake services send
SIGKILL to their own process group (``checkpoint``; for 'replay-child' only inside the child). ``fake_solve`` rows
carry ``public_hash`` as the real solve's do (ADV8; R41 reads it).
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import signal
import sys
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from skillopt.continual_eval.core import require
from skillopt.execskill.protocol import FIRST_CALL_SYSTEM

from . import (BASE_CARD_DEFAULT, BASE_CARDS, CAPS, CONFIGURATION, GATE_REPEATS, MACHINERY, MAX_PROGRAM_PROPOSALS,
               MEMORY_LOCK_DEFAULT, MEMORY_LOCKS, ORDER, READ_PLAN_DEFAULT, SCHEDULE_DEFAULT, SCHEDULES, SEED,
               SMOKE_SLICES, VERSION)
from . import chain as chain_, library as library_, readplan, units
from .library import canonical_sha256

# the five keys of chain.DEFAULT_LIMITS (DESIGN 3.2): the smoke lowers card rounds, candidates and smoke items only
SMOKE_LIMITS = {'card_rounds': 1, 'max_program_proposals': MAX_PROGRAM_PROPOSALS, 'max_program_candidates': 1,
                'program_smoke_items': 2, 'gate_repeats': GATE_REPEATS}
SMOKE_SUFFIX = '-smoke'
EMBED_DIM = 16
REPEAT_SEARCH = 9  # repeat indexes the fake solve tries when it reads a cell's repeat from its tag
FAKE_SOLVER_BOUND = 4096  # the fake clients' completion bound (the ledger charges bytes + 512 + bound per send)
FAMILY_CHARS = 16  # hash embeddings cluster texts by their first characters (one family per synthetic bench)
# The typed-v2 smoke's sealed values (addenda D9, D13, D17; read-plan R7, S1): the run's, plus the smoke-only probe
CONFIGURED = {'schedule': 'learn_first', 'memory_lock': 'unit_shared', 'base_card': 'historical', 'read_plan': 'economy',
              'read_plan_probe': list(readplan.PLAN_PROBE_EVENT_BENCH)}
DEFAULT_CARD = ('- Read every part of the task before answering.\n'
                '- Quote numbers and names exactly as they appear in the given material.\n'
                '- Give exactly one final answer in the required format.')


def program_reply(changes):
    """A program-writer reply in the typed-v2 format (``replies.REPLY_FORMAT``): one fenced json block holding
    ``{"changes": [entries]}``, then one fenced python block per change, in the same order; no program text in the
    JSON. ``changes``: [(entry, source)]; the entries carry the fields the engineer prompt asks for."""
    manifest = json.dumps({'changes': [entry for entry, _ in changes]})
    return '```json\n' + manifest + '\n```' + ''.join('\n\n```python\n' + source + '```' for _, source in changes)


HELPER_SOURCE = ('def applies(view):\n    return True\n\n\n'
                 'def before_call(view, state):\n    return {"warnings": ["Read the whole task before answering."]}\n')
HELPER_ENTRY = {'kind': 'new', 'description': 'Lists a caution for the solver before it answers.',
                'hooks': ['applies', 'before_call'], 'header': '', 'max_note_chars': 600}
ALFWORLD_SOURCE = ('def alf_before_step(view, state):\n'
                   '    return {"fields": {"warnings": ["Choose each action from the admissible commands."]}, '
                   '"discourage": []}\n')
ALFWORLD_ENTRY = {'kind': 'new', 'description': 'Reminds the agent to choose each action from the admissible commands.',
                  'hooks': ['alf_before_step'], 'header': '', 'max_note_chars': 600}
DEFAULT_PROGRAM = program_reply([(HELPER_ENTRY, HELPER_SOURCE)])        # one clean proposal (note hook before_call)
ALFWORLD_PROGRAM = program_reply([(ALFWORLD_ENTRY, ALFWORLD_SOURCE)])  # ALFWorld's note hook (addendum O7)
# The promotion path of one programs unit (spec/engineer.md change 13 with spec/reply.md's scripted retry): prose
# (no JSON object: 'no_manifest') -> the one format retry -> two changes, the first refused by the static screen
# ([import] os) and its one fix refused again ([name] hasattr: 'dropped_screen'), the second clean (slot 1).
PROMOTION_BENCH = 'searchqa'
UNREADABLE_PROPOSAL = 'A helper that warns the solver before it answers would help on these tasks.'
REFUSED_ENTRY = {**HELPER_ENTRY, 'description': 'Warns the solver before it answers, after a look at its environment.'}
REFUSED_SOURCE = 'import os\n\n\n' + HELPER_SOURCE
FIX_REFUSED = program_reply([(REFUSED_ENTRY, HELPER_SOURCE.replace('return True', 'return hasattr(view, "get")'))])


def _clean_change(bench):
    return (ALFWORLD_ENTRY, ALFWORLD_SOURCE) if bench == 'alfworld' else (HELPER_ENTRY, HELPER_SOURCE)


def scripted_program_writer(system, user):
    """The ``Script`` default of the program writer, chosen by the request alone (so a resumed unit gets the same
    replies): a fix request (or a fix's format retry) gets ``FIX_REFUSED``; a proposal's format retry gets two changes,
    ``REFUSED_SOURCE`` and the bench's clean program; a proposal on PROMOTION_BENCH gets prose; any other proposal one
    clean program (``DEFAULT_PROGRAM``, on ALFWorld ``ALFWORLD_PROGRAM``). On PROMOTION_BENCH the unit makes 3 writer
    calls (proposal, format retry, fix) and promotes the second proposal; elsewhere 1 call, the first proposal."""
    try:
        request = json.loads(user)
    except ValueError:
        request = None
    request = request if isinstance(request, dict) else {}
    kind, bench = request.get('request'), request.get('bench')
    if kind == 'fix' or request.get('purpose') == 'fix':
        return FIX_REFUSED
    if kind == 'format_retry':
        return program_reply([(REFUSED_ENTRY, REFUSED_SOURCE), _clean_change(bench)])
    if bench == PROMOTION_BENCH:
        return UNREADABLE_PROPOSAL
    return program_reply([_clean_change(bench)])


DEFAULT_DESCRIPTION = json.dumps({'description': 'Scripted skill for the practice tasks of its type: use it on tasks '
                                                 'with this public structure; do not use it on other task structures.'})
SHEET_PREVIEW = [{'sheet': 'Sheet1', 'preview': [['A', 'B'], [1, 2], [3, 4]]}]
ZEBRA_GRID = {'House 1': {'Name': 'Alice', 'Colour': 'red'}, 'House 2': {'Name': 'Bob', 'Colour': 'green'},
              'House 3': {'Name': 'Carol', 'Colour': 'blue'}}


def _alfworld_view(i):
    return {'initial_observation': 'You are in a kitchen (%s). A sink 1 and a table 1 are here.\n\n'
                                   'Your task is to: put a mug in sink.' % i,
            'admissible_commands_at_reset': ['look', 'go to sink 1', 'go to table 1'], 'task_text': 'put a mug in sink'}


# (public, private) in the pools' real shapes (what the writers' leakage corpus and references read)
SYNTHETIC_ITEMS = {
    'searchqa': lambda i: ({'question': 'Who wrote the article mentioned in item %s?' % i,
                            'context': 'Snippet for item %s: the article was written by Ada Lovelace in 1843.' % i},
                           {'answers': ['Ada Lovelace']}),
    'officeqa': lambda i: ({'question': 'What is the treasury total reported in item %s?' % i,
                            'context': 'Treasury table of item %s: receipts 30, transfers 12, total 42.' % i},
                           {'answer': '42'}),
    'zebralogic': lambda i: ({'question': 'There are 3 houses, numbered 1 to 3 from left to right, as seen from '
                                          'across the street. Each house is occupied by a different person (%s).' % i,
                              'columns': ['Name', 'Colour'], 'rows': 3}, {'answer': ZEBRA_GRID}),
    'spreadsheetbench': lambda i: ({'instruction': 'Workbook task: sum column B into cell B5 (%s).' % i,
                                    'input_files': [], 'answer_position': 'B5'}, {'test_files': []}),
    'alfworld': lambda i: ({'game_file': '/fake/games/%s/game.tw-pddl' % i, 'routing_view': _alfworld_view(i),
                            'routing_view_sha256': hashlib.sha256(i.encode('utf-8')).hexdigest()}, {}),
}


def synthetic_view(bench, item):
    """The routing view of a synthetic item as ``solver.routing_view`` would build it: ALFWorld's registered view,
    a preview-shaped sheet view (no workbook exists), the public part elsewhere."""
    public = item['public']
    if bench == 'alfworld':
        return public['routing_view']
    if bench == 'spreadsheetbench':
        return {'instruction': public['instruction'], 'workbook_preview': SHEET_PREVIEW}
    return public


# ---- the smoke run ---------------------------------------------------------------------------------------------
def smoke_root(root):
    root = Path(root)
    return root if root.name.endswith(SMOKE_SUFFIX) else root.with_name(root.name + SMOKE_SUFFIX)


def smoke_slices(items, slices):
    """SMOKE_SLICES prefixes of the prepared slices; the panel = held-out practice items (neither learn nor gate),
    the prepared 'panel' ids when present, else the first unused items of the source."""
    out = {}
    for bench, sizes in SMOKE_SLICES.items():
        prepared = slices.get(bench) or {}
        learn = list(prepared.get('learn') or [])[:sizes['learn']]
        gate = list(prepared.get('gate') or [])[:sizes['gate']]
        used = set(learn) | set(gate)
        panel = list(prepared.get('panel') or [])[:sizes['panel']]
        if not panel:
            panel = [item['task_id'] for item in items.get(bench, []) if item['task_id'] not in used][:sizes['panel']]
        require(len(learn) == sizes['learn'] and len(gate) == sizes['gate'] and len(panel) == sizes['panel']
                and not used & set(panel) and len(used) == len(learn) + len(gate),
                'The smoke needs %r disjoint learn/gate/panel practice ids on %s' % (sizes, bench))
        out[bench] = {'learn': learn, 'gate': gate, 'panel': panel}
    return out


def practice_panel(services):
    """The smoke's panel substitute: held-out practice items by id (no consent, no TestAccess)."""
    def panel_tasks(bench, unit):
        by_id = {item['task_id']: item for item in services.items[bench]}
        return [by_id[i] for i in services.slices[bench]['panel']]
    return panel_tasks


def smoke_manifest(root, *, fake, base_card=None, configured=False):
    """The smoke root's prepared manifest (``prepare --smoke``, which seals the base card); a fake smoke without one
    runs on the synthetic manifest (no /data at all) with ``base_card`` (addendum D17; the code default when None).
    A ``base_card`` given for a prepared root must be the one its manifest seals. ``configured`` (a fake smoke without
    a prepared manifest only): the synthetic manifest carries the typed-v2 smoke's values (``CONFIGURED``: economy
    reads with the probe, read-plan 4.3 S2), the base card ``base_card`` when one is given."""
    from . import prepare
    if (Path(root) / prepare.MANIFEST).exists():
        found = prepare.load_manifest(root)
        require(base_card is None or prepare.base_card_of(found) == base_card,
                'The smoke root %s was prepared with base_card %r, not %r: prepare a new smoke root'
                % (root, found.get('base_card'), base_card))
        require(not configured, 'A prepared smoke root runs on its own sealed values (configured is for a fake smoke)')
        return found
    require(fake, 'A real smoke needs the prepared manifest at ' + str(Path(root) / prepare.MANIFEST))
    if configured:
        return synthetic_manifest(**{**CONFIGURED, **({'base_card': base_card} if base_card is not None else {})})
    return synthetic_manifest(base_card=BASE_CARD_DEFAULT if base_card is None else base_card)


def run(root, chain, *, services=None, fake=False, manifest=None, scripted=None, resume=False, sleep=time.sleep,
        base_card=None, configured=False, stop_after_plan=False, fake_kill_at=None):
    """``chain.run`` on the smoke root with the smoke slices and limits. ``services``: ready services (fakes, or
    ``chain.real_services(..., smoke=True)``); without them the CLI form builds them from the smoke root's prepared
    manifest (``fake``: scripted fakes; a fake smoke without a prepared manifest uses the synthetic one, with
    ``base_card``: addendum D17, and the typed-v2 smoke's values when ``configured``). A ``base_card`` given must be
    the base of the manifest the smoke runs on (the chain state then refuses a resume of the same root with another
    base). The CLI form's automatic replay is the real child process (``replay_child``, R76); ``stop_after_plan``:
    R77; ``fake_kill_at``: one of ``readplan.CHECKPOINTS`` (R92, fakes only)."""
    from . import prepare
    require(fake_kill_at is None or (fake and fake_kill_at in readplan.CHECKPOINTS),
            'A kill point is one of %s and exists for a fake smoke only (R92)' % (readplan.CHECKPOINTS,))
    root = smoke_root(root)
    if services is None:
        manifest = manifest if manifest is not None else smoke_manifest(root, fake=fake, base_card=base_card,
                                                                        configured=configured)
        if fake:
            services = fake_services(root, chain, manifest, scripted=scripted, kill_at=fake_kill_at)
            services.replay = chain_.replay_child(fake=True, smoke=True, base_card=base_card,
                                                  kill_at=fake_kill_at)
        else:
            services = chain_.real_services(root, chain, manifest, smoke=True)
    require(base_card is None or prepare.base_card_of(services.manifest) == base_card,
            'The smoke runs on the manifest\'s base card, not %r' % (base_card,))
    services.root, services.chain, services.mode = root, chain, 'smoke'
    services.slices = smoke_slices(services.items, services.slices)  # reads.read_panel draws the smoke panel from them
    services.limits = dict(SMOKE_LIMITS)
    return chain_.run(root, chain, services=services, resume=resume, sleep=sleep, stop_after_plan=stop_after_plan)


# ---- scripted replies, embeddings, items -------------------------------------------------------------------------
def default_outcome(bench, item_id, mounted):
    """A deterministic judge token: items pass by hash, more often with a card, most often with a program."""
    bucket = int(hashlib.sha256((bench + '\x00' + item_id).encode('utf-8')).hexdigest()[:8], 16) % 100
    threshold = 45 + (30 if mounted.get('card_text') else 0) + (20 if mounted.get('enabled') else 0)
    return 'pass' if bucket < threshold else 'fail'


def default_selection(system, user):
    """Pick the first indexed skill (the index names are in the request's user JSON)."""
    skills = json.loads(user).get('skills') or []
    return json.dumps({'use': [skills[0]['name']] if skills else [], 'why': 'scripted: the first listed skill'})


def solver_purpose(system):
    if system == FIRST_CALL_SYSTEM:
        return 'first_call'
    return 'selection' if system == library_.SELECTION_SYSTEM else 'solver'


def receipt(text, *, model, system='', user=''):
    """A delivered receipt in the frozen client's shape (counts from text sizes; never a network call)."""
    prompt, completion = len(system + user) // 4 + 1, max(1, len(text) // 4)
    return {'ok': True, 'response': text, 'finish_reason': 'stop', 'returned_model': model, 'status': 200,
            'usage': {'prompt_tokens': prompt, 'completion_tokens': completion, 'total_tokens': prompt + completion},
            'usage_valid': True, 'reasoning_chars': 0, 'reasoning_tokens': 0, 'error_type': None,
            'attempts': [{'status': 200, 'seconds': 0.0}], 'seconds': 0.0}


class Script:
    """Scripted behaviour of the fakes. ``replies``: {purpose: text | [texts] | callable(system, user) -> text or a
    whole receipt dict}; purposes 'solver', 'selection', 'first_call', 'card_writer', 'program_writer' (default
    ``scripted_program_writer``), 'describer'. ``outcomes``: callable(bench, item_id, mounted) -> judge token.
    ``faults``: {procedure id: ids of items where it faults}. ``fires``: callable(bench, item_id, procedure) -> bool.
    ``items``: {bench: items} (synthetic when absent). ``echo``: {chain: echoed model id}. ``calls`` records
    (purpose, unit) of every send."""

    def __init__(self, scripted=None):
        scripted = dict(scripted or {})
        self.replies = {'solver': 'The answer is 42.', 'selection': default_selection, 'first_call': 'ready',
                        'card_writer': DEFAULT_CARD, 'program_writer': scripted_program_writer,
                        'describer': DEFAULT_DESCRIPTION, **(scripted.get('replies') or {})}
        self.outcomes = scripted.get('outcomes') or default_outcome
        self.faults = dict(scripted.get('faults') or {})
        self.fires = scripted.get('fires') or (lambda bench, item_id, procedure: True)
        self.items = scripted.get('items')
        self.echo = {'G': 'glm-5.3', 'D': 'deepseek-v4-flash', **(scripted.get('echo') or {})}
        self.lock, self.calls, self.counts = threading.Lock(), [], {}

    def reply(self, purpose, system, user, *, unit=None):
        with self.lock:
            self.calls.append((purpose, unit))
            index = self.counts.get(purpose, 0)
            self.counts[purpose] = index + 1
        value = self.replies[purpose]
        if callable(value):
            return value(system, user)
        if isinstance(value, list):
            return value[min(index, len(value) - 1)]
        return value

    def send(self, purpose, system, user, *, model, unit=None):
        """A receipt for one send: scripted text wrapped as delivered, or a scripted receipt dict as is."""
        value = self.reply(purpose, system, user, unit=unit)
        return value if isinstance(value, dict) else receipt(value, model=model, system=system, user=user)


def hash_embedder(texts, *, dim=EMBED_DIM):
    """Deterministic vectors: a strong direction from the text's first characters (one family per synthetic bench)
    plus a small per-text jitter, so a bench's items cluster around their own centroid."""
    rows = []
    for text in texts:
        family = hashlib.sha256(text[:FAMILY_CHARS].encode('utf-8')).digest()
        jitter = hashlib.sha256(text.encode('utf-8')).digest()
        rows.append([(family[i] - 128) / 128 + (jitter[i] - 128) / 1280 for i in range(dim)])
    return rows


def synthetic_manifest(*, sizes=SMOKE_SLICES, base_card=BASE_CARD_DEFAULT, schedule=SCHEDULE_DEFAULT,
                       memory_lock=MEMORY_LOCK_DEFAULT, read_plan=READ_PLAN_DEFAULT, read_plan_probe=None):
    """A manifest for ``smoke --fake`` without /data: ids per slice, fake pool pins, empty runtimes, echo ids, and
    the caps, the base card, the schedule and the memory lock a prepared manifest seals (the ledger takes its cap
    from the manifest; every mount and both writers take its base, addendum D17; the chain runs in its schedule,
    DESIGN 3.6), and its read plan with the smoke-only probe (read-plan R7; 'full' and no probe by default). No
    machinery record: a fake smoke is an unbound start and runs no machinery check."""
    require(type(base_card) is str and base_card in BASE_CARDS, 'A registered base card %s: %r' % (BASE_CARDS, base_card))
    require(type(schedule) is str and schedule in SCHEDULES, 'A registered schedule %s: %r' % (SCHEDULES, schedule))
    require(type(memory_lock) is str and memory_lock in MEMORY_LOCKS,
            'A registered memory lock %s: %r' % (MEMORY_LOCKS, memory_lock))
    readplan.check_read_plan(schedule, read_plan, read_plan_probe, smoke=True)
    slices = {bench: {part: ['%s-%s%d' % (bench, part[0], i) for i in range(count)] for part, count in parts.items()}
              for bench, parts in sizes.items()}
    return {'version': VERSION, 'configuration': CONFIGURATION, 'machinery': MACHINERY, 'mode': 'smoke',
            'evidence': 'engineering_fixture', 'seed': SEED, 'slices': slices, 'caps': dict(CAPS), 'base_card': base_card,
            'schedule': schedule, 'memory_lock': memory_lock, 'read_plan': read_plan,
            'read_plan_probe': None if read_plan_probe is None else list(read_plan_probe),
            'pools': {bench: {'path': '/fake/pools/%s.json' % bench,
                              'sha256': hashlib.sha256(bench.encode('utf-8')).hexdigest()} for bench in ORDER},
            'runtime': {bench: {} for bench in ORDER},
            'clients': {'solver': {'G': {'response_model_ids': ['glm-5.3']}},
                        'routes': {'D': {'B': {'response_model_ids': ['deepseek-flash', 'deepseek-v4-flash']}}}}}


def synthetic_items(manifest):
    """Practice items in the pools' shapes for every id the manifest's slices name (each bench's typing source)."""
    items = {}
    for bench in ORDER:
        parts = manifest['slices'].get(bench) or {}
        ids = [i for part in ('learn', 'gate', 'panel') for i in parts.get(part, [])]
        rows = []
        for i in ids:
            public, private = SYNTHETIC_ITEMS[bench](i)
            rows.append({'benchmark': bench, 'task_id': i, 'public': public, 'private': private})
        items[bench] = rows
    return items


# ---- the fake solve and services --------------------------------------------------------------------------------
def fake_request(bench, item, mounted):
    """The user message of a fake send: the frozen request rendering of the bench where it costs nothing
    (``solver._user``: the registered ZebraLogic template, the QA / sheet view JSON; ALFWorld's first step view), so
    the writers see trajectories in the registered shape; a synthetic JSON when the view cannot be rendered."""
    from skillopt.execskill import solver
    view = synthetic_view(bench, item)
    try:
        if bench == 'alfworld':
            observation = view['initial_observation']
            return json.dumps({'initial_observation': observation, 'observation': observation,
                               'admissible_commands': list(view['admissible_commands_at_reset']), 'recent_history': []},
                              ensure_ascii=False)
        return solver._user(bench, view)
    except Exception:  # noqa: BLE001 -- a fake request never fails a fake cell
        return json.dumps({'task_id': item['task_id'], 'signature': mounted.get('signature')}, sort_keys=True)


def repeat_of_tag(bench, item_id, arm, tag, *, limit=REPEAT_SEARCH):
    """The repeat r of a gate cell, None for a single-run cell. A gate cell's label ``<arm>#<r>`` reaches the solve
    only through its tag (``units.cell_tag``: the mount and the request see the mount arm alone, DESIGN 3.4), so the
    fake finds r by matching the tag."""
    for r in range(1, limit + 1):
        if units.cell_tag(bench, item_id, '%s#%d' % (arm, r)) == tag:
            return r
    return None


def fake_solve(script):
    """``mount.solve``'s record shape (design §5.5) from one scripted send: no worker, no scorer, no episode. The
    script's ``outcomes`` sees the mount record with the cell's ``repeat`` (``repeat_of_tag``; None for a single-run
    cell), so a test can make repeats of one item differ; the row's ``mount`` is the mount record unchanged."""
    def solve(bench, item, mounted, *, call, runtime, worker_factory=None, native=None, nominal_tokens=None, unit, tag,
              scorer_root, mode=None, step=None, episodes=None):
        found = call(mounted.get('system_card') or '', fake_request(bench, item, mounted))
        enabled = list(mounted.get('enabled') or [])
        fired = [p['id'] for p in enabled if script.fires(bench, item['task_id'], p)]
        faults = [{'procedure': p['id'], 'fault': 'exception'} for p in enabled
                  if item['task_id'] in script.faults.get(p['id'], ())]
        seen = {**mounted, 'repeat': repeat_of_tag(bench, item['task_id'], mounted.get('arm'), tag)}
        token = (script.outcomes(bench, item['task_id'], seen) if found.get('ok')
                 else 'unknown_' + str(found.get('error_type')))
        reply = found.get('response')
        return {'bench': bench, 'item_id': item['task_id'], 'arm': mounted.get('arm'),
                'mount': {k: v for k, v in mounted.items() if k not in ('enabled', 'card_text', 'system_card')},
                'public_hash': canonical_sha256(item['public']),  # as mount.solve's rows (ADV8; read-plan R41)
                'prediction_status': 'available' if found.get('ok') else 'unknown', 'output_excerpt': (reply or '')[:2000],
                'reply': reply, 'correct': None if token.startswith('unknown') else token == 'pass', 'token': token,
                'official': {'status': token, 'reason': 'scripted'}, 'format': {}, 'flags': [], 'fired': fired,
                'faults': faults, 'tokens': call.tokens(), 'sends': call.sends,
                'request_sha256': [s['request_sha256'] for s in call.sends], 'configuration_error': False,
                'infrastructure_unknown': call.infrastructure_unknown(), 'failure': None}
    return solve


def _modules(modules):
    if modules is not None:
        return modules
    return SimpleNamespace(**{name: importlib.import_module('skillopt.execskill.typed.' + name)
                              for name in ('mount', 'writers', 'reads')})


def fake_checkpoint(kill_at, *, child=False):
    """R92: the fake services' ``checkpoint(point)``: SIGKILL to this process group at the named point ('replay-child'
    only inside the replay child: the parent merely passes it on), so a parent and its replay child die together and
    nothing is flushed. None without a kill point."""
    if kill_at is None:
        return None
    require(kill_at in readplan.CHECKPOINTS, 'A registered kill point')

    def checkpoint(point):
        if point == kill_at and (point != 'replay-child' or child):
            sys.stdout.flush()
            os.killpg(os.getpgrp(), signal.SIGKILL)
    return checkpoint


def fake_solver_settings(chain, echo):
    """The fake clients' scripted solver settings (R75: fakes write their scripted values)."""
    return {bench: {'model': echo, 'route': 'fake', 'max_tokens': FAKE_SOLVER_BOUND, 'nominal_tokens': None,
                    'thinking': None, 'reasoning_effort': None, 'response_model_ids': [echo], 'read_timeout': None}
            for bench in ORDER}


def fake_services(root, chain, manifest, *, scripted=None, modules=None, kill_at=None, child=False):
    """Services for a local end-to-end run: scripted clients, hash embeddings, a fake solve, no Docker (the worker
    factory yields None), no slots or locks; the real mount / writers / reads code paths unless ``modules`` injects
    fakes. Views are the synthetic items' public parts (already view-shaped), so no runtime is read.

    The one place where fake ``chain.Services`` of the chain and smoke tests are built (Step 1 pass): every field of
    every area, the fakes' values named (``identity_fn``: the injected mount module's ``mount_identity``).
    ``cap`` None: ``run`` takes the manifest's sealed ``caps[chain]``;
    ``machinery_code`` None: an unbound start, no machinery check (only ``own_root``); ``container_scope`` None: no
    containers; ``heavy(bench, unit=None)`` takes no lock and ``lock_setting`` is None; ``limits`` = DEFAULT_LIMITS."""
    modules, script = _modules(modules), scripted if isinstance(scripted, Script) else Script(scripted)
    items, echo = script.items or synthetic_items(manifest), script.echo[chain]

    def mount_fn(bench, item, **kw):  # synthetic views are given, never derived through solver.routing_view
        return modules.mount.mount(bench, item, **{'view': synthetic_view(bench, item), **kw})

    def identity_fn(bench, item, **kw):  # DESIGN 3.4: the gate's zero-call identity, with the same synthetic view
        return modules.mount.mount_identity(bench, item, **{'view': synthetic_view(bench, item), **kw})
    services = chain_.Services(
        manifest=manifest, root=Path(root), chain=chain, mode='smoke', items=items, slices=manifest['slices'],
        runtime=manifest.get('runtime') or {}, embed=hash_embedder, solver_call=None, role_call=None,
        worker_factory=lambda bench, unit, tag: (lambda: None), native=None,
        heavy=lambda bench, unit=None: nullcontext(),
        mount_fn=mount_fn, solve_fn=fake_solve(script), view_fn=synthetic_view,
        write_card=chain_.card_writer(modules.writers),
        propose_programs=chain_.program_writer(modules.mount, modules.writers, chain), describe=modules.writers.describe,
        outcomes_for_writer=lambda cells, rows, *, bench, baseline=None: modules.writers.outcomes_for_writer(
            cells, rows, bench=bench, seed=SEED, baseline=baseline),
        read_panel=modules.reads.read_panel, nominal_tokens=lambda bench: None,
        limits=dict(chain_.DEFAULT_LIMITS), cap=None, machinery_code=None, container_scope=None, lock_setting=None,
        identity_fn=identity_fn)

    def solver_call(bench, unit, tag, *, transform=None, purpose='solve'):
        send = lambda system, user: script.send(solver_purpose(system), system, user, model=echo, unit=unit)
        return units.CallRecorder(send, services.ledger, max_tokens=FAKE_SOLVER_BOUND, tag=tag, unit=unit,
                                  out_path=chain_._calls_path(services, unit, tag, purpose), transform=transform)

    def role_call(purpose, unit, tag, max_tokens):
        send = lambda system, user: script.send(purpose, system, user, model='glm-5.3', unit=unit)
        return units.CallRecorder(send, services.ledger, max_tokens=max_tokens, tag=tag, unit=unit,
                                  out_path=chain_._calls_path(services, unit, tag, purpose))
    services.solver_call, services.role_call = solver_call, role_call
    services.script = script  # for inspection by the CLI and the tests
    services.solver_settings = fake_solver_settings(chain, echo)
    services.checkpoint = fake_checkpoint(kill_at, child=child)
    return services
