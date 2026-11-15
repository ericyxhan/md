import { useSeo } from '../lib/seo'
import Section from '../components/layout/Section'
import Container from '../components/layout/Container'

export default function Terms() {
  useSeo('Terms — Lattice', 'Terms of service.')
  return (
    <Section>
      <Container>
        <div className="mx-auto max-w-3xl space-y-4 text-ink-soft">
          <h1 className="text-3xl font-bold text-ink">Terms of service</h1>
          <p>Lattice is provided free for research and education. You are responsible for the data you upload and for complying with any licenses on input structures. Do not upload data you do not have the right to use.</p>
          <p>The service is provided as-is, without warranty. We may apply fair-use limits to keep the platform available to everyone.</p>
        </div>
      </Container>
    </Section>
  )
}
