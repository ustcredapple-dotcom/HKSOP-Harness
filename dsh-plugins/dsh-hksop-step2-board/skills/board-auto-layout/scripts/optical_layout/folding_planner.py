"""Orthogonal, port-constrained placement with bounded search over lengths and 90° turns."""
from dataclasses import dataclass, replace
from functools import lru_cache
from itertools import product
import math
import random

from .lowering import FOUR, SOURCES, V, advance, bounds, catalog, face, offset, port_side, rectangle, rot, shift_ports, xy

EPS=1e-5


def union(boxes):
    return (min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))


def crosses(a,b,margin=.08):
    return a[0]<b[2]+margin and b[0]<a[2]+margin and a[1]<b[3]+margin and b[1]<a[3]+margin


def linebox(a,b,r=.35):
    return (min(a[0],b[0])-r,min(a[1],b[1])-r,max(a[0],b[0])+r,max(a[1],b[1])+r)


def shift_box(b,p):
    return (b[0]+p[0],b[1]+p[1],b[2]+p[0],b[3]+p[1])


def local_box(kit):
    g=catalog()[0][kit]["layout"]
    b=g.get("collisionBoundsMm") or g["baseBoundsMm"]
    return (b["xMin"],b["yMin"],b["xMax"],b["yMax"])


def rect_rot(b,d):
    return bounds([rot(v,d) for v in rectangle(*b)])


@dataclass(frozen=True)
class Pose:
    key:str
    kind:str
    kit:str
    point:tuple
    head:int
    hand:int
    rotation:int
    base:tuple
    box:tuple
    keep:tuple
    stage:str=""
    stage_rot:int=0

    def moved(self,delta):
        return replace(self, point=offset(self.point,delta),base=offset(self.base,delta),box=shift_box(self.box,delta),
                       keep=tuple((why,tuple(offset(p,delta) for p in poly)) for why,poly in self.keep))


def _hand_box(normal,extent):
    rad=math.radians(normal);vx,vy=math.cos(rad),math.sin(rad)
    return tuple((vx*x-vy*y,vy*x+vx*y) for x,y in ((extent,-15),(extent+25,-15),(extent+25,15),(extent,15)))


@lru_cache(maxsize=2048)
def shape(kind,kit,heading,hand,manual,stage,stage_rot,size,incoming_local=0):
    g=catalog()[0][kit]["layout"] if kit else {}
    if kind in ("Fold","Steer","RetroMirror"):
        din=V[heading];dout=V[(heading+(2 if kind=="RetroMirror" else hand))%4]
        required=math.degrees(math.atan2(dout[1]-din[1],dout[0]-din[0]))
        rotation=round((required-g["opticalFrontNormalDeg"])/90)%4
    elif kind in ("FiberSource","FiberCoupler"):
        rotation=(heading+(1 if kind=="FiberSource" else 3))%4
    elif kind in FOUR:
        # The diagonal bisects the incident and reflected rays modulo 180 degrees.
        local=g.get("pbsDiagonalAngleLocalDeg",g.get("opticalSurfaceAngleDeg",45))
        rotation=(heading+round((hand*45-local)/90))%4
    else:
        rotation=(heading-incoming_local)%4
    center=rot(xy(g.get("opticalCenterMm") or {"xMm":0,"yMm":0}),rotation)
    base=(-center[0],-center[1])
    w,h=size
    own=local_box(kit) if kit else (-w/2,-h/2,w/2,h/2)
    box=shift_box(rect_rot(own,rotation),base)
    boxes=[box]; access=[]
    from .access_rules import controls
    for label, poly in controls(kind,kit,own):
        access.append((label,tuple(offset(rot(p,rotation),base) for p in poly)))
    if manual:
        normal=(g["opticalFrontNormalDeg"]+180)%360
        nx,ny=math.cos(math.radians(normal)),math.sin(math.radians(normal))
        pts=[xy(q) for poly in g.get("collisionPolygonsMm",[]) for q in poly] or rectangle(*own)
        extent=max(x*nx+y*ny for x,y in pts)
        access.append(("mirror",tuple(offset(rot(p,rotation),base) for p in _hand_box(normal,extent))))
    if stage:
        sg=catalog()[0][stage]["layout"]
        points=[xy(q) for poly in sg["collisionPolygonsMm"] for q in poly]
        extremity=min(points,key=lambda pt:pt[0])
        handle=rectangle(extremity[0]-25,extremity[1]-15,extremity[0],extremity[1]+15)
        access.append(("micrometer",tuple(offset(rot(p,stage_rot),base) for p in handle)))
        boxes.append(shift_box(rect_rot(local_box(stage),stage_rot),base))
    return rotation,base,union(boxes),tuple(access)


