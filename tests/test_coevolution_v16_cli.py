from pathlib import Path

import pytest

from scripts import coevolution_v16 as cli
from skillopt.coevolution_v16 import reporting


@pytest.mark.parametrize("target", ["coevolution-v15-protocol.md", "coevolution-v16-protocol.md",
                                    "coevolution-v14-protocol.md", "results.json"])
def test_reports_cannot_overwrite_frozen_protocols_or_non_markdown(tmp_path, monkeypatch, target):
    monkeypatch.setattr(cli, "REPO", tmp_path)
    with pytest.raises(ValueError, match="Derived report"):
        cli.write_report(tmp_path / "run", tmp_path / "docs" / target)


def test_reports_require_inside_docs_and_non_symlink(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO", tmp_path)
    with pytest.raises(ValueError, match="Derived report"):
        cli.write_report(tmp_path / "run", tmp_path / "result.md")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/result.md").symlink_to(tmp_path / "target.md")
    with pytest.raises(ValueError, match="Derived report"):
        cli.write_report(tmp_path / "run", tmp_path / "docs/result.md")


def test_only_derived_report_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO", tmp_path)
    monkeypatch.setattr(reporting, "render", lambda root: "audited derived report")
    (tmp_path / "docs").mkdir()
    path = cli.write_report(tmp_path / "run", tmp_path / "docs/results.md")
    assert Path(path).read_text() == "audited derived report"
