# hksop-standard-optics

保留与增量交付按 [统一保留策略](../../../../../shared/library-policy.md) 执行。

先读 [本步骤的输入与交付约定](../../intake.md) 和 ../../docs/architecture.md。定位 library 的元件包或 projects 的确定修订，冻结输入哈希及库版本。

元件设计交给 hksop-component-design；本库登记交给 hksop-component-upload；加工和客户交付分别使用 hksop-manufacturing-package、hksop-customer-package。布局转三维继续使用 zzlab-optics-json-to-3d 的变换和核验要求。

使用根目录 hksop.py 生成总清单与运行目录；不要在 skill 中维护另一份支持元件表。项目的真实机械/光学验收、云端状态和本地编译状态分别说明。

AI 已验证的设计入库默认按 [验收复用与最小入库流程](../../../../../shared/acceptance-reuse.md) 直接继承结论，只检查新增、变更及其影响；不重复设计验收或事务已完成的构建。

每次更新只把本次新增/变更文件增量同步到指定 UUID 外接盘（用户称 Untitled）；未变文件不动，不重复验收，不重写或重新压缩整库。盘内同一成果仅留当前版，新副本核对成功后仅移除本次被替代旧版。按 [外接盘同步与保留规则](../zzlab-optics-library/references/storage-policy.md) 执行，复制检查不重复原设计验收。
