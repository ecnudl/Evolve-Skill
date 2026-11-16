"""typed-v2 step 7g (DESIGN 5; spec/identity.md 4; IMPLEMENTATION-ORDER Step 7): the ONE bound harness of typed-v2.

    python -I tests/typed2_bound_driver.py <snapshot> <tree> <scratch> [--missing MODULE:NAME]

A fresh interpreter (``-I``: neither this file's directory, the working directory nor PYTHONPATH is on ``sys.path``)
puts ``<tree>/scripts`` on the path, imports ``run_typed`` and binds the machinery with ``bind_machinery(<snapshot>,
<tree>)`` exactly as ``scripts/run_typed.py --machinery-snapshot`` does; no ``skillopt`` module is imported before.
Under the binding it imports every module of ``<tree>``'s typed package, runs ``machinery.check(real=True,
snapshot=<snapshot>)`` and then the cases of the areas, each on literal inputs: no model call, no network, no Docker,
no /data, nothing written outside ``<scratch>`` (a plain-named directory; the capture never creates its scorer path).

  scan     the static scan of the typed package equals REQUIRED (its skillopt part) and lies in SCRIPTS (its scripts
           part); the scripts modules of its import closure are exactly SCRIPTS; typed writes no frozen attribute;
  prompts  the ten program-writer system texts, rendered from the bound policy / profiles / package / notes, each
           equal to its pin, each holding its reply format; ``engineer_prompt.verify()`` through the bound screen;
  card     D2: 4,500 content characters (plus the final newline) pass the typed screen, 4,501 fail for length; the
           copied content screens agree with the bound ``v225_cards.card_violation`` on a content case;
  reply    D4: the two F6 reply shapes are read as the fenced program, which the bound screen passes;
  mount    D17 / D5 / RP12: ``mount_identity`` of C0, C, B and of an untyped F item under both base cards, on
           ZebraLogic and on SearchQA (whose historical card the bound ``v222_cards`` reads from the snapshot's
           fixtures), each equal to the hash of the system text ``mount`` composes;
  capture  read plan R19: the first SearchQA request of C0 and C captured through ``readplan.capture_first_request``
           with the real ``mount.solve`` and the bound solver (a ``CaptureCall``: one recorded send, no model);
  label    read plan T7 (R14, label neutrality; fix-c, review F1): one state whose SearchQA type offers a program with
           an ``applies`` and a note-writing ``before_call`` hook, mounted (arm F, the selector picking it) and solved
           through the real ``mount.solve`` and the bound shell, router and package under the read units of S3 and S5
           with a recording fake worker (the bound client's own load request at start; each hook run in process):
           equal selection requests, equal hook calls and argument hashes, equal solver request hashes for every send
           (the note inside), and load requests that differ only in ``package_sha256``, the unit label's one trace;
  origins  after all cases: every loaded skillopt module outside typed comes from the snapshot, every typed module
           from the tree, every scripts module is a pinned file of the snapshot, and check(real=True) still holds.

A refusal of ``bind_machinery`` or of the machinery check is a result, not a crash: the output names the stage and
the message. ``--missing`` adds a frozen name to REQUIRED before the check (the guard case "a missing private name";
the snapshot keeps its listed bytes, so only check 5 can see it). Prints one JSON line. Not a test module (no
``test_`` prefix): ``tests/test_typed2_machinery.py`` runs it.
"""
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

TYPED = 'skillopt.execskill.typed'
HOOKED = ('def applies(view):\n    return "question" in view\n\n\n'
          'def before_call(view, state):\n    return {"facts": ["the question names one entity"]}\n')
ENTRY = {'kind': 'new', 'description': 'Counts entity mentions', 'hooks': ['applies', 'before_call'],
         'max_note_chars': 600, 'replay_tests': []}
ZEBRA_QUESTION = ('There are 2 houses, numbered 1 to 2 from left to right, as seen from across the street. Each house '
                  'is occupied by a different person. Eric drinks milk. The milk drinker lives in house 1. Arnold '
                  'drinks tea.')
ITEMS = {
    'zebralogic': {'benchmark': 'zebralogic', 'task_id': 'fx-zebra-1',
                   'public': {'question': ZEBRA_QUESTION, 'columns': ['Name', 'Drink']},
                   'private': {'answer': {'House 1': {'Name': 'Eric', 'Drink': 'milk'},
                                          'House 2': {'Name': 'Arnold', 'Drink': 'tea'}}}},
    'searchqa': {'benchmark': 'searchqa', 'task_id': 'fx-searchqa-00',
                 'public': {'question': 'Which fixture town keeps the bell number 0?',
                            'context': 'Fixture note 0. The bell number 0 is kept in Fixtown 0; the bell number 100 '
                                       'is kept elsewhere.'},
                 'private': {'answers': ['Fixtown 0']}},
}


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _fence(tag, body):
    return '```%s\n%s```' % (tag, body)


