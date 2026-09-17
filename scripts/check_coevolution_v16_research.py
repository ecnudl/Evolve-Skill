"""One separately registered quote-delivery diagnostic, never a pilot rerun.

Default action prepares only. --run authorizes at most one new logical model
request. Reuse byte-identical V15 document snapshots and development evidence;
only V16's whitespace presentation changes. No final data or calibration runs.
"""

# ruff: noqa: E402 -- standalone script bootstraps the repository import path.

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v5.core import seal, verify
from skillopt.coevolution_v9.study import OfflineAPI, closed_ledger, stable_api
from skillopt.coevolution_v15 import research as old_research
from skillopt.coevolution_v15 import study as old_study
from skillopt.coevolution_v15 import validator as old_validator
from skillopt.coevolution_v16 import research, study, validator
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "v16-one-shot-research-delivery-diagnostic-v1"
SOURCE_KEY = "h0-r0-adaptive_research"
DEFAULT_SOURCE = REPO / "outputs/coevolution_v15/smoke_20260915_a"
DEFAULT_OUTPUT = REPO / "outputs/coevolution_v16/research_delivery_20260915_a"


def forbidden(*args, **kwargs):
    raise RuntimeError("This diagnostic phase forbids API/network/native execution")


def read(path, *, sealed=True):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError("Required immutable nonsymlink evidence is missing")
    if path.stat().st_size > 20_000_000:
        raise ValueError("Oversized source evidence")
    value = json.loads(path.read_text(encoding="utf-8"))
    return verify(value) if sealed else value


def save(path, value, *, completed=False):
    row = seal(value)
    if Path(path).exists():
        if read(path) != row:
            raise ValueError("Registered diagnostic evidence changed")
    elif completed:
        raise ValueError("Completed diagnostic evidence missing; cannot repair")
    else:
        write_immutable_json(Path(path),row)
    return row


def tree(root):
    result = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink diagnostic evidence is forbidden")
        if path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


@contextmanager
def offline():
    with ExitStack() as stack:
        for target in ("socket.create_connection", "socket.socket", "subprocess.Popen",
                       "skillopt.coevolution_v15.runtime.legacy.evaluate",
                       "skillopt.coevolution_v15.research.fetch_sources",
                       "skillopt.validator_document_transport.fetch_sources"):
            stack.enter_context(patch(target,forbidden))
        stack.enter_context(patch.object(OfflineAPI,"call",forbidden))
        yield


