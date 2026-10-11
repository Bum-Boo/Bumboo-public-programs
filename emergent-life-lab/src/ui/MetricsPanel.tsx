import type { MetricsSnapshot } from "@/src/ca/types";
import styles from "@/src/app/App.module.css";

type MetricsPanelProps = {
  metrics: MetricsSnapshot;
  width: number;
  height: number;
};

export function MetricsPanel({ metrics, width, height }: MetricsPanelProps) {
  const density = metrics.population / Math.max(1, width * height);

  return (
    <section className={styles.observerPanel} aria-label="Observation metrics" tabIndex={0}>
      <div className={styles.panelHeading}>
        <p>Observation</p>
        <h2>Metrics</h2>
      </div>

      <dl className={styles.metricGrid}>
        <Metric label="Generation" value={metrics.generation.toLocaleString()} />
        <Metric label="Population" value={metrics.population.toLocaleString()} />
        <Metric label="Births" value={metrics.births.toLocaleString()} />
        <Metric label="Deaths" value={metrics.deaths.toLocaleString()} />
        <Metric label="Entropy" value={metrics.entropy.toFixed(3)} />
        <Metric label="Clusters" value={metrics.clusterCount.toLocaleString()} />
        <Metric label="Center X/Y" value={`${metrics.centerX.toFixed(1)} / ${metrics.centerY.toFixed(1)}`} />
        <Metric label="Tick rate" value={`${metrics.tickRate.toFixed(1)} Hz`} />
      </dl>

      <section className={styles.summaryBox}>
        <h3>Current state</h3>
        <p>
          {metrics.ruleName} is occupying {(density * 100).toFixed(2)}% of the plate with the mass center at{" "}
          {metrics.centerX.toFixed(1)}, {metrics.centerY.toFixed(1)}.
        </p>
      </section>

      <section className={styles.summaryBox}>
        <h3>Sonification map</h3>
        <ul className={styles.mappingList}>
          <li>Population controls drone gain.</li>
          <li>Births trigger short plucks.</li>
          <li>Deaths trigger a low click layer.</li>
          <li>Entropy opens the filter.</li>
          <li>Center X controls stereo pan.</li>
          <li>Clusters add harmonic density.</li>
        </ul>
      </section>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metric}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
