// Native-effect setups. Edit paths and parameters, then run in AE.
var CLIP_PATH = ""; // Empty uses input.mp4.
var DEPTH_FIRST_PNG = ""; // Empty uses demo/xr/depth/depth_00000.png.
var FOG_COLOR = [0.12, 0.55, 0.72];
var FOG_OPACITY = 55;
var BLUR_RADIUS = 12;
var PARALLAX_AMOUNT = 12;

(function () {
    var script = new File($.fileName), root = script.parent.parent;
    var report = new File(script.parent.fsName + "/depth_looks_report.txt"), started = false;
    function effect(layer, name) {
        var e = layer.property("ADBE Effect Parade").addProperty(name);
        if (!e) { throw new Error("Effect unavailable: " + name); }
        return e;
    }
    function setIfPresent(e, names, value) {
        for (var i = 0; i < names.length; i++) {
            var p = e.property(names[i]);
            if (p) { try { p.setValue(value); return true; } catch (ignored) { /* Try the next name. */ } }
        }
        return false;
    }
    function makeComp(name, footage) {
        return app.project.items.addComp(name, footage.width, footage.height, footage.pixelAspect, footage.duration, footage.frameRate);
    }
    try {
        var clipFile = new File(CLIP_PATH || "input.mp4");
        var depthFile = new File(DEPTH_FIRST_PNG || (root.fsName + "/demo/xr/depth/depth_00000.png"));
        if (!clipFile.exists || !depthFile.exists) { throw new Error("Clip or depth sequence missing"); }
        app.beginUndoGroup("Build AID depth looks"); started = true;
        var clip = app.project.importFile(new ImportOptions(clipFile));
        var options = new ImportOptions(depthFile); options.sequence = true; options.forceAlphabetical = true;
        var depth = app.project.importFile(options);
        depth.mainSource.conformFrameRate = clip.frameRate;
        var fogComp = makeComp("AID depth fog", clip);
        fogComp.layers.add(clip).name = "Original clip";
        var solid = fogComp.layers.addSolid(FOG_COLOR, "Fog colour", clip.width, clip.height, 1, clip.duration);
        solid.property("ADBE Transform Group").property("ADBE Opacity").setValue(FOG_OPACITY);
        var fogMatte = fogComp.layers.add(depth); fogMatte.name = "Depth matte / far white";
        if (solid.setTrackMatte) { solid.setTrackMatte(fogMatte, TrackMatteType.LUMA_INVERTED); }
        else { solid.trackMatteType = TrackMatteType.LUMA_INVERTED; }

        var blurComp = makeComp("AID depth blur", clip);
        var blurLayer = blurComp.layers.add(clip); blurLayer.name = "RGB / Camera Lens Blur";
        var blurDepth = blurComp.layers.add(depth); blurDepth.name = "Depth map / hide after linking";
        var blur = effect(blurLayer, "ADBE Camera Lens Blur");
        setIfPresent(blur, ["Blur Radius", "ADBE Camera Lens Blur-0002"], BLUR_RADIUS);
        if (!setIfPresent(blur, ["Blur Map", "ADBE Camera Lens Blur-0004"], blurDepth.index)) {
            // AE versions differ in this parameter's display name. Report the manual link.
        }
        blurDepth.enabled = false;

        var parallaxComp = makeComp("AID depth parallax", clip);
        var parallaxLayer = parallaxComp.layers.add(clip); parallaxLayer.name = "RGB / Displacement Map";
        var parallaxDepth = parallaxComp.layers.add(depth); parallaxDepth.name = "Depth displacement source";
        var displacement = effect(parallaxLayer, "ADBE Displacement Map");
        setIfPresent(displacement, ["Displacement Map Layer", "ADBE Displacement Map-0001"], parallaxDepth.index);
        setIfPresent(displacement, ["Max Horizontal Displacement", "ADBE Displacement Map-0003"], PARALLAX_AMOUNT);
        setIfPresent(displacement, ["Max Vertical Displacement", "ADBE Displacement Map-0005"], PARALLAX_AMOUNT * .35);
        parallaxDepth.enabled = false;

        var sliceComp = makeComp("AID depth slice reveal", clip);
        var reveal = sliceComp.layers.add(clip); reveal.name = "RGB / revealed by depth";
        var sliceDepth = sliceComp.layers.add(depth); sliceDepth.name = "Depth slice matte";
        var key = effect(sliceDepth, "ADBE Luma Key");
        var threshold = key.property("Threshold");
        if (threshold) {
            try {
                threshold.setValueAtTime(0, 255);
                threshold.setValueAtTime(clip.duration * .9, 0);
            } catch (keyRange) { /* Tune manually if the host uses a different range. */ }
        }
        if (reveal.setTrackMatte) { reveal.setTrackMatte(sliceDepth, TrackMatteType.ALPHA); }
        else { reveal.trackMatteType = TrackMatteType.ALPHA; }
        report.open("w");
        report.writeln("OK: Created fog, blur, parallax and slice comps. Check Camera Lens Blur blur-map and Displacement Map source selectors in this AE version; set slice Luma Key threshold for the desired depth band.");
        report.close();
    } catch (e) {
        report.open("w"); report.writeln("ERROR: " + e.toString() + " at line " + e.line); report.close();
    } finally { if (started) { app.endUndoGroup(); } }
}());
