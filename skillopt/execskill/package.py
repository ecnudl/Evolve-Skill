"""Procedures and packages, the learned objects (registration §1, §2.1, §5.7, §6.1 edit-type table, §9.2; plan §1
package.py, §2.1, T-PKG-1..5).

A procedure is a Python module (``policy.check``: at most 6,000 bytes; module level only imports, literal constants
and plain functions) plus its record: id ``p-<origin bench>-<step>-<n>`` (engineering fixtures ``fx-<name>``, always
``evidence = engineering_fixture`` and never a learned Skill), origin, description (for people only), the declared
hooks (a closed set; each defined at module level with its registered parameters), the declared caps (note
characters, state bytes, whether it may request a second call), a constant header (rendered by the shell, lexicon-
clean on every bench it may fire on), replay tests, lineage, excluded benches. A package is an ordered list of at
most 24 procedures (at most 64,000 source bytes) with its parent's hash, the retired procedures, per-procedure
narrowings and the describer hashes. Both are sealed records (``protocol.record``: ``version``, ``evidence``,
``record_sha256``), content-addressed by that hash and written once (``save``/``load``).

``with_`` builds a candidate from its parent with at most ``MAX_CHANGES`` edits (§9.2); ``edits`` classifies them as
new, revision, deletion or narrowing (§6.1); ``withhold`` and ``restore`` build the twin arms (§6.5): a withholding
twin drops procedures, a restoration twin puts a deleted procedure or a narrowed scope of the parent back.

v2.3 (2026-10-25 E3): a new procedure pins its selected ``policy_version`` in a new record kind. Historical
procedures omit that field and retain their original validation, records and hashes.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import policy
from .errors import PackageInvalid
from .notes import header_hits
from .profiles import (BENCHES, EVIDENCE, HOOKS, MAX_CHANGES, MAX_DESCRIPTION_CHARS, MAX_HEADER_CHARS, MAX_NOTE_CHARS,
                       MAX_PACKAGE_BYTES, MAX_PROCEDURES, RECORD_HASH, record, verified)
from .profiles import SUPPORTED_BENCHES, ZEBRA

FIXTURE = "engineering_fixture"
HOOK_PARAMETERS = {"applies": 1, "before_call": 2, "bindings": 1, "sheet_feedback": 3, "alf_before_step": 2,
                   "alf_after_step": 2}  # (view) (view, state) (view) (view, run_report, state) ... (event, state)
NOTE_HOOKS = ("before_call", "bindings", "sheet_feedback", "alf_before_step")
SECOND_CALL_HOOKS = ("bindings", "sheet_feedback")
EDIT_KINDS = ("new", "revision", "deletion", "narrowing")
MAX_STATE_BYTES = 65_536  # implementation cap on a declared ALFWorld state (the registration fixes none)
LEARNED_ID = re.compile(r"p-(%s)-(\d{1,3})-(\d{1,3})" % "|".join(SUPPORTED_BENCHES))
FIXTURE_ID = re.compile(r"fx-[a-z0-9][a-z0-9-]{0,39}")
SHA = re.compile(r"[0-9a-f]{64}")
STEP = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}")
PROCEDURE_FIELDS = ("id", "origin", "accepted_at", "description", "hooks", "source", "header", "max_note_chars",
                    "requests_second_call", "state_bytes", "excluded_benches", "replay_tests", "lineage")
PACKAGE_FIELDS = ("parent_sha256", "procedures", "order", "retired", "narrowed", "step", "describer")
STAMP = ("version", "evidence", RECORD_HASH)
LINEAGE_KEYS = ["engineer_call", "parent", "revises"]


def ensure(condition, message):
    """Raise ``PackageInvalid(message)`` unless ``condition``."""
    if not condition:
        raise PackageInvalid(message)


def _plain(value):
    """A detached copy of a JSON value; a non-JSON value is invalid."""
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError):
        raise PackageInvalid("Not a JSON value") from None


def _benches(value):
    return tuple(b for b in SUPPORTED_BENCHES if b in value)


def procedure_benches(procedure):
    """Historical procedures keep exactly their registered five-benchmark scope."""
    return SUPPORTED_BENCHES if (procedure.origin == ZEBRA
        or getattr(procedure, 'policy_version', None) in (policy.POLICY_VERSION_V222, policy.POLICY_VERSION_V225)) else BENCHES


def procedure_input_benches(procedure, *, excluded=()):
    """Intrinsic runtime scope, narrowed by both procedure and package exclusions."""
    blocked = set(procedure.excluded_benches) | set(excluded)
    return tuple(bench for bench in procedure_benches(procedure) if bench not in blocked)


def _is_procedure_id(value):
    return type(value) is str and (LEARNED_ID.fullmatch(value) or FIXTURE_ID.fullmatch(value)) is not None


def _hook_functions(source):
    """{name: positional parameter count, or None when it has any other kind of parameter} of module-level defs."""
    out = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            a = node.args
            plain = not (a.posonlyargs or a.vararg or a.kwonlyargs or a.kwarg or a.defaults)
            out[node.name] = len(a.args) if plain else None
    return out


@dataclass(frozen=True)
class Procedure:
    id: str
    origin: str
    description: str
    hooks: tuple
    source: str
    evidence: str
    header: str = ""
    max_note_chars: int = 0
    requests_second_call: bool = False
    state_bytes: int = 0
    excluded_benches: tuple = ()
    replay_tests: tuple = ()
    lineage: dict = field(default_factory=lambda: {"parent": None, "revises": None, "engineer_call": None})
    accepted_at: str | None = None
    policy_version: str = policy.POLICY_VERSION

    def __post_init__(self):
        for name in ("hooks", "excluded_benches"):
            value = getattr(self, name)
            object.__setattr__(self, name, tuple(value) if isinstance(value, (list, tuple)) else value)
        ensure(isinstance(self.replay_tests, (list, tuple)) and isinstance(self.lineage, dict),
               "Replay tests are a list and lineage a mapping")
        object.__setattr__(self, "replay_tests", tuple(_plain(list(self.replay_tests))))
        object.__setattr__(self, "lineage", _plain(self.lineage))
        self._validate()

    def __hash__(self):
        return hash(self.sha256)

    def _validate(self):
        outcome_judged = self.policy_version in (policy.POLICY_VERSION_V28, policy.POLICY_VERSION_V29, policy.POLICY_VERSION_V222, policy.POLICY_VERSION_V225)
        learned = LEARNED_ID.fullmatch(self.id) if type(self.id) is str else None
        ensure(_is_procedure_id(self.id), "A procedure id is p-<bench>-<step>-<n> or fx-<name>")
        ensure(self.origin in SUPPORTED_BENCHES and (learned is None or learned.group(1) == self.origin),
               "A procedure's origin is the bench in its id")
        ensure((self.evidence in EVIDENCE or self.evidence in ('main_v9_real_run', 'main_v10_real_run'))
               and (learned is not None or self.evidence == FIXTURE),
               "Evidence is registered; a fixture procedure is an engineering fixture")
        ensure(type(self.description) is str and 0 < len(self.description) <= MAX_DESCRIPTION_CHARS,
               "A description is 1-600 characters")
        ensure(type(self.hooks) is tuple and self.hooks == tuple(h for h in HOOKS if h in self.hooks)
               and len(set(self.hooks)) == len(self.hooks)
               and (outcome_judged or ("applies" in self.hooks and len(self.hooks) >= 2)),
               "Hooks are distinct registered hooks in registered order: applies and at least one more")
        ensure(type(self.policy_version) is str and self.policy_version in policy.POLICIES,
               "A registered procedure policy")
        violations = policy.check(self.source, version=self.policy_version)
        ensure(not violations, "Policy violations: %s" % [v.to_json() for v in violations[:5]])
        functions = _hook_functions(self.source)
        ensure(outcome_judged or all(functions.get(h) == HOOK_PARAMETERS[h] for h in self.hooks),
               "Every declared hook is a module-level function with its registered parameters")
        ensure(outcome_judged or not [name for name in functions if name in HOOKS and name not in self.hooks],
               "A module-level hook function must be declared")
        ensure(type(self.excluded_benches) is tuple and self.excluded_benches == _benches(self.excluded_benches)
               and len(set(self.excluded_benches)) == len(self.excluded_benches)
               and set(self.excluded_benches) <= set(procedure_benches(self))
               and (outcome_judged or len(self.excluded_benches) < len(procedure_benches(self))),
               "Excluded benches are known, ordered and not all")
        scope = [b for b in procedure_benches(self) if b not in self.excluded_benches]
        ensure(outcome_judged or self.origin != ZEBRA or (self.hooks == ("applies", "before_call")
               and not self.requests_second_call), "ZebraLogic procedures use applies and before_call only")
        ensure(type(self.header) is str and len(self.header) <= MAX_HEADER_CHARS
               and (outcome_judged or not header_hits(self.header, benches=scope)),
               "A header is at most 200 lexicon-clean characters")
        notes = any(h in NOTE_HOOKS for h in self.hooks)
        ensure(type(self.max_note_chars) is int and 0 <= self.max_note_chars <= max(MAX_NOTE_CHARS.values())
               and (self.max_note_chars > 0) == notes, "A note cap is 1-4000 exactly when a hook writes notes")
        ensure(type(self.requests_second_call) is bool
               and (not self.requests_second_call or any(h in SECOND_CALL_HOOKS for h in self.hooks)),
               "Only bindings or sheet_feedback can request a second call")
        ensure(type(self.state_bytes) is int and 0 <= self.state_bytes <= MAX_STATE_BYTES
               and ("alf_after_step" not in self.hooks or self.state_bytes > 0),
               "State is 0-65536 bytes, nonzero when alf_after_step keeps state")
        ids = [t.get("id") for t in self.replay_tests if type(t) is dict]
        ensure(len(ids) == len(self.replay_tests) and all(type(i) is str and i for i in ids)
               and len(set(ids)) == len(ids) and all(t.get("hook") in self.hooks for t in self.replay_tests),
               "Replay tests have distinct ids and name a declared hook")
        lineage = self.lineage
        ensure(sorted(lineage) == LINEAGE_KEYS
               and all(lineage[k] is None or (type(lineage[k]) is str and SHA.fullmatch(lineage[k]) is not None)
                       for k in ("parent", "engineer_call"))
               and (lineage["revises"] is None or _is_procedure_id(lineage["revises"]))
               and (lineage["parent"] is None) == (lineage["revises"] is None) and lineage["revises"] != self.id,
               "Lineage names a revised procedure together with its hash")
        ensure(self.accepted_at is None or (type(self.accepted_at) is str and STEP.fullmatch(self.accepted_at)),
               "accepted_at is a step label or null")
        if self.policy_version == policy.POLICY_VERSION_V222:
            from .v222_cards import segment_violation
            violation = segment_violation(self)
            ensure(violation is None, violation)
        if self.policy_version == policy.POLICY_VERSION_V225:
            from .v225_cards import metadata, MAX_CARD_CHARS
            card = metadata(self)
            ensure(card is not None and card['home'] == self.origin and 0 < len(card['text']) <= MAX_CARD_CHARS
                   and self.excluded_benches == tuple(b for b in SUPPORTED_BENCHES if b != card['route'])
                   and self.hooks == () and self.header == '' and self.max_note_chars == 0
                   and not self.requests_second_call and self.state_bytes == 0 and not self.replay_tests
                   and self.lineage['parent'] is None and self.lineage['revises'] is None,
                   'A card is constants-only, routed to exactly one bench and never executable')

    @property
    def is_fixture(self):
        return self.evidence == FIXTURE

    def to_json(self):
        """The sealed record: ``version`` = fivebench-execskill-v1-procedure, ``evidence``, ``record_sha256``."""
        fields = {name: getattr(self, name) for name in PROCEDURE_FIELDS}
        fields.update(hooks=list(self.hooks), excluded_benches=list(self.excluded_benches),
                      replay_tests=_plain(list(self.replay_tests)), lineage=dict(self.lineage))
        if self.policy_version != policy.POLICY_VERSION:
            fields["policy_version"] = self.policy_version
            stamp = ("procedure-v2-25" if self.policy_version == policy.POLICY_VERSION_V225 else
                     "procedure-v2-22" if self.policy_version == policy.POLICY_VERSION_V222 else
                     "procedure-v2-9" if self.policy_version == policy.POLICY_VERSION_V29 else
                     "procedure-v2-8" if self.policy_version == policy.POLICY_VERSION_V28 else
                     "procedure-v2-5" if self.policy_version == policy.POLICY_VERSION_V25 else
                     "procedure-v2-4" if self.policy_version == policy.POLICY_VERSION_V24 else "procedure-v2-3")
            return record(stamp, self.evidence, fields)
        return record("procedure", self.evidence, fields)

    @property
    def sha256(self):
        return self.to_json()[RECORD_HASH]

    @classmethod
    def from_json(cls, value):
        version = value.get("policy_version") if isinstance(value, dict) else None
        modern = version in (policy.POLICY_VERSION_V23, policy.POLICY_VERSION_V24, policy.POLICY_VERSION_V25, policy.POLICY_VERSION_V28, policy.POLICY_VERSION_V29, policy.POLICY_VERSION_V222, policy.POLICY_VERSION_V225)
        stamp = ("procedure-v2-25" if version == policy.POLICY_VERSION_V225 else
                 "procedure-v2-22" if version == policy.POLICY_VERSION_V222 else
                 "procedure-v2-9" if version == policy.POLICY_VERSION_V29 else
                 "procedure-v2-8" if version == policy.POLICY_VERSION_V28 else
                 "procedure-v2-5" if version == policy.POLICY_VERSION_V25 else
                 "procedure-v2-4" if version == policy.POLICY_VERSION_V24
                 else "procedure-v2-3" if modern else "procedure")
        try:
            value = verified(value, stamp)
        except ValueError as error:
            raise PackageInvalid("Not a sealed procedure record: %s" % error) from None
        ensure(set(value) == set(PROCEDURE_FIELDS) | set(STAMP) | ({"policy_version"} if modern else set()),
               "Unexpected procedure record fields")
        procedure = cls(evidence=value["evidence"], **{name: value[name] for name in PROCEDURE_FIELDS},
                        **({"policy_version": value["policy_version"]} if modern else {}))
        ensure(procedure.sha256 == value[RECORD_HASH], "Procedure hash mismatch")
        return procedure


def default_applies(procedure):
    """v2.9 missing top-level predicate: every item, with no sandbox call.

    Source definitions are authoritative; declarations must never fabricate an
    entry point that the code does not define.
    """
    return (procedure.policy_version in (policy.POLICY_VERSION_V29, policy.POLICY_VERSION_V222)
            and "applies" not in _hook_functions(procedure.source))


@dataclass(frozen=True)
class Edit:
    """One change of a candidate against its parent (§6.1): ``new`` (old None), ``revision`` (old -> new),
    ``deletion`` (new None) or ``narrowing`` (old is new; ``benches`` are newly excluded)."""
    kind: str
    old: Procedure | None
    new: Procedure | None
    benches: tuple = ()

    @property
    def id(self):
        return (self.new or self.old).id

    def to_json(self):
        return {"kind": self.kind, "id": self.id, "old": self.old.sha256 if self.old else None,
                "new": self.new.sha256 if self.new else None, "benches": list(self.benches)}


@dataclass(frozen=True)
class Package:
    procedures: tuple
    step: str
    evidence: str
    parent_sha256: str | None = None
    retired: tuple = ()
    narrowed: dict = field(default_factory=dict)
    describer: dict = field(default_factory=dict)

    def __post_init__(self):
        ensure(isinstance(self.procedures, (list, tuple)) and isinstance(self.retired, (list, tuple))
               and isinstance(self.narrowed, dict) and isinstance(self.describer, dict)
               and all(type(k) is str and isinstance(v, (list, tuple)) and all(type(b) is str for b in v)
                       and set(v) <= set(SUPPORTED_BENCHES) and len(set(v)) == len(v) for k, v in self.narrowed.items()),
               "Procedures and retired hashes are lists; narrowings map ids to known benches")
        object.__setattr__(self, "procedures", tuple(self.procedures))
        object.__setattr__(self, "retired", tuple(sorted(set(self.retired), key=str)))
        object.__setattr__(self, "narrowed", {k: _benches(v) for k, v in sorted(self.narrowed.items())})
        object.__setattr__(self, "describer", _plain(dict(sorted(self.describer.items(), key=lambda kv: str(kv[0])))))
        _check_package(self)

    def __hash__(self):
        return hash(self.sha256)

    @property
    def order(self):
        return tuple(p.id for p in self.procedures)

    def get(self, procedure_id):
        found = [p for p in self.procedures if p.id == procedure_id]
        ensure(len(found) == 1, "No procedure %s in the package" % procedure_id)
        return found[0]

    def excluded(self, procedure_id):
        """The benches a procedure does not run on: its own exclusions and the package's narrowing."""
        return _benches(set(self.get(procedure_id).excluded_benches) | set(self.narrowed.get(procedure_id, ())))

    def for_bench(self, bench):
        """The procedures that may run on ``bench``, in package order (the router's input)."""
        require(bench in SUPPORTED_BENCHES, "Unknown bench")
        return tuple(p for p in self.procedures if p.policy_version != policy.POLICY_VERSION_V225
                     and bench in procedure_benches(p) and bench not in self.excluded(p.id))

    def card_for(self, bench):
        """The one inert instruction card routed to this benchmark, outside worker inputs."""
        from .v225_cards import metadata
        require(bench in SUPPORTED_BENCHES, 'Unknown bench')
        return next((p for p in self.procedures if (row := metadata(p)) is not None and row['route'] == bench), None)

    def to_json(self):
        """The sealed record: ``version`` = fivebench-execskill-v1-package, ``evidence``, ``record_sha256``."""
        return record("package", self.evidence, {
            "parent_sha256": self.parent_sha256, "procedures": [p.sha256 for p in self.procedures],
            "order": list(self.order), "retired": list(self.retired),
            "narrowed": {k: list(v) for k, v in self.narrowed.items()}, "step": self.step,
            "describer": _plain(self.describer)})

    @property
    def sha256(self):
        return self.to_json()[RECORD_HASH]


