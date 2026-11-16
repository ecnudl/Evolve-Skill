post-hoc owner-requested re-read of byte-identical requests (D-chain SkillOpt step-3 text) on the SearchQA and OfficeQA test panels, replies kept for format-tolerant scoring; not the registered 5x5; one read stands for S3, S4 and S5, whose requests were byte-identical in the original run

Accuracies are fractions; paired means and CIs are percentage points.
A limited or budget-stopped read is partial. Registered comparators are never re-scored.
An unavailable CI means too few items or no residual degrees of freedom in the registered strata.

**Execution and usage**

```json
{
  "status": "complete",
  "arms": [
    "S3"
  ],
  "calls": {
    "planned": 572,
    "selected": 572,
    "sent": 572,
    "failed": 1,
    "unsent": 0,
    "unsent_limit": 0,
    "unsent_dry_run": 0,
    "unsent_budget": 0,
    "client_calls": 572,
    "http_attempts": 572
  },
  "usage": {
    "prompt_tokens": 1713488,
    "completion_tokens": 70310,
    "total_tokens": 1783798,
    "unknown_usage_calls": 0,
    "http_attempts_without_reported_usage": 0,
    "conservative_unreported_charge": 0
  },
  "budget": {
    "max_tokens_total": 4000000,
    "workers": 6,
    "stop_reason": null,
    "rule": "Stop new client calls at reported total; admitted calls and internal HTTP retries may overshoot. Unknown usage stops admission.",
    "overshoot_tokens": 0,
    "charged_toward_cap": 1783798,
    "usage_note": "Client receipts report terminal usage; earlier failed HTTP attempts may have unreported usage."
  },
  "statistics": {
    "function": "skillopt.execskill.textskill.readout.pair",
    "ci": "frozen paired-t 95%, registered strata",
    "mask": "registered D/SkillOpt all-arm mask intersect newly sent cells; C_end uses separate registered drift mask",
    "unknowns": "L for new reads, S2 and registered S3; H for C/B/C_end",
    "comparators": "registered durable verdicts remain unchanged under BOTH scoring rules",
    "identical_requests_zero": "secondary only; registered_pair_rule retains re-read noise",
    "resampling": "bootstrap, sign-flip and Wilcoxon skipped",
    "C_end": "reference only"
  },
  "requests_verified": {
    "searchqa": {
      "S3": 400
    },
    "officeqa": {
      "S3": 172
    }
  },
  "identical_s3_s4_s5": {
    "searchqa": {
      "items": 400,
      "identical": 400,
      "missing": 0
    },
    "officeqa": {
      "items": 172,
      "identical": 172,
      "missing": 0
    }
  }
}
```

**Zero-call durable carrier census**

