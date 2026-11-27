---
name: library-intake
description: 校验包结构、真实模型、资源哈希、主推 Tier 与历史选择，在受控工作副本登记部件。
---

执行前遵守 [本插件常驻规则](../../rules/AGENTS.md)。宿主已经注入时不重复加载。

# 定制件设计与登记

阅读 [入库与回滚](references/intake.md)，确认正式目标工作副本及替换旧版的历史策略。校验资产后事务化登记并运行 catalog build，核对精简清单和对应组件身份。

在本技能目录使用下列入口。文件路径可使用绝对路径。

```sh
python3 scripts/intake.py --help
```
