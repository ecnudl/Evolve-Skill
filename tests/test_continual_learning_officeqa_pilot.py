"""The OfficeQA one-call headroom pilot: only train/validation items, original scorer on the answer tag, sealed run."""
import csv
import json

import pytest

from scripts import pilot_officeqa_headroom as pilot
from skillopt.continual_eval.core import read_json
from tests.test_continual_learning_generated_validation import _study
from tests.test_continual_learning_livemath_pilot import Client as Base

ROWS = [("u1", "train", "easy", "1,234.5"), ("u2", "train", "hard", "42"), ("u3", "val", "easy", "7%"),
        ("u4", "val", "hard", "nopage"), ("t1", "test", "hard", "SECRET TEST ANSWER")]


def _upstream(tmp_path, monkeypatch):
    up = tmp_path / "up"
    up.mkdir()
    with (up / "officeqa_full.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["uid", "question", "answer", "source_docs", "source_files",
                                                    "difficulty"])
        writer.writeheader()
        for uid, part, level, gold in ROWS:
            writer.writerow({"uid": uid, "question": f"What is the value for {uid}? SECRET TEST QUESTION" if part == "test"
                             else f"What is the value for {uid}?", "answer": gold,
                             "source_docs": f"https://example.org/doc?page={len(uid)}", "source_files": f"{uid}.txt",
                             "difficulty": level})
    for part in ("train", "val", "test"):
        d = tmp_path / "ids" / part
        d.mkdir(parents=True)
        (d / "items.json").write_text(json.dumps([{"uid": u, "id": u} for u, p, _, _ in ROWS if p == part]),
                                      encoding="utf-8")
    (tmp_path / "ids/split_manifest.json").write_text(json.dumps({"benchmark": "officeqa"}), encoding="utf-8")
    page = tmp_path / "page.json"
    page.write_text("{}", encoding="utf-8")
    from skillopt.envs.officeqa import tool_runtime

    monkeypatch.setattr(tool_runtime, "build_oracle_parsed_pages_context",
                        lambda files, docs, roots, **kw: "" if "u4" in files else
                        f"{kw['evidence_note']}\n\n### {files} page 1\nTABLE value={files}")
    monkeypatch.setattr(tool_runtime, "_iter_oracle_refs", lambda files, docs: [(files, 1, docs)])
    monkeypatch.setattr(tool_runtime, "_locate_parsed_json", lambda source, roots: page)
    return up, tmp_path / "ids"


class Client(Base):
    """Answers with the gold of the item named in the context iff the system message carries the marker."""
    form = "<answer>%s</answer>"

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        receipt = super().call(system, '{"choices": "A. right option\\n\\nB. wrong one"}', kind, key, max_tokens, repeat)
        if kind.endswith("zero-shot") or self.truncate_first and "length-recovery" not in key:
            return receipt
        uid = json.loads(user)["context"].rsplit("value=", 1)[1].split(".txt")[0]
        gold = {u: g for u, _, _, g in ROWS}[uid]
        said = {"1,234.5": "$1234.5 million"}.get(gold, gold) if "MARKER" in system else "0"
        return {**receipt, "response": "work " + self.form % said}


def _prepared(tmp_path, monkeypatch):
    _study(tmp_path, monkeypatch)
    up, ids = _upstream(tmp_path, monkeypatch)
    (tmp_path / "good.md").write_text("MARKER: read the table.\n", encoding="utf-8")
    return pilot.prepare(str(tmp_path / "study"), str(tmp_path), str(up), str(ids), str(tmp_path / "p"),
                         ["empty=none", "good=f:" + str(tmp_path / "good.md")], revision="r" * 40)


