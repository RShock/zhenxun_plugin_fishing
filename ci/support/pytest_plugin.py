"""Early pytest plugin: install lightweight stubs before package/conftest import.

The plugin repo root is itself a Python package (has ``__init__.py`` that
imports nonebot). Pytest therefore imports that package before loading
``conftest.py``. This plugin hooks ``pytest_load_initial_conftests`` so stubs
exist first.
"""

from __future__ import annotations


def pytest_load_initial_conftests(early_config, parser, args):  # noqa: ARG001
    from support.nonebot_stub import install_lightweight_nonebot_stubs

    install_lightweight_nonebot_stubs()
