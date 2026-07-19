"""
物品使用分发表 — 表驱动，避免 handler 里 if/elif 链。

所有分发 handler 统一签名为 async fn(user_id, count, **kwargs) -> (bool, str|bytes)。
内部通过适配函数包装签名不一致的原始 handler。
"""

from __future__ import annotations

from typing import Callable


# 延迟导入，避免循环依赖
def _time_potion():
    from .potion_use import use_time_potion
    return use_time_potion

def _duoduo_potion():
    from .potion_use import use_duoduo_potion
    return use_duoduo_potion

async def _rollback_potion_adapter(user_id: str, count: int = 1, **kwargs):
    from .potion_use import use_rollback_potion
    return await use_rollback_potion(user_id)

async def _lucky_potion_adapter(user_id: str, count: int = 1, **kwargs):
    from .potion_use import use_lucky_potion
    return await use_lucky_potion(user_id, count)

async def _flash_potion_adapter(user_id: str, count: int = 1, **kwargs):
    from .potion_use import use_flash_potion
    return await use_flash_potion(user_id, count, **kwargs)

async def _utr_select_adapter(user_id: str, count: int = 1, **kwargs):
    from .potion_use import use_utr_select_ticket
    return await use_utr_select_ticket(user_id, count, **kwargs)

async def _corn_adapter(user_id: str, count: int = 1, **kwargs):
    from .nest import do_nest
    return await do_nest(user_id, count, **kwargs)

def _corn():
    return _corn_adapter

async def _frame_buff_adapter(user_id: str, count: int = 1, **kwargs):
    from .potion_use import use_display_frame_buff
    return await use_display_frame_buff(user_id, count, **kwargs)

def _frame_buff():
    return _frame_buff_adapter

async def _cat_frame_nest_adapter(user_id: str, count: int = 1, **kwargs):
    from .nest import do_cat_frame_nest
    return await do_cat_frame_nest(user_id, count, **kwargs)

def _cat_frame_nest():
    return _cat_frame_nest_adapter


# (aliases, handler_factory, is_image)
_ITEM_ENTRIES: list[tuple[list[str], Callable, bool]] = [
    (["时光药水", "时间药水"], _time_potion, True),
    (["真多多药水", "多多药水"], _duoduo_potion, False),
    (["回档药水", "回溯药水"], lambda: _rollback_potion_adapter, True),
    (["幸运药水"], lambda: _lucky_potion_adapter, False),
    (["闪光药水"], lambda: _flash_potion_adapter, False),
    (["UTR自选券", "utr自选券", "UTR券", "utr券"], lambda: _utr_select_adapter, False),
    (["香甜玉米", "玉米"], _corn, False),
    (["展示木框", "木框"], _frame_buff, False),
    (["猫猫框", "猫框"], _cat_frame_nest, False),
]

# 展开为 flat dict: name -> (handler_factory, is_image)
ITEM_DISPATCH: dict[str, tuple[Callable, bool]] = {}
for _aliases, _factory, _is_img in _ITEM_ENTRIES:
    for _alias in _aliases:
        ITEM_DISPATCH[_alias] = (_factory, _is_img)


def resolve_item_handler(item_name: str) -> tuple[Callable | None, bool]:
    """根据物品名查找处理函数和响应类型。

    Returns:
        (handler, is_image): handler 为 None 表示未知物品
    """
    entry = ITEM_DISPATCH.get(item_name)
    if entry is None:
        # 兼容去掉空格/全角空格
        compact = (item_name or "").replace(" ", "").replace("　", "")
        entry = ITEM_DISPATCH.get(compact)
    if entry is None:
        return None, False
    factory, is_image = entry
    return factory(), is_image
