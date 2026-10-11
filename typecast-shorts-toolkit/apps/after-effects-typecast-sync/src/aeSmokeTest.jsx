#include "aeLayerUtils.jsx"
#include "aeImportUtils.jsx"
#include "aeCaptionGenerator.jsx"

(function aeSmokeTest() {
  var scriptFolder = new File($.fileName).parent;
  var workspace = scriptFolder.parent.parent.parent.fsName.replace(/\\/g, "/");
  var reportFile = new File(workspace + "/samples/smoke_runtime_srt/ae_smoke_report.txt");
  var projectFile = new File(workspace + "/samples/smoke_runtime_srt/ae_smoke_test.aep");
  var lines = [];
  var passed = true;

  function assertLine(condition, message) {
    if (condition) {
      lines.push("PASS: " + message);
    } else {
      passed = false;
      lines.push("FAIL: " + message);
    }
  }

  function writeReport() {
    reportFile.encoding = "UTF-8";
    reportFile.open("w");
    reportFile.write(lines.join("\n"));
    reportFile.close();
  }

  app.beginSuppressDialogs();
  app.beginUndoGroup("Typecast Shorts Sync Smoke Test");

  try {
    app.newProject();

    var comp = app.project.items.addComp("TCSS_SMOKE_COMP", 1080, 1920, 1, 6, 30);
    var template = comp.layers.addText("CAPTION_TEMPLATE");
    template.name = "CAPTION_TEMPLATE";
    template.property("Transform").property("Position").setValue([540, 1450]);

    var folder = new Folder(workspace + "/samples/smoke_runtime_srt");
    var job = TCSS_AE.discoverJobFolder(folder);
    lines.push("Audio: " + (job.audioFile ? job.audioFile.fsName : "none"));
    lines.push("Caption: " + (job.captionFile ? job.captionFile.fsName : "none"));
    lines.push("Cue count: " + job.cues.length);
    lines.push("Errors: " + job.errors.join(" | "));
    lines.push("Warnings: " + job.warnings.join(" | "));

    assertLine(job.errors.length === 0, "job folder validates");
    assertLine(job.cues.length === 3, "three cues parsed from SRT");
    assertLine(job.cues[0].startSeconds === 0 && job.cues[0].endSeconds === 1.5, "first cue timing parsed");

    var result = TCSS_AE.generateCaptions(comp, job, { adjustDuration: true });
    assertLine(result.cueCount === 3, "generation reports three cues");

    var captionCount = 0;
    var firstCaption = null;
    var secondCaption = null;
    var audioLayer = null;

    for (var index = 1; index <= comp.numLayers; index += 1) {
      var layer = comp.layer(index);
      if (layer.name.indexOf("CAPTION_AUTO_") === 0) {
        captionCount += 1;
        if (layer.name === "CAPTION_AUTO_001") {
          firstCaption = layer;
        }
        if (layer.name === "CAPTION_AUTO_002") {
          secondCaption = layer;
        }
      }
      if (layer.name === "VOICE_AUTO") {
        audioLayer = layer;
      }
    }

    assertLine(captionCount === 3, "three CAPTION_AUTO layers created");
    assertLine(!!audioLayer, "VOICE_AUTO audio layer created");
    assertLine(!!firstCaption, "CAPTION_AUTO_001 exists");
    assertLine(firstCaption && Math.abs(firstCaption.inPoint - 0) < 0.001, "first caption inPoint is 0");
    assertLine(firstCaption && Math.abs(firstCaption.outPoint - 1.5) < 0.001, "first caption outPoint is 1.5");
    assertLine(secondCaption && Math.abs(secondCaption.inPoint - 1.75) < 0.001, "second caption inPoint is 1.75");
    assertLine(template.enabled === false, "CAPTION_TEMPLATE disabled after generation");

    TCSS_AE.generateCaptions(comp, job, { adjustDuration: true });

    var regeneratedCount = 0;
    for (var regenIndex = 1; regenIndex <= comp.numLayers; regenIndex += 1) {
      if (comp.layer(regenIndex).name.indexOf("CAPTION_AUTO_") === 0) {
        regeneratedCount += 1;
      }
    }
    assertLine(regeneratedCount === 3, "regeneration deletes old CAPTION_AUTO layers before recreating");

    app.project.save(projectFile);
    lines.unshift(passed ? "RESULT: PASS" : "RESULT: FAIL");
    lines.push("Saved project: " + projectFile.fsName);
  } catch (error) {
    passed = false;
    lines.unshift("RESULT: FAIL");
    lines.push("Exception: " + error.toString());
  } finally {
    writeReport();
    app.endUndoGroup();
    app.endSuppressDialogs(false);
    app.quit();
  }
})();
