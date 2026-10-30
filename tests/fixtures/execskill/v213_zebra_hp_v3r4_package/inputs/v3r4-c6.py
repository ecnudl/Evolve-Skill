import itertools
import re

ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7}
NUMW = {"one": 1, "two": 2, "three": 3, "four": 4}
MONTHS = {"jan": "january", "feb": "february", "mar": "march", "apr": "april", "jun": "june", "jul": "july", "aug": "august", "sept": "september", "sep": "september", "oct": "october", "nov": "november", "dec": "december"}
NODE_LIMIT = 250000
SOL_CAP = 8
SEP = "[-\\s_]{0,2}"


def applies(view):
    if not isinstance(view, dict):
        return False
    q = view.get("question")
    cols = view.get("columns")
    return (isinstance(q, str) and q.startswith("There are")
            and isinstance(cols, list) and "## Clues:" in q)


def _pat(word):
    chars = [re.escape(c) for c in word if c.isalnum()]
    if not chars:
        return None
    return r"(?<![a-z0-9])" + SEP.join(chars) + r"(?![a-z0-9])"


def _variants(v):
    out = [v]
    if v.endswith("s") and len(v) > 3:
        out.append(v[:-1])
    else:
        out.append(v + "s")
    if v.endswith("ing") and len(v) > 5:
        out.append(v[:-3] + "s")
    if v.endswith("e"):
        out.append(v[:-1] + "ish")
    else:
        out.append(v + "ish")
    if v in MONTHS:
        out.append(MONTHS[v])
    else:
        for a, b in MONTHS.items():
            if v == b:
                out.append(a)
    return out


def _find_values(text, values):
    hits = []
    for v in values:
        for w in _variants(v):
            p = _pat(w)
            if p is None:
                continue
            for mm in re.finditer(p, text, re.I):
                s, e = mm.span()
                if any(s < b and a < e for a, b, _ in hits):
                    continue
                hits.append((s, e, v))
    hits.sort()
    return hits


def _parse_clue(text, values):
    hits = _find_values(text, values)
    vals = []
    for _, _, v in hits:
        if v not in vals:
            vals.append(v)
    masked = list(text)
    for s, e, _ in hits:
        for i in range(s, e):
            masked[i] = " "
    res = "".join(masked).lower()
    neg = bool(re.search(r"\bnot\b", res))
    if len(vals) >= 2:
        m = re.search(r"there (?:is|are) (\w+) houses? between", res)
        if m and m.group(1) in NUMW:
            return (vals[:2], "gap", NUMW[m.group(1)] + 1, neg)
        if "next to each other" in res:
            return (vals[:2], "adj", None, neg)
        if re.search(r"directly (?:to the )?left of", res):
            return (vals[:2], "left1", None, neg)
        if re.search(r"directly (?:to the )?right of", res):
            return (vals[:2], "right1", None, neg)
        if "to the left of" in res:
            return (vals[:2], "left", None, neg)
        if "to the right of" in res:
            return (vals[:2], "right", None, neg)
    m = re.search(r"in the (\w+) house", res)
    if m and vals and m.group(1) in ORD:
        return (vals[:1], "notpos" if neg else "pos", ORD[m.group(1)], neg)
    if len(vals) >= 2 and re.search(r"\bis\b|\bare\b|\bwas\b", res):
        return (vals[:2], "same", None, neg)
    return None


def _involved(cl, valcats):
    cats = set()
    for v in cl[0]:
        for c in valcats.get(v, []):
            cats.add(c)
    return cats


def _check(cl, pos, valcats):
    vals, rel, k, neg = cl
    if rel in ("pos", "notpos"):
        hs = []
        for c in valcats.get(vals[0], []):
            h = pos[c].get(vals[0])
            if h:
                hs.append(h)
        if not hs:
            return True
        if rel == "pos":
            return any(h == k for h in hs)
        return any(h != k for h in hs)
    vx, vy = vals[0], vals[1]
    combos = []
    for cx in valcats.get(vx, []):
        for cy in valcats.get(vy, []):
            if rel == "same" and cx == cy:
                continue
            hx = pos[cx].get(vx)
            hy = pos[cy].get(vy)
            if hx and hy:
                combos.append((hx, hy))
    if not combos:
        return True

    def ok(hx, hy):
        if rel == "same":
            r = hx == hy
        elif rel == "left1":
            r = hx == hy - 1
        elif rel == "right1":
            r = hx == hy + 1
        elif rel == "left":
            r = hx < hy
        elif rel == "right":
            r = hx > hy
        elif rel == "adj":
            r = abs(hx - hy) == 1
        else:
            r = abs(hx - hy) == k
        return (not r) if neg else r

    return any(ok(hx, hy) for hx, hy in combos)


