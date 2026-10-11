/* global require */
(function () {
  var uxp = require("uxp");
  var premiere = require("premierepro");
  var lfs = uxp.storage.localFileSystem;

  if (uxp.entrypoints && uxp.entrypoints.setup) {
    uxp.entrypoints.setup({
      panels: {
        typecastShortsSync: {
          show: function () {}
        }
      }
    });
  }

  var state = {
    folder: null,
    job: null,
    sequenceName: "Not checked",
    generatedSrtPath: ""
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function setStatus(lines) {
    byId("status").textContent = lines.join("\n");
  }

  function renderStatus(extraLines) {
    var lines = [];
    lines.push("Active sequence: " + state.sequenceName);

    if (!state.job) {
      lines.push("Audio: Not selected");
      lines.push("Caption: Not selected");
      lines.push("Cue count: 0");
    } else {
      lines.push("Folder: " + state.job.folderName);
      lines.push("Audio: " + (state.job.audioEntry ? state.job.audioEntry.name : "Not found"));
      lines.push("Caption: " + (state.job.captionEntry ? state.job.captionEntry.name : "Not found"));
      lines.push("Source: " + state.job.captionSource);
      lines.push("Cue count: " + state.job.cues.length);
    }

    if (state.generatedSrtPath) {
      lines.push("Generated SRT: " + state.generatedSrtPath);
    }

    if (state.job && state.job.errors.length) {
      lines.push("");
      lines.push("Errors:");
      lines = lines.concat(state.job.errors);
    }

    if (state.job && state.job.warnings.length) {
      lines.push("");
      lines.push("Warnings:");
      lines = lines.concat(state.job.warnings);
    }

    if (extraLines && extraLines.length) {
      lines.push("");
      lines = lines.concat(extraLines);
    }

    setStatus(lines);
  }

  async function refreshActiveSequence() {
    try {
      var project = await premiere.Project.getActiveProject();
      var sequence = project ? await project.getActiveSequence() : null;
      state.sequenceName = sequence ? sequence.name : "No active sequence";
    } catch (error) {
      state.sequenceName = "Could not read active sequence";
    }

    renderStatus();
  }

  async function selectFolder() {
    var folder = await lfs.getFolder();

    if (!folder) {
      return;
    }

    state.folder = folder;
    state.generatedSrtPath = "";
    state.job = await discoverJobFolder(folder);
    byId("generate").disabled = state.job.errors.length > 0;
    renderStatus();
  }

  async function generateCaptions() {
    if (!state.job || state.job.errors.length > 0) {
      renderStatus(["Select a valid Typecast folder first."]);
      return;
    }

    var lines = [];
    var srtFile = await writeFallbackSrt(state.folder, state.job.cues);
    state.generatedSrtPath = lfs.getNativePath(srtFile);

    try {
      var project = await premiere.Project.getActiveProject();
      if (!project) {
        throw new Error("No active Premiere Pro project.");
      }

      var targetBin = project.getInsertionBin ? await project.getInsertionBin() : await project.getRootItem();
      var importPaths = [lfs.getNativePath(state.job.audioEntry), state.generatedSrtPath];
      var imported = await project.importFiles(importPaths, true, targetBin, false);
      lines.push(imported ? "Imported audio and fallback SRT into the project." : "Premiere did not confirm project import.");
    } catch (error) {
      lines.push("Project import warning: " + error.message);
    }

    // Adobe's documented Premiere UXP DOM currently exposes caption track inspection,
    // but not a stable public method for creating caption cues or inserting clips.
    // The reliable MVP path is to generate/import SRT and show the operator the final step.
    lines.push("Manual step: place the voice audio at 00:00 on the target audio track if it was not placed automatically.");
    lines.push("Manual step: import/place typecast_sync_fallback.srt as captions if Premiere did not create the caption track.");
    renderStatus(lines);
  }

  async function discoverJobFolder(folder) {
    var entries = await folder.getEntries();
    var job = {
      folderName: folder.name || lfs.getNativePath(folder),
      audioEntry: findPreferredEntry(entries, ["voice.wav", "voice.mp3"], ["wav", "mp3"]),
      captionEntry: null,
      captionSource: "none",
      scriptEntry: findPreferredEntry(entries, ["script.txt"], ["txt"]),
      typecastJsonEntry: findPreferredEntry(entries, ["typecast.json"], ["json"]),
      cues: [],
      errors: [],
      warnings: []
    };

    var srtEntry = findPreferredEntry(entries, ["captions.srt"], ["srt"]);
    var vttEntry = findPreferredEntry(entries, ["captions.vtt"], ["vtt"]);

    if (job.typecastJsonEntry) {
      try {
        job.cues = parseTypecastJson(await readText(job.typecastJsonEntry));
        if (job.cues.length > 0) {
          job.captionEntry = job.typecastJsonEntry;
          job.captionSource = "typecast-json";
        } else {
          job.warnings.push("typecast.json exists but no usable timestamp cues were found.");
        }
      } catch (error) {
        job.warnings.push("Could not parse typecast.json: " + error.message);
      }
    }

    if (job.cues.length === 0 && srtEntry) {
      job.cues = parseSrt(await readText(srtEntry));
      job.captionEntry = srtEntry;
      job.captionSource = job.cues.length > 0 ? "srt" : "none";
    }

    if (job.cues.length === 0 && vttEntry) {
      job.cues = parseVtt(await readText(vttEntry));
      job.captionEntry = vttEntry;
      job.captionSource = job.cues.length > 0 ? "vtt" : "none";
    }

    if (!job.audioEntry) {
      job.errors.push("Missing voice audio file. Expected voice.wav or voice.mp3.");
    }

    if (job.cues.length === 0) {
      if (job.scriptEntry) {
        job.captionSource = "script";
        job.warnings.push("script.txt exists, but accurate sync cannot be generated without SRT, VTT, or timestamp JSON.");
      }
      job.errors.push("Missing usable caption timing file.");
    }

    addCueWarnings(job);
    return job;
  }

  function addCueWarnings(job) {
    for (var index = 0; index < job.cues.length; index += 1) {
      if (!job.cues[index].text) {
        job.warnings.push("Cue " + job.cues[index].id + " has empty text.");
      }
      if (job.cues[index].endSeconds <= job.cues[index].startSeconds) {
        job.warnings.push("Cue " + job.cues[index].id + " has a non-positive duration.");
      }
    }

    for (var cueIndex = 1; cueIndex < job.cues.length; cueIndex += 1) {
      if (job.cues[cueIndex].startSeconds < job.cues[cueIndex - 1].endSeconds) {
        job.warnings.push("Cue " + job.cues[cueIndex].id + " overlaps cue " + job.cues[cueIndex - 1].id + ".");
      }
    }
  }

  function findPreferredEntry(entries, preferredNames, extensions) {
    var files = entries.filter(function (entry) {
      return entry.isFile;
    });

    for (var preferredIndex = 0; preferredIndex < preferredNames.length; preferredIndex += 1) {
      for (var fileIndex = 0; fileIndex < files.length; fileIndex += 1) {
        if (files[fileIndex].name.toLowerCase() === preferredNames[preferredIndex].toLowerCase()) {
          return files[fileIndex];
        }
      }
    }

    for (var index = 0; index < files.length; index += 1) {
      var lowerName = files[index].name.toLowerCase();
      for (var extIndex = 0; extIndex < extensions.length; extIndex += 1) {
        if (lowerName.endsWith("." + extensions[extIndex])) {
          return files[index];
        }
      }
    }

    return null;
  }

  async function readText(entry) {
    return entry.read({ format: uxp.storage.formats.utf8 });
  }

  async function writeFallbackSrt(folder, cues) {
    var file = await folder.createFile("typecast_sync_fallback.srt", { overwrite: true });
    await file.write(formatSrt(cues), { format: uxp.storage.formats.utf8 });
    return file;
  }

  function parseSrt(input) {
    var lines = String(input).replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").split("\n");
    var cues = [];
    var index = 0;
    var timingPattern = /^\s*((?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3})\s*-->\s*((?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3})(?:\s+.*)?$/;

    while (index < lines.length) {
      while (index < lines.length && lines[index].trim() === "") {
        index += 1;
      }

      if (index >= lines.length) {
        break;
      }

      var explicitId = null;
      if (/^\d+$/.test(lines[index].trim()) && index + 1 < lines.length && timingPattern.test(lines[index + 1])) {
        explicitId = Number(lines[index].trim());
        index += 1;
      }

      var match = lines[index].match(timingPattern);
      if (!match) {
        index += 1;
        continue;
      }

      var startSeconds = timestampToSeconds(match[1]);
      var endSeconds = timestampToSeconds(match[2]);
      index += 1;

      var textLines = [];
      while (index < lines.length && lines[index].trim() !== "") {
        textLines.push(lines[index]);
        index += 1;
      }

      cues.push({
        id: explicitId || cues.length + 1,
        startSeconds: startSeconds,
        endSeconds: endSeconds,
        text: normalizeWhitespace(textLines.join(" "))
      });
    }

    return cues;
  }

  function parseVtt(input) {
    var lines = String(input).replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").split("\n");
    var cues = [];
    var index = 0;
    var timingPattern = /^\s*((?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3})\s*-->\s*((?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3})(?:\s+.*)?$/;

    if (lines[index] && lines[index].trim().indexOf("WEBVTT") === 0) {
      index += 1;
    }

    while (index < lines.length) {
      while (index < lines.length && lines[index].trim() === "") {
        index += 1;
      }

      if (index >= lines.length) {
        break;
      }

      if (!timingPattern.test(lines[index]) && index + 1 < lines.length && timingPattern.test(lines[index + 1])) {
        index += 1;
      }

      var match = lines[index].match(timingPattern);
      if (!match) {
        index += 1;
        continue;
      }

      var startSeconds = timestampToSeconds(match[1]);
      var endSeconds = timestampToSeconds(match[2]);
      index += 1;

      var textLines = [];
      while (index < lines.length && lines[index].trim() !== "") {
        textLines.push(lines[index]);
        index += 1;
      }

      cues.push({
        id: cues.length + 1,
        startSeconds: startSeconds,
        endSeconds: endSeconds,
        text: normalizeWhitespace(textLines.join(" "))
      });
    }

    return cues;
  }

  function parseTypecastJson(input) {
    var root = JSON.parse(input);
    var candidates = [];
    collectCueArrays(root, candidates);

    if (candidates.length === 0) {
      return [];
    }

    candidates.sort(function (a, b) {
      return b.length - a.length;
    });

    return candidates[0].sort(function (a, b) {
      return a.startSeconds - b.startSeconds;
    }).map(function (cue, index) {
      cue.id = index + 1;
      return cue;
    });
  }

  function collectCueArrays(value, out) {
    if (Array.isArray(value)) {
      var cues = value.map(cueFromObject).filter(Boolean);
      if (cues.length > 0 && cues.length / Math.max(1, value.length) >= 0.6) {
        out.push(cues);
      }
      value.forEach(function (child) {
        collectCueArrays(child, out);
      });
      return;
    }

    if (value && typeof value === "object") {
      Object.keys(value).forEach(function (key) {
        collectCueArrays(value[key], out);
      });
    }
  }

  function cueFromObject(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      return null;
    }

    var text = firstString(value, ["text", "caption", "content", "line", "sentence", "displayText", "transcript"]);
    var start = firstNumber(value, ["startSeconds", "start_seconds", "start", "startTime", "start_time", "from", "begin", "offset"]);
    var end = firstNumber(value, ["endSeconds", "end_seconds", "end", "endTime", "end_time", "to", "finish"]);

    if (end === null && start !== null) {
      var duration = firstNumber(value, ["durationSeconds", "duration_seconds", "duration", "length"]);
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
      text: normalizeWhitespace(text)
    };
  }

  function firstString(object, keys) {
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
  }

  function firstNumber(object, keys) {
    for (var index = 0; index < keys.length; index += 1) {
      var key = keys[index];
      var value = object[key];
      if (value === undefined || value === null || value === "") {
        continue;
      }

      var numberValue = Number(value);
      if (Number.isFinite(numberValue)) {
        if (/_ms$/i.test(key) || Math.abs(numberValue) > 10000) {
          return numberValue / 1000;
        }
        return numberValue;
      }
    }
    return null;
  }

  function timestampToSeconds(value) {
    var match = String(value).trim().match(/^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})([,.](\d{1,3}))?$/);
    if (!match) {
      throw new Error("Invalid timestamp: " + value);
    }

    var milliseconds = match[5] || "0";
    while (milliseconds.length < 3) {
      milliseconds += "0";
    }

    return Number(match[1] || 0) * 3600 + Number(match[2]) * 60 + Number(match[3]) + Number(milliseconds) / 1000;
  }

  function formatSrt(cues) {
    return cues.map(function (cue, index) {
      return [
        String(index + 1),
        secondsToSrtTimestamp(cue.startSeconds) + " --> " + secondsToSrtTimestamp(cue.endSeconds),
        cue.text.trim()
      ].join("\n");
    }).join("\n\n") + (cues.length ? "\n" : "");
  }

  function secondsToSrtTimestamp(seconds) {
    var totalMilliseconds = Math.round(Math.max(0, seconds) * 1000);
    var milliseconds = totalMilliseconds % 1000;
    var totalSeconds = Math.floor(totalMilliseconds / 1000);
    var wholeSeconds = totalSeconds % 60;
    var minutes = Math.floor(totalSeconds / 60) % 60;
    var hours = Math.floor(totalSeconds / 3600);
    return pad(hours, 2) + ":" + pad(minutes, 2) + ":" + pad(wholeSeconds, 2) + "," + pad(milliseconds, 3);
  }

  function normalizeWhitespace(text) {
    return String(text).replace(/\s+/g, " ").trim();
  }

  function pad(value, size) {
    var text = String(value);
    while (text.length < size) {
      text = "0" + text;
    }
    return text;
  }

  document.addEventListener("DOMContentLoaded", function () {
    byId("refreshSequence").addEventListener("click", refreshActiveSequence);
    byId("selectFolder").addEventListener("click", selectFolder);
    byId("generate").addEventListener("click", generateCaptions);
    refreshActiveSequence();
  });
})();
