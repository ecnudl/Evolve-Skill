"""Real API / fabricated feedback: test updater delivery, NOT learning effects.

No solver or Python candidate is executed. The exact same scripted public
feedback is supplied to both strategies. This command must never be counted
as a natural task or an independent confirmation experiment.
"""
import argparse
import hashlib
import json
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.mechanism_learning import STRATEGIES, propose
from skillopt.skill_validation.models import require
from skillopt.skill_validation.natural_study import _write
from skillopt.skill_validation.public_revision import _revision_lock
from skillopt.skill_validation.rule_learning_smoke import _fixture_feedback
from skillopt.skill_validation.rule_skill import RuleSkill
from skillopt.skill_validation.single_round import BoundedCalls
from skillopt.validator_pilot.api import CachedAPI


def run(repo, output, *, repeats=3, proxy=None):
    require(type(repeats) is int and 1 <= repeats <= 3, "Smoke repeats must be 1..3")
    with _revision_lock(output / "lock"):
        parent = RuleSkill("mechanism-api-fixture-only", ())
        feedback, _ = _fixture_feedback(parent)
        with CachedAPI(repo, output / "api", workers=2, provider="bigmodel", stream=True,
                       reasoning_effort="low", proxy=proxy) as api:
            protocol = seal({"version": "mechanism-updater-real-api-fixture-feedback-v1",
                "repeats": repeats, "parent": parent.to_dict(), "feedback_hash": feedback["record_hash"],
                "script_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted((repo / "skillopt/skill_validation").glob("*.py"))},
                "service": api.service, "real_model_calls_with_scripted_feedback": True,
                "method_effect_evaluated": False, "deployment_authorized": False})
            _write(output / "protocol.json", protocol)
            _write(output / "fixture_feedback.json", feedback)
            calls = BoundedCalls(api, output / "budget", protocol["record_hash"], 2 * repeats)
            def one(job):
                strategy, repeat = job
                result = propose(calls, parent, feedback, strategy=strategy, repeat=repeat)
                _write(output / "updates" / f"{strategy}-{repeat}.json", result)
                return {"strategy": strategy, "repeat": repeat, "status": result["status"],
                        "request_hash": result["api_receipt"]["request_hash"],
                        "candidate": result["update"].get("candidate"),
                        "semantic_support_verified": False}
            rows = api.parallel([(s, r) for r in range(repeats) for s in STRATEGIES], one,
                                "API format smoke on marked fixtures")
            result = seal({"protocol_hash": protocol["record_hash"], "rows": rows,
                "accounting": calls.accounting(), "real_model_with_fabricated_feedback": True,
                "provenance": "engineering_fixture_feedback_not_natural_experiment",
                "method_effect_evaluated": False, "deployment_authorized": False,
                "warning": "A valid cited candidate establishes syntax only, not useful learning or transfer."})
            _write(output / "summary.json", result)
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--proxy")
    args = parser.parse_args()
    result = run(Path.cwd(), args.output, repeats=args.repeats, proxy=args.proxy)
    print(json.dumps({"accounting": result["accounting"], "statuses": [r["status"] for r in result["rows"]],
                      "method_effect_evaluated": False}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
