"""Authored V17 mechanism-transfer pilot; never a public benchmark.

Families, not cases or model repeats, are the design's independence units.
Gold is calculated by separately written host oracles, never by executing
reference Python on the host. References run only in the existing executor.
Mechanism annotations are HOST-ONLY; public_task excludes all metadata.
"""

from __future__ import annotations

import itertools
import json
from copy import deepcopy

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v6.native import NativeAdapter
from skillopt.coevolution_v8.feedback_study import public_task as _public
from skillopt.validator_pilot.api import digest

VERSION = "v17-authored-mechanism-transfer-v1"
ENTRY = "import logic\n\ndef solve(data):\n    return logic.run(data)\n"
CODE_SOURCE = ("signed-partition-cap", "transaction-cooldown-budget", "ancestor-closed-budget")
CODE_EXTRA = ("distinct-block-partition", "cardinality-gap-selection", "bounded-sign-assignment")
CODE_CONFIRM = ("cyclic-cover-budget", "two-machine-makespan")
CODE_FINAL = ("disjoint-profitable-runs", "weighted-deletion-palindrome", "window-distinct-cover", "signed-replacement-subset")
SHEET_TRANSFER = ("progressive-duty-tax", "priority-reserve-allocation", "bidirectional-storage")
SHEET_CONFIRM = ("two-source-dispatch", "deductible-coverage-layer")
SHEET_FINAL = ("partial-cancellation-invoice", "three-stage-yield-rework", "asymmetric-currency-netting", "replacement-volume-rebate")
RULE_FINAL = ("staged-path-procurement", "overlapping-endorsement-matrix", "dual-seed-recursive-consensus", "replacement-dual-authorization")
SMOKE_CODE = ("smoke-distinct-absolute", "smoke-even-index-product", "smoke-signed-adjacent-change", "smoke-positive-run-length", "smoke-new-signed-sum-policy")
SMOKE_SHEET = ("smoke-rectangle-border", "smoke-triangle-bill", "smoke-parallel-resistors", "smoke-new-flat-service-fee")
SMOKE_RULE = "smoke-three-way-joint"


def _contract(replacement=False):
    return {"change_scope": "full_replacement" if replacement else "partial_update",
            "supersedes_old_policy": replacement,
            "preserve_obligations": ["Keep protected interfaces, input values and audit definitions unchanged.",
                                     "Implement the new behavior where replacement is explicitly authorized."]}


def _metadata(domain, family, variant, split, replacement=False):
    return {"version": VERSION, "domain": domain, "structural_family": family,
            "variant": variant, "partition": split,
            "mechanism_cell": "near_miss" if replacement else "same_mechanism",
            "authorship": "host_authored_synthetic_not_public_benchmark",
            "historical_task_assets_used": False, "smoke_only": family.startswith("smoke-"),
            "oracle": "independent_host_specification_not_reference_execution",
            "independence_unit": "structural_family_not_variant_or_repeat",
            "independence_is_design_assumption_not_population_guarantee": True,
            "contract": _contract(replacement)}


def payload(adapter):
    """Host-only full task, including private outcomes and reference artifact."""
    return adapter.task.to_dict() if isinstance(adapter, CodingAdapter) else deepcopy(adapter.task)


def public_task(adapter):
    public = _public(adapter)
    public["domain"] = adapter.domain
    if adapter.domain == "coding":
        public["contract"] = deepcopy(payload(adapter)["metadata"]["contract"])
    if adapter.domain == "spreadsheet":
        public["runtime"] += " Equality inside expressions is ==. IF is lazy."
    # Adapters already use allowlists; fail closed if future changes add gold.
    if set(public) & {"metadata", "reference_files", "reference_artifact", "hidden_cases", "private_cases"}:
        raise ValueError("Host-only task data entered public projection")
    return public


