"""coevo5 pure layer: the sectioned Skill, the format-check library, lenient scoring, exact statistics and the X v2
decision rules (registration §3, §5, §6)."""
from fractions import Fraction

import pytest

from skillopt.coevo5 import checks, gate, protocol, scoring, stats
from skillopt.coevo5.skill import Rule, Skill, seed_text

OFFICEQA_SEED = ("# Guidance for Treasury Bulletin Questions\n\n- Read the question first.\n"
                 "## Units\n- Watch millions versus billions.")


def test_an_empty_skill_renders_as_the_no_skill_prompt():
    assert Skill().render() == ""
    assert Skill.from_json(Skill().to_json()) == Skill()


def test_the_scaffold_renders_every_section_head_from_the_start():
    scaffold = Skill(scaffold=True)  # v2 §2: chain E's start
    text = scaffold.render()
    heads = ["## %s\n%s" % (protocol.TITLES[b], protocol.APPLIES_WHEN[b]) for b in protocol.ORDER]
    assert text == "\n\n".join(heads) and len(text.encode()) < 1000
    grown = scaffold.add(Rule("s2-r1", "Give the number only.", "officeqa"))
    assert grown.scaffold and grown.render().count("## ") == len(protocol.ORDER)
    assert grown.render().index("- Give the number only.") < grown.render().index("## LiveMath")
    assert Skill().add(Rule("s2-r1", "Give the number only.", "officeqa")).render().count("## ") == 1
    assert grown.to_json()["scaffold"] is True and "scaffold" not in Skill().to_json()
    assert Skill.from_json(grown.to_json()) == grown and Skill.from_json(scaffold.to_json()) == scaffold
    assert scaffold != Skill() and scaffold.size_with() == len(text.encode())
    for value in ({"seeds": {}, "rules": [], "scaffold": False}, {"seeds": {}, "rules": [], "scaffold": 1}):
        with pytest.raises(ValueError):
            Skill.from_json(value)


def test_sections_follow_the_registered_order_with_fixed_applicability_lines():
    skill = Skill.seeded({"officeqa": OFFICEQA_SEED}).add(
        Rule("s1-r1", "Keep the final answer short.", "searchqa", ("officeqa",)),  # a similar placement
        Rule("s1-r2", "Copy the exact surface form\nfrom the snippet.", "searchqa"),
        Rule("s2-r1", "Give the number only.", "officeqa"))
    text = skill.render()
    assert "Shared" not in text and text.index("## SearchQA") < text.index("## OfficeQA")
    assert protocol.APPLIES_WHEN["searchqa"] in text and protocol.APPLIES_WHEN["officeqa"] in text
    assert "## LiveMath" not in text
    assert "- Copy the exact surface form\n  from the snippet." in text
    # the seed's own headings are demoted below the section heading and the seed leads its section; a similar rule is
    # the same text at the end of each of its sections, in insertion order
    searchqa, officeqa = text[:text.index("## OfficeQA")], text[text.index("## OfficeQA"):]
    assert "### Guidance for Treasury Bulletin Questions" in officeqa and "#### Units" in officeqa
    assert officeqa.index("### Guidance") < officeqa.index("- Keep the final answer short.") < officeqa.index(
        "- Give the number only.")
    assert searchqa.count("- Keep the final answer short.") == 1 and text.count("- Keep the final answer short.") == 2
    assert Skill.from_json(skill.to_json()) == skill
    assert skill.to_json()["rules"][0] == {"id": "s1-r1", "text": "Keep the final answer short.", "home": "searchqa",
                                           "also": ["officeqa"]}
    assert seed_text(seed_text(OFFICEQA_SEED)) == seed_text(OFFICEQA_SEED)


@pytest.mark.parametrize("text", ["", " padded", "two\n\nblocks", "# heading", "x" * 601, "a\r\nb"])
def test_rules_are_single_bounded_blocks(text):
    with pytest.raises(ValueError):
        Rule("r", text, "searchqa")


def test_the_length_test_measures_appended_rules_and_every_copy_without_building_an_oversized_skill():
    parent = Skill().add(Rule("a", "Answer briefly.", "searchqa"))
    long = Rule("b", "y" * 600, "searchqa")
    assert parent.size_with(long) == len(parent.add(long).render().encode())
    copies = Rule("b", "y" * 600, "searchqa", ("officeqa",))  # the OfficeQA section and a second copy
    assert parent.size_with(copies) - parent.size_with(long) > 600
    many = [Rule("r%d" % i, "z" * 596 + "%04d" % i, "searchqa") for i in range(40)]
    assert not parent.fits(*many) and parent.size_with(*many) > protocol.MAX_SKILL_BYTES


