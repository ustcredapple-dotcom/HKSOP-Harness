#!/usr/bin/env python3
"""Build a private 532 nm geometry bundle from four manufacturer models and the matching core."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import ssl
import sys
import tempfile
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/pm-fiber-1x3-532"
VERIFY = ROOT / "plugins/hksop-step3-manufacture/skills/json-to-3d-verify/scripts"
sys.path.insert(0, str(VERIFY))
from hksop_runtime import library_root


def bolt(dest):
    from solid_scene import bbox, write_board
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeCone, BRepPrimAPI_MakeCylinder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir, gp_Vec

    def axis(z):
        return gp_Ax2(gp_Pnt(0, 0, z), gp_Dir(0, 0, 1))

    body = BRepPrimAPI_MakeCylinder(axis(-11.45), 3, 11.46).Shape()
    for part in (BRepPrimAPI_MakeCone(axis(-12), 2.45, 3, .55),
                 BRepPrimAPI_MakeCylinder(axis(0), 5, 5.7), BRepPrimAPI_MakeCone(axis(5.7), 5, 4.7, .3)):
        body = BRepAlgoAPI_Fuse(body, part.Shape()).Shape()
    hexagon = BRepBuilderAPI_MakePolygon()
    for index in range(6):
        a = index * math.pi / 3
        radius = 5 / math.sqrt(3)
        hexagon.Add(gp_Pnt(radius * math.cos(a), radius * math.sin(a), 3))
    hexagon.Close()
    socket = BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(hexagon.Wire()).Face(), gp_Vec(0, 0, 4))
    result = BRepAlgoAPI_Cut(body, socket.Shape()).Shape()
    write_board(dest, (result, bbox(result)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sources = p.add_mutually_exclusive_group(required=True)
    sources.add_argument("--vendor", type=Path, help="Directory containing the four locally licensed STEP models")
    sources.add_argument("--fetch", action="store_true", help="Download the pinned models from their original provider")
    p.add_argument("--root", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    a = p.parse_args()
    from build_pm_head import build
    core = library_root(a.root)
    out = a.output.expanduser().resolve()
    if out.exists() or any(base == out or base in out.parents for base in (core,ROOT)):
        p.error("Choose a new external working directory for the geometry bundle")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        stage = Path(tmp) / "bundle"
        vendor = stage / "vendor"
        vendor.mkdir(parents=True)
        for record in json.loads((EXAMPLE / "asset-sources.json").read_bytes()).values():
            dst = vendor / record["file"]
            if a.fetch:
                trust = ssl.create_default_context()
                system_roots = Path("/etc/ssl/cert.pem")
                if system_roots.is_file():
                    trust.load_verify_locations(cafile=system_roots)
                try:
                    with urlopen(record["source"], context=trust, timeout=90) as response, dst.open("wb") as f:
                        shutil.copyfileobj(response, f)
                except URLError as exc:
                    raise ValueError(f"{dst.name}: {exc}. 请从原厂取得四个模型，再用 --vendor 提供本地目录。") from exc
            else:
                shutil.copyfile(a.vendor / dst.name, dst)
            with dst.open("rb") as f:
                if hashlib.file_digest(f, "sha256").hexdigest() != record["sha256"]:
                    raise ValueError("Supplier geometry SHA-256 mismatch: " + dst.name)
        build(core, vendor, stage)
        shutil.copyfile(EXAMPLE / "kit-datums.json", stage / "kit-datums.json")
        bolt(stage / "M6x12-ISO4762.step")
        stage.rename(out)
    print(out)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, ImportError) as e:
        sys.exit(str(e))
