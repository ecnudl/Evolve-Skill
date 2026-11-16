"""typed-v3 item bank CLI (skillopt/execskill/typed/bank/; docs/handoff/typed-v3/BANK-PILOT.md).

    python scripts/run_bank.py [--machinery-snapshot P] prepare    --root R --typed-manifest M [--cap N]
    python scripts/run_bank.py [--machinery-snapshot P] carry      --root R --from-root OLD
    python scripts/run_bank.py [--machinery-snapshot P] oqa-trace  --root R [--limit N] [--width W]
    python scripts/run_bank.py [--machinery-snapshot P] oqa-twins  --root R
    python scripts/run_bank.py [--machinery-snapshot P] oqa-check  --root R [--limit N] [--width W]
    python scripts/run_bank.py [--machinery-snapshot P] research   --root R --bench officeqa
    python scripts/run_bank.py [--machinery-snapshot P] oqa-newq   --root R [--arms plain,brief,target] [--limit N]
    python scripts/run_bank.py [--machinery-snapshot P] oqa-diagnose --root R
    python scripts/run_bank.py [--machinery-snapshot P] oqa-audit  --root R [--scope calibration|unverified|questions|all]
    python scripts/run_bank.py [--machinery-snapshot P] oqa-contrast --root R --config NAME (--card c0|c | --card-file F)
                                                           [--runs R] [--side judge] [--solver-chain G|D]
    python scripts/run_bank.py [--machinery-snapshot P] oqa-contrast --root R --cards NAME=FILE,NAME=FILE --runs R
                               --side judge --chain-dir D --step K   (a re-judging: needs the passing oqa-parity
                               record of that step; the configurations meet each item together)
    python scripts/run_bank.py [--machinery-snapshot P] oqa-contrast-report --root R --config NAME [--base c]
    python scripts/run_bank.py [--machinery-snapshot P] oqa-report --root R
    python scripts/run_bank.py [--machinery-snapshot P] spare-contrast --root R --bench B --chain-dir D --step K
                               --cards c,NAME=FILE[,NAME=FILE] [--runs 3] [--limit N]
    python scripts/run_bank.py [--machinery-snapshot P] spare-report --root R --bench B --config NAME [--base c]
    python scripts/run_bank.py [--machinery-snapshot P] spare-parity --root R --bench B --chain-dir D --step K
                               --cards c,NAME=FILE[,NAME=FILE]      (no call; exit 2 unless every request agrees)
    python scripts/run_bank.py [--machinery-snapshot P] oqa-parity --root R --chain-dir D --step K
                               --cards NAME=FILE[,NAME=FILE] --base NAME --base-unit UNIT
                               (no call; exit 2 unless every request agrees; the base against the unit the step's
                               card gate used as its baseline, every other card against the round that wrote it)
    python scripts/run_bank.py [--machinery-snapshot P] sheet-ref  --root R [--styles a,b] [--limit N] [--width W]
    python scripts/run_bank.py [--machinery-snapshot P] sheet-twins --root R [--limit N]
    python scripts/run_bank.py [--machinery-snapshot P] sheet-newtask --root R [--arms plain,brief] [--per-parent K]
    python scripts/run_bank.py [--machinery-snapshot P] sheet-report --root R
    python scripts/run_bank.py [--machinery-snapshot P] zebra-language --root R
                               (no call: the ZebraLogic puzzle language, learned from the pinned practice pool and
                               proved on it: every pool puzzle written back exactly and solved to its reference alone)
    python scripts/run_bank.py [--machinery-snapshot P] zebra-make --root R [--per-size 30] [--shown-per-size 10]
                               (no call: new puzzles of the judged sizes, each certified from its text by two
                               solvers: exactly one solution, the stored grid, no clue that can be left out)
    python scripts/run_bank.py [--machinery-snapshot P] zebra-report --root R
                               (no call: counts, and made against real puzzles on a reference sample)
    python scripts/run_bank.py [--machinery-snapshot P] zebra-parity --root R --chain-dir D --step K --cards c,NAME=FILE
                               [--solver-chain G|D]   (no call; exit 2 unless every request agrees with the run's)
    python scripts/run_bank.py [--machinery-snapshot P] zebra-contrast --root R --chain-dir D --step K
                               --cards c,NAME=FILE --runs N [--solver-chain G|D] [--width W]
                               (the configurations on the run's gate items AND the made puzzles of the judging side)
    python scripts/run_bank.py [--machinery-snapshot P] zebra-contrast-report --root R --base c --config NAME
                               [--solver-chain G|D]   (chain G's stage runs only after chain D's check of the same
                               bank was read PARITY and REPRODUCED; the report of chain D's check records that)
    python scripts/run_bank.py [--machinery-snapshot P] status     --root R

The bank has its OWN root (never a chain root), its own ledger and cap. ``prepare`` pins what the bank is built
from: the training-side pool of a typed manifest (path and sha256), that manifest's learn / gate slices (a parent of
the learn slice gives items SHOWN to writers, a parent of the gate slice items kept for JUDGING), the bench runtime
and hand card of the checker, and the hashes of the bank's code. Nothing test-side is opened: the page-overlap flag
uses the id manifest's page references only (ids, source file, page number; no question, no answer).

``research`` is the only stage that reaches the web: the English Wikipedia API, the arXiv API and HTML pages, and
the Stack Exchange API, through the one explicit credential-free gateway of the model clients; every page is
archived before use and a page naming a benchmark is never shown to a role (bank/research.py).

Every stage writes ``<root>/stages/<stamp>-<command>.json`` with the hashes of the bank code it ran with: a pilot
root may see more than one code version, and the stage log says which stage ran with which (BANK-PILOT B13).

``oqa-diagnose`` reads the checker's replies on the REAL parents of the shown side that it failed and names the
weaknesses behind them (the ``target`` arm of ``oqa-newq`` writes questions against them); ``oqa-audit`` checks the
meaning of derivations, first on the calibration set (what is known right and wrong), then on the new questions
(BANK-PILOT B23, B24).

``oqa-contrast`` runs the solver with ANOTHER system card on the real parents and on the made items whose answers
something vouches for (confirmed twins, verified or audited questions): ``--card c0`` is the chain's arm C0 (the
answer-format block alone), ``--card c`` the hand card; ``--card-file F`` mounts the learned card text of F on the
hand card the way a chain does (``typed.mount.system_card``, base 'historical'). ``--solver-chain D`` sends the
requests to chain D's solver model (two configurations to compare must use the same one; the checker itself, base
``c``, is chain G's). ``oqa-contrast-report`` compares a configuration
with the checker (``--base c``, the hand card alone) or with another configuration, on first runs, real against
made: the instrument check of the design (section 6.3) and the re-judging of a card on more items. With
``--runs 3 --side judge`` a configuration gets a gate arm's three runs per item on the judging side; the report of
two such configurations adds the chain's own gate rule (``typed.gatestats``) on real, made and all judging items.

``carry`` (right after ``prepare``, before any stage) copies the stored calls of an earlier bank root: the stages of
the new root then compute everything again with the new code and send only the requests that the earlier root did
not send in the same words. Every model stage prints how many requests were answered from stored replies.

``sheet-ref``, ``sheet-twins`` and ``sheet-newtask`` run programs in the benchmark's sandbox and score them with
the benchmark's scorer; each run and each scoring holds the machine-wide memory lock exclusively and one native
slot, so it waits for (and holds up) every sheet and ALFWorld unit of a chain on the same machine: start them only
when no chain works there. ``sheet-newtask`` needs no reference program of the parent: its two programs are written
for the new instruction (bank/sheet_build.py).

A model stage that stops (token cap, an infrastructure failure, an interruption) is run again with the same command.
Exit codes: 0 done, 3 stopped by the ledger, 4 some tasks have no verdict yet (run the stage again).
"""
import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

