# Prep worker image: runs packmol-memgen for membrane embedding.
# Build from the repository root:
#   docker build -f service/worker/prep_worker.Dockerfile -t md-prep-worker:local .
FROM python:3.12-slim

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

RUN groupadd --gid 10002 mdprep \
    && useradd --uid 10002 --gid 10002 --create-home --shell /usr/sbin/nologin mdprep \
    && mkdir -p /home/mdprep \
    && chown -R 10002:10002 /home/mdprep

ENV HOME=/home/mdprep

USER 10002:10002

EXPOSE 8000

CMD ["python", "-u", "prep_worker.py"]
