"""S2 vNext 星穹矿脉的命令行闭环模拟器。

这是设计实验工具，不依赖 NoneBot、数据库或网页资源。它刻意使用固定时间
步进；阶段二的巨大星球数量通过对数表示，避免创建 10**308 个对象。

示例::

    python s2_mining_simulator.py scenario --days 45 --target-log10 11
    python s2_mining_simulator.py repl --target-log10 11
"""

from __future__ import annotations

import argparse
import math
import random
import shlex
from dataclasses import dataclass, field
from typing import Iterable


ORE_NAMES = ("锡矿", "铜矿", "紫晶", "金猫锭", "虹核晶")
ORE_VALUES = (1.0, 2.8, 9.0, 32.0, 120.0)
LOCAL_KEYS = (
    "pickaxe",
    "cart",
    "refinery",
    "survey",
    "cat",
    "industrial_blaster",
    "steam_cart",
    "electric_pickaxe",
    "electric_cart",
    "modern_drill",
    "future_quantum",
    "relativity",
)
CORE_KEYS = (
    "planetary_power",
    "stage_skip",
    "core_survey",
    "entanglement",
    "auto_all",
    "core_quantum",
)


@dataclass(frozen=True)
class LogNumber:
    """非负的科学计数法数值，支持 10**308 级别的计数和外推。"""

    mantissa: float
    exponent: int = 0

    def __post_init__(self) -> None:
        if self.mantissa < 0 or not math.isfinite(self.mantissa):
            raise ValueError("LogNumber 只接受有限的非负尾数")
        if self.mantissa == 0:
            object.__setattr__(self, "exponent", 0)
            return
        exponent = self.exponent
        mantissa = self.mantissa
        while mantissa >= 10:
            mantissa /= 10
            exponent += 1
        while mantissa < 1:
            mantissa *= 10
            exponent -= 1
        object.__setattr__(self, "mantissa", mantissa)
        object.__setattr__(self, "exponent", exponent)

    @classmethod
    def zero(cls) -> "LogNumber":
        return cls(0.0)

    @classmethod
    def one(cls) -> "LogNumber":
        return cls(1.0)

    @classmethod
    def from_int(cls, value: int) -> "LogNumber":
        if value < 0:
            raise ValueError("LogNumber 只接受非负数")
        if value == 0:
            return cls.zero()
        digits = len(str(value))
        return cls(value / (10 ** (digits - 1)), digits - 1)

    @property
    def is_zero(self) -> bool:
        return self.mantissa == 0

    @property
    def log10(self) -> float:
        return -math.inf if self.is_zero else self.exponent + math.log10(self.mantissa)

    def __mul__(self, other: float | int | "LogNumber") -> "LogNumber":
        if isinstance(other, LogNumber):
            if self.is_zero or other.is_zero:
                return LogNumber.zero()
            return LogNumber(self.mantissa * other.mantissa, self.exponent + other.exponent)
        if other < 0:
            raise ValueError("不支持负数")
        return LogNumber(self.mantissa * float(other), self.exponent)

    __rmul__ = __mul__

    def __truediv__(self, other: float | int | "LogNumber") -> "LogNumber":
        if isinstance(other, LogNumber):
            if other.is_zero:
                raise ZeroDivisionError
            if self.is_zero:
                return LogNumber.zero()
            return LogNumber(self.mantissa / other.mantissa, self.exponent - other.exponent)
        if other <= 0:
            raise ValueError("除数必须为正数")
        return LogNumber(self.mantissa / float(other), self.exponent)

    def __add__(self, other: "LogNumber") -> "LogNumber":
        if not isinstance(other, LogNumber):
            return NotImplemented
        if self.is_zero:
            return other
        if other.is_zero:
            return self
        if self.exponent < other.exponent:
            return other + self
        difference = self.exponent - other.exponent
        if difference > 15:
            return self
        return LogNumber(self.mantissa + other.mantissa * (10 ** -difference), self.exponent)

    def __lt__(self, other: "LogNumber") -> bool:
        if self.is_zero:
            return not other.is_zero
        if other.is_zero:
            return False
        return (self.exponent, self.mantissa) < (other.exponent, other.mantissa)

    def __le__(self, other: "LogNumber") -> bool:
        return self == other or self < other

    def __ge__(self, other: "LogNumber") -> bool:
        return not self < other

    def __gt__(self, other: "LogNumber") -> bool:
        return not self <= other

    def __str__(self) -> str:
        if self.is_zero:
            return "0"
        if self.exponent <= 5:
            return f"{self.mantissa * (10 ** self.exponent):,.2f}"
        return f"{self.mantissa:.3g}e{self.exponent}"


@dataclass
class UpgradeSpec:
    key: str
    name: str
    max_level: int
    base_cost: dict[str, float]
    growth: float = 1.38
    unlock: float = 0.0
    local: bool = True
    effect: str = ""
    category: str = "基础"
    effect_kind: str = "none"
    effect_per_level: float = 0.0
    prerequisites: tuple[str, ...] = ()
    special: str = ""
    secondary_kind: str = "none"
    secondary_per_level: float = 0.0


