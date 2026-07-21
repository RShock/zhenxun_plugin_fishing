import time

from .base import (
    RARITY_COLORS,
    RARITY_NAMES,
    get_location_image_src,
    gradient_bg,
    render_html,
    render_template,
    save_debug_output,
)


async def render_location_select(
    user_id: str,
    locations: list,
    user_level: int = 1,
) -> bytes:
    from ..config import WEATHER_EMOJI
    from ..models import FishingBuff, FishingUser
    from ..weather_service import get_all_location_weathers

    t0 = time.perf_counter()

    fisher_counts = await FishingUser.get_location_fisher_counts()
    t1 = time.perf_counter()

    nest_counts = {}
    for loc in locations:
        if getattr(loc, "difficulty", 1) > user_level:
            continue
        count = await FishingBuff.get_location_buff_count(loc.id)
        if count > 0:
            nest_counts[loc.id] = count
    t1b = time.perf_counter()

    frame_bonus_by_loc = {}
    for loc in locations:
        frame_count = await FishingBuff.get_frame_buff_count_for_location(loc.id)
        frame_bonus_by_loc[loc.id] = frame_count * 5

    all_weathers = await get_all_location_weathers(user_id)
    t1c = time.perf_counter()

    from ..cat_park import has_cat_park_ticket, is_cat_park_location
    from ..starry import has_starry_ship, is_starry_location

    has_ticket = await has_cat_park_ticket(user_id)
    has_ship = await has_starry_ship(user_id)
    available_locations = []
    for loc in locations:
        if is_cat_park_location(loc.id):
            if has_ticket:
                available_locations.append(loc)
        elif is_starry_location(loc.id):
            if has_ship and getattr(loc, "difficulty", 1) <= user_level:
                available_locations.append(loc)
        elif getattr(loc, "difficulty", 1) <= user_level:
            available_locations.append(loc)

    loc_data = []
    for i, loc in enumerate(available_locations, 1):
        diff = getattr(loc, "difficulty", 1)
        image_src = get_location_image_src(loc.name)
        if str(loc.id).upper() == "S1" and not image_src:
            from .fishing_scene import _find_scene_file

            scene_file, _ = _find_scene_file(loc)
            image_src = scene_file.as_uri() if scene_file else ""
        fisher_count = fisher_counts.get(loc.id, 0)
        nest_count = nest_counts.get(loc.id, 0)
        nest_bonus = nest_count * 5
        total_speed_bonus = nest_bonus + frame_bonus_by_loc.get(loc.id, 0)

        w = all_weathers.get(loc.id)
        if w:
            wt = w.get("weather_type", "sunny")
            weather_emoji = WEATHER_EMOJI.get(wt, "☀️")
            weather_time = ""
            if wt not in ("sunny", "chaotic_era") and w.get("start_time") and w.get("end_time"):
                st = w["start_time"]
                et = w["end_time"]
                if hasattr(st, "hour"):
                    st_str = str(st.hour)
                else:
                    st_str = str(st)
                if hasattr(et, "hour"):
                    et_hour = et.hour
                    et_str = "24" if et_hour == 0 else str(et_hour)
                else:
                    et_str = str(et)
                weather_time = f"{st_str}-{et_str}"
        else:
            _default_wt = "chaotic_era" if is_starry_location(loc.id) else "sunny"
            weather_emoji = WEATHER_EMOJI.get(_default_wt, "☀️")
            weather_time = ""

        loc_data.append(
            {
                "num": loc.id if str(loc.id).upper() == "S1" else i,
                "name": loc.name,
                "difficulty": diff,
                "image_src": image_src,
                "fisher_count": fisher_count,
                "nest_bonus": total_speed_bonus,
                "weather_emoji": weather_emoji,
                "weather_time": weather_time,
            }
        )

    t2 = time.perf_counter()

    html = render_template(
        "location_select.html",
        body_bg=gradient_bg("blue"),
        width=600,
        locations=loc_data,
        hint_text="输入【钓鱼 x】选择钓鱼地点，x为蓝圈中的字",
    )
    t3 = time.perf_counter()

    result = await render_html(html, 600)
    t4 = time.perf_counter()

    save_debug_output(
        "location_select",
        user_id,
        html,
        result,
        {
            "db_query": t1 - t0,
            "nest_query": t1b - t1,
            "data_prep": t2 - t1b,
            "template": t3 - t2,
            "html_to_pic": t4 - t3,
            "total": t4 - t0,
        },
    )

    return result


async def render_sign_result(
    user_id: str,
    corn_count: int,
    display_income: int = 0,
) -> bytes:
    html = render_template(
        "sign_result.html",
        body_bg=gradient_bg("green"),
        width=350,
        corn_count=corn_count,
        display_income=display_income,
    )
    return await render_html(html, 350)


async def render_upgrade_result(
    user_id: str,
    title: str,
    old_level: int,
    new_level: int,
    desc: str,
    price: int,
    remaining_gold: int,
    next_price: int = 0,
) -> bytes:
    html = render_template(
        "upgrade_result.html",
        body_bg=gradient_bg("blue"),
        width=350,
        title=title,
        old_level=old_level,
        new_level=new_level,
        desc=desc,
        price=price,
        remaining_gold=remaining_gold,
        next_price=next_price,
    )
    return await render_html(html, 350)


