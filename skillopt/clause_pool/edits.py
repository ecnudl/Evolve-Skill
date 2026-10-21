"""Decompose a candidate Skill into single edits relative to its parent, and apply any set of edits (zero calls).

A Skill is a sequence of blocks -- a heading line, a top-level bullet with its continuation lines, an HTML comment or
a paragraph -- each kept with the exact text that separates it from the previous block (line endings of any kind), so
that applying no edit reproduces the parent text exactly. Blocks are aligned on their exact text (separator
included); a replaced span is split into one-to-one replacements (a block whose text is unchanged but moved, a new
block similar to an old one, or one keeping most of its text), inserts and deletes, so that every edit touches at most
one parent block; an inserted heading and the blocks inserted right after it with no blank line in between are one
edit; a different trailing text is a ``tail`` edit. ``decompose`` checks that applying all its edits reproduces the
candidate exactly, and raises otherwise. (Texts are compared as given: a caller that reads files with universal
newlines, as the probe does, round-trips the text the probe measures, not the file's raw bytes.)

Contract: ``apply(p, []) == p`` and ``apply(p, decompose(p, c, name)) == c`` for every parent and candidate text.
"""
from __future__ import annotations

import difflib
import re

from skillopt.skill_features.tagger import guidance_tags

VERSION = "clause-pool-edits-v1"
# A new block replaces an old one when they are this similar, or when it keeps this share of the old block's text
# (an old rule rewritten at length); otherwise it is an insert.
PAIR_RATIO, PAIR_COVERAGE = 0.5, 0.6
OPS = ("replace", "insert", "delete", "tail")
_BULLET = re.compile(r"^[-*+]\s|^\d+[.)]\s")
_ENDINGS = "\r\n"
ID = re.compile(r"[A-Za-z0-9_-]{1,40}")


class Conflict(ValueError):
    """Two edits change the same parent block (or both change the tail)."""


def blocks(text):
    """([[separator, body], ...], tail): ``separator`` is the exact text before the block, ``body`` the block without
    its final line ending; ``"".join(s + b for s, b in blocks) + tail == text``."""
    result, current, pending, sep = [], [], "", ""

    def flush():
        nonlocal current, pending
        if current:
            body = "".join(current)
            stripped = body.rstrip(_ENDINGS)
            result.append([sep, stripped])
            pending, current = body[len(stripped):], []

    def start(line):
        nonlocal current, pending, sep
        sep, pending, current = pending, "", [line]

    for line in text.splitlines(keepends=True):
        if not line.strip():
            flush()
            pending += line
        elif line.lstrip().startswith("#"):
            flush()
            start(line)
            flush()
        elif _BULLET.match(line) or line.lstrip().startswith("<!--") or not current:
            flush()
            start(line)
        else:
            current.append(line)
    flush()
    return result, pending


def _norm(body):
    return " ".join(body.split())


def _is_heading(body):
    return body.lstrip().startswith("#")


def edit_tags(op, old, new):
    """What an edit is about (design section 6): for a replacement the tags its new text adds over the text it
    replaces (all of the new text's tags if it adds none), for an insert the new text's tags. A delete or a tail edit
    has no new guidance: it is generic (an empty list, every item)."""
    if op in ("delete", "tail"):
        return []
    added = sorted(set(guidance_tags(new)) - set(guidance_tags(old or "")))
    return added if op == "replace" and added else guidance_tags(new)


def _similarity(old, new):
    """(score, pairs): score = max(difflib ratio, share of the old text kept in the new one); pairs when the ratio
    reaches PAIR_RATIO or the kept share reaches PAIR_COVERAGE."""
    a, b = _norm(old), _norm(new)
    if not a or not b:
        return 0.0, False
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ratio = matcher.ratio()
    kept = sum(block.size for block in matcher.get_matching_blocks()) / len(a)
    return max(ratio, kept), ratio >= PAIR_RATIO or kept >= PAIR_COVERAGE


