import { useCallback, useMemo, type ReactNode } from "react";
import { useResource } from "../../hooks/useResource";
import { fetchMe, signOut } from "./api";
import { AuthContext, type AuthValue } from "./authContext";

export function AuthProvider({ children }: { children: ReactNode }) {
  const me = useResource(fetchMe);
  const { reload, set } = me;

  // Signed out as soon as Core API confirms, without another /v1/me round
  // trip, so no page sees the old user in between.
  const handleSignOut = useCallback(async () => {
    await signOut();
    set(null);
  }, [set]);

  const value = useMemo<AuthValue>(() => {
    const base = { retry: reload, signOut: handleSignOut };
    if (me.state === "loading") return { ...base, status: "loading", user: null, error: null };
    if (me.state === "error") return { ...base, status: "error", user: null, error: me.error };
    return me.data
      ? { ...base, status: "signed-in", user: me.data, error: null }
      : { ...base, status: "signed-out", user: null, error: null };
  }, [me, reload, handleSignOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
