# P2C-R7: will the GLM role scopes pause a pilot step? (registrar addendum 15:5x, row R7)

Read-only analysis by P2C, 2026-10-22, against the code as read between 15:5x and 16:3x. I1 is editing `step.py`,
`engineer.py` and `examiner.py`. After I1's 16:21-16:24 edits I re-checked every flow cited here: `_ask`,
`run`, `_candidate`, `glm_projection` and the system prompt sizes. Line numbers are approximate.

I made no code change and no model call. Two kinds of computation were run on dl with `python -B` and no write:
- `smoke.glm_projection` on synthetic S3 inputs;
- prompt sizes from the modules.

The only data read was the v1 ledger `/data/coevo5-20261017-run/shared/ledger/events.jsonl`:
- settle events of the learning scopes only (training);
- aggregates only: no text, no evaluation scope, no test file.

I did not read the smoke root, so S3's real measurements are unknown (section 4).

## Short answer

- **Normal step: no pause.** In a normal SpreadsheetBench (SB) or OfficeQA (OQ) step, no role scope refuses. The highest
  single need (settled + the next reservation, against the cap) is:
  - engineer: 0.97M of 1.5M with no self-test block, 1.10-1.29M with one block;
  - examiner: ≤ 1.87M of 2.5M;
  - examiner research: ≤ 1.13M of 4.6M.
- **The engineer scope is the only realistic risk.**
  - **Admission rule.** A full-size engineer request reserves 968,264. So it is admitted only while settled ≤ 531,736.
  - **Worst sequence.** The worst sequence the code allows has 4 full-size requests: proposal and re-proposal, twice,
    once in `engineer` and once in `engineer-2`. That sequence needs:
    - 1.26M at typical usage;
    - 1.47M at heavy usage, a 31k margin;
    - 1.55M at heavy usage with 75 KB fixes: refused;
    - 1.97M at the ledger's single-attempt bound: refused.
  - **Charged failed attempts.** A charged failed attempt is HTTP 5xx, a read timeout or the like; connect errors and 4xx
    cost 0. Each one on a full-size call adds 242,066:
    - one such attempt → the 4th full-size request is refused even at typical usage (need 1,502,843);
    - two before any later full-size request → refused in every model;
    - one fully failed full-size send (4 charged attempts, or no receipt) settles 968,264, so its resend 300 s later is
      refused at once.
- **The pause is sticky.** Role scopes have no attempt sub-scope, so a redo of the paused unit meets the same settled
  sum. Only an owner cap raise (`Budget.raise_cap`) clears it, and no route-B command does that.
- **S-E6 passes only conditionally.** S-E6 will most likely pass the 14 GLM rows, so the go check passes. But that pass
  does not cover the worst sequence:
  - S-E6 counts 6/6/3 engineer/leakage/describer calls per step; the code allows 10/12/3;
  - it prices calls at S3's SearchQA mean;
  - its 220,000-byte floor omits the system prompt.

  The engineer row fails if S3's engineer mean exceeds about 86-90k tokens per call, or if one S3 engineer send had a
  charged failed attempt.
- **Recommendation.** Engineer 2.5M and examiner 3.0M per step; examiner research stays 4.6M. That is 10.1M per step
  and 20.2M for the two pilot steps, so the `<c>:glm` cap of 30M is unchanged and still never binds first.

## 1. Scopes, caps, what is charged where, concurrency

Every role call is GLM-5.3 (ledger bound B = M = 16,384) and charges three scopes: `overall` (210M per chain = solver 180M
+ GLM 30M), `<c>:glm` (30M) and one per-step role scope, `<c>:xs:<bench>:<k>:role:<role>` (`budgets.glm_scopes`,
`budgets.ROLES`). The pilot runs SB as step 1 and OQ as step 2, for chains G and D. Each chain has its own ledger.

