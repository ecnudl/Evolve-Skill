"""main-v9 practice-only smoke and immutable zero-call S0 registration."""
from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import replace
from fractions import Fraction
import hashlib
import math
from pathlib import Path

from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest
from . import profiles as p, v225_cards as cards, v225_phase as phase

START = 'empty_format_only_v2_25'
REFERENCE_SHA256 = '587883bf35392fd3d7739fce98407519515c2090fa4eef705d4b5f59bfb0a994'
PRICE_CARD = ('Use the supplied evidence carefully. Check the task constraints and verify the result. ' * 40)[:3000]
PRICE_SOURCE = 'def applies(view):\n    return True\n\ndef before_call(view, state):\n    return {}\n'


def probe_caps(chain):
    from . import v225_limits
    require(chain in p.CHAINS, 'A registered smoke chain')
    prefix = chain + ':v225-smoke:card-probe:'
    return {prefix+'solver': v225_limits.SMOKE_SOLVER_TOKENS,
            prefix+'method': v225_limits.SMOKE_METHOD_TOKENS}


def probe_endpoint(setting, chain, bench, *, writer=False):
    """Add the registered smoke ceiling before a real endpoint can dispatch."""
    from . import units, v222_smoke
    setting.budget.declare(probe_caps(chain))
    endpoint = (units.role_endpoint(setting, chain, 'card_writer', 'searchqa', 1) if writer
                else v222_smoke._endpoint(setting, chain, bench))
    endpoint = copy(endpoint)
    endpoint.scopes = tuple(endpoint.scopes) + (chain+':v225-smoke:card-probe:'+('method' if writer else 'solver'),)
    return endpoint


def reserve_probe_dispatch(root, kind, count, *, evidence='smoke'):
    """Count attempted dispatches durably, including interrupted attempts."""
    from skillopt.coevo5.cells import exclusive
    from .errors import BudgetStop
    limits = {'writer':3, 'solver':60}
    require(kind in limits and type(count) is int and count > 0, 'A positive registered smoke dispatch')
    root = safe_path(root)/'dispatches'
    with exclusive(root/'.lock', wait=True):
        previous = [p.verified(read_json(path), 'v225-smoke-dispatch') for path in sorted(root.glob(kind+'-*.json'))]
        used = sum(row['count'] for row in previous)
        if used + count > limits[kind]:
            raise BudgetStop('main-v9 smoke %s dispatch cap %d exhausted' % (kind, limits[kind]))
        write_json(root/('%s-%03d.json' % (kind,len(previous)+1)), p.record('v225-smoke-dispatch',
            evidence, {'kind':kind,'count':count,'previous':used,'cap':limits[kind]}))


class ProbeWriter:
    def __init__(self, roles, root, evidence):
        self.roles, self.root, self.evidence = roles, root, evidence

    @property
    def calls(self):
        return self.roles.calls

    def plain(self, *args, **kwargs):
        reserve_probe_dispatch(self.root, 'writer', 1, evidence=self.evidence)
        return self.roles.plain(*args, **kwargs)


def price_package(bench, chain, evidence):
    """Measured P: a pinned executable fixture plus maximal card, or the fixed ALF import."""
    from .package import Package, Procedure
    from . import policy, v210_import
    if bench == 'alfworld':
        procedures = tuple(replace(Procedure.from_json(row['record']), evidence=evidence)
                           for row in v210_import.pins()['procedures'])
    else:
        procedure = Procedure(id=f'p-{bench}-0-90', origin=bench, description='Authored smoke price procedure',
            hooks=('applies', 'before_call'), source=PRICE_SOURCE, max_note_chars=1,
            excluded_benches=tuple(b for b in p.SUPPORTED_BENCHES if b != bench),
            evidence=evidence, policy_version=policy.POLICY_VERSION_V222)
        procedures = (procedure, cards.make_card(bench, PRICE_CARD, evidence=evidence))
    return Package(procedures, chain + '/price-' + bench, evidence)


