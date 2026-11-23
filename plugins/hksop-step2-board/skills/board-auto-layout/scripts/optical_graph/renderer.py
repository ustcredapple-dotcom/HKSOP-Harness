"""Self-contained SVG diagrams and an offline tabbed HTML gallery."""
from collections import defaultdict
from html import escape
from math import hypot
from pathlib import Path
import json
import os
import tempfile

from . import schema as s
from .schematic_layout import Rect, schematic_layout, segment_box

INK, LENS, ACCENT = "#1d3743", "#d6efee", "#106773"
COLORS = {399: "#6441b0", 461: "#2859bf", 532: "#168148", 780: "#be3840", 1064: "#b7610b"}
LEVELS = {"INFO": 0, "WARNING": 1, "ERROR": 2}


def esc(value):
    return escape(str(value), quote=True)


def fmt(x):
    return f"{x:.4f}".rstrip("0").rstrip(".") if x else "0"


def wave_color(nm):
    if nm in COLORS:
        return COLORS[nm]
    return "#6a45a8" if nm < 450 else "#166eaa" if nm < 500 else "#177844" if nm < 575 else "#b46803" if nm < 620 else "#b2353a"


def points_text(points):
    return " ".join(f"{fmt(x)},{fmt(y)}" for x, y in points)


def rect(box, **attrs):
    options = " ".join(f'{key}="{esc(value)}"' for key, value in attrs.items())
    return f'<rect x="{fmt(box.x)}" y="{fmt(box.y)}" width="{fmt(box.w)}" height="{fmt(box.h)}" {options}/>'


def svg_text(x, y, value, style="", extra=""):
    return f'<text x="{fmt(x)}" y="{fmt(y)}" class="{style}" {extra}>{esc(value)}</text>'


def path(d, **attrs):
    options = " ".join(f'{key}="{esc(value)}"' for key, value in attrs.items())
    return f'<path d="{d}" {options}/>'


