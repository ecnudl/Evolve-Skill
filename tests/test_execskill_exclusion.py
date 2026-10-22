"""execskill test exclusion (registration §8.1 exclusion consent, §3.1, §10 S0; plan T-EXCL-1): the exact consent
key set, refusal without it (and of the test-read consent in its place), counts and hashes only. The test set is a
fake behind a real ``data.TestAccess``: ``data.test_ids``/``data.test_panel`` are replaced by synthetic readers."""
import json

import pytest

from skillopt.coevo5 import data
from skillopt.continual_eval.core import write_json
from skillopt.execskill import exclusion, protocol, supply
from tests.fixtures.execskill import items as fx

CONSENT = {"exclusion_runs": ["alfworld_test_identity_check", "searchqa_test_exclusion"], "by": "owner",
           "date": "2026-10-21", "note": "Owner allows the two S0 exclusion runs (fixture)."}
TEST_QUESTION = "Which fixture town keeps the bell number 4?"
TEST_GAMES = ["json_2.1.1/valid_unseen/look_at_obj_in_light-Obj0-None-Recep0-%d/trial_T%d/game.tw-pddl" % (n, n)
              for n in (1, 2, 3)]


def _consent(tmp_path, value=CONSENT, name="exclusion-consent.json", folder="shared"):
    path = tmp_path / "root" / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.fixture
def fake_tests(monkeypatch, tmp_path):
    """Synthetic test readers that demand a TestAccess and count their reads."""
    reads = []

    def test_ids(pinned, benchmark):
        reads.append(("ids", benchmark))
        return frozenset({"fx-searchqa-02", "sq-test-1"})

    def test_panel(pinned, benchmark, *, access):
        assert isinstance(access, data.TestAccess)
        reads.append(("panel", benchmark))
        if benchmark == "searchqa":
            tasks = [{"task_id": "sq-test-1", "public": {"question": "  which FIXTURE town keeps the bell number 4  ",
                                                         "context": "secret test context"}}]
        else:
            tasks = [{"task_id": "alf-test-%d" % n, "public": {"game_file": str(tmp_path / "data" / game)}}
                     for n, game in enumerate(fake_tests_games)]
        return tasks, {"tasks": len(tasks)}

    fake_tests_games = list(TEST_GAMES)
    monkeypatch.setattr(data, "test_ids", test_ids)
    monkeypatch.setattr(data, "test_panel", test_panel)
    return {"reads": reads, "games": fake_tests_games}


def test_consent_key_set_is_exact(tmp_path):
    assert exclusion.exclusion_consent(_consent(tmp_path)) == CONSENT
    for value in ({**CONSENT, "extra": 1}, {k: v for k, v in CONSENT.items() if k != "note"},
                  {**CONSENT, "by": "agent"}, {**CONSENT, "exclusion_runs": ["searchqa_test_exclusion"]},
                  {**CONSENT, "exclusion_runs": CONSENT["exclusion_runs"] * 2}, {**CONSENT, "note": " "},
                  {"test_evaluation": True, "sheet_test_qualification": True, "multi_arm_arms": ["F", "C"],
                   "by": "owner", "date": "2026-10-21", "note": "test-read consent"}):
        with pytest.raises(ValueError, match="consent"):
            exclusion.exclusion_consent(_consent(tmp_path / "bad", value))
    with pytest.raises(ValueError, match="consent"):  # the test-read consent's file, even with these keys
        exclusion.exclusion_consent(_consent(tmp_path / "read", name="consent.json"))
    with pytest.raises(ValueError, match="consent"):
        exclusion.exclusion_consent(_consent(tmp_path / "dir", folder="elsewhere"))
    with pytest.raises(ValueError, match="consent"):
        exclusion.exclusion_consent(tmp_path / "missing" / "shared" / "exclusion-consent.json")


def test_both_runs_refuse_without_the_exclusion_consent(tmp_path, fake_tests):
    access = data.TestAccess("s0/exclusion")
    read_consent = _consent(tmp_path / "read", {"test_evaluation": True, "sheet_test_qualification": True,
                                                "multi_arm_arms": ["F", "C", "P_F", "T_F", "twins"], "by": "owner",
                                                "date": "2026-10-21", "note": "test read"}, name="consent.json")
    for consent in (tmp_path / "none" / "shared" / "exclusion-consent.json", read_consent):
        with pytest.raises(ValueError, match="consent"):
            exclusion.exclude_tests({}, fx.searchqa_items(), access=access, consent=consent)
        with pytest.raises(ValueError, match="consent"):
            exclusion.alfworld_test_identity({}, [], access=access, consent=consent)
    with pytest.raises(ValueError, match="TestAccess"):
        exclusion.exclude_tests({}, fx.searchqa_items(), access="s0/exclusion", consent=_consent(tmp_path))
    assert fake_tests["reads"] == []  # nothing of the test set was read


