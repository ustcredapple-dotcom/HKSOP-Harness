> 设计规范。仓库内的当前命令、依赖及目录结构见 [README](../../README.md)。

# HKSOP 四插件分步隔离封装规范（一步一插件工程施工图）

> **定位说明**：前三份规格书已经分别定型了[第一层纯光学语法与原理图渲染](optical-graph-v1.0-spec.md)、[第二层自动盘板、滑台与 M6 对孔引擎](layer2-auto-layout-spec.md)以及元件库精简主推契约。本文件给出最终面向日常使用与团队分发的**“一步一插件”工程封装规范**：把整个流程切分成 **3 个主线步骤插件 + 1 个按需开启的支线造件插件**，每个插件独立成文件夹、独立打包规则、靠唯一交接文件单向接力，彻底根除跨步上下文污染与 AI 越界抢跑。

---

## 1. 为什么要“一步一个独立插件”？（核心隔离架构）

在插件系统里，只要一个插件处于启用状态，它携带的 `rules/AGENTS.md` 与 `skills/*/SKILL.md` 说明就会常驻或被路由进模型上下文。把所有流程拆成 **4 个物理隔离的独立文件夹插件** 后：
- **干哪一步就只开哪一个插件**（或新开对话仅启用对应插件）；
- 第 1 步讨论光学方案时，AI 脑子里绝不会混进“C0.3 倒角”或“面包板侧壁镭雕”；
- 上下游只靠硬盘上的标准交付文件交接，换人或换对话都能无缝续跑。

```mermaid
flowchart LR
    U["实验需求"] --> P1["插件 1：hksop-step1-optics<br/>(\"纯光学原理与仿真 · 零外部依赖\")"]
    P1 -->|"交接文件：graph.py / trace.json / schematic.svg"| P2["插件 2：hksop-step2-board<br/>(\"二维自动盘板 · 配LS30与M6对孔\")"]
    P2 -.->|"若吐出 custom-wishes.json"| PX["支线插件：hksop-custom-part<br/>(\"非标转接件 CAD 与库入库维护\")"]
    PX -.->|"入库并重编精简清单后重跑"| P2
    P2 -->|"定稿交接文件：project.zzoptics.json"| P3["插件 3：hksop-step3-manufacture<br/>(\"三维总装 · 3D光管挡光终检 · 出加工包\")"]
```

---

## 2. 落地总目录树与单插件标准文件夹结构

所有 4 个插件统一构建在 `<WORKSPACE>/plugins/` 目录下（先验收测试，不擅自修改用户全局目录）：

```text
<WORKSPACE>/plugins/
├── hksop-step1-optics/           # 插件 1：纯光学原理设计与仿真
├── hksop-step2-board/            # 插件 2：二维面包板自动盘板、配滑台与 M6 对孔
├── hksop-custom-part/            # 支线插件：非标转接件 CAD 建模与元件库维护
└── hksop-step3-manufacture/      # 插件 3：三维总装、三维光束管碰撞终检与加工/客户包导出
```

### 每个插件内部的标准目录结构（双平台兼容）

```text
<plugin-dir>/
├── plugin.json                   # Antigravity 官方清单（仅用白名单字段）
├── .codex-plugin/
│   └── plugin.json               # Codex 插件清单（共享同目录 skills / scripts）
├── README.md                     # 给人类看的操作说明与交接契约（不注入 AI 上下文）
├── assets/
│   └── logo.svg                  # 128x128 透明底高对比正方形图标（四周预留 ~10% 留白）
├── rules/
│   └── AGENTS.md                 # 纯 Markdown 铁律（严禁写 YAML frontmatter，只写本步约束）
└── skills/
    └── <skill-name>/
        ├── SKILL.md              # 带 name / description frontmatter，正文章节简练清晰（<250 行）
        ├── references/           # 精简速查表与本步专属参考规范
        └── scripts/              # 本插件直接调度的 Python / Shell 脚本
```