def pose(n,point,heading,hand,stage="",stage_rot=0):
    t=n["type"];kit=n["kit"]
    if t=="CustomTwoPort":size=(n["params"]["length_mm"],max(24,n["params"]["clear_aperture_mm"]+8))
    else:size=tuple(n.get("hardware",{}).get("envelopeMm",(24,24) if t=="LaserSource" else (42,38)))
    manual=t=="Steer" or (t=="RetroMirror" and n["params"].get("actuation")=="manual")
    local=shift_ports(n)[0] if t=="HeightShift" and kit else 0
    if kit=="waveplate-centered-dual-1-wpc2-r1":local=1
    r,b,box,keep=shape(t,kit,heading,hand,manual,stage,stage_rot,size,local)
    return Pose(n["id"],t,kit,point,heading,hand,r,offset(b,point),shift_box(box,point),
                tuple((why,tuple(offset(q,point) for q in poly)) for why,poly in keep),stage,stage_rot)


@lru_cache(maxsize=1024)
def support_shape(kit,rotation,stage,stage_rot):
    def side(name,r):
        raw=catalog()[0][name]["layout"]
        b=raw.get("baseBoundsMm") or raw["collisionBoundsMm"]
        return rect_rot((b["xMin"],b["yMin"],b["xMax"],b["yMax"]),r)
    boxes=[side(kit,rotation)]
    if stage:boxes.append(side(stage,stage_rot))
    return union(boxes)


def support(q):
    if not q.kit:return q.box
    bb=shift_box(support_shape(q.kit,q.rotation,q.stage,q.stage_rot),q.base)
    if q.kit=="fiber-coupling-mft-rear-r3":
        from .access_rules import REAR_LIMIT_MM
        return union([bb,shift_box(rect_rot((-6,21,6,max(REAR_LIMIT_MM.values())),q.rotation),q.base)])
    return bb


def variants(n,p,head,hand,m):
    required=m["stages"]["nodes"].get(n["id"],{}).get("required",False)
    if not required:
        yield pose(n,p,head,hand);return
    for rev in (0,2):
        for h in ("l","r"):
            yield pose(n,p,head,hand,"stage-board-lbtek-ls30-6"+h+"1-r3",(head+rev)%4)


def mirror(key,point,d1,d2,steer):
    turn=(d2-d1)%4
    n=dict(id=key,type="Steer" if steer else "Fold",params={},kit="uma1-r8-mt-"+("am1s5" if steer else "flf1s")+"-45")
    return pose(n,point,d1,1 if turn==1 else -1)


@dataclass
class State:
    poses:dict
    paths:dict
    lines:list
    box:tuple
    folds:int=0


def ordered_edges(m,seed=0):
    edges=m["edges"];nodes=m["nodes"]
    root=next((n for n in nodes if nodes[n]["type"] in SOURCES),None)
    if not root:root=next(iter(nodes))
    rng=random.Random(seed)
    incident={k:sum(k in (e["a"],e["b"]) for e in edges) for k in nodes}
    if seed%5:
        core=[k for k in nodes if incident[k] and (nodes[k]["type"] in FOUR or m["stages"]["nodes"][k]["required"] or nodes[k]["type"]=="FiberCoupler")]
        if core:root=core[(seed-1)%len(core)]
    ranks={e["id"]:rng.random() for e in edges}
    # Close a shared-cell / ring branch while its interior is still free.
    degrees=incident.copy();remaining=set(k for k in nodes if degrees[k])
    leaves=[k for k in remaining if degrees[k]<2]
    while leaves:
        k=leaves.pop();remaining.discard(k)
        for e in edges:
            if k not in (e["a"],e["b"]):continue
            other=e["a"] if e["b"]==k else e["b"]
            if other in remaining:
                degrees[other]-=1
                if degrees[other]==1:leaves.append(other)
    if remaining and seed%4:
        root=sorted(remaining)[seed%len(remaining)]
    known={root};result=[];todo=list(edges)
    while todo:
        frontier=[e for e in todo if e["a"] in known or e["b"] in known]
        if not frontier:raise ValueError("disconnected board input")
        def priority(e):
            close=e["a"] in known and e["b"] in known
            target=e["b"] if e["a"] in known else e["a"]
            return (not close, bool(remaining and seed%4 and not {e["a"],e["b"]}<=remaining),(e["steer"]>0) if seed%3==0 else (e["steer"]==0 if seed%3==1 else False),not e["fixed"],e["fold"] if seed%2==0 else False,
                    nodes[target]["type"] in ("Camera","Photodiode","BeamDump") if seed%3==0 else False,ranks[e["id"]] if seed else edges.index(e))
        e=min(frontier,key=priority);todo.remove(e)
        reverse=e["a"] not in known
        to=e["a"] if reverse else e["b"]
        result.append((e,reverse,to in known));known.add(to)
    return root,result


