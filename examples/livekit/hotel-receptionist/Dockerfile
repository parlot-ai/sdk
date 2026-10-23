# syntax=docker/dockerfile:1
#
# Shared Dockerfile for every example under examples/. Byte-identical
# across the tree — each example's entry script is named `agent.py`,
# so there's no per-example variation left.
ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/app" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

RUN apt-get update && apt-get install -y \
    git \
    git-lfs \
    gcc \
    g++ \
    python3-dev \
  && rm -rf /var/lib/apt/lists/*

# Enable git-lfs so pip's git installs smudge LFS-tracked binaries
# (e.g. silero's bundled VAD onnx) instead of leaving pointer files.
# --system so the unprivileged appuser below inherits the filters.
RUN git lfs install --system

WORKDIR /app
USER appuser

COPY requirements.txt ./
# Bootstraps pip >=26.2.2 (emSign CA incident): image-bundled pip vendors
# an older certifi that OS trust alone cannot override.
RUN pip install --user --no-cache-dir \
    "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70" \
  && pip install --user --no-cache-dir -r requirements.txt

# Pre-download model weights plugins ship (silero VAD, turn-detector, …)
# so the container is ready to take traffic without a cold-download stall.
RUN python -m livekit.agents download-files

COPY . .

CMD ["python", "agent.py", "start"]
