"""Cross-v5's frozen card sources, cross arms and descriptive transfer matrix."""
from __future__ import annotations

from skillopt.continual_eval.core import require

from . import instruction_start, profiles as p, v218_read, zebralogic
from .cells import Arm

VERSION = 'cross-v5-read-request-reuse-v1'
EVIDENCE_KIND = 'post_hoc_selected_upper_bound_transfer'


def cards():
    """Registered source texts only; no benchmark items are opened."""
    return {**{bench: row['text'] for bench, row in instruction_start.pins().items()},
            p.ZEBRA: zebralogic.CARD_TEXT}


def cross_labels(bench):
    require(bench in p.MAIN_V5_ORDER, 'A cross panel belongs to the five-benchmark roster')
    return ['X_' + source for source in p.MAIN_V5_ORDER if source != bench]


def labels(bench):
    return ['F', 'C', 'B', *cross_labels(bench)]


def arms(bench, final, card):
    return {'F': Arm('candidate', final), 'C': Arm('card', card), 'B': Arm('blank', card),
            **{label: Arm('candidate', final) for label in cross_labels(bench)}}


def card_source(bench, label):
    """Stored on every cross-v5 cell; B has no card source."""
    if label.startswith('X_'):
        require(label in cross_labels(bench), 'A cross arm names a different registered source bench')
        return label[2:]
    return None if label == 'B' else bench


def card_text(context, bench, label):
    require(p.is_v219(context.configuration), 'Card substitution belongs only to cross-v5')
    source = card_source(bench, label)
    if source is None:
        return ''
    return cards()[source] if label.startswith('X_') else context.cards[bench]


def plan(base, arms, packages, *, bench, context, workers):
    """The exact main-v6 planner, with registered cross ordering and source cards."""
    require(p.is_v219(context.configuration), 'Cross request planning belongs only to cross-v5')
    return v218_read.plan(base, arms, packages, bench=bench, context=context, workers=workers)


def matrix(units, *, secondary=False):
    """Same paired estimates and sides as the primary read; no new statistic."""
    from . import readout as r
    contrast = v218_read.contrast if secondary else r._contrast
    out = {}
    for target, cells in units.items():
        out[target] = {}
        for source in p.MAIN_V5_ORDER:
            arm = 'F' if source == target else 'X_' + source
            items = r._items(cells, arm, 'C', 'F')
            out[target][source] = {
                'arm': arm, 'card_source': source, 'n': len(items),
                'accuracy': {side: r._accuracy(cells, arm, items, side) for side in ('L', 'H')},
                'minus_card': contrast(cells, arm, 'C', items, bootstrap=True, sensitivity=True),
                'minus_final': contrast(cells, arm, 'F', items, bootstrap=True, sensitivity=True),
                'reading': ('equals F-C by construction: the ZebraLogic shell omits every card; not transfer evidence'
                            if target == p.ZEBRA else 'post-hoc selected upper-bound card transfer')}
    return out
