"""Research (registration §7; §4 step 5b; the material of §8).

Version 6 narrows research to two jobs, both done after the stage's training results are known:

1. a proposed rule's research questions (§4 step 5b): each question is one request ending in a conclusion backed by
   verbatim quotes, or in "no qualified finding"; with at least one qualified finding the analyst rewrites the rule once
   or keeps it (``rewrite``);
2. the real public material of forward items (§8, ``material``): a numeric data table of an English Wikipedia page
   (OfficeQA style) or a verbatim Wikipedia definition or theorem (LiveMath style).

The sources are frozen (§7): the English Wikipedia API at fixed parameters -- the final title, the revision id and the
redirects followed are kept; disambiguation pages and titles containing "Jeopardy" (SearchQA's source) are dropped, also
after a redirect -- and a pre-launch archive of documents pinned by SHA-256 (Python 3.11 and openpyxl documentation
pages, v2: the LibreOffice Calc 25.2 help pages, and the five public task cards). Nothing else is accessed. Every search result list and every page body is archived
write-once under the unit's store, named by its hash, before it is used.

A request is at most 3 rounds of at most 3 queries, at most 3 pages read in all and at most 8 model calls -- an invalid
reply consumes its call and is never retried. A round (query, pick, conclude) starts only while its three calls and a
page still fit. A quote must occur verbatim (whitespace normalized) in the archived text of the page it names, else the
finding is void and the request goes on. The researcher sees the rule text, the question or the material request, and
the pages it reads -- never a benchmark item (the caller checks rule texts and questions mechanically before dispatch,
§4 step 5b). A stop of the run raised by a model call propagates; a source that fails is recorded as a failed fetch.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from html.parser import HTMLParser

import httpx

from skillopt.continual_eval.core import require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from .protocol import (
    ARCHIVE_MIN_WORD_SHARE,
    ORDER,
    RESEARCH_MAX_CALLS,
    RESEARCH_MAX_PAGES,
    RESEARCH_MAX_QUERIES,
    RESEARCH_MAX_ROUNDS,
)
from .roles import Invalid, fields, items, text
from .skill import Rule

# §7: the frozen sources (to be recorded in the manifest).
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "coevo5-research/2 (fivebench-coevolution-v2)"
SEARCH_LIMIT = 5  # results of one Wikipedia query
ARCHIVE_LIMIT = 5  # results of one archive query
EXCLUDED_TITLE = "jeopardy"  # SearchQA's source: no page or result whose title contains it
# §7, §8: the shapes of a request's replies and of the material (to be moved to protocol.py).
MAX_QUERY_CHARS = 100
MAX_CONCLUSION_CHARS = 1000
MAX_QUOTES, MAX_QUOTE_CHARS = 3, 500
MAX_DEFINITION_CHARS = 1500
TABLE_ROWS, TABLE_COLUMNS = (2, 60), (2, 15)  # an eligible table: rows, columns; and at least one numeric cell
EXCERPT_CHARS = 8000  # page text shown per page (quotes are checked against the whole archived page)
LEAD_CHARS = 2000  # of an excerpt, at most this (and a quarter) for the page's opening lines; then the richest lines
PREVIEW_TABLES, PREVIEW_ROWS, PREVIEW_CELL_CHARS = 10, 6, 60  # what a table request is shown of each page
CALLS_PER_ROUND = 3  # query, pick, conclude

PURPOSES = ("verify", "table", "definition")
STYLES = {"officeqa": "table", "livemath": "definition"}  # forward style -> material request

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
}
REWRITE_SYSTEM = (
    "You revise one guidance rule for a language model that solves tasks. You receive the rule and research findings: "
    "a question about the rule, its conclusion and verbatim quotes from Wikipedia or documentation. Rewrite the rule "
    "so that it agrees with the findings, or return it unchanged if it already does. Keep what the rule is about and "
    "when it applies; do not add facts about particular questions or answers. The rule is one block of plain text of "
    "at most 600 characters, without blank lines and without headings.\n\n"
    "Reply with only a JSON object: {\"text\": \"the rule\"}.")
MATERIAL_REQUEST = {
    "officeqa": "Find an English Wikipedia article on the topic of the rule below that contains a table of numbers "
                "(for example statistics, measurements, finances or results by year) from which questions requiring "
                "a calculation can be written.",
    "livemath": "Find an English Wikipedia article on the topic of the rule below that states a mathematical "
                "definition or theorem from which a question with a numerical answer can be computed.",
}

PROXY = re.compile(r"https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/?")  # explicit, without credentials
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
WORD = re.compile(r"[a-z0-9]+")
NUMBER = re.compile(r"[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
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
    """The English Wikipedia API at the frozen parameters (§7). ``proxy``: an explicit proxy without credentials (the
    environment's proxy settings are never read); ``transport``: for tests."""

    def __init__(self, *, proxy=None, transport=None, timeout=60):
        require(proxy is None or (type(proxy) is str and PROXY.fullmatch(proxy) is not None),
                "A proxy is an explicit http(s) host without credentials")
        options = {"transport": transport} if transport is not None else ({"proxy": proxy} if proxy else {})
        self.client = httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False,
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
    """A table OfficeQA-style items can be written from (§8): 2-60 rows, 2-15 columns, a numeric cell."""
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


def _excluded(title):
    return EXCLUDED_TITLE in title.lower()


# ------------------------------------------------------------------------------------------------------ sources
class Archive:
    """The pre-launch archive (§7): ``root/index.json`` = {name: {"sha256", "title"}} and the files it names, each
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
        at least one), ranked by the number of distinct words held, then by their occurrences, then by name (v2 §8; v1
        required every word)."""
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
    else:  # a material request searches Wikipedia only, whatever the reply names
        fields(value, ["queries"], ["source"])
    listed = items(value["queries"], limit=RESEARCH_MAX_QUERIES, low=1)
    queries = [text(query, limit=MAX_QUERY_CHARS).strip() for query in listed]
    return {"queries": queries, "source": value["source"] if len(allowed) > 1 else allowed[0]}


def _pick(value, keys):
    pages = items(fields(value, ["pages"])["pages"], limit=len(keys))
    if not all(type(key) is str and key in keys for key in pages) or len(set(pages)) != len(pages):
        raise Invalid("pages")
    return {"pages": pages}


def _conclusion(value, purpose, keys):
    status = value.get("status") if type(value) is dict else None
    if status in ("continue", "none"):
        return fields(value, ["status"])
    if status != "found":
        raise Invalid("status")
    if purpose == "verify":
        fields(value, ["status", "conclusion", "quotes"])
        quotes = items(value["quotes"], limit=MAX_QUOTES, low=1)
        for quote in quotes:
            fields(quote, ["page", "text"])
            text(quote["text"], limit=MAX_QUOTE_CHARS)
        conclusion = text(value["conclusion"], limit=MAX_CONCLUSION_CHARS)
        pages = [quote["page"] for quote in quotes]
        found = {"status": status, "conclusion": conclusion, "quotes": [dict(q) for q in quotes]}
    elif purpose == "table":
        fields(value, ["status", "page", "table"])
        if type(value["table"]) is not int or value["table"] < 0:
            raise Invalid("table")
        pages, found = [value["page"]], {"status": status, "page": value["page"], "table": value["table"]}
    else:
        fields(value, ["status", "page", "quote"])
        pages = [value["page"]]
        found = {"status": status, "page": value["page"], "quote": text(value["quote"], limit=MAX_DEFINITION_CHARS)}
    if not all(type(page) is str and page in keys for page in pages):
        raise Invalid("page")
    return found


def _source(page):
    return {"title": page["title"], "revid": page["revid"]}


def _qualify(found, purpose, read):
    """(the finding, None), or (None, why the finding is void)."""
    pages = {page["key"]: page for page in read}
    if purpose == "verify":
        if not all(verbatim(q["text"], pages[q["page"]]["text"]) for q in found["quotes"]):
            return None, "quote_not_verbatim"
        quotes = [{"page": q["page"], "archive": pages[q["page"]]["archive"], **_source(pages[q["page"]]),
                   "text": q["text"]} for q in found["quotes"]]
        return {"conclusion": found["conclusion"], "quotes": quotes}, None
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


def request(roles, sources, *, purpose, question, label, rule=None):
    """One research request (§7). ``purpose``: "verify" (a research question about the rule ``rule``; Wikipedia or
    the archive), "table" or "definition" (forward-item material; Wikipedia only). Returns {"purpose", "question",
    "rule", "status": "found" | "none", "reason", "conclusion", "quotes", "pages", "calls", "rounds", "log"}, with
    "table" and "source" for a table, "quote", "page", "archive" and "source" for a definition."""
    require(purpose in PURPOSES and type(question) is str and question.strip(), "Invalid research request")
    require(type(label) is str and label and (rule is None or (type(rule) is str and rule.strip())),
            "Invalid research request")
    allowed = ("wikipedia", "archive") if purpose == "verify" and sources.archive is not None else ("wikipedia",)
    base = {"purpose": purpose, "request": question, "rule": rule}
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
        finding, void = _qualify(conclusion, purpose, read)
        if finding is not None:
            break
        entry["void"] = void
    else:
        reason = "rounds_exhausted"
    record = {"purpose": purpose, "question": question, "rule": rule,
              "status": "found" if finding is not None else "none", "reason": None if finding is not None else reason,
              "conclusion": None, "quotes": [], "calls": calls, "rounds": len(log), "log": log,
              "pages": [{k: page[k] for k in ("key", "source", "title", "revid", "archive")} for page in read]}
    return {**record, **(finding or {})}


def material(roles, sources, *, rule_text, style, label, log=None):
    """The real public material of one forward generation round (§8): an eligible Wikipedia table (OfficeQA style)
    or a verbatim Wikipedia definition or theorem (LiveMath style) on the topic of the rule; None when the request
    found nothing. ``log``: a list that receives the request's record either way."""
    require(style in STYLES, "Unknown forward style")
    found = request(roles, sources, purpose=STYLES[style], question=MATERIAL_REQUEST[style], rule=rule_text,
                    label=label)
    if log is not None:
        log.append(found)
    if found["status"] != "found":
        return None
    if style == "officeqa":
        table = {"caption": found["table"]["caption"], "rows": found["table"]["rows"]}
        return {"style": style, "source": found["source"], "page": found["table"]["archive"], "table": table,
                "text": render_table(table)}
    return {"style": style, "source": found["source"], "page": found["archive"], "quote": found["quote"],
            "text": found["quote"]}


def rewrite(roles, rule_text, findings, *, label):
    """§4 step 5b: one rewrite call, never retried, given the qualified findings of the rule's questions. Returns
    (text, "rewritten" | "kept" | "rewrite_failed"); a failed rewrite -- an invalid reply, or a text outside the rule
    format of §3 -- keeps the original text."""
    require(findings and all(f.get("status") == "found" and f.get("purpose") == "verify" for f in findings),
            "A rewrite needs qualified findings")
    payload = {"rule": rule_text, "findings": [{"question": f["question"], "conclusion": f["conclusion"],
                                                 "quotes": [q["text"] for q in f["quotes"]]} for f in findings]}
    value = roles.ask("research_rewrite", REWRITE_SYSTEM, payload, label=label,
                      check=lambda reply: {"text": fields(reply, ["text"])["text"]})
    if value is None or type(value["text"]) is not str:
        return rule_text, "rewrite_failed"
    try:
        Rule("rewrite-check", value["text"], ORDER[0])  # the rule format of §3: 1-600 characters, one block, ...
    except ValueError:
        return rule_text, "rewrite_failed"
    return (rule_text, "kept") if value["text"] == rule_text else (value["text"], "rewritten")
