import { BRIANS_BRAIN_RULE } from "@/src/ca/rules/briansBrain";
import { LIFE_LIKE_RULES } from "@/src/ca/rules/lifeLike";
import { WIREWORLD_RULE } from "@/src/ca/rules/wireWorld";
import type { RuleDefinition, RuleId } from "@/src/ca/types";

export const RULES: Record<RuleId, RuleDefinition> = {
  ...LIFE_LIKE_RULES,
  "brians-brain": BRIANS_BRAIN_RULE,
  wireworld: WIREWORLD_RULE
};

export const RULE_ORDER: RuleId[] = [
  "conway",
  "highlife",
  "seeds",
  "day-night",
  "diamoeba",
  "replicator",
  "brians-brain",
  "wireworld"
];
