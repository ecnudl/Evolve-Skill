"""ZebraLogic grid-mode adapter, registered by value for ``zebra-pc-v1``.

This is a separate route-B adapter: historical dataset/backend/card registries stay
frozen. The public contract is exactly question + columns. Gold grids are private;
only the raw scorer result contains descriptive cell counts. No reader except
``test_panel`` accepts the sealed source, and that reader requires TestAccess.
"""
from __future__ import annotations

import hashlib
import json
import errno
import os
import re
from collections import Counter, deque
from pathlib import Path

from skillopt.coevo5.data import TestAccess
from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

BENCH = "zebralogic"
VERSION = "zebra-pc-v1-grid-adapter"
POOL_PATH = "/data/probe-data-20261025/split-v1/zebralogic/pool.json"
POOL_SHA256 = "059dba6a303dcc5216e92079d283942204e206ab411b52cef9a1351e523a793e"
SEALED_PATH = "/data/probe-data-20261025/split-v1/zebralogic/sealed-holdout.json"
SEALED_SHA256 = "7f690a67e03e1a95ffe9f2aba5efa6fd8958d58f828cfd1df6858b3074530f6c"
SPLIT_MANIFEST_PATH = "/data/probe-data-20261025/split-v1/split-manifest.json"
SOURCE_REVISION = "0a473f5a0054835754ed156d5a79c6ce27178bb1"
LICENSE = "None stated for ZebraLogic; internal use only"
DOMAIN = tuple("%d*%d" % (houses, columns) for houses in (5, 6) for columns in range(2, 7))
DOMAIN_COUNT = 200
SLICES_PER_TASK = {"smoke": 1, "run": 6, "accept": 10}
SLICE_SEED = 20261025
SLICE_TAG = "zebra-pc-v1:stratified-slices"
EXCLUDED_RUN = "v3-zebralogic-large"
EXCLUDED_IDS = (
    "lgp-test-5x3-8", "lgp-test-5x3-13", "lgp-test-5x3-18",
    "lgp-test-5x4-32", "lgp-test-5x4-3", "lgp-test-5x4-4",
    "lgp-test-5x5-33", "lgp-test-5x5-21", "lgp-test-5x5-14",
    "lgp-test-5x6-1", "lgp-test-5x6-20", "lgp-test-5x6-26",
    "lgp-test-6x2-18", "lgp-test-6x2-22", "lgp-test-6x2-33",
    "lgp-test-6x3-31", "lgp-test-6x3-38", "lgp-test-6x3-33",
    "lgp-test-6x4-18", "lgp-test-6x4-22", "lgp-test-6x4-24",
    "lgp-test-6x5-17", "lgp-test-6x5-3", "lgp-test-6x5-20",
    "lgp-test-6x6-32", "lgp-test-6x6-36", "lgp-test-6x6-16",
)
# SHA256 of the ordered list's UTF-8 compact JSON, explicitly reproducible.
EXCLUDED_IDS_SHA256 = hashlib.sha256(json.dumps(list(EXCLUDED_IDS), ensure_ascii=False,
                                               separators=(",", ":")).encode()).hexdigest()
