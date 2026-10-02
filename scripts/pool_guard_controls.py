"""24 predeclared synthetic Pool/official-guard controls, zero model calls.

Two fixed images x guard on/off x quick-map/busy-exit x three repeats. This is
an engineering compatibility study, never a hidden-task retry or gate repair.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import tempfile
import time
import uuid
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.backends import _image_ready
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.skill_validation import sandbox

VERSION = "pool-guard-engineering-controls-v2"
IMAGES = {
    "original": "sha256:b13b0bb97861eb3a2f3f9ead1e8718d1410882613f84e088bb31338c343149fa",
    "data_only": "sha256:4e8c8cb8cb1ed55daf980203da45ef5e4c3eff1cfcf44121968bd52f82f851c8",
}
SDK = {"sdk_utils": "9061f74fe937c4eb7a1b2bc423f7acab547ae01804d5e25933e2aa8a3cc2d685",
       "pool": "1539ad7e8aa4b8df03778f1fe5381d928928c5837be7172747bf07c3e6cb4a78",
       "popen_fork": "0a09db57e7fab7061c01a61778feea6e2b6bb02ccbc150332f2960b05258ef95"}
WORKER = Path(__file__).with_name("pool_guard_control_worker.py")
PHASES = {"sdk_verified", "guard_entered", "pool_entered", "map_completed", "busy_worker_confirmed",
          "before_pool_exit", "after_pool_exit", "after_guard_exit", "worker_start_unconfirmed",
          "source_or_start_method_mismatch"}


def sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def sources():
    return {str(p.resolve()): sha(p) for p in (Path(__file__), WORKER, Path(sandbox.__file__),
        Path(_image_ready.__code__.co_filename), Path(read_json.__code__.co_filename))}


def matrix():
    rows = []
    for repeat in range(3):
        for case in ("quick_map", "busy_exit"):
            for image in (tuple(IMAGES) if repeat % 2 == 0 else tuple(reversed(IMAGES))):
                for guard in ((False, True) if repeat % 2 == 0 else (True, False)):
                    rows.append({"index": len(rows), "repeat": repeat, "case": case, "image": image, "guard": guard})
    return rows


def prepare(output, native_lock):
    root, lock = safe_path(output), safe_path(native_lock)
    require(not root.exists() and lock.is_file() and not lock.is_relative_to(root), "New output and existing native lock required")
    identities = {k: _image_ready({"image": image}) for k, image in IMAGES.items()}
    require(all(v["status"] == "ready" and v["image_id"] == IMAGES[k] for k, v in identities.items()), "Fixed images unavailable")
    value = seal({"version": VERSION, "output_root": str(root), "native_lock": str(lock),
        "images": IMAGES, "image_identities": identities, "sdk_sources": SDK, "sources": sources(), "matrix": matrix(),
        "runtime": {"outer_timeout_seconds": 20, "memory_mb": 8192, "cpus": 1, "pids_limit": 128,
                    "cleanup_timeout_seconds": 10}, "model_calls": 0, "hidden_tasks_used": False,
        "engineering_only": True, "qualification_or_skill_gate_authorized": False})
    write_json(root / "protocol.json", value)
    return value


def check(root):
    value = read_json(root / "protocol.json", sealed=True)
    require(value["version"] == VERSION and value["output_root"] == str(root) and value["sources"] == sources()
            and value["images"] == IMAGES and value["sdk_sources"] == SDK and value["matrix"] == matrix()
            and value["runtime"] == {"outer_timeout_seconds": 20, "memory_mb": 8192, "cpus": 1,
                                    "pids_limit": 128, "cleanup_timeout_seconds": 10}, "Control protocol changed")
    return value


def command(image, name, directory):
    return ["docker", "run", "--pull=never", "--name", name, "--network=none", "--read-only",
        "--user=65534:65534", "--cap-drop=ALL", "--security-opt=no-new-privileges=true", "--pids-limit=128",
        "--memory=8192m", "--memory-swap=8192m", "--cpus=1", "--ipc=private", "--shm-size=64m",
        "--no-healthcheck", "--log-driver=none", "--ulimit=nofile=256:256", "--ulimit=core=0:0",
        "--env", "SKILLOPT_POOL_CONTROL=" + VERSION, "--env", "MPLCONFIGDIR=/tmp/matplotlib",
        "--env", "OMP_NUM_THREADS=1", "--env", "OPENBLAS_NUM_THREADS=1",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=256m,mode=1777", "--workdir=/tmp",
        "--mount", f"type=bind,source={directory},target=/input,readonly", "--entrypoint=python",
        image, "-I", "-B", "-u", "/input/worker.py"]


def _private_logs(root, item, stdout, stderr):
    folder = safe_path(root / "logs")
    folder.mkdir(mode=0o700, exist_ok=True)
    result = {}
    for name, data in (("stdout", stdout), ("stderr", stderr)):
        require(len(data) <= 32768, "Control log exceeds frozen output bound")
        path = safe_path(folder / f"{item['index']}-{name}.bin")
        with path.open("xb") as handle:
            path.chmod(0o600)
            handle.write(data)
        result[name] = {"path": str(path.relative_to(root)), "sha256": hashlib.sha256(data).hexdigest(),
                        "bytes": len(data)}
    return result


def _validate_logs(root, item, result):
    require(set(result.get("private_logs", {})) == {"stdout", "stderr"}, "Private control logs missing")
    for name, log in result["private_logs"].items():
        require(log["path"] == f"logs/{item['index']}-{name}.bin" and type(log["bytes"]) is int
                and 0 <= log["bytes"] <= 32768, "Control log identity differs")
        path = safe_path(root / log["path"])
        require(path.stat().st_size == log["bytes"] and sha(path) == log["sha256"]
                and log["sha256"] == result[name + "_sha256"], "Private control log changed")


def _execute(item, root):
    image = IMAGES[item["image"]]
    ready = _image_ready({"image": image})
    require(ready["status"] == "ready" and ready["image_id"] == image, "Image unavailable before control")
    with tempfile.TemporaryDirectory(prefix="pool-guard-control-") as directory:
        folder = Path(directory)
        folder.chmod(0o755)
        (folder / "worker.py").write_bytes(WORKER.read_bytes())
        (folder / "request.json").write_text(json.dumps({"guard": item["guard"], "case": item["case"], "sdk_sources": SDK}))
        for path in folder.iterdir():
            path.chmod(0o444)
        name = "pool-guard-control-" + uuid.uuid4().hex
        started = time.monotonic()
        result = cleanup = None
        error = None
        try:
            result = sandbox._bounded_command(command(image, name, folder), 20, limit=32768)
        except Exception as exc:
            error = type(exc).__name__
        finally:
            try:
                cleanup = sandbox._bounded_command(["docker", "rm", "--force", name], 10)
            except Exception:
                pass
        cleaned = (cleanup is not None and not cleanup.timed_out and not cleanup.overflow and not cleanup.unavailable
                   and (cleanup.code == 0 or b"no such container" in cleanup.stderr.lower()))
        stdout = result.stdout if result is not None else b""
        stderr = result.stderr if result is not None else b""
        private_logs = _private_logs(root, item, stdout, stderr)
        phases = []
        for line in stdout.decode(errors="replace").splitlines():
            if line.startswith("POOL_DIAG "):
                try:
                    phase = json.loads(line[len("POOL_DIAG "):])["phase"]
                    if phase in PHASES:
                        phases.append(phase)
                except (ValueError, KeyError, TypeError):
                    pass
        status = ("cleanup_unconfirmed" if not cleaned else "host_execution_error" if result is None else
                  "outer_timeout" if result.timed_out else "output_limit" if result.overflow else
                  "completed" if result.code == 0 and phases[-1:] == ["after_guard_exit"] else "control_failed")
        return {"status": status, "phases": phases, "kill_denial_messages": len(re.findall(
                    rb"Prevented attempt to kill PID \d+ with signal", stdout)),
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(), "private_logs": private_logs,
            "exit_code": result.code if result is not None else None, "error_type": error,
            "cleanup_confirmed": cleaned, "image_id": image, "container_calls": 1,
            "wall_seconds": round(time.monotonic() - started, 6), "includes_cleanup": True,
            "model_calls": 0, "raw_output_exported": False}


def run(output):
    root = safe_path(output)
    with output_lock(root):
        value = check(root)
        for report_path in (root / "reports").glob("*.json"):
            published = read_json(report_path, sealed=True)
            require(published["protocol_hash"] == value["record_hash"] and len(published["record_hashes"]) <= 24,
                    "Published control protocol differs")
            require(all(read_json(root / "records" / (str(i) + ".json"), sealed=True)["record_hash"] == expected
                        for i, expected in enumerate(published["record_hashes"])), "Published control record changed")
        lock = safe_path(value["native_lock"])
        require(lock.is_file(), "Original shared native lock missing")
        with lock.open("rb") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            rows = []
            for item in value["matrix"]:
                key = str(item["index"])
                intent, path = root / "intents" / (key + ".json"), root / "records" / (key + ".json")
                identity = {"protocol_hash": value["record_hash"], "control": item}
                if path.exists():
                    row = read_json(path, sealed=True)
                    require(row["identity"] == identity and read_json(intent, sealed=True) == seal(identity), "Control record differs")
                else:
                    require(not intent.exists(), "Unclosed control: no retries")
                    write_json(intent, seal(identity))
                    row = seal({"identity": identity, "result": _execute(item, root)})
                    write_json(path, row)
                rows.append(row)
                result = row["result"]
                _validate_logs(root, item, result)
                require(result["status"] in {"completed", "outer_timeout", "control_failed", "output_limit",
                        "host_execution_error", "cleanup_unconfirmed"}
                        and type(result["cleanup_confirmed"]) is bool and result["image_id"] == IMAGES[item["image"]]
                        and result["model_calls"] == 0 and result["container_calls"] == 1
                        and isinstance(result["phases"], list) and set(result["phases"]) <= PHASES,
                        "Control receipt identity/status differs")
                if not row["result"]["cleanup_confirmed"]:
                    break
            result = seal({"version": VERSION, "protocol_hash": value["record_hash"],
                "status": "completed" if len(rows) == 24 and all(r["result"]["cleanup_confirmed"] for r in rows) else "pending",
                "closed": len(rows), "planned": 24, "counts": dict(Counter(r["result"]["status"] for r in rows)),
                "record_hashes": [r["record_hash"] for r in rows], "model_calls": 0,
                "container_calls": sum(r["result"]["container_calls"] for r in rows),
                "wall_seconds": sum(r["result"]["wall_seconds"] for r in rows),
                "engineering_only": True, "hidden_tasks_used": False, "qualification_or_skill_gate_authorized": False})
            write_json(root / "reports" / (result["record_hash"] + ".json"), result)
            return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "check", "run"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--native-lock")
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        require(args.native_lock, "Shared native lock required")
        value = prepare(args.output, args.native_lock)
    elif args.mode == "check":
        value = check(safe_path(args.output))
    else:
        value = run(args.output)
    print(json.dumps({k: value[k] for k in ("version", "record_hash", "status", "closed", "counts", "model_calls") if k in value}))


if __name__ == "__main__":
    main()
