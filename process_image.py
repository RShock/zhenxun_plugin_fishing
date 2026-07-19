from PIL import Image

input_path = r"r:\zhenxun_bot\zhenxun\plugins\fishing\temp.png"
output_path = r"r:\zhenxun_bot\zhenxun\plugins\fishing\temp_processed.png"

img = Image.open(input_path).convert("RGBA")
pixels = img.load()

for y in range(img.height):
    for x in range(img.width):
        r, g, b, a = pixels[x, y]
        # 取亮度（用灰度值近似），RGB通道统一设为纯白
        # 如果像素不是纯白，也转为纯白，alpha 由亮度决定
        brightness = int(0.299 * r + 0.587 * g + 0.114 * b)  # 加权亮度
        pixels[x, y] = (255, 255, 255, brightness)

img.save(output_path)
print(f"处理完成: {output_path}")