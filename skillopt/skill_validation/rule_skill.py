"""Bounded conditional Skill rules, not correctness or deployment authority.

Scope matching uses only explicit, public obligation kinds. It is a syntactic
filter: matching does not establish that the prose ``when`` or its exceptions
hold. Evidence IDs are references, not authenticated evidence in this module.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .admission import ScopeRule
from .checks import CallableTask
from .models import Record, exact_fields, hash_text, require, text, typed_tuple, unique

MAX_RULES = 8
MAX_EDITS = 2
MAX_RENDER_BYTES = 6000
SCOPE_BASIS = "public_obligation_kind_syntax_only_not_semantic_applicability_or_deployment_authority"


def _identifier(value):
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value) is not None,
            "Expected a stable bounded identifier")


def _strings(values, *, maximum_items, maximum_bytes, nonempty=False):
    typed_tuple(values, str, maximum=maximum_items)
    require(not nonempty or bool(values), "At least one procedure step is required")
    for value in values:
        text(value, maximum=maximum_bytes)


def _array(value, name):
    require(type(value) is list, name + " must be a JSON array")
    return tuple(value)


def _scope(value):
    fields = exact_fields(ScopeRule, value)
    for name in fields:
        fields[name] = _array(fields[name], name)
        require(all(type(v) is str for v in fields[name]), "Scope kinds must be strings")
    return ScopeRule(**fields)


@dataclass(frozen=True)
class Rule(Record):
    id: str
    mechanism: str
    procedure: tuple[str, ...]
    when: str
    exceptions: tuple[str, ...]
    scope: ScopeRule
    evidence_ids: tuple[str, ...]

    def __post_init__(self):
        _identifier(self.id)
        text(self.mechanism, maximum=256)
        text(self.when, maximum=1024)
        _strings(self.procedure, maximum_items=8, maximum_bytes=1024, nonempty=True)
        _strings(self.exceptions, maximum_items=8, maximum_bytes=1024)
        require(type(self.scope) is ScopeRule, "Typed public-obligation scope required")
        _strings(self.evidence_ids, maximum_items=16, maximum_bytes=256)
        unique(self.evidence_ids, "evidence ID")
        require(len(json.dumps(self.to_dict(), ensure_ascii=False).encode()) <= 8192,
                "Rule exceeds serialized size budget")

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        for name in ("procedure", "exceptions", "evidence_ids"):
            data[name] = _array(data[name], name)
        data["scope"] = _scope(data["scope"])
        return cls(**data)


def _render(rules):
    if not rules:
        return ""
    # Explicit whitelist. Neither task annotations nor host evidence objects
    # enter this rendering. Keep every rule's conditions and exceptions.
    view = [{"id": r.id, "mechanism": r.mechanism, "when": r.when,
             "exceptions": list(r.exceptions), "procedure": list(r.procedure),
             "public_scope": r.scope.to_dict()} for r in rules]
    return ("Optional, unverified conditional Skill advice. The public task contract overrides this advice. "
            "Use a rule only when its prerequisites and exceptions permit it. Public-obligation matching "
            "is syntactic only; these rules have no deployment authorization.\n"
            + json.dumps({"rules": view}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


@dataclass(frozen=True)
class RuleSkill(Record):
    history_id: str
    rules: tuple[Rule, ...]

    def __post_init__(self):
        _identifier(self.history_id)
        typed_tuple(self.rules, Rule, maximum=MAX_RULES)
        unique([r.id for r in self.rules], "rule ID")
        require(len(_render(self.rules).encode()) <= MAX_RENDER_BYTES, "Skill exceeds rendered text budget")
        require(len(json.dumps(self.to_dict(), ensure_ascii=False).encode()) <= 24000,
                "Skill exceeds serialized size budget")

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        data["rules"] = tuple(Rule.from_dict(r) for r in _array(data["rules"], "rules"))
        return cls(**data)


def render_skill(skill):
    """Full-rule diagnostic rendering; empty cold starts are exactly No-Skill."""
    require(type(skill) is RuleSkill, "Typed RuleSkill required")
    return _render(skill.rules)


def render_for_task(skill, task):
    """Public-kind filtering only, not a trained router or a deployment gate."""
    require(type(skill) is RuleSkill and type(task) is CallableTask, "Typed Skill and public task required")
    selected = tuple(r for r in skill.rules if r.scope.matches(task))
    selected_ids = {r.id for r in selected}
    return {"text": _render(selected), "selected_rule_ids": [r.id for r in selected],
            "disabled_rule_ids": [r.id for r in skill.rules if r.id not in selected_ids],
            "scope_basis": SCOPE_BASIS, "deployment_authorized": False}


@dataclass(frozen=True)
class RuleEdit(Record):
    operation: str
    rule_id: str = ""
    rule: Rule | None = None
    evidence_ids: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self):
        _strings(self.evidence_ids, maximum_items=16, maximum_bytes=256)
        unique(self.evidence_ids, "edit evidence ID")
        text(self.reason, maximum=1024, empty=True)
        require(type(self.operation) is str and self.operation in
                {"add", "replace", "remove", "no_update", "scope_expansion_request"},
                "Unsupported local rule operation")
        if self.operation == "no_update":
            require(self.rule_id == "" and self.rule is None, "No-update cannot carry a hidden edit")
            return
        _identifier(self.rule_id)
        if self.operation == "remove":
            require(self.rule is None, "Removal cannot carry a replacement rule")
        else:
            require(type(self.rule) is Rule and self.rule.id == self.rule_id,
                    "Add/replace/scope request must bind the same stable rule ID")

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        data["evidence_ids"] = _array(data["evidence_ids"], "evidence_ids")
        if data["rule"] is not None:
            data["rule"] = Rule.from_dict(data["rule"])
        return cls(**data)


@dataclass(frozen=True)
class RuleUpdate(Record):
    parent_hash: str
    edits: tuple[RuleEdit, ...]

    def __post_init__(self):
        hash_text(self.parent_hash)
        typed_tuple(self.edits, RuleEdit, maximum=MAX_EDITS)
        require(bool(self.edits), "Use an explicit no_update operation")
        require(not any(e.operation == "no_update" for e in self.edits) or len(self.edits) == 1,
                "No-update cannot accompany other operations")
        unique([e.rule_id for e in self.edits], "edited rule ID")

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        data["edits"] = tuple(RuleEdit.from_dict(e) for e in _array(data["edits"], "edits"))
        return cls(**data)


@dataclass(frozen=True)
class RuleUpdateResult(Record):
    skill: RuleSkill
    changed: bool
    applied_rule_ids: tuple[str, ...]
    scope_expansion_requests: tuple[RuleEdit, ...]
    deployment_authorized: bool = False

    def __post_init__(self):
        require(type(self.skill) is RuleSkill and type(self.changed) is bool, "Typed update result required")
        typed_tuple(self.applied_rule_ids, str, maximum=MAX_EDITS)
        unique(self.applied_rule_ids, "applied rule ID")
        typed_tuple(self.scope_expansion_requests, RuleEdit, maximum=MAX_EDITS)
        require(all(e.operation == "scope_expansion_request" for e in self.scope_expansion_requests),
                "Only diagnostic scope requests belong here")
        require(self.deployment_authorized is False, "Rule edits never grant deployment authorization")

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        data["skill"] = RuleSkill.from_dict(data["skill"])
        data["applied_rule_ids"] = _array(data["applied_rule_ids"], "applied_rule_ids")
        data["scope_expansion_requests"] = tuple(RuleEdit.from_dict(e) for e in
                                                 _array(data["scope_expansion_requests"], "scope_expansion_requests"))
        return cls(**data)


def apply_update(parent, update, *, max_edits=MAX_EDITS):
    """Apply bounded local content edits; scope expansion is diagnostic only.

    No evidence validity, semantic improvement, or applicability is certified.
    A changed Skill has a new content hash and inherits no deployment rights.
    """
    require(type(parent) is RuleSkill and type(update) is RuleUpdate, "Typed parent and update required")
    require(type(max_edits) is int and 1 <= max_edits <= MAX_EDITS, "Edit budget must be one or two")
    require(update.parent_hash == parent.content_hash, "Update is not bound to this parent Skill")
    require(len(update.edits) <= max_edits, "Local edit budget exceeded")
    original = {r.id: r for r in parent.rules}
    rules = dict(original)
    applied, requests = [], []
    for edit in update.edits:
        if edit.operation == "no_update":
            continue
        if edit.operation == "add":
            require(edit.rule_id not in original, "Added rule ID already exists")
            rules[edit.rule_id] = edit.rule
            applied.append(edit.rule_id)
            continue
        require(edit.rule_id in original, "Edited rule ID does not exist in parent")
        old = original[edit.rule_id]
        if edit.operation == "scope_expansion_request":
            # Even a plausible proposal cannot change this Skill's live rules.
            requests.append(edit)
        elif edit.operation == "remove":
            del rules[edit.rule_id]
            applied.append(edit.rule_id)
        else:
            require(set(edit.rule.scope.required_obligation_kinds) >= set(old.scope.required_obligation_kinds)
                    and set(edit.rule.scope.forbidden_obligation_kinds) >= set(old.scope.forbidden_obligation_kinds),
                    "Replacement cannot expand syntactic scope; submit a diagnostic scope_expansion_request")
            if edit.rule != old:
                rules[edit.rule_id] = edit.rule
                applied.append(edit.rule_id)
    candidate = RuleSkill(parent.history_id, tuple(rules.values()))
    return RuleUpdateResult(candidate, candidate != parent, tuple(applied), tuple(requests))