def direction(a,b):
    if abs(a[1]-b[1])<EPS:return 0 if b[0]>a[0] else 2
    if abs(a[0]-b[0])<EPS:return 1 if b[1]>a[1] else 3
    raise ValueError("nonorthogonal segment")


def manhattan(a,b):
    return abs(a[0]-b[0])+abs(a[1]-b[1])


def _steps(start,d,phase,pitch,low,high):
    axis=d%2;sign=V[d][axis]
    first=(sign*(phase-start[axis]))%pitch
    return [round(first+i*pitch,6) for i in range(max(0,math.ceil((low-first-EPS)/pitch)),
                                                  math.floor((high-first+EPS)/pitch)+1)]


def hands_for(node):
    if node["type"]=="HeightShift" and node["kit"]:
        first,last=shift_ports(node)
        return (-1,) if (last-first)%4==3 else (1,)
    return (1,-1) if node["type"] in FOUR|{"HeightShift"} else (1,)


def headings(node,pin,in_dir):
    for h in hands_for(node):
        orientation=(in_dir+2-port_side(node,pin,0,h))%4
        yield orientation,h


def sequences(d,bends):
    for turns in product((1,-1),repeat=bends):
        dirs=[d]
        for turn in turns:dirs.append((dirs[-1]+turn)%4)
        yield dirs


