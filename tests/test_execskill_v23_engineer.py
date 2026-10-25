"""Route B v2.3 E1-E4: synthetic, zero-call checks, without sandbox processes or network transports."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer, engineer_payload, policy, protocol
from skillopt.execskill.errors import PackageInvalid
from skillopt.execskill.package import FIXTURE, Procedure, empty
from skillopt.execskill.sandbox import client, worker
from skillopt.validator_pilot.api import digest

SOURCE = 'def applies(view):\n    return True\ndef before_call(view, state):\n    return {}\n'
V23 = protocol.MAIN_V2_3


@pytest.mark.parametrize("constant", [
    'A = re.compile("x")', 'A = re.compile("x", re.I | re.MULTILINE)',
    'A = set(["a", "b"])', 'A = frozenset((1, 2))', 'A = tuple([1, 2])', 'A = list((1, 2))',
    'A = dict([("a", 1)])', 'A = sorted([2, 1])', 'A = "a b".split()', 'A = "a,b".split(",")',
    'A = ",".join(["a", "b"])', 'A = ",".join(("a", "b"))', 'A = "a" + "b" + "c"',
    'A = [1] + [2]', 'A = (1,) + (2,)', 'A = 1 + 2 + 3', 'A = set([1])\nB = A',
])
def test_v23_accepts_only_registered_pure_constants_and_legacy_stays_literal_only(constant):
    text = 'import re\n' + constant + '\n' + SOURCE
    assert not policy.check(text, version=policy.POLICY_VERSION_V23)
    assert any(v.rule == "module_level" for v in policy.check(text))


@pytest.mark.parametrize("constant", [
    'A = re.compile("x")', 'import re\nA = re.compile("x", 2)', 'import re\nA = re.compile("x", flags=re.I)',
    'import re\nA = re.escape("x")', 'A = list(range(3))', 'A = set(x for x in [1])',
    'A = dict(a=1)', 'A = [1] + (2,)', 'A = "x" * 10', 'A = "x".replace("x", "y")',
    'A = ",".join(["a", 2])', 'A = "x".split(None)', 'A = B\nB = [1]', 'A = A',
    'def set(x):\n    return x\nA = set([1])', 'import re\nre = "x"\nA = re.compile("x")',
])
def test_v23_rejects_unregistered_module_expressions(constant):
    assert any(v.rule == "module_level" for v in policy.check(constant + '\n' + SOURCE,
                                                              version=policy.POLICY_VERSION_V23))


def test_policy_size_caps_and_frozen_policy_file_are_preserved():
    assert policy.policy_sha256() == digest(policy.POLICY)
    assert json.loads(policy.POLICY_PATH.read_text()) == policy.POLICY
    assert json.loads(policy.POLICY_PATH_V23.read_text()) == policy.POLICY_V23
    assert policy.policy_sha256(version=policy.POLICY_VERSION_V23) != policy.policy_sha256()
    text = 'A = "' + 'x' * 2_000 + '".split()\n' + SOURCE
    assert any(v.rule == "constant_size" for v in policy.check(text, version=policy.POLICY_VERSION_V23))


def procedure(version=policy.POLICY_VERSION, source=SOURCE):
    return Procedure(id="fx-v23", origin="searchqa", description="Computes public facts.",
                     hooks=("applies", "before_call"), source=source, evidence=FIXTURE, max_note_chars=1000,
                     policy_version=version)


def test_procedure_and_worker_pin_the_policy_without_changing_old_frames():
    old = procedure()
    source = 'A = set([1])\n' + SOURCE
    new = procedure(policy.POLICY_VERSION_V23, source)
    assert "policy_version" not in old.to_json()
    assert new.to_json()["version"] == protocol.kind("procedure-v2-3")
    assert Procedure.from_json(new.to_json()) == new
    with pytest.raises(PackageInvalid, match="Policy violations"):
        procedure(source=source)
    legacy = client._entries(SimpleNamespace(sha256="a" * 64, procedures=[old]))
    assert set(legacy[0]) == {"id", "source", "hooks"}
    modern = client._entries(SimpleNamespace(sha256="a" * 64, procedures=[new]))
    request = {"seq": 1, "package_sha256": "a" * 64, "policy_version": policy.POLICY_VERSION_V23,
               "policy_sha256": policy.policy_sha256(version=policy.POLICY_VERSION_V23), "procedures": modern,
               "limits": {"address_space_mb": 2048, "frame_bytes": 1 << 20}}
    result = worker.handle_load(request, {"loaded": None}, policy)
    assert result["loaded"] == [new.id] and not result["rejected"]
    request.pop("policy_version")
    request["policy_sha256"] = policy.policy_sha256()
    assert not worker.handle_load(request, {"loaded": None}, policy)["ok"]


def test_excerpts_keep_priority_anchors_merge_windows_and_count_omissions():
    text = "h" * 1500 + "z" * 4000 + "reference-1717" + "z" * 4000 + "answer-2626" + "z" * 4000
    found = engineer_payload.excerpt(text, question="Find exceptionalquartz 1717", references=["reference-1717"],
                                     answers=["answer-2626"])
    assert len(found) <= 6000 and found.startswith(text[:1500])
    assert "reference-1717" in found and "answer-2626" in found and "characters omitted" in found
    assert found == engineer_payload.excerpt(text, question="Find exceptionalquartz 1717",
                                            references=["reference-1717"], answers=["answer-2626"])
    assert engineer_payload.excerpt("short") == "short"


def test_payload_is_detached_and_alfworld_steps_are_never_shortened():
    long = "prefix " * 1200 + "special-reference" + " middle" * 1200 + "solver-last" + " tail" * 1200
    trajectory = {"bench": "officeqa", "kind": "failures", "reference": "special-reference",
                  "replies": ["<answer>solver-last</answer>"],
                  "calls": [{"user": json.dumps({"question": "Which exceptional words?", "context": [long]})}]}
    payload = {"bench": "officeqa", "trajectories": [trajectory]}
    before = copy.deepcopy(payload)
    shown = engineer_payload.trim(payload)
    view = json.loads(shown["trajectories"][0]["calls"][0]["user"])
    assert len(view["context"][0]) <= 6000 and "special-reference" in view["context"][0]
    assert "solver-last" in view["context"][0]
    assert payload == before
    counts = shown["payload_trimming"]
    assert counts["original_chars"] == len(long) + len(view["question"])
    assert counts["trimmed_chars"] == len(view["context"][0]) + len(view["question"])
    payload = {"bench": "alfworld", "trajectories": [{"alfworld_steps": [{"observation": long}]}]}
    assert engineer_payload.trim(payload)["trajectories"] == payload["trajectories"]


class ScriptedRoles:
    def __init__(self):
        self.calls, self.seen = [], []

    def count(self, prefix):
        return sum(c["label"].startswith(prefix) for c in self.calls)

    def plain(self, role, system, user, *, label, **options):
        self.seen.append((role, system, json.loads(user), options))
        self.calls.append({"label": label, "request_sha256": digest([system, user])})
        return '```json\n{"changes": []}\n```'


def context(configuration=V23):
    base = empty(step="s0", evidence=FIXTURE)
    return engineer.Context(bench="searchqa", k=1, step="s1", evidence=FIXTURE, parent=base, base=base,
                            trajectories=[], current=[], corpora={}, workers=None, roles=ScriptedRoles(),
                            label="D/s1-searchqa/engineer-r1", mode="train", round=1, configuration=configuration)


def test_only_v23_train_proposals_request_32k_and_the_record_names_the_new_prompt():
    ctx = context()
    for purpose in ("propose", "repropose", "fix/1/1"):
        engineer._ask(ctx, {"request": purpose}, purpose)
    assert [entry[-1] for entry in ctx.roles.seen] == [{"max_tokens": 32768}, {"max_tokens": 32768}, {}]
    assert all(entry[1] == engineer.ENGINEER_SYSTEM_V23 for entry in ctx.roles.seen)
    old = context(protocol.MAIN_V2_2)
    engineer._ask(old, {"request": "propose"}, "propose")
    assert old.roles.seen[0][1] == engineer.ENGINEER_SYSTEM_V2 and old.roles.seen[0][-1] == {}
    _, sealed = engineer.run_train(context())
    assert sealed["version"] == protocol.kind("engineer-v2-3-a2")
    assert sealed["prompt_sha256"] == engineer.ENGINEER_PROMPT_V23_SHA256
    assert "payload_trimming" in sealed


def test_structure_normalization_and_c2_feedback_are_v23_only():
    entry = {"kind": "new", "description": "Extracts numeric facts.", "hooks": ["bindings", "applies"],
             "max_note_chars": 1000}
    source = 'A = range(3)\ndef applies(view):\n    return True\ndef bindings(view):\n    return {}\n'
    modern = engineer.Change(1, "new", copy.deepcopy(entry), source, "a" * 64)
    result = engineer.check(modern, context())
    assert result["failed"] == "C2" and modern.entry["hooks"] == ["applies", "bindings"]
    assert modern.entry["excluded_benches"] == ["spreadsheetbench", "alfworld"]
    assert len(modern.to_json()["normalized"]) == 2
    violation = result["checks"][-1]["detail"][0]
    assert violation["line_text"] == "A = range(3)" and violation["rule"] == "module_level"
    assert violation["fix_hint"] == "Move the call into a function, or write the literal value."
    old = engineer.Change(1, "new", copy.deepcopy(entry), source, "a" * 64)
    assert engineer.check(old, context(protocol.MAIN_V2_2))["failed"] == "C1"
    assert "normalized" not in old.to_json() and old.entry == entry
