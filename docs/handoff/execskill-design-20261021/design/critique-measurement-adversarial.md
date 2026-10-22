# Adversarial critique (lens 2: engineering / runtime) of spec-measurement.md

Target: /private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/design/spec-measurement.md
Critic: lens 2 (engineering and adversarial: try to break the runtime). Read-only on repo and dl.
Status: DONE 2026-10-21 about 19:45 HKT. This is the second pass: the first pass was interrupted, and this pass resumed it at 19:21 HKT with dl reachable (aTrust on).

Verdict: **needs_revision** (0 fatal, 22 major M1-M22, 17 minor m1-m17). Nothing found is fatal: every defect has a
registrable fix before the smoke. But several of them would crash or hang a unit. Others let model-written code, the
action canonicaliser or the placebo carry effects that the spec says are impossible.

Session note:
- The first pass could not reach dl ("Connection closed by 10.102.254.2 port 22").
- In the second pass dl was reachable (read-only, BatchMode). I verified the probe-2 log (K1) and the D3
  `parse`/`canonical` source there. Section G lists what was verified and what was not.
- Every repository line cited below was re-read locally on 2026-10-21.

## 给负责人的摘要（白话）

1. 总体判断：这份"测量优先"的稿子在统计设计上很扎实，但作为可运行的系统还有不少漏洞，需要修改后才能冒烟。
   我没有找到"推翻整个方案"的致命问题，但找到 22 个"重大"问题（编号 M1–M22）和 17 个"次要"问题（编号 m1–m17）。不修的话，会出现三类后果：运行中途卡死或整体停机；
   模型写的程序或固定的"动作纠正器"带进来稿子声称不可能有的效果；冒烟测试查不出这些问题。
   （"冒烟"指正式试点前的小规模检查，"试点"指先做两个 bench 的小规模正式运行。）
2. 最要紧的五条：
   - **账本会被一条超长回答整体叫停。** 新接口不执行"回答长度上限"（max_tokens）。稿子说"超过上限两倍才停机"，但
     又说直接沿用冻结的记账代码；冻结代码只要超过上限一次就让所有运行停下（ledger.py:67）。两句话互相矛盾，
     必须写清楚用哪一种。
   - **"格式护栏"并没有真的挡在可学习部分之外。** 过程往提示里加的是自由文字，可以写"请用 JSON 回答"这类话。
     稿子的检查只拦字面上的答案标签和代码块，挡不住这种写法。昨夜 E4、E9 测到的 −9.5 到 −33 分，正是这类格式冲突造成的。
   - **ALFWorld 的"动作纠正器"会替模型挑动作。** 模型的回答对不上合法命令时，它会选"回答里最先提到的合法命令"。
     这其实是在修改模型的答案。D3 实测：带状态记录的组有 41% 的步靠它纠正，对照组只有 13%。所以"每组都装了它就公平"
     这个理由不成立。我在开发机上核对了它的源代码：它在整段回答里找命令。所以模型写"柜子 1 是空的，不要再去柜子 1"
     却没写对标签时，它反而会执行"去柜子 1"。
   - **暂停后的重做和"每道题只用一次"互相冲突。** 稿子规定已登记的题不能再派发，又规定暂停后整个单元重做。照字面执行，
     重做根本无法进行。
   - **沙盒里的程序能把运行搞乱。** "沙盒"指隔离运行模型所写代码的容器。按现在的写法会有三种情况：程序里一句 print 就会
     打乱进程间的通信；Python 每次启动的随机化会让同一程序在不同进程里输出不同；常驻进程会把上一道题的状态带到下一道题。
     建议改成"每次请求从预热好的进程分叉出一个干净子进程"，ALFWorld 一局内的状态明确地传进传出。
3. 考官一侧（"考官"是写检测器和出题程序的模型角色）有两条规则可以被轻易满足。一条是检测器：ALFWorld 失败的局几乎都走满
   50 步，看步数就能"检测失败"。另一条是回放测试：工程师自己写被测程序，也自己写判定条件，判定条件可以永远返回"通过"。
   这两条都需要改成工程师和考官控制不了的检查。
4. 冒烟测试只在"只有任务卡"那一组上查格式，从没让带过程的组、带"精确计算"二次调用的组真正调用一次新接口。
   v2、v3 冒烟抓到过的"缺答案标签、格式率不对"这类问题，在新管线里恰恰最可能来自过程本身，现在的冒烟查不出来。
5. 另外两条容易被忽视的问题：
   - **"精确计算"的第二次调用没有写死的提示文字。** "精确计算"指过程让做题模型写一个算式，由固定代码算出结果，
     再把结果交给模型问一次。稿子没写第二次问话的原文。安慰剂组收到的是"[数值已隐藏]"这类字样，模型可能因此拒答或
     答偏格式（"安慰剂组"指占同样位置、做同样次数调用、但不给有用信息的对照组）。这样新包"胜过安慰剂"就变得很容易，
     这个对照起不到作用。建议把第二次问话原文登记下来，安慰剂只把数值换成"未计算"，并在冒烟里实测两组的格式。
   - **"运行清单"没有写清要固定哪些东西。** "运行清单"（manifest）指开跑前锁定的代码、镜像、数据和接口设置的指纹。
     新接口默认是开着推理的，只要少传一个参数，模型的工作方式就会悄悄改变。沙盒镜像里的库版本目前只是推断，没有实测。
     建议登记清单的每一项，每个单元开跑前零调用核对一遍。
   - **协议身份基本守住了。** 新的版本名、新的输出目录都与 v3 分开，v3 的冻结文件也不改动。只有一处没写明：
     三个直接沿用的模块悄悄用了 v3 的几个常数，即重发次数、调用失败后的等待时间和预扣额度。其中等待时间默认是 v3
     的 300 秒，而不是稿子写的 60 秒。这要在清单里写明，并在代码里显式传入 60 秒（m17）。
6. 稿子里最值得保留的设计：先在冒烟里实测再定截断规则；第一步父版本等于任务卡，正好白得一个噪声底检查；
   "壳"没有改写回答的通道，否决只做提示、不替模型改动作；登记前先写好的同文本对照和各种"如实报告"规则；
   测试时加"只给文字说明"的一组，直接检验代码形式和文字形式哪个迁移得好。完整清单在文末。

## Findings (for implementers; English)

Severity scale: **fatal** = invalidates the protocol or makes it unrunnable as registered; **major** = would produce a
crash/hang, a silent bias, an unfalsifiable rule or a contradiction that must be resolved before the smoke;
**minor** = clarity, cost or reporting gap.

### A. Endpoint, ledger and decision table

**M1 (major) — The 2x completion bound contradicts the unchanged ledger, and two truncation rules overlap.**
- Quote: §0 "Import unchanged (protocol-free): `coevo5.{budget, ledger, calls, outcomes, ...}`". §3.1:
  "`completion_tokens − (reasoning_tokens or 0) ≥ max_tokens` ... → truncated (completion-aware fail);
  `max_tokens < completion ≤ COMPLETION_BOUND` → flag `over_nominal`, counted, delivered; `completion >
  COMPLETION_BOUND` → `AssumptionBroken`". §8.4 "halt on completion > 2 × max_tokens".
- Why it is wrong:
  - The unchanged `ledger.settle` breaks the assumption at `completion > max_tokens`
    (skillopt/coevo5/ledger.py:67). Here `max_tokens` is the Endpoint's own value, which is used for the reservation,
    the settlement and the cell record alike (skillopt/coevo5/calls.py:150-161).
  - Imported unchanged, the first reply above the nominal cap therefore halts every unit on the ledger. The gateway
    is known not to enforce the cap: 21 tokens came back at max_tokens 2 (docs/project-status.md:14).
  - The two receipt rules contradict each other. A 9,000-token reply with reasoning 0 at max_tokens 8,192 is
    "truncated → fail" (9,000 − 0 ≥ 8,192) and also "over_nominal → delivered, scored". P6 (§4.9) says it is scored as
    delivered.
  - The spec pre-registers no branch for the case where S-E4 shows the cap is NOT enforced with reasoning off. In
    that case runaway replies are the expected failure mode: in D3, 2 of 3 logged tracker episodes died of runaway
    replies under the 32k cap (FD/D3/critic-result.json:4 item 2).
