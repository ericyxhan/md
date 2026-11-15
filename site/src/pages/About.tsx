import { useSeo } from '../lib/seo'
import Section from '../components/layout/Section'
import Container from '../components/layout/Container'
import SectionHeader from '../components/marketing/SectionHeader'

export default function About() {
  useSeo('About — MolDy', 'Why MolDy exists.')
  return (
    <Section>
      <Container>
        <SectionHeader eyebrow="About" title="MD simulation for everyone" description="MolDy exists because running a molecular dynamics simulation should not require a cluster, a license, or a specialist." />
        <div className="mx-auto mt-10 max-w-3xl space-y-4 text-ink-soft">
          <p>Molecular dynamics is one of the most powerful tools in structural biology and drug discovery — and one of the least accessible. The software is free and open, but the infrastructure, expertise, and time are not.</p>
          <p>MolDy wraps a real, checkpointed OpenMM pipeline in a guided web console. You upload a structure, review the generated system, pick a preset, and run. Live progress, artifacts, and downloads come standard.</p>
          <p>It is the first platform of its kind for running these MD simulations completely for free. Built on OpenMM, Amber14, and OpenFF 2.3.0. Open methodology, downloadable everything.</p>
        </div>
      </Container>
    </Section>
  )
}
