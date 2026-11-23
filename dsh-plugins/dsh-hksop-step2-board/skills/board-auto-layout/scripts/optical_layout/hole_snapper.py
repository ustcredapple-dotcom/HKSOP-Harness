"""M6 ownership, travel reserve, access and custom-adapter contracts in board coordinates."""
from itertools import combinations
import math

from .folding_planner import bounds, crosses, linebox, shift_box, support, union
from .lowering import V, advance, catalog, face, offset, rectangle, rot, xy

TOL=.001


class FitError(ValueError):
    pass


def near(p,q):
    return math.hypot(p[0]-q[0],p[1]-q[1])


def aspoint(p):
    return {"xMm":round(p[0],6),"yMm":round(p[1],6)}


def grid(w,h,p):
    return { (i,j):dict(id=f"R{j+1}C{i+1}",rowIndex=j,columnIndex=i,xMm=12.5+i*p,yMm=12.5+j*p)
            for i in range(math.floor((w-25)/p)+1) for j in range(math.floor((h-25)/p)+1) }


def lookup(holemap,pitch,p):
    ij=tuple(round((n-12.5)/pitch) for n in p)
    h=holemap.get(ij)
    return h if h and near(xy(h),p)<=TOL else None


def choose_counterbores(holemap,w,h,boxes,cutouts,count,polys=()):
    from .footprints import overlaps
    targets=[(0,0),(w,0),(w,h),(0,h)]
    if count==8:targets.extend([(w/2,0),(w,h/2),(0,h/2),(w/2,h)])
    holes=[v for v in holemap.values() if not any(crosses(linebox(xy(v),xy(v),5.5),b) for b in boxes)
           and not any(overlaps(rectangle(*linebox(xy(v),xy(v),5.5)),poly) for poly in polys)
           and all(near(xy(v),k["center"])>=5.5+k["diameterMm"]/2 for k in cutouts)]
    chosen=[]
    for t in targets:
        candidates=[v for v in holes if v not in chosen and abs(v["xMm"]-t[0])<w*.5 and abs(v["yMm"]-t[1])<h*.5]
        if not candidates:raise FitError("没有可接近的四周板固定沉孔")
        chosen.append(min(candidates,key=lambda v:near(xy(v),t)))
    return [dict(v,label=f"H{i+1}",throughMm=6.6,counterboreMm=11) for i,v in enumerate(chosen)]


def spatial_data(model,state):
    cuts=[];records={}
    height=model["stages"]["boardAxisHeightMm"]
    for chain in model["spatial"]:
        root=chain["root"];q=state.poses[root];comp=model["nodes"][root];p=comp["params"]
        raydir=(0.,0.,-1. if p.get("direction")=="down" else 1.)
        if comp["type"]=="SpatialFold":
            a,b=math.radians(p["pitch_deg"]),math.radians(90*q.head+p["yaw_deg"])
            raydir=(math.cos(a)*math.cos(b),math.cos(a)*math.sin(b),math.sin(a))
        pos=(*q.point,height)
        downstream=[]
        for row in chain["members"]:
            n=row["node"];e=next(e for e in model["allEdges"] if e["id"]==row["link"])
            a=model["nodes"][row["previous"]];b=model["nodes"][n]
            z=e["length"]+face(a,e["pa"] if e["a"]==row["previous"] else e["pb"])+face(b,row["entry"])
            pos=tuple(x+k*z for x,k in zip(pos,raydir))
            downstream.append(dict(id=n,kind=b["type"],axisXYZmm=[round(c,6) for c in pos],incomingLink=e["id"],airMm=e["length"],
                                   mountedTo="external vacuum assembly" if b["type"] in ("Window","TargetPlane") else root,
                                   stageAxisXYZ=raydir if model["stages"]["nodes"][n]["required"] else None))
        if raydir[2]<-1e-7:
            length=-height/raydir[2];center=offset(q.point,(raydir[0]*length,raydir[1]*length))
            # Evaluate the actual first-layer q where the chief ray intersects the plate surface.
            diameter=0.;s0=0.
            for member in chain["members"]:
                e=next(e for e in model["allEdges"] if e["id"]==member["link"])
                if s0-1e-6<=length<=s0+e["length"]+1e-6:
                    for beam in model["beams"][e["id"]]:
                        r=beam["start"];qz=complex(*r["q_mm"])+(length-s0)
                        diameter=max(diameter,2*math.sqrt(-r["m2"]*r["wavelength_nm"]*1e-6/(math.pi*(1/qz).imag)))
                s0+=e["length"]+2*face(model["nodes"][member["node"]],member["entry"])
            cuts.append(dict(node=root,center=center,diameterMm=max(25.,3*diameter),beamDiameterMm=diameter))
        records[root]=downstream
    return cuts,records


