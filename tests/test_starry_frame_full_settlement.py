from __future__ import annotations

from types import SimpleNamespace

from zhenxun.plugins.zhenxun_plugin_fishing.core.actions import (
    _apply_miracle_claims,
)
from zhenxun.plugins.zhenxun_plugin_fishing.models.user_mutations import (
    apply_try_claim_miracle,
    apply_try_claim_miracles,
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


def test_miracles_keep_settling_and_accumulate_extra_frames_after_max_level():
    def miracle_group():
        return [{"id": 999_999} for _ in range(7)] + [{"id": 777_784}]

    user = SimpleNamespace(
        starry_frames=10,
        star_frames=10,
        starry_fish=miracle_group() + miracle_group(),
        items={},
    )
    dirty: set[str] = set()

    claims = apply_try_claim_miracles(user, dirty=dirty)

    assert len(claims) == 2
    assert user.starry_frames == 10
    assert user.star_frames == 12
    assert user.starry_fish == []
    assert "star_frames" in dirty


def test_full_starry_frame_does_not_claim_upgrade_hint(monkeypatch):
    from zhenxun.plugins.zhenxun_plugin_fishing.models import user_mutations

    monkeypatch.setattr(
        user_mutations,
        "apply_try_claim_miracles",
        lambda user, dirty=None: [
            {"subset_count": 1, "consumed_ids": ["999999"], "star_frames": 11}
        ],
    )
    plan = SimpleNamespace(
        user=SimpleNamespace(starry_frames=10),
        dirty=set(),
        miracle_info=None,
    )

    _apply_miracle_claims(plan)

    assert plan.miracle_info["can_upgrade_starry_frame"] is False
