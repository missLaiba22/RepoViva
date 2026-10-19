# Build from the repo root: docker build -f repository-service/Dockerfile .
FROM python:3.11-slim

# Ingestion shells out to `git clone`.
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY libs/repoviva-common /app/libs/repoviva-common
WORKDIR /app/repository-service

COPY repository-service/pyproject.toml repository-service/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY repository-service ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/repository-service/.venv/bin:$PATH" \
    WORKSPACE_ROOT=/app/repository-service/workspace

EXPOSE 8001
# The worker uses the same image: `python -m repository_service.worker`.
CMD ["uvicorn", "repository_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
