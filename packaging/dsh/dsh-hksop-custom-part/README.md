# HKSOP Custom · 非标件设计与元件库

本机 DeepSeek Harness 的 Cordis 插件。可在插件管理页单独开关，在任意普通工作区的对话中使用 custom-part-cad、library-intake。选择技能时会一并读取本阶段规则。引用的脚本和资料位于各技能目录。阶段之间用工程文件交接。

从 `skills/custom-part-cad/scripts/parse_wishes.py` 读取需求，按 `custom-part-cad` 制作并按 `library-intake` 登记。首次入库与已有版本替换分别处理。需要实体几何时使用本机配置的 CadQuery 解释器。完整原始参考资料按职责位于各技能的 `references/heritage/`。交接正式器件编号、修订、资产 SHA256 和更新后的精简清单。

此目录在源码仓库中是宿主包装模板，不含技能载荷。请从仓库根目录运行 `python3 scripts/install_plugins.py --client dsh --apply`，或先运行 `python3 scripts/build_dist.py`，使用生成的 `dist/dsh-plugins/` 包。

This source directory is a host wrapper, not a standalone installation. The installer or build_dist.py assembles its isolated runtime payload under dist/dsh-plugins before use.
