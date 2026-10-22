"""Test exclusion under TestAccess, behind its own owner consent (registration §8.1 "排除测试集"同意书, §3.1, §10 S0;
check O4; plan §2.10, T-EXCL-1).

The two S0 exclusion runs hold a TestAccess before any test-read consent exists: ``alfworld_test_identity`` (the
ALFWorld test set is ``valid_unseen`` and disjoint from the new games) and ``exclude_tests`` (the SearchQA new block
drops every item that is a test item, by id or by normalized question). The frozen ``evaluation.consent`` requires
``test_evaluation = true`` (coevo5/evaluation.py:152-159) and is not reused: both runs require the owner's separate,
write-once ``<root>/shared/exclusion-consent.json`` with exactly ``{exclusion_runs, by, date, note}`` and refuse
anything else, the test-read consent included. Their records hold counts and hashes only -- never a question, a
context, an answer, a test id or a game path -- and nothing here prints.

The CLI's ``exclude-tests`` writes both records once under ``<root>/shared/exclusion/`` (``protocol.EXCLUSION_DIR``).
``apply_exclusion`` reads the SearchQA record only from there (``persisted``; ticket C3-2): a SearchQA tail supply is
cut into slices only with the sealed ``searchqa-kept`` record it returns (``supply.slices(kept=)``), so no caller can
skip the exclusion or hand in a record of its own making.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from scripts.make_searchqa_fresh_sample import normalized
from skillopt.coevo5 import data
from skillopt.continual_eval.core import read_json, require, safe_path
from skillopt.validator_pilot.api import digest

from .protocol import (
    EXCLUSION_CONSENT,
    EXCLUSION_CONSENT_FIELDS,
    EXCLUSION_DIR,
    EXCLUSION_RUNS,
    RECORD_HASH,
    record,
    verified,
)
from .supply import RELEASE, task_folder

RECORD_KIND = "exclusion"  # version fivebench-execskill-v1-exclusion
KEPT_KIND = "searchqa-kept"  # the SearchQA tail supply without its test items (``apply_exclusion``)
ALFWORLD_RUN, SEARCHQA_RUN = EXCLUSION_RUNS
TEST_SPLIT = "valid_unseen"
EVIDENCE = "smoke"  # both runs are S0 steps of the smoke (registration §10)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def exclusion_consent(path):
    """The owner's exclusion consent (``<root>/shared/exclusion-consent.json``), checked for its exact key set."""
    path = safe_path(path)
    require(path.parts[-2:] == tuple(EXCLUSION_CONSENT.split("/")) and path.is_file(),
            "No recorded owner consent to the test-exclusion runs")
    value = read_json(path)
    runs = value.get("exclusion_runs") if isinstance(value, dict) else None
    require(isinstance(value, dict) and set(value) == EXCLUSION_CONSENT_FIELDS and value["by"] == "owner"
            and type(runs) is list and len(runs) == len(EXCLUSION_RUNS) and set(runs) == set(EXCLUSION_RUNS)
            and type(value["date"]) is str and value["date"].strip()
            and type(value["note"]) is str and value["note"].strip(),
            "No recorded owner consent to the test-exclusion runs")
    return value


def _opened(consent, access, run):
    """The consent record, checked before the test access is used."""
    value = exclusion_consent(consent)
    require(run in value["exclusion_runs"], "The exclusion consent does not cover " + run)
    require(isinstance(access, data.TestAccess), "A test-exclusion run needs a TestAccess")
    return value


def _supply_sha256(supply):
    """The digest of a supply's task ids (sorted): what binds an exclusion record to the supply it was made on."""
    return digest(sorted(str(i["task_id"]) for i in supply))


def exclude_tests(pinned, supply, *, access, consent):
    """SearchQA new block: the supply items that are test items -- by id, or by normalized question -- as a record of
    counts and hashes: ``dropped`` lists sha256(task id) of each dropped supply item, ``exclusion_sha256`` its digest,
    ``supply_sha256`` the digest of the supply's ids. ``apply_exclusion`` turns the persisted record into the kept
    supply."""
    consent_record = _opened(consent, access, SEARCHQA_RUN)
    test_ids = data.test_ids(pinned, "searchqa")
    tasks, _ = data.test_panel(pinned, "searchqa", access=access)
    questions = {_sha(normalized(task["public"]["question"])) for task in tasks}
    by_id = [i for i in supply if str(i["task_id"]) in test_ids]
    by_question = [i for i in supply if str(i["task_id"]) not in test_ids
                   and _sha(normalized(i["public"]["question"])) in questions]
    dropped = sorted(_sha(str(i["task_id"])) for i in by_id + by_question)
    return record(RECORD_KIND, EVIDENCE, {
        "run": SEARCHQA_RUN, "bench": "searchqa", "unit": access.unit, "consent_sha256": digest(consent_record),
        "counts": {"supply": len(supply), "test_items": len(tasks), "dropped_by_id": len(by_id),
                   "dropped_by_question": len(by_question), "kept": len(supply) - len(dropped)},
        "dropped": dropped, "exclusion_sha256": digest(dropped), "supply_sha256": _supply_sha256(supply)})


