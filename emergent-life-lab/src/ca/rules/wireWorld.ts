import type { RuleDefinition } from "@/src/ca/types";

export const WIREWORLD_RULE: RuleDefinition = {
  id: "wireworld",
  name: "WireWorld",
  code: "4-state",
  description: "Electron heads and tails travel through conductors, useful for logic-like circuits.",
  states: 4,
  kind: "wireworld"
};

export function transitionWireWorld(current: number, electronHeads: number): 0 | 1 | 2 | 3 {
  if (current === 1) {
    return 2;
  }

  if (current === 2) {
    return 3;
  }

  if (current === 3) {
    return electronHeads === 1 || electronHeads === 2 ? 1 : 3;
  }

  return 0;
}
