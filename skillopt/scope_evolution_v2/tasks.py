"""Synthetic artifact-editing diagnostic with a non-executing expression DSL.

Targets produce patches, not arithmetic answers. Coding artifacts are sequential
expression programs; spreadsheet artifacts are dependency-recalculated cells;
rule artifacts are ordered first-match rule stages. We never eval/exec model
code. Behavioral tests are generated from the complete public contract before
any model response. These remain synthetic tasks, not public benchmarks.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import itertools
import json
import math
import random
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, Mapping, Sequence

DOMAINS = ("coding", "spreadsheet", "rule_reasoning")
MECHANISMS = ("constraint_preservation", "evidence_verification")
SPLITS = ("train", "dev", "validation", "test")
DEFAULT_DOMAINS = {"train": ("coding",), "dev": ("coding",),
                   "validation": ("coding", "spreadsheet"), "test": DOMAINS}
PROTOCOL_VERSION = "artifact-scope-v2.0"
MAX_EXPRESSION_CHARS = 3000


@dataclass(frozen=True)
class Task:
    id: str
    domain: str
    mechanism: str
    group: str
    split: str
    family: str
    prompt: str
    gold: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Task":
        return cls(**{key: value[key] for key in cls.__dataclass_fields__})


def _rng(seed: int, split: str, domain: str, mechanism: str, group: str, index: int, difficulty: str) -> random.Random:
    key = f"{PROTOCOL_VERSION}|{seed}|{split}|{domain}|{mechanism}|{group}|{index}|{difficulty}"
    return random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:16], "big"))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@lru_cache(maxsize=4096)
def _parse(expression: str, spreadsheet: bool = False) -> ast.Expression:
    if not isinstance(expression, str) or len(expression) > MAX_EXPRESSION_CHARS:
        raise ValueError("expression must be a bounded string")
    if spreadsheet:
        if not expression.startswith("="):
            raise ValueError("spreadsheet formulas must begin with =")
        expression = expression[1:].replace("<>", "!=")
        expression = re.sub(r"(?<![<>=!])=(?!=)", "==", expression)
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 700:
        raise ValueError("expression is too complex")
    allowed = (ast.Expression, ast.Constant, ast.Name, ast.Load, ast.BinOp, ast.Add, ast.Sub,
               ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.UnaryOp, ast.USub, ast.UAdd,
               ast.Not, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Eq, ast.NotEq,
               ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.IfExp, ast.Call)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError(f"unsupported expression node: {type(node).__name__}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool, str)):
            raise ValueError("unsupported constant")
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.keywords):
            raise ValueError("only named built-in DSL operations are permitted")
        if isinstance(node, ast.Call) and node.func.id not in {"MIN", "MAX", "ABS", "INT", "IF", "AND", "OR", "NOT"}:
            raise ValueError("unknown DSL operation")
    return tree


def _eval(expression: str, env: Mapping[str, Any], spreadsheet: bool = False) -> Any:
    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in {"TRUE", "FALSE"}:
                return node.id == "TRUE"
            return env[node.id]
        if isinstance(node, ast.IfExp):
            return visit(node.body if visit(node.test) else node.orelse)
        if isinstance(node, ast.BoolOp):
            return all(bool(visit(x)) for x in node.values) if isinstance(node.op, ast.And) else any(bool(visit(x)) for x in node.values)
        if isinstance(node, ast.UnaryOp):
            value = visit(node.operand)
            if isinstance(node.op, ast.Not):
                return not value
            return -value if isinstance(node.op, ast.USub) else +value
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left), visit(node.right)
            if isinstance(a, str) or isinstance(b, str):
                raise ValueError("string arithmetic is not allowed")
            if isinstance(node.op, ast.Add):
                value = a + b
            elif isinstance(node.op, ast.Sub):
                value = a - b
            elif isinstance(node.op, ast.Mult):
                value = a * b
            elif isinstance(node.op, ast.Div):
                value = a / b
            elif isinstance(node.op, ast.FloorDiv):
                value = a // b
            else:
                value = a % b
            if not math.isfinite(value) or abs(value) > 10**12:
                raise ValueError("numeric range exceeded")
            return value
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            for op, item in zip(node.ops, node.comparators):
                right = visit(item)
                if isinstance(op, ast.Eq):
                    ok = left == right
                elif isinstance(op, ast.NotEq):
                    ok = left != right
                elif isinstance(op, ast.Lt):
                    ok = left < right
                elif isinstance(op, ast.LtE):
                    ok = left <= right
                elif isinstance(op, ast.Gt):
                    ok = left > right
                else:
                    ok = left >= right
                if not ok:
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            name = node.func.id
            if name == "IF" and len(node.args) == 3:
                return visit(node.args[1] if visit(node.args[0]) else node.args[2])
            if name in {"AND", "OR"} and 1 <= len(node.args) <= 10:
                return all(bool(visit(x)) for x in node.args) if name == "AND" else any(bool(visit(x)) for x in node.args)
            if name == "NOT" and len(node.args) == 1:
                return not visit(node.args[0])
            args = [visit(x) for x in node.args]
            if name in {"MIN", "MAX"} and 1 <= len(args) <= 10:
                return min(args) if name == "MIN" else max(args)
            if name == "ABS" and len(args) == 1:
                return abs(args[0])
            if name == "INT" and len(args) == 1:
                return math.floor(args[0])
            raise ValueError(f"unsupported DSL call or arity: {name}")
        raise ValueError("unsupported expression")

    result = visit(_parse(expression, spreadsheet).body)
    if isinstance(result, (float, int)) and (not math.isfinite(result) or abs(result) > 10**12):
        raise ValueError("numeric range exceeded")
    return result


def _column(index: int) -> str:
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result + "2"


def _excel(expression: str, names: Mapping[str, str]) -> str:
    """Render our trusted expression templates into a small Excel-compatible subset."""
    def render(node: ast.AST) -> str:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return "TRUE" if node.value else "FALSE"
            return json.dumps(node.value)
        if isinstance(node, ast.Name):
            return names.get(node.id, node.id)
        if isinstance(node, ast.IfExp):
            return f"IF({render(node.test)},{render(node.body)},{render(node.orelse)})"
        if isinstance(node, ast.Call):
            return f"{node.func.id}({','.join(render(a) for a in node.args)})"
        if isinstance(node, ast.BoolOp):
            return f"{'AND' if isinstance(node.op, ast.And) else 'OR'}({','.join(render(a) for a in node.values)})"
        if isinstance(node, ast.UnaryOp):
            return f"NOT({render(node.operand)})" if isinstance(node.op, ast.Not) else f"({'-' if isinstance(node.op, ast.USub) else '+'}{render(node.operand)})"
        if isinstance(node, ast.BinOp):
            ops = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}
            if isinstance(node.op, ast.FloorDiv):
                return f"INT({render(node.left)}/{render(node.right)})"
            return f"({render(node.left)}{ops[type(node.op)]}{render(node.right)})"
        if isinstance(node, ast.Compare):
            ops = {ast.Eq: "=", ast.NotEq: "<>", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
            left = node.left
            parts = []
            for op, right in zip(node.ops, node.comparators):
                parts.append(f"({render(left)}{ops[type(op)]}{render(right)})")
                left = right
            return parts[0] if len(parts) == 1 else f"AND({','.join(parts)})"
        raise ValueError("unsupported trusted template")
    return "=" + render(_parse(expression).body)


def _artifact(domain: str, inputs: Sequence[str], nodes: Mapping[str, str]) -> dict[str, Any]:
    if domain == "coding":
        return {"kind": "sequential_expression_program", "inputs": list(inputs),
                "statements": [{"name": name, "expression": expr} for name, expr in nodes.items()],
                "exports": list(nodes)}
    if domain == "spreadsheet":
        names = {name: _column(i + 1) for i, name in enumerate(list(inputs) + list(nodes))}
        return {"kind": "recalculated_worksheet", "input_cells": {names[k]: k for k in inputs},
                "cells": {names[k]: _excel(v, names) for k, v in nodes.items()},
                "export_cells": {k: names[k] for k in nodes}}
    stages = []
    for name, expression in nodes.items():
        tree = _parse(expression).body
        if isinstance(tree, ast.IfExp):
            rules = [{"id": f"{name}_if", "when": ast.unparse(tree.test), "value": ast.unparse(tree.body)},
                     {"id": f"{name}_else", "when": "True", "value": ast.unparse(tree.orelse)}]
        else:
            rules = [{"id": f"{name}_rule", "when": "True", "value": expression}]
        stages.append({"output": name, "rules": rules})
    return {"kind": "ordered_rule_stages", "inputs": list(inputs), "stages": stages, "exports": list(nodes)}


def _reference_patch(artifact: Mapping[str, Any], changed: Mapping[str, str]) -> dict[str, Any]:
    if artifact["kind"] == "sequential_expression_program":
        return {"replace": dict(changed)}
    if artifact["kind"] == "recalculated_worksheet":
        names = {v: k for k, v in artifact["input_cells"].items()} | artifact["export_cells"]
        return {"set_cells": {names[k]: _excel(v, names) for k, v in changed.items()}}
    return {"replace_rules": {f"{k}_rule": {"when": "True", "value": v} for k, v in changed.items()}}


def _apply(artifact: Mapping[str, Any], patch: Any) -> dict[str, Any]:
    result = copy.deepcopy(artifact)
    kind = artifact["kind"]
    expected_key = {"sequential_expression_program": "replace", "recalculated_worksheet": "set_cells",
                    "ordered_rule_stages": "replace_rules"}[kind]
    if not isinstance(patch, dict) or set(patch) != {expected_key} or not isinstance(patch[expected_key], dict):
        raise ValueError(f"patch must contain exactly the object field {expected_key}")
    changes = patch[expected_key]
    if len(changes) > 20:
        raise ValueError("at most 20 existing entries may be replaced")
    if kind == "sequential_expression_program":
        entries = {entry["name"]: entry for entry in result["statements"]}
        if set(changes) - set(entries):
            raise ValueError("cannot add or rename program statements")
        for name, expression in changes.items():
            _parse(expression)
            entries[name]["expression"] = expression
    elif kind == "recalculated_worksheet":
        if set(changes) - set(result["cells"]):
            raise ValueError("cannot modify input cells or add cells")
        for cell, expression in changes.items():
            _parse(expression, True)
            result["cells"][cell] = expression
    else:
        rules = {rule["id"]: rule for stage in result["stages"] for rule in stage["rules"]}
        if set(changes) - set(rules):
            raise ValueError("cannot add, delete, or reorder rules")
        for rule_id, entry in changes.items():
            if not isinstance(entry, dict) or set(entry) != {"when", "value"}:
                raise ValueError("each replacement rule has exactly when and value string fields")
            _parse(entry["when"])
            _parse(entry["value"])
            rules[rule_id].update(entry)
    return result


def _execute(artifact: Mapping[str, Any], inputs: Mapping[str, Any]) -> dict[str, Any]:
    kind = artifact["kind"]
    if kind == "sequential_expression_program":
        env = dict(inputs)
        for item in artifact["statements"]:
            env[item["name"]] = _eval(item["expression"], env)
        return {name: env[name] for name in artifact["exports"]}
    if kind == "ordered_rule_stages":
        env = dict(inputs)
        for stage in artifact["stages"]:
            for rule in stage["rules"]:
                if _eval(rule["when"], env):
                    env[stage["output"]] = _eval(rule["value"], env)
                    break
            else:
                raise ValueError("a stage has no matching rule")
        return {name: env[name] for name in artifact["exports"]}
    values = {cell: inputs[name] for cell, name in artifact["input_cells"].items()}
    pending: set[str] = set()

    class Cells(dict):
        def __missing__(self, key: str) -> Any:
            if key in pending or key not in artifact["cells"]:
                raise ValueError("cyclic or unknown cell reference")
            pending.add(key)
            value = _eval(artifact["cells"][key], self, True)
            pending.remove(key)
            self[key] = value
            return value

    env = Cells(values)
    return {name: env[cell] for name, cell in artifact["export_cells"].items()}


def _contract(domain: str, artifact: Mapping[str, Any]) -> str:
    if domain == "coding":
        schema = '{"answer":{"replace":{"existing_statement_name":"expression string"}}}'
        semantics = "Statements execute once in the given order. A statement may read inputs and earlier statements only."
    elif domain == "spreadsheet":
        schema = '{"answer":{"set_cells":{"existing_formula_cell":"=formula string"}}}'
        semantics = "All formula cells recalculate by dependency, not row/order of listing. Input cells are read-only; cycles are invalid. Formula strings must start with =."
    else:
        schema = '{"answer":{"replace_rules":{"existing_rule_id":{"when":"condition string","value":"expression string"}}}}'
        semantics = "Stages execute in the given order; each stage uses its FIRST matching rule. Later stages read the resulting stage outputs. Rule order is fixed."
    return (
        f"Artifact:\n{json.dumps(artifact, ensure_ascii=False, indent=2)}\n"
        f"Execution contract: {semantics}\n"
        "Allowed expressions: named inputs/references, numeric/string/Boolean literals, + - * / // %, comparisons, "
        "and/or/not, conditional X if C else Y; calls only MIN, MAX, ABS, INT (floor), IF, AND, OR, NOT. "
        "For worksheet formulas use IF/AND/OR/NOT instead of Python conditionals; Excel = and <> comparisons are supported. "
        "No attributes, indexing, imports, loops, comprehensions, arbitrary functions, file/network operations, or external tools.\n"
        f"OUTPUT SCHEMA (exact nesting and field names): {schema}\n"
        "Return exactly one JSON object with only answer. The answer contains exactly the indicated patch object field; "
        "that field maps existing entry identifiers to replacement strings (or complete when/value objects for rules). "
        "Omitted entries remain unchanged. No new entries, deletions, reordering, full-artifact replacement, explanations, Markdown, or example placeholders. "
        "Your patch is checked on boundary cases and regression cases covering the public contract; do not output test answers."
    )


def _cp_parameters(rng: random.Random, split: str, difficulty: str) -> dict[str, Any]:
    return {"split": split, "difficulty": difficulty, "bulk_n": rng.randint(3, 6),
            "bulk_cap": rng.randint(17, 31), "bulk_div": rng.randint(3, 6),
            "member_rate": rng.randint(1, 4), "local_fee": rng.randint(3, 8),
            "remote_fee": rng.randint(11, 19), "rush_fee": rng.randint(7, 13),
            "rush_cutoff": rng.randint(65, 110), "free_ship": rng.randint(90, 140),
            "tax_div": rng.randint(7, 12), "packing_rate": rng.randint(1, 3),
            "offer_n": rng.randint(3, 7), "offer_floor": rng.randint(24, 51),
            "rebate_rate": rng.randint(2, 5), "priority_bonus": rng.randint(3, 9),
            "flat_rate": rng.randint(3, 9), "flat_rush": rng.randint(2, 8)}


def _cp_nodes(p: Mapping[str, Any]) -> dict[str, str]:
    bulk = f"MIN({p['bulk_cap']}, gross // {p['bulk_div']}) if qty >= {p['bulk_n']} else 0"
    if p["split"] == "dev":
        bulk = f"MIN({p['bulk_cap']}, (qty // {p['bulk_n']}) * price)"
    elif p["split"] == "test":
        bulk = f"MIN({p['bulk_cap']}, gross // {p['bulk_div']}) if qty >= {p['bulk_n']} and not fragile else 0"
    zone = f"{p['remote_fee']} if remote else {p['local_fee']}"
    if p["split"] == "validation":
        zone = f"0 if goods >= {p['free_ship']} else ({zone})"
    elif p["split"] == "test":
        zone = f"({zone}) + ({p['packing_rate']} if fragile else 0)"
    return {"gross": "price * qty", "bulk_cut": bulk,
            "member_cut": f"{p['member_rate']} * qty if member else 0",
            "goods": "MAX(0, gross - bulk_cut - member_cut)", "zone_quote": zone,
            "rush_quote": f"{p['rush_fee']} if rush and goods < {p['rush_cutoff']} else 0",
            "packing_quote": f"{p['packing_rate']} * qty if fragile else 0" if p["difficulty"] == "hard" else "0",
            "tax_quote": f"goods // {p['tax_div']} if remote or priority else 0",
            "quoted_total": "goods + zone_quote + rush_quote + packing_quote + tax_quote",
            "credit_used": "MIN(credit, quoted_total)", "amount_due": "MAX(0, quoted_total - credit)",
            "audit_code": "quoted_total * 3 + zone_quote * 5 + bulk_cut"}


def _cp_eligibility(p: Mapping[str, Any]) -> str:
    if p["split"] == "train":
        return f"campaign and member and qty >= {p['offer_n']}"
    if p["split"] == "dev":
        return f"campaign and (member or priority) and goods >= {p['offer_floor']}"
    if p["split"] == "validation":
        return f"campaign and qty >= {p['offer_n']} and not rush"
    return f"campaign and ((member and not fragile) or (priority and qty >= {p['offer_n']}))"


def _cp_changes(p: Mapping[str, Any], near: bool) -> dict[str, str]:
    if near:
        working = f"{p['flat_rate']} * qty + ({p['flat_rush']} if rush else 0)"
    else:
        eligible = _cp_eligibility(p)
        rebate = f"(MIN(goods, {p['rebate_rate']} * qty + ({p['priority_bonus']} if priority else 0)) if ({eligible}) else 0)"
        waiver = f"(zone_quote if ({eligible}) and not remote else 0)"
        working = f"quoted_total - {rebate} - {waiver}"
        if p["difficulty"] == "hard":
            new_tax = f"((MAX(0, goods - {rebate}) // {p['tax_div']}) if remote or priority else 0)"
            working += f" - tax_quote + {new_tax}"
    working = f"MAX(0, {working})"
    return {"credit_used": f"MIN(credit, {working})", "amount_due": f"MAX(0, {working} - credit)"}


def _cp_expected(p: Mapping[str, Any], x: Mapping[str, Any], near: bool) -> dict[str, Any]:
    """Independent procedural oracle, not evaluation of the reference patch."""
    gross = x["price"] * x["qty"]
    if p["split"] == "dev":
        bulk = min(p["bulk_cap"], (x["qty"] // p["bulk_n"]) * x["price"])
    else:
        allowed = x["qty"] >= p["bulk_n"] and not (p["split"] == "test" and x["fragile"])
        bulk = min(p["bulk_cap"], gross // p["bulk_div"]) if allowed else 0
    member = p["member_rate"] * x["qty"] if x["member"] else 0
    goods = max(0, gross - bulk - member)
    zone = p["remote_fee"] if x["remote"] else p["local_fee"]
    if p["split"] == "validation" and goods >= p["free_ship"]:
        zone = 0
    if p["split"] == "test" and x["fragile"]:
        zone += p["packing_rate"]
    rush = p["rush_fee"] if x["rush"] and goods < p["rush_cutoff"] else 0
    packing = p["packing_rate"] * x["qty"] if p["difficulty"] == "hard" and x["fragile"] else 0
    tax = goods // p["tax_div"] if x["remote"] or x["priority"] else 0
    quoted = goods + zone + rush + packing + tax
    if near:
        working = p["flat_rate"] * x["qty"] + (p["flat_rush"] if x["rush"] else 0)
    else:
        if p["split"] == "train":
            eligible = x["campaign"] and x["member"] and x["qty"] >= p["offer_n"]
        elif p["split"] == "dev":
            eligible = x["campaign"] and (x["member"] or x["priority"]) and goods >= p["offer_floor"]
        elif p["split"] == "validation":
            eligible = x["campaign"] and x["qty"] >= p["offer_n"] and not x["rush"]
        else:
            eligible = x["campaign"] and ((x["member"] and not x["fragile"]) or (x["priority"] and x["qty"] >= p["offer_n"]))
        rebate = min(goods, p["rebate_rate"] * x["qty"] + (p["priority_bonus"] if x["priority"] else 0)) if eligible else 0
        waived = zone if eligible and not x["remote"] else 0
        working = quoted - rebate - waived
        if p["difficulty"] == "hard":
            new_tax = max(0, goods - rebate) // p["tax_div"] if x["remote"] or x["priority"] else 0
            working += new_tax - tax
    working = max(0, working)
    return {"gross": gross, "bulk_cut": bulk, "member_cut": member, "goods": goods,
            "zone_quote": zone, "rush_quote": rush, "packing_quote": packing, "tax_quote": tax,
            "quoted_total": quoted, "credit_used": min(x["credit"], working),
            "amount_due": max(0, working - x["credit"]), "audit_code": quoted * 3 + zone * 5 + bulk}


def _cp_tests(rng: random.Random, p: Mapping[str, Any], near: bool) -> list[dict[str, Any]]:
    cases = []
    # Enumerate every Boolean conjunction, plus threshold/credit boundary probes.
    for bits in itertools.product([False, True], repeat=6):
        x = dict(zip(["member", "remote", "rush", "campaign", "fragile", "priority"], bits))
        x.update(price=rng.randint(3, 25), qty=rng.choice([p["offer_n"], p["offer_n"] + 1, p["bulk_n"]]),
                 credit=rng.choice([0, 1, 9, 1000]))
        cases.append(x)
    for qty in sorted({0, 1, p["offer_n"] - 1, p["offer_n"], p["offer_n"] + 1, p["bulk_n"] - 1, p["bulk_n"], p["bulk_n"] + 1}):
        for credit in [0, 1, 1000]:
            cases.append({"price": rng.choice([0, 1, 7, 19]), "qty": qty, "credit": credit,
                          "member": True, "remote": False, "rush": False, "campaign": True,
                          "fragile": True, "priority": True})
    for price, qty, credit in [(0, 0, 0), (100, 30, 0), (100, 30, 10000), (0, 30, 10000)]:
        cases.append({"price": price, "qty": qty, "credit": credit, "member": True,
                      "remote": True, "rush": True, "campaign": True, "fragile": True, "priority": True})
    # Probe all reachable public monetary branch thresholds at -1, 0, +1.
    # Searching uses only the original public program/spec, never model output.
    wanted = {value + delta for value in [p["offer_floor"], p["free_ship"], p["rush_cutoff"]] for delta in [-1, 0, 1]}
    found = set()
    for qty in range(1, 31):
        for price in range(101):
            for member in [False, True]:
                probe = {"price": price, "qty": qty, "credit": 0, "member": member, "remote": False,
                         "rush": True, "campaign": True, "fragile": False, "priority": True}
                goods = _cp_expected(p, probe, near)["goods"]
                if goods in wanted and goods not in found:
                    found.add(goods)
                    cases.append(probe)
            if found == wanted:
                break
        if found == wanted:
            break
    # Exact available-credit boundaries matter: subtracting a waiver AFTER a
    # preexisting zero floor can create a negative amount or wrong credit usage.
    anchors = cases[::max(1, len(cases) // 16)][:16]
    for original in anchors:
        without_credit = original | {"credit": 0}
        subtotal = _cp_expected(p, without_credit, near)["amount_due"]
        for credit in sorted({max(0, subtotal - 1), subtotal, subtotal + 1}):
            cases.append(original | {"credit": credit})
    unique = {_json(case): case for case in cases}
    return [{"inputs": x, "expected": _cp_expected(p, x, near)} for x in unique.values()]


def _cp_task(rng: random.Random, split: str, domain: str, near: bool, difficulty: str) -> tuple:
    p = _cp_parameters(rng, split, difficulty)
    inputs = ["price", "qty", "member", "remote", "rush", "credit", "campaign", "fragile", "priority"]
    artifact = _artifact(domain, inputs, _cp_nodes(p))
    if near:
        request = (
            f"Replace the collection policy entirely with flat_rate*qty + (flat_rush if rush else 0), "
            f"where flat_rate={p['flat_rate']} and flat_rush={p['flat_rush']}. "
            "The old merchandise, membership, zone, packing, tax, and campaign rules do NOT contribute to this new collection subtotal. "
            "Then apply available credit."
        )
    else:
        request = (
            f"Add this campaign to collection only. Eligibility is exactly: {_cp_eligibility(p)}. "
            f"An eligible order receives a rebate MIN(goods, {p['rebate_rate']}*qty + ({p['priority_bonus']} if priority else 0)); "
            "all other orders receive zero rebate. Eligible non-remote orders also have the ENTIRE zone_quote waived for collection; other orders do not. "
            "Start from quoted_total and subtract these two adjustments BEFORE applying credit or the final zero floor. "
        )
        if difficulty == "hard":
            request += (
                f"In the collection subtotal only, replace the old tax_quote contribution by MAX(0,goods-rebate)//{p['tax_div']} "
                "when remote or priority is true, otherwise by zero. This tax adjustment does not mutate the historical tax_quote. "
            )
        else:
            request += "The quoted tax contribution is unchanged. "
    request += (
        "Floor that collection subtotal at zero. Set credit_used to MIN(credit, collection subtotal), "
        "and amount_due to MAX(0, collection subtotal-credit). "
        "ONLY the exported credit_used and amount_due behaviors change: EVERY other exported value is a historical quote/audit value "
        "and must remain exactly as in the original artifact for every input, including ineligible orders and zero/excess-credit cases. "
        "Valid integer ranges are price=0..100, qty=0..30, credit=0..10000; all six flags are Boolean. "
        "Existing definitions, branch boundaries, and rounding are the source of truth."
    )
    prompt = (
        "Modify the following executable declarative artifact to implement a collection-policy change. "
        "This is an artifact-editing task, not a request to calculate a single order.\n"
        f"Change contract: {request}\n{_contract(domain, artifact)}"
    )
    return prompt, _reference_patch(artifact, _cp_changes(p, near)), artifact, _cp_tests(rng, p, near), {
        "parameters": p, "requested_outputs": ["credit_used", "amount_due"],
        "structural_family": {"train": "capped_bulk_quote", "dev": "bundle_discount_quote",
                              "validation": "free_shipping_quote", "test": "fragility_dependent_quote"}[split],
        "candidate_specific_boundary": "replacement removes old collection dependencies, but preserving separate historical exports remains appropriate",
    }


def _ev_task(rng: random.Random, split: str, domain: str, near: bool, difficulty: str) -> tuple:
    base = "signed and region == target_region and valid_from <= day and day < valid_until"
    additions = {"train": "approved and issuer_allowed", "dev": "approved and checksum_ok",
                 "validation": "issuer_allowed and not revoked", "test": "checksum_ok and not revoked"}[split]
    if difficulty == "hard":
        additions += " and (not emergency or emergency_authorized)"
    predicate = f"({base}) and ({additions})"
    inputs = ["signed", "region", "target_region", "valid_from", "day", "valid_until", "approved",
              "issuer_allowed", "checksum_ok", "revoked", "emergency", "emergency_authorized", "replay"]
    artifact = _artifact(domain, inputs, {"eligible": base, "use_active": "not replay"})
    changed = {"use_active": "False"} if near else {"eligible": predicate}
    request = (
        "The service is being converted to audit replay ONLY: use_active must always be false, including when the legacy replay flag is false. "
        "The wrapper must return the explicitly requested record even if it is ineligible. Keep the exported eligibility diagnostics exactly as before."
        if near else f"For active selection, extend eligible with ALL the following additional requirements: {additions}. "
        "Preserve every original admission requirement. The legacy replay bypass behavior must remain unchanged."
    )
    prompt = (
        "Patch an executable record-selection artifact. Each record supplies the displayed record fields; context supplies target_region, day, and replay. "
        "The trusted wrapper evaluates eligible for every record. It also evaluates use_active, which must depend only on context, never the individual record. "
        "If use_active is true, the wrapper returns the ID of the eligible record with largest revision (IDs ascending break revision ties); "
        "if false, it returns requested_id exactly when present, without filtering. No matching record means JSON null. "
        "The wrapper also exports the set of eligible IDs as a diagnostic. You may not change the wrapper. "
        "signed/approved/issuer_allowed/checksum_ok/revoked/emergency/emergency_authorized/replay are supplied Booleans, "
        "region and target_region are strings, and dates/revisions are integers.\n"
        f"Change contract: {request}\n{_contract(domain, artifact)}"
    )
    cases = []
    # Exhaust each admission bit and both replay modes, with date boundaries.
    for index in range(40):
        day = rng.randint(10, 30)
        target = rng.choice(["east", "west"])
        records = []
        ids = [f"D{i}" for i in rng.sample(range(100, 999), 9)]
        for i in range(9):
            rec = {"id": ids[i], "revision": rng.randint(1, 1000), "signed": True, "region": target,
                   "valid_from": day - 2, "valid_until": day + 2, "approved": True,
                   "issuer_allowed": True, "checksum_ok": True, "revoked": False,
                   "emergency": False, "emergency_authorized": False}
            if i:
                field = ["signed", "approved", "issuer_allowed", "checksum_ok", "revoked", "region", "valid_from", "valid_until"][i - 1]
                rec[field] = ({"revoked": True, "region": "other", "valid_from": day + 1, "valid_until": day}.get(field, False))
            if difficulty == "hard" and i in {1, 3, 7}:
                rec["emergency"] = True
                rec["emergency_authorized"] = bool((index + i) % 2)
            records.append(rec)
        if difficulty == "hard":
            # These extra records independently isolate the emergency clause:
            # unlike the distractors above, every other admission field passes.
            for permitted in [False, True]:
                records.append({"id": f"isolated-emergency-{index}-{int(permitted)}",
                                "revision": 1100 + int(permitted), "signed": True, "region": target,
                                "valid_from": day - 2, "valid_until": day + 2, "approved": True,
                                "issuer_allowed": True, "checksum_ok": True, "revoked": False,
                                "emergency": True, "emergency_authorized": permitted})
        if index % 10 == 0:
            # Explicit lower-bound validity probe, independent of other flags.
            records[0]["valid_from"] = day
        rng.shuffle(records)
        context = {"target_region": target, "day": day, "replay": bool(index % 2)}
        requested = "missing-record" if index % 11 == 0 else rng.choice(records)["id"]
        case = {"records": records, "context": context, "requested_id": requested}
        eligible = []
        for rec in records:
            ok = rec["signed"] and rec["region"] == target and rec["valid_from"] <= day < rec["valid_until"]
            if not near:
                if split == "train":
                    ok = ok and rec["approved"] and rec["issuer_allowed"]
                elif split == "dev":
                    ok = ok and rec["approved"] and rec["checksum_ok"]
                elif split == "validation":
                    ok = ok and rec["issuer_allowed"] and not rec["revoked"]
                else:
                    ok = ok and rec["checksum_ok"] and not rec["revoked"]
                if difficulty == "hard":
                    ok = ok and (not rec["emergency"] or rec["emergency_authorized"])
            if ok:
                eligible.append(rec)
        active = not near and not context["replay"]
        if active:
            selected = sorted(eligible, key=lambda r: (-r["revision"], r["id"]))[0]["id"] if eligible else None
        else:
            selected = requested if any(r["id"] == requested for r in records) else None
        cases.append({"inputs": case, "expected": {"selected_id": selected, "eligible_ids": sorted(r["id"] for r in eligible), "use_active": active}})
    return prompt, _reference_patch(artifact, changed), artifact, cases, {
        "parameters": {"split": split, "difficulty": difficulty},
        "requested_outputs": ["selected_id", "use_active"] if near else ["selected_id", "eligible_ids"],
        "structural_family": f"selector_{split}_admission_join",
        "candidate_specific_boundary": "active-policy evidence admission is not a precondition for an explicit audit replay",
    }


def _unrelated_task(rng: random.Random, split: str, domain: str, difficulty: str) -> tuple:
    expressions = {
        "train": {"out_a": "(x + y) * z", "out_b": "MAX(x, y) - MIN(y, z)"},
        "dev": {"out_a": "ABS(x - y) + ABS(y - z)", "out_b": "MAX(x, y, z)"},
        "validation": {"out_a": "x * x + y * y + z * z", "out_b": "MIN(x, y, z)"},
        "test": {"out_a": "(x + y + z) % 7", "out_b": "MAX(x - y, y - z, z - x)"},
    }[split]
    artifact = _artifact(domain, ["x", "y", "z"], {"out_a": "0", "out_b": "0"})
    cases = []
    for _ in range(24):
        x, y, z = (rng.randint(-15, 15) for _ in range(3))
        if split == "train":
            values = [(x + y) * z, max(x, y) - min(y, z)]
        elif split == "dev":
            values = [abs(x - y) + abs(y - z), max(x, y, z)]
        elif split == "validation":
            values = [x*x + y*y + z*z, min(x, y, z)]
        else:
            values = [(x + y + z) % 7, max(x - y, y - z, z - x)]
        cases.append({"inputs": {"x": x, "y": y, "z": z}, "expected": dict(zip(["out_a", "out_b"], values))})
    prompt = (
        "Complete two previously empty arithmetic-expression slots. There is no existing policy, record selection, historical quote, or dependency migration to preserve. "
        f"For all integer x,y,z, implement exactly {_json(expressions)}. The zero expressions are placeholders, not required behavior.\n{_contract(domain, artifact)}"
    )
    return prompt, _reference_patch(artifact, expressions), artifact, cases, {
        "requested_outputs": ["out_a", "out_b"], "structural_family": f"new_arithmetic_slots_{split}",
    }


def build_tasks(seed: int = 42, split: str = "train", n_per_cell: int = 4,
                domains: Sequence[str] | None = None, mechanisms: Sequence[str] | None = None,
                difficulty: str = "medium") -> list[Task]:
    """Generate only the requested split. Each selected mechanism has positive/near_miss cells, plus one unrelated cell per domain."""
    if split not in SPLITS or difficulty not in {"medium", "hard"}:
        raise ValueError("invalid split or difficulty")
    if isinstance(n_per_cell, bool) or not isinstance(n_per_cell, int) or n_per_cell < 1:
        raise ValueError("n_per_cell must be a positive integer")
    chosen = tuple(DEFAULT_DOMAINS[split] if domains is None else domains)
    mechanisms = tuple(MECHANISMS if mechanisms is None else mechanisms)
    if not chosen or len(chosen) != len(set(chosen)) or set(chosen) - set(DEFAULT_DOMAINS[split]):
        raise ValueError("invalid domains or exposure of held-out domain")
    if not mechanisms or len(mechanisms) != len(set(mechanisms)) or set(mechanisms) - set(MECHANISMS):
        raise ValueError("invalid mechanisms")
    tasks = []
    for domain in chosen:
        cells = [(m, g) for m in mechanisms for g in ("positive", "near_miss")] + [("none", "unrelated")]
        for mechanism, group in cells:
            for i in range(n_per_cell):
                rng = _rng(seed, split, domain, mechanism, group, i, difficulty)
                if mechanism == "constraint_preservation":
                    prompt, patch, artifact, cases, metadata = _cp_task(rng, split, domain, group == "near_miss", difficulty)
                elif mechanism == "evidence_verification":
                    prompt, patch, artifact, cases, metadata = _ev_task(rng, split, domain, group == "near_miss", difficulty)
                else:
                    prompt, patch, artifact, cases, metadata = _unrelated_task(rng, split, domain, difficulty)
                task_id = f"scope-v2-s{seed}-{split}-{domain}-{mechanism}-{group}-{difficulty}-{i:04d}"
                metadata.update({"protocol_version": PROTOCOL_VERSION, "synthetic": True, "difficulty": difficulty,
                                 "artifact": artifact, "tests": cases, "seed": seed, "index": i,
                                 "mechanism_label_status": "hypothesized_not_candidate_specific_ground_truth"})
                tasks.append(Task(task_id, domain, mechanism, group, split, f"{domain}/{metadata['structural_family']}",
                                  prompt, patch, metadata))
    random.Random(f"{PROTOCOL_VERSION}|{seed}|{split}|order").shuffle(tasks)
    return tasks


def _selector_execute(artifact: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    eligible = []
    modes = []
    for record in case["records"]:
        output = _execute(artifact, record | case["context"])
        if not isinstance(output["eligible"], bool) or not isinstance(output["use_active"], bool):
            raise ValueError("selector exports must be Booleans")
        modes.append(output["use_active"])
        if output["eligible"]:
            eligible.append(record)
    if len(set(modes)) != 1:
        raise ValueError("use_active must not depend on individual record")
    if modes[0]:
        selected = sorted(eligible, key=lambda r: (-r["revision"], r["id"]))[0]["id"] if eligible else None
    else:
        selected = case["requested_id"] if any(r["id"] == case["requested_id"] for r in case["records"]) else None
    return {"selected_id": selected, "eligible_ids": sorted(r["id"] for r in eligible), "use_active": modes[0]}


def evaluate_answer(task: Task | Mapping[str, Any], response_text: str) -> dict[str, Any]:
    """Apply a declarative patch and require *all* requested and regression tests.

    Reflection may use returned train failure examples; never put hidden tests
    or gold into the target model's prompt, and never train on test feedback.
    """
    task = task if isinstance(task, Task) else Task.from_dict(task)
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate JSON key")
            out[key] = value
        return out

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite constant {value}")

    try:
        parsed = json.loads(response_text, object_pairs_hook=unique, parse_constant=reject_constant)
        if not isinstance(parsed, dict) or set(parsed) != {"answer"}:
            raise ValueError("response must have exactly answer")
        artifact = _apply(task.metadata["artifact"], parsed["answer"])
    except (ValueError, TypeError, SyntaxError, KeyError, RecursionError) as error:
        return {"correct": False, "hard": 0.0, "soft": 0.0, "format_valid": False, "artifact_valid": False,
                "parsed_answer": None, "passed_tests": 0, "total_tests": len(task.metadata["tests"]),
                "reason": f"invalid_patch: {error}", "failure_examples": []}
    requested = set(task.metadata["requested_outputs"])
    passed = 0
    dimension_passes = {"requested_behavior": 0, "preserved_behavior": 0}
    failures = []
    runtime_errors = 0
    for case in task.metadata["tests"]:
        try:
            actual = _selector_execute(artifact, case["inputs"]) if task.mechanism == "evidence_verification" else _execute(artifact, case["inputs"])
            expected = case["expected"]
            changed_ok = all(actual[k] == v and not (isinstance(actual[k], bool) != isinstance(v, bool)) for k, v in expected.items() if k in requested)
            protected_ok = all(actual[k] == v and not (isinstance(actual[k], bool) != isinstance(v, bool)) for k, v in expected.items() if k not in requested)
            dimension_passes["requested_behavior"] += changed_ok
            dimension_passes["preserved_behavior"] += protected_ok
            passed += changed_ok and protected_ok
            if not (changed_ok and protected_ok) and len(failures) < 4:
                failures.append({"inputs": case["inputs"], "expected": expected, "actual": actual,
                                 "failed_outputs": [k for k, v in expected.items() if actual[k] != v]})
        except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError, RecursionError) as error:
            runtime_errors += 1
            if len(failures) < 4:
                failures.append({"inputs": case["inputs"], "runtime_error": str(error)})
    total = len(task.metadata["tests"])
    correct = passed == total
    return {"correct": correct, "hard": float(correct), "soft": passed / total, "format_valid": True,
            "artifact_valid": runtime_errors == 0, "parsed_answer": parsed["answer"], "passed_tests": passed,
            "total_tests": total, "dimensions": {k: {"passed": v, "total": total} for k, v in dimension_passes.items()},
            "runtime_errors": runtime_errors, "reason": "all_behavioral_tests_passed" if correct else "behavioral_test_failure",
            "failure_examples": failures}