> [!IMPORTANT]
> **清单字段严格守则（Antigravity + Codex 通用约束）**：
> 1. Antigravity 根目录 `plugin.json` **只允许**使用以下白名单顶层字段：`name`、`displayName`、`version`、`description`、`logo`、`suggestedPrompts`（恰好 3 条简明中文常用启动语）。**严禁发明其他自定义顶层字段**，且 4 个插件的 `name` 必须全局唯一。
> 2. `.codex-plugin/plugin.json` 放置面向 Codex 运行时的镜像元数据，与根目录清单保持一致。
> 3. `rules/AGENTS.md` 必须是**无 YAML frontmatter 的纯 Markdown**，仅在对应插件开启时生效；`skills/*/SKILL.md` 必须有合规的 `name` 和 `description` YAML frontmatter。
> 4. 图标 `assets/logo.svg` 必须是正方形矢量图（`viewBox="0 0 128 128"`），透明背景，主图形居中并留约 10% 边距，深浅色主题均高对比可读（4 个插件分别采用：**1. 棱镜与光线**、**2. 孔阵网格与折线**、**3. 卡尺与定制铝块**、**4. 立方总装与工程箱**）。

---

## 3. 四个插件逐个详细规格

### 3.1 插件 1：`hksop-step1-optics`（纯光学原理车间）

- **Manifest `name`**：`"hksop-step1-optics"`
- **`displayName`**：`"HKSOP Step 1 · 纯光学原理设计"`
- **唯一输入**：用户的自然语言光学目标，或待修正的 `graph.py`。
- **唯一输出**：`graph.py`（`OpticalGraph v1.0` 代码）、`trace.json`（`hksop-optical-graph-v1` 格式）、`schematic.svg`（及可选 `gallery.html`）。
- **内置程序与资料（100% 自包含，不连元件库）**：
  - 将已验收通过的纯标准库 `optical_graph/` 与 `optical_graph_render.py` 直接打包进 `skills/optics-graph-design/scripts/`（零外部依赖，任何电脑装上插件就能跑）；
  - `references/optical-graph-cheatsheet.md`：只放 24 种抽象元件构造函数、四口 `p1..p4` 拓扑配对表、双通/对射写法与 6 项自动体检码速查。
- **`rules/AGENTS.md` 专属铁律**：
  1. 本阶段只谈纯光学原理与端面几何距离：禁止出现任何二维坐标、旋转角、孔阵、螺丝孔或机械支架具体型号；
  2. 禁止读取原元件库或尝试执行排板与三维建模命令；
  3. 每次生成或修改 `graph.py`，必须实际执行内置脚本跑通 6 项体检并输出 `schematic.svg`；
  4. 展示光路原理图、关键光斑与偏振结论后**立即停手**，提示用户确认无误后开启 `hksop-step2-board` 继续。
- **`suggestedPrompts`（3 条）**：
  - `"根据实验参数设计一套双通 AOM 移频进保偏光纤的原理方案并出原理图"`
  - `"帮我审查并检查这段 OpticalGraph 光路代码有没有偏振、孔径或废光漏洞"`
  - `"把两束不同波长激光合束后垂直向下打穿面包板，生成第一层原理图"`

---

### 3.2 插件 2：`hksop-step2-board`（二维自动盘板与对孔车间）

- **Manifest `name`**：`"hksop-step2-board"`
- **`displayName`**：`"HKSOP Step 2 · 二维自动盘板与对孔"`
- **唯一输入**：第 1 步体检通过的 `graph.py`（或 `trace.json`）+ 面包板尺寸/孔距/板级光高策略要求。
- **唯一输出**：`project.zzoptics.json`、`step6_board_layout.svg`（7 层工程俯视图）、`step_by_step_walkthrough.html`（6 步白盒审计页）、`bom.json`，以及按需生成的 `custom-wishes.json` / `custom-wishes.md`。
- **内置程序与仓库连接**：
  - `skills/board-auto-layout/scripts/` 内置 `optical_layout/` 与 `optical_graph_to_board.py`（以及辅助检查精简目录与调用复验的轻量包装）；
  - 通过环境变量 `$HKSOP_ROOT`（未设置时默认使用 `$HKSOP_ROOT`）**只读访问** `library/catalog-ai-slim.json`（`<200 KB`）与 `library/curation.json`，并调用 `python3 $HKSOP_ROOT/hksop.py design verify/export` 做多边形底座碰撞与光学复验；
  - 可附带说明如何一键用 `python3 $HKSOP_ROOT/hksop.py serve` 打开网页编辑器微调排好的 `.zzoptics.json`。
