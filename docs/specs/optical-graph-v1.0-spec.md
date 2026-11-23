> 设计规范。仓库内的当前命令、依赖及目录结构见 [README](../../README.md)。

# `OpticalGraph v1.0` 第一层纯光学语法定型总纲与原理图渲染交付规范

> **定位说明**：经过 GPT 与 DeepSeek 两轮双向盲测（正向需求编排 + 脱敏代码反向还原与找茬）验证，`OpticalGraph` 的核心骨架已证明无歧义且跨模型通用。本文件正式定型 **`OpticalGraph v1.0`** 第一层语法标准（吸收盲测暴露的细节补丁与三维穿层需求），给出第一层配套轻量原理图渲染程序（`optical_graph_render.py`）的完整设计，并附上供 GPT 直接在 `HKSOP harness` 中落地实现的**物理数学口径、JSON/CLI 契约与 10 组黄金回归验收标准**。

---

## 1. 第一层的职责边界（什么归第一层，什么留给第二层）

第一层只画**“纯光学原理与光程关系”**（好比电子电路里的原理图），第二层才负责**“在面包板上摆实物、加镜拐弯、对 M6 螺孔”**。两层分工严格正交：

| 维度 | 第一层：纯光学原理层（`OpticalGraph v1.0`） | 第二层：二维面包板落板层（Layout Engine） |
|---|---|---|
| **核心任务** | 表达光路功能、拓扑连接、偏振演化、移频、死距离与可折叠区间 | 替换真实 `HKSOP` 套件、插入 45° 折转镜盘进板面、对齐 M6 螺孔、查碰撞 |
| **空间坐标** | **禁止出现** `(x, y)` 坐标、旋转角 `rotationDeg`、孔距、孔阵 | 计算每个套件的真实 `(xMm, yMm, rotationDeg)` 与沉孔避让 |
| **拐弯与反射镜** | **禁止手插**纯粹为了省地方拐弯的 45° 平面反射镜；只在直线上写 `can_fold=True` | 在 `can_fold=True` 的准直段按 `L / U / Z` 自动插镜拐弯，自动防反面入射 |
| **硬件型号** | 只用抽象光学元件（如 `Lens`、`PBS`、`CustomTwoPort`） | 查 `curation.json` 优先选用 `Tier 1` 套件；缺失则生成许愿单 `custom-wishes.json` |
| **立体出平面光路** | 用 `HeightShift` / `VerticalFold` / `SpatialFold` 明确写出换高或上下折转 | 按换高选爬架、为向下穿光标记面包板开孔（Cutout）及非标定制座 |
| **距离定义** | **机械端面之间的空气几何距离**（`exact_mm` / `span` / `min_mm..max_mm`） | 直接将 `exact_mm` 对齐螺孔整数格或自动展开 `EX/ED` 延长块、`LS30` 滑台 |

---

## 2. 图容器与仅有的 3 个核心操作方法

```python
g = OpticalGraph(name: str, default_plane_height_mm: float = 62.5)
```

整套语法有且仅有以下 **3 个构图方法**（严禁另创 `chain`、`arm`、`branch` 等方法）：

### 2.1 `g.add(node_id: str, component: Component)`
向光路图中添加一个抽象光学元件。`node_id` 必须在同一张图内唯一（英文标识符，例如 `"LS"`、`"P1"`、`"AOM"`）。

### 2.2 `g.link(port_u, port_v, *, exact_mm=None, tol_mm=0.5, min_mm=25.0, max_mm=500.0, can_fold=False, note="")`
声明两个端口之间存在一条自由空间光路通道（端口名格式严格为 `"<node_id>.<port_name>"`）：

1. **物理通道唯一性（双向复用铁律）**：每条 `link` 代表两端口之间的一段**无向自由空间物理通道**。单向传播、经端镜 180° 原路往返的双通光束、以及相向对射的泵浦-探测光束，**共用同一条 `link`**。同一对端口之间严禁重复调用第二次 `link`。
2. **死距离模式（`exact_mm` 非空）**：要求两端口端面之间的物理空气距离严格等于 `exact_mm ± tol_mm`（通常须设 `can_fold=False`，例如开普勒透镜组 `f1 + f2`）。
3. **活距离模式（`exact_mm=None`）**：两端口之间允许在 `[min_mm, max_mm]` 区间内伸缩；若该段光束已准直且纯偏振安全、允许第二层为省空间自动插入 45° 折转镜拐弯，设为 `can_fold=True`。

### 2.3 `g.span(start_port, end_port, *, exact_mm: float, tol_mm: float = 0.5, note: str = "")`
声明**跨中间元件的总几何距离锁死约束**：当 `start_port` 到 `end_port` 之间串联了波片、平板窗、采样片等透射件时，内部单段 `link` 可以保持各自的活距离，但沿主路径从 `start_port` 到 `end_port` 的端面到端面总距离之和必须严格锁死：

$$\sum d_{\text{air\_link}} + \sum t_{\text{intermediate}} = \text{exact\_mm} \pm \text{tol\_mm}$$

> [!IMPORTANT]
> **v1.0 距离口径定型约定（空气端面几何距离 vs 内部光程焦移）**：
> 所有 `link` 和 `span` 填写的都是**光学元件端面之间的真实空气/几何空间距离**（这样第二层可以直接对着它量孔位、排延长块，不会差一两毫米）；而 `Window`、`PBS` 棱镜体、`AOM` 晶体内部的折射光程 $d/n$ 以及平板造成的近轴焦点后移 $\Delta = t(1 - 1/n)$，**全部由第一层纯光学模拟器在后台自动计入高斯追迹**。

---

## 3. 四大类抽象元件字典与端口公理（共 24 种标准元件原语）