@pytest.mark.parametrize("home, also", [
    ("kor", ()),  # unknown bench
    ("officeqa", ("spreadsheetbench",)),  # similar, but no forward panel can be generated: not checkable
    ("searchqa", ("livemath",)),  # not similar
    ("officeqa", ("livemath", "searchqa")),  # not in chain order
    ("officeqa", ("officeqa",)),  # its own section is not a similar target
    ("officeqa", ("searchqa",)),  # a placement is all of the stage's checkable similar targets or none (§3)
    ("officeqa", ("livemath",)),
    ("alfworld", ("officeqa",)),  # ALFWorld has no similar bench
    ("livemath", ["officeqa"]),  # a tuple
])
def test_a_rule_names_its_home_section_and_only_checkable_similar_targets(home, also):
    with pytest.raises(ValueError):
        Rule("c", "x", home, also)


def test_the_checkable_similar_targets_follow_the_confirmed_map():
    assert [protocol.similar_targets(b) for b in protocol.ORDER] == [
        ((), ("officeqa",)), (("searchqa",), ("livemath",)), (("officeqa",), ()), (("officeqa",), ()), ((), ())]


def test_skills_refuse_duplicates_and_oversize():
    rule = Rule("a", "Answer briefly.", "searchqa", ("officeqa",))
    with pytest.raises(ValueError):
        Skill().add(rule, Rule("a", "Other.", "searchqa"))
    with pytest.raises(ValueError):
        Skill().add(rule, Rule("b", "Answer briefly.", "searchqa"))
    with pytest.raises(ValueError):  # the same text twice in the OfficeQA section, through the similar copy
        Skill().add(rule, Rule("b", "Answer briefly.", "officeqa"))
    big = tuple(Rule("r%d" % i, "y" * 590 + "%04d" % i, "searchqa") for i in range(60))
    with pytest.raises(ValueError):
        Skill(rules=big)
    with pytest.raises(ValueError):
        Skill.from_json({"seeds": {}, "rules": [{"id": "a", "text": "x", "placement": "shared"}]})


@pytest.mark.parametrize("output,name,params,expected", [
    ("x <answer>B</answer>", "answer_single_letter", {}, True),
    ("<answer>b.</answer>", "answer_single_letter", {}, True),
    ("<answer>(B)</answer>", "answer_single_letter", {}, False),
    ("no tag", "answer_single_letter", {}, False),
    ("<answer>1,234.5</answer>", "answer_pure_number", {"allow_percent": False}, True),
    ("<answer>4.8%</answer>", "answer_pure_number", {"allow_percent": False}, False),
    ("<answer>4.8%</answer>", "answer_pure_number", {"allow_percent": True}, True),
    ("no tag", "answer_pure_number", {"allow_percent": True}, None),
    ("<answer>4.8 percent</answer>", "answer_no_letters", {}, False),
    ("<answer>a</answer> then <answer>Paris</answer>", "answer_max_words", {"n": 1}, True),
    ("<answer>a b c</answer>", "answer_max_words", {"n": 2}, False),
    ({"code": "print(1)", "cases": []}, "code_present", {}, True),
    ("text", "code_present", {}, None),
])
def test_format_checks(output, name, params, expected):
    assert checks.run({"name": name, "params": params}, output) is expected


@pytest.mark.parametrize("spec", [{"name": "eval", "params": {}}, {"name": "answer_max_words", "params": {"n": 99}},
                                  {"name": "answer_max_words", "params": {"n": "3"}},
                                  {"name": "answer_tag_present", "params": {"x": 1}}, {"name": "answer_tag_present"}])
def test_check_specs_are_validated_against_the_registered_schema(spec):
    with pytest.raises(ValueError):
        checks.validate(spec)


def _pred(output):
    return {"status": "available", "output": output}


