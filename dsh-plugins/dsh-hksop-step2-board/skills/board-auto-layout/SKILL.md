---
name: board-auto-layout
description: 将通过体检的图装入指定板型，安排 LS30 和手部净空，校验 M6 孔并生成原生工程。
---

# 二维面包板布局

先读 [接口与孔位](references/board-contract.md)。从 trace.json 恢复原始约束并重算有效性，按给定板型与高度策略求解。审阅每个原生待确认项。

在本技能目录使用下列入口。文件路径可使用绝对路径。

```sh
python3 scripts/optical_graph_to_board.py trace.json --board 450x350 --pitch 12.5 --height-policy auto -o board
```

## 保偏接口与验收

级联同类输出优先直线主干与等距同侧梳齿，优先 12.5 mm 孔距。复核同光高交叉、操作通道与实际投影，登记每个波片、PBS、双镜、XY、MFT、插拔和顺出边界。1 inch 双片选 WPC2-R2-C03。前镜独立固定，带键裸纤法兰装在 MFT 移动环；定焦头须选无 MFT 的紧凑座，缺件输出 WISH。
