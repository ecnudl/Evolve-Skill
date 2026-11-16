"""Conservative documentation-path audit for source-snapshot test inputs.

This recognizes literal paths, ordinary path joins and simple local aliases.
It is deliberately not a general Python/shell data-flow proof. Documentary
exceptions bind exact file bytes and exact findings; they permit no live input.
"""
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import tokenize


DOC_PATH = re.compile(r'(?<![\w])docs[/\\][^\s\"\'<>]+')


def _paths(value):
    if isinstance(value, (list, tuple)) and value and all(isinstance(v, str) for v in value):
        value = '/'.join(value)
    if not isinstance(value, str):
        return []
    return sorted({match.group().replace('\\', '/').rstrip('),.;:]}')
                   for match in DOC_PATH.finditer(value)})


def _join(values):
    return '/'.join(value.strip('/') for value in values if isinstance(value, str)) or None


def _value(node, names):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_value(item, names) for item in node.elts]
    if isinstance(node, ast.BinOp):
        left, right = _value(node.left, names), _value(node.right, names)
        if isinstance(node.op, ast.Div):
            return _join([left, right])
        if isinstance(node.op, ast.Add) and isinstance(left, str) and isinstance(right, str):
            return left + right
    if isinstance(node, ast.JoinedStr):
        return ''.join(str(_value(item.value, names) or '{dynamic}') if isinstance(item, ast.FormattedValue)
                       else str(item.value) for item in node.values)
    if isinstance(node, ast.Call):
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
        args = []
        for item in node.args:
            value = _value(item.value if isinstance(item, ast.Starred) else item, names)
            args.extend(value if isinstance(item, ast.Starred) and isinstance(value, (list, tuple)) else [value])
        if name in ('Path', 'PurePath', 'PurePosixPath', 'joinpath'):
            base = _value(node.func.value, names) if name == 'joinpath' else None
            return _join([base, *args])
        if name == 'join':
            separator = _value(node.func.value, names) if isinstance(node.func, ast.Attribute) else None
            if isinstance(separator, str) and len(args) == 1 and isinstance(args[0], (list, tuple)):
                return separator.join(str(value) for value in args[0])
            return _join(args)
    return None


def _finding(file, line, kind, path, expression):
    value = {'file':file, 'kind':kind, 'path':path, 'expression':expression}
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return {**value, 'line':line, 'fingerprint':hashlib.sha256(raw).hexdigest()}


def scan_source(file, source):
    """Return potential documentation references, without opening their targets."""
    result = []
    if file.endswith('.py'):
        tree = ast.parse(source)
        parents = {child:node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        names = {}
        for _ in range(3):
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    value = _value(node.value, names)
                    if value is not None:
                        names.update((target.id,value) for target in targets if isinstance(target,ast.Name))
        docstrings = {id(node.body[0].value) for node in ast.walk(tree)
            if isinstance(node,(ast.Module,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and node.body
            and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant)
            and isinstance(node.body[0].value.value,str)}
        candidates = {node:_paths(_value(node,names)) for node in ast.walk(tree)
                      if isinstance(node,(ast.Constant,ast.BinOp,ast.Call,ast.JoinedStr,ast.List,ast.Tuple))}
        candidates = {node:paths for node,paths in candidates.items() if paths}
        for node,paths in candidates.items():
            parent = parents.get(node)
            if parent in candidates:
                continue
            kind = 'documentary_text' if id(node) in docstrings else 'python_path'
            result.extend(_finding(file,node.lineno,kind,path,ast.unparse(node)) for path in paths)
        # The ops manifest's explicitly documentary directory must not become
        # an unreviewed live dependency through an otherwise opaque JSON read.
        for node in ast.walk(tree):
            if isinstance(node,ast.Subscript) and isinstance(node.slice,ast.Constant) \
                    and node.slice.value == 'source_directory':
                result.append(_finding(file,node.lineno,'documentary_directory_use',
                    '{documentary source_directory}',ast.unparse(node)))
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                result.extend(_finding(file,token.start[0],'documentary_text',path,token.string)
                              for path in _paths(token.string))
    elif file.endswith('.json'):
        def walk(value, pointer):
            if isinstance(value, dict):
                for key,item in value.items():
                    walk(item,pointer+'/'+str(key))
            elif isinstance(value,list):
                paths = _paths(value)
                if paths:
                    result.extend(_finding(file,0,'json_path',path,pointer) for path in paths)
                else:
                    for index,item in enumerate(value):
                        walk(item,pointer+'/'+str(index))
            elif isinstance(value,str):
                result.extend(_finding(file,0,'json_path',path,pointer) for path in _paths(value))
        walk(json.loads(source),'')
    else:
        for number,line in enumerate(source.splitlines(),1):
            # Adjacent quoted shell components remain detectable after quote removal.
            result.extend(_finding(file,number,'template_text',path,line.strip())
                          for path in _paths(line.replace('"','').replace("'",'')))
    return sorted(result,key=lambda row:(row['line'],row['path'],row['kind']))


def audit_source(file, source, policy):
    findings = scan_source(file,source)
    exception = policy.get('documentary_exceptions',{}).get(file)
    problems = []
    if exception and hashlib.sha256(source.encode()).hexdigest() != exception['sha256']:
        problems.append(file+': documentary exception bytes changed')
    allowed = set(exception['findings']) if exception else set()
    registered = {'/'.join(parts) for parts in policy['snapshot_kept_paths']}
    for finding in findings:
        if finding['path'] not in registered and finding['fingerprint'] not in allowed:
            problems.append('%s:%s: unregistered documentation reference %s' % (file,finding['line'],finding['path']))
    if exception and allowed != {row['fingerprint'] for row in findings if row['path'] not in registered}:
        problems.append(file+': documentary exception findings changed')
    return problems, findings


def audit_tree(root, policy):
    root = Path(root)
    files = set((root/'tests').glob('test_execskill_v225_*.py'))
    files.update((root/'tests').glob('execskill_v225_*.py'))
    for path in (root/'tests/fixtures/execskill').glob('v225*'):
        files.update([path] if path.is_file() else (item for item in path.rglob('*') if item.is_file()))
    problems, findings = [], []
    for path in sorted(files):
        errors, rows = audit_source(path.relative_to(root).as_posix(),path.read_text(),policy)
        problems.extend(errors)
        findings.extend(rows)
    missing = set(policy['documentary_exceptions'])-{path.relative_to(root).as_posix() for path in files}
    problems.extend('Missing documented exception source: '+name for name in sorted(missing))
    return {'files':len(files), 'problems':problems, 'findings':findings}
