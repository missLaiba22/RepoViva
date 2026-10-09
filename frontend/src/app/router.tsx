import { createBrowserRouter } from "react-router-dom";
import { LandingPage, RequireAuth } from "../features/auth";
import { HomePage } from "../features/home";
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
      { path: "/repositories/:id/interview", element: <NotBuiltYet title="Interview setup" /> },
      { path: "/interviews/:id/report", element: <NotBuiltYet title="Interview report" /> },
    ],
  },
  { path: "*", element: <NotFound /> },
]);
