import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v5 import adapters as a
from skillopt.coevolution_v5.core import feedback_packet, initial_rubric, verify
from skillopt.validator_pilot.api import digest


def task_for(split="dev"):
    files = {"api.py": "import calculation\ndef solve(data):\n    return calculation.double(data['x'])\n",
             "calculation.py": "def double(value):\n    return value\n"}
    reference = {**files, "calculation.py": "def double(value):\n    return value * 2\n"}

    def case(label, value, public):
        return {"label": label, "input": {"x": value}, "expected": value * 2, "exception": None,
                "public": public, "dimension": "requested_behavior" if public else "preserved_behavior"}

    return RepoTask("v5-unit", split, "unit", "unit", "Return twice x without changing input.", files, reference,
                    ["calculation.py"], {"type": "object", "properties": {"x": {"type": "integer"}},
                                         "required": ["x"], "additionalProperties": False},
                    [case("public", 2, True)], [case("PRIVATE_SECRET_LABEL", 617, False)],
                    {"private_metadata": "DO_NOT_SEND"})


def rubric():
    return initial_rubric()


def qa_for(split="dev"):
    return {"id": "qa-unit", "cluster_id": "qa-family", "question": "Which city is the capital of France?",
            "contexts": ["Paris is the capital of France.", "Rome is the capital of Italy."],
            "answers": ["Paris", "The city of Paris"], "split": split, "secret_metadata": "DO_NOT_SEND"}


def delivered(source="def double(value):\n    return value * 2\n", ending="<<<END FILE>>>\n"):
    return "<<<FILE calculation.py>>>\n" + source + ending


class FakeAPI:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def call(self, system, user, **kwargs):
        self.calls.append({"system": system, "user": user, **kwargs})
        response = self.responses.pop(0)
        return {"request_hash": digest(self.calls[-1]), **(response if isinstance(response, dict)
                else {"ok": True, "response": response})}


@pytest.mark.parametrize("ending", ["<<<END FILE>>>\n", "<<<END FILE>>>", ""])
def test_declared_delimiter_grammar_preserves_exact_source_bytes(ending):
    source = "# precise bytes\ndef double(value):\n    text = 'quote\\\\value'\n    return value * 2\n\n"
    parsed = a.parse_delivery(task_for(), delivered(source, ending))
    assert parsed["calculation.py"] == source
    assert parsed["api.py"] == task_for().files["api.py"]


def test_missing_eof_newline_is_not_added():
    source = "def double(value):\n    return value * 2"
    assert a.parse_delivery(task_for(), delivered(source, ""))["calculation.py"] == source


def test_implicit_next_header_preserves_each_source():
    task = replace(task_for(), editable_paths=["api.py", "calculation.py"])
    raw = delivered(ending="") + "<<<FILE api.py>>>\n" + task.files["api.py"]
    result = a.parse_delivery(task, raw)
    assert result == task.reference_files


@pytest.mark.parametrize("raw", [
    "", "KEEP", "prose\n" + delivered(), delivered() + "prose",
    "```python\n" + delivered() + "```", delivered() + delivered(),
    "<<<FILE ../calculation.py>>>\nx=1\n", "<<<FILE new.py>>>\nx=1\n",
    "<<<FILE api.py>>>\nx=1\n", "<<<FILE calculation.py>>>\n\n",
    "<<<FILE calculation.py>>> trailing\nx=1\n", delivered("import os\n"),
    delivered("def x(:\n"), delivered() + "<<<END FILE>>>\n",
    delivered("```python\nx=1\n```\n"),
])
def test_invalid_delivery_cannot_relax_ast_or_path_guards(raw):
    with pytest.raises((ValueError, SyntaxError)):
        a.parse_delivery(task_for(), raw)


def test_protected_bytes_checked_even_for_already_parsed_files(monkeypatch):
    task = task_for()
    monkeypatch.setattr(a.executor, "run_payload", lambda _: pytest.fail("invalid artifact executed"))
    rows = a.CodingAdapter(task).evaluate({**task.reference_files, "api.py": "x=1\n"}, rubric(), phase="development")
    assert rows[0]["status"] == "unknown"
    assert rows[0]["details"]["reason"] == "delivery"


