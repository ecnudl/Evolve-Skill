"""Six original held-out multi-module projects with independent case answers.

No old experiment artifacts, model calls, or runtime evaluation are used here.
Expected answers below are enumerated from the visible contracts, not obtained
by executing either reference implementation.  Both modes retain a legacy API.
"""

from copy import deepcopy
from textwrap import dedent

MODES = ("local-update", "full-policy-replacement")


def _object(properties, required=None, *, extra=False):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": extra}


def _array(items, limit=16, *, unique=False):
    return {"type": "array", "items": items, "maxItems": limit, "uniqueItems": unique}


def _input_schema(slug):
    string = {"type": "string", "minLength": 1, "maxLength": 128}
    text = {"type": "string", "maxLength": 2048}
    strings = _array(string)
    mapping = {"type": "object", "additionalProperties": strings}
    if slug == "resource-slot-scheduler":
        bounds = {"resource": string, "start": {"type": "integer", "minimum": 0, "maximum": 10000},
                  "end": {"type": "integer", "minimum": 0, "maximum": 10000}}
        properties = {"requests": _array(_object({**bounds, "id": string, "priority": {
            "type": "integer", "minimum": -1000, "maximum": 1000}})), "blocked": _array(_object(bounds))}
    elif slug == "group-permission-inheritance":
        properties = {"user_groups": strings, "permissions": _array(string, unique=True),
                      "parents": mapping, "grants": mapping, "denies": mapping}
    elif slug == "message-locale-fallback":
        catalogs = {"type": "object", "additionalProperties": {"type": "object", "additionalProperties": text}}
        properties = {"locale": string, "default_locale": string, "keys": _array(string, unique=True), "messages": catalogs}
    elif slug == "document-posting-replacement":
        properties = {"documents": _array(_object({"id": string, "text": text})),
                      "index": {"type": "object", "additionalProperties": _array(string, unique=True)}}
    elif slug == "package-selection-precedence":
        properties = {"paths": strings, "include": strings, "exclude": strings, "force_include": strings}
    elif slug == "response-cors-middleware":
        pair = {"type": "array", "items": text, "minItems": 2, "maxItems": 2}
        properties = {"headers": _array(pair), "origin": {"type": ["string", "null"], "minLength": 1, "maxLength": 128},
                      "allowed_origins": strings, "credentials": {"type": "boolean"}}
    else:
        raise ValueError("Unknown project")
    return _object({"action": {"type": "string", "enum": ["legacy", "apply"]}, **properties}, list(properties))


def _name(value):
    return isinstance(value, str) and 0 < len(value) <= 128


def _map_names(mapping, *, values_are_strings=False):
    if not isinstance(mapping, dict) or len(mapping) > 16:
        return False
    for key, values in mapping.items():
        if not _name(key):
            return False
        if values_are_strings:
            if not isinstance(values, str) or len(values) > 2048:
                return False
        elif not all(_name(value) for value in values):
            return False
    return True


def _normalized_path(value, *, pattern=False):
    if not _name(value):
        return False
    if pattern and value == "*":
        return True
    if "*" in value or value.startswith("/") or "\\" in value:
        return False
    if pattern and value.endswith("/"):
        value = value[:-1]
    return all(part not in ("", ".", "..") for part in value.split("/"))


def _header_name(value):
    return _name(value) and value.isascii() and all("a" <= ch.lower() <= "z" or "0" <= ch <= "9" or ch == "-" for ch in value)


def _extra_valid(slug, data):
    """Additional public domain relations after structural schema validation."""
    try:
        if slug == "resource-slot-scheduler":
            requests = data["requests"]
            return (len({row["id"] for row in requests}) == len(requests)
                    and all(_name(row["id"]) for row in requests)
                    and all(_name(row["resource"]) and row["start"] < row["end"]
                            for row in [*requests, *data["blocked"]]))
        if slug == "group-permission-inheritance":
            return (all(_name(value) for value in [*data["permissions"], *data["user_groups"]])
                    and all(_map_names(data[key]) for key in ("parents", "grants", "denies")))
        if slug == "message-locale-fallback":
            return (all(_name(data[key]) and data[key].count("-") <= 1 for key in ("locale", "default_locale"))
                    and all(_name(key) for key in data["keys"]) and len(data["messages"]) <= 16
                    and all(_name(locale) and _map_names(catalog, values_are_strings=True)
                            for locale, catalog in data["messages"].items()))
        if slug == "document-posting-replacement":
            documents = data["documents"]
            return (len({row["id"] for row in documents}) == len(documents)
                    and all(_name(row["id"]) and len(row["text"]) <= 2048 and row["text"].isascii() for row in documents)
                    and _map_names(data["index"])
                    and all(all("a" <= ch <= "z" or "0" <= ch <= "9" for ch in token) for token in data["index"]))
        if slug == "package-selection-precedence":
            return (all(_normalized_path(path) for path in data["paths"])
                    and all(_normalized_path(pattern, pattern=True) for key in ("include", "exclude", "force_include")
                            for pattern in data[key]))
        if slug == "response-cors-middleware":
            origin = data["origin"]
            valid_origin = origin is None or (_name(origin) and origin != "*" and "\r" not in origin and "\n" not in origin)
            if not valid_origin or not all(_name(value) and "\r" not in value and "\n" not in value for value in data["allowed_origins"]):
                return False
            for name, value in data["headers"]:
                if not _header_name(name) or len(value) > 2048 or "\r" in value or "\n" in value:
                    return False
                if name.lower() == "vary" and any(token.strip() and not _header_name(token.strip()) for token in value.split(",")):
                    return False
            return True
    except (KeyError, TypeError, AttributeError):
        return False
    return False


