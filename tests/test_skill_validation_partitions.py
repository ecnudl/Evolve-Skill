"""Data boundary tests; all records here are explicitly synthetic fixtures."""

from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.partitions import PARTITIONS, PartitionEntry, PartitionManifest


def entry(**kwargs):
    values = {"record_id": "fixture:task-1/base/0", "original_task_id": "source:task-1",
              "near_duplicate_family": "source:family-1", "project_id": "project-1",
              "partition": "development", "provenance_kind": "fixture",
              "provenance_complete": True}
    return PartitionEntry(**(values | kwargs))


def test_five_distinct_data_purposes():
    assert PARTITIONS == {"development", "verifier_calibration", "verifier_audit",
                          "skill_confirmation", "final"}


def test_idempotent_registration_and_json_round_trip():
    record = entry()
    registry = PartitionManifest()
    assert registry.register(record) == record
    assert registry.register(record) == record
    assert len(registry.entries) == 1
    envelope = registry.to_dict()
    assert PartitionManifest.from_dict(envelope).to_dict() == envelope
    assert PartitionEntry.from_dict(record.to_dict()) == record
    registry.validate()


def test_all_artifact_conditions_and_repeats_stay_together():
    registry = PartitionManifest([entry()])
    for condition in ("base", "current", "candidate"):
        for repeat in (1, 2):
            registry.register(entry(record_id=f"fixture:task-1/{condition}/{repeat}"))
    assert len(registry.entries) == 7
    for purpose in PARTITIONS - {"development"}:
        with pytest.raises(ValueError, match="Original task cannot cross"):
            registry.register(entry(record_id=f"new-{purpose}", partition=purpose))
    assert len(registry.entries) == 7


def test_near_duplicate_cannot_cross_even_with_distinct_original_task():
    registry = PartitionManifest([entry()])
    with pytest.raises(ValueError, match="Near-duplicate family"):
        registry.register(entry(record_id="task-2", original_task_id="source:task-2", partition="final"))


def test_same_project_is_not_automatically_a_partition_group():
    second = entry(record_id="task-2", original_task_id="source:task-2",
                   near_duplicate_family="source:family-2", partition="final")
    assert len(PartitionManifest([entry(), second]).entries) == 2
    with pytest.raises(ValueError, match="Project cannot cross"):
        PartitionManifest([entry(), second], project_disjoint=True)
    with pytest.raises(ValueError, match="requires every project identity"):
        PartitionManifest([entry(project_id="")], project_disjoint=True)


def test_conflicting_repeat_or_provenance_assignment_is_atomic():
    registry = PartitionManifest([entry()])
    before = registry.to_dict()
    with pytest.raises(ValueError, match="Conflicting assignment"):
        registry.register(entry(provenance_complete=False))
    assert registry.to_dict() == before


@pytest.mark.parametrize("changed", [{"near_duplicate_family": "different-family"}, {"project_id": "different-project"}])
def test_original_task_cannot_be_relabelled_to_evade_grouping(changed):
    registry = PartitionManifest([entry()])
    with pytest.raises(ValueError, match="cannot change its family or project"):
        registry.register(entry(record_id="alternate", **changed))


@pytest.mark.parametrize("kind", ["fixture", "mutant"])
def test_non_natural_records_never_count_as_formal_natural_evidence(kind):
    record = entry(provenance_kind=kind, partition="verifier_calibration")
    registry = PartitionManifest([record])
    assert not record.formal_eligible
    with pytest.raises(ValueError, match="diagnostic-only"):
        registry.require_eligible(record.record_id, "verifier_calibration")


def test_incomplete_model_import_is_retained_but_not_formal_evidence():
    record = entry(provenance_kind="model", provenance_complete=False)
    registry = PartitionManifest([record])
    assert registry.entries == (record,)
    assert record.ineligible_reasons == ("incomplete_provenance",)
    with pytest.raises(ValueError, match="incomplete_provenance"):
        registry.require_eligible(record.record_id, "development")
    # Merely tagging a newly constructed record as model does not default to complete.
    assert not PartitionEntry("r", "t", "f", "p", "development").formal_eligible


def test_host_attested_complete_model_can_only_be_consumed_for_assigned_purpose():
    # Unit-test metadata only; this does not represent a real run or effect evidence.
    record = entry(provenance_kind="model", partition="verifier_audit")
    registry = PartitionManifest([record])
    assert registry.require_eligible(record.record_id, "verifier_audit") == record
    with pytest.raises(ValueError, match="different validation purpose"):
        registry.require_eligible(record.record_id, "final")
    with pytest.raises(ValueError, match="not registered"):
        registry.require_eligible("absent", "verifier_audit")


def test_exposed_legacy_is_development_only_even_with_closed_provenance():
    record = entry(provenance_kind="model", legacy_exposed=True)
    assert not record.formal_eligible
    assert record.ineligible_reasons == ("previously_exposed_legacy",)
    with pytest.raises(ValueError, match="development-only"):
        replace(record, partition="skill_confirmation")


def test_checksum_and_schema_are_validated():
    registry = PartitionManifest([entry()])
    altered = registry.to_dict()
    altered["entries"][0]["partition"] = "final"
    with pytest.raises(ValueError, match="checksum mismatch"):
        PartitionManifest.from_dict(altered)
    payload = {k: v for k, v in registry.to_dict().items() if k != "manifest_hash"}
    payload["extra"] = "not-allowed"
    with pytest.raises(ValueError, match="manifest fields"):
        PartitionManifest.from_dict(seal(payload, "manifest_hash"))
    with pytest.raises(ValueError, match="entry fields"):
        PartitionEntry.from_dict(entry().to_dict() | {"formal_eligible": True})


def test_deserialization_checks_conflicts_not_just_checksum():
    records = [entry(), entry(record_id="different", partition="final")]
    payload = {"version": "skill-validation-partitions-v1", "project_disjoint": False,
               "entries": [r.to_dict() for r in records]}
    with pytest.raises(ValueError, match="Original task cannot cross"):
        PartitionManifest.from_dict(seal(payload, "manifest_hash"))
    payload["entries"] = [records[0].to_dict(), records[0].to_dict()]
    with pytest.raises(ValueError, match="duplicate record"):
        PartitionManifest.from_dict(seal(payload, "manifest_hash"))


@pytest.mark.parametrize("invalid", [
    {"partition": "test"}, {"provenance_kind": "real"}, {"provenance_complete": 1},
    {"legacy_exposed": "false"}, {"original_task_id": ""}, {"near_duplicate_family": ""},
    {"record_id": " accidental-padding "},
])
def test_invalid_metadata_is_rejected(invalid):
    with pytest.raises(ValueError):
        entry(**invalid)


def test_serialized_order_does_not_depend_on_registration_order():
    first = entry(record_id="z")
    second = entry(record_id="a")
    assert PartitionManifest([first, second]).to_dict() == PartitionManifest([second, first]).to_dict()
