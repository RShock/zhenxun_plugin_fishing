"""
天气数据模型 — FishingWeather。

记录每天每个钓场的天气类型（晴天/雨天/流星/暴雨/迷途风/星空天气）。
天气日从每天 23:00 开始，到次日 22:59 结束。
"""

from datetime import datetime, time, timedelta

from tortoise import fields

from zhenxun.services.db_context import Model


def _weather_date() -> "date":
    """返回当前天气日对应的数据库日期（仅用于生成记录时的 date 字段）。"""
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.hour >= 23:
        return now.date()
    return now.date() - timedelta(days=1)


def _weather_window() -> "tuple[datetime, datetime]":
    """返回当前天气日的时间窗口 [start, end)。

    天气日从每天 23:00 开始，到次日 23:00 结束。
    """
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    weather_date = now.date() if now.hour >= 23 else now.date() - timedelta(days=1)
    window_start = datetime.combine(weather_date, time(23, 0))
    window_end = window_start + timedelta(hours=24)
    return window_start, window_end


class FishingWeather(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    location_id = fields.CharField(50, index=True, description="地点ID")
    weather_type = fields.CharField(20, description="天气类型: sunny/rain/meteor/storm/lost_wind/solar_wind/meteor_shower/hengjiyuan")
    date = fields.DateField(index=True, description="日期")
    start_time = fields.DatetimeField(null=True, description="天气开始时间")
    end_time = fields.DatetimeField(null=True, description="天气结束时间")

    class Meta:
        table = "fishing_weather"
        table_description = "钓鱼天气表"

    @classmethod
    async def is_generated_today(cls) -> bool:
        """当前天气日是否已有足够天气记录。

        使用 date 字段查询，避免 sunny 天气（start_time=None）被遗漏。
        """
        today = _weather_date()
        count = await cls.filter(date=today).count()
        from ..config import ConfigManager

        locations = ConfigManager.get_locations()
        return count >= len(locations)

    @classmethod
    async def get_today_weather(cls, location_id: str) -> "FishingWeather | None":
        """获取当前天气日某地点的天气记录。

        使用 date 字段查询，确保 sunny 天气（start_time=None）也能被找到。
        """
        today = _weather_date()
        return await cls.filter(
            location_id=location_id,
            date=today,
        ).first()

    @classmethod
    async def get_all_today_weathers(cls) -> dict[str, "FishingWeather"]:
        """获取当前天气日所有地点的天气记录。

        使用 date 字段查询，确保 sunny 天气（start_time=None）也能被找到。
        同一地点若存在多条记录（历史 bug 残留），取 id 最大的那条。
        """
        today = _weather_date()
        weathers = await cls.filter(date=today).all()
        result: dict[str, "FishingWeather"] = {}
        for w in weathers:
            if w.location_id not in result or w.id > result[w.location_id].id:
                result[w.location_id] = w
        return result
