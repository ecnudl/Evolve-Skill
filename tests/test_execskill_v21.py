"""v2.1 (owner decision 2026-10-24 02:22, "好的，那就按照你的说法来，先修，修好之后继续跑"): the run configuration
``main-v2-1`` -- main-v2 whose fix calls never show a flagged text, a matched term or the adjudicator's reason, and
whose C4 fails a procedure that behaves differently when the LiveMath meta option's text is replaced by a neutral
filler -- the unlimited connection pools of every solver and role client (the httpcore tunnel-pool leak that stopped
main-v2's chain D) and the type guards on model-written values (the replay test whose mutation was an object, which
stopped main-v2's chain G); with the Codex review's fixes (2026-10-24): the research Wikipedia client without a cap,
the sheet family's edits inside the worksheet, the shown trajectories without the screens' matched texts. Offline: the
engineer, analysts and leakage adjudicator are FakeGLM behind the real ``Roles``; every procedure runs in the real
worker through FakeDocker; the pool tests talk to a local proxy that never completes a TLS handshake; every procedure,
trajectory and workbook is a synthetic fixture."""
from __future__ import annotations

import json
import random
import socket
import sys
import threading
from types import SimpleNamespace

import httpx
import pytest

from scripts import weak_solver_probe as probe
from skillopt.coevo5.leakage import Corpus
from skillopt.execskill import (budgets, client, engineer, manifest, notes, policy, protocol, replay, research, routes,
                                smoke, step)
from skillopt.execskill.generators import sheet
from skillopt.execskill.package import FIXTURE, empty
from skillopt.execskill.protocol import verified
from tests.execskill_fakes import engineer_reply, fake_config, glm_roles
from tests.test_execskill_engineer import COMPOSER, WORDS
from tests.test_execskill_replay import (LEXICON, META, NOTE, QA, fake, fixture, qa_items, qa_trajectories,  # noqa: F401
                                         source, test_case, trajectory, workers)
from tests.test_execskill_routes import route_b_config
from skillopt.execskill.trajectories import whitelisted
from tests.test_execskill_generators import FakeEngine, _functions as sheet_functions, _sheet_item
from tests.test_execskill_generators import _generate as generated_items
from tests.test_execskill_v2 import coded, reply_of, train_context

SHA = "0" * 64
V2, V21 = protocol.MAIN_V2, protocol.MAIN_V2_1


def configured(name):
    return SimpleNamespace(extra={"configuration": name})


# ------------------------------------------------------------------------------------------- the configuration
def test_main_v2_1_is_main_v2_with_its_own_root_namespaces_and_two_engineer_rules():
    assert V21 == "main-v2-1" and protocol.KIND.fullmatch(V21) and V21 in protocol.CONFIGURATIONS
    assert protocol.LEARNING[V21] == "train" and protocol.STAGE_READ[V21] is True
    for table in (protocol.PILOTS, protocol.TEST_READ_CELLS, protocol.CONFIG_STEP_CAPS, protocol.CONFIG_SCHEDULE_CELLS,
                  protocol.CONFIG_ROLE_CAPS, protocol.CONFIG_GLM_CAP, protocol.CONFIG_CAP_FACTOR,
                  protocol.COST_CHECK_PAUSES):
        assert table[V21] == table[V2]
    assert all(budgets.chain_caps(chain, V21) == budgets.chain_caps(chain, V2) for chain in protocol.CHAINS)
    assert manifest.prompt_sha(V21) == manifest.prompt_sha(V2) and "v2" in manifest.prompt_sha(V21)
    assert smoke.max_role_calls(V21) == smoke.max_role_calls(V2)
    assert smoke.engineer_request_floor(V21) == smoke.engineer_request_floor(V2)
    assert protocol.read_arms_of(V21) == protocol.read_arms_of(V2) and protocol.estimate_arms(V21) == 8
    assert protocol.REAL_RUN_EVIDENCE[V21] == "main_v2_1_real_run" and "main_v2_1_real_run" in protocol.EVIDENCE
    assert protocol.RUN_ROOTS[V21] == protocol.MAIN_V2_1_ROOT == "/data/execskill-20261024-main-v2-1"
    assert protocol.MAIN_V2_1_MANIFEST == "/data/execskill-20261024-main-v2-1-manifest.json"
    assert protocol.MAIN_V2_1_ROOT not in (protocol.MAIN_ROOT, protocol.MAIN_V2_ROOT)
    assert [protocol.namespace_of(configured(V21), c) for c in ("G", "D")] == ["G-v2-1", "D-v2-1"]
    assert [protocol.namespace_of(configured(V2), c) for c in ("G", "D")] == ["G-v2", "D-v2"]
    assert [protocol.namespace_of(configured("main"), c) for c in ("G", "D")] == ["G", "D"]
    assert set(protocol.V21_NAMESPACES.values()) <= set(protocol.NAMESPACES)
    assert set(protocol.FIX_ECHO) == set(protocol.META_COUNTERFACTUAL) == set(protocol.CONFIGURATIONS)
    assert {name for name, echo in protocol.FIX_ECHO.items() if not echo} == {V21}
    assert {name for name, on in protocol.META_COUNTERFACTUAL.items() if on} == {V21}
    with pytest.raises(ValueError, match="route B"):
        routes.check_pins({}, configuration=V21)  # main's chains: chain D pins its route B
    filler = protocol.META_FILLER
    assert not policy.meta_option_hits(filler) and not notes.lexicon_hits(filler, bench="livemath")
    assert not engineer.OPTION_LETTER.search(filler) and filler not in protocol.LIVEMATH_META_OPTION


