"""Paraxial Gaussian / Jones tracer. Lengths are mm, fields are sqrt(mW)."""
from __future__ import annotations

import cmath
import math
from collections import deque
from dataclasses import dataclass, replace
from itertools import combinations

from . import schema as s

EPS = 1e-12
UVFS = ((399, 1.470), (532, 1.461), (780, 1.454), (1064, 1.450))
# The worked AOM example explicitly grades a small active-aperture overfill as a warning.
AOM_WARNING_RATIO = 0.90
FIBER_MODE_RELATIVE_TOLERANCE = 0.05


def _index(comp, wavelength):
    if isinstance(comp, s.CustomTwoPort):
        return (comp.params or {}).get("refractive_index", 1.0)
    if comp.refractive_index is not None:
        return comp.refractive_index
    if comp.material.upper() == "UVFS":
        for (a, na), (b, nb) in zip(UVFS, UVFS[1:]):
            if a <= wavelength <= b:
                return na + (nb - na) * (wavelength - a) / (b - a)
    return 1.458


def _thickness(comp):
    return getattr(comp, "thickness_mm", getattr(comp, "length_mm", 0.0))


def _span_paths(graph, span):
    """Alternate external links and internal optical port pairings, starting at a face."""
    pending = [(span.start, (), 0.0)]
    found = []
    while pending and len(found) < 2:
        out, path, thickness = pending.pop()
        link = graph._by_port.get(out)
        if link is None or link.id in path:
            continue
        new_path = path + (link.id,)
        incoming = link.other(out)
        if incoming == span.end:
            found.append((new_path, thickness))
            continue
        node, pin = incoming.split(".")
        comp = graph.nodes[node]
        if isinstance(comp, s.Four):
            exits = (s.TRANSMIT[pin], s.REFLECT[pin])
        elif isinstance(comp, s.Two):
            exits = ("b" if pin == "a" else "a",)
        else:
            exits = ()
        pending.extend((f"{node}.{p}", new_path, thickness + _thickness(comp)) for p in exits)
    return found


def _distances(graph, diagnose):
    links = {link.id: link for link in graph.links}
    air = {k: v.exact_mm if v.exact_mm is not None else (v.min_mm + v.max_mm) / 2 for k, v in links.items()}
    spans, equations = [], []
    for i, span in enumerate(graph.spans):
        paths = _span_paths(graph, span)
        if len(paths) != 1:
            diagnose("ERROR", "span_path_error", "span", str(i), "Span needs one unambiguous optical path.")
            spans.append(dict(link_ids=[], internal_mm=0, resolved_mm=None))
            continue
        path, internal = paths[0]
        free = [k for k in path if links[k].exact_mm is None]
        locked = sum(air[k] for k in path if links[k].exact_mm is not None)
        target = span.exact_mm - internal - locked
        spans.append(dict(link_ids=list(path), internal_mm=internal))
        if free:
            low = sum(links[k].min_mm for k in free)
            high = sum(links[k].max_mm for k in free)
            equations.append((free, max(low, min(high, target))))

    # Project midpoints onto the simultaneous span equalities and link bounds
    # (Dykstra). This also handles several free legs and intersecting spans.
    corrections = [0.0] * len(equations)
    bounded = {k: 0.0 for free, _ in equations for k in free}
    for _ in range(1500 if equations else 0):
        previous = {k: air[k] for k in bounded}
        for i, (free, target) in enumerate(equations):
            delta = (sum(air[k] + corrections[i] for k in free) - target) / len(free)
            for k in free:
                air[k] += corrections[i] - delta
            corrections[i] = delta
        for k, correction in bounded.items():
            value = air[k] + correction
            air[k] = max(links[k].min_mm, min(links[k].max_mm, value))
            bounded[k] = value - air[k]
        error = max((abs(sum(air[k] for k in free) - target) for free, target in equations), default=0)
        if error < 1e-9 and max(abs(air[k] - previous[k]) for k in bounded) < 1e-9:
            break
    for i, (span, result) in enumerate(zip(graph.spans, spans)):
        if result["link_ids"]:
            value = sum(air[k] for k in result["link_ids"]) + result["internal_mm"]
            result["resolved_mm"] = value
            if abs(value - span.exact_mm) > span.tol_mm + 1e-8:
                diagnose("ERROR", "span_distance_error", "span", str(i),
                         f"Reachable span is {value:g} mm, requested {span.exact_mm:g} ± {span.tol_mm:g} mm.")
    return air, spans


