"""Byte identities captured from the untouched route-B v2.3 + Amendment-2 base.

Golden values were generated from /tmp/zebra-pc-writer-baseline before this patch;
future runs need no external checkout. All items, responses, procedures and cells
are engineering fixtures. No subprocess, socket, Docker or model is used by tests.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import replace

import pytest

from tests.execskill_zpc_fakes import tmp_path


FEATURES = (
    "CONFIGURATIONS", "LEARNING", "FIX_ECHO", "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING",
    "ACCEPT_RULES", "ACCEPT_FRESHNESS", "ENGINEER_MAX_TOKENS", "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE",
    "CHECK_NON_FIRING", "ENGINEER_RECORDS", "IDENTICAL_REQUEST_REUSE", "POLICY_VERSIONS", "CODE_EXTRACTION",
    "MULTIPLE_PYTHON_BLOCKS", "CONFIG_STEP_CAPS", "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP",
    "CONFIG_CAP_FACTOR", "COST_CHECK_PAUSES", "TEST_READ_CELLS", "STAGE_READ", "REAL_RUN_EVIDENCE", "RUN_ROOTS",
)


def legacy_snapshot(root):
    """Serialize live historical behavior; reusable on the pre-extension source tree."""
    from skillopt.execskill import (acceptance, budgets, code_delivery, describer, engineer, manifest, notes,
                                    policy, protocol, reuse, solver, step)
    try:
        from skillopt.execskill import profiles as registry
    except ImportError:  # only while generating the goldens on the untouched base
        registry = protocol
    from skillopt.continual_eval.code_delivery import extract_python
    from tests.execskill_fakes_env import FakeSandbox
    from tests.test_execskill_acceptance import make_cells, packages, seal
    from tests.test_execskill_judge import fixtures, run
    from tests.test_execskill_v23_engineer import context
    from tests.test_execskill_v23_training_amendment import fixed_items

    root = root.resolve()
    names = tuple(protocol.CONFIGURATIONS)
    registered_accepts_configuration = bool(inspect.signature(manifest.registered).parameters)
    configuration = {}
    for name in names:
        configuration[name] = {
            "features": {key: getattr(registry, key).get(name, {"unregistered": True}) for key in FEATURES},
            "registered": manifest.registered(name) if registered_accepts_configuration else manifest.registered(),
            "roles": manifest.role_settings(name), "prompts": manifest.prompt_sha(name),
            "budgets": {chain: budgets.chain_caps(chain, name) for chain in protocol.CHAINS},
        }
    configuration["implicit_defaults"] = {"registered": manifest.registered(), "roles": manifest.role_settings(),
                                          "prompts": manifest.prompt_sha()}
    registrations = manifest._plain(configuration)

    records = {}
    for name in names:
        ctx = context(name)
        _, trained = engineer.run_train(ctx)
        single = replace(context(name), mode="single", round=0, base=None, label="D/s1-searchqa/engineer")
        _, one = engineer.run(single)
        records[name] = {"train": trained, "single": one, "train_requests": ctx.roles.seen,
                         "single_requests": single.roles.seen}

    parent, candidate = packages("delete")
    structures = {"parent": parent.to_json(), "candidate": candidate.to_json(),
                  "procedures": [p.to_json() for p in candidate.procedures],
                  "scope": {p.id: describer._scope(p, ()) for p in candidate.procedures},
                  "policy": {v: policy.policy_sha256(version=v) for v in policy.POLICIES},
                  "lexicon": notes.lexicon_record()}
    requests = {}
    for bench, view in {
        "searchqa": {"question": "Which synthetic city?", "context": ["Synthetic city is Sampleton."]},
        "officeqa": {"question": "Synthetic total?", "context": ["2010 | 12"]},
        "livemath": {"question": "Synthetic sum?", "choices": "A) 1 B) 2 C) 3 D) 4 E) 5"},
        "spreadsheetbench": {"instruction": "Synthetic cell", "workbook_preview": [], "input_path": "input.xlsx",
                             "required_output_path": "output.xlsx", "required_answer_position": "A1"},
    }.items():
        worker = FakeSandbox().start(candidate, kind="cell")
        requests[bench] = reuse.signature(bench, candidate, view, worker, card_text="Synthetic card.",
                                          runtime={"prompt_layout": "contract-first-v2"})
        worker.close()
    delivery = {reply: {"v1": extract_python(reply), "v2": code_delivery.extract_python(reply),
                        "legacy_shell": solver._extract(reply, "explicit-python-fences-v1"),
                        "v23_shell": solver._extract(reply, code_delivery.VERSION)}
                for reply in ("```python\nprint(1)\n```", "prose```python\nprint(1)\n```",
                              "```python\nprint(1)\n```\n```\n", "```python\na=1\n```\n```python\na=2\n```",
                              "No program")}

    # Exact all-zero score contrasts avoid stochastic sampling in the fixture snapshot.
    acceptance_records = {}
    for name, options in (("legacy", {}), ("v22", {"rule": protocol.PRACTICAL_RULE}),
                          ("v23", {"rule": protocol.PRACTICAL_RULE,
                                   "reuse": {"card_text": "Synthetic card.", "runtime": {}}})):
        sealed = seal(root / name, **options)
        cells = make_cells(sealed, token=lambda job: "fail")
        decision = acceptance.decide(cells, sealed)
        acceptance_records[name] = {"sealed": sealed, "decision": decision,
                                    "schedule": acceptance.schedule(sealed)}
    training = {}
    for sign in (False, True):
        for identical in (None, ["same"]):
            ids = ["fixed"] + ([] if identical is None else identical)
            training[str((sign, identical))] = step.train_verdict(fixed_items(["fixed"]), ids, [], set(),
                predicate_faults=0, routed=len(ids), sign=sign, identical=identical, runs=2)
    judged = [{"bench": bench, "reply": reply, "judge": run(bench, reply)} for bench, reply in fixtures()]
    return {"registrations": registrations, "engineer_records_and_requests": records,
            "packages_policy_scope_and_lexicon": structures, "request_identities": requests,
            "delivery": delivery, "acceptance": acceptance_records, "training": training,
            "historical_judges": judged}


def byte_sha(value):
    """SHA256 of exact UTF-8 sorted compact JSON, with no type-changing fallback."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