def test_only_the_train_mode_takes_the_v2_1_rules(tmp_path, workers):
    for rules in ({"echo": False}, {"counterfactual": True}):
        with pytest.raises(ValueError, match="train mode"):
            engineer.Context(bench="searchqa", k=1, step="s1", evidence=FIXTURE, parent=empty(step="s0",
                             evidence=FIXTURE), trajectories=qa_trajectories(), corpora={}, workers=workers,
                             roles=None, label="D/s1-searchqa/engineer", **rules)
    with pytest.raises(ValueError, match="train mode"):
        train_context(tmp_path, workers, [], echo=0)


# ------------------------------------------------------------------------------- unlimited connection pools
class StallingProxy:
    """A local HTTP proxy that answers every CONNECT with 200 and then never speaks, so every TLS handshake through it
    times out -- as the PJLAB gateway's tunnels to elucid did on 2026-10-23 before chain D's pool ran out."""

    def __init__(self):
        self.server = socket.create_server(("127.0.0.1", 0))
        self.url = "http://127.0.0.1:%d" % self.server.getsockname()[1]
        self.held = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            self.held.append(conn)
            try:
                conn.settimeout(5)
                data = b""
                while b"\r\n\r\n" not in data:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            except OSError:
                pass

    def close(self):
        self.server.close()
        for conn in self.held:
            conn.close()


@pytest.fixture
def stalling():
    proxy = StallingProxy()
    yield proxy
    proxy.close()


def outcomes_of(http, n):
    """The exception names of ``n`` requests through the client (the per-request timeout keeps the test short)."""
    out = []
    for _ in range(n):
        try:
            http.post("https://gateway.invalid/v1/chat/completions", json={}, timeout=httpx.Timeout(0.3))
            out.append("ok")
        except httpx.HTTPError as error:
            out.append(type(error).__name__)
    return out


def pools(http):
    """The connection pools of an httpx client: its default transport's and its mounted (proxy) transports'."""
    return [t._pool for t in [http._transport, *http._mounts.values()] if t is not None and hasattr(t, "_pool")]


def test_the_installed_httpcore_keeps_every_timed_out_tunnel_in_its_pool(stalling):
    """The mechanism (control): a pool of two is exhausted by two TLS handshake timeouts through the proxy."""
    with httpx.Client(proxy=stalling.url, limits=httpx.Limits(max_connections=2), trust_env=False) as http:
        assert outcomes_of(http, 3) == ["ConnectTimeout", "ConnectTimeout", "PoolTimeout"]


def test_the_shared_http_client_has_no_connection_limit_so_timeouts_never_exhaust_it(stalling):
    with client.http_client(5, {"proxy": stalling.url}) as http:
        assert pools(http) and all(pool._max_connections == sys.maxsize for pool in pools(http))  # httpcore: None
        assert outcomes_of(http, 6) == ["ConnectTimeout"] * 6
        assert (http._trust_env, http.follow_redirects, http.timeout.connect, http.timeout.read) == (
            False, False, 20, 5)