# WildEval/ZeroEval, Apache-2.0; exact template copied by value from the
# coordinator-supplied upstream/ZEBRA_GRID.py, never fetched at runtime.
TEMPLATE_VERSION = "zeroeval-zebra-grid-8c1485edf12c"
TEMPLATE_URL = "https://github.com/WildEval/ZeroEval/blob/8c1485edf12c6efb5f69135a562927c5ad484059/src/templates/ZEBRA_GRID.py"
TEMPLATE_COMMIT = "8c1485edf12c6efb5f69135a562927c5ad484059"
TEMPLATE_FILE_SHA256 = "bbeed4d971d19dc04b84e888255598ab1d35c3de6701aad240d7d26abfd4bd08"
TEMPLATE_LICENSE = "Apache-2.0"
TEMPLATE_TEXT = """
# Example Puzzle 

There are 3 houses, numbered 1 to 3 from left to right, as seen from across the street. Each house is occupied by a different person. Each house has a unique attribute for each of the following characteristics:
 - Each person has a unique name: `Peter`, `Eric`, `Arnold`.
 - Each person has a unique favorite drink: `tea`, `water`, `milk`

## Clues for the Example Puzzle

1. Peter is in the second house.
2. Arnold is directly left of the one who only drinks water.
3. The one who only drinks water is directly left of the person who likes milk.

## Answer to the Example Puzzle

{
    "reasoning": "Given Clue 1, we know Peter is in House 2. According to Clue 2, Arnold is directly left of the one who only drinks water. The person in House 3 cannot be on the left of anyone, so Arnold must be in House 1. Thus, Peter drinks water, and Eric lives in House 3. Then, according to Clue 3, Eric drinks milk. Therefore, Arnold drinks tea.",
    "solution": {
        "House 1": {
            "Name": "Arnold",
            "Drink": "tea"
        },
        "House 2": {
            "Name": "Peter",
            "Drink": "water"
        },
        "House 3": {
            "Name": "Eric",
            "Drink": "milk"
        }
    }
}

# Puzzle to Solve 

{puzzle}


# Instruction

Now please solve the above puzzle. Present your reasoning and solution in the following json format:

{json_template}

"""
TEMPLATE_SHA256 = hashlib.sha256(TEMPLATE_TEXT.encode()).hexdigest()
CARD_VERSION = "zebralogic-neutral-card-v1"
CARD_TEXT = "Follow the format in the user message."
CARD_SHA256 = hashlib.sha256(CARD_TEXT.encode()).hexdigest()
CONTRACT = ""  # no competing format instruction in the frozen QA system line
NOTES_SUFFIX = "\n\n# Procedure notes\n\n"
FORBIDDEN_POOL = re.compile(r"final|test|holdout|held_out|verifier_calibration|reserve|sealed", re.I)
HOUSE_COUNT = re.compile(r"\AThere are ([1-9][0-9]*) houses, numbered 1 to ([1-9][0-9]*) "
                         r"from left to right, as seen from across the street\.")


def identity():
    """Preparation's by-value pins; this does not stat, hash or open the sealed path."""
    from .protocol import LEXICON_MATCH, LEXICON_SUFFIXES, LEXICON_TERMS, LEXICON_VERBATIM

    return {"version": VERSION, "benchmark": BENCH, "source_revision": SOURCE_REVISION,
            "split_manifest": SPLIT_MANIFEST_PATH, "split_manifest_field": "output_sha256",
            "pool": {"path": POOL_PATH, "sha256": POOL_SHA256},
            "sealed": {"path": SEALED_PATH, "sha256": SEALED_SHA256},
            "domain": list(DOMAIN), "pool_domain_count": DOMAIN_COUNT, "sealed_domain_count": DOMAIN_COUNT,
            "excluded_run": EXCLUDED_RUN, "excluded_ids": list(EXCLUDED_IDS),
            "excluded_ids_sha256": EXCLUDED_IDS_SHA256,
            "exclusion_hash_encoding": "UTF-8 compact ordered JSON list; ensure_ascii=False",
            "slice_seed": SLICE_SEED, "slice_tag": SLICE_TAG, "slices_per_task": dict(SLICES_PER_TASK),
            "card": {"version": CARD_VERSION, "text": CARD_TEXT, "sha256": CARD_SHA256,
                     "provenance": "Neutral card; nonempty manifest card required; format supplied only by official user template"},
            "user_template": {"version": TEMPLATE_VERSION, "text": TEMPLATE_TEXT,
                              "sha256": TEMPLATE_SHA256, "upstream_url": TEMPLATE_URL,
                              "upstream_commit": TEMPLATE_COMMIT, "upstream_file_sha256": TEMPLATE_FILE_SHA256,
                              "license": TEMPLATE_LICENSE,
                              "renderer": "apply_lgp_grid_template: replace puzzle, json.dumps(template, indent=4)",
                              "house_count_source": "public question: exact anchored opening sentence; both counts equal",
                              "house_count_pattern": HOUSE_COUNT.pattern,
                              "notes_suffix": NOTES_SUFFIX, "system": "frozen_QA_SYSTEM_only"},
            "freshness": "first_use_of_zebra_pc_v1_slices_after_excluding_v3_probe_items",
            "scorer": {"name": "zebralogic_all_cells", "version": "zebra-pc-v1-grid-scorer",
                       "carrier": "last_outer_json_object_with_solution_key_fenced_or_bare",
                       "normalization": {"keys": ["trim", "casefold"],
                                         "values": ["trim", "casefold", "collapse_inner_whitespace"]},
                       "houses": "exactly_House_1_through_House_N",
                       "columns": "exactly_registered_public_columns_per_house",
                       "duplicates": "reject_literal_or_normalized_keys",
                       "invalid_delivered_string": "fail", "invalid_scorer_input_or_transport": "unknown",
                       "puzzle_binary": True, "raw_only_cell_metrics": ["correct_cells", "total_cells"],
                       "persist_gold": False},
            "hooks": {"allowed": ["applies", "before_call"], "bindings": False,
                      "note_cap_chars_per_cell": 4000, "lexicon_terms": list(LEXICON_TERMS),
                      "lexicon_exemptions": [], "lexicon_match": LEXICON_MATCH,
                      "lexicon_suffixes": list(LEXICON_SUFFIXES), "verbatim": dict(LEXICON_VERBATIM),
                      "verbatim_table_rule": "unchanged_public_text_cells_unscreened"},
            "license": LICENSE}


