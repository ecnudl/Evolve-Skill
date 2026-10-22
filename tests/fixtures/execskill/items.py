"""Fixture item builders for the execskill tests (plan §7 "Fixture items"; registration §10: engineering fixtures
shaped like the frozen public views, truth computed by code, labelled ``engineering_fixture``, never evidence).

Every item has the pool shape of ``coevo5.data.pool`` -- ``{benchmark, task_id, family_id, part, public, private}``
with the frozen public/private field sets of ``continual_eval.datasets`` -- and ``panel`` wraps items into a
``continual-panel-v1`` panel checked by the frozen ``validate_panel``. Nothing here is real benchmark content.

- ``searchqa_items``: 20 short QA items (question, one context text, answers).
- ``officeqa_items``: 20 table-text pages with arithmetic questions (difference, ratio, percent change, sum over named
  cells); the answer is computed exactly from the table.
- ``livemath_items``: 20 five-option items with a computed true option; every fourth offers the meta option
  ``STRONGER_OPTION`` (the key on two of them); answer letters rotate.
- ``spreadsheetbench_items(root)``: 20 input/answer workbook pairs written with openpyxl under ``root``.
- ``alfworld_games`` / ``alfworld_items(root)``: 12 fake games over 6 rooms and the 7 task-folder prefixes, each
  game file (``json_2.1.1/train/<type>-<object>-None-<receptacle>-<room>/trial_*/game.tw-pddl``) holding its scripted
  episode as JSON: initial observation, admissible commands, the winning plan, ``won_at`` (the step whose observation
  says "You won!"; T <= 10 on the short successful games), the terminal observation, and an ``expert_plan`` /
  ``extra`` block a view must never show.
- ``alfworld_tree(root, rooms, per_room)``: a larger synthetic ``json_2.1.1/train`` layout for supply slicing.
"""
from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

from skillopt.coevo5.protocol import STRONGER_OPTION
from skillopt.continual_eval import datasets

COUNT = 20
EVIDENCE = "engineering_fixture"
TASK_TYPES = ("pick_and_place_simple", "look_at_obj_in_light", "pick_clean_then_place_in_recep",
              "pick_heat_then_place_in_recep", "pick_cool_then_place_in_recep", "pick_two_obj_and_place",
              "pick_and_place_with_movable_recep")
WON = "You won!"


def _item(bench, number, public, private):
    task_id = "fx-%s-%02d" % (bench, number)
    return {"benchmark": bench, "task_id": task_id, "family_id": "%s:%s" % (bench, task_id), "part": "fixture",
            "public": public, "private": private}


def panel(bench, items):
    """A fixture panel of the items, validated by the frozen panel validator."""
    tasks = [{"task_id": i["task_id"], "family_id": i["family_id"], "project_id": "", "partition": "development",
              "public": i["public"], "private": i["private"]} for i in items]
    return datasets.validate_panel({"version": datasets.VERSION, "benchmark": bench,
                                    "dataset_revision": "execskill-fixture-v1", "provenance": "fixture",
                                    "tasks": tasks})


def searchqa_items(count=COUNT):
    return [_item("searchqa", n, {"question": "Which fixture town keeps the bell number %d?" % n,
                                  "context": "Fixture note %d. The bell number %d is kept in Fixtown %d; the bell "
                                             "number %d is kept elsewhere." % (n, n, n, n + 100)},
                  {"answers": ["Fixtown %d" % n]}) for n in range(count)]


def _number(value):
    """An exact value as text: an integer, else two decimals."""
    return str(value.numerator) if value.denominator == 1 else "%.2f" % value


def officeqa_items(count=COUNT):
    kinds = ("difference", "ratio", "percent_change", "sum")
    items = []
    for n in range(count):
        a, b, c = 1000 + 37 * n, 1200 + 53 * n, 300 + 11 * n
        page = ("Fixture bulletin page %d\nTable %d. Receipts by fiscal year (millions of dollars)\n"
                "Year | Customs | Excise | Other\n2019 | %d | %d | %d\n2020 | %d | %d | %d\n"
                % (n, n + 1, a, c, 7 * n, b, c + 5, 9 * n))
        kind = kinds[n % len(kinds)]
        if kind == "difference":
            question, value = "By how much did customs receipts change from 2019 to 2020?", Fraction(b - a)
        elif kind == "ratio":
            question, value = "What is the ratio of 2020 customs to 2020 excise receipts?", Fraction(b, c + 5)
        elif kind == "percent_change":
            question, value = "What was the percent change in customs receipts from 2019 to 2020?", \
                Fraction(100 * (b - a), a)
        else:
            question, value = "What is the sum of the 2019 customs, excise and other receipts?", Fraction(a + c + 7 * n)
        items.append(_item("officeqa", n, {"question": question, "context": page}, {"answer": _number(value)}))
    return items