def _split_replace(old_blocks, new_blocks, i1, j1):
    """One-to-one pairing inside a replaced span, order-preserving: blocks whose text is unchanged up to whitespace
    (only their separator moved) are anchored first; between anchors, each new block pairs with the most similar
    remaining old block when they pair (``_similarity``); unpaired new blocks are inserts before the next old block,
    unpaired old blocks are deletes. Headings pair only with headings."""
    out = []
    anchors = difflib.SequenceMatcher(None, [_norm(b) for _, b in old_blocks], [_norm(b) for _, b in new_blocks],
                                      autojunk=False)
    for tag, a1, a2, b1, b2 in anchors.get_opcodes():
        if tag == "equal":
            out.extend(("replace", i1 + a1 + n, j1 + b1 + n) for n in range(a2 - a1))
        else:
            out.extend(_pair(old_blocks[a1:a2], new_blocks[b1:b2], i1 + a1, j1 + b1))
    return out


def _pair(old_blocks, new_blocks, i1, j1):
    out, k = [], 0
    for j, new in enumerate(new_blocks):
        best, at = 0.0, None
        for m in range(k, len(old_blocks)):
            if _is_heading(old_blocks[m][1]) != _is_heading(new[1]):
                continue
            score, pairs = _similarity(old_blocks[m][1], new[1])
            if pairs and score > best:
                best, at = score, m
        if at is not None:
            out.extend(("delete", i1 + m, None) for m in range(k, at))
            out.append(("replace", i1 + at, j1 + j))
            k = at + 1
        else:
            out.append(("insert", i1 + k, j1 + j))
    out.extend(("delete", i1 + m, None) for m in range(k, len(old_blocks)))
    return out


def decompose(parent, candidate, source):
    """The single edits that turn ``parent`` into ``candidate``; ``source`` names the candidate (an id of letters,
    digits, _ or -). Each edit: id, source, op (replace/insert/delete/tail), at (the parent block it replaces or
    deletes or inserts before; the number of parent blocks for an append or the tail), seq, old, new, separator (the
    candidate's text before the new block), blocks, tags. Raises ValueError if the edits do not reproduce the
    candidate exactly."""
    if not ID.fullmatch(source or ""):
        raise ValueError("A source name is letters, digits, _ or - (at most 40)")
    pb, ptail = blocks(parent)
    cb, ctail = blocks(candidate)
    ops = difflib.SequenceMatcher(None, [s + b for s, b in pb], [s + b for s, b in cb], autojunk=False).get_opcodes()
    steps = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        if tag == "insert":
            steps.extend(("insert", i1, j) for j in range(j1, j2))
        elif tag == "delete":
            steps.extend(("delete", i, None) for i in range(i1, i2))
        else:
            steps.extend(_split_replace(pb[i1:i2], cb[j1:j2], i1, j1))
    groups = []
    for op, at, j in steps:
        prev = groups[-1] if groups else None
        if (prev and op == "insert" and prev[0] == "insert" and prev[1] == at and j == prev[2][-1] + 1
                and _is_heading(cb[prev[2][0]][1]) and not _is_heading(cb[j][1]) and len(cb[j][0].splitlines()) <= 1):
            prev[2].append(j)
        else:
            groups.append([op, at, [j] if j is not None else []])
    # ``apply`` gives a parent block that ends up first the parent's leading text; a candidate that keeps that block's
    # own separator before it instead differs only in whitespace there: a replacement of the block by itself.
    inserted = {at for op, at, _ in groups if op == "insert"}
    deleted = {at for op, at, _ in groups if op == "delete"}
    replaced = {at for op, at, _ in groups if op == "replace"}
    first = next(k for k in range(len(pb) + 1) if k in inserted or k == len(pb) or k not in deleted)
    if (0 < first < len(pb) and first not in inserted | replaced and cb and cb[0][1] == pb[first][1]
            and cb[0][0] != pb[0][0]):
        groups.insert(sum(1 for g in groups if g[1] < first), ["replace", first, [0]])
    edits = []
    for seq, (op, at, js) in enumerate(groups):
        old = pb[at][1] if op in ("replace", "delete") else None
        new = "".join((cb[j][0] if n else "") + cb[j][1] for n, j in enumerate(js)) if js else None
        edits.append({"version": VERSION, "id": "%s-e%02d" % (source, seq), "source": source, "op": op, "at": at,
                      "seq": seq, "old": old, "new": new, "separator": cb[js[0]][0] if js else None,
                      "blocks": len(js), "tags": edit_tags(op, old, new)})
    if ctail != ptail:
        seq = len(edits)
        edits.append({"version": VERSION, "id": "%s-e%02d" % (source, seq), "source": source, "op": "tail",
                      "at": len(pb), "seq": seq, "old": ptail, "new": ctail, "separator": None, "blocks": 0, "tags": []})
    if apply(parent, edits) != candidate:
        raise ValueError("The candidate cannot be represented as edits of the parent")
    return edits


