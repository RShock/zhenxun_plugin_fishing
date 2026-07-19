# ── 模块级导入前 mock：必须在导入任何插件模块前生效 ────────────────────────────
from unittest.mock import MagicMock

from tests.support.nonebot_stub import install_lightweight_nonebot_stubs

# 根 conftest 会在插件包导入前安装一次；这里再调用一遍保证直接导入本文件时也安全。
install_lightweight_nonebot_stubs()

from unittest.mock import AsyncMock

import pytest

from .mock_db import MockDB

FISHING_PKG = "zhenxun.plugins.zhenxun_plugin_fishing"


@pytest.fixture
def db():
    return MockDB()


@pytest.fixture(autouse=True)
def mock_all(db, monkeypatch):
    _patch_models(db, monkeypatch)
    _patch_render(monkeypatch)
    _patch_nonebot(monkeypatch)
    _patch_zhenxun_db(monkeypatch)
    _reset_config_cache()


def _patch_models(db, monkeypatch):

    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_or_create_user", db.user_get_or_create
    )
    monkeypatch.setattr(f"{FISHING_PKG}.models.FishingUser.get_user", db.user_get)
    monkeypatch.setattr(f"{FISHING_PKG}.models.FishingUser.add_gold", db.user_add_gold)
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.reduce_gold", db.user_reduce_gold
    )
    monkeypatch.setattr(f"{FISHING_PKG}.models.FishingUser.add_corn", db.user_add_corn)
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.reduce_corn", db.user_reduce_corn
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.check_and_sign", db.user_check_and_sign
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.increment_stop_count",
        db.user_increment_stop_count,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_stop_count", db.user_get_stop_count
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.increment_sell_count",
        db.user_increment_sell_count,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_sell_count", db.user_get_sell_count
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.add_display_frames",
        db.user_add_display_frames,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.increment_nest_count",
        db.user_increment_nest_count,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_nest_count", db.user_get_nest_count
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.increment_gift_count",
        db.user_increment_gift_count,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_gift_count", db.user_get_gift_count
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_owned_skins", db.user_get_owned_skins
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.change_skin", db.user_change_skin
    )
    monkeypatch.setattr(f"{FISHING_PKG}.models.FishingUser.reset_user", db.user_reset)
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.start_fishing", db.status_start_fishing
    )
    monkeypatch.setattr(f"{FISHING_PKG}.models.FishingUser.get_status", db.status_get)
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.stop_fishing", db.status_stop_fishing
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.update_fishing_status",
        db.status_update_fishing_status,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.is_fishing", db.status_is_fishing
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_location_fishers",
        db.status_get_location_fishers,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.clear_user_status", AsyncMock()
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.add_fish", db.backpack_add_fish
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_user_fish", db.backpack_get_user_fish
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_fish_by_numeric_id",
        db.backpack_get_fish_by_numeric_id,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.remove_fish_by_numeric_id",
        db.backpack_remove_fish_by_numeric_id,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.toggle_lock_by_numeric_id",
        db.backpack_toggle_lock,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.lock_by_rarity",
        db.backpack_lock_by_rarity,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.unlock_by_rarity",
        db.backpack_unlock_by_rarity,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.lock_by_location_prefix",
        db.backpack_lock_by_location_prefix,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.unlock_by_location_prefix",
        db.backpack_unlock_by_location_prefix,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.lock_all",
        db.backpack_lock_all,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.unlock_all",
        db.backpack_unlock_all,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.clear_user_backpack", db.backpack_clear
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.filter_fish", db.backpack_filter_fish
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.delete_fish_entries",
        db.backpack_delete_fish_entries,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_unlocked_fish",
        db.backpack_get_unlocked_fish,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_user_displays",
        db.display_get_user_displays,
    )
    monkeypatch.setattr(f"{FISHING_PKG}.models.FishingUser.set_display", db.display_set)
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.remove_display", db.display_remove
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.clear_user_displays", db.display_clear
    )
    monkeypatch.setattr(f"{FISHING_PKG}.models.FishingUser.add_item", db.items_add)
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_user_items", db.items_get_user_items
    )
    monkeypatch.setattr(f"{FISHING_PKG}.models.FishingUser.get_item", db.items_get_item)
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.remove_item", db.items_remove
    )
    monkeypatch.setattr(f"{FISHING_PKG}.models.FishingUser.has_item", db.items_has)
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.clear_user_items", db.items_clear
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.is_achievement_completed",
        db.achievement_is_completed,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.mark_achievement_completed",
        db.achievement_mark_completed,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_user_achievements",
        db.achievement_get_user_achievements,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.mark_collected", db.collection_mark_collected
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_user_collected",
        db.collection_get_user_collected,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_user_collected_with_count",
        db.collection_get_user_collected_with_count,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.is_collected", db.collection_is_collected
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.clear_user_collection",
        db.collection_clear_user_collection,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.clear_all_user_data", db.user_clear_all_data
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingExchangeRecord.create_black_record",
        db.exchange_create_black_record,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingExchangeRecord.list_active_records",
        db.exchange_list_active_records,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingExchangeRecord.find_active_reverse",
        db.exchange_find_active_reverse,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingExchangeRecord.invalidate_record",
        db.exchange_invalidate_record,
    )
    monkeypatch.setattr(f"{FISHING_PKG}.models.FishingUser.add_skin", db.user_add_skin)
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.reduce_display_frames",
        db.user_reduce_display_frames,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.has_unlocked_lost_wind",
        db.has_unlocked_lost_wind,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_auto_sell", db.user_get_auto_sell
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_auto_sell_rarity",
        db.user_get_auto_sell_rarity,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.set_auto_sell_rarity",
        db.user_set_auto_sell_rarity,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_auto_lock", db.user_get_auto_lock
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_auto_lock_pattern",
        db.user_get_auto_lock_pattern,
    )

    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingBuff.add_user_buff", db.buff_add_user_buff
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingBuff.add_location_buff", db.buff_add_location_buff
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingBuff.get_active_buffs_for_fishing",
        db.buff_get_active_buffs_for_fishing,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingBuff.get_location_buff_count",
        db.buff_get_location_buff_count,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingBuff.get_global_buff_count",
        db.buff_get_global_buff_count,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingBuff.add_global_buff",
        db.buff_add_global_buff,
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingBuff.get_active_user_buff",
        db.buff_get_active_user_buff,
    )
    monkeypatch.setattr(f"{FISHING_PKG}.models.FishingBuff.filter", MagicMock())
    monkeypatch.setattr(f"{FISHING_PKG}.models.FishingUser.filter", MagicMock())

    mock_wq = MagicMock()
    mock_wq.first = AsyncMock(return_value=None)
    mock_wq.all = AsyncMock(return_value=[])
    mock_wq.count = AsyncMock(return_value=10)
    mock_wq.filter = MagicMock(return_value=mock_wq)
    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingWeather.filter",
        MagicMock(return_value=mock_wq),
    )

    monkeypatch.setattr(
        f"{FISHING_PKG}.weather_service.ensure_weather_generated", AsyncMock()
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.core.actions.ensure_weather_generated", AsyncMock()
    )

    mock_query = MagicMock()
    mock_query.first = AsyncMock(return_value=None)
    mock_query.all = AsyncMock(return_value=[])
    mock_query.count = AsyncMock(return_value=0)
    mock_query.filter = MagicMock(return_value=mock_query)
    mock_query.exclude = MagicMock(return_value=mock_query)
    mock_query.order_by = MagicMock(return_value=mock_query)
    mock_query.limit = MagicMock(return_value=mock_query)
    mock_query.offset = MagicMock(return_value=mock_query)
    mock_query.values = AsyncMock(return_value=[])
    mock_query.exists = AsyncMock(return_value=False)

    for model_name in ["FishingBuff", "FishingUser"]:
        monkeypatch.setattr(
            f"{FISHING_PKG}.models.{model_name}.filter",
            MagicMock(return_value=mock_query),
        )
        monkeypatch.setattr(
            f"{FISHING_PKG}.models.{model_name}.all",
            AsyncMock(return_value=[]),
        )

    monkeypatch.setattr(
        f"{FISHING_PKG}.models.FishingUser.get_location_fisher_counts",
        AsyncMock(return_value={}),
    )


