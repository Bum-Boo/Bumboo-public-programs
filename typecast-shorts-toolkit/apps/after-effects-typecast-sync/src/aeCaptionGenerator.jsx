var TCSS_AE = TCSS_AE || {};

TCSS_AE.discoverJobFolder = function (folder) {
  var files = folder.getFiles();
  var job = {
    folder: folder,
    audioFile: null,
    captionFile: null,
    captionSource: "none",
    scriptFile: null,
    typecastJsonFile: null,
    cues: [],
    errors: [],
    warnings: []
  };

  job.audioFile = TCSS_AE.findPreferredFile(files, ["voice.wav", "voice.mp3"], ["wav", "mp3"]);
  job.captionFile = TCSS_AE.findPreferredFile(files, ["captions.srt"], ["srt"]);
  var vttFile = TCSS_AE.findPreferredFile(files, ["captions.vtt"], ["vtt"]);
  job.scriptFile = TCSS_AE.findPreferredFile(files, ["script.txt"], ["txt"]);
  job.typecastJsonFile = TCSS_AE.findPreferredFile(files, ["typecast.json"], ["json"]);

  if (job.typecastJsonFile) {
    try {
      job.cues = TCSS_AE.parseTypecastJson(TCSS_AE.readTextFile(job.typecastJsonFile));
      if (job.cues.length > 0) {
        job.captionFile = job.typecastJsonFile;
        job.captionSource = "typecast-json";
      } else {
        job.warnings.push("typecast.json exists but no usable timestamp cues were found.");
      }
    } catch (error) {
      job.warnings.push("Could not parse typecast.json: " + error.toString());
    }
  }

  if (job.cues.length === 0 && job.captionFile) {
    job.cues = TCSS_AE.parseSrt(TCSS_AE.readTextFile(job.captionFile));
    job.captionSource = job.cues.length > 0 ? "srt" : "none";
  }

  if (job.cues.length === 0 && vttFile) {
    job.captionFile = vttFile;
    job.cues = TCSS_AE.parseVtt(TCSS_AE.readTextFile(vttFile));
    job.captionSource = job.cues.length > 0 ? "vtt" : "none";
  }

  if (!job.audioFile) {
    job.errors.push("Missing voice audio file. Expected voice.wav or voice.mp3.");
  }

  if (job.cues.length === 0) {
    if (job.scriptFile) {
      job.captionSource = "script";
      job.warnings.push("script.txt exists, but accurate sync cannot be generated without SRT, VTT, or timestamp JSON.");
    }
    job.errors.push("Missing usable caption timing file.");
  }

  for (var index = 1; index < job.cues.length; index += 1) {
    if (job.cues[index].startSeconds < job.cues[index - 1].endSeconds) {
      job.warnings.push("Cue " + job.cues[index].id + " overlaps cue " + job.cues[index - 1].id + ".");
    }
  }

  return job;
};

TCSS_AE.generateCaptions = function (comp, job, options) {
  if (job.errors.length > 0) {
    throw new Error(job.errors.join("\n"));
  }

  var deleted = TCSS_AE.deleteAutoCaptionLayers(comp);
  var audioItem = TCSS_AE.importAudioFile(job.audioFile);
  var audioLayer = TCSS_AE.placeAudioAtStart(comp, audioItem);

  if (options && options.adjustDuration && audioItem.duration && audioItem.duration > 0) {
    comp.duration = Math.max(comp.duration, audioItem.duration);
    audioLayer.outPoint = audioItem.duration;
  }

  var template = TCSS_AE.findLayerByName(comp, "CAPTION_TEMPLATE");
  if (template) {
    template.enabled = false;
  }

  for (var index = 0; index < job.cues.length; index += 1) {
    var cue = job.cues[index];
    var layer = TCSS_AE.createCaptionLayer(comp, template, cue.text, index + 1);
    layer.inPoint = Math.max(0, cue.startSeconds);
    layer.outPoint = Math.max(layer.inPoint + 0.01, cue.endSeconds);
  }

  return {
    deletedLayers: deleted,
    cueCount: job.cues.length,
    audioFile: job.audioFile.fsName,
    captionFile: job.captionFile ? job.captionFile.fsName : "",
    warnings: job.warnings
  };
};

