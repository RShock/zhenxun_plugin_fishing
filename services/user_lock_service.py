"""钓鱼插件内跨功能共享的用户级异步锁。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from time import monotonic
from typing import Any, ParamSpec, TypeVar, cast

from nonebot.adapters import Event
from nonebot.exception import FinishedException
from nonebot.matcher import Matcher

from zhenxun.services.log import logger

P = ParamSpec("P")
R = TypeVar("R")
UserIdResolver = Callable[[Event, tuple[Any, ...], dict[str, Any]], list[str]]


@dataclass
class _UserLockEntry:
    lock: asyncio.Lock
    references: int = 0
    holder_feature: str | None = None
    holder_since: float | None = None
    holder_task: str | None = None
    holder_owner: asyncio.Task[Any] | None = None


_entries: dict[str, _UserLockEntry] = {}
_held_user_ids: ContextVar[frozenset[str]] = ContextVar(
    "fishing_held_user_ids", default=frozenset()
)
_held_owner: ContextVar[asyncio.Task[Any] | None] = ContextVar(
    "fishing_held_owner", default=None
)

_WARNING_WAIT_SECONDS = 0.5
_LOCK_WAIT_TIMEOUT_SECONDS = 10.0
_BUSY_MESSAGE = "上一个钓鱼操作仍在处理中，请稍后再试。"


@dataclass
class _DeferredSendQueue:
    owner: asyncio.Task[Any] | None
    callbacks: list[Callable[[], Awaitable[Any]]]


_deferred_sends: ContextVar[_DeferredSendQueue | None] = ContextVar(
    "fishing_deferred_sends", default=None
)


def defer_user_lock_send(callback: Callable[[], Awaitable[Any]]) -> bool:
    """???????????????????????????"""
    queue = _deferred_sends.get()
    if queue is None or queue.owner is not asyncio.current_task():
        return False
    queue.callbacks.append(callback)
    return True


async def _flush_deferred_sends(queue: _DeferredSendQueue):
    for callback in queue.callbacks:
        await callback()


class UserOperationBusyError(TimeoutError):
    """同一用户的前一项操作在限定时间内没有结束。"""

    def __init__(
        self,
        user_id: str,
        feature: str,
        holder_feature: str | None,
        waited: float,
    ):
        self.user_id = user_id
        self.feature = feature
        self.holder_feature = holder_feature
        self.waited = waited
        super().__init__(
            f"user={user_id}, feature={feature}, "
            f"holder_feature={holder_feature or 'unknown'}, waited={waited:.3f}s"
        )


def _task_name() -> str:
    task = asyncio.current_task()
    if task is None:
        return "unknown"
    try:
        return task.get_name()
    except AttributeError:
        return repr(task)


async def _acquire_lock(lock: asyncio.Lock, wait_timeout: float | None) -> None:
    """可取消地获取锁，避免 wait_for 子任务在取消竞态中遗留已获取的锁。"""
    if wait_timeout is None:
        await lock.acquire()
        return

    acquire_task = asyncio.create_task(lock.acquire())
    try:
        await asyncio.wait_for(asyncio.shield(acquire_task), max(wait_timeout, 0.0))
    except BaseException:
        acquire_task.cancel()
        acquired = False
        try:
            acquired = await acquire_task
        except asyncio.CancelledError:
            pass
        if acquired and lock.locked():
            lock.release()
        raise


def event_user_ids(
    event: Event, _args: tuple[Any, ...], _kwargs: dict[str, Any]
) -> list[str]:
    return [event.get_user_id()]


def event_user_and_at_ids(
    event: Event, _args: tuple[Any, ...], _kwargs: dict[str, Any]
) -> list[str]:
    user_ids = [event.get_user_id()]
    if hasattr(event, "get_message"):
        for segment in event.get_message():
            if getattr(segment, "type", None) not in {"at", "mention_user"}:
                continue
            target = segment.data.get("qq") or segment.data.get("user_id")
            if target:
                user_ids.append(str(target))
                break
    return user_ids


class user_operation_lock:
    """按稳定顺序持有一个或多个用户锁，并在退出后回收空闲条目。"""

    def __init__(
        self,
        user_ids: list[str],
        feature: str,
        *,
        wait_timeout: float | None = _LOCK_WAIT_TIMEOUT_SECONDS,
    ):
        self.user_ids = sorted({str(user_id) for user_id in user_ids if user_id})
        self.feature = feature
        self.wait_timeout = wait_timeout
        self._entries: list[tuple[str, _UserLockEntry]] = []
        self._token = None
        self._owner_token = None
        self._reentrant = False

    async def __aenter__(self):
        current_task = asyncio.current_task()
        inherited_owner = _held_owner.get()
        # ContextVar 会被 create_task 复制；只有实际持锁 Task 才能重入。
        held = _held_user_ids.get() if inherited_owner is current_task else frozenset()
        requested = frozenset(self.user_ids)
        if requested.issubset(held):
            # 同一任务内的下层业务可能再次经过共享入口；直接复用外层锁，避免自锁。
            self._reentrant = True
            return self
        if held & requested or held:
            # 已持锁后再扩张锁集合无法保证全局顺序，明确失败优于形成锁顺序环。
            raise RuntimeError(
                f"用户锁禁止嵌套扩张: held={sorted(held)}, requested={self.user_ids}, "
                f"feature={self.feature}"
            )

        acquired: set[str] = set()
        try:
            for user_id in self.user_ids:
                entry = _entries.get(user_id)
                if entry is None:
                    entry = _UserLockEntry(asyncio.Lock())
                    _entries[user_id] = entry
                entry.references += 1
                self._entries.append((user_id, entry))

            for user_id, entry in self._entries:
                wait_started = monotonic()
                holder_feature = entry.holder_feature
                holder_task = entry.holder_task
                holder_seconds = (
                    wait_started - entry.holder_since
                    if entry.holder_since is not None
                    else 0.0
                )
                contended = entry.lock.locked()
                try:
                    await _acquire_lock(entry.lock, self.wait_timeout)
                except asyncio.TimeoutError as exc:
                    waited = monotonic() - wait_started
                    logger.warning(
                        "钓鱼用户锁等待超时: "
                        f"user={user_id}, feature={self.feature}, "
                        f"waited={waited:.3f}s, "
                        f"holder_feature={holder_feature or 'unknown'}, "
                        f"holder_task={holder_task or 'unknown'}, "
                        f"holder_seconds={holder_seconds:.3f}s"
                    )
                    raise UserOperationBusyError(
                        user_id, self.feature, holder_feature, waited
                    ) from exc
                acquired.add(user_id)
                waited = monotonic() - wait_started
                if contended:
                    log = (
                        logger.warning
                        if waited >= _WARNING_WAIT_SECONDS
                        else logger.debug
                    )
                    log(
                        "钓鱼用户锁并发等待: "
                        f"user={user_id}, feature={self.feature}, "
                        f"waited={waited:.3f}s, "
                        f"holder_feature={holder_feature or 'unknown'}, "
                        f"holder_task={holder_task or 'unknown'}, "
                        f"holder_seconds={holder_seconds:.3f}s"
                    )
                entry.holder_feature = self.feature
                entry.holder_since = monotonic()
                entry.holder_task = _task_name()
                entry.holder_owner = current_task
        except BaseException:
            self._release_entries(acquired)
            raise

        self._token = _held_user_ids.set(held | requested)
        self._owner_token = _held_owner.set(current_task)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._reentrant:
            return False
        if self._token is not None:
            _held_user_ids.reset(self._token)
        if self._owner_token is not None:
            _held_owner.reset(self._owner_token)
        self._release_entries()
        return False

    def _release_entries(self, acquired: set[str] | None = None):
        for user_id, entry in reversed(self._entries):
            owns_lock = (
                user_id in acquired
                if acquired is not None
                else entry.holder_owner is asyncio.current_task()
            )
            if entry.lock.locked() and owns_lock:
                entry.holder_feature = None
                entry.holder_since = None
                entry.holder_task = None
                entry.holder_owner = None
                entry.lock.release()
            entry.references -= 1
            if entry.references == 0 and not entry.lock.locked():
                _entries.pop(user_id, None)
        self._entries.clear()


def with_user_lock(
    feature: str, *, resolver: UserIdResolver = event_user_ids
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """为 NoneBot handler 添加共享用户锁；锁只包裹业务，不跨消息发送层复用。"""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            event = next(
                (arg for arg in args if isinstance(arg, Event)),
                kwargs.get("event"),
            )
            if event is None:
                raise RuntimeError(f"用户锁入口缺少 Event: feature={feature}")
            user_ids = resolver(event, args, kwargs)

            inherited_queue = _deferred_sends.get()
            owns_queue = (
                inherited_queue is None
                or inherited_queue.owner is not asyncio.current_task()
            )
            queue = (
                _DeferredSendQueue(asyncio.current_task(), [])
                if owns_queue
                else inherited_queue
            )
            queue_token = _deferred_sends.set(queue) if owns_queue else None
            finished: FinishedException | None = None
            try:
                try:
                    async with user_operation_lock(user_ids, feature):
                        result = await func(*args, **kwargs)
                except UserOperationBusyError:
                    matcher = next(
                        (arg for arg in args if isinstance(arg, Matcher)),
                        kwargs.get("matcher"),
                    )
                    if matcher is None:
                        raise
                    await matcher.finish(_BUSY_MESSAGE)
                    return cast(R, None)
            except FinishedException as exc:
                if not owns_queue:
                    raise
                finished = exc
                result = cast(R, None)
            finally:
                if queue_token is not None:
                    _deferred_sends.reset(queue_token)

            if owns_queue:
                # QQ API ?????????????????????????????
                await _flush_deferred_sends(queue)
            if finished is not None:
                raise finished
            return result

        return wrapped

    return decorator


def active_user_lock_count() -> int:
    """仅供运行状态检查与测试，正常空闲时应回到 0。"""
    return len(_entries)
