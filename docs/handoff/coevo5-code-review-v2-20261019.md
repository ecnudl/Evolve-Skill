# Codex 代码审查：第 2 版代码（一轮，2026-10-19 09:59）

> 原文照录（gpt-6-astra，推理强度 ultra，只读；只把本机绝对路径的链接改成相对链接）；处理见 [第 2 版改动登记](coevo5-registration-v2-delta-20261019.md) §13。

1. **Smoke bypasses the research leakage check — [smoke.py:139](../../skillopt/coevo5/smoke.py#L139).**  
   **Failing state:** the first proposal contains a single-word reference collision, and no other proposal dispatches research. `step._research()` records `skipped_answer_word`, but `paths()` interprets the missing dispatch as an unexercised path and sends the same rule to `research.request()` anyway. It also sends previously rejected questions without screening. This violates delta §7.  
   **Minimal fix:** reuse the production pre-dispatch checks for both rule and question, including the fallback question; record a skipped path when dispatch is prohibited.

2. **Malformed examiner edits still discard valid siblings — [examiner.py:320](../../skillopt/coevo5/examiner.py#L320).**  
   **Failing input:** a revision containing `{"op":"remove","id":[],"basis":"shown","evidence":["task1"]}` followed by a valid, evidenced edit. The membership check at line 297 raises `TypeError`; the per-edit handler catches only `ValueError`. `Roles.ask()` consequently invalidates the entire response, losing the valid sibling and the dropped-edit record. A collection-valued `check.name` causes the same failure. This violates delta §6.  
   **Minimal fix:** validate identifier/check-name types before lookup, or catch `TypeError` within the per-edit boundary. Confirmed with an in-memory fake.

3. **The formal report still uses v1’s readout registry — [readout.py:286](../../skillopt/coevo5/readout.py#L286), [readout.py:348](../../skillopt/coevo5/readout.py#L348), [report.py:465](../../skillopt/coevo5/report.py#L465).**  
   **Failing state:** E-glm, I-glm and NoSkill-glm complete normally; baselines remain unrun. The report omits NoSkill’s five stage-0 units and never computes the scaffold difference. It still presents P1–P4 as primary tests and emits v1 combined claims. An in-memory fixture with five E updates and established positive learning gain nevertheless produced `claim1=False` and `claim2=False` because the baselines were absent. This contradicts delta §§1 and 9.  
   **Minimal fix:** implement a v2 registry including NoSkill stage 0 and the descriptive scaffold difference; report E learning gain and Q1–Q3 under the registered v2 interpretation, removing v1 baseline tests and combined claims.

Lower-priority remarks:

- [analyst.py:174](../../skillopt/coevo5/analyst.py#L174): `transfer={"none":""}` passes despite §4 requiring a reason. Remove `empty=True`.
- [prelaunch.py:190](../../skillopt/coevo5/prelaunch.py#L190), [prelaunch.py:228](../../skillopt/coevo5/prelaunch.py#L228): omitting `--previous` refetches the v1 documentation pages, and validation accepts the archive without `carried.json`. Require the previous archive and the complete expected carry set for v2.
