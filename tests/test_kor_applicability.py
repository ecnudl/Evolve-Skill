"""Label-free KOR verifier and its zero-call study: synthetic instances only, no KOR data."""
import hashlib
import json

import pytest

from scripts import report_kor_applicability as study
from skillopt.applicability import kor
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, write_json
from skillopt.validator_pilot.api import digest


def check(handler, question, response):
    rule = "synthetic rule for " + handler
    return kor.verify(rule, question, response, rules={kor.rule_hash(rule): handler})


ONE = " Please ensure the answer is a single number and wrap it in double square brackets, like this: [[your answer]]."
OR = (" When providing your answer, please enclose it in double square brackets, like this: [[answer]]."
      " If there is more than one correct answer, separate the answers with 'or', like this: [[1or2]].")
COMPLEX = (" If the answer is a complex number, write it in the form x + yi."
           " Please wrap the answer in double square brackets, like this: [[your answer]].")
MATRIX = " The answer is a matrix, write it in this form:[[((a,b),(c,d))]]."
A_B = ("A= \\[ \\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix} \\] "
       "B= \\[ \\begin{pmatrix} 0 & 1 \\\\ 2 & 3 \\end{pmatrix} \\] ")


@pytest.mark.parametrize("handler,question,response,status", [
    ("operation:circle", "Compute 1○2." + ONE, "[[21]]", "pass"),
    ("operation:circle", "Compute 1○2○1." + ONE, "The result is [[528]].", "pass"),
    ("operation:circle", "Compute 1○2." + ONE, "[[22]]", "fail"),
    ("operation:circle", "Compute 1○2." + ONE, "21", "fail"),                     # no answer span
    ("operation:circle", "Compute 1○2." + ONE, "[[21 or 3]]", "fail"),
    ("operation:circle", "Compute 1○2." + ONE, "[[twenty-one]]", "unknown"),
    ("operation:circle", "Compute 1○2." + ONE, "[[your answer]] so [[21]]", "unknown"),  # first span, as officially
    ("operation:circle", "Compute 1○2=21." + ONE, "[[21]]", "unknown"),           # ambiguous question
    ("operation:circle", "Compute 1○2." + ONE + " Please use A○B=A+B for this question.", "[[21]]", "unknown"),
    ("operation:circle", "Now we make a little change to the rule: compute 1○2." + ONE, "[[21]]", "unknown"),
    # Exact arithmetic: no floating-point acceptance or cancellation failures.
    ("operation:circle", "Compute 100000○100000." + ONE, "[[80000000001]]", "fail"),
    ("operation:circle", "Compute 100000○100000." + ONE, "[[80000000000]]", "pass"),
    ("operation:circle", "Compute 1○2." + ONE, "[[10000000000000000+21-10000000000000000]]", "pass"),
    # Custom-operator precedence is never guessed.
    ("operation:circle", "Compute -1○2." + ONE, "[[5]]", "unknown"),
    ("operation:circle", "Compute (-1)○2." + ONE, "[[5]]", "pass"),
    ("operation:circle", "Compute 2×1○2." + ONE, "[[42]]", "unknown"),
    ("operation:complex_pair", "Compute 2i⊕3." + COMPLEX, "[[3i]]", "unknown"),
    ("operation:circle", "If X○1=15, find X." + OR, "[[2or-6]]", "unknown"),       # sound, completeness open
    ("operation:circle", "If X○1=15, find X." + OR, "[[X=2 or X=3]]", "fail"),
    ("operation:circle", "If X○1=15, find Y." + OR, "[[2]]", "unknown"),
    # An unsupported equation stays unknown whatever the response, even without an answer span.
    ("operation:circle", "If X○1+1=16, find X." + OR, "I cannot solve this.", "unknown"),
    ("operation:circle", "If X○1+1=16, find X." + OR, "[[2]]", "unknown"),
    ("operation:circle", "If (X○1)+1=16, find X." + OR, "I cannot solve this.", "fail"),
    ("operation:circle", "If (X○1)+1=16, find X." + OR, "[[2or-6]]", "unknown"),
    ("operation:multiple", "Compute 6※3※5." + ONE, "[[24]]", "pass"),            # left to right: 6※3=4, 4※5=24
    ("operation:multiple", "Compute 2※8." + ONE, "[[6]]", "pass"),
    ("operation:angle", "Compute ⟨1,2,3,4⟩." + ONE, "[[3]]", "pass"),
    ("operation:angle", "Compute ⟨1,2,3⟩." + ONE, "[[3]]", "unknown"),            # wrong arity
    ("operation:venus_mars", "Compute (3♀5)♂1." + ONE, "[[17]]", "pass"),
    # Irrational values are interval enclosures: they can refute an answer, never confirm it.
    ("operation:sqrt", "Compute (4①3)②4." + ONE, "[[4\\sqrt{11}]]", "unknown"),   # √(√4+3²)·4
    ("operation:sqrt", "Compute (4①3)②4." + ONE, "[[13.27]]", "fail"),
    ("operation:sqrt", "Compute (4①3)②4." + ONE, "[[13.2665]]", "fail"),          # a decimal is not 4√11
    ("operation:log", "Compute 2￠8." + ONE, "[[10/3]]", "pass"),                 # exact: log_8 2 = 1/3
    ("operation:log", "Compute 2￠8." + ONE, "[[3.3333333333]]", "fail"),
    ("operation:log", "Compute 2￠4." + ONE, "[[\\frac{5}{2}]]", "pass"),
    ("operation:log", "Compute 2￠4." + ONE, "[[2 1/2]]", "unknown"),             # mixed number, not 2·1/2
    ("operation:log", "Compute 2￠4." + ONE, "[[2\\frac{1}{2}]]", "unknown"),
    ("operation:log", "Compute 5￠8." + ONE, "[[\\log_{8}{5}+\\log_{5}{8}]]", "unknown"),
    ("operation:log", "Compute 5￠8." + ONE, "[[\\log_{8}{5}+\\log_{5}{9}]]", "fail"),
    ("operation:complex_pair", "Compute (1⊕2)×(3⊕4)." + COMPLEX, "[[−5 + 10i]]", "pass"),
    ("operation:complex_square", "Compute (1◎1)+(1◎2)." + COMPLEX, "[[-3+6i]]", "pass"),
    ("operation:complex_square", "Compute (1◎1)+(1◎2)." + COMPLEX, "[[-3+5i]]", "fail"),
    # Matrices: the whole structure is read, never a flattened digit sequence.
    ("operation:matrix_power", A_B + "Compute A&B." + MATRIX, "[[((1,2),(9,64))]]", "pass"),
    ("operation:matrix_power", A_B + "Compute A&B." + MATRIX, "[[((1,2),(9,8*8))]]", "pass"),
    ("operation:matrix_power", A_B + "Compute A&B." + MATRIX,
     "[[\\begin{pmatrix} 1 & 2 \\\\ 9 & 64 \\end{pmatrix}]]", "pass"),
    ("operation:matrix_power", A_B + "Compute A&B." + MATRIX, "[[((1.2,9.64))]]", "fail"),
    ("operation:matrix_power", A_B + "Compute A&B." + MATRIX, "[[((1,2,9,64))]]", "fail"),
    ("operation:matrix_power", A_B + "Compute A&B." + MATRIX, "[[1 2 9 64]]", "unknown"),
    ("operation:matrix_affine", A_B + "Compute A€B." + MATRIX, "[[((2,7),(12,18))]]", "fail"),
    ("operation:matrix_affine", "Now ignoring the previous rule. " + A_B + "Compute A€B." + MATRIX,
     "[[((2,7),(12,17))]]", "unknown"),
])
def test_operation_rules(handler, question, response, status):
    assert check(handler, question, response)["status"] == status