def source_evidence(repo, source):
    """Verify only the closed, predetermined development request, never finals.

    The entire V15 smoke may still be running. Do not inspect its final outputs
    or demand closure of unrelated requests. Original proposal/receipt/intent,
    development seals, initial state, research bytes and frozen source do close.
    """
    source = old_study.safe_root(repo,source)
    protocol = read(source / "protocol.json")
    snapshot = read(source / "source_snapshot.json")
    if (protocol.get("version") != old_study.VERSION
            or protocol.get("design") != "smoke" or protocol.get("model") != "glm-5.3"
            or snapshot["record_hash"] != protocol["source_snapshot_hash"]
            or old_study.source_hashes(repo) != protocol["source_hashes"]
            or {k:hashlib.sha256(v.encode()).hexdigest() for k,v in snapshot["files"].items()} != protocol["source_hashes"]):
        raise ValueError("Source must be the unchanged, snapshotted V15 smoke protocol")
    candidates = []
    for path in sorted((source / "validator/proposals").glob("*.json")):
        row = read(path)
        if row.get("identity",{}).get("key") == SOURCE_KEY:
            candidates.append((path,row))
    if len(candidates) != 1:
        raise ValueError("Require the unique preregistered h0-r0 Research proposal")
    path, proposal = candidates[0]
    identity = proposal["identity"]
    if (proposal.get("arm") != "adaptive_research" or proposal.get("phase") != "development"
            or identity.get("phase") != "development" or identity.get("repeat") != 0
            or path.stem != digest(identity)):
        raise ValueError("Source proposal is not the fixed development position")
    receipt = read(source / "api/calls" / (proposal["request_hash"]+".json"),sealed=False)
    request = receipt["request"]
    if (digest(request) != proposal["request_hash"] or receipt.get("request_hash") != proposal["request_hash"]
            or digest(receipt) != proposal["receipt_hash"] or request.get("kind") != "v15_validator_proposal"
            or request.get("model") != "glm-5.3" or request.get("key") != digest(identity)
            or request.get("repeat") != 0):
        raise ValueError("Source actual model request/receipt binding differs")
    intent = read(source / "validator/request_intents" / (proposal["request_hash"]+".json"))
    if intent != seal({"version":old_validator.VERSION,"request_hash":proposal["request_hash"],"identity":identity}):
        raise ValueError("Source proposal intent differs")
    reservation = read(source / "api/budget_reservations" / (proposal["request_hash"]+".json"),sealed=False)
    if reservation != {"request_hash":proposal["request_hash"],"kind":request["kind"]}:
        raise ValueError("Source logical reservation differs")
    visible = json.loads(request["user"])
    initial = old_validator.initial_state()
    evidence = old_validator._development(visible["development_evidence"])
    if (visible["current_policy"] != {k:initial[k] for k in ("search_policy","when")}
            or proposal["parent_state_hash"] != initial["record_hash"]
            or identity["parent_hash"] != initial["record_hash"] or identity["evidence_hash"] != digest(evidence)
            or any(row.get("history") != 0 or row.get("round") != 0 for row in evidence)):
        raise ValueError("Source evidence must belong to initial h0-r0 development")
    with offline():
        replayed = old_validator.propose(OfflineAPI(source / "api"),initial,evidence,
            arm="adaptive_research",root=source,key=SOURCE_KEY,repeat=0,completed=True)
    if replayed != proposal:
        raise ValueError("Source proposal cannot be exactly reconstructed from its actual receipt")
    raw = old_research.retrieve(source,completed=True)
    if (visible["official_excerpts"] != raw["documents"] or visible["research_available"] != raw["available"]
            or proposal["research"] != raw or identity["research_hash"] != raw["record_hash"]):
        raise ValueError("Source actual excerpts differ from frozen document provenance")
    return {"source":str(source),"source_protocol_hash":protocol["record_hash"],
        "source_snapshot_hash":snapshot["record_hash"],"source_proposal_hash":proposal["record_hash"],
        "source_proposal_file":str(path.relative_to(source)),"source_request_hash":receipt["request_hash"],
        "source_receipt_hash":digest(receipt),"source_intent_hash":intent["record_hash"],
        "source_key":SOURCE_KEY,"state":initial,"development_evidence":evidence,
        "development_evidence_hash":digest(evidence),"raw_research_hash":raw["record_hash"],
        "raw_research_files":tree(source / "validator/research"),
        "old_delivery_valid":proposal["valid"],"old_delivery_error":proposal["error"],
        "source_is_closed_development_request_not_completed_run":True,
        "final_data_used":False}


