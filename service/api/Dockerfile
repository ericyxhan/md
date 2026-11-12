# API control plane.  Build from the repository root:
#   docker build -f service/api/Dockerfile .
FROM python:3.13-slim

# Shared contract values.  They are declared here so the image can be built
# with the same account and port as the rest of the stack; compose passes
# them from service/contract.env.  The defaults match that file and
# scripts/check-contract.py asserts that they still do.
ARG MD_SERVICE_UID=10001
ARG MD_SERVICE_GID=10001
ARG MD_API_PORT=8000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    SIMULATION_CONFIG_PATH=/app/config.py

# Runtime libraries needed by numpy/scipy/numba wheels.
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

RUN groupadd --gid ${MD_SERVICE_GID} mdservice \
    && useradd --uid ${MD_SERVICE_UID} --gid ${MD_SERVICE_GID} --no-create-home --shell /usr/sbin/nologin mdservice

COPY service/api/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /tmp/requirements.txt

# Only the pure-stdlib validation module is copied from the simulation code.
# The API must never import OpenMM or simulate.py.
COPY config.py /app/config.py
COPY service/api /app

RUN python -m compileall -q /app/app && chown -R ${MD_SERVICE_UID}:${MD_SERVICE_GID} /app

USER ${MD_SERVICE_UID}:${MD_SERVICE_GID}

EXPOSE ${MD_API_PORT}

# The exec form cannot expand build arguments, so the port is written out.
# Compose overrides this command with the value from the contract.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
