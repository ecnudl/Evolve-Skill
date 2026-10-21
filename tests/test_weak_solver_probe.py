"""Solver-strength probe (scripts/weak_solver_probe.py): the learning stages' prompt, the frozen scorers, a real client
against a mock HTTP transport."""
import json

import httpx
import pytest

from scripts import weak_solver_probe as probe

URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


def _panel(path, extra=None):
    tasks = []
    for i in range(4):
        tasks.append({"task_id": "g%d" % i, "family_id": "f%d" % i, "project_id": "", "partition": "skill_confirmation",
                      "public": {"question": "What is value %d, rounded to the nearest hundredths place?" % i,
                                 "context": "| v%d | 4%d.00 |" % (i, i)},
                      "private": {"answer": "4%d.00" % i}})
    tasks += extra or []
    path.write_text(json.dumps({"tasks": tasks}))
    return path


def _repo(tmp_path):
    (tmp_path / ".env").write_text("BIGMODEL_CHAT_URL=%s\nBIGMODEL_API_KEY=secret-xyz\n" % URL)
    return tmp_path


def _reply(content, *, model="glm-4.7-flash", finish="stop", usage=True, extra=None):
    body = {"model": model, "choices": [{"finish_reason": finish, "message": {"content": content, "reasoning_content": "r"}}]}
    if usage:
        body["usage"] = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
    body.update(extra or {})
    return body


