"""用户级共享异步锁的并发、嵌套与回收行为。"""

import ast
import asyncio
from pathlib import Path

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.services import (
    user_lock_service as lock_service,
)
from zhenxun.plugins.zhenxun_plugin_fishing.services.user_lock_service import (
    UserOperationBusyError,
    active_user_lock_count,
    event_user_and_at_ids,
    user_operation_lock,
)


async def test_same_user_operations_are_serialized():
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    order: list[str] = []

    async def first():
        async with user_operation_lock(["u1"], "收杆"):
            order.append("first-enter")
            first_entered.set()
            await release_first.wait()
            order.append("first-exit")

    async def second():
        await first_entered.wait()
        async with user_operation_lock(["u1"], "卖鱼"):
            order.append("second-enter")

    first_task = asyncio.create_task(first(), name="first-operation")
    second_task = asyncio.create_task(second(), name="second-operation")
    await first_entered.wait()
    await asyncio.sleep(0)
    assert order == ["first-enter"]

    release_first.set()
    await asyncio.gather(first_task, second_task)

    assert order == ["first-enter", "first-exit", "second-enter"]
    assert active_user_lock_count() == 0


async def test_different_users_do_not_block_each_other():
    both_entered = asyncio.Event()
    entered: set[str] = set()

    async def operation(user_id: str):
        async with user_operation_lock([user_id], "并发功能"):
            entered.add(user_id)
            if len(entered) == 2:
                both_entered.set()
            await asyncio.wait_for(both_entered.wait(), timeout=1)

    await asyncio.gather(operation("u1"), operation("u2"))

    assert entered == {"u1", "u2"}
    assert active_user_lock_count() == 0


async def test_same_lock_can_be_reused_in_nested_business_call():
    async with user_operation_lock(["u1"], "外层"):
        async with user_operation_lock(["u1"], "内层"):
            assert active_user_lock_count() == 1

    assert active_user_lock_count() == 0


async def test_child_task_inheriting_context_must_wait_for_parent_lock():
    child_started = asyncio.Event()
    child_entered = asyncio.Event()

    async def child():
        child_started.set()
        async with user_operation_lock(["u1"], "子任务"):
            child_entered.set()

    async with user_operation_lock(["u1"], "父任务"):
        child_task = asyncio.create_task(child(), name="inherited-context-child")
        await child_started.wait()
        await asyncio.sleep(0)
        assert not child_entered.is_set()

    await asyncio.wait_for(child_task, timeout=1)
    assert child_entered.is_set()
    assert active_user_lock_count() == 0


@pytest.mark.parametrize(
    ("warning_threshold", "expected_level"), [(0.5, "debug"), (0.0, "warning")]
)
async def test_contention_log_level_depends_on_wait_time(
    monkeypatch, warning_threshold, expected_level
):
    messages: dict[str, list[str]] = {"debug": [], "warning": []}
    fake_logger = type(
        "FakeLogger",
        (),
        {
            "debug": lambda _self, message: messages["debug"].append(message),
            "warning": lambda _self, message: messages["warning"].append(message),
        },
    )()
    monkeypatch.setattr(lock_service, "logger", fake_logger)
    monkeypatch.setattr(lock_service, "_WARNING_WAIT_SECONDS", warning_threshold)
    holder_entered = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder():
        async with user_operation_lock(["u1"], "日志持锁"):
            holder_entered.set()
            await release_holder.wait()

    async def waiter():
        async with user_operation_lock(["u1"], "日志等待"):
            pass

    holder_task = asyncio.create_task(holder())
    await holder_entered.wait()
    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    release_holder.set()
    await asyncio.gather(holder_task, waiter_task)

    assert len(messages[expected_level]) == 1
    other_level = "warning" if expected_level == "debug" else "debug"
    assert messages[other_level] == []
    assert active_user_lock_count() == 0


async def test_multi_user_operation_blocks_on_receiver_lock():
    receiver_entered = asyncio.Event()
    release_receiver = asyncio.Event()
    gift_entered = asyncio.Event()

    async def receiver_operation():
        async with user_operation_lock(["receiver"], "接收者操作"):
            receiver_entered.set()
            await release_receiver.wait()

    async def gift_operation():
        await receiver_entered.wait()
        async with user_operation_lock(["sender", "receiver"], "赠送鱼"):
            gift_entered.set()

    receiver_task = asyncio.create_task(receiver_operation(), name="receiver-operation")
    gift_task = asyncio.create_task(gift_operation(), name="gift-operation")
    await receiver_entered.wait()
    await asyncio.sleep(0)
    assert not gift_entered.is_set()

    release_receiver.set()
    await asyncio.gather(receiver_task, gift_task)
    assert gift_entered.is_set()
    assert active_user_lock_count() == 0


