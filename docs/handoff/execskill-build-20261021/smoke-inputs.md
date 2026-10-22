# Route-B smoke: operator inputs (fivebench-execskill-v1)

Prepared by the operations-prep agent OPS1 on 2026-10-22, 12:00–12:35 (dl clock), for the operator of
`smoke-runbook.md`. **Zero model or API calls.** The only network use on dl was installing packages: the PJLAB PyPI mirror,
and pypi.org through `proxy_on`. Nothing was written under these places:

- `skillopt/`, `scripts/` or `tests/`;
- `/data/coevo5-*`, `/data/execskill-history` or `$SMOKE`.

`$SMOKE/shared/exclusion-consent.json` was not changed (sha256 `77872f24418fd20fd94e372d740e891c35b21dc074244cbf73f9d510a80585a8`,
mtime 09:18). `/data/execskill-20261021-source` was not created. No test pool was opened: the test and reserve ids come
only from the ids-only accessor `skillopt.coevo5.data._part_ids`. Nothing below contains item content. Progress log:
`notes/OPS1-progress.md`.

## Summary

| Task | Result |
|---|---|
| 1. Tools venv | **Ready**: `/data/execskill-tools/hfenv`. All 77 distributions of the pinned env have the same versions there, 21 packages were added (the `datasets` 3.4.1 stack), `pip check` is clean, and the pinned env is unchanged. |
| 2. HF cache | **Ready.** The copy is byte-identical: all 3 sha256 equal the Mac's. It loads offline from the datasets cache alone: validation has 16,980 rows, and its `cache_files` is the copied arrow. |
| 3. Inputs directory | **Ready**: 6 files in `/data/execskill-20261021-pre/inputs/` (directory 700, files 600). |
| 4. SearchQA tail dry run | **Pass**: 11,378 tail items. Blocks A–D replay correctly with pool-only questions. |
| 5. Other runbook inputs | Table in section 1. ALFWorld dry run **passes**: 3,514 games in 108 rooms. Two inputs exist nowhere and nothing produces them: `--control-cells` and `--noise-anchor` (registrar decision). |
| 6. 600-item SearchQA pool | Still not exported (C7b1-2). The frozen reader `data.pool(v3 data, "searchqa")` gives 600 items; its digests are in section 5. |

## 1. Runbook placeholders

### Section 1 of the runbook (shell)

| Item | Path / value | sha256 | Status |
|---|---|---|---|
| `PY` | `/root/continual-alf-prep-20260928/env/bin/python` (3.11.16) | – | present, unchanged |
| `SRC` | `/data/execskill-20261021-source` | – | absent; the main agent creates it in step 2 |
| `PRE` | `/data/execskill-20261021-pre` | – | present (`smoke/shared/`, `inputs/`) |
| `HIST` | `/data/execskill-history` | – | absent; the first non-dry `make-items` creates it |
| `V3` | `/data/coevo5-20261019-v3-run-manifest.json` | `20d9ffcc5ad00a96bb1d90360c2ad43d157aaa72e774bb4109d12b9941e5ad5c` | present |
| `ELUCID` | `/root/.config/weak-solver/elucid.env` | not read | present (mode 600) |
| `GREPO` | `/root/continual-noskill-bcb-20260928-a` | – | present (directory) |
| `ALFWORLD_DATA` | `/root/continual-alf-prep-20260928/data` | – | present; `json_2.1.1/train` holds 3,553 games |

### Section 3 of the runbook (S0)