def _source(text):
    return dedent(text).strip() + "\n"


def _bundle(contracts, engine, policy, mode, *, alternative=False, broken=False, preservation=False):
    api = """
        from contracts import load_request
        from engine import apply, legacy

        def solve(data):
            request = load_request(data)
            action = request.get("action", "apply")
            if action == "legacy":
                return legacy(request)
            return apply(request)
    """
    if alternative:
        api = """
            from contracts import load_request
            from engine import apply, legacy

            def solve(data):
                request = load_request(data)
                handlers = {"legacy": legacy, "apply": apply}
                operation = handlers[request.get("action", "apply")]
                result = operation(request)
                return result
        """
    if preservation:
        api = """
            from contracts import load_request
            from engine import apply, legacy

            def solve(data):
                request = load_request(data)
                action = request.get("action", "apply")
                if action == "legacy":
                    return apply(request)
                return apply(request)
        """
    return {"api.py": _source(api), "contracts.py": _source(contracts),
            "engine.py": _source(engine),
            "policy.py": _source(policy).replace("__MODE__", repr(mode)).replace("__BROKEN__", repr(broken))}


def _starter_bundle(slug, contracts, engine, policy):
    """Old project really implements only old policy, not dormant new answers."""
    policies = {
        "resource-slot-scheduler": """
            MODE = "legacy"

            def ordered(requests, mode):
                "Compatibility order is the order supplied by the caller."
                result = []
                for request in requests:
                    result.append(request)
                return result

            def overlaps(left, right):
                "Resources are independent; endpoints are half-open."
                if left["resource"] != right["resource"]:
                    return False
                left_before_right_end = left["start"] < right["end"]
                right_before_left_end = right["start"] < left["end"]
                return left_before_right_end and right_before_left_end

            def blocked_slots(request, mode):
                "Old clients carry blocked metadata but do not enforce it."
                result = []
                return result
        """,
        "group-permission-inheritance": """
            MODE = "legacy"

            def groups(request, mode):
                "Only direct groups belong to the compatibility identity."
                active = set()
                for group in request["user_groups"]:
                    active.add(group)
                return active

            def permits(permission, active, request, mode):
                "Legacy grants are additive; absent grants deny by default."
                granted = False
                for group in active:
                    permissions = request["grants"].get(group, [])
                    for item in permissions:
                        if item == permission:
                            granted = True
                return granted

            # Parent and deny maps are accepted request metadata in this version.
            # They do not participate in the compatibility decision.
        """,
        "message-locale-fallback": """
            MODE = "legacy"

            def chain(request, mode):
                "Pick one whole catalog before inspecting individual keys."
                locale = request["locale"]
                default = request["default_locale"]
                available = request["messages"]
                if locale in available:
                    chosen = locale
                else:
                    chosen = default
                return [chosen]

            def has_message(catalog, key):
                "An empty translation is a stored value, not a missing key."
                if key in catalog:
                    return True
                return False

            # The engine asks this module for its catalog lookup order.
            # The legacy API has exactly one catalog in that order.
        """,
        "document-posting-replacement": """
            MODE = "legacy"

            def tokens(text):
                "Canonical terms are lowercase ASCII alphanumeric runs."
                result = set()
                current = ""
                for character in text.lower() + " ":
                    accepted = "a" <= character <= "z" or "0" <= character <= "9"
                    if accepted:
                        current += character
                    elif current:
                        result.add(current)
                        current = ""
                return sorted(result)

            def starting_index(request, mode):
                "Copy every existing posting before add-only ingestion."
                result = {}
                for token, ids in request["index"].items():
                    result[token] = set(ids)
                return result
        """,
        "package-selection-precedence": """
            MODE = "legacy"

            def matches(path, pattern):
                if pattern == "*":
                    return True
                if pattern.endswith("/"):
                    return path.startswith(pattern)
                return path == pattern

            def any_match(path, patterns):
                for pattern in patterns:
                    if matches(path, pattern):
                        return True
                return False

            def selected(path, request, mode):
                "Compatibility selection considers inclusion alone."
                if not request["include"]:
                    return True
                return any_match(path, request["include"])

            # Exclude and force metadata are ignored by the old packager.
            # Only the requested file paths are candidates, never the filesystem.
        """,
        "response-cors-middleware": """
            MODE = "legacy"

            def allowance(request, mode):
                "Compatibility middleware makes no CORS admission decision."
                origin = request["origin"]
                allowed = request["allowed_origins"]
                if origin is None or not allowed:
                    return None
                return None

            def vary_origin(value):
                "Legacy handling retains the final Vary header value."
                return value

            def permit_credentials(request):
                "No credential header is synthesized in compatibility mode."
                return False

            # The old entrypoint only normalizes names and resolves duplicates.
            # It retains headers originally supplied by the caller.
            # Policy hooks exist for future middleware versions.
        """,
    }
    files = _bundle(contracts, engine, policy, "legacy")
    files["policy.py"] = _source(policies[slug])
    # New behavior requires updating engine dispatch AND implementing policy
    # helpers; assigning a different MODE alone cannot reveal a hidden answer.
    files["engine.py"] = files["engine.py"].replace(", MODE)", ', "legacy")')
    if slug == "response-cors-middleware":
        files["engine.py"] = _source("""
            from policy import MODE, allowance, permit_credentials, vary_origin

            def _headers(request, mode):
                # The old engine has no admission, Vary merge, or CORS synthesis.
                # It only canonicalizes the caller's existing header list.
                headers = {}
                for pair in request["headers"]:
                    name = pair[0]
                    value = pair[1]
                    canonical_name = name.lower()
                    headers[canonical_name] = value
                names = sorted(headers)
                normalized = []
                for name in names:
                    normalized.append([name, headers[name]])
                return {"headers": normalized}

            def legacy(request):
                return _headers(request, "legacy")

            def apply(request):
                return _headers(request, "legacy")
        """)
    return files