TREE = Path(__file__).resolve().parents[1]
COMMANDS = ('prepare', 'carry', 'oqa-trace', 'oqa-twins', 'oqa-check', 'research', 'oqa-newq', 'oqa-diagnose',
            'oqa-audit', 'oqa-contrast', 'oqa-contrast-report', 'oqa-parity', 'oqa-report', 'spare-contrast',
            'spare-report', 'spare-parity', 'sheet-ref', 'sheet-twins', 'sheet-newtask', 'sheet-report',
            'zebra-language', 'zebra-make', 'zebra-report', 'zebra-parity', 'zebra-contrast',
            'zebra-contrast-report', 'status')
DEFAULT_CAP = 20_000_000


def bind(snapshot):
    import run_typed  # bare name: this directory is sys.path[0]; in a bound process ``scripts`` is the snapshot's
    if snapshot:
        info = run_typed.bind_machinery(snapshot, TREE)
    else:
        run_typed.ensure_tree_importable(TREE)
        info = {'snapshot': None, 'tree': str(TREE)}
    run_typed.clean_environment()
    return run_typed, info


def code_identity():
    from skillopt.execskill.typed.bank import env
    files = sorted((TREE / 'skillopt' / 'execskill' / 'typed' / 'bank').glob('*.py')) + [Path(__file__).resolve()]
    return {str(path.relative_to(TREE)): env.file_sha256(path) for path in files}


def machinery_identity():
    """Where the fixed tools were imported from, with their hashes (the judge, the solver request, the evaluator)."""
    from skillopt.continual_eval import backends
    from skillopt.envs.officeqa import evaluator
    from skillopt.execskill import compute, v222_cards
    from skillopt.execskill.typed.bank import env
    return {module.__name__: {'file': module.__file__, 'sha256': env.file_sha256(module.__file__)}
            for module in (backends, evaluator, compute, v222_cards)}


def pages_outside_pool():
    """{(source file, page)} named by the id manifest for the items that are NOT in the practice pool. Page
    references only: the manifest holds ids, source files and source URLs, no question and no answer."""
    from skillopt.envs.officeqa import tool_runtime
    folder = TREE / 'data' / 'officeqa_id_split'
    part = [name for name in ('train', 'val') if (folder / name / 'items.json').exists()]
    assert part == ['train', 'val'], 'The id manifest holds the two pool parts'
    outside = sorted(p.name for p in folder.iterdir() if p.is_dir() and p.name not in part)
    refs = set()
    for name in outside:
        for row in json.loads((folder / name / 'items.json').read_text()):
            refs |= {(file, page) for file, page, _ in tool_runtime._iter_oracle_refs(row['source_files'],
                                                                                         row['source_docs'])}
    categories = {row['uid']: row.get('category') for name in part
                  for row in json.loads((folder / name / 'items.json').read_text())}
    return refs, categories


