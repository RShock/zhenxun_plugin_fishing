"""Render deterministic S2 artwork fixtures without starting the bot or touching saves.

Usage: python tools/assets/s2_preview.py OUTPUT_DIRECTORY
The production renderer functions run with a small isolated data provider;
only DB/economy inputs and final screenshot service are replaced for fixtures.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name,path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


async def build_previews(output):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    for name in ("_s2_art_preview", "_s2_art_preview.render"):
        package = types.ModuleType(name); package.__path__ = []
        sys.modules[name] = package
    assets = module("_s2_art_preview.render.s2_assets",ROOT/"render/s2_assets.py")
    data = json.loads((ROOT/"web/static/s2-vnext/game_data.json").read_text(encoding="utf-8"))
    env = Environment(loader=FileSystemLoader(ROOT/"templates"),autoescape=True)
    base = types.ModuleType("_s2_art_preview.render.base")
    base.gradient_bg = lambda _: "linear-gradient(135deg,#ffecd2,#fcb69f)"
    base.render_template = lambda name,**context: env.get_template(name).render(**context)
    async def html_result(html,width):
        return html
    base.render_html = html_result
    sys.modules[base.__name__] = base
    provider = types.ModuleType("_s2_art_preview.s2_mining")
    rows = [dict(idx=i+1,key=s["key"],name=s["name"],lv=i%4,max=s["maxLevel"],cost=760+i*100,
                 can=i%3==0,unlocked=True,reason="可购买" if i%3==0 else "矿币不足",era="工业时代")
            for i,s in enumerate(data["upgrades"]) if s["status"]=="active"]
    provider._load_game_data = lambda: data
    provider._shop_entries = lambda state: rows
    provider._income_rate = lambda state: 1240
    provider._depth_rate = lambda state: 40
    provider._cost_for = provider._available = lambda *args: 0
    sys.modules[provider.__name__] = provider
    renderer = module("_s2_art_preview.render.s2_mining",ROOT/"render/s2_mining.py")
    state = dict(planet=3,completedPlanets=2,s2_unlocked=True,credits=42580,
                 depth=3200,targetDepth=6000,totalBuilt=12,autoUnlocked=["rotary_pick"],
                 planetComplete=False,helperEnabled=True,cores=3,startTime=0,lastTick=1000)
    fixtures = {}
    fixtures["main"] = await renderer.render_mining_main(state,{"first":True})
    fixtures["breakthrough"] = await renderer.render_mining_main({**state,"planetComplete":True,"depth":6000}, {})
    fixtures["locked"] = await renderer.render_mining_main({**state,"s2_unlocked":False}, {})
    pages = (len(rows)+5)//6
    for page in range(pages):
        fixtures[f"shop-{page+1}"] = await renderer.render_shop_with_total(state,rows[page*6:page*6+6],page+1,pages,len(rows))
    for name,html in fixtures.items():
        (output/f"{name}.html").write_text(html,encoding="utf-8")
    # Every local/permanent icon, at its actual 32px and 64px delivery sizes.
    cards=[]
    for spec in data["upgrades"]+data["prestige"]["upgrades"]:
        src=assets.get_s2_icon_src(spec["key"])
        cards.append(f'<article><img width="64" height="64" src="{src}"><img width="32" height="32" src="{src}"><p>{spec["name"]}</p><small>{spec["key"]}</small></article>')
    html='<!doctype html><meta charset="utf-8"><style>body{background:#f9e5cf;font:14px sans-serif;margin:20px}main{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}article{background:#fff8eb;padding:12px;border-radius:8px}img{image-rendering:pixelated;object-fit:contain}small{font-size:10px}</style><h1>S2 素材验收 · 119 科技</h1><main>'+''.join(cards)+'</main>'
    (output/"catalog.html").write_text(html,encoding="utf-8")
    print(f"Rendered {len(fixtures)} production template fixtures and complete catalog in {output}")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    asyncio.run(build_previews(parser.parse_args().output))
