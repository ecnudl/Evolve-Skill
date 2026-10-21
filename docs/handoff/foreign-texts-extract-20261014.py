"""Zero-call: write the learned Skill texts used by the cross-dataset evaluation of 2026-10-14 as files, each
checked against the hash its sealed record carries. Usage: extract.py <output directory> (must not exist)."""
import hashlib, os, sys
from skillopt.continual_eval.core import read_json  # sealed=True: a record whose hash does not match its content is refused
from skillopt.validator_pilot.api import digest

ONE_STEP = {"oq_z41": "/root/fivebench-g-20261013-officeqa-oq-z41", "oq_e41": "/root/fivebench-g-20261013-officeqa-oq-e41",
            "lm_z41": "/root/fivebench-g-20261013-livemath-lm-z41", "lm_e41": "/root/fivebench-g-20261013-livemath-lm-e41",
            "qa_v9": "/root/fivebench-g-20261006-searchqa-chain-skillopt-v9c"}
CANDIDATE = ("e41s2", "/root/fivebench-g-20261013-livemath-lm-v9-e41/learning", 2)
out = sys.argv[1]
os.makedirs(out, mode=0o700)
for name, stage in ONE_STEP.items():
    learned = read_json(stage + "/learned.json", sealed=True)
    text = learned["skill"]
    if not (learned["status"] == "completed" and learned["action"] == "selected_update" and text
            and hashlib.sha256(text.encode()).hexdigest() == learned["skill_sha256"]):
        raise SystemExit("%s: not a completed stage with an accepted Skill matching its recorded hash" % name)
    with open(os.path.join(out, name + ".md"), "x", encoding="utf-8") as handle:
        handle.write(text)
    print(name, "bytes", len(text.encode()), "sha256", learned["skill_sha256"][:16], "from", os.path.basename(stage))
name, root, step = CANDIDATE
r = read_json("%s/native/%d/result.json" % (root, step), sealed=True)
s = read_json("%s/steps/%d.json" % (root, step), sealed=True)
text = r["candidate_skill"]
if s["candidate_skill_hash"] not in (digest(text), hashlib.sha256(text.encode()).hexdigest()):
    raise SystemExit("%s: candidate text does not match the hash its step recorded" % name)
with open(os.path.join(out, name + ".md"), "x", encoding="utf-8") as handle:
    handle.write(text)
print(name, "bytes", len(text.encode()), "gate", s["gate_action"], "(a candidate the frozen gate rejected)")