def pins(runtime=None, *, configuration=p.MAIN_V9):
    from . import v222_cards, v225_writer, v225_limits, manifest, policy, evaluation
    root = Path(__file__).resolve().parents[2]
    fixture = root / 'tests/fixtures/execskill/v225_cl_metrics_reference.py'
    reference = hashlib.sha256(fixture.read_bytes()).hexdigest()
    require(reference == REFERENCE_SHA256, 'The CL metrics reference differs from its source pin')
    found = {'configuration': configuration, 'start': START, 'prompts': cards.prompt_pins(),
        'formats': {b: hashlib.sha256(v222_cards.format_text(b).encode()).hexdigest() for b in p.MAIN_V5_ORDER},
        'constants': {'CARD_ROUNDS': phase.CARD_ROUNDS, 'MAX_CARD_CHARS': cards.MAX_CARD_CHARS,
            'MAX_CARD_BULLETS': cards.MAX_CARD_BULLETS, 'CARD_WRITER_INPUT_CHARS': 120000,
            'ENGINEER_SHOWN': {'fail': 12, 'pass': 6}, 'view_chars': 3000,
            'reply_head': 300, 'reply_tail': 1200, 'reference_chars': 300,
            'CARD_ACCEPT_ITEMS': phase.CARD_ACCEPT_ITEMS, 'CARD_CONFIRM_ITEMS': phase.CARD_CONFIRM_ITEMS,
            'MAX_CARDS': 5, 'MAX_CARD_EDITS': 4, 'gain_share': '1/20'},
        'routing': 'item_own_bench; excluded_benches; composed_before_format',
        'read_layout': ['anchor', 's1', 's2', 's3', 's4', 's5', 'i', 'c_end'],
        'read_arms': list(p.read_arms_of(configuration)), 'fresh_reads': True, 'overlapped_reads': True,
        'cl_metrics_sha256': reference, 'caps': manifest._plain(v225_limits.identity()),
        'price_card_sha256': hashlib.sha256(PRICE_CARD.encode()).hexdigest(),
        'price_procedure_source_sha256': hashlib.sha256(PRICE_SOURCE.encode()).hexdigest(),
        'price_packages': {b: price_package(b, 'G', 'engineering_fixture').sha256 for b in p.MAIN_V5_ORDER},
        'card_policy': deepcopy(policy.POLICY_V225), 'card_policy_sha256': policy.policy_sha256(version=policy.POLICY_VERSION_V225),
        'card_template': "V225_CARD = 'learned-card-v2-25'\nCARD_HOME = %r\nCARD_ROUTE = %r\nCARD_TEXT = %r\n",
        'consent_fields': sorted(evaluation.CONSENT_FIELDS),
        'parents_sha256': hashlib.sha256((root / 'tests/fixtures/execskill/v225_parents_before.json').read_bytes()).hexdigest()}
    literal = root / 'tests/fixtures/execskill/v225_literals.json'
    if literal.exists():
        found['literal_audit_sha256'] = hashlib.sha256(literal.read_bytes()).hexdigest()
    if runtime is not None:
        found['task_cards'] = {b: hashlib.sha256(v225_writer.task_card(b, runtime).encode()).hexdigest()
                              for b in phase.CARD_ACCEPT_ITEMS}
    if p.is_v226(configuration):
        found['cl_metrics'] = deepcopy(p.main_v10_identity()['cl_metrics'])
    return found


def schedule(configuration=p.MAIN_V9):
    from . import v214_smoke, manifest
    found = v214_smoke.schedule(p.MAIN_V7)
    found.update(configuration=configuration, maximum_schedule=manifest._plain(p.main_v10_identity() if p.is_v226(configuration) else p.main_v9_identity()),
        S2_arms=['B', 'C0', 'C', 'P'], v225=pins(**({'configuration': configuration} if p.is_v226(configuration) else {})),
        cross_narrowing={'cases': ['harmful_format', 'benign'], 'parent': 'empty',
                         'paired_item_calls_max': 960},
        card_probe={'writer_calls_max': 3, 'solver_cells_max': 60, 'practice_only': True})
    found['SE6'] = {'procedure_cost': 'measured with pinned 3000-character card before format',
        'card_cost': 'max(B,C0,C)', 'stage_packages': 5, 'formula':
        'ceil(ratio x sum_b n_b x (4 x card_b + 6 x proc_b)); fresh cells, no sharing discount'}
    found['SX']['purpose'] = 'authored card rules, composition, fresh stage read layout and isolation'
    return found


