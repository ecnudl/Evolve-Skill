"""typed-v3 item bank: ZebraLogic made puzzles put before a solver (bank/zebra_check.py) with fake clients. The made
puzzles are those of a real, finished small bank (zebra_build.stage_make on the small language of the zebra tests);
they go through the chain's cell function and the benchmark's judge (spare.stage_spare). No network."""
import json

import pytest

from skillopt.execskill import zebralogic
from skillopt.execskill.typed import units
from skillopt.execskill.typed.bank import rejudge, spare, zebra, zebra_build, zebra_check
from tests.test_typed3_bank_spare import CARD, IDENT, TOOLS, Fake, expected_rule, make_env, root, step_of  # noqa: F401
from tests.test_typed3_bank_zebra import LANGUAGE, PIN, made, open_env, pool_tasks

T, F = True, False
SIZES = ('5*2', '6*2')
CARDS = {'c': None, 'k1': CARD}
PER = 10                              # judging-side puzzles and gate items of each size


def gate_items():
    """The run's gate slice of the fixtures: ten real-shaped puzzles of each size."""
    out = []
    for size in SIZES:
        houses = int(size[0])
        for number in range(1, PER + 1):
            row = zebra.row_of(made('gate:%s:%d' % (size, number), houses, 2), LANGUAGE, 'g-%dx2-%03d' % (houses, number))
            out.append(zebralogic.normalize(row, partition='pool'))
    return out


def build_bank(root, compared=True):
    env, tasks = open_env(root), pool_tasks()
    language = zebra_build.stage_language(env, tasks, PIN)
    zebra_build.stage_make(env, language, tasks, zebralogic.normalize, count=PER + 2, shown=2, sizes=SIZES)
    if compared:
        zebra_build.build_report(env, language, tasks, reference=24)
    return zebra_build.made_items(env, 'judge')


def allow(env, solver, cards=CARDS):
    """A passing parity record of the solver's record kind for the step and identity of the fixtures."""
    shas = spare.card_shas(TOOLS, 'zebralogic', cards)
    rows = {name: {'card_sha256': sha, 'gate_items': 1, 'same_request': 1, 'different': 0, 'no_run_cell_with_this_card': 0,
                   'source': rejudge.base_source('noise') if cards[name] is None else
                   {'role': 'candidate', 'unit': 'card-r1', 'arms': ['cand_card']}} for name, sha in shas.items()}
    units.write_json(env.path('zebralogic', zebra_check.KINDS[solver] + '-parity.json'), {
        'bench': 'zebralogic', 'step_dir': str(rejudge.step_dir_of(step_of(env))), 'request_identity': IDENT, 'ok': True,
        'configurations': rows})


def scripted(items, verdicts):
    """A solver client that answers run r of (item, configuration) with the item's own grid when ``verdicts[(item id,
    configuration)][r]`` holds, else with two names exchanged. The item is recognised by its question."""
    counts = {}

    def answer(system, user):
        item = next(item for item in items if item['public']['question'] in user)
        key = (item['task_id'], 'k1' if CARD.strip() in system else 'c')
        counts[key] = counts.get(key, 0) + 1
        grid = json.loads(json.dumps(item['private']['answer']))
        if not verdicts[key][counts[key] - 1]:
            grid['House 1']['Name'], grid['House 2']['Name'] = grid['House 2']['Name'], grid['House 1']['Name']
        return grid
    return Fake(answer)


def verdicts_of(gate, bank, real_base, real_cand, made_base, made_cand):
    """Run tables: each argument says which of the items of a size pass (both runs): a number (the first so many
    items of a size, the same number for both sizes), a function of an item's place in its size, or one of the two
    for each size."""
    out = {}
    for group, items, base, cand in (('real', gate, real_base, real_cand), ('made', bank, made_base, made_cand)):
        for index, size in enumerate(SIZES):
            of_size = [item for item in items if item['task'] == size]
            assert of_size
            of = lambda value: value[index] if isinstance(value, tuple) else value
            passes = lambda value, place: bool(value(place)) if callable(value) else place < value
            for place, item in enumerate(of_size):
                out[(item['task_id'], 'c')] = [passes(of(base), place)] * 2
                out[(item['task_id'], 'k1')] = [passes(of(cand), place)] * 2
    return out


