"""Golden fixture suite (10 circuits) for OpticalGraph v1.0 Layer-1 verification."""

from optical_graph import (
    AOM,
    BeamDump,
    Camera,
    CustomTwoPort,
    Dichroic,
    DualWaveplate,
    FiberCoupler,
    FiberSource,
    HalfWaveplate,
    HeightShift,
    Isolator,
    LaserSource,
    Lens,
    OpticalGraph,
    PBS,
    Photodiode,
    QuarterWaveplate,
    RetroMirror,
    SamplerPlate,
    TargetPlane,
    VerticalFold,
    Window,
)


def q1_kepler_expander() -> OpticalGraph:
    """780 nm 3x Keplerian beam expander (0.8 -> 2.4 mm) into SM-PM fiber."""
    g = OpticalGraph("q1-kepler-expander", default_plane_height_mm=62.5)
    g.add("LS", LaserSource(wavelength_nm=780.0, diameter_mm=0.8, pol="P", power_mw=10.0))
    g.add("ISO", Isolator(wavelength_nm=780.0, clear_aperture_mm=4.5, output_pol="P"))
    g.add("L1", Lens(f_mm=50.0, aperture_inch=1.0, kind="singlet", convex_toward="a"))
    g.add("L2", Lens(f_mm=150.0, aperture_inch=1.0, kind="singlet", convex_toward="b"))
    g.add("HWP", HalfWaveplate(aperture_inch=1.0, target_pol="P", note="PM axis trim"))
    g.add("FC", FiberCoupler(allow_uncompensated_pm=True, mode="SM_PM", design_diameter_mm=2.4, required_pol="P", steering_mirrors=2))

    g.link("LS.front", "ISO.a", min_mm=30.0, max_mm=150.0, can_fold=False)
    g.link("ISO.b", "L1.a", min_mm=30.0, max_mm=200.0, can_fold=True)
    g.link("L1.b", "L2.a", exact_mm=200.0, tol_mm=0.5, can_fold=False)
    g.link("L2.b", "HWP.a", min_mm=30.0, max_mm=250.0, can_fold=True)
    g.link("HWP.b", "FC.front", min_mm=40.0, max_mm=300.0, can_fold=True)
    return g


def q2_1x3_splitter() -> OpticalGraph:
    """532 nm 1x3 tunable PM fiber distribution with 4% purification dump."""
    g = OpticalGraph("q2-1x3-splitter", default_plane_height_mm=62.5)
    g.add("LS", LaserSource(wavelength_nm=532.0, diameter_mm=1.5, pol="elliptical", power_mw=100.0))
    g.add("DW", DualWaveplate(aperture_inch=1.0, target_pol="P"))
    g.add("H0", HalfWaveplate(aperture_inch=1.0, split_reflect_ratio=0.04, note="4% polarization purification tap"))
    g.add("P0", PBS(aperture_inch=1.0))
    g.add("BD0", BeamDump(monitor_pd=False))

    g.add("H1", HalfWaveplate(aperture_inch=1.0, split_reflect_ratio=0.50))
    g.add("P1", PBS(aperture_inch=1.0))
    g.add("HA", HalfWaveplate(aperture_inch=1.0, target_pol="P"))
    g.add("FC1", FiberCoupler(allow_uncompensated_pm=True, mode="SM_PM", design_diameter_mm=1.5, required_pol="P", steering_mirrors=2))

    g.add("H2", HalfWaveplate(aperture_inch=1.0, split_reflect_ratio=0.40, note="Input is S; reflects 40% of stage-2"))
    g.add("P2", PBS(aperture_inch=1.0))
    g.add("HB", HalfWaveplate(aperture_inch=1.0, target_pol="P"))
    g.add("FC2", FiberCoupler(allow_uncompensated_pm=True, mode="SM_PM", design_diameter_mm=1.5, required_pol="P", steering_mirrors=2))
    g.add("HC", HalfWaveplate(aperture_inch=1.0, target_pol="P"))
    g.add("FC3", FiberCoupler(allow_uncompensated_pm=True, mode="SM_PM", design_diameter_mm=1.5, required_pol="P", steering_mirrors=2))

    g.link("LS.front", "DW.a", min_mm=30.0, max_mm=120.0, can_fold=False)
    g.link("DW.b", "H0.a", min_mm=25.0, max_mm=80.0, can_fold=False)
    g.link("H0.b", "P0.p1", min_mm=25.0, max_mm=80.0, can_fold=False)
    g.link("P0.p2", "BD0.front", min_mm=25.0, max_mm=100.0, can_fold=False)

    g.link("P0.p3", "H1.a", min_mm=30.0, max_mm=150.0, can_fold=True)
    g.link("H1.b", "P1.p1", min_mm=25.0, max_mm=80.0, can_fold=False)
    g.link("P1.p3", "HA.a", min_mm=25.0, max_mm=100.0, can_fold=True)
    g.link("HA.b", "FC1.front", min_mm=40.0, max_mm=300.0, can_fold=True)

    g.link("P1.p2", "H2.a", min_mm=25.0, max_mm=120.0, can_fold=True)
    g.link("H2.b", "P2.p1", min_mm=25.0, max_mm=80.0, can_fold=False)
    g.link("P2.p3", "HB.a", min_mm=25.0, max_mm=100.0, can_fold=True)
    g.link("HB.b", "FC2.front", min_mm=40.0, max_mm=300.0, can_fold=True)
    g.link("P2.p2", "HC.a", min_mm=25.0, max_mm=100.0, can_fold=True)
    g.link("HC.b", "FC3.front", min_mm=40.0, max_mm=300.0, can_fold=True)
    return g


