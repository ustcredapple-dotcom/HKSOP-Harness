# hksop-customer-package

保留与增量交付按 [统一保留策略](../../../../../shared/library-policy.md) 执行。

先读 [本步骤的输入与交付约定](../../packages.md)，以项目当前明确选定的修订为准，保持原始 .zzoptics.json 与 library-lock.json 配套。

收齐实际可用的总装 STEP、项目 JSON、俯视/三维光路展示、BOM/采购清单、装配说明及必要元件依赖。光学假设、名义值、未验收制造项及云端同步状态在说明中保留；不把旧修订的 STEP 配给新布局并称为已同步。

客户包与加工包用途分别说明，引用加工包的确定修订。所有交付文件进入 manifest.json 并记录 SHA256；项目打开检查与总装来源检查写入 acceptance.json。

输出放 projects/<project>/results/customer/<revision>；打包并校验实际内容。发送、共享或云端发布只有用户要求时才执行。
