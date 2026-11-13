"""Decoding the robot's map file and building the card payload."""

from __future__ import annotations

import base64
import json
import zlib

import pytest

from custom_components.xiaomi_live_map import mapdata

from .synthetic import DEVICE_ID, MODEL, ROOMS, H, W, encrypt, make_map


def test_decode_raw_and_json_wrapped() -> None:
    decoded = make_map()
    raw = encrypt(decoded)
    assert mapdata.decode(raw, MODEL, DEVICE_ID) == decoded
    wrapped = json.dumps({"data": base64.b64encode(raw).decode()}).encode()
    assert mapdata.decode(wrapped, MODEL, DEVICE_ID) == decoded


def test_decode_wrong_device_is_unsupported() -> None:
    with pytest.raises(mapdata.UnsupportedMapError):
        mapdata.decode(encrypt(make_map()), MODEL, "999")


def test_decode_other_format_is_unsupported() -> None:
    with pytest.raises(mapdata.UnsupportedMapError, match="JSON grid format"):
        mapdata.decode(encrypt({"something": "else"}), MODEL, DEVICE_ID)


def test_build_payload() -> None:
    decoded = make_map()
    out = mapdata.build(decoded)
    base = out["base"]
    assert (base["w"], base["h"], base["res"]) == (W, H, 50)
    assert [r["id"] for r in base["rooms"]] == [r[0] for r in ROOMS]
    assert base["rooms"][0]["name"] == "Kitchen"
    assert base["rooms"][0]["color"] == 2
    assert base["charger"]["yaw"] == pytest.approx(1.571)
    assert len(base["carpets"]) == 1
    assert len(base["vwalls"]) == 1
    assert base["regions"][0]["type"] == "no_mop"
    assert len(base64.b64decode(out["grid"])) == W * H

    points = decoded["paths"]["points"]
    assert len(out["path"]) == 4 * len(points)
    first = points[1]
    assert out["path"][4:8] == [first["x"], first["y"], 1, 1]
    assert out["robot"] == {"x": points[-1]["x"], "y": points[-1]["y"], "yaw": 0.0}


def test_grid_rev_follows_grid_only() -> None:
    a = mapdata.build(make_map(path_points=5))["base"]["grid_rev"]
    b = mapdata.build(make_map(path_points=50))["base"]["grid_rev"]
    assert a == b
    changed = make_map()
    grid = bytearray(zlib.decompress(base64.b64decode(changed["map_data"])))
    grid[0] = 1
    changed["map_data"] = base64.b64encode(zlib.compress(bytes(grid))).decode()
    assert mapdata.build(changed)["base"]["grid_rev"] != a


def test_bad_grid_is_unsupported() -> None:
    decoded = make_map()
    decoded["map_data"] = base64.b64encode(zlib.compress(b"\x00" * 10)).decode()
    with pytest.raises(mapdata.UnsupportedMapError):
        mapdata.build(decoded)


def test_summary_has_no_coordinates() -> None:
    summary = mapdata.summary(make_map())
    assert summary["path_kinds"]["type=1 mode=3"] > 0
    assert summary["path_kinds"]["type=0 mode=1"] == 1
    text = json.dumps(summary)
    assert "Kitchen" not in text
    assert str(make_map()["paths"]["points"][5]["x"]) not in text
