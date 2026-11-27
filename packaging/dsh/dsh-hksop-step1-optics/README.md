# HKSOP Step 1 · 纯光学原理设计

本机 DeepSeek Harness 的 Cordis 插件。可在插件管理页单独开关，在任意普通工作区的对话中使用 optics-graph-design。选择技能时会一并读取本阶段规则。引用的脚本和资料位于各技能目录。阶段之间用工程文件交接。

通过安装器生成完整包后即可独立使用，仅需 Python 3。把 `graph.py` 中的 `build_graph` 指向实验方案。在 `skills/optics-graph-design/` 中运行技能说明的命令。输出 `trace.json`、`schematic.svg` 和可离线打开的 `gallery.html`；和 `graph.py` 一起交给下一步。

此目录在源码仓库中是宿主包装模板，不含技能载荷。请从仓库根目录运行 `python3 scripts/install_plugins.py --client dsh --apply`，或先运行 `python3 scripts/build_dist.py`，使用生成的 `dist/dsh-plugins/` 包。

This source directory is a host wrapper, not a standalone installation. The installer or build_dist.py assembles its isolated runtime payload under dist/dsh-plugins before use.
