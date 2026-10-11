import styles from "@/src/app/App.module.css";

type SliderProps = {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  suffix?: string;
  hint?: string;
  onChange: (value: number) => void;
};

export function Slider({ label, value, min, max, step = 1, suffix = "", hint, onChange }: SliderProps) {
  return (
    <label className={styles.slider}>
      <span className={styles.sliderHeader}>
        <span>
          {label}
          {hint ? <small>{hint}</small> : null}
        </span>
        <strong>
          {value}
          {suffix}
        </strong>
      </span>
      <input min={min} max={max} step={step} type="range" value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}
