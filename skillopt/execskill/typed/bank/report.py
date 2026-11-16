"""Fidelity and yield tables of the item bank (fixed code, no model): how many items were made, why the others were
dropped, and how the made items compare with the real practice items on features fixed code can read off."""
from __future__ import annotations

from collections import Counter


def quartiles(values):
    """(min, lower quartile, median, upper quartile, max) by the nearest-rank rule; None for no values."""
    ordered = sorted(values)
    if not ordered:
        return None
    pick = lambda q: ordered[min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))]
    return [ordered[0], pick(.25), pick(.5), pick(.75), ordered[-1]]


def shares(rows, key):
    """{value: share} of a categorical feature (lists count once per element), sorted by the value's text."""
    counts, n = Counter(), len(rows)
    for row in rows:
        value = row.get(key)
        for element in (value if isinstance(value, (list, tuple)) else [value]):
            counts[str(element)] += 1
    return {value: counts[value] / n for value in sorted(counts)} if n else {}


def compare(real, made, *, categorical, numeric):
    """Real against made feature rows: per categorical feature the share of every value on both sides and the
    largest absolute gap in points; per numeric feature both quartile rows. A feature is compared over the rows that
    carry it (a real item without a derivation has no ``values`` / ``operations``)."""
    out = {'n_real': len(real), 'n_made': len(made), 'categorical': {}, 'numeric': {}}
    for key in categorical:
        a, b = [r for r in real if key in r], [r for r in made if key in r]
        left, right = shares(a, key), shares(b, key)
        values = sorted(set(left) | set(right))
        gaps = {v: 100 * (right.get(v, 0.0) - left.get(v, 0.0)) for v in values}
        out['categorical'][key] = {
            'n_real': len(a), 'n_made': len(b),
            'values': {v: {'real_pct': 100 * left.get(v, 0.0), 'made_pct': 100 * right.get(v, 0.0),
                           'gap_points': gaps[v]} for v in values},
            'max_gap_points': max((abs(g) for g in gaps.values()), default=0.0)}
    for key in numeric:
        a, b = [r[key] for r in real if r.get(key) is not None], [r[key] for r in made if r.get(key) is not None]
        out['numeric'][key] = {'n_real': len(a), 'n_made': len(b), 'real': quartiles(a), 'made': quartiles(b)}
    return out


def tally(reasons):
    """{reason: count}, most frequent first (ties by name)."""
    counts = Counter(reasons)
    return {reason: counts[reason] for reason in sorted(counts, key=lambda r: (-counts[r], r))}


def markdown_compare(table, title):
    lines = ['### ' + title, '', 'real items %d, made items %d' % (table['n_real'], table['n_made']), '',
             '| feature | value | real % | made % | gap (points) |', '|---|---|---|---|---|']
    for key, body in table['categorical'].items():
        for value, cell in body['values'].items():
            lines.append('| %s | %s | %.1f | %.1f | %+.1f |' % (key, value, cell['real_pct'], cell['made_pct'],
                                                                 cell['gap_points']))
    lines += ['', '| feature | side | min | lower quartile | median | upper quartile | max |', '|---|---|---|---|---|---|---|']
    for key, body in table['numeric'].items():
        for side in ('real', 'made'):
            row = body[side]
            lines.append('| %s | %s | %s |' % (key, side, ' | '.join(str(v) for v in row) if row else '— | — | — | — | —'))
    return '\n'.join(lines) + '\n'
