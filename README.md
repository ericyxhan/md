# OpenMM protein + ligand workflow

A checkpointed OpenMM 8.6.1 pipeline for protein–ligand systems:

1. parameterize the input in a separate CPU environment;
2. minimize the prepared coordinates;
3. run any number of equilibration stages;
4. run a checkpointed production stage.

The workflow accepts either:

- one structure file containing the protein and its ligands; or
- a protein PDB/mmCIF plus one or more ligand files in SDF, MOL, MOL2, PDB,
  or mmCIF format; or
- a four-character RCSB PDB ID, downloaded automatically.

Disconnected nonstandard components are extracted from the protein, kept as
whole molecules, and parameterized with SMIRNOFF. Protein, water, and ions use
`amber14/protein.ff14SB.xml` + `amber14/tip3p.xml`.

For the FastAPI control plane, SQLite schema, and GPU worker handoff, see
[`service/README.md`](service/README.md) and
[`docs/service-implementation-plan.md`](docs/service-implementation-plan.md).

## Pipeline

```text
input structures
      │
      ▼
prepare_system.py                    separate CPU environment
  PDBFixer, RDKit, OpenFF, gemmi
      │  prepared.pdb + system.xml
      ▼
minimization                         stages/minimization/
      │  state.xml
      ▼
[[equilibration]] stages             stages/<name>/
      │  state.xml after each stage
      ▼
[production]                         stages/production/
      │  checkpointed
      ▼
final state + trajectories + logs
```

Each stage hands the next stage a portable `state.xml` (positions, velocities,
box vectors, time). The stage-local `checkpoint.chk` is used only to resume the
same stage, because a checkpoint is tied to its exact integrator and barostat.
This is what allows NVT → NPT → production transitions.

## Components and versions

| Component | Version |
| --- | --- |
| OpenMM (simulation) | 8.6.1 |
| OpenMM CUDA platform | `OpenMM-CUDA-12` 8.6.1 |
| PDBFixer | 1.12.0 |
| CUDA runtime / NVRTC / cuFFT | 12.9.x (pip `nvidia-*` wheels) |
| Python (local simulation venv) | 3.14 |
| Python (Docker simulation image) | 3.13 |
| Python (parameterization environment) | 3.12 |
| OpenFF Toolkit | 0.19.x |
| SMIRNOFF force field | `openff-2.3.0` |

CUDA 12 is deliberate: it supports Maxwell (GTX 9xx), Pascal, Volta, Turing,
Ampere, Ada, Hopper, and Blackwell GPUs. CUDA 13 drops Maxwell/Pascal/Volta
support, so it would not work on a GTX 960.

## Configuration

All workflow settings live in `config.toml`. Relative paths are resolved
against the directory containing the configuration file, not the current
working directory. Unknown keys are rejected so a typo cannot silently fall
back to a default.

```bash
# Print the fully resolved plan without writing anything.
python simulate.py --config config.toml --dry-run

# Run the default plan.
python simulate.py --config config.toml
```

If `--config` is omitted, `simulate.py` looks for `config.toml` in the current
directory, then next to `simulate.py`.

### Input

Choose exactly one input mode:

```toml
# One complex file containing the protein and its ligands.
[input]
complex = "7YAE.pdb"
```

```toml
# Protein plus separate ligand files.
[input]
protein = "protein.pdb"
ligands = ["ligand.sdf", "ligand.mol2"]
```

```toml
# Download a complex from RCSB.
[input]
pdb_id = "7YAE"
```

For custom ligands, SDF/MOL/MOL2 is preferred because those formats carry bond
orders, formal charges, stereochemistry, and protonation. PDB ligand files use
the RCSB Chemical Component Dictionary (CCD) for bond orders and charges;
peptide and disulfide links are inferred from geometry when the PDB lacks
LINK/CONECT records.

### Run settings

```toml
[run]
output_dir = "outputs"
platform = "CUDA"

# Optional OpenMM platform properties. Values must be strings.
[run.platform_properties]
# Precision = "mixed"
# DeviceIndex = "0"
```

The platform can be overridden without editing the file:

```bash
python simulate.py --platform CPU
python simulate.py --platform CPU --output-dir outputs-cpu-test
```

### Parameterization

```toml
[parameterization]
# Leave commented to use OPENMM_PARAMETERIZER_PYTHON or .param-env/bin/python.
# python = "/opt/param-env/bin/python"

forcefields = ["amber14/protein.ff14SB.xml", "amber14/tip3p.xml"]
ligand_forcefield = "openff-2.3.0"
ph = 7.4
padding_nm = 1.0
ionic_strength_molar = 0.15
add_missing_residues = false
allow_undefined_stereo = false
max_ligand_residues = 50
# ccd_cache = "~/.cache/openmm-parameterizer/ccd"
reuse_existing = true
```

