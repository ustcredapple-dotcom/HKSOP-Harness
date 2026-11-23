# OpticalGraph v1.0 速查

端面到端面距离使用 mm，功率 mW，波长 nm，频移 MHz。

- `LaserSource(wavelength_nm: 'float', diameter_mm: 'float', pol: 'str' = 'P', pol_angle_deg: 'float' = None, height_mm: 'float' = None, power_mw: 'float' = 10.0, m2: 'float' = 1.0) -> None`
- `FiberSource(wavelength_nm: 'float', diameter_mm: 'float', pol: 'str' = 'P', mode: 'str' = 'SM_PM', height_mm: 'float' = None, power_mw: 'float' = 10.0, pol_angle_deg: 'float' = None) -> None`
- `FiberCoupler(mode: 'str' = 'SM_PM', design_diameter_mm: 'float' = None, required_pol: 'str' = 'P', steering_mirrors: 'int' = 2) -> None`
- `Photodiode(label: 'str' = '', bandwidth_mhz: 'float' = None) -> None`
- `Camera(label: 'str' = '') -> None`
- `TargetPlane(label: 'str' = '', target_waist_um: 'float' = None) -> None`
- `BeamDump(monitor_pd: 'bool' = False) -> None`
- `RetroMirror(aperture_inch: 'float' = 1.0, actuation: 'str' = 'manual') -> None`
- `Lens(f_mm: 'float', aperture_inch: 'float' = 1.0, kind: 'str' = 'singlet', convex_toward: 'str' = 'auto') -> None`
- `HalfWaveplate(aperture_inch=1.0, *, fast_axis_deg=None, target_pol=None, split_reflect_ratio=None, note='')`
- `QuarterWaveplate(aperture_inch=1.0, *, fast_axis_deg=None, target_pol=None, double_pass_flip=False, note='')`
- `DualWaveplate(aperture_inch=1.0, *, target_pol='P', qwp_deg=None, hwp_deg=None, note='')`
- `Aperture(diameter_mm: 'float') -> None`
- `Window(thickness_mm: 'float', material: 'str' = 'UVFS', refractive_index: 'float' = None, clear_aperture_mm: 'float' = 25.0) -> None`
- `CustomTwoPort(device_type: 'str', length_mm: 'float', clear_aperture_mm: 'float', params: 'dict' = None, custom_reason: 'str' = '') -> None`
- `Isolator(wavelength_nm: 'float', clear_aperture_mm: 'float' = 4.5, output_pol: 'str' = 'P') -> None`
- `AOM(rf_mhz: 'float', order: 'int' = 1, active_aperture_mm: 'float' = 1.5, zero_order_blocked: 'bool' = True) -> None`
- `PBS(aperture_inch: 'float' = 1.0) -> None`
- `NPBS(aperture_inch: 'float' = 1.0, reflect_ratio: 'float' = 0.5) -> None`
- `SamplerPlate(aperture_inch: 'float' = 1.0, reflect_ratio: 'float' = 0.02) -> None`
- `Dichroic(aperture_inch: 'float' = 1.0, pass_wavelengths_nm: 'list' = <factory>, reflect_wavelengths_nm: 'list' = <factory>) -> None`
- `HeightShift(in_height_mm: 'float', out_height_mm: 'float', mode: 'str' = 'straight', aperture_inch: 'float' = 1.0) -> None`
- `VerticalFold(direction: 'str' = 'down', aperture_inch: 'float' = 1.0) -> None`
- `SpatialFold(pitch_deg: 'float', yaw_deg: 'float' = 0.0, aperture_inch: 'float' = 1.0) -> None`

## 四口与返回光

透射 p1↔p3、p2↔p4，反射 p1↔p2、p3↔p4。双通臂只连接一次，端镜返回时回用同一条 link。对射支路从相反端口进入同一实体。多段约束可用 g.span 指定，废光接入 BeamDump。

## 六项体检

检查端口与终端闭合（unterminated_beam），分光频段与回光（unmapped_wavelength、isolator_reverse_blocked），偏振折转与保偏端口（polarization_fold_hazard、pm_pol_mismatch），孔径和高斯准直（collimation_error），锁距（span_distance_error），以及反向、拍频和功率闭合。每一段在 trace.beams 中可查起终点的复 q、2w、偏振、功率及频移。

## 保偏接口与验收

保偏出口从最后一个分束面起须有 QWP 与 HWP。入口先 QWP 消除残余椭偏，后 HWP 设第一分光比。PBS 透射直通纯 P 的级间可用单 HWP。反射、厚窗或声光级间优先双片。默认窄键 FC/APC；平端面约 4% 背反。反射支路目标 20 dB 需实测，30 dB 需清理或高消光比分束器。超过 1 W 核对石英波片及高损伤阈值光学元件。
