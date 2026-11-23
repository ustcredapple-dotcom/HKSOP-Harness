"""Reuse orthogonal route families as search seeds. Every candidate is re-traced and re-verified."""
import json
from pathlib import Path
from .folding_planner import State,direction,face,linebox,manhattan,mirror,pose,support,union

def instantiate(m,seed,offsets=None,strict=True):
    poses={};paths={};lines=[];offsets=offsets or {}
    for k,(kind,x,y,d,hand,stage,sr) in seed['nodes'].items():
        a,b=offsets.get(k,(0,0));point=(x+a,y+b)
        if kind in ('Steer','Fold'):poses[k]=mirror(k,point,d,(d+hand)%4,kind=='Steer')
        else:poses[k]=pose(m['nodes'][k],point,d,hand,stage,sr)
    for e in m['edges']:
        ids=seed['paths'][e['id']]
        if ids[0]!=e['a'] or ids[-1]!=e['b']:return
        pts=[poses[k].point for k in ids]
        if any(a==b or abs(a[0]-b[0])>.001 and abs(a[1]-b[1])>.001 for a,b in zip(pts,pts[1:])):return
        orig=[seed['nodes'][k][1:3] for k in ids]
        if any(direction(a,b)!=direction(c,d) for a,b,c,d in zip(pts,pts[1:],orig,orig[1:])):return
        air=sum(manhattan(a,b) for a,b in zip(pts,pts[1:]))-face(m['nodes'][e['a']],e['pa'])-face(m['nodes'][e['b']],e['pb'])
        if strict and not e['lo']-.001<=air<=e['hi']+.001:return
        paths[e['id']]=dict(ids=ids,points=pts,airMm=round(air,6),bends=len(ids)-2)
        r=max([max(b['start']['diameter_mm'],b['end']['diameter_mm'])/2 for b in m['beams'][e['id']]] or [.25])
        lines.extend((ka,kb,linebox(a,b,r)) for ka,kb,a,b in zip(ids,ids[1:],pts,pts[1:]))
    return State(poses,paths,lines,union([support(q) for q in poses.values()]),sum(v['bends'] for v in paths.values()))
def registered(m,w,h,pitch):
    fn=Path(__file__).with_name('route-families.json')
    if not fn.is_file():return
    for item in json.loads(fn.read_bytes()):
        if item['pitch']!=pitch or w<item['width'] or h<item['height']:continue
        names={k:n[0] for k,n in item['nodes'].items() if n[0] not in ('Fold','Steer')}
        if names!={k:n['type'] for k,n in m['nodes'].items() if k not in m['downstream']}:continue
        if set(item['paths'])!={e['id'] for e in m['edges']}:continue
        s=instantiate(m,item)
        if s:yield s