ERA_NODE_NAMES: dict[str, tuple[str, ...]] = {
    "foundation": (
        "地质罗盘", "猫爪耐磨层", "手摇绞盘", "碎石筛分台", "矿灯电池", "双路通风",
        "水压排渣", "安全绳网", "回收熔炉", "应急猫粮", "地层标记", "便携矿仓",
        "低温冷却", "矿脉听诊", "基础测绘", "矿车轴承",
    ),
    "industrial": (
        "高压爆破", "定向炸药", "蒸汽活塞", "锅炉绝热", "重型铰链", "钢轨铺设",
        "矿渣压块", "工业除尘", "液压支架", "连续装载", "熔炉增压", "耐热猫爪",
        "矿井升降机", "燃料回收", "爆破时序", "工业安全协议",
    ),
    "electrical": (
        "电磁钻头", "三相供能", "蓄电矿车", "绝缘猫服", "电弧熔炼", "高频震岩",
        "智能照明", "电网调度", "电容脉冲", "矿石电析", "感应雷达", "电机冷却",
        "远程断路", "备用电池", "电磁吊臂", "电力回收",
    ),
    "modern": (
        "全断面掘进", "激光测距", "无人运输", "液氮破岩", "模块化钻臂", "智能排水",
        "岩层预测", "材料复合", "超硬刀头", "自动换头", "矿尘净化", "地下中继",
        "机械臂编队", "应力平衡", "精密取样", "现代安全网",
    ),
    "future": (
        "纳米钻群", "量子定位", "相位切割", "真空输送", "拓扑矿车", "引力补偿",
        "光子熔炼", "冷核供能", "猫群神经链", "概率采样", "时间标记", "空间折叠",
        "暗能量电池", "量子回收", "奇点预警", "未来工厂",
    ),
    "planetary": (
        "行星地壳扫描", "地核共振", "潮汐钻井", "磁场牵引", "地幔导流", "星球环轨",
        "重力矿车", "地核散热", "行星级猫群", "熔岩隔离", "极点同步", "核心护盾",
        "地质时间压缩", "星球裂隙", "引力透镜", "行星工厂",
    ),
    "anomaly": (
        "相对论回响", "宏观量子纠缠", "真空涨落", "因果回收", "时间膨胀舱", "奇点穿刺",
        "熵减协议", "多维猫爪", "虚数矿脉", "观测者偏置", "宇宙弦牵引", "反物质排渣",
        "无穷压缩", "星门装载", "宇宙背景采样", "终极挖掘许可",
    ),
}

ERA_UNLOCKS = {
    "foundation": 0.0,
    # 前十天需要持续有新选择；行星级之后再把跨度拉开。
    "industrial": 0.00001,
    "electrical": 0.00003,
    "modern": 0.00007,
    "future": 0.00015,
    "planetary": 0.0200,
    "anomaly": 0.0800,
}

# 特殊节点只延后到约 0.002% 深度；普通科技树不会因等待特殊门槛而出现空操作。
SPECIAL_UNLOCK_DELAY = 0.00002
# 跳跃型效果在基础成长完成一个小段后才介入；0.5% 足以避免 D3 突跳。
SPECIAL_BURST_THRESHOLD = 0.005

ERA_LABELS = {
    "foundation": "基础工程",
    "industrial": "工业时代",
    "electrical": "电力时代",
    "modern": "现代时代",
    "future": "未来时代",
    "planetary": "行星时代",
    "anomaly": "异常科技",
}

EFFECT_ROTATION = (
    ("speed_add", 0.10, "推进力"),
    ("depth_efficiency", 0.012, "深度效率"),
    ("yield_add", 0.018, "矿物产量"),
    ("credit_add", 0.020, "矿币收益"),
    ("carry_add", 0.022, "携带量"),
    ("rare_find", 0.004, "稀有矿发现率"),
    ("ore_value", 0.015, "矿石价值"),
    ("noise_reduction", 0.006, "扰动稳定度"),
    ("crit_chance", 0.003, "暴击挖掘率"),
    ("crit_power", 0.012, "暴击倍率"),
    ("salvage", 0.025, "回收收益"),
    ("cat_sync", 0.010, "猫群协同"),
)

SPECIAL_ROTATION = (
    "relativity_burst", "phase_skip", "singularity_finish", "ore_echo", "time_dilation",
    "entropy_guard", "quantum_tunnel", "gravity_sling", "cat_overclock", "core_resonance",
    "parallel_bore", "vacuum_cache",
)