def scan_case(machinery, tree):
    scan = machinery.frozen_uses(tree)
    machinery_uses = {module: names for module, names in scan['uses'].items() if module.split('.')[0] == 'skillopt'}
    scripts_uses = sorted(module for module in scan['uses'] if module.split('.')[0] == 'scripts')
    closure = [module for module in machinery.import_closure(scan['modules'], tree) if module.split('.')[0] == 'scripts']
    relative = lambda module: machinery.module_file(module, tree).relative_to(tree).as_posix()
    return {'required_equal': machinery_uses == {module: list(names) for module, names in machinery.REQUIRED.items()},
            'scripts_uses': scripts_uses, 'scripts_uses_pinned': all(relative(m) in machinery.SCRIPTS for m in scripts_uses),
            'closure_equal': sorted(relative(m) for m in closure) == sorted(machinery.SCRIPTS),
            'writes': scan['writes'], 'symbols': machinery.require_symbols()}


def prompt_case():
    from skillopt.execskill.typed import ORDER, engineer_prompt, replies
    texts = {(bench, purpose): engineer_prompt.system(bench, purpose)
             for bench in ORDER for purpose in engineer_prompt.PURPOSES}
    return {'rendered': len(texts), 'pinned': sum(_sha(text) == engineer_prompt.PINS[key] for key, text in texts.items()),
            'reply_format_inside': sum(replies.REPLY_FORMAT[purpose] in text for (_, purpose), text in texts.items()),
            'verify': engineer_prompt.verify()['version'] == engineer_prompt.PROMPT_VERSION}


def card_case():
    from skillopt.execskill import v225_cards
    from skillopt.execskill.typed import cards, mount
    common = dict(bench='zebralogic', corpus=None, shown=[], task_card='Solve the puzzle from its clues.',
                  format_block=mount.format_block('zebralogic'), practice_ids=['fx-zebra-1'])
    passed = cards.card_screen('a' * 4500 + '\n', **common)
    failed = cards.card_screen('a' * 4501 + '\n', **common)
    content = 'Keep the grid in a table.\nNever write <answer> tags before the end.\n'
    return {'passed': passed, 'failed': failed,
            'content': [cards.content_violation(content, **common), v225_cards.card_violation(content, **common)]}


def reply_case():
    from skillopt.execskill import policy
    from skillopt.execskill.typed import engineer_prompt, replies
    alias = _fence('json', json.dumps({'change': {'id': 'p1', 'description': 'Counts entity mentions'}}) + '\n')
    placeholder = _fence('json', json.dumps({'changes': [{'id': 'p1', 'source': 'PLACEHOLDER'}]}) + '\n')
    under_repair = {'entry': dict(ENTRY), 'source': 'import os\n\n' + HOOKED}
    read = []
    for manifest in (alias, placeholder):
        result = replies.read_fix(manifest + '\n\n' + _fence('python', HOOKED), change=under_repair)
        read.append(result['problem'] is None and len(result['records']) == 1
                    and result['records'][0]['source'] == HOOKED)
    return {'read': read, 'screen': [v.to_json() for v in policy.check(HOOKED, version=engineer_prompt.POLICY_VERSION)]}


def mount_case():
    from skillopt.execskill.typed import BASE_CARDS, library, mount, tasktypes
    rows = []
    for bench, item in sorted(ITEMS.items()):
        for base in BASE_CARDS:
            for arm in ('C0', 'C', 'B', 'F'):
                kw = dict(arm=arm, typemap=tasktypes.TypeMap(), library=library.Library(), vector=None,
                          base_card=base)                      # a new chain: the empty type map and library
                identity = mount.mount_identity(bench, item, **kw)
                mounted = mount.mount(bench, item, **kw)
                expected = {'C0': mount.format_block(bench), 'C': mount.historical_card(bench),
                            'B': mount.system_card(bench, '', base_card=base),
                            'F': mount.system_card(bench, '', base_card=base)}[arm]
                rows.append({'bench': bench, 'base': base, 'arm': arm, 'sha256': identity['system_card_sha256'],
                             'equal': identity['system_card_sha256'] == mounted['system_card_sha256'] == _sha(expected),
                             'offered': identity['programs_offered'], 'forced': identity['forced']})
    by = {(row['bench'], row['base'], row['arm']): row['sha256'] for row in rows}
    return {'rows': rows, 'all_equal': all(row['equal'] for row in rows),
            'historical_base_is_c': all(by[(b, 'historical', 'B')] == by[(b, 'historical', 'C')] ==
                                        by[(b, 'historical', 'F')] for b in ITEMS),
            'format_base_is_c0': all(by[(b, 'format', 'B')] == by[(b, 'format', 'C0')] == by[(b, 'format', 'F')]
                                     for b in ITEMS),
            'searchqa_card_differs_from_format': by[('searchqa', 'historical', 'C')] != by[('searchqa', 'format', 'C0')]}