def test_every_solver_and_role_client_is_built_without_a_connection_limit(tmp_path):
    glm = client.solver_client(client.GLM_SOLVER, config=fake_config(tmp_path, client.GLM_SOLVER))
    elucid = client.solver_client(client.ELUCID_MODEL, config=fake_config(tmp_path, client.ELUCID_MODEL))
    northgate = client.solver_client(client.ELUCID_MODEL, config=route_b_config(tmp_path))
    repo = fake_config(tmp_path, client.GLM_SOLVER)["repo"]
    m = {"root": str(tmp_path), "clients": {
        "solver": {"G": {"model": client.GLM_SOLVER, "env_path": repo, "proxy": probe.GATEWAY}},
        "roles": {"model": protocol.ROLE_MODEL, "max_tokens": protocol.ROLE_MAX_TOKENS, "read_timeout": 600}}}
    role = manifest._clients(m, "G", None)(protocol.ROLE_MODEL, None)
    assert type(glm) is probe.Client and type(role) is probe.Client  # the frozen class, its httpx client rebuilt
    assert (type(elucid), type(northgate)) == (client.ElucidClient, client.NorthgateClient)
    for built, read in ((glm, 2400), (elucid, fake_config(tmp_path, client.ELUCID_MODEL)["read_timeout"]),
                        (northgate, route_b_config(tmp_path)["read_timeout"]), (role, 600)):
        http = built.http
        found = pools(http)
        assert found and all(pool._max_connections == sys.maxsize and pool._max_keepalive_connections == 20
                             for pool in found)
        assert (http._trust_env, http.follow_redirects, http.timeout.read) == (False, False, read)
        assert len(http._mounts) == 1  # the gateway proxy, as the frozen constructor mounts it


# --------------------------------------------------------------------------- model-written values: type guards
ZOO = (None, True, False, 0, 7, -1, 2.5, "", "x", "strip_digits", "applies", "before_call", "c-q1", [], ["strip_digits"],
       [[]], {}, {"strip_digits": True}, {"kind": "applies_true"}, [{"a": None}])
PATHS = (("id",), ("trajectory",), ("hook",), ("claims_fix",), ("property",), ("property", "kind"),
         ("property", "value"), ("property", "step"), ("nonvacuity",), ("nonvacuity", "mutation"),
         ("nonvacuity", "withheld_expect"))
GOOD_TEST = test_case("c-q1", "before_call", {"kind": "note_contains", "value": "17"}, mutation="strip_digits")
CRASHED = {**GOOD_TEST, "nonvacuity": {"withheld_expect": False, "mutation": {"strip_digits": True}}}  # G/s3, r3


def _set(value, path, item):
    """``value`` (a JSON copy) with ``item`` at ``path``; None when a parent on the path is no longer an object."""
    target = value
    for key in path[:-1]:
        target = target.get(key) if isinstance(target, dict) else None
    if not isinstance(target, dict):
        return None
    target[path[-1]] = item
    return value


def anything(rng, depth=0):
    """A random JSON value of the shapes a model may write."""
    roll = rng.randrange(7 if depth < 3 else 4)
    if roll == 0:
        return rng.choice([None, True, False])
    if roll == 1:
        return rng.choice([0, 1, -1, 2.5, 4000, 10 ** 9])
    if roll in (2, 3):
        return rng.choice(ZOO[7:13] + ("new", "revision", "deletion", "narrowing", "searchqa", "fx-old", "x" * 700))
    if roll == 4:
        return [anything(rng, depth + 1) for _ in range(rng.randrange(4))]
    keys = replay.TEST_KEYS + ("kind", "value", "mutation", "withheld_expect", "description", "hooks", "id", "benches")
    return {rng.choice(keys): anything(rng, depth + 1) for _ in range(rng.randrange(4))}


