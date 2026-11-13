"""Write dev/payload.js for demo.html from the synthetic apartment.

Run from the repo root: python dev/make_payload.py"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from custom_components.xiaomi_live_map import mapdata  # noqa: E402
from tests.synthetic import make_map  # noqa: E402

out = mapdata.build(make_map(path_rooms=((7, 1), (3, 3), (9, 3))))
full = {
    "rev": 1,
    "active": True,
    "error": None,
    "updated": None,
    "base": out["base"],
    "grid": out["grid"],
    "robot": out["robot"],
    "path_from": 0,
    "path_pts": [],
    "path_len": 0,
    "last_path": [],
    "last_ts": None,
}
(Path(__file__).parent / "payload.js").write_text(
    f"window.FULL = {json.dumps(full)};\nwindow.SIM = {json.dumps(out['path'])};\n"
)
print("wrote dev/payload.js:", len(out["path"]) // 4, "path points")
