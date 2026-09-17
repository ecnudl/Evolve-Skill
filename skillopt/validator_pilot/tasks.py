"""Pinned, explicitly adapted SkillEvolBench Python repair pilot and hard oracle.

Nine original public task identities, three family-disjoint splits. This is NOT
canonical SkillEvolBench: modules are flattened, file/document/process checks
are excluded, and independent behavioral fixtures replace upstream verifiers.
Private expected answers never enter the candidate subprocess or model prompt.
Generated code is NEVER run without macOS sandbox-exec; other hosts fail closed.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import subprocess
import sys
import textwrap
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

VERSION = "validator-pilot-tasks-v1"
UPSTREAM_COMMIT = "9e3daa339987c3cfa624121e1be442593a53d43c"
UPSTREAM = "https://github.com/AIoT-MLSys-Lab/SkillEvolBench"
ASSETS = Path(__file__).resolve().parents[2] / "configs/validator_pilot/tasks/upstream"
SPLIT_TASKS = {
    "train": (
        "five-file-data-pipeline-type-cascade",
        "json-float-precision-across-services",
        "cross-layer-fix-plus-integration-test-plus-docs",
    ),
    "dev": (
        "auto-merge-success-semantic-conflict",
        "resolve-conflicts-to-unblock-release",
        "three-way-merge-plus-integration-validation",
    ),
    "holdout": (
        "refactor-breaks-none-handling-chain",
        "refactor-extract-test-add-coverage",
        "refactor-god-module-before-adding-plugin-system",
    ),
}
FAMILIES = {
    "train": "E1-LS4-multi-file-bug-fix",
    "dev": "E1-LS5-merge-conflict-resolution",
    "holdout": "E1-LS3-safe-refactoring",
}
ALLOWED_IMPORTS = {
    "json",
    "decimal",
    "math",
    "re",
    "hashlib",
    "time",
    "csv",
    "io",
    "sqlite3",
    "xml.etree.ElementTree",
    "copy",
}
FORBIDDEN_NAMES = {
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "help",
    "dir",
    "breakpoint",
    "memoryview",
    "exit",
    "quit",
}


@dataclass(frozen=True)
class Task:
    id: str
    split: str
    family: str
    cluster_id: str
    prompt: str
    starter_code: str
    reference_code: str
    public_cases: list[dict[str, Any]]
    private_cases: list[dict[str, Any]]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Task":
        return cls(**{key: value[key] for key in cls.__dataclass_fields__})


def _read(name: str, relative: str) -> str:
    return (ASSETS / name / relative).read_text(encoding="utf-8")


def _combine(name: str, files: list[str]) -> str:
    """Flatten local imports only; preserve upstream function implementations."""
    chunks = []
    for filename in files:
        source = _read(name, "environment/" + filename)
        # Imports may have multiline local symbol lists. Safe stdlibs retained.
        lines, result, skipping = source.splitlines(), [], False
        for line in lines:
            if skipping:
                skipping = ")" not in line
                continue
            match = re.match(r"^(from|import)\s+([\w.]+)", line)
            if match and match.group(2) not in ALLOWED_IMPORTS:
                skipping = "(" in line and ")" not in line
                continue
            if line.startswith('if __name__ == "__main__":'):
                break
            result.append(line)
        source = "\n".join(result)
        source = source.replace(
            'type(record["amount"]).__name__', '("Decimal" if isinstance(record["amount"], Decimal) else "float")'
        )
        chunks.append(f"# Original component: {filename}\n{source}\n")
    return "\n\n".join(chunks)


def _resolve_conflicts(source: str, choose: str = "theirs") -> str:
    lines, out, ours, theirs, mode = source.splitlines(), [], [], [], None
    for line in lines:
        if line.startswith("<<<<<<<"):
            mode, ours, theirs = "ours", [], []
        elif line.startswith("=======") and mode:
            mode = "theirs"
        elif line.startswith(">>>>>>>") and mode:
            out.extend(ours if choose == "ours" else theirs)
            mode = None
        elif mode == "ours":
            ours.append(line)
        elif mode == "theirs":
            theirs.append(line)
        else:
            out.append(line)
    if mode:
        raise ValueError("unterminated upstream merge conflict")
    return "\n".join(out) + "\n"


def _case(
    label: str,
    expr: str,
    expected: Any = None,
    *,
    requested: bool = False,
    setup: str = "",
    public: bool = False,
    exception: str | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "expr": expr,
        "setup": setup,
        "expected": expected,
        "dimension": "requested_behavior" if requested else "preserved_behavior",
        "public": public,
        "exception": exception,
    }


def _etl(name: str) -> tuple[str, str, str, list[dict[str, Any]]]:
    files = [
        "amount_audit.py",
        "comparison_policy.py",
        "formatting_policy.py",
        "extractor.py",
        "validator.py",
        "transformer.py",
        "enricher.py",
        "loader.py",
        "pipeline.py",
    ]
    source = _combine(name, files)
    ref = source.replace(
        'record["amount"] = float(record["amount"])', 'record["amount"] = Decimal(str(record["amount"]))'
    )
    contract = "Fix precision-induced false change detection throughout this flattened ETL pipeline. Preserve genuine changes, new-record handling, validation rejection, currency formatting, input order, and the existing report keys. Decimal source values must not lose precision at any intermediate stage. Existing validators intentionally reject a missing/falsy id or name and None amount; do not change those rules. Decimal-valued report fields are normalized to decimal text by the harness, not rounded for scoring."
    cases = [
        _case(
            "default unchanged records",
            '(run_pipeline()["changed_count"], run_pipeline()["unchanged_count"])',
            [0, 5],
            requested=True,
            public=True,
        ),
        _case(
            "report keys",
            "sorted(run_pipeline().keys())",
            sorted(
                ["total", "changed_count", "unchanged_count", "changed_records", "unchanged_records", "change_summary"]
            ),
            public=True,
        ),
    ]
    for i, (amount, old, changed) in enumerate(
        [
            ("0.10", "0.10", False),
            ("999999999999.99", "999999999999.99", False),
            ("0.30", "0.29", True),
            ("0", "0.01", True),
            ("-0.10", "-0.10", False),
            ("123.456789", "123.456788", True),
            ("1.2300", "1.23", False),
            ("7.77", None, True),
        ]
    ):
        setup = f'MOCK_DB=[{{"id":71,"name":"case","amount":Decimal({amount!r})}}]\nHISTORICAL_DB=' + (
            "{}" if old is None else "{71:Decimal(" + repr(old) + ")}"
        )
        cases.append(
            _case(
                f"amount path {i}",
                '(run_pipeline()["changed_count"],run_pipeline()["change_summary"][0]["changed"])',
                [int(changed), changed],
                setup=setup,
                requested=not changed,
            )
        )
    cases += [
        _case(
            "invalid excluded and zero accepted",
            'run_pipeline()["total"]',
            1,
            setup='MOCK_DB=[{"id":0,"name":"x","amount":Decimal("1")},{"id":2,"name":"","amount":Decimal("1")},{"id":3,"name":"x","amount":None},{"id":4,"name":"z","amount":Decimal("0")}]\nHISTORICAL_DB={}',
        ),
        _case(
            "mixed order and formatting",
            '[(r["id"],r["amount_formatted"],r["processed"]) for r in transform_batch(validate_batch(extract_records()))]',
            [[9, "$1,234.50", True], [2, "$-0.10", True]],
            setup='MOCK_DB=[{"id":9,"name":"a","amount":Decimal("1234.50")},{"id":2,"name":"b","amount":Decimal("-0.10")}]',
        ),
        _case(
            "nonempty historical summaries retained",
            'run_pipeline()["change_summary"][0]["historical_amount"]',
            "100.50",
        ),
        _case(
            "batch transform leaves original dictionaries",
            '([r["processed"] for r in transform_batch(original)], "processed" in original[0])',
            [[True], False],
            setup='original=[{"id":1,"amount":Decimal("1.00")}]',
        ),
    ]
    return source, ref, contract, cases


def _money(name: str) -> tuple[str, str, str, list[dict[str, Any]]]:
    files = [
        "shared/models.py",
        "shared/money.py",
        "service_a/serialization.py",
        "service_a/calculator.py",
        "service_a/api.py",
        "service_b/audit_log.py",
        "service_b/comparison_policy.py",
        "service_b/reconciler.py",
        "service_b/api.py",
    ]
    source = _combine(name, files)
    ref = (
        source.replace(
            "return float(quantity) * float(unit_price)", "return Decimal(str(quantity)) * Decimal(str(unit_price))"
        )
        .replace(
            '"unit_price": float(order["unit_price"])', '"unit_price": format(Decimal(str(order["unit_price"])), "f")'
        )
        .replace(
            '"calculated_total": calculated_total', '"calculated_total": format(Decimal(str(calculated_total)), "f")'
        )
    )
    contract = "Fix decimal precision across calculator -> JSON payload -> reconciliation. Preserve all function APIs and payload keys. Money crossing JSON must be decimal-safe text (not binary floats); text may retain scale, comparison is numeric Decimal equality with no tolerance masking genuine differences. Quantity remains numeric. Unknown IDs retain the existing status/error schemas, all mismatches retain diagnostics, and source database rows must not be mutated."
    cases = [
        _case(
            "fractional known order",
            'run_single_reconciliation("ORD001")',
            {"id": "ORD001", "status": "MATCH"},
            requested=True,
            public=True,
        ),
        _case(
            "unknown order schema",
            'run_single_reconciliation("missing")',
            {"id": "missing", "status": "ERROR", "reason": "API call failed"},
            public=True,
        ),
    ]
    for i, (qty, price, total, match) in enumerate(
        [
            (7, "14.28", "99.96", True),
            (3, "0.10", "0.30", True),
            (3, "0.10", "0.31", False),
            (1, "999999999999.99", "999999999999.99", True),
            (2, "-0.15", "-0.30", True),
            (0, "88.88", "0", True),
            (5, "0.002", "0.011", False),
            (100, "0.01", "1.00", True),
        ]
    ):
        setup = f'ORDERS_DB={{"X":{{"id":"X","item":"widget","quantity":{qty},"unit_price":Decimal({price!r}),"total":Decimal({total!r})}}}}'
        cases.append(
            _case(
                f"cross service path {i}",
                'run_single_reconciliation("X")["status"]',
                "MATCH" if match else "MISMATCH",
                setup=setup,
                requested=match,
            )
        )
    cases += [
        _case(
            "safe payload types and values",
            '(isinstance(json.loads(get_order_calculation("ORD001")[0])["unit_price"],str),isinstance(json.loads(get_order_calculation("ORD001")[0])["calculated_total"],str),Decimal(json.loads(get_order_calculation("ORD001")[0])["calculated_total"])==Decimal("0.30"))',
            [True, True, True],
            requested=True,
        ),
        _case(
            "payload schema",
            'sorted(json.loads(get_order_calculation("ORD001")[0]))',
            sorted(["id", "item", "quantity", "unit_price", "calculated_total"]),
        ),
        _case(
            "all reconciliation counts",
            "run_full_reconciliation()",
            {"total": 5, "matches": 5, "mismatches": 0, "mismatch_details": []},
            requested=True,
        ),
        _case(
            "unknown database result",
            'reconcile_order(json.dumps({"id":"unknown","calculated_total":"1.00"}))',
            {"id": "unknown", "status": "ERROR", "reason": "Order not found in DB"},
        ),
        _case(
            "source copy isolation",
            '(get_order("ORD001")["unit_price"]==Decimal("0.10"),get_all_orders()["ORD001"]["quantity"])',
            [True, 3],
            setup='copy_row=get_order("ORD001")\ncopy_row["unit_price"]=Decimal("9")\ncopy_all=get_all_orders()\ncopy_all["ORD001"]["quantity"]=88',
        ),
    ]
    return source, ref, contract, cases


def _orders(name: str) -> tuple[str, str, str, list[dict[str, Any]]]:
    files = [
        "models/order.py",
        "database/row_mappers.py",
        "database/queries.py",
        "services/price_policy.py",
        "services/order_service.py",
        "api/serializers.py",
        "api/routes.py",
    ]
    source = _combine(name, files)
    ref = (
        source.replace("self.unit_price = unit_price", "self.unit_price = Decimal(str(unit_price))")
        .replace("self.total_amount = float(total_amount)", "self.total_amount = Decimal(str(total_amount))")
        .replace('"unit_price": self.unit_price', '"unit_price": format(self.unit_price, "f")')
        .replace(
            '"total_amount": self.total_amount',
            '"total_amount": format(self.total_amount.quantize(Decimal("0.01")), "f")',
        )
        .replace(
            'return order["items_count"] * order["unit_price"]',
            'return (Decimal(str(order["items_count"])) * Decimal(str(order["unit_price"]))).quantize(Decimal("0.01"))',
        )
    )
    contract = "Fix model/query/service/API precision without dropping fields or not-found behavior. total_amount must be a decimal-precise string with exactly two fractional digits in service and JSON results; unit_price must be decimal-safe text retaining necessary precision. Recalculation multiplies quantity and unit_price with Decimal semantics and rounds to cents using ROUND_HALF_EVEN (Python Decimal default). Preserve database order, customer/id/items_count, independent copies, and 404 responses. File edits, documentation and coverage-tool requirements of the original task are outside this single-module adaptation."
    cases = [
        _case(
            "known total is safe text",
            'json.loads(handle_get_order("ORD-1003")[0])["total_amount"]',
            "0.30",
            requested=True,
            public=True,
        ),
        _case(
            "not found",
            '(json.loads(handle_get_order("missing")[0]),handle_get_order("missing")[1],get_order("missing"))',
            [{"error": "Order not found"}, 404, None],
            public=True,
        ),
    ]
    for i, (qty, price, stored, expected) in enumerate(
        [
            (3, "0.10", "0.30", "0.30"),
            (7, "7.141428571428571", "49.99", "49.99"),
            (1, "999999999999.99", "999999999999.99", "999999999999.99"),
            (3, "-0.05", "-0.15", "-0.15"),
            (0, "12.34", "0", "0.00"),
            (1, "0.125", "0.12", "0.12"),
            (1, "0.135", "0.14", "0.14"),
        ]
    ):
        setup = f'ORDERS={{"X":Order("X","customer",{qty},{price!r},{stored!r})}}'
        cases.append(
            _case(
                f"order roundtrip {i}",
                '(get_order("X")["total_amount"],Decimal(str(calculate_order_total("X")))==Decimal('
                + repr(expected)
                + "))",
                [stored if "." in stored else stored + ".00", True],
                setup=setup,
                requested=True,
            )
        )
    cases += [
        _case(
            "list identity preserved",
            '[(r["id"],r["customer"],r["items_count"]) for r in list_orders()]',
            [["ORD-1001", "Alice", 7], ["ORD-1002", "Bob", 1], ["ORD-1003", "Charlie", 3], ["ORD-1004", "Diana", 10]],
        ),
        _case(
            "service result schema",
            'sorted(get_order("ORD-1001"))',
            sorted(["id", "customer", "items_count", "unit_price", "total_amount"]),
        ),
        _case("list route schema", "(len(json.loads(handle_list_orders()[0])),handle_list_orders()[1])", [4, 200]),
        _case(
            "copy isolation",
            'get_order("ORD-1002")["customer"]',
            "Bob",
            setup='row=get_order("ORD-1002")\nrow["customer"]="mutated"',
        ),
        _case("missing recalculation", 'calculate_order_total("missing")', None),
    ]
    return source, ref, contract, cases


def _validation(name: str) -> tuple[str, str, str, list[dict[str, Any]]]:
    source = _combine(name, ["validators.py", "app.py"])
    ref = source.replace("def validate_input(value):", "def validate_email(value):", 1)
    start = ref.index("# --- Added by Branch B")
    ref = ref[:start] + ref[start:].replace("def validate_input(value):", "def validate_phone(value):", 1)
    ref = ref.replace("email_result = validate_input(email)", "email_result = validate_email(email)").replace(
        "phone_result = validate_input(phone)", "phone_result = validate_phone(phone)"
    )
    ref += '\ndef validate_input(value):\n    email = validate_email(value)\n    return email if email["valid"] else validate_phone(value)\n'
    contract = "Resolve the duplicate validator semantic collision. Export separately named validate_email and validate_phone and route register_user fields to the matching helper. Preserve validate_name, validate_age, error ordering (name/email/phone/age), and success/error dictionary schemas. For compatibility validate_input accepts either valid email or valid phone. Preserve existing validation semantics including the original regex, phone normalization, and Python isinstance(value,int) age policy; do not silently strengthen unrelated requirements."
    cases = [
        _case(
            "registration both features",
            'register_user("Alice","alice@example.com","+1 (234) 567-8900",25)',
            {"success": True, "message": "User registered successfully"},
            requested=True,
            public=True,
        ),
        _case("name preserved", 'validate_name("A")', {"valid": False, "error": "Name too short"}, public=True),
    ]
    for i, (value, valid) in enumerate(
        [
            ("a+b@example.co", True),
            ("not-an-email", False),
            ("x@y.c", False),
            ("", False),
            (None, False),
            ("1234567890", False),
            ("x@a-b.example", True),
        ]
    ):
        cases.append(_case(f"email helper {i}", f'validate_email({value!r})["valid"]', valid, requested=True))
    for i, (value, valid) in enumerate(
        [
            ("+1 (234) 567-8900", True),
            ("123456789", False),
            ("1234567890123456", False),
            ("12345abcde", False),
            (None, False),
            ("alice@example.com", False),
        ]
    ):
        cases.append(_case(f"phone helper {i}", f'validate_phone({value!r})["valid"]', valid, requested=True))
    cases += [
        _case(
            "age boundaries",
            '[validate_age(x)["valid"] for x in [-1,0,150,151,True,25.0]]',
            [False, True, True, False, True, False],
        ),
        _case(
            "field error order",
            'register_user("A","bad","bad",151)',
            {
                "success": False,
                "errors": [
                    "Name: Name too short",
                    "Email: Invalid email format",
                    "Phone: Invalid phone number format",
                    "Age: Invalid age",
                ],
            },
        ),
        _case(
            "compatibility entry point",
            '[validate_input(x)["type"] for x in ["alice@example.com","1234567890"]]',
            ["email", "phone"],
        ),
        _case(
            "crossed fields rejected",
            'register_user("Alice","1234567890","alice@example.com",25)["success"]',
            False,
            requested=True,
        ),
    ]
    return source, ref, contract, cases


def _auth(name: str) -> tuple[str, str, str, list[dict[str, Any]]]:
    source = _combine(name, ["src/auth.py", "src/notifications.py"])
    ref = _resolve_conflicts(source)
    ref = ref.replace(
        "    user = _find_user(username)\n",
        '    if not _check_rate_limit(username):\n        return {"success":False,"error":"Too many attempts. Please wait."}\n    user = _find_user(username)\n',
        1,
    )
    ref += "\ndef _check_rate_limit(username):\n    return True\n"
    contract = "Resolve the authentication merge while retaining both the rate-limit hook and remember_me token lifetime. authenticate(username,password,remember_me=False) must invoke _check_rate_limit(username) before user lookup/password verification; denial returns the original hotfix error. The default hook remains the upstream always-True fixture and will be replaced by callers/tests. Successful responses expose success,token,remember_me; expiry is 3600 or 2592000 seconds. Preserve invalid-credential responses and notification functions. The sandbox supplies a fixed clock for reproducibility. Package versions/changelog edits are outside this adaptation."
    cases = [
        _case(
            "remember option",
            '(authenticate("admin","admin123",True)["remember_me"],authenticate("admin","admin123",True)["token"].split("_")[-1])',
            [True, "2592000"],
            requested=True,
            public=True,
        ),
        _case(
            "invalid password",
            'authenticate("admin","wrong")',
            {"success": False, "error": "Invalid credentials"},
            public=True,
        ),
    ]
    cases += [
        _case(
            "rate limit denial retained",
            'authenticate("admin","admin123",True)',
            {"success": False, "error": "Too many attempts. Please wait."},
            setup="_check_rate_limit=lambda username:False",
            requested=True,
        ),
        _case(
            "rate limit executes before lookup",
            'authenticate("admin","wrong")',
            {"success": False, "error": "Too many attempts. Please wait."},
            setup='_check_rate_limit=lambda username:False\ndef _find_user(username):\n    raise RuntimeError("lookup must not execute")',
            requested=True,
        ),
        _case(
            "limit receives actual username",
            'authenticate("admin","admin123")["success"]',
            False,
            setup='_check_rate_limit=lambda username:username!="admin"',
            requested=True,
        ),
        _case(
            "normal token",
            '(authenticate("admin","admin123")["token"],authenticate("admin","admin123")["remember_me"])',
            ["token_1_1700000000_3600", False],
        ),
        _case("second user lifetime", 'authenticate("user1","pass456",True)["token"]', "token_2_1700000000_2592000"),
        _case(
            "unknown user", 'authenticate("nobody","wrong",True)', {"success": False, "error": "Invalid credentials"}
        ),
        _case("valid result shape", 'sorted(authenticate("admin","admin123"))', ["remember_me", "success", "token"]),
        _case(
            "notifications retained",
            '(send_notification(8,"hello"),get_notifications(8))',
            [True, [{"id": 1, "message": "Welcome!", "read": False}]],
        ),
        _case(
            "password verification still meaningful",
            '[_verify_password(x,_find_user("user1")["password_hash"]) for x in ["pass456","PASS456",""]]',
            [True, False, False],
        ),
        _case(
            "denial with remember false",
            'authenticate("user1","pass456",False)["success"]',
            False,
            setup="_check_rate_limit=lambda username:False",
            requested=True,
        ),
    ]
    return source, ref, contract, cases


def _integration(name: str) -> tuple[str, str, str, list[dict[str, Any]]]:
    source = _combine(name, ["src/notifications.py", "src/search.py", "src/export.py", "src/app.py"])
    # Flatten the one nested local import, which is not part of the repair.
    source = source.replace("    from src.notifications import setup_notifications_table\n", "")
    ref = (
        _resolve_conflicts(source)
        .replace(" AND event_type = ?", " AND type = ?")
        .replace("SELECT DISTINCT event_type FROM user_events", "SELECT DISTINCT type FROM user_events")
    )
    contract = "Resolve merge conflicts and make notifications, search and export agree on the actual user_events schema: event type is stored in column 'type'. Preserve parameterized SQL, optional event/user filtering, JSON user export, CSV header/data consistency, notification return values and get_user_notifications. Integration uses a real in-memory sqlite3 database; disk DBs and file I/O are forbidden. Preserve the upstream truthy optional-filter convention (None/0/empty string do not filter), rather than altering unrelated behavior."
    setup = 'db=sqlite3.connect(":memory:")\ndb.row_factory=sqlite3.Row\nsetup_database(db)\ndb.execute("INSERT INTO users (id,name,email) VALUES (1,?,?)",("Alice","alice@example.com"))\ndb.execute("INSERT INTO users (id,name,email) VALUES (2,?,?)",("Bob","bob@example.com"))\nsend_notification(db,1,"login","User logged in")\nsend_notification(db,1,"purchase","Bought item")\nsend_notification(db,2,"login","Second logged in")\ndb.execute("UPDATE user_events SET created_at=?",("2024-01-01 00:00:00",))\ndb.commit()'
    cases = [
        _case(
            "type-filter integration",
            '[row["user_id"] for row in search_events(db,"",event_type="purchase")]',
            [1],
            setup=setup,
            requested=True,
            public=True,
        ),
        _case("notification retrieval", "len(get_user_notifications(db,1))", 2, setup=setup, public=True),
        _case(
            "actual event types",
            "sorted(row[0] for row in get_event_types(db))",
            ["login", "purchase"],
            setup=setup,
            requested=True,
        ),
        _case(
            "search text and type jointly",
            '[row["user_id"] for row in search_events(db,"Second",event_type="login")]',
            [2],
            setup=setup,
            requested=True,
        ),
        _case("no matching type", 'len(search_events(db,"",event_type="absent"))', 0, setup=setup, requested=True),
        _case(
            "injection literal remains literal",
            'len(search_events(db,"",event_type="login\' OR 1=1 --"))',
            0,
            setup=setup,
        ),
        _case(
            "export authoritative schema",
            "list(csv.reader(io.StringIO(export_events(db))))[0]",
            ["id", "user_id", "type", "description", "created_at"],
            setup=setup,
            requested=True,
        ),
        _case(
            "export optional user filter",
            "[(row[1],row[2]) for row in list(csv.reader(io.StringIO(export_events(db,1))))[1:]]",
            [["1", "login"], ["1", "purchase"]],
            setup=setup,
        ),
        _case("legacy zero means no filter", "len(list(csv.reader(io.StringIO(export_events(db,0)))))", 4, setup=setup),
        _case(
            "user json rows",
            'json.loads(export_users(db,"json"))',
            [
                {"id": 1, "name": "Alice", "email": "alice@example.com"},
                {"id": 2, "name": "Bob", "email": "bob@example.com"},
            ],
            setup=setup,
        ),
        _case(
            "csv punctuation preserved",
            "list(csv.reader(io.StringIO(export_users(db))))[1][1]",
            'A,"B"',
            setup=setup + '\ndb.execute("UPDATE users SET name=? WHERE id=1",(\'A,"B"\',))',
        ),
        _case(
            "repeated setup preserves rows",
            "len(get_user_notifications(db,1))",
            2,
            setup=setup + "\nsetup_database(db)",
        ),
        _case("text search remains working", 'len(search_events(db,"logged"))', 2, setup=setup),
        _case(
            "empty integration",
            '(len(search_events(db,"")),list(csv.reader(io.StringIO(export_events(db)))))',
            [0, [["id", "user_id", "type", "description", "created_at"]]],
            setup='db=sqlite3.connect(":memory:")\ndb.row_factory=sqlite3.Row\nsetup_database(db)',
            requested=True,
        ),
    ]
    return source, ref, contract, cases


def _pipeline(name: str) -> tuple[str, str, str, list[dict[str, Any]]]:
    source = _combine(
        name,
        [
            "input_contracts.py",
            "legacy_formatter.py",
            "stage_runtime.py",
            "stage_contracts.py",
            "pipeline.py",
            "cli_wrapper.py",
        ],
    )
    ref = source + "\nclass Pipeline:\n    def run(self,value):\n        return run_pipeline(value)\n"
    contract = "Add Pipeline().run(value) while preserving the existing module-level parse, transform, format_output, run_pipeline and run_from_cli APIs. Preserve stage-specific boundaries: parse(None) and parse('') return {}; transform(None) returns None while transform({}) returns {'_default':True}; format_output(None) returns ''. Running the full chain on None or '' therefore returns the JSON default marker. Existing marker overwrites, sorted JSON output, Unicode escaping, errors for malformed JSON/unsupported inputs and dictionary copy isolation must remain unchanged. Single-module adaptation does not require filesystem module splitting."
    cases = [
        _case(
            "new class entry point",
            'Pipeline().run({"name":"alice"})',
            '{"_transformed": true, "name": "alice"}',
            requested=True,
            public=True,
        ),
        _case("empty string still default", 'run_pipeline("")', '{"_default": true}', public=True),
    ]
    cases += [
        _case("parse none", "parse(None)", {}),
        _case("transform none", "transform(None)", None),
        _case("format none", "format_output(None)", ""),
        _case("empty mapping transform", "transform({})", {"_default": True}),
        _case("none full chain", "Pipeline().run(None)", '{"_default": true}', requested=True),
        _case("empty mapping full chain", "Pipeline().run({})", '{"_default": true}', requested=True),
        _case("json null full chain", 'Pipeline().run("null")', "", requested=True),
        _case(
            "unicode formatting preserved",
            'Pipeline().run({"name":"中文"})',
            '{"_transformed": true, "name": "\\u4e2d\\u6587"}',
            requested=True,
        ),
        _case("marker overwrite preserved", 'transform({"_transformed":False,"x":0})', {"_transformed": True, "x": 0}),
        _case(
            "copy isolation",
            "original",
            {"name": "a"},
            setup='original={"name":"a"}\ncopy_row=parse(original)\ncopy_row["name"]="mutated"',
        ),
        _case("unsupported transport", "Pipeline().run(23)", exception="TypeError", requested=True),
        _case("malformed json error", 'Pipeline().run("{bad")', exception="JSONDecodeError", requested=True),
        _case("cli still uses chain", "run_from_cli(None)", '{"_default": true}'),
        _case("false json not collapsed", 'Pipeline().run("false")', exception="TypeError", requested=True),
    ]
    return source, ref, contract, cases


ANALYZER_REFERENCE = """
import math

