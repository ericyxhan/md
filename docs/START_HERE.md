# MolDy — Start here (canonical entrypoint)

_Last updated: 2026-11-16_

This is the **recommended reading order** for MolDy. If you are lost in the repo docs, start here.

## Status tags used in docs (convention)
- **Current**: intended to be accurate for the present codebase.
- **Reference**: detailed specs/plans (may lag implementation).
- **Design note / Historical**: context and decisions; verify against code.

## I want to run MolDy (self-hosted)
1. **Service overview (Current)**: [`service/README.md`](../service/README.md)
2. **Deploy checklist (run first)**: `./scripts/deploy-check.sh` from repo root (prints checks + reminders)
3. **Environment template**: `service/.env.example` (fill tokens, paths, secrets)
4. **Compose stack**: see “Docker Compose” in `service/README.md`
5. **If something fails**: use the **“What went wrong”** panel in the Job Detail UI (web) and the Logs tab; also check service logs (`docker compose logs ...`).

## I want to use the web app (quickstart)
- After deploy, open the edge URL (Caddy/Tailscale) → sign in/register → **New Job**.
- Prefer the guided flow; advanced TOML/spec views are for debugging/reproducibility.

## I want to understand the science/workflow
- **Root pipeline (CLI)**: [`README.md`](../README.md)
- **Platform vision / UX direction**: [`docs/platform-vision.md`](platform-vision.md)
- **Roadmap**: [`docs/roadmap-beyond-vanilla-md.md`](roadmap-beyond-vanilla-md.md)

## I want API details
- FastAPI app code: `service/api/app/`
- OpenAPI: typically available when running the API (check `service/README.md` / deployment notes). Treat `/api/v1/*` as the public contract.

## Troubleshooting quick links
- Worker/API logs: `docker compose --env-file service/.env logs api worker` (adjust service names as in `service/compose.yml`)
- GPU: `nvidia-smi`, confirm `CUDA_VISIBLE_DEVICES` and driver/CUDA compatibility (see root `README.md` CUDA notes)

## Contributing / development
- Web: `service/web/` (React/Vite). API: `service/api/`. Worker: `service/worker/`.
- Run tests where available (`service/api/tests`, web tests). See repo docs for current commands.


## Golden path example (try it quickly)
- Sample inputs live in `test_inputs_7yae/` (protein + ligand files). Use them to validate your deployment:
  1. Start the stack and sign in to the web UI.
  2. Create a **New Job** → upload/select the sample protein/ligand (or use the files as a template) and run the **Quick check** preset.
  3. Confirm the job completes and you can view structure/analysis artifacts.
- If you prefer CLI, see the root [`README.md`](../README.md) “Pipeline” section for `simulate.py --config ...` usage with example inputs.
