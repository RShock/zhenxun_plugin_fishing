"""钓鱼命令通过 Web 公开路由入口的匹配行为测试。"""

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.commands import (
    COMMAND_DEFS,
    get_command_pattern,
    iter_command_aliases,
    iter_web_commands,
)
from zhenxun.plugins.zhenxun_plugin_fishing.web.command_router import (
    _COMMAND_TABLE,
    CommandRouter,
)


@pytest.fixture(scope="module")
def command_router() -> CommandRouter:
    return CommandRouter()


@pytest.mark.parametrize(
    ("command", "expected_name", "expected_groups"),
    [
        ("钓鱼", "钓鱼", (None,)),
        ("钓鱼11", "钓鱼", ("11",)),
        ("钓鱼 S1", "钓鱼", ("S1",)),
        ("收杆", "收杆", ()),
        ("收线", "收杆", ()),
        ("卖鱼", "卖鱼", (None,)),
        ("卖鱼 SSR", "卖鱼", ("SSR",)),
        ("升级钓杆", "升级钓竿", ()),
        ("升级渔钩", "升级鱼钩", ()),
        ("鱼店购买鱼饵 12", "购买", ("鱼饵", "12")),
        ("图鉴2", "图鉴", ("2",)),
        ("星空展馆", "星空鱼展馆", ()),
        ("白市交换 鲤鱼", "白商交换", ("鲤鱼",)),
        ("自动锁鱼 SSR", "自动锁鱼", ("SSR",)),
        ("钓鱼使用 时光药水 2", "使用物品", ("时光药水", "2")),
        ("天气状态 2", "天气", ("2",)),
        ("建设星空艇", "建设星空艇", ()),
        ("建设猫猫乐园", "建设猫猫乐园", (None,)),
        ("建设猫猫乐园1", "建设猫猫乐园", ("1",)),
        ("建设猫猫乐园 1", "建设猫猫乐园", ("1",)),
        ("建设猫猫乐园4567", "建设猫猫乐园", ("4567",)),
        ("建设猫猫乐园 4 5 6 7", "建设猫猫乐园", ("4 5 6 7",)),
        ("建设猫猫乐园猫屋", "建设猫猫乐园", ("猫屋",)),
        ("建设猫猫乐园 猫屋", "建设猫猫乐园", ("猫屋",)),
        ("设定鱼饵 玉米鱼饵", "设定鱼饵", ("玉米鱼饵",)),
        ("设置鱼饵 自动", "设定鱼饵", ("自动",)),
        ("卖出鱼饵 玉米鱼饵", "卖出鱼饵", ("玉米鱼饵",)),
        ("卖鱼饵 玉米鱼饵", "卖出鱼饵", ("玉米鱼饵",)),
        # “买鱼饵”是“鱼店购买”的前缀别名，与“卖出鱼饵 鱼饵名”对称
        ("买鱼饵 蚯蚓鱼饵 10", "购买", ("蚯蚓鱼饵", "10")),
        ("买鱼饵 黄金鱼饵", "购买", ("黄金鱼饵", None)),
        # 展示框万能升级的四个别名均路由到同一指令
        ("升级展示栏", "升级展示栏", ()),
        ("升级展示框", "升级展示栏", ()),
        ("升级木框", "升级展示栏", ()),
        ("升级星空展示框", "升级展示栏", ()),
    ],
)
def test_public_router_accepts_supported_commands(
    command_router: CommandRouter,
    command: str,
    expected_name: str,
    expected_groups: tuple,
):
    routed = command_router.find_matcher(command)

    assert routed is not None
    _, matched, name = routed
    assert name == expected_name
    assert matched is not None
    assert matched.groups() == expected_groups


@pytest.mark.parametrize(
    "command",
    [
        "钓鱼abc",
        "收杆现在",
        "图鉴3",
        "鱼店购买",
        "天气 3",
        "建设星空艇 extra",
        "完全未知的命令",
    ],
)
def test_public_router_rejects_invalid_or_trailing_input(
    command_router: CommandRouter, command: str
):
    assert command_router.find_matcher(command) is None


def test_public_command_registry_drives_web_and_plugin_metadata(command_router):
    web_commands = list(iter_web_commands())

    assert len(_COMMAND_TABLE) == len(web_commands)
    assert {command.name for command in web_commands} >= {"设定鱼饵", "卖出鱼饵"}
    assert "钓鱼公告" not in {command.name for command in web_commands}
    assert {"设定鱼饵", "卖出鱼饵", "钓鱼公告"} <= set(iter_command_aliases())
    assert all(not hasattr(command, "category") for command in COMMAND_DEFS)


@pytest.mark.asyncio
async def test_route_command_returns_user_facing_unknown_command_response(command_router):
    responses = await command_router.route_command("regex-user", "测试者", "完全未知")

    assert responses == [{"type": "text", "content": "未知指令，请输入钓鱼相关命令"}]
