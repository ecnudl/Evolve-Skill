#!/usr/bin/env python3
"""Fail-closed template patch for the operator's delegated consent writer.

The writer source is not present in this checkout. Supply its reviewed SHA256
and an exact whitelist line containing main-v7. Only that line gains main-v8;
no consent file is fabricated, no older run is rewritten, and the original
writer stays untouched. Review the output before installing it. The writer
must obtain arms from profiles.read_arms_of(configuration), including main-v8's
B/C0/C/F/stages, and retain sheet_test_qualification=True.
"""
import argparse
import ast
import hashlib
from pathlib import Path


def patch(source, *, sha256, whitelist_line):
    assert hashlib.sha256(source.encode()).hexdigest() == sha256, 'Reviewed writer hash mismatch'
    assert '\n' not in whitelist_line and source.splitlines().count(whitelist_line) == 1, 'One exact reviewed whitelist line required'
    assert 'main-v8' not in source, 'Writer already names main-v8; review instead of repatching'
    token = "'main-v7'" if "'main-v7'" in whitelist_line else '"main-v7"'
    assert whitelist_line.count(token) == 1, 'Whitelist line names main-v7 exactly once'
    tree = ast.parse(source)
    number = source.splitlines().index(whitelist_line) + 1
    whitelists = [node for node in ast.walk(tree) if isinstance(node, (ast.Tuple, ast.List, ast.Set))
                  and node.lineno <= number <= node.end_lineno
                  and any(isinstance(v, ast.Constant) and v.value == 'main-v7' for v in node.elts)]
    assert len(whitelists) == 1, 'Reviewed line must extend one literal configuration whitelist'
    assert 'read_arms_of' in source, 'Delegated writer must read the registered per-configuration arms'
    replacement = whitelist_line.replace(token, token + ', ' + token.replace('main-v7', 'main-v8'))
    lines = source.splitlines(keepends=True)
    suffix = '\n' if lines[number - 1].endswith('\n') else ''
    lines[number - 1] = replacement + suffix
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
    source, target = Path(args.writer), Path(args.out)
    assert source.resolve() != target.resolve() and not target.exists(), 'Write a new reviewable writer copy only'
    result = patch(source.read_text(), sha256=args.sha256, whitelist_line=args.whitelist_line)
    target.write_text(result)
    print('{"passed":true,"exit_code":0,"consent_written":false}')


if __name__ == '__main__':
    main()