def load_bank(root):
    from skillopt.execskill.typed import units
    return units.read_json(Path(root) / 'bank.json')


def log_stage(a):
    from skillopt.execskill.typed import units
    stamp = time.strftime('%Y%m%dT%H%M%S')
    units.write_json(Path(a.root) / 'stages' / ('%s-%s.json' % (stamp, a.command)), {
        'command': a.command, 'at': stamp, 'code': code_identity(), 'binding': a.binding,
        'arguments': {key: getattr(a, key) for key in ('limit', 'width', 'bench', 'arms', 'styles', 'per_parent',
                                                         'scope', 'config', 'base', 'card_file', 'runs',
                                                         'side', 'card', 'solver_chain', 'chain_dir', 'step',
                                                         'cards', 'base_unit', 'per_size', 'shown_per_size')}})


def pool_items(bank, bench):
    from skillopt.execskill.typed import prepare as typed_prepare
    pin = bank['pools'][bench]
    items, _ = typed_prepare.load_pool(bench, bank['pools_root'], pin={'path': pin['path'], 'sha256': pin['sha256']})
    return items


def command_prepare(a):
    from skillopt.execskill import v222_cards
    from skillopt.execskill.typed import prepare as typed_prepare, units
    from skillopt.execskill.typed.bank import BENCHES, ROLE_MAX_TOKENS, SEED, SIDES, VERSION, env, oqa
    root = Path(a.root)
    assert not (root / 'bank.json').exists(), 'This bank root is already prepared'
    manifest = typed_prepare.verify(json.loads(Path(a.typed_manifest).read_text()))   # contents against their seal
    pools, sides, counts = {}, {}, {}
    for bench in BENCHES:
        pin = manifest['pools'][bench]
        items, pools[bench] = typed_prepare.load_pool(bench, manifest['pools_root'],
                                                      pin={'path': pin['path'], 'sha256': pin['sha256']})
        ids = [item['task_id'] for item in items]
        slices = manifest['slices'][bench]
        sides[bench] = {**{i: SIDES[0] for i in slices['learn']}, **{i: SIDES[1] for i in slices['gate']}}
        assert sorted(sides[bench]) == sorted(ids) and not set(slices['learn']) & set(slices['gate']), \
            'Every parent of %s has one side' % bench
        counts[bench] = {side: sum(v == side for v in sides[bench].values()) for side in SIDES}
        if bench == 'officeqa':
            officeqa = items
    outside, categories = pages_outside_pool()
    shared = sorted(item['task_id'] for item in officeqa if oqa.pages_of(item['public']['context']) & outside)
    bank = {
        'version': VERSION, 'prepared_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'root': str(root.absolute()),
        'seed': SEED, 'cap': a.cap, 'role_max_tokens': ROLE_MAX_TOKENS,
        'typed_manifest': {'path': str(Path(a.typed_manifest).absolute()), 'record_sha256': manifest.get('record_sha256'),
                           'version': manifest.get('version')},
        'pools_root': manifest['pools_root'], 'pools': pools, 'sides': sides, 'side_counts': counts,
        'categories': {'officeqa': {item['task_id']: categories.get(item['task_id']) for item in officeqa}},
        'shared_pages': {'officeqa': shared}, 'outside_pool_page_refs': len(outside),
        'runtime': {bench: manifest['runtime'][bench] for bench in BENCHES}, 'slot_root': manifest.get('slot_root'),
        'card_sha256': {bench: env.text_sha256(v222_cards.historical_text(bench)) for bench in BENCHES},
        'code': code_identity(), 'machinery': machinery_identity(), 'binding': a.binding,
    }
    units.write_json(root / 'bank.json', bank)
    print(json.dumps({k: bank[k] for k in ('version', 'root', 'cap', 'side_counts', 'outside_pool_page_refs')}, indent=1))
    print('officeqa parents %d, sharing a page with a page reference outside the pool: %d' % (len(officeqa), len(shared)))
    return 0


def sheet_tools(a, bank):
    """The benchmark's own sandbox run and scorer for a reference program, each under the machine-wide memory lock
    (exclusive, as every sheet cell takes it) and a native slot -- the way a solver cell's program is run and
    judged. The runtime, the sandbox measurements and the slot root are read from the typed manifest the bank was
    prepared from."""
    import base64
    import copy
    from skillopt.continual_eval import backends
    from skillopt.execskill import chain as route_b_chain, code_delivery, manifest as route_b_manifest, slots
    from skillopt.execskill.typed import mount
    typed = typed_manifest_of(bank)
    runtime, slot_root = typed['runtime']['spreadsheetbench'], typed['slot_root']
    sizes = route_b_manifest._slot_sizes({'configuration': 'main-v10', 'sandbox': typed['sandbox']})
    native = slots.pools(slot_root, sizes=sizes)[slots.NATIVE]
    setting = SimpleNamespace(extra={'slot_root': slot_root, 'configuration': 'default'})
    heavy = lambda: route_b_chain.heavy(setting, 'spreadsheetbench')
    scorer_root = Path(a.root) / 'spreadsheetbench' / 'scores'

    def run(program, input_path):
        with heavy(), native.hold():
            return backends._native({'operation': 'spreadsheet_generate', 'code': program,
                                     'input_base64': base64.b64encode(backends._xlsx_bytes(input_path)).decode()}, runtime)

    def score(item, program, cases, tag):
        prediction = {'status': 'available', 'output': {'code': program, 'cases': cases}, 'costs': {},
                      'reason': 'generated_once_executed_per_public_case'}
        with heavy():
            return mount._sheet_score({'public': item['public'], 'private': item['private']}, prediction,
                                      copy.deepcopy(runtime), native=native, unit='itembank', tag=tag,
                                      scorer_root=scorer_root)[0]

    return {'run': run, 'score': score, 'extract': code_delivery.extract_python}


