"""A made-up apartment in the robot's map file format, for tests and the demo page. Not a real home."""

from __future__ import annotations

import base64
import json
from typing import Any
import zlib

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from vacuum_map_parser_xiaomi.aes_decryptor import gen_md5_key

MODEL = "xiaomi.vacuum.test01"
DEVICE_ID = "123456789"
IV = b"ABCDEF1234123412"

W, H, RES = 120, 90, 50  # cells, mm per cell
OX, OY = -3000, -2000  # world position of cell (0, 0), mm

# id, name, colour index, cell rectangle (x0, y0, x1, y1) inclusive
ROOMS = [
    (3, "Kitchen", 2, (6, 50, 40, 82)),
    (4, "Bedroom", 4, (72, 50, 112, 82)),
    (7, "Living room", 1, (6, 8, 70, 47)),
    (8, "Bathroom", 3, (42, 50, 69, 82)),
    (9, "Study", 5, (73, 8, 112, 47)),
]
# cell rectangle of each doorway, and the room it belongs to
DOORS = [((20, 48, 26, 49), 7), ((52, 48, 58, 49), 7), ((71, 20, 72, 28), 9), ((84, 48, 90, 49), 9)]
# where the robot crosses between two rooms (cell coordinates)
TRANSIT = {
    frozenset((7, 3)): (23, 48.5),
    frozenset((7, 8)): (55, 48.5),
    frozenset((7, 9)): (71.5, 24),
    frozenset((9, 4)): (87, 48.5),
}
DOCK = (58, 8)


def world(cx: float, cy: float) -> tuple[int, int]:
    return round(OX + (cx + 0.5) * RES), round(OY + (cy + 0.5) * RES)


def _grid() -> bytearray:
    g = bytearray(W * H)
    for rid, _name, _color, (x0, y0, x1, y1) in ROOMS:
        for y in range(y0 - 1, y1 + 2):
            for x in range(x0 - 1, x1 + 2):
                g[y * W + x] = 1 if g[y * W + x] in (0, 1) else g[y * W + x]
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                g[y * W + x] = rid
    for (x0, y0, x1, y1), rid in DOORS:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                g[y * W + x] = rid
    for x, y in [(30, 30), (31, 30), (30, 31), (31, 31), (100, 70), (101, 70)]:  # furniture legs
        g[y * W + x] = 2
    return g


def _sweep(g: bytearray, room: int, mode: int, step: int = 4) -> list[dict[str, int]]:
    """Boustrophedon rows across one room, 3 cells apart along each row."""
    x0, y0, x1, y1 = next(rect for rid, _n, _c, rect in ROOMS if rid == room)
    pts: list[dict[str, int]] = []
    flip = False
    for y in range(y0 + 1, y1, step):
        a, b = x0 + 2, x1 - 2
        for x in range(b, a - 1, -3) if flip else range(a, b + 1, 3):
            if g[y * W + x] == room:
                wx, wy = world(x, y)
                pts.append({"x": wx, "y": wy, "type": 1, "sweep_mop_mode": mode, "yaw": 0})
        flip = not flip
    return pts


def make_map(path_rooms: tuple[tuple[int, int], ...] = ((7, 1), (3, 3)), path_points: int | None = None) -> dict:
    """Decoded map file. `path_rooms` is (room id, sweep_mop_mode) cleaned in order; 1 = vacuum, 3 = vacuum and mop."""
    g = _grid()
    dock = world(*DOCK)
    path: list[dict[str, int]] = [{"x": dock[0], "y": dock[1] + 150, "type": 0, "sweep_mop_mode": 1, "yaw": 0}]
    previous = 7  # the dock is in the living room
    for room, mode in path_rooms:
        if (door := TRANSIT.get(frozenset((previous, room)))) is not None:
            x, y = world(*door)
            path.append({"x": x, "y": y, "type": 0, "sweep_mop_mode": mode, "yaw": 0})
        path += _sweep(g, room, mode)
        previous = room
    if path_points is not None:
        path = path[:path_points]
    last = path[-1]
    return {
        "width": W,
        "height": H,
        "resolution": RES,
        "origin_x": OX,
        "origin_y": OY,
        "map_data": base64.b64encode(zlib.compress(bytes(g))).decode(),
        "room_attrs": [
            {
                "id": rid,
                "room_name": name,
                "name_pos_x": world((x0 + x1) / 2, (y0 + y1) / 2)[0],
                "name_pos_y": world((x0 + x1) / 2, (y0 + y1) / 2)[1],
            }
            for rid, name, _c, (x0, y0, x1, y1) in ROOMS
        ],
        "map_room_info": [{"grid_id": rid, "color": color} for rid, _n, color, _r in ROOMS],
        "map_3d_info": {"carpets": [{"p_3d": [*world(80, 14), *world(100, 14), *world(100, 30), *world(80, 30)]}]},
        "fb_walls": [{"wall_points": [*world(60, 40), *world(68, 44)]}],
        "fb_regions": [
            {
                "type": "no_mop",
                "points": [
                    {"x": world(8, 70)[0], "y": world(8, 70)[1]},
                    {"x": world(16, 70)[0], "y": world(16, 70)[1]},
                    {"x": world(16, 80)[0], "y": world(16, 80)[1]},
                    {"x": world(8, 80)[0], "y": world(8, 80)[1]},
                ],
            }
        ],
        "have_pile": 1,
        "pile_x": dock[0],
        "pile_y": dock[1],
        "pile_yaw": 1571,
        "position": {"x": last["x"], "y": last["y"], "yaw": 0},
        "paths": {"points": path},
        "current_cleaning_config": {"rooms": [r for r, _ in path_rooms], "clean_mode": 3},
        "task_id": 42,
    }


def encrypt(decoded: dict[str, Any], model: str = MODEL, did: str = DEVICE_ID) -> bytes:
    """Encrypt a decoded map the way the robot uploads it."""
    key = bytes.fromhex(gen_md5_key(model.replace("xiaomi", "mi"), did))
    data = zlib.compress(json.dumps(decoded).encode())
    return AES.new(key, AES.MODE_CBC, IV).encrypt(pad(data, AES.block_size))