def _project(slug, context, domain, common, local, replacement, contracts, engine, policy,
             cases, *, public=(0, 1), preserved=()):
    modes = {}
    for offset, mode in enumerate(MODES, 1):
        modes[mode] = {
            "contract": (common + "\nCompatibility is required for api.solve with action='legacy'. "
                         "This migration explicitly permits changing helper semantics inside contracts.py, engine.py, "
                         "and policy.py; they are implementation interfaces, not additional stable public APIs. "
                         "\nNEW apply CONTRACT: " + (local if offset == 1 else replacement)),
            "reference_files": _bundle(contracts, engine, policy, mode),
            "alternative_files": _bundle(contracts, engine, policy, mode, alternative=True),
            "semantic_mutant_files": _bundle(contracts, engine, policy, mode, broken=True),
            "preservation_mutant_files": _bundle(contracts, engine, policy, mode, preservation=True),
            "expected": deepcopy([case[offset] for case in cases]),
        }
    input_schema = _input_schema(slug)
    input_schema["description"] = (domain + " Additional bounds: nonempty identifiers/locales/paths are at most 128 characters; "
                                   "maps and arrays contain at most 16 entries; text/header values are at most 2048 characters. "
                                   "The complete input JSON object must remain exactly unchanged. Missing action means apply.")
    return {"slug": slug, "context": context,
            "files": _starter_bundle(slug, contracts, engine, policy),
            "editable_paths": ["api.py", "contracts.py", "engine.py", "policy.py"],
            "input_domain": input_schema,
            "input_validator": lambda value, project_slug=slug: _extra_valid(project_slug, value),
            "inputs": deepcopy([case[0] for case in cases]), "public_indices": list(public),
            "preserved_indices": list(preserved), "modes": modes}


def _slots():
    contracts = """
        def interval(value):
            if not isinstance(value, dict):
                raise ValueError("interval object required")
            if not isinstance(value.get("resource"), str) or not value["resource"]:
                raise ValueError("resource required")
            start, end = value.get("start"), value.get("end")
            if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool) or start < 0 or start >= end:
                raise ValueError("positive half-open interval required")

        def load_request(data):
            if not isinstance(data, dict) or data.get("action", "apply") not in ("legacy", "apply"):
                raise ValueError("invalid action")
            if not isinstance(data.get("requests"), list) or not isinstance(data.get("blocked"), list):
                raise ValueError("request and blocked lists required")
            seen = set()
            for item in data["requests"]:
                interval(item)
                if not isinstance(item.get("id"), str) or not item["id"] or item["id"] in seen:
                    raise ValueError("unique request ID required")
                if not isinstance(item.get("priority"), int) or isinstance(item.get("priority"), bool):
                    raise ValueError("integer priority required")
                seen.add(item["id"])
            for item in data["blocked"]:
                interval(item)
            return data
    """
    policy = """
        MODE = __MODE__
        BROKEN = __BROKEN__

        def ordered(requests, mode):
            rows = list(requests)
            if mode == "full-policy-replacement":
                rows.sort(key=lambda row: (-row["priority"], row["start"], row["id"]))
            return rows

        def overlaps(left, right):
            if left["resource"] != right["resource"]:
                return False
            if BROKEN:
                return left["start"] <= right["end"] and right["start"] <= left["end"]
            return left["start"] < right["end"] and right["start"] < left["end"]

        def blocked_slots(request, mode):
            if mode == "legacy":
                return []
            return list(request["blocked"])
    """
    engine = """
        from policy import MODE, blocked_slots, ordered, overlaps

        def _schedule(request, mode):
            accepted = []
            rejected = []
            occupied = blocked_slots(request, mode)
            queue = ordered(request["requests"], mode)
            for proposal in queue:
                conflict = False
                for existing in occupied:
                    if overlaps(proposal, existing):
                        conflict = True
                        break
                if conflict:
                    rejected.append(proposal["id"])
                else:
                    accepted.append(proposal["id"])
                    occupied.append(proposal)
            return {"accepted": accepted, "rejected": rejected}

        def legacy(request):
            return _schedule(request, "legacy")

        def apply(request):
            return _schedule(request, MODE)
    """

    def req(name, start, end, priority=0, resource="room"):
        return {"id": name, "resource": resource, "start": start, "end": end, "priority": priority}

    def inp(requests, blocked=None, action="apply"):
        return {"action": action, "requests": requests, "blocked": blocked or []}

    def answer(accepted, rejected):
        return {"accepted": accepted, "rejected": rejected}

    cases = [
        (inp([req("a", 0, 2, 1), req("b", 2, 4, 2)]), answer(["a", "b"], []), answer(["b", "a"], [])),
        (inp([req("a", 0, 3, 1), req("b", 1, 2, 9)]), answer(["a"], ["b"]), answer(["b"], ["a"])),
        (inp([req("a", 2, 3), req("b", 1, 2)], [{"resource": "room", "start": 0, "end": 2}]),
         answer(["a"], ["b"]), answer(["a"], ["b"])),
        (inp([req("a", 1, 2, resource="one"), req("b", 1, 2, resource="two")],
             [{"resource": "one", "start": 0, "end": 4}]), answer(["b"], ["a"]), answer(["b"], ["a"])),
        (inp([req("z", 3, 5, 2), req("b", 0, 2, 2), req("a", 0, 2, 2)]),
         answer(["z", "b"], ["a"]), answer(["a", "z"], ["b"])),
        (inp([]), answer([], []), answer([], [])),
        (inp([req("a", 0, 3, 1), req("b", 1, 2, 9)],
             [{"resource": "room", "start": 0, "end": 9}], "legacy"), answer(["a"], ["b"]), answer(["a"], ["b"])),
        (inp([req("a", 0, 1, 1), req("b", 1, 2, 2)], action="legacy"),
         answer(["a", "b"], []), answer(["a", "b"], [])),
    ]
    return _project("resource-slot-scheduler", "resource_scheduling",
                    "requests: unique nonempty id, resource string, integer 0<=start<end, integer priority; "
                    "blocked: resource/start/end intervals with the same bounds. Lists may be empty.",
                    "OLD/legacy: greedy request input order, ignore blocked intervals, never preempt an accepted request. "
                    "Intervals are half-open [start,end); adjacency is allowed and different resources never conflict. "
                    "Return accepted/rejected ID arrays, each in processing order. Keep legacy behavior intact.",
                    "Keep input-order greedy admission; blocked intervals occupy only their named resources.",
                    "Replace input-order priority with descending priority, then ascending start, then ascending ID. "
                    "Greedily admit in that order, honoring blocked intervals; no later preemption.",
                    contracts, engine, policy, cases, preserved=(5, 6, 7))


