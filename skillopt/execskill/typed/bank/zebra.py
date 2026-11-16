"""ZebraLogic made items: new logic-grid puzzles written and certified by fixed code (design section 5, source 乙;
BANK-PILOT B31).

The practice pool has no unused puzzle of the judged sizes left (BANK-PILOT B28), so new ones are MADE here. No model
takes part and no solver's success admits anything: the puzzle language is learned from the pinned practice pool, a
puzzle is built the way the benchmark's paper describes its own (Lin et al. 2025, arXiv 2502.01100, Algorithm 1: a
random grid, every true clue, clues taken away in a weighted random order as long as the grid stays the only
solution), and its answer is certified by exhaustive search.

What fixed code establishes before anything made is trusted:

- the language is complete and exact (``learn``): every clue line of every pool puzzle is one of nine sentence
  patterns over phrases that each name one value of one column, and writing a parsed puzzle out again gives its text
  byte for byte;
- the reading is right (the anchor: the reference is reproduced before anything new is computed): solved from its
  parsed clues alone, every pool puzzle has exactly one solution, and it is the reference grid;
- a made puzzle is certified from its TEXT (``certify``): parsed like a real one, solved by two solvers written
  independently of each other, exactly one solution, the stored grid; and no clue can be left out, as in every pool
  puzzle.

Pure functions; nothing here calls a model or reads a file. A clue is ``(kind, a, b)``: ``a`` and ``b`` are
``(column, value)``, and for the two kinds that name a house ``b`` is the house, counted from 0.
"""
from __future__ import annotations

import itertools
import re

ORDINALS = ('first', 'second', 'third', 'fourth', 'fifth', 'sixth')
OPENING = ('There are %d houses, numbered 1 to %d from left to right, as seen from across the street. Each house is '
           'occupied by a different person. Each house has a unique attribute for each of the following characteristics:')
OPENING_PATTERN = re.compile(re.escape(OPENING).replace('%d', '([2-6])'))
ATTRIBUTE_LINE = re.compile(r' - (.+): ((?:`[^`\n]+`, )*`[^`\n]+`)')
CLUE_HEAD = '## Clues:'
# kind -> (text before the first phrase, between the phrases, after the second; None where a house is named)
HOUSE_KINDS = {'found_at': ' is in the %s house.', 'not_at': ' is not in the %s house.'}
PAIR_KINDS = {
    'same': ('', ' is ', '.'),
    'direct_left': ('', ' is directly left of ', '.'),
    'left_of': ('', ' is somewhere to the left of ', '.'),
    'right_of': ('', ' is somewhere to the right of ', '.'),
    'next_to': ('', ' and ', ' are next to each other.'),
    'one_between': ('There is one house between ', ' and ', '.'),
    'two_between': ('There are two houses between ', ' and ', '.'),
}
KINDS = tuple(HOUSE_KINDS) + tuple(PAIR_KINDS)
RULES = {   # what a pair kind says about the houses of its first and second value
    'same': lambda a, b: a == b,
    'direct_left': lambda a, b: a + 1 == b,
    'left_of': lambda a, b: a < b,
    'right_of': lambda a, b: a > b,
    'next_to': lambda a, b: abs(a - b) == 1,
    'one_between': lambda a, b: abs(a - b) == 2,
    'two_between': lambda a, b: abs(a - b) == 3,
}


# In which order the true clues of a grid are tried for removal: a clue's turn is drawn with its kind's weight, a
# heavier kind comes earlier and is left in the puzzle less often. The paper says its sampling is weighted by kind and
# gives no numbers; these were fitted ONCE (2026-11-14) to the clue kinds of the 200 pool puzzles of the judged sizes
# (5 or 6 houses): damped fixed-point steps on the pooled shares, left/right tied, rounded. With them 1,000 made
# puzzles differ from the 200 real ones by 0.015 in total variation of the pooled kind shares and by at most 0.9 in
# the mean number of clues of any size. The comparison of a bank with the pool is ``compare``, made again each time.
REMOVAL_WEIGHTS = {'found_at': 0.73, 'not_at': 0.77, 'same': 0.53, 'direct_left': 0.96, 'left_of': 1.15,
                   'right_of': 1.15, 'next_to': 1.17, 'one_between': 1.44, 'two_between': 1.56}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def opening_form(phrase):
    """A phrase as it opens a sentence (the pool's one rule: its first letter in upper case)."""
    return phrase[:1].upper() + phrase[1:]