def _specs() -> dict[str, UpgradeSpec]:
    specs = {
        # 初始资源只支持做出一条明确选择；达到 3 级后自动采购再接管成长，避免 D1 手动刷满四条基础线。
        "pickaxe": UpgradeSpec("pickaxe", "矿镐", 100, {"credits": 500}, 1.34, effect="每级 +0.35 基础挖掘力", category="基础工程", effect_kind="speed_add", effect_per_level=0.35),
        "cart": UpgradeSpec("cart", "矿车", 100, {"credits": 750}, 1.35, effect="每级 +0.04 携带量", category="基础工程", effect_kind="carry_add", effect_per_level=0.04),
        "refinery": UpgradeSpec("refinery", "矿石精炼", 100, {"credits": 1100}, 1.36, effect="每级 +0.22 精炼收益", category="基础工程", effect_kind="credit_add", effect_per_level=0.22),
        "survey": UpgradeSpec("survey", "洞穴勘探", 100, {"credits": 1500}, 1.37, effect="每级 +0.25 推进效率", category="基础工程", effect_kind="speed_add", effect_per_level=0.25),
        "cat": UpgradeSpec("cat", "猫矿工", 12, {"credits": 1500}, 2.8, effect="每级复制一份基础挖掘数据", category="基础工程", effect_kind="cat_sync", effect_per_level=0.03),
        "industrial_blaster": UpgradeSpec("industrial_blaster", "爆破镐", 40, {"credits": 12_000, "copper": 50_000}, 1.43, ERA_UNLOCKS["industrial"], effect="每级 +0.30 推进效率", category="工业时代", effect_kind="speed_add", effect_per_level=0.30),
        "steam_cart": UpgradeSpec("steam_cart", "蒸汽矿车", 40, {"credits": 15_000, "copper": 65_000}, 1.43, ERA_UNLOCKS["industrial"], effect="每级 +0.05 携带量", category="工业时代", effect_kind="carry_add", effect_per_level=0.05),
        "electric_pickaxe": UpgradeSpec("electric_pickaxe", "电动镐", 40, {"credits": 80_000, "quartz": 80_000}, 1.47, ERA_UNLOCKS["electrical"], effect="每级 +0.55 基础挖掘力", category="电力时代", effect_kind="speed_add", effect_per_level=0.55),
        "electric_cart": UpgradeSpec("electric_cart", "电力车", 40, {"credits": 90_000, "quartz": 90_000}, 1.47, ERA_UNLOCKS["electrical"], effect="每级 +0.08 携带量", category="电力时代", effect_kind="carry_add", effect_per_level=0.08),
        "modern_drill": UpgradeSpec("modern_drill", "掘进机", 40, {"credits": 500_000, "gold": 50_000}, 1.50, ERA_UNLOCKS["modern"], effect="每级 +0.90 推进效率", category="现代时代", effect_kind="speed_add", effect_per_level=0.90),
        "future_quantum": UpgradeSpec("future_quantum", "微观量子挖掘", 30, {"credits": 4_000_000, "gold": 200_000, "coreshard": 20_000}, 1.55, ERA_UNLOCKS["future"], effect="每级 +1.50 推进效率", category="未来时代", effect_kind="speed_add", effect_per_level=1.50),
        "relativity": UpgradeSpec("relativity", "相对论效应", 10, {"credits": 2.0e6, "coreshard": 40}, 1.72, ERA_UNLOCKS["anomaly"] + 0.02, effect="重生后 60 秒速度 ×100", category="异常科技", special="relativity_burst"),
        "planetary_power": UpgradeSpec("planetary_power", "行星之力", 100, {"cores": 1}, 1.0, local=False, effect="每级 +1.00 全局速度，首级使速度翻倍"),
        "stage_skip": UpgradeSpec("stage_skip", "阶段跳过", 20, {"cores": 2}, 1.0, local=False, effect="每级减少 8% 星球深度需求"),
        "core_survey": UpgradeSpec("core_survey", "核心勘探技术", 50, {"cores": 3}, 1.0, local=False, effect="每级额外获得 1 个核心"),
        "entanglement": UpgradeSpec("entanglement", "宏观量子纠缠", 40, {"cores": 5}, 1.0, local=False, effect="每级让爆星时额外摧毁 25% 星球"),
        "auto_all": UpgradeSpec("auto_all", "全自动采购", 1, {"cores": 8}, 1.0, local=False, effect="所有本地升级都可自动购买"),
        "core_quantum": UpgradeSpec("core_quantum", "核心量子加速", 50, {"cores": 8}, 1.0, local=False, effect="每级 +1.50 全局速度"),
    }
    era_costs = {
        # 每个时代绑定一种主要矿物；这样矿物会改变升级路线，而不是只作为展示数字。
        "foundation": {"credits": 180, "tin": 500},
        "industrial": {"credits": 12_000, "copper": 50_000},
        "electrical": {"credits": 80_000, "quartz": 80_000},
        "modern": {"credits": 500_000, "gold": 50_000},
        "future": {"credits": 4_000_000, "gold": 200_000, "coreshard": 20_000},
        "planetary": {"credits": 50_000_000, "gold": 1_000_000, "coreshard": 100_000},
        "anomaly": {"credits": 500_000_000, "coreshard": 500_000},
    }
    for era_index, (era, names) in enumerate(ERA_NODE_NAMES.items()):
        for index, name in enumerate(names):
            effect_kind, per_level, effect_label = EFFECT_ROTATION[(index + era_index * 3) % len(EFFECT_ROTATION)]
            key = f"{era}_{index + 1:02d}"
            special = SPECIAL_ROTATION[(index + era_index) % len(SPECIAL_ROTATION)] if index % 4 == 0 else ""
            secondary_kind, secondary_per_level, secondary_label = EFFECT_ROTATION[(index * 2 + era_index + 5) % len(EFFECT_ROTATION)] if index % 3 == 0 else ("none", 0.0, "")
            per_level *= 1.0 + era_index * 0.08 + index * 0.006
            secondary_per_level *= 1.0 + era_index * 0.05
            max_level = 8 + ((index + era_index) % 5)
            growth = 1.30 + era_index * 0.025 + (index % 3) * 0.015
            # 科技树的顺序由时代和资源成本表达；特殊效果不再要求玩家先点某个无关节点。
            prerequisites = ()
            effect_text = f"{ERA_LABELS[era]}：每级 +{per_level:g} {effect_label}"
            if secondary_kind != "none":
                effect_text += f"；每级 +{secondary_per_level:g} {secondary_label}"
            specs[key] = UpgradeSpec(
                key,
                name,
                max_level,
                era_costs[era],
                growth,
                ERA_UNLOCKS[era] + (SPECIAL_UNLOCK_DELAY if special else 0.0),
                True,
                effect_text,
                ERA_LABELS[era],
                effect_kind,
                per_level,
                prerequisites,
                special=special,
                secondary_kind=secondary_kind,
                secondary_per_level=secondary_per_level,
            )
    return specs


SPECS = _specs()
# 注册表是阶段一内容的唯一来源，避免新增科技后忘记加入重置、自动采购或状态显示。
LOCAL_KEYS = tuple(key for key, spec in SPECS.items() if spec.local)
CORE_KEYS = tuple(key for key, spec in SPECS.items() if not spec.local)


