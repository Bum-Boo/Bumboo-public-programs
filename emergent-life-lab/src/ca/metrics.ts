import type { BoundaryMode, GridBuffer, MetricsSnapshot, RuleDefinition } from "@/src/ca/types";

const OFFSETS = [
  [-1, -1],
  [0, -1],
  [1, -1],
  [-1, 0],
  [1, 0],
  [-1, 1],
  [0, 1],
  [1, 1]
] as const;

export function computeMetrics(
  grid: GridBuffer,
  rule: RuleDefinition,
  generation: number,
  births: number,
  deaths: number,
  tickRate: number,
  boundary: BoundaryMode
): MetricsSnapshot {
  const counts = new Array(rule.states).fill(0) as number[];
  let population = 0;
  let weightedX = 0;
  let weightedY = 0;

  for (let index = 0; index < grid.cells.length; index += 1) {
    const value = Math.min(rule.states - 1, grid.cells[index]);
    counts[value] += 1;

    if (value > 0) {
      population += 1;
      weightedX += index % grid.width;
      weightedY += Math.floor(index / grid.width);
    }
  }

  return {
    generation,
    population,
    births,
    deaths,
    entropy: entropy(counts, grid.cells.length),
    clusterCount: countClusters(grid, boundary),
    centerX: population > 0 ? weightedX / population : grid.width / 2,
    centerY: population > 0 ? weightedY / population : grid.height / 2,
    ruleName: rule.name,
    tickRate
  };
}

function entropy(counts: readonly number[], total: number) {
  if (total === 0) {
    return 0;
  }

  let value = 0;
  for (const count of counts) {
    if (count === 0) {
      continue;
    }

    const probability = count / total;
    value -= probability * Math.log2(probability);
  }

  return value;
}

function countClusters(grid: GridBuffer, boundary: BoundaryMode) {
  const visited = new Uint8Array(grid.cells.length);
  const stack = new Int32Array(grid.cells.length);
  let clusters = 0;

  for (let start = 0; start < grid.cells.length; start += 1) {
    if (visited[start] || grid.cells[start] === 0) {
      continue;
    }

    clusters += 1;
    let stackLength = 1;
    stack[0] = start;
    visited[start] = 1;

    while (stackLength > 0) {
      const index = stack[--stackLength];
      const x = index % grid.width;
      const y = Math.floor(index / grid.width);

      for (const [dx, dy] of OFFSETS) {
        let nx = x + dx;
        let ny = y + dy;

        if (boundary === "toroidal") {
          nx = (nx + grid.width) % grid.width;
          ny = (ny + grid.height) % grid.height;
        } else if (nx < 0 || nx >= grid.width || ny < 0 || ny >= grid.height) {
          continue;
        }

        const next = ny * grid.width + nx;
        if (!visited[next] && grid.cells[next] > 0) {
          visited[next] = 1;
          stack[stackLength++] = next;
        }
      }
    }
  }

  return clusters;
}