# ---- reading a puzzle text ---------------------------------------------------------------------------------------------
def split_text(text):
    """(houses, [(introducing sentence, [values as listed])], [clue sentences]) of a puzzle text, or ValueError: the
    layout every pool puzzle has, and nothing else."""
    require(type(text) is str and text.endswith('\n') and text.count('\n' + CLUE_HEAD + '\n') == 1, 'Not the puzzle layout')
    head, clue_part = text.split('\n' + CLUE_HEAD + '\n')
    head_lines = head.split('\n')
    opening = OPENING_PATTERN.fullmatch(head_lines[0])
    require(opening is not None and opening.group(1) == opening.group(2) and head_lines[-1] == '', 'Not the opening sentence')
    houses, attributes = int(opening.group(1)), []
    for line in head_lines[1:-1]:
        match = ATTRIBUTE_LINE.fullmatch(line)
        require(match is not None, 'Not an attribute line: ' + line)
        values = match.group(2)[1:-1].split('`, `')
        require(len(values) == houses and len(set(values)) == houses, 'An attribute lists one value per house')
        attributes.append((match.group(1), values))
    require(attributes and len({intro for intro, _ in attributes}) == len(attributes), 'Distinct attributes')
    clue_lines = clue_part[:-1].split('\n')
    clues = []
    for number, line in enumerate(clue_lines, 1):
        prefix = '%d. ' % number
        require(line.startswith(prefix) and line == line.strip() and len(line) > len(prefix), 'Not a numbered clue: ' + line)
        clues.append(line[len(prefix):])
    return houses, attributes, clues


def _splits(sentence, kind):
    """Every way to read ``sentence`` as a pair sentence of ``kind``: (first phrase, second phrase)."""
    before, between, after = PAIR_KINDS[kind]
    if not (sentence.startswith(before) and sentence.endswith(after)):
        return []
    body = sentence[len(before):len(sentence) - len(after)]
    out, at = [], body.find(between)
    while at >= 0:
        if at > 0 and at + len(between) < len(body):
            out.append((body[:at], body[at + len(between):]))
        at = body.find(between, at + 1)
    return out


def _house_reading(sentence):
    """(kind, phrase, house) when the sentence names a house, else None."""
    for kind, tail in HOUSE_KINDS.items():
        for house, ordinal in enumerate(ORDINALS):
            end = tail % ordinal
            if sentence.endswith(end) and len(sentence) > len(end):
                return kind, sentence[:-len(end)], house
    return None


