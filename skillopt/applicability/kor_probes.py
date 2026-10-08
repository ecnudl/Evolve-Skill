"""Fresh KOR probe tasks for label-free interference measurement (zero model calls).

Each probe reuses a registered public KOR rule text verbatim and the answer-format
instructions of a public panel question of that rule, with new random inputs; a
probe never repeats a panel question (a cipher probe shares no plaintext or
ciphertext with a panel task of its rule, in either direction). Its reference
answer is computed independently of the verifier (direct formulas, a brute-force
24-game search, constructed puzzle solutions, separately written encryptions; a
decryption probe's reference is its random plaintext) and must pass the verifier,
while a mutated reference must fail. Probes carry no official scorer identity: only the
label-free verifier scores them.
"""
from __future__ import annotations

import itertools
import random
import re
from fractions import Fraction

from . import kor

VERSION = "kor-probes-v5"


class ProbeError(ValueError):
    """A generated probe failed its own qualification: a generator defect, never skipped."""


def _number(value):
    value = Fraction(value)
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _complex(real, imaginary):
    if imaginary == 0:
        return str(real)
    size = "" if abs(imaginary) == 1 else str(abs(imaginary))
    if real == 0:
        return ("-" if imaginary < 0 else "") + size + "i"
    return f"{real}{'+' if imaginary > 0 else '-'}{size}i"


def _multiply(x, y):
    return x[0] * y[0] - x[1] * y[1], x[0] * y[1] + x[1] * y[0]


# ------------------------------------------------------------------ operations
def _multiple(rng):
    def rule(a, b):
        if b != 0 and a % b == 0:
            return a // b + 2
        if a != 0 and b % a == 0:
            return b // a + 2
        return 24
    b = rng.randint(2, 9)
    a = b * rng.randint(2, 9) if rng.random() < 0.6 else rng.randint(2, 60)
    if rng.random() < 0.5:
        return f"{a}※{b}", Fraction(rule(a, b))
    c = rng.randint(2, 30)
    return f"{a}※{b}※{c}", Fraction(rule(rule(a, b), c))


def _circle(rng):
    def rule(a, b):
        return (a + 3 * b) * (a + b)
    if rng.random() < 0.6:
        a, b = rng.randint(1, 9), rng.randint(1, 9)
        return f"{a}○{b}", Fraction(rule(a, b))
    a, b, c = rng.randint(1, 4), rng.randint(1, 4), rng.randint(1, 4)
    return f"{a}○{b}○{c}", Fraction(rule(rule(a, b), c))


def _angle(rng):
    a, b, c, d = (rng.randint(1, 9) for _ in range(4))
    return f"⟨{a},{b},{c},{d}⟩", Fraction(2 * a * b + c - d)


