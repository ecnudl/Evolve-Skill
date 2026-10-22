"""Registrar-defined transformation families of the examiner's generation path (protocol ``fivebench-execskill-v1``;
registration §7.2 after Codex F8 and owner rule (b) of §21; implementation plan §1 generators row; T-GEN-1..6).

``FAMILIES[bench]`` maps a family name to its ``Family``: OfficeQA (``officeqa``: difference, ratio, percent change,
sum over named cells of a researched table), LiveMath (``livemath``: templates solved by the fixed checker in the
sandbox), SpreadsheetBench (``sheet``: formula-defined edits recalculated by the recalculation engine, then a separate
engine qualification). ALFWorld has no family -- only selection (``alfworld_select``) -- and SearchQA none at all:
both are ``selection_only`` and never carry generated truth.

``generate`` turns the parameter sets an examiner's generator emitted for one qualified research material into sealed
generated items: no material, no item (``no_material``); every parameter set goes through the family's fixed code,
whose truth wins over anything a finding or a generator states; at most ``MAX_ITEMS_PER_FINDING`` (10) items derive
from one finding (``finding_exhausted``); drops are counted by reason.
"""
from __future__ import annotations

from collections import Counter

from skillopt.continual_eval.core import require

from ..protocol import BENCHES, MAX_ITEMS_PER_FINDING
from . import alfworld_select, livemath, officeqa, sheet
from .families import DROPS, Drop, Family, generated_item

__all__ = ["DROPS", "Drop", "FAMILIES", "Family", "alfworld_select", "family", "generate", "mode"]

FAMILIES = {"officeqa": officeqa.FAMILIES, "livemath": livemath.FAMILIES, "spreadsheetbench": sheet.FAMILIES,
            "alfworld": {}, "searchqa": {}}
MATERIAL_KINDS = {"table": "table", "definition": "definition", "function": "functions"}


def mode(bench):
    """"families" for a bench with registered families, else "selection_only" (no generated truth)."""
    require(bench in BENCHES, "Unknown bench")
    return "families" if FAMILIES[bench] else "selection_only"


def family(name):
    """The registered family ``name`` (``<bench>.<template>``)."""
    bench = name.split(".", 1)[0] if type(name) is str else None
    require(bench in FAMILIES and name in FAMILIES[bench], "Unknown family")
    return FAMILIES[bench][name]


def _findings(family_, params, material):
    """The findings a parameter set would draw on (known before the family's code runs)."""
    if family_.material != "function":
        return [material["id"]]
    edits = params.get("edits") if type(params) is dict else None
    names = {name for edit in (edits if type(edits) is list else []) if type(edit) is dict
             and type(edit.get("formula")) is str for name in sheet.functions(edit["formula"])}
    return sorted(material["functions"][name]["id"] for name in names if name in material["functions"])


def generate(family_, param_sets, material, *, generator, set_name, seed, evidence, start=0, source_items=None,
             checker=None, engine=None, out_dir=None):
    """The generated items of ``family_`` from ``param_sets`` on one qualified ``material`` (``research.material``;
    SpreadsheetBench: ``sheet.function_set``): {"status": "no_material" | "made" | "none_kept", "items": [sealed
    items], "made": parameter sets tried, "dropped": {reason: n}}. Items are numbered from ``start``.
    ``source_items``: the item each parameter set was written for (one per set; SpreadsheetBench edits it, the QA
    families record its id); ``checker`` (LiveMath), ``engine`` and ``out_dir`` (SpreadsheetBench): the fixed engines."""
    require(isinstance(family_, Family) and type(param_sets) is list, "A family and a list of parameter sets")
    require(source_items is None or len(source_items) == len(param_sets), "One source item per parameter set")
    require(family_.bench != "livemath" or checker is not None, "A LiveMath family needs the fixed checker")
    require(family_.bench != "spreadsheetbench" or None not in (source_items, engine, out_dir),
            "A SpreadsheetBench family needs source items, the engines and an output directory")
    if material is None:
        return {"status": "no_material", "items": [], "made": 0, "dropped": {}}
    require(material.get("kind") == MATERIAL_KINDS[family_.material], "The family's material kind")
    items, dropped, used = [], Counter(), Counter()
    for index, params in enumerate(param_sets):
        source = source_items[index] if source_items is not None else None
        number = start + len(items)
        item_id = "gen:%s:%d" % (generator, number)
        findings = _findings(family_, params, material)
        try:
            if any(used[finding] >= MAX_ITEMS_PER_FINDING for finding in findings):
                raise Drop("finding_exhausted")
            if family_.bench == "officeqa":
                built = officeqa.apply(family_, params, material)
            elif family_.bench == "livemath":
                built = livemath.apply(family_, params, material, checker=checker, number=number)
            else:
                built = sheet.apply(family_, params, material, engine=engine, source_item=source, out_dir=out_dir,
                                    item_id=item_id)
        except Drop as drop:
            dropped[drop.reason] += 1
            continue
        used.update(built.get("findings", findings))
        items.append(generated_item(
            evidence=evidence, generator=generator, number=number, bench=family_.bench, family=family_.name,
            source_item=source["task_id"] if source is not None else None, material_id=material["id"],
            public=built["public"], private_fields=built.get("private_fields", {"answer": built.get("answer")}),
            truth=built["truth"], set_name=set_name, seed=seed,
            engine_qualification=built.get("engine_qualification")))
    return {"status": "made" if items else "none_kept", "items": items, "made": len(param_sets),
            "dropped": dict(sorted(dropped.items()))}
