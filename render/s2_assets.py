"""Shared, local S2 artwork. Missing assets are packaging errors, not emoji."""

from __future__ import annotations

import base64
import re
from functools import lru_cache
from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parents[1] / "resources/images/s2"
CHARA_ROOT = Path(__file__).resolve().parents[1] / "resources/images/chara"


@lru_cache(maxsize=256)
def get_s2_image_src(name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError(f"Invalid S2 asset name: {name!r}")
    payload = (ASSET_ROOT / f"{name}.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")


def get_s2_icon_src(key: str) -> str:
    return get_s2_image_src(f"tech_{key}")


@lru_cache(maxsize=32)
def get_chara_image_src(name: str) -> str:
    """读取正式角色图，供 S2 等页面复用，避免复制或用 emoji 代替。"""
    if not re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9_-]+", name):
        raise ValueError(f"Invalid character asset name: {name!r}")
    payload = (CHARA_ROOT / f"{name}.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")


def get_fatfish_image_src() -> str:
    return get_chara_image_src("大肥鱼")
