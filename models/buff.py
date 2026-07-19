"""
Buff 数据模型 — BuffEffect, FishingBuff, FishingBuffCalculator。

管理各类限时效果：打窝加速、药水、天气影响、周末奖励等。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from tortoise import fields

from zhenxun.services.db_context import Model

from .user import FishingUser, _make_naive


@dataclass(frozen=True)
class BuffMeta:
    """buff 元数据：每个 buff_type 必须在 BUFF_REGISTRY 中注册。

    新建 buff 时必须同时注册 display_name（中文名）和 color（时间轴颜色），
    否则显示层（时间轴图例、buff 消息）无法获取中文名，会回退到英文 buff_type。
    """

    key: str  # buff_type 英文键
    display_name: str  # 中文显示名
    color: str = "#999999"  # 时间轴颜色
    emoji: str = ""  # 可选 emoji 前缀


class BuffEffect:
    BUFF_TYPE_NEST = "nest"
    BUFF_TYPE_SPEED_BOOST = "speed_boost"
    BUFF_TYPE_DOUBLE_CATCH = "double_catch"
    BUFF_TYPE_WEEKEND_BONUS = "weekend_bonus"
    BUFF_TYPE_ROD_BONUS = "rod_bonus"
    BUFF_TYPE_WISH = "wish"
    BUFF_TYPE_DUODUO = "duoduo"
    BUFF_TYPE_FRAME = "frame"
    BUFF_TYPE_WEATHER_RAIN = "weather_rain"
    BUFF_TYPE_WEATHER_METEOR = "weather_meteor"
    BUFF_TYPE_WEATHER_STORM = "weather_storm"
    BUFF_TYPE_WEATHER_LOST_WIND = "weather_lost_wind"
    BUFF_TYPE_WEATHER_CAT = "weather_cat"
    BUFF_TYPE_LUCKY_BOOST = "lucky_double"
    BUFF_TYPE_DRAGON_BOAT = "dragon_boat"
    BUFF_TYPE_STARRY_BONUS = "starry_bonus"
    # ── 流星鱼/星空祈愿天气 buff ──
    BUFF_TYPE_WEATHER_SOLAR_WIND = "weather_solar_wind"
    BUFF_TYPE_WEATHER_METEOR_SHOWER = "weather_meteor_shower"
    BUFF_TYPE_WEATHER_HENGJIYUAN = "weather_hengjiyuan"
    # ── 闪光药水 ──
    BUFF_TYPE_GAMMA_RAY_BURST = "gamma_ray_burst"

    TARGET_TYPE_USER = "user"
    TARGET_TYPE_LOCATION = "location"
    TARGET_TYPE_GLOBAL = "global"

    # ===== Buff 元数据注册表（单一数据源）=====
    # 新建 buff 时必须在此注册，否则显示层无法获取中文名。
    # 修改 display_name / color 时只需改这一处，所有显示层自动同步。
    BUFF_REGISTRY: dict[str, BuffMeta] = {
        BUFF_TYPE_NEST: BuffMeta(BUFF_TYPE_NEST, "打窝加速", "#4CAF50", "🪺"),
        BUFF_TYPE_SPEED_BOOST: BuffMeta(BUFF_TYPE_SPEED_BOOST, "加速药水", "#2196F3", "⚡"),
        BUFF_TYPE_DOUBLE_CATCH: BuffMeta(BUFF_TYPE_DOUBLE_CATCH, "双倍捕获", "#E91E63", "✨"),
        BUFF_TYPE_WEEKEND_BONUS: BuffMeta(BUFF_TYPE_WEEKEND_BONUS, "周末奖励", "#FF9800", "🎉"),
        BUFF_TYPE_ROD_BONUS: BuffMeta(BUFF_TYPE_ROD_BONUS, "鱼力加成", "#00BCD4", "🎣"),
        BUFF_TYPE_WISH: BuffMeta(BUFF_TYPE_WISH, "许愿药水", "#FFC107", "🌟"),
        BUFF_TYPE_DUODUO: BuffMeta(BUFF_TYPE_DUODUO, "真多多药水", "#FF5722", "🐟"),
        BUFF_TYPE_FRAME: BuffMeta(BUFF_TYPE_FRAME, "展示木框", "#8D6E63", "🖼️"),
        BUFF_TYPE_WEATHER_RAIN: BuffMeta(BUFF_TYPE_WEATHER_RAIN, "雨天", "#42A5F5", "🌧️"),
        BUFF_TYPE_WEATHER_METEOR: BuffMeta(BUFF_TYPE_WEATHER_METEOR, "流星雨", "#AB47BC", "☄️"),
        BUFF_TYPE_WEATHER_STORM: BuffMeta(BUFF_TYPE_WEATHER_STORM, "暴雨", "#78909C", "⛈️"),
        BUFF_TYPE_WEATHER_LOST_WIND: BuffMeta(BUFF_TYPE_WEATHER_LOST_WIND, "迷途风", "#E040FB", "🌀"),
        BUFF_TYPE_WEATHER_CAT: BuffMeta(BUFF_TYPE_WEATHER_CAT, "猫天气", "#FF9800", "🐱"),
        BUFF_TYPE_LUCKY_BOOST: BuffMeta(BUFF_TYPE_LUCKY_BOOST, "幸运药水", "#FFD54F", "🎲"),
        BUFF_TYPE_DRAGON_BOAT: BuffMeta(BUFF_TYPE_DRAGON_BOAT, "端午活动", "#8BC34A", "🐲"),
        BUFF_TYPE_STARRY_BONUS: BuffMeta(BUFF_TYPE_STARRY_BONUS, "星空艇", "#7C4DFF", "🚀"),
        # ── 流星鱼/星空祈愿天气 buff ──
        BUFF_TYPE_WEATHER_SOLAR_WIND: BuffMeta(
            BUFF_TYPE_WEATHER_SOLAR_WIND, "太阳风", "#26C6DA", "🌬️"
        ),
        BUFF_TYPE_WEATHER_METEOR_SHOWER: BuffMeta(
            BUFF_TYPE_WEATHER_METEOR_SHOWER, "流星雨", "#AB47BC", "💫"
        ),
        BUFF_TYPE_WEATHER_HENGJIYUAN: BuffMeta(
            BUFF_TYPE_WEATHER_HENGJIYUAN, "恒纪元", "#FFB300", "🏛️"
        ),
        # ── 闪光药水 ──
        BUFF_TYPE_GAMMA_RAY_BURST: BuffMeta(
            BUFF_TYPE_GAMMA_RAY_BURST, "伽马射线暴", "#76FF03", "💥"
        ),
    }

    @classmethod
    def get_meta(cls, buff_type: str) -> BuffMeta | None:
        """获取 buff 元数据，未注册返回 None。"""
        return cls.BUFF_REGISTRY.get(buff_type)

    @classmethod
    def get_display_name(cls, buff_type: str) -> str:
        """获取中文显示名，未注册回退到英文 buff_type。"""
        meta = cls.BUFF_REGISTRY.get(buff_type)
        return meta.display_name if meta else buff_type

    @classmethod
    def get_color(cls, buff_type: str) -> str:
        """获取时间轴颜色，未注册回退到灰色。"""
        meta = cls.BUFF_REGISTRY.get(buff_type)
        return meta.color if meta else "#999999"


class FishingBuff(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    target_type = fields.CharField(20, description="目标类型(user/location/global)")
    target_id = fields.CharField(
        255, description="目标ID(用户ID/地点ID/空)", index=True
    )
    buff_type = fields.CharField(50, description="buff类型")
    start_time = fields.DatetimeField(description="开始时间")
    end_time = fields.DatetimeField(description="结束时间", index=True)
    value = fields.IntField(default=1, description="buff值")
    description = fields.CharField(255, description="buff描述")
    source_user_id = fields.CharField(255, null=True, description="来源用户ID")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")

    class Meta:
        table = "fishing_buff"
        table_description = "钓鱼buff表"

    @classmethod
    async def add_buff(
        cls,
        buff_type: str,
        start_time: datetime,
        end_time: datetime,
        value: int = 1,
        description: str = "",
        target_type: str = BuffEffect.TARGET_TYPE_USER,
        target_id: str = "",
        source_user_id: str = None,
    ) -> "FishingBuff":
        return await cls.create(
            target_type=target_type,
            target_id=target_id,
            buff_type=buff_type,
            start_time=start_time,
            end_time=end_time,
            value=value,
            description=description,
            source_user_id=source_user_id,
        )

    @classmethod
    async def add_user_buff(
        cls,
        user_id: str,
        buff_type: str,
        duration_minutes: int,
        value: int = 1,
        description: str = "",
    ) -> "FishingBuff":
        now = datetime.now()
        end_time = now + timedelta(minutes=duration_minutes)
        return await cls.add_buff(
            buff_type=buff_type,
            start_time=now,
            end_time=end_time,
            value=value,
            description=description,
            target_type=BuffEffect.TARGET_TYPE_USER,
            target_id=user_id,
        )

    @classmethod
    async def add_location_buff(
        cls,
        location_id: str,
        buff_type: str,
        duration_hours: int,
        value: int = 1,
        description: str = "",
        source_user_id: str = None,
    ) -> "FishingBuff":
        now = datetime.now()
        end_time = now + timedelta(hours=duration_hours)
        return await cls.add_buff(
            buff_type=buff_type,
            start_time=now,
            end_time=end_time,
            value=value,
            description=description,
            target_type=BuffEffect.TARGET_TYPE_LOCATION,
            target_id=location_id,
            source_user_id=source_user_id,
        )

    @classmethod
    async def add_global_buff(
        cls,
        buff_type: str,
        start_time: datetime,
        end_time: datetime,
        value: int = 1,
        description: str = "",
    ) -> "FishingBuff":
        return await cls.add_buff(
            buff_type=buff_type,
            start_time=start_time,
            end_time=end_time,
            value=value,
            description=description,
            target_type=BuffEffect.TARGET_TYPE_GLOBAL,
            target_id="",
        )

    @classmethod
    async def get_active_buffs_for_fishing(
        cls,
        user_id: str,
        location_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list["FishingBuff"]:
        buffs = []
        for target_type, target_id in [
            (BuffEffect.TARGET_TYPE_USER, user_id),
            (BuffEffect.TARGET_TYPE_LOCATION, location_id),
            (BuffEffect.TARGET_TYPE_GLOBAL, ""),
        ]:
            user_buffs = await cls.filter(
                target_type=target_type,
                target_id=target_id,
                start_time__lt=end_time,
                end_time__gt=start_time,
            ).all()
            buffs.extend(user_buffs)
        has_lost_wind = any(
            b.buff_type == BuffEffect.BUFF_TYPE_WEATHER_LOST_WIND for b in buffs
        )
        if has_lost_wind:
            unlocked = await FishingUser.has_unlocked_lost_wind(user_id, location_id)
            if not unlocked:
                buffs = [
                    b
                    for b in buffs
                    if b.buff_type != BuffEffect.BUFF_TYPE_WEATHER_LOST_WIND
                ]
        from ..cat_park import is_cat_park_location
        from ..starry import is_starry_location

        # 星空艇加成作用于一阶段地图（1-10 + S1），不包括星空地图（11-20）
        if is_starry_location(location_id):
            buffs = [
                b for b in buffs if b.buff_type != BuffEffect.BUFF_TYPE_STARRY_BONUS
            ]
        # 展示木框打窝加成仅作用于普通地图（1-10）和 S1，不作用于星空地图（11-20）
        if is_starry_location(location_id):
            buffs = [b for b in buffs if b.buff_type != BuffEffect.BUFF_TYPE_FRAME]
        return buffs

    @classmethod
    async def get_frame_buff_count_for_location(cls, location_id: str) -> int:
        from ..starry import is_starry_location

        if is_starry_location(location_id):
            return 0
        return await cls.get_global_buff_count(BuffEffect.BUFF_TYPE_FRAME)

    @classmethod
    async def get_active_user_buff(
        cls, user_id: str, buff_type: str
    ) -> "FishingBuff | None":
        now = datetime.now()
        return await cls.filter(
            target_type=BuffEffect.TARGET_TYPE_USER,
            target_id=user_id,
            buff_type=buff_type,
            start_time__lte=now,
            end_time__gt=now,
        ).first()

    @classmethod
    async def get_location_buff_count(
        cls, location_id: str, buff_type: str = BuffEffect.BUFF_TYPE_NEST
    ) -> int:
        now = datetime.now()
        return await cls.filter(
            target_type=BuffEffect.TARGET_TYPE_LOCATION,
            target_id=location_id,
            buff_type=buff_type,
            start_time__lte=now,
            end_time__gt=now,
        ).count()

    @classmethod
    async def get_global_buff_count(
        cls, buff_type: str = BuffEffect.BUFF_TYPE_FRAME
    ) -> int:
        now = datetime.now()
        return await cls.filter(
            target_type=BuffEffect.TARGET_TYPE_GLOBAL,
            buff_type=buff_type,
            start_time__lte=now,
            end_time__gt=now,
        ).count()

    @classmethod
    async def get_user_nest_count_at_location(
        cls, user_id: str, location_id: str
    ) -> int:
        now = datetime.now()
        return await cls.filter(
            target_type=BuffEffect.TARGET_TYPE_LOCATION,
            target_id=location_id,
            buff_type=BuffEffect.BUFF_TYPE_NEST,
            source_user_id=user_id,
            start_time__lte=now,
            end_time__gt=now,
        ).count()

    @classmethod
    async def clear_expired_buffs(cls) -> None:
        cutoff = datetime.now() - timedelta(days=30)
        await cls.filter(end_time__lt=cutoff).delete()

    @classmethod
    async def check_weekend_bonus_exists(cls, year: int) -> int:
        start_of_year = datetime(year, 1, 1)
        end_of_year = datetime(year, 12, 31, 23, 59, 59)
        return await cls.filter(
            target_type=BuffEffect.TARGET_TYPE_GLOBAL,
            buff_type=BuffEffect.BUFF_TYPE_WEEKEND_BONUS,
            start_time__gte=start_of_year,
            end_time__lte=end_of_year,
        ).count()

    @classmethod
    async def generate_weekend_bonus(cls, year: int) -> int:
        await cls.filter(
            buff_type=BuffEffect.BUFF_TYPE_WEEKEND_BONUS,
            value=1,
        ).update(value=30, description="周末奖励，额外速度×1.3")

        existing_count = await cls.check_weekend_bonus_exists(year)

        weekends = []
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)

        current = start_date
        while current <= end_date:
            if current.weekday() == 5:
                saturday = current
                sunday = current + timedelta(days=1)
                if sunday <= end_date:
                    weekends.append((saturday, sunday))
                else:
                    weekends.append((saturday, saturday))
            current += timedelta(days=1)

        if existing_count >= len(weekends):
            return 0

        created_count = 0
        for saturday, sunday in weekends:
            start_time = datetime.combine(saturday, datetime.min.time())
            end_time = datetime.combine(sunday, datetime.max.time())

            exists = await cls.filter(
                target_type=BuffEffect.TARGET_TYPE_GLOBAL,
                buff_type=BuffEffect.BUFF_TYPE_WEEKEND_BONUS,
                start_time=start_time,
            ).exists()

            if not exists:
                await cls.add_global_buff(
                    buff_type=BuffEffect.BUFF_TYPE_WEEKEND_BONUS,
                    start_time=start_time,
                    end_time=end_time,
                    value=30,
                    description="周末奖励，额外速度×1.3",
                )
                created_count += 1

        return created_count

    @classmethod
    async def check_dragon_boat_buff(cls) -> "FishingBuff | None":
        """检查端午活动buff是否已存在（2026-06-19 00:00 ~ 2026-06-22 00:00）。"""
        start = datetime(2026, 6, 19, 0, 0, 0)
        return await cls.filter(
            target_type=BuffEffect.TARGET_TYPE_GLOBAL,
            buff_type=BuffEffect.BUFF_TYPE_DRAGON_BOAT,
            start_time=start,
        ).first()

    @classmethod
    async def create_dragon_boat_buff(cls) -> "FishingBuff":
        """创建端午活动全局buff（2026-06-19 00:00 ~ 2026-06-22 00:00）。"""
        start = datetime(2026, 6, 19, 0, 0, 0)
        end = datetime(2026, 6, 22, 0, 0, 0)
        return await cls.add_global_buff(
            buff_type=BuffEffect.BUFF_TYPE_DRAGON_BOAT,
            start_time=start,
            end_time=end,
            value=1,
            description="端午活动：2%概率额外获得流星鱼",
        )


class FishingBuffCalculator:
    BUFF_EFFECTS = {
        BuffEffect.BUFF_TYPE_NEST: lambda v, r: ("speed_bonus", v),
        BuffEffect.BUFF_TYPE_SPEED_BOOST: lambda v, r: ("speed_bonus", v),
        BuffEffect.BUFF_TYPE_FRAME: lambda v, r: ("speed_bonus", v),
        BuffEffect.BUFF_TYPE_STARRY_BONUS: lambda v, r: ("speed_bonus", v),
        BuffEffect.BUFF_TYPE_DOUBLE_CATCH: lambda v, r: ("double_catch", True),
        BuffEffect.BUFF_TYPE_WEEKEND_BONUS: lambda v, r: (
            "extra_speed_multiplier",
            1 + v / 100,
        ),
        BuffEffect.BUFF_TYPE_ROD_BONUS: lambda v, r: ("rod_bonus", v),
        BuffEffect.BUFF_TYPE_WISH: lambda v, r: ("wish_active", True),
        BuffEffect.BUFF_TYPE_DUODUO: lambda v, r: (
            "duoduo_count",
            0 if r["duoduo_count"] else 1,
        ),
        BuffEffect.BUFF_TYPE_WEATHER_RAIN: lambda v, r: (
            "weather_speed_multiplier",
            1 + v / 100,
        ),
        BuffEffect.BUFF_TYPE_WEATHER_METEOR: lambda v, r: (
            "weather_luck_boost",
            v,
        ),
        BuffEffect.BUFF_TYPE_WEATHER_STORM: lambda v, r: ("weather_half_bait", True),
        BuffEffect.BUFF_TYPE_WEATHER_LOST_WIND: lambda v, r: (
            "weather_lost_wind",
            True,
        ),
        BuffEffect.BUFF_TYPE_WEATHER_CAT: lambda v, r: (
            "weather_cat_eat",
            True,
        ),
        BuffEffect.BUFF_TYPE_LUCKY_BOOST: lambda v, r: (
            "lucky_double_active",
            True,
        ),
    }

    # ── 流星鱼/星空祈愿 buff 说明 ──
    # 以下 buff 不直接映射到 BUFF_EFFECTS，其效果在钓鱼引擎中特殊处理：
    # - BUFF_TYPE_WEATHER_SOLAR_WIND:  在引擎中处理流星鱼掉率加成（恒定 +2.5%）
    # - BUFF_TYPE_WEATHER_METEOR_SHOWER: 在引擎中处理2选1机制
    # - BUFF_TYPE_WEATHER_HENGJIYUAN:  在引擎中处理流星鱼数字过滤（品种质量更高）
    # - BUFF_TYPE_GAMMA_RAY_BURST:     在引擎中处理综合效果（闪光药水）

    @staticmethod
    def get_effects_at_time(
        buffs: list["FishingBuff"],
        target_time: datetime,
        base_rod_level: int,
        base_bait_speed: int,
        base_difficulty: int,
    ) -> dict[str, Any]:
        result = {
            "rod_bonus": 0,
            "speed_bonus": base_bait_speed,
            "double_catch": False,
            "drop_bonus": 0,
            "rod_level": base_rod_level,
            "difficulty": base_difficulty,
            "wish_active": False,
            "extra_speed_multiplier": 1.0,
            "duoduo_count": 0,
            "weather_speed_multiplier": 1.0,
            "weather_luck_boost": 0,
            "weather_half_bait": False,
            "weather_lost_wind": False,
            "weather_cat_eat": False,
            "lucky_double_active": False,
        }

        for buff in buffs:
            buff_start = _make_naive(buff.start_time)
            buff_end = _make_naive(buff.end_time)
            if buff_start <= target_time < buff_end:
                effect_func = FishingBuffCalculator.BUFF_EFFECTS.get(buff.buff_type)
                if effect_func:
                    key, value = effect_func(buff.value, result)
                    if key in (
                        "rod_bonus",
                        "speed_bonus",
                        "drop_bonus",
                        "duoduo_count",
                        "weather_luck_boost",
                    ):
                        result[key] += value
                    elif key in (
                        "extra_speed_multiplier",
                        "weather_speed_multiplier",
                    ):
                        result[key] *= value
                    else:
                        result[key] = value

        result["rod_level"] = max(
            0, base_rod_level + result["rod_bonus"] - result.get("duoduo_count", 0)
        )

        return result

    @staticmethod
    def calculate_buff_effects(
        buffs: list["FishingBuff"],
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, Any]:
        result = {
            "rod_bonus": 0,
            "speed_bonus": 0,
            "double_catch": False,
            "drop_bonus": 0,
            "extra_speed_multiplier": 1.0,
            "duoduo_count": 0,
            "weather_speed_multiplier": 1.0,
            "weather_luck_boost": 0,
            "weather_half_bait": False,
            "weather_lost_wind": False,
            "weather_cat_eat": False,
        }

        for buff in buffs:
            overlap_start = max(start_time, buff.start_time)
            overlap_end = min(end_time, buff.end_time)
            overlap_duration = (overlap_end - overlap_start).total_seconds()
            total_duration = (end_time - start_time).total_seconds()

            if overlap_duration <= 0:
                continue

            coverage_ratio = (
                overlap_duration / total_duration if total_duration > 0 else 0
            )

            effect_func = FishingBuffCalculator.BUFF_EFFECTS.get(buff.buff_type)
            if effect_func:
                key, value = effect_func(buff.value, result)
                if key in (
                    "rod_bonus",
                    "speed_bonus",
                    "drop_bonus",
                    "duoduo_count",
                    "weather_luck_boost",
                ):
                    result[key] += value
                elif key in (
                    "extra_speed_multiplier",
                    "weather_speed_multiplier",
                ):
                    result[key] *= value
                elif key == "double_catch" and coverage_ratio > 0.5:
                    result[key] = value

        return result
