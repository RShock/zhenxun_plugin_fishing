"""成就金币倍数保护测试。

测试目标：确保 _check_achievement 中 bonus_multiplier 的计算逻辑
不会被意外修改。一旦有人修改倍数，此测试会立刻失败。

成就倍数规范：
- collect_rarity_{loc}_{rarity}    → 3x   (同场景相同稀有度全收集, 含UTR)
- collect_rarity_{loc}_UTR         → 3x   (同场景全鱼UTR收集)
- collect_fish_{loc}_{fish}        → 3x   (同场景单鱼全稀有度收集 N~UR)
- collect_scene_{loc}             → 1x   (同场景全鱼全稀有度收集, 含迷途风解锁)
- collect_fish_utr_{loc}_{fish}   → 3x   (同场景单鱼真全稀有度 N~UTR)
- collect_scene_utr_{loc}         → 1x   (同场景全鱼真全稀有度收集 N~UTR)
"""

RARITIES_UP_TO_UR = ["N", "R", "SR", "SSR", "UR"]
RARITIES_FULL = ["N", "R", "SR", "SSR", "UR", "UTR"]

EXPECTED_MULTIPLIERS = {
    "collect_rarity": 3.0,
    "collect_rarity_utr": 3.0,
    "collect_fish": 3.0,
    "collect_scene": 1.0,
    "collect_fish_utr": 3.0,
    "collect_scene_utr": 1.0,
}