@dataclass
class SimulationState:
    target_depth: float = 1_000_000.0
    seed: int = 42
    deterministic: bool = False
    enforce_daily_limit: bool = True
    day: int = 1
    minute: int = 0
    depth: float = 0.0
    planets: LogNumber = field(default_factory=LogNumber.zero)
    cores: LogNumber = field(default_factory=LogNumber.zero)
    resources: dict[str, float] = field(default_factory=lambda: {
        "tin": 0.0,
        "copper": 0.0,
        "quartz": 0.0,
        "gold": 0.0,
        "coreshard": 0.0,
        "credits": 0.0,
    })
    local_levels: dict[str, int] = field(default_factory=dict)
    permanent_levels: dict[str, int] = field(default_factory=dict)
    auto_unlocked: set[str] = field(default_factory=set)
    ever_local_keys: set[str] = field(default_factory=set)
    lifetime_levels: dict[str, int] = field(default_factory=dict)
    daily_upgrade_messages: int = 0
    max_daily_upgrade_messages: int = 0
    total_upgrade_messages: int = 0
    first_reset_day: int | None = None
    max_speed_seen: float = 1.0
    burst_seconds: int = 0
    fractional_planets: float = 0.0
    auto_cursor: int = 0
    reset_days: list[int] = field(default_factory=list)
    era_first_days: dict[str, int] = field(default_factory=dict)
    special_triggers: dict[str, int] = field(default_factory=dict)
    _effects_cache: dict[str, float] | None = field(default=None, init=False, repr=False)
    _special_cache: dict[str, int] | None = field(default=None, init=False, repr=False)
    rng: random.Random = field(init=False, repr=False)
    events: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        for key in LOCAL_KEYS:
            self.local_levels.setdefault(key, 0)
            self.lifetime_levels.setdefault(key, 0)
        for key in CORE_KEYS:
            self.permanent_levels.setdefault(key, 0)
        for special in SPECIAL_ROTATION:
            self.special_triggers.setdefault(special, 0)

    @property
    def progress(self) -> float:
        return min(1.0, self.depth / self.target_depth)

    @property
    def active_auto_keys(self) -> set[str]:
        if self.permanent_levels["auto_all"]:
            return set(LOCAL_KEYS)
        return set(self.auto_unlocked)

    def level(self, key: str) -> int:
        return self.permanent_levels.get(key, 0) + self.local_levels.get(key, 0) if not SPECS[key].local else self.local_levels.get(key, 0)

    def effect_totals(self) -> dict[str, float]:
        if self._effects_cache is not None:
            return self._effects_cache
        totals: dict[str, float] = {}
        for key in LOCAL_KEYS:
            level = self.local_levels.get(key, 0)
            spec = SPECS[key]
            if level and spec.effect_kind != "none":
                totals[spec.effect_kind] = totals.get(spec.effect_kind, 0.0) + level * spec.effect_per_level
            if level and spec.secondary_kind != "none":
                totals[spec.secondary_kind] = totals.get(spec.secondary_kind, 0.0) + level * spec.secondary_per_level
        self._effects_cache = totals
        return totals

    def special_level(self, special: str) -> int:
        if self._special_cache is None:
            self._special_cache = {
                name: sum(self.local_levels.get(key, 0) for key in LOCAL_KEYS if SPECS[key].special == name)
                for name in SPECIAL_ROTATION
            }
        return self._special_cache.get(special, 0)

    def _mark_special(self, special: str) -> None:
        if special in self.special_triggers:
            self.special_triggers[special] += 1

    def _cost_for(self, key: str, level: int) -> dict[str, float]:
        spec = SPECS[key]
        multiplier = spec.growth**level if spec.growth != 1 else 1.0
        return {resource: cost * multiplier for resource, cost in spec.base_cost.items()}

    def _core_count_as_float(self) -> float:
        if self.cores.exponent > 15:
            return math.inf
        return self.cores.mantissa * 10**self.cores.exponent

    def _pay_cores(self, amount: int) -> None:
        current = self._core_count_as_float()
        if current < amount:
            raise ValueError("核心不足")
        self.cores = LogNumber.from_int(max(0, int(current - amount)))

    def _available(self, key: str) -> bool:
        spec = SPECS[key]
        if not spec.local:
            return True
        if self.progress < spec.unlock and key not in self.active_auto_keys:
            return False
        return all(self.local_levels.get(required, 0) >= 1 for required in spec.prerequisites)

    def _batch_cost(self, key: str, amount: int) -> dict[str, float]:
        level = self.local_levels[key] if SPECS[key].local else self.permanent_levels[key]
        total: dict[str, float] = {}
        for offset in range(amount):
            for resource, cost in self._cost_for(key, level + offset).items():
                total[resource] = total.get(resource, 0.0) + cost
        return total

    def upgrade_command(self, orders: Iterable[tuple[str, int]], *, automatic: bool = False) -> tuple[bool, str]:
        """一次消息可买多个项目；手动消息每天最多三条。"""
        if not automatic and self.enforce_daily_limit and self.daily_upgrade_messages >= 3:
            return False, "今天的升级消息已用完（3/3）"
        normalized: list[tuple[str, int]] = []
        for key, amount in orders:
            if key not in SPECS or amount <= 0:
                return False, f"未知升级或数量无效: {key}"
            spec = SPECS[key]
            level = self.local_levels[key] if spec.local else self.permanent_levels[key]
            if level + amount > spec.max_level:
                return False, f"{spec.name}最多 {spec.max_level} 级"
            if spec.local and not self._available(key):
                return False, f"{spec.name}尚未达到深度解锁条件"
            normalized.append((key, amount))
        if not normalized:
            return False, "没有升级项目"

        total: dict[str, float] = {}
        for key, amount in normalized:
            for resource, cost in self._batch_cost(key, amount).items():
                total[resource] = total.get(resource, 0.0) + cost
        for resource, cost in total.items():
            if resource == "cores":
                if self._core_count_as_float() < cost:
                    return False, f"核心不足，需要 {cost:.0f}"
            elif self.resources.get(resource, 0.0) + 1e-9 < cost:
                return False, f"{resource}不足，需要 {cost:.1f}"

        for resource, cost in total.items():
            if resource == "cores":
                self._pay_cores(math.ceil(cost))
            else:
                self.resources[resource] -= cost
        for key, amount in normalized:
            spec = SPECS[key]
            levels = self.permanent_levels if not spec.local else self.local_levels
            was_seen = key in self.ever_local_keys
            levels[key] += amount
            if spec.local:
                self.ever_local_keys.add(key)
                self.lifetime_levels[key] += amount
                if not was_seen:
                    self.era_first_days.setdefault(spec.category, self.day)
            if spec.local and levels[key] >= 3:
                self.auto_unlocked.add(key)
            if key in CORE_KEYS and key == "auto_all":
                self.events.append("核心科技：全自动采购已启用")
        self._effects_cache = None
        self._special_cache = None
        if not automatic:
            self.daily_upgrade_messages += 1
            self.max_daily_upgrade_messages = max(self.max_daily_upgrade_messages, self.daily_upgrade_messages)
            self.total_upgrade_messages += 1
        return True, "、".join(f"{SPECS[key].name}+{amount}" for key, amount in normalized)

    def auto_purchase(self) -> int:
        bought = 0
        active = sorted(self.active_auto_keys)
        if not active:
            return 0
        # 自动采购是后台任务，不必每分钟扫描全部科技；轮转保证最迟数个周期覆盖所有线路。
        budget = min(24, len(active))
        start = self.auto_cursor % len(active)
        keys = [active[(start + offset) % len(active)] for offset in range(budget)]
        self.auto_cursor = (start + budget) % len(active)
        for key in keys:
            if key not in self.active_auto_keys or not self._available(key):
                continue
            ok, _ = self.upgrade_command([(key, 1)], automatic=True)
            if ok:
                bought += 1
        return bought

    def _speed_multiplier(self) -> float:
        local = self.local_levels
        effects = self.effect_totals()
        base = 1.0 + effects.get("speed_add", 0.0)
        base *= 1.0 + effects.get("depth_efficiency", 0.0)
        workers = 1 + min(12, local["cat"])
        base *= workers * (1.0 + effects.get("cat_sync", 0.0))
        base *= 1.0 + effects.get("carry_add", 0.0) * 0.35
        permanent = 1.0 + self.permanent_levels["planetary_power"]
        permanent += 1.5 * self.permanent_levels["core_quantum"]
        if self.burst_seconds > 0:
            permanent *= 100.0
        return max(1.0, base * permanent)

    def _yield_ores(self) -> dict[str, float]:
        p = self.progress
        effects = self.effect_totals()
        weights = [0.68, 0.25, 0.055, 0.014, 0.001]
        if p > 0.12:
            weights[0] -= 0.08
            weights[1] += 0.05
            weights[2] += 0.02
            weights[3] += 0.009
            weights[4] += 0.001
        if p > 0.58:
            weights[0] -= 0.08
            weights[1] -= 0.02
            weights[2] += 0.04
            weights[3] += 0.04
            weights[4] += 0.02
        rare = min(0.40, effects.get("rare_find", 0.0) + self.special_level("ore_echo") * 0.01)
        weights[0] = max(0.10, weights[0] - rare * 0.50)
        weights[1] += rare * 0.24
        weights[2] += rare * 0.16
        weights[3] += rare * 0.08
        weights[4] += rare * 0.02
        total = 10.0 * self._speed_multiplier() * (1.0 + effects.get("carry_add", 0.0))
        total *= 1.0 + effects.get("yield_add", 0.0)
        noise_sigma = max(
            0.010,
            0.08 - effects.get("noise_reduction", 0.0) - 0.010 * self.special_level("entropy_guard"),
        )
        noise = 1.0 if self.deterministic else max(0.70, min(1.30, self.rng.gauss(1.0, noise_sigma)))
        parallel_level = self.special_level("parallel_bore")
        if parallel_level:
            chance = min(0.25, 0.01 * parallel_level)
            if self.deterministic:
                # 固定序列取期望收益，不掷骰子也保留特殊科技的长期价值。
                total *= 1.0 + chance
            elif self.rng.random() < chance:
                self._mark_special("parallel_bore")
                total *= 2.0
        total *= noise
        return {name: total * weight for name, weight in zip(ORE_NAMES, weights)}

    def mine_minute(self, minutes: int = 1) -> list[str]:
        events: list[str] = []
        for _ in range(minutes):
            if self.depth >= self.target_depth:
                events.append(self.prestige())
            depth_gain = 8.0 * self._speed_multiplier()
            self.max_speed_seen = max(self.max_speed_seen, self._speed_multiplier())
            effects = self.effect_totals()
            # 这些计数不是额外收益，只用于阶段审计确认特殊科技确实参与过结算。
            if self.special_level("ore_echo"):
                self._mark_special("ore_echo")
            if self.special_level("entropy_guard"):
                self._mark_special("entropy_guard")
            if self.special_level("time_dilation"):
                self._mark_special("time_dilation")
            depth_gain *= 1.0 + effects.get("speed_add", 0.0) * 0.02
            if not self.deterministic:
                depth_gain *= max(0.70, min(1.30, self.rng.gauss(1.0, max(0.01, 0.025 - effects.get("noise_reduction", 0.0) * 0.25))))
            if self.special_level("gravity_sling") and 0.25 < self.progress < 0.75:
                self._mark_special("gravity_sling")
                depth_gain *= 1.0 + 0.10 * self.special_level("gravity_sling")
            if self.special_level("time_dilation"):
                depth_gain *= 1.0 + 0.015 * self.special_level("time_dilation")
            local_cat = self.local_levels["cat"]
            cat_overclock_level = self.special_level("cat_overclock")
            if cat_overclock_level and local_cat:
                self._mark_special("cat_overclock")
                chance = min(0.25, 0.02 * local_cat * cat_overclock_level)
                if self.deterministic:
                    depth_gain *= 1.0 + chance
                elif self.rng.random() < chance:
                    depth_gain *= 2.0
            crit_chance = min(0.40, effects.get("crit_chance", 0.0))
            if crit_chance:
                crit_power = max(0.20, effects.get("crit_power", 0.0))
                if self.deterministic:
                    depth_gain *= 1.0 + crit_chance * crit_power
                elif self.rng.random() < crit_chance:
                    depth_gain *= 1.0 + crit_power
            remaining = self.target_depth - self.depth
            self.depth += min(remaining, depth_gain)
            phase_level = self.special_level("phase_skip")
            if phase_level and self.progress >= SPECIAL_BURST_THRESHOLD:
                if self.deterministic:
                    if self.minute % 60 == 0:
                        self._mark_special("phase_skip")
                        self.depth += self.target_depth * 0.0005 * phase_level
                elif self.rng.random() < 0.001 * phase_level:
                    self._mark_special("phase_skip")
                    self.depth += self.target_depth * 0.0005
            quantum_level = self.special_level("quantum_tunnel")
            if quantum_level and self.progress >= SPECIAL_BURST_THRESHOLD:
                if self.deterministic:
                    if self.minute % 60 == 0:
                        self._mark_special("quantum_tunnel")
                        self.depth += self.target_depth * 0.001 * quantum_level
                elif self.rng.random() < 0.0002 * quantum_level:
                    self._mark_special("quantum_tunnel")
                    self.depth += self.target_depth * 0.001
            if self.special_level("singularity_finish") and self.progress >= 0.97:
                self._mark_special("singularity_finish")
                self.depth += self.target_depth * 0.01 * self.special_level("singularity_finish")
            self.depth = min(self.target_depth, self.depth)
            ores = self._yield_ores()
            for name, amount in ores.items():
                key = {"锡矿": "tin", "铜矿": "copper", "紫晶": "quartz", "金猫锭": "gold", "虹核晶": "coreshard"}[name]
                self.resources[key] += amount
            refine = 0.72 + effects.get("credit_add", 0.0)
            ore_value = 1.0 + effects.get("ore_value", 0.0)
            salvage = 1.0 + effects.get("salvage", 0.0)
            self.resources["credits"] += sum(ores[name] * value for name, value in zip(ORE_NAMES, ORE_VALUES)) * refine * ore_value * salvage
            if self.special_level("vacuum_cache"):
                self._mark_special("vacuum_cache")
                self.resources["credits"] += self._speed_multiplier() * 0.50 * self.special_level("vacuum_cache")
            self.minute += 1
            if self.burst_seconds > 0:
                self.burst_seconds = max(0, self.burst_seconds - 60)
            # 固定步进测试每 10 分钟结算一次自动采购；玩家的小时决策不阻塞后台成长。
            if self.minute % 10 == 0:
                self.auto_purchase()
            if self.depth >= self.target_depth:
                events.append(self.prestige())
        self.events.extend(events)
        return events

    def mine_block(self, minutes: int = 10) -> list[str]:
        """按原型测试的固定步长结算；用整块步进减少测试开销但不跳过中间自动采购。"""
        if minutes != 10:
            raise ValueError("原型测试固定使用 10 分钟步长")
        return self.mine_minute(minutes)

    def prestige(self) -> str:
        survey = self.permanent_levels["core_survey"]
        entanglement = self.permanent_levels["entanglement"]
        relativity_active = self.special_level("relativity_burst") > 0
        if relativity_active:
            self._mark_special("relativity_burst")
        if self.special_level("core_resonance"):
            self._mark_special("core_resonance")
        gain = 1 + survey + self.special_level("core_resonance")
        self.fractional_planets += entanglement * 0.25
        extra = int(self.fractional_planets)
        self.fractional_planets -= extra
        destroyed = 1 + extra
        if self.planets.is_zero and self.first_reset_day is None:
            self.first_reset_day = self.day
        self.reset_days.append(self.day)
        self.planets = self.planets + LogNumber.from_int(destroyed)
        self.cores = self.cores + LogNumber.from_int(gain)
        self.depth = 0.0
        self.resources = {key: 0.0 for key in self.resources}
        for key in LOCAL_KEYS:
            self.local_levels[key] = 0
        self.auto_cursor = 0
        self._effects_cache = None
        self._special_cache = None
        self.burst_seconds = 60 if relativity_active else 0
        self.events.append(f"星球爆裂：摧毁 {destroyed} 颗，获得核心 {gain} 个")
        return self.events[-1]

    def start_new_day(self) -> None:
        self.day += 1
        self.daily_upgrade_messages = 0

    def spendable_resources(self) -> dict[str, float | str]:
        result: dict[str, float | str] = dict(self.resources)
        result["cores"] = str(self.cores)
        return result

    def stage_coverage(self) -> dict[str, int]:
        return {
            category: sum(1 for key in self.ever_local_keys if SPECS[key].category == category)
            for category in sorted({SPECS[key].category for key in LOCAL_KEYS})
        }

    def summary(self) -> str:
        local = ", ".join(f"{SPECS[k].name}{v}" for k, v in self.local_levels.items() if v)
        permanent = ", ".join(f"{SPECS[k].name}{v}" for k, v in self.permanent_levels.items() if v)
        return (
            f"第{self.day}天 {self.minute % 1440:04d}分 | 深度 {self.depth:.2f}/{self.target_depth:.2g} "
            f"({self.progress:.1%}) | 星球 {self.planets} | 核心 {self.cores}\n"
            f"资源 credits={self.resources['credits']:.1f}, tin={self.resources['tin']:.1f}, "
            f"copper={self.resources['copper']:.1f}, quartz={self.resources['quartz']:.1f}, "
            f"gold={self.resources['gold']:.1f}, shard={self.resources['coreshard']:.1f}\n"
            f"本日升级消息 {self.daily_upgrade_messages}/3 | 本地 [{local or '无'}] | 永久 [{permanent or '无'}]"
            f"\n阶段一已触达 {len(self.ever_local_keys)}/{len(LOCAL_KEYS)} 条科技"
        )

    def project_stage_two(self, target_log10: int = 308) -> dict[str, float | int | str]:
        """用稳定态单星球耗时外推到目标数量，不实际循环巨量星球。"""
        speed = self._speed_multiplier()
        effective_target = self.target_depth * max(0.02, 1.0 - 0.08 * self.permanent_levels["stage_skip"])
        minutes_per_planet = max(1.0, effective_target / (8.0 * speed))
        core_gain = 1 + self.permanent_levels["core_survey"]
        planet_multiplier = 1.0 + 0.25 * self.permanent_levels["entanglement"]
        return {
            "target_log10": target_log10,
            "minutes_per_planet": minutes_per_planet,
            "core_per_planet": core_gain,
            "expected_planets_per_reset": planet_multiplier,
            "log10_minutes_to_target": target_log10 + math.log10(minutes_per_planet) - math.log10(planet_multiplier),
            "stable_speed": speed,
        }


