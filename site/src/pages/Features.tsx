import { useSeo } from '../lib/seo'
import FeatureGrid from '../components/marketing/FeatureGrid'
import Section from '../components/layout/Section'
import Container from '../components/layout/Container'
import SectionHeader from '../components/marketing/SectionHeader'
import { Check } from 'lucide-react'

export default function Features() {
  useSeo('Features — Lattice', 'Everything you need to run molecular dynamics in the browser.')
  const extra = [
    'Guided four-step wizard with a validate-before-run gate',
    'Live SSE event stream with reconnect and polling fallback',
    'Stage timeline, progress bars, temperature / density / speed',
    'Artifact and log inspection with bounded tail viewer',
    'Membrane embedding (POPC, POPE, DPPC, DLPC, DSPC, SOPC)',
    'System preparation and interactive structure viewer',
    'Account isolation, admin console, and audit trail',
    'Retry modes: resume, restart, restart-stage, reparameterize',
  ]
  return (
    <>
      <Section>
        <Container>
          <SectionHeader eyebrow="Features" title="A complete MD workbench in the browser" description="From upload to trajectory, with the safety and observability of a real platform." />
        </Container>
      </Section>
      <FeatureGrid compact />
      <Section className="bg-surface">
        <Container>
          <div className="grid gap-10 lg:grid-cols-2">
            <div>
              <h3 className="text-2xl font-bold text-ink">Workflow depth</h3>
              <p className="mt-3 text-ink-soft">Lattice is not a toy. It wraps a checkpointed OpenMM pipeline with real force fields and real ensembles.</p>
              <ul className="mt-6 space-y-2.5">
                {extra.map((e) => (
                  <li key={e} className="flex items-start gap-3 text-sm text-ink-soft">
                    <span className="mt-0.5 text-brand-600"><Check className="h-4 w-4" /></span>
                    {e}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-card border border-line-strong bg-canvas p-6">
              <p className="text-xs font-semibold uppercase tracking-wider text-faint">Supported inputs</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {['PDB', 'mmCIF', 'SDF', 'MOL', 'MOL2', 'RCSB PDB ID'].map((t) => (
                  <span key={t} className="rounded-md border border-line bg-surface px-2.5 py-1 font-mono text-xs text-ink-soft">{t}</span>
                ))}
              </div>
              <p className="mt-6 text-xs font-semibold uppercase tracking-wider text-faint">Force fields</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {['Amber14 (protein)', 'TIP3P (water)', 'OpenFF 2.3.0 (ligands)'].map((t) => (
                  <span key={t} className="rounded-md border border-line bg-surface px-2.5 py-1 text-xs text-ink-soft">{t}</span>
                ))}
              </div>
            </div>
          </div>
        </Container>
      </Section>
    </>
  )
}