def structural_smoke(root, *, configuration=p.MAIN_V9):
    if p.is_v226(configuration):
        from . import manifest
        manifest._check_run_root(root, configuration, 'engineering_fixture')
    from .package import empty, with_
    from . import v222_cards, v225_read
    base = empty(step='G/s0', evidence='engineering_fixture')
    card = cards.make_card('searchqa', 'Check all supplied evidence before deciding.')
    package = with_(base, step='G/s1-searchqa', add=[card])
    routed = {b: cards.compose(b, v222_cards.format_text(b), package) for b in p.MAIN_V5_ORDER}
    require(routed['searchqa'].startswith(cards.metadata(card)['text'] + cards.CARD_JOIN),
            'The home card precedes the unchanged format block')
    require(all(routed[b] == v222_cards.format_text(b) for b in p.MAIN_V5_ORDER if b != 'searchqa'),
            'Every off-home card slot is byte identical')
    decisions = {'train_pass': phase.counts(touched=300, fixed=30, broken=15, batch=300),
        'train_fail': phase.counts(touched=300, fixed=29, broken=15, batch=300),
        'confirm_pass': phase.counts(touched=40, fixed=5, broken=2, batch=40),
        'cross_pass': phase.counts(touched=60, fixed=5, broken=2, batch=60)}
    require(decisions['train_pass']['decision'] == decisions['confirm_pass']['decision'] == 'accept'
            and decisions['train_fail']['decision'] == 'reject', 'The registered five-percent worked cases')
    controller = phase.authored_phase_smoke(safe_path(root) / 'card-phase',
        **({'configuration': configuration} if p.is_v226(configuration) else {}))
    edges = authored_phase_edges(safe_path(root) / 'card-edges',
        **({'configuration': configuration} if p.is_v226(configuration) else {}))
    plans = authored_read_plans(package, **({'configuration': configuration} if p.is_v226(configuration) else {}))
    readout = v225_read.structural_readout_demo(**({'configuration': configuration} if p.is_v226(configuration) else {}))
    return {'configuration': configuration, 'passed': True, 'model_calls': 0, 'sealed_reads': 0,
            'fixture_only': True, 'routing_sha256': {b: hashlib.sha256(t.encode()).hexdigest() for b,t in routed.items()},
            'decisions': decisions, 'card_phase': controller, 'card_edges': edges, 'read_plans': plans,
            'readout': readout,
            'read_events': 8, 'read_units': 40, 'panel_arm_reads': 50,
            'pins': pins(**({'configuration': configuration} if p.is_v226(configuration) else {}))}


def authored_phase_edges(root, *, configuration=p.MAIN_V9):
    """Production controllers exercise rejection, replacement and finite supply."""
    scenarios = ('static','training','confirmation','acceptance','all_training','cross_reject','replacement','exhausted')
    found = {name: phase.authored_phase_smoke(safe_path(root)/name, scenario=name,
        **({'configuration': configuration} if p.is_v226(configuration) else {})) for name in scenarios}
    for name, stage in (('static', None),('training','training'),('confirmation','confirmation'),('acceptance','acceptance')):
        first = found[name]['rounds'][0]
        require(first.get('decision') == 'card_rejected_static' if stage is None
                else first[stage]['decision'] == 'reject', 'The authored first rejection reaches its registered stage')
        require(found[name]['rounds'][-1]['decision'] == 'accept', 'A later writer revision can pass')
    require(len(found['all_training']['rounds']) == 3
            and all(row['training']['decision'] == 'reject' for row in found['all_training']['rounds'])
            and found['all_training']['consumed_acceptance'] == 0,
            'Three failed training rounds preserve the acceptance pool')
    require(found['confirmation']['consumed_acceptance'] == 140
            and found['acceptance']['consumed_acceptance'] == 200,
            'A rejected confirmation or acceptance consumes its prefix permanently')
    require(found['cross_reject']['cross_cards'][0]['gate']['passed'] is False
            and found['cross_reject']['rounds'][-1]['decision'] == 'accept',
            'A rejected cross card preserves the accepted own card')
    supply = {bench: phase.authored_phase_smoke(safe_path(root)/bench, bench=bench,
                **({'configuration': configuration} if p.is_v226(configuration) else {}))
              for bench in ('officeqa','zebralogic','spreadsheetbench')}
    require(all(row['consumed_acceptance'] == phase.CARD_ACCEPT_ITEMS[bench] for bench,row in supply.items())
            and all(supply[bench]['procedure_round_count'] == 0 for bench in ('officeqa','spreadsheetbench')),
            'Every small bench uses its registered supply and skips procedures on exhaustion')
    return p.record('v225-authored-phase-edges', 'engineering_fixture', {
        'passed': True, 'real_calls': 0, 'scenarios': found, 'supply': supply})


