"""Pinned public-project-derived, separate-module V4 engineering panel.

These nine identities were already used in the older flattened pilot. They are
NOT an unseen benchmark, canonical SkillEvolBench, or cross-domain evaluation.
Original component bodies and dependency edges are retained where compatible
with the closed eight-module executor. Tiny policy files are co-located, package
imports are renamed, process/file/document requirements are excluded, and an
explicit JSON entry adapter replaces a container agent. Fixtures are ours.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from copy import deepcopy
from functools import lru_cache

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v3.tasks import _schema_valid
from skillopt.validator_pilot import tasks as old

VERSION = "coevolution-v4-pinned-project-adaptation-v1"
NAMES = tuple(name for names in old.SPLIT_TASKS.values() for name in names)
RUNTIME = (
    "All modules remain separate Python namespaces. api.solve(data) is the fixed JSON adapter; "
    "do not edit api.py. Preserve input values, nested types, and dictionary insertion order, "
    "including when raising exceptions. Local imports must name declared flat modules. No file, "
    "network, process, introspection, eval/exec, decorators, inheritance, or special methods except "
    "__init__. Allowed libraries are json, decimal, math, re, hashlib, fixed time.time, copy, csv, "
    "io.StringIO, in-memory sqlite3, and xml.etree.ElementTree, with the restricted executor APIs. "
    "Only declared editable paths may change. Public tests are examples, not the whole contract. "
    "All task inputs satisfy the displayed schema and global bounds: 6000 JSON characters, 256 "
    "nodes, depth 8, 64 elements per container, 2048 characters per string, numeric magnitude 1000000."
)


def _obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required,
            "additionalProperties": False}


STR = {"type": "string", "maxLength": 500}
NUM = {"type": "number", "minimum": -1000000, "maximum": 1000000}
INT = {"type": "integer", "minimum": -10000, "maximum": 10000}
BOOL = {"type": "boolean"}
AMOUNT = {"type": "string", "pattern": r"^-?\d{1,15}(?:\.\d{1,18})?$", "maxLength": 36}
ANY = {}


def _array(item, maximum=16):
    return {"type": "array", "items": item, "maxItems": maximum}


def _enum(*values):
    return {"enum": list(values)}


def _source(name, groups):
    """Retain original bodies, renaming package imports, co-locating tiny files."""
    aliases = {path.removesuffix(".py").replace("/", "."): target.removesuffix(".py")
               for target, paths in groups.items() for path in paths}
    result = {}
    for target, paths in groups.items():
        chunks = []
        for path in paths:
            source = old._read(name, "environment/" + path)
            source = source.split('if __name__ == "__main__":')[0]
            for previous, new in sorted(aliases.items(), key=lambda p: -len(p[0])):
                source = re.sub(r"\bfrom " + re.escape(previous) + r" import", "from " + new + " import", source)
            # A helper merged into its consumer must not import its own module.
            source = re.sub(r"^from " + target.removesuffix(".py") + r" import [^\n]+\n", "", source, flags=re.M)
            source = source.replace('type(record["amount"]).__name__',
                                    '("Decimal" if isinstance(record["amount"], Decimal) else "float")')
            if "isinstance(record[\"amount\"], Decimal)" in source and "from decimal import Decimal" not in source:
                source = "from decimal import Decimal\n" + source
            chunks.append("# Original component: " + path + "\n" + source)
        result[target] = "\n\n".join(chunks)
    return result


def _replace(files, path, before, after):
    result = deepcopy(files)
    if before not in result[path]:
        raise ValueError("pinned adaptation anchor missing: " + path + " / " + before)
    result[path] = result[path].replace(before, after)
    return result


def _case(value, expected=None, preserved=False, public=False, exception=None):
    return {"input": value, "expected": expected, "exception": exception,
            "dimension": "preserved_behavior" if preserved else "requested_behavior", "public": public}


def _project(index, files, reference, schema, clauses, cases, semantic, preservation, alternative=None):
    if alternative is None:
        alternative = deepcopy(reference)
        path = next(path for path in files if path != "api.py")
        # Behavior-equivalent syntactic transformation, not another reference label.
        alternative[path] = ast.unparse(ast.parse(alternative[path])) + "\n"
    return {"name": NAMES[index], "files": files, "reference": reference, "schema": schema,
            "clauses": clauses, "cases": cases, "controls": {"equivalent": alternative,
            "alternative": alternative, "semantic_mutant": semantic, "preservation_mutant": preservation}}


def _etl():
    name = NAMES[0]
    files = _source(name, {"policy.py": ["amount_audit.py", "comparison_policy.py", "formatting_policy.py"],
        **{path: [path] for path in ["extractor.py", "validator.py", "transformer.py", "enricher.py", "loader.py", "pipeline.py"]}})
    files["api.py"] = '''from decimal import Decimal
import extractor
import pipeline
import transformer

def solve(data):
    rows = [{**row, "amount": None if row["amount"] is None else Decimal(row["amount"])} for row in data["rows"]]
    if data["operation"] == "transform":
        result = transformer.transform_batch(rows)
        return [{"id": row["id"], "formatted": row["amount_formatted"], "processed": row["processed"]} for row in result]
    extractor.MOCK_DB = rows
    extractor.HISTORICAL_DB = {int(key): Decimal(value) for key, value in data["history"].items()}
    report = pipeline.run_pipeline()
    return {"total": report["total"], "changed": report["changed_count"], "unchanged": report["unchanged_count"],
            "summary": report["change_summary"], "ids": [row["id"] for row in report["changed_records"] + report["unchanged_records"]]}
'''
    ref = _replace(files, "validator.py", 'record["amount"] = float(record["amount"])',
                   'record["amount"] = Decimal(str(record["amount"]))')
    ref["validator.py"] = "from decimal import Decimal\n" + ref["validator.py"]
    schema = _obj({"operation": _enum("run", "transform"), "rows": _array(_obj({"id": INT, "name": STR,
        "amount": {"anyOf": [AMOUNT, {"type": "null"}]}})), "history": {"type": "object", "additionalProperties": AMOUNT}})
    cases = []
    for i, (amount, previous, changed) in enumerate([
        ("0.30", "0.30", False), ("0.125", "0.125", False), ("1.2300", "1.23", False),
        ("999999999999.99", "999999999999.99", False), ("-0.10", "-0.10", False),
        ("0.30", "0.29", True), ("0", "0.01", True), ("0.002", "0.001", True), ("7.77", None, True)]):
        data = {"operation": "run", "rows": [{"id": 1, "name": "order", "amount": amount}],
                "history": {} if previous is None else {"1": previous}}
        cases.append(_case(data, {"total": 1, "changed": int(changed), "unchanged": int(not changed), "ids": [1],
            "summary": [{"id": 1, "changed": changed, "historical_amount": str(previous)}]}, preserved=changed, public=i in {0, 5}))
    cases += [_case({"operation": "run", "rows": [{"id": 0, "name": "x", "amount": "1"},
        {"id": 2, "name": "", "amount": "1"}, {"id": 3, "name": "x", "amount": None},
        {"id": 4, "name": "zero", "amount": "0"}], "history": {}},
        {"total": 1, "changed": 1, "unchanged": 0, "ids": [4], "summary": [{"id": 4, "changed": True, "historical_amount": "None"}]}, True),
        _case({"operation": "run", "rows": [], "history": {}}, {"total": 0, "changed": 0, "unchanged": 0, "ids": [], "summary": []}, True),
        _case({"operation": "transform", "rows": [{"id": 9, "name": "a", "amount": "1234.50"},
            {"id": 2, "name": "b", "amount": "-0.10"}], "history": {}},
            [{"id": 9, "formatted": "$1,234.50", "processed": True}, {"id": 2, "formatted": "$-0.10", "processed": True}], True)]
    semantic = _replace(ref, "validator.py", 'record["amount"] = Decimal(str(record["amount"]))', 'record["amount"] = float(record["amount"])')
    preservation = _replace(ref, "enricher.py", 'record["changed"] = has_amount_changed(record["amount"], historical)', 'record["changed"] = False')
    clauses = ["Repair precision-induced false changes across extractor, validator, transformer, enricher and loader; preserve exact Decimal values at every intermediate stage.",
        "Historical comparison is numeric exact equality, never a tolerance: genuine changes and absent history must still be marked changed.",
        "Validation intentionally rejects missing/falsy id or name and None amount; zero amount is valid. Preserve report keys, record grouping/order and currency formatting.",
        "The transform operation exposes the original batch transformer independently and must preserve caller rows. History object keys are canonical integer strings. Decimal input strings contain at most 18 digit characters."]
    return _project(0, files, ref, schema, clauses, cases, semantic, preservation)


def _money():
    files = _source(NAMES[1], {"models.py": ["shared/models.py"],
        "policy.py": ["shared/money.py", "service_b/audit_log.py", "service_b/comparison_policy.py"],
        "serialization.py": ["service_a/serialization.py"], "calculator.py": ["service_a/calculator.py"],
        "servicea.py": ["service_a/api.py"], "reconciler.py": ["service_b/reconciler.py"], "serviceb.py": ["service_b/api.py"]})
    files["api.py"] = '''import json
from decimal import Decimal
import models
import servicea
import serviceb

def solve(data):
    models.ORDERS_DB = {"X": {"id": "X", "item": "widget", "quantity": data["quantity"],
        "unit_price": Decimal(data["price"]), "total": Decimal(data["total"])}}
    if data["operation"] == "unknown":
        return serviceb.run_single_reconciliation("missing")
    if data["operation"] == "copy":
        row = models.get_order("X")
        row["item"] = "changed"
        return models.get_order("X")["item"]
    if data["operation"] == "payload":
        return json.loads(servicea.get_order_calculation("X")[0])
    result = serviceb.run_single_reconciliation("X")
    return result["status"]
'''
    ref = _replace(files, "calculator.py", 'return float(quantity) * float(unit_price)', 'return Decimal(str(quantity)) * Decimal(str(unit_price))')
    ref["calculator.py"] = "from decimal import Decimal\n" + ref["calculator.py"]
    ref = _replace(ref, "serialization.py", '"unit_price": float(order["unit_price"])', '"unit_price": format(Decimal(str(order["unit_price"])), "f")')
    ref = _replace(ref, "serialization.py", '"calculated_total": calculated_total', '"calculated_total": format(Decimal(str(calculated_total)), "f")')
    ref["serialization.py"] = "from decimal import Decimal\n" + ref["serialization.py"]
    schema = _obj({"operation": _enum("reconcile", "payload", "unknown", "copy"), "quantity": INT, "price": AMOUNT, "total": AMOUNT})
    cases = []
    for i, (qty, price, total, match) in enumerate([(3, "0.10", "0.30", True), (7, "14.28", "99.96", True),
        (3, "0.10", "0.31", False), (1, "999999999999.99", "999999999999.99", True),
        (2, "-0.15", "-0.30", True), (0, "88.88", "0", True), (5, "0.002", "0.011", False),
        (100, "0.01", "1.00", True), (1, "1.23456789", "1.23456788", False)]):
        cases.append(_case({"operation": "reconcile", "quantity": qty, "price": price, "total": total},
                           "MATCH" if match else "MISMATCH", not match, i in {0, 2}))
    for op, expected in [("unknown", {"id": "missing", "status": "ERROR", "reason": "API call failed"}),
                          ("copy", "widget"), ("payload", {"id": "X", "item": "widget", "quantity": 3,
                           "unit_price": "0.10", "calculated_total": "0.30"})]:
        cases.append(_case({"operation": op, "quantity": 3, "price": "0.10", "total": "0.30"}, expected, op != "payload"))
    semantic = _replace(ref, "calculator.py", 'return Decimal(str(quantity)) * Decimal(str(unit_price))', 'return float(quantity) * float(unit_price)')
    preservation = _replace(ref, "reconciler.py", 'if api_total != db_total:', 'if False:')
    return _project(1, files, ref, schema, ["Repair exact decimal arithmetic across calculator -> JSON payload -> reconciliation.",
        "Money crossing JSON must be decimal-safe text, never binary floats; quantity stays numeric. Preserve payload fields and source row copies.",
        "Reconciliation must use exact numeric Decimal equality without a tolerance; genuine mismatches remain mismatches and unknown IDs retain existing error schemas. Decimal input strings contain at most 18 digit characters."], cases, semantic, preservation)


def _orders():
    files = _source(NAMES[2], {"order.py": ["models/order.py"], "mappers.py": ["database/row_mappers.py"],
        "queries.py": ["database/queries.py"], "policy.py": ["services/price_policy.py"],
        "service.py": ["services/order_service.py"], "serializers.py": ["api/serializers.py"], "routes.py": ["api/routes.py"]})
    files["api.py"] = '''import json
import order
import service
import routes

def solve(data):
    order.ORDERS.clear()
    order.ORDERS["X"] = order.Order("X", "customer", data["quantity"], data["price"], data["stored"])
    if data["operation"] == "unknown":
        raw, status = routes.handle_get_order("missing")
        return {"body": json.loads(raw), "status": status, "recalculated": service.calculate_order_total("missing")}
    if data["operation"] == "copy":
        row = service.get_order("X")
        row["customer"] = "changed"
        return service.get_order("X")["customer"]
    if data["operation"] == "recalculate":
        return str(service.calculate_order_total("X"))
    raw, status = routes.handle_get_order("X")
    return {"body": json.loads(raw), "status": status}
'''
    ref = _replace(files, "order.py", "self.unit_price = unit_price", "self.unit_price = Decimal(str(unit_price))")
    ref = _replace(ref, "order.py", "self.total_amount = float(total_amount)", "self.total_amount = Decimal(str(total_amount))")
    ref = _replace(ref, "order.py", '"unit_price": self.unit_price', '"unit_price": format(self.unit_price, "f")')
    ref = _replace(ref, "order.py", '"total_amount": self.total_amount', '"total_amount": format(self.total_amount.quantize(Decimal("0.01")), "f")')
    ref = _replace(ref, "service.py", 'return order["items_count"] * order["unit_price"]',
                   'return (Decimal(str(order["items_count"])) * Decimal(str(order["unit_price"]))).quantize(Decimal("0.01"))')
    ref["service.py"] = "from decimal import Decimal\n" + ref["service.py"]
    schema = _obj({"operation": _enum("get", "recalculate", "unknown", "copy"), "quantity": INT, "price": AMOUNT, "stored": AMOUNT})
    cases = []
    for i, (qty, price, stored, expected) in enumerate([(3, "0.10", "0.30", "0.30"),
        (7, "7.141428571428571", "49.99", "49.99"), (1, "999999999999.99", "999999999999.99", "999999999999.99"),
        (3, "-0.05", "-0.15", "-0.15"), (0, "12.34", "0", "0.00"), (1, "0.125", "0.12", "0.12"), (1, "0.135", "0.14", "0.14")]):
        for op in ["get", "recalculate"]:
            value = {"operation": op, "quantity": qty, "price": price, "stored": stored}
            outcome = expected if op == "recalculate" else {"body": {"id": "X", "customer": "customer", "items_count": qty,
                "unit_price": price, "total_amount": expected}, "status": 200}
            cases.append(_case(value, outcome, False, i == 0))
    for op, expected in [("unknown", {"body": {"error": "Order not found"}, "status": 404, "recalculated": None}), ("copy", "customer")]:
        cases.append(_case({"operation": op, "quantity": 2, "price": "3.00", "stored": "6.00"}, expected, True, op == "unknown"))
    semantic = _replace(ref, "service.py", ').quantize(Decimal("0.01"))', ').quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")')
    preservation = _replace(ref, "routes.py", '404', '200')
    return _project(2, files, ref, schema, ["Repair model, query, service and JSON API precision without dropping existing fields or not-found behavior.",
        "total_amount in service/JSON must be a decimal-safe string with exactly two fractional digits; unit_price is decimal text retaining necessary precision.",
        "Recalculation multiplies quantity by unit price with Decimal and rounds to cents using ROUND_HALF_EVEN, including exact ties and negative values.",
        "Preserve id/customer/items_count, independent result copies, missing-order None recalculation and 404 JSON error response. Decimal input strings contain at most 18 digit characters."], cases, semantic, preservation)


def _validation():
    files = _source(NAMES[3], {"validators.py": ["validators.py"], "registration.py": ["app.py"]})
    files["api.py"] = '''import validators
import registration

def solve(data):
    op = data["operation"]
    if op == "register":
        return registration.register_user(data["name"], data["email"], data["phone"], data["age"])
    if op == "email":
        return validators.validate_email(data["value"])
    if op == "phone":
        return validators.validate_phone(data["value"])
    if op == "name":
        return validators.validate_name(data["value"])
    if op == "age":
        return validators.validate_age(data["value"])
    return validators.validate_input(data["value"])
'''
    ref = _replace(files, "validators.py", "def validate_input(value):", "def validate_email(value):")
    # Two colliding definitions must receive distinct names, not one global rename.
    first = ref["validators.py"].index("def validate_email(value):")
    tail = ref["validators.py"][first + 1:].replace("def validate_email(value):", "def validate_phone(value):", 1)
    ref["validators.py"] = ref["validators.py"][:first + 1] + tail
    ref["validators.py"] += '\ndef validate_input(value):\n    email = validate_email(value)\n    return email if email["valid"] else validate_phone(value)\n'
    ref["registration.py"] = ref["registration.py"].replace("from validators import validate_input,", "from validators import validate_email, validate_phone,")
    ref["registration.py"] = ref["registration.py"].replace("validate_input(email)", "validate_email(email)").replace("validate_input(phone)", "validate_phone(phone)")
    schema = {"oneOf": [_obj({"operation": _enum("register"), "name": ANY, "email": ANY, "phone": ANY, "age": ANY}),
        _obj({"operation": _enum("email", "phone", "name", "age", "compat"), "value": ANY})]}
    # Expected dictionaries copied from explicit original public API semantics.
    cases = [_case({"operation": "register", "name": "Alice", "email": "alice@example.com", "phone": "1234567890", "age": 25},
        {"success": True, "message": "User registered successfully"}, public=True),
        _case({"operation": "name", "value": "A"}, {"valid": False, "error": "Name too short"}, True, True)]
    for op, val, expected in [
        ("email", "a+b@example.co", {"valid": True, "type": "email"}),
        ("email", "x@y.c", {"valid": False, "error": "Invalid email format"}),
        ("email", None, {"valid": False, "error": "Empty or non-string input"}),
        ("phone", "+1 (234) 567-8900", {"valid": True, "type": "phone"}),
        ("phone", "123456789", {"valid": False, "error": "Invalid phone number format"}),
        ("compat", "x@y.com", {"valid": True, "type": "email"}),
        ("compat", "1234567890", {"valid": True, "type": "phone"}),
        ("age", True, {"valid": True, "type": "age"}),
        ("age", 0, {"valid": True, "type": "age"}),
        ("age", -1, {"valid": False, "error": "Invalid age"}),
        ("name", "Ada", {"valid": True, "type": "name"})]:
        cases.append(_case({"operation": op, "value": val}, expected, op in {"age", "name"}))
    semantic = _replace(ref, "registration.py", "validate_email(email)", "validate_phone(email)")
    preservation = _replace(ref, "validators.py", "not isinstance(value, int)", "(not isinstance(value, int) or isinstance(value, bool))")
    return _project(3, files, ref, schema, ["Resolve the duplicate validator collision: export validate_email and validate_phone, and dispatch registration fields to the matching helper.",
        "For compatibility validate_input accepts either a valid email or a valid phone. Preserve the original regex and phone normalization.",
        "Preserve name and age validation, including Python isinstance(value, int) age acceptance of booleans; do not strengthen unrelated validation.",
        "Preserve success/error dictionary shapes and registration error ordering name/email/phone/age."], cases, semantic, preservation)


def _auth():
    files = _source(NAMES[4], {"auth.py": ["src/auth.py"], "notifications.py": ["src/notifications.py"]})
    # A parsable incorrect branch resolution preserves the semantic merge problem.
    files["auth.py"] = old._resolve_conflicts(files["auth.py"])
    files["api.py"] = '''import auth
import notifications

def solve(data):
    if data["operation"] == "notification":
        return {"sent": notifications.send_notification(8, data["message"]), "items": notifications.get_notifications(8)}
    auth._check_rate_limit = lambda username: data["allowed"]
    return auth.authenticate(data["username"], data["password"], data["remember"])
'''
    ref = _replace(files, "auth.py", '    user = _find_user(username)\n',
        '    if not _check_rate_limit(username):\n        return {"success": False, "error": "Too many attempts. Please wait."}\n    user = _find_user(username)\n')
    ref["auth.py"] += '\ndef _check_rate_limit(username):\n    return True\n'
    schema = {"oneOf": [_obj({"operation": _enum("login"), "username": STR, "password": STR, "remember": BOOL, "allowed": BOOL}),
        _obj({"operation": _enum("notification"), "message": STR})]}
    cases = []
    for i, (user, password, remember, allowed, expected) in enumerate([
        ("admin", "admin123", True, True, {"success": True, "token": "token_1_1700000000_2592000", "remember_me": True}),
        ("admin", "wrong", False, True, {"success": False, "error": "Invalid credentials"}),
        ("admin", "admin123", True, False, {"success": False, "error": "Too many attempts. Please wait."}),
        ("missing", "wrong", False, False, {"success": False, "error": "Too many attempts. Please wait."}),
        ("admin", "admin123", False, True, {"success": True, "token": "token_1_1700000000_3600", "remember_me": False}),
        ("user1", "pass456", True, True, {"success": True, "token": "token_2_1700000000_2592000", "remember_me": True}),
        ("user1", "PASS456", True, True, {"success": False, "error": "Invalid credentials"}),
        ("missing", "x", True, True, {"success": False, "error": "Invalid credentials"}),
        ("user1", "pass456", False, False, {"success": False, "error": "Too many attempts. Please wait."})]):
        cases.append(_case({"operation": "login", "username": user, "password": password, "remember": remember, "allowed": allowed},
                           expected, allowed and not remember, i in {0, 1}))
    cases.append(_case({"operation": "notification", "message": "hello"},
        {"sent": True, "items": [{"id": 1, "message": "Welcome!", "read": False}]}, True))
    semantic = _replace(ref, "auth.py", "if not _check_rate_limit(username):", "if False:")
    preservation = _replace(ref, "auth.py", "expiry = 86400 * 30 if long_lived else 3600", "expiry = 86400 * 30")
    return _project(4, files, ref, schema, ["Repair a semantically incorrect merge resolution that kept remember_me but dropped rate limiting; retain both branches' behavior.",
        "authenticate(username,password,remember_me=False) invokes the caller-replaceable _check_rate_limit hook before user lookup/password verification; denial returns the hotfix error.",
        "Successful login exposes success/token/remember_me, with 3600-second ordinary or 2592000-second remembered lifetime. Preserve invalid-credential and notification behavior.",
        "A fixed clock of 1700000000 makes tokens deterministic; the default rate-limit hook remains always True."], cases, semantic, preservation)


def _integration():
    files = _source(NAMES[5], {"notifications.py": ["src/notifications.py"], "search.py": ["src/search.py"],
        "exporter.py": ["src/export.py"], "application.py": ["src/app.py"]})
    files = {path: old._resolve_conflicts(source) for path, source in files.items()}
    files["api.py"] = '''import csv
import io
import json
import application
import notifications
import search
import exporter

def solve(data):
    db = application.get_db()
    application.setup_database(db)
    for user in data["users"]:
        db.execute("INSERT INTO users (id,name,email) VALUES (?,?,?)", (user["id"], user["name"], user["email"]))
    for event in data["events"]:
        notifications.send_notification(db, event["user"], event["type"], event["text"])
    db.execute("UPDATE user_events SET created_at=?", ("2024-01-01 00:00:00",))
    db.commit()
    op = data["operation"]
    if op == "search":
        return [row["user_id"] for row in search.search_events(db, data["query"], event_type=data["filter"])]
    if op == "types":
        return sorted(row[0] for row in search.get_event_types(db))
    if op == "export":
        return list(csv.reader(io.StringIO(exporter.export_events(db, data["user_id"]))))
    if op == "users":
        return json.loads(exporter.export_users(db, "json"))
    return len(notifications.get_user_notifications(db, data["user_id"]))
'''
    ref = _replace(files, "search.py", "event_type", "type")
    # Preserve the callable argument name; only the SQL column is renamed.
    ref["search.py"] = files["search.py"].replace(" AND event_type = ?", " AND type = ?").replace(
        "SELECT DISTINCT event_type FROM user_events", "SELECT DISTINCT type FROM user_events")
    schema = _obj({"operation": _enum("search", "types", "export", "users", "notifications"),
        "users": _array(_obj({"id": INT, "name": STR, "email": STR})),
        "events": _array(_obj({"user": INT, "type": STR, "text": STR})), "query": STR,
        "filter": {"anyOf": [STR, {"type": "null"}]}, "user_id": {"anyOf": [INT, {"type": "null"}]}})
    common = {"users": [{"id": 1, "name": "Alice", "email": "a@x.test"}, {"id": 2, "name": "Bob", "email": "b@x.test"}],
        "events": [{"user": 1, "type": "login", "text": "User logged in"}, {"user": 1, "type": "purchase", "text": "Bought item"},
                   {"user": 2, "type": "login", "text": "Second logged in"}], "query": "", "filter": None, "user_id": None}
    cases = []
    specs = [("search", {"filter": "purchase"}, [1], False), ("notifications", {"user_id": 1}, 2, True),
        ("types", {}, ["login", "purchase"], False), ("search", {"query": "Second", "filter": "login"}, [2], False),
        ("search", {"filter": "absent"}, [], False), ("search", {"filter": "login' OR 1=1 --"}, [], True),
        ("search", {"query": "logged"}, [1, 2], True), ("search", {"filter": ""}, [1, 1, 2], True),
        ("users", {}, common["users"], True)]
    for i, (op, update, expected, preserved) in enumerate(specs):
        cases.append(_case({**deepcopy(common), "operation": op, **update}, expected, preserved, i < 2))
    header = ["id", "user_id", "type", "description", "created_at"]
    rows = [["1", "1", "login", "User logged in", "2024-01-01 00:00:00"],
            ["2", "1", "purchase", "Bought item", "2024-01-01 00:00:00"],
            ["3", "2", "login", "Second logged in", "2024-01-01 00:00:00"]]
    cases += [_case({**deepcopy(common), "operation": "export", "user_id": uid}, [header] + selected, True)
              for uid, selected in [(1, rows[:2]), (0, rows), (None, rows)]]
    semantic = _replace(ref, "search.py", " AND type = ?", " AND event_type = ?")
    preservation = _replace(ref, "exporter.py", "if user_id:", "if user_id is not None:")
    return _project(5, files, ref, schema, ["Repair agreement among notification, search and export modules on the actual user_events schema; its event-type column is named type.",
        "Preserve parameterized SQL, combined text/type filters, CSV header/data alignment, JSON users and notification return values.",
        "Optional filters preserve the upstream truthy convention: None, 0 or empty string means no filter, not an exact-zero filter.",
        "Inputs contain distinct user IDs and email addresses, and events refer to declared users. All SQL runs in a real in-memory database."], cases, semantic, preservation)


def _pipeline():
    files = _source(NAMES[6], {path: [path] for path in ["input_contracts.py", "legacy_formatter.py", "stage_runtime.py", "stage_contracts.py", "pipeline.py", "cli_wrapper.py"]})
    files["api.py"] = '''import pipeline
import cli_wrapper

def solve(data):
    value = data["value"]
    op = data["operation"]
    if op == "new":
        return pipeline.Pipeline().run(value)
    if op == "run":
        return pipeline.run_pipeline(value)
    if op == "parse":
        return pipeline.parse(value)
    if op == "transform":
        return pipeline.transform(value)
    if op == "format":
        return pipeline.format_output(value)
    return cli_wrapper.run_from_cli(value)
'''
    ref = deepcopy(files)
    ref["pipeline.py"] += '\nclass Pipeline:\n    def run(self, value):\n        return run_pipeline(value)\n'
    schema = _obj({"operation": _enum("new", "run", "parse", "transform", "format", "cli"), "value": ANY})
    specs = [("new", {"name": "alice"}, '{"_transformed": true, "name": "alice"}', False, None),
        ("run", "", '{"_default": true}', True, None), ("parse", None, {}, True, None),
        ("transform", None, None, True, None), ("format", None, "", True, None),
        ("new", None, '{"_default": true}', False, None), ("new", "null", "", False, None),
        ("transform", {"_transformed": False, "x": 0}, {"_transformed": True, "x": 0}, True, None),
        ("new", "{bad", None, False, "JSONDecodeError"), ("cli", None, '{"_default": true}', True, None),
        ("new", {"name": "bob"}, '{"_transformed": true, "name": "bob"}', False, None),
        ("run", {}, '{"_default": true}', True, None), ("parse", "", {}, True, None),
        ("transform", {}, {"_default": True}, True, None), ("format", {}, "{}", True, None),
        ("new", {}, '{"_default": true}', False, None), ("new", {"name": "中文"}, '{"_transformed": true, "name": "\\u4e2d\\u6587"}', False, None),
        ("new", 23, None, False, "TypeError"), ("new", "false", None, False, "TypeError"),
        ("cli", {"z": 2, "a": 1}, '{"_transformed": true, "a": 1, "z": 2}', True, None)]
    cases = [_case({"operation": op, "value": value}, expected, preserved, i in {0, 1, 10, 11}, exception)
             for i, (op, value, expected, preserved, exception) in enumerate(specs)]
    semantic = _replace(ref, "pipeline.py", "return run_pipeline(value)", 'return run_pipeline(value) if value else ""')
    # This mutant incorrectly merges stage-specific None and empty-map behavior.
    preservation = _replace(ref, "pipeline.py", "if should_skip_transform(value):", "if not value:")
    return _project(6, files, ref, schema, ["Add Pipeline().run(value), preserving module-level parse, transform, format_output, run_pipeline and CLI functions.",
        "Stage boundaries differ intentionally: parse(None) and parse('') produce {}; transform(None) returns None but transform({}) returns {'_default': True}; format_output(None) returns ''.",
        "Running the full chain on None or empty string yields the JSON default marker; JSON null yields empty output. Preserve invalid-JSON and unsupported-type exceptions.",
        "Preserve sorted JSON keys, Unicode escaping, marker overwrite semantics and caller dictionary copy isolation."], cases, semantic, preservation)


def _analyzer():
    files = _source(NAMES[7], {"analyzer.py": ["analyzer.py"]})
    # The annotation-future directive was inert here; the sandbox omits it.
    files["analyzer.py"] = old._combine(NAMES[7], ["analyzer.py"])
    files["statistics_core.py"] = '"""Extract reusable numeric helpers here while preserving analyzer.analyze_data."""\n'
    files["api.py"] = 'import analyzer\n\ndef solve(data):\n    return analyzer.analyze_data(data["values"])\n'
    tree = ast.parse(old.ANALYZER_REFERENCE)
    helper_nodes = [node for node in tree.body if not isinstance(node, ast.FunctionDef) or node.name != "analyze_data"]
    entry = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "analyze_data")
    ref = deepcopy(files)
    ref["statistics_core.py"] = ast.unparse(ast.Module(body=helper_nodes, type_ignores=[])) + "\n"
    # Unlike the older flattened adapter, do not add a new error=None key to
    # legacy nonempty reports: those exact upstream schemas are preserved.
    ref["statistics_core.py"] = ref["statistics_core.py"].replace(", 'error': None", "")
    ref["analyzer.py"] = "from statistics_core import validate_values, calculate_statistics, detect_outliers, build_report\n\n" + ast.unparse(entry) + "\n"
    schema = _obj({"values": {"anyOf": [_array(ANY, 32), {"type": "null"}]}})
    values = [[], [1], [-1, 0, 1], [1, 1, 1, 1, 100], [7, 7, 7, 7], [-7, -3, -1], [True, False, True], None,
              [1, "2", 3], [1, 2, 3, 4], [], [2], [-2, 0, 2], [2, 2, 2, 2, 200], [8, 8, 8],
              [-200, -150, 20], [False, True], None, [4, "five"], [1.5, 2.5, 2.5]]
    # Duplicate empty/None inputs cannot straddle gate/final; use disjoint wrappers
    # with a contract-neutral marker only in metadata? No: instead distinct
    # error/empty representations are unavailable. Place them only in gate.
    values[10] = [0, 0, 0, 1]
    values[17] = ["bad"]
    empty = {"count": 0, "mean": 0.0, "median": 0.0, "stddev": 0.0, "q1": 0.0, "q3": 0.0,
        "outliers": [], "spread": 0.0, "negative_ratio": 0.0, "zero_ratio": 0.0, "report": "empty_input",
        "zero_count": 0, "error": "empty input", "value_buckets": {"negative": 0, "zero": 0, "positive": 0},
        "percentile_window": {"lower": 0.0, "upper": 0.0, "iqr": 0.0}, "has_zero_crossing": False}
    cases = []
    for i, value in enumerate(values):
        exception = "ValueError" if value is None else "TypeError" if any(not isinstance(x, (int, float)) for x in value) else None
        expected = None if exception else empty if not value else old._statistics_expected(value)
        if value and exception is None:
            expected.pop("error")
        cases.append(_case({"values": value}, expected, bool(value) and exception is None, i in {0, 1, 10, 11}, exception))
    semantic = _replace(ref, "analyzer.py", "if not cleaned:", "if cleaned is None:")
    # Held-out side needs a requested-behavior failing control too; changing the
    # helper's empty branch would only fail gate, so also break input validation.
    semantic = _replace(semantic, "statistics_core.py", "raise TypeError('all values must be numeric')", "raise ValueError('all values must be numeric')")
    preservation = deepcopy(ref)
    preservation["statistics_core.py"] = preservation["statistics_core.py"].replace("isinstance(value, (int, float))", "(isinstance(value, (int, float)) and not isinstance(value, bool))")
    return _project(7, files, ref, schema, ["Refactor analyzer helpers into statistics_core while preserving analyze_data and all nonempty distribution semantics; fix empty-input division failure.",
        "Empty input returns the documented zero-valued report, error 'empty input', empty outliers/buckets, and report 'empty_input'; None raises ValueError and nonnumeric members raise TypeError.",
        "Use population standard deviation and rank-index quartiles (n//4, 3*n//4), preserving outlier bounds, report precedence, buckets, zero crossing and float normalization.",
        "Python numeric compatibility intentionally accepts bool values as 0/1; preserve it and never sort/mutate the caller list."], cases, semantic, preservation)


def _processor():
    files = _source(NAMES[8], {"sink.py": ["fake_sink_adapter.py"], "processor.py": ["processor.py"]})
    source = files["processor.py"]
    start = source.index('    if destination == "file":')
    end = source.index('    raise ValueError(f"unsupported destination', start)
    files["processor.py"] = "import copy\n" + source[:start] + '    if destination == "file":\n        raise ValueError("file destination disabled in sandbox adaptation")\n' + source[end:]
    files["api.py"] = '''import json
import processor

def plugin(kind, amount):
    def apply(rows):
        if kind == "plus":
            return [{**row, "amount": row.get("amount", 0) + amount} for row in rows]
        if kind == "double":
            return [{**row, "amount": row.get("amount", 0) * 2} for row in rows]
        if kind == "drop":
            return []
        if rows:
            rows[0]["amount"] = 999
            if "nested" in rows[0]:
                rows[0]["nested"]["x"] = 999
        if kind == "raise":
            raise ValueError("plugin failed")
        return None
    return apply

def solve(data):
    if data["operation"] == "legacy":
        return processor.process(data["raw"], input_format=data["format"], mode=data["mode"], destination=data["destination"])
    engine = processor.Processor()
    for spec in data["plugins"]:
        engine.register_plugin(spec["name"], plugin(spec["kind"], spec["amount"]), spec["order"])
    if data["operation"] == "isolation":
        engine = processor.Processor()
    return engine.process(data["raw"], input_format=data["format"], mode=data["mode"], destination=data["destination"])
'''
    ref = deepcopy(files)
    ref["processor.py"] += old.PROCESSOR_EXTENSION
    schema = _obj({"operation": _enum("legacy", "plugins", "isolation"), "raw": STR,
        "format": _enum("json", "csv", "xml"), "mode": _enum("identity", "uppercase", "filter-positive"),
        "destination": _enum("memory", "json", "api", "absent"), "plugins": _array(_obj({"name": STR,
            "kind": _enum("plus", "double", "drop", "raise", "invalid"), "amount": NUM, "order": INT}))})
    base = {"operation": "plugins", "raw": '[{"name":"a","amount":"2","nested":{"x":1}}]',
            "format": "json", "mode": "identity", "destination": "memory", "plugins": []}
    def spec(kind, order=0, amount=1, name=None):
        return {"name": name or kind, "kind": kind, "amount": amount, "order": order}
    def ok(amount=2, name="a", nested=True):
        row = {"name": name, "amount": float(amount)}
        if nested:
            row["nested"] = {"x": 1}
        return {"status": "ok", "result": [row]}
    cases = []
    entries = [({"plugins": [spec("plus")]}, ok(3), False), ({"operation": "legacy"}, ok(), True),
        ({"plugins": [spec("raise"), spec("plus", 1)]}, ok(3), False),
        ({"plugins": [spec("invalid")]}, ok(), False),
        ({"plugins": [spec("double", 20), spec("plus", 10), spec("plus", 20, 3, "last")]}, ok(9), False),
        ({"operation": "isolation", "plugins": [spec("drop")]}, ok(), False),
        ({"destination": "api", "raw": "[]"}, {"status": "ok", "result": {"rows": 0, "transport": "fake"}}, False),
        ({"operation": "legacy", "raw": "name,amount\nalice,3\n", "format": "csv", "mode": "uppercase"}, ok(3, "ALICE", False), True),
        ({"operation": "legacy", "raw": "<rows><row><name> bob </name><amount>2</amount></row></rows>", "format": "xml"}, ok(2, "bob", False), True),
        ({"operation": "legacy", "destination": "json", "raw": "[]"}, {"status": "ok", "result": "[]"}, True),
        ({"plugins": [spec("plus", amount=2)]}, ok(4), False),
        ({"operation": "legacy", "raw": '[{"name":"b","amount":"4"}]'}, ok(4, "b", False), True),
        ({"plugins": [spec("raise"), spec("plus", 1, 2)]}, ok(4), False),
        ({"plugins": [spec("invalid"), spec("double", 1)]}, ok(4), False),
        ({"plugins": [spec("double", 3), spec("plus", 2, 2), spec("plus", 3, 4, "tail")]}, ok(12), False),
        ({"operation": "isolation", "plugins": [spec("plus", amount=50)]}, ok(), False),
        ({"destination": "api"}, {"status": "ok", "result": {"rows": 1, "transport": "fake"}}, False),
        ({"operation": "legacy", "raw": "name,amount\nzoe,6\n", "format": "csv", "mode": "uppercase"}, ok(6, "ZOE", False), True),
        ({"operation": "legacy", "raw": "<rows><row><name> eve </name><amount>7</amount></row></rows>", "format": "xml"}, ok(7, "eve", False), True),
        ({"operation": "legacy", "raw": '[{"amount":"0"},{"amount":"2"}]', "mode": "filter-positive"},
            {"status": "ok", "result": [{"amount": 2.0}]}, True)]
    for i, (update, expected, preserved) in enumerate(entries):
        cases.append(_case({**deepcopy(base), **update}, expected, preserved, i in {0, 1, 10, 11}))
    semantic = _replace(ref, "processor.py", "trial = copy.deepcopy(rows)", "trial = rows")
    preservation = _replace(ref, "processor.py", 'value.upper()', 'value.lower()')
    return _project(8, files, ref, schema, ["Add an instance-isolated Processor with register_plugin(name,function,order=0) and process matching the legacy API.",
        "Plugins receive normalized/coerced row lists before output, run by increasing order with stable ties, and return lists of dictionaries; duplicate names raise ValueError.",
        "On exception or invalid return, discard ALL tentative plugin mutations, including nested objects, retain previous rows, and continue later plugins. Separate instances must not share registration.",
        "Preserve legacy JSON/CSV/XML parsing, trimming, amount coercion, uppercase/filter-positive modes, memory/JSON/fake-API output and error shapes. File output is explicitly disabled; registration replaces filesystem discovery."], cases, semantic, preservation)


@lru_cache(maxsize=1)
def _projects():
    return [_etl(), _money(), _orders(), _validation(), _auth(), _integration(), _pipeline(), _analyzer(), _processor()]


def validate_input(task: RepoTask | str, value) -> bool:
    """Reject unsupported or resource-unbounded probes before reference execution."""
    try:
        identifier = task if isinstance(task, str) else task.id
        project = next(p for p in _projects() if identifier.startswith("repo-v4-" + p["name"] + "-"))
        if not isinstance(value, dict) or len(json.dumps(value, allow_nan=False)) > 6000:
            return False
        nodes = 0
        def visit(item, depth=0):
            nonlocal nodes
            nodes += 1
            if nodes > 256 or depth > 8:
                raise ValueError("input bounds")
            if isinstance(item, dict):
                if len(item) > 64 or any(type(k) is not str for k in item):
                    raise ValueError("object bounds")
                for key, child in item.items():
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            elif isinstance(item, list):
                if len(item) > 64:
                    raise ValueError("array bounds")
                for child in item:
                    visit(child, depth + 1)
            elif isinstance(item, str):
                if len(item) > 2048:
                    raise ValueError("string bounds")
            elif item is None or type(item) is bool:
                pass
            elif type(item) in {int, float}:
                if not math.isfinite(item) or abs(item) > 1000000:
                    raise ValueError("numeric bounds")
            else:
                raise ValueError("non JSON input")
        visit(value)
        if not _schema_valid(value, project["schema"]):
            return False
        if project["name"] == NAMES[0]:
            if any(not re.fullmatch(r"-?(?:0|[1-9]\d{0,4})", key) or not -10000 <= int(key) <= 10000 or str(int(key)) != key for key in value["history"]):
                return False
            if value["operation"] == "transform" and any(row["amount"] is None for row in value["rows"]):
                return False
        if project["name"] in NAMES[:3]:
            amounts = ([row["amount"] for row in value["rows"]] + list(value["history"].values())
                       if project["name"] == NAMES[0] else [value[key] for key in ("price", "total" if project["name"] == NAMES[1] else "stored")])
            if any(amount is not None and sum(character.isdigit() for character in amount) > 18 for amount in amounts):
                return False
        if project["name"] == NAMES[5]:
            users = value["users"]
            if len({u["id"] for u in users}) != len(users) or len({u["email"] for u in users}) != len(users):
                return False
            if any(event["user"] not in {u["id"] for u in users} for event in value["events"]):
                return False
        return True
    except (ValueError, TypeError, KeyError, StopIteration, OverflowError, RecursionError):
        return False


def input_valid(task_id: str, value) -> bool:
    return validate_input(task_id, value)


def build_tasks() -> list[RepoTask]:
    """Six learning identities, three gate/final project pairs, twelve bundles."""
    tasks = []
    for index, project in enumerate(_projects()):
        phases = [("learn" + str(index // 2), project["cases"])] if index < 6 else [
            ("gate", project["cases"][:10]), ("holdout", project["cases"][10:])]
        for phase, cases in phases:
            cases = deepcopy(cases)
            for number, case in enumerate(cases):
                case["label"] = project["name"] + "-" + phase + "-" + str(number)
            paths = sorted(p for p in (old.ASSETS / project["name"]).rglob("*.py") if "public_tests" not in p.parts)
            metadata = {"version": VERSION, "domain": "coding", "project": project["name"], "phase": phase,
                "round": index // 2 if index < 6 else index - 6, "upstream_commit": old.UPSTREAM_COMMIT,
                "upstream": old.UPSTREAM, "previous_exposure": "All nine identities appeared in the older flattened pilot; this is development engineering, not unseen benchmark generalization.",
                "adaptation": "Separate original component bodies/imports; tiny policies co-located; flat package aliases; fixed JSON adapter; file/process/docs checks excluded; explicit incorrect branch resolution replaces merge-marker syntax errors.",
                "source_files": [{"path": str(path.relative_to(old.ASSETS)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths],
                "controls": deepcopy(project["controls"]), "oracle": "Manually stated behavioral fixtures; statistics use pre-existing independent host calculator, never candidate/reference execution.",
                "control_labels": {"equivalent": "AST-rendered equivalent, not an independently designed algorithm",
                    "semantic_mutant": "Controlled requested-behavior damage, not a natural model failure",
                    "preservation_mutant": "Controlled preserved-behavior damage; may also affect requested behavior"},
                "independence": "Gate and final use distinct fixtures from the SAME project. Repeats and fixtures are not independent project identities. All tasks remain Coding.",
                "license": "Upstream license unresolved; local research only, review before redistribution."}
            contract = "\n".join("C" + str(i + 1) + ": " + clause for i, clause in enumerate(project["clauses"]))
            task = RepoTask("repo-v4-" + project["name"] + "-" + phase, phase, project["name"], "repo-v4-" + project["name"],
                contract + "\nRUNTIME: " + RUNTIME, deepcopy(project["files"]), deepcopy(project["reference"]),
                [path for path in project["files"] if path != "api.py"], deepcopy(project["schema"]),
                [case for case in cases if case["public"]], [case for case in cases if not case["public"]], metadata)
            if not all(validate_input(task, case["input"]) for case in cases):
                raise ValueError("fixture outside explicit input contract: " + task.id)
            tasks.append(task)
    return tasks
