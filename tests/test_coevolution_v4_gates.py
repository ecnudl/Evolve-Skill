from skillopt.coevolution_v4.gates import decide_local, decide_scope, probe_losses


def row(flags, preserved=("p",)):
    return {"available": True, "hard": all(flags.values()), "case_results": flags,
            "preserved": {k: flags[k] for k in preserved}, "case_total": len(flags),
            "case_passes": sum(flags.values())}


def pair():
    return {"id": "task", "repeat": 0, "base": row({"p": True, "r": False}),
            "working": row({"p": True, "r": False}), "candidate": row({"p": True, "r": True})}


def test_local_shared_probe_cannot_be_ignored():
    p = pair()
    p["probe_results"] = {"base": {"x": True}, "working": {"x": True}, "candidate": {"x": False}}
    result = decide_local({"valid": True, "content": "skill"}, [p])
    assert not result["passed"]
    assert result["reason"] == "verified_local_probe_regression"


def test_unknown_does_not_erase_independent_finite_checks():
    p = pair()
    p["search_unknown"] = "malformed_probe"
    result = decide_local({"valid": True, "content": "skill"}, [p])
    assert result["passed"]
    assert result["evidence"]["shared_probe_audit"]["unknown"]
    assert not result["statistical_safety_certified"]


def test_replay_regression_rejects_even_with_source_gain():
    replay = pair()
    replay["id"] = "old"
    replay["base"], replay["candidate"] = replay["candidate"], replay["base"]
    assert not decide_local({"valid": True, "content": "skill"}, [pair()], [replay])["passed"]


def test_scope_local_dependency_and_no_crossdomain_claim():
    c = {"valid": True, "content": "skill"}
    p = pair()
    p["approved"] = p.pop("working")
    local = decide_local(c, [pair()])
    result = decide_scope(c, local, [p])
    assert result["passed"] and not result["cross_domain_validated"]


def test_known_harm_survives_another_unknown():
    p = pair()
    p["probe_results"] = {"candidate": {"x": False, "y": None}, "base": {"x": True, "y": True}}
    losses, unknown = probe_losses([p], "working")
    assert len(losses) == 1 and unknown