def _authorization():
    contracts = """
        def string_list(value):
            return isinstance(value, list) and all(isinstance(x, str) and x for x in value)

        def load_request(data):
            if not isinstance(data, dict) or data.get("action", "apply") not in ("legacy", "apply"):
                raise ValueError("invalid request")
            for key in ("user_groups", "permissions"):
                if not string_list(data.get(key)):
                    raise ValueError("string array required")
            if len(set(data["permissions"])) != len(data["permissions"]):
                raise ValueError("unique permission queries required")
            for key in ("parents", "grants", "denies"):
                value = data.get(key)
                if not isinstance(value, dict):
                    raise ValueError("group map required")
                for group, members in value.items():
                    if not isinstance(group, str) or not group or not string_list(members):
                        raise ValueError("invalid group map")
            return data
    """
    policy = """
        MODE = __MODE__
        BROKEN = __BROKEN__

        def groups(request, mode):
            active = set(request["user_groups"])
            if mode != "full-policy-replacement":
                return active
            pending = list(active)
            while pending:
                child = pending.pop()
                for parent in request["parents"].get(child, []):
                    if parent not in active:
                        active.add(parent)
                        pending.append(parent)
            return active

        def permits(permission, active, request, mode):
            granted = any(permission in request["grants"].get(group, []) for group in active)
            denied = any(permission in request["denies"].get(group, []) for group in active)
            if mode == "legacy" or BROKEN:
                return granted
            return granted and not denied
    """
    engine = """
        from policy import MODE, groups, permits

        def _authorize(request, mode):
            active = groups(request, mode)
            allowed = []
            denied = []
            for permission in request["permissions"]:
                decision = permits(permission, active, request, mode)
                if decision:
                    allowed.append(permission)
                else:
                    denied.append(permission)
            result = {}
            result["allowed"] = allowed
            result["denied"] = denied
            return result

        def legacy(request):
            return _authorize(request, "legacy")

        def apply(request):
            return _authorize(request, MODE)
    """

    def inp(groups, permissions, grants, denies=None, parents=None, action="apply"):
        return {"action": action, "user_groups": groups, "permissions": permissions,
                "grants": grants, "denies": denies or {}, "parents": parents or {}}

    def answer(allowed, denied):
        return {"allowed": allowed, "denied": denied}

    cases = [
        (inp(["team"], ["read", "write"], {"team": ["read", "write"]}, {"team": ["write"]}),
         answer(["read"], ["write"]), answer(["read"], ["write"])),
        (inp(["team"], ["write"], {"department": ["write"]}, parents={"team": ["department"]}),
         answer([], ["write"]), answer(["write"], [])),
        (inp(["team"], ["write"], {"team": ["write"]}, {"department": ["write"]}, {"team": ["department"]}),
         answer(["write"], []), answer([], ["write"])),
        (inp(["a", "a"], ["x", "y"], {"b": ["x"], "c": ["y"]}, parents={"a": ["b"], "b": ["c"], "c": ["a"]}),
         answer([], ["x", "y"]), answer(["x", "y"], [])),
        (inp(["a", "b"], ["x"], {"a": ["x"]}, {"b": ["x"]}), answer([], ["x"]), answer([], ["x"])),
        (inp([], ["x"], {"a": ["x"]}), answer([], ["x"]), answer([], ["x"])),
        (inp(["a"], ["x"], {"a": ["x"]}, {"a": ["x"]}, action="legacy"), answer(["x"], []), answer(["x"], [])),
        (inp(["a"], ["x"], {"parent": ["x"]}, parents={"a": ["parent"]}, action="legacy"),
         answer([], ["x"]), answer([], ["x"])),
        (inp(["a"], ["z", "x", "y"], {"a": ["y", "z"]}), answer(["z", "y"], ["x"]), answer(["z", "y"], ["x"])),
    ]
    return _project("group-permission-inheritance", "group_authorization",
                    "user_groups and permissions are arrays of nonempty case-sensitive strings; permissions are unique. "
                    "parents/grants/denies map nonempty group strings to string arrays. Parent cycles and duplicate memberships are allowed.",
                    "OLD/legacy: only directly listed user_groups grant permissions; parent membership and denies are ignored. "
                    "No grant means denied. Return allowed/denied arrays in permission query order. Keep legacy unchanged.",
                    "Keep direct membership only. Explicit denies from any direct group override all direct grants.",
                    "Use the transitive parent closure of direct groups, including direct groups. Terminate on cycles. "
                    "Any deny anywhere in the closure overrides every grant; otherwise at least one closure grant is required.",
                    contracts, engine, policy, cases, preserved=(5, 6, 7, 8))


