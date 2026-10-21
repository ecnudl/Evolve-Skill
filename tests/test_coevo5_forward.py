"""coevo5 forward panels (registration v6 §8): exact arithmetic, the validity rules of the two generated styles, the
independent consistency check, deduplication by identity, the round and panel limits, and the frozen scorer on the
produced tasks."""
from fractions import Fraction

import pytest

from skillopt.coevo5 import forward
from skillopt.coevo5.outcomes import BudgetStop
from skillopt.coevo5.roles import Invalid
from skillopt.continual_eval import backends
from skillopt.continual_eval.datasets import livemath_options
from tests.coevo5_fakes import Script
from tests.coevo5_fakes import roles as make_roles

ROWS = [["Year", "Revenue", "Share"], ["2019", "$1,234.50", "12.5%"], ["2020", "1,300", "−3.2"]]
QUOTE = "The binomial coefficient is the number of ways to choose k elements from a set of n elements."


def office_material(title="Revenue of a company", revid=101, rows=ROWS):
    return {"style": "officeqa", "source": {"title": title, "revid": revid}, "page": "sha256:page",
            "table": {"caption": "Revenue", "rows": rows}, "text": "\n".join(" | ".join(r) for r in rows)}


def live_material(title="Binomial coefficient", revid=7, quote=QUOTE):
    return {"style": "livemath", "source": {"title": title, "revid": revid}, "page": "sha256:page", "quote": quote,
            "text": quote}


def office_item(question, formula="1300 - 1234.50", decimals=2, answer="65.50"):
    return {"question": question, "formula": formula, "decimals": decimals, "answer": answer}


def live_item(question, options=("8", "10", "12", "15", "20"), answer="B", formula="comb(5, 2)"):
    return {"question": question, "options": list(options), "answer": answer, "formula": formula}


class Model:
    """Answers generation calls from ``batches`` (one per call, in order) and check calls by ``check(payload)``."""

    def __init__(self, target, batches, check=None):
        self.target, self.batches = target, list(batches)
        self.check = check or (lambda payload: {"formula": "1300 - 1234.50"} if target == "officeqa"
                               else {"verdict": "yes"})

    def __call__(self, system, payload):
        if system == forward.GENERATE_SYSTEM[self.target]:
            return self.batches.pop(0)
        assert system == forward.CHECK_SYSTEM[self.target]
        return self.check(payload)


def panel(tmp_path, target, batches, *, check=None, materials=None, rule_id="s1-r2"):
    """(result, roles, script, rounds whose material was requested); calls are labelled fwd/<rule>/<target>."""
    roles, script = make_roles(tmp_path, Model(target, batches, check))
    requested = []

    def material(number):
        requested.append(number)
        if materials is not None:
            return materials(number)
        return office_material() if target == "officeqa" else live_material()

    result = forward.build_panel(roles, rule_id=rule_id, rule_text="Compute differences from the exact cells.",
                                 target=target, material=material, label="fwd/%s/%s" % (rule_id, target))
    return result, roles, script, requested


# --------------------------------------------------------------------------------------------- exact arithmetic
@pytest.mark.parametrize("formula, value", [
    ("0.1 + 0.2", Fraction(3, 10)),
    ("1/3*3", Fraction(1)),
    ("2**-2", Fraction(1, 4)),
    ("-(3 - 5) ** 2", Fraction(-4)),
    ("+7 / 2", Fraction(7, 2)),
    ("comb(5, 2) + perm(4, 2) + factorial(5)", Fraction(142)),
    ("gcd(12, 18) + lcm(4, 6)", Fraction(18)),
    ("floor(7/2) + ceil(-7/2)", Fraction(0)),
    ("min(3, 1.5) * max(2, 4, 3)", Fraction(6)),
    ("abs(-2.5)", Fraction(5, 2)),
    ("1234.50 - 0.005", Fraction(246899, 200)),  # 1234.495 exactly, never a float
    ("2 ** (1 + 1) ** 2", Fraction(16)),
])
def test_formulas_evaluate_exactly(formula, value):
    assert forward.evaluate(formula) == value and type(forward.evaluate(formula)) is Fraction