def test_searchqa_exclusion_holds_counts_and_hashes_only(tmp_path, fake_tests):
    pool = fx.searchqa_items()
    record = exclusion.exclude_tests({}, pool, access=data.TestAccess("s0/exclusion"), consent=_consent(tmp_path))
    assert record["counts"] == {"supply": 20, "test_items": 1, "dropped_by_id": 1, "dropped_by_question": 1,
                                "kept": 18}
    assert record["version"] == "fivebench-execskill-v1-exclusion" and record["evidence"] == "smoke"
    assert record["exclusion_sha256"] == exclusion.digest(record["dropped"])
    text = json.dumps(record)
    for secret in ("secret test context", "bell number", "sq-test-1", "fx-searchqa-02", "fx-searchqa-04"):
        assert secret not in text
    root = tmp_path / "root"
    with pytest.raises(ValueError, match="exclude-tests first"):  # ticket C3-2: no persisted record, no kept supply
        exclusion.apply_exclusion(pool, root)
    write_json(root / protocol.EXCLUSION_DIR / (exclusion.SEARCHQA_RUN + ".json"), record)
    kept = exclusion.apply_exclusion(pool, root, record_sha256=record[protocol.RECORD_HASH])
    assert protocol.verified(kept, "searchqa-kept") == kept and kept["evidence"] == "smoke"
    assert [i["task_id"] for i in kept["items"]] == [i["task_id"] for i in pool if i["task_id"] not in
                                                     ("fx-searchqa-02", "fx-searchqa-04")]
    assert kept["exclusion_record_sha256"] == record[protocol.RECORD_HASH]
    assert kept["counts"] == {"supply": 20, "dropped": 2, "kept": 18}
    with pytest.raises(ValueError, match="exclusion record of this supply"):
        exclusion.apply_exclusion(pool[1:], root)
    with pytest.raises(ValueError, match="exclusion record of this supply"):  # same size, another supply
        exclusion.apply_exclusion(pool[1:] + [{**pool[0], "task_id": "fx-other"}], root)
    with pytest.raises(ValueError, match="manifest binds"):
        exclusion.apply_exclusion(pool, root, record_sha256="0" * 64)


def test_c3_2_a_searchqa_tail_is_cut_only_with_its_persisted_exclusion(tmp_path, fake_tests):
    tail = [{**item, "part": "tail"} for item in fx.searchqa_items()]
    record = exclusion.exclude_tests({}, tail, access=data.TestAccess("s0/exclusion"), consent=_consent(tmp_path))
    order = supply.order("searchqa", tail)
    with pytest.raises(ValueError, match="persisted test exclusion"):
        supply.slices("searchqa", order, {"run": 5})
    root = tmp_path / "root"
    write_json(root / protocol.EXCLUSION_DIR / (exclusion.SEARCHQA_RUN + ".json"), record)
    kept = exclusion.apply_exclusion(tail, root)
    cut = supply.slices("searchqa", supply.order("searchqa", kept["items"]), {"run": 5, "accept": 10}, kept=kept)
    taken = {i["task_id"] for name in ("run", "accept") for i in cut[name]}
    assert len(taken) == 15 and not taken & {"fx-searchqa-02", "fx-searchqa-04"}
    with pytest.raises(ValueError, match="outside the kept supply"):  # the dropped test items cannot be cut
        supply.slices("searchqa", order, {"run": 5}, kept=kept)
    with pytest.raises(ValueError):  # the kept record must be sealed
        supply.slices("searchqa", supply.order("searchqa", kept["items"]), {"run": 5},
                      kept={**kept, "items": tail})
    assert supply.slices("searchqa", supply.order("searchqa", fx.searchqa_items()), {"run": 3})["run"]  # pool items
    broken = tmp_path / "broken"
    write_json(broken / protocol.EXCLUSION_DIR / (exclusion.SEARCHQA_RUN + ".json"),
               {**record, "counts": {**record["counts"], "kept": 20}})
    with pytest.raises(ValueError):  # a changed record breaks its seal
        exclusion.apply_exclusion(tail, broken)
    with pytest.raises(ValueError, match="exclude-tests first"):
        exclusion.persisted(root, exclusion.ALFWORLD_RUN)


def test_alfworld_identity_checks_the_split_and_disjointness(tmp_path, fake_tests):
    access, consent = data.TestAccess("s0/alfworld-identity"), _consent(tmp_path)
    games = fx.alfworld_tree(tmp_path / "data", 3, lambda r: 2, first_room=301)
    items = supply.alfworld_items(tmp_path / "data", {})
    record = exclusion.alfworld_test_identity({}, items, access=access, consent=consent)
    assert record["split"] == "valid_unseen" and record["disjoint"] is True
    assert record["counts"] == {"test_games": 3, "supply_games": 6, "overlap_games": 0, "test_rooms": 3,
                                "overlap_rooms": 0}
    assert not any(part in json.dumps(record) for part in ("valid_unseen/", "json_2.1.1", "Recep0"))
    clash = items + [{"task_id": "x", "gamefile": TEST_GAMES[0], "room": "1"}]
    with pytest.raises(ValueError, match="1 ALFWorld test games are new-game supply games; stop and report"):
        exclusion.alfworld_test_identity({}, clash, access=access, consent=consent)
    fake_tests["games"].append(games[0])  # a train game in the test set: stop and report
    with pytest.raises(ValueError, match="not valid_unseen"):
        exclusion.alfworld_test_identity({}, items, access=access, consent=consent)


def test_isolation_4_an_overlapping_supply_stops_with_counts_only(tmp_path, fake_tests):
    """Isolation review finding 4: a test game in the new-game supply stops the S0 identity run (it is not merely
    recorded), and the refusal names a count, never a game path."""
    access, consent = data.TestAccess("s0/alfworld-identity"), _consent(tmp_path)
    fx.alfworld_tree(tmp_path / "data", 2, lambda r: 1, first_room=301)
    items = supply.alfworld_items(tmp_path / "data", {})
    clash = items + [{"task_id": "x%d" % i, "gamefile": game, "room": "1"} for i, game in enumerate(TEST_GAMES[:2])]
    with pytest.raises(ValueError) as refused:
        exclusion.alfworld_test_identity({}, clash, access=access, consent=consent)
    assert str(refused.value).startswith("2 ALFWorld test games")
    assert not any(part in str(refused.value) for part in ("valid_unseen/", "json_2.1.1", "game.tw-pddl"))
    assert exclusion.alfworld_test_identity({}, items, access=access, consent=consent)["disjoint"] is True
