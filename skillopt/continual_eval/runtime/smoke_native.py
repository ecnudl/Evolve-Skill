"""Authored, zero-model-call container smoke, with explicit evidence labels.

Run on the evaluation machine after image provisioning. Only fixture workbook
code is executed, and only through the hardened Docker backend.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--backends", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / "report.json"
    if report_path.exists():
        raise SystemExit("Use a new output directory; smoke records are immutable")
    spec = importlib.util.spec_from_file_location("standalone_continual_backend", args.backends)
    backend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend)
    import openpyxl
    def book(name, value):
        path = args.output / name
        workbook = openpyxl.Workbook()
        workbook.active["A1"] = value
        workbook.save(path)
        workbook.close()
        return str(path)
    source, gold = book("input.xlsx", 7), book("gold.xlsx", 14)
    runtime = {"image": args.image, "timeout_seconds": 30, "memory_mb": 512}
    readiness = backend.readiness("spreadsheetbench", runtime)
    report = {"evidence_kind": "engineering_fixture_real_docker", "model_calls": 0,
              "benchmark_tasks": 0, "readiness": readiness, "cases": [],
              "limitations": ["No model effectiveness evidence", "No ALFWorld game executed",
                              "BigCodeBench and KOR official scorers not provisioned by this smoke"]}
    if readiness["status"] == "ready":
        for name, expression, expected in (("positive", "14", "pass"), ("negative", "15", "fail"),
                                            ("missing_dependency", None, "unknown")):
            code = ("import fixture_missing_dependency_hopefully_never_installed" if expression is None else
                    "import openpyxl\nw=openpyxl.load_workbook('input.xlsx')\n"
                    f"w.active['A1']={expression}\nw.save('output.xlsx')\n")
            public = {"instruction": "Double the value in A1.", "input_files": [source], "answer_position": "A1"}
            prediction = backend.solve("spreadsheetbench", public, "", lambda *_: {
                "ok": True, "response": "```python\n" + code + "```", "usage": {}}, runtime=runtime)
            result = backend.score("spreadsheetbench", public,
                                   {"test_files": [gold], "answer_position": "A1"}, prediction, runtime=runtime)
            report["cases"].append({"fixture": name, "expected_status": expected, "prediction": prediction,
                                    "score": result, "matched": result["status"] == expected})
        report["bigcodebench_dependency_probe"] = backend.readiness("bigcodebench", runtime)
    report["passed"] = len(report["cases"]) == 3 and all(row["matched"] for row in report["cases"])
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"report": str(report_path), "passed": report["passed"], "model_calls": 0,
                      "cases": [{"fixture": row["fixture"], "status": row["score"]["status"]}
                                for row in report["cases"]]}, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