def test_real_coding_contract_and_probe_use_frozen_os_sandbox():
    task = task_for()
    rows = a.CodingAdapter(task).evaluate(task.reference_files, rubric(), phase="development", extra_inputs=[{"x": 3}])
    assert [r["status"] for r in rows] == ["pass", "pass", "not_applicable", "not_applicable"]
    assert all(r["gate_eligible"] for r in rows[:2])
    assert rows[0]["details"]["total_tests"] == 4
    assert rows[1]["details"]["receipts"][0]["actual"]["input_unchanged"] is True
    assert a.executor.run_payload.__module__ == "skillopt.coevolution_v3.executor"
    for row in rows:
        verify(row, "receipt_hash")


def test_real_wrong_coding_artifact_produces_replayable_counterexample():
    task = task_for()
    rows = a.CodingAdapter(task).evaluate(task.files, rubric(), phase="development", extra_inputs=[{"x": 3}])
    assert rows[0]["status"] == rows[1]["status"] == "fail"
    receipt = rows[1]["details"]["receipts"][0]
    assert receipt["reference"]["value"] == 6 and receipt["actual"]["value"] == 3
    packet = feedback_packet(task_id=task.id, cluster_id=task.cluster_id, domain="coding", assessments=rows,
                             artifact=task.files, contract=task.prompt)
    assert packet["facts"]


def test_rubric_domain_mismatch_does_not_execute(monkeypatch):
    monkeypatch.setattr(a.executor, "run_payload", lambda _: pytest.fail("N/A check executed"))
    rows = a.QAAdapter(qa_for()).evaluate("Paris", rubric(), phase="development")
    assert rows[0]["status"] == rows[1]["status"] == "not_applicable"


@pytest.mark.parametrize("inputs", [[], None, [{"x": 2}] * 5, [{"x": True}], [{"bad": 2}], [{"x": float("nan")} ]])
def test_probe_requires_bounded_legal_input(inputs):
    task = task_for()
    row = a.CodingAdapter(task).evaluate(task.files, rubric(), phase="development", extra_inputs=inputs)[1]
    assert row["status"] == "unknown" and not row["gate_eligible"]


def test_disputed_reference_is_not_reported_as_semantic_failure(monkeypatch):
    task = task_for()
    monkeypatch.setattr(a.executor, "run_payload", lambda _: pytest.fail("disputed oracle executed"))
    rows = a.CodingAdapter(task).evaluate(task.files, rubric(), phase="development", reference_reviewed=False)
    assert all(row["status"] == "unknown" and not row["verified"] for row in rows[:2])


def test_reference_must_match_fixed_contract():
    task = task_for()
    task = replace(task, reference_files=task.files)
    row = a.CodingAdapter(task).evaluate(task.files, rubric(), phase="development")[0]
    assert row["status"] == "unknown" and row["details"]["reason"] == "reference_dispute_or_unavailable"


def test_empty_fixed_oracle_cannot_vacuously_approve():
    task = replace(task_for(), public_cases=[], private_cases=[])
    row = a.CodingAdapter(task).evaluate(task.reference_files, rubric(), phase="development")[0]
    assert row["status"] == "unknown" and row["details"]["reason"] == "no_fixed_contract_fixtures"


@pytest.mark.parametrize("domain", ["coding", "qa"])
def test_reference_review_flag_cannot_be_truthy_text(domain):
    adapter = a.CodingAdapter(task_for()) if domain == "coding" else a.QAAdapter(qa_for())
    artifact = task_for().files if domain == "coding" else "Paris"
    with pytest.raises(ValueError, match="boolean"):
        adapter.evaluate(artifact, rubric(), phase="development", reference_reviewed="false")


def test_reference_execution_failure_is_unknown(monkeypatch):
    monkeypatch.setattr(a.executor, "run_payload", lambda _: (1, "", "sandbox unavailable"))
    rows = a.CodingAdapter(task_for()).evaluate(task_for().files, rubric(), phase="development")
    assert all(row["status"] == "unknown" and not row["verified"] for row in rows[:2])


@pytest.mark.parametrize("split,phase", [("holdout", "development"), ("calibration", "learn0"),
                                         ("test", "gate"), ("dev", "final"), ("dev", "arbitrary")])
def test_split_provenance_cannot_be_relabelled(split, phase):
    with pytest.raises(ValueError, match="phase"):
        a.CodingAdapter(task_for(split)).evaluate(None, rubric(), phase=phase)
    with pytest.raises(ValueError, match="phase"):
        a.QAAdapter(qa_for(split)).evaluate("Paris", rubric(), phase=phase)


