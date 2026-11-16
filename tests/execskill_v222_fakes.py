"""Authored ALF game bytes and public reset views, only under pytest scratch."""
from copy import deepcopy
import hashlib

from skillopt.execskill import supply
from skillopt.validator_pilot.api import digest


def alf_rows(rows, root, *, runtime=None):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    runtime = runtime or {'alfworld_data': str(root), 'max_steps': 50, 'seed': 42}
    result = deepcopy(rows)
    for row in result:
        name = hashlib.sha256(row['task_id'].encode()).hexdigest() + '.game'
        path = root / name
        path.write_text('Authored game ' + row['task_id'])
        view = supply.routing_view('Authored room.\nYour task is to: look.', ['look'])
        row['public'] = {'game_file': str(path), 'routing_view': view, 'routing_view_sha256': digest(view)}
        row['private'] = {'game_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'game_metadata': {}}
        row['views_runtime_sha256'] = digest(runtime)
    return result, runtime
