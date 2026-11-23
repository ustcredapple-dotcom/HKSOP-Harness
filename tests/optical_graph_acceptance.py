#!/usr/bin/env python3
"""Check the supplied OpticalGraph fixtures, JSON contract, routing and CLI, using only stdlib."""
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import optical_graph as og
from optical_graph import schema
from optical_graph.renderer import json_text, render_svg, write_output
from optical_graph.schematic_layout import Rect, segment_box
from optical_graph_fixtures import ALL_FIXTURES

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("HKSOP_TEST_OUTPUT", HERE.parent / "results")) / "optical-graph"
EXPECTED = HERE/"optical-graph-expected.json"
SVG = "{http://www.w3.org/2000/svg}"
MISSING = object()


class Checks:
    def __init__(self):
        self.items = []

    def equal(self, label, actual, expected, tol=None):
        if tol is None:
            ok = actual == expected and (not isinstance(expected,bool) or type(actual) is bool)
        else:
            ok = (isinstance(actual,(int,float)) and not isinstance(actual,bool)
                  and math.isfinite(actual) and abs(actual-expected) <= tol+1e-10)
        row = dict(check=label,actual=actual if actual is not MISSING else "<missing>",expected=expected,passed=ok)
        if tol is not None:
            row["tolerance"] = tol
        self.items.append(row)

    def require(self, label, condition):
        self.equal(label,bool(condition),True)

    def report(self):
        return dict(passed=all(r["passed"] for r in self.items),check_count=len(self.items),checks=self.items)


def fixture_checks(check, graph, data, expected):
    trace=data["trace"]
    check.equal("valid",trace["valid"],expected["expectedValid"])
    codes={d["code"] for d in trace["diagnostics"]}
    for code in expected["expectedDiagnostics"]["mustIncludeCodes"]:
        check.require("diagnostic required: "+code,code in codes)
    for code in expected["expectedDiagnostics"]["mustExcludeCodes"]:
        check.require("diagnostic excluded: "+code,code not in codes)
    tolerances={"power_mw":"power_tol_mw","total_power_mw":"power_tol_mw","diameter_mm":"diameter_tol_mm",
                "beat_freq_mhz":"beat_tol_mhz","resolved_air_mm":"air_tol_mm","beat_phase_diff_deg":"phase_tol_deg"}
    for spec in expected.get("terminalChecks",[]):
        node=spec["node"]
        row=trace["terminals"][node]
        for key, wanted in spec.items():
            if key=="node" or key in tolerances.values():
                continue
            if key=="max_abs_defocus_mm":
                value=row.get("defocus_mm")
                check.require(f"{node}: |defocus| ≤ {wanted} mm",value is not None and abs(value)<=wanted)
            else:
                actual=row.get(key,MISSING)
                tol=spec.get(tolerances.get(key))
                check.equal(f"{node}.{key}",actual,wanted,tol)
    for node,spec in expected.get("nodeChecks",{}).items():
        for key,wanted in spec.items():
            check.equal(f"{node}.{key}",trace["nodes"][node].get(key,MISSING),wanted)
    for spec in expected.get("linkChecks",[]):
        u,v=spec["u"],spec["v"]
        matches=[r for r in data["links"] if {r["u"],r["v"]}=={u,v}]
        check.equal(f"{u} ↔ {v} count",len(matches),1)
        for key,wanted in spec.items():
            if key not in ("u","v") and key not in tolerances.values():
                check.equal(f"{u} ↔ {v}.{key}", matches[0].get(key,MISSING) if matches else MISSING,
                            wanted,spec.get(tolerances.get(key)))
    for spec in expected.get("differentialChecks",[]):
        a,b=spec["node_a"],spec["node_b"]
        diff=abs(math.remainder(trace["terminals"][a]["beat_phase_deg"]-trace["terminals"][b]["beat_phase_deg"],360))
        check.equal(f"{a}/{b} phase difference",diff,spec["beat_phase_diff_deg"],spec["phase_tol_deg"])
    # Additional requirements in the prose spec (the machine fixture does not repeat these).
    if graph.name=="q7-buggy-double-pass":
        check.require("§9 clipping in faulty telescope","severe_clipping" in codes)
    if graph.name=="q7-fixed-double-pass":
        check.equal("§9 repaired circuit warnings/errors",[d["code"] for d in trace["diagnostics"] if d["level"]!="INFO" and d["code"] not in {"pm_output_compensation","pbs_reflection_per","pbs_interstage_compensation"}],[])
    for row,spec in zip(data["spans"],graph.spans):
        check.equal(f"{spec.start} ↔ {spec.end} total geometric distance",row["resolved_mm"],spec.exact_mm,spec.tol_mm)


