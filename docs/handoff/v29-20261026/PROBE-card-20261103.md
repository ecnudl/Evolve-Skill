# PROBE brief — instruction-card decomposition probe on practice items (2026-11-03)

Purpose (owner 2026-11-03 19:2x: explore freely; see BRIEF-v222-main-v8.md §1 and §4): measure, on PRACTICE items only, how
much of each bench's instruction card is answer-FORMAT value and how much is CONTENT value, for the two solvers. No test item
is read; nothing is learned; the result calibrates the v2.22 card decomposition.

## Script: `scripts/card_probe.py` (new, standalone, no protocol unit, no consent)

Inputs
- Practice pools: `/data/execskill-20261021-pre/pools/searchqa.json` and `/data/execskill-20261021-pre/pools/officeqa.json`
  (the route-B practice pools; read their structure with the existing loaders in `skillopt/execskill/` — find where S0 and the
  training slices load them — and sample 200 items per bench with a fixed seed `20261103`, excluding nothing else).
- Historical cards: `docs/handoff/v29-20261026/v210-instructions-coevo5-v1.json` (texts + sha256; verify the hashes).
- Format blocks: write them as constants in the script (one per bench) by extracting ONLY the answer-form sentences of each
  historical card (SearchQA: answer tag/minimal entity/exact match; OfficeQA: single number with the scaled digits, answer
  tag); print the exact texts and their sha256 at start so they can be pinned later.
- Solvers: chain G = GLM-5.3 through the roles repo credentials (`/root/continual-noskill-bcb-20260928-a`, as the route-B
  manifests use them) and chain D = deepseek-v4-flash through northgate (`<deepseek-credentials-file>`); reuse
  `skillopt/execskill/client.py` / `budgets.py` endpoint construction exactly as `manifest.py` does for a chain-G and a chain-D
  solver block (same timeouts, max tokens, proxy pin); never print credentials.

Arms (each item once per arm, same shell as the C arm of the bench: `solver.solve(bench, public, card_text, package=empty)`)
- `hist`: card_text = the historical card.
- `fmt`: card_text = the format block only.
- `fmt_own`: card_text = format block + "\n\n" + the card's remaining content sentences (as the card, but reordered: format
  first).
