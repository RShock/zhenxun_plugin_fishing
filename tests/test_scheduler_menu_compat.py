from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace


def test_database_ready_falls_back_when_host_has_no_is_initialized(monkeypatch):
    from zhenxun.plugins.zhenxun_plugin_fishing import scheduler as fishing_scheduler
    from zhenxun.services import db_context

    fake_tortoise = ModuleType("tortoise")
    fake_tortoise.Tortoise = SimpleNamespace(apps={"models": {}})
    monkeypatch.delattr(db_context, "is_initialized", raising=False)
    monkeypatch.setitem(sys.modules, "tortoise", fake_tortoise)

    assert fishing_scheduler._database_is_ready() is True
