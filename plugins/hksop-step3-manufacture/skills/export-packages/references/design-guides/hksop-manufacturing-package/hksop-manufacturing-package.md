# hksop-manufacturing-package

保留与增量交付按 [统一保留策略](../../../../../shared/library-policy.md) 执行。

先读 [本步骤的输入与交付约定](../../packages.md)，读取项目当前版本信息与实际验收记录，遵循 [加工包规范](../../machinist-package.md)。

冻结输入工程、元件修订、每个加工文件和 BOM 的 SHA256。按加工零件列数量、材料、表面处理、螺纹与装配要求；外购件另列采购清单。每个可加工件提供对应 STEP 和可读工程图；DXF 只作为补充，不替代三视图。激光刻字包含字体/位置、实际刻字文本、DXF 和定位图及对应哈希。

2D 图纸按 [行业制图规范](../../drawing-standard.md) 出图并逐页视觉验收。

倒 C 角按 统一规则 核对：实际 STEP、加工图和修订对应，标明 C 值/角度、适用边组及功能例外；复用已有倒角验收，只补新增或受影响项。不能用“去毛刺”文字替代已确认但尚未建模的倒角。

使用引擎 exports 的原验收约束；专业预览警告不能被删除后作为放行依据。缺图、缺尺寸、未核查的孔或未确认版本写入 blocking-items.json。未解除制造阻塞时交付 review 状态，不冠以 ready。

输出放 projects/<project>/results/manufacturing，附 manifest.json、验收记录和 README.md。验证压缩包可解压、清单内所有文件哈希一致、数量与已冻结工程一致，再追加日志。