def open_env(a, bank, *, clients):
    from skillopt.execskill.typed import units
    from skillopt.execskill.typed.bank import env as bank_env
    path = Path(a.root) / 'ledger.json'
    ledger = units.Ledger(path, bank['cap'], resume=path.exists())
    return bank_env.BankEnv(a.root, ledger, clients, width=a.width)


def make_clients(a, run_typed, bank, *, solver):
    """The bank's role client (chain G's role model) and, for the stages that solve, a solver client: chain G's by
    default (the checker), chain D's for a contrast run with ``--solver-chain D`` (its credentials are read by the
    frozen client code from the registered path; nothing of them is read or printed here)."""
    inputs = run_typed.run_inputs(None, 'G', roles_repo=a.roles_repo)
    clients = {'role': inputs['clients']['role'](bank['role_max_tokens'])}
    if solver:
        chain = a.solver_chain if a.command in ('oqa-contrast', 'zebra-contrast') else 'G'
        source = inputs if chain == 'G' else run_typed.run_inputs(None, chain, roles_repo=a.roles_repo)
        bench = a.bench if a.command == 'spare-contrast' else 'zebralogic' if a.command == 'zebra-contrast' else 'officeqa'
        clients['solver'] = source['clients']['solver'](bench)[0]
    return clients


def read_card(path):
    """A card text VERBATIM (a run mounts a writer's text as stored, final newline included: a stripped text
    would be another system card)."""
    text = Path(path).read_text(encoding='utf-8')
    assert text.strip(), 'An empty card file: ' + str(path)
    return text


def read_cards(spec):
    """``c,NAME=FILE,...`` -> {configuration name: card text, or None for 'c' (the hand card alone)}."""
    cards = {}
    for part in [p for p in (spec or '').split(',') if p]:
        name, _, path = part.partition('=')
        assert name not in cards and (name == 'c') == (not path), 'Configurations: c (the hand card) or NAME=FILE'
        cards[name] = read_card(path) if path else None
    assert cards, 'A list of configurations: --cards'
    return cards


def typed_manifest_of(bank):
    """The typed manifest the bank was prepared from: read again, its seal recomputed from its contents
    (``typed.prepare.verify``) and compared with the seal the bank pinned at ``prepare``."""
    from skillopt.execskill.typed import prepare as typed_prepare
    manifest = typed_prepare.verify(json.loads(Path(bank['typed_manifest']['path']).read_text()))
    assert manifest['record_sha256'] == bank['typed_manifest']['record_sha256'], 'The typed manifest changed'
    return manifest


def request_identity(a, runtime):
    """What decides how this process builds a request besides the item and the card: the runtime table, this
    tree's bank code, the bound machinery's files and the binding (which snapshots the modules came from)."""
    from skillopt.execskill.typed.bank import rejudge
    return rejudge.request_identity(runtime, {'code': code_identity(), 'machinery': machinery_identity(),
                                              'binding': a.binding})


def step_dir_of(a):
    """``<chain dir>/s<k>`` of a typed run: one learning step (practice side; no read unit lives in it)."""
    assert a.chain_dir and a.step >= 1, 'A chain directory of a typed run and a learning step: --chain-dir, --step'
    path = Path(a.chain_dir) / ('s%d' % a.step)
    assert path.is_dir(), 'No such learning step: ' + str(path)
    return path


def spare_setup(a, bank):
    """The typed manifest the bank was prepared from (unchanged since), the spare items of ``a.bench`` in the run's
    ranking, and the chain's own cell tools (``typed.mount``, the manifest's runtime table; chain G: no nominal
    token bound)."""
    from skillopt.coevo5 import data
    from skillopt.execskill.typed import mount, prepare as typed_prepare
    from skillopt.execskill.typed.bank import spare
    manifest = typed_manifest_of(bank)
    items = spare.spare_items(manifest, a.bench, load_pool=typed_prepare.load_pool, ranked=data.ranked,
                              slice_tag=typed_prepare.SLICE_TAG)
    return manifest, items, {'mount': mount, 'runtime': manifest['runtime'], 'nominal_tokens': None}