- `blank`: card_text = "" (the B arm's definition).

Scoring: the bench's registered judge (`judge.py`) exactly as the C arm's cells are judged (official, lenient, format
counters: tag_present/usable, single_number, violation, numeric_equal_string_unequal, truncated).

Outputs (under an output root given on the command line, e.g. `/data/probe-card-20261103/<chain>/<bench>/`): one JSON per
cell (item id, arm, request sha256, reply, judged fields, usage), a `summary.json` per (chain, bench) with accuracy per arm,
paired contrasts vs `hist` (mean difference in points, 95% bootstrap CI, better/worse counts, sign-test p), format counters per
arm, total tokens; and `probe-report.md` with the four tables. Concurrency ≤ 3 per solver (the machines run other chains);
retries as the route-B client does; resumable (skip cells that exist).

Controls: `--limit N` for a smoke (5 items), `--dry-run` (print the arms' system prompts and the first item's request, no
calls). Tests: `tests/test_card_probe.py` with a fake client: arms produce the expected card texts, blank = empty guidance,
summary arithmetic on a toy set, resumability. Constraints: no network/model calls in tests; never open files whose names
contain test/holdout/sealed/final/reserve; no edits outside `scripts/card_probe.py`, `tests/test_card_probe.py`,
`docs/handoff/v29-20261026/PROBE-card-20261103.md` (append a "writer notes" section with the exact run command).

## Writer notes (2026-11-03)

Implemented in `scripts/card_probe.py`; offline checks are in `tests/test_card_probe.py`.
This is a standalone practice probe, with no protocol unit, learning, Docker, or consent machinery.
Only these two files and this appended section were edited for this task. Existing research documents and
historical artifacts were left untouched under the brief's three-file constraint.

The loader is `manifest._items`, including its fixed practice ordering and file-hash check. A seeded draw of
200 items precedes the optional `--limit` prefix, so a five-item smoke resumes into the same 200-item draw.
No practice families or historical training slices are excluded. `--pool PATH` accepts relocated practice
fixture copies; restricted filenames/paths and non-practice part labels are refused before use. The original
item's `public` goes to `solver.solve`, which selects the public request fields; `private` goes only to the
registered judge. All arms use an empty package and the inherited `contract-first-v2` QA runtime. In particular,
`blank` has empty guidance but still receives the common shell answer-tag contract.

`instruction_start.pins()` verifies the frozen card file, every card SHA-256, and character counts. The format
constants contain verbatim historical text. SearchQA takes the independent exact-match clause after the
semicolon, the minimal-answer sentence, and the answer-tag sentence; its snippet-selection prefix remains
verbatim in the content remainder, including its semicolon. OfficeQA takes the scaled-digits sentence from
the mixed units bullet and its last three answer-format bullets. No table-search or source-selection advice
is added to the format block. `fmt_own` prepends the format block plus two newlines to the remainder, preserving
the remainder's order and historical wording. Printed format SHA-256 pins (UTF-8, no trailing newline):

- SearchQA: `41199c70104004cf2012e155a9047734cce7b02b5a07e72211d9fb70841fddb3`
- OfficeQA: `a478520617ee74cb13bfe112b3c6332ee315d7f9bef1dd472ef9a65387e00fc2`

Client construction uses `manifest.solver_block`, `manifest.solver_config`, the northgate route pin, and
`client.solver_client`, with the historical-card baseline configuration. G uses the roles repository above,
65,536 max tokens and a 2,400-second read timeout; D uses the northgate env path above, request model
`deepseek-v4-flash`, 8,192 max tokens and a 600-second read timeout. Both retain the registered explicit PJLAB
proxy and connect/write/pool timeouts (20/30/30 seconds). D's conservative branch-N bound is 32,768 using the
inherited 256-token route floor; that floor is not a newly measured probe result. The standalone runner uses
`budgets.Endpoint` without a protocol budget ledger, retaining the normal client retries and recorder resends.
Per-solver file slots under the common output root cap simultaneous requests at three, across both benches;
`--concurrency` accepts 1–3 and defaults to 3. Each invocation checks one completed response before releasing
its parallel work. Client creation is deferred until live, missing cells actually need a call.

Each completed/attempted cell has its item ID, arm, request hash, raw reply, registered judge result, usage,
and allow-listed send receipts; an exception that prevents judging is explicitly recorded with a null judge
result and exception type, without exception text. Failed sends remain evidence and are skipped on resume.
Cells are atomically written and checked against their checksum and item/request/configuration/code identity
before reuse. A changed pool, reference, card, or implementation requires a new output root. Parallel stops
retain already-running cells and leave unsubmitted cells missing. The four report tables are accuracy,
official paired contrasts, lenient paired contrasts, and format counters with tokens.

Accuracy denominators exclude infrastructure-unknown cells; known truncated/filtered/empty completions count
as failures for both metrics. Missing cells and unknown counts are separate. Each contrast uses only known
paired items, reports arm minus hist in percentage points, a seeded 10,000-draw paired-item percentile 95% CI,
better/worse/tie counts, and an exact two-sided binomial sign test excluding ties. These are exploratory
unadjusted comparisons. Format counts retain their applicable denominators, including unavailable or
inapplicable counters. Token totals include recorder resends; missing usage is counted explicitly, and no
monetary cost is inferred. Fake-client results are engineering fixtures, not method-effect evidence.

Local verification uses Python 3.13 (`python`; the Mac's `/usr/bin/python3` is 3.9 and is too old for this repo):

```sh
python -B tests/test_card_probe.py
for chain in G D; do
  for bench in searchqa officeqa; do
    python -B scripts/card_probe.py --chain "$chain" --bench "$bench" \
      --out /private/tmp/card-probe-local-dry-20261103 --limit 5 --dry-run \
      --pool "/private/tmp/execskill-v214/full/e2e-main0/pools/$bench.json"
  done
done
```

The four local dry runs used existing fixture copies (SearchQA 40 items; OfficeQA 80 items), selected five
items apiece, printed all four arm requests, and created no output root. The guarded verification additionally
blocked client construction and sockets. All 20 fake-client/unit checks passed, including interrupted parallel
work, retained failure receipts, resend token totals, paired arithmetic, and resume identity checks. The script
also passed Ruff with its repository configuration. No network/model calls, remote launches, Docker, or commits were made.

Linux commands below are for the operator, from the Linux checkout root containing this script. Use the
requested interpreter directly; do not prefix its executable path with another `python`. First verify all
four prompt/configuration combinations without credentials or calls:

```sh
for chain in G D; do
  for bench in searchqa officeqa; do
    /root/continual-alf-prep-20260928/env/bin/python -B scripts/card_probe.py \
      --chain "$chain" --bench "$bench" --out /data/probe-card-20261103 --limit 5 --dry-run
  done
done
```

For a real five-item smoke, run in one interactive Linux shell (proxy activation and commands share the shell):

```sh
proxy_on
for chain in G D; do
  for bench in searchqa officeqa; do
    /root/continual-alf-prep-20260928/env/bin/python -B scripts/card_probe.py \
      --chain "$chain" --bench "$bench" --out /data/probe-card-20261103 --limit 5 --concurrency 3 || break 2
  done
done
```

After inspecting the smoke's actual responses, these two background launches resume the smoke and complete
200 items per bench. Each process runs its two benches sequentially; G and D may run together. The gateway
configuration must still match the pinned credential-free PJLAB gateway before launching. No command prints
credential files or environment contents.

```sh
mkdir -p /data/probe-card-20261103
nohup bash -ic 'proxy_on && for bench in searchqa officeqa; do /root/continual-alf-prep-20260928/env/bin/python -B scripts/card_probe.py --chain G --bench "$bench" --out /data/probe-card-20261103 --concurrency 3 || exit; done' > /data/probe-card-20261103/G.log 2>&1 < /dev/null &
nohup bash -ic 'proxy_on && for bench in searchqa officeqa; do /root/continual-alf-prep-20260928/env/bin/python -B scripts/card_probe.py --chain D --bench "$bench" --out /data/probe-card-20261103 --concurrency 3 || exit; done' > /data/probe-card-20261103/D.log 2>&1 < /dev/null &
```

Results are `/data/probe-card-20261103/<chain>/<bench>/cells/*.json`, `summary.json`, and `probe-report.md`.
Repeat the same command to resume. Exit status is nonzero while selected cells are missing or infrastructure
unknown; existing failed cells are retained rather than automatically replayed.