def _check_package(package):
    procedures = package.procedures
    from .v225_cards import is_card, metadata, MAX_CARDS
    ordinary = [p for p in procedures if not is_card(p)]
    cards = [p for p in procedures if is_card(p)]
    ensure(all(isinstance(p, Procedure) for p in procedures) and len(ordinary) <= MAX_PROCEDURES,
           "A package holds at most 24 procedures")
    ensure(len(cards) <= MAX_CARDS and len({metadata(p)['route'] for p in cards}) == len(cards),
           'At most five cards, one per route bench')
    ensure(len(set(package.order)) == len(procedures) and len({p.sha256 for p in procedures}) == len(procedures),
           "Procedure ids and contents are distinct")
    ensure(sum(len(p.source.encode("utf-8")) for p in ordinary) <= MAX_PACKAGE_BYTES,
           "A package's sources total at most 64,000 bytes")
    ensure(package.parent_sha256 is None
           or (type(package.parent_sha256) is str and SHA.fullmatch(package.parent_sha256) is not None),
           "The parent is a package hash or null")
    ensure(type(package.step) is str and STEP.fullmatch(package.step) is not None, "A step label is required")
    ensure((package.evidence in EVIDENCE or package.evidence in ('main_v9_real_run', 'main_v10_real_run'))
           and (package.evidence == FIXTURE or not any(p.is_fixture for p in procedures)),
           "Evidence is registered; a package holding a fixture procedure is an engineering fixture")
    ensure(all(type(s) is str and SHA.fullmatch(s) for s in package.retired)
           and not set(package.retired) & {p.sha256 for p in procedures}, "Retired procedures are hashes not in use")
    for procedure_id, benches in package.narrowed.items():
        ensure(procedure_id in package.order and benches, "A narrowing names a procedure of the package and benches")
        ensure(not is_card(package.get(procedure_id)), 'A card route is immutable; cross copies use distinct cards')
        own = package.get(procedure_id).excluded_benches
        scope = procedure_benches(package.get(procedure_id))
        ensure(set(benches) <= set(scope) and not set(benches) & set(own)
               and len(set(benches) | set(own)) < len(scope),
               "A narrowing adds benches and leaves at least one")
    for procedure_id, entry in package.describer.items():
        ensure(procedure_id in package.order and type(entry) is dict
               and not is_card(package.get(procedure_id))
               and sorted(entry) == ["prompt_sha256", "text_sha256"]
               and all(type(v) is str and SHA.fullmatch(v) for v in entry.values()),
               "A describer entry holds the text and prompt hashes of a procedure of the package")