| 类别 | 合法端口 | 适用对象与数量 |
|---|---|---|
| **A 类 · 单口元件** | `.front` | 发射光源（2）+ 接收终端与光阱（5）+ 原路端镜（1），共 **8 种** |
| **B 类 · 双口直穿元件** | `.a`、`.b` | 对称无源穿射件（7）+ 有向功能件（2），共 **9 种** |
| **C 类 · 四口十字元件** | `.p1`、`.p2`、`.p3`、`.p4` | 偏振/非偏振分束、抽样片、双色镜，共 **4 种** |
| **D 类 · 空间折转元件** | `.a`、`.b` | 同向/转向换高爬架、垂直上下打光、任意斜向入腔，共 **3 种** |

### 3.1 A 类 · 单口发射源、接收终端与原路端镜（唯一端口：`.front`）

1. **`LaserSource(wavelength_nm, diameter_mm, pol="P", pol_angle_deg=None, height_mm=None, power_mw=10.0, m2=1.0)`**
   - 空间自由光激光器。`height_mm=None` 时自动继承容器的 `default_plane_height_mm`；如为非标光高（如 `height_mm=95.7`）必须显式写出。
   - `pol` 允许取值：`"P"`（水平线偏振 0°）、`"S"`（竖直线偏振 90°）、`"linear"`（需配合 `pol_angle_deg`）、`"LHC"`（左旋圆偏振）、`"RHC"`（右旋圆偏振）、`"elliptical"`（未知椭圆偏振）、`"unpolarized"`（非偏振）。
2. **`FiberSource(wavelength_nm, diameter_mm, pol="P", mode="SM_PM", height_mm=None, power_mw=10.0)`**
   - 光纤准直发射源（如 `SM_PM` 保偏光纤输出头）。
3. **`FiberCoupler(mode="SM_PM", design_diameter_mm=None, required_pol="P", steering_mirrors=2)`**
   - 单模/保偏光纤耦合接收端。`steering_mirrors=2` 表示逻辑上直接连光路，第二层落板时自动在其前方配置 2 面指向耦合调节反射镜。
4. **`Photodiode(label="", bandwidth_mhz=None)`**
   - 光电探测器接收端（含高速拍频或直流锁频信号采集）。
5. **`Camera(label="")`**
   - 相机监控端（光斑轮廓、合束重合度监测）。
6. **`TargetPlane(label="", target_waist_um=None)`**
   - 物理实验作用靶面（真空腔内原子团中心、离子阱中心或目标焦点面）。
7. **`BeamDump(monitor_pd=False)`**
   - 废光吸收光阱。`monitor_pd=True` 表示自带后置功率监测探头的光阱（常用于从杂散/废偏振端口实时监控激光功率波动）。
8. **`RetroMirror(aperture_inch=1.0, actuation="manual")`**
   - 正入射全反端镜（`actuation` 可选 `"manual" | "piezo" | "motorized"`）。从 `.front` 射入的光束会严格沿同一条 `link` 180° 原路返回。

### 3.2 B 类 · 双口直线穿射元件（唯一端口：`.a`、`.b`）

#### 对称双向可逆无源件（`.a -> .b` 与 `.b -> .a` 等效通行）

9. **`Lens(f_mm, aperture_inch=1.0, kind="singlet", convex_toward="auto")`**
   - 球面/消色差/非球面透镜（`kind` 取 `"singlet" | "achromat" | "asphere"`）。
   - `convex_toward` 取 `"auto" | "a" | "b" | "both"`。平凸单透镜设为 `"auto"` 时，第一层模拟器根据两侧光束发散角（将凸面朝向准直侧/小发散角侧）自动判定正反面并透传给第二、三层，杜绝机械装配装反。
10. **`HalfWaveplate(aperture_inch=1.0, *, fast_axis_deg=None, target_pol=None, split_reflect_ratio=None, note="")`**
    - **v1.0 明确工作点规则**：禁止三个求解参数全部留空造成模拟器无法追迹（全空应在构图阶段抛出校验错误）。必须三选一：
      - 直接给出 `fast_axis_deg`（对线偏振角度 $\alpha_{\text{in}}$，出射偏振角为 $2\theta - \alpha_{\text{in}}$）；
      - 指定目标线偏振 `target_pol="P" | "S"`（由模拟器根据输入偏振自动反算快轴角）；
      - 紧贴后端分束 `PBS` 时指定 `split_reflect_ratio`（`0.0 ~ 1.0` 之间，表示希望反射端口 `.p2/.p4` 分走的比例，**彻底取代大模型手算三角函数**）。
11. **`QuarterWaveplate(aperture_inch=1.0, *, fast_axis_deg=None, target_pol=None, double_pass_flip=False, note="")`**
    - 四分之一波片。设置 `fast_axis_deg=45.0` 或 `double_pass_flip=True` 时，线偏振往返双通自动转为正交线偏振（`P <-> S`）；也可设 `target_pol="LHC" | "RHC" | "linear"` 由模拟器求解（全部留空同样判为构图错误）。
12. **`DualWaveplate(aperture_inch=1.0, *, target_pol="P", qwp_deg=None, hwp_deg=None, note="")`**
    - `QWP + HWP` 组合全偏振整形器，可将任意已知或未知椭圆偏振态整形为纯目标线偏振（对应库内双波片调整架）。
13. **`Aperture(diameter_mm)`**
    - 物理光阑/空间滤孔。
14. **`Window(thickness_mm, material="UVFS", refractive_index=None, clear_aperture_mm=25.0)`**
    - 透明平行平板/真空腔窗片。默认按材质查折射率（见第 7.1 节色散表），并在追迹时自动计入光程变化与焦点后移。
15. **`CustomTwoPort(device_type, length_mm, clear_aperture_mm, params=None, custom_reason="")`**
    - 标准化可扩展双口器件入口（如原子蒸汽室 `rb87_vapor_cell`、电光调制器 `eom`、参考光学腔 `cavity`、定制棱镜组等）。`length_mm` 参与 `span` 几何总长计算。

