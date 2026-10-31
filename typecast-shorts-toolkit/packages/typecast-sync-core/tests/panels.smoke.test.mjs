// Smoke tests for the parser/job-discovery JavaScript embedded in the Adobe
// panels, run under Node with fake host objects (see helpers/panelHarness.mjs).
// NOT covered here: After Effects/Premiere Pro runtime behaviour (footage
// import, layer creation, caption tracks, UXP permissions) - that needs the
// Adobe hosts, which cannot run in CI.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { parseSrt } from "../dist/index.js";
import { loadAeParser, loadPremierePanel, toolkitRoot } from "./helpers/panelHarness.mjs";

const sampleFolder = join(toolkitRoot, "samples", "synthetic");
const premiereSrc = join(toolkitRoot, "apps", "premiere-typecast-sync", "src");

function tempJob(files) {
  const folder = mkdtempSync(join(tmpdir(), "typecast-panel-smoke-"));
  for (const [name, contents] of Object.entries(files)) {
    writeFileSync(join(folder, name), contents);
  }
  return folder;
}

function simplify(cues) {
  // Array.from: arrays created inside the vm harness belong to another realm.
  return Array.from(cues, ({ startSeconds, endSeconds, text }) => ({ startSeconds, endSeconds, text }));
}

test("AE parser (Node shim): discovers bundled synthetic job like the core", () => {
  const { TCSS_AE, Folder } = loadAeParser();
  const job = TCSS_AE.discoverJobFolder(new Folder(sampleFolder));

  assert.deepEqual(Array.from(job.errors), []);
  assert.equal(job.captionSource, "srt");
  assert.equal(job.audioFile.name, "voice.wav");
  assert.equal(job.captionFile.name, "captions.srt");
  assert.deepEqual(simplify(job.cues), simplify(parseSrt(readFileSync(join(sampleFolder, "captions.srt"), "utf8"))));
  assert.match(TCSS_AE.formatJobStatus(job, { name: "SYNTHETIC_COMP" }), /Cue count: 2/);
});

test("AE parser (Node shim): VTT with CRLF/BOM, identifiers and cue settings", () => {
  const { TCSS_AE, Folder } = loadAeParser();
  const folder = tempJob({
    "voice.mp3": "synthetic placeholder",
    "captions.vtt": "WEBVTT\r\n\r\nintro\r\n00:00.500 --> 00:02.000 align:center\r\nHello  VTT\r\n\r\n00:00:02.000 --> 00:00:03.000\r\nNext\r\n"
  });

  const job = TCSS_AE.discoverJobFolder(new Folder(folder));
  assert.deepEqual(Array.from(job.errors), []);
  assert.equal(job.captionSource, "vtt");
  assert.deepEqual(simplify(job.cues), [
    { startSeconds: 0.5, endSeconds: 2, text: "Hello VTT" },
    { startSeconds: 2, endSeconds: 3, text: "Next" }
  ]);
});

test("AE parser (Node shim): typecast.json cues win, overlaps warn, script-only fails", () => {
  const { TCSS_AE, Folder } = loadAeParser();
  const jsonJob = TCSS_AE.discoverJobFolder(
    new Folder(
      tempJob({
        "voice.wav": "synthetic placeholder",
        "captions.srt": "1\n00:00:00,000 --> 00:00:09,000\nIgnored\n",
        "typecast.json": JSON.stringify({
          captions: [
            { start: 1, end: 2.5, text: " Second " },
            { start: 0, end: 1.2, text: "First" }
          ]
        })
      })
    )
  );
  assert.equal(jsonJob.captionSource, "typecast-json");
  assert.deepEqual(simplify(jsonJob.cues), [
    { startSeconds: 0, endSeconds: 1.2, text: "First" },
    { startSeconds: 1, endSeconds: 2.5, text: "Second" }
  ]);
  assert.ok(Array.from(jsonJob.warnings).includes("Cue 2 overlaps cue 1."));

  const scriptOnly = TCSS_AE.discoverJobFolder(new Folder(tempJob({ "script.txt": "Synthetic script only" })));
  assert.equal(scriptOnly.captionSource, "script");
  assert.equal(scriptOnly.errors.length, 2);
});