def zebra_tools(a, bank):
    """For a ZebraLogic contrast (BANK-PILOT B31): the run's gate items and the chain's own cell tools. The nominal
    token bound is the one the run's chain used for the bench (its ``solver-settings.json``; chain G: none), and
    the chain of --chain-dir must be the chain of --solver-chain. The request identity names the chain and the
    bound too, so a parity record of one chain authorises no stage of the other."""
    from skillopt.execskill.typed import mount, prepare as typed_prepare, units
    from skillopt.execskill.typed.bank import rejudge, spare
    manifest = typed_manifest_of(bank)
    assert a.chain_dir, 'A chain directory of a typed run: --chain-dir'
    settings = units.read_json(Path(a.chain_dir) / 'solver-settings.json')
    assert settings.get('chain') == a.solver_chain, 'The chain directory is not of the chain --solver-chain'
    tools = {'mount': mount, 'runtime': manifest['runtime'],
             'nominal_tokens': settings['benches']['zebralogic'].get('nominal_tokens')}
    identity = rejudge.request_identity(tools['runtime'], {
        'code': code_identity(), 'machinery': machinery_identity(), 'binding': a.binding,
        'solver_chain': a.solver_chain, 'nominal_tokens': tools['nominal_tokens']})
    gate = spare.gate_items(manifest, 'zebralogic', load_pool=typed_prepare.load_pool)
    return gate, tools, identity


def limited(items, limit):
    return items if not limit else items[:limit]


def command_model(a, run_typed):
    from skillopt.continual_eval import backends
    from skillopt.execskill import v222_cards
    from skillopt.execskill.typed import units
    from skillopt.execskill.typed.bank import ARMS, oqa_build
    bank = load_bank(a.root)
    # stages whose result is a statistic of the whole bank (a calibration, a diagnosis, a comparison) take no limit
    assert not (a.limit and a.command in ('oqa-audit', 'oqa-diagnose', 'oqa-contrast')), a.command + ' takes no --limit'
    log_stage(a)
    bench = 'spreadsheetbench' if a.command.startswith('sheet-') else 'officeqa'
    items = None if a.command in ('spare-contrast', 'zebra-contrast') else limited(pool_items(bank, bench), a.limit)
    env = open_env(a, bank, clients=make_clients(a, run_typed, bank, solver=a.command in (
        'oqa-check', 'oqa-contrast', 'spare-contrast', 'zebra-contrast')))
    try:
        if a.command == 'zebra-contrast':
            from skillopt.execskill.typed.bank import zebra_check
            assert not a.limit and 2 <= a.runs <= 5, 'zebra-contrast takes no --limit and needs --runs 2..5'
            gate, tools, identity = zebra_tools(a, bank)
            result = zebra_check.stage_contrast(env, tools, gate, read_cards(a.cards), step_dir=step_dir_of(a),
                                                identity=identity, runs=a.runs, solver=a.solver_chain)
        elif a.command == 'spare-contrast':
            from skillopt.execskill.typed.bank import spare
            assert a.solver_chain == 'G', 'Spare items are solved by chain G (the cards re-judged are chain G\'s)'
            _, spare_pool, tools = spare_setup(a, bank)
            result = spare.stage_spare(env, tools, a.bench, limited(spare_pool, a.limit), read_cards(a.cards),
                                       step_dir=step_dir_of(a), identity=request_identity(a, tools['runtime']),
                                       runs=a.runs or spare.GATE_REPEATS, solver=a.solver_chain)
        elif a.command == 'sheet-twins':
            from skillopt.execskill.typed.bank import sheet_build
            result = sheet_build.stage_twins(env, sheet_tools(a, bank), items, bank['sides']['spreadsheetbench'])
            if result['parents_without_a_verdict']:
                result['note'] = 'unknown: some parents have no verdict'
        elif a.command == 'sheet-newtask':
            from skillopt.execskill.typed.bank import sheet_build
            arms = [arm for arm in a.arms.split(',') if arm]
            assert arms and set(arms) <= set(ARMS), 'Arms among ' + str(sorted(ARMS))
            brief = None
            if 'brief' in arms:
                made = env.read('research', 'spreadsheetbench', 'brief.json')
                assert made.get('shown'), 'The brief arm needs a research brief: run research --bench spreadsheetbench'
                brief = made['shown']
            result = sheet_build.stage_newtask(env, sheet_tools(a, bank), items, bank['sides']['spreadsheetbench'],
                                               arms, a.per_parent, brief)
        elif a.command == 'sheet-ref':
            from skillopt.execskill.typed.bank import prompts, sheet_build
            styles = [style for style in a.styles.split(',') if style]
            assert styles and set(styles) <= set(prompts.SHEET_STYLES), 'Styles among ' + str(sorted(prompts.SHEET_STYLES))
            result = sheet_build.stage_ref(env, sheet_tools(a, bank), items, styles)
        elif a.command == 'oqa-trace':
            result = oqa_build.stage_trace(env, items)
        elif a.command == 'research':
            try:
                result = command_research(a, run_typed, env)
            except units.Stop:
                raise
            except RuntimeError as failed:          # a role call failed for an infrastructure reason: run it again
                result = {'research': str(failed)[:200]}
        elif a.command == 'oqa-newq':
            arms = [arm for arm in a.arms.split(',') if arm]
            assert arms and set(arms) <= set(ARMS), 'Arms among ' + str(sorted(ARMS))
            brief = None
            if 'brief' in arms:
                made = env.read('research', 'officeqa', 'brief.json')
                assert made.get('shown'), 'The brief arm needs a research brief: run the research stage first'
                brief = made['shown']
            weaknesses = None
            if 'target' in arms:
                merged = env.read('officeqa', 'diagnosis', 'weaknesses.json')
                assert merged.get('shown'), 'The target arm needs merged weaknesses: run oqa-diagnose first'
                weaknesses = merged['shown']
            result = oqa_build.stage_newq(env, items, bank['sides']['officeqa'], bank['shared_pages']['officeqa'],
                                          arms, brief, weaknesses)
        elif a.command == 'oqa-contrast' and a.cards:
            # a re-judging (B26): several card files in ONE stage, allowed only after a passing oqa-parity
            from skillopt.execskill.typed import mount
            assert not (a.config or a.card or a.card_file), '--cards replaces --config, --card and --card-file'
            texts = read_cards(a.cards)
            assert 'c' not in texts, 'Every configuration of --cards is NAME=FILE (a card text on the hand card)'
            tools = {'solve': backends.solve, 'score': backends._score_answer_tag, 'runtime': bank['runtime']['officeqa'],
                     'system_card': lambda text: mount.system_card('officeqa', text, base_card='historical')}
            result = oqa_build.stage_rejudge(env, tools, items, texts, runs=a.runs, side=a.side or None,
                                             sides=bank['sides']['officeqa'], solver=a.solver_chain,
                                             step_dir=step_dir_of(a), identity=request_identity(a, tools['runtime']))
        elif a.command == 'oqa-contrast':
            from skillopt.execskill.typed import mount
            assert bool(a.card_file) != bool(a.card), 'One of --card-file F and --card c0|c'
            if a.card_file:
                card = mount.system_card('officeqa', read_card(a.card_file), base_card='historical')
            else:
                assert a.card in ('c0', 'c'), 'A registered card: c0 (the answer-format block) or c (the hand card)'
                card = mount.format_block('officeqa') if a.card == 'c0' else mount.historical_card('officeqa')
            tools = {'solve': backends.solve, 'score': backends._score_answer_tag, 'card': card,
                     'runtime': bank['runtime']['officeqa']}
            result = oqa_build.stage_contrast(env, tools, items, a.config, card, runs=a.runs or None,
                                              side=a.side or None, sides=bank['sides']['officeqa'],
                                              solver=a.solver_chain)
        elif a.command == 'oqa-diagnose':
            result = oqa_build.stage_diagnose(env, items, bank['sides']['officeqa'])
        elif a.command == 'oqa-audit':
            assert a.scope in oqa_build.AUDIT_SCOPES, 'Scope among ' + str(oqa_build.AUDIT_SCOPES)
            result = oqa_build.stage_audit(env, items, a.scope)
        else:
            tools = {'solve': backends.solve, 'score': backends._score_answer_tag,
                     'card': v222_cards.historical_text('officeqa'), 'runtime': bank['runtime']['officeqa']}
            result = oqa_build.stage_check(env, tools, items)
    except units.Stop as stopped:
        print('STOPPED by the ledger: %s' % stopped)
        return 3
    print(json.dumps(result, indent=1, ensure_ascii=False))
    print('requests answered from stored replies: %s | ledger sends %s, charged %s' % (
        env.reused, env.ledger.state.get('sends'), env.ledger.state.get('charged')))
    if env.ledger.state.get('stopped'):             # whatever a stage returned: a stopped ledger is exit 3
        print('STOPPED by the ledger: %s' % env.ledger.state.get('stop_reason'))
        return 3
    text = json.dumps(result)
    return 4 if any(mark in text for mark in ('infrastructure', 'unknown', 'None', 'parent_unchecked', 'sandbox',
                                              'scorer', 'error: ')) else 0


