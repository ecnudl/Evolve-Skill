"""Chain D's second provider (registrar "Owner instructions 2026-10-22 17:0x and 17:3x", row "deepseek route B";
builder M4): route B's client (the registered body under its own model id, the PJLAB gateway, the credential checks,
its echo set, the same reasoning check, the route on every receipt), balance exhaustion on both routes (never retried,
a ``balance_exhausted`` stop through the frozen Endpoint and the cell loop; an ordinary rate limit keeps the frozen
retries), the per-chain route history (write-once, chained, verified), the per-process binding (a unit never switches
mid-unit), the route-B manifest pin, the ``switch-route`` command line and its refusals, the route in cells and
receipts, and route B's own first-call confirmation. Offline: mock transports and fake credential files under
tmp_path; no network, and no real credential file is read."""
from __future__ import annotations

import json
import os
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from scripts import run_execskill as cli
from scripts import weak_solver_probe as probe
from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.cells import exclusive
from skillopt.continual_eval.core import read_json, safe_path, write_json
from skillopt.execskill import chain, client, errors, evaluation, manifest, protocol, routes
from skillopt.execskill.cells import Arm, Context, Pause, TrainingStore, run_cell
from skillopt.execskill.client import ELUCID_MODEL, NORTHGATE_MODEL
from skillopt.execskill.errors import BalanceExhausted, ConfigurationError, stop_kind
from skillopt.execskill.package import empty
from skillopt.execskill.protocol import (BENCHES, ELUCID_MAX_TOKENS, ELUCID_READ_TIMEOUT, FIRST_CALL_BENCH,
                                         RECORD_HASH, verified)
from tests import execskill_fakes as fakes
from tests.execskill_fakes import QA_MAX_TOKENS, QA_READ_TIMEOUT, FakeSolver, fake_config, tagged, with_first_call
from tests.execskill_fakes_env import FakeSandbox
from tests.fixtures.execskill.items import searchqa_items
from tests.test_execskill_cells import CARD, RUNTIMES, _cell
from tests.test_execskill_chain import Launch, Learn
from tests.test_execskill_chain import setting as chain_setting
from tests.test_execskill_manifest import MEASURED, NO_CALLS, FakeDockerCLI, fake_environment, given, run_given

EVIDENCE = "engineering_fixture"
RUN = "fixture-run"
M = QA_MAX_TOKENS
NORTHGATE_URL = "https://%s%s" % (client.NORTHGATE_HOST, client.NORTHGATE_PATH)
NORTHGATE_KEY = "fake-northgate-key-0000"
QUOTA = {"error": {"code": "insufficient_quota", "message": "fake: you exceeded your current quota"}}
RATE_LIMIT = {"error": {"code": "rate_limit_exceeded", "message": "fake: slow down"}}


def northgate_env(root, *, url=NORTHGATE_URL, key=NORTHGATE_KEY):
    """A fake route-B credential file under ``root`` (None leaves that variable out)."""
    path = safe_path(root) / "fake-credentials" / "northgate.env"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (["NORTHGATE_CHAT_URL=" + url] if url is not None else []) + (
        ["NORTHGATE_API_KEY=" + key] if key is not None else [])
    path.write_text("".join(line + "\n" for line in lines))
    return path


def route_b_config(root, **changes):
    return {client.ROUTE_KEY: client.ROUTE_B, "env_path": str(northgate_env(root)), "proxy": probe.GATEWAY,
            "max_tokens": M, "read_timeout": QA_READ_TIMEOUT, **changes}


def completion(text=tagged("4"), *, model=NORTHGATE_MODEL, tokens=None, reasoning=None):
    """(200, a chat-completions body) of a reply echoing ``model``."""
    message = {"role": "assistant", "content": text}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    body = {"id": "chatcmpl-fake", "object": "chat.completion", "model": model, "usage": fakes.usage(5),
            "choices": [{"index": 0, "finish_reason": "stop", "message": message}]}
    if tokens is not None:
        body["usage"]["completion_tokens_details"] = {"reasoning_tokens": tokens}
    return 200, body


def as_bytes(body, *, ascii_only=True):
    return json.dumps(body, ensure_ascii=ascii_only).encode("utf-8")


