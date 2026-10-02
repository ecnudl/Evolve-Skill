# Native evaluation runtime setup

These are deployment instructions, **not evidence of five-domain method
effectiveness**. On 2026-09-28 a Linux Docker smoke ran three authored workbook
cases: correct output passed, wrong output failed, missing dependency remained
unknown. It used 0 model calls and 5 containers including two dependency probes;
BigCodeBench's full environment was absent. Local receipts are retained under
`outputs/continual_eval/native_smoke_20260928/`. KOR's official scoring and
ALFWorld episodes still need their own environment acceptance. Do not start
paid baselines until dataset readiness and each relevant native smoke pass.

Later on the same date, the official KOR scorer passed five positive and five
negative controls and a 500-task development No-Skill run started. The full
BigCodeBench image was loaded and two authored native tests passed, but its
real dataset and full dependency coverage remain unqualified. ALFWorld assets
and six-type zero-model native controls are now exercised; this is not GLM
accuracy. Spreadsheet's real development data revealed coordinate/cache issues
despite complete files, so paid inference is deferred. See the maintained
[baseline status](../../../docs/skill-validation-baselines-20260928.md).

## KOR-Bench and SpreadsheetBench

Build one small Linux image for both. Select a Python 3.11 base; record the
downloaded manifest digest, then supply that digest to the Docker build:

```sh
docker pull python:3.11-slim
docker image inspect python:3.11-slim --format '{{json .RepoDigests}}'
docker build --build-arg BASE_IMAGE='python@sha256:REPLACE_WITH_RECORDED_DIGEST' -t evolve-skill-native:initial skillopt/continual_eval/runtime
docker image inspect evolve-skill-native:initial --format '{{.Id}}'
```

Set each benchmark's frozen runtime `image` to the resulting **local
`sha256:...` ID**, not the mutable build tag. Record the base digest, final ID,
build log, Dockerfile, architecture and installed package manifest. Our runtime
never pulls an image automatically. The requirements pin direct packages; the
final image identity, not these pins alone, binds transitive dependencies.

The implemented fixture smoke can be run on the evaluation machine after
building an image (replace the ID and paths; use a fresh output directory):

```sh
python skillopt/continual_eval/runtime/smoke_native.py --image sha256:REPLACE_WITH_LOCAL_IMAGE_ID --backends skillopt/continual_eval/backends.py --output outputs/continual_eval/native-smoke-new
```

The verified lightweight image was
`sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd`
(Linux amd64). This local ID is not a public registry download location. Its
base image was the preinstalled Python image
`sha256:b8fe4ce3655e95f7f22c2a87d8e03a2f1f0cedc488a8e9adf18cc5a18cfdf401`;
the build used the existing local tag with `--pull=false` and recorded that ID.
Only the image build used the developer-machine proxy; all smoke containers
ran with networking disabled.

KOR needs an operator-reviewed official checkout, not model-generated evaluator
code. Freeze the checkout revision and hash all three files:

```sh
git clone https://github.com/KOR-Bench/KOR-Bench.git /ABS/kor-bench
git -C /ABS/kor-bench rev-parse HEAD
shasum -a 256 /ABS/kor-bench/eval/eval_utils.py /ABS/kor-bench/utils/common.py /ABS/kor-bench/config/config_wrapper.py
```

