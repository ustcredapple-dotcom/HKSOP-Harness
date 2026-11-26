#!/usr/bin/env python3
"""Build an eccentric adapter STEP and a GB First-Angle three-view machining SVG."""
import argparse
from collections import defaultdict
from html import escape
import json
import math
from pathlib import Path
import sys


def _first_angle_symbol(cx, cy, r=2.3):
    x0, x1 = cx - 8.5, cx - 3.2
    r1, r2 = r * 0.55, r
    cone = (
        f'<polygon points="{x0:g},{cy - r1:g} {x1:g},{cy - r2:g} {x1:g},{cy + r2:g} {x0:g},{cy + r1:g}" '
        f'fill="none" stroke="#111" stroke-width="0.25"/>'
    )
    ccx = cx + 2.5
    circles = (
        f'<circle cx="{ccx:g}" cy="{cy:g}" r="{r1:g}" fill="none" stroke="#111" stroke-width="0.25"/>'
        f'<circle cx="{ccx:g}" cy="{cy:g}" r="{r2:g}" fill="none" stroke="#111" stroke-width="0.25"/>'
    )
    axes = (
        f'<line x1="{x0 - 1.2:g}" y1="{cy:g}" x2="{ccx + r2 + 1.2:g}" y2="{cy:g}" '
        f'stroke="#c0392b" stroke-width="0.14" stroke-dasharray="1.8 0.6 0.4 0.6"/>'
        f'<line x1="{ccx:g}" y1="{cy - r2 - 1.1:g}" x2="{ccx:g}" y2="{cy + r2 + 1.1:g}" '
        f'stroke="#c0392b" stroke-width="0.14" stroke-dasharray="1.8 0.6 0.4 0.6"/>'
    )
    return axes + cone + circles


def _dim_h(x1, x2, y_line, y_ref1, y_ref2, text, font_size=2.5):
    if x2 < x1:
        x1, x2 = x2, x1
    ext = 1.4 if y_line > y_ref1 else -1.4
    return (
        f'<line x1="{x1:g}" y1="{y_ref1:g}" x2="{x1:g}" y2="{y_line + ext:g}" stroke="#111" stroke-width="0.16"/>'
        f'<line x1="{x2:g}" y1="{y_ref2:g}" x2="{x2:g}" y2="{y_line + ext:g}" stroke="#111" stroke-width="0.16"/>'
        f'<line x1="{x1:g}" y1="{y_line:g}" x2="{x2:g}" y2="{y_line:g}" stroke="#111" stroke-width="0.2" marker-start="url(#arrow-s)" marker-end="url(#arrow-e)"/>'
        f'<text x="{(x1 + x2) / 2:g}" y="{y_line - 0.9:g}" text-anchor="middle" font-size="{font_size:g}" fill="#111">{escape(text)}</text>'
    )


def _dim_v(y1, y2, x_line, x_ref1, x_ref2, text, font_size=2.5):
    if y2 < y1:
        y1, y2 = y2, y1
    ext = 1.4 if x_line > x_ref1 else -1.4
    mx, my = x_line - 1.1, (y1 + y2) / 2
    return (
        f'<line x1="{x_ref1:g}" y1="{y1:g}" x2="{x_line + ext:g}" y2="{y1:g}" stroke="#111" stroke-width="0.16"/>'
        f'<line x1="{x_ref2:g}" y1="{y2:g}" x2="{x_line + ext:g}" y2="{y2:g}" stroke="#111" stroke-width="0.16"/>'
        f'<line x1="{x_line:g}" y1="{y1:g}" x2="{x_line:g}" y2="{y2:g}" stroke="#111" stroke-width="0.2" marker-start="url(#arrow-s)" marker-end="url(#arrow-e)"/>'
        f'<text x="{mx:g}" y="{my:g}" text-anchor="middle" font-size="{font_size:g}" fill="#111" transform="rotate(-90 {mx:g} {my:g})">{escape(text)}</text>'
    )


def _hole_spec(entry):
    d = entry["diameterMm"] * 1.0
    if entry.get("thread"):
        spec = str(entry["thread"])
        if "-6H" not in spec and "-6h" not in spec.lower():
            spec += "-6H"
        if entry.get("depthMm") is not None:
            spec += f" 深{entry['depthMm']:g}"
        return spec
    if entry.get("counterboreDiameterMm") and entry.get("counterboreDepthMm"):
        return f"Ø{d:g} 通 / 沉孔Ø{entry['counterboreDiameterMm']:g} 深{entry['counterboreDepthMm']:g}"
    if entry.get("depthMm") is not None:
        return f"Ø{d:g} 深{entry['depthMm']:g}"
    return f"Ø{d:g} 通"


