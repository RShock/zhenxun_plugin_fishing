"""Build/check S2 raster assets. Never calls an image API.

The manifest records semantic keys and source rectangles, not game rules.
Keep original generations outside Git; ship only reviewed, optimized PNGs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web/static/s2-vnext"
ASSETS = ROOT / "resources/images/s2"


def expected_keys():
    data = json.loads((WEB / "game_data.json").read_text(encoding="utf-8"))
    return {s["key"]: s["name"] for s in data["upgrades"] + data["prestige"]["upgrades"]}


def remove_neutral_checkerboard(source, output):
    """For reviewed sheets with a baked neutral checkerboard, not general art.

    Seed only mid-gray neutral pixels; grow into connected white backdrop tiles.
    White highlights enclosed by colored outlines are preserved. Check the result
    on both dark and light backgrounds, especially translucent glass interiors.
    """
    import numpy as np
    from scipy import ndimage
    image = Image.open(source).convert("RGBA")
    pixels = np.asarray(image).copy()
    rgb = pixels[:, :, :3].astype(int)
    neutral = (rgb.max(2)-rgb.min(2)) < 18
    gray = neutral & (rgb.min(2)>105) & (rgb.max(2)<235)
    backdrop = ndimage.binary_propagation(gray, mask=neutral & (rgb.min(2)>105))
    pixels[backdrop,3]=0
    Image.fromarray(pixels).save(output)


def grid_rectangles(sheet, columns=4, rows=4):
    """Locate empty gutters near the nominal grid, including per-row columns."""
    import numpy as np
    from scipy.ndimage import uniform_filter1d
    alpha = np.asarray(sheet.convert("RGBA"))[:, :, 3] > 128

    def boundaries(ink, parts):
        result = [0]
        length = len(ink)
        for index in range(1,parts):
            ideal = length*index/parts
            radius = length/parts*.17
            left,right = round(ideal-radius),round(ideal+radius)
            density = uniform_filter1d(ink.astype(float),size=7)
            positions = np.arange(left,right)
            # Favor actual blank space; distance breaks ties in broad blank gutters.
            score = density[left:right]+abs(positions-ideal)*.012
            result.append(int(positions[np.argmin(score)]))
        return result+[length]

    ys=boundaries(alpha.sum(axis=1),rows)
    rectangles=[]
    for top,bottom in zip(ys,ys[1:]):
        xs=boundaries(alpha[top:bottom].sum(axis=0),columns)
        rectangles.extend([[left,top,right,bottom] for left,right in zip(xs,xs[1:])])
    return rectangles


def cut_sheet(source, keys, output, rectangles=None, columns=4, rows=4, prefix="tech_"):
    """Cut a reviewed 4x4 sheet. Explicit rectangles override equal cells.

    Preserve source alpha, retain padding, and reject nontransparent sources:
    global white removal would erase white fur and metal highlights.
    """
    sheet = Image.open(source).convert("RGBA")
    if sheet.getchannel("A").getextrema()[0] == 255:
        raise ValueError("Source lacks transparency; remove its background before cutting")
    if rectangles is None:
        rectangles = grid_rectangles(sheet,columns,rows)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for index, key in enumerate(keys):
        col, row = index % columns, index // columns
        rect = rectangles[index] if rectangles else [
            round(col * sheet.width / columns), round(row * sheet.height / rows),
            round((col + 1) * sheet.width / columns), round((row + 1) * sheet.height / rows),
        ]
        tile = sheet.crop(rect)
        # Remove isolated background extraction specks; keep detached sprite parts.
        # Preview on light AND dark backgrounds is still required after this pass.
        import numpy as np
        from scipy import ndimage
        pixels = np.array(tile)
        labels, count = ndimage.label(pixels[:, :, 3] >= 96)
        sizes = np.bincount(labels.ravel())
        threshold = max(32, max(sizes[1:], default=0) * .006)
        keep_ids = np.flatnonzero(sizes >= threshold)
        keep_ids = keep_ids[keep_ids != 0]
        keep = np.isin(labels, keep_ids)
        # Retain the one-pixel antialiased boundary of each accepted component.
        keep = ndimage.binary_dilation(keep, iterations=1)
        pixels[~keep, 3] = 0
        # Remove only near-white matte connected to the transparent exterior.
        # Enclosed white fur and highlights remain intact.
        rgb = pixels[:, :, :3].astype(int)
        pale = (rgb.min(axis=2) > 225) & ((rgb.max(axis=2)-rgb.min(axis=2)) < 24)
        exterior = pixels[:, :, 3] == 0
        matte = ndimage.binary_propagation(exterior, mask=exterior | pale)
        pixels[matte, 3] = 0
        tile = Image.fromarray(pixels)
        # Ignore almost transparent noise, but preserve antialiasing of the subject.
        bbox = tile.getchannel("A").point(lambda a: 255 if a >= 24 else 0).getbbox()
        if not bbox:
            raise ValueError(f"Empty tile: {key}")
        touching = bbox[0] < 2 or bbox[1] < 2 or bbox[2] > tile.width - 2 or bbox[3] > tile.height - 2
        subject = tile.crop(bbox)
        for size in (64, 32):
            scaled = subject.copy()
            scaled.thumbnail((round(size * .875), round(size * .875)), Image.Resampling.NEAREST)
            icon = Image.new("RGBA", (size, size))
            icon.alpha_composite(scaled, ((size-scaled.width)//2, (size-scaled.height)//2))
            target = output if size == 64 else output / "32"
            target.mkdir(parents=True, exist_ok=True)
            icon.save(target / f"{prefix}{key}.png", optimize=True)
        if key in ("planet_cracked", "helper_fatfish"):
            size = 256 if key == "planet_cracked" else 128
            subject.thumbnail((size-16,size-16), Image.Resampling.NEAREST)
            icon = Image.new("RGBA",(size,size))
            icon.alpha_composite(subject,((size-subject.width)//2,(size-subject.height)//2))
            icon.save(output/f"{prefix}{key}.png",optimize=True)
        records.append({"key": key, "rect": rect, "subject_bbox": list(bbox), "edge_warning": touching})
    return records


def sync_web():
    """The demo can be served on its own, so package identical local PNGs."""
    target = WEB / "assets"
    target.mkdir(exist_ok=True)
    for source in ASSETS.glob("*.png"):
        shutil.copy2(source,target/source.name)


def rebuild(sources, main_reference):
    """Recreate reviewed exports from original generations, with no API calls."""
    plan=json.loads((Path(__file__).with_name("s2_generation_prompts.json")).read_text(encoding="utf-8"))
    sources=Path(sources)
    main_reference=Path(main_reference)
    inputs=[(sources/b["sourceFile"],b["sourceSha256"]) for b in plan["batches"]]
    inputs.append((main_reference,plan["scene"]["referenceSha256"]))
    # Validate all originals before overwriting any export.
    for path,expected in inputs:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError(f"Source hash mismatch: {path}")
    ASSETS.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="s2-matte-") as temporary:
        for batch in plan["batches"]:
            source=sources/batch["sourceFile"]
            if batch.get("matte")=="neutral_checkerboard":
                cleaned=Path(temporary)/batch["sourceFile"]
                remove_neutral_checkerboard(source,cleaned)
                source=cleaned
            cut_sheet(source,batch["keys"],ASSETS,rectangles=batch["rectangles"],prefix=batch["prefix"])
    scene=plan["scene"]
    with Image.open(main_reference) as im:
        im.crop(scene["rect"]).resize(tuple(scene["size"]),Image.Resampling.LANCZOS).save(ASSETS/"scene_shaft.png",optimize=True)
    sync_web()


def contact_sheet(folder, output):
    files = sorted(Path(folder).glob("*.png"))
    if not files:
        raise ValueError("No PNGs to preview")
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = ImageFont.truetype(str(font_path), 12) if font_path.exists() else ImageFont.load_default()
    canvas = Image.new("RGB", (960, ((len(files)+5)//6)*140), "#f4e8d4")
    draw = ImageDraw.Draw(canvas)
    for i, file in enumerate(files):
        x, y = i % 6 * 160, i // 6 * 140
        draw.rectangle((x+80,y,x+159,y+105), fill="#233648")
        icon = Image.open(file).convert("RGBA")
        icon.thumbnail((72,88), Image.Resampling.NEAREST)
        canvas.paste(icon, (x+4, y+8), icon)
        canvas.paste(icon, (x+84, y+8), icon)
        label = file.stem.removeprefix("tech_")
        draw.text((x+3,y+108), label[:22], fill="#263530", font=font)
        if len(label)>22:
            draw.text((x+3,y+123),label[22:],fill="#263530",font=font)
    canvas.save(output)


def audit():
    missing, invalid = [], []
    for key in expected_keys():
        for size, folder in ((64,ASSETS),(32,ASSETS/"32")):
            path = folder / f"tech_{key}.png"
            if not path.exists():
                missing.append(str(path.relative_to(ROOT)))
                continue
            with Image.open(path) as im:
                if im.mode != "RGBA" or im.size != (size,size) or not im.getbbox():
                    invalid.append(str(path.relative_to(ROOT)))
    manifest_path = ASSETS / "manifest.json"
    if not manifest_path.exists():
        missing.append("manifest.json")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name,metadata in manifest["files"].items():
            source, mirror = ASSETS/name, WEB/"assets"/name
            if not source.exists() or not mirror.exists():
                missing.append(name)
            elif hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(mirror.read_bytes()).digest():
                invalid.append(f"Web mirror differs: {name}")
            elif hashlib.sha256(source.read_bytes()).hexdigest()!=metadata["sha256"]:
                invalid.append(f"Manifest differs: {name}")
        for name,expected in manifest.get("thumbnails",{}).items():
            path=ASSETS/"32"/name
            if not path.exists():
                missing.append(f"32/{name}")
            elif hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                invalid.append(f"Thumbnail differs: {name}")
    print(json.dumps({"technology_count":len(expected_keys()),"missing":missing,"invalid":invalid},ensure_ascii=False,indent=2))
    return bool(missing or invalid)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command",required=True)
    commands.add_parser("audit")
    commands.add_parser("sync")
    build=commands.add_parser("build")
    build.add_argument("--sources",required=True,type=Path)
    build.add_argument("--main-reference",required=True,type=Path)
    preview = commands.add_parser("preview")
    preview.add_argument("folder")
    preview.add_argument("output")
    args = parser.parse_args()
    if args.command == "audit":
        raise SystemExit(audit())
    if args.command == "sync":
        sync_web()
    elif args.command == "build":
        rebuild(args.sources,args.main_reference)
    else:
        contact_sheet(args.folder,args.output)
