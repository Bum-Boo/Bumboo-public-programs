
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EmergentAudioEngine } from "@/src/audio/audioEngine";
import { stepAutomata, sanitizeGridForRule } from "@/src/ca/engine";
import { computeMetrics } from "@/src/ca/metrics";
import { applyPreset, recommendedRuleForPreset } from "@/src/ca/presets";
import { RULES } from "@/src/ca/rules";
import type { BoundaryMode, GridBuffer, MetricsSnapshot, PresetId, RuleId } from "@/src/ca/types";
import { CanvasAutomata, type CanvasAutomataHandle } from "@/src/render/CanvasAutomata";
import { ControlPanel } from "@/src/ui/ControlPanel";
import { MetricsPanel } from "@/src/ui/MetricsPanel";
import { TopBar } from "@/src/ui/TopBar";
import { decodeState, encodeState, exportStateJson, restoreCells } from "@/src/utils/encoding";
import { createGrid, paintDisc, randomizeGrid } from "@/src/utils/grid";
import styles from "@/src/app/App.module.css";

const GRID_WIDTH = 128;
const GRID_HEIGHT = 80;
const DEFAULT_RULE: RuleId = "conway";
const DEFAULT_PRESET: PresetId = "gosper";

function emptyMetrics(ruleName: string): MetricsSnapshot {
  return {
    generation: 0,
    population: 0,
    births: 0,
    deaths: 0,
    entropy: 0,
    clusterCount: 0,
    centerX: GRID_WIDTH / 2,
    centerY: GRID_HEIGHT / 2,
    ruleName,
    tickRate: 0
  };
}

