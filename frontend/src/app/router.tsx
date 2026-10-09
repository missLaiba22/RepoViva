import { createBrowserRouter } from "react-router-dom";
import { LandingPage, RequireAuth } from "../features/auth";
import { HomePage } from "../features/home";
import { LivePage, SetupPage } from "../features/interview";
import { ConnectRepositoryPage, RepositoryPage } from "../features/repositories";
import { Layout } from "./Layout";
import { NotBuiltYet, NotFound } from "./placeholders";

export const router = createBrowserRouter([
  { path: "/", element: <LandingPage /> },
  {
    element: (
      <RequireAuth>
        <Layout />
      </RequireAuth>
    ),
    children: [
      { path: "/home", element: <HomePage /> },
      { path: "/repositories/new", element: <ConnectRepositoryPage /> },
      { path: "/repositories/:id", element: <RepositoryPage /> },
      { path: "/repositories/:id/interview", element: <SetupPage /> },
      { path: "/interviews/:id/report", element: <NotBuiltYet title="Interview report" /> },
    ],
  },
  // The live interview is a focused room: signed in, but without the header.
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
