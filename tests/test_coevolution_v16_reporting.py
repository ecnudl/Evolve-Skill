import hashlib
from pathlib import Path

import pytest

from skillopt.coevolution_v12.study import save
from skillopt.coevolution_v16 import reporting


def protocol(root, **changes):
    row = {"version": "v16-lagged-calibrated-normalized-evidence-v1",
           "research_fix": "normalize_already_truncated_visible_whitespace_before_prompt",
           "task_panel_and_scientific_thresholds_unchanged_from_v15": True,
           "source_hashes": {"skillopt/coevolution_v16/reporting.py":
               hashlib.sha256(Path(reporting.__file__).read_bytes()).hexdigest()}}
    save(root / "protocol.json", {**row, **changes})


def test_wrapper_reuses_original_audit_and_preserves_limitations(tmp_path, monkeypatch):
    protocol(tmp_path)
    calls = []
    def render(root):
        calls.append(root)
        return "# V15 协同进化实验报告\n\n没有验证器被激活。\n"
    monkeypatch.setattr(reporting.legacy, "render", render)
    before = (tmp_path / "protocol.json").read_bytes()
    result = reporting.render(tmp_path)
    assert result.startswith("# V16 协同进化实验报告")
    assert "没有验证器被激活" in result and "旧 V15 失败提案不重判" in result
    assert calls == [tmp_path] and (tmp_path / "protocol.json").read_bytes() == before


@pytest.mark.parametrize("changes", [{"version": "v15"}, {"research_fix": "loose_quote_matching"},
                                    {"task_panel_and_scientific_thresholds_unchanged_from_v15": False}])
def test_other_protocols_fail_closed(tmp_path, changes):
    protocol(tmp_path, **changes)
    with pytest.raises(ValueError, match="registered V16"):
        reporting.render(tmp_path)


def test_report_source_drift_rejected(tmp_path):
    protocol(tmp_path, source_hashes={"skillopt/coevolution_v16/reporting.py": "wrong"})
    with pytest.raises(ValueError, match="source drift"):
        reporting.render(tmp_path)
