"""Authored main-v6 completion records for v2.20 tests; no benchmark source data."""
from pathlib import Path

from skillopt.continual_eval.core import write_json
from skillopt.execskill import profiles as p, v220_import as imp
from skillopt.execskill.package import Package, Procedure, save


def main_v6_root(root, *, empty_chains=(), run='authored-main-v6'):
    root = Path(root)
    for chain in p.CHAINS:
        procedures = () if chain in empty_chains else (
            Procedure('p-officeqa-2-1', 'officeqa', 'Authored other-bench program',
                ('applies', 'before_call'),
                "def applies(view):\n    return view.get('bench') == 'officeqa'\n"
                "def before_call(view, state):\n    return {'notes': []}\n",
                imp.SOURCE_EVIDENCE, header='authored program', max_note_chars=100,
                policy_version=p.POLICY_VERSIONS[p.MAIN_V6]),)
        package = Package(procedures, chain + '/s5-alfworld', imp.SOURCE_EVIDENCE,
            parent_sha256='a' * 64, retired=('b' * 64,),
            narrowed={'p-officeqa-2-1': ('searchqa',)} if procedures else {},
            describer={'p-officeqa-2-1': {'prompt_sha256': 'c' * 64, 'text_sha256': 'd' * 64}} if procedures else {})
        save(root / chain, package)
        write_json(root / chain / 'chain-complete.json', p.record('chain-complete', imp.SOURCE_EVIDENCE,
            {'identity': {'run': run, 'chain': chain}, 'package_sha256': package.sha256,
             'steps': [str(i) * 64 for i in range(5)]}))
    return root


def pinned_source(root, *, empty_chains=()):
    return imp.pins(main_v6_root(Path(root) / 'main-v6', empty_chains=empty_chains))
