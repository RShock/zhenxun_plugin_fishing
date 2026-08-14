from __future__ import annotations

from types import SimpleNamespace

from zhenxun.plugins.zhenxun_plugin_fishing.models.user_mutations import (
    apply_try_claim_miracle,
)
from zhenxun.plugins.zhenxun_plugin_fishing.services.item_registry import (
    ItemType,
    get_item_on_user,
)


def test_miracle_still_settles_when_starry_frame_upgrade_is_maxed():
    user = SimpleNamespace(
        starry_frames=10,
        star_frames=0,
        starry_fish=[{"id": 999_999} for _ in range(7)] + [{"id": 777_784}],
        items={},
    )
    dirty: set[str] = set()

    claim = apply_try_claim_miracle(user, dirty)

    assert claim is not None
    assert user.starry_frames == 10
    assert user.star_frames == 1
    assert "star_frames" in dirty
    assert get_item_on_user(user, "star_frame", ItemType.STAR_FRAME) == {
        "item_id": ItemType.STAR_FRAME,
        "item_type": ItemType.STAR_FRAME,
        "count": 1,
    }