def test_irrational_answers_are_refuted_by_rigorous_enclosures_never_confirmed():
    # (9①2)②4 = √(√9+2²)·4 = 4√7, an irrational value.
    question = "Compute (9①2)②4." + ONE
    for equal in ("[[4\\sqrt{7}]]", "[[\\sqrt{112}]]", "[[10^18+4\\sqrt{7}-10^18]]"):
        assert check("operation:sqrt", question, equal)["reason"] == "irrational_equality_unprovable"
    for wrong in ("[[2\\sqrt{7}]]", "[[10.583005244258]]", "[[4\\sqrt{7}+(10^18+\\sqrt{2}-10^18)]]"):
        assert check("operation:sqrt", question, wrong)["status"] == "fail"
    # Perfect squares stay exact: (81①0)②4 = √(√81+0²)·4 = 12.
    assert check("operation:sqrt", "Compute (81①0)②4." + ONE, "[[12]]")["status"] == "pass"
    assert check("operation:sqrt", "Compute (81①0)②4." + ONE, "[[12.000000001]]")["status"] == "fail"


TWENTY_FOUR = kor._PUZZLE_TEMPLATES["puzzle:twenty_four"]
NUMBERS = "The four randomly selected numbers are:\n8 3 8 3.\n" + TWENTY_FOUR


@pytest.mark.parametrize("question,response,status", [
    (NUMBERS, "[[8 ÷ (3 − 8 ÷ 3)]]", "pass"),
    (NUMBERS, "[[8/(3-8/3) = 24]]", "pass"),
    (NUMBERS, "[[\\frac{8}{3-\\frac{8}{3}}]]", "pass"),
    (NUMBERS.replace("3.\n", "3\n"), "[[8/(3-8/3)]]", "pass"),
    (NUMBERS, "[[(8-3)*(8-3)]]", "fail"),
    (NUMBERS, "[[8*3]]", "fail"),
    (NUMBERS, "[[8/(3-3)+8]]", "fail"),
    (NUMBERS, "[[8^1*3+8-8]]", "fail"),             # only the four basic operations are allowed
    (NUMBERS, "[[8(3-8/3)]]", "unknown"),           # implicit multiplication is not parsed
    (NUMBERS, "[[twenty four]]", "unknown"),
    ("The numbers are hidden.\n" + TWENTY_FOUR, "[[24]]", "unknown"),
    (NUMBERS + " Use exponentiation as well.", "[[8/(3-8/3)]]", "unknown"),  # unrecognized instruction
])
def test_twenty_four(question, response, status):
    assert check("puzzle:twenty_four", question, response)["status"] == status


GRID_LETTERS = kor._PUZZLE_TEMPLATES["puzzle:grid_letters"]
SOLVED = ["534678912", "672195348", "198342567", "859761423", "426853791",
          "713924856", "961537284", "287419635", "345286179"]


def sudoku(rows):
    grid = "\n".join(" ".join(c if (i + j) % 3 == 0 else "X" for j, c in enumerate(r)) for i, r in enumerate(SOLVED))
    return check("puzzle:sudoku", grid + "\n" + GRID_LETTERS, "[[" + ",".join(rows) + "]]")


def test_sudoku():
    rows = [" ".join(r) for r in SOLVED]
    assert sudoku(rows)["status"] == "pass"
    assert sudoku(rows[:3] + ["8 5 9 7 61 4 2 3"] + rows[4:])["status"] == "pass"  # merged single digits
    swapped = list(rows)
    swapped[0] = "5 3 4 6 7 8 9 2 1"  # both swapped cells are blanks: columns break
    assert sudoku(swapped)["reason"] == "sudoku_constraint"
    changed = list(rows)
    changed[0] = "3 5 4 6 7 8 9 1 2"
    assert sudoku(changed)["reason"] == "given_changed"
    assert sudoku(rows[:8])["reason"] == "malformed_grid"
    assert sudoku(["your answer"])["status"] == "unknown"