def authored_read_plans(package, *, configuration=p.MAIN_V9):
    """Real request planner on authored public views, without native environments."""
    from contextlib import nullcontext
    from types import SimpleNamespace
    from unittest.mock import patch
    from . import solver, evaluation, v222_cards, v222_gate, v225_read
    views = {'searchqa': {'question': 'Find an author.', 'context': 'Authored public evidence.'},
        'officeqa': {'question': 'Find a total.', 'context': 'Authored public table.'},
        'zebralogic': {'question': 'There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street.',
                      'columns': ['Name', 'Color']},
        'spreadsheetbench': {'instruction': 'Copy a supplied value.', 'workbook_preview': {'Sheet1': [['value']]}},
        'alfworld': {'initial_observation': 'An authored room.', 'admissible_commands_at_reset': ['look']}}
    context = SimpleNamespace(configuration=configuration,
        cards={b: v222_cards.format_text(b) for b in p.MAIN_V5_ORDER}, runtime={b: {} for b in p.MAIN_V5_ORDER})
    rows = []
    for event in v225_read.EVENTS:
        chosen = v225_read.arms(package, event, chain='G', evidence='engineering_fixture')
        for bench in p.MAIN_V5_ORDER:
            if bench == 'alfworld':
                identities = {label: v222_gate._alf_signature(arm.package, views[bench], None,
                    card_text=v225_read.context_for(context, bench, label).cards[bench], configuration=configuration)
                    for label, arm in chosen.items()}
                source = {label: {'authored': None} for label in chosen}
                identity_sha = digest(identities)
            else:
                base = {'tasks': [{'task_id': 'authored', 'public': views[bench]}]}
                # Native sheet input construction is the authored boundary;
                # the actual composition, routing and fresh planner run here.
                with patch.object(solver, 'routing_view', lambda _bench, public, **kw: public), \
                        patch.object(evaluation, 'public_inputs', lambda *_args: {}):
                    plan = v225_read.fresh_plan(base, chosen, {}, bench=bench, context=context,
                                              workers=lambda *_: nullcontext(None))
                source, identity_sha = plan['sources'], digest(plan['identities'])
            require(all(value is None for entries in source.values() for value in entries.values()),
                    'Authored reads never share an identical request cell')
            rows.append({'event': event, 'bench': bench, 'arms': list(chosen), 'sources': source,
                         'request_identities_sha256': identity_sha})
    return {'units': rows, 'logical_cells': sum(len(row['arms']) for row in rows),
            'fresh_cells': sum(len(row['arms']) for row in rows), 'model_calls': 0, 'authored_only': True}


def check_structural(value):
    configuration = value.get('configuration')
    require(p.is_v225(configuration) and value.get('passed') is True
        and value.get('model_calls') == value.get('sealed_reads') == 0
        and value.get('pins') == pins(**({'configuration': configuration} if p.is_v226(configuration) else {}))
        and value.get('read_units') == 40 and value.get('panel_arm_reads') == 50,
        'main-v9 structural smoke pins all card and read mechanisms')
    controller = p.verified(value.get('card_phase', {}), 'v225-authored-phase-smoke')
    edges = p.verified(value.get('card_edges', {}), 'v225-authored-phase-edges')
    readout = value['readout']
    require(controller['passed'] is True and controller['real_calls'] == 0
            and edges['passed'] is True and edges['real_calls'] == 0
            and readout['passed'] is True and readout['model_calls'] == readout['sealed_reads'] == 0
            and readout['panels'] == 5 and readout['arms'] == 10 and readout['authored_cells'] == 300
            and readout['reference_sha256'] == REFERENCE_SHA256 and readout['anchor_C_equal'] is True
            and controller['consumed_acceptance'] == 100 and controller['procedure_round_count'] == 6
            and len(value['read_plans']['units']) == 40
            and value['read_plans']['fresh_cells'] == value['read_plans']['logical_cells'] == 50,
            'SX exercises production card phases, subsequent procedure rounds and every fresh read plan')
    return value


