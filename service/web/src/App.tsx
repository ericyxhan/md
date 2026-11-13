import { BrowserRouter, Link, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { Suspense, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { useAuth } from "./auth/AuthProvider";
import { LoginPage } from "./auth/LoginPage";
import { RegisterPage } from "./auth/RegisterPage";
import { AppShell } from "./components/layout/AppShell";
import { ErrorBoundary } from "./components/layout/ErrorBoundary";
import { Logo } from "./components/layout/Logo";
import { Button } from "./components/ui/Button";
import { EmptyState, Spinner } from "./components/ui/EmptyState";
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

const AdminUsersPage = lazyWithReload(
  () => import("./pages/AdminUsersPage").then((m) => ({ default: m.AdminUsersPage })),
);

const AccountPage = lazyWithReload(
  () => import("./pages/AccountPage").then((m) => ({ default: m.AccountPage })),
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

/**
 * Guards the administrator routes.
 *
 * The API refuses a non-administrator with a 403 either way, but showing
 * the raw error in place of the page would be a poor experience for
 * somebody who followed a link they were not meant to have.
 */
function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();

  if (!user?.is_admin) {
    return (
      <div className="mx-auto max-w-lg py-16">
        <div className="card">
          <EmptyState
            icon={<ShieldAlert className="size-5" />}
            title="Not your account to manage"
            description="These pages are for the server's administrators. Ask one of them if you need an account changed."
            action={
              <Link to="/">
                <Button variant="primary">Back to overview</Button>
              </Link>
            }
          />
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

export default function App() {
  const { status } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");

  if (status === "loading") return <Splash />;

  if (status === "anonymous") {
    return mode === "register" ? (
      <RegisterPage onSignIn={() => setMode("login")} />
    ) : (
      <LoginPage onRegister={() => setMode("register")} />
    );
  }

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
          <Route path="/account" element={<AccountPage />} />
          <Route
            path="/admin/users"
            element={
              <AdminRoute>
                <AdminUsersPage />
              </AdminRoute>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