HIDATO = kor._PUZZLE_TEMPLATES["puzzle:hidato"]


def test_hidato():
    question = "1 X 3\nX 5 X\n7 X 9\n" + HIDATO
    assert check("puzzle:hidato", question, "[[1 2 3,6 5 4,7 8 9]]")["status"] == "pass"
    assert check("puzzle:hidato", question, "[[1 2 3;6 5 4;7 8 9]]")["status"] == "pass"
    assert check("puzzle:hidato", question, "[[1 2 3,4 5 6,7 8 9]]")["reason"] == "consecutive_numbers_not_adjacent"
    assert check("puzzle:hidato", question, "[[1 2 3,6 5 4,7 8 8]]")["reason"] == "not_each_number_once"
    assert check("puzzle:hidato", "1 X\nX 5 X\n" + HIDATO, "[[1]]")["status"] == "unknown"


def test_islands():
    question = "1 X 1\nX X X\n1 X 1\n\n" + GRID_LETTERS
    assert check("puzzle:islands", question, "[[1 A 1,A A A,1 A 1]]")["status"] == "pass"
    assert check("puzzle:islands", question, "[[1 X 1,A A A,1 A 1]]")["reason"] == "island_hint_or_size"
    assert check("puzzle:islands", question, "[[2 A 1,A A A,1 A 1]]")["reason"] == "hint_changed_or_invalid_cell"
    blocked = "2 X X\nX X X\nX X X\n\n" + GRID_LETTERS
    assert check("puzzle:islands", blocked, "[[2 X A,A A A,A A A]]")["reason"] == "wall_2x2_block"
    # Walls on both sides of a full-height island: every other constraint holds.
    split = "X 3 X\nX X X\nX X X\n\n" + GRID_LETTERS
    assert check("puzzle:islands", split, "[[A 3 A,A X A,A X A]]")["reason"] == "walls_not_continuous"


def dominoes(layout, response):
    question = ("Grid Layout:\n" + "\n".join("\t".join(r) for r in layout) + "\n"
                + kor._PUZZLE_TEMPLATES["puzzle:dominoes"])
    return check("puzzle:dominoes", question, response)


def test_dominoes():
    layout = ["AABB", "AABB", "CCDD", "CCDD"]
    grid = "Grid Layout:\n" + "\n".join("\t".join(r) for r in layout) + "\n" + kor._PUZZLE_TEMPLATES["puzzle:dominoes"]
    horizontal = "[[(1,1)(1,2),(1,4)(2,4),(3,1)(4,1),(4,3)(4,4)]]"
    for prefixed in ("All dominoes must be vertical.\n" + grid, "Grid Layout:\n" + grid):
        assert check("puzzle:dominoes", prefixed, horizontal)["status"] == "unknown"
    valid = "(1,1)(1,2),(1,4)(2,4),(3,1)(4,1),(4,3)(4.4)"
    assert dominoes(layout, f"[[{valid}]]")["status"] == "pass"
    assert dominoes(layout, f"[[{valid},(-1,1)(-1,2)]]")["reason"] == "domino_not_adjacent_cells"
    assert dominoes(layout, f"[[{valid}, and more]]")["status"] == "unknown"
    assert dominoes(layout, "[[]]")["reason"] == "no_dominoes"
    assert dominoes(layout, "[[(1,1)(1,2),(1,4)(2,4),(3,1)(4,1),(3,4)(4,4)]]")["reason"] == "dominoes_touch"
    assert dominoes(layout, "[[(1,1)(2,2),(1,4)(2,4)]]")["reason"] == "domino_not_adjacent_cells"
    # One letter may label two disjoint regions; each needs exactly two covered cells.
    split = ["AACAA", "CCCCC", "CCCCC"]
    assert dominoes(split, "[[(1,1)(1,2),(1,4)(1,5),(3,2)(3,3)]]")["status"] == "pass"
    assert dominoes(split, "[[(1,1)(1,2),(3,2)(3,3)]]")["reason"] == "region_coverage"


def skyscrapers(grid):
    n = len(grid)
    columns = [[grid[i][j] for i in range(n)] for j in range(n)]
    clues = [[kor._visible(c) for c in columns], [kor._visible(c[::-1]) for c in columns]]
    rows = "\n".join(f"{kor._visible(r)}\t" + "\t".join("X" * n) + f"\t{kor._visible(r[::-1])}" for r in grid)
    return ("Grid Layout:\n\t" + "\t".join(map(str, clues[0])) + "\t\n" + rows + "\n\t"
            + "\t".join(map(str, clues[1])) + "\n" + kor._PUZZLE_TEMPLATES["puzzle:skyscrapers"])


def test_skyscrapers():
    small = skyscrapers([[1, 2, 3], [2, 3, 1], [3, 1, 2]])
    assert check("puzzle:skyscrapers", small, "[[1 2 3,2 3 1,3 1 2]]")["status"] == "pass"
    assert check("puzzle:skyscrapers", small, "[[1 3 2,2 1 3,3 2 1]]")["reason"] == "visibility_clue"
    assert check("puzzle:skyscrapers", small, "[[1 2 3,2 3 1,3 2 1]]")["reason"] == "latin_square"
    assert check("puzzle:skyscrapers", small, "[[1 2 3,2 3 1]]")["reason"] == "malformed_grid"
    big = [[(i + j) % 10 + 1 for j in range(10)] for i in range(10)]  # multi-digit cells
    answer = "[[" + ",".join(" ".join(map(str, r)) for r in big) + "]]"
    assert check("puzzle:skyscrapers", skyscrapers(big), answer)["status"] == "pass"
    zero = small.replace("Grid Layout:\n\t3", "Grid Layout:\n\t0", 1)  # "no clue" is not publicly defined
    assert check("puzzle:skyscrapers", zero, "[[1 2 3,2 3 1,3 1 2]]")["status"] == "unknown"
    for prefixed in ("The top-left cell is 3.\n" + small, small.replace("Grid Layout:", "Grid Layout:\nGrid Layout:", 1)):
        assert check("puzzle:skyscrapers", prefixed, "[[1 2 3,2 3 1,3 1 2]]")["status"] == "unknown"