UNEVEN = PER + 4                      # a gate slice as a run's is: ten items of the first size, four of the second


def run(root, real_base, real_cand, made_base, made_cand, solver='D', gate=None):
    bank = build_bank(root) if not (root / 'zebralogic' / 'made.json').exists() else zebra_build.made_items(open_env(root), 'judge')
    gate = gate_items() if gate is None else gate
    env = make_env(root, scripted(gate + bank, verdicts_of(gate, bank, real_base, real_cand, made_base, made_cand)), width=1)
    allow(env, solver)
    made_stage = zebra_check.stage_contrast(env, TOOLS, gate, CARDS, step_dir=step_of(env), identity=IDENT, runs=2,
                                            solver=solver)
    return env, gate, bank, made_stage


def report(env, gate, solver='D'):
    return zebra_check.contrast_report(env, 'c', 'k1', gate, solver)


def test_the_stage_registers_the_population_of_a_finished_bank(root):
    env, gate, bank, stage = run(root, 7, 7, 7, 7)
    assert stage['items'] == 40 and stage['runs'] == 2 and sorted(stage['configurations']) == ['c', 'k1']
    ids = [item['task_id'] for item in gate] + [item['task_id'] for item in bank]
    assert [item['task_id'] for item in bank] == ['zm-%sx2-%03d' % (h, n) for h in '56' for n in range(3, 13)]   # the judging side
    rows = [[item['task_id'], 'real', item['task']] for item in gate] + [[item['task_id'], 'made', item['task']] for item in bank]
    for config in CARDS:
        record = rejudge.registered(env, 'zebralogic', 'maded', config)
        assert record['items'] == ids and record['population'] == rows and record['solver'] == 'D' and record['runs'] == 2
        assert record['bank_sha256'] == zebra_check.population(env, gate)[2]
        assert len(list((root / 'zebralogic' / ('maded-' + config)).glob('*.json'))) == 40
    assert not list((root / 'zebralogic').glob('spare-*')) and not list((root / 'zebralogic').glob('madeg-*'))
    assert len(env.clients['solver'].calls) == 160                   # 40 items, 2 configurations, 2 runs
    again = make_env(root, scripted([], {}), width=1)                # a second run of the stage sends nothing
    zebra_check.stage_contrast(again, TOOLS, gate, CARDS, step_dir=step_of(again), identity=IDENT, runs=2, solver='D')
    assert again.clients['solver'].calls == []


