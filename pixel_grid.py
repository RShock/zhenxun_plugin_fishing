"""
像素网格工具 — 为 AI 绘图生成像素校准网格

功能 1: generate_pixel_grid() — 生成 1536x1024 硬描边像素网格
功能 2: place_pixel_art()   — 将迷你像素画嵌入网格，自动对齐

每个格子 cell_size×cell_size，内部 1px 纯黑描边，
相邻格子边框自然堆叠为 2px，外缘 1px。
纯白背景，无棋盘格。

横向 1536，竖向 1024，更适合 GPT 绘图。
CLI 用法:
    python pixel_grid.py grid_16.png --cell-size 16
    python pixel_grid.py grid_32.png --cell-size 32
    python pixel_grid.py place art.png out.png --cell-size 16 --gx 4 --gy 4
"""

from pathlib import Path

from PIL import Image

WIDTH = 1536
HEIGHT = 1024

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


def generate_pixel_grid(
    output_path: str | Path,
    cell_size: int = 16,
) -> Path:
    """生成 1536x1024 硬描边像素网格

    纯白背景，每个格子内部 1px 纯黑描边。
    相邻格子边框堆叠为 2px，外缘 1px。

    参数:
        output_path: 输出路径
        cell_size:   每个格子的像素宽度（16 → 96×64 格子，32 → 48×32 格子）
    """
    cols = WIDTH // cell_size
    rows = HEIGHT // cell_size
    img = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    pixels = img.load()

    for y in range(HEIGHT):
        for x in range(WIDTH):
            is_border = (
                x % cell_size == 0
                or x % cell_size == cell_size - 1
                or y % cell_size == 0
                or y % cell_size == cell_size - 1
            )
            if is_border:
                pixels[x, y] = BLACK

    output = Path(output_path)
    img.save(output)
    return output


def place_pixel_art(
    image_path: str | Path,
    output_path: str | Path,
    cell_size: int = 16,
    grid_x: int = 0,
    grid_y: int = 0,
) -> Path:
    """将迷你像素画嵌入网格中，与网格严格对齐

    参数:
        image_path:  源图片路径
        output_path: 输出路径
        cell_size:   格子像素大小（须与网格一致）
        grid_x, grid_y: 放置的起始网格坐标，默认左上角

    源图尺寸限制：宽 ≤ WIDTH//cell_size，高 ≤ HEIGHT//cell_size。
    """
    max_cols = WIDTH // cell_size
    max_rows = HEIGHT // cell_size

    base = generate_pixel_grid(output_path, cell_size)
    img = Image.open(base)
    source = Image.open(image_path)

    if source.mode != "RGBA":
        source = source.convert("RGB")

    sw, sh = source.size
    if sw > max_cols or sh > max_rows:
        raise ValueError(
            f"源图片尺寸 {sw}x{sh} 超出限制（最大 {max_cols}x{max_rows} 像素）"
        )

    ox = grid_x * cell_size
    oy = grid_y * cell_size

    scaled = source.resize((sw * cell_size, sh * cell_size), Image.NEAREST)
    if source.mode == "RGBA":
        img.paste(scaled, (ox, oy), scaled)
    else:
        img.paste(scaled, (ox, oy))

    out = Path(output_path)
    img.save(out)
    return out


if __name__ == "__main__":
    import sys

    raw = sys.argv[1:]

    cell_size = 16
    gx, gy = 0, 0

    def pop_int(args: list[str], flag: str, default: int) -> tuple[int, list[str]]:
        for i, a in enumerate(args):
            if a == flag and i + 1 < len(args):
                val = int(args[i + 1])
                args = args[:i] + args[i + 2 :]
                return val, args
        return default, args

    cell_size, raw = pop_int(raw, "--cell-size", cell_size)
    gx, raw = pop_int(raw, "--gx", 0)
    gy, raw = pop_int(raw, "--gy", 0)

    max_cols = WIDTH // cell_size
    max_rows = HEIGHT // cell_size

    if raw and raw[0] == "place":
        src = raw[1]
        dst = raw[2] if len(raw) > 2 else "output_grid.png"
        result = place_pixel_art(src, dst, cell_size, gx, gy)
        print(f"[place] 已生成: {result}  (格子 {cell_size}px)")
    else:
        dst = raw[0] if raw else "pixel_grid.png"
        result = generate_pixel_grid(dst, cell_size)
        print(f"[grid]  已生成: {result}  (格子 {cell_size}px → {max_cols}×{max_rows} 像素画空间)")