@pytest.mark.parametrize("formula", [
    "", "   ", "1e3", "0x10", "1_000", ".5", "5.", "1j", "x + 1", "__import__('os')", "(1).real", "1 if 1 else 2",
    "[1, 2]", "1, 2", "'a'", "True", "None", "1/0", "1 / (2 - 2)", "2 ** 0.5", "2 ** 11", "0 ** -1", "min(1)",
    "abs(1, 2)", "abs(x=1)", "factorial(101)", "factorial(2.5)", "factorial(-1)", "comb(1001, 2)", "perm(5, -1)",
    "gcd(1.5, 2)", "lcm(4)", "round(1.5)", "max(*[1, 2])", "1 % 2", "1 // 2", "1 < 2", "lambda: 1", "-" * 301,
    "1+" * 50 + "1", "(((10 ** 10) ** 10) ** 10) ** 10",
])
def test_formulas_outside_the_grammar_are_refused(formula):
    with pytest.raises(Invalid):
        forward.evaluate(formula)


def test_literals_are_kept_as_written_in_order():
    assert forward.literals("(12.50 - 3) * 2 + max(0.1, 007.5)") == ["12.50", "3", "2", "0.1", "007.5"]
    with pytest.raises(Invalid):
        forward.literals("1e3 + 1")


@pytest.mark.parametrize("value, decimals, written", [
    (Fraction(2345, 1000), 2, "2.35"), (Fraction(-2345, 1000), 2, "-2.35"), (Fraction(5, 2), 0, "3"),
    (Fraction(-5, 2), 0, "-3"), (Fraction(-1, 1000), 2, "0.00"), (Fraction(1, 3), 4, "0.3333"),
    (Fraction(12), 2, "12.00"), (Fraction(1, 20), 1, "0.1"), (Fraction(-1, 20), 1, "-0.1"),
    (Fraction(123449, 100), 0, "1234"),
])
def test_rounding_is_half_away_from_zero_with_exactly_the_stated_digits(value, decimals, written):
    assert forward.rounded(value, decimals) == written


def test_identity_normalises_the_material_and_the_question():
    same = forward.identity("Year | Revenue\n2019 | 1", "What  is it?")
    assert forward.identity("year | revenue 2019 | 1", "WHAT is it?") == same
    assert forward.identity("Year | Revenue\n2019 | 1", "What is it？") == same  # NFKC: a full-width mark
    assert forward.identity("Year | Revenue\n2019 | 2", "What is it?") != same


# --------------------------------------------------------------------------------------------- OfficeQA style
def test_an_officeqa_item_uses_only_table_cells_and_states_its_rounding(tmp_path):
    batch = {"items": [
        office_item("Q1 revenue growth?"),  # "1,300" and "$1,234.50" written without separators and sign
        office_item("Q2 sum of share and the change?", formula="-3.2 + 12.5", decimals=1, answer="9.3"),  # % and minus
        office_item("Q3 rounded wrong?", formula="1300 - 1234.5", answer="65.50"),  # not verbatim: "1234.50"
    ]}

    def check(payload):
        return {"formula": "1300 - 1234.50" if payload["question"].startswith("Q1") else "12.5 + -3.2"}

    result, roles, _, _ = panel(tmp_path, "officeqa", [batch] + [{"items": []}] * 4, check=check)
    assert [i["id"] for i in result["items"]] == ["fwd:s1-r2:officeqa:1", "fwd:s1-r2:officeqa:2"]
    first, second = result["items"]
    assert first["public"] == {"question": "Q1 revenue growth? Round your answer to 2 decimal places.",
                               "context": "Source: Wikipedia, Revenue of a company (revision 101)\n"
                                          + office_material()["text"]}
    assert first["private"] == {"answer": "65.50"} and second["private"] == {"answer": "9.3"}
    assert second["public"]["question"].endswith("Round your answer to 1 decimal place.")
    assert result["counts"]["dropped"] == {"literal_not_in_table": 1}
    assert roles.count("fwd/s1-r2/officeqa/r1/check") == 2
    assert result["status"] == "short" and result["counts"]["rounds"] == 5


