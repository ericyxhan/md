import { Link } from 'react-router-dom'
import { ArrowRight, Play, Sparkles } from 'lucide-react'
import { APP_URL } from '../../lib/config'

export default function Hero() {
  return (
    <section className="relative overflow-hidden pt-12 pb-20 sm:pt-20 sm:pb-28">
      {/* background lattice */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_-10%,rgba(23,163,148,0.12),transparent)]" />
        <svg className="absolute right-[-10%] top-10 h-[520px] w-[520px] opacity-40 animate-float" viewBox="0 0 400 400" fill="none">
          <g stroke="#17a394" strokeWidth="1">
            {Array.from({ length: 18 }).map((_, i) => {
              const x = (i * 37 + 13) % 360
              const y = (i * 53 + 29) % 360
              return <circle key={i} cx={x + 20} cy={y + 20} r={3 + (i % 3)} fill="#17a394" opacity={0.5 + (i % 5) * 0.1} />
            })}
            {Array.from({ length: 22 }).map((_, i) => {
              const a = (i * 37 + 13) % 360 + 20
              const b = (i * 53 + 29) % 360 + 20
              const c = ((i + 7) * 37 + 13) % 360 + 20
              const d = ((i + 7) * 53 + 29) % 360 + 20
              return <line key={i} x1={a} y1={b} x2={c} y2={d} strokeOpacity={0.25} />
            })}
          </g>
        </svg>
      </div>

      <div className="mx-auto w-full max-w-6xl px-5 sm:px-8">
        <div className="mx-auto max-w-3xl text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-brand-100 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700">
            <Sparkles className="h-3.5 w-3.5" />
            Free for research and education — no credit card, no trial
          </div>
          <h1 className="mt-6 text-4xl font-extrabold tracking-tight text-ink sm:text-6xl">
            Molecular dynamics,<br />
            <span className="text-brand-600">run in your browser.</span>
          </h1>
          <p className="mt-6 text-lg text-ink-soft sm:text-xl">
            MolDy is the first platform for running complete molecular dynamics simulations
            — from a structure file to a solvated, parameterized, production-ready trajectory —
            <span className="font-semibold text-ink"> completely free.</span>
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a
              href={`${APP_URL}`}
              className="inline-flex items-center gap-2 rounded-control bg-brand-500 px-6 py-3.5 text-base font-medium text-white shadow-sm transition-colors hover:bg-brand-600"
            >
              Create free account <ArrowRight className="h-4 w-4" />
            </a>
            <Link
              to="/how-it-works"
              className="inline-flex items-center gap-2 rounded-control border border-line-strong bg-white px-6 py-3.5 text-base font-medium text-ink transition-colors hover:bg-surface-muted"
            >
              <Play className="h-4 w-4" /> See how it works
            </Link>
          </div>
          <p className="mt-4 text-xs text-faint">
            Powered by OpenMM · Amber14 / OpenFF 2.3.0 · No installation required
          </p>
        </div>

        {/* product preview card */}
        <div className="mx-auto mt-14 max-w-4xl">
          <div className="overflow-hidden rounded-card border border-line-strong bg-surface shadow-[0_20px_60px_-20px_rgba(14,27,37,0.25)]">
            <div className="flex items-center gap-2 border-b border-line bg-surface-muted px-4 py-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
              <span className="ml-3 font-mono text-xs text-muted">moldy.app · jobs/7yae-production</span>
            </div>
            <div className="grid gap-0 sm:grid-cols-5">
              <div className="col-span-2 border-r border-line p-5">
                <p className="text-xs font-medium text-faint">Stage timeline</p>
                <ul className="mt-3 space-y-2.5 text-sm">
                  {[
                    ['Parameterize', 'done'],
                    ['Minimization', 'done'],
                    ['Equilibration 01', 'done'],
                    ['Equilibration 02', 'done'],
                    ['Production', 'running'],
                  ].map(([name, state], i) => (
                    <li
                      key={name}
                      className="flex items-center justify-between opacity-0 animate-fade-up"
                      style={{ animationDelay: `${i * 180 + 300}ms`, animationFillMode: 'forwards' }}
                    >
                      <span className="text-ink-soft">{name}</span>
                      <span
                        className={`text-xs font-medium ${
                          state === 'done' ? 'text-emerald-600' : 'text-brand-600 animate-pulse-soft'
                        }`}
                      >
                        {state === 'done' ? '✓ done' : '● running'}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="col-span-3 p-5">
                <p className="text-xs font-medium text-faint">Live progress</p>
                <div className="mt-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-ink">Production</span>
                    <span className="font-mono text-xs text-muted">42,800 / 100,000 steps</span>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-muted">
                    <div className="h-full w-[43%] rounded-full bg-brand-500 animate-grow-bar" />
                  </div>
                </div>
                <div className="mt-5 grid grid-cols-3 gap-3">
                  {[
                    ['Temperature', '300.2 K'],
                    ['Density', '1.012 g/cm³'],
                    ['Speed', '48 ns/day'],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-lg border border-line bg-canvas p-3">
                      <p className="text-[11px] text-faint">{k}</p>
                      <p className="mt-1 font-mono text-sm font-medium text-ink">{v}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-5 flex flex-wrap gap-2">
                  {['trajectory.dcd', 'state.xml', 'config.toml', 'simulation.log'].map((f) => (
                    <span key={f} className="rounded-md border border-line bg-surface-muted px-2 py-1 font-mono text-[11px] text-muted">
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