def validate_values(values):
    if values is None:
        raise ValueError("values cannot be None")
    cleaned = []
    for value in values:
        if not isinstance(value, (int, float)):
            raise TypeError("all values must be numeric")
        cleaned.append(float(value))
    return cleaned

def calculate_statistics(values):
    ordered = sorted(values)
    count = len(ordered)
    mean = sum(ordered) / count
    middle = count // 2
    median = ordered[middle] if count % 2 else (ordered[middle-1]+ordered[middle])/2
    stddev = math.sqrt(sum((v-mean)**2 for v in ordered)/count)
    return {"count":count,"mean":mean,"median":median,"stddev":stddev,
            "q1":ordered[count//4],"q3":ordered[count*3//4],
            "spread":ordered[-1]-ordered[0]}

def detect_outliers(values, statistics):
    iqr = statistics["q3"] - statistics["q1"]
    lower = statistics["q1"] - 1.5 * iqr
    upper = statistics["q3"] + 1.5 * iqr
    outliers = [v for v in sorted(values) if v < lower or v > upper]
    return outliers,{"lower":lower,"upper":upper,"iqr":iqr}

def build_report(values, statistics, outliers, window):
    negative = sum(v < 0 for v in values)
    zero = sum(v == 0 for v in values)
    positive = len(values)-negative-zero
    ratio = negative/len(values)
    crossing = bool(negative and positive)
    report = "stable"
    if statistics["spread"] > 100: report = "wide_spread"
    if ratio > 0.5: report = "mostly_negative"
    if outliers and ratio == 0: report = "positive_outliers"
    if crossing and statistics["spread"] < 25: report = "crosses_zero"
    return {**statistics,"outliers":outliers,"negative_ratio":ratio,
            "zero_ratio":zero/len(values),"report":report,"zero_count":zero,
            "value_buckets":{"negative":negative,"zero":zero,"positive":positive},
            "percentile_window":window,"has_zero_crossing":crossing,"error":None}

def analyze_data(values):
    cleaned = validate_values(values)
    if not cleaned:
        return {"count":0,"mean":0.0,"median":0.0,"stddev":0.0,"q1":0.0,"q3":0.0,
                "outliers":[],"spread":0.0,"negative_ratio":0.0,"zero_ratio":0.0,
                "report":"empty_input","zero_count":0,"error":"empty input",
                "value_buckets":{"negative":0,"zero":0,"positive":0},
                "percentile_window":{"lower":0.0,"upper":0.0,"iqr":0.0},"has_zero_crossing":False}
    statistics = calculate_statistics(cleaned)
    outliers, window = detect_outliers(cleaned, statistics)
    return build_report(cleaned, statistics, outliers, window)
"""


def _statistics_expected(values: list[float]) -> dict[str, Any]:
    """Independent fixture calculator using population moments and rank indices."""
    values = [float(v) for v in values]
    ordered = sorted(values)
    n = len(values)
    mean = sum(values) / n
    q1, q3 = ordered[n // 4], ordered[3 * n // 4]
    low, high = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    neg, zero = len([v for v in values if v < 0]), values.count(0)
    outliers = list(filter(lambda x: not low <= x <= high, ordered))
    span = ordered[-1] - ordered[0]
    ratio = neg / n
    crossing = min(values) < 0 < max(values)
    # Reverse-precedence decision tree, independent from sequential override code.
    report = (
        "crosses_zero"
        if crossing and span < 25
        else "positive_outliers"
        if outliers and neg == 0
        else "mostly_negative"
        if ratio > 0.5
        else "wide_spread"
        if span > 100
        else "stable"
    )
    return {
        "count": n,
        "mean": mean,
        "median": (ordered[(n - 1) // 2] + ordered[n // 2]) / 2,
        "stddev": math.sqrt(sum((v - mean) ** 2 for v in values) / n),
        "q1": q1,
        "q3": q3,
        "outliers": outliers,
        "spread": span,
        "negative_ratio": ratio,
        "zero_ratio": zero / n,
        "report": report,
        "zero_count": zero,
        "value_buckets": {"negative": neg, "zero": zero, "positive": n - neg - zero},
        "percentile_window": {"lower": low, "upper": high, "iqr": q3 - q1},
        "has_zero_crossing": crossing,
        "error": None,
    }


def _analyzer(name: str) -> tuple[str, str, str, list[dict[str, Any]]]:
    source = _combine(name, ["analyzer.py"])
    contract = "Refactor analyze_data into focused helpers without changing its nonempty-data statistics or report precedence. Export analyze_data and at least four additional callable helper functions. Population stddev, integer-rank quartiles (n//4 and 3*n//4), strict IQR outlier bounds, existing report override precedence, numeric bool acceptance and all existing report fields are preserved. Add error=None on valid nonempty results. For [] return count=0, report='empty_input', a nonempty explanatory error, empty outliers and numeric zero statistics. None still raises ValueError; nonnumeric members raise TypeError. Do not mutate inputs. Coverage-tool/file requirements of the original task are excluded; function count is only a limited structural check, not proof of maintainable refactoring."
    cases = [
        _case(
            "covered mean median",
            '(analyze_data([1,2,3,4,5])["mean"],analyze_data([1,2,3,4,5])["median"])',
            [3, 3],
            public=True,
        ),
        _case(
            "empty controlled report",
            '(analyze_data([])["count"],analyze_data([])["report"],bool(analyze_data([])["error"]))',
            [0, "empty_input", True],
            requested=True,
            public=True,
        ),
    ]
    fixtures = [
        [1],
        [7, 7, 7, 7],
        [1, 2, 3, 4],
        [-7, -3, -1],
        [-1, 0, 1],
        [0, 0, 0, 1],
        [1, 1, 1, 1, 100],
        [0, 1, 2, 3, 4, 5, 6, 1000],
        [-200, -150, 20],
        [-100, 0, 200],
        [1.5, 2.5, 2.5],
        [True, False, True],
    ]
    for i, values in enumerate(fixtures):
        cases.append(_case(f"preserved distribution {i}", f"analyze_data({values!r})", _statistics_expected(values)))
    cases += [
        _case("None error", "analyze_data(None)", exception="ValueError"),
        _case("nonnumeric member", 'analyze_data([1,"2",3])', exception="TypeError"),
        _case("input list unchanged", "original", [4, 1, 3, 2], setup="original=[4,1,3,2]\nanalyze_data(original)"),
        _case(
            "empty numeric fields",
            'all(analyze_data([])[k]==0 for k in ["mean","median","stddev","q1","q3","spread","negative_ratio","zero_count"])',
            True,
            requested=True,
        ),
    ]
    return source, textwrap.dedent(ANALYZER_REFERENCE), contract, cases


PROCESSOR_EXTENSION = """
class Processor:
    def __init__(self):
        self.plugins = []

    def register_plugin(self, name, function, order=0):
        if not callable(function):
            raise TypeError("plugin must be callable")
        if any(entry[1] == name for entry in self.plugins):
            raise ValueError("duplicate plugin name")
        self.plugins.append((order, name, function))

    def process(self, raw_data, input_format="json", mode="identity", destination="memory", output_file=None):
        base = process(raw_data, input_format=input_format, mode=mode, destination="memory")
        if base["status"] != "ok":
            return base
        rows = base["result"]
        for entry in sorted(self.plugins, key=lambda entry:entry[0]):
            trial = copy.deepcopy(rows)
            try:
                proposed = entry[2](trial)
                if not isinstance(proposed,list) or not all(isinstance(row,dict) for row in proposed):
                    raise TypeError("plugin must return list of dictionaries")
                rows = proposed
            except Exception:
                continue
        try:
            return {"status":"ok","result":output_results(rows,destination=destination,output_file=output_file)}
        except Exception as exc:
            return handle_errors(exc)
"""


def _processor(name: str) -> tuple[str, str, str, list[dict[str, Any]]]:
    source = _combine(name, ["fake_sink_adapter.py", "processor.py"])
    start = source.index('    if destination == "file":')
    end = source.index('    raise ValueError(f"unsupported destination', start)
    source = (
        source[:start]
        + '    if destination == "file":\n        raise ValueError("file destination disabled in sandbox adaptation")\n'
        + source[end:]
    )
    source = "import copy\n" + source
    ref = source + textwrap.dedent(PROCESSOR_EXTENSION)
    contract = "Add an instance-isolated Processor API with register_plugin(name,function,order=0) and process matching module process arguments. Registered plugins receive the whole normalized/coerced row list during transformation before output; run in increasing order, stable for ties. Each plugin returns a list of dicts. On exception or invalid return discard ALL of that plugin's tentative mutations, retain the prior rows and continue later plugins. Duplicate names raise ValueError. Different Processor instances must not share registration. Preserve legacy module functions, JSON/CSV/XML parsing, trimming, numeric amount coercion, uppercase/filter-positive modes, memory/JSON/API output and error dictionary shapes. This adaptation replaces filesystem plugin discovery with explicit registration and disables file output; do not add filesystem access. Audit globals from the legacy module need not be redesigned for this pilot."
    cases = [
        _case(
            "legacy parse/coercion",
            'process(\'[{"name":" alice ","amount":"5"}]\')',
            {"status": "ok", "result": [{"name": "alice", "amount": 5.0}]},
            public=True,
        ),
        _case(
            "registered plugin",
            'p.process(\'[{"name":"a","amount":"5"}]\')',
            {"status": "ok", "result": [{"name": "a", "amount": 6.0}]},
            setup='p=Processor()\ndef plus(rows):\n    return [{**r,"amount":r["amount"]+1} for r in rows]\np.register_plugin("plus",plus)',
            requested=True,
            public=True,
        ),
        _case(
            "csv uppercase",
            'process("name,amount\\nalice,3\\n",input_format="csv",mode="uppercase")',
            {"status": "ok", "result": [{"name": "ALICE", "amount": 3.0}]},
        ),
        _case(
            "xml kept",
            'process("<rows><row><name> bob </name><amount>2</amount></row></rows>",input_format="xml")',
            {"status": "ok", "result": [{"name": "bob", "amount": 2.0}]},
        ),
        _case(
            "filter and bad amount",
            'process(\'[{"amount":"0"},{"amount":"bad"},{"amount":"-1"},{"amount":"2"},{"x":"yes"}]\',mode="filter-positive")',
            {"status": "ok", "result": [{"amount": 2.0}, {"x": "yes"}]},
        ),
        _case(
            "api destination",
            'Processor().process("[]",destination="api")',
            {"status": "ok", "result": {"rows": 0, "transport": "fake"}},
            requested=True,
        ),
        _case(
            "json destination",
            'json.loads(Processor().process(\'[{"amount":"2"}]\',destination="json")["result"])',
            [{"amount": 2.0}],
            requested=True,
        ),
        _case(
            "instance registrations separate",
            'other.process(\'[{"amount":"2"}]\')["result"]',
            [{"amount": 2.0}],
            setup='p=Processor()\nother=Processor()\np.register_plugin("drop",lambda rows:[])',
            requested=True,
        ),
        _case(
            "priority and stable ties",
            'p.process(\'[{"amount":"2"}]\')["result"]',
            [{"amount": 9.0}],
            setup='p=Processor()\np.register_plugin("double",lambda rows:[{**r,"amount":r["amount"]*2} for r in rows],order=20)\np.register_plugin("plus",lambda rows:[{**r,"amount":r["amount"]+1} for r in rows],order=10)\np.register_plugin("last",lambda rows:[{**r,"amount":r["amount"]+3} for r in rows],order=20)',
            requested=True,
        ),
        _case(
            "failed plugin rollback and continuation",
            'p.process(\'[{"amount":"2","nested":{"x":1}}]\')["result"]',
            [{"amount": 3.0, "nested": {"x": 1}}],
            setup='p=Processor()\ndef bad(rows):\n    rows[0]["amount"]=999\n    rows[0]["nested"]["x"]=999\n    raise ValueError("broken")\np.register_plugin("bad",bad,0)\np.register_plugin("later",lambda rows:[{**r,"amount":r["amount"]+1} for r in rows],1)',
            requested=True,
        ),
        _case(
            "invalid plugin return rollback",
            'p.process(\'[{"amount":"2"}]\')["result"]',
            [{"amount": 2.0}],
            setup='p=Processor()\ndef bad(rows):\n    rows[0]["amount"]=999\n    return None\np.register_plugin("bad",bad)',
            requested=True,
        ),
        _case(
            "duplicate registration rejected",
            'p.register_plugin("x",lambda rows:rows)',
            setup='p=Processor()\np.register_plugin("x",lambda rows:rows)',
            exception="ValueError",
            requested=True,
        ),
        _case(
            "bad format still controlled",
            'Processor().process("{}",input_format="xml")["status"]',
            "error",
            requested=True,
        ),
        _case("unsupported destination", 'process("[]",destination="absent")["status"]', "error"),
        _case(
            "direct transform does not mutate rows",
            "rows",
            [{"name": "a", "amount": "3"}],
            setup='rows=[{"name":"a","amount":"3"}]\ntransform_data(rows,mode="uppercase")',
        ),
    ]
    return source, ref, contract, cases


BUILDERS = {
    "five-file-data-pipeline-type-cascade": _etl,
    "json-float-precision-across-services": _money,
    "cross-layer-fix-plus-integration-test-plus-docs": _orders,
    "auto-merge-success-semantic-conflict": _validation,
    "resolve-conflicts-to-unblock-release": _auth,
    "three-way-merge-plus-integration-validation": _integration,
    "refactor-breaks-none-handling-chain": _pipeline,
    "refactor-extract-test-add-coverage": _analyzer,
    "refactor-god-module-before-adding-plugin-system": _processor,
}


def build_tasks(split: str, n_per_family: int | None = None, seed: int = 20260908) -> list[Task]:
    """Build distinct original task identities, never pad by parameter variants.

    Seed is provenance only: there is no random fixture selection or split search.
    Splits are one original latent family each: only THREE independent families.
    """
    if split not in SPLIT_TASKS:
        raise ValueError("split must be train, dev or holdout")
    if n_per_family is not None and not 1 <= n_per_family <= 3:
        raise ValueError("exactly three distinct released tasks per family; no padding")
    tasks = []
    for name in SPLIT_TASKS[split][: (n_per_family or 3)]:
        source, ref, contract, cases = BUILDERS[name](name)
        public = [c for c in cases if c["public"]]
        private = [c for c in cases if not c["public"]]
        visible = [{k: c[k] for k in ("label", "setup", "expr", "expected", "exception")} for c in public]
        prompt = (
            "Repair the following executable Python module.\n"
            "This is a single-module adaptation of a public coding task, not its original container workflow.\n"
            "TASK CONTRACT\n" + contract + "\n\n"
            'EXECUTION CONTRACT\nReturn exactly one JSON object {"code":"complete Python module"}. '
            "Allowed imports: json, decimal, math, re, hashlib, time, csv, io, sqlite3 (in-memory only), "
            "xml.etree.ElementTree, copy. These imports expose only: json loads/dumps/JSONDecodeError; "
            "decimal Decimal/InvalidOperation/ROUND_HALF_EVEN/ROUND_HALF_UP/ROUND_DOWN/ROUND_UP; "
            "math sqrt/isfinite/isclose/floor/ceil/fabs/fsum; re match/fullmatch/search/sub/split/findall/compile "
            "and IGNORECASE/MULTILINE/DOTALL; hashlib sha256; time time; csv reader/writer/DictReader/DictWriter; "
            "io StringIO; sqlite3 connect/Row/Error/IntegrityError; ElementTree fromstring/tostring/Element/SubElement/ParseError; "
            "copy copy/deepcopy. Standard collection, numeric, iteration and exception builtins are available, "
            "but no type/introspection, globals/locals/vars/getattr/setattr, input or file functions. "
            "No filesystem/network/process access, introspection, dynamic eval/exec or magic attributes. "
            "No decorators, inheritance, metaclasses, or async code. Classes may define __init__. "
            "Execution is bounded to 5 CPU seconds, 12 wall seconds, monitored 384 MiB RSS and 250000 output characters. "
            "Keep all relevant existing APIs; "
            "helper refactoring is permitted. Hidden checks test the stated contract, not an unstated feature.\n\n"
            "VISIBLE CHECKS\n"
            + json.dumps(visible, ensure_ascii=False)
            + "\n\nSTARTER MODULE\n```python\n"
            + source
            + "\n```\n"
        )
        original_meta = _read(name, "task.toml")
        original_id = re.search(r'task_id = "([^"]+)"', original_meta).group(1)
        files = sorted(p for p in (ASSETS / name).rglob("*") if p.is_file())
        provenance = [
            {
                "path": str(p.relative_to(ASSETS)),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "url": f"{UPSTREAM}/blob/{UPSTREAM_COMMIT}/benchmark/tasks/{p.relative_to(ASSETS).as_posix()}",
            }
            for p in files
        ]
        metadata = {
            "version": VERSION,
            "seed": seed,
            "upstream_task_id": original_id,
            "upstream_name": name,
            "upstream_commit": UPSTREAM_COMMIT,
            "upstream_split": re.search(r'split = "([^"]+)"', original_meta).group(1),
            "domain": "coding",
            "mechanism": "constraint_preservation",
            "source_files": provenance,
            "adaptation": "Flattened public source; own behavioral oracles, no original process/file scores; not canonical benchmark.",
            "independence": "One task identity, clustered by original latent family. Different fixtures/draws are not new tasks.",
            "contract": contract,
            "starter_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "reference_sha256": hashlib.sha256(ref.encode()).hexdigest(),
        }
        tasks.append(
            Task(original_id, split, FAMILIES[split], FAMILIES[split], prompt, source, ref, public, private, metadata)
        )
    return tasks


def validate_code(code: str) -> ast.Module:
    """Defense in depth; the AST policy is NOT a replacement for the OS sandbox."""
    if not isinstance(code, str) or not code.strip() or len(code) > 60000:
        raise ValueError("code must be nonempty and at most 60000 characters")
    tree = ast.parse(code)
    nodes = list(ast.walk(tree))
    if len(nodes) > 12000:
        raise ValueError("code AST exceeds limit")
    for node in nodes:
        if isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)):
            raise ValueError("asynchronous execution is not supported")
        if isinstance(node, ast.Import):
            if any(alias.name not in ALLOWED_IMPORTS for alias in node.names):
                raise ValueError("import is not allowlisted")
        if isinstance(node, ast.ImportFrom):
            if (
                node.level
                or node.module not in ALLOWED_IMPORTS
                or any(a.name.startswith("_") or a.name == "*" for a in node.names)
            ):
                raise ValueError("from-import is not allowlisted")
        if isinstance(node, ast.Name) and (node.id.startswith("__") or node.id in FORBIDDEN_NAMES):
            raise ValueError("introspection or dynamic execution is forbidden")
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("__") or node.attr in {"load_extension", "enable_load_extension", "set_authorizer"}
        ):
            raise ValueError("magic attributes and extension loading are forbidden")
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if node.name.startswith("__") and node.name != "__init__":
                raise ValueError("only the __init__ special method is supported")
            if node.decorator_list:
                raise ValueError("decorators are not supported in this pilot")
            if isinstance(node, ast.ClassDef) and (node.bases or node.keywords):
                raise ValueError("class inheritance/metaclasses are not supported")
    return tree


def sandbox_profile() -> str:
    executable = Path(sys.executable).resolve()
    prefix = Path(sys.prefix).resolve()
    ancestors = {str(p) for p in prefix.parents} | {"/"}

    def quote(value: str) -> str:
        return json.dumps(value)

    allowed = [f"(subpath {quote(str(prefix))})"]
    allowed += [f"(subpath {quote(p)})" for p in ("/System", "/usr", "/Library", "/private/etc", "/dev")]
    allowed += [f"(literal {quote(p)})" for p in sorted(ancestors)]
    return (
        "(version 1)(deny default)(allow process-exec (literal " + quote(str(executable)) + "))"
        "(allow sysctl-read)(allow file-read* " + " ".join(allowed) + ")"
    )


def _command(program: str) -> list[str]:
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise RuntimeError("macOS sandbox-exec is required; refusing unsandboxed execution")
    return [
        "/usr/bin/sandbox-exec",
        "-p",
        sandbox_profile(),
        str(Path(sys.executable).resolve()),
        "-I",
        "-S",
        "-c",
        program,
    ]


def sandbox_probe() -> dict[str, Any]:
    """Only trusted probe code; verify interpreter and denied filesystem/network."""
    program = """import json,os,socket
result={"interpreter":True,"environment_clean":not any("KEY" in k or "TOKEN" in k for k in os.environ)}
for key,path in [("workspace_denied",PAYLOAD_WORKSPACE),("home_denied",PAYLOAD_HOME)]:
    try:
        os.listdir(path)
        result[key]=False
    except PermissionError: result[key]=True
s=socket.socket()
try:
    s.connect(("127.0.0.1",9))
    result["network_denied"]=False
except PermissionError: result["network_denied"]=True
except OSError: result["network_denied"]=False
try:
    os.open("/private/tmp/validator_pilot_sandbox_forbidden_probe",os.O_WRONLY|os.O_CREAT,0o600)
    result["write_denied"]=False
except PermissionError: result["write_denied"]=True
print(json.dumps(result))
""".replace("PAYLOAD_WORKSPACE", repr(str(Path(__file__).resolve().parents[2]))).replace(
        "PAYLOAD_HOME", repr(str(Path.home() / ".codex"))
    )
    try:
        proc = subprocess.run(
            _command(program),
            cwd="/private/tmp",
            env={"PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=8,
        )
        result = (
            json.loads(proc.stdout) if proc.returncode == 0 else {"interpreter": False, "returncode": proc.returncode}
        )
        result["ok"] = all(
            result.get(k) is True
            for k in (
                "interpreter",
                "environment_clean",
                "workspace_denied",
                "home_denied",
                "network_denied",
                "write_denied",
            )
        )
        return result
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": type(exc).__name__}


CHILD_RUNNER = r"""
import builtins,copy,csv,decimal,hashlib,io,json,math,re,resource,sqlite3,sys,types
import xml.etree.ElementTree as element_tree
resource.setrlimit(resource.RLIMIT_CPU,(5,5))
resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))
payload=json.load(sys.stdin)
def memory_connect(database=':memory:',*args,**kwargs):
    if database!=':memory:' or kwargs.get('uri'):
        raise PermissionError('only private in-memory SQLite is permitted')
    connection=sqlite3.connect(':memory:')
    connection.set_authorizer(lambda action,*rest:sqlite3.SQLITE_DENY if action in (sqlite3.SQLITE_ATTACH,sqlite3.SQLITE_DETACH) else sqlite3.SQLITE_OK)
    return connection
