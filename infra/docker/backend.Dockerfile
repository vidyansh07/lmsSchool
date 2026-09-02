# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Django backend image.
#
# Multi-stage so the runtime layer carries no build toolchain, and split into
# `development` and `production` targets from one common base so the two stay
# in sync. Runs as an unprivileged user in both.
# ---------------------------------------------------------------------------
ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# curl is used by the container healthcheck; libpq is the PostgreSQL client lib.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

# ---------------------------------------------------------------------------
FROM base AS builder
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements/ /tmp/requirements/
ARG REQUIREMENTS=prod.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r /tmp/requirements/${REQUIREMENTS}

# ---------------------------------------------------------------------------
FROM base AS runtime
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY --chown=app:app backend/ /app/
COPY --chown=app:app infra/scripts/backend-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /app/staticfiles /app/mediafiles \
    && chown -R app:app /app/staticfiles /app/mediafiles

USER app
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# ---------------------------------------------------------------------------
# Development: dev dependencies (pytest, ruff) and the autoreloading server.
# ---------------------------------------------------------------------------
FROM runtime AS development
USER root
COPY backend/requirements/ /tmp/requirements/
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential libpq-dev \
    && /opt/venv/bin/pip install -r /tmp/requirements/dev.txt \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /tmp/requirements
USER app
ENV DJANGO_SETTINGS_MODULE=config.settings.local
CMD ["runserver"]

# ---------------------------------------------------------------------------
# Production: gunicorn, no dev tooling.
# ---------------------------------------------------------------------------
FROM runtime AS production
ENV DJANGO_SETTINGS_MODULE=config.settings.production
CMD ["gunicorn"]
