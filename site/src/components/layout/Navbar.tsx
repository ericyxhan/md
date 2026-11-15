import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import Container from './Container'
import { Menu, X, ArrowRight } from 'lucide-react'
import { APP_URL } from '../../lib/config'

const links = [
  { to: '/features', label: 'Features' },
  { to: '/how-it-works', label: 'How it works' },
  { to: '/science', label: 'Science' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/docs', label: 'Docs' },
  { to: '/faq', label: 'FAQ' },
]

export default function Navbar() {
  const [open, setOpen] = useState(false)
  return (
    <header className="sticky top-0 z-40 border-b border-line/80 bg-canvas/80 backdrop-blur">
      <Container className="flex h-16 items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
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
          <span className="text-lg font-semibold tracking-tight text-ink">Lattice</span>
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) =>
                `rounded-control px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? 'text-ink' : 'text-ink-soft hover:text-ink'
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>

        <div className="hidden items-center gap-2 md:flex">
          <a href={APP_URL} className="text-sm font-medium text-ink-soft hover:text-ink">Sign in</a>
          <a
            href={`${APP_URL}`}
            className="inline-flex items-center gap-1.5 rounded-control bg-brand-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-600"
          >
            Get started <ArrowRight className="h-4 w-4" />
          </a>
        </div>

        <button
          className="md:hidden rounded-control p-2 text-ink-soft hover:bg-surface-muted"
          onClick={() => setOpen((v) => !v)}
          aria-label="Toggle menu"
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </Container>

      {open && (
        <div className="border-t border-line bg-canvas md:hidden">
          <Container className="flex flex-col gap-1 py-4">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                onClick={() => setOpen(false)}
                className="rounded-control px-3 py-2 text-sm font-medium text-ink-soft hover:bg-surface-muted hover:text-ink"
              >
                {l.label}
              </NavLink>
            ))}
            <a href={APP_URL} className="rounded-control px-3 py-2 text-sm font-medium text-ink-soft hover:bg-surface-muted">Sign in</a>
            <a href={`${APP_URL}`} className="mt-2 rounded-control bg-brand-500 px-3 py-2 text-center text-sm font-medium text-white">Get started</a>
          </Container>
        </div>
      )}
    </header>
  )
}
