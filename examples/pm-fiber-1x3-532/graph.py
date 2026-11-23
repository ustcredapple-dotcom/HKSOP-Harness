"""A visible PM delivery network. Length ranges refer to free air between surfaces."""
from optical_graph import OpticalGraph, FiberSource, FiberCoupler, PBS, DualWaveplate, HalfWaveplate

def build_graph():
    graph = OpticalGraph("PM532-1x3-R2", default_plane_height_mm=62.5)
    graph.add("IN", FiberSource(532, 1.51, pol="P", power_mw=3, connector="FC/APC"))
    graph.add("WP_IN", DualWaveplate(split_reflect_ratio=1/3))
    graph.add("PBS1", PBS(1))
    graph.add("H_STAGE2", HalfWaveplate(split_reflect_ratio=.5))
    graph.add("PBS2", PBS(1))
    def link(a,b,fold=False):
        graph.link(a,b,min_mm=15,max_mm=400,can_fold=fold)
    link("IN.front","WP_IN.a")
    link("WP_IN.b","PBS1.p1")
    link("PBS1.p3","H_STAGE2.a")
    link("H_STAGE2.b","PBS2.p1")
    for i,origin in enumerate(("PBS1.p2","PBS2.p2","PBS2.p3"),1):
        wp="WP_OUT"+str(i)
        fc="OUT"+str(i)
        graph.add(wp,DualWaveplate(target_pol="P"))
        graph.add(fc,FiberCoupler(design_diameter_mm=1.51,required_pol="P"))
        link(origin,wp+".a",i==3)
        link(wp+".b",fc+".front",True)
    return graph
