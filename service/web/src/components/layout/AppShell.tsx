import { useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  Atom,
  Boxes,
  ChevronRight,
  FlaskConical,
  Gauge,
  Layers,
  LogOut,
  Menu,
  Plus,
  Settings,
  TestTubes,
  X,
} from "lucide-react";
import { useAuth } from "../../auth/AuthProvider";
import { cn } from "../../lib/utils";
import { Button } from "../ui/Button";
import { Logo } from "./Logo";

const primaryNav = [
  { to: "/", label: "Overview", icon: Gauge, end: true },
  { to: "/jobs", label: "Simulations", icon: Activity, end: false },
];

const futureNav = [
  { to: "/prep/system-prep", label: "System preparation", icon: Layers },
  { label: "Docking", icon: Boxes },
  { label: "Free energy", icon: Atom },
  { label: "Property prediction", icon: TestTubes },
];

function NavItem({
  to,
  label,
  icon: Icon,
  end,
  onNavigate,
}: {
  to: string;
  label: string;
  icon: typeof Gauge;
  end?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          "group flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13.5px] font-medium transition-colors",
          isActive
            ? "bg-brand-50 text-brand-800"
            : "text-ink-soft hover:bg-ink/[0.04] hover:text-ink",
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon
            className={cn(
              "size-4 shrink-0",
              isActive ? "text-brand-600" : "text-faint group-hover:text-muted",
            )}
          />
          <span className="flex-1 truncate">{label}</span>
          {isActive ? (
            <span className="size-1.5 rounded-full bg-brand-500" />
          ) : null}
        </>
      )}
    </NavLink>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { signOut, session } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const isNewJob = location.pathname.startsWith("/new");

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center gap-2.5 px-5">
        <Logo className="size-7 text-brand-700" />
        <div className="min-w-0">
          <p className="truncate text-[14px] font-semibold tracking-[-0.01em] text-ink">
            Lattice
          </p>
          <p className="truncate text-[10.5px] font-medium uppercase tracking-[0.14em] text-faint">
            MD console
          </p>
        </div>
      </div>

      <div className="px-3 pb-2 pt-1">
        <Button
          variant={isNewJob ? "primary" : "secondary"}
          size="sm"
          className="w-full justify-start"
          leadingIcon={<Plus className="size-3.5" />}
          onClick={() => {
            navigate("/new");
            onNavigate?.();
          }}
        >
          New simulation
        </Button>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-2">
        <p className="px-2.5 pb-1.5 pt-2 text-[10.5px] font-semibold uppercase tracking-[0.13em] text-faint">
          Workspace
        </p>
        <div className="space-y-0.5">
          {primaryNav.map((item) => (
            <NavItem key={item.to} {...item} onNavigate={onNavigate} />
          ))}
        </div>

        <p className="px-2.5 pb-1.5 pt-6 text-[10.5px] font-semibold uppercase tracking-[0.13em] text-faint">
          Platform
        </p>
        <div className="space-y-0.5">
          {futureNav.map((item) => {
            const hasRoute = "to" in item && !!item.to;
            if (hasRoute) {
              return (
                <NavItem
                  key={item.to}
                  to={item.to}
                  label={item.label}
                  icon={item.icon}
                  onNavigate={onNavigate}
                />
              );
            }
            return (
              <div
                key={item.label}
                className="flex h-9 cursor-not-allowed items-center gap-2.5 rounded-lg px-2.5 text-[13.5px] font-medium text-faint/80"
                title="Planned workspace"
              >
                <item.icon className="size-4 shrink-0" />
                <span className="flex-1 truncate">{item.label}</span>
                <span className="rounded-full bg-ink/[0.05] px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wide text-faint">
                  Soon
                </span>
              </div>
            );
          })}
        </div>

        <div className="mt-6 rounded-xl border border-dashed border-line-strong bg-surface/60 p-3">
          <div className="flex items-center gap-2 text-[12px] font-medium text-ink-soft">
            <FlaskConical className="size-3.5 text-brand-600" />
            Molecular dynamics
          </div>
          <p className="mt-1 text-[11.5px] leading-relaxed text-muted">
            Protein–ligand systems on a single GPU worker.
          </p>
          <div className="mt-2.5 flex items-center gap-1 text-[11px] font-medium text-brand-700">
            Active workflow
            <ChevronRight className="size-3" />
          </div>
        </div>
      </nav>

      <div className="border-t border-line p-3">
        <div className="flex items-center gap-2.5 rounded-lg px-1.5 py-1.5">
          <div className="flex size-8 items-center justify-center rounded-full bg-brand-100 text-[11px] font-semibold text-brand-800">
            LAB
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[12.5px] font-medium text-ink">
              Shared lab
            </p>
            <p className="truncate text-[11px] text-faint">
              {session?.owner ?? "local"} · session
            </p>
          </div>
          <button
            type="button"
            onClick={() => void signOut()}
            className="rounded-md p-1.5 text-faint transition hover:bg-ink/5 hover:text-ink"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="size-4" />
          </button>
        </div>
        <div className="mt-1 flex items-center gap-2 px-2 py-1 text-[10.5px] text-faint">
          <Settings className="size-3" />
          API v1 · OpenMM
        </div>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-dvh">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[264px] border-r border-line bg-surface lg:block">
        <SidebarContent />
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-ink/25 backdrop-blur-[1px]"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-[276px] border-r border-line bg-surface shadow-[var(--shadow-float)] animate-fade-up">
            <button
              type="button"
              className="absolute right-3 top-4 rounded-md p-1.5 text-muted hover:bg-ink/5"
              onClick={() => setMobileOpen(false)}
              aria-label="Close menu"
            >
              <X className="size-4" />
            </button>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      ) : null}

      <div className="lg:pl-[264px]">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-canvas/85 px-4 backdrop-blur lg:hidden">
          <button
            type="button"
            className="rounded-lg p-2 text-ink-soft hover:bg-ink/5"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="size-5" />
          </button>
          <div className="flex items-center gap-2">
            <Logo className="size-6 text-brand-700" />
            <span className="text-sm font-semibold tracking-tight">Lattice</span>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1180px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
