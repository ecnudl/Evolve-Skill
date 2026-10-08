"""Fresh KOR probes: synthetic rule texts only, no KOR data and no model calls."""
import re

import pytest

from scripts import make_kor_probes
from skillopt.applicability import kor, kor_probes
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import write_json
from skillopt.validator_pilot.api import digest

ONE = "Please ensure the answer is a single number and wrap it in double square brackets, like this: [[your answer]]."
FRACTION = ("If the answer is a fraction, write it in 'a/b' text format.Decimals are not allowed.\n"
            "Please wrap the answer in double square brackets, like this: [[your answer]].")
COMPLEX = ("If the answer is a complex number, write it in the form x + yi.\n"
           "Please wrap the answer in double square brackets, like this: [[your answer]].")
MATRIX = ("A=\n\\[\n\\begin{pmatrix}\n  1 & 2 \\\\\n  3 & 4\n\\end{pmatrix}\n\\]\nB=\n\\[\n\\begin{pmatrix}\n"
          "  0 & 1 \\\\\n  2 & 3\n\\end{pmatrix}\n\\]\nCompute A<OP>B.\n"
          "The answer is a matrix, write it in this form:[[((a,b),(c,d))]].")
TEMPLATES = kor._PUZZLE_TEMPLATES
ENC = ("\n\nPlease provide the encrypted answer, encapsulated in double square brackets. "
       "For example, the format should be: [[encrypted answer]].")
DEC = ENC.replace("encrypted", "decrypted")


def ciphers(plain, cipher, fields=""):
    """One public question per direction, as a cipher panel has."""
    middle = "\n" + fields if fields else ""
    return f'Plaintext: "{plain}"{middle}{ENC}', f'Ciphertext: "{cipher}"{middle}{DEC}'


QUESTIONS = {
    "operation:multiple": "Compute 4※7.\n" + ONE,
    "operation:circle": "Compute 2○3.\n" + ONE,
    "operation:angle": "Compute ⟨1,2,3,4⟩.\n" + ONE,
    "operation:venus_mars": "Compute (3♀5)♂2.\n" + ONE,
    "operation:sqrt": "Compute 9②(4①2).\n" + ONE,
    "operation:log": "Compute 2￠8.\n" + FRACTION,
    "operation:complex_pair": "Compute (3⊕4)+(2⊕1).\n" + COMPLEX,
    "operation:complex_square": "Compute (4◎5)+(2◎3).\n" + COMPLEX,
    "operation:matrix_power": MATRIX.replace("<OP>", "&"),
    "operation:matrix_affine": MATRIX.replace("<OP>", "€"),
    "puzzle:twenty_four": "The four randomly selected numbers are:\n1 2 3 4.\n" + TEMPLATES["puzzle:twenty_four"],
    "puzzle:sudoku": "X X\nX X\n" + TEMPLATES["puzzle:grid_letters"],
    "puzzle:skyscrapers": "Grid Layout:\n\t1\t2\t\n1\tX\tX\t2\n2\tX\tX\t1\n\t2\t1\n" + TEMPLATES["puzzle:skyscrapers"],
    "puzzle:hidato": "1 X\nX 4\n" + TEMPLATES["puzzle:hidato"],
    "cipher:affine": ciphers("O", "L"),
    "cipher:solitaire": ciphers("V", "H"),
    "cipher:grid_shift": ciphers("B", "S"),
    "cipher:porta": ciphers("O", "A", "Key: GVIE"),
    "cipher:disks": ciphers("R", "X", "period: 3\nincrement: 1"),
    "cipher:morse_pairs": ciphers("AB", "415."),
    "cipher:rail_columns": ciphers("ABC", "A*B*C***"),
    "cipher:sbox_blocks": ciphers("B", "3B9C9986938C9784"),
    "cipher:ascii_scale": ciphers("G", "780,792"),
}