def fit_spatial_stages(records,model,w,h):
    """Mount a real LS30 on its side with travel parallel to the vertical beam."""
    stage_modules={v["id"]:v for v in catalog()[2]["stageModules"]}
    for members in records.values():
        for item in members:
            axis=item["stageAxisXYZ"]
            if not axis:continue
            if abs(axis[2])<.999999:
                raise FitError("倾斜滑台需要已知载台侧装基准")
            target=item["axisXYZmm"];candidates=[]
            # Positive local X upward puts the actual rear screw below the board.
            u=(0,0,1)
            for side in range(4):
                v=(*V[side],0);normal=(-v[1],v[0],0)
                origin=tuple(a-87.5*n for a,n in zip(target,normal))
                def world(x,y,z):
                    return [round(origin[i]+x*u[i]+y*v[i]+z*normal[i],6) for i in range(3)]
                for hand in ("l","r"):
                    kit="stage-board-lbtek-ls30-6"+hand+"1-r3"
                    layout=catalog()[0][kit]["layout"]
                    outline=[xy(p) for poly in layout["collisionPolygonsMm"] for p in poly]
                    knob=min(outline,key=lambda p:p[0])
                    handpoly=[world(x,y,22) for x,y in rectangle(knob[0]-25,knob[1]-15,knob[0],knob[1]+15)]
                    body=[world(x,y,z) for x,y in outline for z in (0,37.5)]
                    if max(p[2] for p in body+handpoly)>-12.5:continue
                    if any(not (0<=p[0]<=w and 0<=p[1]<=h) for p in body):continue
                    # The vertical glass/chamber axis occupies the clear central cylinder.
                    clearance=min(math.hypot(p[0]-target[0],p[1]-target[1]) for p in handpoly)
                    holes=[world(*xy(pt),0) for pt in stage_modules[kit]["lowerAttachmentHoles"]]
                    edge_gap=min(min(p[0],w-p[0],p[1],h-p[1]) for p in handpoly)
                    candidates.append((min(clearance,edge_gap),dict(stageKitId=kit,stageAxisXYZ=u,
                        beamDirectionXYZ=axis,localYAxisXYZ=v,stackNormalXYZ=normal,fixedOriginXYZmm=origin,
                        carrierM6XYZmm=holes,topM6XYZmm=[world(x,y,37.5) for x in (-12.5,12.5) for y in (-12.5,12.5)],
                        qMm=0.,remainingTravelMm=[3.,3.],stageStackMm=37.5,loadAxisAboveTopMm=50.,
                        operatorKeepoutXYZmm=handpoly,operatorWidthMm=30.,operatorDepthMm=25.,
                        clearanceToPlateUndersideMm=round(-12.5-max(p[2] for p in body+handpoly),4),
                        carrierStatus="待提供腔体外壳、支腿和固定接口的三维 CAD；按已知板面与光轴检验。")))
            if not candidates:raise FitError("竖直物镜侧装滑台无可用板下空间")
            item.update(max(candidates,key=lambda c:c[0])[1])


