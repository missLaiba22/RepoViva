import { Icon, type IconName } from "./Icon";
import styles from "./Facts.module.css";

/** A row of short, icon-led facts in place of a paragraph. */
export function Facts({ items, label }: { items: { icon: IconName; label: string }[]; label: string }) {
  return (
    <ul className={styles.facts} aria-label={label}>
      {items.map((item) => (
        <li key={item.label}>
          <Icon name={item.icon} size={16} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