# ---- the language of the pool --------------------------------------------------------------------------------------------
def learn(rows):
    """The puzzle language of the pool rows ({'id', 'puzzle', 'solution': {'header', 'rows'}}), learned and checked
    in one pass; ValueError when the pool is not what this module can read and write exactly.

    Returns {'columns': {column: {'intro', 'values': {'<houses>': sorted values}}}, 'phrases': {column: {value: phrase
    as written inside a sentence}}, 'checks': counts}; plain JSON (the house count is a text key), so the language
    read back from its record is the language. A phrase's meaning is not read off its words: it is the one value
    that fits the reference grid in every clue the phrase occurs in (a house clue fixes it directly, a pair clue
    through the other phrase), and it must be the only one."""
    puzzles = []
    intro_of, column_of, value_sets = {}, {}, {}
    for row in rows:
        houses, attributes, sentences = split_text(row['puzzle'])
        header, table = row['solution']['header'], row['solution']['rows']
        require(header[0] == 'House' and len(header) == len(attributes) + 1 and len(table) == houses
                and [cells[0] for cells in table] == [str(house + 1) for house in range(houses)], 'A reference grid by house')
        place = {}
        for index, ((intro, values), column) in enumerate(zip(attributes, header[1:]), 1):
            require(intro_of.setdefault(column, intro) == intro and column_of.setdefault(intro, column) == column,
                    'One introducing sentence per column')
            require(sorted(cells[index] for cells in table) == sorted(values), 'The grid holds the listed values')
            require(value_sets.setdefault((column, houses), sorted(values)) == sorted(values),
                    'One value set per column and house count')
            for house, cells in enumerate(table):
                place[(column, cells[index])] = house
        puzzles.append({'id': row['id'], 'houses': houses, 'columns': [(column_of[intro], values) for intro, values in attributes],
                        'place': place, 'sentences': sentences, 'text': row['puzzle']})
    # 1. phrases of the sentences that cannot be read two ways: a house sentence, or a pair sentence of another kind
    #    than 'same' with one split (a phrase may itself contain " is ", never one of the longer joining texts)
    #    A phrase is known by its text with the first letter lowered (a phrase that opens a sentence is written
    #    with a capital); how it is written INSIDE a sentence is taken from the places where it stands inside one.
    readings, known, inside_forms, open_same = {}, set(), {}, []

    def seen(kind, first, second=None):
        known.add(_key(first))
        if kind in PAIR_KINDS:
            known.add(_key(second))
            inside_forms.setdefault(_key(second), set()).add(second)
            if PAIR_KINDS[kind][0] != '':
                inside_forms.setdefault(_key(first), set()).add(first)

    for number, puzzle in enumerate(puzzles):
        for line, sentence in enumerate(puzzle['sentences']):
            house = _house_reading(sentence)
            pair = [(kind, split) for kind in PAIR_KINDS if kind != 'same' for split in _splits(sentence, kind)]
            require(not (house and pair) and len(pair) <= 1, 'A clue sentence with two readings: ' + sentence)
            if house:
                readings[(number, line)] = house
                seen(house[0], house[1])
            elif pair:
                kind, (first, second) = pair[0]
                readings[(number, line)] = (kind, first, second)
                seen(kind, first, second)
            else:
                open_same.append((number, line))
    # 2. 'same' sentences: the one split with a known phrase on both sides; a sentence with one known side teaches
    #    the other phrase; repeated until nothing changes
    while open_same:
        left = []
        for number, line in open_same:
            splits = _splits(puzzles[number]['sentences'][line], 'same')
            both = [split for split in splits if _key(split[0]) in known and _key(split[1]) in known]
            one = [split for split in splits if _key(split[0]) in known or _key(split[1]) in known]
            chosen = both if len(both) == 1 else one if not both and len(one) == 1 else None
            require(len(both) <= 1, 'A clue sentence with two readings: ' + puzzles[number]['sentences'][line])
            if chosen is None:
                left.append((number, line))
                continue
            readings[(number, line)] = ('same',) + chosen[0]
            seen('same', *chosen[0])
        require(len(left) < len(open_same), 'Clue sentences that are none of the nine patterns: %d' % len(left))
        open_same = left
    # 3. meanings: the values that fit the reference grid wherever the phrase occurs
    fits = {}

    def narrow(phrase, options):
        fits[phrase] = options if phrase not in fits else fits[phrase] & options

    for (number, line), (kind, first, second) in readings.items():
        if kind in HOUSE_KINDS:
            place = puzzles[number]['place']
            narrow(_key(first), {meaning for meaning, house in place.items() if (house == second) == (kind == 'found_at')})
    changed = True
    while changed:
        before = {phrase: len(options) for phrase, options in fits.items()}
        for (number, line), (kind, first, second) in readings.items():
            if kind in HOUSE_KINDS:
                continue
            place, rule = puzzles[number]['place'], RULES[kind]
            first, second = _key(first), _key(second)
            a = fits.get(first, set(place)) & set(place)
            b = fits.get(second, set(place)) & set(place)
            narrow(first, {x for x in a if any(x != y and rule(place[x], place[y]) for y in b)})
            narrow(second, {y for y in b if any(x != y and rule(place[x], place[y]) for x in a)})
        changed = before != {phrase: len(options) for phrase, options in fits.items()}
    require(set(fits) == known and all(len(options) == 1 for options in fits.values()),
            'A phrase without exactly one meaning: %s' % sorted(p for p, o in fits.items() if len(o) != 1)[:3])
    meaning = {phrase: next(iter(options)) for phrase, options in fits.items()}
    phrases = {}
    for phrase, (column, value) in sorted(meaning.items()):
        require(value not in phrases.setdefault(column, {}), 'Two phrases for one value: %s %s' % (column, value))
        require(len(inside_forms.get(phrase, ())) == 1, 'A phrase never seen, or seen two ways, inside a sentence: ' + phrase)
        phrases[column][value] = next(iter(inside_forms[phrase]))
    columns = {column: {'intro': intro, 'values': {}} for column, intro in sorted(intro_of.items())}
    for (column, houses), values in sorted(value_sets.items()):
        columns[column]['values'][str(houses)] = values
    for column, entry in columns.items():   # a value the pool never speaks of could not be written into a clue
        for houses, values in entry['values'].items():
            require(set(values) <= set(phrases.get(column, {})), 'A value without a phrase: %s' % column)
    language = {'columns': columns, 'phrases': phrases}
    # 4. the two proofs on the pool itself: exact text, and the reference as the one solution
    clue_count = 0
    for puzzle in puzzles:
        parsed = parse(puzzle['text'], language)
        require(write(parsed, language) == puzzle['text'], 'A pool puzzle is not written back exactly: ' + puzzle['id'])
        solutions, _ = solve(parsed['houses'], parsed['columns'], parsed['clues'], limit=2)
        require(len(solutions) == 1 and solutions[0] == puzzle['place'],
                'A pool puzzle is not solved to its reference alone: ' + puzzle['id'])
        clue_count += len(parsed['clues'])
    language['checks'] = {'puzzles': len(puzzles), 'clues': clue_count, 'phrases': len(meaning), 'columns': len(columns),
                          'written_back_exactly': len(puzzles), 'solved_to_the_reference_alone': len(puzzles)}
    return language


