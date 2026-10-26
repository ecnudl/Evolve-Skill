"""Lean v2.9 S3: real dual audits of authored errors and held-out fixture cells."""
from __future__ import annotations

import contextlib
import copy
import json

from skillopt.validator_pilot.api import digest

from . import audit, engineer, profiles as p, smoke, solver, step, units


def authored_reply(bench):
    from . import alf_smoke, zebra_smoke
    owner = alf_smoke if bench == "alfworld" else zebra_smoke
    entries, _ = engineer.parse(owner.authored_reply())
    entry = entries[0]
    if bench == "alfworld":
        source = alf_smoke.AUTHORED_SOURCE.replace(
            '[view["initial_observation"]]',
            '[view["initial_observation"], "All receptacles named in the room description have been visited."]')
        entry["description"] = "Tracks visits and reports whether all named receptacles were visited."
    else:
        source = '''def before_call(view, state):
    parsed = view["question"].splitlines()[:1]
    return {"facts": [parsed[0], "All clues were parsed."]}
'''
        entry["description"] = "Parses every puzzle clue and reports completion."
        entry["hooks"] = ["before_call"]
    return "```json\n" + json.dumps({"changes": [entry]}, sort_keys=True) + "\n```\n```python\n" + source + "```"


def confirm_fixtures(bench, items):
    rows = copy.deepcopy(items[:2])
    for index, row in enumerate(rows):
        row["task_id"] = bench + "/v29-confirm-fixture-%d" % index
        row["family_id"] = row["task_id"]
        if bench == "alfworld":
            row["room"] = "v29-confirm-room-%d" % index
            row["public"]["game_file"] = "alf-smoke-fixture://confirm-%d" % index
    return rows


def false_template_confirmed(result, bench):
    if not result:
        return False
    text = ("All receptacles named in the room description have been visited." if bench == "alfworld"
            else "All clues were parsed.")
    for finding in result["confirmed"]:
        if finding["kind"] == "template":
            templates = result["templates"][finding["procedure"]]["templates"]
            if any(t["t"] == finding["t"] and t["text"] == text for t in templates):
                return True
        elif finding["kind"] == "note":
            for situation in result["sampling"]["situations"]:
                if situation["s"] == finding["s"] and any(n["n"] == finding["n"] and n["text"] == text
                                                         for n in situation["notes"]):
                    return True
    return False


def judge_counts(result):
    """Selected-attempt coverage; multiple field problems count one abstained unit.

    Counts are summed over request-local units. Ignored optional rows and extra
    keys remain separate from required-unit coverage and do not change S3a's gate.
    """
    counts = {judge: {"covered": 0, "abstained": 0, "ignored": 0} for judge in audit.JUDGES}
    for pair in (result or {}).get("requests", []):
        for judge, request in pair["requests"].items():
            counts[judge]["covered"] += len(request.get("covered", []))
            counts[judge]["abstained"] += len({row["unit"] for row in request.get("abstained", [])})
            counts[judge]["ignored"] += len(request.get("ignored", []))
    return counts


def _proposal(st, cut):
    def work(attempt):
        reply = authored_reply(st.bench)
        entries, sources = engineer.parse(reply)
        changes = engineer.changes_of(entries, sources, digest(reply))
        _, _, publics = step._training_publics(cut, None, st.bench)
        ctx = engineer.Context(bench=st.bench, k=1, step=st.name, evidence=st.evidence, parent=st.parent,
            trajectories=step._run_trajectories(st), current=step._current(st, []), corpora=step._corpora(st, cut),
            workers=st.services.workers, roles=st.roles("engineer"), label=st.label("engineer-r1"),
            card=st.setting.cards.get(st.bench, ""), mode="train", round=1, base=st.parent,
            configuration=p.configuration_of(st.setting), echo=True, counterfactual=True,
            routing_items=[(key, solver.routing_view(st.bench, public, runtime=st.runtime()))
                           for key, public in publics.items()], routing_workers=step._item_workers(st, publics),
            routing_shared_worker=st.services.item_workers is None,
            audit_judges=units.audit_judges(st.setting, st.chain, st.bench, st.k))
        checked = engineer.check(changes[0], ctx)
        audited = audit.audit1(ctx, changes[0], checked) if checked["passed"] else None
        candidate, kept = engineer._combined_train(ctx, changes) if checked["passed"] else (None, [])
        if candidate is not None:
            step.save(st.chain_root, candidate)
        return {"parsed": True, "passed": bool(audited and all(audited["available"].values())),
                "checks": checked, "audit": audited, "false_template_confirmed": false_template_confirmed(audited, st.bench),
                "judge_counts": judge_counts(audited),
                "candidate_sha256": candidate.sha256 if candidate is not None else None,
                "exercise": True, "decision_used_for_adoption": False}
    return st.unit("engineer-r1", work)