# Each variant changes a semantic obligation, not merely numeric test values.
# Tuple: public specification, reference body, uniquely replaceable fault.
_CODE = {
    CODE_SOURCE[0]: (
        "Count partitions of the whole signed sequence into exactly k NONEMPTY contiguous blocks. "
        "Every block's sum must be at most 3. {variant} The empty sequence has one partition only when k=0.",
        "dp = {(0,0):1}\nfor end in range(1,len(values)+1):\n    for count in range(1,k+1):\n        total = 0\n        for start in range(end-1,-1,-1):\n            total += values[start]\n            if total <= 3 and (v == 0 or total >= -1):\n                dp[end,count] = dp.get((end,count),0)+dp.get((start,count-1),0)\nresult = dp.get((len(values),k),0)",
        ("total <= 3", "total < 3")),
    CODE_SOURCE[1]: (
        "values are nonnegative daily prices. Maximize realized profit with at most k completed transactions, "
        "one share held at most, no same-day buy/sell. A sale charges fee 1. {variant} Unsold stock earns nothing; doing nothing is legal.",
        "states = {(0,0,0):0}\nfor price in values:\n    nxt = {}\n    for (held,count,cool),cash in states.items():\n        choices = [((held,count,max(0,cool-1)),cash)]\n        if held and count < k:\n            choices.append(((0,count+1,1+v),cash+price-1))\n        if not held and cool == 0 and count < k:\n            choices.append(((1,count,0),cash-price))\n        for state,money in choices:\n            nxt[state] = max(nxt.get(state,-10000),money)\n    states = nxt\nresult = max([cash for (held,count,cool),cash in states.items() if held == 0])",
        ("cool == 0", "cool <= 1")),
    CODE_SOURCE[2]: (
        "Items have signed benefits values[i], cost (i mod 3)+1. Select items with total cost at most k. "
        "Selecting nonroot i requires its parent {variant} selected, transitively; item 0 has no parent. "
        "Return maximum summed benefit; selecting nothing is allowed.",
        "result = 0\nfor mask in range(1<<len(values)):\n    total = 0\n    cost = 0\n    legal = True\n    for i,x in enumerate(values):\n        if (mask>>i)&1:\n            parent = (i-1)//2 if v == 0 else i-1\n            if i and not ((mask>>parent)&1):\n                legal = False\n            cost += i%3+1\n            total += x\n    if legal and cost <= k:\n        result = max(result,total)",
        ("if legal and cost <= k:", "if cost <= k:")),
    CODE_EXTRA[0]: (
        "Count partitions into exactly k nonempty contiguous blocks, with no repeated value inside any block. "
        "{variant} Empty input has one partition iff k=0.",
        "dp = {(0,0):1}\nfor end in range(1,len(values)+1):\n    for count in range(1,k+1):\n        seen = set()\n        for start in range(end-1,-1,-1):\n            if values[start] in seen:\n                break\n            seen.add(values[start])\n            if v == 0 or (end-start)%2 == 1:\n                dp[end,count] = dp.get((end,count),0)+dp.get((start,count-1),0)\nresult = dp.get((len(values),k),0)",
        ("if values[start] in seen:", "if False:")),
    CODE_EXTRA[1]: (
        "Choose EXACTLY k indices to maximize the signed sum, leaving at least {variant} unchosen index(es) "
        "between successive chosen indices. Return null if infeasible; k=0 returns 0. This is a line, not a circle.",
        "states = {(0,-10):0}\nfor i,x in enumerate(values):\n    nxt = dict(states)\n    for (count,last),total in states.items():\n        if count < k and i-last > 1+v:\n            key = (count+1,i)\n            nxt[key] = max(nxt.get(key,-10000),total+x)\n    states = nxt\nanswers = [total for (count,last),total in states.items() if count == k]\nresult = max(answers) if answers else None",
        ("i-last > 1+v", "i-last >= 1+v")),
    CODE_EXTRA[2]: (
        "Assign each position a plus or minus sign. Count assignments whose signed total is k. "
        "{variant} Different signs on a zero are distinct assignments.",
        "states = {(0,0):1}\nfor x in values:\n    nxt = {}\n    for (total,minus),count in states.items():\n        for sign in (-1,1):\n            key = (total+sign*x,(minus+(sign == -1))%2)\n            nxt[key] = nxt.get(key,0)+count\n    states = nxt\nresult = sum(count for (total,minus),count in states.items() if total == k and (v == 0 or minus == 0))",
        ("for sign in (-1,1):", "for sign in ((1,) if x == 0 else (-1,1)):")),
    CODE_CONFIRM[0]: (
        "Choose at most k positions on a circle, maximizing total signed benefit. Every adjacent circular pair "
        "must include a chosen position. {variant} Infeasible returns null. Empty input returns 0 only when the selection-count "
        "constraint is feasible (thus exactly-k requires k=0); otherwise it returns null. A singleton's pair is itself.",
        "answers = []\nfor mask in range(1<<len(values)):\n    selected = [i for i in range(len(values)) if (mask>>i)&1]\n    if len(selected) > k or (v == 1 and len(selected) != k):\n        continue\n    if all(((mask>>i)&1) or ((mask>>((i+1)%len(values)))&1) for i in range(len(values))):\n        answers.append(sum(values[i] for i in selected))\nresult = max(answers) if answers else None",
        ("for i in range(len(values))):", "for i in range(max(0,len(values)-1))):")),
    CODE_CONFIRM[1]: (
        "EXPLICIT FULL POLICY REPLACEMENT: old identical-machine timings are withdrawn. "
        "Assign each nonnegative job duration to one of two machines. Machine A duration equals the input; "
        "machine B duration is {variant}. B may receive at most k jobs. Return the minimum makespan, with idle machines allowed.",
        "result = sum(values)\nfor mask in range(1<<len(values)):\n    chosen = [i for i in range(len(values)) if (mask>>i)&1]\n    if len(chosen) <= k:\n        b = sum(values[i]*(2 if v == 0 else 1)+v for i in chosen)\n        a = sum(values[i] for i in range(len(values)) if i not in chosen)\n        result = min(result,max(a,b))",
        ("sum(values[i]*(2 if v == 0 else 1)+v for i in chosen)", "sum(values[i] for i in chosen)")),
    CODE_FINAL[0]: (
        "Choose up to k nonempty contiguous runs, separated by at least one unchosen position, to maximize signed sum. "
        "{variant} No position is counted twice; selecting nothing yields 0.",
        "result = 0\nfor mask in range(1<<len(values)):\n    runs = 0\n    length = 0\n    legal = True\n    for i in range(len(values)+1):\n        if i < len(values) and ((mask>>i)&1):\n            if length == 0:\n                runs += 1\n            length += 1\n        else:\n            if v == 1 and length == 1:\n                legal = False\n            length = 0\n    if legal and runs <= k:\n        result = max(result,sum(x for i,x in enumerate(values) if (mask>>i)&1))",
        ("if legal and runs <= k:", "if legal and runs < k:")),
    CODE_FINAL[1]: (
        "Delete positions to make the retained sequence a palindrome. Deleting original position i costs "
        "{variant}. Return minimum total deletion cost. k is unused; an empty retained sequence is permitted.",
        "costs = [1+i%3 if v == 0 else 1+abs(x) for i,x in enumerate(values)]\ndp = {}\nfor length in range(2,len(values)+1):\n    for left in range(len(values)-length+1):\n        right = left+length-1\n        dp[left,right] = min(costs[left]+dp.get((left+1,right),0),costs[right]+dp.get((left,right-1),0))\n        if values[left] == values[right]:\n            dp[left,right] = min(dp[left,right],dp.get((left+1,right-1),0))\nresult = dp.get((0,len(values)-1),0)",
        ("min(costs[left]+dp.get((left+1,right),0),costs[right]+dp.get((left,right-1),0))", "1+min(dp.get((left+1,right),0),dp.get((left,right-1),0))")),
    CODE_FINAL[2]: (
        "Count nonempty contiguous subarrays containing exactly k distinct values. {variant} k=0 yields 0.",
        "result = 0\nfor left in range(len(values)):\n    counts = {}\n    for right in range(left,len(values)):\n        x = values[right]\n        counts[x] = counts.get(x,0)+1\n        if len(counts) == k and (v == 0 or all(count >= 2 for count in counts.values())):\n            result += 1",
        ("len(counts) == k", "len(counts) <= k")),
    CODE_FINAL[3]: (
        "EXPLICIT FULL POLICY REPLACEMENT: obsolete behavior required exactly k POSITIVE items. "
        "New behavior chooses AT MOST k positions, including zero and negative values, and minimizes "
        "absolute distance of their summed values from {variant}. Return that minimum distance, not the sum. "
        "The empty choice is legal. Preserve only the documented input audits and api.py, not the obsolete policy.",
        "target = 2 if v == 0 else -2\nresult = abs(target)\nfor mask in range(1<<len(values)):\n    chosen = [x for i,x in enumerate(values) if (mask>>i)&1]\n    if len(chosen) <= k:\n        result = min(result,abs(sum(chosen)-target))",
        ("if len(chosen) <= k:", "if len(chosen) == k and all(x > 0 for x in chosen):")),
    SMOKE_CODE[0]: ("Return the number of DISTINCT absolute input values. k is unused.",
        "result = len(set(abs(x) for x in values))", ("abs(x)", "x")),
    SMOKE_CODE[1]: ("Multiply values at even ORIGINAL indices, with empty product 1. k is unused.",
        "result = 1\nfor i,x in enumerate(values):\n    if i%2 == 0:\n        result *= x", ("i%2 == 0", "i%2 == 1")),
    SMOKE_CODE[2]: ("Sum ABSOLUTE differences between adjacent values. k is unused; lengths below two give zero.",
        "result = sum(abs(values[i]-values[i-1]) for i in range(1,len(values)))", ("abs(values[i]-values[i-1])", "values[i]-values[i-1]")),
    SMOKE_CODE[3]: ("Return longest contiguous run of strictly positive values. k is unused.",
        "result = 0\nrun = 0\nfor x in values:\n    run = run+1 if x > 0 else 0\n    result = max(result,run)", ("x > 0", "x >= 0")),
    SMOKE_CODE[4]: ("EXPLICIT FULL POLICY REPLACEMENT: old positive-only summation is withdrawn. Return the SIGNED sum of every value, including negatives. k is unused. Preserve only the audit/interface contract, not old result semantics.",
        "result = sum(values)", ("sum(values)", "sum(x for x in values if x > 0)")),
}

