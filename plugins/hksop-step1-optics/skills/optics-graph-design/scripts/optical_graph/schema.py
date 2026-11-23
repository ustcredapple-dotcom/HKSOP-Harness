"""Layer-one optical components and the hksop-optical-graph-v1 interchange format."""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field, fields, replace

FORMAT = "hksop-optical-graph-v1"
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")
POLARIZATIONS = ("P", "S", "linear", "LHC", "RHC", "elliptical", "unpolarized")
TRANSMIT = {"p1": "p3", "p3": "p1", "p2": "p4", "p4": "p2"}
REFLECT = {"p1": "p2", "p2": "p1", "p3": "p4", "p4": "p3"}


class GraphError(ValueError):
    def __init__(self, message, code="invalid_graph", target=None):
        self.code, self.target = code, target
        super().__init__(message)


def number(value, name, *, minimum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise GraphError(f"{name} must be finite")
    if (positive and value <= 0) or (minimum is not None and value < minimum):
        raise GraphError(f"{name} outside allowed range: {value}")
    return value


class Component:
    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None or f.name in ("pass_wavelengths_nm", "reflect_wavelengths_nm"):
                continue
            if f.name.endswith(("_mm", "_inch", "_nm", "_mhz", "_deg")) or f.name in ("power_mw", "m2", "refractive_index"):
                number(value, f.name)
                if f.name in ("m2", "refractive_index", "wavelength_nm", "rf_mhz", "bandwidth_mhz",
                              "diameter_mm", "design_diameter_mm", "clear_aperture_mm", "aperture_inch",
                              "active_aperture_mm") and value <= 0:
                    raise GraphError(f"{f.name} must be positive")
            if f.name in ("split_reflect_ratio", "reflect_ratio"):
                if not 0 <= number(value, f.name) <= 1:
                    raise GraphError(f"{f.name} must be in [0, 1]")
            if f.name in ("monitor_pd", "double_pass_flip", "zero_order_blocked", "allow_uncompensated_pm") and not isinstance(value, bool):
                raise GraphError(f"{f.name} must be a boolean")
        for key, choices in self.choices.items():
            value = getattr(self, key)
            if value not in choices:
                raise GraphError(f"{key} must be one of {choices}")
        if hasattr(self, "power_mw"):
            number(self.power_mw, "power_mw", minimum=0)
            if self.pol == "linear" and getattr(self, "pol_angle_deg", None) is None:
                raise GraphError("linear source requires pol_angle_deg")
        self._validate()

    choices = {}

    def _validate(self):
        pass


class Single(Component):
    category, ports = "single_port", ("front",)


class Two(Component):
    category, ports = "two_port", ("a", "b")


class Four(Component):
    category, ports = "four_port", ("p1", "p2", "p3", "p4")


class Spatial(Two):
    category = "spatial_fold"


@dataclass(frozen=True)
class LaserSource(Single):
    wavelength_nm: float
    diameter_mm: float
    pol: str = "P"
    pol_angle_deg: float = None
    height_mm: float = None
    power_mw: float = 10.0
    m2: float = 1.0
    choices = {"pol": POLARIZATIONS}


@dataclass(frozen=True)
class FiberSource(Single):
    wavelength_nm: float
    diameter_mm: float
    pol: str = "P"
    mode: str = "SM_PM"
    height_mm: float = None
    power_mw: float = 10.0
    pol_angle_deg: float = None
    connector: str = "FC/APC"
    choices = {"pol": POLARIZATIONS, "connector": ("FC/APC", "FC/PC")}


@dataclass(frozen=True)
class FiberCoupler(Single):
    mode: str = "SM_PM"
    design_diameter_mm: float = None
    required_pol: str = "P"
    steering_mirrors: int = 2
    connector: str = "FC/APC"
    allow_uncompensated_pm: bool = False
    choices = {"required_pol": (None, "P", "S", "LHC", "RHC"), "connector": ("FC/APC", "FC/PC")}

    def _validate(self):
        if type(self.steering_mirrors) is not int or self.steering_mirrors < 0:
            raise GraphError("steering_mirrors must be a nonnegative integer")


@dataclass(frozen=True)
class Photodiode(Single):
    label: str = ""
    bandwidth_mhz: float = None


@dataclass(frozen=True)
class Camera(Single):
    label: str = ""


@dataclass(frozen=True)
class TargetPlane(Single):
    label: str = ""
    target_waist_um: float = None

    def _validate(self):
        if self.target_waist_um is not None:
            number(self.target_waist_um, "target_waist_um", positive=True)


@dataclass(frozen=True)
class BeamDump(Single):
    monitor_pd: bool = False


@dataclass(frozen=True)
class RetroMirror(Single):
    aperture_inch: float = 1.0
    actuation: str = "manual"
    choices = {"actuation": ("manual", "piezo", "motorized")}


@dataclass(frozen=True)
class Lens(Two):
    f_mm: float
    aperture_inch: float = 1.0
    kind: str = "singlet"
    convex_toward: str = "auto"
    choices = {"kind": ("singlet", "achromat", "asphere"), "convex_toward": ("auto", "a", "b", "both")}

    def _validate(self):
        if self.f_mm == 0:
            raise GraphError("f_mm must be nonzero")


class _Waveplate(Two):
    def _set_parameters(self, values):
        # Keep the public keyword-only constructors on Python 3.9 as well.
        for parameter in fields(self):
            object.__setattr__(self, parameter.name, values[parameter.name])
        self.__post_init__()


@dataclass(frozen=True, init=False)
class HalfWaveplate(_Waveplate):
    aperture_inch: float = 1.0
    fast_axis_deg: float = None
    target_pol: str = None
    split_reflect_ratio: float = None
    note: str = ""
    choices = {"target_pol": (None, "P", "S")}

    def __init__(self, aperture_inch=1.0, *, fast_axis_deg=None, target_pol=None, split_reflect_ratio=None, note=""):
        self._set_parameters(locals())

    def _validate(self):
        if sum(x is not None for x in (self.fast_axis_deg, self.target_pol, self.split_reflect_ratio)) != 1:
            raise GraphError("HalfWaveplate needs exactly one operating point")


@dataclass(frozen=True, init=False)
class QuarterWaveplate(_Waveplate):
    aperture_inch: float = 1.0
    fast_axis_deg: float = None
    target_pol: str = None
    double_pass_flip: bool = False
    note: str = ""
    choices = {"target_pol": (None, "LHC", "RHC", "linear")}

    def __init__(self, aperture_inch=1.0, *, fast_axis_deg=None, target_pol=None, double_pass_flip=False, note=""):
        self._set_parameters(locals())

    def _validate(self):
        if sum((self.fast_axis_deg is not None, self.target_pol is not None, self.double_pass_flip)) != 1:
            raise GraphError("QuarterWaveplate needs exactly one operating point")


@dataclass(frozen=True, init=False)
class DualWaveplate(_Waveplate):
    aperture_inch: float = 1.0
    order: str = "QWP_HWP"
    qwp_fast_axis_deg: float = None
    hwp_fast_axis_deg: float = None
    split_reflect_ratio: float = None
    target_pol: str = None
    note: str = ""
    choices = {"target_pol": (None, "P", "S"), "order": ("QWP_HWP", "HWP_QWP")}

    def __init__(self, aperture_inch=1.0, order="QWP_HWP", qwp_fast_axis_deg=None,
                 hwp_fast_axis_deg=None, split_reflect_ratio=None, target_pol=None, note="",
                 *, qwp_deg=None, hwp_deg=None):
        if qwp_deg is not None and qwp_fast_axis_deg is not None or hwp_deg is not None and hwp_fast_axis_deg is not None:
            raise GraphError("Duplicate waveplate axis designation")
        if target_pol is not None and split_reflect_ratio is not None:
            raise GraphError("Choose a target polarization or a PBS split ratio")
        qwp_fast_axis_deg = qwp_fast_axis_deg if qwp_deg is None else qwp_deg
        hwp_fast_axis_deg = hwp_fast_axis_deg if hwp_deg is None else hwp_deg
        self._set_parameters(locals())

    @property
    def qwp_deg(self):
        return self.qwp_fast_axis_deg

    @property
    def hwp_deg(self):
        return self.hwp_fast_axis_deg


@dataclass(frozen=True)
class Aperture(Two):
    diameter_mm: float


@dataclass(frozen=True)
class Window(Two):
    thickness_mm: float
    material: str = "UVFS"
    refractive_index: float = None
    clear_aperture_mm: float = 25.0

    def _validate(self):
        number(self.thickness_mm, "thickness_mm", minimum=0)


@dataclass(frozen=True)
class CustomTwoPort(Two):
    device_type: str
    length_mm: float
    clear_aperture_mm: float
    params: dict = None
    custom_reason: str = ""

    def _validate(self):
        number(self.length_mm, "length_mm", minimum=0)
        if self.params is not None:
            if not isinstance(self.params, dict):
                raise GraphError("CustomTwoPort params must be an object")
            if "refractive_index" in self.params:
                number(self.params["refractive_index"], "refractive_index", positive=True)


@dataclass(frozen=True)
class Isolator(Two):
    wavelength_nm: float
    clear_aperture_mm: float = 4.5
    output_pol: str = "P"
    choices = {"output_pol": ("P", "S")}


@dataclass(frozen=True)
class AOM(Two):
    rf_mhz: float
    order: int = +1
    active_aperture_mm: float = 1.5
    zero_order_blocked: bool = True

    def _validate(self):
        if type(self.order) is not int:
            raise GraphError("AOM order must be an integer")


@dataclass(frozen=True)
class PBS(Four):
    aperture_inch: float = 1.0


@dataclass(frozen=True)
class NPBS(Four):
    aperture_inch: float = 1.0
    reflect_ratio: float = 0.5


@dataclass(frozen=True)
class SamplerPlate(Four):
    aperture_inch: float = 1.0
    reflect_ratio: float = 0.02


@dataclass(frozen=True)
class Dichroic(Four):
    aperture_inch: float = 1.0
    pass_wavelengths_nm: list = field(default_factory=list)
    reflect_wavelengths_nm: list = field(default_factory=list)

    def _validate(self):
        for bands in (self.pass_wavelengths_nm, self.reflect_wavelengths_nm):
            if not isinstance(bands, (list, tuple)):
                raise GraphError("Dichroic bands must be a sequence")
            for wavelength in bands:
                number(wavelength, "wavelength_nm", positive=True)
        if set(self.pass_wavelengths_nm) & set(self.reflect_wavelengths_nm):
            raise GraphError("Dichroic transmission and reflection bands overlap")


@dataclass(frozen=True)
class HeightShift(Spatial):
    in_height_mm: float
    out_height_mm: float
    mode: str = "straight"
    aperture_inch: float = 1.0
    choices = {"mode": ("straight", "turn90")}


@dataclass(frozen=True)
class VerticalFold(Spatial):
    direction: str = "down"
    aperture_inch: float = 1.0
    choices = {"direction": ("up", "down")}


@dataclass(frozen=True)
class SpatialFold(Spatial):
    pitch_deg: float
    yaw_deg: float = 0.0
    aperture_inch: float = 1.0


SOURCES = (LaserSource, FiberSource)
TERMINALS = (FiberCoupler, Photodiode, Camera, TargetPlane, BeamDump)
COMPONENTS = {cls.__name__: cls for cls in (
    *SOURCES, *TERMINALS, RetroMirror, Lens, HalfWaveplate, QuarterWaveplate, DualWaveplate,
    Aperture, Window, CustomTwoPort, Isolator, AOM, PBS, NPBS, SamplerPlate, Dichroic,
    HeightShift, VerticalFold, SpatialFold,
)}


@dataclass(frozen=True)
class Link:
    id: str
    u: str
    v: str
    exact_mm: float
    tol_mm: float
    min_mm: float
    max_mm: float
    can_fold: bool
    note: str

    def other(self, port):
        return self.v if port == self.u else self.u


@dataclass(frozen=True)
class Span:
    start: str
    end: str
    exact_mm: float
    tol_mm: float
    note: str


class OpticalGraph:
    def __init__(self, name, default_plane_height_mm=62.5):
        if not isinstance(name, str) or not name.strip():
            raise GraphError("graph name must be nonempty")
        self.name = name
        self.default_plane_height_mm = number(default_plane_height_mm, "default_plane_height_mm")
        self.nodes, self.links, self.spans, self._by_port = {}, [], [], {}
        self._link_ids = set()

    def add(self, node_id, component):
        if not isinstance(node_id, str) or not IDENTIFIER.fullmatch(node_id) or node_id in self.nodes:
            raise GraphError(f"invalid or duplicate node {node_id!r}", "invalid_port_or_duplicate_link")
        if type(component) not in COMPONENTS.values():
            raise GraphError(f"unsupported component at {node_id!r}")
        self.nodes[node_id] = component

    def _port(self, port):
        if isinstance(port, str) and port.count(".") == 1:
            node, pin = port.split(".")
            if node in self.nodes and pin in self.nodes[node].ports:
                return node, pin
        raise GraphError(f"unknown port {port!r}", "invalid_port_or_duplicate_link")

    def link(self, port_u, port_v, *, exact_mm=None, tol_mm=0.5, min_mm=25.0, max_mm=500.0,
             can_fold=False, note=""):
        self._port(port_u)
        self._port(port_v)
        if port_u == port_v or port_u in self._by_port or port_v in self._by_port:
            raise GraphError(f"duplicate link or occupied port: {port_u} / {port_v}", "invalid_port_or_duplicate_link")
        for key, value in (("min_mm", min_mm), ("max_mm", max_mm), ("tol_mm", tol_mm)):
            number(value, key, minimum=0)
        if exact_mm is not None:
            number(exact_mm, "exact_mm", minimum=0)
        if min_mm > max_mm or not isinstance(can_fold, bool) or not isinstance(note, str):
            raise GraphError("invalid link range, can_fold or note")
        index = len(self.links) + 1
        while f"L{index}" in self._link_ids:
            index += 1
        link = Link(f"L{index}", port_u, port_v, exact_mm, tol_mm, min_mm, max_mm, can_fold, note)
        self._link_ids.add(link.id)
        self.links.append(link)
        self._by_port[port_u] = self._by_port[port_v] = link

    def span(self, start_port, end_port, *, exact_mm, tol_mm=0.5, note=""):
        self._port(start_port)
        self._port(end_port)
        number(exact_mm, "exact_mm", minimum=0)
        number(tol_mm, "tol_mm", minimum=0)
        if start_port == end_port or not isinstance(note, str):
            raise GraphError("invalid span endpoints or note")
        self.spans.append(Span(start_port, end_port, exact_mm, tol_mm, note))

    def to_dict(self, include_trace=False):
        from .simulator import trace_graph
        trace = trace_graph(self) if include_trace else None
        nodes = []
        for key, comp in self.nodes.items():
            params = asdict(comp)
            if isinstance(comp, SOURCES) and comp.height_mm is None:
                params["height_mm"] = self.default_plane_height_mm
            item = dict(id=key, type=type(comp).__name__, category=comp.category, ports=list(comp.ports), params=params)
            if trace is not None:
                item["computed"] = trace["nodes"][key]
            nodes.append(item)
        links = [asdict(link) for link in self.links]
        spans = [asdict(span) for span in self.spans]
        result = dict(format=FORMAT, name=self.name, default_plane_height_mm=self.default_plane_height_mm,
                      nodes=nodes, links=links, spans=spans)
        if trace is not None:
            for link in links:
                link.update(trace["links"][link["id"]])
            for span, computed in zip(spans, trace["spans"]):
                span.update(computed)
            result["trace"] = trace
        return result

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise GraphError(f"expected format {FORMAT}")
        for key in ("nodes", "links", "spans"):
            rows = data.get(key, [] if key == "spans" else None)
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise GraphError(f"{key} must be a list of objects")
        graph = cls(data["name"], data.get("default_plane_height_mm", 62.5))
        for row in data["nodes"]:
            if {"x", "y", "xMm", "yMm", "rotationDeg", "holePitch"} & row.keys():
                raise GraphError("mechanical placement does not belong to a layer-one node")
            kind = COMPONENTS.get(row["type"])
            if kind is None or list(row.get("ports", kind.ports)) != list(kind.ports) or row.get("category", kind.category) != kind.category:
                raise GraphError(f"unknown component or inconsistent ports/category: {row['type']}", "invalid_port_or_duplicate_link")
            graph.add(row["id"], kind(**row["params"]))
        used_ids = set()
        for row in data["links"]:
            graph.link(row["u"], row["v"], **{k: row[k] for k in
                       ("exact_mm", "tol_mm", "min_mm", "max_mm", "can_fold", "note") if k in row})
            link = graph.links[-1]
            key = row.get("id", link.id)
            if not isinstance(key, str) or not IDENTIFIER.fullmatch(key) or key in used_ids:
                raise GraphError(f"invalid link ID {key!r}", "invalid_port_or_duplicate_link")
            used_ids.add(key)
            if key != link.id:
                graph._link_ids.remove(link.id)
                graph._link_ids.add(key)
                graph.links[-1] = graph._by_port[link.u] = graph._by_port[link.v] = replace(link, id=key)
        for span in data.get("spans", []):
            graph.span(span["start"], span["end"], **{k: span[k] for k in ("exact_mm", "tol_mm", "note") if k in span})
        return graph
