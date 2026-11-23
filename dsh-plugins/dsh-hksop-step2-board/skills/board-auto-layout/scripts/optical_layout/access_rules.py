"""Plan-view hand access, rigid tail profiles and point intersections in mm."""
import math
from itertools import combinations
from .lowering import V, bounds, rectangle, rot, xy
TOL=1.e-5
# Local native mount frame: +Y points to the back of the FC connector. The 85 mm
# envelope includes the moving plug and boot at either end of the MFT travel.
REAR_LIMIT_MM={"FC/APC":85.0,"FC/PC":87.0}
def controls(kind,kit,body):
    x0,y0,x1,y1=body
    def area(name,ax,ay,side):
        box={'E':(ax,ay-15,ax+25,ay+15),'W':(ax-25,ay-15,ax,ay+15),
             'N':(ax-15,ay,ax+15,ay+25),'S':(ax-15,ay-25,ax+15,ay)}[side]
        return name,rectangle(*box)
    if kit=="waveplate-centered-dual-1-wpc2-r1":
        return [area("QWP rotation B",21,-10,"E"),area("HWP rotation A",-21,10,"W")]
    if kind in ("HalfWaveplate","QuarterWaveplate","DualWaveplate"):
        return [area("rotation dial",(x0+x1)/2,y1,"N")]
    if kit=="mt-cube-pbs-1inch-m1-r1":
        return [area("MT-AM1 left rear adjuster",-17.9,-56.86,"S"),area("MT-AM1 right rear adjusters",17.9,-56.86,"S")]
    if kit=="fiber-coupling-mft-rear-r3":
        return [area("CS30 X side",29.3,9,"E"),area("CS30 Y upper access",-17.5,9,"W"),
                area("MFT Z micrometer",25.6,70.765,"N"),area("FC insertion and straight exit",0,85,"N")]
    return []


def fiber_tail(row,width,height,connector="FC/APC",designated=None):
    turn=round(row["rotationDeg"]/90)%4;bx,by=xy(row["baseOrigin"])
    length=REAR_LIMIT_MM[connector];rear=rot((0,length),turn);x,y=bx+rear[0],by+rear[1]
    poly=[(bx+a,by+b) for a,b in (rot(q,turn) for q in rectangle(-9,21,9,length))]
    box=bounds(poly);over=max(0,-box[0],-box[1],box[2]-width,box[3]-height)
    side=("north","west","south","east")[turn];d={"west":x,"east":width-x,"south":y,"north":height-y}
    target=designated or min(d,key=d.get)
    valid_direction=(side==target) if designated else d[side]<=min(d.values())+TOL
    return dict(direction=side,designatedSide=target,exitVector=rot((0,1),turn),rigidBoundsMm=box,tipMm=[x,y],
                overhangMm=over,matchingExit=valid_direction,straightCableLengthToEdgeMm=d[side],profile=connector)


def contact(a,b,c,d):
    """Intersection of closed segments. For a collinear overlap return both ends."""
    def det(v,z):return v[0]*z[1]-v[1]*z[0]
    def sub(p,q):return (p[0]-q[0],p[1]-q[1])
    v,z=sub(b,a),sub(d,c);offs=sub(c,a);denom=det(v,z)
    if abs(denom)>TOL:
        t=det(offs,z)/denom;u=det(offs,v)/denom
        return [(a[0]+t*v[0],a[1]+t*v[1])] if -TOL<=t<=1+TOL and -TOL<=u<=1+TOL else []
    if abs(det(offs,v))>TOL:return []
    use=int(abs(v[1])>abs(v[0]))
    if abs(v[use])<TOL:return []
    lo,hi=sorted(((c[use]-a[use])/v[use],(d[use]-a[use])/v[use]))
    lo,hi=max(0,lo),min(1,hi)
    if lo>hi+TOL:return []
    return [(a[0]+t*v[0],a[1]+t*v[1]) for t in ([lo,hi] if hi-lo>TOL else [lo])]


def crossings(paths,model):
    rows=[]
    for edge,path in paths.items():
        beams=model.get("beams",{}).get(edge,[])
        p=path["points"];ids=path["ids"]
        heights={round(x["start"]["height_mm"],6) for x in beams} or {model["stages"]["boardAxisHeightMm"]}
        for a,b,i,j in zip(p,p[1:],ids,ids[1:]):
            rows.append((edge,a,b,i,j,heights))
    result=[]
    for (e,a,b,i,j,h),(f,c,d,k,l,g) in combinations(rows,2):
        if not h&g:continue
        hits=contact(a,b,c,d)
        if not hits:continue
        shared=[p for p,n in [(a,i),(b,j)] for q,m in [(c,k),(d,l)] if n==m and math.dist(p,q)<TOL]
        if len(hits)==1 and any(math.dist(hits[0],p)<TOL for p in shared):continue
        result.append(dict(links=[e,f],segments=[[i,j],[k,l]],pointsMm=hits,heightMm=min(h&g)))
    return result