def _field(pol, angle=None):
    if pol == "P":
        return 1+0j, 0j
    if pol == "S":
        return 0j, 1+0j
    if pol in ("LHC", "RHC"):
        return 1 / math.sqrt(2), (1j if pol == "LHC" else -1j) / math.sqrt(2)
    if pol == "elliptical":
        return math.cos(math.radians(28)), cmath.rect(math.sin(math.radians(28)), math.radians(53))
    a = math.radians(angle)
    return math.cos(a), math.sin(a)


def _power(e):
    return sum(abs(x)**2 for x in e)


def _stokes(e):
    x, y = e
    p = _power(e)
    c = x.conjugate() * y
    return ((abs(x)**2 - abs(y)**2) / p, 2*c.real/p, 2*c.imag/p)


def _azimuth(e):
    a, b, _ = _stokes(e)
    # Circular polarization has no azimuth. Use the numeric field's zero convention.
    if math.hypot(a, b) <= 1e-14:
        return 0.0
    return math.degrees(math.atan2(b, a)) / 2


def _pol(e):
    a, _, c = _stokes(e)
    if abs(c) < 1e-8:
        if abs(1 - abs(a)) < 1e-10:
            return "P" if a > 0 else "S"
        return "linear"
    if abs(1 - abs(c)) < 1e-9:
        return "LHC" if c > 0 else "RHC"
    return "elliptical"


def _plate(e, angle, delay):
    a = math.radians(angle)
    c, t = math.cos(a), math.sin(a)
    fast = c*e[0] + t*e[1]
    slow = (-t*e[0] + c*e[1]) * cmath.exp(-1j*delay)
    return c*fast - t*slow, t*fast + c*slow


def _angle_mod(degrees, period):
    value = degrees % period
    return 0.0 if min(value, period-value) < 1e-10 else value


def _waveplate(comp, pin, e, settings):
    alpha = _azimuth(e)
    if isinstance(comp, s.DualWaveplate):
        if "resolved_qwp_deg" not in settings:
            target = (math.degrees(math.asin(math.sqrt(comp.split_reflect_ratio)))
                      if comp.split_reflect_ratio is not None else 90 if comp.target_pol == "S" else 0)
            if (pin == "a") == (comp.order == "QWP_HWP"):
                q = comp.qwp_deg if comp.qwp_deg is not None else alpha
                linear = _plate(e, q, math.pi/2)
                h = comp.hwp_deg if comp.hwp_deg is not None else (_azimuth(linear) + target) / 2
            else:
                # A HWP reverses ellipticity chi. With the final QWP on the
                # new ellipse axis q, the linear output angle is q - chi.
                chi = math.degrees(math.asin(max(-1., min(1., _stokes(e)[2]))))/2
                q = comp.qwp_deg if comp.qwp_deg is not None else target + chi
                h = comp.hwp_deg if comp.hwp_deg is not None else (q + alpha)/2
                if comp.qwp_deg is None and comp.hwp_deg is not None:
                    q = 2*h - alpha
            settings.update(resolved_qwp_deg=_angle_mod(q, 180), resolved_hwp_deg=_angle_mod(h, 180))
        plates = [(settings["resolved_qwp_deg"], math.pi/2), (settings["resolved_hwp_deg"], math.pi)]
        settings.update(qwp_fast_axis_deg=settings["resolved_qwp_deg"], hwp_fast_axis_deg=settings["resolved_hwp_deg"], order=comp.order)
        if comp.order == "HWP_QWP":
            plates.reverse()
        for angle, delay in (plates if pin == "a" else reversed(plates)):
            e = _plate(e, angle, delay)
        return e
    if "resolved_fast_axis_deg" not in settings:
        angle = comp.fast_axis_deg
        if angle is None and isinstance(comp, s.HalfWaveplate):
            if comp.split_reflect_ratio is not None:
                target = math.degrees(math.asin(math.sqrt(comp.split_reflect_ratio)))
            else:
                target = 0 if comp.target_pol == "P" else 90
            angle = (alpha + target) / 2
        elif angle is None:
            offset = {"linear": 0, "LHC": 45, "RHC": -45}.get(comp.target_pol, 45)
            angle = alpha + offset
        settings["resolved_fast_axis_deg"] = _angle_mod(angle, 180)
    return _plate(e, settings["resolved_fast_axis_deg"], math.pi if isinstance(comp, s.HalfWaveplate) else math.pi/2)


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])


