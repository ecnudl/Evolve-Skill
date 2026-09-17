from scripts.validator_pilot_preflight import _semantic_ok


def test_plain_and_fenced_json_are_equivalent():
    raw = '{"valid":true,"reason":"preserved","probe":2}'
    for response in (raw, '```json\n' + raw + '\n```'):
        assert _semantic_ok({"ok": True, "response": response}, 2)
    assert not _semantic_ok({"ok": True, "response": raw}, 3)
    assert not _semantic_ok({"ok": False, "response": raw}, 2)
    assert not _semantic_ok({"ok": True, "response": "extra " + raw}, 2)
