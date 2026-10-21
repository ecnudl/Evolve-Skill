"""The sectioned Skill (registration §3).

One section per benchmark in the chain order, each opened by its fixed applicability line; there is no shared section.
A benchmark section may start with a seed text (chain I: the task-card instruction); rules are append-only bullets. A
rule sits at the end of its home section (the bench whose stage learned it) and, at a similar placement, the same text
also at the end of the sections of its similar targets (§1.1, §5.3). An empty Skill renders as "" so the solver prompt
is exactly the No-Skill prompt. v2 §2: a scaffolded Skill (chain E's start) renders every section's heading and
applicability line from stage 0, also while a section holds nothing else.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from skillopt.continual_eval.core import require

from .protocol import APPLIES_WHEN, MAX_RULE_CHARS, MAX_SKILL_BYTES, ORDER, TITLES, similar_targets

RULE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
HEADING = re.compile(r"^(#{1,2})(?=\s)")


@dataclass(frozen=True)
class Rule:
    id: str
    text: str
    home: str
    also: tuple = ()  # a similar placement: every checkable similar target of the stage, in chain order

    def __post_init__(self):
        require(type(self.id) is str and RULE_ID.fullmatch(self.id) is not None, "Invalid rule id")
        require(self.home in ORDER, "Unknown rule placement")
        require(type(self.also) is tuple and self.also in ((), sum(similar_targets(self.home), ())),
                "A similar placement names every checkable similar target of the rule's stage, in chain order")
        require(type(self.text) is str and self.text == self.text.strip() and 0 < len(self.text) <= MAX_RULE_CHARS,
                "A rule is 1-%d characters without surrounding whitespace" % MAX_RULE_CHARS)
        require("\r" not in self.text, "Rule line endings are \\n")
        lines = self.text.split("\n")
        require(all(line.strip() for line in lines), "A rule is one block (no blank lines)")
        require(not any(line.lstrip().startswith("#") for line in lines), "A rule cannot open a heading")

    @property
    def sections(self):
        return (self.home,) + self.also

    def to_json(self):
        return {"id": self.id, "text": self.text, "home": self.home, "also": list(self.also)}


def seed_text(text):
    """A seed keeps its Markdown, but level-1 and level-2 headings become level 3 and 4 so that they cannot close the
    benchmark section that holds them. Line endings are normalised to "\\n"."""
    require(type(text) is str and text.strip(), "A seed is nonblank text")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    return "\n".join(HEADING.sub(lambda m: "##" + m.group(1), line) for line in lines)


def _bullet(text):
    first, *rest = text.split("\n")
    return "\n".join(["- " + first] + ["  " + line for line in rest])


def _render(seeds, rules, scaffold=False):
    seeds = dict(seeds)
    blocks = []
    for bench in ORDER:
        placed = [r for r in rules if bench in r.sections]
        seed = seeds.get(bench, "")
        if not placed and not seed and not scaffold:
            continue
        head = "## " + TITLES[bench] + "\n" + APPLIES_WHEN[bench]
        body = ([seed] if seed else []) + (["\n".join(_bullet(r.text) for r in placed)] if placed else [])
        blocks.append(head + "\n\n" + "\n\n".join(body) if body else head)
    return "\n\n".join(blocks)


@dataclass(frozen=True)
class Skill:
    seeds: tuple = ()  # ((benchmark, seed text), ...) in chain order, already passed through seed_text
    rules: tuple = ()  # (Rule, ...) in insertion order
    scaffold: bool = False  # v2 §2: every section's heading and applicability line, even when empty

    def __post_init__(self):
        benches = [b for b, _ in self.seeds]
        require(len(set(benches)) == len(benches) and all(b in ORDER for b in benches), "Seeds name distinct benchmarks")
        require(all(type(t) is str and t == seed_text(t) for _, t in self.seeds), "Seeds must be normalised")
        require(all(isinstance(r, Rule) for r in self.rules), "Rules must be Rule objects")
        require(type(self.scaffold) is bool, "scaffold is a flag")
        ids = [r.id for r in self.rules]
        require(len(set(ids)) == len(ids), "Duplicate rule id")
        keys = [(bench, r.text) for r in self.rules for bench in r.sections]
        require(len(set(keys)) == len(keys), "Duplicate rule text in one section")
        require(len(self.render().encode()) <= MAX_SKILL_BYTES, "Skill exceeds %d bytes" % MAX_SKILL_BYTES)

    @classmethod
    def seeded(cls, seeds):
        """Chain I's start: {benchmark: task-card instruction}."""
        return cls(seeds=tuple((b, seed_text(seeds[b])) for b in ORDER if b in seeds))

    def add(self, *rules):
        """Append-only: new rules go to the end of their sections, in the given order (§3)."""
        return Skill(self.seeds, self.rules + tuple(rules), self.scaffold)

    def size_with(self, *rules):
        """UTF-8 bytes of this Skill with ``rules`` appended, without the cap check (the length tests of §4 and §5.7)."""
        return len(_render(self.seeds, self.rules + tuple(rules), self.scaffold).encode())

    def fits(self, *rules):
        return self.size_with(*rules) <= MAX_SKILL_BYTES

    def text_with(self, *rules):
        """The rendered text with ``rules`` appended, without the cap: a control arm (§4 step 8: controls are only
        compared against, never accepted, so the 20,000-byte cap does not bind them)."""
        return _render(self.seeds, self.rules + tuple(rules), self.scaffold)

    def render(self):
        return _render(self.seeds, self.rules, self.scaffold)

    def to_json(self):
        """v2: a scaffolded Skill also records the flag (an unscaffolded one keeps v1's two keys)."""
        out = {"seeds": {b: t for b, t in self.seeds}, "rules": [r.to_json() for r in self.rules]}
        return {**out, "scaffold": True} if self.scaffold else out

    @classmethod
    def from_json(cls, value):
        require(type(value) is dict and set(value) in ({"seeds", "rules"}, {"seeds", "rules", "scaffold"})
                and value.get("scaffold", True) is True, "Skill JSON has seeds and rules (and a true scaffold flag)")
        require(type(value["seeds"]) is dict and type(value["rules"]) is list, "Malformed Skill JSON")
        seeds = tuple((b, value["seeds"][b]) for b in ORDER if b in value["seeds"])
        require(len(seeds) == len(value["seeds"]), "Unknown seed benchmark")
        rules = []
        for row in value["rules"]:
            require(type(row) is dict and set(row) == {"id", "text", "home", "also"} and type(row["also"]) is list,
                    "Malformed rule JSON")
            rules.append(Rule(row["id"], row["text"], row["home"], tuple(row["also"])))
        return cls(seeds, tuple(rules), "scaffold" in value)
