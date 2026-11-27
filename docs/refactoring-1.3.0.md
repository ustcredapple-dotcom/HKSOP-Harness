# HKSOP Harness 1.3.0 · 双语封面与仓库去重

本次保留四个插件及现有零构建 Codex 市场入口，选择方案 B。删除的是重复指令、同插件重复资料和 DSH 整树镜像；独立安装所需的运行时副本改为明确登记并逐字节校验。未修改配套 HKSOP 本体、元件 CAD 或既有项目成果。

Four isolated plugins and the existing zero-build marketplace contract remain intact. Strategy B keeps the minimum independently required runtime copies. DSH payloads are generated on demand; they are no longer tracked. HKSOP Core and its existing CAD/project assets were not modified.

## 瘦身重构前后对比 / Before and after

基线：提交 `52be20026b47e388d64d1d1b54b907761011916a`。按 Git 跟踪的普通文件计算，排除 `.git` 与未跟踪构建输出。KB 均按 1024 字节计；重复字节统计每组除一份外的副本。具体结果由 `refactoring-metrics.json` 记录。

<!-- METRICS_TABLE -->
| 范围 / Scope | 文件 | 总 KiB | 重复组 | 冗余份数 | 重复 KiB | 占比 |
|---|---:|---:|---:|---:|---:|---:|
| 改造前 / Baseline | 319 | 2522.2 | 105 | 164 | 1192.9 | 47.3% |
| 去重检查点 / Refactoring checkpoint | 198 | 1638.3 | 27 | 37 | 330.7 | 20.2% |
| 含双语展示完整交付 / Complete release | 217 | 4711.5 | 27 | 37 | 330.7 | 7.0% |
<!-- END_METRICS -->

完整交付的总字节数高于去重后的基础仓库，因为新增双语 SVG、2× PNG、字体、内联图片的独立网页与维护源。离线 HTML 和两张 SVG 必须自带资源；这类展示交付内的嵌入属于发布格式要求。它们不是插件运行时，不进入三端插件包。不能把添加高清图片后的整仓库称作“体积下降”。

The final repository includes new standalone presentation artifacts. Its total size grows despite a substantial reduction in engine/reference duplication. The report separates the refactoring checkpoint from the complete visual release; generated presentation assets do not ship inside any plugin.

## P0–P3 实施记录

- P0：删除六份 SKILL 与相关速查文档中的重复保偏段落；常驻约束保留在所属插件规则。两对同名制造文档逐行比对后，差异均为链接表达而非不同工程条款。合并到 Step 3 并恢复权威链接，保留制造、打标、定位与 QC 要求。
- P1：三个俯视渲染器、三份风格说明和两份验收复用规则分别收敛成一个插件共享文件。九个指南的保留策略改为引用单源。旧项目索引、型号基线及可选网页/总册流程移到顶层人工参考归档；当前设计依据仍随对应插件安装。
- P2：移除跟踪的 `dsh-plugins/`，仅保留 16 个宿主包装文件。安装时生成完整 Cordis 包；验证独立安装、升级、dry-run、开发软链接及本地修改保护。两个阶段必需的引擎，以及入库/三维定位器，按受控分发映射保留。
- P3：版本统一为 1.3.0；兼容目录仍锁定 `hksop-20261122-curated-r1`。保留 staged/working 双扫描、每文件 <2 MB、隐私、无软链接、隔离及 Cordis 契约，新增四类重复/漂移门禁、真实提示词装配、反例测试与 Codex 缓存保护检查。

制图规则仍为第一角法、右下角标题栏、GB/T 1804-m、Ra 3.2、内螺纹 6H；销孔/功能面等专用要求直接标注。现有测试的工程断言没有删除、放宽或跳过。

## 验收 / Verification

| 验收项目 | 结果 |
|---|---|
| 原理图基准 | 10/10 fixtures，另 52 项 API/CLI 检查，通过 |
| PM 光学 | 12 项，通过 |
| 原生排板与挑战 | layer2_acceptance.py 全部通过 |
| PM 排板与负例 | pm_layout_checks.py 全部通过 |
| 三端隔离安装与离线接力 | 通过 |
| 完整原生/CAD 接力 | 通过；STEP、光束、失败负例、BOM、两个 ZIP 的 CRC/冻结文件均核验 |
| 仓库卫生与四类新增门禁 | 通过 |
| 包装反例、内部引用、Codex 缓存保护 | 通过 |
| 双语字典、原始品牌资产、SVG/PNG 尺寸与哈希 | 通过 |
| 六份技能结构 | 六份均通过 |
| 桌面/手机功能与截图 | 发布后的浏览器验收待完成 |

原生/CAD 接力使用兼容目录的真实模型，在临时目录执行。PM-532 封面数据沿用原示例已核验记录：21 段光束、2.727 mm 净空下界、BFL 5.677 ± 0.50 mm；原资产未改动。原生接力中的另一套测试总装有其自己的实体数和净空，不冒充同一 PM-532 基准。3 mW → 3 × 1 mW 是无损模型；现场功率、插损和 PER 仍待实测。

浏览器直接打开本机 `file://` 的操作受到当前工具限制。独立页面的无外部资源、脚本语法及内容一致性已通过静态检查；不能将其表述为完成了真实离线浏览器点击验收。线上交互验收另行记录实际结果。

## 交付与维护

[中文 README](../README.md) · [English README](../README.en.md) · [交互页源码](index.html) · [展示维护](showcase-maintenance.md) · [架构与单源边界](architecture.md)。所有版本、来源、版权和“模型/实测”边界保持一致。仓库整体版权保留；Manrope 的 SIL OFL 仅适用于字体。