def _key(phrase):
    return phrase[:1].lower() + phrase[1:]


def _dictionary(language):
    """{phrase inside a sentence: (column, value)} and {phrase opening a sentence: (column, value)}."""
    inside = {phrase: (column, value) for column, table in language['phrases'].items() for value, phrase in table.items()}
    require(len(inside) == sum(len(table) for table in language['phrases'].values()), 'One meaning per phrase')
    opening = {opening_form(phrase): meaning for phrase, meaning in inside.items()}
    require(len(opening) == len(inside), 'One meaning per opening phrase')
    return inside, opening


def parse(text, language):
    """{'houses', 'columns': [(column, values as listed)], 'clues': [(kind, a, b)]} of a puzzle text. Every clue
    sentence must have exactly one reading in the language, with the phrases spelled as their place asks."""
    houses, attributes, sentences = split_text(text)
    by_intro = {entry['intro']: column for column, entry in language['columns'].items()}
    columns = []
    for intro, values in attributes:
        require(intro in by_intro, 'An attribute the language does not have: ' + intro)
        column = by_intro[intro]
        require(sorted(values) == language['columns'][column]['values'].get(str(houses)), 'Not the value set of %s' % column)
        columns.append((column, list(values)))
    present = {(column, value) for column, values in columns for value in values}
    inside, opening = _dictionary(language)
    clues = []
    for sentence in sentences:
        found = []
        house = _house_reading(sentence)
        if house and opening.get(house[1]) in present:
            found.append((house[0], opening[house[1]], house[2]))
        for kind, (before, _, _) in PAIR_KINDS.items():
            first_table = opening if before == '' else inside
            for first, second in _splits(sentence, kind):
                if first_table.get(first) in present and inside.get(second) in present:
                    found.append((kind, first_table[first], inside[second]))
        require(len(found) == 1, 'A clue sentence with %d readings: %s' % (len(found), sentence))
        kind, a, b = found[0]
        require(kind in HOUSE_KINDS and b < houses or kind in PAIR_KINDS and a != b, 'A clue outside the grid: ' + sentence)
        clues.append(found[0])
    return {'houses': houses, 'columns': columns, 'clues': clues}


def sentence_of(clue, language):
    kind, a, b = clue
    first = language['phrases'][a[0]][a[1]]
    if kind in HOUSE_KINDS:
        return opening_form(first) + HOUSE_KINDS[kind] % ORDINALS[b]
    before, between, after = PAIR_KINDS[kind]
    return before + (opening_form(first) if before == '' else first) + between + language['phrases'][b[0]][b[1]] + after


def write(puzzle, language):
    """The text of a parsed or made puzzle, in the pool's layout."""
    lines = [OPENING % (puzzle['houses'], puzzle['houses'])]
    for column, values in puzzle['columns']:
        lines.append(' - %s: %s' % (language['columns'][column]['intro'], ', '.join('`%s`' % value for value in values)))
    lines += ['', CLUE_HEAD]
    lines += ['%d. %s' % (number, sentence_of(clue, language)) for number, clue in enumerate(puzzle['clues'], 1)]
    return '\n'.join(lines) + '\n'


