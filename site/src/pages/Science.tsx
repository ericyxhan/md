import { useSeo } from '../lib/seo'
import Section from '../components/layout/Section'
import Container from '../components/layout/Container'
import SectionHeader from '../components/marketing/SectionHeader'

export default function Science() {
  useSeo('Science — Lattice', 'The methodology behind Lattice simulations.')
  return (
    <Section>
      <Container>
        <SectionHeader eyebrow="Science" title="Reproducible MD, open methodology" description="Lattice runs real physics with published force fields and a checkpointed pipeline." />
        <div className="mt-12 grid gap-8 lg:grid-cols-2">
          <div className="space-y-4 text-ink-soft">
            <h3 className="text-lg font-semibold text-ink">Engine</h3>
            <p>OpenMM 8.6.1 with the CUDA platform. Supports Maxwell through Blackwell GPUs. CPU fallback for development.</p>
            <h3 className="text-lg font-semibold text-ink">Force fields</h3>
            <p>Protein: Amber14 (ff14SB). Water: TIP3P. Ions: standard. Ligands: OpenFF 2.3.0 (SMIRNOFF) via the OpenFF Toolkit, with NAGL charge models.</p>
            <h3 className="text-lg font-semibold text-ink">Preparation</h3>
            <p>PDBFixer for structure repair, RDKit/OpenFF for ligand parameterization, gemmi for mmCIF. Disconnected nonstandard components are extracted and parameterized as whole molecules.</p>
          </div>
          <div className="space-y-4 text-ink-soft">
            <h3 className="text-lg font-semibold text-ink">Stages</h3>
            <p>Parameterize → minimize → equilibrate (NVT/NPT) → production. Each stage writes a portable state.xml so the next stage can change ensemble freely.</p>
            <h3 className="text-lg font-semibold text-ink">Checkpointing</h3>
            <p>Stage-local checkpoint.chk for intra-stage resume; portable state.xml for cross-stage handoff. A checkpoint is tied to its exact integrator and barostat.</p>
            <h3 className="text-lg font-semibold text-ink">Reproducibility</h3>
            <p>Every run stores config.toml, job.json, stage manifests, logs, and artifacts. Re-run from any stage. Config is validated by config.load_config() before execution.</p>
          </div>
        </div>
      </Container>
    </Section>
  )
}
