// Built-in AE effects only. Edit the source path before running.
var HALFTONE_CLIP_PATH = "input.mp4";
var DOT_SIZE = 8;
var NOISE_PERCENT = 6;

(function () {
    var report = new File(File($.fileName).parent.fsName + "/halftone_report.txt"), started = false;
    try {
        var source = new File(HALFTONE_CLIP_PATH);
        if (!source.exists) { throw new Error("Source clip missing"); }
        app.beginUndoGroup("Build AID halftone"); started = true;
        var clip = app.project.importFile(new ImportOptions(source));
        var comp = app.project.items.addComp("AID halftone", clip.width, clip.height, clip.pixelAspect, clip.duration, clip.frameRate);
        var layer = comp.layers.add(clip); layer.name = "Halftone / editable native effects";
        var fx = layer.property("ADBE Effect Parade");
        var tint = fx.addProperty("ADBE Tint");
        var mosaic = fx.addProperty("ADBE Mosaic");
        // Horizontal/vertical block counts. Pixel cells stay roughly square.
        mosaic.property(1).setValue(Math.max(2, Math.round(clip.width / DOT_SIZE)));
        mosaic.property(2).setValue(Math.max(2, Math.round(clip.height / DOT_SIZE)));
        var noise = fx.addProperty("ADBE Noise");
        noise.property(1).setValue(NOISE_PERCENT);
        var dots = null;
        try { dots = fx.addProperty("CC Ball Action"); } catch (missingDots) { /* Mosaic remains usable. */ }
        if (dots) { layer.name = "Halftone / Tint + Mosaic + Noise + CC Ball Action"; }
        report.open("w"); report.writeln("OK: " + comp.name + (dots ? ". Tune CC Ball Action Ball Size, Grid Spacing and Scatter for dot density." : ". CC Ball Action unavailable; Mosaic + Noise provides a block dither look.")); report.close();
    } catch (e) {
        report.open("w"); report.writeln("ERROR: " + e.toString() + " at line " + e.line); report.close();
    } finally { if (started) { app.endUndoGroup(); } }
}());
