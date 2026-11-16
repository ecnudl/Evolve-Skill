"""Count-only segment coverage; the older feedback schema stays unchanged."""
from . import v221_rule, v222_cards


def coverage(batch, touched, per_procedure, package, *, incumbent=None):
    result = v221_rule.coverage(batch, touched, per_procedure)
    def segment(pid):
        source = package if pid in package.order else incumbent
        return source is not None and pid in source.order and v222_cards.is_segment(source.get(pid))
    result['segments'] = {pid: dict(row) for pid, row in result['procedures'].items() if segment(pid)}
    return result


def coverage_ok(value):
    if not isinstance(value, dict) or 'segments' not in value:
        return False
    core = {key: row for key, row in value.items() if key != 'segments'}
    return (v221_rule.coverage_ok(core) and isinstance(value['segments'], dict)
            and set(value['segments']) <= set(core['procedures'])
            and all(row == core['procedures'][pid] for pid, row in value['segments'].items()))


def cross_gate_ok(value):
    """Only bounded aggregate counts enter engineer feedback, never harm rows."""
    from .v222_gate import HARM_ITEMS
    if not (isinstance(value, dict) and set(value) == {'passed', 'benches'}
            and type(value['passed']) is bool and isinstance(value['benches'], dict)
            and len(value['benches']) == 4 and set(value['benches']) <= set(HARM_ITEMS)):
        return False
    for bench, row in value['benches'].items():
        if not (isinstance(row, dict) and {'fired', 'passed'} <= set(row)
                and set(row) <= {'fired', 'passed', 'fixed', 'broken', 'net'}
                and type(row['passed']) is bool and type(row['fired']) is int
                and 0 <= row['fired'] <= HARM_ITEMS[bench]):
            return False
        counts = set(row) & {'fixed', 'broken', 'net'}
        if counts and (counts != {'fixed', 'broken', 'net'}
                       or any(type(row[key]) is not int for key in counts)
                       or not 0 <= row['fixed'] + row['broken'] <= row['fired']
                       or min(row['fixed'], row['broken']) < 0
                       or row['net'] != row['fixed'] - row['broken']):
            return False
    return True
