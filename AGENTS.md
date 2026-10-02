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

# PJLAB Linux networking and experiment launches

- Test the user's exact `ssh PJ-CL4MIND-DULIN` command first. The configured
  ControlMaster may provide a working authenticated connection even when a
  fresh TCP/SSH handshake fails. Use `ssh -O check PJ-CL4MIND-DULIN` to distinguish
  these cases; a failed diagnostic with `ControlMaster=no`/`ControlPath=none`
  does not prove that the normal alias is unusable. Do not terminate the user's
  working master connection while diagnosing or closing a child session.
- Connect to the development machine with `ssh PJ-CL4MIND-DULIN`. Before
  downloading dependencies/data or calling external APIs there, run `proxy_on`
  **on the Linux machine**, not on the local Mac. For non-interactive SSH, use
  an interactive Bash shell when necessary to load this shell function, e.g.
  `ssh PJ-CL4MIND-DULIN "bash -ic 'proxy_on && YOUR_COMMAND'"`.
- Keep proxy activation and the launched command in the same shell, or pass an
  explicit approved proxy to the client. Running `proxy_on` in one SSH session
  does not change the environment of another session or an existing process.
- A client using `trust_env=False` ignores `HTTP_PROXY`/`HTTPS_PROXY`; activating
  the shell proxy alone is insufficient. The current BigModel client accepts
  an explicit, credential-free PJLAB gateway
  `http://httpproxy-headless.kubebrain.svc.pjlab.local:3128`. Verify the current
  `proxy_on` configuration without exposing credentials; bind the actual proxy
  to the new experiment protocol/cache identity instead of silently changing
  a frozen run. Other proxy destinations need explicit review.
- Check network/TLS connectivity separately from API authorization. Direct
  connection timeouts are not evidence that a key is invalid or banned. Confirm
  the first actual model response before releasing a concurrent experiment.
- Prefer Linux background execution for long runs, so local sleep/disconnection
  does not terminate them. Keep failed launches and receipts; do not interpret
  unsubmitted tasks or infrastructure failures as model accuracy.
- Do not stop, restart, or globally reconfigure the local Clash Party to make
  these experiments work. Never print `.env`, API keys, or proxy credentials.
- If SSH fails while aTrust is logged in, distinguish the private SSH route
  from the VPN's public gateway route. On 2026-10-01, the private destination
  used aTrust but its confirmed public gateway was captured by Clash's TUN.
  A user-authorized temporary host route for that single VPN gateway through
  the active Wi-Fi gateway restored the exact SSH alias. Verify both addresses
  and the physical interface anew before proposing this remedy; do not reuse
  stale gateway addresses, bypass the entire VPN/private subnet, or change the
  default route. Obtain administrator authorization through the OS prompt,
  never through a password in chat. Record the exact route and its rollback
  in the local handoff; do not remove it during an active remote experiment.