def q3_double_pass_aom() -> OpticalGraph:
    """780 nm elliptical source -> 5% monitor PD dump -> cat-eye +220 MHz double-pass AOM -> SM-PM fiber."""
    g = OpticalGraph("q3-double-pass-aom", default_plane_height_mm=62.5)
    g.add("LS", LaserSource(wavelength_nm=780.0, diameter_mm=1.2, pol="elliptical", power_mw=50.0))
    g.add("DW", DualWaveplate(aperture_inch=1.0, target_pol="P"))
    g.add("H0", HalfWaveplate(aperture_inch=1.0, split_reflect_ratio=0.05, note="5% monitor tap"))
    g.add("P0", PBS(aperture_inch=1.0))
    g.add("BD0", BeamDump(monitor_pd=True))

    g.add("P1", PBS(aperture_inch=1.0))
    g.add("AOM", AOM(rf_mhz=110.0, order=+1, active_aperture_mm=2.0, zero_order_blocked=True))
    g.add("L", Lens(f_mm=100.0, aperture_inch=1.0, kind="singlet", convex_toward="a"))
    g.add("QWP", QuarterWaveplate(aperture_inch=1.0, fast_axis_deg=45.0))
    g.add("RM", RetroMirror(aperture_inch=1.0))
    g.add("HWP", HalfWaveplate(aperture_inch=1.0, target_pol="P"))
    g.add("FC", FiberCoupler(allow_uncompensated_pm=True, mode="SM_PM", design_diameter_mm=1.2, required_pol="P", steering_mirrors=2))

    g.link("LS.front", "DW.a", min_mm=30.0, max_mm=120.0, can_fold=False)
    g.link("DW.b", "H0.a", min_mm=25.0, max_mm=80.0, can_fold=False)
    g.link("H0.b", "P0.p1", min_mm=25.0, max_mm=80.0, can_fold=False)
    g.link("P0.p2", "BD0.front", min_mm=25.0, max_mm=100.0, can_fold=False)
    g.link("P0.p3", "P1.p1", min_mm=30.0, max_mm=150.0, can_fold=True)

    g.link("P1.p3", "AOM.a", min_mm=40.0, max_mm=120.0, can_fold=False)
    g.link("AOM.b", "L.a", exact_mm=100.0, tol_mm=0.5, can_fold=False)
    g.link("L.b", "QWP.a", min_mm=20.0, max_mm=60.0, can_fold=False)
    g.link("QWP.b", "RM.front", min_mm=20.0, max_mm=60.0, can_fold=False)
    g.span("L.b", "RM.front", exact_mm=100.0, tol_mm=0.5, note="Cat-eye back focal plane")

    g.link("P1.p4", "HWP.a", min_mm=30.0, max_mm=150.0, can_fold=True)
    g.link("HWP.b", "FC.front", min_mm=40.0, max_mm=300.0, can_fold=True)
    return g


