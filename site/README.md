# Lattice marketing website

Static marketing site (Vite + React + Tailwind 4). See `../docs/marketing-website.md` for the hosting
decision and deploy notes.

```bash
npm install
npm run dev     # http://127.0.0.1:5173
npm run build   # dist/
npm run preview
```

Configure the app link at build time:

```bash
VITE_APP_URL=https://your-app-url npm run build
```