def before_call(view, state):
    q = view.get("question", "")
    cols = list(view.get("columns") or [])
    facts = []
    warnings = []
    n = 0
    m = re.search(r"There are (\d+) houses", q)
    if m:
        n = int(m.group(1))
    cats_orig = []
    for line in q.splitlines():
        s = line.strip()
        if s.startswith("- ") and "`" in s:
            vals = re.findall(r"`([^`]*)`", s)
            vals = [v.strip() for v in vals if v.strip()]
            if vals:
                cats_orig.append(vals)
    clue_part = q.split("## Clues:", 1)[1] if "## Clues:" in q else ""
    raw = []
    for line in clue_part.splitlines():
        mm = re.match(r"\s*(\d+)\.\s*(.+)$", line)
        if mm:
            raw.append(mm.group(2).strip())
    if n < 2 or not cats_orig or not raw:
        return {"facts": ["Could not parse the puzzle structure."],
                "warnings": ["Parsing failed; no grid computed."]}
    nc = len(cats_orig)
    cats_low = [[v.lower() for v in c] for c in cats_orig]
    allvals = sorted({v for c in cats_low for v in c}, key=len, reverse=True)
    valcats = {}
    for i, c in enumerate(cats_low):
        for v in c:
            valcats.setdefault(v, []).append(i)
    clues = []
    skipped = []
    for idx, text in enumerate(raw):
        cl = _parse_clue(text, allvals)
        if cl is None or not _involved(cl, valcats):
            skipped.append(idx + 1)
        else:
            clues.append(cl)
    facts.append("Parsed %d categories and %d numbered clues from the puzzle text." % (nc, len(raw)))
    if skipped:
        warnings.append("Clues not understood and ignored: %s." % ", ".join(str(x) for x in skipped[:10]))
    if not clues:
        return {"facts": facts, "warnings": warnings + ["No usable clues; no grid computed."]}
    mention = [0] * nc
    for cl in clues:
        for c in _involved(cl, valcats):
            mention[c] += 1
    order = sorted(range(nc), key=lambda i: (-mention[i], i))
    level_of = {c: i for i, c in enumerate(order)}
    by_level = {}
    single = [[] for _ in range(nc)]
    pair_clues = {}
    for cl in clues:
        inv = _involved(cl, valcats)
        lvl = max(level_of[c] for c in inv)
        by_level.setdefault(lvl, []).append(cl)
        if len(inv) == 1:
            single[next(iter(inv))].append(cl)
        elif len(inv) == 2:
            pair_clues.setdefault(tuple(sorted(inv)), []).append(cl)
    pos = [dict() for _ in range(nc)]
    cands = []
    for ci in range(nc):
        ok_perms = []
        vals = cats_low[ci]
        for p in itertools.permutations(range(1, n + 1)):
            d = dict(zip(vals, p))
            if single[ci]:
                pos[ci] = d
                good = all(_check(cl, pos, valcats) for cl in single[ci])
                pos[ci] = {}
                if not good:
                    continue
            ok_perms.append(d)
        cands.append(ok_perms)
        if not ok_perms:
            warnings.append("No arrangement of one category satisfies the parsed clues.")
            return {"facts": facts, "warnings": warnings + ["No assignment of values to houses satisfied the parsed clues."]}
    sols = []
    nodes = [0]

    def dfs(lvl, cands):
        if len(sols) >= SOL_CAP or nodes[0] > NODE_LIMIT:
            return
        if lvl == nc:
            sols.append([dict(p) for p in pos])
            return
        ci = order[lvl]
        for d in cands[ci]:
            nodes[0] += 1
            if nodes[0] > NODE_LIMIT:
                pos[ci] = {}
                return
            pos[ci] = d
            good = True
            for cl in by_level.get(lvl, []):
                if not _check(cl, pos, valcats):
                    good = False
                    break
            if good:
                fc = None
                for lj in range(lvl + 1, nc):
                    cj = order[lj]
                    key = (ci, cj) if ci < cj else (cj, ci)
                    rel = pair_clues.get(key, ())
                    if not rel:
                        continue
                    keep = []
                    for e in cands[cj]:
                        pos[cj] = e
                        ok2 = True
                        for cl in rel:
                            if not _check(cl, pos, valcats):
                                ok2 = False
                                break
                        if ok2:
                            keep.append(e)
                    pos[cj] = {}
                    if not keep:
                        good = False
                        break
                    if len(keep) < len(cands[cj]):
                        if fc is None:
                            fc = list(cands)
                        fc[cj] = keep
                if good:
                    dfs(lvl + 1, fc if fc is not None else cands)
        pos[ci] = {}

    dfs(0, cands)
    if nodes[0] > NODE_LIMIT:
        warnings.append("Search stopped at a node limit; the grid may be incomplete.")
    if not sols:
        return {"facts": facts,
                "warnings": warnings + ["No assignment of values to houses satisfied the parsed clues."]}
    if len(sols) == 1:
        facts.append("An exact search over house permutations found exactly one grid satisfying every parsed clue; each table row lists one house.")
    elif len(sols) >= SOL_CAP:
        warnings.append("At least %d different grids satisfy the parsed clues; ? marks cells that differ among them." % SOL_CAP)
    else:
        warnings.append("%d different grids satisfy the parsed clues; ? marks cells that differ among them." % len(sols))
    headers = ["House"] + (cols if len(cols) == nc else ["Cat%d" % (i + 1) for i in range(nc)])
    table = [headers[:12]]
    for h in range(1, n + 1):
        row = [str(h)]
        for i in range(nc):
            at = []
            for s in sols:
                for v in cats_low[i]:
                    if s[i].get(v) == h:
                        at.append(v)
                        break
            uniq = set(at)
            if len(at) == len(sols) and len(uniq) == 1:
                low = at[0]
                orig = low
                for v in cats_orig[i]:
                    if v.lower() == low:
                        orig = v
                        break
                row.append(orig[:40])
            else:
                row.append("?")
        table.append(row[:12])
    return {"facts": facts, "table": table, "warnings": warnings}
