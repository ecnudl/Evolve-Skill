"""Pinned, by-value ALFWorld v11 import for main-v3's fifth step; zero learning calls."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import profiles as p
from .package import Package, Procedure, ensure, load, save

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/execskill/v210_alfworld_v11_package"
ORIGIN = "alfworld_v11_real_run"
PACKAGE_SHA256 = "7d814ba51fb589ecd1480c14e57757cb383942520798eb10d43481f796520eb4"
PACKAGE_FILE_SHA256 = "be9acfdc7311a9fe099e7fdd5b3289a68ddf53c076944b49f80a24e46c0eae00"
IMPORT_SOURCE_BYTES = 5_404
IMPORT_PROCEDURES = 3
LEARNED_SOURCE_BYTES = p.MAX_PACKAGE_BYTES - IMPORT_SOURCE_BYTES
LEARNED_PROCEDURES = p.MAX_PROCEDURES - IMPORT_PROCEDURES
# (id, sealed procedure hash, file bytes hash, source text hash), frozen before v2.10.
PROCEDURES = (
    ("p-alfworld-1-15", "768778bd771e5c9470f8faf1e36e51af33418503c492e77b8db8044f02ac689c",
     "a137e94c664dedbc5b2a42038208181c7d7481a3dd266e58a086b84d87c01142",
     "6c501e61b311842c1324fecb4fa92693323d2b6904b69639f6b9af67378acced"),
    ("p-alfworld-1-14", "9ab7ff8b708e0992ffa1ecaa8a68334587e63e6523e0fe61d8960992709fa919",
     "cfeb6dad0e3fa24b81ae3129b92c61cbb274d93df4c2bbe03ae463547854f8f8",
     "d6edc0d628c73cbcb19d3bf5800470420db4464b12bdb4e32ecc11fade28edc8"),
    ("p-alfworld-1-6", "a93758eae5454350a6cbb1301032f4de94c05d82159edc699e72d065e530f262",
     "70b5837d3443bffe6d68e61234c81e9670e7ea03e56245f0332c7fbd3184675a",
     "e68f5bf901711700abbd8e6ceeddb32bbc0d1c672f080db77f9e5caea573d96c"),
)


def pins(*, fixture=None):
    """Detached source records and all hashes; refuse even a resealed modified fixture."""
    root = safe_path(fixture or FIXTURE)
    package_path = root / "packages" / (PACKAGE_SHA256 + ".json")
    require(hashlib.sha256(package_path.read_bytes()).hexdigest() == PACKAGE_FILE_SHA256,
            "The alfworld-v11 source package file hash differs from the fixture pin")
    package = load(package_path)
    require(package.evidence == ORIGIN and package.sha256 == PACKAGE_SHA256
            and package.order == tuple(row[0] for row in PROCEDURES), "The alfworld-v11 source package identity")
    procedures = []
    for pid, record_sha, file_sha, source_sha in PROCEDURES:
        source = root / "procedures" / (record_sha + ".json")
        require(hashlib.sha256(source.read_bytes()).hexdigest() == file_sha,
                "The alfworld-v11 procedure file hash differs from the fixture pin")
        procedure = package.get(pid)
        require(procedure.sha256 == record_sha and procedure.evidence == ORIGIN
                and hashlib.sha256(procedure.source.encode()).hexdigest() == source_sha,
                "The alfworld-v11 procedure source hash differs from the fixture pin")
        procedures.append({"id": pid, "record_sha256": record_sha, "file_sha256": file_sha,
                           "source_sha256": source_sha, "record": procedure.to_json()})
    require(sum(len(row["record"]["source"].encode()) for row in procedures) == IMPORT_SOURCE_BYTES
            and len(procedures) == IMPORT_PROCEDURES, "The preregistered import capacity reservation")
    return {"origin": ORIGIN, "package_record_sha256": PACKAGE_SHA256,
            "package_file_sha256": PACKAGE_FILE_SHA256, "package": package.to_json(),
            "procedures": procedures}


def learning_capacity(package):
    """Reserve the immutable import inside the inherited package cap, before any adoption."""
    used_bytes = sum(len(procedure.source.encode()) for procedure in package.procedures)
    return {"package_source_bytes": LEARNED_SOURCE_BYTES, "package_procedures": LEARNED_PROCEDURES,
            "reserved_import_source_bytes": IMPORT_SOURCE_BYTES, "reserved_import_procedures": IMPORT_PROCEDURES,
            "used_source_bytes": used_bytes, "used_procedures": len(package.procedures),
            "remaining_source_bytes": LEARNED_SOURCE_BYTES - used_bytes,
            "remaining_procedures": LEARNED_PROCEDURES - len(package.procedures)}


def check_learning_capacity(package):
    capacity = learning_capacity(package)
    ensure(capacity["remaining_source_bytes"] >= 0 and capacity["remaining_procedures"] >= 0,
           "main-v3 reserves 5404 source bytes and 3 procedure slots for alfworld-v11: "
           "the learned package may use at most 58596 bytes and 21 procedures")
    return package


def import_step(setting, chain_root, chain, k, bench, parent):
    """Compose the old chain parent with a newly evidenced copy of the frozen v11 package.

    The import has its own parent package (the v11 copy) and a provenance record;
    the final package retains the chain's learned procedures in their existing order.
    Source procedure fields are unchanged except evidence and its resulting record hash.
    """
    require(p.configuration_of(setting) in (p.MAIN_V3, p.MAIN_V4, p.MAIN_V5, p.IMPLANT_V5) and chain in p.CHAINS and k == 5 and bench == "alfworld",
            "The registered main-v3 ALFWorld import is step 5")
    source = pins()
    require(setting.extra.get("alfworld_v11_import") == source,
            "The alfworld-v11 import pins differ from the immutable fixture")
    require(isinstance(parent, Package), "The import retains the earlier chain package")
    check_learning_capacity(parent)
    root = safe_path(chain_root)
    name = "%s/s5-alfworld" % chain
    procedures = tuple(replace(Procedure.from_json(row["record"]), evidence=setting.evidence)
                       for row in source["procedures"])
    imported = Package(procedures, name + "/import", setting.evidence,
                       parent_sha256=PACKAGE_SHA256, retired=tuple(source["package"]["retired"]),
                       narrowed=source["package"]["narrowed"], describer=source["package"]["describer"])
    package = Package(parent.procedures + procedures, name, setting.evidence, parent.sha256,
                      parent.retired, {**parent.narrowed, **imported.narrowed},
                      {**parent.describer, **imported.describer})
    provenance = p.record("import-v2-10", setting.evidence, {
        "origin": ORIGIN, "source": source, "imported_package_sha256": imported.sha256,
        "procedures": [{"id": original["id"], "source_record_sha256": original["record_sha256"],
                         "source_sha256": original["source_sha256"], "imported_record_sha256": copied.sha256}
                        for original, copied in zip(source["procedures"], procedures)]})
    value = p.record("step-v2-3", setting.evidence, {
        "chain": chain, "k": k, "bench": bench, "step": name, "learning": "import",
        "origin": ORIGIN, "parent_sha256": imported.sha256, "chain_parent_sha256": parent.sha256,
        "source_package_sha256": PACKAGE_SHA256, "candidate_sha256": None,
        "package_sha256": package.sha256, "decision": "import", "reason": "preregistered_alfworld_v11_import",
        "decision_sha256": None, "fault_items": [], "violating_items": [], "units": {},
        "evidence_kind": "import", "import_sha256": provenance[p.RECORD_HASH]})
    final = root / "s5-alfworld" / "step.json"
    if final.exists():
        require(p.verified(read_json(final), "step") == value, "A finished import step has different pins or parents")
        require(p.verified(read_json(final.with_name("import.json")), "import-v2-10") == provenance,
                "A finished import has different provenance")
        return load(root / "packages" / (package.sha256 + ".json")), value
    save(root, imported)
    save(root, package)
    write_json(final.with_name("import.json"), provenance)
    write_json(final, value)
    return package, value
