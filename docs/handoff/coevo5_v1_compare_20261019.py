"""Descriptive, unregistered paired differences between the ended v1 chains (zero calls; read only).

Uses the frozen v1 report loader and readout (same bootstrap seed and resamples as the registered report)."""
import json
import sys

from skillopt.coevo5 import readout
from skillopt.coevo5 import report as reports
from skillopt.coevo5.protocol import ORDER

value, run = reports.of_manifest(sys.argv[1])
units, states = reports.load(run)
found = reports.panels(run, units)
records = {key: readout.Unit(unit["source"], {i: c["token"] for i, c in unit["cells"].items()})
           for key, unit in units.items()}
r = readout.Readings(records, found)
M, D, A = readout.macro, readout.difference, readout.accuracy
last = len(ORDER)
asks = {
    "I0-SkillOpt5": D(M("I-glm", 0), M("SkillOpt-glm", last)),
    "I0-GEPA5": D(M("I-glm", 0), M("GEPA-glm", last)),
    "I0-E5": D(M("I-glm", 0), M("E-glm", last)),
    "SkillOpt5-GEPA5": D(M("SkillOpt-glm", last), M("GEPA-glm", last)),
    "I0-blank0": D(M("I-glm", 0), M("E-glm", 0)),
}
for bench in ORDER:
    asks["bench:%s:I0-SkillOpt5" % bench] = D(A("I-glm", 0, bench), A("SkillOpt-glm", last, bench))
    asks["bench:%s:I0-blank0" % bench] = D(A("I-glm", 0, bench), A("E-glm", 0, bench))
    asks["bench:%s:E5-blank0" % bench] = D(A("E-glm", last, bench), A("E-glm", 0, bench))
    asks["bench:%s:SkillOpt5-blank0" % bench] = D(A("SkillOpt-glm", last, bench), A("E-glm", 0, bench))
    asks["bench:%s:GEPA5-blank0" % bench] = D(A("GEPA-glm", last, bench), A("E-glm", 0, bench))
out = {}
for name, terms in asks.items():
    res = r.reading(terms)
    out[name] = {v: {"estimate": round(res[v]["estimate"], 2), "interval95": [round(x, 2) for x in res[v]["interval95"]]}
                 for v in readout.VARIANTS} if res["available"] else res
print(json.dumps(out, ensure_ascii=False))
