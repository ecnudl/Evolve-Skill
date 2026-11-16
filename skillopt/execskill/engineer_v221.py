"""The main-v7-only engineer decision and coverage additions."""
from copy import copy
from types import SimpleNamespace

from skillopt.continual_eval.core import require

from . import audit, profiles as p, v221_rule

BENCHES = ('searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench')
PURPOSES = ('propose', 'fix', 'format_retry', 'audit_fix', 'fault_repair', 'inert_repair')
DECISION_PARAGRAPH = (
    '\nMain-v7 replaces the earlier gain and audit-decision descriptions above. At training, fresh confirmation '
    'and immediate fresh acceptance, count fixed and broken on changed solver requests: net must be at least '
    'max(3, ceil(0.10 * touched)), broken must be at most 2/3 of fixed, and whole-batch gain must be at least '
    '-0.01. J3/J4/J5/J6 are recorded diagnostics only; J2 stays removed and J7 is not applicable. '
    'A truth audit removes a procedure only when both judges find its notes untrue and its own confirmation '
    'items show more broken than fixed. Safety, leakage and shortcut policy checks remain hard. '
    'A confirmed candidate is accepted immediately on fresh acceptance items or rolled back; later rounds '
    'improve the last accepted incumbent.\n'
)
COVERAGE_PARAGRAPH = (
    '\nFirst propose procedures that act on every item of this bench: organise the supplied evidence, '
    're-rank it, perform structured extraction, or check a candidate result before adding special-case helpers. '
    + v221_rule.COVERAGE_SENTENCE + ' Report candidate and per-procedure touched coverage. '
    'A candidate touching fewer than 3 items fires on almost nothing and gets the existing inert repair '
    'request with its coverage count.\n'
)


def dispatch(ctx, user):
    require(p.is_v221(ctx.configuration) and ctx.bench in BENCHES, 'The main-v7 engineer prompt is opt-in')
    from . import engineer, engineer_v211
    parent = copy(ctx)
    parent.configuration = p.MAIN_V6
    text = (engineer_v211.dispatch(parent, user) if p.uses_v211(parent.configuration, parent.bench)
            else engineer._legacy_system(parent, user))
    if p.is_v225(ctx.configuration):
        from .v225_cards import engineer_sentence
        return text + DECISION_PARAGRAPH + COVERAGE_PARAGRAPH + engineer_sentence()
    if p.is_v222(ctx.configuration):
        from .v222_cards import ENGINEER_SENTENCE
        return text + DECISION_PARAGRAPH + COVERAGE_PARAGRAPH + ENGINEER_SENTENCE
    return text + DECISION_PARAGRAPH + COVERAGE_PARAGRAPH


def system(bench, *, train, purpose='propose', causes=(), configuration=p.MAIN_V7):
    ctx = SimpleNamespace(configuration=configuration, bench=bench, mode='train' if train else 'single', sheet={})
    return dispatch(ctx, {'request': purpose, 'causes': causes, 'evidence': {}})


def prompt_pins(configuration=p.MAIN_V7):
    values = {'decision': DECISION_PARAGRAPH, 'coverage': COVERAGE_PARAGRAPH}
    for bench in BENCHES:
        for mode in ('single', 'train'):
            ctx = SimpleNamespace(configuration=configuration, bench=bench, mode=mode, sheet={})
            for purpose in PURPOSES:
                values[bench + '/' + mode + '/' + purpose] = dispatch(ctx, {'request': purpose, 'evidence': {}})
    return {key: {'text': text, 'sha256': audit.text_sha256(text)} for key, text in values.items()}


def inert_coverage(change, ctx):
    """Inspect the current coded candidate's complete practice routing set without a solver."""
    from . import engineer, reuse
    from .errors import PackageInvalid
    from .package import withhold
    changes = list(ctx.sheet.get('v221_survivors', ())) + [change]
    try:
        candidate = engineer.candidate(ctx.parent, changes, step=ctx.step, evidence=ctx.evidence)
    except PackageInvalid:
        # The unchanged combination pass drops the incompatible suffix. It
        # cannot become the learned candidate, so retain the single-change check.
        changes = [change]
        candidate = engineer.candidate(ctx.parent, changes, step=ctx.step, evidence=ctx.evidence)
    signatures, observations = {}, []
    practice = engineer._run_views(ctx) if ctx.bench == 'spreadsheetbench' else {}

    def signature(package, key, view, worker, arm):
        def observed(shell, _):
            entry = practice.get(key)
            if entry is not None and entry.get('report') is not None:
                shell.feedback(view, entry['report'])
                observations.append({'task_id': key, 'arm': arm,
                    'post_call_effects': v221_rule.post_call_effects(
                        shell.record(), package=package, practice_replay=True)})
        return reuse.signature(ctx.bench, package, view, worker, card_text=ctx.sheet.get('v225_base_card', ctx.card),
                               configuration=ctx.configuration, note_observer=observed)

    for key, view in ctx.routing_items:
        pair = {}
        for arm, package in (("S'", candidate), ('S', ctx.parent)):
            with ctx.routing_workers(package, key) as worker:
                pair[arm] = signature(package, key, view, worker, arm)
        signatures[key] = pair
    touched = v221_rule.identity_touched(signatures, bench=ctx.bench, trajectories=observations)
    per_procedure = {}
    for member in changes:
        if member.kind not in engineer.CODED:
            continue
        without = withhold(candidate, [member.procedure.id])
        pairs = {}
        previous = len(observations)
        for key, view in ctx.routing_items:
            with ctx.routing_workers(without, key) as worker:
                without_signature = signature(without, key, view, worker, 'S')
            pairs[key] = {"S'": signatures[key]["S'"], 'S': without_signature}
        per_procedure[member.procedure.id] = sorted(set(touched) & set(
            v221_rule.identity_touched(pairs, bench=ctx.bench,
                trajectories=[row for row in observations[:previous] if row['arm'] == "S'"]
                             + observations[previous:])))
    result = v221_rule.coverage(len(signatures), touched, per_procedure)
    if p.is_v222(ctx.configuration):
        from . import v222_feedback
        result = v222_feedback.coverage(len(signatures), touched, per_procedure, candidate)
    return result
