import assert from "node:assert/strict";
import test from "node:test";
import { sanitizeGridForRule, stepAutomata } from "../src/ca/engine";
import { computeMetrics } from "../src/ca/metrics";
import { applyPreset, PRESETS, recommendedRuleForPreset } from "../src/ca/presets";
import { RULE_ORDER, RULES } from "../src/ca/rules";
import type { BoundaryMode, GridBuffer, PresetId, RuleId } from "../src/ca/types";
import { decodeState, encodeState, exportStateJson, restoreCells } from "../src/utils/encoding";
import { createGrid, paintDisc, setCell } from "../src/utils/grid";

// The app uses a fixed 128x80 plate; the smoke tests use the same size so presets land where the UI puts them.
const WIDTH = 128;
const HEIGHT = 80;

function run(grid: GridBuffer, ruleId: RuleId, generations: number, boundary: BoundaryMode = "toroidal") {
  let current = grid;
  let next = createGrid(grid.width, grid.height);
  const populations: number[] = [];
  for (let generation = 0; generation < generations; generation += 1) {
    const stats = stepAutomata(current, next, RULES[ruleId], boundary);
    populations.push(stats.population);
    [current, next] = [next, current];
  }
  return { grid: current, populations };
}

function presetGrid(presetId: PresetId, ruleId: RuleId = recommendedRuleForPreset(presetId) ?? "conway") {
  const grid = createGrid(WIDTH, HEIGHT);
  applyPreset(grid, presetId, RULES[ruleId], 0.28);
  return grid;
}

function encodeHash(payload: unknown) {
  return `#state=${Buffer.from(JSON.stringify(payload)).toString("base64url")}`;
}

test("smoke: every rule in the selector steps a seeded grid without leaving its state range", () => {
  assert.deepEqual([...RULE_ORDER].sort(), Object.keys(RULES).sort());

  for (const ruleId of RULE_ORDER) {
    const rule = RULES[ruleId];
    const grid = createGrid(32, 24);
    for (let index = 0; index < grid.cells.length; index += 1) {
      grid.cells[index] = (index * 7 + (index >> 3)) % rule.states;
    }

    for (const boundary of ["toroidal", "finite"] as const) {
      const { grid: result, populations } = run(grid, ruleId, 8, boundary);
      assert.equal(populations.length, 8);
      assert.ok(result.cells.every((value) => value < rule.states), `${ruleId} produced an out-of-range state`);
      const metrics = computeMetrics(result, rule, 8, 0, 0, 0, boundary);
      assert.equal(metrics.ruleName, rule.name);
      assert.equal(metrics.population, result.cells.filter((value) => value > 0).length);
      assert.ok(metrics.entropy >= 0 && metrics.entropy <= Math.log2(rule.states) + 1e-9);
    }
  }
});

test("smoke: Brian's Brain fires on exactly two firing neighbours and decays through refractory", () => {
  const current = createGrid(5, 5);
  const next = createGrid(5, 5);
  setCell(current, 1, 2, 1);
  setCell(current, 3, 2, 1);
  setCell(current, 2, 0, 2);

  stepAutomata(current, next, RULES["brians-brain"], "finite");

  assert.equal(next.cells[2 * 5 + 2], 1, "dead cell with two firing neighbours fires");
  assert.equal(next.cells[2 * 5 + 1], 2, "firing cell becomes refractory");
  assert.equal(next.cells[0 * 5 + 2], 0, "refractory cell dies");
});

test("smoke: WireWorld electron travels along a conductor", () => {
  const current = createGrid(8, 3);
  const next = createGrid(8, 3);
  for (let x = 0; x < 8; x += 1) {
    setCell(current, x, 1, 3);
  }
  setCell(current, 1, 1, 2);
  setCell(current, 2, 1, 1);

  const { grid } = run(current, "wireworld", 3, "finite");
  void next;
  assert.deepEqual([...grid.cells.subarray(8, 16)], [3, 3, 3, 3, 2, 1, 3, 3]);
});

test("smoke: Conway glider translates one cell diagonally every four generations", () => {
  const grid = presetGrid("glider");
  const start = [...grid.cells];
  const { grid: after } = run(grid, "conway", 4);
  const shifted = new Array(WIDTH * HEIGHT).fill(0);
  start.forEach((value, index) => {
    if (value) {
      const x = (index % WIDTH) + 1;
      const y = Math.floor(index / WIDTH) + 1;
      shifted[y * WIDTH + x] = 1;
    }
  });
  assert.deepEqual([...after.cells], shifted);
});

test("smoke: pulsar is a period-3 oscillator and the LWSS keeps a 9/12 cell rhythm", () => {
  const pulsar = presetGrid("pulsar");
  const start = [...pulsar.cells];
  assert.equal(start.filter(Boolean).length, 48);
  const { grid: afterThree, populations } = run(pulsar, "conway", 3);
  assert.deepEqual(populations, [56, 72, 48]);
  assert.deepEqual([...afterThree.cells], start);

  const { populations: lwss } = run(presetGrid("lwss"), "conway", 8);
  assert.deepEqual(lwss, [12, 9, 12, 9, 12, 9, 12, 9]);
});

test("smoke: Gosper glider gun keeps emitting so population grows", () => {
  const { populations, grid } = run(presetGrid("gosper"), "conway", 120);
  assert.ok(populations[119] > 36 + 5 * 3, `expected emitted gliders, got population ${populations[119]}`);
  assert.ok(computeMetrics(grid, RULES.conway, 120, 0, 0, 0, "toroidal").clusterCount > 3);
});

