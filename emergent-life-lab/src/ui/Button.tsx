import type { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "@/src/app/App.module.css";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
  children: ReactNode;
};

export function Button({ variant = "secondary", children, className = "", ...props }: ButtonProps) {
  return (
    <button className={`${styles.button} ${styles[`button_${variant}`]} ${className}`} type="button" {...props}>
      {children}
    </button>
  );
}
