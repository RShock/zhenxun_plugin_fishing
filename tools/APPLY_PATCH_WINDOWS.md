# Windows apply_patch 修复工具

## 问题

部分 Windows Codex 桌面环境会生成 `apply_patch.bat`。当前机器同时存在两个问题：

1. Codex 安装目录含中文和特殊括号，而生成的批处理是无 BOM 的 UTF-8；代码页 936 的 `cmd.exe` 会把可执行文件路径解码错误，报“找不到指定的路径”。
2. Windows PowerShell 5.1 通过批处理 `%*` 转发多行参数时会破坏换行或双引号，Codex 补丁引擎随后报 `The last line of the patch must be '*** End Patch'`。

`apply_patch_windows.ps1` 不重写补丁算法。它读取 Codex 生成的包装器，找到当前 `codex.exe`，按 Windows 原生命令行规则转义完整补丁参数，然后调用 Codex 自带的 `--codex-run-as-apply-patch` 引擎。

## 当前会话安装

从钓鱼插件目录运行：

```powershell
& .\tools\apply_patch_windows.ps1 -Install
```

Codex 沙箱通常会把生成的包装器目录视为工作区外路径，因此安装时可能需要批准一次外部写入。如果不希望授权，使用下方“直接使用”方式即可，功能相同。

安装后，同一 Codex 应用会话中新开的 PowerShell 会优先找到包装器目录里的 `apply_patch.ps1`，可以继续使用通常的命令名：

```powershell
$patch = @'
*** Begin Patch
*** Update File: example.txt
@@
-"old"
+"new"
*** End Patch
'@

apply_patch $patch
```

Codex 桌面应用重启或更新后可能生成新的临时包装器目录，此时重新执行一次 `-Install`。

## 不安装时直接使用

也可以直接把补丁交给仓库内脚本。这种方式只读取 Codex 包装器，不向工作区外写文件，适合新对话首先使用：

```powershell
$patch = @'
*** Begin Patch
*** Add File: patch_probe.txt
+中文与 "quotes"
*** End Patch
'@

& .\tools\apply_patch_windows.ps1 $patch
```

## 适用范围

- 面向 Windows PowerShell 5.1 和 Codex 生成的 `apply_patch.bat`。
- 依赖包装器仍包含 `codex.exe --codex-run-as-apply-patch`。
- 只解决启动路径与参数传递，不改变补丁语法、文件权限或沙箱限制。
- 脚本应作为临时兼容工具保留；Codex 上游修复 Windows 包装器后可停止安装。
