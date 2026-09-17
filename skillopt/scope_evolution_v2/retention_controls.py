"""Small, independent controls for a frozen relation-evidence QA skill.

This is a synthetic diagnostic, not another source benchmark or a claim that a
control must induce negative transfer. In particular, the mature SearchQA skill
already qualifies its short-answer advice. Calibration and holdout have distinct
structural templates, independently seeded entities, and separate generation.
Only question/context go to the target. Never expose gold or latent records.
"""
from __future__ import annotations

import hashlib
import random
import re
import string
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from skillopt.envs.searchqa.rollout import _build_user

CROSS_DOMAINS = ("coding", "spreadsheet", "rule_reasoning")
DOMAINS = CROSS_DOMAINS + ("searchqa",)
SPLITS = ("calibration", "holdout")
GROUPS = ("positive", "near_miss", "unrelated")
PROTOCOL_VERSION = "frozen-searchqa-retention-controls-v1"
RELATION_MECHANISM = "relation_constrained_evidence"
ANSWER_CONTRACT = (
    "Return exactly <answer>YOUR_ANSWER</answer> and nothing else. Preserve every character of the requested "
    "identifier/name/text, including capitalization, punctuation, namespace, and every word. "
    "Do not add quotation marks. Whitespace between words may be normalized; no other shortening or normalization is allowed."
)


@dataclass(frozen=True)
class Task:
    id: str
    domain: str
    mechanism: str
    group: str
    split: str
    family: str
    prompt: str
    gold: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Task":
        return cls(**{key: value[key] for key in cls.__dataclass_fields__})


def _rng(seed: int, split: str, domain: str, group: str, index: int) -> random.Random:
    key = f"{PROTOCOL_VERSION}|{seed}|{split}|{domain}|{group}|{index}"
    return random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:16], "big"))


class _Entities:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.used: set[str] = set()

    def token(self, prefix: str = "") -> str:
        while True:
            token = "".join(self.rng.choices(string.ascii_lowercase, k=9))
            value = prefix + token
            if value not in self.used:
                self.used.add(value)
                return value

    def person(self) -> str:
        return " ".join(self.token().capitalize() for _ in range(3))


def _context(rng: random.Random, docs: Sequence[str]) -> str:
    docs = list(docs)
    rng.shuffle(docs)
    result = "\n\n".join("[DOC]\n" + document for document in docs)
    if len(result) > 5900:
        raise ValueError("control context exceeds the original SearchQA builder's safe untruncated budget")
    return result