# ---- solving ---------------------------------------------------------------------------------------------------------
_SUPPORT = {}


def _support(kind, houses):
    """For a pair kind: (houses the first value can take, by the mask of the second's; and the other way round)."""
    key = (kind, houses)
    if key not in _SUPPORT:
        rule, size = RULES[kind], 1 << houses
        first, second = [0] * size, [0] * size
        for mask in range(size):
            for a in range(houses):
                if any(mask >> b & 1 and rule(a, b) for b in range(houses)):
                    first[mask] |= 1 << a
                if any(mask >> b & 1 and rule(b, a) for b in range(houses)):
                    second[mask] |= 1 << a
        _SUPPORT[key] = (first, second)
    return _SUPPORT[key]


def _cells(columns):
    """{(column, value): cell number}; a column's values take consecutive cells in their listed order."""
    cells = {}
    for column, values in columns:
        for value in values:
            require((column, value) not in cells, 'A value listed twice')
            cells[(column, value)] = len(cells)
    return cells


def solve(houses, columns, clues, limit=2):
    """At most ``limit`` solutions of a grid, each as {(column, value): house}, and the number of search nodes.
    Every column's values take distinct houses (as many values as houses). Bit masks of the houses a value can
    still take, the clues and the columns applied until nothing changes, then a search on the value with the
    fewest houses left."""
    cells = _cells(columns)
    require(all(len(values) == houses for _, values in columns) and 2 <= houses <= len(ORDINALS), 'A square grid')
    full = (1 << houses) - 1
    start, pairs = [full] * len(cells), []
    for kind, a, b in clues:
        if kind == 'found_at':
            start[cells[a]] &= 1 << b
        elif kind == 'not_at':
            start[cells[a]] &= full ^ (1 << b)
        elif cells[a] == cells[b]:
            if kind != 'same':
                return [], 0                       # a value in two different houses
        else:
            pairs.append((cells[a], cells[b]) + _support(kind, houses))
    watch = [[] for _ in start]
    for index, pair in enumerate(pairs):
        watch[pair[0]].append(index)
        watch[pair[1]].append(index)
    spans = [range(base, base + houses) for base in range(0, len(start), houses)]
    solutions, nodes = [], [0]

    def settle(domain, queue):
        while True:
            while queue:
                cell = queue.pop()
                for index in watch[cell]:
                    x, y, of_first, of_second = pairs[index]
                    if cell == y:
                        new = domain[x] & of_first[domain[y]]
                        if new != domain[x]:
                            if not new:
                                return False
                            domain[x] = new
                            queue.append(x)
                    else:
                        new = domain[y] & of_second[domain[x]]
                        if new != domain[y]:
                            if not new:
                                return False
                            domain[y] = new
                            queue.append(y)
            for span in spans:
                for cell in span:
                    mask = domain[cell]
                    if mask & (mask - 1) == 0:              # settled: nobody else of the column lives there
                        for other in span:
                            if other != cell and domain[other] & mask:
                                domain[other] &= ~mask
                                if not domain[other]:
                                    return False
                                queue.append(other)
                for house in range(houses):                  # a house only one value of the column can still take
                    bit, holder, count = 1 << house, -1, 0
                    for cell in span:
                        if domain[cell] & bit:
                            holder, count = cell, count + 1
                    if count == 0:
                        return False
                    if count == 1 and domain[holder] != bit:
                        domain[holder] = bit
                        queue.append(holder)
            if not queue:
                return True

    def search(domain, queue):
        nodes[0] += 1
        if not settle(domain, queue):
            return
        best, fewest = -1, houses + 1
        for cell, mask in enumerate(domain):
            count = bin(mask).count('1')
            if 1 < count < fewest:
                best, fewest = cell, count
        if best < 0:
            solutions.append(tuple(mask.bit_length() - 1 for mask in domain))
            return
        mask = domain[best]
        while mask and len(solutions) < limit:
            bit = mask & -mask
            mask ^= bit
            branch = list(domain)
            branch[best] = bit
            search(branch, [best])

    if all(start):
        search(start, list(range(len(start))))
    names = sorted(cells, key=cells.get)
    return [dict(zip(names, solution)) for solution in solutions], nodes[0]