def options(state,model,e,reverse,closing,pitch,width,height,rng,effort):
    nodes=model["nodes"]
    u,v,pu,pv=(e["b"],e["a"],e["pb"],e["pa"]) if reverse else (e["a"],e["b"],e["pa"],e["pb"])
    start=state.poses[u]; d=port_side(nodes[u],pu,start.head,start.hand)
    end=state.poses.get(v);pad=face(nodes[u],pu)+face(nodes[v],pv)
    lo,hi=e["lo"]+pad,e["hi"]+pad
    if e["steer"]: counts=[e["steer"]]
    elif e["fold"] and not e["fixed"]:counts=[0,1,2]+([3] if closing else [])
    else:counts=[0]
    if any(b["start"]["pol"] not in ("P","S") for b in model["beams"][e["id"]]):
        counts=[k for k in counts if not k]
    counts=[k for k in counts if k<=4]
    result=[]
    for count in counts:
        candidates=[]
        for dirs in sequences(d,count):
            for head,hand in headings(nodes[v],pv,dirs[-1]):
                if end and (head!=end.head or (nodes[v]["type"] in FOUR and hand!=end.hand)):continue
                template=pose(nodes[v],(0,0),head,hand)
                phase=-(template.base[dirs[-1]%2])
                def walk(points,j,length):
                    last=points[-1];dd=dirs[j];rem=len(dirs)-j
                    if j:
                        previous=points[-2]
                        tip=mirror("_candidate",last,dirs[j-1],dd,bool(e["steer"]))
                        spanbox=linebox(previous,last)
                        for old in state.poses.values():
                            if crosses(tip.box,old.box) or any(crosses(bounds(poly),old.box) for _,poly in tip.keep):return
                            if any(crosses(bounds(poly),tip.box) for _,poly in old.keep):return
                            if old.key!=u and crosses(spanbox,old.box):return
                        if any(crosses(tip.box,b) for _,_,b in state.lines):return
                    if end and rem<=2:
                        projected=(end.point[0]-last[0])*V[dd][0]+(end.point[1]-last[1])*V[dd][1]
                        dist=projected
                        if dist<=EPS:return
                        nxt=advance(last,dd,dist)
                        if rem==1:
                            if manhattan(nxt,end.point)>EPS:return
                            dist2=0
                        else:
                            dist2=(end.point[0]-nxt[0])*V[dirs[-1]][0]+(end.point[1]-nxt[1])*V[dirs[-1]][1]
                            if dist2<=EPS or manhattan(advance(nxt,dirs[-1],dist2),end.point)>EPS:return
                        total=length+dist+dist2
                        if lo-EPS<=total<=hi+EPS:candidates.append((points+([nxt] if rem==2 else [])+[end.point],head,hand))
                        return
                    last_leg=(rem==1)
                    minseg=max(16,lo-length if last_leg else 0)
                    # Two parallel legs on a folded path require a hand-accessible return aisle.
                    if not last_leg and j>0:minseg=max(minseg,100 if start.stage or nodes[u]["type"]=="AOM" or nodes[v]["type"]=="AOM" else 75)
                    limit=min((width,height)[dd%2],hi-length-22*(rem-1))
                    if minseg>limit+EPS:return
                    values=_steps(last,dd,phase if last_leg else 0,pitch,minseg,limit)
                    if last_leg:
                        if e["fixed"]:values=[hi-length]
                        else:
                            values.extend([minseg,min(limit,max(minseg,e["length"]+pad-length))])
                    values=sorted(set(round(x,6) for x in values if minseg-EPS<=x<=limit+EPS))
                    if not last_leg and len(values)>6:
                        values=values[:3]+rng.sample(values[3:],3)
                    if last_leg and len(values)>9:values=values[:5]+rng.sample(values[5:],4)
                    for val in values:
                        pt=advance(last,dd,val)
                        if last_leg:
                            finish=pose(nodes[v],pt,head,hand)
                            lastbox=linebox(last,pt)
                            if any(crosses(finish.box,old.box) or
                                   (old.key!=u and crosses(lastbox,old.box))
                                   for old in state.poses.values()):continue
                            candidates.append((points+[pt],head,hand))
                        else:walk(points+[pt],j+1,length+val)
                walk([start.point],0,0)
        if candidates:
            rng.shuffle(candidates)
            # Sample feasible routes, not just their lengths. A short U-turn often
            # places the coupler inside its own steering mount and cannot survive.
            if count:
                ranked=sorted(candidates,key=lambda item:sum(manhattan(a,b) for a,b in zip(item[0],item[0][1:])))
                short=ranked[:max(10,effort*2)]
                valid=[];tested=set()
                for route,head,hand in short+candidates[:max(350,effort*12)]:
                    key=(tuple(route),head,hand)
                    if key in tested:continue
                    tested.add(key)
                    probe=insert(state,model,e,reverse,u,v,route,head,hand,None if closing else pose(nodes[v],route[-1],head,hand),width,height)
                    if probe:
                        l,b,r,t=probe.box
                        if (math.ceil((-l-EPS)/pitch)<=math.floor((width-r+EPS)/pitch) and
                            math.ceil((-b-EPS)/pitch)<=math.floor((height-t+EPS)/pitch)):
                            valid.append((route,head,hand))
                            if len(valid)>=effort:break
                candidates=valid
            elif len(candidates)>effort:candidates=candidates[:effort]
            result.extend(candidates)
    rng.shuffle(result)
    return u,v,result


def clear_input(model,poses,w,h):
    for k,n in model["nodes"].items():
        if k not in poses or not n.get("hardware",{}).get("entrancePort"):continue
        q=poses[k];ray=linebox(q.point,advance(q.point,q.head+2,2*max(w,h)),n["params"]["diameter_mm"]/2)
        for key,other in poses.items():
            if key!=k and (crosses(ray,other.box) or any(crosses(ray,bounds(poly)) for _,poly in other.keep)):return False
    return True


