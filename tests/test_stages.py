"""Stage runner tests on a tiny OpenMM system."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openmm import (
    BrownianIntegrator,
    LangevinIntegrator,
    LangevinMiddleIntegrator,
    NonbondedForce,
    NoseHooverIntegrator,
    Platform,
    System,
    VariableLangevinIntegrator,
    VariableVerletIntegrator,
    Vec3,
    VerletIntegrator,
    unit,
)
from openmm.app import Element, Topology

from config import (
    BarostatConfig,
    IntegratorConfig,
    MinimizationConfig,
    StageConfig,
)
from stages import (
    create_integrator,
    run_minimization,
    run_stage,
    stage_completed,
)

CPU_PROPERTIES = {"Threads": "1"}


def build_tiny_system() -> tuple[System, Topology, unit.Quantity, unit.Quantity]:
    """Four argon atoms in a small periodic box; enough to exercise OpenMM."""
    topology = Topology()
    chain = topology.addChain("A")
    residue = topology.addResidue("ARG", chain)
    topology.setUnitCellDimensions(Vec3(3, 3, 3) * unit.nanometer)
    box_vectors = topology.getPeriodicBoxVectors()

    system = System()
    system.setDefaultPeriodicBoxVectors(*box_vectors)
    nonbonded = NonbondedForce()
    nonbonded.setNonbondedMethod(NonbondedForce.CutoffPeriodic)
    nonbonded.setCutoffDistance(1.0)

    positions = []
    for index in range(4):
        system.addParticle(39.948)  # argon
        nonbonded.addParticle(0.0, 0.34, 0.997)
        topology.addAtom(
            f"AR{index}", Element.getByAtomicNumber(18), residue
        )
        positions.append(Vec3(0.5 + 0.5 * index, 0.5, 0.5))

    system.addForce(nonbonded)
    return (
        system,
        topology,
        unit.Quantity(positions, unit.nanometer),
        box_vectors,
    )


def make_stage(
    *,
    name: str = "test",
    steps: int = 20,
    barostat: BarostatConfig | None = None,
) -> StageConfig:
    return StageConfig(
        name=name,
        steps=steps,
        report_interval=5,
        trajectory_interval=5,
        checkpoint_interval=5,
        integrator=IntegratorConfig(
            type="langevin_middle",
            temperature_k=300.0,
            friction_per_ps=1.0,
            timestep_ps=0.001,
            random_seed=1,
        ),
        barostat=barostat or BarostatConfig(type="none"),
    )


class IntegratorFactoryTests(unittest.TestCase):
    def test_all_supported_integrators(self) -> None:
        cases = {
            "langevin_middle": LangevinMiddleIntegrator,
            "langevin": LangevinIntegrator,
            "brownian": BrownianIntegrator,
            "verlet": VerletIntegrator,
            "variable_verlet": VariableVerletIntegrator,
            "variable_langevin": VariableLangevinIntegrator,
            "nose_hoover": NoseHooverIntegrator,
        }
        for integrator_type, expected_class in cases.items():
            with self.subTest(integrator_type=integrator_type):
                config = IntegratorConfig(type=integrator_type)
                config.validate("integrator")
                integrator = create_integrator(config)
                self.assertIsInstance(integrator, expected_class)


class StageRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.system, self.topology, self.positions, self.box_vectors = (
            build_tiny_system()
        )
        self.platform = Platform.getPlatformByName("CPU")

    def test_minimization_writes_handoff_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "minimization"
            state_path = run_minimization(
                system=self.system,
                topology=self.topology,
                positions=self.positions,
                box_vectors=self.box_vectors,
                output_dir=output_dir,
                platform=self.platform,
                platform_properties=CPU_PROPERTIES,
                config=MinimizationConfig(),
            )

            self.assertTrue(state_path.is_file())
            self.assertTrue((output_dir / "minimized.pdb").is_file())
            self.assertTrue((output_dir / "minimization.log").is_file())
            self.assertTrue((output_dir / "stage.json").is_file())

    def test_stage_resume_and_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stage_dir = Path(temporary) / "nvt"
            stage = make_stage(steps=20)

            result = run_stage(
                system=self.system,
                topology=self.topology,
                positions=self.positions,
                box_vectors=self.box_vectors,
                stage=stage,
                stage_dir=stage_dir,
                platform=self.platform,
                platform_properties=CPU_PROPERTIES,
            )

            self.assertEqual(result.steps_completed, 20)
            self.assertFalse(result.resumed)
            self.assertTrue(result.checkpoint_path.is_file())
            self.assertTrue(result.state_path.is_file())
            self.assertTrue(stage_completed(stage_dir, stage))

            resumed = run_stage(
                system=self.system,
                topology=self.topology,
                positions=self.positions,
                box_vectors=self.box_vectors,
                stage=stage,
                stage_dir=stage_dir,
                platform=self.platform,
                platform_properties=CPU_PROPERTIES,
            )
            self.assertTrue(resumed.resumed)
            self.assertEqual(resumed.steps_completed, 20)

            extended_stage = make_stage(steps=30)
            self.assertFalse(stage_completed(stage_dir, extended_stage))
            extended = run_stage(
                system=self.system,
                topology=self.topology,
                positions=self.positions,
                box_vectors=self.box_vectors,
                stage=extended_stage,
                stage_dir=stage_dir,
                platform=self.platform,
                platform_properties=CPU_PROPERTIES,
            )
            self.assertTrue(extended.resumed)
            self.assertEqual(extended.steps_completed, 30)
            self.assertTrue(stage_completed(stage_dir, extended_stage))

    def test_npt_stage_starts_from_previous_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nvt = make_stage(name="nvt", steps=10)
            nvt_result = run_stage(
                system=self.system,
                topology=self.topology,
                positions=self.positions,
                box_vectors=self.box_vectors,
                stage=nvt,
                stage_dir=root / "nvt",
                platform=self.platform,
                platform_properties=CPU_PROPERTIES,
            )

            npt = make_stage(
                name="npt",
                steps=10,
                barostat=BarostatConfig(
                    type="monte_carlo",
                    pressure_bar=1.0,
                    temperature_k=300.0,
                    frequency=5,
                    random_seed=1,
                ),
            )
            npt_result = run_stage(
                system=self.system,
                topology=self.topology,
                positions=self.positions,
                box_vectors=self.box_vectors,
                stage=npt,
                stage_dir=root / "npt",
                platform=self.platform,
                platform_properties=CPU_PROPERTIES,
                initial_state_path=nvt_result.state_path,
            )

            self.assertEqual(npt_result.steps_completed, 10)
            self.assertTrue(stage_completed(root / "npt", npt))

    def test_npt_stage_resumes_from_barostat_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stage_dir = Path(temporary) / "npt"
            npt = make_stage(
                name="npt",
                steps=10,
                barostat=BarostatConfig(
                    type="monte_carlo",
                    pressure_bar=1.0,
                    temperature_k=300.0,
                    frequency=5,
                    random_seed=1,
                ),
            )
            first = run_stage(
                system=self.system,
                topology=self.topology,
                positions=self.positions,
                box_vectors=self.box_vectors,
                stage=npt,
                stage_dir=stage_dir,
                platform=self.platform,
                platform_properties=CPU_PROPERTIES,
                reset_velocities=True,
            )
            self.assertEqual(first.steps_completed, 10)

            extended = make_stage(
                name="npt",
                steps=20,
                barostat=npt.barostat,
            )
            second = run_stage(
                system=self.system,
                topology=self.topology,
                positions=self.positions,
                box_vectors=self.box_vectors,
                stage=extended,
                stage_dir=stage_dir,
                platform=self.platform,
                platform_properties=CPU_PROPERTIES,
            )

            self.assertTrue(second.resumed)
            self.assertEqual(second.steps_completed, 20)
            self.assertTrue(stage_completed(stage_dir, extended))

    def test_changed_integrator_rejects_checkpoint_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stage_dir = Path(temporary) / "nvt"
            stage = make_stage(steps=10)
            run_stage(
                system=self.system,
                topology=self.topology,
                positions=self.positions,
                box_vectors=self.box_vectors,
                stage=stage,
                stage_dir=stage_dir,
                platform=self.platform,
                platform_properties=CPU_PROPERTIES,
            )

            changed = make_stage(steps=10)
            changed = StageConfig(
                name=changed.name,
                steps=changed.steps,
                report_interval=changed.report_interval,
                trajectory_interval=changed.trajectory_interval,
                checkpoint_interval=changed.checkpoint_interval,
                integrator=IntegratorConfig(
                    type="langevin_middle",
                    temperature_k=310.0,
                    friction_per_ps=1.0,
                    timestep_ps=0.001,
                    random_seed=1,
                ),
                barostat=changed.barostat,
            )

            with self.assertRaises(RuntimeError) as context:
                stage_completed(stage_dir, changed)
            self.assertIn("--restart-stage", str(context.exception))

    def test_chunked_stepping_reports_monotonic_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stage_dir = Path(temporary) / "chunked"
            stage = make_stage(steps=250)
            events: list[tuple[int, int, int]] = []

            result = run_stage(
                system=self.system,
                topology=self.topology,
                positions=self.positions,
                box_vectors=self.box_vectors,
                stage=stage,
                stage_dir=stage_dir,
                platform=self.platform,
                platform_properties=CPU_PROPERTIES,
                on_progress=lambda step, total, attempt: events.append(
                    (step, total, attempt)
                ),
            )

            self.assertEqual(result.steps_completed, 250)
            self.assertEqual([event[0] for event in events], sorted(
                event[0] for event in events
            ))
            self.assertGreaterEqual(len(events), 3)
            self.assertTrue(all(event[1] == 250 for event in events))
            self.assertEqual(events[-1][0], 250)
            self.assertTrue(stage_completed(stage_dir, stage))

    def test_interrupt_saves_checkpoint_and_marks_stage_canceled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stage_dir = Path(temporary) / "interrupted"
            stage = make_stage(steps=250)

            def interrupt(step: int, _total: int, _attempt: int) -> None:
                if step > 0:
                    raise KeyboardInterrupt

            with self.assertRaises(KeyboardInterrupt):
                run_stage(
                    system=self.system,
                    topology=self.topology,
                    positions=self.positions,
                    box_vectors=self.box_vectors,
                    stage=stage,
                    stage_dir=stage_dir,
                    platform=self.platform,
                    platform_properties=CPU_PROPERTIES,
                    on_progress=interrupt,
                )

            self.assertTrue((stage_dir / "checkpoint.chk").is_file())
            manifest = json.loads(
                (stage_dir / "stage.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "canceled")
            self.assertFalse(stage_completed(stage_dir, stage))


if __name__ == "__main__":
    unittest.main()