def empty(*, step, evidence):
    """The root package: no procedures, no parent (the card-only start of a chain, §5)."""
    return Package((), step, evidence)


def edits(parent, candidate):
    """The edits of ``candidate`` against ``parent`` (§6.1): new and revised procedures in candidate order, then
    deletions in parent order, then narrowings in candidate order. A revision is a procedure whose lineage revises a
    procedure of the parent that the candidate no longer holds; widening a scope is not an edit type."""
    before = {p.id: p for p in parent.procedures}
    after = {p.id: p for p in candidate.procedures}
    out, revised = [], set()
    for procedure in candidate.procedures:
        if procedure.id in before:
            ensure(before[procedure.id].sha256 == procedure.sha256, "One id names two different procedures")
            continue
        old_id = procedure.lineage["revises"]
        if old_id in before and old_id not in after and old_id not in revised:
            ensure(procedure.lineage["parent"] == before[old_id].sha256, "A revision names its old version's hash")
            out.append(Edit("revision", before[old_id], procedure))
            revised.add(old_id)
        else:
            out.append(Edit("new", None, procedure))
    out += [Edit("deletion", p, None) for p in parent.procedures if p.id not in after and p.id not in revised]
    for procedure in candidate.procedures:
        if procedure.id in before:
            was, now = set(parent.narrowed.get(procedure.id, ())), set(candidate.narrowed.get(procedure.id, ()))
            ensure(was <= now, "Widening a scope is not an edit type")
            if now - was:
                out.append(Edit("narrowing", procedure, procedure, _benches(now - was)))
    return out