def solve_plainly(houses, columns, clues, limit=2):
    """The same question answered another way, to check ``solve`` against (no masks, no tables, nothing shared but
    ``RULES``): the columns are filled one after the other with every arrangement of their values that the clues
    inside the column allow, most-constrained column first, and every clue between two filled columns is tested by
    its rule on the two houses. Slower; used to certify made puzzles and in tests."""
    require(all(len(values) == houses for _, values in columns), 'A square grid')
    names = [column for column, _ in columns]
    require(len(set(names)) == len(names), 'Distinct columns')
    inside = {name: [] for name in names}       # clues about one column alone
    across = []                                  # clues that join two columns
    for kind, a, b in clues:
        if kind in HOUSE_KINDS or a[0] == b[0]:
            inside[a[0]].append((kind, a, b))
        else:
            across.append((kind, a, b))

    def holds(kind, a, b, place):
        if kind == 'found_at':
            return place[a] == b
        if kind == 'not_at':
            return place[a] != b
        return RULES[kind](place[a], place[b]) if a != b else kind == 'same'

    options = {}
    for column, values in columns:
        options[column] = []
        for order in itertools.permutations(range(houses)):
            place = {(column, value): house for value, house in zip(values, order)}
            if all(holds(kind, a, b, place) for kind, a, b in inside[column]):
                options[column].append(place)
    order, left = [], set(names)
    while left:   # next: the column tied to the filled ones by most clues, then the one with the fewest arrangements
        tied = {name: sum(1 for _, a, b in across if {a[0], b[0]} & set(order) and name in (a[0], b[0])) for name in left}
        chosen = min(sorted(left), key=lambda name: (-tied[name], len(options[name])))
        order.append(chosen)
        left.remove(chosen)
    due = []
    for depth, name in enumerate(order):
        filled = set(order[:depth + 1])
        due.append([clue for clue in across if name in (clue[1][0], clue[2][0]) and {clue[1][0], clue[2][0]} <= filled])
    solutions = []

    def fill(depth, place):
        if len(solutions) >= limit:
            return
        if depth == len(order):
            solutions.append(dict(place))
            return
        for option in options[order[depth]]:
            place.update(option)
            if all(RULES[kind](place[a], place[b]) for kind, a, b in due[depth]):
                fill(depth + 1, place)
            if len(solutions) >= limit:
                return
        for key in options[order[depth]][0] if options[order[depth]] else ():
            place.pop(key, None)

    fill(0, {})
    return solutions


# ---- making ----------------------------------------------------------------------------------------------------------
def true_clues(houses, columns, place, rng):
    """Every true clue of a grid, one sentence per fact. The starting set is a reconstruction that fits the pool
    (in 465 of 465 pool clues about neighbours or houses in between the value on the left is named first; no pool
    puzzle says both 'directly left' and 'next to' of one pair): where a value is and where it is not;
    two values of different columns in one house ('same', either one first); for a value on the left and one
    on the right, 'somewhere to the left' or the same fact said as 'somewhere to the right' (one of the two); for
    neighbours, 'directly left' or 'next to' (one of the two); one house between; two houses between."""
    cells = sorted(_cells(columns), key=_cells(columns).get)
    clues = []
    for cell in cells:
        for house in range(houses):
            clues.append(('found_at' if place[cell] == house else 'not_at', cell, house))
    for a, b in itertools.combinations(cells, 2):
        distance = place[b] - place[a]
        if distance == 0:
            if a[0] != b[0]:
                clues.append(('same', a, b) if rng.random() < 0.5 else ('same', b, a))
            continue
        left, right = (a, b) if distance > 0 else (b, a)
        clues.append(('left_of', left, right) if rng.random() < 0.5 else ('right_of', right, left))
        if abs(distance) == 1:
            clues.append(('direct_left', left, right) if rng.random() < 0.5 else ('next_to', left, right))
        elif abs(distance) == 2:
            clues.append(('one_between', left, right))
        elif abs(distance) == 3:
            clues.append(('two_between', left, right))
    return clues


def thin(houses, columns, ordered):
    """The clues that stay when ``ordered`` is gone through once from the front and a clue is taken away whenever
    the grid stays the only solution without it (the paper's loop, run to its end). The solver is asked far fewer
    times than there are clues: taking clues away never makes a solution disappear, so the longest run of clues
    that can go together is found by halving, and the clue after it has to stay."""
    def unique(position):
        return len(solve(houses, columns, kept + ordered[position:], limit=2)[0]) == 1

    kept, start, total = [], 0, len(ordered)
    require(unique(0), 'The full clue set does not pin the grid')
    while start < total:
        low, high = start, total + 1          # unique(low) holds; high is beyond the last position that might
        while high - low > 1:
            middle = (low + high) // 2
            if unique(middle):
                low = middle
            else:
                high = middle
        if low == total:
            break
        kept.append(ordered[low])
        start = low + 1
    return kept


