# Cross-Domain Safe Skill Evolution MVP

This opt-in research harness extends SkillOpt's **candidate-generation machinery**,
not its existing benchmark trainer. Original SearchQA configs/results are unchanged.

## Scope and implemented components

1. **Hard-oracle diagnostic tasks** (`skillopt/cross_domain/tasks.py`): coding-state
   reasoning, spreadsheet-state reasoning, and rule/evidence reasoning. These are
   controlled synthetic, single-turn JSON tasks, **not public benchmarks, actual
   repository repair, or interactive spreadsheet editing**. Model code is never
   executed. Two hypothesized mechanisms (constraint preservation and evidence
   verification), corresponding near-misses, and unrelated controls are balanced.
2. **Local candidate evolution** (`evolution.py`): real GPT calls through the
   original SkillOpt minibatch success/failure analysts, aggregation, ranking and
   bounded patch application. Two edit rounds per mechanism, local dev gate,
   rejected-edit context, and resumable artifacts. This is not the original
   four-epoch/slow-meta training schedule. No-op candidates remain in history but
   are excluded from forced-injection intervention selection.
3. **Scope hypotheses and routing** (`policies.py`): propose observable prerequisites
   and exclusions without changing candidate content. GPT routes from task input
   and scope descriptions only. Generator mechanism/group labels and gold are
   inaccessible to the router. Domain and shuffled-group comparators share all
   candidate and rollout data. Unknown groups fall back before skill injection.
4. **Cross-domain gate** (`gate.py`): paired Base/Current/Candidate outcomes,
   local/cross-domain/protected cells, improvement checks, noninferiority and
   conditional regression checks. Returns local commit, cross-domain commit,
   restrict, reject or pending. Restriction requests **revalidation** of the
   actual restricted router, including misrouted non-source tasks.
5. **Evidence and experiment reporting** (`experiment.py`, `runtime.py`): independent
   scope-fit/confirmation partitions, frozen policies before test, counterexample
   files, input-only routing masks recorded before test outcomes, caching and
   task-clustered bootstrap summaries.

There is no automatic Split, DeepResearch/Rubric validator, learned model weights,
multi-skill composition, or claim of universal OOD safety in this MVP.

## Fixed experiment protocol

Configuration: `configs/cross_domain/mvp.json`.

| Partition | Domains | Items | Use |
|---|---|---:|---|
| Train | Coding | 40 | Source rollouts; mechanism-positive subsets drive reflection |
| Dev | Coding | 40 | Source candidate/current selection; no cross-domain exposure |
| Validation fit | Coding, Spreadsheet | 320 | Learn allowed groups from paired gains |
| Validation confirmation | Coding, Spreadsheet | 320 | Independently screen the fixed proposed policy |
| Test | Coding, Spreadsheet, Rule reasoning | 360 | Frozen-policy evaluation, two generation repeats |

Rule reasoning is an entirely held-out *domain rendering*. Each split has a distinct
structural template family, but the three domains intentionally share mechanisms and
some underlying computational structures. This does **not** establish transfer to
arbitrary real-world domains. Labels remain hypotheses specified by the task designer.

Before any task-model result, generator review removed fixed correct-document IDs
and disjoint valid/invalid revision ranges. At least one inapplicable higher revision
remains intentionally present as a noisy-evidence challenge. Later generator changes
require a different output directory and manifest.

The provider is the already configured Freerouter `gpt-5.5`. The compatible backend
does not forward reasoning effort or a generation seed. Temperature uses the service
default; target output budget is 3,000 tokens (provider cap 8,000); workers=6. Two
generation repeats share a **single training seed**, so they are not two training runs.
The runner clears only its own process proxy environment and never changes Clash.

## Contrasts and interpretations

### H1: Does scope control reduce negative transfer while preserving gains?

- `no_skill`: no learned skill.
- `unconditional`: inject the same nonempty candidate on every task, regardless of
  whether the source gate accepted it; this is an intervention diagnostic.