| Per-step scope | Cap | Charged by (unit) | Most calls per step in the code |
|---|---|---|---|
| `…:role:engineer` | 1,500,000 | Engineer proposal, re-proposal and fixes (`engineer`, `engineer-2`). The C4 leakage adjudications inside both (`leak/…`, same Roles). The describer (`freeze`). | Engineer 10 (5 per unit: propose, re-propose, 3 fixes). Adjudications 12 (one per check, ≤ 2 checks per change, ≤ 3 changes per unit). Describer 3. |
| `…:role:examiner` | 2,500,000 | Detector write and rewrite (`diagnose`). Policy (`generate`). Generator write and rewrite, plus the band re-writes (`generate`). The band, shortcut and G_acc probe cells are solver calls charged to `…:examiner` under `<c>:solver`, not here. | 2 + 1 + 3 × 2 = 9 |
| `…:role:examiner:research` | 4,600,000 | Research query, pick and conclude (`generate`). | 24 requests × 8 calls = 192, with ≤ 2 concludes per request (9 calls would be needed for 3) |
| `<c>:glm` (per chain) | 30,000,000 | All of the above. Nothing else: chain G's solver cells and the first-call confirmation charge `<c>:solver`. | Per-step caps 8.6M × 2 steps = 17.2M < 30M, so `<c>:glm` never binds first in the pilot. |

- **`ENGINEER_CALLS` = 6 never binds.**
  - It is counted per unit label within one Roles, i.e. per unit attempt (`engineer._ask`).
  - One unit makes at most 5 engineer calls.
  - `engineer-2` is a new label with a new Roles, so a step can make 10.
  - Every redo attempt restarts all counters: up to +5 engineer calls, +6 adjudications, +9 examiner calls and +192
    research calls. Each charges the same per-step role scope, since `glm_scopes` takes no attempt argument.
- **Concurrency inside a scope: none.**
  - A chain is one process; a step's units run in order.
  - `engineer`, `examiner`, `research`, `describer` and `leakage` use no threads. The only `ThreadPoolExecutor` is the
    test read in `chain.py`.
  - So a role scope has at most one open reservation. `Budget.reserve` (coevo5/budget.py:283) therefore admits a call iff
    settled + R ≤ cap; otherwise it refuses at once (no wait, since nothing open shares the scope).
  - Chains G and D run concurrently on separate ledgers. They share only the 10 glm-5.3 slots: a slot wait, never a
    budget refusal.

## 2. Per-call reservation and settlement

- **Reservation.** R = 4 × (request bytes + 512 + 16,384), where request bytes = system + user. The user message is
  fitted to 220,000 bytes (`roles.fit`) only for the engineer proposal, the detector and the SB generator sources.
- **Settlement.** A valid single-attempt receipt charges prompt + completion. Each charged failed attempt adds one
  bound (bytes + 512 + 16,384). No receipt, or 4 failed attempts, charges R. `Recorder` resends an undelivered call ≤ 2
  times, 300 s apart, each send making its own reservation.
- **Three settlement models:**
  - *typ*: bytes ÷ 3.0 per prompt token, plus completion 6,000 (full-size), 4,000 (fix), 100 (adjudication) or 400
    (describer). For reference, v1 gives 3.21 for the rule writer and 2.99 for OQ GLM requests ≥ 20 KB.
  - *heavy*: bytes ÷ 2.0, plus completion 16,384 for engineer and examiner calls. v1 OQ requests ≥ 20 KB have p10 ≈ 2.1;
    the minimum seen in v1 is 1.84-1.91.
  - *bound*: bytes + 512 + 16,384, the most a valid single-attempt receipt can be charged.