def validate(package, parent=None):
    """The package invariants (caps, ids, hooks, module shape, scopes); with ``parent`` also the hash link and at
    most ``MAX_CHANGES`` edits (§9.2, Codex F18). Raises ``PackageInvalid``."""
    ensure(isinstance(package, Package), "Not a package")
    _check_package(package)
    if parent is not None:
        ensure(package.parent_sha256 == parent.sha256, "The candidate's parent hash is not its parent's")
        changes = edits(parent, package)
        from .v225_cards import card_edit, MAX_CARD_EDITS
        card_changes = [edit for edit in changes if card_edit(edit)]
        ordinary = [edit for edit in changes if not card_edit(edit)]
        ensure(len(ordinary) <= MAX_CHANGES, "At most %d edits per step (%d)" % (MAX_CHANGES, len(ordinary)))
        ensure(len(card_changes) <= MAX_CARD_EDITS, 'At most four card edits per step')


def with_(package, *, step, add=(), revise=(), remove=(), narrow=None, evidence=None):
    """The candidate S' of a step from its parent S: ``add`` new procedures (appended in order), ``revise``
    procedures replacing, in place, the ones their lineage names, ``remove`` ids (deleted) and ``narrow``
    {id: benches} (excluded from now on). Replaced and deleted procedures are retired. At most ``MAX_CHANGES``
    edits; ``evidence`` defaults to the parent's."""
    narrow = dict(narrow or {})
    removed = set(remove)
    replaced = {p.lineage["revises"]: p for p in revise}
    touched = list(removed) + list(replaced) + list(narrow)
    ensure(len(touched) == len(set(touched)) and set(touched) <= set(package.order),
           "Each edited procedure is in the parent and edited once")
    ensure(all(p.lineage["parent"] == package.get(old).sha256 for old, p in replaced.items()),
           "A revision names its old version's hash")
    ensure(all(p.lineage["revises"] is None for p in add), "A new procedure revises nothing")
    gone_ids = removed | set(replaced)
    procedures = [replaced.get(p.id, p) for p in package.procedures if p.id not in removed] + list(add)
    narrowed = {k: v for k, v in package.narrowed.items() if k not in gone_ids}
    for procedure_id, benches in narrow.items():
        narrowed[procedure_id] = _benches(set(narrowed.get(procedure_id, ())) | set(benches))
    candidate = Package(tuple(procedures), step, evidence or package.evidence, package.sha256,
                        package.retired + tuple(package.get(i).sha256 for i in gone_ids), narrowed,
                        {k: v for k, v in package.describer.items() if k not in gone_ids})
    validate(candidate, package)
    return candidate


