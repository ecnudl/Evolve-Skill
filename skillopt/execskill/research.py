"""Examiner research, the mandatory step of every generation path (protocol ``fivebench-execskill-v1``; registration
§7.2 "查证", §4.3, §5.3, §21 owner rule (b); implementation plan §1 research row; T-RES-1..3).

A copy of the frozen v3 research machinery (``skillopt/coevo5/research.py``) under this protocol's version: the
sources, the archive, the write-once store, the call ceilings, the verbatim check and the request loop are the frozen
code with byte-identical API parameters (``search_params``/``page_params``, coevo5/research.py:135-143); only
``USER_AGENT`` names the new version (and, registrar addendum 2026-10-23 05:3x, a contact URL). Left out: v3's
``rewrite`` and its ``skill.Rule`` import (route B has no rule texts) and v3's forward ``material`` (replaced by the
route-B request kinds below).

The sources are frozen (§7.2): the English Wikipedia API at fixed parameters -- the final title, the revision id and
the redirects followed are kept; disambiguation pages and titles containing "Jeopardy" (SearchQA's source) are
dropped, also after a redirect (coevo5/research.py:53, :190-192) -- and a pre-launch archive of documents pinned by
SHA-256 (Python 3.11, openpyxl and LibreOffice Calc help pages, the five public task cards), verified when it is opened
(:353-393). Nothing else is accessed: one explicit credential-free proxy, never the environment's (:145-154), and no
redirect is followed. Every search result list and every page body is archived write-once under the unit's store,
named by its hash, before it is used (:395-407; ``write_json`` is the write-once ``write_immutable_json``,
continual_eval/core.py:60-61).

A request is at most 3 rounds of at most 3 queries, at most 3 pages read in all and at most 8 model calls -- an invalid
reply consumes its call and is never retried; a round (query, pick, conclude) starts only while its three calls and a
page still fit (coevo5/protocol.py:254-257; research.py:17-19, :63). A quote must occur verbatim (whitespace
normalized) in the archived text of the page it names, else the finding is void and the request goes on (:342-346,
:510-531). The researcher (GLM-5.3, charged by the caller's endpoint to ``<chain>:...:examiner:research``) sees the
request and the pages it reads -- never a benchmark item: ``Researcher`` screens every request text with the frozen
mechanical leakage checks before dispatch (coevo5/leakage.py ``mechanical``; v3 step.py:278) and refuses it on any hit.

Route-B request kinds (§7.2; plan research row):
- ``family_material``: the material of one transformation family -- OfficeQA an eligible Wikipedia numeric table
  (2-60 rows, 2-15 columns, a numeric cell; research.py:59, :328-334), LiveMath a verbatim Wikipedia definition or
  theorem of at most 1,500 characters (:58), SpreadsheetBench an archived LibreOffice Calc help quote of one function
  (purpose ``function``: archive only; the quote must name the function);
- ``parameter_choice``: values of named family parameters, each backed by a verbatim quote in which the value is
  written (purpose ``parameter``); values outside the family's registered ranges are dropped by the family's caller;
- ``selection_hint``: a verified statement (purpose ``verify``) used only to write an ALFWorld selection filter.
At most ``MAX_RESEARCH_REQUESTS`` (24) requests per step and bench (calc T11). ``split`` divides the qualified findings
by the seed tag ``execskill-v1:research-split:<unit>`` into a G_self and a G_acc half that share no material, and the
sealed split record carries both halves' hashes before the engineer step (§5.3).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from fractions import Fraction
from html.parser import HTMLParser

import httpx

from skillopt.coevo5 import leakage
from skillopt.coevo5.protocol import ARCHIVE_MIN_WORD_SHARE
from skillopt.coevo5.roles import Invalid, fields, items, text
from skillopt.continual_eval.core import require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import VERSION
from .client import POOL_LIMITS
from .protocol import (
    BENCHES,
    LIVEMATH_DEFINITION_CHARS,
    MAX_RESEARCH_REQUESTS,
    OFFICEQA_TABLE_COLUMNS,
    OFFICEQA_TABLE_ROWS,
    RESEARCH_MAX_CALLS,
    RESEARCH_MAX_PAGES,
    RESEARCH_MAX_QUERIES,
    RESEARCH_MAX_ROUNDS,
    RESEARCH_REQUESTS,
    record,
    research_split_tag,
)

# §7.2: the frozen sources (recorded in the manifest).
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
# registrar addendum 2026-10-23 05:3x: Wikimedia's User-Agent policy asks for contact information. From dl through
# the PJLAB gateway the contact-free agent "execskill-research/1 (fivebench-execskill-v1)" got HTTP 403 ("Please
# respect our robot policy", https://w.wiki/4wJS) on 9 of 9 requests -- the chain-G smoke's S3 generator_research
# row failed on it -- and the same request with a contact URL got 200 on 7 of 7. Only the header changed: the
# parameters, limits, retries and timeouts are as before.
CONTACT = "https://github.com/ecnudl/Evolve-Skill"
USER_AGENT = "execskill-research/1 (%s; %s)" % (VERSION, CONTACT)
SEARCH_LIMIT = 5  # results of one Wikipedia query
ARCHIVE_LIMIT = 5  # results of one archive query
EXCLUDED_TITLE = "jeopardy"  # SearchQA's source: no page or result whose title contains it
MAX_QUERY_CHARS = 100
MAX_CONCLUSION_CHARS = 1000
MAX_QUOTES, MAX_QUOTE_CHARS = 3, 500
MAX_DEFINITION_CHARS = LIVEMATH_DEFINITION_CHARS
TABLE_ROWS, TABLE_COLUMNS = OFFICEQA_TABLE_ROWS, OFFICEQA_TABLE_COLUMNS
EXCERPT_CHARS = 8000  # page text shown per page (quotes are checked against the whole archived page)
LEAD_CHARS = 2000  # of an excerpt, at most this (and a quarter) for the page's opening lines; then the richest lines
PREVIEW_TABLES, PREVIEW_ROWS, PREVIEW_CELL_CHARS = 10, 6, 60  # what a table request is shown of each page
CALLS_PER_ROUND = 3  # query, pick, conclude
MAX_PARAMETERS = 6  # values of one parameter_choice request
MAX_PARAMETER_CHARS = 40  # a parameter's name or value as written

PURPOSES = ("verify", "table", "definition", "function", "parameter")
MATERIAL_PURPOSE = {"officeqa": "table", "livemath": "definition", "spreadsheetbench": "function"}
MATERIAL_BENCHES = tuple(MATERIAL_PURPOSE)

QUERY_SYSTEM = (
    "You are the researcher of a study that writes short guidance rules for a language model. You receive one "
    "research request as JSON: its purpose, the request text, possibly the guidance rule it concerns, the queries "
    "already tried and the pages already read. Write search queries for one of the allowed sources: \"wikipedia\" "
    "searches English Wikipedia articles; \"archive\" searches a fixed archive of documentation pages (the Python 3.11 "
    "standard library, openpyxl, the LibreOffice Calc functions) and public task descriptions; short queries of a few "
    "distinctive words work best there. Search for general knowledge only.\n\n"
    "Reply with only a JSON object: {\"queries\": [one to three search queries, each at most 100 characters], "
    "\"source\": one of the allowed sources}.")
PICK_SYSTEM = (
    "You are the researcher of a study that writes short guidance rules for a language model. You receive one "
    "research request as JSON and the search results of this round (key, source, title). Choose the pages most likely "
    "to answer the request, at most pages_left of them; an empty list reads nothing this round.\n\n"
    "Reply with only a JSON object: {\"pages\": [result keys]}.")
CONCLUDE_SYSTEM = {
    "verify": (
        "You are the researcher of a study that writes short guidance rules for a language model. You receive a "
        "research question about a guidance rule and excerpts of the pages read so far (key, source, title, text). "
        "If the pages settle the question, state the conclusion and support it with one to three quotes copied "
        "character for character from the page texts (whitespace may differ). If reading more pages could settle it, "
        "continue; if these sources cannot settle it, answer none.\n\n"
        "Reply with only a JSON object, one of: {\"status\": \"found\", \"conclusion\": \"at most 1000 characters\", "
        "\"quotes\": [{\"page\": \"page key\", \"text\": \"an exact quote of at most 500 characters\"}]}, "
        "{\"status\": \"continue\"}, {\"status\": \"none\"}."),
    "table": (
        "You are the researcher of a study that writes practice questions. You receive a request for a data table and "
        "previews of the eligible tables of the pages read so far (page key, table index, caption, size, first rows). "
        "Choose one table whose cells hold numbers from which questions requiring a calculation can be written. If "
        "reading more pages could find a better table, continue; if none can be found, answer none.\n\n"
        "Reply with only a JSON object, one of: {\"status\": \"found\", \"page\": \"page key\", \"table\": table "
        "index}, {\"status\": \"continue\"}, {\"status\": \"none\"}."),
    "definition": (
        "You are the researcher of a study that writes practice questions. You receive a request for a mathematical "
        "definition or theorem and excerpts of the pages read so far (key, source, title, text). Choose the passage "
        "that states it and copy it character for character (whitespace may differ), at most 1500 characters. If "
        "reading more pages could find it, continue; if it cannot be found, answer none.\n\n"
        "Reply with only a JSON object, one of: {\"status\": \"found\", \"page\": \"page key\", \"quote\": \"the exact "
        "passage\"}, {\"status\": \"continue\"}, {\"status\": \"none\"}."),
    "function": (
        "You are the researcher of a study that writes practice spreadsheet tasks. You receive a request about one "
        "LibreOffice Calc function and excerpts of the documentation pages read so far (key, source, title, text). If "
        "the pages state what the function computes and how it is called, summarize that and support it with one to "
        "three quotes copied character for character from the page texts (whitespace may differ), at least one of "
        "them naming the function. If reading more pages could find it, continue; if it cannot be found, answer "
        "none.\n\n"
        "Reply with only a JSON object, one of: {\"status\": \"found\", \"conclusion\": \"at most 1000 characters\", "
        "\"quotes\": [{\"page\": \"page key\", \"text\": \"an exact quote of at most 500 characters\"}]}, "
        "{\"status\": \"continue\"}, {\"status\": \"none\"}."),
    "parameter": (
        "You are the researcher of a study that writes practice questions. You receive a request for realistic values "
        "of named parameters (\"subject\" lists the names) and excerpts of the pages read so far (key, source, title, "
        "text). For each parameter you can support, give one value written exactly as it appears in a quote copied "
        "character for character from the page texts (whitespace may differ). If reading more pages could find the "
        "values, continue; if they cannot be found, answer none.\n\n"
        "Reply with only a JSON object, one of: {\"status\": \"found\", \"values\": [{\"name\": \"a parameter name\", "
        "\"value\": \"the number as written in the quote\", \"quote\": {\"page\": \"page key\", \"text\": \"an exact "
        "quote of at most 500 characters\"}}]}, {\"status\": \"continue\"}, {\"status\": \"none\"}."),
}
MATERIAL_REQUEST = {
    "officeqa": "Find an English Wikipedia article on the topic below that contains a table of numbers (for example "
                "statistics, measurements, finances or results by year) from which questions requiring a calculation "
                "can be written.",
    "livemath": "Find an English Wikipedia article that states the mathematical definition or theorem named below, "
                "from which a question with a numerical answer can be computed.",
    "spreadsheetbench": "Find the LibreOffice Calc help page of the function named below and quote what it computes "
                        "and how it is called.",
}

PROXY = re.compile(r"https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/?")  # explicit, without credentials
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
WORD = re.compile(r"[a-z0-9]+")
NUMBER = re.compile(r"[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
FUNCTION = re.compile(r"[A-Z][A-Z0-9]*(?:\.[A-Z0-9]+)*")  # a spreadsheet function name
BLOCK = frozenset({"p", "div", "li", "ul", "ol", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
                   "pre", "section", "figure", "figcaption", "br", "hr"})


class FetchError(RuntimeError):
    """A source that failed or answered outside its frozen interface: a failed search or fetch, recorded; never a stop
    of the run."""


def search_params(query):
    return {"action": "query", "list": "search", "srsearch": query, "srlimit": SEARCH_LIMIT, "srnamespace": 0,
            "srprop": "", "format": "json", "formatversion": 2}


def page_params(title):
    return {"action": "parse", "page": title, "prop": "text|revid|properties", "redirects": 1,
            "disableeditsection": 1, "disabletoc": 1, "format": "json", "formatversion": 2}


class Wikipedia:
    """The English Wikipedia API at the frozen parameters (§7.2). ``proxy``: an explicit proxy without credentials
    (the environment's proxy settings are never read); ``transport``: for tests."""

    def __init__(self, *, proxy=None, transport=None, timeout=60):
        require(proxy is None or (type(proxy) is str and PROXY.fullmatch(proxy) is not None),
                "A proxy is an explicit http(s) host without credentials")
        options = {"transport": transport} if transport is not None else ({"proxy": proxy} if proxy else {})
        # v2.1 (Codex review 2026-10-24 #1): no connection cap, as the model clients (``client.POOL_LIMITS``)
        self.client = httpx.Client(timeout=timeout, limits=POOL_LIMITS, trust_env=False, follow_redirects=False,
                                   headers={"User-Agent": USER_AGENT}, **options)

    def _get(self, params):
        try:
            response = self.client.get(WIKIPEDIA_API, params=params)
        except httpx.HTTPError as error:
            raise FetchError("transport:" + type(error).__name__) from None
        if response.status_code != 200:
            raise FetchError("http_%d" % response.status_code)
        try:
            value = response.json()
        except ValueError:
            raise FetchError("invalid_json") from None
        if type(value) is not dict or "error" in value:
            raise FetchError("api_error")
        return value

    def search(self, query):
        """Titles of the first results of ``query``, in the API's order."""
        found = self._get(search_params(query)).get("query")
        hits = found.get("search") if type(found) is dict else None
        if type(hits) is not list or not all(type(h) is dict and type(h.get("title")) is str for h in hits):
            raise FetchError("malformed_search")
        return [h["title"] for h in hits[:SEARCH_LIMIT]]

    def page(self, title):
        """{"title": the final title, "revid", "redirects": [{"from", "to"}], "html", "disambiguation"}."""
        parsed = self._get(page_params(title)).get("parse")
        if (type(parsed) is not dict or type(parsed.get("title")) is not str or type(parsed.get("revid")) is not int
                or type(parsed.get("text")) is not str):
            raise FetchError("malformed_page")
        redirects, properties = parsed.get("redirects", []), parsed.get("properties", {})
        if type(redirects) is not list or not all(type(r) is dict and type(r.get("from")) is str
                                                  and type(r.get("to")) is str for r in redirects):
            raise FetchError("malformed_page")
        if type(properties) is dict:  # formatversion 2
            disambiguation = "disambiguation" in properties
        elif type(properties) is list:
            disambiguation = any(type(p) is dict and p.get("name") == "disambiguation" for p in properties)
        else:
            raise FetchError("malformed_page")
        return {"title": parsed["title"], "revid": parsed["revid"],
                "redirects": [{"from": r["from"], "to": r["to"]} for r in redirects], "html": parsed["text"],
                "disambiguation": disambiguation}

    def close(self):
        self.client.close()


# ---------------------------------------------------------------------------------------------------- page text
def _squeeze(value):
    return " ".join(value.split())


class _Page(HTMLParser):
    """Plain text and tables of an HTML page: script, style and reference markers dropped; a table row is its cells
    joined by " | " on a line of its own; block elements end a line. A nested table's text belongs to it only."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.current, self.tables, self.open = [], [], [], []
        self.skipping, self.depth = None, 0

    def handle_starttag(self, tag, attrs):
        if self.skipping is not None:
            self.depth += tag == self.skipping
            return
        classes = (dict(attrs).get("class") or "").split()
        if tag in ("script", "style") or (tag == "sup" and "reference" in classes):
            self.skipping, self.depth = tag, 1
        elif tag == "table":
            self._break()
            self.open.append({"caption": [], "rows": [], "row": None, "cell": None, "captioning": False})
        elif self.open:
            table = self.open[-1]
            if tag == "tr":
                self._end_row(table)
                table["row"] = []
            elif tag in ("td", "th"):
                self._end_cell(table)
                table["cell"] = []
            elif tag == "caption":
                table["captioning"] = True
            elif tag in BLOCK:
                self._text(" ")
        elif tag in BLOCK:
            self._break()

    def handle_endtag(self, tag):
        if self.skipping is not None:
            if tag == self.skipping:
                self.depth -= 1
                if self.depth == 0:
                    self.skipping = None
            return
        if tag == "table" and self.open:
            self._end_table()
        elif self.open:
            table = self.open[-1]
            if tag in ("td", "th"):
                self._end_cell(table)
            elif tag == "tr":
                self._end_row(table)
            elif tag == "caption" and table["captioning"]:
                table["captioning"] = False
                self._line(_squeeze("".join(table["caption"])))
        elif tag in BLOCK:
            self._break()

    def handle_data(self, data):
        if self.skipping is None:
            self._text(data)

    def close(self):
        super().close()
        while self.open:
            self._end_table()
        self._break()

    def _text(self, data):
        if not self.open:
            self.current.append(data)
            return
        table = self.open[-1]
        if table["cell"] is not None:
            table["cell"].append(data)
        elif table["captioning"]:
            table["caption"].append(data)

    def _end_cell(self, table):
        if table["cell"] is not None:
            table["row"] = [] if table["row"] is None else table["row"]
            table["row"].append(_squeeze("".join(table["cell"])))
            table["cell"] = None

    def _end_row(self, table):
        self._end_cell(table)
        if table["row"]:
            table["rows"].append(table["row"])
            self._line(" | ".join(table["row"]))
        table["row"] = None

    def _end_table(self):
        table = self.open.pop()
        self._end_row(table)
        self.tables.append({"caption": _squeeze("".join(table["caption"])), "rows": table["rows"]})

    def _break(self):
        line = _squeeze("".join(self.current))
        if line:
            self.lines.append(line)
        self.current = []

    def _line(self, value):
        self._break()
        if value:
            self.lines.append(value)


def page_text(html):
    """(text, tables) of an HTML page; tables in document order (an inner table before its outer one), each
    {"caption", "rows": [[cell text]]}."""
    parser = _Page()
    parser.feed(html)
    parser.close()
    return "\n".join(parser.lines), parser.tables


def numeric(cell):
    """A cell holding one number (thousands separators, a leading currency sign or a trailing % allowed)."""
    value = cell.strip().lstrip("$€£¥").rstrip("%").strip()
    return NUMBER.fullmatch(value) is not None


def eligible(table):
    """A table OfficeQA-style items can be written from (§7.2): 2-60 rows, 2-15 columns, a numeric cell."""
    rows = table["rows"]
    columns = max((len(row) for row in rows), default=0)
    return (TABLE_ROWS[0] <= len(rows) <= TABLE_ROWS[1] and TABLE_COLUMNS[0] <= columns <= TABLE_COLUMNS[1]
            and any(numeric(cell) for row in rows for cell in row))


def render_table(table):
    """The material text of a table: its caption line, then each row's cells joined by " | "."""
    lines = ([table["caption"]] if table["caption"] else []) + [" | ".join(row) for row in table["rows"]]
    return "\n".join(lines)


def verbatim(quote, page):
    """Whether ``quote`` occurs in ``page`` once whitespace is normalized on both sides."""
    quote = _squeeze(quote)
    return bool(quote) and quote in _squeeze(page)


def number_value(written):
    """The exact value of a number as written (thousands separators and a U+2212 minus allowed), else None."""
    if type(written) is not str or NUMBER.fullmatch(written.strip()) is None:
        return None
    return Fraction(written.strip().replace(",", "").replace("−", "-"))


def _excluded(title):
    return EXCLUDED_TITLE in title.lower()


# ------------------------------------------------------------------------------------------------------ sources
class Archive:
    """The pre-launch archive (§7.2): ``root/index.json`` = {name: {"sha256", "title"}} and the files it names, each
    verified against its hash when the archive is opened; an HTML file is read as its text. ``index_sha256``: the
    index's own hash, which the launch manifest binds."""

    def __init__(self, root):
        self.root = safe_path(root)
        raw = safe_path(self.root / "index.json").read_bytes()
        self.index_sha256 = hashlib.sha256(raw).hexdigest()
        index = json.loads(raw.decode("utf-8"))
        require(type(index) is dict and index, "An archive has an index")
        self.titles, self.texts, self.hashes = {}, {}, {}
        for name, entry in sorted(index.items()):
            require(NAME.fullmatch(name) is not None and name != "index.json" and type(entry) is dict
                    and set(entry) == {"sha256", "title"} and type(entry["sha256"]) is str
                    and type(entry["title"]) is str and entry["title"].strip(), "Malformed archive index")
            raw = (self.root / name).read_bytes()
            require(hashlib.sha256(raw).hexdigest() == entry["sha256"], "An archived document changed: " + name)
            body = raw.decode("utf-8")
            self.texts[name] = page_text(body)[0] if name.endswith((".html", ".htm")) else body
            self.titles[name], self.hashes[name] = entry["title"], entry["sha256"]

    def search(self, query):
        """Up to 5 names whose text holds at least half of ``query``'s distinct words (``WORD``, whole words, any case;
        at least one), ranked by the number of distinct words held, then by their occurrences, then by name."""
        words = sorted(set(WORD.findall(query.lower())))
        need = max(1, math.ceil(ARCHIVE_MIN_WORD_SHARE * len(words)))
        ranked = []
        for name, body in self.texts.items():
            lower = body.lower()
            counts = [len(re.findall(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(word), lower)) for word in words]
            held = sum(1 for c in counts if c)
            if words and held >= need:
                ranked.append((-held, -sum(counts), name))
        return [name for _, _, name in sorted(ranked)[:ARCHIVE_LIMIT]]

    def page(self, name):
        require(name in self.texts, "Unknown archived document")
        return self.texts[name]


class Sources:
    """The searches and pages of one unit attempt. Everything fetched is archived write-once under ``store/sources/``,
    named by its hash, before it is used; a page fetched again in the same attempt is the archived one."""

    def __init__(self, wikipedia, archive, store):
        self.wikipedia, self.archive = wikipedia, archive
        self.store = safe_path(store) / "sources"
        self.pages = {}

    def keep(self, value):
        sha = digest(value)
        write_json(self.store / (sha + ".json"), value)
        return sha

    def search(self, source, query):
        """{"source", "query", "archive", "results": [{"source", "title", "ref"}], "dropped": [titles]}, or with
        "error" (a failed search; nothing archived)."""
        require(source in ("wikipedia", "archive"), "Unknown source")
        if source == "wikipedia":
            try:
                found = [(title, title) for title in self.wikipedia.search(query)]
            except FetchError as error:
                return {"source": source, "query": query, "error": str(error), "results": [], "dropped": []}
        elif self.archive is None:
            return {"source": source, "query": query, "error": "no_archive", "results": [], "dropped": []}
        else:
            found = [(self.archive.titles[name], name) for name in self.archive.search(query)]
        sha = self.keep({"kind": "search", "source": source, "query": query,
                         "results": [{"title": title, "ref": ref} for title, ref in found]})
        return {"source": source, "query": query, "archive": sha,
                "results": [{"source": source, "title": t, "ref": r} for t, r in found if not _excluded(t)],
                "dropped": [t for t, _ in found if _excluded(t)]}

    def fetch(self, source, ref):
        """{"source", "title", "revid", "archive", "text", "tables"}, with "dropped" (a disambiguation page, a title
        containing "Jeopardy" before or after a redirect) or as {"source", "title", "error"} (a failed fetch)."""
        require(source in ("wikipedia", "archive"), "Unknown source")
        if (source, ref) in self.pages:
            return self.pages[(source, ref)]
        if source == "wikipedia":
            try:
                got = self.wikipedia.page(ref)
            except FetchError as error:
                return {"source": source, "title": ref, "error": str(error)}
            sha = self.keep({"kind": "page", "source": source, "requested": ref, **got})
            names = [ref, got["title"]] + [r[side] for r in got["redirects"] for side in ("from", "to")]
            dropped = ("disambiguation" if got["disambiguation"]
                       else "excluded_title" if any(_excluded(n) for n in names) else None)
            body, tables = page_text(got["html"])
            page = {"source": source, "title": got["title"], "revid": got["revid"], "archive": sha, "text": body,
                    "tables": tables, **({"dropped": dropped} if dropped else {})}
        else:
            require(self.archive is not None, "No archive")
            body = self.archive.page(ref)
            sha = self.keep({"kind": "page", "source": source, "name": ref, "title": self.archive.titles[ref],
                             "sha256": self.archive.hashes[ref], "text": body})
            page = {"source": source, "title": self.archive.titles[ref], "revid": None, "archive": sha, "text": body,
                    "tables": []}
        self.pages[(source, ref)] = page
        return page


# ----------------------------------------------------------------------------------------------------- requests
def _query(value, allowed):
    if len(allowed) > 1:
        fields(value, ["queries", "source"])
        if value["source"] not in allowed:
            raise Invalid("source")
    else:  # a single-source request searches that source only, whatever the reply names
        fields(value, ["queries"], ["source"])
    listed = items(value["queries"], limit=RESEARCH_MAX_QUERIES, low=1)
    queries = [text(query, limit=MAX_QUERY_CHARS).strip() for query in listed]
    return {"queries": queries, "source": value["source"] if len(allowed) > 1 else allowed[0]}


def _pick(value, keys):
    pages = items(fields(value, ["pages"])["pages"], limit=len(keys))
    if not all(type(key) is str and key in keys for key in pages) or len(set(pages)) != len(pages):
        raise Invalid("pages")
    return {"pages": pages}


def _quotes(value):
    quotes = items(value, limit=MAX_QUOTES, low=1)
    for quote in quotes:
        fields(quote, ["page", "text"])
        text(quote["text"], limit=MAX_QUOTE_CHARS)
    return [dict(q) for q in quotes]


def _conclusion(value, purpose, keys):
    status = value.get("status") if type(value) is dict else None
    if status in ("continue", "none"):
        return fields(value, ["status"])
    if status != "found":
        raise Invalid("status")
    if purpose in ("verify", "function"):
        fields(value, ["status", "conclusion", "quotes"])
        quotes = _quotes(value["quotes"])
        conclusion = text(value["conclusion"], limit=MAX_CONCLUSION_CHARS)
        pages = [quote["page"] for quote in quotes]
        found = {"status": status, "conclusion": conclusion, "quotes": quotes}
    elif purpose == "table":
        fields(value, ["status", "page", "table"])
        if type(value["table"]) is not int or value["table"] < 0:
            raise Invalid("table")
        pages, found = [value["page"]], {"status": status, "page": value["page"], "table": value["table"]}
    elif purpose == "definition":
        fields(value, ["status", "page", "quote"])
        pages = [value["page"]]
        found = {"status": status, "page": value["page"], "quote": text(value["quote"], limit=MAX_DEFINITION_CHARS)}
    else:  # parameter
        fields(value, ["status", "values"])
        values = items(value["values"], limit=MAX_PARAMETERS, low=1)
        for entry in values:
            fields(entry, ["name", "value", "quote"])
            text(entry["name"], limit=MAX_PARAMETER_CHARS)
            text(entry["value"], limit=MAX_PARAMETER_CHARS)
            _quotes([entry["quote"]])
        pages = [entry["quote"]["page"] for entry in values]
        found = {"status": status, "values": [{"name": e["name"], "value": e["value"], "quote": dict(e["quote"])}
                                              for e in values]}
    if not all(type(page) is str and page in keys for page in pages):
        raise Invalid("page")
    return found


def _source(page):
    return {"title": page["title"], "revid": page["revid"]}


def _cited(quote, pages):
    page = pages[quote["page"]]
    return {"page": quote["page"], "archive": page["archive"], **_source(page), "text": quote["text"]}


def _names_function(name, quote):
    return re.search(r"(?<![A-Za-z0-9_.])%s(?![A-Za-z0-9_])" % re.escape(name), quote, re.I) is not None


def _qualify(found, purpose, read, subject=None):
    """(the finding, None), or (None, why the finding is void)."""
    pages = {page["key"]: page for page in read}
    if purpose in ("verify", "function"):
        if not all(verbatim(q["text"], pages[q["page"]]["text"]) for q in found["quotes"]):
            return None, "quote_not_verbatim"
        if purpose == "function" and not any(_names_function(subject, q["text"]) for q in found["quotes"]):
            return None, "function_not_quoted"
        return {"conclusion": found["conclusion"], "quotes": [_cited(q, pages) for q in found["quotes"]]}, None
    if purpose == "parameter":
        values = []
        for entry in found["values"]:
            quote = entry["quote"]
            if not verbatim(quote["text"], pages[quote["page"]]["text"]):
                return None, "quote_not_verbatim"
            value = number_value(entry["value"])
            written = {number_value(m.group()) for m in NUMBER.finditer(quote["text"])}
            if entry["name"] not in subject or value is None or value not in written:
                return None, "value_not_quoted"
            values.append({"name": entry["name"], "value": entry["value"], "quote": _cited(quote, pages)})
        return {"values": values}, None
    page = pages[found["page"]]
    if purpose == "table":
        if found["table"] >= len(page["tables"]):
            return None, "unknown_table"
        table = page["tables"][found["table"]]
        if not eligible(table):
            return None, "ineligible_table"
        return {"table": {"page": page["key"], "archive": page["archive"], "index": found["table"], **table},
                "source": _source(page)}, None
    if not verbatim(found["quote"], page["text"]):
        return None, "quote_not_verbatim"
    return {"quote": found["quote"], "page": page["key"], "archive": page["archive"], "source": _source(page)}, None


def _excerpt(body, words, limit=EXCERPT_CHARS):
    """The page text a researcher is shown: the whole text when it fits; else its opening lines and then the lines
    richest in the request's words, in page order, with "[...]" where lines were left out."""
    if len(body) <= limit:
        return body
    lines = body.split("\n")
    chosen, size, lead = set(), 0, min(LEAD_CHARS, limit // 4)
    for index, line in enumerate(lines):
        if size + len(line) + 1 > lead:
            break
        chosen.add(index)
        size += len(line) + 1
    scored = sorted((-sum(word in line.lower() for word in words), index) for index, line in enumerate(lines))
    for score, index in scored:
        if score == 0:
            break
        if index not in chosen and size + len(lines[index]) + 6 <= limit:
            chosen.add(index)
            size += len(lines[index]) + 6
    if not chosen:  # a single overlong line: its opening part
        return body[:limit] + "\n[...]"
    shown, last = [], -1
    for index in sorted(chosen):
        if index != last + 1:
            shown.append("[...]")
        shown.append(lines[index])
        last = index
    return "\n".join(shown + (["[...]"] if last != len(lines) - 1 else []))


def _shown(page, purpose, words):
    if purpose != "table":
        return {"key": page["key"], "source": page["source"], "title": page["title"],
                "text": _excerpt(page["text"], words)}
    previews = [{"index": index, "caption": table["caption"], "rows": len(table["rows"]),
                 "columns": max(len(row) for row in table["rows"]),
                 "first_rows": [[cell[:PREVIEW_CELL_CHARS] for cell in row] for row in table["rows"][:PREVIEW_ROWS]]}
                for index, table in enumerate(page["tables"]) if eligible(table)]
    return {"key": page["key"], "title": page["title"], "tables": previews[:PREVIEW_TABLES]}


def _brief(page):
    return {"key": page["key"], "source": page["source"], "title": page["title"]}


def _allowed(purpose, sources):
    if purpose == "function":
        return ("archive",)  # SpreadsheetBench functions: the pinned LibreOffice Calc help pages only
    if purpose in ("verify", "parameter") and sources.archive is not None:
        return ("wikipedia", "archive")
    return ("wikipedia",)


def request(roles, sources, *, purpose, question, label, rule=None, subject=None):
    """One research request (§7.2; the frozen loop, coevo5/research.py:578-664). ``purpose``: "verify" (Wikipedia or
    the archive), "table" or "definition" (Wikipedia only), "function" (the archive only; ``subject``: the function
    name a quote must carry) or "parameter" (Wikipedia or the archive; ``subject``: the parameter names). ``rule``:
    the topic the request concerns, shown to the researcher. Returns {"purpose", "question", "rule", "subject",
    "status": "found" | "none", "reason", "conclusion", "quotes", "pages", "calls", "rounds", "log"} with the
    qualified finding's keys."""
    require(purpose in PURPOSES and type(question) is str and question.strip(), "Invalid research request")
    require(type(label) is str and label and (rule is None or (type(rule) is str and rule.strip())),
            "Invalid research request")
    if purpose == "function":
        require(type(subject) is str and FUNCTION.fullmatch(subject) is not None and sources.archive is not None,
                "A function request names one function and needs the archive")
    elif purpose == "parameter":
        require(isinstance(subject, (list, tuple)) and subject and all(type(s) is str and s for s in subject),
                "A parameter request names its parameters")
        subject = list(subject)
    else:
        require(subject is None, "Only function and parameter requests carry a subject")
    allowed = _allowed(purpose, sources)
    base = {"purpose": purpose, "request": question, "rule": rule, **({"subject": subject} if subject else {})}
    calls, used, read, tried, log = 0, 0, [], [], []
    seen = set()  # (source, ref) already picked in this request
    finding, reason = None, None
    for number in range(1, RESEARCH_MAX_ROUNDS + 1):
        if used >= RESEARCH_MAX_PAGES:
            reason = "pages_exhausted"
            break
        if RESEARCH_MAX_CALLS - calls < CALLS_PER_ROUND:
            reason = "calls_exhausted"
            break
        entry = {"round": number}
        log.append(entry)
        query = roles.ask("research_query", QUERY_SYSTEM,
                          {**base, "round": number, "sources": list(allowed), "queries_tried": list(tried),
                           "pages_read": [_brief(p) for p in read]},
                          label="%s/q%d" % (label, number), check=lambda value: _query(value, allowed))
        calls += 1
        entry["query"] = query
        if query is None:
            continue
        tried += query["queries"]
        results, entry["searches"] = [], []
        for item in query["queries"]:
            found = sources.search(query["source"], item)
            entry["searches"].append({k: v for k, v in found.items() if k != "results"})
            for hit in found["results"]:
                if (hit["source"], hit["ref"]) not in seen | {(h["source"], h["ref"]) for h in results}:
                    results.append(hit)
        keyed = {"R%d" % (index + 1): hit for index, hit in enumerate(results)}
        entry["results"] = [{"key": key, "source": hit["source"], "title": hit["title"]} for key, hit in keyed.items()]
        if not keyed:
            continue
        left = RESEARCH_MAX_PAGES - used
        pick = roles.ask("research_pick", PICK_SYSTEM,
                         {**base, "results": entry["results"], "pages_left": left,
                          "pages_read": [_brief(p) for p in read]},
                         label="%s/p%d" % (label, number), check=lambda value: _pick(value, set(keyed)))
        calls += 1
        entry["pick"] = pick
        new = []
        for key in (pick or {"pages": []})["pages"][:left]:
            hit = keyed[key]
            seen.add((hit["source"], hit["ref"]))
            used += 1
            page = sources.fetch(hit["source"], hit["ref"])
            if "error" in page or "dropped" in page:
                new.append({"result": key, "title": page["title"], "skipped": page.get("error") or page["dropped"],
                            **({"archive": page["archive"]} if "archive" in page else {})})
                continue
            read.append({"key": "P%d" % (len(read) + 1), **page})
            new.append({"result": key, "page": read[-1]["key"], "archive": page["archive"], **_source(page)})
        entry["fetched"] = new
        if not any("page" in note for note in new):
            continue
        words = sorted({w for w in WORD.findall(" ".join([question, rule or ""] + tried).lower()) if len(w) >= 4})
        conclusion = roles.ask("research_conclude", CONCLUDE_SYSTEM[purpose],
                               {**base, "pages": [_shown(page, purpose, words) for page in read]},
                               label="%s/c%d" % (label, number),
                               check=lambda value: _conclusion(value, purpose, {page["key"] for page in read}))
        calls += 1
        entry["conclusion"] = conclusion
        if conclusion is None or conclusion["status"] == "continue":
            continue
        if conclusion["status"] == "none":
            reason = "researcher_none"
            break
        finding, void = _qualify(conclusion, purpose, read, subject)
        if finding is not None:
            break
        entry["void"] = void
    else:
        reason = "rounds_exhausted"
    found = {"purpose": purpose, "question": question, "rule": rule, "subject": subject,
             "status": "found" if finding is not None else "none", "reason": None if finding is not None else reason,
             "conclusion": None, "quotes": [], "calls": calls, "rounds": len(log), "log": log,
             "pages": [{k: page[k] for k in ("key", "source", "title", "revid", "archive")} for page in read]}
    return {**found, **(finding or {})}


# ----------------------------------------------------------------------------------- route-B request kinds (§7.2)
def material(found):
    """The material a family consumes from one qualified request record (None for an unqualified one), with its
    ``id`` (the digest of the material: two findings of the same material share it)."""
    if found.get("status") != "found":
        return None
    purpose = found["purpose"]
    if purpose == "table":
        table = found["table"]
        body = {"kind": "table", "caption": table["caption"], "rows": table["rows"], "archive": table["archive"],
                "index": table["index"], "source": found["source"]}
    elif purpose == "definition":
        body = {"kind": "definition", "quote": found["quote"], "archive": found["archive"], "source": found["source"]}
    elif purpose == "function":
        body = {"kind": "function", "name": found["subject"], "conclusion": found["conclusion"],
                "quotes": found["quotes"]}
    elif purpose == "parameter":
        body = {"kind": "parameter", "values": found["values"]}
    else:
        body = {"kind": "selection", "conclusion": found["conclusion"], "quotes": found["quotes"]}
    return {**body, "id": digest(body)}


class Researcher:
    """The research of one step on one bench (§7.2, §4.3): at most ``MAX_RESEARCH_REQUESTS`` requests, each screened
    by the frozen mechanical leakage checks of ``corpus`` (the bench's training pool, ``leakage.Corpus``) before it is
    dispatched; every request's record, dispatched or not, is kept in ``log`` in order. ``roles``: the GLM-5.3 roles
    of the unit attempt (the caller charges them to ``<chain>:...:examiner:research``)."""

    def __init__(self, roles, sources, corpus, *, bench, label, limit=MAX_RESEARCH_REQUESTS):
        require(bench in BENCHES and isinstance(corpus, leakage.Corpus) and type(label) is str and label,
                "A researcher of one bench, with its leakage corpus")
        require(type(limit) is int and 0 < limit <= MAX_RESEARCH_REQUESTS, "At most 24 requests per step and bench")
        self.roles, self.sources, self.corpus, self.bench, self.label, self.limit = (roles, sources, corpus, bench,
                                                                                   label, limit)
        self.log = []

    def dispatched(self):
        return sum(1 for entry in self.log if entry["status"] != "not_dispatched")

    def _send(self, kind, texts, **arguments):
        """Screen, count and dispatch one request; its record (with ``kind``) is appended to ``log``. Every string the
        researcher will see is screened before dispatch -- the question, the rule (topic) and each subject name, as
        well as ``texts`` (isolation review 8)."""
        require(kind in RESEARCH_REQUESTS, "Unknown research request kind")
        base = {"kind": kind, "question": arguments["question"], "rule": arguments.get("rule"),
                "subject": arguments.get("subject")}
        subject = arguments.get("subject")
        seen = list(texts) + [arguments["question"], arguments.get("rule")] + (
            list(subject) if isinstance(subject, (list, tuple)) else [subject])
        hits = [hit for hit in (leakage.mechanical(value, self.corpus) for value in seen if value) if hit]
        if hits:
            found = {**base, "status": "not_dispatched", "reason": "leak:" + hits[0]}
        elif self.dispatched() >= self.limit:
            found = {**base, "status": "not_dispatched", "reason": "requests_exhausted"}
        else:
            label = "%s/%s-%d" % (self.label, kind, len(self.log) + 1)
            found = {"kind": kind, **request(self.roles, self.sources, label=label, **arguments)}
        self.log.append(found)
        return found

    def family_material(self, *, concept, topic=None):
        """The material request of one family (OfficeQA: a numeric table on ``topic``; LiveMath: the definition or
        theorem ``concept``; SpreadsheetBench: the help quote of the function ``concept``)."""
        require(self.bench in MATERIAL_BENCHES, "Only OfficeQA, LiveMath and SpreadsheetBench have material")
        require(type(concept) is str and concept.strip(), "A material request names its concept")
        purpose = MATERIAL_PURPOSE[self.bench]
        if purpose == "function":
            return self._send("family_material", [concept], purpose=purpose, subject=concept,
                              question="%s\nFunction: %s" % (MATERIAL_REQUEST[self.bench], concept))
        question = "%s\n%s: %s" % (MATERIAL_REQUEST[self.bench], "Topic" if purpose == "table" else "Concept",
                                   concept)
        return self._send("family_material", [concept, topic], purpose=purpose, question=question, rule=topic)

    def parameter_choice(self, *, question, names, topic=None):
        """Values of the parameters ``names`` (1 to ``MAX_PARAMETERS`` names of at most ``MAX_PARAMETER_CHARS``
        characters), each with a verbatim quote (the caller drops out-of-range values)."""
        require(isinstance(names, (list, tuple)) and 1 <= len(names) <= MAX_PARAMETERS
                and all(type(n) is str and 0 < len(n.strip()) and len(n) <= MAX_PARAMETER_CHARS for n in names),
                "A parameter request names 1 to %d parameters of at most %d characters"
                % (MAX_PARAMETERS, MAX_PARAMETER_CHARS))
        return self._send("parameter_choice", [question, topic, *names], purpose="parameter", question=question,
                          rule=topic, subject=list(names))

    def selection_hint(self, *, question, topic=None):
        """A verified statement for an ALFWorld selection filter (selection validity only, §7.2)."""
        require(self.bench == "alfworld", "Selection hints are ALFWorld's")
        return self._send("selection_hint", [question, topic], purpose="verify", question=question, rule=topic)

    def summary(self):
        """The per-step research counts §7.2 asks every report to list: requests by kind and status, the reasons
        nothing was found, and the qualified findings."""
        counts = {}
        for entry in self.log:
            key = "%s:%s" % (entry["kind"], entry["status"])
            counts[key] = counts.get(key, 0) + 1
        reasons = {}
        for entry in self.log:
            if entry["status"] != "found":
                reasons[entry["reason"]] = reasons.get(entry["reason"], 0) + 1
        return {"requests": len(self.log), "dispatched": self.dispatched(), "counts": counts, "reasons": reasons,
                "findings": sum(1 for entry in self.log if entry["status"] == "found")}

    def record(self, *, evidence, step):
        """The sealed research record of the step (``fivebench-execskill-v1-research``)."""
        return record("research", evidence, {"step": step, "bench": self.bench, "label": self.label,
                                             "requests": self.log, "summary": self.summary()})


def split(findings, unit, *, evidence):
    """The sealed ``fivebench-execskill-v1-research-split`` record (§7.2): the qualified findings' materials grouped
    by material id (two findings of one material never part), the groups ordered by sha256 of the seed tag
    ``execskill-v1:research-split:<unit>`` and the id, then dealt alternately to G_self and G_acc. Each half lists its
    materials; ``g_self_sha256``/``g_acc_sha256`` are their digests."""
    tag = research_split_tag(unit)
    materials = {}
    for found in findings:
        value = material(found)
        require(value is not None, "Only qualified findings are split")
        materials.setdefault(value["id"], value)
    order = sorted(materials, key=lambda key: hashlib.sha256(("%s:%s" % (tag, key)).encode()).hexdigest())
    halves = {"g_self": [materials[key] for key in order[0::2]], "g_acc": [materials[key] for key in order[1::2]]}
    return record("research-split", evidence, {
        "unit": unit, "tag": tag, **halves,
        "g_self_sha256": digest(halves["g_self"]), "g_acc_sha256": digest(halves["g_acc"])})
