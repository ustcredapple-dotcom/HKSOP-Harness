"""Positive periodic layout and independent negative geometry checks."""
import json,tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pm_graph_fixture import build_graph
from optical_layout import run
from optical_layout.access_rules import crossings,fiber_tail
from optical_layout.folding_planner import linebox
from optical_layout.comb_planner import topology,candidates
from optical_layout.stage_policy import evaluate
from optical_layout.lowering import lower,bounds
from optical_layout.hole_snapper import snap,FitError
def check():
    model={"beams":{"a":[{"start":{"height_mm":62.5}}],"b":[{"start":{"height_mm":62.5}}]}}
    segments={"a":{"points":[(0,1),(2,1)],"ids":["A","B"]},"b":{"points":[(1,0),(1,2)],"ids":["C","D"]}}
    assert crossings(segments,model)
    model["beams"]["b"][0]["start"]["height_mm"]=100
    assert not crossings(segments,model)
    def tail(x,y):
        return fiber_tail(dict(rotationDeg=180,baseOrigin=dict(xMm=x,yMm=y)),450,300)
    assert tail(200,60)["overhangMm"]>0 and not tail(10,230)["matchingExit"]
    g=build_graph();d=g.to_dict(True);m=lower(d,evaluate(d,"fixed"));pat=topology(m)
    with tempfile.TemporaryDirectory() as td:
        q=Path(td);run(g,q,"450x300",12.5,"fixed")
        ledger=json.loads((q/"step5_hole_ledger.json").read_bytes());f=json.loads((q/"step4_folding_plan.json").read_bytes())
        nodes=ledger["nodes"];outs=[nodes["OUT"+str(i)] for i in range(1,4)];xs=[v["baseOrigin"]["xMm"] for v in outs]
        assert not ledger["beamCrossings"] and not ledger["wishes"] and all(x["fiberExit"]["direction"]=="south" and x["bodyOverhangMm"]==0 for x in outs)
        assert abs((xs[0]-xs[1])-(xs[1]-xs[2]))<.001 and all(row["operatorKeepout"] for row in nodes.values() if row["type"]!="Fold")
        state=next(s for s in candidates(m,pat,450,300,12.5) if all(abs(s.poses[k].base[0]-r["baseOrigin"]["xMm"])+abs(s.poses[k].base[1]-r["baseOrigin"]["yMm"])<.001 for k,r in nodes.items()))
        _,poly=state.poses["WP_OUT1"].keep[0];x,y,xx,yy=bounds(poly)
        state.lines.append(("isolation test","test target",linebox(((x+xx)/2,(y+yy)/2),((x+xx)/2+1,(y+yy)/2),.2)))
        try:snap(m,state,450,300,12.5)
        except FitError as e:assert "手位" in str(e)
        else:raise AssertionError("波片拨杆通道允许旁路激光穿越")
    return ["同光高交叉拦截、跨光高对照","尾套越板与向内出纤负例","25 × 30 mm 波片手位穿光负例","四双一单、同侧等距、零交叉、全头在板且原生 verify 成功"]


if __name__ == "__main__":
    for case in check():
        print("PASS", case)
