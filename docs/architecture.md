# 工具链结构 / Toolchain architecture

实验要求先进入 OpticalGraph。模拟器传播功率、琼斯偏振、频移和高斯光束，区分错误和待实测条件。带 ERROR 的追迹不能进入排板。主线保持光路原理、二维排板、三维与制造三个阶段；定制件是按缺件需求触发的支线，登记后回到排板复验。四个插件独立加载、独立安装，通过冻结文件交接，不共享跨插件进程或隐含上下文。

The main line remains Optical Graph → Board Layout → 3D & Manufacture. Custom CAD is an on-demand branch that returns to layout verification after intake. Four independently installable plugins exchange frozen files; no plugin imports another plugin or depends on a shared host process.

## 单源与独立安装 / Authoring and distribution

本仓库选择方案 B，保留 `.agents/plugins/marketplace.json` 的 `./plugins/<name>` 零构建入口。改为纯 `dist/` 入口会要求现有 Codex 市场用户在首次加载前运行构建，因此本次不改变该契约。作者源为 `src/optical_graph`、`src/optical_layout` 和 `scripts/` 的两个设计入口。Step 1 使用光路引擎；Step 2 需复算光路，故使用光路与排板引擎；入库与三维仅分发各自所需的本体定位器。所有受控分发路径逐文件登记在 `scripts/sync_plugins.py::distribution_map()`，禁止额外副本或内容漂移。

**Strategy B preserves zero-build loading from `./plugins/<name>`.** Step 1 needs the graph engine; Step 2 must replay that graph and needs both engines. Intake and 3D receive only the core resolver they actually use. The explicit distribution map is the complete allowlist, with byte-for-byte source checks. This is deliberate runtime distribution, not permission to add arbitrary copies.

Each `plugin.json` owns that plugin's identity, description and prompts; `.codex-plugin/plugin.json` is derived. `packaging/release.json` owns the release version, synchronized into four plugin manifests, four DSH package manifests, `pyproject.toml` and `compatibility.json`. The core catalog remains a separately pinned compatibility input.

~~~sh
python3 scripts/sync_plugins.py --apply
python3 scripts/sync_plugins.py --check
python3 scripts/build_dist.py
~~~

Git 中不再保存 `dsh-plugins/`。`packaging/dsh/` 仅保留每个宿主的四个包装文件：清单、Cordis 补丁、注册入口和说明。`build_dist.py` 从原生插件装配其 `skills`、`rules`、`assets` 及必要 `shared`，写入被忽略的 `dist/dsh-plugins/`。安装器自动完成构建；dry-run 只在临时目录构建，不写客户端目录。生成包与原生包逐字节核对并分别扫描隔离边界。开发用软链接安装仍可显式选择，但 Git 跟踪的文件与插件载荷不得包含软链接。

DSH templates are not installable payloads. The installer builds the four complete Cordis packages on demand. Dry-runs use temporary assembly; copy and explicit developer-link modes use the generated distribution. Local edits and foreign receipts remain protected, including the Codex versioned cache.

DSH 桌面配置可将生成包作为本地 `link:` 依赖加载，在“插件 → 已安装”中分别启停。普通工作区的新对话中，用 `/` 加技能名调用。每份 `cordis.patch.yml` 仅声明自身；账号、模型和路由由宿主管理。

In DSH, add generated packages as local `link:` dependencies in the desktop configuration and enable each under Plugins → Installed. Invoke a skill with `/` plus its name in a new workspace chat. Each Cordis patch declares only its own plugin; accounts, models and routing remain host-managed.

## 规则与资料 / Instructions and references

各插件的 `rules/AGENTS.md` 保存常驻约束。六个 `SKILL.md` 只保留触发条件、执行流程、脚本、交付和检查入口，并指向本插件规则；宿主已注入时不重复读取。DSH 注册入口仍将技能与本阶段规则组合一次，验收会真实加载入口，检查六份最终提示词，不依赖字符串搜到注册函数就判通过。

定制件的 `shared/` 只保留一份俯视渲染、一份风格规范和一份验收复用规则。底板标识、完整加工包和激光打标规范归 Step 3；定制件仅保留四行接口边界。两个同名漂移文档已合并，经比较差异都是失效或缺失链接，工程条款完整保留并恢复指向权威文件。官方 Logo、彩色符号、字体声明及品牌清单均复用 Step 3 原资产。

`docs/library-policy.md` 是保留策略的唯一作者源；为离线独立安装，在 custom-part 和 manufacture 各派生一份按需读取的政策文件，九份原指南不再复写该长段。两阶段都需要的 2D 制图详规以 Step 3 的 `drawing-standard.md` 为作者源，custom-part 仅保留一份受控分发。历史项目位置、旧型号基线、网页交互与总册维护资料移到 `docs/heritage-archive/`，不进入安装包。当前设计依据保留在各技能的 `references/design-guides/`；不以“历史”标签删除仍有效的工程知识。

Standing instructions are loaded once per plugin. Current, task-specific references remain available on demand. Human-only project snapshots and optional web/atlas procedures stay outside installed packages. Shared retention and drawing policies have explicit authoring sources and the minimum controlled copies needed for offline independence.

## 门禁 / Gates

`test_repo_hygiene.py` 保留暂存区与工作文件双扫描、隐私/凭据检查、每个文件小于 2,000,000 字节、无软链接、隔离、定位器与 Cordis 契约。新增规则/技能长段交集、未登记同字节副本、同名语义冲突及 DSH 运行期提示词重复检查。内嵌资源先解码再检查，正文继续检查，不能把 Base64 编码当作隐私豁免。`packaging/semantic-names.json` 只列出确有不同职责的入口文件，按准确路径登记；增加同名文件必须重新说明其用途。

`packaging_regression.py` includes negative fixtures for duplicate files, semantic drift, repeated prompts, unowned build targets, symlinks and modified Codex caches, plus every installed Markdown reference. `showcase_acceptance.py` checks both translations, original embedded assets, brand identity, cover hashes and exact export dimensions. Existing optical, PM, board and native CAD tests retain their assertions.

The full integration test requires the compatible core, Node and a Python interpreter with OCP and NumPy. CAD results are digital verification, not physical power, PER, machining or first-article acceptance.

设计规范 / Specifications: [OpticalGraph](specs/optical-graph-v1.0-spec.md) · [Board layout](specs/layer2-auto-layout-spec.md) · [Plugin boundaries](specs/hksop-4-plugins-spec.md).