def test_gate_only_exposes_public_fixtures_even_false_override():
    task = task_for("gate")
    row = a.CodingAdapter(task).evaluate(task.files, rubric(), phase="gate0", public_only=False)[0]
    text = json.dumps(row)
    assert "PRIVATE_SECRET_LABEL" not in text and "617" not in text
    assert row["phase"] == "development" and row["details"]["task_split"] == "gate"


def test_promotion_default_does_not_read_hidden_truth_but_can_be_audited_separately():
    task = task_for("calibration")
    files = {**task.files, "calculation.py": "def double(value):\n    return 4\n"}
    adapter = a.CodingAdapter(task)
    public = adapter.evaluate(files, rubric(), phase="promotion")[0]
    truth = adapter.evaluate(files, rubric(), phase="promotion", public_only=False)[0]
    assert public["status"] == "pass" and truth["status"] == "fail"
    assert "PRIVATE_SECRET_LABEL" not in json.dumps(public)


def test_final_assessment_cannot_be_optimizer_feedback():
    task = task_for("holdout")
    rows = a.CodingAdapter(task).evaluate(task.files, rubric(), phase="final")
    assert not any(row["gate_eligible"] for row in rows)
    with pytest.raises(ValueError):
        feedback_packet(task_id=task.id, cluster_id=task.cluster_id, domain="coding", assessments=rows,
                        artifact=task.files, contract=task.prompt)


def test_coding_solver_fixed_two_calls_public_only_repair_and_keep():
    task = task_for()
    api = FakeAPI([delivered(ending=""), "KEEP"])
    record = a.CodingAdapter(task).solve(api, "Check constraints.", key="test", repeat=2)
    assert record["solver_calls"] == 2 and record["revision_kept"]
    assert record["evaluation"]["total_tests"] == 2 and record["evaluation"]["hard"] is True
    for call in api.calls:
        for secret in ("PRIVATE_SECRET_LABEL", "617", "DO_NOT_SEND", "reference_files"):
            assert secret not in call["user"]
        assert call["max_tokens"] == a.TARGET_TOKENS
    assert all(len(value) == 64 for value in record["request_hashes"])


def test_failed_generation_can_be_repaired_not_kept():
    api = FakeAPI(["bad", delivered(ending="")])
    assert a.CodingAdapter(task_for()).solve(api, "", key="unit")["format_ok"]
    api = FakeAPI(["bad", "KEEP"])
    record = a.CodingAdapter(task_for()).solve(api, "", key="unit")
    assert not record["format_ok"] and record["evaluation"]["hard"] is None


@pytest.mark.parametrize("domain", ["coding", "qa"])
def test_transport_failure_is_not_semantic_failure_or_silent_retry(domain):
    adapter = a.CodingAdapter(task_for()) if domain == "coding" else a.QAAdapter(qa_for())
    first = delivered() if domain == "coding" else '{"answer":"Paris"}'
    api = FakeAPI([first, {"ok": False, "response": "truncated"}])
    record = adapter.solve(api, "", key="unit")
    assert record["delivery_status"] == "transport_unavailable" and len(api.calls) == 2


def test_qa_public_whitelist_omits_private_fields():
    task = qa_for()
    task["answers"] = ["GOLD_SECRET"]
    public = a.QAAdapter(task).public_task()
    assert set(public) == {"id", "question", "contexts"}
    assert "GOLD_SECRET" not in json.dumps(public) and "DO_NOT_SEND" not in json.dumps(public)
    assert public["contexts"][0]["context_id"] == 0


def test_grounded_wrong_answer_does_not_pass_native_oracle():
    answer = {"answer": "Rome", "citations": [{"context_id": 1, "quote": "Rome is the capital of Italy."}]}
    rows = a.QAAdapter(qa_for()).evaluate(answer, rubric(), phase="development")
    assert rows[2]["status"] == "fail" and rows[2]["gate_eligible"]
    assert rows[3]["status"] == "pass" and not rows[3]["gate_eligible"]
    assert rows[3]["details"]["entailment"] == "unknown"
    assert rows[2]["details"]["scores"]["em"] == 0
    assert rows[2]["details"]["expected_answers"] == qa_for()["answers"]