def panel(monkeypatch, *, drop=None):
    rules = {handler: "synthetic rule for " + handler for handler in QUESTIONS}
    monkeypatch.setattr(kor, "RULES", {kor.rule_hash(rule): handler for handler, rule in rules.items()})
    tasks = {}
    for index, (handler, questions) in enumerate(QUESTIONS.items()):
        if handler == drop:
            continue
        category, rule_id = kor.RULE_IDS[handler]
        for number, question in enumerate((questions,) if isinstance(questions, str) else questions):
            task_id = f"{category}:{index}.{number}"
            tasks[task_id] = {"task_id": task_id, "family_id": task_id, "partition": "development", "project_id": None,
                              "public": {"rule": rules[handler], "question": question},
                              "private": {"answer": "[[0]]", "category": category, "rule_id": rule_id}}
    return tasks


def test_every_probe_is_new_and_qualified(monkeypatch):
    tasks = panel(monkeypatch)
    probes = kor_probes.generate(tasks, per_rule=6, seed=7)
    assert len(probes) == 6 * len(kor_probes.GENERATED) and set(kor_probes.GENERATED) == set(QUESTIONS)
    # Cipher questions of different rules may read alike; a task is its rule plus its question.
    questions = [(p["public"]["rule"], " ".join(p["public"]["question"].split())) for p in probes]
    assert len(set(questions)) == len(questions)
    assert not set(questions) & {(t["public"]["rule"], " ".join(t["public"]["question"].split()))
                                 for t in tasks.values()}
    for probe in probes:
        rule, question = probe["public"]["rule"], probe["public"]["question"]
        assert kor.verify(rule, question, probe["private"]["reference"])["status"] == "pass"
        assert kor.verify(rule, question, probe["private"]["mutated"])["status"] == "fail"
        assert rule == "synthetic rule for " + probe["handler"]
        assert (probe["private"]["category"], probe["private"]["rule_id"]) == kor.RULE_IDS[probe["handler"]]
    assert kor_probes.generate(tasks, per_rule=6, seed=7) == probes
    assert kor_probes.generate(tasks, per_rule=6, seed=8) != probes


def test_a_registered_rule_missing_from_the_panel_is_refused(monkeypatch):
    with pytest.raises(kor_probes.ProbeError, match="missing from the panel"):
        kor_probes.generate(panel(monkeypatch, drop="puzzle:sudoku"), per_rule=1, seed=1)


def study(tmp_path, tasks):
    write_json(tmp_path / "panel.json", {"tasks": list(tasks.values())})
    plan = seal({"repeats": 2, "config": {"panels": {"korbench": str(tmp_path / "panel.json")}},
                 "tasks": [{"benchmark": "korbench", "task_id": k, "task_hash": digest(t)} for k, t in tasks.items()]})
    write_json(tmp_path / "noskill/plan.json", plan)
    protocol = seal({"references": {"korbench": {"root": str(tmp_path / "noskill"), "plan_hash": plan["record_hash"]}}})
    write_json(tmp_path / "study/protocol.json", protocol)
    return tmp_path / "study"


def test_build_binds_the_frozen_panel_and_hides_private_fields(tmp_path, monkeypatch):
    tasks = panel(monkeypatch)
    value = make_kor_probes.build(study(tmp_path, tasks), per_rule=2, seed=3)
    assert len(value["probes"]) == 2 * len(QUESTIONS) and value["model_api_calls"] == 0
    assert value["scored_by"] == "label_free_verifier_only" and value["verifier"] == kor.VERSION
    seen = []
    monkeypatch.setattr(kor_probes, "generate", lambda public, **kw: seen.append(public) or [])
    make_kor_probes.build(study(tmp_path / "again", tasks), per_rule=1, seed=3)
    assert all(set(task) == {"task_id", "public"} for task in seen[0].values())