def q4_dichroic_window_focus() -> OpticalGraph:
    """780 nm (62.5 mm) + 532 nm (95.7 -> 62.5 mm HeightShift) dichroic combine + 2% sampler + UVFS focus."""
    g = OpticalGraph("q4-dichroic-window-focus", default_plane_height_mm=62.5)
    g.add("SRC_A", FiberSource(wavelength_nm=780.0, diameter_mm=2.0, pol="P", mode="SM_PM", height_mm=62.5, power_mw=20.0))
    g.add("SRC_B", LaserSource(wavelength_nm=532.0, diameter_mm=2.0, pol="S", height_mm=95.7, power_mw=10.0))
    g.add("HS", HeightShift(in_height_mm=95.7, out_height_mm=62.5, mode="straight", aperture_inch=1.0))
    g.add("D", Dichroic(aperture_inch=1.0, pass_wavelengths_nm=[780.0], reflect_wavelengths_nm=[532.0]))
    g.add("BD_D", BeamDump(monitor_pd=False))
    g.add("SP", SamplerPlate(aperture_inch=1.0, reflect_ratio=0.02))
    g.add("CAM", Camera(label="coaxial-overlap"))
    g.add("L", Lens(f_mm=200.0, aperture_inch=1.0, kind="achromat", convex_toward="a"))
    g.add("W", Window(thickness_mm=6.0, material="UVFS", clear_aperture_mm=25.0))
    g.add("T", TargetPlane(label="common-focus"))

    g.link("SRC_A.front", "D.p1", min_mm=30.0, max_mm=200.0, can_fold=True)
    g.link("SRC_B.front", "HS.a", min_mm=30.0, max_mm=120.0, can_fold=False)
    g.link("HS.b", "D.p4", min_mm=30.0, max_mm=200.0, can_fold=True)
    g.link("D.p2", "BD_D.front", min_mm=25.0, max_mm=100.0, can_fold=False)

    g.link("D.p3", "SP.p1", min_mm=30.0, max_mm=200.0, can_fold=True)
    g.link("SP.p2", "CAM.front", min_mm=30.0, max_mm=150.0, can_fold=True)
    g.link("SP.p3", "L.a", min_mm=30.0, max_mm=150.0, can_fold=True)

    g.link("L.b", "W.a", min_mm=100.0, max_mm=160.0, can_fold=False)
    g.link("W.b", "T.front", exact_mm=60.0, tol_mm=0.5, can_fold=False)
    g.span("L.b", "T.front", exact_mm=200.0, tol_mm=0.5, note="134 mm air + 6 mm UVFS + 60 mm air")
    return g


def q5_rb87_offset_sas() -> OpticalGraph:
    """780 nm Rb87 counter-propagating offset SAS + SM-PM main output (anonymized N1..N13)."""
    g = OpticalGraph("q5-rb87-offset-sas", default_plane_height_mm=62.5)
    g.add("N1", LaserSource(wavelength_nm=780.0, diameter_mm=1.6, pol="P", power_mw=50.0))
    g.add("N2", Isolator(wavelength_nm=780.0, output_pol="P"))
    g.add("N3", HalfWaveplate(aperture_inch=1.0, fast_axis_deg=22.5))
    g.add("N4", PBS(aperture_inch=1.0))

    g.add("N5", HalfWaveplate(aperture_inch=1.0, fast_axis_deg=0.0))
    g.add("N6", FiberCoupler(allow_uncompensated_pm=True, mode="SM_PM", design_diameter_mm=1.6, required_pol="P", steering_mirrors=2))

    g.add("N7", HalfWaveplate(aperture_inch=1.0, fast_axis_deg=22.5))
    g.add("N8", PBS(aperture_inch=1.0))
    g.add("N9", CustomTwoPort(
        device_type="rb87_vapor_cell",
        length_mm=75.0,
        clear_aperture_mm=20.0,
        params={"temperature_c": 25.0},
        custom_reason="Rb87 vapor cell",
    ))
    g.add("N10", PBS(aperture_inch=1.0))
    g.add("N11", Photodiode(label="signal"))
    g.add("N12", AOM(rf_mhz=80.0, order=+1, active_aperture_mm=1.5, zero_order_blocked=True))
    g.add("N13", BeamDump(monitor_pd=False))

    g.link("N1.front", "N2.a", min_mm=30.0, max_mm=120.0, can_fold=False)
    g.link("N2.b", "N3.a", min_mm=25.0, max_mm=100.0, can_fold=False)
    g.link("N3.b", "N4.p1", min_mm=25.0, max_mm=100.0, can_fold=False)

    g.link("N4.p3", "N5.a", min_mm=30.0, max_mm=200.0, can_fold=True)
    g.link("N5.b", "N6.front", min_mm=40.0, max_mm=350.0, can_fold=True)

    g.link("N4.p2", "N7.a", min_mm=25.0, max_mm=150.0, can_fold=True)
    g.link("N7.b", "N8.p1", min_mm=25.0, max_mm=150.0, can_fold=False)

    g.link("N8.p3", "N9.a", min_mm=30.0, max_mm=150.0, can_fold=False)
    g.link("N9.b", "N10.p1", min_mm=30.0, max_mm=150.0, can_fold=False)
    g.link("N10.p3", "N11.front", min_mm=30.0, max_mm=150.0, can_fold=True)

    g.link("N8.p2", "N12.a", min_mm=40.0, max_mm=200.0, can_fold=True)
    g.link("N12.b", "N10.p2", min_mm=40.0, max_mm=250.0, can_fold=True)
    g.link("N8.p4", "N13.front", min_mm=25.0, max_mm=100.0, can_fold=False)
    return g