def make(rng, houses, column_names, language, weights=None):
    """One made puzzle: {'houses', 'columns', 'clues', 'place'}. ``column_names``: the columns in their order (the
    pool always starts with Name); ``weights``: {kind: weight}, a heavier kind is tried for removal earlier
    (``REMOVAL_WEIGHTS`` when not given)."""
    weights = REMOVAL_WEIGHTS if weights is None else weights
    columns = []
    for name in column_names:
        values = list(language['columns'][name]['values'][str(houses)])
        rng.shuffle(values)
        columns.append((name, values))
    place = {}
    for name, values in columns:
        order = list(range(houses))
        rng.shuffle(order)
        place.update({(name, value): house for value, house in zip(values, order)})
    clues = true_clues(houses, columns, place, rng)
    keyed = [(rng.expovariate(1.0) / weights[clue[0]], index) for index, clue in enumerate(clues)]
    kept = thin(houses, columns, [clues[index] for _, index in sorted(keyed)])
    rng.shuffle(kept)
    return {'houses': houses, 'columns': columns, 'clues': kept, 'place': place}


def row_of(puzzle, language, item_id):
    """A made puzzle as a source row of the benchmark's shape (what ``zebralogic.normalize`` reads)."""
    size = '%d*%d' % (puzzle['houses'], len(puzzle['columns']))
    by_house = {house: {column: value for (column, value), at in puzzle['place'].items() if at == house}
                for house in range(puzzle['houses'])}
    names = [column for column, _ in puzzle['columns']]
    return {'id': item_id, 'bench': 'zebralogic', 'task': size, 'size': size, 'puzzle': write(puzzle, language),
            'solution': {'header': ['House'] + names,
                         'rows': [[str(house + 1)] + [by_house[house][name] for name in names] for house in range(puzzle['houses'])]}}


def certify(row, language):
    """The certificate of a made row, from its TEXT and its stored grid alone, or ValueError: the text is read like
    a pool puzzle and written back exactly; both solvers find exactly one solution and it is the stored grid; no
    clue can be left out. Returns the counts a report needs."""
    parsed = parse(row['puzzle'], language)
    require(write(parsed, language) == row['puzzle'], 'The text is not written back exactly')
    header, table = row['solution']['header'], row['solution']['rows']
    require(header == ['House'] + [column for column, _ in parsed['columns']] and len(table) == parsed['houses']
            and [cells[0] for cells in table] == [str(house + 1) for house in range(parsed['houses'])], 'The stored grid')
    stored = {(column, cells[index]): house for house, cells in enumerate(table) for index, column in enumerate(header[1:], 1)}
    solutions, nodes = solve(parsed['houses'], parsed['columns'], parsed['clues'], limit=2)
    require(len(solutions) == 1 and solutions[0] == stored, 'Not exactly the stored grid (first solver)')
    plain = solve_plainly(parsed['houses'], parsed['columns'], parsed['clues'], limit=2)
    require(len(plain) == 1 and plain[0] == stored, 'Not exactly the stored grid (second solver)')
    for index in range(len(parsed['clues'])):
        rest = parsed['clues'][:index] + parsed['clues'][index + 1:]
        require(len(solve(parsed['houses'], parsed['columns'], rest, limit=2)[0]) == 2, 'A clue that can be left out')
    return {'houses': parsed['houses'], 'columns': len(parsed['columns']), 'clues': len(parsed['clues']),
            'kinds': {kind: sum(1 for clue in parsed['clues'] if clue[0] == kind) for kind in KINDS},
            'search_nodes': nodes, 'solutions': 1, 'second_solver_agrees': True, 'no_clue_can_be_left_out': True}


