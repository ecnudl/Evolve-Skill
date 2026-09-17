"""One-request diagnostic with synthetic persisted receipts; no live services."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts import check_coevolution_v16_research as s
from skillopt.coevolution_v9 import study as transport


def put(path,value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False),encoding="utf-8")


class FakeAPI:
    model = "glm-5.3"
    service = {"synthetic":True,"max_retries":2}

    def __init__(self,root,state,max_calls):
        self.root,self.state = Path(root),state
        state["constructors"] += 1
        put(self.root / "service.json",self.service)
        put(self.root / "budget_protocol.json",{"model":self.model,"workers":4,
            "max_logical_calls":max_calls,"service_sha256":s.digest(self.service)})

    def call(self,**arguments):
        self.state["calls"] += 1
        assert self.state["calls"] == 1
        request = {**arguments,"model":self.model,"service":self.service}
        visible = json.loads(arguments["user"])
        item = visible["official_excerpts"][0]
        quote = "This quote was never supplied." if self.state.get("bad_quote") else item["text"][:32]
        response = json.dumps({"search_policy":"Check signed, zero and dependency interactions.",
            "when":"Only inside the declared input schema.","citations":[{"url":item["url"],"quote":quote}]})
        ok = not self.state.get("api_unknown")
        receipt = {"request":request,"request_hash":s.digest(request),"ok":ok,
            "response":response if ok else "","finish_reason":"stop" if ok else None,
            "http_attempt_count":1,"usage":{"total_tokens":1}}
        put(self.root / "budget_reservations" / (receipt["request_hash"]+".json"),
            {"request_hash":receipt["request_hash"],"kind":arguments["kind"]})
        put(self.root / "calls" / (receipt["request_hash"]+".json"),receipt)
        return receipt

    def close(self):
        self.state["closed"] += 1


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    repo = tmp_path
    source = repo / "outputs/coevolution_v15/source"
    output = repo / "outputs/coevolution_v16/diagnostic"
    source_file = repo / "frozen.py"
    source_file.write_text("# immutable source fixture\n")
    def hashes(repo):
        return {"frozen.py":hashlib.sha256(source_file.read_bytes()).hexdigest()}
    monkeypatch.setattr(s.old_study,"source_hashes",hashes)
    monkeypatch.setattr(s.study,"source_hashes",hashes)
    monkeypatch.setattr(transport,"audit_pacing",lambda *a:{"offline_synthetic_pacing":True})
    snapshot = s.save(source / "source_snapshot.json",{"files":{"frozen.py":source_file.read_text()}})
    s.save(source / "protocol.json",{"version":s.old_study.VERSION,"design":"smoke","model":"glm-5.3",
        "source_snapshot_hash":snapshot["record_hash"],"source_hashes":hashes(repo)})
    old_state = {"calls":0,"constructors":0,"closed":0,"bad_quote":True}
    api = FakeAPI(source / "api",old_state,192)

    def fetch(urls,root):
        text = "Public   semantics are\n explained with bounded conditional expressions and comparisons."
        rows = [{"requested_url":url,"ok":True,"text":text,"text_sha256":hashlib.sha256(text.encode()).hexdigest()}
                for url in urls]
        for i,row in enumerate(rows):
            put(root / (str(i)+".json"),row)
        return rows

    monkeypatch.setattr(s.old_research,"fetch_sources",fetch)
    evidence = [s.seal({"phase":"development","history":0,"round":0,
        "observations":[],"probes":[],"public_tasks":[],"skill_update_hash":"a"*64})]
    s.old_validator.propose(api,s.old_validator.initial_state(),evidence,
        arm="adaptive_research",root=source,key=s.SOURCE_KEY)
    state = {"calls":0,"constructors":0,"closed":0}

    def factory(repo,root,*,max_calls,workers):
        assert max_calls == 1 and workers == 4
        return FakeAPI(root,state,max_calls)

    monkeypatch.setattr(s,"stable_api",factory)
    monkeypatch.setattr(s.old_research,"fetch_sources",s.forbidden)
    return repo,source,output,state,factory,source_file


def test_prepare_exact_documents_no_model_or_document_requests(fixture):
    repo,source,output,state,_,_ = fixture
    before = s.tree(source)
    protocol = s.prepare(repo,source,output)
    assert state["calls"] == state["constructors"] == 0
    assert protocol["max_logical_calls"] == 1 and protocol["new_document_http_requests"] == 0
    assert protocol["included_in_pilot_results"] is False
    assert not (output / "api").exists() and s.tree(source) == before
    assert s.tree(source / "validator/research") == s.tree(output / "validator/research")
    raw = s.old_research.retrieve(source,completed=True)
    normalized = s.research.retrieve(output,completed=True)
    assert normalized["raw_bundle_hash"] == raw["record_hash"]
    assert normalized["documents"][0]["text"] == " ".join(raw["documents"][0]["text"].split())
    assert normalized["raw_documents"] == raw["documents"]
    new_before = s.tree(output)
    assert s.prepare(repo,source,output) == protocol and s.tree(output) == new_before


@pytest.mark.parametrize("failure,expected",[(None,True),("bad_quote",False),("api_unknown",None)])
def test_one_call_terminal_outcomes_and_zero_activity_replay(fixture,monkeypatch,failure,expected):
    repo,source,output,state,factory,_ = fixture
    if failure:
        state[failure] = True
    before = s.tree(source)
    result = s.run(repo,source,output,api_factory=factory)
    assert state["calls"] == state["constructors"] == state["closed"] == 1
    assert result["exact_citations_valid"] is expected
    assert result["candidate_activated"] is False and result["calibrated"] is False
    assert result["logical_calls"] == 1 and s.tree(source) == before
    new_before = s.tree(output)
    monkeypatch.setattr(s,"stable_api",s.forbidden)
    assert s.run(repo,source,output,api_factory=s.forbidden) == result
    assert s.status(repo,output)["offline_verified"] is True
    assert s.tree(output) == new_before and s.tree(source) == before


def test_same_development_state_system_only_excerpt_presentation_changes(fixture):
    repo,source,output,_,factory,_ = fixture
    result = s.run(repo,source,output,api_factory=factory)
    origin = s.source_evidence(repo,source)
    old = s.read(source / "api/calls" / (origin["source_request_hash"]+".json"),sealed=False)["request"]
    new = s.read(output / "api/calls" / (result["request_hash"]+".json"),sealed=False)["request"]
    before,after = json.loads(old["user"]),json.loads(new["user"])
    assert old["system"] == new["system"] and old["max_tokens"] == new["max_tokens"]
    assert before["current_policy"] == after["current_policy"]
    assert before["development_evidence"] == after["development_evidence"]
    assert before["official_excerpts"] != after["official_excerpts"]


@pytest.mark.parametrize("what",["receipt","intent","reservation","source_snapshot","proposal"])
def test_missing_or_tampered_source_fails_before_api(fixture,what):
    repo,source,output,state,_,_ = fixture
    origin = s.source_evidence(repo,source)
    path = {"receipt":source / "api/calls" / (origin["source_request_hash"]+".json"),
        "intent":source / "validator/request_intents" / (origin["source_request_hash"]+".json"),
        "reservation":source / "api/budget_reservations" / (origin["source_request_hash"]+".json"),
        "source_snapshot":source / "source_snapshot.json",
        "proposal":source / origin["source_proposal_file"]}[what]
    if what == "receipt":
        row = s.read(path,sealed=False)
        row["response"] += "tampered"
        put(path,row)
    else:
        path.unlink()
    with pytest.raises(ValueError):
        s.prepare(repo,source,output)
    assert state["calls"] == state["constructors"] == 0


def test_completed_missing_snapshot_never_refetched(fixture):
    repo,source,output,state,factory,_ = fixture
    s.run(repo,source,output,api_factory=factory)
    next((output / "validator/research/snapshots").glob("*.json")).unlink()
    before = s.tree(output)
    with pytest.raises(ValueError):
        s.replay(repo,output)
    assert s.tree(output) == before and state["calls"] == 1


def test_source_drift_stops_before_client(fixture):
    repo,source,output,state,_,source_file = fixture
    s.prepare(repo,source,output)
    source_file.write_text("# changed code\n")
    with pytest.raises(ValueError):
        s.run(repo,source,output)
    assert state["constructors"] == 0


def test_unresolved_intent_never_resamples(fixture):
    repo,source,output,state,_,_ = fixture
    s.prepare(repo,source,output)
    s.save(output / "validator/request_intents" / ("f"*64+".json"),{"unfinished":True})
    with pytest.raises(ValueError,match="one-shot"):
        s.run(repo,source,output)
    assert state["constructors"] == 0


@pytest.mark.parametrize("target",["results.json","protocol.json","source_development.json"])
def test_completed_resealed_tampering_rejected(fixture,target):
    repo,source,output,_,factory,_ = fixture
    s.run(repo,source,output,api_factory=factory)
    value = s.read(output / target)
    value["scientific_efficacy_claim"] = True
    put(output / target,s.seal({k:v for k,v in value.items() if k != "record_hash"}))
    with pytest.raises(ValueError):
        s.replay(repo,output)


def test_unprepared_status_no_writes_and_unsafe_root_rejected(fixture):
    repo,source,output,state,_,_ = fixture
    assert s.status(repo,output)["prepared"] is False
    assert not output.exists() and state["constructors"] == 0
    output.parent.mkdir(parents=True)
    output.symlink_to(source,target_is_directory=True)
    with pytest.raises(ValueError):
        s.prepare(repo,source,output)
    with pytest.raises(ValueError):
        s.status(repo,repo / "outputs/coevolution_v15/not-v16")


def test_cli_default_prepare_and_explicit_run(fixture,monkeypatch,capsys):
    repo,source,output,state,_,_ = fixture
    monkeypatch.setattr(s,"REPO",repo)
    args = ["--source",str(source),"--output",str(output)]
    assert s.main(args) == 0
    assert json.loads(capsys.readouterr().out)["model_api_calls"] == 0 and state["calls"] == 0
    assert s.main(args+["--run"]) == 0
    assert json.loads(capsys.readouterr().out)["logical_calls"] == 1
    before = s.tree(output)
    assert s.main(args+["--run"]) == 0
    assert json.loads(capsys.readouterr().out)["offline_verified"] is True
    assert s.tree(output) == before and state["calls"] == 1
