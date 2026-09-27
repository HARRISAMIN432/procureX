FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_AUTH_MODE=oidc
RUN npm run build

FROM python:3.12.13-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /build
RUN pip install --no-cache-dir uv==0.12.3
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
RUN uv sync --frozen --no-dev

FROM python:3.12.13-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        clamav \
        libseccomp2 \
        poppler-utils \
        tesseract-ocr \
    && freshclam --stdout \
    && clamscan --version \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system procurex \
    && adduser --system --ingroup procurex procurex
WORKDIR /app
COPY --from=builder --chown=procurex:procurex /build/.venv ./.venv
COPY --from=builder --chown=procurex:procurex /build/app ./app
COPY --from=frontend-builder --chown=procurex:procurex /frontend/dist ./frontend_dist
COPY --chown=procurex:procurex backend/alembic ./alembic
COPY --chown=procurex:procurex backend/alembic.ini ./alembic.ini
USER procurex
EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
