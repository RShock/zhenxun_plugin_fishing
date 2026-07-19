"""Repo-root conftest: install stubs before any plugin import (standalone CI)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_CI = _ROOT / "ci"
_RUNTIME = _CI / "runtime"

for path in (_RUNTIME, _CI, _ROOT):
    path_s = str(path)
    if path_s not in sys.path:
        sys.path.insert(0, path_s)

from support.nonebot_stub import install_lightweight_nonebot_stubs  # noqa: E402

install_lightweight_nonebot_stubs()
