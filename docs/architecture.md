# 工具链结构

实验要求先进入 OpticalGraph。光源、波片、分束器、探测器和光纤用有方向的端口连接。模拟器传播功率、琼斯偏振、频移和高斯光束，区分错误和待实测条件。带 ERROR 的追迹在进入排板前被拦截。

| 环节 | 主要输入 | 主要输出 | 验证 |
|---|---|---|---|
| 光路原理 | 实验要求、图构造器或图 JSON | graph.py、trace.json、schematic.svg | 十组基准图与保偏规则 |
| 二维排板 | 有效追迹、板型与孔距、兼容元件库 | 原生工程、六步审阅页、孔位和手位、定制件需求 | S1–S4、零延长块、光束/手位净空、原生 verify |
| 定制件支线 | custom-wishes.json 和已获授权的尺寸资料 | cad-tasks.json、几何和加工资料 | 基准、孔系、部件来源与复验 |
| 三维与交付 | 已验证的原生工程、真实模型及定位登记 | 实体总装、立体光束净空、加工包与客户包 | STEP 回读、BOM 归并、ZIP 成员和哈希 |

每个插件只捆绑自己所需的代码与规则。二维排板需要读取并复算光路，因此包含光路引擎。两个客户端系列中同一插件的技能与规则完全相同。Cordis 单独保留其 package.json、入口和启用补丁。

src/optical_graph、src/optical_layout 和 scripts/ 下的两个设计入口是维护源。普通插件是其余技能与规则的维护源。在修改这些源文件后运行以下命令。

~~~sh
python3 scripts/sync_plugins.py --apply
python3 scripts/sync_plugins.py --check
~~~

光路测试和离线接力仅需标准库。排板调用同一版 HKSOP 的原生编译器与 Node。三维检查使用有 OpenCascade 和 NumPy 的 Python，分别读模型、跟踪自由空间光束、校核活动头与板边、冻结总装与图纸。缺少原厂资产时应补齐已授权的真实模型，模型身份由哈希校验。

设计规范分别见 [光路图](specs/optical-graph-v1.0-spec.md)、[排板](specs/layer2-auto-layout-spec.md)和[插件边界](specs/hksop-4-plugins-spec.md)。
