import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { ConnectionProblem } from "../../components/ConnectionProblem";
import { PageSpinner } from "../../components/Spinner";
import { useAuth } from "./authContext";

/** Renders its children only for a signed-in user; otherwise back to the landing page. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useAuth();

  if (auth.status === "loading") return <PageSpinner />;
  if (auth.status === "error") return <ConnectionProblem onRetry={auth.retry} />;
  if (auth.status === "signed-out") return <Navigate to="/" replace />;
  return children;
}