class Gateway:
    """A scripted provider: ``answers`` are (status, body) pairs used in order, the last one repeated; a dict body is
    sent as JSON, bytes as they are. Every request is kept."""

    def __init__(self, *answers):
        self.answers, self.requests = list(answers), []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request):
        self.requests.append(request)
        status, body = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return httpx.Response(status, content=body) if isinstance(body, bytes) else httpx.Response(status, json=body)

    @property
    def bodies(self):
        return [json.loads(request.content) for request in self.requests]


def route_b(tmp_path, gateway, **changes):
    return client.solver_client(ELUCID_MODEL, config=route_b_config(tmp_path, **changes), transport=gateway.transport)


def route_a(tmp_path, gateway):
    return client.solver_client(ELUCID_MODEL, config=fake_config(tmp_path, ELUCID_MODEL), transport=gateway.transport)


def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(probe.time, "sleep", slept.append)
    return slept


def paused_attempt(chain_root, kind, *, unit="s2-officeqa/run", at=1_000):
    """A paused attempt as ``units.run_unit`` leaves it (``unit-status``), written at time ``at``."""
    attempt = safe_path(chain_root) / unit / "attempt-1"
    attempt.mkdir(parents=True, exist_ok=True)
    status = attempt / "status.json"
    write_json(status, protocol.record("unit-status", EVIDENCE, {"status": "paused", "kind": kind,
                                                                 "reason": "fixture", "cell": None}))
    os.utime(status, ns=(at * 10 ** 9, at * 10 ** 9))
    return attempt


def routed_manifest(tmp_path, monkeypatch, *, pin=True):
    """A pilot manifest (``run_given``) whose clients block pins chain D's route B unless ``pin`` is False."""
    values = run_given(tmp_path, monkeypatch, root=tmp_path / "run")
    clients = values["clients"]
    if pin:
        clients = {**clients, "routes": {"D": {"B": routes.pin("D", "B", env_path=northgate_env(tmp_path),
                                                               solver_block=clients["solver"]["D"])}}}
    out = tmp_path / "manifest.json"
    return manifest.make(out, evidence=EVIDENCE, environment_found=fake_environment(), measured=MEASURED,
                         **{**values, "clients": clients}), out


# ---------------------------------------------------------------------------------------------- route B's client
def test_route_b_sends_the_registered_body_under_its_model_id_and_names_its_route(tmp_path):
    gateway = Gateway(completion())
    solver = route_b(tmp_path, gateway)
    assert type(solver) is client.NorthgateClient and solver.model == ELUCID_MODEL  # chain D's solver slot
    assert (solver.route, solver.request_model, solver.max_tokens) == ("B", NORTHGATE_MODEL, M)
    receipt = solver.call("system text", "user text")
    (request,) = gateway.requests
    assert str(request.url) == NORTHGATE_URL and request.headers["authorization"] == "Bearer " + NORTHGATE_KEY
    assert "x-session-id" not in request.headers
    assert gateway.bodies == [{"model": NORTHGATE_MODEL, "max_tokens": M, "temperature": 0, "reasoning_effort": "none",
                               "messages": [{"role": "system", "content": "system text"},
                                            {"role": "user", "content": "user text"}]}]
    assert receipt["ok"] is True and (receipt["route"], receipt["route_model"]) == ("B", NORTHGATE_MODEL)
    assert (receipt["reasoning_tokens"], receipt["over_nominal"]) == (None, False)
    a = FakeSolver(tmp_path / "a", [(None, tagged("4"))]).call("sys", "user")  # route A: its own model id
    assert a["ok"] is True and (a["route"], a["route_model"]) == ("A", ELUCID_MODEL)
    assert client.route_of(solver) == {"route": "B", "model": NORTHGATE_MODEL}
    assert client.route_of(SimpleNamespace(model="glm-5.3")) == {"route": None, "model": "glm-5.3"}