def test_build_refuses_a_registry_that_disagrees_with_the_panel(tmp_path, monkeypatch):
    tasks = panel(monkeypatch)
    first = next(iter(tasks.values()))
    first["private"]["rule_id"] = "99"
    with pytest.raises(ValueError, match="Rule registry does not match"):
        make_kor_probes.build(study(tmp_path, tasks), per_rule=1, seed=3)


def test_reordered_or_symmetric_inputs_never_re_pose_a_panel_task(monkeypatch):
    tasks = panel(monkeypatch)
    first = {p["handler"]: p for p in kor_probes.generate(tasks, per_rule=1, seed=11)}
    numbers = sorted(int(v) for v in first["puzzle:twenty_four"]["public"]["question"].split("\n")[1].rstrip(".").split())
    sky = [line.split() for line in first["puzzle:skyscrapers"]["public"]["question"].split("The answer")[0]
           .split("Grid Layout:")[1].strip("\n").split("\n")]
    mirrored = ("Grid Layout:\n\t" + "\t".join(sky[0][::-1]) + "\t\n"
                + "\n".join(f"{r[-1]}\t" + "\t".join(r[1:-1]) + f"\t{r[0]}" for r in sky[1:-1])
                + "\n\t" + "\t".join(sky[-1][::-1]) + "\n" + TEMPLATES["puzzle:skyscrapers"])
    for task in tasks.values():
        handler = kor.RULES[kor.rule_hash(task["public"]["rule"])]
        if handler == "puzzle:twenty_four":  # the same four numbers in another order
            task["public"]["question"] = ("The four randomly selected numbers are:\n"
                                          + " ".join(map(str, numbers[::-1])) + ".\n" + TEMPLATES[handler])
        if handler == "puzzle:skyscrapers":  # the mirror image of the first probe
            task["public"]["question"] = mirrored
    again = {p["handler"]: p for p in kor_probes.generate(tasks, per_rule=1, seed=11)}
    assert again["puzzle:twenty_four"]["public"]["question"] != first["puzzle:twenty_four"]["public"]["question"]
    assert again["puzzle:skyscrapers"]["public"]["question"] != first["puzzle:skyscrapers"]["public"]["question"]
    for handler in ("puzzle:twenty_four", "puzzle:skyscrapers"):
        keys = {kor_probes._canonical(handler, t["public"]["question"]) for t in tasks.values()
                if kor.RULES[kor.rule_hash(t["public"]["rule"])] == handler}
        assert kor_probes._canonical(handler, again[handler]["public"]["question"]) not in keys


def test_an_exhausted_probe_space_fails_in_bounded_time(monkeypatch):
    # Same numbers and operators in any order count as one task: the circle rule has fewer than 80.
    with pytest.raises(kor_probes.ProbeError, match="probe space exhausted"):
        kor_probes.generate(panel(monkeypatch), per_rule=80, seed=1)


def test_equivalent_operator_spellings_are_one_task(monkeypatch):
    tasks = panel(monkeypatch)
    spellings = [("Compute (9⊕8)-(5⊕7).", "Compute (9⊕8)−(5⊕7)."), ("Compute (2⊕3)*(4⊕1).", "Compute (2⊕3)×(4⊕1)."),
                 ("Compute (2⊕3)\\times(4⊕1).", "Compute (2⊕3)·(4⊕1)."), ("Compute 8/2.", "Compute 8÷2.")]
    for ascii_form, unicode_form in spellings:
        assert (kor_probes._canonical("operation:complex_pair", ascii_form + "\n" + COMPLEX)
                == kor_probes._canonical("operation:complex_pair", unicode_form + "\n" + COMPLEX))
    # End to end: an ASCII spelling of a generated probe in the panel excludes that probe.
    probe = next(p for p in kor_probes.generate(tasks, per_rule=8, seed=20261004)
                 if p["handler"] == "operation:complex_pair" and ("−" in p["public"]["question"]
                                                                   or "×" in p["public"]["question"]))
    head = probe["public"]["question"].split("\n")[0]
    for task in tasks.values():
        if kor.RULES[kor.rule_hash(task["public"]["rule"])] == "operation:complex_pair":
            task["public"]["question"] = head.replace("−", "-").replace("×", "*") + "\n" + COMPLEX
    again = kor_probes.generate(tasks, per_rule=8, seed=20261004)
    assert all(p["public"]["question"].split("\n")[0] != head for p in again)


