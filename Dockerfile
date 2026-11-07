# CPU-only OpenFF/SMIRNOFF parameterization environment.  It is copied into
# the final image so simulate.py can launch prepare_system.py without needing
# OpenFF in the CUDA simulation environment.
FROM condaforge/miniforge3:latest AS param-env

COPY environment-param.yml /tmp/environment-param.yml
RUN conda env create -y -p /opt/param-env -f /tmp/environment-param.yml \
    && conda clean -afy


FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENMM_PARAMETERIZER_PYTHON=/opt/param-env/bin/python

# Runtime libraries needed by OpenMM, RDKit, and the CUDA wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        libgl1 \
        libxrender1 \
        libxext6 \
        libsm6 \
        libice6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=param-env /opt/param-env /opt/param-env

# Install the CUDA simulation environment first so this layer is cached when
# only code changes.
COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . .

# Fail the build early if the workflow modules do not compile or the
# dependency-free stage tests fail.  The stage tests use OpenMM's CPU platform,
# so this check also verifies that the installed OpenMM package is usable.
RUN python -m compileall -q . \
    && python -m unittest discover -s tests -t .

# The NVIDIA driver (libcuda.so.1) is injected by the NVIDIA container runtime;
# all other CUDA libraries come from the pip nvidia-* packages.
CMD ["python", "check_gpu.py"]