@pytest.mark.parametrize("raw, reason", [
    ({"question": "Q?", "formula": "1300 - 1234.50", "decimals": 2}, "format"),  # no answer
    (office_item("Q?", decimals=5), "format"),
    (office_item("Q?", decimals=True), "format"),
    (office_item("x" * 601), "format"),
    ({**office_item("Q?"), "note": "extra"}, "format"),
    (office_item("Q?", formula="1300 -"), "formula"),
    (office_item("Q?", formula="1300 / (2019 - 2019)"), "formula"),
    (office_item("Q?", formula="1300 * 2"), "literal_not_in_table"),
    (office_item("Q?", answer="65.4"), "answer_mismatch"),
    (office_item("Q?", answer="65.50 dollars"), "answer_mismatch"),
    (office_item("Q?", formula="1300 - 1234.50", decimals=0, answer="66"), None),
    (office_item("Q?", answer="65.5"), None),  # the same number: the reference is written with the stated digits
])
def test_each_officeqa_validity_rule(tmp_path, raw, reason):
    result, roles, _, _ = panel(tmp_path, "officeqa", [{"items": [raw]}] + [{"items": []}] * 4)
    if reason is None:
        assert len(result["items"]) == 1 and roles.count("fwd/s1-r2/officeqa/r1/check") == 1
        assert result["items"][0]["private"]["answer"] == ("66" if raw["decimals"] == 0 else "65.50")
    else:
        assert result["items"] == [] and result["counts"]["dropped"] == {reason: 1}
        assert roles.count("fwd/s1-r2/officeqa/r1/check") == 0  # no check call for an item the program refuses


def test_the_officeqa_check_sees_only_the_table_and_the_question_and_must_agree(tmp_path):
    batch = {"items": [office_item("Q1?"), office_item("Q2?"), office_item("Q3?")]}
    answers = {"Q1?": {"formula": "1300 - 1234.50"}, "Q2?": {"formula": "1300 - 2019"}, "Q3?": "not json"}
    result, _, script, _ = panel(tmp_path, "officeqa", [batch] + [{"items": []}] * 4,
                                 check=lambda p: answers[p["question"].split(" Round")[0]])
    checks = [payload for system, payload in script.seen if system == forward.CHECK_SYSTEM["officeqa"]]
    assert all(set(p) == {"table", "question"} and p["table"] == office_material()["text"] for p in checks)
    assert len(result["items"]) == 1
    assert result["counts"]["dropped"] == {"check_mismatch": 1, "check_invalid": 1}


def test_the_officeqa_check_formula_too_takes_every_number_from_a_cell(tmp_path):
    batch = {"items": [office_item("Q1?"), office_item("Q2?")]}
    answers = {"Q1?": {"formula": "1300 - 1234.5"}, "Q2?": {"formula": "65.50"}}  # same values, numbers not cells
    result, _, _, _ = panel(tmp_path, "officeqa", [batch] + [{"items": []}] * 4,
                            check=lambda p: answers[p["question"].split(" Round")[0]])
    assert result["items"] == [] and result["counts"]["dropped"] == {"check_literal_not_in_table": 2}


# --------------------------------------------------------------------------------------------- LiveMath style
@pytest.mark.parametrize("raw, reason", [
    (live_item("Ways to choose 2 of 5?"), None),
    (live_item("Ways?", options=("8", "10", "12", "15")), "options"),
    (live_item("Ways?", options=("1/2", "0.5", "10", "12", "15")), "options"),  # the same number twice
    (live_item("Ways?", options=("8", "ten", "12", "15", "20")), "options"),
    (live_item("Ways?", options=("8", "10", "1/0", "15", "20")), "options"),
    (live_item("Ways?", answer="F"), "format"),
    (live_item("Ways?", answer="b"), "format"),
    (live_item("Ways?", answer="C"), "answer_mismatch"),  # the formula's value is option B
    (live_item("Ways?", formula="comb(6, 2)"), "answer_mismatch"),  # 15: option D, not the answer
    (live_item("Ways?", formula="comb(7, 2)"), "answer_mismatch"),  # 21: no option
    (live_item("Ways?", formula="comb(5, two)"), "formula"),
    (live_item("Ways?", options=("-8", "+10.0", "3/4", "15", "20"), answer="B", formula="10"), None),
])
def test_each_livemath_validity_rule(tmp_path, raw, reason):
    result, roles, _, _ = panel(tmp_path, "livemath", [{"items": [raw]}] + [{"items": []}] * 4)
    if reason is None:
        item = result["items"][0]
        assert livemath_options(item["public"]["choices"]) == [o.strip() for o in raw["options"]]
        assert item["private"] == {"answer": "B"} and item["public"]["question"] == raw["question"]
        assert roles.count("fwd/s1-r2/livemath/r1/check") == 1
    else:
        assert result["items"] == [] and result["counts"]["dropped"] == {reason: 1}
        assert roles.count("fwd/s1-r2/livemath/r1/check") == 0


