"""The v2.8 schema reader. No evaluation, source rewriting, or answer repair.

Only JSON's data language is accepted. The fallback removes comments outside
strings, translates JSON literals, and uses ast.literal_eval (never eval).
Defaults, inheritance, relocation and unknown-key handling share one walker.
Historical readers never import this module on their execution path.
"""
from __future__ import annotations

import ast
import copy
import io
import json
import re
import tokenize
from dataclasses import dataclass, field

from . import profiles as p, replay
from .package import MAX_STATE_BYTES

MAX_REPLY_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})([^\n]*)\n(.*?)^[ \t]*\1[ \t]*$", re.M | re.S)


class Unusable(ValueError):
    pass


def _bounded_text(value):
    try:
        return isinstance(value, str) and len(value.encode("utf-8")) <= MAX_REPLY_BYTES
    except UnicodeError:
        return False


def _bounded_structure(value):
    """Check container depth iteratively, before any recursive copy or walker."""
    pending = [(value, 0)]
    while pending:
        child, depth = pending.pop()
        if not isinstance(child, (dict, list)):
            continue
        if depth >= MAX_JSON_DEPTH:
            raise Unusable("manifest nesting exceeds the reader depth limit (%d)" % MAX_JSON_DEPTH)
        pending.extend((item, depth + 1) for item in (child.values() if isinstance(child, dict) else child))


def tolerant_json(text):
    try:
        return _tolerant_json(text)
    except (RecursionError, MemoryError, OverflowError) as error:
        raise Unusable("manifest JSON exceeds reader resources (%s)" % type(error).__name__) from None


