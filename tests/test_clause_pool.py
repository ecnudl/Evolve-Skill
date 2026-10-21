"""Clause pool (architecture X): edit decomposition, the pre-registered gate, and the CLI end to end on probe
directories written in weak_solver_probe's format (real item sources, Skill hashes, solver configuration)."""
import json
import time

import pytest

from scripts import build_training_profile as builder
from scripts import clause_pool as tool
from scripts import weak_solver_probe as probe
from skillopt.clause_pool import edits as ed
from skillopt.clause_pool import gate as gt

PARENT = ("# Guidance\n\n"
          "- Read the question first.\n"
          "- If a computation is required (difference, sum), show the work and round only at the end.\n"
          "- Watch units: millions of dollars versus billions.\n"
          "- Emit one <answer> tag.\n")
CANDIDATE = ("# Guidance\n\n"
             "- Read the question first.\n"
             "- If a computation is required (difference, sum, mean, standard deviation, correlation), list the series "
             "first, show the work and round only at the end; recheck by a second route.\n"
             "- When the same table appears in multiple supplied Bulletin issues, prefer the most recent issue.\n"
             "- Watch units: millions of dollars versus billions.\n"
             "- Emit one <answer> tag.\n\n"
             "## Statistical conventions\n"
             "- A standard deviation of a complete set of periods is the population standard deviation.\n"
             "- State the convention you used.\n\n"
             "- Keep the answer short.\n")


@pytest.mark.parametrize("text", [PARENT, CANDIDATE, "\n\n# T\n- a\n  continued\n\npara one\npara two\n<!-- c -->\n- b",
                                  "no newline at end", "- a\n\n\n- b\n\n", "a\rb\r", "- a\r\n- b\r\n", ""])
def test_blocks_round_trip_byte_for_byte(text):
    blocks, tail = ed.blocks(text)
    assert "".join(s + b for s, b in blocks) + tail == text
    assert ed.apply(text, []) == text


@pytest.mark.parametrize("parent,candidate", [
    (PARENT, CANDIDATE),
    ("# Rules\n- Keep units\n", "# Rules\n\n- Keep units carefully\n"),   # a blank line and a rewrite
    ("# Rules\n- Keep units\n", "# Rules\n- Keep units\n\n\n"),           # the tail only
    ("# Rules\n- Keep units\n", "- New first rule\n\n# Rules\n- Keep units\n"),  # insert at 0, then a blank line
    ("# Rules\n- Keep units\n", "# Rules\n- Keep units\n- Appended"),     # append without a final newline
    ("# Rules\n- Keep units\n", ""),                                      # delete everything
    ("a\rb\r", "a\rc\r"), ("\n\n# T\n- a\n", "# T\n- a\n- b\n"),
    ("# A\n\n# B\n", "\n\n# B\n"),                                       # first block deleted, blank lines kept
    ("# A\n\n# B\n", "# B\n"), ("x\n", "# New\r\r- unrelated\r"),
])
def test_decompose_reproduces_every_candidate_exactly(parent, candidate):
    assert ed.apply(parent, ed.decompose(parent, candidate, "c")) == candidate


def test_decompose_pairs_rewrites_groups_sections_and_tags_by_the_registered_rule():
    edits = ed.decompose(PARENT, CANDIDATE, "cand")
    assert [(e["op"], e["at"], e["blocks"]) for e in edits] == [("replace", 2, 1), ("insert", 3, 1), ("insert", 5, 3),
                                                                 ("insert", 5, 1)]
    replace, vintage, conventions, generic = edits
    assert replace["tags"] == ["op:correlation", "op:mean", "op:stdev"]  # what the rewrite adds
    assert "ctx:multi_vintage" in vintage["tags"] and conventions["tags"] == ["op:stdev"] and generic["tags"] == []
    one = ed.apply(PARENT, [conventions])
    assert one.startswith(PARENT.rstrip("\n")) and "## Statistical conventions" in one and "most recent" not in one
    assert ed.apply(PARENT, [replace]).count("If a computation is required") == 1
    deleted = ed.decompose(PARENT, PARENT.replace("- Watch units: millions of dollars versus billions.\n", ""), "d")
    assert [(e["op"], e["tags"]) for e in deleted] == [("delete", [])]  # a delete is generic (design section 6)
    blank = ed.decompose(PARENT, PARENT.replace("\n- Emit", "\n\n- Emit"), "w")
    assert blank and all(ed.no_effect(PARENT, [e]) for e in blank)  # whitespace only: not measured