# Generated on the untouched base, not on the implementation being tested.
BASELINE_SHA256 = {
  "acceptance": "60819c09496a395743a3ba26066f315a3efcbc7180e854c25ceb78db451a05bf",
  "delivery": "812117551996814e4c6475ba1cff7d9f983e8a94e68412cff7b2121e41c6cae4",
  "engineer_records_and_requests": "9a0f577aefdfdf62dd34b0f913a98c6b320b1399130bb5a09803760b91992bae",
  "historical_judges": "2d8809291e17b2e780ba859fe1e357a4c283302134737f789591e8f6f7ad0a4d",
  "packages_policy_scope_and_lexicon": "e677343be3a342a24510cc0b9679a1ad24a88d68194ad8cb061c1c1b4493355f",
  "registrations": "1362e82577182e721f4b37e72fcce456f76702a5e995f43a30b4d6898f3fa878",
  "request_identities": "b340557cc6e6c6bc050f11a10f71807f095d9c26b5c105041dce9f0ea36ae221",
  "training": "e3ed2a0cdb4242f4b2bf40ac5157f7f74ff50d34f433153db4614b56f92904c5"
}


@pytest.fixture(scope="module")
def legacy_bytes(tmp_path_factory):
    return {name: byte_sha(value) for name, value in legacy_snapshot(tmp_path_factory.mktemp("old-behavior")).items()}


@pytest.mark.parametrize("name", tuple(BASELINE_SHA256))
def test_main_v23_and_all_older_profiles_keep_their_baseline_bytes(name, legacy_bytes):
    assert legacy_bytes[name] == BASELINE_SHA256[name]


def test_old_procedure_scope_does_not_expand_to_zebralogic():
    from tests.test_execskill_acceptance import packages
    from skillopt.execskill import protocol
    parent, candidate = packages("delete")
    assert parent.for_bench("zebralogic") == candidate.for_bench("zebralogic") == ()
    assert all(candidate.for_bench(bench) for bench in protocol.BENCHES)
