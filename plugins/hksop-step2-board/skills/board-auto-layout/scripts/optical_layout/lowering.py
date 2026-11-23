"""Hardware selection, port frames, steering expansion, spatial branches and straight runs."""
from functools import lru_cache
from collections import defaultdict
import json
import math
from .hksop_runtime import library_root

STANDARD_BOARDS = [(250,200),(300,200),(350,250),(450,300),(450,350),(500,350),(600,450),(750,500),(900,600)]
FOUR = {"PBS","NPBS","SamplerPlate","Dichroic"}
SOURCES = {"LaserSource","FiberSource"}
TERMINALS = {"Camera","Photodiode","BeamDump","TargetPlane","FiberCoupler"}
V = ((1,0),(0,1),(-1,0),(0,-1))


def catalog():
    return _catalog(library_root())


@lru_cache(maxsize=4)
def _catalog(root):
    curation=json.loads((root/"library/curation.json").read_bytes())
    slim_path=root/"library/catalog-ai-slim.json"
    if not curation or slim_path.stat().st_size>=200_000:raise ValueError("精简库或主推配置不符合只读接口")
    full=json.loads((root/"library/catalog.json").read_bytes())
    slim=json.loads((root/"library/catalog-ai-slim.json").read_bytes())
    if full["version"]!=slim["catalogVersion"]:
        raise ValueError("Native catalog versions disagree")
    return {k["id"]:k for k in full["kits"]}, {k["kitId"]:k for k in slim["kits"]},full


def xy(p):
    return (p["xMm"],p["yMm"])


def rot(p,r):
    x,y=p
    return ((x,y),(-y,x),(-x,-y),(y,-x))[r%4]


def offset(p,q):
    return (p[0]+q[0],p[1]+q[1])


def advance(p,dir,d):
    dx,dy=V[dir%4]
    return (round(p[0]+dx*d,6),round(p[1]+dy*d,6))


def rectangle(x0,y0,x1,y1):
    return [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]


def bounds(poly):
    return (min(p[0] for p in poly),min(p[1] for p in poly),max(p[0] for p in poly),max(p[1] for p in poly))


def kit_for(n):
    t,p=n["type"],n["params"]
    large=p.get("aperture_inch",1)>=1
    if t=="PBS":return "mt-cube-pbs-1inch-m1-r1" if large else "uma1-r8-pbs05-0"
    if t=="NPBS":return "mt-cube-bs-1inch-m1-r1"
    if t in ("Dichroic","SamplerPlate"):return "fixed-dichroic-1inch-45-r1"
    if t in ("FiberSource","FiberCoupler"):return "fiber-coupling-mft-rear-r3"
    if t=="Isolator":return "new-isolator" if abs(p["wavelength_nm"]-780)<2 else None
    if t=="Lens":return "new-lens-filter" if p["aperture_inch"]<=1 else "new-lens-filter-2inch"
    if t in ("HalfWaveplate","QuarterWaveplate"):return "new-waveplate-single" if large else "waveplate-single-05-m1"
    if t=="DualWaveplate":return "waveplate-centered-dual-1-wpc2-r1" if large else "waveplate-double-05-m1"
    if t=="BeamDump":return "compact-beam-dump-pd-bd1-r4" if p["monitor_pd"] else "compact-beam-dump-bd1-r2"
    if t=="AOM":return "new-aom"
    if t=="Camera":return "new-camera-flir"
    if t=="Photodiode":return "new-pd"
    if t=="Aperture":return "new-iris"
    if t=="RetroMirror":return "uma1-r8-mt-am1s5-0"
    if t=="HeightShift":
        heights=(p["in_height_mm"],p["out_height_mm"])
        return next((k for k,v in catalog()[1].items() if v["primitive"]=="height_shift"
                     and v["parameters"]["mode"]==p["mode"] and
                     set(heights)=={v["parameters"]["inputHeightMm"],v["parameters"]["outputHeightMm"]}),None)
    return None


def shift_ports(node):
    """Directions of propagation in the actual assembly's local XY frame, in quarter turns."""
    record=catalog()[1][node["kit"]]
    first,last=record["foldDirectionsLocalDeg"]
    if node["params"]["in_height_mm"]!=record["parameters"]["inputHeightMm"]:
        first,last=last+180,first+180
    return round(first/90)%4,round(last/90)%4


def port_side(n,pin,heading,hand):
    if pin.startswith("p"):
        return (heading+{"p1":2,"p2":hand,"p3":0,"p4":-hand}[pin])%4
    if pin=="front":
        return (heading+(0 if n["type"] in SOURCES else 2))%4
    if pin=="a": return (heading+2)%4
    if n["type"]=="HeightShift" and n["params"]["mode"]=="turn90":return (heading+hand)%4
    return heading%4


def face(n,pin):
    if n["type"]=="CustomTwoPort":return n["params"]["length_mm"]/2
    if n["type"]=="Window":return n["params"]["thickness_mm"]/2
    if n["type"] in ("PBS","NPBS"):
        return n["params"].get("aperture_inch",1)*25.4/2
    return 0.


