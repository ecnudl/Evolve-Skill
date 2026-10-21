"""coevo5 leakage checks (registration §9, §4 step 5b): the mechanical checks against one bench's training pool --
shared 8-grams outside template text, reference answers by type -- and the adjudicator's fixed verdict."""
import pytest

from skillopt.coevo5.leakage import ADJUDICATE_SYSTEM, Corpus, adjudicate, findings, mechanical, normalize, surface
from tests.coevo5_fakes import reply, roles

PAD = 30  # unrelated items: with them, an 8-gram of one item is in under 5% of the corpus (not template text)


def _item(benchmark, task_id, public, private=None):
    return {"benchmark": benchmark, "task_id": task_id, "family_id": task_id, "part": "train", "public": public,
            "private": private or {}}


def _unique(n):
    """Ten words no other item shares."""
    return " ".join("w%dx%d" % (n, k) for k in range(10))


def _qa(benchmark, questions_and_answers, *, pad=PAD):
    """Pool items: SearchQA private {"answers": [...]}, OfficeQA private {"answer": ...}; ``pad`` unrelated items."""
    rows = list(questions_and_answers) + [(_unique(1000 + n), "x") for n in range(pad)]
    items = []
    for n, (question, answer) in enumerate(rows):
        private = ({"answers": answer if isinstance(answer, list) else [answer]} if benchmark == "searchqa"
                   else {"answer": answer})
        items.append(_item(benchmark, "t%d" % n, {"question": question, "context": "ctx"}, private))
    return items


def _choices(*options):
    return "\n\n".join("%s. %s" % (label, text) for label, text in zip("ABCDE", options))


def _livemath(rows, *, pad=PAD):
    rows = list(rows) + [(_unique(1000 + n), _choices("p", "q", "r", "s", "t"), "A") for n in range(pad)]
    return [_item("livemath", "m%d" % n, {"question": q, "choices": c}, {"answer": a})
            for n, (q, c, a) in enumerate(rows)]


# ------------------------------------------------------------------------------------------- normalization
def test_normalization_folds_width_and_case_and_turns_punctuation_and_symbols_into_spaces():
    assert normalize("ＡＢＣ１ Hello,   World!") == "abc1 hello world"
    assert normalize("$5 + 3% = 8—ok\t(yes)") == "5 3 8 ok yes"
    assert normalize("  ") == ""


def test_the_surface_is_the_question_with_context_options_instruction_or_alfworld_task_text():
    assert surface("searchqa", _item("searchqa", "a", {"question": "Q", "context": ["s1", "s2"]})) == "Q\ns1\ns2"
    assert surface("officeqa", _item("officeqa", "a", {"question": "Q", "context": "page"})) == "Q\npage"
    livemath = _item("livemath", "a", {"question": "Q", "choices": _choices("1", "2", "3", "4", "5")})
    assert surface("livemath", livemath) == "Q\n" + _choices("1", "2", "3", "4", "5")
    sheet = _item("spreadsheetbench", "a", {"instruction": "Sum column B", "input_files": [], "answer_position": "C1"})
    assert surface("spreadsheetbench", sheet) == "Sum column B"
    game = _item("alfworld", "a", {"game_file": "/data/g/game.tw-pddl"})
    assert surface("alfworld", game, task_text="Your task is to: put a mug in the sink.") == \
        "Your task is to: put a mug in the sink."
    with pytest.raises(ValueError):
        surface("alfworld", game)
    with pytest.raises(ValueError):
        surface("kor", game)


# ----------------------------------------------------------------------------------------------- check 1
def test_eight_consecutive_words_of_a_question_are_a_leak_seven_are_not():
    question = "Which river flows through the ancient city of Babylon in Mesopotamia today"
    corpus = Corpus("searchqa", _qa("searchqa", [(question, "Euphrates")]))
    assert mechanical("Remember: which RIVER flows, through the ancient city of Babylon!", corpus) == "shared_8gram"
    assert mechanical("Remember which river flows through the ancient city.", corpus) is None