@pytest.mark.parametrize("benchmark,private,output,expected", [
    ("searchqa", {"answers": ["Paris"]}, "<answer>Paris</answer>", True),
    ("searchqa", {"answers": ["Paris"]}, "<answer>The city of Paris</answer>", True),
    ("searchqa", {"answers": ["Paris"]}, "<answer>Parisian</answer>", False),
    # a list of candidates is not a single answer, and nothing outside the last tag counts
    ("searchqa", {"answers": ["Paris"]}, "<answer>London, Rome, Berlin, Madrid or Paris</answer>", False),
    ("searchqa", {"answers": ["Paris"]}, "It is Paris.", False),
    ("officeqa", {"answer": "4.815%"}, "<answer>4.815</answer>", True),
    ("officeqa", {"answer": "1,234.50"}, "<answer>$1234.5 million</answer>", True),
    ("officeqa", {"answer": "1234.5"}, "<answer>about 1,234.5</answer>", True),
    ("officeqa", {"answer": "1234.5"}, "<answer>1234.6</answer>", False),
    ("officeqa", {"answer": "1234.5"}, "<answer>1234.5 or 1234.6</answer>", False),
    ("officeqa", {"answer": "1234.5"}, "the total is 1,234.5", False),
    ("officeqa", {"answer": "March 2, 1998"}, "<answer>march 2 1998</answer>", True),
    ("livemath", {"answer": "C"}, "<answer>(C) 42</answer>", True),
    ("livemath", {"answer": "C"}, "<answer>C or D</answer>", False),
    ("livemath", {"answer": "C"}, "so the answer is (C).", False),
    ("livemath", {"answer": "C"}, "<answer>D</answer>", False),
])
def test_lenient_matching_reads_one_answer_in_the_last_tag(benchmark, private, output, expected):
    assert scoring.lenient(benchmark, private, _pred(output)) is expected


def test_lenient_matching_is_undefined_without_a_reply_or_a_decomposition():
    assert scoring.lenient("officeqa", {"answer": "1"}, {"status": "unknown"}) is None
    assert scoring.lenient("alfworld", {}, _pred({"won": True})) is None
    assert scoring.lenient("searchqa", {"answers": []}, _pred("<answer>x</answer>")) is None


def test_bounds_count_unknown_runs_as_fail_for_L_and_pass_for_H():
    table = stats.bounds({("a", "i1"): ["pass", "unknown"], ("a", "i2"): ["fail", "unknown_artifact"]})
    assert table[("a", "i1")] == (Fraction(1, 2), Fraction(1), 1, 2, 1)
    assert table[("a", "i2")] == (Fraction(0), Fraction(1, 2), 1, 2, 0)
    assert stats.total(table, "a", ["i1", "i2"], "L") == Fraction(1, 2)
    assert stats.total(table, "a", ["i1", "i2"], "H") == Fraction(3, 2)
    assert stats.unknown_share(table, "a", ["i1", "i2"]) == Fraction(1, 2)
    assert stats.unknown_share(table, "a", ["i1", "i2"], infrastructure_only=True) == Fraction(1, 4)
    with pytest.raises(ValueError):
        stats.total(table, "a", ["i3"], "L")
    with pytest.raises(ValueError):
        stats.bounds({("a", "i1"): ["maybe"]})


def test_sign_test_and_stratified_bootstrap():
    assert stats.sign_test(0, 0) == 1.0
    assert stats.sign_test(5, 0) == pytest.approx(0.0625)
    lo, hi = stats.bootstrap({"b": [1, 1, 0, -1, 1]}, lambda d: sum(d["b"]), resamples=2000)
    assert lo <= 2 <= hi
    # the same draw feeds both arms: a constant paired difference has a degenerate interval
    units = [(1, 0), (1, 0), (0, -1)]
    assert stats.bootstrap({"b": units}, lambda d: sum(a - b for a, b in d["b"]), resamples=500) == (3.0, 3.0)


ITEMS = {"trigger": ["t1", "t2", "t3", "t4"], "rest": ["r%d" % i for i in range(10)]}
CONTROLS = ["c0", "c1", "c2", "c3"]


def _table(rule_trigger, *, control_trigger="fail", rest_rule="pass", regression=None, unknown_rule_rest=0):
    """Parent fails every trigger item and passes the rest; controls differ from the parent on trigger items only."""
    cells = {}
    for i in ITEMS["trigger"]:
        cells[("parent", i)] = ["fail", "fail"]
        cells[("rule", i)] = [rule_trigger, rule_trigger]
        for c in CONTROLS:
            cells[(c, i)] = [control_trigger, "fail"]
    for n, i in enumerate(ITEMS["rest"]):
        cells[("parent", i)] = ["pass", "pass"]
        cells[("rule", i)] = ["unknown", "pass"] if n < unknown_rule_rest else [rest_rule, rest_rule]
    for bench, (parent, rule) in (regression or {}).items():
        for n in range(60):
            cells[("parent", "%s%d" % (bench, n))] = [parent[n]]
            cells[("rule", "%s%d" % (bench, n))] = [rule[n]]
    return stats.bounds(cells)