def choose_donors(q,holes,used,boxes,keepouts,cuts,w,h):
    candidates=[]
    for h1 in holes.values():
        p=xy(h1)
        if h1["id"] in used or near(q.base,p)>50+TOL:continue
        if any(near(p,k["center"])<k["diameterMm"]/2+4 for k in cuts):continue
        # Include the bolt land and the load point in the manufacturing budget.
        envelope=union([linebox(q.base,q.base,8.),linebox(p,p,4.)])
        if envelope[0]<0 or envelope[1]<0 or envelope[2]>w or envelope[3]>h:continue
        if any(crosses(envelope,b) for key,b in boxes.items() if key!=q.key):continue
        if any(crosses(envelope,b) for key,b in keepouts if key!=q.key):continue
        candidates.append((near(q.base,p),h1))
    candidates=[item[1] for item in sorted(candidates,key=lambda item:(item[0],item[1]["id"]))[:15]]
    # Prefer 4 for torsion support; never accept a one-hole cantilever.
    for count in (4,3,2):
        for take in combinations(candidates,count):
            if max(near(xy(a),xy(b)) for a,b in combinations(take,2))<12.5-TOL:continue
            if count>=3 and all(abs((b["xMm"]-take[0]["xMm"])*(c["yMm"]-take[0]["yMm"])-
                                     (b["yMm"]-take[0]["yMm"])*(c["xMm"]-take[0]["xMm"]))<.01 for b,c in combinations(take[1:],2)):continue
            envelope=union([linebox(q.base,q.base,8.)]+[linebox(xy(v),xy(v),4.) for v in take])
            if any(crosses(envelope,b) for key,b in boxes.items() if key!=q.key):continue
            if any(crosses(envelope,b) for key,b in keepouts if key!=q.key):continue
            return list(take),envelope
    raise FitError(q.key+" 附近 50 mm 内没有足够独立的借孔")