def _copy_research(source, root, manifest, *, completed=False):
    source, target = Path(source) / "validator/research", Path(root) / "validator/research"
    if tree(source) != manifest:
        raise ValueError("Source research bytes changed")
    if set(tree(target)) - set(manifest):
        raise ValueError("Unexpected copied research evidence")
    for name, expected in manifest.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe research snapshot path")
        content, destination = (source / relative).read_bytes(),target / relative
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Source research file changed during copy")
        if destination.exists():
            if destination.read_bytes() != content:
                raise ValueError("Existing research copy differs; never overwrite")
        elif completed:
            raise ValueError("Completed research snapshot missing")
        else:
            destination.parent.mkdir(parents=True,exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(content)


@contextmanager
def locked(repo, root, *, create):
    root = study.safe_root(repo,root)
    path = root / ".run.lock"
    if create:
        root.mkdir(parents=True,exist_ok=True)
    elif not path.is_file():
        raise ValueError("Original diagnostic lock missing")
    with path.open("a+" if create else "rb") as handle:
        fcntl.flock(handle,fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield root


def _prepare(repo, source, root, *, completed=False):
    origin = source_evidence(repo,source)
    source_record = save(root / "source_development.json",{"version":VERSION,**origin},completed=completed)
    sources = study.source_hashes(repo)
    snapshot = save(root / "source_snapshot.json",{"version":VERSION,
        "files":{name:(Path(repo)/name).read_text(encoding="utf-8") for name in sources}},completed=completed)
    _copy_research(source,root,origin["raw_research_files"],completed=completed)
    with offline():
        presentation = research.retrieve(root,completed=completed)
    if presentation["raw_bundle_hash"] != origin["raw_research_hash"]:
        raise ValueError("V16 presentation did not reuse the exact original research bundle")
    if validator.initial_state() != origin["state"]:
        raise ValueError("Quote-only diagnostic cannot change initial policy state")
    protocol = save(root / "protocol.json",{"version":VERSION,"model":"glm-5.3","workers":4,
        "max_logical_calls":1,"http_min_interval_seconds":10,"max_http_attempts":3,
        "source_hashes":sources,"source_snapshot_hash":snapshot["record_hash"],
        "source_development_hash":source_record["record_hash"],"source":str(source),
        "source_proposal_hash":origin["source_proposal_hash"],"source_request_hash":origin["source_request_hash"],
        "initial_state_hash":origin["state"]["record_hash"],"development_evidence_hash":origin["development_evidence_hash"],
        "presentation_hash":presentation["record_hash"],"raw_research_hash":presentation["raw_bundle_hash"],
        "presentation_change":research.PROJECTION_VERSION,"new_document_http_requests":0,
        "historical_document_http_attempts_not_new_cost":True,
        "diagnostic_only":True,"calibration_calls":0,"native_executions":0,
        "final_data_used":False,"included_in_pilot_results":False,"scientific_efficacy_claim":False,
        "selection_rule":"unique_fixed_h0_r0_research_position_not_response_score",
        "terminal_policy":"preserve_every_result_no_retry_or_resampling"},completed=completed)
    return protocol,source_record


def prepare(repo, source, root):
    with locked(repo,root,create=True) as root:
        if (root / "results.json").exists():
            raise ValueError("Terminal diagnostic must use read-only replay")
        return _prepare(repo,source,root)[0]


def _result(root, protocol, proposal):
    ledger = closed_ledger(root,1)
    calls = list((root / "api/calls").glob("*.json"))
    intents = list((root / "validator/request_intents").glob("*.json"))
    proposals = list((root / "validator/proposals").glob("*.json"))
    if (len(calls) != 1 or calls[0].stem != proposal["request_hash"]
            or len(intents) != 1 or intents[0].stem != proposal["request_hash"]
            or len(proposals) != 1 or read(proposals[0]) != proposal
            or ledger["cached_logical_calls"] != 1):
        raise ValueError("One-call proposal/intent/budget closure differs")
    receipt = read(calls[0],sealed=False)
    if receipt["request"]["kind"] != "v16_validator_proposal" or digest(receipt) != proposal["receipt_hash"]:
        raise ValueError("Diagnostic result is not bound to its actual V16 receipt")
    citations_valid = None
    if receipt["ok"]:
        try:
            parsed = old_validator._strict(receipt["response"])
            research.validate_citations(parsed.get("citations"),proposal["research"],required=True)
            citations_valid = True
        except (ValueError,TypeError,KeyError,RecursionError):
            citations_valid = False
    return {"version":VERSION,"complete":True,"protocol_hash":protocol["record_hash"],
        "proposal_hash":proposal["record_hash"],"request_hash":proposal["request_hash"],
        "receipt_hash":proposal["receipt_hash"],"delivery_valid":proposal["valid"],"error":proposal["error"],
        "exact_citations_valid":citations_valid,"citation_count":len(proposal["citations"]),
        "candidate_activated":False,"calibrated":False,"api_ok":receipt["ok"],"ledger":ledger,
        "logical_calls":1,"new_document_http_requests":0,"native_executions":0,
        "included_in_pilot_results":False,"scientific_efficacy_claim":False,
        "one_draw_not_statistical_validation":True}


def _replay(repo, root):
    before = tree(root)
    saved = read(root / "results.json")
    protocol = read(root / "protocol.json")
    with offline():
        verified, origin = _prepare(repo,Path(protocol["source"]),root,completed=True)
        proposal = validator.propose(OfflineAPI(root / "api"),origin["state"],origin["development_evidence"],
            arm="adaptive_research",root=root,key=verified["record_hash"],repeat=0,completed=True)
        expected = seal(_result(root,verified,proposal))
    if saved != expected or tree(root) != before:
        raise ValueError("Read-only replay changed bytes or disagreed with terminal result")
    return saved


def replay(repo, root):
    with locked(repo,root,create=False) as root:
        return _replay(repo,root)


def run(repo, source, root, *, api_factory=None):
    root = study.safe_root(repo,root)
    if (root / "results.json").exists():
        return replay(repo,root)
    with locked(repo,root,create=True) as root:
        protocol,origin = _prepare(repo,source,root)
        if (any((root / "api/calls").glob("*.json"))
                or any((root / "api/budget_reservations").glob("*.json"))
                or any((root / "validator/request_intents").glob("*.json"))):
            raise ValueError("Incomplete one-shot admission; preserve evidence and do not retry")
        api = (api_factory or stable_api)(repo,root / "api",max_calls=1,workers=4)
        try:
            if api.model != "glm-5.3":
                raise ValueError("Diagnostic requires glm-5.3")
            proposal = validator.propose(api,origin["state"],origin["development_evidence"],
                arm="adaptive_research",root=root,key=protocol["record_hash"],repeat=0)
        finally:
            api.close()
        if study.source_hashes(repo) != protocol["source_hashes"]:
            raise ValueError("Frozen source changed during diagnostic; preserve evidence")
        result = save(root / "results.json",_result(root,protocol,proposal))
    if replay(repo,root) != result:
        raise ValueError("Diagnostic replay disagrees")
    return result


def status(repo, root):
    root = study.safe_root(repo,root)
    if not (root / "protocol.json").exists():
        return {"prepared":False,"model_api_calls":0,"output":str(root)}
    if (root / "results.json").exists():
        result = replay(repo,root)
        return {"prepared":True,"complete":True,"offline_verified":True,"model_api_calls":0,
            "result_hash":result["record_hash"],"delivery_valid":result["delivery_valid"],
            "exact_citations_valid":result["exact_citations_valid"],"error":result["error"]}
    protocol = read(root / "protocol.json")
    if study.source_hashes(repo) != protocol["source_hashes"]:
        raise ValueError("Frozen source drift")
    return {"prepared":True,"complete":False,"model_api_calls":0,"max_logical_calls":1,
        "admitted_requests":len(list((root / "validator/request_intents").glob("*.json"))),
        "actual_receipts":len(list((root / "api/calls").glob("*.json"))),
        "protocol_hash":protocol["record_hash"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=DEFAULT_SOURCE)
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--run",action="store_true")
    actions.add_argument("--status",action="store_true")
    actions.add_argument("--prepare-only",action="store_true")
    args = parser.parse_args(argv)
    root = study.safe_root(REPO,args.output)
    source = old_study.safe_root(REPO,args.source)
    if args.status or (root / "results.json").exists():
        result = status(REPO,root)
    elif args.run:
        result = run(REPO,source,root)
    else:
        result = {"prepared":True,"model_api_calls":0,"protocol_hash":prepare(REPO,source,root)["record_hash"]}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
