"""The LiveMathematicianBench headroom pilot: eligibility, frozen option order, sealed outcomes, no resume."""
import json

import pytest

from scripts import pilot_livemath_headroom as pilot
from skillopt.continual_eval.core import read_json
from tests.test_continual_learning_generated_validation import _study


def _upstream(tmp_path, months=("202602", "202603", "202604"), per=5):
    for month in months:
        d = tmp_path / "up/data" / month
        d.mkdir(parents=True)
        rows = [{"no": n, "month": month, "paper_link": f"https://example.org/{month}/{n}", "theorem": "SECRET THEOREM",
                 "sketch": "SECRET SKETCH", "theorem_type": ["implication"],
                 "mcq": {"question": f"Which statement holds for object {month}-{n}?",
                         "choices": [{"label": "B", "text": f"wrong one {n}"}, {"label": "C", "text": f"wrong two {n}"},
                                     {"label": "D", "text": f"wrong three {n}"}, {"label": "E", "text": f"wrong four {n}"}],
                         "correct_choice": {"label": "A", "text": f"right option {n}"}, "meta": {},
                         "sketch_usage_meta": {}}} for n in range(1, per + 1)]
        (d / f"qa_{month}_final.json").write_text(json.dumps(rows), encoding="utf-8")
    for part, month in (("train", "202602"), ("val", "202602"), ("test", "202602")):
        d = tmp_path / "ids" / part
        d.mkdir(parents=True)
        (d / "items.json").write_text(json.dumps([{"id": "x", "month": month, "no": 1, "paper_link": "p",
                                                    "source_file": "f"}]), encoding="utf-8")
    (tmp_path / "ids/split_manifest.json").write_text(json.dumps({"benchmark": "livemathematicianbench"}), encoding="utf-8")
    return tmp_path / "up", tmp_path / "ids"


class Client:
    """Answers with the right option's letter iff the system message carries the marker; counts its calls."""
    service = {"fixture": True}

    def __init__(self, fail=False, truncate_first=False):
        self.calls, self.fail, self.truncate_first = [], fail, truncate_first

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        self.calls.append((kind, key, max_tokens))
        if self.fail:
            raise RuntimeError("provider text that must not be recorded")
        base = {"ok": True, "usage": {"prompt_tokens": 5, "completion_tokens": 2}, "http_attempt_count": 1,
                "request_hash": "h" + key,
                "request": {"service": {}}, "status": 200, "stream_complete": True, "returned_model": "glm-5.3"}
        if kind.endswith("zero-shot"):
            return {**base, "response": "- Read every option.\n- Answer with one letter.", "finish_reason": "stop"}
        if self.truncate_first and "length-recovery" not in key:
            return {**base, "ok": False, "response": "", "finish_reason": "length", "error_type": "truncated_content"}
        lines = json.loads(user)["choices"].split("\n\n")
        want = "right option" if "MARKER" in system else "wrong one"
        return {**base, "response": "reasoning <answer>%s</answer>" % next(x[0] for x in lines if want in x),
                "finish_reason": "stop"}


def _prepared(tmp_path, monkeypatch, **more):
    _study(tmp_path, monkeypatch)
    up, ids = _upstream(tmp_path)
    (tmp_path / "good.md").write_text("MARKER: prefer the right option.\n", encoding="utf-8")
    return pilot.prepare(str(tmp_path / "study"), str(tmp_path), str(up), str(ids), str(tmp_path / "p"),
                         ["empty=none", "good=f:" + str(tmp_path / "good.md")], revision="r" * 40, per_month=3,
                         seed=7, **more)


def test_only_months_outside_the_published_split_and_a_frozen_option_order(tmp_path, monkeypatch):
    record = _prepared(tmp_path, monkeypatch)
    assert record["excluded_months"] == ["202602"] and record["items"] == 6
    assert sorted(record["source"]["files"]) == ["data/202603/qa_202603_final.json", "data/202604/qa_202604_final.json"]
    items = read_json(tmp_path / "p/items.json", sealed=True)["items"]
    assert all(i["id"].split(":")[0] in {"202603", "202604"} for i in items)
    text = json.dumps(items)
    assert "SECRET" not in text and "paper_link" not in text  # theorem, sketch and source stay in the source files
    for item in items:
        lines = item["public"]["choices"].split("\n\n")
        assert [x[:2] for x in lines] == ["A.", "B.", "C.", "D.", "E."]  # the correct option is one of the five
        assert "right option" in lines["ABCDE".index(item["private"]["answer"])]
        assert sum("right option" in line for line in lines) == 1
    assert len({i["private"]["answer"] for i in items}) > 1  # not the upstream position of the correct option
    again, _ = pilot.draw(tmp_path / "up", {"202602"}, 3, 7)
    assert again == items and pilot.draw(tmp_path / "up", {"202602"}, 3, 8)[0] != items
    with pytest.raises(ValueError, match="new directory"):
        pilot.prepare(str(tmp_path / "study"), str(tmp_path), str(tmp_path / "up"), str(tmp_path / "ids"),
                      str(tmp_path / "p"), ["a=none", "b=none"], revision="r" * 40, per_month=3, seed=7)


