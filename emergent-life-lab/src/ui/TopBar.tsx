
import { useEffect, useState } from "react";
import type { RuleDefinition } from "@/src/ca/types";
import styles from "@/src/app/App.module.css";

type TopBarProps = {
  rule: RuleDefinition;
  fullscreenActive: boolean;
  onFullscreenToggle: () => void;
};

export function TopBar({ rule, fullscreenActive, onFullscreenToggle }: TopBarProps) {
  const [guideOpen, setGuideOpen] = useState(false);

  useEffect(() => {
    if (!guideOpen) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setGuideOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [guideOpen]);

  return (
    <header className={styles.topBar}>
      <div className={styles.topActionButtons}>
        <button
          type="button"
          className={styles.guideButton}
          aria-expanded={guideOpen}
          aria-controls="emergent-life-guide"
          onClick={() => setGuideOpen((value) => !value)}
        >
          Guide
        </button>
        <button type="button" className={styles.fullscreenButton} onClick={onFullscreenToggle}>
          {fullscreenActive ? "Exit Full" : "Fullscreen"}
        </button>
      </div>

      {guideOpen ? (
        <section id="emergent-life-guide" className={styles.guidePopover} role="dialog" aria-label="Emergent Life guide">
          <div className={styles.guideHeader}>
            <p>Emergent Life</p>
            <button type="button" className={styles.guideClose} aria-label="Close guide" onClick={() => setGuideOpen(false)}>
              Close
            </button>
          </div>
          <h2>Cellular automata lab</h2>
          <p>
            A focused laboratory for observing artificial-life rules as spatial patterns, live metrics, and subtle audio signals.
          </p>
          <dl className={styles.guideFacts}>
            <div>
              <dt>Active rule</dt>
              <dd>
                {rule.name} <span>{rule.code}</span>
              </dd>
            </div>
            <div>
              <dt>Rule note</dt>
              <dd>{rule.description}</dd>
            </div>
            <div>
              <dt>Shortcuts</dt>
              <dd>Space play/pause, S step, R randomize, C clear, E erase. Hold Alt while painting to erase.</dd>
            </div>
          </dl>
        </section>
      ) : null}
    </header>
  );
}
