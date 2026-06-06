from __future__ import annotations

import os
from pathlib import Path


_ROOT = Path(__file__).resolve().parent
_PYTHONPATH_ENTRIES = [str(_ROOT), str(_ROOT / "scripts")]
_existing_pythonpath = [item for item in os.environ.get("PYTHONPATH", "").split(os.pathsep) if item]
for _entry in reversed(_PYTHONPATH_ENTRIES):
    if _entry not in _existing_pythonpath:
        _existing_pythonpath.insert(0, _entry)
os.environ["PYTHONPATH"] = os.pathsep.join(_existing_pythonpath)

from scripts.yaml import *  # noqa: E402,F401,F403
