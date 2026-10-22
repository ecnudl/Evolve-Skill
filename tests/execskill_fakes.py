"""Shared fakes for the fivebench-execskill-v1 tests (implementation plan §7; registration §4.1): scripted chat gateways
behind the REAL clients, so every receipt a test sees is produced by the client code a run uses -- the frozen
``weak_solver_probe.Client`` for glm-5.3 (chain G's solver and every method role) and ``execskill.client.ElucidClient``
for deepseek-v4.1-flash-1017 (chain D's solver and the smoke) -- answering through an ``httpx.MockTransport``: no
network, fake credential files under the test's own directory, nothing secret.

- ``FakeSolver``: one model's solver. Replies are chosen by request SHA-256 (``calls._request_hash`` of system and
  user), by a regular expression searched in the user message, or for every request; the reply builders emit a tagged
  answer, a JSON answer, ``<calc>`` tags, a truncated reply, an over-nominal usage, reasoning tokens and text, another
  model's echo and the undelivered failures. A glm-5.3 solver may reply with reasoning (thinking enabled: never a
  mismatch); a deepseek reply is reasoning-off unless the test says otherwise. One instance per model, so one
  end-to-end run drives chains G and D.
- ``FakeGLM`` and ``glm_roles``: the method roles (engineer, examiner, describer, leakage adjudicator, researcher),
  ported from tests/coevo5_fakes.py (``Script``, ``roles``): replies in order or from a function of (system, payload),
  behind a real ``Endpoint`` without a ledger and without resend cooldowns; builders for fenced code, the engineer's
  manifest-plus-code reply, invalid JSON and policy-violating code.
- ``first_call_solvers`` and ``with_first_call``: both chains' solvers for the first-call confirmation that
  ``chain.run`` makes before a chain's first unit (registrar addendum 2026-10-22 14:10, row 7), and a fixture
  Setting wired to them.
- ``ProbeGateway``: the scripted elucid gateway of ``probe --fake`` (registrar addendum 2026-10-22 15:0x), on which the
  S1 probe passes rows a-f: every completion within its max_tokens (branch E), reasoning text only for a body without
  ``reasoning_effort`` (S1-e's control call).
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path

import httpx

from scripts.weak_solver_probe import BIGMODEL_HOST, BIGMODEL_PATH, GATEWAY, Client
from skillopt.coevo5.calls import Endpoint, Slots, _request_hash
from skillopt.coevo5.protocol import ROLE_MAX_TOKENS, ROLE_MODEL, ROLE_READ_TIMEOUT_SECONDS
from skillopt.coevo5.roles import Roles
from skillopt.execskill.client import ELUCID_HOST, ELUCID_MODEL, ELUCID_PATH, GLM_SOLVER, solver_client
from skillopt.execskill.protocol import ELUCID_MAX_TOKENS, ELUCID_READ_TIMEOUT, FIRST_CALL_BENCH

USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
FAKE_KEYS = {GLM_SOLVER: "fake-bigmodel-key-0000", ELUCID_MODEL: "fake-elucid-key-0000"}
# chain D's nominal M and read timeout on the QA benches (registration §4.1, registered once in protocol, ticket
# A2-1): a deepseek FakeSolver's default
QA_MAX_TOKENS, QA_READ_TIMEOUT = ELUCID_MAX_TOKENS["officeqa"], ELUCID_READ_TIMEOUT["officeqa"]
FAILURES = frozenset({"transport", "error_payload", "invalid_json", "malformed_choices"})
HTTP_FAILURE = re.compile(r"http_([45][0-9][0-9])")
SHA256 = re.compile(r"[0-9a-f]{64}")


def usage(completion, *, prompt=USAGE["prompt_tokens"]):
    """A reported usage with ``completion`` completion tokens."""
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}


@dataclass(frozen=True)
class Reply:
    """One scripted gateway answer. ``text``: the message content (None: absent); ``finish``: the finish reason;
    ``usage``: the reported usage (None: absent); ``reasoning_tokens``: ``usage.completion_tokens_details.
    reasoning_tokens`` (None: absent; needs a usage); ``reasoning``: ``message.reasoning_content`` (None: absent);
    ``model``: the echoed model id (None: the requested one); ``failure``: an undelivered call instead of a reply --
    ``"http_<4xx|5xx>"``, ``"error_payload"``, ``"invalid_json"``, ``"malformed_choices"`` or ``"transport"`` (the real
    client retries a transport failure and HTTP 429/5xx with its frozen backoff: such a test patches ``time.sleep``)."""

    text: str | None = ""
    finish: str | None = "stop"
    usage: dict | None = field(default_factory=lambda: dict(USAGE))
    reasoning_tokens: object = None
    reasoning: object = None
    model: str | None = None
    failure: str | None = None

    def __post_init__(self):
        if self.failure is not None and self.failure not in FAILURES and not HTTP_FAILURE.fullmatch(self.failure):
            raise ValueError("Unknown fake failure: %s" % self.failure)


def tagged(answer):
    """Reply text with the official answer carrier."""
    return "<answer>%s</answer>" % answer


def json_answer(answer):
    """Reply text that is a JSON answer object (the v2 scorer's second carrier, registration §4.4)."""
    return json.dumps({"answer": answer})


def calc(*expressions):
    """A first reply asking the shell's exact evaluator (registration §2.4)."""
    return "\n".join("<calc>%s</calc>" % expression for expression in expressions)


def truncated(text):
    return Reply(text=text, finish="length")


def over_nominal(text, completion):
    """A delivered reply reporting ``completion`` completion tokens (above the nominal M: P7)."""
    return Reply(text=text, usage=usage(completion))


def with_reasoning(text, *, tokens=12, content="Let me think."):
    """A reply carrying reasoning: ``tokens`` reasoning tokens (counted in the completion) and ``content``."""
    extra = tokens if type(tokens) is int else 0
    return Reply(text=text, usage=usage(USAGE["completion_tokens"] + extra), reasoning_tokens=tokens,
                 reasoning=content)


def undelivered(failure="http_400"):
    return Reply(text=None, usage=None, failure=failure)


def _completion(reply, model):
    """The chat-completions body of a scripted reply (the gateway's shape: echoed model, one choice, usage)."""
    message = {"role": "assistant", "content": reply.text}
    if reply.reasoning is not None:
        message["reasoning_content"] = reply.reasoning
    body = {"id": "chatcmpl-fake", "object": "chat.completion", "model": reply.model or model,
            "choices": [{"index": 0, "finish_reason": reply.finish, "message": message}]}
    if reply.usage is not None:
        body["usage"] = dict(reply.usage)
        if reply.reasoning_tokens is not None:
            body["usage"]["completion_tokens_details"] = {"reasoning_tokens": reply.reasoning_tokens}
    return body


def _response(reply, model):
    if reply.failure == "transport":
        raise httpx.ConnectError("fake transport failure")
    status = HTTP_FAILURE.fullmatch(reply.failure or "")
    if status is not None:
        return httpx.Response(int(status.group(1)), json={"error": {"code": "fake_" + reply.failure}})
    if reply.failure == "error_payload":
        return httpx.Response(200, json={"error": {"message": "fake provider error"}})
    if reply.failure == "invalid_json":
        return httpx.Response(200, content=b"<html>fake gateway page</html>")
    if reply.failure == "malformed_choices":
        return httpx.Response(200, json={"model": reply.model or model, "choices": []})
    return httpx.Response(200, json=_completion(reply, model))


class FakeProvider:
    """A scripted chat-completions gateway for one model: ``answer(system, user)`` returns a ``Reply`` or reply text;
    every request body is kept in ``requests``, in order. A request naming another model fails the test (a fake is
    wired to its own model's client)."""

    def __init__(self, model, answer):
        self.model, self.answer, self.requests = model, answer, []
        self.lock = threading.Lock()
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request):
        body = json.loads(request.content)
        with self.lock:
            if body.get("model") != self.model:
                raise AssertionError("A %s fake received a request for %s" % (self.model, body.get("model")))
            self.requests.append(body)
            system, user = (message["content"] for message in body["messages"])
            reply = self.answer(system, user)
        return _response(reply if isinstance(reply, Reply) else Reply(text=reply), self.model)


