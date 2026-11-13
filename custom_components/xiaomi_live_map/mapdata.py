"""Turn the robot's cloud map file into a compact payload for the card. No Home Assistant imports."""

from __future__ import annotations

import base64
import binascii
from contextlib import suppress
import hashlib
import json
from typing import Any
import zlib


class UnsupportedMapError(Exception):
    """The map file is not the JSON format this integration understands."""


def decode(raw: bytes, model: str, did: str) -> dict[str, Any]:
    """Decrypt the cloud map file, the same way Xiaomi Cloud Map Extractor's Xiaomi connector does."""
    from vacuum_map_parser_xiaomi.aes_decryptor import decrypt  # noqa: PLC0415 - heavy import, only when needed

    # Older firmware wraps the encrypted bytes in {"data": "<base64>"}; newer firmware sends them as they are.
    with suppress(ValueError, KeyError, TypeError, UnicodeDecodeError, binascii.Error):
        raw = base64.decodebytes(json.loads(raw)["data"].encode("latin1"))
    try:
        data = json.loads(decrypt(raw.hex(), model.replace("xiaomi", "mi"), did))
    except Exception as err:
        raise UnsupportedMapError(f"Could not decrypt the map file ({type(err).__name__})") from err
    if not isinstance(data, dict) or "map_data" not in data or "width" not in data:
        raise UnsupportedMapError("The map file is not in the JSON grid format this integration reads")
    return data


def _pose(x: float, y: float, yaw: float | None) -> dict[str, float]:
    # yaw is in milliradians (1571 = 90 degrees, pointing +y)
    return {"x": x, "y": y, "yaw": (yaw or 0) / 1000.0}


def build(p: dict[str, Any]) -> dict[str, Any]:
    """Compact payload: static map ("base" + "grid"), robot pose and the path as flat [x, y, type, mode, ...]."""
    w, h = int(p["width"]), int(p["height"])
    try:
        grid = zlib.decompress(base64.b64decode(p["map_data"]))
    except (binascii.Error, zlib.error, TypeError) as err:
        raise UnsupportedMapError("The map grid could not be unpacked") from err
    if len(grid) < w * h:
        raise UnsupportedMapError("The map grid is smaller than its stated size")

    colors = {}
    for r in p.get("map_room_info") or []:
        if isinstance(r, dict) and r.get("grid_id") is not None:
            colors[int(r["grid_id"])] = r.get("color")
    rooms = []
    for r in p.get("room_attrs") or []:
        if not isinstance(r, dict) or r.get("id") is None or r.get("notshow"):
            continue
        rid = int(r["id"])
        rooms.append(
            {
                "id": rid,
                "name": r.get("room_name") or "",
                "x": r.get("name_pos_x"),
                "y": r.get("name_pos_y"),
                "color": colors.get(rid),
            }
        )
    carpets3d = (p.get("map_3d_info") or {}).get("carpets") or []
    carpets = [c.get("p_3d") or c.get("p") for c in (carpets3d or p.get("carpets") or []) if isinstance(c, dict)]
    vwalls = [v.get("wall_points") for v in p.get("fb_walls") or [] if isinstance(v, dict) and v.get("wall_points")]
    regions = []
    for a in p.get("fb_regions") or []:
        if isinstance(a, dict) and a.get("points"):
            pts: list[float] = []
            for pt in a["points"]:
                pts += [pt.get("x", 0), pt.get("y", 0)]
            regions.append({"type": a.get("type"), "p": pts})
    cfg = p.get("current_cleaning_config") or {}
    zones = [
        [z.get("x1"), z.get("y1"), z.get("x2"), z.get("y2")] for z in cfg.get("zones") or [] if isinstance(z, dict)
    ]
    base = {
        "w": w,
        "h": h,
        "res": p.get("resolution", 50),
        "ox": p.get("origin_x", 0),
        "oy": p.get("origin_y", 0),
        "grid_rev": hashlib.sha1(grid + f"{w}x{h}".encode()).hexdigest()[:12],
        "rooms": rooms,
        "carpets": [c for c in carpets if c],
        "vwalls": vwalls,
        "regions": regions,
        "zones": zones,
        "charger": _pose(p.get("pile_x", 0), p.get("pile_y", 0), p.get("pile_yaw")) if p.get("have_pile") else None,
    }
    pos = p.get("position")
    robot = _pose(pos.get("x", 0), pos.get("y", 0), pos.get("yaw")) if isinstance(pos, dict) else None
    paths = p.get("paths")
    src = paths.get("points") if isinstance(paths, dict) else paths if isinstance(paths, list) else []
    raw_points = [q for q in src or [] if isinstance(q, dict)]
    path: list[int] = []
    for q in raw_points:
        path += [q.get("x", 0), q.get("y", 0), q.get("type", 0), q.get("sweep_mop_mode", -1)]
    return {"base": base, "grid": base64.b64encode(grid[: w * h]).decode(), "robot": robot, "path": path}


def summary(p: dict[str, Any]) -> dict[str, Any]:
    """Non-geometric facts about a decoded map, for diagnostics."""
    paths = p.get("paths")
    src = paths.get("points") if isinstance(paths, dict) else paths if isinstance(paths, list) else []
    kinds: dict[str, int] = {}
    for q in src or []:
        if isinstance(q, dict):
            key = f"type={q.get('type')} mode={q.get('sweep_mop_mode')}"
            kinds[key] = kinds.get(key, 0) + 1
    cfg = p.get("current_cleaning_config") or {}
    return {
        "keys": sorted(p),
        "size": [p.get("width"), p.get("height"), p.get("resolution")],
        "rooms": len(p.get("room_attrs") or []),
        "path_points": sum(kinds.values()),
        "path_kinds": kinds,
        "cleaning_config": {k: v for k, v in cfg.items() if k != "zones"} if isinstance(cfg, dict) else None,
    }


def decode_and_build(raw: bytes, model: str, did: str) -> tuple[dict[str, Any], dict[str, Any]]:
    decoded = decode(raw, model, did)
    return build(decoded), summary(decoded)