def _localization():
    contracts = """
        def load_request(data):
            if not isinstance(data, dict) or data.get("action", "apply") not in ("legacy", "apply"):
                raise ValueError("invalid action")
            for name in ("locale", "default_locale"):
                if not isinstance(data.get(name), str) or not data[name]:
                    raise ValueError("locale required")
            keys = data.get("keys")
            if not isinstance(keys, list) or not all(isinstance(key, str) and key for key in keys):
                raise ValueError("message keys required")
            if len(keys) != len(set(keys)):
                raise ValueError("duplicate key")
            messages = data.get("messages")
            if not isinstance(messages, dict):
                raise ValueError("catalog map required")
            for locale, catalog in messages.items():
                if not isinstance(locale, str) or not isinstance(catalog, dict):
                    raise ValueError("invalid catalog")
                if not all(isinstance(key, str) and isinstance(value, str) for key, value in catalog.items()):
                    raise ValueError("catalog values must be strings, including empty strings")
            return data
    """
    policy = """
        MODE = __MODE__
        BROKEN = __BROKEN__

        def chain(request, mode):
            locale = request["locale"]
            default = request["default_locale"]
            if mode == "legacy":
                return [locale if locale in request["messages"] else default]
            choices = [locale]
            if mode == "full-policy-replacement" and "-" in locale:
                choices.append(locale.split("-", 1)[0])
            choices.append(default)
            unique = []
            for item in choices:
                if item not in unique:
                    unique.append(item)
            return unique

        def has_message(catalog, key):
            if BROKEN:
                return bool(catalog.get(key))
            return key in catalog
    """
    engine = """
        from policy import MODE, chain, has_message

        def _translate(request, mode):
            order = chain(request, mode)
            translated = {}
            for key in request["keys"]:
                found = False
                for locale in order:
                    catalog = request["messages"].get(locale, {})
                    if has_message(catalog, key):
                        translated[key] = catalog[key]
                        found = True
                        break
                if not found:
                    translated[key] = None
            return {"translations": translated}

        def legacy(request):
            return _translate(request, "legacy")

        def apply(request):
            return _translate(request, MODE)
    """

    def inp(locale, keys, messages, default="en", action="apply"):
        return {"action": action, "locale": locale, "default_locale": default, "keys": keys, "messages": messages}

    def answer(**values):
        return {"translations": values}

    cases = [
        (inp("fr", ["title", "body"], {"fr": {"title": "Bonjour"}, "en": {"title": "Hello", "body": "Body"}}),
         answer(title="Bonjour", body="Body"), answer(title="Bonjour", body="Body")),
        (inp("fr-CA", ["title", "body"], {"fr-CA": {"body": "Texte"}, "fr": {"title": "Bonjour"}, "en": {"title": "Hello", "body": "Body"}}),
         answer(title="Hello", body="Texte"), answer(title="Bonjour", body="Texte")),
        (inp("fr-CA", ["title", "body"], {"fr": {"title": "Bonjour"}, "en": {"title": "Hello", "body": "Body"}}),
         answer(title="Hello", body="Body"), answer(title="Bonjour", body="Body")),
        (inp("fr", ["title"], {"fr": {"title": ""}, "en": {"title": "Fallback"}}), answer(title=""), answer(title="")),
        (inp("en", ["title", "missing"], {"en": {"title": "A"}}), answer(title="A", missing=None), answer(title="A", missing=None)),
        (inp("de-AT", ["unknown"], {"en": {"title": "A"}}), answer(unknown=None), answer(unknown=None)),
        (inp("fr", ["title", "body"], {"fr": {"title": "Bonjour"}, "en": {"body": "Body"}}, action="legacy"),
         answer(title="Bonjour", body=None), answer(title="Bonjour", body=None)),
        (inp("fr-CA", ["title"], {"fr": {"title": "Bonjour"}, "en": {"title": "Hello"}}, action="legacy"),
         answer(title="Hello"), answer(title="Hello")),
        (inp("x-Z", [], {}), answer(), answer()),
    ]
    return _project("message-locale-fallback", "message_localization",
                    "locale/default_locale are nonempty case-sensitive strings; locale has at most one hyphen. "
                    "keys are unique nonempty strings. messages maps locale strings to key/string-value objects. "
                    "Empty catalogs and empty translations are permitted; null translations are not stored.",
                    "OLD/legacy: choose the entire exact-locale catalog if it exists, otherwise the entire default catalog. "
                    "Missing requested keys become null; do not fall back per key. Return a translations object containing every requested key. Keep legacy unchanged.",
                    "For each key search exact locale, then default locale. Catalog presence does not stop fallback for a missing key. Empty string is a present translation.",
                    "For each key search exact locale, then language before the first hyphen if present, then default locale; remove duplicate locales. "
                    "An existing empty string ends search; return null only when the key is absent everywhere in this chain.",
                    contracts, engine, policy, cases, preserved=(4, 5, 6, 7, 8))