def livemath_items(count=COUNT):
    items = []
    for n in range(count):
        k = n + 2
        truth = str(k * (k - 1))  # f''(1) for f(x) = x^k
        wrong = [str(k * (k - 1) + d) for d in (1, -1, 2, 3)]
        if n % 4 == 3:  # the meta option is offered as E; it is the key on items 7 and 15
            options = wrong[:3]
            options.insert((n // 4) % 4, truth)
            options.append(STRONGER_OPTION)
            letter = "E" if n % 8 == 7 else "ABCD"[options.index(truth)]
        else:
            options = list(wrong)
            options.insert(n % 5, truth)
            letter = "ABCDE"[n % 5]
        choices = "\n\n".join("%s. %s" % (label, text) for label, text in zip("ABCDE", options))
        items.append(_item("livemath", n, {"question": "Let f(x) = x^%d. What is f''(1)?" % k, "choices": choices},
                           {"answer": letter}))
    return items


def spreadsheetbench_items(root, count=COUNT):
    """Input and answer workbooks under ``root``: the answer puts the sum of A1:A5 into B1."""
    from openpyxl import Workbook

    items = []
    for n in range(count):
        folder = Path(root) / ("fx-spreadsheetbench-%02d" % n)
        folder.mkdir(parents=True, exist_ok=True)
        values = [n + k for k in range(1, 6)]
        paths = []
        for suffix, answer in (("input", False), ("answer", True)):
            book = Workbook()
            sheet = book.active
            for row, value in enumerate(values, 1):
                sheet.cell(row=row, column=1, value=value)
            if answer:
                sheet["B1"] = sum(values)
            path = folder / ("1_%02d_%s.xlsx" % (n, suffix))
            book.save(path)
            paths.append(str(path))
        items.append(_item("spreadsheetbench", n,
                           {"instruction": "Put the sum of A1:A5 into B1.", "input_files": [paths[0]],
                            "answer_position": "B1"},
                           {"test_files": [paths[1]], "answer_position": "B1"}))
    return items


def alfworld_games():
    """Twelve scripted fake games (6 rooms x 2): six short wins (won at step <= 10), six long ones."""
    games = []
    for n in range(12):
        room, task_type = str(301 + n // 2), TASK_TYPES[n % len(TASK_TYPES)]
        thing, place = ("mug", "cabinet 1") if n % 2 else ("apple", "countertop 1")
        steps = 3 + n % 4 if n < 6 else 12 + n
        plan = ["go to %s" % place, "take %s 1 from %s" % (thing, place)] + \
            ["examine %s 1" % thing] * (steps - 3) + ["put %s 1 in/on fridge 1" % thing]
        observation = ("-= Welcome to TextWorld, ALFRED! =-\n\nYou are in the middle of a room. Looking quickly "
                       "around you, you see a cabinet 1, a countertop 1, a drawer 3, and a fridge 1.\n\n"
                       "Your task is to: put a %s in fridge." % thing)
        trial = "trial_T2019%04d_fixture" % n
        games.append({"task_id": "fx-alfworld-%02d" % n, "room": room, "task_type": task_type,
                      "gamefile": "json_2.1.1/train/%s-%s-None-Fridge-%s/%s/game.tw-pddl"
                                  % (task_type, thing.capitalize(), room, trial),
                      "initial_observation": observation,
                      "admissible_commands": ["go to cabinet 1", "go to countertop 1", "go to drawer 3",
                                              "go to fridge 1", "look", "inventory"],
                      "plan": plan, "won_at": len(plan),
                      "terminal_observation": "You put the %s 1 in/on the fridge 1. %s" % (thing, WON),
                      "expert_plan": list(plan), "extra": {"gamefile": "hidden", "expert_plan": list(plan)}})
    return games


def alfworld_items(root):
    """The 12 fake games written under ``root`` (each game file holds its episode as JSON), as pool-shaped items."""
    items = []
    for number, game in enumerate(alfworld_games()):
        path = Path(root) / game["gamefile"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(game, sort_keys=True), encoding="utf-8")
        items.append(_item("alfworld", number, {"game_file": str(path)},
                           {"game_metadata": {"source_split": "train", "task_type": game["task_type"],
                                              "asset_files": []}}))
    return items


def alfworld_tree(root, rooms, per_room, *, split="train", first_room=1):
    """A synthetic ``json_2.1.1/<split>`` layout: ``per_room(room index)`` games in each of ``rooms`` rooms (task
    types cycling); returns the relative game paths."""
    paths = []
    for r in range(rooms):
        room = str(first_room + r)
        for g in range(per_room(r)):
            task_type = TASK_TYPES[(r + g) % len(TASK_TYPES)]
            relative = "json_2.1.1/%s/%s-Obj%d-None-Recep%d-%s/trial_T%03d_%02d/game.tw-pddl" % (
                split, task_type, g, r, room, r, g)
            path = Path(root) / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture game %s %d" % (room, g), encoding="utf-8")
            paths.append(relative)
    return paths