| Call | Bytes (system + user) | R | Settled typ / heavy / bound |
|---|---|---|---|
| Engineer proposal or re-proposal, both units | 225,170 (5,170 + ≤ 220,000) | 968,264 | 81,057 / 128,969 / 242,066 |
| Engineer fix (payload not fitted) | 25,170 (20 KB) / 80,170 (75 KB) | 168,264 / 388,264 | 12,390 / 28,969 / 42,066; 30,723 / 56,469 / 97,066 |
| Leakage adjudication | ≤ 8,202 ASCII (≤ 21,002 if 3-byte text) | 100,392 (151,592) | 2,000 / 4,401 / 25,098 |
| Describer | ≤ 8,319 | 100,860 | 3,173 / 5,160 / 25,215 |
| Detector write | 221,823 | 954,876 | 79,941 / 127,296 / 238,719 |
| Policy (no previous policy in the pilot) | 2,192 SB / 3,427 OQ | 76,352 / 81,292 | ≈ 4,100 / 18,100 / 20,323 |
| Generator write, SB (sources fitted) | 222,293 | 956,756 | 80,098 / 127,530 / 239,189 |
| Generator write, OQ (materials not fitted; 100 KB assumed) | 102,293 | 476,756 | 40,098 / 67,530 / 119,189 |
| Research query or pick | ≈ 2,500 | ≈ 77,584 | v1 345 / 340; heavy ≈ 1,350; bound ≈ 19,396 |
| Research conclude, text (≤ 3 × 8,000-character excerpts) | ≈ 31,000 | ≈ 191,584 | v1 2,783 (max 5,310); heavy ≈ 15,800; bound ≈ 47,896 |
| Research conclude, table (preview limits) | ≤ ≈ 172,000 | ≈ 755,584 | heavy ≈ 86,300; bound ≈ 188,896 |

The re-proposal, detector rewrite and generator rewrite add `"unparseable"` after fitting. This is ≤ about 40 bytes, so
R grows by at most about 160.

v1 GLM ledger, learning-scope role calls (2,314 calls). Charged is in ledger tokens; request bytes = reserved ÷ 4 − 512 −
16,384:

| v1 role (proxy for) | n | Request bytes, mean (max) | Charged, mean (max) | Prompt tokens, mean (max) | Completion, mean (max) | Bytes per prompt token, mean (min) |
|---|---|---|---|---|---|---|
| analyst = v1 rule writer (engineer proposal) | 10 | 111,032 (209,041) | 37,839 (86,707) | 37,006 (85,789) | 833 (1,205) | 3.21 (2.38) |
| examiner/revise (large examiner call) | 8 | 68,322 (131,604) | 24,924 (60,327) | 23,949 (59,209) | 975 (1,240) | 3.11 (2.22) |
| diagnose | 593 | 6,811 (12,056) | 2,177 (22,551) | 1,984 (4,985) | 122 (6,677) | 3.58 (2.26) |
| leak (adjudication) | 45 | 1,078 (1,218) | 690 (18,418) | 242 (269) | 46 (68) | 4.45 (4.29) |
| research query / pick / conclude | 18 / 8 / 8 | 1,360 / 1,244 / 11,779 (22,798) | 345 / 340 / 2,783 (5,310) | 309 / 326 / 2,756 | 36 / 13 / 27 (≤ 61) | 4.41 / 3.86 / 4.28 |

- **Failed attempts in v1.** 4 of 2,314 role calls had a charged failed attempt (0.17%, all HTTP 500); the 22,551 and
  18,418 maxima above are two of them. 3 calls ended HTTP 400 and were charged 0. There were no read timeouts, and none
  of the 10 rule-writer calls failed.
- **Bytes per token of v1 GLM solver requests ≥ 20 KB:** OQ mean 2.99 (min 1.89), SB 3.03 (1.91), SearchQA 4.12 (min
  3.19, all sizes).

## 3. Admission sequences

### Engineer scope

A full-size request is admitted while settled ≤ 531,736. The table gives the need at the binding call
(settled before it + its R):

| Sequence | Binding call | Need typ / heavy / bound (20 KB fixes) | Heavy / bound with 75 KB fixes | With 1 charged failed attempt on a full-size call: typ / heavy / bound |
|---|---|---|---|---|
| T (typical SB or OQ step): P1, 3 × (A, X, A), 3 D | P1 | 968,264 in every model | 968,264 | 968,264 (bound with 75 KB fixes: X1 needs 1,192,018) |
| B1 (one self-test block): T + engineer-2 (P2, 3 × (A, X, A)) before freeze | P2 | 1,098,491 / 1,210,546 / 1,487,116 | 1,293,046 / **1,652,116** | 1,340,557 / 1,452,612 / **1,729,182** (heavy with 75 KB fixes **1,535,112**) |
| W (worst in the code, 25 calls): P1, RP1, 3 × (A, X, A), P2, RP2, 3 × (A, X, A), 3 D | RP2 | 1,260,777 / 1,468,664 / **1,971,448** | **1,551,164** / **2,136,448** | **1,502,843** / **1,710,730** / **2,213,514** |