def with_describer(package, describer):
    """The frozen package of a step (§5.7): the same procedures with each procedure's describer text and prompt
    hashes recorded. A new record, hence a new hash; the decision keeps the sealed candidate's hash."""
    return Package(package.procedures, package.step, package.evidence, package.parent_sha256, package.retired,
                   package.narrowed, {**package.describer, **describer})


def withhold(package, ids):
    """A withholding twin (§6.5): the package without the procedures ``ids``, otherwise unchanged."""
    ids = set(ids)
    ensure(ids and ids <= set(package.order), "Withheld procedures are in the package")
    return Package(tuple(p for p in package.procedures if p.id not in ids), package.step, package.evidence,
                   package.parent_sha256, package.retired,
                   {k: v for k, v in package.narrowed.items() if k not in ids},
                   {k: v for k, v in package.describer.items() if k not in ids})


def restore(package, parent, ids):
    """A restoration twin (§6.1, §6.5): ``package`` with each of ``ids`` put back as ``parent`` had it -- a deleted
    procedure re-inserted after its nearest preceding parent procedure still present, or that procedure's revision,
    which stands in its place (with the parent's narrowing and describer entry); a narrowed procedure given back the
    parent's scope."""
    changes = edits(parent, package)
    deleted = {e.id for e in changes if e.kind == "deletion"}
    narrowed = {e.id for e in changes if e.kind == "narrowing"}
    stands_for = {e.new.id: e.old.id for e in changes if e.kind == "revision"}
    ids = set(ids)
    ensure(ids and ids <= deleted | narrowed, "Only deleted or narrowed procedures are restored")
    order = list(package.procedures)
    for index, procedure in enumerate(parent.procedures):
        if procedure.id in ids & deleted:
            earlier = {p.id for p in parent.procedures[:index]}
            present = [i for i, p in enumerate(order) if stands_for.get(p.id, p.id) in earlier]
            order.insert(present[-1] + 1 if present else 0, procedure)
    scopes = {k: v for k, v in package.narrowed.items() if k not in ids}
    scopes.update({k: parent.narrowed[k] for k in ids if k in parent.narrowed})
    describer = {**package.describer, **{k: parent.describer[k] for k in ids & deleted if k in parent.describer}}
    back = {parent.get(i).sha256 for i in ids & deleted}
    return Package(tuple(order), package.step, package.evidence, package.parent_sha256,
                   tuple(s for s in package.retired if s not in back), scopes, describer)


