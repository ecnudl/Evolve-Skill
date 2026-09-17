"""Preload existing gateway session IDs before importing the frozen source CLI."""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SESSION_KEYS = (
    "OPENAI_COMPATIBLE_SESSION_ID",
    "OPTIMIZER_OPENAI_COMPATIBLE_SESSION_ID",
    "TARGET_OPENAI_COMPATIBLE_SESSION_ID",
)
DEFAULT_OUT = Path("outputs/scope_evolution_v2/source_retention_gpt55_20260908_sessionfix")
FAILED_OUT = Path("outputs/scope_evolution_v2/source_retention_gpt55_20260908")


def preload_session_environment(repo: Path) -> str | None:
    """Copy only existing session variables; never print, invent or persist IDs.

    Use the frozen runtime's precedence: .env overrides inherited values for
    keys it defines; target-specific values take precedence over shared ones.
    Literal parsing deliberately does not expand unrelated secret variables.
    """
    from dotenv import dotenv_values

    values = dotenv_values(Path(repo) / ".env", interpolate=False)
    for key in SESSION_KEYS:
        value = values.get(key)
        if value is not None:
            os.environ[key] = value
    return (os.environ.get("TARGET_OPENAI_COMPATIBLE_SESSION_ID")
            or os.environ.get("OPENAI_COMPATIBLE_SESSION_ID") or "").strip() or None


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--phase")
    parser.add_argument("--out", type=Path)
    known, _ = parser.parse_known_args(arguments)
    real_phase = known.phase in {"pilot", "test"} and not any(arg in {"-h", "--help"} for arg in arguments)
    output = known.out if known.out is not None else DEFAULT_OUT
    if (REPO / output).resolve() == (REPO / FAILED_OUT).resolve():
        raise ValueError("Preserve the failed source run; use a new sessionfix output directory")
    if known.out is None:
        arguments.extend(["--out", str(DEFAULT_OUT)])

    # No SkillOpt/CLI/model imports may be moved above this line. Its backend
    # snapshots environment variables once when the module is first imported.
    expected = preload_session_environment(REPO)
    if real_phase and expected is None:
        raise ValueError("No existing target/shared gateway session ID is configured; no API calls started")
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    delegate = importlib.import_module("scripts.source_retention_mvp")
    if real_phase:
        backend = importlib.import_module("skillopt.model.openai_compatible_backend")
        if backend.TARGET_CONFIG.session_id != expected:
            raise ValueError("Target gateway session was not initialized from the preloaded configuration; use a fresh launcher process")
    return delegate.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
