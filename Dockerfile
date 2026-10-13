# ---- build: resolve the locked environment with uv -------------------------
FROM python:3.12-slim AS build
# uv comes from PyPI rather than ghcr.io/astral-sh/uv, so building does not depend
# on GitHub Container Registry access (or a builder's stale ghcr credentials).
RUN pip install --no-cache-dir uv==0.9.18
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first so the layer is cached across source-only changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# ---- runtime ----------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app

COPY --from=build --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations

USER app
EXPOSE 8000

# One worker per container: scale horizontally with replicas, not processes.
# Railway/compose run `alembic upgrade head` as a pre-deploy step, not here.
CMD ["sh", "-c", "uvicorn boost_bridge.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
