"""Illustrative numbers only; these are software tests, not model experiments."""

import json

import pytest

from scripts.summarize_domain_portfolio import main, summarize_file


def input_file(tmp_path):
    path = tmp_path / "input.json"
    path.write_text(json.dumps({
        "metadata": {"kind": "illustrative_example"},
        "scores": {"a": {"baseline": .6, "reference": .8, "candidate": .78}},
        "source_domains": ["a"],
    }))
    return path


def test_explicit_illustration_not_evidence(tmp_path):
    report = summarize_file(input_file(tmp_path))
    assert report["model_calls"] == 0
    assert report["illustration_is_not_experimental_evidence"] is True
    assert report["metrics"]["macro_scores"]["candidate"] == .78
    assert report["metrics"]["source_gain_retention"]["a"]["retention"] == pytest.approx(.9)


def test_cli_new_output_and_immutable_input(tmp_path):
    source = input_file(tmp_path)
    original = source.read_bytes()
    output = tmp_path / "report.json"
    assert main(["--input", str(source), "--output", str(output)]) == 0
    assert source.read_bytes() == original
    written = output.read_bytes()
    with pytest.raises(SystemExit):
        main(["--input", str(source), "--output", str(output)])
    assert output.read_bytes() == written


def test_cannot_overwrite_input(tmp_path):
    source = input_file(tmp_path)
    before = source.read_bytes()
    with pytest.raises(SystemExit):
        main(["--input", str(source), "--output", str(source)])
    assert source.read_bytes() == before


def test_duplicate_domain_rejected(tmp_path):
    source = tmp_path / "duplicates.json"
    source.write_text('{"metadata":{"kind":"illustrative_example"},"scores":{"a":{},"a":{}}}')
    with pytest.raises(ValueError, match="Duplicate"):
        summarize_file(source)


@pytest.mark.parametrize("kind", [None, "", "confirmed_safe", 1])
def test_missing_or_unrecognized_kind(tmp_path, kind):
    source = input_file(tmp_path)
    payload = json.loads(source.read_text())
    payload["metadata"]["kind"] = kind
    source.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="metadata.kind"):
        summarize_file(source)


def test_unknown_input_fields_rejected(tmp_path):
    source = input_file(tmp_path)
    payload = json.loads(source.read_text())
    payload["replace_existing_scores"] = True
    source.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Input must"):
        summarize_file(source)
