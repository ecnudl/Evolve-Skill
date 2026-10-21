"""Batch 3: before launch (registration §0, §2.1, §6, §7, §14) -- the snapshot's engine in the runtime, the training-side
SpreadsheetBench qualification, the research archive, the pre-launch texts, the launch manifest's generator and the
owner's consent."""
from __future__ import annotations

import functools
import hashlib
import http.server
import threading
import urllib.error

import pytest

from scripts import generate_zero_shot_skill as generator
from scripts import run_coevo5
from skillopt.coevo5 import chain, data, evaluation, manifest, prelaunch, texts
from skillopt.coevo5.budget import OVERALL, Budget, step_scope
from skillopt.coevo5.examiner import GENERAL
from skillopt.coevo5.protocol import (
    DATA_SEED,
    ORDER,
    OVERALL_CEILING,
    RUNTIME,
    TITLES,
    TOLERANCE_FOCAL,
    TOLERANCE_REGRESSION,
    VERSION,
)
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from skillopt.validator_pilot.api import digest
from tests.coevo5_fakes import USAGE, Script


def _engine(tmp_path):
    path = tmp_path / "q23" / "qualification.json"
    write_json(path, seal({"version": "fixture", "status": "qualified"}))
    return path


def _pool(bench, n):
    return [{"benchmark": bench, "task_id": "%s-%03d" % (bench, i), "family_id": "f%d" % i, "part": "train",
             "public": {"q": i}, "private": {"a": i}} for i in range(n)]


def test_the_runtime_names_the_snapshot_s_engine_qualification(tmp_path):
    path = _engine(tmp_path)
    runtime = prelaunch.engine_runtime(path)
    spec = runtime["spreadsheetbench"]["recalculation"]
    assert (spec["qualification_path"], spec["qualification_sha256"]) == (str(path), data.sha(path))
    assert spec["qualification_hash"] == read_json(path)["record_hash"]
    assert spec["image"] == RUNTIME["spreadsheetbench"]["recalculation"]["image"]
    assert all(runtime[b] == RUNTIME[b] for b in ORDER if b != "spreadsheetbench")
    assert RUNTIME["spreadsheetbench"]["recalculation"]["qualification_path"] != str(path)  # the constant is untouched


def test_regression_panels_and_tolerances_follow_the_registered_rules(monkeypatch):
    monkeypatch.setattr(data, "sheet_tolerances", functools.lru_cache(maxsize=None)(data.sheet_tolerances))  # once
    pools = {"searchqa": _pool("searchqa", 600), "officeqa": _pool("officeqa", 74), "livemath": _pool("livemath", 283),
             "spreadsheetbench": _pool("spreadsheetbench", 52), "alfworld": _pool("alfworld", 57)}
    focal, regression = prelaunch.tolerances(pools)
    assert [len(regression[b]["items"]) for b in ORDER] == [60, 60, 60, 52, 0]
    assert regression["searchqa"]["items"] == [i["task_id"] for i in
                                               data.regression_items(pools["searchqa"], "searchqa", DATA_SEED)]
    assert focal["searchqa"] == TOLERANCE_FOCAL["searchqa"]
    assert regression["officeqa"]["tolerance"] == TOLERANCE_REGRESSION["officeqa"]
    assert (focal["spreadsheetbench"], regression["spreadsheetbench"]["tolerance"]) == data.sheet_tolerances(52)
    assert regression["alfworld"] == {"items": [], "tolerance": None} and focal["alfworld"] == TOLERANCE_FOCAL["alfworld"]
    focal, regression = prelaunch.tolerances({**pools, "spreadsheetbench": _pool("spreadsheetbench", 29)})
    assert focal["spreadsheetbench"] is None and regression["spreadsheetbench"] == {"items": [], "tolerance": None}