def test_eight_words_of_the_supplied_context_are_a_leak_too():
    items = _qa("officeqa", [(_unique(0), "x")])
    items[0]["public"]["context"] = "Table 3. Receipts of the general fund rose sharply in the second quarter of 1952."
    snippets = _qa("searchqa", [(_unique(0), "x")])
    snippets[0]["public"]["context"] = ["unrelated", "the old lighthouse keeper rowed across the bay every night"]
    assert mechanical("Note: receipts of the general fund rose sharply in the second quarter.",
                      Corpus("officeqa", items)) == "shared_8gram"
    assert mechanical("The old lighthouse keeper rowed across the bay every night.",
                      Corpus("searchqa", snippets)) == "shared_8gram"


def test_an_eight_gram_in_at_least_five_percent_of_the_items_is_template_text():
    template = "read the snippets carefully and answer with a name"
    single = "the dragon of the north sleeps under frozen lakes"
    questions = [_unique(n) for n in range(40)]
    questions[0] += " " + template
    questions[1] += " " + template  # 2 of 40 = 5%: template text
    questions[2] += " " + single  # 1 of 40 = 2.5%: an item's own words
    corpus = Corpus("searchqa", _qa("searchqa", [(q, "x") for q in questions], pad=0))
    assert corpus.size == 40
    assert mechanical("Always " + template + ".", corpus) is None
    assert mechanical("Note that " + single + ".", corpus) == "shared_8gram"


def test_a_lone_item_is_all_template_text():
    """With fewer than 20 items every 8-gram is in at least 5% of them: check 1 cannot fire (the real pools have at
    least 30 items)."""
    question = "Which river flows through the ancient city of Babylon in Mesopotamia today"
    corpus = Corpus("searchqa", _qa("searchqa", [(question, "x")], pad=0))
    assert mechanical("Which river flows through the ancient city of Babylon?", corpus) is None


# ------------------------------------------------------------------------------------------ text answers
def test_a_multiword_answer_counts_only_as_a_contiguous_whole_word_run():
    corpus = Corpus("searchqa", _qa("searchqa", [(_unique(0), ["Abraham Lincoln", "Honest Abe"])]))
    assert mechanical("Presidents such as abraham lincoln are common answers.", corpus) == "answer_text"
    assert mechanical("Prefer HONEST-ABE style nicknames.", corpus) == "answer_text"
    assert mechanical("Abraham and Lincoln are separate words here.", corpus) is None
    assert mechanical("Abraham lincolnshire is not a whole-word match.", corpus) is None


def test_a_single_word_answer_needs_five_characters_and_a_whole_word():
    corpus = Corpus("searchqa", _qa("searchqa", [(_unique(0), "Paris"), (_unique(1), "Rome")]))
    # v2 §7: a single-word answer is its own reason, last in order -- the stage adjudicates it instead of dropping
    assert mechanical("Capitals like Paris are frequent.", corpus) == "answer_word"
    assert findings("Capitals like Paris are frequent.", corpus) == {"answer_word": ["paris"]}
    assert mechanical("Capitals like Rome are frequent.", corpus) is None  # four characters: not checked
    assert mechanical("Parisian cuisine is not the answer.", corpus) is None


def test_every_mechanical_hit_is_found_and_a_word_hit_never_hides_another():
    corpus = Corpus("searchqa", _qa("searchqa", [(_unique(0), "Paris"), (_unique(1), "Eiffel Tower")]))
    text = "Paris has the eiffel tower."
    assert findings(text, corpus) == {"answer_text": True, "answer_word": ["paris"]}
    assert mechanical(text, corpus) == "answer_text"


def test_the_colliding_items_are_at_most_three_in_a_seeded_order():
    corpus = Corpus("searchqa", _qa("searchqa", [(_unique(n) + " " + "y" * 700, "Paris") for n in range(5)]))
    shown = corpus.evidence(["paris"])
    assert len(shown) == 3 and all(len(e["question"]) == 600 and e["answer"] == "Paris" for e in shown)
    assert corpus.evidence(["paris"]) == shown and corpus.evidence(["lyon"]) == []