| Chain | Method | Bench | Arm | n | None | Official | JSON | Other | Pass | Fail | Unknown | Fault unknown | Artifact unknown |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| G | skillopt | searchqa | C | 400 | 0 | 400 | 0 | 0 | 339 | 61 | 0 | 0 | 0 |
| G | skillopt | searchqa | B | 400 | 0 | 400 | 0 | 0 | 294 | 106 | 0 | 0 | 0 |
| G | skillopt | searchqa | C_end | 400 | 0 | 400 | 0 | 0 | 337 | 63 | 0 | 0 | 0 |
| G | skillopt | searchqa | S1 | 400 | 0 | 400 | 0 | 0 | 350 | 50 | 0 | 0 | 0 |
| G | skillopt | searchqa | S2 | 400 | 0 | 400 | 0 | 0 | 347 | 53 | 0 | 0 | 0 |
| G | skillopt | searchqa | S3 | 400 | 0 | 400 | 0 | 0 | 350 | 50 | 0 | 0 | 0 |
| G | skillopt | searchqa | S4 | 400 | 0 | 400 | 0 | 0 | 351 | 49 | 0 | 0 | 0 |
| G | skillopt | searchqa | S5 | 400 | 0 | 400 | 0 | 0 | 352 | 48 | 0 | 0 | 0 |
| G | skillopt | officeqa | C | 172 | 3 | 169 | 0 | 0 | 86 | 86 | 0 | 0 | 0 |
| G | skillopt | officeqa | B | 172 | 18 | 154 | 0 | 0 | 57 | 115 | 0 | 0 | 0 |
| G | skillopt | officeqa | C_end | 172 | 4 | 168 | 0 | 0 | 80 | 92 | 0 | 0 | 0 |
| G | skillopt | officeqa | S1 | 172 | 2 | 170 | 0 | 0 | 86 | 86 | 0 | 0 | 0 |
| G | skillopt | officeqa | S2 | 172 | 4 | 168 | 0 | 0 | 80 | 92 | 0 | 0 | 0 |
| G | skillopt | officeqa | S3 | 172 | 7 | 165 | 0 | 0 | 83 | 89 | 0 | 0 | 0 |
| G | skillopt | officeqa | S4 | 172 | 6 | 166 | 0 | 0 | 86 | 86 | 0 | 0 | 0 |
| G | skillopt | officeqa | S5 | 172 | 2 | 170 | 0 | 0 | 83 | 89 | 0 | 0 | 0 |
| G | gepa | searchqa | C | 400 | 0 | 400 | 0 | 0 | 339 | 61 | 0 | 0 | 0 |
| G | gepa | searchqa | B | 400 | 0 | 400 | 0 | 0 | 294 | 106 | 0 | 0 | 0 |
| G | gepa | searchqa | C_end | 400 | 0 | 400 | 0 | 0 | 337 | 63 | 0 | 0 | 0 |
| G | gepa | searchqa | S1 | 400 | 0 | 400 | 0 | 0 | 339 | 61 | 0 | 0 | 0 |
| G | gepa | searchqa | S2 | 400 | 0 | 400 | 0 | 0 | 343 | 57 | 0 | 0 | 0 |
| G | gepa | searchqa | S3 | 400 | 0 | 400 | 0 | 0 | 342 | 58 | 0 | 0 | 0 |
| G | gepa | searchqa | S4 | 400 | 0 | 400 | 0 | 0 | 340 | 60 | 0 | 0 | 0 |
| G | gepa | searchqa | S5 | 400 | 0 | 400 | 0 | 0 | 342 | 58 | 0 | 0 | 0 |
| G | gepa | officeqa | C | 172 | 3 | 169 | 0 | 0 | 86 | 86 | 0 | 0 | 0 |
| G | gepa | officeqa | B | 172 | 18 | 154 | 0 | 0 | 57 | 115 | 0 | 0 | 0 |
| G | gepa | officeqa | C_end | 172 | 4 | 168 | 0 | 0 | 80 | 92 | 0 | 0 | 0 |
| G | gepa | officeqa | S1 | 172 | 2 | 170 | 0 | 0 | 87 | 85 | 0 | 0 | 0 |
| G | gepa | officeqa | S2 | 172 | 4 | 168 | 0 | 0 | 89 | 83 | 0 | 0 | 0 |
| G | gepa | officeqa | S3 | 172 | 5 | 167 | 0 | 0 | 78 | 94 | 0 | 0 | 0 |
| G | gepa | officeqa | S4 | 172 | 3 | 169 | 0 | 0 | 89 | 83 | 0 | 0 | 0 |
| G | gepa | officeqa | S5 | 172 | 1 | 171 | 0 | 0 | 84 | 88 | 0 | 0 | 0 |
| D | skillopt | searchqa | C | 400 | 1 | 399 | 0 | 0 | 328 | 72 | 0 | 0 | 0 |
| D | skillopt | searchqa | B | 400 | 1 | 399 | 0 | 0 | 261 | 139 | 0 | 0 | 0 |
| D | skillopt | searchqa | C_end | 400 | 2 | 398 | 0 | 0 | 325 | 75 | 0 | 0 | 0 |
| D | skillopt | searchqa | S1 | 400 | 1 | 399 | 0 | 0 | 258 | 142 | 0 | 0 | 0 |
| D | skillopt | searchqa | S2 | 400 | 1 | 399 | 0 | 0 | 261 | 139 | 0 | 0 | 0 |
| D | skillopt | searchqa | S3 | 400 | 265 | 135 | 0 | 0 | 75 | 325 | 0 | 0 | 0 |
| D | skillopt | searchqa | S4 | 400 | 267 | 133 | 0 | 0 | 75 | 325 | 0 | 0 | 0 |
| D | skillopt | searchqa | S5 | 400 | 259 | 141 | 0 | 0 | 81 | 319 | 0 | 0 | 0 |
| D | skillopt | officeqa | C | 172 | 1 | 171 | 0 | 0 | 48 | 124 | 0 | 0 | 0 |
| D | skillopt | officeqa | B | 172 | 0 | 172 | 0 | 0 | 25 | 147 | 0 | 0 | 0 |
| D | skillopt | officeqa | C_end | 172 | 0 | 172 | 0 | 0 | 50 | 122 | 0 | 0 | 0 |
| D | skillopt | officeqa | S1 | 172 | 1 | 171 | 0 | 0 | 28 | 144 | 0 | 0 | 0 |
| D | skillopt | officeqa | S2 | 172 | 0 | 172 | 0 | 0 | 26 | 146 | 0 | 0 | 0 |
| D | skillopt | officeqa | S3 | 172 | 126 | 46 | 0 | 0 | 11 | 161 | 0 | 0 | 0 |
| D | skillopt | officeqa | S4 | 172 | 129 | 43 | 0 | 0 | 10 | 162 | 0 | 0 | 0 |
| D | skillopt | officeqa | S5 | 172 | 129 | 43 | 0 | 0 | 10 | 162 | 0 | 0 | 0 |
| D | gepa | searchqa | C | 400 | 1 | 399 | 0 | 0 | 328 | 72 | 0 | 0 | 0 |
| D | gepa | searchqa | B | 400 | 1 | 399 | 0 | 0 | 261 | 139 | 0 | 0 | 0 |
| D | gepa | searchqa | C_end | 400 | 2 | 398 | 0 | 0 | 325 | 75 | 0 | 0 | 0 |
| D | gepa | searchqa | S1 | 400 | 1 | 399 | 0 | 0 | 335 | 65 | 0 | 0 | 0 |
| D | gepa | searchqa | S2 | 400 | 1 | 399 | 0 | 0 | 332 | 68 | 0 | 0 | 0 |
| D | gepa | searchqa | S3 | 400 | 2 | 398 | 0 | 0 | 332 | 68 | 0 | 0 | 0 |
| D | gepa | searchqa | S4 | 400 | 2 | 398 | 0 | 0 | 335 | 65 | 0 | 0 | 0 |
| D | gepa | searchqa | S5 | 400 | 1 | 399 | 0 | 0 | 331 | 69 | 0 | 0 | 0 |
| D | gepa | officeqa | C | 172 | 1 | 171 | 0 | 0 | 48 | 124 | 0 | 0 | 0 |
| D | gepa | officeqa | B | 172 | 0 | 172 | 0 | 0 | 25 | 147 | 0 | 0 | 0 |
| D | gepa | officeqa | C_end | 172 | 0 | 172 | 0 | 0 | 50 | 122 | 0 | 0 | 0 |
| D | gepa | officeqa | S1 | 172 | 3 | 169 | 0 | 0 | 45 | 127 | 0 | 0 | 0 |
| D | gepa | officeqa | S2 | 172 | 1 | 171 | 0 | 0 | 48 | 124 | 0 | 0 | 0 |
| D | gepa | officeqa | S3 | 172 | 2 | 170 | 0 | 0 | 42 | 130 | 0 | 0 | 0 |
| D | gepa | officeqa | S4 | 172 | 3 | 169 | 0 | 0 | 46 | 126 | 0 | 0 | 0 |
| D | gepa | officeqa | S5 | 172 | 4 | 168 | 0 | 0 | 47 | 125 | 0 | 0 | 0 |

The JSON report also contains the full carrier × verdict cross-tabulation.

**Registered references**

| Bench | Arm | n | Side | Accuracy |
|---|---|---:|---|---:|
| searchqa | C | 400 | H | 0.82 |
| searchqa | B | 400 | H | 0.6525 |
| searchqa | S2 | 400 | L | 0.6525 |
| searchqa | S3 | 400 | L | 0.1875 |
| searchqa | S4 | 400 | L | 0.1875 |
| searchqa | S5 | 400 | L | 0.2025 |
| searchqa | C_end | 400 | H | 0.8125 |
| officeqa | C | 172 | H | 0.27906976744186046 |
| officeqa | B | 172 | H | 0.14534883720930233 |
| officeqa | S2 | 172 | L | 0.1511627906976744 |
| officeqa | S3 | 172 | L | 0.06395348837209303 |
| officeqa | S4 | 172 | L | 0.05813953488372093 |
| officeqa | S5 | 172 | L | 0.05813953488372093 |
| officeqa | C_end | 172 | H | 0.29069767441860467 |

**searchqa / S3'**

| Scoring | n | Correct | Accuracy |
|---|---:|---:|---:|
| primary | 400 | 72 | 0.18 |
| tolerant | 400 | 250 | 0.625 |

Counts cover all sent cells, including cells outside the registered comparison mask.

```json
{
  "calls": {
    "selected": 400,
    "sent": 400,
    "failed": 1,
    "unsent": 0
  },
  "carriers": {
    "none": 271,
    "official": 129,
    "json": 0,
    "other": 0
  },
  "format_counts": {
    "primary_carrier_none": 271,
    "learned_json_format": 270,
    "candidate_found": 216,
    "candidate_passed": 178
  },
  "usage": {
    "prompt_tokens": 780779,
    "completion_tokens": 30589,
    "total_tokens": 811368
  },
  "registered_mask_n": 400,
  "sent_outside_registered_mask": 0
}
```