def test_nothing_is_sent_for_an_unfinished_uncompared_or_unbalanced_population(root, monkeypatch):
    gate = gate_items()
    stage = lambda env, slice_=gate, solver='D': zebra_check.stage_contrast(
        env, TOOLS, slice_, CARDS, step_dir=step_of(env), identity=IDENT, runs=2, solver=solver)
    env = make_env(root, scripted([], {}), width=1)
    allow(env, 'D')
    with pytest.raises(AssertionError, match='not finished'):        # no bank at all
        stage(env)
    # a bank interrupted after its first judging-side puzzle: one made puzzle must not become the population
    tasks = pool_tasks()
    language = zebra_build.stage_language(open_env(root), tasks, PIN)
    real_once = type(env).once

    def interrupted(self, parts, compute):
        if parts == ('zebralogic', 'records', 'zm-5x2-004.json'):
            raise KeyboardInterrupt
        return real_once(self, parts, compute)
    monkeypatch.setattr(type(env), 'once', interrupted)
    with pytest.raises(KeyboardInterrupt):
        zebra_build.stage_make(open_env(root), language, tasks, zebralogic.normalize, count=PER + 2, shown=2, sizes=SIZES)
    monkeypatch.setattr(type(env), 'once', real_once)
    assert (root / 'zebralogic' / 'records' / 'zm-5x2-003.json').exists()
    with pytest.raises(AssertionError, match='not finished'):
        stage(env)
    build_bank(root, compared=False)
    with pytest.raises(AssertionError, match='comparison of made with real puzzles is missing'):
        stage(env)
    build_bank(root)
    with pytest.raises(AssertionError, match='every size of the bank'):   # a gate slice without one of the bank's sizes
        stage(env, gate[:PER])
    other = zebralogic.normalize(zebra.row_of(made('gate:other', 5, 3), LANGUAGE, 'g-5x3-001'), partition='pool')
    with pytest.raises(AssertionError, match='no other size'):            # ... or with a size the bank has not
        stage(env, gate + [other])
    with pytest.raises(AssertionError, match='each once'):
        stage(env, gate + [gate[0]])
    with pytest.raises(AssertionError, match='parity'):              # chain G's kind has no parity record
        (root / 'zebralogic' / 'check-d.json').write_text(json.dumps({
            'bank_sha256': zebra_check.population(env, gate)[2], 'parity': 'PARITY', 'known_effect': 'REPRODUCED'}))
        stage(env, solver='G')
    with pytest.raises(AssertionError, match='A solver chain'):
        stage(env, solver='X')
    # a list and a record changed together, so that a judging puzzle counts as shown: the judging side is not whole
    listing_path, record_path = root / 'zebralogic' / 'made.json', root / 'zebralogic' / 'records' / 'zm-5x2-003.json'
    listing, record = units.read_json(listing_path), units.read_json(record_path)
    units.write_json(record_path, {**record, 'side': 'shown'})
    units.write_json(listing_path, {**listing, 'items': [dict(row, side='shown') if row['item'] == 'zm-5x2-003' else row
                                                          for row in listing['items']]})
    assert len(zebra_build.made_items(env, 'judge')) == 2 * PER - 1
    with pytest.raises(AssertionError, match='not whole'):
        stage(env)
    assert env.clients['solver'].calls == []


def test_the_report_reads_parity_a_known_effect_and_the_gate_rule(root):
    # base: 7 of 10 everywhere; the card: 3 of 10 on real and on made items
    env, gate, bank, _ = run(root, 7, 3, 7, 3)
    out = report(env, gate)
    assert out['complete'] is True and out['items'] == {'real': 20, 'made': 20} and out['repeats'] == 2 and out['solver'] == 'D'
    groups = out['groups']
    assert [groups[name]['base_pass_pct'] for name in ('real', 'made', 'both')] == [70.0, 70.0, 70.0]
    assert [groups[name]['candidate_pass_pct'] for name in ('real', 'made', 'both')] == [30.0, 30.0, 30.0]
    assert all(groups[name]['gain_points'] == -40.0 for name in groups)
    verdicts = verdicts_of(gate, bank, 7, 3, 7, 3)
    for name, items in (('real', gate), ('made', bank)):
        ids = [item['task_id'] for item in items]
        want = expected_rule({i: verdicts[(i, 'c')] for i in ids}, {i: verdicts[(i, 'k1')] for i in ids}, ids, repeats=2)
        rule = groups[name]['gate_rule']
        assert all(rule[key] == want[key] for key in ('n', 'better', 'worse', 'reaches', 'accepted'))
        assert rule['gain_points'] == pytest.approx(want['gain_points']) and rule['accepted'] is False
        low, high = groups[name]['gain_interval_95']
        assert low <= -40.0 <= high < 0
    assert out['by_size'] == {size: {group: {'items': 10, 'base_pass_pct': 70.0, 'candidate_pass_pct': 30.0}
                                     for group in ('real', 'made')} for size in SIZES}
    assert out['parity']['base_pass_made_minus_real_points'] == 0.0 and out['parity']['reading'] == 'PARITY'
    low, high = out['parity']['interval_95']                          # items are resampled within their size
    assert low < 0 < high and -45 < low and high < 45
    assert out['known_effect']['gain_made_minus_gain_real_points'] == 0.0 and out['known_effect']['reading'] == 'REPRODUCED'
    assert out['rejudging'] == {'on_real_items': 'HARMFUL', 'on_real_and_made_items': 'HARMFUL'}
    assert out['sizes_named_by_the_comparison_of_made_with_real_puzzles'] == zebra_build.named_sizes(env)
    assert report(env, gate) == out                                   # seeded
    # the report of chain D's check on the first card round is check D of this bank
    check = units.read_json(root / 'zebralogic' / 'check-d.json')
    assert out['check_d_recorded'] is True and check['parity'] == 'PARITY' and check['known_effect'] == 'REPRODUCED'
    assert check['bank_sha256'] == out['bank_sha256']
    assert check['gain_points'] == {'real': -40.0, 'made_at_the_sizes_of_the_gate_items': -40.0}
    # with as many gate items of every size the made puzzles at the sizes of the gate items are the made puzzles
    assert out['made_at_the_sizes_of_the_gate_items'] == {
        'weights': {'5*2': 0.5, '6*2': 0.5}, 'base_pass_pct': 70.0, 'candidate_pass_pct': 30.0, 'gain_points': -40.0,
        'gain_interval_95': groups['made']['gain_interval_95']}


