# Upstream ZebraLogic grid-mode prompt (ZeroEval), test fixture

- Repository: https://github.com/WildEval/ZeroEval (licence Apache-2.0, per the GitHub licence API, fetched 2026-10-25 13:04 CST).
- `ZEBRA_GRID.py.txt` = `src/templates/ZEBRA_GRID.py` at branch `main` (main = commit 8c1485edf12c6efb5f69135a562927c5ad484059,
  2025-04-14), byte for byte; the last commit touching this file is 469406eee2bd74e432bfc4763ccf5aa310bda79c (2024-07-13).
  sha256: bbeed4d971d19dc04b84e888255598ab1d35c3de6701aad240d7d26abfd4bd08 (1,435 bytes). Stored with a `.txt` suffix so that
  nothing imports or collects it.
- `apply_lgp_grid_template.py.txt` = lines 32-43 of `src/_TEMPLATES.py` at the same `main` commit: the official rendering.
- Used only by `tests/test_execskill_zpc_prompt_and_paths.py` (independent byte-exact rendering check of zebra-pc-v1);
  never read at runtime. Internal research use with attribution.