def capture_case(scratch):
    from skillopt.execskill.typed import mount, readplan
    services = SimpleNamespace(solve_fn=mount.solve, runtime={'searchqa': {}}, native=None,
                               nominal_tokens=lambda bench: None, mode='test')
    item, found = ITEMS['searchqa'], {}
    for arm in ('C0', 'C'):
        mounted = mount.mount('searchqa', item, arm=arm, typemap=None, library=None, vector=None)
        first = [readplan.capture_first_request(services, 'searchqa', item, mounted, event=arm, smoke=True,
                                                chain_dir=Path(scratch) / 'G') for _ in range(2)]
        found[arm] = first
    return {'hashes': found, 'stable': all(len(set(v)) == 1 and readplan.is_hash(v[0]) for v in found.values()),
            'arms_differ': found['C0'][0] != found['C'][0],
            'scratch_untouched': not (Path(scratch) / 'G').exists()}


LABEL_UNITS = ('test-read-S3-searchqa', 'test-read-S5-searchqa')   # two events whose identities are equal (R14)
NOTE_FACT = 'the question names one entity'                         # what HOOKED's before_call writes
LABEL_ANSWER = '<answer>Fixtown 0</answer>'


class RecordingWorker:
    """T7's recording fake of the sandbox worker (no container): ``start`` records the load request the bound client
    itself would send (``client._entries`` and ``client._load_request``, so ``package_sha256`` is the label's only
    trace), ``call`` records (procedure, function, argument hash) and runs the hook in process on the literal
    source; ``ping`` and ``close`` record nothing."""

    def __init__(self, record):
        self.record, self.namespaces, self.restarts, self.cleanups = record, {}, [], []

    def start(self, package, *, kind, inputs_dir=None):
        from skillopt.execskill.sandbox import client
        entries = client._entries(package)
        self.record['load'].append(client._load_request(package, entries, {'kind': kind}))
        for entry in entries:
            namespace = {'__name__': 'procedure', '__builtins__': __builtins__}
            exec(compile(entry['source'], '<procedure %s>' % entry['id'], 'exec'), namespace)   # the literal HOOKED
            self.namespaces[entry['id']] = namespace
        return self

    def call(self, proc_id, fn, args, *, timeout_s, **kw):
        self.record['hooks'].append([proc_id, fn, _sha(json.dumps(list(args), sort_keys=True))])
        value = self.namespaces[proc_id][fn](*args)
        return {'ok': True, 'value': value, 'value_sha256': _sha(json.dumps(value, sort_keys=True)), 'cpu_ms': 0,
                'rss_kib': 0}

    def ping(self):
        return {'ok': True}

    def close(self):
        return None


def label_case(scratch):
    from skillopt.execskill.package import Procedure
    from skillopt.execskill.typed import library, mount, tasktypes, units
    item, vector = ITEMS['searchqa'], [1.0, 0.0, 0.0]
    typemap = tasktypes.TypeMap()
    sid = typemap.add_source({'path': '/fixture/searchqa.json', 'sha256': 'a' * 64}, 'question/context', [vector],
                             step=1)
    tid = typemap.new_type(sid, step=1)
    program = Procedure(id='fx-label', origin='searchqa', description='Counts entity mentions',
                        hooks=('applies', 'before_call'), source=HOOKED, evidence='engineering_fixture',
                        max_note_chars=600).to_json()
    skill = library.make_skill(skill_id='prog-%s-s1-a' % tid, name='entity-counter', kind='program', home_type=tid,
                               body={'procedure': program}, origin={'chain': 'G', 'step': 1, 'bench': 'searchqa'},
                               description='Counts entity mentions.')
    lib = library.Library()
    lib.add(skill)
    typemap.add_program(tid, skill['skill_id'], step=1)
    found = {}
    for unit in LABEL_UNITS:
        record, sends, selections = {'load': [], 'hooks': []}, [], []

        def selector(system, user, selections=selections):
            selections.append(_sha(system + '\x00' + user))
            return {'ok': True, 'response': json.dumps({'use': ['entity-counter'], 'why': 'fixture'}),
                    'usage': {'total_tokens': 0}}

        def call(system, user, sends=sends):
            sends.append((_sha(system + '\x00' + user), NOTE_FACT in system + user))
            return {'ok': True, 'response': LABEL_ANSWER, 'finish_reason': 'stop', 'returned_model': 'fixture',
                    'status': 200, 'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
                    'usage_valid': True, 'error_type': None}
        mounted = mount.mount('searchqa', item, arm='F', typemap=typemap, library=lib, vector=vector,
                              selector=selector, base_card='historical')
        row = mount.solve('searchqa', item, mounted, call=call, runtime={'searchqa': {}},
                          worker_factory=lambda record=record: RecordingWorker(record), unit=unit,
                          tag=units.cell_tag('searchqa', item['task_id'], 'F'),
                          scorer_root=Path(scratch) / 'G' / unit / 'transient', mode='test')
        found[unit] = {'enabled': list(mounted['programs_enabled']), 'selections': selections, 'load': record['load'],
                       'hooks': record['hooks'], 'sends': [digest for digest, _ in sends],
                       'noted': [noted for _, noted in sends], 'package': row['package_sha256'], 'fired': row['fired']}
    a, b = (found[unit] for unit in LABEL_UNITS)
    unlabelled = lambda loads: [{key: value for key, value in load.items() if key != 'package_sha256'} for load in loads]
    return {'enabled': [a['enabled'], b['enabled']], 'fired': [a['fired'], b['fired']],
            'hook_calls': [[proc, fn] for proc, fn, _ in a['hooks']], 'sends': [len(a['sends']), len(b['sends'])],
            'note_in_first_request': [a['noted'][:1], b['noted'][:1]],
            'selections_equal': bool(a['selections']) and a['selections'] == b['selections'],
            'hooks_equal': bool(a['hooks']) and a['hooks'] == b['hooks'],
            'sends_equal': bool(a['sends']) and a['sends'] == b['sends'],
            'loads': [len(a['load']), len(b['load'])],
            'loads_equal_but_package': unlabelled(a['load']) == unlabelled(b['load']),
            'load_packages': [[load['package_sha256'] for load in a['load']] == [a['package']],
                              [load['package_sha256'] for load in b['load']] == [b['package']]],
            'packages_differ': a['package'] != b['package'],
            'scratch_untouched': not (Path(scratch) / 'G').exists()}