def insert(state,model,e,reverse,u,v,route,head,hand,ending,width,height):
    points=route;dirs=[direction(a,b) for a,b in zip(points,points[1:])]
    additions={};ids=[u]
    for j,point in enumerate(points[1:-1]):
        logical=j+1 if (not reverse)==(e["fc"]==e["b"]) else len(points)-2-j
        key=f"M_steer_{e['fc']}_{logical}" if e["steer"] else f"M_fold_{e['id']}_{j+1}"
        additions[key]=mirror(key,point,dirs[j],dirs[j+1],bool(e["steer"]));ids.append(key)
    if ending:additions[v]=ending
    ids.append(v)
    old=list(state.poses.values())
    for q in additions.values():
        for x in old:
            if crosses(q.box,x.box):return
            if any(crosses(bounds(poly),x.box) for _,poly in q.keep) or any(crosses(bounds(poly),q.box) for _,poly in x.keep):return
        for a,b,box in state.lines:
            if crosses(q.box,box) and q.key not in (a,b):return
            if any(crosses(bounds(poly),box) for _,poly in q.keep):return
        old.append(q)
    if not clear_input(model,{**state.poses,**additions},width,height):return
    newbox=union([state.box]+[support(q) for q in additions.values()])
    if newbox[2]-newbox[0]>width+EPS or newbox[3]-newbox[1]>height+EPS:return
    newlines=[]
    beam_radius=max([max(b["start"]["diameter_mm"],b["end"]["diameter_mm"])/2 for b in model["beams"][e["id"]]] or [.25])
    for i,(a,b) in enumerate(zip(points,points[1:])):
        box=linebox(a,b,beam_radius)
        for q in old:
            if q.key not in (ids[i],ids[i+1]) and crosses(q.box,box):return
            if any(crosses(bounds(poly),box) for _,poly in q.keep):return
        newlines.append((ids[i],ids[i+1],box))
    travel=sum(manhattan(a,b) for a,b in zip(points,points[1:]))
    available=travel-face(model["nodes"][u],e["pb" if reverse else "pa"])-face(model["nodes"][v],e["pa" if reverse else "pb"])
    if not e["lo"]-EPS<=available<=e["hi"]+EPS:return
    if len(points)>=4:
        spacing=100 if any(q.stage or q.kind=="AOM" for q in old if q.key in ids) else 75
        if any(manhattan(points[i],points[i+1])<spacing-EPS for i in range(1,len(points)-2)):return
    edges={**state.paths,e["id"]:dict(ids=ids[::-1] if reverse else ids,points=points[::-1] if reverse else points,
                                      airMm=round(available,6),bends=len(points)-2)}
    from .access_rules import crossings
    if crossings(edges,model):return
    return State({**state.poses,**additions},edges,state.lines+newlines,newbox,state.folds+len(points)-2)


def forward_space(state,model,width,height,pitch):
    """Reserve exits of placed ports before another branch closes them off."""
    boxes=[state.box]
    for e in model["edges"]:
        if e["id"] in state.paths:continue
        for node,port,other,otherport in ((e["a"],e["pa"],e["b"],e["pb"]),(e["b"],e["pb"],e["a"],e["pa"])):
            if node not in state.poses:continue
            q=state.poses[node];d=port_side(model["nodes"][node],port,q.head,q.hand)
            edge=q.box[(2,3,0,1)[d]]
            dist=abs(edge-q.point[d%2])+10
            if not e["fold"] and not e["steer"]:
                dist=max(dist,e["lo"]+face(model["nodes"][node],port)+face(model["nodes"][other],otherport))
            tip=advance(q.point,d,dist);area=linebox(q.point,tip,.25)
            if any(crosses(area,n.box) for key,n in state.poses.items() if key not in (node,other)):return False
            if any(crosses(area,bounds(p)) for n in state.poses.values() for _,p in n.keep):return False
            boxes.append(linebox(tip,tip,4))
    l,b,r,t=union(boxes)
    return (math.ceil((-l-EPS)/pitch)<=math.floor((width-r+EPS)/pitch) and
            math.ceil((-b-EPS)/pitch)<=math.floor((height-t+EPS)/pitch))


def score(state,w,h,rng):
    a,b,c,d=state.box
    area=(c-a)*(d-b)/(w*h)
    output=[q for q in state.poses.values() if q.kind=="FiberCoupler"]
    sides=len({q.rotation for q in output})
    spread=0
    if len(output)>2 and sides==1:
        axis=0 if output[0].rotation%2==0 else 1
        values=sorted(q.base[axis] for q in output);gaps=[b-a for a,b in zip(values,values[1:])]
        spread=(max(gaps)-min(gaps))/max(w,h)
    return max(0,sides-1)*2.0+spread+area+.24*max((c-a)/w,(d-b)/h)+.025*state.folds+rng.random()*.27


