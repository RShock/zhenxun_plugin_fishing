"""白商资格计算，供命令、QQ 背包和网页端共同使用。"""

from dataclasses import dataclass

from ..config import DAILY_GIFT_LIMIT
from ..models import FishingExchangeRecord, FishingUser

WHITE_MARKET_LIMIT_MESSAGE = "今日白商次数已用完"


@dataclass(frozen=True)
class WhiteMarketTarget:
    numeric_id: str
    fish_name: str
    rarity: str
    location_id: str
    location_name: str

    def as_dict(self) -> dict:
        return {
            "numeric_id": self.numeric_id,
            "fish_name": self.fish_name,
            "rarity": self.rarity,
            "location_id": self.location_id,
            "location_name": self.location_name,
        }


@dataclass(frozen=True)
class WhiteMarketPayment:
    numeric_id: str
    fish_name: str
    rarity: str
    location_id: str
    location_name: str
    locked: bool
    targets: tuple[WhiteMarketTarget, ...]

    def as_dict(self) -> dict:
        return {
            "numeric_id": self.numeric_id,
            "fish_name": self.fish_name,
            "rarity": self.rarity,
            "location_id": self.location_id,
            "location_name": self.location_name,
            "locked": self.locked,
            "targets": [target.as_dict() for target in self.targets],
        }


@dataclass(frozen=True)
class WhiteMarketEligibility:
    used_count: int
    limit: int
    payments: tuple[WhiteMarketPayment, ...]

    @property
    def exhausted(self) -> bool:
        return self.used_count >= self.limit

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used_count)

    def as_dict(self) -> dict:
        return {
            "used_count": self.used_count,
            "limit": self.limit,
            "remaining": self.remaining,
            "exhausted": self.exhausted,
            "message": WHITE_MARKET_LIMIT_MESSAGE if self.exhausted else "",
            "payments": [payment.as_dict() for payment in self.payments],
        }


async def get_white_market_eligibility(user_id: str) -> WhiteMarketEligibility:
    """返回当前背包中每条可支付鱼及其可获得目标。

    白商记录的 source 是可获得鱼；支付鱼只需与记录 target 同地图、同稀有度。
    已解锁图鉴的获得鱼继续沿用白商列表规则隐藏。
    """
    # 延迟导入避免交换模块调用资格服务时形成模块级循环依赖。
    from ..backpack.black_market import find_fish_target

    used_count = await FishingUser.get_gift_count(user_id)
    records = await FishingExchangeRecord.list_active_records()
    user_fish = await FishingUser.get_user_fish(user_id)

    targets_by_requirement: dict[tuple[str, str], dict[str, WhiteMarketTarget]] = {}
    collected_cache: dict[tuple[str, str], bool] = {}
    for record in records:
        collected_key = (record.source_name, record.source_rarity)
        if collected_key not in collected_cache:
            collected_cache[collected_key] = await FishingUser.is_collected(
                user_id, record.source_name, record.source_rarity
            )
        if collected_cache[collected_key]:
            continue
        requirement = (record.target_location_id, record.target_rarity)
        target = WhiteMarketTarget(
            numeric_id=record.source_numeric_id,
            fish_name=record.source_name,
            rarity=record.source_rarity,
            location_id=record.source_location_id,
            location_name=record.source_location_name,
        )
        targets_by_requirement.setdefault(requirement, {})[target.numeric_id] = target

    payments: list[WhiteMarketPayment] = []
    for fish in user_fish:
        if int(fish.get("count", 0) or 0) < 1:
            continue
        fish_target = find_fish_target(fish["fish_name"], fish["rarity"])
        if not fish_target:
            continue
        targets = targets_by_requirement.get(
            (fish_target.location_id, fish_target.rarity), {}
        )
        if not targets:
            continue
        payments.append(
            WhiteMarketPayment(
                numeric_id=str(fish["numeric_id"]),
                fish_name=fish["fish_name"],
                rarity=fish["rarity"],
                location_id=fish_target.location_id,
                location_name=fish_target.location_name,
                locked=bool(fish.get("locked", False)),
                targets=tuple(targets.values()),
            )
        )

    return WhiteMarketEligibility(
        used_count=used_count,
        limit=DAILY_GIFT_LIMIT,
        payments=tuple(payments),
    )


async def get_white_market_payment(
    user_id: str, payment_numeric_id: str
) -> WhiteMarketPayment | None:
    eligibility = await get_white_market_eligibility(user_id)
    return next(
        (
            payment
            for payment in eligibility.payments
            if payment.numeric_id == str(payment_numeric_id)
        ),
        None,
    )
