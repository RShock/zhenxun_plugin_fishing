"""S2 vNext 星穹矿脉的命令行闭环模拟器。

这是设计实验工具，不依赖 NoneBot、数据库或网页资源。它刻意使用固定时间
步进；阶段二的巨大星球数量通过对数表示，避免创建 10**308 个对象。

示例::

    python s2_mining_simulator.py scenario --days 60 --target-log10 9
    python s2_mining_simulator.py repl --target-log10 9
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


def _specs() -> dict[str, UpgradeSpec]:
    return {
        "pickaxe": UpgradeSpec("pickaxe", "矿镐", 100, {"credits": 35}, 1.34, effect="每级 +0.35 基础挖掘力"),
        "cart": UpgradeSpec("cart", "矿车", 100, {"credits": 50}, 1.35, effect="每级 +0.20 携带量"),
        "refinery": UpgradeSpec("refinery", "矿石精炼", 100, {"credits": 80}, 1.36, effect="每级 +0.22 精炼收益"),
        "survey": UpgradeSpec("survey", "洞穴勘探", 100, {"credits": 110}, 1.37, effect="每级 +0.25 推进效率"),
        "cat": UpgradeSpec("cat", "猫矿工", 12, {"credits": 1500}, 2.8, effect="每级复制一份基础挖掘数据"),
        "industrial_blaster": UpgradeSpec("industrial_blaster", "爆破镐", 40, {"credits": 600, "copper": 40}, 1.43, 0.10, effect="每级 +0.30 推进效率"),
        "steam_cart": UpgradeSpec("steam_cart", "蒸汽矿车", 40, {"credits": 750, "copper": 60}, 1.43, 0.10, effect="每级 +0.28 携带量"),
        "electric_pickaxe": UpgradeSpec("electric_pickaxe", "电动镐", 40, {"credits": 3200, "quartz": 35}, 1.47, 0.35, effect="每级 +0.55 基础挖掘力"),
        "electric_cart": UpgradeSpec("electric_cart", "电力车", 40, {"credits": 4000, "quartz": 50}, 1.47, 0.35, effect="每级 +0.50 携带量"),
        "modern_drill": UpgradeSpec("modern_drill", "掘进机", 40, {"credits": 18000, "gold": 20}, 1.50, 0.55, effect="每级 +0.90 推进效率"),
        "future_quantum": UpgradeSpec("future_quantum", "微观量子挖掘", 30, {"credits": 90000, "gold": 90, "coreshard": 8}, 1.55, 0.75, effect="每级 +1.50 推进效率"),
        "relativity": UpgradeSpec("relativity", "相对论效应", 10, {"credits": 2.0e6, "coreshard": 40}, 1.72, 0.90, effect="重生后 60 秒速度 ×100"),
        "planetary_power": UpgradeSpec("planetary_power", "行星之力", 100, {"cores": 1}, 1.0, local=False, effect="每级 +1.00 全局速度，首级使速度翻倍"),
        "stage_skip": UpgradeSpec("stage_skip", "阶段跳过", 20, {"cores": 2}, 1.0, local=False, effect="每级减少 8% 星球深度需求"),
        "core_survey": UpgradeSpec("core_survey", "核心勘探技术", 50, {"cores": 3}, 1.0, local=False, effect="每级额外获得 1 个核心"),
        "entanglement": UpgradeSpec("entanglement", "宏观量子纠缠", 40, {"cores": 5}, 1.0, local=False, effect="每级让爆星时额外摧毁 25% 星球"),
        "auto_all": UpgradeSpec("auto_all", "全自动采购", 1, {"cores": 8}, 1.0, local=False, effect="所有本地升级都可自动购买"),
        "core_quantum": UpgradeSpec("core_quantum", "核心量子加速", 50, {"cores": 8}, 1.0, local=False, effect="每级 +1.50 全局速度"),
    }


SPECS = _specs()


@dataclass
class SimulationState:
    target_depth: float = 1_000_000.0
    seed: int = 42
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
    daily_upgrade_messages: int = 0
    total_upgrade_messages: int = 0
    burst_seconds: int = 0
    fractional_planets: float = 0.0
    rng: random.Random = field(init=False, repr=False)
    events: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        for key in LOCAL_KEYS:
            self.local_levels.setdefault(key, 0)
        for key in CORE_KEYS:
            self.permanent_levels.setdefault(key, 0)

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
        return self.progress >= spec.unlock or key in self.active_auto_keys

    def _batch_cost(self, key: str, amount: int) -> dict[str, float]:
        level = self.local_levels[key] if SPECS[key].local else self.permanent_levels[key]
        total: dict[str, float] = {}
        for offset in range(amount):
            for resource, cost in self._cost_for(key, level + offset).items():
                total[resource] = total.get(resource, 0.0) + cost
        return total

    def upgrade_command(self, orders: Iterable[tuple[str, int]], *, automatic: bool = False) -> tuple[bool, str]:
        """一次消息可买多个项目；手动消息每天最多三条。"""
        if not automatic and self.daily_upgrade_messages >= 3:
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
            levels[key] += amount
            if spec.local and levels[key] >= 3:
                self.auto_unlocked.add(key)
            if key in CORE_KEYS and key == "auto_all":
                self.events.append("核心科技：全自动采购已启用")
        if not automatic:
            self.daily_upgrade_messages += 1
            self.total_upgrade_messages += 1
        return True, "、".join(f"{SPECS[key].name}+{amount}" for key, amount in normalized)

    def auto_purchase(self) -> int:
        bought = 0
        for key in LOCAL_KEYS:
            if key not in self.active_auto_keys or not self._available(key):
                continue
            # 每个固定步只推进有限级数，防止自动化在一次结算中吞掉整条曲线。
            for _ in range(4):
                ok, _ = self.upgrade_command([(key, 1)], automatic=True)
                if not ok:
                    break
                bought += 1
        return bought

    def _speed_multiplier(self) -> float:
        local = self.local_levels
        base = 1.0 + 0.35 * local["pickaxe"]
        base += 0.25 * local["survey"]
        base += 0.30 * local["industrial_blaster"]
        base += 0.55 * local["electric_pickaxe"]
        base += 0.90 * local["modern_drill"]
        base += 1.50 * local["future_quantum"]
        base *= 1.0 + local["cart"] * 0.04 + local["steam_cart"] * 0.05 + local["electric_cart"] * 0.08
        workers = 1 + min(12, local["cat"])
        base *= workers
        permanent = 1.0 + self.permanent_levels["planetary_power"]
        permanent += 1.5 * self.permanent_levels["core_quantum"]
        if self.burst_seconds > 0:
            permanent *= 100.0
        return max(1.0, base * permanent)

    def _yield_ores(self) -> dict[str, float]:
        p = self.progress
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
        total = 10.0 * self._speed_multiplier() * (1 + 0.20 * self.local_levels["cart"] + 0.28 * self.local_levels["steam_cart"] + 0.50 * self.local_levels["electric_cart"])
        noise = max(0.70, min(1.30, self.rng.gauss(1.0, 0.08)))
        total *= noise
        return {name: total * weight for name, weight in zip(ORE_NAMES, weights)}

    def mine_minute(self, minutes: int = 1) -> list[str]:
        events: list[str] = []
        for _ in range(minutes):
            if self.depth >= self.target_depth:
                events.append(self.prestige())
            if self.burst_seconds > 0:
                self.burst_seconds = max(0, self.burst_seconds - 60)
            depth_gain = 8.0 * self._speed_multiplier()
            depth_gain *= max(0.70, min(1.30, self.rng.gauss(1.0, 0.025)))
            remaining = self.target_depth - self.depth
            self.depth += min(remaining, depth_gain)
            ores = self._yield_ores()
            for name, amount in ores.items():
                key = {"锡矿": "tin", "铜矿": "copper", "紫晶": "quartz", "金猫锭": "gold", "虹核晶": "coreshard"}[name]
                self.resources[key] += amount
            refine = 0.72 + 0.22 * self.local_levels["refinery"]
            self.resources["credits"] += sum(ores[name] * value for name, value in zip(ORE_NAMES, ORE_VALUES)) * refine
            self.auto_purchase()
            self.minute += 1
            if self.depth >= self.target_depth:
                events.append(self.prestige())
        self.events.extend(events)
        return events

    def prestige(self) -> str:
        survey = self.permanent_levels["core_survey"]
        entanglement = self.permanent_levels["entanglement"]
        relativity_active = self.local_levels["relativity"] > 0 or "relativity" in self.auto_unlocked
        gain = 1 + survey
        self.fractional_planets += entanglement * 0.25
        extra = int(self.fractional_planets)
        self.fractional_planets -= extra
        destroyed = 1 + extra
        self.planets = self.planets + LogNumber.from_int(destroyed)
        self.cores = self.cores + LogNumber.from_int(gain)
        self.depth = 0.0
        self.resources = {key: 0.0 for key in self.resources}
        for key in LOCAL_KEYS:
            self.local_levels[key] = 0
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


def _strategy(state: SimulationState) -> None:
    """一个有意保守的每日策略，用来观察曲线而不是寻找最优解。"""
    if state.daily_upgrade_messages >= 3:
        return
    # 重生后的前三条核心投资先建立“下一轮更快”的反馈，再把剩余消息留给本地科技。
    if not state.planets.is_zero:
        core_plans = [
            ("planetary_power", 1, 1),
            ("stage_skip", 1, 2),
            ("core_survey", 1, 3),
            ("entanglement", 1, 5),
            ("auto_all", 1, 8),
            ("core_quantum", 1, 8),
        ]
        for key, amount, minimum in core_plans:
            if state.daily_upgrade_messages >= 3:
                break
            if state.permanent_levels[key] >= SPECS[key].max_level:
                continue
            if state._core_count_as_float() < minimum:
                continue
            ok, _ = state.upgrade_command([(key, amount)])
            if ok and key in {"auto_all", "core_survey"}:
                break
    if state.day <= 2:
        plans = [[("pickaxe", 2), ("cart", 1)], [("refinery", 2), ("survey", 1)], [("cat", 1)]]
    elif state.day <= 7:
        plans = [[("pickaxe", 2), ("refinery", 1)], [("cart", 2), ("survey", 1)], [("cat", 1)]]
    else:
        plans = [
            [("pickaxe", 2), ("cart", 2)],
            [("refinery", 2), ("survey", 2)],
            [("industrial_blaster", 1), ("steam_cart", 1)],
            [("electric_pickaxe", 1), ("electric_cart", 1)],
            [("modern_drill", 1), ("future_quantum", 1)],
            [("relativity", 1)],
        ]
    for plan in plans:
        if state.daily_upgrade_messages >= 3:
            break
        available = [(key, amount) for key, amount in plan if key in SPECS and state._available(key) and state.level(key) + amount <= SPECS[key].max_level]
        if not available:
            continue
        ok, _ = state.upgrade_command(available)
        if not ok and len(available) > 1:
            # 批量购买失败时退回为一项，保留“每条消息可多项”的体验。
            state.upgrade_command([available[0]])


def _development_target(target_log10: int) -> float:
    # 10^308 只用于阶段二外推；阶段一仍用可观察的开发目标跑精确分钟步。
    return 10**target_log10 if target_log10 <= 12 else 1_000_000_000.0


def run_scenario(days: int = 60, seed: int = 42, target_log10: int = 9) -> tuple[SimulationState, list[str]]:
    target = _development_target(target_log10)
    state = SimulationState(target_depth=target, seed=seed)
    log: list[str] = []
    milestone_days = {1, 2, 3, 7, 11, 15, 20, 25, 30, 37, 45, 50, days}
    for day in range(1, days + 1):
        if day > 1:
            state.start_new_day()
        _strategy(state)
        state.mine_minute(1440)
        if day in milestone_days:
            log.append(f"D{day:02d}: {state.summary()}")
        state.events.clear()
    projection = state.project_stage_two(308)
    log.append(
        "阶段二外推：稳定速度 "
        f"×{projection['stable_speed']:.2f}，单星球约 {projection['minutes_per_planet']:.1f} 分钟，"
        f"抵达 10^{projection['target_log10']} 星球约需 10^{projection['log10_minutes_to_target']:.2f} 分钟（对数估算）"
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
                _strategy(state)
                state.mine_minute(1440)
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
    scenario.add_argument("--target-log10", type=int, default=9, help="单星球深度的数量级，支持 308（阶段一仍用开发目标精确跑）")
    scenario.add_argument("--summary-only", action="store_true")
    interactive = subparsers.add_parser("repl", help="进入交互式命令行")
    interactive.add_argument("--seed", type=int, default=42)
    interactive.add_argument("--target-log10", type=int, default=9)
    args = parser.parse_args()
    if args.command == "scenario":
        state, log = run_scenario(args.days, args.seed, args.target_log10)
        if args.summary_only:
            print(state.summary())
        else:
            print("\n\n".join(log))
    else:
        repl(args.target_log10, args.seed)


if __name__ == "__main__":
    main()
