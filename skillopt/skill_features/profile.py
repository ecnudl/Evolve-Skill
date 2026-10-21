"""Distribution of item tags (a feature profile) and the distance between two profiles (zero calls)."""
from __future__ import annotations

from collections import Counter

from .tagger import VERSION as TAGGER_VERSION

VERSION = "skill-features-profile-v1"
AXES = ("primary_op", "answer_form", "rounding")


def _share(counter, n):
    return {str(k): round(v / n, 6) for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))}


def _quantiles(values):
    if not values:
        return None
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]
    return {"min": ordered[0], "p25": pick(0.25), "median": pick(0.5), "p75": pick(0.75), "max": ordered[-1]}


def profile(records):
    """The feature profile of a list of ``tagger.tag_item`` records: per-axis shares, per-tag frequencies and the
    context-shape quantiles."""
    records = list(records)
    n = len(records)
    if n == 0:
        raise ValueError("A profile needs at least one item")
    return {"version": VERSION, "tagger_version": TAGGER_VERSION, "items": n,
            **{axis: _share(Counter(str(r[axis]) for r in records), n) for axis in AXES},
            "tag_frequency": _share(Counter(t for r in records for t in r["tags"]), n),
            **{key: _quantiles([r[key] for r in records]) for key in ("pages", "issues", "context_chars")}}


def total_variation(p, q):
    keys = set(p) | set(q)
    return round(0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys), 6)


def compare(target, candidate):
    """How far ``candidate`` is from ``target``: total-variation distance per axis, the mean absolute difference of
    tag frequencies over the union of tags, and the tags whose frequency differs by more than 0.15."""
    union = set(target["tag_frequency"]) | set(candidate["tag_frequency"])
    gaps = {t: round(candidate["tag_frequency"].get(t, 0.0) - target["tag_frequency"].get(t, 0.0), 6) for t in union}
    return {"version": VERSION, **{axis + "_tv": total_variation(target[axis], candidate[axis]) for axis in AXES},
            "tag_mean_abs_diff": round(sum(abs(v) for v in gaps.values()) / len(union), 6) if union else 0.0,
            "largest_tag_gaps": dict(sorted(((t, g) for t, g in gaps.items() if abs(g) > 0.15),
                                            key=lambda kv: -abs(kv[1])))}
