"""v28-1 reader ownership/resource regressions on authored offline replies."""
import json
from dataclasses import replace

import pytest

from skillopt.execskill import engineer as e, engineer_reader as reader, profiles as p
from skillopt.execskill.package import with_
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import GOOD, change, context as base_context
from tests.test_execskill_v28_engineer import encoded, requests, run
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


def context(**options):
    ctx, workers = base_context(**options)
    ctx.current = list(ctx.trajectories)
    return ctx, workers


def incumbent_context(count=1):
    ctx, _ = context(configuration=p.ZEBRA_PC_V6)
    proposed = change(ctx)
    e._build(proposed, ctx)
    incumbents = [replace(proposed.procedure, id="fx-source-%d" % index,
                          source=GOOD + "# incumbent %d\n" % index) for index in range(count)]
    parent = with_(ctx.parent, step="D/s0-parent", add=incumbents)
    return replace(ctx, parent=parent, base=parent), incumbents


@pytest.mark.parametrize("revision_first", [True, False])
def test_source_free_revision_cannot_consume_a_new_siblings_only_fence(revision_first):
    ctx, (incumbent,) = incumbent_context()
    revision = {"kind": "revision", "revises": incumbent.id,
                "hooks": ["applies", "before_call"], "description": "Metadata revision."}
    proposed = change(ctx, GOOD + "# new sibling source\n")
    entries = [revision, proposed.entry] if revision_first else [proposed.entry, revision]
    results = reader.read(engineer_reply({"changes": entries}, [proposed.source]), ctx)
    assert all(result["error"] is None for result in results)
    revised, added = results if revision_first else reversed(results)
    assert revised["source"] == incumbent.source
    assert added["source"].strip() == proposed.source.strip()
    assert {row["rule"] for row in revised["repairs"]} >= {"inherited_source"}


@pytest.mark.parametrize("repair", [True, False])
def test_inheritable_siblings_with_one_unowned_fence_use_one_format_retry(repair):
    ctx, incumbents = incumbent_context(2)
    entries = [{"kind": "revision", "revises": incumbent.id, "hooks": list(incumbent.hooks)}
               for incumbent in incumbents]
    ambiguous = engineer_reply({"changes": entries}, [GOOD])
    with pytest.raises(reader.Unusable, match="ownership"):
        reader.read(ambiguous, ctx)
    corrected = engineer_reply({"changes": entries}, [incumbent.source for incumbent in incumbents])
    _, record = run(ctx, ambiguous, corrected if repair else ambiguous)
    assert len(requests(ctx, "format_retry")) == 1
    assert record["format_retries"][0]["parsed"] is repair
    if repair:
        assert len(record["changes"]) == 2 and all(row["survived"] for row in record["changes"])
    else:
        assert record["changes"][0]["reason"] == "unparseable"
    assert not requests(ctx, "fix")


def deep_reply():
    # Review reproduction: a valid, small JSON reply whose unknown field has 500 nested lists.
    reply = ('{"changes":[{"kind":"new","source":"def helper():\\n    return 1\\n",'
             '"unknown":' + "[" * 500 + "0" + "]" * 500 + "}]}")
    reply += " " * (1252 - len(reply.encode("utf-8")))
    assert len(reply.encode("utf-8")) == 1252
    assert json.loads(reply)["changes"][0]["kind"] == "new"
    return reply


@pytest.mark.parametrize("repair", [True, False])
def test_small_deep_unknown_field_gets_format_retry_and_unparseable_record(repair):
    ctx, _ = context(configuration=p.ZEBRA_PC_V6)
    reply = deep_reply()
    with pytest.raises(reader.Unusable, match="depth"):
        reader.read(reply, ctx)
    package, record = run(ctx, reply, encoded(change(ctx)) if repair else reply)
    assert len(requests(ctx, "format_retry")) == 1 and not requests(ctx, "fix")
    assert record["format_retries"][0]["parsed"] is repair
    if repair:
        assert package is not None and record["changes"][0]["survived"]
    else:
        assert package is None and record["changes"][0]["reason"] == "unparseable"


def test_depth_bound_allows_shallow_unknown_data_and_ignores_it_normally():
    ctx, _ = context(configuration=p.ZEBRA_PC_V6)
    proposed = change(ctx)
    proposed.entry["unknown"] = [[["unrelated data"]]]
    result = reader.read(encoded(proposed), ctx)[0]
    assert result["error"] is None and "unknown" not in result["entry"]
    assert any(row["rule"] == "unknown_key_ignored" and row["path"] == "$.unknown"
               for row in result["repairs"])


@pytest.mark.parametrize("failure", [RecursionError, MemoryError, OverflowError])
@pytest.mark.parametrize("boundary", ["read", "tolerant_json"])
def test_reader_resource_failures_are_unusable(monkeypatch, failure, boundary):
    ctx, _ = context(configuration=p.ZEBRA_PC_V6)
    def exhausted(*args, **kwargs):
        raise failure("authored resource exhaustion")
    if boundary == "read":
        monkeypatch.setattr(reader, "normalize", exhausted)
        invoke = lambda: reader.read('{"changes":[]}', ctx)
    else:
        monkeypatch.setattr(reader.json, "loads", exhausted)
        # RecursionError in strict JSON takes the tolerant parser fallback; exhaust it too.
        monkeypatch.setattr(reader.ast, "parse", exhausted)
        invoke = lambda: reader.tolerant_json('{"changes":[]}')
    with pytest.raises(reader.Unusable):
        invoke()


@pytest.mark.parametrize("configuration,bench", [(p.ZEBRA_PC_V6, "zebralogic"), (p.ALFWORLD_V3, "alfworld")])
def test_helper_only_unknown_hook_declaration_derives_empty_hooks_and_is_inert(configuration, bench):
    ctx, _ = context(configuration=configuration, bench=bench)
    proposal = change(ctx, "def helper(value):\n    return value\n")
    proposal.entry["hooks"] = ["on_request"]
    report = e.check(proposal, ctx)
    assert report["passed"] and report["failed"] is None and report["inert"]
    assert proposal.entry["hooks"] == [] and proposal.procedure.hooks == ()
    assert any(row["path"] == "$.hooks" and row["before"] == ["on_request"] and row["after"] == []
               for row in proposal.repairs)
    proposal.entry["hooks"] = ["on_request"]
    package, record = run(ctx, encoded(proposal))
    assert package is None and record["changes"][0]["inert"]
    assert not requests(ctx, "fix") and not requests(ctx, "format_retry")
