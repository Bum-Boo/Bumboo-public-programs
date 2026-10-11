import assert from "node:assert/strict";
import test from "node:test";
import { stepAutomata } from "../src/ca/engine";
import { RULES } from "../src/ca/rules";
import { createGrid, setCell } from "../src/utils/grid";
import { decodeState, encodeState, restoreCells } from "../src/utils/encoding";

test("Conway blinker advances from horizontal to vertical", () => {
  const current = createGrid(5, 5);
  const next = createGrid(5, 5);
  setCell(current, 1, 2, 1);
  setCell(current, 2, 2, 1);
  setCell(current, 3, 2, 1);

  const stats = stepAutomata(current, next, RULES.conway, "finite");

  assert.deepEqual([...next.cells], [
    0, 0, 0, 0, 0,
    0, 0, 1, 0, 0,
    0, 0, 1, 0, 0,
    0, 0, 1, 0, 0,
    0, 0, 0, 0, 0
  ]);
  assert.deepEqual(stats, { births: 2, deaths: 2, population: 3 });
});

test("encoded grids restore their rule, generation, and live cells", () => {
  const original = createGrid(7, 4);
  setCell(original, 2, 1, 1);
  setCell(original, 6, 3, 1);
  const decoded = decodeState(`#state=${encodeState(original, "highlife", 42)}`);
  assert.ok(decoded);
  assert.equal(decoded.rule, "highlife");
  assert.equal(decoded.generation, 42);

  const restored = createGrid(7, 4);
  restoreCells(decoded, restored);
  assert.deepEqual([...restored.cells], [...original.cells]);
});
