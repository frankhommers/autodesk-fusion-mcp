"""
WavyPlate  –  960 × 275 × 30 mm
Autodesk Fusion 360 Python Script

Çalıştırmak için:
  Fusion 360 → Shift+S → Scripts sekmesi → '+' → bu dosyayı seç → Run
"""

import adsk.core, adsk.fusion, math, traceback

def run(context):
    app = adsk.core.Application.get()
    ui  = app.userInterface

    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        root   = design.rootComponent
        feats  = root.features
        skts   = root.sketches

        def c(mm): return mm / 10.0   # mm → cm  (Fusion iç birimi cm)

        # ═══════════════════════════════════════════════════════════
        #  PARAMETRELER
        # ═══════════════════════════════════════════════════════════
        L, W, H = 960, 275, 30   # uzunluk, genişlik, yükseklik (mm)

        # Kenar dalgaları
        n_lobes = 5              # lob sayısı (her uzun kenarda)
        e_amp   = 18             # dalga genliği (mm)
        N       = 80             # spline nokta yoğunluğu

        # Üst yüzey kanalları
        n_ch    = 18             # kanal sayısı
        ch_amp  = 12             # kanal dalga genliği (mm)
        ch_cyc  = 2              # kanal başına dalga periyodu
        ch_w    = 2.5            # kanal genişliği (mm)
        ch_d    = 3.0            # kanal derinliği (mm)
        Np      = 60             # kanal spline nokta yoğunluğu

        # Delikler
        h_dia   = 4.0            # çap (mm)
        h_rows  = [W/4, W/2, 3*W/4]  # Y konumları (3 sıra)
        h_cols  = 24             # sütun sayısı
        h_sp    = L / (h_cols + 1)

        # ═══════════════════════════════════════════════════════════
        #  1. ANA GÖVDE  –  Dalgalı kenarlı kapalı profil
        # ═══════════════════════════════════════════════════════════
        sk0 = skts.add(root.xYConstructionPlane)
        sp0 = sk0.sketchCurves.sketchFittedSplines
        ln0 = sk0.sketchCurves.sketchLines

        # Alt kenar spline:  y = e_amp·sin(2π·n·t),  x: 0→L
        pb = adsk.core.ObjectCollection.create()
        for i in range(N + 1):
            t = i / N
            pb.add(adsk.core.Point3D.create(
                c(t * L),
                c(e_amp * math.sin(2 * math.pi * n_lobes * t)),
                0))
        sp0.add(pb)

        # Üst kenar spline:  y = W + e_amp·sin(2π·n·t+π),  x: L→0 (ters yön)
        pt = adsk.core.ObjectCollection.create()
        for i in range(N + 1):
            t = (N - i) / N
            pt.add(adsk.core.Point3D.create(
                c(t * L),
                c(W + e_amp * math.sin(2 * math.pi * n_lobes * t + math.pi)),
                0))
        sp0.add(pt)

        # Kısa kenar çizgileri  (spline uçları: sol=(0,0)/(0,W), sağ=(L,0)/(L,W))
        ln0.addByTwoPoints(
            adsk.core.Point3D.create(c(L), c(0), 0),
            adsk.core.Point3D.create(c(L), c(W), 0))
        ln0.addByTwoPoints(
            adsk.core.Point3D.create(0, c(W), 0),
            adsk.core.Point3D.create(0, c(0), 0))

        prof0 = sk0.profiles.item(0)
        ei0   = feats.extrudeFeatures.createInput(
            prof0, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        ei0.setDistanceExtent(False, adsk.core.ValueInput.createByReal(c(H)))
        base  = feats.extrudeFeatures.add(ei0)
        base.bodies.item(0).name = "WavyPlate"

        # ═══════════════════════════════════════════════════════════
        #  2. DALGALI KANALLAR  –  Üst yüzeyden aşağıya keser
        # ═══════════════════════════════════════════════════════════
        top_pi = root.constructionPlanes.createInput()
        top_pi.setByOffset(
            root.xYConstructionPlane,
            adsk.core.ValueInput.createByReal(c(H)))
        top_pl = root.constructionPlanes.add(top_pi)

        sk1    = skts.add(top_pl)
        sp1    = sk1.sketchCurves.sketchFittedSplines
        ch_gap = L / (n_ch + 1)

        for i in range(n_ch):
            xc  = ch_gap * (i + 1)
            pts = adsk.core.ObjectCollection.create()

            # Sol kenar  (y: 0→W, artan)
            for j in range(Np + 1):
                t = j / Np
                pts.add(adsk.core.Point3D.create(
                    c(xc + ch_amp * math.sin(2 * math.pi * ch_cyc * t) - ch_w / 2),
                    c(t * W),
                    0))

            # Sağ kenar  (y: W→0, azalan — kapalı döngüyü tamamlar)
            for j in range(Np + 1):
                t = (Np - j) / Np
                pts.add(adsk.core.Point3D.create(
                    c(xc + ch_amp * math.sin(2 * math.pi * ch_cyc * t) + ch_w / 2),
                    c(t * W),
                    0))

            sp1.add(pts, True)   # isClosed=True

        n_p1 = sk1.profiles.count
        if n_p1 > 0:
            pc1 = adsk.core.ObjectCollection.create()
            for k in range(n_p1):
                pc1.add(sk1.profiles.item(k))
            ci1 = feats.extrudeFeatures.createInput(
                pc1, adsk.fusion.FeatureOperations.CutFeatureOperation)
            dd  = adsk.fusion.DistanceExtentDefinition.create(
                adsk.core.ValueInput.createByReal(c(ch_d)))
            ci1.setOneSideExtent(dd, adsk.fusion.ExtentDirections.NegativeExtentDirection)
            feats.extrudeFeatures.add(ci1)

        # ═══════════════════════════════════════════════════════════
        #  3. DELİKLER  –  Üst yüzeyden aşağıya geçer
        # ═══════════════════════════════════════════════════════════
        sk2 = skts.add(top_pl)
        ci2 = sk2.sketchCurves.sketchCircles

        for hy in h_rows:
            for col in range(h_cols):
                hx = h_sp * (col + 1)
                ci2.addByCenterRadius(
                    adsk.core.Point3D.create(c(hx), c(hy), 0),
                    c(h_dia / 2))

        n_p2 = sk2.profiles.count
        if n_p2 > 0:
            pc2 = adsk.core.ObjectCollection.create()
            for k in range(n_p2):
                pc2.add(sk2.profiles.item(k))
            hi = feats.extrudeFeatures.createInput(
                pc2, adsk.fusion.FeatureOperations.CutFeatureOperation)
            hi.setAllExtent(adsk.fusion.ExtentDirections.NegativeExtentDirection)
            feats.extrudeFeatures.add(hi)

        ui.messageBox(
            "✓  WavyPlate  960 × 275 × 30 mm  oluşturuldu!\n\n"
            f"  • Kenar dalgaları : {n_lobes} lob, ±{e_amp} mm\n"
            f"  • Üst kanallar    : {n_ch} adet, {ch_d} mm derinlik\n"
            f"  • Delikler        : {len(h_rows) * h_cols} adet, Ø{h_dia} mm")

    except Exception:
        if ui:
            ui.messageBox(f"Hata:\n{traceback.format_exc()}")