def _patch_render(monkeypatch):
    async def _fake_render_html(html, width=300):
        return b"FAKE_IMAGE_BYTES"

    for mod in [
        f"{FISHING_PKG}.render.base",
        f"{FISHING_PKG}.render.fishing_scene",
        f"{FISHING_PKG}.render.fishing_result",
        f"{FISHING_PKG}.render.fishing_status",
        f"{FISHING_PKG}.render.backpack",
        f"{FISHING_PKG}.render.shop",
        f"{FISHING_PKG}.render.collection",
        f"{FISHING_PKG}.render.misc",
        f"{FISHING_PKG}.render",
        f"{FISHING_PKG}.utils",
    ]:
        monkeypatch.setattr(f"{mod}.render_html", _fake_render_html, raising=False)

    def _fake_render_template(*args, **kwargs):
        return "<html>fake</html>"

    for mod in [f"{FISHING_PKG}.render.base", f"{FISHING_PKG}.render"]:
        monkeypatch.setattr(
            f"{mod}.render_template", _fake_render_template, raising=False
        )

    async def _fake_html_to_pic(html, **kwargs):
        return b"FAKE_IMAGE_BYTES"

    monkeypatch.setattr(
        "nonebot_plugin_htmlrender.html_to_pic", _fake_html_to_pic, raising=False
    )


