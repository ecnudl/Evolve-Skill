"""Host-executed error-mode diagnosis on generated OfficeQA items (skillopt/feedback_study/error_modes.py)."""
from fractions import Fraction

from skillopt.feedback_study import error_modes as em

PAGES = ("### bulletin page 3\n"
         "| Fiscal year | Receipts | Expenditures | Deficit |\n"
         "| 1955 | 60,390 | 64,570 | 4,180 |\n"
         "| 1956 | 68,165 | 66,540 | 1,625 |\n"
         "| 1957 | 71,029 | 69,433 | 1,596 |\n")
DERIVATION = {"figures": [{"name": "a", "value": "60,390", "quote": "| 1955 | 60,390 | 64,570 | 4,180 |"},
                          {"name": "b", "value": "68,165", "quote": "| 1956 | 68,165 | 66,540 | 1,625 |"}],
              "expression": "(b - a) / a * 100", "decimals": 2, "answer": "12.87", "category": "percent"}


def mode(output, derivation=DERIVATION, pages=PAGES):
    return em.diagnose(derivation, pages, output)["mode"]


def test_each_simple_variant_is_named():
    # exact: (68165 - 60390) / 60390 * 100 = 12.8746...
    assert mode("<answer>12.9</answer>") == "rounding"
    assert mode("<answer>0.1287</answer>") == "power_of_ten" and mode("<answer>128.75</answer>") == "power_of_ten"
    assert mode("<answer>-12.87</answer>") == "sign"
    assert mode("<answer>-11.41</answer>") == "operand_order"  # (a - b) / b * 100
    d = em.diagnose(DERIVATION, PAGES, "<answer>17.62</answer>")  # b read from 1957 (71,029): same column
    assert d["mode"] == "neighbour_cell" and "71029" in d["detail"] and "same column, 1 table line(s) below" in d["detail"]
    note = em.render(DERIVATION, d, 1800)
    assert "| 1957 |" not in note and "69,433" not in note  # no other line of the page is quoted
    assert mode("work shown, no tag") == "not_one_number" and mode("<answer>12.87 percent</answer>") == "not_one_number"
    assert mode("<answer>55.5</answer>") == "unexplained"


def test_truncation_is_exact():
    third = {"figures": [{"name": "a", "value": "31", "quote": "| Right | 31 | 99 |"},
                         {"name": "b", "value": "3", "quote": "| Three | 3 | 0 |"}],
             "expression": "a / b", "decimals": 2, "answer": "10.33"}
    pages = "| Right | 31 | 99 |\n| Three | 3 | 0 |\n"
    assert mode("<answer>10.33</answer>", third, pages) == "unexplained"  # the right answer is never diagnosed as a slip
    assert mode("<answer>10.34</answer>", third, pages) == "unexplained"  # neither rounding nor truncation of 10.333...
    two = {**third, "figures": [{"name": "a", "value": "20", "quote": "| R | 20 | 9 |"}, {"name": "b", "value": "3", "quote": "| T | 3 | 0 |"}],
           "answer": "6.67"}
    assert mode("<answer>6.66</answer>", two, "| R | 20 | 9 |\n| T | 3 | 0 |\n") == "truncation"


def test_a_neighbour_is_taken_only_around_the_quoted_cell():
    deriv = {"figures": [{"name": "a", "value": "31", "quote": "| Right | 31 | 99 |"},
                         {"name": "b", "value": "3", "quote": "| Three | 3 | 0 |"}],
             "expression": "a / b", "decimals": 2, "answer": "10.33"}
    pages = "| Right | 31 | 99 |\n| Three | 3 | 0 |\n\nAnother table\n| Other | 31 | 21 |\n"
    assert mode("<answer>7.00</answer>", deriv, pages) == "unexplained"  # 21 / 3 comes from an unrelated table
    assert mode("<answer>33.00</answer>", deriv, pages) == "neighbour_cell"  # 99 / 3: the quoted row
    ambiguous = "| Right | 31 | 99 |\n| Right | 31 | 98 |\n| Three | 3 | 0 |\n"
    assert em._anchor(ambiguous, deriv["figures"][0]) == (0, 2)  # the full quote picks one row
    assert em._anchor(ambiguous, {**deriv["figures"][0], "quote": "| Right | 31 |"}) is None  # two places: abstain
    big = "\n".join("| r%d | %d | 31 |" % (i, i) for i in range(5000)) + "\n| Three | 3 | 0 |\n"
    assert len(em._neighbours(big, {"name": "a", "value": "31", "quote": "| r31 | 31 | 31 |"})) <= em.MAX_SUBSTITUTES


def test_hostile_answers_are_bounded():
    assert em.final_answer("<answer>" + "9" * 400 + ".1</answer>") == (None, None)
    assert em.final_answer("<answer>" + "1" * 20000 + "</answer>") == (None, None)
    assert mode("<answer>" + "9" * 400 + ".1</answer>") == "not_one_number"
    assert em.final_answer("<answer>1</answer> then <answer>$1,234.50</answer>") == (Fraction("1234.50"), 2)
    assert mode("<answer>0.00</answer>") != "power_of_ten"  # zero is never called a power-of-ten variant
    assert mode("<answer>0.00</answer>") == "neighbour_cell"  # b read as 60,390 (the column's 1955 cell) gives 0


def test_the_note_puts_the_diagnosis_before_the_quotes_and_is_bounded():
    d = em.diagnose(DERIVATION, PAGES, "<answer>0.1287</answer>")
    note = em.render(DERIVATION, d, 1800)
    assert note.index("Diagnosis (power_of_ten)") < note.index('a = 60,390 ("')
    assert "expected 12.87; your answer 0.1287" in note and "(b - a) / a * 100" in note
    short = em.render(DERIVATION, d, 300)
    assert "Diagnosis (power_of_ten)" in short and len(short) <= 300 + len(" …[truncated]")
