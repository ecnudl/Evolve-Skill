# M4 progress (deepseek route B: second provider for chain D)

Started 2026-10-22 18:11 CST. Target 20:11, hard stop 20:41. All items done at 18:5x.
Spec: registrar "Owner instructions 2026-10-22 17:0x and 17:3x", row "deepseek route B"; registration §4.1, §21.
Owned: skillopt/execskill/client.py; new skillopt/execskill/routes.py; new tests/test_execskill_routes.py;
minimal logged edits elsewhere (see the coordination log 18:3x-18:5x). Mutation numbers: 108-110.

## Status
- [x] read coordination, registrar 17:0x/17:3x, registration §4.1/§21, client.py, frozen client/calls/outcomes
- [x] client.py: `RouteClient` base (no frozen constructor), `ElucidClient` = route A, `NorthgateClient` = route B
      (NORTHGATE_ENV by path, NORTHGATE_CHAT_URL / NORTHGATE_API_KEY, host northgate.xiaobei.top, /v1/chat/completions,
      body model deepseek-v4-flash, reasoning_effort "none", GATEWAY, trust_env=False, same reasoning check, echo set
      {deepseek-v4-flash, deepseek-flash}); `model` stays chain D's slot name, `request_model` is what the body names;
      every receipt carries `route` and `route_model`; `solver_client` takes an optional `route` config key
- [x] balance exhaustion: `balance_signal` (route B: 429 + error.code insufficient_quota; both routes: 402, and 403/429
      whose body or decoded JSON mentions insufficient balance/quota/credit/funds or 余额); `_Guard` wraps the httpx client,
      raises `errors.BalanceExhausted` before the frozen retries and latches (nothing sent afterwards); ordinary 429 keeps
      the frozen RATE_BACKOFF retries
- [x] errors.py: `BalanceExhausted` -> stop kind `balance_exhausted` (STOP_KINDS; outcomes_ext re-raises it by name)
- [x] routes.py: `route-<n>.json` write-once history (chained hashes, run, chain), `current`, `check_bound`, `idle`
      (runner lock held + no owned unit lock), `open_pauses` / `latest_pause`, `switch` (one pause motivates one switch,
      otherwise --reason), `pin` / `check_pins` (branch N, longest = S1 longest on N else 256), `block_of`, `config`
- [x] manifest.py: optional `clients.routes` pin, required for `main`; `setting_of` binds the chain's current route per
      process (branch/longest/B of its block, `extra["route"]`); `_clients` re-reads the history at every solver client
      request and refuses a changed route (no mid-unit switch)
- [x] run_execskill.py: `switch-route --manifest M --chain D --to B [--reason TEXT]`
- [x] chain.py: route B's own first call (`confirm-route-B.json`); `confirmation()` defaults to the current route
- [x] cells.py: `solver_route` on every cell record (and shared cells)
- [x] tests/test_execskill_routes.py (46 passed) + mutation entries 108-110 (+ re-pointed 39, 42), verified on /tmp copies
- [x] offline check of the real route-B credential file: accepted (mode 600), nothing printed, no request

## Open questions (in the final report)
- route B echo ids: allow-list {deepseek-v4-flash, deepseek-flash} -- confirm from the 17:3x probe receipts
- route B's `longest` = 256 (S1-b ceiling) unless chain D's S1 ran on branch N; B = 4M (QA 32,768 / SB 65,536)
- a balance-exhausted call charges its full reservation (frozen Endpoint, no receipt): conservative
- route A's balance format is unknown: the 402 / 403-429 text heuristics may misclassify an unusual body
- evaluation.sealed_cell drops `solver_route` (asked V); docs/current-workflow.md needs a route-B paragraph (integrator)