def persisted(root, run):
    """The record ``exclude-tests`` wrote once for ``run`` under ``<root>/shared/exclusion/``, verified (seal, kind,
    run; for SearchQA the digest of its dropped list). ValueError when it is missing or broken."""
    require(run in EXCLUSION_RUNS, "Unknown exclusion run")
    path = safe_path(root) / EXCLUSION_DIR / (run + ".json")
    require(path.is_file(), "No persisted %s record: run exclude-tests first" % run)
    value = verified(read_json(path), RECORD_KIND)
    require(value["run"] == run and (run != SEARCHQA_RUN or value["exclusion_sha256"] == digest(value["dropped"])),
            "Not a passing %s record" % run)
    return value


def apply_exclusion(supply, root, *, record_sha256=None):
    """The sealed ``searchqa-kept`` record of the SearchQA tail ``supply`` without the items its persisted exclusion
    record dropped (``persisted(root, ...)``; ticket C3-2): refused without that record, for a record made on another
    supply, and -- given the manifest's ``data.exclusion.searchqa_test_exclusion.record_sha256`` -- for any other
    record. Holds the kept items, the two hashes and the counts (``supply.slices(kept=)`` requires it)."""
    value = persisted(root, SEARCHQA_RUN)
    require(record_sha256 is None or value[RECORD_HASH] == record_sha256,
            "The persisted exclusion record is not the one the manifest binds")
    require(value["supply_sha256"] == _supply_sha256(supply) and value["counts"]["supply"] == len(supply),
            "Not the exclusion record of this supply")
    dropped = set(value["dropped"])
    kept = [i for i in supply if _sha(str(i["task_id"])) not in dropped]
    require(len(kept) == value["counts"]["kept"], "The exclusion record does not match this supply")
    return record(KEPT_KIND, value["evidence"], {
        "items": kept, "supply_sha256": value["supply_sha256"], "exclusion_record_sha256": value[RECORD_HASH],
        "counts": {"supply": len(supply), "dropped": len(supply) - len(kept), "kept": len(kept)}})


def release_path(game_file):
    """(split, path from the split on) of an ALFWorld game file inside the json_2.1.1 release; public, because the
    CLI's ALFWorld canary texts use the same normalization (ticket C3-2)."""
    parts = Path(game_file).parts
    require(RELEASE in parts and len(parts) > parts.index(RELEASE) + 1, "An ALFWorld game outside the release")
    start = parts.index(RELEASE) + 1
    return parts[start], "/".join(parts[start:])


def alfworld_test_identity(pinned, supply, *, access, consent):
    """The ALFWorld test set lies wholly in ``valid_unseen`` and shares no game with the new games (§10 S0: pass,
    otherwise stop): either failure raises with counts only, never a game path (isolation review finding 4); the
    record of a passing run carries counts and hashes only."""
    consent_record = _opened(consent, access, ALFWORLD_RUN)
    tasks, _ = data.test_panel(pinned, "alfworld", access=access)
    tests = [release_path(task["public"]["game_file"]) for task in tasks]
    splits = Counter(split for split, _ in tests)
    require(set(splits) == {TEST_SPLIT}, "The ALFWorld test set is not %s (games per split: %s); stop and report"
            % (TEST_SPLIT, dict(sorted(splits.items()))))
    test_games = {path for _, path in tests}
    test_rooms = {task_folder(path)[0] for path in test_games}
    supply_games = {release_path(item["gamefile"])[1] for item in supply}
    overlap = test_games & supply_games
    require(not overlap, "%d ALFWorld test games are new-game supply games; stop and report" % len(overlap))
    return record(RECORD_KIND, EVIDENCE, {
        "run": ALFWORLD_RUN, "bench": "alfworld", "unit": access.unit, "consent_sha256": digest(consent_record),
        "split": TEST_SPLIT, "disjoint": not overlap,
        "counts": {"test_games": len(test_games), "supply_games": len(supply_games), "overlap_games": len(overlap),
                   "test_rooms": len(test_rooms), "overlap_rooms": len(test_rooms & {item["room"] for item in supply})},
        "exclusion_sha256": digest(sorted(_sha(path) for path in test_games))})
