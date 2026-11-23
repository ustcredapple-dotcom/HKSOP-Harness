"""Acceptance checks for directed PM polarization and connector decisions."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from optical_graph import FiberSource,FiberCoupler,OpticalGraph,HalfWaveplate,DualWaveplate,PBS,Photodiode
from pm_graph_fixture import build_graph

def checks(test):
    g=build_graph();data=g.to_dict(True);t=data["trace"]
    def diagnostics(g):
        return {(r["code"],r["level"]) for r in g.to_dict(True)["trace"]["diagnostics"]}
    test.require("equal PM trident",t["valid"] and all(abs(t["terminals"]["OUT"+str(i)]["beams"][0]["power_mw"]-1)<1.e-8 for i in (1,2,3)))
    test.require("PBS T direct single and reflected outputs",diagnostics(g)=={("pbs_reflection_per","WARNING")})
    for override in (True,False):
        simple=OpticalGraph("uncompensated")
        simple.add("A",FiberSource(532,1.5,connector="FC/PC",power_mw=1100))
        simple.add("B",FiberCoupler(design_diameter_mm=1.5,allow_uncompensated_pm=override))
        simple.link("A.front","B.front",exact_mm=40)
        ds=diagnostics(simple)
        for code,level in [("pm_output_compensation","WARNING" if override else "ERROR"),("flat_fiber_backreflection","WARNING"),("high_power_optics","WARNING")]:
            test.require(code+" "+str(override),(code,level) in ds)
    g.nodes["WP_IN"]=HalfWaveplate(split_reflect_ratio=1/3)
    test.require("entry single HWP ellipticity",("pm_input_ellipticity","WARNING") in diagnostics(g))
    def stokes(order,reverse):
        q=OpticalGraph("non-commuting plates");q.add("A",FiberSource(532,1.5))
        q.add("W",DualWaveplate(order=order,qwp_fast_axis_deg=31,hwp_fast_axis_deg=14))
        q.add("D",Photodiode());a,b=("b","a") if reverse else ("a","b")
        q.link("A.front","W."+a,exact_mm=50);q.link("W."+b,"D.front",exact_mm=50)
        return q.to_dict(True)["trace"]["terminals"]["D"]["beams"][0]["stokes"]
    a=stokes("QWP_HWP",False);b=stokes("HWP_QWP",False)
    test.require("order changes Jones evolution",max(abs(i-j) for i,j in zip(a,b))>.2)
    for order,result in (("QWP_HWP",b),("HWP_QWP",a)):
        test.require("reverse propagation "+order,max(abs(i-j) for i,j in zip(stokes(order,True),result))<1.e-7)


if __name__ == "__main__":
    from optical_graph_acceptance import Checks
    results = Checks()
    checks(results)
    for row in results.items:
        if not row["passed"]:
            raise SystemExit("FAIL " + row["check"])
    print(f"PASS {len(results.items)} PM optical checks")