def test_validate_test_answers_every_written_value_with_a_registered_reason():
    procedure = fixture("fx-note", source(NOTE), ("applies", "before_call"))
    entries = {t["cell"]: replay.inputs_of(t) for t in qa_trajectories()}
    assert replay.validate_test(GOOD_TEST, procedure, entries) is None
    assert replay.validate_test(CRASHED, procedure, entries) == "mutation"  # main-v2's TypeError, 2026-10-24 00:01
    for path in PATHS:
        for item in ZOO:
            test = _set(json.loads(json.dumps(GOOD_TEST)), path, item)
            found = replay.validate_test(test, procedure, entries)
            assert found is None or found in engineer.LINT_DETAILS, (path, item, found)
    rng = random.Random(20261024)
    for _ in range(3000):
        test = json.loads(json.dumps(GOOD_TEST)) if rng.random() < 0.8 else anything(rng)
        for _ in range(rng.randrange(1, 4)):
            test = _set(test, rng.choice(PATHS), anything(rng)) or test if isinstance(test, dict) else test
        found = replay.validate_test(test, procedure, entries)
        assert found is None or found in engineer.LINT_DETAILS


def test_random_change_entries_end_in_a_registered_refusal_and_never_raise():
    rng = random.Random(1024)
    parent = empty(step="s0", evidence=FIXTURE)
    skeletons = (lambda: {"kind": "new", "description": "Lists numbers.", "hooks": ["applies", "before_call"],
                          "max_note_chars": 1000, "replay_tests": [json.loads(json.dumps(GOOD_TEST))]},
                 lambda: {"kind": "revision", "revises": "fx-old", "description": "Lists numbers.",
                          "hooks": ["applies", "before_call"], "max_note_chars": 1000},
                 lambda: {"kind": "deletion", "id": "fx-old"},
                 lambda: {"kind": "narrowing", "id": "fx-old", "benches": ["searchqa"]})
    paths = (("kind",), ("id",), ("revises",), ("benches",), ("description",), ("hooks",), ("header",),
             ("max_note_chars",), ("replay_tests",), ("excluded_benches",), ("source",))
    seen = set()
    for _ in range(2000):
        entry = rng.choice(skeletons)()
        for _ in range(rng.randrange(1, 4)):
            entry[rng.choice(paths)[0]] = anything(rng)
        coded_ = isinstance(entry.get("kind"), str) and entry["kind"] in engineer.CODED
        reply = engineer_reply({"changes": [entry]}, [source(NOTE)] if coded_ else [])
        try:
            entries, sources = engineer.parse(reply, lenient=True)
        except engineer.Unparseable as error:
            seen.add("unparseable:%s" % str(error).split(":")[0])
            continue
        for change in engineer.changes_of(entries, sources, SHA):
            problem = engineer._structure(change, parent, set(), train=True)
            assert problem is None or type(problem) is str
            seen.add(problem)
            if problem:
                json.dumps(engineer._structure_detail(change, problem))
            sealed = {"candidate_sha256": None, "engineer": {"dropped": [], "changes": [
                {**change.to_json(), "attempts": [{"failed": "C1"}], "survived": False,
                 "summary": engineer._summary(change)}]}}
            line = step._line(1, sealed, None)
            assert engineer._history_line(line, 2) and line["proposals"][0]["kind"] in engineer.EDIT_KINDS + (None,)
    assert {"kind", "keys", "types", "target_not_in_parent"} <= seen


@pytest.mark.parametrize("kind", [{"x": 1}, ["new"], None, 3])
def test_a_fix_call_on_a_change_of_any_written_kind_never_raises(tmp_path, workers, kind):
    fixed = reply_of(coded("Lists the numbers of the question.", NOTE))
    ctx, glm = train_context(tmp_path, workers, answering(fixed, fixes=[fixed]))
    change = engineer.Change(1, kind, {"kind": kind, "description": "x"}, None, SHA)
    report = engineer.check(change, ctx)
    assert report["failed"] == "C1" and report["checks"][0]["detail"]["problem"] == "kind"
    assert engineer._fix(ctx, change, report, attempt=1) == (None, "another kind or target than the change to fix")


def test_main_v2s_crashing_replay_test_is_an_invalid_test_in_the_lint(tmp_path, workers):
    proposal = reply_of(coded("Lists the numbers of the question.", NOTE, replay_tests=[CRASHED]))
    ctx, glm = train_context(tmp_path, workers, answering(proposal))
    package, sealed = engineer.run_train(ctx)
    sealed = verified(sealed, "engineer")
    assert sealed["changes"][0]["survived"] and package is not None
    (lint,) = sealed["lint"]
    assert {"reason": "invalid_test", "test": 1, "detail": "mutation"} in lint["problems"]


