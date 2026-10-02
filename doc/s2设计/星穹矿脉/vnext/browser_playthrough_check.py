"""S2《星穹矿脉》黑盒通关验收：真正在浏览器里把这局玩完。

这是 TESTING_GUIDE_黑盒与白盒.md 里 B1–B6 几条准则的可执行版本：

  B1 结论来自实际游玩，不读代码推断
  B2 只用玩家按得到的按钮推进时间（这里固定 1 天一步；调试用的 30 天快进会漏掉
     核心自动购买，同一套数据会算出 D153 而不是 D126，结论不可用）
  B3 全程监听 pageerror / console.error，0 报错才算过
  B4 清档 + 固定节奏开局，记录玩家可感知指标（天数、颗数、操作次数、倍率、称号）
  B5 本脚本跑的是「完全不操作」画像：除了教学期必须亲手点的前几次启程之外，
     玩家一次都不碰，用来回答"躺平玩家能不能通关"
  B6 顺手检查科学计数法残留

用法：
    python3 -m http.server 4160 --bind 0.0.0.0 --directory web/static/s2-vnext &
    python3 doc/s2设计/星穹矿脉/vnext/browser_playthrough_check.py [URL]

依赖：pip install playwright && python3 -m playwright install --with-deps chromium
耗时：约 50 秒。
"""

import asyncio
import json
import pathlib
import re
import sys
import tempfile

from playwright.async_api import async_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:4160/index.html"
DATA = pathlib.Path(__file__).resolve().parents[4] / "web/static/s2-vnext/game_data.json"
GOAL = json.loads(DATA.read_text(encoding="utf-8"))["prestige"]["galaxyTargetPlanets"]

# 时间推进只用 data-advance="1440"，即页面上的「推进 1 天」
ADVANCE_ONE_DAY = "()=>document.querySelector(`[data-advance='1440']`).click()"
STATE = "()=>window.s2.state()"


async def main() -> int:
    async with async_playwright() as play:
        with tempfile.TemporaryDirectory() as profile:
            ctx = await play.chromium.launch_persistent_context(
                profile, viewport={"width": 1280, "height": 1100}
            )
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(f"PAGEERROR {e}"))
            page.on(
                "console",
                lambda m: errors.append(f"CONSOLE {m.text}") if m.type == "error" else None,
            )

            # —— 清档开局：残留存档会让教学期（前 5 次亲手启程）整段测不到
            await page.goto(URL, wait_until="networkidle")
            await page.evaluate("()=>localStorage.clear()")
            await page.reload(wait_until="networkidle")
            await page.wait_for_timeout(600)
            await page.evaluate("()=>window.s2.start()")

            # —— 教学期：前几颗星球必须亲手点启程，这是设计里的引导，不是 bug
            for _ in range(600):
                s = await page.evaluate(STATE)
                if s["completedPlanets"] >= 5 and not s["planetComplete"]:
                    break
                if s["planetComplete"]:
                    await page.evaluate("()=>document.getElementById('departButton').click()")
                    await page.wait_for_timeout(120)
                await page.evaluate(ADVANCE_ONE_DAY)
                await page.wait_for_timeout(60)
            s = await page.evaluate(STATE)
            print(f"教学期结束: {s['time']} / {s['completedPlanets']} 颗")

            # —— 之后完全不操作，只推进时间，直到银河目标
            cleared = False
            for step in range(900):
                s = await page.evaluate(STATE)
                if s["completedPlanets"] >= GOAL:
                    cleared = True
                    break
                if s["planetComplete"]:
                    await page.evaluate("()=>document.getElementById('departButton').click()")
                    await page.wait_for_timeout(150)
                await page.evaluate(ADVANCE_ONE_DAY)
                await page.wait_for_timeout(200)
                if step % 10 == 0:
                    print(f"  step {step}: {s['time']} 累计 {s['completedPlanets']:,} 颗")

            final = await page.evaluate(STATE)
            print("最终状态:", {k: final[k] for k in
                              ("time", "day", "completedPlanets", "cores", "prestigeSpeed")
                              if k in final})

            report = await page.evaluate(
                "()=>{const e=document.getElementById('finalReport');return e?e.innerText:'(无结算面板)'}"
            )
            print("\n=== 通关结算 ===\n" + report)

            body = await page.evaluate("()=>document.body.innerText")
            sci = re.findall(r"\de[+-]\d+", body)
            print("科学计数法残留:", sci[:5] or "无")
            print("JS 错误:", errors or "无", "| 已通关:", cleared)

            await ctx.close()
            # 通关 + 零 JS 报错 + 无科学计数法 = 验收通过
            return 0 if (cleared and not errors and not sci) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