def _unit(v):
    n = math.sqrt(_dot(v, v))
    return tuple(x/n for x in v)


def _mirror(v, n):
    factor = 2*_dot(v, n)
    return tuple(x - factor*y for x, y in zip(v, n))


def _rotate_z(v, angle):
    c, t = math.cos(angle), math.sin(angle)
    return (c*v[0] - t*v[1], t*v[0] + c*v[1], v[2])


@dataclass(frozen=True)
class Ray:
    source: str
    coherence: str
    wavelength: float
    m2: float
    q: complex
    e: tuple
    height: float
    shift: float = 0.0
    # A and C are the first column of the ray-transfer matrix (parallel test ray).
    a: float = 1.0
    c: float = 0.0
    k: tuple = (1.0, 0.0, 0.0)
    p_axis: tuple = (0.0, 1.0, 0.0)
    s_axis: tuple = (0.0, 0.0, 1.0)

    def through(self, distance, index=1.0):
        phase = math.tau * math.remainder(distance*index / (self.wavelength*1e-6), 1.0)
        q_out = self.q + distance/index
        gouy = cmath.phase(q_out/self.q)
        factor = cmath.exp(1j*(phase + gouy))
        return replace(self, q=q_out, a=self.a + distance/index*self.c,
                       height=self.height + distance*self.k[2], e=tuple(x*factor for x in self.e))

    def turn(self, angle):
        return replace(self, k=_rotate_z(self.k, angle), p_axis=_rotate_z(self.p_axis, angle),
                       s_axis=_rotate_z(self.s_axis, angle))

    def spot(self):
        return 2*math.sqrt(-self.m2*self.wavelength*1e-6 / (math.pi*(1/self.q).imag))

    def collimated_until(self, end):
        # d(log w)/dz = Re(1/q). Its extrema occur at one Rayleigh length either side of the waist.
        lo, hi = sorted((self.q.real, end.q.real))
        zr = self.q.imag
        samples = [lo, hi] + [x for x in (-zr, zr) if lo < x < hi]
        return max(abs(x)/(x*x + zr*zr) for x in samples) < 1/5000

    def readout(self):
        curvature = (1/self.q).real
        waist = 2*math.sqrt(self.m2*self.wavelength*1e-6 * self.q.imag / math.pi)
        return dict(source=self.source, coherence=self.coherence, wavelength_nm=self.wavelength,
                    m2=self.m2, power_mw=_power(self.e), pol=_pol(self.e), stokes=list(_stokes(self.e)),
                    pol_angle_deg=_azimuth(self.e), freq_shift_mhz=self.shift,
                    jones=[[x.real, x.imag] for x in self.e], q_mm=[self.q.real, self.q.imag],
                    diameter_mm=self.spot(), waist_diameter_mm=waist, defocus_mm=self.q.real,
                    radius_mm=1/curvature if curvature else None, collimated=abs(curvature) < 1/5000,
                    afocal=abs(self.c) < EPS, height_mm=self.height,
                    k=list(self.k), p_axis=list(self.p_axis), s_axis=list(self.s_axis))


