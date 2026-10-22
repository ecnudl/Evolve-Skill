# Linux operations on dl (route B / execskill) -- area map

Status: COMPLETE (read-only survey, 2026-10-21 16:59-17:20 HKT). Author: subagent "linux-ops". Nothing in the repository or on dl was modified; the only files written are this deliverable and two helper scripts plus one empty dry-run dir in `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/` (`treehash.py`, `celltimes.py`, empty `rsync-dryrun/`).

Host: `ssh -o BatchMode=yes dl.dulin+root.ailab-datatools.ws@h.pjlab.org.cn` (hostname `dl`, root). Legend: "verified" = I read it (file:line or command on dl); "inferred" = my conclusion, not directly observed.

## 1. Scope and files read

Area: python env, working copy and snapshot hashing, proxy, credentials (names only), docker images and invocation, ALFWorld install, run-dir/manifest/tmux conventions, concurrency slots, observed per-cell timings, and a credential-free launch recipe for `/data/execskill-20261021-source`.

Local repo (read; line counts): `docs/project-status.md` (491; §4 lines 178-260 and §6 431-491), `docs/handoff/coevo5-registration-v3-delta-20261019.md` (387; §8-§11 lines 227-321), `docs/handoff/coevo5-registration-20261016.md` (700; grep only), `docs/results-and-lessons.md` (666; grep only), `skillopt/coevo5/protocol.py` (357), `skillopt/coevo5/calls.py` (279; lines 1-135), `skillopt/coevo5/manifest.py` (154; lines 1-5, 30-35, 88-118, 149-151), `skillopt/coevo5/cells.py` (263; grep), `skillopt/coevo5/evaluation.py` (455; lines 360-380), `skillopt/coevo5/smoke.py` (435; lines 315-330), `skillopt/coevo5/data.py` (358; grep), `skillopt/coevo5/budget.py` (351; grep), `skillopt/continual_eval/backends.py` (783; lines 1-60 constants, 100-284, 600-783), `skillopt/continual_eval/core.py` (359; lines 30-39), `skillopt/continual_eval/sheet_recalc.py` (886; grep), `skillopt/continual_eval/native_worker.py` (119; grep), `skillopt/continual_eval/sheet_recalc_worker.py` (123; grep), `skillopt/continual_eval/runtime/requirements-native.txt` (10), `skillopt/envs/alfworld/vendor/config_tw.yaml` (145; grep), `scripts/run_coevo5.py` (311; lines 230-311), `scripts/weak_solver_probe.py` (608; lines 60-96, 115-175, 226-260, grep), design sketch `.../scratchpad/execskill/design-v0.md` (55), auto-memory `new-machine-migration.md`.

On dl (read-only; line counts): `/data/coevo5-20261019-v3-ops/prep-v3.sh` (37), `/data/coevo5-20261019-v3-ops/f/{prep-v3f.sh 34, prep-launch-v3.sh 17, launch-v3.sh 12, run-chain-v3.sh 9, poll-v3-first.sh 6, poll-v3-run.sh 7, show-v3-run.sh 17, consent-note.txt, prep-launch.log, make-manifest.log, smoke.log, prep.log}`, sha lists `source-v3.sha256`/`source-v3-expected.sha256`/`f/source-v3f.sha256` (1,144 lines each; format and coverage only), `/data/coevo5-20261019-v3-run-manifest.json` (134,219 B; structure via python with secret-looking keys redacted; test entries not followed), `/root/.bashrc` (151; through a sanitizer that replaced every value with `<value>`), `/root/.config/weak-solver/*.env` (variable NAMES only), `/root/continual-noskill-bcb-20260928-a/.env` (NAMES only), `/etc/docker/daemon.json` (keys), `/data/docker/image/overlay2/{repositories.json, imagedb/content/sha256/<3 ids>}`, `/root/continual-alf-prep-20260928/{env/pyvenv.cfg, assets-complete.json}`, `/data/feasibility/D6/{pip-sympy.log head/tail, pilot/common.py:16, pilot/sandbox_runner.py:16}`, another agent's `/data/execskill-probe.py` (47) and `/data/execskill-ops/probe-20261021-1.log` (6), stat-only timing of `/data/coevo5-20261019-v3-run/{I-ds,E-ds}/s1..s5/<non-test units>` and `/data/coevo5-20261019-v3-pre/smoke-3/I-ds`, one smoke training cell record (status/timing fields only), `psutil` process listing.

Not read (by rule): anything under `evaluation/`, `shared/test/`, unit names containing "test" (incl. `selftest`), test panels, `.env` contents, key values, the ELUCID URL itself.

## 2. Facts

### 2.1 Host, env, packages, launch history (verified 2026-10-21 ~17:00 HKT)
F1 (verified, dl shell): host `dl`, 7 CPUs (`nproc`), 15 GiB RAM (`free -g`), `/` = /dev/rbd0 100G (71G used), `/data` = /dev/rbd1 400G (5.8G used). Clock on dl is HKT (UTC+8), same wall time as the Mac.
F2 (verified, dl `ls -la /data`): existing package dirs follow `/data/coevo5-<YYYYMMDD>-<ver>-<role>[-<letter>]`, roles seen: `source`, `source-b..f`, `ops`, `pre`, `run`, `archive`, `sheet-q23[-b..f]`, `sheet-train[-b..f]`, `report`, plus top-level `/data/coevo5-<date>-<ver>-run-manifest.json` (mode 600, root). Source dirs are owned `dulin:staff` with mtime Oct 15 18:02 (rsync -a from the Mac preserves Mac uid/gid/mtime); all generated dirs are `root:root`. Also present: `/data/feasibility/{D1..D14,E1..E10,*-critic}`, `/data/skillopt-work` (dulin:staff), `/data/docker` (drwx--x--- root), `/data/migrate-logs`, `/data/jupyter`, and NEW today (16:58, created by another agent, not by me): `/data/execskill-ops/probe-20261021-1.log`, `/data/execskill-probe.py`.
F3 (verified): python = `/root/continual-alf-prep-20260928/env/bin/python` -> symlink to `/root/miniconda3/envs/skill_validation/bin/python`; Python 3.11.16; it is a venv created with `--system-site-packages` (`/root/continual-alf-prep-20260928/env/pyvenv.cfg`: `include-system-site-packages = true`, `home = /root/miniconda3/envs/skill_validation/bin`). Packages resolve from two site-packages: the venv's (`alfworld`, `textworld`, `openai`) and the conda env's (`numpy`, `openpyxl`, `yaml`, `httpx`).
F4 (verified, `pip list` in that env, 79 lines): alfworld 0.4.2, textworld 1.7.0, fast_downward_textworld 20.6.4, gymnasium 1.2.0, jericho 3.3.1, openpyxl 3.1.5, numpy 2.4.6, httpx 0.28.1, openai 3.17.0, PyYAML 6.0.3, requests 2.34.2, pydantic 2.13.5, pytest 9.1.1, python-dotenv 1.2.3, omegaconf 2.3.0, networkx 3.6.1, spacy 3.8.16, psutil 7.2.2, truststore 0.10.4, tqdm 4.70.1.
F5 (verified, import test): **NOT importable in that env: `sympy`, `docker` (Python SDK), `pandas`, `scipy`, `formulas`.** pandas and scipy exist only under the system Python 3.10.12 (`/usr/local/lib/python3.10/dist-packages/{pandas,scipy}`; `/usr/bin/python3`). No docker SDK anywhere checked.
F6 (verified): the only sympy on dl is a `pip install --target` tree from feasibility D6: `/data/feasibility/D6/pylib/` (sympy 1.14.0 `/data/feasibility/D6/pylib/sympy/release.py:1`, mpmath 1.3.0), used via `sys.path.insert(0, "/data/feasibility/D6/pylib")` (`/data/feasibility/D6/pilot/sandbox_runner.py:16`, `/data/feasibility/D6/pilot/common.py:16`). The pip log `/data/feasibility/D6/pip-sympy.log` shows the install came from the PJLAB internal mirrors (`http://mirrors.i.h.pjlab.org.cn/repository/pypi-proxy/simple/`, `http://pypi.i.h.pjlab.org.cn/brain/dev/+simple`), i.e. pip installs work on dl via the internal index.
F7 (verified, local docs): v3 run rules fixed concurrency slots "deepseek 12、GLM 10、SpreadsheetBench 本地 3、ALFWorld 6" (`docs/handoff/coevo5-registration-v3-delta-20261019.md:235`); the three chains NoSkill-ds, I-ds, E-ds ran simultaneously sharing those 12 deepseek and 10 GLM slots (`docs/handoff/coevo5-registration-v3-delta-20261019.md:318`).
F8 (verified, local docs): v3 launch = 19:25 `prep-launch-v3.sh` (smoke-summary, make-manifest, check-baselines, consent; all zero-call, EXIT 0), 19:27 `launch-v3.sh` started the 3 chains each in its own tmux session `coevo5-v3-<chain>`, logs `/data/coevo5-20261019-v3-ops/f/run-<chain>.log`, run root `/data/coevo5-20261019-v3-run` (`docs/project-status.md:187`). Smoke ran in tmux `coevo5-v3f-prep` with scripts/logs in `/data/coevo5-20261019-v3-ops/f/` (`docs/project-status.md:189-190`). A second make-manifest is refused by code; one run process per chain (`docs/project-status.md:187`).
F9 (verified, local docs): deepseek solver in v3 = `deepseek-v4-flash` over the PJLAB token endpoint `https://token.pjlab.org.cn/v1/chat/completions` via the approved PJLAB gateway; key file mode 600 on dl, bound into the manifest by path (`--deepseek-env`), backend name `pjlab_token`; every request sends `thinking: disabled` and checks it per call (`thinking_mismatch` -> undelivered, max 2 resends) (`docs/handoff/coevo5-registration-v3-delta-20261019.md:241-264`). Max output 32,768 tokens, temperature 0 (same section). Reservation = worst case `4 x (request bytes + 512 + 32,768)` tokens; ledger is a lower bound because the client retries up to 3 times inside one request and only the last usage is recorded (same section, budget bullet).
F10 (verified, local docs): `docs/project-status.md` §6.2 (lines 440-458) still describes the OLD machine (`ssh PJ-CL4MIND-DULIN`, `/root/...` paths, `native.lock`); the new-machine facts live only in auto-memory `new-machine-migration.md` (Docker 26.1.3 works; `/usr/local/bin/curl` broken, `/usr/bin/curl` works; four SpreadsheetBench images migrated; working tree copied to `/data/skillopt-work` without .git/outputs/data). An implementer must not copy §6.2 paths blindly.

