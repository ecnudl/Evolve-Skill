"""Generator v2 (scripts/generate_officeqa_diagnostic_tasks.py, learn side; scripts/generate_officeqa_transfer_tasks.py,
held-out side, page-only): v1's sound generation plus a registered category per item, restricted to one side of an L/H
split, and the host-only derivations of the accepted items."""
import json

import pytest

from scripts import generate_officeqa_diagnostic_tasks as gen2
from scripts import generate_officeqa_tasks as v1
from scripts import generate_officeqa_transfer_tasks as gent
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from tests.test_continual_learning_officeqa_generated_validation import Writer, _study


class CategoryWriter(Writer):
    """v1's fixture writer and reviewer; every proposal gets a category -- the first 'percent', the second an
    unregistered category (filtered), the rest 'precision'. Records every payload it was shown."""

    def __init__(self):
        super().__init__()
        self.payloads = []

    def _verifier(self, payload):
        self.payloads.append(payload)
        if "computed_answer" in payload and "source_question" not in payload:  # the page-only reviewer
            uid = int(payload["question"].split("item u", 1)[1].split(":")[0].split(",")[0])
            keep = payload["computed_answer"] == "20.21" or uid % 2 == 0
            return {"grounded": True, "computation": True, "unique": keep, "format": True, "needs_pages": True,
                    "reason": "fixture"}
        reply = super()._verifier(payload)
        if "pages" in payload and "computed_answer" not in payload:
            for i, task in enumerate(reply["tasks"]):
                task["category"] = "percent" if i == 0 else "chart_reading" if i == 1 else "precision"
        return reply


def _cut(tmp_path, where):
    """An L/H split of the fixture study's training draw (seed 3): the first four drawn tasks learn, the rest held out."""
    from scripts import run_fivebench_g_stage as tool

    split = read_json(where[1], sealed=True)
    dev = read_json(tmp_path / "study" / "dev_panel.json")
    train, _ = tool.train_tasks(dev, split, "officeqa", 3)
    ids = sorted(t["task_id"] for t in train)
    record = seal({"learn_tasks": ids[:4], "held_out_tasks": ids[4:], "manifest_hash": "m" * 64})
    write_json(tmp_path / "lh.json", record)
    return str(tmp_path / "lh.json"), ids


def test_the_learn_side_shows_its_source_questions_and_carries_categories(tmp_path, monkeypatch):
    assert gen2.WRITER.count("\"category\"") == 2 and all(c in gen2.WRITER for c in gen2.CATEGORIES)
    source = {"question": "q", "context": "c"}
    assert gen2.admit({"question": "x"}, source, set())[0] == "category_missing_or_unknown"
    assert gen2.admit({"question": "x", "category": "chart_reading"}, source, set())[0] == "category_missing_or_unknown"
    assert gen2.admit({"question": "x", "category": "percent"}, source, set())[0] == "malformed"
    where = _study(tmp_path, monkeypatch)
    lh, ids = _cut(tmp_path, where)
    record = gen2.prepare(*where, str(tmp_path / "g"), str(tmp_path), seed=3, lh_split=lh)
    assert record["version"] == gen2.VERSION and record["side"] == "learn" and record["source_question_shown"] is True
    assert record["source_tasks"] == 4 and v1.VERSION == "generated-officeqa-tasks-v1" and v1.WRITER != gen2.WRITER
    api = CategoryWriter()
    result = gen2.run(str(tmp_path / "g"), fixture_api=api)
    assert result["status"] == "completed" and result["source_tasks"] == 4
    path, _, _ = gen2.check(str(tmp_path / "g"))
    items = json.loads(path.read_text(encoding="utf-8"))
    assert items and all(set(i) == {"id", "question", "context", "answer", "category"} for i in items)
    writes = [p for p in api.payloads if "computed_answer" not in p]
    assert writes and all("source_question" in p for p in writes)
    derivations = gen2.derivations(str(tmp_path / "g"))
    assert set(derivations) == {i["id"] for i in items}
    for item in items:
        d = derivations[item["id"]]
        values = {f["name"]: v1.figure(f["value"]) for f in d["figures"]}
        assert d["answer"] == item["answer"] == v1.rounded(v1.evaluate(d["expression"], values), d["decimals"])
    with pytest.raises(ValueError):
        v1.check(str(tmp_path / "g"))


def test_the_held_out_side_is_page_only(tmp_path, monkeypatch):
    assert "source question" not in gent.WRITER and "source question" not in gent.REVIEWER and "distinct" not in gent.VERDICTS
    where = _study(tmp_path, monkeypatch)
    lh, ids = _cut(tmp_path, where)
    record = gent.prepare(*where, str(tmp_path / "t"), str(tmp_path), seed=3, lh_split=lh)
    assert record["side"] == "held_out" and record["source_question_shown"] is False and record["source_tasks"] == len(ids) - 4
    assert record["tool_sha256"] == gent.tool_sha256() != gen2.tool_sha256()
    api = CategoryWriter()
    result = gent.run(str(tmp_path / "t"), fixture_api=api)
    assert result["status"] == "completed"
    held = {t["public"]["question"] for t in read_json(tmp_path / "t/panel.json")["tasks"]}
    assert held and all(set(p) == {"pages"} for p in api.payloads if "computed_answer" not in p)
    assert all("source_question" not in p for p in api.payloads)
    assert not any(q in json.dumps(p) for q in held for p in api.payloads)  # no held-out question in any prompt
    assert set(gent.derivations(str(tmp_path / "t"))) == {i["id"] for i in json.loads(gent.check(str(tmp_path / "t"))[0].read_text())}
    # the split must partition this draw
    bad = seal({"learn_tasks": ids[:3], "held_out_tasks": ids[4:], "manifest_hash": "m" * 64})
    write_json(tmp_path / "bad.json", bad)
    with pytest.raises(ValueError):
        gent.prepare(*where, str(tmp_path / "t2"), str(tmp_path), seed=3, lh_split=str(tmp_path / "bad.json"))