# Independently recorded public identities of the registered rule texts (from the frozen KOR panel).
EXPECTED_RULES = {
    "8c7dd333754ee3c1f56763adb95670a9288961f2d9f794a7c7efcaeb79aa71ee": ("operation", "1"),
    "f580d18a3d0726ebd835b4578791541741d4f9b29d56861bc83015d372ed1df1": ("operation", "2"),
    "0a8f117f381c855d4c3643355e3589f1d6347e8976b1155f63dbc8aefeba2300": ("operation", "3"),
    "9875028fc445d09ce3ac327e62cbd39a699306f02c8b4ddb1546f51abbc12a18": ("operation", "7"),
    "007be49f4f841bb9daae2161b8c64faec1fb86a8b277d25e78468f47d0064f48": ("operation", "8"),
    "dd6f40b2937dd200969307e7d9951337d3d99fd1303c5a3ace52b46d5e834177": ("operation", "10"),
    "ae9a7d101bfa9161bc454b8f2a8c00c6102213c5b5bf94e473dae8076cd97657": ("operation", "13"),
    "2852d61f9f957e6369ef2a52653cc77d4a8f37bc08249b5a0b73282d278c7ffe": ("operation", "14"),
    "6e91a231c5274509652a5ae8b9a875c2a413b5d2598815023100efeb8546173b": ("operation", "23"),
    "2317fbeb07bccfd054fd3187ac9f74551815d2e20f096cbfb8f442c68f4c2a35": ("operation", "25"),
    "482ee0aca292a74878ace115b99e95e018814f4281c4ec4f9df1a13e63b78d81": ("puzzle", "10"),
    "8a7410ba6fc4737118c9d43cd172316d421af6c14340c04deb78919394c3d2a0": ("puzzle", "13"),
    "4f3cd425f139794588a37eafe863b33daa8bb45f0b02d48b44de77dd5eac6c18": ("puzzle", "14"),
    "cfc14cfa03c2e2a40bb08d0b34c16b02fcaf4909956835ba4c44e736833b2512": ("puzzle", "15"),
    "0a4ddc9d9a406b9ef3930aa125d63b39f055d23a459bc34c152e3d5ead2aee16": ("puzzle", "23"),
    "332d3bf55d6ea1f0a6db746cdc99f13a8d8b30899cffe5896d8606d570203515": ("puzzle", "25"),
    "e3c0ebaa02b3aa3a355004a05a4291a40d38db2f10883c88e188ab6d8bb5c90f": ("cipher", "5"),
    "8eca8eeda76db554fa5ce29f4efb1e5fdcfae0faabb6d40a7205e1a64edaa5f2": ("cipher", "6"),
    "37f052dd0c40365783167c148de2c5a368bd446bd3f8f93fc3134e044b848608": ("cipher", "7"),
    "f3e138da05cadaf95795c18d5ce18104075c3a6d4220e3ec40d923255532388d": ("cipher", "8"),
    "dbf633d3e0832d9c465e44ad6af432b7ded7352a9e871f253c9a49112fecb6dd": ("cipher", "9"),
    "aa8d071bed655c5d822b06742d906a0bb600e163d1380c8afc1d25032107320f": ("cipher", "12"),
    "8cd20f759610034c6d7dd2e1926bd8d1e128991290b327ae1504137a540511dd": ("cipher", "16"),
    "d31d789eb29dd359a4d6c232f98fefa6b72667dbfcecffb39284de933b2e1456": ("cipher", "22"),
    "dd19412f1555bfb94b239792c86f4538852e76467960d423cebcc41f24089ed1": ("cipher", "24"),
}


def test_registry_declares_each_public_rule_identity():
    # A swapped production mapping changes some hash's declared identity.
    assert {h: kor.RULE_IDS[handler] for h, handler in kor.RULES.items()} == EXPECTED_RULES
    assert len(kor.RULES) == 25 and set(kor.RULES.values()) == set(kor.HANDLERS) == set(kor.RULE_IDS)
    assert all(handler.split(":")[0] == kor.RULE_IDS[handler][0] for handler in kor.HANDLERS)
    assert len(set(kor.RULE_IDS.values())) == len(kor.RULE_IDS)
    assert kor.verify("some unregistered rule", "Compute 1○2.", "[[21]]")["reason"] == "unregistered_rule"
    assert kor.verify(None, "q", "[[1]]")["reason"] == "invalid_input"
    long = "[[21]]" + " " * kor.MAX_RESPONSE_CHARS
    assert check("operation:circle", "Compute 1○2." + ONE, long)["reason"] == "response_too_long"


# ------------------------------------------------------------------ cipher rules
ENC = ("\n\nPlease provide the encrypted answer, encapsulated in double square brackets. "
       "For example, the format should be: [[encrypted answer]].")
DEC = ENC.replace("encrypted", "decrypted")


def cipher(handler, text, response, *, decrypt=False, fields=""):
    question = f'{"Ciphertext" if decrypt else "Plaintext"}: "{text}"\n' + (fields and fields + "\n")
    return check(handler, question + (DEC if decrypt else ENC), response)