def s2(setting, chain):
    configuration = p.MAIN_V9
    if p.is_v226(p.configuration_of(setting)):
        configuration = p.configuration_of(setting)
    from . import v214_stages, v222_cards, v222_smoke, rounds, units, smoke, v221_rule, outcomes_ext
    from .cells import Arm
    from .package import empty, with_
    require(p.is_v225(p.configuration_of(setting)), 'main-v9 smoke only')
    setting.extra['v222_fallbacks'] = {}
    cross = v222_smoke.cross_probe(setting, chain)
    require(cross['passed'], 'Both inherited cross cases must exercise the production gate')
    pools, results = v214_stages.fixture_pools(setting, chain), {}
    start = empty(step=chain + '/s0', evidence=setting.evidence)
    for bench, items in pools.items():
        name = chain + '/v225-smoke/price/' + bench
        local = units.for_unit(setting, chain, bench, name)
        def work(attempt, bench=bench, items=items, local=local, name=name):
            tasks = {rounds.key(bench, row['task_id']): {'public': row['public'], 'private': row['private']} for row in items}
            rows, arms = {}, {}
            for label in ('B', 'C0', 'C', 'P'):
                chosen = start
                if label == 'P':
                    chosen = price_package(bench, chain, setting.evidence)
                text = '' if label == 'B' else v222_cards.historical_text(bench) if label == 'C' else v222_cards.format_text(bench)
                runtime = deepcopy(local.runtime)
                if label == 'C' and bench == 'zebralogic':
                    runtime[bench] = v222_cards.historical_runtime(runtime[bench])
                # The blank arm removes guidance inside the cell shell; the
                # Setting itself retains its registered format-only card map.
                run_setting = replace(local, cards={**local.cards,
                    bench: v222_cards.format_text(bench) if label == 'B' else text}, runtime=runtime)
                arm = Arm('blank' if label == 'B' else 'candidate' if label == 'P' else 'card', chosen)
                found = v222_smoke._practice_round(run_setting, attempt, v222_smoke._endpoint(local, chain, bench),
                    name + '/' + label, {label: arm}, tasks, tag='price-' + label)
                cells = [row for group in found.values() for row in group]
                require(len(cells) == len(tasks) and all(v221_rule.token(row) in outcomes_ext.TOKENS for row in cells),
                    'Each price arm has fresh completed scored cells')
                arms[label] = {'cells': len(cells), 'measurements': smoke.measured_cells(cells),
                    'tokens': sum(send.get('charged', 0) for row in cells for send in row['sends']),
                    'package_sha256': chosen.sha256, 'card_sha256': hashlib.sha256(text.encode()).hexdigest(),
                    'cell_sha256': [row[p.RECORD_HASH] for row in cells]}
                if bench == 'searchqa' and label == 'C0':
                    rows['writer_unit'] = name + '/' + label
            return {'passed': True, 'items': len(tasks), 'cells': 4*len(tasks), 'arms': arms, **rows,
                    'settled_tokens': sum(r['tokens'] for r in arms.values()), 'sealed_reads': 0}
        results[bench] = units.run_unit(safe_path(setting.root)/name, run=setting.run, identity={'unit':name},
            work=work, evidence=setting.evidence, configuration=configuration, drain=units.drainer(local,chain,name))['result']
    probe = card_probe(setting, chain, pools)
    return {'passed': all(row['passed'] for row in results.values()) and probe['passed'], 'configuration':configuration,
        'chain':chain, 'benches':results, 'cross_narrowing':cross, 'card_probe':probe,
        'v222_fallbacks':{}, 'cells':sum(r['cells'] for r in results.values())+probe['solver_cells'],
        'practice_registration': setting.extra['v222_practice'], 'sealed_reads':0}


