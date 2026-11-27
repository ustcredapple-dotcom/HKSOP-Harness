# hksop-component-upload

保留与增量交付按 [统一保留策略](../../../../../shared/library-policy.md) 执行。

先读 [本步骤的输入与交付约定](../../intake.md) 与 ../../docs/component-intake.md。按 package.json 归集零件、套件、板型及资源，不手工同时修改多个总表。

在库外准备候选，AI 已经验证过的设计直接复用验收。按 [验收复用与最小入库流程](../../../../../shared/acceptance-reuse.md) 只补新增、变更及受影响的未覆盖检查。执行 package check、package stage；读取事务报告后执行 package adopt。事务已完成的校验和 catalog/runtime 构建直接复用，仅缺少产物或相关输入改变时补一次必要构建。用户已授权入库时直接完成，无需重复确认。

不同配置共享完全相同的数据；稳定 ID 不因显示名改变而变化。新文件记录 SHA256，变更内容使用新文件名。列出未通过的能力，不将示意图当作真实接口或制造证据。

导入原有资料、真实俯视图和厂家数据时参考 ../zzlab-optics-library/SKILL.md；其中外部发布步骤仅在对应目标获用户要求时使用。验收并记录元件数量、ID、资源、BOM、摆放和光学基准。

每次更新只把本次新增/变更文件增量同步到指定 UUID 外接盘（用户称 Untitled）；未变文件不动，不重复验收，不重写或重新压缩整库。盘内同一成果仅留当前版，新副本核对成功后仅移除本次被替代旧版。按 [外接盘同步与保留规则](../zzlab-optics-library/references/storage-policy.md) 执行，复制检查不重复原设计验收。
