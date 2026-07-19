"""
星级颜色方案设计

设计原则：
1. 相邻等级颜色区别很大（因为经常被一起钓到）
2. 不同等级范围区别小，有渐变炫彩效果
"""

STAR_COLORS = {
    1: {"name": "★", "color": "#FF4444", "bg_color": "#FFE4E1", "description": "一星"},
    2: {"name": "★★", "color": "#FF8C00", "bg_color": "#FFF8DC", "description": "二星"},
    3: {
        "name": "★★★",
        "color": "#FFD700",
        "bg_color": "#FFFACD",
        "description": "三星",
    },
    4: {
        "name": "★★★★",
        "color": "#32CD32",
        "bg_color": "#F0FFF0",
        "description": "四星",
    },
    5: {
        "name": "★★★★★",
        "color": "#4169E1",
        "bg_color": "#E6E6FA",
        "description": "五星",
    },
    6: {
        "name": "☆",
        "color": "#9932CC",
        "bg_color": "#F5F5F5",
        "description": "一星蓝",
    },
    7: {
        "name": "☆☆",
        "color": "#FF69B4",
        "bg_color": "#FFF0F5",
        "description": "二星蓝",
    },
    8: {
        "name": "☆☆☆",
        "color": "#00CED1",
        "bg_color": "#E0FFFF",
        "description": "三星蓝",
    },
    9: {
        "name": "☆☆☆☆",
        "color": "#D2691E",
        "bg_color": "#FAEBD7",
        "description": "四星蓝",
    },
    10: {
        "name": "☆☆☆☆☆",
        "color": "#708090",
        "bg_color": "#F5F5F5",
        "description": "五星蓝",
    },
    11: {
        "name": "✦",
        "color": "#DC143C",
        "bg_color": "#FFE4E1",
        "description": "一星红",
    },
    12: {
        "name": "✦✦",
        "color": "#FF4500",
        "bg_color": "#FFE4B5",
        "description": "二星红",
    },
    13: {
        "name": "✦✦✦",
        "color": "#FFD700",
        "bg_color": "#FFFACD",
        "description": "三星红",
    },
    14: {
        "name": "✦✦✦✦",
        "color": "#00FA9A",
        "bg_color": "#F0FFF0",
        "description": "四星红",
    },
    15: {
        "name": "✦✦✦✦✦",
        "color": "#1E90FF",
        "bg_color": "#E6E6FA",
        "description": "五星红",
    },
    16: {
        "name": "◆",
        "color": "#8B008B",
        "bg_color": "#E6E6FA",
        "description": "一星紫",
    },
    17: {
        "name": "◆◆",
        "color": "#FF1493",
        "bg_color": "#FFF0F5",
        "description": "二星紫",
    },
    18: {
        "name": "◆◆◆",
        "color": "#00BFFF",
        "bg_color": "#E0FFFF",
        "description": "三星紫",
    },
    19: {
        "name": "◆◆◆◆",
        "color": "#228B22",
        "bg_color": "#F0FFF0",
        "description": "四星紫",
    },
    20: {
        "name": "◆◆◆◆◆",
        "color": "#FF6347",
        "bg_color": "#FFE4E1",
        "description": "五星紫",
    },
}


def get_star_display(stars: int) -> dict:
    return STAR_COLORS.get(stars, STAR_COLORS[1])


def get_star_name(stars: int) -> str:
    return STAR_COLORS.get(stars, STAR_COLORS[1])["name"]


def get_star_color(stars: int) -> str:
    return STAR_COLORS.get(stars, STAR_COLORS[1])["color"]


def get_star_bg_color(stars: int) -> str:
    return STAR_COLORS.get(stars, STAR_COLORS[1])["bg_color"]


if __name__ == "__main__":
    print("星级颜色方案")
    print("=" * 80)
    for stars, info in STAR_COLORS.items():
        print(
            f"{stars:2d}星: {info['name']:<20} 颜色: {info['color']} 背景: {info['bg_color']}"
        )