def command_research(a, run_typed, env):
    """The research stage of one bench: every registered research question, then the brief."""
    import httpx
    from skillopt.execskill import research as frozen_research
    from skillopt.execskill.typed.bank import prompts, research
    assert a.bench in prompts.RESEARCH_QUESTIONS, 'A bench with registered research questions'
    proxy = run_typed.run_inputs(None, 'G', roles_repo=a.roles_repo)['settings']['clients']['solver']['G']['proxy']
    http = httpx.Client(proxy=proxy, trust_env=False, follow_redirects=True, timeout=httpx.Timeout(60, connect=20),
                        headers={'User-Agent': research.USER_AGENT})
    wikipedia = frozen_research.Wikipedia(proxy=proxy)
    web = research.Web(http, wikipedia, frozen_research.page_text)
    try:
        records = [research.investigate(env, web, prompts, a.bench, prompts.FAMILY[a.bench], question)
                   for question in prompts.RESEARCH_QUESTIONS[a.bench]]
        made = research.brief(env, prompts, a.bench, prompts.FAMILY[a.bench], records, prompts.MISTAKE_LABELS)
    finally:
        http.close()
        wikipedia.close()
    return {'questions': {record['question']: {
                'findings': len(record['findings']), 'rounds': len(record['rounds']),
                'pages_read': sum(len(row['read']) for row in record['rounds']),
                'screened_hits': sum(row['screened_hits'] for row in record['rounds']),
                'screened_pages': sum(row['screened_pages'] for row in record['rounds']),
                'void_findings': sum(row['void_findings'] for row in record['rounds']),
                'failed': [f for row in record['rounds'] for f in row['failed']]} for record in records},
            'brief': {key: len(value) for key, value in (made.get('brief') or {}).items()}, 'reason': made.get('reason')}


