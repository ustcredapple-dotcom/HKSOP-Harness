# 光束管与三维坐标

采用实际 STEP 固体和按波长、光斑与 q 传播的保守分段光束管。默认检查外包络 1.5 倍 1/e² 半径。校验同一冻结工程的 SHA256 和原生追迹；逐段计算相邻支架、板面与孔壁的距离。光学交互面在有明确启动/接收光口的有限范围内按有效口径处理。缺少空间登记、重选支柱后的几何或处理复合段所需数据时返回待补证。定位矩阵按源到套件、套件到载板、载板到世界的顺序复合。

[保留装配层级与坐标实测依据](design-guides/zzlab-optics-json-to-3d/zzlab-optics-json-to-3d.md)

## 补充实测几何

换柱、非零滑台位移和未登记的坐标系可随 `--geometry geometry.json` 提供。根对象以 `projectSha256` 锁定当前工程。`instances` 按实例 ID 索引，每条记录给出实际 STEP 文件 `step`、`sha256`、毫米制刚体矩阵 `sourceToKit3x4` 和定位依据 `datumEvidence`。异形主板用 `mainBoard`、`sourceToBoard3x4` 和相同的资产凭据。穿板孔用 `cutouts` 列出板坐标 `center` 与 `diameterMm`。登记实体已有的孔直接随 STEP 验证。

透光介质按实际叶件的 `index` 和 `name` 唯一指定。每个 `transmissiveOpticalLeaves` 条目都需要源 CAD 坐标系中的 `centerSourceMm`、`normalSourceXYZ`、`clearRadiusMm`、`halfThicknessMm`。仅在对应光学交互端点且整个高斯光束管落在已测有效口径时允许穿过。支架、滑台、立柱与板材逐一参与实体距离计算。

`spatialSegments` 可追加已确认的板外光段。每条带有唯一 `id`、端点身份 `source`、`hit`、毫米世界坐标 `a`、`b`、`rangeMm`、`wavelengthNm`、`m2`、折射率 `index` 与子午、弧矢两个复 q 数组 `q`、`qSagittal`。退出码 0 为通过，1 为光束管干涉，2 为占位或证据不全。加工包会核对三维回执中总装和板件 STEP 的 SHA256。