@pytest.mark.parametrize("handler,text,response,decrypt,fields,status,reason", [
    # Affine: O sits at 6, (3*6+5) % 26 = 23 is E; decryption 9*(23-5) % 26 = 6.
    ("cipher:affine", "O", "[[E]]", False, "", "pass", "cipher_answer"),
    ("cipher:affine", "O", 'The answer is [[ "E" ]].', False, "", "pass", "cipher_answer"),  # official cleaning
    ("cipher:affine", "O", "[[e]]", False, "", "fail", "wrong_cipher_answer"),               # case is significant
    ("cipher:affine", "O", "E", False, "", "fail", "no_answer_span"),
    ("cipher:affine", "O", "[[X]] then [[E]]", False, "", "fail", "wrong_cipher_answer"),  # first span, as officially
    ("cipher:affine", "E", "[[O]]", True, "", "pass", "cipher_answer"),
    ("cipher:affine", "o", "[[E]]", False, "", "unknown", "input_outside_rule"),
    ("cipher:affine", "PARAMETER", "[[QMOMPYVYO]]", False, "", "pass", "cipher_answer"),    # data, not an instruction
    ("cipher:affine", "O", "[[E]]", False, "Key: ABC", "unknown", "unrecognized_question"),
    # Solitaire: the rule's worked example yields keystream 14 first; V (19) + 14 = 33 % 26 = 7 is C.
    ("cipher:solitaire", "V", "[[C]]", False, "", "pass", "cipher_answer"),
    ("cipher:solitaire", "C", "[[V]]", True, "", "pass", "cipher_answer"),
    # Grid shift: B (1,1) -> (2,2) K in Grid0; J passes through; every grid gives the same diagonal step.
    ("cipher:grid_shift", "BJ", "[[KJ]]", False, "", "pass", "cipher_answer"),
    ("cipher:grid_shift", "KJ", "[[BJ]]", True, "", "pass", "cipher_answer"),
    ("cipher:grid_shift", "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBB", "[[" + "K" * 30 + "]]", False, "", "pass", "cipher_answer"),
    # Porta: key letter G selects GH; O (14) -> E; the key repeats.
    ("cipher:porta", "O", "[[E]]", False, "Key: GZ", "pass", "cipher_answer"),
    ("cipher:porta", "OA", "[[EN]]", False, "Key: GA", "pass", "cipher_answer"),
    ("cipher:porta", "AA", "[[NN]]", False, "Key: A", "pass", "cipher_answer"),
    ("cipher:porta", "E", "[[O]]", True, "Key: H", "pass", "cipher_answer"),
    ("cipher:porta", "O", "[[E]]", False, "", "unknown", "unrecognized_question"),
    # Disks: no rotation before the first character; the rotation direction (prose vs example) and which of
    # the inner disk's two Js decrypts are reading-dependent; P is absent from the inner disk.
    ("cipher:disks", "Q", "[[J]]", False, "period: 1 increment: 4", "pass", "cipher_answer"),
    ("cipher:disks", "QQ", "[[JX]]", False, "period: 1 increment: 4", "unknown", "reading_dependent_answer"),
    ("cipher:disks", "QQ", "[[JY]]", False, "period: 1 increment: 4", "unknown", "reading_dependent_answer"),
    ("cipher:disks", "QQ", "[[JJ]]", False, "period: 1 increment: 4", "fail", "wrong_cipher_answer"),
    ("cipher:disks", "QQ", "[[JJ]]", False, "period: 2 increment: 4", "pass", "cipher_answer"),
    ("cipher:disks", "QQ", "[[JF]]", False, "period: 1 increment: 13", "pass", "cipher_answer"),  # both agree
    ("cipher:disks", "J", "[[Q]]", True, "period: 1 increment: 1", "unknown", "reading_dependent_answer"),
    ("cipher:disks", "JJ", "[[QJ]]", True, "period: 9 increment: 1", "unknown", "reading_dependent_answer"),
    ("cipher:disks", "JJ", "[[QA]]", True, "period: 9 increment: 1", "fail", "wrong_cipher_answer"),
    ("cipher:disks", "J", "[[A]]", True, "period: 1 increment: 1", "fail", "wrong_cipher_answer"),
    ("cipher:disks", "P", "[[A]]", True, "period: 1 increment: 1", "unknown", "undefined_by_rule"),
    ("cipher:disks", "Q", "[[J]]", False, "period: 0 increment: 1", "unknown", "input_outside_rule"),
    # Morse pairs: AB is .-/-... (the rule's example): .- /- .. and an unmapped trailing "." that rejoins it.
    ("cipher:morse_pairs", "AB", "[[415.]]", False, "", "pass", "cipher_answer"),
    ("cipher:morse_pairs", "415.", "[[AB]]", True, "", "pass", "cipher_answer"),
    ("cipher:morse_pairs", "415.", "[[AD]]", True, "", "fail", "wrong_cipher_answer"),
    ("cipher:morse_pairs", "2", "[[E]]", True, "", "unknown", "undefined_by_rule"),
    ("cipher:morse_pairs", "40", "[[A]]", True, "", "unknown", "input_outside_rule"),
    # Rail columns: the worked example and the prose disagree once an upward column exists.
    ("cipher:rail_columns", "ABC", "[[A*B*C***]]", False, "", "pass", "cipher_answer"),
    ("cipher:rail_columns", "HELLOWORLD", "[[HL#*ERD*LO*LW*O#*]]", False, "", "unknown", "reading_dependent_answer"),
    ("cipher:rail_columns", "HELLOWORLD", "[[H##*ELD*LR*LO*OW*]]", False, "", "unknown", "reading_dependent_answer"),
    ("cipher:rail_columns", "HELLOWORLD", "[[HL*ERD*LO*LW*O*]]", False, "", "fail", "wrong_cipher_answer"),
    ("cipher:rail_columns", "HL#*ERD*LO*LW*O#*", "[[HELLOWORLD]]", True, "", "pass", "cipher_answer"),
    ("cipher:rail_columns", "H##*ELD*LR*LO*OW*", "[[HELLOWORLD]]", True, "", "pass", "cipher_answer"),
    ("cipher:rail_columns", "HL#*ERD", "[[HELLO]]", True, "", "unknown", "input_outside_rule"),
    # S-box blocks: only hexadecimal A-E must be capitals, so an F may be written either way; a 16-byte
    # key meets 8-byte blocks (restart or continue); a reading decrypting to no stated plaintext is
    # inadmissible; a decrypted space cannot be compared.
    ("cipher:sbox_blocks", "B", "[[3B9C9986938C9784]]", False, "", "pass", "cipher_answer"),
    ("cipher:sbox_blocks", "B", "[[3b9c9986938c9784]]", False, "", "fail", "wrong_cipher_answer"),
    ("cipher:sbox_blocks", "AA", "[[2F389986938C9784]]", False, "", "unknown", "reading_dependent_answer"),
    ("cipher:sbox_blocks", "AA", "[[2f389986938C9784]]", False, "", "unknown", "reading_dependent_answer"),
    ("cipher:sbox_blocks", "AA", "[[2f389986938c9784]]", False, "", "fail", "wrong_cipher_answer"),
    ("cipher:sbox_blocks", "BBBBBBBBB", "[[3B2C272E352431303B9C9986938C9784]]", False, "", "unknown",
     "reading_dependent_answer"),
    ("cipher:sbox_blocks", "BBBBBBBBB", "[[3B2C272E35243130358E746D6877627D]]", False, "", "unknown",
     "reading_dependent_answer"),
    ("cipher:sbox_blocks", "BBBBBBBBB", "[[3B2C272E352431303B9C9986938C9785]]", False, "", "fail",
     "wrong_cipher_answer"),
    ("cipher:sbox_blocks", "2f389986938C9784", "[[AA]]", True, "", "pass", "cipher_answer"),
    ("cipher:sbox_blocks", "3B2C272E352431303B9C9986938C9784", "[[BBBBBBBBB]]", True, "", "pass", "cipher_answer"),
    ("cipher:sbox_blocks", "3B2C272E35243130358E746D6877627D", "[[BBBBBBBBB]]", True, "", "pass", "cipher_answer"),
    ("cipher:sbox_blocks", "3B7D2786938C9784", "[[B B]]", True, "", "unknown", "answer_not_comparable"),
    ("cipher:sbox_blocks", "0123", "[[A]]", True, "", "unknown", "input_outside_rule"),
    ("cipher:sbox_blocks", "2e389986938C9784", "[[AA]]", True, "", "unknown", "input_outside_rule"),
    # ASCII scale: A is 65 * 12 = 780.
    ("cipher:ascii_scale", "AB", "[[780, 792]]", False, "", "pass", "cipher_answer"),
    ("cipher:ascii_scale", "AB", "[[780 792]]", False, "", "fail", "wrong_cipher_answer"),
    ("cipher:ascii_scale", "780,803", "[[AB]]", True, "", "pass", "cipher_answer"),   # integer division
    ("cipher:ascii_scale", "12", "[[A]]", True, "", "unknown", "undefined_by_rule"),
])
def test_cipher_rules(handler, text, response, decrypt, fields, status, reason):
    result = cipher(handler, text, response, decrypt=decrypt, fields=fields)
    assert (result["status"], result["reason"]) == (status, reason)