def _audit_measurements(*values):
    """Project actual reviewer sends, including format retries, with prompt byte floors."""
    rows, seen = [], set()
    def walk(value):
        if isinstance(value, dict):
            if value.get("phase") in (1, 2) and isinstance(value.get("requests"), list):
                # Findings and ignored reply fragments are untrusted model data,
                # even if their keys happen to resemble an audit request record.
                for pair in value["requests"]:
                    walk(pair)
                return
            if isinstance(value.get("requests"), dict) and set(value["requests"]) == {"G", "D"}:
                for judge, request in value["requests"].items():
                    key = (judge, request.get("prompt_sha256"))
                    if key in seen or request.get("reused"):
                        continue
                    seen.add(key)
                    attempts = 1 + len(request.get("retries", []))
                    texts = [request] + request.get("retries", [])
                    size = max(len((row.get("system", "") + row.get("user", "")).encode()) for row in texts)
                    for _ in range(attempts):
                        rows.append({"role": "audit_" + judge.lower(),
                                     "charged": request["tokens"]["charged"] / attempts,
                                     "request_bytes": size})
                return  # do not scan parsed replies or their diagnostic raw rows
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    for value in values:
        seen.clear()  # distinct completed units may legitimately send the same prompt
        walk(value)
    return smoke.role_calls_measured(rows)


def s3(setting, services):
    from . import alf_smoke, zebra_smoke
    configuration = p.configuration_of(setting)
    alf = p.is_alfworld(configuration)
    owner = alf_smoke if alf else zebra_smoke
    st, cut = (owner._fixture_step(setting, services, "S3a") if alf
               else owner._fixture_step(setting, services, "D", "S3a"))
    cut["confirm"] = confirm_fixtures(st.bench, cut["run"])
    identity = {"run": setting.run, "configuration": configuration, "chain": "D", "substage": "S3a",
                "recipe": "v29-audit-confirm-v1", "fixtures_sha256": digest(cut),
                "proposal_sha256": digest(authored_reply(st.bench))}
    authored = owner._cached_substage(st, identity)
    if authored is None:
        environment = owner._fixture_environment(cut["run"] + cut["confirm"]) if alf else contextlib.nullcontext()
        with environment:
            step._run(st, cut)
            proposed = _proposal(st, cut)
            candidate = step._package(st, proposed["candidate_sha256"]) if proposed["candidate_sha256"] else st.parent
            evaluated = step._train_eval(st, cut, 1, st.parent, candidate, None)
            confirmed = step._confirm_eval(st, cut, 1, st.parent, candidate, exercise=True)
        authored = owner._save_substage(st, identity, {"passed": proposed["passed"], "proposal": proposed,
            "training": evaluated, "confirm": confirmed, "exercise": True,
            "decision_used_for_adoption": False})
    real = owner._s3b(setting, services)
    measurements = {**real["role_measurements"], **_audit_measurements(authored, real)}
    confirm_record = authored["confirm"]
    confirm_cells = list(confirm_record["candidate_cells"].values()) + list(confirm_record["incumbent_cells"].values())
    confirm_measured = smoke.measured_cells(confirm_cells)
    confirm_measured.update(cells=len(confirm_cells),
                            settled_tokens=sum(s.get("charged", 0) for c in confirm_cells for s in c["sends"]))
    fault_repair = _s3c(setting, services) if p.is_v291(configuration) else None
    if fault_repair is not None:
        measurements = _merge_measurements(measurements, fault_repair["role_measurements"])
    substages = [("S3a", authored), ("S3b", real)] + ([("S3c", fault_repair)] if fault_repair is not None else [])
    failed = [name for name, row in substages if not row["passed"]]
    return {"passed": not failed, **({"S3c": fault_repair} if fault_repair is not None else {}), "S3a": authored, "S3b": real, "failed_substages": failed,
            "rounds": 1, "fixtures": len(cut["run"]), "confirm_fixtures": 2,
            "role_measurements": measurements, "confirm_measurements": confirm_measured, "generator": "selection", "research": "not_applicable",
            "solver_route": "B"}


def authored_fault_reply(bench, *, configuration=None):
    """A deterministic, public-input crash in the first note hook of every item."""
    from . import alf_smoke, zebra_smoke
    owner = alf_smoke if bench == 'alfworld' else zebra_smoke
    entries, _ = engineer.parse(owner.authored_reply())
    entry = entries[0]
    entry.update(description='Extracts useful facts from the public task.', replay_tests=[],
                 requests_second_call=False, state_bytes=0)
    if bench == 'alfworld':
        source = ('def alf_before_step(view, state):\n'
                  '    return {"facts": [state.get("previous_observation", "")] }\n')
        if configuration is not None and p.is_v292(configuration):
            source = ('def alf_before_step(view, state):\n'
                      '    return {"fields": {"facts": [state.get("previous_observation", "")]}}\n')
        entry['hooks'] = ['alf_before_step']
    else:
        source = ('def before_call(view, state):\n'
                  '    return {"facts": [view["question"].splitlines()[999]]}\n')
        entry['hooks'] = ['before_call']
    return '```json\n' + json.dumps({'changes': [entry]}, sort_keys=True) + '\n```\n```python\n' + source + '```'