### 2.2 Concurrency, clients, credentials, proxy (verified ~17:04 HKT)
F11 (verified): cross-process concurrency is a protocol constant: `SLOTS = {"glm-5.3": 10, "deepseek-v4-flash": 12, "spreadsheet-native": 3, "alfworld-episode": 6}` (`skillopt/coevo5/protocol.py:331`; comment at :324-326 says these are file-lock slots shared by every coevo5 process, sized for "the development machine: 7 CPUs, 15 GB"). Per-model max output `SOLVER_MAX_TOKENS = {"glm-5.3": 65536, "deepseek-v4-flash": 32768}` (`skillopt/coevo5/protocol.py:327`). `DEEPSEEK_ROUTE = "pjlab_token"` (`skillopt/coevo5/protocol.py:330`).
F12 (verified): slots are implemented by `class Slots` (`skillopt/coevo5/calls.py:39-122`): `Slots(root, name, count, *, poll=0.5, sleep=time.sleep)`; one `fcntl.flock` lock file per slot `<root>/<name>.<index>.lock` (mode 600) plus `<name>.gather.lock` / `<name>.many.lock`; `hold()` (context manager yielding a slot index; random probe order; polls every 0.5 s) and `hold_many(count)` (gathers `count` slots, one gatherer per pool). A process that dies releases its locks (kernel flock). Name rule: `name.replace("-", "").replace(".", "").isalnum()` (`skillopt/coevo5/calls.py:41`). The manifest-bound runtime instantiates `Slots(shared / "slots", name, count)` for every SLOTS entry (`skillopt/coevo5/manifest.py:149-150`; smoke: `skillopt/coevo5/smoke.py:161`).
F13 (verified, dl manifest read with python, secrets redacted): `/data/coevo5-20261019-v3-run-manifest.json` top-level keys = `version, root, data, sheet_qualification, regression, tolerance, cards, instructions, rubrics, runtime, clients, research, baseline, workers, code, provenance, record_hash`; `version = fivebench-coevolution-v3-manifest`; `root = /data/coevo5-20261019-v3-run`; **`workers = 16`** (thread-pool width per evaluation call, used by `run_cells(context, jobs, workers=...)`, `skillopt/coevo5/cells.py:237-263`, `skillopt/coevo5/manifest.py:151`); `clients = {repo: /root/continual-noskill-bcb-20260928-a, proxy: http://httpproxy-headless.kubebrain.svc.pjlab.local:3128, deepseek_route: pjlab_token, deepseek_env: /root/.config/weak-solver/pjlab-token.env}`; `research.proxy` = same gateway; `baseline.model = {provider: bigmodel, name: glm-5.3, reasoning_effort: low, proxy: <gateway>}`; `baseline.service.host = open.bigmodel.cn`, `trust_env: False`. Expected key set is enforced at `skillopt/coevo5/manifest.py:35`. `code` maps every snapshot file path -> sha256 (e.g. `skillopt/coevo5/budget.py` -> `fe34ba79...`).
F14 (verified, same manifest): `runtime.spreadsheetbench = {prompt_layout: contract-first-v2, image: sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd, timeout_seconds: 300, memory_mb: 4096, cpus: 1, code_extraction_version: explicit-python-fences-v1, spreadsheet_preview_version: public-formula-preview-v1, _stop_on_cleanup_failure: True, spreadsheet_scorer: qualified_lo_recalc_v7_v1, recalculation: {5 keys}}`; `runtime.alfworld = {alfworld_data: /root/continual-alf-prep-20260928/data, alfworld_split: train, max_steps: 50, timeout_seconds: 60, seed: 42, alfworld_trace_version: alfworld-public-transitions-v1}`; `runtime.{searchqa,officeqa,livemath} = {prompt_layout: contract-first-v2}`.
F15 (verified): the solver HTTP client is `scripts/weak_solver_probe.py` `class Client` (`scripts/weak_solver_probe.py:227-257`): `Client(repo, model, *, proxy, max_tokens, router_env=None, read_timeout=900, transport=None, route=None, route_env=None)`; refuses any proxy other than `None` or `GATEWAY = "http://httpproxy-headless.kubebrain.svc.pjlab.local:3128"` (`:71`, `:234-235`); builds `httpx.Client(timeout=httpx.Timeout(connect=20, read=read_timeout, write=30, pool=30), trust_env=False, follow_redirects=False, proxy=<explicit>)` (`:254-256`). **Because `trust_env=False`, shell proxy variables set by `proxy_on` are ignored by this client; the proxy reaches it only through the manifest's `clients.proxy`.** Allow-lists: `MODELS` (`:77-86`) and `ROUTES = {"pjlab_token": {"deepseek-v4-flash": (frozenset({"deepseek-v4-flash"}), "disabled")}}` (`:88`); any explicit route is wired to `pjlab_credentials(route_env)` unconditionally (`:238-243`). Retry: `RETRY_STATUSES = {429, 500, 502, 503, 504}`, `BACKOFF = (10, 30, 60)`, `RATE_BACKOFF = (30, 90, 180)` (`:91-93`).
F16 (verified): credential files are read by PATH, in-process, never `source`d: `_read_env(path)` parses `KEY=VALUE` lines, strips quotes, keeps values in memory (`scripts/weak_solver_probe.py:115-123`); `bigmodel_credentials(repo)` reads `<repo>/.env` keys `BIGMODEL_CHAT_URL`, `BIGMODEL_API_KEY` and validates host/path (`:140-147`); `router_credentials(env_path)` reads `OPENDATALAB_ROUTER_URL`, `OPENDATALAB_ROUTER_KEY` (`:150-162`); `pjlab_credentials(env_path)` reads `PJLAB_TOKEN_API_KEY` with the fixed URL `https://token.pjlab.org.cn/v1/chat/completions` (`:165-171`). `_validated_url` requires https, exact host, no userinfo/query/fragment, port 443, exact path (`:126-137`). There is NO `elucid` route or `ELUCID_*` reader anywhere in the client (grep: no match for ELUCID/elucid in `scripts/weak_solver_probe.py`).
F17 (verified, dl `ls -la /root/.config/weak-solver/`; variable NAMES only via `grep -o '^NAME='`): dir mode 700 root. Files: `elucid.env` (600, 166 B, mtime 2026-10-21 16:57; names `ELUCID_CHAT_URL`, `ELUCID_API_KEY`, `ELUCID_MODEL`, plain `NAME=value` lines with no `export`), `pjlab-token.env` (600, 56 B, 10-19 11:12; `PJLAB_TOKEN_API_KEY`), `router.env` (600, 134 B, 10-15; `OPENDATALAB_ROUTER_URL`, `OPENDATALAB_ROUTER_KEY`), plus three helper scripts `bigmodel_check.py` (644), `router_check.py` (644), `search_check.py` (600). The BigModel (GLM-5.3) key lives in `/root/continual-noskill-bcb-20260928-a/.env` (manifest `clients.repo`, F13); not opened.
F18 (verified, `/root/.bashrc` read with values redacted by a python sanitizer): `.bashrc` is 151 lines; line 6 `[ -z "$PS1" ] && return` -> **a plain non-interactive `ssh dl 'cmd'` loads nothing from `.bashrc` (no proxy, no functions)**; `bash -ic '...'` sets PS1 and loads it. Lines 121-123 define `HTTP_PROXY_VAL=${MY_HTTP_PROXY:-...}`, `HTTPS_PROXY_VAL=${MY_HTTPS_PROXY:-...}`, `NO_PROXY_VAL=${MY_NO_PROXY:-...}`; `proxy_on()` (lines 126-137) exports exactly six variables `http_proxy, https_proxy, no_proxy, HTTP_PROXY, HTTPS_PROXY, NO_PROXY` and then ECHOES their values (hence redirect its output: `proxy_on >/dev/null 2>&1`); `proxy_off()` (140-144) unsets them. Defaults (parsed, not printed raw): both proxies = `http://httpproxy-headless.kubebrain.svc.pjlab.local:3128` with NO userinfo (equal to the manifest gateway); `NO_PROXY` default entries = `127.0.0.1, 10.0.0.0/8, 100.96.0.0/12, .pjlab.org.cn, .pjh-service.org.cn, 35.220.164.252`.
F19 (verified, same sanitized read): **`.bashrc` line 148 calls `proxy_on >/dev/null` automatically, and lines 149-150 `export OPENAI_BASE_URL=...` and `export OPENAI_API_KEY=...` (an "OpenDataLab Codex API" block, lines 147-151).** So every `bash -ic` shell (and every tmux session started from one) already has the proxy on AND carries an ambient OpenAI-SDK key/base URL. Any route-B client built on the `openai` SDK (openai 3.17.0 is installed) would silently pick these up unless it passes `base_url`/`api_key` explicitly; any `env` dump or `os.environ` logging would leak them.
F20 (verified by reading another agent's files, not mine): `/data/execskill-probe.py` (created 16:58 today) reads `/root/.config/weak-solver/elucid.env` by path in-process and calls `ELUCID_CHAT_URL` with `urllib.request` (which honors `HTTPS_PROXY`/`NO_PROXY` env); its log `/data/execskill-ops/probe-20261021-1.log` (16:59, starts with `bash: cannot set terminal process group`, i.e. it was run under `bash -ic`) shows 5 calls: 4x HTTP 200 with echoed model `deepseek-v4.1-flash-1017`, latency 2.4-6.8 s, and **`reasoning_content` present with 14-19 `reasoning_tokens` even when the body says `thinking: {"type": "disabled"}`**; an unknown model name gives HTTP 503 `model_not_found` ("No available channel ... under group ...(distributor)"). Consequence for ops: v3's per-call `thinking_mismatch` rule (F9) would mark every call on this route undelivered; route B needs its own receipt rule. (5 calls only; it is unknown whether the elucid host is inside NO_PROXY.)

### 2.3 Working copy, snapshot hashing, launch scripts, docker (verified ~17:08 HKT)
F21 (verified, hash computation on both sides with the same script `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/treehash.py`: tree hash = sha256 of sorted `"<relpath> <sha256>"` lines, `__pycache__`/`.pyc` excluded): the code trees are IDENTICAL on the Mac working tree, on dl `/data/skillopt-work`, and in the frozen v3 snapshot `/data/coevo5-20261019-v3-source-f`:
  - `skillopt/coevo5` 32 files `6d001f002fd0f2e62846b3b8eab3ff0f591748a2679a3be3f6ac3667a3649e9f` (per-file e.g. `protocol.py` f9296d5c1d1cf75b..., `calls.py` 1940c0d0c920a945..., `manifest.py` 3a460eb78d9b3b80..., `budget.py` fe34ba79773f2b1c... which also equals the v3 manifest `code` entry, F13);
  - `skillopt/continual_eval` 32 files `c0e41b319560170766cda89d964553c37f565e69bb3cc5923e587ecd1acdac76`; `skillopt/envs/alfworld` 19 files `c02d785b54c4927df7da59c32958147d5885313810f165db961f5bc3e4408ee1`; `scripts` 200 files `41ee87e55be3d81916c6bdc56c33b0a53ffb7076d4f71642e0667a7abe52e0fd`; whole `skillopt` 472 files `f870b8631595cdfd3ae504c0abcc334a9d0df721ebbe66e131d98839b85fa3be`; `tests` 472 files `de7fe18869a3dbda812ed3d89b9d288111cfde788171ca48725672e85a5eead0`; `configs` 117 files `02edd07f06444895beb9902d5db225350f50c14831801f0025500c8743da1632`.
  - Only `docs/` differs (Mac 565 files vs `/data/skillopt-work/docs` 461 files): docs were added locally after the 10-20 copy. So: **no code has changed locally since v3 snapshot f** (as of ~17:06 today); the uncommitted `M` files in the git status are already inside snapshot f.
F22 (verified, `ls -la`): `/data/skillopt-work` (dulin:staff, top mtime Oct 15 18:02) is a plain rsync copy of the Mac working tree without `.git`, `outputs`, `data`; **it contains the Mac repo's `.env` (mode 600, 1,663 B, mtime Sep 21)** -- i.e. that copy did not exclude `.env`. The v3 snapshot `/data/coevo5-20261019-v3-source-f` has NO `.env` (has `.env.example` only) and additionally has `blog/`, `ckpt/`, `skillopt-assets/`. Both keep Mac ownership/mtimes (rsync -a). How exactly `/data/skillopt-work` was copied (flags) is only recorded in auto-memory `new-machine-migration.md` ("the local repo working tree (no .git/outputs/data)"); no script for it found on dl (`/data/migrate-logs/` holds only `api_probe.py`, `api_probe2.py`, `pathcheck.sh`).
F23 (verified): snapshot integrity convention in v3 = a sha256sum-format list made on the Mac (owner `dulin`) and copied with the snapshot, plus a list recomputed on dl (owner `root`), compared byte-for-byte: `/data/coevo5-20261019-v3-ops/source-v3.sha256` (dulin, 13:16:48) vs `/data/coevo5-20261019-v3-ops/source-v3-expected.sha256` (root, 13:17:01), 1,144 lines each and identical (`cmp`); snapshot f's list `/data/coevo5-20261019-v3-ops/f/source-v3f.sha256` (dulin, 16:58:06). Format `<sha256>␠␠<relpath>`; coverage = `scripts/` (200) + `skillopt/` (472) + `tests/` (472); no `.env` line. Additionally the run manifest pins every code file's sha256 under `code` (F13) and a chain re-checks it ("A chain process checks, when it ...", `skillopt/coevo5/manifest.py:5`).
F24 (verified, `/data/coevo5-20261019-v3-ops/prep-v3.sh:1-37` and `f/prep-v3f.sh:1-34`): prep pattern = variables `O` (ops dir), `S` (snapshot), `PY`, `P` (pre), `A` (archive), `Q`/`T` (sheet qualification dirs), `ENVF=/root/.config/weak-solver/pjlab-token.env`; `cd $S`; offline tests `PYTHONPATH=$S $PY -m pytest -q -p no:cacheprovider tests/test_coevo5_*.py tests/test_weak_solver_probe.py > $O/tests.log 2>&1; echo EXIT $? >> $O/tests.log` and a `grep -q "^EXIT 0"` gate; zero-call SpreadsheetBench engine certification `PYTHONPATH=$S $PY -m scripts.replay_sheet_v6 qualify --output $Q --image sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790 ... --native-lock /root/continual-baselines-long-20261001-study/native.lock --engine-version v7` then `scripts/run_coevo5.py qualify-train-sheet` (in a background subshell `( ... ) &`); then `proxy_on >/dev/null 2>&1` (line 17) before the network steps (`build-archive`, probes, smoke). Every step writes `EXIT <code>` into its own log and the script stops on the first missing `EXIT 0` (`PREP-STOPPED <step>`).
F25 (verified, `/data/coevo5-20261019-v3-ops/f/prep-launch-v3.sh:1-17`): zero-call pre-launch = `smoke-summary --spec $P/smoke-3/smoke.json`, `make-manifest --out /data/coevo5-20261019-v3-run-manifest.json --root /data/coevo5-20261019-v3-run --sheet-qualification ... --engine-qualification ... --texts ... --smoke ... --archive ... --baseline-protocol /root/continual-fivebench-20261003-f-study/protocol.json --repo /root/continual-noskill-bcb-20260928-a --deepseek-env /root/.config/weak-solver/pjlab-token.env --gepa-source /root/continual-learning-env-20260928/gepa-source`, `check-baselines --manifest $M`, `consent --manifest $M --date 2026-10-19 --note "$(cat $O/consent-note.txt)"`; prints `PREP-LAUNCH-DONE` (log `/data/coevo5-20261019-v3-ops/f/prep-launch.log`: 19:25:37-19:25:58). make-manifest log: `{"manifest": ..., "run": "4bdd4cb3...", "root": ...}` + `EXIT 0`.
F26 (verified, `/data/coevo5-20261019-v3-ops/f/launch-v3.sh:1-12`, `f/run-chain-v3.sh:1-9`): launch refuses unless `^PREP-LAUNCH-DONE` is in `prep-launch.log` and refuses if `tmux has-session -t coevo5-v3-$C` already exists; then per chain `tmux new-session -d -s coevo5-v3-$C "bash -i $O/run-chain-v3.sh $C > $O/run-$C.log 2>&1"`. The chain script: `proxy_on >/dev/null 2>&1; cd $S; date "+START %F %T"; PYTHONPATH=$S $PY scripts/run_coevo5.py run --manifest $M --chain $C; echo EXIT $?; date "+END %F %T"`. `bash -i` is what makes `.bashrc` (and `proxy_on`) available inside tmux (F18), at the cost of the noise line `bash: cannot set terminal process group` in every log (filtered by `f/show-v3-run.sh:5`).
F27 (verified, `f/poll-v3-run.sh:1-7`, `f/poll-v3-first.sh:1-6`, `f/show-v3-run.sh:1-17`): monitoring = exit-0 pollers for background watchers (`grep -q "^EXIT " run-$C.log` or tmux session gone); a status printer that tails logs, lists the newest `unit.json`/`status.json` under `$R/$C`, `chain-*.json`, runs `progress-v3.py`, and prints the ledger via `Budget('$R/shared/ledger').snapshot()` with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.` from the snapshot dir; `first-responses-v3.py` confirms the first real model answers before the run is released (F8).
F28 (verified, `scripts/run_coevo5.py:238-311`): CLI subcommands `run, evaluate-unit, qualify-test-sheet, monitor, check-baselines, terminate, resume-ledger` (all `--manifest`; `run`/`terminate` also `--chain` from `CHAINS`), `qualify-train-sheet, build-archive, prepare-texts, import-texts, smoke-make, smoke, smoke-summary, make-manifest, consent, report, recover`. `make-manifest`/`smoke-make` default `--proxy`/`--research-proxy` = `GATEWAY` and `--workers 16`; `--deepseek-env` is required; `--router-env` optional.
F29 (verified, `/etc/docker/daemon.json` keys; `/data/docker/image/overlay2/repositories.json`): Docker 26.1.3 (`/usr/bin/docker`), data-root `/data/docker`, socket `/var/run/docker.sock` (root:docker 660), 0 entries in `/data/docker/containers` (no leftover containers). Images: `evolve-skill-native:smoke-20260928` -> `sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd` (= v3 `runtime.spreadsheetbench.image`, the solver-program runtime); `evolve-skill-sheet-recalc:20260930-offline` -> `sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790` (the LibreOffice recalculation/scoring engine used by `replay_sheet_v6 qualify`); `evolve-skill-python-base:20260930-b8fe4ce3655e` and `python:3.11-slim` -> the same `sha256:b8fe4ce3655e95f7f22c2a87d8e03a2f1f0cedc488a8e9adf18cc5a18cfdf401`.
F30 (verified, image config JSON under `/data/docker/image/overlay2/imagedb/content/sha256/`): native image: amd64, created 2026-09-28, `User 65534:65534`, `Entrypoint ["python"]`, `WorkingDir /tmp`, `PYTHONDONTWRITEBYTECODE=1`; its build ran `python -m pip install -r /opt/requirements-native.txt` and an import check `import openpyxl,pandas,numpy,sympy,antlr4,yaml,tqdm; from sympy.parsing.latex import parse_latex` -> **sympy, pandas, numpy, openpyxl ARE available inside the sandbox image even though they are not in the host env (F5)**. Repo pins (assumed to be what was built; inferred): `skillopt/continual_eval/runtime/requirements-native.txt:4-10` = antlr4-python3-runtime 4.11, sympy 1.13.3, PyYAML 6.0.2, tqdm 4.67.1, openpyxl 3.1.5, numpy 1.26.4, pandas 2.2.3. Recalc image: amd64, created 2026-09-30, `User 65534:65534`, `Entrypoint ["/usr/bin/python3", "/worker.py"]`, offline-installed `libreoffice-calc=4:25.2.3-2+deb13u7` and `python3-uno`.
F31 (verified, code): every coevo5/continual_eval container is started through the docker CLI via `subprocess` (no docker SDK): `_native(request, runtime)` (`skillopt/continual_eval/backends.py:153-212`) runs `docker run --pull=never --name continual-eval-<uuid> --network=none --read-only --user=65534:65534 --cap-drop=ALL --security-opt=no-new-privileges=true --pids-limit=128 --memory=<m>m --memory-swap=<m>m --cpus=<c> --ipc=private --shm-size=64m --no-healthcheck --log-driver=none --ulimit=nofile=256:256 --ulimit=core=0:0 --env CONTINUAL_EVAL_CONTAINER=continual-eval-native-v1 --env MPLCONFIGDIR=/tmp/matplotlib --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 --tmpfs=/tmp:rw,noexec,nosuid,nodev,size=256m,mode=1777 --workdir=/tmp --mount type=bind,source=<tmpdir>,target=/input,readonly --entrypoint=python <image> -I -B /input/worker.py`, then always `docker rm --force <name>`; an unconfirmed cleanup returns unknown `container_cleanup_unconfirmed`. Limits validated by `_runtime_limits` (`:119-129`): timeout 5..600 s (default 300), memory 256..32768 MiB (default 4096), cpus (0, 8] (default 1). Image must be digest-pinned and pass `docker image inspect` identity checks (`_image_ready`, `:132-150`). The in-container worker refuses to run unless `/.dockerenv` exists and `CONTINUAL_EVAL_CONTAINER` matches (`skillopt/continual_eval/native_worker.py:105`). Same pattern for the recalc engine (`skillopt/continual_eval/sheet_recalc.py:423-470`, `sheet_recalc_functions.py:247-295`, `sheet_passive_links.py:453-501`; worker guard `sheet_recalc_worker.py:40` with `SKILLOPT_SHEET_RECALC_CONTAINER=1`). Host-side SpreadsheetBench also needs `openpyxl` (readiness `backends.py:263-264`).

### 2.4 ALFWorld install, observed timings, timeouts (verified ~17:12 HKT)
F32 (verified, dl `ls`/`du`; `/root/continual-alf-prep-20260928/assets-complete.json`): ALFWorld data root = `/root/continual-alf-prep-20260928/data` (2.2 GB): `json_2.1.1/{train, valid_seen, valid_unseen, valid_train}` (task dirs: train 2,435, valid_seen 242, valid_unseen 85), `logic/{alfred.pddl, alfred.twl2}`, plus the three source zips from the alfworld GitHub releases 0.2.2/0.4.0 (sha256 recorded in `assets-complete.json`; `game_files: 4027`, `detector_downloaded: false`, `pretrained_agent_downloaded: false`, `model_calls: 0`). TextWorld-only (no THOR, no Mask R-CNN). Package: alfworld 0.4.2 + textworld 1.7.0 + fast_downward_textworld 20.6.4 in the venv site-packages (F3/F4).
F33 (verified): `ALFWORLD_DATA` is NOT set in any shell profile on dl (`grep` of `/root/.bashrc`, `/root/.profile`: no match). coevo5 sets it in-process from the manifest: `os.environ["ALFWORLD_DATA"] = setting.runtime["alfworld"]["alfworld_data"]` (`scripts/run_coevo5.py:75`; smoke: `skillopt/coevo5/smoke.py:323`) and an evaluation refuses to start if it differs (`skillopt/coevo5/evaluation.py:372-373`; backend: `skillopt/continual_eval/backends.py:669-673` "Set ALFWORLD_DATA to the frozen runtime path before launch"). The path is hard-coded in `skillopt/coevo5/protocol.py:355` (runtime) and `skillopt/coevo5/data.py:59`. Backend readiness requires packages `alfworld, gymnasium, yaml, numpy` and `<root>/logic/alfred.pddl` (`skillopt/continual_eval/backends.py:244-249`).
F34 (verified): ALFWorld config = repo file `skillopt/envs/alfworld/vendor/config_tw.yaml` (145 lines; `data_path: '$ALFWORLD_DATA/json_2.1.1/train'` :2, `eval_id_data_path ... valid_seen` :3, `eval_ood_data_path ... valid_unseen` :4, `logic.domain '$ALFWORLD_DATA/logic/alfred.pddl'` :9, `env.type 'AlfredTWEnv'` :13, `task_types [1..6]` :16, `expert_type "handcoded"` :18, `controller.type 'oracle'` :34, `max_nb_steps_per_episode: 50` :88/:121). Per episode the backend copies this config, narrows the dataset path to the single game's directory, and sets both `max_nb_steps_per_episode` to the frozen `max_steps` (`skillopt/continual_eval/backends.py:666-698`).
F35 (verified): each ALFWorld episode runs in its OWN `multiprocessing` "spawn" child (`class _AlfSession`, `skillopt/continual_eval/backends.py:605-663`; worker `skillopt.envs.alfworld.vendor.alfworld_envs._worker_loop`), with queue timeouts `min(120, runtime.timeout_seconds)` (v3: 60 s) and a bounded close (put close -> join 1 s -> terminate -> join 3 s -> kill -> join 2 s; failure raises "ALFWorld worker cleanup unconfirmed", which coevo5 treats as a pause-the-run outcome, registration row 3 `docs/handoff/coevo5-registration-20261016.md:197`). Concurrency of episodes is bounded globally by the `alfworld-episode` slot pool = 6 (F11), chosen for 7 CPUs / 15 GB (`skillopt/coevo5/protocol.py:324-326`). No measured per-episode RSS was found in the docs; "how many threads are safe" is therefore only evidenced as "6 ran for hours without a cleanup pause" in v3 (inferred from the completed chains, `docs/project-status.md:183`).
F36 (verified, stat-only timing of v3 TRAINING-side units with `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/celltimes.py`; never opened a cell file; `evaluation/`, `shared/test/` and any unit name containing "test" skipped). Unit wall time = `attempt-N/started.json` mtime -> `<unit>/unit.json` mtime; per-cell = `cells/<id>.claim` mtime -> `cells/<id>.json` mtime (includes slot waiting and client retries). Three chains shared 12 deepseek slots (solver `deepseek-v4-flash`, thinking disabled):

| chain / stage / unit | cells | wall (min) | cell median / p90 (s) |
| --- | --- | --- | --- |
| I-ds s1 SearchQA train | 400 | 15.1 | 4 / 123 |
| E-ds s1 SearchQA train | 400 | 11.2 | 5 / 122 |
| I-ds s1 SearchQA screen | 1,922 | 43.0 | 2 / 121 |
| E-ds s1 SearchQA screen | 2,510 | 56.3 | 2 / 70 |
| I-ds s2 OfficeQA train | 148 | 6.2 | 2 / 123 |
| E-ds s2 OfficeQA train | 148 | 2.5 | 3 / 30 |
| E-ds s2 OfficeQA screen | 1,168 | 20.8 | 3 / 42 |
| I-ds s3 LiveMath train | 200 | 7.8 | 6 / 85 |
| E-ds s3 LiveMath screen | 1,282 | 23.0 | 4 / 32 |
| I-ds s4 SpreadsheetBench train | 91 | 12.6 | 77 / 189 |
| E-ds s4 SpreadsheetBench train | 91 | 16.4 | 100 / 385 |
| I-ds s4 SpreadsheetBench screen / confirm | 872 / 872 | 44.9 / 49.7 | 12 / 121; 8 / 190 |
| I-ds s5 ALFWorld train | 114 | 53.5 | 290 / 785 |
| E-ds s5 ALFWorld train | 114 | 96.4 | 348 / 1,929 |
| I-ds s5 ALFWorld screen | 974 | 223.3 | 11 / 716 |
| (method role, GLM) prepare units | - | 1.4 - 35.3 | - |

  Test-side stage-0 evaluation is not timed here (forbidden paths); the docs record only "ALFWorld 测试评测最慢，约 20:44–02:00" for NoSkill-ds stage 0 (`docs/project-status.md:186`), i.e. ~5.3 h for its ALFWorld test panel (134 episodes, `TEST_SIZES`, `skillopt/coevo5/protocol.py:65`) while sharing slots with two other chains.
F37 (verified): the "OfficeQA 100 cells ~51 min" figure is the v3 SMOKE, not the formal run: `/data/coevo5-20261019-v3-pre/smoke-3/I-ds/s2/train/attempt-1` = 100 cells (50 items x 2), 18:09 -> 19:00 = 50.6 min, cell median 20 s but p90 2,410 s. The slowest cells' receipts (read field names/status only, no text) show `attempts: [{"error": "ReadTimeout", "seconds": 2400.0}, {"status": 200, "seconds": 34.3}]`: about a dozen requests hung simultaneously until the client read timeout and then succeeded in ~34 s on retry. Cause = `READ_TIMEOUT_SECONDS = 2400  # a 65,536-token reply took 10-19 minutes historically` (`skillopt/coevo5/protocol.py:92`), passed to every `Client` via `manifest._clients(...).make(model, max_tokens, read_timeout)` (`skillopt/coevo5/manifest.py:95-113`). In the formal run the same 148-cell OfficeQA train took 2.5-6.2 min. Lesson: for a non-reasoning solver a 40-minute read timeout turns one upstream stall into a 40-minute unit.
F38 (verified): other per-call constants that shape wall time: `MAX_RESENDS = 2`, `RESEND_COOLDOWN_SECONDS = 300` (`skillopt/coevo5/protocol.py:87-88`), client-internal retries 1+3 attempts with backoff (10, 30, 60) s / 429: (30, 90, 180) s (F15). Worst case for one undelivered call: 3 sends x (4 attempts x 2,400 s + backoff) -> hours; budget ledger counts only the last attempt's usage (F9).

### 2.5 Processes, tools, transfer, credential-file shape (verified ~17:16 HKT)

F39 (verified, `psutil` listing on dl): no tmux server is running (`/tmp/tmux-0/` exists, empty); load average ~1.0; 11.8 GB RAM available; `dockerd` up 164 h. **About 21 orphaned `multiprocessing.spawn` children plus 8 `resource_tracker` processes of `/root/continual-alf-prep-20260928/env/bin/python` are still alive** (ppid 1, sleeping, ages 11-22 h, RSS 104-148 MB each, roughly 2.7 GB in total), with cwd `/data/feasibility/D3`, `/data/feasibility/D3/r2` and `/data/feasibility/D14`, which are the overnight ALFWorld feasibility harnesses. I did not touch them. Two inferences: one ALFWorld-style spawn worker costs about 0.1-0.15 GB, so 6 episode slots need about 1 GB and the binding limit is CPU (7 cores), not RAM. And a route-B run's "no leftover ALFWorld worker" check (coevo5 registration §13.4, `docs/handoff/coevo5-registration-20261016.md:597`) would be ambiguous until someone with authority removes these.
F40 (verified): on dl, `/usr/bin/rsync`, `/usr/bin/tmux` and `/usr/bin/curl` exist (`/usr/local/bin/curl` belongs to uid 1001; auto-memory says it is broken). The Mac's `/usr/bin/rsync` is `openrsync: protocol version 29` and supports `--files-from`, `--exclude`, `--exclude-from`, `--chmod`, `--numeric-ids`, `--itemize-changes` and `--delete-*`. A dry-run pull through the bastion, `rsync -n -a -v -e "ssh -o BatchMode=yes -o ConnectTimeout=20" dl.dulin+root.ailab-datatools.ws@h.pjlab.org.cn:/data/coevo5-20261019-v3-ops/f/launch-v3.sh <scratch>/`, exited 0 and wrote nothing. So rsync works over the `h.pjlab.org.cn` bastion. Ownership is mapped by name: files copied from the Mac show `10250:50` = `dulin:staff` on dl (dl user `dulin` has uid 10250; `staff` has gid 50).
F41 (verified; booleans derived in-process, nothing printed from the file): in `/root/.config/weak-solver/elucid.env`, `ELUCID_CHAT_URL` is https, has no userinfo, no query or fragment, uses the default port, and its path ends with `/v1/chat/completions`. **Its host is NOT covered by the default `NO_PROXY` list** (F18). `ELUCID_MODEL == "deepseek-v4.1-flash-1017"` and `ELUCID_API_KEY` is non-empty. Consequence: under `proxy_on`, any env-honoring client (urllib, curl, the openai SDK) reaches the elucid host through the PJLAB gateway. The repo's `Client` would reach it only if `proxy=GATEWAY` is passed explicitly, because it sets `trust_env=False` (F15). Direct reachability without the gateway was not tested.
F42 (verified, names only): the BigModel/GLM credential file `/root/continual-noskill-bcb-20260928-a/.env` (mode 600, 168 B) holds `BIGMODEL_API_KEY`, `BIGMODEL_CHAT_URL` and `BIGMODEL_MODEL`.
F43 (verified): tmux naming conventions:
- older queues use `ae-<name>`, with exact-name targeting via `tmux kill-session -t "=名字"` (`docs/project-status.md:458,466`);
- coevo5 v3 chains use `coevo5-v3-<chain>` (`/data/coevo5-20261019-v3-ops/f/launch-v3.sh:9`);
- v3 prep/smoke used `coevo5-v3f-prep` (`docs/project-status.md:189`).

Every v3 tmux command runs `bash -i <script> > <log> 2>&1`, and the launcher refuses to start if the session already exists (F26).
F44 (verified by `ls`): run-root layout: `<root>/{<chain>/, shared/}`.
- `shared/` contains `baselines-checked.json`, `consent.json`, `host_only/`, `ledger/`, `slots/` and `test/`.
- `<chain>/` contains `chain.json`, `chain-complete.json` and `s0..s5/`.
- Each `s<k>/` holds units (`train`, `prepare`, `selftest`, `screen`, `confirm`, `merge`, `evaluation/<bench>`). Each unit holds `unit.json` and `attempt-N/`, which contains `started.json`, `cells/<cellid>.claim` (written at start), `cells/<cellid>.json` (the result) and `artifacts/<sha256>.json`.
- The smoke root `/data/coevo5-20261019-v3-pre/smoke-3/` holds `smoke.json`, `summary.json` and `I-ds/s0..s2`.
- Launch manifests sit beside the run root as `/data/coevo5-<date>-<ver>-run-manifest.json` (mode 600).
- The slot lock files are in `<root>/shared/slots/` (`skillopt/coevo5/manifest.py:149`).

Per-step training sizes: `TRAIN_ROLLOUT = {"searchqa": (200, 2), "officeqa": (74, 2), "livemath": (100, 2), "spreadsheetbench": (120, 1), "alfworld": (57, 2)}` (`skillopt/coevo5/protocol.py:60-61`). SpreadsheetBench actually ran 91 qualified items (F36). `TEST_SIZES = {"searchqa": 400, "officeqa": 172, "livemath": 125, "spreadsheetbench": 279, "alfworld": 134}` (`skillopt/coevo5/protocol.py:65`). The v3 totals were deepseek 139,024,462 tokens and GLM 7,804,250 (`docs/project-status.md:183`).
F45 (verified): `require(value, message)` raises `ValueError(message)` (`skillopt/continual_eval/core.py:30-32`). `safe_path(value)` refuses `..` and **any symlink in the path or its parents** (`skillopt/continual_eval/core.py:35-39`), and every coevo5 path passes through it. Route-B dirs must therefore be real paths, not symlinks. The interpreter path is a symlink (F3), but it is not passed through `safe_path`.

## 3. Interfaces an implementer would call or must replace

All entries below were verified by reading the code. Return shapes are as far as I read them.

| Interface | Signature / contract | Returns / raises / side effects | Route-B use |
| --- | --- | --- | --- |
| `skillopt.coevo5.calls.Slots` (`calls.py:39-122`) | `Slots(root, name, count, *, poll=0.5, sleep=time.sleep)`; `with s.hold() as index:`; `with s.hold_many(count) as indices:` | `ValueError` (via `require`) on a bad count or name. Creates `root/` and lock files `<name>.<i>.lock`, `<name>.gather.lock`, `<name>.many.lock` (mode 600). Locks are kernel `flock`, released when the process dies. | Reuse unchanged for cross-process pools: solver, GLM roles, docker sandbox, ALFWorld episodes. |
| `scripts.weak_solver_probe.Client` (`:227-257`) | `Client(repo, model, *, proxy, max_tokens, router_env=None, read_timeout=900, transport=None, route=None, route_env=None)`; `.call(system, user) -> receipt` | The receipt dict has `ok`, `status`, `attempts` (a list of `{status or error, seconds}`), `seconds`, `finish_reason`, `usage{prompt_tokens, completion_tokens, total_tokens}`, `usage_valid`, `returned_model`, `reasoning_chars`, and `response` on success. Failures carry `error_type` (`http_<code>`, `invalid_json`, `content_missing`, `empty_content`). Configuration errors raise `SystemExit`: model not allow-listed, proxy not approved, missing key. | Must be extended: add a model entry, an `elucid` route with its own credential reader, and a new receipt rule for reasoning (F15, F20). |
| `scripts.weak_solver_probe._read_env(path)` (`:115-123`) | parses `KEY=VALUE` lines and strips quotes | returns a dict; values stay in memory only | Reuse to read `/root/.config/weak-solver/elucid.env` by path. |
| `scripts.weak_solver_probe._validated_url(url, host, path, message)` (`:126-137`) | https, exact host, no userinfo/query/fragment, port 443, exact path | returns the url or raises `SystemExit(message)` | Reuse. The elucid host must be pinned (manifest) without printing the key. |
| `skillopt.coevo5.manifest._clients(config)` (`:95-113`) | requires `config["proxy"] in (None, GATEWAY)` and `route in (None, "pjlab_token")`; returns `make(model, max_tokens, read_timeout)`, a client cached per key | `ValueError` from `require` | Replace or generalize the route check and the model-to-route mapping. |
| `skillopt.continual_eval.backends._native(request, runtime)` (`:153-212`), `_image_ready(runtime)` (`:132-150`), `_runtime_limits(runtime)` (`:119-129`) | hardened `docker run` of `native_worker.py` on a digest-pinned image; `runtime` keys `image`, `timeout_seconds`, `memory_mb`, `cpus` | Returns a result dict or `_unknown(reason)` (`docker_unavailable`, `pinned_image_or_daemon_unavailable`, `image_inspection_mismatch`, `container_cleanup_unconfirmed`, `native_timeout`, `native_execution_unavailable`, `invalid_native_receipt`). Writes a temp dir under the system tmp and always runs `docker rm --force`. | Pattern to copy for sandboxed procedures. The worker script itself is benchmark-specific and needs a route-B worker. |
| `skillopt.continual_eval.backends._new_alfworld(public, runtime)` / `_AlfSession` (`:605-698`) | `_AlfSession(config, game, split, seed, timeout)`; `.reset() -> (obs, None, [info])`; `.step([action]) -> (obs, None, scores, dones, [info])`; `.close()` | `ValueError` if `ALFWORLD_DATA` differs from the runtime or the game file is outside the root. `RuntimeError("ALFWorld worker cleanup unconfirmed")`. Spawns one process per episode. | Reuse for environment stepping. The solve loop `_solve_alfworld` (`:715-783`) must be wrapped or replaced by the route-B shell, which runs procedures before and after each model call. |
| `skillopt.continual_eval.backends.readiness(benchmark, runtime=None)` (`:230-283`) | per-bench readiness | `{"status": "ready" or "unsupported", "reason": ...}`. SpreadsheetBench also runs a docker probe. | Reuse as a pre-launch check. |
| `scripts/run_coevo5.py` CLI (`:238-311`) | subcommands listed in F28 | each writes `EXIT`-checked logs via the ops scripts | Template for a `scripts/run_execskill.py` CLI. Do not reuse it: its `VERSION`, `CHAINS` and manifest keys are coevo5-v3. |
| `skillopt.coevo5.budget.Budget(root, *, poll=5.0, sleep=time.sleep)` (`budget.py:120-121`); `.snapshot()` (`:344`) | ledger reader used by `show-v3-run.sh:11-16` | returns a dict of scopes (`settled`, ...) and `halted` | Reuse if route B keeps the same ledger (another area covers this). |
| ops shell scripts (F24-F27) | `prep-*.sh`, `prep-launch-*.sh`, `launch-*.sh`, `run-chain-*.sh`, `poll-*.sh`, `show-*.sh` | `EXIT <code>` markers, refusal checks, tmux | Copy, rename and re-path (recipe §7). |

## 4. Reusable unchanged for route B vs. must be generalized

Reusable unchanged:
- The python env `/root/continual-alf-prep-20260928/env/bin/python` (3.11.16) for the host side: alfworld 0.4.2, textworld 1.7.0, openpyxl 3.1.5, numpy 2.4.6, httpx 0.28.1, PyYAML, pytest (F3-F4).
- Docker 26.1.3 with the three pinned images. The native image already contains sympy, pandas, numpy and openpyxl, so sandboxed procedures can use them (F29-F30).
- The `Slots` file-lock pools (F12).
- The credential-by-path pattern (`_read_env`, `_validated_url`) (F16).
- The `GATEWAY` constant and the explicit-proxy client (`trust_env=False`) (F15).
- The ALFWorld data root and vendor config (F32-F34) and the `_AlfSession` process wrapper (F35).
- The hardened `docker run` flag set (F31).
- The snapshot hashing convention: a Mac-made sha list plus a dl-recomputed list compared with `cmp` (F23).
- The prep, launch and poll script skeletons with `EXIT` markers and tmux refusal checks (F24-F27).
- The run-dir layout idea `<root>/<arm>/s<k>/<unit>/attempt-N/cells` (F44).

Must be generalized, and why:
1. `SLOTS` (`skillopt/coevo5/protocol.py:331`) is keyed by model name. `"deepseek-v4-flash": 12` was tuned for the PJLAB token route, and the new solver `deepseek-v4.1-flash-1017` on the elucid gateway has no measured safe concurrency. `spreadsheet-native: 3` and `alfworld-episode: 6` assume v3's load. Route B adds shell-side procedure execution, possibly docker per call, which competes for the same 7 CPUs.
2. `SOLVER_MAX_TOKENS` (`protocol.py:327`) is keyed by model, and the new model is missing.
3. Routes:
   - `DEEPSEEK_ROUTE = "pjlab_token"` (`protocol.py:330`) is fixed;
   - `manifest._clients` accepts only that route and only for `deepseek-v4-flash` (`manifest.py:99-110`);
   - `Client` sends any explicit route to `pjlab_credentials` (`weak_solver_probe.py:238-243`);
   - `MODELS` and `ROUTES` (`:77-88`) lack `deepseek-v4.1-flash-1017`;
   - `_validated_url` only knows the BigModel, free-router and PJLAB hosts.

   A new route needs its own reader for `ELUCID_CHAT_URL`/`ELUCID_API_KEY`/`ELUCID_MODEL`, a host pin and a response-model allow-list.
4. The thinking rule: v3 sends `thinking: disabled` and treats any reasoning text as `thinking_mismatch`, i.e. undelivered (F9). The elucid route returns `reasoning_content` even when `thinking` is disabled (F20), so this rule would reject every call. It must be replaced, for example by recording reasoning tokens rather than rejecting them, and the receipt's `returned_model` check must expect `deepseek-v4.1-flash-1017`.
5. `READ_TIMEOUT_SECONDS = 2400` (`protocol.py:92`) was sized for 65k-token GLM replies. With a fast non-reasoning solver, one stalled upstream batch cost 40 minutes in the v3 smoke (F37). Route B should register a solver-specific timeout.
6. The ALFWorld data path is hard-coded in `protocol.py:355` and `data.py:59`, and is set in-process by `run_coevo5.py:75`. It is fine on dl but should be manifest-bound in the new package.
7. Prep scripts run `tests/test_coevo5_*.py` and the SpreadsheetBench re-certification bound to a snapshot. Route B needs its own test glob and its own (zero-call) engine certification on the new snapshot, if it scores SpreadsheetBench with `qualified_lo_recalc_v7_v1`.
8. The manifest key set (`manifest.py:35`), the `VERSION` strings and the `workers = 16` default (`scripts/run_coevo5.py:276,288`) are all protocol-bound. Route B needs a new version and a new output dir, per AGENTS.md.
9. The host env lacks `sympy`, `pandas`, `scipy` and the docker SDK (F5). Any host-side generator or verifier that uses sympy (for example LiveMath variant checking, as D6 did) must either run inside the native image (sympy 1.13.3 per the pins) or use a pinned `pip install --target <package>/pylib` from the internal mirror (D6 used sympy 1.14.0). The two versions differ, so pick one and pin it in the manifest.

## 5. Gaps and risks for route B in this area

- **Ambient OpenAI credentials.** Every `bash -i`/`bash -ic` shell exports `OPENAI_API_KEY` and `OPENAI_BASE_URL` (OpenDataLab Codex block, `.bashrc:147-151`) and turns the proxy on automatically (`.bashrc:148`). A route-B client built on the `openai` SDK without an explicit `api_key`/`base_url` would silently call the wrong service. Any `env`/`os.environ` dump in a log leaks a key. Recommendation: `unset OPENAI_API_KEY OPENAI_BASE_URL` in the run script, and never log the environment.
- **Plain non-interactive ssh has no proxy and no `proxy_on`** (`.bashrc:6`). Env-honoring tools (pip, curl, urllib) then go direct. The repo `Client` ignores env anyway (F15). Mixing the two kinds of client in one process gives two different network paths.
- **The elucid gateway is uncharacterized:** concurrency limits, rate limits, error mix, whether `seed` or `temperature` are honored, whether usage is metered against a budget, and whether reasoning is always on (F20; 5 calls only). v3 probed "12 concurrent" before launch (`docs/handoff/coevo5-registration-v3-delta-20261019.md:303`); route B must do the same on elucid before fixing its slots.
- **Leftover processes.** About 2.7 GB of orphaned feasibility workers are alive (F39). They are harmless for RAM but confuse the leftover-worker checks. The owner should decide who removes them; I did not.
- **CPU budget.** 7 cores: 6 ALFWorld episode processes plus 3 SpreadsheetBench containers plus the LibreOffice recalc container plus the Python driver threads already saturate it. Procedure execution in docker costs one container start per run. Cost per container start is not measured here (inferred risk). If procedures run on every ALFWorld step (about 30 steps per episode), docker-per-call may dominate wall time. A long-lived per-episode sandbox or an in-process restricted runner is a design decision.
- **Disk.** `/` has 30 GB free (71% used); `/data` has 395 GB free. Keep all route-B outputs on `/data`. The docker data-root is already `/data/docker`.
- **`/data/skillopt-work` contains the Mac `.env`** (F22). Never use it as an rsync source or publish it. Snapshot from the Mac with `.env` excluded, and verify that it is absent.
- **The `/data/execskill-ops/` name is taken** by another agent's probe (F2). The new package should use dated names (`/data/execskill-20261021-*`), not that dir.
- **The ledger is a lower bound** (client-internal retries keep only the last attempt's usage, F9). The same applies on elucid unless the client changes.
- **Stale docs.** `docs/project-status.md` §6.2 describes the old machine (F10). An implementer following it would use wrong hosts and paths.
- **Unmeasured timings.** Test-side timings were not measured here (forbidden paths). The only test-side figure is NoSkill-ds's ALFWorld test pass at about 5.3 h while sharing slots (F36). Design-v0 budgets test reads per step, so the wall time of a step is dominated by ALFWorld episodes (training median 290-348 s per episode under contention; F36).
- **`safe_path` refuses symlinked paths** (F45). Do not place packages under symlinks.

## 6. Open questions for the designer

1. Should the elucid route be bound to the PJLAB gateway `http://httpproxy-headless.kubebrain.svc.pjlab.local:3128`? I recommend it: it is credential-free, already approved, and its host is outside NO_PROXY (F41). Or is direct egress wanted? Per AGENTS.md, any other proxy destination needs explicit review.
2. What concurrency should the elucid solver pool have (12 like v3?) and what read timeout (for example 300-600 s instead of 2400 s)? Both need a pre-launch probe with error-rate and latency readout.
3. How should reasoning be treated? Accept `reasoning_content` and count `completion_tokens_details.reasoning_tokens`, or keep trying `thinking: disabled`? In the sibling probe, the one call that sent `thinking: {"type": "disabled"}` still returned reasoning (14 reasoning tokens), and all 4 successful calls carried `reasoning_content` (F20).
4. Where do executable procedures run: in the native docker image per call, in a per-episode long-lived container, or in-process with restrictions? This decides the slot design and the CPU budget.
5. Which sympy should host-side generators and verifiers use: the container's 1.13.3, or a pinned `--target` install like D6's 1.14.0? Who installs it? CLAUDE.md says never sudo-install. A `pip --target` into the package dir is not a system install, but it is an environment change to register.
6. Who removes the orphaned D3/D14 workers before a route-B launch?
7. Does route B reuse coevo5's SpreadsheetBench engine qualification and test-side qualification (`shared/test/`), or re-certify on the new snapshot as v3 did per snapshot?
8. Process note: the relayed user request that triggered this workflow asked for a different task (a subagent summarising past experiments for the best-looking numbers, without disturbing the main coding task). This survey is the computed route-B step only. I did not do that summary, and I did not modify anything the main coding task uses.

## 7. Launch recipe for a new package `/data/execskill-20261021-source` (credential-free)

Mirrors the v3 procedure (F23-F27). All names are new; nothing existing is overwritten. `scripts/run_execskill.py` and `tests/test_execskill_*.py` are placeholders for whatever the implementer names the route-B CLI and tests. The local repo currently has `.git`, `data/`, `outputs/` and a `.env` (mode 600) at its top level, so all four must be excluded (verified with `ls`).

```bash
# ===== 0. Mac: names (no secrets anywhere below) =====
REPO=/Users/dulin/Documents/Paper/SkillOpt
DL=dl.dulin+root.ailab-datatools.ws@h.pjlab.org.cn
SSHC="ssh -o BatchMode=yes -o ConnectTimeout=20"
SNAP=/data/execskill-20261021-source        # frozen code snapshot; never edited after step 4
OPS=/data/execskill-20261021-ops            # scripts, sha lists, logs (NOT /data/execskill-ops: another agent's probe dir)
# later: PRE=/data/execskill-20261021-pre  RUN=/data/execskill-20261021-run  MAN=/data/execskill-20261021-run-manifest.json
LOCAL=/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/launch
mkdir -p "$LOCAL"

# ===== 1. refuse to reuse an existing snapshot/ops dir =====
$SSHC $DL "test ! -e $SNAP && test ! -e $OPS" || { echo "REFUSE: $SNAP or $OPS already exists"; exit 1; }

# ===== 2. Mac: freeze the file list + sha256 (v3 coverage: scripts/ skillopt/ tests/; add configs/ if route B reads it) =====
cd "$REPO" && find scripts skillopt tests -type f ! -path '*/__pycache__/*' ! -name '*.pyc' ! -name '.DS_Store' -print \
  | LC_ALL=C sort > "$LOCAL/files.txt"
cd "$REPO" && tr '\n' '\0' < "$LOCAL/files.txt" | xargs -0 shasum -a 256 > "$LOCAL/source.sha256"   # "<sha>  <path>", same as GNU sha256sum
wc -l "$LOCAL/source.sha256"

# ===== 3. Mac -> dl: dry-run leak check, then copy (openrsync on the Mac; rsync over the bastion works, F40) =====
EXC="--exclude=/.git --exclude=/outputs --exclude=/data --exclude=.env --exclude=__pycache__ --exclude=*.pyc --exclude=.pytest_cache --exclude=.ruff_cache --exclude=.DS_Store"
rsync -n -a -i $EXC -e "$SSHC" "$REPO/" "$DL:$SNAP/" | grep -E '( |/)\.env$| \.git/| outputs/| data/' \
  && { echo "LEAK-CHECK-FAILED: excluded paths would be copied"; exit 1; }
rsync -a $EXC -e "$SSHC" "$REPO/" "$DL:$SNAP/"
$SSHC $DL "mkdir -p $OPS"
rsync -a -e "$SSHC" "$LOCAL/source.sha256" "$DL:$OPS/source.sha256"

# ===== 4. dl: recompute on the snapshot, compare byte-for-byte, confirm no .env =====
$SSHC $DL "cd $SNAP && find scripts skillopt tests -type f ! -path '*/__pycache__/*' ! -name '*.pyc' ! -name '.DS_Store' -print \
  | LC_ALL=C sort | tr '\n' '\0' | xargs -0 sha256sum > $OPS/source-expected.sha256 \
  && cmp $OPS/source.sha256 $OPS/source-expected.sha256 && echo SNAPSHOT-HASH-OK; \
  echo env-files: \$(find $SNAP -name .env | wc -l)"          # must print SNAPSHOT-HASH-OK and env-files: 0
```

Prep script (written on the Mac, copied to `$OPS`, run in tmux under `bash -i` so `.bashrc` and `proxy_on` exist; F18, F26):

```bash
cat > "$LOCAL/prep.sh" <<'EOS'
O=/data/execskill-20261021-ops; S=/data/execskill-20261021-source; PY=/root/continual-alf-prep-20260928/env/bin/python
export PYTHONDONTWRITEBYTECODE=1                 # keep the snapshot free of __pycache__
unset OPENAI_API_KEY OPENAI_BASE_URL             # .bashrc:149-150 exports an unrelated key into every bash -i shell
cd $S
date "+START %F %T"
PYTHONPATH=$S $PY -m pytest -q -p no:cacheprovider tests/test_execskill_*.py tests/test_weak_solver_probe.py > $O/tests.log 2>&1
echo EXIT $? >> $O/tests.log
grep -q "^EXIT 0" $O/tests.log || { echo PREP-TESTS-FAILED; date "+END %F %T"; exit 1; }
proxy_on >/dev/null 2>&1                         # only matters for env-honoring tools; the repo Client gets proxy=GATEWAY explicitly
# small solver probe (a few calls; concurrency/error-rate readout before fixing slots), credential passed BY PATH:
PYTHONPATH=$S $PY scripts/run_execskill.py probe --solver-env /root/.config/weak-solver/elucid.env \
  --proxy http://httpproxy-headless.kubebrain.svc.pjlab.local:3128 --out $O/probe > $O/probe.log 2>&1
echo EXIT $? >> $O/probe.log
for f in tests probe; do grep -q "^EXIT 0" $O/$f.log || { echo "PREP-STOPPED $f"; date "+END %F %T"; exit 1; }; done
date "+END %F %T"
echo PREP-DONE
EOS
rsync -a -e "$SSHC" "$LOCAL/prep.sh" "$DL:$OPS/prep.sh"
$SSHC $DL "tmux has-session -t '=execskill-prep' 2>/dev/null && echo REFUSE-SESSION-EXISTS \
  || tmux new-session -d -s execskill-prep 'bash -i $OPS/prep.sh > $OPS/prep.log 2>&1'"
```

Per-arm run script and launcher (same shape as `run-chain-v3.sh` / `launch-v3.sh`):

```bash
cat > "$LOCAL/run-arm.sh" <<'EOS'
A=$1
O=/data/execskill-20261021-ops; S=/data/execskill-20261021-source; PY=/root/continual-alf-prep-20260928/env/bin/python
M=/data/execskill-20261021-run-manifest.json     # binds: solver env PATH, GLM repo path, gateway, image digests, slots, ALFWORLD_DATA
proxy_on >/dev/null 2>&1
unset OPENAI_API_KEY OPENAI_BASE_URL
export PYTHONDONTWRITEBYTECODE=1
cd $S
date "+START %F %T"
PYTHONPATH=$S $PY scripts/run_execskill.py run --manifest $M --chain $A     # sets ALFWORLD_DATA in-process from M (as run_coevo5.py:75)
echo EXIT $?
date "+END %F %T"
EOS
cat > "$LOCAL/launch.sh" <<'EOS'
O=/data/execskill-20261021-ops
grep -q "^PREP-LAUNCH-DONE" $O/prep-launch.log 2>/dev/null || { echo "LAUNCH-REFUSED: prep-launch not done"; exit 1; }
for A in "$@"; do tmux has-session -t "=execskill-$A" 2>/dev/null && { echo "LAUNCH-REFUSED: execskill-$A exists"; exit 1; }; done
for A in "$@"; do
  tmux new-session -d -s execskill-$A "bash -i $O/run-arm.sh $A > $O/run-$A.log 2>&1"
  date "+LAUNCHED $A %F %T"
done
tmux ls | grep execskill-
EOS
cat > "$LOCAL/poll-run.sh" <<'EOS'
# exit 0 when any watched arm's process has ended (EXIT marker) or its tmux session is gone
O=/data/execskill-20261021-ops
for A in "$@"; do
  grep -q "^EXIT " $O/run-$A.log 2>/dev/null && exit 0
  tmux has-session -t "=execskill-$A" 2>/dev/null || exit 0
done
exit 1
EOS
rsync -a -e "$SSHC" "$LOCAL/run-arm.sh" "$LOCAL/launch.sh" "$LOCAL/poll-run.sh" "$DL:$OPS/"
# after a zero-call prep-launch (make-manifest, checks, consent) has printed PREP-LAUNCH-DONE into $OPS/prep-launch.log:
$SSHC $DL "bash $OPS/launch.sh <arm1> <arm2>"
# confirm the first real model responses (status 200, echoed model deepseek-v4.1-flash-1017) BEFORE leaving it running (AGENTS.md)
```

Credential sourcing (`/root/.config/weak-solver/elucid.env`; names `ELUCID_CHAT_URL`, `ELUCID_API_KEY`, `ELUCID_MODEL`; mode 600; plain `NAME=value` lines without `export`):
- **Preferred: pass the path, read it in-process.** Use `--solver-env /root/.config/weak-solver/elucid.env` with a `_read_env`-style reader (`scripts/weak_solver_probe.py:115-123`). The manifest records only the path. Values never reach argv, the environment, tmux command strings or logs. This is how v3 bound `pjlab-token.env` (`--deepseek-env`, F13/F25).
- **Only if a tool insists on environment variables:** run `set -a; . /root/.config/weak-solver/elucid.env; set +a` inside the run script. A plain `. file` does NOT export to child processes, because the file has no `export`. Never combine it with `set -x`, and never dump `env`. The values become visible in `/proc/<pid>/environ` and are inherited by subprocesses, including the docker CLI, though not by containers unless passed with `--env`.
- **Proxy:**
  - The repo `Client` ignores shell proxy variables (`trust_env=False`), so pass `proxy=http://httpproxy-headless.kubebrain.svc.pjlab.local:3128` explicitly and record it in the manifest (AGENTS.md: bind the proxy to the protocol identity).
  - Env-honoring tools need `proxy_on` in the same shell: `bash -ic 'proxy_on >/dev/null 2>&1; <cmd>'`. Always redirect its output, because it echoes the proxy values.
  - A plain `ssh dl 'cmd'` has no proxy (F18).

Log and output locations, following the v3 naming:

| What | Path |
| --- | --- |
| sha lists | `$OPS/source.sha256`, `$OPS/source-expected.sha256` |
| prep | `$OPS/{tests.log, probe.log, prep.log}` |
| zero-call pre-launch | `$OPS/{prep-launch.log, make-manifest.log, check-*.log, consent.log}` |
| per arm | `$OPS/run-<arm>.log`, which starts with the harmless `bash: cannot set terminal process group` line and ends with `EXIT <code>` and `END <time>` |
| smoke | `/data/execskill-20261021-pre/smoke/` |
| run root | `/data/execskill-20261021-run/<arm>/s<k>/<unit>/attempt-N/...` and `/data/execskill-20261021-run/shared/{ledger,slots,...}` |
| manifest | `/data/execskill-20261021-run-manifest.json` (mode 600, as v3) |
| tmux sessions | `execskill-prep`, `execskill-<arm>` |

Stopping: `tmux kill-session -t "=execskill-<arm>"`, only on an owner decision. Pauses wait for the owner and nothing auto-resumes (v3 rule, `docs/handoff/coevo5-registration-v3-delta-20261019.md:320-321`). For monitoring, run `poll-run.sh` from a sparse background watcher (about 30 min) instead of polling continuously.