def command_fixed(a):
    from skillopt.execskill.typed import units
    from skillopt.execskill.typed.bank import env as bank_env, oqa_build, report
    bank = load_bank(a.root)
    items = None if a.command.startswith(('spare-', 'zebra-')) else pool_items(bank, 'officeqa')
    path = Path(a.root) / 'ledger.json'  # read only: a fixed-code stage never opens (and so never changes) the ledger
    state = units.read_json(path) if path.exists() else {}
    ledger = SimpleNamespace(state={key: state.get(key) for key in ('cap', 'charged', 'reported', 'sends', 'stopped',
                                                                    'stop_reason')})
    env = bank_env.BankEnv(a.root, ledger, {}, width=1)
    log_stage(a)
    if a.command == 'sheet-report':
        from skillopt.execskill.typed.bank import sheet_build
        result = sheet_build.build_report(env, pool_items(bank, 'spreadsheetbench'), bank['sides']['spreadsheetbench'])
        units.write_json(Path(a.root) / 'spreadsheetbench' / ('report-%s.json' % time.strftime('%Y%m%dT%H%M%S')), result)
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return 0
    if a.command == 'oqa-twins':
        print(json.dumps(oqa_build.stage_twins(env, items, bank['sides']['officeqa']), indent=1))
        return 0
    if a.command.startswith('zebra-'):
        # ZebraLogic made puzzles (BANK-PILOT B31): fixed code only. The language is learned from the pinned
        # practice pool of the typed manifest the bank was prepared from; every stage begins with its record.
        from skillopt.execskill import zebralogic
        from skillopt.execskill.typed import prepare as typed_prepare
        from skillopt.execskill.typed.bank import zebra_build
        manifest = typed_manifest_of(bank)
        pin = {key: manifest['pools']['zebralogic'][key] for key in ('path', 'sha256')}
        tasks, _ = typed_prepare.load_pool('zebralogic', manifest['pools_root'], pin=pin)
        language = zebra_build.stage_language(env, tasks, pin)
        if a.command == 'zebra-parity':
            from skillopt.execskill.typed.bank import zebra_check
            gate, tools, identity = zebra_tools(a, bank)
            result = zebra_check.stage_parity(env, tools, gate, read_cards(a.cards), step_dir_of(a), identity,
                                              a.solver_chain)
            print(json.dumps(result, indent=1, ensure_ascii=False))
            return 0 if result['ok'] else 2
        if a.command == 'zebra-contrast-report':
            from skillopt.execskill.typed.bank import spare, zebra_check
            gate = spare.gate_items(manifest, 'zebralogic', load_pool=typed_prepare.load_pool)
            result = zebra_check.contrast_report(env, a.base, a.config, gate, a.solver_chain)
            units.write_json(Path(a.root) / 'zebralogic' / ('contrast-report-%s-%s-%s-%s.json' % (
                a.solver_chain, a.base, a.config, time.strftime('%Y%m%dT%H%M%S'))), result)
            print(json.dumps(result, indent=1, ensure_ascii=False))
            return 0
        if a.command == 'zebra-language':
            result = {'version': language['version'], 'pool_items': language['pool_items'], 'checks': language['checks']}
        elif a.command == 'zebra-make':
            result = zebra_build.stage_make(env, language, tasks, zebralogic.normalize, count=a.per_size,
                                            shown=a.shown_per_size)
        else:
            result = zebra_build.build_report(env, language, tasks)
            units.write_json(Path(a.root) / 'zebralogic' / ('report-%s.json' % time.strftime('%Y%m%dT%H%M%S')), result)
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return 0
    if a.command == 'spare-report':
        from skillopt.execskill.typed.bank import spare
        result = spare.spare_report(env, a.bench, a.base, a.config)
        units.write_json(Path(a.root) / a.bench / ('spare-report-%s-%s-%s.json' % (
            a.base, a.config, time.strftime('%Y%m%dT%H%M%S'))), result)
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return 0
    if a.command == 'spare-parity':
        from skillopt.execskill.typed import prepare as typed_prepare
        from skillopt.execskill.typed.bank import spare
        manifest, _, tools = spare_setup(a, bank)
        gate = spare.gate_items(manifest, a.bench, load_pool=typed_prepare.load_pool)
        result = spare.stage_parity(env, tools, a.bench, gate, read_cards(a.cards), step_dir_of(a),
                                    request_identity(a, tools['runtime']))
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return 0 if result['ok'] else 2
    if a.command == 'oqa-parity':
        from skillopt.continual_eval import backends
        from skillopt.execskill.typed import mount
        texts = read_cards(a.cards)
        assert 'c' not in texts, 'Every configuration of --cards is NAME=FILE (a card text on the hand card)'
        assert a.base in texts and a.base_unit, 'oqa-parity needs --base NAME (one of --cards) and --base-unit UNIT'
        tools = {'solve': backends.solve, 'runtime': bank['runtime']['officeqa'],
                 'system_card': lambda text: mount.system_card('officeqa', text, base_card='historical')}
        gate = [item for item in items if bank['sides']['officeqa'][item['task_id']] == 'judge']
        result = oqa_build.stage_parity(env, tools, gate, texts, step_dir_of(a), request_identity(a, tools['runtime']),
                                        base=a.base, base_unit=a.base_unit)
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return 0 if result['ok'] else 2
    if a.command == 'oqa-contrast-report':
        result = oqa_build.contrast_report(env, a.base, a.config, bank['sides']['officeqa'], items=items)
        units.write_json(Path(a.root) / 'officeqa' / ('contrast-report-%s-%s-%s.json' % (
            a.base, a.config, time.strftime('%Y%m%dT%H%M%S'))), result)
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return 0
    result = oqa_build.build_report(env, items, bank['sides']['officeqa'], bank['shared_pages']['officeqa'])
    stamp = time.strftime('%Y%m%dT%H%M%S')
    units.write_json(Path(a.root) / 'officeqa' / ('report-%s.json' % stamp), result)
    body = {k: v for k, v in result.items() if k != 'fidelity'}
    body['new_questions'] = {arm: {k: v for k, v in row.items() if k != 'fidelity'}
                             for arm, row in result['new_questions'].items()}
    print(json.dumps(body, indent=1, ensure_ascii=False))
    print(report.markdown_compare(result['fidelity'], 'OfficeQA: real practice items against number twins'))
    for arm, row in result['new_questions'].items():
        if row['kept_by_fixed_checks']:
            print(report.markdown_compare(row['fidelity'], 'OfficeQA: real practice items against new questions, arm ' + arm))
    return 0