def test_every_arm_solves_every_item_once_and_the_report_pairs_them(tmp_path, monkeypatch):
    record = _prepared(tmp_path, monkeypatch)
    client = Client()
    result = pilot.run(str(tmp_path / "p"), fixture_api=client)
    assert result["status"] == "completed" and result["items"] == 6
    assert result["arms"]["empty"] == {"pass": 0, "fail": 6, "unknown": 0, "not_run": 0, "invalid_format": 0}
    assert result["arms"]["good"] == {"pass": 6, "fail": 0, "unknown": 0, "not_run": 0, "invalid_format": 0}
    assert len(client.calls) == 12 and len({k for _, k, _ in client.calls}) == 12
    assert all(kind == pilot.KIND and cap == record["solver_max_tokens"] for kind, _, cap in client.calls)
    assert result["costs"] == {"calls": 12, "http_attempts": 12, "failed_attempts": 0, "tokens_known_subtotal": 84,
                               "attempts_without_usage": 0, "unresolved_calls": 0, "open_intents": 0}
    assert result["costs_complete"] is True
    assert len(list((tmp_path / "p/intents").glob("*/*.json"))) == 12
    value = pilot.report(str(tmp_path / "p"), ["good-empty"])
    assert value["contrasts"]["good-empty"]["estimate"] == 1.0 and value["arms"]["good"]["skill_bytes"] > 0
    assert value["arms"]["good"]["pass_rate"] == 1.0 and value["arms"]["empty"]["wilson95"][0] == 0.0
    assert value["arms"]["empty"]["wilson95"][1] < 0.5 and value["chance"] == 0.2
    # a second run submits nothing: the sealed result is returned
    assert pilot.run(str(tmp_path / "p"), fixture_api=client) == result and len(client.calls) == 12
    # a tampered call record is refused by the report
    path = next((tmp_path / "p/calls/good").glob("*.json"))
    row = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**row, "status": "fail"}), encoding="utf-8")
    with pytest.raises(ValueError):
        pilot.report(str(tmp_path / "p"))


def test_length_recovery_and_undelivered_calls(tmp_path, monkeypatch):
    record = _prepared(tmp_path, monkeypatch)
    client = Client(truncate_first=True)
    result = pilot.run(str(tmp_path / "p"), fixture_api=client)
    assert result["status"] == "completed" and result["costs"]["calls"] == 24
    assert sorted({cap for _, _, cap in client.calls}) == sorted({record["solver_max_tokens"], record["length_max_tokens"]})
    assert result["arms"]["good"]["pass"] == 6


def test_a_run_that_cannot_reach_the_model_stops_pending_and_is_never_resumed(tmp_path, monkeypatch):
    _prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(pilot, "MAX_UNDELIVERED", 3)
    monkeypatch.setattr(pilot, "CHUNK", 2)
    client = Client(fail=True)
    result = pilot.run(str(tmp_path / "p"), fixture_api=client)
    assert result["status"] == "pending" and result["reason"] == "delivery_margin_exhausted"
    unknown = sum(c["unknown"] for c in result["arms"].values())
    assert unknown == 3 == len(client.calls)  # the bound holds BEFORE submission: never more than the margin
    assert sum(c["not_run"] for c in result["arms"].values()) == 9
    # a call that raised left no receipt: unresolved spending, charged to the margin at three attempts each
    assert result["costs"]["unresolved_calls"] == 3 and result["costs"]["failed_attempts"] == 9
    assert result["costs_complete"] is False
    with pytest.raises(ValueError, match="completed run"):
        pilot.report(str(tmp_path / "p"), ["good-empty"])
    assert pilot.report(str(tmp_path / "p"))["status"] == "pending"
    assert "provider text" not in json.dumps([json.loads(p.read_text()) for p in (tmp_path / "p/calls").glob("*/*.json")])
    assert pilot.run(str(tmp_path / "p"), fixture_api=Client()) == result  # nothing is resumed


