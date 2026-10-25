"""Review regression: generic SearchQA smoke cannot bypass v2.7 profile guards."""
from types import SimpleNamespace

import pytest

from skillopt.execskill import budgets, profiles as p, step
from skillopt.execskill.package import empty
from tests.execskill_zpc_fakes import tmp_path


def valid_training_smoke():
    return step.SmokeStep(items=(), candidate=None, drill=None, model=p.CHAINS["D"], train=True)


@pytest.mark.parametrize("configuration", [p.ZEBRA_PC_V5, p.ALFWORLD_V2])
def test_generic_training_smoke_refused_before_step_or_path_access(monkeypatch, configuration):
    def forbidden(*args, **kwargs):
        pytest.fail("A generic smoke reached step construction or path access")
    monkeypatch.setattr(step, "_Step", forbidden)
    monkeypatch.setattr(step, "safe_path", forbidden)
    # No root is supplied: the profile guard must run before any root/path handling.
    setting = SimpleNamespace(extra={"configuration": configuration})
    parent = empty(step="smoke/s0", evidence="engineering_fixture")
    with pytest.raises(ValueError, match="dedicated smoke stages"):
        step.run_step(setting, budgets.SMOKE, "searchqa", 1, parent, services=None,
                      smoke=valid_training_smoke())


@pytest.mark.parametrize("configuration", [name for name in p.CONFIGURATIONS if not p.is_v27(name)])
def test_older_profiles_still_reach_generic_training_smoke_step(tmp_path, monkeypatch, configuration):
    reached = []
    def intercepted(*args):
        reached.append(args)
        raise RuntimeError("valid historical smoke reached _Step")
    monkeypatch.setattr(step, "_Step", intercepted)
    setting = SimpleNamespace(root=tmp_path, extra={"configuration": configuration})
    parent = empty(step="smoke/s0", evidence="engineering_fixture")
    mini = valid_training_smoke()
    with pytest.raises(RuntimeError, match="valid historical smoke reached _Step"):
        step.run_step(setting, budgets.SMOKE, "searchqa", 1, parent, services=None, smoke=mini)
    assert len(reached) == 1 and reached[0][-1] is mini


@pytest.mark.parametrize("configuration,bench", [(p.ZEBRA_PC_V5, "zebralogic"), (p.ALFWORLD_V2, "alfworld")])
def test_new_profiles_normal_d_step_still_reaches_step(tmp_path, monkeypatch, configuration, bench):
    def intercepted(*args):
        assert args[-1] is None
        raise RuntimeError("registered step reached _Step")
    monkeypatch.setattr(step, "_Step", intercepted)
    setting = SimpleNamespace(root=tmp_path, extra={"configuration": configuration})
    with pytest.raises(RuntimeError, match="registered step reached _Step"):
        step.run_step(setting, "D", bench, 1, empty(step="D/s0", evidence="engineering_fixture"), services=None)