def test_the_adjudicator_sees_the_colliding_items_with_the_rule(tmp_path):
    role, script = roles(tmp_path, [{"verdict": "no", "reason": "incidental"}, {"verdict": "yes", "reason": "gives"}])
    colliding = [{"question": "Which city?", "answer": "Paris"}]
    assert adjudicate(role, "Name the capital city.", label="a", colliding=colliding) is True
    assert script.seen[0] == (ADJUDICATE_SYSTEM, {"rule": "Name the capital city.", "colliding_items": colliding})
    assert adjudicate(role, "Answer Paris.", label="b") is False
    assert script.seen[1][1] == {"rule": "Answer Paris."}  # no collision: the rule alone


def test_officeqa_text_answers_are_checked_as_text():
    corpus = Corpus("officeqa", _qa("officeqa", [(_unique(0), "Federal Reserve Banks")]))
    assert mechanical("Look for the federal reserve banks line.", corpus) == "answer_text"
    assert mechanical("Look for the federal line.", corpus) is None


# --------------------------------------------------------------------------------------- numeric answers
def test_a_number_equal_to_an_officeqa_reference_is_a_leak_whatever_its_separators():
    corpus = Corpus("officeqa", _qa("officeqa", [(_unique(0), "1,234.5"), (_unique(1), "12.5%"),
                                                 (_unique(2), "$0.0500")]))
    assert mechanical("A typical total is 1234.50 here.", corpus) == "answer_number"
    assert mechanical("A typical total is 1,234.5 here.", corpus) == "answer_number"
    assert mechanical("Rates near 12.5 percent occur.", corpus) == "answer_number"
    assert mechanical("A share of 0.05 is small.", corpus) == "answer_number"  # "0.0500": 3 significant digits
    assert mechanical("A typical total is 1234.6 here.", corpus) is None


@pytest.mark.parametrize("written", [".125", "0.125", "0.1250", "1.25e-1", "125E-3", "-0.125", "−.125", "1/8",
                                     "1 / 8", "+0.125"])
def test_every_spelling_of_a_reference_value_is_a_leak(written):
    corpus = Corpus("officeqa", _qa("officeqa", [(_unique(0), "0.125")]))
    assert mechanical("A typical ratio is %s here." % written, corpus) == "answer_number"


@pytest.mark.parametrize("written", ["0.126", "1/9", "1.25e-2", "1/8,000", "2.5/20", "1e999999"])
def test_other_values_are_not_a_leak(written):
    corpus = Corpus("officeqa", _qa("officeqa", [(_unique(0), "0.125")]))
    assert mechanical("A typical ratio is %s here." % written, corpus) is None


def test_references_with_fewer_than_three_significant_digits_are_not_checked():
    corpus = Corpus("officeqa", _qa("officeqa", [(_unique(0), "45"), (_unique(1), "-3.0"), (_unique(2), "0.07")]))
    assert mechanical("Values like 45, -3.0 and 0.07 appear.", corpus) is None


def test_four_digit_years_in_the_rule_are_not_checked():
    corpus = Corpus("officeqa", _qa("officeqa", [(_unique(0), "2019"), (_unique(1), "1850")]))
    assert mechanical("Bulletins from 2019 are monthly.", corpus) is None
    assert mechanical("A value of 2019.0 is suspicious.", corpus) == "answer_number"
    assert mechanical("Records from 1850 are rare.", corpus) == "answer_number"  # outside 1900-2030


def test_numbers_are_checked_on_officeqa_only():
    corpus = Corpus("searchqa", _qa("searchqa", [(_unique(0), "1234")]))
    assert mechanical("The figure 1,234 appears.", corpus) is None  # a one-word answer of four characters


# ------------------------------------------------------------------------------------------------ LiveMath
def test_the_content_of_the_correct_livemath_option_is_a_leak_as_a_substring():
    corpus = Corpus("livemath", _livemath([(_unique(0), _choices("1", "2", r"\frac{\pi}{4}", "3", "4"), "C"),
                                           (_unique(1), _choices("0", "x+1", "2", "3", "4"), "D")]))
    assert mechanical(r"Integrals often equal \frac{\pi}{4}.", corpus) == "option_text"
    assert mechanical("Integrals often equal frac pi4.", corpus) == "option_text"  # whitespace-free substring
    assert mechanical("The answer is usually C or D; choose 3 carefully.", corpus) is None  # letters, a short option
    assert mechanical("Use x+1 when unsure.", corpus) is None  # a wrong option's text


