// Editable hand, pose and face contour overlays from track/track.py JSON.
var LANDMARK_JSON = ""; // Empty uses demo/xr/tracking.json.
var LANDMARK_COLOR = [0.95, 0.6, 0.2];
var LANDMARK_STROKE = 2;

(function () {
    var report = new File(File($.fileName).parent.fsName + "/landmark_hud_report.txt"), started = false;
    try {
        $.evalFile(new File(File($.fileName).parent.fsName + "/json_parser.jsxinc"));
        var base = File($.fileName).parent.parent;
        var file = new File(LANDMARK_JSON || (base.fsName + "/demo/xr/tracking.json"));
        if (!file.exists) { throw new Error("JSON missing: " + file.fsName); }
        file.encoding = "UTF-8"; file.open("r"); var data = parseToolkitJSON(file.read()); file.close();
        app.beginUndoGroup("Build AID landmark HUD"); started = true;
        var comp = app.project.items.addComp("AID landmarks - " + file.displayName, data.width, data.height, 1, data.frame_count / data.fps, data.fps);
        var handEdges = [[0,1,2,3,4],[0,5,6,7,8],[5,9,10,11,12],[9,13,14,15,16],[13,17,18,19,20],[0,17]];
        var poseEdges = [[11,12],[11,13,15],[12,14,16],[11,23,24,12],[23,25,27],[24,26,28],[0,1,2,3,7],[0,4,5,6,8]];
        var faceOval = [10,338,297,332,284,251,389,356,454,323,361,288,397,365,379,378,400,377,152,148,176,149,150,136,172,58,132,93,234,127,162,21,54,103,67,109,10];
        function shape(vertices) {
            var s = new Shape(), k; s.vertices = vertices; s.closed = false; s.inTangents=[]; s.outTangents=[];
            for (k=0;k<vertices.length;k++) { s.inTangents.push([0,0]); s.outTangents.push([0,0]); }
            return s;
        }
        function addLine(name) {
            var layer=comp.layers.addShape(); layer.name=name;
            layer.property("ADBE Transform Group").property("ADBE Position").setValue([0,0]);
            layer.property("ADBE Transform Group").property("ADBE Anchor Point").setValue([0,0]);
            var root=layer.property("ADBE Root Vectors Group"), p=root.addProperty("ADBE Vector Shape - Group");
            var stroke=root.addProperty("ADBE Vector Graphic - Stroke");
            stroke.property("ADBE Vector Stroke Color").setValue(LANDMARK_COLOR);
            stroke.property("ADBE Vector Stroke Width").setValue(LANDMARK_STROKE);
            return {layer:layer,path:p.property("ADBE Vector Shape")};
        }
        var tracks=[], types=["hands","poses","faces"], edges=[handEdges,poseEdges,[faceOval]], t, i, j, n, e;
        for (t=0;t<3;t++) { for (n=0;n<2;n++) { for (e=0;e<edges[t].length;e++) {
            tracks.push({type:types[t], person:n, indices:edges[t][e], line:addLine(types[t] + " " + n + " / segment " + e)});
        }}}
        for (i=0;i<data.frames.length;i++) { var row=data.frames[i], sec=i/data.fps;
            for (j=0;j<tracks.length;j++) { var tr=tracks[j], persons=row[tr.type] || [], person=persons[tr.person];
                var visible=!!person, pts=[], k;
                if (visible) { for (k=0;k<tr.indices.length;k++) {
                    var p=person.points[tr.indices[k]];
                    if (!p || (p.visibility !== undefined && p.visibility < .25)) { visible=false; break; }
                    pts.push([p.x,p.y]);
                }}
                tr.line.layer.property("ADBE Transform Group").property("ADBE Opacity").setValueAtTime(sec,visible?100:0);
                if (visible) { tr.line.path.setValueAtTime(sec,shape(pts)); }
            }
        }
        report.open("w"); report.writeln("OK: " + comp.name + "; hand, pose, face contour paths are editable. Empty detections remain hidden."); report.close();
    } catch (e) {
        report.open("w"); report.writeln("ERROR: " + e.toString() + " at line " + e.line); report.close();
    } finally { if (started) { app.endUndoGroup(); } }
}());
