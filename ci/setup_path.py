"""Prepare import paths for standalone plugin repository tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def setup_standalone_paths(plugin_root: Path | None = None) -> Path:
    """Make `import zhenxun.plugins.zhenxun_plugin_fishing` work in this repo."""
    root = (plugin_root or Path(__file__).resolve().parents[1]).resolve()
    runtime = root / "ci" / "runtime"
    plugins_dir = runtime / "zhenxun" / "plugins"
    link_path = plugins_dir / "zhenxun_plugin_fishing"

    plugins_dir.mkdir(parents=True, exist_ok=True)
    (runtime / "zhenxun").mkdir(parents=True, exist_ok=True)
    (runtime / "zhenxun" / "__init__.py").write_text(
        '"""Runtime namespace for CI imports."""\n', encoding="utf-8"
    )
    (plugins_dir / "__init__.py").write_text(
        '"""Runtime plugins namespace for CI imports."""\n', encoding="utf-8"
    )

    # Prefer symlink / junction; fall back to a path redirector package.
    if link_path.exists() or link_path.is_symlink():
        try:
            if link_path.is_symlink() and link_path.resolve() != root:
                link_path.unlink()
            elif link_path.is_dir() and not any(link_path.iterdir()):
                link_path.rmdir()
        except OSError:
            pass

    if not (link_path.exists() or link_path.is_symlink()):
        linked = False
        try:
            os.symlink(root, link_path, target_is_directory=True)
            linked = True
        except OSError:
            linked = False
        if not linked:
            try:
                # Windows: junction does not require admin / developer mode
                import _winapi  # type: ignore

                _winapi.CreateJunction(str(root), str(link_path))
                linked = True
            except Exception:
                linked = False
        if not linked:
            link_path.mkdir(parents=True, exist_ok=True)
            (link_path / "__init__.py").write_text(
                "import sys\n"
                f"from pathlib import Path\n"
                f"_ROOT = Path(r'''{root}''')\n"
                "if str(_ROOT) not in sys.path:\n"
                "    sys.path.insert(0, str(_ROOT))\n"
                "__path__ = [str(_ROOT)]\n",
                encoding="utf-8",
            )

    runtime_s = str(runtime)
    ci_s = str(root / "ci")
    root_s = str(root)
    for path_s in (runtime_s, ci_s, root_s):
        if path_s not in sys.path:
            sys.path.insert(0, path_s)
    return root


if __name__ == "__main__":
    p = setup_standalone_paths()
    print(f"plugin_root={p}")
    print(f"runtime={p / 'ci' / 'runtime'}")