def test_livemath_options_are_part_of_the_surface():
    choices = _choices("the series converges absolutely for every real value of x", "b1", "c1", "d1", "e1")
    corpus = Corpus("livemath", _livemath([("Decide.", choices, "B")]))
    assert mechanical("Check whether the series converges absolutely for every real value first.",
                      corpus) == "shared_8gram"


# ------------------------------------------------------------------------- SpreadsheetBench and ALFWorld
def test_spreadsheetbench_has_the_eight_gram_check_only():
    instruction = "Fill column D with the product of column B and column C for every row"
    rows = [instruction] + [_unique(1000 + n) for n in range(PAD)]
    items = [_item("spreadsheetbench", "s%d" % n, {"instruction": text, "input_files": [], "answer_position": "D2"},
                   {"answer": "Total revenue", "answers": ["Total revenue"]}) for n, text in enumerate(rows)]
    corpus = Corpus("spreadsheetbench", items)
    assert mechanical("Always fill column D with the product of column B and column C.", corpus) == "shared_8gram"
    assert mechanical("Write total revenue labels in bold.", corpus) is None


def test_alfworld_compares_with_the_task_texts_and_skips_items_without_one():
    room = "You are in the middle of a room. Looking quickly around you, you see a cabinet 1. Your task is to: "
    items = [_item("alfworld", "g%d" % n, {"game_file": "/data/g%d/game.tw-pddl" % n}) for n in range(3 + PAD)]
    texts = {"g0": room + "put a clean mug in the coffee machine.",
             "g1": room + "heat some egg and put it in the fridge.",
             **{"g%d" % n: room + _unique(n) for n in range(3, 3 + PAD)}}  # g2: no initial observation
    corpus = Corpus("alfworld", items, alfworld_texts=texts)
    assert corpus.size == 2 + PAD
    assert mechanical("Your task is to put a clean mug in the coffee machine quickly.", corpus) == "shared_8gram"
    assert mechanical("You are in the middle of a room, looking quickly around you.", corpus) is None  # template
    assert mechanical("Clean an object at the sinkbasin before putting it anywhere.", corpus) is None


def test_the_first_failing_check_decides():
    question = "Name the author of the novel about the white whale and the obsessed captain"
    corpus = Corpus("searchqa", _qa("searchqa", [(question, "Herman Melville")]))
    assert mechanical("The author of the novel about the white whale is Herman Melville.", corpus) == "shared_8gram"
    assert mechanical("Herman Melville wrote sea novels.", corpus) == "answer_text"


def test_a_corpus_holds_one_benchs_items():
    with pytest.raises(ValueError):
        Corpus("officeqa", _qa("searchqa", [(_unique(0), "x")]))


# ---------------------------------------------------------------------------------------------- adjudicator
@pytest.mark.parametrize("answer, keep, valid", [
    ({"verdict": "no", "reason": "General advice on answer format."}, True, True),
    ({"verdict": "yes", "reason": "It names one question's answer."}, False, True),
    ({"verdict": "maybe", "reason": "Unsure."}, False, False),
    ({"verdict": "no"}, False, False),  # no reason
    ({"verdict": "no", "reason": "x" * 301}, False, False),  # reason too long
    ("no", False, False),  # not JSON
    (reply({"verdict": "no", "reason": "ok"}, finish="length"), False, False),  # truncated: no reply
])
def test_the_adjudicator_keeps_a_rule_only_on_a_valid_no(tmp_path, answer, keep, valid):
    role, script = roles(tmp_path, [answer])
    assert adjudicate(role, "Give the final number without units.", label="s1/leak/s1-r1") is keep
    system, payload = script.seen[0]
    assert system == ADJUDICATE_SYSTEM and payload == {"rule": "Give the final number without units."}
    assert role.calls[0]["role"] == "leak_adjudicate" and role.calls[0]["valid"] is valid