@dataclass(frozen=True)
class StageOneAudit:
    """阶段一签收用的机器可读指标，防止只看最终资源而漏掉体验退化。"""

    seed: int
    simulated_days: int
    first_reset_day: int | None
    planets: LogNumber
    local_nodes_reached: int
    local_nodes_total: int
    special_nodes_reached: int
    special_nodes_total: int
    special_effects_exercised: int
    special_effects_total: int
    reset_count: int
    max_daily_messages: int
    max_speed: float
    category_coverage: dict[str, int]
    era_first_days: dict[str, int]

    @property
    def passed(self) -> bool:
        return (
            self.first_reset_day is not None
            # 天数只用于排除明显失速或瞬间通关；最终体验允许落在更宽的 50～100 天窗口。
            and 15 <= self.first_reset_day <= 45
            and self.local_nodes_reached == self.local_nodes_total
            and self.special_nodes_reached == self.special_nodes_total
            and self.special_effects_exercised == self.special_effects_total
            and self.reset_count >= 1
            and self.max_daily_messages <= 3
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "simulated_days": self.simulated_days,
            "first_reset_day": self.first_reset_day,
            "planets": str(self.planets),
            "local_nodes": f"{self.local_nodes_reached}/{self.local_nodes_total}",
            "special_nodes": f"{self.special_nodes_reached}/{self.special_nodes_total}",
            "special_effects": f"{self.special_effects_exercised}/{self.special_effects_total}",
            "reset_count": self.reset_count,
            "max_daily_messages": self.max_daily_messages,
            "max_speed": self.max_speed,
            "category_coverage": self.category_coverage,
            "era_first_days": self.era_first_days,
            "passed": self.passed,
        }