def command_status(a):
    from skillopt.execskill.typed import units
    root = Path(a.root)
    bank = load_bank(a.root)
    count = lambda *parts: len(list(root.joinpath(*parts).glob('*.json'))) if root.joinpath(*parts).is_dir() else 0
    ledger = units.read_json(root / 'ledger.json') if (root / 'ledger.json').exists() else {}
    print(json.dumps({'version': bank['version'], 'cap': bank['cap'],
                      'ledger': {k: ledger.get(k) for k in ('charged', 'reported', 'sends', 'stopped', 'stop_reason')},
                      'pending_calls': len(ledger.get('pending') or {}),
                      'officeqa': {'trace_records': count('officeqa', 'trace'), 'items': count('officeqa', 'items'),
                                   'check_records': count('officeqa', 'check')}}, indent=1))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--machinery-snapshot')
    parser.add_argument('command', choices=COMMANDS)
    parser.add_argument('--root', required=True)
    parser.add_argument('--typed-manifest')
    parser.add_argument('--roles-repo')
    parser.add_argument('--cap', type=int, default=DEFAULT_CAP)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--width', type=int, default=4)
    parser.add_argument('--bench', default='officeqa')
    parser.add_argument('--arms', default='plain,brief')
    parser.add_argument('--styles', default='a')
    parser.add_argument('--per-parent', type=int, default=3)
    parser.add_argument('--from-root')
    parser.add_argument('--scope', default='calibration')
    parser.add_argument('--config')
    parser.add_argument('--base', default='c')
    parser.add_argument('--card-file')
    parser.add_argument('--runs', type=int, default=0)
    parser.add_argument('--card', default='')
    parser.add_argument('--solver-chain', default='G', choices=('G', 'D'))
    parser.add_argument('--side', default='')
    parser.add_argument('--chain-dir')
    parser.add_argument('--cards', default='')
    parser.add_argument('--base-unit', default='')
    parser.add_argument('--step', type=int, default=0)
    parser.add_argument('--per-size', type=int, default=30)
    parser.add_argument('--shown-per-size', type=int, default=10)
    a = parser.parse_args(argv)
    run_typed, a.binding = bind(a.machinery_snapshot)
    if a.command == 'prepare':
        assert a.typed_manifest, 'prepare needs --typed-manifest'
        return command_prepare(a)
    if a.command == 'carry':
        from skillopt.execskill.typed.bank import env as bank_env
        assert a.from_root, 'carry needs --from-root'
        note = bank_env.carry(a.from_root, a.root)
        print(json.dumps({'from': note['from'], 'from_version': note['from_version'], 'call_files': note['call_files'],
                          'research_records': len(note['research_records_carried_as_data'])}, indent=1))
        return 0
    if a.command in ('oqa-contrast', 'oqa-contrast-report', 'spare-report', 'zebra-contrast-report'):
        assert a.config or (a.command == 'oqa-contrast' and a.cards), a.command + ' needs --config'
    if a.command in ('oqa-trace', 'oqa-check', 'research', 'oqa-newq', 'oqa-diagnose', 'oqa-audit', 'oqa-contrast',
                     'spare-contrast', 'sheet-ref', 'sheet-twins', 'sheet-newtask', 'zebra-contrast'):
        return command_model(a, run_typed)
    if a.command in ('oqa-twins', 'oqa-report', 'oqa-contrast-report', 'oqa-parity', 'spare-report',
                     'spare-parity', 'sheet-report', 'zebra-language', 'zebra-make', 'zebra-report',
                     'zebra-parity', 'zebra-contrast-report'):
        return command_fixed(a)
    return command_status(a)


if __name__ == '__main__':
    sys.exit(main())
