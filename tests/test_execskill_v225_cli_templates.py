"""Parse actual operator-template argv with the production CLI; never run handlers."""
from collections import Counter
from itertools import product
from pathlib import Path
import re
import shlex

import pytest

from scripts import run_execskill as cli

OPS = Path(__file__).parent / 'fixtures/execskill/v225_ops'
TEMPLATES = ('m9-env.sh', 'm9-prep.sh', 'm9-smoke.sh', 'm9-launch.sh', 'm9-run.sh', 'm9-go.sh')
EXPECTED = {
    'm9-env.sh': [],
    'm9-prep.sh': ['v214-snapshot', 'verify-snapshot', 'sheet-runtime', 'v214-selftest', 'v214-s0'],
    'm9-smoke.sh': ['v214-manifest', 'v214-structural-smoke', 'v214-smoke-run', 'v214-smoke-summary'],
    'm9-launch.sh': ['v214-manifest'],
    'm9-run.sh': ['run'],
    'm9-go.sh': [],
}
ARRAY = '${M9_PRACTICE_OPTIONS[@]}'


def logical_lines(text):
    """Join shell continuations without executing substitutions or heredocs."""
    pending, start = '', 0
    for number, line in enumerate(text.splitlines(), 1):
        if not pending:
            start = number
        if line.endswith('\\'):
            pending += line[:-1] + ' '
        else:
            yield start, pending + line
            pending = ''
    assert not pending, 'An operator command ends in an incomplete continuation'


def shell_commands(text):
    functions, top, declared = {}, [], []
    body, heredoc = top, None
    for number, line in logical_lines(text):
        stripped = line.strip()
        if heredoc is not None:
            if stripped == heredoc:
                heredoc = None
            continue
        delimiter = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z_0-9]*)['\"]?", line)
        if delimiter:
            heredoc = delimiter.group(1)
            continue
        definition = re.fullmatch(r'(m9_\w+)\(\)\s*[({]', stripped)
        if definition:
            body = functions.setdefault(definition.group(1), [])
            continue
        if stripped in ('}', ')'):
            body = top
            continue
        if not re.match(r'^m9_\w+(?:\s|$)', stripped):
            continue
        tokens = shlex.split(stripped, comments=True)
        row = (number, tokens)
        body.append(row)
        if tokens[0] == 'm9_cli' or tokens[:1] == ['m9_step'] and len(tokens) > 2 and tokens[2] == 'm9_cli':
            declared.append(number)
    assert heredoc is None, 'An operator heredoc must close'

    def visit(rows, arguments=(), via=()):
        for number, raw in rows:
            tokens = []
            for token in raw:
                if token == '$@':
                    tokens.extend(arguments)
                elif re.fullmatch(r'\$[1-9]', token):
                    assert int(token[1:]) <= len(arguments), 'Wrapper argument is unbound'
                    tokens.append(arguments[int(token[1:]) - 1])
                else:
                    tokens.append(token)
            if tokens[0] == 'm9_step':
                tokens = tokens[2:]
            if tokens[0] == 'm9_cli':
                yield {'line': number, 'argv': tokens[1:], 'via': via}
            elif tokens[0] in functions:
                assert tokens[0] not in via, 'Recursive operator wrapper'
                yield from visit(functions[tokens[0]], tokens[1:], (*via, tokens[0]))

    found = list(visit(top))
    assert Counter(row['line'] for row in found) == Counter(declared), 'Every CLI declaration must be invoked exactly once'
    return found


def extracted_commands():
    return [{**row, 'file': name} for name in TEMPLATES
            for row in shell_commands((OPS / name).read_text())]


def arguments(row, *, chain='G', stage='S0', practice=False):
    variables = {'chain': chain, 'stage': stage, 'root': '/authored/smoke-' + chain,
                 'M9_HEAD': 'a' * 40, 'M9_PRE': '/authored path/preparation'}
    def value(match):
        name = match.group(1) or match.group(2)
        assert name.startswith('M9_') or name in variables, 'Unexpected shell variable: ' + name
        return variables.get(name, '/authored/' + name.lower())
    result = []
    for token in row['argv']:
        if token == ARRAY:
            if practice:
                result.extend(['--v222-practice-supply', '/authored/practice.json'])
        else:
            expanded = re.sub(r'\$\{([A-Za-z_]\w*)\}|\$([A-Za-z_]\w*)', value, token)
            assert '$' not in expanded, 'Unresolved command substitution: ' + expanded
            result.append(expanded)
    return result


COMMANDS = extracted_commands()
CASES = []
for row in COMMANDS:
    raw = ' '.join(row['argv'])
    for chain, stage, practice in product(('G', 'D') if '$chain' in raw else ('G',),
            ('S0', 'S1', 'S2', 'S3', 'SE6', 'SX') if '$stage' in raw else ('S0',),
            (False, True) if ARRAY in row['argv'] else (False,)):
        CASES.append(pytest.param(row, chain, stage, practice,
            id=f"{row['file']}:{row['argv'][0]}:{chain}:{stage}:supply-{practice}"))


def test_all_template_cli_commands_are_classified_and_s0_wrapper_is_invoked():
    for name, expected in EXPECTED.items():
        assert [row['argv'][0] for row in COMMANDS if row['file'] == name] == expected
    s0 = next(row for row in COMMANDS if row['argv'][0] == 'v214-s0')
    assert s0['via'], 'S0 must be extracted through its actual invoked locking wrapper'


@pytest.mark.parametrize('row,chain,stage,practice', CASES)
def test_actual_template_argv_is_accepted_by_production_argparse(row, chain, stage, practice):
    argv = arguments(row, chain=chain, stage=stage, practice=practice)
    parsed = cli.parser().parse_args(argv)
    if argv[0].startswith('v214-'):
        assert parsed.configuration == 'main-v9'
    if '--chain' in argv:
        assert parsed.chain == chain
    if '--stage' in argv:
        assert parsed.stage == stage
    if '--smoke-chain' in argv:
        assert parsed.smoke_chain == chain
    if ARRAY in row['argv']:
        assert parsed.v222_practice_supply == ('/authored/practice.json' if practice else None)
        assert parsed.out.startswith('/authored path/preparation/')


@pytest.mark.parametrize('command,flag,wrong', [
    ('v214-snapshot', '--source', '--snapshot-source'),
    ('verify-snapshot', '--list', '--snapshot'),
    ('sheet-runtime', '--engine-qualification', '--qualification'),
    ('v214-selftest', '--preparation', '--preparation-file'),
    ('v214-s0', '--snapshot', '--snapshot-root'),
])
def test_actual_argparse_rejects_misspelled_preparation_options(command, flag, wrong):
    row = next(row for row in COMMANDS if row['file'] == 'm9-prep.sh' and row['argv'][0] == command)
    argv = arguments(row)
    argv[argv.index(flag)] = wrong
    with pytest.raises(SystemExit) as error:
        cli.parser().parse_args(argv)
    assert error.value.code == 2


def test_missing_actual_s0_wrapper_call_cannot_pass_on_an_unused_definition():
    text = (OPS / 'm9-prep.sh').read_text()
    s0 = next(row for row in COMMANDS if row['argv'][0] == 'v214-s0')
    wrapper = s0['via'][0]
    changed, count = re.subn(r'(?m)^' + re.escape(wrapper) + r'\s*$', '# Authored missing invocation', text)
    assert count == 1
    with pytest.raises(AssertionError, match='must be invoked exactly once'):
        shell_commands(changed)