def test_the_chain_g_rejudging_waits_for_a_passed_check_d_of_the_same_bank(root):
    gate = gate_items()
    build_bank(root)
    env = make_env(root, scripted([], {}), width=1)
    allow(env, 'G')
    stage = lambda: zebra_check.stage_contrast(env, TOOLS, gate, CARDS, step_dir=step_of(env), identity=IDENT, runs=2, solver='G')
    with pytest.raises(AssertionError, match='Check D of this bank has not been read'):
        stage()
    bank_sha = zebra_check.population(env, gate)[2]
    path = root / 'zebralogic' / 'check-d.json'
    for parity, effect in (('EASIER', 'REPRODUCED'), ('PARITY', 'NOT REPRODUCED'), ('HARDER', 'NOT REPRODUCED')):
        units.write_json(path, {'bank_sha256': bank_sha, 'parity': parity, 'known_effect': effect})
        with pytest.raises(AssertionError, match='does not start'):
            stage()
    units.write_json(path, {'bank_sha256': 'e' * 64, 'parity': 'PARITY', 'known_effect': 'REPRODUCED'})
    with pytest.raises(AssertionError, match='another bank'):
        stage()
    assert env.clients['solver'].calls == []
    path.unlink()
    # the real sequence: check D is run and read, then chain G's stage starts in the same root
    env_d, gate, bank, _ = run(root, 7, 3, 7, 3, solver='D')
    assert report(env_d, gate)['check_d_recorded'] is True
    env_g, _, _, stage_g = run(root, 6, 8, 6, 8, solver='G')
    assert stage_g['solver'] == 'G' and len(list((root / 'zebralogic' / 'madeg-k1').glob('*.json'))) == 40
    out = report(env_g, gate, solver='G')
    assert out['solver'] == 'G' and out['groups']['both']['gain_points'] == 20.0 and 'check_d_recorded' not in out
    assert report(env_d, gate)['groups']['both']['gain_points'] == -40.0          # the two checks share no record
    with pytest.raises(AssertionError, match='No report'):
        zebra_check.contrast_report(env_g, 'k1', 'c', gate, 'G')


def test_only_the_first_card_round_of_chain_d_is_check_d(root):
    bank = build_bank(root)
    gate = gate_items()
    env = make_env(root, scripted(gate + bank, verdicts_of(gate, bank, 7, 3, 7, 3)), width=1)
    shas = spare.card_shas(TOOLS, 'zebralogic', CARDS)
    units.write_json(env.path('zebralogic', 'maded-parity.json'), {          # the candidate comes from the SECOND round
        'bench': 'zebralogic', 'step_dir': str(rejudge.step_dir_of(step_of(env))), 'request_identity': IDENT, 'ok': True,
        'configurations': {name: {'card_sha256': sha, 'gate_items': 1, 'same_request': 1, 'different': 0,
                                  'no_run_cell_with_this_card': 0,
                                  'source': rejudge.base_source('noise') if CARDS[name] is None else
                                  {'role': 'candidate', 'unit': 'card-r2', 'arms': ['cand_card']}} for name, sha in shas.items()}})
    zebra_check.stage_contrast(env, TOOLS, gate, CARDS, step_dir=step_of(env), identity=IDENT, runs=2, solver='D')
    out = report(env, gate)
    assert out['known_effect']['reading'] == 'REPRODUCED' and out['origin']['candidate_unit'] == 'card-r2'
    assert 'check_d_recorded' not in out and not (root / 'zebralogic' / 'check-d.json').exists()