def svg_checks(check,svg_text,graph,data):
    root=ET.fromstring(svg_text)
    groups=root.findall(".//"+SVG+"g")
    nodes={g.get("data-node"):g for g in groups if "data-node" in g.attrib}
    links={g.get("data-link"):g for g in groups if "data-link" in g.attrib}
    check.equal("SVG node IDs",sorted(nodes),sorted(graph.nodes))
    check.equal("SVG channel IDs",sorted(links),sorted(x.id for x in graph.links))
    check.equal("SVG span brackets",sum("data-span" in g.attrib for g in groups),len(graph.spans))
    obstacles=[]
    for node,g in nodes.items():
        x,y=map(float,g.get("transform").removeprefix("translate(").removesuffix(")").split())
        obstacles.extend([(node,Rect(x-31,y-31,62,62)),(node+" caption",Rect(x+14,y-68,126,34))])
    for g in groups:
        if g.get("class")=="link-badge":
            r=g.find(SVG+"rect")
            obstacles.append((g.get("data-for")+" annotation",Rect(*(float(r.get(k)) for k in ("x","y","width","height")))))
    collisions=[(i,j) for n,(i,a) in enumerate(obstacles) for j,b in obstacles[n+1:] if a.intersects(b)]
    check.equal("SVG overlap of symbols, captions or distance badges",collisions,[])
    crossings=[]
    for link in graph.links:
        g=links[link.id]
        path=g.find(f'{SVG}polyline[@class="pick-line"]')
        coords=[tuple(map(float,p.split(","))) for p in path.get("points").split()]
        for a,b in zip(coords,coords[1:]):
            if (a[0]!=b[0]) and (a[1]!=b[1]):
                crossings.append((link.id,"non-Manhattan"))
            area=segment_box(a,b,.1)
            crossings.extend((link.id,key) for key,box in obstacles if box.intersects(area))
        rails=[r for r in g.findall(SVG+"g") if r.get("class")=="beam-track"]
        if data["trace"]["links"][link.id]["bidirectional"]:
            check.equal(f"SVG {link.id}: both arrow directions",sorted({r.get("data-from") for r in rails}),sorted((link.u,link.v)))
            check.require(f"SVG {link.id}: dashed return and solid outward rail",
                          {r.find(SVG+"polyline").get("stroke-dasharray") is not None for r in rails}=={False,True})
    check.equal("SVG channel crosses symbol or label",crossings,[])
    for d in data["trace"]["diagnostics"]:
        if d["level"] not in ("ERROR","WARNING") or d["target_kind"] not in ("node","link"):
            continue
        g=(nodes if d["target_kind"]=="node" else links)[d["target"]]
        halo=any(el.get("class") in ("halo","halo-line") for el in g)
        check.require(f"SVG {d['target']} {d['level']} halo",d["level"].lower() in g.get("class").split() and halo)


