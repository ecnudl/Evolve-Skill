"""The run subcommands of ``scripts/run_execskill.py`` (protocol ``fivebench-execskill-v1``; implementation plan §6;
tickets A13-1, A12-1, C2-1 §1, fixer-1): one handler per subcommand, each loading and verifying the manifest
(``manifest.load``: the code map, the interpreter and the zero-call image inspection) and calling the module adapter.

- ``run --manifest M --chain G|D``: ``chain.run_manifest`` (the read children get ``--manifest M``); exit 0 when the
  chain completed, 3 when it paused or was terminated;
- ``terminate --manifest M --chain G|D --decision TEXT``: ``chain.terminate_manifest`` (§9.4, an owner action);
- ``step-unit --manifest M --spec S``: ``step.run_unit_spec`` (one step in a child; exit 0, 3 paused, 5 awaiting the
  owner's recorded decision);
- ``evaluate-unit --manifest M --spec S``: ``evaluation.run_unit_spec`` (one test-read unit in the child
  ``chain.launch_child`` starts; the same exit codes);
- ``report --manifest M --out NEWDIR``: ``readout.report``; the run-root canary scan before a chain's first unseal
  (registrar decision C3-1 (b)) can pause it: the pause is printed (kind, reason, where) and the exit code is 3, or 5
  while the scan's hit awaits the owner's recorded decision (ticket PR-C31-1);
- ``seal-addendum --manifest M``: ``evaluation.seal_addendum`` on the manifest's run root (§8.1, owner #32; ticket
  fixer-1): the owner's formal-chain addendum ``shared/formal-addendum.md`` hashed and sealed once, an owner action.

``add_arguments(subparsers)`` registers these subcommands; ``HANDLERS`` maps their names to the handlers. Every handler
prints a JSON summary (statuses, counts and hashes -- never a score or a reply) and returns its exit code.
"""
from __future__ import annotations

import json

from . import chain, evaluation, manifest, protocol, readout, step
from .cells import Pause

__all__ = ("HANDLERS", "add_arguments", "evaluate_unit", "report", "run", "seal_addendum", "step_unit", "terminate")


def _print(value):
    print(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False))


def run(args):
    found = chain.run_manifest(manifest.load(args.manifest), chain=args.chain, path=args.manifest)
    _print(found)
    return chain.EXIT_COMPLETE if found["status"] == "complete" else chain.EXIT_PAUSED


def terminate(args):
    _print(chain.terminate_manifest(manifest.load(args.manifest), chain=args.chain, decision=args.decision))
    return chain.EXIT_COMPLETE


def step_unit(args):
    return step.run_unit_spec(manifest.load(args.manifest), spec=args.spec)


def evaluate_unit(args):
    return evaluation.run_unit_spec(manifest.load(args.manifest), spec=args.spec)


def report(args):
    try:
        found = readout.report(manifest.load(args.manifest), out=args.out)
    except Pause as pause:  # the run-root canary scan before the first unseal (registrar decision C3-1 (b))
        _print({"paused": pause.kind, "reason": pause.reason, "at": pause.cell})
        return chain.EXIT_AWAITING if pause.kind == "awaiting_owner_decision" else chain.EXIT_PAUSED
    _print(found)
    return chain.EXIT_COMPLETE


def seal_addendum(args):
    value = manifest.load(args.manifest)
    sealed = evaluation.seal_addendum(value["root"], evidence=value["evidence"])
    _print({"addendum": sealed["document"], "sha256": sealed["sha256"], "written_at": sealed["written_at"],
            "record_sha256": sealed[protocol.RECORD_HASH]})
    return chain.EXIT_COMPLETE


HANDLERS = {"run": run, "terminate": terminate, "step-unit": step_unit, "evaluate-unit": evaluate_unit,
            "report": report, "seal-addendum": seal_addendum}


def add_arguments(subparsers):
    """Register the subcommands of ``HANDLERS`` on ``subparsers`` (``argparse`` sub-parsers, the command line's
    style: ``--manifest`` on each; ``--chain`` G or D for run and terminate)."""
    for name in HANDLERS:
        command = subparsers.add_parser(name)
        command.add_argument("--manifest", required=True)
        if name in ("run", "terminate"):
            command.add_argument("--chain", required=True, choices=sorted(protocol.CHAINS))
        if name in ("step-unit", "evaluate-unit"):
            command.add_argument("--spec", required=True)
        if name == "terminate":
            command.add_argument("--decision", required=True)
        if name == "report":
            command.add_argument("--out", required=True)