- Fix:
  - (a) State the mechanism: `Endpoint(max_tokens=COMPLETION_BOUND)` for reservation and settlement, with
    `Client(max_tokens=nominal)` for the request body. Record both values in every send. `configuration()` digests
    both.
  - (b) Choose ONE rule. Either a reply with visible content ≥ nominal max_tokens is a completion-aware fail
    (`over_nominal_truncation`), or it is delivered. Then delete the other rule.
  - (c) Pre-register both S-E4 branches. If the cap is enforced: bound = nominal + a reasoning margin. If it is not
    enforced: bound = the provider's hard output limit, measured in the smoke with an uncapped long-generation
    prompt. Then over-nominal replies are never a halt; the halt is kept for prompt-side breaches only.

**M2 (major) — `outcomes` is both "imported unchanged" and "copied with new rows"; `reasoning_mismatch` would not be
resent.**
- Quote: §0 lists `outcomes` under "Import unchanged". §4.9 "Decision-table rows added to the copied `outcomes`
  (A6). Inserted before v3 row 11". §3.1 "`reasoning_mismatch` (undelivered → resend → infrastructure unknown, like
  v3's `thinking_mismatch`, outcomes.py:66-67)".
- Why it is wrong:
  - The frozen `UNDELIVERED_ERRORS` contains `thinking_mismatch` but not `reasoning_mismatch`
    (skillopt/coevo5/outcomes.py:66-67).
  - The imported `Recorder` resends only when `outcomes.undelivered(receipt)` is true (calls.py:268-279, via
    outcomes.py:182).
  - So, as registered, a reasoning-on reply is never resent. It lands in row 11 "unclassified" and is counted as
    infrastructure (outcomes.py:304). That breaks P5 and G4's "after resends".
  - P4 (REEXECUTE on sandbox failure) and the "procedure_fault" reasons equally need a copied table. An unknown
    reason string from the shell is treated as infrastructure by the frozen table (coevo5-infra G2).
- Fix:
  - Copy `outcomes` into `skillopt/execskill/outcomes.py`, re-exporting (not redefining) the coevo5 exception classes.
  - Add `reasoning_mismatch` to the copied UNDELIVERED set.
  - Make P1–P3 logging-only (they never change a verdict). Add P4 as an explicit row.
  - Add a unit test: a synthetic reasoning-on receipt is resent twice and then becomes unknown(infrastructure).

**M3 (major) — Determinism cannot hold across worker processes: `python -I` turns on str-hash randomisation that
cannot be switched off.**
- Quote: §1.5 "`python -I -B /worker/worker.py`" and "Determinism: ... a re-execution must reproduce identical
  requests ...; replay runs every procedure twice and compares output hashes". §9 S-X2 "every smoke procedure
  executed twice on 50 views → identical output hashes".
- Why it is wrong:
  - `-I` implies `-E`, so PYTHONHASHSEED is ignored and each process gets a random str-hash seed (Python docs,
    command-line options).
  - Any procedure that iterates over a `set` of strings produces process-dependent order. Examples: admissible
    commands, receptacle names, table headers. Some sympy outputs also depend on the hash order.
  - Running "twice" inside one worker hides this. The router pre-pass (§1.5), the solve, the withholding twin and a
    REEXECUTE in a fresh worker then send different notes. The REEXECUTE `require(_request_hash(...) == request)`
    fails (skillopt/coevo5/cells.py:139-149). K3's step-1 byte identity (S ≡ C) and the G5 duplicate check would
    break only for some items.
- Fix:
  - Start the worker with `python -s -B -P` (isolation comes from the container, not from `-I`) and
    `--env PYTHONHASHSEED=0` plus the frozen `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1` (backends.py `_native`
    env, linux-ops F31).
  - S-X2 must compare outputs from two DIFFERENT fresh worker processes.
  - Record the worker's `sys.flags.hash_randomization` and seed in every sandbox log.

**M4 (major) — The line-delimited stdin/stdout protocol is corrupted by one `print()`; responses carry no request
id; long-lived QA workers keep hidden cross-item state.**
- Quote: §1.5 "line-delimited JSON on stdin/stdout ... → `{"ok":true,"result":..,"ms":..}`"; banned list without
  `print`; "for QA/Sheet a pool of long-lived workers per (unit, arm) reloaded per package, stateless per request".
- Why it is wrong:
  - Model-written code very often prints. `print` is not banned, and stdout IS the protocol channel. One stray line
    misaligns every later response of that worker.
  - Without an id/echo field the host cannot detect the misalignment. Notes then go to the wrong item or procedure,
    silently.
  - "Stateless per request" is not enforced: module globals persist in a long-lived interpreter. A procedure that
    caches or counts across items gives output that depends on the dispatch order. The twin S'∖{j} runs in another
    arm's pool and sees a different item sequence, so the twin differs from S' in more than j (confounding §5.5 and
    §7.3). A REEXECUTE in a fresh worker differs as well.
- Fix:
  - Fork-per-request worker: the container starts, imports the allowed libraries, loads and compiles the package
    once, then `os.fork()`s a child per request (fixed worker code, not procedure code). The child runs one
    predicate or procedure with stdout/stderr redirected to a bounded buffer and writes the result on a dedicated
    pipe fd. The parent enforces wall time by killing the child.
  - Every response echoes `{req_id, proc_sha256, input_sha256}`; on a mismatch the host kills the worker.
  - ALFWorld state is explicit: `run(inp, state) -> {..., "state": json}`. The shell stores the state in the trace
    and passes it back, so episodes are replayable and no hidden state exists. (The spec's signature already has a
    `state` argument, §1.1, but does not say that the shell owns it, so a per-episode worker may also keep globals.)
  - Hidden state is also a test-integrity problem, not only a determinism one. At the test read a long-lived worker sees
    test public views one after another. A procedure that caches what it saw (questions, table layouts, option
    patterns) adapts across test items, which is transductive learning on the test set. Fork-per-request removes
    module-global state, but the container's `--tmpfs=/tmp` survives forks, and `open` is reachable despite the AST
    ban (see m10). So the parent must also wipe `/tmp` after every request, or the worker must run without a tmpfs
    (openpyxl loads the public workbook from `BytesIO`).
  - This also removes the per-episode worker (M5) and the slot problem (M7).

**M5 (major) — Worker death, load-time code and the exception boundary are unspecified, so model code can turn its
own faults into infrastructure unknowns or stop a round.**
- Quote: §4.9 P2 "cell continues without that procedure (fail-open...)"; P4 "worker start failure not caused by the
  procedure"; "Worker-killed-by-limit (memory, pids, wall) is P2, not P4"; §1.5 "one worker per ALFWorld episode
  (stateful procedures)".
- Why it is wrong:
  - (a) A Python-level timeout cannot interrupt a C-level loop in numpy or sympy. Only killing the process or
    container stops it, and with one worker per episode that kills EVERY procedure's state, not "that procedure".
  - (b) Module-level statements in `procedure_source` run at `op: load`. A crash there looks like a worker-start
    failure (P4), which becomes REEXECUTE → unknown(infrastructure) → G2 pause at >10%.
  - (c) The copied ALFWorld loop keeps the frozen `except Exception` → `alfworld_environment_error` (backends.py:774),
    which is row 8, an infrastructure unknown (solver-backends K6). The QA/Sheet solve maps `OSError`/`ValueError`/
    `KeyError` to `public_input_or_runtime_error:<type>` (backends.py:454-455). That prefix is a CONFIGURATION prefix
    (skillopt/coevo5/outcomes.py:60), and `_stops` raises `ConfigurationError` for it (outcomes.py:231-236, :284-286).
    So a sandbox `ValueError` that reaches the copied QA/Sheet shell is not even an unknown: it is a configuration stop,
    and the unit pauses (cells.py:215-233).
  - (d) `run_parallel` stops dispatching after the first escaping error (cells.py:238-257). One uncaught sandbox
    exception therefore truncates a whole interleaved acceptance round, which then collides with M16.
- Fix:
  - AST rule: sources contain only imports and `def`s, with no module-level executable statements.
  - The worker sends `ready` before loading package code and loads each procedure separately with its own status. Any
    failure after `ready` is P2 for that procedure. Only failures before `ready` (docker/image) are P4.
  - With fork-per-request (M4), a kill affects one request only.
  - Register the catch boundary in code. Every sandbox/hook exception is caught inside the hook call and mapped to
    P1–P3. Only `BudgetStop`, `AssumptionBroken`, `LedgerFailure` and `ConfigurationError` may propagate
    (solver-backends K6).
  - Unit tests: a crash at load, a crash in `run`, a timeout in a C loop (`numpy.linalg` on a huge matrix) and
    worker OOM must each produce P2 and keep the round going.

**M6 (major) — The sandbox `docker run` flags are weaker than the frozen `_native` hardening, and the worker file
mount and container cleanup are missing.**
- Quote: §1.5 "`docker run --rm -i --pull=never --network=none --read-only --user=65534:65534 --cap-drop=ALL
  --pids-limit=64 --memory=512m --cpus=1 --tmpfs=/tmp:...size=16m`; `python -I -B /worker/worker.py`".
- Why it is wrong:
  - The frozen `_native` also sets `--security-opt=no-new-privileges=true`, `--memory-swap=<m>m`, `--ipc=private`,
    `--shm-size=64m`, `--no-healthcheck`, `--log-driver=none`, `--ulimit=nofile=256:256`, `--ulimit=core=0:0`, the
    thread-count env vars, a `--name`, and an always-run `docker rm --force` with cleanup confirmation
    (`container_cleanup_unconfirmed`) (backends.py:169-198; linux-ops F31).
  - Without `--memory-swap` the 512 MB limit can spill into swap: slow, and wall-time-dependent.
  - `/worker/worker.py` does not exist in the image and the command mounts nothing.
  - Long-lived `--rm -i` workers whose docker CLI hangs leave orphans. dl already carries about 2.7 GB of orphaned
    workers (linux-ops F39).
- Fix:
  - Copy `_native`'s flag list as a frozen constant and add only the worker's read-only bind mount (sha256 of
    worker.py pinned in the manifest, M19).
  - Name containers `execskill-sbx-<uuid>`, force removal with confirmation, and map an unconfirmed cleanup to the
    copied `CleanupUnconfirmed` stop.
  - S-X1 ends by listing leftover `execskill-sbx-*` containers (must be 0).

**M7 (major) — The slot design is inconsistent: 6 per-episode workers and at least 5 per-(unit, arm) pools against
3 sandbox slots, with no lock order.**
- Quote: §1.5 "one worker per ALFWorld episode ...; for QA/Sheet a pool of long-lived workers per (unit, arm) ...
  Worker slots: `execskill-sandbox` = 3".
- Why it is wrong:
  - ALFWorld holds an episode slot for the whole episode (cells.py:130-131) and a model slot per step (6 episode
    slots, protocol.py:331). If a per-episode worker needs one of 3 sandbox slots for its lifetime, 3 episodes hold
    episode slots while waiting.
  - An acceptance round has 4 arms plus twins, i.e. at least 5 pools.
  - `Slots.hold` polls forever, with no timeout (calls.py:78-91). Lock-order inversions (episode → sandbox → model vs
    sandbox → model) can therefore deadlock silently.
  - CPU: 6 ALFWorld processes, 3 native and 1 recalc container already saturate 7 CPUs (linux-ops §5).
- Fix: with fork-per-request (M4), a sandbox slot is held per request only; one long-lived worker per process
  serves all arms, and arms share the worker but never state. Register the global lock order (episode → sandbox →
  model → native). Every slot wait gets a timeout that maps to P4. S-X3 measures throughput with 6 concurrent
  episodes and 3 Sheet cells.

**M8 (major) — Multi-call cells break three frozen cell mechanisms: Sheet native-slot deadlock, `_replay` of only the
last send, and classification from `receipts[-1]`.**
- Quote: §0 "Copy with the new VERSION: cells, ..."; §1.1 compute "makes at most one extra solver call ... The
  second reply is the delivered reply"; §4.9 P4 "re-execute the cell's shell from the recorded receipts ≤ 2".
- Why it is wrong:
  - (a) For SpreadsheetBench, `on_reply` enters `context.native.hold()` after EVERY reply inside one ExitStack
    (cells.py:126-128; calls.py:278). A two-call Sheet cell therefore tries to hold a second native slot of the 3-slot
    pool while holding the first. Three such cells deadlock (solver-backends G3).
  - (b) `_replay` asserts the hash of the LAST send and returns the LAST receipt (cells.py:139-149). Replaying a
    two-call cell fails the `require` on the first call, which escapes as an exception (M5d).
  - (c) Delivery and noncompletion rows read only `receipts[-1]` (outcomes.py:251-263). A truncated or undelivered
    FIRST call of a compute round trip is unclassified, and the spec does not say whether a compute tag inside a
    truncated first reply is still evaluated.
- Fix: in the copied cells:
  - `on_reply` takes the native slot once per cell (idempotent) and only after the final reply.
  - `_replay` replays all sends in order, asserting a hash per index.
  - Register "cell delivery = worst over its receipts". Any undelivered receipt → unknown(infrastructure) after
    resends. A truncated first reply → no compute evaluation, cell = completion-aware fail.
  - Unit tests for each case.

**M9 (major) — The compute evaluator can hang or OOM the host process on solver-written input; no cell has a wall
clock.**
- Quote: §1.5 "Compute evaluator (A10): `fractions.Fraction` arithmetic over `+ - * / ** ( )` ..., ≤ 512 chars,
  exponent ≤ 100".
- Why it is wrong:
  - EXPR is model output (the solver writes it), but the spec has the shell evaluate it, apparently on the host.
    A3 says model-written code runs only in the sandbox.
  - "Exponent ≤ 100" does not bound nested results (E, arithmetic: digits = 99^k × log10 9):
    - `((9**99)**99)**99` has every exponent ≤ 100 but about 9.3×10^5 digits;
    - 4 levels give about 9.2×10^7 digits (≈38 MB; minutes to hours of CPU in Python big-int multiplication);
    - 5 levels, `(((((9**99)**99)**99)**99)**99)`, only 31 characters, give about 9.1×10^9 digits (≈3.8 GB). That
      exhausts memory on a 15 GiB host shared with 6 ALFWorld processes.
  - The thread hangs, or the run process dies of OOM with all its threads: a chain crash without `status.json`.
  - Nothing in the frozen stack bounds a cell's wall time. Only model reads and docker have timeouts.
- Fix:
  - Evaluate EXPR inside the sandbox (fork-per-request, 1 s) or bound the magnitude after every operation
    (|numerator|, |denominator| ≤ 10^200) and the depth.
  - `round` digits ≤ 12. Non-integer powers → `computation_failed:irrational_power` (Fraction ** Fraction gives a
    float, so "exact" would be false).
  - Add a per-cell host watchdog (registered, e.g. 3 × read timeout) that converts a stuck cell into unknown
    (infrastructure) with a diagnostic.

### B. Format guard and the ALFWorld loop

**M10 (major) — The format guard is not outside the learnable part: free-text notes can dictate the reply format,
and inherited cross-bench procedures can never be retired.**
- Quote: §1.1 "the system prompt (contract + card) is never touched, so it stays byte-identical across arms". §4.4.4
  "no output on any R view contains an answer tag, an `<action>` tag or a code fence (mechanical check, so a note
  cannot dictate the reply format)". §4.4 "registered retirements, only of procedures whose home bench is b".
- Why it is wrong:
  - A note is arbitrary text in the user message. "Respond with a JSON object", "give the bare number without
    units", "put 'Final answer:' on the last line" and "reply with the command only" contain no tag and no fence, so
    the mechanical check is trivially passed.
  - These are exactly the cross-bench format conflicts that cost −9.5 to −33 points on OfficeQA (E4/E9; map §3.9,
    FP F51-F52). They are the reason design-v0 §一.4 keeps format out of the learnable part.
  - G3 sees the damage only on the home bench at acceptance. Sieve (b) sees it only on EARLIER benches' generated
    sets.
  - A "cross" procedure from SpreadsheetBench that damages OfficeQA formatting sits in S, S' and P alike at the
    OfficeQA step, so the decision contrast is blind to it. It also cannot be retired there (home-bench rule). It
    reaches F, and then contaminates Q1 "home" for OfficeQA at test.
- Fix:
  - (1) Make context notes typed data rendered by the shell, not prose. Example: `{"facts": [{"key": str ≤ 40,
    "value": str | number | list}]}`, with values copied from or computed over the public view.
  - (2) A fixed lexicon screen on note keys and values (answer/return/respond/format/output/JSON/final/last line/
    letter/only/tag/fence ...), with a hit going to the existing leak adjudication.
  - (3) Allow retiring ANY inherited procedure that fires on bench b, tested in the same S' vs S acceptance.
  - (4) Owner decision: a format-only panel (no correctness read) on the tail public views of the other benches for
    sieve (b). Without it, cross-bench format harm is detectable only at the test read, and the registration must
    say so.

**M11 (major; contradiction with working assumption A9) — The canonicaliser is action repair, and it interacts with
the procedures.**
- Quote: §1.4 "it maps wrapper forms ("action: X", case) to an admissible command ... applied in every arm including
  the task-card arm". A9 "registered for every arm, so it cannot flip signs between arms".
- Contradiction:
  - The D3/D14 canonicaliser also has the branch "else take the earliest admissible command named in the reply"
    (docs/handoff/feasibility-20261021/D14/report.md:185-187). The spec omits it from its description but logs it
    (`how = earliest_admissible`).
  - Verified on dl (2026-10-21 19:2x, read-only `sed`): `parse` searches the WHOLE reply, `low = text.lower()`, not the
    tag content (dl:/data/feasibility/D3/r3/pilot_alf_glm.py:178-195). A reply such as "cabinet 1 was empty, so I will
    not go to cabinet 1 again" with a malformed tag therefore executes `go to cabinet 1`, the command the model
    rejected. With the veto hook this is worse: the veto note makes the model name the discouraged command, and the
    canonicaliser can then execute exactly that command. The canonicaliser can thus carry the veto's effect in
    either direction.
  - In the SAME canonicalising loop, the executed action differed from the frozen parse on 41.0% of steps for the
    tracker arm vs 13.2% for control. 25 of 26 tracker passes used at least one rescued step
    (docs/handoff/feasibility-20261021/D3/critic-result.json:4 item 2).
  - So being present in every arm does not neutralise it. A state note that lists "not yet visited: cabinet 1,
    cabinet 2 ..." makes the reply mention commands, and the earliest-named branch turns that prose into actions.
    Part of any measured procedure effect is then a repair effect. AGENTS.md: answer repair is not Skill evolution.
- Fix:
  - Register a deterministic level-1 canonicaliser only: strip known wrappers, then do a case-insensitive exact match
    to an admissible command. Drop the earliest-named branch; an unmatched reply is sent verbatim, as in v3, and the
    environment answers "Nothing happens".
  - S-A1 measures the new model's wrapper rate with reasoning off, to decide whether level 1 suffices.
  - Add guard G6: if the share of canonicalised steps differs between S' and S by more than 5 points (sign test
    p < 0.05), the step is "repair-driven" and is rejected.
  - Report canonicalised shares per arm.
  - REQUIRED_FORMAT's ALFWorld admissible-action share is computed on the RAW reply, before canonicalisation (see
    also m8).

**M15 (major) — The ALFWorld router input is undefined: the ALFWorld public view is the game path, and
"known before dispatch" requires an unregistered reset pre-pass.**
- Quote: §1.5 "at item start evaluates every procedure's `applies(view)` on the *public view only* ... (ALFWorld: on
  the initial observation and task text) ... This makes every enable decision known before dispatch, which the
  withholding twins (§5.5) require".
- Why it is wrong:
  - `_PUBLIC["alfworld"] = ("game_file",)` (skillopt/continual_eval/backends.py:57-60, re-read 19:2x). "Public view only" literally
    hands predicates the game path, a task identifier that the frozen loop deliberately keeps out of the model view
    (backends.py:742-743).
  - The initial observation exists only after an environment reset. Knowing E_i before dispatch therefore needs a
    reset pre-pass over every acceptance and test game (about 200 + 134 resets, E). That pass has no unit, no cost
    estimate and no determinism check against the solve-time reset.
  - The alternative, deciding twins after the S' reset, breaks the "one seeded order".
- Fix:
  - Define the ALFWorld router input as `{initial_observation, task_text}`, produced by a registered zero-call reset
    pre-pass unit (own process, seed 42), with the sha256 of the initial observation recorded and asserted equal at
    solve time.
  - Never pass `game_file`, the item id or any path to model-written code. Add a unit test over all views.
  - Report the pre-pass wall time from S-A1.

**m2 (minor) — Veto marks are unspecified.**
- Quote: §1.1 "marks discouraged commands in the view".
- If the marks are put inside `admissible_commands` strings, the model may copy them into its action and level-1
  matching then fails.
- Fix: a separate `discouraged_commands` key appended after the frozen keys; `admissible_commands` stays
  byte-identical to the frozen view.

### C. Validity of the method-side checks (rules that are trivially satisfiable)

**M12 (major; unfalsifiable as written) — Replay tests are trivially satisfiable.**
- Quote: §1.1 `"property": "<python: def check(out) -> bool>"`; §4.4.3 "for each `claims` trajectory the stated
  property holds".
- Why it is wrong:
  - The engineer writes both the procedure and its property. `def check(out): return True` passes.
  - Zero crashes and determinism are hygiene, not repair (map §2.3, CM §5.9).
  - design-v0's guard "必须在它声称修复的失败轨迹上跑通" (it must run correctly on the failure trajectories it claims to
    fix) thus becomes vacuous. A compute procedure cannot be replay-tested at all without a solver call.
- Fix:
  - Non-vacuity: on every claimed trajectory the property must be False with the procedure withheld (empty
    note/state) and True with it. It must also be False on a registered mutated input.
  - A static check that the property reads at least one field of the item's public view.
  - For ALFWorld state procedures, fixed-code oracle properties derived from the recorded observations, as D3's
    p3–p6 were (FP F10). Examples: consistency of the reached set with the "You arrive at X" observations, and of
    carrying with the pick/put outcomes.
  - Report replay as hygiene only, never as evidence of repair.
  - A wrong tracker: nothing at run time detects a stateful procedure whose state contradicts the observations. An
    example is a receptacle marked "reached" after the environment answered "Nothing happens". The model is then
    misled silently. Add a fixed-code consistency flag per step (state vs the observation it was updated from), and
    report the inconsistency rate per procedure and arm. It is not a decision input.

**M13 (major; unfalsifiable for the examiner headline) — Detector acceptance can be met with outcome proxies already
present in the trajectory.**
- Quote: §6.1 "A detector is `def fires(trajectory) -> bool` over the whitelisted trajectory ... Accept iff |F| ≥ 10
  cells from ≥ 6 items, ... lower bound of (p − b) ≥ 0.10, and r ≥ 0.15". §6.4 "The examiner side "evolved" in a step
  iff a detector was accepted ...".
- Why it is wrong:
  - The ALFWorld loop stops on `won or dones[0]` (backends.py:768-770), so nearly every failing episode runs all 50
    steps. `fires = len(steps) == 50 and <anything>` then has precision ≈ 1 against b ≈ 0.5.
  - SpreadsheetBench predictions carry the case execution status; QA failures with no tag are mechanical anyway.
  - "The examiner evolved" is therefore achievable by restating outcome-visible features: the rule cannot fail.
- Fix:
  - Detector input excludes outcome-revealing fields. ALFWorld: evaluate on a registered prefix (the first 25 steps),
    with the step count hidden. Sheet: the reply only, no execution status. QA: the reply only.
  - Require lift on the cells where NO mechanical category fires (incremental over §4.2a).
  - Require the detector to split the failures (fire on 15–85% of failing V cells).

**M21 (major) — The compute hook has no executable learned part, so "executable procedure" is hollow for it, and its
replay tests are vacuous.**
- Quote: §1.1 "`compute`: the procedure contributes a fixed instruction note telling the solver it may write one
  `<compute>EXPR</compute>`; the shell evaluates EXPR with the registered evaluator".
- Why it is wrong:
  - The evaluator is fixed code and `run` has no registered role for compute. What is learned is a TEXT instruction
    plus the predicate.
  - The paper's claim "skills are executable procedures, not text" (design-v0 §二, final paragraph) does not hold for
    this hook, which is the main one for OfficeQA and LiveMath.
- Fix: compute procedures return `run(inp) -> {"bindings": {name: number}, "note": str}`, i.e. numbers extracted from
  the public view (for example an OfficeQA table) that EXPR may reference by name. Replay can then check, with fixed
  code, that every binding value occurs in the view text. The procedure becomes executable and its tests
  falsifiable.

**M20 (major) — Procedures can exploit the LiveMath label regularity that A8 forbids for generators.**
- Quote: §6.2 L-gate "Banned: training-label regularities (LiveMath ... "stronger statement" meta option)" applies to
  generators only. §3.2: the engineer receives R trajectories "with ... the reference answer".
- Why it is wrong:
  - The meta option `STRONGER_OPTION` (skillopt/coevo5/protocol.py:222) is the key in all 129 of the 283 training
    items that contain it (FP F44).
  - A predicate "an option contains 'a stronger result can be proven'" plus the note "such options are correct here"
    is a label shortcut. The engineer can read it off the R references; the leak check (literal extraction against
    R references) cannot see it.
  - It would pass LiveMath acceptance on the A slice drawn from the same pool, and would be reported as a learned
    procedure.
- Fix:
  - Extend the L-gate to procedures: a static screen for the meta-option text and for option-position or option-
    content rules in predicates and notes, with adjudication.
  - Report LiveMath acceptance stratified by meta vs non-meta items. Optionally require the effect on non-meta items
    alone.

### D. Generators and data

**M14 (major; internal contradiction) — The SpreadsheetBench generator needs the private reference inside
examiner-written code, and the 8 KiB result cap rules out workbook outputs.**
- Quote: §6.2 "SpreadsheetBench — perturb the input values of an R item whose reference answer cells are formulas;
  truth = LibreOffice recalculation of the perturbed reference". §1.5 "Inputs whitelist ... Never `private` ...
  references"; "result ≤ 8 KiB (`RESULT_BYTES`)". §3.3 examiner input "**no references**".
- Why it is wrong:
  - Reading which answer cells are formulas, and perturbing and recalculating the reference, requires the private
    answer workbook. Either model-written code sees references (violating A3 and §3.3) or the work is fixed host code
    (then it is not "examiner evolution").
  - An xlsx output is a zip and typically exceeds 8 KiB (E).
- Fix:
  - Examiner code returns a perturbation SPEC (`{sheet!cell: new value}`, ≤ 8 KiB JSON) computed from the public
    input workbook.
  - Fixed host code applies it to the input and reference workbooks, recalculates in the recalc image (sha256
    `f7f6f598…`) and runs the two-scoring qualification (qualify.py:85-131). Only fixed code ever touches the
    reference.
  - Register a separate output cap for generator specs.
  - The same split for OfficeQA: the reproduction check against the original reference is fixed host code; the
    examiner gets only the pass bit.

**M17 (major; freshness violated by construction) — The LiveMath smoke items collide with the registered slices,
and the smoke root's consumption is invisible to the run root.**
- Quote: §9 "Items: SearchQA/LiveMath/ALFWorld from the tail of each order (beyond every registered slice)"; §2.3
  LiveMath "83 × 2 | 200 × 2 | ... | 0 (283 used)"; §2.1 "Smoke and pilot use separate roots".
- Why it is wrong:
  - The LiveMath slices consume all 283 pool items, so there is no tail beyond them.
  - Because the registry is per root, the LiveMath step of the full chain would later re-use the smoke's items
    without refusal.
- Fix:
  - Remove 5 LiveMath items from the supply before slicing, as for SpreadsheetBench and OfficeQA (R = 78), or smoke
    LiveMath on generated items only.
  - Write every smoke-consumed id into a root-independent registry (`/data/execskill-20261021-registry/`) that the
    run's `run_round` also checks.

**M16 (major; contradiction) — A paused unit can never be redone: the write-once registry refuses the redo, and a
redo is not tied to the sealed candidate.**
- Quote: §2.1 "written and fsynced **before** the first cell of that item is dispatched; the copied `run_round`
  refuses an item already present (also across chains of the same root)". §5.7 ST2 "the owner chooses (a) terminate
  or (b) redo the paused unit whole in a new attempt directory". §10.2 R15 "the unit is redone whole only on an owner
  decision; partial units never read".
- Why it is wrong:
  - Every item of a paused round is already in the registry, because it was written before dispatch. A redo in a new
    attempt directory under the same root is therefore refused item by item. Option (b) does not exist as registered.
    Option (a) burns the slice: A_b is lost with no decision.
  - Pauses will not be rare in this design:
    - every escaped sandbox exception becomes a Pause (cells.py:215-233; M5);
    - a configuration stop (M5c);
    - a `run_parallel` halt, which stops dispatch for the whole interleaved round (cells.py:237-258).
    v3 needed exactly this recovery after cleanup-unconfirmed stops: archive the faulty attempt, then restart.
  - The spec does not say what a redo re-runs. Suppose the redo re-enters 4.3-4.4 (generator, engineer). The hosted
    GLM is not bit-deterministic at temperature 0, so a different candidate would then be decided on a batch that a
    first candidate already partly solved. No role reads those outcomes, but the rule has to make that mechanical.
  - A crash between the registry fsync and the dispatch leaves items "registered, never dispatched". Under "never
    reuse" they are lost silently.
- Fix:
  - Registry lines: `{item, slice, unit, attempt, state ∈ {registered, dispatched, decided}}`. An item is refused if a
    line for it exists in a DIFFERENT unit, or for a round that was decided.
  - A redo of the same unit needs an owner decision and an infrastructure reason only (V6 §13.4). It re-dispatches the
    same items in the same seeded order and appends `redo` lines. The earlier attempt's cells are archived unread and
    never enter any statistic.
  - Seal S', its placebo twins, the twin schedule and G_b (sha256 in the unit record) before 4.6 starts. A redo of
    4.6 must present identical seals, and it never re-runs 4.3-4.5. If 4.4 itself was interrupted (no sealed
    candidate yet), the redo may re-run it, because A_b is untouched.
  - Cap the redos (e.g. ≤ 2 per unit). At the cap, the slice is recorded as consumed-without-decision (R4).
  - Unit test: pause at cell k of an acceptance round, then redo. Assert identical request hashes and that no
    first-attempt verdict reaches the decision record.

### E. Smoke, manifest, placebo mechanics

**M18 (major) — The smoke never sends a procedure arm to the real endpoint, so it cannot catch the defects that the
v2/v3 smoke tests caught.**
- Quote: §9 S-F1 "format check, C arm: 20 items (SB/OQ 5) per bench | ≥ 9/10 format compliance (v3 floor,
  smoke.py:71-77)"; S-A1 "ALFWorld shell: 5 games, C arm and a toy context procedure"; S-X1-S-X3 zero-call.
- Why it is wrong:
  - v3's format check ran on the Skills the method starts from, with two rules: a floor of 9/10 AND a margin of at
    most 1/20 below the empty Skill (`FORMAT_FLOOR`, `FORMAT_FLOORED`, `FORMAT_MARGIN`, skillopt/coevo5/smoke.py:69-77).
    S-F1 checks only C, the frozen card. It tests the model, not the learnable part.
  - All new failure surfaces are in the procedure arms. They are:
    - the `shell_notes` key in the user JSON;
    - the compute second call, a new template that has never been sent to this model (M22);
    - the placebo filler and the veto marks;
    - over-length replies under a cap that the gateway may not enforce.
    Missing answer tags and wrong format rates are most likely to come from exactly these paths. The cal-1 placebos
    moved scores by −9.8 to +3.6 points, mostly through a JSON artefact (spec §5.6).
  - S-A1 has no criterion for the raw wrapper rate, and that rate decides whether a level-1 canonicaliser is enough
    (M11).
  - S-E4 uses max_tokens 16 only. It says nothing about replies running past 8,192 or 16,384 tokens (M1), nor about
    throughput for the read timeout (m1).
- Fix: add these paid checks before the pilot, on smoke-root items only:
  - **S-F2:** a fixed toy package per bench (one context procedure; one compute procedure on QA; one veto on ALFWorld),
    plus its placebo twins. Arms C, S'(toy) and P(toy) on 20 items per bench (OQ/SB 5). Pass: every arm has a
    required-format share ≥ 9/10, and S' and P are each ≥ C − 1/20 (v3's margin rule). Report the compute-tag rate
    and the second call's format share separately.
  - **S-F3:** ALFWorld raw reply forms on 5 games × {C, S'(toy)}: the share of steps with a valid `<action>` tag, with
    a wrapper form, and with no match, all before canonicalisation.
  - **S-E7:** long-generation prompts at the registered max_tokens (QA 8,192 and Sheet 16,384), 5 each, reasoning off.
    Record completion tokens, finish_reason and tokens per second. These register the over-length rule (M1) and the
    read timeout (m1).
  - Fix the S-F1 arithmetic (m16).

**M19 (major) — The manifest is never specified. What is pinned, and how it is checked before each unit, is left to
"copy manifest".**
- Quote: §0 "Copy with the new VERSION: cells, units, evaluation, qualify, manifest, prelaunch helpers, smoke, chain,
  CLI"; §1.5 "image `evolve-skill-native:smoke-20260928` by digest". No section lists the manifest's contents.
- Why it is risky:
  - The v3 manifest pinned the runtime, the images and the source snapshot (V6 §0; linux-ops F14). It has no field
    for the new objects below, and each one changes either the requests or the verdicts.
  - Sandbox code: the worker code, its docker flag list (M6), the compute evaluator and the second-call template
    (M22).
  - Library versions inside the image (sympy 1.13.3, pandas 2.2.3, numpy 1.26.4, openpyxl 3.1.5). linux-ops F30 says
    these were "assumed to be what was built; inferred" from the repo pins, never read from the image. The host env
    lacks sympy and pandas (linux-ops F5), so a check run on the host would silently use a different engine.
  - Gateway identity: endpoint host (never the key), echoed model id, and every request parameter
    (`reasoning_effort: "none"`, temperature, max_tokens, COMPLETION_BOUND). The gateway's default is reasoning ON, so
    one dropped parameter silently changes the model's mode.
  - Client: the proxy URL, `trust_env=False`, and the source sha256 of the new client subclass.
  - Frozen texts: the five cards (texts.json sha256 given in §1.3), the contract sentences, the hook API spec shown to
    the engineer, the role prompts and the placebo corpus.
  - Supplies and state:
    - SearchQA block N ids and the D_alf game list, as written artefacts (m11);
    - the v3 qualification files admitted through `IMPORTABLE` (§0, D13);
    - the registry's hash chain;
    - every package S_k, G_b and detector library, sealed per step.
- Fix:
  - Register a manifest schema (`fivebench-execskill-v1-manifest`) with these fields.
  - `prelaunch` verifies every field with zero model calls before each unit. This includes `docker image inspect` of
    the digest and a `pip freeze` run inside the image with `--network=none`, whose output is recorded. Any mismatch
    is a `ConfigurationError` before dispatch.
  - The manifest pins only what was sent, so the per-receipt check that reasoning was really off (P5) stays as well.

**M22 (major) — The compute second call and its placebo are not registered texts, and "[value withheld]" is a
behavioural signal, not an inert placebo.**
- Quote: §1.1 "makes at most one extra solver call (A10) whose user message is the first user message plus
  `{"first_reply": ..., "computed": value | "computation_failed:<class>"}`. The second reply is the delivered reply".
  §1.6 "`computed` is replaced by the fixed string `"[value withheld]"` padded to the real value's length".
- Why it is wrong:
  - The second call has no registered instruction. The solver gets its own first reply back plus a value, and nothing
    says what to do next: restate the answer in the contract format, or continue. Suppose the model answers "391"
    without a tag on the second call. That fails the format guard in S' only. G3 compares S' with S, so this shows up
    only as a rejection and is never diagnosed.
  - In P, "[value withheld]" tells the model that information was hidden from it, which invites refusals, hedges and
    off-format re-derivations. P then fails for a reason S' cannot have, and S' > P becomes easy. The test of whether
    a second look alone helps then has no content, and nothing signals that. The spec itself records that placebos
    are not inert (cal-1: −9.8 to +3.6 points, §5.6).
  - "Padded to the real value's length" is impossible for values shorter than the 16-character marker, for example
    "42".
  - When a computation fails, S' gets `computation_failed:<class>` but P still gets the marker. So the arms do not
    differ only in the value.
- Fix:
  - Register the second-call template verbatim. Example: the first user message; then a fixed sentence such as "A
    calculator evaluated the expression you wrote. Give your final answer in the required format."; then
    `{"expression": EXPR, "result": R}`.
  - P uses the same template, keys and sentence, with `result` = "not evaluated". A computation failure gives the same
    "not evaluated" in both arms, so the arms differ only when a real value exists.
  - Register a check per acceptance round. If P − S is negative with two-sided p < 0.05, the placebo contrast is
    labelled "placebo-harmful, uninformative". What follows is an owner decision; the default is reject and report.
  - S-F2 (M18) measures the format share of the second call in S' and in P.

### F. Minor findings

**m1 (minor; invented number) — The 600 s read timeout rests on an invented throughput, and it is shorter than a reply
inside the registered bound.**
- Quote: §3.1 "read timeout 600 s (... 600 s exceeds 1.8× the time of a 16k-token reply at ≥ 50 tok/s — E)".
- Why it is a problem:
  - "≥ 50 tok/s" has no source. The probes measured only replies of 15-21 tokens in 2.9-4.3 s (dl:/data/execskill-ops/probe-20261021-2.log, read 19:2x), which says nothing about throughput.
  - At 50 tok/s, a Sheet reply at COMPLETION_BOUND = 32,768 tokens needs about 655 s (E, arithmetic). That is above
    the timeout. A reply the spec calls legitimate (`over_nominal`) therefore times out, becomes a transport error,
    and is resent twice (cooldown 60 s each). Each resend can again cost up to the bound.
- Fix: S-E7 (M18) measures p10 tokens per second on long replies. Register timeout = COMPLETION_BOUND / p10 rate ×
  1.2, or lower the bound to what the timeout admits.

**m3 (minor) — Note overflow is not "identical in every arm".**
- Quote: §1.2 "overflow → the lowest-priority (latest) notes are dropped and the drop is logged (`inject_overflow`),
  identically in every arm".
- Why it is a problem:
  - S', S, P and the twins carry different procedure sets. P keeps the retired procedures; a twin lacks j. So the
    overflow drops a different note in each arm, and a twin can differ from S' in more than j.
  - NOTE_BYTES is 2,048 B and MAX_INJECT 4,096 B for QA, so two full notes already fill the budget, while
    MAX_PROCEDURES = 12.
- Fix: an admission rule in §4.4. The sum of each context procedure's maximum observed note bytes on R ∪ G must be
  ≤ MAX_INJECT. An overflow at solve time is then a P2 fault of the latest procedure, logged per arm.

**m4 (minor) — With retirements, the placebo contrast tests the retirement, not "an extra note".**
- Quote: §1.6 "The placebo arm P = S ∪ {P(j) : j ∈ Δ} (retirements in S' are not mirrored)".
- Why it is a problem:
  - If S' drops a harmful inherited procedure, then S' > P can be earned by the dropping alone.
  - For a retirement-only candidate, P = S, so the intersection-union test collapses into one contrast run twice.
- Fix: P = (S − retired) ∪ {P(j) : j ∈ Δ_add}. S' and P then differ only in the added procedures versus their twins.
  Report retirement-only acceptances as their own category.

**m5 (minor; contradiction) — The engineer's input exceeds the registered role cap.**
- Quote: §3.2 "up to 40 failing and 10 passing R trajectories ... truncated per trajectory to 6,000 B"; "input ≤
  220,000 B".
- Why it is a problem:
  - 50 × 6,000 B = 300,000 B (E, arithmetic) > `ROLE_INPUT_BYTES` = 220,000 (skillopt/coevo5/protocol.py:245). The
    card, the hook API spec and the package sources come on top of that.
  - The v3 rule drops examples from the end of their seeded order (protocol.py:242-244), so the passing trajectories
    disappear first, silently.
  - ALFWorld observations reach 12,000 characters per step (backends.py:757). A 50-step episode cut to 6,000 B shows
    only its first steps, before the loops start (D3: about half of the looping is revisits, FD/D3/critic-result.json:4
    item 5).
- Fix: register byte budgets per bench (ALFWorld: compact action/observation digests plus the last N steps),
  post-cap counts in the payload, and a test that asserts the payload size.

**m6 (minor) — S-Q1 cannot pass on ALFWorld as written.**
- Quote: §9 S-Q1 "every (system, user) request hash ... and prediction equals frozen `backends.solve` ... 100%
  identical"; §5.1 C on ALFWorld = "the new loop with zero procedures and the canonicaliser".
- Why it is a problem:
  - Whenever a recorded reply is a wrapper form, the canonicaliser executes a different action than frozen
    `_solve_alfworld` would (backends.py:752-762). After that, the observations and request hashes diverge.
  - Predictions also gain `prediction["router"]` and the new traces.
  - Under ST1 the failed criterion blocks the pilot.
- Fix:
  - Run S-Q1 on ALFWorld with the canonicaliser off.
  - With it on, compare requests up to the first canonicalised step.
  - Compare predictions after removing the registered new keys.

**m7 (minor) — The compute hook's scope is undefined outside QA.**
- Quote: A10 "at most ONE extra solver call per item"; §1.1 compute hook.
- Why it is a problem:
  - For ALFWorld, one item is up to 50 calls; nothing says whether compute applies per step or per episode.
  - For SpreadsheetBench, the second reply must still carry the program, and the program runs after the final reply
    (M8).
- Fix: register compute for SearchQA/OfficeQA/LiveMath only, or define the per-episode count and the Sheet
  semantics explicitly.

**m8 (minor) — The ALFWorld admissible-action share in G3 and §4.5(b) does not say raw or canonicalised.**
- Why it is a problem: the canonicaliser outputs an admissible command whenever it can. Computed after it, the share
  is close to 1 by construction, and the guard cannot fire.
- Fix: compute the share on the raw tag content before canonicalisation, and report both.

**m9 (minor) — Selected and generated items are not written into the consumption registry.**
- Quote: §2.3 "The selector of §6.2 draws only from the remaining ~2,914 train games".
- Why it is a problem: nothing stops a later ALFWorld step, or the full run after the pilot, from selecting the same
  games again. The same holds for generated items of other benches.
- Fix: registry slice "G" (with the generator's sha256), checked by the same refusal rule.

**m10 (minor) — The banned-import list is presented as a security control, but it is not one.**
- Quote: §1.5 "banned `{os, sys, subprocess, ... builtins.open/eval/exec/compile}` by AST check before load and an
  import hook inside".
- Why it is a problem:
  - The allowed libraries reopen what the list bans:
    - `sympy.sympify` / `parse_expr` evaluate strings with `eval` (sympy's documented behaviour);
    - `pandas.read_pickle` unpickles arbitrary objects;
    - `getattr(__builtins__, "op" + "en")` defeats a name check;
    - `pandas.Timestamp.now()` and `numpy.random` give time and randomness although `time` and `random` are banned.
  - The container is therefore the only boundary.
  - Read-only access is still possible. The worker process can read the image filesystem and `/proc`. That is
    harmless only while nothing sensitive is mounted or passed as an environment variable.
- Fix:
  - Say in the registration that the container is the security boundary and the AST check is a hygiene and
    determinism screen.
  - Add these bypasses to S-X1 (each must be contained) and to S-X2 (determinism).
  - Assert in a unit test that the `docker run` command mounts only worker.py and passes no host environment.

**m11 (minor) — The supplies produced by the test-access code are not pinned artefacts.**
- Quote: §2.2 "exclusion by id ... run by code holding test access; ids only"; S-T1 "prints counts only".
- Why it is a problem: the "one seeded order" can be re-verified only if the input supply is a fixed file.
- Fix: write `supply/<bench>.json` (route-B ids; the sha256 of the exclusion inputs; no test ids). Seal it, and
  record it in the manifest (M19), before any order is computed.

**m12 (minor) — GLM role limits are partly unregistered and tight.**
- Why it is a problem:
  - No slot count is given for the roles (v3: `glm-5.3` = 10, protocol.py:331).
  - Three procedures × 12 KB of source, plus tests and descriptions, come to roughly 9-12k tokens (E: 36 KB at about
    3-4 B/token). That is close to `ROLE_MAX_TOKENS` = 16,384 (protocol.py:31).
  - A truncated JSON reply counts as invalid and uses one of only two attempts.
- Fix: register role slots. Limit source to ≤ 6 KB per procedure, or to ≤ 2 procedures per call.

**m13 (minor) — The text twin T_F confounds code vs text with gated vs ungated.**
- Quote: §7.1 "T_F (text twin: card + the procedures' descriptions as one `shell_notes` block on every item, no code
  executed)".
- Why it is a problem:
  - F applies a procedure only where its predicate fires, while T_F shows every description on every item.
  - The descriptions are documentation of at most 600 B, written to be "shown to nobody at solve time" (§1.1). So
    the pre-stated code-vs-text comparison (§7.4) runs against a weak text arm.
- Fix:
  - Gate T_F's descriptions with the same router decisions, or register both versions (gated and on every item).
  - Have the engineer write the description as a solver-facing instruction.

**m14 (minor) — The placebo corpus is too small to match note lengths, and it does not match typed notes.**
- Why it is a problem:
  - The eight v3 placebo texts are 160-191 B each, 1,388 B in total (measured: skillopt/coevo5/protocol.py:105-124).
    Matching a 2,048 B note "at offset ... mod len" means repeating the corpus, which reads as artificial filler.
  - If notes become typed facts (the M10 fix), prose filler is distinguishable on sight.
- Fix: the placebo note has the same typed structure with irrelevant values. Log byte-length equality per cell in the
  trace.

**m15 (minor; vacuous) — Detector re-validation can never happen in a one-pass chain.**
- Quote: §6.1 "on a later step of the same bench they are re-validated on the new V and retired after two failures".
- Why it is a problem: each bench is visited once. The same defect that K2 corrects for generators applies here.
- Fix: say "never re-validated in a one-pass chain", or re-validate on later benches' R where the detector's category
  applies.

**m16 (minor) — The S-F1 criterion is arithmetically inconsistent and fragile to serving noise.**
- Quote: §9 S-F1 "20 items (SB/OQ 5) per bench | ≥ 9/10 format compliance ... else stop".
- Why it is a problem:
  - On 5 items, 9/10 means 5/5. One miss stops the protocol.
  - v3 recorded an unchanged prompt going from 20/20 to 16/20 between two runs (skillopt/coevo5/smoke.py:74-75). So
    the C arm can fail by serving noise alone, and ST1 then forces a registration amendment.
- Fix: v3's two-part rule (smoke.py:73-77: a floor for the method's arms, and a 1/20 margin to the empty-Skill arm),
  plus a registered single re-run on a first failure.

**m17 (minor; identity) — The "protocol-free" imports bind v3 protocol constants.**
- Quote: §0 "Import unchanged (protocol-free): `coevo5.{budget, ledger, calls, outcomes, stats, checks, roles}`";
  §3.1 "Recorder resends ≤ 2 with cooldown 60 s (v3 used 300 s)"; "the copied settle logs all attempts' reported
  usage".
- Why it is a problem:
  - Three of these modules import `skillopt/coevo5/protocol.py`, where `VERSION = "fivebench-coevolution-v3"`
    (protocol.py:10):
    - `ledger` takes `CLIENT_ATTEMPTS` and `RESERVATION_OVERHEAD` (ledger.py:11-19);
    - `calls` takes `MAX_RESENDS` and `RESEND_COOLDOWN_SECONDS` = 300 (calls.py:32; protocol.py:87-88);
    - `outcomes` takes the workbook limits (outcomes.py:36).
  - The values match what the spec registers, except the cooldown. `Endpoint` defaults to v3's 300 s
    (calls.py:136), so the 60 s happens only if every construction site passes it explicitly.
  - "The copied settle" contradicts "ledger imported unchanged" (see also M1).
  - The new protocol's identity therefore depends on v3's protocol module without saying so.
- Answer to the identity question: the output directories, the VERSION and the frozen files are kept apart
  correctly. The dependency on v3 constants is undeclared but harmless once declared.
- Fix:
  - List `skillopt/coevo5/protocol.py` (sha256) as an inherited dependency in the manifest (M19).
  - Pass `cooldown=60` explicitly, with a unit test on its value.
  - Move `settle` into the copied package (M1), so that "import unchanged" is literally true for the modules that
    remain.

### G. Verification log (what this critic re-checked, 2026-10-21)

- Re-read locally:
  - skillopt/coevo5/ledger.py:67 (the halt fires on `completion > max_tokens`);
  - calls.py:78-91 (`Slots.hold` has no timeout), :150-170, :268-279;
  - outcomes.py:60, :66-67, :176-182, :231-248, :251-263, :284-304;
  - cells.py:122-149, :183-258;
  - skillopt/continual_eval/backends.py:57-60, :169-200, :364-455, :715-783;
  - protocol.py:10, :30-33, :62-65, :87-88, :105-124, :222, :245, :278-279, :331;
  - the imports of ledger.py:11-19, calls.py:29-32 and :136, outcomes.py:36, budget.py, stats.py, checks.py, roles.py;
  - smoke.py:69-77;
  - docs/handoff/feasibility-20261021/D14/report.md:185-187 and D3/critic-result.json:4.
- Read on dl (read-only `cat`/`sed`, BatchMode, after aTrust came up; nothing was written or started):
  - `/data/execskill-ops/probe-20261021-2.log`. It confirms the spec's K1 reading: `max_tokens_2 ... stop 21 19 63
    '391'`, and `reasoning_effort_none ... stop 1 None 0`.
  - `/data/feasibility/D3/r3/pilot_alf_glm.py:160-202` (`canonical`, `parse`). It confirms the earliest-admissible
    branch and that `parse` searches the whole reply (M11).
- Not verified:
  - the Python version inside the native image, which the `-P` flag of the M3 fix needs (≥ 3.11). linux-ops F29-F30
    suggest a python:3.11 base, but this was not read from the image;
  - whether the gateway enforces max_tokens with reasoning off. Only S-E4/S-E7 can settle that.
- Earlier attempt: it could not reach dl ("Connection closed by 10.102.254.2 port 22"). This pass could, and the
  session note at the top is superseded by this log.

### H. What model-written code can and cannot reach (summary of the attack surface)

| target | reachable as specified? | finding |
|---|---|---|
| network | no: `--network=none` | none |
| ledger, run store, `.env`, keys | no mount and no host environment is specified. Only a unit test on the `docker run` command line (m10) can make this a guarantee | m10 |
| reference answers | not at solve time. They are reachable through the SpreadsheetBench and OfficeQA generators, and procedures can learn label regularities from the R references the engineer sees | M14, M20 |
| task identifiers / game path | yes, if "public view" is taken literally on ALFWorld (`game_file`) | M15 |
| test set | public views only, at the test read. A long-lived worker or the shared `/tmp` lets a procedure accumulate state across test items | M4 |
| filesystem | read access to the image and `/proc`; write access to the container's `/tmp` tmpfs, shared across requests. `open` is reachable despite the AST ban | M4, m10 |
| host process | yes, through the compute evaluator running on the host (CPU/memory exhaustion), and through exceptions that escape into the frozen catch clauses (pause / configuration stop) | M9, M5 |
| the delivered reply | not directly (no reply-writing path). It is reachable indirectly through free-text notes, the canonicaliser and the unregistered second-call template | M10, M11, M22 |
| SpreadsheetBench execution and scoring | the solve path itself stays frozen: copied `backends.solve`, then frozen extraction, then `_native` per case, then frozen v7 scoring with the v3 qualification reused under `IMPORTABLE`. Only the two-call cell (native slot, replay) and the generator break it | M8, M14 |

## Best ideas worth keeping in the synthesis

1. **Measure before registering the truncation rule.** The K1 reading of the probe is careful (21 completion tokens
   = 19 reasoning + 2 visible), and S-E4 decides the rule before the pilot. "Reasoning off" is checked as
   `reasoning_tokens in (None, 0)` AND empty/absent `reasoning_content`; the observed value is `None`, not 0. Keep
   this exact definition.
2. **K3: the step-1 parent equals the card arm, which gives a free same-text duplicate.** G5 uses it as a noise-floor
   and interleaving check, with a pause instead of a decision when it fails.
3. **A shell without any reply-writing path.** No hook can alter, append to or post-process the delivered reply.
   The veto only marks commands and never rewrites the chosen action. S-Q1 checks byte equivalence with the frozen
   solver when no procedure is enabled. This is the right construction. M10, M11 and M22 only close its remaining
   side doors.
4. **The consumption registry is written before dispatch, and one seeded order is cut into consecutive slices.**
   Independent tags are forbidden because they overlap by chance (DP F6). Keep this, with M16's states and redo rule.
5. **Intersection-union acceptance over S' vs S and S' vs P,** with the batch consumed whether the candidate is
   accepted or rejected, and no pruning on the decision data.
6. **The sieve can only stop a candidate, never accept one, and a stopped candidate leaves A_b unconsumed.** Its
   clause (c) cannot fire for a generator that has not been validated.
7. **K2: an honest repair of "two consecutive disagreements".** In a one-pass chain it can never trigger, so the spec
   counts the pairwise contrasts within one round and registers "untested" as an outcome.
8. **The text twin T_F at test, and the pre-stated expectation that code transfers worse than text (§7.4).** These
   answer the Break It Down risk directly. Gate the twin as in m13.
9. **Fail-open procedure faults with a cap (G1), and P2 rather than P4 for limit kills.** Keep these, once the catch
   boundary of M5 is in code.
10. **Usage of every client attempt is logged.** The frozen ledger keeps only the last attempt's usage, which makes
    its totals a lower bound.
11. **The MDE table with "not certifiable" statements and the K7 freshness wording** ("route-B-fresh, not unseen").
12. **The SearchQA examiner evolves detectors only, and ALFWorld "generation" is selection of unused train games**
    with the test exclusion done under TestAccess. Both are honest about where program truth exists.
13. **The "claims we never make" list and the positioning table (§10.1)** against FlowEvo, CoEvoSkills, GRASP and
    Break It Down.
14. **Failure modes with their reporting rules (§10.2),** especially R10 ("engineering yield is a result, not
    hidden") and R17 ("sandbox escape is a security incident, not a result").

Status: DONE 2026-10-21 (second pass). Verdict: needs_revision.
