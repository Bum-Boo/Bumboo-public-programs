import type { RuleDefinition } from "@/src/ca/types";

export const BRIANS_BRAIN_RULE: RuleDefinition = {
  id: "brians-brain",
  name: "Brian's Brain",
  code: "3-state",
  description: "Excited cells decay through a refractory state, forming waves and filaments.",
  states: 3,
  kind: "brians-brain"
};

export function transitionBriansBrain(current: number, aliveNeighbors: number): 0 | 1 | 2 {
  if (current === 0) {
    return aliveNeighbors === 2 ? 1 : 0;
  }

  if (current === 1) {
    return 2;
  }

  return 0;
}