async def render_exchange_result(
    user_id: str,
    fish_coins: int,
    gold_received: int,
    remaining_coins: int,
) -> bytes:
    html = render_template(
        "exchange_result.html",
        body_bg=gradient_bg("orange"),
        width=350,
        fish_coins=fish_coins,
        gold_received=gold_received,
        remaining_coins=remaining_coins,
    )
    return await render_html(html, 350)


async def render_nest_confirm(
    user_id: str,
    nest_price: int,
    duration: int = 4,
) -> bytes:
    html = render_template(
        "nest_confirm.html",
        body_bg=gradient_bg("peach"),
        width=400,
        nest_price=nest_price,
        duration=duration,
    )
    return await render_html(html, 400)


async def render_nest_result(
    user_id: str,
    location_name: str,
    cost_text: str,
    duration_hours: int,
    nest_count: int,
) -> bytes:
    html = render_template(
        "nest_result.html",
        body_bg=gradient_bg("green"),
        width=400,
        location_name=location_name,
        cost_text=cost_text,
        duration_hours=duration_hours,
        nest_count=nest_count,
    )
    return await render_html(html, 400)


async def render_sell_result(
    user_id: str,
    fish_list: list,
    total_gold: int,
) -> bytes:
    fish_items = []
    for fish in fish_list:
        color = RARITY_COLORS.get(fish.rarity, "#808080")
        rarity_name = RARITY_NAMES.get(fish.rarity, fish.rarity)
        fish_items.append(
            {
                "rarity_color": color,
                "rarity_name": rarity_name,
                "fish_name": fish.fish_name,
                "count": fish.count,
                "price": fish.price,
            }
        )

    html = render_template(
        "sell_result.html",
        body_bg=gradient_bg("green"),
        width=400,
        fish_items=fish_items,
        total_gold=total_gold,
    )
    return await render_html(html, 400)


async def render_weather_forecast(
    user_id: str,
    locations: list,
    page: str = "",
) -> bytes:
    from ..config import WEATHER_EFFECT_DESC, WEATHER_EMOJI, WEATHER_NAME
    from ..models import FishingBuff, FishingUser
    from ..weather_service import get_all_location_weathers

    all_weathers = await get_all_location_weathers(user_id)

    fisher_counts = await FishingUser.get_location_fisher_counts()

    nest_counts = {}
    for loc in locations:
        count = await FishingBuff.get_location_buff_count(loc.id)
        if count > 0:
            nest_counts[loc.id] = count

    frame_bonus_by_loc = {}
    for loc in locations:
        frame_count = await FishingBuff.get_frame_buff_count_for_location(loc.id)
        frame_bonus_by_loc[loc.id] = frame_count * 5

    loc_data = []
    for i, loc in enumerate(locations, 1):
        w = all_weathers.get(loc.id)
        if w:
            wt = w.get("weather_type", "sunny")
            weather_emoji = WEATHER_EMOJI.get(wt, "☀️")
            weather_name = WEATHER_NAME.get(wt, "晴天")
            weather_time = ""
            weather_effect = ""
            is_active = w.get("is_active", False)
            weather_status = w.get("weather_status", "ended")
            if wt not in ("sunny", "chaotic_era") and w.get("start_time") and w.get("end_time"):
                st = w["start_time"]
                et = w["end_time"]
                if hasattr(st, "hour"):
                    st_str = str(st.hour) + "点"
                else:
                    st_str = str(st)
                if hasattr(et, "hour"):
                    et_hour = et.hour
                    et_str = ("24" if et_hour == 0 else str(et_hour)) + "点"
                else:
                    et_str = str(et)
                weather_time = f"{st_str}-{et_str}"
                weather_effect = WEATHER_EFFECT_DESC.get(wt, "")
        else:
            _default_wt = "chaotic_era" if is_starry_location(loc.id) else "sunny"
            weather_emoji = WEATHER_EMOJI.get(_default_wt, "☀️")
            weather_name = WEATHER_NAME.get(_default_wt, "晴天")
            weather_time = ""
            weather_effect = ""
            is_active = False
            weather_status = "ended"

        image_src = get_location_image_src(loc.name)
        fisher_count = fisher_counts.get(loc.id, 0)
        nest_count = nest_counts.get(loc.id, 0)
        nest_bonus = nest_count * 5
        frame_bonus = frame_bonus_by_loc.get(loc.id, 0)

        loc_data.append(
            {
                "num": i,
                "name": loc.name,
                "difficulty": loc.difficulty,
                "image_src": image_src,
                "weather_emoji": weather_emoji,
                "weather_name": weather_name,
                "weather_time": weather_time,
                "weather_effect": weather_effect,
                "is_active": is_active,
                "weather_status": weather_status,
                "fisher_count": fisher_count,
                "nest_bonus": nest_bonus,
                "frame_bonus": frame_bonus,
            }
        )

    title = "🌤️ 天气预报"
    if page == "2":
        title = "🌤️ 天气预报 · 星空"

    html = render_template(
        "weather_forecast.html",
        body_bg=gradient_bg("purple"),
        width=500,
        title=title,
        locations=loc_data,
    )
    return await render_html(html, 500)
