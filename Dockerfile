# ═════════════════════════════════════════════════════════════════════════════
# Clinical Intelligence Platform — Multi-stage Production Dockerfile
#
# ─────────────────────────────────────────────────────────────────────────────
# EXPLANATION
# ─────────────────────────────────────────────────────────────────────────────
#
# WHAT THIS DOCKERFILE DOES
# ──────────────────────────
# This file builds the application in two stages — builder and runtime.
# Think of it like a factory:
#   - Builder  = the room where things are MADE (compiler, build tools, headers)
#   - Runtime  = the room where only the FINISHED PRODUCT lives (venv + app code)
# The ~200 MB of build tooling never makes it into the production image.
# Result: smaller image, faster deploys, smaller attack surface.
#
#
# STAGE 1 — BUILDER
# ──────────────────
# BASE IMAGE: python:3.11-slim
#   Slim removes documentation and extra locales but keeps a full apt ecosystem.
#   3.11 is required by torch 2.x and HuggingFace Transformers 4.x.
#
# BUILD-TIME SYSTEM PACKAGES (never copied to stage 2):
#   build-essential → gcc + g++ + make; required to compile C extensions in
#                     numpy, scipy, pandas, and any Cython-based packages.
#                     Adds ~150 MB — this is exactly what multi-stage eliminates.
#   libpq-dev       → PostgreSQL header files; required to compile psycopg2
#                     from source. At runtime only libpq5 (the shared library)
#                     is needed — not these headers.
#   curl            → used during build to pull extra assets or debug
#                     network connectivity inside the builder layer.
#
# VIRTUALENV STRATEGY:
#   A dedicated venv is created at /venv instead of installing into the system
#   Python. This lets us copy the entire compiled dependency tree to stage 2
#   with a single COPY --from=builder statement. No compiler needed in stage 2.
#
# UV — FAST DEPENDENCY RESOLVER:
#   uv replaces plain pip for the install step. Two key advantages:
#   1. Speed     — significantly faster than pip for large dependency trees.
#   2. Conflict resolution — automatically finds the best mutually compatible
#      version when two packages pin different versions of a shared dependency
#      (e.g. langchain and ragas both requiring different versions of openai).
#   uv must be explicitly installed inside the venv before use — it is not
#   present on the base image.
#
# LAYER CACHING STRATEGY:
#   requirements.txt is copied BEFORE the application source code.
#   Docker only re-runs the pip install layer when requirements.txt changes.
#   A code-only change reuses the cached packages layer — builds stay fast
#   during development. This is the single highest-ROI caching trick in the file.
#
#
# STAGE 2 — RUNTIME
# ──────────────────
# BASE IMAGE: fresh python:3.11-slim — no build tools carried forward.
#
# RUNTIME SYSTEM PACKAGES (executables and .so files called at runtime):
#   libpq5        → PostgreSQL shared library (.so) required by psycopg2 at
#                   runtime. Different from libpq-dev (compile-time headers).
#   tesseract-ocr → OCR engine binary invoked by pytesseract / pdf2image.
#                   This is a runtime executable, not a build tool — it belongs
#                   here, not in stage 1.
#   poppler-utils → PDF CLI tools (pdftotext, pdftoppm) called by pdfplumber
#                   and pdf2image at runtime. Same reasoning as tesseract.
#   curl          → used by container healthcheck probes and liveness checks
#                   defined in docker-compose.yml.
#
# FOLDER STRUCTURE COPIED:
#   main.py        → FastAPI entrypoint; uvicorn/gunicorn target.
#   dashboard.py   → Streamlit UI entrypoint; run via separate compose service.
#   app/           → entire application package: config, database, embeddings,
#                    llm_factory, modules (agent, rag, auth, storage, llm_ops),
#                    schemas, and services.
#   gunicorn_conf.py → production worker config; must be present for the
#                      gunicorn CMD to resolve correctly.
#
#   NOT copied: .env, .env.example, pyproject.toml, requirements.txt,
#               Dockerfile, docker-compose.yml, __pycache__, .git.
#   These are build-time or local-only files with no role at runtime.
#   Secrets always come in via environment variables injected by compose,
#   never baked into the image.
#
# NON-ROOT USER:
#   The app runs as `appuser`, not root. If a vulnerability allows code
#   execution, the attacker gets limited user permissions rather than root
#   access to the host. This is a mandatory practice for production containers.
#
# WRITABLE DIRECTORIES:
#   /app/data    → raw uploaded files and ingestion input.
#   /app/outputs → processed results, exports.
#   /app/.cache  → HuggingFace model cache, embedding cache.
#   Mount these as named volumes in docker-compose.yml so data persists across
#   container restarts without rebuilding the image.
#
# STARTUP COMMAND:
#   Three options are provided — default, development, and production.
#   The Dockerfile sets a sensible default (single uvicorn worker, no reload).
#   Override per-service in docker-compose.yml using the `command:` key so
#   this file stays environment-agnostic and never needs to be edited for
#   environment-specific deployments.
#
#   Development  → uvicorn --reload   (watches files, restarts on save,
#                                      mount source as a volume)
#   Production   → gunicorn           (manages multiple workers, handles
#                                      crashes, preferred for public traffic)
#   Default      → uvicorn no reload  (single worker, works for local testing
#                                      and low-traffic internal deployments)
#
# ENVIRONMENT VARIABLES:
#   PYTHONDONTWRITEBYTECODE=1 → skip .pyc files; saves disk space in the image.
#   PYTHONUNBUFFERED=1        → stdout/stderr flush immediately; logs appear in
#                               real time in `docker logs` and CI pipelines.
#   PORT=8000                 → documents the default port; referenced by
#                               docker-compose.yml and healthcheck scripts.
#
# PORT EXPOSURE:
#   EXPOSE 8000  → FastAPI / uvicorn port.
#   EXPOSE 8501  → Streamlit dashboard port.
#   EXPOSE does NOT publish ports to the host — that is controlled by the
#   `ports:` mapping in docker-compose.yml.
#
# ═════════════════════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — builder
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

RUN pip install --upgrade pip uv

COPY requirements.txt /tmp/requirements.txt
RUN uv pip install --no-cache-dir -r /tmp/requirements.txt


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — runtime
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    tesseract-ocr \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

COPY --from=builder /venv /venv

# Entrypoints
COPY main.py        ./
COPY dashboard.py   ./
COPY gunicorn_conf.py ./

# Application package — copied as a directory, preserving the full structure:
# app/config.py, app/database.py, app/embeddings.py, app/llm_factory.py
# app/modules/{agent,rag,auth,storage,llm_ops}/
# app/schemas/{chat,auth,rag}.py
# app/services/{agent_service,research_service}.py
COPY app/           ./app/
COPY guardrails/    ./guardrails/
COPY assets/        ./assets/
COPY .streamlit/    ./.streamlit/


RUN mkdir -p /app/data /app/outputs /app/.cache /app/assets/images \
    && chown -R appuser:appuser /app /venv

USER appuser

ENV PATH="/venv/bin:$PATH"

# Development  — uvicorn with file watching (use with volume mount in compose):
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production   — gunicorn with multiple managed workers:
# CMD ["gunicorn", "-c", "gunicorn_conf.py", "main:app"]

# Default      — single uvicorn worker, no reload; override via docker-compose:
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

EXPOSE 8000
EXPOSE 8501