def q6_balanced_heterodyne() -> OpticalGraph:
    """1064 nm dual-AOM (+80/+75 MHz) Mach-Zehnder balanced 5 MHz heterodyne detector."""
    g = OpticalGraph("q6-balanced-heterodyne", default_plane_height_mm=62.5)
    g.add("N1", FiberSource(wavelength_nm=1064.0, diameter_mm=1.4, pol="P", power_mw=20.0))
    g.add("N2", HalfWaveplate(aperture_inch=1.0, fast_axis_deg=22.5))
    g.add("N3", PBS(aperture_inch=1.0))

    g.add("N4", AOM(rf_mhz=80.0, order=+1, active_aperture_mm=1.5, zero_order_blocked=True))
    g.add("N5", AOM(rf_mhz=75.0, order=+1, active_aperture_mm=1.5, zero_order_blocked=True))
    g.add("N6", PBS(aperture_inch=1.0))

    g.add("N7", HalfWaveplate(aperture_inch=1.0, fast_axis_deg=22.5))
    g.add("N8", PBS(aperture_inch=1.0))
    g.add("N9", Photodiode(label="ch_a", bandwidth_mhz=50.0))
    g.add("N10", Photodiode(label="ch_b", bandwidth_mhz=50.0))

    g.link("N1.front", "N2.a", min_mm=25.0, max_mm=120.0, can_fold=False)
    g.link("N2.b", "N3.p1", min_mm=25.0, max_mm=120.0, can_fold=False)

    g.link("N3.p3", "N4.a", min_mm=30.0, max_mm=150.0, can_fold=True)
    g.link("N4.b", "N6.p1", min_mm=30.0, max_mm=150.0, can_fold=True)

    g.link("N3.p2", "N5.a", min_mm=30.0, max_mm=150.0, can_fold=True)
    g.link("N5.b", "N6.p4", min_mm=30.0, max_mm=150.0, can_fold=True)

    g.span("N3.p3", "N6.p1", exact_mm=250.0, tol_mm=1.0)
    g.span("N3.p2", "N6.p4", exact_mm=250.0, tol_mm=1.0)

    g.link("N6.p3", "N7.a", min_mm=25.0, max_mm=120.0, can_fold=False)
    g.link("N7.b", "N8.p1", min_mm=25.0, max_mm=120.0, can_fold=False)
    g.link("N8.p3", "N9.front", min_mm=25.0, max_mm=150.0, can_fold=True)
    g.link("N8.p2", "N10.front", min_mm=25.0, max_mm=150.0, can_fold=True)
    return g


