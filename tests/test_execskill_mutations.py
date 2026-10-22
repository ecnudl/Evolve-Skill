"""Break-the-code checks (implementation plan §8.3): each mutation is applied to a temporary copy of the tree and the
named test must FAIL there; the same tests pass on the unmutated copy first. Every mutation site must occur exactly
once in its file, so a moved or rewritten site fails this suite loudly instead of passing silently. Covered: (1)-(30),
and 31-36 for later registrar decisions (C3-1 (b): the run-root canary scan; C1-2: the no-workbook probe;
PR-C31-3: the read record's training-side skip and the owner's release, tickets PR-C31-2, PR-C12-2, P2-A3-2),
and 37-55 for the registrar addendum 2026-10-22 14:10 (P2C): the first-call confirmation's call, checks, reuse and
sub-scope (row 7), the test-read estimate, its file and chain G's corrected read gate (row 8), the chain-level read
consent check (row 9) and the finished acceptance round that ``recover`` refuses (row 17); 56-77 for the later addenda
of 2026-10-22: tickets P2C-1 (a step unit needs its chain's passed first call of this run) and P2C-2 (a relaunched
read gate prices the units still to run by their pinned per-bench terms), the 15:0x manual smoke path, ``probe
--fake`` and probe-root checks, the 15:5x R1-R6 checks (SpreadsheetBench references, the stored workbooks' mounts,
bindings QA-only, the role-call logs, doubled signs, the probe gates' v2 token, the S0 pins, the completing attempt's
projection) and the R7 decision 16:1x (the step-wide engineer call count, the engineer's GLM reservation floor);
78-110 for Codex's round of 2026-10-22 and the owner's main experiment (registrar 17:0x/17:3x): SpreadsheetBench
test routing and placebo lengths mounting the public workbook only, the qualification artifacts' cleanup (78-80),
the per-call sandbox directory and the reflection ban (81-83), exact detector fractions, twin firings outside A* and
the disclosed SpreadsheetBench values (84-87), the main configuration's order, record-only cost check, caps, real-run
label, ALFWorld pool and the S0 equivalence verdict (88-93), registry ownership by run root, per-bench endpoints and
the memory lock of mixed-bench units, the completion commit, the band probe's minimum and the finding counter (94-101),
SearchQA's kept tail and its exclusion, LiveMath's options-only J7 probe and ALFWorld's fresh supply and views
(102-107), and chain D's route B: balance exhaustion, no switch under a running process, one pause per switch
(108-110); 111 for the smoke S0 of 2026-10-22 22:07: the supply row accepts the room-capped selection slice. (21) is checked on its "after dispatch" half: donor trajectories changed after sealing are accepted
(``donors.verify``); its "from acceptance items" half has no single mutation site, because the donor builder never
receives an acceptance item (``donors.donor_corpus`` takes the run-slice trajectories only), and T-PLACEBO-6 scans the
sealed text for acceptance-item text. (27) is checked on both halves: a changed archive file accepted on open, and a
redirect to a non-frozen host followed. Offline; runs the copied tests with ``python -B`` and the launch environment."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from skillopt.execskill.prelaunch import launch_env

REPO = Path(__file__).resolve().parents[1]
COPIED = ("skillopt", "scripts", "tests")
PE = "skillopt/execskill/"
T = "tests/test_execskill_"

MUTATIONS = {
    "01-shell-appends-to-the-reply": (
        PE + "solver.py", "        return shell.available(response, costs, reason)\n",
        "        return shell.available(response + \" (checked)\", costs, reason)\n",
        [T + "solver.py::test_t_solver_2_notes_are_the_last_user_key_and_the_reply_is_delivered_unchanged"]),
    "02-router-reads-private": (
        PE + "solver.py", "        return registered\n    return view\n",
        "        return registered\n    return {**public, **view}\n",
        [T + "router.py::test_t_route_3_routing_views_are_made_from_public_data_only"]),
    "03-placebo-forgets-the-header": (
        PE + "solver.py", "        text = notes.render(kept, bench=self.bench, header=procedure.header) if kept else \"\"\n",
        "        text = notes.render(kept, bench=self.bench, header=procedure.header if public_text is not None "
        "else \"\") if kept else \"\"\n",
        [T + "placebo.py::test_t_placebo_3_the_shell_keeps_the_header_and_shows_the_donor_content"]),
    "04-registry-allows-re-dispatch": (
        PE + "registry.py", "    if held is not None and not _owns(held, unit, run_root):\n",
        "    if held is not None and not _owns(held, unit, run_root) and target != DISPATCHED:\n",
        [T + "registry.py::test_another_unit_conflicts_and_a_failing_call_writes_nothing"]),
    "05-replay-serves-only-the-last-call": (
        PE + "cells.py", "    replay = Replay(log.entries)\n", "    replay = Replay(log.entries[-1:])\n",
        [T + "cells.py::test_t_cells_1_2_a_two_call_cell_re_executes_by_replaying_its_logical_calls_in_order"]),
    "06-endpoint-built-with-m": (
        PE + "budgets.py", "return Endpoint(client, model=client.model, max_tokens=max_tokens_bound,",
        "return Endpoint(client, model=client.model, max_tokens=client.max_tokens,",
        [T + "budgets.py::test_t_ledger_2_completion_between_m_and_b_does_not_halt"]),
    "07-canonicaliser-searches-the-reply": (
        PE + "canonical.py", "        return matches[0], where + \"_level1\"\n    return raw, \"unchanged\"\n",
        "        return matches[0], where + \"_level1\"\n    found = [c for c in admissible if c in reply]\n"
        "    if found:\n        return min(found, key=reply.find), \"whole_level1\"\n    return raw, \"unchanged\"\n",
        [T + "canonical.py::test_no_search_of_the_reply"]),
    "08-detector-view-shows-the-step-count": (
        PE + "trajectories.py", "                      for step in steps[:LANDMARK_STEPS]]}\n",
        "                      for step in steps]}\n",
        [T + "detectors.py::test_det1_masked_views_hide_answers_run_status_and_step_count"]),
    "09-v2-turns-a-pass-into-a-fail": (
        PE + "judge.py", "    v2 = \"pass\" if rescued else final\n"
        "    require(v2 == final or (final == \"fail\" and v2 == \"pass\"), \"Scorer v2 below the completion-aware verdict\")\n"
        "    require(v2 == \"pass\" or official[\"status\"] != \"pass\", \"Scorer v2 below the official score\")\n",
        "    v2 = \"pass\" if rescued else \"fail\"\n",
        [T + "judge.py::test_t_judge_1_v2_never_below_official_or_final"]),
    "10-consent-accepts-extra-keys": (
        PE + "evaluation.py", "set(value) == CONSENT_FIELDS and value[\"by\"] == \"owner\"",
        "set(value) >= CONSENT_FIELDS and value[\"by\"] == \"owner\"",
        [T + "evaluation.py::test_eval1_the_consent_key_set_is_exact"]),
    "11-worker-child-keeps-stdout": (
        PE + "sandbox/worker.py", "    for fd in (0, 1, 2):\n        os.dup2(null, fd)\n",
        "    for fd in (0, 2):\n        os.dup2(null, fd)\n",
        [T + "sandbox.py::test_sbx06_printing_never_reaches_the_frame_stream_or_stderr"]),
    "12-alfworld-view-keeps-infos-extra": (
        PE + "solver.py", "                         \"recent_history\": prompt_history[-5:]}\n",
        "                         \"recent_history\": prompt_history[-5:],\n"
        "                         \"extra\": {k: v for k, v in infos[0].items() if k.startswith(\"extra.\")}}\n",
        [T + "solver.py::test_t_solver_8_alfworld_hooks_keep_the_shown_list_and_no_private_metadata"]),
    "13-residual-uses-full-episode-categories": (
        PE + "detectors.py",
        "    categories = {cell: mechanical_masked(view, bench=bench) for cell, view in views.items()}\n",
        "    categories = {t[\"cell\"]: mechanical(t, bench=bench) for t in halves[\"hold\"] if t[\"cell\"] in views}\n",
        [T + "detectors.py::test_det4_all_failures_run_50_steps_yet_a_landmark_detector_can_be_accepted"]),
    "14-episode-slot-wait-maps-to-p4": (
        PE + "slots.py", "        return self._slot(log_every_s=log_every_s)\n",
        "        return self._slot(log_every_s=log_every_s, timeout_s=SHORT_HOLD_SECONDS)\n",
        [T + "slots.py::test_t_slot_1_heavy_tailed_episodes_all_finish_without_p4"]),
    "15-exclusion-accepts-the-test-read-consent": (
        PE + "exclusion.py", "    runs = value.get(\"exclusion_runs\") if isinstance(value, dict) else None\n",
        "    if isinstance(value, dict) and value.get(\"test_evaluation\") is True:\n        return value\n"
        "    runs = value.get(\"exclusion_runs\") if isinstance(value, dict) else None\n",
        [T + "exclusion.py::test_consent_key_set_is_exact"]),
    "16-v2-reads-the-json-beside-a-usable-tag": (
        PE + "judge.py", "    if _usable_tag(bench, reply, tag):\n        return tag, \"official\"\n",
        "    if _usable_tag(bench, reply, tag) and json_answer(reply) is None:\n        return tag, \"official\"\n",
        [T + "judge.py::test_t_judge_5_a_usable_official_carrier_is_used_exclusively"]),
    "17-preflight-reads-the-last-receipt": (
        PE + "outcomes_ext.py", "    verdict = _delivery(reason, receipts, deciding)\n",
        "    verdict = _delivery(reason, receipts, len(receipts) - 1 if receipts else deciding)\n",
        [T + "outcomes_ext.py::test_t_out_4_delivery_checks_read_the_deciding_receipt_never_the_last"]),
    "18-every-close-checks-the-whole-prefix": (
        PE + "sandbox/client.py", "            cleanup(container.name, docker=self.docker)\n",
        "            cleanup(container.name, docker=self.docker)\n            drain_check(docker=self.docker)\n",
        [T + "sandbox.py::test_sbx13_two_live_workers_close_by_exact_name_and_drain_by_prefix"]),
    "19-evaluation-store-keeps-raw-replies": (
        PE + "evaluation.py",
        "                      \"reply_sha256\": _sha(reply), \"completion_tokens\": _completion_tokens(receipt)})\n",
        "                      \"reply_sha256\": _sha(reply), \"completion_tokens\": _completion_tokens(receipt),\n"
        "                      \"reply\": reply})\n",
        [T + "evaluation.py::test_eval2_a_multi_arm_unit_shares_structural_zeros_and_seals_hashes_only"]),
    "20-qualify-stamps-v3": (
        PE + "qualify.py", "    write_json(root / \"qualification.json\", value)\n",
        "    value = {**value, \"version\": \"fivebench-coevolution-v3-sheet-qualification\"}\n"
        "    write_json(root / \"qualification.json\", value)\n",
        [T + "qualify.py::test_qual1_the_copied_closure_stamps_this_protocol_and_scores_through_the_frozen_helpers"]),
    "21-placebo-donors-changed-after-sealing-accepted": (
        PE + "donors.py", "    moved = sorted(d for d, sha in corpus[\"sources\"].items() if found.get(d) != sha)\n",
        "    moved = []\n",
        [T + "placebo.py::test_t_placebo_6_donors_are_zero_call_sealed_and_free_of_acceptance_text"]),
    "22-landmark-view-keeps-the-terminal-observation": (
        PE + "trajectories.py", "    if not longer:\n        return Excluded(\"ended_by_step_10:\"",
        "    if not steps:\n        return Excluded(\"ended_by_step_10:\"",
        [T + "trajectories.py::test_t_traj_1_the_landmark_view_keeps_ten_nonterminal_steps_of_long_episodes_only"]),
    "23-replay-serves-a-resent-transport-reply": (
        PE + "cells.py", "        entry[\"receipt\"], entry[\"receipt_index\"] = receipt, index\n",
        "        entry[\"receipt\"], entry[\"receipt_index\"] = self.recorder.sends[sends].get(\"receipt\", receipt), "
        "index\n",
        [T + "cells.py::test_t_cells_4_a_resent_call_and_a_repair_replay_as_two_logical_calls"]),
    "24-j1-decided-by-the-sign-flip-p": (
        PE + "stats_ext.py", "    p = max(first[\"p\"], second[\"p\"])\n",
        "    p = max(signflip(d1, n=2000, seed=1), signflip(d2, n=2000, seed=1))\n",
        [T + "stats_ext.py::test_t_stats_4_a_decision_follows_the_t_test_only"]),
    "25-s1e-counted-as-production": (
        PE + "smoke.py", "    if entry.get(\"probe\") == \"e\" or entry[\"cell\"] in spec[\"control_cells\"]:\n"
        "        return CONTROL\n",
        "    if entry[\"cell\"] in spec[\"control_cells\"]:\n        return CONTROL\n"
        "    if entry.get(\"probe\") == \"e\":\n        return PRODUCTION\n",
        [T + "smoke.py::test_t_smoke_1_receipt_classes"]),
    "26-router-plans-a-third-twin": (
        PE + "router.py", "            if len(held) < MAX_TWINS_PER_ITEM:\n",
        "            if len(held) <= MAX_TWINS_PER_ITEM:\n",
        [T + "router.py::test_t_route_5_astar_by_edit_type_and_the_twin_draws"]),
    "27a-research-archive-accepts-a-changed-file": (
        PE + "research.py", "            require(hashlib.sha256(raw).hexdigest() == entry[\"sha256\"], \"An archived "
        "document changed: \" + name)\n", "",
        [T + "research.py::test_res1_changed_archive_file_refused_on_open"]),
    "27b-research-follows-a-redirect-to-another-host": (
        PE + "research.py", "trust_env=False, follow_redirects=False,", "trust_env=False, follow_redirects=True,",
        [T + "research.py::test_res1_explicit_proxy_only_and_no_other_host"]),
    "28-family-builds-items-without-a-finding": (
        PE + "generators/__init__.py",
        "        return {\"status\": \"no_material\", \"items\": [], \"made\": 0, \"dropped\": {}}\n",
        "        material = {\"kind\": MATERIAL_KINDS[family_.material]}\n",
        [T + "generators.py::test_gen6_items_only_from_qualified_findings_and_at_most_ten_per_finding"]),
    "29-chains-share-one-consumption-namespace": (
        PE + "registry.py", "        return self.root / \"consumption\" / chain / (bench + \".jsonl\")\n",
        "        return self.root / \"consumption\" / (\"smoke\" if chain == \"smoke\" else \"chains\") / (bench + "
        "\".jsonl\")\n",
        [T + "registry.py::test_chains_have_separate_namespaces_and_smoke_items_leave_both_supplies"]),
    "30-glm-solver-client-adds-a-route": (
        PE + "client.py", "                      read_timeout=READ_TIMEOUT_SECONDS, transport=transport)\n"
        "    except (SystemExit, OSError) as refusal:",
        "                      read_timeout=READ_TIMEOUT_SECONDS, transport=transport, route=\"bigmodel\",\n"
        "                      route_env=config[\"repo\"])\n    except (SystemExit, OSError) as refusal:",
        [T + "client.py::test_chain_g_gets_the_frozen_bigmodel_client_built_like_v3"]),
    "31-unseal-skips-the-run-root-scan": (
        PE + "evaluation.py", "    scan = _root_scanned(safe_path(root), chain_root, chain, evidence=evidence)\n",
        "    scan = None\n",
        [T + "canaries.py::test_a_canary_planted_in_the_run_root_pauses_the_unseal_until_the_owner_decides"]),
    "32-no-workbook-view-shows-the-preview": (
        PE + "solver.py", "    if shortcut != NO_WORKBOOK:\n", "    if True:\n",
        [T + "shortcut_sb.py::test_c1_2_the_no_workbook_request_holds_no_workbook_byte_or_preview_text"]),
    "33-cell-runner-drops-the-probe-mode": (
        PE + "cells.py", '        extra["shortcut"] = cell["shortcut"]\n', "        pass\n",
        [T + "shortcut_sb.py::test_c1_2_a_probe_cell_hands_its_mode_to_the_shell_and_its_record_states_it"]),
    "34-read-canaries-skip-nothing-on-the-training-side": (
        PE + "evaluation.py", "            found, counts = select_canaries(texts, skip=skip)\n",
        "            found, counts = select_canaries(texts)\n",
        [T + "canaries.py::test_the_read_selection_skips_test_texts_found_verbatim_in_the_same_field_of_the_"
         "training_pools"]),
    "35-a-release-of-any-record-is-accepted": (
        PE + "evaluation.py", "status.get(\"scan_sha256\") == scan[RECORD_HASH]\n            == match.group(1),",
        "status.get(\"scan_sha256\") == scan[RECORD_HASH],",
        [T + "canaries.py::test_the_owner_releases_exactly_the_paused_scan_and_the_marker_names_the_release"]),
    "36-a-release-covers-any-hits": (
        PE + "evaluation.py",
        "    return released is not None and all(scan[key] == released.get(key) for key in keys)\n",
        "    return released is not None\n",
        [T + "canaries.py::test_a_release_covers_exactly_the_released_hits_and_any_other_scan_pauses"]),
    # registrar addendum 2026-10-22 14:10 (P2C): row 7, the first-call confirmation
    "37-chain-starts-without-its-first-call-confirmation": (
        PE + "chain.py", "            first_call(setting, chain, before=",
        "            (lambda *args, **kwargs: None)(setting, chain, before=",
        [T + "chain.py::test_row7_one_confirmed_reply_alone_before_the_first_unit_and_a_relaunch_reuses_it"]),
    "38-first-call-takes-an-undelivered-reply": (
        PE + "chain.py", "    checks = {\"reply\": receipt.get(\"ok\") is True,", "    checks = {\"reply\": True,",
        [T + "chain.py::test_row7_each_failure_stops_the_chain_before_its_first_unit_and_a_relaunch_calls_again"
         "[truncated]"]),
    "39-first-call-takes-any-echoed-model": (
        PE + "chain.py", "receipt.get(\"returned_model\") in echo,",  # M4: the route's echo set (_confirm_of)
        "receipt.get(\"returned_model\") is not None,",
        [T + "chain.py::test_row7_the_confirmations_own_checks_hold_whatever_the_client_reports[g-echo]"]),
    "40-first-call-passes-with-nothing-settled": (
        PE + "chain.py", "type(entry.get(\"charged\")) is int and entry[\"charged\"] > 0,",
        "type(entry.get(\"charged\")) is int and entry[\"charged\"] >= 0,",
        [T + "chain.py::test_row7_each_failure_stops_the_chain_before_its_first_unit_and_a_relaunch_calls_again"
         "[zero-settled]"]),
    "41-first-call-skips-chain-ds-reasoning-check": (
        PE + "chain.py", "              \"reasoning\": None if glm else (",
        "              \"reasoning\": None if True else (",
        [T + "chain.py::test_row7_the_confirmations_own_checks_hold_whatever_the_client_reports[d-reasoning-tokens]"]),
    "42-a-relaunch-calls-again-despite-confirm-json": (
        PE + "chain.py", "    if (root / confirm).exists():\n", "    if False:\n",  # M4: the route's file
        [T + "chain.py::test_row7_one_confirmed_reply_alone_before_the_first_unit_and_a_relaunch_reuses_it"]),
    "43-first-call-charged-without-its-sub-scope": (
        PE + "budgets.py", "    return ROOT, chain + \":solver\", chain + \":\" + CONFIRM\n",
        "    return ROOT, chain + \":solver\"\n",
        [T + "chain.py::test_row7_one_confirmed_reply_alone_before_the_first_unit_and_a_relaunch_reuses_it"]),
    # row 8, the test-read estimate and chain G's corrected read gate
    "44-estimate-prices-five-arms-per-fired-item": (
        PE + "protocol.py", "TEST_READ_ESTIMATE_ARMS = 4\n", "TEST_READ_ESTIMATE_ARMS = 5\n",
        [T + "protocol.py::test_the_test_read_estimate_is_calc_t5s_high_row_at_the_high_anchors"]),
    "45-estimate-prices-a-missing-procedure-cell-low": (
        PE + "protocol.py", "        proc = card * PROCEDURE_ARM_FACTOR[1] if assumed else",
        "        proc = card * PROCEDURE_ARM_FACTOR[0] if assumed else",
        [T + "protocol.py::test_the_test_read_estimate_is_calc_t5s_high_row_at_the_high_anchors"]),
    "46-estimate-from-a-smoke-that-did-not-pass": (
        PE + "chain.py", "result[\"spec\"] == spec[RECORD_HASH] and result[\"passed\"] is True and \"SE6\" in",
        "result[\"spec\"] == spec[RECORD_HASH] and \"SE6\" in",
        [T + "cli.py::test_test_read_estimate_writes_the_sealed_estimate_of_a_passed_smoke_once"]),
    "47-test-read-estimate-file-rewritten": (
        "scripts/run_execskill.py",
        "    require(not out.exists(), \"%s exists: the test-read estimate is written once\" % out)\n", "",
        [T + "cli.py::test_test_read_estimate_writes_the_sealed_estimate_of_a_passed_smoke_once"]),
    "48-chain-g-read-gate-ignores-its-cost-factor": (
        PE + "chain.py", "        used = math.ceil(part * max(Fraction(1), factor))\n", "        used = part\n",
        [T + "chain.py::test_row8_chain_g_reads_within_1_3_x_its_estimate_corrected_by_its_cost_factor"]),
    "49-chain-g-read-gate-reads-its-first-cost-check": (
        PE + "chain.py", "    while path.with_name(\"cap-check-G-%d.json\" % (n + 1)).exists():\n",
        "    while False:\n",
        [T + "chain.py::test_row8_the_gate_reads_chain_gs_latest_passed_cost_check_and_needs_one"]),
    "50-cost-projection-projects-the-spent-confirm-scope": (
        PE + "step.py",
        "                and \":role:\" not in scope and scope != \"%s:%s\" % (chain, budgets.CONFIRM):\n",
        "                and \":role:\" not in scope:\n",
        [T + "step.py::test_cost_projection_rescales_chain_g_caps_by_the_measured_cost_per_cell"]),
    # row 9, the chain-level read consent check
    "51-chain-reads-without-checking-the-consent": (
        PE + "chain.py",
        "                read_consent(setting, chain)  # registrar addendum 14:10, row 9: before any read child "
        "starts\n",
        "                pass\n",
        [T + "chain.py::test_row9_a_missing_consent_opens_no_read_attempt_and_the_relaunch_reads"]),
    # row 17, a finished acceptance round is final
    "52-finished-round-ignores-a-block-still-to-run": (
        PE + "acceptance.py",
        "    if not blocks or len(earlier_blocks(sealed, unit_root, following)[\"reused\"]) != len(blocks):\n",
        "    if not blocks:\n",
        [T + "acceptance.py::test_row17_a_round_with_a_block_still_to_run_or_without_a_sealed_round_is_not_final"]),
    "53-finished-round-misses-an-undetermined-decision": (
        PE + "acceptance.py", "    if kind == \"acceptance_undetermined\" or decision == \"undetermined\":\n",
        "    if kind == \"acceptance_undetermined\":\n",
        [T + "acceptance.py::test_row17_a_round_whose_cells_are_all_done_and_that_paused_undetermined_or_in_decide_"
         "is_final"]),
    "54-finished-round-takes-any-error-for-decides": (
        PE + "acceptance.py",
        "    if log.exists() and DECIDE_FRAME.search(log.read_text(encoding=\"utf-8\", errors=\"replace\")):\n",
        "    if log.exists():\n",
        [T + "acceptance.py::test_row17_a_round_whose_cells_are_all_done_and_that_paused_undetermined_or_in_decide_"
         "is_final"]),
    "55-recover-redoes-a-finished-acceptance-round": (
        "scripts/run_execskill.py", "    finished = acceptance.finished_round(attempt)\n", "    finished = None\n",
        [T + "cli.py::test_recover_refuses_a_finished_acceptance_round"]),
    # registrar addendum 2026-10-22 15:3x: tickets P2C-1 and P2C-2
    "56-step-unit-starts-without-a-confirmed-first-call": (
        PE + "step.py", "    confirmation(manifest[\"root\"], manifest[RECORD_HASH], chain)  # ticket P2C-1",
        "    (lambda *args: None)(manifest[\"root\"], manifest[RECORD_HASH], chain)  # ticket P2C-1",
        [T + "runcli.py::test_step_unit_runs_one_step_of_the_order_and_maps_its_pause_to_the_exit_code"]),
    "57-step-unit-takes-another-runs-confirmation": (
        PE + "chain.py",
        "    require(found[\"identity\"] == identity and found[\"passed\"] is True,\n",
        "    require(found[\"passed\"] is True or True,\n",
        [T + "runcli.py::test_step_unit_runs_one_step_of_the_order_and_maps_its_pause_to_the_exit_code"]),
    "58-a-relaunched-read-gate-prices-the-whole-estimate": (
        PE + "chain.py", "    if len(units) < len(BENCHES):  # ticket P2C-2: a relaunch prices only the read units",
        "    if False:  # ticket P2C-2: a relaunch prices only the read units",
        [T + "chain.py::test_p2c_2_a_relaunched_read_gate_prices_only_the_read_units_still_to_run"]),
    "59-setting-takes-terms-of-another-estimate": (
        PE + "manifest.py", "_read_terms(terms.get(chain), estimate[chain])",
        "isinstance(terms.get(chain), dict)",
        [T + "manifest.py::test_p2c_2_setting_of_needs_each_chains_per_bench_terms_of_its_estimate"]),
    # registrar addendum 2026-10-22 15:0x: the manual smoke path, probe --fake and the probe roots
    "60-manual-smoke-stage-records-any-stage": (
        "scripts/run_execskill.py", "    require(args.stage in MANUAL_STAGES, ", "    require(True, ",
        [T + "cli.py::test_smoke_make_writes_once_then_stages_and_summary"]),
    "61-probe-fake-takes-a-credential": (
        "scripts/run_execskill.py", "        require(args.env_path is None, \"probe --fake names no credential",
        "        require(True, \"probe --fake names no credential",
        [T + "cli.py::test_probe_fake_rehearses_s1_without_a_credential_and_labels_it_a_fixture"]),
    "62-probe-fake-runs-on-the-registered-probe-root": (
        "scripts/run_execskill.py", "        smoke.rehearsal_roots(spec, probe=True)\n",
        "        smoke.rehearsal_roots(spec)\n",
        [T + "cli.py::test_probe_fake_rehearses_s1_without_a_credential_and_labels_it_a_fixture"]),
    "63-s1-probe-runs-on-another-probe-root": (
        PE + "smoke.py", "    require(probe_root == safe_path(spec[\"probe_root\"]), ", "    require(True, ",
        [T + "smoke.py::test_s1_probe_on_its_own_ledger_judges_rows_a_to_f_and_keeps_no_reply_text"]),
    # registrar addendum 2026-10-22 15:5x, R1-R6
    "64-spreadsheetbench-references-left-out": (
        PE + "step.py", "            reference = _sheet_reference(item[\"private\"])\n",
        "            reference = item[\"private\"].get(\"answer\", item[\"private\"].get(\"answers\"))\n",
        [T + "step.py::test_r1_spreadsheetbench_references_are_the_answer_cells_as_the_frozen_scorer_reads_them"]),
    "65-sheet-reference-reads-an-uncached-formula-as-blank": (
        PE + "step.py", "                        if (sheet, coordinate) not in blanks:\n"
        "                            return None  # the frozen scorer's \"unavailable\": no complete reading\n", "",
        [T + "step.py::test_r1_spreadsheetbench_references_are_the_answer_cells_as_the_frozen_scorer_reads_them"]),
    "66-later-step-mounts-no-earlier-spreadsheet-workbook": (
        PE + "step.py", "for item in st.setting.pools.get(sheet, ())}\n", "for item in ()}\n",
        [T + "step.py::test_r2_every_stored_spreadsheetbench_trajectory_mounts_its_own_workbook_at_any_step"]),
    "67-bindings-hook-runs-on-spreadsheetbench": (
        PE + "solver.py", "and self.bench not in QA):\n", "and False):\n",
        [T + "solver.py::test_r3_bindings_is_qa_only_no_note_and_no_invitation_on_spreadsheetbench"]),
    "68-c1-takes-bindings-in-a-bench-without-calc": (
        PE + "engineer.py", "not set(NO_CALC_BENCHES) <= set(entry.get(\"excluded_benches\", [])):\n", "False:\n",
        [T + "engineer.py::test_r3_a_bindings_hook_whose_declared_scope_reaches_a_bench_without_calc_fails_c1"]),
    "69-role-calls-left-unlogged": (
        PE + "step.py", "                role_calls(root, attempt, self.calls)\n", "                pass\n",
        [T + "step.py::test_step1_one_fake_officeqa_step_through_the_eight_sub_steps"]),
    "70-doubled-multiplication-sign-makes-a-power": (
        PE + "compute.py", "    if POWER_OF_SIGNS.search(source):\n", "    if False:\n",
        [T + "compute.py::test_r6a_the_registered_signs_read_as_ascii_operators"]),
    "71-probe-gates-count-the-final-token": (
        PE + "examiner.py", "    token = judged[\"v2\"][\"token\"] if isinstance(judged, dict) else \"unknown\"\n",
        "    token = value[\"final\"][\"token\"] if isinstance(value.get(\"final\"), dict) else \"unknown\"\n",
        [T + "examiner.py::test_r6b_the_band_and_shortcut_gates_count_scorer_v2_tokens"]),
    "72-make-manifest-without-the-s0-pins": (
        "scripts/run_execskill.py", "    require({\"limits\", \"measured\"} <= set(pins), ", "    require(True, ",
        [T + "cli.py::test_make_manifest_takes_limits_and_measurements_from_the_s0_pins"]),
    "73-cost-projection-reads-the-first-attempts-scope": (
        PE + "step.py", "    run_scope = budgets.solver_scopes(chain, bench, k, \"run\", attempt)[-1]\n",
        "    run_scope = budgets.solver_scopes(chain, bench, k, \"run\")[-1]\n",
        [T + "step.py::test_cost_projection_rescales_chain_g_caps_by_the_measured_cost_per_cell"]),
    # the R7 decision 2026-10-22 16:1x
    "74-engineer-2-gets-a-fresh-call-count": (
        PE + "step.py",
        "        spent = 0 if unit == \"engineer\" else st.done(\"engineer\")[\"engineer\"][\"calls\"]\n",
        "        spent = 0\n",
        [T + "step.py::test_a_step_ending_before_the_acceptance_consumes_no_acceptance_item[blocked_twice]"]),
    "75-engineer-ignores-the-steps-earlier-calls": (
        PE + "engineer.py", "    if ctx.spent + ctx.roles.count(prefix) >= ENGINEER_CALLS:\n",
        "    if ctx.roles.count(prefix) >= ENGINEER_CALLS:\n",
        [T + "engineer.py::test_r7a_engineer_calls_are_counted_per_step_across_both_engineer_units"]),
    "76-engineer-context-takes-any-earlier-count": (
        PE + "engineer.py", "0 <= self.spent <= ENGINEER_CALLS,", "0 <= self.spent,",
        [T + "engineer.py::test_r7a_engineer_calls_are_counted_per_step_across_both_engineer_units"]),
    "77-engineer-glm-floor-without-its-system-prompt": (
        PE + "smoke.py", "    size[\"engineer\"] = max(size[\"engineer\"], ENGINEER_REQUEST_FLOOR)", "    pass",
        [T + "smoke.py::test_glm_projection_prices_every_glm_scope_at_the_registered_maximum_role_calls"]),
    # 78-80: Codex 2026-10-22 review findings 1 (SpreadsheetBench test routing and placebo-length replay mount the
    # item's public workbook) and 3 (the test qualification's reference artifacts go on every exit). V.
    "78-test-routing-mounts-no-workbook": (
        PE + "evaluation.py",
        "    workers = mounting(workers, public_inputs(bench, {task[\"task_id\"]: task for task in tasks}))\n", "",
        [T + "evaluation_sheet.py::"
         "test_codex1_a_workbook_dependent_predicate_dispatches_real_f_cells_on_spreadsheetbench_test_items"]),
    "79-placebo-lengths-mount-no-workbook": (
        PE + "evaluation.py", "            mounted = mounting(workers, public_inputs(bench, {item: task}))\n",
        "            mounted = workers\n",
        [T + "evaluation_sheet.py::"
         "test_codex1_the_placebo_lengths_are_measured_with_the_items_public_workbook_mounted"]),
    "80-failed-test-qualification-keeps-its-artifacts": (
        PE + "evaluation.py", "                _qualification_cleaned(attempt, evidence, when)\n",
        "                if when == \"complete\":\n"
        "                    _qualification_cleaned(attempt, evidence, when)\n",
        [T + "evaluation_sheet.py::"
         "test_codex3_a_failed_test_qualification_deletes_its_reference_artifacts_after_the_workers_drain"]),
    # 81-83: Codex 2026-10-22 review finding 6 (sandbox hidden filesystem state; reflection helpers). W.
    "81-call-writable-dir-not-removed": (
        PE + "sandbox/worker.py", "        _reset_writable(call_dir)\n", "        pass\n",
        [T + "sandbox.py::test_a_call_runs_in_a_private_writable_directory_removed_afterwards"]),
    "82-call-child-does-not-enter-its-private-dir": (
        PE + "sandbox/worker.py", "        os.chdir(call_dir)\n", "        pass\n",
        [T + "sandbox.py::test_each_call_child_runs_in_its_own_private_directory"]),
    "83-policy-allows-attrgetter-reflection": (
        PE + "policy.py", "\"ag_frame\", \"attrgetter\", \"cr_code\"", "\"ag_frame\", \"cr_code\"",
        [T + "policy.py::test_reflection_helpers_that_build_attribute_access_from_a_string_are_banned"]),
    # 84-87: Codex 2026-10-22 review findings 11 (the §7.1 detector minimum judged on exact counts), 12 (inherited
    # twins eligible on their firings in the acceptance slice A, §6.5) and 2 (route B's C4 check of the disclosed
    # SpreadsheetBench reference values, adjudicated with the values shown). E.
    "84-detector-recall-judged-on-the-rounded-float": (
        PE + "detectors.py", "    if _ratio(row[\"recall_counts\"]) < DETECTOR_MIN_RECALL:\n",
        "    if row[\"recall_residual\"] < DETECTOR_MIN_RECALL:\n",
        [T + "detectors.py::test_codex_11_recall_exactly_at_the_registered_minimum_is_accepted"]),
    "85-inherited-twin-firings-counted-inside-astar": (
        PE + "router.py", "    counts = {p: len(firing[p]) for p in inherited}\n",
        "    counts = {p: len([i for i in firing[p] if i in in_astar]) for p in inherited}\n",
        [T + "router.py::test_codex_12_inherited_twin_eligibility_and_draw_count_the_acceptance_slice_a"]),
    "86-engineer-skips-the-disclosed-sheet-references": (
        PE + "engineer.py", "        found = sheet_findings(ctx, text, public, quoted)\n", "        found = []\n",
        [T + "engineer.py::test_codex_2_a_copied_reference_in_a_source_literal_is_adjudicated_with_the_values",
         T + "engineer.py::"
         "test_codex_2_a_copied_reference_in_a_rendered_note_is_adjudicated_not_dropped_mechanically"]),
    "87-adjudicator-not-shown-the-disclosed-values": (
        PE + "engineer.py", "colliding=colliding[:3] or None, values=shown or None)", "colliding=colliding[:3] or None)",
        [T + "engineer.py::test_codex_2_a_copied_reference_in_a_source_literal_is_adjudicated_with_the_values"]),
    # 88-93: the main configuration (registrar addendum 2026-10-22 17:0x: its five-bench order, its caps at 3x, chain
    # G's record-only cost check, ALFWorld's pool from the fresh supply) and Codex 2026-10-22 review finding 13 (S0's
    # equivalence counts only frozen runs that sent requests and executed validly). M1.
    "88-main-cost-check-pauses-on-a-breach": (
        PE + "chain.py", "    if not measured[\"ok\"] and pauses:\n", "    if not measured[\"ok\"]:\n",
        [T + "chain.py::"
         "test_m1_mains_cost_check_records_a_breach_never_pauses_and_the_read_gate_applies_its_factor"]),
    "89-chain-runs-the-pilots-order-under-main": (
        PE + "chain.py", "    order = order_of(setting)\n", "    order = CONFIGURATIONS[PILOT][\"order\"]\n",
        [T + "chain.py::"
         "test_m1_main_runs_its_five_steps_in_mains_order_on_mains_caps_after_a_searchqa_confirmation"]),
    "90-s0-counts-an-unexecuted-frozen-run-as-same": (
        PE + "s0.py", "    if not frozen_call.requests or not _executed(bench, frozen):\n        return \"invalid\"\n",
        "",
        [T + "s0.py::"
         "test_m1_s0_equivalence_runs_on_the_cards_and_runtimes_and_marks_an_unexecuted_frozen_run_invalid"]),
    "91-manifest-takes-any-real-run-label": (
        PE + "manifest.py",
        "    require(value[\"evidence\"] not in real or value[\"evidence\"] == "
        "protocol.REAL_RUN_EVIDENCE[configuration],\n",
        "    require(True,\n",
        [T + "manifest.py::test_m1_a_main_manifest_carries_its_configuration_to_every_consumer"]),
    "92-export-pools-takes-v3s-alfworld-pool": (
        "scripts/run_execskill.py",
        "    pools[\"alfworld\"] = supply.alfworld_pool(fresh, views, runtime=v3[\"runtime\"][\"alfworld\"])\n",
        "    pools[\"alfworld\"] = supply.export_pool(v3[\"data\"], \"alfworld\")\n",
        [T + "cli.py::test_export_pools_writes_the_five_pools_once_and_prints_the_data_pools_pins"]),
    "93-main-projection-prices-caps-at-the-pilots-factor": (
        PE + "step.py", "    cap_factor = CONFIG_CAP_FACTOR[configuration_of(setting)]  #",
        "    cap_factor = COST_FACTOR  #",
        [T + "chain.py::test_m1_mains_cost_projection_prices_each_cap_at_a_third"]),
    # 94-101: Codex 2026-10-22 review findings 4 (a mixed self-test's cells on their own bench's client, M and B), 5
    # (the memory lock of every bench a unit runs), 7 (consumption ownership by label AND run root), 8 (the idempotent
    # completion and settlement commit), 9 (30 qualified band-probe items) and 10 (ten items per finding across the
    # attempt's builds). M2a.
    "94-registry-ownership-ignores-the-run-root": (
        PE + "registry.py",
        "    return held[\"unit\"] == unit and (run_root is None or held[\"run_root\"] == run_root)\n",
        "    return held[\"unit\"] == unit\n",
        [T + "registry.py::test_codex7_identical_labels_in_two_run_roots_never_share_an_item"]),
    "95-slices-exempt-the-same-labels-of-any-run-root": (
        PE + "step.py", "                and not (line[\"unit\"] in own and line[\"run_root\"] == here)} | ",
        "                and line[\"unit\"] not in own} | ",
        [T + "step.py::test_codex7_the_same_step_labels_under_another_run_root_hold_their_items_out_of_the_slices"]),
    "96-selftest-endpoint-takes-the-steps-client-and-bound": (
        PE + "units.py", "    on = bench if cell_bench is None else cell_bench\n", "    on = bench\n",
        [T + "units.py::test_codex4_a_cell_bench_endpoint_has_its_benchs_client_and_bound_on_the_steps_scopes",
         T + "step.py::test_codex4_5_a_mixed_self_test_runs_each_set_on_its_benchs_client_and_bound_and_lock"]),
    "97-mixed-unit-cells-sent-by-the-units-one-endpoint": (
        PE + "cells.py", "        recorder = context.endpoint_of(cell[\"benchmark\"]).recorder(",
        "        recorder = context.endpoint.recorder(",
        [T + "cells.py::test_codex4_each_cell_of_a_mixed_unit_is_sent_by_its_own_benchs_endpoint"]),
    "98-memory-lock-ignores-the-units-other-benches": (
        PE + "chain.py", "    mode = heavy_mode((bench, *more))\n", "    mode = heavy_mode((bench,))\n",
        [T + "chain.py::test_codex5_a_self_test_with_a_spreadsheet_set_never_overlaps_the_other_chains_heavy_units"]),
    "99-recovery-reruns-the-completed-work": (
        PE + "units.py", "        finished = completed(unit_root, run=run, identity=identity)  # a commit attempt",
        "        finished = None  # a commit attempt",
        [T + "units.py::test_codex8_a_failure_right_after_the_settlement_is_finished_by_a_commit_that_repeats_no_work",
         T + "units.py::test_codex8_a_failure_between_the_settlement_and_unit_json_is_committed_after_the_owners"
         "_decision"]),
    "100-insufficient-set-still-probed": (
        PE + "step.py", "            if not examiner.sufficient(built):  # §7.2, Codex finding #9",
        "            if False:  # §7.2, Codex finding #9",
        [T + "step.py::test_codex9_an_insufficient_generated_set_is_recorded_and_never_probed"]),
    "101-finding-counter-restarts-at-every-build": (
        PE + "step.py", "                               derived=_derived(attempt, set_name),\n",
        "                               derived=None,\n",
        [T + "examiner.py::test_codex10_ten_items_per_finding_hold_across_the_attempts_builds"]),
    # 102-107: the five-bench step wiring of the main configuration (registrar addendum 2026-10-22 17:0x/17:3x):
    # SearchQA's acceptance slice from the kept fresh tail, LiveMath's J7 options-only probe, ALFWorld on the fresh
    # supply with views of the pinned runtime. M2b.
    "102-searchqa-acceptance-skips-its-test-exclusion": (
        PE + "step.py", "    return list(kept[\"items\"]), kept\n", "    return list(tail[\"items\"]), kept\n",
        [T + "fivebench_step.py::test_searchqa_runs_on_the_pool_and_accepts_on_the_kept_tail"]),
    "103-searchqa-tail-takes-any-persisted-exclusion": (
        PE + "step.py", "record_sha256=pin[\"exclusion\"][\"record_sha256\"])", "record_sha256=None)",
        [T + "fivebench_step.py::test_searchqa_tail_is_cut_only_with_its_pin_and_the_bound_exclusion"]),
    "104-j7-probe-cells-keep-the-stem": (
        PE + "step.py", "            **{item[\"task_id\"]: _options_only(item) for item in probe},\n", "",
        [T + "fivebench_step.py::test_j7_the_accept_unit_registers_the_probe_and_sends_it_options_only"]),
    "105-alfworld-step-takes-views-of-another-runtime": (
        PE + "step.py", "            require(item.get(\"views_runtime_sha256\") == pinned, ", "            require(True, ",
        [T + "fivebench_step.py::test_alfworld_step_refuses_games_without_a_view_of_the_pinned_runtime"]),
    "106-alfworld-pool-ignores-the-views-runtime": (
        PE + "supply.py", "    require(pinned is not None and views_value.get(\"runtime_sha256\") == pinned,\n",
        "    require(pinned is not None,\n",
        [T + "fivebench_step.py::test_alfworld_pool_is_the_fresh_supply_with_views_of_the_pinned_runtime"]),
    "107-alfworld-pool-keeps-only-the-viewed-games": (
        PE + "supply.py", "    for game in ordered:\n        public, bound = ",
        "    for game in [g for g in ordered if g[\"task_id\"] in views]:\n        public, bound = ",
        [T + "fivebench_step.py::"
         "test_alfworld_step_cuts_the_run_and_acceptance_room_groups_and_blocks_whole_rooms"]),
    # registrar row "deepseek route B" (owner instructions 2026-10-22 17:3x; M4): chain D's second provider
    "108-route-balance-exhaustion-retried-as-a-rate-limit": (
        PE + "client.py", "        signal = balance_signal(response.status_code, response.content)\n",
        "        signal = None\n",
        [T + "routes.py::test_route_b_balance_exhaustion_is_raised_at_once_never_retried_and_nothing_is_sent_after"]),
    "109-route-switches-under-a-running-process": (
        PE + "manifest.py",
        "            routes.check_bound(safe_path(m[\"root\"]) / run, route, run=m[protocol.RECORD_HASH], chain=run)\n",
        "            pass\n",
        [T + "routes.py::test_setting_of_binds_the_route_per_process_and_a_unit_never_switches_mid_run"]),
    "110-route-switch-without-a-balance-pause-or-reason": (
        PE + "routes.py", "        require(reason is not None or (kind == BALANCE_EXHAUSTED and not spent), ",
        "        require(True or (kind == BALANCE_EXHAUSTED and not spent), ",
        [T + "routes.py::test_switch_route_refuses_a_live_or_unexplained_switch_then_writes_once_and_prints_recover"]),
    "111-s0-supply-row-demands-the-full-selection-slice": (
        PE + "s0.py",
        "    full = set(cut) == set(sizes) and all(len(cut[name]) <= size if name in supply.UPTO else len(cut[name]) == size\n",
        "    full = len(wanted) == sum(sizes.values()) and all(len(cut[name]) <= size if name in supply.UPTO else "
        "len(cut[name]) == size\n",
        [T + "s0.py::test_s0_supply_row_accepts_the_room_capped_selection_slice"]),
}


def _pytest(root, tests):
    return subprocess.run([sys.executable, "-B", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests],
                          cwd=root, env=launch_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=900, check=False)


@pytest.fixture(scope="module")
def copy(tmp_path_factory):
    """A copy of the tree (no caches) whose named tests pass before any mutation."""
    root = tmp_path_factory.mktemp("mutations")
    for name in COPIED:
        shutil.copytree(REPO / name, root / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if (REPO / "pyproject.toml").exists():  # the snapshot holds skillopt/, scripts/ and tests/ only (plan §10 step 1)
        shutil.copy2(REPO / "pyproject.toml", root / "pyproject.toml")
    tests = sorted({test for *_, named in MUTATIONS.values() for test in named})
    done = _pytest(root, tests)
    assert done.returncode == 0, done.stdout.decode("utf-8", "replace")[-3000:]
    return root


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_mutation_makes_its_named_test_fail(copy, name):
    path, old, new, tests = MUTATIONS[name]
    target = copy / path
    original = target.read_text(encoding="utf-8")
    assert original.count(old) == 1, "mutation site of %s not found exactly once in %s" % (name, path)
    target.write_text(original.replace(old, new), encoding="utf-8")
    try:
        done = _pytest(copy, tests)
    finally:
        target.write_text(original, encoding="utf-8")
    output = done.stdout.decode("utf-8", "replace")
    assert done.returncode == 1 and " failed" in output, output[-3000:]