def audit_stage_one(state: SimulationState) -> StageOneAudit:
    reached_special = sum(1 for key in state.ever_local_keys if SPECS[key].special)
    total_special = sum(1 for key in LOCAL_KEYS if SPECS[key].special)
    return StageOneAudit(
        seed=state.seed,
        simulated_days=state.day,
        first_reset_day=state.first_reset_day,
        planets=state.planets,
        local_nodes_reached=len(state.ever_local_keys),
        local_nodes_total=len(LOCAL_KEYS),
        special_nodes_reached=reached_special,
        special_nodes_total=total_special,
        special_effects_exercised=sum(1 for count in state.special_triggers.values() if count > 0),
        special_effects_total=len(SPECIAL_ROTATION),
        reset_count=len(state.reset_days),
        max_daily_messages=state.max_daily_upgrade_messages,
        max_speed=state.max_speed_seen,
        category_coverage=state.stage_coverage(),
        era_first_days=dict(state.era_first_days),
    )


def run_stage_one_matrix(
    seeds: Iterable[int] = (1, 42, 2026),
    days: int = 45,
    target_log10: int = 11,
    strategy_mode: str = "balanced",
) -> list[StageOneAudit]:
    audits: list[StageOneAudit] = []
    for seed in seeds:
        state, _ = run_scenario(days, seed, target_log10, strategy_mode)
        audits.append(audit_stage_one(state))
    return audits


