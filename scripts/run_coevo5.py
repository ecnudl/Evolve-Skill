"""Command line of the five-bench coevolution protocol (docs/handoff/coevo5-registration-v6-20261017.md).

  run            --manifest M --chain C        run a chain until it completes or pauses (never resumes by itself)
  evaluate-unit  --manifest M --spec S         one evaluation unit (the child process of ``run``; its stdout and
                                               stderr are a sealed file chosen by the parent)
  qualify-test-sheet --manifest M              the SpreadsheetBench test-side qualification (a child of ``run``
                                               before stage 0; zero model calls)
  monitor        --manifest M                  units, counts and the token ledger -- never a score
  check-baselines --manifest M                 zero calls, before launch: every baseline stage's frozen manifest
                                               builds on the pinned data, runtimes ready, client service unchanged
  report         --manifest M --out NEWDIR     the report of the ended chains (§12): report.json and report.md in a
                                               new directory; zero calls, nothing written into the run
  recover        --unit-root U --decision TEXT the owner's decision to redo a paused or interrupted unit (§13.4 b)
  terminate      --manifest M --chain C --decision TEXT
  resume-ledger  --manifest M --decision TEXT  admit reservations again after a halt (the owner's decision)

Before launch, on the launch snapshot, in this order (skillopt/coevo5/prelaunch.py):
  qualify-train-sheet --engine-qualification Q --out NEWDIR
                                               the training-side SpreadsheetBench qualification (§2.1; zero model
                                               calls), with the snapshot's engine qualification Q
  build-archive  --out NEWDIR --previous A [--proxy P]
                                               the research archive (§7): downloads the fixed public pages; v2:
                                               the pages of the previous archive A carried over byte for byte
  prepare-texts  --out P/NEWDIR --repo R --existing BENCH=DIR (SearchQA, OfficeQA, LiveMath) [--proxy P]
                                               the two missing instructions and the six initial rubrics (§0, §6;
                                               GLM-5.3, charged to the pre-launch ledger P/ledger); exit 3 when a
                                               text is missing (the preparation stopped there)
  import-texts   --out P/NEWDIR --source T     v2: the v1 pre-launch texts T, verified in place and recorded in the
                                               v2 pre-launch directory P (zero calls; delta §11)
  smoke-make     --out P/NEWDIR --texts T --archive A --repo R --deepseek-env D --engine-qualification E
                 --sheet-qualification Q [--router-env E] [--chain C] [--proxy P] [--research-proxy P]
                 [--workers N] [--searchqa-items N] [--officeqa-items N]
                                               the smoke's specification (§14 step 5; zero calls): v3, chain I-ds
                                               (the deepseek solver through the PJLAB token route, credential file
                                               D) from the instructions, on the snapshot's engine qualification E:
                                               the format check (with Q's training-side SpreadsheetBench items),
                                               then stages SearchQA and OfficeQA
  smoke          --spec P/DIR/smoke.json       run the smoke (training data, every GLM-5.3 call charged to P/ledger)
                                               until it completes or pauses; exit 3 when paused
  smoke-summary  --spec P/DIR/smoke.json       what the smoke ran so far (zero calls)
  make-manifest  --out FILE --root NEWDIR --sheet-qualification Q --engine-qualification E --texts T --smoke S
                 --archive A --baseline-protocol F --repo R --deepseek-env D [--router-env E] --gepa-source G
                 [--proxy P] [--research-proxy P] [--workers N]
                                               the launch manifest (§0, §14 step 6; zero calls); the GLM-5.3 tokens
                                               of the pre-launch ledger come off the overall cap
  check-baselines --manifest M                 (as above) required before any chain runs
  consent        --manifest M --date D --note TEXT
                                               the owner's consent to the test sets, in the owner's words (§0)

Every decision subcommand records the owner's words; run them only on the owner's instruction.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.weak_solver_probe import GATEWAY  # noqa: E402
from skillopt.coevo5 import baseline, data, evaluation, manifest, prelaunch, qualify, smoke  # noqa: E402
from skillopt.coevo5 import chain as chains  # noqa: E402
from skillopt.coevo5 import report as reports  # noqa: E402
from skillopt.coevo5.cells import Pause  # noqa: E402
from skillopt.coevo5.units import CHAINS, cell_context, solver_endpoint  # noqa: E402
from skillopt.continual_eval.core import read_json, require, safe_path, write_json  # noqa: E402


def _environment(setting):
    os.environ["ALFWORLD_DATA"] = setting.runtime["alfworld"]["alfworld_data"]


def run(args):
    _, setting = manifest.load(args.manifest)
    require(baseline.checked(setting), "check-baselines has not passed for this manifest (§2.1, §14)")
    _environment(setting)
    print(json.dumps(chains.run(setting, args.chain), sort_keys=True))


def evaluate_unit(args):
    _, setting = manifest.load(args.manifest)
    _environment(setting)
    spec = read_json(args.spec)
    root = safe_path(spec["unit_root"])
    if (root / "unit.json").exists():
        return chains.EXIT_COMPLETE
    attempt = evaluation._next_attempt(root)
    if attempt is None:
        return chains.EXIT_AWAITING
    chain, stage = spec["chain"], spec["stage"]
    solver = "glm-5.3" if chain == chains.SHARED else CHAINS[chain]["solver"]
    endpoint = solver_endpoint(setting, solver, chains.evaluation_scopes(chain, stage))
    try:
        evaluation.evaluate(root, run=setting.run, shared=setting.shared, pinned=setting.extra["pinned"],
                            chain=chain, stage=stage, benchmark=spec["benchmark"],
                            skill=spec["skill"],
                            context=cell_context(setting, attempt, endpoint), workers=setting.workers,
                            previous=spec["previous"])
    except Pause:
        return chains.EXIT_PAUSED
    return chains.EXIT_COMPLETE


def qualify_test_sheet(args):
    """§2.1: once for the run, before any stage-0 call; exit 4 when no test reference qualifies."""
    _, setting = manifest.load(args.manifest)
    try:
        with evaluation.contained(setting.shared):
            evaluation.test_tasks(setting.shared, setting.extra["pinned"], "spreadsheetbench", chains.QUALIFICATION,
                                  run=setting.run, runtime=setting.runtime["spreadsheetbench"],
                                  native=setting.slots["spreadsheet-native"], workers=setting.workers)
    except Pause as pause:
        return {"no_qualified_test_items": chains.EXIT_NO_QUALIFIED,
                "qualification_paused": chains.EXIT_AWAITING}.get(pause.kind, chains.EXIT_PAUSED)
    return chains.EXIT_COMPLETE


def monitor(args):
    _, setting = manifest.load(args.manifest, verify=False)
    units = []
    for path in sorted(safe_path(setting.root).glob("*/s*/**/unit.json")):
        record = read_json(path, sealed=True)
        units.append({"unit": record.get("unit") or record["identity"]["unit"], "status": record["status"],
                      **({"counts": record["counts"]} if "counts" in record else {})})
    open_units = []
    for path in sorted(safe_path(setting.root).glob("*/s*/**/attempt-*")):
        if path.is_dir() and not (path.parent / "unit.json").exists():
            status = path / "status.json"
            open_units.append({"unit_root": str(path.parent), "attempt": path.name,
                               "status": read_json(status, sealed=True)["kind"] if status.exists() else "running"})
    print(json.dumps({"complete": units, "open": open_units, "ledger": setting.budget.snapshot()}, indent=1,
                     sort_keys=True))


def check_baselines(args):
    _, setting = manifest.load(args.manifest)
    _environment(setting)
    print(json.dumps(baseline.check(setting), indent=1, sort_keys=True))


def report(args):
    value, run_of = reports.of_manifest(args.manifest)
    out = Path(args.out).resolve()
    require(not out.exists(), "The report goes to a new directory")
    require(not out.is_relative_to(run_of.root.resolve()), "The report is never written into the run")
    built = reports.build(run_of, supply=reports.available(value) if "provenance" in value else None)
    try:  # the readings are registered (§12): a report from changed code says so
        manifest.verify_code(value)
        built["code"] = {"matches_manifest": True}
    except ValueError as error:
        built["code"] = {"matches_manifest": False, "detail": str(error)}
    out.mkdir(parents=True)
    write_json(out / "report.json", built)
    (out / "report.md").write_text(reports.markdown(built), encoding="utf-8")
    print(json.dumps({"report": str(out), "chains": built["chains"], "code": built["code"]}, ensure_ascii=False))


def qualify_train_sheet(args):
    record = prelaunch.qualify_training_sheet(data.pin(data.DEV_MACHINE),
                                              prelaunch.engine_runtime(args.engine_qualification), args.out)
    print(json.dumps(qualify.summary(record), sort_keys=True))


def build_archive(args):
    opened = prelaunch.build_archive(args.out, fetch=prelaunch.fetcher(args.proxy), previous=args.previous)
    print(json.dumps({"archive": str(opened.root), "documents": len(opened.texts), "index_sha256": opened.index_sha256}))


def prepare_texts(args):
    existing = dict(item.split("=", 1) for item in args.existing)
    require(len(existing) == len(args.existing), "One directory per bench")
    record = prelaunch.prepare_texts(args.out, existing, prelaunch.role_client(args.repo, args.proxy))
    print(json.dumps({"texts": str(Path(args.out) / "texts.json"), "missing": record["missing"]}))
    return 3 if record["missing"] else 0


def import_texts(args):
    record = prelaunch.import_texts(args.out, args.source)
    print(json.dumps({"texts": str(Path(args.out) / "texts.json"), "imported": record["imported"]}))


def smoke_make(args):
    record = smoke.make(args.out, texts_record=args.texts, archive=args.archive, repo=args.repo,
                        deepseek_env=args.deepseek_env, router_env=args.router_env, proxy=args.proxy,
                        research_proxy=args.research_proxy, workers=args.workers, chain_name=args.chain,
                        engine_qualification=args.engine_qualification, sheet_qualification=args.sheet_qualification,
                        draw={"searchqa": args.searchqa_items, "officeqa": args.officeqa_items})
    print(json.dumps({"smoke": str(Path(args.out) / prelaunch.SMOKE_RECORD), "run": record["record_hash"]}))


def smoke_run(args):
    found = smoke.run(args.spec)
    print(json.dumps({k: found.get(k) for k in ("status", "kind", "reason", "unit")}, ensure_ascii=False))
    return 0 if found["status"] == "complete" else 3


def smoke_summary(args):
    print(json.dumps(smoke.summary(read_json(args.spec, sealed=True)), indent=1, sort_keys=True, ensure_ascii=False))


def make_manifest(args):
    record = prelaunch.generate(
        args.out, root=args.root, sheet_qualification=args.sheet_qualification,
        engine_qualification=args.engine_qualification, texts_record=args.texts, smoke=args.smoke,
        archive=args.archive, baseline_protocol=args.baseline_protocol, repo=args.repo, deepseek_env=args.deepseek_env,
        router_env=args.router_env, gepa_source=args.gepa_source, proxy=args.proxy, research_proxy=args.research_proxy,
        workers=args.workers)
    print(json.dumps({"manifest": str(args.out), "run": record["record_hash"], "root": record["root"]}))


def consent(args):
    _, run_of = reports.of_manifest(args.manifest)
    print(json.dumps(prelaunch.record_consent(run_of.shared, date=args.date, note=args.note), ensure_ascii=False))


def recover(args):
    found = evaluation.attempts(args.unit_root)
    require(found and not (safe_path(args.unit_root) / "unit.json").exists(), "No paused or interrupted attempt")
    write_json(found[-1] / "recovery.json", {"by": "owner", "date": datetime.date.today().isoformat(),
                                             "decision": args.decision})
    print("recorded in", found[-1])


def terminate(args):
    _, setting = manifest.load(args.manifest, verify=False)
    chains.terminate(setting, args.chain, decision=args.decision)


def resume_ledger(args):
    _, setting = manifest.load(args.manifest, verify=False)
    setting.budget.resume(decision=args.decision)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "evaluate-unit", "qualify-test-sheet", "monitor", "check-baselines", "terminate",
                 "resume-ledger"):
        command = sub.add_parser(name)
        command.add_argument("--manifest", required=True)
        if name in ("run", "terminate"):
            command.add_argument("--chain", required=True, choices=sorted(CHAINS))
        if name == "evaluate-unit":
            command.add_argument("--spec", required=True)
        if name in ("terminate", "resume-ledger"):
            command.add_argument("--decision", required=True)
    command = sub.add_parser("qualify-train-sheet")
    command.add_argument("--engine-qualification", required=True)
    command.add_argument("--out", required=True)
    command = sub.add_parser("build-archive")
    command.add_argument("--out", required=True)
    command.add_argument("--proxy", default=GATEWAY)
    command.add_argument("--previous", required=True)  # v2 §8: v1's pages are carried, never refetched
    command = sub.add_parser("prepare-texts")
    command.add_argument("--out", required=True)
    command.add_argument("--repo", required=True)
    command.add_argument("--existing", action="append", required=True)
    command.add_argument("--proxy", default=GATEWAY)
    command = sub.add_parser("import-texts")
    command.add_argument("--out", required=True)
    command.add_argument("--source", required=True)
    command = sub.add_parser("smoke-make")
    for name in ("out", "texts", "archive", "repo", "deepseek-env"):
        command.add_argument("--" + name, required=True)
    command.add_argument("--router-env", default=None)
    command.add_argument("--engine-qualification", default=None)  # required while the format check covers
    command.add_argument("--sheet-qualification", default=None)  # SpreadsheetBench (smoke.make refuses otherwise)
    command.add_argument("--chain", default=smoke.CHAIN, choices=smoke.CHAINS)
    command.add_argument("--proxy", default=GATEWAY)
    command.add_argument("--research-proxy", default=GATEWAY)
    command.add_argument("--workers", type=int, default=16)
    command.add_argument("--searchqa-items", type=int, default=smoke.DRAW["searchqa"])
    command.add_argument("--officeqa-items", type=int, default=smoke.DRAW["officeqa"])
    for name in ("smoke", "smoke-summary"):
        sub.add_parser(name).add_argument("--spec", required=True)
    command = sub.add_parser("make-manifest")
    for name in ("out", "root", "sheet-qualification", "engine-qualification", "texts", "smoke", "archive",
                 "baseline-protocol", "repo", "deepseek-env", "gepa-source"):
        command.add_argument("--" + name, required=True)
    command.add_argument("--router-env", default=None)
    command.add_argument("--proxy", default=GATEWAY)
    command.add_argument("--research-proxy", default=GATEWAY)
    command.add_argument("--workers", type=int, default=16)
    command = sub.add_parser("consent")
    for name in ("manifest", "date", "note"):
        command.add_argument("--" + name, required=True)
    command = sub.add_parser("report")
    command.add_argument("--manifest", required=True)
    command.add_argument("--out", required=True)
    command = sub.add_parser("recover")
    command.add_argument("--unit-root", required=True)
    command.add_argument("--decision", required=True)
    args = parser.parse_args(argv)
    handler = {"run": run, "evaluate-unit": evaluate_unit, "qualify-test-sheet": qualify_test_sheet,
               "monitor": monitor, "check-baselines": check_baselines, "report": report, "recover": recover,
               "terminate": terminate, "resume-ledger": resume_ledger, "qualify-train-sheet": qualify_train_sheet,
               "build-archive": build_archive, "prepare-texts": prepare_texts, "import-texts": import_texts,
               "smoke-make": smoke_make,
               "smoke": smoke_run, "smoke-summary": smoke_summary, "make-manifest": make_manifest,
               "consent": consent}[args.command]
    code = handler(args)
    return code or 0


if __name__ == "__main__":
    sys.exit(main())