def _regression(bench, tolerance=5, violations=(0, 0), n=60):
    return {bench: {"items": ["%s%d" % (bench, i) for i in range(n)], "tolerance": tolerance, "violations": violations}}


def _verdict(table, regression=None, **extra):
    return gate.verdict(table, arm="rule", parent="parent", controls=CONTROLS, trigger=ITEMS["trigger"],
                        rest=ITEMS["rest"], tolerance=2, regression=regression or {}, **extra)


def test_a_rule_passes_when_it_beats_the_parent_and_every_control_without_harm():
    result = _verdict(_table("pass"))
    assert result["status"] == "pass" and result["criteria"]["C1"]["gain"] == "4" and result["margin"] == Fraction(4)


def test_a_control_doing_as_well_on_the_trigger_items_blocks_the_rule():
    table = _table("pass", control_trigger="pass")
    table.update({("c2", i): (Fraction(1), Fraction(1), 0, 2, 0) for i in ITEMS["trigger"]})
    assert _verdict(table)["status"] == "fail"


def test_harm_is_measured_against_the_parent_not_the_controls():
    assert _verdict(_table("pass", rest_rule="fail"))["status"] == "fail"  # -10 on the rest, tolerance 2
    # one of ten rest items unknown for the rule: L counts it as one failed run -> -1/2 item, within tolerance
    assert _verdict(_table("pass", unknown_rule_rest=1))["status"] == "pass"


def test_an_arm_with_more_than_a_tenth_unknown_runs_is_undetermined():
    # 2 unknown runs of 28 (7%): judged; 3 of 28 (11%): undetermined, never accepted, even though C1-C3 hold
    assert _verdict(_table("pass", unknown_rule_rest=2))["status"] == "pass"
    result = _verdict(_table("pass", unknown_rule_rest=3))
    assert result["status"] == "undetermined" and result["criteria"]["unknown_share"] == "3/28"


def test_regression_is_judged_bench_by_bench_with_each_panel_s_own_tolerance():
    parent = ["pass"] * 60
    harmed = ["fail"] * 6 + ["pass"] * 54
    regression = {"officeqa": (parent, harmed), "searchqa": (parent, parent)}
    table = _table("pass", regression=regression)
    panels = {**_regression("officeqa"), **_regression("searchqa")}
    result = _verdict(table, panels)
    assert result["status"] == "fail" and result["criteria"]["C3"]["searchqa"]["ok"] is True
    assert _verdict(table, {**_regression("officeqa", tolerance=6), **_regression("searchqa")})["status"] == "pass"
    assert _verdict(table, {**_regression("officeqa", tolerance=6, violations=(3, 0)),
                            **_regression("searchqa")})["status"] == "fail"
    # a smaller qualified SpreadsheetBench panel carries its own (calibrated) tolerance; no size rule in the gate
    small = _regression("searchqa", n=52, tolerance=6)
    assert _verdict(table, small)["status"] == "pass"
    with pytest.raises(ValueError):
        _verdict(table, {"searchqa": {"items": [], "tolerance": 5, "violations": (0, 0)}})


FORWARD = ["f%d" % n for n in range(8)]


def _similar_table(forward_rule, backward_rule=None):
    """Parent: half of the forward panel and every SearchQA regression item; the rule as given."""
    regression = {"searchqa": (["pass"] * 60, backward_rule or ["pass"] * 60)}
    table = _table("pass", regression=regression)
    for n, item in enumerate(FORWARD):
        table[("parent", item)] = (Fraction(n % 2), Fraction(n % 2), 0, 2, 0)
        table[("rule", item)] = (Fraction(forward_rule[n]), Fraction(forward_rule[n]), 0, 2, 0)
    return table


