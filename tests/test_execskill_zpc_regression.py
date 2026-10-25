"""Byte identities captured from the untouched route-B v2.3 + Amendment-2 base.

Golden values were generated from /tmp/zebra-pc-writer-baseline before this patch;
future runs need no external checkout. All items, responses, procedures and cells
are engineering fixtures. No subprocess, socket, Docker or model is used by tests.
Zebra v1 goldens were separately generated from /tmp/zpc-v24-before before v2.4 edits.
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
                  "policy": {v: policy.policy_sha256(version=v)
                             for v in (policy.POLICY_VERSION, policy.POLICY_VERSION_V23)},
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


def zebra_v1_snapshot(root):
    """By-value v1 registration, requests and records captured before the v2.4 extension."""
    from contextlib import contextmanager
    from skillopt.execskill import (acceptance, budgets, describer, engineer, manifest, policy,
                                    profiles as p, reuse, solver, zebralogic as z)
    from skillopt.execskill.package import empty, with_
    from tests.execskill_fakes_env import FakeSandbox, Script
    from tests.test_execskill_acceptance import make_cells
    from tests.test_execskill_v23_engineer import context
    from tests.test_execskill_zpc_adapter import answer, pool_rows
    from tests.test_execskill_zpc_profile import procedure

    name = p.ZEBRA_PC_V1
    cuts = z.slices([z.normalize(item) for item in pool_rows()])
    proc = procedure(z.BENCH, p.BENCHES)
    parent = empty(step="D/s0", evidence="engineering_fixture")
    candidate = with_(parent, step="D/s1-zebralogic/t1", add=[proc])
    hook_table = {proc.id: {"applies": lambda view: True,
                           "before_call": lambda view, state: {"table": [["House 1", "value 1 1"]]}}}

    @contextmanager
    def workers(package, item):
        worker = FakeSandbox(hook_table).start(package, kind="cell")
        try:
            yield worker
        finally:
            worker.close()

    records = {}
    for mode in ("train", "single"):
        base_ctx = context(name)
        ctx = replace(base_ctx, bench=z.BENCH, mode=mode, round=1 if mode == "train" else 0,
                      base=base_ctx.base if mode == "train" else None,
                      label="D/s1-zebralogic/engineer")
        _, result = (engineer.run_train if mode == "train" else engineer.run)(ctx)
        records[mode] = {"record": result, "requests": ctx.roles.seen}

    item = cuts["run"][0]
    requests = {}
    for arm, package in (("C", parent), ("S'", candidate)):
        with workers(package, item["task_id"]) as worker:
            requests[arm] = reuse.signature(z.BENCH, package, item["public"], worker,
                                            card_text=z.CARD_TEXT, runtime={})
            call = Script([answer(item)])
            solved = solver.solve(z.BENCH, item["public"], z.CARD_TEXT, package, call,
                                  worker=FakeSandbox(hook_table))
            requests[arm].update(requests=call.requests, prediction=solved,
                                 score=z.score(item["public"], item["private"], solved))

    views = {item["task_id"]: item["public"] for item in cuts["accept"]}
    trajectories = [{"cell": "D/s1-zebralogic/run/S/" + item["task_id"] + "/0",
                     "task_id": item["task_id"], "bench": z.BENCH, "arm_kind": "parent",
                     "calls": [{"purpose": "first", "user": z.render_user(item["public"])}],
                     "shell": {"precheck": None}} for item in cuts["run"]]
    sealed = acceptance.prepare(root.resolve() / "zpc-v1", chain="D", bench=z.BENCH,
        step=candidate.step, unit="D/s1-zebralogic/accept", candidate=candidate, parent=parent,
        views=views, blocks={item: "b1" for item in views}, workers=workers, trajectories=trajectories,
        freshness=p.ACCEPT_FRESHNESS[name], mde=p.MDE_POINTS[z.BENCH], rule=p.ACCEPT_RULES[name],
        reuse={"card_text": z.CARD_TEXT, "runtime": {}})
    cells = make_cells(sealed, token=lambda job: "fail")
    return {"registration": manifest._plain({
                "features": {key: getattr(p, key).get(name, {"unregistered": True}) for key in FEATURES},
                "registered": manifest.registered(name), "roles": manifest.role_settings(name),
                "prompts": manifest.prompt_sha(name), "data": z.identity(),
                "budgets": {chain: budgets.chain_caps(chain, name) for chain in p.CHAINS},
                "slice_ids": {key: [item["task_id"] for item in items] for key, items in cuts.items()}}),
            "engineer": records, "requests_and_score": requests,
            "packages": {"parent": parent.to_json(), "candidate": candidate.to_json(),
                         "procedure": proc.to_json(), "scope": describer._scope(proc, ()),
                         "policy": policy.policy_sha256(version=policy.POLICY_VERSION_V23)},
            "acceptance": {"sealed": sealed, "schedule": acceptance.schedule(sealed),
                           "decision": acceptance.decide(cells, sealed)}}


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

# Generated with zebra_v1_snapshot against /tmp/zpc-v24-before, before v2.4 source edits.
ZEBRA_V1_SHA256 = {
    "registration": "131aa50cf006e6a3ed25abb3106196ad43930e29202e6c6a4809c4d38c47add1",
    "engineer": "69618ad3cf7b68bf0d098387a772c6d53ebf74cef89bdb99b3bf8f28cc32da89",
    "requests_and_score": "b43a39cb9e94cd7e607e4a756bdfa049776a9d829bdddde945eed4476d229e4d",
    "packages": "d514195037bd073bb420bc22a33012c92742694cb00a21b88ecd367def93a171",
    "acceptance": "528c5894e448c97c3e7fcec57e6c8c296cef49c0cf1c7e3a076166f60f2c75c3",
}


@pytest.fixture(scope="module")
def legacy_bytes(tmp_path_factory):
    return {name: byte_sha(value) for name, value in legacy_snapshot(tmp_path_factory.mktemp("old-behavior")).items()}


@pytest.mark.parametrize("name", tuple(BASELINE_SHA256))
def test_main_v23_and_all_older_profiles_keep_their_baseline_bytes(name, legacy_bytes):
    assert legacy_bytes[name] == BASELINE_SHA256[name]


@pytest.fixture(scope="module")
def zebra_v1_bytes(tmp_path_factory):
    return {name: byte_sha(value) for name, value in zebra_v1_snapshot(tmp_path_factory.mktemp("zpc-v1")).items()}


@pytest.mark.parametrize("name", tuple(ZEBRA_V1_SHA256))
def test_zebra_v1_keeps_its_pre_v24_bytes(name, zebra_v1_bytes):
    assert zebra_v1_bytes[name] == ZEBRA_V1_SHA256[name]


def test_old_procedure_scope_does_not_expand_to_zebralogic():
    from tests.test_execskill_acceptance import packages
    from skillopt.execskill import protocol
    parent, candidate = packages("delete")
    assert parent.for_bench("zebralogic") == candidate.for_bench("zebralogic") == ()
    assert all(candidate.for_bench(bench) for bench in protocol.BENCHES)