# ------------------------------------------------------------------------------------- fix calls without echo
FINDING = {"pattern": "The solver overlooks part of the item.", "items": ["q1", "m1"], "helper": "List the parts."}
REASON = "It names Ludwig Beethoven, the expected answer."


def answering(proposal, fixes=(), verdict="no"):
    """The analysts name one finding; the engineer proposes ``proposal`` and answers fix calls from ``fixes``; the
    leakage adjudicator answers ``verdict`` with ``REASON``."""
    fixes = list(fixes)

    def answer(system, payload):
        if system == engineer.ANALYST_SYSTEM:
            return engineer_reply({"findings": [FINDING]}, [])
        if system == engineer.ENGINEER_SYSTEM_V2:
            return fixes.pop(0) if payload["request"] == "fix" else proposal
        return {"verdict": verdict, "reason": REASON}

    return answer


def fix_calls(glm):
    return [payload for system, payload in glm.seen if system == engineer.ENGINEER_SYSTEM_V2
            and payload["request"] == "fix"]


@pytest.mark.parametrize("echo", [True, False])
def test_a_fix_call_shows_a_failed_c9_with_or_without_the_matched_term(tmp_path, workers, echo):
    lexicon = reply_of(coded("Tells the solver how to reply.", LEXICON))
    ctx, glm = train_context(tmp_path, workers, answering(lexicon, fixes=[reply_of(coded("Counts words.", WORDS))]),
                             echo=echo)
    package, sealed = engineer.run_train(ctx)
    change = verified(sealed, "engineer")["changes"][0]
    assert change["attempts"][0]["failed"] == "C9" and change["survived"]
    recorded = change["attempts"][0]["checks"][-1]["detail"]
    assert all("detail" in fault for fault in recorded)  # the sealed record keeps the matched term
    (shown,) = fix_calls(glm)
    assert shown["failed"]["check"] == "C9"
    if echo:
        assert shown["failed"]["detail"] == recorded
    else:
        assert shown["failed"]["detail"] == [{k: f[k] for k in ("cell", "hook", "step", "kind")} for f in recorded]


@pytest.mark.parametrize("echo", [True, False])
def test_a_fix_call_shows_a_failed_leakage_check_with_or_without_texts_and_reason(tmp_path, workers, echo):
    composer = reply_of(coded("Names the composer of a sonata.", COMPOSER))
    ctx, glm = train_context(tmp_path, workers, answering(composer, fixes=[reply_of(coded("Counts words.", WORDS))],
                                                          verdict="yes"), echo=echo)
    package, sealed = engineer.run_train(ctx)
    change = verified(sealed, "engineer")["changes"][0]
    recorded = change["attempts"][0]["checks"][-1]
    assert recorded["check"] == "C4" and not recorded["passed"] and recorded["detail"]["adjudicator_reason"] == REASON
    assert all("text" in hit for hit in recorded["detail"]["hits"]) and change["survived"]
    (shown,) = fix_calls(glm)
    detail = shown["failed"]["detail"]
    if echo:
        assert detail == recorded["detail"]
    else:
        assert "adjudicator_reason" not in detail and not any("text" in hit for hit in detail["hits"])
        assert detail["hits"] == [{k: h[k] for k in ("where", "bench", "reasons")} for h in recorded["detail"]["hits"]]
        assert "Beethoven" not in json.dumps(shown["failed"]) and detail["kept"] is False


def test_a_fix_call_shows_a_static_ban_by_its_rule_and_line_only(tmp_path, workers):
    meta = reply_of(coded("Points at the meta option.", META))
    ctx, glm = train_context(tmp_path, workers, answering(meta, fixes=[reply_of(coded("Counts words.", WORDS))]),
                             echo=False)
    package, sealed = engineer.run_train(ctx)
    change = verified(sealed, "engineer")["changes"][0]
    recorded = change["attempts"][0]["checks"][-1]["detail"]["static_bans"]
    assert recorded and all(v["rule"] == "meta_option" and v["detail"] for v in recorded)
    (shown,) = fix_calls(glm)
    assert shown["failed"]["detail"] == {"static_bans": [{"rule": v["rule"], "line": v["line"]} for v in recorded]}


