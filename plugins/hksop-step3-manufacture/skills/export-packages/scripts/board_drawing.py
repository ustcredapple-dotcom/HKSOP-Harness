#!/usr/bin/env python3
"""Lay out a 1-page GB First-Angle breadboard machining drawing plus clean laser-marking SVGs."""
import argparse
from html import escape
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


def _first_angle_symbol(cx, cy, r=2.6):
    """Return SVG elements for the standard GB/ISO First-Angle projection symbol."""
    x0, x1 = cx - 9.5, cx - 3.5
    r1, r2 = r * 0.55, r
    cone = (
        f'<polygon points="{x0:g},{cy - r1:g} {x1:g},{cy - r2:g} {x1:g},{cy + r2:g} {x0:g},{cy + r1:g}" '
        f'fill="none" stroke="#111" stroke-width="0.28"/>'
    )
    ccx = cx + 2.8
    circles = (
        f'<circle cx="{ccx:g}" cy="{cy:g}" r="{r1:g}" fill="none" stroke="#111" stroke-width="0.28"/>'
        f'<circle cx="{ccx:g}" cy="{cy:g}" r="{r2:g}" fill="none" stroke="#111" stroke-width="0.28"/>'
    )
    axes = (
        f'<line x1="{x0 - 1.5:g}" y1="{cy:g}" x2="{ccx + r2 + 1.5:g}" y2="{cy:g}" '
        f'stroke="#c0392b" stroke-width="0.16" stroke-dasharray="2 0.7 0.4 0.7"/>'
        f'<line x1="{ccx:g}" y1="{cy - r2 - 1.3:g}" x2="{ccx:g}" y2="{cy + r2 + 1.3:g}" '
        f'stroke="#c0392b" stroke-width="0.16" stroke-dasharray="2 0.7 0.4 0.7"/>'
    )
    return axes + cone + circles


def _dim_h(x1, x2, y_line, y_ref1, y_ref2, label_text, font_size=2.7):
    if x2 < x1:
        x1, x2 = x2, x1
    e1 = 1.4 if y_line > y_ref1 else -1.4
    e2 = 1.4 if y_line > y_ref2 else -1.4
    return (
        f'<line x1="{x1:g}" y1="{y_ref1:g}" x2="{x1:g}" y2="{y_line + e1:g}" stroke="#111" stroke-width="0.18"/>'
        f'<line x1="{x2:g}" y1="{y_ref2:g}" x2="{x2:g}" y2="{y_line + e2:g}" stroke="#111" stroke-width="0.18"/>'
        f'<line x1="{x1:g}" y1="{y_line:g}" x2="{x2:g}" y2="{y_line:g}" stroke="#111" stroke-width="0.22" marker-start="url(#arrow-s)" marker-end="url(#arrow-e)"/>'
        f'<text x="{(x1 + x2) / 2:g}" y="{y_line - 1.0:g}" text-anchor="middle" font-size="{font_size:g}" fill="#111">{escape(label_text)}</text>'
    )


def _dim_v(y1, y2, x_line, x_ref1, x_ref2, label_text, font_size=2.7):
    if y2 < y1:
        y1, y2 = y2, y1
    e1 = 1.4 if x_line > x_ref1 else -1.4
    e2 = 1.4 if x_line > x_ref2 else -1.4
    mx, my = x_line - 1.2, (y1 + y2) / 2
    return (
        f'<line x1="{x_ref1:g}" y1="{y1:g}" x2="{x_line + e1:g}" y2="{y1:g}" stroke="#111" stroke-width="0.18"/>'
        f'<line x1="{x_ref2:g}" y1="{y2:g}" x2="{x_line + e2:g}" y2="{y2:g}" stroke="#111" stroke-width="0.18"/>'
        f'<line x1="{x_line:g}" y1="{y1:g}" x2="{x_line:g}" y2="{y2:g}" stroke="#111" stroke-width="0.22" marker-start="url(#arrow-s)" marker-end="url(#arrow-e)"/>'
        f'<text x="{mx:g}" y="{my:g}" text-anchor="middle" font-size="{font_size:g}" fill="#111" transform="rotate(-90 {mx:g} {my:g})">{escape(label_text)}</text>'
    )


def _leader(px, py, kx, ky, ex, lines, font_size=2.5):
    parts = [
        f'<polyline points="{px:g},{py:g} {kx:g},{ky:g} {ex:g},{ky:g}" fill="none" stroke="#111" stroke-width="0.22" marker-start="url(#arrow-s)"/>'
    ]
    tx = kx + 1.2
    for idx, line in enumerate(lines):
        y_txt = ky - 1.0 if idx == 0 else ky + 3.1 + (idx - 1) * 3.3
        parts.append(
            f'<text x="{tx:g}" y="{y_txt:g}" text-anchor="start" font-size="{font_size:g}" fill="#111">{escape(line)}</text>'
        )
    return "".join(parts)


