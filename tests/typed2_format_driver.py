"""fix-b (review finding rb-requests F1): the fake chain with one bench per type, under the code-default base
'format', run on THIS tree in process (``run_requests``) or, as a script, on the typed package of another tree (an
older commit extracted by ``git archive``):

    python -I tests/typed2_format_driver.py <tree> <scenario> <run root> <out.json>

The script puts ``<tree>`` first on ``sys.path`` (``-I``: neither this file's directory nor PYTHONPATH is on it) and
imports only that tree's ``skillopt.execskill.typed`` ``chain`` and ``smoke``: the smoke's scripted clients,
synthetic items and synthetic manifest, present unchanged in every typed-v2 commit since cdf85b6. So one scenario code
serves both trees. Scenarios (the ones of ``tests/test_typed2_shared.py`` ``SINGLE``): 'smoke-single' (the smoke
limits) and 'default-single' (the default limits, every SearchQA card failing so that round 2 revises); in both,
OfficeQA's no-harm check into SearchQA's type fails, so every type holds one bench (addendum D16 d). The exact axis
embedder makes every routing number exact. Every request is returned as (purpose, unit, system, user). Literal inputs
only: no network, no Docker, no /data, no model call. Not a test module (no ``test_`` prefix): the tests import it."""
import hashlib
import json
import sys
from pathlib import Path

FAMILY_AXES = 16
SCENARIOS = ('smoke-single', 'default-single')


def _sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def run_requests(scenario, root, *, chain, smoke):
    """(final chain state, [(purpose, unit, system, user), ...]) of one scenario on the given ``chain`` and ``smoke``
    modules, run under ``root`` (a new directory whose path names no sealed word)."""
    def exact_embedder(texts):
        rows = []
        for text in texts:
            axis = int(_sha256(text[:smoke.FAMILY_CHARS]), 16) % FAMILY_AXES
            rows.append([1.0 if i == axis else 0.0 for i in range(FAMILY_AXES)])
        return rows

    def searchqa_cards_fail(bench, item_id, mounted):
        if bench == 'searchqa' and (mounted.get('card_text') or '').strip() and mounted.get('arm') != 'C':
            return 'fail'
        return smoke.default_outcome(bench, item_id, mounted)

    def officeqa_own_type(bench, item_id, mounted):
        if bench == 'officeqa' and mounted.get('type') == 't01':
            return 'fail'
        return smoke.default_outcome(bench, item_id, mounted)

    def default_own_type(bench, item_id, mounted):
        if bench == 'officeqa' and mounted.get('type') == 't01':
            return 'fail'
        return searchqa_cards_fail(bench, item_id, mounted)

    class Capture(smoke.Script):
        def __init__(self, scripted=None):
            super().__init__(scripted)
            self.requests = []

        def send(self, purpose, system, user, *, model, unit=None):
            with self.lock:
                self.requests.append((purpose, unit, system, user))
            return super().send(purpose, system, user, model=model, unit=unit)

    limits, outcomes = {'smoke-single': (smoke.SMOKE_LIMITS, officeqa_own_type),
                        'default-single': (chain.DEFAULT_LIMITS, default_own_type)}[scenario]
    script = Capture({'outcomes': outcomes})
    services = smoke.fake_services(Path(root), 'G', smoke.synthetic_manifest(), scripted=script)
    services.embed = exact_embedder
    services.slices = smoke.smoke_slices(services.items, services.slices)
    services.limits = dict(limits)
    state = chain.run(Path(root), 'G', services=services, sleep=lambda s: None)
    return state, list(script.requests)


def main(argv):
    tree, scenario, root, out = argv
    tree = Path(tree).resolve()
    sys.path.insert(0, str(tree))
    from skillopt.execskill.typed import chain, smoke
    for module in (chain, smoke):
        if tree not in Path(module.__file__).resolve().parents:
            raise SystemExit('The typed package was not imported from %s: %s' % (tree, module.__file__))
    state, requests = run_requests(scenario, root, chain=chain, smoke=smoke)
    Path(out).write_text(json.dumps({'complete': state.get('complete'), 'paused': state.get('paused'),
                                     'requests': [list(row) for row in requests]}, ensure_ascii=False),
                         encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