def test_cipher_question_must_be_fully_recognized():
    assert cipher("cipher:affine", "O", "[[E]]")["status"] == "pass"
    mismatched = 'Plaintext: "O"' + DEC                                          # plaintext asked to decrypt
    assert check("cipher:affine", mismatched, "[[E]]")["reason"] == "unrecognized_instruction"
    extra = 'Plaintext: "O"' + ENC + " Use A=5 instead."
    assert check("cipher:affine", extra, "[[E]]")["reason"] == "unrecognized_instruction"
    assert check("cipher:affine", 'Plaintext: "O" Given that A=5,' + ENC, "[[E]]")["reason"] == \
        "unrecognized_question"
    assert check("cipher:affine", 'Plaintext: "O" "P"' + ENC, "[[E]]")["reason"] == "unrecognized_question"
    assert cipher("cipher:affine", "O" * (kor.MAX_CIPHER_INPUT + 1), "[[E]]")["reason"] == "input_too_long"


def test_solitaire_follows_the_rules_worked_example():
    deck = list(kor._DECK)
    assert kor._keystream(deck) == 14
    assert deck == [29, 20, 51, 6, 7, 52, 34, 35, 5, 50, 9, 46, 23, 54, 9, 25, 44, 38, 40, 22, 11, 36, 13, 39, 18,
                    42, 10, 31, 24, 14, 8, 33, 2, 49, 45, 21, 53, 12, 1, 16, 3, 43, 37, 17, 30, 4, 28, 48, 27, 41,
                    32, 15, 47, 26]
    for card, steps, start, end in ((53, 1, 53, 1), (54, 2, 52, 1), (54, 2, 53, 2), (54, 2, 51, 53)):
        deck = [c for c in range(1, 55) if c != card]
        deck.insert(start, card)
        kor._move(deck, card, steps)
        assert deck.index(card) == end and len(deck) == 54


def test_disks_rotation_follows_the_worked_example_or_the_prose():
    # The example: rotating ZXCV...OP by 4 gives BNMA...ZXCV; a string rotated "to the right" ends ...UIO.
    assert kor._disks(True, "QQ", "1", "4") == {"J" + kor._INNER[4], "J" + kor._INNER[-4]}


