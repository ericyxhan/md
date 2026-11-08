# API control plane.  Build from the repository root:
#   docker build -f service/api/Dockerfile .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    SIMULATION_CONFIG_PATH=/app/config.py

WORKDIR /app

RUN groupadd --gid 10001 mdservice \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin mdservice

COPY service/api/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /tmp/requirements.txt

# Only the pure-stdlib validation module is copied from the simulation code.
# The API must never import OpenMM or simulate.py.
COPY config.py /app/config.py
COPY service/api /app

RUN python -m compileall -q /app/app && chown -R 10001:10001 /app

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
