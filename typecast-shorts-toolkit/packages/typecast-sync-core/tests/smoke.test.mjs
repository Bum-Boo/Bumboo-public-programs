// End-to-end smoke tests for the shared core: discover a job folder -> parse ->
// normalize -> validate -> export SRT -> reparse. All inputs are synthetic and
// written to temp directories; the bundled samples/synthetic folder is only read.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  discoverTypecastJob,
  formatSrt,
  parseSrt,
  parseVtt,
  secondsToSrtTimestamp,
  secondsToTimecode,
  splitLongCue,
  validateJobFolder
} from "../dist/index.js";
import { toolkitRoot } from "./helpers/panelHarness.mjs";

const sampleFolder = join(toolkitRoot, "samples", "synthetic");

function tempJob(files) {
  const folder = mkdtempSync(join(tmpdir(), "typecast-smoke-"));
  for (const [name, contents] of Object.entries(files)) {
    writeFileSync(join(folder, name), contents);
  }
  return folder;
}

function simplify(cues) {
  // Array.from: arrays created inside the vm harness belong to another realm.
  return Array.from(cues, ({ startSeconds, endSeconds, text }) => ({ startSeconds, endSeconds, text }));
}

test("smoke: bundled samples/synthetic validates and round-trips through SRT export", () => {
  const validation = validateJobFolder(sampleFolder);
  assert.equal(validation.valid, true, validation.errors.join("; "));
  assert.equal(validation.captionSource, "srt");
  assert.equal(validation.cueCount, 2);
  assert.ok(validation.audioFile.endsWith("voice.wav"));
  assert.ok(validation.files.scriptFile.endsWith("script.txt"));
  assert.deepEqual(validation.warnings, []);

  const job = discoverTypecastJob(sampleFolder);
  assert.deepEqual(simplify(job.cues), [
    { startSeconds: 0, endSeconds: 0.5, text: "Synthetic caption one." },
    { startSeconds: 0.5, endSeconds: 1, text: "Synthetic caption two." }
  ]);

  const exported = formatSrt(job.cues);
  assert.equal(exported, readFileSync(join(sampleFolder, "captions.srt"), "utf8"));

  const outFolder = mkdtempSync(join(tmpdir(), "typecast-smoke-export-"));
  const outFile = join(outFolder, "typecast_sync_fallback.srt");
  writeFileSync(outFile, exported, "utf8");
  assert.deepEqual(simplify(parseSrt(readFileSync(outFile, "utf8"))), simplify(job.cues));

  assert.equal(secondsToTimecode(job.cues[1].startSeconds, 30), "00:00:00:15");
  assert.equal(splitLongCue(job.cues[0].text, 12, 2), "Synthetic\ncaption one.");
});

test("smoke: typecast.json word timings win over SRT and export to SRT", () => {
  const folder = tempJob({
    "voice.mp3": "synthetic placeholder",
    "captions.srt": "1\n00:00:00,000 --> 00:00:09,000\nIgnored lower-priority SRT\n",
    "typecast.json": JSON.stringify({
      result: {
        words: [
          { word: "Synthetic", start: 0, end: 0.4 },
          { word: "words", start: 0.45, end: 0.8 },
          { word: "here.", start: 0.85, end: 1.2 },
          { word: "Second", start: 2.5, end: 2.9 },
          { word: "sentence", start: 2.95, end: 3.4 }
        ]
      }
    })
  });

  const validation = validateJobFolder(folder);
  assert.equal(validation.valid, true, validation.errors.join("; "));
  assert.equal(validation.captionSource, "typecast-json");
  assert.ok(validation.captionFile.endsWith("typecast.json"));

  const job = discoverTypecastJob(folder);
  assert.deepEqual(simplify(job.cues), [
    { startSeconds: 0, endSeconds: 1.2, text: "Synthetic words here." },
    { startSeconds: 2.5, endSeconds: 3.4, text: "Second sentence" }
  ]);

  const srt = formatSrt(job.cues);
  assert.match(srt, /^1\n00:00:00,000 --> 00:00:01,200\nSynthetic words here\.\n\n2\n00:00:02,500 --> 00:00:03,400\nSecond sentence\n$/);
  assert.deepEqual(simplify(parseSrt(srt)), simplify(job.cues));
});

test("smoke: malformed typecast.json falls back to SRT with a warning", () => {
  const folder = tempJob({
    "voice.wav": "synthetic placeholder",
    "typecast.json": "{ not json",
    "captions.srt": "1\n00:00:01,000 --> 00:00:02,000\nFallback\n"
  });

  const job = discoverTypecastJob(folder);
  assert.equal(job.errors.length, 0);
  assert.equal(job.captionSource, "srt");
  assert.ok(job.warnings.some((warning) => warning.startsWith("Could not parse typecast.json")));
  assert.equal(job.cues[0].text, "Fallback");
});