def test_the_livemath_check_sees_the_passage_question_and_formula_and_must_say_yes(tmp_path):
    batch = {"items": [live_item("Q1?"), live_item("Q2?"), live_item("Q3?")]}
    verdicts = {"Q1?": {"verdict": "yes"}, "Q2?": {"verdict": "no"}, "Q3?": {"verdict": "maybe"}}
    result, _, script, _ = panel(tmp_path, "livemath", [batch] + [{"items": []}] * 4,
                                 check=lambda p: verdicts[p["question"]])
    checks = [payload for system, payload in script.seen if system == forward.CHECK_SYSTEM["livemath"]]
    assert [set(p) for p in checks] == [{"passage", "question", "formula"}] * 3
    assert checks[0]["passage"] == QUOTE and checks[0]["formula"] == "comb(5, 2)"
    assert [i["public"]["question"] for i in result["items"]] == ["Q1?"]
    assert result["counts"]["dropped"] == {"check_rejected": 1, "check_invalid": 1}


# ----------------------------------------------------------------------------------------------------- panels
def test_a_repeated_question_on_the_same_material_is_a_duplicate_without_a_check_call(tmp_path):
    materials = {1: office_material(), 2: office_material(), 3: office_material(title="Other page", revid=5,
                                                                              rows=ROWS + [["2021", "7", "1"]])}
    batches = [{"items": [office_item("Q?")]}, {"items": [office_item(" q? ")]}, {"items": [office_item("Q?")]},
               {"items": []}, {"items": []}]
    result, roles, _, _ = panel(tmp_path, "officeqa", batches, materials=lambda n: materials.get(n))
    assert [i["source"]["title"] for i in result["items"]] == ["Revenue of a company", "Other page"]
    assert result["counts"]["duplicates"] == 1 and roles.count("fwd/s1-r2/officeqa/r2/check") == 0
    assert result["rounds"][1]["items"] == [{"position": 1, "identity": result["items"][0]["identity"],
                                             "outcome": "duplicate"}]


def test_a_question_that_failed_its_check_is_not_checked_again(tmp_path):
    batches = [{"items": [office_item("Q?")]}, {"items": [office_item("Q?")]}] + [{"items": []}] * 3
    result, roles, _, _ = panel(tmp_path, "officeqa", batches, check=lambda p: {"formula": "1300 - 2019"})
    assert result["items"] == [] and result["counts"]["dropped"] == {"check_mismatch": 1}
    assert result["counts"]["duplicates"] == 1 and roles.count("fwd/s1-r2/officeqa/r2/check") == 0


def test_the_panel_stops_at_twelve_distinct_items_with_one_generation_and_three_checks_per_round(tmp_path):
    batches = [{"items": [office_item("Q%d-%d?" % (r, j)) for j in range(3)]} for r in range(5)]
    result, roles, _, requested = panel(tmp_path, "officeqa", batches)
    assert result["status"] == "ok" and len(result["items"]) == 12 and requested == [1, 2, 3, 4]
    assert [i["id"] for i in result["items"]] == ["fwd:s1-r2:officeqa:%d" % n for n in range(1, 13)]
    for number in range(1, 5):
        assert roles.count("fwd/s1-r2/officeqa/r%d/generate" % number) == 1
        assert roles.count("fwd/s1-r2/officeqa/r%d/check" % number) == 3
    assert len(roles.calls) == 16 and len({i["identity"] for i in result["items"]}) == 12


def test_items_beyond_twelve_are_counted_and_never_checked(tmp_path):
    batches = [{"items": [office_item("Q%d-%d?" % (r, j)) for j in range(3 if r != 3 else 2)]} for r in range(4)]
    batches.append({"items": [office_item("Last%d?" % j) for j in range(3)]})
    result, roles, _, _ = panel(tmp_path, "officeqa", batches)
    assert len(result["items"]) == 12 and result["counts"]["dropped"] == {"panel_full": 2}
    assert roles.count("fwd/s1-r2/officeqa/r5/check") == 1
    counts = result["counts"]
    assert counts["generated"] == counts["valid"] + counts["duplicates"] + sum(counts["dropped"].values()) == 14


@pytest.mark.parametrize("per_round, status", [((3, 3, 2, 0, 0), "ok"), ((3, 3, 1, 0, 0), "short"),
                                               ((1, 1, 1, 1, 1), "short")])
