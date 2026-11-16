"""Round receipts keep controller provenance outside the exact engineer history."""
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.execskill import engineer, profiles as p, step, v222_cards
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v221_learning import training
from tests.test_execskill_v222_fix1_hygiene import setup


@pytest.mark.parametrize('first_round', ['ordinary', 'deletion'])
def test_two_rounds_validate_real_engineer_context_and_preserve_hygiene_receipts(
        tmp_path, monkeypatch, first_round):
    st, cut, current, pid = setup(tmp_path)
    for row in cut['run']:
        row['public']['context'] = 'An authored public snippet.'
    st.setting.extra['v211_prompt_pins'] = {}
    st.setting.cards = {'searchqa': v222_cards.format_text('searchqa')}
    st.services.workers = lambda *args, **kwargs: pytest.fail('No sandbox is needed for history validation')
    roles, contexts = [], []
    st.roles = lambda role: roles.append(role) or object()
    monkeypatch.setattr(step, '_earlier', lambda *args: [])
    monkeypatch.setattr(step, '_run_trajectories', lambda *args, **kwargs: [])
    monkeypatch.setattr(step, '_evaluated', lambda *args: [])
    monkeypatch.setattr(step, '_corpora', lambda *args: {})
    monkeypatch.setattr(step, '_references', lambda *args, **kwargs: {})
    monkeypatch.setattr(step, '_previous', lambda *args: None)
    monkeypatch.setattr(step, '_inputs_dirs', lambda *args: nullcontext({}))
    monkeypatch.setattr(step, '_item_workers', lambda *args: lambda *a: None)
    monkeypatch.setattr(step.units, 'audit_judges', lambda *args: {})
    monkeypatch.setattr(step, '_current', lambda st, done:
        current if first_round == 'deletion' and not done else [])
    rounds = p.train_rounds
    monkeypatch.setattr(p, 'train_rounds', lambda configuration, *args:
        2 if p.is_v222(configuration) else rounds(configuration, *args))

    def ordinary(ctx):
        # _engineer_train constructed the real Context, including its exact
        # history validator, before this offline proposal boundary is reached.
        assert isinstance(ctx, engineer.Context)
        contexts.append(ctx)
        return None, p.record('engineer', st.evidence, {
            'changes': [], 'analysis': {'items': []}, 'disclosed': [], 'lint': [], 'dropped': []})

    monkeypatch.setattr(engineer, 'run_train', ordinary)
    evaluations = []

    def rejected(st, cut, r, incumbent, candidate, generated, **kwargs):
        evaluations.append(r)
        assert first_round == 'deletion' and r == 1 and pid not in candidate.order
        # The authored paired outcomes reject the deletion. No confirmation or
        # acceptance is needed; feedback is absent to isolate the history seam.
        return {**training(fixed=0, broken=4), 'candidate_sha256': candidate.sha256, 'feedback': None}

    monkeypatch.setattr(step, '_train_eval', rejected)
    monkeypatch.setattr(step, '_confirm_eval', lambda *args, **kwargs: pytest.fail('Rejected training cannot confirm'))
    final, receipts, _ = step._train(st, cut, None)
    assert final == st.parent and len(receipts) == 2
    assert [ctx.round for ctx in contexts] == ([1, 2] if first_round == 'ordinary' else [2])
    assert roles == ['engineer'] * len(contexts)
    assert evaluations == ([1] if first_round == 'deletion' else [])
    seen = deepcopy(contexts[-1].history)
    assert len(seen) == 1 and 'hygiene' not in seen[0]
    assert seen[0]['candidate'] is (first_round == 'deletion')
    assert seen[0]['proposals'] == receipts[0]['proposals']
    if first_round == 'deletion':
        assert seen[0]['proposals'][0]['kind'] == 'deletion'
        assert seen[0]['proposals'][0]['target'] == pid
    for r, receipt in enumerate(receipts, 1):
        assert receipt['hygiene'] == st.done('engineer-r%d' % r)['hygiene']
        assert receipt['hygiene']['hygiene_mode'] == 'measured_candidates'
    assert receipts[0]['hygiene']['selected'] == (pid if first_round == 'deletion' else None)
    assert receipts[1]['hygiene']['selected'] is None

    # Completed ordinary units resume without constructing a role or changing
    # the stored controller receipt; the original engineer history is detached.
    before_roles = list(roles)
    assert step._train(st, cut, None)[1] == receipts
    assert roles == before_roles and contexts[-1].history == seen

    # This fix must not broaden the canonical engineer input schema.
    with pytest.raises(ValueError, match='history holds counts and flags only'):
        replace(contexts[-1], history=[{**seen[0], 'hygiene': receipts[0]['hygiene']}])


@pytest.mark.parametrize('configuration', [p.MAIN_V7, p.MAIN_V8])
def test_history_line_never_adds_controller_receipt_fields(configuration):
    ordinary = {'candidate_sha256': None, 'engineer': {'changes': []}}
    measured = {**ordinary, 'hygiene': {'hygiene_mode': 'measured_candidates', 'selected': None}}
    assert step._line(1, measured, None, configuration=configuration) == step._line(
        1, ordinary, None, configuration=configuration)
