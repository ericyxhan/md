# MolDy platform vision — tools vs. experiments

## The split

MolDy has two tiers of capability:

1. **Tools (unit operations).** Single-purpose operations that are useful on
   their own and are the building blocks of a larger study:
   - System preparation (structure cleanup, ligand removal/addition, chain
     selection, residue edits)
   - Membrane embedding (Packmol-Memgen bilayer packing)
   - Docking (AutoDock Vina pose prediction)
   - (future) Property prediction, analysis views

2. **Experiments (workflow tools).** Higher-level orchestration that composes
   tools into a full in-silico study, closer to how a researcher actually
   designs an experiment:
   - Pipelines (linear → DAG orchestration of tools)
   - Workflows / base systems (a prepared system shared by many simulations)
   - (future) Free-energy campaigns, replica ensembles, batch screening

## Why this split

- Researchers think in experiments, not in tool invocations. A tool that
  requires four manual hand-offs (prep → dock → embed → simulate) is a
  workflow in disguise, and forcing the user to be the orchestrator is the
  same friction MolDy exists to remove.
- Separating the tiers keeps each tool independently testable and reusable,
  while the experiment layer can evolve (stepper → canvas → server-side
  engine) without touching the tools.
- It mirrors the existing code: `prep/*` routers and `PrepJob` are the tools;
  `PipelinesPage` and `WorkflowsPage` are the experiments.

## Navigation

The console sidebar now reflects this split:

- **Workspace** — Overview, Simulations, Activity
- **Tools** — System preparation, Membrane embedding, Docking
- **Experiments** — Pipelines, Workflows
- **Coming soon** — Free energy, Property prediction (classified by tier as
  they ship)

## Roadmap implication

Future capabilities should be classified at design time:

- A new *operation* on a structure → Tools.
- A new way to compose/run many operations → Experiments.

When in doubt, ship the tool first (independently useful, independently
testable), then add the experiment-level orchestration on top.
