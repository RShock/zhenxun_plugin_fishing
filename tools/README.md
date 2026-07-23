# 维护工具

本目录仅存放不参与插件运行时导入的维护工具。

| 目录 | 用途 |
|---|---|
| `simulations/` | 独立数值模拟 |
| `assets/` | 图片和像素素材处理 |
| `packaging/` | 发布归档生成 |

所有工具都应从插件根目录运行，禁止在导入时修改配置或生成文件。

```powershell
python tools/simulations/fishing_simulation.py
python tools/assets/pixel_grid.py pixel_grid.png --cell-size 16
python tools/analysis/scan_starry_max_score.py --show-features
powershell -File tools/analysis/starry_c/build.ps1
tools/analysis/starry_c/scan_starry_max_score.exe --threads 4
& .\tools\packaging\pack.ps1
```

