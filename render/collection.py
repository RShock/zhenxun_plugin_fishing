from .base import gradient_bg, render_html, render_template


async def render_collection(collection_data: list, has_utr: bool = False) -> bytes:
    legend_rarities = (
        ["UTR", "UR", "SSR", "SR", "R", "N"]
        if has_utr
        else ["UR", "SSR", "SR", "R", "N"]
    )
    locations = []
    for loc in collection_data:
        fish_list = []
        for fish in loc.get("fish", []):
            rarities = {}
            for r in legend_rarities:
                rarities[r] = {
                    "collected": fish.get("rarities", {})
                    .get(r, {})
                    .get("collected", False),
                }
            fish_list.append(
                {
                    "name": fish.get("name", fish.get("id", "")),
                    "rarities": rarities,
                    "fish_complete": fish.get("fish_complete", False),
                }
            )
        locations.append(
            {
                "id": loc.get("id", ""),
                "name": loc.get("name", ""),
                "fish": fish_list,
                "scene_complete": loc.get("scene_complete", False),
            }
        )

    html = render_template(
        "collection.html",
        body_bg=gradient_bg("purple"),
        width=480,
        legend_rarities=legend_rarities,
        locations=locations,
    )
    return await render_html(html, 520)