test("smoke: every preset applies cleanly with its recommended rule and stays alive briefly", () => {
  for (const preset of PRESETS) {
    const ruleId = preset.recommendedRule ?? "conway";
    const grid = presetGrid(preset.id, ruleId);
    const rule = RULES[ruleId];
    assert.ok(grid.cells.every((value) => value < rule.states), `${preset.id} wrote a state ${ruleId} cannot hold`);

    if (preset.id === "empty") {
      assert.equal(grid.cells.some(Boolean), false);
      continue;
    }

    assert.ok(grid.cells.some(Boolean), `${preset.id} drew nothing`);
    const { populations } = run(grid, ruleId, 10);
    assert.ok(populations[9] > 0, `${preset.id} died out within 10 generations under ${ruleId}`);
  }
});

test("regression: HighLife replicator preset actually replicates under B36/S23", () => {
  const grid = presetGrid("highlife-replicator");
  assert.equal(grid.cells.filter(Boolean).length, 12);
  const { populations } = run(grid, "highlife", 36);
  // The canonical replicator makes two copies of itself by generation 12 and four by generation 36.
  assert.equal(populations[11], 24);
  assert.equal(populations[35], 48);
});

test("smoke: share hash round-trips every rule with multi-state cells", () => {
  for (const ruleId of RULE_ORDER) {
    const rule = RULES[ruleId];
    const original = createGrid(WIDTH, HEIGHT);
    applyPreset(original, "random", rule, 0.4);
    paintDisc(original, 10, 10, 3, rule.states - 1);

    const hash = `#state=${encodeState(original, ruleId, 1234)}`;
    assert.match(hash, /^#state=[A-Za-z0-9_-]+$/, "hash must be URL-safe base64");
    const decoded = decodeState(hash);
    assert.ok(decoded, `${ruleId} hash failed to decode`);
    assert.equal(decoded.rule, ruleId);
    assert.equal(decoded.generation, 1234);
    assert.equal(decoded.width, WIDTH);
    assert.equal(decoded.height, HEIGHT);

    const restored = createGrid(WIDTH, HEIGHT);
    restoreCells(decoded, restored);
    sanitizeGridForRule(restored, rule);
    assert.deepEqual([...restored.cells], [...original.cells]);
  }

  // A long uniform run crosses the 9999-cell chunk limit of the run-length encoder.
  const big = createGrid(200, 120);
  big.cells.fill(1);
  const restoredBig = createGrid(200, 120);
  const decodedBig = decodeState(`state=${encodeState(big, "seeds", 0)}`);
  assert.ok(decodedBig);
  restoreCells(decodedBig, restoredBig);
  assert.ok(restoredBig.cells.every((value) => value === 1));
});

test("smoke: JSON export lists every cell", () => {
  const grid = createGrid(3, 2);
  setCell(grid, 1, 1, 1);
  const parsed = JSON.parse(exportStateJson(grid, "conway", 5));
  assert.deepEqual(parsed, { version: 1, width: 3, height: 2, rule: "conway", generation: 5, cells: [0, 0, 0, 0, 1, 0] });
});

test("decodeState rejects hashes that are not share state", () => {
  assert.equal(decodeState(""), null);
  assert.equal(decodeState("#other=1"), null);
  assert.equal(decodeState("#state=%%%not-base64"), null);
  assert.equal(decodeState(encodeHash({ version: 2, width: 128, height: 80, rule: "conway", generation: 0, cells: "" })), null);
});

test("regression: decodeState rejects a missing or non-numeric generation", () => {
  // These used to reach MetricsPanel and crash the whole app on `generation.toLocaleString()`.
  const base = { version: 1, width: WIDTH, height: HEIGHT, rule: "conway", cells: "0.a,1.3" };
  assert.equal(decodeState(encodeHash(base)), null);
  assert.equal(decodeState(encodeHash({ ...base, generation: null })), null);
  assert.equal(decodeState(encodeHash({ ...base, generation: "7" })), null);
  assert.equal(decodeState(encodeHash({ ...base, generation: -1 })), null);
  assert.equal(decodeState(encodeHash({ ...base, generation: 1.5 })), null);
  assert.ok(decodeState(encodeHash({ ...base, generation: 0 })));
});

test("regression: decodeState rejects rules that are only inherited object keys", () => {
  // `"constructor" in RULES` is true, which used to load Object as the active rule.
  const base = { version: 1, width: WIDTH, height: HEIGHT, generation: 1, cells: "0.a,1.3" };
  for (const rule of ["constructor", "toString", "__proto__", "hasOwnProperty", "life", 3]) {
    assert.equal(decodeState(encodeHash({ ...base, rule })), null, `rule ${String(rule)} should be rejected`);
  }
  assert.equal(decodeState(encodeHash({ ...base, rule: "brians-brain" }))?.rule, "brians-brain");
});

test("regression: decodeState rejects non-integer or non-positive grid sizes", () => {
  const base = { version: 1, rule: "conway", generation: 1, cells: "0.a,1.3" };
  assert.equal(decodeState(encodeHash({ ...base, width: 0, height: HEIGHT })), null);
  assert.equal(decodeState(encodeHash({ ...base, width: WIDTH, height: -80 })), null);
  assert.equal(decodeState(encodeHash({ ...base, width: 12.5, height: HEIGHT })), null);
});
