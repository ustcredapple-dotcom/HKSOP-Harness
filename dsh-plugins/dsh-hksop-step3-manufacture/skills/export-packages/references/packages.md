# 交付文件

制造包包含冻结工程、assembly.step、面包板和转接件 STEP、标注尺寸的加工图与镭雕文件、有效空间回执及 SHA256 清单。客户包包含版本锁定的 BOM、安装/装配说明和对应工程。源 Logo 与字体、定位框中的中英文及字标边距逐一实检。

- [行业 2D 制图规范](drawing-standard.md)
- [加工交付协议](heritage/hksop-manufacturing-package/GUIDE.md)
- [客户版本与采购交付](heritage/hksop-customer-package/GUIDE.md)

## 从冻结工程出包

`board_drawing.py PROJECT LEDGER LABELS -o board-drawing.svg --marking-dir MARKS` 使用排板第五步的逐孔账本。LABELS 包含这两个原文件的 `projectSha256` 与 `ledgerSha256`、面向观察者的侧面 `outwardSide`、各实例 ID 对应的双语 `labels`（`zh`、`en`）和源自实际追迹端点的 `beamCenterlinesMm`。英文字样须按已批准转接件图纸确认。加工图按第一角法输出 1 页标准底板工程图（含外形与厚度尺寸、M6 阵列标注、安装沉孔中心十字线与气泡简表、右下角标题栏、`GB/T 1804-m` / `Ra 3.2` / `6H` 与 ≤ 5 条技术要求，不附几百行规则网格全孔坐标表）；顶面和侧面的净镭雕图分别另存，底板镭雕定位图缩至 1–2 页（裸板定位总览 + 侧壁 Logo 放大定位，删除逐字坐标明细表）。

`export_packages.py release.json -o OUTPUT` 的清单包含修订号 `revision` 和 `files`。每个文件携带清单内相对 `path`、`sha256`、`role`、`audiences`。制造方使用 `manufacturing`，客户使用 `customer`。两者共用冻结工程 `project`。制造方另收 `clearance`、`assembly`、`board-step`、`drawing`、`marking`，客户另收 `bom` 与 `assembly-guide`。适用时逐件加入自制件 STEP 和配套加工图。两个最终 ZIP 均含本包文件级哈希清单和冻结版本号。

## 保偏接口与验收

总装回读逐个检出真实光纤插头和尾套，核对朝向、板缘、中央工作距、双端余量与全行程干涉。总装、加工图和打标使用同一坐标，采购清单按标准规格归并并保留数量来源。校验 CSV、JSON、压缩包及实模的 SHA256。
