"""coevo5 pre-launch texts (registration §0, §1, §6): the existing instruction prompt and cards copied verbatim, the
two new cards quoting the frozen solver's instructions, one call per instruction, and two attempts per rubric."""
from pathlib import Path

from scripts import generate_zero_shot_skill as generator
from skillopt.coevo5 import texts
from skillopt.coevo5.examiner import GENERAL
from skillopt.coevo5.protocol import ORDER, TITLES
from tests.coevo5_fakes import roles, undelivered

BACKENDS = Path(__file__).resolve().parents[1] / "skillopt" / "continual_eval" / "backends.py"
TAG = {"name": "answer_tag_present", "params": {}}


def _item(n, letter="R", check=None):
    return {"id": "%s%d" % (letter, n), "text": "Criterion %d." % n, "check": check, "basis": "The card states it."}


def test_the_existing_prompt_and_cards_are_copied_verbatim():
    assert texts.INSTRUCTION_SYSTEM == generator.SYSTEM and set(texts.CARDS) == set(ORDER)
    for bench in ("searchqa", "officeqa", "livemath"):
        assert texts.CARDS[bench] == generator.TASK_CARDS[bench]
        assert texts.instruction_prompt(bench) == generator.prompt(bench)


def test_the_new_cards_quote_the_frozen_solver_instructions():
    source = BACKENDS.read_text(encoding="utf-8")
    quoted = {"spreadsheetbench": ("Solve the supplied task using only the supplied public information.",
                                   "Return one complete Python program in a ```python code block."),
              "alfworld": ("Act in the text environment. Return a single action inside <action>...</action>.",)}
    for bench, sentences in quoted.items():
        for sentence in sentences:
            assert '"%s"' % sentence in texts.CARDS[bench] and sentence in source


def test_an_instruction_reply_is_kept_as_the_existing_generator_keeps_it():
    for reply in ("- Read the question.\n", "```markdown\n- Use the context.\n```", "  - A\n- B  ", "```\n```x"):
        assert texts.instruction_text(reply) == generator.skill_text(reply)
    assert texts.instruction_text("  \n") is None and texts.instruction_text("```\n```") is None


def test_an_instruction_is_written_by_one_plain_call(tmp_path):
    role, script = roles(tmp_path, ["- Find the row first.\n- Then compute."])
    assert texts.write_instruction(role, "alfworld", label="pre/alfworld") == "- Find the row first.\n- Then compute.\n"
    assert script.seen == [(generator.SYSTEM, "Public task card:\n\n" + texts.CARDS["alfworld"])]
    assert [(c["role"], c["valid"]) for c in role.calls] == [("instruction_writer", True)]
    role, _ = roles(tmp_path, [undelivered()] * 3)
    assert texts.write_instruction(role, "spreadsheetbench", label="pre/sheet") is None
    assert role.count("pre/sheet") == 1 and len(role.calls[0]["sends"]) == 3  # resent identically, not regenerated


def test_a_rubric_takes_the_first_valid_of_two_replies(tmp_path):
    good = {"items": [_item(1, check=TAG), _item(2)]}
    role, script = roles(tmp_path, [{"items": [_item(1, "G")]}, good])
    assert texts.write_rubric(role, "officeqa", label="pre/rubric/officeqa") == {"bench": "officeqa",
                                                                                 "items": good["items"]}
    assert [(c["label"], c["valid"]) for c in role.calls] == [("pre/rubric/officeqa/attempt1", False),
                                                              ("pre/rubric/officeqa/attempt2", True)]
    system, payload = script.seen[0]
    assert "ids R1, R2" in system and payload == {"rubric": TITLES["officeqa"], "task_card": texts.CARDS["officeqa"]}


def test_two_invalid_rubric_replies_give_none(tmp_path):
    role, _ = roles(tmp_path, ["not json", {"items": [_item(1)] * 2}])
    assert texts.write_rubric(role, "livemath", label="pre/rubric/livemath") is None
    assert role.count("pre/rubric/livemath/") == 2


def test_a_reply_without_an_item_s_basis_or_with_another_key_is_not_a_rubric(tmp_path):
    """The two SpreadsheetBench replies of 10/17: an extra top-level key, items without their basis; the prompt names
    the four keys of every item and the single key of the reply (§25)."""
    bare = {k: v for k, v in _item(1).items() if k != "basis"}
    role, script = roles(tmp_path, [{"items": [_item(1)], "prompt": "Write the rubric."}, {"items": [bare]}])
    assert texts.write_rubric(role, "spreadsheetbench", label="pre/rubric/spreadsheetbench") is None
    assert [c["reason"] for c in role.calls] == ["invalid:fields", "invalid:Malformed rubric item"]
    assert 'single key "items"' in script.seen[0][0] and "id, text, check and basis" in script.seen[0][0]


def test_the_general_rubric_is_written_from_all_five_cards(tmp_path):
    role, script = roles(tmp_path, [{"items": [_item(1, "G")]}])
    assert texts.write_rubric(role, GENERAL, label="pre/rubric/general")["bench"] == GENERAL
    system, payload = script.seen[0]
    assert "ids G1, G2" in system and payload["task_cards"] == {TITLES[b]: texts.CARDS[b] for b in ORDER}