def _fault_evidence_ok(value, bench):
    signatures = value.get('signatures') or []
    call = value.get('example_call') or {}
    arguments = call.get('arguments') or {}
    first = signatures[0] if signatures else {}
    return bool(value.get('triggered') and value.get('fired') and value.get('faulted') == value.get('fired')
                and first.get('exc_type') and first.get('message') and type(first.get('line')) is int
                and first['line'] > 0 and first.get('source_line') and first.get('source_context')
                and call.get('hook') == ('alf_before_step' if bench == 'alfworld' else 'before_call')
                and 'view' in arguments and 'state' in arguments
                and (bench != 'alfworld' or call.get('step') == 0 and arguments['state'] is None))


def _fault_repair_proposal(st, cut):
    from . import engineer_v291
    def work(attempt):
        reply = authored_fault_reply(st.bench, configuration=p.configuration_of(st.setting))
        entries, sources = engineer.parse(reply)
        change = engineer.changes_of(entries, sources, digest(reply))[0]
        _, _, publics = step._training_publics(cut, None, st.bench)
        ctx = engineer.Context(bench=st.bench, k=1, step=st.name, evidence=st.evidence, parent=st.parent,
            trajectories=step._run_trajectories(st), current=step._current(st, []), corpora=step._corpora(st, cut),
            workers=st.services.workers, roles=st.roles('engineer'), label=st.label('engineer-r1'),
            card=st.setting.cards.get(st.bench, ''), mode='train', round=1, base=st.parent,
            configuration=p.configuration_of(st.setting), echo=True, counterfactual=True,
            routing_items=[(key, solver.routing_view(st.bench, public, runtime=st.runtime()))
                           for key, public in publics.items()], routing_workers=step._item_workers(st, publics),
            routing_shared_worker=st.services.item_workers is None)
        checked = engineer.check(change, ctx)
        if not checked['passed'] or checked.get('deferred'):
            return {'passed': False, 'checks': checked, 'fault_repair': None, 'faulted_after': None}
        _, _, attempts, repaired = engineer_v291.repair(ctx, change, checked, max_repairs=1, format_retry=False)
        calls = repaired['calls']
        sent = calls[0] if len(calls) == 1 else {}
        passed = (repaired['triggered'] and _fault_evidence_ok((sent.get('request') or {}).get('evidence', {}), st.bench)
                  and sent.get('call') is not None and sent.get('parsed') and sent.get('checked'))
        return {'passed': bool(passed), 'checks': checked, 'attempts': attempts, 'fault_repair': repaired,
                'faulted_after': sent.get('faulted_after'), 'exercise': True, 'decision_used_for_adoption': False}
    return st.unit('engineer-r1', work)


def _s3c(setting, services):
    """One measured fault-repair engineer call; repaired quality is information."""
    from . import alf_smoke, zebra_smoke
    configuration = p.configuration_of(setting)
    p.require(p.is_v291(configuration), "S3c belongs only to v2.9.1")
    alf = p.is_alfworld(configuration)
    owner = alf_smoke if alf else zebra_smoke
    st, cut = (owner._fixture_step(setting, services, 'S3c') if alf
               else owner._fixture_step(setting, services, 'D', 'S3c'))
    identity = {'run': setting.run, 'configuration': configuration, 'chain': 'D', 'substage': 'S3c',
                'recipe': 'v292-fault-repair-v1' if p.is_v292(configuration) else 'v291-fault-repair-v1',
                'fixtures_sha256': digest(cut),
                'proposal_sha256': digest(authored_fault_reply(st.bench, configuration=configuration))}
    cached = owner._cached_substage(st, identity)
    if cached is not None:
        return cached
    measured = owner._measured_roles(st)
    with owner._fixture_environment(cut['run']) if alf else contextlib.nullcontext():
        step._run(st, cut)
        proposed = _fault_repair_proposal(st, cut)
    measurements = smoke.role_calls_measured([json.loads(row) for row in measured.read_text().splitlines()]
                                             if measured.exists() else [])
    sent = measurements.get('engineer') or {}
    return owner._save_substage(st, identity, {
        'passed': bool(proposed['passed'] and sent.get('calls') == 1 and sent.get('tokens', 0) > 0
                       and sent.get('request_bytes', 0) > 0),
        'proposal': proposed, 'role_measurements': measurements, 'exercise': True,
        'faulted_after': proposed.get('faulted_after'), 'decision_used_for_adoption': False})


def _merge_measurements(left, right):
    result = copy.deepcopy(left)
    for role, row in right.items():
        if role not in result:
            result[role] = copy.deepcopy(row)
        else:
            current = result[role]
            current['calls'] += row['calls']
            current['tokens'] += row['tokens']
            current['request_bytes'] = max(current['request_bytes'], row['request_bytes'])
            current['per_call'] = current['tokens'] / current['calls']
    return result
