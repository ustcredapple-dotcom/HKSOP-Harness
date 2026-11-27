# HKSOP Step 3 · 三维总装与加工交付包

本机 DeepSeek Harness 的 Cordis 插件。可在插件管理页单独开关，在任意普通工作区的对话中使用 json-to-3d-verify、export-packages。选择技能时会一并读取本阶段规则。引用的脚本和资料位于各技能目录。阶段之间用工程文件交接。

输入冻结的 project.zzoptics.json。`json-to-3d-verify` 检查占位件、原生回执、光束管与实际几何。`export-packages` 依据冻结资产和审查凭据生成机加工包及客户包。具体输入、CAD 环境和缺少证据时的报告见各技能。

本机原生复验依次试用 `HKSOP_NODE`、库内 `config/local-environment.json` 指定的 Node、DeepSeek Harness 自带 Node 和 `PATH` 中的 Node。只有当前进程能够读取并实际启动的解释器才会传给原生工具。

此目录在源码仓库中是宿主包装模板，不含技能载荷。请从仓库根目录运行 `python3 scripts/install_plugins.py --client dsh --apply`，或先运行 `python3 scripts/build_dist.py`，使用生成的 `dist/dsh-plugins/` 包。

This source directory is a host wrapper, not a standalone installation. The installer or build_dist.py assembles its isolated runtime payload under dist/dsh-plugins before use.