_CODE_VARIANTS = {
    CODE_SOURCE[0]: ("Negative block sums have no lower bound.", "Every block sum must also be at least -1."),
    CODE_SOURCE[1]: ("The entire day after a sale forbids a new buy.", "The two entire days after a sale forbid a new buy."),
    CODE_SOURCE[2]: ("floor((i-1)/2)", "i-1"),
    CODE_EXTRA[0]: ("Block lengths are unrestricted.", "Every block must have ODD length."),
    CODE_EXTRA[1]: ("one", "two"),
    CODE_EXTRA[2]: ("There is no restriction on minus-sign count.", "The number of minus signs must be EVEN."),
    CODE_CONFIRM[0]: ("There is no minimum number selected.", "Exactly k positions must be selected."),
    CODE_CONFIRM[1]: ("twice its input duration", "its input duration plus one setup unit per job"),
    CODE_FINAL[0]: ("Run lengths are unrestricted.", "Every chosen run must contain at least two positions."),
    CODE_FINAL[1]: ("1+(i mod 3)", "1+abs(values[i])"),
    CODE_FINAL[2]: ("There are no multiplicity restrictions.", "Every distinct value in the subarray must occur at least twice."),
    CODE_FINAL[3]: ("+2", "-2"),
}


def _code_inputs(family):
    rows = [([2,-1,3,0],2), ([1,2,1,2],2), ([],0), ([0,0],1),
            ([3,-3,3,-1,2],3), ([-2,4,-1,3,-2,1],2), ([1],0), ([2,0,2,0,2,0],4),
            ([3,0,3,0,3,0,3],3), ([-1,-2],1)]
    if family in {CODE_SOURCE[1], CODE_CONFIRM[1]}:
        rows = [(list(map(abs,a)),k) for a,k in rows]
    if family == CODE_SOURCE[1]:
        rows += [([0,5,0,0,5],2),([0,5,0,5],2)]
    if family == CODE_EXTRA[2]:
        rows += [([0,0],0)]
    if family == CODE_FINAL[0]:
        rows += [([1,2],1)]
    if family == CODE_FINAL[1]:
        rows += [([1,1,2,1],0)]
    if family == CODE_CONFIRM[0]:
        rows += [([],1)]
    return [{"values":a,"k":k} for a,k in rows]