- `source_gate`: if the source-only dev point gate accepts, naively deploy globally;
  otherwise fallback. It is **not** a source-domain-only router.
- `safe_mechanism`: input-only mechanism scope proposal, cross-domain confirmation
  gate, revalidated local restriction or fallback.

`Current` is the recorded parent of the candidate, not the selected candidate itself.
When no local step is accepted, Current equals Base; the three-arm design then has
only two distinct target prompts. Report this degeneracy rather than hiding it.

### H2: Is mechanism grouping better than domain or shuffled grouping?

The three scope proposals use identical fit data and the same point-gain admission
rule; all undergo the same held-out confirmation gate. Mechanism groups are inferred
applicability match/nonmatch; domain groups use predicted domain; shuffled groups
permute applicability labels within predicted-domain buckets without reading outcomes.

Additionally, `matched_{10,25,50,75}_{mechanism,domain,shuffled}` diagnostics rank
task inputs and inject **exactly the same number and text length of skills**. All
four coverage levels are declared in code before testing, not selected after results.
These ungated diagnostics study routing quality and are NOT certified deployment
policies. They are batch-level ranking experiments, not fixed-threshold online routers.
The learned mechanism grouping is deliberately coarse: fit can admit either the
match or nonmatch bin when its observed gain is positive. It is not a hard logical
proof that every stated prerequisite holds. Mixed benefits and harms inside a bin
can also hide smaller useful scopes. Reserved failure/unknown bins cannot be admitted.

Both tracks are studied separately with one active candidate at a time. Do not pool
their duplicated test tasks as independent observations or claim a multi-skill agent.

## Statistical and experimental limitations

- Fit determines allowed groups; confirmation checks them; test changes neither.
  Reusing confirmation for one predeclared local restriction is recorded; no formal
  sequential/multiple-testing error control is claimed.
- Primary pilot margins: group noninferiority 10 percentage points, conditional
  regression upper bound 15%, 95% intervals. These are **loose pilot tolerances**,
  not production safety guarantees. Strict 5pp/10% results are retained separately.
- Improvement uses an exact one-sided paired sign test with an observed minimum
  effect threshold. Noninferiority uses conservative Wilson marginal-difference
  intervals; conditional harm uses Wilson intervals. Small samples can remain
  pending even when no observed errors occur. Structural fallback is different:
  the unchanged Base policy has exactly zero policy difference by construction.
- No multiplicity correction across all candidates/cells/looks, nor guarantee for
  unknown domain distributions. Near-miss regression is a noisy paired observation,
  not automatic proof of deterministic causal harm.
- Outcomes are **shared-draw offline policy replay**: after an input-only router
  commits a choice, reuse the corresponding precomputed Base/Current/Candidate
  target call. This saves cost and gives matched comparisons, but is not an
  independent online deployment trial. Raw requests and both target repeats remain
  available. Bootstrap resamples unique tasks, not duplicate repeats.
- API transport failures are stored separately. Confirmation aborts if necessary
  outcomes are missing. Test policy comparisons use a common complete-case set;
  missing-data counts and errors must be reported.
- If all approved policies fallback, lower regression alone does not support H1.
  If Base is at ceiling, this suite may fail to identify benefits or distinguish
  routing policies. A null/inconclusive result must not be reframed as success.
- If the source dev gate rejects the candidate, `source_gate` already equals Base.
  Beating forced injection of that rejected candidate does not establish an
  improvement over an accepted SkillOpt update. This harness's two-round source
  point gate is also not a full reproduction of the original benchmark trainer.
- Generic mechanism/near-miss labels are evaluation strata, not verified
  candidate-specific applicability ground truth. A particular skill may still be
  appropriate on some nominal near-misses, or be over-specific on nominal positives.
- Counterexamples from confirmation are saved for future evolution. This run does
  not feed confirmation or test failures back into candidate content, so it does
  not yet measure long-horizon continual recovery from counterexamples.