def _relation_control(rng: random.Random, split: str, domain: str, entities: _Entities) -> tuple:
    """Eight alternatives; each distractor violates a stated relational conjunct.

    Selection is based on relation joins, not signed/eligible/highest-revision
    filters. All candidate answers occur equally often in the supplied records.
    """
    query = {key: entities.token(prefix) for key, prefix in
             [("owner", "owner_"), ("source", "source_"), ("condition", "flag_"), ("event", "event_")]}
    correct_index = rng.randrange(8)
    records = []
    docs = []
    for i in range(8):
        properties = dict(query)
        if i != correct_index:
            mismatches = rng.sample(list(query), 1 + int(rng.random() < 0.35))
            for key in mismatches:
                properties[key] = entities.token(key + "_")
        prefix = {"coding": "api_", "spreadsheet": "Measure_", "rule_reasoning": "Rule_"}[domain]
        answer = entities.token(prefix if split == "calibration" else {"coding": "export_", "spreadsheet": "Report_", "rule_reasoning": "Procedure_"}[domain])
        bridge = entities.token("link_")
        second = entities.token("spec_")
        records.append({"answer": answer, "bridge": bridge, "second": second, **properties})
        p = properties
        if domain == "coding" and split == "calibration":
            docs.extend([
                f"API index: routine `{answer}` is exported by package `{p['owner']}` and accepts descriptor `{bridge}`.",
                f"Descriptor contract `{bridge}`: the producer is `{p['source']}`; the buffer must not carry flag `{p['condition']}`. The lifetime record is `{second}`.",
                f"Lifetime record `{second}`: release occurs only after fence `{p['event']}` is signaled.",
            ])
        elif domain == "coding":
            docs.extend([
                f"Public symbol table: `{answer}` is an export alias for internal handler `{bridge}`.",
                f"Handler `{bridge}` is owned by package `{p['owner']}`. Its input/lifetime specification is `{second}`.",
                f"Specification `{second}`: the input is produced by `{p['source']}`; reject flag `{p['condition']}`; release only after fence `{p['event']}` is signaled.",
            ])
        elif domain == "spreadsheet" and split == "calibration":
            docs.extend([
                f"Workbook `{p['owner']}` defines name `{answer}` as `SUMIFS({bridge},{second},\"<>{p['condition']}\")`.",
                f"Range map `{bridge}` = sheet `{p['source']}`!D2:D99; criteria range `{second}` = the same sheet's F2:F99.",
                f"Calculation schedule: defined name `{answer}` refreshes on trigger `{p['event']}`. The SUMIFS criterion excludes that exact status label.",
            ])
        elif domain == "spreadsheet":
            docs.extend([
                f"Report catalog: label `{answer}` displays the defined formula `{bridge}` in workbook `{p['owner']}`.",
                f"Formula `{bridge}` sums column D of sheet `{p['source']}` only when the row's column F is NOT `{p['condition']}`. Its refresh policy is `{second}`.",
                f"Refresh policy `{second}`: recalculate when event `{p['event']}` occurs. The requested display label is not the formula identifier.",
            ])
        elif split == "calibration":
            docs.extend([
                f"Adoption register: rule `{answer}` is in jurisdiction `{p['owner']}` and invokes procedure `{bridge}`.",
                f"Procedure `{bridge}`: evidence fact `{p['source']}` must be present and exception fact `{p['condition']}` absent. The conclusion is registered under `{second}`.",
                f"Conclusion register `{second}`: infer event `{p['event']}`. No other event is inferred by that entry.",
            ])
        else:
            docs.extend([
                f"Rule catalog: rule `{bridge}` belongs to jurisdiction `{p['owner']}` and is executed by procedure `{answer}`.",
                f"Rule `{bridge}` uses antecedent template `{second}` and concludes event `{p['event']}`.",
                f"Antecedent template `{second}` requires evidence fact `{p['source']}` and absence of exception fact `{p['condition']}`.",
            ])
    if domain == "coding":
        role = "exported routine identifier" if split == "calibration" else "PUBLIC export alias, not the internal handler"
        question = (
            f"Which {role} belongs to package `{query['owner']}`, accepts data produced by `{query['source']}`, "
            f"rejects flag `{query['condition']}`, and releases its buffer only after fence `{query['event']}` is signaled?"
        )
    elif domain == "spreadsheet":
        role = "defined name" if split == "calibration" else "report display label, not its formula identifier"
        question = (
            f"Which {role} in workbook `{query['owner']}` sums column D of sheet `{query['source']}`, "
            f"excludes rows whose column F equals `{query['condition']}`, and refreshes on event `{query['event']}`?"
        )
    else:
        role = "rule identifier" if split == "calibration" else "executing procedure identifier, not the rule identifier"
        question = (
            f"Which {role} in jurisdiction `{query['owner']}` requires fact `{query['source']}`, "
            f"requires exception `{query['condition']}` to be absent, and concludes event `{query['event']}`?"
        )
    chosen = [r for r in records if all(r[key] == value for key, value in query.items())]
    if len(chosen) != 1:
        raise AssertionError("relation oracle must have exactly one match")
    return question, _context(rng, docs), chosen[0]["answer"], RELATION_MECHANISM, {
        "latent_records": records, "query_constraints": query, "selected_index": correct_index,
        "structural_family": f"{domain}_{'direct_multidocument_join' if split == 'calibration' else 'public_alias_indirection_join'}",
    }


