"""Shared, local S2 artwork. Missing assets are packaging errors, not emoji."""

from __future__ import annotations

import base64
import re
from functools import lru_cache
from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parents[1] / "resources/images/s2"


@lru_cache(maxsize=256)
def get_s2_image_src(name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError(f"Invalid S2 asset name: {name!r}")
    payload = (ASSET_ROOT / f"{name}.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")


def get_s2_icon_src(key: str) -> str:
    return get_s2_image_src(f"tech_{key}")
