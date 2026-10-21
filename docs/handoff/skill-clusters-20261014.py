"""Zero-call: how do the learned Skill texts of the three benchmarks cluster? Rule-level (bullet) similarity between
every pair of Skills, agglomerative clustering, and the share of a Skill's rules that another Skill of the same /
another benchmark also carries. Reads sealed learned.json files and the instruction texts; no call."""
import glob, hashlib, json, math, os, re, collections
TEXTS = {}
def add(name, text):
    if text and text.strip():
        TEXTS[name] = text
for path in sorted(glob.glob("/root/fivebench-g-2026101[34]-*/learned.json")):
    stage = os.path.basename(os.path.dirname(path))
    L = json.load(open(path))
    if L.get("status") == "completed" and L.get("action") == "selected_update" and L.get("skill"):
        short = stage.replace("fivebench-g-2026101", "").replace("3-", "").replace("4-", "")
        add(short, L["skill"])
for name, path in (("searchqa:old_v9", "/root/fivebench-g-20261006-searchqa-chain-skillopt-v9c/learned.json"),
                   ("searchqa:old_v10", "/root/fivebench-g-20261006-searchqa-chain-rubric_research-e/learned.json")):
    try:
        L = json.load(open(path)); add(name, L["skill"])
    except Exception as exc:
        print("skip", name, type(exc).__name__)
for name, path in (("officeqa:bzero", "/root/fivebench-g-20261013-officeqa-bzero/skill.md"), ("livemath:bzero", "/root/fivebench-g-20261013-livemath-bzero/skill.md"),
                   ("searchqa:bzero", "/root/fivebench-g-20261012-searchqa-bzero2/skill.md")):
    try:
        add(name, open(path).read())
    except Exception as exc:
        print("skip", name, type(exc).__name__)
for name in ("e41s0", "e41s2", "z41s0", "z41s2"):
    p = "/root/fivebench-g-20261014-livemath-candidates/%s.md" % name
    if os.path.exists(p): add("livemath:cand:" + name, open(p).read())
print("skills:", len(TEXTS))
def rules(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(?:[-*•]|\d+[.)])\s+", line) and len(line) > 20:
            out.append(re.sub(r"^(?:[-*•]|\d+[.)])\s+", "", line))
    return out
STOP = set("the a an of to in and or for is are be with that this it as on by not from at if when into which".split())
def tokens(s):
    return [w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in STOP]
def bench(name):
    for b in ("searchqa", "officeqa", "livemath"):
        if b in name: return b
    return "other"
names = sorted(TEXTS)
docs = {n: collections.Counter(tokens(TEXTS[n])) for n in names}
df = collections.Counter()
for n in names:
    for w in docs[n]: df[w] += 1
N = len(names)
def vec(c):
    v = {w: (1 + math.log(f)) * math.log(N / df[w]) for w, f in c.items() if df[w] < N}
    norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return {w: x / norm for w, x in v.items()}
V = {n: vec(docs[n]) for n in names}
def cos(a, b):
    return sum(V[a].get(w, 0) * x for w, x in V[b].items())
# agglomerative (average linkage) into 3 clusters
clusters = [[n] for n in names]
def link(c1, c2):
    return sum(cos(a, b) for a in c1 for b in c2) / (len(c1) * len(c2))
while len(clusters) > 3:
    best = max(((link(clusters[i], clusters[j]), i, j) for i in range(len(clusters)) for j in range(i + 1, len(clusters))))
    _, i, j = best
    clusters[i] = clusters[i] + clusters[j]; del clusters[j]
print("\nTF-IDF cosine, average-linkage clusters (3):")
for c in clusters:
    print("  ", collections.Counter(bench(n) for n in c), "<-", sorted(c))
# rule-level overlap: a rule "shared" when its token Jaccard with some rule of the other Skill >= 0.5
R = {n: [set(tokens(r)) for r in rules(TEXTS[n])] for n in names}
def shared(a, b):
    ra, rb = R[a], R[b]
    if not ra or not rb: return None
    hit = 0
    for x in ra:
        if any(len(x & y) / max(1, len(x | y)) >= 0.5 for y in rb): hit += 1
    return hit / len(ra)
within, across = [], []
for a in names:
    for b in names:
        if a == b or shared(a, b) is None: continue
        (within if bench(a) == bench(b) else across).append(shared(a, b))
print("\nrule overlap (share of a Skill's rules found in another Skill, token Jaccard >= 0.5):")
print("   same benchmark: mean %.2f over %d pairs | other benchmark: mean %.2f over %d pairs" % (sum(within) / len(within), len(within), sum(across) / len(across), len(across)))
print("   rules per Skill:", {n: len(R[n]) for n in names})
# within-benchmark: how much of each learned Skill is its own instruction (bzero) vs new
for b in ("searchqa", "officeqa", "livemath"):
    base = b + ":bzero"
    if base not in TEXTS: continue
    for n in names:
        if bench(n) == b and n != base and "bzero" not in n:
            print("   %-28s rules %2d | share of rules also in %s: %s" % (n, len(R[n]), base, None if shared(n, base) is None else round(shared(n, base), 2)))
