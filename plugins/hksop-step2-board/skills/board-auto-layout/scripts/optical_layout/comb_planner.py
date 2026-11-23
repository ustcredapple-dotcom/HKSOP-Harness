"""Periodic reflected teeth on a straight horizontal transmitted bus."""
from itertools import product
from .folding_planner import State,face,linebox,manhattan,mirror,pose,support,union
from .lowering import offset

def topology(model):
    nodes=model["nodes"]
    sources=[k for k,n in nodes.items() if n["type"]=="FiberSource"]
    if len(sources)!=1 or model["spatial"] or any(v["required"] for v in model["stages"]["nodes"].values()):return
    byport={}
    for e in model["edges"]:
        byport[e["a"],e["pa"]]=(e,e["b"],e["pb"])
        byport[e["b"],e["pb"]]=(e,e["a"],e["pa"])
    source=sources[0];plates=("DualWaveplate","HalfWaveplate","QuarterWaveplate")
    def walk(k,p):
        seq=[]
        while (k,p) in byport:
            edge,k,p=byport[k,p]
            if k in [n for _,n in seq]:return []
            seq.append((edge,k))
            if nodes[k]["type"] not in plates:return seq
            if p!="a":return []
            p="b"
        return []
    main=walk(source,"front");teeth=[]
    if not main:return
    while nodes[main[-1][1]]["type"]=="PBS":
        split=main[-1][1]
        if main[-1][0] not in [byport.get((split,"p1"),(None,))[0]]:return
        arm=walk(split,"p2");rest=walk(split,"p3")
        if not arm or not rest or nodes[arm[-1][1]]["type"]!="FiberCoupler":return
        teeth.append((split,arm))
        if nodes[rest[-1][1]]["type"]=="FiberCoupler":
            teeth.append((None,rest));break
        main.extend(rest)
    if len(teeth)<2 or set(nodes)!={source,*[n for e,n in main],*[n for _,arm in teeth for _,n in arm]}:return
    kinds=lambda arm:[nodes[n]["type"] for _,n in arm]
    if any(kinds(arm)!=kinds(teeth[0][1]) for _,arm in teeth) or len(teeth[0][1])!=2:return
    if any(arm[-1][0]["steer"]!=2 for _,arm in teeth):return
    return source,main,teeth

def candidates(model,pattern,w,h,pitch):
    if not pattern:return
    source,main,teeth=pattern
    nodes=model["nodes"];n=len(teeth)
    def grid(x):return round(x/pitch)*pitch
    def make(k,x,y,d,bybase=False):
        q=pose(nodes[k],(x,y),d,1)
        return q.moved((x-q.base[0],y-q.base[1])) if bybase else q
    # The rigid termination is 95 mm from its locating hole. Control corridors
    # may be reached from outside the board. Bodies, feet and holes are checked below.
    for left,period,offset_x,outer,top,bottom in product(
        (37.5,25,50,62.5),(112.5,125,100,137.5,150),(37.5,50,-50,62.5,-62.5,75,-75,-37.5),
        (87.5,100,112.5),(37.5,50,62.5,25,75),(87.5,100,112.5)):
        if any(abs(k-grid(k))>.01 for k in (left,period,offset_x,outer,top,bottom)):continue
        xs=[left+(n-i-1)*period for i in range(n)];yt=h-top
        if any(x+offset_x<25 or x+offset_x>w-25 for x in xs) or xs[0]>w-outer-65:continue
        if yt-bottom<100:continue
        for mirror_height in (50,62.5,75,37.5):
            ym=bottom+mirror_height
            for drop in (50,62.5,37.5,75,87.5,100):
                yw=yt-drop
                if yw-ym<35:continue
                poses={source:make(source,w-outer,yt,2,True)}
                edges={};previous=source;onbus=[source]+[k for e,k in main]
                anchors={source:w-outer}
                for i,(pbs,arm) in enumerate(teeth):
                    if pbs:anchors[pbs]=xs[i]
                for i,(e,key) in enumerate(main,1):
                    if key in anchors:x=anchors[key]
                    else:
                        before=next(j for j in range(i-1,-1,-1) if onbus[j] in anchors)
                        after=next(j for j in range(i+1,len(onbus)) if onbus[j] in anchors)
                        x=grid(anchors[onbus[before]]+(anchors[onbus[after]]-anchors[onbus[before]])*(i-before)/(after-before))
                    poses[key]=make(key,x,yt,2,True)
                    edges[e["id"]]=[previous,key];previous=key
                for i,(pbs,arm) in enumerate(teeth):
                    x=xs[i];(e,plate),(tail,fc)=arm
                    poses[plate]=make(plate,x,yw,3);poses[fc]=make(fc,x+offset_x,bottom,3,True)
                    if pbs:edges[e["id"]]=[pbs,plate]
                    else:
                        fold="M_fold_"+e["id"]+"_1"
                        poses[fold]=mirror(fold,(x,yt),2,3,False)
                        edges[e["id"]]=[previous,fold,plate]
                    d=0 if offset_x>0 else 2
                    aa,bb=("M_steer_"+fc+"_"+str(j) for j in (1,2))
                    poses[aa]=mirror(aa,(x,ym),3,d,True)
                    poses[bb]=mirror(bb,(x+offset_x,ym),d,3,True)
                    edges[tail["id"]]=[plate,aa,bb,fc]
                if any(q.kind in ("FiberSource","FiberCoupler") and
                       (q.box[0]<0 or q.box[1]<0 or q.box[2]>w or q.box[3]>h) for q in poses.values()):continue
                paths={};lines=[]
                for e in model["edges"]:
                    ids=edges[e["id"]]
                    if ids[0]!=e["a"]:ids=ids[::-1]
                    pts=[poses[k].point for k in ids]
                    if any((abs(a[0]-b[0])>.001 and abs(a[1]-b[1])>.001) or a==b for a,b in zip(pts,pts[1:])):break
                    length=sum(manhattan(a,b) for a,b in zip(pts,pts[1:]))-face(nodes[e["a"]],e["pa"])-face(nodes[e["b"]],e["pb"])
                    if not e["lo"]-.001<=length<=e["hi"]+.001 or len(ids)>2 and not (e["fold"] or e["steer"]):break
                    paths[e["id"]]=dict(ids=ids,points=pts,airMm=round(length,6),bends=len(pts)-2)
                    radius=max([max(b["start"]["diameter_mm"],b["end"]["diameter_mm"])/2 for b in model["beams"][e["id"]]] or [.25])
                    lines.extend((ka,kb,linebox(a,b,radius)) for ka,kb,a,b in zip(ids,ids[1:],pts,pts[1:]))
                else:
                    yield State(poses,paths,lines,union([support(q) for q in poses.values()]),2*n+1)