| Comparison | Scoring | Pair rule | n | Mean | 95% CI | Better / worse / tied |
|---|---|---|---:|---:|---|---|
| S3'-C | primary | registered_pair_rule | 400 | -64.0 | [-68.7241343735276, -59.2758656264724] | 0 / 256 / 144 |
| S3'-C | primary | identical_requests_zero | 400 | -64.0 | [-68.7241343735276, -59.2758656264724] | 0 / 256 / 144 |
| S3'-C | tolerant | registered_pair_rule | 400 | -19.5 | [-23.9231311137209, -15.076868886279101] | 9 / 87 / 304 |
| S3'-C | tolerant | identical_requests_zero | 400 | -19.5 | [-23.9231311137209, -15.076868886279101] | 9 / 87 / 304 |
| S3'-B | primary | registered_pair_rule | 400 | -47.25 | [-52.16352469635568, -42.33647530364431] | 0 / 189 / 211 |
| S3'-B | primary | identical_requests_zero | 400 | -47.25 | [-52.16352469635568, -42.33647530364431] | 0 / 189 / 211 |
| S3'-B | tolerant | registered_pair_rule | 400 | -2.75 | [-6.708172879638215, 1.2081728796382152] | 27 / 38 / 335 |
| S3'-B | tolerant | identical_requests_zero | 400 | -2.75 | [-6.708172879638215, 1.2081728796382152] | 27 / 38 / 335 |
| S3'-S2 | primary | registered_pair_rule | 400 | -47.25 | [-52.16352469635568, -42.33647530364431] | 0 / 189 / 211 |
| S3'-S2 | primary | identical_requests_zero | 400 | -47.25 | [-52.16352469635568, -42.33647530364431] | 0 / 189 / 211 |
| S3'-S2 | tolerant | registered_pair_rule | 400 | -2.75 | [-6.646512925627713, 1.1465129256277125] | 26 / 37 / 337 |
| S3'-S2 | tolerant | identical_requests_zero | 400 | -2.75 | [-6.646512925627713, 1.1465129256277125] | 26 / 37 / 337 |
| S3'-S3 | primary | registered_pair_rule | 400 | -0.75 | [-3.5759200689265747, 2.0759200689265747] | 15 / 18 / 367 |
| S3'-S3 | primary | identical_requests_zero | 400 | 0.0 | [0.0, 0.0] | 0 / 0 / 400 |
| S3'-S3 | tolerant | registered_pair_rule | 400 | 43.75 | [38.57858616928237, 48.92141383071763] | 181 / 6 / 213 |
| S3'-S3 | tolerant | identical_requests_zero | 400 | 0.0 | [0.0, 0.0] | 0 / 0 / 400 |

**officeqa / S3'**

| Scoring | n | Correct | Accuracy |
|---|---:|---:|---:|
| primary | 172 | 10 | 0.05813953488372093 |
| tolerant | 172 | 35 | 0.20348837209302326 |

Counts cover all sent cells, including cells outside the registered comparison mask.

```json
{
  "calls": {
    "selected": 172,
    "sent": 172,
    "failed": 0,
    "unsent": 0
  },
  "carriers": {
    "none": 131,
    "official": 41,
    "json": 0,
    "other": 0
  },
  "format_counts": {
    "primary_carrier_none": 131,
    "learned_json_format": 131,
    "candidate_found": 65,
    "candidate_passed": 25
  },
  "usage": {
    "prompt_tokens": 932709,
    "completion_tokens": 39721,
    "total_tokens": 972430
  },
  "registered_mask_n": 172,
  "sent_outside_registered_mask": 0
}
```

| Comparison | Scoring | Pair rule | n | Mean | 95% CI | Better / worse / tied |
|---|---|---|---:|---:|---|---|
| S3'-C | primary | registered_pair_rule | 172 | -22.093023255813954 | [-28.56139239531276, -15.624654116315146] | 1 / 39 / 132 |
| S3'-C | primary | identical_requests_zero | 172 | -22.093023255813954 | [-28.56139239531276, -15.624654116315146] | 1 / 39 / 132 |
| S3'-C | tolerant | registered_pair_rule | 172 | -7.55813953488372 | [-15.131218005291144, 0.0149389355237034] | 16 / 29 / 127 |
| S3'-C | tolerant | identical_requests_zero | 172 | -7.55813953488372 | [-15.131218005291144, 0.0149389355237034] | 16 / 29 / 127 |
| S3'-B | primary | registered_pair_rule | 172 | -8.720930232558139 | [-13.824766939898394, -3.617093525217884] | 3 / 18 / 151 |
| S3'-B | primary | identical_requests_zero | 172 | -8.720930232558139 | [-13.824766939898394, -3.617093525217884] | 3 / 18 / 151 |
| S3'-B | tolerant | registered_pair_rule | 172 | 5.813953488372093 | [-0.7754633269447537, 12.40337030368894] | 22 / 12 / 138 |
| S3'-B | tolerant | identical_requests_zero | 172 | 5.813953488372093 | [-0.7754633269447537, 12.40337030368894] | 22 / 12 / 138 |
| S3'-S2 | primary | registered_pair_rule | 172 | -9.30232558139535 | [-14.527681369754497, -4.076969793036202] | 3 / 19 / 150 |
| S3'-S2 | primary | identical_requests_zero | 172 | -9.30232558139535 | [-14.527681369754497, -4.076969793036202] | 3 / 19 / 150 |
| S3'-S2 | tolerant | registered_pair_rule | 172 | 5.232558139534884 | [-1.336838955515298, 11.801955234585066] | 21 / 12 / 139 |
| S3'-S2 | tolerant | identical_requests_zero | 172 | 5.232558139534884 | [-1.336838955515298, 11.801955234585066] | 21 / 12 / 139 |
| S3'-S3 | primary | registered_pair_rule | 172 | -0.5813953488372093 | [-2.577022830819763, 1.4142321331453445] | 1 / 2 / 169 |
| S3'-S3 | primary | identical_requests_zero | 172 | 0.0 | [0.0, 0.0] | 0 / 0 / 172 |
| S3'-S3 | tolerant | registered_pair_rule | 172 | 13.953488372093023 | [8.48469431798378, 19.422282426202266] | 25 / 1 / 146 |
| S3'-S3 | tolerant | identical_requests_zero | 172 | 0.0 | [0.0, 0.0] | 0 / 0 / 172 |

**Provenance and tolerant rule**