#### 有向功能件（定义正向工作方向为 `.a -> .b`）

16. **`Isolator(wavelength_nm, clear_aperture_mm=4.5, output_pol="P")`**
    - 法拉第光隔离器：仅允许 `.a -> .b` 正向通过并校准到 `output_pol`；任何沿相反方向射入 `.b` 口的回光均在内部隔离吸收，严禁再从 `.a` 输出（模拟器会对回击隔离器的错误分支报出 `isolator_reverse_blocked`）。
17. **`AOM(rf_mhz, order=+1, active_aperture_mm=1.5, zero_order_blocked=True)`**
    - 声光调制器：`.a -> .b` 正向通过取 `order` 级衍射（如 `+1` 或 `-1`），频移量为 $\text{order} \times f_{\text{RF}}$；若在猫眼配置中经端镜原路返回、从 `.b -> .a` 二次通过同一衍射级，总频移自动叠加为 $2 \times \text{order} \times f_{\text{RF}}$ 且衍射角自动共轭归零。

### 3.3 C 类 · 四口十字分束与合束元件（唯一端口：`.p1`、`.p2`、`.p3`、`.p4`）

#### 四口严格拓扑公理（所有四口元件统一遵守，不因手性摆放而混淆）

```text
                .p2 (上方 / 反射侧)
                 |
   .p1 (左) ─────/───── .p3 (右 / 直透侧)
                 |
                .p4 (下方 / 回返分离侧)
```

- **直线透射配对（穿直而过）**：`p1 <-> p3`，`p2 <-> p4`
- **90° 斜面反射配对（经斜边全反/分光）**：`p1 <-> p2`，`p3 <-> p4`

只要按这组配对连线，**无论正向分束、双向合束、还是猫眼双通回程复用分流，都不会弄反**：
- 主输入从 `.p1` 进：透射光去 `.p3`，反射光去 `.p2`；
- 回程正交光从 `.p3` 原路退回：直接从 **`.p4`** 反射导出（不回 `.p2`，也不会穿过 `.p1` 撞回激光器）；
- 双束正交合束：一束走 `.p1 -> .p3` 透射，另一束走 `.p4 -> .p3` 反射，恰好在 `.p3` 同向共线合束。

4 种四口标准元件如下：

18. **`PBS(aperture_inch=1.0)`**：偏振分束立方体，**`"P"` 偏振透射、`"S"` 偏振反射**。
19. **`NPBS(aperture_inch=1.0, reflect_ratio=0.5)`**：非偏振分束立方体，按固定比例 `reflect_ratio` 反射、`1 - reflect_ratio` 透射。
20. **`SamplerPlate(aperture_inch=1.0, reflect_ratio=0.02)`**：微弱抽样分束片，遵守相同四口配对（弱反射由 `reflect_ratio` 决定）。
21. **`Dichroic(aperture_inch=1.0, pass_wavelengths_nm=..., reflect_wavelengths_nm=...)`**：双色镜，按波长列表决定走透射配对还是反射配对。

### 3.4 D 类 · 空间换高与跳出二维平面折转元件（唯一端口：`.a`、`.b`）

当光路不局限于单层 62.5 mm 水平面时，使用以下 3 种标准折转原语（不需要更改 `add / link / span` 语法骨架）：

22. **`HeightShift(in_height_mm, out_height_mm, mode="straight", aperture_inch=1.0)`**
    - 水平爬高/降高潜望镜（进出光束均保持水平方向，仅光轴高度变化）：
    - `mode="straight"`：上下两面镜平行同向折返，**保持 `P/S` 偏振不变**；
    - `mode="turn90"`：进出光路在水平投影上拐 90° 的转向爬架，两镜正交导致水平偏振与竖直偏振互换（**自动执行 `P <-> S` 翻转**）。
23. **`VerticalFold(direction="down", aperture_inch=1.0)`**
    - 90° 垂直向上（`direction="up"`，朝 `+Z`）或垂直向下（`direction="down"`，朝 `-Z`）折转全反镜。
    - `.a` 接水平光路，`.b` 射出垂直于面包板的竖直光束；后续可直接接 `Lens`、`QuarterWaveplate`、`Window` 和 `TargetPlane`，第二层自动在板面对应 `(x, y)` 生成通光开孔检查。
24. **`SpatialFold(pitch_deg, yaw_deg=0.0, aperture_inch=1.0)`**
    - 任意三维斜向入腔/出射折转镜（例如真空上层斜向下俯冲 `pitch_deg=-15.0` 打入腔内原子团）。
    - 一旦进入 `VerticalFold` 或 `SpatialFold` 之后的光束段，模拟器自动切换为**三维随动局部偏振基底**追迹电场矢量与圆偏振旋向，不依赖桌面法线定义 `P/S`。

---

## 4. 第一层模拟器的 6 条自动校验铁律（标准化诊断码）

大模型写光路很擅长搭拓扑，但容易在手算三角函数、斜偏振可否折转、孔径余量和潜藏废光处马虎。第一层纯光学模拟器在读入 `OpticalGraph` 后，强制自动跑完以下 **6 项光学体检**，并按统一诊断码输出：

