"""ALFWorld selection (protocol ``fivebench-execskill-v1``; registration §7.2 "ALFWorld", [SF R9], §21 owner rule (b);
implementation plan §1 generators row; T-GEN-4).

ALFWorld has no environment generator: the examiner can only SELECT unused games, by a filter whose parameters it
chooses and which must cite a qualified ``selection_hint`` finding (known failure modes; none -> ``no_material``). The
filter is fixed code over the zero-call routing view of each game (plan §2.3: initial observation, admissible
commands at reset, task text): the task kind, the number of receptacles in sight and how many of them must be opened.
``null_select`` draws a seeded random set of the same size from the same pool, with zero model calls, and ``shift``
reports whether the selected games differ from it on the target feature. This is reported separately as "selection
validity" and is never counted among the examiner's claims (§7.2).
"""
from __future__ import annotations

import hashlib
import re

from skillopt.continual_eval.core import require

from .families import Drop

TASK_KINDS = ("heat", "cool", "clean", "two", "look", "place")
FEATURES = ("receptacles", "openable")
OPENABLE = ("cabinet", "drawer", "fridge", "microwave", "safe", "box")
SEEN = re.compile(r"you see (.*?)\.(?:\s|$)", re.I | re.S)
OBJECT = re.compile(r"\b(?:an?|the)\s+([a-z]+)\s+\d+", re.I)
SPEC_KEYS = {"task_kinds", "min_receptacles", "min_openable", "target", "finding"}


def task_kind(text):
    """The kind of an ALFWorld task text (``TASK_KINDS``), by its fixed keywords."""
    lower = text.lower()
    for kind, words in (("heat", ("heat", "hot")), ("cool", ("cool", "cold")), ("clean", ("clean",)),
                        ("two", ("two ",)), ("look", ("look at", "examine", "lamp"))):
        if any(word in lower for word in words):
            return kind
    return "place"


def features(view):
    """{"task_kind", "receptacles", "openable"} of one game's routing view."""
    seen = SEEN.search(view["initial_observation"])
    things = [name.lower() for name in OBJECT.findall(seen.group(1))] if seen else []
    return {"task_kind": task_kind(view["task_text"]), "receptacles": len(things),
            "openable": sum(1 for name in things if name in OPENABLE)}


def check_spec(spec, materials):
    """A selection filter: {"task_kinds": [...], "min_receptacles": 0..40, "min_openable": 0..20, "target": one of
    ``FEATURES``, "finding": the id of a qualified selection finding among ``materials``}. Drop("no_material") when
    it cites none, Drop("format") for anything else."""
    if not any(m.get("kind") == "selection" and m.get("id") == (spec or {}).get("finding") for m in materials):
        raise Drop("no_material", "a selection filter cites a qualified selection finding")
    if (type(spec) is not dict or set(spec) != SPEC_KEYS or type(spec["task_kinds"]) is not list
            or not set(spec["task_kinds"]) <= set(TASK_KINDS) or spec["target"] not in FEATURES
            or type(spec["min_receptacles"]) is not int or not 0 <= spec["min_receptacles"] <= 40
            or type(spec["min_openable"]) is not int or not 0 <= spec["min_openable"] <= 20):
        raise Drop("format", "an invalid selection filter")
    return spec


def _order(pool_views, tag):
    return sorted(pool_views, key=lambda game: hashlib.sha256(("%s:%s" % (tag, game)).encode()).hexdigest())


def select(spec, pool_views, *, n, seed_tag):
    """The first ``n`` games of the pool (seeded order of ``seed_tag``) that pass the checked filter ``spec``."""
    require(type(n) is int and n > 0, "Select at least one game")
    chosen = []
    for game in _order(pool_views, seed_tag):
        found = features(pool_views[game])
        if ((not spec["task_kinds"] or found["task_kind"] in spec["task_kinds"])
                and found["receptacles"] >= spec["min_receptacles"] and found["openable"] >= spec["min_openable"]):
            chosen.append(game)
            if len(chosen) == n:
                break
    return chosen


def null_select(pool_views, n, *, seed_tag):
    """``n`` games drawn by the seed alone (the zero-call control of the same size)."""
    require(type(n) is int and 0 < n <= len(pool_views), "A null set no larger than the pool")
    return _order(pool_views, seed_tag + ":null")[:n]


def shift(selected, null, pool_views, feature):
    """Selection validity on ``feature``: both sets' means and their difference (selected minus null)."""
    require(feature in FEATURES and selected and null, "Two nonempty sets and a target feature")

    def mean(games):
        return sum(features(pool_views[g])[feature] for g in games) / len(games)
    return {"feature": feature, "selected_mean": mean(selected), "null_mean": mean(null),
            "shift": mean(selected) - mean(null), "selected": len(selected), "null": len(null)}