Set `kor_repo`, `kor_eval_sha256`, `kor_common_sha256` and
`kor_config_sha256` in the KOR runtime. The backend verifies source bytes before
importing them **inside Docker**. The official puzzle scorer can evaluate model
expressions, so importing it on the host is intentionally forbidden. Five
single-question categories are supported; mixed-question modes are not.
Source: [official evaluator](https://github.com/KOR-Bench/KOR-Bench/blob/main/eval/eval_utils.py)
and [official dependencies](https://github.com/KOR-Bench/KOR-Bench/blob/main/requirements.txt).

Spreadsheet generation uses one program from the first input workbook preview,
then independently executes it on every input case. The output coordinates
(`answer_position`) are a public task requirement and must match the scoring
region; expected cell values remain hidden. Only `input.xlsx` is provided;
the program must write `output.xlsx`. Generated Python never executes
on the host and never receives gold workbooks. Native cell comparison runs only
after generation. The image includes openpyxl, pandas and numpy, **not a formula
recalculation engine**: absent cached formula values stay unknown. Install
openpyxl in the host evaluator environment too. This is the initial codegen
profile, not a full spreadsheet GUI/tool agent.

## BigCodeBench: use the full official evaluator image

Do not use the small image above or install only `pip install bigcodebench`.
BigCodeBench's test dependency set includes numerical, ML, vision, web and other
packages; some pins target older Python versions. Use the official evaluation
image and record its digest/architecture:

```sh
docker pull bigcodebench/bigcodebench-evaluate:latest
docker image inspect bigcodebench/bigcodebench-evaluate:latest --format '{{.Id}} {{json .RepoDigests}} {{.Architecture}}'
```

The mutable tag is only for initial acquisition; `runtime.image` must be the
recorded local ID or repository digest. If rebuilding, follow the pinned
upstream image/environment recipe and its **full** evaluation requirements,
not the light requirements in this directory. See
[official setup](https://github.com/bigcode-project/bigcodebench/blob/main/ADVANCED_USAGE.md)
and [full requirements](https://github.com/bigcode-project/bigcodebench/blob/main/Requirements/requirements-eval.txt).

The worker calls the installed official `untrusted_check`, retaining its test
logic. The inspected upstream evaluator has a **240-second native minimum**;
the host default wall limit is 300 seconds. Passing `gt_time_limit=60` does not
reduce that minimum. Missing dependencies, outer timeouts and ambiguous runtime
failures remain unknown. Native assertion failures remain failures. Native
timeout results are retained in metrics but separated from semantic failures.

Our default memory is 4096 MiB, below upstream's documented 30 GiB address-space
default. Choose and freeze the study budget before running; `memory_mb=30720`
is supported if hardware permits. Run independent trusted reference controls in
the same isolated image before interpreting failures. Dependency-import
readiness alone does **not** validate every task's environment. This initial
restricted profile is not automatically comparable to published leaderboard
numbers, especially for network/system-resource-dependent tasks.

## ALFWorld and SearchQA

SearchQA uses the repository's EM/F1 scorer without Docker. ALFWorld requires
the official text environment and downloaded data in a Linux Python environment;
follow [ALFWorld installation](https://github.com/alfworld/alfworld#installation).
Set `ALFWORLD_DATA` before starting the runner and use the same absolute path in
`runtime.alfworld_data`. Install the repository's ALFWorld dependencies as well.
The public game file, `traj_data.json` and logic assets must be present and
hash-frozen in the panel. `alfworld_split`, `seed` and `max_steps` are frozen
settings. Each position creates and tears down a fresh native environment;
only public observations/actions enter prompts, never the expert plan or score.

The latest new-entry adapter narrows native dataset discovery to the frozen
game's own directory, without editing the historical vendor config. It also
synchronizes the environment TimeLimit with `max_steps` (default 50, allowed
1..150), then attempts bounded normal closure before terminate/kill and verifies
worker exit. Earlier snapshots remain unchanged; these runtime fixes need a
new frozen source/run, not an in-place resume of an old ALF protocol.

## Isolation and scope

The new backend mounts a detached task request read-only, disables networking,
drops capabilities, runs as an unprivileged user, and enforces CPU/memory/PID,
output and wall limits. It does not mount the repository, API credentials,
Docker socket or reference workbooks during spreadsheet solving. Cleanup is
limited to the exact generated container name. Native workers are measurements
of **non-adversarial model programs**, not cryptographically authenticated
judges against code deliberately tampering with its in-container observer.
Native execution receipts retain container invocation count and elapsed wall
time (including cleanup); these are separate from model token costs.

Freeze these runtime settings across methods/checkpoints. Do not change an
image, repair an evaluator, or retry an unknown in place after observing scores;
use a new protocol/output directory when behavior changes.
