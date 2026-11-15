# MolDy marketing website

## Hosting decision

**Recommendation: host the marketing site on a separate origin from the app, not as a path on the same origin.**

Concretely:

- Marketing site: `https://moldy.<tld>` (or `https://www.moldy.<tld>`), deployed as a static site
  (GitHub Pages / Cloudflare Pages / Netlify free tier).
- App console: `https://app.moldy.<tld>`, the existing MolDy service behind Caddy + Tailscale Funnel
  (unchanged).

### Why not `moldy.<tld>` marketing + `app.moldy.<tld>` app

Moving the app to a subdomain would force three changes for no functional gain:

1. The signed session cookie is set with `Path=/` and `SameSite=Lax` on the app origin. A subdomain
   split requires either a shared registrable domain cookie (`.moldy.<tld>`) or re-issuing cookies,
   plus a CORS/credentials rework in `service/web` and `service/api`.
2. CSRF double-submit relies on same-origin; cross-subdomain is still same-site but not same-origin,
   which needs explicit handling.
3. The Tailscale Funnel hostname is fixed (`*.ts.net`) and cannot be a subdomain of a purchased domain
   without a custom domain + TLS setup, which costs money — against the free-only constraint.

### Why not marketing as a path on the app origin (`/` marketing, `/app` console)

The app already owns `/` (the console's SPA). Putting marketing at `/` would require either a reverse
proxy split by path (Caddy routing `/api`, `/healthz`, and the SPA) or a merged bundle. That couples
marketing deploys to app deploys and risks breaking the console's history fallback. It also makes the
marketing site inherit the app's (restricted) origin for SEO/OG scraping.

### Why a separate static host

- Marketing is pure static HTML/JS/CSS with no secrets and no auth — ideal for a free static host.
- App auth, cookies, and CSRF stay untouched.
- Marketing can be updated (copy, screenshots) without rebuilding the app image.
- SEO, OG tags, and analytics are simpler on a dedicated origin.

### Free hosting options (no domain purchase)

If no domain is purchased, the app keeps its Tailscale Funnel hostname and marketing can live at:

- GitHub Pages on `https://<user>.github.io/<repo>/` (free, HTTPS, custom domain optional later).
- Cloudflare Pages on a `*.pages.dev` hostname (free, HTTPS, fast CDN).
- Netlify on a `*.netlify.app` hostname.

When a domain is eventually purchased, point `moldy.<tld>` at the static host and `app.moldy.<tld>`
at the funnel (or keep the funnel and CNAME it). The marketing site's app link is configurable via
`VITE_APP_URL`, so no code change is needed.

## App link configuration

The marketing site links to the app using `VITE_APP_URL` (default `https://app.moldy.md`). Set it at
build time:

```bash
cd site
VITE_APP_URL=https://server.tailfe0663.ts.net npm run build
```

## Deploy (GitHub Pages example)

1. Enable GitHub Pages for the repository (Settings → Pages → Source: GitHub Actions).
2. Add a workflow that runs `npm ci && npm run build` in `site/` and publishes `site/dist`.
3. Set `VITE_APP_URL` to the live app URL in the workflow env.

A starter workflow is provided at `.github/workflows/marketing.yml`.

## Local development

```bash
cd site
npm install
npm run dev   # http://127.0.0.1:5173
npm run build # outputs site/dist
```

## What this site is NOT

- It is not the app. Sign-in, account creation, and simulation all happen in the app.
- It does not hold secrets or tokens.
- It does not proxy to the API.
