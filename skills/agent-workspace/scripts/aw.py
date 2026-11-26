#!/usr/bin/env python3
"""统一入口：按当前项目的 .aw/config.json / 布局选择 workspace 或 single 后端。

用户只需要记 python aw.py ...；实际执行：

  workspace -> aw_workspace.py
  single    -> aw_single.py

后端仍保留独立文件，语义不混在一起。
"""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path


def _find_config(start: Path) -> Path | None:
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / ".aw" / "config.json"
        if candidate.is_file():
            return candidate
    return None


def _read_config(path: Path | None) -> dict:
    if not path:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _arg_value(args: list[str], name: str) -> str:
    for i, item in enumerate(args):
        if item == name and i + 1 < len(args):
            return args[i + 1]
        if item.startswith(name + "="):
            return item.split("=", 1)[1]
    return ""


def _is_single(args: list[str], start: Path) -> bool:
    # init 还没有 config：带 --code-root/--docs-root 的是 single init
    if "init" in args:
        if _arg_value(args, "--code-root") or _arg_value(args, "--docs-root"):
            return True
        return False
    config_arg = _arg_value(args, "--config")
    config = Path(config_arg).expanduser() if config_arg else _find_config(start)
    if config and config.is_dir():
        candidate = config / ".aw" / "config.json"
        config = candidate if candidate.is_file() else config / "config.json"
    data = _read_config(config)
    if str(data.get("profile") or "").lower() == "single":
        return True
    if config and "code_root" in data and "docs_root" in data:
        return True
    return False


def _normalize_single_args(args: list[str], config: Path | None) -> list[str]:
    """把统一入口的 --repo 翻译成 single 的 --config。"""
    out: list[str] = []
    i = 0
    while i < len(args):
        item = args[i]
        if item == "--repo" and i + 1 < len(args):
            root = Path(args[i + 1]).resolve()
            out.extend(["--config", str(root / ".aw" / "config.json")])
            i += 2
            continue
        if item.startswith("--repo="):
            root = Path(item.split("=", 1)[1]).resolve()
            out.extend(["--config", str(root / ".aw" / "config.json")])
            i += 1
            continue
        out.append(item)
        i += 1
    return out


def main() -> int:
    args = sys.argv[1:]
    start = Path(_arg_value(args, "--repo") or ".").resolve()
    single = _is_single(args, start)
    scripts = Path(__file__).resolve().parent
    backend = scripts / ("aw_single.py" if single else "aw_workspace.py")
    if single:
        args = _normalize_single_args(args, _find_config(start))
    sys.argv = [str(backend), *args]
    try:
        runpy.run_path(str(backend), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
