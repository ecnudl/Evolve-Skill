"""Heuristic structural tags of an OfficeQA-style item and of a piece of Skill guidance (zero calls).

Item tags come from the question (operation family, rounding requirement, question shape), the reference answer
(answer form; read for training / generated items only -- callers must not pass a held-out or test answer) and the
context (pages, bulletin issues). Guidance tags map Skill text onto the same vocabulary so that one Skill edit can be
measured on the items it is about. The patterns are a documented heuristic, not a parser: precision is what the unit
tests pin, and every consumer reports which tags it used.
"""
from __future__ import annotations

import re

VERSION = "skill-features-tagger-v1"

# Operation families, most specific first. Matching consumes the matched text, so "geometric mean" yields geomean and
# not also mean, and "percent change" yields percent_change and not also difference. The first family found is the
# item's primary operation; an item with none is a lookup.
OPERATIONS = (
    ("cv", r"coefficient\s+of\s+variation|volatility\s+index"),
    ("stdev", r"standard\s+deviation|\bstd\.?\s*dev\w*|\bvariance\b"),
    ("geomean", r"geometric\s+mean"),
    # before cagr: "continuously compounded annual growth rate" is a logarithmic rate, not a CAGR
    ("log_growth", r"contin(?:u)?ous(?:ly)?[\s-]+compound\w*(?:\s+average)?(?:\s+annual)?(?:\s+(?:growth\s+)?rate)?|"
                   r"contin(?:u)?ous\s+rate(?:\s+of\s+change)?|logarithmic\s+(?:growth|change|return)(?:\s+rate)?|"
                   r"log\s+(?:return|growth)(?:\s+rate)?"),
    ("cagr", r"compound(?:ed)?\s+annual(?:\s+growth)?(?:\s+rate)?|\bcagr\b|annuali[sz]ed\s+(?:growth\s+rate|growth|rate|"
             r"return)"),
    ("correlation", r"correlation"),
    ("trend", r"regression|linear\s+trend|\bslope\b|forecast\w*|project(?:ed|ion)|smoothing|extrapolat\w*|"
              r"moving\s+average|grow\s+at\s+the\s+same"),
    ("order_stat", r"percentile|quantile|quartile|trimmed\s+mean|\bmedian\b|z-score|value-at-risk|\bvar\b|theil|gini|"
                   r"hazen|outlier"),
    ("log", r"natural\s+log\w*|logarithm\w*|\bln\b"),
    # the answer is a period (a date, month or year), whatever is compared to find it
    ("which_period", r"\b(?:in|on)\s+which\s+(?:[\w-]+\s+){0,4}(?:year|month|quarter|week|date|day)\b|\bwhen\s+did\b|"
                     r"what\s+(?:was\s+the\s+)?(?:year|month|date)\s+(?:and\s+year\s+)?(?:did|was|that|when|in\s+which)|"
                     r"around\s+what\s+year"),
    # an operation (a noun), not the name of a printed series ("average yields", "yearly average exchange rate") and
    # not the verb ("can mean", "typically means")
    ("mean", r"\barithmetic\s+mean\b|\bmean\s+(?:of|value|level)\b|\baverage\s+of\b|"
             r"\baverage\s+(?:value|level|amount|balance)\b|\b(?:a|the|its)\s+mean\b(?!\s+(?:that|the)\b)|"
             r"\bthe\s+average\b(?!\s+(?:yields?|rates?|prices?|exchange|annual|yearly))|\bmeans?\s+(?:and|or)\s+|"
             r"\bmean(?=\s*[,;)/])"),  # "mean" in a list of operations: "sum, mean, ..." / "mean/std deviation"
    ("pp_change", r"percentage\s+points?"),
    ("percent_change", r"percent(?:age)?\s+(?:change|increase|decrease|growth|difference)|growth\s+rate|"
                       r"rate\s+of\s+(?:change|growth)|%\s*change|\bqoq\b|\byoy\b"),
    ("share", r"\bshare\b|percent\s+of|percentage\s+of|proportion|fraction\s+of|\bratio\b"),
    ("sum", r"\bsum\b|\btotal\s+of\b|combined|in\s+total|aggregate"),
    ("difference", r"difference|\bgap\b|change\s+in|increase\s+in|decrease\s+in|net\s+change|by\s+how\s+(?:much|many)|"
                   r"\bspread\b|\bcompar(?:e|ing|ison)\b"),
    ("extreme", r"\b(?:highest|lowest|largest|smallest|maximum|minimum|peak|trough)\b|local\s+(?:max|min)\w*"),
    ("count", r"how\s+many|number\s+of\s+times"),
)
_OPERATIONS = tuple((name, re.compile(pattern, re.I)) for name, pattern in OPERATIONS)
OPERATION_NAMES = tuple(name for name, _ in OPERATIONS) + ("lookup",)