def test_an_interrupted_run_is_sealed_pending(tmp_path, monkeypatch):
    record = _prepared(tmp_path, monkeypatch)
    from skillopt.coevolution_v5.core import seal
    from skillopt.continual_eval.core import write_json

    write_json(tmp_path / "p/started.json", seal({"pilot_hash": record["record_hash"]}))
    client = Client()
    result = pilot.run(str(tmp_path / "p"), fixture_api=client)
    assert result["status"] == "pending" and result["reason"] == "interrupted_run_no_automatic_resume"
    assert client.calls == []


def test_the_zero_shot_instruction_is_written_once_from_the_public_task_card(tmp_path, monkeypatch):
    _study(tmp_path, monkeypatch)
    client = Client()
    result = pilot.zeroshot(str(tmp_path / "study"), str(tmp_path), str(tmp_path / "z"), fixture_api=client)
    assert result["status"] == "completed" and result["skill_bytes"] > 0 and len(client.calls) == 1
    record = read_json(tmp_path / "z/generation.json", sealed=True)
    assert record["user"].startswith("Public task card:") and "LiveMathematicianBench" in record["user"]
    assert (tmp_path / "z/skill.md").read_text(encoding="utf-8").startswith("- Read every option.")
    with pytest.raises(ValueError, match="new directory"):
        pilot.zeroshot(str(tmp_path / "study"), str(tmp_path), str(tmp_path / "z"), fixture_api=client)



def test_strict_letter_parsing_and_attempt_level_costs():
    assert pilot.letter("work <answer>b</answer>") == "B" and pilot.letter("<answer> C. </answer>") == "C"
    assert pilot.letter("<answer>A</answer> then <answer>D)</answer>") == "D"  # the last tag counts
    assert pilot.letter("<answer>E</answer>") == "E"
    for bad in ("B", "the answer is B", "<answer>A finite group is cyclic</answer>", "<answer>A or B</answer>",
                "<answer></answer>", "<answer>F</answer>"):
        assert pilot.letter(bad) is None
    receipt = {"ok": True, "http_attempt_count": 3, "usage": {"prompt_tokens": 5, "completion_tokens": 2},
               "attempts": [{"usage": {"prompt_tokens": 5, "completion_tokens": 6}}, {"usage": {}},
                            {"usage": {"prompt_tokens": 5, "completion_tokens": 2}}]}
    assert pilot._usage([receipt]) == {"calls": 1, "http_attempts": 3, "failed_attempts": 2,
                                       "tokens_known_subtotal": 18, "attempts_without_usage": 1, "unresolved_calls": 0}
    assert pilot._usage([receipt], raised=1)["failed_attempts"] == 5 and pilot._usage([], 2)["unresolved_calls"] == 2


def test_a_delivered_reply_in_another_form_is_wrong_and_a_lost_outcome_stays_visible(tmp_path, monkeypatch):
    record = _prepared(tmp_path, monkeypatch)

    class Wordy(Client):
        def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
            receipt = super().call(system, user, kind, key, max_tokens, repeat)
            return {**receipt, "response": "I think the right option is correct."}

    result = pilot.run(str(tmp_path / "p"), fixture_api=Wordy())
    assert result["status"] == "completed" and result["arms"]["good"]["fail"] == 6
    assert result["arms"]["good"]["invalid_format"] == 6
    # a position that was submitted and has no outcome: unknown, counted as an open intent, the result is pending
    _study(tmp_path / "second", monkeypatch)
    again = pilot.prepare(str(tmp_path / "second/study"), str(tmp_path), str(tmp_path / "up"), str(tmp_path / "ids"),
                          str(tmp_path / "q"), ["empty=none", "good=f:" + str(tmp_path / "good.md")],
                          revision="r" * 40, per_month=3, seed=7)
    from skillopt.coevolution_v5.core import seal
    from skillopt.continual_eval.core import write_json

    item = read_json(tmp_path / "q/items.json", sealed=True)["items"][0]["id"]
    (tmp_path / "q/intents/good").mkdir(parents=True)
    write_json(tmp_path / "q/intents/good" / pilot._position(item),
               seal({"pilot_hash": again["record_hash"], "arm": "good", "item": item, "key": "k"}))
    write_json(tmp_path / "q/started.json", seal({"pilot_hash": again["record_hash"]}))
    result = pilot.run(str(tmp_path / "q"), fixture_api=Client())
    assert result["status"] == "pending" and result["costs"]["open_intents"] == 1
    assert result["arms"]["good"]["unknown"] == 1 and result["arms"]["good"]["not_run"] == 5




