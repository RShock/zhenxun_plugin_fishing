# S2 星穹矿脉 · 样式参考图与空白占位说明

> **策略**：所有 AI 生成的图像仅作为**参考图（reference）**，不直接打包进代码/资源。使用 **emoji / 空白图** 占位，保证后续可控的像素小图标自行绘制与切片，避免随机性导致的线上不一致。
> 参考图已选定 3 张，保存在项目外的预览区，提示词（prompt）原文归档于此，便于后续按需复刻或手工重绘。

---

## 1. 占位规则

- **代码层**：所有科技 icon、先行效果、星球突破图，渲染时使用 `emoji` 或 `data:image/svg+xml` 空白占位（`⬜` / `⛏️` / `🐱` / `💎` 等），字体走 `HYPixel11pxU-2`，与钓鱼主游戏、S1 猫乐园一致。
- **资源层**：`resources/images/s2/` 预留透明 `32×32` 与 `64×64` 两级切片，后续由 `tools/assets/pixel_grid.py` 批量切分。当前不提交任何 AI 直出 png。
- **文档层**：本文件为唯一对照表，后续手工 icon 需标注 `key → emoji → 正式像素名` 的映射。

---

## 2. 已选参考图与生成 Prompt（自然语言）

### A. 主矿场卡（已选） — `style_mining_main.png`

**用途**：`【挖矿】` 主界面，`720px` 宽，`gradient_bg("peach")`。