def q7_buggy_double_pass() -> OpticalGraph:
    """Negative fixture: wrong lens separation (50 mm), 0 deg QWP, wrong PBS port p2, unrotated HWP."""
    g = OpticalGraph("q7-buggy-double-pass", default_plane_height_mm=62.5)
    g.add("N1", LaserSource(wavelength_nm=780.0, diameter_mm=0.6, pol="P", power_mw=10.0))
    g.add("N2", Isolator(wavelength_nm=780.0, output_pol="P"))
    g.add("N3", Lens(f_mm=50.0, aperture_inch=1.0))
    g.add("N4", Lens(f_mm=100.0, aperture_inch=1.0))
    g.add("N5", PBS(aperture_inch=1.0))

    g.add("N6", AOM(rf_mhz=100.0, order=+1, active_aperture_mm=1.5, zero_order_blocked=True))
    g.add("N7", Lens(f_mm=100.0, aperture_inch=1.0))
    g.add("N8", QuarterWaveplate(aperture_inch=1.0, fast_axis_deg=0.0))
    g.add("N9", RetroMirror(aperture_inch=1.0))

    g.add("N10", HalfWaveplate(aperture_inch=1.0, fast_axis_deg=0.0))
    g.add("N11", FiberCoupler(allow_uncompensated_pm=True, mode="SM_PM", design_diameter_mm=1.2, required_pol="P", steering_mirrors=2))

    g.link("N1.front", "N2.a", min_mm=30.0, max_mm=120.0, can_fold=False)
    g.link("N2.b", "N3.a", min_mm=30.0, max_mm=150.0, can_fold=True)
    g.link("N3.b", "N4.a", exact_mm=50.0, tol_mm=0.5, can_fold=False)
    g.link("N4.b", "N5.p1", min_mm=30.0, max_mm=200.0, can_fold=True)

    g.link("N5.p3", "N6.a", min_mm=40.0, max_mm=150.0, can_fold=False)
    g.link("N6.b", "N7.a", exact_mm=100.0, tol_mm=0.5, can_fold=False)
    g.link("N7.b", "N8.a", min_mm=15.0, max_mm=70.0, can_fold=False)
    g.link("N8.b", "N9.front", min_mm=15.0, max_mm=70.0, can_fold=False)
    g.span("N7.b", "N9.front", exact_mm=100.0, tol_mm=0.5)

    g.link("N5.p2", "N10.a", min_mm=30.0, max_mm=150.0, can_fold=True)
    g.link("N10.b", "N11.front", min_mm=40.0, max_mm=300.0, can_fold=True)
    return g


def q7_fixed_double_pass() -> OpticalGraph:
    """Repaired q7 circuit: 150 mm Keplerian, 45 deg QWP, N5.p4 return port, 45 deg HWP, 2 mm AOM aperture."""
    g = OpticalGraph("q7-fixed-double-pass", default_plane_height_mm=62.5)
    g.add("N1", LaserSource(wavelength_nm=780.0, diameter_mm=0.6, pol="P", power_mw=10.0))
    g.add("N2", Isolator(wavelength_nm=780.0, output_pol="P"))
    g.add("N3", Lens(f_mm=50.0, aperture_inch=1.0, kind="singlet", convex_toward="a"))
    g.add("N4", Lens(f_mm=100.0, aperture_inch=1.0, kind="singlet", convex_toward="b"))
    g.add("N5", PBS(aperture_inch=1.0))

    g.add("N6", AOM(rf_mhz=100.0, order=+1, active_aperture_mm=2.0, zero_order_blocked=True))
    g.add("N7", Lens(f_mm=100.0, aperture_inch=1.0, kind="singlet", convex_toward="a"))
    g.add("N8", QuarterWaveplate(aperture_inch=1.0, fast_axis_deg=45.0))
    g.add("N9", RetroMirror(aperture_inch=1.0))

    g.add("N10", HalfWaveplate(aperture_inch=1.0, fast_axis_deg=45.0))
    g.add("N11", FiberCoupler(allow_uncompensated_pm=True, mode="SM_PM", design_diameter_mm=1.2, required_pol="P", steering_mirrors=2))

    g.link("N1.front", "N2.a", min_mm=30.0, max_mm=120.0, can_fold=False)
    g.link("N2.b", "N3.a", min_mm=30.0, max_mm=150.0, can_fold=True)
    g.link("N3.b", "N4.a", exact_mm=150.0, tol_mm=0.5, can_fold=False)
    g.link("N4.b", "N5.p1", min_mm=30.0, max_mm=200.0, can_fold=True)

    g.link("N5.p3", "N6.a", min_mm=40.0, max_mm=150.0, can_fold=False)
    g.link("N6.b", "N7.a", exact_mm=100.0, tol_mm=0.5, can_fold=False)
    g.link("N7.b", "N8.a", min_mm=15.0, max_mm=70.0, can_fold=False)
    g.link("N8.b", "N9.front", min_mm=15.0, max_mm=70.0, can_fold=False)
    g.span("N7.b", "N9.front", exact_mm=100.0, tol_mm=0.5)

    g.link("N5.p4", "N10.a", min_mm=30.0, max_mm=150.0, can_fold=True)
    g.link("N10.b", "N11.front", min_mm=40.0, max_mm=300.0, can_fold=True)
    return g