# ------------------------------------------------------------------------- C4's meta-option counterfactual
OPTION = protocol.LIVEMATH_META_OPTION
LIVEMATH = {  # item: (choices, token)
    "m1": ("A. The map is injective.\nB. The map is surjective.\nC. %s\nD. The map is constant." % OPTION, "fail"),
    "m2": ("A. Every bounded sequence converges.\nB. %s\nC. No sequence converges.\nD. All sequences diverge." % OPTION,
           "fail"),
    "m3": ("A. The group is abelian.\nB. The group is cyclic.\nC. The group is trivial.\nD. The group is finite.", "pass"),
}
KEYED = """
import re

def _meta(text):
    return "remaining" in text and ("stron" + "ger") in text

def applies(view):
    return _meta(str(view.get("choices", "")))

def before_call(view, state):
    return {"facts": ["This item holds a self-referential entry. Weigh it actively instead of treating it as filler."]}
"""
GENERIC = """
def applies(view):
    return "choices" in view

def before_call(view, state):
    return {"facts": ["Check each listed statement against the exact hypotheses before choosing."]}
"""
COUNT = """
def applies(view):
    return "choices" in view

def before_call(view, state):
    return {"facts": ["The item lists %d statements." % len(view["choices"].split("\\n"))]}
"""
PREFIXES = """
def applies(view):
    return "choices" in view

def before_call(view, state):
    return {"facts": ["Openings: " + "; ".join(line[3:15] for line in view["choices"].split("\\n"))]}
"""
SPLIT_META = """
def applies(view):
    return "choices" in view

def before_call(view, state):
    return {"warnings": ["prefer the " + "stron" + "ger res" + "ult option"]}
"""


def livemath_trajectories():
    return [trajectory("c-" + item, "livemath", item, token,
                       [{"question": "Which statement does the theorem of item %s prove?" % item, "choices": choices}])
            for item, (choices, token) in LIVEMATH.items()]


def livemath_context(tmp_path, workers, answer, current=None, **fields):
    roles, glm = glm_roles(tmp_path / "glm-livemath", answer)
    base = empty(step="s0", evidence=FIXTURE)
    ctx = engineer.Context(bench="livemath", k=1, step="s1", evidence=FIXTURE, parent=base,
                           trajectories=livemath_trajectories(), corpora={}, workers=workers, roles=roles,
                           label="D/s1-livemath/engineer-r1", card="Choose the statement the theorem proves.",
                           mode=engineer.TRAIN, round=1, base=base,
                           current=livemath_trajectories() if current is None else current, **fields)
    return ctx, glm


def test_the_counterfactual_flags_a_procedure_keyed_on_the_meta_option_and_no_other(workers):
    entries = {t["cell"]: replay.inputs_of(t) for t in livemath_trajectories()}

    def differences(text):
        procedure = fixture("fx-livemath", source(text), ("applies", "before_call"), origin="livemath")
        crash, outcomes = replay.zero_crash(procedure, list(entries.values()), workers)
        assert crash["passed"]
        return replay.meta_counterfactual(procedure, entries, outcomes, workers)

    assert differences(KEYED) == [{"cell": "c-m1", "kind": "meta_counterfactual", "aspects": ["applies", "notes"]},
                                  {"cell": "c-m2", "kind": "meta_counterfactual", "aspects": ["applies", "notes"]}]
    assert differences(GENERIC) == differences(COUNT) == []
    # the registered limit: a note that carries part of the option's text (here: its first words) differs as well;
    # only a whole verbatim quote maps back, which no LiveMath note field can hold unscreened (a table cell holds 40)
    assert [d["aspects"] for d in differences(PREFIXES)] == [["notes"], ["notes"]]
    quoted = [{"hook": "before_call", "step": None, "text": "Quoted: " + OPTION, "public": ""}]
    real = replay.Outcome("c-m1", "livemath", applies=True, notes=quoted)
    counter = replay.Outcome("c-m1", "livemath", applies=True, notes=[
        {**quoted[0], "text": "Quoted: " + protocol.META_FILLER}])
    assert replay._behaviour(real) == replay._behaviour(counter, mapped=True) != replay._behaviour(counter)
    assert replay.meta_counterfactual(fixture("fx-livemath", source(KEYED), ("applies", "before_call")),
                                      {c: e for c, e in entries.items() if c == "c-m3"}, {}, workers) == []


