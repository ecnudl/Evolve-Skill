"""New authored V15 mechanism stream, with host-defined independent oracles.

This is a bounded synthetic study, not a public benchmark or IID population.
Reference source is NEVER executed on the host: only the existing OS sandbox.
Models may propose legal inputs, never expected values or executable assertions.
Development, calibration, final and engineering-smoke structures are disjoint.
"""

from __future__ import annotations

import itertools
import json
import math
from copy import deepcopy
from dataclasses import replace
from textwrap import dedent

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v6.native import NativeAdapter
from skillopt.coevolution_v8.feedback_study import public_task as _public
from skillopt.validator_pilot.api import digest

VERSION = "v15-authored-lagged-mechanism-stream-v1"
ENTRY = "import logic\n\ndef solve(data):\n    return logic.run(data)\n"
CODING_DEV = ("exclusive-prefix-products", "strict-increase-streak", "stable-top-k-indices", "prefix-lower-medians")
CODING_CAL = ("pair-inversion-count", "shortest-distinct-cover", "cyclic-left-rotation")
CODING_FINAL = ("earliest-palindromic-slice", "target-subarray-count", "circular-nonadjacent-profit",
                "minimum-forward-jumps", "suffix-minimum-indices", "kth-missing-positive")
SHEET_DEV = ("reaction-braking-budget", "mixed-solution-spill", "trapezoid-flow-value", "leadtime-reorder-gap")
SHEET_CAL = ("signed-buoyancy-force", "heat-capacity-equilibrium", "two-date-discounted-balance")
SHEET_FINAL = ("pulley-work-efficiency", "thin-lens-image", "two-layer-thermal-flow",
               "axle-moment-balance", "growing-three-payment-value", "battery-pack-duration")
RULE_FINAL = ("twofactor-review-composition", "authorized-exception-release", "dual-origin-endorsement",
              "pair-certificate-quorum", "keyed-cycle-bridge", "new-credential-overlap-policy")
SMOKE_CODING = ("smoke-alternating-checksum", "smoke-pair-product-total", "smoke-adjacent-equality-count")
SMOKE_SHEET = ("smoke-scaled-perimeter-price", "smoke-labor-overhead-tax", "smoke-coordinate-translation")
SMOKE_RULE = "smoke-disjoint-payment-ack"
MAX_PROBES = 4


def _contract(replacement=False):
    return {"change_scope": "full_replacement" if replacement else "partial_update",
            "supersedes_old_policy": replacement,
            "preserve_obligations": ["Keep every noneditable interface and protected audit unchanged.",
                                     "Never mutate input data; obey the declared runtime."]}


def _metadata(domain, family, split):
    return {"version": VERSION, "domain": domain, "structural_family": family, "partition": split,
            "authorship": "new_host_authored_synthetic_not_public_benchmark",
            "historical_task_assets_used": False, "smoke_only": family.startswith("smoke-"),
            "independence_unit": "authored_structure_not_case_or_repeat",
            "independence_is_design_assumption_not_population_guarantee": True,
            "oracle": "separately_written_host_arithmetic_or_enumeration_not_reference_execution",
            "obligations": [
                {"id": "behavior", "kind": "requested_behavior", "statement": "Implement the exact public task behavior, including its boundaries and ordering."},
                {"id": "preservation", "kind": "input_preservation", "statement": "Preserve original input values and every explicitly protected interface/audit."}]}