class ProbeGateway:
    """The S1 probe's scripted elucid gateway (``run_execskill.py probe --fake``, registrar addendum 15:0x): a clean
    reply whose completion stays within the request's ``max_tokens`` (branch E), with a usage whose prompt tokens stay
    under the request bytes; a body without ``reasoning_effort`` (S1-e, the control client) also gets reasoning text.
    ``bodies``: every request body, in order."""

    def __init__(self):
        self.bodies, self.lock = [], threading.Lock()
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request):
        body = json.loads(request.content)
        with self.lock:
            self.bodies.append(body)
        completion = min(body["max_tokens"], 40)
        message = {"role": "assistant", "content": "ready"}
        if "reasoning_effort" not in body:
            message["reasoning_content"] = "thinking first"
        return httpx.Response(200, json={"model": ELUCID_MODEL, "choices": [{"message": message,
                                                                            "finish_reason": "stop"}],
                                         "usage": usage(completion, prompt=30)})


def fake_config(root, model, *, max_tokens=None, read_timeout=None):
    """``solver_client``'s config for ``model`` with fake credential files under ``root`` (a test directory): glm-5.3,
    a credential repository whose ``.env`` names the approved BigModel endpoint; deepseek, an elucid credential file.
    deepseek's nominal M and read timeout default to the QA benches' (§4.1); glm-5.3's are the frozen ones (no
    argument)."""
    folder = Path(root) / "fake-credentials" / model
    folder.mkdir(parents=True, exist_ok=True)
    if model == GLM_SOLVER:
        if max_tokens is not None or read_timeout is not None:
            raise ValueError("glm-5.3's max_tokens and read timeout are the frozen ones")
        (folder / ".env").write_text("BIGMODEL_CHAT_URL=https://%s%s\nBIGMODEL_API_KEY=%s\n"
                                     % (BIGMODEL_HOST, BIGMODEL_PATH, FAKE_KEYS[GLM_SOLVER]))
        return {"repo": str(folder), "proxy": GATEWAY}
    if model != ELUCID_MODEL:
        raise ValueError("No fake credentials for %s" % model)
    env = folder / "elucid.env"
    env.write_text("ELUCID_CHAT_URL=https://%s%s\nELUCID_API_KEY=%s\nELUCID_MODEL=%s\n"
                   % (ELUCID_HOST, ELUCID_PATH, FAKE_KEYS[ELUCID_MODEL], ELUCID_MODEL))
    return {"env_path": str(env), "proxy": GATEWAY,
            "max_tokens": QA_MAX_TOKENS if max_tokens is None else max_tokens,
            "read_timeout": QA_READ_TIMEOUT if read_timeout is None else read_timeout}


