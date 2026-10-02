"""Zero-API ALFWorld launch/reset/step/cleanup check, not a task-accuracy run."""
from __future__ import annotations

import argparse
import fcntl
import multiprocessing
import os
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.backends import _new_alfworld
from skillopt.continual_eval.core import output_lock, read_json, require, write_json
from skillopt.continual_learning.launch import learning_environment


def run(manifest_path, panel_path, output, native_lock):
    # This diagnostic consumes only frozen public runtime/task pointers. It does
    # not replay the historical learner or claim its new sources have old hashes.
    manifest = read_json(manifest_path, sealed=True)
    panel = read_json(panel_path)
    require(manifest.get("benchmark") == panel.get("benchmark") == "alfworld"
            and manifest["model"]["provider"] != "fixture", "Natural ALFWorld inputs required")
    from skillopt.validator_pilot.api import digest

    require(digest(panel) == manifest["panel_hash"], "Manifest/panel binding mismatch")
    task = panel["tasks"][0]
    prior = os.environ.get("ALFWORLD_DATA")
    before = {child.pid for child in multiprocessing.active_children()}
    with output_lock(output), Path(native_lock).open("a") as resource:
        require(not (Path(output) / "result.json").exists(), "Use a new smoke output directory")
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        write_json(Path(output) / "started.json", seal({"manifest_hash": manifest["record_hash"],
            "task_hash": digest(task), "evidence_kind": "native_environment_smoke_not_model_effect",
            "model_calls": 0}))
        env, cleanup = None, False
        try:
            with learning_environment(manifest):
                env = _new_alfworld(task["public"], manifest["runtime"])
                try:
                    observations, _, infos = env.reset()
                    reset_ok = bool(observations and isinstance(observations[0], str))
                    actions = infos[0].get("admissible_commands", [])
                    require(actions and all(isinstance(a, str) for a in actions),
                            "Native reset has no public admissible commands")
                    observations, _, _, _, infos = env.step(["look" if "look" in actions else actions[0]])
                    step_ok = bool(observations and isinstance(observations[0], str))
                    require(reset_ok and step_ok and "won" in infos[0], "Native episode signals incomplete")
                    status = "native_reset_step_ready"
                finally:
                    env.close()
                    cleanup = not env.process.is_alive()
        except Exception as exc:
            # Error class only: native internals/private metadata are not public.
            status = "unsupported:" + type(exc).__name__
        restored = os.environ.get("ALFWORLD_DATA") == prior
        after = {child.pid for child in multiprocessing.active_children()}
        result = seal({"status": status, "manifest_hash": manifest["record_hash"],
                       "task_hash": digest(task), "cleanup_confirmed": cleanup,
                       "new_live_child_processes": len(after - before),
                       "environment_restored": restored, "model_calls": 0,
                       "evidence_kind": "native_environment_smoke_not_model_effect",
                       "historical_result_modified": False})
        write_json(Path(output) / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--panel", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--native-lock", required=True)
    args = parser.parse_args()
    result = run(args.manifest, args.panel, args.output, args.native_lock)
    print(result)
    return 0 if (result["status"] == "native_reset_step_ready" and result["cleanup_confirmed"]
                 and result["environment_restored"] and not result["new_live_child_processes"]) else 3


if __name__ == "__main__":
    raise SystemExit(main())