async def test_opposite_multi_user_order_does_not_deadlock():
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    order: list[str] = []

    async def first():
        async with user_operation_lock(["sender", "receiver"], "赠送鱼-A"):
            order.append("first-enter")
            first_entered.set()
            await release_first.wait()

    async def second():
        await first_entered.wait()
        async with user_operation_lock(["receiver", "sender"], "赠送鱼-B"):
            order.append("second-enter")

    first_task = asyncio.create_task(first(), name="first-gift")
    second_task = asyncio.create_task(second(), name="second-gift")
    await first_entered.wait()
    await asyncio.sleep(0)
    assert order == ["first-enter"]

    release_first.set()
    await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=1)
    assert order == ["first-enter", "second-enter"]
    assert active_user_lock_count() == 0


class _AtEvent:
    def get_user_id(self):
        return "sender"

    def get_message(self):
        return [
            type("Segment", (), {"type": "text", "data": {}})(),
            type("Segment", (), {"type": "at", "data": {"qq": "receiver"}})(),
            type("Segment", (), {"type": "at", "data": {"qq": "ignored"}})(),
        ]


def test_event_user_and_at_ids_uses_sender_and_first_receiver():
    assert event_user_and_at_ids(_AtEvent(), (), {}) == ["sender", "receiver"]


class _QQMentionEvent:
    def get_user_id(self):
        return "sender-open-id"

    def get_message(self):
        return [
            type(
                "Segment",
                (),
                {"type": "mention_user", "data": {"user_id": "receiver-open-id"}},
            )()
        ]


def test_event_user_and_at_ids_supports_qq_mention_segment():
    assert event_user_and_at_ids(_QQMentionEvent(), (), {}) == [
        "sender-open-id",
        "receiver-open-id",
    ]


def test_backpack_asset_handlers_have_expected_locks():
    handler_path = Path(__file__).parents[1] / "handlers" / "backpack.py"
    tree = ast.parse(handler_path.read_text(encoding="utf-8"))
    lock_by_called_business: dict[str, str] = {}

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        lock_feature = None
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Name)
                and decorator.func.id == "with_user_lock"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
            ):
                lock_feature = decorator.args[0].value
        if lock_feature is None:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                lock_by_called_business[child.func.id] = lock_feature

    assert lock_by_called_business["gift_fish"] == "赠送鱼"
    assert lock_by_called_business["black_market_exchange"] == "黑商交换"
    assert lock_by_called_business["sell_bait"] == "卖出鱼饵"

    gift_handler = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "gift_fish"
            for child in ast.walk(node)
        )
    )
    gift_lock = next(
        decorator
        for decorator in gift_handler.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Name)
        and decorator.func.id == "with_user_lock"
    )
    resolver = next(
        keyword.value for keyword in gift_lock.keywords if keyword.arg == "resolver"
    )
    assert isinstance(resolver, ast.Name)
    assert resolver.id == "event_user_and_at_ids"


def test_all_player_mutation_handlers_have_expected_locks():
    handlers_dir = Path(__file__).parents[1] / "handlers"
    expected = {
        "backpack.py": {
            "sell_fish": "卖鱼",
            "lock_fish": "锁鱼",
            "unlock_fish": "解锁鱼",
            "gift_fish": "赠送鱼",
            "black_market_revoke": "黑商撤销",
            "smart_black_market_exchange": "智能黑商交换",
            "black_market_exchange": "黑商交换",
            "white_market_exchange": "白商交换",
            "set_preferred_bait": "设定鱼饵",
            "sell_bait": "卖出鱼饵",
        },
        "cat_park.py": {"upgrade_cat_park_building": "猫猫乐园建设"},
        "fishing.py": {
            "start_fishing": "钓鱼/确认地图",
            "stop_fishing": "收杆结算",
            "check_fishing_status": "钓鱼状态结算",
        },
        "player.py": {
            "toggle_auto_sell": "设置自动卖鱼",
            "set_auto_sell_rarity": "设置自动卖鱼",
            "toggle_auto_lock": "设置自动锁鱼",
            "set_auto_lock_pattern": "设置自动锁鱼",
            "rename_fishing_user": "钓鱼改名",
            "change_skin": "更换皮肤",
        },
        "shop.py": {
            "upgrade_rod": "升级钓竿",
            "build_starry_ship": "建设星空艇",
            "upgrade_hook": "升级鱼钩",
            "buy_item": "鱼店购买",
            "upgrade_display_slots": "升级展示栏",
            "do_nest": "打窝",
            "exchange_to_gold": "钓鱼币兑换",
            "resolve_item_handler": "使用物品",
        },
        "web.py": {
            "register": "注册网页端密钥",
            "unregister": "删除网页端密钥",
        },
    }

    for filename, expected_calls in expected.items():
        tree = ast.parse((handlers_dir / filename).read_text(encoding="utf-8"))
        actual: dict[str, set[str]] = {}
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            lock_feature = next(
                (
                    decorator.args[0].value
                    for decorator in node.decorator_list
                    if isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "with_user_lock"
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ),
                None,
            )
            if lock_feature is None:
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                if isinstance(child.func, ast.Name):
                    call_name = child.func.id
                elif isinstance(child.func, ast.Attribute):
                    call_name = child.func.attr
                else:
                    continue
                actual.setdefault(call_name, set()).add(lock_feature)

        for call_name, feature in expected_calls.items():
            assert feature in actual.get(call_name, set()), (
                f"{filename} 的 {call_name} 未使用预期用户锁 {feature}"
            )