def test_apply_rejects_conflicts_and_edits_that_do_not_fit():
    a = ed.decompose(PARENT, PARENT.replace("Watch units", "Watch units carefully"), "a")
    b = ed.decompose(PARENT, PARENT.replace("Watch units", "Always watch units"), "b")
    assert a[0]["op"] == b[0]["op"] == "replace" and a[0]["at"] == b[0]["at"]
    with pytest.raises(ed.Conflict):
        ed.apply(PARENT, a + b)
    for bad in ({**a[0], "op": "rewrite"}, {**a[0], "old": "something else"}, {**a[0], "at": 99},
                {**a[0], "new": None}):
        with pytest.raises(ValueError):
            ed.apply(PARENT, [bad])
    first = ed.decompose(PARENT, "- Zeroth rule.\n" + PARENT, "z")
    # the old first block's separator changes from "" to "\n": a whitespace-only replacement, never measured
    assert [(e["op"], e["at"]) for e in first] == [("insert", 0), ("replace", 0)]
    assert not ed.no_effect(PARENT, [first[0]]) and ed.no_effect(PARENT, [first[1]])
    assert ed.apply(PARENT, [first[0]]) == ed.apply(PARENT, first) == "- Zeroth rule.\n" + PARENT
    with pytest.raises(ValueError):
        ed.decompose(PARENT, CANDIDATE, "bad name!")
    # a block whose text only moved is anchored before any similarity pairing: a new heading before an old one is an
    # insert, not a rewrite of the old heading followed by its re-insertion
    moved = ed.decompose("# A\n- keep\n", "# New\n\n# A\n- keep\n", "m")
    assert [(e["op"], e["at"]) for e in moved] == [("insert", 0), ("replace", 0)] and ed.no_effect("# A\n- keep\n", [moved[1]])
    assert ed.apply("# A\n- keep\n", [moved[0]]) == "# New\n# A\n- keep\n"
    dropped = ed.decompose("# A\n\n# B\n", "\n\n# B\n", "f")
    assert [(e["op"], ed.no_effect("# A\n\n# B\n", [e])) for e in dropped] == [("delete", False), ("replace", True)]


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_a_blank_line_separates_an_inserted_heading_from_its_blocks_with_any_line_ending(ending):
    def inserted(candidate):
        return [e["blocks"] for e in ed.decompose("- x" + ending, candidate.replace("\n", ending), "h")
                if e["op"] == "insert"]
    assert inserted("# New\n- one\n- x\n") == [2]
    assert inserted("# New\n\n- unrelated\n- x\n") == [1, 1]


ITEMS = ["I%02d" % i for i in range(20)]
TAGS = {i: (["op:stdev", "round:2"] if n < 6 else ["op:lookup", "round:none"]) for n, i in enumerate(ITEMS)}


def test_gate_noise_measure_screen_confirm_and_coverage():
    half_a = {i: ["pass", "pass"] if n % 2 else ["fail", "pass"] for n, i in enumerate(ITEMS)}
    half_b = {i: ["pass", "fail"] if n % 2 else ["fail", "pass"] for n, i in enumerate(ITEMS)}
    v = gt.noise(half_a, half_b, ITEMS)
    assert v["n_items"] == 20 and v["v"] == "1/8" and v["v_shown"] == 0.125
    shifted = gt.noise({i: ["pass"] for i in ITEMS}, {i: ["pass", "fail"] for i in ITEMS}, ITEMS)
    assert shifted["v"] == "1/4"  # the second moment: a uniform drift counts as noise
    parent = {i: ["fail", "fail"] if i in ("I00", "I01", "I02") else ["pass", "pass"] for i in ITEMS}
    edit = dict(parent, I00=["pass", "pass"], I01=["pass", "pass"], I02=["pass", "fail"])
    m = gt.measure(["op:stdev"], TAGS, edit, parent)
    assert (m["n_trigger"], m["n_rest"], m["delta_trigger"], m["delta_rest"], m["coverage"]) == (6, 14, 2.5, 0.0, 1.0)
    assert gt.screen(m, v["v"]) == {"threshold": 1.0, "passed": True, "pending": None}
    harmful = dict(edit, I10=["fail", "fail"], I11=["fail", "fail"])
    assert not gt.screen(gt.measure(["op:stdev"], TAGS, harmful, parent), v["v"])["passed"]
    generic = gt.measure([], TAGS, edit, parent)
    assert gt.screen(generic, v["v"])["threshold"] == pytest.approx(1.58114, abs=1e-4)
    assert gt.confirm(m)["passed"] and not gt.confirm(gt.measure(["op:stdev"], TAGS, parent, parent))["passed"]
    # unknown items never shrink the registered sizes, and below 90% coverage nothing passes
    sparse = {i: (["pass", "pass"] if i in ("I00", "I01") else ["unknown", "unknown"]) for i in ITEMS}
    gm = gt.measure([], TAGS, sparse, parent)
    assert gm["n_items"] == 20 and gm["coverage"] == 0.1
    assert gt.screen(gm, "1/5") == {"threshold": None, "passed": False, "pending": "insufficient_coverage"}
    assert gt.confirm(gm)["pending"] == "insufficient_coverage"