def test_a_similar_arm_needs_no_loss_against_the_parent_on_every_similar_target():
    panels = _regression("searchqa")
    targets = {"searchqa": panels["searchqa"]["items"], "livemath": FORWARD}
    table = _similar_table([n % 2 for n in range(8)])  # as good as the parent: no gain needed, no controls
    result = _verdict(table, panels, targets=targets)
    assert result["status"] == "pass" and result["criteria"]["C4'"]["livemath"] == {"ok": True, "delta": "0"}
    assert result["priority"] == result["margin"] == Fraction(4)
    better = _verdict(_similar_table([1] * 8), panels, targets=targets)
    assert better["status"] == "pass" and better["priority"] == Fraction(4 + 4)
    worse = _verdict(_similar_table([0, 0] + [n % 2 for n in range(2, 8)]), panels, targets=targets)  # f1: 1 -> 0
    assert worse["status"] == "fail" and worse["criteria"]["C4'"]["livemath"]["ok"] is False
    # a backward target is checked on its regression panel: C3 allows -5 there, C4' allows no loss
    harmed = ["fail"] + ["pass"] * 59
    backward = _verdict(_similar_table([n % 2 for n in range(8)], harmed), panels, targets=targets)
    assert backward["criteria"]["C3"]["searchqa"]["ok"] is True and backward["status"] == "fail"
    local = _verdict(table, panels)
    assert gate.placement(worse, local) == "local" and gate.placement(None, worse) is None
    assert gate.placement(result, local) == "similar"
    for bad in ({}, {"searchqa": panels["searchqa"]["items"][:59]}, {"livemath": FORWARD[:7]},
                {"livemath": FORWARD[:1] * 8}):
        with pytest.raises(ValueError):
            _verdict(table, panels, targets=bad)


def test_a_similar_placement_that_fails_its_confirmation_falls_back_to_the_bench_s_own_placement():
    passed, failed = {"status": "pass"}, {"status": "fail"}
    assert gate.confirmation_arms("similar", passed) == ["similar", "local"]
    assert gate.confirmation_arms("similar", failed) == ["similar"] and gate.confirmation_arms("local", None) == [
        "local"] and gate.confirmation_arms(None, passed) == []
    final = gate.final_placement
    assert final("similar", screen_local=passed, confirm_similar=passed, confirm_local=failed) == "similar"
    assert final("similar", screen_local=passed, confirm_similar=failed, confirm_local=passed) == "local"
    assert final("similar", screen_local=failed, confirm_similar=failed) is None
    assert final("similar", screen_local=passed, confirm_similar={"status": "undetermined"},
                 confirm_local=failed) is None
    assert final("local", screen_local=passed, confirm_local=passed) == "local"
    assert final("local", screen_local=passed, confirm_local=failed) is None


def test_rounds_whose_parent_or_controls_have_more_than_a_tenth_infrastructure_unknown_are_incomplete():
    table = stats.bounds({("a", "i%d" % n): ["unknown" if n < 2 else "pass"] for n in range(11)})
    assert not gate.round_complete(table, {"a": ["i%d" % n for n in range(10)]})  # 2 of 10
    assert gate.round_complete(table, {"a": ["i%d" % n for n in range(1, 11)]})  # 1 of 10
    # unscorable delivered workbooks are not an infrastructure failure of the round
    artifact = stats.bounds({("a", "i%d" % n): ["unknown_artifact" if n < 5 else "pass"] for n in range(10)})
    assert gate.round_complete(artifact, {"a": ["i%d" % n for n in range(10)]})


def test_composition_keeps_every_member_gain_and_falls_back_to_priority():
    cells = {}
    for i in ("x1", "x2", "y1", "y2", "r1"):
        cells[("parent", i)] = ["fail" if i != "r1" else "pass"]
        cells[("comp", i)] = ["pass"]
    table = stats.bounds(cells)
    members = [{"id": "a", "trigger": ["x1", "x2"]}, {"id": "b", "trigger": ["y1", "y2"]}]
    common = dict(arm="comp", parent="parent", members=members, rest=["r1"], tolerance=0, regression={})
    assert gate.composite(table, **common)["status"] == "pass"
    # a check panel of a similar member: S may not do worse than the parent there
    table[("parent", "p1")], table[("comp", "p1")] = (Fraction(1), Fraction(1), 0, 2, 0), (Fraction(1, 2),) * 2 + (
        0, 2, 0)
    assert gate.composite(table, **common, panels={"forward:a:livemath": ["p1"]})["status"] == "fail"
    table[("comp", "p1")] = (Fraction(1), Fraction(1), 0, 2, 0)
    assert gate.composite(table, **common, panels={"forward:a:livemath": ["p1"]})["status"] == "pass"
    table[("comp", "y1")] = table[("comp", "y2")] = (Fraction(0), Fraction(0), 0, 1, 0)
    assert gate.composite(table, **common)["status"] == "fail"
    margins = {"b": Fraction(2), "a": Fraction(2), "c": Fraction(5, 2)}
    assert gate.priority(margins) == ["c", "a", "b"]
    assert gate.accepted([]) == [] and gate.accepted(["b"]) == ["b"]
    assert gate.accepted(["c", "a", "b"], "pass") == ["c", "a", "b"]
    assert gate.accepted(["c", "a", "b"], "fail") == ["c"] and gate.accepted(["c", "a"], "undetermined") == ["c"]
    with pytest.raises(ValueError):
        gate.accepted(["a", "b"])