def _render_machining_svg(task, drawing, w, h, t, positions, holes):
    scales = [(4.0, "4:1"), (2.5, "2.5:1"), (2.0, "2:1"), (1.5, "1.5:1"), (1.0, "1:1"), (0.5, "1:2"), (0.4, "1:2.5"), (0.25, "1:4"), (0.2, "1:5")]
    s, scale_text = next(
        ((sc, lbl) for sc, lbl in scales if (w + h) * sc <= 122 and (t + h) * sc <= 122),
        (min(122 / max(w + h, 1), 122 / max(t + h, 1)), f"1:{max((w + h) / 122, (t + h) / 122):.1f}"),
    )

    vx = 24.0
    vy_front = 24.0
    sw, sh, st = w * s, h * s, t * s
    gap_x = 18.0
    gap_y = 20.0
    vx_left = vx + sw + gap_x
    vy_top = vy_front + st + gap_y

    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210">',
        '<defs>',
        '<marker id="arrow-e" viewBox="0 0 10 4" refX="10" refY="2" markerWidth="2.4" markerHeight="1.1" orient="auto">'
        '<path d="M0,0 L10,2 L0,4 Z" fill="#111"/></marker>',
        '<marker id="arrow-s" viewBox="0 0 10 4" refX="0" refY="2" markerWidth="2.4" markerHeight="1.1" orient="auto">'
        '<path d="M10,0 L0,2 L10,4 Z" fill="#111"/></marker>',
        '</defs>',
        '<rect x="6" y="6" width="285" height="198" fill="#fff" stroke="#111" stroke-width="0.4"/>',
        '<line x1="188" y1="6" x2="188" y2="204" stroke="#111" stroke-width="0.26"/>',
        '<g font-family="sans-serif" fill="#111">',
    ]

    # 1. Front View (w x t) at top-left.
    svg.append(f'<text x="{vx:g}" y="{vy_front - 3.5:g}" font-size="2.9" font-weight="600">主视图 ({scale_text})</text>')
    svg.append(f'<rect x="{vx:g}" y="{vy_front:g}" width="{sw:g}" height="{st:g}" fill="none" stroke="#111" stroke-width="0.34"/>')
    for hx, _, hr in positions:
        cx_v, rx_v = vx + hx * s, hr * s
        svg.append(
            f'<line x1="{cx_v:g}" y1="{vy_front - 1.8:g}" x2="{cx_v:g}" y2="{vy_front + st + 1.8:g}" '
            f'stroke="#c0392b" stroke-width="0.15" stroke-dasharray="2 0.6 0.4 0.6"/>'
            f'<line x1="{cx_v - rx_v:g}" y1="{vy_front:g}" x2="{cx_v - rx_v:g}" y2="{vy_front + st:g}" '
            f'stroke="#444" stroke-width="0.18" stroke-dasharray="1.3 0.8"/>'
            f'<line x1="{cx_v + rx_v:g}" y1="{vy_front:g}" x2="{cx_v + rx_v:g}" y2="{vy_front + st:g}" '
            f'stroke="#444" stroke-width="0.18" stroke-dasharray="1.3 0.8"/>'
        )
    svg.append(_dim_v(vy_front, vy_front + st, vx - 6.0, vx, vx, f"{t:g}"))

    # 2. Left View (h x t) to the right of Front View (First-Angle: Y=h on left, Y=0 on right).
    svg.append(f'<text x="{vx_left:g}" y="{vy_front - 3.5:g}" font-size="2.9" font-weight="600">左视图</text>')
    svg.append(f'<rect x="{vx_left:g}" y="{vy_front:g}" width="{sh:g}" height="{st:g}" fill="none" stroke="#111" stroke-width="0.34"/>')
    for _, hy, hr in positions:
        cx_l, rx_l = vx_left + (h - hy) * s, hr * s
        svg.append(
            f'<line x1="{cx_l:g}" y1="{vy_front - 1.8:g}" x2="{cx_l:g}" y2="{vy_front + st + 1.8:g}" '
            f'stroke="#c0392b" stroke-width="0.15" stroke-dasharray="2 0.6 0.4 0.6"/>'
            f'<line x1="{cx_l - rx_l:g}" y1="{vy_front:g}" x2="{cx_l - rx_l:g}" y2="{vy_front + st:g}" '
            f'stroke="#444" stroke-width="0.18" stroke-dasharray="1.3 0.8"/>'
            f'<line x1="{cx_l + rx_l:g}" y1="{vy_front:g}" x2="{cx_l + rx_l:g}" y2="{vy_front + st:g}" '
            f'stroke="#444" stroke-width="0.18" stroke-dasharray="1.3 0.8"/>'
        )
    svg.append(_dim_h(vx_left, vx_left + sh, vy_front + st + 7.0, vy_front + st, vy_front + st, f"{h:g}"))

    # 3. Top View (w x h) directly below Front View (First-Angle: Y=h at top, Y=0 at bottom).
    svg.append(f'<text x="{vx:g}" y="{vy_top - 3.0:g}" font-size="2.9" font-weight="600">俯视图</text>')
    svg.append(f'<rect x="{vx:g}" y="{vy_top:g}" width="{sw:g}" height="{sh:g}" fill="none" stroke="#111" stroke-width="0.34"/>')
    svg.append(f'<circle cx="{vx:g}" cy="{vy_top + sh:g}" r="1.1" fill="none" stroke="#111" stroke-width="0.24"/>')
    svg.append(f'<text x="{vx + 1.8:g}" y="{vy_top + sh + 4.2:g}" font-size="2.3" font-weight="600">基准 A/B (0,0)</text>')
    svg.append(_dim_h(vx, vx + sw, vy_top + sh + 9.5, vy_top + sh, vy_top + sh, f"{w:g}"))
    svg.append(_dim_v(vy_top, vy_top + sh, vx - 6.0, vx, vx, f"{h:g}"))

    grouped = defaultdict(list)
    for idx_h, ((hx, hy, hr), entry) in enumerate(zip(positions, holes), 1):
        cx_t = vx + hx * s
        cy_t = vy_top + (h - hy) * s
        r_t = hr * s
        ch = max(r_t + 1.5, 2.5)
        svg.append(
            f'<circle cx="{cx_t:g}" cy="{cy_t:g}" r="{r_t:g}" fill="none" stroke="#111" stroke-width="0.26"/>'
            f'<line x1="{cx_t - ch:g}" y1="{cy_t:g}" x2="{cx_t + ch:g}" y2="{cy_t:g}" stroke="#c0392b" stroke-width="0.14" stroke-dasharray="1.8 0.6 0.4 0.6"/>'
            f'<line x1="{cx_t:g}" y1="{cy_t - ch:g}" x2="{cx_t:g}" y2="{cy_t + ch:g}" stroke="#c0392b" stroke-width="0.14" stroke-dasharray="1.8 0.6 0.4 0.6"/>'
            f'<text x="{cx_t + r_t + 0.9:g}" y="{cy_t - r_t - 0.5:g}" font-size="2.3" font-weight="600">{idx_h}</text>'
        )
        grouped[_hole_spec(entry)].append((cx_t, cy_t))

    # Grouped leader callouts beside Top View (sorted top-to-bottom by target hole Y to avoid crossing).
    kx_call = vx + sw + 8.0
    ex_call = min(184.0, kx_call + 32.0)
    groups_sorted = []
    for spec, pts in grouped.items():
        pt = max(pts, key=lambda p_: (p_[0], -p_[1]))
        groups_sorted.append((pt[1], pt[0], spec, len(pts)))
    groups_sorted.sort()
    last_ky = vy_top - 4.0
    for idx_g, (py, px, spec, count) in enumerate(groups_sorted):
        ky = max(last_ky + 10.0, min(vy_top + sh - 4.0, py - 5.0))
        last_ky = ky
        txt = f"{count}× {spec}"
        svg.append(
            f'<polyline points="{px:g},{py:g} {kx_call:g},{ky:g} {ex_call:g},{ky:g}" fill="none" stroke="#111" stroke-width="0.2" marker-start="url(#arrow-s)"/>'
            f'<text x="{kx_call + 1.0:g}" y="{ky - 0.9:g}" font-size="2.4">{escape(txt)}</text>'
        )

    # 4. Right Column: Compact Hole Table (y=12..106) + Notes (y=110..146) + Bottom-Right Title Block.
    rx = 191.0
    svg.append(f'<text x="{rx:g}" y="13.5" font-size="2.9" font-weight="600">孔位坐标与规格表（基准 A/B）</text>')
    ty = 16.5
    row_h = min(4.8, 88.0 / max(len(positions) + 1, 2))
    cols = [rx, rx + 11, rx + 31, rx + 51, rx + 97]
    svg.append(f'<rect x="{rx:g}" y="{ty:g}" width="97" height="{row_h:g}" fill="#f2f4f5" stroke="#111" stroke-width="0.22"/>')
    for cx_c, hdr in zip(cols[:-1], ["孔", "X", "Y", "规格"]):
        svg.append(f'<text x="{cx_c + 1.2:g}" y="{ty + row_h * 0.72:g}" font-size="2.2" font-weight="600">{hdr}</text>')
    for idx_h, ((hx, hy, _), entry) in enumerate(zip(positions, holes), 1):
        ry = ty + idx_h * row_h
        if ry + row_h > 107.0:
            break
        svg.append(f'<rect x="{rx:g}" y="{ry:g}" width="97" height="{row_h:g}" fill="none" stroke="#111" stroke-width="0.18"/>')
        for cx_c, val in zip(cols[:-1], [str(idx_h), f"{hx:.2f}", f"{hy:.2f}", _hole_spec(entry)]):
            svg.append(f'<text x="{cx_c + 1.2:g}" y="{ry + row_h * 0.72:g}" font-size="2.1">{escape(val)}</text>')
    max_y = min(ty + (len(positions) + 1) * row_h, 107.0)
    for cx_line in cols[1:-1]:
        svg.append(f'<line x1="{cx_line:g}" y1="{ty:g}" x2="{cx_line:g}" y2="{max_y:g}" stroke="#111" stroke-width="0.18"/>')

    ny_box = 112.0
    svg.append(f'<text x="{rx:g}" y="{ny_box + 3.5:g}" font-size="2.9" font-weight="600">技术要求</text>')
    notes = [
        "1. 未注尺寸公差按 GB/T 1804-m（ISO 2768-m）。",
        "2. 默认表面粗糙度 Ra 3.2。",
        "3. 外棱倒角 C0.3×45°，锐边去毛刺。",
        "4. 其余几何形状参照同修订 3D STEP。",
    ]
    for idx_n, line in enumerate(notes):
        svg.append(f'<text x="{rx:g}" y="{ny_box + 9.0 + idx_n * 5.2:g}" font-size="2.3">{escape(line)}</text>')

    # 5. Fixed Bottom-Right GB Standard Title Block (x=188..291, y=148..204).
    tx0, ty0, tw, th = 188.0, 148.0, 103.0, 56.0
    svg.append(f'<rect x="{tx0:g}" y="{ty0:g}" width="{tw:g}" height="{th:g}" fill="#fff" stroke="#111" stroke-width="0.36"/>')
    for y_sep in (161.0, 172.0, 183.0, 194.0):
        svg.append(f'<line x1="{tx0:g}" y1="{y_sep:g}" x2="{tx0 + tw:g}" y2="{y_sep:g}" stroke="#111" stroke-width="0.22"/>')
    for x_sep, y_top, y_bot in ((262.0, 148.0, 161.0), (235.0, 161.0, 204.0), (264.0, 161.0, 183.0)):
        svg.append(f'<line x1="{x_sep:g}" y1="{y_top:g}" x2="{x_sep:g}" y2="{y_bot:g}" stroke="#111" stroke-width="0.22"/>')

    part_name = str(drawing.get("partName") or task["wishId"])
    finish = str(drawing.get("finish", "按材料处理"))
    qty = drawing.get("quantity", 1)
    svg.extend([
        f'<text x="{tx0 + 2:g}" y="153.0" font-size="2.0" fill="#555">件号 / 名称</text>',
        f'<text x="{tx0 + 2:g}" y="158.5" font-size="2.8" font-weight="600">{escape(part_name[:20])}</text>',
        f'<text x="264.0" y="153.0" font-size="2.0" fill="#555">页码</text>',
        f'<text x="276.5" y="158.5" font-size="2.7" text-anchor="middle" font-weight="600">1 / 1</text>',
        f'<text x="{tx0 + 2:g}" y="165.5" font-size="1.9" fill="#555">规格 (mm)</text>',
        f'<text x="{tx0 + 2:g}" y="170.2" font-size="2.4">{w:g} × {h:g} × {t:g}</text>',
        f'<text x="237.0" y="165.5" font-size="1.9" fill="#555">数量</text>',
        f'<text x="249.5" y="170.2" font-size="2.5" text-anchor="middle">{qty} 件</text>',
        f'<text x="266.0" y="165.5" font-size="1.9" fill="#555">比例</text>',
        f'<text x="277.5" y="170.2" font-size="2.5" text-anchor="middle">{scale_text}</text>',
        f'<text x="{tx0 + 2:g}" y="176.5" font-size="1.9" fill="#555">材料</text>',
        f'<text x="{tx0 + 2:g}" y="181.2" font-size="2.3">{escape(str(drawing["material"])[:14])}</text>',
        f'<text x="237.0" y="176.5" font-size="1.9" fill="#555">表面处理</text>',
        f'<text x="237.0" y="181.2" font-size="2.1">{escape(finish[:10])}</text>',
        f'<text x="266.0" y="176.5" font-size="1.9" fill="#555">单位</text>',
        f'<text x="277.5" y="181.2" font-size="2.5" text-anchor="middle">mm</text>',
        f'<text x="{tx0 + 2:g}" y="187.5" font-size="1.9" fill="#555">未注公差</text>',
        f'<text x="{tx0 + 2:g}" y="192.2" font-size="2.4" font-weight="600">GB/T 1804-m</text>',
        f'<text x="237.0" y="187.5" font-size="1.9" fill="#555">粗糙度 / 螺纹</text>',
        f'<text x="237.0" y="192.2" font-size="2.4" font-weight="600">Ra 3.2 / 6H</text>',
        f'<text x="{tx0 + 2:g}" y="198.5" font-size="1.9" fill="#555">投影法</text>',
        f'<text x="{tx0 + 2:g}" y="202.5" font-size="2.4" font-weight="600">第一角法 (GB)</text>',
        _first_angle_symbol(264.0, 199.0),
    ])
    svg.append("</g></svg>\n")
    return "".join(svg)