| 序号 | 检查项 | 标准化 `code` | 级别 | 触发条件与工程含义 |
|---|---|---|---|---|
| 1 | 端口与唯一通道 | `invalid_port_or_duplicate_link` | `ERROR` | 节点/端口名非法、不符合 A/B/C/D 公理，或在同一对端口间重复建立第二条 `link` |
| 2 | 废光安全（兼容工程防漏） | `unterminated_beam` / `defensive_dump` | `ERROR` / `INFO` | 非零功率出射口未接 `BeamDump` 或探测器报 `ERROR: unterminated_beam`；理想零功率暗口若主动接 `BeamDump` 防实测残余漏光，识别为合法 `INFO: defensive_dump`，不报错 |
| 3 | 混合偏振段禁折 | `polarization_fold_hazard` | `ERROR` | 在斜线偏振（如 `+45°`、`-45°`、波片与分束 `PBS` 之间）、圆偏振或椭圆偏振段上标记 `can_fold=True`（防止 45° 介质膜折转镜 $P/S$ 相移破坏偏振） |
| 4 | 非标光高段禁折 | `fold_at_nonstandard_height` | `WARNING` | `height_mm != default_plane_height_mm` 且尚未垂直折出的水平段标 `can_fold=True`，提示先经 `HeightShift` 回到主平面再折叠 |
| 5 | 通光孔径截光 | `tight_aperture` / `severe_clipping` | `WARNING` / `ERROR` | 逐面计算高斯光斑直径 $2w$：元件通光孔径 $D < 1.5 \times (2w)$ 报 `WARNING: tight_aperture`；$D < 1.0 \times (2w)$ 报 `ERROR: severe_clipping` |
| 6 | 准直、回光与终端匹配 | `collimation_error` / `isolator_reverse_blocked` / `terminal_no_light` / `pm_pol_mismatch` | `ERROR` | 望远镜失准直（如 50+100 错写成 50 mm 间距）、回光撞入隔离器 `.b` 端、终端未收到光或光斑/偏振不符合 `FiberCoupler` 要求 |

---

## 5. 四种典型拓扑的标准写法速查

### 5.1 单向扩束锁距（`exact_mm` 死距离与 `can_fold=True` 分工）

```python
g = OpticalGraph("kepler-expander", default_plane_height_mm=62.5)
g.add("LS",  LaserSource(wavelength_nm=780.0, diameter_mm=0.8, pol="P"))
g.add("ISO", Isolator(wavelength_nm=780.0, output_pol="P"))
g.add("L1",  Lens(f_mm=50.0, aperture_inch=1.0, kind="singlet", convex_toward="a"))
g.add("L2",  Lens(f_mm=150.0, aperture_inch=1.0, kind="singlet", convex_toward="b"))
g.add("HWP", HalfWaveplate(aperture_inch=1.0, target_pol="P", note="PM 轴微调"))
g.add("FC",  FiberCoupler(mode="SM_PM", design_diameter_mm=2.4, required_pol="P", steering_mirrors=2))

g.link("LS.front", "ISO.a", min_mm=30.0, max_mm=150.0, can_fold=False)
g.link("ISO.b",    "L1.a",  min_mm=30.0, max_mm=200.0, can_fold=True)
g.link("L1.b",     "L2.a",  exact_mm=200.0, tol_mm=0.5, can_fold=False)  # 中间有实焦点，禁折锁死
g.link("L2.b",     "HWP.a", min_mm=30.0, max_mm=250.0, can_fold=True)
g.link("HWP.b",    "FC.front", min_mm=40.0, max_mm=300.0, can_fold=True)
```

### 5.2 按分光比反解的级联树（波片到分束 PBS 之间严格 `can_fold=False`）

```python
# 只需声明各 PBS 想反走的比例 split_reflect_ratio，第一层自动反算波片快轴角，绝不算错
g.add("H1", HalfWaveplate(split_reflect_ratio=0.5, note="第 1 级可调分束"))
g.add("P1", PBS())
g.add("H2", HalfWaveplate(split_reflect_ratio=0.4, note="输入是 S，模拟器自动反算角度"))
g.add("P2", PBS())
g.add("HB", HalfWaveplate(target_pol="P", note="将反射 S 光转回 P"))
g.link("H1.b", "P1.p1", min_mm=25.0, max_mm=80.0, can_fold=False)   # 混合斜偏振禁折
g.link("P1.p2", "H2.a", min_mm=30.0, max_mm=120.0, can_fold=True)  # 纯 S 光段允许折叠
g.link("H2.b", "P2.p1", min_mm=25.0, max_mm=80.0, can_fold=False)   # 混合斜偏振禁折
```

### 5.3 猫眼双通 AOM 复用（单根物理通道往返复用 + `span` 跨组件锁距）

```python
# P1.p1 -> P1.p3 去程(P)；P1.p3 -> P1.p4 回程(S)，AOM 到端镜只写一套 link
g.link("H_in.b",  "P1.p1",  min_mm=25.0, max_mm=100.0, can_fold=False)
g.link("P1.p3",   "AOM.a",  min_mm=40.0, max_mm=150.0, can_fold=False)
g.link("AOM.b",   "L_cat.a", exact_mm=100.0, tol_mm=0.5, can_fold=False)
g.link("L_cat.b", "QWP.a",  min_mm=15.0, max_mm=60.0, can_fold=False)
g.link("QWP.b",   "RM.front", min_mm=15.0, max_mm=60.0, can_fold=False)
g.span("L_cat.b", "RM.front", exact_mm=100.0, tol_mm=0.5, note="端镜位于猫眼后焦面")

g.link("P1.p4",   "H_out.a", min_mm=30.0, max_mm=150.0, can_fold=True)
```

### 5.4 水平面转垂直向下跨真空窗打原子（`VerticalFold` 三维穿层）

