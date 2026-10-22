"""FakeResearch for the fivebench-execskill-v1 examiner tests (implementation plan §7; T-RES-1..3, T-GEN-6): the frozen
research sources without network -- owned by A11, beside A2's ``execskill_fakes.py`` (whose ``glm_roles`` scripts the
GLM-5.3 researcher).

- ``FakeWikipedia``: an ``httpx.MockTransport`` English Wikipedia API that answers only the frozen parameters
  (``research.search_params``/``page_params``) at ``research.WIKIPEDIA_API``; any other host, path or parameter set
  fails the test. Pages: an eligible numeric table, a page whose table is not eligible, a definition paragraph, a
  redirect (``Revenue`` -> ``Government revenue``), a disambiguation page, a "Jeopardy" title and a redirect that
  lands on one. ``redirect_to`` makes every request answer HTTP 302 to another host (which must not be followed).
- ``archive_fixture(root)``: an archive directory with ``index.json`` pinning each file's sha256 -- LibreOffice Calc
  help pages (ROUND, SUM), a Python and an openpyxl page and a public task card.
- reply builders of the researcher's three calls (query, pick, conclude) for ``glm_roles``.
Nothing here is real benchmark content.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qsl

import httpx

from skillopt.execskill import research

TABLE_HTML = (
    "<p>Government revenue is money received by a government.</p>"
    "<table><caption>Receipts by year (billions)</caption>"
    "<tr><th>Year</th><th>Income tax</th><th>Customs</th><th>Total</th></tr>"
    "<tr><td>2019</td><td>1,718</td><td>71</td><td>1,789</td></tr>"
    "<tr><td>2020</td><td>1,609</td><td>68</td><td>1,677</td></tr>"
    "<tr><td>2021</td><td>2,044</td><td>80</td><td>2,124</td></tr></table>")
SMALL_TABLE_HTML = "<p>A short list.</p><table><tr><td>only one row</td></tr></table>"
DEFINITION = ("In mathematics, the derivative is a fundamental tool that quantifies the sensitivity to change of a "
              "function's output with respect to its input.")
DEFINITION_HTML = "<p>%s</p><p>The derivative of x^n is n x^(n-1).</p>" % DEFINITION
GROWTH_HTML = "<p>The economy grew by 3.2 percent in 2021, and inflation reached 4.7 percent.</p>"

PAGES = {  # requested title -> (final title, revid, html, redirects, disambiguation)
    "Government revenue": ("Government revenue", 1001, TABLE_HTML, [], False),
    "Revenue": ("Government revenue", 1001, TABLE_HTML, [{"from": "Revenue", "to": "Government revenue"}], False),
    "Short list": ("Short list", 1002, SMALL_TABLE_HTML, [], False),
    "Derivative": ("Derivative", 1003, DEFINITION_HTML, [], False),
    "Economic growth": ("Economic growth", 1004, GROWTH_HTML, [], False),
    "Budget": ("Budget", 1005, "<p>Budget may refer to several things.</p>", [], True),
    "Quiz numbers": ("Jeopardy! records", 1006, "<p>Quiz records.</p>",
                     [{"from": "Quiz numbers", "to": "Jeopardy! records"}], False),
}
SEARCHES = {  # query (lower case) -> titles
    "government revenue table": ["Government revenue", "Jeopardy! answers", "Short list"],
    "revenue": ["Revenue"],
    "derivative definition": ["Derivative"],
    "economic growth rate": ["Economic growth"],
    "budget": ["Budget", "Quiz numbers"],
}

ARCHIVE_FILES = {
    "calc-round.html": ("LibreOffice Calc: ROUND",
                        "<h1>ROUND</h1><p>Rounds a number to a certain number of decimal places.</p>"
                        "<p>Syntax: ROUND(Number [; Count])</p>"),
    "calc-sum.html": ("LibreOffice Calc: SUM",
                      "<h1>SUM</h1><p>Adds all the numbers in a range of cells.</p>"
                      "<p>Syntax: SUM(Number 1[; Number 2][; ... ;[Number 255]])</p>"),
    "python-fractions.html": ("Python 3.11: fractions",
                              "<p>The fractions module provides support for rational number arithmetic.</p>"),
    "openpyxl-cell.html": ("openpyxl: cell", "<p>A cell holds a value and an optional number format.</p>"),
    "card-spreadsheetbench.txt": ("Task card: SpreadsheetBench",
                                  "Write a Python program that reads the input workbook and writes the answer."),
}


class FakeWikipedia:
    """The frozen Wikipedia interface over ``PAGES`` and ``SEARCHES``; ``requests`` keeps (host, path, params,
    user agent) of every request in order."""

    def __init__(self, *, redirect_to=None):
        self.requests, self.redirect_to = [], redirect_to
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request):
        params = dict(parse_qsl(request.url.query.decode(), keep_blank_values=True))
        self.requests.append((request.url.host, request.url.path, params, request.headers.get("user-agent")))
        api = httpx.URL(research.WIKIPEDIA_API)
        if (request.url.scheme, request.url.host, request.url.path) != (api.scheme, api.host, api.path):
            raise AssertionError("A request outside the frozen API: %s" % request.url)
        if self.redirect_to is not None:
            return httpx.Response(302, headers={"Location": self.redirect_to})
        if params.get("action") == "query":
            query = params.get("srsearch", "")
            assert params == _strings(research.search_params(query)), params
            titles = SEARCHES.get(query.lower(), [])
            return httpx.Response(200, json={"query": {"search": [{"title": t} for t in titles]}})
        title = params.get("page", "")
        assert params == _strings(research.page_params(title)), params
        if title not in PAGES:
            return httpx.Response(200, json={"error": {"code": "missingtitle"}})
        final, revid, html, redirects, disambiguation = PAGES[title]
        parsed = {"title": final, "revid": revid, "text": html, "redirects": redirects,
                  "properties": {"disambiguation": ""} if disambiguation else {}}
        return httpx.Response(200, json={"parse": parsed})


def _strings(params):
    return {key: str(value) for key, value in params.items()}


def archive_fixture(root):
    """The archive directory under ``root``: each file of ``ARCHIVE_FILES`` and ``index.json`` pinning its sha256."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    index = {}
    for name, (title, body) in ARCHIVE_FILES.items():
        (root / name).write_text(body, encoding="utf-8")
        index[name] = {"sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "title": title}
    (root / "index.json").write_text(json.dumps(index, sort_keys=True), encoding="utf-8")
    return root


def sources(root, *, wikipedia=None, archive=True):
    """(research.Sources over the fakes with its store under ``root``, the FakeWikipedia)."""
    fake = wikipedia or FakeWikipedia()
    opened = research.Archive(archive_fixture(Path(root) / "archive")) if archive else None
    return research.Sources(research.Wikipedia(transport=fake.transport), opened, Path(root) / "store"), fake


# ------------------------------------------------------------------------------------- the researcher's replies
def query(*queries, source=None):
    return {"queries": list(queries), **({"source": source} if source else {})}


def pick(*keys):
    return {"pages": list(keys)}


def table(page="P1", index=0):
    return {"status": "found", "page": page, "table": index}


def definition(quote, page="P1"):
    return {"status": "found", "page": page, "quote": quote}


def found(conclusion, *quotes):
    """A verify or function conclusion: ``quotes`` as (page, text) pairs."""
    return {"status": "found", "conclusion": conclusion, "quotes": [{"page": p, "text": t} for p, t in quotes]}


def values(*entries):
    """A parameter conclusion: ``entries`` as (name, value, page, quote text)."""
    return {"status": "found", "values": [{"name": n, "value": v, "quote": {"page": p, "text": t}}
                                          for n, v, p, t in entries]}


CONTINUE = {"status": "continue"}
NONE = {"status": "none"}
