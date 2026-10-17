import { createBrowserRouter, Navigate } from "react-router-dom";
import { LandingPage, RequireAuth } from "../features/auth";
import { LivePage, SetupPage } from "../features/interview";
import { ReportPage, ReportsPage } from "../features/report";
import { ConnectRepositoryPage, RepositoriesPage, RepositoryPage } from "../features/repositories";
import { Layout } from "./Layout";
import { NotFound } from "./NotFound";

export const router = createBrowserRouter([
  { path: "/", element: <LandingPage /> },
  {
    element: (
      <RequireAuth>
        <Layout />
      </RequireAuth>
    ),
    children: [
      // Core API sends the browser to /home after sign-in.
      { path: "/home", element: <Navigate to="/repositories" replace /> },
      { path: "/repositories", element: <RepositoriesPage /> },
      { path: "/repositories/new", element: <ConnectRepositoryPage /> },
      { path: "/repositories/:id", element: <RepositoryPage /> },
      { path: "/repositories/:id/interview", element: <SetupPage /> },
      { path: "/interviews", element: <ReportsPage /> },
      { path: "/interviews/:id/report", element: <ReportPage /> },
    ],
  },
  // The live interview is a focused room: signed in, but without the sidebar.
  {
    path: "/interviews/:id/live",
    element: (
      <RequireAuth>
        <LivePage />
      </RequireAuth>
    ),
  },
  { path: "*", element: <NotFound /> },
]);
