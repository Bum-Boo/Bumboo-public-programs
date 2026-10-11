import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  discoverTypecastJob,
  formatSrt,
  parseSrt,
  parseTypecastJson,
  parseVtt,
  secondsToTimecode,
  splitLongCue,
  validateJobFolder
} from "../dist/index.js";

test("parseSrt handles multiline cues", () => {
  const cues = parseSrt(`1
00:00:01,000 --> 00:00:03,500
Hello
world

2
00:00:04,000 --> 00:00:05,000
Next cue
`);

  assert.equal(cues.length, 2);
  assert.equal(cues[0].id, 1);
  assert.equal(cues[0].startSeconds, 1);
  assert.equal(cues[0].endSeconds, 3.5);
  assert.equal(cues[0].text, "Hello world");
});

test("parseSrt accepts comma and dot millisecond formats", () => {
  const cues = parseSrt(`1
00:00:01.250 --> 00:00:02,750
Mixed milliseconds
`);

  assert.equal(cues.length, 1);
  assert.equal(cues[0].startSeconds, 1.25);
  assert.equal(cues[0].endSeconds, 2.75);
});

test("parseSrt preserves empty cue entries", () => {
  const cues = parseSrt(`1
00:00:01,000 --> 00:00:02,000

2
00:00:03,000 --> 00:00:04,000
Text
`);

  assert.equal(cues.length, 2);
  assert.equal(cues[0].text, "");
});

test("parseVtt handles identifiers and cue settings", () => {
  const cues = parseVtt(`WEBVTT

intro
00:00:00.500 --> 00:00:02.000 align:center
Hello VTT
`);

  assert.equal(cues.length, 1);
  assert.equal(cues[0].startSeconds, 0.5);
  assert.equal(cues[0].text, "Hello VTT");
});

test("parseTypecastJson normalizes cue arrays", () => {
  const cues = parseTypecastJson({
    captions: [
      { start: 0, end: 1.2, text: " First  caption " },
      { start: 1.4, end: 2.1, text: "Second caption" }
    ]
  });

  assert.equal(cues.length, 2);
  assert.equal(cues[0].id, 1);
  assert.equal(cues[0].text, "First caption");
});

test("parseTypecastJson accepts UTF-8 BOM strings", () => {
  const cues = parseTypecastJson('\uFEFF{"captions":[{"start":0,"end":1,"text":"BOM caption"}]}');

  assert.equal(cues.length, 1);
  assert.equal(cues[0].text, "BOM caption");
});

test("parseTypecastJson groups word timestamps", () => {
  const cues = parseTypecastJson({
    words: [
      { word: "Hello", start: 0, end: 0.2 },
      { word: "world.", start: 0.25, end: 0.5 },
      { word: "Next", start: 1.4, end: 1.6 },
      { word: "line", start: 1.65, end: 1.9 }
    ]
  });

  assert.equal(cues.length, 2);
  assert.equal(cues[0].text, "Hello world.");
  assert.equal(cues[0].words.length, 2);
});

test("splitLongCue wraps very long cue text", () => {
  const wrapped = splitLongCue("This is a very long caption that should wrap across multiple readable lines", 24, 2);

  assert.match(wrapped, /\n/);
  assert.ok(wrapped.length > 24);
});

test("discoverTypecastJob warns about overlapping cues", () => {
  const folder = mkdtempSync(join(tmpdir(), "typecast-overlap-"));
  writeFileSync(join(folder, "voice.wav"), "placeholder");
  writeFileSync(
    join(folder, "captions.srt"),
    `1
00:00:01,000 --> 00:00:03,000
First

2
00:00:02,500 --> 00:00:04,000
Overlap
`
  );

  const job = discoverTypecastJob(folder);
  assert.equal(job.errors.length, 0);
  assert.ok(job.warnings.some((warning) => warning.includes("overlaps")));
});

test("validateJobFolder reports missing audio file", () => {
  const folder = mkdtempSync(join(tmpdir(), "typecast-missing-audio-"));
  writeFileSync(
    join(folder, "captions.srt"),
    `1
00:00:01,000 --> 00:00:02,000
Text
`
  );

  const result = validateJobFolder(folder);
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((error) => error.includes("Missing voice audio")));
});

test("validateJobFolder reports missing caption timing file", () => {
  const folder = mkdtempSync(join(tmpdir(), "typecast-missing-caption-"));
  writeFileSync(join(folder, "voice.mp3"), "placeholder");
  writeFileSync(join(folder, "script.txt"), "Script only");

  const result = validateJobFolder(folder);
  assert.equal(result.valid, false);
  assert.equal(result.captionSource, "script");
  assert.ok(result.warnings.some((warning) => warning.includes("accurate sync")));
});

test("formatSrt writes fallback SRT timing", () => {
  const output = formatSrt([{ id: 1, startSeconds: 1.2, endSeconds: 3.4, text: "Caption" }]);

  assert.match(output, /00:00:01,200 --> 00:00:03,400/);
});

test("secondsToTimecode rounds to frames", () => {
  assert.equal(secondsToTimecode(1.5, 30), "00:00:01:15");
});
