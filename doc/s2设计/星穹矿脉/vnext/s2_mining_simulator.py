"""Shared-data simulator for the S2 Starvault Mine economy."""

from __future__ import annotations

import argparse
import copy
import json
import math
import pathlib
import random
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from s2_voyage import compile_voyage, earned_cores, sample_voyage


MODULE_DIR = pathlib.Path(__file__).resolve().parent
PLUGIN_DIR = MODULE_DIR.parents[3]
GAME_DATA_PATH = PLUGIN_DIR / "web" / "static" / "s2-vnext" / "game_data.json"
IMPLEMENTED_EFFECT_KINDS = {
    "speed_compound", "parallel", "cats", "sharpness", "income", "fragility",
    "extra_depth", "coordination", "crit_chance", "crit_damage", "shift_relay",
    "momentum", "teamwork", "penetration", "resonance",
}
IMPLEMENTED_CORE_EFFECT_KINDS = {
    "speed_strength", "income_strength", "depth_strength",
    "equipment_strength", "line_synergy", "global_speed", "global_linear",
    "local_discount", "completion_depth", "opening_burst",
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
    prestige = data.get("prestige")
    expected_resources = ["credits", "cores"] if prestige else ["credits"]
    if [item["key"] for item in data["resources"]] != expected_resources:
        raise ValueError(f"v3 resources must be {expected_resources}")
    if str(data.get("contentVersion", "")).startswith("prestige-") and not prestige:
        raise ValueError("prestige content requires prestige rules")
    if prestige:
        reward_step = prestige.get("rewardStep")
        galaxy_target = prestige.get("galaxyTargetPlanets")
        if (
            not math.isfinite(float(prestige.get("planetTargetDepth", 0)))
            or float(prestige["planetTargetDepth"]) <= 0
            or type(reward_step) is not int
            or reward_step < 1
            or (
                data.get("contentVersion") in {"prestige-2", "prestige-3"}
                and (
                    type(galaxy_target) is not int
                    or galaxy_target < 1
                    or (
                        type(galaxy_target) is int
                        and earned_cores(galaxy_target, reward_step) > 2**53 - 1
                    )
                )
            )
            or type(prestige.get("historyLimit")) is not int
            or prestige["historyLimit"] < 1
            or not isinstance(prestige.get("upgrades"), list)
            or not prestige["upgrades"]
        ):
            raise ValueError("invalid prestige rules")
        if (
            data.get("contentVersion") == "prestige-3"
            and (
                prestige.get("openingBurstSeconds") != 1
                or not prestige.get("legacyCorePrices")
            )
        ):
            raise ValueError("invalid prestige rules")
        core_keys: set[str] = set()
        for item in prestige["upgrades"]:
            if (
                not isinstance(item.get("key"), str)
                or item["key"] in core_keys
                or item.get("effectKind") not in IMPLEMENTED_CORE_EFFECT_KINDS
                or type(item.get("unlockResets")) is not int
                or item["unlockResets"] < 1
                or type(item.get("maxLevel")) is not int
                or not 1 <= item["maxLevel"] <= 20
                or type(item.get("baseCost")) is not int
                or item["baseCost"] < 1
                or type(item.get("costGrowth")) is not int
                or item["costGrowth"] < 1
                or not math.isfinite(float(item.get("effectPerLevel", 0)))
                or float(item["effectPerLevel"]) <= 0
                or (
                    item["baseCost"]
                    * item["costGrowth"] ** (item["maxLevel"] - 1)
                    > 2**53 - 1
                )
            ):
                raise ValueError("invalid core technology")
            core_keys.add(item["key"])
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
PRESTIGE_CONFIG = GAME_DATA.get("prestige")


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


@dataclass(frozen=True)
class CoreSpec:
    key: str
    name: str
    description: str
    unlock_resets: int
    base_cost: int
    cost_growth: int
    max_level: int
    effect_kind: str
    effect_per_level: float


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


def _core_specs() -> dict[str, CoreSpec]:
    return {
        item["key"]: CoreSpec(
            key=item["key"], name=item["name"], description=item["description"],
            unlock_resets=int(item["unlockResets"]), base_cost=int(item["baseCost"]),
            cost_growth=int(item["costGrowth"]), max_level=int(item["maxLevel"]),
            effect_kind=item["effectKind"],
            effect_per_level=float(item["effectPerLevel"]),
        )
        for item in (PRESTIGE_CONFIG or {}).get("upgrades", [])
    }


SPECS = _specs()
CORE_SPECS = _core_specs()
LOCAL_KEYS = tuple(SPECS)
PRIORITY = tuple(key for key in STRATEGY_CONFIG["priority"] if key in SPECS)
PRIORITY_INDEX = {key: index for index, key in enumerate(PRIORITY)}
KEY_INDEX = {key: index for index, key in enumerate(LOCAL_KEYS)}
SETTLEMENT_MINUTES = int(RULES["settlementMinutes"])
TOTAL_LOCAL_MAX_LEVEL = sum(spec.max_level for spec in SPECS.values())
MAX_SAFE_INTEGER = 2**53 - 1


@dataclass
class SimulationState:
    target_depth: float = float(
        (PRESTIGE_CONFIG or {}).get(
            "planetTargetDepth", RULES["developmentTargetDepth"]
        )
    )
    seed: int = 42
    deterministic: bool = False
    day: int = 1
    minute: float = 0
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
    resets: int = 0
    completed_planets: int = 0
    cores: int = 0
    core_levels: dict[str, int] = field(
        default_factory=lambda: {key: 0 for key in CORE_SPECS}
    )
    planet_complete: bool = False
    planet_started_minute: float = 0
    all_maxed_minute: float | None = None
    auto_depart: bool = True
    planet_history: list[dict[str, int | float | None]] = field(
        default_factory=list
    )
    core_auto_route: Literal[
        "off", "balanced", "speed", "rebuild", "burst"
    ] = "off"
    last_batch_summary: dict[str, int] = field(
        default_factory=lambda: {"planets": 0, "compiled": 0, "events": 0}
    )
    _next_auto_minute: int = field(default=int(RULES["autoPurchaseIntervalMinutes"]), init=False)
    _next_helper_minute: int = field(default=int(RULES["helperIntervalMinutes"]), init=False)
    _voyage: tuple[tuple[object, ...], dict[str, Any]] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _canonical_voyage: tuple[tuple[object, ...], dict[str, Any]] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    @property
    def resources(self) -> dict[str, float]:
        resources = {"credits": self.credits}
        if PRESTIGE_CONFIG:
            resources["cores"] = float(self.cores)
        return resources

    @property
    def progress(self) -> float:
        return min(1.0, self.depth / self.target_depth)

    @property
    def local_keys(self) -> tuple[str, ...]:
        return LOCAL_KEYS

    @property
    def specs(self) -> dict[str, UpgradeSpec]:
        return SPECS

    @property
    def rules(self) -> dict[str, object]:
        return RULES

    @property
    def prestige_config(self) -> dict[str, object]:
        return PRESTIGE_CONFIG or {}

    @property
    def era_by_key(self) -> dict[str, dict[str, object]]:
        return ERA_BY_KEY

    @property
    def era_sequence(self) -> tuple[str, ...]:
        return ERA_SEQUENCE

    def level(self, key: str) -> int:
        return self.levels.get(key, 0)

    def manual_target(self, key: str) -> int:
        return max(0, SPECS[key].manual_target - self.resets)

    def core_effect(self, kind: str) -> float:
        return sum(
            spec.effect_per_level * self.core_levels[spec.key]
            for spec in CORE_SPECS.values()
            if spec.effect_kind == kind
        )

    def prestige_speed(self) -> float:
        return (
            (1 + self.core_effect("global_linear"))
            * 2 ** self.core_effect("global_speed")
        )

    def core_cost(self, key: str) -> int | float:
        spec = CORE_SPECS.get(key)
        if spec is None:
            return math.inf
        return spec.base_cost * spec.cost_growth ** self.core_levels[key]

    def core_available(self, key: str) -> bool:
        spec = CORE_SPECS.get(key)
        return bool(
            spec
            and self.completed_planets >= spec.unlock_resets
            and self.core_levels[key] < spec.max_level
        )

    def purchase_core(self, key: str) -> tuple[bool, str]:
        if not self.core_available(key):
            return False, "locked"
        cost = self.core_cost(key)
        if self.cores < cost:
            return False, "cores"
        self.cores -= int(cost)
        self.core_levels[key] += 1
        self._voyage = None
        return True, ""

    def core_route_specs(self) -> list[CoreSpec]:
        return list(CORE_SPECS.values()) if self.core_auto_route != "off" else []

    def core_route_score(self, spec: CoreSpec) -> float:
        preferences = {
            "speed": {"global_linear", "global_speed", "speed_strength"},
            "rebuild": {
                "income_strength", "local_discount", "equipment_strength",
            },
            "burst": {"opening_burst", "global_speed", "completion_depth"},
        }
        divisor = (
            4
            if (
                self.completed_planets >= 10
                and spec.effect_kind
                in preferences.get(self.core_auto_route, set())
            )
            else 1
        )
        return self.core_cost(spec.key) / divisor

    def auto_purchase_core(self) -> list[str]:
        bought: list[str] = []
        while True:
            candidates = [
                spec
                for spec in self.core_route_specs()
                if self.core_available(spec.key)
            ]
            if not candidates:
                return bought
            spec = min(candidates, key=self.core_route_score)
            if self.core_cost(spec.key) > self.cores:
                return bought
            ok, _ = self.purchase_core(spec.key)
            if not ok:
                return bought
            bought.append(spec.key)

    def set_core_auto_route(
        self,
        route: Literal["off", "balanced", "speed", "rebuild", "burst"],
    ) -> list[str]:
        if route not in {"off", "balanced", "speed", "rebuild", "burst"}:
            raise ValueError("invalid core automation route")
        self.core_auto_route = route
        return self.auto_purchase_core()

    def galaxy_complete(self) -> bool:
        target = (PRESTIGE_CONFIG or {}).get("galaxyTargetPlanets")
        return target is not None and self.completed_planets >= int(target)

    def set_auto_depart(self, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise ValueError("auto departure setting must be boolean")
        self.auto_depart = enabled

    def all_local_maxed(self) -> bool:
        return all(
            spec.status != "active" or self.level(key) == spec.max_level
            for key, spec in SPECS.items()
        )

    def finish_planet(self) -> bool:
        if (
            not PRESTIGE_CONFIG
            or self.planet_complete
            or self.depth < self.target_depth
        ):
            return False
        reward = 1 + self.resets // int(PRESTIGE_CONFIG["rewardStep"])
        self.depth = self.target_depth
        self.planet_complete = True
        self.completed_planets += 1
        self.cores += reward
        self.planet_history.append({
            "planet": self.completed_planets,
            "minutes": self.minute - self.planet_started_minute,
            "completed_minute": self.minute,
            "reward": reward,
            "all_maxed_minute": self.all_maxed_minute,
        })
        self.planet_history = self.planet_history[
            -int(PRESTIGE_CONFIG["historyLimit"]):
        ]
        return True

    def depart_planet(self) -> tuple[bool, str]:
        if self.galaxy_complete():
            return False, "galaxy"
        if not self.planet_complete:
            return False, "unfinished"
        self.resets += 1
        self.planet_complete = False
        self.clear_local_planet()
        return True, ""

    def clear_local_planet(self) -> None:
        self.depth = 0.0
        self.credits = 0.0
        self.levels = {key: 0 for key in LOCAL_KEYS}
        self.manual_levels = {key: 0 for key in LOCAL_KEYS}
        self.auto_unlocked = set()
        self.ever_keys = set()
        self.era_first_days = {}
        self.auto_cursor = 0
        self.last_helper_report = None
        self.planet_started_minute = self.minute
        self.all_maxed_minute = None
        self._voyage = None

    def effect_strength(self, kind: str) -> float:
        if kind == "speed_compound":
            return 1 + self.core_effect("speed_strength")
        if kind == "crit_chance":
            return 1.0
        strength = 1 + self.core_effect("equipment_strength")
        if kind in {"income", "shift_relay"}:
            strength *= 1 + self.core_effect("income_strength")
        if kind in {"extra_depth", "penetration"}:
            strength *= 1 + self.core_effect("depth_strength")
        return strength

    def cost_for(self, key: str, level: int | None = None) -> float:
        spec = SPECS[key]
        current = self.level(key) if level is None else level
        return (
            spec.base_cost
            * spec.cost_growth**current
            / (1 + self.core_effect("local_discount"))
        )

    def era_automation_count(self, era: str) -> int:
        return sum(1 for key in self.auto_unlocked if SPECS[key].era == era)

    def era_unlocked(self, era: str) -> bool:
        if era == ERA_SEQUENCE[0]:
            return True
        definition = ERA_BY_KEY[era]
        previous = ERA_SEQUENCE[ERA_SEQUENCE.index(era) - 1]
        return self.depth >= float(definition["unlockDepth"]) and self.era_automation_count(previous) >= int(definition["previousEraAutomations"])

    def current_era(self) -> str:
        return next(
            (
                era for era in reversed(ERA_SEQUENCE)
                if ERA_BY_KEY[era]["status"] != "reserve" and self.era_unlocked(era)
            ),
            ERA_SEQUENCE[0],
        )

    def available(self, key: str, *, automatic: bool = False) -> bool:
        spec = SPECS.get(key)
        if (
            spec is None
            or self.planet_complete
            or self.level(key) >= spec.max_level
            or spec.status != "active"
        ):
            return False
        target = self.manual_target(key)
        if automatic and target > 0 and key not in self.auto_unlocked:
            return False
        if not automatic and self.manual_levels[key] >= target:
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
            remaining = self.manual_target(key) - self.manual_levels[key]
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
            if self.manual_levels[key] == self.manual_target(key):
                self.auto_unlocked.add(key)
                self.era_first_days.setdefault(SPECS[key].era, self.day)
        if automatic and self.manual_target(key) == 0 and key not in self.auto_unlocked:
            self.auto_unlocked.add(key)
            self.era_first_days.setdefault(SPECS[key].era, self.day)
        if self.all_maxed_minute is None and self.all_local_maxed():
            self.all_maxed_minute = self.minute
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
                totals[kind] = (
                    totals.get(kind, 0.0)
                    + SPECS[key].effect_per_level * level * self.effect_strength(kind)
                )
        return totals

    def multiplier_breakdown(self) -> dict[str, float]:
        effects = self.effect_levels()
        speed = math.prod(
            (
                1
                + SPECS[key].effect_per_level
                * self.effect_strength(SPECS[key].effect_kind)
            ) ** level
            for key, level in self.levels.items()
            if level and SPECS[key].effect_kind == "speed_compound"
        )
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
        local_minute = self.minute - self.planet_started_minute
        teamwork = 1 + effects.get("teamwork", 0) * math.sqrt(max(0.0, local_minute / 1440))
        day_minute = local_minute % 1440
        momentum = 1 + effects.get("momentum", 0) * min(1.0, day_minute / 240)
        auto_count = len(self.auto_unlocked)
        resonance = 1 + effects.get("resonance", 0) * auto_count
        shift_relay = 1 + effects.get("shift_relay", 0) * auto_count
        penetration = 1 + effects.get("penetration", 0) * max(0.0, critical - 1)
        opening_burst = (
            1 + self.core_effect("opening_burst")
            if local_minute
            < float((PRESTIGE_CONFIG or {}).get("openingBurstSeconds", 1)) / 60
            else 1
        )
        completion_depth = (
            1 + self.core_effect("completion_depth")
            if self.all_local_maxed()
            else 1
        )
        return {
            "speed": speed, "parallel": parallel, "cats": cats, "sharpness": sharpness,
            "fragility": fragility, "income": income, "extra_depth": extra_depth,
            "critical": critical, "coordination": coordination, "teamwork": teamwork,
            "momentum": momentum, "resonance": resonance, "shift_relay": shift_relay,
            "penetration": penetration, "prestige": self.prestige_speed(),
            "stellar_relay": 1 + self.core_effect("line_synergy") * auto_count,
            "opening_burst": opening_burst,
            "completion_depth": completion_depth,
        }

    def income_multiplier(self) -> float:
        f = self.multiplier_breakdown()
        return math.prod(
            f[key] for key in (
                "speed", "parallel", "cats", "sharpness", "fragility",
                "critical", "coordination", "teamwork", "momentum",
                "resonance", "income", "shift_relay", "prestige",
                "stellar_relay", "opening_burst",
            )
        )

    def depth_multiplier(self) -> float:
        f = self.multiplier_breakdown()
        return math.prod(
            f[key] for key in (
                "speed", "parallel", "cats", "sharpness", "fragility",
                "critical", "coordination", "teamwork", "momentum",
                "resonance", "extra_depth", "penetration", "prestige",
                "stellar_relay", "opening_burst", "completion_depth",
            )
        )

    def auto_purchase(self) -> list[str]:
        if self.resets > 0:
            bought: list[str] = []
            budget = (
                TOTAL_LOCAL_MAX_LEVEL
                if self.resets >= 3
                else min(
                    TOTAL_LOCAL_MAX_LEVEL,
                    math.ceil(
                        self.prestige_speed()
                        * int(RULES["autoPurchaseBudget"])
                    ),
                )
            )
            for _ in range(budget):
                candidates = sorted(
                    (
                        key for key in LOCAL_KEYS
                        if self.available(key, automatic=True)
                    ),
                    key=lambda key: (self.cost_for(key), key),
                )
                key = next(
                    (
                        candidate for candidate in candidates
                        if (
                            self.credits - self.cost_for(candidate) + 1e-9
                            >= self.reserve_cost()
                        )
                    ),
                    None,
                )
                if key is None:
                    break
                ok, _ = self.purchase(key, automatic=True)
                if not ok:
                    break
                bought.append(key)
            return bought
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

    def voyage_plan(self) -> dict[str, Any]:
        key: tuple[object, ...] = (
            tuple(self.core_levels.items()),
            self.target_depth,
        )
        if self._voyage and self._voyage[0] == key:
            return self._voyage[1]
        fresh = (
            self.depth == 0
            and self.credits == 0
            and all(not self.levels[item] for item in LOCAL_KEYS)
        )
        if (
            fresh
            and self._canonical_voyage
            and self._canonical_voyage[0] == key
        ):
            plan = self._canonical_voyage[1]
        else:
            scratch = copy.deepcopy(self)
            scratch._voyage = None
            scratch._canonical_voyage = None
            scratch.minute = self.minute - self.planet_started_minute
            scratch.planet_started_minute = 0
            scratch.all_maxed_minute = (
                None
                if self.all_maxed_minute is None
                else self.all_maxed_minute - self.planet_started_minute
            )
            plan = compile_voyage(scratch)
            self.last_batch_summary["compiled"] += 1
            self.last_batch_summary["events"] += len(plan["events"])
            if fresh:
                self._canonical_voyage = (key, plan)
        self._voyage = (key, plan)
        return plan

    def sync_voyage_clock(self, minute: float) -> None:
        self.minute = minute
        self.start_new_day()
        auto_interval = int(RULES["autoPurchaseIntervalMinutes"])
        self._next_auto_minute = (
            math.floor(minute / auto_interval) + 1
        ) * auto_interval
        last_midnight = math.floor(minute / 1440) * 1440
        if (
            last_midnight >= self._next_helper_minute
            and last_midnight >= self.planet_started_minute
        ):
            self.last_helper_report = {
                "minute": last_midnight,
                "levels": 0,
                "spent": 0,
                "items": [],
            }
        self._next_helper_minute = last_midnight + 1440

    def apply_voyage_sample(
        self,
        plan: dict[str, Any],
        age: float,
    ) -> None:
        sample = sample_voyage(plan, age)
        before_levels = dict(self.levels)
        before = sum(self.levels.values())
        previous_age = self.minute - self.planet_started_minute
        self.total_auto_levels += int(sample["built"]) - before
        self.depth = min(self.target_depth, float(sample["depth"]))
        self.credits = float(sample["credits"])
        self.levels = dict(sample["levels"])
        self.manual_levels = dict(sample["manual_levels"])
        self.auto_unlocked = set(sample["auto_unlocked"])
        self.ever_keys = set(sample["ever_keys"])
        for era, time in sample["era_ages"].items():
            self.era_first_days[era] = (
                math.floor((self.planet_started_minute + time) / 1440) + 1
            )
        self.all_maxed_minute = (
            None
            if sample["all_maxed_age"] is None
            else self.planet_started_minute + sample["all_maxed_age"]
        )
        for event in plan["events"]:
            if (
                event["age"] >= previous_age
                and event["age"] <= age
                and event["level"] > before_levels[event["key"]]
                and len(self.last_block_events) < 1024
            ):
                self.last_block_events.append(
                    {
                        **event,
                        "minute": self.planet_started_minute + event["age"],
                    }
                )
        self.sync_voyage_clock(self.planet_started_minute + age)

    def planets_until_core_purchase(self, limit: int) -> int:
        specs = [
            spec
            for spec in self.core_route_specs()
            if self.core_levels[spec.key] < spec.max_level
        ]
        if not specs:
            return limit
        for spec in specs:
            if spec.unlock_resets > self.completed_planets:
                limit = min(
                    limit,
                    spec.unlock_resets - self.completed_planets,
                )
        target = min(
            (
                spec
                for spec in specs
                if self.core_available(spec.key)
            ),
            key=self.core_route_score,
            default=None,
        )
        if target is None:
            return limit
        step = int(PRESTIGE_CONFIG["rewardStep"])
        earned = earned_cores(self.completed_planets, step)

        def can_buy(count: int) -> bool:
            future_cores = (
                self.cores
                + earned_cores(self.completed_planets + count, step)
                - earned
            )
            return future_cores >= self.core_cost(target.key)

        if not can_buy(limit):
            return limit
        low = 1
        high = limit
        while low < high:
            middle = (low + high) // 2
            if can_buy(middle):
                high = middle
            else:
                low = middle + 1
        return low

    def settle_voyages(self, plan: dict[str, Any], count: int) -> None:
        first = self.completed_planets
        start = self.minute
        step = int(PRESTIGE_CONFIG["rewardStep"])
        duration = float(plan["duration"])
        finish = start + duration * count
        final_planet = first + count
        self.cores += (
            earned_cores(final_planet, step) - earned_cores(first, step)
        )
        self.total_auto_levels += count * int(plan["end"]["built"])
        history_limit = int(PRESTIGE_CONFIG["historyLimit"])
        for index in range(max(1, count - history_limit + 1), count + 1):
            self.planet_history.append(
                {
                    "planet": first + index,
                    "minutes": duration,
                    "completed_minute": start + index * duration,
                    "reward": 1 + (first + index - 1) // step,
                    "all_maxed_minute": (
                        None
                        if plan["end"]["all_maxed_age"] is None
                        else (
                            start
                            + (index - 1) * duration
                            + plan["end"]["all_maxed_age"]
                        )
                    ),
                }
            )
        self.planet_history = self.planet_history[-history_limit:]
        self.completed_planets = final_planet
        self.sync_voyage_clock(finish)
        parked = not self.auto_depart or self.galaxy_complete()
        self.resets = final_planet - int(parked)
        self.planet_complete = parked
        if parked:
            self.planet_started_minute = start + (count - 1) * duration
            self.levels = dict(plan["end"]["levels"])
            self.manual_levels = dict(plan["end"]["manual_levels"])
            self.depth = self.target_depth
            self.credits = float(plan["end"]["credits"])
            self.auto_unlocked = set(plan["end"]["auto_unlocked"])
            self.ever_keys = set(plan["end"]["ever_keys"])
            self.era_first_days = {
                era: (
                    math.floor((self.planet_started_minute + age) / 1440) + 1
                )
                for era, age in plan["end"]["era_ages"].items()
            }
            self.all_maxed_minute = (
                None
                if plan["end"]["all_maxed_age"] is None
                else self.planet_started_minute
                + plan["end"]["all_maxed_age"]
            )
            midnight = math.floor(finish / 1440) * 1440
            self.last_helper_report = (
                {
                    "minute": midnight,
                    "levels": 0,
                    "spent": 0,
                    "items": [],
                }
                if midnight >= self.planet_started_minute
                else None
            )
        else:
            self.clear_local_planet()
        self.last_batch_summary["planets"] += count
        self.auto_purchase_core()

    def advance_voyages(self, end_minute: float) -> None:
        boundaries = 0
        max_boundaries = sum(
            spec.max_level + 2 for spec in CORE_SPECS.values()
        ) + 8
        while self.minute < end_minute:
            boundaries += 1
            if boundaries > max_boundaries:
                raise ValueError("permanent event budget exceeded")
            if self.planet_complete:
                if (
                    not self.auto_depart
                    or self.resets == 0
                    or self.galaxy_complete()
                ):
                    self.sync_voyage_clock(end_minute)
                    return
                self.depart_planet()
            plan = self.voyage_plan()
            remaining = end_minute - self.minute
            age = self.minute - self.planet_started_minute
            if age == 0 and plan["initial_age"] == 0:
                count = math.floor(remaining / plan["duration"])
                count = min(
                    count,
                    int(PRESTIGE_CONFIG["galaxyTargetPlanets"])
                    - self.completed_planets,
                )
                if not self.auto_depart:
                    count = min(count, 1)
                if count > 0:
                    count = self.planets_until_core_purchase(count)
                    self.settle_voyages(plan, count)
                    continue
            end_age = min(
                float(plan["duration"]),
                end_minute - self.planet_started_minute,
            )
            self.apply_voyage_sample(plan, end_age)
            if end_age >= plan["duration"]:
                self.depth = self.target_depth
                self.finish_planet()
                self.last_batch_summary["planets"] += 1
                self.auto_purchase_core()
                if self.auto_depart and not self.galaxy_complete():
                    self.depart_planet()
            else:
                self.sync_voyage_clock(end_minute)
                return

    def mine_block(
        self,
        minutes: int | float = SETTLEMENT_MINUTES,
    ) -> list[str]:
        end_minute = self.minute + minutes
        if (
            isinstance(minutes, bool)
            or not isinstance(minutes, (int, float))
            or not math.isfinite(minutes)
            or minutes <= 0
            or end_minute > MAX_SAFE_INTEGER
            or end_minute <= self.minute
            or (
                self.resets < 3
                and (
                    type(minutes) is not int
                    or minutes % SETTLEMENT_MINUTES
                    or type(end_minute) is not int
                )
            )
        ):
            raise ValueError(
                "mine_block must use settlement-sized minutes "
                "before full automation"
            )
        auto: list[str] = []
        self.last_block_events = []
        self.last_batch_summary = {"planets": 0, "compiled": 0, "events": 0}
        while self.minute < end_minute:
            if self.resets >= 3:
                self.advance_voyages(end_minute)
                break
            if not self.planet_complete:
                noise = (
                    1.0
                    if self.deterministic
                    else max(
                        0.85,
                        min(
                            1.15,
                            self.rng.gauss(
                                1, float(RULES["randomSigma"])
                            ),
                        ),
                    )
                )
                depth_rate = (
                    float(RULES["baseDepthPerMinute"])
                    * self.depth_multiplier()
                    * noise
                )
                mining_minutes = (
                    max(
                        0.0,
                        min(
                            SETTLEMENT_MINUTES,
                            (self.target_depth - self.depth) / depth_rate,
                        ),
                    )
                    if PRESTIGE_CONFIG
                    else SETTLEMENT_MINUTES
                )
                self.credits += (
                    float(RULES["baseCreditsPerMinute"])
                    * self.income_multiplier()
                    * mining_minutes
                    * noise
                )
                self.depth += depth_rate * mining_minutes
                if PRESTIGE_CONFIG and mining_minutes < SETTLEMENT_MINUTES:
                    self.depth = self.target_depth
            self.minute += SETTLEMENT_MINUTES
            self.start_new_day()
            if self.finish_planet():
                self.auto_purchase_core()
            if self.resets > 0:
                before = dict(self.levels)
                bought = self.auto_purchase()
                auto.extend(bought)
                for key in bought:
                    self.last_block_events.append({
                        "minute": self.minute, "source": "auto", "key": key,
                        "level": before[key] + 1,
                        "cost": self.cost_for(key, before[key]),
                    })
                    before[key] += 1
            while self.minute >= self._next_auto_minute:
                if self.resets == 0:
                    before = dict(self.levels)
                    bought = self.auto_purchase()
                    auto.extend(bought)
                    for key in bought:
                        self.last_block_events.append({
                            "minute": self.minute, "source": "auto", "key": key,
                            "level": before[key] + 1,
                            "cost": self.cost_for(key, before[key]),
                        })
                        before[key] += 1
                self._next_auto_minute += int(RULES["autoPurchaseIntervalMinutes"])
            while self.minute >= self._next_helper_minute:
                report = self.helper_purchase()
                self.last_block_events.extend({
                    "minute": self.minute, "source": "helper", **item
                } for item in report["items"])
                self._next_helper_minute += int(RULES["helperIntervalMinutes"])
            if (
                self.planet_complete
                and self.resets > 0
                and self.auto_depart
                and not self.galaxy_complete()
            ):
                self.depart_planet()
        return auto

    def start_new_day(self) -> None:
        new_day = math.floor(self.minute / 1440) + 1
        if self.day != new_day:
            self.day = new_day
            self.daily_manual_levels = 0
            self.daily_helper_levels = 0

    def summary(self) -> str:
        minute_of_day = math.floor(self.minute % 1440)
        return (
            f"D{self.day} {minute_of_day // 60:02d}:"
            f"{minute_of_day % 60:02d} | "
            f"深度 {self.depth:,.0f} | 矿币 {self.credits:,.0f} | "
            f"今日手动 {self.daily_manual_levels} 级 | 自动科技 {len(self.auto_unlocked)}"
        )


Route = Literal["balanced", "cheapest", "depth", "income"]
CoreRoute = Literal["none", "balanced", "speed", "rebuild", "burst"]


def choose_upgrade(state: SimulationState, route: Route = "balanced") -> str | None:
    affordable = [key for key in state.manual_candidates() if state.cost_for(key) <= state.credits + 1e-9]
    if not affordable:
        return None
    priority = {key: index for index, key in enumerate(PRIORITY)}
    if route == "cheapest":
        return min(affordable, key=lambda key: (state.cost_for(key), priority.get(key, 999)))
    if route in {"depth", "income"}:
        depth_kinds = {"speed_compound", "parallel", "cats", "sharpness", "fragility", "crit_chance", "crit_damage", "coordination", "teamwork", "momentum", "resonance", "extra_depth", "penetration"}
        income_kinds = depth_kinds - {"extra_depth", "penetration"} | {"income", "shift_relay"}
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


def purchase_cores_for_route(
    state: SimulationState,
    route: CoreRoute = "balanced",
) -> list[str]:
    if route == "none":
        return []
    if route not in {"balanced", "speed", "rebuild", "burst"}:
        raise ValueError(f"unknown core route {route}")
    preferences = {
        "speed": {"global_linear", "global_speed", "speed_strength"},
        "rebuild": {
            "income_strength", "local_discount", "equipment_strength",
        },
        "burst": {"opening_burst", "global_speed", "completion_depth"},
    }
    bought: list[str] = []
    while True:
        candidates = [
            spec
            for spec in CORE_SPECS.values()
            if state.core_available(spec.key)
        ]
        if not candidates:
            break
        spec = min(
            candidates,
            key=lambda item: state.core_cost(item.key) / (
                4
                if (
                    state.completed_planets >= 10
                    and item.effect_kind in preferences.get(route, set())
                )
                else 1
            ),
        )
        if state.core_cost(spec.key) > state.cores:
            break
        key = spec.key
        ok, _ = state.purchase_core(key)
        if not ok:
            break
        bought.append(key)
    return bought


def replay_prestige(
    *,
    seed: int = 42,
    profile: Literal["daily", "absent"] = "daily",
    planets: int = 12,
    days: int = 300,
    core_route: CoreRoute = "balanced",
) -> tuple[SimulationState, list[dict[str, object]]]:
    if (
        profile not in {"daily", "absent"}
        or core_route not in {"balanced", "speed", "rebuild", "burst", "none"}
        or type(planets) is not int
        or planets < 1
        or type(days) is not int
        or days < 1
    ):
        raise ValueError("invalid replay options")
    state = SimulationState(seed=seed)
    milestones: list[dict[str, object]] = []
    recorded = 0
    for _ in range(days * 144):
        if state.completed_planets >= planets:
            break
        state.mine_block()
        if state.completed_planets > recorded:
            milestones.append({
                **state.planet_history[-1],
                "resets": state.resets,
                "cores": state.cores,
                "core_levels": dict(state.core_levels),
                "total_manual_levels": state.total_manual_levels,
                "total_manual_commands": state.total_manual_commands,
            })
            recorded = state.completed_planets
        if state.minute % 1440 == 1200:
            if profile == "daily":
                strategy_visit(state)
            if (
                core_route != "none"
                and state.core_auto_route == "off"
                and state.completed_planets > 0
            ):
                state.set_core_auto_route(core_route)
            if state.planet_complete and state.resets == 0:
                state.depart_planet()
    return state, milestones


def main() -> None:
    parser = argparse.ArgumentParser(description="S2 星穹矿脉共享数据模拟器")
    parser.add_argument("--days", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--profile", choices=("daily", "absent"), default="daily"
    )
    parser.add_argument(
        "--planets",
        type=int,
        default=12,
        help="在 --days 上限内完成的星球数量",
    )
    parser.add_argument(
        "--core-route",
        choices=("balanced", "speed", "rebuild", "burst", "none"),
        default="balanced",
    )
    args = parser.parse_args()
    if args.days <= 0:
        parser.error("--days must be positive")
    if args.planets <= 0:
        parser.error("--planets must be positive")
    state, milestones = replay_prestige(
        seed=args.seed,
        profile=args.profile,
        planets=args.planets,
        days=args.days,
        core_route=args.core_route,
    )
    for milestone in milestones:
        print(
            f"星球 {milestone['planet']} | "
            f"完成分钟 {milestone['completed_minute']} | "
            f"耗时 {milestone['minutes']} | "
            f"奖励 {milestone['reward']} 核心"
        )
    if state.completed_planets < args.planets:
        print(
            f"未在 {args.days} 天上限内完成 {args.planets} 颗星球；"
            f"当前 {state.completed_planets} 颗"
        )
    print(
        f"最终分钟 {state.minute} | 星球 {state.completed_planets} | "
        f"核心 {state.cores} | 重置 {state.resets} | "
        f"速度 {state.prestige_speed():g}"
    )


if __name__ == "__main__":
    main()