TCSS_AE.findPreferredFile = function (files, preferredNames, extensions) {
  var index;
  var file;
  var lowerName;

  for (index = 0; index < preferredNames.length; index += 1) {
    for (var fileIndex = 0; fileIndex < files.length; fileIndex += 1) {
      file = files[fileIndex];
      if (!(file instanceof File)) {
        continue;
      }
      if (file.name.toLowerCase() === preferredNames[index].toLowerCase()) {
        return file;
      }
    }
  }

  for (index = 0; index < files.length; index += 1) {
    file = files[index];
    if (!(file instanceof File)) {
      continue;
    }

    lowerName = file.name.toLowerCase();
    for (var extIndex = 0; extIndex < extensions.length; extIndex += 1) {
      if (lowerName.substr(lowerName.length - extensions[extIndex].length - 1) === "." + extensions[extIndex]) {
        return file;
      }
    }
  }

  return null;
};

TCSS_AE.readTextFile = function (file) {
  file.encoding = "UTF-8";
  if (!file.open("r")) {
    throw new Error("Could not read file: " + file.fsName);
  }
  var text = file.read();
  file.close();
  return text;
};

TCSS_AE.formatJobStatus = function (job, comp) {
  var lines = [];
  lines.push("Composition: " + (comp ? comp.name : "No active comp"));
  lines.push("Audio: " + (job.audioFile ? job.audioFile.name : "Not found"));
  lines.push("Caption: " + (job.captionFile ? job.captionFile.name : "Not found"));
  lines.push("Source: " + job.captionSource);
  lines.push("Cue count: " + job.cues.length);

  if (job.errors.length > 0) {
    lines.push("");
    lines.push("Errors:");
    lines = lines.concat(job.errors);
  }

  if (job.warnings.length > 0) {
    lines.push("");
    lines.push("Warnings:");
    lines = lines.concat(job.warnings);
  }

  return lines.join("\n");
};

TCSS_AE.formatGenerationStatus = function (result, comp) {
  var lines = [];
  lines.push("Generated captions in: " + comp.name);
  lines.push("Audio: " + result.audioFile);
  lines.push("Caption: " + result.captionFile);
  lines.push("Cue count: " + result.cueCount);
  lines.push("Deleted old auto layers: " + result.deletedLayers);

  if (result.warnings.length > 0) {
    lines.push("");
    lines.push("Warnings:");
    lines = lines.concat(result.warnings);
  }

  return lines.join("\n");
};

TCSS_AE.normalizeWhitespace = function (text) {
  return String(text).replace(/\s+/g, " ").replace(/^\s+|\s+$/g, "");
};

TCSS_AE.parseSrt = function (input) {
  var lines = String(input).replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").split("\n");
  var cues = [];
  var index = 0;
  var timingPattern = /^\s*((?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3})\s*-->\s*((?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3})(?:\s+.*)?$/;

  while (index < lines.length) {
    while (index < lines.length && lines[index].replace(/\s/g, "") === "") {
      index += 1;
    }

    if (index >= lines.length) {
      break;
    }

    var explicitId = null;

    if (/^\d+$/.test(lines[index].replace(/^\s+|\s+$/g, "")) && index + 1 < lines.length && timingPattern.test(lines[index + 1])) {
      explicitId = Number(lines[index].replace(/^\s+|\s+$/g, ""));
      index += 1;
    }

    var match = lines[index].match(timingPattern);
    if (!match) {
      index += 1;
      continue;
    }

    var startSeconds = TCSS_AE.timestampToSeconds(match[1]);
    var endSeconds = TCSS_AE.timestampToSeconds(match[2]);
    index += 1;

    var textLines = [];
    while (index < lines.length && lines[index].replace(/\s/g, "") !== "") {
      textLines.push(lines[index]);
      index += 1;
    }

    cues.push({
      id: explicitId || cues.length + 1,
      startSeconds: startSeconds,
      endSeconds: endSeconds,
      text: TCSS_AE.normalizeWhitespace(textLines.join(" "))
    });
  }

  return cues;
};

