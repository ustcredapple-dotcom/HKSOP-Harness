"""Determine axial adjustment from the optical graph before looking at any M6 holes."""
from collections import defaultdict
import math

SOURCES = {"FiberSource", "LaserSource"}
PLATES = {"QuarterWaveplate", "HalfWaveplate", "DualWaveplate", "Window", "Aperture", "CustomTwoPort"}
STAGE_MIN = {"Lens":87.5, "RetroMirror":87.5, "Camera":100., "AOM":100.}
WEIGHT = {"Aperture":0, "Lens":1, "RetroMirror":2, "AOM":3, "Camera":4}


def evaluate(graph, policy="auto"):
    if policy not in ("auto","fixed"):
        raise ValueError("height policy must be auto or fixed")
    nodes={n["id"]:n for n in graph["nodes"]}
    reads=defaultdict(list)
    for b in graph["trace"]["beams"]:
        reads[b["to"].split(".")[0]].append(b["end"])
    links={p:e for e in graph["links"] for p in (e["u"],e["v"])}
    kind=lambda n:nodes[n]["type"]
    def neighbour(port):
        e=links.get(port)
        return None if not e else (e["v"] if e["u"]==port else e["u"])
    def upstream(n,pin="front"):
        port=neighbour(n+"."+pin)
        seen=set()
        while port and port not in seen:
            seen.add(port)
            key,p=port.split(".")
            yield key
            if kind(key) in SOURCES or kind(key) in ("RetroMirror","FiberCoupler"):
                break
            if p in ("a","b"):
                port=neighbour(key+(".a" if p=="b" else ".b"))
            else:
                break
    rows={}
    for key in nodes:
        samples=reads[key]
        rows[key]=dict(component=kind(key),required=False,rules=[],reason="轴向无独立精调需求",coveredBy=None,
                       minRayleighMm=min((r["q_mm"][1] for r in samples),default=None),
                       minAbsRadiusMm=min((abs(r["radius_mm"]) for r in samples if r["radius_mm"] is not None),default=None))
    def mark(n,rule,why):
        row=rows[n]
        row["required"]=True
        if rule not in row["rules"]:
            row["rules"].append(rule)
        row["reason"]=why
    covered=set()
    for n,c in nodes.items():
        k=kind(n)
        fore=list(upstream(n)) if k in ("Camera","TargetPlane","RetroMirror") else []
        lens=next((x for x in fore if kind(x)=="Lens"),None)
        if k=="FiberCoupler":
            rows[n].update(coveredBy="MFT",reason="MFT 自带轴向调焦")
        elif k=="Camera":
            if lens and any(not r["afocal"] and (abs(r["radius_mm"] or math.inf)<2000 or abs(r["q_mm"][0])<3*r["q_mm"][1]) for r in reads[n]):
                mark(n,"S1","聚焦相机位于像面或焦面")
                covered.update([n,lens])
            else:
                rows[n].update(coveredBy="collimated_monitor",reason="准直分光监视，无像面调焦")
        elif k=="TargetPlane":
            rows[n].update(coveredBy=lens or "fixed_target",reason="靶面固定，调焦转移到最近的聚焦物镜")
            if lens:
                mark(lens,"S1","固定实验靶面，物镜沿光轴调焦")
                covered.update([n,*fore[:fore.index(lens)+1]])
        elif k=="RetroMirror" and lens and (any(q["bidirectional"] for p,q in links.items() if p==n+".front")):
            mark(n,"S1","猫眼返回端镜承担后焦面调节")
            covered.update([n,*fore[:fore.index(lens)+1]])
        elif k in ("AOM","Aperture") and any(not r["afocal"] and abs(r["q_mm"][0])<2*r["q_mm"][1] and r["q_mm"][1]<5 for r in reads[n]):
            mark(n,"S1","作用面位于短瑞利长度束腰")
            covered.add(n)
    constraints=[(e["u"],e["v"],e["exact_mm"],e["tol_mm"]) for e in graph["links"] if e["exact_mm"] is not None]
    constraints += [(e["start"],e["end"],e["exact_mm"],e["tol_mm"]) for e in graph["spans"]]
    for a,b,length,tol in constraints:
        u,v=a.split(".")[0],b.split(".")[0]
        if kind(u)==kind(v)=="Lens":
            f1,f2=nodes[u]["params"]["f_mm"],nodes[v]["params"]["f_mm"]
            if abs(length-f1-f2)<=max(tol,1e-6):
                short,long=sorted((u,v),key=lambda n:abs(nodes[n]["params"]["f_mm"]))
                mark(short,"S2","锁距无焦/中继镜组的短焦端吸收焦距公差")
                rows[long].update(coveredBy=short,reason="长焦端提供刚性基准")
                covered.update((u,v))
    for a,b,_,tol in constraints:
        u,v=a.split(".")[0],b.split(".")[0]
        if tol<=1 and not ({u,v}&covered) and not (rows[u]["coveredBy"] or rows[v]["coveredBy"]):
            candidates=[k for k in (u,v) if kind(k) not in SOURCES|{"Window","TargetPlane","FiberCoupler"}]
            if candidates:
                n=min(candidates,key=lambda k:WEIGHT.get(kind(k),10))
                mark(n,"S3","独立锁距公差 ≤1 mm，选择较轻的一端")
                covered.update((u,v))
    for n,row in rows.items():
        if n not in covered and not row["coveredBy"] and row["minRayleighMm"] is not None and row["minRayleighMm"]<5:
            mark(n,"S3","局部瑞利长度小于 5 mm")
    nominal=graph["default_plane_height_mm"]
    if policy=="auto":
        nominal=max([nominal]+[STAGE_MIN.get(kind(n),87.5) for n,r in rows.items() if r["required"]])
    for n,r in rows.items():
        r["mount"]="rigid"
        if r["required"]:
            r.update(mount="LS30",stackHeightMm=37.5,workingTravelMm=[-3.,3.],mechanicalLimitsMm=[-3.25,3.25])
            if nominal<STAGE_MIN.get(kind(n),87.5):
                r.update(mount="low_profile_stage_mount",availableHeadroomMm=nominal-37.5,
                         preferredKits=["objective-post-ls30-6l1-r3","objective-post-ls30-6r1-r3"] if kind(n)=="Lens" else [])
                r["heightEvidence"]="库中 R3 物镜负载的 62.5 mm 从上板量起，叠加滑台为 100 mm。固定低光高需有独立光学与机械基准的低剖面座。"
    return dict(heightPolicy=policy,boardAxisHeightMm=nominal,nodes=rows)