## Running and resuming

Use the existing `skill` conda environment. `python-dotenv` is additionally used
to read local `.env`; it is already installed in the run environment. A fresh
environment can install this experiment with `pip install -e '.[cross-domain]'`. No credential
is accepted in command arguments or written to generated reports. Do not commit
`.env` or API request headers.

```bash
conda run --no-capture-output -n skill python -u scripts/cross_domain_mvp.py --phase pilot
conda run --no-capture-output -n skill python -u scripts/cross_domain_mvp.py --phase train
conda run --no-capture-output -n skill python -u scripts/cross_domain_mvp.py --phase validate
conda run --no-capture-output -n skill python -u scripts/cross_domain_mvp.py --phase test
```

`--phase all` runs all four stages. Cached successful or terminal-failed requests
are not silently regenerated. Use a new `--out` directory for a changed protocol,
model, generator or independent experiment. After validation, source and policy
hashes prevent silent changes before final testing.

After testing, run the fixed H1/H2 direct paired comparisons (all four coverage
levels and domain strata, not a selected winner):

```bash
conda run -n skill python scripts/analyze_cross_domain_mvp.py --report
```

This offline command performs no API calls; by default it only prints JSON.
`--report` additionally writes `cross_domain_analysis.json` in the run directory.
`analysis_plan_before_test.json` records the analysis script hash and comparison
plan before test access, separately from the core policy freeze.

### Shape-ambiguity sensitivity in this first run

During validation, independent prompt-based recomputation confirmed all 640 gold
values, but exposed under-specified nesting in the unrelated-control prompt.
Numerically correct flattened arrays can fail strict nested-array equality. The
test generator's static unrelated template contains analogous wording. Neither
the generator, primary score nor gate was changed in response.

`scripts/audit_cross_domain_shapes.py` is an explicitly **post-hoc validation-only**
audit of exact nine-difference-plus-two-summary flattenings. After validation:

```bash
conda run -n skill python scripts/audit_cross_domain_shapes.py --report
```

A separate **secondary test sensitivity was fixed before test generation/access**,
including its script hash in `analysis_plan_before_test.json`. It accepts only the
exact seven-scalar flattening of the unrelated test's five-products-plus-two-summary
gold; it repairs no numeric error or other schema failure. After testing:

```bash
conda run -n skill python scripts/analyze_cross_domain_shape_sensitivity.py --report
```

All frozen policies, coverage levels and comparison directions are retained; there
is no refitting or gate recertification. Report both metrics. Differences caused
by this ambiguity are not evidence of mechanism-level negative transfer.

Main artifacts under `outputs/cross_domain/scope_mvp_gpt55_20260907/`:
`protocol.json`, `pilot_summary.json`, `candidates.json`,
`scope_hypotheses_before_validation.json`, `frozen_policies.json`, `summary.json`,
`report.md`, plus full datasets, calls, rollouts, routes, counterexamples and
policy outcomes. Outputs and secrets remain untracked.

## Offline checks

```bash
conda run -n skill python -m pytest -q tests/test_cross_domain_tasks.py \
  tests/test_cross_domain_gate.py tests/test_cross_domain_policies.py \
  tests/test_cross_domain_experiment.py tests/test_cross_domain_end_to_end.py
```

## Implementation audit for the first run

The protocol and task generator were fixed before task-model calls. Before any
validation target outcomes were produced, an implementation correction excluded
empty/no-op candidates from forced-intervention selection. The original mistaken
selection is preserved in `candidates.noop_selection_debug.json`; its preliminary
scope/router calls remain in the cache but are not used as treatment outcomes.
Training was resumed from unchanged checkpoints. Failure-route abstention and
all-missing-result report handling were also corrected and regression-tested before
validation targets and the final code freeze. These are development corrections,
not a claim that the implementation was immutable from its first API call.
