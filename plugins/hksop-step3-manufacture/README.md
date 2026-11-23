# 三维总装与交付

输入冻结的 project.zzoptics.json。`json-to-3d-verify` 检查占位件、原生回执、光束管与实际几何。`export-packages` 依据冻结资产和审查凭据生成机加工包及客户包。具体输入、CAD 环境和缺少证据时的报告见各技能。

本机原生复验依次试用 `HKSOP_NODE`、库内 `config/local-environment.json` 指定的 Node、DeepSeek Harness 自带 Node 和 `PATH` 中的 Node。只有当前进程能够读取并实际启动的解释器才会传给原生工具。
