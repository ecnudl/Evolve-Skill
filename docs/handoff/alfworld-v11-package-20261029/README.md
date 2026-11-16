# alfworld-v11 accepted package (route B v2.9.7, 2026-10-29)

Zero-call copy of the frozen artifacts of run root `/data/execskill-20261028-alfworld-v11` (chain D, deepseek-v4-flash via
northgate; engineer GLM-5.3; judges GLM-5.3 + deepseek-v4-flash; code dl `ba2beeb`; manifest `e996f10a…`). Launched
2026-10-28 17:25:16, ended 2026-10-29 02:42:25 (EXIT 0), 71,755,052 tokens.

Decision: ACCEPT under `practical-v2-9-7-pooled`. Acceptance A* = 150 games (40 rooms, split-v1 slices), one run per cell:
S (parent, no program) 83, C (same-text duplicate) 93, P_y (placebo) 92, S' (candidate) 124 wins.
J1 S' − (S+C)/2 = +24.0 points (47 up / 2 down, CI +17.3..+30.7); S'−S +27.3, S'−C +20.7, S'−P_y +21.3; C−S +6.67
(two-sided p 0.038, the S and C requests are byte-identical, so this is noise); format violations 0/0; faults 0.
Withholding twins: without p-alfworld-1-14 −18.7 points (CI 9.3..28.0); p-alfworld-1-15 0.0; p-alfworld-1-6 −1.6.

The hold-out test was read once at the chain end (pre-registered); its summary is NOT in this folder and had not been
opened when this copy was made. Any ALFWorld test result must be reported together with alfworld-v10's (F 92 = C 92 / 134).

Files: `packages/7d814ba5….json` (package record, order p-alfworld-1-15, p-alfworld-1-14, p-alfworld-1-6),
`procedures/<sha256>.json` (the three procedures with source, header, description, hooks, replay tests),
`s1-alfworld/accept/attempt-1/decision/decision.json` (the sealed acceptance decision), `s1-alfworld/step-summary.json`
(trimmed step record: decision, training rounds, audit token summary), `chain-complete.json`.

- `p-alfworld-1-14` — empty-receptacle memory: remembers every `go to <receptacle>` and the observation after it; a
  receptacle seen empty on its last visit and visited 2+ times is listed and discouraged; from step 12 on lists up to 8
  unvisited `go to` targets whose receptacle type word appears in the room description. Carries the effect.
- `p-alfworld-1-15` — action counts (warn at 3+ non-navigation, 4+ navigation, 5+ look/inventory; discourage at 4+),
  a note after 2+ consecutive "Nothing happens", and a step-budget reminder every 5 steps from step 20.
- `p-alfworld-1-6` — an action that returned "Nothing happens" twice is flagged as possibly not applicable and discouraged.

All three read only hook-visible data (actions, observations, admissible commands, the initial observation).
