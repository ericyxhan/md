import { Upload, Cog, PlayCircle, BarChart3 } from 'lucide-react'
import SectionHeader from './SectionHeader'
import Section from '../layout/Section'
import Container from '../layout/Container'

const steps = [
  { icon: Upload, n: '01', title: 'Upload a structure', body: 'PDB, mmCIF, or SDF — or fetch a 4-character RCSB PDB ID. Protein + ligand, or a single complex.' },
  { icon: Cog, n: '02', title: 'Build the system', body: 'Lattice parameterizes with OpenFF, solvates, adds ions, and writes a validated config. Review before running.' },
  { icon: PlayCircle, n: '03', title: 'Run the simulation', body: 'Minimization, equilibration stages, then production. Watch live progress, temperature, density, and speed.' },
  { icon: BarChart3, n: '04', title: 'Inspect & download', body: 'Trajectories, checkpoints, logs, and configs — all registered as artifacts you can download or replay.' },
]

export default function Steps() {
  return (
    <Section className="bg-surface">
      <Container>
        <SectionHeader
          eyebrow="Workflow"
          title="From structure file to trajectory in four steps"
          description="No cluster login, no SLURM, no license files. A bench scientist can go from upload to a queued run in under two minutes."
        />
        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s) => (
            <div key={s.n} className="relative">
              <div className="flex h-12 w-12 items-center justify-center rounded-control bg-brand-500 text-white">
                <s.icon className="h-5 w-5" />
              </div>
              <p className="mt-4 font-mono text-xs font-medium text-brand-600">{s.n}</p>
              <h3 className="mt-1 text-lg font-semibold text-ink">{s.title}</h3>
              <p className="mt-2 text-sm text-ink-soft">{s.body}</p>
            </div>
          ))}
        </div>
      </Container>
    </Section>
  )
}
