# Prep worker image: runs packmol-memgen for membrane embedding.
# Build from the repository root:
#   docker build -f service/worker/prep_worker.Dockerfile -t md-prep-worker:local .
FROM python:3.12-slim

# Shared contract values, the same ones the API uses.  The prep worker writes
# into the same data volume as the API, so it has to run as the same account:
# two different accounts produce files the other cannot read, and a backup
# misses the difference.  Compose passes these from service/contract.env.
ARG MD_SERVICE_UID=10001
ARG MD_SERVICE_GID=10001
ARG MD_API_PORT=8000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

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

WORKDIR /opt/worker

# Prep worker source and its Python dependencies.
COPY prep_worker.py prep_config.py prep_client.py prep_runner.py prep_ops.py requirements-prep.txt packmol-memgen-wrapper /opt/worker/
# Copy the packmol_memgen package so it's available without PyPI access.
COPY packmol_memgen /opt/worker/packmol_memgen
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /opt/worker/requirements-prep.txt \
    && chmod +x /opt/worker/packmol-memgen-wrapper
ENV PYTHONPATH=/opt/worker

RUN groupadd --gid ${MD_SERVICE_GID} mdprep \
    && useradd --uid ${MD_SERVICE_UID} --gid ${MD_SERVICE_GID} --create-home --shell /usr/sbin/nologin mdprep \
    && mkdir -p /home/mdprep \
    && chown -R ${MD_SERVICE_UID}:${MD_SERVICE_GID} /home/mdprep /opt/worker

ENV HOME=/home/mdprep

USER ${MD_SERVICE_UID}:${MD_SERVICE_GID}

EXPOSE ${MD_API_PORT}

CMD ["python", "-u", "prep_worker.py"]
