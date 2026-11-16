"""main-v8-only reset-view overlay, pinned by value before any paid work.

The original pool exports remain inputs. Only the union of the two seeded
practice draws is attached to copies; missing views use the production reset
without a solver call. Reload validates the pinned value and never resets.
"""
from copy import deepcopy
import hashlib

from skillopt.continual_eval.core import require, safe_path
from skillopt.validator_pilot.api import digest

from . import alfworld_format, profiles as p, supply

KEY = 'alfworld_routing_overlay'
KIND = 'v222-alfworld-routing-overlay'


def _selection(items, harms, decomposition, runtime, configuration):
    require(p.is_v222(configuration), 'The practice routing overlay is main-v8 only (or its main-v9 successor)')
    runtime = alfworld_format.environment_runtime(runtime)
    require(isinstance(runtime.get('alfworld_data'), str), 'The overlay requires the pinned ALFWorld data root')
    root = safe_path(runtime['alfworld_data'])
    draws = {'harm': [row['task_id'] for row in harms], 'decomposition': decomposition['items']}
    require(all(18 <= len(ids) <= 20 and len(ids) == len(set(ids)) for ids in draws.values()),
            'The overlay keeps both actual ALFWorld practice denominators')
    ids = sorted(set(draws['harm']) | set(draws['decomposition']))
    by_id = {row['task_id']: row for row in items}
    require(len(by_id) == len(items) and set(ids) <= set(by_id), 'Overlay IDs belong to available practice')
    chosen, games = [by_id[key] for key in ids], {}
    for row in chosen:
        key = row['task_id']
        path = safe_path(row['public']['game_file'])
        sha = row['private'].get('game_sha256')
        require(path.is_relative_to(root) and isinstance(sha, str) and len(sha) == 64
                and set(sha) <= set('0123456789abcdef'), 'Each overlay game binds its root and original SHA256')
        games[key] = {'game_file': str(path), 'game_sha256': sha, 'source_item_sha256': digest(row)}
    binding = {'configuration': configuration, 'runtime_sha256': digest(runtime),
               'draws': draws, 'ids': ids, 'games': games}
    return chosen, runtime, binding


def _view(view):
    require(isinstance(view, dict) and set(view) == {'view', 'view_sha256', 'source'},
            'An overlay view carries its hash and origin')
    value = view['view']
    require(isinstance(value, dict) and set(value) == set(p.ALFWORLD_ROUTING_VIEW)
            and isinstance(value['initial_observation'], str) and isinstance(value['task_text'], str)
            and isinstance(value['admissible_commands_at_reset'], list)
            and all(isinstance(command, str) for command in value['admissible_commands_at_reset'])
            and view['view_sha256'] == digest(value)
            and view['source'] in ('frozen_export', 'main_v8_reset'), 'An intact public reset routing view')


def validate(value, *, items, harms, decomposition, runtime, configuration=p.MAIN_V8):
    chosen, environment, binding = _selection(items, harms, decomposition, runtime, configuration)
    require(isinstance(value, dict), 'main-v8 requires its prepared ALFWorld routing overlay before paid work')
    value = p.verified(value, KIND)
    require(value.get('binding') == binding and value.get('binding_sha256') == digest(binding),
            'The ALFWorld overlay binds the same games, draws, source rows and runtime')
    require(isinstance(value.get('views'), dict) and set(value['views']) == set(binding['ids'])
            and value.get('model_calls') == 0, 'The overlay covers exactly the selected union without model calls')
    for row in chosen:
        viewed = value['views'][row['task_id']]
        _view(viewed)
        if 'routing_view' in row['public']:
            require(viewed['source'] == 'frozen_export' and row.get('views_runtime_sha256') == digest(environment)
                    and viewed['view'] == row['public']['routing_view']
                    and viewed['view_sha256'] == row['public'].get('routing_view_sha256'),
                    'Existing frozen routing views remain exact')
        else:
            require(viewed['source'] == 'main_v8_reset', 'Only missing routing views use the overlay reset')
    return value


def prepare(items, harms, decomposition, *, runtime, value=None, forbidden_paths=(), configuration=p.MAIN_V8):
    """Check all selected game bytes first; reset missing views only on creation."""
    from .v222_smoke import _practice_path
    chosen, environment, binding = _selection(items, harms, decomposition, runtime, configuration)
    # Validate an existing record before any game-file reads. No native session
    # can be created on reload, even if its record is missing or damaged.
    if value is not None:
        validate(value, items=items, harms=harms, decomposition=decomposition, runtime=runtime,
                 configuration=configuration)
    paths = {key: _practice_path(game['game_file'], forbidden_paths=forbidden_paths)
             for key, game in binding['games'].items()}
    for key, path in paths.items():
        require(hashlib.sha256(path.read_bytes()).hexdigest() == binding['games'][key]['game_sha256'],
                'An overlay game differs from its pinned SHA256')
    if value is not None:
        return deepcopy(value)
    views, missing = {}, []
    root = safe_path(environment['alfworld_data'])
    for row in chosen:
        public, key = row['public'], row['task_id']
        if 'routing_view' in public:
            viewed = {'view': deepcopy(public['routing_view']),
                      'view_sha256': public.get('routing_view_sha256'), 'source': 'frozen_export'}
            _view(viewed)
            require(row.get('views_runtime_sha256') == digest(environment), 'Existing views use the frozen runtime')
            views[key] = viewed
        else:
            missing.append({'task_id': key, 'gamefile': str(paths[key].relative_to(root))})
    if missing:
        reset_views = supply.prereset(missing, {'union': missing}, reset=supply.alfworld_reset(root, environment))
        views.update({key: {**view, 'source': 'main_v8_reset'} for key, view in reset_views.items()})
    result = p.record(KIND, 'smoke', {'binding': binding, 'binding_sha256': digest(binding),
                                    'views': views, 'model_calls': 0})
    return validate(result, items=items, harms=harms, decomposition=decomposition, runtime=runtime,
                    configuration=configuration)


def attach(items, value, *, harms, decomposition, runtime, configuration=p.MAIN_V8):
    """Validate and attach to selected copies, without changing the available set."""
    value = validate(value, items=items, harms=harms, decomposition=decomposition, runtime=runtime,
                     configuration=configuration)
    rows = deepcopy(items)
    for row in rows:
        viewed = value['views'].get(row['task_id'])
        if viewed is not None:
            row['public'].update(routing_view=deepcopy(viewed['view']), routing_view_sha256=viewed['view_sha256'])
            row['views_runtime_sha256'] = value['binding']['runtime_sha256']
    return rows