def _object(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _number_schema(low, high, *, integer=False):
    return {"type": "integer" if integer else "number", "minimum": low, "maximum": high}


def _coding_schema(family):
    lower = 0 if family == CODING_FINAL[3] else -20
    return _object({"values": {"type": "array", "items": _number_schema(lower, 20, integer=True), "maxItems": 8},
                    "k": _number_schema(1 if family == CODING_FINAL[5] else 0, 12, integer=True)})


# description, original reference body, one independently authored starter fault
_CODE = {
    CODING_DEV[0]: ("Return one product per index, using ONLY values strictly BEFORE that index. The first product is 1; zero and negative factors retain their arithmetic meaning. k is unused.",
        "result = []\nproduct = 1\nfor x in values:\n    result.append(product)\n    product *= x", ("result.append(product)", "result.append(product*x)")),
    CODING_DEV[1]: ("Return the length of the longest contiguous STRICTLY increasing run. Equal neighbors break a run; empty input gives 0. k is unused.",
        "result = 0\nlength = 0\nprevious = None\nfor x in values:\n    length = length+1 if previous is not None and previous < x else 1\n    result = max(result,length)\n    previous = x", ("previous < x", "previous <= x")),
    CODING_DEV[2]: ("Return at most k ORIGINAL indices with largest values, sorted by descending value and then increasing index. k=0 gives []; k greater than length returns all indices. Do not reorder the input.",
        "result = sorted(range(len(values)),key=lambda i: (-values[i],i))[:k]", ("(-values[i],i)", "(-values[i],-i)")),
    CODING_DEV[3]: ("For every nonempty prefix return its LOWER median. Sort that prefix conceptually; for even size choose the smaller middle value, not the average or upper middle. k is unused.",
        "result = []\nordered = []\nfor x in values:\n    ordered.append(x)\n    ordered.sort()\n    result.append(ordered[(len(ordered)-1)//2])", ("(len(ordered)-1)//2", "len(ordered)//2")),
    CODING_CAL[0]: ("Count index pairs i<j with values[i] STRICTLY GREATER than values[j]. Equal values are not inversions. k is unused.",
        "result = 0\nfor i,x in enumerate(values):\n    for y in values[i+1:]:\n        if x > y:\n            result += 1", ("x > y", "x >= y")),
    CODING_CAL[1]: ("Return the smallest length of a contiguous interval containing EVERY distinct value appearing anywhere in the input. Multiplicity is irrelevant; empty input gives 0. k is unused.",
        "needed = len(set(values))\ncounts = {}\nleft = 0\nresult = len(values)\nfor right,x in enumerate(values):\n    counts[x] = counts.get(x,0)+1\n    while len(counts) == needed:\n        result = min(result,right-left+1)\n        old = values[left]\n        counts[old] -= 1\n        if counts[old] == 0:\n            del counts[old]\n        left += 1", ("right-left+1", "right-left+2")),
    CODING_CAL[2]: ("Rotate the sequence LEFT by k positions with wraparound. Reduce k modulo length; empty input stays empty. Return a new list without mutating values.",
        "shift = k % len(values) if values else 0\nresult = values[shift:]+values[:shift]", ("k % len(values) if values else 0", "k")),
    CODING_FINAL[0]: ("Return [start,length] of the longest contiguous palindrome, choosing the EARLIEST start on equal lengths. Empty input returns [0,0]. k is unused.",
        "result = [0,0]\nfor center in range(2*len(values)-1):\n    left = center//2\n    right = (center+1)//2\n    while left >= 0 and right < len(values) and values[left] == values[right]:\n        length = right-left+1\n        if length > result[1] or length == result[1] and left < result[0]:\n            result = [left,length]\n        left -= 1\n        right += 1", ("left < result[0]", "left > result[0]")),
    CODING_FINAL[1]: ("Count NONEMPTY contiguous subarrays whose signed sum equals k. Overlapping intervals count separately; zero and negative values are legal.",
        "counts = {0:1}\ncurrent = 0\nresult = 0\nfor x in values:\n    current += x\n    result += counts.get(current-k,0)\n    counts[current] = counts.get(current,0)+1", ("counts = {0:1}", "counts = {}")),
    CODING_FINAL[2]: ("Choose nonadjacent positions on a CIRCLE to maximize signed profit. First and last are adjacent when there are at least two positions. Taking nothing is allowed; a single position is not adjacent to itself. k is unused.",
        "def line(items):\n    before = 0\n    best = 0\n    for x in items:\n        before,best = best,max(best,before+x)\n    return best\nresult = max(0,values[0]) if len(values) == 1 else max(line(values[:-1]),line(values[1:]))", ("max(line(values[:-1]),line(values[1:]))", "line(values)")),
    CODING_FINAL[3]: ("Each nonnegative value is the MAXIMUM forward jump length at that index. Starting at index 0, return the fewest jumps reaching the last index, or -1 if unreachable. Empty or singleton input needs 0 jumps. k is unused.",
        "result = 0\nend = 0\nreach = 0\nfor i in range(max(0,len(values)-1)):\n    reach = max(reach,i+values[i])\n    if i == end:\n        if reach <= i:\n            result = -1\n            break\n        result += 1\n        end = reach", ("reach <= i", "reach < i")),
    CODING_FINAL[4]: ("At each position return the ORIGINAL index of the minimum value in that suffix, breaking ties by earliest index. k is unused.",
        "result = [0]*len(values)\nbest = len(values)-1\nfor i in range(len(values)-1,-1,-1):\n    if values[i] <= values[best]:\n        best = i\n    result[i] = best", ("values[i] <= values[best]", "values[i] < values[best]")),
    CODING_FINAL[5]: ("Return the kth missing POSITIVE integer, starting rank at k=1. Ignore repeated values, zero and negatives. Do not assume sorted input.",
        "present = set(values)\nnumber = 0\nremaining = k\nwhile remaining:\n    number += 1\n    if number not in present:\n        remaining -= 1\nresult = number", ("number = 0", "number = -1")),
    SMOKE_CODING[0]: ("Return the alternating signed sum values[0]-values[1]+values[2]-... . Empty input gives 0; k is unused.",
        "result = 0\nsign = 1\nfor x in values:\n    result += sign*x\n    sign = -sign", ("sign = -sign", "sign = 1")),
    SMOKE_CODING[1]: ("Return the sum of products values[i]*values[j] over every unordered pair i<j. Do not include self-products; k is unused.",
        "result = (sum(values)*sum(values)-sum(x*x for x in values))//2", ("//2", "//1")),
    SMOKE_CODING[2]: ("Count adjacent equal pairs. A run of length n contributes n-1, not n or one. k is unused.",
        "result = sum(1 for i in range(1,len(values)) if values[i] == values[i-1])", ("values[i] == values[i-1]", "values[i] != values[i-1]")),
}


def _coding_inputs(family):
    values = [[3,1,2],[-2,1,-1],[],[0],[2,2,1,2],[1,0,-1,1],[4,-3,4,-3,4],[0,0,0]]
    ks = [2,1,0,0,4,2,7,0]
    if family == CODING_CAL[2]:
        ks = [1,2,4,0,7,8,11,5]
    if family == CODING_FINAL[3]:
        values = [[2,3,1,1,4],[1,0,2],[],[0],[0,2],[1,1,1],[3,0,0,0],[2,0,0,1]]
    if family == CODING_FINAL[0]:
        values = [[1,2,1,4],[3,2,2,3],[],[0],[1,2,3],[2,2,1,2,2],[1,2,1,3,1],[0,0,0]]
    if family == CODING_FINAL[5]:
        ks = [1,2,1,3,4,2,7,1]
    return [{"values": value,"k": k} for value,k in zip(values,ks)]


def _code_oracle(family, data):
    a,k = data["values"],data["k"]
    if family == CODING_DEV[0]:
        result = [math.prod(a[:i]) for i in range(len(a))]
    elif family == CODING_DEV[1]:
        result = max([0]+[j-i for i in range(len(a)) for j in range(i+1,len(a)+1)
                          if all(a[t] < a[t+1] for t in range(i,j-1))])
    elif family == CODING_DEV[2]:
        ranked = sorted(((-x,i) for i,x in enumerate(a)))
        result = [i for _,i in ranked[:k]]
    elif family == CODING_DEV[3]:
        result = [next(x for x in sorted(set(a[:i])) if sum(y <= x for y in a[:i]) >= (i+1)//2)
                  for i in range(1,len(a)+1)]
    elif family == CODING_CAL[0]:
        result = sum(a[i] > a[j] for i,j in itertools.combinations(range(len(a)),2))
    elif family == CODING_CAL[1]:
        result = min([len(a)]+[j-i for i in range(len(a)) for j in range(i+1,len(a)+1) if set(a[i:j]) == set(a)])
    elif family == CODING_CAL[2]:
        result = [a[(i+k)%len(a)] for i in range(len(a))]
    elif family == CODING_FINAL[0]:
        spans = [(j-i,-i) for i in range(len(a)) for j in range(i+1,len(a)+1) if a[i:j] == a[i:j][::-1]]
        length,negative_start = max(spans,default=(0,0))
        result = [-negative_start,length]
    elif family == CODING_FINAL[1]:
        result = sum(sum(a[i:j]) == k for i in range(len(a)) for j in range(i+1,len(a)+1))
    elif family == CODING_FINAL[2]:
        choices = [sum(x for x,take in zip(a,mask) if take) for mask in itertools.product((False,True),repeat=len(a))
                   if len(a) < 2 or not any(mask[i] and mask[(i+1)%len(a)] for i in range(len(a)))]
        result = max(choices,default=0)
    elif family == CODING_FINAL[3]:
        distances = [0]+[len(a)+1]*max(0,len(a)-1)
        for j in range(1,len(a)):
            distances[j] = min([len(a)+1]+[distances[i]+1 for i in range(j) if i+a[i] >= j])
        result = distances[-1] if distances[-1] <= len(a) else -1
    elif family == CODING_FINAL[4]:
        result = [min(range(i,len(a)),key=lambda j:(a[j],j)) for i in range(len(a))]
    elif family == CODING_FINAL[5]:
        result = [x for x in range(1,33) if x not in a][k-1]
    elif family == SMOKE_CODING[0]:
        result = sum(a[::2])-sum(a[1::2])
    elif family == SMOKE_CODING[1]:
        result = sum(x*y for x,y in itertools.combinations(a,2))
    elif family == SMOKE_CODING[2]:
        result = len(a)-1-sum(x != y for x,y in zip(a,a[1:])) if a else 0
    else:
        raise ValueError("Unregistered Coding oracle")
    return {"result":result,"input_count":len(a),"input_sum":sum(a)}


def _coding(family, split):
    description,body,fault = _CODE[family]
    source = "def run(data):\n    values,k = data['values'],data['k']\n"
    source += "".join("    "+line+"\n" for line in dedent(body).splitlines())
    source += "    return {'result':result,'input_count':len(values),'input_sum':sum(values)}\n"
    if source.count(fault[0]) != 1:
        raise ValueError("Ambiguous authored fault")
    identifier = f"repo-v15-{split}-{family}"
    cases = [{"label":f"{identifier}-case{i}","input":value,"expected":_code_oracle(family,value),
              "exception":None,"public":i<2,"dimension":"requested_behavior"}
             for i,value in enumerate(_coding_inputs(family))]
    metadata = _metadata("coding",family,split)
    metadata["contract"] = _contract()
    return CodingAdapter(RepoTask(id=identifier,split=split,family=family,cluster_id="v15-coding-"+family,
        prompt="Repair logic.py. "+description+" Return exactly result, input_count, input_sum in a dict. "
               "The audits are the ORIGINAL input length and SIGNED sum. Keep api.py unchanged; never mutate data.",
        files={"api.py":ENTRY,"logic.py":source.replace(*fault,1)},reference_files={"api.py":ENTRY,"logic.py":source},
        editable_paths=["logic.py"],input_domain=_coding_schema(family),public_cases=cases[:2],private_cases=cases[2:],metadata=metadata))


# Public algebraic specifications. These run in the explicitly documented
# bounded formula DSL, not Excel/LibreOffice. (description, graph, fault, bounds)
_SHEET = {
    SHEET_DEV[0]: ("A1 speed in km/h, A2 reaction seconds, A3 positive deceleration in m/s^2, A4 available meters, A5 price per stopping meter, A6 audit scale. B1 speed in m/s; B2 reaction distance; B3 braking distance speed^2/(2*deceleration); B4 SIGNED distance remaining after reaction and braking. C1 stopping-distance cost; C2 reconciles remaining plus both distances minus available meters, times A6.",
        {"B1":"=A1/3.6","B2":"=B1*A2","B3":"=B1*B1/(2*A3)","B4":"=A4-B2-B3","C1":"=(B2+B3)*A5","C2":"=(B4+B2+B3-A4)*A6"},
        ("B1","=A1"),[(0,100),(0,5),(1,10),(0,100),(0,5),(0,3)]),
    SHEET_DEV[1]: ("A1/A2 solution volumes; A3/A4 solute fractions in [0,1]; A5 spilled volume after COMPLETE mixing; A6 audit scale. B1 mixed volume; B2 total solute before spill; B3 uniform solute fraction, or 0 for zero volume; B4 retained solute after spill limited to available volume. C1=B4; C2 retained solute plus spilled solute, times A6. Spill is nonnegative and cannot remove more than the mixture.",
        {"B1":"=A1+A2","B2":"=A1*A3+A2*A4","B3":"=IF(B1==0,0,B2/B1)","B4":"=MAX(0,B1-A5)*B3","C1":"=B4","C2":"=(B4+MIN(A5,B1)*B3)*A6"},
        ("B3","=(A3+A4)/2"),[(0,20),(0,10),(0,1),(0,1),(0,25),(0,3)]),
    SHEET_DEV[2]: ("A1/A2 SIGNED starting/ending flow rates in liters/second, varying linearly; A3 elapsed minutes; A4 mass density kg/liter; A5 value per kg; A6 audit scale. B1 average signed rate; B2 signed integrated liters; B3 signed mass; B4 signed value. C1=B4; C2 volume/60 minus average rate times minutes, times A6. Negative net flow must not be clamped.",
        {"B1":"=(A1+A2)/2","B2":"=B1*A3*60","B3":"=B2*A4","B4":"=B3*A5","C1":"=B4","C2":"=(B2/60-B1*A3)*A6"},
        ("B2","=MAX(0,B1*A3)"),[(-10,10),(-20,20),(0,10),(0,5),(0,10),(0,3)]),
    SHEET_DEV[3]: ("A1 daily demand, A2 lead-time days, A3 safety quantity, A4 on-hand inventory, A5 on-order inventory, A6 audit scale; all nonnegative. B1 lead-time demand; B2 reorder threshold including safety; B3 inventory POSITION including on-order stock; B4 additional order needed, floored at zero. C1=B4; C2 threshold minus lead-time demand minus safety, times A6. Do not order already in-transit stock again.",
        {"B1":"=A1*A2","B2":"=B1+A3","B3":"=A4+A5","B4":"=MAX(0,B2-B3)","C1":"=B4","C2":"=(B2-B1-A3)*A6"},
        ("B3","=A4"),[(0,10),(0,10),(0,20),(0,50),(0,50),(0,3)]),
    SHEET_CAL[0]: ("A1 mass, A2 displaced volume, A3 fluid density, A4 positive gravitational acceleration, A5 audit scale, A6 SIGNED external-force offset. B1 downward weight; B2 upward buoyancy; B3 SIGNED downward net force; B4 net force plus offset. C1=B4; C2 weight minus buoyancy minus net force, times A5. A floating object may have negative net force.",
        {"B1":"=A1*A4","B2":"=A2*A3*A4","B3":"=B1-B2","B4":"=B3+A6","C1":"=B4","C2":"=(B1-B2-B3)*A5"},
        ("B3","=MAX(0,B1-B2)"),[(0,100),(0,10),(0,10),(1,10),(0,3),(-10,10)]),
    SHEET_CAL[1]: ("A1/A2 nonnegative masses, A3/A4 positive specific heat capacities, A5/A6 signed temperatures. No heat loss or phase change. B1/B2 total heat capacities; B3 sum of heat-capacity times temperature; B4 equilibrium temperature, 0 if total heat capacity is zero. C1=B4; C2=B3. Equal mass does not imply equal heat capacity.",
        {"B1":"=A1*A3","B2":"=A2*A4","B3":"=B1*A5+B2*A6","B4":"=IF(B1+B2==0,0,B3/(B1+B2))","C1":"=B4","C2":"=B3"},
        ("B4","=(A5+A6)/2"),[(0,20),(0,10),(1,5),(1,10),(-20,100),(-10,80)]),
    SHEET_CAL[2]: ("A1 cash due in one period, A2 cash due in two periods, A3 nonnegative per-period discount rate, A4 current liability, A5 audit scale, A6 signed current credit. B1 one-period factor 1+rate; B2 one-period present value; B3 TWO-period present value; B4 sum of both present values minus liability plus credit. C1=B4; C2 present values times A5. Use one discount factor per period, not simple averaging.",
        {"B1":"=1+A3","B2":"=A1/B1","B3":"=A2/(B1*B1)","B4":"=B2+B3-A4+A6","C1":"=B4","C2":"=(B2+B3)*A5"},
        ("B3","=A2/B1"),[(0,100),(0,100),(0,1),(0,50),(0,3),(-10,10)]),
    SHEET_FINAL[0]: ("A1 load mass, A2 gravity, A3 lift height, A4 positive number of supporting rope branches, A5 efficiency in (0,1], A6 price per work unit. B1 load force; B2 pull force=load/(branches*efficiency); B3 pull distance=height*branches; B4 input work=pull force*pull distance. C1 work cost; C2 input work times efficiency minus ideal lifting work. Never divide both force and distance by branch count.",
        {"B1":"=A1*A2","B2":"=B1/(A4*A5)","B3":"=A3*A4","B4":"=B2*B3","C1":"=B4*A6","C2":"=B4*A5-B1*A3"},
        ("B3","=A3/A4"),[(0,20),(1,10),(0,10),(1,8),(0.1,1),(0,5)]),
    SHEET_FINAL[1]: ("A1 positive focal distance, A2 positive object distance, A3 signed object height, A4 image display scale, A5 audit scale, A6 signed display offset. B1 object distance minus focal distance; B2 signed image distance=focal*object/B1, defined as 0 at B1=0; B3 magnification=-image/object; B4 signed image height. C1=B4*A4+A6; C2=B1*A5. Virtual images retain negative distance; the exact focus case uses the stated zero sentinel.",
        {"B1":"=A2-A1","B2":"=IF(B1==0,0,A1*A2/B1)","B3":"=-B2/A2","B4":"=B3*A3","C1":"=B4*A4+A6","C2":"=B1*A5"},
        ("B2","=IF(B1<=0,0,A1*A2/B1)"),[(1,20),(1,20),(-10,10),(0,5),(0,3),(-5,5)]),
    SHEET_FINAL[2]: ("A1/A3 layer thicknesses, A2/A4 positive conductivities, A5 positive common area, A6 signed temperature difference. B1/B2 layer thermal resistances=thickness/(conductivity*area); B3 series resistance; B4 signed heat flow=temperature difference/resistance, defined as 0 when resistance is zero. C1=B4; C2 flow times total resistance. Layers add resistance, not conductance.",
        {"B1":"=A1/(A2*A5)","B2":"=A3/(A4*A5)","B3":"=B1+B2","B4":"=IF(B3==0,0,A6/B3)","C1":"=B4","C2":"=B4*(B1+B2)"},
        ("B3","=MAX(B1,B2)"),[(0,10),(1,10),(0,5),(1,8),(1,20),(-50,50)]),
    SHEET_FINAL[3]: ("A1 positive support span; A2/A4 signed forces applied at distances A3/A5 from the left support (distances may extend beyond the span); A6 audit scale. B1 total moment about left; B2 right reaction=moment/span; B3 total applied force; B4 left reaction=total-right. C1=B4; C2 sum of reactions minus total force, times A6. Keep signed reactions; loads beyond a support are legal.",
        {"B1":"=A2*A3+A4*A5","B2":"=B1/A1","B3":"=A2+A4","B4":"=B3-B2","C1":"=B4","C2":"=(B2+B4-B3)*A6"},
        ("B4","=MAX(0,B3-B2)"),[(1,20),(-20,50),(0,30),(-10,30),(0,30),(0,3)]),
    SHEET_FINAL[4]: ("A1 first payment, A2 nonnegative growth rate, A3 nonnegative discount rate, A4 tax fraction [0,1], A5 current fee, A6 audit scale. Three payments occur at ends of periods 1,2,3: P, P*(1+growth), P*(1+growth)^2. B1/B2/B3 their present values, respectively discounted 1,2,3 periods. B4 sum after tax minus fee. C1=B4; C2 pretax present-value sum times A6. The fee is not discounted or taxed.",
        {"B1":"=A1/(1+A3)","B2":"=A1*(1+A2)/((1+A3)*(1+A3))","B3":"=A1*(1+A2)*(1+A2)/((1+A3)*(1+A3)*(1+A3))","B4":"=(B1+B2+B3)*(1-A4)-A5","C1":"=B4","C2":"=(B1+B2+B3)*A6"},
        ("B4","=(B1+B2+B3-A5)*(1-A4)"),[(0,100),(0,1),(0,1),(0,1),(0,20),(0,3)]),
    SHEET_FINAL[5]: ("A1 cell voltage, A2 cell amp-hours, A3 positive series-cell factor, A4 positive parallel-string factor, A5 usable fraction [0,1], A6 load power. Treat factors as supplied nonnegative numeric scaling quantities. B1 pack voltage scales with series only; B2 amp-hours scale with parallel only; B3 usable watt-hours; B4 duration=B3/load, with -1 when load is zero. C1=B3; C2 nominal watt-hours before usable fraction. Zero load always gives sentinel -1, including an empty battery.",
        {"B1":"=A1*A3","B2":"=A2*A4","B3":"=B1*B2*A5","B4":"=IF(A6==0,-1,B3/A6)","C1":"=B3","C2":"=B1*B2"},
        ("B2","=A2*A3*A4"),[(0,10),(0,20),(1,8),(1,6),(0,1),(0,100)]),
    SMOKE_SHEET[0]: ("A1/A2/A3 side lengths, A4 scale, A5 price per length, A6 signed rebate. B1 perimeter; B2 scaled perimeter; B3 gross price; B4 gross minus rebate. C1=B4; C2 scaled perimeter minus original perimeter times scale. No lower clamp is required.",
        {"B1":"=A1+A2+A3","B2":"=B1*A4","B3":"=B2*A5","B4":"=B3-A6","C1":"=B4","C2":"=B2-B1*A4"},
        ("B2","=B1+A4"),[(0,10),(0,10),(0,10),(0,5),(0,5),(-10,10)]),
    SMOKE_SHEET[1]: ("A1 hours, A2 hourly rate, A3 overhead, A4 tax fraction, A5 rebate, A6 audit scale. B1 labor cost; B2 labor plus overhead; B3 tax on B2; B4 B2+tax-rebate. C1=B4; C2 labor cost times A6. Overhead is taxable; rebate is applied after tax.",
        {"B1":"=A1*A2","B2":"=B1+A3","B3":"=B2*A4","B4":"=B2+B3-A5","C1":"=B4","C2":"=B1*A6"},
        ("B3","=B1*A4"),[(0,10),(0,20),(0,30),(0,1),(0,10),(0,3)]),
    SMOKE_SHEET[2]: ("A1/A2 signed x/y coordinates, A3/A4 signed translations, A5 scale, A6 audit scale. B1/B2 translated coordinates; B3/B4 those coordinates scaled by A5. C1 scaled coordinate sum; C2 translated coordinate sum times A6. Translation happens before scaling and signs remain unchanged.",
        {"B1":"=A1+A3","B2":"=A2+A4","B3":"=B1*A5","B4":"=B2*A5","C1":"=B3+B4","C2":"=(B1+B2)*A6"},
        ("B1","=MAX(0,A1+A3)"),[(-20,20),(-20,20),(-10,10),(-10,10),(0,5),(0,3)]),
}


def _sheet_schema(family):
    return _object({f"A{i+1}":_number_schema(*bounds) for i,bounds in enumerate(_SHEET[family][3])})


def _sheet_inputs(family):
    bounds = _SHEET[family][3]
    # Eight predetermined substitutions; no sampling or selection by model results.
    patterns = [[0.25]*6,[0.75]*6,[0]*6,[1]*6,[0,1,0,1,0,1],[1,0,1,0,1,0],
                [0.2,0.8,0.4,0.6,0.1,0.9],[0.9,0.1,0.6,0.2,0.8,0.4]]
    rows = [{f"A{i+1}":low+(high-low)*fraction for i,((low,high),fraction) in enumerate(zip(bounds,p))} for p in patterns]
    if family == SHEET_CAL[2]:
        rows[0]["A3"] = rows[1]["A3"] = 0
    return rows


def _sheet_oracle(family, a):
    x,y,z,u,v,w = (a[f"A{i}"] for i in range(1,7))
    if family == SHEET_DEV[0]:
        speed = x*5/18
        reaction,braking = speed*y,speed**2/(2*z)
        b,c = [speed,reaction,braking,u-reaction-braking],[(reaction+braking)*v,0]
    elif family == SHEET_DEV[1]:
        volume,solute = x+y,x*z+y*u
        fraction = solute/volume if volume else 0
        retained = solute*(1-min(v,volume)/volume) if volume else 0
        b,c = [volume,solute,fraction,retained],[retained,solute*w]
    elif family == SHEET_DEV[2]:
        volume = (x+y)*z*30
        b,c = [(x+y)/2,volume,volume*u,volume*u*v],[volume*u*v,0]
    elif family == SHEET_DEV[3]:
        lead,position = x*y,u+v
        gap = lead+z-position
        order = gap if gap > 0 else 0
        b,c = [lead,lead+z,position,order],[order,0]
    elif family == SHEET_CAL[0]:
        weight,buoyancy = x*u,y*z*u
        net = (x-y*z)*u
        b,c = [weight,buoyancy,net,net+w],[net+w,0]
    elif family == SHEET_CAL[1]:
        capacities = (x*z,y*u)
        heat = sum(q*t for q,t in zip(capacities,(v,w)))
        temp = heat/sum(capacities) if sum(capacities) else 0
        b,c = [*capacities,heat,temp],[temp,heat]
    elif family == SHEET_CAL[2]:
        discount = 1/(1+z)
        first,second = x*discount,y*discount**2
        b,c = [1+z,first,second,first+second-u+w],[first+second-u+w,(first+second)*v]
    elif family == SHEET_FINAL[0]:
        force,distance = x*y/(u*v),z*u
        work = x*y*z/v
        b,c = [x*y,force,distance,work],[work*w,0]
    elif family == SHEET_FINAL[1]:
        difference = y-x
        image = 1/(1/x-1/y) if difference else 0
        magnification = -image/y
        b,c = [difference,image,magnification,z*magnification],[z*magnification*u+w,difference*v]
    elif family == SHEET_FINAL[2]:
        resistance = x/y/v + z/u/v
        flow = w/resistance if resistance else 0
        b,c = [x/y/v,z/u/v,resistance,flow],[flow,w if resistance else 0]
    elif family == SHEET_FINAL[3]:
        moment,total = y*z+u*v,y+u
        right = moment/x
        b,c = [moment,right,total,total-right],[total-right,0]
    elif family == SHEET_FINAL[4]:
        present = [x*(1+y)**i/(1+z)**(i+1) for i in range(3)]
        value = sum(present)-sum(present)*u-v
        b,c = [*present,value],[value,sum(present)*w]
    elif family == SHEET_FINAL[5]:
        voltage,capacity = x*z,y*u
        energy = x*y*z*u*v
        b,c = [voltage,capacity,energy,energy/w if w else -1],[energy,x*y*z*u]
    elif family == SMOKE_SHEET[0]:
        perimeter = sum((x,y,z))
        scaled = perimeter*u
        b,c = [perimeter,scaled,scaled*v,scaled*v-w],[scaled*v-w,0]
    elif family == SMOKE_SHEET[1]:
        labor,taxable = x*y,x*y+z
        total = taxable*(1+u)-v
        b,c = [labor,taxable,taxable*u,total],[total,labor*w]
    elif family == SMOKE_SHEET[2]:
        translated = (x+z,y+u)
        b,c = [*translated,translated[0]*v,translated[1]*v],[sum(translated)*v,sum(translated)*w]
    else:
        raise ValueError("Unregistered Spreadsheet oracle")
    return {**{f"B{i+1}":value for i,value in enumerate(b)},"C1":c[0],"C2":c[1]}


def _sheet(family, split):
    description,formulas,fault,_ = _SHEET[family]
    identifier = f"v15-sheet-{split}-{family}"
    cases = [{"id":f"{identifier}-case{i}","overrides":value,"expected":_sheet_oracle(family,value)}
             for i,value in enumerate(_sheet_inputs(family))]
    metadata = _metadata("spreadsheet",family,split)
    metadata["input_schema"] = _sheet_schema(family)
    return NativeAdapter({"id":identifier,"domain":"spreadsheet","split":split,"family":family,
        "cluster_id":"v15-sheet-"+family,"contract":_contract(),
        "prompt":"Repair the editable B1..B4 formulas. "+description+
                 " All four intermediates and both protected C1/C2 audits are checked under new legal inputs. "
                 "This is a bounded numeric DSL, NOT Excel. Every formula starts with =; inside IF use == for equality, "
                 "not a single =. Example =IF(A1==0,0,A2/A1). Do not change C1/C2 or inputs.",
        "inputs":deepcopy(cases[0]["overrides"]),"formulas":{**formulas,fault[0]:fault[1]},
        "editable_cells":["B1","B2","B3","B4"],"answer_cell":"C1",
        "reference_artifact":{"formulas":{k:formulas[k] for k in ("B1","B2","B3","B4")}},
        "public_cases":cases[:2],"hidden_cases":cases[2:],"metadata":metadata})


_RULES = {
    RULE_FINAL[0]: ("review_a needs a AND b; review_b needs c AND d. reviewed follows from EITHER review. transport follows from e AND f, or independently g. ready needs reviewed AND transport. audit depends ONLY on h.",
        [(["a","b"],"review_a"),(["c","d"],"review_b"),(["review_a"],"reviewed"),(["review_b"],"reviewed"),(["e","f"],"transport"),(["g"],"transport"),(["reviewed","transport"],"ready")]),
    RULE_FINAL[1]: ("normal requires a,b,c together; exception requires d,e together. Either normal or exception authorizes eligible. dispatch requires eligible AND f. archive independently requires f AND g, even if not eligible. audit depends ONLY on h.",
        [(["a","b","c"],"normal"),(["d","e"],"exception"),(["normal"],"eligible"),(["exception"],"eligible"),(["eligible","f"],"dispatch"),(["f","g"],"archive")]),
    RULE_FINAL[2]: ("x requires a AND b. y comes from x AND c, or from the independent joint endorsement d AND e. ready requires y AND f. record requires a AND g independently of y. No endorsement is retroactive evidence for x. audit depends ONLY on h.",
        [(["a","b"],"x"),(["x","c"],"y"),(["d","e"],"y"),(["y","f"],"ready"),(["a","g"],"record")]),
    RULE_FINAL[3]: ("Three certificate types x,y,z respectively require the JOINT input pairs a,b; c,d; e,f. quorum needs any TWO DISTINCT certificate types. ready needs quorum AND g. Two inputs from one certificate type alone do not form quorum. audit depends ONLY on h.",
        [(["a","b"],"x"),(["c","d"],"y"),(["e","f"],"z"),(["x","y"],"quorum"),(["x","z"],"quorum"),(["y","z"],"quorum"),(["quorum","g"],"ready")]),
    RULE_FINAL[4]: ("a is the only external seed for x. x together with b yields y. y together with c can feed back to x but cannot seed an empty cycle. z needs y AND d; w needs z AND e; ready needs w AND f. g is irrelevant. audit depends ONLY on h.",
        [(["a"],"x"),(["x","b"],"y"),(["y","c"],"x"),(["y","d"],"z"),(["z","e"],"w"),(["w","f"],"ready")]),
    RULE_FINAL[5]: ("NEW POLICY: x uses current credential b AND jurisdiction d, NOT old credential a. y requires either x AND e, or alternative joint credentials c AND f. ready also needs g. Neither obsolete a nor one isolated alternate credential authorizes anything. audit depends ONLY on h.",
        [(["b","d"],"x"),(["x","e"],"y"),(["c","f"],"y"),(["y","g"],"ready")]),
    SMOKE_RULE: ("left requires a AND b; right requires c AND d. ready follows from either left or right. e,f,g are irrelevant; audit depends ONLY on h.",
        [(["a","b"],"left"),(["c","d"],"right"),(["left"],"ready"),(["right"],"ready")]),
}


def _rule_oracle(family, facts):
    a,b,c,d,e,f,g,h = (letter in facts for letter in "abcdefgh")
    if family == RULE_FINAL[0]:
        left,right,transport = a and b,c and d,(e and f) or g
        observed = {"review_a":left,"review_b":right,"reviewed":left or right,"transport":transport,
                    "ready":(left or right) and transport}
    elif family == RULE_FINAL[1]:
        normal,exception = a and b and c,d and e
        observed = {"normal":normal,"exception":exception,"eligible":normal or exception,
                    "dispatch":(normal or exception) and f,"archive":f and g}
    elif family == RULE_FINAL[2]:
        observed = {"x":a and b,"y":(a and b and c) or (d and e),
                    "ready":((a and b and c) or (d and e)) and f,"record":a and g}
    elif family == RULE_FINAL[3]:
        x,y,z = a and b,c and d,e and f
        quorum = sum((x,y,z)) >= 2
        observed = {"x":x,"y":y,"z":z,"quorum":quorum,"ready":quorum and g}
    elif family == RULE_FINAL[4]:
        observed = {"x":a,"y":a and b,"z":a and b and d,"w":a and b and d and e,
                    "ready":a and b and d and e and f}
    elif family == RULE_FINAL[5]:
        x = b and d
        y = (x and e) or (c and f)
        observed = {"x":x,"y":y,"ready":y and g}
    elif family == SMOKE_RULE:
        observed = {"left":a and b,"right":c and d,"ready":(a and b) or (c and d)}
    else:
        raise ValueError("Unregistered Rule oracle")
    return sorted(key for key,value in {**observed,"audit":h}.items() if value)


def _rule(family):
    description,declarations = _RULES[family]
    identifier = "v15-rule-final-"+family
    correct = [{"id":f"r{i}","if":antecedents,"then":consequence} for i,(antecedents,consequence) in enumerate(declarations)]
    correct.append({"id":"audit_rule","if":["h"],"then":"audit"})
    starter = deepcopy(correct)
    starter[0]["if"] = ["h"]
    facts = [[letter for letter,present in zip("abcdefgh",bits) if present]
             for bits in itertools.product((False,True),repeat=8)]
    facts = [facts[-1],facts[1],*facts[2:-1],facts[0]]
    cases = [{"id":f"{identifier}-case{i}","facts":row,"expected":_rule_oracle(family,row)} for i,row in enumerate(facts)]
    derived = sorted({rule["then"] for rule in correct})
    return NativeAdapter({"id":identifier,"domain":"rule_reasoning","split":"final","family":family,
        "cluster_id":"v15-rule-"+family,"contract":_contract(family == RULE_FINAL[5]),
        "prompt":description+" Repair editable rules. Return the COMPLETE rule list with every original id, "
                 "INCLUDING protected audit_rule unchanged. Do not return only changed rules. "
                 "Generation is {\"rules\":[...]}; revision must be {\"action\":\"keep\"} or "
                 "{\"action\":\"apply\",\"artifact\":{\"rules\":[...]}}. Every requested derived fact is checked.",
        "rules":starter,"editable_rule_ids":[r["id"] for r in correct[:-1]],
        "vocabulary":sorted(set("abcdefgh")|set(derived)),"initial_facts":facts[0],"answer_facts":derived,
        "public_cases":cases[:2],"hidden_cases":cases[2:],"reference_artifact":{"rules":correct},
        "metadata":_metadata("rule_reasoning",family,"final")})


def payload(adapter):
    """Host-only: includes references and private oracle outcomes."""
    return adapter.task.to_dict() if isinstance(adapter,CodingAdapter) else deepcopy(adapter.task)


def _registered(adapter):
    row = payload(adapter)
    if row.get("metadata",{}).get("version") != VERSION:
        raise ValueError("Only registered V15 authored tasks are supported")
    return row


def public_task(adapter):
    """Public original task only; never exposes generated probe expected values."""
    row = payload(adapter)
    if row.get("metadata",{}).get("probe"):
        raise ValueError("Do not send a probe adapter or its oracle to a model")
    public = _public(adapter)
    public["domain"] = adapter.domain
    if isinstance(adapter,CodingAdapter):
        public["contract"] = deepcopy(row.get("metadata",{}).get("contract",_contract()))
    if adapter.domain == "spreadsheet":
        public["runtime"] += " Equality INSIDE expressions is == (not =); the formula itself still starts with =."
    elif adapter.domain == "rule_reasoning":
        public["runtime"] += " Return ALL original rules, including protected audit_rule unchanged."
    if row.get("metadata",{}).get("version") == VERSION and adapter.domain in {"coding","spreadsheet"}:
        public["input_domain"] = public_input_schema(adapter)
    return public


def constraints_for(adapter):
    row = _registered(adapter)
    if row["split"] != "development" or row["metadata"].get("probe"):
        raise ValueError("Only ordinary development obligations may feed Skill learning")
    return deepcopy(row["metadata"]["obligations"])


def public_input_schema(adapter):
    row = _registered(adapter)
    if adapter.domain == "coding":
        return deepcopy(row["input_domain"])
    if adapter.domain == "spreadsheet":
        return deepcopy(row["metadata"]["input_schema"])
    raise ValueError("Dynamic probe generation supports Coding and Spreadsheet only")


def _matches(value, schema):
    kind = schema["type"]
    if kind == "object":
        return (type(value) is dict and set(value) == set(schema["properties"])
                and all(_matches(value[key],child) for key,child in schema["properties"].items()))
    if kind == "array":
        return type(value) is list and len(value) <= schema["maxItems"] and all(_matches(v,schema["items"]) for v in value)
    if kind == "integer" and type(value) is not int:
        return False
    if kind == "number" and type(value) not in {int,float}:
        return False
    return type(value) in {int,float} and math.isfinite(value) and schema["minimum"] <= value <= schema["maximum"]


def validate_probe_input(adapter, value):
    """Closed bounded JSON schema, not an LLM judgment; bool != numeric input."""
    try:
        return _matches(value,public_input_schema(adapter))
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):
        return False


def canonical_inputs(adapter):
    """Fixed policy's four public-schema-derived, ordinary-disjoint challenges.

    This contains no reference solutions or oracle outcomes and does not inspect
    candidate code. It is not claimed to be optimal or exhaustive input search.
    """
    row = _registered(adapter)
    if row["split"] not in {"development","calibration"} or row["metadata"].get("probe"):
        raise ValueError("Canonical probes are restricted to ordinary development/calibration tasks")
    ordinary = row["public_cases"]+row["private_cases" if adapter.domain == "coding" else "hidden_cases"]
    field = "input" if adapter.domain == "coding" else "overrides"
    seen = {digest(case[field]) for case in ordinary}
    schema = public_input_schema(adapter)
    if adapter.domain == "coding":
        low = schema["properties"]["values"]["items"]["minimum"]
        kmin = schema["properties"]["k"]["minimum"]
        choices = [{"values":values,"k":k} for values in ([low,0,20,low],[0,0],[20],[3,1,3,0],[],[1,1,0,1])
                   for k in (kmin,12,3)]
    else:
        choices = [{key: child["minimum"]+(child["maximum"]-child["minimum"])*fractions[i]
                    for i,(key,child) in enumerate(schema["properties"].items())}
                   for fractions in ([0,1,1,0,1,0],[1,0,0,1,0,1],[0.5,0,1,0.5,0,1],[0,0.5,1,1,0.5,0],
                                     [0.1,0.3,0.7,0.9,0.2,0.4],[0.8,0.6,0.4,0.2,0.1,0.9])]
    result = []
    for value in choices:
        identity = digest(value)
        if identity not in seen and validate_probe_input(adapter,value):
            result.append(value)
            seen.add(identity)
            if len(result) == MAX_PROBES:
                return result
    raise ValueError("Insufficient distinct legal fixed challenge inputs")


def control_inputs(adapter):
    """HOST-ONLY ordinary calibration inputs, not a model probe prompt.

    Split into <=4 chunks when using probe_adapter; all chunks are needed for
    full control truth. Canonical strategy inputs are not a substitute for this.
    """
    row = _registered(adapter)
    if row["split"] not in {"development","calibration"} or row["metadata"].get("probe"):
        raise ValueError("Control inputs are not exposed for final or probe tasks")
    field = "input" if adapter.domain == "coding" else "overrides"
    cases = row["public_cases"]+row["private_cases" if adapter.domain == "coding" else "hidden_cases"]
    return [deepcopy(case[field]) for case in cases]


def probe_adapter(adapter, inputs):
    """Materialize only model-proposed inputs; compute expected values on host.

    Actual source phase is retained. Duplication of ordinary inputs is allowed
    and explicitly recorded (not advertised as new coverage); duplicate inputs
    within one request are forbidden. No new Python code is compiled or run here.
    """
    row = _registered(adapter)
    if row["split"] not in {"development","calibration"} or row["metadata"].get("probe"):
        raise ValueError("Only ordinary development/calibration tasks can create probes")
    if (type(inputs) is not list or not 1 <= len(inputs) <= MAX_PROBES
            or not all(validate_probe_input(adapter,value) for value in inputs)):
        raise ValueError("One to four legal native input objects required")
    hashes = [digest(value) for value in inputs]
    if len(set(hashes)) != len(hashes):
        raise ValueError("Duplicate probe input")
    identifier = row["id"]+"-probe-"+digest(inputs)[:16]
    metadata = deepcopy(row["metadata"])
    ordinary = row["public_cases"]+row["private_cases" if adapter.domain == "coding" else "hidden_cases"]
    field = "input" if adapter.domain == "coding" else "overrides"
    ordinary_hashes = {digest(case[field]) for case in ordinary}
    metadata.update(probe=True,source_task_id=row["id"],source_task_hash=digest(row),
                    probe_input_hashes=hashes,ordinary_overlap=sum(h in ordinary_hashes for h in hashes),
                    case_obligations={f"{identifier}-case{i}":"behavior" for i in range(len(inputs))})
    if isinstance(adapter,CodingAdapter):
        cases = [{"label":f"{identifier}-case{i}","input":deepcopy(value),"expected":_code_oracle(row["family"],value),
                  "exception":None,"public":True,"dimension":"requested_behavior"} for i,value in enumerate(inputs)]
        return CodingAdapter(replace(adapter.task,id=identifier,public_cases=cases,private_cases=[],metadata=metadata))
    cases = [{"id":f"{identifier}-case{i}","overrides":deepcopy(value),"expected":_sheet_oracle(row["family"],value)}
             for i,value in enumerate(inputs)]
    row.update(id=identifier,public_cases=cases,hidden_cases=[],metadata=metadata)
    return NativeAdapter(row)


def _expanded(formulas, cell):
    """Trusted authored-graph expansion for control fixtures only, never models."""
    import re

    def visit(name, stack):
        if name in stack:
            raise ValueError("Cycle in authored graph")
        return re.sub(r"\b[B-C][1-4]\b",lambda m:"("+visit(m.group(),stack|{name})+")",
                      formulas[name][1:])
    return "="+visit(cell,set())


def calibration_artifacts(adapter):
    """Host-only four controls. Labels and references never enter probe prompts."""
    row = _registered(adapter)
    if isinstance(adapter,CodingAdapter):
        reference = deepcopy(row["reference_files"])
        equivalent = {**reference,"logic.py":reference["logic.py"]+"\n# Equivalent whitespace/comment control.\n"}
        preservation = reference["logic.py"].replace("def run(data):","def calculate(data):",1)
        preservation += "\ndef run(data):\n    result = calculate(data)\n    data['values'].append(0)\n    return result\n"
        return {"reference":reference,"equivalent":equivalent,"semantic_mutant":deepcopy(row["files"]),
                "preservation_mutant":{**reference,"logic.py":preservation}}
    reference = deepcopy(row["reference_artifact"])
    if adapter.domain == "spreadsheet":
        import re

        correct = _SHEET[row["family"]][1]
        equivalent = {"formulas":{cell:"=("+formula[1:]+")+0" for cell,formula in reference["formulas"].items()}}
        preservation = {"formulas":{cell:_expanded(correct,cell) for cell in row["editable_cells"]}}
        audit_dependencies = set(re.findall(r"\bB[1-4]\b",correct["C2"]))
        answer_dependencies = set(re.findall(r"\bB[1-4]\b",correct["C1"]))
        audit_only = sorted(audit_dependencies-answer_dependencies)
        if not audit_only:
            raise ValueError("Authored preservation control needs an audit-only dependency")
        preservation["formulas"][audit_only[0]] += "+1"
        # Explicitly anchor the primary answer while breaking a protected audit.
        # Every output cell is tested; no protected cell bytes are modified.
        semantic = {"formulas":{cell:row["formulas"][cell] for cell in row["editable_cells"]}}
        return {"reference":reference,"equivalent":equivalent,"semantic_mutant":semantic,"preservation_mutant":preservation}
    equivalent = deepcopy(reference)
    for rule in equivalent["rules"][:-1]:
        rule["if"] = list(reversed(rule["if"]))
    preservation = deepcopy(reference)
    preservation["rules"][0]["then"] = "audit"
    return {"reference":reference,"equivalent":equivalent,"semantic_mutant":{"rules":deepcopy(row["rules"])},
            "preservation_mutant":preservation}


def build_panel(smoke=False):
    if type(smoke) is not bool:
        raise ValueError("Explicit smoke boolean required")
    if smoke:
        return {"train":[[_coding(SMOKE_CODING[0],"development")],[_sheet(SMOKE_SHEET[0],"development")]],
                "calibration":[[_coding(SMOKE_CODING[1],"calibration"),_sheet(SMOKE_SHEET[1],"calibration")]],
                "final":[_coding(SMOKE_CODING[2],"final"),_sheet(SMOKE_SHEET[2],"final"),_rule(SMOKE_RULE)]}
    return {"train":[[_coding(f,"development") for f in CODING_DEV[:2]],
                     [_sheet(f,"development") for f in SHEET_DEV[:2]],
                     [_coding(f,"development") for f in CODING_DEV[2:]],
                     [_sheet(f,"development") for f in SHEET_DEV[2:]]],
            "calibration":[[_coding(c,"calibration"),_sheet(s,"calibration")] for c,s in zip(CODING_CAL,SHEET_CAL)],
            "final":[*[_coding(f,"final") for f in CODING_FINAL],*[_sheet(f,"final") for f in SHEET_FINAL],
                     *[_rule(f) for f in RULE_FINAL]]}


def panel_manifest(panel):
    def item(adapter):
        task = payload(adapter)
        return {"task_id":task["id"],"task_hash":digest(task),"cluster_id":task["cluster_id"],
                "domain":adapter.domain,"split":task["split"],"family":task["family"]}
    return {"version":VERSION,"synthetic_not_public_benchmark":True,
            "train":[[item(a) for a in batch] for batch in panel["train"]],
            "calibration":[[item(a) for a in batch] for batch in panel["calibration"]],
            "final":[item(a) for a in panel["final"]]}


def self_check(panel):
    """Offline calibration of authored controls; Python stays inside OS sandbox.

    This checks internal oracle/reference consistency, not public benchmark
    quality or expected model difficulty. No API, no filesystem writes here.
    """
    from skillopt.coevolution_v8.feedback_study import evaluate, score

    rows,seen = [],set()
    groups = [(a,"development") for batch in panel["train"] for a in batch]
    groups += [(a,"calibration") for batch in panel["calibration"] for a in batch]
    groups += [(a,"final") for a in panel["final"]]
    for adapter,phase in groups:
        task = _registered(adapter)
        if task["split"] != phase or task["metadata"]["partition"] != phase or task["cluster_id"] in seen:
            raise ValueError("Task partition/family overlap or relabeling")
        seen.add(task["cluster_id"])
        controls = {}
        for name,artifact in calibration_artifacts(adapter).items():
            evaluation = evaluate(adapter,artifact,public_only=False)
            result = score(adapter,artifact,evaluation)
            if result["all_attempt_success"] != int(name in {"reference","equivalent"}) or not result["oracle_available"]:
                raise ValueError("Authored control failed independent oracle: "+task["id"]+"/"+name)
            controls[name] = {"passed":bool(result["all_attempt_success"]),"available":result["oracle_available"]}
        if phase in {"development","calibration"}:
            challenge = probe_adapter(adapter,canonical_inputs(adapter))
            reference = calibration_artifacts(adapter)["reference"]
            check = score(challenge,reference,evaluate(challenge,reference,public_only=False))
            if check["all_attempt_success"] != 1:
                raise ValueError("Canonical probe reference disagrees with oracle: "+task["id"])
        rows.append({"task_id":task["id"],"domain":adapter.domain,"task_hash":digest(task),"phase":phase,"controls":controls})
    result = {"version":VERSION+"-preflight","all_checked":True,"checked_tasks":len(rows),
              "records":rows,"model_api_calls":0,"reference_execution":"existing_os_sandbox_only",
              "synthetic_internal_consistency_not_model_efficacy":True}
    json.dumps(result,allow_nan=False)
    return result