def proxy(module,names):
    return types.SimpleNamespace(**{name:getattr(module,name) for name in names})
et_proxy=proxy(element_tree,['fromstring','tostring','Element','SubElement','ParseError'])
proxies={
 'json':proxy(json,['loads','dumps','JSONDecodeError']),
 'decimal':proxy(decimal,['Decimal','InvalidOperation','ROUND_HALF_EVEN','ROUND_HALF_UP','ROUND_DOWN','ROUND_UP']),
 'math':proxy(math,['sqrt','isfinite','isclose','floor','ceil','fabs','fsum']),
 're':proxy(re,['match','fullmatch','search','sub','split','findall','compile','IGNORECASE','MULTILINE','DOTALL']),
 'hashlib':proxy(hashlib,['sha256']),
 'time':types.SimpleNamespace(time=lambda:1700000000.0),
 'csv':proxy(csv,['reader','writer','DictReader','DictWriter']),
 'io':types.SimpleNamespace(StringIO=io.StringIO),
 'sqlite3':types.SimpleNamespace(connect=memory_connect,Row=sqlite3.Row,Error=sqlite3.Error,IntegrityError=sqlite3.IntegrityError),
 'xml.etree.ElementTree':et_proxy,
 'copy':types.SimpleNamespace(copy=copy.copy,deepcopy=copy.deepcopy),
}
def safe_import(name,globals=None,locals=None,fromlist=(),level=0):
    if level or name not in proxies: raise ImportError('not allowlisted')
    if name=='xml.etree.ElementTree' and not fromlist:
        return types.SimpleNamespace(etree=types.SimpleNamespace(ElementTree=et_proxy))
    return proxies[name]
