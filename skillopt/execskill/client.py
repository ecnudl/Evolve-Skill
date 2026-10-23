"""Solver clients (registration §4.1, §4.4 rows P6-P7; owner rule 22:3x (c), §21; implementation plan §1
``client.py``; registrar "Owner instructions 2026-10-22 17:0x and 17:3x", row "deepseek route B").

Two formal chains, two solvers, one rule: the client is picked by model name and nothing else of the solver call
differs between the chains (§4.1, the chain G table). ``solver_client``:
- ``"glm-5.3"`` (chain G): the frozen ``scripts.weak_solver_probe.Client``, unchanged, built as the v3 factory builds it
  (coevo5/manifest.py:104-112) and without a route: ``MODELS["glm-5.3"]`` (weak_solver_probe.py:77) is backend
  bigmodel, thinking enabled, effort low, echo ``glm-5.3``; max_tokens = M = B = 65,536 and read timeout 2,400 s on
  every bench (coevo5/protocol.py:327, :92); credentials by path from the credential repository's ``.env``
  (weak_solver_probe.py:140-147). Its reasoning is registered: the frozen ``_receipt`` checks reasoning only when
  thinking is disabled (:295-296), so P6 does not apply to chain G and its receipts carry none of the fields below.
- ``"deepseek-v4.1-flash-1017"`` (chain D and the smoke): the client of the config's ``route`` (``ROUTES``; without
  the key, route A): ``ElucidClient`` (route A) or ``NorthgateClient`` (route B).
- any other model: ``ConfigurationError`` (the ONE exception set, coevo5/outcomes.py:95).

Chain D's two routes (registrar row "deepseek route B"). Route A is the registered, smoke-probed elucid gateway
(``deepseek-v4.1-flash-1017``, credentials in ``/root/.config/weak-solver/elucid.env``). Route B is the owner's second
provider for when A's balance runs out: the northgate gateway (``NORTHGATE_HOST``), model ``deepseek-v4-flash``,
credentials by path from ``NORTHGATE_ENV`` (``NORTHGATE_CHAT_URL``, ``NORTHGATE_API_KEY``; mode 600, never printed,
copied or logged). Both routes send the same OpenAI-compatible body (temperature 0, ``[system, user]``, the nominal M,
``reasoning_effort: "none"``, no ``thinking`` field) through the same explicit PJLAB gateway with ``trust_env=False``,
and both get the same reasoning check. A route's echoed model id must be in its own registered set; route B's is the
frozen allow-list's set for deepseek-v4-flash (weak_solver_probe.py MODELS: the provider may echo the canonical
``deepseek-flash``). Identity across the routes cannot be verified (temperature-0 replies are nondeterministic within
each route and overlap across them; registrar row), so every receipt names its ``route`` and ``route_model`` (the model
id the request named), every cell its ``solver_route`` (``route_of``), and analyses report chain D by route. Inside the
protocol both route clients are chain D's solver: ``model`` is the chain's registered solver name
(``deepseek-v4.1-flash-1017``: its slot pool, ledger scopes, nominal M and the chain checks key on it), while
``request_model`` is what the body names. Route B's ledger bound is branch N's (``routes.pin``: no probe of its own);
which route a chain uses is ``routes.py``'s per-chain history.

Balance exhaustion (``balance_signal``) is never retried: the route client's HTTP client (``_Guard``) raises
``errors.BalanceExhausted`` for such an answer before the frozen ``call`` (weak_solver_probe.py:322-330) can retry it,
and from then on that client sends nothing (later calls in the process raise at once). The frozen ``Endpoint`` records
the send with the exception's class and charges its reservation in full (no receipt: ledger.py:55-57, conservative);
the frozen ``_response`` turns the exception into the call's reason ``model_call_exception:BalanceExhausted``, which
``outcomes_ext`` raises again, so the cell stops and the unit pauses with kind ``balance_exhausted``
(``errors.STOP_KINDS``): not a model failure, not an infrastructure unknown, and never re-sent by the frozen Recorder.
The signals: route B's documented one, HTTP 429 whose ``error.code`` is ``insufficient_quota``; for route A the format
is unknown, so HTTP 402, and HTTP 403 or 429 whose body mentions an insufficient balance, quota or credit, or 余额
(``BALANCE_TEXT``), count as exhaustion -- on both routes. Any other 429 is an ordinary rate limit and keeps the frozen
retries (``RATE_BACKOFF``) and the frozen resend path.

``RouteClient`` (``ElucidClient``, ``NorthgateClient``) subclasses the frozen client WITHOUT calling its constructor,
which refuses every model outside the frozen allow-list (weak_solver_probe.py:232-233), and sets the attributes the
inherited ``body`` and ``call`` read (:243-257). The inherited ``body`` (:259-266) then sends the registered request
(with the route's model id); the inherited ``call`` (:305-345) keeps the frozen retries, attempts and receipt
envelope. URL and key are read by path from the route's credential file, whose URL must be the route's approved
endpoint and which, on route A, must also name the registered model (never printed, written or put in an exception);
requests go through the approved PJLAB gateway only, with ``trust_env=False``; an echoed model id outside the route's
registered set is the frozen ``model_mismatch`` (:285-288); route A's set is the registered id and the echo
``ELUCID_ALIAS`` the owner confirmed as the same model (2026-10-23 19:1x).

Every receipt carrying a reply of the route's registered model is checked for reasoning (§4.1). The frozen receipt
drops ``usage.completion_tokens_details`` (:220-224) and keeps only ``reasoning_chars`` (:291-294), so ``_receipt``
reads both signals itself: reasoning tokens other than absent or 0, or any reasoning text, make the reply the existing
``thinking_mismatch`` with subtype ``reasoning_mismatch``, read before the finish reason like the frozen rule
(:295-296). It is undelivered (coevo5/outcomes.py:64-67): the frozen ``Recorder`` re-sends it identically (at most 2,
300 s apart, calls.py:268-279) and a reply still mismatched is an infrastructure unknown (row 4) -- except when its
completion exceeds the ledger bound B: the frozen ``Endpoint._record`` then halts the ledger and raises
``AssumptionBroken`` before any resend (calls.py:198-221, ledger.py:67), a global stop. Such receipts also get
``reasoning_tokens`` (the reported count; None when absent; ``"invalid"`` when not a non-negative integer, which counts
as reasoning), ``visible_completion_tokens`` (completion minus reasoning tokens; None without a valid usage or with an
invalid or inconsistent reasoning count) and ``over_nominal`` (completion tokens above the nominal M; the Endpoint is
built with B, plan §5): P7, counted and scored as usual, never a stop. Receipts without such a reply (transport, HTTP
status, invalid JSON, an error payload, malformed choices, another model's reply) carry none of the three.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

from scripts.weak_solver_probe import GATEWAY, Client, _read_env, _validated_url
from skillopt.coevo5.outcomes import ConfigurationError
from skillopt.coevo5.protocol import READ_TIMEOUT_SECONDS, SOLVER_MAX_TOKENS
from skillopt.continual_eval.core import safe_path

from .errors import BalanceExhausted

GLM_SOLVER = "glm-5.3"  # chain G (§4.1): the frozen MODELS entry, no route
ELUCID_MODEL = "deepseek-v4.1-flash-1017"  # chain D and the smoke (§4.1); route A's model
ELUCID_HOST = "hk.getelucid.com"
ELUCID_PATH = "/v1/chat/completions"
# the model id every delivered reply echoed in the 2026-10-21 gateway probes; smoke S1-a checks it before any other row.
# Since 2026-10-23 02:32 elucid echoes ``ELUCID_ALIAS`` for the unchanged request id (probes 18:44 and 19:07: 8/8
# each); the owner confirmed on 2026-10-23 19:1x that it is deepseek-v4.1-flash-1017 itself (registrar "Owner
# decision 2026-10-23 19:1x"), so it joins the registered echo set from snapshot f on; any other echo stays
# ``model_mismatch``
ELUCID_ALIAS = "deepseek-v4.1-flash"
ELUCID_RESPONSE_MODEL_IDS = frozenset({ELUCID_MODEL, ELUCID_ALIAS})
# route B (registrar row "deepseek route B", owner 2026-10-22 17:3x): the second deepseek provider of chain D
NORTHGATE_MODEL = "deepseek-v4-flash"
NORTHGATE_HOST = "northgate.xiaobei.top"
NORTHGATE_PATH = "/v1/chat/completions"
NORTHGATE_ENV = "/root/.config/weak-solver/northgate.env"  # address and key, read by path only, never printed
# the frozen allow-list's echo set for this request id (weak_solver_probe.py MODELS["deepseek-v4-flash"])
NORTHGATE_RESPONSE_MODEL_IDS = frozenset({"deepseek-v4-flash", "deepseek-flash"})
REASONING_EFFORT = "none"
THINKING_MISMATCH = "thinking_mismatch"  # the frozen undelivered error type the Recorder re-sends
REASONING_MISMATCH = "reasoning_mismatch"
INVALID = "invalid"
# the frozen receipt's error types returned before any part of the reply is read (weak_solver_probe.py:275-288)
ENVELOPE_ERRORS = frozenset({"error_payload", "malformed_choices", "malformed_finish", "model_mismatch"})
# what ``solver_client`` takes per model, exactly (§4.1: chain D's nominal M and read timeout are per bench); chain D's
# config may also name its route (``ROUTE_KEY``; absent: route A)
CONFIG_KEYS = {GLM_SOLVER: frozenset({"repo", "proxy"}),
               ELUCID_MODEL: frozenset({"env_path", "proxy", "max_tokens", "read_timeout"})}
ROUTE_KEY = "route"
ROUTE_A, ROUTE_B = "A", "B"
# balance exhaustion (module docstring): route B's documented code, the statuses that may carry exhaustion, and the
# body text that marks it on HTTP 403 / 429 (read from the leading part of the body and of its decoded JSON, so an
# escaped \u4f59\u989d counts as 余额)
INSUFFICIENT_QUOTA = "insufficient_quota"
BALANCE_STATUSES = frozenset({402, 403, 429})
BALANCE_TEXT = re.compile(r"insufficient[\s_-]*(?:account[\s_-]*)?(?:balance|quota|credits?|funds)"
                          r"|(?:balance|credits?)[\s_-]+(?:is[\s_-]+)?(?:insufficient|exhausted|too[\s_-]+low)"
                          r"|not[\s_-]+enough[\s_-]+(?:balance|credits?)|余额", re.IGNORECASE)
BALANCE_TEXT_BYTES = 8_192
BALANCE_JSON_BYTES = 65_536


@dataclass(frozen=True)
class Route:
    """One provider of chain D's solver (module docstring): ``backend`` (its name in receipts and messages), ``model``
    (the model id the request names), the approved chat endpoint (``host``, ``path``), the credential file's variables
    (``url_key``, ``key_key``; ``model_key``: a variable the file must set to ``model``, route A's only) and the echoed
    model ids a reply of the route may carry."""

    id: str
    backend: str
    model: str
    host: str
    path: str
    url_key: str
    key_key: str
    model_key: str | None
    response_model_ids: frozenset


ROUTES = {
    ROUTE_A: Route(ROUTE_A, "elucid", ELUCID_MODEL, ELUCID_HOST, ELUCID_PATH, "ELUCID_CHAT_URL", "ELUCID_API_KEY",
                   "ELUCID_MODEL", ELUCID_RESPONSE_MODEL_IDS),
    ROUTE_B: Route(ROUTE_B, "northgate", NORTHGATE_MODEL, NORTHGATE_HOST, NORTHGATE_PATH, "NORTHGATE_CHAT_URL",
                   "NORTHGATE_API_KEY", None, NORTHGATE_RESPONSE_MODEL_IDS),
}


def _configured(value, message):
    """``require`` for the run's configuration: a refusal is a ``ConfigurationError`` (row 1)."""
    if not value:
        raise ConfigurationError(message)


def solver_client(model, *, config, transport=None):
    """The solver client of ``model`` (§4.1). ``config`` holds exactly that client's construction inputs
    (``CONFIG_KEYS``): glm-5.3 -- ``repo`` (the credential repository whose ``.env`` names BIGMODEL_CHAT_URL and
    BIGMODEL_API_KEY) and ``proxy``; deepseek-v4.1-flash-1017 -- ``env_path`` (its route's credential file), ``proxy``,
    ``max_tokens`` (the bench's nominal M), ``read_timeout`` (the bench's) and optionally ``route`` (``ROUTES``; absent:
    route A). ``proxy`` must be the approved PJLAB gateway. ``transport``: an ``httpx`` mock transport in tests; a run
    passes none. Any other model, route or config, or a credential the client refuses, raises ``ConfigurationError``."""
    _configured(isinstance(model, str) and model in CONFIG_KEYS, "Not a registered solver model: %s" % str(model)[:60])
    optional = {ROUTE_KEY} if model == ELUCID_MODEL else set()
    _configured(isinstance(config, dict) and set(config) - optional == CONFIG_KEYS[model],
                "The %s solver config holds exactly %s" % (model, sorted(CONFIG_KEYS[model])))
    _configured(config["proxy"] == GATEWAY, "The solver goes through the approved PJLAB gateway only")
    if model == ELUCID_MODEL:
        route = config.get(ROUTE_KEY, ROUTE_A)
        _configured(isinstance(route, str) and route in ROUTE_CLIENTS, "Not a route of chain D: %s" % str(route)[:20])
        return ROUTE_CLIENTS[route](config["env_path"], proxy=config["proxy"], max_tokens=config["max_tokens"],
                                    read_timeout=config["read_timeout"], transport=transport)
    try:  # the v3 factory's construction (coevo5/manifest.py:110-111) with no route
        return unpooled(Client(config["repo"], GLM_SOLVER, proxy=config["proxy"],
                               max_tokens=SOLVER_MAX_TOKENS[GLM_SOLVER], read_timeout=READ_TIMEOUT_SECONDS,
                               transport=transport),
                        proxy=config["proxy"], read_timeout=READ_TIMEOUT_SECONDS, transport=transport)
    except (SystemExit, OSError) as refusal:  # the frozen refusals (weak_solver_probe.py:140-147) carry no secret
        raise ConfigurationError("glm-5.3 credentials: %s" % refusal) from None


def route_of(solver, model=None):
    """What a cell records of the solver its endpoint called (``solver_route``): {"route", "model"} -- the route id and
    the model id the requests named. A client without routes (chain G's frozen client; a test's fake) has route None
    and its own model (else ``model``, the endpoint's)."""
    return {"route": getattr(solver, "route", None),
            "model": getattr(solver, "request_model", None) or getattr(solver, "model", None) or model}


def _credentials(env_path, route=ROUTES[ROUTE_A]):
    """(url, key) of ``route``'s gateway, read by path from its credential file (§4.1): never printed, written or put
    in an exception. The URL must be the route's approved endpoint; route A's file must also name the registered
    model."""
    name = route.backend
    try:
        path = safe_path(env_path)
    except ValueError as refusal:
        raise ConfigurationError("The %s credential file: %s" % (name, refusal)) from None
    _configured(path.is_file(), "The %s credential file does not exist" % name)
    values = _read_env(path)
    if route.model_key is not None:
        _configured(values.get(route.model_key) == route.model, "The %s credential file names another model" % name)
    try:
        url = _validated_url(values.get(route.url_key, ""), route.host, route.path,
                             "%s is not the approved %s chat endpoint" % (route.url_key, name))
    except SystemExit as refusal:
        raise ConfigurationError(str(refusal)) from None
    key = values.get(route.key_key, "")
    _configured(key, "%s missing" % route.key_key)
    return url, key


def balance_signal(status, content):
    """The balance-exhaustion signal of one HTTP answer (module docstring) as a fixed public string, else None: route
    B's documented ``http_429:insufficient_quota``; ``http_402``; ``http_403:balance_text`` or ``http_429:balance_text``
    for a body that mentions an insufficient balance, quota or credit, or 余额. ``content``: the body's bytes, which
    never reach the signal."""
    if status not in BALANCE_STATUSES:
        return None
    if status == 402:
        return "http_402"
    content = bytes(content or b"")
    try:
        data = json.loads(content) if len(content) <= BALANCE_JSON_BYTES else None
    except ValueError:
        data = None
    error = data.get("error") if isinstance(data, dict) else None
    if status == 429 and isinstance(error, dict) and error.get("code") == INSUFFICIENT_QUOTA:
        return "http_429:" + INSUFFICIENT_QUOTA
    text = content[:BALANCE_TEXT_BYTES].decode("utf-8", "replace")
    if data is not None:
        text += "\n" + json.dumps(data, ensure_ascii=False)[:BALANCE_TEXT_BYTES]
    if BALANCE_TEXT.search(text):
        return "http_%d:balance_text" % status
    return None


def _reasoning_tokens(usage):
    """``usage.completion_tokens_details.reasoning_tokens`` as reported: None when absent (or null), the count when it
    is a non-negative integer, else ``INVALID`` (the registered check needs an absent or zero count)."""
    details = usage.get("completion_tokens_details") if isinstance(usage, dict) else None
    if details is None:
        return None
    value = details.get("reasoning_tokens") if isinstance(details, dict) else INVALID
    return value if value is None or (type(value) is int and value >= 0) else INVALID


def _visible(completion, reasoning_tokens):
    """Completion tokens minus reasoning tokens; None without a valid usage or with an invalid or inconsistent count."""
    if completion is None or reasoning_tokens == INVALID:
        return None
    spent = reasoning_tokens or 0
    return completion - spent if spent <= completion else None


# v2.1 (registrar 2026-10-24, every configuration): no connection limit. httpcore 1.0.9 keeps a proxy tunnel whose
# TLS handshake timed out in its pool as an active connection that is never closed or removed
# (``TunnelHTTPConnection.handle_request``: CONNECT, then ``start_tls`` raises ConnectTimeout), so with httpx's default
# of 100 connections the 100th such timeout turned every later request of the client into PoolTimeout while the
# process held no socket -- main-v2's chain D, 2026-10-23 22:10. Concurrency stays bounded by the slot pools
# (``protocol.SLOTS``); keep-alive connections stay at httpx's default 20.
POOL_LIMITS = httpx.Limits(max_connections=None, max_keepalive_connections=20)


def http_client(read_timeout, options):
    """The ``httpx.Client`` of every solver and role client: the frozen client's (weak_solver_probe.py:255-256 --
    timeouts connect 20 s, write 30 s, pool 30 s, the given read timeout; the environment and redirects ignored) with
    ``POOL_LIMITS``. ``options``: {"proxy": the gateway} or, in tests, {"transport": a mock transport}."""
    return httpx.Client(timeout=httpx.Timeout(connect=20, read=read_timeout, write=30, pool=30), limits=POOL_LIMITS,
                        trust_env=False, follow_redirects=False, **options)


def unpooled(frozen, *, proxy, read_timeout, transport=None):
    """``frozen`` -- a frozen client (weak_solver_probe.Client: chain G's solver and the GLM-5.3 roles) -- with its
    httpx client rebuilt by ``http_client`` from the frozen constructor's own options (weak_solver_probe.py:254);
    the frozen request, retries and receipts are unchanged. Returns ``frozen``."""
    options = {"transport": transport} if transport is not None else ({"proxy": proxy} if proxy else {})
    frozen.http.close()
    frozen.http = http_client(read_timeout, options)
    return frozen


class _Guard:
    """A route client's ``httpx.Client`` behind the balance check (module docstring): ``post`` sends nothing once the
    route reported an exhausted balance, and raises ``BalanceExhausted`` for an answer that reports it -- before the
    frozen ``call`` (weak_solver_probe.py:322-330) could retry it. Every other attribute is the httpx client's."""

    def __init__(self, http, owner):
        self._http, self._owner = http, owner

    def post(self, url, **kwargs):
        self._owner.refuse_exhausted()
        response = self._http.post(url, **kwargs)
        signal = balance_signal(response.status_code, response.content)
        if signal is not None:
            self._owner.exhausted = signal
            self._owner.refuse_exhausted()
        return response

    def __getattr__(self, name):
        return getattr(self._http, name)


class RouteClient(Client):
    """deepseek through one of chain D's routes (module docstring; ``ROUTE``: the subclass's): the frozen client's
    request, retries and receipt, the registered reasoning check, the route on every receipt and the balance check.
    ``env_path``: the route's credential file; ``max_tokens``: the nominal M sent in every body (the Endpoint reserves
    and settles with the ledger bound B, plan §5); ``read_timeout``: the bench's (§4.1)."""

    ROUTE = None

    def __init__(self, env_path, *, proxy, max_tokens, read_timeout, transport=None):
        # the frozen constructor is not called: it refuses every model outside its allow-list (module docstring)
        route = self.ROUTE
        _configured(isinstance(route, Route), "A route client names its route")
        _configured(proxy == GATEWAY, "The %s solver goes through the approved PJLAB gateway only" % route.backend)
        _configured(type(max_tokens) is int and max_tokens > 0, "The nominal max_tokens is a positive integer")
        _configured(type(read_timeout) in (int, float) and read_timeout > 0, "The read timeout is a positive number")
        self.url, self._key = _credentials(env_path, route)
        self.backend, self.model, self.max_tokens = route.backend, ELUCID_MODEL, max_tokens
        self.route, self.request_model, self.exhausted = route.id, route.model, None
        self.thinking, self.effort, self.response_model_ids = None, REASONING_EFFORT, route.response_model_ids
        options = {"transport": transport} if transport is not None else {"proxy": proxy}
        self.http = _Guard(http_client(read_timeout, options), self)
        self._transport_errors = (httpx.TransportError,)

    def body(self, system, user):
        """The frozen body (weak_solver_probe.py:259-266) naming the route's model id (route A: the frozen body)."""
        return {**super().body(system, user), "model": self.request_model}

    def call(self, system, user):
        """The frozen call (retries, attempts, receipt); every receipt names the route and the model id it asked."""
        receipt = super().call(system, user)
        return {**receipt, "route": self.route, "route_model": self.request_model}

    def refuse_exhausted(self):
        """``BalanceExhausted`` once the route reported an exhausted balance (the signal only, never the body)."""
        if self.exhausted is not None:
            raise BalanceExhausted("route %s (%s) balance exhausted: %s" % (self.route, self.backend, self.exhausted))

    def _receipt(self, status, data, attempts, started):
        """The frozen receipt, then the reasoning check and the usage fields of §4.1 (module docstring)."""
        receipt = super()._receipt(status, data, attempts, started)
        if receipt.get("error_type") in ENVELOPE_ERRORS:
            return receipt
        tokens = _reasoning_tokens(data.get("usage"))
        text = data["choices"][0]["message"].get("reasoning_content")
        completion = receipt["usage"].get("completion_tokens")
        receipt = {**receipt, "reasoning_tokens": tokens, "visible_completion_tokens": _visible(completion, tokens),
                   "over_nominal": completion is not None and completion > self.max_tokens}
        if tokens not in (None, 0) or text not in (None, ""):
            return {**receipt, "ok": False, "error_type": THINKING_MISMATCH, "subtype": REASONING_MISMATCH}
        return receipt


class ElucidClient(RouteClient):
    """Route A: deepseek-v4.1-flash-1017 through the elucid gateway (§4.1; chain D and the smoke). ``env_path``:
    ``/root/.config/weak-solver/elucid.env`` on the development machine."""

    ROUTE = ROUTES[ROUTE_A]


class NorthgateClient(RouteClient):
    """Route B: deepseek-v4-flash through the northgate gateway (registrar row "deepseek route B"; chain D only, after
    the operator's ``switch-route``). ``env_path``: ``NORTHGATE_ENV`` on the development machine."""

    ROUTE = ROUTES[ROUTE_B]


ROUTE_CLIENTS = {ROUTE_A: ElucidClient, ROUTE_B: NorthgateClient}
