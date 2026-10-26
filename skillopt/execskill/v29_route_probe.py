"""v2.9-only northgate length measurement for lean S1.

Three sequential long-output fixture requests follow chain.first_call. All use
chain D's registered route-B client, nominal benchmark cap and read timeout.
There are no task items, acceptance/test content or route-A clients here.
"""
from __future__ import annotations

import hashlib

from skillopt.continual_eval.core import require, safe_path, write_json

from . import budgets, client, profiles as p, units

PROBE_CALLS = 3
PROBE_SYSTEM = "You are a connectivity probe. Follow the user's instruction exactly."
PROBE_LONG = ("Write a plain-prose essay of about 1,500 words on the history of the printing press, "
              "without headings or lists.")


def prompt_pins():
    return {"system": PROBE_SYSTEM, "user": PROBE_LONG, "calls": PROBE_CALLS,
            "sha256": hashlib.sha256((PROBE_SYSTEM + "\n" + PROBE_LONG).encode()).hexdigest()}


def measure(setting, chain="D"):
    """Persist the length bound once; retries/resumes reuse the completed unit."""
    config = p.configuration_of(setting)
    require(p.is_v29(config) and chain == "D", "The v2.9 northgate S1 probe")
    bench = p.active_benches(config)[0]
    name = "D/lean-smoke/S1-northgate-length"
    identity = {"unit": name, "configuration": config, "route": client.ROUTE_B,
                "model": client.NORTHGATE_MODEL, "prompt": prompt_pins(),
                "max_tokens": p.solver_tokens(p.CHAINS["D"], bench)}
    def work(attempt):
        made = setting.clients(p.CHAINS["D"], bench)
        require(getattr(made, "route", None) == client.ROUTE_B,
                "S1's length probe must use northgate")
        bound = p.ledger_bound(p.CHAINS["D"], bench, branch=setting.branch, longest=setting.longest)
        endpoint = budgets.endpoint(setting, budgets.first_call_scopes(chain), client=made, max_tokens_bound=bound)
        rows = []
        for index in range(PROBE_CALLS):
            recorder = endpoint.recorder(label=name + "/%d" % index)
            receipt = endpoint.send(PROBE_SYSTEM, PROBE_LONG, recorder)
            usage = receipt.get("usage") or {}
            count = usage.get("completion_tokens")
            # A compliant ALF solver has M=1024; the intentionally long probe
            # can end at that cap. A clean length termination is a usable length
            # measurement, not a failed task or a successful solver answer.
            capped = (receipt.get("error_type") == "finish_length"
                      and receipt.get("finish_reason") == "length"
                      and isinstance(receipt.get("response"), str) and bool(receipt["response"].strip())
                      and receipt.get("reasoning_chars", 0) == 0
                      and receipt.get("reasoning_tokens") in (None, 0))
            passed = ((receipt.get("ok") is True or capped)
                      and receipt.get("returned_model") in client.NORTHGATE_RESPONSE_MODEL_IDS
                      and type(count) is int and count > 0)
            rows.append({"passed": passed, "route": client.ROUTE_B,
                         "returned_model": receipt.get("returned_model"), "usage": usage,
                         "finish_reason": receipt.get("finish_reason"), "capped_measurement": capped,
                         "request_sha256": recorder.sends[-1]["request_sha256"],
                         "tokens": sum(row.get("charged", 0) for row in recorder.sends)})
            # Keep partial evidence if a later reply is unusable or infrastructure pauses.
            write_json(attempt / ("probe-%d.json" % index), {"prompt": prompt_pins(), "receipt": rows[-1]})
            require(passed, "Northgate S1 requires usable replies and explicit completion usage")
        longest = max(row["usage"]["completion_tokens"] for row in rows)
        return {"passed": True, "route": client.ROUTE_B, "model": client.NORTHGATE_MODEL,
                "branch": "N", "longest": longest, "calls": len(rows), "receipts": rows,
                "tokens": sum(row["tokens"] for row in rows), "prompt": prompt_pins(),
                "ledger_bound": p.ledger_bound(p.CHAINS["D"], bench, branch="N", longest=longest)}
    done = units.run_unit(safe_path(setting.root) / chain / "lean-smoke" / "S1-northgate-length",
                          run=setting.run, identity=identity, work=work, evidence=setting.evidence,
                          configuration=config)
    return done["result"]
