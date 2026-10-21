"""Zero-call: pool the sealed blocks of several one-block (or partial) rubric-form studies and run the registered
analysis over the union -- the studies of one series share protocol, arms, rubrics, template and budget and differ
only by the series label (a different block plan each). Usage: reader.py <study dir> [<study dir> ...]
Each directory is <output>/study. Pending studies contribute their COMPLETED blocks only (sealed outcome.json).
Every finished study is re-verified (verify_result: bindings and evidence inventory); studies whose implementation
identity (study sources, native sources, code closure) differs are refused unless --allow-closure-differences is
given, in which case the differing studies are listed (a disclosure to carry into the ledger)."""
import json, os, sys
from skillopt.continual_eval.core import read_json
from skillopt.feedback_study import rubric_form as rf
from skillopt.validator_pilot.api import digest

try:  # 10/15: the verification-note binding study (same series shape, its own protocol, arms and analysis)
    from skillopt.feedback_study import rubric_binding as rb
except ImportError:  # a snapshot without the binding module reads rubric-form series only
    rb = None

allow_closures = "--allow-closure-differences" in sys.argv
roots = [a for a in sys.argv[1:] if not a.startswith("--")]
candidates, outcomes, protocols, labels, seen = [], [], set(), [], set()
pending, closures = [], {}


def comparable(spec):
    """The protocol with only what a series may legitimately vary removed: its own hash, the block count and the
    series label. Everything else -- template (panel hash, families, model, parent, seed, policy), rubrics, arms,
    budget, plan seed, analysis, the template stage's provenance -- must be identical to pool."""
    value = {k: v for k, v in spec.items() if k not in ("record_hash", "blocks")}
    value["source"] = {k: v for k, v in spec["source"].items() if k != "series"}
    return json.dumps(value, sort_keys=True)


first = read_json(os.path.join(roots[0], "protocol.json"), sealed=True)
module = rb if (rb is not None and first["protocol"] == rb.PROTOCOL) else rf
for root in roots:
    spec = read_json(os.path.join(root, "protocol.json"), sealed=True)
    protocols.add(comparable(spec))
    name = os.path.basename(os.path.dirname(root.rstrip("/")))
    study = read_json(os.path.join(root, "study.json"), sealed=True)["study"]
    closures.setdefault(digest({k: study[k] for k in ("study_sources", "native_sources", "code_closure")}), []).append(name)
    if os.path.exists(os.path.join(root, "result.json")):
        result = module.verify_result(root)  # zero-call: bindings and the evidence inventory of the finished study
    else:
        result = None
    labels.append((name, spec["source"].get("series"), spec["blocks"],
                   None if result is None else result["status"], None if result is None else result.get("reason")))
    if result is not None and result["status"] != "completed":
        pending.append((spec["source"].get("series"), result.get("reason"), {k: result["costs"].get(k) for k in ("solver_calls", "verifier_calls", "reflection_calls", "unknown_cost_attempts")}))
    for b in sorted(os.listdir(os.path.join(root, "blocks")), key=int):
        folder = os.path.join(root, "blocks", b)
        if not os.path.exists(os.path.join(folder, "outcome.json")):
            print("  (block %s of %s has no sealed outcome: left out)" % (b, root))
            continue
        c = read_json(os.path.join(folder, "candidates.json"), sealed=True)
        o = read_json(os.path.join(folder, "outcome.json"), sealed=True)
        assert o["candidates_hash"] == c["record_hash"] and c["protocol_hash"] == spec["record_hash"] == o["protocol_hash"]
        if c["record_hash"] in seen:
            raise SystemExit("the same sealed block was given twice (%s): not pooled" % folder)
        seen.add(c["record_hash"])
        candidates.append(c)
        outcomes.append(o)
if len(protocols) != 1:
    raise SystemExit("the studies differ beyond the series label and the block count: not pooled (report them separately)")
if len(closures) != 1:
    listing = "; ".join("%s: %s" % (key[:12], names) for key, names in closures.items())
    if not allow_closures:
        raise SystemExit("the studies ran under %d different implementation identities (%s): not pooled without "
                         "--allow-closure-differences" % (len(closures), listing))
    print("DISCLOSURE: pooled across %d implementation identities (%s)" % (len(closures), listing))
spec = first
binding = module is rb
if not binding and spec["protocol"] != rf.PROTOCOL:
    raise SystemExit("unknown protocol %s: not pooled" % spec["protocol"])
print("protocol:", spec["protocol"])
print("pooled blocks:", len(outcomes), "from (study, series, blocks, status, reason):", labels)
print("studies that ended pending (kept, never resumed; their completed blocks are pooled, their costs counted):", pending)
a = module.analyze(spec, candidates, outcomes)
p = a["parent"]
print("parent on the selection set: %d/%d (unknown %d)" % (p["pass"], p["positions"], p["unknown"]))
for arm, v in a["arms"].items():
    print("  %-19s pass %4d/%-4d (unknown %d) yield %.3f | dispositions %s | authorized blocks %s | %sblocks with feedback %s" % (
        arm, v["pass"], v["positions"], v["unknown"], v["yield"], v["dispositions"], v["authorized_blocks"],
        ("binding applied %s | " % v["binding_applied_blocks"]) if binding else "", v["blocks_with_feedback"]))
for arm, v in a["verifier_component"].items():
    print("  verifier %-16s detection %s (%s/%s) false rejection %s (%s/%s)" % (
        arm, None if v["detection_rate"] is None else round(v["detection_rate"], 3), v["rejected_host_fail_rows"], v["eligible_host_fail_rows"],
        None if v["false_rejection_rate"] is None else round(v["false_rejection_rate"], 3), v["rejected_host_pass_rows"], v["eligible_host_pass_rows"]))
for c in a["contrasts"]:
    if binding:
        bounds = c["unknown_sensitivity_mean_bounds"]
        print("  contrast %-19s - %-13s %s informative %d/%d per block %s (all blocks %s) mean %s | positions wins %d losses %d | block sign-flip p=%.3f (%s) | unknown bounds %s | supported %s" % (
            c["treatment"], c["control"], "PRIMARY" if c["primary"] else "       ", c["informative_blocks"], len(c["all_block_differences"]),
            c["differences"], c["all_block_differences"], None if c["mean_difference"] is None else round(c["mean_difference"], 2),
            c["paired_positions"]["wins"], c["paired_positions"]["losses"], c["block_sign_flip"]["p_value"], c["direction"],
            None if bounds is None else [round(x, 2) for x in bounds], c["supported"]))
        continue
    print("  contrast %-16s - %-13s per block %s mean %+.2f | pooled yield %+.4f | positions wins %d losses %d | block sign-flip p=%.3f (%s) | unknown bounds %s" % (
        c["treatment"], c["control"], c["differences"], c["mean_difference"], c["pooled_yield_difference"],
        c["paired_positions"]["wins"], c["paired_positions"]["losses"], c["block_sign_flip"]["p_value"], c["direction"],
        [round(x, 2) for x in c["unknown_sensitivity_mean_bounds"]]))
if binding:
    an = spec["analysis"]
    print("lead contrast: %s - %s | alpha %s per primary contrast (%s)" % (an["lead"][0], an["lead"][1], an["confirmatory"]["alpha"], an["multiplicity"]))
    print("compliance:", an["compliance"])
print("claim limits:", a["claim_limits"])
