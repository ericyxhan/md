import { Zap, ShieldCheck, Eye, GitBranch, Cpu, Download, Layers, Users } from 'lucide-react'
import Card from '../ui/Card'
import SectionHeader from './SectionHeader'
import Section from '../layout/Section'
import Container from '../layout/Container'

const features = [
  { icon: Zap, title: 'End-to-end automation', body: 'Upload a structure and Lattice parameterizes, solvates, minimizes, equilibrates, and runs production — no TOML, no cluster.' },
  { icon: ShieldCheck, title: 'Safe by default', body: 'Pydantic-validated inputs, confined file paths, per-account isolation, and signed sessions. Your data stays yours.' },
  { icon: Eye, title: 'Live, legible progress', body: 'Stage timelines, SSE event streams, and progress snapshots make a multi-hour GPU job readable from a phone.' },
  { icon: GitBranch, title: 'Checkpointed & resumable', body: 'Every stage hands off a portable state.xml. Cancel, resume, restart a stage, or reparameterize without losing work.' },
  { icon: Cpu, title: 'Real OpenMM physics', body: 'Amber14 + OpenFF 2.3.0 force fields, NVT/NPT ensembles, HMR, and a CUDA backend on real GPUs.' },
  { icon: Download, title: 'Everything downloadable', body: 'Trajectories, states, configs, logs — registered as artifacts with confined, ID-only downloads.' },
  { icon: Layers, title: 'Membrane embedding', body: 'Embed proteins in POPC/POPE/DPPC bilayers with Packmol-Memgen before simulation.' },
  { icon: Users, title: 'Built for teams', body: 'Self-service accounts, an administrator console, and per-owner queues. Share a box, not a password.' },
]

export default function FeatureGrid({ compact = false }: { compact?: boolean }) {
  return (
    <Section className={compact ? 'py-12' : ''}>
      <Container>
        <SectionHeader
          eyebrow="Capabilities"
          title="Everything you need to run MD, nothing you don't"
          description="Lattice wraps a checkpointed OpenMM pipeline in a guided web console. Defaults first, knobs second."
        />
        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f) => (
            <Card key={f.title} className="transition-shadow hover:shadow-md">
              <div className="flex h-10 w-10 items-center justify-center rounded-control bg-brand-50 text-brand-600">
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="mt-4 text-base font-semibold text-ink">{f.title}</h3>
              <p className="mt-2 text-sm text-ink-soft">{f.body}</p>
            </Card>
          ))}
        </div>
      </Container>
    </Section>
  )
}
