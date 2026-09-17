"""Closed, bounded typed-value wire codec shared by host and isolated child.

Only exact builtin values are accepted: a candidate-defined object's methods
are never called. This file can be concatenated as trusted source into the
isolated runner; do not add project imports or top-level execution.
"""

import json
import re

MAX_NODES = 8192
MAX_DEPTH = 32
MAX_STRING_CHARS = 65536
MAX_TOTAL_CHARS = 262144
MAX_INT_BITS = 1024


class ValueCodecError(ValueError):
    """A value is outside the precisely supported wire language."""


def _budget(state, depth, chars=0):
    state[0] += 1
    state[1] += chars
    if depth > MAX_DEPTH or state[0] > MAX_NODES or state[1] > MAX_TOTAL_CHARS:
        raise ValueCodecError("Typed value exceeds structural bounds")


def _integer(value):
    if value.bit_length() > MAX_INT_BITS:
        raise ValueCodecError("Integer exceeds bit bound")
    return value


def _encode(value, state, depth):
    kind = type(value)
    _budget(state, depth)
    if value is None:
        return {"type": "none", "value": None}
    if kind is bool:
        return {"type": "bool", "value": value}
    if kind is int:
        return {"type": "int", "value": str(_integer(value))}
    if kind is float:
        return {"type": "float", "value": value.hex()}
    if kind is str:
        if len(value) > MAX_STRING_CHARS:
            raise ValueCodecError("String exceeds character bound")
        state[1] += len(value)
        if state[1] > MAX_TOTAL_CHARS:
            raise ValueCodecError("Typed strings exceed total bound")
        return {"type": "str", "value": value}
    if kind in (list, tuple, set):
        if len(value) > MAX_NODES:
            raise ValueCodecError("Container exceeds item bound")
        items = [_encode(item, state, depth + 1) for item in value]
        if kind is set:
            items.sort(key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=True))
        return {"type": kind.__name__, "value": items}
    if kind is dict:
        if len(value) > MAX_NODES:
            raise ValueCodecError("Dictionary exceeds item bound")
        return {"type": "dict", "value": [
            [_encode(key, state, depth + 1), _encode(item, state, depth + 1)]
            for key, item in value.items()
        ]}
    raise ValueCodecError("Only exact supported builtin values may cross the wire")


def encode_value(value):
    """Encode builtin data without coercion, approximate floats, or user hooks."""
    return _encode(value, [0, 0], 0)


def _decode(encoded, state, depth):
    _budget(state, depth)
    if type(encoded) is not dict or set(encoded) != {"type", "value"}:
        raise ValueCodecError("Typed value requires exactly type and value")
    tag, value = encoded["type"], encoded["value"]
    if type(tag) is not str:
        raise ValueCodecError("Typed tag must be a string")
    if tag == "none" and value is None:
        return None
    if tag == "bool" and type(value) is bool:
        return value
    if tag == "int" and type(value) is str:
        if len(value) > 310 or re.fullmatch(r"(?:0|-[1-9][0-9]*|[1-9][0-9]*)", value) is None:
            raise ValueCodecError("Integer must use a bounded canonical decimal string")
        return _integer(int(value))
    if tag == "float" and type(value) is str:
        if len(value) > 32:
            raise ValueCodecError("Float representation exceeds bound")
        try:
            number = float.fromhex(value)
        except (ValueError, OverflowError) as error:
            raise ValueCodecError("Invalid float hex representation") from error
        if number.hex() != value:
            raise ValueCodecError("Float must use canonical float.hex representation")
        return number
    if tag == "str" and type(value) is str:
        if len(value) > MAX_STRING_CHARS:
            raise ValueCodecError("String exceeds character bound")
        state[1] += len(value)
        if state[1] > MAX_TOTAL_CHARS:
            raise ValueCodecError("Typed strings exceed total bound")
        return value
    if tag in ("list", "tuple", "set", "dict") and type(value) is list:
        if len(value) > MAX_NODES:
            raise ValueCodecError("Container exceeds item bound")
        if tag == "dict":
            result = {}
            for pair in value:
                if type(pair) is not list or len(pair) != 2:
                    raise ValueCodecError("Dictionary entries must be typed key/value pairs")
                key = _decode(pair[0], state, depth + 1)
                item = _decode(pair[1], state, depth + 1)
                try:
                    if key in result:
                        raise ValueCodecError("Duplicate native dictionary key")
                    result[key] = item
                except TypeError as error:
                    raise ValueCodecError("Unhashable native dictionary key") from error
            return result
        items = [_decode(item, state, depth + 1) for item in value]
        if tag == "list":
            return items
        if tag == "tuple":
            return tuple(items)
        try:
            result = set(items)
        except TypeError as error:
            raise ValueCodecError("Unhashable native set member") from error
        if len(result) != len(items):
            raise ValueCodecError("Duplicate native set member")
        return result
    raise ValueCodecError("Typed tag or primitive payload is unsupported")


def decode_value(encoded):
    """Decode only bounded canonical typed data, preserving Python value types."""
    return _decode(encoded, [0, 0], 0)