def _symbol(c, computed):
    if isinstance(c, s.SOURCES):
        body = path("M-24 -14 H8 L16 -8 V8 L8 14 H-24 Z M16 -6 H24 V6 H16", fill="#e3f1ec")
        detail = "M-19 0 Q-16 -10 -13 0 T-7 0 T-1 0" if isinstance(c, s.LaserSource) else "M-25 9 C-13 12 -13 -11 -1 -7"
        return body+path(detail)
    if isinstance(c, s.Four):
        return path("M-20 -20 H20 V20 H-20 Z", fill=LENS)+path("M-19 -19 L19 19", stroke=ACCENT, **{"stroke-width": 3})
    if isinstance(c, s.Lens):
        side = computed.get("convex_toward", c.convex_toward)
        shape = {"a": "M5 -24 Q-17 0 5 24 Z", "b": "M-5 -24 Q17 0 -5 24 Z"}.get(side, "M0 -24 Q-18 0 0 24 Q18 0 0 -24Z")
        return path(shape, fill=LENS)
    if isinstance(c, (s.HalfWaveplate, s.QuarterWaveplate, s.DualWaveplate)):
        glyph = path("M-6 -21 L5 -24 L8 21 L-3 24 Z M-3 -15 L4 -17 M-2 -9 L4 -11", fill="#ece4f6")
        return glyph if not isinstance(c, s.DualWaveplate) else '<g transform="translate(-6)">'+glyph+'</g><g transform="translate(7)">'+glyph+'</g>'
    if isinstance(c, s.AOM):
        return path("M-23 -14 L16 -18 L23 14 L-16 18 Z", fill="#f8ecd6")+path("M-16 4 L-11 -5 L-6 4 L-1 -5 L4 4 L9 -5 L14 4")
    if isinstance(c, s.Isolator):
        return path("M-22 -16 H22 V16 H-22Z", fill="#e5ecec")+path("M-15 0 H8 M1 -7 L9 0 L1 7 M13 -10 V10")
    if isinstance(c, s.RetroMirror):
        return path("M6 -21 V21 M7 -17 L15 -23 M7 -8 L15 -14 M7 1 L15 -5 M7 10 L15 4 M7 19 L15 13")
    if isinstance(c, s.BeamDump):
        glyph = path("M-22 -17 H20 V17 H-22Z", fill=INK)+path("M23 -12 L9 -7 L19 -2 L7 4 L19 9 L6 13", stroke="#fcfbf7")
        return glyph + (path("M-15 -5 H-10 V5 H-15Z", fill="#67d1b1") if c.monitor_pd else "")
    if isinstance(c, s.FiberCoupler):
        return path("M23 -15 L9 -12 L-1 -6 H-14 V6 H-1 L9 12 L23 15 Z", fill=LENS)+path("M-14 0 Q-22 0 -22 7 T-30 13")
    if isinstance(c, s.Photodiode):
        return path("M20 -16 H-18 V16 H20Z", fill="#e5ecec")+path("M12 -8 L-2 0 L12 8 Z M-4 -9 V9")
    if isinstance(c, s.Camera):
        return path("M-21 -15 H13 V-8 L23 -12 V12 L13 8 V15 H-21Z", fill="#e5ecec")+path("M-14 -6 H3 V6 H-14Z")
    if isinstance(c, s.TargetPlane):
        return '<circle r="18" fill="#e9f3e4"/><circle r="9"/>'+path("M-24 0 H-12 M12 0 H24 M0 -24 V-12 M0 12 V24")
    if isinstance(c, s.Aperture):
        return path("M-4 -23 H4 V-6 H-4Z M-4 6 H4 V23 H-4Z", fill=INK)
    if isinstance(c, s.Window):
        return path("M-6 -23 H6 V23 H-6Z M-5 -9 L5 -17 M-5 -2 L5 -10", fill=LENS)
    if isinstance(c, s.HeightShift):
        return path("M-24 9 H-7 V-9 H24 M-14 15 L0 2 M-14 -2 L0 -15", stroke=ACCENT)
    if isinstance(c, s.VerticalFold):
        mark = path("M-7 -7 L7 7 M-7 7 L7 -7") if c.direction == "down" else '<circle r="4" fill="#1d3743"/>'
        return '<circle r="18" fill="#e1eeef"/>'+mark
    if isinstance(c, s.SpatialFold):
        return path("M-22 10 H-5 L20 -13 M7 -13 H20 V0 M-14 -2 L0 13", stroke=ACCENT)
    return path("M-22 -15 Q-25 0 -22 15 H22 Q25 0 22 -15 Z M-15 -13 V13 M15 -13 V13", fill="#f1ecd9")


def _caption(c, computed):
    if isinstance(c, s.SOURCES):
        return f"{'Fiber' if isinstance(c,s.FiberSource) else 'Laser'} · {c.wavelength_nm:g} nm"
    if isinstance(c, s.Lens):
        return f"Lens · f {c.f_mm:g} mm"
    if isinstance(c, s.DualWaveplate):
        return "λ/4 → λ/2" if c.order == "QWP_HWP" else "λ/2 → λ/4"
    if isinstance(c, (s.HalfWaveplate, s.QuarterWaveplate)):
        short = "HWP" if isinstance(c, s.HalfWaveplate) else "QWP"
        angle = computed.get("resolved_fast_axis_deg", c.fast_axis_deg)
        return f"{short} · {angle:.2f}°" if angle is not None else short
    if isinstance(c, s.AOM):
        return f"AOM · {c.rf_mhz:g} MHz"
    if isinstance(c, s.VerticalFold):
        return "⊗ DOWN (−Z)" if c.direction == "down" else "⊙ UP (+Z)"
    if isinstance(c, s.SpatialFold):
        return f"3D fold · {c.pitch_deg:g}°"
    if isinstance(c, s.HeightShift):
        return f"Height · {c.in_height_mm:g}→{c.out_height_mm:g}"
    if isinstance(c, s.Window):
        return f"{c.material} · {c.thickness_mm:g} mm"
    return type(c).__name__


