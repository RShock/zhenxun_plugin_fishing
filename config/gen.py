from PIL import Image, ImageDraw

# 画布大小（与参考图一致）
W, H = 22, 61
img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 调色板（克制的日系像素配色）
skin = (255, 220, 185, 255)
hair = (255, 210, 70, 255)
hair_dark = (210, 170, 40, 255)
eye = (60, 60, 60, 255)

coat = (255, 245, 250, 255)
coat_shadow = (215, 200, 220, 255)
skirt = (55, 55, 70, 255)
sock = (240, 240, 240, 255)
shoe = (40, 40, 40, 255)

rod = (70, 55, 40, 255)
line = (180, 180, 180, 255)
accent = (220, 60, 80, 255)

# ========= 头部 =========
# 脸
d.rectangle((6, 7, 14, 15), fill=skin)

# 头发主体
d.rectangle((4, 4, 16, 10), fill=hair)
d.rectangle((3, 8, 5, 14), fill=hair)
d.rectangle((15, 8, 17, 14), fill=hair)

# 刘海
d.rectangle((5, 8, 15, 10), fill=hair_dark)

# 双马尾 / 发侧
d.rectangle((2, 9, 3, 13), fill=hair)
d.rectangle((17, 9, 18, 13), fill=hair)

# 眼睛
d.point((8, 11), fill=eye)
d.point((12, 11), fill=eye)

# ========= 身体 =========
# 上衣
d.rectangle((6, 16, 14, 25), fill=coat)
d.rectangle((6, 22, 14, 25), fill=coat_shadow)

# 红领结
d.point((10, 18), fill=accent)
d.point((9, 19), fill=accent)
d.point((11, 19), fill=accent)

# 左手
d.rectangle((4, 18, 5, 24), fill=skin)

# 右手（持竿）
d.rectangle((15, 18, 16, 23), fill=skin)

# 下装
d.rectangle((7, 26, 13, 31), fill=skirt)

# 腿
d.rectangle((8, 32, 9, 43), fill=sock)
d.rectangle((11, 32, 12, 43), fill=sock)

# 鞋
d.rectangle((7, 44, 10, 46), fill=shoe)
d.rectangle((10, 44, 13, 46), fill=shoe)

# ========= 鱼竿 =========
# 竿身（斜向上）
for i in range(10):
    d.point((16 + i // 2, 22 - i), fill=rod)

# 竿尖延长
for i in range(6):
    d.point((20, 12 - i), fill=rod)

# 鱼线
for i in range(10):
    d.point((20, 7 + i), fill=line)

# 小浮标
d.point((20, 18), fill=(255, 80, 80, 255))

# ========= 外轮廓强化 =========
outline = (45, 45, 45, 255)

# 简单描边
for x in range(W):
    for y in range(H):
        p = img.getpixel((x, y))
        if p[3] > 0:
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H:
                    if img.getpixel((nx, ny))[3] == 0:
                        img.putpixel((x, y), outline)

# 保存
img.save("pixel_fishing_girl.png")
print("已保存 pixel_fishing_girl.png")
