# S2 星穹矿脉 · 正式像素素材

## 画风与布局

- 用户认可的主界面概念图：奶油桃色竖版卡片、棕色文字、三只猫矿工和分层矿井。正式场景从概念图的纯插画区裁出，不裁入标题、金额或按钮。
- 用户认可的图标参考：薄荷绿、淡紫、桃色、金色，深紫像素描边；图标用简洁轮廓表现设备、猫矿工和太空科技。
- 手机竖屏是主布局。矿场通栏、状态两列、工程和商店纵向排列；电脑端也保持居中的窄竖版，不使用桌面多栏。机器人生成 720px 宽竖图，字号按手机聊天缩小后的可读性设置。
- 金额、等级、进度、状态和中文说明由模板绘制，不能烘焙进素材。图片等比缩放，矿井底部人物不能被裁掉。

## 素材与映射

- `game_data.json` 当前包含 47 项本地科技（含储备项）、72 项永久科技，全部按 `key` 配备 `tech_<key>.png`，不同等级共用图标。
- `resources/images/s2/`：119 个科技图标及 17 个场景/助手/UI 素材，共 136 个运行时 PNG。普通图标 64px；`32/` 提供 135 个缩略版本；大肥鱼助手 128px，破裂星球 256px，矿场 1376×479。
- 主界面：`scene_shaft`、`icon_credits`、`icon_depth`、`icon_era`、`icon_built`；空建设状态使用 `icon_empty`。
- 突破/助手：`planet_cracked`、`helper_fatfish`、`icon_core`、`icon_depart`；大肥鱼画成戴矿工帽的鱼，不使用太空猫代替。
- 状态：`icon_locked`、`icon_ready`、`icon_wait`、`icon_celebrate`、`icon_research`、`icon_galaxy`、`icon_settings`。
- Bot 通过 `render/s2_assets.py` 读取本地 PNG 并嵌入 data URI。缺失图片是打包错误，不回退成 emoji。网页使用 `web/static/s2-vnext/assets/` 的相同 PNG，可独立作为静态站点运行。
- `resources/images/s2/manifest.json` 保存最终源批次、裁剪框、文件尺寸、SHA256 与检查状态；`tools/assets/s2_generation_prompts.json` 保存全部 9 批正式出图的完整 prompt、参考图指纹、生成记录 ID、源图指纹和裁剪规则。早期不采用的候选图不属于正式素材。

## 生成与裁剪流程

1. 先查看认可的概念图，以其确定场景与图标风格。通过 mengluo_image 的参考图编辑生成新素材，显式列出逐格主体，要求透明底和留白。
2. 查看整张出图。不能假设请求的 1024×1024 就是返回尺寸，也不能假设 4×4 一定等分。定位实际空隙后裁剪；必要时补画有歧义、跨格或截断的主体。
3. 保留透明通道，去掉孤立抠图噪点，保留轮廓和内部高光。少数生成结果会烘焙棋盘格，只对确认的中性灰背景做去底，不全局删除所有白色。
4. 在深浅背景上查看裁剪拼图，检查 64px/32px 辨识度、串格残片、白边与断边；机器人模板和试玩页中还要实际截图检查。
5. 原始大图与临时 QA 图片留在仓库外。正式 PNG、完整 prompt、清单和重复处理工具入库，不提交 PSD/PSB。

## 本地复现与检查

依赖 Pillow、NumPy、SciPy；生图由 mengluo_image 完成，下列工具不调用收费 API。

```powershell
# 从原始生成文件与主界面参考图重复导出（先检查全部输入的 SHA256）
python tools/assets/s2_assets.py build --sources <原始生图目录> --main-reference <主界面参考图.png>
# 图片完整性、32px 文件、清单指纹与网页镜像一致性
python tools/assets/s2_assets.py audit
# 修改正式 PNG 后同步独立网页目录；同时维护 manifest.json
python tools/assets/s2_assets.py sync
# 无需启动机器人或数据库，使用正式渲染函数生成主界面/突破/锁定/全部商店分页和图标图鉴
python tools/assets/s2_preview.py <仓库外验收目录>
```

- 网页验收使用 `?sandbox=1`，不推进用户主存档；至少检查 390px、320px，展开全部永久科技确认无坏图和横向溢出。
- 换星、已挖穿、无待建工程等提前返回状态必须隐藏旧的“下一项可升级”提示，防止页面保留过期提示和图标。