def save(root, package):
    """Write the package and its procedures, content-addressed and write-once, under ``root``:
    ``procedures/<sha>.json`` and ``packages/<sha>.json``. Returns the package hash."""
    root = safe_path(root)
    for procedure in package.procedures:
        write_json(root / "procedures" / (procedure.sha256 + ".json"), procedure.to_json())
    write_json(root / "packages" / (package.sha256 + ".json"), package.to_json())
    return package.sha256


def load(path):
    """A package written by ``save`` (``<root>/packages/<sha>.json``), every hash verified."""
    path = safe_path(path)
    try:
        value = verified(read_json(path), "package")
    except ValueError as error:
        raise PackageInvalid("Not a sealed package record: %s" % error) from None
    ensure(set(value) == set(PACKAGE_FIELDS) | set(STAMP) and path.name == value[RECORD_HASH] + ".json",
           "A package file holds a package record and is named by its hash")
    root = Path(path).parent.parent
    procedures = []
    for sha in value["procedures"]:
        ensure(type(sha) is str and SHA.fullmatch(sha) is not None, "A procedure reference is a hash")
        procedures.append(Procedure.from_json(read_json(root / "procedures" / (sha + ".json"))))
        ensure(procedures[-1].sha256 == sha, "A procedure file does not hold its hash")
    package = Package(tuple(procedures), value["step"], value["evidence"], value["parent_sha256"],
                      tuple(value["retired"]), value["narrowed"], value["describer"])
    ensure(list(package.order) == value["order"] and package.sha256 == value[RECORD_HASH], "Package hash mismatch")
    return package
