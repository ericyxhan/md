# Worker image.  The base image already contains the simulation code and the
# CPU parameterization environment.  Build the simulation image first:
#   docker build -t openmm-cuda12:8.6.1 .
# Then build the worker from service/worker:
#   docker build -t md-worker:local service/worker
FROM openmm-cuda12:8.6.1

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# The conda-forge PyTorch build marks libtorch_cpu.so with an executable
# stack. Newer kernels refuse to dlopen it, which breaks the NAGL charge
# model used by openff-2.3.0. Clear the flag in this layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends patchelf \
    && patchelf --clear-execstack /opt/param-env/lib/libtorch_cpu.so \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/worker

COPY requirements.txt /tmp/worker-requirements.txt
RUN python -m pip install -r /tmp/worker-requirements.txt

COPY . /opt/worker

CMD ["python", "-u", "worker.py"]
