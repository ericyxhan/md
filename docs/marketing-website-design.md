# MolDy marketing website — design & implementation plan

## 1. First principles

### What is the product?
MolDy is a free, web-based molecular dynamics (MD) simulation platform. A user uploads a
biomolecular structure and gets a solvated, parameterized, checkpointed MD run with live
monitoring and downloadable trajectories — without a cluster, a license, or a command line.

### Who is it for?
- Bench scientists who know the chemistry but not the cluster.
- Lab leads who want visibility into runs.
- Computational chemists who want reproducibility and control.
- Students and researchers with no HPC budget.

### What must the site do?
1. Explain what MolDy is in one sentence.
2. State, unambiguously, that it is the first platform of its kind for running MD simulations
   completely free.
3. Show how it works (upload → build → simulate → inspect).
4. List capabilities (force fields, ensembles, artifacts, monitoring, membrane embedding).
5. Remove purchase anxiety: pricing = free, forever.
6. Drive a single conversion: create a free account / open the app.
7. Provide trust: real physics (OpenMM), open methodology, reproducibility, data ownership.

### What must it NOT do?
- Hold secrets or tokens.
- Proxy to the API or duplicate app functionality.
- Make unverifiable claims (no fake testimonials, no invented customer logos).
- Require a domain purchase to deploy.

### Core conversion funnel
Landing → understand value → see how it works → (optional) features/science → pricing (free) → create account in app.

### Single primary CTA
"Create free account" / "Get started" → app's account creation. Secondary: "See how it works".

## 2. Design

### Visual language (continuity with the app console)
- Light, calm scientific console. Off-white canvas, white cards, fine gray rules, deep ink text.
- Single teal accent (`brand-500 #17a394`). Status color only for status.
- Typography: Inter (UI), JetBrains Mono (IDs, code, metrics).
- Radii: 16 px cards, 10 px controls. One restrained card shadow.
- Motion: 350 ms fade-up on entry, soft pulse for active status. No parallax, no decorative animation.
- Respect reduced motion.

### Information architecture
```
/                 Home (hero, steps, features, free promise, CTA)
/features         Feature detail + supported inputs/force fields
/how-it-works     Four-step workflow walkthrough
/science          Methodology, engine, force fields, checkpointing
/pricing          Free, forever + what's included
/docs             Quickstart + launch app
/about            Mission
/faq              Common questions
/privacy          Privacy policy
/terms            Terms of service
```

### Component inventory
- Layout: Navbar, Footer, Container, Section, Layout
- UI: Button, Card, Badge
- Marketing: Hero, SectionHeader, FeatureGrid, Steps, FreePromise

### Key messaging
- Hero: "Molecular dynamics, run in your browser." + "The first platform for running complete
  molecular dynamics simulations — completely free."
- Free promise section states "first platform of its kind — completely free" again, with included list.
- Pricing: "$0 / forever".

## 3. Technical implementation plan

### Stack
- Vite 8 + React 19 + TypeScript
- React Router 7
- Tailwind CSS 4 (CSS-first tokens, matching app)
- lucide-react icons
- framer-motion available (used sparingly)
- No global state library; URL + component state.

### Structure
```
site/
  index.html              (OG tags, fonts, favicon)
  vite.config.ts          (react + tailwind plugins)
  public/                 (favicon, robots, sitemap, 404 fallback)
  src/
    main.tsx, App.tsx
    index.css             (tokens + animations)
    lib/                  (config, seo)
    components/           (layout, ui, marketing)
    pages/                (one per route)
```

### Configuration
- `VITE_APP_URL` → app console URL used in all CTAs (default `https://app.moldy.md`).
- `VITE_CONTACT_EMAIL`, `VITE_GITHUB_URL` optional.

### Hosting
- Separate static host from the app origin (see `docs/marketing-website.md`).
- SPA fallback via `public/404.html` for hosts without server-side rewrite.
- CI: `.github/workflows/marketing.yml` builds `site/` and deploys to GitHub Pages.

### Quality gates
- `npm run typecheck` (tsc -b) and `npm run build` must pass.
- No secret/bearer token/internal URL in the bundle.
- Lighthouse-friendly: semantic HTML, meta tags, sitemap, robots.

## 4. Hosting decision summary

Marketing on its own origin (static host), app unchanged on its origin. Rationale: avoids
breaking the app's same-origin cookie/CSRF model, avoids coupling marketing deploys to app
deploys, and respects the free-only, no-domain-purchase constraint. See `docs/marketing-website.md`.
