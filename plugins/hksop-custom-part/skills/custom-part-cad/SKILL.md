---
name: custom-part-cad
description: 把 WishSpec 或厂家图纸转换为可核验的转接件设计、STEP 与加工图。
---

# 定制件设计与登记

运行解析器，阅读 [造件依据](references/design.md)。依据已知上接口决定能否加工。普通偏心平板可用随附脚本，运动组件应按原始设计流程核实真实空间运动与载荷。

在本技能目录使用下列入口。文件路径可使用绝对路径。

```sh
python3 scripts/parse_wishes.py custom-wishes.json -o cad-tasks.json
```

## 保偏接口与验收

前镜、后纤与移动螺纹分别核对。标准 SM1FCA2 窄键法兰与 MFT 直接配合时记录免定制依据；需要转接时记录公母螺纹、有效旋合长度、端面定位和全程公差。验收记录应含原厂实模及装入移动座的证据。
