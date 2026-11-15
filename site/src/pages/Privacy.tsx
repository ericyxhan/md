import { useSeo } from '../lib/seo'
import Section from '../components/layout/Section'
import Container from '../components/layout/Container'

export default function Privacy() {
  useSeo('Privacy — MolDy', 'Privacy policy.')
  return (
    <Section>
      <Container>
        <div className="mx-auto max-w-3xl space-y-4 text-ink-soft">
          <h1 className="text-3xl font-bold text-ink">Privacy policy</h1>
          <p>MolDy stores your account details (email, name) and the files and simulations you create, scoped to your account. We do not sell or share your data. You can download everything you produce at any time.</p>
          <p>Contact us with any privacy questions.</p>
        </div>
      </Container>
    </Section>
  )
}