class FakeSolver:
    """A scripted solver behind the real client of ``model`` (plan §7), built by ``solver_client`` with fake
    credentials under ``root``. ``script``: rules ``[(key, answer), ...]`` tried in order -- ``key``: a request SHA-256
    (64 lowercase hex), a regular expression searched in the user message, or None (every request); ``answer``: a
    ``Reply`` or reply text, a function ``(system, user) -> Reply or text``, or a list of them used in order (a used-up
    list fails the test, as does a request no rule matches). ``call(system, user)`` is the real client's call;
    ``requests`` holds every request body sent."""

    def __init__(self, root, script, *, model=ELUCID_MODEL, max_tokens=None, read_timeout=None):
        self.rules = [(key, list(answer) if isinstance(answer, (list, tuple)) else answer) for key, answer in script]
        self.provider = FakeProvider(model, self._answer)
        self.config = fake_config(root, model, max_tokens=max_tokens, read_timeout=read_timeout)
        self.client = solver_client(model, config=self.config, transport=self.provider.transport)

    @property
    def requests(self):
        return self.provider.requests

    def call(self, system, user):
        return self.client.call(system, user)

    def _answer(self, system, user):
        request = _request_hash(system, user)
        for index, (key, answer) in enumerate(self.rules):
            if key is None or key == request or (SHA256.fullmatch(key) is None and re.search(key, user)):
                if isinstance(answer, list):
                    if not answer:
                        raise AssertionError("The scripted replies of rule %d are used up" % index)
                    return answer.pop(0)
                return answer(system, user) if callable(answer) else answer
        raise AssertionError("No scripted reply for request %s" % request[:12])