def _offset(points, offset):
    normals = []
    for a, b in zip(points, points[1:]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        d = hypot(dx, dy)
        normals.append((-dy/d, dx/d))
    result = []
    for i, (x, y) in enumerate(points):
        left = normals[max(0, i-1)]
        right = normals[min(i, len(normals)-1)]
        normal = left if left == right else (left[0]+right[0], left[1]+right[1])
        result.append((x+normal[0]*offset, y+normal[1]*offset))
    return result


def _track(link, points, rays):
    groups = {}
    for beam in rays:
        r = beam["start"]
        tag = f"{r['pol_angle_deg']:+.0f}°" if r["pol"] == "linear" else r["pol"]
        key = (beam["from"], r["wavelength_nm"], r["freq_shift_mhz"], tag)
        groups.setdefault(key, r)
    if not groups:
        return f'<polyline class="dark-path" points="{points_text(points)}"/>', []
    primary = next(iter(groups))[0]
    multicolor = len({k[1] for k in groups}) > 1
    layers, labels = [], []
    for i, ((out, nm, shift, pol), r) in enumerate(groups.items()):
        color = wave_color(nm)
        rail = _offset(points, 6*(i-(len(groups)-1)/2))
        if out != link.u:
            rail.reverse()
        rev = out != primary
        # Place the arrow on an actual Manhattan segment, including bent return arms.
        a, b = max(zip(rail, rail[1:]), key=lambda p: hypot(p[1][0]-p[0][0], p[1][1]-p[0][1]))
        dx, dy = b[0]-a[0], b[1]-a[1]
        d = hypot(dx, dy)
        ux, uy = dx/d, dy/d
        x, y = a[0]+.69*dx, a[1]+.69*dy
        tri = [(x+5*ux,y+5*uy),(x-5*ux-4*uy,y-5*uy+4*ux),(x-5*ux+4*uy,y-5*uy-4*ux)]
        dash = ' stroke-dasharray="6 4"' if rev else ""
        layers.append(f'<g class="beam-track" data-from="{esc(out)}" data-return="{str(rev).lower()}">'
                      f'<title>{esc(out)} · {nm:g} nm · {esc(pol)} · {shift:+g} MHz · {r["power_mw"]:.4g} mW</title>'
                      f'<polyline points="{points_text(rail)}" stroke="{color}"{dash}/>'
                      f'<polygon points="{points_text(tri)}" fill="{color}"/></g>')
        band = f"{nm:g} nm · " if multicolor else ""
        labels.append((color, ("↶ " if rev else "")+band+f"{pol} · {shift:+g} MHz"))
    return "".join(layers), labels


SVG_STYLE = """
text{font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;fill:#1d3743}
.sym{stroke:#254850;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round;fill:none}
.caption-id{font-size:16px;font-weight:720}.caption-type{font-size:11.5px;fill:#47636d}
.port-name{font:8px monospace;fill:#4d6572;paint-order:stroke;stroke:#fcfbf7;stroke-width:2px}
.beam-track polyline,.dark-path,.halo-line,.pick-line{fill:none;stroke-width:2.8;stroke-linejoin:round}
.dark-path{stroke:#9ca9ac;stroke-width:1.5;stroke-dasharray:3 5}
.halo-line{stroke-width:13;opacity:.24}.error .halo-line{stroke:#d22333}.warning .halo-line{stroke:#ea8a15}
.halo{stroke-width:2;fill-opacity:.14}.error .halo{fill:#fc4a55;stroke:#ce2431}.warning .halo{fill:#ffab2f;stroke:#bd740c}.error.warning .halo{fill:#fc4a55;stroke:#ce2431}
.pick-line{stroke:transparent;stroke-width:15}.symbol-target.selected .halo,.symbol-target:target .halo{stroke-width:4}
.symbol-target.selected .node-ring,.symbol-target:target .node-ring{stroke:#007c88;stroke-width:3;stroke-dasharray:4 3}
.symbol-target.selected .pick-line,.symbol-target:target .pick-line{stroke:#007c88;opacity:.38}
.note-box{fill:#fcfbf7;stroke:#c2cdcb;stroke-width:1}.constraint{font:600 11px monospace}.beam-note{font:10.6px monospace}
.span-note{font:600 12px monospace;fill:#366c77}.span-bracket{stroke:#47838d;stroke-width:1.6;fill:none}
.symbol-target.selected .span-bracket{stroke:#007c88;stroke-width:3}.span-error .span-bracket{stroke:#ce2431}
"""


def _level_class(diagnostics):
    return max((d["level"] for d in diagnostics), key=LEVELS.get, default="").lower()


def render_svg(graph, data=None, prefix="og"):
    data = data if data is not None else graph.to_dict(include_trace=True)
    trace, layout = data["trace"], schematic_layout(graph)
    by_link, by_target = defaultdict(list), defaultdict(list)
    for ray in trace["beams"]:
        by_link[ray["link_id"]].append(ray)
    for diag in trace["diagnostics"]:
        by_target[diag["target_kind"], diag["target"]].append(diag)
    reserved = list(layout.obstacles)
    strokes = [segment_box(a,b,5) for route in layout.routes.values() for a,b in zip(route, route[1:])]
    layers, annotations, symbols = [], [], []
    for link in graph.links:
        coords = layout.routes[link.id]
        diag = by_target["link",link.id]
        level = _level_class(diag)
        poly = points_text(coords)
        payload, labels = _track(link, coords, by_link[link.id])
        start = f'<g id="{prefix}-link-{esc(link.id)}" class="symbol-target link {level}" data-link="{esc(link.id)}" data-u="{esc(link.u)}" data-v="{esc(link.v)}">'
        tip = f'{link.u} ↔ {link.v} · {trace["links"][link.id]["resolved_air_mm"]:.3f} mm'
        layers.append(start+f'<title>{esc(tip)} {esc(link.note)}</title><polyline class="pick-line" points="{poly}"/>'
                      +(f'<polyline class="halo-line" points="{poly}"/>' if level in ("error","warning") else "")+payload+'</g>')
        exact = link.exact_mm is not None
        length = (f"{link.exact_mm:g}±{link.tol_mm:g} mm" if exact else f"{link.min_mm:g}–{link.max_mm:g} mm")
        width = max(len(length)*7.1+28, *(len(t)*6.45+24 for _,t in labels), 82)
        height = 21+14*len(labels)
        box, anchor = layout.badge(coords,width,height,reserved,strokes)
        x, y = box.x+8, box.y+14
        g = [f'<g class="link-badge" data-for="{esc(link.id)}"><title>{esc(tip)}</title>']
        # A leader appears only if a crowded route needs a displaced annotation.
        ax = max(box.x,min(anchor[0],box.x+box.w))
        ay = max(box.y,min(anchor[1],box.y+box.h))
        if hypot(ax-anchor[0],ay-anchor[1]) > 35:
            g.append(path(f"M{fmt(ax)} {fmt(ay)} L{fmt(anchor[0])} {fmt(anchor[1])}", stroke="#98a9a8", **{"stroke-dasharray":"2 4"}))
        g.append(rect(box, **{"class":"note-box","rx":5}))
        if exact:
            g.append(f'<g transform="translate({fmt(x)} {fmt(y-6)})" fill="none" stroke="#436274" stroke-width="1.4">'+path("M1 1 V-2 A3 3 0 0 1 7 -2 V1 M0 1 H8 V7 H0Z")+'</g>')
        elif link.can_fold:
            g.append(f'<g transform="translate({fmt(x)} {fmt(y-3)})" fill="none" stroke="#18726a" stroke-width="1.6">'+path("M0 2 Q2 -4 4 0 T9 -1")+'</g>')
        else:
            g.append(svg_text(x,y,"↔","constraint"))
        g.append(svg_text(x+14,y,length,"constraint"))
        for i,(color,t) in enumerate(labels):
            cy=y+14*(i+1)
            g.append(f'<circle cx="{fmt(x+3)}" cy="{fmt(cy-3)}" r="2.5" fill="{color}"/>')
            g.append(svg_text(x+11,cy,t,"beam-note"))
        annotations.append("".join(g)+"</g>")

    for key, c in graph.nodes.items():
        p, computed = layout.places[key], trace["nodes"][key]
        diag = by_target["node",key]
        level = _level_class(diag)
        other_levels=" ".join(sorted({item["level"].lower() for item in diag} - {level}))
        g = [f'<g id="{prefix}-node-{esc(key)}" class="symbol-target node {level} {other_levels}" data-node="{esc(key)}" transform="translate({p.x} {p.y})">'
             f'<title>{esc(key)} · {esc(type(c).__name__)} · {esc(getattr(c,"note","") or getattr(c,"label",""))}</title>'
             '<circle class="node-ring" r="34" fill="none" stroke="none"/>']
        if level in ("error","warning"):
            g.append('<circle class="halo" r="30"/>')
        for pin in c.ports:
            px, py = p.port(pin)
            gx, gy = px-p.x, py-p.y
            g.append(path(f"M0 0 L{gx} {gy}", stroke="#5c7278", **{"stroke-width":1.6}))
            if isinstance(c,s.Four):
                g.append(svg_text(gx*.91+(3 if gx==0 else 0),gy*.91+(-4 if gy==0 else 2),pin,"port-name",
                                  'text-anchor="start"' if gx==0 else 'text-anchor="middle"'))
        g.append(f'<g class="sym" transform="rotate({90*p.rotation})">'+_symbol(c,computed)+'</g>')
        # Leave optical axes clear; the two-line caption occupies the upper-right quadrant.
        def cap_text(value, row, cls, char_limit):
            attrs = 'textLength="120" lengthAdjust="spacingAndGlyphs"' if len(value)>char_limit else ""
            return svg_text(16,row,value,cls,attrs)
        g.append(cap_text(key,-53,"caption-id",13))
        g.append(cap_text(_caption(c,computed),-37,"caption-type",20))
        for d in diag:
            if d["code"] == "unterminated_beam" and d.get("port") not in graph._by_port and d.get("port"):
                pin=d["port"].split(".")[1]
                px,py=p.port(pin,44)
                gx,gy=px-p.x,py-p.y
                g.append(path(f"M{gx*.72:g} {gy*.72:g} L{gx} {gy} m-3 -3 l6 6 m-6 0 l6 -6",
                              stroke="#c92938", **{"stroke-width":2,"fill":"none"}))
        symbols.append("".join(g)+"</g>")

    bounds = reserved+strokes or [Rect(0,0,200,100)]
    min_y = min(r.y for r in bounds)
    brackets = []
    for i, span in enumerate(graph.spans):
        left = layout.places[span.start.split(".")[0]].x
        right = layout.places[span.end.split(".")[0]].x
        low,high=sorted((left,right))
        if high-low < 180:
            low, high = low-90, high+90
        y=min_y-28-42*i
        tag=f"{span.start} ↔ {span.end} · Σ {span.exact_mm:g}±{span.tol_mm:g} mm"
        half=max((high-low)/2,len(tag)*3.8)
        bounds.append(Rect((low+high)/2-half,y-18,2*half,30))
        level=_level_class(by_target["span",str(i)])
        brackets.append(f'<g id="{prefix}-span-{i}" class="symbol-target span span-{level}" data-span="{i}"><title>{esc(span.note)}</title>'
                        +path(f"M{low} {y+10} V{y} H{high} V{y+10}",**{"class":"span-bracket"})
                        +svg_text((low+high)/2,y-5,tag,"span-note",'text-anchor="middle"')+'</g>')
    x0,y0=min(r.x for r in bounds)-20,min(r.y for r in bounds)-24
    x1,y1=max(r.x+r.w for r in bounds)+20,max(r.y+r.h for r in bounds)+24
    vb=" ".join(map(fmt,(x0,y0,x1-x0,y1-y0)))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{prefix}-title" viewBox="{vb}" width="{fmt(x1-x0)}" height="{fmt(y1-y0)}" data-valid="{str(trace["valid"]).lower()}">'
            f'<title id="{prefix}-title">{esc(graph.name)}</title><desc>逻辑光路。箭头表示传播方向，虚线表示回程，红色标出错误。</desc>'
            f'<style>{SVG_STYLE}</style>'+rect(Rect(x0,y0,x1-x0,y1-y0),fill="#fcfbf7")
            +"".join(brackets+layers+annotations+symbols)+'</svg>')


