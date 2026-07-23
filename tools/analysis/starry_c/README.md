# Starry Fish C Full-Space Score Scanner

高效 C 语言全量分析：`000000`–`999999` 共 100 万编号。

## 依赖编译器

优先顺序：
1. 系统 `gcc` / `clang`（若已安装）
2. 便携 TinyCC（脚本可自动下载约 0.5MB）

```powershell
# 构建
powershell -File .\build.ps1

# 运行
.\scan_starry_max_score.exe
.\scan_starry_max_score.exe --threads 4 --top 12
.\scan_starry_max_score.exe --selftest
```

## 加速手段

1. **多线程分区扫描**：把 1e6 空间均分到 N 线程
2. **热路径零堆分配**：仅栈上数字与位图
3. **6 位固定展开**：整数拆位，无 sprintf
4. **窗口位图 + 最长窗吸收**：同家族短窗被长窗吞并
5. **分数常量预装**：避免运行期查表字符串
6. **顺序遍历**：缓存友好
7. **可选 OpenMP**（GCC/Clang：`-fopenmp -DUSE_OPENMP`，当前默认 Win32 线程）

## 正确性

`--selftest` 对照 Python `score_starry_fish` 锚点：`777777` / `122221` / `222422`。
