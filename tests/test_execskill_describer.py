"""The text twin T_F (implementation plan §1 describer.py; registration §5.7, §8.1 T_F table): one pinned-prompt call
per procedure through FakeGLM, the lexicon screen, the +-20 % length band and the frozen hashes."""
from __future__ import annotations

from skillopt.execskill import describer
from skillopt.execskill.package import FIXTURE, Package, with_describer
from skillopt.execskill.protocol import verified
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes import glm_roles, truncated
from tests.test_execskill_replay import NOTE, TRACKER, fixture, source

LABEL = "describer/unit-1/fx-note"
ADVICE = ("The helper looks for the numbers written in the question. Comparing them with the context can show "
          "which quantity the question is about.")


def note_procedure():
    return fixture("fx-note", source(NOTE), ("applies", "before_call"))


def test_one_pinned_call_gives_a_frozen_text_within_the_band(tmp_path):
    roles, glm = glm_roles(tmp_path, [ADVICE])
    procedure = note_procedure()
    sealed = describer.describe(roles, procedure, lengths=[100, 140, 120], label=LABEL, evidence=FIXTURE)
    value = verified(sealed, "description")
    assert value["text"] == ADVICE and value["band"] == "within" and value["target_chars"] == 120
    assert value["text_sha256"] == digest(ADVICE) and value["prompt_sha256"] == describer.DESCRIBER_PROMPT_SHA256
    assert value["request_sha256"] == roles.calls[0]["request_sha256"] and len(roles.calls) == 1
    system, payload = glm.seen[0]
    assert system == describer.DESCRIBER_SYSTEM and payload["target_chars"] == 120
    assert "re.findall" in payload["procedure"]["source"]
    assert describer.texts([sealed]) == {"fx-note": ADVICE}
    package = with_describer(Package((procedure,), "s1", FIXTURE), describer.entries([sealed]))
    assert package.describer == {"fx-note": {"text_sha256": digest(ADVICE),
                                             "prompt_sha256": describer.DESCRIBER_PROMPT_SHA256}}


def test_lexicon_sentences_are_left_out_and_long_texts_are_cut_to_the_band(tmp_path):
    long_reply = ADVICE + " Then answer with the number only. " + " ".join(["It also counts the words."] * 10)
    roles, _ = glm_roles(tmp_path, [long_reply, "Short note."])
    value = describer.describe(roles, note_procedure(), lengths=[120], label=LABEL, evidence=FIXTURE)
    assert value["dropped_sentences"] == 1 and "answer" not in value["text"]
    assert value["band"] == "clipped" and 96 <= value["chars"] <= 144 and value["text"].endswith(".")
    short = describer.describe(roles, note_procedure(), lengths=[120], label=LABEL, evidence=FIXTURE)
    assert short["band"] == "short" and short["text"] == "Short note."


def test_no_reply_and_no_note_hook(tmp_path):
    roles, _ = glm_roles(tmp_path, [truncated(ADVICE)])
    value = describer.describe(roles, note_procedure(), lengths=[], label=LABEL, evidence=FIXTURE)
    assert value["text"] is None and value["reason"] == "no_reply" and value["text_sha256"] is None
    assert describer.texts([value]) == {} and describer.entries([value]) == {}
    state_only = fixture("fx-state", source(TRACKER, GREEDY=False, FORGETFUL=False).replace(
        "def alf_before_step(view, state):", "def before_step(view, state):"), ("applies", "alf_after_step"),
        origin="alfworld", state_bytes=4096)
    calls = len(roles.calls)
    value = describer.describe(roles, state_only, lengths=[], label=LABEL, evidence=FIXTURE)
    assert value["reason"] == "no_note_hook" and value["request_sha256"] is None and len(roles.calls) == calls