def _strategy(state: SimulationState, message_budget: int = 3, mode: str = "balanced") -> None:
    """一个有意保守的每日策略，用来观察曲线而不是寻找最优解。"""
    message_limit = min(3, state.daily_upgrade_messages + max(0, message_budget))
    if state.daily_upgrade_messages >= message_limit:
        return
    # 新时代的特殊科技优先于核心消费，避免玩家刚抵达地心就因重生而错过科技窗口。
    unseen_special = any(
        state._available(key) and SPECS[key].special and key not in state.ever_local_keys
        for key in LOCAL_KEYS
    )
    if not state.planets.is_zero and not unseen_special:
        core_plans = [
            ("planetary_power", 1, 1),
            ("stage_skip", 1, 2),
            ("core_survey", 1, 3),
            ("entanglement", 1, 5),
            ("auto_all", 1, 8),
            ("core_quantum", 1, 8),
        ]
        for key, amount, minimum in core_plans:
            if state.daily_upgrade_messages >= message_limit:
                break
            if key != "auto_all" and state.permanent_levels[key] >= 3:
                continue
            if state.permanent_levels[key] >= SPECS[key].max_level:
                continue
            if state._core_count_as_float() < minimum:
                continue
            ok, _ = state.upgrade_command([(key, amount)])
            if ok and key in {"auto_all", "core_survey"}:
                break
    legacy_priority = [
        "pickaxe", "cart", "refinery", "survey", "cat", "industrial_blaster", "steam_cart",
        "electric_pickaxe", "electric_cart", "modern_drill", "future_quantum", "relativity",
    ]
    priority_index = {key: index for index, key in enumerate(legacy_priority)}
    preferred_effects = {
        "speed": {"speed_add", "depth_efficiency"},
        "yield": {"yield_add", "credit_add", "carry_add", "ore_value"},
        "research": {"rare_find", "noise_reduction", "salvage"},
        "cat": {"cat_sync"},
    }.get(mode, set())
    candidates = [
        key for key in LOCAL_KEYS
        if state._available(key) and state.level(key) < SPECS[key].max_level
    ]
    candidates.sort(
        key=lambda key: (
            0 if state.level(key) == 0 and SPECS[key].special and key not in state.ever_local_keys else 1 if state.level(key) == 0 else 2,
            0 if state.level(key) == 0 and key in priority_index and key not in state.ever_local_keys else 1,
            0 if key in priority_index and state.level(key) < 3 else 1,
            0 if SPECS[key].effect_kind in preferred_effects else 1,
            SPECS[key].unlock,
            priority_index.get(key, 100),
            key,
        )
    )
    while state.daily_upgrade_messages < message_limit and candidates:
        orders: list[tuple[str, int]] = []
        for key in candidates:
            level = state.level(key)
            if level >= SPECS[key].max_level:
                continue
            amount = min(3 - level, 3) if level < 3 else 1
            # 一条 QQ 消息允许批量多个项目；这里限制条目数，防止日志和决策面一次膨胀过头。
            orders.append((key, amount))
            if len(orders) >= 8:
                break
        if not orders:
            break
        ok, _ = state.upgrade_command(orders)
        if not ok:
            # 成本不足时逐半缩小批次，保持“消息可批量”而不是整条消息报废。
            reduced = orders[: max(1, len(orders) // 2)]
            ok, _ = state.upgrade_command(reduced)
            if not ok and len(reduced) > 1:
                ok, _ = state.upgrade_command(reduced[:1])
            if not ok:
                break
        candidates = [
            key for key in candidates
            if state._available(key) and state.level(key) < SPECS[key].max_level
        ]


def _development_target(target_log10: int) -> float:
    # 10^308 只用于阶段二外推；阶段一仍用可观察的开发目标跑精确分钟步。
    if target_log10 == 11:
        # 这一档不是数学上的 10^11，而是校准后的 6×10^11，
        # 用来让时代解锁和首轮重生同时落在可审查的窗口内。
        return 600_000_000_000.0
    return 10**target_log10 if target_log10 <= 12 else 10_000_000_000.0


def run_scenario(days: int = 60, seed: int = 42, target_log10: int = 11, strategy_mode: str = "balanced") -> tuple[SimulationState, list[str]]:
    target = _development_target(target_log10)
    state = SimulationState(target_depth=target, seed=seed)
    log: list[str] = []
    milestone_days = {1, 2, 3, 7, 11, 15, 20, 25, 30, 37, 45, 50, days}
    for day in range(1, days + 1):
        if day > 1:
            state.start_new_day()
        for _ in range(3):
            _strategy(state, message_budget=1, mode=strategy_mode)
            state.mine_minute(480)
        if day in milestone_days:
            log.append(f"D{day:02d}: {state.summary()}")
        state.events.clear()
    log.append(
        f"阶段一审查：已触达 {len(state.ever_local_keys)}/{len(LOCAL_KEYS)} 条本地科技，"
        f"特殊科技 {sum(1 for key in state.ever_local_keys if SPECS[key].special)}/{sum(1 for key in LOCAL_KEYS if SPECS[key].special)} 条"
    )
    return state, log


def parse_orders(tokens: list[str]) -> list[tuple[str, int]]:
    aliases = {
        "镐子": "pickaxe", "矿镐": "pickaxe", "矿车": "cart", "精炼": "refinery",
        "勘探": "survey", "爆破镐": "industrial_blaster", "蒸汽矿车": "steam_cart",
        "电动镐": "electric_pickaxe", "电力车": "electric_cart", "掘进机": "modern_drill",
        "量子挖掘": "future_quantum", "相对论": "relativity", "行星之力": "planetary_power",
        "阶段跳过": "stage_skip", "核心勘探": "core_survey", "量子纠缠": "entanglement",
        "全自动": "auto_all", "核心加速": "core_quantum",
    }
    orders: list[tuple[str, int]] = []
    for token in tokens:
        if "=" in token:
            key, raw_amount = token.split("=", 1)
        elif ":" in token:
            key, raw_amount = token.split(":", 1)
        else:
            key, raw_amount = token, "1"
        key = aliases.get(key, key)
        orders.append((key, int(raw_amount)))
    return orders


def repl(target_log10: int, seed: int) -> None:
    target = _development_target(target_log10)
    state = SimulationState(target_depth=target, seed=seed)
    print("S2 vNext 命令行实验室。输入 帮助 查看命令，输入 退出 结束。")
    print(state.summary())
    while True:
        try:
            raw = input("s2> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not raw:
            continue
        parts = shlex.split(raw)
        command = parts[0].lower()
        if command in {"退出", "quit", "q"}:
            return
        if command in {"帮助", "help"}:
            print("挖矿 [分钟] | 升级 镐子=2 矿车=1 | 状态 | 模拟 [天] | 外推 [log10] | 退出")
            continue
        if command in {"状态", "status"}:
            print(state.summary())
            continue
        if command in {"挖矿", "mine"}:
            minutes = int(parts[1]) if len(parts) > 1 else 60
            print("\n".join(state.mine_minute(minutes)) or f"已推进 {minutes} 分钟")
            print(state.summary())
            continue
        if command in {"升级", "upgrade"}:
            try:
                ok, message = state.upgrade_command(parse_orders(parts[1:]))
            except (ValueError, IndexError) as exc:
                ok, message = False, str(exc)
            print(("成功：" if ok else "失败：") + message)
            continue
        if command in {"模拟", "simulate"}:
            days = int(parts[1]) if len(parts) > 1 else 1
            for _ in range(days):
                for _ in range(3):
                    _strategy(state, message_budget=1, mode="balanced")
                    state.mine_minute(480)
                state.start_new_day()
            print(state.summary())
            continue
        if command in {"外推", "project"}:
            log10 = int(parts[1]) if len(parts) > 1 else 308
            print(state.project_stage_two(log10))
            continue
        print("未知命令，输入 帮助 查看命令。")


def main() -> None:
    parser = argparse.ArgumentParser(description="S2 vNext 星穹矿脉命令行模拟器")
    subparsers = parser.add_subparsers(dest="command", required=True)
    scenario = subparsers.add_parser("scenario", help="运行预设体验策略")
    scenario.add_argument("--days", type=int, default=60)
    scenario.add_argument("--seed", type=int, default=42)
    scenario.add_argument("--target-log10", type=int, default=11, help="单星球深度的数量级，支持 308（阶段一仍用开发目标精确跑）")
    scenario.add_argument("--summary-only", action="store_true")
    scenario.add_argument("--strategy", choices=("balanced", "speed", "yield", "research", "cat"), default="balanced")
    interactive = subparsers.add_parser("repl", help="进入交互式命令行")
    interactive.add_argument("--seed", type=int, default=42)
    interactive.add_argument("--target-log10", type=int, default=11)
    args = parser.parse_args()
    if args.command == "scenario":
        state, log = run_scenario(args.days, args.seed, args.target_log10, args.strategy)
        if args.summary_only:
            print(state.summary())
        else:
            print("\n\n".join(log))
    else:
        repl(args.target_log10, args.seed)


if __name__ == "__main__":
    main()
