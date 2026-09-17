"""V16 presentation-aware wrapper around the unchanged V15 evidence audit."""

from __future__ import annotations

import hashlib
from pathlib import Path

from skillopt.coevolution_v15 import reporting as legacy

VERSION = "v16-normalized-presentation-report-v1"


def render(root) -> str:
    root = Path(root).absolute()
    protocol = legacy._read(root / "protocol.json")
    legacy._require(protocol.get("version") == "v16-lagged-calibrated-normalized-evidence-v1"
                    and protocol.get("research_fix") == "normalize_already_truncated_visible_whitespace_before_prompt"
                    and protocol.get("task_panel_and_scientific_thresholds_unchanged_from_v15") is True,
                    "Report is only for the registered V16 presentation repair")
    own_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    legacy._require(protocol["source_hashes"].get("skillopt/coevolution_v16/reporting.py") == own_hash,
                    "V16 report source drift")
    # The complete V15 audit remains applicable: statistics, oracle, task splits,
    # checkpoints, aliases, control calibration and intervention are unchanged.
    report = legacy.render(root).replace("# V15 协同进化实验报告", "# V16 协同进化实验报告", 1)
    note = ("\n\nV16 仅修复 Research 文档展示：对原已截断摘录规范化空白，并保存原文、展示文本及各自哈希；"
            "仍严格核验模型实际看到的精确引文，不放宽引用规则。任务、阈值、共同 Skill 更新器、"
            "求解器和统计均沿用 V15。旧 V15 失败提案不重判，本次不是独立公开 benchmark。\n")
    title, remainder = report.split("\n", 1)
    return title + note + remainder + f"\nV16 展示修复报告版本：`{VERSION}`。\n"