test("smoke: CRLF + BOM SRT with period separators and timing-line cue settings", () => {
  const srt =
    "﻿1\r\n00:00:00.000 --> 00:00:01.5 X1:0 X2:10\r\nLine one\r\nline two\r\n\r\n" +
    "2\r\n00:00:01,500-->00:00:02,250\r\n  spaced   text  \r\n\r\n";
  const folder = tempJob({ "voice.wav": "synthetic placeholder", "captions.srt": srt });

  const job = discoverTypecastJob(folder);
  assert.equal(job.errors.length, 0);
  assert.deepEqual(job.warnings, []);
  assert.deepEqual(
    job.cues.map(({ id, startSeconds, endSeconds, text }) => ({ id, startSeconds, endSeconds, text })),
    [
      { id: 1, startSeconds: 0, endSeconds: 1.5, text: "Line one line two" },
      { id: 2, startSeconds: 1.5, endSeconds: 2.25, text: "spaced text" }
    ]
  );
  assert.deepEqual(simplify(parseSrt(formatSrt(job.cues))), simplify(job.cues));
});

test("smoke: VTT-only folder with header metadata, NOTE/STYLE blocks, ids, cue settings and CRLF", () => {
  const vtt = [
    "﻿WEBVTT - synthetic title",
    "Kind: captions",
    "Language: en",
    "",
    "NOTE synthetic comment",
    "00:00:09.000 --> 00:00:10.000 is not a cue inside NOTE",
    "",
    "STYLE",
    "::cue { color: yellow }",
    "",
    "intro",
    "00:00.500 --> 00:02.000 align:center line:90%",
    "Hello VTT",
    "",
    "00:00:02.000 --> 00:00:03.250 position:10%",
    "Second",
    "cue",
    ""
  ].join("\r\n");
  const folder = tempJob({ "voice.wav": "synthetic placeholder", "captions.vtt": vtt });

  const validation = validateJobFolder(folder);
  assert.equal(validation.valid, true, validation.errors.join("; "));
  assert.equal(validation.captionSource, "vtt");

  const job = discoverTypecastJob(folder);
  assert.deepEqual(simplify(job.cues), [
    { startSeconds: 0.5, endSeconds: 2, text: "Hello VTT" },
    { startSeconds: 2, endSeconds: 3.25, text: "Second cue" }
  ]);
  assert.deepEqual(simplify(parseSrt(formatSrt(job.cues))), simplify(job.cues));
  assert.deepEqual(simplify(parseVtt(vtt)), simplify(job.cues));
});

test("smoke: overlapping, empty and zero-length cues stay valid but warn", () => {
  const folder = tempJob({
    "voice.wav": "synthetic placeholder",
    "captions.srt": [
      "1", "00:00:01,000 --> 00:00:03,000", "First", "",
      "2", "00:00:02,500 --> 00:00:04,000", "Overlap", "",
      "3", "00:00:05,000 --> 00:00:05,000", "", ""
    ].join("\n")
  });

  const result = validateJobFolder(folder);
  assert.equal(result.valid, true);
  assert.equal(result.cueCount, 3);
  assert.ok(result.warnings.includes("Cue 2 overlaps cue 1."));
  assert.ok(result.warnings.includes("Cue 3 has empty text."));
  assert.ok(result.warnings.includes("Cue 3 has a non-positive duration."));
});

test("smoke: missing or empty folders are reported as invalid, not thrown", () => {
  const missing = join(tmpdir(), "typecast-smoke-does-not-exist-" + process.pid);
  assert.equal(existsSync(missing), false);
  const missingResult = validateJobFolder(missing);
  assert.equal(missingResult.valid, false);
  assert.ok(missingResult.errors[0].startsWith("Folder does not exist"));

  const empty = tempJob({});
  const emptyResult = validateJobFolder(empty);
  assert.equal(emptyResult.valid, false);
  assert.equal(emptyResult.captionSource, "none");
  assert.equal(emptyResult.errors.length, 2);
});

test("smoke: SRT timestamps format and clamp predictably", () => {
  assert.equal(secondsToSrtTimestamp(0), "00:00:00,000");
  assert.equal(secondsToSrtTimestamp(-5), "00:00:00,000");
  assert.equal(secondsToSrtTimestamp(Number.NaN), "00:00:00,000");
  assert.equal(secondsToSrtTimestamp(3723.4567), "01:02:03,457");
  assert.equal(secondsToSrtTimestamp(59.9996), "00:01:00,000");
  assert.equal(formatSrt([]), "");
});