def _spatial(comp, pin, ray, settings):
    n = settings.get("mirror_normal")
    if n is None:
        if isinstance(comp, s.VerticalFold):
            goal = (0., 0., -1. if comp.direction == "down" else 1.)
            horizontal = (1., 0., 0.)
        else:
            pitch, yaw = math.radians(comp.pitch_deg), math.radians(comp.yaw_deg)
            forward = math.atan2(ray.k[1], ray.k[0]) if pin == "a" else 0.
            horizontal = (math.cos(forward), math.sin(forward), 0.)
            goal = (math.cos(pitch)*math.cos(forward+yaw), math.cos(pitch)*math.sin(forward+yaw), math.sin(pitch))
        incoming, outgoing = (ray.k, goal) if pin == "a" else (tuple(-x for x in goal), tuple(-x for x in horizontal))
        diff = tuple(a-b for a, b in zip(incoming, outgoing))
        if _dot(diff, diff) < EPS:
            return ray
        n = _unit(diff)
        settings["mirror_normal"] = list(n)
    # Householder reflection acts on both E and k. Choose a right-handed
    # transverse frame after reflection, then project the reflected E into it.
    k, p = _mirror(ray.k, n), _mirror(ray.p_axis, n)
    sy = _unit(_cross(k, p))
    old_s = _mirror(ray.s_axis, n)
    e = (ray.e[0], ray.e[1]*_dot(old_s, sy))
    return replace(ray, k=k, p_axis=p, s_axis=sy, e=e)


def _clear_aperture(comp):
    if isinstance(comp, s.AOM):
        return comp.active_aperture_mm
    if isinstance(comp, s.Aperture):
        return comp.diameter_mm
    if hasattr(comp, "clear_aperture_mm"):
        return comp.clear_aperture_mm
    if hasattr(comp, "aperture_inch"):
        return comp.aperture_inch*25.4
    return None


def _source_headings(graph):
    """Infer horizontal source axes backwards through combiners without drawing coordinates."""
    axes = {}
    base = {"front": 0., "a": math.pi, "b": 0., "p1": math.pi, "p2": math.pi/2,
            "p3": 0., "p4": -math.pi/2}

    def side(comp, pin):
        if pin == "b":
            if isinstance(comp, s.HeightShift) and comp.mode == "turn90":
                return math.pi/2
            if isinstance(comp, s.SpatialFold):
                return math.radians(comp.yaw_deg)
        return base[pin]

    sources = sorted((k for k, c in graph.nodes.items() if isinstance(c, s.SOURCES)),
                     key=lambda k: -graph.nodes[k].power_mw)
    for root in sources:
        if root in axes:
            continue
        axes[root] = 0.
        todo = deque([root])
        while todo:
            key = todo.popleft()
            comp = graph.nodes[key]
            for pin in comp.ports:
                port = f"{key}.{pin}"
                link = graph._by_port.get(port)
                if link is None:
                    continue
                other, port_in = link.other(port).split(".")
                if other not in axes:
                    axes[other] = axes[key]+side(comp,pin)+math.pi-side(graph.nodes[other],port_in)
                    todo.append(other)
    return axes