def test_v3_a_rule_left_with_fewer_than_four_trigger_items_after_the_exclusion_is_undetermined():
    table = _table("pass")
    assert _verdict(table, min_trigger=4)["status"] == "pass"
    short = gate.verdict(table, arm="rule", parent="parent", controls=CONTROLS, trigger=ITEMS["trigger"][:3],
                         rest=ITEMS["rest"], tolerance=2, regression={}, min_trigger=4)
    assert short == {"status": "undetermined", "margin": 0, "priority": 0,
                     "criteria": {"trigger_after_exclusion": 3}}
    members = [{"id": "a", "trigger": ITEMS["trigger"][:2]}, {"id": "b", "trigger": ITEMS["trigger"][2:]}]
    found = gate.composite(table, arm="rule", parent="parent", members=members, rest=ITEMS["rest"], tolerance=2,
                           regression={}, min_trigger=4)
    assert found == {"status": "undetermined", "criteria": {"trigger_after_exclusion": {"a": 2, "b": 2}}}
    assert gate.composite(table, arm="rule", parent="parent", members=members, rest=ITEMS["rest"], tolerance=2,
                          regression={})["status"] == "pass"  # no floor without the caller's minimum


def test_v3_a_rule_s_evidence_items_leave_c2_but_still_count_in_its_unknown_share():
    table = _table("pass", unknown_rule_rest=4)  # the rule's 4 unknown runs of 28: more than 10%
    assert _verdict(table)["status"] == "undetermined"
    held, rest = ITEMS["rest"][:4], ITEMS["rest"][4:]
    kept = dict(arm="rule", parent="parent", controls=CONTROLS, trigger=ITEMS["trigger"], rest=rest, tolerance=2,
                regression={})
    assert gate.verdict(table, **kept)["status"] == "pass"  # dropping the items altogether would hide the unknowns
    assert gate.verdict(table, **kept, held=held)["status"] == "undetermined"
    members = [{"id": "a", "trigger": ITEMS["trigger"][:2]}, {"id": "b", "trigger": ITEMS["trigger"][2:]}]
    together = dict(arm="rule", parent="parent", members=members, rest=rest, tolerance=2, regression={})
    assert gate.composite(table, **together)["status"] == "pass"
    assert gate.composite(table, **together, held=held)["status"] == "undetermined"
    with pytest.raises(ValueError):  # a held item is read by no criterion
        gate.verdict(table, **{**kept, "rest": ITEMS["rest"]}, held=held)


def test_the_merged_subset_is_fixed_by_priority_and_length_before_the_composition_round():
    sizes = {"c": 9000, "a": 10000, "b": 4000}
    parent = 2000

    def size(rules):
        return parent + sum(sizes[r] for r in rules)

    # c fits, a would exceed 20,000 bytes together with c and is skipped, b still fits
    assert gate.fitting_subset(["c", "a", "b"], size) == ["c", "b"]
    assert gate.fitting_subset([], size) == []
    with pytest.raises(ValueError):
        gate.fitting_subset(["c"], lambda rules: 30000)


def test_placebo_passage_lets_each_control_play_the_rule_for_description_only():
    table = _table("pass", control_trigger="pass")
    table.update({("c0", i): (Fraction(1), Fraction(1), 0, 2, 0) for i in ITEMS["trigger"]})
    passage = gate.placebo_passage(table, CONTROLS, {"rule": ITEMS["trigger"]}, "parent")
    assert passage["c0"]["rule"] is True and passage["c1"]["rule"] is False
