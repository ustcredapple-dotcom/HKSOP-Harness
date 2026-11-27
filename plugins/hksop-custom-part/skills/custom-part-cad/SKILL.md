---
name: custom-part-cad
description: 把 WishSpec 或厂家图纸转换为可核验的转接件设计、STEP 与加工图。
---

执行前遵守 [本插件常驻规则](../../rules/AGENTS.md)。宿主已经注入时不重复加载。

# 定制件设计与登记

运行解析器，阅读 [造件依据](references/design.md) 与 [行业 2D 制图规范](references/drawing-standard.md)。依据已知上接口决定能否加工。普通偏心平板可用随附脚本，运动组件应按原始设计流程核实真实空间运动与载荷。

逐页渲染新增或修改的加工图，核验尺寸、字体、引线与裁切。

在本技能目录使用下列入口。文件路径可使用绝对路径。

```sh
python3 scripts/parse_wishes.py custom-wishes.json -o cad-tasks.json
```