def _patch_nonebot(monkeypatch):
    mock_logger = MagicMock()
    monkeypatch.setattr(f"{FISHING_PKG}.fishing.logger", mock_logger, raising=False)
    monkeypatch.setattr(f"{FISHING_PKG}.shop.logger", mock_logger, raising=False)
    monkeypatch.setattr(f"{FISHING_PKG}.backpack.logger", mock_logger, raising=False)
    monkeypatch.setattr(f"{FISHING_PKG}.gm.logger", mock_logger, raising=False)
    monkeypatch.setattr(
        f"{FISHING_PKG}.core.actions.logger", mock_logger, raising=False
    )
    monkeypatch.setattr(f"{FISHING_PKG}.core.scene.logger", mock_logger, raising=False)
    monkeypatch.setattr(f"{FISHING_PKG}.core.potion.logger", mock_logger, raising=False)
    monkeypatch.setattr(
        f"{FISHING_PKG}.shop.purchase.logger", mock_logger, raising=False
    )
    monkeypatch.setattr(f"{FISHING_PKG}.shop.nest.logger", mock_logger, raising=False)
    monkeypatch.setattr(
        f"{FISHING_PKG}.shop.potion_use.logger", mock_logger, raising=False
    )
    monkeypatch.setattr(f"{FISHING_PKG}.shop.misc.logger", mock_logger, raising=False)
    monkeypatch.setattr(
        f"{FISHING_PKG}.backpack.sell.logger", mock_logger, raising=False
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.backpack.gift.logger", mock_logger, raising=False
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.services.user_service.logger", mock_logger, raising=False
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.services.display_service.logger", mock_logger, raising=False
    )
    monkeypatch.setattr(
        f"{FISHING_PKG}.services.achievement_service.logger", mock_logger, raising=False
    )

    mock_console = MagicMock()
    mock_console.add_gold = AsyncMock()
    import zhenxun.models.user_console as user_console

    user_console.UserConsole = mock_console


def _patch_zhenxun_db(monkeypatch):
    pass


def _reset_config_cache():
    from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager

    ConfigManager._locations = None
    ConfigManager._fish = None
    ConfigManager._shop = None


# ── 覆盖根 conftest 的 _init_bot，避免触发 nonebug → 真实 nonebot 冲突 ──
@pytest.fixture(scope="session", autouse=True)
def _init_bot():
    """覆盖根 conftest 的 _init_bot，避免加载 nonebug/nonebot 真实例。"""
    pass


# ── 覆盖 nonebug 插件的 autouse session 夹具 ──
# nonebug 通过 pytest 插件机制注册了 _nonebot_init / after_nonebot_init / nonebug_init
# 三个 autouse session 夹具，它们会调用 nonebot.init() 和 ASGIMixin isinstance 检查。
# 在这里用空夹具覆盖，防止与 MagicMock 的 nonebot 冲突。
@pytest.fixture(scope="session", autouse=True)
def _nonebot_init():
    """覆盖 nonebug._nonebot_init，避免调用 nonebot.init()。"""
    pass


@pytest.fixture(scope="session", autouse=True)
async def after_nonebot_init():
    """覆盖 nonebug.after_nonebot_init。"""
    pass


@pytest.fixture(scope="session", autouse=True)
async def nonebug_init():
    """覆盖 nonebug.nonebug_init，避免 lifespan 初始化。"""
    pass
