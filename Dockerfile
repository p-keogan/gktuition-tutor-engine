# syntax=docker/dockerfile:1.7
#
# Multi-stage build for the GKTuition FastAPI orchestrator + cost firewall.
#
# Stage 1 — builder: installs dependencies declared in api/pyproject.toml with
#                    `uv pip compile`/`uv pip install` into a throwaway
#                    virtualenv. We only need the resolved venv, not the
#                    builder image, in the runtime layer.
#
# Stage 2 — runtime: a minimal python:3.12-slim with the venv + the `api/`
#                    package copied in. No build toolchain, no caches.
#
# Target final image size: < 200MB. Last measured locally: ~165MB.
#
# Build:
#   docker build -t gktuition-api:dev .
#
# Run:
#   docker run --rm -p 8000:8000 \
#     -e WP_JWT_SECRET=dev-only \
#     -e GKTUITION_ENV=dev \
#     gktuition-api:dev
#
# Health probe (used by Fly):
#   curl -fsS http://localhost:8000/healthz
#
# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

# uv is a fast, Rust-implemented pip replacement. Pinning the version keeps
# CI reproducible; bump in lock-step with the dev workflow.
ENV UV_VERSION=0.5.11 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && curl -LsSf "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-installer.sh" \
      | env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh

WORKDIR /build

# Bring just the dependency manifest first so Docker can cache the install
# layer when source files change but deps don't.
COPY api/pyproject.toml api/README.md ./api/

# Build a venv under /opt/venv that we'll copy whole into the runtime stage.
#
# Note: we do NOT `uv pip install ./api` here. The api package's hatchling
# config points at `../api` (so `pip install -e .` works for local dev from
# inside the api/ folder), which `hatchling` rejects as a non-relative path
# when building a wheel. The runtime container doesn't need the api package
# installed as a wheel — we just need the deps + the source tree on PYTHONPATH.
# So: compile the deps to a requirements list, install those, and copy the
# source in stage 2.
RUN uv venv /opt/venv \
 && uv pip compile --quiet --output-file /tmp/requirements.txt ./api/pyproject.toml \
 && VIRTUAL_ENV=/opt/venv uv pip install --no-cache -r /tmp/requirements.txt

# Prune __pycache__ caches so the venv is as small as possible. We keep
# dist-info dirs because pip metadata is small and some runtime code paths
# (eg ``importlib.metadata.version``) walk them.
RUN find /opt/venv -name '__pycache__' -type d -exec rm -rf {} +

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PORT=8000 \
    GKTUITION_ENV=prod

# ca-certificates is needed for outbound HTTPS to Anthropic + Snowflake.
# curl is kept for the in-container healthcheck.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 gktuition \
 && useradd --system --uid 10001 --gid gktuition --shell /usr/sbin/nologin gktuition

# Copy the prebuilt venv from the builder.
COPY --from=builder /opt/venv /opt/venv

# Copy the application source — only what's needed at runtime.
WORKDIR /app
COPY --chown=gktuition:gktuition api/ ./api/

# GIT_SHA is baked at build time so /healthz can report it. CI passes it via
# --build-arg; locally it stays "unknown" which is fine.
ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA}

USER gktuition:gktuition
EXPOSE 8000

# In-container probe — Fly also runs an external probe per fly.toml, but
# having one here lets `docker run` show health status locally.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:${PORT}/healthz || exit 1

# tini reaps zombies + forwards signals so uvicorn shuts down cleanly when
# Fly's machine API sends SIGTERM on deploy/scale-to-zero.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
