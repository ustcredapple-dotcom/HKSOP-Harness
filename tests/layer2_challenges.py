"""Four independent laboratory briefs. Builders express optical constraints only."""
from optical_graph import (
    AOM, BeamDump, Camera, CustomTwoPort, Dichroic, DualWaveplate, FiberCoupler, FiberSource,
    HalfWaveplate, Isolator, LaserSource, Lens, OpticalGraph, PBS, Photodiode, QuarterWaveplate,
    RetroMirror, SamplerPlate, TargetPlane, VerticalFold, Window,
)


def challenge_1():
    g = OpticalGraph("compact-expander")
    g.add("Input", LaserSource(780, .7, pol="elliptical", height_mm=62.5, power_mw=30))
    g.add("Pol", DualWaveplate(.5, hwp_deg=60.03161012, note="椭偏输入经 QWP 线化；HWP 比纯 P 标定点转约 39.23°，使 PBS 透射 4%"))
    g.add("ISO", Isolator(780,output_pol="S"))
    g.add("PBS", PBS(.5))
    g.add("Monitor", BeamDump(monitor_pd=True))
    g.add("Lshort", Lens(25,kind="achromat"))
    g.add("Llong", Lens(75,kind="achromat"))
    g.add("PM", FiberCoupler(allow_uncompensated_pm=True, design_diameter_mm=2.1,required_pol="S"))
    g.link("Input.front","Lshort.a",min_mm=24,max_mm=75)
    g.link("Pol.b","PBS.p1",min_mm=28,max_mm=110)
    g.link("PBS.p3","Monitor.front",min_mm=40,max_mm=200,can_fold=True)
    g.link("PBS.p2","ISO.a",min_mm=42,max_mm=380,can_fold=True)
    g.link("Llong.b","Pol.a",min_mm=25,max_mm=100)
    g.link("Lshort.b","Llong.a",exact_mm=100,tol_mm=.5)
    g.link("ISO.b","PM.front",min_mm=145,max_mm=640,can_fold=True)
    return g


def challenge_2():
    g=OpticalGraph("double-pass-focus-camera")
    g.add("Input",FiberSource(780,1.2,power_mw=40))
    g.add("PBS",PBS(.5))
    g.add("AO",AOM(100,order=1,active_aperture_mm=3))
    g.add("Cat",Lens(100))
    g.add("Q",QuarterWaveplate(.5,fast_axis_deg=45))
    g.add("End",RetroMirror())
    g.add("Tap",SamplerPlate(reflect_ratio=.02))
    g.add("Image",Lens(100,kind="achromat"))
    g.add("Camera",Camera("far-field spot"))
    g.add("PM",FiberCoupler(allow_uncompensated_pm=True, design_diameter_mm=1.2,required_pol="S"))
    g.link("Input.front","PBS.p1",min_mm=40,max_mm=380,can_fold=True)
    g.link("PBS.p3","AO.a",min_mm=40,max_mm=180)
    g.link("AO.b","Cat.a",exact_mm=100,tol_mm=1.5)
    g.link("Cat.b","Q.a",min_mm=42,max_mm=58)
    g.link("Q.b","End.front",min_mm=42,max_mm=58)
    g.span("Cat.b","End.front",exact_mm=100,tol_mm=.35)
    g.link("PBS.p4","Tap.p1",min_mm=50,max_mm=400,can_fold=True)
    g.link("Tap.p2","Image.a",min_mm=50,max_mm=360,can_fold=True)
    g.link("Image.b","Camera.front",exact_mm=100,tol_mm=.4)
    g.link("Tap.p3","PM.front",min_mm=145,max_mm=680,can_fold=True)
    return g


def challenge_3():
    # A rigid laser riser uses the measured bare height. Both launch ports are at 100 mm.
    g=OpticalGraph("dual-colour-vertical-atoms",default_plane_height_mm=100)
    g.add("Violet",FiberSource(399,2,height_mm=100,power_mw=15))
    g.add("Green",LaserSource(532,2,height_mm=100,power_mw=10))
    g.add("Comb",Dichroic(pass_wavelengths_nm=[399],reflect_wavelengths_nm=[532]))
    g.add("Tap",SamplerPlate(reflect_ratio=.01))
    g.add("Camera",Camera("collimated two-colour overlap"))
    g.add("Q",QuarterWaveplate(.5,target_pol="LHC",note="Achromatic retarder at both wavelengths"))
    g.add("Down",VerticalFold("down"))
    g.add("Obj",Lens(100,kind="achromat"))
    g.add("Win",Window(6,material="UVFS",clear_aperture_mm=25))
    g.add("Atoms",TargetPlane("common atomic waist"))
    g.link("Violet.front","Comb.p1",min_mm=35,max_mm=280,can_fold=True)
    g.link("Green.front","Comb.p4",min_mm=50,max_mm=300,can_fold=True)
    g.link("Comb.p3","Tap.p1",min_mm=45,max_mm=250,can_fold=True)
    g.link("Tap.p2","Camera.front",min_mm=45,max_mm=230,can_fold=True)
    g.link("Tap.p3","Q.a",min_mm=42,max_mm=300,can_fold=True)
    g.link("Q.b","Down.a",min_mm=40,max_mm=160)
    g.link("Down.b","Obj.a",min_mm=140,max_mm=150)
    g.link("Obj.b","Win.a",min_mm=45,max_mm=51)
    g.link("Win.b","Atoms.front",exact_mm=48,tol_mm=.2)
    g.span("Obj.b","Atoms.front",exact_mm=101.93,tol_mm=.15)
    return g


