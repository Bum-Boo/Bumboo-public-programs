import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { parseSrt } from "./parseSrt.js";
import { parseTypecastJson } from "./parseTypecastJson.js";
import { parseVtt } from "./parseVtt.js";
import type { CaptionCue, CaptionSource, TypecastJob, TypecastJobFiles } from "./types.js";

const AUDIO_EXTENSIONS = [".wav", ".mp3"];

export function discoverTypecastJob(folderPath: string): TypecastJob {
  const errors: string[] = [];
  const warnings: string[] = [];
  const files = discoverFiles(folderPath);
  let cues: CaptionCue[] = [];
  let captionSource: CaptionSource = "none";
  let captionFile: string | undefined;

  if (!existsSync(folderPath) || !statSync(folderPath).isDirectory()) {
    return {
      folderPath,
      files,
      captionSource,
      cues,
      errors: [`Folder does not exist: ${folderPath}`],
      warnings
    };
  }

  if (files.typecastJsonFile) {
    try {
      cues = parseTypecastJson(readFileSync(files.typecastJsonFile, "utf8"));
      if (cues.length > 0) {
        captionSource = "typecast-json";
        captionFile = files.typecastJsonFile;
      } else {
        warnings.push("typecast.json exists but no usable timestamp cues were found.");
      }
    } catch (error) {
      warnings.push(`Could not parse typecast.json: ${(error as Error).message}`);
    }
  }

  if (cues.length === 0 && files.srtFile) {
    cues = parseSrt(readFileSync(files.srtFile, "utf8"));
    captionSource = cues.length > 0 ? "srt" : "none";
    captionFile = cues.length > 0 ? files.srtFile : undefined;
  }

  if (cues.length === 0 && files.vttFile) {
    cues = parseVtt(readFileSync(files.vttFile, "utf8"));
    captionSource = cues.length > 0 ? "vtt" : "none";
    captionFile = cues.length > 0 ? files.vttFile : undefined;
  }

  if (!files.audioFile) {
    errors.push("Missing voice audio file. Expected voice.wav, voice.mp3, or another .wav/.mp3 file.");
  }

  if (cues.length === 0) {
    if (files.scriptFile) {
      captionSource = "script";
      warnings.push("script.txt exists, but accurate sync cannot be generated without SRT, VTT, or timestamp JSON.");
    }
    errors.push("Missing usable caption timing file. Expected captions.srt, captions.vtt, or timestamped typecast.json.");
  }

  warnings.push(...findCueWarnings(cues));

  return {
    folderPath,
    files,
    audioFile: files.audioFile,
    captionFile,
    captionSource,
    cues,
    errors,
    warnings
  };
}

export function discoverFiles(folderPath: string): TypecastJobFiles {
  if (!existsSync(folderPath) || !statSync(folderPath).isDirectory()) {
    return {};
  }

  const entries = readdirSync(folderPath);
  const lowerToActual = new Map(entries.map((entry) => [entry.toLowerCase(), entry]));
  const filesOnly = entries.filter((entry) => statSync(join(folderPath, entry)).isFile());

  const preferredAudio =
    lowerToActual.get("voice.wav") ??
    lowerToActual.get("voice.mp3") ??
    filesOnly.find((entry) => AUDIO_EXTENSIONS.some((extension) => entry.toLowerCase().endsWith(extension)));

  const srtFile = lowerToActual.get("captions.srt") ?? filesOnly.find((entry) => entry.toLowerCase().endsWith(".srt"));
  const vttFile = lowerToActual.get("captions.vtt") ?? filesOnly.find((entry) => entry.toLowerCase().endsWith(".vtt"));
  const scriptFile = lowerToActual.get("script.txt") ?? filesOnly.find((entry) => entry.toLowerCase().endsWith(".txt"));
  const typecastJsonFile =
    lowerToActual.get("typecast.json") ?? filesOnly.find((entry) => entry.toLowerCase().endsWith(".json"));

  return {
    audioFile: preferredAudio ? join(folderPath, preferredAudio) : undefined,
    srtFile: srtFile ? join(folderPath, srtFile) : undefined,
    vttFile: vttFile ? join(folderPath, vttFile) : undefined,
    scriptFile: scriptFile ? join(folderPath, scriptFile) : undefined,
    typecastJsonFile: typecastJsonFile ? join(folderPath, typecastJsonFile) : undefined
  };
}

function findCueWarnings(cues: CaptionCue[]): string[] {
  const warnings: string[] = [];

  cues.forEach((cue) => {
    if (cue.text.trim() === "") {
      warnings.push(`Cue ${cue.id} has empty text.`);
    }

    if (cue.endSeconds <= cue.startSeconds) {
      warnings.push(`Cue ${cue.id} has a non-positive duration.`);
    }
  });

  for (let index = 1; index < cues.length; index += 1) {
    if (cues[index].startSeconds < cues[index - 1].endSeconds) {
      warnings.push(`Cue ${cues[index].id} overlaps cue ${cues[index - 1].id}.`);
    }
  }

  return warnings;
}