```python
g.add("Src",    FiberSource(wavelength_nm=399.0, diameter_mm=2.0, pol="P"))
g.add("HS",     HeightShift(in_height_mm=62.5, out_height_mm=212.5, mode="turn90"))
g.add("QWP",    QuarterWaveplate(target_pol="LHC"))
g.add("M_down", VerticalFold(direction="down", aperture_inch=2.0))  # .a 水平进，.b 垂直向下(-Z)出
g.add("Obj",    Lens(f_mm=100.0, aperture_inch=2.0, kind="achromat"))
g.add("Win",    Window(thickness_mm=6.0, material="UVFS"))
g.add("Atoms",  TargetPlane(label="腔内镱原子团"))

g.link("Src.front", "HS.a", min_mm=30.0, max_mm=120.0, can_fold=True)
g.link("HS.b",      "QWP.a", min_mm=30.0, max_mm=120.0, can_fold=False)
g.link("QWP.b",     "M_down.a", min_mm=25.0, max_mm=80.0, can_fold=False)
g.link("M_down.b",  "Obj.a", min_mm=30.0, max_mm=150.0, can_fold=False)
g.link("Obj.b",     "Win.a", min_mm=30.0, max_mm=80.0, can_fold=False)
g.link("Win.b",     "Atoms.front", exact_mm=45.0, tol_mm=0.5, can_fold=False)
g.span("Obj.b",     "Atoms.front", exact_mm=101.92, tol_mm=0.5)  # 空气几何总长已预补偿 6 mm UVFS 焦移 (+1.92 mm)
```

---

## 6. 第一层原理图轻量渲染程序（`optical_graph_render.py`）设计方案

写一个简单好用的程序直接把第一层 `OpticalGraph` 代码画成直观光路图，关键不在于“把长度按真实毫米等比例画出来”，而在于**把物理连接、分束反折方向、往返双通和报错体检一眼画明白**。

### 6.1 核心定位：画“逻辑原理图（Schematic）”，而不是“按毫米等比例的机械图”

如果按毫米等比例画图，一根 `200 mm` 的扩束段会拉得很长，而相邻两片间隔只有 `25 mm` 的波片和 PBS 会挤成一团看不清。因此第一层渲染采用**均匀逻辑网格 `(col, row)`**（例如每格 `120 × 100 px`）：
- 每个元件刚好占一个清爽的标准网格单元；
- 真实物理间距全部用标注徽章挂在连线上（比如死距离 `🔒 200.0±0.5 mm`，活距离 `30..200 mm 〰`）；
- 一张笔记本屏幕就能完整看完包含扩束、双通 AOM、一分三分配甚至双臂干涉仪的整张光路。

### 6.2 最巧妙的几何性质：45° 斜线方块天然满足全部四口公理

把每个四口元件画成一个**内部带 45° 斜线的正方形**，让 `(p1, p2, p3, p4)` 固定按顺时针或逆时针分布在正方形的四个正交面（随输入端转动自适应旋转）：

```text
                p2 (正上方：反射出/入)
                 ▲
                 │
   p1 (正左侧) ──┼──▶ p3 (正右侧：直线透射)
         /       │
                 ▼
                p4 (正下方：回程分流出 / 合束另一输入)
```

> 严格把 `(p1, p2, p3, p4)` 对应到正方形的 `(`左, 上, 右, 下`)`（斜线从左上到右下 `\` 表示 `p1↔p2`、`p3↔p4` 反射）会带来一个**拓扑保角性质**：
> - `p1 ↔ p3` 与 `p2 ↔ p4` 在图上**永远是一条直线穿过方块**；
> - `p1 ↔ p2` 与 `p3 ↔ p4` 在图上**永远是碰在 45° 斜线上拐整整 90° 弯**。
>
> 所以不管是正向分束、猫眼双通回程复用（`p3` 退回来撞斜面自动向下从 `p4` 出去）、双色镜合束（`p4` 向上撞斜面与 `p1` 直来的光在 `p3` 同向汇合），还是铷泡对射泵浦，画出来的光线拐弯方向和真实物理棱镜一致。

### 6.3 三步自动排版算法（零复杂依赖，约 140 行 Python 搞定）

1. **主光源正向树展开**：挑功率最大或首个 `LaserSource / FiberSource` 放 `(col=0, row=0)` 朝右生长；双口/单口件前进 `1` 格；四口分束器透射直走、反射拐向正交行，按子树占用行数 `[row_min, row_max]` 自动推开分支防止节点重叠。
2. **合束副光源逆向回推**：遇到多光源合束（如 532 nm 进双色镜 `D.p4`），从 `D.p4` 的正交入口方向**逆着光线往回退着分配网格**，自然长成十字汇合支路。
3. **闭环与干涉臂正交折线连接**：对两端节点都已定位的闭环边（如铷泡反向泵浦环、马赫-曾德尔双臂），用避让已占用格点的 `L` 形 / `U` 形曼哈顿折线从对应端口垂直绕出去接通。

### 6.4 光学符号与物理信息叠加层

- **纯 SVG 教材级光学符号**：光源喷嘴、隔离器单向箭头与反挡竖杠、平凸/双凸月牙透镜（按 `convex_toward` 画凸面朝向）、细长波片标注角、带声波齿纹的 AOM、45° 斜线方块分束器、黑体锯齿光阱、`⊗ DOWN (-Z)` / `⊙ UP (+Z)` 立体标志。
- **波长真彩色与双通双轨平行箭头**：`780 nm` 红、`532 nm` 翠绿、`1064 nm` 琥珀橙、`399/461 nm` 蓝紫；同一 `link` 上检测到双向光线时，在中心线上下错开 `±3 px` 画**去程实线箭头 + 回程/对射虚线反箭头**，各自独立标注偏振与移频。
- **约束徽章与错误高亮**：`exact_mm` 加锁徽标、`can_fold=True` 折弯波浪标、`span` 顶部括号总距标尺；一旦模拟器检出 `ERROR/WARNING`，对应元件和光束直接亮起红色/橙色警示光晕，右侧悬浮体检面板点击即高亮定位。

### 6.5 程序模块划分与命令行架构

```mermaid
flowchart LR
    A["OpticalGraph Python 文件<br/>(\"或 hksop-optical-graph-v1 JSON\")"] --> B["1. trace_lite (simulator.py)<br/>(\"复数q高斯 + 琼斯/斯托克斯 + 6项体检\")"]
    B --> C["2. schematic_layout.py<br/>(\"四口保角网格自动排版 + 闭合臂正交绕线\")"]
    C --> D["3. renderer.py<br/>(\"纯 SVG 矢量图 + 交互式多标签 HTML 对比页\")"]