def card_probe(setting, chain, pools):
    """Small practice writer/paired probe, independent of method adoption."""
    configuration = p.MAIN_V9
    if p.is_v226(p.configuration_of(setting)):
        configuration = p.configuration_of(setting)
    from . import v225_writer, v222_smoke, v222_cards, v222_gate, trajectories, rounds, units
    from .corpus import Corpus
    from .package import empty, with_
    from .cells import Arm
    name = chain + '/v225-smoke/card-probe'
    base = empty(step=chain+'/s0', evidence=setting.evidence)
    local = units.for_unit(setting, chain, 'searchqa', name)
    local = replace(local, workers=1,
                    extra={**local.extra, 'v225_smoke_probe_root': str(safe_path(setting.root)/name)})
    def work(attempt):
        source = safe_path(setting.root)/chain/'v225-smoke/price/searchqa'
        traces = [row for row in trajectories.load_run(source) if row['arm']=='C0']
        chosen = pools['searchqa'][:18]
        ids = {rounds.key('searchqa', row['task_id']) for row in chosen}
        # Original sealed provenance is retained; the explicit smoke-only
        # selector cannot admit these rows in a learning request.
        offered = [row for row in traces if row['task_id'] in ids]
        require(len(offered) == len(ids) and len(ids) <= 18, 'Smoke writer reads every reserved C0 example exactly once')
        refs = {rounds.key('searchqa', row['task_id']):row['private'].get('answers', row['private'].get('answer')) for row in chosen}
        roles = ProbeWriter(units.roles(probe_endpoint(local,chain,'searchqa',writer=True),configuration=configuration),
                            safe_path(setting.root)/name, local.evidence)
        written = v225_writer.write(roles,
            chain=chain,bench='searchqa',k=1,c=1,incumbent=base,rows=offered,references=refs,allowed_ids=ids,
            corpus={'searchqa':Corpus('searchqa',chosen)},practice_ids=[r['task_id'] for r in pools['searchqa']],
            runtime=local.runtime,label=name+'/writer',smoke=True,
            state_root=safe_path(setting.root)/chain/'card-writer-smoke')
        call_path = safe_path(attempt) / 'card-writer.json'
        write_json(call_path, written['call_record'])
        writer_sha256 = hashlib.sha256(call_path.read_bytes()).hexdigest()
        if not written.get('text'):
            return {'passed':False,'writer_calls':written['calls'],'solver_cells':0,'static':written['static'],
                    'reason':'no_valid_probe_card','sealed_reads':0}
        card = cards.make_card('searchqa',written['text'],writer_sha256=writer_sha256,evidence=local.evidence)
        candidate = with_(base,step=chain+'/s1-searchqa',add=[card])
        tasks = {rounds.key('searchqa',row['task_id']):{'public':row['public'],'private':row['private']} for row in pools['searchqa'][:20]}
        require(2*len(tasks) <= 40, 'Home probe dispatches at most forty solver cells')
        inspected = v222_gate.inspect('searchqa',base,candidate,pools['searchqa'][:20],
            v222_smoke._workers(local,attempt,probe_endpoint(local,chain,'searchqa'),name,'searchqa',pools['searchqa'][:20]),
            card_text=v222_cards.format_text('searchqa'),runtime=local.runtime['searchqa'],configuration=configuration)
        signatures = {rounds.key('searchqa',key): pair for key,pair in inspected['signatures'].items()}
        require(len(phase.request_changed(signatures)) == len(tasks), 'The home card probe changes every request')
        found = v222_smoke._practice_round(local,attempt,probe_endpoint(local,chain,'searchqa'),name+'/home',
            {'S':Arm('parent',base),"S'":Arm('candidate',candidate)},tasks,tag='card-probe')
        home = phase.decide(found,list(tasks),signatures=signatures)
        # Measured mini cross slice has its own explicit <=10 smoke denominator;
        # no practice acceptance can use this relaxed smoke registration.
        _, harms, registered = v222_smoke.practice(setting)
        target_items = harms['officeqa'][:10]
        copy_card = cards.make_card('searchqa',written['text'],route='officeqa',ordinal=110,evidence=local.evidence,
            writer_sha256=writer_sha256)
        copied = with_(base,step=chain+'/s1-searchqa',add=[copy_card])
        other = units.for_unit(setting,chain,'officeqa',name+'/cross')
        other = replace(other, workers=1,
                        extra={**other.extra, 'v225_smoke_probe_root': str(safe_path(setting.root)/name)})
        endpoint = probe_endpoint(other,chain,'officeqa')
        def inspect(bench,before,after,items):
            chosen_local=units.for_unit(setting,chain,bench,name+'/cross')
            ep=v222_smoke._endpoint(chosen_local,chain,bench)
            return v222_gate.inspect(bench,before,after,items,
                v222_smoke._workers(chosen_local,attempt,ep,name,bench,items),
                card_text=v222_cards.format_text(bench),runtime=chosen_local.runtime[bench],configuration=configuration)
        def pairs(bench,before,after,items):
            require(bench=='officeqa','Only the route bench can fire for a cross card')
            require(2*len(items) <= 20 and 2*(len(tasks)+len(items)) <= 60,
                    'Cross-card dispatch stays inside the sixty-cell combined probe')
            targets={rounds.key(bench,row['task_id']):{'public':row['public'],'private':row['private']} for row in items}
            paired=v222_smoke._practice_round(other,attempt,endpoint,name+'/cross',
                {'S':Arm('parent',before),"S'":Arm('candidate',after)},targets,tag='cross-card')
            return {(arm,key.split('/',1)[1]):rows for (arm,key),rows in paired.items()}
        slices={**harms,'officeqa':target_items}
        selected,gate=v222_gate.check(home='searchqa',parent=base,candidate=copied,slices=slices,
            inspector=inspect,run_pairs=pairs,phase='cross_card',configuration=configuration,smoke=True)
        target=gate['benches']['officeqa']
        return {'passed':target['fired']==len(target_items) and gate['paired_item_calls']==2*len(target_items),
            'writer_calls':written['calls'], 'solver_cells':2*len(tasks)+gate['paired_item_calls'],
            'static':None,'chars':len(written['text']), 'home':home,
            'writer_sha256':writer_sha256, 'delivered':True,
            'card_sha256':card.sha256, 'card_text_sha256':hashlib.sha256(written['text'].encode()).hexdigest(),
            'cross_card':{'gate':gate,'phase':'cross_card','rule':target.get('card_rule'),'fired':target['fired'],
                'harm_registration_sha256':registered['harm']['sha256']},'sealed_reads':0,
            'decision_used_for_adoption':False}
    return units.run_unit(safe_path(setting.root)/name,run=setting.run,identity={'unit':name},work=work,
        evidence=setting.evidence,configuration=configuration,drain=units.drainer(local,chain,name))['result']