The parameterizer runs as a subprocess in an environment that has OpenFF,
RDKit, PDBFixer, and gemmi. The simulation process only reads `prepared.pdb`
and `system.xml`; it does not import the parameterization stack.

A prepared system is reused only when the input files and chemistry settings
match its fingerprint. `reuse_existing = false` forces a rebuild on every run.
`--reparameterize` also forces a rebuild, and because a new system invalidates
all coordinates and velocities, it clears every simulation stage.

### Minimization

```toml
[minimization]
enabled = true
max_iterations = 0          # 0 = minimize until convergence
tolerance_kj_mol_nm = 10.0
```

Minimization writes `stages/minimization/state.xml`. It is rerun only when it
is missing or when `--restart` / `--restart-stage minimization` is used.

### Equilibration stages

Add, remove, or reorder `[[equilibration]]` blocks to change the number of
stages. They run in file order.

```toml
[[equilibration]]
name = "nvt"
duration_ps = 20.0
report_interval = 1000
trajectory_interval = 1000
checkpoint_interval = 1000
retries = 0
velocity_seed = 1

[equilibration.integrator]
type = "langevin_middle"
temperature_k = 300.0
friction_per_ps = 1.0
timestep_ps = 0.002
random_seed = 1

[equilibration.barostat]
type = "none"

[[equilibration]]
name = "npt"
duration_ps = 100.0
report_interval = 1000
trajectory_interval = 1000
checkpoint_interval = 1000
retries = 0

[equilibration.integrator]
type = "langevin_middle"
temperature_k = 300.0
friction_per_ps = 1.0
timestep_ps = 0.002
random_seed = 1

[equilibration.barostat]
type = "monte_carlo"
pressure_bar = 1.0
temperature_k = 300.0
frequency = 25
random_seed = 1
```

Stage duration is specified with exactly one of:

- `steps = 100000`;
- `duration_ps = 100.0`;
- `duration_ns = 0.1`.

`duration_ps` and `duration_ns` are converted to steps with the integrator
timestep. They require a fixed-step integrator; variable-step integrators must
use `steps`.

### Production

Production follows the last equilibration stage and uses the same kinds of stage
settings:

```toml
[production]
name = "production"
enabled = true
duration_ns = 0.1
report_interval = 1000
trajectory_interval = 5000
checkpoint_interval = 5000
retries = 2
retry_delay_s = 5.0

[production.integrator]
type = "langevin_middle"
temperature_k = 300.0
friction_per_ps = 1.0
timestep_ps = 0.002
random_seed = 1

[production.barostat]
type = "monte_carlo"
pressure_bar = 1.0
temperature_k = 300.0
frequency = 25
random_seed = 1
```

The default production length is deliberately short (0.1 ns). Increase
`duration_ns` for a real production run. Set `enabled = false` to stop after
equilibration.

### Common stage settings

| Key | Meaning |
| --- | --- |
| `name` | Stage directory name; must be unique. |
| `steps` / `duration_ps` / `duration_ns` | Stage length; set exactly one. |
| `report_interval` | Steps between rows in the state log. |
| `trajectory_interval` | Steps between DCD frames. Unset = same as `report_interval`; `0` disables the DCD. |
| `checkpoint_interval` | Steps between `checkpoint.chk` writes. |
| `retries` | Additional attempts after a failure, resuming from the latest checkpoint. |
| `retry_delay_s` | Seconds to wait between attempts. |
| `initial_velocity_temperature_k` | Temperature for velocities when a stage starts from fresh coordinates. Defaults to the integrator temperature. |
| `velocity_seed` | Optional seed for initial velocities. |

Supported integrators:

- `langevin_middle` (recommended default);
- `langevin`;
- `brownian`;
- `verlet` (no thermostat);
- `variable_verlet`;
- `variable_langevin`;
- `nose_hoover`.

Supported barostats:

- `none` — constant volume;
- `monte_carlo` — constant pressure. If `temperature_k` is omitted, it inherits
  the integrator temperature.

## Running locally

The simulation environment is already in `.venv`:

```bash
source .venv/bin/activate
python check_gpu.py
```

Expected output ends with:

```text
Device: NVIDIA GeForce GTX 960
Precision: single
CUDA simulation OK
```

