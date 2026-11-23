"""Polarization decisions on directed optical paths, including branches with zero nominal power."""
from collections import deque
from . import schema as s


def check_interfaces(graph, diagnose):
    def note(level, code, node, message):
        diagnose(level, code, "node", node, message)
    for node, comp in graph.nodes.items():
        if getattr(comp, "connector", None) == "FC/PC":
            note("WARNING", "flat_fiber_backreflection", node,
                 "FC/PC 平端玻璃遇空气时约有 4% 菲涅耳背反，核对上游光隔离器和光源允许回返。")
        if isinstance(comp, s.SOURCES) and comp.power_mw > 1000:
            note("WARNING", "high_power_optics", node, "光源超过 1 W，核对石英零级波片和高损伤阈值激光线反射镜。")
    for source, launch in graph.nodes.items():
        if not isinstance(launch, s.SOURCES):
            continue
        # Track independent source-to-first-PBS and last-split-to-fibre histories.
        queue = deque([(source+".front", "", "", 0, False, False, 0)])
        seen = set()
        while queue:
            state = queue.popleft()
            if state in seen:
                continue
            seen.add(state)
            out, previous, arm, plates, disturbed, seen_pbs, input_plates = state
            link = graph._by_port.get(out)
            if not link:
                continue
            node, pin = link.other(out).split(".")
            comp = graph.nodes[node]
            group = 3 if isinstance(comp,s.DualWaveplate) else 1 if isinstance(comp,s.QuarterWaveplate) else 2 if isinstance(comp,s.HalfWaveplate) else 0
            plates |= group
            if not seen_pbs:
                input_plates |= group
            if isinstance(comp,s.FiberCoupler) and comp.mode == "SM_PM":
                if plates != 3:
                    note("WARNING" if comp.allow_uncompensated_pm else "ERROR","pm_output_compensation",node,
                         "自最后分束面至保偏纤端须有 QWP 与 HWP，补偿相位并对准共同慢轴。")
                if previous and isinstance(graph.nodes[previous],s.PBS) and arm == "R":
                    note("WARNING","pbs_reflection_per",node,"宽带 PBS 反射口消光比通常低于透射口。20 dB 目标须实测，30 dB 级需清理偏振片或高消光比 PBS。")
            if isinstance(comp,s.Four):
                if isinstance(comp,s.PBS):
                    if not seen_pbs and isinstance(launch,s.FiberSource) and launch.mode == "SM_PM" and input_plates != 3:
                        note("WARNING","pm_input_ellipticity",node,"单半波片只能旋转偏振面、无法消除输入保偏光纤的残余椭偏；推荐入口 QWP → HWP。")
                    if previous and previous != node and (arm == "R" or disturbed) and plates != 3:
                        note("WARNING","pbs_interstage_compensation",node,"反射或经相位敏感元件的级间光建议双波片补偿，极高消光比可加清理偏振片。")
                for branch,port in (("T",s.TRANSMIT[pin]),("R",s.REFLECT[pin])):
                    queue.append((node+"."+port,node,branch,0,False,seen_pbs or isinstance(comp,s.PBS),input_plates))
            elif isinstance(comp,(s.Two,s.RetroMirror)):
                relevant = isinstance(comp,(s.Spatial,s.RetroMirror,s.AOM,s.Window))
                if isinstance(comp,s.CustomTwoPort):
                    relevant = (comp.params or {}).get("birefringent",False) or any(v in comp.device_type.lower() for v in ("mirror","crystal","window","双折射","转向"))
                exit_port = pin if isinstance(comp,s.RetroMirror) else ("b" if pin == "a" else "a")
                queue.append((node+"."+exit_port,previous,arm,plates,disturbed or relevant,seen_pbs,input_plates))