```

---

## 7. 第一层物理追迹数学口径（防符号踩坑指南，供 GPT 实现 `simulator.py`）

为保证大模型心算与 Python 物理模拟器算出来的结果在小数点后完全一致，实现 `simulator.py` 时严格采用以下数学公式与坐标符号：

### 7.1 复曲率参数 $q$ 高斯追迹（支持 $M^2$ 与平板焦移）

- **初始条件（光源出口默认为束腰）**：$w_0 = d_{\text{in}} / 2$，瑞利长度 $z_R = \frac{\pi w_0^2}{M^2 \lambda}$，复参数 $q_0 = i z_R$（长度单位统一用 `mm`）。
- **空气段距离解析与传播**：
  - 若 `link` 设有 `exact_mm`，取 `d_air = exact_mm`；
  - 若无 `exact_mm` 但属于某条 `span(start, end, exact_mm=S)` 覆盖路径上**唯一未锁死**的自由段，自动精确反解：
    $$d_{\text{air}} = S - \sum d_{\text{locked\_links}} - \sum t_{\text{intermediate}}$$
    （其中中间厚元件厚度取 `Window.thickness_mm`、`CustomTwoPort.length_mm`，薄波片厚度取 `0.0`）；
  - 其余活距离取 `[min_mm, max_mm]` 中点 `0.5 * (min_mm + max_mm)`。
  - 空气传输矩阵作用：$q' = q + d_{\text{air}}$。
- **平行平板（`Window` / `CustomTwoPort` 折光段）**：
  - 传播矩阵等价空气折合光程：$q' = q + \frac{t}{n}$（自动体现平板造成的近轴焦点后移 $\Delta = t(1 - 1/n)$）。
  - 默认 `UVFS` 常用波长折射率查表（线性插值或分段查找）：`399 nm -> 1.470`、`532 nm -> 1.461`、`780 nm -> 1.454`、`1064 nm -> 1.450`（其他未注明默认取 `1.458`）。
- **薄透镜 `Lens(f_mm=f)`**：
  $$\frac{1}{q'} = \frac{1}{q} - \frac{1}{f}$$
  - 平凸透镜 `convex_toward="auto"` 判定规则：比较进入前光束发散角（$1/|R_{\text{in}}|$）与出射后发散角（$1/|R_{\text{out}}|$），将凸面自动朝向更准直（$|R|$ 更大）的一侧（即 `"a"` 或 `"b"`）并写入 trace 结果。
- **任意截面读数**：
  - $1/e^2$ 光斑直径：$d = 2w = 2\sqrt{\frac{-M^2 \lambda}{\pi \operatorname{Im}(1/q)}}$；
  - 波前曲率半径：$R = \frac{1}{\operatorname{Re}(1/q)}$（若 $\operatorname{Re}(1/q) == 0$ 或 $|R| > 5000\text{ mm}$ 且全束段变化率小，标为准直 `collimated=True`；`exact_mm` 跨度上焦点位置偏移判据可结合目标处 $\operatorname{Re}(q_{\text{target}})$ 与 $z_R$ 给出 `defocus_mm = Re(q_target)`）。

### 7.2 固定实验室偏振坐标与往返双通琼斯矩阵（防左右手翻转 Bug）

- **水平主平面固定横向基** $(x_P = \text{平行面包板水平方向},\; y_S = \text{垂直面包板竖直方向})$：
  - 水平线偏振 `"P"` $= [1, 0]^T$，竖直线偏振 `"S"` $= [0, 1]^T$，方位角 $\alpha$ 线偏振 $= [\cos\alpha, \sin\alpha]^T$；
  - `"LHC"` $= \frac{1}{\sqrt{2}}[1, i]^T$，`"RHC"` $= \frac{1}{\sqrt{2}}[1, -i]^T$；
  - `"elliptical"` 未知一般椭圆态在数值校验时固定采用非简并探测初态 $[\cos 28^\circ,\; e^{i \cdot 53^\circ}\sin 28^\circ]^T$ 追迹（既保证功率归一化为 1，又能检验任意椭偏输入下 `DualWaveplate` 与 `PBS` 纯化支路是否工作正常）；`"unpolarized"` 按各占 50% 功率的非相干正交 `P`/`S` 双态分解追迹。
- **波片快轴旋转投影与实验室系对称琼斯矩阵**：
  - 坐标投影矩阵明确定义为 $R(\theta) = \begin{pmatrix} \cos\theta & \sin\theta \\ -\sin\theta & \cos\theta \end{pmatrix}$（从 $(x_P, y_S)$ 投影到 `(fast, slow)`），反投影为 $R(-\theta) = R(\theta)^T$。
  - 快轴在 $\theta$、相位延迟 $\Gamma$（HWP 为 $\pi$，QWP 为 $\pi/2$）的实验室系矩阵为：
    $$J(\theta, \Gamma) = R(-\theta)\begin{pmatrix} 1 & 0 \\ 0 & e^{-i\Gamma} \end{pmatrix} R(\theta)$$
    对 HWP（$\Gamma = \pi$）化简为 $\begin{pmatrix} \cos 2\theta & \sin 2\theta \\ \sin 2\theta & -\cos 2\theta \end{pmatrix}$，作用在 $[\cos\alpha_{\text{in}}, \sin\alpha_{\text{in}}]^T$ 上严格等于 $[\cos(2\theta - \alpha_{\text{in}}), \sin(2\theta - \alpha_{\text{in}})]^T$。
- **正入射端镜 `RetroMirror` 双通往返规则**：
  - 在固定实验室横向基 $(x_P, y_S)$ 下，正入射反射不改变空间水平/竖直基轴的方向；因此反向二次穿过同一波片时，**直接再次左乘同一个对称矩阵 $J(\theta, \Gamma)$**（如 $\theta=45^\circ$ 的 QWP 连续两次作用满足 $J(45^\circ, \pi/2)^2 [1, 0]^T = -i[0, 1]^T \propto S$，绝不发生坐标系手性颠倒 Bug）。
  - 双通中正向/反向偏振分量分别按各四口 `PBS` 的反射对与透射对严格分离：$I_P = |E_P|^2$ 走透射配对（`p1<->p3`, `p2<->p4`），$I_S = |E_S|^2$ 走反射配对（`p1<->p2`, `p3<->p4`）。

### 7.3 波片目标模式自动反解与多光束干涉计算

- **`HalfWaveplate` 自动反解**：设入射纯线偏振在实验室系方位角为 $\alpha_{\text{in}}$（`"P"` 为 $0^\circ$，`"S"` 为 $90^\circ$）：
  - 若给定 `target_pol="P"`（$\alpha_{\text{out}} = 0^\circ$）或 `"S"`（$\alpha_{\text{out}} = 90^\circ$）：
    $$\theta_{\text{fast}} = \frac{\alpha_{\text{in}} + \alpha_{\text{out}}}{2} \bmod 180^\circ$$
  - 若给定 `split_reflect_ratio = r`（$r \in [0, 1]$，希望下一级 `PBS` 反射出去的 `S` 光功率占比 $\sin^2\alpha_{\text{out}} = r$）：
    $$\alpha_{\text{out}} = \arcsin(\sqrt{r}) \in [0^\circ, 90^\circ],\quad \theta_{\text{fast}} = \frac{\alpha_{\text{in}} + \alpha_{\text{out}}}{2} \bmod 180^\circ$$
    （无论来光是 `P` 还是 `S`，该式统一严格给出正确的快轴角；并将算出的角度写入节点的 `resolved_fast_axis_deg`）。
- **`QuarterWaveplate` 自动反解**：`double_pass_flip=True` 或 `target_pol="LHC"|"RHC"` 时自动锁定 $45^\circ$（或与入射 `S`/`P` 匹配的 $\pm 45^\circ$）以精确输出圆偏振或正交双通转换。
- **`DualWaveplate` 自动配对**：输入为任意极化状态时，直接构造精确将输入琼斯矢量正交映射到目标 `target_pol` 的理想波片对变换（记录虚拟求解角 `resolved_qwp_deg` / `resolved_hwp_deg`）。
- **三维立体折转与转向换高**：
  - `HeightShift(mode="turn90")`：直接交换偏振分量 $E_P \leftrightarrow E_S$；`mode="straight"` 保持矢量不变。
  - `VerticalFold` / `SpatialFold`：维护当前光束传播单位矢量 $\hat{k}$ 与三维正交电场基底 $(\hat{e}_1, \hat{e}_2, \hat{k})$，按反射镜反射定律 $\hat{k}' = \hat{k} - 2(\hat{k}\cdot\hat{n})\hat{n}$、`E' = E - 2(E·n)n`（含圆偏振旋向随反射自然反转）追踪后续元件；当 `direction == "down"` 或 `pitch_deg < 0` 时，在节点属性写明 `board_cutout_required = True` 传给第二层。