export default function App() {
  const [ruleId, setRuleId] = useState<RuleId>(DEFAULT_RULE);
  const [presetId, setPresetId] = useState<PresetId>(DEFAULT_PRESET);
  const [playing, setPlaying] = useState(true);
  const [density, setDensity] = useState(28);
  const [speed, setSpeed] = useState(12);
  const [brushSize, setBrushSize] = useState(2);
  const [boundary, setBoundary] = useState<BoundaryMode>("toroidal");
  const [erasing, setErasing] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [shareStatus, setShareStatus] = useState("");
  const [sparkline, setSparkline] = useState<number[]>([]);
  const [metrics, setMetrics] = useState<MetricsSnapshot>(() => emptyMetrics(RULES[DEFAULT_RULE].name));
  const [controlsMinimized, setControlsMinimized] = useState(false);
  const [fullscreenActive, setFullscreenActive] = useState(false);

  const shellRef = useRef<HTMLDivElement | null>(null);
  const currentGridRef = useRef<GridBuffer>(createGrid(GRID_WIDTH, GRID_HEIGHT));
  const nextGridRef = useRef<GridBuffer>(createGrid(GRID_WIDTH, GRID_HEIGHT));
  const canvasRef = useRef<CanvasAutomataHandle | null>(null);
  const generationRef = useRef(0);
  const ruleIdRef = useRef(ruleId);
  const boundaryRef = useRef(boundary);
  const metricsRef = useRef(metrics);
  const audioRef = useRef<EmergentAudioEngine | null>(null);
  const tickTimesRef = useRef<number[]>([]);

  const rule = useMemo(() => RULES[ruleId], [ruleId]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setFullscreenActive(document.fullscreenElement === shellRef.current);
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);

    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
    };
  }, []);

  const toggleFullscreen = useCallback(() => {
    const shell = shellRef.current;

    if (!shell) {
      return;
    }

    if (document.fullscreenElement === shell) {
      void document.exitFullscreen();
      return;
    }

    void shell.requestFullscreen();
  }, []);

  const publishMetrics = useCallback(
    (stats: { births: number; deaths: number; population: number }, now: number) => {
      const times = tickTimesRef.current;
      times.push(now);
      while (times.length > 24) {
        times.shift();
      }

      const elapsed = times.length > 1 ? (times[times.length - 1] - times[0]) / 1000 : 0;
      const tickRate = elapsed > 0 ? (times.length - 1) / elapsed : 0;
      const nextMetrics = computeMetrics(
        currentGridRef.current,
        RULES[ruleIdRef.current],
        generationRef.current,
        stats.births,
        stats.deaths,
        tickRate,
        boundaryRef.current
      );

      metricsRef.current = nextMetrics;
      audioRef.current?.update(nextMetrics, GRID_WIDTH, GRID_HEIGHT);

      setMetrics(nextMetrics);
      setSparkline((values) => [...values.slice(-95), nextMetrics.population]);
    },
    []
  );

  const stepOnce = useCallback(
    () => {
      const stats = stepAutomata(currentGridRef.current, nextGridRef.current, RULES[ruleIdRef.current], boundaryRef.current);
      const previous = currentGridRef.current;
      currentGridRef.current = nextGridRef.current;
      nextGridRef.current = previous;
      generationRef.current += 1;
      publishMetrics(stats, performance.now());
    },
    [publishMetrics]
  );

  const resetWithPreset = useCallback(
    (nextPreset: PresetId, nextRuleId = ruleIdRef.current) => {
      const nextRule = RULES[nextRuleId];
      applyPreset(currentGridRef.current, nextPreset, nextRule, density / 100);
      nextGridRef.current.cells.fill(0);
      generationRef.current = 0;
      tickTimesRef.current = [];
      const nextMetrics = computeMetrics(currentGridRef.current, nextRule, 0, 0, 0, 0, boundaryRef.current);
      metricsRef.current = nextMetrics;
      setMetrics(nextMetrics);
      setSparkline([nextMetrics.population]);
      canvasRef.current?.drawNow();
    },
    [density]
  );

  useEffect(() => {
    const encoded = decodeState(window.location.hash);
    if (encoded && encoded.width === GRID_WIDTH && encoded.height === GRID_HEIGHT && Object.hasOwn(RULES, encoded.rule)) {
      restoreCells(encoded, currentGridRef.current);
      generationRef.current = encoded.generation;
      // The shared-state hash only exists on the client, so it is restored after hydration.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRuleId(encoded.rule);
      ruleIdRef.current = encoded.rule;
      setPresetId("empty");
      sanitizeGridForRule(currentGridRef.current, RULES[encoded.rule]);
      const nextMetrics = computeMetrics(currentGridRef.current, RULES[encoded.rule], generationRef.current, 0, 0, 0, boundaryRef.current);
      metricsRef.current = nextMetrics;
      setMetrics(nextMetrics);
      setSparkline([nextMetrics.population]);
    } else {
      resetWithPreset(DEFAULT_PRESET, DEFAULT_RULE);
    }
  }, [resetWithPreset]);

  useEffect(() => {
    boundaryRef.current = boundary;
  }, [boundary]);

  useEffect(() => {
    ruleIdRef.current = ruleId;
  }, [ruleId]);

  useEffect(() => {
    audioRef.current = new EmergentAudioEngine();
    return () => audioRef.current?.dispose();
  }, []);

  useEffect(() => {
    if (!playing) {
      return;
    }

    const intervalId = window.setInterval(() => {
      stepOnce();
    }, 1000 / Math.max(1, speed));

    return () => window.clearInterval(intervalId);
  }, [playing, speed, stepOnce]);

  const changeRule = (nextRuleId: RuleId) => {
    const nextRule = RULES[nextRuleId];
    setRuleId(nextRuleId);
    ruleIdRef.current = nextRuleId;
    sanitizeGridForRule(currentGridRef.current, nextRule);
    generationRef.current = 0;

    const recommended = recommendedRuleForPreset(presetId);
    if (recommended && recommended !== nextRuleId) {
      setPresetId("empty");
    }

    const nextMetrics = computeMetrics(currentGridRef.current, nextRule, 0, 0, 0, 0, boundaryRef.current);
    metricsRef.current = nextMetrics;
    setMetrics(nextMetrics);
    setSparkline([nextMetrics.population]);
  };

  const changePreset = (nextPreset: PresetId) => {
    const recommended = recommendedRuleForPreset(nextPreset);
    const nextRuleId = recommended ?? ruleIdRef.current;
    if (recommended && recommended !== ruleIdRef.current) {
      setRuleId(recommended);
      ruleIdRef.current = recommended;
    }
    setPresetId(nextPreset);
    resetWithPreset(nextPreset, nextRuleId);
  };

  const randomize = useCallback(() => {
    randomizeGrid(currentGridRef.current, density / 100, RULES[ruleIdRef.current].states - 1);
    generationRef.current = 0;
    const nextMetrics = computeMetrics(currentGridRef.current, RULES[ruleIdRef.current], 0, 0, 0, 0, boundaryRef.current);
    metricsRef.current = nextMetrics;
    setMetrics(nextMetrics);
    setPresetId("random");
    setSparkline([nextMetrics.population]);
  }, [density]);

  const clear = useCallback(() => {
    currentGridRef.current.cells.fill(0);
    nextGridRef.current.cells.fill(0);
    generationRef.current = 0;
    const nextMetrics = computeMetrics(currentGridRef.current, RULES[ruleIdRef.current], 0, 0, 0, 0, boundaryRef.current);
    metricsRef.current = nextMetrics;
    setMetrics(nextMetrics);
    setPresetId("empty");
    setSparkline([0]);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.target instanceof HTMLButtonElement ||
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLSelectElement ||
        event.target instanceof HTMLTextAreaElement
      ) {
        return;
      }

      if (event.code === "Space") {
        event.preventDefault();
        setPlaying((value) => !value);
      } else if (event.key.toLowerCase() === "s") {
        stepOnce();
      } else if (event.key.toLowerCase() === "r") {
        randomize();
      } else if (event.key.toLowerCase() === "c") {
        clear();
      } else if (event.key.toLowerCase() === "e") {
        setErasing((value) => !value);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [clear, randomize, stepOnce]);

  const paint = (x: number, y: number, erase: boolean) => {
    const paintState = erase ? 0 : RULES[ruleIdRef.current].kind === "wireworld" ? 3 : 1;
    paintDisc(currentGridRef.current, x, y, brushSize, paintState);
    const nextMetrics = computeMetrics(currentGridRef.current, RULES[ruleIdRef.current], generationRef.current, 0, 0, metricsRef.current.tickRate, boundaryRef.current);
    metricsRef.current = nextMetrics;
    setMetrics(nextMetrics);
  };

  const exportPng = () => {
    const png = canvasRef.current?.exportPng();
    if (!png) {
      return;
    }

    const link = document.createElement("a");
    link.href = png;
    link.download = `emergent-life-${ruleIdRef.current}-gen-${generationRef.current}.png`;
    link.click();
    setShareStatus("PNG exported.");
  };

  const copyShare = async () => {
    const encoded = encodeState(currentGridRef.current, ruleIdRef.current, generationRef.current);
    const url = `${window.location.origin}${window.location.pathname}#state=${encoded}`;
    window.history.replaceState(null, "", `#state=${encoded}`);

    try {
      await navigator.clipboard.writeText(url);
      setShareStatus("Encoded URL copied.");
    } catch {
      await navigator.clipboard.writeText(exportStateJson(currentGridRef.current, ruleIdRef.current, generationRef.current));
      setShareStatus("Clipboard used JSON fallback.");
    }
  };

  const toggleSound = async () => {
    const next = !soundEnabled;
    setSoundEnabled(next);
    await audioRef.current?.setEnabled(next);
    if (next) {
      audioRef.current?.update(metricsRef.current, GRID_WIDTH, GRID_HEIGHT);
    }
  };

  const exitLab = () => {
    try {
      if (document.referrer && new URL(document.referrer).origin === window.location.origin) {
        window.history.back();
        return;
      }
    } catch {
      // Fall through to the portfolio home when referrer parsing is unavailable.
    }

    window.location.assign("/");
  };

  const sparkMax = Math.max(1, ...sparkline);

  return (
    <div ref={shellRef} className={`${styles.shell} ${controlsMinimized ? styles.controlsMinimized : ""} emergent-life-shell`}>
      <TopBar rule={rule} fullscreenActive={fullscreenActive} onFullscreenToggle={toggleFullscreen} />
      <h1 className="sr-only">Emergent Life Lab</h1>
      <section className={styles.labGrid} aria-label="Cellular automata lab">
        {controlsMinimized ? (
          <div className={styles.minimizedPanelControls} aria-label="Minimized controls">
            <button type="button" className={styles.restorePanelButton} onClick={() => setControlsMinimized(false)}>
              Controls
            </button>
            <button type="button" className={styles.restorePanelButton} data-danger="true" onClick={exitLab}>
              Exit
            </button>
          </div>
        ) : (
          <ControlPanel
            ruleId={ruleId}
            presetId={presetId}
            playing={playing}
            density={density}
            speed={speed}
            brushSize={brushSize}
            boundary={boundary}
            erasing={erasing}
            soundEnabled={soundEnabled}
            shareStatus={shareStatus}
            onRuleChange={changeRule}
            onPresetChange={changePreset}
            onPlayToggle={() => setPlaying((value) => !value)}
            onStep={() => stepOnce()}
            onReset={() => resetWithPreset(presetId)}
            onClear={clear}
            onRandomize={randomize}
            onDensityChange={setDensity}
            onSpeedChange={setSpeed}
            onBrushSizeChange={setBrushSize}
            onBoundaryChange={setBoundary}
            onEraseToggle={() => setErasing((value) => !value)}
            onSoundToggle={toggleSound}
            onExportPng={exportPng}
            onCopyShare={copyShare}
            onMinimize={() => setControlsMinimized(true)}
            onExit={exitLab}
            observer={<MetricsPanel metrics={metrics} width={GRID_WIDTH} height={GRID_HEIGHT} />}
          />
        )}

        <section className={styles.stagePanel} aria-label="Simulation stage">
          <CanvasAutomata ref={canvasRef} gridRef={currentGridRef} rule={rule} brushSize={brushSize} erasing={erasing} onPaint={paint} />
        </section>
      </section>

      <footer className={styles.timeline} aria-label="Recent population sparkline">
        <span>Population trace</span>
        <div className={styles.sparkline}>
          {sparkline.map((value, index) => (
            <i key={`${index}-${value}`} style={{ height: `${Math.max(3, (value / sparkMax) * 100)}%` }} />
          ))}
        </div>
      </footer>
    </div>
  );
}