def test_a_reading_on_made_puzzles_is_withheld_without_parity(root):
    # the reviewer's case: real 80 -> 90, made 20 -> 80: the made puzzles are much harder under the base
    env, gate, bank, _ = run(root, 8, 9, 2, 8)
    out = report(env, gate)
    assert out['parity']['reading'] == 'HARDER' and out['parity']['base_pass_made_minus_real_points'] == -60.0
    assert out['parity']['interval_95'][1] < 0
    assert out['groups']['both']['gain_points'] == 35.0 and out['groups']['both']['gain_interval_95'][0] > 0
    assert out['rejudging']['on_real_and_made_items'] == zebra_check.WITHHELD
    assert out['rejudging']['on_real_items'] == spare.reading(out['groups']['real']['gate_rule'],
                                                               out['groups']['real']['gain_interval_95'])
    assert units.read_json(root / 'zebralogic' / 'check-d.json')['parity'] == 'HARDER'


def test_easier_made_puzzles_are_named(root):
    env, gate, bank, _ = run(root, 5, 5, 9, 9)
    out = report(env, gate)
    assert out['parity']['base_pass_made_minus_real_points'] == 40.0 and out['parity']['reading'] == 'EASIER'
    assert 0 < out['parity']['interval_95'][0] < 40.0 < out['parity']['interval_95'][1]
    assert out['known_effect']['reading'] == 'NOT REPRODUCED'
    assert out['rejudging'] == {'on_real_items': 'NO EVIDENCE', 'on_real_and_made_items': zebra_check.WITHHELD}


def test_a_known_effect_is_reproduced_only_under_all_three_conditions(root):
    # same sign, but the made gain is too small to exclude 0: one made item of twenty changes
    env, gate, bank, _ = run(root, 6, 4, 6, (5, 6))
    out = report(env, gate)
    assert out['groups']['real']['gain_points'] == -20.0 and out['groups']['made']['gain_points'] == -5.0
    low, high = out['groups']['made']['gain_interval_95']
    assert low < 0 <= high                                            # the made interval contains 0 ...
    low, high = out['known_effect']['interval_95']
    assert low <= 0 <= high                                           # ... while the difference could be 0
    assert out['known_effect']['reading'] == 'NOT REPRODUCED'


def test_a_made_effect_much_smaller_than_the_real_one_is_not_a_reproduction(root):
    # same sign and a made gain that excludes 0, but far from the real one: the difference excludes 0
    env, gate, bank, _ = run(root, 8, 2, 8, 6)
    out = report(env, gate)
    assert out['groups']['real']['gain_points'] == -60.0 and out['groups']['made']['gain_points'] == -20.0
    assert out['groups']['made']['gain_interval_95'][1] < 0
    assert out['known_effect']['gain_made_minus_gain_real_points'] == 40.0 and out['known_effect']['interval_95'][0] > 0
    assert out['known_effect']['reading'] == 'NOT REPRODUCED'


def test_a_made_gain_of_the_other_sign_is_not_a_reproduction(root):
    env, gate, bank, _ = run(root, 8, 4, 4, 8)
    out = report(env, gate)
    assert out['groups']['made']['gain_points'] == 40.0 and out['known_effect']['reading'] == 'NOT REPRODUCED'


def test_a_made_gain_of_the_other_sign_is_not_a_reproduction_whatever_the_intervals_say(root):
    # real: five of ten pass under the base and four OTHER ones under the card (-10 points, a wide interval);
    # made: six, then eight of ten (+20 points, an interval above 0). The difference could be 0; the signs differ.
    env, gate, bank, _ = run(root, 5, lambda place: 5 <= place <= 8, 6, 8)
    out = report(env, gate)
    assert out['groups']['real']['gain_points'] == -10.0 and out['groups']['made']['gain_points'] == 20.0
    assert out['groups']['made']['gain_interval_95'][0] > 0
    low, high = out['known_effect']['interval_95']
    assert out['known_effect']['gain_made_minus_gain_real_points'] == 30.0 and low <= 0 <= high
    assert out['known_effect']['reading'] == 'NOT REPRODUCED'


