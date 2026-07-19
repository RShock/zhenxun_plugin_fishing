from datetime import date, datetime, timedelta


class InMemoryUser:
    def __init__(self, user_id: str, nickname: str = ""):
        self.id: int = 0
        self.user_id = user_id
        self.rod_level = 0
        self.bonus_rod_level = 0
        self.hook_level = 0
        self.bait_id = "0"
        self.preferred_bait_id = "0"
        self.skin_id = "1"
        self.owned_skins = ["1"]
        self.nickname = nickname
        self.display_slots = 3
        self.upgraded_display_count = 0
        self.gold = 0
        self.corn = 0
        self.last_sign_date = None
        self.display_frames = 0
        self.cat_frames = 0
        self.auto_sell = False
        self.auto_sell_rarity = None
        self.auto_lock = False
        self.auto_lock_pattern = ""
        self.frame_pity_counter = 0
        self.cat_frame_pity_counter = 0
        self.utr_pity_counter = 0
        self.black_market_pity_counter = 0
        self.starry_score_accumulated = 0.0
        self.star_frames = 0
        self.starry_frames = 0
        self.s2_ticket_claimed = False
        self.starry_fish = []
        self.starry_exhibition = []
        self.daily_counters = {
            "stop": {"count": 0, "date": None},
            "sell": {"count": 0, "date": None},
            "nest": {"count": 0, "date": None},
            "gift": {"count": 0, "date": None},
            "status": {"count": 0, "date": None},
            "black_market": {"count": 0, "date": None},
        }
        self.backpack = {}
        self.collection = {}
        self.achievements = []
        self.items = {}
        self.displays = {}
        self.fishing_status = None

    @property
    def base_rod_level(self) -> int:
        return max(0, self.rod_level - self.bonus_rod_level)

    def _get_daily_counter(self, counter_type: str):
        info = self.daily_counters.get(counter_type, {"count": 0, "date": None})
        return info.get("count", 0), info.get("date")

    def _set_daily_counter(self, counter_type: str, count: int, date_str: str | None):
        self.daily_counters[counter_type] = {"count": count, "date": date_str}

    async def save(self, update_fields=None):
        pass


class InMemoryExchangeRecord:
    def __init__(self, record_id: int, user_id: str, source, target):
        self.id = record_id
        self.user_id = user_id
        self.source_name = source.name
        self.source_rarity = source.rarity
        self.source_numeric_id = source.numeric_id
        self.source_location_id = source.location_id
        self.source_location_name = source.location_name
        self.source_scene_level = source.scene_level
        self.target_name = target.name
        self.target_rarity = target.rarity
        self.target_numeric_id = target.numeric_id
        self.target_location_id = target.location_id
        self.target_location_name = target.location_name
        self.target_scene_level = target.scene_level
        self.is_active = True
        self.reversed_by_user_id = None

    async def save(self, update_fields=None):
        pass


class InMemoryBuff:
    def __init__(
        self,
        target_type,
        target_id,
        buff_type,
        start_time,
        end_time,
        value=1,
        description="",
        source_user_id=None,
    ):
        self.id: int = 0
        self.target_type = target_type
        self.target_id = target_id
        self.buff_type = buff_type
        self.start_time = start_time
        self.end_time = end_time
        self.value = value
        self.description = description
        self.source_user_id = source_user_id


def _normalize_fish_numeric_id(numeric_id: str | int | None) -> str:
    if numeric_id is None:
        return ""
    numeric_id = str(numeric_id).strip()
    if (
        len(numeric_id) == 4
        and numeric_id.startswith("-1")
        and numeric_id[2:].isdigit()
    ):
        return f"s1{numeric_id[2:]}"
    if (
        len(numeric_id) == 4
        and numeric_id[:2].lower() == "s1"
        and numeric_id[2:].isdigit()
    ):
        return f"s1{numeric_id[2:]}"
    return numeric_id


def _normalize_backpack_numeric_ids(backpack: dict) -> tuple[dict, bool]:
    normalized: dict = {}
    changed = False
    for numeric_id, entry in backpack.items():
        new_id = _normalize_fish_numeric_id(numeric_id)
        changed = changed or new_id != numeric_id
        if new_id in normalized:
            existing = normalized[new_id]
            existing["count"] = existing.get("count", 0) + entry.get("count", 0)
            existing["locked"] = existing.get("locked", False) or entry.get(
                "locked", False
            )
        else:
            normalized[new_id] = dict(entry)
    return normalized, changed


