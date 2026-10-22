"""The level-1 ALFWorld action canonicaliser (registration §2.2, §2.3, §14 #16, §16 C-A9; plan §1 canonical.py,
§3, T-CANON-1..4).

On every arm the shell maps the solver's reply to the executed action in one fixed way:

1. the text is what the frozen loop would execute: the first ``<action>...</action>`` tag's content, stripped, or the
   whole reply, stripped, when there is no tag (backends.py:752-753, the same expression);
2. if that text is exactly an admissible command, it is executed (``tag_exact`` / ``whole_exact``);
3. otherwise level 1: a leading "action:" prefix, surrounding quotes and whitespace and a trailing period are removed
   (repeated until nothing changes) and the result is compared with the admissible commands ignoring case; exactly one
   match is executed in its admissible spelling (``tag_level1`` / ``whole_level1``);
4. otherwise the text of step 1 is executed unchanged (``unchanged``); the frozen rule for an empty or over-long action
   (``invalid_action_format``, backends.py:754) stays with the shell.

There is NO search of the reply for an admissible command (D3's earliest-admissible parse, pilot_alf_glm.py:178-195,
is not ported): that would execute commands the model rejected, which is action repair, not a learned Skill. Only the
level-1 steps differ from the frozen loop, which executes the raw text; from the first such step on, an episode's
later transitions and requests differ from v3's, so route-B ALFWorld numbers are not comparable with v3's (§2.3).
"""
from __future__ import annotations

import re

from skillopt.continual_eval.core import require

ACTION = re.compile(r"<action>(.*?)</action>", re.S)  # the frozen extraction, backends.py:752
PREFIX = re.compile(r"\Aaction\s*:", re.I)
QUOTES_AND_SPACE = "\"'`“”‘’ \t\r\n\f\v"
HOWS = ("tag_exact", "tag_level1", "whole_exact", "whole_level1", "unchanged")


def level1(text):
    """The level-1 normal form: the "action:" prefix, surrounding quotes and whitespace and a trailing period removed
    until none is left. Case is kept; the comparison ignores it."""
    previous = None
    while text != previous:
        previous = text
        text = PREFIX.sub("", text.strip(QUOTES_AND_SPACE), count=1).strip(QUOTES_AND_SPACE)
        if text.endswith("."):
            text = text[:-1]
    return text


def canonical(reply, admissible):
    """``(action, how)``: the action the shell executes for ``reply`` given the step's admissible commands, and how it
    was obtained (one of ``HOWS``)."""
    require(type(reply) is str, "A reply is text")
    require(isinstance(admissible, (list, tuple)) and all(type(c) is str for c in admissible),
            "Admissible commands are a list of text")
    match = ACTION.search(reply)
    raw = match.group(1).strip() if match else reply.strip()
    where = "tag" if match else "whole"
    if raw in admissible:
        return raw, where + "_exact"
    key = level1(raw).casefold()
    matches = sorted({c for c in admissible if c.casefold() == key}) if key else []
    if len(matches) == 1:
        return matches[0], where + "_level1"
    return raw, "unchanged"