@pytest.mark.parametrize("handler,fields", [
    ("cipher:affine", ()), ("cipher:solitaire", ()), ("cipher:grid_shift", ()), ("cipher:porta", ("KEY",)),
    ("cipher:disks", ("3", "5")), ("cipher:morse_pairs", ()), ("cipher:rail_columns", ()),
    ("cipher:sbox_blocks", ()), ("cipher:ascii_scale", ()),
])
def test_every_encryption_reading_decrypts_back(handler, fields):
    readings = {"cipher:affine": kor._affine, "cipher:solitaire": kor._solitaire, "cipher:grid_shift": kor._grid_shift,
                "cipher:porta": kor._porta, "cipher:disks": kor._disks, "cipher:morse_pairs": kor._morse_pairs,
                "cipher:rail_columns": kor._rail_columns, "cipher:sbox_blocks": kor._sbox_blocks,
                "cipher:ascii_scale": kor._ascii_scale}[handler]
    for text in ("A", "HELLO", "QUICKBROWNFOXJUMPSOVERTHELAZYDOG", "ZZZZZZZZZZZZZZZZZZZ"):
        for answer in readings(True, text, *fields):
            if isinstance(answer, str):  # tuples only list alternative spellings of a string answer
                assert any(kor._fits(e, text) for e in readings(False, answer, *fields))


# ---------------------------------------------------------------- zero-call study
CIRCLE, TWENTY, LOGIC = "test circle rule", "test 24 rule", "test logic rule"
TASKS = [  # task_id, rule, question, gold, (category, rule_id)
    ("operation:1", CIRCLE, "Compute 1○2." + ONE, "[[21]]", ("operation", "2")),
    ("puzzle:1", TWENTY, NUMBERS, "[[8/(3-8/3)\n8÷(3-8÷3)]]", ("puzzle", "10")),
    ("operation:2", CIRCLE, "Compute 2○1." + ONE, "[[16]]", ("operation", "2")),        # gold breaks the rule: 15
    ("operation:3", CIRCLE, "If X○1=15, find X." + OR, "[[2or-6]]", ("operation", "2")),  # gold not provable
    ("logic:1", LOGIC, "Which is it?", "[[A]]", ("logic", "1")),
]
SERVICE = {"name": "fixture-service"}


def task(task_id, rule_id=None):
    _, rule, question, gold, (category, default) = next(t for t in TASKS if t[0] == task_id)
    return {"task_id": task_id, "family_id": task_id, "partition": "development", "project_id": None,
            "public": {"rule": rule, "question": question},
            "private": {"answer": gold, "category": category, "rule_id": rule_id or default}}


def run_dir(root, method, stage, skill, outputs, statuses, rule_ids=None, *, repeats=2, max_tokens=4096,
            unavailable=()):
    plan = seal({"version": "fixture-plan", "repeats": repeats,
                 "config": {"panels": {"korbench": str(root.parent / "panel.json")}, "methods": [method],
                            "model": {"max_tokens": max_tokens}},
                 "tasks": [{"benchmark": "korbench", "task_id": t[0],
                            "task_hash": digest(task(t[0], (rule_ids or {}).get(t[0])))} for t in TASKS]})
    write_json(root / "plan.json", plan)
    checkpoint = seal({"plan_hash": plan["record_hash"], "method": method, "history": "h0", "stage": stage,
                       "skill_text": skill, "skill_hash": hashlib.sha256(skill.encode()).hexdigest()})
    write_json(root / f"checkpoints/{method}/h0/s{stage}.json", checkpoint)
    rows = []
    for (task_id, *_), output, status in zip(TASKS, outputs, statuses):
        for repeat in (0, 1):
            request = {"benchmark": "korbench", "plan_hash": plan["record_hash"], "repeat": repeat,
                       "task_hash": digest(task(task_id, (rule_ids or {}).get(task_id))),
                       "checkpoint_hash": checkpoint["record_hash"]}
            attempt = ({"status": "unknown", "output": ""} if task_id in unavailable
                       else {"status": "available", "output": output})
            prediction = seal({"request": request, "prediction": attempt})
            name = f"{task_id.replace(':', '-')}-{repeat}"
            write_json(root / "predictions" / name / "prediction.json", prediction)
            score = seal({"task_id": task_id, "repeat": repeat, "status": status, "plan_hash": plan["record_hash"],
                          "method": method, "history": "h0", "stage": stage,
                          "checkpoint_hash": checkpoint["record_hash"], "prediction_hash": prediction["record_hash"]})
            write_json(root / "host_only/scores" / f"{name}.json", score)
            rows.append({"task_id": task_id, "family_id": task_id, "repeat": repeat, "status": status,
                         "record_hash": score["record_hash"]})
    return {"root": str(root), "plan_hash": plan["record_hash"], "rows": rows}


