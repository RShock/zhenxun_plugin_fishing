"""
定时任务 — 天气生成、Buff清理、周末奖励、数据库备份、Web服务器启动。

此处定义所有 scheduler.scheduled_job 装饰的定时任务。
__init__.py 通过 `from . import scheduler` 触发注册。
"""

import asyncio
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, unquote

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler

from .models import FishingBuff

BACKUP_DIR = Path("data/db/backups")

# 钓鱼相关表名列表，用于 PostgreSQL 选择性备份
_FISHING_TABLES = [
    "fishing_active_group",
    "fishing_buff",
    "fishing_exchange_record",
    "fishing_user",
    "fishing_weather",
    "fishing_web_key",
]

# pg_dump 可能的安装路径（Windows）
_PG_DUMP_CANDIDATES = [
    "pg_dump",
    r"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe",
    r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
    r"C:\Program Files\PostgreSQL\15\bin\pg_dump.exe",
]


def _find_pg_dump() -> str | None:
    """查找可用的 pg_dump 可执行文件路径。"""
    for candidate in _PG_DUMP_CANDIDATES:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None

_web_started = False


@scheduler.scheduled_job("cron", hour=0, minute=5)
async def _scheduled_weekend_bonus():
    year = datetime.now().year
    created = await FishingBuff.generate_weekend_bonus(year)
    if created > 0:
        logger.info(f"自动生成了 {created} 个周末奖励buff")


@scheduler.scheduled_job("cron", hour=23, minute=0, timezone="Asia/Shanghai")
async def _scheduled_weather_generation():
    from .weather_service import ensure_weather_generated

    generated = await ensure_weather_generated()
    if generated:
        logger.info("定时任务：自动生成了今日天气")


@scheduler.scheduled_job("interval", hours=1)
async def _scheduled_clear_expired_buffs():
    await FishingBuff.clear_expired_buffs()


def _backup_sqlite(parsed, now: datetime) -> Path | None:
    """SQLite 数据库备份：直接复制文件。"""
    db_path = Path(unquote(parsed.path).lstrip("/"))
    if not db_path.exists():
        logger.warning(f"[钓鱼备份] 数据库文件 {db_path} 不存在，跳过")
        return None

    backup_name = f"zhenxun_backup_{now.strftime('%Y%m%d_%H%M%S')}.db"
    backup_path = BACKUP_DIR / backup_name
    shutil.copy2(db_path, backup_path)
    return backup_path


def _backup_postgres(parsed, now: datetime) -> Path | None:
    """PostgreSQL 数据库备份：使用 pg_dump 导出钓鱼相关表。"""
    pg_dump = _find_pg_dump()
    if not pg_dump:
        logger.error("[钓鱼备份] 未找到 pg_dump，跳过 PostgreSQL 备份")
        return None

    host = parsed.hostname or "127.0.0.1"
    port = str(parsed.port or 5432)
    username = parsed.username or "postgres"
    password = unquote(parsed.password) if parsed.password else ""
    dbname = parsed.path.lstrip("/")

    backup_name = f"fishing_backup_{now.strftime('%Y%m%d_%H%M%S')}.sql"
    backup_path = BACKUP_DIR / backup_name

    cmd = [pg_dump, "--host", host, "--port", port, "--username", username, "--dbname", dbname]
    for table in _FISHING_TABLES:
        cmd.extend(["--table", table])
    cmd.extend(["--format=plain", "--no-owner", "--no-privileges"])

    env = None
    if password:
        import os
        env = {**os.environ, "PGPASSWORD": password}

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    if result.returncode != 0:
        logger.error(f"[钓鱼备份] pg_dump 失败: {result.stderr[:500]}")
        return None

    backup_path.write_text(result.stdout, encoding="utf-8")
    return backup_path


@scheduler.scheduled_job("interval", hours=12)
async def _scheduled_backup_fishing_db():
    from zhenxun.configs.config import BotConfig

    db_url = BotConfig.db_url
    if not db_url:
        return

    parsed = urlparse(db_url)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    try:
        if parsed.scheme == "sqlite":
            backup_path = await asyncio.to_thread(_backup_sqlite, parsed, now)
        elif parsed.scheme in ("postgres", "postgresql"):
            backup_path = await asyncio.to_thread(_backup_postgres, parsed, now)
        else:
            logger.warning(f"[钓鱼备份] 暂不支持 {parsed.scheme} 数据库备份，跳过")
            return

        if backup_path:
            logger.info(
                f"[钓鱼备份] 备份完成: {backup_path} ({backup_path.stat().st_size} bytes)"
            )
    except Exception as e:
        logger.error(f"[钓鱼备份] 备份失败: {e}")
        return

    cutoff = now - timedelta(days=3)
    for f in BACKUP_DIR.glob("fishing_backup_*.sql"):
        try:
            if f.stat().st_mtime < cutoff.timestamp():
                f.unlink()
                logger.info(f"[钓鱼备份] 已删除过期备份: {f.name}")
        except Exception as e:
            logger.warning(f"[钓鱼备份] 删除过期备份失败 {f.name}: {e}")
    for f in BACKUP_DIR.glob("zhenxun_backup_*.db"):
        try:
            if f.stat().st_mtime < cutoff.timestamp():
                f.unlink()
                logger.info(f"[钓鱼备份] 已删除过期备份: {f.name}")
        except Exception as e:
            logger.warning(f"[钓鱼备份] 删除过期备份失败 {f.name}: {e}")


@scheduler.scheduled_job(
    "date",
    id="_start_web_servers",
    next_run_time=datetime.now() + timedelta(seconds=60),
    misfire_grace_time=120,
)
async def _start_web_servers():
    global _web_started
    if _web_started:
        return
    _web_started = True

    from .status_api import start_status_server

    try:
        start_status_server()
        logger.info("[钓鱼插件] 状态API服务器已启动(端口4158)")
    except Exception as e:
        logger.error(f"[钓鱼插件] 状态API服务器启动失败: {e}")

    from .web.websocket_server import get_ws_server

    try:
        await get_ws_server().start()
        logger.info("[钓鱼插件] WebSocket网页服务器已启动(端口4159)")
    except Exception as e:
        logger.error(f"[钓鱼插件] WebSocket网页服务器启动失败: {e}")