names=['abs','all','any','bool','bytes','callable','chr','dict','enumerate','filter','float','format','int','isinstance','issubclass','iter','len','list','map','max','min','next','ord','pow','print','range','repr','reversed','round','set','slice','sorted','str','sum','tuple','zip','Exception','ValueError','TypeError','KeyError','IndexError','RuntimeError','ZeroDivisionError','StopIteration','AssertionError','PermissionError']
safe_builtins={name:getattr(builtins,name) for name in names}
safe_builtins['__import__']=safe_import
safe_builtins['__build_class__']=builtins.__build_class__
safe_builtins['print']=lambda *args,**kwargs:None
def normalize(value,depth=0):
    if depth>30: raise ValueError('output nesting limit')
    if isinstance(value,decimal.Decimal): return str(value)
    if isinstance(value,sqlite3.Row): return {k:normalize(value[k],depth+1) for k in value.keys()}
    if isinstance(value,dict): return {str(k):normalize(v,depth+1) for k,v in value.items()}
    if isinstance(value,(tuple,list)): return [normalize(v,depth+1) for v in value]
    if value is None or isinstance(value,(str,int,float,bool)): return value
    raise TypeError('unsupported output type')
rows=[]
for case in payload['cases']:
    env={'__builtins__':safe_builtins,'__name__':'candidate'}
    try:
        exec(compile(payload['code'],'candidate.py','exec'),env,env)
        exec(compile(case.get('setup',''),'fixture.py','exec'),env,env)
        value=eval(compile(case['expr'],'fixture.py','eval'),env,env)
        rows.append({'actual':normalize(value),'exception':None})
    except Exception as exc:
        rows.append({'actual':None,'exception':type(exc).__name__,'message':str(exc)[:200]})