**Prompt 原文**：
> Pixel art QQ bot game UI card, 720px wide, peach gradient background (#ffecd2 to #fcb69f), HYPixel pixel font style, Chinese game "星穹矿脉". Top scene: small pixel mining shaft cross-section with cat miners, layered rock strata. Stats grid: 矿币 ◆ 42,580 ( +1,240/分 ), 深度 3.2km / 6.0km (53%), 时代 工业时代, 已建 12级. Large horizontal progress bar green. Next project card "分岔矿道 Lv3" with upgrade button "+1 级". Bottom hint "发送【挖矿】查看收益". Clean, soft shadows, rounded corners, pixelated but modern. No photograph, pure UI mockup.

**占位映射**：
| 位置 | 现用 emoji | 后续像素名 | 备注 |
|---|---|---|---|
| 顶部场景 | ⛏️🐱 | `s2/scene_shaft.png` | 3 猫矿工 + 三竖井，后续改为全图 `1376×768` 等比缩放，与猫乐园大地图一致 |
| 矿币 | 💎 / ◆ | `s2/icon_credits.png` | 黄色菱形 |
| 深度 | ⛏️ | `s2/icon_depth.png` | 青色镐头，显示 `3.2km/6.0km (53%)` |
| 时代 | ⚙️ | `s2/icon_era.png` | 齿轮 |
| 已建 | 🔨 | `s2/icon_built.png` | 锤子 |
| 下一项 | 🪨 | `s2/tech_split_tunnel.png` | 分岔矿道 Lv3，32px 切片 |
| 按钮 | — | `+1 级` 橙色圆角 | `cat_park.py` 的 `can-build` 绿色高亮复刻 |

---

### B. 星球挖穿卡（已选） — `style_planet_breakthrough.png`

**用途**：`下一个星球` 前 5 颗手动提示，`720px` 宽，深空渐变。

**Prompt 原文**：
> Pixel art planet breakthrough UI card, 720px wide, deep space starry gradient background (dark navy to purple), pixel font, Chinese. Center large pixel planet cracked with light burst, text "☆ 第 3 颗星球 已挖穿！" golden. Stats "本次耗时 1天 4小时 | 获得 3 星球核心 ◎". Big green button "下一个星球 →". Hint below "前5颗需手动启程，之后自动". Small helper status "大肥鱼助手：自动购买中". Rounded card, soft glow, pixel art but clean UI, QQ bot image style.

**占位映射**：
| 位置 | 现用 emoji | 后续像素名 |
|---|---|---|
| 破裂星球 | 🪐💥 | `s2/planet_cracked.png`，带环+裂纹+光柱 |
| 太空猫 | 🐱‍🚀 | 右上 `s2/helper_fatfish.png` |
| 核心奖励 | ◎ | `s2/icon_core.png` |
| 主按钮 | 🐟➡️ | `下一个星球` 绿色像素钮 |
| 脚注 | — | 灰字 `前5颗需手动启程，之后自动`，参考 `s2-vnext/style.css` `.departure-panel small` |

---

### C. Icon 精灵表（已选） — `style_icon_sheet.png`

**用途**：40 项本星科技 + 82 项永久科技的小图标来源，`64×64` 预生成、`32×32` 切片。

**Prompt 原文**：
> Pixel art icon sprite sheet, transparent background, 4x4 grid of 16 small mining tech icons, each 64x64px isolated, pixel style, pastel palette. Icons: rotary pickaxe, split tunnel (forked road), cat miner (small cat with helmet), honed edge (sharpened blade), ore ledger (book), fault mapping (cracked rock), deep marker (ruler), steam drill array (steam engine), cat whistle, impact hammer, blast charge (dynamite), relay shift (three cats passing), drill momentum (spinning drill), teamwork (paw prints), arc pick (electric pick), weakpoint scope (target). All with subtle shading, 1px outline, small size suitable for 32px display. Clean, no background, no text, centered grid with spacing.

**占位映射（示例 16 → 扩展到 40+）**：
| tech key | emoji 占位 | 中文名 | 切片名 |
|---|---|---|---|
| rotary_pick | ⛏️ | 手工矿镐 | `s2/tech_rotary_pick.png` |
| split_tunnel | 🛤️ | 分岔矿道 | `s2/tech_split_tunnel.png` |
| cat_crew | 🐱⛑️ | 猫矿工小队 | `s2/tech_cat_crew.png` |
| honed_edge | 🔪 | 精磨镐刃 | `s2/tech_honed_edge.png` |
| ore_ledger | 📒 | 矿石账本 | `s2/tech_ore_ledger.png` |
| fault_mapping | 🪨 | 裂隙测绘 | `s2/tech_fault_mapping.png` |
| deep_marker | 📏 | 深层标尺 | `s2/tech_deep_marker.png` |
| steam_array | 🚂 | 蒸汽钻列 | `s2/tech_steam_array.png` |
| crew_whistle | 🪈 | 猫班汽笛 | `s2/tech_crew_whistle.png` |
| impact_hammer | 🔨 | 冲击锤头 | `s2/tech_impact_hammer.png` |
| blast_charge | 🧨 | 定向爆破 | `s2/tech_blast_charge.png` |
| relay_shift | 🐈‍⬛🐈‍⬛ | 三班接力 | `s2/tech_relay_shift.png` |
| drill_momentum | 🌀 | 钻进动量 | `s2/tech_drill_momentum.png` |
| union_rhythm | 🐾 | 齐心协力 | `s2/tech_union_rhythm.png` |
| arc_pick | ⚡⛏️ | 电弧矿镐 | `s2/tech_arc_pick.png` |
| weakpoint_scope | 🎯 | 弱点示波器 | `s2/tech_weakpoint_scope.png` |

> 完整 40 项本星 + 82 项永久科技按此表扩展，**不在代码中硬编码 AI 图片 URL**，全部走 `get_s2_icon_src(key)` → `resources/images/s2/tech_*.png` → 不存在时回退到 emoji。

**后续重绘提示词模板**（给美术/AI 二次出图用，透明底，像素风，Pastel 低饱和）：
> `pixel art icon, 64x64, transparent background, pastel palette (#f7c7a3, #a8d8ea, #d8b4fe, #b8e6c2), 1px dark outline, soft shading, [主体描述], suitable for 32px display, no text`

---

## 3. 商店页（未选，需重绘）

首版商店 6 宫格因字小被跳过，后续将直接复用 `cat_park.py` 的 `row.can-build` 行列表（而非宫格），每页 6 行，含 `编号/名称/Lv/价格/不可购原因`，已在 `doc/s2设计/星穹矿脉/vnext/GAME_DESIGN_VNEXT.md` 确认。

提示词待定，沿用 A/B 的画风占位，不额外生成 AI 图。

---

## 4. 约定

- **参考图不进 git**：`style_*.png` 保留在本地预览与本文件，`.gitignore` 已覆盖 `*.psd`，后续 `resources/images/s2/` 只接受手绘或板绘后的 `png`。
- **先 emoji，后像素**：上线前全部 UI 用 emoji 验证文案与布局，像素图到齐后只需替换 `icon_src`，不改 HTML 结构。
- **科技描述不绘图**：`game_data.json` 的 `description` 含公式型文案（例：`额外收入 +0.25`），评估后决定不在图中重复数值，仅画 `Lv/价格/状态色`。