def origins(machinery, snapshot, tree):
    snapshot_root, typed_root = snapshot / 'skillopt', tree / 'skillopt' / 'execskill' / 'typed'
    counts, outside = {'machinery': 0, 'typed': 0, 'scripts': 0}, []
    for name, module in sorted(sys.modules.items()):
        top = name.split('.')[0]
        if module is None or top not in ('skillopt', 'scripts'):
            continue
        file = getattr(module, '__file__', None)
        places = [Path(file).resolve()] if file else [Path(p).resolve() for p in getattr(module, '__path__', ())]
        typed = name == TYPED or name.startswith(TYPED + '.')
        base = typed_root if typed else snapshot_root if top == 'skillopt' else snapshot / 'scripts'
        if places and all(place == base or base in place.parents for place in places):
            counts['typed' if typed else 'machinery' if top == 'skillopt' else 'scripts'] += 1
        else:
            outside.append(name)
    binding = machinery.loaded()
    return {'counts': counts, 'outside': outside, 'misplaced': machinery.misplaced(binding),
            'misplaced_scripts': machinery.misplaced_scripts(binding), 'binding': binding}


def main(argv):
    snapshot, tree, scratch = (Path(value).resolve() for value in argv[:3])
    missing = argv[argv.index('--missing') + 1] if '--missing' in argv else None
    sys.path.insert(0, str(tree / 'scripts'))
    out = {'stage': 'bind', 'preloaded': sorted(n for n in sys.modules if n.split('.')[0] in ('skillopt', 'scripts'))}
    import run_typed
    try:
        out['binding'] = run_typed.bind_machinery(snapshot, tree)
    except ValueError as error:
        out['refused'] = str(error)
        return out
    out['stage'] = 'import'
    stems = sorted(path.stem for path in (tree / 'skillopt' / 'execskill' / 'typed').glob('*.py'))
    for stem in stems:
        importlib.import_module(TYPED if stem == '__init__' else TYPED + '.' + stem)
    out['typed_modules'] = stems
    from skillopt.execskill.typed import machinery
    if missing:
        module, name = missing.split(':')
        machinery.REQUIRED[module] = tuple(machinery.REQUIRED.get(module, ())) + (name,)
    out['stage'] = 'check'
    try:
        out['record'] = machinery.check(real=True, snapshot=str(snapshot))
    except ValueError as error:
        out['refused'] = str(error)
        return out
    out['stage'] = 'cases'
    out['cases'] = {'scan': scan_case(machinery, tree), 'prompts': prompt_case(), 'card': card_case(),
                    'reply': reply_case(), 'mount': mount_case(), 'capture': capture_case(scratch),
                    'label': label_case(scratch)}
    out['final_check'] = machinery.check(real=True, snapshot=str(snapshot)) == out['record']
    out['origins'] = origins(machinery, snapshot, tree)
    out['stage'] = 'done'
    return out


if __name__ == '__main__':
    print(json.dumps(main(sys.argv[1:]), sort_keys=True, default=str))
