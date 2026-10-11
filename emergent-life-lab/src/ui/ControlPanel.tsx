import type { ReactNode } from "react";
import { PRESETS } from "@/src/ca/presets";
import { RULE_ORDER, RULES } from "@/src/ca/rules";
import type { BoundaryMode, PresetId, RuleId } from "@/src/ca/types";
import { Button } from "@/src/ui/Button";
import { Select } from "@/src/ui/Select";
import { Slider } from "@/src/ui/Slider";
import styles from "@/src/app/App.module.css";

type ControlPanelProps = {
  ruleId: RuleId;
  presetId: PresetId;
  playing: boolean;
  density: number;
  speed: number;
  brushSize: number;
  boundary: BoundaryMode;
  erasing: boolean;
  soundEnabled: boolean;
  shareStatus: string;
  onRuleChange: (ruleId: RuleId) => void;
  onPresetChange: (presetId: PresetId) => void;
  onPlayToggle: () => void;
  onStep: () => void;
  onReset: () => void;
  onClear: () => void;
  onRandomize: () => void;
  onDensityChange: (value: number) => void;
  onSpeedChange: (value: number) => void;
  onBrushSizeChange: (value: number) => void;
  onBoundaryChange: (value: BoundaryMode) => void;
  onEraseToggle: () => void;
  onSoundToggle: () => void;
  onExportPng: () => void;
  onCopyShare: () => void;
  onMinimize: () => void;
  onExit: () => void;
  observer?: ReactNode;
};

export function ControlPanel({
  ruleId,
  presetId,
  playing,
  density,
  speed,
  brushSize,
  boundary,
  erasing,
  soundEnabled,
  shareStatus,
  onRuleChange,
  onPresetChange,
  onPlayToggle,
  onStep,
  onReset,
  onClear,
  onRandomize,
  onDensityChange,
  onSpeedChange,
  onBrushSizeChange,
  onBoundaryChange,
  onEraseToggle,
  onSoundToggle,
  onExportPng,
  onCopyShare,
  onMinimize,
  onExit,
  observer
}: ControlPanelProps) {
  return (
    <aside className={styles.panel}>
      <div className={styles.panelHeader}>
        <div className={styles.panelHeading}>
          <p>Controls</p>
          <h2>Experiment setup</h2>
        </div>
        <div className={styles.panelActions} aria-label="Panel actions">
          <button type="button" className={styles.panelUtilityButton} data-danger="true" onClick={onExit}>
            Exit
          </button>
          <button type="button" className={styles.panelUtilityButton} onClick={onMinimize}>
            Minimize
          </button>
        </div>
      </div>

      <section className={styles.controlSection} aria-labelledby="rule-section-title">
        <div className={styles.sectionHeading}>
          <h3 id="rule-section-title">Rule</h3>
          <span>{RULES[ruleId].code}</span>
        </div>
        <div className={styles.fieldStack}>
          <Select label="Ruleset" value={ruleId} onChange={onRuleChange}>
            {RULE_ORDER.map((id) => (
              <option key={id} value={id}>
                {RULES[id].name} {RULES[id].code}
              </option>
            ))}
          </Select>

          <Select label="Pattern preset" value={presetId} onChange={onPresetChange}>
            {PRESETS.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.name}
              </option>
            ))}
          </Select>
        </div>
      </section>

      <section className={styles.controlSection} aria-labelledby="playback-section-title">
        <div className={styles.sectionHeading}>
          <h3 id="playback-section-title">Playback</h3>
          <span>{playing ? "Running" : "Paused"}</span>
        </div>
        <div className={`${styles.actionGrid} ${styles.playbackGrid}`}>
          <Button variant="primary" onClick={onPlayToggle}>
            {playing ? "Pause" : "Play"}
          </Button>
          <Button onClick={onStep}>Step</Button>
          <Button onClick={onReset}>Reset</Button>
          <Button variant="danger" onClick={onClear}>
            Clear
          </Button>
        </div>
      </section>

      <section className={styles.controlSection} aria-labelledby="parameters-section-title">
        <div className={styles.sectionHeading}>
          <h3 id="parameters-section-title">Parameters</h3>
          <span>{speed} Hz</span>
        </div>
        <div className={styles.fieldStack}>
          <Slider label="Speed" value={speed} min={1} max={60} suffix=" Hz" onChange={onSpeedChange} />
          <Slider label="Random density" value={density} min={1} max={75} suffix="%" hint="Used by Randomize and Random preset." onChange={onDensityChange} />
          <Slider label="Brush" value={brushSize} min={1} max={9} suffix=" cells" onChange={onBrushSizeChange} />

          <Select label="Boundary" value={boundary} onChange={onBoundaryChange}>
            <option value="toroidal">Toroidal wrap</option>
            <option value="finite">Finite edge</option>
          </Select>
        </div>
      </section>

      <section className={styles.controlSection} aria-labelledby="tools-section-title">
        <div className={styles.sectionHeading}>
          <h3 id="tools-section-title">Tools</h3>
          <span>{erasing ? "Erase" : "Paint"}</span>
        </div>
        <div className={`${styles.actionGrid} ${styles.toolsGrid}`}>
          <Button onClick={onRandomize}>Randomize</Button>
          <Button onClick={onEraseToggle} aria-pressed={erasing}>
            {erasing ? "Erase on" : "Paint"}
          </Button>
          <Button onClick={onSoundToggle} aria-pressed={soundEnabled}>
            {soundEnabled ? "Sound on" : "Sound off"}
          </Button>
          <Button onClick={onExportPng}>PNG</Button>
        </div>

        <Button className={styles.wideButton} onClick={onCopyShare}>
          Copy share state
        </Button>
        <p className={styles.shortStatus} aria-live="polite">
          {shareStatus || "Shortcuts: Space, S, R, C, E. Hold Alt while painting to erase."}
        </p>
      </section>

      {observer}
    </aside>
  );
}
