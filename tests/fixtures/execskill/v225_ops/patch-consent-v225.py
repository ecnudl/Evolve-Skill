#!/usr/bin/env python3
"""Patch one reviewed consent-writer whitelist into a NEW reviewable source copy.

Never writes a consent. Supported consent fields use the exact arm literal or
read_arms_of(configuration), with configuration an unchanged function parameter
or a single args.configuration binding. Consent dictionaries explicitly set
sheet_test_qualification to True. Later protected-field/list mutations and
ambiguous dynamic updates require separate source review rather than patching.
"""
import argparse
import ast
import hashlib
from pathlib import Path

EXPECTED_ARMS = ('B', 'C0', 'C', 'S1', 'S2', 'S3', 'S4', 'S5', 'I', 'C_end')
PROTECTED_FIELDS = ('multi_arm_arms', 'sheet_test_qualification')


def _exact_arms(value):
    if isinstance(value, (ast.List, ast.Tuple)):
        return all(isinstance(item, ast.Constant) for item in value.elts) and tuple(item.value for item in value.elts) == EXPECTED_ARMS
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in ('list', 'tuple'):
        return len(value.args) == 1 and not value.keywords and _exact_arms(value.args[0])
    if not isinstance(value, ast.Call):
        return False
    is_reader = (isinstance(value.func, ast.Name) and value.func.id == 'read_arms_of'
                 or isinstance(value.func, ast.Attribute) and value.func.attr == 'read_arms_of')
    args = value.args
    if not args and len(value.keywords) == 1 and value.keywords[0].arg == 'configuration':
        args = [value.keywords[0].value]
    elif value.keywords:
        return False
    return is_reader and len(args) == 1 and isinstance(args[0], ast.Name) and args[0].id == 'configuration'


def _guard_mutations(tree, consent_dicts):
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    def scope(node):
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                return node
        return tree
    def protected(node):
        return (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant)
                and node.slice.value in PROTECTED_FIELDS)
    def valid_field(name, value):
        return _exact_arms(value) if name == 'multi_arm_arms' else isinstance(value, ast.Constant) and value.value is True
    for owner in {scope(node) for node in consent_dicts}:
        nodes = [node for node in ast.walk(owner) if scope(node) is owner]
        own_dicts = [node for node in consent_dicts if scope(node) is owner]
        # A same-spelled but rebound variable is not the caller's configuration.
        readers = [node for dictionary in own_dicts for node in ast.walk(dictionary)
                   if isinstance(node, ast.Call) and any(isinstance(arg, ast.Name) and arg.id == 'configuration'
                       for arg in [*node.args, *(kw.value for kw in node.keywords)])]
        if readers:
            arguments = getattr(owner, 'args', None)
            parameter = arguments is not None and any(arg.arg == 'configuration'
                for arg in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs])
            writes = [node for node in nodes if isinstance(node, ast.Name) and node.id == 'configuration'
                      and isinstance(node.ctx, (ast.Store, ast.Del))]
            if not parameter and not writes:
                writes = [node for node in ast.walk(tree) if scope(node) is tree and isinstance(node, ast.Name)
                          and node.id == 'configuration' and isinstance(node.ctx, (ast.Store, ast.Del))]
            assert not writes if parameter else len(writes) == 1, 'Consent configuration must be an unchanged parameter or one args.configuration binding'
            if writes:
                assignment = parents[writes[0]]
                value = getattr(assignment, 'value', None)
                assert isinstance(assignment, (ast.Assign, ast.AnnAssign)) and isinstance(value, ast.Attribute) \
                    and value.attr == 'configuration' and isinstance(value.value, ast.Name), 'Consent configuration cannot be rebound to a fixed or ambiguous value'
        containers, fields = set(), set()
        for _ in range(len(nodes) + 1):
            before = (set(containers), set(fields))
            for node in nodes:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names = {target.id for target in targets if isinstance(target, ast.Name)}
                if value in own_dicts or isinstance(value, ast.Name) and value.id in containers:
                    containers.update(names)
                getter = (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                    and isinstance(value.func.value, ast.Name) and value.func.value.id in containers
                    and value.func.attr == 'get' and value.args and isinstance(value.args[0], ast.Constant)
                    and value.args[0].value in PROTECTED_FIELDS)
                if protected(value) or getter or isinstance(value, ast.Name) and value.id in fields:
                    fields.update(names)
            if before == (containers, fields):
                break
        def field_value(node):
            return protected(node) or isinstance(node, ast.Name) and node.id in fields
        for node in nodes:
            if isinstance(node, ast.Delete):
                assert not any(protected(target) or isinstance(target, ast.Subscript)
                    and (field_value(target.value) or isinstance(target.value, ast.Name) and target.value.id in containers)
                    for target in node.targets), 'Consent protected fields cannot be deleted'
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    assert not (isinstance(node, ast.AugAssign) and isinstance(target, ast.Name)
                                and target.id in fields), 'Consent arm-list aliases cannot be mutated'
                    if protected(target):
                        assert not isinstance(node, ast.AugAssign) and valid_field(target.slice.value, node.value), 'Later consent field writes must preserve the registered arms and qualification'
                    elif isinstance(target, ast.Subscript) and (field_value(target.value)
                            or isinstance(target.value, ast.Name) and target.value.id in containers):
                        assert isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str) \
                            and target.slice.value not in PROTECTED_FIELDS and not field_value(target.value), 'Ambiguous consent field or arm-list writes require review'
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                receiver, method = node.func.value, node.func.attr
                assert not field_value(receiver), 'Later consent arm-list or qualification mutations require review'
                if isinstance(receiver, ast.Name) and receiver.id in containers:
                    if method in ('clear', 'popitem'):
                        raise AssertionError('Consent fields cannot be removed by a container mutation')
                    if method in ('pop', 'setdefault', '__setitem__', '__delitem__'):
                        assert node.args and isinstance(node.args[0], ast.Constant) \
                            and node.args[0].value not in PROTECTED_FIELDS, 'Consent protected-field mutation requires review'
                    if method == 'update':
                        assert not node.args and all(kw.arg is not None for kw in node.keywords), 'Dynamic consent updates require review'
                for keyword in node.keywords:
                    if keyword.arg in PROTECTED_FIELDS:
                        assert valid_field(keyword.arg, keyword.value), 'Later consent field writes must preserve the registered arms and qualification'


