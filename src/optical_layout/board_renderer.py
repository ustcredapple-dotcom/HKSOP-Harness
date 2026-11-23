"""Offline seven-layer engineering drawing in millimetres, with a separate Z section."""
from html import escape
from math import hypot, pi, sqrt

from .hole_snapper import grid
from .lowering import bounds, catalog, face, offset, rectangle, rot, xy


def number(x):
    return f"{x:.3f}".rstrip("0").rstrip(".") or "0"


def board_svg(graph,model,state,ledger,sketch=False,problems=()):
    board=ledger["board"];w,h=board["widthMm"],board["heightMm"]
    occupied=[q.box for q in state.poses.values()]+[bounds(poly) for q in state.poses.values() for _,poly in q.keep]
    left=19-min(0,min(b[0] for b in occupied));top=46+max(0,max(b[3] for b in occupied)-h)
    bottom=top+h;notes=bottom-min(0,min(b[1] for b in occupied))
    spatial=ledger["spatialAssemblies"];pagew=max(left+max(w,max(b[2] for b in occupied))+19,298);pageh=notes+(83 if spatial else 38)
    def pos(q):return left+q[0],bottom-q[1]
    def pts(poly):return " ".join(number(x)+","+number(y) for x,y in map(pos,poly))
    def poly(p,attr):return '<polygon points="'+pts(p)+'" '+attr+'/>'
    def line(a,b,style):return '<polyline points="'+pts([a,b])+'" '+style+'/>'
    def circle(p,r,attr):
        x,y=pos(p);return f'<circle cx="{number(x)}" cy="{number(y)}" r="{number(r)}" {attr}/>'
    def text(x,y,v,size=3.2,color="#203743",extra=""):
        return f'<text x="{number(x)}" y="{number(y)}" font-size="{number(size)}" fill="{color}" {extra}>{escape(str(v))}</text>'
    def label(p,s,size=3,extra=""):
        return text(*pos(p),s,size,extra=extra)
    def group(id_,content):return '<g id="'+id_+'">'+"".join(content)+'</g>'
    prefix='''<defs><marker id="arrow" orient="auto-start-reverse" markerWidth="4" markerHeight="4" refX="3" refY="2" markerUnits="userSpaceOnUse"><path d="M0 0 L4 2 L0 4Z" fill="context-stroke"/></marker><pattern id="stageHatch" patternUnits="userSpaceOnUse" width="4" height="4"><path d="M0 4L4 0" stroke="#7ea7b5" stroke-width=".33"/></pattern></defs>'''
    sections=[];rows=ledger["nodes"];kits=catalog()[0];z=model["stages"]["boardAxisHeightMm"]
    plates=[q for q in rows.values() if q.get("stageKitId")]
    vertical=[m for items in spatial.values() for m in items if m.get("stageKitId")]
    a=[poly(rectangle(0,0,w,h),'fill="#f6f8f7" stroke="#314d56" stroke-width=".8"')]
    for axis,length in ((0,w),(1,h)):
        for i in range(0,int(length)+1,25):
            d=3.2 if i%50==0 else 1.7
            a.append(line((i,0) if axis==0 else (0,i),(i,-d) if axis==0 else (-d,i),'stroke="#63808a" stroke-width=".55"'))
            if i%50==0:a.append(label((i,-7) if axis==0 else (-5,i-1),str(i),2.8,'text-anchor="middle"' if axis==0 else 'text-anchor="end"'))
    if not sketch:
        for hole in grid(w,h,board["pitchMm"]).values():
            a.append(circle(xy(hole),2.5,'fill="none" stroke="#c0cbd0" stroke-width=".45"'))
    for item in board["mountingHoles"]:
        p=xy(item);a.extend([circle(p,5.5,'fill="#e7e9dd" stroke="#6a7252" stroke-width=".55"'),
                            circle(p,3.3,'fill="white" stroke="#6a7252" stroke-width=".5"'),label(offset(p,(4,5)),item["label"],3.2)])
    sections.append(group("board-and-m6-grid",a))
    a=[]
    for row in rows.values():
        center=xy(row["opticalCenter"])
        for hole in row["screws"]:
            hp=xy(hole)
            if row["mode"]=="adapter":a.append(line(center,hp,'fill="none" stroke="#ce730e" stroke-width=".62" stroke-dasharray="2 1" marker-end="url(#arrow)"'))
            a.append('<g><title>'+escape(row["id"]+" · "+hole["id"])+'</title>'+circle(hp,2,'fill="#174d78" stroke="white" stroke-width=".4"')+'</g>')
    screws=group("mounting-screws-and-borrowed-holes",a)
    a=[]
    for row in plates:
        stage=row["stageKitId"];r=row["stageRotationDeg"]//90;orig=xy(row["baseOrigin"]);q=row["qMm"]
        def tr(p):return offset(orig,rot(p,r))
        a.extend([poly([tr(p) for p in rectangle(-25,-50,25,50)],'fill="#e4eef3" stroke="#3f7897" stroke-width=".8"'),
                  poly([tr(p) for p in rectangle(-25+q,-25,25+q,25)],'fill="url(#stageHatch)" stroke="#478ba6" stroke-width=".75"')])
        silhouette=kits[stage]["layout"]["collisionPolygonsMm"]
        for p in silhouette:a.append(poly([tr(xy(pt)) for pt in p],'fill="none" stroke="#547484" stroke-width=".45"'))
        a.append(line(tr((-19+q,-19)),tr((19+q,-19)),'stroke="#24536b" stroke-width=".75" marker-start="url(#arrow)" marker-end="url(#arrow)"'))
        a.append(label(tr((0,42)),stage.split("-")[-2].upper()+f"  q={q:+.2f}",3.3,'text-anchor="middle" class="halo"'))
    side_controls=[]
    for stage_index,m in enumerate(vertical):
        scale=.31;cx=left+w*.76+stage_index*48;cy=notes+52
        def side(x,y):return f"{number(cx+scale*y)},{number(cy-scale*x)}"
        def side_poly(points,style):return '<polygon points="'+' '.join(side(x,y) for x,y in points)+'" '+style+'/>'
        a.append(text(cx,cy-16,m["id"]+" · LS30 "+m["stageKitId"].split("-")[-2].upper()+"   q="+number(m["qMm"])+" mm",3.0,extra='text-anchor="middle"'))
        a.append(side_poly(rectangle(-25,-50,25,50),'fill="#e4eef3" stroke="#3f7897" stroke-width=".55"'))
        a.append(side_poly(rectangle(-25+m["qMm"],-25,25+m["qMm"],25),'fill="url(#stageHatch)" stroke="#478ba6" stroke-width=".45"'))
        for outline in kits[m["stageKitId"]]["layout"]["collisionPolygonsMm"]:
            a.append(side_poly([xy(p) for p in outline],'fill="none" stroke="#547484" stroke-width=".35"'))
        a.append('<polyline points="'+side(-18,12)+' '+side(18,12)+'" stroke="#24536b" stroke-width=".55" marker-start="url(#arrow)" marker-end="url(#arrow)"/>')
        for x in (-12.5,12.5):
            for y in (-37.5,37.5):
                ax,ay=side(x,y).split(",");a.append(f'<circle cx="{ax}" cy="{ay}" r=".75" fill="#174d78"/>')
        origin=m["fixedOriginXYZmm"]
        def local(point,axis):return sum((p-o)*v for p,o,v in zip(point,origin,axis))
        hand=[(local(p,m["stageAxisXYZ"]),local(p,m["localYAxisXYZ"])) for p in m["operatorKeepoutXYZmm"]]
        side_controls.append(side_poly(hand,'fill="#f6a34b" fill-opacity=".17" stroke="#cd731b" stroke-width=".6" stroke-dasharray="1.7 1"'))
    sections.append(group("ls30-stage-and-travel",a))
    a=[];controls=side_controls
    for k,pose in state.poses.items():
        row=rows[k];kit=pose.kit
        fill="#ef9b84" if k in problems else "#f2c75c" if row["wishIds"] else "#a9c2cd"
        if row.get("adapterBoundsMm"):a.append(poly(rectangle(*row["adapterBoundsMm"]),'fill="#f6d17d" fill-opacity=".48" stroke="#b07e26" stroke-width=".48"'))
        polys=kits[kit]["layout"].get("collisionPolygonsMm",[]) if kit else []
        world=([[offset(pose.base,rot(xy(pt),pose.rotation)) for pt in ps] for ps in polys] if polys else [rectangle(*pose.box)])
        for ps in world:
            a.append('<g><title>'+escape(k+" · "+(kit or "定制包络"))+'</title>'+poly(ps,f'fill="{fill}" fill-opacity=".65" stroke="#455d67" stroke-width=".52"')+'</g>')
        for keep in row["operatorKeepout"]:
            controls.append(poly([xy(p) for p in keep["polygon"]],'fill="#f6a34b" fill-opacity=".12" stroke="#cd731b" stroke-width=".7" stroke-dasharray="2.1 1.4"'))
    sections.append(group("kit-outlines-and-operator-clearance",a+controls));sections.append(screws)
    a=[]
    for e in model["edges"]:
        route=state.paths[e["id"]]["points"]
        for beam in model["beams"][e["id"]]:
            ray=beam["start"];wave=ray["wavelength_nm"];color="#783aaa" if wave<460 else "#188540" if wave<580 else "#be3d42"
            way=route if beam["from"].split(".")[0]==e["a"] else route[::-1]
            source_node,source_port=beam["from"].split(".")
            s0=-face(model["nodes"][source_node],source_port)
            for first,last in zip(way,way[1:]):
                dx=last[0]-first[0];dy=last[1]-first[1];length=hypot(dx,dy);ux,uy=dx/length,dy/length
                front=[];back=[]
                for n in range(13):
                    along=length*n/12
                    q=complex(*ray["q_mm"])+max(0,min(s0+along,state.paths[e["id"]]["airMm"]))
                    radius=sqrt(-ray["m2"]*wave*1e-6/(pi*(1/q).imag))
                    x=first[0]+ux*along;y=first[1]+uy*along
                    front.append((x-uy*radius,y+ux*radius));back.append((x+uy*radius,y-ux*radius))
                a.append(poly(front+back[::-1],f'fill="{color}" fill-opacity=".36"'))
                a.append(line(first,last,f'stroke="{color}" stroke-width=".24"'))
                part=lambda fraction:(first[0]+dx*fraction,first[1]+dy*fraction)
                a.append(line(part(.49),part(.58),f'stroke="{color}" stroke-width=".64" marker-end="url(#arrow)"'))
                s0+=length
        shifts=sorted({round(b["start"]["freq_shift_mhz"],3) for b in model["beams"][e["id"]]})
        if any(shifts):
            a.append(label(offset(tuple((x+y)/2 for x,y in zip(route[0],route[1])),(2,2)), "/".join(f"{f:+g}" for f in shifts)+" MHz",2.7,'class="halo"'))
    for entry in ledger.get("externalInputs",[]):
        a.append(line(entry["boardEdgeMm"],entry["datumMm"],'stroke="#bf4148" stroke-width=".75" stroke-dasharray="2 1" marker-end="url(#arrow)"'))
        a.append(label(offset(entry["boardEdgeMm"],(0,4)),"IN",3.1,'class="halo" text-anchor="middle"'))
    sections.append(group("gaussian-beam-envelopes",a))
    a=[];labels=[]
    for k,p in state.poses.items():
        x,y=pos(p.point);shown=k.replace("M_steer_","S·").replace("M_fold_","F·")
        offsets=[(3,-3),(3,5),(-3-len(shown)*1.7,-2),(3,10),(-6,-7),(0,13)]
        for dx,dy in offsets:
            box=(x+dx,y+dy-3.2,x+dx+len(shown)*1.95,y+dy+.7)
            if not any(box[0]<b[2] and b[0]<box[2] and box[1]<b[3] and b[1]<box[3] for b in labels):break
        labels.append(box);a.append(circle(p.point,.9,'fill="#193e4a"'))
        a.append(text(x+dx,y+dy,shown,3.1,extra='class="halo" font-weight="600"'))
    for e in graph["links"]:
        if e["exact_mm"] is None or e["id"] not in state.paths:continue
        points=state.paths[e["id"]]["points"];u,v=points[0],points[-1];dx,dy=v[0]-u[0],v[1]-u[1]
        norm=hypot(dx,dy) or 1;d=(-dy/norm*8,dx/norm*8);u,v=offset(u,d),offset(v,d)
        a.append(line(u,v,'stroke="#535478" stroke-width=".42" stroke-dasharray="1.3 1" marker-start="url(#arrow)" marker-end="url(#arrow)"'))
        a.append(label(offset(((u[0]+v[0])/2,(u[1]+v[1])/2),(1,1.8)),f'{e["exact_mm"]:g} ±{e["tol_mm"]:g} mm',2.8,'class="halo"'))
    for s in graph["spans"]:
        k1,k2=s["start"].split(".")[0],s["end"].split(".")[0]
        if k1 in state.poses and k2 in state.poses:
            p1,p2=state.poses[k1].point,state.poses[k2].point
            delta=(10,0) if abs(p1[0]-p2[0])<.01 else (0,-10)
            a.append(line(offset(p1,delta),offset(p2,delta),'stroke="#795d82" stroke-width=".6" stroke-dasharray="3 1"'))
            a.append(label(offset(((p1[0]+p2[0])/2,(p1[1]+p2[1])/2),delta),"Σ "+number(s["exact_mm"])+" mm",3,'class="halo"'))
    for c in ledger["boardCutouts"]:
        p=c["center"];a.append(circle(p,c["diameterMm"]/2,'fill="none" stroke="#bd2e31" stroke-width="1" stroke-dasharray="4 1 .7 1"'))
        a.append(label(offset(p,(0,-17)),f'⊗ CUTOUT Ø{c["diameterMm"]:g}',3.5,'class="halo" text-anchor="middle"'))
    sections.append(group("dimensions-cutouts-and-datums",a))
    a=[text(left,10,"HKSOP   /   OPTICAL LAYOUT",3.3,"#467483", 'letter-spacing=".7"'),text(left,22,graph["name"],8,"#173e49",'font-weight="650"')]
    direct=sum(n["mode"] in ("direct","stage") for n in rows.values())
    stats=f'{w:g} × {h:g} mm   ·   M6 / {board["pitchMm"]:g} mm   ·   光高 {z:g} mm   ·   {len(rows)+len(plates)+sum(map(len,spatial.values()))+len(vertical)} 个器件及滑台   ·   折转/调节镜 {state.folds}   ·   LS30 {len(plates)+len(vertical)}   ·   主板直锁 {direct}/{len(rows)}   ·   WISH {len(ledger["wishes"])}'
    a.extend([text(left,32,stats,3.4),text(left,notes+17,"深蓝点  M6 实锁孔       橙虚线  借孔 / 25 × 30 mm 手部净空       黄色  待加工       彩色带  实际 1/e² 半径",3.15)])
    a.append(text(left,notes+23,"坐标单位 mm，原点在板左下角。图中各孔、套件编号与螺孔账本对应。",3.05,"#58727b"))
    if spatial:
        for root,items in spatial.items():
            a.append(text(left,notes+34,"板下剖面  ·  "+root+"   /   Z 相对板面",4.3))
            for j,m in enumerate(items):
                desc=f'{m["id"]}   Z {m["axisXYZmm"][2]:+.2f} mm   ·   空气段 {m["airMm"]:.2f} mm'
                if m.get("stageKitId"):desc+='   ·   侧装 '+m["stageKitId"].split("-")[-2].upper()+'，沿 Z 调焦 ±3 mm'
                a.append(text(left+5,notes+42+j*6,desc,3.5))
            for j,s in enumerate(graph["spans"]):
                if s["start"].split(".")[0] in model["downstream"]:a.append(text(left,notes+68+j*4,f'{s["start"]} → {s["end"]}   {s["exact_mm"]} ±{s["tol_mm"]} mm',3.3))
    sections.append(group("engineering-title-block",a))
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {number(pagew)} {number(pageh)}" role="img"><title>{escape(graph["name"])} · 工程俯视图</title><style>text{{font-family:"Helvetica Neue","PingFang SC",sans-serif}}.halo{{paint-order:stroke;stroke:#fff;stroke-width:1.1;stroke-linejoin:round}}</style>'+prefix+'<rect width="100%" height="100%" fill="#fff"/>'+"".join(sections)+'</svg>\n'