Legend: P = proposal, RP = re-proposal, X = fix, A = adjudication, D = describer. Bold = refused (> 1,500,000).

- Settled at the end of T: 0.14M typ, 0.26M heavy.
- At the bound, W is already refused at P2, with settled 760,958.
- Typ + 1 failure is refused at RP2, with settled 534,419.

### Examiner scope

A full-size call is admitted while settled ≤ 1,545,124 (detector) or ≤ 1,543,244 (SB generator).

| Sequence | Binding call | Need typ / heavy / bound | Refused when |
|---|---|---|---|
| SB typical: D1, policy, G1, one band re-write G2 | G2 | 1,120,937 / 1,229,680 / 1,454,987 | not with ≤ 3 charged failed attempts (bound + 3: 2,171,144) |
| SB worst: D1, D2, policy, G1, G1', G2, G2', G3, G3' | G3' | 1,521,469 / 1,867,317 / **2,650,742** | heavy + 3 charged failed attempts (2,583,474); typ + 5 |
| OQ typical (generator about 100 KB) | D1 | 954,876 | — |
| OQ worst | G3' | 1,034,977 / 1,087,317 / 1,570,742 | not with ≤ 3 charged failed attempts at the bound (2,286,899) |

### Research scope

The worst schedule is 24 requests × 8 calls with 2 concludes each:

| Model | Need |
|---|---|
| v1 means | 0.37M (0.18M settled + R) |
| heavy, text concludes | 1,125,884 |
| heavy, table previews at their limits | **5,003,384**: refused at request 22's conclude (settled 3,886,400) |
| bound, text concludes | **5,196,928**: refused at request 22 |

### Where a refusal becomes likely

Only the engineer scope is at risk in realistic runs:

1. With no charged failed attempt, a refusal needs the 4th full-size request: an unparseable reply in both engineer units
   plus a self-test block. It also needs heavy tokenization with large fixes.
2. One charged failed attempt on any full-size engineer call (+242,066) causes a refusal:
   - at the 4th full-size request at typical usage;
   - at engineer-2's proposal at heavy usage with 75 KB fixes.
3. Two charged failed attempts before a later full-size request cause a refusal in every model: 484,132 + P1's own usage
   (≥ 81,057) > 531,736.
4. One fully failed full-size send settles 968,264, so the resend needs 1,936,528 and is refused at once.
5. All of these are sticky: a redo meets the same settled sum (section 1), so only an owner cap raise clears the pause.

Likelihood: v1 shows 0.17% of role calls with a charged failed attempt, so cases 2-4 should be rare per step. But v1
never measured 220 KB GLM requests under the 900 s read timeout (unverified).

## 4. What S-E6's zero-call GLM projection computes, and the go check

`smoke.glm_projection` (smoke.py:1334) produces 14 rows: for chains G and D, steps (spreadsheetbench, 1) and (officeqa,
2), plus `<c>:glm`. The rows are identical across chains and steps, because S3 is SearchQA-only.

| Row | Formula | Cap |
|---|---|---|
| Engineer | ⌈6e + 3d + 6l⌉ + 4 × (max(b_e, b_d, b_l, 220,000) + 16,896) | 1,500,000 |
| Examiner | ⌈9x⌉ + 4 × (max(b_x, 220,000) + 16,896) | 2,500,000 |
| Research | ⌈192r⌉ + 4 × (max(b_r, 220,000) + 16,896) | 4,600,000 |
| `<c>:glm` | ⌈2 × (6e + 3d + 6l + 9x + 192r)⌉ + the largest of the three R | 30,000,000 |

