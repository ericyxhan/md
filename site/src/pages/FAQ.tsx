import { useSeo } from '../lib/seo'
import Section from '../components/layout/Section'
import Container from '../components/layout/Container'
import SectionHeader from '../components/marketing/SectionHeader'

const faqs = [
  { q: 'Is it really free?', a: 'Yes. No subscription, no trial, no credit card. Lattice is completely free for research and education.' },
  { q: 'What force fields are used?', a: 'Amber14 (ff14SB) for proteins, TIP3P for water, OpenFF 2.3.0 (SMIRNOFF) for ligands.' },
  { q: 'What inputs are supported?', a: 'PDB, mmCIF, SDF, MOL, MOL2, or a 4-character RCSB PDB ID. Protein + ligand separately or a single complex.' },
  { q: 'Can I resume or retry a run?', a: 'Yes. Resume, restart, restart from a stage, or reparameterize — all from the job page.' },
  { q: 'Is my data private?', a: 'Each account has its own isolated data directory and rows. Only you (and admins) can access your runs.' },
  { q: 'What GPUs power it?', a: 'NVIDIA GPUs via OpenMM CUDA. CPU fallback is available for development.' },
]

export default function FAQ() {
  useSeo('FAQ — Lattice', 'Frequently asked questions.')
  return (
    <Section>
      <Container>
        <SectionHeader eyebrow="FAQ" title="Frequently asked questions" />
        <div className="mx-auto mt-10 max-w-3xl space-y-6">
          {faqs.map((f) => (
            <div key={f.q} className="rounded-card border border-line bg-surface p-6">
              <h3 className="text-base font-semibold text-ink">{f.q}</h3>
              <p className="mt-2 text-sm text-ink-soft">{f.a}</p>
            </div>
          ))}
        </div>
      </Container>
    </Section>
  )
}
