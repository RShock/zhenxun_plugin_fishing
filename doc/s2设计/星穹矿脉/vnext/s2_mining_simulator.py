"""Shared-data simulator for the S2 Starvault Mine economy."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
from dataclasses import dataclass, field
from typing import Iterable, Literal


MODULE_DIR = pathlib.Path(__file__).resolve().parent
PLUGIN_DIR = MODULE_DIR.parents[3]
GAME_DATA_PATH = PLUGIN_DIR / "web" / "static" / "s2-vnext" / "game_data.json"
IMPLEMENTED_EFFECT_KINDS = {
    "speed_compound", "parallel", "cats", "sharpness", "income", "fragility",
    "extra_depth", "coordination", "crit_chance", "crit_damage", "shift_relay",
    "momentum", "teamwork", "penetration", "resonance", "pressure", "network",
    "heat", "diversity", "cascade", "precision", "compression", "lens",
}


def validate_game_data(data: dict[str, object]) -> dict[str, object]:
    required = {"schemaVersion", "gameVersion", "rules", "resources", "eras", "multiplierRegions", "upgrades", "strategy"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"game_data.json missing {sorted(missing)}")
    if data["schemaVersion"] != 3 or data["gameVersion"] != "s2-vnext-v3-helper-1":
        raise ValueError(f"unsupported schemaVersion {data['schemaVersion']}")
    required_rules = {
        "settlementMinutes", "baseCreditsPerMinute", "baseDepthPerMinute",
        "manualAutomationThreshold", "autoPurchaseIntervalMinutes", "autoPurchaseBudget",
        "autoReserveManualLevels", "randomAlgorithm", "randomSigma",
        "dailyUpgradeAuditMin", "dailyUpgradeAuditMax", "developmentTargetDepth",
        "helperIntervalMinutes", "baseCriticalDamage", "manualBurstWarningLevels",
        "batchCommandMaxLevels",
    }
    missing_rules = required_rules - data["rules"].keys()
    if missing_rules:
        raise ValueError(f"game rules missing {sorted(missing_rules)}")
    if int(data["strategy"].get("opportunityCheckIntervalMinutes", 0)) <= 0:
        raise ValueError("strategy opportunityCheckIntervalMinutes must be positive")
    if int(data["rules"]["helperIntervalMinutes"]) != 1440:
        raise ValueError("helperIntervalMinutes must be 1440")
    if int(data["rules"]["batchCommandMaxLevels"]) <= 0:
        raise ValueError("batchCommandMaxLevels must be positive")
    for profile, minutes in (("daily", [1200]), ("absent", [])):
        if data["strategy"]["profiles"].get(profile, {}).get("checkMinutes") != minutes:
            raise ValueError(f"{profile} profile must use {minutes}")
    if data["rules"]["randomAlgorithm"] != "python-mt19937-v1":
        raise ValueError("unsupported random algorithm")
    if [item["key"] for item in data["resources"]] != ["credits"]:
        raise ValueError("v3 must use credits as its only resource")
    eras = {item["key"] for item in data["eras"]}
    regions = {item["key"] for item in data["multiplierRegions"]}
    keys: set[str] = set()
    for item in data["upgrades"]:
        if item["key"] in keys:
            raise ValueError(f"duplicate upgrade {item['key']}")
        keys.add(item["key"])
        if item["era"] not in eras or item["region"] not in regions:
            raise ValueError(f"invalid era/region for {item['key']}")
        if item["manualTarget"] != data["rules"]["manualAutomationThreshold"]:
            raise ValueError(f"{item['key']} has a different automation threshold")
        if item["status"] == "active" and item["effectKind"] not in IMPLEMENTED_EFFECT_KINDS:
            raise ValueError(f"{item['key']} has unsupported active effect {item['effectKind']}")
    for item in data["upgrades"]:
        unknown = set(item["prerequisites"]) - keys
        if unknown:
            raise ValueError(f"{item['key']} has unknown prerequisites {sorted(unknown)}")
    return data


def load_game_data(path: pathlib.Path = GAME_DATA_PATH) -> dict[str, object]:
    return validate_game_data(json.loads(path.read_text(encoding="utf-8")))


GAME_DATA = load_game_data()
RULES = GAME_DATA["rules"]
ERA_DEFINITIONS = tuple(GAME_DATA["eras"])
ERA_BY_KEY = {item["key"]: item for item in ERA_DEFINITIONS}
ERA_SEQUENCE = tuple(item["key"] for item in ERA_DEFINITIONS)
ERA_LABELS = {item["key"]: item["name"] for item in ERA_DEFINITIONS}
STRATEGY_CONFIG = GAME_DATA["strategy"]


@dataclass(frozen=True)
class UpgradeSpec:
    key: str
    name: str
    era: str
    region: str
    description: str
    effect_kind: str
    effect_per_level: float
    max_level: int
    base_cost: float
    cost_growth: float
    unlock_depth: float
    prerequisites: tuple[str, ...]
    manual_target: int
    status: str


def _specs() -> dict[str, UpgradeSpec]:
    return {
        item["key"]: UpgradeSpec(
            key=item["key"], name=item["name"], era=item["era"], region=item["region"],
            description=item["description"], effect_kind=item["effectKind"],
            effect_per_level=float(item["effectPerLevel"]), max_level=int(item["maxLevel"]),
            base_cost=float(item["baseCost"]), cost_growth=float(item["costGrowth"]),
            unlock_depth=float(item["unlockDepth"]), prerequisites=tuple(item["prerequisites"]),
            manual_target=int(item["manualTarget"]), status=item["status"],
        )
        for item in GAME_DATA["upgrades"]
    }


SPECS = _specs()
LOCAL_KEYS = tuple(SPECS)
PRIORITY = tuple(key for key in STRATEGY_CONFIG["priority"] if key in SPECS)
PRIORITY_INDEX = {key: index for index, key in enumerate(PRIORITY)}
KEY_INDEX = {key: index for index, key in enumerate(LOCAL_KEYS)}
SETTLEMENT_MINUTES = int(RULES["settlementMinutes"])


@dataclass
class SimulationState:
    target_depth: float = float(RULES["developmentTargetDepth"])
    seed: int = 42
    deterministic: bool = False
    day: int = 1
    minute: int = 0
    depth: float = 0.0
    credits: float = 0.0
    levels: dict[str, int] = field(default_factory=lambda: {key: 0 for key in LOCAL_KEYS})
    manual_levels: dict[str, int] = field(default_factory=lambda: {key: 0 for key in LOCAL_KEYS})
    auto_unlocked: set[str] = field(default_factory=set)
    ever_keys: set[str] = field(default_factory=set)
    daily_manual_levels: int = 0
    max_daily_manual_levels: int = 0
    total_manual_levels: int = 0
    daily_helper_levels: int = 0
    total_helper_levels: int = 0
    total_manual_commands: int = 0
    total_auto_levels: int = 0
    helper_enabled: bool = True
    last_helper_report: dict[str, object] | None = None
    last_block_events: list[dict[str, object]] = field(default_factory=list)
    era_first_days: dict[str, int] = field(default_factory=dict)
    auto_cursor: int = 0
    _next_auto_minute: int = field(default=int(RULES["autoPurchaseIntervalMinutes"]), init=False)
    _next_helper_minute: int = field(default=int(RULES["helperIntervalMinutes"]), init=False)
    rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    @property
    def resources(self) -> dict[str, float]:
        return {"credits": self.credits}

    @property
    def progress(self) -> float:
        return min(1.0, self.depth / self.target_depth)

    def level(self, key: str) -> int:
        return self.levels.get(key, 0)

    def cost_for(self, key: str, level: int | None = None) -> float:
        spec = SPECS[key]
        current = self.level(key) if level is None else level
        return spec.base_cost * spec.cost_growth**current

    def era_automation_count(self, era: str) -> int:
        return sum(1 for key in self.auto_unlocked if SPECS[key].era == era)

    def era_unlocked(self, era: str) -> bool:
        if era == ERA_SEQUENCE[0]:
            return True
        definition = ERA_BY_KEY[era]
        previous = ERA_SEQUENCE[ERA_SEQUENCE.index(era) - 1]
        return self.depth >= float(definition["unlockDepth"]) and self.era_automation_count(previous) >= int(definition["previousEraAutomations"])

    def current_era(self) -> str:
        return next((era for era in reversed(ERA_SEQUENCE) if self.era_unlocked(era)), ERA_SEQUENCE[0])

    def available(self, key: str, *, automatic: bool = False) -> bool:
        spec = SPECS.get(key)
        if spec is None or self.level(key) >= spec.max_level or spec.status != "active":
            return False
        if automatic and key not in self.auto_unlocked:
            return False
        if not automatic and self.manual_levels[key] >= spec.manual_target:
            return False
        return (
            self.era_unlocked(spec.era)
            and self.depth >= spec.unlock_depth
            and all(self.level(required) >= 1 for required in spec.prerequisites)
        )

    def manual_candidates(self) -> list[str]:
        return [key for key in LOCAL_KEYS if self.available(key)]

    def reserve_cost(self) -> float:
        # Protect the cheapest real sequence of the next three manual levels,
        # including the rising second/third cost of the same technology.
        costs: list[float] = []
        for key in self.manual_candidates():
            spec = SPECS[key]
            remaining = spec.manual_target - self.manual_levels[key]
            costs.extend(self.cost_for(key, self.level(key) + offset) for offset in range(remaining))
        count = int(RULES["autoReserveManualLevels"])
        costs.sort()
        if not costs:
            return 0.0
        while len(costs) < count:
            costs.append(costs[-1])
        return sum(costs[:count])

    def purchase(self, key: str, *, automatic: bool = False, helper: bool = False) -> tuple[bool, str]:
        if automatic and helper:
            return False, "source"
        if not self.available(key, automatic=automatic):
            return False, "locked"
        cost = self.cost_for(key)
        if self.credits + 1e-9 < cost:
            return False, "credits"
        if automatic and self.credits - cost + 1e-9 < self.reserve_cost():
            return False, "reserve"
        self.credits = max(0.0, self.credits - cost)
        self.levels[key] += 1
        self.ever_keys.add(key)
        if automatic:
            self.total_auto_levels += 1
        else:
            self.manual_levels[key] += 1
            if helper:
                self.daily_helper_levels += 1
                self.total_helper_levels += 1
            else:
                self.daily_manual_levels += 1
                self.total_manual_levels += 1
                self.max_daily_manual_levels = max(self.max_daily_manual_levels, self.daily_manual_levels)
            if self.manual_levels[key] == SPECS[key].manual_target:
                self.auto_unlocked.add(key)
                self.era_first_days.setdefault(SPECS[key].era, self.day)
        return True, ""

    def upgrade_command(self, orders: Iterable[tuple[str, int]], *, automatic: bool = False) -> tuple[bool, str]:
        normalized = list(orders)
        if (
            not normalized
            or any(
                not isinstance(order, (tuple, list)) or len(order) != 2
                or not isinstance(order[0], str) or order[0] not in SPECS
                or type(order[1]) is not int or order[1] <= 0
                for order in normalized
            )
            or sum(amount for _, amount in normalized) > int(RULES["batchCommandMaxLevels"])
        ):
            return False, "invalid"
        purchased = False
        for key, amount in normalized:
            for _ in range(amount):
                ok, reason = self.purchase(key, automatic=automatic)
                if not ok:
                    if purchased and not automatic:
                        self.total_manual_commands += 1
                    return purchased, reason
                purchased = True
        if purchased and not automatic:
            self.total_manual_commands += 1
        return purchased, ""

    def set_helper_enabled(self, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise ValueError("helper setting must be boolean")
        self.helper_enabled = enabled

    def effect_levels(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for key, level in self.levels.items():
            if level:
                kind = SPECS[key].effect_kind
                totals[kind] = totals.get(kind, 0.0) + SPECS[key].effect_per_level * level
        return totals

    def multiplier_breakdown(self) -> dict[str, float]:
        effects = self.effect_levels()
        speed = math.prod((1 + SPECS[key].effect_per_level) ** level for key, level in self.levels.items() if level and SPECS[key].effect_kind == "speed_compound")
        parallel = 1 + effects.get("parallel", 0)
        cats = 1 + effects.get("cats", 0)
        sharpness = 1 + effects.get("sharpness", 0)
        fragility = 1 + effects.get("fragility", 0)
        income = 1 + effects.get("income", 0)
        extra_depth = 1 + effects.get("extra_depth", 0)
        crit_chance = min(0.65, effects.get("crit_chance", 0))
        crit_damage = float(RULES["baseCriticalDamage"]) + effects.get("crit_damage", 0)
        critical = 1 + crit_chance * crit_damage
        cat_levels = sum(level for key, level in self.levels.items() if SPECS[key].effect_kind == "cats")
        coordination = 1 + effects.get("coordination", 0) * cat_levels
        teamwork = 1 + effects.get("teamwork", 0) * math.sqrt(max(0.0, self.minute / 1440))
        day_minute = self.minute % 1440
        momentum = 1 + effects.get("momentum", 0) * min(1.0, day_minute / 240)
        auto_count = len(self.auto_unlocked)
        resonance = 1 + effects.get("resonance", 0) * auto_count
        shift_relay = 1 + effects.get("shift_relay", 0) * auto_count
        penetration = 1 + effects.get("penetration", 0) * max(0.0, critical - 1)
        pressure = 1 + effects.get("pressure", 0) * math.log10(1 + self.depth) / 10
        active_regions = len({SPECS[key].region for key, level in self.levels.items() if level})
        diversity = 1 + effects.get("diversity", 0) * active_regions
        network = 1 + effects.get("network", 0) * math.sqrt(parallel * cats)
        heat = 1 + effects.get("heat", 0) * (momentum + math.log10(speed))
        cascade = math.prod(
            1 + effects.get("cascade", 0)
            * sum(key in self.auto_unlocked for key in active_specs) / len(active_specs)
            for era in ERA_SEQUENCE
            if (active_specs := [
                key for key in LOCAL_KEYS
                if SPECS[key].era == era and SPECS[key].status == "active"
            ])
        )
        precision = (
            1 + effects.get("precision", 0) * fragility * critical
            * (1 + max(0.0, effects.get("crit_chance", 0) - 0.65))
        )
        compression = 1 + effects.get("compression", 0) * math.sqrt(penetration * pressure)
        lens = 1 + effects.get("lens", 0) * math.log10(1 + self.depth) / 10 * compression
        return {
            "speed": speed, "parallel": parallel, "cats": cats, "sharpness": sharpness,
            "fragility": fragility, "income": income, "extra_depth": extra_depth,
            "critical": critical, "coordination": coordination, "teamwork": teamwork,
            "momentum": momentum, "resonance": resonance, "shift_relay": shift_relay,
            "penetration": penetration, "pressure": pressure, "diversity": diversity,
            "network": network, "heat": heat, "cascade": cascade,
            "precision": precision, "compression": compression, "lens": lens,
        }

    def income_multiplier(self) -> float:
        f = self.multiplier_breakdown()
        return math.prod(f[key] for key in ("speed", "parallel", "cats", "sharpness", "fragility", "critical", "coordination", "teamwork", "momentum", "resonance", "income", "shift_relay", "diversity", "network", "heat", "cascade", "precision"))

    def depth_multiplier(self) -> float:
        f = self.multiplier_breakdown()
        return math.prod(f[key] for key in ("speed", "parallel", "cats", "sharpness", "fragility", "critical", "coordination", "teamwork", "momentum", "resonance", "extra_depth", "penetration", "pressure", "network", "cascade", "precision", "compression", "lens"))

    def auto_purchase(self) -> list[str]:
        active = sorted(self.auto_unlocked)
        if not active:
            return []
        budget = min(int(RULES["autoPurchaseBudget"]), len(active))
        start = self.auto_cursor % len(active)
        ordered = active[start:] + active[:start]
        self.auto_cursor = (start + budget) % len(active)
        bought: list[str] = []
        for key in ordered:
            if len(bought) >= budget:
                break
            ok, _ = self.purchase(key, automatic=True)
            if ok:
                bought.append(key)
        return bought

    def helper_purchase(self) -> dict[str, object]:
        items: list[dict[str, object]] = []
        spent = 0.0
        if self.helper_enabled:
            while True:
                affordable = [
                    key for key in self.manual_candidates()
                    if self.cost_for(key) <= self.credits + 1e-9
                ]
                if not affordable:
                    break
                key = min(affordable, key=lambda candidate: (
                    self.cost_for(candidate), PRIORITY_INDEX.get(candidate, len(PRIORITY)),
                    KEY_INDEX[candidate]
                ))
                cost = self.cost_for(key)
                ok, _ = self.purchase(key, helper=True)
                if not ok:
                    break
                items.append({"key": key, "level": self.level(key), "cost": cost})
                spent += cost
        self.last_helper_report = {
            "minute": self.minute, "levels": len(items), "spent": spent, "items": items
        }
        return self.last_helper_report

    def mine_block(self, minutes: int = SETTLEMENT_MINUTES) -> list[str]:
        if minutes <= 0 or minutes % SETTLEMENT_MINUTES:
            raise ValueError("mine_block must use settlement-sized minutes")
        auto: list[str] = []
        self.last_block_events = []
        for _ in range(minutes // SETTLEMENT_MINUTES):
            noise = 1.0 if self.deterministic else max(0.85, min(1.15, self.rng.gauss(1, float(RULES["randomSigma"]))))
            self.credits += float(RULES["baseCreditsPerMinute"]) * self.income_multiplier() * SETTLEMENT_MINUTES * noise
            self.depth += float(RULES["baseDepthPerMinute"]) * self.depth_multiplier() * SETTLEMENT_MINUTES * noise
            self.minute += SETTLEMENT_MINUTES
            self.start_new_day()
            while self.minute >= self._next_auto_minute:
                before = dict(self.levels)
                bought = self.auto_purchase()
                auto.extend(bought)
                for key in bought:
                    self.last_block_events.append({
                        "minute": self.minute, "source": "auto", "key": key,
                        "level": before[key] + 1, "cost": self.cost_for(key, before[key])
                    })
                    before[key] += 1
                self._next_auto_minute += int(RULES["autoPurchaseIntervalMinutes"])
            while self.minute >= self._next_helper_minute:
                report = self.helper_purchase()
                self.last_block_events.extend({
                    "minute": self.minute, "source": "helper", **item
                } for item in report["items"])
                self._next_helper_minute += int(RULES["helperIntervalMinutes"])
        return auto

    def start_new_day(self) -> None:
        new_day = self.minute // 1440 + 1
        if self.day != new_day:
            self.day = new_day
            self.daily_manual_levels = 0
            self.daily_helper_levels = 0

    def summary(self) -> str:
        return (
            f"D{self.day} {self.minute % 1440 // 60:02d}:{self.minute % 60:02d} | "
            f"深度 {self.depth:,.0f} | 矿币 {self.credits:,.0f} | "
            f"今日手动 {self.daily_manual_levels} 级 | 自动科技 {len(self.auto_unlocked)}"
        )


Route = Literal["balanced", "cheapest", "depth", "income"]


def choose_upgrade(state: SimulationState, route: Route = "balanced") -> str | None:
    affordable = [key for key in state.manual_candidates() if state.cost_for(key) <= state.credits + 1e-9]
    if not affordable:
        return None
    priority = {key: index for index, key in enumerate(PRIORITY)}
    if route == "cheapest":
        return min(affordable, key=lambda key: (state.cost_for(key), priority.get(key, 999)))
    if route in {"depth", "income"}:
        depth_kinds = {"speed_compound", "parallel", "cats", "sharpness", "fragility", "crit_chance", "crit_damage", "coordination", "teamwork", "momentum", "resonance", "extra_depth", "penetration", "pressure", "network", "cascade", "precision", "compression", "lens"}
        income_kinds = depth_kinds - {"extra_depth", "penetration", "pressure", "compression", "lens"} | {"income", "shift_relay", "diversity", "heat"}
        preferred = depth_kinds if route == "depth" else income_kinds
        matching = [key for key in affordable if SPECS[key].effect_kind in preferred]
        if matching:
            affordable = matching
    # Finish a technology's three manual levels before opening another automation line.
    started = [key for key in affordable if state.manual_levels[key] > 0]
    pool = started or affordable
    return min(pool, key=lambda key: (priority.get(key, 999), state.cost_for(key)))


def strategy_step(state: SimulationState, route: Route = "balanced") -> tuple[str, int] | None:
    key = choose_upgrade(state, route)
    if key is None:
        return None
    ok, _ = state.upgrade_command([(key, 1)])
    return (key, 1) if ok else None


def strategy_visit(state: SimulationState, route: Route = "balanced") -> list[tuple[str, int, float]]:
    purchases: list[tuple[str, int, float]] = []
    while (key := choose_upgrade(state, route)) is not None:
        cost = state.cost_for(key)
        choice = strategy_step(state, route)
        if choice is None:
            break
        purchases.append((key, state.level(key), cost))
    return purchases


def main() -> None:
    parser = argparse.ArgumentParser(description="S2 星穹矿脉共享数据模拟器")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--route", choices=STRATEGY_CONFIG["routeVariants"], default="balanced")
    args = parser.parse_args()
    state = SimulationState(seed=args.seed)
    checks = set(STRATEGY_CONFIG["profiles"]["daily"]["checkMinutes"])
    for day in range(1, args.days + 1):
        for minute in range(SETTLEMENT_MINUTES, 1441, SETTLEMENT_MINUTES):
            state.mine_block()
            if minute in checks:
                strategy_visit(state, args.route)
        print(state.summary())


if __name__ == "__main__":
    main()