def _code_oracle(family, v, data):
    """Independent declarative enumeration; no reference source is read/executed."""
    a,k = data["values"],data["k"]
    n = len(a)
    def subsets():
        return (s for size in range(n+1) for s in itertools.combinations(range(n),size))
    if family in {CODE_SOURCE[0], CODE_EXTRA[0]}:
        result = int(n == 0 and k == 0)
        if 1 <= k <= n:
            for cuts in itertools.combinations(range(1,n),k-1):
                edges = (0,*cuts,n)
                blocks = [a[left:right] for left,right in zip(edges,edges[1:])]
                valid = (all(sum(b) <= 3 and (v == 0 or sum(b) >= -1) for b in blocks)
                         if family == CODE_SOURCE[0] else
                         all(len(set(b)) == len(b) and (v == 0 or len(b)%2) for b in blocks))
                result += int(valid)
    elif family == CODE_SOURCE[1]:
        def trades(start, remaining):
            options = [0]
            if remaining:
                for buy in range(start,n):
                    for sell in range(buy+1,n):
                        options.append(a[sell]-a[buy]-1+trades(sell+2+v,remaining-1))
            return max(options)
        result = trades(0,k)
    elif family == CODE_SOURCE[2]:
        result = max([0]+[sum(a[i] for i in s) for s in subsets()
                          if sum(i%3+1 for i in s) <= k and all(i == 0 or ((i-1)//2 if v == 0 else i-1) in s for i in s)])
    elif family == CODE_EXTRA[1]:
        options = [sum(a[i] for i in s) for s in itertools.combinations(range(n),k)
                   if all(right-left >= 2+v for left,right in zip(s,s[1:]))]
        result = max(options) if options else None
    elif family == CODE_EXTRA[2]:
        result = sum(sum(x*s for x,s in zip(a,signs)) == k and (v == 0 or signs.count(-1)%2 == 0)
                     for signs in itertools.product((-1,1),repeat=n))
    elif family == CODE_CONFIRM[0]:
        options = [sum(a[i] for i in s) for s in subsets() if len(s) <= k and (v == 0 or len(s) == k)
                   and all(i in s or (i+1)%n in s for i in range(n))]
        result = max(options) if options else None
    elif family == CODE_CONFIRM[1]:
        result = min(max(sum(a[i] for i in range(n) if i not in s),
                         sum(a[i]*2 if v == 0 else a[i]+1 for i in s)) for s in subsets() if len(s) <= k)
    elif family == CODE_FINAL[0]:
        options = []
        for s in subsets():
            groups = [list(g) for _,g in itertools.groupby(enumerate(s),lambda pair:pair[1]-pair[0])]
            if len(groups) <= k and (v == 0 or all(len(g) >= 2 for g in groups)):
                options.append(sum(a[i] for i in s))
        result = max(options)
    elif family == CODE_FINAL[1]:
        costs = [1+i%3 if v == 0 else 1+abs(x) for i,x in enumerate(a)]
        result = min(sum(costs[i] for i in range(n) if i not in s) for s in subsets()
                     if [a[i] for i in s] == [a[i] for i in reversed(s)])
    elif family == CODE_FINAL[2]:
        blocks = [a[left:right] for left in range(n) for right in range(left+1,n+1)]
        result = sum(len(set(b)) == k and (v == 0 or all(b.count(x) >= 2 for x in set(b))) for b in blocks)
    elif family == CODE_FINAL[3]:
        result = min(abs(sum(a[i] for i in s)-(2 if v == 0 else -2)) for s in subsets() if len(s) <= k)
    elif family == SMOKE_CODE[0]:
        result = len({x*x for x in a})
    elif family == SMOKE_CODE[1]:
        result = 1
        for x in a[::2]:
            result *= x
    elif family == SMOKE_CODE[2]:
        result = sum(max(x,y)-min(x,y) for x,y in zip(a,a[1:]))
    elif family == SMOKE_CODE[3]:
        result = max([0]+[right-left for left in range(n) for right in range(left+1,n+1) if all(x > 0 for x in a[left:right])])
    elif family == SMOKE_CODE[4]:
        result = sum(x for x in a if x >= 0)-sum(-x for x in a if x < 0)
    else:
        raise ValueError("Unregistered code family")
    return {"result":result,"input_count":n,"input_sum":sum(a)}


def _coding(family, variant, split):
    description,body,fault = _CODE[family]
    description = description.format(variant=_CODE_VARIANTS.get(family,("",""))[variant])
    source = "def run(data):\n    values,k = data['values'],data['k']\n    v = "+str(variant)+"\n"
    source += "".join("    "+line+"\n" for line in body.splitlines())
    source += "    return {'result':result,'input_count':len(values),'input_sum':sum(values)}\n"
    # This replacement concerns the body, not the protected audit expression.
    if body.count(fault[0]) != 1:
        raise ValueError("Ambiguous authored fault: "+family)
    identifier = f"repo-v17-{split}-{family}-v{variant}"
    cases = [{"label":f"{identifier}-c{i}","input":data,"expected":_code_oracle(family,variant,data),
              "exception":None,"public":i < 2,"dimension":"requested_behavior"}
             for i,data in enumerate(_code_inputs(family))]
    replacement = family in {CODE_FINAL[3], CODE_CONFIRM[1], SMOKE_CODE[4]}
    schema = {"type":"object","properties":{
        "values":{"type":"array","items":{"type":"integer","minimum":0 if family in {CODE_SOURCE[1],CODE_CONFIRM[1]} else -6,"maximum":6},"maxItems":8},
        "k":{"type":"integer","minimum":0,"maximum":6}},"required":["values","k"],"additionalProperties":False}
    return CodingAdapter(RepoTask(id=identifier,split=split,family=family,cluster_id="v17-coding-"+family,
        prompt="Repair logic.py under the following specification. "+description+
               " Return exactly result, input_count and input_sum; the audits are ORIGINAL length and signed sum. "
               "Do not change api.py or mutate inputs. These audits remain protected even when the behavior is replaced.",
        files={"api.py":ENTRY,"logic.py":source.replace(*fault,1)},reference_files={"api.py":ENTRY,"logic.py":source},
        editable_paths=["logic.py"],input_domain=schema,public_cases=cases[:2],private_cases=cases[2:],
        metadata=_metadata("coding",family,variant,split,replacement)))


def _sheet_spec(family, v):
    """Public specifications and reference dependency graphs, never host gold."""
    if family == SHEET_TRANSFER[0]:
        desc = "A1 gross import value; first A2 units are duty-free; duty rate A3; sales tax rate A4; rebate A5. B1 dutiable value floored at zero; B2 duty; B3 sales-tax base; B4 final bill including duty/tax minus rebate. "
        desc += "Rebate reduces the tax base, floored at zero." if v else "Rebate is applied after tax and does NOT reduce its base."
        fs = ["=MAX(0,A1-A2)","=B1*A3","=MAX(0,A1+B2-A5)" if v else "=A1+B2","=A1+B2+B3*A4-A5"]
        fault = ("B3","=A1")
    elif family == SHEET_TRANSFER[1]:
        desc = "A1 stock, A2 protected reserve, A3 priority claim, A4 ordinary claim, A5 ordinary-item price. B1 distributable stock; B2 priority filled; B3 ordinary filled from remaining; B4 ordinary bill. "
        desc += "Priority may consume the reserve; reserve is deducted only AFTER priority fill when computing B1, which is ordinary availability." if v else "Reserve is deducted BEFORE either claim; B1 is availability before priority fill."
        fs = (["=MAX(0,A1-B2-A2)","=MIN(A1,A3)","=MIN(B1,A4)","=B3*A5"] if v else
              ["=MAX(0,A1-A2)","=MIN(B1,A3)","=MIN(MAX(0,B1-B2),A4)","=B3*A5"])
        fault = ("B3","=MIN(B1,A4)" if not v else "=MIN(A1,A4)")
    elif family == SHEET_TRANSFER[2]:
        desc = "A1 current stored energy, A2 capacity (at least A1), A3 signed requested grid transfer (positive=charge), A4 charge efficiency and A5 discharge efficiency in (0,1]. B1 accepted charge from grid; B2 delivered discharge to grid; B3 energy after transfer; B4 signed net grid draw. "
        desc += "A3 is instead specified on the STORAGE side: positive increases stored energy, negative removes it." if v else "A3 is measured on the GRID side for both signs."
        fs = (["=MIN(MAX(0,A3),A2-A1)/A4","=MIN(MAX(0,0-A3),A1)*A5","=A1+B1*A4-B2/A5","=B1-B2"] if v else
              ["=MIN(MAX(0,A3),(A2-A1)/A4)","=MIN(MAX(0,0-A3),A1*A5)","=A1+B1*A4-B2/A5","=B1-B2"])
        fault = ("B3","=A1+B1-B2")
    elif family == SHEET_CONFIRM[0]:
        desc = "A1 demand; A2 local capacity; A3 local unit price; A4 remote capacity; A5 remote unit price. B1 local dispatch, B2 remote dispatch, B3 unmet demand, B4 cost. "
        desc += "Use cheaper source first, ties favor local." if v else "Always exhaust local capacity before using remote, regardless of price."
        fs = ["=IF(A3<=A5,MIN(A1,A2),MIN(MAX(0,A1-A4),A2))" if v else "=MIN(A1,A2)",
              "=MIN(MAX(0,A1-B1),A4)","=MAX(0,A1-B1-B2)","=B1*A3+B2*A5"]
        fault = ("B2","=MIN(A1,A4)")
    elif family == SHEET_CONFIRM[1]:
        desc = "EXPLICIT FULL POLICY REPLACEMENT: the obsolete policy ignoring prior reimbursement is withdrawn. A1 loss, A2 deductible, A3 coverage cap, A4 insurer share in [0,1], A5 prior reimbursement. B1 loss after deductible, B2 eligible remainder after prior reimbursement, B3 insurer payment, B4 residual cost to claimant including deductible. "
        desc += "Cap limits FINAL insurer payment, after applying share." if v else "Cap limits loss BEFORE applying insurer share."
        fs = ["=MAX(0,A1-A2)","=MAX(0,B1-A5)","=MIN(B2*A4,A3)" if v else "=MIN(B2,A3)*A4","=MAX(0,A1-A5-B3)"]
        fault = ("B3","=MIN(B1,A3)*A4")
    elif family == SHEET_FINAL[0]:
        desc = "A1 originally ordered quantity, A2 cancelled quantity capped at ordered amount, A3 unit price, A4 minimum surviving quantity for discount, A5 discount fraction. B1 surviving quantity, B2 prediscount subtotal, B3 discount, B4 final subtotal. "
        desc += "Qualification uses ORIGINAL ordered quantity, even after cancellation." if v else "Qualification uses SURVIVING quantity after cancellation."
        fs = ["=MAX(0,A1-A2)","=B1*A3","=IF(A1>=A4,B2*A5,0)" if v else "=IF(B1>=A4,B2*A5,0)","=B2-B3"]
        fault = ("B3","=IF(B1>A4,A1*A3*A5,0)")
    elif family == SHEET_FINAL[1]:
        desc = "A1 initial units; stage-one yield A2; stage-two yield A3; rejected-unit recovery fraction A4; unit value A5. B1 passes stage one; B2 passes both stages; B3 additional recovered units; B4 total value including recovery. "
        desc += "Only STAGE TWO rejects can be recovered." if v else "Rejects from BOTH stages can be recovered once."
        fs = ["=A1*A2","=B1*A3","=(B1-B2)*A4" if v else "=(A1-B2)*A4","=(B2+B3)*A5"]
        fault = ("B3","=(A1-B1)*A4")
    elif family == SHEET_FINAL[2]:
        desc = "A1 foreign receivable, A2 foreign payable, A3 bid rate, A4 ask rate (at least bid), A5 fixed fee charged once only when there is conversion. B1 signed net foreign balance; B2 converted receivable; B3 converted payable; B4 net domestic proceeds minus fee. "
        desc += "Do NOT net before conversion: convert gross receivable at bid and gross payable at ask; charge fee if either gross leg is nonzero." if v else "Net FIRST: convert positive net at bid or negative net at ask, charging fee only for nonzero net."
        fs = ["=A1-A2","=A1*A3" if v else "=MAX(0,B1)*A3","=A2*A4" if v else "=MAX(0,0-B1)*A4",
              "=B2-B3-IF(A1+A2==0,0,A5)" if v else "=B2-B3-IF(B1==0,0,A5)"]
        fault = ("B3","=MAX(0,0-B1)*A3" if not v else "=A2*A3")
    elif family == SHEET_FINAL[3]:
        desc = "EXPLICIT FULL POLICY REPLACEMENT: remove the old marginal-tier per-item rebate. A1 quantity, A2 unit price, A3 qualification threshold, A4 one-off fixed rebate, A5 tax fraction. B1 gross amount; B2 new fixed rebate (capped at gross); B3 net amount; B4 tax-inclusive invoice. "
        desc += "New rebate qualification is STRICTLY MORE than A3." if v else "New rebate qualification is AT LEAST A3."
        fs = ["=A1*A2",f"=IF(A1{'>' if v else '>='}A3,MIN(A4,B1),0)","=B1-B2","=B3*(1+A5)"]
        fault = ("B2","=MIN(B1,MAX(0,A1-A3)*A4)")
    elif family == SMOKE_SHEET[0]:
        desc = "A1/A2 rectangle sides; A3 price per perimeter unit; B1 perimeter, B2 area, B3 perimeter bill, B4 bill plus A4 minus A5."
        fs = ["=2*(A1+A2)","=A1*A2","=B1*A3","=B3+A4-A5"]
        fault = ("B1","=A1+A2")
    elif family == SMOKE_SHEET[1]:
        desc = "A1 base and A2 height; A3 price per area; B1 triangular area, B2 price, B3 tax B2*A4, B4 price plus tax minus A5."
        fs = ["=A1*A2/2","=B1*A3","=B2*A4","=B2+B3-A5"]
        fault = ("B1","=A1*A2")
    elif family == SMOKE_SHEET[2]:
        desc = "A1/A2 positive resistances in parallel; B1 resistance sum, B2 product, B3 equivalent resistance, B4 current under A3 voltage. A4/A5 unused."
        fs = ["=A1+A2","=A1*A2","=B2/B1","=A3/B3"]
        fault = ("B3","=B1")
    elif family == SMOKE_SHEET[3]:
        desc = "EXPLICIT FULL POLICY REPLACEMENT: old proportional service fee is withdrawn. A1 quantity, A2 price, A3 FLAT one-off service fee, A4 discount, A5 tax fraction. B1 subtotal, B2 service fee (A3 iff quantity positive), B3 subtotal plus fee minus discount, B4 taxed total."
        fs = ["=A1*A2","=IF(A1>0,A3,0)","=B1+B2-A4","=B3*(1+A5)"]
        fault = ("B2","=B1*A3")
    else:
        raise ValueError("Unknown Spreadsheet family")
    formulas = {f"B{i+1}":f for i,f in enumerate(fs)}
    formulas.update(C1="=B4",C2="=B1+2*B2+3*B3+4*B4")
    return desc,formulas,fault


def _sheet_inputs(family):
    rows = [(12,4,2,3,1),(8,2,3,1,2),(0,0,0,0,0),(4,4,1,4,0),
            (3,5,2,3,1),(20,8,4,2,3),(1,0,2,1,1),(6,3,0,0,2),(10,2,5,5,1),(4,1,4,3,4)]
    if family in {SHEET_TRANSFER[0],SHEET_CONFIRM[1],SHEET_FINAL[0],SHEET_FINAL[1],SHEET_FINAL[3]}:
        rows = [(12,4,.2,.3,1),(8,2,.5,.5,2),(0,0,0,0,0),(4,4,1,1,0),
                (3,5,.4,.2,1),(20,8,.8,.7,3),(1,0,.2,0,1),(6,3,0,1,2),(10,2,.5,.5,1),(4,1,1,.3,4)]
    if family == SHEET_CONFIRM[1]:
        rows = [(12,2,4,.5,1),(20,3,5,.8,2),(0,0,0,0,0),(4,4,2,1,0),(3,5,2,.3,1),
                (20,8,4,.2,3),(1,0,2,1,1),(6,3,0,0,2),(10,2,5,.5,1),(4,1,4,.3,4)]
    if family in {SHEET_FINAL[0],SHEET_FINAL[3]}:
        rows = [(12,4,2,3,.1),(8,2,3,1,.2),(0,0,0,0,0),(4,4,4,4,0),(3,5,2,3,.5),
                (20,8,4,2,.3),(1,0,2,1,1),(6,3,3,6,.2),(10,2,5,5,.1),(4,1,4,3,.4)]
    if family == SHEET_FINAL[1]:
        rows = [(12,.8,.5,.3,2),(8,.5,.8,.5,3),(0,0,0,0,0),(4,1,1,1,2),(3,0,1,.3,1),
                (20,.6,.4,.2,3),(1,1,0,1,1),(6,.3,0,0,2),(10,.2,.5,.5,1),(4,1,.4,.3,4)]
    if family == SHEET_TRANSFER[2]:
        rows = [(4,10,3,.8,.5),(8,10,-2,.5,.8),(0,0,0,1,1),(4,4,4,.5,.5),(3,5,-20,.7,.3),
                (0,8,20,.4,.2),(1,1,-1,1,1),(6,9,0,.2,.2),(10,12,5,.5,.5),(4,10,-1,.3,.4)]
    if family == SHEET_FINAL[2]:
        rows = [(12,4,2,3,1),(8,2,1,3,2),(0,0,0,0,0),(4,4,1,4,0),(3,5,2,3,1),
                (20,8,2,4,3),(1,0,1,2,1),(6,3,0,0,2),(10,2,5,5,1),(4,1,3,4,4)]
    if family == SMOKE_SHEET[2]:
        rows = [(max(1,a),max(1,b),c,d,e) for a,b,c,d,e in rows]
    if family == SHEET_CONFIRM[0]:
        rows += [(5,4,1,5,3)]
    return [{f"A{i+1}":x for i,x in enumerate(row)} for row in rows]


def _sheet_oracle(family,v,d):
    a,b,c,e,f = (d[f"A{i}"] for i in range(1,6))
    if family == SHEET_TRANSFER[0]:
        taxable = max(0,a-b)
        duty = taxable*c
        base = max(0,a+duty-f) if v else a+duty
        out = [taxable,duty,base,a+duty+base*e-f]
    elif family == SHEET_TRANSFER[1]:
        priority = min(a,c) if v else min(max(0,a-b),c)
        availability = max(0,a-priority-b) if v else max(0,a-b)
        ordinary = min(max(0,a-b-priority),e)
        out = [availability,priority,ordinary,ordinary*f]
    elif family == SHEET_TRANSFER[2]:
        stored_add = min(max(c,0)*(1 if v else e),b-a)
        stored_remove = min(max(-c,0)*(1 if v else 1/f),a)
        charge,discharge = stored_add/e,stored_remove*f
        out = [charge,discharge,a+stored_add-stored_remove,charge-discharge]
    elif family == SHEET_CONFIRM[0]:
        remote = min(a,e) if v and c > f else min(max(0,a-b),e)
        local = min(max(0,a-remote),b)
        out = [local,remote,max(0,a-local-remote),local*c+remote*f]
    elif family == SHEET_CONFIRM[1]:
        after = max(0,a-b)
        eligible = max(0,after-f)
        paid = min(eligible*e,c) if v else min(eligible,c)*e
        out = [after,eligible,paid,max(0,a-f-paid)]
    elif family == SHEET_FINAL[0]:
        remain = max(0,a-b)
        gross = remain*c
        discount = gross*f if (a if v else remain) >= e else 0
        out = [remain,gross,discount,gross-discount]
    elif family == SHEET_FINAL[1]:
        first,second = a*b,a*b*c
        recovered = (first-second if v else a-second)*e
        out = [first,second,recovered,(second+recovered)*f]
    elif family == SHEET_FINAL[2]:
        net = a-b
        receivable = a*c if v else max(0,net)*c
        payable = b*e if v else max(0,-net)*e
        fee = f if (a+b != 0 if v else net != 0) else 0
        out = [net,receivable,payable,receivable-payable-fee]
    elif family == SHEET_FINAL[3]:
        gross = a*b
        rebate = min(e,gross) if (a > c if v else a >= c) else 0
        out = [gross,rebate,gross-rebate,(gross-rebate)*(1+f)]
    elif family == SMOKE_SHEET[0]:
        out = [2*(a+b),a*b,2*(a+b)*c,2*(a+b)*c+e-f]
    elif family == SMOKE_SHEET[1]:
        area = a*b*.5
        out = [area,area*c,area*c*e,area*c*(1+e)-f]
    elif family == SMOKE_SHEET[2]:
        equivalent = 1/(1/a+1/b)
        out = [a+b,a*b,equivalent,c/equivalent]
    elif family == SMOKE_SHEET[3]:
        gross,fee = a*b,c if a > 0 else 0
        out = [gross,fee,gross+fee-e,(gross+fee-e)*(1+f)]
    else:
        raise ValueError("Unregistered sheet oracle")
    return {**{f"B{i+1}":x for i,x in enumerate(out)},"C1":out[3],"C2":sum((i+1)*x for i,x in enumerate(out))}


def _sheet(family,variant,split):
    description,formulas,fault = _sheet_spec(family,variant)
    identifier = f"v17-sheet-{split}-{family}-v{variant}"
    cases = [{"id":f"{identifier}-c{i}","overrides":d,"expected":_sheet_oracle(family,variant,d)}
             for i,d in enumerate(_sheet_inputs(family))]
    replacement = family in {SHEET_FINAL[3], SHEET_CONFIRM[1], SMOKE_SHEET[3]}
    return NativeAdapter({"id":identifier,"domain":"spreadsheet","split":split,"family":family,
        "cluster_id":"v17-sheet-"+family,"contract":_contract(replacement),
        "prompt":"Repair B1..B4 formulas. "+description+
                 " All unspecified quantities are nonnegative. All intermediates are required outputs. "
                 "C1=B4 and C2=B1+2*B2+3*B3+4*B4 are protected audits; do not edit them or inputs. "
                 "This is a bounded numeric formula DSL, not Excel: formula prefix =, equality ==, lazy IF.",
        "inputs":deepcopy(cases[0]["overrides"]),"formulas":{**formulas,fault[0]:fault[1]},
        "editable_cells":["B1","B2","B3","B4"],"answer_cell":"C1",
        "reference_artifact":{"formulas":{cell:formulas[cell] for cell in ("B1","B2","B3","B4")}},
        "public_cases":cases[:2],"hidden_cases":cases[2:],
        "metadata":_metadata("spreadsheet",family,variant,split,replacement)})


def _rule_spec(family,v):
    if family == RULE_FINAL[0]:
        desc = "first requires (a OR b) AND c; second requires d AND e; combined follows from first OR second; ready needs combined AND f; archive needs first AND g."
        rules = [(["a","c"],"first"),(["b","c"],"first"),(["d","e"],"second"),
                 (["first"],"combined"),(["second"],"combined"),(["combined","f"],"ready"),(["first","g"],"archive")]
        if v:
            desc = "first requires (a OR b) AND c; second requires d AND e; combined needs BOTH first AND second; ready needs combined AND f; archive needs second AND g."
            rules[3:5] = [(["first","second"],"combined"),(["second","first"],"combined")]
            rules[-1] = (["second","g"],"archive")
    elif family == RULE_FINAL[1]:
        desc = "x requires a AND b, or c AND d. y requires a AND c, or b AND e. endorsed needs BOTH x AND y; ready follows from endorsed with f OR with g. Shared base evidence may support both endorsements."
        rules = [(["a","b"],"x"),(["c","d"],"x"),(["a","c"],"y"),(["b","e"],"y"),
                 (["x","y"],"endorsed"),(["endorsed","f"],"ready"),(["endorsed","g"],"ready")]
        if v:
            desc = desc.replace("f OR with g","f AND g")
            rules[-2:] = [(["endorsed","f","g"],"ready"),(["endorsed","g","f"],"ready")]
    elif family == RULE_FINAL[2]:
        desc = "a externally seeds x; c AND d externally seed y. y with b feeds x; x with e feeds y. A cycle never seeds itself. consensus needs x AND y AND f; ready needs consensus AND g."
        rules = [(["a"],"x"),(["c","d"],"y"),(["y","b"],"x"),(["x","e"],"y"),
                 (["x","y","f"],"consensus"),(["consensus","g"],"ready")]
        if v:
            desc = desc.replace("a externally seeds x", "a AND g externally seed x").replace("ready needs consensus AND g", "ready needs consensus AND a")
            rules[0] = (["a","g"],"x")
            rules[-1] = (["consensus","a"],"ready")
    elif family == RULE_FINAL[3]:
        desc = "EXPLICIT FULL POLICY REPLACEMENT: obsolete a-only authorization is withdrawn. Current identity requires b AND c; entitlement requires d OR e; authorized needs BOTH identity AND entitlement; release requires authorized AND f; logged requires release AND g. Do not preserve the obsolete a-only grant."
        rules = [(["b","c"],"identity"),(["d"],"entitlement"),(["e"],"entitlement"),
                 (["identity","entitlement"],"authorized"),(["authorized","f"],"release"),(["release","g"],"logged")]
        if v:
            desc = desc.replace("entitlement requires d OR e", "entitlement requires d AND e")
            rules[1:3] = [(["d","e"],"entitlement"),(["e","d"],"entitlement")]
    elif family == SMOKE_RULE:
        desc = "left needs a AND c; middle needs b AND d; right needs e AND f; ready needs ALL left, middle and right. g has no effect."
        rules = [(["a","c"],"left"),(["b","d"],"middle"),(["e","f"],"right"),(["left","middle","right"],"ready")]
    else:
        raise ValueError("Unknown Rule family")
    return desc+" audit depends ONLY on h.",rules


def _rule_oracle(family,v,facts):
    a,b,c,d,e,f,g,h = (x in facts for x in "abcdefgh")
    if family == RULE_FINAL[0]:
        first,second = (a or b) and c,d and e
        combined = (first and second) if v else (first or second)
        out = {"first":first,"second":second,"combined":combined,"ready":combined and f,"archive":(second if v else first) and g}
    elif family == RULE_FINAL[1]:
        x,y = (a and b) or (c and d),(a and c) or (b and e)
        out = {"x":x,"y":y,"endorsed":x and y,"ready":x and y and ((f and g) if v else (f or g))}
    elif family == RULE_FINAL[2]:
        seed = (a and g) if v else a
        x = seed or (c and d and b)
        y = (c and d) or (seed and e)
        consensus = x and y and f
        out = {"x":x,"y":y,"consensus":consensus,"ready":consensus and (a if v else g)}
    elif family == RULE_FINAL[3]:
        identity = b and c
        entitlement = (d and e) if v else (d or e)
        authorized = identity and entitlement
        release = authorized and f
        out = {"identity":identity,"entitlement":entitlement,"authorized":authorized,"release":release,"logged":release and g}
    elif family == SMOKE_RULE:
        out = {"left":a and c,"middle":b and d,"right":e and f,"ready":a and b and c and d and e and f}
    else:
        raise ValueError("Unregistered Rule oracle")
    return sorted(k for k,value in {**out,"audit":h}.items() if value)


def _rule(family,variant):
    description,declarations = _rule_spec(family,variant)
    correct = [{"id":f"r{i}","if":antecedents,"then":consequence} for i,(antecedents,consequence) in enumerate(declarations)]
    correct.append({"id":"audit_rule","if":["h"],"then":"audit"})
    starter = deepcopy(correct)
    starter[0]["if"] = ["a"] if family == RULE_FINAL[3] else ["h"]
    # A second interaction bug prevents a one-line local repair being sufficient.
    starter[-2]["if"] = [starter[0]["then"]]
    identifier = f"v17-rule-final-{family}-v{variant}"
    facts = [[letter for letter,present in zip("abcdefgh",bits) if present]
             for bits in itertools.product((False,True),repeat=8)]
    facts = [facts[-1],facts[0],*facts[1:-1]]
    cases = [{"id":f"{identifier}-c{i}","facts":x,"expected":_rule_oracle(family,variant,x)} for i,x in enumerate(facts)]
    derived = sorted({r["then"] for r in correct})
    return NativeAdapter({"id":identifier,"domain":"rule_reasoning","split":"final","family":family,
        "cluster_id":"v17-rule-"+family,"contract":_contract(family == RULE_FINAL[3]),
        "prompt":description+" Repair the editable rules and return the COMPLETE rule list with all original ids, "
                 "including protected audit_rule unchanged. Every requested derived fact is checked.",
        "rules":starter,"editable_rule_ids":[r["id"] for r in correct[:-1]],
        "vocabulary":sorted(set("abcdefgh")|set(derived)),"initial_facts":facts[0],"answer_facts":derived,
        "public_cases":cases[:2],"hidden_cases":cases[2:],"reference_artifact":{"rules":correct},
        "metadata":_metadata("rule_reasoning",family,variant,"final",family == RULE_FINAL[3])})


def build_panel(smoke=False):
    if type(smoke) is not bool:
        raise ValueError("Explicit smoke boolean required")
    if smoke:
        return {"source":[_coding(SMOKE_CODE[0],0,"development")],
                "source_extra":[_coding(SMOKE_CODE[1],0,"development")],
                "transfer":[_sheet(SMOKE_SHEET[0],0,"development")],
                "confirmation":[_coding(SMOKE_CODE[2],0,"calibration"),_coding(SMOKE_CODE[4],0,"calibration"),
                                _sheet(SMOKE_SHEET[1],0,"calibration"),_sheet(SMOKE_SHEET[3],0,"calibration")],
                "final":[_coding(SMOKE_CODE[3],0,"final"),_sheet(SMOKE_SHEET[2],0,"final"),_rule(SMOKE_RULE,0)]}
    return {"source":[_coding(f,v,"development") for f in CODE_SOURCE for v in (0,1)],
            "source_extra":[_coding(f,v,"development") for f in CODE_EXTRA for v in (0,1)],
            "transfer":[_sheet(f,v,"development") for f in SHEET_TRANSFER for v in (0,1)],
            "confirmation":[*[_coding(f,v,"calibration") for f in CODE_CONFIRM for v in (0,1)],
                            *[_sheet(f,v,"calibration") for f in SHEET_CONFIRM for v in (0,1)]],
            "final":[*[_coding(f,v,"final") for f in CODE_FINAL for v in (0,1)],
                     *[_sheet(f,v,"final") for f in SHEET_FINAL for v in (0,1)],
                     *[_rule(f,v) for f in RULE_FINAL for v in (0,1)]]}


def artifacts(adapter):
    row = payload(adapter)
    if row["metadata"]["version"] != VERSION:
        raise ValueError("V17 authored task required")
    if adapter.domain == "coding":
        return {"reference":deepcopy(row["reference_files"]),"starter":deepcopy(row["files"])}
    starter = {"formulas":{c:row["formulas"][c] for c in row["editable_cells"]}} if adapter.domain == "spreadsheet" else {"rules":row["rules"]}
    return {"reference":deepcopy(row["reference_artifact"]),"starter":deepcopy(starter)}


def manifest(panel):
    def item(a):
        row = payload(a)
        return {"task_id":row["id"],"task_hash":digest(row),"domain":a.domain,"split":row["split"],
                "family":row["family"],"cluster_id":row["cluster_id"],"variant":row["metadata"]["variant"],
                "mechanism_cell":row["metadata"]["mechanism_cell"]}
    return {"version":VERSION,"synthetic_not_public_benchmark":True,
            **{phase:[item(a) for a in group] for phase,group in panel.items()}}


panel_manifest = manifest


def self_check(panel):
    """Offline reference/starter checks in the existing isolated executors."""
    from skillopt.coevolution_v8.feedback_study import evaluate, score

    seen_ids, family_partitions, rows = set(),{},[]
    for phase,group in panel.items():
        expected_split = "final" if phase == "final" else "calibration" if phase == "confirmation" else "development"
        for adapter in group:
            row = payload(adapter)
            if row["id"] in seen_ids or row["split"] != expected_split or row["metadata"]["partition"] != expected_split:
                raise ValueError("Task duplication or incorrect split")
            seen_ids.add(row["id"])
            family = row["cluster_id"]
            if family in family_partitions and family_partitions[family] != phase:
                raise ValueError("Structural family leaks between partitions")
            family_partitions[family] = phase
            controls = {}
            for name,artifact in artifacts(adapter).items():
                evaluation = evaluate(adapter,artifact,public_only=False)
                result = score(adapter,artifact,evaluation)
                if not result["oracle_available"] or result["all_attempt_success"] != int(name == "reference"):
                    raise ValueError("Authored oracle/reference mismatch: "+row["id"]+"/"+name+" "+str(result)+" "+str(evaluation)[:1500])
                controls[name] = {"available":True,"passed":bool(result["all_attempt_success"])}
            rows.append({"task_id":row["id"],"phase":phase,"controls":controls})
    report = {"version":VERSION,"all_checked":True,"checked_tasks":len(rows),"records":rows,
              "model_api_calls":0,"reference_execution":"existing_os_sandbox_only",
              "internal_consistency_not_model_efficacy":True}
    json.dumps(report,allow_nan=False)
    return report