```json
{
  "script_sha256": "5dd984a7d5d305de327f8a15d40de02c6235a1afb30dda41f28e17a9aad8c1c4",
  "tolerant_script_sha256": "f20618b192d7845fe36d5139e08137b0e427f3a8be1c8f77c416df4807e9866d",
  "snapshot_git_head": "128187abbdd60dc0cb9657a025d2629f6db42c96",
  "snapshot": "/data/execskill-code-20261104-textskill5x5-v1",
  "module_sha256s": {
    "scripts": {
      "path": "scripts/__init__.py",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    "scripts.generate_zero_shot_skill": {
      "path": "scripts/generate_zero_shot_skill.py",
      "sha256": "393b57031fc5464dcf77ea8fe062d294ad9974e336030720d97499f27198e734"
    },
    "scripts.make_searchqa_fresh_sample": {
      "path": "scripts/make_searchqa_fresh_sample.py",
      "sha256": "8966294e3b4645d8feb10de39da7fe973ba202b8af83fed8f04bd1b482277919"
    },
    "scripts.pilot_livemath_headroom": {
      "path": "scripts/pilot_livemath_headroom.py",
      "sha256": "bb6a428daeba5477147ab4b687f0c0168f8ba7fcccd93ae6fe2ab0ab400a00ff"
    },
    "scripts.pilot_officeqa_headroom": {
      "path": "scripts/pilot_officeqa_headroom.py",
      "sha256": "c1fb57307430ab416a8349718ac18f1582107e30d860dd59aaab916ccc4861cc"
    },
    "scripts.run_fivebench_g_stage": {
      "path": "scripts/run_fivebench_g_stage.py",
      "sha256": "29b096a150987c06d55bb4628f34e3395314b63f84c91ddbe25f1c464b29ae99"
    },
    "scripts.weak_solver_probe": {
      "path": "scripts/weak_solver_probe.py",
      "sha256": "d62a002ef5d44fcd194d195bfd11486c8cdd418d251b9423398cf13a20ee00d6"
    },
    "skillopt": {
      "path": "skillopt/__init__.py",
      "sha256": "acde34f209004e93450198fbcc4cf5f161e5079c53e5e38492d934e42347995c"
    },
    "skillopt.coevo5": {
      "path": "skillopt/coevo5/__init__.py",
      "sha256": "85860a1e82580abf073851e3d99a8b2c25184b1b222d79ca0e8518c9ea4d3cb7"
    },
    "skillopt.coevo5.analyst": {
      "path": "skillopt/coevo5/analyst.py",
      "sha256": "676990b8cbf2340ce650427858937c8d03f6c56d713b6f57118f8413fb29a52d"
    },
    "skillopt.coevo5.budget": {
      "path": "skillopt/coevo5/budget.py",
      "sha256": "fe34ba79773f2b1c501eddb03a744bec77a593e86282b4bdd1abb30fb47fdf3d"
    },
    "skillopt.coevo5.calls": {
      "path": "skillopt/coevo5/calls.py",
      "sha256": "1940c0d0c920a945f0c9e6248f8e6c7017e07a2ea3f20009d71fba30b41a7019"
    },
    "skillopt.coevo5.cells": {
      "path": "skillopt/coevo5/cells.py",
      "sha256": "d304302adcba4e71bb72951b80157a09681d6599be231f681d522e7ae7f15d0e"
    },
    "skillopt.coevo5.checks": {
      "path": "skillopt/coevo5/checks.py",
      "sha256": "03e87b0c7b6060b09b2bcc6bc8e06da7fb38bc6464ecfb02195fd5ae2c0739a6"
    },
    "skillopt.coevo5.data": {
      "path": "skillopt/coevo5/data.py",
      "sha256": "f987a06b6b568acf532cae3b2115170fe26203f4dd3748e5f052b54507373bc8"
    },
    "skillopt.coevo5.evaluation": {
      "path": "skillopt/coevo5/evaluation.py",
      "sha256": "0f653d2073de2ed64cbd8fb27f7a5aca785048486788ae105e945ebc581c078b"
    },
    "skillopt.coevo5.examiner": {
      "path": "skillopt/coevo5/examiner.py",
      "sha256": "742c777d54038947df65d567ee7c1710b43ad7be00cdbe10541c1f6f958cf224"
    },
    "skillopt.coevo5.forward": {
      "path": "skillopt/coevo5/forward.py",
      "sha256": "c8b57839292494b93d9922c8fe362ee6f0438daf4891df5d1d02ef72de2af496"
    },
    "skillopt.coevo5.gate": {
      "path": "skillopt/coevo5/gate.py",
      "sha256": "19d40a6bcafbd542a650fabeb6e63323dafbf560d8167e0cd9249504fd2f1a42"
    },
    "skillopt.coevo5.leakage": {
      "path": "skillopt/coevo5/leakage.py",
      "sha256": "b50be6aeb9c0958e7d2f68ced518355408346ae191d83e98e796b33004262127"
    },
    "skillopt.coevo5.ledger": {
      "path": "skillopt/coevo5/ledger.py",
      "sha256": "9a058cb10c0b5917438dc322ec5bba137942c2edca65394a9ec0f6ecbd9a1f5b"
    },
    "skillopt.coevo5.outcomes": {
      "path": "skillopt/coevo5/outcomes.py",
      "sha256": "93285cf687aa7f465f8e94ea4a5ff87c1db33db0312d8c71b3227c9a91941742"
    },
    "skillopt.coevo5.protocol": {
      "path": "skillopt/coevo5/protocol.py",
      "sha256": "f9296d5c1d1cf75b8e07d2eecefd61e2cdf96399e2eb71af222ee68e2e547d96"
    },
    "skillopt.coevo5.qualify": {
      "path": "skillopt/coevo5/qualify.py",
      "sha256": "641f0e3af9de6d8be3cd22d3345cb8872dc3148a55f7d496ba3e0ca431630323"
    },
    "skillopt.coevo5.research": {
      "path": "skillopt/coevo5/research.py",
      "sha256": "dc3bcc25a05e0c2f13d0b9b15eb1f1ac24e0c5d2d9916fc276d2fff4c3e87a83"
    },
    "skillopt.coevo5.roles": {
      "path": "skillopt/coevo5/roles.py",
      "sha256": "1b0d19270c11f4053a447a9a45fc2bc7e1c40306f04cd58dffacbf6495db40e6"
    },
    "skillopt.coevo5.scoring": {
      "path": "skillopt/coevo5/scoring.py",
      "sha256": "188009c71ae942664412d60ad6fb5b8395dba5d97373308fc6e086ab2f85dcf3"
    },
    "skillopt.coevo5.sheetview": {
      "path": "skillopt/coevo5/sheetview.py",
      "sha256": "fb3c3e1e72344179136db9c7fe0eefc7d7ab9d0747244e5166fc85c2ac29cd33"
    },
    "skillopt.coevo5.skill": {
      "path": "skillopt/coevo5/skill.py",
      "sha256": "904493955211d764fe148a881d709902999f50250b5ed395d2073e7b75e077db"
    },
    "skillopt.coevo5.stats": {
      "path": "skillopt/coevo5/stats.py",
      "sha256": "1c9be033210574f634250d58d065cc301d9622568da39cfbdb94e987b7a18068"
    },
    "skillopt.coevo5.step": {
      "path": "skillopt/coevo5/step.py",
      "sha256": "2ab69cba4b21535fca680271751b5081dd7739c25fe4b9acd1fe78f3b64a4a7b"
    },
    "skillopt.coevo5.units": {
      "path": "skillopt/coevo5/units.py",
      "sha256": "8854141177410eb04496800d0f321e181af20a37fd098e96080e7c964c82c34a"
    },
    "skillopt.coevolution_v5": {
      "path": "skillopt/coevolution_v5/__init__.py",
      "sha256": "ce3ef7c72a8c3fab332a1853739fc86881bf78162262df51388334ef0fc10fb2"
    },
    "skillopt.coevolution_v5.core": {
      "path": "skillopt/coevolution_v5/core.py",
      "sha256": "6883f4374c141f6670bd05a08d3571f1bf8cec981391d8ad7499811929fa9acc"
    },
    "skillopt.continual_eval": {
      "path": "skillopt/continual_eval/__init__.py",
      "sha256": "80a3ef022ded22bc4748b36498ad438f50fd11f92a5ed559fc3123e76618aea6"
    },
    "skillopt.continual_eval.backends": {
      "path": "skillopt/continual_eval/backends.py",
      "sha256": "1ee2718f46655f5e5b49d3ba5758f3503b2cac480b422f6ea0d0b820eba25def"
    },
    "skillopt.continual_eval.code_delivery": {
      "path": "skillopt/continual_eval/code_delivery.py",
      "sha256": "3d03eb0d4567316c499e5c6a692c4469df93a11d9277162447ff88660919a187"
    },
    "skillopt.continual_eval.core": {
      "path": "skillopt/continual_eval/core.py",
      "sha256": "73b8580f1fb08ab391b9c5ff50542fe0386ada6407861cef6a0b4c0f341ff0ba"
    },
    "skillopt.continual_eval.datasets": {
      "path": "skillopt/continual_eval/datasets.py",
      "sha256": "1d502146905511495364f7b98870d02b396eafb1dfe9fc9c9bf11cfa369c9262"
    },
    "skillopt.continual_eval.sheet_numeric_adapter": {
      "path": "skillopt/continual_eval/sheet_numeric_adapter.py",
      "sha256": "6e87f44e4fd5dc89caa5e98399e1d01239fb0293fef3a326cdab5f4c3a3c08af"
    },
    "skillopt.continual_eval.sheet_recalc": {
      "path": "skillopt/continual_eval/sheet_recalc.py",
      "sha256": "ae9bd26cda8e220240538cde96713c6809bab6286301993f88505b6e02cae35b"
    },
    "skillopt.continual_eval.sheet_recalc_adapter": {
      "path": "skillopt/continual_eval/sheet_recalc_adapter.py",
      "sha256": "de94d5848051d08d475ba80ced8dffb551b6ce142ba0b489f73459a6da91716f"
    },
    "skillopt.continual_eval.sheet_recalc_v6": {
      "path": "skillopt/continual_eval/sheet_recalc_v6.py",
      "sha256": "9440f1279dc781c5424809708798238e5d4c7e6430211fb94dd2e578816dfa99"
    },
    "skillopt.continual_eval.sheet_recalc_v7": {
      "path": "skillopt/continual_eval/sheet_recalc_v7.py",
      "sha256": "717bfb2e3363cf79ee803bff93746c47b262f2d6831839afd56d2f5558ae523d"
    },
    "skillopt.continual_eval.spreadsheet_compat": {
      "path": "skillopt/continual_eval/spreadsheet_compat.py",
      "sha256": "4b81345fa88eed55172ffb5d3f801804dff0067fbfe0e45d1fa4985b39370a47"
    },
    "skillopt.continual_learning": {
      "path": "skillopt/continual_learning/__init__.py",
      "sha256": "0290aa82f0306d24be8f1b505c948d3c739be0a3fdec282e2c7428c873535149"
    },
    "skillopt.continual_learning.ledger": {
      "path": "skillopt/continual_learning/ledger.py",
      "sha256": "f78b3457225d078bcb9b7280eac61f982918a7aaa9935ad65756638f00b40e57"
    },
    "skillopt.datasets": {
      "path": "skillopt/datasets/__init__.py",
      "sha256": "39a907e5207f3daa2477a4b3f9b01395fbadd43918f22ecdb8d4c132958467e7"
    },
    "skillopt.datasets.base": {
      "path": "skillopt/datasets/base.py",
      "sha256": "82a68f80271fadb4947f49b81a27cf03af08af61ed85d5326381a7955d0da48b"
    },
    "skillopt.envs": {
      "path": "skillopt/envs/__init__.py",
      "sha256": "a3e66f90175f614a239a4f1264569cefdc6f8c7c62f4204986119d9c8f605621"
    },
    "skillopt.envs.officeqa": {
      "path": "skillopt/envs/officeqa/__init__.py",
      "sha256": "78a588eb690f26cd9e2bdeb6eac88ca5848c75a3758af073a777f020902b0f01"
    },
    "skillopt.envs.officeqa.evaluator": {
      "path": "skillopt/envs/officeqa/evaluator.py",
      "sha256": "49dad2a2bdede9665541102fe47ca74ab2a0cc05ad84d2f8ca047f223c1b4aef"
    },
    "skillopt.envs.officeqa.tool_runtime": {
      "path": "skillopt/envs/officeqa/tool_runtime.py",
      "sha256": "c94510816a4e8afdb1b1abd6c65a800d294f9c4b7bf2eb966f831b502227a4f4"
    },
    "skillopt.envs.searchqa": {
      "path": "skillopt/envs/searchqa/__init__.py",
      "sha256": "3874a40b6adfb028a32a8aa3a54604b1586032131a30cf53271e3cf0b2ece2fc"
    },
    "skillopt.envs.searchqa.evaluator": {
      "path": "skillopt/envs/searchqa/evaluator.py",
      "sha256": "b69136fa727fedeede7ab257144f4dc937877bd1792f13c5c596d566df66fbd3"
    },
    "skillopt.evaluation": {
      "path": "skillopt/evaluation/__init__.py",
      "sha256": "1d34dd85f77152bca307443ec0ad4609cdc0f8fb0d68638d1e1235d2e5bbc854"
    },
    "skillopt.evaluation.gate": {
      "path": "skillopt/evaluation/gate.py",
      "sha256": "3c2405f13288e97f53afa0bdfc0752ba6917c51edd1904a810deb4b5a1a81bef"
    },
    "skillopt.execskill": {
      "path": "skillopt/execskill/__init__.py",
      "sha256": "73af70f49d27d63cb88660193a4ce1f8eb0a432bf81ea9fe9e9e1ed488a4b2de"
    },
    "skillopt.execskill.acceptance": {
      "path": "skillopt/execskill/acceptance.py",
      "sha256": "e5db8c0f38bacb4f892fb125a5359436b582058de098953e7cadbe5972c3485a"
    },
    "skillopt.execskill.alfworld_format": {
      "path": "skillopt/execskill/alfworld_format.py",
      "sha256": "64182c2d9d86c0979645426c83427cdb378b4019e31c109c10492be13a58cf4f"
    },
    "skillopt.execskill.budgets": {
      "path": "skillopt/execskill/budgets.py",
      "sha256": "93fc65c99c01adf6806a6ce000649dedb4f9fc245cf536889aa5377369d5df15"
    },
    "skillopt.execskill.canonical": {
      "path": "skillopt/execskill/canonical.py",
      "sha256": "cec39c6c834fd37fc4e6a80fded1f2f5e4df52d5e379984c60ba2bb97da64a74"
    },
    "skillopt.execskill.cells": {
      "path": "skillopt/execskill/cells.py",
      "sha256": "a87131917d787f2444d22ee54c3423dfcec5f70b299bd98769a57188cd622b12"
    },
    "skillopt.execskill.chain": {
      "path": "skillopt/execskill/chain.py",
      "sha256": "c5452e914f3add1ed5f20b3ed6f7c815ba455c1066cfa06531378424ec375fa0"
    },
    "skillopt.execskill.client": {
      "path": "skillopt/execskill/client.py",
      "sha256": "cac82a0bf6bbb387b970340f4bd0b09752dec0701015a732028f1ab87156e3f6"
    },
    "skillopt.execskill.code_delivery": {
      "path": "skillopt/execskill/code_delivery.py",
      "sha256": "ebe5f4208425e4cf8c7864023ec7f62426c6a883ba07603b9c1ded70c0fc3ede"
    },
    "skillopt.execskill.compute": {
      "path": "skillopt/execskill/compute.py",
      "sha256": "1dc7a7ea2d35aa5f0313dac45bc12c900bdf17c988e9090456aeb6b5dc373efa"
    },
    "skillopt.execskill.confirm": {
      "path": "skillopt/execskill/confirm.py",
      "sha256": "ac4716941957ce9765fb78230bfda510de7875498bf7781d481c4574e9585aae"
    },
    "skillopt.execskill.corpus": {
      "path": "skillopt/execskill/corpus.py",
      "sha256": "1839669772996a44fba5ce629b029236991d354419952ace118f5076fd4c35ee"
    },
    "skillopt.execskill.describer": {
      "path": "skillopt/execskill/describer.py",
      "sha256": "59369cd25ee5970d3c49e82f309441dbcfe7f8b1f6a482c18a00adb850ec25cb"
    },
    "skillopt.execskill.detectors": {
      "path": "skillopt/execskill/detectors.py",
      "sha256": "3e3f646195d7877c8719d862ed5f93aecc74ab3eeaadc319422396eb7764f88f"
    },
    "skillopt.execskill.diagnostics": {
      "path": "skillopt/execskill/diagnostics.py",
      "sha256": "8927a14aca7da04e22f5fab26d6d2a4616b50b52084abce6ccc3ba311a7bbbae"
    },
    "skillopt.execskill.diagnostics_runtime": {
      "path": "skillopt/execskill/diagnostics_runtime.py",
      "sha256": "4e15bb82713e5142316cab1ac1bb66deccdbd8455c96f5abfd64940e226ea105"
    },
    "skillopt.execskill.donors": {
      "path": "skillopt/execskill/donors.py",
      "sha256": "bfb6a8da8a49e37694d64bb6a18a263f7fc2c874b6a1a84174ebb1ca9666d88c"
    },
    "skillopt.execskill.engineer": {
      "path": "skillopt/execskill/engineer.py",
      "sha256": "2f8f0401a763a5ff3e34fd95612dd4dbce444b579268c09b074c26a72ac03b0c"
    },
    "skillopt.execskill.engineer_payload": {
      "path": "skillopt/execskill/engineer_payload.py",
      "sha256": "c89303b58da63a2bba0e90e14054ed9665de33e676a14790f0c47d37ce93e874"
    },
    "skillopt.execskill.engineer_reader": {
      "path": "skillopt/execskill/engineer_reader.py",
      "sha256": "5ddd70bf8febe3db575a0c6b184a95c94a7eca013c0e924d129f0764e0ced6f6"
    },
    "skillopt.execskill.engineer_v28": {
      "path": "skillopt/execskill/engineer_v28.py",
      "sha256": "6b79737926973925b5d6b125e96d80f8b59a1a8811fc59808233d1529dedf873"
    },
    "skillopt.execskill.engines": {
      "path": "skillopt/execskill/engines.py",
      "sha256": "87533d8366e0444c751f516b1b4b97c5ebb4fe81015776e9d1910719ea607664"
    },
    "skillopt.execskill.errors": {
      "path": "skillopt/execskill/errors.py",
      "sha256": "91262ff4154c70cb4ebb48addd96fe0c03a3141fcbc73d61b8cdc69be51cfb00"
    },
    "skillopt.execskill.evaluation": {
      "path": "skillopt/execskill/evaluation.py",
      "sha256": "3b055e165f7af0872cedd089ac2cc6ec172b7b730d88a9fe8ebfaddc73ba61f7"
    },
    "skillopt.execskill.examiner": {
      "path": "skillopt/execskill/examiner.py",
      "sha256": "56f84c64834ea047d5f722f7f3cadb213d1fd8d3600269cf9a5917838c7f73c2"
    },
    "skillopt.execskill.exclusion": {
      "path": "skillopt/execskill/exclusion.py",
      "sha256": "a115172b81d8997c70d276a6db1c5279c441e4ffbb262daed367833e4141c15b"
    },
    "skillopt.execskill.generators": {
      "path": "skillopt/execskill/generators/__init__.py",
      "sha256": "5dd75172ad59ba140f2e5cbf49fad54daf633002a9288449d9485795b8343b60"
    },
    "skillopt.execskill.generators.alfworld_select": {
      "path": "skillopt/execskill/generators/alfworld_select.py",
      "sha256": "f808f3d2ff40b5f7f9dbda3d2e7b2ba5128a949ef7868e91b359cb924c559ada"
    },
    "skillopt.execskill.generators.families": {
      "path": "skillopt/execskill/generators/families.py",
      "sha256": "c0e907efd7cd4ad6792f5b76dcf145cd3730e52524c21fcd9fec112b690792ff"
    },
    "skillopt.execskill.generators.livemath": {
      "path": "skillopt/execskill/generators/livemath.py",
      "sha256": "8a0933dd41885529375e1e4458ba7b31fcee6304b83d4b351c64c35c94d3d382"
    },
    "skillopt.execskill.generators.officeqa": {
      "path": "skillopt/execskill/generators/officeqa.py",
      "sha256": "21e081abdba6e8f82febb0809959f75dd96c5dd874167c7c1e541fb2123d00de"
    },
    "skillopt.execskill.generators.sheet": {
      "path": "skillopt/execskill/generators/sheet.py",
      "sha256": "cf05f46da43839ee4bf3cebc4f85ba97116ca255b2426c1d854d00adb3d21ef8"
    },
    "skillopt.execskill.instruction_start": {
      "path": "skillopt/execskill/instruction_start.py",
      "sha256": "18a3280207027160ce0b4c13d8d66a40cac04f2738eee1ec4af28d47f4d008b3"
    },
    "skillopt.execskill.judge": {
      "path": "skillopt/execskill/judge.py",
      "sha256": "53227857d47a32d0ac32f4bc5a3a6ac19bd333eca57219f34c6096bed441f995"
    },
    "skillopt.execskill.manifest": {
      "path": "skillopt/execskill/manifest.py",
      "sha256": "1e1ca5a8153254e48069d9e0ae9a4cab03ecbe39ad59261488b0ded905832697"
    },
    "skillopt.execskill.membase": {
      "path": "skillopt/execskill/membase/__init__.py",
      "sha256": "7b618702a5d7bee492c7e21fdf4bb1d43cf7591074c30d5af70100f83583d0ad"
    },
    "skillopt.execskill.membase.arms": {
      "path": "skillopt/execskill/membase/arms.py",
      "sha256": "a53d20529ebd14de8604e380de6c25c42d2c66d5b370553e005cd139ca998de2"
    },
    "skillopt.execskill.membase.limits": {
      "path": "skillopt/execskill/membase/limits.py",
      "sha256": "50a2d3202fcbe574c22e9d3ca4f527e3590fa9f9a37f2cab1c090f45320b4a45"
    },
    "skillopt.execskill.notes": {
      "path": "skillopt/execskill/notes.py",
      "sha256": "0e5d059925155980bf2169d5dec7558e8eb69630a773029986c1e399a8894aee"
    },
    "skillopt.execskill.outcomes_ext": {
      "path": "skillopt/execskill/outcomes_ext.py",
      "sha256": "e2ce7dd21d6242a90d3ae7efac03771b73c941f317dde863600222eb19f001a6"
    },
    "skillopt.execskill.package": {
      "path": "skillopt/execskill/package.py",
      "sha256": "32ff7fc46a05c0f16ca6afa82cfa945b5448b544a79eee5306d7694792228db4"
    },
    "skillopt.execskill.placebo": {
      "path": "skillopt/execskill/placebo.py",
      "sha256": "a521f7011666123ac1f23c0dc16da17c24f8a22907b5c38b0b649142b39a501b"
    },
    "skillopt.execskill.policy": {
      "path": "skillopt/execskill/policy.py",
      "sha256": "60e7fa27163cfb2b2691663768bed4d4dbdead3810e1d12624d1fe37e5c66438"
    },
    "skillopt.execskill.precheck": {
      "path": "skillopt/execskill/precheck.py",
      "sha256": "a18d1676d7f3d1bf0fcef45c4016e6ff2c20a418f460537d0f54430123e4d022"
    },
    "skillopt.execskill.prelaunch": {
      "path": "skillopt/execskill/prelaunch.py",
      "sha256": "5658891d71ff304cd8cb132f7ba9a9392e87b09a644494d87f78e1d6dcb3fd26"
    },
    "skillopt.execskill.profiles": {
      "path": "skillopt/execskill/profiles.py",
      "sha256": "1cb59fa3835c4a839dbacf93d6526732b500a4a3029dfb2dbb857c0e44ba4c90"
    },
    "skillopt.execskill.protocol": {
      "path": "skillopt/execskill/protocol.py",
      "sha256": "fcdc2b9d4bcd311940549f68605c62fa1b2bfea8a510d196dc3d576f4d5a7221"
    },
    "skillopt.execskill.qualify": {
      "path": "skillopt/execskill/qualify.py",
      "sha256": "a36de3d2c6d3a964de4ff74fcc83407093a1c58ff27e72f02e09233113bb8c99"
    },
    "skillopt.execskill.readout": {
      "path": "skillopt/execskill/readout.py",
      "sha256": "4a072a07bec62c6742c7efdc6a2709d6dbbb923bc41e55049c870f114490db2a"
    },
    "skillopt.execskill.registry": {
      "path": "skillopt/execskill/registry.py",
      "sha256": "97991f03ff3d58d3a4a6f810f4d07e147aeb46f035b158bdff7fb89be315942b"
    },
    "skillopt.execskill.replay": {
      "path": "skillopt/execskill/replay.py",
      "sha256": "a24955de7a0fbc6fd544ef1336b59d5c942a446122fbc824f612ef7137ac58a3"
    },
    "skillopt.execskill.research": {
      "path": "skillopt/execskill/research.py",
      "sha256": "9b3d78e5fef477d09d8d94d5abc41bfe586779e09c59eb49faced38563c5a005"
    },
    "skillopt.execskill.reuse": {
      "path": "skillopt/execskill/reuse.py",
      "sha256": "9dba8e79077b481d2103bf1d63f5f7b47ff8e6cd63c9ef0c8b70b1f500f618f0"
    },
    "skillopt.execskill.rounds": {
      "path": "skillopt/execskill/rounds.py",
      "sha256": "5fcfeca0d973ec1f550aa726e805c7b01d432b6e333d3ab15946e35d7b792276"
    },
    "skillopt.execskill.router": {
      "path": "skillopt/execskill/router.py",
      "sha256": "6c8b8b1d2cde18c5cedd7a9a8302f51918cea014403e366ef2c5af64fc6e3e80"
    },
    "skillopt.execskill.routes": {
      "path": "skillopt/execskill/routes.py",
      "sha256": "417ab306bf739b62becc60841ddc9245672ce75a0f5cc1ceccea7726825649d9"
    },
    "skillopt.execskill.sandbox": {
      "path": "skillopt/execskill/sandbox/__init__.py",
      "sha256": "fd6527069e74fcee2b034f220e1ca27c83aa3835eac914e4d49222f1b9c19c8c"
    },
    "skillopt.execskill.sandbox.client": {
      "path": "skillopt/execskill/sandbox/client.py",
      "sha256": "71d9344ed32fc39eb4f964fe6279ecef03825a50d4bbe857a28c5478cc696980"
    },
    "skillopt.execskill.sandbox.worker": {
      "path": "skillopt/execskill/sandbox/worker.py",
      "sha256": "bb1ccc0d90cafbda1f842569454ec676a8329d721a423246d92572632cf4ea0d"
    },
    "skillopt.execskill.slots": {
      "path": "skillopt/execskill/slots.py",
      "sha256": "e9c1cbdd12d3af1a61b09f082860bd7865bffacc03a51fed90a36435d70eb97c"
    },
    "skillopt.execskill.solver": {
      "path": "skillopt/execskill/solver.py",
      "sha256": "bdd404e7c650d6847d61482aac66d88908596f6e872a018bd25cbeb1d1a63d40"
    },
    "skillopt.execskill.stats_ext": {
      "path": "skillopt/execskill/stats_ext.py",
      "sha256": "3bb7b49f65dcdb19d55eb1abf881579e3624002487a1a0e0aada2ec1139ac2dd"
    },
    "skillopt.execskill.step": {
      "path": "skillopt/execskill/step.py",
      "sha256": "3947ca9334d29415b8d034ad7f8f4b81b3b97fad866f4d14c7dc95e7d2eb7b4a"
    },
    "skillopt.execskill.supply": {
      "path": "skillopt/execskill/supply.py",
      "sha256": "4582e8ca540b24a329c3010525092398b942cf132e2e4e7544bf37b2b9592ea1"
    },
    "skillopt.execskill.textskill": {
      "path": "skillopt/execskill/textskill/__init__.py",
      "sha256": "450c6e5da9f7c06b0c0f2d805e2b12a9a9d6ec63865b6ccd6c8076f56434c25f"
    },
    "skillopt.execskill.textskill.arms": {
      "path": "skillopt/execskill/textskill/arms.py",
      "sha256": "28f0d53e617ad709b446a0ceb4efde33436670509999681989a285ceb4a47ff4"
    },
    "skillopt.execskill.textskill.clients": {
      "path": "skillopt/execskill/textskill/clients.py",
      "sha256": "bcf4db7a4a86149c89c5ebd4426716177e75e3c7011cd7ca4c99a2a83b78186f"
    },
    "skillopt.execskill.textskill.panels": {
      "path": "skillopt/execskill/textskill/panels.py",
      "sha256": "ae9e33dd9f8e6c1894f31dc82f2773463fcbbc00a634108ec9464e23d2e6da8e"
    },
    "skillopt.execskill.textskill.read": {
      "path": "skillopt/execskill/textskill/read.py",
      "sha256": "157fedf78edc116c4749ffedda9a70e500b8d21a8edca0f5b78da328c1e50863"
    },
    "skillopt.execskill.textskill.readout": {
      "path": "skillopt/execskill/textskill/readout.py",
      "sha256": "d3b9482557226738ec95bceab502c393fb1934fd6686c9d046ba08793ff0da7f"
    },
    "skillopt.execskill.textskill.registration": {
      "path": "skillopt/execskill/textskill/registration.py",
      "sha256": "752af9d9e66389ded92d04e952dc32a4aab424cdc1904d8cdd9196589e3fee17"
    },
    "skillopt.execskill.trajectories": {
      "path": "skillopt/execskill/trajectories.py",
      "sha256": "4cf8928f972ff2e03a0bf9421a6b1dfd6c5c1abe09dbb9b7154909d0a549c7e6"
    },
    "skillopt.execskill.units": {
      "path": "skillopt/execskill/units.py",
      "sha256": "af9ee087898388ef783f9f0f037065bdd5b18b37a23994c804382fad74a91601"
    },
    "skillopt.execskill.v211_limits": {
      "path": "skillopt/execskill/v211_limits.py",
      "sha256": "af0f750e73012644c62621895df89969bc9ee29d6ef3a9a4aac3007aefd319e9"
    },
    "skillopt.execskill.v218_limits": {
      "path": "skillopt/execskill/v218_limits.py",
      "sha256": "85825c83967af8cc3ed29928a5ae2b7a80a3b56aadce49859732d49eb173c7f9"
    },
    "skillopt.execskill.v218_read": {
      "path": "skillopt/execskill/v218_read.py",
      "sha256": "9c295ce24c6c97ce23a453b0fac9b8327ab417c86aecf83c42c94fe908ee9dfe"
    },
    "skillopt.execskill.v221_limits": {
      "path": "skillopt/execskill/v221_limits.py",
      "sha256": "3af4ee9ea8e4c9c95878a60823b3abb9dabe218aefae5cc9ce5a8cea28f1b0a1"
    },
    "skillopt.execskill.v222_limits": {
      "path": "skillopt/execskill/v222_limits.py",
      "sha256": "3d10487fd0a6746ea0ef139b4bde51e910ecda66c39205d471efc3018273b11e"
    },
    "skillopt.execskill.v29_limits": {
      "path": "skillopt/execskill/v29_limits.py",
      "sha256": "c528eadc13ae11b7998a0aa7040a4f277c8cc4a37a5acf7f36b31449f3a99c65"
    },
    "skillopt.execskill.validity": {
      "path": "skillopt/execskill/validity.py",
      "sha256": "0dc9ee46a07c53404eb97524993fc9d72c3dd5aed90abcfff2c974728e7b4ccc"
    },
    "skillopt.execskill.zebralogic": {
      "path": "skillopt/execskill/zebralogic.py",
      "sha256": "c48dc9e78c138138121c76bde76ff287ffdcea6d1f84cf95fe7ed54b0469e8b6"
    },
    "skillopt.skill_validation": {
      "path": "skillopt/skill_validation/__init__.py",
      "sha256": "92ee469aff62784f6dd1c49b7c3e829872704a3a728c6563519f320654bd85bc"
    },
    "skillopt.skill_validation.models": {
      "path": "skillopt/skill_validation/models.py",
      "sha256": "ebe0729d642d96c2e910d2bf2d2b277c34608d30d19162e17c522b1c8930b679"
    },
    "skillopt.skill_validation.sandbox": {
      "path": "skillopt/skill_validation/sandbox.py",
      "sha256": "8a88a3a5664ac305d8ae499955462d202304dd38ba7b27f105bb4728da6502ce"
    },
    "skillopt.types": {
      "path": "skillopt/types.py",
      "sha256": "f8f425c44f352255dd36a5bd6438ae0aafbc671d5e84af349ccb32c9674fddfa"
    },
    "skillopt.validator_pilot": {
      "path": "skillopt/validator_pilot/__init__.py",
      "sha256": "b8d6d377466b8441ffd0432b5febe57a756dcd50d37a21de218978b8f86b899e"
    },
    "skillopt.validator_pilot.api": {
      "path": "skillopt/validator_pilot/api.py",
      "sha256": "ceab4635cd771a784a606add566e2ec0ebc25a2a1454d16a428cffd023b94cf4"
    }
  },
  "run_root": "/data/execskill-20261104-textskill5x5-v1",
  "manifest_sha256": "02d351e99d45c970d63a656b350497d6ba5a5ba35cefea11c0131822035ecc79",
  "readout_sha256s": {
    "skillopt": "6997ae5e6b7440b0656b707ca745664cd2ec355d948b6bd82dac1edbd62728e8",
    "gepa": "0673961bbd432bc1ff2a67c9858cd7b7c260bea345bce148a677616b11dc4383"
  },
  "runtime": {
    "model": "deepseek-v4-flash",
    "route": "B",
    "temperature": 0,
    "reasoning_effort": "none",
    "max_tokens": {
      "searchqa": 8192,
      "officeqa": 8192
    },
    "timeouts_seconds": {
      "read": {
        "searchqa": 600,
        "officeqa": 600
      },
      "connect": 20,
      "write": 30,
      "pool": 30
    },
    "trust_env": false,
    "follow_redirects": false,
    "client": "skillopt.execskill.client.NorthgateClient",
    "factory": "skillopt.execskill.manifest.solver_config -> skillopt.execskill.client.solver_client",
    "credential_mechanism": "frozen _credentials reads clients.solver.D.env_path; NORTHGATE_CHAT_URL, NORTHGATE_API_KEY",
    "http_attempts_per_client_call_max": 4,
    "http_backoff_seconds": [
      10,
      30,
      60
    ],
    "http_429_backoff_seconds": [
      30,
      90,
      180
    ],
    "delivery_resends_max": 2,
    "delivery_resend_cooldown_seconds": 300
  },
  "generated_at": "2026-11-08T16:35:54+08:00",
  "tolerant_rule": "PRIMARY is the recomputed frozen registered v2 verdict, with the registered item mask and scoring side.\nTOLERANT equals PRIMARY except for a delivered primary-fail reply with primary carrier 'none'.\nScan left to right using judge.json_answer decoder conventions, treating an object nested in another as part\nof that object and scanning Markdown fences as ordinary text. Use only the LAST top-level JSON object with\na case-sensitive 'solution' key; an unusable last value never falls back to an earlier object.\nNumbers retain their original lexical text but remain distinguishable from strings and are not candidates.\nA non-blank string solution is the candidate. For an object solution: first use the first non-blank string\nvalue, in JSON key order, whose key lower-cases to 'answer' or 'final_answer'; otherwise use its sole value\nif it has exactly one key with a non-blank string value; otherwise, if it has exactly one key with an object\nvalue that itself has exactly one non-blank string value, use that inner string. Other shapes,\nlists, numbers, booleans, nulls and blank strings yield no candidate. Judge at most one candidate with\njudge._passes and the original QA runtime. Correct PRIMARY cells are never re-judged by the tolerant path;\nunknown cells retain their token and scoring side. Only primary-fail cells can become pass."
}
```
