# Build from the repo root: docker build -f core-api/Dockerfile .
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY libs/repoviva-common /app/libs/repoviva-common
WORKDIR /app/core-api

# Dependencies first so code changes don't reinstall them.
COPY core-api/pyproject.toml core-api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY core-api ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/core-api/.venv/bin:$PATH"

EXPOSE 8000
# The worker uses the same image: `python -m core_api.worker`.
CMD ["sh", "-c", "alembic upgrade head && uvicorn core_api.main:app --host 0.0.0.0 --port 8000"]