def test_the_gate_decides_exactly_at_the_registered_boundary():
    # Codex round 3: v = 1/6 and Δ_trig = 2 = σ(24) exactly; a rounded v (0.166667) would refuse this edit
    items = ["G%02d" % i for i in range(48)]
    tags = {i: (["op:stdev"] if n < 24 else ["op:lookup"]) for n, i in enumerate(items)}
    half_a = {i: (["fail", "pass"] if n < 32 else ["fail", "fail"]) for n, i in enumerate(items)}
    half_b = {i: ["fail", "fail"] for i in items}
    v = gt.noise(half_a, half_b, items)
    assert v["v"] == "1/6"
    parent = {i: half_a[i] + half_b[i] for i in items}
    edit = {i: (["pass", "pass"] if n < 8 or n in (24, 25) else ["fail", "fail"]) for n, i in enumerate(items)}
    m = gt.measure(["op:stdev"], tags, edit, parent)
    assert m["exact"] == {"delta_trigger": "2", "delta_rest": "0", "delta_total": "2"} and m["n_trigger"] == 24
    assert gt.screen(m, v["v"]) == {"threshold": 2.0, "passed": True, "pending": None}
    lower = dict(edit, G07=["pass", "fail"])  # Δ_trig = 3/2 < σ(24) = 2
    assert not gt.screen(gt.measure(["op:stdev"], tags, lower, parent), v["v"])["passed"]
    # coverage is decided on counts: 43 of 48 known (89.6%) is pending, 44 (91.7%) is decided
    unknown = lambda k: {**edit, **{items[n]: ["unknown", "unknown"] for n in range(47, 47 - k, -1)}}
    assert gt.screen(gt.measure(["op:stdev"], tags, unknown(5), parent), v["v"])["pending"] == "insufficient_coverage"
    assert gt.screen(gt.measure(["op:stdev"], tags, unknown(4), parent), v["v"])["pending"] is None


# ----------------------------------------------------------------------------- probe directories
def _panel(path):
    tasks = [{"task_id": i, "family_id": "f" + i, "partition": "development",
              "public": {"question": "What is value %s? Round to 2 decimal places." % i, "context": "| v | %s |" % i},
              "private": {"answer": "1.%s" % i[1:]}} for i in ITEMS]
    path.write_text(json.dumps({"tasks": tasks}))
    return path


SOLVER = {"version": probe.VERSION, "backend": "free_router", "model": "deepseek-v4-flash", "benchmark": "officeqa",
          "max_tokens": 32768, "thinking": None, "reasoning_effort": None, "temperature": 0, "proxy": probe.GATEWAY,
          "response_model_ids": ["deepseek-flash", "deepseek-v4-flash"], "session_id_header": "X-Session-Id",
          "prompt": "continual_eval.backends.solve (the learning stages' solver prompt)"}