def test_unresolved_calls_use_up_the_failed_attempt_margin_and_staging_files_are_not_records(tmp_path, monkeypatch):
    record = _prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(pilot, "MAX_FAILED_ATTEMPTS", 12)  # room for two positions at six attempts each
    client = Client(fail=True)
    result = pilot.run(str(tmp_path / "p"), fixture_api=client)
    # 2 positions -> 6 charged attempts -> room for one more -> 9 -> no room: never beyond the margin
    assert result["reason"] == "delivery_margin_exhausted" and len(client.calls) == 3
    assert result["costs"]["failed_attempts"] == 9 <= 12
    # an abandoned staging file of the writer is not a record
    (tmp_path / "p/calls/empty/.pending-x.json").write_text("{", encoding="utf-8")
    (tmp_path / "p/intents/empty/.pending-y.json").write_text("{", encoding="utf-8")
    assert pilot.report(str(tmp_path / "p"))["status"] == "pending"


def test_zero_shot_validation_keeps_what_was_spent(tmp_path, monkeypatch):
    _study(tmp_path, monkeypatch)

    class Huge(Client):
        def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
            return {**super().call(system, user, kind, key, max_tokens, repeat), "response": "x" * 40000}

    result = pilot.zeroshot(str(tmp_path / "study"), str(tmp_path), str(tmp_path / "z"), fixture_api=Huge())
    assert result["status"] == "pending" and result["reason"] == "generated_skill_invalid"
    assert result["calls"] == 1 and result["tokens_known_subtotal"] == 7 and not (tmp_path / "z/skill.md").exists()



def test_rolling_submission_passes_a_slow_position_and_never_exceeds_the_margins(monkeypatch):
    import threading
    import time

    release, order = threading.Event(), []

    def work(job):
        if job == "slow":
            release.wait(5)
        order.append(job)
        if job == "last":
            release.set()
        return {"status": "pass", "failed_attempts": 0}

    monkeypatch.setattr(pilot, "WORKERS", 2)
    assert pilot.execute(["slow", "a", "b", "last"], work) is None
    assert order == ["a", "b", "last", "slow"]  # the others were not held back by the slow one
    # margins count what is in flight at its worst case: room for two positions means two in flight, not eight
    monkeypatch.setattr(pilot, "WORKERS", 8)
    monkeypatch.setattr(pilot, "MAX_FAILED_ATTEMPTS", 12)
    lock, flying, peak = threading.Lock(), [0], [0]

    def counted(job):
        with lock:
            flying[0] += 1
            peak[0] = max(peak[0], flying[0])
        time.sleep(0.02)
        with lock:
            flying[0] -= 1
        return {"status": "pass", "failed_attempts": 0}

    assert pilot.execute(list(range(10)), counted) is None and peak[0] == 2
    # undelivered positions use the margin up: nothing is submitted beyond it, the rest stays unsubmitted
    monkeypatch.setattr(pilot, "MAX_UNDELIVERED", 3)
    monkeypatch.setattr(pilot, "MAX_FAILED_ATTEMPTS", 96)
    seen = []
    lost = lambda job: seen.append(job) or {"status": "unknown", "failed_attempts": 0}  # noqa: E731
    assert pilot.execute(list(range(10)), lost) == "delivery_margin_exhausted" and len(seen) == 3
    # the gate only delays; when it gives up nothing more is submitted and the error surfaces after the flight
    monkeypatch.setattr(pilot, "PROBE_SECONDS", 0.0)
    monkeypatch.setattr(pilot, "MAX_UNDELIVERED", 16)
    asked, done = [], []

    def gate():
        asked.append(1)
        if len(asked) > 2:
            raise RuntimeError("unreachable")

    with pytest.raises(RuntimeError, match="unreachable"):
        pilot.execute(list(range(10)), lambda job: done.append(job) or {"status": "pass", "failed_attempts": 0}, gate)
    assert sorted(done) == [0, 1]
