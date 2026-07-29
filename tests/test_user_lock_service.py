"""用户级共享异步锁的并发、嵌套与回收行为。"""

import ast
import asyncio
from pathlib import Path

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.services.user_lock_service import (
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