def test_route_b_goes_through_the_pjlab_gateway_only_and_ignores_the_environment(tmp_path, monkeypatch):
    made, original = [], httpx.Client

    class Recording(original):
        def __init__(self, **kwargs):
            made.append(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(httpx, "Client", Recording)
    monkeypatch.setenv("HTTPS_PROXY", "http://elsewhere.example:3128")
    config = route_b_config(tmp_path)
    solver = client.solver_client(ELUCID_MODEL, config=config)
    (kwargs,) = made
    assert (kwargs["proxy"], kwargs["trust_env"], kwargs["follow_redirects"]) == (probe.GATEWAY, False, False)
    assert "transport" not in kwargs and kwargs["timeout"].read == QA_READ_TIMEOUT and solver.http.trust_env is False
    for proxy in (None, "http://elsewhere.example:3128", probe.GATEWAY + "/"):
        with pytest.raises(ConfigurationError, match="gateway"):
            client.solver_client(ELUCID_MODEL, config={**config, "proxy": proxy})
    assert len(made) == 1


@pytest.mark.parametrize("echo, ok", [(NORTHGATE_MODEL, True), ("deepseek-flash", True), (ELUCID_MODEL, False),
                                      ("glm-5.3", False)])
def test_route_b_takes_only_its_registered_echo_set(tmp_path, echo, ok):
    receipt = route_b(tmp_path, Gateway(completion(model=echo))).call("sys", "user")
    assert receipt["ok"] is ok and (ok or receipt["error_type"] == "model_mismatch")
    assert client.ROUTES["B"].response_model_ids == frozenset({NORTHGATE_MODEL, "deepseek-flash"})


@pytest.mark.parametrize("answer", [completion(tokens=7), completion(reasoning="Let me think."),
                                    completion(tokens="x")],
                         ids=["tokens", "text", "invalid-count"])
def test_route_b_gets_the_same_reasoning_check(tmp_path, answer):
    receipt = route_b(tmp_path, Gateway(answer)).call("sys", "user")
    assert (receipt["ok"], receipt["error_type"], receipt["subtype"]) == (
        False, client.THINKING_MISMATCH, client.REASONING_MISMATCH)


@pytest.mark.parametrize("url, key", [
    ("https://api.example.com/v1/chat/completions", NORTHGATE_KEY),
    ("http://%s%s" % (client.NORTHGATE_HOST, client.NORTHGATE_PATH), NORTHGATE_KEY),
    ("https://%s/v2/chat/completions" % client.NORTHGATE_HOST, NORTHGATE_KEY),
    (NORTHGATE_URL + "?key=" + NORTHGATE_KEY, NORTHGATE_KEY),
    ("https://user:%s@%s%s" % (NORTHGATE_KEY, client.NORTHGATE_HOST, client.NORTHGATE_PATH), NORTHGATE_KEY),
    ("https://%s%s" % (client.ELUCID_HOST, client.ELUCID_PATH), NORTHGATE_KEY),  # route A's endpoint
    (NORTHGATE_URL, None),
    (None, NORTHGATE_KEY),
])
def test_route_b_credentials_are_refused_unless_registered_and_the_key_never_shows(tmp_path, capsys, url, key):
    config = {**route_b_config(tmp_path), "env_path": str(northgate_env(tmp_path, url=url, key=key))}
    with pytest.raises(ConfigurationError) as refusal:
        client.solver_client(ELUCID_MODEL, config=config)
    out = capsys.readouterr()
    assert NORTHGATE_KEY not in str(refusal.value) + out.out + out.err


def test_route_b_needs_a_real_credential_file_and_chain_d_a_known_route(tmp_path):
    for path in (tmp_path / "missing.env", tmp_path):
        with pytest.raises(ConfigurationError, match="northgate credential file"):
            client.solver_client(ELUCID_MODEL, config=route_b_config(tmp_path, env_path=str(path)))
    elucid = fake_config(tmp_path, ELUCID_MODEL)  # route A's file names no NORTHGATE_* variable
    with pytest.raises(ConfigurationError, match="NORTHGATE_CHAT_URL"):
        client.solver_client(ELUCID_MODEL, config=route_b_config(tmp_path, env_path=elucid["env_path"]))
    with pytest.raises(ConfigurationError, match="Not a route of chain D"):
        client.solver_client(ELUCID_MODEL, config=route_b_config(tmp_path, route="C"))
    with pytest.raises(ConfigurationError, match="holds exactly"):
        client.solver_client(client.GLM_SOLVER, config={**fake_config(tmp_path, client.GLM_SOLVER), "route": "B"})


# ------------------------------------------------------------------------------------------- balance exhaustion
@pytest.mark.parametrize("status, content, signal", [
    (429, as_bytes(QUOTA), "http_429:insufficient_quota"),  # route B's documented signal
    (402, as_bytes({"error": {"message": "Payment Required"}}), "http_402"),
    (402, b"", "http_402"),
    (403, as_bytes({"error": {"message": "账户余额不足"}}, ascii_only=False), "http_403:balance_text"),
    (403, as_bytes({"error": {"message": "账户余额不足"}}), "http_403:balance_text"),  # escaped in the JSON
    (429, as_bytes({"error": {"message": "Insufficient balance, please top up"}}), "http_429:balance_text"),
    (429, b"<html>insufficient account balance</html>", "http_429:balance_text"),
    (403, as_bytes({"error": {"message": "Your credit balance is too low"}}), "http_403:balance_text"),
    (403, as_bytes({"error": {"code": "insufficient_quota"}}), "http_403:balance_text"),
    (429, as_bytes(RATE_LIMIT), None),  # an ordinary rate limit
    (429, b"", None),
    (403, as_bytes({"error": {"message": "Forbidden: invalid token"}}), None),
    (401, as_bytes(QUOTA), None),
    (500, as_bytes({"error": {"message": "insufficient balance"}}), None),
    (200, as_bytes(QUOTA), None),
])
def test_the_balance_signals_of_both_routes(status, content, signal):
    assert client.balance_signal(status, content) == signal


def test_route_b_balance_exhaustion_is_raised_at_once_never_retried_and_nothing_is_sent_after(tmp_path, monkeypatch):
    slept = no_sleep(monkeypatch)
    secret = "fake-body-text-never-shown"
    gateway = Gateway((429, {"error": {"code": "insufficient_quota", "message": secret}}), completion())
    solver = route_b(tmp_path, gateway)
    with pytest.raises(BalanceExhausted) as stop:
        solver.call("sys", "user")
    assert len(gateway.requests) == 1 and slept == [] and solver.exhausted == "http_429:insufficient_quota"
    assert stop_kind(stop.value) == "balance_exhausted" and "http_429:insufficient_quota" in str(stop.value)
    assert secret not in str(stop.value)
    with pytest.raises(BalanceExhausted):
        solver.call("sys", "user")  # the client sends nothing once its route reported an exhausted balance
    assert len(gateway.requests) == 1


@pytest.mark.parametrize("status, content", [
    (402, as_bytes({"error": {"message": "fake"}})),
    (403, as_bytes({"error": {"message": "账户余额不足"}})),
    (429, as_bytes({"error": {"message": "insufficient account balance"}})),
    (429, as_bytes(QUOTA)),
], ids=["402", "403-balance-zh", "429-balance-text", "429-insufficient-quota"])
def test_route_a_balance_exhaustion_follows_the_documented_heuristics(tmp_path, monkeypatch, status, content):
    slept = no_sleep(monkeypatch)
    gateway = Gateway((status, content))
    with pytest.raises(BalanceExhausted, match="route A"):
        route_a(tmp_path, gateway).call("sys", "user")
    assert len(gateway.requests) == 1 and slept == []


@pytest.mark.parametrize("route", ["A", "B"])
def test_an_ordinary_rate_limit_or_refusal_keeps_the_frozen_behaviour_on_both_routes(tmp_path, monkeypatch, route):
    slept = no_sleep(monkeypatch)
    build = route_a if route == "A" else route_b
    gateway = Gateway((429, RATE_LIMIT))
    solver = build(tmp_path, gateway)
    receipt = solver.call("sys", "user")
    assert (receipt["ok"], receipt["error_type"], receipt["route"]) == (False, "http_429", route)
    assert len(gateway.requests) == len(receipt["attempts"]) == 4 and slept == list(probe.RATE_BACKOFF)
    assert solver.exhausted is None
    refused = build(tmp_path / "403", Gateway((403, {"error": {"message": "Forbidden"}}))).call("sys", "user")
    assert refused["error_type"] == "http_403"


def _cell_context(tmp_path, solver):
    endpoint = Endpoint(solver, model=solver.model, max_tokens=4 * M, slots=Slots(tmp_path / "slots", solver.model, 2),
                        sleep=lambda _: None)
    return Context(attempt=tmp_path / "unit" / "attempt-1", endpoint=endpoint, runtime=RUNTIMES,
                   cards={bench: CARD for bench in BENCHES}, native=Slots(tmp_path / "slots", "spreadsheet-native", 1),
                   episodes=Slots(tmp_path / "slots", "alfworld-episode", 1), worker=lambda bench: FakeSandbox(),
                   evidence=EVIDENCE)


def test_a_cell_records_its_solver_route_and_balance_exhaustion_stops_it_with_its_own_kind(tmp_path, monkeypatch):
    no_sleep(monkeypatch)
    item = searchqa_items(1)[0]
    cell, arm = _cell(item, arm="C", unit="D/s1-searchqa/run"), Arm("card", empty(step="s0", evidence=EVIDENCE))
    answered = Gateway(completion("<answer>Fixtown 0</answer>"))
    context = _cell_context(tmp_path / "ok", route_b(tmp_path / "ok", answered))
    record = run_cell(context, cell, item, arm, store=TrainingStore(context.attempt))
    assert record["stop"] is None and record["final"]["token"] == "pass"
    assert record["solver_route"] == {"route": "B", "model": NORTHGATE_MODEL}
    sealed = evaluation.sealed_cell(read_json(context.attempt / "cells" / (cell["id"] + ".json")))
    assert sealed["solver_route"] == record["solver_route"]  # the test read's sealed cell keeps the route (M4)
    assert (record["sends"][0]["receipt"]["route"], record["sends"][0]["receipt"]["route_model"]) == (
        "B", NORTHGATE_MODEL)
    gateway = Gateway((429, QUOTA))
    context = _cell_context(tmp_path / "out", route_b(tmp_path / "out", gateway))
    with pytest.raises(Pause) as stop:
        run_cell(context, cell, item, arm, store=TrainingStore(context.attempt))
    assert stop.value.kind == "balance_exhausted" == errors.STOP_KINDS[BalanceExhausted] == routes.BALANCE_EXHAUSTED
    stored = verified(read_json(context.attempt / "cells" / (cell["id"] + ".json")), "cell")
    assert stored["stop"]["kind"] == "balance_exhausted" and stored["final"] is None
    assert stored["solver_route"] == {"route": "B", "model": NORTHGATE_MODEL}
    assert [send.get("exception") for send in stored["sends"]] == ["BalanceExhausted"]
    assert len(gateway.requests) == 1  # never retried, never re-sent


# --------------------------------------------------------------------------------------------- the route history
def test_the_route_history_is_write_once_chained_verified_and_one_pause_motivates_one_switch(tmp_path):
    root = tmp_path / "root" / "D"
    root.mkdir(parents=True)
    assert routes.history(root, run=RUN) == [] and routes.current(root, run=RUN) == "A"
    attempt = paused_attempt(root, "balance_exhausted")
    one = routes.switch(root, to="B", run=RUN, evidence=EVIDENCE)
    value = one["record"]
    assert one["path"] == root / "route-1.json" and one["pause"] == attempt
    assert (value["n"], value["from"], value["to"], value["model"], value["previous"]) == (1, "A", "B", NORTHGATE_MODEL,
                                                                                           None)
    assert (value["by"], value["reason"], value["run"], value["chain"]) == ("operator", None, RUN, "D")
    assert value["pause"] == {"attempt": "s2-officeqa/run/attempt-1", "kind": "balance_exhausted",
                              "status_sha256": read_json(attempt / "status.json")[RECORD_HASH]}
    assert routes.current(root, run=RUN) == "B"
    with pytest.raises(ValueError, match="answered by a route record"):  # the same pause, no second switch
        routes.switch(root, to="A", run=RUN, evidence=EVIDENCE)
    with pytest.raises(ValueError, match="already runs on route B"):
        routes.switch(root, to="B", run=RUN, evidence=EVIDENCE, reason="again")
    with pytest.raises(ValueError, match="non-blank"):
        routes.switch(root, to="A", run=RUN, evidence=EVIDENCE, reason="  ")
    with pytest.raises(ValueError, match="not a route of chain D"):
        routes.switch(root, to="C", run=RUN, evidence=EVIDENCE, reason="x")
    two = routes.switch(root, to="A", run=RUN, evidence=EVIDENCE, reason="fixture: route A was topped up")
    assert (two["record"]["n"], two["record"]["previous"]) == (2, value[RECORD_HASH])
    assert [found["to"] for found in routes.history(root, run=RUN)] == ["B", "A"] and routes.current(root) == "A"
    with pytest.raises(ValueError, match="another run"):
        routes.current(root, run="another-run")
    with pytest.raises(ValueError):  # write-once
        write_json(one["path"], {**value, "reason": "rewritten"})
    with pytest.raises(ValueError, match="one route"):
        routes.history(root, chain="G")
    gap = tmp_path / "gap" / "D"
    gap.mkdir(parents=True)
    write_json(gap / "route-2.json", two["record"])
    with pytest.raises(ValueError, match="gap"):
        routes.current(gap)
    alone = tmp_path / "alone" / "D"  # record 2 alone as record 1: it leaves B, which the chain never took
    alone.mkdir(parents=True)
    write_json(alone / "route-1.json", two["record"])
    with pytest.raises(ValueError, match="does not follow"):
        routes.current(alone)
    tampered = tmp_path / "tampered" / "D"
    tampered.mkdir(parents=True)
    write_json(tampered / "route-1.json", {**value, "to": "A"})
    with pytest.raises(ValueError):
        routes.current(tampered)
    assert routes.RUNNER_LOCK == chain.RUNNER_LOCK


# ---------------------------------------------------------------------------- the binding per process and unit
def test_setting_of_binds_the_route_per_process_and_a_unit_never_switches_mid_run(tmp_path, monkeypatch):
    m, _ = routed_manifest(tmp_path, monkeypatch)
    docker, chain_root = FakeDockerCLI(), safe_path(m["root"]) / "D"
    a = manifest.setting_of(m, "D", docker=docker, transport=NO_CALLS)
    assert a.extra["route"] == "A" and (a.branch, a.longest) == ("E", None)
    first = a.clients(ELUCID_MODEL, "officeqa")
    assert type(first) is client.ElucidClient and a.clients(ELUCID_MODEL, "officeqa") is first
    chain_root.mkdir(parents=True, exist_ok=True)
    routes.switch(chain_root, to="B", run=m[RECORD_HASH], evidence=m["evidence"], reason="fixture: drill")
    with pytest.raises(ConfigurationError, match="new process"):  # the process on route A: refused at a unit start
        a.clients(ELUCID_MODEL, "officeqa")
    assert a.clients(protocol.ROLE_MODEL, None).model == "glm-5.3"  # the roles never depend on the route
    b = manifest.setting_of(m, "D", docker=docker, transport=NO_CALLS)  # the next process runs on route B
    pin = m["clients"]["routes"]["D"]["B"]
    assert b.extra["route"] == "B" and (b.branch, b.longest) == ("N", pin["longest"]) == ("N", routes.S1B_CEILING)
    solver = b.clients(ELUCID_MODEL, "officeqa")
    assert type(solver) is client.NorthgateClient and solver.model == ELUCID_MODEL and solver.max_tokens == 8_192
    assert solver.url == NORTHGATE_URL and solver.http.timeout.read == pin["read_timeout"]["officeqa"]
    assert all(protocol.ledger_bound(ELUCID_MODEL, bench, branch=b.branch, longest=b.longest) == pin["B"][bench]
               for bench in BENCHES)
    assert "route" not in manifest.setting_of(m, "G", docker=docker, transport=NO_CALLS).extra
    plain, _ = routed_manifest(tmp_path / "plain", monkeypatch, pin=False)
    plain_root = safe_path(plain["root"]) / "D"
    plain_root.mkdir(parents=True)
    routes.switch(plain_root, to="B", run=plain[RECORD_HASH], evidence=plain["evidence"], reason="fixture")
    with pytest.raises(ConfigurationError, match="does not pin"):
        manifest.setting_of(plain, "D", docker=docker, transport=NO_CALLS)


# --------------------------------------------------------------------------------------------- the manifest pin
def test_the_route_b_pin_is_rederived_and_required_in_a_main_manifest(tmp_path):
    clients = given(tmp_path)["clients"]
    env = northgate_env(tmp_path)
    block = routes.pin("D", "B", env_path=env, solver_block=clients["solver"]["D"])
    assert (block["route"], block["backend"], block["model"], block["url_host"]) == (
        "B", "northgate", NORTHGATE_MODEL, client.NORTHGATE_HOST)
    assert (block["env_path"], block["proxy"], block["reasoning_effort"]) == (str(env), probe.GATEWAY, "none")
    assert (block["branch"], block["longest"]) == ("N", routes.S1B_CEILING) == ("N", 256)
    assert block["B"] == {b: max(4 * block["M"][b], 384) for b in BENCHES} and block["M"] == clients["solver"]["D"]["M"]
    assert block["B"]["searchqa"] == 32_768 and block["response_model_ids"] == ["deepseek-flash", NORTHGATE_MODEL]
    pinned = {**clients, "routes": {"D": {"B": block}}}
    manifest.check_clients(pinned)
    manifest.check_clients(pinned, configuration=protocol.MAIN)
    manifest.check_clients(clients)  # optional outside main
    with pytest.raises(ValueError, match="main manifest pins"):
        manifest.check_clients(clients, configuration=protocol.MAIN)
    bad = [{**block, "B": {**block["B"], "officeqa": 2 * block["M"]["officeqa"]}}, {**block, "branch": "E"},
           {**block, "model": ELUCID_MODEL}, {**block, "proxy": "http://other:3128"}, {**block, "longest": 1_000},
           {**block, "client_source_sha": "0" * 64}, {**block, "url_host": client.ELUCID_HOST},
           {key: found for key, found in block.items() if key != "slots"}]
    for value in bad:
        with pytest.raises(ValueError):
            manifest.check_clients({**clients, "routes": {"D": {"B": value}}})
    for routed in ({"G": {"B": block}}, {"D": {"A": block}}, {"D": {}}, {}):
        with pytest.raises(ValueError):
            manifest.check_clients({**clients, "routes": routed})
    longer = manifest.solver_block("D", env_path=tmp_path / "elucid.env", branch="N", longest=40_000)
    assert routes.pin("D", "B", env_path=env, solver_block=longer)["B"]["searchqa"] == 60_000  # S1's longest on N


# ---------------------------------------------------------------------------------------- the command line
def test_switch_route_refuses_a_live_or_unexplained_switch_then_writes_once_and_prints_recover(
        tmp_path, monkeypatch, capsys):
    m, path = routed_manifest(tmp_path, monkeypatch)
    chain_root = safe_path(m["root"]) / "D"
    argv = ["switch-route", "--manifest", str(path), "--chain", "D", "--to", "B"]

    def switch(*more):
        return cli.switch_route(cli.parser().parse_args(argv + list(more)))

    with pytest.raises(ValueError, match="No chain root"):
        switch()
    chain_root.mkdir(parents=True)
    with pytest.raises(ValueError, match="latest pause is none"):
        switch()
    sandbox = paused_attempt(chain_root, "sandbox", at=1_000)
    with pytest.raises(ValueError, match="latest pause is sandbox"):
        switch()
    attempt = paused_attempt(chain_root, "balance_exhausted", unit="s3-livemath/run", at=2_000)
    with exclusive(chain_root / chain.RUNNER_LOCK):  # a live chain process
        with pytest.raises(ValueError, match="Another process owns"):
            switch()
    with exclusive(attempt.parent / ".lock"):  # a unit still running
        with pytest.raises(ValueError, match="still running"):
            switch()
    northgate_env(tmp_path, url="https://api.example.com/v1/chat/completions")  # the pinned file, changed
    with pytest.raises(ConfigurationError, match="NORTHGATE_CHAT_URL"):
        switch()
    northgate_env(tmp_path)
    assert not list(chain_root.glob("route-*.json")) and NORTHGATE_KEY not in "".join(capsys.readouterr())
    switch()
    out = json.loads(capsys.readouterr().out)
    found = verified(read_json(chain_root / "route-1.json"), routes.KIND)
    assert (out["from"], out["to"], out["model"], out["paused_attempt"]) == ("A", "B", NORTHGATE_MODEL, str(attempt))
    assert out["record"] == str(chain_root / "route-1.json") and out["record_sha256"] == found[RECORD_HASH]
    assert found["pause"]["attempt"] == "s3-livemath/run/attempt-1" and found["run"] == m[RECORD_HASH]
    recover = "python -B scripts/run_execskill.py recover --attempt %s --decision \"<the owner's decision: %s>\""
    assert out["next"] == [recover % (attempt, "redo on route B"), recover % (sandbox, "its sandbox pause"),
                           "python -B scripts/run_execskill.py run --manifest %s --chain D" % path]
    assert routes.current(chain_root, run=m[RECORD_HASH]) == "B"
    with pytest.raises(ValueError, match="already runs on route B"):
        switch("--reason", "again")
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["switch-route", "--manifest", str(path), "--chain", "G", "--to", "B"])
    plain, plain_path = routed_manifest(tmp_path / "plain", monkeypatch, pin=False)
    paused_attempt(safe_path(plain["root"]) / "D", "balance_exhausted")
    with pytest.raises(ConfigurationError, match="does not pin"):
        cli.switch_route(cli.parser().parse_args(["switch-route", "--manifest", str(plain_path), "--chain", "D",
                                                  "--to", "B"]))
    assert not list((safe_path(plain["root"]) / "D").glob("route-*.json"))


