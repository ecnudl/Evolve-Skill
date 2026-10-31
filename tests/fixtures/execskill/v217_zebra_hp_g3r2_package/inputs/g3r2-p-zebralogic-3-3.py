# zebra-csp-solve-v2 (fault fix: removed module-level class, use budget flag)
import re

_MAX_BUDGET = 500000
_ORD = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
        'sixth': 6, 'seventh': 7, 'eighth': 8}
_NUMW = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6}


def applies(view):
    q = view.get('question') or ''
    return ('## Clues:' in q) and ('houses' in q)


def _parse_question(q):
    cats = []
    names = []
    for line in q.split('\n'):
        s = line.strip()
        if s.startswith('- ') and ':' in s and '`' in s:
            head, _, tail = s.partition(':')
            vals = re.findall(r'`([^`]+)`', tail)
            if vals:
                cats.append(vals)
                nm = head[2:].strip()
                names.append(nm[:12] if nm else '')
    m = re.search(r'There are (\d+) houses', q)
    H = int(m.group(1)) if m else 0
    clues = []
    mc = q.find('## Clues:')
    if mc >= 0:
        for line in q[mc:].split('\n'):
            s = line.strip()
            mm = re.match(r'^(\d+)\.\s*(.*)$', s)
            if mm:
                clues.append((int(mm.group(1)), mm.group(2).strip()))
    return H, cats, names, clues


def _mentions(text, cats):
    low = text.lower()
    out = []
    for ci, vals in enumerate(cats):
        for v in vals:
            vl = v.lower()
            m = re.search(r'(?<![a-z])' + re.escape(vl) + r'(?![a-z])', low)
            if m:
                out.append((m.start(), ci, v))
    out.sort()
    return out


def _classify(text, men):
    low = text.lower()
    has_not = bool(re.search(r'\bnot\b', low))
    if re.search(r'houses? between', low):
        m = re.search(r'(\w+) houses? between', low)
        n = _NUMW.get(m.group(1)) if m else None
        if n is None or len(men) != 2 or has_not:
            return None
        return ('between', men, n)
    if 'next to each other' in low or 'are neighbors' in low:
        if has_not or len(men) != 2:
            return None
        return ('adj', men, None)
    if 'directly left of' in low or 'immediately left of' in low:
        if has_not or len(men) != 2:
            return None
        return ('leftadj', men, None)
    if 'directly right of' in low or 'immediately right of' in low:
        if has_not or len(men) != 2:
            return None
        return ('rightadj', men, None)
    if 'to the left of' in low:
        if has_not or len(men) != 2:
            return None
        return ('lt', men, None)
    if 'to the right of' in low:
        if has_not or len(men) != 2:
            return None
        return ('gt', men, None)
    m = re.search(r'in the (\w+) house', low)
    if m:
        n = _ORD.get(m.group(1))
        if n is None or len(men) != 1:
            return None
        if has_not:
            return ('negpos', men, n)
        return ('pos', men, n)
    if has_not:
        if len(men) == 2 and re.search(r'\bis\b', low):
            return ('neq', men, None)
        return None
    if len(men) == 2:
        return ('eq', men, None)
    return None


def _solve(H, cats, cons):
    solutions = []
    placed = {}
    counter = [0]
    budget = [False]
    N = len(cats)

    def ready_ok():
        for kind, refs, data in cons:
            complete = True
            for r in refs:
                if r not in placed:
                    complete = False
                    break
            if not complete:
                continue
            hs = [placed[r] for r in refs]
            if kind == 'pos':
                if hs[0] != data:
                    return False
            elif kind == 'negpos':
                if hs[0] == data:
                    return False
            elif kind == 'eq':
                if hs[0] != hs[1]:
                    return False
            elif kind == 'neq':
                if hs[0] == hs[1]:
                    return False
            elif kind == 'leftadj':
                if hs[0] != hs[1] - 1:
                    return False
            elif kind == 'rightadj':
                if hs[0] != hs[1] + 1:
                    return False
            elif kind == 'adj':
                if abs(hs[0] - hs[1]) != 1:
                    return False
            elif kind == 'lt':
                if not hs[0] < hs[1]:
                    return False
            elif kind == 'gt':
                if not hs[0] > hs[1]:
                    return False
            elif kind == 'between':
                if abs(hs[0] - hs[1]) != data + 1:
                    return False
        return True

    def put(ci, vi, used):
        if len(solutions) >= 2 or budget[0]:
            return
        if ci == N:
            solutions.append(dict(placed))
            return
        vals = cats[ci]
        if vi == len(vals):
            put(ci + 1, 0, set())
            return
        for h in range(1, H + 1):
            if h in used:
                continue
            counter[0] += 1
            if counter[0] > _MAX_BUDGET:
                budget[0] = True
                return
            placed[(ci, vals[vi])] = h
            used.add(h)
            if ready_ok():
                put(ci, vi + 1, used)
            used.discard(h)
            del placed[(ci, vals[vi])]
            if len(solutions) >= 2 or budget[0]:
                return

    put(0, 0, set())
    if budget[0]:
        return None
    return solutions


def before_call(view, state):
    q = view.get('question') or ''
    H, cats, names, clues = _parse_question(q)
    if H < 2 or H > 7 or not cats or not clues:
        return None
    if len(cats) > 11:
        return None
    if any(len(c) != H for c in cats):
        return None
    cons = []
    for num, text in clues:
        men = _mentions(text, cats)
        c = _classify(text, men)
        if c is None:
            return None
        kind, men, data = c
        refs = [(ci, v) for _, ci, v in men]
        if len(set(refs)) != len(refs):
            return None
        cons.append((kind, refs, data))
    sols = _solve(H, cats, cons)
    if not sols or len(sols) != 1:
        return None
    sol = sols[0]
    header = ['House']
    for i in range(len(cats)):
        header.append(names[i] if names[i] else 'Cat%d' % (i + 1))
    table = [header]
    for h in range(1, H + 1):
        row = [str(h)]
        for ci, vals in enumerate(cats):
            cell = ''
            for v in vals:
                if sol.get((ci, v)) == h:
                    cell = v
                    break
            row.append(cell[:40])
        table.append(row)
    facts = [
        'Parsed all %d clues of this puzzle and ran an exhaustive backtracking search over house assignments.' % len(clues),
        'Exactly one assignment satisfies every parsed clue; the table gives it (each row is one house, 1 = leftmost).',
    ]
    return {'facts': facts, 'table': table}