def _key(value):
    return value.strip().casefold()


def _value(value):
    return " ".join(value.split()).casefold()


def public_view(public):
    """Whitelisted inference/routing view; extra fields never reach a hook or solver."""
    question, columns = public["question"], public["columns"]
    require(type(question) is str and bool(question.strip()), "ZebraLogic question must be nonempty text")
    require(type(columns) is list and bool(columns)
            and all(type(c) is str and c.strip() for c in columns)
            and len({_key(c) for c in columns}) == len(columns)
            and "house" not in {_key(c) for c in columns}, "ZebraLogic columns must be distinct text")
    return {"question": question, "columns": list(columns)}



def public_house_count(public):
    """House count from the puzzle itself; private grid/solution rows are never read."""
    opening = HOUSE_COUNT.match(public_view(public)["question"])
    require(opening is not None and opening.group(1) == opening.group(2),
            "ZebraLogic public puzzle must start with the registered house-count sentence with matching counts")
    return int(opening.group(1))


def render_user(public, notes=""):
    """Byte-exact official ZeroEval rendering, optionally followed by registered notes."""
    view = public_view(public)
    houses = public_house_count(view)
    template = {"reasoning": "___", "solution": {}}
    for i in range(houses):
        template["solution"]["House %d" % (i + 1)] = {column: "___" for column in view["columns"]}
    rendered = TEMPLATE_TEXT.replace("{puzzle}", view["question"])
    rendered = rendered.replace("{json_template}", json.dumps(template, indent=4))
    require(type(notes) is str, "Procedure notes must be text")
    return rendered + (NOTES_SUFFIX + notes if notes else "")


def parse_user(user):
    """Recover a stored official request's original public view and optional notes.

    This lets replay/donors/role views use the same public puzzle without feeding
    the official template's example puzzle to a clue parser. Exact re-rendering
    refuses a different or ambiguous transport representation.
    """
    require(type(user) is str, "A ZebraLogic request is text")
    prefix, rest = TEMPLATE_TEXT.split("{puzzle}")
    separator, suffix = rest.split("{json_template}")
    require(user.startswith(prefix), "ZebraLogic request does not use the registered template")
    split = user.find(separator, len(prefix))
    while split >= 0:
        try:
            question = user[len(prefix):split]
            tail = user[split + len(separator):]
            template, end = json.JSONDecoder(object_pairs_hook=_strict_object).raw_decode(tail)
            require(tail[end:].startswith(suffix), "ZebraLogic request suffix changed")
            appended = tail[end + len(suffix):]
            require(not appended or appended.startswith(NOTES_SUFFIX), "Unregistered ZebraLogic note appendix")
            notes = appended[len(NOTES_SUFFIX):] if appended else ""
            require(not appended or bool(notes), "An appended note is nonempty")
            require(type(template) is dict and set(template) == {"reasoning", "solution"}
                    and template["reasoning"] == "___" and type(template["solution"]) is dict
                    and bool(template["solution"]), "Invalid ZebraLogic request grid template")
            first = next(iter(template["solution"].values()))
            require(type(first) is dict, "Invalid ZebraLogic request columns")
            view = public_view({"question": question, "columns": list(first)})
            require(render_user(view, notes) == user, "ZebraLogic request differs from the official rendering")
            return {**view, **({"procedure_notes": notes} if notes else {})}
        except (ValueError, TypeError, KeyError, RecursionError):
            # Puzzle or notes may themselves quote the instruction separator. A
            # boundary counts only if its template parses and exact re-rendering agrees.
            split = user.find(separator, split + len(separator))
    raise ValueError("ZebraLogic request has no valid official template boundary")


