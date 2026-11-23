---
name: optics-graph-design
description: 根据实验目标建立 OpticalGraph，计算各端口的功率、偏振、频移、孔径及高斯光斑，交付可重放的原理图。
---

# 光路原理设计

阅读 [光学速查](references/optical-graph-cheatsheet.md)。把方案写成返回 OpticalGraph 的无参数函数。给可吸收的废光指定终端，使用同一条物理通道表达双通。分别核对正反向的频移与偏振。

在本技能目录使用下列入口。文件路径可使用绝对路径。

```sh
python3 scripts/optical_graph_render.py graph.py --func build_graph -o gallery.html --svg schematic.svg --json trace.json
```

## 保偏接口与验收

保偏出口从最后一个分束面起须有 QWP 与 HWP。入口先 QWP 消除残余椭偏，后 HWP 设第一分光比。PBS 透射直通纯 P 的级间可用单 HWP。反射、厚窗或声光级间优先双片。默认窄键 FC/APC；平端面约 4% 背反。反射支路目标 20 dB 需实测，30 dB 需清理或高消光比分束器。超过 1 W 核对石英波片及高损伤阈值光学元件。
