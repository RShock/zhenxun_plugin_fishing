"""
插件 matcher 定义模块。

将所有 Matcher 集中于此，供 __init__.py 和 handlers/ 引用。
普通指令正则模式统一从 commands.py 取，避免与 command_router.py 不一致。
GM 指令使用 on_command 前缀匹配（仅超管）。
"""

from nonebot import on_command, on_regex
from nonebot.permission import SUPERUSER

from .commands import get_command_pattern


def on_fishing_command(name: str, *, full_match: bool = True):
    pattern = get_command_pattern(name)
    suffix = r"\s*$" if full_match else ""
    return on_regex(rf"^\s*{pattern}{suffix}", priority=5, block=True)


fishing_matcher = on_fishing_command("钓鱼")
stop_fishing_matcher = on_fishing_command("收杆")
backpack_matcher = on_fishing_command("背包")
sell_fish_matcher = on_fishing_command("卖鱼")
shop_matcher = on_fishing_command("鱼店")
upgrade_rod_matcher = on_fishing_command("升级钓竿")
upgrade_hook_matcher = on_fishing_command("升级鱼钩")
buy_matcher = on_fishing_command("购买")
display_slot_matcher = on_fishing_command("升级展示栏")
status_matcher = on_fishing_command("钓鱼状态")

nest_matcher = on_fishing_command("打窝")
collection_matcher = on_fishing_command("图鉴")
starry_exhibition_matcher = on_fishing_command("星空鱼展馆")
exchange_matcher = on_fishing_command("兑换")
black_market_matcher = on_fishing_command("黑商交换")
white_market_matcher = on_fishing_command("白商")
white_market_exchange_matcher = on_fishing_command("白商交换")
lock_fish_matcher = on_fishing_command("锁鱼")
unlock_fish_matcher = on_fishing_command("解锁")
gift_fish_matcher = on_fishing_command("赠送", full_match=False)
auto_sell_matcher = on_fishing_command("自动卖鱼")
auto_lock_matcher = on_fishing_command("自动锁鱼")
rename_matcher = on_fishing_command("改名")
skin_matcher = on_fishing_command("更换皮肤")
# GM 指令仅超管使用，统一走 on_command 前缀匹配（与其它插件一致），避免正则/激活预筛漏匹配
gm_reset_matcher = on_command(
    "清空钓鱼数据", permission=SUPERUSER, priority=5, block=True
)
gm_force_stop_matcher = on_command(
    "gm收杆", permission=SUPERUSER, priority=5, block=True
)
gm_money_matcher = on_command(
    "gm钱钱", permission=SUPERUSER, priority=5, block=True
)
gm_give_gold_matcher = on_command(
    "gm发钱", permission=SUPERUSER, priority=5, block=True
)
# 长命令写在前面，避免与 gm添加 混淆（实际按首 token 精确匹配）
gm_add_skin_matcher = on_command(
    "gm添加皮肤", permission=SUPERUSER, priority=5, block=True
)
gm_add_item_matcher = on_command(
    "gm添加",
    aliases={"gm赠送"},
    permission=SUPERUSER,
    priority=5,
    block=True,
)
gm_set_gold_matcher = on_command(
    "gm设定金钱", permission=SUPERUSER, priority=5, block=True
)
gm_give_fish_matcher = on_command(
    "gm发鱼", permission=SUPERUSER, priority=5, block=True
)
gm_rollback_rod_matcher = on_command(
    "gm回退鱼竿", permission=SUPERUSER, priority=5, block=True
)
gm_rollback_hook_matcher = on_command(
    "gm回退鱼钩", permission=SUPERUSER, priority=5, block=True
)
gm_weather_reset_matcher = on_command(
    "gm天气重置", permission=SUPERUSER, priority=5, block=True
)
gm_weather_info_matcher = on_command(
    "gm天气", permission=SUPERUSER, priority=5, block=True
)
gm_check_achievements_matcher = on_command(
    "gm补成就", permission=SUPERUSER, priority=5, block=True
)
gm_limit_on_matcher = on_command(
    "gm限流开启", permission=SUPERUSER, priority=5, block=True
)
gm_limit_off_matcher = on_command(
    "gm限流关闭", permission=SUPERUSER, priority=5, block=True
)
test_render_matcher = on_regex(
    r"^\s*测试渲染(?:\s+(.+))?\s*$", permission=SUPERUSER, priority=5, block=True
)
test_scene_render_matcher = on_regex(
    r"^\s*测试场景渲染\s+((?:\d+)|[sS]1)\s*$",
    permission=SUPERUSER,
    priority=5,
    block=True,
)
debug_render_matcher = on_regex(
    r"^\s*钓鱼调试(?:\s*(开启|关闭|状态))?\s*$",
    permission=SUPERUSER,
    priority=5,
    block=True,
)
use_item_matcher = on_fishing_command("使用物品")
weather_forecast_matcher = on_fishing_command("天气")
cat_park_build_matcher = on_fishing_command("建设猫猫乐园")
build_starry_ship_matcher = on_fishing_command("建设星空艇")
fishing_announcement_matcher = on_regex(
    r"^\s*钓鱼公告(?:\s+(.+))?\s*$", permission=SUPERUSER, priority=5, block=True
)
set_bait_matcher = on_regex(
    r"^\s*设定鱼饵\s*(\S+)?\s*$",
    priority=1,
    block=True,
)
sell_bait_matcher = on_regex(
    r"^\s*卖出鱼饵\s*(\S+)?\s*$",
    priority=1,
    block=True,
)
