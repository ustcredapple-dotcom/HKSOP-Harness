---
name: board-auto-layout
description: 将通过体检的图装入指定板型，安排 LS30 和手部净空，校验 M6 孔并生成原生工程。
---

执行前遵守 [本插件常驻规则](../../rules/AGENTS.md)。宿主已经注入时不重复加载。

# 二维面包板布局

先读 [接口与孔位](references/board-contract.md)。从 trace.json 恢复原始约束并重算有效性，按给定板型与高度策略求解。审阅每个原生待确认项。

在本技能目录使用下列入口。文件路径可使用绝对路径。

```sh
python3 scripts/optical_graph_to_board.py trace.json --board 450x350 --pitch 12.5 --height-policy auto -o board
```