def build(task, drawing, out):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    if drawing["wishId"] != task["wishId"] or not drawing.get("upperDrawingReference") or not drawing.get("material"):
        raise ValueError("须提供对应需求、上接口原图及材料")
    if task["envelope"]["frame"] != "board":
        raise ValueError("先将包络与接口注册到同一坐标系")
    x0, y0, x1, y1 = drawing["boundsXYmm"]
    a, b, c, d = task["envelope"]["xyxyMm"]
    if not (a <= x0 < x1 <= c and b <= y0 < y1 <= d):
        raise ValueError("超出已批准加工包络")
    w, h, t = x1 - x0, y1 - y0, drawing["thicknessMm"]
    if not all(math.isfinite(n) and n > .6 for n in (w, h, t)):
        raise ValueError("坯料尺寸无效")
    holes = [dict(xMm=p["xMm"], yMm=p["yMm"], diameterMm=6.6, role="lower " + p["id"]) for p in task["mountingInterface"]["holes"]] + drawing["upperHoles"]
    initial = BRepPrimAPI_MakeBox(w, h, t).Shape()
    ch = BRepFilletAPI_MakeChamfer(initial)
    edges = TopExp_Explorer(initial, TopAbs_EDGE)
    cast = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    while edges.More():
        ch.Add(.3, cast(edges.Current()))
        edges.Next()
    ch.Build()
    if not ch.IsDone():
        raise ValueError("外棱倒角失败")
    solid = ch.Shape()
    positions = []
    for entry in holes:
        x, y, r = entry["xMm"] - x0, entry["yMm"] - y0, entry["diameterMm"] / 2
        if not (r > 0 and r + .3 < x < w - r - .3 and r + .3 < y < h - r - .3):
            raise ValueError("孔与外棱相交")
        if any(math.hypot(x - px, y - py) <= r + pr for px, py, pr in positions):
            raise ValueError("孔组相交")
        positions.append((x, y, r))
        solid = BRepAlgoAPI_Cut(solid, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y, -1), gp_Dir(0, 0, 1)), r, t + 2).Shape()).Shape()
    if not BRepCheck_Analyzer(solid).IsValid():
        raise ValueError("实体无效")
    out.mkdir(parents=True, exist_ok=True)
    writer = STEPControl_Writer()
    writer.Transfer(solid, STEPControl_AsIs)
    if writer.Write(str(out / "adapter.step")) != IFSelect_RetDone:
        raise ValueError("STEP 写入失败")
    (out / "machining.svg").write_text(_render_machining_svg(task, drawing, w, h, t, positions, holes))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("tasks", type=Path)
    p.add_argument("dimensions", type=Path)
    p.add_argument("-o", type=Path, required=True)
    a = p.parse_args()
    try:
        d = json.loads(a.dimensions.read_bytes())
        row = next(t for t in json.loads(a.tasks.read_bytes())["tasks"] if t["wishId"] == d["wishId"])
        build(row, d, a.o)
    except (ImportError, StopIteration, ValueError, KeyError, OSError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