class Server:
    """A mock BigModel: answers correctly when the Skill text mentions 'decimals', otherwise drops them."""

    def __init__(self, mode=None):
        self.mode, self.requests = mode, []

    def __call__(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        assert request.headers["authorization"] == "Bearer secret-xyz" and request.url == URL
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        n = json.loads(user)["question"].split("value ")[1].split(",")[0]
        answer = "<answer>4%s%s</answer>" % (n, ".00" if "decimals" in system else "")
        if self.mode == "auth":
            return httpx.Response(401, text="unauthorized")
        return httpx.Response(200, json=_reply(answer, model=body["model"]))


def factory(server):
    def make(repo, model, *, proxy, max_tokens, router_env=None):
        return probe.Client(repo, model, proxy=proxy, max_tokens=max_tokens, router_env=router_env,
                            transport=httpx.MockTransport(server))
    return make


def test_probe_scores_every_skill_on_every_item_and_run(tmp_path, capsys):
    repo, server = _repo(tmp_path), Server()
    panel = _panel(tmp_path / "panel.json")
    skill = tmp_path / "skill.md"
    skill.write_text("Give the requested decimals.")
    out = tmp_path / "out"
    probe.main(["run", "--model", "glm-4.7-flash", "--benchmark", "officeqa", "--repo", str(repo),
                "--items", "%s:skill_confirmation" % panel, "--skill", "empty=none", "--skill", "dec=f:%s" % skill,
                "--runs", "2", "--workers", "2", "--output", str(out)], client_factory=factory(server))
    summary = json.loads((out / "summary.json").read_text())
    assert summary["status"] == "completed" and summary["cells"] == 16 and summary["unknown_cells"] == 0
    assert summary["per_skill"]["dec"]["pass"] == 8 and summary["per_skill"]["empty"]["pass"] == 0
    pair = summary["pairs"]["dec - empty"]
    assert {k: pair["items"][k] for k in ("better", "worse", "tied", "excluded_all_unknown", "partially_known")} == \
        {"better": 4, "worse": 0, "tied": 0, "excluded_all_unknown": 0, "partially_known": 0}
    assert pair["items"]["sign_test_p"] == pytest.approx(0.125)
    assert pair["cells"]["wins"] == 8 and summary["stability"]["dec"]["always_pass"] == 4
    # the stages' prompt: Skill in the system prompt, only public fields in the user payload, thinking on, temperature 0
    assert all(set(json.loads(b["messages"][1]["content"])) == {"question", "context"} for b in server.requests)
    assert any("Frozen skill guidance" in b["messages"][0]["content"] for b in server.requests)
    assert all(b["thinking"] == {"type": "enabled"} and b["temperature"] == 0 and b["max_tokens"] == 32768 for b in server.requests)
    assert "secret" not in (out / "config.json").read_text() and "secret" not in json.dumps(summary)
    probe.main(["report", "--output", str(out)])
    assert "dec - empty" in capsys.readouterr().out


def test_only_completed_replies_of_the_requested_model_are_scored(tmp_path):
    client = probe.Client(_repo(tmp_path), "glm-4.7-flash", proxy=None, max_tokens=1024,
                          transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    t = 0.0
    ok = client._receipt(200, _reply("<answer>1</answer>"), [], t)
    assert ok["ok"] is True
    for finish in ("sensitive", "content_filter", "network_error", "tool_calls", None, "length"):
        receipt = client._receipt(200, _reply("<answer>1</answer>", finish=finish), [], t)
        assert receipt["ok"] is False
        assert probe.backends.solve("officeqa", {"question": "q", "context": "c"}, "", lambda s, u: receipt)["status"] == "unknown"
    assert client._receipt(200, _reply("<answer>1</answer>", model="glm-5.3"), [], t)["error_type"] == "model_mismatch"
    assert client._receipt(200, _reply("<answer>1</answer>", extra={"error": {"code": "1"}}), [], t)["error_type"] == "error_payload"
    assert client._receipt(200, {"model": "glm-4.7-flash", "choices": []}, [], t)["error_type"] == "malformed_choices"
    bad_usage = client._receipt(200, _reply("<answer>1</answer>", extra={"usage": "bad"}), [], t)
    assert bad_usage["ok"] is True and bad_usage["usage"] == {} and bad_usage["usage_valid"] is False
    for model in ("glm-4.7-flash", "glm-5.3", None):  # matching, mismatched and missing model ids
        for finish in ([], {}, 3):
            body = _reply("<answer>1</answer>", finish=finish, model=model)
            if model is None:
                body.pop("model")
            receipt = client._receipt(200, body, [], t)
            assert receipt["error_type"] == "malformed_finish" and receipt["finish_reason"] is None
            assert probe.backends.solve("officeqa", {"question": "q", "context": "c"}, "", lambda s, u: receipt)["status"] == "unknown"
    reasoning_only = client._receipt(200, _reply(None), [], t)
    assert reasoning_only["ok"] is False and reasoning_only["error_type"] == "content_missing"
    blank = client._receipt(200, _reply("   "), [], t)  # a delivered blank reply: the frozen 'completed without text'
    assert blank["error_type"] == "empty_content" and probe.backends.solve(
        "officeqa", {"question": "q", "context": "c"}, "", lambda s, u: blank)["status"] == "available"


def test_permanent_errors_are_not_retried_and_stop_the_probe_at_the_first_cell(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda s: None)
    repo, server = _repo(tmp_path), Server(mode="auth")
    client = factory(server)(repo, "glm-4.7-flash", proxy=None, max_tokens=1024)
    receipt = client.call("s", json.dumps({"question": "value 1, x", "context": "c"}))
    assert receipt["error_type"] == "http_401" and len(server.requests) == 1  # no retry of an authorization failure
    panel = _panel(tmp_path / "panel.json")
    with pytest.raises(SystemExit):
        probe.main(["run", "--model", "glm-4.7-flash", "--benchmark", "officeqa", "--repo", str(repo),
                    "--items", "%s:skill_confirmation" % panel, "--skill", "empty=none", "--runs", "2",
                    "--output", str(tmp_path / "out")], client_factory=factory(server))
    assert len(server.requests) == 2  # the first cell only
    assert json.loads((tmp_path / "out" / "summary.json").read_text())["status"] == "aborted_at_first_cell"


@pytest.mark.parametrize("failure", ["transport", "http_422", "invalid_json"])
def test_the_batch_opens_only_after_a_validated_first_response(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(probe.time, "sleep", lambda s: None)
    requests = []

    def server(request):
        requests.append(request)
        if failure == "transport":
            raise httpx.ConnectError("boom")
        if failure == "http_422":
            return httpx.Response(422, json={"error": {"code": "x"}})
        return httpx.Response(200, text="not json")

    repo = _repo(tmp_path)
    with pytest.raises(SystemExit):
        probe.main(["run", "--model", "glm-4.7-flash", "--benchmark", "officeqa", "--repo", str(repo),
                    "--items", "%s:skill_confirmation" % _panel(tmp_path / "p.json"), "--skill", "e=none",
                    "--runs", "2", "--output", str(tmp_path / "out")], client_factory=factory(server))
    assert json.loads((tmp_path / "out" / "summary.json").read_text())["status"] == "aborted_at_first_cell"
    assert len(list((tmp_path / "out" / "records").rglob("*.json"))) == 1  # one cell, never the batch
    assert len(requests) == (4 if failure == "transport" else 1)  # transport is retried, a 422 or bad JSON is not


def test_inputs_are_refused_when_unsafe(tmp_path):
    repo = _repo(tmp_path)
    leak = [{"task_id": "t0", "family_id": "x0", "project_id": "", "partition": "final",
             "public": {"question": "q", "context": "c"}, "private": {"answer": "1"}}]
    panel = _panel(tmp_path / "panel.json", leak)
    base = ["run", "--model", "glm-4.7-flash", "--benchmark", "officeqa", "--repo", str(repo), "--skill", "e=none"]
    clean = _panel(tmp_path / "clean.json")
    for argv in (["--items", str(panel), "--output", str(tmp_path / "a")],                        # a final task in the file
                 ["--items", "%s:nothing" % clean, "--output", str(tmp_path / "b")]):              # empty selection
        with pytest.raises(SystemExit):
            probe.main(base + argv, client_factory=factory(Server()))
    with pytest.raises(SystemExit):  # two names that collide on a case-insensitive filesystem
        probe.main(["run", "--model", "glm-4.7-flash", "--benchmark", "officeqa", "--repo", str(repo), "--skill", "a=none",
                    "--skill", "A=none", "--items", "%s:skill_confirmation" % clean, "--output", str(tmp_path / "e")],
                   client_factory=factory(Server()))
    pilot = tmp_path / "items.json"
    pilot.write_text(json.dumps({"items": [{"id": "u1", "meta": {"part": "test"}, "public": {"question": "q", "context": "c"},
                                            "private": {"answer": "1"}}]}))
    with pytest.raises(SystemExit):
        probe.main(base + ["--items", str(pilot), "--output", str(tmp_path / "c")], client_factory=factory(Server()))
    good = tmp_path / "pilot.json"
    good.write_text(json.dumps({"items": [{"id": "u1", "meta": {"part": "train"}, "public": {"question": "q", "context": "c"},
                                           "private": {"answer": "1"}}]}))
    assert probe.load_items(str(good))[0]["label"] == "train"
    with pytest.raises(SystemExit):  # a suffix never relabels a pilot file
        probe.load_items("%s:skill_confirmation" % good)
    with pytest.raises(SystemExit):
        probe.load_skill("../x=none")
    with pytest.raises(SystemExit):
        probe.load_skill("/abs=none")
    with pytest.raises(SystemExit):
        probe.main(["run", "--model", "gpt-x", "--benchmark", "officeqa", "--repo", str(repo), "--skill", "e=none",
                    "--items", "%s:skill_confirmation" % _panel(tmp_path / "p2.json"), "--output", str(tmp_path / "d")])
    probe.write_once(tmp_path / "w" / "x.json", {"a": 1})
    with pytest.raises(FileExistsError):
        probe.write_once(tmp_path / "w" / "x.json", {"a": 2})
    assert json.loads((tmp_path / "w" / "x.json").read_text()) == {"a": 1}


def test_credentials_are_validated_and_never_echoed(tmp_path):
    for url in ("https://evil.example/api/paas/v4/chat/completions", "https://open.bigmodel.cn:secret-xyz/api"):
        (tmp_path / ".env").write_text("BIGMODEL_CHAT_URL=%s\nBIGMODEL_API_KEY=secret-xyz\n" % url)
        with pytest.raises(SystemExit) as exc:
            probe.bigmodel_credentials(tmp_path)
        assert "secret" not in str(exc.value) and exc.value.__cause__ is None
    with pytest.raises(SystemExit):
        probe.Client(_repo(tmp_path), "glm-4.7-flash", proxy="http://other:3128", max_tokens=1024)


def test_item_level_denominators_count_ties_unknowns_and_partial_items():
    records = []
    for item, a, b in (("i1", ["pass", "pass"], ["fail", "fail"]),        # better
                       ("i2", ["pass", "fail"], ["fail", "pass"]),        # tied (net 0)
                       ("i3", ["unknown", "unknown"], ["pass", "pass"]),  # all unknown jointly: excluded
                       ("i4", ["pass", "unknown"], ["fail", "fail"]),     # partly known, better on the known run
                       ("i5", ["fail", "fail"], ["pass", "fail"])):       # worse
        for run in range(2):
            records.append({"skill": "a", "item": item, "run": run, "status": a[run], "usage": {}})
            records.append({"skill": "b", "item": item, "run": run, "status": b[run], "usage": {}})
    items = probe.summarize(records, ["a", "b"], 2)["pairs"]["a - b"]["items"]
    assert (items["better"], items["worse"], items["tied"], items["excluded_all_unknown"], items["partially_known"]) == (2, 1, 1, 1, 1)


def test_report_shows_unknown_runs_as_not_available(tmp_path, capsys):
    out = tmp_path / "out"
    out.mkdir()
    config = {"model": "glm-4.7-flash", "benchmark": "officeqa", "n_items": 1, "runs": 1, "items_hash": "h",
              "skills": {"e": {"hash": "x", "bytes": 0}}}
    (out / "config.json").write_text(json.dumps(config))
    summary = probe.summarize([{"skill": "e", "item": "i", "run": 0, "status": "unknown", "usage": {}, "error_type": "transport"}], ["e"], 1)
    (out / "summary.json").write_text(json.dumps({**summary, "status": "completed", "config_hash": probe.digest(config)}))
    probe.main(["report", "--output", str(out)])
    assert "N/A" in capsys.readouterr().out


ROUTER_URL = "https://free-router.opendatalab.com/v1/chat/completions"


def _router_env(tmp_path):
    env = tmp_path / "router.env"
    env.write_text("OPENDATALAB_ROUTER_URL=https://free-router.opendatalab.com\nOPENDATALAB_ROUTER_KEY=router-secret\n")
    return env


class RouterServer:
    """A mock free-router that gates on X-Session-Id and may echo a canonical model id different from the request."""

    MODEL_ECHO = {"deepseek-v4-flash": "deepseek-flash", "Qwen/Qwen3.5-9B": "Qwen/Qwen3.5-9B"}

    def __init__(self):
        self.requests, self.session_ids = [], []

    def __call__(self, request):
        body = json.loads(request.content)
        self.requests.append((request, body))
        assert request.url == ROUTER_URL
        assert request.headers["authorization"] == "Bearer router-secret"
        sid = request.headers.get("x-session-id")
        if not sid:
            return httpx.Response(456, json={"error": {"message": "This gateway only serves agent requests.",
                                                       "type": "proxy_forbidden", "code": "session_id_required"}})
        self.session_ids.append(sid)
        model = body["model"]
        n = json.loads(body["messages"][1]["content"])["question"].split("value ")[1].split(",")[0]
        return httpx.Response(200, json=_reply("<answer>4%s.00</answer>" % n, model=self.MODEL_ECHO[model]))


@pytest.mark.parametrize("model", ["deepseek-v4-flash", "Qwen/Qwen3.5-9B"])
def test_free_router_model_sends_x_session_id_and_omits_thinking(tmp_path, model):
    import uuid as _uuid
    env, server = _router_env(tmp_path), RouterServer()
    panel = _panel(tmp_path / "panel.json")
    probe.main(["run", "--model", model, "--benchmark", "officeqa", "--router-env", str(env),
                "--items", "%s:skill_confirmation" % panel, "--skill", "e=none", "--runs", "2", "--workers", "2",
                "--output", str(tmp_path / "out")], client_factory=factory(server))
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    config = json.loads((tmp_path / "out" / "config.json").read_text())
    assert summary["status"] == "completed" and summary["unknown_cells"] == 0
    assert summary["per_skill"]["e"]["pass"] == 8  # 4 items x 2 runs, mock always answers correctly
    assert config["backend"] == "free_router" and config["session_id_header"] == "X-Session-Id"
    assert config["thinking"] is None and config["reasoning_effort"] is None
    assert config["model"] == model
    sids = server.session_ids
    assert len(sids) == len(server.requests) == 8
    assert len(set(sids)) == 8  # a fresh UUID per call
    for s in sids:
        assert _uuid.UUID(s).version == 4  # standard UUID v4
    for _, body in server.requests:
        assert "thinking" not in body and "reasoning_effort" not in body
    # neither the key nor any session UUID appears in any persisted artifact (config, summary, every record)
    record_blob = "".join(p.read_text() for p in (tmp_path / "out" / "records").rglob("*.json"))
    text = (tmp_path / "out" / "config.json").read_text() + json.dumps(summary) + record_blob
    for leak in ("router-secret",) + tuple(sids):
        assert leak not in text


@pytest.mark.parametrize("failure", ["429", "transport"])
def test_free_router_rotates_x_session_id_across_retries(tmp_path, monkeypatch, failure):
    """Each HTTP attempt (429 or transport retry) gets its own fresh UUID; the second call is independent."""
    import uuid as _uuid
    monkeypatch.setattr(probe.time, "sleep", lambda s: None)
    env = _router_env(tmp_path)
    attempts = {"n": 0}
    seen = []

    def server(request):
        sid = request.headers.get("x-session-id")
        seen.append(sid)
        attempts["n"] += 1
        if attempts["n"] in (1, 3):  # first HTTP of each call retries once
            if failure == "429":
                return httpx.Response(429, json={"error": {"code": "rate"}})
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json=_reply("<answer>40.00</answer>", model="deepseek-flash"))

    client = factory(server)(_repo(tmp_path), "deepseek-v4-flash", proxy=None, max_tokens=1024, router_env=env)
    r1 = client.call("sys", json.dumps({"question": "value 0, x", "context": "c"}))
    r2 = client.call("sys", json.dumps({"question": "value 0, x", "context": "c"}))
    assert r1["ok"] and r2["ok"] and len(seen) == 4 and len(set(seen)) == 4
    for s in seen:
        assert _uuid.UUID(s).version == 4


def test_router_credentials_require_approved_endpoint(tmp_path):
    good = tmp_path / "router.env"
    good.write_text("OPENDATALAB_ROUTER_URL=https://free-router.opendatalab.com\nOPENDATALAB_ROUTER_KEY=router-secret\n")
    url, key = probe.router_credentials(good)
    assert url == ROUTER_URL and key == "router-secret"
    bad_urls = (
        "https://evil.example",                                      # wrong host
        "http://free-router.opendatalab.com",                        # not https
        "https://free-router.opendatalab.com:8080",                  # non-standard port
        "https://free-router.opendatalab.com:bad-port",              # malformed port
        "https://free-router.opendatalab.com?q=1",                   # query string
        "https://user:router-secret@free-router.opendatalab.com",    # credentials in URL
        "https://free-router.opendatalab.com#frag",                  # fragment
        "https://free-router.opendatalab.com/wrong",                 # unexpected path appended
        "https://open.bigmodel.cn",                                  # the BigModel host via the wrong backend
    )
    for bad in bad_urls:
        bad_env = tmp_path / "bad.env"
        bad_env.write_text("OPENDATALAB_ROUTER_URL=%s\nOPENDATALAB_ROUTER_KEY=router-secret\n" % bad)
        with pytest.raises(SystemExit) as exc:
            probe.router_credentials(bad_env)
        assert "router-secret" not in str(exc.value)
    empty = tmp_path / "empty.env"
    empty.write_text("OPENDATALAB_ROUTER_URL=https://free-router.opendatalab.com\n")
    with pytest.raises(SystemExit) as exc:
        probe.router_credentials(empty)
    assert "missing" in str(exc.value).lower()


def test_free_router_requires_router_env_and_bigmodel_requires_repo(tmp_path):
    repo = _repo(tmp_path)
    env = _router_env(tmp_path)
    panel = _panel(tmp_path / "panel.json")
    # free-router model without --router-env
    with pytest.raises(SystemExit) as exc:
        probe.main(["run", "--model", "deepseek-v4-flash", "--benchmark", "officeqa", "--repo", str(repo),
                    "--items", "%s:skill_confirmation" % panel, "--skill", "e=none",
                    "--output", str(tmp_path / "a")], client_factory=factory(RouterServer()))
    assert "router-env" in str(exc.value)
    # BigModel model without --repo
    with pytest.raises(SystemExit) as exc:
        probe.main(["run", "--model", "glm-4.7-flash", "--benchmark", "officeqa", "--router-env", str(env),
                    "--items", "%s:skill_confirmation" % panel, "--skill", "e=none",
                    "--output", str(tmp_path / "b")], client_factory=factory(Server()))
    assert "repo" in str(exc.value)


def test_wrong_or_malformed_echoed_model_id_marks_cell_unknown(tmp_path):
    """Includes list/dict echoes which would raise TypeError on a naive ``in frozenset`` check."""
    env = _router_env(tmp_path)
    # unit-level: non-str model echoes stay as mismatches, not crashes
    with_env = _router_env(tmp_path)  # noqa: F841  # ensure the real router_credentials runs
    client = factory(lambda r: httpx.Response(200, json={}))(
        _repo(tmp_path), "deepseek-v4-flash", proxy=None, max_tokens=1024, router_env=with_env)
    for weird in ("deepseek-other", "DeepSeek-Flash", "deepseek-flash-extra", "Qwen/Qwen3.5-9B", None, [], {}, 7):
        receipt = client._receipt(200, _reply("<answer>1</answer>", model=weird), [], 0.0)
        assert receipt["error_type"] == "model_mismatch" and receipt["ok"] is False
    # for a matching alias (deepseek-flash), ok is True
    assert client._receipt(200, _reply("<answer>1</answer>", model="deepseek-flash"), [], 0.0)["ok"] is True

    # end-to-end: an unapproved echo aborts at the first cell
    def server(request):
        return httpx.Response(200, json=_reply("<answer>40.00</answer>", model="deepseek-other"))

    panel = _panel(tmp_path / "panel.json")
    with pytest.raises(SystemExit):
        probe.main(["run", "--model", "deepseek-v4-flash", "--benchmark", "officeqa", "--router-env", str(env),
                    "--items", "%s:skill_confirmation" % panel, "--skill", "e=none",
                    "--output", str(tmp_path / "out")], client_factory=factory(server))
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary["status"] == "aborted_at_first_cell" and summary["error_type"] == "model_mismatch"


def test_bigmodel_client_factory_signature_unchanged(tmp_path):
    """A legacy factory with the old (repo, model, *, proxy, max_tokens) signature still works for BigModel models."""
    repo = _repo(tmp_path)

    def legacy_factory(r, m, *, proxy, max_tokens):
        assert m == "glm-4.7-flash"
        return probe.Client(r, m, proxy=proxy, max_tokens=max_tokens, transport=httpx.MockTransport(Server()))

    panel = _panel(tmp_path / "panel.json")
    probe.main(["run", "--model", "glm-4.7-flash", "--benchmark", "officeqa", "--repo", str(repo),
                "--items", "%s:skill_confirmation" % panel, "--skill", "e=none",
                "--output", str(tmp_path / "out")], client_factory=legacy_factory)
    assert json.loads((tmp_path / "out" / "summary.json").read_text())["status"] == "completed"


PJLAB_URL = "https://token.pjlab.org.cn/v1/chat/completions"


def _plain(reply):
    """A reply of the non-thinking serving: no reasoning text."""
    del reply["choices"][0]["message"]["reasoning_content"]
    return reply


def test_the_pjlab_route_is_opt_in_with_its_own_allow_list_and_credential_file(tmp_path):
    """coevo5 v3 §9: deepseek-v4-flash through the PJLAB token endpoint, only for a caller that names the route."""
    env, seen = tmp_path / "pjlab-token.env", []
    env.write_text("PJLAB_TOKEN_API_KEY=pjlab-secret\n")

    def server(request):
        seen.append(request)
        assert request.url == PJLAB_URL and request.headers["authorization"] == "Bearer pjlab-secret"
        assert "x-session-id" not in request.headers
        body = json.loads(request.content)
        assert body["max_tokens"] == 32768 and body["temperature"] == 0 and body["thinking"] == {"type": "disabled"}
        assert "reasoning_effort" not in body  # the route names the one thinking mode every upstream honours
        return httpx.Response(200, json=_plain(_reply("<answer>1</answer>", model=body["model"])))

    client = probe.Client(None, "deepseek-v4-flash", proxy=None, max_tokens=32768, route="pjlab_token",
                          route_env=env, transport=httpx.MockTransport(server))
    receipt = client.call("sys", "user")
    assert receipt["ok"] and receipt["returned_model"] == "deepseek-v4-flash" and client.backend == "pjlab_token"
    assert len(seen) == 1 and "pjlab-secret" not in json.dumps(receipt)
    # the free router's canonical echo is not this route's
    assert client._receipt(200, _plain(_reply("<answer>1</answer>", model="deepseek-flash")), [], 0.0)["error_type"] == \
        "model_mismatch"
    # a reply that carries reasoning text came from the thinking serving: not the requested one, whatever its finish
    for finish in ("stop", "length"):
        mixed = client._receipt(200, _reply("<answer>1</answer>", model="deepseek-v4-flash", finish=finish), [], 0.0)
        assert not mixed["ok"] and mixed["error_type"] == "thinking_mismatch" and mixed["reasoning_chars"] == 1
        assert mixed["usage"]["total_tokens"] == 12  # billed all the same: the ledger charges the reported usage
    for message in ({"content": "<answer>1</answer>", "reasoning_content": ""}, {"content": "<answer>1</answer>",
                                                                                 "reasoning_content": None}):
        plain = {"model": "deepseek-v4-flash", "choices": [{"finish_reason": "stop", "message": message}]}
        assert client._receipt(200, plain, [], 0.0)["ok"]
    for model, route, route_env, message in (("glm-5.3", "pjlab_token", env, "allow-list"),
                                             ("deepseek-v4-flash", "other", env, "allow-list"),
                                             ("deepseek-v4-flash", "pjlab_token", None, "credential file")):
        with pytest.raises(SystemExit, match=message):
            probe.Client(None, model, proxy=None, max_tokens=10, route=route, route_env=route_env)
    empty = tmp_path / "empty.env"
    empty.write_text("PJLAB_TOKEN_URL=https://evil.example\n")
    with pytest.raises(SystemExit, match="missing") as exc:
        probe.Client(None, "deepseek-v4-flash", proxy=None, max_tokens=10, route="pjlab_token", route_env=empty)
    assert "evil" not in str(exc.value)
    # without a route, deepseek-v4-flash still goes to the free router: existing callers are unchanged
    legacy = probe.Client(None, "deepseek-v4-flash", proxy=None, max_tokens=10, router_env=_router_env(tmp_path))
    assert legacy.backend == "free_router" and legacy.url == ROUTER_URL
    assert "thinking" not in legacy.body("s", "u")  # the free router's requests are unchanged
    assert legacy._receipt(200, _reply("<answer>1</answer>", model="deepseek-flash"), [], 0.0)["ok"]  # reasoning is fine
