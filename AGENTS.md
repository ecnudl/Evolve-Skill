# Research documentation maintenance

This repository has two canonical, living research documents:

- `docs/current-workflow.md`: the current workflow, each stage's inputs/outputs,
  code entry points, and what is implemented, exercised, or still pending.
- `docs/results-and-lessons.md`: a concise ledger of important experimental
  results, limitations, lessons, and links to complete archived evidence.

When implementing a relevant change to Skill initialization, task generation,
feedback, Rubric/Research, evaluation, gates, or orchestration, update the affected
workflow section in the same work. Do not just change its date. If a change has
no workflow impact, no gratuitous document rewrite is needed.

When an experiment completes or changes an important conclusion, update the
ledger with the actual denominators, necessary controls, unknowns, costs, model,
data provenance, and report/data links. Keep the ledger selective: detailed runs
belong in dated reports and result JSON, not repeated log dumps. Negative or
pending results must not be presented as positive effects.

Distinguish engineering fixtures, historical replay, real model runs, and
independent method-effect evidence. Code availability is not evidence of an
end-to-end experiment. Answer repair is not Skill evolution; fallback is not
learned generalization; an accepted verifier is not an accepted Skill.

Preserve frozen historical protocols, scores, and artifacts. New behavior needs
a new version/output directory; do not retrospectively relabel an old run.
Never publish secrets, `.env`, private API caches, or unreviewed third-party data.

Keep README and `docs/research-overview.md` as discoverable entry points to the
two living documents. Check relative links and numeric consistency when editing
them. Documentation-only work does not require paid experiments. These
maintenance instructions do not authorize unrelated edits, experiments, commits,
or pushes during read-only explanation/review requests.