def plans(model,width,height,pitch,seed=0,beam_width=32,effort=32):
    rng=random.Random(seed)
    root,order=ordered_edges(model,seed)
    source=model["nodes"][root]
    heading=(seed//2)%4 if seed else 0
    temp=pose(source,(0,0),heading,1)
    states=[State({root:p},{},[],support(p)) for hand in hands_for(source)
            for p in variants(source,(-temp.base[0],-temp.base[1]),heading,hand,model)]
    last_depth=0
    for e,rev,close in order:
        next_states=[]
        for state in states:
            u,v,paths=options(state,model,e,rev,close,pitch,width,height,rng,effort)
            for route,head,hand in paths:
                ends=(None,) if close else variants(model["nodes"][v],route[-1],head,hand,model)
                for end in ends:
                    s=insert(state,model,e,rev,u,v,route,head,hand,end,width,height)
                    if s:
                        l,b,r,t=s.box
                        if forward_space(s,model,width,height,pitch):
                            next_states.append((score(s,width,height,rng),s))
        if not next_states:
            return [],dict(depth=last_depth,stoppedAt=e["id"],reason="方向、尺寸、操作或通光占区无可行延续")
        next_states.sort(key=lambda item:item[0])
        # Distinct stages and mirrored branches must survive pruning.
        states=[];seen=set()
        for _,s in next_states:
            key=tuple((q.key,round(q.point[0],2),round(q.point[1],2),q.head,q.hand,q.stage,q.stage_rot) for q in s.poses.values())
            if key not in seen:
                states.append(s);seen.add(key)
                if len(states)>=beam_width:break
        last_depth+=1
    return states,dict(depth=last_depth,candidates=len(states))


def translations(state,w,h,pitch):
    b=state.box
    xs=range(math.ceil((-b[0]-EPS)/pitch),math.floor((w-b[2]+EPS)/pitch)+1)
    ys=range(math.ceil((-b[1]-EPS)/pitch),math.floor((h-b[3]+EPS)/pitch)+1)
    shifts=[(x*pitch,y*pitch) for x in xs for y in ys]
    for dx,dy in sorted(shifts,key=lambda s:abs(b[0]+s[0]-(w-b[2]-s[0]))+abs(b[1]+s[1]-(h-b[3]-s[1]))):
        delta=(dx,dy)
        yield State({k:q.moved(delta) for k,q in state.poses.items()},
                    {k:{**r,"points":[offset(p,delta) for p in r["points"]]} for k,r in state.paths.items()},
                    [(a,b,shift_box(box,delta)) for a,b,box in state.lines],shift_box(state.box,delta),state.folds)



def transform_state(state,r,shift):
    def point(p):return offset(rot(p,r),shift)
    def box(b):return shift_box(rect_rot(b,r),shift)
    return State({k:replace(q,point=point(q.point),base=point(q.base),box=box(q.box),
                  head=(q.head+r)%4,rotation=(q.rotation+r)%4,stage_rot=(q.stage_rot+r)%4,
                  keep=tuple((why,tuple(point(p) for p in poly)) for why,poly in q.keep)) for k,q in state.poses.items()},
                 {k:{**v,"points":[point(p) for p in v["points"]]} for k,v in state.paths.items()},
                 [(a,b,box(bb)) for a,b,bb in state.lines],box(state.box),state.folds)


def join_routes(a,b,d,f,e,model,pitch):
    """Orthogonal routes with exactly matching directions at both splice ports."""
    if d==f and manhattan(a,b) and (a[0]==b[0] or a[1]==b[1]) and direction(a,b)==d:
        yield [a,b]
    if not e["fold"]:return
    if any(x["start"]["pol"] not in ("P","S") for x in model["beams"][e["id"]]):return
    along=lambda p,q,dir_:(q[0]-p[0])*V[dir_][0]+(q[1]-p[1])*V[dir_][1]
    if d%2!=f%2:
        corner=(b[0],a[1]) if d%2==0 else (a[0],b[1])
        if along(a,corner,d)>16 and along(corner,b,f)>16:yield [a,corner,b]
    elif abs(a[1-d%2]-b[1-d%2])>=75:
        for length in _steps(a,d,0,pitch,20,min(e["hi"]-40,550)):
            p=advance(a,d,length);q=(p[0],b[1]) if d%2==0 else (b[0],p[1])
            if along(q,b,f)>16:yield [a,p,q,b]


def halves(model,bridge):
    neighbors={k:set() for k in model["nodes"] if k not in model["downstream"]}
    for e in model["edges"]:
        if e==bridge:continue
        neighbors[e["a"]].add(e["b"]);neighbors[e["b"]].add(e["a"])
    a={bridge["a"]};stack=list(a)
    while stack:
        for v in neighbors[stack.pop()]-a:a.add(v);stack.append(v)
    b=set(neighbors)-a
    if len(a)<2 or len(b)<2:return
    return [{**model,"nodes":{k:n for k,n in model["nodes"].items() if k in group},
             "edges":[e for e in model["edges"] if e["a"] in group and e["b"] in group]} for group in (a,b)]


def compatible(a,b):
    for q in a.poses.values():
        for p in b.poses.values():
            if crosses(q.box,p.box):return False
            if any(crosses(bounds(poly),p.box) for _,poly in q.keep) or any(crosses(bounds(poly),q.box) for _,poly in p.keep):return False
    for l,r in ((a,b),(b,a)):
        for _,_,beam in l.lines:
            if any(crosses(p.box,beam) or any(crosses(bounds(poly),beam) for _,poly in p.keep) for p in r.poses.values()):return False
    return True


def spliced_plans(model,w,h,pitch,seed=0):
    """Place independent branches first, then connect them on the same screw lattice."""
    rng=random.Random(seed)
    cuts=[]
    for edge in model["edges"]:
        if edge["steer"] or edge["fixed"]:continue
        groups=halves(model,edge)
        if groups:cuts.append((abs(len(groups[0]["edges"])-len(groups[1]["edges"])),edge,groups))
    cuts.sort(key=lambda v:v[0])
    for _,e,groups in cuts:
        pools=[]
        for g in groups:
            candidates=[]
            for n in range(3):
                s,_=plans(g,w,h,pitch,seed*3+n,12,20)
                if s:candidates+=rng.sample(s,min(len(s),6))
            if not candidates:break
            pools.append(candidates)
        if len(pools)!=2:continue
        pairs=[(a,b,r) for a in pools[0] for b in pools[1] for r in range(4)]
        rng.shuffle(pairs)
        for a,b,r in pairs:
            b=transform_state(b,r,(0,0))
            u=a.poses[e["a"]];v=b.poses[e["b"]];pa=port_side(model["nodes"][u.key],e["pa"],u.head,u.hand)
            pb=(port_side(model["nodes"][v.key],e["pb"],v.head,v.hand)+2)%4
            if not e["fold"] and pa!=pb:continue
            opts=[]
            for axis,side in enumerate((w,h)):
                low=a.box[axis+2]-side-b.box[axis];high=a.box[axis]+side-b.box[axis+2]
                opts.append(range(math.ceil((low-EPS)/pitch),math.floor((high+EPS)/pitch)+1))
            shifts=list(product(*opts));rng.shuffle(shifts)
            for sx,sy in shifts:
                shift=(sx*pitch,sy*pitch);pt=offset(v.point,shift)
                if manhattan(u.point,pt)>e["hi"]+face(model["nodes"][u.key],e["pa"])+face(model["nodes"][v.key],e["pb"]):continue
                routes=list(join_routes(u.point,pt,pa,pb,e,model,pitch))
                if not routes:continue
                bb=transform_state(b,0,shift)
                if not compatible(a,bb):continue
                bounds_=union([a.box,bb.box])
                if math.ceil((-bounds_[0]-EPS)/pitch)>math.floor((w-bounds_[2]+EPS)/pitch) or math.ceil((-bounds_[1]-EPS)/pitch)>math.floor((h-bounds_[3]+EPS)/pitch):continue
                merged=State({**a.poses,**bb.poses},{**a.paths,**bb.paths},a.lines+bb.lines,bounds_,a.folds+bb.folds)
                for route in routes:
                    s=insert(merged,model,e,False,u.key,v.key,route,v.head,v.hand,None,w,h)
                    if s:yield s,e["id"]
