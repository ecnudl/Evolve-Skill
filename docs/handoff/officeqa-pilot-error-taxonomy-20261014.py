"""Zero-call error taxonomy of the OfficeQA headroom pilot (74 training + validation items, four arms): what the
last answer tag said against the reference. Reads the pilot's sealed outcomes and cached replies only."""
import collections, json, re, string, sys
B = "/root/fivebench-g-20261013-officeqa-pilot-a"
items = {i["id"]: i for i in json.load(open(B + "/items.json"))["items"]}

def norm(text):
    text = text.lower().strip().replace(",", "")
    text = "".join(ch for ch in text if ch not in string.punctuation or ch in "0123456789.-" or ch == "%")
    text = re.sub(r"\b(million|millions|billion|billions|dollars|dollar|nominal)\b", " ", text)
    return " ".join(text.split())

def number(text):
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)%?", norm(text))
    return float(m.group(1)) if m else None

def kind(said, gold):
    if said is None:
        return "no_answer_tag"
    a, b = norm(said), norm(gold)
    if a == b:
        return "correct"
    if a.replace("%", "") == b.replace("%", ""):
        return "percent_sign_only"
    x, y = number(said), number(gold)
    if x is None or y is None:
        if y is not None:
            return "reference_numeric_answer_not_a_plain_number"
        return "text_or_list_mismatch"
    if y != 0 and x != 0:
        r = abs(x / y)
        for p in (3, 6, 9, 2, -2, -3, -6, -9):
            if abs(r / 10 ** p - 1) < 5e-3:
                return "scale_or_unit (x10^%d)" % p
        if abs(r - 1) < 5e-4:
            return "same_value_other_precision_or_last_digit (<0.05%)"
        if abs(r - 1) < 2e-2:
            return "near_miss (<2%)"
        if x == -y:
            return "sign"
    return "different_number"

rows = collections.defaultdict(collections.Counter)
examples = collections.defaultdict(list)
for arm in ("empty", "bzero", "human", "paper"):
    for uid, item in sorted(items.items()):
        o = json.load(open("%s/calls/%s/%s.json" % (B, arm, uid)))
        if o["status"] == "unknown":
            rows[arm]["unknown"] += 1; continue
        reply = json.load(open("%s/api/calls/%s.json" % (B, o["request_hashes"][-1])))
        text = reply.get("response") or ""
        tags = re.findall(r"<answer>(.*?)</answer>", text, flags=re.S)
        said = tags[-1].strip() if tags else None
        k = kind(said, item["private"]["answer"])
        if (k == "correct") != (o["status"] == "pass"):
            k += " [scorer:%s]" % o["status"]
        rows[arm][k] += 1
        if arm == "bzero" and k != "correct" and len(examples[k]) < 3:
            examples[k].append((uid, item["meta"]["difficulty"], (said or "")[:40], item["private"]["answer"][:40]))
kinds = sorted({k for c in rows.values() for k in c}, key=lambda k: -rows["bzero"][k])
print("%-58s %6s %6s %6s %6s" % ("last answer tag vs reference (74 items)", "empty", "bzero", "human", "paper"))
for k in kinds:
    print("%-58s %6d %6d %6d %6d" % (k, rows["empty"][k], rows["bzero"][k], rows["human"][k], rows["paper"][k]))
print()
for k, ex in examples.items():
    for uid, level, said, gold in ex:
        print("  bzero %-52s %s %-5s said %-28r reference %r" % (k, uid, level, said, gold))
