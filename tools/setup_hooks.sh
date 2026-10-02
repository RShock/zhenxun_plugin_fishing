#!/bin/sh
# 一键启用本地 PSD 拦截钩子
set -e
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
HOOKS_DIR="$REPO_ROOT/.githooks"
if [ ! -d "$HOOKS_DIR" ]; then
  echo "❌ 未找到 $HOOKS_DIR"
  exit 1
fi
git config core.hooksPath .githooks
echo "✅ 已设置 core.hooksPath = .githooks"
echo "   当前 hooks: $(ls -1 .githooks)"
# 同时兼容旧式 .git/hooks 复制
mkdir -p .git/hooks
cp -f .githooks/pre-commit .git/hooks/pre-commit 2>/dev/null || true
cp -f .githooks/pre-push .git/hooks/pre-push 2>/dev/null || true
chmod +x .git/hooks/pre-commit .git/hooks/pre-push 2>/dev/null || true
echo "✅ 本地钩子已安装，PSD 将永远无法提交/推送"
