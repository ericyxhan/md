import { BrowserRouter, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthProvider";
import { LoginPage } from "./auth/LoginPage";
import { AppShell } from "./components/layout/AppShell";
import { Logo } from "./components/layout/Logo";
import { Spinner } from "./components/ui/EmptyState";
import { DashboardPage } from "./pages/DashboardPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { JobsPage } from "./pages/JobsPage";
import MembraneEmbedPage from "./pages/prep/MembraneEmbedPage";
import SystemPrepPage from "./pages/prep/SystemPrepPage";
import { NewJobPage } from "./pages/NewJobPage";
import { NotFoundPage } from "./pages/NotFoundPage";

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

function ProtectedLayout() {
  return (
    <AppShell>
      <Outlet />
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
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
