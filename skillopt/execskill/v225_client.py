"""Opt-in main-v9 route-B request shape; the frozen client and guards stay intact.

Keeping this adapter separate preserves every older client_source_sha pin.
The manifest pins this file for main-v9 D and pins all loaded source as usual.
"""
from copy import copy

from . import client, profiles as p


def options(configuration, chain='D'):
    return {'thinking': {'type': 'disabled'}} if p.is_v225(configuration) and chain == 'D' else {}


class RouteClient(client.NorthgateClient):
    """Route B with an explicit body option, using both inherited receipt guards."""

    def __init__(self, env_path, *, thinking, **kwargs):
        client._configured(thinking == {'type': 'disabled'}, 'main-v9 route B explicitly disables thinking')
        super().__init__(env_path, **kwargs)
        self.thinking = thinking['type']


def solver_client(model, *, configuration, config, transport=None):
    """The main-v9 adapter to solver_client; CONFIG_KEYS itself remains frozen."""
    client._configured(p.is_v225(configuration) and model == client.ELUCID_MODEL,
                       'The route thinking option belongs to main-v9 chain D only')
    client._configured(isinstance(config, dict)
                       and set(config) == client.CONFIG_KEYS[model] | {client.ROUTE_KEY, 'thinking'}
                       and config[client.ROUTE_KEY] == client.ROUTE_B,
                       'main-v9 D requires the registered route-B config and thinking option')
    return RouteClient(config['env_path'], thinking=config['thinking'], proxy=config['proxy'],
                       max_tokens=config['max_tokens'], read_timeout=config['read_timeout'], transport=transport)


def control_client(registered):
    """S1-e keeps the registered route/transport and receipt guard, omitting both controls."""
    client._configured(isinstance(registered, RouteClient) and registered.route == client.ROUTE_B
                       and registered.thinking == 'disabled' and registered.effort == 'none',
                       'main-v9 S1-e starts from the registered route-B client')
    control = copy(registered)
    control.thinking = control.effort = None
    return control