def challenge_4():
    g=OpticalGraph("rb87-lock-and-two-pm-outputs")
    g.add("Input",LaserSource(780,1.4,height_mm=62.5,power_mw=60))
    g.add("ISO",Isolator(780))
    g.add("TapH",HalfWaveplate(.5,split_reflect_ratio=.15))
    g.add("Tap",PBS(.5))
    g.add("Ratio",HalfWaveplate(.5,split_reflect_ratio=.5))
    g.add("Dist",PBS(.5))
    g.add("PM_A",FiberCoupler(allow_uncompensated_pm=True, design_diameter_mm=1.4,required_pol="P"))
    g.add("PM_B",FiberCoupler(allow_uncompensated_pm=True, design_diameter_mm=1.4,required_pol="S"))
    g.add("LockH",HalfWaveplate(.5,split_reflect_ratio=.5))
    g.add("P1",PBS(.5))
    g.add("Cell",CustomTwoPort("rb87_vapor_cell",75,16,custom_reason="75 mm cell, counterpropagating pump and probe"))
    g.add("P2",PBS(.5))
    g.add("PD",Photodiode("unshifted probe"))
    g.add("AO",AOM(80,active_aperture_mm=3))
    g.add("Dump",BeamDump())
    g.link("Input.front","ISO.a",min_mm=50,max_mm=240,can_fold=True)
    g.link("ISO.b","TapH.a",min_mm=60,max_mm=350,can_fold=True)
    g.link("TapH.b","Tap.p1",min_mm=35,max_mm=135)
    g.link("Tap.p3","Ratio.a",min_mm=45,max_mm=400,can_fold=True)
    g.link("Ratio.b","Dist.p1",min_mm=35,max_mm=135)
    g.link("Dist.p3","PM_A.front",min_mm=145,max_mm=650,can_fold=True)
    g.link("Dist.p2","PM_B.front",min_mm=145,max_mm=650,can_fold=True)
    g.link("Tap.p2","LockH.a",min_mm=45,max_mm=380,can_fold=True)
    g.link("LockH.b","P1.p1",min_mm=35,max_mm=135)
    g.link("P1.p3","Cell.a",min_mm=25,max_mm=100)
    g.link("Cell.b","P2.p1",min_mm=25,max_mm=100)
    g.link("P2.p3","PD.front",min_mm=35,max_mm=270,can_fold=True)
    g.link("P1.p2","AO.a",min_mm=45,max_mm=320,can_fold=True)
    g.link("AO.b","P2.p2",min_mm=75,max_mm=720,can_fold=True)
    g.link("P1.p4","Dump.front",min_mm=35,max_mm=260,can_fold=True)
    return g


BRIEFS = [
    ("350x250",25,"fixed","固定 62.5 mm 的 780 nm、30 mW 椭偏入射。入板即以 +25/+75 mm 消色差开普勒镜组扩束，间距 100 mm，名义腰径由 0.7 变为 2.1 mm。双波片将可标定椭偏调至离 S 轴 11.54° 的线偏振；PBS 将 4% 的 P 光（1.2 mW）透射到监测光阱，96% 的 S 光自然转向，其后隔离器阻断主路回光。28.8 mW 经两面可调镜注入 S 轴。该监测比例需在稳定偏振工作点标定。外部激光从板缘直入，入口小座只提供可复现的对准基准。",{"Input":{"entrancePort":True,"hardware":"可拆式入板对准基准","envelopeMm":[24,24]}}),
    ("450x350",12.5,"auto","40 mW、780 nm 的 P 光穿过 PBS 及 +1 级 100 MHz AOM。AOM 至 f100 猫眼透镜、透镜至端镜各 100 mm。45° QWP 双通把回光变为 S，从 PBS 第四口引出 +200 MHz。2% 抽样经 100 mm 长焦镜在相机上形成傅里叶面，0.8 mW 用于光斑诊断，39.2 mW 对准 PM 光纤 S 轴。相机和猫眼分别保留轴向调焦。",{}),
    ("auto",12.5,"auto","399/532 nm 均用 2.0 mm 的 P 光。532 nm 激光裸机光高 88.3 mm，用 11.7 mm 刚性增高底座匹配 100 mm 公共光轴。双色镜合束，1% 给准直监视相机（0.25 mW），余下 24.75 mW 经双波长消色差 QWP 后向下。f100 消色差物镜到原子 101.93 mm，补偿 6 mm UVFS 的焦移。窗下表面至原子固定 48 mm。物镜沿竖直光轴调焦，靶面与真空窗保持固定。两色剩余色差及焦移见逐色 q 读数，双波长波片与物镜需实物标定。",{"Green":{"bareHeightMm":88.3,"hardware":"external laser and rigid riser","envelopeMm":[75,50]}}),
    ("500x350",25,"fixed","780 nm、60 mW、62.5 mm 固定输入。隔离后 HWP/PBS 向锁频支路反射 15%（9 mW）。再等分为未移频探测和 +80 MHz 泵浦各 4.5 mW，共用 75 mm 铷泡对射，分别进入 PD 和光阱。剩余 51 mW 经可转 HWP/PBS 连续分配，验收工作点为 25.5/25.5 mW，两根保偏光纤分别对 P、S 主轴，各用两面调节镜。外部激光从板缘直入。",{"Input":{"entrancePort":True,"hardware":"可拆式入板对准基准","envelopeMm":[24,24]}}),
]
ALL_FIXTURES=[challenge_1,challenge_2,challenge_3,challenge_4]
