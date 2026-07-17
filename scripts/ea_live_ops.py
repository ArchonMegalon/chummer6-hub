#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Sequence


DEFAULT_EA_LIVE_OPS_PATH = Path("/docker/EA/scripts/ea_live_ops.py")
EA_LIVE_OPS_SCRIPT_PATH_ENV = "EA_LIVE_OPS_SCRIPT_PATH"


def resolve_ea_live_ops_path(explicit: Path | None = None) -> Path:
    candidate = explicit
    if candidate is None:
        override = str(os.environ.get(EA_LIVE_OPS_SCRIPT_PATH_ENV) or "").strip()
        if override:
            candidate = Path(os.path.expandvars(os.path.expanduser(override)))
    return candidate or DEFAULT_EA_LIVE_OPS_PATH


def load_ea_live_ops_module(path: Path | None = None) -> ModuleType:
    path = resolve_ea_live_ops_path(path)
    if not path.is_file():
        raise FileNotFoundError(f"missing_ea_live_ops_script:{path}")
    spec = importlib.util.spec_from_file_location("external_ea_live_ops", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"ea_live_ops_module_load_failed:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: Sequence[str] | None = None) -> int:
    forwarded_argv = list(sys.argv[1:] if argv is None else argv)
    resolved_path = resolve_ea_live_ops_path()
    module = load_ea_live_ops_module(resolved_path)
    old_argv = sys.argv[:]
    sys.argv = [str(resolved_path), *forwarded_argv]
    try:
        return int(module.main())
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    raise SystemExit(main())