def _indexing():
    contracts = """
        def load_request(data):
            if not isinstance(data, dict) or data.get("action", "apply") not in ("legacy", "apply"):
                raise ValueError("invalid action")
            documents = data.get("documents")
            index = data.get("index")
            if not isinstance(documents, list) or not isinstance(index, dict):
                raise ValueError("documents and index required")
            seen = set()
            for document in documents:
                if not isinstance(document, dict) or not isinstance(document.get("id"), str):
                    raise ValueError("document ID required")
                if not document["id"] or document["id"] in seen or not isinstance(document.get("text"), str):
                    raise ValueError("unique document ID and text required")
                seen.add(document["id"])
            for token, identifiers in index.items():
                if not isinstance(token, str) or not token or not isinstance(identifiers, list):
                    raise ValueError("invalid posting")
                if not all(isinstance(identifier, str) and identifier for identifier in identifiers):
                    raise ValueError("document IDs required")
            return data
    """
    policy = """
        MODE = __MODE__
        BROKEN = __BROKEN__

        def tokens(text):
            result = set()
            current = ""
            for character in text.lower() + " ":
                numeric = "0" <= character <= "9"
                accepted = "a" <= character <= "z" or (numeric and not BROKEN)
                if accepted:
                    current += character
                elif current:
                    result.add(current)
                    current = ""
            return sorted(result)

        def starting_index(request, mode):
            if mode == "full-policy-replacement":
                return {}
            removed = set()
            if mode == "local-update":
                removed = {document["id"] for document in request["documents"]}
            return {token: set(ids) - removed for token, ids in request["index"].items()}
    """
    engine = """
        from policy import MODE, starting_index, tokens

        def _update(request, mode):
            index = starting_index(request, mode)
            for document in request["documents"]:
                identifier = document["id"]
                vocabulary = tokens(document["text"])
                for token in vocabulary:
                    if token not in index:
                        index[token] = set()
                    index[token].add(identifier)
            normalized = {}
            for token in sorted(index):
                postings = sorted(index[token])
                if postings:
                    normalized[token] = postings
            return {"index": normalized}

        def legacy(request):
            return _update(request, "legacy")

        def apply(request):
            return _update(request, MODE)
    """

    def inp(index, documents, action="apply"):
        return {"action": action, "index": index, "documents": [{"id": key, "text": text} for key, text in documents]}

    def answer(index):
        return {"index": index}

    cases = [
        (inp({"alpha": ["A"], "beta": ["B"]}, [("A", "Gamma gamma")]),
         answer({"beta": ["B"], "gamma": ["A"]}), answer({"gamma": ["A"]})),
        (inp({"alpha": ["A"], "shared": ["A", "B"]}, [("A", "")]), answer({"shared": ["B"]}), answer({})),
        (inp({"cache": ["Z"]}, [("A", "X,y!X"), ("B", "y 123")]),
         answer({"123": ["B"], "cache": ["Z"], "x": ["A"], "y": ["A", "B"]}),
         answer({"123": ["B"], "x": ["A"], "y": ["A", "B"]})),
        (inp({"old": ["Z"]}, []), answer({"old": ["Z"]}), answer({})),
        (inp({"old": ["a", "aa"]}, [("a", "new")]), answer({"new": ["a"], "old": ["aa"]}), answer({"new": ["a"]})),
        (inp({}, [("D", "V2___42 .. v2")]), answer({"42": ["D"], "v2": ["D"]}), answer({"42": ["D"], "v2": ["D"]})),
        (inp({"old": ["A"]}, [("A", "new")], "legacy"), answer({"new": ["A"], "old": ["A"]}), answer({"new": ["A"], "old": ["A"]})),
        (inp({"old": ["Z"]}, [], "legacy"), answer({"old": ["Z"]}), answer({"old": ["Z"]})),
        (inp({"stale": ["A", "B"]}, [("B", "same"), ("A", "same")]), answer({"same": ["A", "B"]}), answer({"same": ["A", "B"]})),
    ]
    return _project("document-posting-replacement", "document_indexing",
                    "documents is an array of unique nonempty string IDs and ASCII text strings. index maps lowercase ASCII "
                    "alphanumeric tokens to arrays of unique nonempty IDs. Empty text/documents/index are allowed.",
                    "Tokenize into maximal ASCII alphanumeric runs, lowercase, deduplicate repeated words per document. "
                    "Return an index object with sorted unique ID postings and no empty postings. OLD/legacy merges new postings "
                    "into the existing index without removing old memberships, even for replaced IDs. Keep legacy intact.",
                    "Replace all indexed memberships of the supplied document IDs, then add their new tokens. "
                    "Empty text removes that document's memberships. Preserve every membership of IDs not supplied.",
                    "Rebuild the complete index from the supplied documents alone; discard all existing postings, "
                    "including IDs not supplied. Empty documents array yields an empty index.",
                    contracts, engine, policy, cases, preserved=(5, 6, 7))