def test_user_initialization_uses_shared_user_lock():
    service_path = Path(__file__).parents[1] / "services" / "user_service.py"
    tree = ast.parse(service_path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "get_or_create_user"
    )
    lock_calls = [
        child
        for child in ast.walk(function)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == "user_operation_lock"
    ]
    assert len(lock_calls) == 1
    assert isinstance(lock_calls[0].args[0], ast.List)
    assert isinstance(lock_calls[0].args[0].elts[0], ast.Name)
    assert lock_calls[0].args[0].elts[0].id == "user_id"


async def test_nested_lock_expansion_is_rejected_without_leak():
    with pytest.raises(RuntimeError, match="禁止嵌套扩张"):
        async with user_operation_lock(["u1"], "外层"):
            async with user_operation_lock(["u1", "u2"], "内层"):
                pass

    assert active_user_lock_count() == 0


async def test_cancelled_waiter_is_removed_without_leak():
    holder_entered = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder():
        async with user_operation_lock(["u1"], "持锁功能"):
            holder_entered.set()
            await release_holder.wait()

    async def waiter():
        async with user_operation_lock(["u1"], "等待功能"):
            pass

    holder_task = asyncio.create_task(holder(), name="holder")
    await holder_entered.wait()
    waiter_task = asyncio.create_task(waiter(), name="waiter")
    await asyncio.sleep(0)
    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    release_holder.set()
    await holder_task
    assert active_user_lock_count() == 0


async def test_cancelled_multi_lock_after_partial_acquire_releases_all_entries():
    blocker_entered = asyncio.Event()
    release_blocker = asyncio.Event()

    async def blocker():
        async with user_operation_lock(["u2"], "阻塞第二把锁"):
            blocker_entered.set()
            await release_blocker.wait()

    blocker_task = asyncio.create_task(blocker(), name="multi-lock-blocker")
    await blocker_entered.wait()
    waiter_task = asyncio.create_task(
        user_operation_lock(["u1", "u2"], "多锁等待").__aenter__(),
        name="partial-multi-lock-waiter",
    )
    await asyncio.sleep(0)
    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    # u1 已先取得，取消后必须立即可被其他业务获取。
    async def verify_partial_lock_cleanup():
        async with user_operation_lock(["u1"], "验证部分锁回收"):
            pass

    await asyncio.wait_for(verify_partial_lock_cleanup(), timeout=1)

    release_blocker.set()
    await blocker_task
    assert active_user_lock_count() == 0


async def test_business_exception_releases_lock_and_entry():
    with pytest.raises(ValueError, match="业务失败"):
        async with user_operation_lock(["u1"], "异常业务"):
            raise ValueError("业务失败")

    async with user_operation_lock(["u1"], "异常后重试"):
        pass
    assert active_user_lock_count() == 0


async def test_cancelled_business_releases_lock_and_entry():
    entered = asyncio.Event()

    async def business():
        async with user_operation_lock(["u1"], "取消业务"):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(business(), name="cancelled-business")
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    async def retry_after_cancel():
        async with user_operation_lock(["u1"], "取消后重试"):
            pass

    await asyncio.wait_for(retry_after_cancel(), timeout=1)
    assert active_user_lock_count() == 0


async def test_wait_timeout_does_not_leave_waiter_or_entry_behind():
    holder_entered = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder():
        async with user_operation_lock(["u1"], "holder"):
            holder_entered.set()
            await release_holder.wait()

    holder_task = asyncio.create_task(holder(), name="timeout-holder")
    await holder_entered.wait()

    with pytest.raises(UserOperationBusyError) as exc_info:
        async with user_operation_lock(
            ["u1"], "timed-waiter", wait_timeout=0.01
        ):
            pass

    assert exc_info.value.user_id == "u1"
    assert exc_info.value.holder_feature == "holder"
    release_holder.set()
    await holder_task
    assert active_user_lock_count() == 0


async def test_multi_lock_timeout_releases_partially_acquired_lock():
    blocker_entered = asyncio.Event()
    release_blocker = asyncio.Event()

    async def blocker():
        async with user_operation_lock(["u2"], "second-lock-holder"):
            blocker_entered.set()
            await release_blocker.wait()

    blocker_task = asyncio.create_task(blocker(), name="second-lock-holder")
    await blocker_entered.wait()

    with pytest.raises(UserOperationBusyError):
        async with user_operation_lock(
            ["u1", "u2"], "multi-lock-waiter", wait_timeout=0.01
        ):
            pass

    async with user_operation_lock(["u1"], "partial-lock-check"):
        pass

    release_blocker.set()
    await blocker_task
    assert active_user_lock_count() == 0
