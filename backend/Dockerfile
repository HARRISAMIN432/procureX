FROM python:3.12.13-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /build
RUN pip install --no-cache-dir uv==0.12.3
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
RUN uv sync --frozen --no-dev

FROM python:3.12.13-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN addgroup --system procurex && adduser --system --ingroup procurex procurex
WORKDIR /app
COPY --from=builder --chown=procurex:procurex /build/.venv ./.venv
COPY --from=builder --chown=procurex:procurex /build/app ./app
USER procurex
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
