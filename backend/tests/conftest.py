import pytest


@pytest.fixture(scope="module")
def monkeymodule():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(autouse=True, scope="module")
def _legacy_pw_gate(request):
    """Older in-process suites create admin-set passwords and skip the forced change; the live server keeps the gate."""
    import sys
    srv = sys.modules.get("server")
    if srv is None or getattr(request.module, "KEEP_PW_GATE", False):
        yield
        return
    srv.ENFORCE_PW_CHANGE = False
    yield
    srv.ENFORCE_PW_CHANGE = True