def snap(model,state,w,h,pitch,counter_count=4):
    from .access_rules import crossings,fiber_tail
    conflicts=crossings(state.paths,model)
    if conflicts:raise FitError("同光高路线相交 "+str(conflicts[0]))
    holes=grid(w,h,pitch);kits,_,cat=catalog();stages=model["stages"]["nodes"]
    boxes={k:q.box for k,q in state.poses.items()}
    keep=[(k,bounds(poly)) for k,q in state.poses.items() for _,poly in q.keep]
    cuts,spatial=spatial_data(model,state)
    fit_spatial_stages(spatial,model,w,h)
    for cut in cuts:
        p=cut["center"];rr=cut["diameterMm"]/2
        if not rr<=p[0]<=w-rr or not rr<=p[1]<=h-rr:raise FitError("cutout crosses board edge")
        if any(crosses(linebox(p,p,rr),b) for k,b in boxes.items() if k!=cut["node"]):raise FitError("cutout intersects another base")
    from .footprints import polygons
    access_polys=[p for q in state.poses.values() for _,p in q.keep]
    solids=[p for q in state.poses.values() for p in polygons(q)]
    fixed=choose_counterbores(holes,w,h,[],cuts,counter_count,solids+access_polys)
    used={v["id"] for v in fixed}
    used.update(v["id"] for v in holes.values() if any(near(xy(v),k["center"])<k["diameterMm"]/2+3 for k in cuts))
    rows={};wish=[];deferred=[]
    axis_heights={}
    if any(n["type"]=="HeightShift" for n in model["nodes"].values()):
        for link,rays in model["beams"].items():
            if link not in state.paths or not rays:continue
            for key in state.paths[link]["ids"]:
                node=model["nodes"].get(key,{})
                z=node["params"]["in_height_mm"] if node.get("type")=="HeightShift" else rays[0]["start"]["height_mm"]
                if key in axis_heights and abs(axis_heights[key]-z)>.001:raise FitError(key+" 跨光高节点缺少升降光学元件")
                axis_heights[key]=z
    sm={s["id"]:s for s in cat["stageModules"]}
    for k,q in state.poses.items():
        spec=model["nodes"].get(k,{})
        row=dict(id=k,type=q.kind,kitId=q.kit,opticalCenter=aspoint(q.point),baseOrigin=aspoint(q.base),rotationDeg=q.rotation*90,
                 headingDeg=q.head*90,hand=q.hand,collisionBoundsMm=list(q.box),screws=[],wishIds=[],
                 operatorKeepout=[dict(owner=k,control=why,depthMm=25,widthMm=30,polygon=[aspoint(p) for p in poly]) for why,poly in q.keep])
        if k in axis_heights:row["axisHeightMm"]=axis_heights[k]
        from .folding_planner import support_shape
        row["supportBoundsMm"]=list(shift_box(support_shape(q.kit,q.rotation,q.stage,q.stage_rot),q.base) if q.kit else q.box)
        row["bodyOverhangMm"]=round(max(0,-q.box[0],-q.box[1],q.box[2]-w,q.box[3]-h),4)
        if any((support(q)[0]<-TOL,support(q)[1]<-TOL,support(q)[2]>w+TOL,support(q)[3]>h+TOL)):raise FitError(k+" 实际支撑底面越过板边")
        if q.kind in ("FiberSource","FiberCoupler") and q.kit=="fiber-coupling-mft-rear-r3":
            hw=spec.get("hardware",{})
            tail=fiber_tail(row,w,h,spec["params"]["connector"],hw.get("exitSide"))
            if tail["overhangMm"]>TOL or not tail["matchingExit"]:
                raise FitError(k+" 尾套越界或出纤方向指向板内")
            if q.kind in ("FiberSource","FiberCoupler") and spec.get("hardware",{}).get("containEntireHead",True):
                if row["bodyOverhangMm"]>.001:raise FitError(k+" 调节头本体越板")
            row["fiberExit"]=tail
            row["focusConfiguration"]={"front":"independent lens on CS30-XY1D","rear":"keyed fiber flange on moving MFT","travelMm":1.0}
        rows[k]=row
        if q.stage:
            r=q.stage_rot;d=V[r];q_init=None
            # Fixed LS30 base is locked independently of the moving optical origin.
            for travel in (q.base[r%2]-round(q.base[r%2]/pitch)*pitch,):
                disp=travel*d[r%2]
                if abs(disp)<=1+TOL:
                    at=advance(q.base,r,-disp)
                    lower=[lookup(holes,pitch,offset(at,rot(xy(pt),r))) for pt in sm[q.stage]["lowerAttachmentHoles"]]
                    if all(v and v["id"] not in used for v in lower):q_init=disp
            if q_init is None:raise FitError(k+" 滑台基座无法在 ±1 mm 内直锁")
            at=advance(q.base,r,-q_init)
            row.update(mode="stage",baseOrigin=aspoint(at),screws=lower,stageKitId=q.stage,stageRotationDeg=r*90,
                       stageTopZ=37.5,qMm=round(q_init,6),remainingTravelMm=[round(3+q_init,6),round(3-q_init,6)],
                       topHoleIds=["T01","T03","T04","T06"],topLoadHeightMm=model["stages"]["boardAxisHeightMm"]-37.5)
            used.update(v["id"] for v in lower)
            if stages[k]["mount"]=="low_profile_stage_mount":deferred.append((k,"low_profile_stage_mount"))
        elif q.kit:
            local=kits[q.kit]["layout"].get("mountingHoleOffsetsMm",[])
            direct=[lookup(holes,pitch,offset(q.base,rot(xy(pt),q.rotation))) for pt in local]
            if direct and all(v and v["id"] not in used for v in direct):
                row.update(mode="direct",screws=direct);used.update(v["id"] for v in direct)
            else:deferred.append((k,"off_grid_adapter"))
        else:
            reason=("nonstandard_height" if "bareHeightMm" in spec.get("hardware",{}) or q.kind=="HeightShift" else
                    "vertical_carrier" if q.kind in ("SpatialFold","VerticalFold") else "unregistered_hardware")
            deferred.append((k,reason))
    for key,trigger in deferred:
        q=state.poses[key];row=rows[key]
        if row.get("mode")=="stage":
            donors=row["screws"];envelope=q.box
        else:
            donors,envelope=choose_donors(q,holes,used,boxes,keep,cuts,w,h)
            row.update(mode="adapter",screws=donors,adapterBoundsMm=list(envelope))
            boxes[key]=union([boxes[key],envelope]);used.update(v["id"] for v in donors)
        wid=f"WISH-{len(wish)+1:03d}"
        record=dict(wishId=wid,node=key,trigger=trigger,hardware=q.kit or model["nodes"][key]["type"],
                    opticalDatum={**aspoint(q.point),"zMm":axis_heights.get(key,model["stages"]["boardAxisHeightMm"])},
                    upperInterface=model["nodes"].get(key,{}).get("hardware",{}),
                    lowerM6=donors,envelopeBudgetMm=list(envelope),borrowRadiusMm=max(near(xy(v),q.base) for v in donors),
                    keepoutNeighbors=[dict(id=id_,boundsMm=list(b)) for id_,b in boxes.items() if id_!=key and
                                      math.hypot(max(0,b[0]-envelope[2],envelope[0]-b[2]),max(0,b[1]-envelope[3],envelope[1]-b[3]))<80],
                    status="pending CAD and physical inspection")
        if trigger=="low_profile_stage_mount":record.update(stageTopZ=37.5,targetOpticalZ=model["stages"]["boardAxisHeightMm"],
                availableHeadroomMm=model["stages"]["boardAxisHeightMm"]-37.5,preferredKits=stages[key].get("preferredKits",[]))
        if trigger=="nonstandard_height" and q.kind=="HeightShift":
            ports=model["nodes"][key]["params"]
            record["heightShift"]={"inputHeightMm":ports["in_height_mm"],"outputHeightMm":ports["out_height_mm"],
                                 "mode":ports["mode"],"inputDeg":q.head*90,
                                 "outputDeg":((q.head+q.hand)%4)*90 if ports["mode"]=="turn90" else q.head*90}
        if trigger=="nonstandard_height" and "bareHeightMm" in record["upperInterface"]:
            record["riserThicknessMm"]=record["opticalDatum"]["zMm"]-record["upperInterface"]["bareHeightMm"]
        if key in spatial:record.update(spatialAssembly=spatial[key],boardCutouts=[c for c in cuts if c["node"]==key],
            verticalStageMount="侧置 L 形承架将 LS30 局部 X 行程对准物镜光轴；承架、窗口及腔体接口待 CAD。")
        row["wishIds"].append(wid);wish.append(record)
    # Include the real fixed actuator origin after q snapping in the final access audit.
    for k,q in state.poses.items():
        row=rows[k]
        if q.stage and abs(row["qMm"])>1e-8:
            shift=advance((0,0),q.stage_rot,-row["qMm"])
            actual=shift_box(rect_rot_bounds(q.stage,q.stage_rot),xy(row["baseOrigin"]))
            boxes[k]=union([boxes[k],actual])
            for access in row["operatorKeepout"]:
                if access["control"]=="micrometer":access["polygon"]=[aspoint(offset(xy(pt),shift)) for pt in access["polygon"]]
        row["collisionBoundsMm"]=list(boxes[k])
    entries=[]
    for k,q in state.poses.items():
        if not model["nodes"].get(k,{}).get("hardware",{}).get("entrancePort"):continue
        side=(0,0,w,h)[q.head]
        boundary=list(q.point);boundary[q.head%2]=side
        radius=model["nodes"][k]["params"]["diameter_mm"]/2
        corridor=linebox(tuple(boundary),q.point,radius)
        if any(crosses(corridor,b) for key,b in boxes.items() if key!=k) or any(crosses(corridor,b) for key,b in keep if key!=k):
            raise FitError(k+" 板缘至入口对准基准的外部直射通道受阻")
        entries.append(dict(node=k,boardEdgeMm=boundary,datumMm=q.point,onBoardApproachMm=near(q.point,boundary),
                    nominalAxisHeightMm=model["stages"]["boardAxisHeightMm"],hardware="外置激光；图内仅有入射对准基准"))
    from .footprints import conflicts as physical_conflicts,overlaps,polygons
    reason=physical_conflicts(state,boxes)
    if reason:raise FitError(reason)
    for k,q in state.poses.items():
        for f in fixed:
            if any(overlaps(p,rectangle(*linebox(xy(f),xy(f),5.5))) for p in polygons(q,boxes[k])):
                raise FitError("沉孔被底座覆盖")
    for k,row in rows.items():row["collisionPolygonsMm"]=[[aspoint(y) for y in x] for x in polygons(state.poses[k],boxes[k])]
    return dict(board=dict(widthMm=w,heightMm=h,pitchMm=pitch,edgeOffsetMm=12.5,holeType="M6_through",
                           mountingHoles=fixed),nodes=rows,wishes=wish,spatialAssemblies=spatial,boardCutouts=cuts,
                externalInputs=entries,beamCrossings=conflicts,zeroEXED=True,operatorClearanceMm=25,mainBoardScrewCount=sum(len(row["screws"]) for row in rows.values()))