def test_only_train_and_validation_items_are_read_out(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="tenth"):  # one of four items has no parsed page
        _prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(pilot, "require", lambda ok, message: None if ok or "tenth" in message else
                        (_ for _ in ()).throw(ValueError(message)))
    record = pilot.prepare(str(tmp_path / "study"), str(tmp_path), str(tmp_path / "up"), str(tmp_path / "ids"),
                           str(tmp_path / "q"), ["empty=none", "good=f:" + str(tmp_path / "good.md")],
                           revision="r" * 40)
    assert record["items"] == 3 and record["dropped_without_parsed_page"] == ["u4"] and record["parts"] == ["train", "val"]
    text = (tmp_path / "q/items.json").read_text(encoding="utf-8")
    assert "SECRET TEST" not in text and '"t1"' not in text  # the paper's test part never leaves the question file
    items = read_json(tmp_path / "q/items.json", sealed=True)["items"]
    assert [i["id"] for i in items] == ["u1", "u2", "u3"] and set(items[0]["public"]) == {"question", "context"}
    assert items[0]["public"]["context"].startswith(pilot.EVIDENCE_NOTE) and items[0]["private"] == {"answer": "1,234.5"}
    assert record["source"]["parsed_page_files"] == 1 and record["variant"] == "one_call_oracle_parsed_pages"


def _three(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "require", lambda ok, message: None if ok or "tenth" in message else
                        (_ for _ in ()).throw(ValueError(message)))
    return _prepared(tmp_path, monkeypatch)


def test_the_original_scorer_reads_the_last_answer_tag(tmp_path, monkeypatch):
    assert pilot.answer("x <answer> 12 </answer> y <answer>13</answer>") == "13"
    assert pilot.answer("the answer is 13") is None and pilot.answer("<answer>  </answer>") is None
    record = _three(tmp_path, monkeypatch)
    client = Client()
    result = pilot.run(str(tmp_path / "p"), fixture_api=client)
    assert result["status"] == "completed" and result["items"] == 3 and result["costs_complete"] is True
    assert result["arms"]["good"] == {"pass": 3, "fail": 0, "unknown": 0, "not_run": 0, "invalid_format": 0}
    assert result["arms"]["empty"]["fail"] == 3  # "$1234.5 million" equals "1,234.5" after the scorer's normalisation
    assert all(kind == pilot.KIND and cap == record["solver_max_tokens"] for kind, _, cap in client.calls)
    value = pilot.report(str(tmp_path / "p"), ["good-empty"])
    assert "chance" not in value and value["contrasts"]["good-empty"]["estimate"] == 1.0
    assert value["by_difficulty"] == {"easy": {"items": 2, "empty": {"pass": 0, "known": 2}, "good": {"pass": 2, "known": 2}},
                                      "hard": {"items": 1, "empty": {"pass": 0, "known": 1}, "good": {"pass": 1, "known": 1}}}
    assert pilot.run(str(tmp_path / "p"), fixture_api=client) == result and len(client.calls) == 6


def test_a_reply_without_a_tag_is_wrong_and_a_changed_tool_refuses_to_run(tmp_path, monkeypatch):
    _three(tmp_path, monkeypatch)

    class Untagged(Client):
        form = "the value is %s"

    result = pilot.run(str(tmp_path / "p"), fixture_api=Untagged())
    assert result["arms"]["good"]["fail"] == 3 and result["arms"]["good"]["invalid_format"] == 3
    _study(tmp_path / "second", monkeypatch)
    record = pilot.prepare(str(tmp_path / "second/study"), str(tmp_path), str(tmp_path / "up"), str(tmp_path / "ids"),
                           str(tmp_path / "q"), ["empty=none", "good=f:" + str(tmp_path / "good.md")], revision="r" * 40)
    monkeypatch.setattr(pilot.base, "_sha", lambda path: "0" * 64)
    with pytest.raises(ValueError, match="Tool changed"):
        pilot.run(str(tmp_path / "q"), fixture_api=Client())
    assert record["implementation_sha256"]["scripts/pilot_livemath_headroom.py"] != "0" * 64


def test_the_zero_shot_instruction_uses_the_officeqa_task_card(tmp_path, monkeypatch):
    _study(tmp_path, monkeypatch)
    client = Client()
    result = pilot.zeroshot(str(tmp_path / "study"), str(tmp_path), str(tmp_path / "z"), fixture_api=client)
    assert result["status"] == "completed" and len(client.calls) == 1 and client.calls[0][0].endswith("zero-shot")
    record = read_json(tmp_path / "z/generation.json", sealed=True)
    assert "Treasury Bulletin" in record["user"] and "no numeric tolerance" in record["user"].lower()