TCSS_AE.parseVtt = function (input) {
  var text = String(input).replace(/^WEBVTT[^\n]*\n/, "");
  return TCSS_AE.parseSrt(text);
};

TCSS_AE.parseTypecastJson = function (input) {
  var data = TCSS_AE.parseJson(input);
  var candidates = [];
  TCSS_AE.collectJsonCues(data, candidates);

  if (candidates.length === 0) {
    return [];
  }

  candidates.sort(function (a, b) {
    return b.length - a.length;
  });

  for (var index = 0; index < candidates[0].length; index += 1) {
    candidates[0][index].id = index + 1;
  }

  return candidates[0];
};

TCSS_AE.collectJsonCues = function (value, candidates) {
  if (value instanceof Array) {
    var cues = [];
    for (var index = 0; index < value.length; index += 1) {
      var cue = TCSS_AE.jsonObjectToCue(value[index]);
      if (cue) {
        cues.push(cue);
      }
      TCSS_AE.collectJsonCues(value[index], candidates);
    }

    if (cues.length > 0 && cues.length / Math.max(1, value.length) >= 0.6) {
      candidates.push(cues);
    }
  } else if (value && typeof value === "object") {
    for (var key in value) {
      if (value.hasOwnProperty(key)) {
        TCSS_AE.collectJsonCues(value[key], candidates);
      }
    }
  }
};

TCSS_AE.jsonObjectToCue = function (value) {
  if (!value || typeof value !== "object" || value instanceof Array) {
    return null;
  }

  var text = TCSS_AE.firstString(value, ["text", "caption", "content", "line", "sentence", "displayText", "transcript"]);
  var start = TCSS_AE.firstNumber(value, ["startSeconds", "start_seconds", "start", "startTime", "start_time", "from", "begin", "offset"]);
  var end = TCSS_AE.firstNumber(value, ["endSeconds", "end_seconds", "end", "endTime", "end_time", "to", "finish"]);

  if (end === null && start !== null) {
    var duration = TCSS_AE.firstNumber(value, ["durationSeconds", "duration_seconds", "duration", "length"]);
    if (duration !== null) {
      end = start + duration;
    }
  }

  if (text === null || start === null || end === null || end < start) {
    return null;
  }

  return {
    id: 0,
    startSeconds: start,
    endSeconds: end,
    text: TCSS_AE.normalizeWhitespace(text)
  };
};

TCSS_AE.parseJson = function (input) {
  if (typeof JSON !== "undefined" && JSON.parse) {
    return JSON.parse(input);
  }

  return eval("(" + input + ")");
};

TCSS_AE.firstString = function (object, keys) {
  for (var index = 0; index < keys.length; index += 1) {
    var value = object[keys[index]];
    if (typeof value === "string") {
      return value;
    }
    if (typeof value === "number") {
      return String(value);
    }
  }

  return null;
};

TCSS_AE.firstNumber = function (object, keys) {
  for (var index = 0; index < keys.length; index += 1) {
    var key = keys[index];
    var value = object[key];
    if (value === undefined || value === null || value === "") {
      continue;
    }

    var numberValue = Number(value);
    if (!isNaN(numberValue)) {
      if (/_ms$/i.test(key) || Math.abs(numberValue) > 10000) {
        return numberValue / 1000;
      }
      return numberValue;
    }
  }

  return null;
};

TCSS_AE.timestampToSeconds = function (value) {
  var match = String(value).replace(/^\s+|\s+$/g, "").match(/^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})([,.](\d{1,3}))?$/);

  if (!match) {
    throw new Error("Invalid timestamp: " + value);
  }

  var hours = Number(match[1] || 0);
  var minutes = Number(match[2]);
  var seconds = Number(match[3]);
  var millisText = match[5] || "0";
  while (millisText.length < 3) {
    millisText += "0";
  }

  return hours * 3600 + minutes * 60 + seconds + Number(millisText) / 1000;
};
