---
name: json-to-3d-verify
description: 从已验证的工程恢复总装和真实空间光束包络，检查立柱、滑台、孔壁与通光。
---

# 三维总装与交付

阅读 [空间核查](references/clearance.md)。先用原生 verify 审核当前工程，再运行光束管检查。定位、孔位、端口、三维光高及源总装层级从登记资料复建。只有证据完整的配置可以放行。

在本技能目录使用下列入口。文件路径可使用绝对路径。

```sh
python3 scripts/check_3d_beam_clearance.py project.zzoptics.json --assembly assembly.step --board-step board.step -o beam_clearance_3d.json
```

## 保偏接口与验收

总装回读逐个检出真实光纤插头和尾套，核对朝向、板缘、中央工作距、双端余量与全行程干涉。总装、加工图和打标使用同一坐标，采购清单按标准规格归并并保留数量来源。校验 CSV、JSON、压缩包及实模的 SHA256。
