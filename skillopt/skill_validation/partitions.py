"""Host-side grouping and provenance checks for validation data partitions.

The manifest records eligibility; it does not authenticate a model run. Importers
must establish ``provenance_complete`` from the actual source records. Neither
host grouping labels nor this manifest belong in a model-visible input view.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Iterable

from skillopt.coevolution_v5.core import seal, verify

PARTITIONS = frozenset({
    "development", "verifier_calibration", "verifier_audit",
    "skill_confirmation", "final",
})
PROVENANCE_KINDS = frozenset({"model", "fixture", "mutant"})
MANIFEST_VERSION = "skill-validation-partitions-v1"


def _identifier(value: Any, field: str, *, optional: bool = False) -> None:
    if not isinstance(value, str) or (not optional and not value.strip()):
        raise ValueError(f"{field} must be a nonempty string")
    if value != value.strip():
        raise ValueError(f"{field} must not contain surrounding whitespace")


@dataclass(frozen=True)
class PartitionEntry:
    """One artifact/run's host identity and dataset assignment.

    IDs must be source-qualified, not just a row number. A singleton task should
    still have an explicit ``near_duplicate_family`` (e.g. its source task ID).
    ``record_id`` distinguishes conditions/repeats; those variants retain the
    same original task and family. Project grouping is optional protocol policy.
    """

    record_id: str
    original_task_id: str
    near_duplicate_family: str
    project_id: str
    partition: str
    provenance_kind: str = "model"
    provenance_complete: bool = False
    legacy_exposed: bool = False

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        for name in ("record_id", "original_task_id", "near_duplicate_family"):
            _identifier(getattr(self, name), name)
        _identifier(self.project_id, "project_id", optional=True)
        if not isinstance(self.partition, str) or self.partition not in PARTITIONS:
            raise ValueError("Unknown validation partition")
        if not isinstance(self.provenance_kind, str) or self.provenance_kind not in PROVENANCE_KINDS:
            raise ValueError("Unknown provenance kind")
        if type(self.provenance_complete) is not bool or type(self.legacy_exposed) is not bool:
            raise ValueError("Provenance flags must be explicit booleans")
        if self.legacy_exposed and self.partition != "development":
            raise ValueError("Previously exposed legacy records are development-only diagnostics")

    @property
    def ineligible_reasons(self) -> tuple[str, ...]:
        reasons = []
        if self.provenance_kind != "model":
            reasons.append(f"non_natural_{self.provenance_kind}")
        if not self.provenance_complete:
            reasons.append("incomplete_provenance")
        if self.legacy_exposed:
            reasons.append("previously_exposed_legacy")
        return tuple(reasons)

    @property
    def formal_eligible(self) -> bool:
        """Eligible as natural-data evidence, not an approval or truth label.

        Fixtures and mutants may exercise any partition's engineering flow, but
        cannot be counted as natural model evidence for a formal acceptance.
        """
        return not self.ineligible_reasons

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PartitionEntry":
        if not isinstance(value, dict) or set(value) != {f.name for f in fields(cls)}:
            raise ValueError("Partition entry fields do not match the schema")
        return cls(**value)


class PartitionManifest:
    """Small, serializable registry with atomic, idempotent registration.

    The same task or near-duplicate family must not cross purposes, irrespective
    of condition, repeat, provenance kind or artifact content. Sharing a project
    across purposes is allowed unless ``project_disjoint=True`` was declared.
    The checksum detects mismatch, not deliberate forgery or execution validity.
    """

    def __init__(self, entries: Iterable[PartitionEntry] = (), *, project_disjoint: bool = False):
        if type(project_disjoint) is not bool:
            raise ValueError("project_disjoint must be an explicit boolean")
        self._project_disjoint = project_disjoint
        self._entries: dict[str, PartitionEntry] = {}
        for entry in entries:
            self.register(entry)

    @property
    def project_disjoint(self) -> bool:
        return self._project_disjoint

    @property
    def entries(self) -> tuple[PartitionEntry, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))

    def register(self, entry: PartitionEntry) -> PartitionEntry:
        if not isinstance(entry, PartitionEntry):
            raise ValueError("Expected a PartitionEntry")
        entry.validate()
        previous = self._entries.get(entry.record_id)
        if previous is not None:
            if previous != entry:
                raise ValueError("Conflicting assignment or provenance for an existing record")
            return previous
        if self.project_disjoint and not entry.project_id:
            raise ValueError("Project-disjoint protocol requires every project identity")
        for old in self._entries.values():
            if old.original_task_id == entry.original_task_id:
                if (old.near_duplicate_family, old.project_id) != (entry.near_duplicate_family, entry.project_id):
                    raise ValueError("Original task cannot change its family or project metadata")
                if old.partition != entry.partition:
                    raise ValueError("Original task cannot cross validation partitions")
            if old.near_duplicate_family == entry.near_duplicate_family and old.partition != entry.partition:
                raise ValueError("Near-duplicate family cannot cross validation partitions")
            if (self.project_disjoint and old.project_id == entry.project_id
                    and old.partition != entry.partition):
                raise ValueError("Project cannot cross partitions in a project-disjoint protocol")
        self._entries[entry.record_id] = entry
        return entry

    def validate(self) -> None:
        # Rebuild through the same checks, including after deserialization.
        PartitionManifest(self.entries, project_disjoint=self.project_disjoint)

    def get(self, record_id: str) -> PartitionEntry:
        try:
            return self._entries[record_id]
        except KeyError:
            raise ValueError("Record is not registered in this partition manifest") from None

    def require_eligible(self, record_id: str, purpose: str) -> PartitionEntry:
        """Fail closed before consuming a record as formal natural-data evidence."""
        if not isinstance(purpose, str) or purpose not in PARTITIONS:
            raise ValueError("Unknown validation purpose")
        entry = self.get(record_id)
        if entry.partition != purpose:
            raise ValueError("Record was assigned to a different validation purpose")
        if not entry.formal_eligible:
            raise ValueError("Record is diagnostic-only: " + ", ".join(entry.ineligible_reasons))
        return entry

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return seal({"version": MANIFEST_VERSION, "project_disjoint": self.project_disjoint,
                     "entries": [entry.to_dict() for entry in self.entries]}, "manifest_hash")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PartitionManifest":
        value = verify(value, "manifest_hash")
        if set(value) != {"version", "project_disjoint", "entries", "manifest_hash"}:
            raise ValueError("Partition manifest fields do not match the schema")
        if value["version"] != MANIFEST_VERSION or not isinstance(value["entries"], list):
            raise ValueError("Invalid partition manifest version or entries")
        entries = [PartitionEntry.from_dict(row) for row in value["entries"]]
        if len({entry.record_id for entry in entries}) != len(entries):
            raise ValueError("Serialized manifest contains duplicate record identities")
        return cls(entries, project_disjoint=value["project_disjoint"])