def _hatch_rect(x0, y0, w, h, step=2.2):
    """Draw 45-degree section hatch lines inside axis-aligned rectangle [x0..x0+w, y0..y0+h]."""
    lines = []
    # Lines x + y = c where x in [x0, x0+w], y in [y0, y0+h]
    c_min = x0 + y0 + step * 0.5
    c_max = x0 + w + y0 + h - step * 0.5
    c = c_min
    while c <= c_max:
        pts = []
        # Intersect x + y = c with rect edges
        y_left = c - x0
        if y0 <= y_left <= y0 + h:
            pts.append((x0, y_left))
        y_right = c - (x0 + w)
        if y0 <= y_right <= y0 + h:
            pts.append((x0 + w, y_right))
        x_top = c - y0
        if x0 < x_top < x0 + w:
            pts.append((x_top, y0))
        x_bot = c - (y0 + h)
        if x0 < x_bot < x0 + w:
            pts.append((x_bot, y0 + h))
        if len(pts) >= 2:
            p1, p2 = pts[0], pts[-1]
            if math.hypot(p1[0] - p2[0], p1[1] - p2[1]) > 0.2:
                lines.append(
                    f'<line x1="{p1[0]:g}" y1="{p1[1]:g}" x2="{p2[0]:g}" y2="{p2[1]:g}" stroke="#666" stroke-width="0.18"/>'
                )
        c += step
    return "".join(lines)