@pytest.mark.parametrize("counterfactual", [False, True])
def test_c4_fails_a_keyed_procedure_only_with_the_counterfactual(tmp_path, workers, counterfactual):
    ctx, glm = livemath_context(tmp_path, workers, answering(""), counterfactual=counterfactual)
    (change,) = engineer.changes_of(*engineer.parse(reply_of(coded("Weighs a self-referential entry.", KEYED)),
                                                    lenient=True), SHA)
    report = engineer.check(change, ctx)
    if counterfactual:
        assert report["failed"] == "C4" and report["checks"][-1]["detail"] == {"output_bans": [
            {"cell": "c-m1", "kind": "meta_counterfactual", "aspects": ["applies", "notes"]},
            {"cell": "c-m2", "kind": "meta_counterfactual", "aspects": ["applies", "notes"]}]}
    else:  # main-v2: nothing stops it before acceptance's J7
        assert report["passed"]


def test_a_training_round_of_main_v2_1_redacts_the_counterfactual_and_takes_the_fix(tmp_path, workers):
    keyed = reply_of(coded("Weighs a self-referential entry.", KEYED))
    ctx, glm = livemath_context(tmp_path, workers, answering(keyed, fixes=[reply_of(coded("Checks hypotheses.",
                                                                                          GENERIC))]),
                                echo=False, counterfactual=True)
    package, sealed = engineer.run_train(ctx)
    change = verified(sealed, "engineer")["changes"][0]
    assert [a["failed"] for a in change["attempts"]] == ["C4", None] and change["survived"]
    (shown,) = fix_calls(glm)
    assert shown["failed"]["detail"] == {"rule": engineer.COUNTERFACTUAL_RULE, "output_bans": [
        {"cell": "c-m1", "kind": "meta_counterfactual", "aspects": ["applies", "notes"]},
        {"cell": "c-m2", "kind": "meta_counterfactual", "aspects": ["applies", "notes"]}]}
    assert package is not None and package.procedures[0].description == "Checks hypotheses."


@pytest.mark.parametrize("echo", [True, False])
def test_a_screened_meta_option_note_reaches_the_fix_call_without_its_matched_phrase(tmp_path, workers, echo):
    split = reply_of(coded("Points the solver at an option.", SPLIT_META))
    ctx, glm = livemath_context(tmp_path, workers, answering(split, fixes=[reply_of(coded("Checks hypotheses.",
                                                                                          GENERIC))]),
                                echo=echo, counterfactual=True)
    package, sealed = engineer.run_train(ctx)
    change = verified(sealed, "engineer")["changes"][0]
    recorded = change["attempts"][0]["checks"][-1]["detail"]["output_bans"]
    assert {b["kind"] for b in recorded} == {"note_meta_option"} and all(b["detail"] for b in recorded)
    (shown,) = fix_calls(glm)
    if echo:
        assert shown["failed"]["detail"] == {"output_bans": recorded}
    else:
        assert shown["failed"]["detail"] == {"output_bans": [
            {"cell": b["cell"], "hook": b["hook"], "step": b["step"], "kind": "note_meta_option"} for b in recorded]}
        assert "stronger" not in json.dumps(shown["failed"])


# ----------------------------------------------------------------------------- Codex review 2026-10-24 (#1-#3)
def test_the_research_wikipedia_client_has_no_connection_limit_either(stalling):
    """#1: the chain's Wikipedia client goes through the same gateway, so its pool had the same leak."""
    wikipedia = research.Wikipedia(proxy=stalling.url, timeout=0.3)
    http = wikipedia.client
    assert pools(http) and all(pool._max_connections == sys.maxsize and pool._max_keepalive_connections == 20
                               for pool in pools(http))
    found = []
    for _ in range(4):
        with pytest.raises(research.FetchError) as error:
            wikipedia._get({"action": "query"})
        found.append(str(error.value))
    assert found == ["transport:ConnectTimeout"] * 4
    assert (http._trust_env, http.follow_redirects, http.headers["User-Agent"]) == (False, False, research.USER_AGENT)


@pytest.mark.parametrize("edit, reason", [({"cell": "A1048577", "formula": "=SUM(A1)"}, "edit_target_invalid"),
                                          ({"cell": "XFE1", "formula": "=SUM(A1)"}, "edit_target_invalid"),
                                          ({"cell": "A3", "formula": "=SUM(A1)\x01"}, "format")])