def patch(source, *, sha256, whitelist_line):
    assert hashlib.sha256(source.encode()).hexdigest() == sha256, 'Reviewed writer hash mismatch'
    assert '\n' not in whitelist_line and source.splitlines().count(whitelist_line) == 1, 'One exact reviewed whitelist line required'
    assert 'main-v9' not in source, 'Writer already names main-v9; review instead of repatching'
    token = "'main-v8'" if "'main-v8'" in whitelist_line else '"main-v8"'
    assert whitelist_line.count(token) == 1, 'Whitelist line names main-v8 exactly once'
    tree = ast.parse(source)
    number = source.splitlines().index(whitelist_line) + 1
    whitelists = [n for n in ast.walk(tree) if isinstance(n, (ast.Tuple, ast.List, ast.Set))
        and n.lineno <= number <= n.end_lineno
        and any(isinstance(v, ast.Constant) and v.value == 'main-v8' for v in n.elts)]
    assert len(whitelists) == 1, 'Reviewed line must extend one literal configuration whitelist'
    # Inspect the value actually emitted in each consent dictionary. An unrelated
    # read_arms_of call says nothing about that field's value.
    consent_dicts = [node for node in ast.walk(tree) if isinstance(node, ast.Dict)
        and any(isinstance(key, ast.Constant) and key.value == 'multi_arm_arms' for key in node.keys)]
    assert consent_dicts, 'Writer must emit multi_arm_arms in a consent dictionary'
    for node in consent_dicts:
        assert all(key is not None for key in node.keys), 'Consent dictionaries cannot hide field overrides in unpacking'
        fields = [(key.value, value) for key, value in zip(node.keys, node.values)
                  if isinstance(key, ast.Constant)]
        arms = [value for key, value in fields if key == 'multi_arm_arms']
        qualifications = [value for key, value in fields if key == 'sheet_test_qualification']
        assert len(arms) == 1 and _exact_arms(arms[0]), 'Consent arms must be read_arms_of(configuration) or the exact ten labels'
        assert len(qualifications) == 1 and isinstance(qualifications[0], ast.Constant) and qualifications[0].value is True, 'Consent must preserve sheet_test_qualification: True'
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in PROTECTED_FIELDS:
            valid = (_exact_arms(node.value) if node.arg == 'multi_arm_arms' else
                     isinstance(node.value, ast.Constant) and node.value.value is True)
            assert valid, 'Later consent arm writes must preserve the exact registered arms and qualification'
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) and target.slice.value in PROTECTED_FIELDS:
                    valid = (_exact_arms(node.value) if target.slice.value == 'multi_arm_arms' else
                             isinstance(node.value, ast.Constant) and node.value.value is True)
                    assert not isinstance(node, ast.AugAssign) and valid, 'Later consent arm writes must preserve the exact registered arms and qualification'
    _guard_mutations(tree, consent_dicts)
    replacement = whitelist_line.replace(token, token + ', ' + token.replace('main-v8', 'main-v9'))
    lines = source.splitlines(keepends=True)
    lines[number - 1] = replacement + ('\n' if lines[number - 1].endswith('\n') else '')
    result = ''.join(lines)
    ast.parse(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--writer', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--whitelist-line', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    from skillopt.execskill.profiles import MAIN_V9, read_arms_of
    assert tuple(read_arms_of(MAIN_V9)) == EXPECTED_ARMS, 'Review changed main-v9 read arms before patching'
    source, target = Path(args.writer), Path(args.out)
    assert source.resolve() != target.resolve() and not target.exists(), 'Write a new reviewable writer copy only'
    result = patch(source.read_text(), sha256=args.sha256, whitelist_line=args.whitelist_line)
    with target.open('x') as stream:
        stream.write(result)
    print('{"passed":true,"exit_code":0,"consent_written":false}')


if __name__ == '__main__':
    main()