class GalleryIndex(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids,self.tabs,self.panels,self.targets=[],[],[],[]
        self.svg_count=0

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if attrs.get("role")=="tab":
            self.tabs.append(attrs["aria-controls"])
        if attrs.get("role")=="tabpanel":
            self.panels.append(attrs["id"])
        if "data-focus" in attrs:
            self.targets.append(attrs["data-focus"])
        if tag=="svg":
            self.svg_count+=1


def contract_checks(check):
    check.equal("public primitive constructors",len(schema.COMPONENTS),24)
    serial=og.OpticalGraph("unpolarized branches")
    serial.add("Src",og.LaserSource(532,1,pol="unpolarized",power_mw=8))
    serial.add("Split",og.NPBS(reflect_ratio=.25))
    serial.add("A",og.Photodiode()); serial.add("B",og.Camera())
    serial.link("Src.front","Split.p1",exact_mm=20)
    serial.link("Split.p2","A.front",exact_mm=20); serial.link("Split.p3","B.front",exact_mm=20)
    t=og.trace_graph(serial)
    check.equal("incoherent 25% port",t["terminals"]["A"]["total_power_mw"],2,1e-9)
    check.equal("incoherent 75% port",t["terminals"]["B"]["total_power_mw"],6,1e-9)
    check.equal("no beat between incoherent modes",t["terminals"]["A"]["beats"],[])
    for title,fn in (
        ("empty HWP",lambda:og.HalfWaveplate()),("empty QWP",lambda:og.QuarterWaveplate()),
        ("overdetermined HWP",lambda:og.HalfWaveplate(fast_axis_deg=0,target_pol="P")),
        ("invalid port",lambda: serial.link("Split.x","B.front")),
        ("duplicate reversed link",lambda: serial.link("Split.p1","Src.front")),
    ):
        try:
            fn()
        except og.GraphError as e:
            check.require(title,e.code=="invalid_port_or_duplicate_link" if "link" in title or "port" in title else True)
        else:
            check.require(title,False)
    angled=og.OpticalGraph("sloped aperture")
    angled.add("Src",og.LaserSource(532,2,pol="LHC",height_mm=90))
    angled.add("M",og.SpatialFold(-15,yaw_deg=22))
    angled.add("Stop",og.Aperture(.5)); angled.add("T",og.TargetPlane())
    angled.link("Src.front","M.a",exact_mm=0,can_fold=True)
    angled.link("M.b","Stop.a",exact_mm=0); angled.link("Stop.b","T.front",exact_mm=100)
    t=og.trace_graph(angled); r=t["terminals"]["T"]["beams"][0]
    check.require("3D downward cutout",t["nodes"]["M"]["board_cutout_required"])
    check.equal("reflected helicity",r["pol"],"RHC")
    check.equal("unit direction pitch",r["k"][2],math.sin(math.radians(-15)),1e-10)
    check.equal("three-dimensional height",r["height_mm"],90+100*math.sin(math.radians(-15)),1e-9)
    check.equal("small stop clips/high launch warns",{d["code"] for d in t["diagnostics"]}==
                {"fold_at_nonstandard_height","polarization_fold_hazard","severe_clipping"},True)
    # Independent Gaussian number: never replace a face spot by the coupling specification.
    g=og.OpticalGraph("face q")
    g.add("L",og.LaserSource(780,.8,m2=1.3)); g.add("T",og.Camera()); g.link("L.front","T.front",exact_mm=200)
    t=og.trace_graph(g)["terminals"]["T"]
    zr=math.pi*.4**2/(1.3*.00078)
    check.equal("face spot from q and M²",t["diameter_mm"],.8*math.sqrt(1+(200/zr)**2),1e-10)


    # The same real plate orientations must work in both directions for synthesized dual plates.
    for pin in ("a", "b"):
        g = og.OpticalGraph("dual-plate " + pin)
        g.add("L", og.LaserSource(532, 1, pol="elliptical"))
        g.add("D", og.DualWaveplate(target_pol="S"))
        g.add("T", og.Camera())
        g.link("L.front", "D."+pin, exact_mm=0)
        g.link("D."+("b" if pin == "a" else "a"), "T.front", exact_mm=0)
        check.equal("elliptical to S entering " + pin, og.trace_graph(g)["terminals"]["T"]["pol"], "S")

    g = og.OpticalGraph("bounded spans")
    g.add("S", og.FiberSource(532, 1))
    g.add("W", og.Window(4, refractive_index=2))
    g.add("P", og.Aperture(5))
    g.add("T", og.Camera())
    g.link("S.front", "W.a", min_mm=0, max_mm=100)
    g.link("W.b", "P.a", min_mm=0, max_mm=20)
    g.link("P.b", "T.front", min_mm=5, max_mm=10)
    g.span("S.front", "P.a", exact_mm=120)
    g.span("W.b", "T.front", exact_mm=30)
    t = og.trace_graph(g)
    check.require("overlapping bounded geometric spans", t["valid"])
    for link, distance in zip(g.links, (96, 20, 10)):
        check.equal("simultaneous span "+link.id,t["links"][link.id]["resolved_air_mm"],distance,1e-8)
    check.equal("window reduced q propagation",t["terminals"]["T"]["defocus_mm"],128,1e-8)
    g.span("W.b", "T.front", exact_mm=40)
    check.require("infeasible span remains an error","span_distance_error" in {d["code"] for d in og.trace_graph(g)["diagnostics"]})
    payload = serial.to_dict()
    payload["links"][0]["id"] = "L4"
    imported = og.OpticalGraph.from_dict(payload)
    imported.add("Stop", og.BeamDump())
    imported.link("Split.p4", "Stop.front")
    check.equal("append after importing custom channel IDs",len({x.id for x in imported.links}),len(imported.links))


def reference_differences(data, expected):
    """Audit the literal surface interpretation alongside the supplied coupling-mode contract."""
    differences = []
    for spec in expected.get("terminalChecks", []):
        node = spec["node"]
        terminal = data["trace"]["terminals"][node]
        if "face_diameter_mm" not in terminal:
            continue
        if "diameter_mm" in spec and abs(terminal["face_diameter_mm"]-spec["diameter_mm"]) > spec["diameter_tol_mm"]:
            differences.append(dict(field="diameter_mm", node=node, golden=spec["diameter_mm"],
                                    tolerance=spec["diameter_tol_mm"], face=terminal["face_diameter_mm"],
                                    mode=terminal["diameter_mm"]))
        if "collimated" in spec and terminal["face_collimated"] != spec["collimated"]:
            differences.append(dict(field="collimated", node=node, golden=spec["collimated"],
                                    face=terminal["face_collimated"], mode=terminal["collimated"],
                                    face_radius_mm=terminal["radius_mm"]))
    for diag in data["trace"]["diagnostics"]:
        if diag.get("strict_aperture_code",diag["code"]) != diag["code"]:
            differences.append(dict(field="aperture_diagnostic",node=diag["target"], aperture_ratio=diag["aperture_ratio"],
                                    golden=diag["code"], strict_section_4=diag["strict_aperture_code"]))
    return differences


def cli_checks(check, negatives, positives):
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder)
        cli=HERE.parent/"scripts/optical_graph_render.py"
        py=HERE/"optical_graph_fixtures.py"
        def run(label,code,*args):
            result=subprocess.run([sys.executable,"-B",str(cli),*map(str,args)],cwd=tmp,capture_output=True,text=True)
            check.equal(label,result.returncode,code)
            if result.returncode!=code:
                check.items[-1]["stderr"]=result.stderr[-1200:]
        run("valid Python CLI",0,py,"--func",positives[0],"-o","one.html","--svg","one.svg","--json","one.json")
        run("single interchange JSON CLI",0,"one.json","-o","round.html","--json","round.json")
        check.equal("JSON CLI round trip",
                    json.loads((tmp/"one.json").read_bytes())==json.loads((tmp/"round.json").read_bytes()),True)
        run("invalid graph CLI",1,py,"--func",negatives[0],"-o","bad.html")
        run("invalid graph with opt-in",0,py,"--func",negatives[0],"--allow-invalid","-o","bad.html")
        run("missing function CLI",2,py,"--func","missing_builder","-o","bad.html")
        run("missing input CLI",2,"missing.py","--func","builder","-o","bad.html")
        (tmp/"broken.py").write_text("def broken(:\n",encoding="utf-8")
        run("syntax error CLI",2,"broken.py","--all")
        run("batch with invalid circuits",1,py,"--all")
        gallery=tmp/"results/optical-graph/gallery.html"
        parser=GalleryIndex()
        parser.feed(gallery.read_text(encoding="utf-8"))
        check.equal("gallery unique IDs",len(set(parser.ids)),len(parser.ids))
        check.equal("gallery tabs select all panels",parser.tabs,parser.panels)
        check.require("all diagnostic and terminal targets exist",set(parser.targets)<=set(parser.ids))
        check.equal("gallery SVG count",parser.svg_count,len(ALL_FIXTURES))
        check.equal("standalone SVG count",len(list((gallery.parent/"svg").glob("*.svg"))),len(ALL_FIXTURES))