def lower(graph, stages, hardware=None):
    hardware=hardware or {}
    nodes={n["id"]:{**n,"kit":kit_for(n),"hardware":hardware.get(n["id"],{})} for n in graph["nodes"]}
    for spec in nodes.values():
        if spec["type"] not in ("FiberSource","FiberCoupler"):continue
        hw=spec["hardware"];head=str(hw.get("collimator",hw.get("lensModel",""))).upper()
        if hw.get("fixedFocus") or head.startswith("F240"):
            if hw.get("kitId")=="fiber-coupling-mft-rear-r3":
                raise ValueError("定焦准直头不可配后置 MFT 空台")
            chosen=hw.get("kitId")
            if chosen and chosen not in catalog()[0]:raise ValueError("未登记的紧凑安装座")
            spec["kit"]=chosen
            if not chosen:hw=dict(hw,reason="定焦准直头需要无 MFT 的紧凑安装座");spec["hardware"]=hw
    span_links={key for sp in graph["spans"] for key in sp["link_ids"]}
    beams=defaultdict(list)
    for b in graph["trace"]["beams"]:beams[b["link_id"]].append(b)
    edges=[]; chains=[]; steering=[]
    for l in graph["links"]:
        a,pa=l["u"].split("."); b,pb=l["v"].split(".")
        k=max([nodes[x]["params"].get("steering_mirrors",0) for x in (a,b) if nodes[x]["type"]=="FiberCoupler"] or [0])
        fc=next((x for x in (a,b) if nodes[x]["type"]=="FiberCoupler"),None)
        if k:
            steering.append(dict(terminal=fc,channel=l["id"],mirrors=[f"M_steer_{fc}_{i+1}" for i in range(k)]))
        fixed=l["exact_mm"] is not None or l["id"] in span_links
        e=dict(id=l["id"],a=a,b=b,pa=pa,pb=pb,length=l["resolved_air_mm"],lo=l["resolved_air_mm"] if fixed else l["min_mm"],
               hi=l["resolved_air_mm"] if fixed else l["max_mm"],fixed=fixed,exact=l["exact_mm"] is not None,adjustLo=l["resolved_air_mm"] if l["exact_mm"] is not None else l["min_mm"],
               adjustHi=l["resolved_air_mm"] if l["exact_mm"] is not None else l["max_mm"],fold=l["can_fold"],steer=k,fc=fc)
        if k and any(v["start"]["pol"] not in ("P","S") for v in beams[l["id"]]):
            raise ValueError("fiber steering would fold mixed polarization on "+l["id"])
        edges.append(e)
    by_port={e[n]+'.'+e[p]:e for e in edges for n,p in (('a','pa'),('b','pb'))}
    downstream=set()
    for n,c in nodes.items():
        if c["type"] not in ("VerticalFold","SpatialFold"):continue
        last=n; port=n+".b"; chain=[]
        while port in by_port:
            e=by_port[port]
            key,p=(e["b"],e["pb"]) if port==e["a"]+"."+e["pa"] else (e["a"],e["pa"])
            if key in downstream or key==n or nodes[key]["type"] in FOUR:raise ValueError("ambiguous spatial assembly")
            downstream.add(key);chain.append(dict(node=key,link=e["id"],entry=p,previous=last));last=key
            if p not in ("a","b"):break
            port=key+(".a" if p=="b" else ".b")
        chains.append(dict(root=n,members=chain))
    planar=[e for e in edges if e["a"] not in downstream and e["b"] not in downstream]
    return dict(nodes=nodes,edges=planar,allEdges=edges,spans=graph["spans"],spatial=chains,downstream=downstream,
                steering=steering,beams=beams,stages=stages)


def rigid_runs(model):
    adjacent=defaultdict(list)
    for e in model["allEdges"]:
        if not e["fold"] and not e["steer"]:
            adjacent[e["a"]].append(e);adjacent[e["b"]].append(e)
    used=set();runs=[]
    for root in sorted(adjacent,key=lambda n:len(adjacent[n])==2):
        for edge in adjacent[root]:
            if edge["id"] in used:continue
            n=root; total=0.; items=[dict(id=n,offset_mm=0.)];ids=[]
            while edge:
                used.add(edge["id"]);ids.append(edge["id"])
                a,b=(("a","pa"),("b","pb")) if edge["a"]==n else (("b","pb"),("a","pa"))
                other=edge[b[0]]
                total+=face(model["nodes"][n],edge[a[1]])+edge["length"]+face(model["nodes"][other],edge[b[1]])
                items.append(dict(id=other,offset_mm=round(total,6)))
                n=other
                if model["nodes"][n]["type"] in FOUR|{"VerticalFold","SpatialFold","HeightShift"}:break
                rest=[e for e in adjacent[n] if e["id"] not in used]
                edge=rest[0] if len(rest)==1 else None
            widths=[]
            for item in items:
                kit=model["nodes"][item["id"]]["kit"]
                if kit:
                    b=catalog()[0][kit]["layout"]["collisionBoundsMm"]
                    widths.append(max(abs(b["yMin"]),abs(b["yMax"])))
            runs.append(dict(nodes=items,links=ids,nominalLengthMm=round(total,6),maxHalfWidthMm=max(widths or [15])))
    return runs