# ------------------------------------------------------------------------------------ route B's first call
def test_route_b_confirms_its_own_first_reply_and_a_paid_unit_needs_the_current_routes(tmp_path):
    gateway = Gateway(completion("ready"))
    northgate = client.NorthgateClient(str(northgate_env(tmp_path)), proxy=probe.GATEWAY,
                                       max_tokens=ELUCID_MAX_TOKENS[FIRST_CALL_BENCH],
                                       read_timeout=ELUCID_READ_TIMEOUT[FIRST_CALL_BENCH], transport=gateway.transport)
    s = with_first_call(chain_setting(tmp_path, chain_="D"), {ELUCID_MODEL: SimpleNamespace(client=northgate)},
                        tmp_path / "slots-b")
    s = replace(s, branch="N", longest=routes.S1B_CEILING, extra={**s.extra, "route": "B"})
    assert chain.run(s, "D", learn=Learn(pause_at=1), launch=Launch(tmp_path))["reason"] == "fake_step_pause"
    root = tmp_path / "root" / "D"
    found = verified(read_json(root / "confirm-route-B.json"), "first-call")
    assert found["identity"] == {"run": RUN, "chain": "D", "route": "B"} and found["passed"] is True
    assert (found["model"], found["returned_model"], found["bench"]) == (ELUCID_MODEL, NORTHGATE_MODEL,
                                                                         FIRST_CALL_BENCH)
    assert found["bound"] == protocol.ledger_bound(ELUCID_MODEL, FIRST_CALL_BENCH, branch="N", longest=256)
    assert found["checks"] == {"reply": True, "model": True, "settled": True, "reasoning": True}
    assert not (root / chain.CONFIRM).exists() and [b["model"] for b in gateway.bodies] == [NORTHGATE_MODEL]
    with pytest.raises(ValueError, match="no confirmed first call"):
        chain.confirmation(tmp_path / "root", RUN, "D")  # the chain's history still names route A
    routes.switch(root, to="B", run=RUN, evidence=EVIDENCE, reason="fixture")
    assert chain.confirmation(tmp_path / "root", RUN, "D") == found  # a paid unit now needs route B's
    assert chain.run(s, "D", learn=Learn(), launch=Launch(tmp_path)) == {"status": "complete"}
    assert len(gateway.requests) == 1  # a relaunch reuses route B's confirmation
    wrong = Gateway(completion("ready", model=ELUCID_MODEL))  # route A's echo on route B
    other = replace(s, run="another-run", clients=lambda model, bench: client.NorthgateClient(
        str(northgate_env(tmp_path)), proxy=probe.GATEWAY, max_tokens=ELUCID_MAX_TOKENS[FIRST_CALL_BENCH],
        read_timeout=ELUCID_READ_TIMEOUT[FIRST_CALL_BENCH], transport=wrong.transport), root=tmp_path / "root2")
    (tmp_path / "root2" / "D").mkdir(parents=True)
    with pytest.raises(Pause, match="route B"):
        chain.first_call(other, "D")
    assert (tmp_path / "root2" / "D" / (chain.CONFIRM_ROUTE_FAILED % "B" % 1)).exists()