- **Per-call inputs:** e, d, l, x, r are S3's charge per call, i.e. the sum of each call's sends ÷ calls:
  - engineer (e): S3's engineer step, including its fixes and its in-step adjudications, which run through the same
    Roles;
  - describer (d): 1 call;
  - leakage (l): only the first-call adjudication;
  - examiner (x): the detector plus the LiveMath generator;
  - research (r): ≤ 8 calls.
- **Byte inputs:** b is S3's largest request (system + user) per role. So R = 947,584 for every role, unless S3's own
  request was larger: a full SearchQA proposal gives 968,264, a full detector request 954,876.
- **Pass thresholds:**
  - engineer: 6e + 3d + 6l ≤ 552,416 (or ≤ 531,736 with a full S3 proposal). With d ≈ 3.2k and l ≈ 0.7k, that is
    e ≤ 89.8k (86.3k);
  - examiner: x ≤ 172,490 (171,680);
  - research: r ≤ 19,023;
  - `<c>:glm` never binds.

Outputs of the code itself on synthetic S3 inputs. All use x = 32k (48k for E3), r = 2k, d = 3.2k and l = 0.7k; "full"
means S3's SearchQA proposal was fitted to the 220,000 bytes:

| S3 scenario | Engineer row | Examiner | Research | `G:glm` |
|---|---|---|---|---|
| E1: proposal 59.7k + 2 fixes of 10k + 2 adjudications of 1k (e = 16,340), full | 1,080,104 pass | 1,242,876 pass | 1,331,584 pass | 2,535,944 pass |
| E2: proposal only (e = 59,700), full | 1,340,264 pass | 1,242,876 | 1,331,584 | 3,056,264 |
| E3: proposal only at 3.19 bytes/token with a 16,384-token completion (e = 86,970), full | **1,503,884 FAIL** | 1,386,876 | 1,331,584 | 3,671,504 |
| E3b: E3 with S3's proposal at 185 KB | 1,483,204 pass | 1,379,584 | 1,331,584 | 3,650,824 |
| E4: E2 + one charged failed attempt (e = 301,766) | **2,792,660 FAIL** | 1,242,876 | 1,331,584 | 5,961,056 |

**Go check.** `smoke-result.passed` requires every required stage to be `pass`. SE6 is `pass` only if the solver rows
and every GLM row fit. So:
- E1, E2 and E3b: S-E6 passes, and the runbook's §2 go-check `assert` passes;
- E3 and E4: SE6 fails, and the go check stops: no pilot, a v1.1 re-registration first (§9.3).

The realistic expectation is a pass. That assumes no charged failure, and SearchQA tokenizing at ≥ 3.19 bytes per token
as in v1. The engineer row's margin is then between about 0 and 0.42M. The real values are unknown until S3's record is
read.

**What a pass does not show:**
- **Call counts.** S-E6 counts 6/6/3 engineer/leakage/describer calls; the code allows 10/12/3 per step, +5/+6 per redo
  attempt. With 10/12/3, E2 would give 1,583,264 and fail at 1.5M.
- **Pricing.** e is a SearchQA mean, diluted by fixes and adjudications. A pilot proposal is a 225,170-byte request
  settling 81-129k. For the worst sequence, the true settled part before the 4th full-size request is 0.29M (typ) to
  0.50M (heavy); in E1, 6e + 3d + 6l = 0.11M.
- **Floor.** The 220,000-byte floor is the user-message limit; a full request also carries its system prompt. Unless S3's
  request was full, R is short by:
  - engineer: 20,680 (968,264 vs 947,584);
  - detector: 7,292;
  - generator: 9,172.
- **Sequence.** S-E6 checks "settled at the maximum + one R", not the per-call sequence. The binding call, the 4th
  full-size engineer request, is never evaluated.

## 5. Recommended per-step caps