- **`rules/AGENTS.md` 专属铁律**：
  1. 严格执行第 2 层的四项核心准则：精密 `LS30` 滑台配置（S1–S4，含 `37.5 mm` 叠高联动与 `MFT` 豁免）、90° 横平竖直正交盘板、`≥ 25 mm` 旋钮/千分尺操作净空；
  2. **严禁自动挂载库内 `EX / ED` 标准延长块**；凡无法靠活距离调通的对孔缺口或非标外购件，一律直接输出定制转接件需求单 `WISH-xxx`；
  3. 禁止擅自篡改上游 `graph.py` 的物理拓扑或丢弃锁定的死距离（若限定板型确定塞不下，明确报出瓶颈并建议最小可用板型）；
  4. 严禁在本插件内运行重型 3D CAD 装配；输出 7 层工程俯视图并给出 6 步汇总后**立即停手**：若存在 `custom-wishes.json` 则提示开启 `hksop-custom-part` 补齐定制件，若全标准件无冲突则提示开启 `hksop-step3-manufacture`。
- **`suggestedPrompts`（3 条）**：
  - `"把当前通过体检的 graph.py 自动排进 450×350 mm（12.5 mm 孔距）面包板并输出俯视图"`
  - `"在 25 mm 孔距限制下帮我选最小能装下的标准面包板，并标出哪些地方配了 LS30 滑台"`
  - `"检查这个布局里哪些器件没对上 M6 螺孔，列出需要定制的偏心转接板清单"`

---

### 3.3 支线插件：`hksop-custom-part`（非标转接件设计与元件库维护车间）

- **Manifest `name`**：`"hksop-custom-part"`
- **`displayName`**：`"HKSOP Custom · 非标件设计与元件库"`
- **什么时候开**：**平时可保持关闭**；仅当第 2 步吐出黄色 `custom-wishes.json`，或者新买商业光学零件要入库、调整 `curation.json` 主推清单时开启。
- **唯一输入**：`custom-wishes.json`（偏心转接铝板、非标光高座、低剖面滑台转接座、电动微调镜座、特种蒸汽室夹具）或厂家原厂 STEP / PDF 资料。
- **唯一输出**：完成三维 STEP、加工工程图、正交金属俯视图 SVG 的完整元件包（写入 `$HKSOP_ROOT/library/custom/` 或 `library/standard/`）+ 重编后的全库清单与 `catalog-ai-slim.json`。
- **包含的 2 个正交 Skills（完整收编原库造件与入库规范）**：
  1. `skills/custom-part-cad/SKILL.md`：合并原 `zzlab-modular-optics` + `zzlab-motorized-mirror-design` + `hksop-component-design`。读取 `WishSpec` 的 `opticalDatum`、`mountingInterface`、`envelopeBudgetMm`，调用本地 `cad-venv` Python (`CadQuery`) 自动建模并产出加工工程图，同时附带 `scripts/parse_wishes.py`（自动校验并拆解 `custom-wishes.json` 任务单）。
  2. `skills/library-intake/SKILL.md`：合并原 `hksop-component-upload` + `zzlab-optics-library` + `hksop-standard-optics` 的入库维护职责。执行结构与 SHA256 资源校验、事务化入库、`curation.json` 主推Tier维护及 `hksop.py catalog build` 重编。
- **`rules/AGENTS.md` 专属铁律（只在本插件开启时加载，绝不干扰前两步）**：
  1. 自制机加工件普通去锐边默认采用 **`C0.3×45°` 倒角协议**（功能配合边与薄壁处单独核定，实际 STEP 与加工工程图必须一致）；
  2. 入库俯视图必须采用**真实完整 CAD 正交金属着色质感渲染**（遵守 `topview-style` 规范，严禁用纯色方块/包围盒充当有 CAD 元件的最终图）；
  3. 严格执行 **版本保留协议**：更新已有元件前必须先向用户确认“保留旧版至 `library/history`”还是“跳过历史归档”，历史元件仅允许供旧工程渲染，禁止进入新选型列表；
  4. 仅将 `library/custom/` 或 `library/standard/` 新件落库并刷新 `catalog-ai-slim.json` 后即止步，提示用户切回 `hksop-step2-board` 用正式入库新件替换黄色占位重验。
- **`suggestedPrompts`（3 条）**：
  - `"读取 custom-wishes.json，为所有待定制的偏心转接板与非标座生成 STEP 模型和工程图"`
  - `"按 HKSOP 规范把刚画好的定制转接件校验入库，并刷新精简目录"`
  - `"帮我把一套新采购的商业镜架/电动调整架拆解成标准套件包登记进元件库"`

---

### 3.4 插件 3：`hksop-step3-manufacture`（三维总装、3D 挡光终检与交付包车间）