def _probe(path, panel, texts, outcomes, *, started=None, runs=2, solver=None):
    """A completed probe directory as weak_solver_probe writes it; outcomes[skill][item] = list of statuses."""
    rows = probe.load_items("%s:development" % panel)
    config = {**(solver or SOLVER), "runs": runs, "items": ["%s:development" % panel],
              "item_ids_hash": probe.digest(sorted(r["id"] for r in rows)),
              "items_hash": probe.digest(sorted(probe.digest(r) for r in rows)), "n_items": len(rows),
              "skills": {s: {"hash": probe.digest(t), "bytes": len(t.encode())} for s, t in texts.items()},
              "seed": 1, "started": started or time.strftime(tool.STAMP)}
    path.mkdir(parents=True)
    (path / "config.json").write_text(json.dumps(config))
    for skill, by_item in outcomes.items():
        for item, statuses in by_item.items():
            for run, status in enumerate(statuses):
                d = path / "records" / skill
                d.mkdir(parents=True, exist_ok=True)
                (d / ("%s.%d.json" % (item, run))).write_text(json.dumps({"skill": skill, "item": item, "run": run,
                                                                           "status": status}))
    (path / "summary.json").write_text(json.dumps({"status": "completed", "config_hash": probe.digest(config)}))
    return path


PAST, PAST_B = "2026-10-15T00:00:00+0800", "2026-10-15T05:00:00+0800"
LATER, LATEST = "2099-01-01T00:00:00+0800", "2099-01-02T00:00:00+0800"


def _setup(tmp_path):
    panel = _panel(tmp_path / "panel.json")
    builder.build(panel, tmp_path / "profile.json", partition="development")
    profile = json.loads((tmp_path / "profile.json").read_text())
    for item, tags in TAGS.items():  # the fixture's own trigger structure
        profile["items"][item]["tags"] = tags
    (tmp_path / "profile.json").unlink()
    (tmp_path / "profile.json").write_text(json.dumps(profile))
    (tmp_path / "parent.md").write_text(PARENT)
    (tmp_path / "cand.md").write_text(CANDIDATE)
    base = {i: ["fail", "fail"] if i in ("I00", "I01", "I02") else ["pass", "pass"] for i in ITEMS}
    half_a = _probe(tmp_path / "a", panel, {"bzero": PARENT}, {"bzero": base}, started=PAST)
    half_b = _probe(tmp_path / "b", panel, {"bzero": PARENT}, {"bzero": base}, started=PAST_B)
    return panel, base, half_a, half_b


