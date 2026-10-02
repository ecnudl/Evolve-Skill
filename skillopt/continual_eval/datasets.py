"""Strict, host-side panels for frozen continual evaluation.

Importers never execute benchmark code or download data.  Answers and tests stay
in ``private``; callers must pass only ``public_view(task)`` to model backends.
Revision labels are caller-supplied provenance, not proof of upstream identity.
Near-duplicate/project grouping still requires a reviewed family manifest.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

VERSION = "continual-panel-v1"
BENCHMARKS = ("bigcodebench", "spreadsheetbench", "searchqa", "korbench", "alfworld")
PARTITIONS = ("development", "verifier_calibration", "skill_confirmation", "final")
_ROOT = {"version", "benchmark", "dataset_revision", "provenance", "tasks"}
_TASK = {"task_id", "family_id", "project_id", "partition", "public", "private"}
_PUBLIC = {
    "searchqa": {"question", "context"},
    "korbench": {"rule", "question"},
    "bigcodebench": {"prompt", "entry_point"},
    "spreadsheetbench": {"instruction", "input_files", "answer_position"},
    "alfworld": {"game_file"},
}
_PRIVATE = {
    "searchqa": {"answers"},
    "korbench": {"answer", "category", "rule_id", "upstream_index"},
    "bigcodebench": {"test"},
    "spreadsheetbench": {"test_files", "answer_position"},
    "alfworld": {"game_metadata"},
}
_OPTIONAL = {"source_sha256", "source_url", "asset_sha256"}
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _json_native(value):
    if value is None or type(value) in (bool, str, int):
        return
    if type(value) is float:
        _require(math.isfinite(value), "Nonfinite JSON value")
        return
    if type(value) is list:
        for item in value:
            _json_native(item)
        return
    _require(type(value) is dict, "Expected JSON-native data")
    _require(all(type(key) is str for key in value), "JSON keys must be strings")
    for item in value.values():
        _json_native(item)


def _canonical(value):
    _json_native(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def _loads(value):
    def reject_constant(_):
        raise ValueError("Nonfinite JSON value")
    return json.loads(value, object_pairs_hook=_pairs, parse_constant=reject_constant)


def _text(value, label, *, empty=False):
    _require(type(value) is str and (empty or bool(value.strip())), f"{label} must be a string")


def _strings(value, label, *, empty=False):
    _require(type(value) is list and (empty or bool(value)), f"{label} must be a list")
    for item in value:
        _text(item, label)


def validate_panel(panel):
    """Validate metadata and split isolation without reading or executing assets."""
    _json_native(panel)
    _require(type(panel) is dict and set(panel) == _ROOT, "Invalid panel fields")
    _require(panel["version"] == VERSION, "Unsupported panel version")
    benchmark = panel["benchmark"]
    _require(type(benchmark) is str and benchmark in BENCHMARKS, "Unknown benchmark")
    _text(panel["dataset_revision"], "dataset_revision")
    _require(panel["dataset_revision"].lower() not in {"main", "master", "head", "latest", "default"},
             "dataset_revision must identify a frozen source, not a mutable branch")
    _require(panel["provenance"] in ("natural", "fixture"), "Invalid provenance")
    _require(type(panel["tasks"]) is list and bool(panel["tasks"]), "Panel tasks must be nonempty")
    task_ids, families, asset_hashes = set(), {}, {}
    for task in panel["tasks"]:
        _require(type(task) is dict and set(task) == _TASK, "Invalid task fields")
        for key in ("task_id", "family_id"):
            _text(task[key], key)
        _text(task["project_id"], "project_id", empty=True)
        _require(task["task_id"] not in task_ids, "Duplicate task_id")
        task_ids.add(task["task_id"])
        partition = task["partition"]
        _require(partition in PARTITIONS, "Invalid partition")
        family = task["family_id"]
        _require(family not in families or families[family] == partition, "Family partition conflict")
        families[family] = partition
        public, private = task["public"], task["private"]
        _require(type(public) is dict and set(public) == _PUBLIC[benchmark], "Invalid public fields")
        _require(type(private) is dict and _PRIVATE[benchmark] <= set(private)
                 <= _PRIVATE[benchmark] | _OPTIONAL,
                 "Invalid private fields")
        for key, value in public.items():
            if key == "input_files":
                _strings(value, key)
                _require(len(set(value)) == len(value), "Duplicate input file")
            elif key == "context" and type(value) is list:
                _strings(value, key, empty=True)
            else:
                _text(value, key, empty=key == "context")
        if benchmark == "bigcodebench":
            _require(public["entry_point"].isidentifier(), "Invalid entry_point")
        for key in _PRIVATE[benchmark]:
            value = private[key]
            if key in ("answers", "test_files"):
                _strings(value, key)
            elif key == "game_metadata":
                _require(type(value) is dict, "game_metadata must be an object")
                if "asset_files" in value:
                    _strings(value["asset_files"], "ALFWorld asset_files", empty=True)
            else:
                _text(value, key)
        if benchmark == "spreadsheetbench":
            _require(len(public["input_files"]) == len(private["test_files"]), "Workbook case counts differ")
            _require(not set(public["input_files"]) & set(private["test_files"]), "Private workbook exposed as input")
            _require(public["answer_position"] == private["answer_position"],
                     "Public output contract and private scoring region differ")
        for key in ("source_url", "category", "upstream_index", "rule_id"):
            if key in private:
                _text(private[key], key)
        if "source_sha256" in private:
            _require(type(private["source_sha256"]) is str and bool(_HEX.fullmatch(private["source_sha256"])),
                     "Invalid source_sha256")
        assets = private.get("asset_sha256", {})
        _require(type(assets) is dict, "asset_sha256 must be an object")
        expected_paths = set(_asset_paths(benchmark, task))
        _require(set(assets) <= expected_paths, "Asset hash references unlisted file")
        for name, value in assets.items():
            _require(type(value) is str and bool(_HEX.fullmatch(value)), "Invalid asset SHA-256")
            _require(name not in asset_hashes or asset_hashes[name] == value, "Conflicting asset hashes")
            asset_hashes[name] = value
        if benchmark == "korbench":
            _require(private["category"] in ("cipher", "logic", "operation", "puzzle", "counterfactual"),
                     "Invalid KOR category")
    if benchmark == "spreadsheetbench":
        inputs = {name for task in panel["tasks"] for name in task["public"]["input_files"]}
        tests = {name for task in panel["tasks"] for name in task["private"]["test_files"]}
        _require(not inputs & tests, "Private workbook exposed across tasks")
    return panel


def _asset_paths(benchmark, task):
    if benchmark == "spreadsheetbench":
        return task["public"]["input_files"] + task["private"]["test_files"]
    if benchmark == "alfworld":
        return [task["public"]["game_file"], *task["private"]["game_metadata"].get("asset_files", [])]
    return []


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_state(panel):
    """Return host-only file identities; unavailable files cannot look ready."""
    result = {}
    for task in panel["tasks"]:
        for name in _asset_paths(panel["benchmark"], task):
            path = Path(name)
            try:
                if not path.is_file():
                    result[name] = {"status": "missing_or_not_file"}
                    continue
                actual = file_hash(path)
                expected = task["private"].get("asset_sha256", {}).get(name)
                mismatch = expected and actual != expected or result.get(name, {}).get("status") == "hash_mismatch"
                result[name] = {"status": "hash_mismatch" if mismatch else "ready",
                                "sha256": actual}
            except OSError:
                result[name] = {"status": "unreadable"}
    return result


def load_panel(path):
    """Load a panel, resolving asset paths relative to its JSON file.

    Missing assets are reported by readiness rather than silently substituted.
    Hash mismatches are also retained as blocking readiness failures.
    """
    path = Path(path).resolve()
    panel = validate_panel(_loads(path.read_text(encoding="utf-8")))
    benchmark = panel["benchmark"]
    for task in panel["tasks"]:
        mapping = {name: str((path.parent / name).resolve()) for name in _asset_paths(benchmark, task)}
        if benchmark == "spreadsheetbench":
            task["public"]["input_files"] = [mapping[name] for name in task["public"]["input_files"]]
            task["private"]["test_files"] = [mapping[name] for name in task["private"]["test_files"]]
        elif benchmark == "alfworld":
            task["public"]["game_file"] = mapping[task["public"]["game_file"]]
            metadata = task["private"]["game_metadata"]
            if "asset_files" in metadata:
                metadata["asset_files"] = [mapping[name] for name in metadata["asset_files"]]
        if "asset_sha256" in task["private"]:
            task["private"]["asset_sha256"] = {mapping[name]: digest for name, digest in task["private"]["asset_sha256"].items()}
    return validate_panel(panel)


def panel_hash(panel):
    """Bind normalized content plus current file bytes, never merely file paths."""
    validate_panel(panel)
    return hashlib.sha256(_canonical({"panel": panel, "assets": _asset_state(panel)})).hexdigest()


def public_view(task):
    """Deep copy only public task content, excluding condition/ID/audit fields."""
    return copy.deepcopy(task["public"])


def readiness(panel):
    """Dataset readiness, not a claim that its model/sandbox backend is ready."""
    validate_panel(panel)
    assets = _asset_state(panel)
    blocked = Counter(item["status"] for item in assets.values() if item["status"] != "ready")
    return {"benchmark": panel["benchmark"], "status": "blocked" if blocked else "ready",
            "scope": "dataset_only", "provenance": panel["provenance"],
            "tasks": len(panel["tasks"]), "families": len({task["family_id"] for task in panel["tasks"]}),
            "partitions": dict(Counter(task["partition"] for task in panel["tasks"])),
            "assets": len(assets), "asset_failures": dict(blocked), "panel_hash": panel_hash(panel),
            "family_review": "Caller must audit near-duplicates and historical exposure; IDs alone do not establish independence."}


def _rows(source):
    if isinstance(source, (str, Path)):
        content = Path(source).read_bytes()
        try:
            data = _loads(content)
        except json.JSONDecodeError:
            data = [_loads(line) for line in content.decode("utf-8").splitlines() if line.strip()]
        digest = hashlib.sha256(content).hexdigest()
    else:
        data = copy.deepcopy(source)
        digest = hashlib.sha256(_canonical(data)).hexdigest()
    if type(data) is dict and set(data) == {"data"}:
        data = data["data"]
    _require(type(data) is list and bool(data), "Source must be a nonempty JSON/JSONL record list")
    _require(all(type(row) is dict for row in data), "Source contains non-record items")
    return data, digest


def _family(task_id, public, family_map):
    if family_map is not None:
        _require(task_id in family_map, "Family map lacks source task")
        _text(family_map[task_id], "family_id")
        return family_map[task_id]
    normalized = {key: " ".join(value.split()).casefold() if type(value) is str else value
                  for key, value in public.items()}
    return "exact-" + hashlib.sha256(_canonical(normalized)).hexdigest()[:24]


def _panel(benchmark, revision, tasks):
    return validate_panel({"version": VERSION, "benchmark": benchmark, "dataset_revision": revision,
                           "provenance": "natural", "tasks": tasks})


def import_searchqa(source, *, partition="development", revision, family_map=None):
    """Import local materialized SkillOpt/HF SearchQA records, not ID manifests."""
    rows, digest = _rows(source)
    tasks = []
    for row in rows:
        _require({"question", "context", "answers"} <= set(row),
                 "SearchQA requires materialized question/context/answers; ID-only manifests are not data")
        task_id = row.get("id", row.get("key"))
        _require(type(task_id) in (str, int) and type(task_id) is not bool, "SearchQA record lacks id/key")
        task_id = str(task_id)
        public = {key: row[key] for key in ("question", "context")}
        tasks.append({"task_id": task_id, "family_id": _family(task_id, {"question": row["question"]}, family_map),
                      "project_id": "", "partition": partition, "public": public,
                      "private": {"answers": row["answers"], "source_sha256": digest}})
    return _panel("searchqa", revision, tasks)


def import_bigcodebench(source, *, partition="development", revision, family_map=None, split="instruct"):
    """Import upstream cached rows; preserve tests privately, drop solutions.

    Source schema: bigcode-project/bigcodebench/bigcodebench/data/bigcodebench.py.
    The import deliberately does not execute its unittest code.
    """
    _require(split in ("instruct", "complete"), "Invalid BigCodeBench split")
    rows, digest = _rows(source)
    tasks = []
    for row in rows:
        field = split + "_prompt"
        _require({"task_id", field, "entry_point", "test"} <= set(row), "Incomplete BigCodeBench source row")
        task_id = row["task_id"]
        _text(task_id, "task_id")
        public = {"prompt": row[field], "entry_point": row["entry_point"]}
        tasks.append({"task_id": task_id, "family_id": _family(task_id, public, family_map),
                      "project_id": "", "partition": partition, "public": public,
                      "private": {"test": row["test"], "source_sha256": digest}})
    return _panel("bigcodebench", revision, tasks)


def import_korbench(samples, rules, *, category, partition="development", revision):
    """Join upstream zero-shot sample/rule records; a rule is a split family.

    Source schema: KOR-Bench/KOR-Bench/infer/data_loader.py.  Keeping all tasks
    sharing one rule in one partition prevents rule leakage across our split.
    """
    _require(category in ("cipher", "logic", "operation", "puzzle", "counterfactual"), "Invalid KOR category")
    sample_rows, sample_hash = _rows(samples)
    rule_rows, rule_hash = _rows(rules)
    lookup = {}
    for row in rule_rows:
        _require({"idx", "rule_content"} <= set(row), "Incomplete KOR rule")
        key = str(row["idx"])
        _require(key not in lookup, "Duplicate KOR rule ID")
        lookup[key] = row["rule_content"]
    digest = hashlib.sha256(_canonical([sample_hash, rule_hash])).hexdigest()
    tasks = []
    for row in sample_rows:
        _require({"idx", "rule_id", "question", "answer"} <= set(row), "Incomplete KOR sample")
        index, rule_id = str(row["idx"]), str(row["rule_id"])
        _require(rule_id in lookup, "KOR sample references missing rule")
        tasks.append({"task_id": category + ":" + index, "family_id": category + ":rule:" + rule_id,
                      "project_id": "", "partition": partition,
                      "public": {"rule": lookup[rule_id], "question": row["question"]},
                      "private": {"answer": row["answer"], "category": category,
                                  "upstream_index": index, "rule_id": rule_id, "source_sha256": digest}})
    return _panel("korbench", revision, tasks)


def _contained_path(data_root, name):
    """Resolve an explicit release path, never glob for a guessed replacement."""
    _text(name, "asset path")
    _require("\\" not in name and not name.startswith("~") and "$" not in name,
             "Asset paths must be explicit POSIX paths")
    root, path = Path(data_root).resolve(), Path(name)
    _require(".." not in path.parts, "Asset path traverses outside release layout")
    resolved = (root / path).resolve()
    _require(resolved.is_relative_to(root), "Asset path escapes data_root")
    return resolved


def _present_hashes(paths):
    return {str(path): file_hash(path) for path in paths if Path(path).is_file()}


def import_spreadsheetbench(source, *, data_root, partition="development", revision, family_map=None):
    """Import materialized official metadata and explicit paired workbooks.

    Supported release names match envs/spreadsheetbench/rollout.py and the
    stricter scripts/prepare_verified400.py inventory.  No workbooks are read
    by an office interpreter here, and no gold files become model inputs.
    ``data_root`` must already be the prefix of metadata ``spreadsheet_path``.
    """
    rows, digest = _rows(source)
    tasks = []
    for row in rows:
        _require({"id", "instruction", "instruction_type", "spreadsheet_path", "answer_position"} <= set(row),
                 "SpreadsheetBench requires full metadata, not an ID-only manifest")
        _require(type(row["id"]) in (str, int) and type(row["id"]) is not bool, "Invalid SpreadsheetBench id")
        for key in ("instruction", "instruction_type", "spreadsheet_path", "answer_position"):
            _text(row[key], key)
        task_id = str(row["id"])
        directory = _contained_path(data_root, row["spreadsheet_path"])
        _require(directory.is_dir(), "Explicit spreadsheet_path directory does not exist")
        files = sorted(directory.glob("*.xlsx"))
        _require(bool(files), "No XLSX assets in spreadsheet_path")
        pairs, used = [], set()
        for path in files:
            _require(_contained_path(data_root, str(path)).is_file(), "Workbook must be a regular file inside data_root")
            if path.name.endswith("_input.xlsx"):
                partner = path.with_name(path.name[:-len("_input.xlsx")] + "_answer.xlsx")
            elif path.name.endswith("_init.xlsx"):
                partner = path.with_name(path.name[:-len("_init.xlsx")] + "_golden.xlsx")
            elif path.name == "initial.xlsx":
                partner = path.with_name("golden.xlsx")
            else:
                continue
            _require(partner in files and partner.is_file(), "Input workbook lacks its gold partner")
            pairs.append((str(path.resolve()), str(partner.resolve())))
            used.update((path, partner))
        _require(bool(pairs) and used == set(files), "Unpaired or unrecognized workbook file")
        # Output coordinates belong to the task contract, not to hidden answer
        # values. Freeze the same region publicly and in the native scorer.
        public = {"instruction": row["instruction"], "input_files": [item[0] for item in pairs],
                  "answer_position": row["answer_position"]}
        private = {"test_files": [item[1] for item in pairs], "answer_position": row["answer_position"],
                   "source_sha256": digest, "asset_sha256": _present_hashes([str(path.resolve()) for path in files])}
        tasks.append({"task_id": task_id, "family_id": _family(task_id, {"instruction": row["instruction"]}, family_map),
                      "project_id": "", "partition": partition, "public": public, "private": private})
    return _panel("spreadsheetbench", revision, tasks)


def import_alfworld(source, *, data_root, partition="development", revision, family_map=None):
    """Import the repository's json_2.1.1 game-path manifest, not game answers.

    The registered native backend uses that release's fixed config. Other
    layouts must get an explicit adapter instead of silently guessing paths.
    Missing game/support files are allowed only as blocked readiness records.
    Trials sharing the same scenario form one family by default.
    """
    rows, digest = _rows(source)
    tasks = []
    for row in rows:
        _require({"id", "gamefile", "task_type"} <= set(row), "ALFWorld requires id/gamefile/task_type records")
        _require(type(row["id"]) in (str, int) and type(row["id"]) is not bool, "Invalid ALFWorld id")
        _text(row["task_type"], "task_type")
        task_id = str(row["id"])
        game = _contained_path(data_root, row["gamefile"])
        relative = game.relative_to(Path(data_root).resolve())
        parts = relative.parts
        _require(len(parts) == 5 and parts[0] == "json_2.1.1"
                 and parts[1] in ("train", "valid_seen", "valid_unseen")
                 and parts[3].startswith("trial_") and parts[4] == "game.tw-pddl",
                 "Unsupported ALFWorld gamefile layout; expected registered json_2.1.1 release")
        support = [game.with_name("traj_data.json"), Path(data_root).resolve() / "logic/alfred.pddl",
                   Path(data_root).resolve() / "logic/alfred.twl2"]
        for path in support:
            _contained_path(data_root, str(path))
        family = _family(task_id, {"scenario": parts[2]}, family_map)
        tasks.append({"task_id": task_id, "family_id": family, "project_id": "", "partition": partition,
                      "public": {"game_file": str(game)},
                      "private": {"game_metadata": {"source_split": parts[1], "task_type": row["task_type"],
                                                    "asset_files": [str(path) for path in support]},
                                  "source_sha256": digest, "asset_sha256": _present_hashes([game, *support])}})
    return _panel("alfworld", revision, tasks)
