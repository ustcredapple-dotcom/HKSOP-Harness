---
name: json-to-3d-verify
description: 从已验证的工程恢复总装和真实空间光束包络，检查立柱、滑台、孔壁与通光。
---

执行前遵守 [本插件常驻规则](../../rules/AGENTS.md)。宿主已经注入时不重复加载。

# 三维总装与交付

阅读 [空间核查](references/clearance.md)。先用原生 verify 审核当前工程，再运行光束管检查。定位、孔位、端口、三维光高及源总装层级从登记资料复建。只有证据完整的配置可以放行。

在本技能目录使用下列入口。文件路径可使用绝对路径。

```sh
python3 scripts/check_3d_beam_clearance.py project.zzoptics.json --assembly assembly.step --board-step board.step -o beam_clearance_3d.json
```
