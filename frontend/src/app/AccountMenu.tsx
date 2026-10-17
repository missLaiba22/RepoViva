import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../features/auth";
import { useTheme } from "../hooks/useTheme";
import styles from "./AccountMenu.module.css";

/** The signed-in user, opening a small menu: theme and sign out. */
export function AccountMenu() {
  const { user, signOut } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await signOut();
      navigate("/", { replace: true });
    } finally {
      setSigningOut(false);
    }
  }

  const login = user?.github_login ?? "";

  return (
    <div className={styles.root} ref={rootRef}>
      {open && (
        <div id={menuId} className={styles.menu} role="menu">
          <button type="button" role="menuitem" className={styles.item} onClick={toggle}>
            {theme === "dark" ? "Light theme" : "Dark theme"}
          </button>
          <button type="button" role="menuitem" className={styles.item} onClick={handleSignOut} disabled={signingOut}>
            Sign out
          </button>
        </div>
      )}
      <button
        type="button"
        className={styles.trigger}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`Account: ${login}`}
        onClick={() => setOpen(!open)}
      >
        <Avatar login={login} />
        <span className={styles.login}>{login}</span>
        <span className={styles.chevron} aria-hidden="true" />
      </button>
    </div>
  );
}

function Avatar({ login }: { login: string }) {
  const [failed, setFailed] = useState(false);
  if (!login || failed) {
    return (
      <span className={styles.avatar} aria-hidden="true">
        {login.charAt(0).toUpperCase()}
      </span>
    );
  }
  return (
    <img
      className={styles.avatar}
      src={`https://github.com/${encodeURIComponent(login)}.png?size=64`}
      alt=""
      width={28}
      height={28}
      onError={() => setFailed(true)}
    />
  );
}
