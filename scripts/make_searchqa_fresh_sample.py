"""Materialize a FRESH SearchQA evaluation sample that no run of this project has ever used.

Outcome-blind and content-blind: the script reads the locally cached Hugging Face dataset (the same repository
and revision the native items were materialized from), removes every item of the existing native split (train /
val / test, which is where the canonical train / val / test / reserve partitions come from) and every item whose
normalized question equals a native question or an earlier drawn one, draws ``--count`` items with a seeded
generator from the SAME source split as the native evaluation items (``validation``), and divides the draw into
equal blocks by the same seeded order. It prints counts and length statistics only -- never a question, a context
or an answer.

Block roles are decided by the design memo, not here; a block that is to stay sealed must simply not be copied
to a machine that runs experiments until its protocol is sealed.

Usage: python scripts/make_searchqa_fresh_sample.py --output data/<new dir> [--count 4000]
       [--blocks 4] [--seed searchqa-fresh-20261012]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import statistics
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_SPLIT = "validation"  # the native val and test items (hence canonical val / test / reserve) come from it


def normalized(question):
    return re.sub(r"\W+", " ", question.lower()).strip()


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(dataset, native_dir, output, *, count, blocks, seed, dataset_name, revision):
    output = Path(output).resolve()
    data = PROJECT_ROOT / "data"
    if (PROJECT_ROOT in output.parents or output == PROJECT_ROOT) and (
            data not in output.parents or output.name.endswith("_id_split")):
        # data/* is git-ignored except the *_id_split manifests; materialized third-party items are never published
        raise ValueError("Write the materialized sample under data/ (git-ignored) or outside the repository")
    if output.exists():
        raise ValueError("Use a new directory")
    if count % blocks:
        raise ValueError("The draw must divide into equal blocks")
    native_ids, native_questions, native_sources = set(), set(), {}
    for part in ("train", "val", "test"):
        path = Path(native_dir) / part / "items.json"
        native_sources[str(path)] = _sha(path)
        for item in json.loads(path.read_text(encoding="utf-8")):
            native_ids.add(str(item["id"]))
            native_questions.add(normalized(item["question"]))
    rows = dataset[SOURCE_SPLIT]
    keys = [str(k) for k in rows["key"]]
    if len(set(keys)) != len(keys):
        raise ValueError("Source keys are not unique")
    order = sorted(range(len(keys)), key=lambda i: keys[i])
    random.Random(seed).shuffle(order)
    chosen, seen, skipped = [], set(native_questions), {"native_id": 0, "duplicate_question": 0, "invalid": 0}
    for index in order:
        if len(chosen) == count:
            break
        if keys[index] in native_ids:
            skipped["native_id"] += 1
            continue
        row = rows[index]
        answers = row.get("answers")
        if not (isinstance(row.get("question"), str) and row["question"].strip() and isinstance(row.get("context"), str)
                and row["context"].strip() and isinstance(answers, list) and answers
                and all(isinstance(a, str) and a.strip() for a in answers)):
            skipped["invalid"] += 1
            continue
        key = normalized(row["question"])
        if key in seen:
            skipped["duplicate_question"] += 1
            continue
        seen.add(key)
        chosen.append({"id": keys[index], "question": row["question"], "context": row["context"], "answers": answers})
    if len(chosen) != count:
        raise RuntimeError("The source split has too few eligible items")
    size = count // blocks
    record = {"version": "searchqa-fresh-sample-v1", "source_dataset": dataset_name, "source_revision": revision,
              "source_split": SOURCE_SPLIT, "source_rows": len(keys), "seed": seed, "count": count,
              "native_sources": native_sources, "native_items_excluded": len(native_ids), "skipped_before_full": skipped,
              "dedupe": "normalized question (lower case, non-word runs collapsed) against every native item and "
                        "every earlier drawn item",
              "item_fields": ["id", "question", "context", "answers"], "blocks": {}}
    output.mkdir(parents=True)
    for number in range(blocks):
        items = chosen[number * size:(number + 1) * size]
        name = "block_%s" % "abcdefgh"[number]
        (output / name).mkdir()
        path = output / name / "items.json"
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        record["blocks"][name] = {"items": len(items), "sha256": _sha(path), "ids": [i["id"] for i in items]}
    (output / "sample_manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record, chosen


def _lengths(items):
    context = sorted(len(i["context"]) for i in items)
    return {"items": len(items), "context_chars_median": int(statistics.median(context)),
            "context_chars_p10": context[len(context) // 10], "context_chars_p90": context[9 * len(context) // 10],
            "question_chars_median": int(statistics.median(len(i["question"]) for i in items)),
            "answers_per_item_mean": round(statistics.mean(len(i["answers"]) for i in items), 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--native-dir", default=str(PROJECT_ROOT / "data" / "searchqa_split"))
    parser.add_argument("--dataset", default="lucadiliello/searchqa")
    parser.add_argument("--revision", default="c1a979068ba118d85467179b704031d113d689cc",
                        help="dataset revision the native items were materialized from (checked against the cache)")
    parser.add_argument("--count", type=int, default=4000)
    parser.add_argument("--blocks", type=int, default=4)
    parser.add_argument("--seed", default="searchqa-fresh-20261012")
    args = parser.parse_args()
    import os

    # the cached revision only, never the network: the offline switches are read when ``datasets`` is imported
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from datasets import load_dataset

    dataset = load_dataset(args.dataset, revision=args.revision)
    files = [f["filename"] for split in dataset.values() for f in split.cache_files]
    if not files or not all(("/" + args.revision + "/") in f for f in files):
        raise ValueError("The loaded dataset is not the cached revision named by --revision")
    revision = args.revision
    record, chosen = build(dataset, args.native_dir, args.output, count=args.count, blocks=args.blocks, seed=args.seed,
                           dataset_name=args.dataset, revision=revision)
    native_test = json.loads((Path(args.native_dir) / "test" / "items.json").read_text(encoding="utf-8"))
    print(json.dumps({"skipped_before_full": record["skipped_before_full"],
                      "blocks": {k: {"items": v["items"], "sha256": v["sha256"][:16]} for k, v in record["blocks"].items()},
                      "source_revision": record["source_revision"],
                      "lengths_fresh": _lengths(chosen), "lengths_native_test": _lengths(native_test)}, indent=1))


if __name__ == "__main__":
    main()
