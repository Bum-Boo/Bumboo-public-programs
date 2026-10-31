// Regression tests for defects reproduced during verification.
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { formatSrt, parseSrt, parseTypecastJson, parseVtt, splitLongCue, timestampToSeconds } from "../dist/index.js";
import { loadAeParser, loadPremierePanel } from "./helpers/panelHarness.mjs";

const msCaptions = {
  captions: [
    { start_ms: 1500, end_ms: 2500, text: "Millisecond cue" },
    { start_ms: 3000, duration_ms: 750, text: "Duration cue" }
  ]
};
const expectedMsCues = [
  { startSeconds: 1.5, endSeconds: 2.5, text: "Millisecond cue" },
  { startSeconds: 3, endSeconds: 3.75, text: "Duration cue" }
];

function simplify(cues) {
  // Array.from: arrays created inside the vm harness belong to another realm.
  return Array.from(cues, ({ startSeconds, endSeconds, text }) => ({ startSeconds, endSeconds, text }));
}

test("regression: parseTypecastJson reads documented *_ms fields as milliseconds", () => {
  assert.deepEqual(simplify(parseTypecastJson(msCaptions)), expectedMsCues);

  const words = parseTypecastJson({
    words: [
      { word: "Hello", start_ms: 0, end_ms: 200 },
      { word: "world.", start_ms: 250, end_ms: 500 }
    ]
  });
  assert.deepEqual(simplify(words), [{ startSeconds: 0, endSeconds: 0.5, text: "Hello world." }]);
});

test("regression: AE embedded parser reads *_ms fields", () => {
  const { TCSS_AE } = loadAeParser();
  assert.deepEqual(simplify(TCSS_AE.parseTypecastJson(JSON.stringify(msCaptions))), expectedMsCues);
});

test("regression: Premiere panel parser reads *_ms fields", async () => {
  const folder = mkdtempSync(join(tmpdir(), "typecast-ms-"));
  writeFileSync(join(folder, "voice.wav"), "synthetic placeholder");
  writeFileSync(join(folder, "typecast.json"), JSON.stringify(msCaptions));
  const panel = loadPremierePanel({ folderPath: folder });
  await panel.start();
  await panel.click("selectFolder");
  assert.match(panel.status(), /Source: typecast-json/);
  assert.match(panel.status(), /Cue count: 2/);
});

test("regression: SRT/VTT timestamps with 3+ digit hours round-trip through formatSrt", () => {
  const cues = [{ id: 1, startSeconds: 360000.5, endSeconds: 360001, text: "Long timeline" }];
  const srt = formatSrt(cues);
  assert.match(srt, /^1\n100:00:00,500 --> 100:00:01,000\n/);
  assert.deepEqual(simplify(parseSrt(srt)), simplify(cues));
  assert.deepEqual(simplify(parseVtt(`WEBVTT\n\n100:00:00.500 --> 100:00:01.000\nLong timeline\n`)), simplify(cues));
  assert.equal(timestampToSeconds("123:00:00,000"), 442800);

  const { TCSS_AE } = loadAeParser();
  assert.deepEqual(simplify(TCSS_AE.parseSrt(srt)), simplify(cues));
});

test("regression: splitLongCue with maxLines=1 keeps all text instead of truncating", () => {
  assert.equal(splitLongCue("aaa bbb ccc", 3, 1), "aaa bbb ccc");
  // Existing behaviour for maxLines >= 2 is unchanged: overflow goes on the last line.
  assert.equal(splitLongCue("aaa bbb ccc ddd", 3, 2), "aaa\nbbb ccc ddd");
  assert.equal(splitLongCue("aaa bbb ccc ddd", 3, 3), "aaa\nbbb\nccc ddd");
});

test("regression: AE embedded parser orders typecast.json cues by start time like the core", () => {
  const { TCSS_AE, Folder } = loadAeParser();
  const folder = mkdtempSync(join(tmpdir(), "typecast-ae-order-"));
  writeFileSync(join(folder, "voice.wav"), "synthetic placeholder");
  writeFileSync(
    join(folder, "typecast.json"),
    JSON.stringify({
      captions: [
        { start: 2, end: 3, text: "Later" },
        { start: 0, end: 1, text: "Earlier" }
      ]
    })
  );

  const job = TCSS_AE.discoverJobFolder(new Folder(folder));
  assert.deepEqual(Array.from(job.cues, (cue) => `${cue.id}:${cue.text}`), ["1:Earlier", "2:Later"]);
  assert.deepEqual(Array.from(job.warnings), []);
});

test("regression: panel parsers accept typecast.json with a UTF-8 BOM like the core", async () => {
  const bomJson = '﻿{"captions":[{"start":0,"end":1,"text":"BOM caption"}]}';
  const { TCSS_AE } = loadAeParser();
  assert.deepEqual(simplify(TCSS_AE.parseTypecastJson(bomJson)), [{ startSeconds: 0, endSeconds: 1, text: "BOM caption" }]);

  // Note: the fake UXP read returns the raw file text; whether real UXP strips a BOM is unverified.
  const folder = mkdtempSync(join(tmpdir(), "typecast-bom-"));
  writeFileSync(join(folder, "voice.wav"), "synthetic placeholder");
  writeFileSync(join(folder, "typecast.json"), bomJson);
  const panel = loadPremierePanel({ folderPath: folder });
  await panel.start();
  await panel.click("selectFolder");
  assert.match(panel.status(), /Source: typecast-json/);
  assert.doesNotMatch(panel.status(), /Could not parse typecast\.json/);
});