# ---- what a set of puzzles looks like (for the comparison of made with real ones) ---------------------------------------
def profile(parsed_puzzles):
    """Counts of a list of parsed puzzles, by size ('5*3'): puzzles, clues per puzzle, clues by kind, pair clues inside
    one column, and the first solver's search nodes."""
    out = {}
    for puzzle in parsed_puzzles:
        size = '%d*%d' % (puzzle['houses'], len(puzzle['columns']))
        entry = out.setdefault(size, {'puzzles': 0, 'clues': [], 'kinds': {kind: 0 for kind in KINDS},
                                      'pairs_inside_one_column': 0, 'pairs': 0, 'search_nodes': []})
        entry['puzzles'] += 1
        entry['clues'].append(len(puzzle['clues']))
        for kind, a, b in puzzle['clues']:
            entry['kinds'][kind] += 1
            if kind in PAIR_KINDS:
                entry['pairs'] += 1
                entry['pairs_inside_one_column'] += a[0] == b[0]
        entry['search_nodes'].append(solve(puzzle['houses'], puzzle['columns'], puzzle['clues'], limit=2)[1])
    return out


def _mean(values):
    return sum(values) / len(values)


def _kind_shares(entries):
    total = {kind: sum(entry['kinds'][kind] for entry in entries) for kind in KINDS}
    count = sum(total.values())
    return {kind: total[kind] / count for kind in KINDS}


def _features(puzzle):
    kinds = {kind: 0 for kind in KINDS}
    for clue in puzzle['clues']:
        kinds[clue[0]] += 1
    return {'clues': len(puzzle['clues']), 'kinds': kinds,
            'nodes': solve(puzzle['houses'], puzzle['columns'], puzzle['clues'], limit=2)[1]}


def compare(real, made, rng, draws=2000):
    """Are the made puzzles like the real ones of the same size, as far as fixed code can see? For every size and
    three measures (the mean number of clues, the shares of the nine clue kinds, the share of puzzles the first
    solver settles without search) the real puzzles of that size are compared with random groups of made puzzles
    OF THE SAME NUMBER: 'beyond' is the share of such groups that lie further from the whole made set than the real
    group does (small = the real puzzles look unlike made ones). ``real`` and ``made``: lists of parsed puzzles.
    Returns {'sizes': {size: {...}}, 'comparisons', 'beyond_below_0.05', 'beyond_below_0.001'}."""
    by_size = {}
    for label, puzzles in (('real', real), ('made', made)):
        for puzzle in puzzles:
            size = '%d*%d' % (puzzle['houses'], len(puzzle['columns']))
            by_size.setdefault(size, {'real': [], 'made': []})[label].append(_features(puzzle))

    def measures(group, whole_mean, whole_shares, whole_easy):
        shares = _kind_shares(group)
        return {'clues': abs(_mean([entry['clues'] for entry in group]) - whole_mean),
                'kinds': 0.5 * sum(abs(shares[kind] - whole_shares[kind]) for kind in KINDS),
                'no_search': abs(_mean([entry['nodes'] == 1 for entry in group]) - whole_easy)}

    out, low, very_low, comparisons = {}, 0, 0, 0
    for size in sorted(by_size):
        real_group, made_group = by_size[size]['real'], by_size[size]['made']
        if not real_group or len(made_group) < 2 * len(real_group):
            out[size] = {'real': len(real_group), 'made': len(made_group), 'compared': False}
            continue
        whole = (_mean([entry['clues'] for entry in made_group]), _kind_shares(made_group),
                 _mean([entry['nodes'] == 1 for entry in made_group]))
        seen = measures(real_group, *whole)
        beyond = {name: 0 for name in seen}
        for _ in range(draws):
            drawn = measures(rng.sample(made_group, len(real_group)), *whole)
            for name in seen:
                beyond[name] += drawn[name] >= seen[name]
        entry = {'real': len(real_group), 'made': len(made_group), 'compared': True,
                 'clues_mean': {'real': round(_mean([e['clues'] for e in real_group]), 2), 'made': round(whole[0], 2)},
                 'kind_shares_distance': round(seen['kinds'], 4),
                 'no_search_share': {'real': round(_mean([e['nodes'] == 1 for e in real_group]), 3), 'made': round(whole[2], 3)},
                 'beyond': {name: round(beyond[name] / draws, 4) for name in seen}}
        for name in seen:
            comparisons += 1
            low += entry['beyond'][name] < 0.05
            very_low += entry['beyond'][name] < 0.001
        out[size] = entry
    return {'sizes': out, 'comparisons': comparisons, 'beyond_below_0.05': low, 'beyond_below_0.001': very_low,
            'draws': draws}