def q8_vertical_down_atoms() -> OpticalGraph:
    """399 nm 3D out-of-plane path: turn90 HeightShift (P->S) -> LHC QWP -> VerticalFold down -> UVFS window -> atoms."""
    g = OpticalGraph("q8-vertical-down-atoms", default_plane_height_mm=62.5)
    g.add("Src", FiberSource(wavelength_nm=399.0, diameter_mm=2.0, pol="P", mode="SM_PM", height_mm=62.5, power_mw=15.0))
    g.add("HS", HeightShift(in_height_mm=62.5, out_height_mm=212.5, mode="turn90", aperture_inch=1.0))
    g.add("QWP", QuarterWaveplate(aperture_inch=1.0, target_pol="LHC"))
    g.add("M_down", VerticalFold(direction="down", aperture_inch=2.0))
    g.add("Obj", Lens(f_mm=100.0, aperture_inch=2.0, kind="achromat", convex_toward="a"))
    g.add("Win", Window(thickness_mm=6.0, material="UVFS", clear_aperture_mm=35.0))
    g.add("Atoms", TargetPlane(label="Yb-atoms"))

    g.link("Src.front", "HS.a", min_mm=30.0, max_mm=120.0, can_fold=True)
    g.link("HS.b", "QWP.a", min_mm=30.0, max_mm=120.0, can_fold=False)
    g.link("QWP.b", "M_down.a", min_mm=25.0, max_mm=80.0, can_fold=False)
    g.link("M_down.b", "Obj.a", min_mm=30.0, max_mm=150.0, can_fold=False)
    g.link("Obj.b", "Win.a", min_mm=30.0, max_mm=80.0, can_fold=False)
    g.link("Win.b", "Atoms.front", exact_mm=45.0, tol_mm=0.5, can_fold=False)
    g.span("Obj.b", "Atoms.front", exact_mm=101.92, tol_mm=0.5, note="Compensates +1.92 mm UVFS shift at 399 nm")
    return g


def q9_fold_hazard_and_leak_negative() -> OpticalGraph:
    """Negative fixture: mixed-polarization fold hazard + dangling PBS.p2 waste output."""
    g = OpticalGraph("q9-fold-hazard-and-leak-negative", default_plane_height_mm=62.5)
    g.add("LS", LaserSource(wavelength_nm=780.0, diameter_mm=1.0, pol="P", power_mw=10.0))
    g.add("HWP", HalfWaveplate(aperture_inch=1.0, fast_axis_deg=22.5))
    g.add("PBS", PBS(aperture_inch=1.0))
    g.add("PD", Photodiode(label="transmitted"))

    g.link("LS.front", "HWP.a", min_mm=25.0, max_mm=100.0, can_fold=False)
    g.link("HWP.b", "PBS.p1", min_mm=25.0, max_mm=100.0, can_fold=True)
    g.link("PBS.p3", "PD.front", min_mm=25.0, max_mm=100.0, can_fold=True)
    return g


ALL_FIXTURES = [
    q1_kepler_expander,
    q2_1x3_splitter,
    q3_double_pass_aom,
    q4_dichroic_window_focus,
    q5_rb87_offset_sas,
    q6_balanced_heterodyne,
    q7_buggy_double_pass,
    q7_fixed_double_pass,
    q8_vertical_down_atoms,
    q9_fold_hazard_and_leak_negative,
]
