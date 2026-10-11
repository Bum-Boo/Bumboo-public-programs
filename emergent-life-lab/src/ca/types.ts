export type RuleId =
  | "conway"
  | "highlife"
  | "seeds"
  | "day-night"
  | "diamoeba"
  | "replicator"
  | "brians-brain"
  | "wireworld";

export type BoundaryMode = "toroidal" | "finite";

export type GridBuffer = {
  width: number;
  height: number;
  cells: Uint8Array;
};

export type TickStats = {
  births: number;
  deaths: number;
  population: number;
};

export type RuleDefinition = {
  id: RuleId;
  name: string;
  code: string;
  description: string;
  states: number;
  kind: "life-like" | "brians-brain" | "wireworld";
  birth?: ReadonlySet<number>;
  survive?: ReadonlySet<number>;
};

export type MetricsSnapshot = {
  generation: number;
  population: number;
  births: number;
  deaths: number;
  entropy: number;
  clusterCount: number;
  centerX: number;
  centerY: number;
  ruleName: string;
  tickRate: number;
};

export type PresetId =
  | "random"
  | "glider"
  | "lwss"
  | "pulsar"
  | "gosper"
  | "highlife-replicator"
  | "brians-wave"
  | "wireworld-diode"
  | "empty";

export type PatternPreset = {
  id: PresetId;
  name: string;
  description: string;
  recommendedRule?: RuleId;
};