encoded=json.dumps({'rows':rows},ensure_ascii=False,allow_nan=False)
if len(encoded)>250000: raise ValueError('output exceeds limit')
sys.stdout.write(encoded)
"""


def _same(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual == expected
    if isinstance(expected, int) and not isinstance(expected, bool):
        return isinstance(actual, (int, float)) and not isinstance(actual, bool) and actual == expected
    if isinstance(expected, float):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12)
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_same(a, b) for a, b in zip(actual, expected))
        )
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and actual.keys() == expected.keys()
            and all(_same(actual[k], v) for k, v in expected.items())
        )
    return type(actual) is type(expected) and actual == expected


def parse_response(response: str | Mapping[str, Any]) -> str:
    if isinstance(response, str):
        response = response.strip()
        if response.startswith("```"):
            match = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
            if not match:
                raise ValueError("malformed JSON code fence")
            response = match.group(1).strip()
        value = json.loads(response)
    else:
        value = response
    if not isinstance(value, Mapping) or set(value) != {"code"} or not isinstance(value["code"], str):
        raise ValueError('response must be exactly {"code": "complete Python module"}')
    return value["code"]


def _run_payload(payload: Mapping[str, Any]) -> tuple[int, str, str]:
    """Parent RSS watchdog supplements OS CPU/file/network/process limits.

    Darwin rejects finite RLIMIT_DATA/RLIMIT_AS on this host. RSS sampling is not
    a hard allocation barrier; checks occur every 50 ms and may briefly overshoot.
    """
    import psutil

    proc = subprocess.Popen(
        _command(CHILD_RUNNER),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/private/tmp",
        env={"PATH": "/usr/bin:/bin"},
        text=True,
    )
    start = time.monotonic()
    first = json.dumps(payload)
    try:
        while True:
            try:
                out, err = proc.communicate(input=first, timeout=0.05)
                return proc.returncode, out, err
            except subprocess.TimeoutExpired:
                first = None
                if time.monotonic() - start > 12:
                    raise RuntimeError("candidate exceeded 12 second wall limit")
                try:
                    if psutil.Process(proc.pid).memory_info().rss > 384 * 1024 * 1024:
                        raise RuntimeError("candidate exceeded monitored RSS limit")
                except psutil.NoSuchProcess:
                    pass
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate()


def evaluate(task: Task, response: str | Mapping[str, Any]) -> dict[str, Any]:
    cases = task.public_cases + task.private_cases
    result = {
        "correct": False,
        "hard": False,
        "execution_ok": False,
        "artifact_execution_ok": False,
        "public_observations": [],
        "private_diagnostics": [],
        "dimensions": {
            k: {"passed": 0, "total": sum(c["dimension"] == k for c in cases)}
            for k in ("requested_behavior", "preserved_behavior")
        },
    }
    try:
        code = parse_response(response)
        tree = validate_code(code)
        # Never send expected answers/labels/split/family to candidate process.
        payload = {"code": code, "cases": [{k: c[k] for k in ("setup", "expr")} for c in cases]}
        returncode, stdout, _stderr = _run_payload(payload)
        if returncode != 0:
            result["safety_error"] = f"sandbox execution failed: exit {returncode}"
            result["error_category"] = "sandbox_or_resource_failure"
            return result
        rows = json.loads(stdout)["rows"]
        if len(rows) != len(cases):
            raise ValueError("runner result cardinality mismatch")
        result["execution_ok"] = True
        result["artifact_execution_ok"] = all(
            row["exception"] is None or case["exception"] is not None for case, row in zip(cases, rows)
        )
        for case, row in zip(cases, rows):
            passed = (
                row["exception"] == case["exception"]
                if case["exception"]
                else row["exception"] is None and _same(row["actual"], case["expected"])
            )
            result["dimensions"][case["dimension"]]["passed"] += int(passed)
            observation = {
                "label": case["label"],
                "expr": case["expr"],
                "setup": case["setup"],
                "passed": passed,
                "actual": row["actual"],
                "exception": row["exception"],
            }
            if case["public"]:
                result["public_observations"].append(observation)
            elif not passed:
                result["private_diagnostics"].append(
                    {**observation, "expected": case["expected"], "expected_exception": case["exception"]}
                )
        if task.metadata["upstream_name"] == "refactor-extract-test-add-coverage":
            count = sum(isinstance(node, ast.FunctionDef) for node in tree.body)
            dimension = result["dimensions"]["requested_behavior"]
            dimension["total"] += 1
            dimension["passed"] += int(count >= 5)
            if count < 5:
                result["private_diagnostics"].append(
                    {"label": "limited helper count structure", "passed": False, "actual": count, "expected_minimum": 5}
                )
        result["correct"] = result["hard"] = all(d["passed"] == d["total"] for d in result["dimensions"].values())
        result["passed_tests"] = sum(d["passed"] for d in result["dimensions"].values())
        result["total_tests"] = sum(d["total"] for d in result["dimensions"].values())
        result["public_pass"] = all(row["passed"] for row in result["public_observations"])
        return result
    except (ValueError, TypeError, SyntaxError) as exc:
        result["execution_ok"] = True
        result["error_category"] = "candidate_contract_violation"
        result["public_pass"] = False
        result["passed_tests"] = 0
        result["total_tests"] = sum(d["total"] for d in result["dimensions"].values())
        result["safety_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return result
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        result["error_category"] = "infrastructure_or_resource_failure"
        result["safety_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return result


def controlled_fixtures(task: Task) -> list[dict[str, Any]]:
    """Controlled stress only: not natural agent error/negative-transfer samples."""
    name, ref = task.metadata["upstream_name"], task.reference_code
    if name == "five-file-data-pipeline-type-cascade":
        mutant = ref.replace("return current_amount != historical_amount", "return False")
    elif name == "json-float-precision-across-services":
        mutant = ref.replace("if api_total != db_total:", 'if abs(api_total-db_total) > Decimal("0.10"):')
    elif name == "cross-layer-fix-plus-integration-test-plus-docs":
        mutant = ref.replace('Decimal("0.01"))', 'Decimal("0.01"),rounding="ROUND_HALF_UP")')
    elif name == "auto-merge-success-semantic-conflict":
        mutant = ref.replace(
            "def validate_phone(value):",
            'def validate_phone(value):\n    if isinstance(value,str) and "@" in value:\n        return {"valid":True,"type":"phone"}',
        )
    elif name == "resolve-conflicts-to-unblock-release":
        mutant = ref.replace(
            '    if not _check_rate_limit(username):\n        return {"success":False,"error":"Too many attempts. Please wait."}\n',
            "",
        )
    elif name == "three-way-merge-plus-integration-validation":
        mutant = ref.replace("if user_id:", "if False:")
    elif name == "refactor-breaks-none-handling-chain":
        mutant = ref.replace(
            "if should_skip_transform(value):\n        return None",
            "if should_skip_transform(value):\n        return {}",
        )
    elif name == "refactor-extract-test-add-coverage":
        mutant = ref.replace("for v in ordered)/count)", "for v in ordered)/max(1,count-1))")
    else:
        mutant = ref.replace("trial = copy.deepcopy(rows)", "trial = rows")
    if mutant == ref:
        raise ValueError("controlled mutation failed to alter reference")
    kind = (
        "preservation_mutant"
        if name
        in {
            "five-file-data-pipeline-type-cascade",
            "json-float-precision-across-services",
            "three-way-merge-plus-integration-validation",
            "refactor-extract-test-add-coverage",
        }
        else "generic_mutant"
    )
    return [
        {
            "kind": kind,
            "response": json.dumps({"code": code}),
            "controlled": True,
            "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
        }
        for kind, code in [("starter", task.starter_code), ("reference", ref), (kind, mutant)]
    ]
