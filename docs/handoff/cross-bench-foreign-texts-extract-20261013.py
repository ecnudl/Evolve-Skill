"""Zero-call helper of queue z3: write three BigCodeBench-trained Skill texts as fixed-text files with provenance.

Sources are sealed records that already exist (nothing is run or changed): the two candidates of the pending
cross-benchmark run cross-bcb-qa-r1 and the Skill adopted by the completed one-step stage bigcodebench-active-pfix1.
"""
import hashlib, json, sys
from pathlib import Path

from skillopt.continual_eval.core import read_json
from skillopt.validator_pilot.api import digest

out = Path(sys.argv[1])
out.mkdir()
cross = Path("/root/fivebench-g-20261013-cross-bcb-qa-r1")
stage = Path("/root/fivebench-g-20261011-bigcodebench-active-pfix1")
rows = []
for name, step in (("xbcb0", 0), ("xbcb1", 1)):
    candidate = read_json(cross / "candidates" / f"{step}.json", sealed=True)
    record = read_json(cross / "steps" / f"{step}.json", sealed=True)
    assert candidate["step"] == step == record["step"]
    text = candidate["skill"]
    assert len(text.encode("utf-8")) == record["candidate_skill_bytes"]
    assert digest(text) == record["candidate_skill_hash"]  # the text is the candidate the gate judged
    rows.append((name, text, {"source": str(cross / "candidates" / f"{step}.json"), "source_record_hash": candidate["record_hash"],
                              "step_record_hash": record["record_hash"], "gate_action_in_pending_run": record["gate_action"]}))
learned = read_json(stage / "learned.json", sealed=True)
assert learned["status"] == "completed" and learned["action"] == "selected_update"
assert hashlib.sha256(learned["skill"].encode("utf-8")).hexdigest() == learned["skill_sha256"]
rows.append(("xbcbp", learned["skill"], {"source": str(stage / "learned.json"), "source_record_hash": learned["record_hash"],
                                         "stage_reason": learned["reason"]}))
provenance = {}
for name, text, info in rows:
    (out / f"{name}.md").write_text(text, encoding="utf-8")
    data = (out / f"{name}.md").read_bytes()
    assert data.decode("utf-8") == text
    provenance[name] = {**info, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
(out / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True), encoding="utf-8")
print(json.dumps({k: {"bytes": v["bytes"], "sha256": v["sha256"][:16]} for k, v in provenance.items()}))