def test_presentation_variants_share_a_key():
    same = [("operation:circle", "Compute 4○5.", ("Compute 4.0○5.", "Compute 04○5.", "Compute (+4)○5.",
                                                    "Compute 5○4.")),
            ("operation:multiple", "Compute 12※2※18.", ("Compute 1\\,2※2※18.", "Compute 18※2※12.")),
            ("operation:complex_pair", "Compute (6⊕4)×(6⊕3).", ("Compute (6⊕4)(6⊕3).", "Compute (6⊕4)*(6⊕3)."))]
    for handler, original, variants in same:
        key = kor_probes._canonical(handler, original + "\n" + ONE)
        assert all(kor_probes._canonical(handler, v + "\n" + ONE) == key for v in variants)
    hidato = "1 X 3\nX 5 X\n7 X 9\n" + TEMPLATES["puzzle:hidato"]
    for variant in ("01 X 3\nX 5 X\n7 X 9\n", "7 X 1\nX 5 X\n9 X 3\n", "9 X 7\nX 5 X\n3 X 1\n"):  # pad, rotate, reverse
        assert kor_probes._canonical("puzzle:hidato", variant + TEMPLATES["puzzle:hidato"]) \
            == kor_probes._canonical("puzzle:hidato", hidato)
    rows = ["5 3 X", "6 X X", "X 9 8"]
    sudoku = "\n".join(rows) + "\n" + TEMPLATES["puzzle:grid_letters"]
    rotated = ["X 6 5", "9 X 3", "8 X X"]  # rotated a quarter turn, then digits renamed below
    renamed = "\n".join(r.replace("5", "a").replace("3", "5").replace("a", "3") for r in rotated)
    assert kor_probes._canonical("puzzle:sudoku", renamed + "\n" + TEMPLATES["puzzle:grid_letters"]) \
        == kor_probes._canonical("puzzle:sudoku", sudoku)


def test_a_respelled_panel_task_excludes_its_probe(monkeypatch):
    tasks = panel(monkeypatch)
    first = next(p for p in kor_probes.generate(tasks, per_rule=1, seed=5) if p["handler"] == "operation:circle")
    head = first["public"]["question"].split("\n")[0]  # e.g. "Compute 7○3."
    respelled = re.sub(r"([0-9]+)", r"\1.0", head, count=1).replace("○", "○ ")
    for task in tasks.values():
        if kor.RULES[kor.rule_hash(task["public"]["rule"])] == "operation:circle":
            task["public"]["question"] = respelled + "\n" + ONE
    again = next(p for p in kor_probes.generate(tasks, per_rule=1, seed=5) if p["handler"] == "operation:circle")
    assert kor_probes._canonical("operation:circle", again["public"]["question"]) \
        != kor_probes._canonical("operation:circle", first["public"]["question"])


def test_cipher_probes_are_reading_independent_and_never_meet_a_panel_message(monkeypatch):
    tasks = panel(monkeypatch)
    probes = [p for p in kor_probes.generate(tasks, per_rule=12, seed=3) if p["handler"].startswith("cipher:")]
    assert len(probes) == 12 * 9
    for probe in probes:
        encrypt, text, _ = kor._cipher_question(probe["public"]["question"])
        answer = probe["private"]["reference"][2:-2]
        plain = text if encrypt else answer
        if probe["handler"] == "cipher:rail_columns" and encrypt:
            assert len(plain) <= 5          # longer plaintexts depend on prose vs worked example
        if probe["handler"] == "cipher:sbox_blocks":
            assert len(plain) <= 8 and (not encrypt or "F" not in answer)
        if probe["handler"] == "cipher:disks" and not encrypt:
            assert "J" not in text
        for task in tasks.values():
            if task["public"]["rule"] == probe["public"]["rule"]:
                assert not kor_probes._keys(probe["handler"], task["public"]["question"]) \
                    & kor_probes._keys(probe["handler"], probe["public"]["question"])
    directions = {kor._cipher_question(p["public"]["question"])[0] for p in probes}
    assert directions == {True, False}


