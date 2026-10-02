import json

import pytest

from skillopt.continual_eval.cli import main
from skillopt.continual_eval.core import read_json, write_json


def test_searchqa_prepare_does_not_print_answers(tmp_path, capsys):
    source = tmp_path / "source.json"
    target = tmp_path / "panel.json"
    write_json(source, [{"id": "q1", "question": "Question", "context": "Context", "answers": ["PRIVATE_SENTINEL"]}])
    assert main(["prepare", "--benchmark", "searchqa", "--source", str(source), "--revision", "v1-frozen",
                 "--output", str(target)]) == 0
    output = capsys.readouterr().out
    assert "PRIVATE_SENTINEL" not in output
    assert json.loads(output)["tasks"] == 1
    assert read_json(target)["tasks"][0]["partition"] == "development"


def test_bigcode_import_keyword_contract(tmp_path, capsys):
    source = tmp_path / "source.json"
    target = tmp_path / "panel.json"
    write_json(source, [{"task_id": "BigCodeBench/9999", "instruct_prompt": "Public task", "entry_point": "f",
                         "test": "PRIVATE_TEST", "canonical_solution": "PRIVATE_SOLUTION"}])
    main(["prepare", "--benchmark", "bigcodebench", "--source", str(source), "--revision", "v1-frozen",
          "--variant", "instruct", "--output", str(target)])
    assert "PRIVATE" not in capsys.readouterr().out
    assert "canonical_solution" not in target.read_text()


def test_kor_import_keyword_contract(tmp_path, capsys):
    samples, rules, target = [tmp_path / name for name in ("samples.json", "rules.json", "panel.json")]
    write_json(samples, [{"idx": 0, "rule_id": 1, "question": "q", "answer": "PRIVATE"}])
    write_json(rules, [{"idx": 1, "rule_content": "public rule"}])
    main(["prepare", "--benchmark", "korbench", "--source", str(samples), "--rules", str(rules),
          "--category", "logic", "--revision", "v1-frozen", "--output", str(target)])
    assert json.loads(capsys.readouterr().out)["tasks"] == 1


def test_id_manifest_is_not_silently_materialized(tmp_path):
    source = tmp_path / "source.json"
    write_json(source, [{"id": "123"}])
    with pytest.raises(ValueError, match="materialized"):
        main(["prepare", "--benchmark", "searchqa", "--source", str(source), "--revision", "v1-frozen",
              "--output", str(tmp_path / "panel.json")])