def _check(edit, pb, ptail):
    if edit.get("op") not in OPS:
        raise ValueError("Unknown edit op: %s" % edit.get("id"))
    at = edit.get("at")
    if type(at) is not int or not 0 <= at <= len(pb):
        raise ValueError("An edit's position is outside the parent: %s" % edit.get("id"))
    if edit["op"] in ("replace", "delete"):
        if at == len(pb) or edit.get("old") != pb[at][1]:
            raise ValueError("An edit does not match the parent block it changes: %s" % edit.get("id"))
    if edit["op"] in ("replace", "insert") and type(edit.get("new")) is not str:
        raise ValueError("An edit has no new text: %s" % edit.get("id"))
    if edit["op"] == "tail" and (at != len(pb) or edit.get("old") != ptail or type(edit.get("new")) is not str):
        raise ValueError("A tail edit does not match the parent's tail: %s" % edit.get("id"))


def apply(parent, edits):
    """The parent with ``edits`` applied (any subset, possibly from several sources). Raises Conflict when two edits
    change the same parent block or both change the tail, ValueError for an edit that does not fit the parent.
    Inserts at one position keep (source, seq) order."""
    pb, tail = blocks(parent)
    changed, inserts, new_tail = {}, {}, None
    for e in sorted(edits, key=lambda e: (e["at"], e["source"], e["seq"])):
        _check(e, pb, tail)
        if e["op"] == "insert":
            inserts.setdefault(e["at"], []).append(e)
        elif e["op"] == "tail":
            if new_tail is not None:
                raise Conflict("Two edits change the tail: %s" % e["id"])
            new_tail = e
        elif e["at"] in changed:
            raise Conflict("%s and %s both change parent block %d" % (changed[e["at"]]["id"], e["id"], e["at"]))
        else:
            changed[e["at"]] = e
    pieces = []  # (separator, body, from an edit)
    for k in range(len(pb) + 1):
        pieces.extend((e["separator"] or "", e["new"], True) for e in inserts.get(k, []))
        if k < len(pb):
            sep, body = pb[k]
            e = changed.get(k)
            if e is None:
                pieces.append((sep, body, False))
            elif e["op"] == "replace":
                pieces.append((e["separator"] or "", e["new"], True))
            # a deleted block is dropped together with its separator
    out = []
    for i, (sep, body, edited) in enumerate(pieces):
        if i == 0 and not edited:
            sep = pb[0][0]  # a parent block that comes first carries the parent's leading text
        elif i > 0 and not sep:
            sep = "\n"  # a block that was first elsewhere needs a line break here
        out.append(sep + body)
    return "".join(out) + (new_tail["new"] if new_tail else tail)


def no_effect(parent, edits):
    """Whether applying ``edits`` changes nothing but whitespace (such an edit is not measured)."""
    return _norm(apply(parent, edits)) == _norm(parent)
