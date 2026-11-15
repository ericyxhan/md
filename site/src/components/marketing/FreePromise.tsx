import { Check } from 'lucide-react'
import SectionHeader from './SectionHeader'
import Section from '../layout/Section'
import Container from '../layout/Container'

const points = [
  'No subscription, no trial, no credit card.',
  'No per-job fees, no compute-hour charges.',
  'No software license to buy or renew.',
  'No data lock-in — download everything you produce.',
  'Open methodology: OpenMM, Amber14, OpenFF 2.3.0.',
]

export default function FreePromise() {
  return (
    <Section>
      <Container>
        <div className="grid items-center gap-10 lg:grid-cols-2">
          <div>
            <SectionHeader
              align="left"
              eyebrow="Free, forever"
              title="The first platform of its kind — completely free"
              description="MD simulation has always required a cluster, a license, and a specialist. MolDy removes all three. Run real, reproducible molecular dynamics at no cost."
            />
            <ul className="mt-8 space-y-3">
              {points.map((p) => (
                <li key={p} className="flex items-start gap-3 text-sm text-ink-soft">
                  <span className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-600">
                    <Check className="h-3.5 w-3.5" />
                  </span>
                  {p}
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-card border border-line-strong bg-gradient-to-br from-brand-50 to-white p-8">
            <p className="text-xs font-semibold uppercase tracking-wider text-brand-600">What's included</p>
            <dl className="mt-4 space-y-4">
              {[
                ['Simulations', 'Unlimited queued runs per account'],
                ['Force fields', 'Amber14 protein + TIP3P, OpenFF 2.3.0 ligands'],
                ['Ensembles', 'NVT, NPT, minimization, multi-stage equilibration'],
                ['Outputs', 'Trajectories, states, checkpoints, logs, configs'],
                ['Monitoring', 'Live stages, events, progress, and artifacts'],
                ['Support', 'Documentation and community'],
              ].map(([k, v]) => (
                <div key={k} className="flex items-baseline justify-between gap-4 border-b border-line/60 pb-3 last:border-0 last:pb-0">
                  <dt className="text-sm font-medium text-ink">{k}</dt>
                  <dd className="text-right text-sm text-ink-soft">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </Container>
    </Section>
  )
}