def _full_name_control(rng: random.Random, split: str, domain: str, entities: _Entities) -> tuple:
    project = entities.token({"coding": "package_", "spreadsheet": "workbook_", "rule_reasoning": "instrument_", "searchqa": "Book_"}[domain])
    name = entities.person()
    surname = name.split()[-1]
    other = entities.person()
    registration = entities.token("record_")
    if domain == "searchqa" and split == "calibration":
        docs = [f"Biographical catalog `{registration}`: the author of the novel `{project}` has complete cataloged name {name}. The catalog includes all three name components.",
                f"Trivia archive: This author wrote `{project}` | {surname}. The archive uses surname-only clue answers.",
                f"Publishing note: {other} edited `{project}`; that person was not its author."]
        question = (
            f"Who wrote the novel `{project}`? For this question give the author's COMPLETE three-word name from biographical catalog `{registration}`, "
            "including the middle name, not the surname-only trivia answer."
        )
    elif domain == "searchqa":
        entry = entities.token("biography_")
        docs = [f"Literature index `{registration}` links the author of `{project}` to biography `{entry}`.",
                f"Biography `{entry}`: given_name={name.split()[0]}; middle_name={name.split()[1]}; family_name={surname}.",
                f"Quiz digest: Author of `{project}` | {surname}. This is a deliberately abbreviated clue answer.",
                f"Book review by {other}: this reviewer is not the author in biography `{entry}`."]
        question = (
            f"Who is the author linked to `{project}` in literature index `{registration}`? "
            "Answer with the complete given-middle-family name, all three fields separated by single spaces; a surname alone is insufficient."
        )
    elif split == "calibration":
        docs = [f"Final registration `{registration}` for `{project}`. The field registered_signer_name is exactly: {name}. Role: signing author. This registry records the complete three-word name.",
                f"Trivia digest: Who signed `{project}`? | {surname}. The digest abbreviates people to surnames and is not a full-name registry.",
                f"Review log for `{project}`: reviewer name {other}; reviewer is not the signing author."]
        question = (
            f"For `{project}`, copy the ENTIRE registered_signer_name from final registration `{registration}`. "
            "Return all three name words, not the trivia digest's surname-only shorthand."
        )
    else:
        entry = entities.token("entry_")
        docs = [f"Index `{registration}`: `{project}` has signing-party entry `{entry}`.",
                f"Party entry `{entry}`: given_name={name.split()[0]}; middle_name={name.split()[1]}; family_name={surname}. These three fields form the registered name in given-middle-family order.",
                f"Quick answer listing: Signing party of `{project}` | {surname}. This is a shortened listing.",
                f"Another party entry: registered reviewer {other}. It is not entry `{entry}`."]
        question = (
            f"Look up the signing-party entry linked by index `{registration}` for `{project}`. "
            "Return the full registered name by joining given_name, middle_name, family_name with one space, in that order. "
            "All three fields are required; the shortened answer listing is not the requested representation."
        )
    return question, _context(rng, docs), name, "complete_name_retrieval", {
        "structural_family": f"{domain}_{'whole_registered_name' if split == 'calibration' else 'linked_name_field_assembly'}",
        "near_miss_kind": "explicit_full_name", "required_name_words": name.split(),
        "forbidden_shorthand": surname, "candidate_boundary_note": "the mature skill explicitly permits full names when requested; failure is not assumed",
    }


def _verbatim_control(rng: random.Random, split: str, domain: str, entities: _Entities) -> tuple:
    selected_id = entities.token("fragment_")
    first, second, third = (entities.token().capitalize() for _ in range(3))
    text = f"The {first} and {second} {third} Unit"
    doc_kind = {"coding": "diagnostic message catalog", "spreadsheet": "exported report heading catalog",
                "rule_reasoning": "instrument caption catalog", "searchqa": "original trivia-source title catalog"}[domain]
    if split == "calibration":
        docs = [f"{doc_kind}, fragment `{selected_id}`. Verbatim text begins on the next line:\n{text}\nEnd of verbatim text.",
                f"Keyword index for fragment `{selected_id}`: {first}. This is an index keyword, not a quotation.",
                f"Topic note: {second} is a related project name; it is not the full heading."]
        question = (
            f"Copy the complete verbatim text from fragment `{selected_id}` in the {doc_kind}. "
            "Include its leading article The, both coordinated names, and the final word Unit. "
            "Return the entire line, not a keyword or missing-word completion."
        )
    else:
        alias = entities.token("catalog_key_")
        text = f"{first}: the {second}-{third} Archive"
        docs = [f"Catalog index `{alias}` maps to source fragment `{selected_id}`.",
                f"Source fragment `{selected_id}` has display_text: {text}\nThe colon and hyphen are literal characters in display_text.",
                f"Search summary for `{alias}`: {second}. This is a normalized keyword, not display_text."]
        question = (
            f"Follow catalog index `{alias}` and copy its source fragment's COMPLETE display_text. "
            "Preserve the colon, hyphen, article, final word Archive, and all name components exactly. "
            "Do not return the normalized search keyword."
        )
    return question, _context(rng, docs), text, "verbatim_extraction", {
        "structural_family": f"{domain}_{'whole_line_copy' if split == 'calibration' else 'indexed_punctuated_field_copy'}",
        "near_miss_kind": "specified_verbatim_text", "verbatim_text": text,
        "candidate_boundary_note": "explicit whole-text extraction differs from concise clue completion",
    }