class _Tracer:
    def __init__(self, graph):
        self.graph = graph
        self.diagnostics, self.seen_diagnostics = [], set()
        self.air, self.spans = _distances(graph, self.diagnose)
        self.nodes = {k: dict(board_cutout_required=(isinstance(c, s.VerticalFold) and c.direction == "down") or
                              (isinstance(c, s.SpatialFold) and c.pitch_deg < 0)) for k, c in graph.nodes.items()}
        self.arrivals = {k: [] for k, comp in graph.nodes.items() if isinstance(comp, s.TERMINALS)}
        self.directions = {link.id: set() for link in graph.links}
        self.queue, self.beams, self.dark = deque(), [], set()

    def diagnose(self, level, code, kind, target, message, **details):
        key = (level, code, kind, target, details.get("port"))
        if key not in self.seen_diagnostics:
            self.seen_diagnostics.add(key)
            self.diagnostics.append(dict(level=level, code=code, target_kind=kind, target=target,
                                         message=message, **details))

    def emit(self, port, ray, history):
        link = self.graph._by_port.get(port)
        if _power(ray.e) <= EPS * EPS * max(getattr(self.graph.nodes[ray.source], "power_mw", 1), 1e-300):
            if link is not None:
                self.dark.add(link.other(port))
            return
        if link is None:
            self.diagnose("ERROR", "unterminated_beam", "node", port.split(".")[0],
                          f"{port} emits {_power(ray.e):.4g} mW into an open port.", port=port, power_mw=_power(ray.e))
            return
        if port in history:
            self.diagnose("ERROR", "optical_cycle", "link", link.id, "Beam revisits a directed link; steady-state cavity model required.")
            return
        other = link.other(port)
        if link.can_fold:
            if _pol(ray.e) not in ("P", "S"):
                self.diagnose("ERROR", "polarization_fold_hazard", "link", link.id,
                              f"{port} carries {_pol(ray.e)} polarization on a foldable path.")
            if abs(ray.k[2]) < 1e-9 and abs(ray.height - self.graph.default_plane_height_mm) > 1e-8:
                self.diagnose("WARNING", "fold_at_nonstandard_height", "link", link.id,
                              f"Foldable horizontal path at {ray.height:g} mm.")
        arrived = ray.through(self.air[link.id])
        collimated = ray.collimated_until(arrived)
        if link.can_fold and abs(ray.c) > EPS and not collimated:
            self.diagnose("ERROR", "collimation_error", "link", link.id,
                          "A converging or diverging passage is marked foldable.")
        self.beams.append(dict(link_id=link.id, **{"from": port, "to": other}, segment_collimated=collimated,
                               start=ray.readout(), end=arrived.readout()))
        self.directions[link.id].add(port)
        self.queue.append((other, arrived, history | {port}))

    def aperture(self, node, comp, ray):
        aperture = _clear_aperture(comp)
        if aperture is None:
            return
        diameter = ray.spot()
        ratio = aperture/diameter
        settings = self.nodes[node]
        if ratio < settings.get("min_aperture_ratio", math.inf):
            settings.update(min_aperture_ratio=ratio, clear_aperture_mm=aperture, max_spot_diameter_mm=diameter)
        if ratio >= 1.5:
            return
        strict = "severe_clipping" if ratio < 1 else "tight_aperture"
        marginal_aom = isinstance(comp, s.AOM) and ratio >= AOM_WARNING_RATIO
        severe = ratio < 1 and not marginal_aom
        code = "severe_clipping" if severe else "tight_aperture"
        self.diagnose("ERROR" if severe else "WARNING", code, "node", node,
                      f"Aperture {aperture:g} mm / face spot {diameter:.3f} mm = {ratio:.3f}.",
                      aperture_ratio=ratio, strict_aperture_code=strict)

    def split(self, node, pin, comp, ray, history):
        if isinstance(comp, s.PBS):
            transmitted, reflected = (ray.e[0], 0j), (0j, 1j*ray.e[1])
        else:
            if isinstance(comp, s.Dichroic):
                if ray.wavelength in comp.pass_wavelengths_nm:
                    r = 0.
                elif ray.wavelength in comp.reflect_wavelengths_nm:
                    r = 1.
                else:
                    self.diagnose("ERROR", "unmapped_wavelength", "node", node, f"No dichroic band for {ray.wavelength:g} nm.")
                    return
            else:
                r = comp.reflect_ratio
            transmitted = tuple(math.sqrt(1-r)*x for x in ray.e)
            reflected = tuple(1j*math.sqrt(r)*x for x in ray.e)
        self.emit(f"{node}.{s.TRANSMIT[pin]}", replace(ray, e=transmitted), history)
        reflected_ray = ray.turn(math.pi/2 if pin in ("p1", "p3") else -math.pi/2)
        self.emit(f"{node}.{s.REFLECT[pin]}", replace(reflected_ray, e=reflected), history)

    def visit(self, port, ray, history):
        node, pin = port.split(".")
        comp, settings = self.graph.nodes[node], self.nodes[node]
        self.aperture(node, comp, ray)
        if isinstance(comp, s.TERMINALS):
            self.arrivals[node].append(ray)
            return
        if isinstance(comp, s.SOURCES):
            self.diagnose("ERROR", "unterminated_beam", "node", node, "Return beam strikes the source.", port=port)
            return
        if isinstance(comp, s.Four):
            self.split(node, pin, comp, ray, history)
            return
        if isinstance(comp, s.RetroMirror):
            # Unfold a plane mirror in q; in-plane Jones axes stay fixed on return.
            self.emit(port, replace(ray, k=tuple(-x for x in ray.k)), history)
            return
        out = "b" if pin == "a" else "a"
        before = ray
        if isinstance(comp, s.Lens):
            q = 1/(1/ray.q - 1/comp.f_mm)
            convex = comp.convex_toward
            if convex == "auto":
                convex = pin if abs((1/ray.q).real) <= abs((1/q).real) else out
            settings.setdefault("convex_toward", convex)
            ray = replace(ray, q=q, c=ray.c-ray.a/comp.f_mm)
            incoming = self.graph._by_port[port]
            outgoing = self.graph._by_port.get(f"{node}.{out}")
            prev = self.graph.nodes[incoming.other(port).split(".")[0]]
            if isinstance(prev, s.Lens) and incoming.exact_mm is not None and outgoing and outgoing.can_fold:
                nominal = prev.f_mm + comp.f_mm
                if abs(incoming.exact_mm - nominal) > incoming.tol_mm and abs(ray.c) > EPS:
                    self.diagnose("ERROR", "collimation_error", "link", incoming.id,
                                  f"Telescope separation {incoming.exact_mm:g} mm; afocal separation {nominal:g} mm.")
        elif isinstance(comp, (s.Window, s.CustomTwoPort)):
            index = _index(comp, ray.wavelength)
            settings.setdefault("refractive_index_by_nm", {})[f"{ray.wavelength:g}"] = index
            ray = ray.through(_thickness(comp), index)
            self.aperture(node, comp, ray)
        elif isinstance(comp, (s.HalfWaveplate, s.QuarterWaveplate, s.DualWaveplate)):
            ray = replace(ray, e=_waveplate(comp, pin, ray.e, settings))
        elif isinstance(comp, s.Isolator):
            if pin == "b":
                self.diagnose("ERROR", "isolator_reverse_blocked", "node", node, f"Reverse beam absorbed at {port}.", port=port)
                return
            phase = cmath.phase(max(ray.e, key=abs))
            amp = cmath.rect(math.sqrt(_power(ray.e)), phase)
            ray = replace(ray, e=tuple(amp*x for x in _field(comp.output_pol)))
        elif isinstance(comp, s.AOM):
            ray = replace(ray, shift=ray.shift+comp.order*comp.rf_mhz)
            if comp.order and not comp.zero_order_blocked:
                self.diagnose("WARNING", "unblocked_zero_order", "node", node,
                              "Zero order is unblocked; its efficiency and waste path are unspecified.")
        elif isinstance(comp, s.HeightShift):
            ray = replace(ray, height=comp.out_height_mm if pin == "a" else comp.in_height_mm)
            if comp.mode == "turn90":
                ray = replace(ray.turn(math.pi/2 if pin == "a" else -math.pi/2), e=(ray.e[1], ray.e[0]))
        elif isinstance(comp, (s.VerticalFold, s.SpatialFold)):
            ray = _spatial(comp, pin, ray, settings)
        settings.setdefault("input_pol", _pol(before.e))
        settings.setdefault("output_pol", _pol(ray.e))
        self.emit(f"{node}.{out}", ray, history)

    def terminal(self, node, rays):
        comp = self.graph.nodes[node]
        readings = [ray.readout() for ray in rays]
        total = sum(item["power_mw"] for item in readings)
        data = dict(beam_count=len(rays), power_mw=total, total_power_mw=total, beams=readings, beats=[])
        if not rays:
            if isinstance(comp, s.BeamDump) and f"{node}.front" in self.dark:
                self.diagnose("INFO", "defensive_dump", "node", node, "Beam dump protects a nominally dark port.")
            else:
                self.diagnose("ERROR", "terminal_no_light", "node", node, "No optical power reaches this terminal.")
            return data
        for key in ("wavelength_nm", "freq_shift_mhz", "pol"):
            if all(r[key] == readings[0][key] for r in readings):
                data[key] = readings[0][key]
        if len(readings) == 1:
            for key in ("diameter_mm", "defocus_mm", "collimated", "waist_diameter_mm", "radius_mm"):
                data[key] = readings[0][key]
        if isinstance(comp, s.FiberCoupler):
            for r in readings:
                # Golden SM-PM diameters describe the collimated mode (afocal waist);
                # preserve the local q result independently on every terminal and link.
                mode = r["waist_diameter_mm"] if r["afocal"] else r["diameter_mm"]
                collimated = r["afocal"] or r["collimated"]
                r.update(mode_diameter_mm=mode, mode_collimated=collimated)
                if len(readings) == 1:
                    data.update(diameter_mm=mode, collimated=collimated, face_diameter_mm=r["diameter_mm"],
                                face_collimated=r["collimated"], diameter_reference="afocal_mode_waist" if r["afocal"] else "face")
                if comp.required_pol and r["pol"] != comp.required_pol:
                    self.diagnose("ERROR", "pm_pol_mismatch", "node", node, f"Expected {comp.required_pol}, received {r['pol']}.")
                if comp.design_diameter_mm and (not collimated or abs(mode/comp.design_diameter_mm-1) > FIBER_MODE_RELATIVE_TOLERANCE):
                    self.diagnose("ERROR", "collimation_error", "node", node,
                                  f"Input mode {mode:.3f} mm; design {comp.design_diameter_mm:g} mm.")
        if isinstance(comp, s.Photodiode):
            for a, b in combinations(rays, 2):
                if a.wavelength != b.wavelength or a.coherence != b.coherence:
                    continue
                if a.shift < b.shift:
                    a, b = b, a
                # The detector sees both fields in one laboratory frame.
                ea = tuple(a.e[0]*p + a.e[1]*v for p, v in zip(a.p_axis, a.s_axis))
                eb = tuple(b.e[0]*p + b.e[1]*v for p, v in zip(b.p_axis, b.s_axis))
                overlap = sum(x*y.conjugate() for x, y in zip(ea, eb))
                if abs(overlap) > EPS*math.sqrt(_power(a.e)*_power(b.e)):
                    data["beats"].append(dict(beat_freq_mhz=a.shift-b.shift, beat_phase_deg=_angle_mod(math.degrees(cmath.phase(overlap)), 360),
                                              amplitude_mw=2*abs(overlap), coefficient_mw=[2*overlap.real, 2*overlap.imag]))
            if len(data["beats"]) == 1:
                data.update(data["beats"][0])
        return data

    def run(self):
        from .pm_policy import check_interfaces
        check_interfaces(self.graph, self.diagnose)
        headings = _source_headings(self.graph)
        for node, comp in self.graph.nodes.items():
            if not isinstance(comp, s.SOURCES) or comp.power_mw == 0:
                continue
            m2 = getattr(comp, "m2", 1.0)
            q = 1j*math.pi*(comp.diameter_mm/2)**2 / (m2*comp.wavelength_nm*1e-6)
            pols = ("P", "S") if comp.pol == "unpolarized" else (comp.pol,)
            for pol in pols:
                amp = math.sqrt(comp.power_mw/len(pols))
                e = tuple(amp*x for x in _field(pol, comp.pol_angle_deg))
                height = self.graph.default_plane_height_mm if comp.height_mm is None else comp.height_mm
                ray = Ray(node, f"{node}/{pol}", comp.wavelength_nm, m2, q, e, height).turn(headings[node])
                self.emit(f"{node}.front", ray, frozenset())
        while self.queue:
            self.visit(*self.queue.popleft())
        terminals = {k: self.terminal(k, rays) for k, rays in self.arrivals.items()}
        links = {k: dict(resolved_air_mm=v, bidirectional=len(self.directions[k]) == 2) for k, v in self.air.items()}
        return dict(valid=not any(d["level"] == "ERROR" for d in self.diagnostics), diagnostics=self.diagnostics,
                    terminals=terminals, beams=self.beams, nodes=self.nodes, links=links, spans=self.spans)


def trace_graph(graph):
    """Return a JSON-safe trace. Derived data are recomputed from graph inputs."""
    if isinstance(graph, dict):
        graph = s.OpticalGraph.from_dict(graph)
    return _Tracer(graph).run()


def validate_graph(graph):
    """Return the same diagnostic report, including malformed interchange input."""
    try:
        return trace_graph(graph)
    except (s.GraphError, KeyError, TypeError, ValueError) as exc:
        return dict(valid=False, diagnostics=[dict(level="ERROR", code=getattr(exc, "code", "invalid_graph"),
                    target_kind="graph", target=getattr(exc, "target", None), message=str(exc))],
                    terminals={}, beams=[], nodes={}, links={}, spans=[])