- **Manifest `name`**：`"hksop-step3-manufacture"`
- **`displayName`**：`"HKSOP Step 3 · 三维总装与加工交付包"`
- **唯一输入**：第 2 步全部通过（且零未解决占位件，或已由用户确认放行范围）的 `project.zzoptics.json`。
- **唯一输出**：整板三维总装 `assembly.step`、三维光束管碰撞检查报告 `beam_clearance_3d.json`、含铭牌框线镭雕的面包板加工图、机加工交付包 `manufacturing_package.zip` 及客户采购包 `customer_package.zip`。
- **包含的 2 个正交 Skills（完整收编原库三维转制与交付规范 + 补齐三维光束管检查）**：
  1. `skills/json-to-3d-verify/SKILL.md`：继承原 `zzlab-optics-json-to-3d`（按 `.zzoptics.json` 的真实矩阵变换与万能柱高度组装保留源层级的三维总装 STEP），**并内建 `scripts/check_3d_beam_clearance.py`**：依据二维布局追迹段、爬架高低变化与 `VerticalFold` 下打孔径在三维空间生成含真实高斯包络余量的光束管，核查是否擦到相邻支架立柱边缘、滑台本体或面包板开孔孔壁！
  2. `skills/export-packages/SKILL.md`：合并原 `hksop-manufacturing-package` + `hksop-customer-package`，汇总所有自制铝件 STEP/图纸、激光打标图元、采购物料清单与版本号锁定的客户/加工包。
- **`rules/AGENTS.md` 专属铁律（只在本插件开启时加载）**：
  1. **面包板固定标识与定位框镭雕铁律**：主底板、模块底板和小面包板在布局朝外侧竖直壁右端镭雕完整 **`HKSOP` 黑白 Logo**（外侧正看距右 `3 mm`、距上下各 `1.5 mm`，左侧图案右侧 `HKSOP` 为 `Manrope Bold` 字体、下方全称 `Hong Kong Standard Optical Protocol` 为像素字体）；面包板顶面须提供器件定位框、编号、朝向点位、名义光路辅助线，且**每个定位框内必须刻该器件中文名及与转接件一致的英文字样**；
  2. **占位拦截防呆**：若检测到 `project.zzoptics.json` 中仍有 `placeholder: true`（未入库黄色 `WISH` 块），强制发出阻断提示并建议回到 `hksop-custom-part` 完成设计，严禁把未落地占位冒充已可制造放行。
- **`suggestedPrompts`（3 条）**：
  - `"把确认好的 project.zzoptics.json 拼成整板三维总装 STEP，并检查有没有三维光束擦边挡光"`
  - `"为当前模块生成含侧壁 HKSOP Logo、顶面中文定位框镭雕的机加工交付包"`
  - `"汇总本光路版本锁定的全部采购清单与装配文档，打包生成客户交付包"`

---

## 4. 原库 11 个散装 Skill 的 100% 无损归宿对照表

拆成 4 个插件后，原先仓库里容易混乱的 11 个 Skill 全部精确落位，**核心工程经验零丢失**：

| 原 `$HKSOP_ROOT/skills` 名 | 归宿去向（新插件 / 技能位置） | 传承说明 |
|---|---|---|
| *(全新)* 第一层抽象光路建模与渲染 | **`hksop-step1-optics`** → `skills/optics-graph-design` | 含 `OpticalGraph v1.0` + 高斯/琼斯模拟器 + 原理图渲染 |
| *(全新)* 第二层自动盘板、滑台与 M6 对孔 | **`hksop-step2-board`** → `skills/board-auto-layout` | 含 `LS30` S1–S4、90° 盘板、25 mm 净空、零 `EX/ED` |
| `hksop-component-design` | **`hksop-custom-part`** → `skills/custom-part-cad` | 统一标准/定制件接口设计 |
| `zzlab-modular-optics` | **`hksop-custom-part`** → `skills/custom-part-cad` | 保留公制光高、真实光学面、C0.3 倒角与金属俯视图规范 |
| `zzlab-motorized-mirror-design` | **`hksop-custom-part`** → `skills/custom-part-cad` | 保留电动镜架驱动连杆、通光孔与运动包络规范 |
| `hksop-component-upload` | **`hksop-custom-part`** → `skills/library-intake` | 保留包校验、SHA256 资源映射与事务化入库 |
| `zzlab-optics-library` | **`hksop-custom-part`** → `skills/library-intake` | 保留厂家资料核对、真实俯视图渲染与版本保留规则 |
| `hksop-standard-optics` | 职责拆解：入口路由交给 4 个插件各自承载；入库规则迁入 **`hksop-custom-part`** → `skills/library-intake` | 消除重名总管 Skill，减少冗余上下文 |
| `zzlab-optics-json-to-3d` | **`hksop-step3-manufacture`** → `skills/json-to-3d-verify` | 继承 3D 装配变换，并升级加入 `check_3d_beam_clearance.py` |
| `hksop-manufacturing-package` | **`hksop-step3-manufacture`** → `skills/export-packages` | 继承加工图纸、STEP 与侧壁 Logo / 定位框镭雕交付 |
| `hksop-customer-package` | **`hksop-step3-manufacture`** → `skills/export-packages` | 继承版本锁定工程与完整采购清单出包 |
| `mac-nas-storage` | 保持在系统通用维护插件/全局层（不放入光学插件） | 保持电脑级 NAS/外接盘存储策略与纯光学流程解耦 |
| `project-archive-log` | 保持在系统通用维护插件/全局层（不放入光学插件） | 保持跨项目日志审计工具独立可用 |

