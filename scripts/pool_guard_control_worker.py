"""Container-only authored Pool controls: no task, reference, or model input."""
import contextlib
import hashlib
import inspect
import json
import multiprocessing as mp
import os
import time
from pathlib import Path

VERSION = "pool-guard-engineering-controls-v2"
STARTED = None


def emit(phase):
    print("POOL_DIAG " + json.dumps({"phase": phase}), flush=True)


def identity(value):
    return value


def source_file(value):
    """Fingerprint the SDK function, not contextlib's decorator wrapper."""
    return inspect.getsourcefile(inspect.unwrap(value))


def busy(_):
    STARTED.set()
    time.sleep(60)
    return 1


def main():
    if os.environ.get("SKILLOPT_POOL_CONTROL") != VERSION or not Path("/.dockerenv").exists():
        raise SystemExit("Container-only engineering control")
    request = json.loads(Path("/input/request.json").read_text())
    if (set(request) != {"guard", "case", "sdk_sources"} or type(request["guard"]) is not bool
            or request["case"] not in {"quick_map", "busy_exit"}):
        raise SystemExit("Invalid authored control")
    from multiprocessing import pool, popen_fork

    from bigcodebench.eval.utils import safe_environment
    files = {"sdk_utils": source_file(safe_environment), "pool": pool.__file__,
             "popen_fork": popen_fork.__file__}
    actual = {k: hashlib.sha256(Path(p).read_bytes()).hexdigest() for k, p in files.items()}
    if actual != request["sdk_sources"] or mp.get_start_method() != "fork":
        emit("source_or_start_method_mismatch")
        raise SystemExit(2)
    emit("sdk_verified")
    global STARTED
    STARTED = mp.Event()
    context = safe_environment() if request["guard"] else contextlib.nullcontext()
    with context:
        emit("guard_entered")
        with mp.Pool(processes=2) as workers:
            emit("pool_entered")
            if request["case"] == "quick_map":
                if workers.map(identity, [1, 2]) != [1, 2]:
                    raise RuntimeError("Authored map mismatch")
                emit("map_completed")
            else:
                workers.apply_async(busy, [None])
                if not STARTED.wait(5):
                    emit("worker_start_unconfirmed")
                    raise SystemExit(3)
                emit("busy_worker_confirmed")
            emit("before_pool_exit")
        emit("after_pool_exit")
    emit("after_guard_exit")


if __name__ == "__main__":
    main()
