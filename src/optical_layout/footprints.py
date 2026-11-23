"""Conservative convex projections of measured component outlines for planar clearance."""
from functools import lru_cache
from .lowering import bounds,catalog,rectangle,rot,xy
def hull(points):
    def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    pts=sorted(set(points))
    def half(order):
        v=[]
        for p in order:
            while len(v)>1 and cross(v[-2],v[-1],p)<=.000001:v.pop()
            v.append(p)
        return v
    return tuple(half(pts)[:-1]+half(pts[::-1])[:-1])

@lru_cache(maxsize=100)
def local(kit,r):
    g=catalog()[0][kit]["layout"]
    polys=g.get("collisionPolygonsMm") or []
    return tuple(hull([rot(xy(p),r) for p in poly]) for poly in polys)
def polygons(q,box=None):
    if q.stage or not q.kit or box is not None and any(abs(a-b)>.001 for a,b in zip(box,q.box)):
        return (tuple(rectangle(*(box or q.box))),)
    return tuple(tuple((x+q.base[0],y+q.base[1]) for x,y in poly) for poly in local(q.kit,q.rotation)) or (tuple(rectangle(*q.box)),)
def overlaps(a,b,gap=.08):
    ax,ay,bx,by=bounds(a);cx,cy,dx,dy=bounds(b)
    if ax>dx+gap or cx>bx+gap or ay>dy+gap or cy>by+gap:return False
    for poly in (a,b):
        for i,(x,y) in enumerate(poly):
            u,v=poly[i-1];nx,ny=y-v,u-x
            pad=gap*(nx*nx+ny*ny)**.5
            pa=[p*nx+q*ny for p,q in a];pb=[p*nx+q*ny for p,q in b]
            if max(pa)+pad<min(pb) or max(pb)+pad<min(pa):return False
    return True
def conflicts(state,boxes=None):
    outlines={k:polygons(q,boxes[k] if boxes else None) for k,q in state.poses.items()}
    # Tail including its connector is a solid obstacle for neighbours.
    for k,q in state.poses.items():
        if q.kit=="fiber-coupling-mft-rear-r3":
            from .access_rules import REAR_LIMIT_MM
            b=q.base
            geom=[rot(p,q.rotation) for p in rectangle(-6,21,6,max(REAR_LIMIT_MM.values()))]
            outlines[k]+= (tuple((x+b[0],y+b[1]) for x,y in geom),)
    seen=[]
    for k,q in state.poses.items():
        for kk in seen:
            if any(overlaps(p,r) for p in outlines[k] for r in outlines[kk]):return k+" 与 "+kk+" 实体投影重叠"
        seen.append(k)
        for a,b,bb in state.lines:
            if k not in (a,b) and any(overlaps(p,rectangle(*bb)) for p in outlines[k]):return k+" 遮挡 "+a+" → "+b
        for label,poly in q.keep:
            for key,parts in outlines.items():
                if key!=k and any(overlaps(poly,part) for part in parts):return k+" "+label+" 手位占用 "+key
            for a,b,bb in state.lines:
                if overlaps(poly,rectangle(*bb)):return k+" "+label+" 手位穿光 "+a+" → "+b
    return ""
