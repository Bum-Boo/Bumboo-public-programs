import type { ReactNode } from "react";
import styles from "@/src/app/App.module.css";

type SelectProps<T extends string> = {
  label: string;
  value: T;
  children: ReactNode;
  onChange: (value: T) => void;
};

export function Select<T extends string>({ label, value, children, onChange }: SelectProps<T>) {
  return (
    <label className={styles.selectLabel}>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value as T)}>
        {children}
      </select>
    </label>
  );
}