@pytest.mark.parametrize("split,phase", [("calibration", "promotion"), ("holdout", "final"), ("audit", "audit")])
def test_qa_expected_answers_appear_only_in_development_feedback(split, phase):
    rows = a.QAAdapter(qa_for(split)).evaluate("Rome", rubric(), phase=phase)
    assert "expected_answers" not in rows[2]["details"]


def test_quote_match_does_not_establish_entailment_or_authorize_approval():
    answer = {"answer": "Paris", "citations": [{"context_id": 1, "quote": "Italy"}]}
    rows = a.QAAdapter(qa_for()).evaluate(answer, rubric(), phase="development")
    assert rows[2]["status"] == "pass"
    assert rows[3]["status"] == "pass" and not rows[3]["gate_eligible"]
    assert rows[3]["details"]["citations"][0]["entailment"] == "unknown"


@pytest.mark.parametrize("citations,status", [([], "unknown"), ([{"context_id": -1, "quote": "Paris"}], "fail"),
                                             ([{"context_id": 0, "quote": "fabricated"}], "fail")])
def test_missing_or_unmatched_citation_is_not_approval(citations, status):
    rows = a.QAAdapter(qa_for()).evaluate({"answer": "Paris", "citations": citations}, rubric(), phase="development")
    assert rows[3]["status"] == status and not rows[3]["gate_eligible"]


def test_qa_unreviewed_gold_is_unknown():
    row = a.QAAdapter(qa_for()).evaluate("Rome", rubric(), phase="development", reference_reviewed=False)[2]
    assert row["status"] == "unknown" and not row["verified"]


def test_empty_gold_is_not_an_oracle():
    task = qa_for()
    task["answers"] = [""]
    with pytest.raises(ValueError, match="nonempty"):
        a.QAAdapter(task)


def test_original_searchqa_normalization_and_f1_retained():
    task = qa_for()
    task["answers"] = ["the city of Paris"]
    row = a.QAAdapter(task).evaluate("City of Paris!", rubric(), phase="development")[2]
    assert row["details"]["scores"] == {"em": 1.0, "f1": 1.0, "sub_em": 1.0}


def test_qa_solver_never_receives_gold_or_correctness_feedback():
    task = qa_for()
    task["answers"] = ["GOLD_SECRET"]
    api = FakeAPI(['{"answer":"Rome","citations":[{"context_id":1,"quote":"Rome"}]}', "KEEP"])
    record = a.QAAdapter(task).solve(api, "Verify quotes.", key="unit")
    assert record["answer"]["answer"] == "Rome" and record["revision_kept"]
    assert len(api.calls) == 2
    for call in api.calls:
        assert "GOLD_SECRET" not in call["user"] and "DO_NOT_SEND" not in call["user"]
    feedback = json.loads(api.calls[1]["user"])["public_feedback"]
    assert feedback["correctness"] == "not_evaluated" and feedback["entailment"] == "unknown"
    assert "scores" not in feedback


@pytest.mark.parametrize("raw", ["Paris", '```json\n{"answer":"Paris"}\n```', '{"answer":"Paris","answer":"Rome"}',
                                 '{"answer":null}', '{"answer":"Paris","verdict":true}',
                                 '{"answer":"Paris","citations":[{"context_id":true,"quote":"Paris"}]}',
                                 '{"answer":"Paris","citations":[{"context_id":0,"quote":""}]}'])
def test_qa_delivery_schema_rejects_ambiguity(raw):
    with pytest.raises((ValueError, TypeError)):
        a.parse_answer(raw)


def test_unsupported_check_cannot_invent_evidence():
    r = deepcopy(rubric())
    r["checks"] = [{"id": "soft_model_says_correct", "domains": ["qa"]}]
    with pytest.raises(ValueError):
        a.QAAdapter(qa_for()).evaluate("Paris", r, phase="development")


def test_deterministic_call_sharing_binds_task_skill_and_repeat():
    keys = []
    for skill, repeat in [("", 0), ("", 0), ("new", 0), ("", 1)]:
        api = FakeAPI(['{"answer":"Paris"}', "KEEP"])
        a.QAAdapter(qa_for()).solve(api, skill, key="shared", repeat=repeat)
        keys.append(tuple(row["key"] for row in api.calls))
    assert keys[0] == keys[1] and len(set(keys)) == 3