def test_a_written_edit_outside_the_worksheet_or_unstorable_is_a_registered_drop(tmp_path, edit, reason):
    """#2: the first edit raised openpyxl's ValueError and the third its IllegalCharacterError past the family's
    validation, which ``generate`` does not catch; each is now a registered drop before any file is written."""
    fake = FakeEngine()
    made = generated_items(sheet.FAMILY, [{"edits": [edit]}], sheet_functions(), engine=fake.engine(),
                           source_items=[_sheet_item(tmp_path / "items")], out_dir=tmp_path / "generated")
    assert made["items"] == [] and made["dropped"] == {reason: 1} and fake.log == []
    assert not (tmp_path / "generated").exists() or list((tmp_path / "generated").iterdir()) == []


HIT = "one of the remaining"


def screened(t):
    """``t`` resealed with a shell that recorded two screen hits -- the faults and the dropped fields, as the solver
    shell writes them -- beside a crash and a field over its cap."""
    shell = dict(t["shell"], faults=[
        {"procedure": "p-old", "hook": "before_call", "kind": "note_meta_option", "exc_type": None, "message": HIT},
        {"procedure": "p-old", "hook": "before_call", "kind": "note_lexicon", "exc_type": None, "message": "answer is"},
        {"procedure": "p-new", "hook": "before_call", "kind": "exception", "exc_type": "KeyError", "message": "'x'"}],
        notes=[{"id": "p-old", "hook": "before_call", "fields": {}, "rendered_chars": 0, "dropped": [
            {"field": "warnings", "reason": "meta_option", "detail": HIT},
            {"field": "facts", "reason": "lexicon", "detail": "answer is"},
            {"field": "candidates", "reason": "cap", "detail": ""}]}])
    fields = {k: v for k, v in t.items() if k not in ("version", "evidence", protocol.RECORD_HASH)}
    return protocol.record("trajectory", t["evidence"], dict(fields, shell=shell))


def test_with_echo_off_a_shown_trajectory_keeps_the_screens_kinds_and_leaves_out_their_matches():
    """#3: the message of a screen fault and the detail of a screened field are the matched texts."""
    t = screened(livemath_trajectories()[0])
    on, off = engineer._shown_view("failures", t, {}), engineer._shown_view("failures", t, {}, False)
    assert on["shell"] == whitelisted(t)["shell"]  # echo on (every configuration but main-v2-1): unchanged
    assert [f["message"] for f in off["shell"]["faults"]] == [None, None, "'x'"]
    assert [f["kind"] for f in off["shell"]["faults"]] == [f["kind"] for f in on["shell"]["faults"]]
    assert [d["detail"] for d in off["shell"]["notes"][0]["dropped"]] == [None, None, ""]
    assert [d["reason"] for d in off["shell"]["notes"][0]["dropped"]] == ["meta_option", "lexicon", "cap"]
    assert {k: v for k, v in off.items() if k != "shell"} == {k: v for k, v in on.items() if k != "shell"}
    assert HIT not in json.dumps(off["shell"]) and "answer is" not in json.dumps(off["shell"])


@pytest.mark.parametrize("echo", [True, False])
def test_the_proposal_and_analyst_calls_show_the_screens_matches_only_with_echo(tmp_path, workers, echo):
    """#3 end to end: a training round's analyst and proposal calls over trajectories with screen hits."""
    ctx, glm = livemath_context(tmp_path, workers, answering(reply_of(coded("Checks hypotheses.", GENERIC))),
                                current=[screened(t) for t in livemath_trajectories()], echo=echo,
                                counterfactual=not echo)
    engineer.run_train(ctx)
    shown = [(payload["request"], t) for system, payload in glm.seen
             if system in (engineer.ANALYST_SYSTEM, engineer.ENGINEER_SYSTEM_V2)
             and payload.get("request") in ("analyse", "propose") for t in payload["trajectories"]]
    assert {request for request, _ in shown} == {"analyse", "propose"}
    messages = {f["message"] for _, t in shown for f in t["shell"]["faults"]}
    details = {d["detail"] for _, t in shown for n in t["shell"]["notes"] for d in n["dropped"]}
    if echo:
        assert messages == {HIT, "answer is", "'x'"} and details == {HIT, "answer is", ""}
    else:
        assert messages == {None, "'x'"} and details == {None, ""}
