"""fivebench-execskill-v1 solver clients (registration §4.1, §4.4 rows P6-P7; owner rule 22:3x (c); implementation plan
§8 T-CLIENT-1..6): the elucid client's registered request, reasoning check, usage fields and configuration refusals, the
frozen resend path and ledger stop its receipts feed, the solver factory of chains G and D, and the shared fakes. Every
receipt comes from the real client code over a mock transport; no test makes a real call or reads a real credential."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from scripts import weak_solver_probe as probe
from skillopt.coevo5.budget import DEEPSEEK, Budget
from skillopt.coevo5.calls import BREACH, Endpoint, Slots, _request_hash
from skillopt.coevo5.outcomes import (
    INFRASTRUCTURE,
    UNKNOWN,
    AssumptionBroken,
    ConfigurationError,
    classify,
    undelivered,
)
from skillopt.coevo5.protocol import MAX_RESENDS, RESEND_COOLDOWN_SECONDS
from skillopt.continual_eval import backends
from skillopt.execskill.client import (
    ELUCID_ALIAS,
    ELUCID_MODEL,
    ELUCID_RESPONSE_MODEL_IDS,
    GLM_SOLVER,
    ElucidClient,
    solver_client,
)
from tests import execskill_fakes as fakes
from tests.execskill_fakes import FAKE_KEYS, QA_MAX_TOKENS, QA_READ_TIMEOUT, FakeSolver, Reply, fake_config, tagged

M = QA_MAX_TOKENS
B = 2 * M  # branch E of §4.1: the bound the Endpoint reserves and settles with
GOOD_URL = "https://hk.getelucid.com/v1/chat/completions"
KEY = FAKE_KEYS[ELUCID_MODEL]


def _solver(tmp_path, *answers, **settings):
    """A FakeSolver answering every request from ``answers``, in order."""
    return FakeSolver(tmp_path, [(None, list(answers))], **settings)


def _raw(tmp_path, body):
    """The receipt of a gateway body a ``Reply`` cannot express."""
    client = solver_client(ELUCID_MODEL, config=fake_config(tmp_path, ELUCID_MODEL),
                           transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    return client.call("sys", "user")


def _ledger(tmp_path):
    ledger = Budget(tmp_path / "ledger", poll=0)
    ledger.declare({DEEPSEEK: 10 ** 9})
    return ledger


def _endpoint(tmp_path, fake, *, ledger=None, slept=None):
    """The frozen call wrapper around a fake, with the registered cooldown recorded instead of slept."""
    return Endpoint(fake, model=ELUCID_MODEL, max_tokens=B, slots=Slots(tmp_path / "slots", ELUCID_MODEL, 2),
                    budget=ledger, scopes=(DEEPSEEK,) if ledger is not None else (),
                    cooldown=RESEND_COOLDOWN_SECONDS, sleep=(slept.append if slept is not None else lambda _: None))


def _recording(monkeypatch):
    """Every ``httpx.Client`` construction's keyword arguments (the clients build theirs through the module)."""
    made, original = [], httpx.Client

    class Recording(original):
        def __init__(self, **kwargs):
            made.append(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(httpx, "Client", Recording)
    return made


# ------------------------------------------------------------------------- T-CLIENT-1: the reasoning check
LEAKS = [
    Reply(text=tagged("4"), usage=fakes.usage(17), reasoning_tokens=12),  # reasoning tokens only
    Reply(text=tagged("4"), reasoning="Let me think."),  # reasoning text only
    Reply(text=tagged("4"), reasoning_tokens=0, reasoning=" "),  # any text, even blank
    Reply(text=tagged("4"), reasoning_tokens=True),  # a count that is not an integer
    Reply(text=tagged("4"), reasoning_tokens="0"),
    Reply(text=tagged("4"), reasoning=["step"]),
    Reply(text=tagged("4"), finish="length", reasoning_tokens=3),  # read before the finish reason
    Reply(text="", reasoning="only reasoning"),  # and before the empty-reply rule
    fakes.with_reasoning(tagged("4")),
]
CLEAN = [Reply(text=tagged("4")), Reply(text=tagged("4"), reasoning_tokens=0), Reply(text=tagged("4"), reasoning=""),
         Reply(text=tagged("4"), reasoning_tokens=0, reasoning="")]


@pytest.mark.parametrize("reply", LEAKS)
def test_any_reasoning_is_a_thinking_mismatch_with_the_reasoning_subtype(tmp_path, reply):
    receipt = _solver(tmp_path, reply).call("sys", "user")
    assert (receipt["ok"], receipt["error_type"], receipt["subtype"]) == (False, "thinking_mismatch",
                                                                         "reasoning_mismatch")
    assert undelivered(receipt)  # the frozen Recorder re-sends it (outcomes.py:66-67)


@pytest.mark.parametrize("reply", CLEAN)
def test_absent_or_zero_reasoning_is_a_delivered_reply(tmp_path, reply):
    receipt = _solver(tmp_path, reply).call("sys", "user")
    assert receipt["ok"] is True and "error_type" not in receipt and "subtype" not in receipt
    assert receipt["response"] == "<answer>4</answer>" and receipt["returned_model"] == ELUCID_MODEL


def test_reasoning_details_of_another_shape_count_as_reasoning_and_null_details_as_absent(tmp_path):
    body = {"model": ELUCID_MODEL, "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]}
    malformed = _raw(tmp_path, {**body, "usage": {**fakes.usage(5), "completion_tokens_details": "many"}})
    null = _raw(tmp_path, {**body, "usage": {**fakes.usage(5), "completion_tokens_details": None},
                           "choices": [{"finish_reason": "stop",
                                        "message": {"content": "ok", "reasoning_content": None}}]})
    assert (malformed["error_type"], malformed["reasoning_tokens"]) == ("thinking_mismatch", "invalid")
    assert null["ok"] is True and null["reasoning_tokens"] is None and null["visible_completion_tokens"] == 5


# ------------------------------------------------------------------------- T-CLIENT-2: the frozen resend path
def test_a_reasoning_reply_takes_the_frozen_resend_path_and_the_clean_resend_is_kept(tmp_path):
    slept = []
    fake = _solver(tmp_path, fakes.with_reasoning(tagged("4")), tagged("4"))
    recorder = _endpoint(tmp_path, fake, slept=slept).recorder(label="cell")
    receipt = recorder("sys", "user")
    first = recorder.sends[0]["receipt"]
    assert (first["ok"], first["error_type"], first["subtype"]) == (False, "thinking_mismatch", "reasoning_mismatch")
    assert receipt["ok"] is True and receipt["response"] == "<answer>4</answer>" and recorder.receipts == [receipt]
    assert len(recorder.sends) == 2 and slept == [RESEND_COOLDOWN_SECONDS]
    assert fake.requests[0] == fake.requests[1]  # re-sent identically


def test_a_reply_still_mismatched_after_the_resends_is_an_infrastructure_unknown(tmp_path):
    fake = _solver(tmp_path, *[fakes.with_reasoning(tagged("4"))] * (MAX_RESENDS + 1))
    recorder = _endpoint(tmp_path, fake).recorder(label="cell")
    prediction = backends.solve("searchqa", {"question": "Q", "context": ["c"]}, "", recorder)
    assert len(recorder.sends) == MAX_RESENDS + 1 and undelivered(recorder.receipts[-1])
    verdict = classify("searchqa", prediction, receipts=recorder.receipts, refused=recorder.refused)
    assert (verdict.outcome, verdict.kind, verdict.row) == (UNKNOWN, INFRASTRUCTURE, "4")
    assert verdict.reason.endswith(":thinking_mismatch")


def test_a_reasoning_reply_beyond_the_ledger_bound_halts_the_ledger_before_any_resend(tmp_path):
    ledger = _ledger(tmp_path)
    fake = _solver(tmp_path, fakes.with_reasoning(tagged("4"), tokens=B), tagged("4"))  # completion 5 + B > B
    recorder = _endpoint(tmp_path, fake, ledger=ledger).recorder(label="cell")
    with pytest.raises(AssumptionBroken):
        recorder("sys", "user")
    (send,) = recorder.sends
    assert send["receipt"]["error_type"] == "thinking_mismatch" and send["assumption_broken"] is True
    assert recorder.broken == BREACH and recorder.receipts == [] and len(fake.requests) == 1
    assert ledger.snapshot()["halted"] == {"reason": BREACH, "label": "cell"}


# ------------------------------------------------------------------------- T-CLIENT-3: over_nominal and usage
@pytest.mark.parametrize("completion, flagged, halts", [(M, False, False), (M + 1, True, False), (B, True, False),
                                                        (B + 1, True, True)])
def test_a_completion_above_nominal_m_is_flagged_and_only_one_above_bound_b_stops(tmp_path, completion, flagged,
                                                                                    halts):
    ledger = _ledger(tmp_path)
    fake = _solver(tmp_path, fakes.over_nominal(tagged("4"), completion))
    recorder = _endpoint(tmp_path, fake, ledger=ledger).recorder(label="cell")
    if halts:
        with pytest.raises(AssumptionBroken):
            recorder("sys", "user")
        assert ledger.snapshot()["halted"]["reason"] == BREACH
        return
    receipt = recorder("sys", "user")
    assert receipt["ok"] is True and receipt["over_nominal"] is flagged
    assert receipt["visible_completion_tokens"] == completion
    view = ledger.snapshot()
    assert "halted" not in view and view[DEEPSEEK]["settled"] == 10 + completion and view[DEEPSEEK]["open"] == 0


@pytest.mark.parametrize("reply, fields", [
    (Reply(text="x"), (None, 5, False)),
    (Reply(text="x", usage=None), (None, None, False)),
    (Reply(text="x", usage=fakes.usage(20), reasoning_tokens=3), (3, 17, False)),
    (Reply(text="x", usage=fakes.usage(20), reasoning_tokens=30), (30, None, False)),
    (Reply(text="x", usage=fakes.usage(20), reasoning_tokens=1.5), ("invalid", None, False)),
    (Reply(text="x", usage=fakes.usage(M + 3), reasoning_tokens=0), (0, M + 3, True)),
])
def test_the_usage_fields_of_a_receipt(tmp_path, reply, fields):
    receipt = _solver(tmp_path, reply).call("sys", "user")
    assert (receipt["reasoning_tokens"], receipt["visible_completion_tokens"], receipt["over_nominal"]) == fields
    assert receipt["usage_valid"] is (reply.usage is not None)


# ------------------------------------------------------------------------- T-CLIENT-4: the echoed model id
@pytest.mark.parametrize("echo", ["deepseek-v4-flash", "deepseek-flash", "glm-5.3", "deepseek-v4.1-flash-1018",
                                  "deepseek-v4.1"])
def test_an_echo_outside_the_registered_set_is_a_model_mismatch(tmp_path, echo):
    receipt = _solver(tmp_path, Reply(text=tagged("4"), model=echo, reasoning="r")).call("sys", "user")
    assert (receipt["ok"], receipt["error_type"], receipt["returned_model"]) == (False, "model_mismatch", echo)
    assert "subtype" not in receipt and "over_nominal" not in receipt and undelivered(receipt)
    assert ELUCID_RESPONSE_MODEL_IDS == {ELUCID_MODEL, ELUCID_ALIAS} and ELUCID_ALIAS == "deepseek-v4.1-flash"


@pytest.mark.parametrize("reasoning", [None, "r"])
def test_the_owner_confirmed_alias_echo_is_a_reply_of_the_registered_model(tmp_path, reasoning):
    # owner 2026-10-23 19:1x: the echo deepseek-v4.1-flash is deepseek-v4.1-flash-1017 itself; its replies keep the
    # reasoning check of every registered reply
    receipt = _solver(tmp_path, Reply(text=tagged("4"), model=ELUCID_ALIAS, reasoning=reasoning)).call("sys", "user")
    assert receipt["returned_model"] == ELUCID_ALIAS
    if reasoning is None:
        assert receipt["ok"] is True and "error_type" not in receipt and receipt["response"] == tagged("4")
    else:
        assert (receipt["ok"], receipt["error_type"], receipt["subtype"]) == (False, "thinking_mismatch",
                                                                              "reasoning_mismatch")


def test_a_non_text_echo_is_a_model_mismatch(tmp_path):
    receipt = _raw(tmp_path, {"model": 7, "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
                              "usage": fakes.usage(2)})
    assert (receipt["ok"], receipt["error_type"]) == (False, "model_mismatch")


# ------------------------------------------------------------------------- T-CLIENT-5: request, proxy, credentials
def test_the_registered_body_turns_reasoning_off_and_names_no_thinking_mode(tmp_path):
    fake = _solver(tmp_path, tagged("4"))
    fake.call("system text", "user text")
    (body,) = fake.requests
    assert body == {"model": ELUCID_MODEL, "max_tokens": M, "temperature": 0, "reasoning_effort": "none",
                    "messages": [{"role": "system", "content": "system text"},
                                 {"role": "user", "content": "user text"}]}


def test_requests_go_to_the_approved_endpoint_with_the_key_and_no_session_header(tmp_path):
    seen = []

    def server(request):
        seen.append(request)
        return httpx.Response(200, json={"model": ELUCID_MODEL, "usage": fakes.usage(2),
                                         "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]})

    client = solver_client(ELUCID_MODEL, config=fake_config(tmp_path, ELUCID_MODEL),
                           transport=httpx.MockTransport(server))
    assert client.call("sys", "user")["ok"] is True
    (request,) = seen
    assert str(request.url) == GOOD_URL and request.headers["authorization"] == "Bearer " + KEY
    assert "x-session-id" not in request.headers


def test_the_client_goes_through_the_pjlab_gateway_only_and_ignores_the_environment(tmp_path, monkeypatch):
    made = _recording(monkeypatch)
    config = fake_config(tmp_path, ELUCID_MODEL)
    assert type(solver_client(ELUCID_MODEL, config=config)) is ElucidClient
    (kwargs,) = made
    assert (kwargs["proxy"], kwargs["trust_env"], kwargs["follow_redirects"]) == (probe.GATEWAY, False, False)
    assert "transport" not in kwargs and kwargs["timeout"].read == QA_READ_TIMEOUT
    for proxy in (None, "http://elsewhere.example:3128", probe.GATEWAY + "/"):
        with pytest.raises(ConfigurationError, match="gateway"):
            solver_client(ELUCID_MODEL, config={**config, "proxy": proxy})
        with pytest.raises(ConfigurationError, match="gateway"):
            ElucidClient(config["env_path"], proxy=proxy, max_tokens=M, read_timeout=QA_READ_TIMEOUT)
    assert len(made) == 1


@pytest.mark.parametrize("lines", [
    ["ELUCID_CHAT_URL=https://api.example.com/v1/chat/completions", "ELUCID_API_KEY=" + KEY,
     "ELUCID_MODEL=" + ELUCID_MODEL],
    ["ELUCID_CHAT_URL=http://hk.getelucid.com/v1/chat/completions", "ELUCID_API_KEY=" + KEY,
     "ELUCID_MODEL=" + ELUCID_MODEL],
    ["ELUCID_CHAT_URL=" + GOOD_URL + "?key=" + KEY, "ELUCID_API_KEY=" + KEY, "ELUCID_MODEL=" + ELUCID_MODEL],
    ["ELUCID_CHAT_URL=https://user:" + KEY + "@hk.getelucid.com/v1/chat/completions", "ELUCID_API_KEY=" + KEY,
     "ELUCID_MODEL=" + ELUCID_MODEL],
    ["ELUCID_CHAT_URL=https://hk.getelucid.com:8443/v1/chat/completions", "ELUCID_API_KEY=" + KEY,
     "ELUCID_MODEL=" + ELUCID_MODEL],
    ["ELUCID_CHAT_URL=https://hk.getelucid.com/v2/chat/completions", "ELUCID_API_KEY=" + KEY,
     "ELUCID_MODEL=" + ELUCID_MODEL],
    ["ELUCID_CHAT_URL=" + GOOD_URL, "ELUCID_MODEL=" + ELUCID_MODEL],  # no key
    ["ELUCID_CHAT_URL=" + GOOD_URL, "ELUCID_API_KEY=" + KEY, "ELUCID_MODEL=deepseek-v4-flash"],
    ["ELUCID_CHAT_URL=" + GOOD_URL, "ELUCID_API_KEY=" + KEY],  # no model
])
def test_elucid_credentials_are_refused_unless_registered_and_the_key_never_shows(tmp_path, capsys, lines):
    env = tmp_path / "elucid.env"
    env.write_text("\n".join(lines) + "\n")
    with pytest.raises(ConfigurationError) as refusal:
        ElucidClient(env, proxy=probe.GATEWAY, max_tokens=M, read_timeout=QA_READ_TIMEOUT)
    assert KEY not in str(refusal.value) and KEY not in repr(refusal.value)
    assert capsys.readouterr() == ("", "")


def test_the_elucid_credential_file_must_be_a_real_file(tmp_path):
    config = fake_config(tmp_path, ELUCID_MODEL)
    link = tmp_path / "link.env"
    link.symlink_to(config["env_path"])
    for path in (tmp_path / "absent.env", link):
        with pytest.raises(ConfigurationError, match="credential file"):
            ElucidClient(path, proxy=probe.GATEWAY, max_tokens=M, read_timeout=QA_READ_TIMEOUT)


@pytest.mark.parametrize("settings", [{"max_tokens": 0}, {"max_tokens": True}, {"max_tokens": 8192.0},
                                      {"max_tokens": "8192"}, {"read_timeout": 0}, {"read_timeout": -1},
                                      {"read_timeout": True}, {"read_timeout": "600"}])
def test_invalid_nominal_settings_are_configuration_errors(tmp_path, settings):
    with pytest.raises(ConfigurationError, match="positive"):
        solver_client(ELUCID_MODEL, config={**fake_config(tmp_path, ELUCID_MODEL), **settings})


# ------------------------------------------------------------------------- T-CLIENT-6: the two chains' solvers
def test_chain_g_gets_the_frozen_bigmodel_client_built_like_v3(tmp_path, monkeypatch):
    made = _recording(monkeypatch)
    client = solver_client(GLM_SOLVER, config=fake_config(tmp_path, GLM_SOLVER))
    assert type(client) is probe.Client
    assert (client.backend, client.model, client.thinking, client.effort, client.max_tokens) == (
        "bigmodel", "glm-5.3", "enabled", "low", 65536)
    assert client.response_model_ids == {"glm-5.3"}
    assert client.url == "https://%s%s" % (probe.BIGMODEL_HOST, probe.BIGMODEL_PATH)  # no route
    (kwargs,) = made
    assert (kwargs["proxy"], kwargs["trust_env"], kwargs["timeout"].read) == (probe.GATEWAY, False, 2400)


def test_chain_g_sends_the_frozen_body_and_its_reasoning_is_never_a_mismatch(tmp_path):
    fake = FakeSolver(tmp_path, [(None, fakes.with_reasoning(tagged("4"), tokens=40))], model=GLM_SOLVER)
    receipt = fake.call("sys", "user")
    assert receipt["ok"] is True and receipt["reasoning_chars"] == len("Let me think.")
    assert "subtype" not in receipt and "over_nominal" not in receipt
    (body,) = fake.requests
    assert body == {"model": GLM_SOLVER, "max_tokens": 65536, "temperature": 0, "thinking": {"type": "enabled"},
                    "reasoning_effort": "low", "messages": [{"role": "system", "content": "sys"},
                                                            {"role": "user", "content": "user"}]}


def test_chain_d_gets_the_elucid_client_with_the_benchs_settings(tmp_path):
    client = solver_client(ELUCID_MODEL, config=fake_config(tmp_path, ELUCID_MODEL, max_tokens=16384,
                                                            read_timeout=900))
    assert type(client) is ElucidClient and isinstance(client, probe.Client)
    assert (client.backend, client.model, client.max_tokens, client.thinking, client.effort) == (
        "elucid", ELUCID_MODEL, 16384, None, "none")
    assert client.http.timeout.read == 900 and client.response_model_ids == ELUCID_RESPONSE_MODEL_IDS


@pytest.mark.parametrize("model", ["deepseek-v4-flash", "glm-4.7-flash", "Qwen/Qwen3.5-9B", "", None])
def test_any_other_solver_model_is_a_configuration_error(tmp_path, model):
    with pytest.raises(ConfigurationError, match="Not a registered solver model"):
        solver_client(model, config=fake_config(tmp_path, ELUCID_MODEL))


def test_a_solver_config_holds_exactly_its_registered_inputs(tmp_path):
    glm, elucid = fake_config(tmp_path, GLM_SOLVER), fake_config(tmp_path, ELUCID_MODEL)
    wrong = [(GLM_SOLVER, {**glm, "max_tokens": 65536}), (GLM_SOLVER, {**glm, "route": "pjlab_token"}),
             (GLM_SOLVER, {**glm, "proxy": None}), (GLM_SOLVER, elucid), (ELUCID_MODEL, glm),
             (ELUCID_MODEL, {k: v for k, v in elucid.items() if k != "read_timeout"}),
             (GLM_SOLVER, sorted(glm.items()))]
    for model, config in wrong:
        with pytest.raises(ConfigurationError):
            solver_client(model, config=config)


def test_glm_credential_refusals_are_configuration_errors_that_never_carry_the_key(tmp_path, capsys):
    config = fake_config(tmp_path, GLM_SOLVER)
    env = Path(config["repo"]) / ".env"
    env.write_text("BIGMODEL_CHAT_URL=https://elsewhere.example.com/api/paas/v4/chat/completions\n"
                   "BIGMODEL_API_KEY=%s\n" % FAKE_KEYS[GLM_SOLVER])
    with pytest.raises(ConfigurationError) as wrong_host:
        solver_client(GLM_SOLVER, config=config)
    env.unlink()
    with pytest.raises(ConfigurationError) as missing:
        solver_client(GLM_SOLVER, config=config)
    for refusal in (wrong_host, missing):
        assert str(refusal.value).startswith("glm-5.3 credentials:") and FAKE_KEYS[GLM_SOLVER] not in str(refusal.value)
    assert capsys.readouterr() == ("", "")


# ------------------------------------------------------------------------- the shared fakes (plan §7)
def test_fake_solver_rules_answer_by_request_hash_then_regex_then_every_request(tmp_path):
    exact = _request_hash("sys", '{"question": "Q1"}')
    fake = FakeSolver(tmp_path, [(exact, tagged("exact")),
                                 (r'"question": "Q[0-9]"', [tagged("first"), tagged("second")]),
                                 (None, lambda system, user: fakes.json_answer(user))])
    replies = [fake.call("sys", '{"question": "Q%d"}' % n)["response"] for n in (1, 2, 3)]
    assert replies == ["<answer>exact</answer>", "<answer>first</answer>", "<answer>second</answer>"]
    assert fake.call("sys", "plain")["response"] == '{"answer": "plain"}'
    with pytest.raises(AssertionError, match="used up"):
        fake.call("sys", '{"question": "Q4"}')
    with pytest.raises(AssertionError, match="No scripted reply"):
        FakeSolver(tmp_path, [("never", "x")]).call("sys", "user")


def test_the_reply_builders_through_the_real_client(tmp_path):
    texts = [tagged("12.5"), fakes.json_answer("12.5"), fakes.calc("a + b", "2 ** 3")]
    fake = _solver(tmp_path, *texts, fakes.truncated("<answer>12"))
    assert [fake.call("sys", "user")["response"] for _ in texts] == texts
    assert texts[1:] == ['{"answer": "12.5"}', "<calc>a + b</calc>\n<calc>2 ** 3</calc>"]
    cut = fake.call("sys", "user")
    assert (cut["ok"], cut["error_type"], cut["finish_reason"]) == (False, "finish_length", "length")


@pytest.mark.parametrize("failure", ["http_400", "http_404", "error_payload", "invalid_json", "malformed_choices"])
def test_the_undelivered_failures_reach_the_frozen_resend_rule(tmp_path, failure):
    receipt = _solver(tmp_path, fakes.undelivered(failure)).call("sys", "user")
    assert (receipt["ok"], receipt["error_type"]) == (False, failure) and undelivered(receipt)
    assert "over_nominal" not in receipt
    with pytest.raises(ValueError, match="Unknown fake failure"):
        fakes.undelivered("http_200")


def test_a_transport_failure_runs_the_frozen_client_retries(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr(probe.time, "sleep", slept.append)
    receipt = _solver(tmp_path, *[fakes.undelivered("transport")] * 4).call("sys", "user")
    assert receipt["error_type"] == "transport" and len(receipt["attempts"]) == 4 and slept == list(probe.BACKOFF)


def test_one_fake_per_model_drives_chains_g_and_d(tmp_path):
    chain_g = FakeSolver(tmp_path, [(None, fakes.with_reasoning(tagged("G")))], model=GLM_SOLVER)
    chain_d = FakeSolver(tmp_path, [(None, tagged("D"))])
    assert chain_g.call("sys", "user")["response"] == "<answer>G</answer>"
    assert chain_d.call("sys", "user")["response"] == "<answer>D</answer>"
    assert [body["model"] for body in chain_g.requests + chain_d.requests] == [GLM_SOLVER, ELUCID_MODEL]
    assert "thinking" in chain_g.requests[0] and "thinking" not in chain_d.requests[0]
    with pytest.raises(ValueError, match="frozen"):
        FakeSolver(tmp_path, [(None, "x")], model=GLM_SOLVER, max_tokens=1024)


def test_fake_glm_answers_the_method_roles_through_the_real_frozen_client(tmp_path):
    reply = fakes.engineer_reply({"changes": [{"kind": "new", "id": "p-officeqa-1-1"}]},
                                 ["def applies(view):\n    return True\n", fakes.POLICY_VIOLATING_SOURCE])
    roles, fake = fakes.glm_roles(tmp_path, [{"detectors": []}, fakes.INVALID_JSON, reply, fakes.undelivered(),
                                             {"label": "no_leak"}])
    assert roles.ask("examiner", "sys", {"task": "detectors"}, label="x:1") == {"detectors": []}
    assert roles.ask("examiner", "sys", {"task": "again"}, label="x:2") is None
    assert roles.calls[-1]["reason"].startswith("invalid:")
    text = roles.plain("engineer", "sys", "propose", label="e:1")
    assert text == reply and text.startswith("```json\n") and text.count("```python\n") == 2
    assert roles.ask("leakage", "sys", {"q": 1}, label="l:1") == {"label": "no_leak"}
    assert len(roles.calls[-1]["sends"]) == 2  # the undelivered send was re-sent by the frozen Recorder
    assert fake.seen[0] == ("sys", {"task": "detectors"}) and fake.seen[2] == ("sys", "propose")
    assert all(body["thinking"] == {"type": "enabled"} and body["reasoning_effort"] == "low"
               and body["max_tokens"] == 16384 for body in fake.provider.requests)