def main():
    expected=json.loads(EXPECTED.read_bytes())["fixtures"]
    by_name={fn.__name__:fn for fn in ALL_FIXTURES}
    common=Checks()
    common.equal("exact fixture coverage",sorted(by_name),sorted(expected))
    common.equal("fixture count including negative examples",len(ALL_FIXTURES),10)
    cases=[]
    for key,spec in expected.items():
        check=Checks()
        row=dict(fixture=key)
        try:
            graph=by_name[key]()
            data=graph.to_dict(include_trace=True)
            trace=data["trace"]
            fixture_checks(check,graph,data,spec)
            reconstructed=og.OpticalGraph.from_dict(json.loads(json_text(data)))
            check.require("traced interchange round trip",reconstructed.to_dict(include_trace=True)==data)
            svg_checks(check,render_svg(graph,data),graph,data)
            row.update(valid=trace["valid"],diagnostics=trace["diagnostics"],
                       literal_face_or_aperture_differences=reference_differences(data,spec),terminals={
                k:{p:v for p,v in terminal.items() if p not in ("beams","beats")} for k,terminal in trace["terminals"].items()})
        except Exception as exc:
            check.equal("execution",f"{type(exc).__name__}: {exc}","success")
        row.update(check.report())
        cases.append(row)
        print(f"{'PASS' if row['passed'] else 'FAIL'}  {key}  ({row['check_count']} checks)")
        for fail in row["checks"]:
            if not fail["passed"]:
                print("     ",fail)
    try:
        from pm_optics_checks import checks as pm_checks
        pm_checks(common)
        contract_checks(common)
        cli_checks(common,[k for k,v in expected.items() if not v["expectedValid"]],
                   [k for k,v in expected.items() if v["expectedValid"]])
    except Exception as exc:
        common.equal("public API / CLI execution",f"{type(exc).__name__}: {exc}","success")
    for fail in common.items:
        if not fail["passed"]:
            print("FAIL ",fail)
    passed=sum(case["passed"] for case in cases)
    count=len(cases)
    success=passed==count and common.report()["passed"]
    references = [HERE.parent/"docs/specs/optical-graph-v1.0-spec.md", HERE/"optical_graph_fixtures.py", EXPECTED]
    baseline = {p.name: sha256(p.read_bytes()).hexdigest() for p in references}
    report=dict(format="hksop-optical-graph-acceptance-v1",passed=success,passed_count=passed,total=count,
                pass_percent=100*passed/count if count else 0,valid_count=sum(c.get("valid",False) for c in cases),
                reference_sha256=baseline,
                conventions={
                    "sm_pm":"The golden coupling diameter/collimation refers to the afocal mode waist. The Gaussian spot and curvature at the actual fiber face are reported separately.",
                    "aom":"The golden AOM marginal-overfill example is a warning. For active AOM apertures only, D/(2w) from 0.90 to <1 is tight_aperture; strict_aperture_code retains the §4 severity.",
                    "coupling_tolerance":"FiberCoupler diagnoses a mode size mismatch beyond ±5% of design. Each golden assertion independently applies the tolerance from the supplied JSON.",
                    "span":"Multiple free legs share the correction from their midpoints subject to their bounds and all span sums."},
                fixtures=cases,contract=common.report())
    write_output(OUT/"acceptance.json",json_text(report))
    print(f"{passed}/{count} fixtures ({report['pass_percent']:g}%), {len(common.items)} API/CLI checks. {OUT/'acceptance.json'}")
    return 0 if success else 1


if __name__=="__main__":
    sys.exit(main())