Recreate it with:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python check_gpu.py
```

Create the parameterization environment once:

```bash
./create_param_env.sh
```

This uses micromamba and `environment-param.yml` to create `.param-env`
(Python 3.12 + OpenFF Toolkit, RDKit, PDBFixer, gemmi, OpenMM CPU). If
micromamba is not on `PATH`, the script falls back to `.tools/bin/micromamba`.
Point the workflow at another interpreter with
`parameterization.python` in `config.toml` or with
`OPENMM_PARAMETERIZER_PYTHON`.

Then run:

```bash
python simulate.py --config config.toml
```

For a CPU-only smoke test:

```bash
python simulate.py --config config.toml --platform CPU --dry-run
```

A full CPU run is possible but very slow for solvated systems.

## Checkpoints, resumes, and restarts

The simplest resume is to rerun the same command:

```bash
python simulate.py --config config.toml
```

Completed stages are skipped. An interrupted stage reloads its latest
`checkpoint.chk` and continues from that step. If a checkpoint is corrupt or
contains non-finite energies, it is moved aside and the stage restarts from its
input state.

Use these flags when automatic resume is not what you want:

| Flag | Effect |
| --- | --- |
| `--restart` | Rerun every simulation stage from the prepared (or minimized) coordinates. The prepared system and input files are reused. |
| `--restart-stage NAME` | Rerun `NAME` and every later stage. Earlier completed stages are reused. |
| `--reparameterize` | Rebuild `prepared.pdb` and `system.xml`, then clear every simulation stage. |

Examples:

```bash
# Redo the NPT stage and production, keeping minimization and NVT.
python simulate.py --restart-stage npt

# Redo minimization and everything after it.
python simulate.py --restart-stage minimization

# Rebuild the prepared system and start over.
python simulate.py --reparameterize
```

Changing a stage's step count, logging interval, or retry count does not
invalidate its checkpoint. If production was 0.1 ns and is increased to 1 ns,
rerunning extends the existing production stage from its checkpoint.

Changing a stage's integrator or barostat does invalidate its checkpoint. The
workflow stops with a message asking for `--restart-stage NAME`, because
resuming an incompatible checkpoint would be unsafe.

### Live progress

The service worker runs `simulate.py --progress-file <job_root>/progress.json`.
The file is an atomic JSON document with the current phase, stage, step,
percent, attempt, and timestamp. It is written at lifecycle boundaries and
between bounded simulation chunks so a reader can follow a long stage without
waiting for it to finish. SIGTERM takes the same graceful path as Ctrl-C: the
current stage checkpoint is saved and the process exits 130.

The flag is optional for manual runs and is not written during `--dry-run`.

## Output bundle

```text
outputs/
├── inputs/
│   └── 7YAE.pdb
├── logs/
│   └── parameterization.txt
├── metadata/
│   ├── config.toml
│   ├── parameterization.json
│   ├── parameterization.txt
│   ├── prepared.pdb
│   └── system.xml
└── stages/
    ├── minimization/
    │   ├── minimized.pdb
    │   ├── minimization.log
    │   ├── stage.json
    │   └── state.xml
    ├── nvt/
    │   ├── checkpoint.chk
    │   ├── simulation.log
    │   ├── stage.json
    │   ├── state.xml
    │   └── trajectory.dcd
    ├── npt/
    │   ├── checkpoint.chk
    │   ├── simulation.log
    │   ├── stage.json
    │   ├── state.xml
    │   └── trajectory.dcd
    └── production/
        ├── checkpoint.chk
        ├── simulation.log
        ├── stage.json
        ├── state.xml
        └── trajectory.dcd