QUESTION_SHAPES = (
    # "Figure 3" / "Figure TF-G" name a chart; "this figure" names a number
    ("q:chart", r"\b(?:charts?|exhibits?|graphs?|plots?|plotted)\b|(?-i:\b[Ff]igure\s+[A-Z0-9][\w.-]*)"),
    ("q:indirect_date", r"\bmid-[a-z]+|\b(?:first|second|third|fourth|last)\s+(?:monday|tuesday|wednesday|thursday|friday|"
                        r"week)\b|week\s+end(?:ing|ed)|issue\s+date"),
    ("q:series", r"\bbetween\b.{1,80}\band\b|\bfrom\b.{1,60}\b(?:to|through)\b|\bmonthly\b|\bquarterly\b|"
                 r"\beach\s+(?:year|month|quarter)|\b(?:1[89]|20)\d\d\s*(?:-|–|to|through)\s*(?:1[89]|20)\d\d"),
    ("q:date_format", r"date\s+format|long\s+date"),
    ("q:unit_stated", r"\bin\s+(?:millions|billions|thousands|trillions)\b|\(in\s+(?:millions|billions|thousands)|"
                      r"(?:millions|billions|thousands)\s+of\s+(?:nominal\s+)?dollars"),
    ("q:multi_step", r"\bthen\b|\bfinally\b|in\s+that\s+(?:corresponding\s+)?(?:\w+\s+){0,2}(?:month|year)|"
                     r"using\s+(?:that|this)\s+(?:value|result|figure)|\bconvert\w*\b"),
    # the question asks for several values (read from its wording, never from a reference answer)
    ("q:multi_value", r"square\s+brackets|comma[\s-]separated|both\s+values|\b(?:two|three)\s+values\b|"
                      r"\[\s*[a-z\w]+\s*,|\band\s+(?:what|compute|calculate|report|determine)\b"),
)
_QUESTION_SHAPES = tuple((name, re.compile(pattern, re.I | re.S)) for name, pattern in QUESTION_SHAPES)

# Context (or question) properties of an item that guidance can be about but no question pattern reveals.
_BOND_PRICE_CONTEXT = re.compile(r"32nds|price\s+decimals", re.I)
_BOND_PRICE_QUESTION = re.compile(r"\b(?:bid|asked|bond\s+prices?|quotations?)\b", re.I)

# Guidance-only tags: Skill text that speaks about a context or answer property rather than an operation.
GUIDANCE = (
    ("ctx:multi_vintage", r"most\s+recent\s+(?:issue|page|edition|vintage)|revis(?:ion|ions|ed)\b|vintage|reprinted|"
                          r"(?:several|multiple|different)\s+(?:supplied\s+)?(?:bulletin\s+)?(?:issues|editions)"),
    ("ctx:multi_page", r"multi-page|(?:several|multiple|different|two)\s+(?:supplied\s+)?pages|across\s+pages"),
    ("q:chart", r"\bcharts?\b|\bexhibits?\b|\bgraphs?\b|\bplots?\b"),  # not "figure": Skill text uses it for "number"
    ("q:indirect_date", r"mid-[a-z]+|third\s+thursday|week\s+end(?:ing|ed)|indirect\s+date|date\s+language"),
    ("q:date_format", r"date\s+format|long\s+date|spelled-out\s+month"),
    ("ctx:bond_price", r"32nds|fractional\s+notation|market[\s-]quotation|\bbid\b"),
    ("ans:bracketed", r"bracket|multi-part|several\s+quantities|comma-separated|multiple\s+values"),
    ("round:any", r"decimal\s+places?|nearest\s+(?:whole|tenth|hundredth|thousandth)|\bround(?:ing|ed)?\b|precision"),
    ("q:unit_stated", r"millions\s+of\s+dollars|\bbillions?\b|\bthousands\b|scaling|magnitude|\bunits?\s+(?:and|or)\s+scal"),
)
_GUIDANCE = tuple((name, re.compile(pattern, re.I)) for name, pattern in GUIDANCE)

MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december")
_WORD_DECIMALS = {"whole": 0, "integer": 0, "tenth": 1, "tenths": 1, "hundredth": 2, "hundredths": 2,
                  "thousandth": 3, "thousandths": 3, "ten-thousandth": 4, "ten-thousandths": 4}