def _provenance_control(rng: random.Random, split: str, domain: str, entities: _Entities) -> tuple:
    project = entities.token({"coding": "commit_", "spreadsheet": "workbook_run_", "rule_reasoning": "decision_", "searchqa": "Novel_"}[domain])
    alternatives = ([entities.person() for _ in range(5)] if domain == "searchqa" else
                    [entities.token({"coding": "handler_", "spreadsheet": "defined_name_", "rule_reasoning": "operative_rule_"}[domain]) for _ in range(5)])
    gold, copied_claim = rng.sample(alternatives, 2)
    primary_id, weak_id = entities.token("source_"), entities.token("post_")
    descriptions = {
        "coding": ("direct instrumentation trace", "actually executed handler"),
        "spreadsheet": ("independent cell-dependency audit", "actually referenced defined name"),
        "rule_reasoning": ("signed operative instrument", "operative rule identifier"),
        "searchqa": ("original first-edition title page", "credited author"),
    }
    kind, relation = descriptions[domain]
    if split == "calibration":
        docs = [f"Primary {kind} `{primary_id}`, concerning `{project}`: {relation} = `{gold}`. This is a direct record, not a repost.",
                f"Unverified post `{weak_id}` claims that for `{project}`, {relation} is `{copied_claim}`. It supplies no direct record."]
        for i in range(4):
            docs.append(f"Mirror page {entities.token('mirror_')}: copied verbatim from post `{weak_id}`; no independent verification. For `{project}`, {relation} is `{copied_claim}`.")
        question = (
            f"For `{project}`, what is the {relation} established by primary {kind} `{primary_id}`? "
            "The mirror pages all repeat one unverified source and do not constitute independent corroboration. "
            "Use the direct record for this fact, not a frequency vote."
        )
    else:
        index = entities.token("provenance_index_")
        docs = [f"Provenance index `{index}` for `{project}` identifies `{primary_id}` as the direct {kind}, and `{weak_id}` as an unverified origin copied by all mirror excerpts.",
                f"Evidence item `{primary_id}`: project `{project}`; {relation} `{gold}`; evidence class direct.",
                f"Evidence item `{weak_id}`: project `{project}`; {relation} `{copied_claim}`; evidence class unverified claim."]
        for _ in range(4):
            docs.append(f"Excerpt `{entities.token('excerpt_')}` cites only `{weak_id}`. Project `{project}`; {relation} `{copied_claim}`. This excerpt supplies no additional observation.")
        question = (
            f"Resolve provenance index `{index}` for `{project}` and return the {relation} supported by its direct evidence item. "
            "Count shared-origin copies as one claim, not independent witnesses; the unverified claim does not override the direct observation."
        )
    return question, _context(rng, docs), gold, "source_provenance_resolution", {
        "structural_family": f"{domain}_{'primary_against_copied_claims' if split == 'calibration' else 'provenance_index_against_mirrors'}",
        "near_miss_kind": "dependent_copies_vs_direct_source", "direct_answer": gold,
        "copied_claim": copied_claim, "alternatives": alternatives,
        "candidate_boundary_note": "repetition alone is not independent corroboration",
    }


