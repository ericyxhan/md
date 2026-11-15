import { useSeo } from '../lib/seo'
import Section from '../components/layout/Section'
import Container from '../components/layout/Container'
import SectionHeader from '../components/marketing/SectionHeader'
import { Check } from 'lucide-react'
import { APP_URL } from '../lib/config'

export default function Pricing() {
  useSeo('Pricing — MolDy', 'Free. Forever.')
  return (
    <Section>
      <Container>
        <SectionHeader eyebrow="Pricing" title="Free. Forever." description="No tiers, no trials, no credit card. MolDy is completely free for research and education." />
        <div className="mx-auto mt-12 max-w-md">
          <div className="rounded-card border-2 border-brand-500 bg-surface p-8 shadow-md">
            <p className="text-xs font-semibold uppercase tracking-wider text-brand-600">Free</p>
            <div className="mt-3 flex items-baseline gap-1">
              <span className="text-5xl font-extrabold text-ink">$0</span>
              <span className="text-muted">/ forever</span>
            </div>
            <ul className="mt-6 space-y-3">
              {[
                'Unlimited simulations per account',
                'Full MD pipeline (min, equil, production)',
                'Membrane embedding',
                'Live monitoring and artifacts',
                'Download everything you produce',
              ].map((p) => (
                <li key={p} className="flex items-start gap-3 text-sm text-ink-soft">
                  <span className="mt-0.5 text-brand-600"><Check className="h-4 w-4" /></span>
                  {p}
                </li>
              ))}
            </ul>
            <a href={`${APP_URL}`} className="mt-8 block rounded-control bg-brand-500 px-4 py-3 text-center text-sm font-medium text-white hover:bg-brand-600">
              Create free account
            </a>
          </div>
        </div>
      </Container>
    </Section>
  )
}
