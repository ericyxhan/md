import { useState, type FormEvent } from "react";
import { ArrowRight, Atom, LockKeyhole, ShieldCheck } from "lucide-react";
import { useAuth } from "./AuthProvider";
import { Button } from "../components/ui/Button";
import { TextInput } from "../components/ui/Form";
import { Logo } from "../components/layout/Logo";

export function LoginPage({ onRegister }: { onRegister: () => void }) {
  const { signIn, error: connectionError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!email || !password || pending) return;
    setPending(true);
    setError(null);
    try {
      await signIn(email, password);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not sign in",
      );
      setPassword("");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="grid min-h-dvh bg-canvas lg:grid-cols-[1.05fr_1fr]">
      <section className="relative hidden overflow-hidden bg-brand-900 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.22]"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 15%, #35beae 0, transparent 42%), radial-gradient(circle at 82% 78%, #17a394 0, transparent 46%)",
          }}
        />
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.13]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.6) 1px, transparent 1px)",
            backgroundSize: "44px 44px",
            maskImage:
              "radial-gradient(ellipse at 50% 50%, black 30%, transparent 75%)",
          }}
        />

        <div className="relative flex items-center gap-3">
          <Logo className="size-9 text-brand-200" />
          <div>
            <p className="text-[15px] font-semibold tracking-tight">Lattice</p>
            <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-brand-200/80">
              Molecular Dynamics
            </p>
          </div>
        </div>

        <div className="relative max-w-md">
          <h1 className="text-[40px] font-semibold leading-[1.08] tracking-[-0.03em]">
            From structure to
            <br />
            trajectory, without
            <br />
            the command line.
          </h1>
          <p className="mt-5 max-w-sm text-[15px] leading-relaxed text-brand-100/80">
            Prepare a protein–ligand system, launch a GPU simulation, and follow
            every equilibration step in real time.
          </p>

          <div className="mt-9 grid gap-3 text-[13px] text-brand-100/85">
            {[
              "Your own account, your own simulations",
              "Guided system preparation with sensible defaults",
              "Live stage progress and checkpoint-safe cancellation",
              "Downloadable trajectories, states, and logs",
            ].map((line) => (
              <div key={line} className="flex items-center gap-2.5">
                <span className="flex size-5 items-center justify-center rounded-full bg-white/10 ring-1 ring-inset ring-white/15">
                  <ShieldCheck className="size-3 text-brand-200" />
                </span>
                {line}
              </div>
            ))}
          </div>
        </div>

        <p className="relative text-[11px] text-brand-200/60">
          OpenMM · Amber14 · OpenFF 2.3.0
        </p>
      </section>

      <section className="flex items-center justify-center px-6 py-14">
        <div className="w-full max-w-[380px] animate-fade-up">
          <div className="mb-9 flex items-center gap-2.5 lg:hidden">
            <Logo className="size-8 text-brand-700" />
            <span className="text-[15px] font-semibold tracking-tight">
              Lattice
            </span>
          </div>

          <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 text-[11.5px] font-medium text-brand-700 ring-1 ring-inset ring-brand-200/70">
            <LockKeyhole className="size-3" />
            Account access
          </span>

          <h2 className="mt-4 text-[26px] font-semibold tracking-[-0.025em] text-ink">
            Welcome back
          </h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            Sign in with the email address you registered with.
          </p>

          <form onSubmit={submit} className="mt-7 space-y-4">
            <div>
              <label className="field-label" htmlFor="account-email">
                Email address
              </label>
              <TextInput
                id="account-email"
                type="email"
                autoComplete="email"
                autoFocus
                className="input-lg"
                placeholder="you@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                aria-invalid={Boolean(error)}
              />
            </div>

            <div>
              <label className="field-label" htmlFor="account-password">
                Password
              </label>
              <TextInput
                id="account-password"
                type="password"
                autoComplete="current-password"
                className="input-lg"
                placeholder="••••••••••••"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-invalid={Boolean(error)}
              />
            </div>

            {error ? (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-[13px] font-medium text-rose-700 ring-1 ring-inset ring-rose-200/70">
                {error}
              </p>
            ) : connectionError ? (
              <p className="rounded-lg bg-amber-50 px-3 py-2 text-[13px] leading-relaxed text-amber-800 ring-1 ring-inset ring-amber-200/70">
                {connectionError}
              </p>
            ) : null}

            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="w-full"
              loading={pending}
              trailingIcon={<ArrowRight className="size-4" />}
              disabled={!email || !password}
            >
              Sign in
            </Button>
          </form>

          <p className="mt-6 text-center text-[13px] text-muted">
            New here?{" "}
            <button
              type="button"
              onClick={onRegister}
              className="font-medium text-brand-700 hover:text-brand-800"
            >
              Create an account
            </button>
          </p>

          <div className="mt-8 flex items-start gap-2.5 rounded-xl border border-line bg-surface/70 px-3.5 py-3">
            <Atom className="mt-0.5 size-4 shrink-0 text-muted" />
            <p className="text-[12px] leading-relaxed text-muted">
              The browser never stores the service token. Your session is a
              signed, HttpOnly cookie that expires after 12 hours.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