| Placeholder | Path / value | sha256 | Status |
|---|---|---|---|
| `make-fixtures --p99-workbook-bytes` | `views.workbook.p99` printed by `s0-pool-views` (C7b1's throwaway run: 599,328) | – | produced by the step `s0-pool-views` |
| `import-texts --source` | `/data/coevo5-20261019-v3-pre/texts/texts.json` | file `195f24f4f6354003cc12a39535235e01f2899410e86361dc640143f4322271e1`; record_hash `14187ae5660784c53ed255aaf91d639c2e63e67bc7be54ddf6604551d11dd571` | present. Verified read-only from the dev tree: `coevo5.prelaunch.verify_texts` passes, the version is `fivebench-coevolution-v3-texts-import` (= `protocol.TEXTS_IMPORT`), and all 5 cards match `CARD_IDENTITY`. Its source is `/data/coevo5-20261017-pre/texts-2/texts.json`. |
| `import-sheet-qualification --source` and `s0-collect --sheet-source` | `/data/coevo5-20261019-v3-sheet-train-f/sheet/qualification.json` | file `83ae6be22468eb950715dac0a2b30ce40037c7be1db1603e5b377dc1f836ffa0` | present; the same path as the v3 manifest's `sheet_qualification.path` |
| `import-sheet-qualification --sha256` and `s0-collect --sheet-sha256` | **`acc5c07f76a088969181cf45e8224fae2d4d033aa49385713802cba5338827a1`** = v3 manifest `sheet_qualification.record_hash` | – | Verified: `qualify.load` + `reverify(pinned=acc5c07f…)` pass. **Do not pass the file sha256**: `reverify` compares the record's own hash and refused `83ae6be2…` ("not the pinned one"). Summary: train side, 120 items, 91 qualified. |
| `make-items --bench alfworld --pool-games` | `/data/execskill-20261021-pre/inputs/alfworld-pool-games.json` | `63eeccabfd01567832c72ff7193505b3714b6569ede7217bc498f9bcfb33e614` | Written by OPS1 from the frozen `data.pool(v3 data, "alfworld")`: `{task_id: public.game_file}` for the 57-game pool (39 train + 18 `valid_seen`). Every file exists under `ALFWORLD_DATA`. |
| `make-items --bench alfworld --runtime` | `/data/execskill-20261021-pre/inputs/alfworld-runtime.json` | `840f10c5cc5dea7d9fe4b4ab6a1a289ea6b7ed13eb885126c1807af9d59fa8c2` | Written by OPS1: the v3 manifest's `runtime.alfworld`, verbatim (alfworld_data = `ALFWORLD_DATA`, split `train`, max_steps 50, seed 42, timeout 60 s). The dry run does not read it. |
| `make-items --bench searchqa --fresh-manifest` | `/data/execskill-20261021-pre/inputs/searchqa-sample-manifest.json` | `e65b9f564267beb29f9bd3c937df4fb5a0cea380a24d34d9b6cbec0925e0a742` | Byte copy of the Mac's git-ignored `data/searchqa_fresh_20261012/sample_manifest.json`. It holds ids and hashes only. |
| `--dataset`, `--revision` | `lucadiliello/searchqa`, `c1a979068ba118d85467179b704031d113d689cc` | – | – |
| `--exclude` | `/data/execskill-20261021-pre/inputs/searchqa-exclude.json` | `66536d2678129cbd3e9e27d96248616feab691db79937fd2063495e686884e52` | Written by OPS1: 2,000 ids and 600 questions (section 2). |
| `--cache-sha256` | `/data/execskill-20261021-pre/inputs/searchqa-cache-sha256.json` | `191900ed19f9901c7a333b4e8a4775b401af738b4bf60148a6377b1964d2e354` | Written by OPS1 (section 2). |
| Interpreter for `make-items --bench searchqa` | `/data/execskill-tools/hfenv/bin/python`, with `HF_HOME=/data/execskill-tools/hf-home HF_DATASETS_OFFLINE=1 HF_HUB_OFFLINE=1` | – | Required. The runbook's `$CLI` uses `$PY`, and that env has no `datasets`. |
| `exclude-tests --pinned` | `/data/execskill-20261021-pre/inputs/v3-data-pins.json` | `0f07ad4869a7909ea4a4fe2e8302d55109beadb09db6e5332680a0ae39edc23c` | Written by OPS1: the v3 manifest's `data` block, verbatim (`{paths, sha256}`, 16 pins). That is the object `exclude_tests` and `data.test_panel` take. |
| `exclude-tests --searchqa-supply`, `--alfworld-supply` | `$HIST/supply/searchqa-tail.json`, `$HIST/supply/alfworld-xs.json` | – | produced by the non-dry `make-items` runs |
| `smoke-items --searchqa-pool` | – | – | **Missing.** No command exports it (C7b1-2). See section 5. |
| `smoke-items --alfworld-supply`, `--alfworld-views` | `$HIST/supply/alfworld-xs.json`, `$HIST/supply/alfworld-xs-views.json` | – | produced by the non-dry `make-items --bench alfworld` (about 422 zero-call pre-resets) |
| `smoke-items --fixtures` | `$PRE/fixtures` | – | produced by `make-fixtures` |
| `sandbox-selftest --items <each smoke item file>` | one `--items` each: `$PRE/smoke-items/searchqa.json`, `$PRE/smoke-items/alfworld.json`, `$PRE/fixtures/officeqa.json`, `$PRE/fixtures/livemath.json`, `$PRE/fixtures/spreadsheetbench.json` | – | produced by `make-fixtures` + `smoke-items` |
| `s0-collect --items`, `smoke-make --items <SET=FILE ...>` | the five `SET=FILE` pairs that `smoke-items` prints (also in `$PRE/smoke-items/smoke-items.json`) | – | produced by `smoke-items` |
| `s0-collect --traces` (default `s0.D3_TRACES`) | `/data/feasibility/D3/r3/lt/traces.json` | `4384bbf2e14a5e91a61351711dfe4955cacb9a50405ee33e79682a6e6245a450` (805,018 B) | present: 228 trajectories, 7,524 steps (= `D3_TRAJECTORIES`, `D3_STEPS`) |
| `smoke-make --control-cells` | – | – | **No file, and nothing produces one.** Section 6, item 1. |
| `smoke-make --noise-anchor` | – | – | **No file, and nothing produces one.** Section 6, item 2. |
| `smoke --stage S0 --input` | `$SMOKE/s0/checks.json` | – | produced by `s0-collect` |

### Sections 4 and 5 of the runbook (after S0)

| Placeholder | Source | Status |
|---|---|---|
| `smoke --stage S1 --input`; `branch` and `longest` | S1 | produced by `probe` (S1-b) |
| `smoke-pins.json` `data.research` `{archive, index_sha256}` | The v3 manifest's `research` block: archive `/data/coevo5-20261019-v3-archive`, index_sha256 `7219096cbb7e487439b5598dc12660f639562221c2167744f20c895f8bb2f725` | candidate source only; the operator decides |
| `smoke-pins.json` `sheet_qualification` | the path above and record hash `acc5c07f…` | – |
| `smoke-pins.json` `runtime` | Its `alfworld` entry must equal `inputs/alfworld-runtime.json`, because the pre-reset routing views were made with that runtime. | – |
| `cards`, `contracts`, `fixtures`, `provenance`, `clients` | steps 2–3 and S1 | produced later |

## 2. Inputs directory `/data/execskill-20261021-pre/inputs/`

All files are owned by root. The directory is `drwx------` and every file is `-rw-------`. Every file was created once,
with exclusive create.

| File | Bytes | sha256 | Content (counts only) |
|---|---|---|---|
| `searchqa-sample-manifest.json` | 177,698 | `e65b9f564267beb29f9bd3c937df4fb5a0cea380a24d34d9b6cbec0925e0a742` | version searchqa-fresh-sample-v1; seed searchqa-fresh-20261012; validation split, 16,980 rows; 4 blocks of 1,000 ids each; `native_items_excluded` 2,000; `skipped_before_full` {native_id 447, duplicate_question 0, invalid 0} |
| `searchqa-cache-sha256.json` | 218 | `191900ed19f9901c7a333b4e8a4775b401af738b4bf60148a6377b1964d2e354` | `{"/data/execskill-tools/hf-home/datasets/lucadiliello___searchqa/default/0.0.0/c1a979068ba118d85467179b704031d113d689cc/searchqa-validation.arrow": "30f098509cd1f42fa7a4bf9546b7a8ad6aac5b13c55a281d61d61bb1562b39cb"}`. The key is the `filename` string that `datasets` reports for the validation split's only cache file, which is the shape `supply._pinned_cache` expects. |
| `searchqa-exclude.json` | 123,725 | `66536d2678129cbd3e9e27d96248616feab691db79937fd2063495e686884e52` | `{"ids", "questions"}`. ids: 2,000 sorted strings from `_part_ids`: train 400, val 200, test 400, reserve 1,000. The parts are pairwise disjoint, and digest(sorted ids) is `78dbb3dd…`. questions: the 600 pool questions (v3 train panel 400 via `data._load(.., "train")`, then val 200 via `data._load(.., "val")`, in panel order). All 600 are distinct after normalization, and the pool ids equal the train + val part ids. |
| `alfworld-pool-games.json` | 9,653 | `63eeccabfd01567832c72ff7193505b3714b6569ede7217bc498f9bcfb33e614` | 57 `{task_id: absolute game file}` |
| `alfworld-runtime.json` | 206 | `840f10c5cc5dea7d9fe4b4ab6a1a289ea6b7ed13eb885126c1807af9d59fa8c2` | the v3 `runtime.alfworld` block |
| `v3-data-pins.json` | 3,657 | `0f07ad4869a7909ea4a4fe2e8302d55109beadb09db6e5332680a0ae39edc23c` | the v3 `data` block |

## 3. Commands run (tasks 1–4)

All commands ran on dl through `ssh -o BatchMode=yes -o ConnectTimeout=20 dl.dulin+root.ailab-datatools.ws@h.pjlab.org.cn '<cmd>'`
unless they are marked (Mac).

### Task 1: tools venv `/data/execskill-tools/hfenv`

```bash
mkdir -p /data/execskill-tools
/root/miniconda3/envs/skill_validation/bin/python -m venv --system-site-packages /data/execskill-tools/hfenv   # pip 24.0, Python 3.11.16
/root/continual-alf-prep-20260928/env/bin/python -m pip freeze --local > /data/execskill-tools/pinned-env-requirements.txt   # 56 lines
/root/continual-alf-prep-20260928/env/bin/python -m pip freeze \
  | sed "s#^packaging @ .*#packaging==26.3#" > /data/execskill-tools/pinned-env-constraints.txt                 # 74 lines (the conda direct-URL line of packaging -> its version)
printf "%s\n" datasets==3.4.1 huggingface-hub==0.29.3 pyarrow==19.0.1 pandas==2.2.3 fsspec==2024.12.0 dill==0.3.8 \
  multiprocess==0.70.16 xxhash==3.5.0 aiohttp==3.11.12 filelock==3.18.0 > /data/execskill-tools/hf-requirements.txt
# The install (attempts 1-4 failed, see below); attempt 5 succeeded (log /data/execskill-tools/pip-install.log):
bash -ic 'proxy_on && /data/execskill-tools/hfenv/bin/python -m pip install --no-input \
  -r /data/execskill-tools/pinned-env-requirements.txt -r /data/execskill-tools/hf-requirements.txt \
  -c /data/execskill-tools/pinned-env-constraints.txt'
```

The datasets stack is pinned to the versions of the Mac env that made the 10/12 draw (Mac miniconda base: datasets 3.4.1,
huggingface-hub 0.29.3, pyarrow 19.0.1, pandas 2.2.3, fsspec 2024.12.0, dill 0.3.8, multiprocess 0.70.16, xxhash 3.5.0,
aiohttp 3.11.12, filelock 3.18.0). This was OPS1's choice. The brief asked only for `datasets==3.4.1`, but this way no
untested huggingface-hub/pyarrow combination is used. numpy stays the pinned env's 2.4.6 (the Mac had 2.2.4). The
constraints file fixes every pinned package at its current version.

Failed attempts. Each is kept as `pip-install-attempt{1..4}.log`; none installed anything.

- Attempts 1–2: the PJLAB mirror returned HTTP 504 (gateway time-out) on the uncached `spacy-3.8.16` wheel.
- Attempt 3: as attempt 2, with `--find-links /data/execskill-tools/wheels`. pip still chose the mirror URL.
- Attempt 4: the mirror returned HTTP 504 on `pyarrow-19.0.1`.

The fix: the three large wheels were fetched from PyPI through the proxy, with pip's mirror config ignored. Their sha256
equal the hashes the mirror's own index lists. They were then installed locally:

```bash
bash -ic 'proxy_on && /data/execskill-tools/hfenv/bin/python -m pip download --no-input --no-deps --only-binary=:all: \
  --isolated --index-url https://pypi.org/simple --timeout 120 -d /data/execskill-tools/wheels spacy==3.8.16'
bash -ic 'proxy_on && /data/execskill-tools/hfenv/bin/python -m pip download --no-input --no-deps --only-binary=:all: \
  --isolated --index-url https://pypi.org/simple --timeout 120 -d /data/execskill-tools/wheels pyarrow==19.0.1 pandas==2.2.3'
#   spacy-3.8.16-cp311-...manylinux_2_28_x86_64.whl  bc4e59799dcb0eb4823e5946515d3ca0d503ff78ef2502172d4b59ee0fc567ec
#   pyarrow-19.0.1-cp311-...manylinux_2_28_x86_64.whl 49a3aecb62c1be1d822f8bf629226d4a96418228a42f5b40835c1f10d42e4db6
#   pandas-2.2.3-cp311-...manylinux2014_x86_64.whl    c124333816c3a9b03fbeef3a9f230ba9a737e9e5bb4060aa2107a86cc0a497fc
/data/execskill-tools/hfenv/bin/python -m pip install --no-input --no-deps --no-index /data/execskill-tools/wheels/spacy-3.8.16-*.whl
/data/execskill-tools/hfenv/bin/python -m pip install --no-input --no-deps --no-index \
  /data/execskill-tools/wheels/pyarrow-19.0.1-*.whl /data/execskill-tools/wheels/pandas-2.2.3-*.whl
```

Verification:

```bash
/data/execskill-tools/hfenv/bin/python -m pip freeze > /data/execskill-tools/hfenv-freeze.txt        # 95 lines
/root/continual-alf-prep-20260928/env/bin/python -m pip freeze > /data/execskill-tools/pinned-env-freeze.txt   # 74 lines
diff <(sed "s#^packaging @ .*#packaging==26.3#" pinned-env-freeze.txt) pinned-env-constraints.txt     # identical: pinned env untouched
# importlib.metadata {name: version} of both interpreters: changed or missing = {} (77 pinned dists); added = 21
/data/execskill-tools/hfenv/bin/python -m pip check        # No broken requirements found.
cd /tmp && /data/execskill-tools/hfenv/bin/python -I -c "import datasets, pyarrow, pandas"   # datasets 3.4.1, pyarrow 19.0.1, pandas 2.2.3, huggingface_hub 0.29.3, numpy 2.4.6
```

The 21 added packages: aiohappyeyeballs 2.7.1, aiohttp 3.11.12, aiosignal 1.4.0, attrs 26.1.0, datasets 3.4.1,
dill 0.3.8, filelock 3.18.0, frozenlist 1.8.0, fsspec 2024.12.0, huggingface-hub 0.29.3, multidict 6.9.1,
multiprocess 0.70.16, pandas 2.2.3, propcache 0.5.4, pyarrow 19.0.1, python-dateutil 2.9.0.post0, pytz 2026.5, six 1.17.0,
tzdata 2026.5, xxhash 3.5.0, yarl 1.25.1.

In `pip freeze`, spacy 3.8.16 (same version as the pinned env), pyarrow and pandas appear as `@ file:///data/execskill-tools/wheels/...`.

Files: `pinned-env-requirements.txt` `0d13657a…`, `pinned-env-constraints.txt` `fe430df4…`, `hf-requirements.txt`
`7260598c…`, `hfenv-freeze.txt` `68a6b970…`, `pinned-env-freeze.txt` `fa769b7b…` (all in `/data/execskill-tools/`).

### Task 2: HF cache under `HF_HOME=/data/execskill-tools/hf-home`

```bash
# (Mac) cd ~/.cache/huggingface/datasets/lucadiliello___searchqa/default/0.0.0/c1a979068ba118d85467179b704031d113d689cc/
shasum -a 256 dataset_info.json searchqa-train.arrow searchqa-validation.arrow
#   29f9649da447897e65345ad2e7c4bf1efe81f22e54b5ad1a3e9bc919d725b437  dataset_info.json         (1,328 B)
#   bae2f12c665e5d9bfc638a4ea52108cf0cfd519ed74455636576c6f85064288b  searchqa-train.arrow      (484,084,416 B)
#   30f098509cd1f42fa7a4bf9546b7a8ad6aac5b13c55a281d61d61bb1562b39cb  searchqa-validation.arrow (69,660,568 B)
D=/data/execskill-tools/hf-home/datasets/lucadiliello___searchqa/default/0.0.0/c1a979068ba118d85467179b704031d113d689cc
mkdir -p $D                                                                                    # (dl)
rsync -a -e "ssh -o BatchMode=yes -o ConnectTimeout=20" ./dataset_info.json dl.dulin+root.ailab-datatools.ws@h.pjlab.org.cn:$D/   # (Mac)
chown root:root $D/dataset_info.json                                                           # (dl)
rsync -a --no-o --no-g -e "ssh -o BatchMode=yes -o ConnectTimeout=20" ./searchqa-validation.arrow ./searchqa-train.arrow \
  dl.dulin+root.ailab-datatools.ws@h.pjlab.org.cn:$D/                                          # (Mac), 49 s
sha256sum $D/*                                                                                 # (dl): the same three hashes
cd /tmp && env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  HF_HOME=/data/execskill-tools/hf-home HF_DATASETS_OFFLINE=1 HF_HUB_OFFLINE=1 /data/execskill-tools/hfenv/bin/python -I -c '
from datasets import load_dataset
ds = load_dataset("lucadiliello/searchqa", revision="c1a979068ba118d85467179b704031d113d689cc")
print({k: ds[k].num_rows for k in ds}, [f["filename"] for f in ds["validation"].cache_files])'
#   {"train": 117384, "validation": 16980}; validation cache_files = [$D/searchqa-validation.arrow]
```

Offline loading worked from the datasets cache alone ("Using the latest cached version ... (offline mode is enabled)"),
so the hub snapshot `~/.cache/huggingface/hub/datasets--lucadiliello--searchqa/` was **not** copied. The loader created a
lock file and a `modules/` directory under `hf-home`. The arrow files are unchanged: their sha256 was re-read after
loading, when `searchqa-cache-sha256.json` was written.

### Task 3: inputs

```bash
# (Mac) the manifest, piped:
ssh ... 'umask 077; mkdir -p /data/execskill-20261021-pre/inputs && chmod 700 /data/execskill-20261021-pre/inputs \
  && test ! -e /data/execskill-20261021-pre/inputs/searchqa-sample-manifest.json \
  && cat > /data/execskill-20261021-pre/inputs/searchqa-sample-manifest.json \
  && chmod 600 /data/execskill-20261021-pre/inputs/searchqa-sample-manifest.json' < data/searchqa_fresh_20261012/sample_manifest.json
```

`searchqa-cache-sha256.json` was written in the tools venv (same env vars as task 2, cwd `/tmp`, `python -I`):

```python
v = load_dataset("lucadiliello/searchqa", revision="c1a979068ba118d85467179b704031d113d689cc")["validation"]
files = [str(e["filename"]) for e in v.cache_files]
value = {name: hashlib.sha256(open(name, "rb").read()).hexdigest() for name in files}
assert list(value.values()) == ["30f098509cd1f42fa7a4bf9546b7a8ad6aac5b13c55a281d61d61bb1562b39cb"]
os.umask(0o077); json.dump(value, open(OUT, "x"), indent=1); os.chmod(OUT, 0o600)
```

`searchqa-exclude.json` was written with
`cd /data/execskill-dev && PYTHONDONTWRITEBYTECODE=1 /root/continual-alf-prep-20260928/env/bin/python -B - <<EOF ... EOF`:

```python
from skillopt.coevo5 import data
pinned = json.load(open("/data/coevo5-20261019-v3-run-manifest.json"))["data"]
parts = {p: data._part_ids(pinned, "searchqa", p) for p in ("train", "val", "test", "reserve")}   # ids only
union = set().union(*map(set, parts.values()))
train, val = data._load(pinned, "searchqa", "train"), data._load(pinned, "searchqa", "val")
pool_tasks = train["tasks"] + val["tasks"]
assert {str(t["task_id"]) for t in pool_tasks} == set(parts["train"]) | set(parts["val"])
value = {"ids": sorted(union), "questions": [t["public"]["question"] for t in pool_tasks]}
os.umask(0o077); json.dump(value, open(OUT, "x"), ensure_ascii=False); os.chmod(OUT, 0o600)
# printed: part counts 400/200/400/1000, union 2000, disjoint, 600 questions, 600 distinct normalized
```

The same interpreter, with `ALFWORLD_DATA` set, wrote the three task-5 files (with `open(.., "x")`, umask 077, chmod 600):

- `alfworld-pool-games.json` = `{i["task_id"]: i["public"]["game_file"] for i in data.pool(pinned, "alfworld")}`;
- `alfworld-runtime.json` = `manifest["runtime"]["alfworld"]`;
- `v3-data-pins.json` = `manifest["data"]`.

### Task 4: SearchQA tail dry run (dev tree, writes nothing)

```bash
cd /data/execskill-dev && env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  HF_HOME=/data/execskill-tools/hf-home HF_DATASETS_OFFLINE=1 HF_HUB_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
  /data/execskill-tools/hfenv/bin/python -B scripts/run_execskill.py make-items --bench searchqa \
  --history-root /data/execskill-history --dry-run \
  --fresh-manifest /data/execskill-20261021-pre/inputs/searchqa-sample-manifest.json \
  --dataset lucadiliello/searchqa --revision c1a979068ba118d85467179b704031d113d689cc \
  --exclude /data/execskill-20261021-pre/inputs/searchqa-exclude.json \
  --cache-sha256 /data/execskill-20261021-pre/inputs/searchqa-cache-sha256.json
# run in the background, log /data/execskill-tools/logs/make-items-searchqa-dryrun.log; the first launch failed only
# because /usr/bin/time does not exist on dl (no Python started)
```

The flags were checked with `--help` (`make-items` and every subcommand the runbook names). The code was read in the
dev tree at these sha256:

- `scripts/run_execskill.py` `182cba01…`;
- `skillopt/execskill/supply.py` `c58c9c72…`;
- `skillopt/execskill/protocol.py` `cf353612…`;
- `scripts/make_searchqa_fresh_sample.py` `8966294e…`;
- `skillopt/coevo5/data.py` `f987a06b…`.

## 4. Dry-run results

**SearchQA tail** (12:20 dl, 4.8 s, exit 0):

```json
{"bench": "searchqa", "counts": {"items": 11378}, "written": false}
```

**Key answer: the replay of blocks A–D reproduces with pool-only questions.** Every check in `searchqa_tail` passed: each
block id was found in order, every skipped row had a frozen reason, the skipped counts equal the manifest's
`skipped_before_full` (native_id 447), and all four block hashes are equal. The frozen 10/12 draw also deduplicated
against test and reserve questions, but that changed nothing: it skipped 0 rows as duplicate questions.

A read-only diagnostic then called the same `supply.searchqa_tail` plus a recount of the walk. It printed counts only:

- 16,980 rows = 4,000 drawn + 447 native ids skipped before the draw was full + 11,378 kept in the tail + 1,155 tail
  skips (native_id 1,153, duplicate_question 2).
- So 1,600 native ids lie in the validation split.
- Tail positions run from 4,001 to 15,378. The tail shares no id with the exclusion ids or the blocks.
- digest(sorted tail ids) = `d8677ced4a08d4321edb9b800d39bca28f10c487ebe636e479b6bb909ad7786e`.

**ALFWorld** (12:22 dl, 81 s, exit 0; it only reads and hashes the 3,553 train game files, makes zero calls and does no reset):

```bash
cd /data/execskill-dev && ALFWORLD_DATA=/root/continual-alf-prep-20260928/data PYTHONDONTWRITEBYTECODE=1 \
  /root/continual-alf-prep-20260928/env/bin/python -B scripts/run_execskill.py make-items --bench alfworld \
  --history-root /data/execskill-history --dry-run --data-root /root/continual-alf-prep-20260928/data \
  --pool-games /data/execskill-20261021-pre/inputs/alfworld-pool-games.json \
  --runtime /data/execskill-20261021-pre/inputs/alfworld-runtime.json
```

```json
{"bench": "alfworld", "counts": {"items": 3514, "rooms": 108, "task_types": {"look_at_obj_in_light": 303,
 "pick_and_place_simple": 783, "pick_clean_then_place_in_recep": 641, "pick_cool_then_place_in_recep": 527,
 "pick_heat_then_place_in_recep": 452, "pick_two_obj_and_place": 808}}, "written": false}
```

3,514 is the registered `ALFWORLD_UNUSED_GAMES`, and 108 the registered room count. Neither dry run created
`/data/execskill-history`, and no `__pycache__` was written in the dev tree.

## 5. The 600-item SearchQA pool (ticket C7b1-2, not exported)

The 600 items come from the frozen `skillopt.coevo5.data.pool(pinned, "searchqa")`, with pinned = the v3 `data` block
(= `inputs/v3-data-pins.json`). It returns the train items and then the val items, each labelled with its `part`. Its parts:

| Part | Reader | File (v3 pin) | sha256 |
|---|---|---|---|
| train, 400 | `data._load(pinned, "searchqa", "train")`, which is `datasets.load_panel` on the v3 training panel | `/root/continual-searchqa-long-20261001-study/data/panel.json` | `868f41862100e542158686e5f4b46dc96a0dcb54250b8827da3c220a3280269a` |
| val, 200 | `data._load(pinned, "searchqa", "val")`, as the stage tool builds it: the rows of the split's 200 val ids, through `datasets.import_searchqa` (partition skill_confirmation, revision `skillopt-searchqa-native-val:fivebench-split-v2:<split record_hash[:12]>`). Val is allowed; nothing here reads test. | `/root/fivebench-split-20261005-source/data/searchqa_split/val/items.json` | `c6285bdfd7ce62ae72c2bd49797cd01a1d1782fd8fb79f0eb5416b54af56fd40` |
| ids of the parts | `data._part_ids` | `/root/fivebench-split-20261005-v2/split_manifest.json` | `48fd257224de9e5ebb894b75b1646c3a4ed061d20b139017518cde990196744e` |

Each item has the keys `{benchmark, task_id, family_id, part, public, private}`, which is the shape `s0.smoke_items` reads.
`smoke_items` applies `supply.order` itself, so the order inside the file does not change the result.

Digests (`validator_pilot.api.digest`), computed read-only with nothing written:

| What | Digest |
|---|---|
| the 600 ids, sorted | `901fb49e219da901e4e910db6657d000241bc9bf6a013a32f67869680b1b3a62` |
| the 600 ids in `supply.order("searchqa", pool)` | `332df1bffc67468eb76ea206af584e6a4c790facc32ab3f374fdf8e215e00db2` |
| the 600 items in that order | `120f123facc30534c6902cfbc393add22c04e45d7d178a5df84b366eef28c473` |
| the smoke slice (the last 280 of the order: 198 train + 82 val), ids in order | `7033d48d685c4cbabfa55ee7b2a52779d6ea78ecc1a279396324020d94aeb169` |
| the run slice (300), ids in order | `50ce48330655cf2d64b0bdd6fefa9e43891bc4456691cbce2865a9e9f14482e5` |

When C7b1-2's export exists, its file should reproduce the first three digests.

## 6. Open problems and decisions needed

1. **`--control-cells` (registrar).** `smoke.make` needs a JSON list of unique, non-empty cell ids. An empty list `[]`
   also passes the check. The receipts of these cells are classed CONTROL: they are listed, and excluded from the
   ≥ 300 production receipts (Codex F19).
   - A cell id is `coevo5.cells.cell_id(unit, arm, task_id, run)`, the first 32 hex digits of
     digest({unit, arm, task_id, run}). For S2 the unit is `smoke/S2/<set>`, the task_id `<bench>/<item id>`, and run
     runs from 0 to runs−1.
   - The fault-drill items are `fixtures.FX_CRASH_SUBSET`, 2 per fixture bench. fx-crash fires under the package arm X.
     Not verified by OPS1: whether it also fires under P (P replaces the note hooks with shams) and under twin arms
     that keep it.
   - The twin arms are drawn at dispatch time (`smoke._twins`), so the full list cannot be known before S2 unless the
     registrar fixes which cells count.
   - The registration does not enumerate them, and no command writes them. Decide which cells are fault drills (fx-crash
     only, or the S4 drill too) and who writes the file.
2. **`--noise-anchor` (registrar).** It must be the JSON object `{"searchqa": float > 0, "alfworld": float > 0}`: "the
   registered per-item SD of a same-text paired difference". `sn1_noise` divides the measured SD of the 0/1 score
   differences by it and flags a ratio above 1.25.
   - The registration (§3.3) gives single-contrast MDE anchors in points, not per-item SDs: SearchQA 3.0 at 1,000 × 1,
     ALFWorld 8.4/1.135 at 200 games. protocol.py has no such constant.
   - An illustration of the scale only, **not a registered value**: SD = anchor / K × √n / 100 with K = 2.487 gives
     about 0.381 for SearchQA and about 0.421 for ALFWorld. The unit is score difference, not points.
3. **The SearchQA pool export (C7b1-2)** is still missing. Section 5 gives the frozen reader and its digests. The
   step order is blocked behind it:
   1. `make-fixtures` and the non-dry `make-items` for both benches;
   2. `smoke-items`, which needs the pool;
   3. `sandbox-selftest`;
   4. `s0-collect`;
   5. `smoke-make`.

   `exclude-tests` needs both non-dry supply files.
4. **The interpreter for the SearchQA step.**
   - Run `make-items --bench searchqa` (dry and real) with `/data/execskill-tools/hfenv/bin/python` and
     `HF_HOME=/data/execskill-tools/hf-home HF_DATASETS_OFFLINE=1 HF_HUB_OFFLINE=1`, from `$SRC` once it exists.
   - The pinned key in `searchqa-cache-sha256.json` is the absolute arrow path under that `HF_HOME`. Any other
     `HF_HOME` or path fails `_pinned_cache` ("The cache files differ from the pinned list").
   - In offline mode, `datasets` takes "the latest cached" configuration whatever the revision. Keep only this one
     revision in that `HF_HOME`; `_pinned_cache` still checks the revision in the path.
   - `prelaunch.launch_env` removes only `OPENAI_API_KEY` and `OPENAI_BASE_URL`, so the HF variables reach `datasets`
     (confirmed in the dry run).
5. **What the supply record does not pin.** `_searchqa_items` records the fresh-manifest sha256, the dataset, the
   revision and the cache sha256. It does not record the exclusion file's sha256, the interpreter or the `datasets`
   version. This document records them: exclusion `66536d26…`, hfenv with `datasets` 3.4.1.
6. **Sealed content on dl, as designed.** The copied validation arrow holds all 16,980 source rows. That includes the
   rows of sealed blocks C and D, which the manifest names by id. `searchqa_tail` keeps them in memory only, but anyone
   who reads the arrow together with the manifest could rebuild C and D. The cache files are mode 644 under
   `/data/execskill-tools/hf-home`, and every process runs as root. Tighten the modes if wanted.
7. **The PJLAB PyPI mirror fails on large uncached wheels** (HTTP 504). The workaround is to download from PyPI through
   `proxy_on`, check the sha256 against the mirror's index, and install with `--no-deps --no-index`.
8. **Changes since the runbook (FYI).** The dev tree's `smoke.BUILT_STAGES` is now `("S2", "SN1", "SE6", "S4")`, while
   runbook §0 still says S3, S4 and S-E6 are unbuilt. C7c edited `smoke.py` and `step.py` after 12:00. Neither file is
   used by `make-items`.
9. **Not changed by this work:** blocker C7b1-3 (the SpreadsheetBench scorer bound to `/data/coevo5-20261019-v3-source-f`)
   still blocks the S0 sheet row and S2.
