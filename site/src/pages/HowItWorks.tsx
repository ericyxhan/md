import { useSeo } from '../lib/seo'
import Steps from '../components/marketing/Steps'
import Section from '../components/layout/Section'
import Container from '../components/layout/Container'
import SectionHeader from '../components/marketing/SectionHeader'

export default function HowItWorks() {
  useSeo('How it works — MolDy', 'From structure file to trajectory in four steps.')
  return (
    <>
      <Section>
        <Container>
          <SectionHeader eyebrow="How it works" title="From upload to trajectory" description="No cluster login. No SLURM. No license files." />
        </Container>
      </Section>
      <Steps />
      <Section className="bg-surface">
        <Container>
          <div className="mx-auto max-w-3xl space-y-8 text-ink-soft">
            <div>
              <h3 className="text-xl font-semibold text-ink">1. Upload</h3>
              <p className="mt-2">Drop a structure file or enter a PDB ID. MolDy accepts protein + ligand separately or a single complex, and validates suffixes and atom counts.</p>
            </div>
            <div>
              <h3 className="text-xl font-semibold text-ink">2. Build</h3>
              <p className="mt-2">Set pH, padding, and ionic strength. MolDy parameterizes with OpenFF, solvates, adds ions, and writes a validated config.toml you can review.</p>
            </div>
            <div>
              <h3 className="text-xl font-semibold text-ink">3. Simulate</h3>
              <p className="mt-2">Choose a preset (quick check, standard, production, custom). Minimization, equilibration stages, then production. Live progress via SSE.</p>
            </div>
            <div>
              <h3 className="text-xl font-semibold text-ink">4. Inspect</h3>
              <p className="mt-2">Trajectories, states, checkpoints, logs, and configs are registered as artifacts. Download, retry from a stage, or reparameterize.</p>
            </div>
          </div>
        </Container>
      </Section>
    </>
  )
}