def test_made_puzzles_are_compared_at_the_sizes_of_the_gate_items(root):
    # a run's gate slice holds its sizes unequally often: here ten items of 5*2 and four of 6*2, against ten made
    # puzzles of each. Passing under the base / the card: real 9 of 10 and 1 of 4 / 5 and 0; made 9 and 3 of 10 / 5
    # and 1. Counted item by item the made puzzles look 11.4 points harder (60.0 against 71.4): they are not, they
    # only hold more puzzles of the hard size. By hand, with 10/14 and 4/14 as the weights of the two sizes:
    #   made base (10 x 90 + 4 x 30) / 14 = 72.857, with the card (10 x 50 + 4 x 10) / 14 = 38.571
    gate = gate_items()[:UNEVEN]
    env, gate, bank, stage = run(root, (9, 1), (5, 0), (9, 3), (5, 1), gate=gate)
    assert stage['items'] == UNEVEN + 2 * PER
    out = report(env, gate)
    assert out['items'] == {'real': UNEVEN, 'made': 2 * PER}
    real, made_group, both = (out['groups'][name] for name in ('real', 'made', 'both'))
    assert [real['base_pass_pct'], real['candidate_pass_pct'], real['gain_points']] == [71.43, 35.71, -35.71]
    assert [made_group['base_pass_pct'], made_group['candidate_pass_pct'], made_group['gain_points']] == [60.0, 30.0, -30.0]
    assert [both['items'], both['base_pass_pct'], both['candidate_pass_pct'], both['gain_points']] == [34, 64.71, 32.35, -32.35]
    weighted = out['made_at_the_sizes_of_the_gate_items']
    assert weighted['weights'] == {'5*2': 0.7143, '6*2': 0.2857}
    assert [weighted['base_pass_pct'], weighted['candidate_pass_pct'], weighted['gain_points']] == [72.86, 38.57, -34.29]
    low, high = weighted['gain_interval_95']
    assert low < -34.29 < high < 0
    assert out['parity']['base_pass_made_minus_real_points'] == 1.43 and out['parity']['reading'] == 'PARITY'
    assert out['known_effect']['gain_made_minus_gain_real_points'] == 1.43 and out['known_effect']['reading'] == 'REPRODUCED'
    assert out['by_size']['6*2'] == {'real': {'items': 4, 'base_pass_pct': 25.0, 'candidate_pass_pct': 0.0},
                                     'made': {'items': 10, 'base_pass_pct': 30.0, 'candidate_pass_pct': 10.0}}
    check = units.read_json(root / 'zebralogic' / 'check-d.json')
    assert check['gain_points'] == {'real': -35.71, 'made_at_the_sizes_of_the_gate_items': -34.29}
    assert check['base_pass_made_minus_real_points'] == 1.43


def test_a_difference_of_sizes_is_not_read_as_a_difference_of_difficulty(root):
    # every puzzle of the first size passes and none of the second, real or made, with and without the card. The gate
    # slice holds ten and four of them, the bank ten and ten: item by item 71.4 against 50.0 per cent, at the sizes
    # of the gate items no difference at all, whatever is drawn within a size.
    gate = gate_items()[:UNEVEN]
    env, gate, bank, _ = run(root, (10, 0), (10, 0), (10, 0), (10, 0), gate=gate)
    out = report(env, gate)
    assert out['groups']['real']['base_pass_pct'] == 71.43 and out['groups']['made']['base_pass_pct'] == 50.0
    assert out['made_at_the_sizes_of_the_gate_items']['base_pass_pct'] == 71.43
    assert out['parity']['base_pass_made_minus_real_points'] == 0.0 and out['parity']['interval_95'] == [0.0, 0.0]
    assert out['parity']['reading'] == 'PARITY'
    assert out['known_effect']['interval_95'] == [0.0, 0.0] and out['known_effect']['reading'] == 'NOT REPRODUCED'   # no effect at all
    assert out['rejudging'] == {'on_real_items': 'NO EVIDENCE', 'on_real_and_made_items': 'NO EVIDENCE'}


