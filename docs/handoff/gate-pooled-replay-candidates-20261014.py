"""Zero-call: check the texts of the four LiveMath gate candidates against the hashes their stages recorded and
print what the headroom pilot's empty arm did on format. With --write DIR the texts are written as files."""
import hashlib, json, os, sys
from skillopt.validator_pilot.api import digest
P = "/root/fivebench-g-20261013-livemath-"
out = sys.argv[sys.argv.index("--write") + 1] if "--write" in sys.argv else None
if out:
    os.makedirs(out, mode=0o700)
for arm, name, step in (("e41s0", "lm-v9-e41", 0), ("e41s2", "lm-v9-e41", 2), ("z41s0", "lm-v9-z41", 0),
                        ("z41s2", "lm-v9-z41", 2)):
    d = P + name + "/learning"
    r = json.load(open("%s/native/%d/result.json" % (d, step)))
    s = json.load(open("%s/steps/%d.json" % (d, step)))
    text = r["candidate_skill"]
    ok = s["candidate_skill_hash"] in (digest(text), hashlib.sha256(text.encode()).hexdigest())
    fp = s["first_pass"]
    print(arm, name, "step", step, "| bytes", len(text.encode()), "| text matches the step's recorded hash:", ok, "| gate", s["gate_action"],
          "| first pass %d/%d, confirmation %d/%d" % (fp["wins"], fp["losses"], s["wins"], s["losses"]))
    if not ok:
        raise SystemExit("candidate text of %s step %d does not match the hash its stage recorded" % (name, step))
    if out:
        with open(os.path.join(out, arm + ".md"), "x", encoding="utf-8") as handle:
            handle.write(text)
        print("   written", os.path.join(out, arm + ".md"), hashlib.sha256(text.encode()).hexdigest()[:16])
res = json.load(open(P + "pilot-b/result.json"))
for arm, a in (res.get("arms") or {}).items():
    print("pilot-b arm", arm, {k: a.get(k) for k in ("pass", "fail", "unknown", "invalid_format")})