```

`stage.json` records status, the stage fingerprint, attempt count, step counts,
duration, and final potential energy. `simulation.log` is the CSV state log.
The production trajectory is often the largest file; increase
`trajectory_interval` to write fewer frames.

## Parameterization details

`prepare_system.py` runs in `.param-env` / `/opt/param-env`:

1. Loads the structure and adds missing atoms/hydrogens with PDBFixer. Missing
   loops are not rebuilt unless `add_missing_residues` is enabled; unresolved
   peptide-chain gaps are split into separate chains so PDBFixer adds proper
   terminal atoms instead of creating a false long peptide bond.
2. Finds disconnected components from the OpenMM topology.
3. Classifies a component as a ligand if any residue has no Amber/water
   template. Short mixed components are treated as one ligand; large connected
   components are rejected unless `max_ligand_residues` is raised deliberately.
4. Builds each PDB ligand as an RDKit/OpenFF molecule using CCD intra-residue
   bond orders, topology/geometry inter-residue bonds, formal-charge fixes, and
   3D stereochemistry. Free N-terminal amines in nonstandard peptide residues
   are protonated; SDF/MOL2 protonation states are kept exactly as supplied.
5. Merges each ligand component into one topology residue with unique atom
   names, preserving atoms, bonds, positions, charge, and stereochemistry.
6. Registers `SMIRNOFFTemplateGenerator` with the Amber force field and builds
   the solvated combined `System`.
7. Writes `prepared.pdb`, `system.xml`, and `parameterization.txt`.

PDBFixer's CPU hydrogen minimization is pinned to one thread and the
standard-library RNG is seeded, so repeated parameterization with the same
inputs is reproducible.

Before solvation, every polymer/solvent residue is checked with
`forcefield_coverage.py`. If a residue has no Amber/water template, the run
stops with a coverage report instead of failing later in `createSystem`.
Standalone coverage checks still work:

```bash
python forcefield_coverage.py 7YAE.pdb amber14/protein.ff14SB.xml amber14/tip3p.xml --try-hydrogens
```

## Docker

The Docker image contains both environments:

- the pip OpenMM CUDA 12 simulation environment;
- `/opt/param-env`, the CPU OpenFF parameterization environment.

Build it with:

```bash
docker build -t openmm-cuda12:8.6.1 .
```

The build compiles the workflow modules and runs the CPU-only unit tests. Run
the GPU check:

```bash
docker run --rm --gpus all openmm-cuda12:8.6.1
```

Run the workflow with the project mounted:

```bash
docker run --rm --gpus all \
  -v "$PWD":/app -w /app \
  openmm-cuda12:8.6.1 python simulate.py --config config.toml
```

Inspect the plan without a GPU:

```bash
docker run --rm \
  -v "$PWD":/app -w /app \
  openmm-cuda12:8.6.1 python simulate.py --config config.toml --dry-run
```

Run the unit tests:

```bash
docker run --rm \
  -v "$PWD":/app -w /app \
  openmm-cuda12:8.6.1 python -m unittest discover -s tests -t .
```

Or use Compose:

```bash
docker compose run --rm openmm      # GPU check
docker compose run --rm dry-run     # resolved plan, no GPU
docker compose run --rm test        # CPU-only tests
docker compose run --rm simulate    # full workflow, needs a GPU
```

## Server prerequisites

On the GPU server you need:

1. An NVIDIA driver compatible with CUDA 12.x (driver >= 525.60.13).
2. The [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
   installed and configured for Docker.
3. A working GPU pass-through, verifiable with:

   ```bash
   docker run --rm --gpus all nvidia/cuda:12.9.1-base-ubuntu24.04 nvidia-smi
   ```

The image does not bundle the NVIDIA kernel driver. The container runtime
injects `libcuda.so.1` from the host; the pip `nvidia-*` packages provide the
rest of the CUDA user-space libraries.

If Docker reports `could not select device driver "" with capabilities:
[[gpu]]`, the NVIDIA Container Toolkit is not registered with the Docker
daemon. Install/configure it and restart Docker; this is a host configuration
issue, not an image issue.

## Notes and limitations

- A GTX 960 has only 2 GB of VRAM. The full 7YAE complex at the default
  `padding_nm = 1.0` produced 398,753 particles and used about 670 MiB for the
  CUDA context in testing, so it fits but is slow. Larger complexes or more
  padding can exceed 2 GB; use a larger GPU for production runs.
- Ligand protonation is taken from PDBFixer/CCD for PDB inputs; free
  N-terminal amines in nonstandard peptide residues are protonated
  automatically. For pH-specific or non-RCSB ligands, supply an SDF/MOL2 file
  with the desired protonation and formal charges.
- A large protein chain with a covalent nonstandard modification is not
  silently merged into one ligand. Provide the ligand separately or raise
  `max_ligand_residues` only after confirming that treating the whole component
  as one molecule is appropriate.
- Separate ligand coordinates must be in the same frame as the protein. The
  workflow combines topology and coordinates but does not perform docking or
  automatic placement.
- Do not name a script `openmm.py` or any name that shadows an imported package.
- The stage fingerprint intentionally covers only integrator and barostat
  settings. If you change the prepared `system.xml` by hand, use
  `--reparameterize` or `--restart`.
- The parameterization fingerprint covers the input files and chemistry
  settings. After changing `prepare_system.py` itself, use
  `--reparameterize` if you want to rebuild an existing prepared system.
