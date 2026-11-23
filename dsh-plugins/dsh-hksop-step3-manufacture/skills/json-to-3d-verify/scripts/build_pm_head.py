"""Fit the manufacturer's independent asphere and bare keyed receptacle to the two real SM1 stages."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID,TopAbs_FACE
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.TopoDS import TopoDS
from solid_scene import source,bbox,rigid,doc,XCAFDoc_DocumentTool,TDataStd_Name,TCollection_ExtendedString,TopLoc_Location,STEPCAFControl_Writer,STEPControl_AsIs,IFSelect_RetDone

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def placed(shape,R,D):return shape.Moved(rigid(np.column_stack([R,D]).tolist()))
def parts(f):
    leaves=source(f,digest(f))[2]
    ex=TopExp_Explorer(leaves[0][1],TopAbs_SOLID);out=[]
    while ex.More():out.append(ex.Current());ex.Next()
    return out
def named_step(seq,path):
    d=doc();t=XCAFDoc_DocumentTool.ShapeTool_s(d.Main());top=t.NewShape()
    TDataStd_Name.Set_s(top,TCollection_ExtendedString("FC-APC independent focus head"))
    for label,s in seq:
        child=t.AddShape(s,False);TDataStd_Name.Set_s(child,TCollection_ExtendedString(label))
        ins=t.AddComponent(top,child,TopLoc_Location());TDataStd_Name.Set_s(ins,TCollection_ExtendedString(label))
    t.UpdateAssemblies();writer=STEPCAFControl_Writer();writer.SetNameMode(True)
    if not writer.Transfer(d,STEPControl_AsIs) or writer.Write(str(path))!=IFSelect_RetDone:raise ValueError("head export failed")
def build(root,vendor,out):
    out.mkdir(exist_ok=True,parents=True)
    kit=next(k for k in json.loads((root/"library/catalog.json").read_bytes())["kits"] if k["id"]=="fiber-coupling-mft-rear-r3")
    ref=kit["assemblyReference"];stock=source(root/"library/assets"/ref["stepPath"],ref["sourceStepSha256"])[2]
    codes=("A240TM-A","S1TM12","SM1FCA2","P3-488PM-FC-2");models={k:parts(vendor/(k+".step")) for k in codes}
    if [len(models[k]) for k in codes]!=[2,2,1,21] or len(stock)<65:raise ValueError("unrecognized supplier revision")
    # Molded D-LaK6, paraxial prescription of manufacturer 15817-S03, no laser window.
    # Index interpolated between the measured molded e and F lines (vendor catalog).
    index=1.6929+(546.7-532)/(546.7-486.1)*(1.699-1.6929)
    p1=(index-1)*.18252041050236778;p2=(1-index)*(-.0015804459639203151);ct=3.69
    f=1/(p1+p2-ct*p1*p2/index);bfl=f*(1-ct*p1/index)
    tilt=math.radians(4.05);c,s=math.cos(tilt),math.sin(tilt)
    F=np.array([[-1,0,0],[0,0,1],[0,1,0.]])
    tilted=np.array([0,s,c]);P=F@np.column_stack(([-1,0,0],np.cross(tilted,[-1,0,0]),tilted))
    # Sleeve datum: the keyed plug's cylindrical nose seats at the inner annular
    # shoulder (the mouth and the fiber tip are distinct manufacturer's faces).
    bore=np.array([15.411017698,.175693918,-4.118943755])
    seat_plane=np.array([15.411017698,2.97,-7.63])
    # Recover the exact plane rather than relying on rounded drawing dimensions.
    flange=models[codes[2]][0];ex=TopExp_Explorer(flange,TopAbs_FACE)
    while ex.More():
        ad=BRepAdaptor_Surface((getattr(TopoDS,"Face_s",None) or TopoDS.Face)(ex.Current()))
        if ad.GetType()==GeomAbs_Plane:
            p=np.array(ad.Plane().Location().Coord());n=np.array(ad.Plane().Axis().Direction().Coord())
            if abs(p[2]+7.63)<.025 and abs(n@tilted)>.9999:seat_plane=p;break
        ex.Next()
    seat=bore+tilted*((seat_plane-bore)@tilted)
    plug=models[codes[3]]
    paxis=np.array([-.8980344407774447,24.579329556625364,0])
    nose=paxis.copy();nose[2]=bbox(plug[2])[2]+1.e-7
    ex=TopExp_Explorer(plug[3],TopAbs_FACE)
    while ex.More():
        ad=BRepAdaptor_Surface((getattr(TopoDS,"Face_s",None) or TopoDS.Face)(ex.Current()))
        if ad.GetType()==GeomAbs_Plane and .98<abs(ad.Plane().Axis().Direction().Z())<.999:break
        ex.Next()
    if not ex.More():raise ValueError("missing 8-degree optical facet")
    fn=np.array(ad.Plane().Axis().Direction().Coord());fp=np.array(ad.Plane().Location().Coord())
    tip=paxis.copy();tip[2]=(fp-paxis)@fn/fn[2]
    # The moving SM1 external thread starts inside the front of the moving MFT carriage.
    mid=np.array([15.411017698,-.3122538024,-12.474503851])
    fd=np.array([0,23.65,62.5])-F@mid
    plugD=F@seat+fd-P@nose
    # Mated connector: locate the first solid contact of the keyed housing and
    # sprung ceramic independently. The supplier STEP depicts the loose cap.
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    fixed_flange=placed(flange,F,fd);direction=P[:,2]
    def volume(a,b):
        inter=BRepAlgoAPI_Common(a,b).Shape();v=GProp_GProps()
        BRepGProp.VolumeProperties_s(inter,v);return v.Mass()
    def first_contact(i):
        lo,hi=0.,2.
        if volume(fixed_flange,placed(plug[i],P,plugD+hi*direction))>.000001:raise ValueError("unseated connector "+str(i))
        for _ in range(13):
            t=(lo+hi)/2
            if volume(fixed_flange,placed(plug[i],P,plugD+t*direction))>.000001:lo=t
            else:hi=t
        return hi+.001
    housing_stop=first_contact(2);ferrule_stop=first_contact(3)
    axial={i:housing_stop for i in range(1,11)}
    axial[3]=ferrule_stop;axial[4]=ferrule_stop;axial[5]=ferrule_stop
    # Floating coupling nut overlaps three turns of the M8 x 0.75 threaded port.
    # The vendor STEP represents the nut's internal thread by its minor cylinder.
    axial[6]=-3.5
    apex=P@tip+plugD+direction*ferrule_stop
    # Position XY carriage using its actual adjustment, removing the small transverse
    # offset between the tilted bore and the concentric outer SM1 datum.
    rear=apex[1]-bfl
    lens=models[codes[0]];front_x,rear_x=bbox(lens[1])[0]+1.e-7,bbox(lens[1])[3]-1.e-7
    L=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
    ld=np.array([apex[0],rear-rear_x,apex[2]])
    A=np.array([[1,0,0],[0,0,-1],[0,1,0.]])
    ad=np.array([apex[0],ld[1]+2.2-2.0315,apex[2]])
    seq=[]
    for i,(name,shape) in enumerate(stock):
        if i in (7,41,60):continue
        if i==13:
            shape=placed(shape,np.eye(3),[apex[0],0,apex[2]-62.5])
        seq.append(("stock-%02d "%i+name,shape))
    for k,R,D,labels in ((codes[0],L,ld,("front lens housing","front lens glass")),(codes[1],A,ad,("front SM1 carrier","front retaining spring")),(codes[2],F,fd,("moving FC APC flange",))):
        for name,shape in zip(labels,models[k]):seq.append((name,placed(shape,R,D)))
    for i in range(1,11):
        label={2:"moving keyed plug",3:"moving APC ferrule",10:"moving rigid boot"}.get(i,"moving plug part %02d"%i)
        seq.append((label,placed(plug[i],P,plugD+direction*axial[i])))
    dst=out/"pm532-head.step";named_step(seq,dst)
    outparts=source(dst,digest(dst))[2];names=[n for n,_ in outparts]
    glass=dict(outparts)["front lens glass"];bb=bbox(glass)
    # Exact axial vertices via OCC bounds. The transverse aperture is centered on the optical axes.
    meta=dict(format="hksop-pm-head-v2",sha256=digest(dst),stockSha256=ref["sourceStepSha256"],files={k:digest(vendor/(k+".step")) for k in codes},
        step=dst.name,sourceToKit3x4=np.column_stack((np.eye(3),[0,0,0])).tolist(),datumEvidence="Manufacturer STEP mated faces, 1.035-40 moving thread, real 4.05 degree keyway; head-registration.json",
        transmissiveOpticalLeaves=[dict(index=names.index("front lens glass"),name="front lens glass",centerSourceMm=[apex[0],(bb[1]+bb[4])/2,apex[2]],normalSourceXYZ=[0,1,0],clearRadiusMm=4,halfThicknessMm=(bb[4]-bb[1])/2)],focus=dict(lensRearYmm=rear,lensFrontYmm=ld[1]+front_x,tipXYZmm=apex.tolist(),keyAxis=P[:,0].tolist(),fiberAxis=P[:,2].tolist(),facetNormal=(P@fn).tolist(),eflMm=f,bflMm=bfl,moldedIndex532=index,strokeMm=1.,nominalFocusMm=0.,source="Thorlabs 15817-S03.zmx surfaces 2/3, modeled in air without its optional laser window. LBTEK MFT 1.0 mm full stroke; centre the stage before setup.",removedStockIndices=[7,41,60],rearBounds=bbox(dict(outparts)["moving rigid boot"]),housingStopCorrectionMm=housing_stop,ceramicSpringCompressionMm=ferrule_stop-housing_stop,nutDatumAdjustmentMm=axial[6],fixedLensThreadOverlapMm=2.41,flangeThreadEngagementMm=2.54))
    (out/"head-registration.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    return meta
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("root",type=Path);p.add_argument("vendor",type=Path);p.add_argument("output",type=Path)
    a=p.parse_args();m=build(a.root,a.vendor,a.output);print(json.dumps(m["focus"],ensure_ascii=False))
