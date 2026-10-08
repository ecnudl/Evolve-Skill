"""Canonical five-domain split builder: synthetic sources only, no benchmark data."""
import pytest

from scripts import make_fivebench_split as split
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, write_json

PARTITIONS = ("development", "skill_confirmation", "final", "verifier_calibration")


def panel(folder, partition, benchmark, count=2, family=None):
    tasks = [{"task_id": f"{benchmark}-{partition}-{i}", "family_id": family or f"{benchmark}-{partition}-f{i}",
              "partition": partition} for i in range(count)]
    write_json(folder / f"{partition}.json", {"tasks": tasks})
    return [t["task_id"] for t in tasks]


def sources(tmp_path, *, crossing=False, learning=None, evaluated=None):
    train = {}
    for benchmark, name in (("bigcodebench", "bcb"), ("korbench", "kor"), ("spreadsheetbench", "sheet")):
        for partition in PARTITIONS[:3] if name == "sheet" else PARTITIONS:
            ids = panel(tmp_path / name, partition, benchmark,
                        family="shared-family" if crossing and name == "kor" and partition != "skill_confirmation"
                        else None)
            if partition == "development":
                train[benchmark] = ids
    for part, count in (("train", 2), ("val", 2), ("test", 5)):
        write_json(tmp_path / f"qa/{part}/items.json", [
            {"id": f"qa-{part}-{i}", "question": f"{part} question {i}?", "context": "c", "answers": ["a"]}
            for i in range(count)])
        native = {"train": "train", "val": "valid_seen", "test": "valid_unseen"}[part]
        write_json(tmp_path / f"alf/{part}/items.json", [
            {"id": f"{part}:{i}", "gamefile": f"json_2.1.1/{native}/scene-{part}-{i}/trial_1/game.tw-pddl",
             "task_type": "t"} for i in range(2)])
    train["searchqa"] = ["qa-train-0", "qa-train-1"]
    train["alfworld"] = ["train:0", "train:1"]
    references, roles = {}, {}
    for benchmark in BENCHMARKS:
        tasks = (evaluated or {}).get(benchmark, train[benchmark])
        plan = seal({"tasks": [{"benchmark": benchmark, "task_id": t} for t in tasks]})
        write_json(tmp_path / f"ref-{benchmark}/plan.json", plan)
        write_json(tmp_path / f"learning-{benchmark}.json",
                   {"tasks": [{"task_id": t} for t in (learning or {}).get(benchmark, train[benchmark][:1])]})
        references[benchmark] = {"root": str(tmp_path / f"ref-{benchmark}"), "plan_hash": plan["record_hash"]}
        roles[benchmark] = {"path": str(tmp_path / f"learning-{benchmark}.json")}
    write_json(tmp_path / "study/protocol.json", seal({"references": references, "roles": roles}))
    return {"f_study": tmp_path / "study", "searchqa_split": tmp_path / "qa", "alfworld_split": tmp_path / "alf",
            "sheet_panels": tmp_path / "sheet", "bcb_partitions": tmp_path / "bcb", "kor_panels": tmp_path / "kor"}


@pytest.fixture(autouse=True)
def small_sample(monkeypatch):
    monkeypatch.setattr(split, "SEARCHQA_TEST", 3)


def test_parts_follow_the_project_partitions_and_native_splits_and_bind_the_study(tmp_path):
    value = split.build(**sources(tmp_path))
    assert value["version"] == "fivebench-split-v2" and value["model_calls"] == 0
    assert value["counts"]["bigcodebench"] == {"train": 2, "val": 2, "test": 2, "reserve": 2}
    assert value["counts"]["spreadsheetbench"]["reserve"] == 0 and value["counts"]["alfworld"]["reserve"] == 0
    assert value["counts"]["searchqa"] == {"train": 2, "val": 2, "test": 3, "reserve": 2}  # sampled native test
    assert [e["task_id"] for e in value["splits"]["bigcodebench"]["test"]] == ["bigcodebench-final-0",
                                                                             "bigcodebench-final-1"]
    again = split.build(**sources(tmp_path / "again"))
    assert value["splits"] == again["splits"]  # the sample depends only on the fixed seed and the ids
    usage = value["f_study_usage"]["korbench"]
    assert set(usage) >= {"protocol_hash", "reference_plan_hash", "learning_panel_sha256"}
    assert "not an exposure-filtered independent final" in value["claim"] and set(value["exposure"]) == set(BENCHMARKS)
    entries = [e for b in value["splits"].values() for part in b.values() for e in part]
    assert all(set(e) == {"task_id", "family_id"} for e in entries)  # ids only, no task content


def test_a_family_crossing_parts_is_refused(tmp_path):
    with pytest.raises(ValueError, match="korbench: family crosses parts"):
        split.build(**sources(tmp_path, crossing=True))


@pytest.mark.parametrize("kwargs,message", [
    ({"learning": {"bigcodebench": ["bigcodebench-development-0", "bigcodebench-final-0"]}}, "learned outside train"),
    ({"evaluated": {"searchqa": ["qa-train-0"]}}, "not exactly train"),
    ({"evaluated": {"alfworld": ["train:0", "train:1", "test:0"]}}, "not exactly train"),
])
def test_a_study_that_used_tasks_outside_train_is_refused(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        split.build(**sources(tmp_path, **kwargs))
