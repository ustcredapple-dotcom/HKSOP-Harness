---
name: export-packages
description: 为已放行总装锁定加工图、铭牌、光路框线、采购版本与客户交付清单。
---

执行前遵守 [本插件常驻规则](../../rules/AGENTS.md)。宿主已经注入时不重复加载。

# 三维总装与交付

阅读 [交付文件清单](references/packages.md) 与 [行业 2D 制图规范](references/drawing-standard.md)。核对输入项目、空间回执与源资产哈希，用冻结的制造档案分别导出加工和客户包。

逐页渲染新增或修改的加工图，核验尺寸、字体、引线与裁切。

在本技能目录使用下列入口。文件路径可使用绝对路径。

```sh
python3 scripts/export_packages.py --help
```