def check_measured(value):
    configuration = value.get('configuration')
    from . import v222_smoke, v222_gate, v222_cards, v214_smoke
    from .package import empty, with_
    require(p.is_v225(configuration) and value.get('passed') is True and value.get('sealed_reads')==0,
            'A passing main-v9 measured practice smoke')
    chain = value.get('chain')
    require(chain in p.CHAINS and value.get('v222_fallbacks') == {} and 'decomposition' not in value,
            'main-v9 smoke starts empty without decomposition or whole-card fallback')
    registered=value['practice_registration']
    summary = value['cross_narrowing']
    require(summary.get('passed') is True and summary.get('sealed_reads') == 0
            and set(summary.get('cases', {})) == set(v222_smoke.PROBE_CASES)
            and summary.get('harm_registration_sha256') == registered['harm']['sha256'],
            'Both inherited cross cases bind the S0 harm registration')
    for case in v222_smoke.PROBE_CASES:
        row = summary['cases'][case]
        v222_smoke._check_probe_case(row,registered[v222_smoke.SUPPLY_FLAG],configuration=configuration)
        record = row['gate']
        parent = empty(step=chain+'/s0', evidence=record['evidence'])
        segment = v222_smoke.probe_segment(case, evidence=record['evidence'])
        candidate = with_(parent, step=chain+'/s1-searchqa', add=[segment])
        require(record['parent_sha256'] == parent.sha256 and record['proposed_sha256'] == candidate.sha256
                and row.get('probe_source_sha256') == hashlib.sha256(segment.source.encode()).hexdigest(),
                'Inherited cross probes retain their exact sources and empty main-v9 parent')
    narrowed = any(row['narrowing_exercised'] for row in summary['cases'].values())
    require(summary.get('narrowing_exercised') is narrowed
            and summary.get('reason') == (None if narrowed else 'no_measured_harm')
            and summary.get('paired_item_calls') == sum(row['gate']['paired_item_calls'] for row in summary['cases'].values())
            and summary.get('call_bound') == len(v222_smoke.PROBE_CASES)*v222_gate.MAX_PAIRED_ITEM_CALLS,
            'Inherited cross summaries retain all measured calls and decisions')
    probe=value['card_probe']
    require(probe.get('passed') is True and probe.get('static') is None and 0<probe['writer_calls']<=3
            and 0<probe['solver_cells']<=60 and probe.get('decision_used_for_adoption') is False
            and probe.get('delivered') is True and probe.get('sealed_reads') == 0
            and type(probe.get('chars')) is int and 0 < probe['chars'] <= cards.MAX_CARD_CHARS
            and all(isinstance(probe.get(key), str) and len(probe[key]) == 64
                    for key in ('writer_sha256','card_sha256','card_text_sha256')),
            'Measured card and cross-card probes obey their practice-only bounds')
    home = probe['home']
    expected = phase.counts(touched=home['touched'], fixed=home['fixed'], broken=home['broken'],
                            batch=home['touched'], whole_batch=home['whole_batch'])
    require(0 < home['touched'] <= 20 and all(home.get(key) == val for key,val in expected.items())
            and len(set(home['fixed_items'])) == home['fixed'] and len(set(home['broken_items'])) == home['broken']
            and not set(home['fixed_items']) & set(home['broken_items']),
            'The diagnostic home contrast recomputes without affecting adoption')
    cross = probe['cross_card']
    record = p.verified(cross['gate'], 'v222-cross-gate')
    require(cross.get('phase') == record.get('phase') == 'cross_card'
            and record.get('configuration') == configuration and record.get('home') == 'searchqa'
            and cross.get('harm_registration_sha256') == registered['harm']['sha256']
            and record.get('narrowing') is None
            and set(record['benches']) == set(p.MAIN_V5_ORDER)-{'searchqa'},
            'The cross-card probe uses the production gain gate without narrowing')
    target = record['benches']['officeqa']
    expected = phase.counts(touched=target['fired'], fixed=target['fixed'], broken=target['broken'],
                            batch=target['items'], whole_batch=target['whole_slice'])
    require(target['fired'] == target['items'] == min(10, registered['harm']['benches']['officeqa']['items'])
            and cross.get('fired') == target['fired'] and cross.get('rule') == target.get('card_rule') == expected
            and target.get('passed') is (expected['decision'] == 'accept')
            and target.get('decision') == record.get('decision') == expected['decision']
            and record.get('passed') is target['passed']
            and record.get('paired_item_calls') == target.get('paired_item_calls') == 2*target['fired']
            and probe['solver_cells'] == 2*home['touched']+record['paired_item_calls']
            and record.get('candidate_sha256') == (record['proposed_sha256'] if record['passed'] else None),
            'Cross-card decisions and the sixty-cell probe bound recompute from real pairs')
    require(all(row.get('identity_proven') is True and row.get('fired') == row.get('paired_item_calls') == 0
                for bench,row in record['benches'].items() if bench != 'officeqa'),
            'A cross card changes only its route bench')
    require(set(value['benches'])==set(p.MAIN_V5_ORDER) and all(set(row['arms'])=={'B','C0','C','P'}
            for row in value['benches'].values()),'All card and procedure price arms were measured')
    hashes = []
    evidence = record['evidence']
    for bench, row in value['benches'].items():
        n = v214_smoke.S2_ITEMS[bench]
        require(row.get('passed') is True and row.get('sealed_reads') == 0 and row.get('items') == n
                and row.get('cells') == 4*n
                and row.get('settled_tokens') == sum(arm['tokens'] for arm in row['arms'].values()),
                'Every price bench records its complete four-arm sample')
        for label, arm in row['arms'].items():
            measured = arm['measurements']
            kind = 'procedure' if label == 'P' else 'card'
            entry = measured['per_arm'].get(bench, {}).get(label, {})
            text = '' if label == 'B' else v222_cards.historical_text(bench) if label == 'C' else v222_cards.format_text(bench)
            package = price_package(bench, chain, evidence) if label == 'P' else empty(step=chain+'/s0', evidence=evidence)
            require(arm.get('cells') == n and len(arm['cell_sha256']) == n
                    and all(isinstance(h, str) and len(h) == 64 for h in arm['cell_sha256'])
                    and arm.get('package_sha256') == package.sha256
                    and arm.get('card_sha256') == hashlib.sha256(text.encode()).hexdigest()
                    and entry.get('cells') == n and entry.get('tokens', 0) > 0
                    and measured.get('actual') == entry['tokens']
                    and measured.get('per_class') == {bench: {kind: entry}}
                    and measured['request_bytes'].get(bench, 0) > 0 and arm['tokens'] > 0,
                    'Price cells bind their exact measured package, guidance, token usage and fresh receipts')
            hashes.extend(arm['cell_sha256'])
    require(len(set(hashes)) == len(hashes)
            and value.get('cells') == sum(row['cells'] for row in value['benches'].values())+probe['solver_cells'],
            'Every price arm is fresh and the new measurements reconcile')
    return value


def check_bound_practice(value,registered):
    check_measured(value)
    require(value['practice_registration']==registered and
        value['cross_narrowing']['harm_registration_sha256']==registered['harm']['sha256'],
        'Smoke binds the same S0 practice registration')
    return value


def projection(s2,chain,*,s3,bounds):
    configuration = p.MAIN_V9
    if p.is_v226(s2.get('configuration')):
        configuration = s2['configuration']
    from . import v214_stages
    check_measured(s2)
    # Reuse the unchanged projection machinery with explicit measured prices.
    # This branch is entered only by main-v9; old pricing is not changed.
    return v214_stages.projection(s2,chain,s3=s3,bounds=bounds,configuration=configuration)