def guard_pool_path(path):
    """Reject reserved tokens before any file stat/read, including symlink targets.

    Only readlink metadata is consulted while resolving aliases; no stat/lstat,
    existence probe or content read is needed. Requested components are checked
    before resolution, so even nonexistent forbidden names are refused at once.
    """
    requested = Path(path).expanduser()
    def check(value):
        require(not any(FORBIDDEN_POOL.search(part) for part in value.parts),
                "Refuse sealed or reserved path in non-TestAccess reader")
    check(requested)
    absolute = requested if requested.is_absolute() else Path.cwd() / requested
    check(absolute)
    resolved, pending, links = Path(absolute.anchor), deque(absolute.parts[1:]), 0
    while pending:
        component = pending.popleft()
        if component in ("", "."):
            continue
        if component == "..":
            resolved = resolved.parent
            continue
        probe = resolved / component
        check(probe)
        try:
            link = os.readlink(probe)
        except OSError as exc:
            if exc.errno not in (errno.EINVAL, errno.ENOENT, errno.ENOTDIR):
                raise
            resolved = probe
            continue
        links += 1
        require(links <= 40, "Too many symlinks in non-TestAccess path")
        target = Path(link)
        check(target)
        if target.is_absolute():
            resolved = Path(target.anchor)
            parts = target.parts[1:]
        else:
            parts = target.parts
        pending.extendleft(reversed(parts))
    check(resolved)
    return resolved


def _strict_object(pairs):
    value = {}
    for key, entry in pairs:
        require(key not in value, "Duplicate source JSON key")
        value[key] = entry
    return value


def _reject_constant(value):
    raise ValueError("Non-finite JSON constant")


def normalize(row, *, partition="pool"):
    """Normalize one split-v1 row without changing its puzzle text or column names."""
    require(type(row) is dict and row.get("bench") == BENCH and type(row.get("id")) is str
            and bool(row["id"]) and row.get("task") in DOMAIN, "Invalid ZebraLogic domain row")
    houses, attributes = map(int, row["task"].split("*"))
    require(row.get("size") == row["task"], "ZebraLogic size and stratum disagree")
    solution = row.get("solution")
    require(type(solution) is dict and set(solution) == {"header", "rows"}, "Invalid source grid")
    header, rows = solution["header"], solution["rows"]
    require(type(header) is list and len(header) == attributes + 1
            and all(type(h) is str and h.strip() for h in header)
            and len({_key(h) for h in header}) == len(header) and "house" in {_key(h) for h in header},
            "Invalid source grid header")
    house_column = next(i for i, name in enumerate(header) if _key(name) == "house")
    columns = [name for i, name in enumerate(header) if i != house_column]
    require(type(rows) is list and len(rows) == houses, "Invalid source grid height")
    grid = {}
    for cells in rows:
        require(type(cells) is list and len(cells) == len(header)
                and all(type(c) is str and c.strip() for c in cells), "Invalid source grid row")
        number = cells[house_column].strip()
        require(number in {str(i) for i in range(1, houses + 1)} and "House " + number not in grid,
                "Invalid source house")
        grid["House " + number] = {name: cells[i] for i, name in enumerate(header) if i != house_column}
    public = public_view({"question": row.get("puzzle"), "columns": columns})
    require(public_house_count(public) == houses, "Public puzzle house count differs from public task size")
    return {"benchmark": BENCH, "task_id": row["id"], "task": row["task"], "partition": partition,
            "family_id": BENCH + ":" + row["id"], "public": public, "private": {"answer": grid},
            "source_index": row.get("source_index"), "pool_order": row.get("pool_order"),
            "dataset_revision": SOURCE_REVISION}


def _rows(raw, *, partition):
    rows = json.loads(raw, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    require(type(rows) is list and rows, "ZebraLogic source must be a nonempty JSON list")
    require(all(type(row) is dict and type(row.get("id")) is str and row.get("bench") == BENCH
                and type(row.get("task")) is str for row in rows), "Invalid ZebraLogic source row")
    require(len({row["id"] for row in rows}) == len(rows), "Duplicate ZebraLogic item id")
    tasks = [normalize(row, partition=partition) for row in rows if row["task"] in DOMAIN]
    require(Counter(task["task"] for task in tasks) == Counter({task: 20 for task in DOMAIN}),
            "ZebraLogic domain must contain 20 items per registered stratum")
    return tasks


def load_pool(path=POOL_PATH, *, expected_sha256=POOL_SHA256):
    """Pinned POOL only, filtered to the registered 200-item domain; no sealed reads."""
    path = guard_pool_path(path)
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected_sha256, "ZebraLogic pool identity mismatch")
    tasks = _rows(raw, partition="pool")
    require(set(EXCLUDED_IDS) <= {t["task_id"] for t in tasks}, "Registered probe IDs absent from pool")
    return tasks