def test_eight_items_make_a_panel_within_five_rounds(tmp_path, per_round, status):
    batches = [{"items": [office_item("Q%d-%d?" % (r, j)) for j in range(n)]} for r, n in enumerate(per_round)]
    result, _, _, requested = panel(tmp_path, "officeqa", batches)
    assert result["status"] == status and len(result["items"]) == sum(per_round) and requested == [1, 2, 3, 4, 5]


def test_no_material_or_an_invalid_generation_yields_nothing_that_round(tmp_path):
    materials = {1: None, 2: office_material(), 3: office_material(), 4: office_material(), 5: office_material()}
    batches = ["not json", {"items": [office_item("A?")] * 4}, {"things": []}, {"items": [office_item("B?")]}]
    result, roles, _, _ = panel(tmp_path, "officeqa", batches, materials=lambda n: materials[n])
    assert [r["reply"] for r in result["rounds"]] == ["no_material", "invalid", "invalid", "invalid", "ok"]
    assert roles.count("fwd/s1-r2/officeqa/r1/") == 0 and len(result["items"]) == 1
    assert result["counts"] == {"rounds": 5, "generated": 1, "valid": 1, "duplicates": 0, "dropped": {}}


def test_ids_are_namespaced_by_rule_and_target(tmp_path):
    a, _, _, _ = panel(tmp_path / "a", "officeqa", [{"items": [office_item("Q?")]}] + [{"items": []}] * 4,
                       rule_id="s1-r1")
    b, _, _, _ = panel(tmp_path / "b", "officeqa", [{"items": [office_item("Q?")]}] + [{"items": []}] * 4,
                       rule_id="s1-r3")
    c, _, _, _ = panel(tmp_path / "c", "livemath", [{"items": [live_item("Q?")]}] + [{"items": []}] * 4,
                       rule_id="s1-r1")
    assert [a["items"][0]["id"], b["items"][0]["id"], c["items"][0]["id"]] == [
        "fwd:s1-r1:officeqa:1", "fwd:s1-r3:officeqa:1", "fwd:s1-r1:livemath:1"]
    assert a["items"][0]["identity"] == b["items"][0]["identity"]  # the same question: still two items


def test_the_generation_request_names_the_rule_the_material_and_three_items(tmp_path):
    _, _, script, _ = panel(tmp_path, "livemath", [{"items": []}] * 5)
    system, payload = script.seen[0]
    assert system == forward.GENERATE_SYSTEM["livemath"] and payload == {
        "topic": "Compute differences from the exact cells.", "source": {"title": "Binomial coefficient", "revid": 7},
        "material": QUOTE, "count": 3}


def test_the_produced_tasks_score_with_the_frozen_scorers(tmp_path):
    office, _, _, _ = panel(tmp_path / "o", "officeqa", [{"items": [office_item("Growth?")]}] + [{"items": []}] * 4)
    live, _, _, _ = panel(tmp_path / "l", "livemath", [{"items": [live_item("Ways?")]}] + [{"items": []}] * 4)
    for item, right, wrong in ((office["items"][0], "65.50", "65.40"), (live["items"][0], "B", "C")):
        assert backends._public_view(item["benchmark"], item["public"]) == item["public"]
        for answer, status in ((right, "pass"), (wrong, "fail")):
            prediction = {"status": "available", "output": "Working.\n<answer>%s</answer>" % answer}
            score = backends.score(item["benchmark"], item["public"], item["private"], prediction)
            assert score["status"] == status


def test_a_stop_of_the_run_propagates(tmp_path):
    def stopped(number):
        raise BudgetStop("budget_stop:overall")

    with pytest.raises(BudgetStop):
        panel(tmp_path / "a", "officeqa", [], materials=stopped)

    def stop(system, payload):
        raise BudgetStop("budget_stop:overall")

    roles, _ = make_roles(tmp_path / "b", stop)
    with pytest.raises(BudgetStop):
        forward.build_panel(roles, rule_id="s1-r1", rule_text="Rule.", target="officeqa",
                            material=lambda n: office_material(), label="fwd")


@pytest.mark.parametrize("material", [
    live_material(),  # another style
    {**office_material(), "source": {"title": "T"}},  # no revision
    {**office_material(), "table": {"caption": "c", "rows": []}},
    {k: v for k, v in office_material().items() if k != "page"},
])
def test_malformed_material_is_a_fault_of_the_run(tmp_path, material):
    with pytest.raises(ValueError):
        panel(tmp_path, "officeqa", [{"items": []}] * 5, materials=lambda n: material)


def test_script_helper_is_the_shared_one():
    assert Script.__module__ == "tests.coevo5_fakes"