_NUMBER_WORDS = {"zero": 0, "no": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_PAGE = re.compile(r"###\s+(treasury_bulletin_(\d{4})_(\d{2}))\.txt\s+page\s+(\d+)", re.I)
LENGTH_BUCKETS = ((3000, "short"), (8000, "medium"))


def operations(text):
    """The operation families named in ``text`` (in OPERATIONS order); an empty tuple when none is named."""
    remaining, found = text, []
    for name, pattern in _OPERATIONS:
        if pattern.search(remaining):
            found.append(name)
            remaining = pattern.sub(" \x00 ", remaining)  # a separator: consumed text never rejoins its neighbours
    return tuple(found)


def answer_form(answer):
    a = answer.strip()
    if a.startswith("[") and a.endswith("]"):
        return "bracketed"
    if re.fullmatch(r"(?:%s)\s+\d{1,2},\s*\d{4}" % MONTHS, a, re.I):
        return "date"
    if re.fullmatch(r"(?:%s)\s+\d{4}" % MONTHS, a, re.I):
        return "month_year"
    if re.fullmatch(r"(?:1[6-9]|20|21)\d\d", a):
        return "year"
    if a.endswith("%"):
        return "percent"
    if a.startswith("$") or a.startswith("-$") or re.search(r"\b(?:thousand|million|billion|trillion)\b", a, re.I):
        return "currency_or_scaled"
    if re.fullmatch(r"-?[\d,]*\.\d+", a):
        return "decimal"
    if re.fullmatch(r"-?\d[\d,]*", a):
        return "integer"
    return "text"


def rounding(question):
    """The number of decimals the question requires, "unspecified" when it asks for rounding without saying how, or
    None when it says nothing about rounding."""
    q = question.lower()
    match = re.search(r"nearest\s+(whole|integer|ten-thousandths?|tenths?|hundredths?|thousandths?)", q)
    if match:
        return _WORD_DECIMALS[match.group(1)]
    match = re.search(r"\b(\d|zero|no|one|two|three|four|five)\s+decimal\s+places?", q)
    if match:
        value = match.group(1)
        return int(value) if value.isdigit() else _NUMBER_WORDS[value]
    match = re.search(r"\bround(?:ed|ing)?\b[^.?]{0,40}?\b(\d)\s+decimal", q)
    if match:
        return int(match.group(1))
    if re.search(r"\bround(?:ed|ing)?\b|\bdecimal\s+places?\b", q):
        return "unspecified"
    return None


def context_shape(context):
    pages = _PAGE.findall(context or "")
    issues = sorted({p[0] for p in pages})
    chars = len(context or "")
    bucket = next((name for limit, name in LENGTH_BUCKETS if chars < limit), "long")
    return {"pages": len(pages), "issues": len(issues), "years": sorted({p[1] for p in pages}), "context_chars": chars,
            "length": bucket}


def tag_item(question, answer=None, context=None):
    """The structural record of one item. ``answer`` may be None (an item whose reference must not be read): its
    answer form is then "unknown"."""
    ops = operations(question)
    primary = ops[0] if ops else "lookup"
    form = answer_form(answer) if isinstance(answer, str) else "unknown"
    if form == "year" and "which_period" not in ops:
        form = "integer"  # a four-digit amount ("2000") is a year only when the question asks for a period
    decimals = rounding(question)
    shape = context_shape(context)
    tags = {"op:" + op for op in ops} or {"op:lookup"}
    tags.add("ans:" + form)
    tags.add("round:none" if decimals is None else "round:%s" % decimals)
    tags.update(name for name, pattern in _QUESTION_SHAPES if pattern.search(question))
    if _BOND_PRICE_CONTEXT.search(context or "") or _BOND_PRICE_QUESTION.search(question):
        tags.add("ctx:bond_price")
    if shape["pages"] >= 2:
        tags.add("ctx:multi_page")
    if shape["issues"] >= 2:
        tags.add("ctx:multi_vintage")
    tags.add("ctx:" + shape["length"])
    return {"version": VERSION, "tags": sorted(tags), "primary_op": primary, "operations": list(ops),
            "answer_form": form, "rounding": decimals, **{k: shape[k] for k in ("pages", "issues", "context_chars")}}


def guidance_tags(text):
    """The tags a piece of Skill guidance is about: the operation families it names and the guidance-only properties.
    Empty when the text names none (generic advice: it is about every item)."""
    tags = {"op:" + op for op in operations(text)}
    tags.update(name for name, pattern in _GUIDANCE if pattern.search(text))
    return sorted(tags)


def matches(item_tags, edit_tags):
    """Whether an item belongs to an edit's trigger subset: the edit names no tag (generic: every item), or it shares
    a tag with the item; "round:any" matches an item with any rounding requirement."""
    if not edit_tags:
        return True
    item = set(item_tags)
    for tag in edit_tags:
        if tag == "round:any":
            if any(t.startswith("round:") and t != "round:none" for t in item):
                return True
        elif tag in item:
            return True
    return False