def _unrelated_control(rng: random.Random, split: str, domain: str, entities: _Entities) -> tuple:
    a, b, c = rng.randint(3, 20), rng.randint(2, 8), rng.randint(2, 6)
    label = entities.token("task_")
    if split == "calibration":
        gold = str(a + b * c)
        instructions = {
            "coding": f"Evaluate the pure integer expression {a} + {b} * {c}. Use ordinary multiplication-before-addition precedence.",
            "spreadsheet": f"Cells A1={a}, A2={b}, A3={c}. Cell B1 has formula =A1+A2*A3. Give B1's integer value.",
            "rule_reasoning": f"A counter starts at {a}. Apply exactly {b} transitions, each adding {c}. Give the final counter.",
            "searchqa": f"Arithmetic quiz: a collection has {a} single items and {b} boxes containing {c} items each. How many items are there in total?",
        }[domain]
    else:
        gold = str((a + b) // c)
        instructions = {
            "coding": f"Evaluate ({a} + {b}) // {c}, where // means floor division on nonnegative integers.",
            "spreadsheet": f"Cells C1={a}, C2={b}, C3={c}. D1=INT((C1+C2)/C3), where INT is floor. Give D1's integer value.",
            "rule_reasoning": f"Combine {a} existing units with {b} new units. Form as many complete groups of size {c} as possible. Give the number of complete groups.",
            "searchqa": f"Arithmetic quiz: distribute {a}+{b} counters into complete groups of {c}. How many complete groups can be made?",
        }[domain]
    question = f"{instructions} Return a single base-10 integer with no units, decimal point, separators, or other words."
    context = _context(rng, [f"Task label `{label}`. This is a self-contained numerical task; no entity or document-source selection is required."])
    return question, context, gold, "none", {
        "structural_family": f"{domain}_{'integer_accumulation' if split == 'calibration' else 'complete_group_floor'}",
        "parameters": {"a": a, "b": b, "c": c},
    }


def build_controls(seed: int = 42, split: str = "calibration", n_per_group: int = 16,
                   domains: Sequence[str] | None = None) -> list[Task]:
    """Return 3*n_per_group controls total, with explicit domain assumptions.

    Positive controls use only the three new domains. By default half of the
    near-miss controls have SearchQA/trivia source-domain appearance; the rest
    cycle over the new domains. Unrelated controls cycle over all four domains.
    Thus a source-domain-only policy cannot trivially exclude every near miss.
    Holdout is generated only when explicitly requested. Do not increase the
    pilot sample or revise it based on holdout model outcomes. The default
    near-miss group mixes full-name, verbatim and provenance cases within domains.
    """
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}")
    if isinstance(n_per_group, bool) or not isinstance(n_per_group, int) or n_per_group < 1:
        raise ValueError("n_per_group must be a positive integer")
    chosen = tuple(DOMAINS if domains is None else domains)
    if not chosen or len(chosen) != len(set(chosen)) or set(chosen) - set(DOMAINS):
        raise ValueError("domains must be a nonempty unique subset of the supported domains")
    targets = tuple(domain for domain in chosen if domain != "searchqa")
    if not targets:
        raise ValueError("at least one non-source domain is required for positive controls")
    tasks = []
    near_builders = (_full_name_control, _verbatim_control, _provenance_control)
    for group_index, group in enumerate(GROUPS):
        for index in range(n_per_group):
            if group == "positive":
                domain = targets[index % len(targets)]
            elif group == "near_miss" and "searchqa" in chosen:
                domain = "searchqa" if index % 2 == 0 else targets[(index // 2) % len(targets)]
            else:
                domain = chosen[(index + group_index) % len(chosen)]
            rng = _rng(seed, split, domain, group, index)
            entities = _Entities(rng)
            if group == "positive":
                parts = _relation_control(rng, split, domain, entities)
            elif group == "near_miss":
                subtype_index = ((index // 2) // len(targets)) if "searchqa" in chosen else index // len(targets)
                parts = near_builders[subtype_index % len(near_builders)](rng, split, domain, entities)
            else:
                parts = _unrelated_control(rng, split, domain, entities)
            question, context, gold, mechanism, metadata = parts
            question = question + "\n" + ANSWER_CONTRACT
            task_id = f"retention-v1-s{seed}-{split}-{domain}-{group}-{index:04d}"
            metadata.update({"protocol_version": PROTOCOL_VERSION, "question": question, "context": context,
                             "entities": sorted(entities.used), "seed": seed, "index": index,
                             "synthetic": True, "hypothesized_parent_mechanism": RELATION_MECHANISM,
                             "source_domain_label": "searchqa", "domain_status": "source_appearance" if domain == "searchqa" else "cross_domain",
                             "normalization": "Unicode NFC and whitespace only; case punctuation articles and name words retained"})
            prompt = _build_user(question, context)
            if context not in prompt:
                raise AssertionError("SearchQA builder unexpectedly truncated a control")
            tasks.append(Task(task_id, domain, mechanism, group, split, metadata["structural_family"], prompt, gold, metadata))
    random.Random(f"{PROTOCOL_VERSION}|{seed}|{split}|order").shuffle(tasks)
    return tasks


def normalize_control_answer(value: str) -> str:
    """Only harmless Unicode/spacing normalization; never drop answer tokens."""
    return " ".join(unicodedata.normalize("NFC", value).split())


def evaluate_control_answer(task: Task | Mapping[str, Any], response_text: str) -> dict[str, Any]:
    gold = task.gold if isinstance(task, Task) else task["gold"]
    match = re.fullmatch(r"\s*<answer>([^<>]*)</answer>\s*", response_text, flags=re.DOTALL) if isinstance(response_text, str) else None
    if match is None or not normalize_control_answer(match.group(1)):
        return {"correct": False, "hard": 0.0, "soft": 0.0, "format_valid": False,
                "parsed_answer": None, "reason": "expected_exactly_one_nonempty_answer_tag"}
    answer = normalize_control_answer(match.group(1))
    correct = answer == normalize_control_answer(gold)
    return {"correct": correct, "hard": float(correct), "soft": float(correct), "format_valid": True,
            "parsed_answer": answer, "reason": "exact_required_text" if correct else "wrong_required_text"}


# Adapter-friendly names without importing or modifying frozen task modules.
build_retention_controls = build_controls
evaluate_answer = evaluate_control_answer