def test_the_interval_of_parity_holds_the_uncertainty_of_the_real_items_too(root):
    # the reviewer's case (second look, 2026-11-14): gate items ten and four, passing 8 and 1; made puzzles ten and
    # ten, passing 10 and 0; the card changes nothing. At the sizes of the gate items the made puzzles pass 71.43
    # per cent against 64.29: +7.14 points. Every made puzzle of a size does the same, so the made side does not
    # move under resampling; the interval is the real items' alone and must cross 0 (PARITY, not EASIER).
    gate = gate_items()[:UNEVEN]
    env, gate, bank, _ = run(root, (8, 1), (8, 1), (10, 0), (10, 0), gate=gate)
    out = report(env, gate)
    assert out['groups']['real']['base_pass_pct'] == 64.29 and out['made_at_the_sizes_of_the_gate_items']['base_pass_pct'] == 71.43
    assert out['parity']['base_pass_made_minus_real_points'] == 7.14
    low, high = out['parity']['interval_95']
    assert low < 0 < 7.14 < high and out['parity']['reading'] == 'PARITY'


def test_the_interval_of_parity_holds_the_uncertainty_of_the_made_puzzles_too(root):
    # the mirror case: every gate item of a size does the same (ten pass, four fail: 71.43 per cent, whatever is
    # drawn), the made puzzles pass 8 and 1 of ten: (10 x 80 + 4 x 10) / 14 = 60.0, 11.43 points lower. The interval
    # is the made puzzles' alone and must cross 0 (PARITY, not HARDER).
    gate = gate_items()[:UNEVEN]
    env, gate, bank, _ = run(root, (10, 0), (10, 0), (8, 1), (8, 1), gate=gate)
    out = report(env, gate)
    assert out['groups']['real']['base_pass_pct'] == 71.43 and out['made_at_the_sizes_of_the_gate_items']['base_pass_pct'] == 60.0
    assert out['parity']['base_pass_made_minus_real_points'] == -11.43
    low, high = out['parity']['interval_95']
    assert low < -11.43 < 0 < high and out['parity']['reading'] == 'PARITY'


def test_the_interval_of_a_known_effect_holds_the_uncertainty_of_the_made_puzzles_too(root):
    # the card fails every puzzle of the first size, real or made, and leaves the four gate items of the second size
    # right: -71.43 points on the gate items, whatever is drawn. Of the made puzzles of the second size five pass
    # under the base and six under the card (two turn wrong, three turn right): (10 x -100 + 4 x 10) / 14 = -68.57
    # at the sizes of the gate items, 2.86 points from the real gain, with an interval (the made puzzles' alone)
    # that crosses 0.
    gate = gate_items()[:UNEVEN]
    env, gate, bank, _ = run(root, (10, 10), (0, 10), (10, 5), (0, lambda place: 2 <= place <= 7), gate=gate)
    out = report(env, gate)
    weighted = out['made_at_the_sizes_of_the_gate_items']
    assert out['groups']['real']['gain_points'] == -71.43 and out['groups']['real']['gain_interval_95'] == [-71.43, -71.43]
    assert [weighted['base_pass_pct'], weighted['candidate_pass_pct'], weighted['gain_points']] == [85.71, 17.14, -68.57]
    assert weighted['gain_interval_95'][1] < 0
    assert out['known_effect']['gain_made_minus_gain_real_points'] == 2.86
    low, high = out['known_effect']['interval_95']
    assert low < 0 < 2.86 < high and out['known_effect']['reading'] == 'REPRODUCED'


