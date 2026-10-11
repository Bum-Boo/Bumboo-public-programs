import type { RuleDefinition, RuleId } from "@/src/ca/types";

function setOf(values: readonly number[]) {
  return new Set(values);
}

export const LIFE_LIKE_RULES: Record<Exclude<RuleId, "brians-brain" | "wireworld">, RuleDefinition> = {
  conway: {
    id: "conway",
    name: "Conway Life",
    code: "B3/S23",
    description: "The canonical balance of extinction, still life, oscillators, and mobile gliders.",
    states: 2,
    kind: "life-like",
    birth: setOf([3]),
    survive: setOf([2, 3])
  },
  highlife: {
    id: "highlife",
    name: "HighLife",
    code: "B36/S23",
    description: "Life with an extra birth condition that can produce self-replicating structures.",
    states: 2,
    kind: "life-like",
    birth: setOf([3, 6]),
    survive: setOf([2, 3])
  },
  seeds: {
    id: "seeds",
    name: "Seeds",
    code: "B2/S",
    description: "Explosive growth where every live cell dies and exact pairs seed the next front.",
    states: 2,
    kind: "life-like",
    birth: setOf([2]),
    survive: setOf([])
  },
  "day-night": {
    id: "day-night",
    name: "Day & Night",
    code: "B3678/S34678",
    description: "A symmetric rule where dense and sparse regions mirror each other.",
    states: 2,
    kind: "life-like",
    birth: setOf([3, 6, 7, 8]),
    survive: setOf([3, 4, 6, 7, 8])
  },
  diamoeba: {
    id: "diamoeba",
    name: "Diamoeba",
    code: "B35678/S5678",
    description: "Blob-like regions accrete, split, and settle into amoebic borders.",
    states: 2,
    kind: "life-like",
    birth: setOf([3, 5, 6, 7, 8]),
    survive: setOf([5, 6, 7, 8])
  },
  replicator: {
    id: "replicator",
    name: "Replicator",
    code: "B1357/S1357",
    description: "Parity-like dynamics that copy simple seeds into recursive diamond waves.",
    states: 2,
    kind: "life-like",
    birth: setOf([1, 3, 5, 7]),
    survive: setOf([1, 3, 5, 7])
  }
};

export function transitionLifeLike(current: number, aliveNeighbors: number, rule: RuleDefinition): 0 | 1 {
  if (current === 1) {
    return rule.survive?.has(aliveNeighbors) ? 1 : 0;
  }

  return rule.birth?.has(aliveNeighbors) ? 1 : 0;
}