def _packaging():
    contracts = """
        def strings(value):
            return isinstance(value, list) and all(isinstance(item, str) and item for item in value)

        def load_request(data):
            if not isinstance(data, dict) or data.get("action", "apply") not in ("legacy", "apply"):
                raise ValueError("invalid action")
            for key in ("paths", "include", "exclude", "force_include"):
                if not strings(data.get(key)):
                    raise ValueError("nonempty string entries required")
            for path in data["paths"]:
                if path.startswith("/") or path.endswith("/"):
                    raise ValueError("relative file path required")
                if any(part in ("", ".", "..") for part in path.split("/")):
                    raise ValueError("normalized file path required")
            for key in ("include", "exclude", "force_include"):
                for pattern in data[key]:
                    if pattern.startswith("/") or ".." in pattern.split("/"):
                        raise ValueError("relative patterns required")
            return data
    """
    policy = """
        MODE = __MODE__
        BROKEN = __BROKEN__

        def matches(path, pattern):
            if pattern == "*":
                return True
            if pattern.endswith("/") or BROKEN:
                return path.startswith(pattern)
            return path == pattern

        def any_match(path, patterns):
            return any(matches(path, pattern) for pattern in patterns)

        def selected(path, request, mode):
            include = not request["include"] or any_match(path, request["include"])
            exclude = any_match(path, request["exclude"])
            force = any_match(path, request["force_include"])
            if mode == "legacy":
                return include
            if mode == "local-update":
                return include and not exclude
            return force or (include and not exclude)
    """
    engine = """
        from policy import MODE, selected

        def _package(request, mode):
            candidates = set()
            for path in request["paths"]:
                candidates.add(path)
            accepted = []
            ordered = sorted(candidates)
            for path in ordered:
                keep = selected(path, request, mode)
                if keep:
                    accepted.append(path)
            result = {"files": accepted}
            return result

        def legacy(request):
            return _package(request, "legacy")

        def apply(request):
            return _package(request, MODE)
    """

    def inp(paths, include, exclude=None, force=None, action="apply"):
        return {"action": action, "paths": paths, "include": include, "exclude": exclude or [], "force_include": force or []}

    def answer(paths):
        return {"files": paths}

    cases = [
        (inp(["src/a.py", "src/tests/t.py", "README.md"], ["src/"], ["src/tests/"]),
         answer(["src/a.py"]), answer(["src/a.py"])),
        (inp(["src/a.py", "src/tests/t.py"], ["src/"], ["src/tests/"], ["src/tests/t.py"]),
         answer(["src/a.py"]), answer(["src/a.py", "src/tests/t.py"])),
        (inp(["src/a.py.bak", "src/a.py"], ["src/a.py"]), answer(["src/a.py"]), answer(["src/a.py"])),
        (inp(["docs/a", "README"], ["docs/"], ["README"], ["README"]), answer(["docs/a"]), answer(["README", "docs/a"])),
        (inp(["a", "build/drop", "build/keep"], [], ["build/"], ["build/keep"]), answer(["a"]), answer(["a", "build/keep"])),
        (inp([], ["*"], ["*"], ["*"]), answer([]), answer([])),
        (inp(["a", "b"], ["*"], ["a"], action="legacy"), answer(["a", "b"]), answer(["a", "b"])),
        (inp(["z", "a", "z"], [], action="legacy"), answer(["a", "z"]), answer(["a", "z"])),
        (inp(["src2/a", "src/a", "src"], ["src/"]), answer(["src/a"]), answer(["src/a"])),
    ]
    return _project("package-selection-precedence", "package_building",
                    "paths are normalized relative file paths with nonempty components, no '.', '..', wildcard, or trailing slash. "
                    "Pattern lists contain '*', normalized relative file names, or normalized directory prefixes ending '/'. "
                    "Duplicates and empty lists are allowed; strings are case-sensitive.",
                    "Pattern '*' matches every file; a pattern ending '/' is a directory prefix; all other patterns match an exact file only. "
                    "An empty include list includes all paths. Return sorted unique selected files; no filesystem access. "
                    "OLD/legacy uses include only and ignores exclude/force_include. Keep legacy unchanged.",
                    "Apply include eligibility, then exclude always wins. force_include remains ignored by this compatibility policy.",
                    "Replace precedence with force_include highest: a forced file is selected even if excluded or not included. "
                    "Otherwise require include eligibility and no exclude match. Only supplied paths may appear in output.",
                    contracts, engine, policy, cases, preserved=(5, 6, 7, 8))


