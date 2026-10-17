import { NavLink, Outlet } from "react-router-dom";
import { ButtonLink } from "../components/Button";
import { Icon } from "../components/Icon";
import { Logo } from "../components/Logo";
import { AccountMenu } from "./AccountMenu";
import { SidebarRepositories } from "./SidebarRepositories";
import styles from "./Layout.module.css";

const linkClass = (active: boolean) => (active ? `${styles.link} ${styles.active}` : styles.link);

/** The signed-in shell: a sidebar for moving between sections, and the page. */
export function Layout() {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <Logo to="/repositories" />
        <ButtonLink to="/repositories/new" variant="secondary" className={styles.connect}>
          <Icon name="plus" size={16} />
          Connect repository
        </ButtonLink>
        <nav className={styles.nav} aria-label="Main">
          <SidebarRepositories linkClass={linkClass} />
          <NavLink to="/interviews" className={({ isActive }) => linkClass(isActive)}>
            <Icon name="report" size={18} />
            Reports
          </NavLink>
        </nav>
        <div className={styles.account}>
          <AccountMenu />
        </div>
      </aside>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
