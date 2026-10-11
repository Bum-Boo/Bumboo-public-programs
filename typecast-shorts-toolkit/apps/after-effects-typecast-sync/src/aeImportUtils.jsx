var TCSS_AE = TCSS_AE || {};

TCSS_AE.importAudioFile = function (file) {
  if (!file || !file.exists) {
    throw new Error("Audio file does not exist.");
  }

  var options = new ImportOptions(file);

  if (!options.canImportAs(ImportAsType.FOOTAGE)) {
    throw new Error("After Effects cannot import this audio file as footage: " + file.fsName);
  }

  options.importAs = ImportAsType.FOOTAGE;
  return app.project.importFile(options);
};

TCSS_AE.placeAudioAtStart = function (comp, audioItem) {
  var layer = comp.layers.add(audioItem);
  layer.name = "VOICE_AUTO";
  layer.startTime = 0;
  layer.inPoint = 0;

  if (audioItem.duration && audioItem.duration > 0) {
    layer.outPoint = Math.min(audioItem.duration, comp.duration);
  }

  var placeholder = TCSS_AE.findLayerByName(comp, "VOICE_HERE");
  if (placeholder) {
    layer.moveBefore(placeholder);
    placeholder.enabled = false;
  }

  return layer;
};
