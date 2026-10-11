// Editable HUD from track/track.py JSON. Edit these parameters before running.
var TRACKING_JSON = ""; // Empty uses demo/xr/tracking.json.
var HUD_COLOR = [0.15, 0.9, 1.0];
var STROKE_WIDTH = 2;
var FONT_NAME = "ArialMT";
var FONT_SIZE = 16;
var LABEL_PREFIX = "AID / ";
var LABEL_FORMAT = "{prefix}{id}  {x},{y}"; // Tokens: prefix, id, x, y.
var BOX_STYLE = "corners"; // "corners" or "box"
var MAX_TARGETS = 8;
var CONNECT_DISTANCE = 250;

(function () {
    var report = new File(File($.fileName).parent.fsName + "/tracking_hud_report.txt");
    var started = false;
    try {
        $.evalFile(new File(File($.fileName).parent.fsName + "/json_parser.jsxinc"));
        var base = File($.fileName).parent.parent;
        var source = new File(TRACKING_JSON || (base.fsName + "/demo/xr/tracking.json"));
        if (!source.exists) { throw new Error("Tracking file missing: " + source.fsName); }
        source.encoding = "UTF-8";
        if (!source.open("r")) { throw new Error("Cannot open tracking file"); }
        var data = parseToolkitJSON(source.read()); source.close();
        if (!data.frames || !data.width || !data.height || !data.fps) { throw new Error("Missing metadata"); }
        app.beginUndoGroup("Build AID tracking HUD"); started = true;
        var comp = app.project.items.addComp("AID HUD - " + source.displayName, data.width, data.height, 1, data.frame_count / data.fps, data.fps);
        var ids = {}, ordered = [], i, j, o, id;
        for (i = 0; i < data.frames.length; i++) {
            var objects = data.frames[i].objects || [];
            for (j = 0; j < objects.length; j++) {
                id = String(objects[j].id);
                ids[id] = (ids[id] || 0) + 1;
            }
        }
        for (id in ids) { if (ids.hasOwnProperty(id) && ids[id] >= 5) { ordered.push(id); } }
        ordered.sort(function (a, b) { return ids[b] - ids[a]; });
        if (ordered.length > MAX_TARGETS) { ordered.length = MAX_TARGETS; }
        function path(vertices, closed) {
            var s = new Shape(); s.vertices = vertices; s.closed = closed;
            s.inTangents = []; s.outTangents = [];
            for (var k = 0; k < vertices.length; k++) { s.inTangents.push([0, 0]); s.outTangents.push([0, 0]); }
            return s;
        }
        function newShape(name, color, width) {
            var layer = comp.layers.addShape(); layer.name = name;
            layer.property("ADBE Transform Group").property("ADBE Position").setValue([0, 0]);
            layer.property("ADBE Transform Group").property("ADBE Anchor Point").setValue([0, 0]);
            return layer;
        }
        function addStroke(layer, color, width) {
            var stroke = layer.property("ADBE Root Vectors Group").addProperty("ADBE Vector Graphic - Stroke");
            stroke.property("ADBE Vector Stroke Color").setValue(color);
            stroke.property("ADBE Vector Stroke Width").setValue(width);
        }
        function addPath(layer, name) {
            var p = layer.property("ADBE Root Vectors Group").addProperty("ADBE Vector Shape - Group");
            p.name = name; return p.property("ADBE Vector Shape");
        }
        var targets = {};
        for (i = 0; i < ordered.length; i++) {
            id = ordered[i]; var l = newShape("TARGET " + id + " / brackets", HUD_COLOR, STROKE_WIDTH);
            var ps = [], count = BOX_STYLE == "box" ? 1 : 4;
            for (j = 0; j < count; j++) { ps.push(addPath(l, "corner " + j)); }
            ps.push(addPath(l, "crosshair H")); ps.push(addPath(l, "crosshair V"));
            addStroke(l, HUD_COLOR, STROKE_WIDTH);
            var label = comp.layers.addText(LABEL_PREFIX + id); label.name = "TARGET " + id + " / label";
            var doc = label.property("Source Text").value;
            doc.font = FONT_NAME; doc.fontSize = FONT_SIZE; doc.fillColor = HUD_COLOR; doc.applyFill = true;
            label.property("Source Text").setValue(doc);
            targets[id] = {shape:l, paths:ps, label:label};
        }
        var links = {};
        for (i = 0; i < ordered.length; i++) { for (j = i + 1; j < ordered.length; j++) {
            var key = ordered[i] + "_" + ordered[j], link = newShape("LINK " + key, HUD_COLOR, STROKE_WIDTH * .5);
            links[key] = {layer:link, path:addPath(link, "connection")};
            addStroke(link, HUD_COLOR, STROKE_WIDTH * .5);
        }}
        for (i = 0; i < data.frames.length; i++) {
            var t = i / data.fps, visible = {}, frame = data.frames[i].objects || [];
            for (j = 0; j < frame.length; j++) { visible[String(frame[j].id)] = frame[j]; }
            for (j = 0; j < ordered.length; j++) {
                id = ordered[j]; o = visible[id]; var target = targets[id];
                target.shape.property("ADBE Transform Group").property("ADBE Opacity").setValueAtTime(t, o ? 100 : 0);
                target.label.property("ADBE Transform Group").property("ADBE Opacity").setValueAtTime(t, o ? 100 : 0);
                if (!o) { continue; }
                var x = o.box[0], y = o.box[1], w = o.box[2], h = o.box[3], n = Math.min(18, w * .25, h * .25), v;
                if (BOX_STYLE == "box") { target.paths[0].setValueAtTime(t, path([[x,y],[x+w,y],[x+w,y+h],[x,y+h]], true)); }
                else {
                    v = [ [[x,y+n],[x,y],[x+n,y]], [[x+w-n,y],[x+w,y],[x+w,y+n]], [[x+w,y+h-n],[x+w,y+h],[x+w-n,y+h]], [[x+n,y+h],[x,y+h],[x,y+h-n]] ];
                    for (var c = 0; c < 4; c++) { target.paths[c].setValueAtTime(t, path(v[c], false)); }
                }
                var cx = o.centroid[0], cy = o.centroid[1], p = target.paths.length;
                target.paths[p-2].setValueAtTime(t, path([[cx-7,cy],[cx+7,cy]], false));
                target.paths[p-1].setValueAtTime(t, path([[cx,cy-7],[cx,cy+7]], false));
                target.label.property("ADBE Transform Group").property("ADBE Position").setValueAtTime(t, [x, Math.max(20,y-8)]);
                var td = target.label.property("Source Text").value;
                td.text = LABEL_FORMAT.replace(/\{prefix\}/g, LABEL_PREFIX).replace(/\{id\}/g, id)
                    .replace(/\{x\}/g, String(Math.round(cx))).replace(/\{y\}/g, String(Math.round(cy)));
                target.label.property("Source Text").setValueAtTime(t, td);
            }
            for (var lk in links) { if (links.hasOwnProperty(lk)) {
                var pair = lk.split("_"), a = visible[pair[0]], b = visible[pair[1]], line = links[lk], show = false;
                if (a && b) { var dx = a.centroid[0]-b.centroid[0], dy = a.centroid[1]-b.centroid[1]; show = dx*dx+dy*dy <= CONNECT_DISTANCE*CONNECT_DISTANCE; }
                line.layer.property("ADBE Transform Group").property("ADBE Opacity").setValueAtTime(t, show ? 50 : 0);
                if (show) { line.path.setValueAtTime(t, path([a.centroid,b.centroid], false)); }
            }}
        }
        report.open("w"); report.writeln("OK: " + comp.name + ", " + ordered.length + " targets, " + data.frames.length + " frames."); report.close();
    } catch (e) {
        report.open("w"); report.writeln("ERROR: " + e.toString() + " at line " + e.line); report.close();
    } finally { if (started) { app.endUndoGroup(); } }
}());
