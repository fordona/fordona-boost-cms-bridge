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

# ---- boost-stub ---------------------------------------------------------------
# The Boost stub (plan §4.5): a separate deployable, dev and staging only. It
# shares the `build` stage's dependencies (a superset of what it needs) but is
# run from source, not installed as a package: `boost_stub` is deliberately
# excluded from this project's wheel (see [tool.hatch.build.targets.wheel]), so
# `src/boost_stub` is copied in here and nowhere else — in particular, never
# into the `runtime` stage above. Build with `docker build --target boost-stub`.
FROM python:3.12-slim AS boost-stub
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PORT=8080 \
    STUB_SQLITE_PATH=/app/data/stub-changes.sqlite3
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app

COPY --from=build --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src/boost_stub ./src/boost_stub
# The change tracker's SQLite file needs a writable directory; /app itself is
# root-owned (created by WORKDIR before USER app takes effect below).
RUN mkdir -p /app/data && chown app:app /app/data

USER app
EXPOSE 8080

CMD ["sh", "-c", "uvicorn boost_stub.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