test("Premiere panel main.js (mocked UXP): select bundled-style folder, generate fallback SRT, import paths", async () => {
  const folder = tempJob({
    "voice.wav": readFileSync(join(sampleFolder, "voice.wav")),
    "captions.srt": readFileSync(join(sampleFolder, "captions.srt"))
  });
  const imports = [];
  const project = {
    async getActiveSequence() {
      return { name: "SYNTHETIC_SEQUENCE" };
    },
    async getRootItem() {
      return "root-bin";
    },
    async importFiles(paths, suppressUI, targetBin, asNumberedStills) {
      imports.push({ paths, suppressUI, targetBin, asNumberedStills });
      return true;
    }
  };

  const panel = loadPremierePanel({ folderPath: folder, project });
  await panel.start();
  assert.match(panel.status(), /Active sequence: SYNTHETIC_SEQUENCE/);

  await panel.click("selectFolder");
  assert.equal(panel.elements.generate.disabled, false, panel.status());
  assert.match(panel.status(), /Source: srt/);
  assert.match(panel.status(), /Cue count: 2/);

  await panel.click("generate");
  const fallback = join(folder, "typecast_sync_fallback.srt");
  assert.ok(existsSync(fallback));
  assert.equal(readFileSync(fallback, "utf8"), readFileSync(join(sampleFolder, "captions.srt"), "utf8"));
  assert.equal(imports.length, 1);
  assert.deepEqual(Array.from(imports[0].paths), [join(folder, "voice.wav"), fallback]);
  assert.equal(imports[0].targetBin, "root-bin");
  assert.match(panel.status(), /Imported audio and fallback SRT/);
});

test("Premiere panel main.js (mocked UXP): invalid folder keeps Generate disabled; no project is a warning", async () => {
  const scriptOnly = tempJob({ "script.txt": "Synthetic script only" });
  const invalidPanel = loadPremierePanel({ folderPath: scriptOnly });
  await invalidPanel.start();
  assert.match(invalidPanel.status(), /Active sequence: No active sequence/);
  await invalidPanel.click("selectFolder");
  assert.equal(invalidPanel.elements.generate.disabled, true);
  assert.match(invalidPanel.status(), /Missing voice audio file/);
  assert.match(invalidPanel.status(), /Missing usable caption timing file/);

  const vttFolder = tempJob({
    "voice.mp3": "synthetic placeholder",
    "captions.vtt": "﻿WEBVTT\r\n\r\n1\r\n00:00:00.000 --> 00:00:01.000 align:start\r\nVTT cue\r\n"
  });
  const noProjectPanel = loadPremierePanel({ folderPath: vttFolder, project: null });
  await noProjectPanel.start();
  await noProjectPanel.click("selectFolder");
  assert.match(noProjectPanel.status(), /Source: vtt/);
  await noProjectPanel.click("generate");
  assert.equal(
    readFileSync(join(vttFolder, "typecast_sync_fallback.srt"), "utf8"),
    "1\n00:00:00,000 --> 00:00:01,000\nVTT cue\n"
  );
  assert.match(noProjectPanel.status(), /Project import warning: No active Premiere Pro project\./);
});

test("Premiere manifest.json is valid JSON and references files that exist", () => {
  const manifest = JSON.parse(readFileSync(join(premiereSrc, "manifest.json"), "utf8"));
  assert.equal(manifest.manifestVersion, 5);
  assert.equal(manifest.host.app, "premierepro");
  assert.ok(existsSync(join(premiereSrc, manifest.main)), `missing ${manifest.main}`);

  const html = readFileSync(join(premiereSrc, manifest.main), "utf8");
  for (const [, src] of html.matchAll(/<script[^>]*src="([^"]+)"/g)) {
    assert.ok(existsSync(join(premiereSrc, src)), `index.html references missing ${src}`);
  }
  for (const id of ["refreshSequence", "selectFolder", "generate", "status"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }

  const panelIds = manifest.entrypoints.filter((entry) => entry.type === "panel").map((entry) => entry.id);
  const mainJs = readFileSync(join(premiereSrc, "main.js"), "utf8");
  for (const id of panelIds) {
    assert.match(mainJs, new RegExp(`\\b${id}\\s*:`), `main.js does not set up panel ${id}`);
  }
});

test("Adobe host runtime (After Effects / Premiere Pro)", { skip: "Requires Adobe After Effects / Premiere Pro; cannot run on Linux CI" }, () => {});