def test_cli_end_to_end(tmp_path, monkeypatch):
    panel, base, half_a, half_b = _setup(tmp_path)
    value = tool.decompose(tmp_path / "parent.md", ["cand=%s" % (tmp_path / "cand.md")], tmp_path / "pool")
    ids = [e["id"] for e in value["edits"]]
    assert ids == ["cand-e00", "cand-e01", "cand-e02", "cand-e03"] and value["wholes"][0]["id"] == "cand-whole"
    with pytest.raises(SystemExit):
        tool.decompose(tmp_path / "parent.md", ["cand=%s" % (tmp_path / "cand.md")], tmp_path / "pool")
    halves = ["%s:bzero" % half_a, "%s:bzero" % half_b]
    reg = tool.noise(tmp_path / "parent.md", halves, tmp_path / "profile.json", tmp_path / "noise.json")
    assert reg["v"] == "0" and reg["n_items"] == 20 and len(reg["items"]) == 20
    texts = {e["id"]: (tmp_path / "pool" / "skills" / e["skill_file"]).read_text()
             for e in [*value["edits"], *value["wholes"]]}
    helps = dict(base, I00=["pass", "pass"], I01=["pass", "pass"])  # cand-e02 (stdev): +2 on its subset
    hurts = dict(base, I10=["fail", "fail"], I11=["fail", "fail"])
    outcomes = {"bzero": base, "cand-e00": base, "cand-e01": hurts, "cand-e02": helps, "cand-e03": base,
                "cand-whole": helps}
    screen_dir = _probe(tmp_path / "s", panel, {"bzero": PARENT, **{k: texts[k] for k in outcomes if k != "bzero"}},
                        outcomes, started=LATER)
    parents = halves + ["%s:bzero" % screen_dir]
    screened = tool.screen(tmp_path / "pool" / "edits.json", tmp_path / "noise.json", parents, screen_dir,
                           tmp_path / "screen.json")
    assert screened["passed"] == ["cand-e02", "cand-whole"]
    with pytest.raises(SystemExit):  # the screen probe cannot confirm itself
        tool.confirm(tmp_path / "screen.json", parents, screen_dir, tmp_path / "c0.json")
    confirm_dir = _probe(tmp_path / "c", panel, {"bzero": PARENT, "cand-e02": texts["cand-e02"],
                                                 "cand-whole": texts["cand-whole"]},
                         {"bzero": base, "cand-e02": dict(base, I00=["pass", "fail"]), "cand-whole": base},
                         started=LATEST)
    decided = decided_first = tool.confirm(tmp_path / "screen.json", parents, confirm_dir, tmp_path / "confirm.json")
    assert decided["accepted"] == ["cand-e02"]
    real = tool._write_once

    def receipt_fails(path, value):
        if str(path).endswith(".md.json"):
            raise OSError("disk full")
        real(path, value)
    monkeypatch.setattr(tool, "_write_once", receipt_fails)
    with pytest.raises(OSError):  # a failed receipt leaves no orphan text, and the composition can be retried
        tool.compose(tmp_path / "pool" / "edits.json", tmp_path / "confirm.json", tmp_path / "final.md")
    assert not (tmp_path / "final.md").exists() and not (tmp_path / "final.md.json").exists()
    monkeypatch.setattr(tool, "_write_once", real)
    pool = tool.compose(tmp_path / "pool" / "edits.json", tmp_path / "confirm.json", tmp_path / "final.md")
    assert pool["included"] == ["cand-e02"]
    assert (tmp_path / "final.md").read_text() == ed.apply(PARENT, [value["edits"][2]])
    whole = tool.compose(tmp_path / "pool" / "edits.json", tmp_path / "confirm.json", tmp_path / "whole.md", whole=True)
    assert whole["chosen"] is None and (tmp_path / "whole.md").read_text() == PARENT
    with pytest.raises(SystemExit):  # receipt and text are published together, once
        tool.compose(tmp_path / "pool" / "edits.json", tmp_path / "confirm.json", tmp_path / "final.md")
    assert not list(tmp_path.rglob("*.tmp"))  # every write went through a temporary file linked into place
    # several gated edit sets of one parent compose together (old + new candidates): a repeated text is skipped
    (tmp_path / "cand2.md").write_text(CANDIDATE)
    second = tool.decompose(tmp_path / "parent.md", ["cand2=%s" % (tmp_path / "cand2.md")], tmp_path / "pool2")
    decided = _decisions(second, {"cand2-e01": ("2", 3), "cand2-e02": ("1", 6)}, tmp_path / "decisions2.json")
    both = tool.compose(tmp_path / "pool" / "edits.json", tmp_path / "confirm.json", tmp_path / "all.md",
                        more=[(tmp_path / "pool2" / "edits.json", decided)])
    # strength order: cand2-e01 (2 over 3), cand2-e02 (1 over 6), cand-e02 (1/2 over 6, the same text: a repeat)
    assert both["included"] == ["cand2-e01", "cand2-e02"] and both["skipped_repeats"] == ["cand-e02"]
    assert (tmp_path / "all.md").read_text() == ed.apply(PARENT, [second["edits"][1], second["edits"][2]])
    with pytest.raises(SystemExit):  # one gate's decisions twice: the same edit ids
        tool.compose(tmp_path / "pool" / "edits.json", tmp_path / "confirm.json", tmp_path / "twice.md",
                     more=[(tmp_path / "pool" / "edits.json", tmp_path / "confirm.json")])
    # Codex: a candidate name reused by another gate is refused in both modes -- here cand-e01 was rejected by the
    # first gate and the second gate accepts a different text under the same id
    assert "cand-e01" not in decided_first["accepted"]
    (tmp_path / "cand-other.md").write_text(CANDIDATE.replace("prefer the most recent issue", "prefer the earliest issue"))
    same = tool.decompose(tmp_path / "parent.md", ["cand=%s" % (tmp_path / "cand-other.md")], tmp_path / "pool-same")
    assert same["edits"][1]["id"] == "cand-e01" and same["edits"][1]["new"] != value["edits"][1]["new"]
    accepted_same = _decisions(same, {"cand-e01": ("2", 6)}, tmp_path / "decisions-same.json")
    for whole in (False, True):
        with pytest.raises(SystemExit):
            tool.compose(tmp_path / "pool" / "edits.json", tmp_path / "confirm.json", tmp_path / ("same%d.md" % whole),
                         whole=whole, more=[(tmp_path / "pool-same" / "edits.json", accepted_same)])
    (tmp_path / "parent3.md").write_text(PARENT + "- Another parent.\n")
    third = tool.decompose(tmp_path / "parent3.md", ["cand3=%s" % (tmp_path / "cand.md")], tmp_path / "pool3")
    with pytest.raises(SystemExit):  # another parent
        tool.compose(tmp_path / "pool" / "edits.json", tmp_path / "confirm.json", tmp_path / "mixed.md",
                     more=[(tmp_path / "pool3" / "edits.json", _decisions(third, {}, tmp_path / "decisions3.json"))])