def make_study(tmp_path, monkeypatch, *, stage_edit=None, cell_edit=None, rule_ids=None, cell=None):
    monkeypatch.setattr(kor, "RULES", {kor.rule_hash(CIRCLE): "operation:circle",
                                       kor.rule_hash(TWENTY): "puzzle:twenty_four"})
    write_json(tmp_path / "panel.json", {"tasks": [task(t[0], (rule_ids or {}).get(t[0])) for t in TASKS]})
    base = run_dir(tmp_path / "noskill", "no_skill", 0, "",
                   ["[[21]]", "[[(8-3)*(8-3)]]", "[[15]]", "[[3]]", "[[A]]"], ["pass", "fail", "fail", "fail", "pass"],
                   rule_ids)
    reference = {**base, "positions": len(base["rows"]), "model_service": SERVICE}
    protocol = seal({"version": "fivebench-sequential-attempts-v4", "order": list(BENCHMARKS), "methods": ["skillopt"],
                     "references": {"korbench": reference}})
    write_json(tmp_path / "study/protocol.json", protocol)
    cell = run_dir(tmp_path / "s1", "skillopt", 1, "a skill",
                   ["[[20]]", "[[8 ÷ (3 − 8 ÷ 3)]]", "[[16]]", "[[2or-6]]", "[[B]]"],
                   ["fail", "fail", "pass", "pass", "fail"], rule_ids, **(cell or {}))
    result = {"benchmark": "korbench", "model_service": SERVICE, **cell, **(cell_edit(base, cell) if cell_edit else {})}
    stage = {"protocol_hash": protocol["record_hash"], "method": "skillopt", "stage": 1, "benchmark": BENCHMARKS[0],
             "parent_skill": "", "parent_stage_hash": None, "action": "selected_update", "skill": "a skill",
             "cells": {"korbench": {"result": result}}}
    write_json(tmp_path / f"study/skillopt/s1-{BENCHMARKS[0]}/stage.json", seal({**stage, **(stage_edit or {})}))
    return tmp_path / "study"


def test_study_separates_gold_scopes_and_compares_label_free_deltas(tmp_path, monkeypatch):
    report = study.build(make_study(tmp_path, monkeypatch))
    assert report["gold_inconsistent_tasks"] == {"operation:2": "value_differs"}
    assert report["positions"] == {"total": 10, "registered": 8, "gold_qualified": 4, "gold_unverified": 2,
                                   "gold_inconsistent": 2}
    assert report["gold_qualification"] == {"operation:circle": {"pass": 1, "fail": 1, "unknown": 1},
                                            "puzzle:twenty_four": {"pass": 1}}
    base = report["agreement"]["no_skill"]
    assert base["operation|gold_qualified"] == {"official_pass|verifier_pass": 2}
    assert base["puzzle|gold_qualified"] == {"official_fail|verifier_fail": 2}
    assert base["operation|gold_inconsistent"] == {"official_fail|verifier_pass": 2}  # noisy gold rejects a right answer
    assert base["operation|gold_unverified"] == {"official_fail|verifier_fail": 2}    # 3 refuted by substitution
    assert base["logic"] == {"unregistered": 2}
    qualified = report["paired_deltas"]["s1"]["gold_qualified"]["registered"]
    assert qualified["official_all"] == {"loss": 2, "tie": 2}     # official rejects the ÷ spelling
    assert qualified["verifier"] == {"loss": 2, "win": 2}
    assert qualified["official_same_positions"] == {"loss": 2, "tie": 2}
    wider = report["paired_deltas"]["s1"]["not_gold_inconsistent"]["registered"]
    assert wider["verifier"] == {"loss": 2, "win": 2, "unknown": 2}
    assert report["model_api_calls"] == 0 and not report["deployment_authorized"]
    assert "KOR" in study.markdown(report)


@pytest.mark.parametrize("kwargs,message", [
    ({"stage_edit": {"parent_skill": "x"}}, "Stage chain binding mismatch"),
    ({"stage_edit": {"action": "completed_no_update"}}, "Only an accepted update"),
    # Authentic No-Skill observations presented as the new Skill's cell.
    ({"cell_edit": lambda base, cell: base}, "does not hold the declared Skill"),
    ({"cell_edit": lambda base, cell: {"rows": [r for r in cell["rows"] if r["repeat"] == 0]}}, "Incomplete"),
    ({"rule_ids": {"operation:1": "3"}}, "Rule registry does not match"),
    ({"cell": {"repeats": 3}}, "Incomplete"),                        # its own plan declares more repeats
    ({"cell": {"max_tokens": 65536}}, "differs from the No-Skill reference"),
])
def test_study_refuses_unbound_or_incomplete_evidence(tmp_path, monkeypatch, kwargs, message):
    with pytest.raises(ValueError, match=message):
        study.build(make_study(tmp_path, monkeypatch, **kwargs))


def test_study_refuses_observations_that_do_not_bind(tmp_path, monkeypatch):
    root = make_study(tmp_path, monkeypatch)
    path = tmp_path / "s1/predictions/operation-1-0/prediction.json"
    value = json.loads(path.read_text())
    value["request"]["repeat"] = 1
    path.write_text(json.dumps(seal({k: v for k, v in value.items() if k != "record_hash"})))
    with pytest.raises(ValueError, match="does not bind to its prediction"):
        study.build(root)


def test_study_refuses_a_panel_or_plan_that_is_not_frozen(tmp_path, monkeypatch):
    root = make_study(tmp_path, monkeypatch)
    panel = json.loads((tmp_path / "panel.json").read_text())
    panel["tasks"][0]["public"]["question"] += " edited"
    (tmp_path / "panel.json").write_text(json.dumps(panel))
    with pytest.raises(ValueError, match="does not match the frozen plan"):
        study.build(root)
    plan = json.loads((tmp_path / "noskill/plan.json").read_text())
    (tmp_path / "noskill/plan.json").write_text(json.dumps(seal({**{k: v for k, v in plan.items() if k != "record_hash"},
                                                                   "other": 1})))
    with pytest.raises(ValueError, match="not the frozen reference plan"):
        study.build(root)


def test_unavailable_predictions_are_never_judged(tmp_path, monkeypatch):
    # An interrupted attempt (no answer) is unknown for the verifier, not a missing-span failure.
    report = study.build(make_study(tmp_path, monkeypatch, cell={"unavailable": {"operation:1"}}))
    assert report["agreement"]["s1"]["operation|gold_qualified"] == {"official_fail|verifier_unknown": 2}
    assert report["paired_deltas"]["s1"]["gold_qualified"]["operation"]["verifier"] == {"unknown": 2}
