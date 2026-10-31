"""main-v6 split-evaluation cells and the inherited Zebra v15 role ceilings."""
from copy import deepcopy

LEARNED = ('searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench')
SPLIT_MAX = 3
GENERATED_MAX = {'searchqa': 0, 'officeqa': 60, 'zebralogic': 0, 'spreadsheetbench': 60}


def read_unit_caps(p):
    """One complete registered read unit, including all worst-case stage arms."""
    return {bench: p.legacy._round_up(p.MAIN_CAP_FACTOR * (
        p.CELL_ANCHORS[bench][1] * (cards + p.PROCEDURE_ARM_FACTOR[1] * procedures)
        + p.MAIN_RESERVATIONS * p.READ_RESERVATION), p.MILLION)
        for bench, (cards, procedures) in p.TEST_READ_CELLS[p.MAIN_V5].items()}


def split_cells(p):
    return {bench: {
        'selftest': 2 * SPLIT_MAX * p.train_rounds(p.MAIN_V6, bench)
                    * (p.slice_spec(p.MAIN_V6, bench)['run'][0] + GENERATED_MAX[bench]),
        'confirm': 2 * SPLIT_MAX * p.train_rounds(p.MAIN_V6, bench)
                   * p.confirm_spec(p.MAIN_V6, bench, 1)['items']}
        for bench in LEARNED}


def extend(p):
    child, parent = p.MAIN_V6, p.MAIN_V5
    # Existing main-v5 solver cells include Zebra's earlier OfficeQA self-test.
    # v15 changes engineer/audit budgets, not those solver cells.
    for bench, additions in split_cells(p).items():
        for kind, extra in additions.items():
            schedule = p.CONFIG_SCHEDULE_CELLS[child][bench][kind]
            cards, procedures = schedule.get(bench, (0, 0))
            schedule[bench] = (cards, procedures + extra)
            derived = p.legacy._round_up(p.MAIN_CAP_FACTOR * (
                sum(p.CELL_ANCHORS[b][1] * (c + p.PROCEDURE_ARM_FACTOR[1] * n)
                    for b, (c, n) in schedule.items())
                + p.MAIN_RESERVATIONS * p.READ_RESERVATION), 100000)
            p.CONFIG_STEP_CAPS[child][bench][kind] = max(p.CONFIG_STEP_CAPS[parent][bench][kind], derived)
    p.CONFIGURATIONS[child]['redo_reserve'] = max(
        p.CONFIGURATIONS[parent]['redo_reserve'],
        *(cap for row in p.CONFIG_STEP_CAPS[child].values() for cap in row.values()))
    # Every read attempt charges :test, so its retry must be funded there.
    # Keep :redo intact for the existing learning step-kind retries.
    p.CONFIGURATIONS[child]['test_read_cap'] = (
        p.CONFIGURATIONS[parent]['test_read_cap'] + max(read_unit_caps(p).values()))
    p.CONFIGURATIONS[child]['solver_cap'] = p.legacy._round_up(
        sum(sum(row.values()) for row in p.CONFIG_STEP_CAPS[child].values())
        + p.CONFIGURATIONS[child]['test_read_cap'] + p.CONFIGURATIONS[child]['redo_reserve'],
        5 * p.MILLION)
    p.CONFIG_GLM_CAP[child] = (p.CONFIG_GLM_CAP[parent]
        + p.CONFIG_GLM_CAP[p.ZEBRA_PC_V15] - p.CONFIG_GLM_CAP[p.ZEBRA_PC_V13])
    p.CONFIG_ROLE_CAPS[child] = {role: max(value, p.CONFIG_ROLE_CAPS[p.ZEBRA_PC_V15][role])
        for role, value in p.CONFIG_ROLE_CAPS[parent].items()}


def identity():
    from . import profiles as p
    return {'maximum_subcandidates': SPLIT_MAX, 'runs_per_item': 1,
        'paired_cells_per_item': 2, 'generated_max': deepcopy(GENERATED_MAX),
        'extra_procedure_cells': split_cells(p),
        'cell_formula': '2*k_max*rounds*items; train items include admitted G_self',
        'cap_formula': 'ceil_100000(3*(sum(high_anchor*(card+1.6*procedure))+16*520192))',
        'read_retry': {'base_read_cap': p.CONFIGURATIONS[p.MAIN_V5]['test_read_cap'],
                       'unit_caps': read_unit_caps(p), 'reserve': max(read_unit_caps(p).values()),
                       'charged_scope': '<chain>:test', 'learning_redo_unchanged': True},
        'missing_incumbent': 'Both cells may be absent after whole-candidate identical-request skipping; price both.',
        'zebra_v13_to_v15_method_delta': p.CONFIG_GLM_CAP[p.ZEBRA_PC_V15] - p.CONFIG_GLM_CAP[p.ZEBRA_PC_V13]}