def _venus_mars(rng):
    a = rng.randint(1, 9)
    b = a + 2 * rng.randint(0, 4)  # even sums keep (a+b)/2 an integer
    c = rng.randint(1, 9)
    if rng.random() < 0.5:
        return f"({a}♀{b})♂{c}", Fraction(4 * (a + b) // 2 + c)
    return f"{c}♂({a}♀{b})", Fraction(4 * c + (a + b) // 2)


def _sqrt(rng):
    if rng.random() < 0.5:
        root, inner_root, c = rng.randint(1, 9), rng.randint(1, 9), rng.randint(1, 5)
        return f"{root * root}②({inner_root * inner_root}①{c})", Fraction(root * (inner_root + c * c))
    c = rng.randint(1, 4)
    t = rng.randint(c + 1, c + 3)
    s = t * t - c * c  # √(s²) + c² = t², a perfect square
    a = rng.randint(1, 9)
    return f"({s * s}①{c})②{a}", Fraction(t * a)


def _log(rng):
    base = rng.choice((2, 3, 5, 6, 7, 10))
    m, n = rng.sample(range(1, 7), 2)
    return f"{base ** m}￠{base ** n}", Fraction(m, n) + Fraction(n, m)


def _pairs(rng, rule):
    a, b, c, d = (rng.randint(1, 9) for _ in range(4))
    left, right = rule(a, b), rule(c, d)
    symbol, value = rng.choice((("+", (left[0] + right[0], left[1] + right[1])),
                                ("−", (left[0] - right[0], left[1] - right[1])),
                                ("×", _multiply(left, right))))
    return (a, b, c, d), symbol, value


def _complex_pair(rng):
    (a, b, c, d), symbol, value = _pairs(rng, lambda x, y: (x, y))
    return f"({a}⊕{b}){symbol}({c}⊕{d})", value


def _complex_square(rng):
    (a, b, c, d), symbol, value = _pairs(rng, lambda x, y: (x * x - y * y, 2 * x * y))
    return f"({a}◎{b}){symbol}({c}◎{d})", value


def _matrix(rng, low_a, high_a, low_b, high_b, cell):
    a = [[rng.randint(low_a, high_a) for _ in range(2)] for _ in range(2)]
    b = [[rng.randint(low_b, high_b) for _ in range(2)] for _ in range(2)]

    def block(name, m):
        return (f"{name}=\n\\[\n\\begin{{pmatrix}}\n  {m[0][0]} & {m[0][1]} \\\\\n  {m[1][0]} & {m[1][1]}\n"
                "\\end{pmatrix}\n\\]\n")
    return block("A", a) + block("B", b), [[cell(x, y) for x, y in zip(ra, rb)] for ra, rb in zip(a, b)]


def _matrix_text(m):
    return "(" + ",".join("(" + ",".join(map(str, row)) + ")" for row in m) + ")"


# --------------------------------------------------------------------- puzzles
_OPERATORS = {"+": lambda x, y: x + y, "-": lambda x, y: x - y, "*": lambda x, y: x * y,
              "/": lambda x, y: x / y if y else None}
_SHAPES = ("(({a}{o}{b}){p}{c}){q}{d}", "({a}{o}({b}{p}{c})){q}{d}", "({a}{o}{b}){p}({c}{q}{d})",
           "{a}{o}(({b}{p}{c}){q}{d})", "{a}{o}({b}{p}({c}{q}{d}))")


def _evaluate_shape(shape, numbers, operators):
    a, b, c, d = (Fraction(n) for n in numbers)
    o, p, q = (_OPERATORS[s] for s in operators)

    def apply(function, x, y):
        return None if x is None or y is None else function(x, y)
    trees = (lambda: apply(q, apply(p, apply(o, a, b), c), d), lambda: apply(q, apply(o, a, apply(p, b, c)), d),
             lambda: apply(p, apply(o, a, b), apply(q, c, d)), lambda: apply(o, a, apply(q, apply(p, b, c), d)),
             lambda: apply(o, a, apply(p, b, apply(q, c, d))))
    return trees[_SHAPES.index(shape)]()


def _twenty_four(rng):
    while True:
        numbers = [rng.randint(1, 13) for _ in range(4)]
        for order in itertools.permutations(numbers):
            for operators in itertools.product("+-*/", repeat=3):
                for shape in _SHAPES:
                    if _evaluate_shape(shape, order, operators) == 24:
                        expression = shape.format(a=order[0], b=order[1], c=order[2], d=order[3],
                                                  o=operators[0], p=operators[1], q=operators[2])
                        for other in "+-*/":  # change the first operator so the value is no longer 24
                            changed = (other,) + operators[1:]
                            if other != operators[0] and _evaluate_shape(shape, order, changed) not in (24, None):
                                mutated = shape.format(a=order[0], b=order[1], c=order[2], d=order[3],
                                                       o=other, p=operators[1], q=operators[2])
                                return numbers, expression, mutated


def _sudoku(rng):
    grid = [[(i * 3 + i // 3 + j) % 9 + 1 for j in range(9)] for i in range(9)]
    digits = rng.sample(range(1, 10), 9)
    grid = [[digits[v - 1] for v in row] for row in grid]
    bands = rng.sample(range(3), 3)
    rows = [3 * band + r for band in bands for r in rng.sample(range(3), 3)]
    stacks = rng.sample(range(3), 3)
    columns = [3 * stack + c for stack in stacks for c in rng.sample(range(3), 3)]
    grid = [[grid[r][c] for c in columns] for r in rows]
    shown = set(rng.sample(range(81), rng.randint(30, 36)))
    question = "\n".join(" ".join(str(grid[i][j]) if 9 * i + j in shown else "X" for j in range(9)) for i in range(9))
    hidden = [k for k in range(81) if k not in shown]
    return question, grid, hidden


def _latin(rng, n):
    labels = rng.sample(range(1, n + 1), n)
    rows, columns = rng.sample(range(n), n), rng.sample(range(n), n)
    return [[labels[(rows[i] + columns[j]) % n] for j in range(n)] for i in range(n)]


def _visible(line):
    count, tallest = 0, 0
    for height in line:
        if height > tallest:
            count, tallest = count + 1, height
    return count


def _skyscrapers(rng):
    n = rng.choice((4, 5))
    grid = _latin(rng, n)
    columns = [[grid[i][j] for i in range(n)] for j in range(n)]
    top, bottom = [_visible(c) for c in columns], [_visible(c[::-1]) for c in columns]
    lines = [f"{_visible(row)}\t" + "\t".join("X" * n) + f"\t{_visible(row[::-1])}" for row in grid]
    question = ("Grid Layout:\n\t" + "\t".join(map(str, top)) + "\t\n" + "\n".join(lines) + "\n\t"
                + "\t".join(map(str, bottom)))
    return question, grid


def _hidato(rng):
    n = 9  # the public rule fixes the numbers 1 to 81
    path = [(i, j if i % 2 == 0 else n - 1 - j) for i in range(n) for j in range(n)]
    if rng.random() < 0.5:
        path = [(j, i) for i, j in path]
    flip_rows, flip_columns = rng.random() < 0.5, rng.random() < 0.5
    path = [(n - 1 - i if flip_rows else i, n - 1 - j if flip_columns else j) for i, j in path]
    if rng.random() < 0.5:
        path = path[::-1]
    grid = [[0] * n for _ in range(n)]
    for number, (i, j) in enumerate(path, 1):
        grid[i][j] = number
    shown = {1, n * n} | set(rng.sample(range(2, n * n), 20))
    question = "\n".join("  ".join(str(v) if v in shown else "X" for v in row) for row in grid)
    return question, grid, shown


def _rows(grid):
    return ",".join(" ".join(map(str, row)) for row in grid)


# ------------------------------------------------------------------- assembly
_FORMAT = {"operation:multiple": (_multiple, _number), "operation:circle": (_circle, _number),
           "operation:angle": (_angle, _number), "operation:venus_mars": (_venus_mars, _number),
           "operation:sqrt": (_sqrt, _number), "operation:log": (_log, _number),
           "operation:complex_pair": (_complex_pair, lambda v: _complex(*v)),
           "operation:complex_square": (_complex_square, lambda v: _complex(*v))}


def _operation_instructions(question):
    """The answer-format lines after the 'Compute ...' line of a public forward question."""
    lines = question.split("\n")
    index = next((k for k, line in enumerate(lines) if line.startswith("Compute ")), None)
    if index is None or index + 1 >= len(lines):
        return None
    return "\n".join(lines[index + 1:])


# --------------------------------------------------------------------- ciphers
# Encryptions written apart from the verifier's (only the public tables are shared). A decryption
# probe's reference is the random plaintext itself. Only instances whose answer every reading of
# the rule agrees on are posed, so the verifier can pass the reference.
_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _solitaire_stream(count):
    deck, values = list(kor._DECK), []
    while len(values) < count:
        i = deck.index(53)                     # joker A one down; from the bottom it becomes the second card
        deck = [deck[0], 53, *deck[1:53]] if i == 53 else deck[:i] + [deck[i + 1], 53] + deck[i + 2:]
        i = deck.index(54)                     # joker B two down; second-last -> second, last -> third
        if i == 52:
            deck = [deck[0], 54, *deck[1:52], deck[53]]
        elif i == 53:
            deck = [deck[0], deck[1], 54, *deck[2:53]]
        else:
            deck = deck[:i] + deck[i + 1:i + 3] + [54] + deck[i + 3:]
        a, b = sorted((deck.index(53), deck.index(54)))
        deck = deck[b + 1:] + deck[a:b + 1] + deck[:a]
        cut = 53 if deck[53] > 52 else deck[53]
        deck = deck[cut:53] + deck[:cut] + [deck[53]]
        value = deck[53 if deck[0] > 52 else deck[0]]
        if value <= 52:
            values.append(value)
    return values


def _rails(plain):
    """The worked example's fill: column 1 down, then '#'-led columns of four alternately up and down."""
    rows = [[] for _ in range(5)]
    for row, char in zip(range(5), plain[:5]):
        rows[row].append(char)
    for column, start in enumerate(range(5, len(plain), 4)):
        order = (4, 3, 2, 1, 0) if column % 2 == 0 else (0, 1, 2, 3, 4)
        for row, char in zip(order, "#" + plain[start:start + 4]):
            rows[row].append(char)
    return "".join("".join(row) + "*" for row in rows)


def _sbox_byte(byte, key):
    byte ^= key
    byte = kor._SBOX[byte // 16] * 16 + kor._SBOX[byte % 16]
    return ((byte * 2) % 256 + byte // 128) ^ key


def _disk_encrypt(plain, period, increment, left):
    inner, out = kor._INNER, ""
    for i, char in enumerate(plain):
        out += inner[kor._OUTER.find(char)]
        if (i + 1) % period == 0:
            shift = increment % 26 if left else (26 - increment % 26) % 26
            inner = inner[shift:] + inner[:shift]
    return out


def _encrypt(handler, plain, fields):
    """The ciphertext of an uppercase plaintext under the rule's worked example (or only) reading."""
    if handler == "cipher:affine":
        return "".join(kor._AFFINE[(3 * kor._AFFINE.find(c) + 5) % 26] for c in plain)
    if handler == "cipher:solitaire":
        letters = kor._SOLITAIRE
        return "".join(letters[(letters.find(c) + y) % 26] for c, y in zip(plain, _solitaire_stream(len(plain))))
    if handler == "cipher:grid_shift":
        grid = kor._GRID
        where = {c: (r, k) for r, line in enumerate(grid) for k, c in enumerate(line)}
        return "".join(c if c == "J" else grid[(where[c][0] + 1) % 5][(where[c][1] + 1) % 5] for c in plain)
    if handler == "cipher:porta":
        key = fields["Key"]
        return "".join(kor._PORTA[(_UPPER.find(key[i % len(key)])) // 2][_UPPER.find(c)] for i, c in enumerate(plain))
    if handler == "cipher:disks":
        return _disk_encrypt(plain, fields["period"], fields["increment"], True)
    if handler == "cipher:morse_pairs":
        code = "/".join(kor._MORSE[c] for c in plain)
        pairs = [code[i:i + 2] for i in range(0, len(code), 2)]
        return "".join(kor._PAIRS[p] if len(p) == 2 else p for p in pairs)
    if handler == "cipher:rail_columns":
        return _rails(plain)
    if handler == "cipher:sbox_blocks":
        data = plain.encode("ascii")
        data += b"\0" * (-len(data) % 8)
        return "".join(f"{_sbox_byte(b, kor._BLOCK_KEY[i % 8]):02X}" for i, b in enumerate(data))
    if handler == "cipher:ascii_scale":
        return ",".join(str(12 * ord(c)) for c in plain)
    raise ProbeError("no cipher generator for " + handler)


def _posable(handler, plain, cipher, fields, encrypt):
    """Whether every admissible reading of the rule gives this instance's answer."""
    if handler == "cipher:disks":  # both rotation directions agree; each ciphertext J has two inverses
        right = _disk_encrypt(plain, fields["period"], fields["increment"], False)
        return cipher == right and (encrypt or "J" not in cipher)
    if handler == "cipher:rail_columns":  # beyond one column its prose and worked example place '#' apart
        return not encrypt or len(plain) <= 5
    if handler == "cipher:sbox_blocks":  # one block (key alignment unstated); only A-E must be capitals
        return len(plain) <= 8 and not (encrypt and "F" in cipher)
    return True


def _draw(handler, rng):
    encrypt = rng.random() < 0.5
    plain = "".join(rng.choice(_UPPER) for _ in range(rng.randint(1, 11)))
    return encrypt, plain, _cipher_fields(handler, rng)


def _cipher_fields(handler, rng):
    if handler == "cipher:porta":
        return {"Key": "".join(rng.choice(_UPPER) for _ in range(rng.randint(4, 10)))}
    if handler == "cipher:disks":
        return {"period": rng.randint(1, 12), "increment": rng.randint(1, 12)}
    return {}


def _pose(template, text, fields):
    """A public panel question of the same direction with its quoted input and fields replaced."""
    question = re.sub(r'"[^"]*"', lambda _: f'"{text}"', template, count=1)
    for name, value in fields.items():
        question, count = re.subn(rf"\b{name}: [A-Z0-9]+", lambda _: f"{name}: {value}", question)
        if count != 1:
            raise ProbeError(f"public question lacks its {name} field")
    return question


def _cipher_probe(handler, rng, templates):
    for _ in range(200):
        encrypt, plain, fields = _draw(handler, rng)
        cipher = _encrypt(handler, plain, fields)
        if not _posable(handler, plain, cipher, fields, encrypt):
            continue
        text, answer = (plain, cipher) if encrypt else (cipher, plain)
        positions = [i for i, c in enumerate(answer) if c.isalnum()]
        if not positions:  # e.g. the Morse rule encrypts E or T to a lone symbol
            continue
        i = rng.choice(positions)
        pool = "0123456789" if answer[i].isdigit() else _UPPER
        mutated = answer[:i] + rng.choice(pool.replace(answer[i], "")) + answer[i + 1:]
        return _pose(templates["encrypt" if encrypt else "decrypt"], text, fields), answer, mutated
    raise ProbeError(handler + ": no reading-independent instance in 200 draws")


def _cipher_keys(handler, question):
    """Every plaintext and ciphertext a cipher question involves under any reading of its rule."""
    encrypt, text, extra = kor._cipher_question(question)
    readings = getattr(kor, "_" + handler.split(":")[1])
    pattern = {"cipher:porta": r"Key: ([A-Z]+)", "cipher:disks": r"period: ([0-9]{1,4}) increment: ([0-9]{1,4})"}
    match = re.fullmatch(pattern.get(handler, ""), extra)
    other = set()
    if match is not None:
        try:
            for answer in readings(encrypt, text, *match.groups()):
                spellings = itertools.product(*answer) if isinstance(answer, tuple) else [answer]
                other.update("".join(s).upper() for s in itertools.islice(spellings, 4096))
        except kor.Unknown:
            pass
    first, second = ("plain", "cipher") if encrypt else ("cipher", "plain")
    return {(handler, first, text)} | {(handler, second, value) for value in other}


def _probe(handler, rng, instructions):
    """(question, reference answer, mutated answer) for one fresh instance."""
    if handler.startswith("cipher:"):
        return _cipher_probe(handler, rng, instructions)
    if handler in _FORMAT:
        generate, show = _FORMAT[handler]
        expression, value = generate(rng)
        if isinstance(value, tuple):
            mutated = show((value[0] + 1, value[1]))
        else:
            mutated = show(value + 1)
        return f"Compute {expression}.\n{instructions}", show(value), mutated
    if handler in {"operation:matrix_power", "operation:matrix_affine"}:
        if handler == "operation:matrix_power":
            blocks, value = _matrix(rng, 1, 6, 0, 3, lambda x, y: x ** y)
            symbol = "&"
        else:
            blocks, value = _matrix(rng, -5, 9, -5, 9, lambda x, y: 2 * x + 3 * y)
            symbol = "€"
        mutated = [[value[0][0] + 1, value[0][1]], value[1]]
        return f"{blocks}Compute A{symbol}B.\n{instructions}", _matrix_text(value), _matrix_text(mutated)
    if handler == "puzzle:twenty_four":
        numbers, expression, mutated = _twenty_four(rng)
        question = "The four randomly selected numbers are:\n" + " ".join(map(str, numbers)) + ".\n" + instructions
        return question, expression, mutated
    if handler == "puzzle:sudoku":
        body, grid, hidden = _sudoku(rng)
        a, b = next((x, y) for x, y in itertools.combinations(hidden, 2)
                    if x // 9 == y // 9 and grid[x // 9][x % 9] != grid[y // 9][y % 9])
        swapped = [row[:] for row in grid]
        swapped[a // 9][a % 9], swapped[b // 9][b % 9] = grid[b // 9][b % 9], grid[a // 9][a % 9]
        return f"{body}\n{instructions}", _rows(grid), _rows(swapped)
    if handler == "puzzle:skyscrapers":
        body, grid = _skyscrapers(rng)
        swapped = [row[:] for row in grid]
        swapped[0][0], swapped[0][1] = grid[0][1], grid[0][0]
        return f"{body}\n{instructions}", _rows(grid), _rows(swapped)
    if handler == "puzzle:hidato":
        body, grid, shown = _hidato(rng)
        where = {grid[i][j]: (i, j) for i in range(9) for j in range(9)}
        # Swapping k and k+1 (both hidden, k >= 2) always breaks the path: k-1's cell and
        # k+1's old cell are both neighbours of k's cell, hence never adjacent to each other.
        k = rng.choice([k for k in range(2, 80) if k not in shown and k + 1 not in shown])
        (a, b), (c, d) = where[k], where[k + 1]
        swapped = [row[:] for row in grid]
        swapped[a][b], swapped[c][d] = k + 1, k
        return f"{body}\n{instructions}", _rows(grid), _rows(swapped)
    raise ProbeError("no generator for " + handler)


GENERATED = (*_FORMAT, "operation:matrix_power", "operation:matrix_affine",
             "puzzle:twenty_four", "puzzle:sudoku", "puzzle:skyscrapers", "puzzle:hidato",
             "cipher:affine", "cipher:solitaire", "cipher:grid_shift", "cipher:porta", "cipher:disks",
             "cipher:morse_pairs", "cipher:rail_columns", "cipher:sbox_blocks", "cipher:ascii_scale")


def _instructions(handler, questions):
    """Public answer-format instructions of this rule, taken from a panel question.

    A cipher rule instead yields one whole public question per direction, whose quoted
    input and fields a probe replaces.
    """
    if handler.startswith("cipher:"):
        templates = {}
        for question in questions:
            try:
                encrypt = kor._cipher_question(question)[0]
            except kor.Unknown:
                continue
            templates.setdefault("encrypt" if encrypt else "decrypt", question)
        if len(templates) != 2:
            raise ProbeError("no public question of each direction for " + handler)
        return templates
    for question in questions:
        if handler.startswith("operation"):
            found = _operation_instructions(question)
        else:
            template = kor._PUZZLE_TEMPLATES[{"puzzle:sudoku": "puzzle:grid_letters"}.get(handler, handler)]
            index = question.find(template[:24])
            found = question[index:] if index >= 0 else None
        if found:
            return found
    raise ProbeError("no public instructions for " + handler)


def _literals(text):
    """Exact numeric values after the verifier's own cleaning and tokenization."""
    return tuple(sorted(Fraction(token) for token in kor._tokens(text)
                        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", token)))  # ASCII only: '②' is an operator


def _dihedral(grid):
    """The eight rotations and reflections of a square grid."""
    n, shapes = len(grid), []
    for transpose in (False, True):
        g = [list(row) for row in zip(*grid)] if transpose else [list(row) for row in grid]
        for flip_rows in (False, True):
            for flip_columns in (False, True):
                h = g[::-1] if flip_rows else g
                shapes.append(tuple(tuple(row[::-1] if flip_columns else row) for row in h))
    assert all(len(shape) == n for shape in shapes)
    return shapes


def _relabeled(grid):
    """Digits renamed in order of first appearance (row-major); blanks (0) stay blank."""
    names = {}
    return tuple(tuple(0 if v == 0 else names.setdefault(v, len(names) + 1) for v in row) for row in grid)


def _cells(body):
    """A square grid of integers, blanks ('X') as 0, or None when the body is not one."""
    rows = [line.split() for line in body.strip("\n").split("\n") if line.strip()]
    if not rows or any(len(row) != len(rows) for row in rows) \
            or not all(t == "X" or _is_number(t) for row in rows for t in row):
        return None
    return [[0 if t == "X" else int(t) for t in row] for row in rows]


def _symmetries(top, bottom, left, right):
    """Skyscraper clue sets under the eight rotations and reflections of the grid."""
    states, frontier = set(), [(tuple(top), tuple(bottom), tuple(left), tuple(right))]
    while frontier:
        state = frontier.pop()
        if state in states:
            continue
        states.add(state)
        t, b, lf, r = state
        frontier += [(lf, r, t, b), (t[::-1], b[::-1], r, lf)]  # transpose, mirror
    return min(states)


def _canonical(handler, question):
    """Task inputs regardless of presentation, so a probe never re-poses an evaluation task.

    Operation questions are keyed only by their multiset of exact numbers (operators,
    order and spelling ignored): conservative, it may exclude more than necessary.
    """
    text = " ".join(question.split())
    if handler == "puzzle:twenty_four":
        found = re.search(r"numbers are:\s*((?:[0-9]+\s+){3}[0-9]+)", text)
        if found:  # the order of the four numbers carries no meaning
            return handler, tuple(sorted(int(v) for v in found.group(1).split()))
    elif handler == "puzzle:skyscrapers":
        body = question.split("Grid Layout:")[-1].split("The answer should be given")[0]
        lines = [line.split() for line in body.strip("\n").split("\n") if line.strip()]
        if lines and all(_is_number(t) for t in lines[0] + lines[-1]) and len(lines) == len(lines[0]) + 2:
            middle = lines[1:-1]
            return handler, len(lines[0]), _symmetries([int(t) for t in lines[0]], [int(t) for t in lines[-1]],
                                                       [int(r[0]) for r in middle], [int(r[-1]) for r in middle])
    elif handler in {"puzzle:sudoku", "puzzle:hidato"}:
        marker = "Please provide" if handler == "puzzle:sudoku" else "Output all the numbers"
        grid = _cells(question.split(marker)[0])
        if grid is not None:
            if handler == "puzzle:sudoku":  # rotations, reflections and digit renaming
                return handler, min(_relabeled(shape) for shape in _dihedral(grid))
            top = len(grid) ** 2 + 1  # a reversed path (k -> n*n+1-k) is the same puzzle
            reversed_grid = [[0 if v == 0 else top - v for v in row] for row in grid]
            return handler, min(_dihedral(grid) + _dihedral(reversed_grid))
    elif handler.startswith("operation"):
        return handler, _literals(kor._operation_head(question))
    return handler, text


def _is_number(token):
    return re.fullmatch(r"[0-9]+", token) is not None


def _keys(handler, question):
    if handler.startswith("cipher:"):
        return _cipher_keys(handler, question)
    return {_canonical(handler, question)}


def generate(tasks, *, per_rule, seed):
    """Probes for every generated registered rule, from panel tasks {task_id: task}."""
    by_handler = {}
    for task in tasks.values():
        handler = kor.RULES.get(kor.rule_hash(task["public"]["rule"]))
        if handler in GENERATED:
            by_handler.setdefault(handler, []).append(task)
    probes = []
    for handler in GENERATED:
        group = sorted(by_handler.get(handler, []), key=lambda t: t["task_id"])
        if not group:
            raise ProbeError("registered rule missing from the panel: " + handler)
        rule = group[0]["public"]["rule"]
        seen = set().union(*(_keys(handler, t["public"]["question"]) for t in group))
        instructions = _instructions(handler, [t["public"]["question"] for t in group])
        rng = random.Random(f"{seed}:{handler}")
        made, attempts = 0, 0
        while made < per_rule:
            attempts += 1
            if attempts > 1000 + 200 * per_rule:
                raise ProbeError(f"{handler}: probe space exhausted after {made} distinct probes")
            question, answer, mutated = _probe(handler, rng, instructions)
            keys = _keys(handler, question)
            if keys & seen:
                continue  # never re-pose a panel task (in either direction for a cipher) or an earlier probe
            seen |= keys
            reference = kor.verify(rule, question, f"[[{answer}]]")
            refuted = kor.verify(rule, question, f"[[{mutated}]]")
            if reference["status"] != "pass" or refuted["status"] != "fail":
                raise ProbeError(f"{handler} probe failed qualification: {reference['reason']}/{refuted['reason']}")
            category, rule_id = kor.RULE_IDS[handler]
            probes.append({"task_id": f"probe:{handler}:{made}", "family_id": f"probe:{handler}", "handler": handler,
                           "public": {"rule": rule, "question": question},
                           "private": {"reference": f"[[{answer}]]", "mutated": f"[[{mutated}]]",
                                       "category": category, "rule_id": rule_id}})
            made += 1
    return probes