---

## 5. 安全交付边界、辅助安装工具与自动化验收（`plugins_acceptance.py`）

### 5.1 安全红线（禁止直接动用户全局配置）

1. 本次制作仅在 **`<WORKSPACE>/plugins/`** 内生成 4 个完整插件文件夹及测试验收脚本，**严禁直接写修改用户家目录 `~/.gemini/config/config.json` 或 `~/.codex/` 运行时全局配置**；
2. 同时附带一个小脚本 `<WORKSPACE>/install_plugins.py`：默认 `--dry-run` 只打印即将链接/复制的目标路径，用户确认后可手动传 `--target <插件目录> --mode symlink|copy` 一键部署到自己的 Antigravity 或 Codex 环境。
3. 严禁修改 `$HKSOP_ROOT/` 与 `$HKSOP_ROOT/` 的源码及原库内容。

### 5.2 自动化验收脚本 `plugins_acceptance.py` 必检项目

请 GPT 在 `<WORKSPACE>/plugins_acceptance.py` 实现以下 4 类自动化检查，全部通过返回码为 `0`，并写出 `<WORKSPACE>/results/plugins-acceptance/report.json`：

1. **双端 Manifest 与目录格式全检**：
   - 验证 4 个插件的 `plugin.json` 只包含白名单顶层键、`name` 彼此不重名、`suggestedPrompts` 恰好 3 条非空中文、`logo` 指向的 `assets/logo.svg` 可被 XML 解析且 `viewBox` 为正方形；
   - 验证 `.codex-plugin/plugin.json`、`README.md` 均存在；
   - 验证每个 `rules/AGENTS.md` 开头**不含** `---` YAML frontmatter；每个 `SKILL.md` 均包含有效 `name` 与 `description` frontmatter 且行数合理。
2. **上下文物理隔离泄漏静态扫描**：
   - 扫描 `hksop-step1-optics` 全目录的 Markdown/文本：确认不出现后续阶段才有的工艺与机械规范词条（如 `C0.3`、`Manrope`、`Hong Kong Standard Optical Protocol`、`LS30`、`catalog-ai-slim`、`cad-venv`）；
   - 扫描 `hksop-step2-board` 全目录的 Markdown/文本：确认不出现第 3 步制造词条（如 `C0.3×45`、`Manrope`、`Hong Kong Standard Optical Protocol`）——确保写出来的规则靠正向边界约束自身，不靠堆砌无关后期规则而造成上下文污染。
3. **四棒文件接力冒烟联调**：
   - **第 1 棒（Step 1 插件脚本）**：独立运行 `hksop-step1-optics` 内部打包的渲染脚本对一条双通测试光路生成临时目录的 `graph.py`、`trace.json` 和 `schematic.svg`（校验不依赖工作区外脚本）；
   - **第 2 棒（Step 2 插件脚本）**：运行 `hksop-step2-board` 内部脚本读取上一步产出的 `trace.json`（或 `graph.py`），生成 `project.zzoptics.json`、`step6_board_layout.svg` 与 `custom-wishes.json`（含 `WISH` 测试样例）；
   - **支线棒（Custom Part 插件脚本）**：运行 `hksop-custom-part` 内部 `parse_wishes.py` 成功解析上一步吐出的 `custom-wishes.json` 并输出结构化 CAD 任务简表；
   - **第 3 棒（Step 3 插件脚本）**：运行 `hksop-step3-manufacture` 内部 `check_3d_beam_clearance.py` 对一份无占位标准示例工程（如 `results/example/project.zzoptics.json`）完成三维光束管净空检查，验证返回码为 `0` 并产出 `beam_clearance_3d.json`。
4. **原有回归保护与日志登记**：