def _decisions(edits_value, accepted, path):
    """A sealed decisions record accepting ``accepted`` = {edit id: (confirmation Δ_trig, |S|)} (compose's inputs)."""
    from skillopt.coevolution_v5.core import seal

    decisions = [{"id": e["id"], "source": e["source"], "kind": "edit", "accepted": e["id"] in accepted,
                  "n_trigger": accepted.get(e["id"], ("0", 1))[1],
                  "confirm": {"exact": {"delta_trigger": accepted.get(e["id"], ("0", 1))[0], "delta_rest": "0",
                                        "delta_total": accepted.get(e["id"], ("0", 1))[0]}}}
                 for e in edits_value["edits"]]
    path.write_text(json.dumps(seal({"edits_hash": edits_value["record_hash"], "decisions": decisions})))
    return path


def test_cli_refuses_foreign_tampered_or_reused_measurements(tmp_path):
    panel, base, half_a, half_b = _setup(tmp_path)
    halves = ["%s:bzero" % half_a, "%s:bzero" % half_b]
    with pytest.raises(SystemExit):  # one probe cannot be both halves
        tool.noise(tmp_path / "parent.md", ["%s:bzero" % half_a] * 2, tmp_path / "profile.json", tmp_path / "n0.json")
    other_parent = _probe(tmp_path / "x", panel, {"bzero": PARENT + "- extra\n"}, {"bzero": base}, started=PAST)
    with pytest.raises(SystemExit):  # the halves must measure the parent text
        tool.noise(tmp_path / "parent.md", ["%s:bzero" % half_a, "%s:bzero" % other_parent], tmp_path / "profile.json",
                   tmp_path / "n1.json")
    tool.noise(tmp_path / "parent.md", halves, tmp_path / "profile.json", tmp_path / "noise.json")
    value = tool.decompose(tmp_path / "parent.md", ["cand=%s" % (tmp_path / "cand.md")], tmp_path / "pool")
    e02 = (tmp_path / "pool" / "skills" / "cand-e02.md").read_text()
    early = _probe(tmp_path / "early", panel, {"bzero": PARENT, "cand-e02": e02}, {"bzero": base, "cand-e02": base},
                   started=PAST)
    with pytest.raises(SystemExit):  # measured before the noise registration
        tool.screen(tmp_path / "pool" / "edits.json", tmp_path / "noise.json", halves, early, tmp_path / "s1.json")
    wrong_text = _probe(tmp_path / "w", panel, {"bzero": PARENT, "cand-e02": e02 + "x"}, {"bzero": base, "cand-e02": base},
                        started=LATER)
    with pytest.raises(SystemExit):  # measured another text under the edit's name
        tool.screen(tmp_path / "pool" / "edits.json", tmp_path / "noise.json", halves, wrong_text, tmp_path / "s2.json")
    other_model = _probe(tmp_path / "m", panel, {"bzero": PARENT, "cand-e02": e02}, {"bzero": base, "cand-e02": base},
                         solver={**SOLVER, "model": "glm-5.3"}, started=LATER)
    with pytest.raises(SystemExit):  # another solver
        tool.screen(tmp_path / "pool" / "edits.json", tmp_path / "noise.json", halves, other_model, tmp_path / "s3.json")
    partial = _probe(tmp_path / "p", panel, {"bzero": PARENT, "cand-e02": e02},
                     {"bzero": base, "cand-e02": {i: s for i, s in base.items() if i != "I05"}}, started=LATER)
    with pytest.raises(SystemExit):  # incomplete runs
        tool.screen(tmp_path / "pool" / "edits.json", tmp_path / "noise.json", halves, partial, tmp_path / "s4.json")
    with pytest.raises(SystemExit):  # a parent probe named twice
        tool.screen(tmp_path / "pool" / "edits.json", tmp_path / "noise.json", halves + [halves[0]],
                    _probe(tmp_path / "ok", panel, {"bzero": PARENT, "cand-e02": e02}, {"bzero": base, "cand-e02": base},
                           started=LATER),
                    tmp_path / "s5.json")
    original = (tmp_path / "pool" / "edits.json").read_text()
    edits = json.loads(original)
    edits["edits"][2]["new"] = "- tampered\n"
    (tmp_path / "pool" / "edits.json").write_text(json.dumps(edits))
    with pytest.raises(SystemExit):  # a changed edits record no longer matches its content hash
        tool.load_edits(tmp_path / "pool" / "edits.json")
    (tmp_path / "pool" / "edits.json").write_text(original)
    assert tool.load_edits(tmp_path / "pool" / "edits.json")["record_hash"] == value["record_hash"]
    (tmp_path / "pool" / "skills" / "cand-e02.md").write_text("changed")
    with pytest.raises(SystemExit):  # a Skill file changed after decomposition
        tool.load_edits(tmp_path / "pool" / "edits.json")