- **探测器 `Photodiode` 同频/外差干涉计算**：
  - 当多束相干同一波长的光束同时抵达同一 `Photodiode` 端口且偏振矢量非正交（$\mathbf{E}_1 \cdot \mathbf{E}_2^* \neq 0$）时，总平均功率计为 $\sum P_i$，并计算两束光复振幅内积 $2 \operatorname{Re}(\mathbf{E}_1 \cdot \mathbf{E}_2^*)$ 的拍频频率 $|\Delta f_1 - \Delta f_2|$（如 `|80 - 75| = 5.0 MHz`）与拍频复系数符号/相位角 `beat_phase_deg`（用于自动验证题 6 平衡探测 `ch_a` 与 `ch_b` 相差 $180^\circ$ 反相）。

---

## 8. 在 `HKSOP harness` 中的落地目录、JSON 导出与 CLI 契约

请 GPT 直接在 `<WORKSPACE>/` 目录下实现以下结构（**完全使用 Python 3 标准库**，零第三方 pip 依赖，不修改 `$HKSOP_ROOT/` 与 `$HKSOP_ROOT/`）：

```text
<WORKSPACE>/
├── optical-graph-v1.0-spec.md        # 本规范（已就位）
├── optical_graph_fixtures.py         # 10 组黄金测试光路（已就位）
├── optical-graph-expected.json       # 机器可读验收期望与契约（已就位）
├── optical_graph/                    # [待 GPT 实现] 第一层核心包
│   ├── __init__.py                   # 导出 OpticalGraph、全部 24 种元件类、trace_graph、validate_graph
│   ├── schema.py                     # 元件/连线/span 定义、端口公理校验、to_dict()/from_dict() JSON 序列化
│   ├── simulator.py                  # 第 7 节复数q高斯 + 琼斯/斯托克斯多束队列追迹与 6 项体检
│   ├── schematic_layout.py           # 第 6.3 节四口保角网格自动排版 + 闭合臂正交绕线
│   └── renderer.py                   # 纯 SVG 符号/双轨渲染 + 交互式多标签 HTML 生成器
├── optical_graph_render.py           # [待 GPT 实现] 命令行工具（支持单函数与 --all 批量画廊导出）
└── optical_graph_acceptance.py       # [待 GPT 实现] 自动化验收脚本（对比 10 组 fixtures 生成 results 报告）
```

### 8.1 `OpticalGraph` 标准 JSON 交换格式（`"format": "hksop-optical-graph-v1"`）

`g.to_dict(include_trace=True)` 导出 JSON 需满足以下结构，确保**未来第二层自动落板引擎可以直接读取同一份 JSON**：

