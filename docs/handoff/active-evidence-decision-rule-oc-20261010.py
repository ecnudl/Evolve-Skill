"""Zero-call, count-only table behind the decision-v2 design memo: CONDITIONAL resampling frequencies from fixed,
realized, jointly known paired holdout outcomes (candidate minus parent as wins / losses / ties). Exact, no Monte
Carlo: (a) finite-population sampling of n positions without replacement (hypergeometric), (b) independent draws at
the same plug-in outcome rates (multinomial). Only the FRESH components are evaluated -- v1's fresh net-wins rule
and v2's fresh one-sided sign tests -- not either complete decision procedure (no replay veto, no unknown positions,
single-task families only). The frequencies contain no new solver randomness and no candidate-generation
uncertainty; they do not establish future power or error rates. The BigCodeBench No-Skill rows use F's baseline of
2026-10-01, non-contemporaneous and added retrospectively (not a prospective null control)."""
from math import comb

POPS = {
    "QA  S-parent (observed +10.4pt)": (28, 3, 209), "QA  M-parent (observed +11.3pt)": (29, 2, 209),
    "QA  M-S (observed +0.8pt)": (6, 4, 230),
    "BCB x4 S-NoSkill r0": (15, 15, 211), "BCB x4 S-NoSkill r1": (20, 13, 209),
    "BCB x4 M-NoSkill r0": (18, 14, 209), "BCB x4 M-NoSkill r1": (22, 12, 208),
    "BCB y2 S-NoSkill r0": (16, 15, 210), "BCB y2 S-NoSkill r1": (18, 9, 214),
    "BCB y2 M-NoSkill r0": (17, 15, 209), "BCB y2 M-NoSkill r1": (21, 11, 209),
    "BCB NoSkill r1-r0 (x4 draw)": (9, 15, 217), "BCB NoSkill r1-r0 (y2 draw)": (8, 16, 217),
    "BCB x4 M-S": (20, 17, 205), "BCB y2 M-S": (15, 14, 212),
}
ALPHA = 0.05


def sign_p(k, n):
    """One-sided exact sign test: P(X >= k | n, 1/2)."""
    return 1.0 if n == 0 else sum(comb(n, i) for i in range(k, n + 1)) / 2 ** n


def joint(pop, n, finite):
    """Yield (wins, losses, probability) of a sample of n positions."""
    w, l, t = pop
    total = w + l + t
    if finite:
        denom = comb(total, n)
        for i in range(min(w, n) + 1):
            for j in range(min(l, n - i) + 1):
                if n - i - j <= t:
                    yield i, j, comb(w, i) * comb(l, j) * comb(t, n - i - j) / denom
    else:
        pw, pl, pt = w / total, l / total, t / total
        for i in range(n + 1):
            for j in range(n - i + 1):
                yield i, j, comb(n, i) * comb(n - i, j) * pw ** i * pl ** j * pt ** (n - i - j)


def frequencies(pop, finite):
    v1_keep = sum(p for i, j, p in joint(pop, 24, finite) if i - j >= 2)
    v1_revert = sum(p for i, j, p in joint(pop, 24, finite) if i - j < 0)
    gain = sum(p for i, j, p in joint(pop, 96, finite) if sign_p(i, i + j) <= ALPHA)
    harm = sum(p for i, j, p in joint(pop, 96, finite) if sign_p(j, i + j) <= ALPHA)
    return v1_keep, v1_revert, gain, harm


if __name__ == "__main__":
    print("%-34s %-44s %s" % ("population (wins, losses, ties)", "finite population (without replacement)",
                               "independent draws (plug-in rates)"))
    print("%-34s %-44s %s" % ("", "v1keep v1rev | v2gain v2harm (n=96)", "v1keep v1rev | v2gain v2harm (n=96)"))
    for name, pop in POPS.items():
        a, b = frequencies(pop, True), frequencies(pop, False)
        print("%-34s %.3f  %.3f | %.3f  %.3f                %.3f  %.3f | %.3f  %.3f" % (name, *a, *b))
