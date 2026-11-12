import { BrowserRouter, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { Suspense } from "react";
import { useAuth } from "./auth/AuthProvider";
import { LoginPage } from "./auth/LoginPage";
import { AppShell } from "./components/layout/AppShell";
import { ErrorBoundary } from "./components/layout/ErrorBoundary";
import { Logo } from "./components/layout/Logo";
import { Spinner } from "./components/ui/EmptyState";
import { lazyWithReload } from "./lib/lazy";

/**
 * Route components are loaded on demand.
 *
 * Every page used to be part of the entry chunk, which meant the browser
 * downloaded the charting library (only the Analysis tab needs it) and every
 * page's code before the first paint.  Splitting the routes keeps the entry
 * chunk small and lets the browser fetch only the page it is about to show.
 */
const DashboardPage = lazyWithReload(() =>
  import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })),
);
const JobDetailPage = lazyWithReload(() =>
  import("./pages/JobDetailPage").then((m) => ({ default: m.JobDetailPage })),
);
const JobsPage = lazyWithReload(() =>
  import("./pages/JobsPage").then((m) => ({ default: m.JobsPage })),
);
const NewJobPage = lazyWithReload(() =>
  import("./pages/NewJobPage").then((m) => ({ default: m.NewJobPage })),
);
const NotFoundPage = lazyWithReload(() =>
  import("./pages/NotFoundPage").then((m) => ({ default: m.NotFoundPage })),
);
const WorkflowsPage = lazyWithReload(() =>
  import("./pages/WorkflowsPage").then((m) => ({ default: m.WorkflowsPage })),
);
const WorkflowDetailPage = lazyWithReload(() =>
  import("./pages/WorkflowDetailPage").then((m) => ({
    default: m.WorkflowDetailPage,
  })),
);
const MembraneEmbedPage = lazyWithReload(
  () => import("./pages/prep/MembraneEmbedPage"),
);
const SystemPrepPage = lazyWithReload(
  () => import("./pages/prep/SystemPrepPage"),
);

function Splash() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-canvas">
      <Logo className="size-10 text-brand-700" />
      <div className="flex items-center gap-2 text-[12.5px] text-muted">
        <Spinner />
        Opening the simulation console
      </div>
    </div>
  );
}

/**
 * Re-mounts the error boundary whenever the route changes, so navigating
 * away from a broken view recovers instead of showing the stale error.
 */
function RouteBoundary({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  return <ErrorBoundary key={location.pathname}>{children}</ErrorBoundary>;
}

function ProtectedLayout() {
  return (
    <AppShell>
      <RouteBoundary>
        <Suspense fallback={<Splash />}>
          <Outlet />
        </Suspense>
      </RouteBoundary>
    </AppShell>
  );
}

export default function App() {
  const { status } = useAuth();

  if (status === "loading") return <Splash />;

  if (status === "anonymous") return <LoginPage />;

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<ProtectedLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/jobs/:id" element={<JobDetailPage />} />
          <Route path="/new" element={<NewJobPage />} />
          <Route path="/prep/membrane" element={<MembraneEmbedPage />} />
          <Route path="/prep/membrane/:prepJobId" element={<MembraneEmbedPage />} />
          <Route path="/prep/system-prep" element={<SystemPrepPage />} />
          <Route path="/prep/system-prep/:prepJobId" element={<SystemPrepPage />} />
          <Route path="/workflows" element={<WorkflowsPage />} />
          <Route path="/workflows/:workflowId" element={<WorkflowDetailPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
