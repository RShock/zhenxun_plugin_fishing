from .base import ConfigManager, gradient_bg, render_html, render_template


async def render_shop(
    baits: list,
    potions: list,
    rod_level: int,
    rod_upgrade_price: int,
    hook_level: int,
    hook_upgrade_price: int,
    display_slots: int = 3,
    display_frames: int = 0,
    cat_frames: int = 0,
    upgraded_display_count: int = 0,
    gold: int = 0,
    user_id: str = "",
    starry_frames: int = 0,
    has_starry_ship: bool = False,
    star_frames: int = 0,
) -> bytes:
    rod_section = {"is_max": rod_level >= 20}
    if rod_level >= 20:
        rod_section["name"] = "🎣 钓竿已满级"
        rod_section["desc"] = "当前等级: 20级 · 奇迹彼岸钓竿"
    elif rod_level == 10 and user_id:
        # Lv.10 未建设星空艇时，升级入口替换为星空艇建设入口。
        from ..starry import STARRY_SHIP_COST, has_starry_ship

        if not await has_starry_ship(user_id):
            rod_section["name"] = "🚀 购买星空艇"
            rod_section["desc"] = "解锁第二部分【星空钓鱼】"
            rod_section["price"] = STARRY_SHIP_COST
            rod_section["cmd"] = "建设星空艇"
        else:
            rod_section["name"] = "🎣 升级钓竿"
            rod_section["desc"] = f"当前等级: {rod_level}级 → {rod_level + 1}级"
            rod_section["price"] = rod_upgrade_price
            rod_section["cmd"] = "升级钓竿"
    else:
        rod_section["name"] = "🎣 升级钓竿"
        rod_section["desc"] = f"当前等级: {rod_level}级 → {rod_level + 1}级"
        rod_section["price"] = rod_upgrade_price
        rod_section["cmd"] = "升级钓竿"

    hook_section = {"is_max": hook_level >= 10}
    if hook_level >= 10:
        hook_section["name"] = "🪝 鱼钩已满级"
        hook_section["desc"] = "当前速度加成: 100%"
    else:
        hook_section["name"] = "🪝 升级鱼钩"
        hook_section["desc"] = (
            f"速度加成: {hook_level * 10}% → {(hook_level + 1) * 10}%"
        )
        hook_section["price"] = hook_upgrade_price
        hook_section["cmd"] = "升级鱼钩"

    # 展示栏万能升级：单入口，细分木框 / 猫框 / 星空框等级与材料
    from ..constants import (
        STARRY_FRAME_UPGRADE_COSTS,
        STARRY_FRAMES_MAX,
        UPGRADE_DISPLAY_COSTS,
    )

    frame_rows: list[dict] = []

    # 1) 展示木框 → 增加展示栏位
    if display_slots < 10:
        next_slot = display_slots + 1
        display_slot_costs = {4: 1, 5: 2, 6: 3, 7: 5, 8: 8, 9: 13, 10: 21}
        frames_needed = display_slot_costs.get(next_slot, next_slot - 3)
        enough = display_frames >= frames_needed
        frame_rows.append(
            {
                "key": "wood",
                "icon": "🖼️",
                "name": "展示木框",
                "level_text": f"{display_slots} → {next_slot}",
                "material": f"需要 {frames_needed} 个展示木框",
                "owned_text": f"拥有 {display_frames}",
                "enough": enough,
                "is_max": False,
            }
        )
    else:
        frame_rows.append(
            {
                "key": "wood",
                "icon": "🖼️",
                "name": "展示木框",
                "level_text": f"{display_slots}/10",
                "material": "已满级",
                "owned_text": f"拥有 {display_frames}",
                "enough": True,
                "is_max": True,
            }
        )

    # 2) 猫猫框 → 强化展示栏位
    if display_slots <= 0:
        frame_rows.append(
            {
                "key": "cat",
                "icon": "🐱",
                "name": "猫猫框",
                "level_text": "0/10",
                "material": "需先拥有展示栏位",
                "owned_text": f"拥有 {cat_frames}",
                "enough": False,
                "is_max": True,
            }
        )
    elif upgraded_display_count < 10 and upgraded_display_count < display_slots:
        next_upgrade = upgraded_display_count + 1
        frames_needed = UPGRADE_DISPLAY_COSTS.get(next_upgrade, next_upgrade)
        enough = cat_frames >= frames_needed
        frame_rows.append(
            {
                "key": "cat",
                "icon": "🐱",
                "name": "猫猫框",
                "level_text": f"{upgraded_display_count} → {next_upgrade}",
                "material": f"需要 {frames_needed} 个猫猫框",
                "owned_text": f"拥有 {cat_frames}",
                "enough": enough,
                "is_max": False,
            }
        )
    else:
        level_cap = min(display_slots, 10)
        frame_rows.append(
            {
                "key": "cat",
                "icon": "🐱",
                "name": "猫猫框",
                "level_text": f"{upgraded_display_count}/{level_cap}",
                "material": "已满级" if upgraded_display_count >= 10 else "已强化全部栏位",
                "owned_text": f"拥有 {cat_frames}",
                "enough": True,
                "is_max": True,
            }
        )

    # 3) 星空木框 → 消耗星辰木框（仅已建星空艇）
    if has_starry_ship:
        if starry_frames < STARRY_FRAMES_MAX:
            next_level = starry_frames + 1
            frames_needed = STARRY_FRAME_UPGRADE_COSTS.get(next_level, next_level)
            enough = star_frames >= frames_needed
            frame_rows.append(
                {
                    "key": "starry",
                    "icon": "✨",
                    "name": "星空木框",
                    "level_text": f"{starry_frames} → {next_level}",
                    "material": f"需要 {frames_needed} 个星辰木框",
                    "owned_text": f"拥有 {star_frames}",
                    "enough": enough,
                    "is_max": False,
                }
            )
        else:
            frame_rows.append(
                {
                    "key": "starry",
                    "icon": "✨",
                    "name": "星空木框",
                    "level_text": f"{starry_frames}/{STARRY_FRAMES_MAX}",
                    "material": "已满级",
                    "owned_text": f"拥有 {star_frames}",
                    "enough": True,
                    "is_max": True,
                }
            )

    all_max = all(row["is_max"] for row in frame_rows)
    frame_upgrade = {
        "rows": frame_rows,
        "all_max": all_max,
        "cmd": "升级展示栏",
    }

    bait_items = []
    for item in baits:
        bait_items.append(
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "info": f"速度+{item.speed_bonus}%",
                "price": item.price,
            }
        )

    potion_items = []
    for item in potions:
        potion_items.append(
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "info": f"持续: {item.duration}分钟",
                "price": item.price,
            }
        )

    html = render_template(
        "shop.html",
        body_bg=gradient_bg("peach"),
        width=550,
        gold=gold,
        display_frames=display_frames,
        cat_frames=cat_frames,
        star_frames=star_frames,
        rod_section=rod_section,
        hook_section=hook_section,
        frame_upgrade=frame_upgrade,
        bait_items=bait_items,
        potion_items=potion_items,
    )
    return await render_html(html, 550)


async def render_user_status(
    user_id: str,
    gold: int,
    rod_name: str,
    rod_level: int,
    hook_level: int,
    bait_name: str,
    fishing_interval: float,
    is_fishing: bool,
    fishing_location: str | None = None,
    corn: int = 0,
    bait_remaining: int = 0,
    display_frames: int = 0,
) -> bytes:
    bait_display = bait_name
    if bait_remaining > 0:
        bait_display = f"{bait_name} (剩余{bait_remaining}个)"

    html = render_template(
        "user_status.html",
        body_bg=gradient_bg("purple"),
        width=400,
        gold=gold,
        is_fishing=is_fishing,
        fishing_location=fishing_location,
        rod_name=rod_name,
        rod_level=rod_level,
        hook_level=hook_level,
        hook_speed_percent=hook_level
        * ConfigManager.get_shop().hook_speed_bonus_per_level,
        bait_display=bait_display,
        fishing_interval=fishing_interval,
        corn=corn,
    )
    return await render_html(html, 400)