def _tolerant_json(text):
    """Bounded literal-only JSON extensions; never guess missing closing bytes."""
    if not _bounded_text(text):
        raise Unusable("manifest exceeds the reader byte limit or is not text")
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("ambiguous duplicate object key: %s" % key)
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("nonfinite JSON constant: %s" % value)

    try:
        value = json.loads(text, object_pairs_hook=object_pairs, parse_constant=invalid_constant)
        _bounded_structure(value)
        json.dumps(value, allow_nan=False, ensure_ascii=False).encode("utf-8")
        return value, []
    except Unusable:
        raise
    except (ValueError, RecursionError):
        pass
    # Keep string contents, including URLs and escaped quotes, byte for byte.
    chars, index, quote = [], 0, None
    while index < len(text):
        char = text[index]
        if quote:
            chars.append(char)
            if char == "\\" and index + 1 < len(text):
                index += 1
                chars.append(text[index])
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            chars.append(char)
        elif text.startswith("//", index) or char == "#":
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
            chars.append("\n")
            continue
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise Unusable("unterminated JSON comment")
            chars.append(" ")
            index = end + 2
            continue
        else:
            chars.append(char)
        index += 1
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO("".join(chars).strip()).readline))
        tokens = [token._replace(string={"true": "True", "false": "False", "null": "None"}.get(token.string, token.string))
                  if token.type == tokenize.NAME else token for token in tokens]
        tree = ast.parse(tokenize.untokenize(tokens), mode="eval")
        # literal_eval also permits tuples/sets/bytes; these are not JSON.
        allowed = (ast.Expression, ast.Dict, ast.List, ast.Constant, ast.UnaryOp, ast.USub, ast.UAdd, ast.Load)
        if any(not isinstance(node, allowed) for node in ast.walk(tree)):
            raise ValueError("not JSON data")
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [ast.literal_eval(key) for key in node.keys]
                if any(type(key) is not str for key in keys) or len(set(keys)) != len(keys):
                    raise ValueError("ambiguous object keys")
        value = ast.literal_eval(tree)
        _bounded_structure(value)
        json.dumps(value, allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (ValueError, SyntaxError, TypeError, RecursionError, tokenize.TokenError) as error:
        raise Unusable("manifest JSON: %s" % str(error)[:300]) from None
    return value, [{"rule": "tolerant_json", "path": "$"}]


@dataclass
class Field:
    type: type | tuple
    required: bool = False
    default: object = None
    derive: object = None
    children: dict = field(default_factory=dict)
    advisory: bool = False


def schema(kind="new", *, train=True, source="", entry=None, target=None):
    """C1 tables are the authority for procedure fields, types and requirements."""
    from . import engineer as e
    entry = entry or {}
    if kind in e.CODED:
        required, allowed = e._keys(kind, train)
        hook_value = entry.get("hooks")
        hooks = hook_value if isinstance(hook_value, list) else defined_hooks(source)
        fields = {key: Field(type_, key in required, copy.deepcopy(e.OPTIONAL.get(key, type_())))
                  for key, type_ in e.PROCEDURE_KEYS.items()}
        fields["description"].default = "Helper procedure."
        fields["replay_tests"].advisory = True
        fields["hooks"].derive = lambda: defined_hooks(source)
        fields["max_note_chars"].default = max(p.MAX_NOTE_CHARS.values()) if any(
            h in p.NOTE_HOOKS for h in hooks) else 0
        fields["state_bytes"].default = MAX_STATE_BYTES if "alf_after_step" in hooks else 0
        fields.update({key: Field(str, key in required, "") for key in sorted(allowed - fields.keys())})
    else:
        fields = {"kind": Field(str, True, kind), "id": Field(str, True, "")}
        if kind == "narrowing":
            fields["benches"] = Field(list, True, [])
    fields["kind"].default = kind
    target_key = e.TARGET_KEYS.get(kind)
    if target is not None and target_key in fields:
        fields[target_key].derive = lambda: target
    return fields


def test_schema(test):
    """Replay structure comes from validate_test's registered key/kind tables."""
    prop = test.get("property", {}) if isinstance(test, dict) else {}
    prop = prop if isinstance(prop, dict) else {}
    kind = prop.get("kind", test.get("kind"))
    hooks, keys = replay.PROPERTY_KINDS.get(kind, ((), ())) if isinstance(kind, str) else ((), ())
    types = {"claims_fix": bool, "hook": str, "id": str, "nonvacuity": dict,
             "property": dict, "trajectory": str}
    fields = {key: Field(types.get(key, str), True, types.get(key, str)()) for key in replay.TEST_KEYS}
    property_types = {"kind": str, "name": str, "key": str, "step": int,
                      "value": list if kind == "note_matches" else bool if kind == "repair_requested" else
                      (str, int, float, bool, list, dict, type(None)) if kind == "state_equals" else str}
    fields["property"].children = {key: Field(property_types.get(key, str), True,
        0 if key == "step" else None if key == "value" and kind == "state_equals" else
        property_types.get(key, str)()) for key in ("kind", *keys,
        *(("step",) if test.get("hook") in replay.STEP_HOOKS else ()))}
    fields["nonvacuity"].children = {"mutation": Field((str, type(None)), True, None),
                                     "withheld_expect": Field(bool, True, False)}
    return fields


def _places(fields, prefix=()):
    out = []
    for key, spec in fields.items():
        out.append((prefix + (key,), spec))
        out.extend(_places(spec.children, prefix + (key,)))
    return out


def _relocate(value, fields, path, repairs):
    """Resolve unique schema locations across siblings and unrecognized wrappers.

    A declared opaque JSON value is a leaf: its application data is never moved.
    List entries are normalized separately so values cannot migrate between tests.
    """
    places, misplaced = {}, []
    for parts, _ in _places(fields):
        places.setdefault(parts[-1], []).append(parts)

    def visit(node, schema_fields, prefix=()):
        for key, child in list(node.items()):
            spec = schema_fields.get(key)
            if spec is None:
                misplaced.append((node, key, prefix + (key,)))
                if isinstance(child, dict):
                    visit(child, {}, prefix + (key,))
            elif spec.children and isinstance(child, dict):
                visit(child, spec.children, prefix + (key,))

    visit(value, fields)
    for origin, key, given in misplaced:
        targets = places.get(key, ())
        if key not in origin or len(targets) != 1:
            continue
        target, dest = targets[0], value
        for part in target[:-1]:
            if not isinstance(dest.get(part), dict):
                dest[part] = {}
            dest = dest[part]
        if key not in dest:
            dest[key] = origin.pop(key)
            repairs.append({"rule": "relocated", "path": path + "." + ".".join(given),
                            "to": path + "." + ".".join(target)})


def normalize(value, fields, *, inherited=(), path="$", repairs=None):
    """One walker for every object: relocate, ignore, inherit, derive, default."""
    repairs = repairs if repairs is not None else []
    _bounded_structure(value)
    value = copy.deepcopy(value)
    if not isinstance(value, dict):
        raise Unusable("%s must be an object" % path)
    _relocate(value, fields, path, repairs)
    for key in list(value):
        if key in fields:
            continue
        places = [parts for parts, _ in _places(fields) if parts[-1] == key]
        if len(places) == 1:
            dest = value
            for part in places[0][:-1]:
                if not isinstance(dest.get(part), dict):
                    dest[part] = {}
                dest = dest[part]
            if key not in dest:
                dest[key] = value.pop(key)
                repairs.append({"rule": "relocated", "path": path + "." + key,
                                "to": path + "." + ".".join(places[0])})
                continue
        value.pop(key)
        repairs.append({"rule": "unknown_key_ignored", "path": path + "." + str(key)})
    for key, spec in fields.items():
        if key not in value:
            found = next(((n, parent[key]) for n, parent in enumerate(inherited)
                          if isinstance(parent, dict) and key in parent), None)
            if found is not None:
                value[key] = copy.deepcopy(found[1])
                rule = "inherited_change" if found[0] == 0 else "inherited_parent"
            elif spec.derive is not None:
                value[key], rule = spec.derive(), "derived"
            else:
                value[key], rule = copy.deepcopy(spec.default), "schema_default"
            repairs.append({"rule": rule, "path": path + "." + key})
        expected = spec.type if isinstance(spec.type, tuple) else (spec.type,)
        if type(value[key]) not in expected:
            # Scalar wrapping and lossless numeric conversions are generic.
            original = value[key]
            if spec.advisory and expected == (list,):
                value[key] = [original]  # validate/drop this test, never the program
            elif expected == (list,) and isinstance(original, (str, dict)):
                value[key] = [original]
            elif expected == (int,) and isinstance(original, str) and re.fullmatch(r"[+-]?\d+", original):
                value[key] = int(original)
            elif expected == (bool,) and isinstance(original, str) and original.lower() in ("true", "false"):
                value[key] = original.lower() == "true"
            else:
                raise Unusable("%s.%s must have type %s, got %s" % (
                    path, key, "/".join(t.__name__ for t in expected), type(original).__name__))
            repairs.append({"rule": "advisory_list_wrapped" if spec.advisory else "lossless_type_conversion", "path": path + "." + key})
        if spec.children:
            value[key] = normalize(value[key], spec.children,
                inherited=tuple(parent.get(key, {}) if isinstance(parent, dict) else {} for parent in inherited),
                path=path + "." + key, repairs=repairs)
    return value


def defined_hooks(source):
    try:
        names = {node.name for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return []
    return [hook for hook in p.HOOKS if hook in names]


def _source_owners(entries, blocks, ctx, fix_change, *, selected=None):
    """Assign fences together, reserving sources needed by non-inheriting siblings.

    The small change limit bounds this matching to O(fences * 2**changes).
    Hooks identify blocks; equal scores use order only for a complete matching.
    A partial matching with indistinguishable owners is an unusable envelope.
    """
    candidates = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or isinstance(entry.get("source"), str) and entry["source"].strip():
            continue
        fixing = fix_change if selected is None or selected == index else None
        target = entry.get("revises", entry.get("id"))
        if target is None and fixing is not None:
            target = fixing.entry.get("revises", fixing.entry.get("id"))
        parent = ctx.parent.get(target) if isinstance(target, str) and target in ctx.parent.order else None
        kind = entry.get("kind", fixing.kind if fixing else "revision" if parent else "new")
        if kind not in ("new", "revision"):
            continue
        inherited = any(getattr(item, "source", None) for item in (fixing, parent))
        hooks = entry.get("hooks")
        hooks = set(hooks) if isinstance(hooks, list) and all(isinstance(h, str) for h in hooks) else set()
        candidates.append((index, not inherited, hooks))
    if not candidates or not blocks:
        return {}
    selected_slot = next((slot for slot, (index, _, _) in enumerate(candidates) if index == selected), None)
    if selected is not None and selected_slot is None:
        return {}
    mandatory = [index for index, required, _ in candidates if required]
    order = (list(range(len(entries))) if len(blocks) == len(entries) else
             [index for index, _, _ in candidates] if len(blocks) == len(candidates) else
             mandatory if len(blocks) == len(mandatory) else [])
    # Keep two tied assignments so ambiguity is detected without enumerating all permutations.
    empty = (None,) * len(candidates)
    states = {0: ((0, 0, 0, 0), [empty])}
    for position, (number, lang, body) in enumerate(blocks):
        actual = set(defined_hooks(body))
        updated = dict(states)
        for mask, (score, assignments) in states.items():
            for slot, (index, required, hooks) in enumerate(candidates):
                if mask & (1 << slot):
                    continue
                increment = (int(required), len(actual & hooks) if hooks else len(actual), 1,
                             int(bool(order) and order[position] == index))
                proposed = tuple(left + right for left, right in zip(score, increment))
                key = mask | (1 << slot)
                previous, tied = updated.get(key, ((-1, -1, -1, -1), []))
                if proposed < previous:
                    continue
                if proposed > previous:
                    tied = []
                else:
                    tied = list(tied)
                for assignment in assignments:
                    assigned = assignment[:slot] + (number,) + assignment[slot + 1:]
                    if selected_slot is not None:
                        if len(tied) < 2 and not any(item[selected_slot] == assigned[selected_slot] for item in tied):
                            tied.append(assigned)
                    elif assigned not in tied and len(tied) < 2:
                        tied.append(assigned)
                updated[key] = (proposed, tied)
        states = updated
    best = max(score for score, _ in states.values())
    choices = [assignment for score, assignments in states.values() if score == best for assignment in assignments]
    if selected is not None:
        # A sibling's ambiguous ownership cannot invalidate a uniquely owned
        # selected source. Inline/inherited selected sources need no owner.
        selected_owners = {choice[selected_slot] for choice in choices}
        if len(selected_owners) != 1:
            raise Unusable("ambiguous procedure source blocks; ownership is not unique")
        number = selected_owners.pop()
        return {selected: next(block for block in blocks if block[0] == number)} if number is not None else {}
    if len(choices) != 1:
        raise Unusable("ambiguous procedure source blocks; ownership is not unique")
    by_number = {number: (number, lang, body) for number, lang, body in blocks}
    return {index: by_number[number] for (index, _, _), number in zip(candidates, choices[0]) if number is not None}


def _source(entry, owned, inherited):
    inline = entry.get("source")
    if isinstance(inline, str) and inline.strip():
        return inline, "inline_source"
    if owned is not None:
        return owned[2], "source_block_selected"
    for parent in inherited:
        if parent is not None and getattr(parent, "source", None):
            return parent.source, "inherited_source"
    raise Unusable("no procedure source block")


def read(reply, ctx, *, fix_change=None, selection=None, metadata=None):
    """Per-change results; a broken sibling cannot discard a usable change."""
    try:
        return _read(reply, ctx, fix_change=fix_change, selection=selection, metadata=metadata)
    except (RecursionError, MemoryError, OverflowError) as error:
        raise Unusable("reply exceeds reader resources (%s)" % type(error).__name__) from None


def _inline_source(entry, repairs):
    """v2.9.2 aliases/fences only; never alter unfenced program text."""
    if not isinstance(entry, dict):
        return entry
    entry = copy.deepcopy(entry)
    source, code = entry.get("source"), entry.pop("code", None)
    usable_source = isinstance(source, str) and bool(source.strip())
    usable_code = isinstance(code, str) and bool(code.strip())
    if usable_source and usable_code and source != code:
        repairs.append({"rule": "inline_source_precedence", "path": "$.source", "ignored": "$.code"})
    if not usable_source and usable_code:
        source = code
        repairs.append({"rule": "inline_code_alias", "path": "$.code", "to": "$.source"})
    if isinstance(source, str) and source.strip():
        stripped = source.strip()
        # Parse the opener independently so a short closing run cannot make
        # the regex backtrack part of the opening delimiter into the info.
        opening = re.match(r"(`{3,}|~{3,})([^\n]*)\n", stripped)
        if opening is not None:
            delimiter, info = opening.groups()
            valid_info = not info.startswith(delimiter[0]) and (delimiter[0] != "`" or "`" not in info)
            if valid_info:
                closing = re.search(r"^[ \t]*" + re.escape(delimiter[0]) + r"{%d,}[ \t]*\r?$" % len(delimiter),
                                    stripped[opening.end():], re.M)
                # The first valid closing line ends the block. Any following
                # text means this is not exactly one complete inline fence.
                if closing is not None and opening.end() + closing.end() == len(stripped):
                    source = stripped[opening.end():opening.end() + closing.start()]
                    repairs.append({"rule": "inline_source_unfenced", "path": "$.source"})
        entry["source"] = source
    return entry


def _selected_entry(entries, selection):
    """Resolve raw manifest identities before defaults/inheritance can add ids."""
    selection["reply_change_count"] = len(entries)
    if len(entries) == 1:
        selection["selected_by"] = "single"
        return 0
    change_id = selection.get("change_id")
    matches = [index for index, entry in enumerate(entries) if isinstance(entry, dict)
               and isinstance(change_id, str) and any(entry.get(key) == change_id for key in ("id", "revises"))]
    if len(matches) == 1:
        selection["selected_by"] = "id"
        return matches[0]
    index = selection.get("change_index")
    if (len(entries) == selection.get("change_count") and type(index) is int
            and 1 <= index <= len(entries)):
        selection["selected_by"] = "position"
        return index - 1
    raise Unusable("format retry must contain exactly the requested change")


def _large_retry_source_owner(entries, blocks, selected, ctx, fix_change):
    """Resolve just one oversized retry entry in linear work, never 2**N.

    Inline code wins. Position breaks ties only when every mapped entry attains
    its maximal hook score; otherwise a uniquely best hook match, without a
    competing sibling, is the only available ownership proof.
    """
    entry = entries[selected]
    if not isinstance(entry, dict) or isinstance(entry.get("source"), str) and entry["source"].strip():
        return {}
    target = entry.get("revises", entry.get("id"))
    if target is None and fix_change is not None:
        target = fix_change.entry.get("revises", fix_change.entry.get("id"))
    parent = ctx.parent.get(target) if isinstance(target, str) and target in ctx.parent.order else None
    kind = entry.get("kind", fix_change.kind if fix_change else "revision" if parent else "new")
    if kind not in ("new", "revision"):
        return {}
    if not blocks:
        return {}
    candidates = []
    for index, value in enumerate(entries):
        if not isinstance(value, dict) or isinstance(value.get("source"), str) and value["source"].strip():
            continue
        fixing = fix_change if index == selected else None
        target = value.get("revises", value.get("id"))
        if target is None and fixing is not None:
            target = fixing.entry.get("revises", fixing.entry.get("id"))
        parent = ctx.parent.get(target) if isinstance(target, str) and target in ctx.parent.order else None
        kind = value.get("kind", fixing.kind if fixing else "revision" if parent else "new")
        if kind not in ("new", "revision"):
            continue
        inherited = any(getattr(item, "source", None) for item in (fixing, parent))
        hooks = value.get("hooks")
        hooks = set(hooks) if isinstance(hooks, list) and all(isinstance(hook, str) for hook in hooks) else set()
        candidates.append((index, not inherited, hooks))
    mandatory = [index for index, required, _ in candidates if required]
    order = (list(range(len(entries))) if len(blocks) == len(entries) else
             [index for index, _, _ in candidates] if len(blocks) == len(candidates) else
             mandatory if len(blocks) == len(mandatory) else [])
    block_hooks = [set(defined_hooks(block[2])) for block in blocks]
    if order:
        positions = {index: position for position, index in enumerate(order)}
        maximal = all(
            (len(block_hooks[positions[index]] & hooks) if hooks else len(block_hooks[positions[index]]))
            == max(len(actual & hooks) if hooks else len(actual) for actual in block_hooks)
            for index, _, hooks in candidates if index in positions)
        if maximal:
            return {selected: blocks[positions[selected]]} if selected in positions else {}
    _, required, hooks = next(candidate for candidate in candidates if candidate[0] == selected)
    required_only = len(blocks) <= len(mandatory)
    if required_only and not required:
        return {}  # Every authored block is needed by a non-inheriting sibling.
    scores = []
    for block, actual in zip(blocks, block_hooks):
        scores.append((len(actual & hooks) if hooks else len(actual), block))
    best = max(score for score, _ in scores)
    winners = [block for score, block in scores if score == best and score > 0]
    if len(winners) != 1:
        raise Unusable("ambiguous procedure source blocks; ownership is not unique")
    actual = set(defined_hooks(winners[0][2]))
    for index, other_required, other_hooks in candidates:
        if index == selected or required_only and not other_required:
            continue
        # In an incomplete envelope, a block matching another source-needing
        # entry cannot uniquely belong to this one. Once mandatory sources can
        # all be filled, inherited replacements also compete for spare blocks.
        competes = bool(actual & other_hooks) if other_hooks else bool(actual)
        if competes:
            raise Unusable("ambiguous procedure source blocks; ownership is not unique")
    return {selected: winners[0]}


def _read(reply, ctx, *, fix_change=None, selection=None, metadata=None):
    from .engineer import EDIT_KINDS
    if not _bounded_text(reply):
        raise Unusable("missing reply or reply exceeds reader byte limit")
    blocks = [(n, match.group(2).strip().lower(), match.group(3)) for n, match in enumerate(FENCE.finditer(reply))]
    manifests = []
    for n, lang, body in blocks:
        if lang in ("json", "jsonc", "json5") or (lang == "" and body.lstrip().startswith("{")):
            manifests.append((n, body))
    if not manifests and not blocks:
        manifests = [(-1, reply.strip())]
    if len(manifests) != 1:
        raise Unusable("expected one manifest object, found %d" % len(manifests))
    manifest, repairs = tolerant_json(manifests[0][1])
    manifest = normalize(manifest, {"changes": Field(list, True, [])}, repairs=repairs)
    entries = manifest["changes"]
    v292 = p.is_v292(getattr(ctx, "configuration", None))
    if v292 and metadata is not None:
        metadata.update(change_count=len(entries), entries=entries)
    if v292 and selection is not None:
        selection["reply_change_count"] = len(entries)
    if selection is not None and not v292:
        raise Unusable("retry selection belongs only to v2.9.2")
    selected = _selected_entry(entries, selection) if selection is not None else None
    if len(entries) > p.MAX_CHANGES and selected is None:
        raise Unusable("changes count %d exceeds %d" % (len(entries), p.MAX_CHANGES))
    if fix_change is not None and len(entries) != 1 and selected is None:
        raise Unusable("a fix must contain exactly its one change")
    originals = entries
    inline_repairs = [[] for entry in entries]
    if v292:
        entries = [_inline_source(entry, log) for entry, log in zip(entries, inline_repairs)]
    code = [(n, lang, body) for n, lang, body in blocks if n != manifests[0][0]]
    owners = (_large_retry_source_owner(entries, code, selected, ctx, fix_change) if len(entries) > p.MAX_CHANGES else
              _source_owners(entries, code, ctx, fix_change, selected=selected))
    results = []
    for index, prepared in enumerate(entries, 1):
        if selected is not None and index - 1 != selected:
            continue
        original = originals[index - 1]
        log = copy.deepcopy(repairs) + inline_repairs[index - 1]
        try:
            if not isinstance(original, dict):
                raise Unusable("change must be an object")
            entry = copy.deepcopy(prepared)
            target = entry.get("revises", entry.get("id"))
            if target is None and fix_change is not None:
                target = fix_change.entry.get("revises", fix_change.entry.get("id"))
            parent = ctx.parent.get(target) if isinstance(target, str) and target in ctx.parent.order else None
            kind = entry.get("kind", fix_change.kind if fix_change else "revision" if parent else "new")
            if kind == "revision" and parent is None:
                kind = "new"
                entry.pop("revises", None)
                log.append({"rule": "unknown_revision_is_new", "path": "$.kind"})
            if kind not in EDIT_KINDS:
                raise Unusable("unknown change kind %r" % kind)
            if fix_change is not None and (kind != fix_change.kind or (
                    fix_change.kind != "new" and target != fix_change.entry.get(
                        "revises" if fix_change.kind == "revision" else "id"))):
                raise Unusable("fix changes its kind or incumbent target")
            source, rule = _source(entry, owners.get(index - 1), (fix_change, parent)) if kind in ("new", "revision") else (None, None)
            if rule:
                log.append({"rule": rule, "path": "$.source"})
            entry.pop("source", None)
            if "kind" in entry:
                entry["kind"] = kind
            parent_values = ({key: list(getattr(parent, key)) if isinstance(getattr(parent, key, None), tuple)
                              else getattr(parent, key) for key in schema(kind) if hasattr(parent, key)} if parent else {})
            inherited = (fix_change.entry if fix_change else {}, parent_values)
            entry = normalize(entry, schema(kind, train=ctx.mode == "train", source=source or "", entry=entry, target=target),
                              inherited=inherited, repairs=log)
            for n, test in enumerate(entry.get("replay_tests", [])):
                if isinstance(test, dict):
                    try:
                        entry["replay_tests"][n] = normalize(test, test_schema(test),
                            path="$.replay_tests[%d]" % n, repairs=log)
                    except Unusable as error:
                        log.append({"rule": "malformed_test", "path": "$.replay_tests[%d]" % n, "reason": str(error)})
            results.append({"entry": entry, "source": source, "repairs": log, "error": None})
        except Unusable as error:
            results.append({"entry": original, "source": None, "repairs": log, "error": str(error)})
        if v292:
            results[-1]["original"] = copy.deepcopy(original)
    return results


def schema_document():
    """Full format retry specification and example, generated from the reader."""
    from .engineer import EDIT_KINDS
    def describe(fields):
        return {key: {"type": "/".join(t.__name__ for t in (spec.type if isinstance(spec.type, tuple) else (spec.type,))),
                      "required": spec.required, "default": spec.default,
                      **({"fields": describe(spec.children)} if spec.children else {})}
                for key, spec in fields.items()}
    example_source = "def applies(view):\n    return True\ndef before_call(view, state):\n    return {}\n"
    sample = normalize({}, schema(source=example_source), repairs=[])
    example = "```json\n" + json.dumps({"changes": [sample]}, sort_keys=True) + "\n```\n```python\n" + example_source + "```"
    return {"changes": {"type": "list", "required": True, "max": p.MAX_CHANGES},
            "kinds": {kind: describe(schema(kind)) for kind in EDIT_KINDS},
            "replay_tests": {kind: {"hooks": list(hooks), "fields": describe(test_schema({
                "hook": hooks[0], "property": {"kind": kind}}))} for kind, (hooks, _) in replay.PROPERTY_KINDS.items()},
            "replay_limits": replay.test_format_limits(), "example": example}
