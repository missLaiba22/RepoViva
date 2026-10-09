import { useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { ThemeToggle } from "../components/ThemeToggle";
import { useAuth } from "../features/auth";
import styles from "./Layout.module.css";

/** The signed-in shell: header and a centred content column. */
export function Layout() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await signOut();
      navigate("/", { replace: true });
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.bar}>
          <Logo to="/home" />
          <div className={styles.right}>
            {user && <span className={styles.user}>{user.github_login}</span>}
            <ThemeToggle />
            <Button variant="ghost" onClick={handleSignOut} disabled={signingOut}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
