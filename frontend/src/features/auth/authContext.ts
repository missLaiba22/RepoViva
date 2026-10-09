import { createContext, useContext } from "react";
import type { User } from "../../api/types";

export interface AuthValue {
  status: "loading" | "error" | "signed-out" | "signed-in";
  user: User | null;
  error: Error | null;
  retry: () => void;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
