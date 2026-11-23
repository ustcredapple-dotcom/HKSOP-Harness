# HKSOP 在 DeepSeek Harness 中的 Cordis 插件

在「插件 → 已安装」分别开关四个包。在任意普通工作区新建对话，输入斜杠和技能名即可调用。

- dsh-hksop-step1-optics 提供 optics-graph-design。
- dsh-hksop-step2-board 提供 board-auto-layout。
- dsh-hksop-custom-part 提供 custom-part-cad、library-intake。
- dsh-hksop-step3-manufacture 提供 json-to-3d-verify、export-packages。

每个包可独立复制到本机 ~/.dsh/local-plugins/，然后用桌面自带的 DSH 插件管理入口将该包作为本地 link: 依赖安装到 desktop 配置。包内的 cordis.patch.yml 只声明自己的一个插件行。用户的账号配置和模型路由由桌面宿主单独管理。


运行 `python3 tests/plugins_acceptance.py --offline` 可在隔离的临时用户目录核对四个包和六个技能。
