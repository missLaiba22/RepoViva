import type { AnchorHTMLAttributes, ButtonHTMLAttributes } from "react";
import { Link, type LinkProps } from "react-router-dom";
import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "ghost";
interface Common {
  variant?: Variant;
  size?: "default" | "large";
}

function classes(variant: Variant, size: Common["size"], extra?: string) {
  return [styles.button, styles[variant], size === "large" && styles.large, extra].filter(Boolean).join(" ");
}

export function Button({ variant = "primary", size, className, ...props }: Common & ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" className={classes(variant, size, className)} {...props} />;
}

/** In-app navigation styled as a button. */
export function ButtonLink({ variant = "primary", size, className, ...props }: Common & LinkProps) {
  return <Link className={classes(variant, size, className)} {...props} />;
}

/** Full-page navigation (e.g. the OAuth redirect) styled as a button. */
export function ButtonAnchor({ variant = "primary", size, className, ...props }: Common & AnchorHTMLAttributes<HTMLAnchorElement>) {
  return <a className={classes(variant, size, className)} {...props} />;
}
