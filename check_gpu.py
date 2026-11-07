#!/usr/bin/env python3
"""Check that OpenMM can run on the available NVIDIA GPU."""

import sys

import numpy as np
import openmm as mm


def main() -> None:
    print(f"OpenMM {mm.__version__}")

    platforms = [
        mm.Platform.getPlatform(i).getName()
        for i in range(mm.Platform.getNumPlatforms())
    ]
    print("Available platforms:", ", ".join(platforms))

    if "CUDA" not in platforms:
        sys.exit("ERROR: the CUDA platform is not available.")

    platform = mm.Platform.getPlatformByName("CUDA")

    # Small periodic Lennard-Jones system, enough to exercise the CUDA kernels.
    n_particles = 200
    system = mm.System()
    system.setDefaultPeriodicBoxVectors(
        mm.Vec3(3, 0, 0), mm.Vec3(0, 3, 0), mm.Vec3(0, 0, 3)
    )
    for _ in range(n_particles):
        system.addParticle(39.948)  # argon

    lj = mm.NonbondedForce()
    lj.setNonbondedMethod(mm.NonbondedForce.CutoffPeriodic)
    lj.setCutoffDistance(1.0)
    lj.setUseSwitchingFunction(True)
    lj.setSwitchingDistance(0.9)
    for _ in range(n_particles):
        lj.addParticle(0.0, 0.34, 0.997)
    system.addForce(lj)

    integrator = mm.VerletIntegrator(0.001)
    context = mm.Context(system, integrator, platform)
    rng = np.random.default_rng(0)
    context.setPositions(rng.uniform(0, 3, (n_particles, 3)))
    context.setVelocitiesToTemperature(300)
    integrator.step(200)

    energy = context.getState(energy=True).getPotentialEnergy()
    device = platform.getPropertyValue(context, "DeviceName").strip()
    precision = platform.getPropertyValue(context, "Precision").strip()

    print(f"Device: {device}")
    print(f"Precision: {precision}")
    print(f"Potential energy after 200 steps: {energy}")
    print("CUDA simulation OK")


if __name__ == "__main__":
    main()