def test_a_known_effect_is_compared_at_the_sizes_of_the_gate_items(root):
    # the card turns every puzzle of the first size from wrong to right and every puzzle of the second from right to
    # wrong, real or made. On the gate items (ten and four) that is +42.86 points; on the made puzzles counted one
    # by one (ten and ten) it is 0, which would be no effect of the same sign and made puzzles 21.4 points easier.
    gate = gate_items()[:UNEVEN]
    env, gate, bank, _ = run(root, (0, 10), (10, 0), (0, 10), (10, 0), gate=gate)
    out = report(env, gate)
    assert out['groups']['real']['gain_points'] == 42.86 and out['groups']['made']['gain_points'] == 0.0
    assert [out['groups']['real']['base_pass_pct'], out['groups']['made']['base_pass_pct']] == [28.57, 50.0]
    weighted = out['made_at_the_sizes_of_the_gate_items']
    assert [weighted['base_pass_pct'], weighted['candidate_pass_pct'], weighted['gain_points']] == [28.57, 71.43, 42.86]
    assert weighted['gain_interval_95'] == [42.86, 42.86]
    assert out['parity'] == {'base_pass_made_minus_real_points': 0.0, 'interval_95': [0.0, 0.0], 'reading': 'PARITY'}
    assert out['known_effect'] == {'gain_made_minus_gain_real_points': 0.0, 'interval_95': [0.0, 0.0], 'reading': 'REPRODUCED'}
    assert units.read_json(root / 'zebralogic' / 'check-d.json')['known_effect'] == 'REPRODUCED'


def test_items_are_resampled_within_their_size(root):
    # every item of the first size passes, none of the second, in both groups: whatever is drawn WITHIN a size the
    # rates do not move, so every interval collapses; drawing across sizes would spread them
    env, gate, bank, _ = run(root, (10, 0), (10, 0), (10, 0), (10, 0))
    out = report(env, gate)
    assert out['parity']['interval_95'] == [0.0, 0.0] and out['parity']['reading'] == 'PARITY'
    assert out['known_effect']['interval_95'] == [0.0, 0.0]
    assert all(out['groups'][name]['gain_interval_95'] == [0.0, 0.0] for name in ('real', 'made', 'both'))
    assert out['by_size']['5*2']['made'] == {'items': 10, 'base_pass_pct': 100.0, 'candidate_pass_pct': 100.0}
    assert out['by_size']['6*2']['real'] == {'items': 10, 'base_pass_pct': 0.0, 'candidate_pass_pct': 0.0}


def test_the_report_is_of_the_registered_population_only(root):
    env, gate, bank, _ = run(root, 7, 3, 7, 3)
    with pytest.raises(AssertionError, match='No report'):
        zebra_check.contrast_report(env, 'k1', 'c', gate, 'D')       # the base is the run's base
    with pytest.raises(AssertionError, match='another population'):  # the same sizes, the gate items in another order
        report(env, gate[PER:] + gate[:PER])
    other = [dict(item, task_id=item['task_id'] + 'x') for item in gate]
    with pytest.raises(AssertionError, match='another population'):
        report(env, other)
    # the names of the sizes come from the bank's comparison
    stored = units.read_json(root / 'zebralogic' / 'comparison.json')
    stored['comparison']['sizes']['6*2']['beyond']['clues'] = 0.0
    units.write_json(root / 'zebralogic' / 'comparison.json', stored)
    assert '6*2' in report(env, gate)['sizes_named_by_the_comparison_of_made_with_real_puzzles']
    # a record that is missing leaves the report undecided
    (root / 'zebralogic' / 'maded-k1' / (spare.stem(bank[0]['task_id']) + '.json')).unlink()
    out = report(env, gate)
    assert out['complete'] is False and out['reading'] == 'INCOMPLETE' and out['records'] == {'base': 40, 'candidate': 39}
    assert 'groups' not in out and 'parity' not in out
    # a bank whose list changed is another bank
    listing = units.read_json(root / 'zebralogic' / 'made.json')
    record = units.read_json(root / 'zebralogic' / 'records' / 'zm-5x2-012.json')
    item = units.read_json(root / 'zebralogic' / 'items' / 'zm-5x2-012.json')
    item['public']['question'] = item['public']['question'].replace('first', 'second', 1)
    units.write_json(root / 'zebralogic' / 'items' / 'zm-5x2-012.json', item)
    with pytest.raises(AssertionError, match='not the one its record certifies'):
        report(env, gate)
    assert listing and record