def write_output(pathname, content):
    """Atomic, repeatable writes, including exports to a mounted share."""
    dest = Path(pathname)
    raw = content.encode("utf-8")
    if dest.is_file() and dest.read_bytes() == raw:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=".optical-graph-", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(raw)
            handle.close()
            os.replace(temporary, dest)
        finally:
            temporary.unlink(missing_ok=True)


def json_text(data):
    return json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)+"\n"


HTML_STYLE = """
:root{color-scheme:light;--ink:#223c44;--muted:#546c71;--border:#ccd6d3;--teal:#075f63;--paper:#fcfbf7}
*{box-sizing:border-box}body{margin:0;background:#eeefea;color:var(--ink);font:15px/1.48 Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
main{max-width:1800px;margin:auto;padding:24px clamp(12px,3vw,48px) 30px}h1,h2,h3,p{margin:0}
header,.bar,.diagram-foot,.metrics,nav,.controls{display:flex;align-items:center;gap:10px}header,.bar{justify-content:space-between;flex-wrap:wrap}
header{margin-bottom:16px}.product{font:600 12px ui-monospace,monospace;color:var(--teal);letter-spacing:.04em}h1{font-size:clamp(23px,3vw,34px);font-weight:680;letter-spacing:-.035em}
.metrics{font:13px ui-monospace,monospace;color:var(--muted)}.metrics b{color:var(--ink)}
nav{gap:5px;overflow:auto;border-bottom:1px solid var(--border);padding:0 0 10px;margin-bottom:15px}
button{font:inherit;color:inherit;cursor:pointer}.tab,.controls button{border:1px solid var(--border);background:#fafbf8;border-radius:5px;white-space:nowrap}
.tab{padding:8px 12px;font-size:13px}.tab[aria-selected=true]{background:var(--teal);border-color:var(--teal);color:white}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#338065;margin-right:.5rem}.dot.bad{background:#ca3f46}
.panel[hidden]{display:none}.panel{background:var(--paper);border:1px solid var(--border);border-radius:10px;overflow:hidden}
.bar{padding:16px 20px;border-bottom:1px solid var(--border)}.bar h2{font-size:clamp(16px,2vw,23px);font-weight:650;overflow-wrap:anywhere}.bar p,.meta{color:var(--muted);font-size:13px}
.controls{gap:5px}.controls button{padding:5px 10px;font-size:13px;min-width:30px}.controls output{font:12px ui-monospace,monospace;min-width:38px;text-align:center}
.grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(240px,310px)}
.stage{height:clamp(380px,60vh,790px);overflow:auto;background:var(--paper);position:relative;scrollbar-color:#9caeaa #eeefeb}
.svghost{min-width:100%;min-height:100%;width:max-content;display:grid;place-items:center;padding:12px}
.svghost svg{display:block;max-width:none;flex-shrink:0}.side{padding:16px 18px;border-left:1px solid var(--border);background:#f6f7f1;overflow:auto;max-height:clamp(380px,60vh,790px)}
h3{font-size:15px;margin-bottom:8px}.side section+section{border-top:1px solid var(--border);padding-top:14px;margin-top:14px}
.diag,.terminal{display:block;width:100%;text-align:left;background:#fffefa;border:1px solid var(--border);border-radius:5px;padding:8px 9px;margin-top:6px;font-size:12px;overflow-wrap:anywhere}
.diag{border-left:3px solid #4b8480}.diag.error{border-left-color:#c92d3c;background:#fff4f1}.diag.warning{border-left-color:#bb7b17;background:#fff9ec}
.diag b,.terminal b{font:650 12px ui-monospace,monospace}.diag small,.terminal small{display:block;color:#52686f;margin-top:3px;font-size:11.5px}.flag{font-weight:650;margin-right:5px}
.diagram-foot{border-top:1px solid var(--border);padding:10px 20px;flex-wrap:wrap;color:var(--muted);font-size:12px;gap:6px 18px}.line-key{display:inline-block;width:21px;border-top:2px solid var(--teal);vertical-align:middle;margin-right:5px}.line-key.back{border-top-style:dashed}
button:focus-visible{outline:3px solid #288d94;outline-offset:2px}button:hover{filter:brightness(.96)}
@media(max-width:780px){main{padding:12px 8px}.grid{grid-template-columns:1fr}.stage{height:50vh;min-height:280px}.side{border:0;border-top:1px solid var(--border);max-height:38vh}.bar{padding:12px}}
@media print{body{background:white}main{padding:0}nav,.controls{display:none}.stage,.side{height:auto;max-height:none;overflow:visible}.svghost{width:100%}.svghost svg{max-width:100%;height:auto!important}.panel{break-inside:avoid}}
"""