def test_a_cipher_probe_inverse_to_a_panel_task_is_excluded(monkeypatch):
    tasks = panel(monkeypatch)
    # The panel encrypts O (affine: O -> E); a probe decrypting E would re-pose it in reverse.
    draws = iter([("decrypt", "E", "O"), ("decrypt", "M", None)])

    def probe(handler, rng, templates):
        kind, text, _ = next(draws)
        answer = "".join(kor._AFFINE[9 * (kor._AFFINE.index(c) - 5) % 26] for c in text)
        return kor_probes._pose(templates[kind], text, {}), answer, "Z" if answer != "Z" else "Y"
    monkeypatch.setattr(kor_probes, "_cipher_probe", probe)
    monkeypatch.setattr(kor_probes, "GENERATED", ("cipher:affine",))
    made = kor_probes.generate(tasks, per_rule=1, seed=1)
    assert [p["public"]["question"].split("\n")[0] for p in made] == ['Ciphertext: "M"']
    assert kor_probes._keys("cipher:affine", 'Plaintext: "O"' + ENC) >= {("cipher:affine", "plain", "O"),
                                                                        ("cipher:affine", "cipher", "E")}


def test_cipher_draws_without_a_mutable_position_or_off_direction_limits(monkeypatch):
    tasks = panel(monkeypatch)
    templates = kor_probes._instructions("cipher:morse_pairs", [t["public"]["question"] for t in tasks.values()
                                                                if t["public"]["rule"].endswith("morse_pairs")])
    draws = iter([(True, "E", {}), (True, "T", {}), (True, "AB", {})])  # E -> "." and T -> "-": nothing to mutate
    monkeypatch.setattr(kor_probes, "_draw", lambda handler, rng: next(draws))
    question, answer, mutated = kor_probes._cipher_probe("cipher:morse_pairs", __import__("random").Random(1), templates)
    assert question.startswith('Plaintext: "AB"') and answer == "415." and mutated != answer
    assert kor_probes._posable("cipher:rail_columns", "HELLOWORLD", "HL#*ERD*LO*LW*O#*", {}, False)
    assert not kor_probes._posable("cipher:rail_columns", "HELLOWORLD", "HL#*ERD*LO*LW*O#*", {}, True)
    cipher = kor_probes._encrypt("cipher:sbox_blocks", "C", {})
    assert "F" in cipher and kor_probes._posable("cipher:sbox_blocks", "C", cipher, {}, False)
    assert not kor_probes._posable("cipher:sbox_blocks", "C", cipher, {}, True)
    assert not kor_probes._posable("cipher:sbox_blocks", "ABCDEFGHI", "", {}, False)  # second block


def test_cipher_decryption_probes_reach_beyond_encryption_limits(monkeypatch):
    probes = kor_probes.generate(panel(monkeypatch), per_rule=30, seed=9)
    decrypted = {p["handler"]: [] for p in probes}
    for p in probes:
        encrypt, text, _ = kor._cipher_question(p["public"]["question"]) if p["handler"].startswith("cipher:") \
            else (True, "", "")
        if not encrypt:
            decrypted[p["handler"]].append((text, p["private"]["reference"][2:-2]))
    assert any(len(plain) > 5 for _, plain in decrypted["cipher:rail_columns"])   # several columns
    assert any("F" in cipher for cipher, _ in decrypted["cipher:sbox_blocks"])