def _normalize_collection(collection: dict) -> tuple[dict, bool]:
    normalized: dict = {}
    changed = False
    for key, value in collection.items():
        if isinstance(value, dict):
            fish_name = key
            normalized.setdefault(fish_name, {})
            for rarity, count in value.items():
                normalized[fish_name][rarity] = normalized[fish_name].get(
                    rarity, 0
                ) + int(count or 0)
            continue
        parts = str(key).split("|", 1)
        if len(parts) != 2:
            normalized[key] = value
            continue
        fish_name, rarity = parts
        normalized.setdefault(fish_name, {})
        normalized[fish_name][rarity] = normalized[fish_name].get(rarity, 0) + int(
            value or 0
        )
        changed = True
    return normalized, changed


class MockDB:
    def __init__(self):
        self._users: dict[str, InMemoryUser] = {}
        self._buffs: list[InMemoryBuff] = []
        self._exchange_records: list[InMemoryExchangeRecord] = []
        self._next_id = 1
        self._unlocked_lost_winds: set[tuple[str, str]] = set()

    def _gen_id(self):
        self._next_id += 1
        return self._next_id

    def reset(self):
        self._users.clear()
        self._buffs.clear()
        self._exchange_records.clear()
        self._next_id = 1
        self._unlocked_lost_winds.clear()

    # --- FishingUser ---
    async def user_get_or_create(self, user_id: str, nickname: str = ""):
        if user_id in self._users:
            u = self._users[user_id]
            if nickname and not u.nickname:
                u.nickname = nickname
            return u, False
        u = InMemoryUser(user_id, nickname)
        u.id = self._gen_id()
        self._users[user_id] = u
        return u, True

    async def user_get(self, user_id: str):
        u, _ = await self.user_get_or_create(user_id)
        return u

    async def user_add_gold(self, user_id: str, amount: int):
        u = await self.user_get(user_id)
        u.gold += amount

    async def user_reduce_gold(self, user_id: str, amount: int) -> bool:
        u = await self.user_get(user_id)
        if u.gold < amount:
            return False
        u.gold -= amount
        return True

    async def user_add_corn(self, user_id: str, amount: int = 1):
        u = await self.user_get(user_id)
        u.corn += amount

    async def user_reduce_corn(self, user_id: str, amount: int = 1) -> bool:
        u = await self.user_get(user_id)
        if u.corn < amount:
            return False
        u.corn -= amount
        return True

    async def user_check_and_sign(self, user_id: str):
        u = await self.user_get(user_id)
        today = date.today()
        if u.last_sign_date == today:
            return False, 0, 0
        days_missed = 0
        if u.last_sign_date is not None:
            delta = (today - u.last_sign_date).days
            days_missed = max(0, delta - 1)
        u.last_sign_date = today
        u.corn += 1
        return True, u.corn, days_missed

    async def user_increment_stop_count(self, user_id: str):
        u = await self.user_get(user_id)
        today_str = date.today().isoformat()
        info = u.daily_counters.get("stop", {"count": 0, "date": None})
        if info.get("date") != today_str:
            info = {"count": 0, "date": today_str}
        info["count"] += 1
        u.daily_counters["stop"] = info
        return info["count"], info["count"] >= 3

    async def user_get_stop_count(self, user_id: str):
        u = await self.user_get(user_id)
        today_str = date.today().isoformat()
        info = u.daily_counters.get("stop", {"count": 0, "date": None})
        if info.get("date") != today_str:
            return 0
        return info.get("count", 0)

    async def user_increment_sell_count(self, user_id: str):
        u = await self.user_get(user_id)
        today_str = date.today().isoformat()
        info = u.daily_counters.get("sell", {"count": 0, "date": None})
        if info.get("date") != today_str:
            info = {"count": 0, "date": today_str}
        info["count"] += 1
        u.daily_counters["sell"] = info
        return info["count"], info["count"] >= 3

    async def user_get_sell_count(self, user_id: str):
        u = await self.user_get(user_id)
        today_str = date.today().isoformat()
        info = u.daily_counters.get("sell", {"count": 0, "date": None})
        if info.get("date") != today_str:
            return 0
        return info.get("count", 0)

    async def user_add_display_frames(self, user_id: str, count: int = 1):
        u = await self.user_get(user_id)
        u.display_frames += count

    async def user_reduce_display_frames(self, user_id: str, count: int = 1) -> bool:
        u = await self.user_get(user_id)
        if u.display_frames < count:
            return False
        u.display_frames -= count
        return True

    async def user_increment_nest_count(self, user_id: str):
        u = await self.user_get(user_id)
        today_str = date.today().isoformat()
        info = u.daily_counters.get("nest", {"count": 0, "date": None})
        if info.get("date") != today_str:
            info = {"count": 0, "date": today_str}
        info["count"] += 1
        u.daily_counters["nest"] = info
        return info["count"], info["count"] >= 2

    async def user_get_nest_count(self, user_id: str):
        u = await self.user_get(user_id)
        today_str = date.today().isoformat()
        info = u.daily_counters.get("nest", {"count": 0, "date": None})
        if info.get("date") != today_str:
            return 0
        return info.get("count", 0)

    async def user_increment_gift_count(self, user_id: str):
        u = await self.user_get(user_id)
        today_str = date.today().isoformat()
        info = u.daily_counters.get("gift", {"count": 0, "date": None})
        if info.get("date") != today_str:
            info = {"count": 0, "date": today_str}
        info["count"] += 1
        u.daily_counters["gift"] = info
        return info["count"]

    async def user_get_gift_count(self, user_id: str):
        u = await self.user_get(user_id)
        today_str = date.today().isoformat()
        info = u.daily_counters.get("gift", {"count": 0, "date": None})
        if info.get("date") != today_str:
            return 0
        return info.get("count", 0)

    async def user_get_owned_skins(self, user_id: str):
        u = await self.user_get(user_id)
        if not u.owned_skins or not isinstance(u.owned_skins, list):
            return ["1"]
        return u.owned_skins

    async def user_change_skin(self, user_id: str, skin_id: str):
        u = await self.user_get(user_id)
        if not u.owned_skins or skin_id not in u.owned_skins:
            return False, f"你没有皮肤 {skin_id}"
        u.skin_id = skin_id
        return True, f"已更换为皮肤 {skin_id}"

    async def user_add_skin(self, user_id: str, skin_id: str):
        u = await self.user_get(user_id)
        if not u.owned_skins:
            u.owned_skins = ["1"]
        if skin_id not in u.owned_skins:
            u.owned_skins.append(skin_id)

    async def user_reset(self, user_id: str):
        if user_id in self._users:
            del self._users[user_id]

    async def user_clear_all_data(self, user_id: str):
        u = await self.user_get(user_id)
        u.backpack = {}
        u.collection = {}
        u.achievements = []
        u.items = {}
        u.displays = {}
        u.fishing_status = None
        u.daily_counters = {
            "stop": {"count": 0, "date": None},
            "sell": {"count": 0, "date": None},
            "nest": {"count": 0, "date": None},
            "gift": {"count": 0, "date": None},
        }

    # --- FishingUser: Status (fishing_status JSONB) ---
    async def status_start_fishing(self, user_id: str, location_id: str):
        u = await self.user_get(user_id)
        now_iso = datetime.now().isoformat()
        u.fishing_status = {
            "location_id": location_id,
            "start_time": now_iso,
            "last_settle_time": now_iso,
            "fish_caught": [],
            "bait_consumed": 0,
            "frame_pity": u.frame_pity_counter,
            "utr_pity": u.utr_pity_counter,
        }
        return u.fishing_status

    async def status_get(self, user_id: str):
        u = await self.user_get(user_id)
        return u.fishing_status

    async def status_stop_fishing(self, user_id: str):
        u = await self.user_get(user_id)
        status = u.fishing_status
        if status:
            u.fishing_status = None
        return status

    async def status_update_fishing_status(self, user_id: str, status: dict):
        u = await self.user_get(user_id)
        u.fishing_status = status

    async def status_is_fishing(self, user_id: str):
        u = await self.user_get(user_id)
        return u.fishing_status is not None

    async def status_get_location_fishers(self, location_id: str):
        return [
            u.user_id
            for u in self._users.values()
            if u.fishing_status
            and isinstance(u.fishing_status, dict)
            and u.fishing_status.get("location_id") == location_id
        ]

    # --- FishingUser: Backpack (backpack JSONB) ---
    async def backpack_add_fish(self, user_id, fish_name, rarity, numeric_id, count=1):
        u = await self.user_get(user_id)
        if not isinstance(u.backpack, dict):
            u.backpack = {}
        numeric_id = _normalize_fish_numeric_id(numeric_id)
        entry = u.backpack.get(numeric_id)
        if entry:
            entry["count"] = entry.get("count", 0) + count
        else:
            u.backpack[numeric_id] = {
                "fish_name": fish_name,
                "rarity": rarity,
                "count": count,
                "locked": False,
            }

    async def backpack_get_user_fish(self, user_id: str):
        u = await self.user_get(user_id)
        if not isinstance(u.backpack, dict):
            return []
        normalized, changed = _normalize_backpack_numeric_ids(u.backpack)
        if changed:
            u.backpack = normalized
        rarity_order = {"N": 0, "R": 1, "SR": 2, "SSR": 3, "UR": 4, "UTR": 5}
        result = []
        for nid, entry in u.backpack.items():
            result.append(
                {
                    "numeric_id": nid,
                    "fish_name": entry.get("fish_name", ""),
                    "rarity": entry.get("rarity", "N"),
                    "count": entry.get("count", 0),
                    "locked": entry.get("locked", False),
                }
            )
        result.sort(
            key=lambda f: (rarity_order.get(f["rarity"], 0), f["count"]), reverse=True
        )
        return result

    async def backpack_get_fish_by_numeric_id(self, user_id: str, numeric_id: str):
        u = await self.user_get(user_id)
        if not isinstance(u.backpack, dict):
            return None
        normalized_id = _normalize_fish_numeric_id(numeric_id)
        entry = u.backpack.get(normalized_id)
        if not entry:
            return None
        return {
            "numeric_id": normalized_id,
            "fish_name": entry.get("fish_name", ""),
            "rarity": entry.get("rarity", "N"),
            "count": entry.get("count", 0),
            "locked": entry.get("locked", False),
        }

    async def backpack_remove_fish_by_numeric_id(
        self, user_id: str, numeric_id: str, count: int = 1
    ):
        u = await self.user_get(user_id)
        if not isinstance(u.backpack, dict):
            return False
        normalized_id = _normalize_fish_numeric_id(numeric_id)
        entry = u.backpack.get(normalized_id)
        if not entry or entry.get("count", 0) < count:
            return False
        entry["count"] -= count
        if entry["count"] <= 0:
            del u.backpack[normalized_id]
        return True

    async def backpack_toggle_lock(self, user_id: str, numeric_id: str, lock=None):
        u = await self.user_get(user_id)
        if not isinstance(u.backpack, dict):
            return False
        normalized_id = _normalize_fish_numeric_id(numeric_id)
        entry = u.backpack.get(normalized_id)
        if not entry:
            return False
        entry["locked"] = lock if lock is not None else not entry.get("locked", False)
        return True

    async def backpack_lock_by_rarity(self, user_id: str, rarity: str) -> int:
        u = await self.user_get(user_id)
        if not isinstance(u.backpack, dict):
            return 0
        count = 0
        for numeric_id, entry in u.backpack.items():
            if entry.get("rarity") == rarity and not entry.get("locked", False):
                entry["locked"] = True
                count += 1
        return count

    async def backpack_unlock_by_rarity(self, user_id: str, rarity: str) -> int:
        u = await self.user_get(user_id)
        if not isinstance(u.backpack, dict):
            return 0
        count = 0
        for numeric_id, entry in u.backpack.items():
            if entry.get("rarity") == rarity and entry.get("locked", False):
                entry["locked"] = False
                count += 1
        return count

    async def backpack_lock_by_location_prefix(
        self, user_id: str, prefix: str
    ) -> int:
        u = await self.user_get(user_id)
        if not isinstance(u.backpack, dict):
            return 0
        count = 0
        for numeric_id, entry in u.backpack.items():
            if numeric_id.startswith(prefix) and not entry.get("locked", False):
                entry["locked"] = True
                count += 1
        return count

    async def backpack_unlock_by_location_prefix(
        self, user_id: str, prefix: str
    ) -> int:
        u = await self.user_get(user_id)
        if not isinstance(u.backpack, dict):
            return 0
        count = 0
        for numeric_id, entry in u.backpack.items():
            if numeric_id.startswith(prefix) and entry.get("locked", False):
                entry["locked"] = False
                count += 1
        return count

    async def backpack_lock_all(self, user_id: str) -> int:
        u = await self.user_get(user_id)
        if not isinstance(u.backpack, dict):
            return 0
        count = 0
        for numeric_id, entry in u.backpack.items():
            if not entry.get("locked", False):
                entry["locked"] = True
                count += 1
        return count

    async def backpack_unlock_all(self, user_id: str) -> int:
        u = await self.user_get(user_id)
        if not isinstance(u.backpack, dict):
            return 0
        count = 0
        for numeric_id, entry in u.backpack.items():
            if entry.get("locked", False):
                entry["locked"] = False
                count += 1
        return count

    async def backpack_clear(self, user_id: str):
        u = await self.user_get(user_id)
        u.backpack = {}

    async def backpack_filter_fish(
        self, user_id, rarity_in=None, locked=None, numeric_id=None
    ):
        fish_list = await self.backpack_get_user_fish(user_id)
        result = []
        for f in fish_list:
            if rarity_in and f["rarity"] not in rarity_in:
                continue
            if locked is not None and f.get("locked", False) != locked:
                continue
            if numeric_id and f["numeric_id"] != numeric_id:
                continue
            result.append(f)
        return result

    async def backpack_delete_fish_entries(self, user_id, fish_list):
        u = await self.user_get(user_id)
        if not isinstance(u.backpack, dict):
            return
        for f in fish_list:
            nid = f.get("numeric_id")
            if nid and nid in u.backpack:
                del u.backpack[nid]

    async def backpack_get_unlocked_fish(self, user_id):
        fish_list = await self.backpack_get_user_fish(user_id)
        return [f for f in fish_list if not f.get("locked", False)]

    # --- FishingUser: Display (displays JSONB) ---
    async def display_get_user_displays(self, user_id: str):
        u = await self.user_get(user_id)
        if not isinstance(u.displays, dict):
            return []
        result = []
        for slot_str, entry in u.displays.items():
            result.append(
                {
                    "slot": int(slot_str),
                    "fish_name": entry.get("fish_name", ""),
                    "rarity": entry.get("rarity", "N"),
                    "numeric_id": _normalize_fish_numeric_id(
                        entry.get("numeric_id", "")
                    ),
                }
            )
        result.sort(key=lambda d: d["slot"])
        return result

    async def display_set(self, user_id, slot, fish_name, rarity, numeric_id):
        u = await self.user_get(user_id)
        if not isinstance(u.displays, dict):
            u.displays = {}
        numeric_id = _normalize_fish_numeric_id(numeric_id)
        u.displays[str(slot)] = {
            "fish_name": fish_name,
            "rarity": rarity,
            "numeric_id": numeric_id,
        }
        return u.displays[str(slot)]

    async def display_remove(self, user_id, slot):
        u = await self.user_get(user_id)
        if not isinstance(u.displays, dict):
            return False
        slot_str = str(slot)
        if slot_str not in u.displays:
            return False
        del u.displays[slot_str]
        return True

    async def display_clear(self, user_id: str):
        u = await self.user_get(user_id)
        u.displays = {}

    # --- FishingUser: Items (items JSONB) ---
    async def items_add(self, user_id, item_id, item_type, count=1):
        u = await self.user_get(user_id)
        if not isinstance(u.items, dict):
            u.items = {}
        key = f"{item_id}|{item_type}"
        entry = u.items.get(key)
        if entry:
            entry["count"] = entry.get("count", 0) + count
        else:
            u.items[key] = {"item_type": item_type, "count": count}

    async def items_get_user_items(self, user_id: str):
        u = await self.user_get(user_id)
        if not isinstance(u.items, dict):
            return []
        result = []
        for key, entry in u.items.items():
            parts = key.split("|", 1)
            if len(parts) == 2:
                result.append(
                    {
                        "item_id": parts[0],
                        "item_type": entry.get("item_type", parts[1]),
                        "count": entry.get("count", 0),
                    }
                )
        return result

    async def items_get_item(self, user_id, item_id, item_type):
        u = await self.user_get(user_id)
        if not isinstance(u.items, dict):
            return None
        key = f"{item_id}|{item_type}"
        entry = u.items.get(key)
        if not entry:
            return None
        return {
            "item_id": item_id,
            "item_type": entry.get("item_type", item_type),
            "count": entry.get("count", 0),
        }

    async def items_remove(self, user_id, item_id, item_type, count=1):
        u = await self.user_get(user_id)
        if not isinstance(u.items, dict):
            return False
        key = f"{item_id}|{item_type}"
        entry = u.items.get(key)
        if not entry or entry.get("count", 0) < count:
            return False
        entry["count"] -= count
        if entry["count"] <= 0:
            del u.items[key]
        return True

    async def items_has(self, user_id, item_id, item_type):
        u = await self.user_get(user_id)
        if not isinstance(u.items, dict):
            return False
        key = f"{item_id}|{item_type}"
        return key in u.items

    async def items_clear(self, user_id: str):
        u = await self.user_get(user_id)
        u.items = {}

    # --- FishingUser: Achievement (achievements JSONB) ---
    async def achievement_is_completed(self, user_id: str, key: str):
        u = await self.user_get(user_id)
        if not isinstance(u.achievements, list):
            return False
        return key in u.achievements

    async def achievement_mark_completed(self, user_id: str, key: str):
        u = await self.user_get(user_id)
        if not isinstance(u.achievements, list):
            u.achievements = []
        if key not in u.achievements:
            u.achievements.append(key)

    async def achievement_get_user_achievements(self, user_id: str):
        u = await self.user_get(user_id)
        if not isinstance(u.achievements, list):
            return set()
        return set(u.achievements)

    # --- FishingUser: Collection (collection JSONB) ---
    async def collection_mark_collected(
        self, user_id: str, fish_name: str, rarity: str, count: int = 1
    ):
        u = await self.user_get(user_id)
        if not isinstance(u.collection, dict):
            u.collection = {}
        collection, _ = _normalize_collection(u.collection)
        fish_entry = collection.setdefault(fish_name, {})
        fish_entry[rarity] = fish_entry.get(rarity, 0) + count
        u.collection = collection

    async def collection_get_user_collected(self, user_id: str):
        u = await self.user_get(user_id)
        if not isinstance(u.collection, dict):
            return set()
        collection, changed = _normalize_collection(u.collection)
        if changed:
            u.collection = collection
        result = set()
        for fish_name, rarities in collection.items():
            if not isinstance(rarities, dict):
                continue
            for rarity, count in rarities.items():
                if count:
                    result.add((fish_name, rarity))
        return result

    async def collection_get_user_collected_with_count(self, user_id: str):
        u = await self.user_get(user_id)
        if not isinstance(u.collection, dict):
            return {}
        collection, changed = _normalize_collection(u.collection)
        if changed:
            u.collection = collection
        result = {}
        for fish_name, rarities in collection.items():
            if not isinstance(rarities, dict):
                continue
            for rarity, count in rarities.items():
                result[(fish_name, rarity)] = count
        return result

    async def collection_is_collected(self, user_id: str, fish_name: str, rarity: str):
        u = await self.user_get(user_id)
        if not isinstance(u.collection, dict):
            return False
        collection, changed = _normalize_collection(u.collection)
        if changed:
            u.collection = collection
        return bool(collection.get(fish_name, {}).get(rarity, 0))

    async def collection_clear_user_collection(self, user_id: str):
        u = await self.user_get(user_id)
        u.collection = {}

    # --- FishingBuff ---
    async def buff_add_user_buff(
        self, user_id, buff_type, duration_minutes, value=1, description=""
    ):
        now = datetime.now()
        b = InMemoryBuff(
            "user",
            user_id,
            buff_type,
            now,
            now + timedelta(minutes=duration_minutes),
            value,
            description,
        )
        b.id = self._gen_id()
        self._buffs.append(b)
        return b

    async def buff_add_location_buff(
        self,
        location_id,
        buff_type,
        duration_hours,
        value=1,
        description="",
        source_user_id=None,
    ):
        now = datetime.now()
        b = InMemoryBuff(
            "location",
            location_id,
            buff_type,
            now,
            now + timedelta(hours=duration_hours),
            value,
            description,
            source_user_id,
        )
        b.id = self._gen_id()
        self._buffs.append(b)
        return b

    async def buff_get_active_buffs_for_fishing(
        self, user_id, location_id, start_time, end_time
    ):
        result = []
        for target_type, target_id in [
            ("user", user_id),
            ("location", location_id),
            ("global", ""),
        ]:
            for b in self._buffs:
                if b.target_type == target_type and b.target_id == target_id:
                    if b.start_time < end_time and b.end_time > start_time:
                        result.append(b)
        has_lost_wind = any(b.buff_type == "weather_lost_wind" for b in result)
        if has_lost_wind:
            unlocked = await self.has_unlocked_lost_wind(user_id, location_id)
            if not unlocked:
                result = [b for b in result if b.buff_type != "weather_lost_wind"]
        return result

    async def buff_get_location_buff_count(
        self, location_id: str, buff_type: str = "nest"
    ):
        now = datetime.now()
        return sum(
            1
            for b in self._buffs
            if b.target_type == "location"
            and b.target_id == location_id
            and b.buff_type == buff_type
            and b.start_time <= now
            and b.end_time > now
        )

    async def buff_get_global_buff_count(self, buff_type: str = "frame"):
        now = datetime.now()
        return sum(
            1
            for b in self._buffs
            if b.target_type == "global"
            and b.buff_type == buff_type
            and b.start_time <= now
            and b.end_time > now
        )

    async def buff_add_global_buff(
        self,
        buff_type,
        start_time,
        end_time,
        value=1,
        description="",
    ):
        b = InMemoryBuff(
            "global",
            "",
            buff_type,
            start_time,
            end_time,
            value,
            description,
        )
        b.id = self._gen_id()
        self._buffs.append(b)
        return b

    async def buff_get_active_user_buff(self, user_id: str, buff_type: str):
        now = datetime.now()
        for b in self._buffs:
            if (
                b.target_type == "user"
                and b.target_id == user_id
                and b.buff_type == buff_type
                and b.start_time <= now
                and b.end_time > now
            ):
                return b
        return None

    async def buff_clear_expired(self):
        cutoff = datetime.now() - timedelta(hours=24)
        self._buffs = [b for b in self._buffs if b.end_time >= cutoff]

    async def has_unlocked_lost_wind(self, user_id: str, location_id: str) -> bool:
        return (user_id, location_id) in self._unlocked_lost_winds

    async def mark_lost_wind_unlocked(self, user_id: str, location_id: str) -> None:
        self._unlocked_lost_winds.add((user_id, location_id))

    # --- FishingUser: Auto-sell ---
    async def user_get_auto_sell(self, user_id: str) -> bool:
        u = await self.user_get(user_id)
        return u.auto_sell

    async def user_get_auto_sell_rarity(self, user_id: str) -> str:
        u = await self.user_get(user_id)
        return u.auto_sell_rarity or "UTR"

    async def user_set_auto_sell_rarity(self, user_id: str, rarity: str) -> None:
        u = await self.user_get(user_id)
        u.auto_sell_rarity = rarity

    # --- FishingUser: Auto-lock ---
    async def user_get_auto_lock(self, user_id: str) -> bool:
        u = await self.user_get(user_id)
        return u.auto_lock

    async def user_get_auto_lock_pattern(self, user_id: str) -> str:
        u = await self.user_get(user_id)
        return u.auto_lock_pattern or ""

    # --- FishingExchangeRecord ---
    async def exchange_create_black_record(self, user_id: str, source, target):
        record = InMemoryExchangeRecord(self._gen_id(), user_id, source, target)
        self._exchange_records.append(record)
        return record

    async def exchange_list_active_records(self):
        return sorted(
            [
                r
                for r in self._exchange_records
                if r.is_active and r.source_numeric_id != r.target_numeric_id
            ],
            key=lambda r: (
                r.target_scene_level,
                r.target_location_id,
                r.target_name,
                r.target_rarity,
                r.id,
            ),
        )

    async def exchange_find_active_reverse(self, source, target):
        if source.numeric_id == target.numeric_id:
            return None
        records = [
            r
            for r in self._exchange_records
            if r.is_active
            and r.source_numeric_id == target.numeric_id
            and r.target_numeric_id == source.numeric_id
        ]
        records.sort(key=lambda r: r.id)
        return records[0] if records else None

    async def exchange_invalidate_record(
        self, record_id: int, reversed_by_user_id: str
    ):
        for record in self._exchange_records:
            if record.id == record_id:
                record.is_active = False
                record.reversed_by_user_id = reversed_by_user_id
                return
        raise ValueError(f"record {record_id} not found")
