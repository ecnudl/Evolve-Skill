"""Configuration-bound ALFWorld format rule; historical runtime sheets stay unchanged."""
from skillopt.continual_eval.core import require

from . import profiles as p

RULE = "alfworld-readable-action-v2-9-6"
CONFIGURATION_KEY = "execskill_configuration"
RULE_KEY = "alfworld_format_rule"


def validate(runtime, configuration=None):
    """Return whether the sheet opts into v2.9.6, refusing partial or mismatched identities.

    An unmarked historical sheet keeps the historical rule. Callers that know the
    run configuration additionally require its exact sheet identity, so a new run
    cannot silently use an unmarked parent sheet.
    """
    require(isinstance(runtime, dict), "An ALFWorld runtime is a mapping")
    marked = CONFIGURATION_KEY in runtime or RULE_KEY in runtime
    if configuration is not None:
        require(configuration in p.CONFIGURATIONS, "Unknown ALFWorld format configuration")
        if p.uses_readable_alf_format(configuration, 'alfworld'):
            require(marked, "The ALFWorld v2.9.6 format runtime is required")
        else:
            require(not marked, "A historical runtime cannot use the ALFWorld v2.9.6 format rule")
    if not marked:
        return False
    actual = runtime.get(CONFIGURATION_KEY)
    require(isinstance(actual, str) and actual in p.CONFIGURATIONS and p.uses_readable_alf_format(actual, 'alfworld')
            and (configuration is None or actual == configuration),
            "The ALFWorld format runtime has its exact configuration")
    require(runtime.get(RULE_KEY) == p.alfworld_format_rule(actual, 'alfworld') == RULE,
            "The ALFWorld format runtime has its exact rule")
    return True


def bind(runtime, configuration):
    """Copy a preparation sheet and bind only the new configuration's format rule.

    Existing markers must already agree; this never repairs a mismatched sheet.
    Historical sheets receive no additional fields.
    """
    require(isinstance(runtime, dict), "An ALFWorld runtime is a mapping")
    require(configuration in p.CONFIGURATIONS, "Unknown ALFWorld format configuration")
    if not p.uses_readable_alf_format(configuration, 'alfworld'):
        validate(runtime, configuration)
        return dict(runtime)
    if CONFIGURATION_KEY in runtime or RULE_KEY in runtime:
        validate(runtime, configuration)
        return dict(runtime)
    return {**runtime, CONFIGURATION_KEY: configuration, RULE_KEY: RULE}


def environment_runtime(runtime):
    """Return the unchanged environment sheet beneath a validated judge binding.

    The two judge-only fields do not change a prepared environment's reset views
    or their digest. Invalid bindings are refused before either field is removed.
    """
    validate(runtime)
    return {key: value for key, value in runtime.items() if key not in (CONFIGURATION_KEY, RULE_KEY)}