def slices(tasks, *, seed=SLICE_SEED):
    """Seeded SHA256 ordering within each task, then 1/6/10/rest; probe items stay out."""
    require(type(seed) is int, "ZebraLogic slice seed must be an integer")
    require(len({t["task_id"] for t in tasks}) == len(tasks), "Duplicate pool item")
    out = {name: [] for name in (*SLICES_PER_TASK, "spare")}
    for stratum in DOMAIN:
        eligible = [task for task in tasks if task["task"] == stratum and task["task_id"] not in EXCLUDED_IDS]
        ordered = sorted(eligible, key=lambda task: hashlib.sha256(json.dumps(
            [seed, SLICE_TAG, stratum, task["task_id"]], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest())
        require(len(ordered) >= sum(SLICES_PER_TASK.values()), "Insufficient fresh ZebraLogic stratum")
        start = 0
        for name, count in SLICES_PER_TASK.items():
            out[name].extend(ordered[start:start + count])
            start += count
        out["spare"].extend(ordered[start:])
    return out


def test_panel(pinned=None, benchmark=BENCH, *, access):
    """Only TestAccess admits the sealed reader. Preparation pins hashes by value."""
    require(isinstance(access, TestAccess), "Only the consent-gated evaluation step reads the sealed panel")
    require(benchmark == BENCH, "This reader admits only ZebraLogic")
    entry = identity()["sealed"] if pinned is None else pinned
    if "sealed" in entry:
        entry = entry["sealed"]
    require(type(entry) is dict and type(entry.get("path")) is str and type(entry.get("sha256")) is str,
            "A pinned ZebraLogic panel path and SHA256")
    raw = Path(entry["path"]).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == entry["sha256"], "ZebraLogic sealed identity mismatch")
    tasks = _rows(raw, partition="test")
    report = {"benchmark": BENCH, "tasks": len(tasks), "excluded_without_pages": [],
              "training_items_identical": None, "panel_hash": digest(tasks), "unit": access.unit,
              "source_files": None, "source_sha256": entry["sha256"]}
    return tasks, report


class _Object(list):
    """JSON object pairs preserve duplicates (a normal dict would silently discard them)."""


def solution_objects(reply):
    """All outer JSON objects bearing a normalized solution key, in response order.

    A complete object's children are never considered separate answer attempts.
    Duplicate keys are retained so an invalid final object cannot rescue an earlier grid.
    """
    decoder = json.JSONDecoder(object_pairs_hook=_Object, parse_constant=_reject_constant)
    index, found = 0, []
    while True:
        start = reply.find("{", index)
        if start < 0:
            return found
        try:
            obj, end = decoder.raw_decode(reply, start)
        except (ValueError, RecursionError):
            index = start + 1
            continue
        if isinstance(obj, _Object) and any(_key(key) == "solution" for key, _ in obj):
            found.append((start, end, obj))
        index = end


def _mapping(obj):
    require(isinstance(obj, _Object), "Grid object required")
    mapped = {}
    for key, value in obj:
        normalized = _key(key)
        require(normalized not in mapped, "Duplicate normalized grid key")
        mapped[normalized] = value
    return mapped


def parse_solution(reply, columns=None, houses=None):
    """The last solution-bearing JSON object's grid or None; exact shape if supplied."""
    if type(reply) is not str:
        return None
    found = solution_objects(reply)
    if not found:
        return None
    try:
        envelope = _mapping(found[-1][2])
        grid = _mapping(envelope["solution"])
        if houses is not None:
            require(set(grid) == {"house %d" % i for i in range(1, houses + 1)}, "Wrong houses")
        else:
            require(bool(grid) and set(grid) == {"house %d" % i for i in range(1, len(grid) + 1)}, "Wrong houses")
        parsed = {}
        for house, cells in grid.items():
            cells = _mapping(cells)
            require(bool(cells) and all(type(v) is str and v.strip() for v in cells.values()), "Invalid cells")
            if columns is not None:
                require(set(cells) == {_key(c) for c in columns}, "Wrong columns")
            parsed[house] = cells
        if columns is None:
            require(len({tuple(sorted(cells)) for cells in parsed.values()}) == 1, "Inconsistent columns")
        return parsed
    except (ValueError, TypeError, KeyError):
        return None


def _gold(public, private):
    view = public_view(public)
    answer = private["answer"]
    require(type(answer) is dict and bool(answer), "Private grid required")
    # Validate scorer inputs with the same exact shape and duplicate-normalized-key rule.
    grid = parse_solution(json.dumps({"solution": answer}), view["columns"], len(answer))
    require(grid is not None, "Invalid private grid")
    return view, grid


def score(public, private, prediction, *, runtime=None):
    """Puzzle-binary score; cell counts live in this raw artifact, never gate records."""
    from skillopt.continual_eval.backends import _unknown

    if not isinstance(prediction, dict):
        return _unknown("invalid_zebralogic_score_input")
    if prediction.get("status") != "available":
        return _unknown(prediction.get("reason", "prediction_unavailable"))
    try:
        view, gold = _gold(public, private)
    except (KeyError, ValueError, TypeError, RecursionError):
        return _unknown("invalid_zebralogic_score_input")
    output = prediction.get("output")
    if type(output) is not str:
        return _unknown("invalid_zebralogic_score_input")
    parsed = parse_solution(output, view["columns"], len(gold))
    total = len(gold) * len(view["columns"])
    correct = 0 if parsed is None else sum(_value(parsed[h][c]) == _value(value)
                                          for h, cells in gold.items() for c, value in cells.items())
    ok = parsed is not None and correct == total
    return {"status": "pass" if ok else "fail", "score": float(ok),
            "reason": ("zebralogic_all_cells_match" if ok else "zebralogic_cell_mismatch")
                      if parsed is not None else "zebralogic_invalid_format",
            "metrics": {"invalid_format": float(parsed is None), "correct_cells": correct, "total_cells": total}}


def format_valid(public, private, reply):
    """Shape only (not correctness), used for the existing J4 format failure category."""
    try:
        view, gold = _gold(public, private)
    except (KeyError, ValueError, TypeError, RecursionError):
        return False
    return parse_solution(reply, view["columns"], len(gold)) is not None


def carried_values(reply):
    """All complete grids' string cells, including duplicate-bearing objects.

    This protects the already disclosed answer cells as public excerpt anchors;
    it never consults a private grid. For an incomplete grid, retain JSON string
    values after its solution marker as conservative reply-only anchors.
    """
    cells = []
    def strings(value):
        if isinstance(value, _Object):
            for _, child in value:
                strings(child)
        elif isinstance(value, list):
            for child in value:
                strings(child)
        elif type(value) is str and value.strip():
            cells.append(value.strip())
    for _, _, obj in solution_objects(reply):
        for key, value in obj:
            if _key(key) == "solution":
                strings(value)
    if not cells:
        marker = re.search(r'"\s*solution\s*"\s*:', reply, re.I)
        if marker:
            for match in re.finditer(r':\s*("(?:[^"\\]|\\.)*")', reply[marker.end():]):
                try:
                    value = json.loads(match.group(1))
                except ValueError:
                    continue
                if value.strip():
                    cells.append(value.strip())
    return list(dict.fromkeys(cells))


def mask_reply(reply):
    """Mask every grid, carried cell restatement, and malformed/incomplete grid output.

    A malformed reply cannot safely expose guessed cells to a correctness-labelled
    detector, so it is masked whole. Valid replies retain non-answer reasoning.
    """
    if reply is None:
        return None
    from .trajectories import MASK, _restated

    objects = solution_objects(reply)
    if not objects:
        return MASK if reply.strip() else reply
    cells = carried_values(reply)
    masked, cursor = [], 0
    for start, end, obj in objects:
        masked += [reply[cursor:start], MASK]
        cursor = end
    masked.append(reply[cursor:])
    result = "".join(masked)
    if re.search(r'"\s*solution\s*"\s*:', result, re.I):
        return MASK  # an additional malformed/incomplete grid must not leak cells
    for cell in sorted(set(cells), key=lambda text: (-len(text), text)):
        if cell.strip():
            result = _restated(result, cell)
    return result