HTML_SCRIPT = """
(() => {
  const tabs = [...document.querySelectorAll('[role=tab]')];
  const panels = [...document.querySelectorAll('.panel')];
  function resize(panel, scale) {
    const stage = panel.querySelector('.stage'), svg = stage.querySelector('svg');
    const b = svg.viewBox.baseVal;
    const fit = Math.min((stage.clientWidth-26)/b.width,(stage.clientHeight-26)/b.height,1.4);
    const z = scale === 'fit' ? fit : Math.max(.12,Math.min(4,Number(scale)));
    svg.style.width = (b.width*z)+'px'; svg.style.height = (b.height*z)+'px';
    panel.dataset.scale = z; panel.dataset.fit = String(scale === 'fit');
    panel.querySelector('output').textContent = Math.round(z*100)+'%';
  }
  function activate(i) {
    tabs.forEach((t,j) => {t.setAttribute('aria-selected',String(i===j));t.tabIndex=i===j?0:-1;panels[j].hidden=i!==j;});
    const p = panels[i]; resize(p, p.dataset.fit === 'false' ? p.dataset.scale : 'fit');
  }
  tabs.forEach((tab,i) => {
    tab.addEventListener('click',()=>activate(i));
    tab.addEventListener('keydown',ev=>{
      const n=tabs.length, j={ArrowRight:(i+1)%n,ArrowLeft:(i+n-1)%n,Home:0,End:n-1}[ev.key];
      if(j!==undefined){ev.preventDefault();activate(j);tabs[j].focus();}
    });
  });
  panels.forEach(p=>{
    const stage=p.querySelector('.stage');
    p.querySelectorAll('[data-zoom]').forEach(b=>b.addEventListener('click',()=>{
      const m=b.dataset.zoom; resize(p,m==='fit'?m:m==='actual'?1:Number(p.dataset.scale)*(m==='in'?1.35:1/1.35));
    }));
    p.querySelectorAll('[data-focus]').forEach(button=>button.addEventListener('click',()=>{
      const target=document.getElementById(button.dataset.focus);
      if(!target)return;
      p.querySelectorAll('.selected').forEach(x=>x.classList.remove('selected'));
      target.classList.add('selected'); resize(p,Math.max(.88,Number(p.dataset.scale)));
      const a=target.getBoundingClientRect(), b=stage.getBoundingClientRect();
      stage.scrollTo({left:stage.scrollLeft+a.left+(a.width-b.width)/2-b.left,
                      top:stage.scrollTop+a.top+(a.height-b.height)/2-b.top,behavior:'smooth'});
    }));
  });
  activate(0);
  window.addEventListener('resize',()=>{const p=panels.find(x=>!x.hidden);if(p.dataset.fit==='true')resize(p,'fit');});
})();
"""