class FakeGLM:
    """Scripted GLM-5.3 method roles (plan §7), the coevo5 ``Script`` behind the real frozen glm-5.3 client with the role
    settings (coevo5/protocol.py:30-32: 16,384 tokens, 900 s). ``replies``: a list answered in order or a function
    ``(system, payload) -> reply`` (payload: the user message parsed as JSON, else its text); a reply is a ``Reply``,
    text, or a dict sent as JSON text. Every request is kept in ``seen`` as (system, payload)."""

    def __init__(self, root, replies):
        self.replies, self.seen = (replies if callable(replies) else list(replies)), []
        self.provider = FakeProvider(ROLE_MODEL, self._answer)
        self.client = Client(fake_config(root, GLM_SOLVER)["repo"], ROLE_MODEL, proxy=GATEWAY,
                             max_tokens=ROLE_MAX_TOKENS, read_timeout=ROLE_READ_TIMEOUT_SECONDS,
                             transport=self.provider.transport)

    def call(self, system, user):
        return self.client.call(system, user)

    def _answer(self, system, user):
        try:
            payload = json.loads(user)
        except ValueError:  # a plain-text user message (``Roles.plain``)
            payload = user
        self.seen.append((system, payload))
        if callable(self.replies):
            value = self.replies(system, payload)
        else:
            if not self.replies:
                raise AssertionError("No scripted reply left")
            value = self.replies.pop(0)
        return json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value


def glm_roles(root, replies):
    """(Roles, FakeGLM) over a real ``Endpoint`` without a ledger and without resend cooldowns (the coevo5 ``roles``
    port; the ledger has its own tests)."""
    fake = FakeGLM(root, replies)
    endpoint = Endpoint(fake, model=ROLE_MODEL, max_tokens=ROLE_MAX_TOKENS,
                        slots=Slots(Path(root) / "slots", ROLE_MODEL, 4), cooldown=0, sleep=lambda _: None)
    return Roles(endpoint), fake


def first_call_solvers(root, answer="ready"):
    """Registrar addendum 2026-10-22 14:10, row 7 (``chain.first_call``): fake solvers of both chains' models behind
    the real clients with the registered settings of the first-call confirmation (glm-5.3: its frozen M and read
    timeout; deepseek: those of the first step's bench, ``FIRST_CALL_BENCH``), answering every request with ``answer``
    (as ``FakeSolver`` takes it: a ``Reply``, text, a function or a list); -> {model: FakeSolver}."""
    root = Path(root) / "first-call"
    return {GLM_SOLVER: FakeSolver(root, [(None, answer)], model=GLM_SOLVER),
            ELUCID_MODEL: FakeSolver(root, [(None, answer)], model=ELUCID_MODEL,
                                     max_tokens=ELUCID_MAX_TOKENS[FIRST_CALL_BENCH],
                                     read_timeout=ELUCID_READ_TIMEOUT[FIRST_CALL_BENCH])}


def with_first_call(setting, solvers, slot_root):
    """``setting`` (a ``units.Setting``) whose ``clients`` are the ``solvers``' (``first_call_solvers``), with one slot
    pool per solver model under ``slot_root`` and chain D's ledger-bound branch E unless the setting names one."""
    return replace(setting, clients=lambda model, bench: solvers[model].client,
                   slots={**setting.slots, **{model: Slots(Path(slot_root), model, 2) for model in solvers}},
                   branch=setting.branch or "E")


def fenced(text, lang="python"):
    return "```%s\n%s\n```" % (lang, text)


def engineer_reply(manifest, sources):
    """The engineer's reply (registration §4.2): one ```json manifest block, then one ```python block per procedure."""
    blocks = [fenced(json.dumps(manifest, ensure_ascii=False, sort_keys=True), "json")]
    return "\n\n".join(blocks + [fenced(source) for source in sources])


# a role reply cut off inside its JSON object
INVALID_JSON = '{"detectors": [{"id": "d-officeqa-1-1", "source": "def fires(view):'
# a procedure the static policy must reject (a forbidden import and eval); never executed by a test
POLICY_VIOLATING_SOURCE = ("import subprocess\n\n\ndef before_call(view):\n"
                           "    return {\"facts\": [str(eval(view[\"question\"]))]}\n")