def test_the_training_side_qualification_scores_the_whole_pool(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(prelaunch.data, "pool", lambda pinned, bench: (pinned, bench))

    def qualify(tasks, root, runtime, *, side, native, workers):
        seen.update(tasks=tasks, root=root, runtime=runtime, side=side, native=native.name, workers=workers)
        return {"fixture": True}
    monkeypatch.setattr(prelaunch.qualify, "qualify", qualify)
    assert prelaunch.qualify_training_sheet({"pinned": 1}, RUNTIME, tmp_path / "q") == {"fixture": True}
    assert seen == {"tasks": ({"pinned": 1}, "spreadsheetbench"), "root": tmp_path / "q" / "sheet",
                    "runtime": RUNTIME["spreadsheetbench"], "side": "train", "native": "spreadsheet-native",
                    "workers": 3}
    with pytest.raises(FileExistsError):  # a new directory every time
        prelaunch.qualify_training_sheet({"pinned": 1}, RUNTIME, tmp_path / "q")


def _page(url):
    return ("<html><body><p>Archived page from %s about decimal rounding.</p></body></html>" % url).encode()


def test_the_archive_holds_the_fixed_pages_and_the_cards(tmp_path):
    fetched = []
    opened = prelaunch.build_archive(tmp_path / "archive", fetch=lambda url: fetched.append(url) or _page(url))
    assert sorted(fetched) == sorted(url for url, _ in prelaunch.ARCHIVE_PAGES.values()) and len(fetched) == 66
    assert all(u.startswith(("https://docs.python.org/3.11/library/", "https://openpyxl.readthedocs.io/en/3.1.3/",
                             "https://help.libreoffice.org/25.2/en-US/text/")) for u in fetched)
    assert read_json(tmp_path / "archive" / "sources.json")["libreoffice-calc-25.2-func-sumif.html"] == \
        "https://help.libreoffice.org/25.2/en-US/text/scalc/01/func_sumif.html"
    assert not (tmp_path / "archive" / prelaunch.CARRIED).exists()
    assert set(opened.texts) == set(prelaunch.ARCHIVE_PAGES) | {"card-%s.txt" % b for b in ORDER}
    assert opened.page("card-alfworld.txt") == texts.CARDS["alfworld"]
    assert opened.index_sha256 == hashlib.sha256((tmp_path / "archive" / "index.json").read_bytes()).hexdigest()
    assert read_json(tmp_path / "archive" / "sources.json")["python-3.11-re.html"] == \
        "https://docs.python.org/3.11/library/re.html"
    with pytest.raises(ValueError, match="new directory"):
        prelaunch.build_archive(tmp_path / "archive", fetch=_page)

    def down(url):
        raise OSError("unreachable")
    with pytest.raises(OSError):
        prelaunch.build_archive(tmp_path / "other", fetch=down)
    with pytest.raises(UnicodeDecodeError):
        prelaunch.build_archive(tmp_path / "binary", fetch=lambda url: b"\xff\xfe")
    assert not (tmp_path / "other").exists() and not (tmp_path / "binary").exists()  # nothing half-made


def test_a_v2_archive_carries_the_previous_pages_byte_for_byte(tmp_path, monkeypatch):
    full = dict(prelaunch.ARCHIVE_PAGES)
    v1 = {name: page for name, page in full.items() if not name.startswith("libreoffice-calc-")}
    monkeypatch.setattr(prelaunch, "ARCHIVE_PAGES", v1)
    before = prelaunch.build_archive(tmp_path / "v1", fetch=lambda url: _page(url) + b"<!-- fetched 10/17 -->")
    monkeypatch.setattr(prelaunch, "ARCHIVE_PAGES", full)
    fetched = []
    opened = prelaunch.build_archive(tmp_path / "v2", fetch=lambda url: fetched.append(url) or _page(url),
                                     previous=tmp_path / "v1")
    assert len(fetched) == 50 and all(u.startswith("https://help.libreoffice.org/25.2/") for u in fetched)
    assert all(opened.hashes[name] == before.hashes[name] for name in v1)  # the bytes of 10/17, not refetched
    carried = read_json(tmp_path / "v2" / prelaunch.CARRIED)
    assert carried == {"archive": str(before.root), "index_sha256": before.index_sha256, "pages": sorted(v1)}
    assert prelaunch.check_archive(tmp_path / "v2", carried=True)[0].index_sha256 == opened.index_sha256
    fresh = prelaunch.build_archive(tmp_path / "fresh", fetch=_page)  # every page fetched anew: no launch
    assert prelaunch.check_archive(tmp_path / "fresh")[0].index_sha256 == fresh.index_sha256
    with pytest.raises(ValueError, match="--previous"):
        prelaunch.check_archive(tmp_path / "fresh", carried=True)
    record = tmp_path / "v2" / prelaunch.CARRIED
    record.unlink()
    write_json(record, dict(carried, pages=sorted(v1)[1:]))  # a carry record that leaves out a previous page
    with pytest.raises(ValueError, match="every page"):
        prelaunch.check_archive(tmp_path / "v2")
    record.unlink()
    write_json(record, carried)
    (tmp_path / "v1" / "python-3.11-re.html").write_bytes(b"changed")  # the previous archive no longer holds it
    with pytest.raises(ValueError, match="changed"):
        prelaunch.check_archive(tmp_path / "v2")


def test_v3_an_archive_built_from_v2_s_carries_every_page_the_calc_help_included(tmp_path, monkeypatch):
    full = dict(prelaunch.ARCHIVE_PAGES)
    v1 = {name: page for name, page in full.items() if not name.startswith(prelaunch.CALC_PREFIX)}
    monkeypatch.setattr(prelaunch, "ARCHIVE_PAGES", v1)
    first = prelaunch.build_archive(tmp_path / "v1", fetch=lambda url: _page(url) + b"<!-- fetched 10/17 -->")
    monkeypatch.setattr(prelaunch, "ARCHIVE_PAGES", full)
    second = prelaunch.build_archive(tmp_path / "v2", fetch=lambda url: _page(url) + b"<!-- fetched 10/19 -->",
                                     previous=tmp_path / "v1")
    fetched = []
    third = prelaunch.build_archive(tmp_path / "v3", fetch=lambda url: fetched.append(url) or _page(url),
                                    previous=tmp_path / "v2")
    assert not fetched and third.hashes == second.hashes  # nothing refetched: v1's bytes and v2's Calc help
    assert all(third.hashes[name] == first.hashes[name] for name in v1)
    carried = read_json(tmp_path / "v3" / prelaunch.CARRIED)
    assert carried["pages"] == sorted(full) and carried["archive"] == str(second.root)
    assert prelaunch.check_archive(tmp_path / "v3", carried=True)[0].index_sha256 == third.index_sha256
    assert prelaunch.check_archive(tmp_path / "v2", carried=True)[0].index_sha256 == second.index_sha256  # v2 unchanged
    record = tmp_path / "v3" / prelaunch.CARRIED
    for pages in (sorted(v1), sorted(full)[1:]):  # a carry record that leaves out pages the previous archive holds
        record.unlink()
        write_json(record, dict(carried, pages=pages))
        with pytest.raises(ValueError, match="every page"):
            prelaunch.check_archive(tmp_path / "v3")
    # never fewer than v1's pages: an archive carried from one without them is refused
    monkeypatch.setattr(prelaunch, "ARCHIVE_PAGES", {n: p for n, p in full.items() if n not in v1})
    prelaunch.build_archive(tmp_path / "calc-only", fetch=_page)
    monkeypatch.setattr(prelaunch, "ARCHIVE_PAGES", full)
    prelaunch.build_archive(tmp_path / "partial", fetch=_page, previous=tmp_path / "calc-only")
    with pytest.raises(ValueError, match="every page"):
        prelaunch.check_archive(tmp_path / "partial")


class _Handler(http.server.BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):  # noqa: N802 -- the http.server interface
        _Handler.seen.append(self.path)
        if self.path == "/moved":
            self.send_response(302)
            self.send_header("Location", "/page")
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<html><body>page</body></html>")

    def log_message(self, *args):
        pass


def test_pages_come_only_through_the_explicit_proxy_and_never_redirected(monkeypatch):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")  # an environment proxy is never used
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    try:
        fetch = prelaunch.fetcher(None)
        assert fetch(base + "/page") == b"<html><body>page</body></html>"
        _Handler.seen.clear()
        with pytest.raises(urllib.error.HTTPError):  # the redirect itself stops: no second request is sent
            fetch(base + "/moved")
        assert _Handler.seen == ["/moved"]
    finally:
        server.shutdown()


def test_an_archive_must_hold_exactly_the_registered_documents(tmp_path):
    opened = prelaunch.build_archive(tmp_path / "archive", fetch=_page)
    found, sources = prelaunch.check_archive(tmp_path / "archive")
    assert found.index_sha256 == opened.index_sha256 and sources == data.sha(tmp_path / "archive" / "sources.json")

    def foreign(change):
        root = tmp_path / ("foreign-%d" % len(list(tmp_path.glob("foreign-*"))))
        prelaunch.build_archive(root, fetch=_page)
        change(root)
        with pytest.raises(ValueError):
            prelaunch.check_archive(root)

    def extra(root):  # an answer-bearing document added, its index entry included
        (root / "notes.txt").write_text("the answer is 42", encoding="utf-8")
        index = read_json(root / "index.json")
        index["notes.txt"] = {"sha256": data.sha(root / "notes.txt"), "title": "Notes"}
        (root / "index.json").write_text(__import__("json").dumps(index), encoding="utf-8")

    def card(root):  # a card rewritten with its index entry
        (root / "card-officeqa.txt").write_text("Another card.", encoding="utf-8")
        index = read_json(root / "index.json")
        index["card-officeqa.txt"]["sha256"] = data.sha(root / "card-officeqa.txt")
        (root / "index.json").write_text(__import__("json").dumps(index), encoding="utf-8")

    def address(root):  # a page recorded from another address
        sources = read_json(root / "sources.json")
        (root / "sources.json").unlink()
        write_json(root / "sources.json", {**sources, "python-3.11-re.html": "https://example.org/re.html"})
    for change in (extra, card, address):
        foreign(change)


def _existing(tmp_path, bench, *, card=None, pilot=False, model="glm-5.3"):
    """A completed generation: the zero-shot generator's (naming its bench), or with ``pilot`` a headroom pilot's."""
    directory = tmp_path / "existing" / bench
    system, user = texts.instruction_prompt(bench)
    named = {"version": "%s-headroom-pilot-v1:zero-shot" % bench} if pilot else {"version": generator.VERSION,
                                                                                "benchmark": bench}
    record = seal({**named, "system": system, "user": user if card is None else "Public task card:\n\n" + card,
                   "learning_model_service": {"model": model, "reasoning_effort": "low", "temperature": 0}})
    write_json(directory / "generation.json", record)
    (directory / "skill.md").write_text("- Existing %s guidance.\n" % bench, encoding="utf-8")
    write_json(directory / "result.json", seal({"generation_hash": record["record_hash"], "status": "completed",
                                                "skill_sha256": data.sha(directory / "skill.md")}))
    return directory


def _item(letter):
    return {"id": letter + "1", "text": "The answer is in the required format.", "check": None,
            "basis": "The card states the format."}


def _writer(*, invalid=(), instruction="- Read the card first.\n- Answer in the required form."):
    """The pre-launch role replies: an instruction text, or a rubric (twice invalid for the scopes ``invalid``)."""
    def reply(system, payload):
        if system == texts.INSTRUCTION_SYSTEM:
            return instruction
        scope = GENERAL if payload["rubric"].startswith("general") else {TITLES[b]: b for b in ORDER}[payload["rubric"]]
        if scope in invalid:
            return {"items": "not a list"}
        return {"items": [_item("G" if scope == GENERAL else "R")]}
    return Script(reply)


def _texts(tmp_path, name="texts", client=None, existing=None):
    existing = existing or {b: _existing(tmp_path, b) for b in prelaunch.EXISTING}
    return prelaunch.prepare_texts(tmp_path / "pre" / name, existing, client or _writer())


def test_the_pre_launch_texts_keep_the_existing_instructions_and_write_the_rest(tmp_path):
    existing = {b: _existing(tmp_path, b) for b in prelaunch.EXISTING}
    client = _writer()
    record = _texts(tmp_path, client=client, existing=existing)
    out = tmp_path / "pre" / "texts"
    assert record["missing"] == [] and record["stopped"] is None and list(record["instructions"]) == list(ORDER)
    assert record["instructions"]["officeqa"] == "- Existing officeqa guidance.\n"
    assert record["instructions"]["alfworld"] == "- Read the card first.\n- Answer in the required form.\n"
    assert set(record["rubrics"]) == {*ORDER, GENERAL} and record["rubrics"][GENERAL]["items"][0]["id"] == "G1"
    assert record["provenance"]["searchqa"]["generation_hash"] == read_json(
        existing["searchqa"] / "generation.json")["record_hash"]
    assert record["provenance"]["spreadsheetbench"] == {"source": "written", "label": "pre/instruction/spreadsheetbench"}
    calls = read_json(out / "roles.json")
    assert len(calls) == len(client.seen) == 2 + 6 and record["roles_sha256"] == data.sha(out / "roles.json")
    assert read_json(out / "texts.json", sealed=True) == record and prelaunch.verify_texts(out / "texts.json") == record
    # every call is charged to the pre-launch ledger, beside the texts
    spent = Budget(tmp_path / "pre" / "ledger").snapshot()
    assert record["ledger"] == str(tmp_path / "pre" / "ledger") and spent[OVERALL]["settled"] == 8 * 15
    assert spent[prelaunch.TEXTS_SCOPE] == {"cap": prelaunch.TEXTS_CAP, "settled": 8 * 15, "open": 0}


def test_the_first_text_that_cannot_be_written_stops_the_preparation(tmp_path):
    client = _writer(invalid=("officeqa",))
    record = _texts(tmp_path, client=client)
    assert record["stopped"] == "rubric:officeqa" and len(client.seen) == 2 + 1 + 2  # nothing after the stop
    assert record["missing"] == ["rubric:officeqa", "rubric:livemath", "rubric:spreadsheetbench", "rubric:alfworld",
                                 "rubric:general"]
    blank = _writer(instruction="   ")
    record = _texts(tmp_path, "texts-2", client=blank)
    assert record["stopped"] == "instruction:spreadsheetbench" and len(blank.seen) == 1
    assert record["missing"][:2] == ["instruction:spreadsheetbench", "instruction:alfworld"]
    with pytest.raises(ValueError, match="incomplete"):
        prelaunch.verify_texts(tmp_path / "pre" / "texts-2" / "texts.json")


def test_a_foreign_existing_instruction_is_refused_before_any_call(tmp_path):
    existing = {b: _existing(tmp_path, b) for b in prelaunch.EXISTING}
    client = _writer()
    for n, (bench, foreign) in enumerate([
            ("livemath", lambda root: _existing(root, "livemath", card="Another card.")),
            ("officeqa", lambda root: _existing(root, "officeqa", model="deepseek-v4-flash")),  # another writer
            ("searchqa", lambda root: _existing(root, "searchqa", pilot=True)),  # a version not registered for it
            ("officeqa", lambda root: _existing(root, "livemath", pilot=True))]):  # another bench's card
        with pytest.raises(ValueError, match="not written"):
            prelaunch.prepare_texts(tmp_path / "pre" / "texts", {**existing, bench: foreign(tmp_path / str(n))},
                                    client)
    assert client.seen == [] and not (tmp_path / "pre" / "texts").exists()


def test_the_headroom_pilots_zero_shot_instructions_are_existing_instructions(tmp_path):
    existing = {"searchqa": _existing(tmp_path, "searchqa"), "officeqa": _existing(tmp_path, "officeqa", pilot=True),
                "livemath": _existing(tmp_path, "livemath", pilot=True)}
    record = _texts(tmp_path, existing=existing)
    assert record["provenance"]["officeqa"]["version"] == "officeqa-headroom-pilot-v1:zero-shot"
    assert record["provenance"]["searchqa"]["version"] == generator.VERSION
    assert prelaunch.verify_texts(tmp_path / "pre" / "texts" / "texts.json") == record


def test_texts_are_checked_against_their_recorded_replies_and_the_current_prompts(tmp_path, monkeypatch):
    _texts(tmp_path)
    path = tmp_path / "pre" / "texts" / "texts.json"
    record = read_json(path, sealed=True)

    def rewritten(name, change):
        """A copy of the texts record with ``change`` applied (re-sealed, its calls kept)."""
        out = tmp_path / "pre" / name
        out.mkdir()
        calls = read_json(path.parent / "roles.json")
        value = change({k: v for k, v in record.items() if k != "record_hash"}, calls)
        write_json(out / "roles.json", calls)
        write_json(out / "texts.json", seal({**value, "roles_sha256": data.sha(out / "roles.json"),
                                             "ledger": str(tmp_path / "pre" / "ledger")}))
        return out / "texts.json"

    def edited(value, calls):  # a text that is not its recorded reply
        return {**value, "instructions": {**value["instructions"], "alfworld": "- Something else.\n"}}

    def empty(value, calls):  # filled texts without any call
        calls.clear()
        return value
    for name, change in (("edited", edited), ("empty", empty)):
        with pytest.raises(ValueError):
            prelaunch.verify_texts(rewritten(name, change))
    monkeypatch.setattr(texts, "RUBRIC_SYSTEM", texts.RUBRIC_SYSTEM + " Be brief.")  # the prompt changed since
    with pytest.raises(ValueError, match="other prompts"):
        prelaunch.verify_texts(path)


def test_v1_texts_are_imported_unchanged_beside_the_v2_smoke(tmp_path, monkeypatch, prepared):
    monkeypatch.setattr(prelaunch, "TEXTS_VERSION", "fivebench-coevolution-v1-texts")  # as v1 wrote them
    v1 = _texts(tmp_path, name="texts-v1")  # in v1's pre-launch directory, charged to its ledger
    monkeypatch.setattr(prelaunch, "TEXTS_VERSION", VERSION + "-texts")
    source = tmp_path / "pre" / "texts-v1" / "texts.json"
    with pytest.raises(ValueError, match="incomplete"):  # never taken for this version's own texts
        prelaunch.verify_texts(source)
    record = prelaunch.import_texts(tmp_path / "pre2" / "texts", source)
    assert record["version"] == VERSION + "-texts-import" and record["ledger"] == str(tmp_path / "pre2" / "ledger")
    assert all(record[k] == v1[k] for k in ("cards", "instructions", "rubrics"))
    assert {k: record["imported"][k] for k in ("path", "record_hash", "version", "ledger")} == {
        "path": str(source), "record_hash": v1["record_hash"], "version": "fivebench-coevolution-v1-texts",
        "ledger": str(tmp_path / "pre" / "ledger")}
    path = tmp_path / "pre2" / "texts" / "texts.json"
    assert prelaunch.verify_texts(path) == record and read_json(source, sealed=True) == v1  # the source untouched
    assert not (tmp_path / "pre2" / "ledger").exists()  # no call
    with pytest.raises(ValueError, match="new directory"):
        prelaunch.import_texts(tmp_path / "pre2" / "texts", source)
    # the manifest takes the imported texts, charged with the smoke beside them
    out = tmp_path / "manifest-import.json"
    built = prelaunch.generate(out, **{**prepared, "root": tmp_path / "run-import", "texts_record": path,
                                       "smoke": _smoke(tmp_path / "pre2")})
    assert built["instructions"] == v1["instructions"] and built["rubrics"] == v1["rubrics"]
    assert built["provenance"]["texts"]["imported"] == record["imported"]
    assert built["provenance"]["prior_glm_tokens"] == {"ledger": str(tmp_path / "pre2" / "ledger"), "total": 1234}
    # an import moved elsewhere, or a source whose calls changed since, is refused
    moved = tmp_path / "pre3" / "texts" / "texts.json"
    write_json(moved, read_json(path))
    with pytest.raises(ValueError, match="charged elsewhere"):
        prelaunch.verify_texts(moved)
    (source.parent / "roles.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="calls' record"):
        prelaunch.verify_texts(path)


def _panels(pools):
    """The historical train and val parts of each pool (half each), as the frozen learner reads them."""
    def load(pinned, bench, part):
        tasks = pools[bench]
        half = len(tasks) // 2
        chosen = tasks[:half] if part == data.TRAIN else tasks[half:]
        return {"version": "continual-panel-v1", "benchmark": bench, "tasks": [
            {"task_id": t["task_id"], "family_id": "%s-%s" % (part, t["task_id"])} for t in chosen]}
    return load


def _protocol(tmp_path, **changes):
    model = {"provider": "bigmodel", "name": "glm-5.3", "reasoning_effort": "low", "max_tokens": 65536}
    service = {"model": "glm-5.3", "reasoning_effort": "low", "thinking": {"type": "enabled"}, "temperature": 0,
               "max_retries": 2}
    model.update(changes.get("model", {}))
    service.update(changes.get("service", {}))
    path = tmp_path / ("f-study-%d" % len(list(tmp_path.glob("f-study-*")))) / "protocol.json"
    write_json(path, seal({"model": model, "learning_model_service": seal(service)}))
    return path


def _smoke(pre, spent=1234, status="complete"):
    """A smoke of the pre-launch directory: its record, its summary and its spending in the pre-launch ledger."""
    root = pre / "smoke"
    record = seal({"version": VERSION + "-smoke", "root": str(root), "chain": "I-ds", "code": manifest.pin_code()})
    write_json(root / prelaunch.SMOKE_RECORD, record)
    write_json(root / prelaunch.SMOKE_SUMMARY, {"run": record["record_hash"], "status": status})
    budget = Budget(pre / "ledger")
    budget.declare(chain.caps("E-ds", prelaunch.PRELAUNCH_CAP))
    scopes = (OVERALL, "chain:E-ds", step_scope("E-ds", 1, "learning"))
    budget.settle(budget.reserve(scopes, 5000, label="smoke", generation=budget.generation()), spent, detail={})
    return root


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    """Every pre-launch input of a fixture run: data, readiness, the qualification, the texts, the smoke, the archive
    and the baselines' protocol."""
    pools = {b: _pool(b, 4) for b in ORDER}
    pools["spreadsheetbench"] = _pool("spreadsheetbench", 40)
    monkeypatch.setattr(prelaunch.data, "pin", lambda config: {"fixture": True})
    monkeypatch.setattr(prelaunch.data, "pool", lambda pinned, bench: [dict(t) for t in pools[bench]])
    monkeypatch.setattr(prelaunch.data, "_load", _panels(pools))
    monkeypatch.setattr(prelaunch.backends, "readiness", lambda bench, runtime: {"status": "ready"})
    monkeypatch.setattr(prelaunch.data, "sheet_tolerances", lambda n: (n // 5, n // 7) if n >= 30 else None)  # the
    # registered rule has its own tests (it calibrates for seconds)
    engine = _engine(tmp_path)
    runtime = prelaunch.engine_runtime(engine)
    qualified = [t["task_id"] for t in pools["spreadsheetbench"][:35]]
    sheet = tmp_path / "sheet" / "qualification.json"
    write_json(sheet, seal({"version": VERSION + "-sheet-qualification", "side": "train", "tasks": 40,
                            "qualified": qualified, "excluded": {}, "counts": {}, "scorings_per_item": 2,
                            "model_calls": 0, "scorer": "qualified_lo_recalc_v7_v1",
                            "recalculation": runtime["spreadsheetbench"]["recalculation"],
                            "task_hashes": {t["task_id"]: digest(t) for t in pools["spreadsheetbench"]}}))
    _texts(tmp_path)
    full = dict(prelaunch.ARCHIVE_PAGES)  # as launched (v2 §8): v1's pages carried, the Calc help fetched
    monkeypatch.setattr(prelaunch, "ARCHIVE_PAGES",
                        {n: page for n, page in full.items() if not n.startswith(prelaunch.CALC_PREFIX)})
    prelaunch.build_archive(tmp_path / "archive-v1", fetch=_page)
    monkeypatch.setattr(prelaunch, "ARCHIVE_PAGES", full)
    prelaunch.build_archive(tmp_path / "archive", fetch=_page, previous=tmp_path / "archive-v1")
    protocol = _protocol(tmp_path)
    monkeypatch.setattr(prelaunch, "BASELINE_PROTOCOL", read_json(protocol)["record_hash"])
    return {"root": tmp_path / "run", "sheet_qualification": sheet, "engine_qualification": engine,
            "texts_record": tmp_path / "pre" / "texts" / "texts.json", "smoke": _smoke(tmp_path / "pre"),
            "archive": tmp_path / "archive", "baseline_protocol": protocol, "repo": tmp_path / "repo",
            "deepseek_env": tmp_path / "pjlab-token.env", "gepa_source": tmp_path / "gepa", "proxy": None,
            "research_proxy": None, "workers": 16}


def test_the_generated_manifest_freezes_every_input_and_builds_the_setting(tmp_path, prepared):
    out = tmp_path / "manifest.json"
    record = prelaunch.generate(out, **prepared)
    value, setting = manifest.load(out)
    assert value == record and setting.run == record["record_hash"] and setting.root == tmp_path / "run"
    assert record["cards"] == texts.CARDS  # registered as written; the roles read the run's contract (v3, v2 layout)
    assert setting.cards == texts.solver_cards(texts.CARDS, record["runtime"]) != texts.CARDS
    assert set(record) == manifest.FIELDS and record["code"] == manifest.pin_code()
    assert [t["task_id"] for t in setting.pools["spreadsheetbench"]] == ["spreadsheetbench-%03d" % i for i in range(35)]
    assert record["regression"]["spreadsheetbench"]["items"] == [
        t["task_id"] for t in data.regression_items(setting.pools["spreadsheetbench"], "spreadsheetbench", DATA_SEED)]
    assert (record["tolerance"]["spreadsheetbench"], record["regression"]["spreadsheetbench"]["tolerance"]) == (7, 5)
    assert record["runtime"]["spreadsheetbench"]["recalculation"]["qualification_path"] == \
        str(prepared["engine_qualification"])
    texts_record = read_json(prepared["texts_record"], sealed=True)
    assert record["instructions"] == texts_record["instructions"] and record["rubrics"] == texts_record["rubrics"]
    assert record["provenance"]["texts"]["record_hash"] == texts_record["record_hash"]
    assert record["provenance"]["sheet_qualification"] == {"side": "train", "items": 40, "qualified": 35,
                                                           "excluded": {}}
    assert record["baseline"]["service"] == read_json(prepared["baseline_protocol"])["learning_model_service"]
    assert record["provenance"]["baseline_settings"]["reasoning_effort"] == "low"
    smoke = read_json(prepared["smoke"] / prelaunch.SMOKE_RECORD)
    assert record["provenance"]["smoke"] == {"path": str(prepared["smoke"]), "record_hash": smoke["record_hash"],
                                             "chain": "I-ds", "status": "complete", "changed_since": []}
    # v3 §9: the deepseek solver's route and credential file (never read here); no free-router env
    assert record["clients"] == {"repo": str(tmp_path / "repo"), "proxy": None, "deepseek_route": "pjlab_token",
                                 "deepseek_env": str(tmp_path / "pjlab-token.env")}
    prior = record["provenance"]["prior_glm_tokens"]  # the texts' eight calls and the smoke, one ledger
    assert prior == {"ledger": str(tmp_path / "pre" / "ledger"), "total": 8 * USAGE["total_tokens"] + 1234}
    assert setting.extra["overall"] == OVERALL_CEILING - prior["total"]
    assert {k: record["provenance"][k] for k in ("python", "openpyxl")} == manifest.environment()
    assert record["research"]["index_sha256"] == hashlib.sha256(
        (tmp_path / "archive" / "index.json").read_bytes()).hexdigest()
    assert record["research"]["sources_sha256"] == data.sha(tmp_path / "archive" / "sources.json")
    with pytest.raises(ValueError, match="new directory"):  # neither the manifest nor the run directory is reused
        prelaunch.generate(tmp_path / "again.json", **prepared)


def test_the_generator_refuses_incomplete_or_foreign_inputs(tmp_path, prepared, monkeypatch):
    missing = _texts(tmp_path, "texts-missing", client=_writer(invalid=("alfworld",)))
    assert missing["stopped"] == "rubric:alfworld"
    refused = {
        "incomplete": {"texts_record": tmp_path / "pre" / "texts-missing" / "texts.json"},
        "another engine": {"engine_qualification": tmp_path / "other-q23" / "qualification.json"},
        "study F": {"baseline_protocol": _protocol(tmp_path)},
        "smoke": {"smoke": tmp_path / "elsewhere" / "smoke"}}
    write_json(tmp_path / "other-q23" / "qualification.json", seal({"version": "fixture", "status": "qualified",
                                                                   "other": True}))
    _smoke(tmp_path / "elsewhere")  # completed, but charged to another pre-launch ledger
    write_json(tmp_path / "f-study-x" / "protocol.json", seal({}))
    for n, (reason, change) in enumerate(refused.items()):
        if reason == "study F":  # a protocol other than study F's, even with the solver's settings
            monkeypatch.setattr(prelaunch, "BASELINE_PROTOCOL", "0" * 64)
        with pytest.raises(ValueError):
            prelaunch.generate(tmp_path / ("%d.json" % n), **{**prepared, **change})
        monkeypatch.setattr(prelaunch, "BASELINE_PROTOCOL", read_json(prepared["baseline_protocol"])["record_hash"])
    monkeypatch.setattr(prelaunch.backends, "readiness", lambda bench, runtime: {"status": "unsupported",
                                                                                 "reason": "fixture"})
    with pytest.raises(ValueError, match="not ready"):
        prelaunch.generate(tmp_path / "c.json", **prepared)
    assert not any((tmp_path / name).exists() for name in ("0.json", "1.json", "2.json", "3.json", "c.json", "run"))


@pytest.mark.parametrize("model, service", [({"reasoning_effort": "high"}, {"reasoning_effort": "high"}),
                                            ({}, {"temperature": 1}), ({"max_tokens": 32768}, {}),
                                            ({}, {"thinking": None})])
def test_the_baselines_learning_model_must_match_the_solver(tmp_path, prepared, monkeypatch, model, service):
    protocol = _protocol(tmp_path, model=model, service=service)
    monkeypatch.setattr(prelaunch, "BASELINE_PROTOCOL", read_json(protocol)["record_hash"])  # study F's, by fiat
    with pytest.raises(ValueError, match="differs from the solver"):
        prelaunch.generate(tmp_path / "m.json", **{**prepared, "baseline_protocol": protocol})


def test_a_stage_the_baselines_cannot_learn_or_an_unusable_start_refuses_the_launch(tmp_path, prepared, monkeypatch):
    pools = {b: _pool(b, 4) for b in ORDER}
    pools["spreadsheetbench"] = _pool("spreadsheetbench", 40)
    halves = _panels(pools)

    def no_val(pinned, bench, part):  # the qualified SpreadsheetBench items are all historical train
        found = halves(pinned, bench, part)
        if bench == "spreadsheetbench" and part == data.VAL:
            found["tasks"] = [t for t in found["tasks"] if int(t["task_id"].rsplit("-", 1)[1]) >= 35]
        return found
    monkeypatch.setattr(prelaunch.data, "_load", no_val)
    with pytest.raises(ValueError, match="historical train and val"):
        prelaunch.generate(tmp_path / "a.json", **prepared)
    monkeypatch.setattr(prelaunch.data, "_load", halves)
    _texts(tmp_path, "texts-long", client=_writer(instruction="- " + "x" * 21000))
    with pytest.raises(ValueError, match="Skill exceeds"):  # §3: the I chains' start must fit
        prelaunch.generate(tmp_path / "b.json", **{**prepared, "texts_record": tmp_path / "pre" / "texts-long" /
                                                   "texts.json"})


def test_the_pre_launch_ledger_must_be_settled_and_not_halted(tmp_path, prepared):
    budget = Budget(tmp_path / "pre" / "ledger")
    rid = budget.reserve((OVERALL,), 100, label="a running smoke", generation=budget.generation())
    with pytest.raises(ValueError, match="still holds"):  # this process is alive: its reservation is open
        prelaunch.generate(tmp_path / "a.json", **prepared)
    budget.settle(rid, 120, detail={}, breach="reported_usage_beyond_attempt_bound")  # a breach halts the ledger
    with pytest.raises(ValueError, match="halted"):
        prelaunch.generate(tmp_path / "b.json", **prepared)
    budget.resume(decision="the owner reviewed the breach")
    record = prelaunch.generate(tmp_path / "c.json", **prepared)
    assert record["provenance"]["prior_glm_tokens"]["total"] == 8 * 15 + 1234 + 120


def test_the_owner_s_consent_is_written_once_in_the_owner_s_words(tmp_path):
    root = tmp_path / "run"
    value = seal({"version": VERSION + "-manifest", "root": str(root)})
    write_json(tmp_path / "manifest.json", value)
    note = "10/17 19:2x 负责人：同意（读测试集做评测，含 SpreadsheetBench 测试侧资格检查）"
    assert run_coevo5.main(["consent", "--manifest", str(tmp_path / "manifest.json"), "--date", "2026-10-17",
                            "--note", note]) == 0
    assert evaluation.consent(root / "shared") == {"test_evaluation": True, "sheet_test_qualification": True,
                                                   "by": "owner", "date": "2026-10-17", "note": note}
    with pytest.raises(ValueError):  # written once
        prelaunch.record_consent(root / "shared", date="2026-10-18", note="other words")


def test_the_texts_command_exits_3_when_a_text_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(prelaunch, "role_client", lambda repo, proxy: _writer(invalid=("officeqa",)))
    arguments = ["prepare-texts", "--out", str(tmp_path / "pre" / "texts"), "--repo", str(tmp_path / "repo")]
    for bench in prelaunch.EXISTING:
        arguments += ["--existing", "%s=%s" % (bench, _existing(tmp_path, bench))]
    assert run_coevo5.main(arguments) == 3
    assert read_json(tmp_path / "pre" / "texts" / "texts.json", sealed=True)["stopped"] == "rubric:officeqa"


def test_v3_the_clients_send_the_deepseek_solver_through_its_registered_route(tmp_path, monkeypatch):
    from scripts import weak_solver_probe as probe

    made = []

    class Client:
        def __init__(self, repo, model, **options):
            made.append((model, options))
    monkeypatch.setattr(probe, "Client", Client)
    config = manifest.client_config(tmp_path / "repo", None, deepseek_env=tmp_path / "pjlab-token.env")
    make = manifest._clients(config)
    make("deepseek-v4-flash", 32768, 900)
    make("glm-5.3", 16384, 900)
    make("deepseek-v4-flash", 32768, 900)  # one client per setting
    assert [model for model, _ in made] == ["deepseek-v4-flash", "glm-5.3"]
    assert (made[0][1]["route"], made[0][1]["route_env"]) == ("pjlab_token", str(tmp_path / "pjlab-token.env"))
    assert "route" not in made[1][1] and made[1][1]["router_env"] is None  # GLM-5.3: the credential repository
    for broken in ({**config, "deepseek_route": "free_router"},
                   {k: v for k, v in config.items() if k != "deepseek_env"}):
        with pytest.raises(ValueError, match="route"):
            manifest._clients(broken)
    legacy = manifest._clients({"repo": str(tmp_path), "proxy": None, "router_env": str(tmp_path / "router.env")})
    legacy("deepseek-v4-flash", 32768, 900)  # v1-v2's manifests: the free router, as before
    assert "route" not in made[-1][1] and made[-1][1]["router_env"] == str(tmp_path / "router.env")
