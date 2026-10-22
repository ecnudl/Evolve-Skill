"""Shared parts of the registrar-defined transformation families (protocol ``fivebench-execskill-v1``; registration
§7.2 after Codex F8 and owner rule (b) of §21; implementation plan §1 generators row; T-GEN-1..6).

A family is fixed registrar code: a parameter schema (what the examiner may choose -- cells, perturbation sizes,
template parameters, never an answer) and a reference function that computes the truth of every generated item. A
family consumes ONLY a qualified research finding of its material kind (``research.material``); without one it makes
no item (``no_material``). The examiner's generator program only emits parameter sets; ``check`` validates a set
against the schema, and any other key -- an ``answer`` above all -- makes the set invalid (``format``).

Also here: ``Bundle``/``Entry``, the minimal package shape the sandbox client loads (``sandbox.client._entries``: an
object with ``sha256`` and ``procedures`` of ``id``, ``source``, ``hooks``) for fixed checker code and for examiner
programs (detectors, generators), and ``generated_item``, the sealed item line of plan §2.5.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from ..protocol import BENCHES, record

# why a parameter set made no item (plan §2.5 ``gates.truth.dropped``; D6's drop reasons as the template)
DROPS = ("no_material", "material_mismatch", "format", "perturbation_noop", "reference_fn_failed",
         "literal_not_in_context", "answer_in_context", "options", "meta_option", "function_not_researched",
         "forbidden_function", "literal_answer", "edit_target_invalid", "recalc_failed",
         "engine_qualification_failed", "finding_exhausted")
SETS = ("G_self", "G_acc", "band", "shortcut")
KINDS = ("int", "cell", "cells", "ints", "edits")


class Drop(ValueError):
    """A parameter set that makes no item, and why (one of ``DROPS``)."""

    def __init__(self, reason, detail=""):
        require(reason in DROPS, "Unknown drop reason")
        super().__init__("%s: %s" % (reason, detail) if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class Param:
    """One registered parameter: ``kind`` (``KINDS``), the value range [low, high] of an int (of each int of a list,
    of each perturbation percentage), and the list length range ``count`` of a list kind. ``optional``: may be
    absent."""
    kind: str
    low: int = 0
    high: int = 0
    count: tuple = (1, 1)
    optional: bool = False

    def __post_init__(self):
        require(self.kind in KINDS and self.low <= self.high and 0 <= self.count[0] <= self.count[1],
                "Invalid parameter registration")


@dataclass(frozen=True)
class Family:
    """A registrar-defined family: its name (``<bench>.<template>``), bench, the research material kind it
    consumes, its parameter schema and its fixed reference function (the module's own; recorded by name)."""
    name: str
    bench: str
    material: str
    params: dict
    reference: str
    concept: str = ""  # LiveMath: the term the definition must state; OfficeQA: the material request's topic hint

    def __post_init__(self):
        require(self.bench in BENCHES and self.name.startswith(self.bench + ".")
                and self.material in ("table", "definition", "function", "selection"), "Invalid family")

    def in_range(self, name, value):
        """Whether a researched value of parameter ``name`` lies in the registered range (§7.2 parameter_choice:
        values outside are dropped)."""
        param = self.params.get(name)
        if param is None or param.kind not in ("int", "ints") or not isinstance(value, Fraction):
            return False
        return value.denominator == 1 and param.low <= value <= param.high


def _int(value, param, name):
    if type(value) is not int or not param.low <= value <= param.high:
        raise Drop("format", "%s out of its registered range" % name)
    return value


def _cell(value, name):
    if (type(value) is not list or len(value) != 2 or not all(type(v) is int and v >= 0 for v in value)):
        raise Drop("format", "%s is a [row, column] pair" % name)
    return tuple(value)


def check(family, params):
    """The parameter set ``params`` (a dict) validated against ``family``'s schema, normalized (cells as tuples);
    Drop("format") for a missing or unknown key (an ``answer`` key included) or a value outside its range."""
    if type(params) is not dict:
        raise Drop("format", "a parameter set is an object")
    unknown = set(params) - set(family.params)
    missing = {name for name, p in family.params.items() if not p.optional} - set(params)
    if unknown or missing:
        raise Drop("format", "keys: unknown %s, missing %s" % (sorted(unknown), sorted(missing)))
    out = {}
    for name, value in params.items():
        param = family.params[name]
        if param.kind == "int":
            out[name] = _int(value, param, name)
        elif param.kind == "cell":
            out[name] = _cell(value, name)
        elif param.kind in ("cells", "ints", "edits"):
            if type(value) is not list or not param.count[0] <= len(value) <= param.count[1]:
                raise Drop("format", "%s has %d to %d entries" % (name, *param.count))
            if param.kind == "cells":
                out[name] = tuple(_cell(v, name) for v in value)
            elif param.kind == "ints":
                out[name] = tuple(_int(v, param, name) for v in value)
            else:
                out[name] = tuple(value)  # checked entry by entry by the family (sheet edits, perturbations)
    return out


@dataclass(frozen=True)
class Entry:
    """One loadable source of a sandbox bundle: ``hooks`` are the functions the host may call."""
    id: str
    source: str
    hooks: tuple


@dataclass(frozen=True)
class Bundle:
    """What ``sandbox.client.Worker.start`` loads: ``sha256`` of the entries and the entries."""
    sha256: str
    procedures: tuple = field(default_factory=tuple)


def bundle(entries):
    """The bundle of ``entries`` (``Entry`` objects), its sha256 the digest of their ids, sources and hooks."""
    entries = tuple(entries)
    require(entries and all(isinstance(e, Entry) for e in entries) and len({e.id for e in entries}) == len(entries),
            "A bundle of distinct entries")
    return Bundle(digest([[e.id, e.source, list(e.hooks)] for e in entries]), entries)


def generated_item(*, evidence, generator, number, bench, family, source_item, material_id, public, private_fields,
                   truth, set_name, seed, engine_qualification=None):
    """The sealed ``fivebench-execskill-v1-generated-item`` line (plan §2.5): ``id`` = ``gen:<generator>:<n>``, also
    the item's ``task_id``; ``private`` holds the bench's private fields (QA: the answer; SpreadsheetBench: the
    reference workbook and answer position), the semantic truth and the engine qualification apart."""
    require(set_name in SETS and type(number) is int and number >= 0, "A generated item of a known set")
    item_id = "gen:%s:%d" % (generator, number)
    return record("generated-item", evidence, {
        "id": item_id, "task_id": item_id, "benchmark": bench, "family": family, "source_item": source_item,
        "material": material_id, "public": public,
        "private": {**private_fields, "truth": truth, "engine_qualification": engine_qualification},
        "set": set_name, "seed": seed})