def _tab_name(name):
    chunks=name.replace("_","-").split("-")
    if chunks[0][:1].lower()=="q" and chunks[0][1:].isdigit():
        suffix = " · "+chunks[1] if len(chunks)>1 and chunks[1] in ("buggy","fixed") else ""
        return chunks[0].upper()+suffix
    return name


def _panel(key, graph, data, svg, i):
    prefix = f"og{i}"
    trace = data["trace"]
    counts = f'{len(graph.nodes)} 个元件 · {len(graph.links)} 条物理通道 · {len(graph.spans)} 个总距约束'
    diagnostics = []
    for d in trace["diagnostics"]:
        level=d["level"].lower()
        target=f'{prefix}-{d["target_kind"]}-{d["target"]}'
        diagnostics.append(f'<button class="diag {level}" data-focus="{esc(target)}"><span class="flag">{esc(d["level"])}</span>'
                           f'<b>{esc(d["code"])}</b><small>{esc(d["target"])} · {esc(d["message"])}</small></button>')
    if not diagnostics:
        diagnostics.append('<p class="meta">未发现异常。</p>')
    terminals=[]
    for node,r in trace["terminals"].items():
        detail = f'{r["beam_count"]} 束'
        if "pol" in r:
            detail += " · "+r["pol"]
        if "freq_shift_mhz" in r:
            detail += f' · {r["freq_shift_mhz"]:+g} MHz'
        if "beat_freq_mhz" in r:
            detail += f' · 拍频 {r["beat_freq_mhz"]:g} MHz / {r["beat_phase_deg"]:.1f}°'
        if "face_diameter_mm" in r:
            detail += f' · 模式 Ø{r["diameter_mm"]:.3f} / 端面 Ø{r["face_diameter_mm"]:.3f} mm'
        if isinstance(graph.nodes[node],s.TargetPlane) and "defocus_mm" in r:
            detail += f' · 离焦 {r["defocus_mm"]:+.3f} mm'
        terminals.append(f'<button class="terminal" data-focus="{prefix}-node-{esc(node)}"><b>{esc(node)}</b> · '
                         f'{r["power_mw"]:.4g} mW<small>{esc(detail)}</small></button>')
    waves=sorted({beam["start"]["wavelength_nm"] for beam in trace["beams"]})
    legend="".join(f'<span><i class="dot" style="background:{wave_color(nm)}"></i>{nm:g} nm</span>' for nm in waves)
    hidden = "" if i==0 else " hidden"
    return (f'<article id="panel-{i}" class="panel" role="tabpanel" aria-labelledby="tab-{i}"{hidden}>'
            f'<div class="bar"><div><h2>{esc(graph.name)}</h2><p>{counts}</p></div><div class="controls">'
            '<button data-zoom="fit">适应全图</button><button data-zoom="out" aria-label="缩小">−</button>'
            '<output aria-live="polite"></output><button data-zoom="in" aria-label="放大">＋</button><button data-zoom="actual">100%</button></div></div>'
            f'<div class="grid"><div class="stage" tabindex="0" aria-label="可滚动的光路图"><div class="svghost">{svg}</div></div>'
            f'<aside class="side"><section><h3>光路诊断</h3>{"".join(diagnostics)}</section><section><h3>终端读数</h3>'
            f'{"".join(terminals)}</section></aside></div><div class="diagram-foot">{legend}<span><i class="line-key"></i>去程</span>'
            '<span><i class="line-key back"></i>回程 / 对射</span><span>距离单位 mm · 示意图未按距离缩放</span></div></article>')


def render_gallery(entries):
    """Entries contain (fixture name, graph, traced interchange object, standalone SVG)."""
    tabs, panels = [], []
    for i,(key, graph, data, svg) in enumerate(entries):
        good = data["trace"]["valid"]
        tabs.append(f'<button role="tab" class="tab" id="tab-{i}" aria-controls="panel-{i}" '
                    f'aria-selected="{str(i==0).lower()}" title="{esc(key)}">'
                    f'<i class="dot{"" if good else " bad"}"></i>{esc(_tab_name(graph.name))}</button>')
        panels.append(_panel(key,graph,data,svg,i))
    valid = sum(data["trace"]["valid"] for _,_,data,_ in entries)
    return ('<!doctype html><html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>HKSOP · 光路原理图</title><style>{HTML_STYLE}</style></head><body><main><header><div>'
            '<div class="product">HKSOP / OpticalGraph v1.0</div><h1>光路原理图</h1></div>'
            f'<p class="metrics"><b>{len(entries)} 组</b> · {valid} 有效 · {len(entries)-valid} 含错误</p></header>'
            f'<nav role="tablist" aria-label="光路选择">{"".join(tabs)}</nav>{"".join(panels)}'
            f'</main><script>{HTML_SCRIPT}</script></body></html>\n')