def rect_rot_bounds(kit,d):
    from .folding_planner import local_box,rect_rot
    return rect_rot(local_box(kit),d)




def fitted_states(model,state,w,h,pitch):
    """Translate whole parallel lines to screw-grid phase, preserving exact spacings."""
    from .folding_planner import State, clear_input, direction, manhattan, support
    from itertools import product
    keys=list(state.poses);groups=[];index={}
    for axis in (0,1):
        parent={k:k for k in keys}
        def root(k):
            while parent[k]!=k:k=parent[k]
            return k
        for e in model["edges"]:
            route=state.paths[e["id"]];ids=route["ids"]
            for i,(a,b) in enumerate(zip(ids,ids[1:])):
                p,q=route["points"][i:i+2]
                if abs(p[axis]-q[axis])<TOL or (e["exact"] and len(ids)==2):
                    parent[root(a)]=root(b)
        for span in model["spans"]:
            a,b=span["start"].split(".")[0],span["end"].split(".")[0]
            if a in parent and b in parent and all(state.paths.get(link,{}).get("bends")==0 for link in span["link_ids"]):
                parent[root(a)]=root(b)
        sets={}
        for k in keys:sets.setdefault(root(k),[]).append(k)
        for members in sets.values():
            values={0.};targets=[]
            for k in members:
                q=state.poses[k]
                if not q.kit:continue
                b=q.base[axis];targets.append(b)
                nearest=round(b/pitch)*pitch-b
                values.add(round(nearest,6))
                if abs(nearest)>TOL:values.add(round(nearest+(-pitch if nearest>0 else pitch),6))
            order=sorted(values,key=lambda d:(-sum(abs((p+d)/pitch-round((p+d)/pitch))<TOL/pitch for p in targets),abs(d)))
            if len(order)==1:continue
            for k in members:index[k,axis]=len(groups)
            groups.append(order)
    choices=[((),0)]
    for values in groups:
        choices=sorted(((prev+(v,),cost+j) for prev,cost in choices for j,v in enumerate(values)),key=lambda r:r[1])[:96]
    for moves,_ in choices:
        delta={k:tuple(moves[index[k,i]] if (k,i) in index else 0. for i in (0,1)) for k in keys}
        if not any(dx or dy for dx,dy in delta.values()):continue
        posed={k:q.moved(delta[k]) for k,q in state.poses.items()}
        if not clear_input(model,posed,w,h):continue
        paths={};lines=[];ok=True
        for e in model["edges"]:
            old=state.paths[e["id"]];ids=old["ids"];pts=[posed[k].point for k in ids]
            radius=max((max(b["start"]["diameter_mm"],b["end"]["diameter_mm"])/2 for b in model["beams"][e["id"]]),default=.25)
            air=sum(manhattan(p,q) for p,q in zip(pts,pts[1:]))-face(model["nodes"][e["a"]],e["pa"])-face(model["nodes"][e["b"]],e["pb"])
            if not e["adjustLo"]-TOL<=air<=e["adjustHi"]+TOL:ok=False;break
            for j,(a,b) in enumerate(zip(pts,pts[1:])):
                old_a,old_b=old["points"][j:j+2]
                minimum=100 if any(posed[n].stage or posed[n].kind=="AOM" for n in ids) else 75
                if manhattan(a,b)<.01 or direction(a,b)!=direction(old_a,old_b) or (0<j<len(pts)-2 and manhattan(a,b)<minimum-TOL):
                    ok=False;break
                lines.append((ids[j],ids[j+1],linebox(a,b,radius)))
            if not ok:break
            paths[e["id"]]={**old,"points":pts,"airMm":round(air,6)}
        if ok:
            yield State(posed,paths,lines,union([support(q) for q in posed.values()]),state.folds)
    yield state
