import { useSeo } from '../lib/seo'
import Hero from '../components/marketing/Hero'
import Steps from '../components/marketing/Steps'
import FeatureGrid from '../components/marketing/FeatureGrid'
import FreePromise from '../components/marketing/FreePromise'
import { Link } from 'react-router-dom'
import { APP_URL } from '../lib/config'
import { ArrowRight } from 'lucide-react'
import Container from '../components/layout/Container'
import Section from '../components/layout/Section'

export default function Home() {
  useSeo('Lattice — Molecular dynamics, free', 'The first platform for running complete molecular dynamics simulations — completely free. From structure file to trajectory in minutes.')
  return (
    <>
      <Hero />
      <Steps />
      <FeatureGrid />
      <FreePromise />
      <Section className="bg-brand-900 text-white">
        <Container className="text-center">
          <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Ready to run your first simulation?</h2>
          <p className="mx-auto mt-4 max-w-xl text-brand-100">
            Create a free account and queue a real MD run in under two minutes. No credit card, no trial.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a href={`${APP_URL}`} className="inline-flex items-center gap-2 rounded-control bg-white px-6 py-3.5 text-base font-medium text-brand-900 hover:bg-brand-50">
              Create free account <ArrowRight className="h-4 w-4" />
            </a>
            <Link to="/docs" className="inline-flex items-center gap-2 rounded-control border border-brand-300 px-6 py-3.5 text-base font-medium text-white hover:bg-brand-700">
              Read the docs
            </Link>
          </div>
        </Container>
      </Section>
    </>
  )
}
