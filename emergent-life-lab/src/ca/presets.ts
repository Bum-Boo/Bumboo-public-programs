import type { GridBuffer, PatternPreset, PresetId, RuleDefinition, RuleId } from "@/src/ca/types";
import { clearGrid, randomizeGrid, setCell } from "@/src/utils/grid";

export const PRESETS: PatternPreset[] = [
  {
    id: "random",
    name: "Random field",
    description: "A stochastic starting point for seeing how each rule selects structure from noise."
  },
  {
    id: "glider",
    name: "Single glider",
    description: "A compact Conway Life spaceship that walks diagonally.",
    recommendedRule: "conway"
  },
  {
    id: "lwss",
    name: "Lightweight spaceship",
    description: "A wider mobile Life pattern with a stable period-four wake.",
    recommendedRule: "conway"
  },
  {
    id: "pulsar",
    name: "Pulsar",
    description: "A period-three oscillator useful for checking local rhythm and metrics.",
    recommendedRule: "conway"
  },
  {
    id: "gosper",
    name: "Gosper glider gun",
    description: "A classic Life emitter that periodically releases gliders.",
    recommendedRule: "conway"
  },
  {
    id: "highlife-replicator",
    name: "HighLife replicator",
    description: "The small seed that demonstrates HighLife's extra B6 replication behavior.",
    recommendedRule: "highlife"
  },
  {
    id: "brians-wave",
    name: "Brian's Brain wave seed",
    description: "Excited cells and refractory tails arranged to launch expanding wave fronts.",
    recommendedRule: "brians-brain"
  },
  {
    id: "wireworld-diode",
    name: "WireWorld diode-like sample",
    description: "Conductors, heads, and tails arranged as a compact signal-gating specimen.",
    recommendedRule: "wireworld"
  },
  {
    id: "empty",
    name: "Empty grid",
    description: "A cleared plate for direct painting.",
    recommendedRule: "conway"
  }
];

export function applyPreset(grid: GridBuffer, presetId: PresetId, rule: RuleDefinition, density: number) {
  clearGrid(grid);

  if (presetId === "random") {
    randomizeGrid(grid, density, rule.states - 1);
    return;
  }

  if (presetId === "empty") {
    return;
  }

  const centerX = Math.floor(grid.width / 2);
  const centerY = Math.floor(grid.height / 2);

  if (presetId === "glider") {
    drawPoints(grid, centerX - 2, centerY - 2, [
      [1, 0],
      [2, 1],
      [0, 2],
      [1, 2],
      [2, 2]
    ]);
  } else if (presetId === "lwss") {
    drawPoints(grid, centerX - 3, centerY - 2, [
      [1, 0],
      [4, 0],
      [0, 1],
      [0, 2],
      [4, 2],
      [0, 3],
      [1, 3],
      [2, 3],
      [3, 3]
    ]);
  } else if (presetId === "pulsar") {
    drawPoints(grid, centerX - 6, centerY - 6, pulsarPoints());
  } else if (presetId === "gosper") {
    drawPoints(grid, centerX - 18, centerY - 5, gosperPoints());
  } else if (presetId === "highlife-replicator") {
    // Canonical HighLife replicator (RLE 2b3o$bo2bo$o3bo$o2bo$3o!).
    drawPoints(grid, centerX - 2, centerY - 2, [
      [2, 0],
      [3, 0],
      [4, 0],
      [1, 1],
      [4, 1],
      [0, 2],
      [4, 2],
      [0, 3],
      [3, 3],
      [0, 4],
      [1, 4],
      [2, 4]
    ]);
  } else if (presetId === "brians-wave") {
    drawStatePoints(grid, centerX - 13, centerY - 5, [
      [0, 4, 1],
      [1, 4, 1],
      [2, 4, 2],
      [4, 3, 1],
      [5, 3, 1],
      [6, 3, 2],
      [8, 5, 1],
      [9, 5, 1],
      [10, 5, 2],
      [12, 2, 1],
      [13, 3, 1],
      [14, 4, 2],
      [17, 6, 1],
      [18, 5, 1],
      [19, 4, 2],
      [23, 3, 1],
      [24, 3, 1],
      [25, 3, 2]
    ]);
  } else if (presetId === "wireworld-diode") {
    drawWireWorldSample(grid, centerX - 17, centerY - 7);
  }
}

export function recommendedRuleForPreset(presetId: PresetId): RuleId | undefined {
  return PRESETS.find((preset) => preset.id === presetId)?.recommendedRule;
}

function drawPoints(grid: GridBuffer, originX: number, originY: number, points: readonly (readonly [number, number])[]) {
  for (const [x, y] of points) {
    setCell(grid, originX + x, originY + y, 1);
  }
}

function drawStatePoints(grid: GridBuffer, originX: number, originY: number, points: readonly (readonly [number, number, number])[]) {
  for (const [x, y, state] of points) {
    setCell(grid, originX + x, originY + y, state);
  }
}

function pulsarPoints() {
  const points: [number, number][] = [];
  const lines = [0, 5, 7, 12];
  const spans = [
    [2, 3, 4],
    [8, 9, 10]
  ];

  for (const y of lines) {
    for (const span of spans) {
      for (const x of span) {
        points.push([x, y]);
        points.push([y, x]);
      }
    }
  }

  return points;
}

function gosperPoints(): [number, number][] {
  return [
    [0, 4],
    [0, 5],
    [1, 4],
    [1, 5],
    [10, 4],
    [10, 5],
    [10, 6],
    [11, 3],
    [11, 7],
    [12, 2],
    [12, 8],
    [13, 2],
    [13, 8],
    [14, 5],
    [15, 3],
    [15, 7],
    [16, 4],
    [16, 5],
    [16, 6],
    [17, 5],
    [20, 2],
    [20, 3],
    [20, 4],
    [21, 2],
    [21, 3],
    [21, 4],
    [22, 1],
    [22, 5],
    [24, 0],
    [24, 1],
    [24, 5],
    [24, 6],
    [34, 2],
    [34, 3],
    [35, 2],
    [35, 3]
  ];
}

function drawWireWorldSample(grid: GridBuffer, originX: number, originY: number) {
  const conductor: [number, number][] = [];

  for (let x = 0; x <= 32; x += 1) {
    conductor.push([x, 7]);
  }

  for (let x = 12; x <= 20; x += 1) {
    conductor.push([x, 3], [x, 11]);
  }

  for (let y = 3; y <= 11; y += 1) {
    conductor.push([12, y], [20, y]);
  }

  for (const [x, y] of conductor) {
    setCell(grid, originX + x, originY + y, 3);
  }

  drawStatePoints(grid, originX, originY, [
    [2, 7, 1],
    [1, 7, 2],
    [13, 7, 1],
    [12, 7, 2],
    [22, 7, 1],
    [21, 7, 2]
  ]);
}