| Scope | Registered | Worst code sequence, heavy, no failure | Worst code sequence, bound + 1 charged failed attempt | Recommended |
|---|---|---|---|---|
| Engineer | 1.5M | 1,468,664 (20 KB fixes) / 1,551,164 (75 KB) | 2,213,514 / 2,378,514 | **2.5M** |
| Examiner | 2.5M | 1,867,317 (SB) | 2,889,461 (SB) | **3.0M** |
| Examiner research | 4.6M | 1,125,884 (text concludes); 5,003,384 if table previews are at their limits | bound, text: 5,196,928 (not meaningful: v1 research completions ≤ 61 of 16,384 tokens) | **4.6M unchanged**; 5.1M only to cover the table-preview extreme |

- **Engineer at 2.5M** admits the worst code sequence at the bound, with 75 KB fixes and one charged failed full-size
  attempt (margin 121,486). At heavy usage it also absorbs one fully failed full-size send plus its resend (2,436,928).
- **If 6 engineer calls per step were enforced** across `engineer` and `engineer-2`, the binding call becomes the 3rd
  full-size request. At the bound + 1 failure that needs 1,971,248 (20 KB fixes) or 2,136,248 (75 KB fixes), so about
  2.2M would do.
- **Examiner at 3.0M** admits SB's worst sequence at the bound + 1 charged failed attempt (margin 110,539). At heavy
  usage it tolerates 4 such attempts.
- **Effect on the chain total.** The per-step role ceiling goes from 8.6M to 10.1M (10.6M with research at 5.1M). The
  two pilot steps total 20.2M (21.2M), so:
  - `<c>:glm` stays 30M and still cannot bind first;
  - `overall` stays 210M per chain;
  - both chains' GLM stays at 60M.
- **Effect on S-E6.** The new caps reach S-E6 through `budgets.chain_caps` (ROLE_SCOPE_CAPS ← `protocol.ROLE_CAPS`):
  - engineer row: passes for e ≤ about 253-256k. E3 then passes (1,503,884 ≤ 2.5M); E4 still fails (2,792,660);
  - examiner row: passes for x ≤ 227,236;
  - research row: unchanged;
  - `<c>:glm` row: unchanged (2.5-6.0M against 30M in E1-E4);
  - if `MAX_ROLE_CALLS` were also set to the code's 10/12/3: the engineer row passes at 2.5M for e ≤ about 151-153k
    (E2 1,583,264 and E3 1,855,964 both pass).
- **Registration.** The caps are registered (§9.3, calc T11; owner rule: registered caps are not recomputed in place).
  So any change is a registrar or v1.1 decision. It must also update the 8.6M figure in the `budgets.py` docstring and in
  the runbook's cap table.

## 6. Not verified

1. **S3's real measurements.** I did not read the smoke root; the E1-E4 inputs are v1-based proxies.
2. **Engineer proposals and replies.** No measurement exists of SB or OQ proposals at 225 KB, nor of route-B engineer
   replies (code + replay tests). The heavy model's 2.0 bytes/token and 16,384-token completion are assumptions taken
   from v1's OQ and SB solver requests (v1 steps s2 = OQ and s4 = SB, read from v3's bench order).
3. **Fix payloads** are not fitted. 20 KB (typical) and 75 KB (bounded by the 16,384-token reply) are my estimates.
4. **Adjudication size** assumes reference answers of ≤ 200 characters; the SB and OQ corpora were not read.
5. **OQ generator.** Only `sources` is fitted, and OQ has none: the materials (OfficeQA tables, up to 60 × 15 uncut cells)
   are not.
   - The request size depends on research; 100 KB was assumed.
   - Above 220 KB, `fit` raises ValueError and the generate unit pauses. That is a non-budget pause, outside R7's scope.
6. **Research table previews** depend on the Wikipedia pages read. The maximum assumes 10 tables × 6 rows × 15 columns ×
   60 characters per page, over 3 pages.
7. **Failure rates** of 220 KB GLM requests under the 900 s read timeout are not measured: v1's largest role call was
   209 KB, n = 10, with no failure.
8. **Line numbers** are as read at 16:2x, while I1 was editing the files.