def _cors():
    contracts = """
        def load_request(data):
            if not isinstance(data, dict) or data.get("action", "apply") not in ("legacy", "apply"):
                raise ValueError("invalid action")
            if not isinstance(data.get("credentials"), bool):
                raise ValueError("credentials boolean required")
            origin = data.get("origin")
            if origin is not None and (not isinstance(origin, str) or not origin):
                raise ValueError("origin string or null required")
            allowed = data.get("allowed_origins")
            if not isinstance(allowed, list) or not all(isinstance(item, str) and item for item in allowed):
                raise ValueError("allowed origin list required")
            headers = data.get("headers")
            if not isinstance(headers, list):
                raise ValueError("header pairs required")
            for pair in headers:
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError("two element header pair required")
                if not all(isinstance(item, str) for item in pair) or not pair[0]:
                    raise ValueError("header strings required")
            return data
    """
    policy = """
        MODE = __MODE__
        BROKEN = __BROKEN__

        def allowance(request, mode):
            origin = request["origin"]
            if origin is None:
                return None
            wildcard = mode == "full-policy-replacement" and "*" in request["allowed_origins"]
            exact = origin in request["allowed_origins"] and origin != "*"
            if not wildcard and not exact:
                return None
            if wildcard and not request["credentials"]:
                return "*"
            return origin

        def vary_origin(value):
            tokens = []
            seen = set()
            for token in value.split(","):
                token = token.strip()
                if token and token.lower() not in seen:
                    seen.add(token.lower())
                    tokens.append(token)
            if "origin" not in seen:
                tokens.append("Origin")
            return ", ".join(tokens)

        def permit_credentials(request):
            return request["credentials"] and not BROKEN
    """
    engine = """
        from policy import MODE, allowance, permit_credentials, vary_origin

        def _headers(request, mode):
            headers = {}
            for name, value in request["headers"]:
                headers[name.lower()] = value
            if mode != "legacy":
                headers.pop("access-control-allow-origin", None)
                headers.pop("access-control-allow-credentials", None)
                allowed = allowance(request, mode)
                if allowed is not None:
                    headers["access-control-allow-origin"] = allowed
                    if permit_credentials(request):
                        headers["access-control-allow-credentials"] = "true"
                    if allowed != "*":
                        headers["vary"] = vary_origin(headers.get("vary", ""))
            return {"headers": [[name, headers[name]] for name in sorted(headers)]}

        def legacy(request):
            return _headers(request, "legacy")

        def apply(request):
            return _headers(request, MODE)
    """

    def inp(headers, origin="https://a.example", allowed=None, credentials=False, action="apply"):
        return {"action": action, "headers": headers, "origin": origin,
                "allowed_origins": ["https://a.example"] if allowed is None else allowed,
                "credentials": credentials}

    def answer(headers):
        return {"headers": headers}

    allow = "access-control-allow-origin"
    creds = "access-control-allow-credentials"
    cases = [
        (inp([["Content-Type", "text/plain"], ["Vary", "Accept-Encoding"]]),
         answer([[allow, "https://a.example"], ["content-type", "text/plain"], ["vary", "Accept-Encoding, Origin"]]),
         answer([[allow, "https://a.example"], ["content-type", "text/plain"], ["vary", "Accept-Encoding, Origin"]])),
        (inp([], allowed=["*"]), answer([]), answer([[allow, "*"]])),
        (inp([], allowed=["*"], credentials=True), answer([]),
         answer([[creds, "true"], [allow, "https://a.example"], ["vary", "Origin"]])),
        (inp([["Vary", " origin, Accept-Encoding, ORIGIN "]], credentials=True),
         answer([[creds, "true"], [allow, "https://a.example"], ["vary", "origin, Accept-Encoding"]]),
         answer([[creds, "true"], [allow, "https://a.example"], ["vary", "origin, Accept-Encoding"]])),
        (inp([[allow, "old"], [creds, "true"], ["X-Trace", "a"], ["x-trace", "b"]], origin="https://blocked.example"),
         answer([["x-trace", "b"]]), answer([["x-trace", "b"]])),
        (inp([[allow, "old"], ["Vary", "Accept"]], origin=None), answer([["vary", "Accept"]]), answer([["vary", "Accept"]])),
        (inp([["Access-Control-Allow-Origin", "legacy"], ["X-Trace", "keep"]], action="legacy"),
         answer([[allow, "legacy"], ["x-trace", "keep"]]), answer([[allow, "legacy"], ["x-trace", "keep"]])),
        (inp([["X-Z", "a"], ["x-z", "b"], ["Vary", "A"], ["vary", "B"]], credentials=True, action="legacy"),
         answer([["vary", "B"], ["x-z", "b"]]), answer([["vary", "B"], ["x-z", "b"]])),
        (inp([], origin="https://a.example.evil"), answer([]), answer([])),
        (inp([], allowed=["*", "https://a.example"]), answer([[allow, "https://a.example"], ["vary", "Origin"]]), answer([[allow, "*"]])),
    ]
    return _project("response-cors-middleware", "http_response_policy",
                    "headers is an array of [nonempty ASCII header-name, string value] pairs without CR/LF. origin is a "
                    "nonempty literal origin string or null, never '*'. allowed_origins is an array of literal origins or '*'. "
                    "credentials is boolean. Header names are ASCII letters/digits/hyphen; duplicates are allowed. "
                    "Vary values contain only comma-separated header-name tokens and surrounding whitespace; '*' is excluded.",
                    "Pure function only, no HTTP requests. Header names normalize to lowercase, last duplicate wins; output sorted header pairs. "
                    "OLD/legacy only normalizes and ignores all CORS settings, retaining any existing CORS headers. Keep legacy intact. "
                    "For NEW apply always remove old allow-origin/allow-credentials before recomputing; unrelated headers retain their values. "
                    "On accepted non-wildcard origin add Vary Origin, splitting the last Vary value on commas, trimming and case-insensitively "
                    "deduplicating tokens while retaining first spelling/order, and appending Origin if absent. Rejected/missing origin adds nothing. "
                    "Accepted credentialed requests add allow-credentials='true'; otherwise omit it.",
                    "Accept only an exact literal origin listed in allowed_origins. '*' entries are ignored. Echo accepted origin.",
                    "Allow '*' to match every non-null origin. With wildcard and credentials=false return allow-origin='*' and do not alter Vary. "
                    "With credentials=true echo the requesting origin and add Vary Origin. Wildcard wins over an accompanying exact allow entry; "
                    "without wildcard retain exact-match rules. Never combine credential permission with allow-origin='*'.",
                    contracts, engine, policy, cases, preserved=(6, 7, 8))


def build_projects():
    """Return six held-out project specifications; caller assigns task IDs/splits."""
    return [_slots(), _authorization(), _localization(), _indexing(), _packaging(), _cors()]
