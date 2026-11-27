---
name: optics-graph-design
description: 根据实验目标建立 OpticalGraph，计算各端口的功率、偏振、频移、孔径及高斯光斑，交付可重放的原理图。
---

执行前遵守 [本插件常驻规则](../../rules/AGENTS.md)。宿主已经注入时不重复加载。

# 光路原理设计

阅读 [光学速查](references/optical-graph-cheatsheet.md)。把方案写成返回 OpticalGraph 的无参数函数。给可吸收的废光指定终端，使用同一条物理通道表达双通。分别核对正反向的频移与偏振。

在本技能目录使用下列入口。文件路径可使用绝对路径。

```sh
python3 scripts/optical_graph_render.py graph.py --func build_graph -o gallery.html --svg schematic.svg --json trace.json
```
