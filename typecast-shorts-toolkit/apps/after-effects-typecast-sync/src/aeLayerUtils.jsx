var TCSS_AE = TCSS_AE || {};

TCSS_AE.findLayerByName = function (comp, name) {
  for (var index = 1; index <= comp.numLayers; index += 1) {
    if (comp.layer(index).name === name) {
      return comp.layer(index);
    }
  }

  return null;
};

TCSS_AE.deleteAutoCaptionLayers = function (comp) {
  var deleted = 0;

  for (var index = comp.numLayers; index >= 1; index -= 1) {
    var layer = comp.layer(index);
    if (layer.name.indexOf("CAPTION_AUTO_") === 0 || layer.name === "VOICE_AUTO") {
      layer.remove();
      deleted += 1;
    }
  }

  return deleted;
};

TCSS_AE.setTextLayerValue = function (layer, text) {
  var textProp = layer.property("Source Text");

  if (!textProp) {
    textProp = layer.property("ADBE Text Properties").property("ADBE Text Document");
  }

  var document = textProp.value;

  if (document && document.text !== undefined) {
    document.text = text;
    textProp.setValue(document);
  } else {
    textProp.setValue(text);
  }
};

TCSS_AE.createCaptionLayer = function (comp, templateLayer, text, index) {
  var layer;

  if (templateLayer) {
    layer = templateLayer.duplicate();
    layer.enabled = true;
    TCSS_AE.setTextLayerValue(layer, text);
  } else {
    layer = comp.layers.addText(text);
    TCSS_AE.applyDefaultCaptionStyle(comp, layer);
  }

  layer.name = "CAPTION_AUTO_" + TCSS_AE.padNumber(index, 3);
  return layer;
};

TCSS_AE.applyDefaultCaptionStyle = function (comp, layer) {
  var textProp = layer.property("Source Text");
  var document = textProp.value;

  if (document && document.text !== undefined) {
    document.fontSize = Math.max(44, Math.round(comp.height * 0.055));
    document.justification = ParagraphJustification.CENTER_JUSTIFY;
    document.fillColor = [1, 1, 1];
    textProp.setValue(document);
  }

  var position = layer.property("Transform").property("Position");
  position.setValue([comp.width / 2, comp.height * 0.78]);
};

TCSS_AE.padNumber = function (value, size) {
  var text = String(value);
  while (text.length < size) {
    text = "0" + text;
  }
  return text;
};