def test_cli_enforces_the_registered_runs_and_scoring_references(tmp_path):
    panel, base, half_a, half_b = _setup(tmp_path)
    halves = ["%s:bzero" % half_a, "%s:bzero" % half_b]
    single = _probe(tmp_path / "one", panel, {"bzero": PARENT}, {"bzero": {i: s[:1] for i, s in base.items()}},
                    runs=1, started=PAST_B)
    with pytest.raises(SystemExit):  # a noise half with one run per item, against the registered two
        tool.noise(tmp_path / "parent.md", ["%s:bzero" % half_a, "%s:bzero" % single], tmp_path / "profile.json",
                   tmp_path / "n0.json")
    reg = tool.noise(tmp_path / "parent.md", halves, tmp_path / "profile.json", tmp_path / "noise.json")
    assert reg["runs"] == {"half": 2, "measured": 2, "parent_min": 4} and len(reg["scoring"]) == 20
    tool.decompose(tmp_path / "parent.md", ["cand=%s" % (tmp_path / "cand.md")], tmp_path / "pool")
    e02 = (tmp_path / "pool" / "skills" / "cand-e02.md").read_text()
    once = _probe(tmp_path / "s1", panel, {"bzero": PARENT, "cand-e02": e02},
                  {"bzero": {i: s[:1] for i, s in base.items()}, "cand-e02": {i: s[:1] for i, s in base.items()}},
                  runs=1, started=LATER)
    with pytest.raises(SystemExit):  # a screen probe with one run per item
        tool.screen(tmp_path / "pool" / "edits.json", tmp_path / "noise.json", halves, once, tmp_path / "x1.json")
    good = _probe(tmp_path / "s2", panel, {"bzero": PARENT, "cand-e02": e02}, {"bzero": base, "cand-e02": base},
                  started=LATER)
    with pytest.raises(SystemExit):  # one half alone gives the parent two runs per item, not the registered four
        tool.screen(tmp_path / "pool" / "edits.json", tmp_path / "noise.json", halves[:1], good, tmp_path / "x2.json")
    rows = json.loads(panel.read_text())
    rows["tasks"][4]["private"]["answer"] = "9.99"  # same question and context, another reference answer
    other = tmp_path / "other-panel.json"
    other.write_text(json.dumps(rows))
    regraded = _probe(tmp_path / "s3", other, {"bzero": PARENT, "cand-e02": e02}, {"bzero": base, "cand-e02": base},
                      started=LATER)
    with pytest.raises(SystemExit):  # scored against another reference
        tool.screen(tmp_path / "pool" / "edits.json", tmp_path / "noise.json", halves, regraded, tmp_path / "x3.json")
    assert tool.screen(tmp_path / "pool" / "edits.json", tmp_path / "noise.json", halves, good,
                       tmp_path / "x4.json")["results"]
    # a provenance key the scorer never reads does not change the scoring inputs (a panel partition vs an item file)
    rows = json.loads(panel.read_text())
    for task in rows["tasks"]:
        task["private"]["source_sha256"] = "0" * 64
    provenance = tmp_path / "provenance-panel.json"
    provenance.write_text(json.dumps(rows))
    same = _probe(tmp_path / "s4", provenance, {"bzero": PARENT, "cand-e02": e02}, {"bzero": base, "cand-e02": base},
                  started=LATER)
    assert tool.screen(tmp_path / "pool" / "edits.json", tmp_path / "noise.json", halves, same,
                       tmp_path / "x5.json")["results"]
