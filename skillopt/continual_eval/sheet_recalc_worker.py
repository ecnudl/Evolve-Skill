"""Trusted LibreOffice UNO driver, executed only inside the isolated container.

No model Python is executed, no reference workbook accompanies a prediction.
The host forbids external relationships/macros before this worker is invoked.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import subprocess
import time
from pathlib import Path


class NumericProofError(ValueError):
    """Trusted, content-free reason codes for conservative unsupported inputs."""


def verify_numeric_literals(document, manifest, stage):
    """Read-only UNO checks: exact binary64, including signed zero; no setters."""
    sheets = document.getSheets()
    checked = 0
    for item in manifest["cells"]:
        if not sheets.hasByName(item["sheet"]):
            raise NumericProofError("numeric_literal_sheet_missing:" + stage)
        cell = sheets.getByName(item["sheet"]).getCellByPosition(item["column"], item["row"])
        if cell.getType().value != "VALUE":
            raise NumericProofError("numeric_literal_type_changed:" + stage)
        value = float(cell.getValue())
        if not math.isfinite(value) or value.hex() != item["binary64"]:
            raise NumericProofError("numeric_literal_value_changed:" + stage)
        checked += 1
    return checked


def main():
    if not Path("/.dockerenv").is_file() or os.environ.get("SKILLOPT_SHEET_RECALC_CONTAINER") != "1":
        print(json.dumps({"status": "unknown", "reason": "isolated_container_required"}))
        return
    import uno
    from com.sun.star.beans import PropertyValue
    from com.sun.star.document.MacroExecMode import NEVER_EXECUTE
    from com.sun.star.document.UpdateDocMode import NO_UPDATE

    def prop(name, value):
        item = PropertyValue()
        item.Name, item.Value = name, value
        return item

    version = subprocess.check_output(["libreoffice", "--version"], timeout=10).decode().strip()
    process = subprocess.Popen([
        "libreoffice", "-env:UserInstallation=file:///tmp/profile", "--headless", "--nologo",
        "--nodefault", "--nofirststartwizard", "--norestore",
        "--accept=pipe,name=skilloptrecalc;urp;StarOffice.ComponentContext",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    document = None
    try:
        manifest_raw = Path("/input/numeric_literals.json").read_bytes()
        if len(manifest_raw) > 8 * 1024 * 1024:
            raise NumericProofError("numeric_manifest_size_limit")
        manifest = json.loads(manifest_raw)
        if (manifest.get("schema") != "numeric-literal-export-proof-v1"
                or len(manifest.get("cells", [])) > 100_000
                or manifest.get("input_sha256") != hashlib.sha256(Path("/input/book.xlsx").read_bytes()).hexdigest()):
            raise NumericProofError("numeric_manifest_binding_mismatch")
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
        deadline = time.monotonic() + 20
        while True:
            try:
                context = resolver.resolve("uno:pipe,name=skilloptrecalc;urp;StarOffice.ComponentContext")
                break
            except Exception:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("office_startup_unavailable") from None
                time.sleep(0.1)
        desktop = context.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", context)
        document = desktop.loadComponentFromURL("file:///input/book.xlsx", "_blank", 0, (
            prop("Hidden", True), prop("ReadOnly", True), prop("MacroExecutionMode", NEVER_EXECUTE),
            prop("UpdateDocMode", NO_UPDATE),
        ))
        if document is None or not document.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
            raise RuntimeError("not_a_spreadsheet_document")
        before_count = verify_numeric_literals(document, manifest, "before_calculate")
        document.calculateAll()
        after_count = verify_numeric_literals(document, manifest, "after_calculate")
        document.storeAsURL("file:///tmp/recalculated.xlsx", (
            prop("FilterName", "Calc MS Excel 2007 XML"), prop("Overwrite", False),
        ))
        output = Path("/tmp/recalculated.xlsx")
        if not output.is_file() or output.stat().st_size > 8 * 1024 * 1024:
            raise RuntimeError("recalculated_workbook_size_limit")
        raw = output.read_bytes()
        print(json.dumps({"status": "available", "libreoffice_version": version,
                          "output_sha256": hashlib.sha256(raw).hexdigest(),
                          "output_base64": base64.b64encode(raw).decode(),
                          "numeric_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                          "numeric_verified_before": before_count, "numeric_verified_after": after_count,
                          "calculate_all": True, "macros": "never_execute", "links": "no_update"}))
    except Exception as exc:
        # No workbook content, paths, executable code or secret environment in errors.
        reason = str(exc) if isinstance(exc, NumericProofError) else "recalculation_error:" + type(exc).__name__
        print(json.dumps({"status": "unknown", "reason": reason,
                          "libreoffice_version": version}))
    finally:
        if document is not None:
            try:
                document.close(True)
            except Exception:
                pass
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


if __name__ == "__main__":
    main()
