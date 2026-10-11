import { transitionBriansBrain } from "@/src/ca/rules/briansBrain";
import { transitionLifeLike } from "@/src/ca/rules/lifeLike";
import { transitionWireWorld } from "@/src/ca/rules/wireWorld";
import type { BoundaryMode, GridBuffer, RuleDefinition, TickStats } from "@/src/ca/types";

const NEIGHBOR_OFFSETS = [
  [-1, -1],
  [0, -1],
  [1, -1],
  [-1, 0],
  [1, 0],
  [-1, 1],
  [0, 1],
  [1, 1]
] as const;

export function stepAutomata(current: GridBuffer, next: GridBuffer, rule: RuleDefinition, boundary: BoundaryMode): TickStats {
  let births = 0;
  let deaths = 0;
  let population = 0;

  for (let y = 0; y < current.height; y += 1) {
    for (let x = 0; x < current.width; x += 1) {
      const index = y * current.width + x;
      const previous = current.cells[index];
      const neighbors = countNeighbors(current, x, y, boundary, 1);
      let value = 0;

      if (rule.kind === "life-like") {
        value = transitionLifeLike(previous, neighbors, rule);
      } else if (rule.kind === "brians-brain") {
        value = transitionBriansBrain(previous, neighbors);
      } else {
        value = transitionWireWorld(previous, neighbors);
      }

      next.cells[index] = value;

      if (previous === 0 && value > 0) {
        births += 1;
      } else if (previous > 0 && value === 0) {
        deaths += 1;
      }

      if (value > 0) {
        population += 1;
      }
    }
  }

  return { births, deaths, population };
}

function countNeighbors(grid: GridBuffer, x: number, y: number, boundary: BoundaryMode, targetState: number) {
  let count = 0;

  for (const [dx, dy] of NEIGHBOR_OFFSETS) {
    let nx = x + dx;
    let ny = y + dy;

    if (boundary === "toroidal") {
      nx = (nx + grid.width) % grid.width;
      ny = (ny + grid.height) % grid.height;
    } else if (nx < 0 || nx >= grid.width || ny < 0 || ny >= grid.height) {
      continue;
    }

    if (grid.cells[ny * grid.width + nx] === targetState) {
      count += 1;
    }
  }

  return count;
}

export function sanitizeGridForRule(grid: GridBuffer, rule: RuleDefinition) {
  const maximum = rule.states - 1;

  for (let index = 0; index < grid.cells.length; index += 1) {
    if (grid.cells[index] > maximum) {
      grid.cells[index] = grid.cells[index] > 0 ? maximum : 0;
    }

    if (rule.kind === "life-like" && grid.cells[index] > 1) {
      grid.cells[index] = 1;
    }
  }
}
