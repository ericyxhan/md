import { useSeo } from '../lib/seo'
import Section from '../components/layout/Section'
import Container from '../components/layout/Container'
import { Link } from 'react-router-dom'

export default function NotFound() {
  useSeo('Not found — MolDy', 'Page not found.')
  return (
    <Section>
      <Container className="text-center">
        <h1 className="text-5xl font-extrabold text-ink">404</h1>
        <p className="mt-3 text-ink-soft">That page doesn't exist.</p>
        <Link to="/" className="mt-6 inline-flex rounded-control bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600">Go home</Link>
      </Container>
    </Section>
  )
}