```json
{
  "format": "hksop-optical-graph-v1",
  "name": "q3-double-pass-aom",
  "default_plane_height_mm": 62.5,
  "nodes": [
    {
      "id": "LS",
      "type": "LaserSource",
      "category": "single_port",
      "ports": ["front"],
      "params": {"wavelength_nm": 780.0, "diameter_mm": 1.2, "pol": "elliptical", "height_mm": 62.5, "power_mw": 50.0, "m2": 1.0},
      "computed": {"board_cutout_required": false}
    }
  ],
  "links": [
    {
      "id": "L1",
      "u": "P1.p3",
      "v": "AOM.a",
      "exact_mm": null,
      "tol_mm": 0.5,
      "min_mm": 40.0,
      "max_mm": 120.0,
      "resolved_air_mm": 80.0,
      "can_fold": false,
      "bidirectional": true,
      "note": ""
    }
  ],
  "spans": [
    {"start": "L.b", "end": "RM.front", "exact_mm": 100.0, "tol_mm": 0.5, "note": ""}
  ],
  "trace": {
    "valid": true,
    "diagnostics": [],
    "terminals": {},
    "beams": []
  }
}
```

### 8.2 命令行契约（`optical_graph_render.py`）

- 渲染单个函数并同时输出交互 HTML、纯 SVG 与追迹 JSON：
  `python3 scripts/optical_graph_render.py <py_or_json_file> --func <fn_name> -o <out.html> [--svg <out.svg>] [--json <trace.json>] [--allow-invalid]`
- 批量渲染一个 `.py` 文件里的全部光路到一个多标签对比 HTML 画廊：
  `python3 scripts/optical_graph_render.py <py_file> --all [-o results/optical-graph/gallery.html] [--svg-dir results/optical-graph/svg] [--json results/optical-graph/summary.json] [--allow-invalid]`
- 返回码约定：
  - `0`：所有被测光路 `valid == True`（或显式传入 `--allow-invalid` 用于生成含反例/报错演示的对比页）；
  - `1`：存在至少一条 `valid == False`（含 `ERROR`）的光路且未传 `--allow-invalid`；
  - `2`：命令行参数错误、找不到目标函数、Python 语法或文件读取错误。

---

## 9. 随附黄金测试集说明与 GPT 验收步骤

在 `<WORKSPACE>/` 下已经放好两份机器校验基线文件，用来直接检验你实现出来的第一层模拟器与渲染器：

1. **[optical_graph_fixtures.py](../../tests/optical_graph_fixtures.py)**：内置 `ALL_FIXTURES` 列表，共 **10 组真实光路**：
   - `q1_kepler_expander`：780 nm 3× 开普勒扩束（`50+150=200 mm`）进保偏光纤；
   - `q2_1x3_splitter`：532 nm 任意椭圆光纯化（`4%` 废光进光阱）+ 按 `split_reflect_ratio` 自动求解的一分三保偏分发；
   - `q3_double_pass_aom`：780 nm 椭圆光纯化带监测 PD 光阱 + 猫眼双通 `+220 MHz` AOM 复用；
   - `q4_dichroic_window_focus`：780（62.5 mm）+ 532（`HeightShift` 95.7→62.5 mm）双色合束 + `2%` 相机抽样 + `span` 自动反解 6 mm UVFS 窗前 `134.0 mm` 空气距离；
   - `q5_rb87_offset_sas`：780 nm 铷-87 移频泵浦–探测对射光谱与主光纤分配（并验证 `1.6 mm` 光斑过 `1.5 mm` AOM 触发 `tight_aperture` 预警但不阻塞）；
   - `q6_balanced_heterodyne`：1064 nm 双 AOM（`+80 / +75 MHz`）平衡外差干涉仪（验证两个 PD 均测出 `5.0 MHz` 拍频且相位差严格 `180°`）；
   - `q7_buggy_double_pass`：反例，同时存在透镜间距错为 `50 mm`（`collimation_error` + `severe_clipping`）、QWP `0°` 回击隔离器（`isolator_reverse_blocked`）、返回口错接 `p2` 致光纤无光（`terminal_no_light`）；
   - `q7_fixed_double_pass`：`q7` 彻底修好后的零警告版本；
   - `q8_vertical_down_atoms`：399 nm 先经 `HeightShift(mode="turn90")` 翻偏振（`P -> S`）、再转圆偏振 `LHC` 后经 `VerticalFold(direction="down")` 垂直向下跨 6 mm 窗片打腔内原子（验证 `board_cutout_required=True` 与 `101.92 mm` 预补偿焦距正中靶面）；
   - `q9_fold_hazard_and_leak_negative`：反例，同时验证波片后进 PBS 前误标 `can_fold=True`（`polarization_fold_hazard`）以及 `PBS.p2` 悬空漏光（`unterminated_beam`）。
2. **[optical-graph-expected.json](../../tests/optical-graph-expected.json)**：给出每一题终端功率、直径、偏振、移频、拍频相位差、双向链路标志、`board_cutout_required` 标志与诊断码的机器预期值。

### GPT 完成实现后必须跑通的验收步骤

1. 在 `<WORKSPACE>` 下运行：
   ```sh
   python3 tests/optical_graph_acceptance.py
   ```
   确认返回码 `0`，10/10 项测试全部通过，并输出 `<WORKSPACE>/results/optical-graph/acceptance.json`。
2. 运行批量画廊渲染命令：
   ```sh
   python3 scripts/optical_graph_render.py optical_graph_fixtures.py --all --allow-invalid \
     -o results/optical-graph/gallery.html \
     --svg-dir results/optical-graph/svg \
     --json results/optical-graph/summary.json
   ```
   确认生成交互式多标签页 `gallery.html` 与全部 10 份独立 `.svg` 矢量图，并在无头浏览器或解析检查中确认 `svg` 无重叠报错、`q7_buggy` 与 `q9` 在画面上亮红报错。
