"""Leakage corpus extension for grid tasks; legacy implementations are delegated unchanged."""
from collections import Counter
from fractions import Fraction

from skillopt.coevo5 import leakage
from skillopt.continual_eval.core import require


class Corpus(leakage.Corpus):
    def __init__(self, benchmark, items, *, alfworld_texts=None):
        if benchmark != "zebralogic":
            super().__init__(benchmark, items, alfworld_texts=alfworld_texts)
            return
        require(all(item["benchmark"] == benchmark for item in items), "A corpus holds one benchmark")
        surfaces = [item["public"]["question"] + "\n" + "\n".join(item["public"]["columns"]) for item in items]
        grams = [leakage._grams(leakage.normalize(text).split()) for text in surfaces]
        counts = Counter(gram for found in grams for gram in found)
        self.benchmark, self.size = benchmark, len(grams)
        self.template = frozenset(g for g, count in counts.items()
                                  if Fraction(count, len(grams)) >= leakage.LEAK_TEMPLATE_SHARE)
        self.shared = frozenset(counts) - self.template
        self.phrases, self.words, self.numbers, self.options = set(), set(), set(), set()
        self.word_items = {}
        for item in items:
            grid = item["private"]["answer"]
            require(isinstance(grid, dict), "A grid corpus needs a validated private grid")
            for house, row in grid.items():
                for column, value in row.items():
                    self._text_answer(value, item)
                    # Catch a copied assignment as well as copied cell values, without adding detector categories.
                    self.phrases.add(tuple(leakage.normalize(house + " " + column + " " + value).split()))