def drawing(project, ledger, labels, logo, filename, marking_dir=None):
    p = json.loads(project.read_bytes())
    l = json.loads(ledger.read_bytes())
    text = json.loads(labels.read_bytes())
    if text["projectSha256"] != hashlib.sha256(project.read_bytes()).hexdigest():
        raise ValueError("刻字表未绑定当前工程")
    if any(i.get("placeholder") for i in p["layout"]["instances"]):
        raise ValueError("未解决的 WISH 不能制作加工标记")
    b = p["layout"]["board"]
    w, h, t = b["widthMm"], b["heightMm"], b["thicknessMm"]
    pitch, edge = b["pitchMm"], b["edgeOffsetMm"]
    if any(b[k] != l["board"][k] for k in ("widthMm", "heightMm", "pitchMm", "edgeOffsetMm")):
        raise ValueError("孔图与工程板型不符")
    ids = {i["id"] for i in p["layout"]["instances"]}
    if ids != set(l["nodes"]) or ids != set(text["labels"]):
        raise ValueError("器件框及双语铭牌数量不匹配")
    side = text["outwardSide"]
    length = w if side in ("south", "north") else h if side in ("west", "east") else None
    if length is None or t <= 3:
        raise ValueError("外侧面或壁高无效")
    sign = ET.parse(logo).getroot()
    m = json.loads((logo.parent / "manifest.json").read_bytes())
    expected = next(v["sha256"] for v in m["files"] if v["path"] == logo.name)
    if hashlib.sha256(logo.read_bytes()).hexdigest() != expected:
        raise ValueError("Logo 哈希不符")
    ink = json.loads((logo.parent / "ink-bounds.json").read_bytes())["bounds"]
    if text.get("ledgerSha256") != hashlib.sha256(ledger.read_bytes()).hexdigest():
        raise ValueError("刻字表未绑定孔位账本")
    ix, iy, iw, ih = ink
    logo_scale = (t - 3) / ih
    if logo_scale * iw > length - 3:
        raise ValueError("完整标识超过外侧壁")

    # Validate node bilingual markings and build clean marking primitives (in board mm coords).
    top_mark_elems = []
    for k, r in l["nodes"].items():
        x0, y0, x1, y1 = r["supportBoundsMm"]
        v = text["labels"][k]
        if not re.search(r"[\u3400-\u9fff]", v["zh"]) or not re.search(r"[a-z]", v["en"], re.I):
            raise ValueError("需核实中英文刻字 " + k)
        top_mark_elems.append(
            f'<rect x="{x0:g}" y="{h - y1:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" fill="none" stroke="#111" stroke-width=".2"/>'
        )
        for j, title in enumerate((k, v["zh"], v["en"])):
            fsize = min(3.1, (x1 - x0 - 1) / max(1, len(title)))
            top_mark_elems.append(
                f'<text x="{x0 + 1:g}" y="{h - y1 + 4 + j * 4:g}" font-size="{fsize:.2f}">{escape(title)}</text>'
            )
        angle = math.radians(r["rotationDeg"])
        cx = (x0 + x1) / 2 + math.cos(angle) * (x1 - x0 - 3) / 2
        cy = h - (y0 + y1) / 2 - math.sin(angle) * (y1 - y0 - 3) / 2
        top_mark_elems.append(f'<circle cx="{cx:g}" cy="{cy:g}" r="1"/>')
    for a, b_ in text["beamCenterlinesMm"]:
        top_mark_elems.append(
            f'<line x1="{a[0]:g}" y1="{h - a[1]:g}" x2="{b_[0]:g}" y2="{h - b_[1]:g}" stroke="#444" stroke-width=".18" stroke-dasharray="2 1"/>'
        )
    top_marks_str = "".join(top_mark_elems)

    tx_side = length - 3 - logo_scale * (ix + iw)
    ty_side = 1.5 - logo_scale * iy
    artwork = "".join(
        ET.tostring(n, encoding="unicode")
        for n in sign
        if n.tag.rsplit("}", 1)[-1] not in ("title", "desc")
    )

    if marking_dir:
        marking_dir.mkdir(parents=True, exist_ok=True)

        def clean_svg(width, height, contents):
            return (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" '
                f'viewBox="0 0 {width} {height}"><g fill="#111" font-family="sans-serif">{contents}</g></svg>'
            )

        (marking_dir / "top-marking.svg").write_text(clean_svg(w, h, top_marks_str))
        (marking_dir / "side-marking.svg").write_text(
            clean_svg(length, t, f'<g transform="translate({tx_side:g} {ty_side:g}) scale({logo_scale:g})">{artwork}</g>')
        )

    # Choose standard scale on an A3 Landscape sheet (420 x 297 mm) in GB First-Angle projection.
    scales = [(1.0, "1:1"), (0.5, "1:2"), (0.4, "1:2.5"), (0.25, "1:4"), (0.2, "1:5"), (0.1, "1:10")]
    s, scale_text = next(
        ((sc, lbl) for sc, lbl in scales if w * sc <= 198 and (t + h) * sc <= 134),
        (min(198 / max(w, 1), 134 / max(t + h, 1)), f"1:{max(w / 198, (t + h) / 134):.1f}"),
    )

    vx = 30.0
    vy_front = 18.0
    vy_top = vy_front + t * s + 19.0
    sw, sh, st = w * s, h * s, t * s

    fixed = {(v["columnIndex"], v["rowIndex"]) for v in b["mountingHoles"]}
    nx = int((w - 2 * edge) // pitch) + 1
    ny = int((h - 2 * edge) // pitch) + 1
    grid_total = nx * ny
    thread_count = grid_total - len(fixed)

    cb_rows = []
    for j in range(ny):
        for i in range(nx):
            if (i, j) in fixed:
                cb_rows.append((f"H{len(cb_rows) + 1}", edge + i * pitch, edge + j * pitch, i, j))
    cutouts = l.get("boardCutouts", [])

    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 420 297">',
        '<defs>',
        '<marker id="arrow-e" viewBox="0 0 10 4" refX="10" refY="2" markerWidth="2.6" markerHeight="1.2" orient="auto">'
        '<path d="M0,0 L10,2 L0,4 Z" fill="#111"/></marker>',
        '<marker id="arrow-s" viewBox="0 0 10 4" refX="0" refY="2" markerWidth="2.6" markerHeight="1.2" orient="auto">'
        '<path d="M10,0 L0,2 L10,4 Z" fill="#111"/></marker>',
        '</defs>',
        '<rect x="6" y="6" width="408" height="285" fill="#fff" stroke="#111" stroke-width="0.45"/>',
        '<line x1="280" y1="6" x2="280" y2="291" stroke="#111" stroke-width="0.28"/>',
        '<g font-family="sans-serif" fill="#111">',
    ]

    # 1. Front View (Main view, w x t) aligned above Top View.
    svg.append(f'<text x="{vx:g}" y="{vy_front - 3.2:g}" font-size="3.0" font-weight="600">主视图 ({scale_text})</text>')
    svg.append(f'<rect x="{vx:g}" y="{vy_front:g}" width="{sw:g}" height="{st:g}" fill="none" stroke="#111" stroke-width="0.35"/>')
    seen_x = set()
    for _, hx, _, _, _ in cb_rows:
        key = round(hx, 3)
        if key in seen_x:
            continue
        seen_x.add(key)
        cx_v = vx + hx * s
        r_cb = 5.5 * s
        r_th = 3.3 * s
        depth_v = min(6.5, t) * s
        svg.append(
            f'<line x1="{cx_v:g}" y1="{vy_front - 1.5:g}" x2="{cx_v:g}" y2="{vy_front + st + 1.5:g}" '
            f'stroke="#c0392b" stroke-width="0.16" stroke-dasharray="2 0.7 0.4 0.7"/>'
        )
        for dx in (-r_cb, r_cb):
            svg.append(
                f'<line x1="{cx_v + dx:g}" y1="{vy_front:g}" x2="{cx_v + dx:g}" y2="{vy_front + depth_v:g}" '
                f'stroke="#444" stroke-width="0.2" stroke-dasharray="1.2 0.7"/>'
            )
        svg.append(
            f'<line x1="{cx_v - r_cb:g}" y1="{vy_front + depth_v:g}" x2="{cx_v + r_cb:g}" y2="{vy_front + depth_v:g}" '
            f'stroke="#444" stroke-width="0.2" stroke-dasharray="1.2 0.7"/>'
        )
        for dx in (-r_th, r_th):
            svg.append(
                f'<line x1="{cx_v + dx:g}" y1="{vy_front + depth_v:g}" x2="{cx_v + dx:g}" y2="{vy_front + st:g}" '
                f'stroke="#444" stroke-width="0.2" stroke-dasharray="1.2 0.7"/>'
            )
    if side in ("south", "north"):
        svg.append(
            f'<g transform="translate({vx + tx_side * s:g} {vy_front + ty_side * s:g}) scale({logo_scale * s:g})">{artwork}</g>'
        )
    svg.append(_dim_v(vy_front, vy_front + st, vx + sw + 6.5, vx + sw, vx + sw, f"{t:g}"))

    # 2. Top View (w x h) directly below Front View (First-Angle Projection).
    svg.append(f'<text x="{vx:g}" y="{vy_top - 4.0:g}" font-size="3.0" font-weight="600">俯视图 ({scale_text})</text>')
    svg.append(f'<rect x="{vx:g}" y="{vy_top:g}" width="{sw:g}" height="{sh:g}" fill="none" stroke="#111" stroke-width="0.35"/>')
    svg.append(f'<circle cx="{vx:g}" cy="{vy_top + sh:g}" r="1.2" fill="none" stroke="#111" stroke-width="0.25"/>')
    svg.append(f'<text x="{vx + 2.0:g}" y="{vy_top + sh + 4.0:g}" font-size="2.4" font-weight="600">基准 A/B (0,0)</text>')

    svg.append(f'<g transform="translate({vx:g} {vy_top:g}) scale({s:g})" opacity="0.52">{top_marks_str}</g>')

    cb_index_by_ij = {(i, j): code for code, _, _, i, j in cb_rows}
    rep_thread = None
    best_score = -1e9
    for j in range(ny):
        for i in range(nx):
            hx = edge + i * pitch
            hy = edge + j * pitch
            cx_v = vx + hx * s
            cy_v = vy_top + (h - hy) * s
            is_cb = (i, j) in fixed
            if is_cb:
                svg.append(f'<circle cx="{cx_v:g}" cy="{cy_v:g}" r="{3.3 * s:g}" fill="none" stroke="#111" stroke-width="0.22"/>')
                svg.append(f'<circle cx="{cx_v:g}" cy="{cy_v:g}" r="{5.5 * s:g}" fill="none" stroke="#111" stroke-width="0.28"/>')
                ch = max(5.5 * s + 1.5, 2.8)
                svg.append(
                    f'<line x1="{cx_v - ch:g}" y1="{cy_v:g}" x2="{cx_v + ch:g}" y2="{cy_v:g}" stroke="#c0392b" stroke-width="0.16" stroke-dasharray="2 0.7 0.4 0.7"/>'
                    f'<line x1="{cx_v:g}" y1="{cy_v - ch:g}" x2="{cx_v:g}" y2="{cy_v + ch:g}" stroke="#c0392b" stroke-width="0.16" stroke-dasharray="2 0.7 0.4 0.7"/>'
                )
                code = cb_index_by_ij[(i, j)]
                svg.append(
                    f'<text x="{cx_v + 5.5 * s + 0.8:g}" y="{cy_v - 1.0:g}" font-size="2.3" font-weight="600" fill="#111">{code}</text>'
                )
            else:
                svg.append(f'<circle cx="{cx_v:g}" cy="{cy_v:g}" r="{2.5 * s:g}" fill="none" stroke="#666" stroke-width="0.18"/>')
                if i in (0, nx - 1) and j in (0, ny - 1):
                    ch = max(2.5 * s + 1.3, 2.2)
                    svg.append(
                        f'<line x1="{cx_v - ch:g}" y1="{cy_v:g}" x2="{cx_v + ch:g}" y2="{cy_v:g}" stroke="#c0392b" stroke-width="0.14"/>'
                        f'<line x1="{cx_v:g}" y1="{cy_v - ch:g}" x2="{cx_v:g}" y2="{cy_v + ch:g}" stroke="#c0392b" stroke-width="0.14"/>'
                    )
                score = i * 10 + j
                if score > best_score:
                    best_score = score
                    rep_thread = (cx_v, cy_v)

    for idx_c, c in enumerate(cutouts, 1):
        cx_c, cy_c = vx + c["center"][0] * s, vy_top + (h - c["center"][1]) * s
        rc = c["diameterMm"] / 2 * s
        svg.append(f'<circle cx="{cx_c:g}" cy="{cy_c:g}" r="{rc:g}" fill="none" stroke="#111" stroke-width="0.28"/>')
        svg.append(
            f'<line x1="{cx_c - rc - 1.5:g}" y1="{cy_c:g}" x2="{cx_c + rc + 1.5:g}" y2="{cy_c:g}" stroke="#c0392b" stroke-width="0.16"/>'
            f'<line x1="{cx_c:g}" y1="{cy_c - rc - 1.5:g}" x2="{cx_c:g}" y2="{cy_c + rc + 1.5:g}" stroke="#c0392b" stroke-width="0.16"/>'
        )
        svg.append(f'<text x="{cx_c + rc + 1.0:g}" y="{cy_c + 1.0:g}" font-size="2.3" font-weight="600">C{idx_c}</text>')

    # Top View dimension chains (edge offset placed cleanly at bottom-right/top-right away from title).
    svg.append(_dim_v(vy_top, vy_top + sh, vx - 13.0, vx, vx, f"{h:g}"))
    if ny >= 2:
        y_first = vy_top + (h - edge) * s
        y_last = vy_top + (h - (edge + (ny - 1) * pitch)) * s
        svg.append(_dim_v(y_last, y_first, vx - 6.0, vx + edge * s, vx + edge * s, f"{ny - 1}×{pitch:g}={(ny - 1) * pitch:g}", 2.4))
    svg.append(_dim_h(vx, vx + sw, vy_top + sh + 14.5, vy_top + sh, vy_top + sh, f"{w:g}"))
    if nx >= 2:
        x_first = vx + edge * s
        x_last = vx + (edge + (nx - 1) * pitch) * s
        svg.append(_dim_h(x_first, x_last, vy_top + sh + 7.5, vy_top + sh - edge * s, vy_top + sh - edge * s, f"{nx - 1}×{pitch:g}={(nx - 1) * pitch:g}", 2.4))
    # Edge offset at top-right of Top View, well away from "俯视图" label at top-left.
    svg.append(_dim_h(vx + sw - edge * s, vx + sw, vy_top - 4.0, vy_top + edge * s, vy_top, f"边距 {edge:g}", 2.3))

    # Compact leader callouts to the right of Top View.
    kx_land = vx + sw + 7.0
    ex_land = min(277.0, kx_land + 34.0)
    if rep_thread:
        svg.append(_leader(rep_thread[0], rep_thread[1], kx_land, vy_top + 14.0, ex_land, [f"{thread_count}× M6-6H"]))
    if cb_rows:
        _, h0x, h0y, _, _ = max(cb_rows, key=lambda r: (r[1], -r[2]))
        svg.append(
            _leader(
                vx + h0x * s,
                vy_top + (h - h0y) * s,
                kx_land,
                vy_top + 36.0,
                ex_land,
                [f"{len(cb_rows)}× Ø6.6 通", "沉孔 Ø11 深6.5"],
            )
        )

    # 3. Bottom-left details: A-A Counterbore Section (2:1) + Outward Sidewall Logo Detail.
    dy_box = 207.0
    svg.append(f'<rect x="14" y="{dy_box:g}" width="88" height="78" fill="none" stroke="#999" stroke-width="0.22" stroke-dasharray="3 1.5"/>')
    svg.append(f'<text x="17" y="{dy_box + 5.5:g}" font-size="3.0" font-weight="600">局部剖视 A-A (沉孔 2:1)</text>')
    ds = 2.0
    dx0, dy0 = 33.0, dy_box + 22.0
    bw_d, bt_d = 24.0 * ds, t * ds
    r_cb_d, r_th_d, d_cb_d = 5.5 * ds, 3.3 * ds, min(6.5, t) * ds
    cx_d = dx0 + bw_d / 2
    # Section halves with explicit 45-deg vector hatch lines (universally compatible).
    left_outer_w = (cx_d - r_cb_d) - dx0
    left_step_w = (cx_d - r_th_d) - (cx_d - r_cb_d)
    right_step_x = cx_d + r_th_d
    right_outer_x = cx_d + r_cb_d
    svg.append(_hatch_rect(dx0, dy0, left_outer_w, bt_d))
    svg.append(_hatch_rect(cx_d - r_cb_d, dy0 + d_cb_d, left_step_w, bt_d - d_cb_d))
    svg.append(_hatch_rect(right_step_x, dy0 + d_cb_d, left_step_w, bt_d - d_cb_d))
    svg.append(_hatch_rect(right_outer_x, dy0, left_outer_w, bt_d))
    svg.append(
        f'<polygon points="{dx0:g},{dy0:g} {cx_d - r_cb_d:g},{dy0:g} {cx_d - r_cb_d:g},{dy0 + d_cb_d:g} '
        f'{cx_d - r_th_d:g},{dy0 + d_cb_d:g} {cx_d - r_th_d:g},{dy0 + bt_d:g} {dx0:g},{dy0 + bt_d:g}" '
        f'fill="none" stroke="#111" stroke-width="0.32"/>'
        f'<polygon points="{cx_d + r_cb_d:g},{dy0:g} {dx0 + bw_d:g},{dy0:g} {dx0 + bw_d:g},{dy0 + bt_d:g} '
        f'{cx_d + r_th_d:g},{dy0 + bt_d:g} {cx_d + r_th_d:g},{dy0 + d_cb_d:g} {cx_d + r_cb_d:g},{dy0 + d_cb_d:g}" '
        f'fill="none" stroke="#111" stroke-width="0.32"/>'
        f'<line x1="{cx_d - r_cb_d:g}" y1="{dy0:g}" x2="{cx_d + r_cb_d:g}" y2="{dy0:g}" stroke="#111" stroke-width="0.22"/>'
        f'<line x1="{cx_d - r_th_d:g}" y1="{dy0 + bt_d:g}" x2="{cx_d + r_th_d:g}" y2="{dy0 + bt_d:g}" stroke="#111" stroke-width="0.22"/>'
        f'<line x1="{cx_d:g}" y1="{dy0 - 3:g}" x2="{cx_d:g}" y2="{dy0 + bt_d + 3:g}" stroke="#c0392b" stroke-width="0.18" stroke-dasharray="2 0.7 0.4 0.7"/>'
    )
    svg.append(_dim_h(cx_d - r_cb_d, cx_d + r_cb_d, dy0 - 6.0, dy0, dy0, "Ø11", 2.5))
    svg.append(_dim_h(cx_d - r_th_d, cx_d + r_th_d, dy0 + bt_d + 6.5, dy0 + bt_d, dy0 + bt_d, "Ø6.6", 2.5))
    svg.append(_dim_v(dy0, dy0 + d_cb_d, dx0 + bw_d + 5.5, cx_d + r_cb_d, cx_d + r_cb_d, "6.5", 2.5))
    svg.append(_dim_v(dy0, dy0 + bt_d, dx0 - 5.5, dx0, dx0, f"{t:g}", 2.5))
    svg.append(f'<text x="17" y="{dy_box + 73.5:g}" font-size="2.4">沉孔上口及通孔底口倒角 C0.3×45°</text>')

    # 3b. Sidewall HKSOP Logo placement detail (x=106..276, y=207..285)
    svg.append(f'<rect x="106" y="{dy_box:g}" width="170" height="78" fill="none" stroke="#999" stroke-width="0.22" stroke-dasharray="3 1.5"/>')
    svg.append(f'<text x="109" y="{dy_box + 5.5:g}" font-size="3.0" font-weight="600">外侧壁 ({side}) HKSOP 激光打标局部定位</text>')
    ls_det = min(24.0 / t, 118.0 / max(logo_scale * iw + 16.0, 40.0))
    wall_show_mm = min(length, (logo_scale * iw + 14.0))
    wall_px_w = wall_show_mm * ls_det
    wall_px_h = t * ls_det
    wx0, wy0 = 120.0, dy_box + 23.0
    svg.append(
        f'<rect x="{wx0:g}" y="{wy0:g}" width="{wall_px_w:g}" height="{wall_px_h:g}" fill="none" stroke="#111" stroke-width="0.32"/>'
    )
    dx_logo = wall_show_mm - 3.0 - logo_scale * (ix + iw)
    svg.append(
        f'<g transform="translate({wx0 + dx_logo * ls_det:g} {wy0 + ty_side * ls_det:g}) scale({logo_scale * ls_det:g})">{artwork}</g>'
    )
    svg.append(_dim_h(wx0 + wall_px_w - 3.0 * ls_det, wx0 + wall_px_w, wy0 + wall_px_h + 7.5, wy0 + wall_px_h, wy0 + wall_px_h, "3", 2.5))
    # Clear vertical 1.5 mm labels to the right of the wall without colliding with extension lines.
    x_ext_r = wx0 + wall_px_w + 5.0
    svg.append(
        f'<line x1="{wx0 + wall_px_w:g}" y1="{wy0:g}" x2="{x_ext_r + 2:g}" y2="{wy0:g}" stroke="#111" stroke-width="0.16"/>'
        f'<line x1="{wx0 + wall_px_w:g}" y1="{wy0 + 1.5 * ls_det:g}" x2="{x_ext_r + 2:g}" y2="{wy0 + 1.5 * ls_det:g}" stroke="#111" stroke-width="0.16"/>'
        f'<line x1="{x_ext_r:g}" y1="{wy0:g}" x2="{x_ext_r:g}" y2="{wy0 + 1.5 * ls_det:g}" stroke="#111" stroke-width="0.2"/>'
        f'<text x="{x_ext_r + 2.6:g}" y="{wy0 + 1.5 * ls_det / 2 + 0.9:g}" font-size="2.4">上下各 1.5</text>'
        f'<line x1="{wx0 + wall_px_w:g}" y1="{wy0 + wall_px_h - 1.5 * ls_det:g}" x2="{x_ext_r + 2:g}" y2="{wy0 + wall_px_h - 1.5 * ls_det:g}" stroke="#111" stroke-width="0.16"/>'
        f'<line x1="{wx0 + wall_px_w:g}" y1="{wy0 + wall_px_h:g}" x2="{x_ext_r + 2:g}" y2="{wy0 + wall_px_h:g}" stroke="#111" stroke-width="0.16"/>'
        f'<line x1="{x_ext_r:g}" y1="{wy0 + wall_px_h - 1.5 * ls_det:g}" x2="{x_ext_r:g}" y2="{wy0 + wall_px_h:g}" stroke="#111" stroke-width="0.2"/>'
        f'<text x="{x_ext_r + 2.6:g}" y="{wy0 + wall_px_h - 1.5 * ls_det / 2 + 0.9:g}" font-size="2.4">1.5</text>'
    )
    svg.append(f'<text x="109" y="{dy_box + 73.5:g}" font-size="2.4">完整黑白 Logo 随附 side-marking DXF（1:1 mm，距右 3 mm，上下各 1.5 mm）</text>')

    # 4. Right Column: Counterbore / Cutout Table (NO full regular M6 grid table!)
    rx = 285.0
    svg.append(f'<text x="{rx:g}" y="14.5" font-size="3.1" font-weight="600">固定沉孔及非规则孔坐标表（左下角基准）</text>')
    table_rows = [(code, f"{hx:g}", f"{hy:g}", "Ø6.6 通 / 沉孔 Ø11 深6.5") for code, hx, hy, _, _ in cb_rows]
    for idx_c, c in enumerate(cutouts, 1):
        table_rows.append((f"C{idx_c}", f"{c['center'][0]:g}", f"{c['center'][1]:g}", f"Ø{c['diameterMm']:g} 通"))
    ty = 18.0
    row_h = min(5.2, 122.0 / max(len(table_rows) + 1, 2))
    cols = [rx, rx + 15, rx + 39, rx + 63, rx + 123]
    svg.append(f'<rect x="{rx:g}" y="{ty:g}" width="123" height="{row_h:g}" fill="#f2f4f5" stroke="#111" stroke-width="0.24"/>')
    for cx_t, hdr in zip(cols[:-1], ["孔号", "X (mm)", "Y (mm)", "孔规格"]):
        svg.append(f'<text x="{cx_t + 1.8:g}" y="{ty + row_h * 0.72:g}" font-size="2.4" font-weight="600">{hdr}</text>')
    for idx_r, (c_id, x_s, y_s, spec) in enumerate(table_rows, 1):
        ry = ty + idx_r * row_h
        if ry + row_h > 147.0:
            svg.append(f'<text x="{rx + 2:g}" y="{ry + 3.2:g}" font-size="2.3">… 其余 {len(table_rows) - idx_r + 1} 孔见同版 3D STEP</text>')
            break
        svg.append(f'<rect x="{rx:g}" y="{ry:g}" width="123" height="{row_h:g}" fill="none" stroke="#111" stroke-width="0.2"/>')
        for cx_t, val in zip(cols[:-1], [c_id, x_s, y_s, spec]):
            svg.append(f'<text x="{cx_t + 1.8:g}" y="{ry + row_h * 0.72:g}" font-size="2.2">{escape(val)}</text>')
    for cx_line in cols[1:-1]:
        max_y = min(ty + (len(table_rows) + 1) * row_h, 147.0)
        svg.append(f'<line x1="{cx_line:g}" y1="{ty:g}" x2="{cx_line:g}" y2="{max_y:g}" stroke="#111" stroke-width="0.2"/>')

    # 5. Technical Notes (<= 5 concise machining lines).
    ny_box = 152.0
    svg.append(f'<text x="{rx:g}" y="{ny_box + 4:g}" font-size="3.1" font-weight="600">技术要求</text>')
    notes = [
        "1. 未注尺寸公差按 GB/T 1804-m（ISO 2768-m）。",
        "2. 默认表面粗糙度 Ra 3.2，基准面按要求。",
        "3. 未注锐边去毛刺；外棱及沉孔口 C0.3×45°。",
        "4. 全部 M6 孔按 M6-6H 攻牙，节距不缩放。",
        "5. 表面黑色阳极氧化后白色激光打标（1:1 DXF）。",
    ]
    for idx_n, line in enumerate(notes):
        svg.append(f'<text x="{rx:g}" y="{ny_box + 10.5 + idx_n * 6.0:g}" font-size="2.5">{escape(line)}</text>')

    # 6. Fixed Bottom-Right GB Standard Title Block (x=280..414, y=223..291).
    tx0, ty0, tw, th = 280.0, 223.0, 134.0, 68.0
    svg.append(f'<rect x="{tx0:g}" y="{ty0:g}" width="{tw:g}" height="{th:g}" fill="#fff" stroke="#111" stroke-width="0.4"/>')
    for y_sep in (239.0, 252.0, 265.0, 278.0):
        svg.append(f'<line x1="{tx0:g}" y1="{y_sep:g}" x2="{tx0 + tw:g}" y2="{y_sep:g}" stroke="#111" stroke-width="0.25"/>')
    for x_sep, y_top, y_bot in (
        (376.0, 223.0, 239.0),
        (332.0, 239.0, 291.0),
        (378.0, 239.0, 265.0),
    ):
        svg.append(f'<line x1="{x_sep:g}" y1="{y_top:g}" x2="{x_sep:g}" y2="{y_bot:g}" stroke="#111" stroke-width="0.25"/>')

    pname = str(p["metadata"]["name"])
    if len(pname) > 22:
        pname = pname[:21] + "…"
    material = str(b.get("material", "6061-T6 铝合金"))
    finish = str(b.get("surfaceTreatment", "黑色阳极氧化 / 白色镭雕"))
    svg.extend([
        f'<text x="{tx0 + 2.5:g}" y="229.0" font-size="2.2" fill="#555">名称 / 图号</text>',
        f'<text x="{tx0 + 2.5:g}" y="235.5" font-size="3.1" font-weight="600">{escape(pname)}</text>',
        f'<text x="378.5" y="229.0" font-size="2.2" fill="#555">页码</text>',
        f'<text x="395.0" y="235.5" font-size="3.0" text-anchor="middle" font-weight="600">1 / 1</text>',
        f'<text x="{tx0 + 2.5:g}" y="244.0" font-size="2.1" fill="#555">规格 (mm)</text>',
        f'<text x="{tx0 + 2.5:g}" y="249.5" font-size="2.7">{w:g} × {h:g} × {t:g}</text>',
        f'<text x="334.5" y="244.0" font-size="2.1" fill="#555">数量</text>',
        f'<text x="355.0" y="249.5" font-size="2.8" text-anchor="middle">1 件</text>',
        f'<text x="380.5" y="244.0" font-size="2.1" fill="#555">比例</text>',
        f'<text x="396.0" y="249.5" font-size="2.8" text-anchor="middle">{scale_text}</text>',
        f'<text x="{tx0 + 2.5:g}" y="257.0" font-size="2.1" fill="#555">材料</text>',
        f'<text x="{tx0 + 2.5:g}" y="262.5" font-size="2.6">{escape(material)}</text>',
        f'<text x="334.5" y="257.0" font-size="2.1" fill="#555">表面处理</text>',
        f'<text x="334.5" y="262.5" font-size="2.2">{escape(finish[:18])}</text>',
        f'<text x="380.5" y="257.0" font-size="2.1" fill="#555">单位</text>',
        f'<text x="396.0" y="262.5" font-size="2.8" text-anchor="middle">mm</text>',
        f'<text x="{tx0 + 2.5:g}" y="270.0" font-size="2.1" fill="#555">未注公差</text>',
        f'<text x="{tx0 + 2.5:g}" y="275.5" font-size="2.7" font-weight="600">GB/T 1804-m</text>',
        f'<text x="334.5" y="270.0" font-size="2.1" fill="#555">默认粗糙度 / 螺纹</text>',
        f'<text x="334.5" y="275.5" font-size="2.7" font-weight="600">Ra 3.2  /  内螺纹 6H</text>',
        f'<text x="{tx0 + 2.5:g}" y="283.0" font-size="2.1" fill="#555">投影法</text>',
        f'<text x="{tx0 + 2.5:g}" y="288.5" font-size="2.6" font-weight="600">第一角法 (GB)</text>',
        _first_angle_symbol(383.0, 284.5),
    ])

    svg.append("</g></svg>\n")
    filename.write_text("".join(svg))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("project", type=Path)
    p.add_argument("ledger", type=Path)
    p.add_argument("labels", type=Path)
    p.add_argument("-o", type=Path, required=True)
    p.add_argument("--marking-dir", type=Path)
    a = p.parse_args()
    try:
        drawing(a.project, a.ledger, a.labels, Path(__file__).resolve().parents[1] / "references/logo/hksop-logo-mono.svg", a.o, a.marking_dir)
    except (KeyError, OSError, ValueError) as e:
        sys.exit(str(e))
