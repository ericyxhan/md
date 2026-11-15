import { useSeo } from '../lib/seo'
import Section from '../components/layout/Section'
import Container from '../components/layout/Container'
import SectionHeader from '../components/marketing/SectionHeader'
import { APP_URL } from '../lib/config'

export default function Docs() {
  useSeo('Documentation — MolDy', 'Getting started with MolDy.')
  return (
    <Section>
      <Container>
        <SectionHeader eyebrow="Docs" title="Getting started" description="From zero to a running simulation in minutes." />
        <div className="mt-12 grid gap-6 lg:grid-cols-2">
          <div className="rounded-card border border-line bg-surface p-6">
            <h3 className="text-lg font-semibold text-ink">Quickstart</h3>
            <ol className="mt-4 space-y-3 text-sm text-ink-soft">
              <li>1. Create a free account.</li>
              <li>2. Upload a PDB/mmCIF or enter a 4-character PDB ID.</li>
              <li>3. Review the generated system (pH, padding, ions).</li>
              <li>4. Pick a preset and validate.</li>
              <li>5. Start the simulation and watch live progress.</li>
              <li>6. Download trajectories, states, and logs.</li>
            </ol>
          </div>
          <div className="rounded-card border border-line bg-surface p-6">
            <h3 className="text-lg font-semibold text-ink">Launch the app</h3>
            <p className="mt-2 text-sm text-ink-soft">The full console lives at the app URL. Sign in or create an account to begin.</p>
            <a href={APP_URL} className="mt-4 inline-flex rounded-control bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600">Open app</a>
            <h3 className="mt-6 text-lg font-semibold text-ink">Need help?</h3>
            <p className="mt-2 text-sm text-ink-soft">Check the FAQ or contact us for support.</p>
          </div>
        </div>
      </Container>
    </Section>
  )
}