class TestAchievementGoldCalculation:
    """通过实际调用 _check_achievement 验证金币计算。"""

    async def test_rarity_collection_gives_3x_of_total_fish_price(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager, calculate_fish_price
        from zhenxun.plugins.zhenxun_plugin_fishing.services.achievement_service import (
            _check_achievement,
        )

        locations = ConfigManager.get_locations()
        loc = locations[0]

        fish_list = []
        for fid in loc.fish_pool:
            f = ConfigManager.get_fish(fid)
            if f:
                fish_list.append(f)

        user_id = "test_ach_rarity"
        await db.user_get_or_create(user_id)

        for rarity in RARITIES_UP_TO_UR:
            collected = set()
            total_price = 0
            for f in fish_list:
                collected.add((f.id, rarity))
                total_price += calculate_fish_price(f, rarity, loc.difficulty)

            db._users[user_id].collection = {
                f"{fid}|{rarity}": 1 for fid in loc.fish_pool
            }
            db._users[user_id].achievements = []

            pairs = [(f.id, rarity) for f in fish_list]
            result = await _check_achievement(
                user_id,
                f"test_rarity_{loc.id}_{rarity}",
                pairs,
                "test",
                collected,
                loc.difficulty,
                bonus_multiplier=3.0,
            )

            expected = int(total_price * 3.0)
            assert result["coins"] == expected, (
                f"[漏洞] {loc.name} {rarity}级全收集: "
                f"期望{expected}金币, 实际{result['coins']}\n"
                f"所有鱼{rarity}价格总和={total_price}, bonus_mult=3.0"
            )

    async def test_fish_full_rarity_collection_gives_3x(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager, calculate_fish_price
        from zhenxun.plugins.zhenxun_plugin_fishing.services.achievement_service import (
            _check_achievement,
        )

        locations = ConfigManager.get_locations()
        loc = locations[0]
        fish_list = [ConfigManager.get_fish(fid) for fid in loc.fish_pool]
        fish_list = [f for f in fish_list if f]

        user_id = "test_ach_fish"
        await db.user_get_or_create(user_id)

        for fish in fish_list:
            collected = set()
            total_price = 0
            for rarity in RARITIES_UP_TO_UR:
                collected.add((fish.id, rarity))
                total_price += calculate_fish_price(fish, rarity, loc.difficulty)

            db._users[user_id].collection = {
                f"{fish.id}|{r}": 1 for r in RARITIES_UP_TO_UR
            }
            db._users[user_id].achievements = []

            pairs = [(fish.id, r) for r in RARITIES_UP_TO_UR]
            result = await _check_achievement(
                user_id,
                f"test_fish_{loc.id}_{fish.id}",
                pairs,
                "test",
                collected,
                loc.difficulty,
                bonus_multiplier=3.0,
            )

            expected = int(total_price * 3.0)
            assert result["coins"] == expected, (
                f"[漏洞] {fish.id} 全稀有度收集(N~UR): "
                f"期望{expected}金币, 实际{result['coins']}\n"
                f"各稀有度价格总和={total_price}"
            )

    async def test_fish_utr_collection_gives_3x(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager, calculate_fish_price
        from zhenxun.plugins.zhenxun_plugin_fishing.services.achievement_service import (
            _check_achievement,
        )

        locations = ConfigManager.get_locations()
        loc = locations[0]
        fish_list = [ConfigManager.get_fish(fid) for fid in loc.fish_pool]
        fish_list = [f for f in fish_list if f]

        user_id = "test_ach_fish_utr"
        await db.user_get_or_create(user_id)

        for fish in fish_list:
            collected = set()
            total_price = 0
            for rarity in RARITIES_FULL:
                collected.add((fish.id, rarity))
                total_price += calculate_fish_price(fish, rarity, loc.difficulty)

            db._users[user_id].collection = {f"{fish.id}|{r}": 1 for r in RARITIES_FULL}
            db._users[user_id].achievements = []

            pairs = [(fish.id, r) for r in RARITIES_FULL]
            result = await _check_achievement(
                user_id,
                f"test_fish_utr_{loc.id}_{fish.id}",
                pairs,
                "test",
                collected,
                loc.difficulty,
                bonus_multiplier=3.0,
            )

            expected = int(total_price * 3.0)
            assert result["coins"] == expected, (
                f"[漏洞] {fish.id} 真全稀有度收集(N~UTR): "
                f"期望{expected}金币, 实际{result['coins']}\n"
                f"各稀有度价格总和={total_price}"
            )

    async def test_scene_collection_gives_1x(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager, calculate_fish_price
        from zhenxun.plugins.zhenxun_plugin_fishing.services.achievement_service import (
            _check_achievement,
        )

        locations = ConfigManager.get_locations()
        loc = locations[0]
        fish_list = [ConfigManager.get_fish(fid) for fid in loc.fish_pool]
        fish_list = [f for f in fish_list if f]

        user_id = "test_ach_scene"
        await db.user_get_or_create(user_id)

        collected = set()
        total_price = 0
        for fish in fish_list:
            for rarity in RARITIES_UP_TO_UR:
                collected.add((fish.id, rarity))
                total_price += calculate_fish_price(fish, rarity, loc.difficulty)

        db._users[user_id].collection = {
            f"{f.id}|{r}": 1 for f in fish_list for r in RARITIES_UP_TO_UR
        }
        db._users[user_id].achievements = []

        pairs = [(f.id, r) for f in fish_list for r in RARITIES_UP_TO_UR]
        result = await _check_achievement(
            user_id,
            f"test_scene_{loc.id}",
            pairs,
            "test",
            collected,
            loc.difficulty,
            bonus_multiplier=1.0,
        )

        expected = int(total_price * 1.0)
        assert result["coins"] == expected, (
            f"[漏洞] {loc.name} 场景全收集: "
            f"期望{expected}金币, 实际{result['coins']}\n"
            f"各鱼各稀有度价格总和={total_price}"
        )

    async def test_utr_rarity_collection_gives_3x(self, db):
        """同场景全鱼UTR稀有度收集, 3x奖励。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager, calculate_fish_price
        from zhenxun.plugins.zhenxun_plugin_fishing.services.achievement_service import (
            _check_achievement,
        )

        locations = ConfigManager.get_locations()
        loc = locations[0]
        fish_list = [ConfigManager.get_fish(fid) for fid in loc.fish_pool]
        fish_list = [f for f in fish_list if f]

        user_id = "test_ach_utr_rarity"
        await db.user_get_or_create(user_id)

        collected = set()
        total_price = 0
        for fish in fish_list:
            collected.add((fish.id, "UTR"))
            total_price += calculate_fish_price(fish, "UTR", loc.difficulty)

        db._users[user_id].collection = {f"{f.id}|UTR": 1 for f in fish_list}
        db._users[user_id].achievements = []

        pairs = [(f.id, "UTR") for f in fish_list]
        result = await _check_achievement(
            user_id,
            f"test_utr_rarity_{loc.id}",
            pairs,
            "test",
            collected,
            loc.difficulty,
            bonus_multiplier=3.0,
        )

        expected = int(total_price * 3.0)
        assert result["coins"] == expected, (
            f"[漏洞] {loc.name} 全鱼UTR收集: "
            f"期望{expected}金币, 实际{result['coins']}\n"
            f"UTR总价={total_price}"
        )

    async def test_scene_utr_collection_gives_1x(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager, calculate_fish_price
        from zhenxun.plugins.zhenxun_plugin_fishing.services.achievement_service import (
            _check_achievement,
        )

        locations = ConfigManager.get_locations()
        loc = locations[0]
        fish_list = [ConfigManager.get_fish(fid) for fid in loc.fish_pool]
        fish_list = [f for f in fish_list if f]

        user_id = "test_ach_scene_utr"
        await db.user_get_or_create(user_id)

        collected = set()
        total_price = 0
        for fish in fish_list:
            for rarity in RARITIES_FULL:
                collected.add((fish.id, rarity))
                total_price += calculate_fish_price(fish, rarity, loc.difficulty)

        db._users[user_id].collection = {
            f"{f.id}|{r}": 1 for f in fish_list for r in RARITIES_FULL
        }
        db._users[user_id].achievements = []

        pairs = [(f.id, r) for f in fish_list for r in RARITIES_FULL]
        result = await _check_achievement(
            user_id,
            f"test_scene_utr_{loc.id}",
            pairs,
            "test",
            collected,
            loc.difficulty,
            bonus_multiplier=1.0,
        )

        expected = int(total_price * 1.0)
        assert result["coins"] == expected, (
            f"[漏洞] {loc.name} 场景真全收集: "
            f"期望{expected}金币, 实际{result['coins']}\n"
            f"各鱼各稀有度价格总和={total_price}"
        )

    async def test_achievement_not_triggered_twice(self, db):
        """已完成的成就不应再次触发。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager
        from zhenxun.plugins.zhenxun_plugin_fishing.services.achievement_service import (
            _check_achievement,
        )

        locations = ConfigManager.get_locations()
        loc = locations[0]
        fish_list = [ConfigManager.get_fish(fid) for fid in loc.fish_pool]
        fish_list = [f for f in fish_list if f]

        user_id = "test_ach_twice"
        await db.user_get_or_create(user_id)

        collected = set()
        for f in fish_list:
            collected.add((f.id, "N"))

        db._users[user_id].collection = {f"{fid}|N": 1 for fid in loc.fish_pool}
        db._users[user_id].achievements = [f"collect_rarity_{loc.id}_N"]

        result = await _check_achievement(
            user_id,
            f"collect_rarity_{loc.id}_N",
            [(f.id, "N") for f in fish_list],
            "test",
            collected,
            loc.difficulty,
            bonus_multiplier=3.0,
        )

        assert result["coins"] == 0, "已完成的成就不应再发金币"
        assert len(result["messages"]) == 0, "已完成的成就不应再有消息"
