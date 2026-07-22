"""???????????????"""

SHADOW_SCENE_INPUT = "-11"
SHADOW_SCENE_LOCATION_ID = "11"
SHADOW_SCENE_USER_ID = "418648118"


def get_scene_instance_id(status: dict | None, default: str = "") -> str:
    """??????????????????????????"""
    if not status:
        return str(default)
    explicit = status.get("scene_instance_id")
    if explicit:
        return str(explicit)
    location_id = str(status.get("location_id") or default)
    if status.get("shadow_scene") and location_id == SHADOW_SCENE_LOCATION_ID:
        return SHADOW_SCENE_INPUT
    return location_id
