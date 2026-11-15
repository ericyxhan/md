import { Link } from 'react-router-dom'
import Container from './Container'
import { APP_URL, CONTACT_EMAIL } from '../../lib/config'
import { Mail } from 'lucide-react'

export default function Footer() {
  return (
    <footer className="border-t border-line bg-surface">
      <Container className="grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <div className="flex items-center gap-2.5">
            <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden>
              <rect width="32" height="32" rx="8" fill="#0e1b25" />
              <g stroke="#17a394" strokeWidth="1.6" fill="none">
                <circle cx="16" cy="8" r="3" fill="#17a394" />
                <circle cx="8" cy="22" r="3" fill="#17a394" />
                <circle cx="24" cy="22" r="3" fill="#17a394" />
                <line x1="16" y1="11" x2="8" y2="19" />
                <line x1="16" y1="11" x2="24" y2="19" />
                <line x1="11" y1="22" x2="21" y2="22" />
              </g>
            </svg>
            <span className="text-base font-semibold text-ink">Lattice</span>
          </div>
          <p className="mt-3 text-sm text-muted">
            The first platform for running molecular dynamics simulations — completely free.
          </p>
        </div>

        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-faint">Product</h4>
          <ul className="mt-3 space-y-2 text-sm">
            <li><Link to="/features" className="text-ink-soft hover:text-ink">Features</Link></li>
            <li><Link to="/how-it-works" className="text-ink-soft hover:text-ink">How it works</Link></li>
            <li><Link to="/science" className="text-ink-soft hover:text-ink">Science</Link></li>
            <li><Link to="/pricing" className="text-ink-soft hover:text-ink">Pricing</Link></li>
            <li><a href={APP_URL} className="text-ink-soft hover:text-ink">Launch app</a></li>
          </ul>
        </div>

        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-faint">Resources</h4>
          <ul className="mt-3 space-y-2 text-sm">
            <li><Link to="/docs" className="text-ink-soft hover:text-ink">Documentation</Link></li>
            <li><Link to="/faq" className="text-ink-soft hover:text-ink">FAQ</Link></li>
            <li><Link to="/about" className="text-ink-soft hover:text-ink">About</Link></li>
            <li><Link to="/privacy" className="text-ink-soft hover:text-ink">Privacy</Link></li>
            <li><Link to="/terms" className="text-ink-soft hover:text-ink">Terms</Link></li>
          </ul>
        </div>

        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-faint">Contact</h4>
          <ul className="mt-3 space-y-2 text-sm">
            <li>
              <a href={`mailto:${CONTACT_EMAIL}`} className="inline-flex items-center gap-2 text-ink-soft hover:text-ink">
                <Mail className="h-4 w-4" /> {CONTACT_EMAIL}
              </a>
            </li>

          </ul>
        </div>
      </Container>
      <div className="border-t border-line">
        <Container className="flex flex-col items-center justify-between gap-2 py-6 text-xs text-faint sm:flex-row">
          <span>© {new Date().getFullYear()} Lattice. All rights reserved.</span>
          <span>Built on OpenMM. Free for research and education.</span>
        </Container>
      </div>
    </footer>
  )
}
