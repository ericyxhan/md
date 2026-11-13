import { useState, type FormEvent } from "react";
import { ArrowRight, Atom, UserPlus } from "lucide-react";
import { useAuth } from "./AuthProvider";
import { Button } from "../components/ui/Button";
import { TextInput } from "../components/ui/Form";
import { Logo } from "../components/layout/Logo";

export function RegisterPage({ onSignIn }: { onSignIn: () => void }) {
  const { signUp, error: connectionError } = useAuth();
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // The mismatch is reported while the confirmation is being typed, not
  // only on submit: a button that is silently disabled gives the reader no
  // idea of what is wrong.  It is one message, not two, so the reader is
  // never left wondering which of them is the current one.
  const [submitted, setSubmitted] = useState(false);
  const mismatch = password !== confirmation && (confirmation.length > 0 || submitted);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (pending) return;
    if (!email || !firstName || !lastName || !password) return;
    if (password !== confirmation) {
      setSubmitted(true);
      return;
    }
    setPending(true);
    setError(null);
    try {
      await signUp({
        email,
        first_name: firstName,
        last_name: lastName,
        password,
      });
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not create the account",
      );
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
            Your own lab,
            <br />
            on shared
            <br />
            hardware.
          </h1>
          <p className="mt-5 max-w-sm text-[15px] leading-relaxed text-brand-100/80">
            Create an account to run your own preparations, simulations, and
            embeddings. Everything you upload stays yours.
          </p>

          <div className="mt-9 grid gap-3 text-[13px] text-brand-100/85">
            {[
              "Private uploads, simulations, and results",
              "Preparation, embedding, and production in one place",
              "Downloadable trajectories, states, and logs",
            ].map((line) => (
              <div key={line} className="flex items-center gap-2.5">
                <span className="flex size-5 items-center justify-center rounded-full bg-white/10 ring-1 ring-inset ring-white/15">
                  <UserPlus className="size-3 text-brand-200" />
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
            <UserPlus className="size-3" />
            New account
          </span>

          <h2 className="mt-4 text-[26px] font-semibold tracking-[-0.025em] text-ink">
            Create your account
          </h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            It takes a moment, and your simulations stay private to you.
          </p>

          <form onSubmit={submit} className="mt-7 space-y-4">
            <div>
              <label className="field-label" htmlFor="register-email">
                Email address
              </label>
              <TextInput
                id="register-email"
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

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="field-label" htmlFor="register-first-name">
                  First name
                </label>
                <TextInput
                  id="register-first-name"
                  type="text"
                  autoComplete="given-name"
                  className="input-lg"
                  placeholder="Ada"
                  value={firstName}
                  onChange={(event) => setFirstName(event.target.value)}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="register-last-name">
                  Last name
                </label>
                <TextInput
                  id="register-last-name"
                  type="text"
                  autoComplete="family-name"
                  className="input-lg"
                  placeholder="Lovelace"
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                />
              </div>
            </div>

            <div>
              <label className="field-label" htmlFor="register-password">
                Password
              </label>
              <TextInput
                id="register-password"
                type="password"
                autoComplete="new-password"
                className="input-lg"
                placeholder="At least 10 characters"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>

            <div>
              <label className="field-label" htmlFor="register-confirm">
                Confirm password
              </label>
              <TextInput
                id="register-confirm"
                type="password"
                autoComplete="new-password"
                className="input-lg"
                placeholder="Repeat the password"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                aria-invalid={Boolean(mismatch)}
              />
              {mismatch ? (
                <p className="mt-1.5 text-[12px] font-medium text-rose-600">
                  The two passwords do not match
                </p>
              ) : null}
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
              disabled={!email || !firstName || !lastName || !password}
            >
              Create account
            </Button>
          </form>

          <p className="mt-6 text-center text-[13px] text-muted">
            Already have an account?{" "}
            <button
              type="button"
              onClick={onSignIn}
              className="font-medium text-brand-700 hover:text-brand-800"
            >
              Sign in
            </button>
          </p>

          <div className="mt-8 flex items-start gap-2.5 rounded-xl border border-line bg-surface/70 px-3.5 py-3">
            <Atom className="mt-0.5 size-4 shrink-0 text-muted" />
            <p className="text-[12px] leading-relaxed text-muted">
              Your password is stored as a scrypt hash. It is never written to
              disk in plain text and never leaves this server.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
